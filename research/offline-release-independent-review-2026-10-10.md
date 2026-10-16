# Offline release candidate — independent review

Date: **2026-10-10**. Status: **ACCEPTED for the bounded local offline candidate; independent review complete**. Independent AI review; human mastery is not assessed. Review scope is the frozen offline release contract and its preparation addendum, the release builder and standalone acceptance, final curated artifacts, and the proposed immutable-skills specification. No production source edits, inference, account discovery, image pulls or publication are authorized by this review.

## Contract and review method

Read `AGENTS.md`, `context/current-state.md`, the selected H0 reference-runtime packet, and [the release specification](offline-release-spec-2026-10-10.md). Addendum A permits exact public locked-wheel acquisition as **online preparation**; subsequent build/install/acceptance must remain offline. A verified package requires both byte identity and behavior: selected source → staged source → archive/wheel → installed origins, then accepted request → durable receipt → checkpoint → separately acquired fresh owner.

**VI:** Wheel đúng hash vẫn có thể thiếu asset; test pass vẫn có thể import nhầm checkout. Review phải kiểm tra cả chuỗi bytes lẫn state thật. Thanh toán được xác nhận muộn không tự biến effect Unknown thành thành công.

Review findings are sent to implementation owners; this reviewer owns only this report and independent scratch evidence under `runs/offline-release-2026-10-10/review/`. Final artifact checks used a fresh external working directory and installed package, with before/after source hashes. Failed probes remain evidence, not accepted outcomes.

## Findings and repairs (static review complete)

1. **Acceptance creates a post-checkpoint effect before clean restore.** The initial context scenario invokes `ToolBroker.execute` for a forbidden-resource control after recording its last checkpoint. The broker durably commits a `failed_known` dispatch, so `restore_checkpoint` correctly refuses to rewind the now-incomplete frontier. Move the negative control into a separate fixture/copy or check the resource boundary without adding a dispatch to the continuation fixture. Runtime recovery must remain unchanged. Reported to root before installed execution. Repaired: the negative control calls the installed resource validator directly and asserts an unchanged ledger; actual successful retrieval still uses a durable broker dispatch. Reproduced successfully against the final installed candidate.
2. **Negative assertions admit unrelated exceptions.** The initial `expect_error` helper accepts arbitrary exceptions for Unknown recovery/replacement and corrupted typed manifests. Require expected exception classes and invariant-specific reasons. Also assert outstanding liability and persisted dispatch identities/counts around rejected retries and late settlement; a local HTTP observation counter alone does not establish an unchanged durable dispatch frontier. Reported to root. Repaired: expected classes/invariant messages, positive unsettled bound, preserved dispatch IDs/counts, unchanged rejected-operation snapshots, exact reservation release and duplicate-settlement snapshot equality. Root also required observed request bytes to be inserted into the canonical request wrapper before digest comparison, avoiding Python False/0 equality aliases. Reproduced successfully against the final installed candidate.

3. **Actual source freeze rejected the harness’s isolation check.** A later-added AST guard rejected every `sys.path` reference, including read-only iteration that checks import isolation. Root’s actual freeze exposed this gap in the original synthetic fixtures. Repaired: reads/iteration pass; writes, deletes, subscript mutation and method calls reject. Tests now include the actual shipped acceptance source. This is an accidental checkout-dependency guard, not a general Python sandbox. Failed first-freeze diagnostics remain preserved by root.

## Immutable-skills design review

The [proposed skills contract](immutable-skills-spec-2026-10-10.md) has been inspected as design only. It uses a successful ordinary `load_skill` receipt as activation evidence, adds opt-in per-dispatch metadata without global RuntimeStore schema migration, keeps skills as instruction data, and separates the last accepted request's loaded state from newer post-turn checkpoint state. Resource access is pinned to accepted catalog/package membership; same-response loading cannot bootstrap resource permission. Fresh-owner recovery preserves original receipt provenance and requires separate authority. Actual native mock request capture and post-load/pre-disclosure recovery are specified as distinguishing future experiments.

The requested boundedness clarification is repaired in the frozen design: verify the original primary load directly through seed identifiers; no recursive skills-state replay; remaining provenance walks reject cycles or more than 64 distinct records before new intent. The reviewed frozen specification SHA-256 is `99f5f74959efd592e967f5f57d372a151f74c921972be7eaf214ad2dd112b18f`. Tiny illustrative body length was independently checked as **30 UTF-8 bytes**, matching the draft. No runtime implementation or task-quality result follows from this design review.

**VI:** Checkpoint sau load chứa nhiều state hơn request trước load là đúng. Nếu sửa lại request cũ để “khớp” state mới thì đã làm sai lịch sử; nếu chỉ restore state cũ thì mất receipt load. Spec hiện phân biệt hai thời điểm này rõ ràng.

## Measured artifact evidence

Builder and release documentation static review is complete, including the 52 authored adversarial cases. The unverified-cache alternative was removed; actual selected installation uses original lock-hashed wheels. All 18 prepared wheel byte hashes and sizes were independently compared to `uv.lock`; every wheel contains license/notice paths. Available package/version/license metadata is recorded in `review/wheelhouse-independent.json`, with legal completeness explicitly unreviewed. A separate pre-acceptance comparison found 153 baseline runtime/workload/compute/evaluation/lock/historical-artifact files unchanged (`review/runtime-historical-preservation.json`).

Independent AI reproduction on the **same local machine** passed all bounded A1–A8 release checks. This is neither an external human reproduction nor production M7 completion. Evidence is rooted at `runs/offline-release-2026-10-10/review/`:

| Check | Independently observed result | Evidence |
|---|---|---|
| A1 identities | 148 source entries, 137 product wheel entries; exact runtime/assets/license bytes; curated exclusions hold | `candidate-independent.json` |
| Source reproduction | Extracted archive plus its shipped builder re-freezes to exactly the same manifest, rebuilds the exact source archive and identical wheel member bytes | `archive-refreeze.json`, `archive-rebuild.json`, `reproduction.json` |
| A2 clean installation | Fresh isolated venv, Python 3.12.11 on Darwin arm64; final original wheel plus 18 original lock-hashed dependencies, offline/no-index/no-deps/no-build; 19 distributions exactly; installed origins and every product source/asset agree | `independent-install-evidence.json`, `independent-install.json` |
| A3–A5 repair/restart/report | Native mock + local immutable Linux arm64 Docker image; uninterrupted five requests and separate-process pause2/resume3; epochs1→2; review_eligible/pending; independent git apply reproduces exact candidate bytes; replay dispatches10→10; slots retired | `acceptance-evidence/acceptance.json` and raw repair subdirectories |
| A6 context/retrieval | Four native mock requests; captured payload's canonical wrapper matches accepted request digest; old sentinel omitted from offloaded request but retained in raw source; exact 1024-byte read with zero-bound receipt/provenance | `acceptance-evidence/context/` |
| A7 recovery | New RuntimeStore controller validates typed checkpoint; restore leaves authority snapshot unchanged; separately claimed epoch2 starts a new accepted chain with old projection/checkpoint lineage | `acceptance-evidence/context/typed-recovery.json`, `snapshot-after-fresh-owner.json` |
| A8 uncertainty | Third request loses response; bound4 remains unsettled; restore/replacement denied without new dispatch; idempotent late charge1 reduces total reserved92→88; effect stays Unknown, five dispatch IDs unchanged | `acceptance-evidence/context-unknown/`, acceptance summary |
| Isolated Unknown fence | On a disposable copy, retire synthetic slot after billing settlement; a new claim still raises `Fenced: previous operation requires reconciliation`; five dispatches and full snapshot unchanged | `retired-unknown-negative.json` |
| Real artifact mutation | Alter `service/context.py` in a disposable copy of the final wheel; builder rejects `stale wheel bytes: service/context.py` | `real-artifact-negative.json`, preserved mutated wheel |
| Source preservation | All 145 unique selected source origins unchanged before/after independent reproduction; 148 archive targets include three root/template aliases | `reproduction.json` |

Docker daemon identity/version was captured separately in `docker-daemon.json`: local Docker Desktop 28.4.0, Linux aarch64. The inspected image ID is `sha256:ce9a404c2c0138e747a43e6ea022d2f7e670ed868df35d627a663ba7fb940ea9`. No image pull occurred. The installed script blocks Python internet sockets and uses explicit MockTransport; actual Docker checks use the already-local image.

Final reviewed artifact identities:

- Frozen manifest bytes: `fa702411c17f00b18dc419dec05f9059a536803346350595f1b62efeafb37583`.
- Frozen manifest content: `20625e3114aa8ff439659c20cdf7544a2674a07fc6ae358c0c661fafbd447511`.
- Final original wheel: `132a8ec972f918bc4a99fb67aa4f096b5844d3e51faf7f8982924c91b19fe040`.
- Source archive: `540bbbcaf6be5567dbafb8f4f4c3dc23eb293af89e17401464edd1209f7a93d6`.
- Unchanged dependency lock: `40f83da9fd62a2d6758f0a426f43bd284670e46c559c08776b2b50d54cd07e32`.
- Standalone acceptance source: `4f3e8b5459e571d30e0d55f112e739d94e58ca1f5a59789ea000a9a0e76c7d02`.

Rebuilt wheel container hash differs (`e4a7d5e9c74a71b74511e8ab9f0b9eb6cefc0d74de1439c93ae3282708b3d615`) while every member byte matches; no bit-for-bit reproducible wheel archive claim is made. Independent acceptance installed the **final original** wheel, not the rebuilt one. Both full repairs produced tree `3ab9f75f17af1461f7fb73cb9f14e1bf7e5edfcc9300c4e29ce4c1048f47868b` and patch SHA-256 `b6c92b1b1153b815db0bb3f22859d4489e318af795eda85b2c3e93bf545d90aa`.

**VI:** Kết quả đủ cho release mechanics đã chọn trên máy này. Không suy ra live-model quality, hostile-code isolation, active-container crash recovery, GPU performance, hosted judge access, publication, production readiness hay human mastery. Skills vẫn chỉ là design đã review; paid execution giữ disabled.



## Final status-document review

Reviewed the release index, current-state summary, implementation coverage, D033 decision, START-HERE, capstone release/skills contracts, delivery ledger and current installed-runbook section. They distinguish separate online dependency preparation from offline build/install/acceptance, same-machine AI reproduction from fresh-machine/human/production evidence, frozen skills design from implementation, and local release progress from live sponsor/public G5 gates. The earlier capstone resource-materialization wording was reconciled with the frozen artifact-only first profile. Root owns the final integrated verification record and documentation/link checks; no runtime test repetition is needed for these prose changes.

All reproduced blocking findings are repaired within release tooling/tests or specification/docs. Production runtime source, schema, lock, workload population, historical release bytes, paid-execution hold and human mastery records remain unchanged. Final independent post-run preservation checks again matched all 153 baseline runtime/lock/historical files. The stable independent evidence inventory is `runs/offline-release-2026-10-10/review/evidence-inventory.json` (263 files); current report bytes are bound separately by root's final verification record.

Independent rebuilt archive/wheel and backend evidence, installation command/probe logs, and the disposable retired-Unknown case were copied into review evidence before temporary-directory cleanup. The fresh venv and redundant extracted source can be discarded after root verifies this inventory; they are not delivery artifacts.
