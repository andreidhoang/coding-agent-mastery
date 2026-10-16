"""Fixed trusted subprocess fixture for validation-runner cleanup."""

import os
import signal
import subprocess
import sys
import time

import pytest

from scripts.run_local_checks import _terminate_owned_process


@pytest.mark.skipif(os.name != "posix", reason="owned POSIX process group contract")
def test_timeout_cleanup_kills_child_that_ignores_term_after_leader_exits(tmp_path):
    marker = tmp_path / "heartbeat"
    child_source = (
        "import signal,time,pathlib\n"
        "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
        f"p=pathlib.Path({str(marker)!r})\n"
        "while True:\n p.write_text(str(time.monotonic_ns())); time.sleep(.01)\n"
    )
    parent_source = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable,'-c',{child_source!r}]); time.sleep(60)"
    )
    parent = subprocess.Popen(
        [sys.executable, "-c", parent_source],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists(), "authored child fixture failed to start"
        _terminate_owned_process(parent)
        assert parent.poll() is not None
        time.sleep(0.03)
        after = marker.read_text()
        time.sleep(0.08)
        assert marker.read_text() == after, "child continues work after cleanup returned"
    finally:
        try:
            os.killpg(parent.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        parent.wait(timeout=5)
