# Hackathon plan review — 2026-10-10

Review-only inspection of `hackathon/README.md`, `01-product-and-system-design.md`, `02-delivery-and-submission.md`, `03-foundations-and-evaluation.md` and `00-nebius-protocol-contract.md`, compared with the same-day rules/provider audits and newly landed source. This review did not repeat web research, run paid calls, deploy, rerun tests or edit implementation. Official facts below are checked against the retained research, not independently re-fetched. Earlier architecture/provider research describes its preimplementation source snapshot; do not silently rewrite that history into current-state evidence.

**Assessment:** The product plan is coherent and materially stronger than a general multiagent demo. Deadline conversions, cost arithmetic, sponsor inference versus application execution, final-verifier limitations, and pilot inference caveats are sound. It preserves the two-worker capstone default while selecting one worker for the hackathon. No winning, live-model, GPU-performance, hostile-isolation or human-mastery result is falsely claimed. Correct the endpoint mismatch and make conditional release gates and judge-access decisions explicit before treating this as the executable schedule.

**VI:** Phạm vi đã tập trung đúng: model thật sửa một bug, chạy test và đưa bằng chứng đúng candidate. Những điểm cần chỉnh là contract khớp code mới, gate nào được cắt nếu thiếu giờ, và judge chạy miễn phí bằng cách nào. Đây là review kế hoạch, chưa phải evidence sản phẩm đã chạy.

## Material findings

### P2 — Documented endpoint allowlist exceeds the implemented adapter

[Protocol contract line40](../../hackathon/00-nebius-protocol-contract.md#L40) says the initial allowlist contains both global and us-central1 endpoints. [NebiusChatCompletions](../../service/providers.py#L249) permits only the exact global endpoint, rejecting all others at construction and again before receive. A developer following the contract could configure the documented regional URL and fail before the first call. Change the contract to **global-only in S0; regional support is a future separately validated change**. Do not widen the adapter merely to satisfy stale prose. Other product docs already prefer the global route.

### P2 — Sequential release-gate wording conflicts with the allowed reduced product

[README G3/G4 and next-step rule](../../hackathon/README.md#L50) presents supported restart and the paired pilot as ordinary release gates and instructs engineering to follow the first unsatisfied gate. [Delivery fallback](../../hackathon/02-delivery-and-submission.md#L61) permits dropping restart UI when hours are lower; [video fallback](../../hackathon/02-delivery-and-submission.md#L104) explicitly permits a completed repair without supported recovery. These are reasonable fallbacks, but the gate table can still block submission work behind G3/G4.

Label G0/G1/G2/G5 as required for this proposed entry; classify G3 as required **only if restart is retained in the product claim**, and the comparative portion of G4 as conditional on available effort/spend. Honest evidence and exact successful-run provenance remain unconditional even when the 24-run comparison is cut. Once a gate is deliberately cut, revise the title/claims/demo accordingly and proceed to release readiness; do not leave the product described as resumable while its restart gate is waived.

### P2 — Free test-build judging path is a release decision, not yet an operational fallback

[Cost and judging access](../../hackathon/02-delivery-and-submission.md#L75) correctly requires free access and refuses a public server key or judge-paid account. It does not yet choose how a downloaded test build gets funded inference through December 16 Vietnam time. A public ZIP alone cannot resolve this. A gateway with private credentials, a funded hosted demo, or an organizer-confirmed workable test-access arrangement still needs implementation and cost ownership. Recorded traces are helpful evidence but not a replacement for the stated functioning build requirement.

Add a dated decision gate, preferably by October 20, choosing the access route and owner. Before G5, exercise that route from a clean unauthenticated client using the actual judge instructions, and retain the inference/availability budget through the judging window. The plan already states this obligation accurately; the issue is dependency closure within the schedule. Neither the generic signup credit nor an advertised hackathon promotion proves that December usage is covered.

### P2 — Freeze baseline restart behavior before the paired pilot

[Foundations pilot](../../hackathon/03-foundations-and-evaluation.md#L55) identifies a minimal single-agent baseline and durable candidate but does not define exactly what baseline state survives the injected interruption. [Fault assignment](../../hackathon/03-foundations-and-evaluation.md#L59) says “clean-checkpoint interruption in both arms,” although the minimal baseline may have no checkpoint mechanism. Different restart decisions can determine the whole treatment effect.

Before executing the pilot, record the fault boundary as an observable logical event common to both arms, such as completion of a specified successful tool-result turn. Declare whether baseline restart uses original source/transcript, surviving workspace only, or its own documented checkpoint support, and whether one restart is attempted automatically. Both arms must use the same outer run budget/deadline and durable cost meter so a process kill cannot reset the baseline spending ceiling. All repeated calls consume the same assigned allowance. Preserve the current separation of fault and clean strata; different task sets cannot identify the causal effect of interruption itself.

### P3 — The “exact” owner tuple omits tenant identity

[System trace step2](../../hackathon/01-product-and-system-design.md#L87) abbreviates the owner to six members and omits tenant. The [actual grant](../../service/storage.py#L586) uses seven: service incarnation, tenant, task, generation, node, node epoch, attempt. Even for a single-tenant hackathon flow, preserve the exact tuple in a teaching trace or explicitly label the expression abbreviated. The omission does not currently weaken code authorization, but it undermines the packet's exact-state teaching contract.

## Feasibility and scheduling judgment

The arithmetic is correct: October10–29 inclusive is20 days; four hours/day is80 hours; planned stage effort sums to80. The October29 six-hour allocation is explicitly drawn from earlier retained time and is not a hidden daily-availability claim. October29 at18:00 Vietnam is30 hours before October31 at00:00. Submission contingency is October30, with no planned feature work.

Eighty human hours is an aggressive integration estimate, not a reliable forecast. The strongest dependency risks are first real model conformance, creating the first supported repository verifier, implementing clean restart authority/retirement, and provisioning genuinely free judge access. AI coding assistance does not remove those verification decisions. The six-task/two-family pilot also needs task curation and an additional recipe if the families cannot share one; that work is not clearly assigned to a stage.

Recommended schedule control: by October17 require one oracle-free live repair and final exact-tree verification. If missed, drop restart and the comparative pilot before spending on polish, preserve all existing negative evidence, and focus on the required useful repair/access/release path. By October20 choose judging access and either budget the second repository recipe inside the evaluation allocation or reduce the predeclared pilot before any assignments run. Never reduce the denominator after viewing outcomes. This keeps the plan credible for one engineer without pretending that the entire 80-hour scope is certain.

**VI:** 80 giờ là tổng đúng, nhưng chưa phải dự báo chắc chắn. Nếu ngày17 chưa có repair thật thì cần cắt feature trước khi quay video hoặc làm thêm UI. Pilot giảm trước khi chạy được; bỏ task fail sau khi chạy thì làm sai kết quả.

## Checks that passed

| Area | Review conclusion |
|---|---|
| Deadline/time zones | Oct30 10:00 PDT =17:00 UTC =Oct31 00:00 Vietnam. Dec15 noon PST =Dec16 03:00 Vietnam. Jan11 noon PST =Jan12 03:00 Vietnam. Schedule agrees with retained rules audit. |
| Sponsor condition | Actual NVIDIA runtime inference through Token Factory, or relevant AI Cloud execution, remains required. Docs correctly separate inference API from guarded code execution and do not imply self-hosted GPUs are mandatory. |
| Submission requirements | Ledger covers registration, eligibility/rights, actual coding behavior, sponsor use, functioning URL/test build, public licensed source, setup instructions, public YouTube, English materials, feedback, significant in-period updates, free judging access, track fields and optional prize conditions. |
| Video | Plan chooses2:40 and “under3 minutes,” conservatively satisfying the audit's “at most3 minutes.” Recorded real generation is distinguished from scripted fixtures and accelerated footage. |
| License/legal limits | Apache2.0 is proposed for owned product code, not guaranteed applicable to all material. Third-party licenses/notices and model artifact distinctions are retained; no weights redistribution or personal eligibility guarantee is asserted. Detailed eligibility exclusions/support ambiguity remain linked in the rules audit. |
| Defaults | [Contract defaults](../../service/contracts.py#L157) retain patch slots2. An explicit patch slot1 is valid; no new schema profile name is required. |
| Billing math | P1000/C200/O100 at $1/$0.25/$3 per million equals $0.00115=1150 micro-USD. Cache normalization and reasoning-as-subset agree with [current parser](../../service/providers.py#L179). Integer ceiling reservation has correct units. |
| Bound limits | Docs correctly require source-backed enforceable input/output limits and explicitly leave `max_tokens` reasoning enforcement pending live conformance. Request bytes are not misrepresented as tokenizer counts. An observed cap sample alone must not become a universal enforcement guarantee. |
| Final verification | Docs distinguish developer feedback from authoritative final receipts, preserve exact tree/environment identity, retain issue-tracker grader restrictions, and require a separately supported external check recipe. A finite check set is not presented as universal proof. |
| Recovery | Clean committed checkpoint continuation differs from advanced/ambiguous dispatch; replacement needs retirement and fresh authority, and uncertain charges stay retained. |
| Pilot inference | Same model/resources, frozen assignments, all-run denominator, failures/Unknowns, disjoint interruption strata, calibration separation and descriptive small-sample limits are explicit. No manufactured human acceptance receipts or benchmark label. |
| Mastery and evidence | AI delivery, mock protocol tests, synthetic fixtures, live model ability, hardware measurements and human learning evidence stay separate. H0 remains the learning entry point. |

## Current-source alignment notes

The landed provider implementation means S0 is no longer simply absent. Its results need the separate implementation verification record and code review before G0 is marked complete. Existing research source anchors should retain their inspected date and be described as historical where code moved. The current source still has the fixture-only ReferenceEngine, a specialized Linux verifier and no general live repository runner; the plans accurately keep those next-slice gaps open.

Optional usage `total_tokens` is validated if present in [source](../../service/providers.py#L191) and in the current protocol contract. The earlier research table's terse “total must equal” can be read more strictly; preserve the historical note but explicitly identify the selected implementation contract as prompt/completion required, total optional-and-consistent. This is a documentation precision issue, not evidence of live provider conformance.

Only this review document was changed. Findings were sent to the parent for correction; this record describes the inspected version, and a later resolution section should identify any repaired findings rather than implying they never existed.

## Coordinator resolutions after review

On October10 the coordinator corrected the S0 contract to global-only, separated required product release gates from conditional restart/pilot gates, added an October17 exercised free-access decision, and defined a shared outer spending meter plus explicit B0/D1 restart semantics at a common known-tool-result boundary. The exact owner tuple now includes tenant. October17 failure to obtain a real repair removes optional claims before release work. Original findings above remain as the review history; the final documents contain the corrected choices. Current mock-only source limitations are explicitly retained in the protocol contract.
