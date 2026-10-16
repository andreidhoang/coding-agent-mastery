# Research engineering and learning through the current reference

Date: **2026-10-11**. Purpose: connect Huy's ambition to an efficient, inspectable engineering and
learning process. The near-term product is the supported NVIDIA/Nebius coding repair entry; the
long-term capability is independently explaining, evaluating, improving and operating agentic
systems. Use [readiness](system-readiness-plan-2026-10-11.md) for engineering evidence and the
[mastery tracker](../docs/05-mastery-tracker.md) for Huy's demonstrated understanding.

The principal conclusion is to make the next consequential unknown explicit. Additional general
infrastructure is not the current proof of useful repair. The local reference has substantial
recorded checks; live NVIDIA/Nebius repair quality, usable judging access and operated production
remain separate gates. Paid execution remains disabled. Learning continues through the built
reference without claiming mastery from its test results.

**VI:** Tầm nhìn là em có thể nhìn một hệ thống mới, tìm đúng boundary, dựng giả thuyết, thiết kế
thí nghiệm và giải thích kết quả. Capstone cho ta vật thể thật để luyện năng lực đó. Mỗi task phải
mở khóa một câu hỏi hoặc giá trị cụ thể; không chạy theo số lượng file hay framework.

## What public frontier practice establishes

OpenAI's January 2026 account describes daily engineering use of Codex for understanding code,
refactoring, tests, performance work and incidents. Its February harness report describes one
team shifting effort toward environments, constraints and feedback for agent-written code. These
are reported practices, not a measurable definition of the top 1% or access to private calendars.
[Engineering usage](https://openai.com/business/guides-and-resources/how-openai-uses-codex/),
[harness report](https://openai.com/index/harness-engineering/).

**VI:** Chuẩn đáng học là cách đặt vấn đề, quan sát và kiểm chứng. Không cần giả vờ có chức danh
ở một lab để áp dụng chuẩn đó. Kết quả của team khác là nguồn giả thuyết, chưa phải kết quả của ta.

Anthropic's agent evaluation guidance separates what the transcript says from what changed in
the environment. NVIDIA's September 2026 evaluation guidance likewise distinguishes step-level
diagnostics from task outcomes. OpenAI's September 2026 harness evaluation shows why direct tool
tests and a standalone model loop cannot stand in for the actual product harness.
[Anthropic](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents),
[NVIDIA](https://developer.nvidia.com/blog/how-to-evaluate-ai-agents-from-tool-calls-to-task-completion/),
[OpenAI](https://developers.openai.com/cookbook/examples/partners/harness_aware_plugin_evals/harness_aware_plugin_evals).

**VI:** Model nói “xong” là một message. File đúng, test độc lập pass đúng tree, chi phí được ghi
nhận và reviewer chấp nhận là các sự kiện khác nhau. Ta cần evidence ở đúng tầng đang tuyên bố.

For deployment, NVIDIA's AI-Q account describes profiling individual workflows, checking quality,
load testing and observing rollout. Its title does not establish a measured 1,000-user deployment.
For GPU work, Nsight Compute may serialize launches during profiling; a kernel measurement and a
normal concurrent application measurement answer different questions.
[Deployment account, August 2025](https://developer.nvidia.com/blog/how-to-scale-your-langgraph-agents-in-production-from-a-single-user-to-1000-coworkers/),
[profiling guide](https://docs.nvidia.com/nsight-compute/ProfilingGuide/).

**VI:** Tối ưu thứ nhanh nhất để đo có thể không tối ưu thứ đang làm người dùng chờ. Ta đo workload
toàn hệ thống trước, rồi mới đi sâu vào component gây bottleneck. CPU correctness không đo GPU speed.

Anthropic's January 2026 randomized study of 52 developers learning an unfamiliar library found
lower immediate quiz scores with AI assistance: 50% versus 67%. Its short task, small sample and
qualitative interaction patterns do not settle long-term learning or prove our build-first
sequence. They justify measuring understanding separately from completion.
[Study](https://www.anthropic.com/research/AI-assistance-coding-skills).

**VI:** AI viết code trước không tự làm em mất tư duy, nhưng đọc lời giải thấy hợp lý cũng chưa
chứng minh hiểu. Ta kiểm tra bằng dự đoán chưa xem đáp án, giải thích lỗi và xử lý một case đổi điều kiện.

The full dated source-to-practice map lives in the updated
[mentor skill reference — local-only](../docs/github-snapshot.md#omitted-local-evidence).
Jensen Huang's “How hard can it be?” is verified in the original
[March 2026 interview at 01:41:53](https://lexfridman.com/jensen-huang-transcript/).
We use it as permission to begin reasoning: define the next small test, learn from the result,
and reconsider assumptions. It cannot guarantee that we never get stuck.

## Audit of the active plans

This audit read the current state, H0 packet, H0–H15 learning plan/tracker, capstone chapters 01–08,
hackathon packet and readiness dependency/evidence plan. It evaluates their
alignment and selected current source; it is not a new full-code security review or test run.

| Track | Actual position | Next decision and value |
|---|---|---|
| Hackathon product | Local supported function repair, exact provider mocks, protected verification and release evidence exist. | Prepare one concrete conformance/repair trial and judge-access contract offline. Actual quality/access need their later authorization and observations. |
| Durable agent reference | Ownership, accounting, skills recovery, local environment reconciliation and offline fixture service are recorded as delivered within their contracts. | Select new code only for a specific unmet outcome. Cleanup of a container does not authorize replay or settle an unknown bill. |
| Human learning | H0 remains not demonstrated. | Trace one unseen effect/receipt failure, then transfer to a remote tool. This builds the judgment needed to review agent output. |
| NVIDIA specialization | CPU RMSNorm reference and a trusted authored qualification probe are prepared. | Generated GPU execution still needs NV-S1 isolation/lifetime mechanisms; actual hardware qualification is separate. Keep it out of the API-only hackathon critical path. |
| Production operations | Local installed acceptance exists. | A declared live workload/threat/SLO envelope must precede claims about containment, restore, load, canary or rollback. |

**VI:** Có hai kiểu ô trống: thiếu code và thiếu phép đo. Không thể thuê GPU để bù cho code
isolation chưa có; cũng không thể viết thêm test mock để tạo ra kết quả model thật. Chọn đúng loại
việc cần làm giúp tiết kiệm thời gian hơn việc cố làm mọi thứ cùng lúc.

Reconciled active navigation: removed tracker/runtime/evaluation wording that required human
learning before implementation; marked old effort ranges as historical; pointed current audit/release navigation
to October11 evidence; distinguished delivered optional skills from default repair; added a dated
pointer after the frozen initial Nebius contract. Historical results, workload assets and human
mastery states remain preserved. Essential access and useful repair take precedence over the
previous illustrative percentage allocation to an optional pilot.

## The repeatable working cycle

This is our proposed operating method, derived from the evidence above rather than attributed to
a company's private schedule. It has no daily-hour quota.

1. **Frame:** name the user outcome, why this component matters, present constraints and one
   decision to unlock. Example: can interruption preserve liability without repeating a tool?
2. **Specify:** name inputs/outputs, owner, invariant, source, plausible failure and distinguishing
   experiment. Separate a mathematical fact from a systems assumption.
3. **Delegate:** one agent implements a bounded slice; another checks the contract independently;
   one integration owner reconciles evidence. Huy keeps one deep-work topic.
4. **Trace:** follow one object or element through actual code with full tiny values. Use an
   ownership timeline for effects and a shape/layout table for tensors.
5. **Decide:** compare prediction and observation. Keep, change or reject the design. Include failed
   attempts in the result. Stop repeating work once it no longer changes the decision.
6. **Transfer:** when studying, Huy explains a changed case without copying the answer. Record
   reasoning and hints honestly in the existing session; do not invent a completed exercise.

**VI:** “How hard can it be?” trở thành hành động: bài toán lớn → một cơ chế → một invariant →
một thí nghiệm phân biệt. Nếu vẫn bí, đổi biểu diễn từ prose sang số, timeline hoặc executable
reference. Nếu thiếu prerequisite, học đúng mắt xích đó rồi quay lại, không mở thêm cả khóa học.

Prefer the task that unlocks a required result or removes the largest consequential uncertainty
per scarce human attention. Do not invent probabilities to manufacture a priority score. Agents
can prepare independent tests/docs while a resource is unavailable. Hardware time, agent time,
human attention and elapsed waiting are separate quantities. Essential conformance, repair and
judging access precede optional scaling pilots; unknown prices remain unset.

## Exact trace A — an uncertain action keeps its liability

Purpose: prevent a retry from duplicating effects or spending capacity that may already be owed.
The code's budget equation at [RuntimeStore._budget](../service/storage.py#L380) is:

`reserved = sum(attempt allowance_remaining) + sum(unsettled dispatch bound_units)`

`spent = sum(settled dispatch actual_units)`

Tiny derived example, in abstract budget units rather than real currency:

| Transition | Allowance | Unsettled bound | Spent | Available under limit 100 | Physical slots |
|---|---:|---:|---:|---:|---:|
| Claim 40 | 40 | 0 | 0 | 60 | 1 |
| Dispatch bound 12 | 28 | 12 | 0 | 60 | 1 |
| Response lost, effect Unknown | 28 | 12 | 0 | 60 | 1 |
| Cancel authority | 28 | 12 | 0 | 60 | 1 |
| Confirm physical retirement | 0 | 12 | 0 | 88 | 0 |
| Trusted late actual charge 9 | 0 | 0 | 9 | 91 | 0 |
| Same receipt repeated | 0 | 0 | 9 | 91 | 0 |

Read [claim](../service/storage.py#L551), [dispatch](../service/storage.py#L718),
[receipt](../service/storage.py#L1056), [cancel](../service/storage.py#L1297) and
[retirement](../service/storage.py#L1537). The reserve moves from allowance into a dispatch;
it is not an extra 12 on top of 40. Cancellation changes authority. Retirement changes resource
occupancy. A trusted billing receipt changes financial knowledge. None alone proves the tool's
effect succeeded. The transfer exercise is to change a local edit into a remote issue creation
whose response is lost; the human answer is intentionally unfilled.

**VI:** Giống một khoản đã giữ chỗ để thanh toán: mất biên lai không có nghĩa cửa hàng chưa thu
tiền. Nhưng analogy dừng ở đây—hệ thống còn có owner token, transaction và physical slot; từng cái
cần evidence riêng. Em cần giải thích vì sao `28 + 12 = 40`, rồi áp dụng cho một effect khác.

## Exact trace B — from one tensor row to a performance decision

Purpose: establish the numerical meaning before judging a proposed kernel. The implemented
inference-only equation is `y[r,h] = x[r,h] * scale[h] / sqrt(mean_j(x[r,j]^2) + epsilon)`.
The [CPU oracle](../compute/rmsnorm.py#L85) uses Python-float accumulation; the
[eager path](../compute/rmsnorm.py#L99) uses FP32. They have an explicit elementwise tolerance at
[check_rmsnorm](../compute/rmsnorm.py#L124), not an assumed bitwise match.

For one real-arithmetic teaching row, take `x=[[1,2,2]]`, `scale=[1,-2,0.5]`, `epsilon=0.00001`.
Every input element is shown. Square: `[[1,4,4]]`; sum: `[[9]]`; mean: `[[3]]`; add epsilon:
`[[3.00001]]`; denominator: `[[sqrt(3.00001)]]`; normalize:
`[[1/sqrt(3.00001),2/sqrt(3.00001),2/sqrt(3.00001)]]`; scale:
`[[1/sqrt(3.00001),-4/sqrt(3.00001),1/sqrt(3.00001)]]`.
Shapes are `[1,3] -> [1,1] -> [1,3]`. A contiguous FP32 input has stride `(3,1)` in elements,
12 logical bytes, and element `(0,2)` starts 8 bytes after its base. The width-3 scale is
broadcast, not physically copied into another row by the equation. Logical bytes are not a
measured allocation peak or DRAM-traffic count.

**VI:** Chia cho 3 là bước giữ ý nghĩa “mean”; bỏ nó sẽ đổi denominator. `epsilon` nằm trong căn
để ổn định row gần 0; chuyển ra ngoài có thể trông hợp lý với số lớn nhưng sai rõ ở số nhỏ. Vì thế
fixture hiện tại có cả row `[1,2,2]` và một row nhỏ hơn để phân biệt hai implementation.

The interactive trace derives both fixture rows after FP32 input conversion and labels its
subsequent arithmetic FP64 visualization arithmetic. It is not a new Torch measurement. The
[counterexample fixture](../compute/rmsnorm.py#L180) contains omitted-scale, tail, reduction and
epsilon-placement controls. Trace this layer only when selected; H0 remains the current lesson.

Production relevance depends on the consumer. For a **toy** workload where this operation consumes
10% of end-to-end time, a 2x speedup with everything else fixed yields
`1 / (0.9 + 0.1/2) = 1.0526x`, about a 5.26% throughput improvement for that simple serial model.
The 10% fraction is hypothetical, not a measured bottleneck here. Actual serving also needs
quality, workload, batch/sequence shape, synchronization, warmup, variance and resource evidence.

**VI:** Kernel nhanh gấp đôi chưa chắc ứng dụng nhanh gấp đôi. Đầu tiên phải biết nó chiếm bao
nhiêu thời gian của consumer thật. Phép tính nhỏ này giúp quyết định có đáng đầu tư vào kernel
hay nên sửa bottleneck ở tool, queue hoặc network trước.

## Immediate continuation

For Huy: one unseen H0 trace, an explicit prediction, source inspection, then one changed remote
effect or stale-verification case. For agents: prepare the required live-conformance/repair and
judge-access packets offline using the existing runtime; leave unavailable account/model/rate
inputs unset. No new curriculum, duplicate runtime or human mastery credit is created by this audit.

**VI:** Mục tiêu gần là em tự giải thích được một boundary quan trọng và đưa ra quyết định có lý
do. Mục tiêu sản phẩm gần là phép thử repair thật có contract rõ, sẵn sàng khi execution được cho
phép. Hai tiến độ hỗ trợ nhau nhưng không giả làm bằng chứng cho nhau.
