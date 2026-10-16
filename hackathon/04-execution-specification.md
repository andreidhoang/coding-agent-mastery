# Repository repair execution specification

Active instruction, 2026-10-10: Huy requests sustained specification and implementation without a daily build-time limit. The earlier four-hour/80-hour estimate is superseded. Work advances by tested acceptance gates. Paid inference/hosting limits and account inputs remain unset; this build uses local mock HTTP and already present local containers, with live spending disabled.

This slice implements the missing supported-repository path while preserving the existing fixture engine, authority database, harness, artifact store, verifier accounting and evaluator. Course-derived context/LSP/skills and NV1–NV3 work remain separately specified and do not displace the repair path. Later NV-S0 CPU evidence has its own source-bound record. AI authorship and engineering tests do not create human mastery.

**VI:** Không còn daily-hour gate. Ta hoàn thành từng đường chạy có invariant và evidence, rồi tiếp tục phần chưa đạt. Model/API thật và paid deployment vẫn cần input rõ; việc đó không cản build và kiểm tra reference locally.

## Component sequence and owners

| Step | Source owner and input/output | Invariant | Distinguishing check |
|---|---|---|---|
| E1 Frozen intake | `service/repositories.py`; operator-declared source/read paths and writable subset -> immutable UTF-8 snapshot/manifest | <=50 files/256KiB; canonical safe paths; symlinks and protected path names rejected; detached input/output; optional Git provenance distinct from tree digest. Embedded secrets are not detected; source selection remains operator-owned | Source change after intake cannot alter manifest; symlink/path escape/oversize rejected; protected path cannot become writable |
| E2 Recipe | `service/repair_verification.py`; exact source manifest, module/export, public/private JSON cases -> frozen recipe/grader identity | Expected outputs and private assertions remain supervisor-owned; worker receives public case metadata only; no arbitrary host imports | Wrong/unchanged/forged-PASS implementations fail; True cannot satisfy expected integer1 |
| E3 Bounded execution | Same recipe + immutable candidate -> per-case Docker RPC result and retirement evidence | Fresh container per independent case; no network/host mounts/host credentials; bounded process/output; unknown cleanup halts and retains slot | Timeout/output/schema/nonzero/uncertain cleanup latch failure; no subsequent PASS overwrites it |
| E4 Oracle-free runner | `service/repair.py`; frozen task/repository/recipe/provider -> one patch node -> harness -> immutable candidate -> independent verifier | No reference-patch imports; explicit approved model; fixed tools/test recipe; dispatch and reservations reuse RuntimeStore; worker tests are feedback, final verifier binds exact tree | Mock NVIDIA-shaped transport sees source, edits based on digest, receives test feedback and reaches review_eligible with pending review |
| E5 Clean restart | Runner + supported committed checkpoint -> trusted retirement -> fresh owner -> native continuation | No rewind across later/unknown dispatch; cancellation is not pause; old owner fenced; consumed budget retained | Pause after committed checkpoint, reopen process/store, continue with new epoch; uncertain dispatch refuses resume |
| E6 Product artifact | `service/repair_reporting.py` and CLI; committed state/artifacts -> diff, tests, costs, HTML | Exact downloadable diff reconstructs candidate; escaped user strings; reports distinguish mock/provider and final/human evidence | Report reload makes no provider call; stale identity cannot show verified; script injection rendered as text |

Public API names and record schemas are frozen in the component contracts before their implementation; architectural audits record any remaining assumptions. Supported tasks live inside the existing `workloads/repair/` package. First task is an owned tiny Python function repository, labeled authored evaluation rather than a real-world capability benchmark.

## Supported semantics

The initial repository recipe evaluates stateless JSON-callable Python functions. Each input carries module path, allowlisted export, positional/keyword JSON arguments and a request identity. The candidate returns a strict typed envelope with either JSON value or exception type. The trusted host compares against one frozen assertion. It never trusts candidate exit0 or the word PASS as a verdict. Only candidate inputs cross the container boundary; expected outputs stay in the parent. A fresh container starts from the candidate snapshot for each independent case.

Worker tests use public cases. Final verification uses private cases in fresh containers and retains exact recipe/environment/tree identities. The runner reserves an auxiliary verifier slot before either kind of test and retires it only after every created container is confirmed retired. The patch grant covers text workspace ownership, not arbitrary host code execution. A separate patch-retirement record proves removal of that controlled workspace.

**VI:** Public tests giúp model sửa lỗi; private final assertions tạo một observation độc lập. Không gửi đáp án cùng input vào container. Mỗi case độc lập cần bắt đầu từ cùng bytes để candidate không sửa state giữa cases rồi làm sai ý nghĩa tree digest.

## Tiny expected trace and failure prediction

Authored source exports `normalize_slug(text)` and mishandles repeated whitespace/punctuation. Intake freezes its bytes and writable path. A native mock provider first reads source, requests a guarded edit, runs the fixed public checks, then proposes completion. The runner freezes the resulting candidate, runs the private host assertions against fresh bounded containers, records an exact verification receipt and publishes review eligibility. Human review remains pending.

AI prediction: a plausible wrong edit that passes public cases fails at least one private control; an HTTP response lost after dispatch leaves Unknown and its bound reserved; a pause after the committed tool-result checkpoint can resume with a new owner and exact native transcript. Observation of a repeated uncertain request, old-owner write, leaked private assertion in provider payload, or wrong tree reaching eligibility falsifies the design.

## Acceptance and evidence

Complete intake, recipe, runner, restart and report tests with deterministic injected transports; then exercise the new final verifier on the already present immutable local Python image. Preserve previous source/runs. Run the default suite once after integration and focused checks after any review repair. Independently review the integrated source before delivery. Record source digests, environment and backend skips; do not inherit the October9 integration result for new source.

This delivers a runnable local supported repair reference. Actual Nebius account conformance, measured NVIDIA coding capability on unseen authorized tasks, public hosting/source/video and submitted entry remain separate operational gates. No winning outcome or broad hostile isolation is asserted.

## Delivered evidence and review corrections

E1–E6 are implemented for the bounded stateless Python function profile. [Delivery verification](../research/hackathon-2026-10-10/repair-delivery-verification.json) binds source hashes, dated checks, real local Docker controls, uninterrupted repair and a pause/resume across two separate processes. Each authored demonstration used five native mock requests and three verifier evaluations, reached review eligibility with human review pending, and retired every slot. This measures controller/execution mechanics rather than actual NVIDIA coding quality.

The default suite passed575 tests and15 subtests with24 explicit skips; the opted-in new integration suite passed132 tests. Both preceded the final event-contiguity correction, which has its own13-test boundary result. These overlapping phased counts must not be summed. [Independent Astra review](../research/hackathon-2026-10-10/repair-independent-review.md) drove fixes for cross-attempt rewind, exact patch framing, failure-outcome display and complete event export. Committed final receipts are reused after a publication interruption rather than rerun.

Earlier offline wheels and unpublished licensed source candidates remain historical snapshots. The [current offline release](../releases/README.md) now packages current runtime/compute/evaluation source and has [two fresh installed-package acceptance runs](../research/offline-release-verification-2026-10-10.json) on this Mac; it preserves the supported repair profile and original production contracts. The [runbook](05-local-repair-runbook.md) supplies reproduction and genuine-provider setup. Browser local-file navigation was policy-blocked, so rendered report layout remains uninspected; static structure/download/escaping checks passed.

The optional [journaled local-Docker profile](../ops/runbooks/environment-reconciliation.md) now records per-case creation intent/nonce before effects and supports bounded explicit cleanup after process loss. Automatic task replacement, remote-effect/billing reconciliation and Unknown replay remain unsupported. Existing default CLI runs are not silently switched or adopted. The later [HTTP evidence contract](06-http-error-evidence-contract.md) is now implemented/reviewed under its [own verification](../research/hackathon-2026-10-10/http-error-verification.json), with current integrated checks and refreshed packaging. Huy keeps paid execution disabled. Account/model/rate evidence, a changed spending instruction, live NVIDIA repairs, public access and final submission remain essential external gates.

**VI:** Evidence thuộc đúng source và đúng phase. Mock điều khiển tool proposal; Docker chạy candidate thật. Không cộng các suite trùng nhau, không lấy CPU RMSNorm của nhánh NVIDIA làm bằng chứng repair, và không suy ra mastery của Huy từ code do AI viết.

## Qualification wrapper delivered before live activation

[The frozen spec](../research/provider-qualification-spec-2026-10-11.md) adds prepare/run/report/handoff commands around the existing native harness and ledger. [Runbook](../ops/runbooks/provider-qualification.md), [review](../research/provider-qualification-independent-review-2026-10-11.md) and [verification](../research/provider-qualification-verification-2026-10-11.json) bind its offline scope. Exact manifest digest in the durable contract prevents transcript relabeling; read-only prepared-state checks protect the existing repair. No changes to RepairEngine/provider authority, live flags, schema2 or required G1/G2/G5 criteria. Paid/live execution stays disabled.
