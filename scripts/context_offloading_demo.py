"""Inspect real mock HTTP request bytes, accepted context, reload and recovery.

Usage: .venv/bin/python scripts/context_offloading_demo.py --output /fresh/path
The output must not exist. This invokes only an httpx MockTransport fixture;
no network connection, model inference or live performance measurement occurs.
"""
# ruff: noqa: E402
import argparse
import json
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from service.artifacts import canonical_bytes, digest_bytes, digest_json
from service.recovery import restore_checkpoint
from service.storage import RuntimeStore


def write_json(path, value):
    path.write_bytes(canonical_bytes(value) + b"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    # The independently authored fixture is shared with its boundary tests.
    fixture = runpy.run_path(str(ROOT / "tests" / "test_context_integration.py"))
    case = fixture["run_case"](output, pause_after_turn=3)
    store, artifacts, owner = case["store"], case["artifacts"], case["owner"]
    tenant, task = owner["tenant_id"], owner["task_id"]
    snapshot = store.snapshot(tenant, task)
    checkpoint = max(snapshot["checkpoints"], key=lambda c: c["manifest"]["next_turn"])
    controller = RuntimeStore("sqlite:///" + str(output / "runtime.db"), artifacts)
    restored = restore_checkpoint(controller, artifacts, tenant, task, checkpoint["checkpoint_id"])
    resumed_controller, fresh_restored, final_result, resumed_requests = fixture["continue_under_fresh_owner"](case, output)
    write_json(output / "recovery.json", restored)
    write_json(output / "fresh-owner-recovery.json", fresh_restored)
    write_json(output / "fresh-owner-actual-request.json", resumed_requests[0]["payload"])
    (output / "fresh-owner-actual-wire.json").write_bytes(resumed_requests[0]["wire_bytes"])
    write_json(output / "fresh-owner-dispatch.json", resumed_requests[0]["dispatch"])
    write_json(output / "fresh-owner-result.json", final_result)
    write_json(output / "snapshot.json", snapshot)
    write_json(output / "raw-final-history.json", final_result["messages"])
    write_json(output / "receipts.json", snapshot["dispatches"])
    comparisons = []
    for index, (payload, dispatch) in enumerate(zip(case["captured"], case["observed_dispatches"], strict=True)):
        acceptance = dispatch["context_acceptance"]
        manifest = acceptance["manifest"]
        accepted = artifacts.get_json(tenant, task, manifest["request_ref"]["digest"])
        projection = artifacts.get_json(tenant, task, manifest["projection_ref"]["digest"])
        source = artifacts.get_json(tenant, task, manifest["raw_history_ref"]["digest"])
        write_json(output / f"turn-{index}-actual-sent-payload.json", payload)
        (output / f"turn-{index}-actual-sent-wire.json").write_bytes(case["captured_bytes"][index])
        write_json(output / f"turn-{index}-accepted-request.json", accepted)
        write_json(output / f"turn-{index}-projection.json", projection)
        write_json(output / f"turn-{index}-source-history.json", source)
        write_json(output / f"turn-{index}-acceptance.json", acceptance)
        observed_record = {**accepted, "payload": payload}
        observed = digest_json(observed_record)
        if observed != manifest["request_digest"]:
            raise RuntimeError("observed mock request differs from accepted request")
        comparisons.append({"turn": index, "projection_id": acceptance["projection_id"],
                            "accepted_request_digest": manifest["request_digest"],
                            "observed_request_digest": observed,
                            "request_payload_bytes": len(canonical_bytes(payload)),
                            "actual_wire_digest": digest_bytes(case["captured_bytes"][index]),
                            "projection_bytes": len(canonical_bytes(projection)),
                            "offload_count": len(manifest["offload_refs"])})
    third = case["observed_dispatches"][2]["context_acceptance"]
    sentinel = fixture["SENTINEL"]
    if sentinel in json.dumps(case["captured"][2]) or sentinel not in json.dumps(final_result["messages"]):
        raise RuntimeError("sentinel distinguishing control failed")
    summary = {"schema": 1, "mode": "local_mock_http_only", "live_performance_claim": False,
               "status": final_result["status"], "request_comparisons": comparisons,
               "reload_projection_id": third["projection_id"],
               "restored_projection_id": restored["context"]["acceptance"]["projection_id"],
               "raw_history_retained": True, "old_tool_only_sentinel_absent_from_third_request": True,
               "recovery_grants_authority": False,
               "fresh_owner_new_projection_id": resumed_requests[0]["dispatch"]["context_acceptance"]["projection_id"],
               "fresh_owner_new_chain": True,
               "source_sha256": {str(path.relative_to(ROOT)): digest_bytes(path.read_bytes())
                                 for path in [ROOT / "service" / name for name in (
                                     "context.py", "context_retrieval.py", "protocol.py", "providers.py",
                                     "storage.py", "harness.py", "recovery.py")]}}
    write_json(output / "summary.json", summary)
    (output / "trace.md").write_text(
        "1. Turn 0 requests old.txt; raw tool result contains the sentinel.\n"
        "2. Turn 1 requests recent.txt; newest batch remains protected.\n"
        "3. Turn 2 replaces the old tool body with an immutable reference. The canonical request reconstructed from the captured mock payload matches the accepted request digest; raw HTTP wire bytes have a separate digest.\n"
        "4. The mock model explicitly requests bounded bytes by accepted digest; the broker records projection provenance and a zero-bound receipt.\n"
        "5. A fresh controller restores the typed checkpoint, verifies the accepted source prefix and request artifacts, and grants no execution authority.\n"
        "6. After explicit mock environment retirement, a new owner dispatches a new projection chain whose lineage points to that validated checkpoint.\n"
        "\nVI: Raw history còn nguyên; chỉ request gửi đi dùng projection. Reload đọc byte theo allowlist của dispatch đã commit. Đây là mock, không chứng minh khả năng nhớ của model thật.\n")
    resumed_controller.close()
    controller.close()
    store.close()
    print(json.dumps({"output": str(output), "status": summary["status"], "mock_requests": len(comparisons) + len(resumed_requests)}))


if __name__ == "__main__":
    main()
