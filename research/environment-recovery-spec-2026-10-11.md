# Durable Docker environment intent and bounded cleanup recovery

Date: **2026-10-11**, Asia/Ho_Chi_Minh. Status: **FROZEN before implementation — source-inspected design, not delivered evidence**. Scope: existing local Docker verifier environments, current RuntimeStore schema2, explicit trusted lifecycle injection and finite reconciliation. No paid provider/GPU execution, image pull, arbitrary repository support, automatic model/tool retry or operated disaster-recovery claim. Preserve historical releases and existing non-journaled fixtures. This follows [the runtime audit](runtime-readiness-audit-2026-10-11.md).

## Problem, owners and decisive experiment

`DockerSandbox` currently generates `creation_nonce` in memory before `docker create`; `_recover_owned_instance` correctly requires that nonce and `_bind_container` verifies the immutable container ID. A supervisor restart loses the nonce before it can use those checks. Persist the exact creation intention first, then bind observed physical identity to it. The existing sandbox reservation remains the physical capacity owner. A new controller may inspect/clean only that recorded identity; absence after uncertain create remains uncertainty.

**VI:** Tên container có thể được tái sử dụng; nonce chỉ đúng cho một lần tạo. Muốn restart an toàn thì phải ghi nonce trước khi gọi Docker. Không thấy container sau timeout chưa chứng minh nó sẽ không xuất hiện muộn.

Expected test: reserve one verifier slot; commit instance intent with nonce N; create container C but lose its acknowledgment and kill the supervisor. Fresh process loads the same intent, finds exactly one C with N on the same configured Docker daemon, verifies C's identity/config, binds C, removes C by immutable ID, observes its absence, then releases the reservation once. A zero-match probe keeps the reservation occupied; it never calls create. A replacement container with the same name but another nonce remains untouched. This is a proposed oracle.

| Object | Owner and contract |
|---|---|
| Task generation, service incarnation, reservation/slot | RuntimeStore; new creation requires current authority and existing reservation |
| Candidate/recipe/environment/input digests | Existing verifier; bind actual copied source and immutable image/limits, retain private test inputs only in protected verifier memory |
| Create intention, nonce and immutable container ID | Closed versioned metadata in existing sandbox row; immutable intention, monotonic observed state |
| Physical observation | Trusted configured local Docker adapter; complete bounded launcher output and same daemon identity required |
| Cleanup admission | Trusted lifecycle supervisor, fenced by current service incarnation; explicit irreversible cleanup request blocks new instance admissions |
| Task effect/charge ledger | Existing dispatch/receipt/budget records; lifecycle reconciliation neither settles charges nor manufactures verifier passes |

## Persistence and exact bounded metadata

No new SQL tables or schema migration. Add optional sibling `environment_journal` only to newly opted-in `sandboxes` rows. Existing rows remain untouched. The envelope is closed:

`{schema:1,profile:"docker_environment_journal_v1",revision,phase,backend,source,max_instances,instances}`.

- `revision` is a strict positive integer incremented on each novel transition; identical retries do not increment it. `phase` is `open`, `cleanup_requested`, or `retired`. Once cleanup is requested the journal never reopens. A journaled reservation cannot be retired through the old arbitrary-evidence path.
- `backend` is exactly `{kind:"docker_local",backend_id,daemon_id}`. Trusted startup selects a non-secret backend label and obtains the daemon ID using bounded local Docker inspection; every recovery observation confirms it. A different daemon/socket/context refuses. Backend strings are nonempty ASCII, at most128 bytes; no candidate-controlled endpoint or shell string.
- `source` is exactly `{generation,service_incarnation,purpose,tree_digest,input_digest,grader_digest,environment_digest}`. Purpose is `fixture`, `worker` or `final`. Digests bind the actual candidate, exact copied file map including the existing bridge, frozen grader and measured verifier environment. No private test arguments/expected values enter journal/event/cleanup output. Source metadata is supplied by the trusted existing verifier, not by model input. Task/generation and frozen grader/environment identities are checked where applicable.
- `max_instances` is a strict integer1–32 fixed at journal initialization. A Linux fixture verifier uses1; a Python-function verifier uses its selected frozen case count. `instances` is a list in ordinal order with at most that many elements; **one physically unresolved instance at a time**. Instance ordinal is contiguous and cannot be reused with changed intent.
- Each instance is closed `{ordinal,intent_id,name,creation_nonce,launch,state,container_id,create_observation_ref,retirement_observation_ref}`. `intent_id=D({sandbox_id,ordinal,source,backend,launch})`; `name` is deterministic `cam-sandbox-` plus a bounded digest identity. `creation_nonce` is newly generated32-hex and durable before create; a duplicate retains its original nonce. `container_id` is null until an exact64-hex Docker ID is verified, then immutable. Observation refs are null or ordinary scoped hash/size/content-type checked references.
- `launch` is closed `{image,memory_mb,cpus,pids,disk_mb,timeout_seconds,policy_digest}`. Preserve the existing DockerSandbox validated limits and immutable image requirement. `policy_digest` binds the existing fixed no-network/no-host-mount/read-only/nonroot/drop-capabilities/no-new-privileges/tmpfs/workdir/entrypoint/create-argument policy. Candidate text cannot alter launch flags. `state` is `create_intent`, `bound`, `create_rejected`, or `retired`; unresolved cleanup retains `create_intent`/`bound` with a bounded diagnostic observation and occupied slot.

Enforce canonical journal size <=65,536 bytes before commit; observation <=16,384 canonical bytes and individual retained sanitized diagnostic strings<=1,024 UTF-8 bytes. Read bounded artifacts before JSON parsing; query only the selected sandbox and at most32 stored instances. Do not scan all containers or all task artifacts, then apply the cap. A nonce-filtered query allows a two-record sentinel to detect ambiguity and has bounded output/time. Unknown/extra/bool-version fields reject; failed validation publishes no authority record. These local policy limits are proposed design values, not measured optimality.

**VI:** Một reservation có thể chạy nhiều testcase nối tiếp nhưng chỉ giữ tối đa một container chưa chứng minh đã chết. Journal ghi hash của source và policy, không ghi test private để tiện debug rồi vô tình mở grader cho candidate.

## State transitions, effects and authority

1. Initialize the journal once under a current task generation/service incarnation and live reservation. Exact duplicate initialization is read-only; changed source/backend/limit conflicts. This may be combined with first-instance intent in one store transaction. Failure before commit must call no Docker operation.
2. Admit ordinal n only while `phase:open`, reservation unretired and current authority valid; ordinal0 starts the sequence, all earlier instances must be terminal `retired`/`create_rejected`. Commit nonce, exact intent and event before `docker create`. Return `{duplicate:false,instance}` only to the winner. A duplicate `create_intent` must never reissue create, even when the caller believes its original call had not started. No database lock is held during Docker operations.
3. The winner invokes the existing fixed create command with the journal's name/nonce and frozen launch. `DockerSandbox` must accept the durable nonce explicitly on this path and must not overwrite it with a new random value. After acknowledged create, inspect the returned immutable ID, name, exact nonce, immutable image/config and same daemon; only then commit `bound`. Do not start/copy/exec until binding commit succeeds. If create or binding acknowledgment is lost, recovery inspects; it never guesses a binding or creates again.
4. A complete acknowledged name-conflict rejection of this sole create invocation may commit `create_rejected`: no owned instance was created. Unrecognized nonzero errors, timeout, truncated output, invalid ID or ambiguous transport remain `create_intent`. No absence probe alone proves create rejection. A failed journal write after acknowledged conflict leaves conservative uncertainty.
5. Normal close or trusted reconciliation requests `phase:cleanup_requested` before final reservation cleanup. Per-case close may retire an instance while the phase stays open so the next frozen case can start; final phase closure seals further admissions. Binding/observation/cleanup transitions require this RuntimeStore controller's current service incarnation, even after task cancellation/deadline. Cleanup is allowed for revoked tasks and for old reservations via a fresh current-incarnation controller; it does not reinstate task execution.
6. For an unbound intent, query the exact durable nonce on the same daemon. One matching container may bind only after the same ownership/config checks. Zero matches remain unresolved because a delayed create may still arrive. Two matches or mismatched name/image/nonce/config remain unresolved; delete neither. Operators may supply stronger separately specified evidence later; no generic `reconciled:true` override in this slice.
7. For a bound instance, address only the immutable container ID. Revalidate ownership before deletion when present. Removing that ID is idempotent; subsequent complete acknowledged inspection/inventory showing that bound ID absent on the same daemon establishes physical retirement. Reused names are irrelevant. Incomplete/truncated/failed observation, uncertain daemon identity, or unknown remote cleanup retains the slot. A valid absence for an already bound ID is distinct from absence for a create intention with no known ID.
8. Persist the trusted observation artifact outside the store transaction; the transaction validates its closed fields/scope/digest against the instance and records the monotonic terminal state. Final reservation retirement requires `phase:cleanup_requested`, every admitted instance terminal and no unresolved creation/cleanup. Atomically set journal/reservation retired and use existing allowance/physical-slot retirement semantics exactly once. A journaled sandbox cannot bypass this by passing a nonempty dictionary to `retire_sandbox`.

Exact duplicate intent/binding/retirement requests return saved data without new effects/events. Changed nonce/container/config under the same intent conflicts. Use a bounded operation identity for novel observations and stable terminal evidence so multiple cleanup controllers converge; a stale revision cannot replace newer binding/retirement. Cleanup of one immutable ID may be safely retried, but successful cleanup never implies replaying model/tool/test execution or publishing a verification pass. Journal completion records physical state only.

**VI:** Hai loại absence khác nhau: đã biết ID C rồi không còn C thì có thể xác nhận C đã bị dọn; chỉ có nonce N nhưng chưa biết C có được tạo hay chưa thì không thấy N vẫn là Unknown. Đây là invariant quan trọng nhất của slice.

## Minimal API and actual consumer integration

Proposed internal interfaces (exact names may be consolidated at freeze; semantics above remain fixed):

```python
RuntimeStore.begin_environment_instance(tenant, sandbox_id, *, source, backend,
    max_instances, ordinal, launch) -> dict  # duplicate + immutable instance grant
RuntimeStore.bind_environment_instance(tenant, sandbox_id, intent_id,
    observation_ref, *, expected_revision) -> dict
RuntimeStore.record_environment_retirement(tenant, sandbox_id, intent_id,
    observation_ref, *, expected_revision) -> dict
RuntimeStore.request_environment_cleanup(tenant, sandbox_id) -> dict
RuntimeStore.read_environment_journal(tenant, sandbox_id) -> dict

EnvironmentLifecycle(store, artifacts, tenant, task_id, sandbox_id, backend)
EnvironmentLifecycle.instance(*, ordinal, source, launch, max_instances) -> binding
reconcile_environment(lifecycle, docker_backend, *, max_instances=32) -> dict
```

`reconcile_environment` is a finite trusted local command/function for one explicit reservation. It requests cleanup, inspects/cleans at most32 journaled instances, then either returns `retired` or `unresolved` with exact retained identities/reasons. It must not automatically select a new attempt, call a model, rerun a case, settle usage, or operate on unjournaled names. Persisted intent is required for reconstruction; an unjournaled historical reservation returns unsupported/manual reconciliation without inventing a nonce. No HTTP operator endpoint or recurring automation is added.

Add an optional lifecycle parameter to **existing** `LinuxVerifier.verify(..., sandbox_id=None, lifecycle=None)` and `PythonFunctionVerifier.verify(..., purpose="worker", sandbox_id=None, lifecycle=None)`. The Linux verifier has one instance. PythonFunctionVerifier already creates a fresh instance per case with a deterministic reservation/ordinal identity; acquire the durable instance binding immediately before constructing that case's DockerSandbox. An exception/Unknown retirement stops the loop as today. Successful per-case closures persist independently of eventual aggregate result return, so a crash before that return is recoverable.

Do not inject the journal through `PythonFunctionVerifier(sandbox_factory=...)`: that existing switch deliberately marks execution as `injected_test_only` and changes environment identity. Use the new lifecycle argument alongside the actual Docker backend; retain test-only factory behavior and default signatures. Extend `DockerSandbox.__init__`/start/close via optional journal binding/callbacks while preserving its normal no-journal behavior for historical tests. Validation must happen before external create, not merely after result assembly.

`RepairEngine._checks` and the Linux branch of `ReferenceEngine.run_task` supply the lifecycle object from their already accepted reservation when explicitly configured for the new profile. They keep their exact frozen verifier/candidate checks, publish no pass on infrastructure failure, and close/seal aggregate retirement through the new journal-aware store path. Trusted fixture workspaces with no candidate process keep existing retirement evidence. Runtime launcher opt-in must be explicit; no silent retrofit of arbitrary old rows. The environment identity already binds verifier/execution source, so refresh newly measured source identities rather than editing old frozen approval artifacts.

**VI:** Tích hợp đúng vào verifier thật rất quan trọng: bọc `sandbox_factory` sẽ làm hệ thống tự gắn nhãn mock, không phải proof của Docker path. Ghi từng case trước/sau create giúp restart không phụ thuộc result cuối cùng còn nằm trong RAM.

## Adversarial acceptance and scope limits

| ID | Intervention | Required result |
|---|---|---|
| E01 write-ahead | Crash/fail journal before create; lose journal ACK; replay same ordinal with changed launch | No create before committed winner; duplicate/changed identity cannot launch; original nonce retained |
| E02 uncertain create | Docker create completes then timeout/ACK loss; terminate supervisor; reopen DB/artifacts in fresh process | Reconcile exact nonce to immutable ID, clean once; zero-match/ambiguous inventory remains occupied and no create retry |
| E03 wrong target | Reuse name with different nonce; wrong daemon/image/config/ID; multiple nonce matches | No wrong-instance deletion/binding; bounded unresolved evidence |
| E04 crash windows | Fail binding write, start/copy/run, per-case retirement write, aggregate report publication, slot-release ACK | Owned environment remains findable; absent terminal evidence retains slot; known terminal retry converges |
| E05 authority | Cancel/deadline/quarantine or replace service incarnation around create/bind/cleanup | No new execution from stale actor; fresh trusted cleanup can retire old exact instance; no capability/task authority revival |
| E06 capacity | Two instance admissions/cleanup controllers race; prior instance Unknown; final reservation retired | Single creation winner, one unresolved physical instance per reservation, no next case on uncertainty, exactly-once slot release |
| E07 bypass | Call old `retire_sandbox` with fabricated generic evidence on a journaled row | Rejected unless all journal terminal guards satisfied; unknown effect/billing reservations unchanged |
| E08 bounds/schema |32/33 instances, journal/observation cap/cap+1, unknown keys/bool ordinals, huge/truncated inventory | Bounded pre-effect refusal, no partial authority update, no private grader/source leakage |
| E09 actual consumers | Real local Docker fixture verifier and Python-function verifier with multiple cases; mock injected equivalents separately | Physical lifecycle records for each actual instance, preserved verifier identities/negative grader control, honest modes; no live provider/GPU required |
| E10 bookkeeping only | Reconcile physical instance while model effect Unknown or bill unsettled; wrong candidate passes its own output | Slot may retire from valid physical proof, liabilities remain; no completion/verification/charge record synthesized |
| E11 transactions/replay | Instrument artifacts/Docker I/O during store transaction; repeat identical intent/bind/terminal receipt | No external I/O inside authority transaction; no duplicate create/event/result/slot release |
| E12 old compatibility | Non-journaled fixture verifier/repair path and schema2 stored rows | Existing tested behavior remains; missing historical nonce explicitly unsupported, no rewriting release artifacts |

Required defective controls: remove write-ahead admission; treat zero nonce matches as retirement; clean by name; allow generic retirement to bypass unresolved journal. Each must fail a targeted oracle. Run CPU/mock checks first, existing authorized local Docker and PostgreSQL when available, one real fresh-process ACK-loss cleanup drill, affected execution/verifier/repair/store regressions and lint. Record actual source/daemon/image identities and skips. No full-suite pass count can establish hostile containment, remote-provider reconciliation, backup RPO/RTO or operated production readiness.

**VI:** Slice này sửa mất ownership của process qua restart. Nó không chứng minh candidate an toàn tuyệt đối, không biết provider đã charge bao nhiêu, và không làm task đã fail trở thành pass. Evidence phải giữ riêng các lane đó.

## Source seams inspected and work ownership

- [DockerSandbox](../service/execution.py#L259): nonce currently in memory; start at340, bind297, nonce lookup317, close468.
- [LinuxVerifier.verify](../service/verification.py#L148): one actual Docker instance; close result returned only after protected grader finishes.
- [PythonFunctionVerifier.verify](../service/repair_verification.py#L338): per-case creation and cleanup; factory mode at269 distinguishes mocks; environment source identity at310 and module end.
- [RepairEngine._checks](../service/repair.py#L155): existing reservation -> verifier -> aggregate retirement, plus clean-checkpoint resume guards at183.
- [ReferenceEngine.run_task](../service/engine.py#L57): existing auxiliary reservation and Linux verifier execution.
- [RuntimeStore.retire_sandbox](../service/storage.py#L1347) and [reserve_environment](../service/storage.py#L1989): existing physical capacity/allowance owners. Line numbers reflect the source during step5 review and may move with integration.

One runtime integration owner edits these shared files after freeze. Independent tests should use a controlled fake Docker transport with exact lost-response/late-create states before candidate code, then a distinct local Docker drill. Source review checks every release of physical capacity against recorded immutable instance evidence. Separate `service/environment_recovery.py` for pure shapes/lifecycle/reconciler is preferable to growing skill recovery. No automatic deployment or paid execution follows.

## Integration owner freeze decision

Use the proposed methods or thin delegates on RuntimeStore with closed validation isolated in `service/environment_recovery.py`; authority writes still use its existing `_tx`. Engine opt-in is an explicit trusted `environment_backend` constructor argument defaulting to `None`; absence preserves historical behavior. Only an injected actual local Docker backend activates the profile. Do not enable this journal through serving `offline_fixture_v1`, which launches no Docker candidate. Record real Docker acceptance through the existing Linux and supported-function paths. No implicit background cleanup, public route or old-row adoption. Current-owner checks precede every new create/start/copy/exec; current-incarnation cleanup may reconcile revoked execution. A cleanup request fences subsequent execution even when the container still exists.
