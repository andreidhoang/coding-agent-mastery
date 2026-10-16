"""AI-written teaching harness. Standard library; trusted fixtures only.

This demonstrates protocol/control invariants, NOT OS sandboxing or a live LLM.
One process owns each Ledger. Never use this executor on untrusted repositories.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from typing import Protocol


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bounded(text: str, limit: int = 1200) -> str:
    marker = "\n...[truncated; head and tail retained]...\n"
    if len(text) <= limit:
        return text
    keep = (limit - len(marker)) // 2
    return text[:keep] + marker + text[-keep:]


class Ledger:
    """Durable action journal with conservative recovery of uncertain effects."""

    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS actions (
                id TEXT PRIMARY KEY, request TEXT NOT NULL, result TEXT);
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL, payload TEXT NOT NULL);
        """)
        self.db.commit()
        # An external side effect and SQLite cannot share a transaction.
        # On process restart, do not assume an unrecorded effect did not happen.
        for call_id, in self.db.execute("SELECT id FROM actions WHERE result IS NULL").fetchall():
            self.finish(call_id, {"id": call_id, "ok": False,
                "error": "outcome_unknown", "detail": "Reconcile effect before retrying."})

    def _event(self, kind, payload):
        self.db.execute("INSERT INTO events(kind,payload) VALUES (?,?)", (kind, canonical(payload)))

    def event(self, kind, payload):
        with self.db:
            self._event(kind, payload)

    def begin(self, call):
        """Return an existing result on replay; reject reused IDs with new inputs."""
        encoded = canonical(call)
        row = self.db.execute("SELECT request,result FROM actions WHERE id=?", (call["id"],)).fetchone()
        if row:
            if row[0] != encoded:
                raise ValueError("call_id_collision")
            if row[1] is None:
                raise RuntimeError("action_already_in_flight")
            return json.loads(row[1])
        with self.db:
            self.db.execute("INSERT INTO actions(id,request) VALUES (?,?)", (call["id"], encoded))
            self._event("action_started", call)
        return None

    def finish(self, call_id, result):
        with self.db:
            changed = self.db.execute(
                "UPDATE actions SET result=? WHERE id=? AND result IS NULL",
                (canonical(result), call_id)).rowcount
            if changed != 1:
                raise ValueError("action_already_completed_or_missing")
            self._event("tool_result", result)

    def events(self):
        return [{"seq": seq, "kind": kind, "payload": json.loads(payload)}
                for seq, kind, payload in self.db.execute("SELECT seq,kind,payload FROM events ORDER BY seq")]

    def close(self):
        self.db.close()


class Tools:
    """Path policy is illustrative and has no hostile-concurrency protection."""
    schemas = {"read": {"path"}, "edit": {"path", "sha256", "old", "new"}, "test": set()}

    def __init__(self, root: Path):
        self.root = root.resolve()

    def path(self, name):
        p = (self.root / name).resolve()
        if not p.is_relative_to(self.root) or p.name != "calculator.py":
            raise PermissionError("path_denied")
        return p

    def execute(self, name, args):
        if name not in self.schemas:
            raise PermissionError("tool_denied")
        if not isinstance(args, dict) or set(args) != self.schemas[name]:
            raise ValueError("invalid_tool_schema")
        if any(not isinstance(value, str) for value in args.values()):
            raise ValueError("tool_arguments_must_be_strings")
        if name == "test":
            # Verifier assertions are outside the editable fixture. This is still
            # Python execution on the host; only our own trusted demo may run.
            tested_sha256 = digest(self.path("calculator.py").read_bytes())
            marker = "HARNESS_VERIFIER_COMPLETED_3_ASSERTIONS"
            check = ("import sys; sys.path.insert(0, sys.argv[1]); "
                     "from calculator import add; "
                     "assert add(2,3)==5; assert add(-2,2)==0; "
                     "assert add(0,0)==0; print('HARNESS_VERIFIER_COMPLETED_3_ASSERTIONS')")
            p = subprocess.run([sys.executable, "-I", "-B", "-c", check, str(self.root)],
                               capture_output=True, text=True, timeout=3,
                               env={"PATH": os.defpath})
            unchanged = digest(self.path("calculator.py").read_bytes()) == tested_sha256
            return {"passed": p.returncode == 0 and marker in p.stdout.splitlines() and unchanged,
                    "tested_sha256": tested_sha256, "exit_code": p.returncode,
                    "output": bounded(p.stdout + p.stderr)}
        p = self.path(args["path"])
        data = p.read_bytes()
        if len(data) > 64_000:
            raise ValueError("fixture_too_large")
        text = data.decode("utf-8")
        if name == "read":
            return {"sha256": digest(data), "text": bounded(text),
                    "partial": len(text) > 1200}
        if digest(data) != args["sha256"]:
            raise ValueError("stale_read")
        if not args["old"] or text.count(args["old"]) != 1:
            raise ValueError("edit_anchor_must_be_unique")
        updated = text.replace(args["old"], args["new"], 1).encode("utf-8")
        if len(updated) > 64_000:
            raise ValueError("fixture_too_large")
        # Atomic visibility on one filesystem. Directory fsync/power-loss
        # durability, concurrent writers and permission preservation are future labs.
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".edit-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(updated)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, p)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return {"sha256": digest(updated), "changed": updated != data}


def dispatch(call, tools, ledger):
    """Exactly one durable logical result per accepted ID; no exactly-once effect claim."""
    if not isinstance(call, dict) or set(call) != {"id", "name", "args"}:
        raise ValueError("invalid_call_envelope")
    if not isinstance(call["id"], str) or not call["id"] or not isinstance(call["name"], str):
        raise ValueError("invalid_call_identity")
    cached = ledger.begin(call)
    if cached is not None:
        return cached
    try:
        result = {"id": call["id"], "ok": True, "value": tools.execute(call["name"], call["args"])}
    except (ValueError, PermissionError, OSError, UnicodeError, subprocess.TimeoutExpired) as e:
        result = {"id": call["id"], "ok": False, "error": type(e).__name__, "detail": bounded(str(e))}
    ledger.finish(call["id"], result)
    return result


class Model(Protocol):
    def respond(self, history: list[dict]) -> dict: ...


class ScriptedModel:
    """Deterministic double. Knows the fixture repair; measures no AI capability."""
    def respond(self, history):
        observations = [e for e in history if e["role"] == "tool"]
        n = len(observations)
        if n == 0:
            return {"call": {"id": "read-1", "name": "read", "args": {"path": "calculator.py"}}}
        if n == 1:
            return {"call": {"id": "edit-1", "name": "edit", "args": {
                "path": "calculator.py", "sha256": observations[0]["result"]["value"]["sha256"],
                "old": "return a - b", "new": "return a + b"}}}
        if n == 2:
            return {"call": {"id": "test-1", "name": "test", "args": {}}}
        return {"final": "Candidate repair complete."}


def run(model: Model, tools: Tools, ledger: Ledger, max_turns=8, max_calls=6):
    """One bounded episode. The full model conversation is not resumable yet."""
    history = [{"role": "user", "text": "Fix add and verify the change."}]
    verified_sha256 = None
    calls = 0
    for turn in range(max_turns):
        reply = model.respond(history)
        ledger.event("model_reply", {"turn": turn, "reply": reply})
        history.append({"role": "assistant", "reply": reply})
        if "call" not in reply:
            current_sha256 = digest(tools.path("calculator.py").read_bytes())
            status = "verified" if verified_sha256 == current_sha256 else "unverified"
            ledger.event("stopped", {"reason": status})
            return status, history
        if calls >= max_calls:
            ledger.event("stopped", {"reason": "call_budget"})
            return "call_budget", history
        call = reply["call"]
        result = dispatch(call, tools, ledger)
        calls += 1
        if call["name"] == "edit":
            verified_sha256 = None
        if call["name"] == "test":
            verified_sha256 = (result["value"]["tested_sha256"]
                               if result["ok"] and result["value"]["passed"] else None)
        history.append({"role": "tool", "result": result})
    ledger.event("stopped", {"reason": "turn_budget"})
    return "turn_budget", history


def token_work(prefix: int, delta: int, turns: int):
    """Ideal growing-prefix token accounting; not latency or a provider emulator."""
    if prefix < 0 or delta < 0 or turns < 1:
        raise ValueError("invalid_workload")
    total = turns * prefix + delta * turns * (turns - 1) // 2
    written = prefix + (turns - 1) * delta
    return {"uncached": total, "written": written, "read": total - written}


def main():
    out = Path(__file__).parent / "runs"
    out.mkdir(exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="demo-", dir=out))
    workspace = folder / "workspace"
    workspace.mkdir()
    (workspace / "calculator.py").write_text("def add(a, b):\n    return a - b\n")
    ledger = Ledger(folder / "session.sqlite")
    tools = Tools(workspace)
    baseline = tools.execute("test", {})
    status, history = run(ScriptedModel(), tools, ledger)
    events = ledger.events()
    ledger.close()
    (folder / "trace.jsonl").write_text("".join(canonical(e) + "\n" for e in events))
    summary = {"kind": "deterministic teaching fixture; not a model benchmark",
               "baseline_passed": baseline["passed"], "status": status,
               "tool_results": sum(e["kind"] == "tool_result" for e in events),
               "model_calls": sum(e["kind"] == "model_reply" for e in events),
               "token_example": token_work(20_000, 3_000, 100), "run_directory": str(folder)}
    (folder / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
