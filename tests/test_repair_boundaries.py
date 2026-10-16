"""Independent patch application and bounded saved-history export checks."""

import subprocess

import pytest

from service.integration import candidate_manifest
from service.repair import committed_repair_events


@pytest.mark.parametrize("before,after", [
    ("old", "new"), ("old\n", "new"), ("old", "new\n"),
    ("old\r\n", "new\r\n"), ("a\u2028b\n", "a\u2028c\n"),
    ("", "new"), ("old", ""), ("a\nb", "a\nc"),
])
def test_git_applied_patch_reconstructs_exact_supported_bytes(tmp_path, before, after):
    source = tmp_path / "calc.py"
    source.write_bytes(before.encode())
    manifest = candidate_manifest({"calc.py": before}, {"calc.py": after}, ["calc.py"], {}, ["repair"])
    patch = tmp_path / "change.patch"
    patch.write_bytes(manifest["patch"].encode())
    result = subprocess.run(["git", "apply", "--no-index", str(patch)], cwd=tmp_path,
                            capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert source.read_bytes() == after.encode()


def test_export_pages_through_exact_snapshot_frontier_without_later_events():
    class Store:
        def __init__(self):
            self.calls = []

        def events(self, tenant, task_id, cursor, limit):
            self.calls.append(cursor)
            start = int(cursor or 0) + 1
            events = [{"sequence": n} for n in range(start, min(start + limit, 1206))]
            return {"events": events, "cursor": str(events[-1]["sequence"]), "service_incarnation": "i"}

    store = Store()
    events = committed_repair_events(store, "tenant", "task", {"frontier": {
        "sequence": 1203, "service_incarnation": "i",
    }})
    assert [e["sequence"] for e in events] == list(range(1, 1204))
    assert store.calls == [None, "1000"]


def test_missing_event_history_cannot_be_exported_as_complete():
    class Store:
        def events(self, *args, **kwargs):
            return {"events": [], "cursor": "0", "service_incarnation": "i"}

    with pytest.raises(RuntimeError, match="incomplete"):
        committed_repair_events(Store(), "tenant", "task", {"frontier": {
            "sequence": 2, "service_incarnation": "i",
        }})


@pytest.mark.parametrize("sequences", [[3], [1, 3], [1, 1, 3]])
def test_missing_prefix_middle_or_duplicate_cannot_be_exported_as_complete(sequences):
    class Store:
        def events(self, *args, **kwargs):
            return {"events": [{"sequence": n} for n in sequences], "cursor": "3", "service_incarnation": "i"}

    with pytest.raises(RuntimeError, match="prefix, gap or duplicate"):
        committed_repair_events(Store(), "tenant", "task", {"frontier": {
            "sequence": 3, "service_incarnation": "i",
        }})
