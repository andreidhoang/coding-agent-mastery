# NVIDIA Nebius coding agent submission plan

Prepared **2026-10-10**, Vietnam time. Team confirmed by Huy: one human engineer, assisted by Codex GPT and Gemini. Huy supersedes the four-hour/day estimate: build continuously by acceptance gates without a daily-time limit. Actual Nebius credits, account availability and spending limit remain unset. This is a focused delivery profile of the existing coding-agent capstone; it preserves H0–H15, the broader role contract and the capstone's two-worker default.

Build a **verified repository repair tool** for maintainers of small Python services. A frozen issue and repository snapshot produce a generated diff, independently checked exact-tree evidence, a cost ledger and an inspectable execution history. Start with one live worker and one supported repository recipe. Add a clean-checkpoint restart only after repair works. Competitive differentiation is a hypothesis: useful repair with trustworthy evidence across interruption. First place is a target, not a result that architecture can guarantee.

**VI:** Ta dùng capstone làm nền, nhưng hackathon có deadline và người dùng cụ thể. Điều cần chứng minh là một lỗi thật được model NVIDIA sửa qua Nebius, test đúng bytes và bàn giao rõ ràng. Không lấy số lượng agent hoặc test runtime làm proxy cho chất lượng sửa code.

## Deadlines and entry conditions

Official submission closes **2026-10-30 10:00 PDT = 2026-10-30 17:00 UTC = 2026-10-31 00:00 Vietnam**. Internal target: submit by **October 29 at 18:00 Vietnam**, leaving 30 hours for submission issues. Judging ends December 15 at noon PST, or December 16 at 03:00 Vietnam; keep judging access available until then. Winners are expected around January 11, 2027 at noon PST. [Official schedule](https://nebiusglobalaihackathon.devpost.com/details/dates).

The mandatory sponsor path is a runtime call to Nebius Token Factory, or execution on Nebius AI Cloud, using at least one NVIDIA open model. The rest of the application can be hosted elsewhere. For this product use Nemotron through Token Factory in the actual repair loop. [Organizer FAQ](https://nebiusglobalaihackathon.devpost.com/details/faqs).

The required package is a working project/demo or test-build URL, English description and track selection, public licensed source with setup README, public YouTube demonstration under three minutes, and technology feedback. Explain significant in-period changes if any project existed before August 26. See the [complete rules audit](../research/hackathon-2026-10-10/rules-audit.md), including eligibility, rights, prize combinations, free judging access and official-page conflicts.

The **overall Grand Prize is $20,000**; the **Coding and Agentic Engineering track prize is a Jetson Orin Nano**. The four scoring dimensions are equally weighted. The organizer's coding guidance emphasizes planning, editing, testing and iteration on real repositories with limited intervention. [Judging guidance](https://nebiusglobalaihackathon.devpost.com/updates/46204-here-s-how-judging-works), [prize guidance](https://nebiusglobalaihackathon.devpost.com/updates/46206-did-someone-say-prizes).

**VI:** Midnight thuộc ngày 31/10, nhưng lịch làm việc phải coi tối 29/10 là hạn nội bộ. Demo còn phải dùng được trong kỳ chấm tháng 12; hết credit cuối tháng 10 là rủi ro vận hành thật. Giải toàn cuộc thi và giải track là hai hạng khác nhau.

## Read and execute in this order

1. [Product and system design](01-product-and-system-design.md): audience, scope, owners, invariants, exact state trace and component acceptance.
2. [Delivery and submission](02-delivery-and-submission.md): requirements ledger, dates, acceptance checkpoints, release gates and demonstration script.
3. [Foundations and evaluation](03-foundations-and-evaluation.md): model/tool mechanics, cost/latency derivations, matched experiments and H0–H15 study map.
4. [Nebius implementation contract](00-nebius-protocol-contract.md): the immediate protocol/harness slice before live repository work.
5. [Execution specification](04-execution-specification.md) and [local runbook](05-local-repair-runbook.md): delivered source, reproducible supported repair/restart and remaining live/release gates.
6. [HTTP error evidence contract](06-http-error-evidence-contract.md): delivered/reviewed bounded provider hardening, preserving diagnostics without tool authority or inferred zero charge.

Evidence: [official-rule audit](../research/hackathon-2026-10-10/rules-audit.md), [inspected architecture audit](../research/hackathon-2026-10-10/architecture-audit.md), [provider and research audit](../research/hackathon-2026-10-10/provider-and-research.md). The coverage register and dated test records remain authoritative for the existing reference. New implementation evidence belongs to the separate hackathon verification record.

## Decisions and release gates

| Decision | Reason | Condition for changing it |
|---|---|---|
| One worker in the hackathon flow | General live coding is the critical missing link | A second worker improves verified outcomes under the same total resource ceiling |
| Token Factory API inference | Satisfies the sponsor path while avoiding a GPU-serving project | Account access fails or a measured product requirement needs AI Cloud |
| Small Python repository recipe | Enables meaningful tests and bounded execution within the deadline | A second recipe has its own immutable checks and reproduction evidence |
| Super is the first calibration candidate | Documented reasoning/tool tier between small and largest models | Actual catalog, conformance, cost or task outcomes favor another NVIDIA model |
| One pinned model for first comparison | Isolates harness/recovery effects | Routing has separately measured benefit and full cross-model cost accounting |
| Public test build is a valid fallback | Rules accept a functioning test-build URL | A hosted service is reproducible and funded through judging |

Model choice is proposed, not enabled. Documented model IDs and inconsistent model/context/license claims are recorded in the provider audit. Do not treat catalog marketing, cached JSON or a generic API schema as proof of your account's tool protocol or price.

**VI:** Chọn Super để thử đầu tiên là quyết định engineering có thể đảo ngược, không phải kết luận nó tốt nhất. Freeze một model trước giúp biết cải tiến đến từ harness hay chỉ do đổi model đắt hơn.

| Gate | Evidence needed | Status at plan creation |
|---|---|---|
| G0 Protocol | Strict mock transport, native continuation, conservative billing and replay | Implemented and independently reviewed; [verification](../research/hackathon-2026-10-10/verification.json) |
| G1 Sponsor conformance | Actual account/model catalog, approved rates/bounds, live NVIDIA call through Nebius | Offline [qualification/handoff](../ops/runbooks/provider-qualification.md) implemented and installed; actual account/catalog/rates/live call still pending |
| G2 Useful repair | Oracle-free run on a supported issue, edit, worker test, exact independent verification and diff | Supported runner/recipe implemented; mock provider plus real Docker measured; live NVIDIA repair quality pending |
| G3 Supported restart | Process restart from clean committed checkpoint with new authority; ambiguous call stops safely | Implemented/measured across two local processes; optional journaled physical cleanup now exists; automatic task continuation remains unsupported |
| G4 Matched pilot | Frozen paired assignments, all outcomes/costs, failures included, limits stated | Competitive extension; descriptive actual-run evidence still required for any measured claim |
| G5 Submission readiness | Fresh-install reproduction, rights/license review, public source and demo/test build, public video, completed fields | [Current rc4](../releases/README.md) passed full independent installed acceptance on this Mac; October10 retains two historical runs; fresh-machine/public access/source/video, final rights review and actual sponsor use pending |

G1, G2 and G5 are essential for the intended functioning submission; G0 supports this implementation. G3 and the paired pilot in G4 are competitive extensions, not organizer prerequisites. If cut, remove their promises from the product/video and report the smaller demonstrated scope. No test count, AI-delivered code or research document marks Huy's mastery. The next learning entry remains H0; the engineering next step follows the first unsatisfied essential release gate.

## Delivered first slice

Native Nebius adapter/harness source, mock tests and [independent Astra review](../research/hackathon-2026-10-10/nebius-review.md) are complete. The review found and repaired documented nullable-field compatibility and a cache-rate admission assumption. Focused result:98 passed, including67 Nebius cases. Complete default suite:323 passed,17 explicit backend-integration skips,15 passing subtests; Ruff passed across service/tests. Dated [machine evidence](../research/hackathon-2026-10-10/verification.json) includes source hashes and JUnit. PostgreSQL/Docker/Temporal opted-in integration was not rerun for this slice; prior production evidence retains its own date/hashes.

The next sustained implementation delivered S1–S5 for the supported stateless Python function profile: source intake, provider approval, oracle-free runner, protected independent checks, exact downloadable diff, clean process restart and offline report. The [runbook](05-local-repair-runbook.md) and [independent review](../research/hackathon-2026-10-10/repair-independent-review.md) describe the scope and limits. [Source-bound delivery verification](../research/hackathon-2026-10-10/repair-delivery-verification.json) records real-Docker/restart delivery and phased checks. No live inference, authenticated catalog, arbitrary-repository capability or hosted deployment is claimed. The next essential external gate is G1 followed by live G2 evaluation; permitted spending/account evidence remain unset.

Subsequent HTTP error hardening is implemented and independently reviewed. [Dated HTTP delivery verification](../research/hackathon-2026-10-10/http-error-verification.json):662 default tests/156 subtests passed with24 backend skips;347 opted-in native/repair integration tests passed; package and locked assets validated. The suites overlap. Error evidence remains separate from tool/billing authority, including late reconciliation replay. Refreshed source/wheel artifacts are prepared locally, unpublished. Huy explicitly keeps paid execution disabled; G1/G2 live evidence remains pending until that instruction and required inputs change.

**VI:** G0 đã có code và evidence cụ thể. Muốn tới G2 phải có runner tự sửa từ issue/source, không đọc oracle; muốn nộp phải có model NVIDIA qua Nebius thật và free judge access. Test mock không thay các gate đó.

The later [shared codebase audit](../research/codebase-refactor-spec-2026-10-10.md) tightens the supervisor and provider boundaries reused here. [Current source verification](../research/codebase-review-verification-2026-10-10.json) is separate from the earlier unpublished source/wheel artifacts, which retain their dated identities. It does not advance live sponsor use, public access or submission gates.

The [bounded evidence-to-regression delivery](../research/failure-regression-spec-2026-10-10.md) adds local inspection of failed verification and Unknown dispatch under [separate source-bound verification](../research/failure-regression-verification-2026-10-10.json). It leaves the repair runner and provider gates unchanged. G1 sponsor conformance, live G2 repair and G5 public submission readiness remain the essential release path; paid execution stays disabled. Earlier wheel/source bundles retain their dated identities and were not rebuilt by this adapter delivery.

**Shared reference update, 2026-10-10:** [context offloading](../research/context-offloading-spec-2026-10-10.md) now has local mock-provider/SQLite/PostgreSQL evidence, while the supported repair profile retains its existing default behavior. This optional context path does not satisfy sponsor conformance, live repair, public release or free judge access. Current source checks do not refresh an older exported wheel/release automatically. Paid execution remains disabled; release/access preparation keeps priority.

**Current readiness work, 2026-10-11:** [the dependency/evidence plan](../research/system-readiness-plan-2026-10-11.md) adds optional typed skills recovery, configured local fixture serving, explicit Docker journaling/reconciliation and trusted GPU preparation. [The release index](../releases/README.md) separates the current installed candidate from preserved October10 artifacts. These remain supporting reference capabilities, not extra hackathon deliverables or evidence of NVIDIA live coding quality. The configured HTTP profile serves scripted fixtures; hosted repair admission still requires its own contract. Required G1/live G2/public G5 retain priority; paid execution stays disabled.

**Latest delivery, 2026-10-11:** [offline qualification](../ops/runbooks/provider-qualification.md) now freezes an unstarted repair, approval and service source identity; exercises two native mock turns through the existing harness/ledger; and derives an immutable report/advisory handoff. [Verification](../research/provider-qualification-verification-2026-10-11.json) and independently installed rc4 preserve failed/corrupted/Unknown controls. It does not fetch account/catalog data, establish prices, run repair or satisfy G1/G2. Required live conformance → useful repair → public submission gates retain priority; paid execution stays disabled.
