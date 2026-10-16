"""Protected behavior grader. Never copy this into a worker workspace.

Caller supplies trusted-control classes locally, or classes loaded ONLY inside
an externally enforced candidate Linux sandbox. Assertions require no pytest.
"""
import tempfile
from pathlib import Path

REQUIREMENT_IDS = ("tenant_idempotency", "resume_atomicity", "cancellation", "cursor_binding", "pagination", "sync_compatibility")


def csv_input(label="Issue", count=5):
    return "issue_id,title\n" + "".join(f"{i},{label} {i}\n" for i in range(count))


def _raises(exception, operation):
    try:
        operation()
    except exception:
        return
    raise AssertionError(f"expected {exception.__name__}")


def _all_events(tracker, tenant, job_id):
    cursor = None
    events = []
    for _ in range(100):
        page = tracker.progress(tenant, job_id, cursor, limit=1)
        if not page["events"]:
            return events
        events.extend(page["events"])
        cursor = page["cursor"]
    raise AssertionError("pagination never terminates")


def check(requirement, tracker_module, client_module, variant=0):
    """A variant changes synthetic labels only; it is not an independent task."""
    Tracker = tracker_module.IssueTracker
    label = f"Synthetic {variant}"
    data = csv_input(label)
    if requirement == "tenant_idempotency":
        t = Tracker()
        try:
            first = t.submit_import("a", "key", data)
            assert t.submit_import("a", "key", data.replace("\n", "\r\n")) == first
            _raises(tracker_module.Conflict, lambda: t.submit_import("a", "key", csv_input("changed")))
            second = t.submit_import("b", "key", csv_input("tenant b"))
            assert first != second
            _raises(KeyError, lambda: t.status("b", first))
            _raises(ValueError, lambda: t.submit_import("a", "bad", "title,issue_id\nbad,x\n"))
        finally:
            t.close()
    elif requirement == "resume_atomicity":
        with tempfile.TemporaryDirectory() as root:
            database = str(Path(root) / "fixture.sqlite")
            t = Tracker(database)
            job = t.submit_import("a", "resume", data)
            _raises(RuntimeError, lambda: t.process_batch("a", job, crash_before_commit=True))
            assert t.status("a", job)["processed"] == 0
            assert t.list_issues("a") == []
            assert t.process_batch("a", job)["processed"] == 2
            t.close()
            t = Tracker(database)
            try:
                for _ in range(3):
                    t.process_batch("a", job)
                assert t.status("a", job)["status"] == "complete"
                assert t.status("a", job)["processed"] == 5
                assert [row["issue_id"] for row in t.list_issues("a")] == [str(i) for i in range(5)]
                # Replayed processing after completion cannot alter issues/events.
                before = t.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
                t.process_batch("a", job)
                assert t.db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == before
            finally:
                t.close()
    elif requirement == "cancellation":
        t = Tracker()
        try:
            job = t.submit_import("a", "cancel", data)
            t.process_batch("a", job)
            t.cancel("a", job)
            count = t.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            t.cancel("a", job)
            t.process_batch("a", job)
            assert t.status("a", job)["status"] == "cancelled"
            assert t.status("a", job)["processed"] == 2
            assert len(t.list_issues("a")) == 2
            assert t.db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == count
            empty = t.submit_import("a", "empty", "issue_id,title\n")
            assert t.cancel("a", empty)["status"] == "complete"
        finally:
            t.close()
    elif requirement == "cursor_binding":
        t = Tracker()
        try:
            a = t.submit_import("a", "first", data)
            b = t.submit_import("a", "second", data)
            c = t.submit_import("b", "first", data)
            cursor = t.progress("a", a)["cursor"]
            _raises(tracker_module.InvalidCursor, lambda: t.progress("a", b, cursor))
            _raises(tracker_module.InvalidCursor, lambda: t.progress("b", c, cursor))
            _raises(tracker_module.InvalidCursor, lambda: t.progress("a", a, "broken!"))
            _raises(tracker_module.InvalidCursor, lambda: t.progress("a", a, t._cursor("a", a, 100)))
        finally:
            t.close()
    elif requirement == "pagination":
        t = Tracker()
        try:
            job = t.submit_import("a", "page", data)
            t.process_batch("a", job)
            first = t.progress("a", job, limit=1)
            cursor = first["cursor"]
            assert first["events"][0]["seq"] == 1
            second = t.progress("a", job, cursor, limit=1)
            assert second["events"][0]["seq"] == 2
            t.cancel("a", job)
            events = _all_events(t, "a", job)
            assert [row["seq"] for row in events] == [1, 2, 3]
            tail = t.progress("a", job, t._cursor("a", job, 3))
            assert tail["events"] == []
        finally:
            t.close()
    elif requirement == "sync_compatibility":
        t = Tracker()
        try:
            client = client_module.ImportClient(t)
            # One-row batches keep this criterion independent of the resume defect.
            one_batch = csv_input(label, count=2)
            assert len(client.import_csv(one_batch, "small")) == 2
            # Integration criterion requires multiple batches and full completion.
            job = client.submit("large", data)
            result = client.import_csv(data, "large")
            assert isinstance(result, list)
            assert t.status("default", job)["status"] == "complete"
            assert len(result) == 5
            assert client.import_csv(data, "large") == result
        finally:
            t.close()
    else:
        raise ValueError("unknown requirement")


def grade(requirements, tracker_module, client_module, variant=0):
    results = []
    for requirement in requirements:
        try:
            check(requirement, tracker_module, client_module, variant)
        except Exception as error:
            results.append({"requirement": requirement, "passed": False,
                            "error_type": type(error).__name__, "message": str(error)[:500]})
        else:
            results.append({"requirement": requirement, "passed": True})
    return {"passed": all(row["passed"] for row in results), "criteria": results}
