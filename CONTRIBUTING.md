# Contributing

This private repository is a source snapshot for engineering collaboration and AI-assisted work. Its reference runtime uses authored fixtures and scripted or mocked providers. Passing those checks does not establish live-model quality, hostile-code containment, CUDA performance, or production readiness.

## Set up a checkout

Use Python 3.11 or later and an installed `uv`. Dependency installation may access the package registry; the checks below use local fixtures and mock transports.

```sh
git clone git@github.com:andreidhoang/coding-agent-mastery.git
cd coding-agent-mastery
uv sync --locked --extra dev
.venv/bin/python -m service doctor
```

`dev` is an optional dependency extra. This installs the locked base runtime, pytest and Ruff, without requesting the `production` or `compute` extras. Missing optional packages reported by `doctor` are expected. Keep `uv.lock` unchanged unless dependency changes are part of the task.

## Validate locally

Keep all four integration opt-ins unset for the local fixture and mock checks. On POSIX systems:

```sh
unset CAM_TEST_POSTGRES_URL CONTEXT_TEST_POSTGRES_URL CAM_TEST_SANDBOX_IMAGE CAM_TEST_TEMPORAL
```

The minimal `dev` setup supports `doctor`, the scripted demo, and this first-clone smoke check of the runtime and mocked native-provider qualification:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q \
  tests/test_engine.py tests/test_provider_qualification.py
.venv/bin/python -m service demo
```

The demo defaults to a fresh `.runtime/demo-*` directory. Expected task outcome: `review_eligible` with review still `pending`. It does not call a paid model or approve the repair.

The full default suite also exercises mocked Temporal SDK behavior and synthetic release-builder paths. Those tests need the SDKs and packaging toolchain installed, even when no integration backend is enabled:

```sh
uv sync --locked --extra dev --extra production
uv pip install 'pip==24.3.1' 'setuptools==84.0.0'
unset CAM_TEST_POSTGRES_URL CONTEXT_TEST_POSTGRES_URL CAM_TEST_SANDBOX_IMAGE CAM_TEST_TEMPORAL
.venv/bin/python scripts/run_local_checks.py --plan
.venv/bin/python scripts/run_local_checks.py
```

The `production` extra installs SDK dependencies; it does not start PostgreSQL, Docker or Temporal, or authorize live model calls. All four integration opt-ins must stay unset for this default validation. The pinned pip/setuptools tools supplement the locked environment for release-builder tests; a later `uv sync` can remove these supplemental packages, so repeat the packaging-tool install after syncing when needed. The `compute` extra is optional and is not required for these checks.

The launcher runs Ruff on the product, tests and scripts, then the full pytest suite. It disables unrelated pytest plugins and writes a fresh summary under ignored `.runtime/checks/`. Its child output is hashed rather than retained; to investigate a failing test, run that test directly in a private terminal and review the output before sharing it. Use the full local checks before proposing a substantial change; record actual passes, skips, platform and source revision. Skips are missing evidence, not passes.

Optional integration checks need separate setup and explicit permission for the selected resources:

| Opt-in | Effect |
| --- | --- |
| `CAM_TEST_POSTGRES_URL` | Real PostgreSQL tests create and remove isolated schemas; use a disposable local database and the `production` extra. |
| `CONTEXT_TEST_POSTGRES_URL` | Separate PostgreSQL opt-in used by the context integration test. |
| `CAM_TEST_SANDBOX_IMAGE` | Real Docker execution; the launcher requires an explicitly selected digest-pinned image and local daemon. |
| `CAM_TEST_TEMPORAL=1` | Real Temporal development-server tests; use the `production` extra. |
| `compute` extra | Enables CPU tensor checks requiring PyTorch/NumPy; unavailable compute checks otherwise skip. This does not authorize GPU execution. |

Registered pytest markers are `postgres`, `docker`, `temporal` and `gpu`. Some integration tests rely on environment-variable skips without the corresponding marker, so marker filtering alone does not disable all external backends. Consult [operations](ops/README.md) and the relevant runbook before opting in. GPU qualification has its own disabled-by-default execution contract; fake GPU tests are not hardware measurements.

## Read before changing code

For people and AI agents:

1. Read [AGENTS.md](AGENTS.md), [current state](context/current-state.md), and [START-HERE.md](START-HERE.md).
2. Check [implementation coverage](capstone/08-implementation-coverage.md) and the [code-reading guide](docs/06-reference-code-reading-guide.md).
3. Select the relevant contract, runbook or learning packet; inspect its actual source and tests. Load other context only as needed.

Before implementing a substantive component, identify its purpose, state/data owners, invariants, source references, failure modes and distinguishing experiment. Preserve authority boundaries: a tool intent is not a completed effect, a verifier receipt is not human approval, and restored context grants no execution authority. Unknown effects and unresolved billing must not be silently retried or erased. Preserve raw provider protocol artifacts through the supported adapter.

Historical instructions and operational approvals recorded in context describe Huy's original workspace. They grant collaborators no live API, spending, GPU rental, arbitrary-repository execution or deployment permissions. Obtain task-specific authorization before those actions. Never commit credentials, account data or private run artifacts.

Learning follows production traces, with no mastery gates: start from an observed artifact, trace the mechanism, predict and deliberately change it, then ship a concrete output. Label AI assistance and separate proposed, reported, measured and demonstrated evidence. Only Huy's own words/actions belong in Huy's evidence fields.

## Keep the snapshot clean

The original workspace's Git repository and history stay local; this repository has its own publication history. Generated runs, databases, virtual environments, wheelhouses, release archives, caches and captured external source are excluded from the shared snapshot. Some historical documents link to excluded artifacts or original machine paths; those links are provenance, not reproducible evidence in this checkout.

Before a commit, inspect both tracked and untracked files:

```sh
git status --short --untracked-files=all
git diff --cached --stat
git diff --cached
git ls-files
git log --oneline --all
```

Confirm that staged paths contain only intended source, fixtures, tests and documentation. Check the repository's `.gitignore` for generated locations, and use `git check-ignore -v PATH` when an artifact should be ignored. Ignore rules do not remove already tracked files. Do not copy the original workspace's `.git`, excluded histories or generated evidence into this repository; do not force-add ignored artifacts.

Keep changes reviewable and scoped. Add a regression check when it proves changed behavior, run checks appropriate to the actual change, and describe the problem, resulting behavior, validation and remaining limitations in the pull request. Do not claim a source test validates a different installed wheel or an unmeasured production environment.
