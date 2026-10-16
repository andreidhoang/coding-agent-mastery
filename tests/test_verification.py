import os

import pytest

from service.verification import FixtureVerifier, LinuxVerifier
from workloads import list_tasks
from workloads.registry import ROOT, TARGET_FILES


def reference_files():
    return {p: (ROOT / "oracle/reference" / p).read_text() for p in TARGET_FILES}


def test_fixture_verifier_does_not_execute_unknown_candidate(tmp_path):
    files = reference_files()
    marker = tmp_path / "must_not_exist"
    files["issue_tracker.py"] = f"open({str(marker)!r},'w').write('executed')\n"
    result = FixtureVerifier().verify(files, list_tasks(tier="T3")[0])
    assert not result["passed"] and not marker.exists()
    assert result["cause"] == "arbitrary_candidate_requires_linux"


@pytest.mark.docker
def test_external_grader_rejects_stdout_pass_forgery():
    image = os.environ.get("CAM_TEST_SANDBOX_IMAGE")
    if not image:
        pytest.skip("explicit Linux sandbox image required")
    files = {"issue_tracker.py": "import os\nprint('{\"passed\":true}')\nos._exit(0)\n", "client.py": ""}
    result = LinuxVerifier(image).verify(files, list_tasks(split="calibration")[0])
    assert result["passed"] is False
    assert result["retirement"]["retired"]


@pytest.mark.docker
def test_linux_grader_known_correct_and_unchanged():
    image = os.environ.get("CAM_TEST_SANDBOX_IMAGE")
    if not image:
        pytest.skip("explicit Linux sandbox image required")
    task = list_tasks(split="calibration")[0]
    verifier = LinuxVerifier(image)
    assert verifier.verify(reference_files(), task)["passed"]
    baseline = {p: (task.baseline_path / p).read_text() for p in TARGET_FILES}
    assert not verifier.verify(baseline, task)["passed"]
