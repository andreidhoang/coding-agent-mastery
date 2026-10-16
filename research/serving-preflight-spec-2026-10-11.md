# Bounded configured offline serving: specification before implementation

Prepared **2026-10-11**. **FROZEN before implementation.** AI-authored architecture contract reviewed by the integration owner. This specifies an actual local HTTP service plus atomic admission limits, not a production-readiness scoring document. No source implementation is claimed by this document. The [serving audit](serving-readiness-audit-2026-10-11.md) owns the pre-change observations. Skills recovery proceeds in its own lane; this slice must not alter its acceptance/checkpoint semantics.

## Purpose and boundary

Make the existing API, durable store, outbox dispatcher and scripted reference runner operate together under a small explicit local envelope. A caller can submit a registered frozen fixture through authenticated HTTP, follow its durable task/events/artifacts, receive review eligibility, restart the service at a clean boundary and retrieve the same task. Overload is rejected atomically. Startup and readiness distinguish an available HTTP process from a functioning configured worker.

**VI:** Mục tiêu là nối các phần đã có thành một service chạy được và từ chối đúng lúc. Scripted fixture chỉ kiểm tra cơ chế phục vụ; kết quả đó không đo khả năng sửa code của model thật.

The only executable mode in this slice is `offline_fixture_v1`: local SQLite, local artifacts, existing `ReferenceEngine`, existing `FixtureVerifier`, the existing immutable workload registry, one service process identity and one serial task runner. Default two-worker fixture semantics stay unchanged inside the runner. Bind only literal loopback addresses; no provider constructor, GPU, Docker provisioning, remote database, arbitrary uploaded source, arbitrary command, public exposure or paid path. Optional integrations retain their prior contracts and are not silently selected.

Reuse `service.api.create_app`, `RuntimeStore`, `LocalOutboxDispatcher`, `ReferenceEngine` and the current evaluator. A new `service.offline_server` module invoked as `python -m service.offline_server ...` avoids changing the shared CLI. A small optional API submission-policy/readiness injection is permitted, defaulting to existing behavior. This is one composition root, not another runtime or evaluator.

## Owners and interfaces

| Object | Owner | Interface/invariant |
|---|---|---|
| Admission policy | Existing authority guard, under `_tx` | Count/check/insert in the transaction that owns submission; never an API-memory counter |
| Frozen serving config | Trusted local operator file | Strict bounded JSON; unknown keys and unsupported modes reject; no repository code/config import |
| Principals and tokens | Trusted parent process | Existing `Principal` validation; explicit environment-supplied tokens, no default/generated public credential |
| Fixture contracts | Composition root + immutable workload registry | Exact model/base/requirements/grader/environment/capability/resource identity validated before durable admission |
| Durable tasks/receipts/Unknown | Existing `RuntimeStore` | No alternate status, queue, settlement or checkpoint store |
| Runner lifecycle | Composition root | Exactly one dispatcher for the root; existing runner checks all effect authority |
| Readiness | Read-only bounded probes + runner supervisor | No user-supplied readiness assertions; no admission, settlement, retirement or restore mutation |
| Artifact probe | Existing scoped artifact store | Byte/digest identity checked; no candidate content or credential returned by health |

**VI:** API được phép nhận ý định; database mới quyết định ý định nào được nhận. Readiness chỉ quan sát điều kiện chạy, không có quyền đổi Unknown thành success hay giải phóng sandbox.

## S-01: opt-in atomic pending-task limits

Add an optional immutable admission policy to `RuntimeStore` construction, with exactly `{schema:1, service_pending_limit, tenant_pending_limit}`. Limits are strict integers (booleans rejected), `1..10000`, and tenant limit cannot exceed service limit. Freeze and digest the validated policy. The policy belongs to the persisted authority record, using existing schema 2 and the existing transaction guard; no new authority table, schema migration or production default is introduced.

Fresh stores created with the explicit policy persist it. Existing stores without it retain current semantics when no policy is requested; do not silently install a policy into historical stores. A requested policy against an existing policy-less store rejects with a structured configuration error. Explicit changed-policy reopen rejects. Callers omitting a policy on an already configured store must still obey its persisted policy inside `submit`; omission cannot disable caps. The serving composition root additionally verifies effective persisted physical/budget limits against its declared values because current constructor arguments do not overwrite existing limits. No policy mutation endpoint is added.

The minimal policy protects **current-code writers under the declared single-owner deployment**. Schema-2 compatibility alone does not stop an old schema-2 binary that predates this policy from writing directly. Mixed-version writers and rolling upgrades are unsupported; startup/runbook require exclusive ownership of the serving root and no legacy writer attached to it. Do not claim a database trigger enforces this new policy unless one is independently designed/tested.

Submission order under the existing `_tx`:

1. Validate tenant/key and canonicalize the original request as today.
2. Resolve existing tenant/key. Identical payload returns the prior task even if full, drained or now expired. Changed payload conflicts without new rows.
3. Check current incarnation, admission/quarantine and contract/deadline as today.
4. Count tasks whose `execution_state` is `queued` or `running`, globally and for that tenant. These exact states are the current executable population. Expired-but-unreconciled tasks still count; elapsed time alone does not delete intent.
5. If either count is at its cap, raise existing `CapacityExceeded`; add no task, submission, event or outbox row.
6. Commit task/submission/event/start command normally. The count and writes share the service guard lock.

`cancelled`, `failed` and `review_eligible` tasks release this logical admission capacity through their existing transitions. Their unretired physical environments and unsettled charges remain in the independent existing ledgers. Terminal rows/history are retained. This policy bounds concurrent accepted work, not lifetime storage growth or tenant fairness.

**VI:** Với cap2: A và B được nhận; C bị từ chối. Retry đúng key A vẫn trả A. Cancel A mở một chỗ trong queue, nhưng nếu sandbox A chưa được xác nhận dừng thì physical slot của A vẫn bị giữ. Hai giới hạn này không được gộp thành một counter.

## S-02: strict configured local composition root

Use one bounded, versioned config with mode, absolute runtime root, literal loopback host/port, explicit physical/budget limits, admission policy, finite worker polling/shutdown bounds, explicit principal grants/token environment-variable names, and an allowlist of frozen fixture contracts. Exact field names may be selected in implementation and frozen before tests; no arbitrary import path, command, URL or provider option is allowed. Reject unknown fields, nonfinite values, duplicate JSON keys, booleans masquerading as integers, oversized input, duplicate/colliding principal/token entries, unsafe root types/symlink replacement and non-loopback binds. Credentials never enter saved config, reports or child fixture environments.

Acquire an exclusive OS lock tied to the resolved root for the lifetime of the service. POSIX local filesystems are the supported lock envelope; fail clearly where that guarantee is unavailable. Two service processes targeting the same root cannot both start. Make root/config identity explicit; a reused root cannot silently switch artifact namespace, workload contract or operating policy. Do not derive trusted startup configuration from candidate/repository files.

Fixture contracts must be canonical and immutable across an HTTP retry. Reuse registry loading/asset validation and the exact checks in `ReferenceEngine.run_task`; extract a pure shared fixture-contract builder if useful. Do **not** call `submit_fixture` again on every HTTP retry: its `time.time()+...` deadlines change the request digest. Either expose a prepared immutable contract catalog with explicit absolute deadlines or accept a stable selection mapped to a durably frozen contract. The smaller preferred implementation is an operator-prepared catalog of exact contracts plus the existing `{key, contract}` HTTP body. A same-key lookup must not generate a fresh deadline or silently rewrite any contract field.

The configured API must reject every submission outside this exact catalog before calling `store.submit`. Preferred optional API hook: trusted `contract_admission(principal, contract)`, which validates exact catalog equality and returns `None` or raises a bounded API error. It performs no mutation or current-time revalidation; an identical prior request can still resolve after its deadline through the store's existing retry ordering. Matching only `repo_id` is insufficient: changed model, base, grader, environment, requirements, capabilities, budget, deadlines, graph/attempt caps or profile can create work the runner cannot honor. Repository/profile grants still apply through the existing API. An optional authenticated catalog read is acceptable; it must expose only granted contracts and no oracle/private recipe. There is no automatic reviewer: final state stays `review_eligible` with human review pending.

Startup sequence: validate pure config/registry first → exclusive root lock → construct scoped local artifacts/store → compare effective persisted policy/limits/config identity → validate supported saved-state frontier → verify a declared scoped artifact sentinel by exact bytes/digest → create existing API and runner → start worker → publish ready. Any partial startup error closes owned resources and releases the lock only after its worker is stopped. It must not overwrite an existing store or silently repair policy drift.

**VI:** Một repo đúng tên nhưng grader khác vẫn là task khác. Catalog cố định giúp API từ chối ngay, thay vì nhận202 rồi để worker mắc kẹt mãi. Deadline cũng là một phần payload nên retry không được tự cộng lại600 giây.

## S-03: runner lifecycle, restart and stop

Run only the existing `LocalOutboxDispatcher` with existing `ReferenceEngine.run_task`, serially, one start task at a time and bounded polling/pages. Before starting, ensure every pending task belongs to the frozen serving catalog. Terminal tasks and genuinely unstarted queued tasks are restartable. A saved `running` task, unfinished dispatch, retained physical environment, policy/incarnation conflict or any unclassified partially executed frontier blocks automatic execution. Keep the original rows and expose a structured `reconciliation_required` result. No fresh ownership, cleanup evidence, billing settlement or replay is invented by this slice.

Prefer a supervised child process for the synchronous dispatcher so the parent can enforce a bounded shutdown without pretending Python thread cancellation stops a running task. The child receives only non-secret runner configuration; do not pass bearer tokens or provider environment. If using another arrangement, its acceptance evidence must prove the same stop and no-concurrent-dispatch properties. Parent observes worker startup/liveness/failure and the current task identity. A runner exception retains the pending outbox entry as today; do not spin repeatedly through an unchanged unsafe frontier. Surface the failure and stop readiness/new admission through the declared supervisor behavior.

On graceful stop: remove readiness, stop new admission, stop taking new starts, allow the current bounded task to finish within the configured drain bound, then close owned worker/store and release the lock. If owned-process termination is necessary, confirm its exit; preserve all unfinished durable records and reserved capacity. A killed process is not a successful task and cannot fabricate retirement receipts. The next startup refuses unresolved active work. A clean completed-task restart can reopen admission only after all normal preflight checks. Arbitrary process-loss recovery, backup restore and active-run migration are separate required production slices.

Cancellation continues through the existing authenticated API and store fencing. Do not install a no-op `stop_task` callback: its success would falsely acknowledge cleanup. In this frozen no-external-sandbox mode, normal runner cleanup supplies its existing trusted-fixture retirement observations; any unresolved stop command stays visible. No broad process/container cleanup is permitted.

## S-04: readiness from actual conditions

Preserve `/health` compatibility as existing lightweight liveness/info; add `/ready` using an optional trusted read-only readiness callback for the configured composition root. HTTP200 means **ready for the declared offline fixture mode** only. HTTP503 carries bounded reason codes for: startup incomplete, config/policy mismatch, store/schema unavailable, stale incarnation/quarantine/admission disabled, artifact sentinel missing/corrupt, registry identity failure, worker absent/failed/stopping, or startup reconciliation required. Queue-full is ordinary backpressure: report it separately and return429 on a new admission; it need not make a healthy service unready. A busy but supervised worker is alive without pretending it has completed its task.

Readiness returns mode, config/policy identity, observed worker state and bounded component statuses; it always retains `production_readiness: unmeasured` and `live_inference: disabled`. Avoid tokens, environment dumps, connection strings, filesystem contents, private code, prompts and tracebacks. Probes must have finite time/size bounds. Read only the declared sentinel; do not write arbitrary files or create tasks from a health request. Startup can create the sentinel in its dedicated scoped namespace; later probes verify it rather than trusting a Boolean in config.

## S-05: acceptance experiments before claiming this slice delivered

| Control | Required distinguishing observation |
|---|---|
| Default compatibility | Existing callers without policy retain existing behavior and current unit suite passes |
| Atomic cap race | Independent store connections race for last service/tenant slot; exactly one new admission commits; loser adds no rows/events/outbox |
| Retry at capacity | Same tenant/key/body returns same ID; changed body409; no duplicate effect or event |
| Two tenants | Tenant cap excludes only that tenant; service cap includes both; cancellation frees admission but retains unresolved physical/billing accounting |
| Reopen/config drift | Exact policy/limits reopen; changed or absent required policy fails; omission by another current-code writer cannot bypass stored cap |
| Catalog adversary | Same repo with altered grader/model/deadline/capability rejects before durable submission; unknown fixture rejected; valid same-body retry remains stable |
| Root/credential controls | Non-loopback, symlink/unsafe root, duplicate owner, malformed config and missing credential reject without running worker or exposing secret |
| Real HTTP lifecycle | Own fresh process/loopback port: unauthorized401 → allowed202 → durable ID/events → existing runner → review eligibility/artifact → clean shutdown → restart/lookup same ID |
| Dependency/readiness faults | Store failure, sentinel damage, worker exit, quarantine/drain and mismatched incarnation independently give503; process still serves liveness where possible |
| Backpressure | Worker deliberately paused; fill cap; excess429; same-key202; release work and observe capacity return without dropping assigned tasks |
| Crash frontier | Kill owned worker after durable start/intent; restart refuses replay, preserves task/Unknown/slot/cost; no fabricated recovery success |
| Network/authority absence | No provider constructor/send, no arbitrary command/import, no API authority mutator, no automatic reviewer, no schema-version change |
| Installed source | New module imports/runs from a fresh installed candidate; historical October10 release remains byte-preserved |

The integration owner records source identities and actual check counts. Use an independent adversarial review after implementation; mutations should remove the atomic cap, ignore policy drift or bypass catalog matching and be rejected by the controls. Do not add prior overlapping test counts. No hardware test is needed for S-01–S-05. Successful delivery enables local service integration experiments, not a production claim.

**VI:** Thí nghiệm quyết định là hai process cùng xin chỗ cuối: nếu cả hai đều nhận202 thì counter nằm sai boundary. HTTP smoke cũng phải đi qua process thật và worker thật; gọi trực tiếp hàm Python không đo được startup/shutdown của service.

## Follow-on required work, without making this slice an empty checklist

This slice closes actual configured-local-serving and pending-admission gaps. Restricted external production still requires a selected supported live repair API contract, explicit provider/account/rate/budget authorization, physical-instance journaling and interrupted-run reconciliation, deployment identity/transport/secret lifecycle, persisted backup/restore with fresh incarnation, storage retention, admission fairness/load/SLO/rollback evidence and a threat model supported by isolation tests. Hardware gates remain separately attached to the GPU slice. These requirements are not made optional by passing local fixture serving.

Current public grounding: [Anthropic Managed Agents, Apr08 2026](https://www.anthropic.com/engineering/managed-agents) supports separating session persistence, harness and sandbox interfaces; [containment engineering, May25 2026](https://www.anthropic.com/engineering/how-we-contain-claude) supports credential exclusion and explicit deterministic boundaries. They motivate this decomposition; they neither validate this code nor reveal unreported private implementations.


## Root-selected interfaces and configuration at freeze

Use `service/serving_config.py` for pure config/catalog validation and `service/offline_server.py` for lifecycle/CLI. `RuntimeStore(..., admission_policy=None)` implements S-01. Add optional `create_app` keyword hooks `contract_admission`, `contract_catalog`, `readiness` and `lifespan`; defaults preserve existing behavior. Submission hook `(principal, contract) -> None` runs after existing repository/profile checks, before `store.submit`. The hook checks exact prepared-catalog bytes without applying wall-clock expiry to same-key retry. Store remains the deadline and replay owner. `GET /catalog` is authenticated and grant-filtered; `GET /ready` uses the read-only callback only in configured mode.

Config exact keys: `{schema:1,mode:"offline_fixture_v1",root,host,port,limits,admission_policy,worker,principals,catalog}`. `root` is an absolute POSIX path with no symlink components; existing managed files must be regular and non-symlink. `host` is `127.0.0.1` or `::1`; port is strict integer1024..65535. `limits` has exactly the existing four constructor slot/budget keys, strict integer values; fixture mode requires service/tenant slots at least3 and service/tenant budget at least1000. `worker` is `{poll_ms,shutdown_seconds}`, strict integers100..10000 and1..120. `principals` contains1..32 closed `{tenant_id,subject_id,repositories,can_review,profiles,token_env}` entries, unique tenant/subject and unique token environment names; use existing Principal validation. Environment names match `CAM_SERVE_TOKEN_[A-Z0-9_]{1,64}`; actual token values are explicit24..512-character values read only by parent, unique, never persisted or inherited by worker. `catalog` contains1..64 exact complete supported fixture contracts, with unique `repo_id` and strict canonical identity. The whole file is at most262144 bytes, strict UTF-8 JSON with unique keys/finite values.

The fixture catalog fixes model `scripted-fixture-v1`, existing expected requirements/base/grader/environment, default five tools, production profile, patch_slot_limit2, budget1000, max_nodes8/max_attempts8, and explicit positive absolute execution/review deadlines. All other fields/overrides reject. Catalog preparation is an explicit CLI action using the existing registry and caller-selected deadlines; preparation never submits or executes work. A changed catalog/config requires a fresh root in this profile. Root config marker stores the canonical config digest, no credentials. The sentinel has fixed authored bytes in a dedicated non-task probe namespace.

Use a fresh subprocess for the existing serial dispatcher, invoked through the current installed Python module, with a minimal environment excluding all tokens/provider keys and Python preload/path hooks. The parent holds the exclusive root lock and passes the lock descriptor into the child, so parent death cannot release ownership while the old worker remains alive. A dedicated parent-liveness pipe makes the child stop taking new tasks after parent loss. The parent can drain then terminate only its own worker process group; an unconfirmed exit retains ownership and an unresolved result. Child status is a bounded internal enum/optional task ID, not an external success authority. Saved active/Unknown/retained-environment state blocks automatic startup. Local filesystem and cooperative current-version ownership are explicit assumptions; the lock is not hostile-user isolation.

CLI: `python -m service.offline_server prepare --config PATH --root PATH --port PORT --workload ID --execution-deadline UNIX_SECONDS --review-deadline UNIX_SECONDS`, then `python -m service.offline_server serve --config PATH`. Preparation writes a new file exclusively. There is no public bind option, live execution mode or automatic dependency installation. Actual local smoke can use an ephemeral operator-selected free port; it must retain its own process identities and stop only its owned processes.
