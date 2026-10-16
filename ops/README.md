# Local operation of the reference

Updated: **2026-10-11**. Prior production repairs/evidence: [production code review](../research/production-code-review-2026-10-09.md) and [verification record](../research/production-review-verification-2026-10-09.json).

These files prepare bounded local operation. They do not launch a service automatically or establish production readiness. The implementation uses one authority/API/workflow contract across SQLite trusted fixtures and deployment-target adapters. See [service operation](runbooks/service.md) and [checkpoint/restore recovery](runbooks/recovery.md). Human mastery remains separate from AI implementation and test evidence.

**VI:** Ops package giúp chạy và kiểm tra đúng phạm vi: fixture local, database local hoặc adapter được chọn rõ. Không có secret mặc định hay workflow tự chạy lên cloud; mỗi integration cần cấu hình và evidence riêng.

From the repository root, inspect the validation plan and run the local checks using the locked environment:

```sh
.venv/bin/python scripts/run_local_checks.py --plan
.venv/bin/python scripts/run_local_checks.py
```

The checker invokes full repository Ruff and pytest checks. It records package versions, configured-integration booleans, exit statuses, durations and summary counts in a new `.runtime/checks/check-<id>.json`; an existing report is never overwritten. It captures then discards raw subprocess output because a traceback may include private database details. Reports contain no connection URLs, token values or environment dump. A failed check returns a nonzero status. To investigate a failure, rerun the named check locally where its output can be handled privately.

Optional integrations use explicit environment settings already honored by the tests:

```sh
CAM_TEST_TEMPORAL=1 .venv/bin/python scripts/run_local_checks.py
CAM_TEST_SANDBOX_IMAGE=python@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f .venv/bin/python scripts/run_local_checks.py
```

Temporal opt-in starts a local SDK dev server and may download its CLI; it does not use a hosted cluster. Docker opt-in requires a local daemon and the explicit pinned Python image. The checker does not pull images, start a database or deploy an API itself. Integration tests own only their disposable schema, server and named containers. POSIX timeout/interruption cleanup monitors the checker-created group independently of leader exit, then escalates `SIGTERM` to `SIGKILL` within a bound. This is launcher cleanup, not containment of children escaping the group; Windows covers the direct process only. Uncertain Docker/DB resources require inspection of their test-owned identities. Never use a broad container/process stop or deletion to clean up this project.

Fresh authority stores now use schema 2. Existing schema 1 stores fail closed until the [explicit offline migration](../service/migrations/002_identity-and-writer-protocol.md) is run with stopped writers, a verified backup and disposable-copy validation. The migration's SQL writer guard supplements quiescence; it does not authorize rolling upgrade or isolate privileged SQL users. Do not use normal service startup as an upgrade command.

**VI:** Leader đã chết không chứng minh child đã dừng, nên cleanup nhìn cả group của checker. Tương tự, schema version đã đổi không chứng minh writer cũ đã bị cắt quyền ở mọi boundary; migration cần quiescence và backup thật, không chỉ một flag.

The Compose file contains **only one PostgreSQL database**, using the local-inspected image digest `postgres@sha256:029660641a0cfc575b14f336ba448fb8a75fd595d42e1fa316b9fb4378742297`, corresponding to `postgres:16.10-alpine` on 2026-10-08. It binds host port 15432 to `127.0.0.1`, uses temporary memory-backed data, and has `pull_policy: never`. No application, worker, Temporal cluster or credential-bearing service is included. Its `disposable-dev` profile deliberately uses PostgreSQL trust authentication: any process reaching that local port can access this synthetic test database. Use it only on a private development machine, never as production or on a shared host containing sensitive data. No data in it is durable; stopping the database discards its contents.

Choose an unused port if necessary with `CAM_POSTGRES_PORT`. Use a fresh project identity so cleanup cannot affect another run:

```sh
CAM_OPS_PROJECT="cam-reference-$(.venv/bin/python -c 'import uuid; print(uuid.uuid4().hex[:12])')"
docker compose -p "$CAM_OPS_PROJECT" -f ops/compose.yaml --profile disposable-dev up -d --wait
CAM_TEST_POSTGRES_URL=postgresql+psycopg://cam_dev@127.0.0.1:15432/cam_test .venv/bin/python scripts/run_local_checks.py
docker compose -p "$CAM_OPS_PROJECT" -f ops/compose.yaml --profile disposable-dev down
```

The PostgreSQL tests create a fresh UUID-named schema and drop only that schema afterward. The checker requires a loopback PostgreSQL URL without query overrides. If you changed the host port, update the URL to match. The database image must already be present at the pinned digest; explicitly obtain it before this command if it is absent. This delivery inspected and validated the Compose source; it did not start another database from this file.

**VI:** `trust` ở đây là lựa chọn dev có chủ ý, không phải password thật được hardcode. Project name riêng và schema UUID giúp cleanup đúng tài nguyên của lần chạy. Database tmpfs cố ý mất data khi dừng nên không được dùng làm nơi lưu evidence duy nhất.

`ops/Dockerfile` was built for **Linux arm64** on 2026-10-08 as `cam-reference:2026-10-08`, image ID `sha256:baff9ee063f6019bfc9293bf09dbf04caf330079651afc440d076da943a16337`. It uses the pinned Python digest above, extracts the base + production dependency closure from `uv.lock`, installs exact versions with locked wheel hashes, `--no-deps`, `--require-hashes` and binary wheels only, and copies explicit source folders. It omits compute/GPU extras. Conditional dependencies are installed as a locked superset; an ambiguous version branch fails the build. The measured build validates this image/architecture; other platforms and future package availability require their own check.

```sh
docker build --pull=false -f ops/Dockerfile -t cam-reference:2026-10-09 .
```

The recipe runs as an unprivileged numeric UID. Its default command serves the existing `create_app` factory on container loopback without a configured authority store or bearer principals, so protected routes return `503 api_unconfigured`. It publishes no port, starts no worker and contains no credential configuration. A configured API requires trusted bootstrap code with explicit store, artifact namespace, token-to-principal grants and operating limits described in the service runbook. The historical 2026-10-08 package smoke under disabled network, a read-only root, non-root UID and dropped capabilities validated all 42 workload definitions and 82 frozen assets, and observed `503 api_unconfigured` for protected `/tasks/example` through TestClient. The [dated delivery record](../research/reference-delivery-verification-2026-10-08.json) preserves that image/source identity; the build command above rebuilds current source under a new tag. Those dated package/test identities belong to the [2026-10-09 verification record](../research/production-review-verification-2026-10-09.json). Package/ASGI smoke is not a deployed HTTP lifecycle, configured service or SLO result. Candidate Linux-supervisor evidence remains separate from the application image.

Production promotion still needs a declared identity/secret lifecycle, transport configuration, persisted database/Temporal/artifact backups, actual restore, review access, SLO/load/canary evidence and a separately bounded threat model. Local integration passes cannot stand in for those measurements.

The audited checkout was rebuilt on **2026-10-09** as `cam-reference:2026-10-09`, image ID `sha256:047761aadd606c58d04f85acb421dc1b7f27d65f24682a9c9531472de4381dc8` (Linux arm64). Its nonroot/read-only/no-network smoke returned503 for an unconfigured protected route and validated all42 workloads/82 assets. Packaged Python hashes match the tested source. The dated [verification record](../research/production-review-verification-2026-10-09.json) owns those historical artifact identities; no hosted API was deployed.

## Current offline release candidate

[Release index](../releases/README.md), [frozen contract](../research/offline-release-spec-2026-10-10.md), [operation guide](../release/OFFLINE.md) and [verification](../research/offline-release-verification-2026-10-10.json) own the October10 packaging evidence. A reviewed exact allowlist staged the frozen October10 bytes, then built without network isolation provisioning. Installation uses a fresh outside-checkout venv, original local locked wheels, `--offline --no-index --require-hashes --no-deps --no-build`, and checks exact origins/content. The public wheel-acquisition preparation phase is separately recorded as online.

Two separate installed acceptance runs on macOS arm64/Python3.12.11 passed with native mocks and the already-local Linux arm64 Docker image. The independent reviewer also rebuilt from the extracted curated archive. This is a base-runtime installed check; optional production/compute extras, fresh-machine deployment, database backup/restore, rolling compatibility, hosted service, public release and GPU performance remain pending. Paid execution stays disabled. The existing network-install Dockerfile remains its own operating recipe, not the offline provisioning path.

## Current configured profiles — 2026-10-11

Use [the offline-service runbook](runbooks/offline-service.md) for strict configuration, explicit bearer principals, literal loopback, persisted pending caps and the actual serial child lifecycle. This profile uses authored scripted fixtures and SQLite/local artifacts. It rejects dirty/Unknown startup; the old default unconfigured image remains historical. No hosted live repair service or operated SLO is implied.

Use [environment reconciliation](runbooks/environment-reconciliation.md) for explicitly journaled actual verifier paths. Persist nonce before creation; verify original daemon/image/policy/immutable ID; reconcile one reservation. Unbound zero-match creation remains unresolved and cannot release a slot. Cleanup does not settle bills or authorize replay. Follow [typed skills recovery](../research/skills-recovery-spec-2026-10-11.md) for exact post-turn checkpoints and fresh-owner continuation, separately from physical cleanup.

Use [trusted GPU preparation](runbooks/trusted-gpu-probe.md) for the disabled-by-default authored RMSNorm qualification probe. Actual CUDA and generated-code isolation are pending. [The current readiness evidence](../research/system-readiness-plan-2026-10-11.md) and [release index](../releases/README.md) supersede older current-source wording above; historical images/results keep their own identities. Paid execution remains disabled.

**VI:** Chọn đúng profile trước khi đọc kết quả: fixture HTTP không dùng Docker; repair verifier có thể opt in journal; GPU probe chỉ đo code authored và không cấp runtime authority.

Use [offline provider qualification](runbooks/provider-qualification.md) to bind native mock protocol evidence to one exact unstarted repair before any later authorized conformance trial. The installed rc4 commands cannot enable network inference. Corruption, source/task drift, interrupted starts and Unknown all fail closed; reports/handoffs are evidence, not authority.
