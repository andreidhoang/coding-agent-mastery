# Offline release candidates

**Current: 2026-10-11 rc4 — built, installed offline and independently accepted; unpublished. Paid/live execution disabled.** This adds the offline provider qualification/repair handoff to the preserved readiness runtime. [Final verification](../research/provider-qualification-verification-2026-10-11.json), [source review](../research/provider-qualification-independent-review-2026-10-11.md) and [runbook](../ops/runbooks/provider-qualification.md) define its bounded evidence.

| Artifact | Current identity/evidence |
|---|---|
| Curated source | [source.tar.gz — local-only](../docs/github-snapshot.md#omitted-local-evidence), SHA256 `b50523a147ed004596b141c75d65abf60cd339c663c53aaec0e0130024c4b32f` |
| Installable wheel | [coding_agent_mastery-0.1.0 — local-only](../docs/github-snapshot.md#omitted-local-evidence), SHA256 `f8152351bee9cef9845fd97f9e55fa3a6189c3226217423affc71eb4315a19f6` |
| Frozen source | [manifest — local-only](../docs/github-snapshot.md#omitted-local-evidence),163 entries; content `2982ccec6e1051f8ea0650ee980b1309505c9dd9abcb3dcf56fd422185b0a819` |
| Build/install | [build evidence — local-only](../docs/github-snapshot.md#omitted-local-evidence), [install evidence — local-only](../docs/github-snapshot.md#omitted-local-evidence), [shipped guide — local-only](../docs/github-snapshot.md#omitted-local-evidence) |
| Independent acceptance | [verification — local-only](../docs/github-snapshot.md#omitted-local-evidence), [full result — local-only](../docs/github-snapshot.md#omitted-local-evidence), SHA256 `4ddba54cbf8d063dbc09681cc2cfd8073283229c3694445ed9af0cbfb8133fc9` |

The fresh outside-checkout Python3.12.11 installation used19 already-verified locked base wheels plus product, with no dependency download/resolution. All152 installed product entries matched the frozen manifest;40 parent origins, five repair CLI records, seven qualification CLI records and actual configured-worker origins were validated. Qualification executed two native mock requests, settled2 synthetic units, preserved upstream repair bytes, and rejected missing/corrupted/reindexed evidence and Unknown resends. Full inherited repair/restart/context/skills/service/journal/GPU-disabled acceptance passed with actual cached-image Docker. This is same-machine offline evidence; live G1/G2, CUDA, fresh-machine/public access and operated production remain open.

**Preserved preliminary rc3:** [build — local-only](../docs/github-snapshot.md#omitted-local-evidence) completed but was not installed or accepted. A final inspection found that nested qualification CLI origin records needed explicit checks. [Recorded disposition — local-only](../docs/github-snapshot.md#omitted-local-evidence) and [independent precheck — local-only](../docs/github-snapshot.md#omitted-local-evidence) retain that history; rc4 contains the corrected standalone acceptance. No product source changed between those candidates. Original rc1/rc2 remain byte-identical. Full new archive/wheel reproduction was not repeated; the unchanged builder's earlier evidence stays historical.

**VI:** “Current” chỉ đúng với rc4 và manifest của nó. rc3 build được nhưng chưa được accept; giữ lịch sử đó để không nhập nhằng packaging pass với installed proof. Tất cả inference ở đây vẫn là mock, còn Docker/package/process checks là thật.

## Preserved rc2

**Previous accepted readiness candidate: 2026-10-11 rc2 — built, installed offline and independently accepted; unpublished. Paid execution disabled.** This records the earlier readiness base-runtime candidate on macOS arm64/Python3.12.11, using native mock transport and the existing local Linux arm64 Docker image. The earlier candidate below is preserved byte for byte.

| Artifact | rc2 identity/evidence |
|---|---|
| Curated source | [source.tar.gz — local-only](../docs/github-snapshot.md#omitted-local-evidence), SHA256 `20bf57b166b78b631862b163654ff43c3922c4b11e734eff21c54d4819f703e5` |
| Installable wheel | [coding_agent_mastery-0.1.0 — local-only](../docs/github-snapshot.md#omitted-local-evidence), SHA256 `04650f6afa9117febf841f604bb251600d4bd3aa3ab8d1dd014fa89f4a3f1545` |
| Frozen source | [manifest — local-only](../docs/github-snapshot.md#omitted-local-evidence), 161 entries; exact content `db2da4b05367baf2a9eb27a05ce724a4b4d24270055a982dba8dc5435dbc1ccc` |
| Build/install | [build evidence — local-only](../docs/github-snapshot.md#omitted-local-evidence), [install evidence — local-only](../docs/github-snapshot.md#omitted-local-evidence), [offline guide — local-only](../docs/github-snapshot.md#omitted-local-evidence) |
| Dependency preparation | [19 original locked wheels — local-only](../docs/github-snapshot.md#omitted-local-evidence), [separate public acquisition record — local-only](../docs/github-snapshot.md#omitted-local-evidence); no dependency resolution/download during build/install/acceptance |
| Independent acceptance | [review](../research/readiness-release-independent-review-2026-10-11.md), [source/artifact verification — local-only](../docs/github-snapshot.md#omitted-local-evidence) |

The fresh outside-checkout installation verified38 parent product origins and22 modules in each of two actual service workers. Acceptance passed exact repair/report/restart, context recovery, Unknown no-resend/once-only billing, three-request skills continuation across epochs1/2/3, strict same-response resource denial, actual configured worker lifecycle/restart, disabled no-Torch/no-child GPU planning, and real Docker journal/terminal-ID proof with read-only cleanup. Worker origin observation uses a declared test wrapper; unmodified real loopback HTTP has separate [serving evidence](../research/serving-independent-review-2026-10-11.md).

All161 frozen source entries and299 files of the October10 candidate remained unchanged during this acceptance. Full new archive/wheel byte-rebuild reproduction was not repeated; the unchanged builder's earlier reproduction remains historical evidence. The new release verifies base dependencies only. No actual CUDA, live-model quality, public access, fresh-machine deployment, operated SLO or human mastery is established. See [coverage](../capstone/08-implementation-coverage.md) for code still missing from the broader capstone.

**VI:** Cài được wheel ngoài source là một gate riêng. Model mock, Docker thật và package thật phải ghi rõ; không dùng chữ “release” để suy rằng đã public hoặc sẵn sàng nhận workload production.

# Preserved October10 candidate

**2026-10-10 rc1 — built, installed and independently checked; unpublished. Paid execution disabled.** Scope: Python3.12.11 on macOS arm64, base runtime dependencies, native mock HTTP and an already-local Linux arm64 Docker image.

| Artifact | Exact candidate |
|---|---|
| Curated source | [source.tar.gz — local-only](../docs/github-snapshot.md#omitted-local-evidence) — SHA-256 `540bbbcaf6be5567dbafb8f4f4c3dc23eb293af89e17401464edd1209f7a93d6` |
| Installable product | [wheel — local-only](../docs/github-snapshot.md#omitted-local-evidence) — SHA-256 `132a8ec972f918bc4a99fb67aa4f096b5844d3e51faf7f8982924c91b19fe040` |
| Source identity | [frozen manifest — local-only](../docs/github-snapshot.md#omitted-local-evidence): 148 curated entries, 145 unique origin files |
| Offline dependencies | [18 original locked wheels — local-only](../docs/github-snapshot.md#omitted-local-evidence), [preparation/inventory — local-only](../docs/github-snapshot.md#omitted-local-evidence), [base requirements — local-only](../docs/github-snapshot.md#omitted-local-evidence) |
| Reproduction | [shipped offline guide — local-only](../docs/github-snapshot.md#omitted-local-evidence), [build evidence — local-only](../docs/github-snapshot.md#omitted-local-evidence), [install evidence — local-only](../docs/github-snapshot.md#omitted-local-evidence) |
| Acceptance | [independent tester — local-only](../docs/github-snapshot.md#omitted-local-evidence), [reviewer rerun — local-only](../docs/github-snapshot.md#omitted-local-evidence), [review](../research/offline-release-independent-review-2026-10-10.md), [verification](../research/offline-release-verification-2026-10-10.json) |

52 packaging tests and repository Ruff passed. Both separate installed runs verified42 workload definitions/82 locked assets, uninterrupted repair and pause2/resume3 with epochs1/2, exact patch application/report replay, accepted context retrieval and fresh-owner recovery. Unknown remained unsendable after a lost response and settled its late charge once. The reviewer independently extracted/refroze/rebuilt the archive; source archive identity and every wheel member byte matched. Rebuilt wheel container hashes differ, so bit-identical wheel reproduction is not claimed.

Public dependency-wheel acquisition was a separate online preparation phase under the frozen addendum. Build, install and acceptance used local material offline. The wheelhouse supports the measured platform; Python/toolchain and Docker must already be available. At that delivery, runtime/schema/lock and prior exports were unchanged. The archive excludes personal learning/context, research, run evidence and private control inputs. Its authored oracle fixtures remain controller-owned and outside worker intake. Candidate Apache-2.0 terms/NOTICE are preserved; third-party license metadata/notice inventory is recorded, with final redistribution rights review pending.

**VI:** Đây là bộ source/wheel đã được cài ngoài checkout rồi chạy lại bằng hai agent độc lập trên cùng máy. Model response vẫn là mock, còn Docker và package install là thật. Giữ cả wheelhouse để lần sau cài offline; source archive riêng không chứa mọi công cụ hệ thống hay Docker image.
