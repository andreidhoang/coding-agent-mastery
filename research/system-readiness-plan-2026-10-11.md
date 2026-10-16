# System readiness: dependency and evidence plan

Date: **2026-10-11**. Status: **bounded offline readiness implementation and installed acceptance passed; external qualification remains open**. User-authorized reference implementation; AI delivery does not assess human mastery. Paid execution, live provider traffic, GPU rental and public deployment remain disabled. Baseline is preserved in `runs/system-readiness-2026-10-11/before.json` and `before-source/`.

## Target and scope

Advance the existing durable coding-agent reference toward a reproducible, configured local service and an explicit dedicated-GPU qualification path. Keep one RuntimeStore, one harness, one evaluator, exact provider artifacts and the existing hackathon workload. A fully operated production claim additionally needs hardware, live-model and deployment evidence that this machine cannot supply. See the [source review](frontier-harness-patterns-2026-10-11.md).

**VI:** Ta xây implementation đủ rõ để kiểm tra và vận hành có kiểm soát; không đổi tên fixture thành agent có năng lực thực. Mỗi release cần biết chính xác phần nào đã chạy, phần nào chỉ có CPU/mock evidence và phần nào còn thiếu code.

## Ordered work

| Order | Work and owner | Required evidence before promotion |
|---|---|---|
| 0 | Three independent Astra audits: durable runtime, serving, GPU. Root integrates and freezes scoped contracts before edits. | Inspected source, dependency graph, failure cases; current public primary sources. |
| 1 | Skills step5: typed post-turn checkpoint and fresh-owner continuation. Sol implements against frozen contract. | Native mock exact bytes; loaded-after-request preservation; stale/Unknown/forged/cyclic/bounded evidence rejection; current-owner capability and accounting intact. |
| 2A, independent of 1 | Configured offline service plus atomic bounded backlog. Reuse API, authority and fixture engine. | Authenticated actual local lifecycle; fail-closed configuration, duplicate-at-cap behavior, atomic admission races, persistence/restart and truthful readiness. |
| 2B, independent of 1/2A | Trusted authored RMSNorm CUDA qualification entry point and explicit generated-code GPU boundary. | CPU oracle, strict input/identity/measurement checks, child-process failure tests, structured CUDA-unavailable result. Actual GPU measurements remain pending. |
| 3 | Durable environment identity and bounded reconciliation, using audit findings and a separately frozen contract. | Persist nonce before create; exact immutable instance inspection; no automatic replay of Unknown effects; restart/late-create/foreign-container controls. |
| 4 | Independent review, integration regressions and current installed-package acceptance. Update source-linked core docs and context. | Source hashes, actual test backend/skips, installed-origin checks and negative controls; old releases preserved. |
| 5, requires external evidence | Authorized hardware/live-model/deployment qualification. | Dedicated supported NVIDIA GPU; actual provider/version/rate envelope and fixed workload; containment, backup/restore, load, rollback and SLO evidence. No invented pass or permission. |

Independent lanes may overlap only with disjoint file ownership. Shared authority changes are integrated sequentially. Failed checks are retained, repaired and rerun against stable source. No gate is passed merely by a report saying it is ready.

**VI:** Spec recovery phải xong trước code recovery. GPU probe có thể xây song song vì không đổi authority. Nhưng hai agent không được cùng sửa `storage.py`; phần queue và checkpoint cần phối hợp một owner hoặc nối tuần tự.

## What stays outside this minimum release

Dynamic graph replanning, arbitrary repository/dependency execution, semantic compaction, LSP/MCP expansion, model training, full serving-engine integration and automatic production scaling are separate broader contracts. They are not prerequisites for a bounded fixed-DAG reference service or a trusted GPU qualification probe. They remain visible gaps; this plan does not claim them completed or remove them from the capstone.

## Acceptance ledger

[The source-bound verification record](system-readiness-verification-2026-10-11.json) owns final identities, preserved failures, before/after comparisons and limits. Focused counts overlap the full suite; do not add them together.

| Gate | Measured result and evidence |
|---|---|
| Skills step5 | [Frozen spec](skills-recovery-spec-2026-10-11.md)/[addendum](skills-recovery-addendum-a-2026-10-11.md); [independent review](skills-recovery-independent-review-2026-10-11.md). Two reproduced review defects repaired; unchanged five reviewer controls passed in root's final rerun. Current [three-owner native mock demo — local-only](../docs/github-snapshot.md#omitted-local-evidence): three requests/checkpoints, two clean reopens, accepted counts0/1/1 versus post-turn1/1/1, exact opaque history and original load preserved. |
| Offline service | [Frozen spec](serving-preflight-spec-2026-10-11.md), [independent review](serving-independent-review-2026-10-11.md):16 independent checks with actual HTTP/child process, PostgreSQL cap races and three rejected scratch defects. Missing/empty/different-incarnation database recovery refuses; stale same-incarnation rollback detection is unimplemented. |
| Trusted GPU preparation | [Frozen boundary](gpu-boundary-spec-2026-10-11.md)/[config](gpu-probe-config-addendum-2026-10-11.md), [review](gpu-probe-independent-review-2026-10-11.md):96 maintained tests/141 subtests,12 root-rerun independent controls. [Three disposable defects](gpu-mutation-review-2026-10-11.md) rejected against unchanged positive controls. CPU/fake only; CUDA and generated-code isolation remain open. |
| Docker environment journal | [Frozen spec](environment-recovery-spec-2026-10-11.md)/[source-identity addendum](environment-recovery-addendum-a-2026-10-11.md), [independent review](environment-recovery-independent-review-2026-10-11.md):41 reviewer-run controls with zero skips;182 maintained independent checks,11 focused policy-oracle refinement checks and four rejected scratch defects. Real separate-process create-ACK-loss recovery passed on SQLite/PostgreSQL. |
| Actual engine integration | [Fixture and repair engine runs — local-only](../docs/github-snapshot.md#omitted-local-evidence) reached review_eligible/pending using actual cached-image Docker. Repair used five native mock requests, three journals/eight containers; all slots retired, zero spent/reserved, repeat cleanup read-only. Runtime source hashes unchanged. |
| Full regression and lint | [Full log — local-only](../docs/github-snapshot.md#omitted-local-evidence):2272 passed,156 subtests passed,two skips. The separately configured context PostgreSQL check subsequently [passed — local-only](../docs/github-snapshot.md#omitted-local-evidence); only the physical filesystem collision remains unexercised. Real local PostgreSQL/Docker/Temporal enabled; Ruff passed. All product Python/assets/lock stayed unchanged. Two test-only literal-policy assertions and two CLI prose corrections landed during the suite; exact delta and focused11-pass follow-up are retained, so full-manifest immutability is explicitly **not** claimed. |
| Installed rc2 | [Review](readiness-release-independent-review-2026-10-11.md)/[verification — local-only](../docs/github-snapshot.md#omitted-local-evidence):161 frozen entries,19 locked base wheels; fresh outside-checkout interpreter, actual child origins, skills, service, GPU-disabled, real journal and previous repair/context/Unknown gates passed. All source entries and299 old candidate files unchanged. |

The current [runbooks](../ops/README.md), [coverage](../capstone/08-implementation-coverage.md), [reading guide](../docs/06-reference-code-reading-guide.md) and [context](../context/current-state.md) now distinguish delivered source from the remaining implementation and measurement gates. Historical source/runs/specs remain retained. The owned disposable PostgreSQL was stopped by exact verified ID after tests; no broad cleanup or external service was started.

**VI:** Full suite pass không có nghĩa mọi file giữ nguyên trong lúc chạy: hai test được bổ sung oracle độc lập và prose CLI được sửa, còn product code không đổi. Báo cáo giữ đúng cả điều này lẫn focused rerun, không đổi log để làm evidence đẹp hơn.

## Next engineering decisions

1. For the deadline-critical hackathon, retain the supported repair profile. Live provider conformance and a tiny frozen repair pilot need the explicitly changed execution instruction plus actual model/catalog/rate/spend/task inputs. Public source/access/video/rights remain later gates.
2. For NVIDIA hardware work, the authored probe can be qualified on a separately authorized dedicated GPU. Record correctness, actual synchronized timings, metadata/noise and lifecycle evidence; missing qualification withholds comparison. No GPU is provisioned or rented here.
3. Before any agent-generated CUDA execution, freeze and implement the remaining NV-S1 build/ABI/isolation, device reservation, protected verifier and uncertain-device retirement/health mechanisms. Then integrate one candidate through NV-S2; profiler and data interventions follow actual records.
4. For broader production, select the declared live workload and threat/SLO envelope before generalized repository intake, orchestration, retention/identity lifecycle or rollout work. Dynamic replanning, semantic compaction and LSP remain distinct source gaps; do not treat them as already completed hardware gates.

The current work is an independently checked **local reference candidate**, ready for its stated next qualification experiments. It is not the entire production service, a live-model benchmark, an isolated generated-GPU runner or evidence of Huy's mastery.

## Subsequent bounded qualification delivery

The subsequent [offline provider qualification](provider-qualification-spec-2026-10-11.md) and [verification](provider-qualification-verification-2026-10-11.json) add an evidence wrapper and exact prepared-repair handoff. The earlier readiness source/test records above remain unchanged. [Current installed rc4](../releases/README.md) now includes that wrapper; rc2 remains the accepted readiness-stage candidate. This closes an offline preparation gap, not G1/G2: actual account/catalog/rates, authorized live conformance and useful repair remain required. No GPU or generalized service scope was added.
