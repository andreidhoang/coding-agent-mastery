"""Adversarial builder boundary checks using synthetic inputs, not acceptance runs."""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import stat
import tarfile
import zipfile

import pytest


SPEC = importlib.util.spec_from_file_location(
    "offline_release_builder", Path(__file__).resolve().parents[1] / "scripts/build_offline_release.py"
)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    for relative in set(builder.FIXED.values()):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("pass\n" if path.suffix == ".py" else "authored fixture\n")
    (root / "pyproject.toml").write_text('[project]\nname="coding-agent-mastery"\nversion="0.1.0"\n')
    (root / "uv.lock").write_text('''version=1
[[package]]
name="coding-agent-mastery"
version="0.1.0"
source={editable="."}
dependencies=[{name="dependency"}]
[[package]]
name="dependency"
version="1.0"
source={registry="https://pypi.org/simple"}
wheels=[{url="https://files.pythonhosted.org/dependency-1.0-py3-none-any.whl",hash="sha256:''' + "a" * 64 + '''",size=12}]
''')
    for product in builder.PRODUCTS:
        directory = root / product
        directory.mkdir(exist_ok=True)
        (directory / "__init__.py").write_text("# authored synthetic fixture\n")
    path = root / "workloads/manifests/tasks.json"
    path.parent.mkdir()
    path.write_text('{"synthetic": true}\n')
    return root


def freeze_source(source, tmp_path):
    path = tmp_path / "manifest.json"
    return path, builder.freeze(source, path)


def fake_wheel(path, manifest, *, omit=None, altered=None, extra=None, identity_version="0.1.0"):
    members = {}
    for target, record in manifest["files"].items():
        if builder.runtime_asset(target) and target != omit:
            # Synthetic fixtures have these exact bytes.
            data = b'{"synthetic": true}\n' if target.endswith(".json") else b"# authored synthetic fixture\n"
            if target in builder.SKILL_ASSETS:
                data = b"authored fixture\n"
            members[target] = data
    if altered:
        members[altered] = b"# stale prior export bytes\n"
    prefix = "coding_agent_mastery-0.1.0.dist-info/"
    members.update({prefix + "METADATA": f"Name: coding-agent-mastery\nVersion: {identity_version}\n".encode(),
                    prefix + "WHEEL": b"Wheel-Version: 1.0\n",
                    prefix + "RECORD": b"", prefix + "licenses/LICENSE": b"authored fixture\n",
                    prefix + "licenses/NOTICE": b"authored fixture\n"})
    if extra:
        members[extra] = b"unexpected\n"
    with zipfile.ZipFile(path, "w") as wheel:
        for name, data in members.items():
            entry = zipfile.ZipInfo(name)
            entry.external_attr = (stat.S_IFREG | 0o644) << 16
            wheel.writestr(entry, data)
    return path


def rewrite_manifest(path, manifest):
    payload = {key: value for key, value in manifest.items() if key != "content_sha256"}
    manifest["content_sha256"] = builder.digest(builder.canonical(payload))
    path.write_text(json.dumps(manifest))


@pytest.mark.parametrize("name", ["/absolute", "../parent", "service/../secret", "service//module.py",
                                 "service/./module.py", "service\\module.py", "tests/helper.py",
                                 "context/private.md", "service/.env.secret", "service/module.pyc"])
def test_forbidden_member_names(name):
    with pytest.raises(builder.ReleaseError):
        builder.path_name(name)


def test_freeze_selects_only_owned_runtime_and_explicit_release_files(source, tmp_path):
    (source / "service/.env").write_text("private")
    (source / "compute/cpu-trace.json").write_text("old measured artifact")
    (source / "evals/reports").mkdir()
    (source / "evals/reports/old.json").write_text("old measured artifact")
    path, manifest = freeze_source(source, tmp_path)
    assert manifest == builder.load_manifest(path)
    assert "workloads/manifests/tasks.json" in manifest["files"]
    assert "LICENSE" in manifest["files"] and manifest["files"]["LICENSE"]["origin"] == "release/LICENSE"
    assert not any(".env" in name or "cpu-trace" in name or "reports" in name for name in manifest["files"])


def test_owned_skill_assets_are_required_and_only_exact_references_are_allowed(source, tmp_path):
    _, manifest = freeze_source(source, tmp_path)
    assert builder.SKILL_ASSETS <= set(manifest["files"])
    for name in builder.SKILL_ASSETS:
        assert builder.runtime_asset(name)
        assert builder.path_name(name) == name
    for name in ("references/private.md", "workloads/skills/other/references/checklist.md",
                 "workloads/skills/verified-repair-guide/references/extra.md"):
        with pytest.raises(builder.ReleaseError, match="forbidden"):
            builder.path_name(name)


@pytest.mark.parametrize("asset", sorted(builder.SKILL_ASSETS))
def test_missing_owned_skill_asset_rejects_freeze(source, tmp_path, asset):
    (source / asset).unlink()
    with pytest.raises(builder.ReleaseError, match="missing selected input"):
        builder.freeze(source, tmp_path / "missing-skill.json")


@pytest.mark.parametrize("parent", [False, True])
def test_symlink_inputs_fail_closed(source, tmp_path, parent):
    if parent:
        actual = source / "service"
        moved = source / "actual-service"
        actual.rename(moved)
        actual.symlink_to(moved, target_is_directory=True)
    else:
        actual = source / "service/alias.py"
        actual.symlink_to(source / "compute/__init__.py")
    with pytest.raises(builder.ReleaseError, match="symlink|aliased"):
        freeze_source(source, tmp_path)


def test_fifo_is_not_read_as_selected_source(source, tmp_path):
    import os
    os.mkfifo(source / "service/device.py")
    with pytest.raises(builder.ReleaseError, match="nonregular"):
        freeze_source(source, tmp_path)


@pytest.mark.parametrize("change", ["add", "remove", "modify"])
def test_source_changes_after_freeze_rejected(source, tmp_path, change):
    _, manifest = freeze_source(source, tmp_path)
    if change == "add":
        (source / "service/newly_appearing.py").write_text("unexpected")
    elif change == "remove":
        (source / "service/__init__.py").unlink()
    else:
        (source / "service/__init__.py").write_text("changed")
    with pytest.raises(builder.ReleaseError, match="allowlist changed|source drift"):
        builder.check_sources(source, manifest)


def test_manifest_tamper_and_duplicate_keys_rejected(source, tmp_path):
    path, manifest = freeze_source(source, tmp_path)
    manifest["files"]["service/__init__.py"]["sha256"] = "f" * 64
    path.write_text(json.dumps(manifest))
    with pytest.raises(builder.ReleaseError, match="identity mismatch"):
        builder.load_manifest(path)
    path.write_text('{"schema":1,"schema":1}')
    with pytest.raises(builder.ReleaseError, match="duplicate JSON key"):
        builder.load_manifest(path)


def test_even_rehashed_unapproved_manifest_addition_rejected(source, tmp_path):
    path, manifest = freeze_source(source, tmp_path)
    manifest["files"]["extra.txt"] = dict(manifest["files"]["LICENSE"])
    rewrite_manifest(path, manifest)
    loaded = builder.load_manifest(path)
    with pytest.raises(builder.ReleaseError, match="allowlist changed"):
        builder.check_sources(source, loaded)


@pytest.mark.parametrize("code", ["import tests\n", "from tests.fixture import x\n", "import runpy\n",
                                 "import sys\nsys.path.insert(0, 'checkout')\n",
                                 "import sys\nsys.path = ['checkout']\n",
                                 "import sys\nsys.path += ['checkout']\n",
                                 "import sys\nsys.path[0:0] = ['checkout']\n",
                                 "import sys\ndel sys.path[0]\n"])
def test_accidental_checkout_acceptance_dependency_rejected(source, tmp_path, code):
    (source / "release/acceptance/installed_package_acceptance.py").write_text(code)
    with pytest.raises(builder.ReleaseError, match="checkout tests/runpy|sys.path"):
        freeze_source(source, tmp_path)


def test_acceptance_may_read_sys_path_to_assert_isolation(source, tmp_path):
    code = "import sys\nfor entry in sys.path:\n    assert 'checkout' not in entry\n"
    (source / "release/acceptance/installed_package_acceptance.py").write_text(code)
    freeze_source(source, tmp_path)


def test_actual_shipped_acceptance_script_is_standalone():
    shipped = Path(__file__).resolve().parents[1] / "release/acceptance/installed_package_acceptance.py"
    builder.check_standalone_script(shipped)


def test_fresh_output_required_and_old_artifact_preserved(source, tmp_path):
    selected = builder.discover(source)
    output = tmp_path / "historical"
    output.mkdir()
    prior = output / "prior.whl"
    prior.write_bytes(b"historical unchanged")
    before = builder.identity(prior)
    with pytest.raises(builder.ReleaseError, match="output collision"):
        builder.check_output(source, output, selected)
    assert builder.identity(prior) == before
    with pytest.raises(builder.ReleaseError):
        builder.check_output(source, source / "service", selected)


def test_staging_and_archive_have_exact_inventory(source, tmp_path):
    _, manifest = freeze_source(source, tmp_path)
    stage = tmp_path / "stage"
    builder.stage_sources(source, stage, manifest)
    archive = tmp_path / "source.tar.gz"
    builder.source_archive(stage, archive, manifest)
    observed = builder.validate_archive(archive, manifest)
    assert set(observed["members"]) == set(manifest["files"]) | {"META/frozen-manifest.json"}


@pytest.mark.parametrize("mutation", ["duplicate", "traversal", "symlink", "extra"])
def test_malicious_source_archive_members_rejected(source, tmp_path, mutation):
    _, manifest = freeze_source(source, tmp_path)
    archive = tmp_path / "malicious.tar.gz"
    names = ["LICENSE", "LICENSE"] if mutation == "duplicate" else [
        "../outside" if mutation == "traversal" else "service/alias.py" if mutation == "symlink" else "unexpected.txt"
    ]
    with tarfile.open(archive, "w:gz") as tar:
        for name in names:
            member = tarfile.TarInfo(name)
            member.mode = 0o644
            data = b"authored fixture\n"
            if mutation == "symlink":
                member.type = tarfile.SYMTYPE
                member.linkname = "LICENSE"
                tar.addfile(member)
            else:
                member.size = len(data)
                tar.addfile(member, io.BytesIO(data))
    with pytest.raises(builder.ReleaseError):
        builder.validate_archive(archive, manifest)


def test_good_wheel_exact_sources_assets_license_and_notice(source, tmp_path):
    _, manifest = freeze_source(source, tmp_path)
    wheel = fake_wheel(tmp_path / "good.whl", manifest)
    assert "workloads/manifests/tasks.json" in builder.wheel_inventory(wheel, manifest)["members"]


@pytest.mark.parametrize("mutation", ["omitted-asset", "stale-source", "extra-source", "private-member", "stale-version"])
def test_wheel_inventory_or_identity_mismatch_rejected(source, tmp_path, mutation):
    _, manifest = freeze_source(source, tmp_path)
    options = {
        "omitted-asset": {"omit": "workloads/manifests/tasks.json"},
        "stale-source": {"altered": "service/__init__.py"},
        "extra-source": {"extra": "service/forgotten.py"},
        "private-member": {"extra": "control-inputs/private.json"},
        "stale-version": {"identity_version": "0.0.9"},
    }[mutation]
    with pytest.raises(builder.ReleaseError):
        builder.wheel_inventory(fake_wheel(tmp_path / "bad.whl", manifest, **options), manifest)


def test_wheel_duplicate_and_symlink_member_rejected(source, tmp_path):
    _, manifest = freeze_source(source, tmp_path)
    wheel = fake_wheel(tmp_path / "bad.whl", manifest)
    with zipfile.ZipFile(wheel, "a") as out:
        entry = zipfile.ZipInfo("service/alias.py")
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        out.writestr(entry, "__init__.py")
    with pytest.raises(builder.ReleaseError, match="nonregular"):
        builder.wheel_inventory(wheel, manifest)


def test_base_requirement_export_is_exact_hash_bound_and_no_extras(source):
    text, closure = builder.export_requirements(source / "uv.lock", "coding-agent-mastery")
    assert text == "dependency==1.0 --hash=sha256:" + "a" * 64 + "\n"
    assert closure["project_extras"] == []
    assert closure["lock"] == builder.identity(source / "uv.lock")


@pytest.mark.parametrize("mutation", ["branch", "source", "hash", "marker"])
def test_ambiguous_or_unsupported_lock_entries_rejected(source, mutation):
    lock = source / "uv.lock"
    text = lock.read_text()
    if mutation == "branch":
        text += '\n[[package]]\nname="dependency"\nversion="2.0"\n'
    elif mutation == "source":
        text = text.replace('registry="https://pypi.org/simple"', 'git="https://example.invalid/repo"')
    elif mutation == "hash":
        text = text.replace("sha256:" + "a" * 64, "md5:1234")
    else:
        text = text.replace('{name="dependency"}', '{name="dependency",marker="undefined_marker"}')
    lock.write_text(text)
    with pytest.raises(builder.ReleaseError):
        builder.export_requirements(lock, "coding-agent-mastery")


@pytest.mark.parametrize("mutation", ["absent", "altered"])
def test_local_dependency_material_missing_or_changed_rejected(source, tmp_path, mutation):
    _, closure = builder.export_requirements(source / "uv.lock", "coding-agent-mastery")
    directory = tmp_path / "wheelhouse"
    directory.mkdir()
    if mutation == "altered":
        (directory / "dependency-1.0-py3-none-any.whl").write_bytes(b"altered")
    with pytest.raises(builder.ReleaseError, match="missing compatible|hash mismatch"):
        builder.verify_wheelhouse(directory, closure)


def test_backend_failure_retains_diagnostics_without_success(source, tmp_path, monkeypatch):
    path, _ = freeze_source(source, tmp_path)
    def failed(*args):
        raise builder.ReleaseError("synthetic backend failure")
    monkeypatch.setattr(builder, "run", failed)
    output = tmp_path / "candidate"
    with pytest.raises(builder.ReleaseError, match="backend failure"):
        builder.build(source, path, output)
    assert (output / "build-failure.json").exists()
    assert not (output / "build-evidence.json").exists()


def test_drift_after_staging_and_backend_rejected(source, tmp_path, monkeypatch):
    path, manifest = freeze_source(source, tmp_path)
    def malicious_backend(command, cwd, log):
        fake_wheel(Path(command[command.index("--wheel-dir") + 1]) / "candidate.whl", manifest)
        (source / "service/__init__.py").write_text("changed after staging")
        return "synthetic backend output"
    monkeypatch.setattr(builder, "run", malicious_backend)
    output = tmp_path / "candidate"
    with pytest.raises(builder.ReleaseError, match="source drift"):
        builder.build(source, path, output)
    assert not (output / "build-evidence.json").exists()


def test_installed_import_contamination_rejected(source, tmp_path):
    _, manifest = freeze_source(source, tmp_path)
    install_root = tmp_path / "external-work"
    prefix = install_root / "venv"
    product_files = {name: {k: record[k] for k in ("sha256", "size")}
                     for name, record in manifest["files"].items() if builder.runtime_asset(name)}
    probe = {"prefix": str(prefix), "base_prefix": "/base-python", "sys_path": [str(prefix / "lib")],
             "origins": {"service": {"path": str(prefix / "lib/service/__init__.py"),
                                     "sha256": manifest["files"]["service/__init__.py"]["sha256"]}},
             "distributions": {"coding-agent-mastery": {"version": "0.1.0", "files": product_files}}}
    builder.check_install_probe(probe, manifest, install_root, [source])
    probe["origins"]["service"]["path"] = str(source / "service/__init__.py")
    with pytest.raises(builder.ReleaseError, match="contamination"):
        builder.check_install_probe(probe, manifest, install_root, [source])
    probe["origins"]["service"]["path"] = str(prefix / "lib/service/__init__.py")
    probe["sys_path"].append(str(source))
    with pytest.raises(builder.ReleaseError, match="sys.path"):
        builder.check_install_probe(probe, manifest, install_root, [source])
