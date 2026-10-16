# First coding harness lab

This AI-written, standard-library lab makes one execution path completely inspectable. A scripted model reads a real Python fixture, proposes a guarded edit, runs three fixed assertions and stops. SQLite journals action intent and results. The teaching target is control and verification semantics; the scripted repair measures no language-model capability.

**VI:** Dùng model giả để giữ action cố định. Khi test thất bại, em biết phải điều tra protocol, tool hoặc state của harness, thay vì đổ lỗi cho sampling. Sau khi hiểu lớp này, H2 và H7 mới thêm transport thật và môi trường cách ly.

## Run it

Requires Python 3.10 or newer. No packages, API keys or network requests are needed.

```sh
cd lab  # from the repository root
python3 -m unittest -v test_harness.py
python3 harness.py
```

Each demo creates a new directory under `runs/`, including a disposable workspace, SQLite journal, JSONL trace and summary. It never resets an existing run. The completed review run is [demo-6gmll59l — local-only](../docs/github-snapshot.md#omitted-local-evidence); its [trace — local-only](../docs/github-snapshot.md#omitted-local-evidence) contains the actual events. [Verification record](verification.md) states the checks and scope.

**VI:** Mỗi run là một artifact riêng, nên có thể so trace trước/sau sửa harness. File source của fixture được sửa thật; không phải chỉ in ra câu “đã sửa”. Nhưng code chạy trên host trong ví dụ tin cậy, không phải sandbox.

## Predict the trace before inspecting it

The script starts with `def add(a,b): return a - b`. Predict the baseline verifier result, number of model responses, number of tool results and final file contents. These are **exercise prompts**, not predictions attributed to Huy. The observed demo yielded a failing baseline, then four scripted model replies and three tool results, with the revised fixture passing its three assertions.

| Boundary | Actual code | Contract and distinguishing test |
|---|---|---|
| Script selects an action from prior observations | [ScriptedModel](harness.py#L182) | This is deterministic; it is not a learned planner |
| Loop controls continuation and stop | [run](harness.py#L198) | [Claimed completion is unverified](test_harness.py#L93) |
| Accepted ID and canonical arguments enter journal | [Ledger.begin](harness.py#L63) | [Same ID with new args is rejected](test_harness.py#L46) |
| Tool input is validated and executed | [Tools.execute](harness.py#L108) | [Stale read](test_harness.py#L51), [ambiguous anchor](test_harness.py#L58) |
| Tool error becomes a correlated result | [dispatch](harness.py#L161) | [Denied action is durably observed](test_harness.py#L73) |
| Result and event commit together | [Ledger.finish](harness.py#L78) | [Completed replay does not reapply edit](test_harness.py#L39) |
| Unfinished action becomes unknown on restart | [Ledger recovery](harness.py#L50) | [Crash after effect](test_harness.py#L82) |
| Verification refers to exact fixture bytes | [Tested digest](harness.py#L118), [final comparison](harness.py#L209) | [Stale verification cannot pass a new revision](test_harness.py#L106) |
| Verifier must reach its completion marker | [Verifier result](harness.py#L127) | [Early clean exit is not a pass](test_harness.py#L100) |
| Ideal token arithmetic | [token_work](harness.py#L228) | [Closed form matches explicit sums](test_harness.py#L132) |

**VI:** Bảng này nối interface → implementation → phép thử bắt một lỗi cụ thể. Đọc test trước giúp em biết đoạn code tồn tại để ngăn loại sai nào. Đọc source production sau đó để so cách cùng một vấn đề được xử lý ở quy mô lớn hơn.

## One edit through the state machine

1. `read-1` returns file text and SHA-256. Text is bounded for context; the digest refers to all bytes.
2. `edit-1` is stored with its exact arguments before any file change. It includes the previously observed digest.
3. The tool checks the current digest and that `old` appears exactly once. A mismatch produces an error without the proposed write.
4. A temporary file is flushed and renamed over the fixture, giving atomic visibility on that filesystem.
5. The result and corresponding event are stored in one SQLite transaction.
6. The model receives the result. `test-1` records the tested digest, exit code, output and normal-completion marker.
7. The loop only returns `verified` when a successful verifier's digest matches the current fixture.

**VI:** Hash gắn “niềm tin lúc đọc” với “bytes lúc sửa”; hash của verifier gắn “bằng chứng test” với “bytes lúc giao”. Hai mối liên hệ khác nhau và đều cần thiết. Đổi file giữa test và giao phải làm mất hiệu lực chứng nhận cũ.

The completion marker catches accidental early exit; candidate code can forge it. The verifier is therefore a trusted-fixture demonstration, not a grader for malicious code. A real verifier needs stronger separation and still has semantic coverage limits. Likewise, checking a file digest before and after execution assumes no hostile concurrent writer; a production implementation should verify and publish an immutable snapshot.

## Crash recovery and its precise limit

The journal commits intent before tool execution. If the process dies after the edit but before `finish`, a new ledger instance sees an unfinished action. It records `outcome_unknown` and refuses automatic re-execution of the same logical ID. The file may already contain the repair. This trades availability for avoiding an unjustified retry.

**VI:** Kết quả unknown là thông tin chính xác, không phải một failure cần che đi. Với operation idempotent hoặc có receipt, em có thể bổ sung reconciliation. Với một lệnh shell làm nhiều việc, biết file cuối cùng chưa chắc biết mọi side effect đã xảy ra.

Only one process may own this ledger. It deduplicates completed actions and demonstrates conservative recovery; it does not reconstruct or resume the full model conversation. Unknown IDs must be reconciled by a later design; changing the ID and retrying is not a general solution.

## Limitations to extend deliberately

| Present behavior | Next engineering step |
|---|---|
| Trusted fixture and scripted model | Recorded provider adapter in H2, then isolated live-model experiment |
| Narrow path checks | OS-enforced containment in H7; checks alone do not sandbox Python imports |
| Read-whole-file limit and capture-then-truncate output | Incremental limits and bounded spooling in H3; current checks do not bound peak capture memory |
| Single-owner digest checks and rename | Ownership/locking, immutable revision verification, metadata/durability policy |
| Turn/call limits | Wall-clock deadline, token/cost reservation and cancellation in H4 |
| Small immutable assertion script | Protected independent verifier with clean checkout and stronger adversarial cases |
| Action journal | Full session reconstruction, attempt model, leases/fencing and version migration |
| Ideal growing-prefix arithmetic | Tokenizer-aware cache simulation, then measured provider/GPU behavior |

**VI:** Đây là backlog có lý do, không phải danh sách thiếu sót để lập tức thêm hết. Mỗi module chọn một contract, thiết kế phép thử có thể làm nó sai, rồi bổ sung implementation nhỏ nhất đáp ứng contract đó.

## Deliberate debugging exercises

Work in a disposable copy so the reference stays usable. Remove one guard at a time: stale digest check, unique-anchor check, verifier completion marker, final verified-digest comparison, or unknown-outcome recovery. Before running, predict which test will fail and what the environment will contain. Then restore the guard and explain the causal chain. Do not infer correctness solely from the expected test failure; also inspect the resulting file and event trace.

**VI:** Bài chuyển giao: thêm một tool `format` có thể thay đổi file sau khi test. Em phải sửa logic chứng nhận ở đâu để `verified` không bị sai? Nếu câu trả lời chỉ là “reset bool sau edit” thì chưa tổng quát; invariant thật là chứng nhận phải khớp artifact cuối cùng.
