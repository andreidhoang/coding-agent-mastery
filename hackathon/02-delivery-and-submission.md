# Hackathon delivery and submission requirements

Team: Huy with Codex GPT and Gemini. Active instruction supersedes the earlier four-hour/80-hour estimate: build continuously by tested acceptance gates without a daily-time limit. The dates below remain scope-control checkpoints before submission. Live calls are enabled for the hackathon path by [D042](../context/decision-log.md#d042-live-execution-enabled-for-the-hackathon-path) within a frozen ceiling (proposed default $5 per task, $300 total through Dec 16, including judge access); the hosting budget remains unset. Local implementation proceeds; spending-dependent experiments require an actual ceiling and configured account.

## Mandatory requirements ledger

The [overview](https://nebiusglobalaihackathon.devpost.com/) establishes the package; [rules](https://nebiusglobalaihackathon.devpost.com/rules) establish eligibility, rights, timing and access; [FAQ](https://nebiusglobalaihackathon.devpost.com/details/faqs) resolves the sponsor runtime condition. Full facts and conflicts live in the [rules audit](../research/hackathon-2026-10-10/rules-audit.md). Every row below needs concrete release evidence, not merely a planned feature.

| ID | Requirement | Owner and release evidence | Current disposition |
|---|---|---|---|
| HR01 | Register and submit required fields before cutoff | Huy: Devpost registration and final submitted status | Not performed in this session |
| HR02 | Eligible entrant/representative and original contribution with rights | Huy: entrant details and third-party inventory | Eligibility/rights need human facts |
| HR03 | Coding-track fit: write, run and test code | Runner: genuine issue-to-edit-to-test trace | Supported runner measured with mock proposals and real Docker; actual NVIDIA generation still pending |
| HR04 | Nebius runtime/compute plus NVIDIA open model | Gateway: actual model request/response IDs, served model and usage evidence | Mock protocol work cannot satisfy this |
| HR05 | Consistent working project | Release: clean-install reproduction with pinned dependencies | Current rc4 passed full independent fresh-venv installed acceptance on the same Mac; October10 retains two historical runs; fresh-machine and judge access still pending |
| HR06 | Working demo, hosted app or test-build URL | Release: accessible functioning version and tested judge instructions | Missing |
| HR07 | Public GitHub/GitLab/Bitbucket repository | Release: all required product source/assets available anonymously | Workspace has private local Git history since 2026-10-15 (rollback only, never pushed); the public repository is still created from the generated source snapshot |
| HR08 | Detectable open-source license | Huy/release: chosen license file plus third-party notices | Huy chose Apache-2.0 on 2026-10-15; unpublished source candidate contains Apache2.0 terms/NOTICE; final rights review and public license detection pending |
| HR09 | Setup/run README and sponsor/model explanation | Release: fresh-machine instructions and exact supported scope | English product README/offline commands shipped in the current candidate; installed behavior and extracted-source rebuild checked; fresh-machine/live reproduction pending |
| HR10 | Public YouTube demonstration under three minutes | Huy: public URL tested logged out, runtime 2:40 target | Not recorded |
| HR11 | English project description, test instructions and media or translation | Release: problem, audience, actual behavior, implementation and limits | [Drafts](07-g5-submission-drafts.md) since 2026-10-15 with G1/G2 slots open; not submitted |
| HR12 | Technology feedback | Huy: concrete actual-use observations for relevant Nebius/NVIDIA tools | Gather during conformance/build |
| HR13 | Significant-update statement if pre-August26 work was reused | Release: provenance baseline and in-period change list | Audit older lab/assets; do not assume all source dates |
| HR14 | Free unrestricted judge access through December15 noon PST | Release: functioning build/service, test credentials if private, cost plan | Must fund/maintain through Dec16 03:00 Vietnam. Judges are not required to test and may judge only from the description, images and video (rules, checked 2026-10-15), so HR10/HR11 carry the score for any judge who does not test |
| HR15 | Video/IP permissions and OSS compliance | Huy/release: content permissions and relevant notices | Include in curated release review |
| HR16 | Complete track and Built With fields | Huy: Coding and Agentic Engineering; actual NVIDIA model and Nebius usage | Fill at submission |
| HR17 | Prize-specific eligibility if pursued | Huy: actual Tavily runtime call or required city attendance | Optional; adds no core product gate |

**VI:** Mandatory là điều kiện dự thi, không phải lời hứa “sẽ làm”. Một mock response hoặc link repo private chưa đạt HR04/HR07. Không cần tự thuê GPU chỉ để đủ sponsor requirement nếu model NVIDIA được gọi qua Token Factory đúng đường chạy sản phẩm.

## Scoring plan

Official guidance scores each dimension 1–5 with equal weight; technical implementation wins the first tie-break, followed by design, impact and idea. [Judging update](https://nebiusglobalaihackathon.devpost.com/updates/46204-here-s-how-judging-works), [rules section6](https://nebiusglobalaihackathon.devpost.com/rules).

| Dimension | Our evidence | Weak result that should trigger a change |
|---|---|---|
| Technological implementation | Real NVIDIA/Nebius repair; actual test loop; exact verification; supported restart; frozen costs | Beautiful trace over oracle-supplied edits only |
| Design | Brief task -> ceiling -> progress -> diff/evidence -> download experience | Judge must operate databases or read runtime internals |
| Potential impact | Specific Python maintainer task; verified result; observed review usefulness/time if measured | Claims about all developers or invented adoption |
| Quality of idea | Useful repair plus evidence surviving interruption; documented alternatives and tradeoffs | Durability shown without an actual repair or user decision |

Winning strategy is to remove obvious evidence gaps across all four dimensions. It is not valid to optimize a numeric internal score and treat that as the probability of first place. A coherent smaller product can compete more credibly than an unfinished general platform; this is our engineering judgment, not an organizer guarantee.

**VI:** Vì bốn tiêu chí ngang nhau, dùng hết thời gian làm runtime rồi bỏ UI/video sẽ bỏ nhiều điểm. Nhưng đẹp cũng không bù cho agent chưa tự sửa được lỗi. Ta phải tạo evidence nhìn thấy được cho từng tiêu chí.

## Calendar and acceptance checkpoints

Gate dates are owned by the owner's private MENTOR_GUIDE §0 (not in this repository): surge targets G1 Oct 15, G2 Oct 20, G5 ready Oct 28, submit Oct 29 12:00 ICT; D044 backstops Oct 16, Oct 22, Oct 29 18:00; official close Oct 31 00:00 ICT. The table and the October 17/26 checkpoints below keep their scope-control content. MENTOR_GUIDE §0 governs their dates and §7.3 their order: G1 → G2 → G5, with G3/G4 competitive extensions only after G5.

| Vietnam dates | Gate | Concrete output and exit gate |
|---|---:|---|
| Oct10–12 | G0 and local source | Source/rules audit, scope, protocol/harness and supported repair reference |
| Oct13–17 | G1 and live G2 | Actual provider conformance and supported NVIDIA-generated repair; free-access route exercised |
| Oct18–20 | G3 (only after G5; MENTOR_GUIDE §7.3) and user inspection | Supported clean restart already measured locally; inspect live evidence and useful workflow |
| Oct21–23 | Product usability | Downloadable verified diff, saved replay and maintainer walk-through |
| Oct24–26 | G4 (only after G5; MENTOR_GUIDE §7.3) | Frozen paired pilot, all-outcome report, controls and reproduction |
| Oct27–28 | G5 | Curated source/license/readme, accessible release, video and honest feedback |
| Oct29 | Submission | Logged-out link checks, Devpost fields, submit by18:00 |
| Oct30 | Contingency | Submission corrections within permitted period; no planned feature work |

Implementation advances continuously as contracts/tests pass. Critical path: **account conformance -> live repair evidence -> independent verification -> accessible release -> video -> submitted entry**. Provider/local reference work can run in parallel with account preparation. If account access is unresolved by October13, choose an officially supported account/AI Cloud route with an approved budget or escalate to Nebius through the organizer channel; another inference provider alone cannot substitute.

**Verifier receipt inside G2 and G5 (2026-10-14; not a G3/G4 extra; must not delay G1 → G2 → G5).** G2's verifier acceptance records a receipt card: verdicts on the three controls (correct, unchanged, plausible-wrong); 3–5 forgery attempts from the stated threat model (editing a protected check, authoring the verdict, for example printing PASS or exiting 0, and submitting a stale tree); false-accept and false-reject counts; CPU/memory request and limit, timeouts and concurrency logged with every score (Anthropic measured 6-point swings from resource configuration). G5's README carries Huy's note: what the verifier caught and missed, and the cost per verified fix with every failure in the denominator, plus the first live G1/G2 failure written as an incident record (symptom; the observation that separated host, provider, library and own code; fix or open gate; author), the form of ladders PLAN §6's J2. Consumer: judges, maintainers of small Python services, D045 clients and Code RL reviewers. Cost: controls offline at $0, live runs inside D042's ceiling. Cannot prove: more than a descriptive pilot, arbitrary repositories, hostile-code containment or any RL result.

On October17 inspect the first actual repair: if G1/G2 are not met, reassign restart and pilot time to the repair path and remove their product promises. The judge-access path must be exercised by the same date, rather than left to packaging week.

If required live gates are delayed, cut the second model, broad repository support and comparative pilot before the complete repair/access/submission path. Add a second authorized real task/repository before a second worker. Freeze product behavior by October26; preserve the exact submitted version afterwards rather than using the November gap as unsubmitted development time.

**VI:** Không còn quota giờ mỗi ngày. Calendar giữ các điểm kiểm tra trước deadline: nếu live gate trễ thì cắt scope tùy chọn, không cắt sponsor call, independent checks hoặc phần nộp. Làm liên tục vẫn cần evidence sau mỗi slice.

## Collaboration without integration drift

Huy owns scope, account, permitted spending, task permissions, useful-product decisions and final submission. Codex Astra owns architecture/research and independent review; 6.1 Sol owns bounded implementation. Gemini can independently inspect a failure or critique a draft/video; it has not been contacted or run in this session. Give each coding agent an input revision, write paths, contracts, acceptance test and stop condition. Root integrates only after checking artifacts/source, rather than trusting completion messages.

Parallelize independent research, test design and bounded files. Avoid two agents changing the harness together. Each delivered slice needs an exact source digest or commit, test environment and result record. Keep negative results. Human learning evidence remains separate; an AI review does not become Huy's teach-back or an independent human reproduction.

## Cost and judging access

Resources advertise $25 promotional Token Factory credit and another $25 through the Builders Program. Actual allocation and expiry must be checked; these credits are not an approved project spending limit or a general AI Cloud grant. [Resources](https://nebiusglobalaihackathon.devpost.com/resources), [credit FAQ](https://nebiusglobalaihackathon.devpost.com/details/faqs).

Live execution is enabled within D042's frozen ceiling. Within it, reserve essential provider conformance, useful repair, demo and free judging access first, including an incident reserve. Allocate any surplus to the optional matched pilot only after measured calibration and access costs; the earlier illustrative percentage split is superseded. Credits expiring before December cannot fund December judging. A bounded test build can avoid continuous hosting but must be usable free of charge by judges, with its supported credentials/inference path and install burden honestly explained. Never put our server key in a public repository or rely on judges to purchase access.

By October17 choose and exercise one judge-access path: either a funded hosted gateway with service-held credentials and task quotas, or a downloadable test build with a funded restricted gateway/credential path supplied privately in judge instructions. Do not release a BYO-paid-key build as free judging access. If the source-only path cannot satisfy this, reserve hosted access costs and cut optional work. A saved replay demonstrates evidence but is not a replacement for a functioning test build.

Approve a maximum per-run bound before dispatch; request budgets, task budgets and global gateway limit enforce spending. Dashboard settled cost alone is insufficient: unresolved liability and unspent reserved allowance also occupy capacity. Billing reconciliation cannot grant permission to rerun an uncertain tool effect.

**VI:** Credit hết không nhất thiết làm provider tự dừng mọi khoản charge. Ta kiểm soát bằng ledger và ceiling của chính hệ thống. Chi phí tháng12 là requirement thực tế; video là bằng chứng nhưng không thay được free judging access.

## Release structure

Publish a curated product repository rather than the entire learning workspace. Include product source, required supported tasks/tests, lockfile, release commands, sample configuration without secrets, architecture and limitations, selected open-source license and third-party notices. Exclude personal study/context, credentials, paid raw transcripts, unrelated projects, oracle patches accessible to workers, and unnecessary third-party source snapshots. Preserve all original material locally.

Since 2026-10-15 the primary workspace has private, never-pushed local Git history for rollback and bisection; it still has no product root license. An unpublished generated source snapshot contains a product README, Apache2.0 license candidate, NOTICE and per-file hashes; its [verification](../research/hackathon-2026-10-10/repair-delivery-verification.json) records the scope and subsequent unrelated source changes. Begin provenance/version control and refresh the reviewed curated distribution before publishing. Proposed Apache2.0 terms apply to owned product code; third-party material keeps its own license. Do not relabel the preserved Codex reference or NVIDIA weights under the product license. We use hosted inference and do not redistribute weights in the initial submission.

The [current offline candidate](../releases/README.md) is governed by the [October11 readiness and installed-acceptance evidence](../research/system-readiness-verification-2026-10-11.json). The [October10 source/artifact-bound evidence](../research/offline-release-verification-2026-10-10.json) retains its historical subset: same-machine isolated venvs, original hash-checked base wheels, repair/restart, exact patch and read-only report replay. Separately online dependency preparation is explicit. Public access, actual sponsor use, rendered browser QA and a genuinely fresh machine remain pending; no G5 completion is inferred.

Clean-install acceptance: pinned supported Python version; locked install; G0 tests; explicit supported test recipe; smoke demo; diff application reproduces candidate digest; downloaded report opens; live provider config remains server-held; documented limitations match the recorded video. Release evidence names OS/image, source revision and exact model. Public upload/registration/submission should follow a reviewable completed release, not an unfinished directory.

**VI:** Workspace học có tài liệu cá nhân và source tham khảo với quyền khác nhau. Curated repo giữ đúng phần sản phẩm để judge chạy được, không cần upload toàn bộ Desktop. License của code mình viết không tự thay license của dependencies hoặc model.

## Demonstration storyboard

Target runtime **2:40**, below the strict three-minute limit. All external submission material is English. The following is a shot plan; insert measured outcomes only after they exist.

| Time | Show and say |
|---|---|
| 0:00–0:20 | A maintainer's concrete bug and failing behavior; name the audience and review problem |
| 0:20–0:35 | Submit issue and ceiling; identify NVIDIA Nemotron model and Nebius Token Factory audibly |
| 0:35–1:15 | Real read/edit/test loop; show one relevant test failure and generated diff, not a long terminal scroll |
| 1:15–1:45 | Interrupt at the supported committed checkpoint, restart with preserved evidence; label replay if playback is recorded |
| 1:45–2:15 | Final independent verification of the exact tree; downloadable diff, settled/unknown costs and pending human review |
| 2:15–2:40 | One measured comparison if available, practical scope, and repository/demo links |

If supported recovery misses its gate, show the completed repair clearly and disclose restart limits. Never stage a scripted run as live generation or omit infrastructure failures to manufacture success. A genuine prerecorded live run may illustrate functionality; label any accelerated footage. Judge clarity is more valuable than displaying every internal component. [Organizer submission tips](https://nebiusglobalaihackathon.devpost.com/updates/46205-how-to-build-a-winning-project).

Technology feedback record: tool/model and task; onboarding steps/time observed; what worked; reproducible problem with request ID/date and sanitized snippet; workaround; impact on the product; whether and why we would reuse it. Documentation conflicts already found are research observations; verify their actual effect before presenting them as experienced provider failures.

## Final submission checks

Reopen current rules/updates before submitting. Verify public repo/license detection and clean-run instructions, actual functioning demo/test build, video visibility/runtime/audio, English materials, correct track, sponsor/model names, feedback, provenance changes, rights and judging access. Test links outside the signed-in session. Verify Devpost indicates submitted, not merely saved draft. Keep a frozen release identity and saved evidence of submission status; proof of attempted upload is not proof of accepted entry. City eligibility remains ambiguous across organizer pages; do not claim attendance we did not have.


## Current release boundary — 2026-10-11

Consult [the release index](../releases/README.md) for the new readiness candidate's exact installed evidence and the preserved October10 candidate. Current source adds skills recovery/service/journal/probe checks without adding required hackathon features. Same-machine offline installation with mocked inference remains only part of G5. Actual sponsor conformance, useful live repair, fresh-machine/public judge access, source/license/video and submission evidence stay open; no paid execution is authorized.

The [offline qualification delivery](../ops/runbooks/provider-qualification.md) supports G1/G2 preparation without completing either live gate. Its source-bound handoff certifies one unstarted repair snapshot only; it cannot enable inference or judge access. [Current verification](../research/provider-qualification-verification-2026-10-11.json) and [rc4](../releases/README.md) supersede earlier current-candidate wording while preserving historical runs.
