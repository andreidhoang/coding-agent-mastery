# Current readiness candidate: installed acceptance addendum

Date **2026-10-11**. **FROZEN before acceptance implementation.** Extend the existing [offline release contract](offline-release-spec-2026-10-10.md) to a new candidate containing the final reviewed readiness source. Preserve the entire October10 candidate, archive, wheel, manifests and installed results. Reuse the builder and its exact allowlist/source/hash checks; no deployment or publication follows.

## Scope and dependencies

Freeze/build only after skills recovery, configured offline serving, trusted GPU planning and environment-journal integration are stable. The base wheel includes their Python modules and authored skills assets. Optional PyTorch/CUDA dependencies remain outside the base-runtime installed claim. A GPU `not_run` plan must work without PyTorch; actual CUDA remains pending.

Extend the existing standalone `release/acceptance/installed_package_acceptance.py`, using installed product APIs only. No checkout tests, demos, `runpy`, source path injection or source-tree imports. The existing repair/context/Unknown controls remain. Add:

1. Capture the installed authored skill, accepted scripted/native mocked load, typed post-turn checkpoint, store/artifact-reader reopen, new owner continuation/resource read and original primary provenance. Denied same-response access and changed immutable source must remain distinguishable. No real provider traffic.
2. Instantiate the configured offline service with explicit in-memory synthetic credentials and new outside-checkout runtime root. Exercise its actual child, authenticated API/catalog, durable task completion, duplicate behavior and clean restart. Validate worker source origins through the installed interpreter/package; parent product origins alone are insufficient. Separate real loopback HTTP evidence may be retained by independent serving review, while installed acceptance can use ASGI transport plus the actual worker process.
3. Run the trusted GPU planner with execution disabled. Assert `not_run`, no Torch dependency requirement and no child/GPU work. Validate installed module paths and source identities against the manifest; absent `uv.lock` in site-packages must be represented honestly.
4. Exercise environment journal write-ahead/bounded reconciliation using installed code and the already-local cached Docker image. At minimum prove one real supported verifier path creates per-instance journal records and releases only proven terminal environments; retain exact immutable IDs/daemon observations. Stronger process-loss controls remain in independent source evidence, not inferred from a normal run.

All product-loaded files must originate in the fresh outside-checkout venv and match manifest bytes. Run from a separate empty directory under Python `-I`, with system site packages disabled, network denial for provider connections and no source imports. Child processes use the same installed interpreter. Existing local Docker is explicit; no image pull or hardware provisioning. Retain initial failures and repaired reruns.

## Dependency preparation and reproducibility

Reuse the18 original locked wheels acquired for October10, verifying them against current lock. The current base closure additionally requires the already locked PyYAML6.0.3 wheel. If its original wheel is absent locally, obtain only the matching public binary from its exact `uv.lock` URL, verify its size and SHA256, and record this as **online dependency preparation**. This is not a paid provider call. No lock change, version resolution or index access during build/install/acceptance. Stage wheels in the new run, leaving old material untouched.

Freeze the current exact manifest before build. Use fresh output/install directories, existing offline builder/install verification and independent acceptance. Record source identities before/after, installed origins, all artifact identities, actual operating system/Python/daemon/image and skipped optional backends. Rebuilding the curated archive must preserve selected bytes; a full new byte-reproducibility study is optional only if the packaging implementation stays unchanged and no stronger claim is made.

## Result boundary

Passing this gate establishes an installed local reference on this machine, with mocked inference and the selected local Docker profile. It does not establish hosted production, arbitrary repositories, GPU isolation/performance, a live-model score, public hackathon judge access or human mastery. Paid execution remains disabled.

**VI:** Test source đúng chưa chứng minh wheel đúng. Ta cài vào venv mới, chạy module thật từ site-packages và kiểm tra từng hash. Số lần agent test không thay thế bằng chứng model/GPU/production còn thiếu.
