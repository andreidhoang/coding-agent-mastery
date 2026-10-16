# Independent review of configured offline serving

**2026-10-11. AI-authored independent source review and adversarial tests.** The reviewed contract is [S-01–S-05 and the root-selected interfaces](serving-preflight-spec-2026-10-11.md). The [preimplementation audit](serving-readiness-audit-2026-10-11.md) remains a dated baseline. This lane wrote independent tests and review/evidence only; the integration owner repaired runtime source. No live provider, paid execution, GPU, public exposure or human mastery evidence was created.

The selected **local scripted-fixture serving envelope passes after one durability defect was repaired**. Independent checks: **16 passed, zero skips**, including real local PostgreSQL races; the final run took12.34s as reported by pytest (JUnit suite time12.317s). Ruff passed for the independent test file. Three deliberately defective disposable copies were each rejected by a distinguishing test. These checks overlap with broader integrated suites and must not be added to their counts.

**VI:** Kết quả này chứng minh service local biết nhận task có giới hạn, giữ identity khi restart sạch và dừng đúng khi crash tạo uncertainty. Nó chưa chứng minh model thật sửa code tốt hoặc hệ thống tự phục hồi từ mọi lỗi.

## Defect found and repaired

**S-R1 — Refuse a missing or replaced authority database under an existing serving identity.** Before repair, a valid saved `service-identity.json` plus a missing `authority.sqlite` caused `RuntimeStore` to create a new empty database. Startup became ready under a different service incarnation while an already acknowledged task returned `NotFound`. The disposable reproduction actually observed all four properties: `ready:true`, incarnation changed, database silently recreated, acknowledged lookup failed. This is not a hypothetical readiness concern; it loses the advertised restart identity.

The integration owner added missing/zero-byte database refusal before opening the store and bound the marker to the original persisted `service_incarnation`, comparing it before starting the worker. The independent tests also replace the database with a well-formed new schema2 store carrying the correct limits/policy: startup refuses it and preserves the saved marker. A marker from the pre-fix unpublished shape is rejected instead of silently upgraded. Relevant code: [database and marker checks](../service/offline_server.py#L130), [incarnation comparison](../service/offline_server.py#L151), [readiness marker binding](../service/offline_server.py#L238).

The original counterexample is retained in [initial-missing-database.json — local-only](../docs/github-snapshot.md#omitted-local-evidence). The [independent missing/empty/replacement controls](../tests/test_serving_independent.py#L197) pass against the repaired source. Incarnation binding detects replacement with a different database; it does not establish detection of restoring a stale backup from the same incarnation. Actual backup restoration still requires the existing quarantined fresh-incarnation/reconciliation protocol.

**VI:** File cấu hình đúng không đủ: database mới có thể dùng cùng policy mà không chứa task cũ. Marker phải nối đến authority identity. Một backup cũ của đúng database lại là bài toán khác; không được dùng test này để tuyên bố đã đo restore/RPO/RTO.

## Independent controls and observations

| Boundary | Independent experiment | Observed result |
|---|---|---|
| Service admission cap | Eight writers on separate connections race for three slots, using eight tenants; seven constructors omit the policy | Exactly three accepted; exactly three tasks, submissions, events and start commands |
| PostgreSQL transaction semantics | Repeat race and explicit changed-policy reopen in a dedicated UUID schema on the existing local PostgreSQL instance | Same outcome as SQLite; only owned schemas created/dropped |
| Idempotence at full/drained admission | Retry each winner after disabling admission; change the same key's payload | Original IDs reused; changed body conflicts; no additional rows |
| Catalog identity | Alter budget, model, grader or execution deadline while retaining the granted repo |422 before any durable task/submission/event/outbox insertion |
| Real HTTP lifecycle | Fresh CLI process bound to its own loopback port, authenticated catalog/submission, task/events/artifact, graceful stop, fresh process and same-key retry |401 without token;202 allowed task; exact artifact digest; review remains pending; same task ID survives restart |
| API backpressure | Pause only the owned worker; fill the tenant cap; send a new key and an identical retry | New key429; identical retry202; releasing the worker returns capacity after review eligibility |
| Read-only readiness | Capture authority/counts, probe ready, damage sentinel and change effective limits, probe again | Failure detected; probes neither repair corrupted bytes nor alter captured authority/counts |
| Active worker crash | Pause owned worker, inject an authoritative running attempt and Unknown dispatch through existing store APIs, SIGKILL the owned worker | Readiness false, admission disabled, exact task/Unknown/reserved capacity retained |
| Unsafe restart | Reopen the previous running/Unknown/retained-environment root | `reconciliation_required`; no repeated dispatch or fabricated settlement/retirement |
| Parent crash and lock ownership | SIGSTOP the owned child, SIGKILL its parent, independently attempt the root flock, then resume child | Lock remains held until the child sees parent-pipe EOF and stops |
| Durable root identity | Remove, truncate or replace the authority DB while preserving serving marker | Startup refuses; no silent database creation or marker rewrite |

The worker-crash test deliberately injects a precise durable frontier through the supported store APIs while the real worker process is stopped; it then kills the real owned process. It does not claim to have hit a random real model-call crash window. The parent-loss test exercises real inherited-lock and pipe behavior on this Mac/POSIX host. PostgreSQL testing covers the new admission transaction, not a PostgreSQL-backed serving composition (that mode remains intentionally unsupported).

**VI:** Fault injection có kiểm soát giúp biết chính xác state trước crash:40 units đã reserve, dispatch12 còn Unknown, sandbox chưa retired. Sau crash phải giữ nguyên các record đó; chạy lại request chỉ vì process cũ chết là sai.

## Mutation controls

Three source copies under `runs/system-readiness-2026-10-11/serving-review/mutation-*` were created without modifying reference source. Each subprocess verified that `service` imported from its own copied tree. The independent test source was copied unchanged into each tree.

| Removed behavior | Distinguishing test | Result |
|---|---|---|
| Atomic pending count rejection | Eight-writer SQLite race expects exactly three tasks/outbox/events | Rejected, pytest exit1 |
| Exact catalog comparison | Same granted repo with altered budget must reject before durable insertion | Rejected, pytest exit1 |
| Explicit persisted-policy mismatch refusal | Reopen with changed service cap must raise `Unsupported` | Rejected, pytest exit1 |

[Mutation identities/results — local-only](../docs/github-snapshot.md#omitted-local-evidence) and the adjacent logs preserve the negative outcomes. A failed import/collection would not count as mutation rejection; all three failed the intended assertions. No mutation was applied to the live checkout.

## Source review and scope limits

The admission count/check/insert remains under the existing `_tx` service guard, after identical-key resolution, and reads the persisted policy even when the current constructor omits it. Default policy-less stores keep prior behavior. The API hook validates complete prepared contracts before durable submission. The child uses a deliberately minimal environment, `-I`, fixed local module execution and the existing fixture runner; no provider credential is passed. Health and readiness remain separate, with readiness explicitly declaring `production_readiness:unmeasured` and `live_inference:disabled`.

The root lock is cooperative current-code local ownership, not a hostile-user boundary and not an old-binary database fence. Pending capacity does not bound lifetime storage, provide tenant fairness, or retire physical/billing liability. Readiness reports failure without claiming to perform reconciliation. An unfinished active run is refused at restart rather than automatically recovered. General live repair serving, independent hardware measurements, persistence/backup/restore, SLO/load/fairness, credential rotation, external transport, hosted deployment and hostile multi-tenant containment remain separate requirements. The October10 release remains historical; this review does not refresh its installed-package acceptance.

**VI:** “Pass selected envelope” là lời hứa có phạm vi cụ thể. Ví dụ giữ root lock khi parent chết ngăn hai worker cùng sở hữu root local; nó không ngăn một binary cũ tự ghi SQL hoặc chứng minh nhiều host cùng chạy an toàn.

## Evidence and test correction

- [Independent tests](../tests/test_serving_independent.py)
- [Final JUnit — local-only](../docs/github-snapshot.md#omitted-local-evidence)
- [Source/version/control verification — local-only](../docs/github-snapshot.md#omitted-local-evidence)
- [Initial JUnit — local-only](../docs/github-snapshot.md#omitted-local-evidence)

The initial run had12 passes and one test failure: it assumed a graceful CLI shutdown returns process exit0. Inspection of the installed Uvicorn implementation showed it deliberately re-raises captured SIGTERM after lifespan shutdown. The test now accepts that signal result and additionally verifies persisted admission is disabled, the acknowledged terminal task remains present and a new real HTTP process can reopen and return the same task. This was a test expectation repair, not another runtime defect. A Starlette `TestClient` deprecation warning was observed; it is not hidden and did not skip/fail the checks.

Source hashes were captured after the final controls; the serving files were coordinated as stable for that run, while unrelated skills work has separate evidence. Runtime source repairs belong to the integration owner. No remaining blocker was found for S-01–S-05's selected offline envelope. The final project-wide integration run owns any broader claim/count.
