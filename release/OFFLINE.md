# Offline candidate operation

Run the builder with the recorded Python toolchain (currently Python3.12.11,
setuptools84.0.0, pip24.3.1). Preserve the original lock and historical candidates.
Use absolute paths for the source, manifest, output and installed work directories.
The installed work directory must be outside the checkout and build staging.

1. `python scripts/build_offline_release.py --source-root SOURCE freeze --manifest MANIFEST`
2. Inspect MANIFEST's exact target paths, origins, byte counts and SHA-256 values.
3. `python scripts/build_offline_release.py --source-root SOURCE build --manifest MANIFEST --output NEW_CANDIDATE`
4. `python scripts/build_offline_release.py --source-root SOURCE install --candidate NEW_CANDIDATE --install-root OUTSIDE_WORK --uv UV_BINARY --wheelhouse LOCAL_WHEELHOUSE`

The freeze phase constructs no source archive or wheel. Build checks the exact list
and bytes before staging and again after the controlled offline backend finishes.
Every output must be new; failure keeps diagnostics and does not issue success
evidence. `source.tar.gz` has exactly the selected files plus its declared generated
`META/frozen-manifest.json`; archive permissions and timestamps are fixed.
LICENSE/NOTICE and product README are copied from narrow release templates to the
archive root, while the templates remain included for source reproduction.

Cache installation uses uv `--offline --require-hashes --no-deps --no-build`, an
explicit cache and exact base lock requirements. Offline cache lookup uses cached
registry metadata; no network is permitted. Unpacked cache contents are not original
wheel bytes. Missing hash-capable cache material fails with explicit diagnostics.
The local cache was insufficient for the measured fresh hash-checked installation.
Frozen Addendum A therefore authorizes a separate preparation phase to acquire only
the exact public binary base wheels, checking their original lock hashes and sizes.
That preparation is online and recorded separately; every later build, installation
and acceptance operation is offline. The original lock is unchanged.

For original local binary wheels, use `--wheelhouse LOCAL_WHEELHOUSE`. The
builder rejects unlisted, modified or incompatible wheel material and installs with
no index, dependency resolution or source build. This route retains wheel byte
hashes from the lock. No dependencies are downloaded during offline operations,
reconstructed or relicensed.

Installation creates an isolated venv without system site packages or pip bootstrap.
It checks dependency consistency, exact installed distribution versions, import
origins and byte equality for every shipped product source/asset. Evidence also
records toolchain, lock, source/archive/wheel and dependency content identities.

After installation, run the standalone shipped acceptance script using the emitted
installed Python path with `-I`. Pass a fresh `--output`, the inspected immutable
`--sandbox-image`, `--source-manifest MANIFEST`, and `--forbidden-root SOURCE` (repeat
for staging and historical exports). The image must already be local; never pull
it. Runtime evidence stays outside the source archive. The only repaired task is
the authored deterministic function fixture. Clean committed pause/restart is
supported. Explicit journaled local-Docker profiles additionally persist per-instance
identity before creation and support bounded one-reservation cleanup after process
loss. Only a verified immutable container identity can be removed; an unresolved
zero-match creation remains retained because a delayed create can still arrive.
Cleanup never resends Unknown work, settles billing, grants a new owner or proves
verification success. Legacy unjournaled reservations are not adopted automatically.

The configured service entry point is `python -m service.offline_server serve --config PATH`.
It accepts only the closed `offline_fixture_v1` profile, literal loopback binding,
SQLite/local artifacts, exact authored task catalog and explicit synthetic or operator
token environment mapping. It refuses dirty or Unknown startup frontiers; readiness
does not claim operated production. The standalone acceptance records its exact
configuration and observes the installed child through a declared test wrapper.
Independent unmodified loopback HTTP evidence is maintained outside this archive.

The compute entry point `python -m compute.rmsnorm_cuda --config PATH` emits a disabled `not_run`
qualification plan without importing PyTorch. Actual execution requires the explicit
frozen trusted-probe configuration and a dedicated supported NVIDIA GPU. The base
install excludes PyTorch/CUDA. This authored probe neither executes generated kernels
nor establishes a GPU sandbox, live-model quality or production performance.

The measured platform is recorded in the manifest and installation evidence.
Pure Python product tagging does not establish cross-platform dependency support.
Source packaging retains optional compute modules as unexecuted reference code.
Human acceptance and public/sponsor/hosting gates remain separate.

## Offline provider qualification

Prepare a repair with the existing `repair-prepare` command and an explicit public
provider approval. Then use the same installed `agent-lab` entry point:

1. `qualification-prepare --output NEW_QUALIFICATION --repair-output PREPARED_REPAIR --execution-deadline UNIX --review-deadline UNIX`
2. `qualification-run --output NEW_QUALIFICATION`
3. `qualification-report --output NEW_QUALIFICATION`
4. `qualification-handoff --output NEW_QUALIFICATION --repair-output PREPARED_REPAIR`

Deadlines are explicit finite Unix seconds, with review later than execution; the
execution deadline must be in the future at preparation. The repair must remain
unstarted under its existing runtime representation. Preparation/handoff may inspect
the already-local immutable image to check its identity; they execute no candidate.
The probe always uses internally isolated native mock transport. These commands
have no network-enablement flag and ignore provider credentials in the environment.

The qualification manifest binds exact service source bytes, supplied approval and
one prepared repair snapshot. Immutable requests, raw replies, broker results and
accounting establish the local two-request continuation check. Synthetic ledger
amounts are separate from payments. A failed or interrupted probe cannot retry a
possibly executed request. Retain its evidence and use report inspection; do not
delete its start marker to force a resend.

A successful handoff is advisory and valid only for the checked snapshot; it does
not lock the task or grant execution authority. Live account/catalog, current
pricing, actual sponsor conformance and useful live repair remain unobserved. A
source/configuration/task change requires new preparation, not relabeling old
results. Paid/live execution and public publication remain disabled.
