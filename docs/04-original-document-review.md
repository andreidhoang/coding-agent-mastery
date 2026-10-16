# Review of the original documents

Reviewed 2026-10-08. **Keep both originals as research references; use the new canonical documents for study and execution.** Their central thesis is sound: coding-agent capability depends on the model, tools, context, execution environment, verification and serving system together. The changes below repair specific overstatements and make the learning path executable. This was a selected fact-check of consequential claims, public product interfaces and source paths, not an exhaustive verification of every paragraph, citation or experiment.

**VI:** Giữ giá trị của tài liệu gốc nhưng không coi mọi câu đã được kiểm chứng. Bản mới ưu tiên cơ chế có thể trace và test, cùng nhãn bằng chứng rõ ràng.

## Preservation and authority

The two original Markdown files were moved into `archive/` without content edits, with clear names: [original mastery plan — local-only](github-snapshot.md#omitted-local-evidence) and [original harness research — local-only](github-snapshot.md#omitted-local-evidence). The pasted handoff was also preserved. All three archived files were rehashed during this review and matched [the preservation manifest — local-only](github-snapshot.md#omitted-local-evidence). Corrections live outside those originals, so their historical statements and line anchors remain inspectable.

The canonical learning sequence is the new [H0–H15 curriculum: 16 modules](02-mastery-learning-plan.md). The original **M0–M13** sequence and the code-research report's **H0–H13** sequence are historical inputs/proposals, not competing execution plans. Research reports supply evidence and rationale; canonical documents decide the study order. No module number should be copied between these sequences without checking its title.

**VI:** Archive là lịch sử nguyên vẹn; docs mới là đường học hiện tại. H0 trong một proposal không tự động là cùng bài với H0 trong chương trình chính.

## What to retain

The original [module contract — local-only](github-snapshot.md#omitted-local-evidence) connects a production incident, first-principles question, derivation, code reading and an experiment. This is stronger than a list of agent frameworks. Keep its emphasis on bounded observations, cancellation, context economics, clean evaluation and the serving/training connection. Also retain the [open-issues ledger — local-only](github-snapshot.md#omitted-local-evidence): exposing contradictions is useful scientific practice.

Several unfamiliar 2026 details survived primary-source checking. Opus 5.5 and Fable 5.1 are present in official documentation; the July 2026 MCP revision and model-specific preserved-thinking rules also have official support. Do not erase these as assumed hallucinations. Equally, verifying a model's existence does not validate every benchmark, internal architecture claim or account-specific availability statement about it. The [Claude Code/Cursor audit](../research/claude-code-cursor-evidence-2026-10-08.md#L17) records the precise findings and primary links.

**VI:** Tên mới cần kiểm tra, không phán đoán từ trí nhớ. “Model tồn tại” và “con số performance này đúng trong điều kiện mình cần” là hai câu hỏi riêng.

## Highest-priority corrections

**1. Separate recorded history, model context and KV state.** The original [state claim — local-only](github-snapshot.md#omitted-local-evidence) calls the harness the only owner of truth, while its [cache derivation — local-only](github-snapshot.md#omitted-local-evidence) treats byte identity as an if-and-only-if theorem. A log owns recorded facts; files and remote services can change independently. A prompt is a projection of history. Ordinary KV reuse requires compatible tokens, positions, weights/adapters, attention semantics and cache identity; a matching prefix does not guarantee residency or routing. Compaction can validly change the prompt while preserving the event ledger. [Detailed correction](../research/serving-evaluation-training-audit-2026-10-08.md#L24).

**VI:** Log là sổ cái; prompt là báo cáo lấy từ sổ; KV là kết quả tính của báo cáo. Ba lớp có invariant khác nhau.

**2. Fix protocol and completion semantics.** The original [tool-result explanation — local-only](github-snapshot.md#omitted-local-evidence) says missing a result makes the next conditional undefined. The mathematical distribution remains definable; the provider may reject the exchange because it violates its protocol. Keep one logical terminal outcome per accepted call, with explicit error/cancellation states. “No tool call” is also not proof that a task succeeded: pending user input, verification and stop policy matter. Codex's inspected implementation considers both model follow-up and queued input. [Verified source packet](../research/code-reading-curriculum-2026-10-08.md#L36).

**VI:** API từ chối request là lỗi hợp đồng, không phải xác suất biến mất. Agent dừng và issue được sửa đúng cũng là hai trạng thái khác nhau.

**3. Avoid universal claims about edit tools.** The research original [says every native edit tool refuses ambiguous matches — local-only](github-snapshot.md#omitted-local-evidence). Codex's pinned sequence matcher returns a first match and includes whitespace and Unicode normalization passes. Unique-span replacement is a good lab contract, but cannot describe every production primitive. Read parser, matcher, caller and tests together; a helper alone does not establish the full editor's behavior. [Inspected matcher](https://github.com/openai/codex/blob/9dd798805fdf9dd0f836f35ccc9480cb0af17784/codex-rs/apply-patch/src/seek_sequence.rs#L35).

**VI:** Một invariant mình chọn cho lab không trở thành sự thật chung về mọi sản phẩm. Source phải được đọc theo đường gọi thực tế.

**4. Separate billing, arithmetic and measured latency.** The original [E3 limiting case — local-only](github-snapshot.md#omitted-local-evidence) drops the quadratic attention term at zero cached prefix; that term remains. FLOPs divided by assumed throughput is a model estimate, not measured TTFT. KV bytes are not total runtime memory. Cached-token billing is not identical to newly computed tokens. The [serving audit](../research/serving-evaluation-training-audit-2026-10-08.md#L40) preserves useful arithmetic while correcting assumptions, units and comparison boundaries.

**VI:** Hóa đơn, số phép tính và thời gian trên đồng hồ cần ba ledger riêng. Capacity tính tay chưa chứng minh chạy được từng ấy session.

**5. Preserve the conditions behind benchmark claims.** The original [evaluation section — local-only](github-snapshot.md#omitted-local-evidence) correctly stresses harness and environment effects. Strengthen that discipline: freeze task/grader versions, use paired tasks and matched budgets, disclose infrastructure failures, and distinguish author reports from independent reproduction. Cursor's reasoning-item comparison uses different models and benchmarks; it is not a controlled company-to-company result. Primary-source accessibility resolves some earlier uncertainty, but does not turn vendor experiments into measurements performed here. [Cursor's account](https://cursor.com/blog/codex-model-harness).

**VI:** Mỗi điểm số phải đi cùng điều kiện đo. Không đổi mẫu số bằng cách âm thầm loại các run khó hoặc lỗi hạ tầng.

**6. Correct the repeated-risk inference.** The research original's [Vietnamese explanation — local-only](github-snapshot.md#omitted-local-evidence) suggests single-attempt risk mechanically becomes the cited adaptive result. Under independent constant-risk trials the calculation is `1−(1−p)^n`; adaptive attacks require conditional probabilities and experimental evidence. Keep reported results as reported results instead of deriving one from the other. [Evaluation corrections](../research/serving-evaluation-training-audit-2026-10-08.md#L108).

**VI:** Kết quả adaptive thực nghiệm không phải hệ quả tự động của giả định independent. Viết rõ giả định trước khi dùng công thức.

**7. Scope serving and RL claims.** The original [training section — local-only](github-snapshot.md#omitted-local-evidence) identifies a useful research direction. Training in a product harness does not mean the deployed product continuously trains itself. Rollout fidelity requires actual state/action tokens, behavior probabilities, masks and versions; compaction may legitimately change the next state. Token-level clipping is not a universal correction for arbitrary distribution mismatch. Likewise, a cache-system speedup from one workload/topology is not a promised benefit for another. [Training audit](../research/serving-evaluation-training-audit-2026-10-08.md#L126).

**VI:** Một paper chứng minh kết quả trong setup của nó. Bước tiếp theo là thiết kế thí nghiệm chuyển giao, không tự gán mức tăng đó cho hệ thống mình.

## Evidence rubric

| Label | Meaning in this packet |
|---|---|
| **Reported** | An identified primary source states it. Official documentation and vendor experiments remain distinguishable subtypes. |
| **Reproduced** | An independent rerun matches a specified result with recorded conditions; opening its source page is insufficient. |
| **Measured** | This work executed the measurement and retained raw evidence, configuration and scope. |
| **Derived** | Arithmetic or reasoning follows from explicit assumptions; it is not a hardware measurement. |
| **Proposed** | A curriculum, design choice or experiment is recommended and still awaits implementation/evaluation. |
| **Unverified** | Evidence is missing, contradictory or not checked within this audit. |

Source-inspected behavior is additionally tagged **code-verified at a commit**; it establishes what was inspected, not that all callers were audited or upstream tests passed. Eighteen selected source/license snapshots were saved, hashed and checked for the cited anchors. The original claims of [earlier clone measurements — local-only](github-snapshot.md#omitted-local-evidence) remain historical claims unless separately reproduced.

**VI:** Nhãn bằng chứng ngăn việc nâng cấp âm thầm từ “đã đọc” thành “đã chạy”, rồi thành “đã hiểu”. Mỗi lần nâng cấp cần một artifact mới.

## Executable learning and ownership

The original [kit specification — local-only](github-snapshot.md#omitted-local-evidence) uses a placeholder `/tmp/...` path and admits unfinished components. The search under `/tmp` and `ladders/study` did not locate that kit; no wider absence claim is made. The new local lab is an independent educational implementation, not a recovered kit or proof of the original acceptance suite. Its actual README and test evidence define what exists.

The original [after-your-attempt reading rule — local-only](github-snapshot.md#omitted-local-evidence) does not bind this separate packet. AI-written first cores are allowed. Huy demonstrates understanding through prediction, exact trace, defect diagnosis and transfer; assistance does not manufacture mastery. Existing `fam` and `ladders` files, schedules and hardware gates remain unchanged. Their project-specific contracts still govern work undertaken there. This packet adds a harness learning path and reuses those foundations where appropriate.

**VI:** AI có thể viết implementation để em học sâu từ hệ thống thật. Gate của em là giải thích và xử lý biến thể mới; không phải chép code bằng tay hay xin phép vì chưa đọc hết tài liệu.
