# Offline release candidate contract — 2026-10-10

Status: **proposed for root freeze before implementation**. Scope is the user-authorized local, unpublished release candidate. Root records this document's SHA-256 before coding; subsequent clarifications must be explicit addenda with their own identities. This document is architecture/specification only. No runtime code is changed by its author.

## Purpose and evidence boundary

Produce a curated current-source archive, installable wheel, local dependency material and executable reproduction instructions. Prove that the installed package outside the checkout executes the existing native mocked repair with real local Docker, clean process restart, exact patch/report replay, and deterministic context offload/retrieval/typed recovery. Prove uncertain dispatches are not resent. This slice changes packaging, release tooling, checks and release documentation; it does not change service/runtime semantics, schema, workload population, verifier/accounting/identity rules or provider authority.

The existing `runs/repair-2026-10-10/dist-http/coding_agent_mastery-0.1.0-py3-none-any.whl` and source archive are historical artifacts predating subsequent current context/recovery work. Preserve them byte-for-byte. Their earlier import check is not current-source acceptance. New artifacts receive a fresh release identity and fresh output directory; version 0.1.0 alone is never an immutable identity.

No inference, account discovery, hosting, publication, dependency downloads, image pulls or sponsor-service contact is authorized. Explicit native MockTransport calls may use the adapter's existing network-enable flag internally but must have no live transport fallback. This is local mechanics evidence, not NVIDIA coding quality, judge access, public-source delivery, production readiness, multi-platform validation or human mastery.

VI: Release phải chạy từ wheel đã cài ở nơi khác, không vô tình import source workspace. Mock chọn hành động; Docker kiểm tra code thật. Kết quả này chưa đạt live sponsor call hay public judge access.

## Owners and immutable identities

| State/data | Owner | Contract |
|---|---|---|
| Source selection and package boundaries | Release builder | Reviewed exact file list; fail closed on unsafe file type, missing selected file or source drift. |
| Runtime source/authority semantics | Existing service modules | Copy exact bytes; never fork controller, verifier, ledger or recovery implementation inside release tooling. |
| Lock and dependency closure | Release builder | Exact `uv.lock` bytes plus selected supported interpreter/platform, closure, wheel hashes and installed distribution versions. No resolution refresh. |
| Build toolchain | Local build environment | Record interpreter, backend/version and local wheel/tool identities separately from runtime closure; a broad build requirement is not a pin. |
| Test fixture inputs | Standalone release smoke runner | Authored deterministic fixtures; native mock only; no private production/user input. Expected answers stay outside candidate workspace. |
| Runtime evidence/private inputs | Existing RuntimeStore/artifact owners | Fresh run directory outside distributable source; existing scope/frontier/Unknown rules unchanged; do not bundle generated private `control-inputs`. |
| Release acceptance | Root integration plus independent reviewer | Record artifact/source/lock hashes and measured checks for exactly those bytes; keep failed/missing evidence explicit. |

Freeze a machine-readable manifest mapping every selected relative POSIX path to SHA-256 and size. Reject duplicate paths, traversal, absolute paths, symlinks (including parent-directory aliases), nonregular files and output-root overlap with selected input. Manifest identities cover product files plus release scripts/docs and metadata. Exclude the manifest's own hash from its internal digest; an outer verification record binds its bytes, source archive, wheel, generated requirements, local wheelhouse inventory and smoke reports. Record a before/after source comparison across staging/build/verification and reject drift. No claimed Git revision exists unless actual Git provenance is separately available; hashes are sufficient here.

## Curated distribution policy

Use an explicitly enumerated file allowlist, frozen before artifact construction. Bounded pattern discovery is permitted only to propose that exact list, not to authorize arbitrary newly appearing files. The final manifest is inspectable and archive members must match it exactly, apart from declared generated metadata.

Allowed owned runtime content is regular source files under `service`, `evals`, `compute` and `workloads`, with required runtime assets selected by reviewed paths: workload manifests, baseline/oracle fixture assets required by the existing authored registry, evidence locks, and the owned repair task/recipe/source. These existing oracle fixtures remain offline test assets and must never enter the supported repair worker source/intake. Their inclusion does not authorize using an oracle to repair a task. Required package assets must be present in the wheel as well as source archive. Do not expand workload population.

Allow `pyproject.toml`, `uv.lock`, product README, product LICENSE/NOTICE, selected standalone release scripts and their own concise operation documentation. Selected release-focused tests may live in the source archive if expressly listed; the installed-package smoke must work without them. Repository-wide learning docs, context, research, references, study, archive, runs, build output, virtualenvs, caches, VCS internals, bytecode, editor files, credentials, `.env*`, private control inputs and unrelated third-party reference copies are excluded. Do not include the entire `ops` tree or learning README implicitly. Include a Docker recipe only if its role and network behavior are accurately documented; the existing `ops/Dockerfile` is a network-install precedent, not the offline provisioning mechanism.

Keep Apache-2.0 candidate terms from the existing unpublished export and its honest contributor NOTICE in the new product distribution, without relicensing third-party material. Place LICENSE/NOTICE in archive and wheel metadata/data in a detectable location. If dependency wheels are bundled, retain their original bytes and license files and provide a dependency inventory with package/version/hash/license metadata where available; unknown or incomplete notices remain explicit. A generic dependency sentence is not evidence that every third-party licensing obligation has been reviewed. This work does not infer legal ownership facts or authorize publication.

## Offline build and dependency provisioning

Select and record the actual local Python minor version, OS and architecture. Support and claim this measured platform only. The runtime requirement remains unchanged; broad Python metadata is not cross-version validation. Use the existing lock as authority, with a bounded base-runtime closure. Optional production/compute/dev extras are not required for repair/context smoke and must not be silently installed or claimed tested. Include optional extra dependencies only when explicitly required by a selected check and bound to the lock.

Generate exact-version, hash-checked requirements from `uv.lock`, resolving only supported unambiguous entries and requested extras. Follow the useful fail-closed closure/hash principle in `ops/Dockerfile`; unsupported version branches or source types must fail rather than select an arbitrary version. All runtime installation must use only explicitly supplied local wheelhouse/cache material, no index and no dependency resolution. Preferred wheelhouse installation verifies exact lock wheel hashes and binary wheels. Root also authorizes uv offline locked installation from the existing local uv cache as a bounded local alternative: use the frozen lock or its exact exported base closure, record uv version, cache location/provenance, platform, installed package versions and content identities. Do not represent extracted uv cache contents as hash-verified original wheel bytes. A cached installed package directory is not a verified original wheel; reconstructed wheels must never claim a lock wheel hash unless their full bytes match it. Cache-backed local reproduction can satisfy A2 when precisely labeled, but does not establish a universally redistributable offline wheelhouse. Missing dependency material under both authorized routes leaves clean-install acceptance pending with exact package/platform detail.

Build from fresh staged curated source, with explicit offline/no-isolation backend invocation or equivalently controlled local build setup. Record the backend and bootstrap tool versions/hashes; provision build requirements locally rather than invoking automatic network build isolation. Build failure returns failure, leaves diagnostic evidence, and never publishes a success manifest or overwrites an earlier candidate. Do not copy the historical wheel or a pre-existing `build/lib` tree. A pure-Python wheel tag does not imply its dependency wheels support every platform.

Installation uses a fresh isolated virtualenv, no system site packages, a fresh work directory outside original checkout/staging, no `PYTHONPATH` injection and isolated interpreter mode where possible. Install wheel plus exact locked dependencies from local files, check declared dependency consistency, then execute real imports. Record distribution version, wheel SHA-256, install root, resolved `__file__` locations and file hashes for all exercised product modules, including context/retrieval/recovery. Assert all product import origins are installed files outside checkout, staging, tests and former exports. Check installed source/asset bytes against wheel and frozen input manifest. An extracted-wheel import, editable install or `sys.path` workaround does not satisfy this gate.

VI: Offline là không tải dependency hay image. Nếu cache thiếu đúng wheel đã khóa, ghi rõ thiếu gì; không thay bằng package đang có rồi gọi đó là clean install. Build tool cũng cần identity riêng.

## Minimal implementation seams

1. A release-builder script, preferably `scripts/build_offline_release.py`, with explicit output and local wheelhouse/cache inputs; owns curated selection, staging, manifest/archive/wheel checks, locked requirement export and install evidence. It calls existing package/build tools and never imports user-supplied candidate code into the supervisor.
2. A standalone smoke script, preferably `release/acceptance/installed_package_acceptance.py`, copied beside the package as a release asset. It contains small synthetic fixture preparation and evidence assertions, imports installed service APIs, and can run with installed Python in isolated mode. It must not import `tests`, use `runpy` against tests, discover checkout roots or rewrite `sys.path`.
3. Product release templates/docs under a narrow new release directory and release-boundary tests under `tests`. A separate helper file is acceptable if explicitly shipped and executable without adding checkout import paths. Prefer one smoke script when that reduces path ambiguity.
4. Existing `python -m service.cli repair-demo` and `repair-report` commands remain the product repair entrypoints. No duplicate runtime or new API surface is needed.

The current `scripts/context_offloading_demo.py` reads `tests/test_context_integration.py` with `runpy` and inserts checkout into `sys.path`; it therefore cannot satisfy installed-package acceptance unchanged. Reuse the authored scenario and assertions as small release fixture orchestration, while all actual projection, admission, retrieval, ledger and restoration behavior remains in installed service modules. Do not move tests into the product runtime merely to make an import succeed.

## Acceptance experiments

| Gate | Required observed evidence | Failure that distinguishes a false pass |
|---|---|---|
| A1 Current artifact | Frozen allowlist and exact source/lock/metadata hashes; wheel/source contents reviewed; prior artifacts unchanged | Stale dist-http payload, omitted context module/data, unexpected private path or drift fails. |
| A2 Offline clean install | Fresh venv outside checkout, local lock-bound closure with explicit wheelhouse-or-uv-cache provenance and build tool identity, import origins and installed byte equivalence | Network dependency attempt, inherited checkout import, missing locked wheel, altered wheel or dependency conflict fails. |
| A3 Installed repair | Existing native mock + already present immutable local Docker Python image; independent verification and review_eligible/pending | Mock transport absent, provider fallback, image pull, recipe missing, incorrect tree/receipt or live-model claim fails. |
| A4 Clean process restart | Separate first and second OS processes at existing committed pause boundary; epochs advance; preserved exact native history, cumulative accounting, five total mock requests in existing authored demo; retired slots | Repeated prior request, unretired slot, forgotten cumulative bound, new task masquerading as resume or unsupported active-case crash recovery fails. |
| A5 Exact patch/report | Independent `git apply` (or equivalently independent standard patch application) to frozen base in a disposable directory reproduces exact candidate tree digest; report reload from committed evidence and unchanged dispatch count | Preview-only diff, stale receipt, replay makes a model call or acceptance displayed as human approved fails. |
| A6 Context + retrieval | Captured native request matches committed accepted request digest; old sentinel absent from offloaded request and retained in raw source; reload yields exact bounded bytes with committed projection provenance and zero-bound retrieval receipt | Merely checking function presence, dropping raw history or unrestricted artifact access fails. |
| A7 Typed recovery | Fresh controller validates typed checkpoint/source prefix/request/config identities, then supported fresh owner derives a new accepted projection chain with checkpoint lineage; restore alone grants no authority | Reusing old owner/chain, skipping validation or synthesizing authority fails. |
| A8 Unknown no resend | Inject mocked lost response after accepted dispatch; record Unknown with unsettled liability; restart/restore refuses and request counter remains unchanged; late billing settlement remains idempotent and effect stays Unknown | Retry after uncertainty, ledger-only recovery authorizes execution, count increments or Unknown disappears fails. |

For A3–A5 use only the already present image inspected by immutable ID. The existing runbook reports local Linux arm64 image `sha256:ce9a404c2c0138e747a43e6ea022d2f7e670ed868df35d627a663ba7fb940ea9`; inspect actual availability before using it, and record observed daemon/image identity. Missing local Docker/image is an explicit blocked measurement, never a simulated pass. Use bounded test-owned resources only. Active-container process-loss recovery remains unsupported; retained/Unknown resources stop the experiment and block replay. Clean pause is the supported case.

Test scripts run with the checkout and `tests` absent from their work directory and import path. Keep raw fixture runtime outputs locally outside release payload; publishable summary candidates contain only bounded synthetic evidence and no inherited environment dump. Zero mock model charges do not imply free infrastructure. Distinguish expected claims from observed results in every record.

## Adversarial checks and delivery

Release-focused tests must exercise forbidden/symlink members, duplicate/traversal archive paths, unexpected allowlist additions, omitted package assets, changed source after manifest/staging, stale wheel bytes, absent/altered local dependency hashes, backend failure, installed-import contamination, accidental tests dependency, and output collision with prior artifacts. Tests may use synthetic source directories and injected failed build commands; label these as builder checks, not real clean-install observations.

Root performs integrated package acceptance once the implementation and independent tests are available; rerun focused checks after review fixes. Run repository lint and relevant packaging/runtime regression checks; avoid unrelated full-suite repetition for prose-only edits. Independent review must inspect actual frozen artifacts, reproduce key installed smoke checks and test the fail-closed boundary. Bind final verification to final source and artifacts after all edits; preserve failures and historical exports. Human mastery and live/hosting/publication gates remain unchanged.

## Inspected authority and references

- `AGENTS.md`; `context/current-state.md` read 2026-10-10.
- `hackathon/02-delivery-and-submission.md`: curated release, license, clean-install and external gates.
- `hackathon/04-execution-specification.md`; `hackathon/05-local-repair-runbook.md`: supported repair semantics, restart/frontier/Unknown and exact report evidence.
- `pyproject.toml`: base/optional dependencies, setuptools discovery/assets, CLI entrypoint; `uv.lock`: immutable closure authority.
- `ops/Dockerfile`; `ops/README.md`: exact-hash closure precedent and bounded local Docker identity.
- `service/repair_demo.py`, `service/recovery.py`, `service/context_retrieval.py`; `tests/test_context_integration.py`: existing runtime seams and distinguishing fixture controls.
- `scripts/context_offloading_demo.py`: checkout/tests dependency requiring standalone release orchestration.
- Existing `runs/repair-2026-10-10/release-source-http/{LICENSE,NOTICE}` and archive inventory: historical licensing candidate/export; preserve unchanged.

No new external research is necessary to freeze this local packaging contract. Current product semantics and authoritative local lock/source supply the required engineering inputs. External rules/account research stays outside this slice.

## Addendum A — verified wheelhouse preparation before offline acceptance

**2026-10-10, frozen before preparation.** Actual cache-only installation failed for the locked SQLAlchemy 2.1.4 platform wheel; see `runs/offline-release-2026-10-10/builder/cache-preflight-install.json`. The user authorized an offline release candidate and keeps paid execution disabled; the user did not prohibit free dependency acquisition. Root chooses exact upstream hash verification instead of disabling dependency hash checks or repacking an installed environment.

This addendum supersedes the earlier prohibition on dependency downloads **only for a separate preparatory wheelhouse acquisition step**. Fetch only the exact base-runtime binary wheels selected from the existing lock for the measured Python/OS/architecture. Sources are unauthenticated public PyPI and `files.pythonhosted.org`; require original SHA-256 hashes from `uv.lock`, reject unsupported sources, missing/ambiguous versions and source distributions. No credential/account discovery, provider calls, model execution, hosting, image pulls, package script execution or publication is authorized by this step. Preserve upstream wheel bytes and license files; record package/version/filename/URL/hash, acquisition outcome and available license metadata. Never use `--no-verify-hashes` as a substitute.

Dependency acquisition is online preparation and must be labeled as such. Subsequent source build, fresh isolated installation (`--no-index`, local wheelhouse, exact hash-checked closure, no dependency resolution) and installed-package acceptance remain offline. The measured candidate is platform-specific and does not claim every supported Python/platform or complete legal review. Keep prior failed cache checks and historical release artifacts. Build-tool identities remain separately recorded under the original contract. Paid execution stays disabled.

**VI:** Offline acceptance nghĩa là bản đã chuẩn bị cài và chạy từ artifact cục bộ. Lần chuẩn bị wheelhouse này có tải public dependency; record phải nói rõ, không gọi toàn bộ quá trình là không dùng mạng. Hash trong lock vẫn là điều kiện bắt buộc.
