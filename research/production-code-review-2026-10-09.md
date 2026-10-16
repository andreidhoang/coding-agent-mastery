# Production-oriented code review — 9 October 2026

**Status: 22 defect groups repaired; independent re-review and consolidated verification passed on 2026-10-09.** Huy requested a full component review and authorized necessary fixes/refactoring. Astra agents independently reviewed authority/recovery, execution/trust boundaries, controller/workflows and research semantics; 6.1 Sol agents implemented bounded repairs. The coordinator inspected cross-component behavior, operations, workloads and the preserved teaching lab. This is AI engineering evidence, not independent human reproduction or a production certification.

**VI:** Review bắt đầu từ invariant và failure trace, không từ việc file có đẹp hay test cũ có xanh. Các lỗi mới đều được phân biệt với feature vốn chưa có; sửa bug không tự hoàn tất production hay mastery.

## Scope and method

Reviewed first-party `service/`, `evals/`, `compute/`, `workloads/` entry points and authored control/grader behavior, `tests/`, packaging and `ops/`/`scripts/`. The original `lab/` was inspected within its explicit trusted-fixture/single-owner contract. Deliberately incorrect workload variants are negative controls; their defects must remain intact. Vendored `references/`, historical `archive/` and prior runs were preserved rather than treated as production code to rewrite.

The pre-review source snapshot and digests are retained in `.runtime/review-2026-10-09/`. Reviewers wrote expected-behavior regressions before repairs where executable locally, then separate reviewers inspected the repaired implementation. Real local PostgreSQL, Docker and Temporal are used for applicable boundary checks. Paid provider calls, GPU hardware, hosted infrastructure and a hostile multi-tenant threat assessment are outside the measured environment.

**VI:** Ví dụ test local cho thấy một container bị xóa nhầm là evidence trực tiếp về cleanup. Nó không chứng minh Docker đủ an toàn cho mọi attacker. Tương tự, mock HTTP giữ nguyên boundary kế toán nhưng không chứng minh model thật giải được task.

## Findings and repair contracts

P1 denotes a serious correctness or trust-boundary failure on a supported path. P2 denotes a material reliability, accounting or measurement defect. Severity is scoped to this reference's supported use, not an estimate of exploitation in a deployed service.

| ID | Priority | Trigger and failure | Corrected behavior / regression |
|---|---|---|---|
| A1 | P1 | A successful effect with pending billing receives a later billing-only receipt; `result_ref` disappears | Preserve bound result evidence on omission; reject conflicting replacement. `test_audit_authority.py` |
| A2 | P1 | Replay of a terminal tool dispatch without saved result bytes executes the tool again before settlement rejects it | Every duplicate returns retained known evidence or fails before the effect. `test_audit_authority.py` |
| A3 | P2 | Candidate acceptance commits, acknowledgement is lost, exact retry sees its already-completed attempt and fails | Return the same owner/content-bound receipt without a new event; changed content and new stale work still rejected |
| A4 | P2 | A clean worker checkpoint records a sibling's in-flight operation and remains unrestorable after the sibling settles | Apply historical unresolved-effect veto to the checkpoint's owner; retain that owner's causal frontier and unknown-effect checks |
| A5 | P2 | Valid `(tenant=a:b,id=c)` and `(tenant=a,id=b:c)` share a concatenated private database key | Unambiguous canonical pair identity; explicit transactional schema 1→2 migration with compatibility guards |
| A6 | P2 | Missing/empty version metadata in a populated legacy database is treated as fresh initialization, orphaning old keys | Reject before any DDL/data mutation; recheck under serialized bootstrap. Truly empty metadata remains supported |
| C1 | P1 | Lost Temporal start acknowledgement leads to duplicate reconciliation calling asynchronous `memo()` without awaiting it | Await the real SDK method; exercise actual local workflow start, acknowledgement loss and reconciliation |
| C2 | P2 | A complete billed `max_tokens` or malformed tool response is rejected before its evidence/usage is retained | Persist exact received bytes; independently settle valid usage; reject semantic/tool execution. Invalid usage retains exposure |
| C3 | P2 | Stop arrives during the last activity before ContinueAsNew and is lost when the workflow resets | Recheck stop after the activity and before completion/rollover/exhaustion; test local history replay |
| C4 | P2 | JSON exponent `1e999` becomes infinity despite rejecting literal NaN/Infinity | Reject nonfinite numeric values at both provider protocol and authority JSON boundaries |
| E1 | P1 | A second container creation encounters a name conflict and deletes the first live container | Cleanup requires per-creation nonce and immutable container identity; name reuse/conflict confers no authority |
| E2 | P1 | Malformed RPC raises a transport exception that the grader accepts as an expected application `ValueError` | Distinct transport/schema failure plus latched rejection, including when a grader catches generic exceptions |
| E3 | P1 | Caller changes source mapping during grading; verifier hashes the changed, untested bytes afterward | Copy and identify the input tree before execution; use exactly that frozen tree for verification and receipt |
| E4 | P2 | Launcher leader exits after a child detaches standard streams; child remains running | Retire the owned POSIX process group independently of leader lifetime; retain unresolved cleanup status when needed |
| E5 | P2 | Unlimited empty ASGI body fragments consume memory although body byte count is zero | Coalesce bounded payload bytes without retaining an object per incoming message; preserve downstream body/disconnect semantics |
| E6 | P2 | API/domain accepts `tenant:blue`, but artifact storage rejects its namespace | Use the same canonical identity rules across admission and local/S3 artifact paths |
| O1 | P2 | Validation-runner timeout kills the leader but leaves a child ignoring TERM alive | Bounded group escalation and race-safe cleanup for the runner-owned group; no broad process cleanup |
| R1 | P2 | Later evaluation/exposure observations reduce already consumed money/tokens/CPU to zero | Consumed cumulative counters cannot decrease; reservations/unknown exposure may decrease on reconciliation |
| R2 | P2 | Boolean counts, nonfinite rates or finite arithmetic overflow produce invalid experiment configurations/timings | Validate discrete and continuous inputs and derived arithmetic; reject a primary contrast using the same arm twice |
| R3 | P2 | Tool-return simulation assumes a warm prefix after another request evicts it | Look up actual residency; account for prompt, prior output and appended observation; no unaccounted pinned private KV |
| R4 | P2 | Caller clears returned prefix-cache keys, mutating ownership and leaving blocks pinned forever | Return detached observations; release must operate on internal ownership state |
| R5 | P2 | GPU benchmark retains the previous output and reports peaks without starting allocator state | Release output between samples/arms; report allocated/reserved baselines, incremental peaks and explicit allocator policy. Hardware validation remains pending |

**VI:** A1/A2 cho thấy vì sao effect, receipt và billing phải độc lập: trả tiền muộn không được xóa evidence đã có, và thiếu receipt không cho phép chạy lại effect đã biết. E2/E3 cho thấy “pass” chỉ có nghĩa khi grader và bytes được test đều có identity đúng. R1/R3 giữ phép so sánh nghiên cứu khỏi được lợi giả do mất cost hoặc giả định cache vẫn còn.

## Compatibility and migration

Schema 2 changes private dispatch/candidate keys while preserving public IDs, task ownership, liabilities, artifact references and event content. Existing schema-1 databases require the [explicit migration procedure](../service/migrations/002_identity-and-writer-protocol.md). The review does not migrate historical runs. Quiescence and a verified backup remain required; compatibility guards do not authorize mixed-version rolling operation or provide a security boundary.

Model response records now separate receipt of transport bytes, trustworthy usage and permission to continue the agent loop. A rejected/truncated response can be billable without authorizing any tool. Automatic provider reconciliation remains absent. Process-group cleanup covers trusted launcher descendants remaining in that group; it is not a containment mechanism for processes that escape into new sessions.

**VI:** Migration không có nhiệm vụ đoán schema khi metadata đã mất. Trường hợp đó cần khôi phục provenance/backup, thay vì gắn nhãn version mới lên dữ liệu chưa chuyển. Các database cũ được giữ nguyên để học và đối chiếu.

## Verification and current limits

The consolidated suite passed **273 tests plus 15 subtests**, with zero failures, errors or skips. Real local PostgreSQL, pinned Docker Linux execution and Temporal execution/history replay were explicitly enabled. Ruff passed. Rebuilt wheel and nonroot, read-only, network-disabled image smoke checks validated all **42 workloads and 82 protected assets**; their Python files match the tested source. CUDA preflight separately reports unavailable hardware, without a CPU/MPS substitute.

The fresh [two-worker execution trace — local-only](../docs/github-snapshot.md#omitted-local-evidence) reaches `review_eligible` with review `pending`, spent 0/reserved 0/limit 1000, and all three physical environments retired. This uses a scripted model. The [CPU tensor trace — local-only](../docs/github-snapshot.md#omitted-local-evidence) and [synthetic evaluation — local-only](../docs/github-snapshot.md#omitted-local-evidence) retain those evidence labels.

Source identities, integration environments, preserved-file checks and packaging results are recorded in [the consolidated verification record](production-review-verification-2026-10-09.json). The previous [8 October delivery record](reference-delivery-verification-2026-10-08.json) remains a historical result for its own source snapshot.

Existing feature gaps remain: automatic active-attempt reconciliation/replacement, graph revision, general live-repository coordination, automatic context rollover, fair queues, full retention/GC and operated release/SLO/restore evidence. CUDA performance, paid-model capability, live scaling results and human mastery are not established by this review. See the [coverage register](../capstone/08-implementation-coverage.md) for the broader contract.

## Primary references checked

- The installed Temporal SDK and [its asynchronous memo API](https://python.temporal.io/temporalio.client.WorkflowExecution.html) support C1's diagnosis; the real local integration is stronger than the original synchronous mock.
- [Anthropic stop reasons](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons) distinguish normal generation stopping from permission to execute incomplete proposals; billing receipt retention must be independent of this decision.
- [ASGI request-body events](https://asgi.readthedocs.io/en/latest/specs/www.html#request-receive-event) allow empty bodies and streamed fragments; a payload-byte limit must not be bypassed by per-message retention.
- [Docker container removal](https://docs.docker.com/reference/cli/docker/container/rm/) is destructive to the selected container; application-level ownership must be established before invoking it.
- [Python subprocess handling](https://docs.python.org/3/library/subprocess.html) distinguishes process waiting, timeout and explicit cleanup; this project additionally owns a POSIX group for trusted launchers.
- [PyTorch allocated peaks](https://docs.pytorch.org/docs/stable/generated/torch.cuda.memory.max_memory_allocated.html) and [reserved peaks](https://docs.pytorch.org/docs/stable/generated/torch.cuda.memory.max_memory_reserved.html) are allocator measurements; resetting their counters does not release tensors or cached allocations.

**VI:** Các tài liệu primary giải thích contract của dependency. Kết luận bug/fix vẫn dựa trên source và distinguishing test của project, không dựa vào tên framework hay lời khẳng định “production pattern”.
