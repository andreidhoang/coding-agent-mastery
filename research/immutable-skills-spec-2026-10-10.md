# Immutable skills — proposed implementation contract

Date: **2026-10-10**, Asia/Ho_Chi_Minh. Status: **REVIEWED DESIGN, frozen for future implementation; not implemented**. AI-authored design, separate from human mastery. Scope: one authored fixture package, immutable catalog, broker loading and bounded resource reads, scripted/mock-provider evidence. No installation, script execution, hot reload, account discovery, paid execution or capability escalation. This document does not authorize implementation.

## Purpose and first principles

Progressive disclosure supplies catalog metadata, then selected instructions, then selected resources. A hash identifies bytes; a successful durable receipt records a load; an accepted model request records what was disclosed; a current owner and frozen capability authorize an operation. These are different facts. Exact reconstruction matters because a process can crash after loading but before the next model request. This slice establishes reproducible data flow and authority boundaries, not improved model task performance.

**VI:** Catalog là mục lục, snapshot là bản sách đã đóng dấu, receipt là biên bản đã lấy sách, capability là quyền truy cập. Biết hash không có nghĩa được đọc mọi artifact. Checkpoint sau load phải nhớ sách đã lấy, dù request trước đó chưa chứa nội dung sách.

The smallest design uses **the ordinary successful `load_skill` dispatch/result receipt as activation evidence**. There is no separate mutable active-skills pointer or activation transaction. “Loaded” means that receipt committed. “Disclosed” means a later accepted request includes its exact result and loaded membership. Resource reads require membership in the accepted request that produced their model response. A load and resource read proposed in the same response cannot bootstrap new resource permission; the next model request must disclose the load first. No receipt or skill metadata grants capabilities.

**VI:** Không cần transaction mới chỉ để ghi “active=true”: receipt thành công đã là durable evidence. Nhưng không được lấy state trong RAM làm authority. Mỗi request phải xác minh lại loaded list từ receipt cụ thể. Cách này giữ thiết kế nhỏ mà vẫn phân biệt rõ crash trước/sau commit.

## Inspected baseline and owners

Read [current state](../context/current-state.md), [H0 runtime packet](../study/packets/H0-reference-runtime.md), [canonical skills proposal](../capstone/07-reference-implementation-spec.md#L211), and [frozen context contract — local-only](../docs/github-snapshot.md#omitted-local-evidence). The historical context specification remains unchanged. Its acceptance does **not** already validate skills.

| Existing inspected seam | Current behavior and proposed extension |
|---|---|
| [Planner](../service/context.py#L72) | Closed v1 binding/offload policy; add explicitly versioned skills-aware projection |
| [Broker](../service/harness.py#L25) | Frozen capabilities and pinned context; add catalog/load/resource membership checks |
| [Harness](../service/harness.py#L147) | System/tools built before turns; add frozen catalog rendering and receipt-derived skill state |
| [Accepted dispatch](../service/storage.py#L648) | Atomic acceptance+intent; add validation of submitted skill membership against durable load receipts |
| [Receipt](../service/storage.py#L802) | Terminal result reference is durable; successful load receipt is the activation commit point |
| [Restore](../service/recovery.py#L34), [request reconstruction](../service/recovery.py#L309) | Source-prefix/request checks; add separate pre-request and post-turn loaded-state validation |
| [Tool schema](../service/protocol.py#L95) | Exact arguments; preserve legacy defaults while opting into new tools |
| [Artifacts](../service/artifacts.py#L36) | Scoped hash-checked bytes under trusted control-plane storage; does not itself make arbitrary directory import safe |

**VI:** Các seam hiện có là điểm nối, chưa phải bằng chứng feature mới đã đúng. `context_acceptance` hiện không biết `load_skill` nào đã thành công hoặc resource thuộc package nào. Cần thêm validation ở đường version mới, không gắn thêm field rồi mặc định tin nó.

| Object | Owner and invariant |
|---|---|
| Import roots, origin/revision, profile/limits | Trusted launcher; repository/model text cannot choose or widen them |
| Task contract/capabilities/current owner | RuntimeStore; immutable task policy and existing lease/generation fencing |
| Captured package/catalog bytes | Trusted importer and scoped artifacts; identity and attributed data, never publisher authentication or authority |
| Load intent/result receipt | Ordinary broker/store dispatch lifecycle; only succeeded + valid result establishes loaded membership |
| Accepted skill state and exact outgoing request | Harness supplies attested source; RuntimeStore validates receipts, scope and frontier and atomically accepts with model intent |
| Resource selection | Broker resolves tuple through current accepted model response only |
| Checkpoint lineage | Store/recovery reconstruct data and compare receipts; acquiring a fresh owner remains separate |

## Persistence, compatibility and crash behavior first

Keep **RuntimeStore schema 2 and its writer protocol**, physical tables, existing six-field dispatch parameters and historical records. Use versioned sibling metadata on the opt-in dispatch path, as context does. Successful `load_skill` result artifacts bind catalog/package and source-model provenance; ordinary receipt commit atomically binds `effect_state:succeeded` and `result_ref`. Derive loaded state from those receipts, not another state table. This avoids the need for a schema migration. No task-wide mandatory skills policy is introduced: old/legacy writers cannot claim skills-aware execution or restore new typed checkpoints. If a future feature requires all writers to enforce a mandatory mode, freeze a separate writer/migration contract first.

**VI:** Schema 2 đủ cho slice chỉ bổ sung evidence theo từng dispatch. Nó không đủ để tuyên bố mọi binary cũ đều hiểu skills. Ranh giới hỗ trợ là opt-in adapter/checkpoint version mới; task-wide enforcement là feature khác, chưa được hứa ở đây.

New intent metadata `skill_call` is closed, with exact keys `{schema:1,operation,catalog_digest,package_digest,path,source_model_dispatch_id,source_projection_id,source_accepted_sequence}`. `operation` is `load` or `read_resource`; path is null only for load. Tool input digest is `D({call_digest,skill_call})`. Here `D` is existing canonical JSON SHA-256; raw file digest is `H(bytes)`. Digests are lowercase 64-hex. Strict integer validation excludes booleans. Duplicate-dispatch comparison includes `skill_call` as well as ordinary parameters; never accept changed provenance under the same ID.

Before intent, broker checks frozen capability and pinned latest successful accepted model dispatch, validates supported response parsing/linkage, catalog and package membership, then calls the normal zero-bound tool-dispatch path with provenance. Store checks current owner and source response identity in the transaction, analogous to existing context retrieval. A diagnostic artifact, failed/Unknown response, missing result or arbitrary same-task request cannot authorize loading. Package/result validation uses bounded artifact reads. The broker writes the prepared canonical result then calls ordinary `finish_dispatch`; only its succeeded receipt makes the package loaded. Failed-known/Unknown/missing-result receipts do not. Existing receipt immutability prevents replacing a result later.

The feature path must validate successful load result contents against captured package/catalog and `skill_call` whenever deriving accepted state or checkpoint state; it cannot trust a receipt's tool name alone. Result bytes must exactly match deterministic rendering of the captured body/resource descriptors, with the original call ID. No active state update happens before receipt commit. If the result exists but commit fails, it is an orphan, not a load. An identical known duplicate uses the existing durable result and cannot activate twice. An unresolved duplicate is not automatically rerun, including read-only operations. A new call to an already loaded package returns `already_loaded` and its original load dispatch ID, with no additional membership entry.

**VI:** Receipt “succeeded” chưa đủ nếu result không khớp package đã quảng cáo. Khi build state, phải kiểm tra bytes và provenance. Ngược lại, artifact đúng cũng chưa đủ nếu chưa có succeeded receipt. Hai điều kiện kết hợp đóng khe hở crash và giả membership.

| Boundary | Required result |
|---|---|
| Import/result publication fails before intent | No new intent or loaded state; orphans confer no access |
| Load intent commits, no terminal result receipt | In-flight/Unknown retained; no loaded membership; no automatic replay |
| Result artifact exists, receipt write fails | Orphan result only; cannot continue from in-memory loaded state |
| Receipt commits, ACK lost | Exact retry returns same result; one load identity, no added event/cost |
| Load succeeds, sibling tool fails before checkpoint | Durable load remains; existing post-checkpoint/frontier rules forbid rewind |
| Checkpoint after load, before next model dispatch | Save post-turn loaded refs separately from last request's accepted state |
| Next request overflows | Load persists; no new model acceptance/intent/send; do not drop body |
| Acceptance+model intent commits, crash before send | Existing in-flight reservation; no presumed zero charge or automatic resend |
| Origin changes after import | Frozen artifact bytes remain the source; changed expected identity fails stale |
| Frozen artifact missing/corrupt | Fail closed; no origin-path fallback or rediscovery |

A restored seed carries direct original primary-load dispatch/result/source-model-acceptance identifiers. Validate those authoritative records directly; do not recursively derive skills state by replaying prior checkpoint/SkillsState chains. Bound any remaining provenance walk to **64 distinct records**; cycles or a 65th record fail before new acceptance/intent. This limit never drops evidence or changes old state. A1/R2 controls must include a cyclic reference and a chain beyond this limit, with no new intent on rejection.

## Package capture, explicit bounds and identities

Initial fixture: one AI-authored local `verified-repair-guide/` with `SKILL.md`, `references/checklist.md`, optional `assets/example.json`. No scripts. A distinctive resource marker supplies a byte-routing oracle. Trusted configuration specifies the single root; never scan installed skills, home directories, accounts or networks. Only this fixture is initially integrated, although invalid second-package inputs must be tested.

`SkillsConfig` exact keys: `{schema:1,profile:"immutable_text_skill_v1",limits,origin,source_revision,catalog_revision}`. Origin exact keys: `{origin_id,scope,root_label}`; scope is `fixture`; other origin strings are nonempty ASCII up to128 bytes, revisions nonempty UTF-8 up to128 bytes. Host path/handles remain private importer arguments. Config digest binds every limit and provenance field. The table's key names/values are the first fixed profile; no implicit increase and no measured-optimality claim.

| Limit key | Fixed initial maximum |
|---|---|
| `max_packages`, `max_loaded_packages` | 1 each; second package rejects entire catalog; earlier 32-package proposal deferred |
| `max_skill_bytes`, `max_frontmatter_bytes`, `max_body_bytes` | 65,536 / 8,192 / 32,768 raw UTF-8 bytes |
| `max_catalog_bytes`, `max_manifest_bytes` | 16,384 / 65,536 canonical bytes, including wrappers/provenance |
| `max_resources`, `max_directories`, `max_path_depth` | 64 / 64 / 4; bounded enumeration before recursive descent |
| `max_resource_bytes`, `max_total_resource_bytes` | 262,144 / 4,194,304 raw bytes; account before retaining allocation |
| `max_path_bytes`, `max_component_bytes` | 240 / 64 ASCII bytes |
| `max_yaml_depth`, `max_yaml_nodes` | 8 / 256 parser nodes/events before construction |
| `max_metadata_entries`, `max_metadata_scalar_bytes` | 32 / 1,024 UTF-8 bytes per key/value; frontmatter total still applies |
| `max_read_bytes`, `max_result_bytes` | 8,192 raw resource bytes / 65,536 canonical result bytes including base64 |

**VI:** Byte cap phải áp trước parse/read hết file. Node/depth cap phải áp trong parser, trước xây object. Giới hạn catalog/result tính cả wrapper, không chỉ body; nếu escaping JSON làm phình quá cap thì từ chối, không truncate âm thầm.

`SKILL.md` must be UTF-8, LF-delimited exact `---` frontmatter, no BOM/NUL/multiple YAML documents; CRLF is explicitly unsupported rather than normalized silently. Preserve raw bytes. Top-level allowed fields are exactly `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`; required name/description. Parse strings and mappings only; reject duplicate keys, aliases, anchors, merge keys, sequences, directives, explicit tags and non-string keys. `metadata` is string→string; other values strings with no implicit numeric/date/object construction. Enforce parser limits before construction; `safe_load` alone is insufficient. Pin parser/library version in lockfile at implementation.

Name is ASCII `[a-z0-9]+(?:-[a-z0-9]+)*`, 1–64 characters, matching package directory basename. Description is non-whitespace, 1–1,024 Unicode characters; optional compatibility is 1–500 characters. Optional fields remain bounded data; `allowed-tools` never changes capabilities, compatibility never triggers installation, license paths are not automatically followed. The local profile deliberately supports less than arbitrary Agent Skills YAML/content.

Importer opens a trusted root descriptor and every component relative to verified directory handles with no-follow semantics; verifies regular files with `fstat`, rejects symlinks, hardlinks (`st_nlink !=1`), devices/sockets/FIFOs and filesystem-device crossings. Nonblocking open before file-kind validation avoids FIFO hangs. Reject absolute paths, dot/dot-dot/empty components, backslashes, drive prefixes, hidden/control characters and components outside `[A-Za-z0-9._-]+`; reject case-fold collisions. Only root `SKILL.md`, `references/` and `assets/` are supported; all resources are text UTF-8, nested within the depth cap. Reject `scripts/` and unexpected entries. No archive extraction. Every file is read with cap+1 and cumulative bounds, then hash/size verified after artifact publication.

**VI:** `resolve()` rồi `open()` dùng hai thời điểm khác nhau; attacker có thể đổi tên thành symlink giữa chúng. Cần đọc từ đúng handle đã kiểm tra. Không cung cấp root artifact store cho process ứng viên; trusted control-plane storage vẫn là assumption hiện tại.

Initial source is a trusted quiescent fixture. Capture descriptor identity/size/mtime/ctime before/after each read and recheck bounded inventory; observed change aborts. This detects tested races but does not claim an atomic multi-file snapshot under hostile concurrent writers. Such writers need a real immutable snapshot producer in a later profile. After capture, activation/resources read **only stored artifacts**, never origin paths. Origin A→B mutation after discovery must still load advertised A or fail if the caller supplies B's digest; never silently substitute B. Explicit rediscovery means a new run/catalog, not hot reload. This clarifies the proposal's “activation consumes advertised snapshot” rule and S4.

Package manifest exact keys: `{schema:1,profile,origin,source_revision,name,metadata,skill_ref,body_ref,resources}`. `metadata` is validated frontmatter; skill/body refs bind full file/exact post-frontmatter body bytes. Resources sorted by path contain `{path,artifact_ref,encoding:"utf-8"}`. Every ref uses the existing closed `{tenant_id,task_id,digest,size,content_type}` and checks scope/bytes/size. `package_digest=D(manifest)`. Resource identity is `(catalog_digest,package_digest,path,artifact_ref.digest)`; same bytes at another path grant no membership. Same bytes with different declared origins produce different package identity; declarations attest configured provenance, not authenticated authorship.

Catalog exact keys: `{schema:1,profile,tenant_id,task_id,config_digest,catalog_revision,entries}`. Entry exact keys: `{name,description,origin,source_revision,package_digest,package_ref}`; deterministic sorting by origin/name/digest. `catalog_digest=D(catalog)`. Catalog binds packages; activation/accepted state later bind catalog. Do not put catalog digest inside the package it hashes. Reject duplicate names across inputs, even identical bytes, with bounded conflicting provenance; no silent precedence or shadowing. Scoped selection cannot bypass the one-package/collision policy.

**VI:** Tránh vòng identity: catalog chứa package hash, receipt chứa cả catalog và package. Không thể để package chứa hash catalog đang chứa chính package ấy. Tên giống nhau cần báo collision thay vì tự chọn “trusted” chỉ theo thứ tự tìm thấy.

## Tools, prompt identity and accepted context

Discovery is a trusted configured operation, not a model filesystem tool. New strict model arguments:

```
load_skill(catalog_digest: str, package_digest: str)
read_skill_resource(catalog_digest: str, package_digest: str,
                    path: str, offset: int, limit: int)
```

Feature opt-in requires both tools already present in frozen task capabilities. Tool schemas opt in without changing legacy default bytes. Exact keys/types, argument-size and integer checks use existing protocol rules. No prompt, metadata, output-directory convention or successful load changes filesystem/network/tool/spend authority.

Successful load's ordinary result `value` has exact keys `{schema:1,status:"loaded",catalog_digest,package_digest,body,body_digest,resources,source_model_dispatch_id}`; descriptors are `{path,digest,size}`. Canonical result wrapper retains existing `{call_id,tool,ok,value}` plus `skill_provenance` equal to validated `skill_call`. Failed-known errors have bounded stable codes: invalid_package, stale_catalog, not_disclosed, resource_denied, bounds_exceeded, unsupported_profile. Do not expose host paths, unbounded input text or parser traceback. Already-loaded result uses `{schema:1,status:"already_loaded",catalog_digest,package_digest,load_dispatch_id}` and cannot become a new membership root.

Resource reads require the package in the current response's accepted loaded state, original successful load receipt, exact relative resource path, scoped artifact integrity and bounds. There is no raw-digest retrieval, workspace/origin fallback or materialization. Artifact-backed virtual reads deliberately defer the earlier optional read-only package-area proposal. Require `0<=offset<=size`, `1<=limit<=max_read_bytes`; EOF at exact size gives empty bytes. Return `{catalog_digest,package_digest,path,digest,offset,total_size,size,next_offset,eof,encoding:"base64",data}` under ordinary durable result/provenance. Base64 makes offsets exact even across multibyte UTF-8. Input alone cannot change accepted membership.

**VI:** Resource không phải một hash bất kỳ trong store. Broker tìm đúng đường dẫn trong package của request đã được chấp thuận. Base64 bảo toàn byte; ghép chunks trước khi decode tiếng Việt. Việc materialize file/script chưa có trong slice này nên không phát sinh quyền chạy ngầm.

Prompt renderer `skills_prompt_v1` retains trusted constraints and appends a fixed wrapper plus canonical JSON catalog to system text. Wrapper labels content untrusted task aids subordinate to frozen constraints; escaping/labeling is not a semantic injection-proof claim. Body is disclosed only through ordinary `load_skill` result in raw history, not duplicated in system or synthetic assistant blocks. In the new context version protect `load_skill` and `read_skill_resource` results from offloading, alongside `read_context_artifact`; protected content can cause an explicit unfit refusal. Existing opaque provider fields, call IDs, error flags and raw artifacts remain exact.

Existing `system_digest` binds actual system text/catalog; `tools_digest` binds actual provider schemas. New `prompt_digest=D({renderer:"skills_prompt_v1",system,tools,messages:projected_messages})`. Catalog changes affect system/prompt/request digest. Activation changes messages/prompt/request digest while system/catalog can stay fixed. `D(contract.capabilities)` must remain unchanged. Request digest additionally binds provider/model/output settings as before. Admission measures the full outgoing request with system/tools/output allowance. No byte count equals exact tokens; no load/offload changes cumulative cost or Unknown exposure.

**VI:** Activation không nhất thiết đổi system digest: body nằm trong tool result. Vì vậy test phải kiểm tra toàn prompt/request digest. Đừng đổi một field vô nghĩa chỉ để assertion “digest đổi” pass.

Proposed opt-in versions (no DB migration): context manifest `context_schema:2` retains v1 keys and adds exactly `{skills_state_ref,skills_state_digest,prompt_digest}`; binding adds `skills_state_digest`; adapter adds `skills_capability`, uses `adapter_version:"context_skills_v1"`; projection uses `schema:2`, adds `skills_state_digest`; acceptance uses `context_schema:2`. All other key sets follow v1. Context config remains v1; separate skills config is hashed in state/catalog. Half-v1/half-v2 objects reject. Legacy validators remain closed, with explicit supported-version dispatch rather than permissive `.get` fallbacks.

`SkillsState` exact keys: `{schema:1,catalog_ref,catalog_digest,config_ref,config_digest,loaded,source_checkpoint}`. `loaded` is empty or one `{package_digest,load_dispatch_id,result_ref}`. Source checkpoint null fresh; restored first and later requests retain their seed checkpoint ID. New load evidence is derived from the current attempt's succeeded `load_skill` receipts plus a validated restored seed; never arbitrary earlier attempts. Validate result against package/body, intent provenance and original accepted catalog, and require exact load tool call/result occurrence in source history. At most one primary load, so provenance validation is bounded. Same catalog/config remains fixed in this skills-aware Harness run; changing it requires fresh run selection, not mid-run reload.

Model-acceptance validation reconstructs candidate skill state from authoritative receipts and compares submitted state; validates artifacts/projection/request and original tool-result presence before transaction. The existing authority transaction rechecks owner, contract, generation, source frontier, previous projection and receipt references/status before atomically storing acceptance+intent. The DB can compare durable evidence, not independently prove filesystem truth. Exact old intent retry converges; changed manifest/state/request under same ID conflicts. New Harness refuses opting in halfway through legacy history, disabling during skills restore, or switching catalog/config in that path. This is supported-path validation, not a claim that old ordinary-dispatch writers enforce a task-wide mandatory mode.

**VI:** State artifact là lời khai; DB phải đối chiếu với receipt. Nếu chỉ tin `loaded:[P]` do caller gửi, ai biết hash cũng giả được activation. Frontier/CAS bắt race giữa lúc plan và commit; không cần biến skills thành capability hay policy mới.

Provider skills capability is separate from offload/continuation capability. Initial values are adapter-declared `scripted_immutable_skills_v1` and `nebius_chat_completions_immutable_skills_v1`. Nebius validation uses local mock HTTP through actual native request/reconstruction code; paid calls remain disabled. Anthropic live adapter is unsupported for skills in this slice, including full-history mode; reject before dispatch, while skills-disabled Anthropic keeps existing behavior. A later profile requires its own provider/tool/prompt/recovery tests. Never infer skills support from model name, package compatibility prose or shared tool syntax. Existing offload capability remains independently required for offload mode.

## Checkpoint, restore and exact tiny trace

New checkpoint payload/manifest use `kind:"harness_skills_v1"`, `schema:3` (payload version, **not store schema**). Retain exact context-checkpoint fields and add exactly `skills_after_turn:{state_ref,state_digest}` in both. Existing `context` retains last request acceptance/source counts and post-turn history digests. A checkpoint after load contains newer loaded refs than that accepted request. Validate both copies, result/receipt/catalog integrity, raw history occurrences and authoritative dispatch frontier; reject invented or omitted successful primary loads. Legacy schema1/context-schema2 checkpoints restore only skills-disabled paths; partial/unknown formats refuse.

Recovery applies existing generation/contract/Unknown/post-checkpoint-effect and separately enforced replacement/environment rules. Reconstruct **last request** using its stored pre-response skill state, system/catalog/tools/renderer, source prefixes and exact provider artifacts. Separately derive **post-turn state** from successful load receipts covered by checkpoint frontier. Check every loaded reference against original owner, intent `skill_call`, source model acceptance, succeeded receipt and exact result. Catalog/config/package/adapter/tool/renderer drift or missing bytes fails; no discovery/planner replacement of old accepted request. Current full provider-evidence/receipt validation remains required.

**VI:** Request t0 chưa có skill; response t0 gọi load; checkpoint sau t0 đã có skill. Hai state khác nhau là đúng. Nếu restore chỉ lấy acceptance t0, sẽ mất activation. Nếu sửa acceptance t0 thành state mới, sẽ làm sai evidence request đã gửi.

Acquire a fresh owner separately; its first accepted request imports post-turn loaded refs only via the verified source checkpoint. Keep original load owner's provenance; new owner/frontier/accepted request authorize new resource calls. Old receipt replay alone grants none. New request's prior-projection chain starts in new attempt, with explicit source-checkpoint lineage. Completed checkpoint restores as completion proposal without a new send. An unresolved read-only load/resource dispatch still blocks replay under current Unknown/frontier rules.

Derived example, not measured evidence or Huy prediction: body `Read references/checklist.md.\n` is 30 UTF-8 bytes; resource `OK\n` is 3 bytes. P/C represent computed full package/catalog hashes, not literal accepted IDs.

| Step | Exact state/data boundary | Expected observation |
|---|---|---|
| Import | Files → scoped refs → package P → catalog C | Later origin mutation cannot alter captured P |
| m0 | Catalog rendered; Q0 acceptance+intent | Accepted loaded `[]`; no unique body sentinel |
| l0 | Response requests load(C,P); ordinary result+receipt | Loaded `[P,l0,result_ref]`; m0 acceptance remains `[]` |
| Same response read | Tries reading newly loaded P using m0 acceptance | Denied `not_disclosed` |
| k0 | Checkpoint m0 acceptance plus post-turn loaded refs | Restore rebuilds body-free Q0 but retains loaded P |
| m1 | New request includes exact l0 result and loaded state | Captured Q1 has 30-byte body; prompt differs, capability digest unchanged |
| Resource chunk0 | read(C,P,path,offset0,limit2), pinned to accepted state | Base64 `T0s=`, size2, next2, EOF false |
| Resource chunk1 | read(C,P,path,offset2,limit2), pinned to current accepted state | Base64 `Cg==`, size1, next3, EOF true |

Distinguishing intervention: mutate origin resource to `BAD\n` after import, then independently corrupt captured artifact. First experiment still returns `OK\n`; second fails integrity. Neither returns B as A. If Q1 exceeds request cap after successful load, l0 persists but no new model dispatch occurs. These are proposed assertions, not executed outcomes.

**VI:** Hai experiment phân biệt snapshot independence với integrity. Chunk đầu chứa O,K; chunk sau newline. Việc Q1 bị từ chối không được “undo” receipt l0, vì đó là evidence thật đã commit trước khi request được build.

## Required distinguishing tests

All rows are future acceptance evidence on disposable local stores with scripted/mock providers. Only one authored successful package fixture is required; negative inputs can be generated in tests. Loading/disclosure does not prove instructions were followed or improved outcomes. Such claims require a later controlled task oracle and fixed provider/budget/tool policy.

| ID | Assertion and defect distinguished |
|---|---|
| S1 authority | Body/allowed-tools demands forbidden command/network/write; capability/contract digest unchanged, broker denies, no process/network authority appears |
| S2 filesystem | Traversal/absolute/backslash/hidden/case collision; symlink each component, hardlink, FIFO/socket/device, replacement race; reject without hang or out-of-root bytes; artifact resource traversal also denied |
| S3 exhaustion | Cap/cap+1 for all byte/count/depth/result limits; YAML duplicate/alias/anchor/merge/tag/directive/sequence, depth9/node257, malformed UTF-8/BOM and bool integers; bounded failure, no partial catalog |
| S4 discovery→load | Capture A, mutate origin B: load exact A only; B digest under A catalog stale; missing/corrupt A fails; repeated identical declared capture deterministic |
| S5 provenance | Same-name same/different bytes across origins, duplicate entry/case collision rejected; equal bytes at different paths do not confer membership |
| S6 resource | Origin mutation after load has no effect; artifact corruption fails; deny unloaded, same-response-newly-loaded, unrelated same-task, foreign task/tenant, wrong path/provenance, inactive acceptance; EOF/UTF-8 byte chunks exact |
| S7 prompt identity | Catalog changes system/prompt/request; load changes prompt/request with fixed catalog/system/capabilities; disabled schemas byte-identical; v2 protects load/resource results from offload |
| A1 actual send | Local mock Nebius captures Q0 without body sentinel and Q1 with exact body after receipt; canonical payload equals accepted request payload and its digest; resource result bytes reach later actual request; opaque fields/call IDs preserved |
| A2 compatibility | Scripted/Nebius explicit skills capability pass construction; forged capability, unsupported Anthropic, changed model/endpoint/tool/renderer fail before send; offload capability checked separately; receive-side native reconstruction cannot waive tools equality |
| A3 persistence/retry | SQLite and opted-in local PostgreSQL: inject failures around result publication/receipt commit/model acceptance+intent; orphan result never loads; identical retry converges; changed result/provenance/state same ID conflicts; in-flight duplicate not rerun |
| A4 owner/frontier | Owner expiry/replacement, cancellation/generation, contract drift and task-event frontier changes reject new skill intent/acceptance; settled late receipt alone cannot authorize a stale owner; fabricated successful result rejected when deriving loaded state |
| R1 pre-disclosure crash | Checkpoint immediately after l0: reconstruct old Q0 with empty state, restore post-turn loaded P, fresh-owner Q1 contains exact body. Omitted/invented l0, altered body, wrong tool receipt or source-model acceptance fails |
| R2 lineage | Restore after resource use verifies original owner/provenance, source-prefix and every provider evidence pair; old receipt cannot authorize fresh resource calls; Unknown/in-flight/post-checkpoint effects refuse rewind even for reads |
| R3 versions | Unknown/partial schema rejected; legacy restore only disabled; skills→disabled and legacy→skills refused; existing store schema2/writer protocol and historical payload digests unchanged; no claimed old-writer enforcement of mandatory skills policy |
| R4 admission/effects | Load commits then force request overflow: loaded receipt persists, no new intent/send. Crash after model intent before send preserves in-flight reservation. Lost response/late settlement preserve Unknown/effect accounting; diagnostics cannot become completions |

**VI:** A1 bắt lỗi “manifest ghi skill nhưng payload gửi thật thiếu body”. R1 bắt lỗi “restore nhầm state trước tool thành state sau tool”. Test chỉ kiểm tra có key `skills` không phát hiện hai lỗi này. Mutation test phải làm các assertion này fail, không chỉ tăng coverage.

## Dependency order and handoff

1. Independent design review and document freeze completed for this design; recheck source identities before future implementation and freeze any necessary addenda first.
2. Bounded importer, serializers, single authored fixture and pure S1–S6 tests; no provider dispatch yet.
3. Broker tools and receipt-derived loaded-state validation; use ordinary dispatch/result persistence and fault/duplicate tests.
4. Versioned context/prompt/provider request construction with actual HTTP-capture A1/A2 tests.
5. Post-turn checkpoint state and fresh-owner restore R1–R4; integrate relevant existing context/protocol/accounting/recovery regressions and lint.
6. Independent source review and measured verification record; only then update implementation coverage. Human mastery remains separate.

One future integration owner should own Harness/storage/recovery edits; pure parser/protocol work and independent test/review can be separated after authorization. This dependency plan does not start implementation or delegate additional agents. Current changes are confined to this specification. Open review choices have concrete proposed defaults: schema2 per-dispatch evidence, artifact-only text resources, one package, no Anthropic skills. Any stronger mandatory policy or execution/materialization needs a new contract.

**VI:** Review spec có thể song song với release offline; code chưa tồn tại không được đưa vào claim của release candidate. Thứ tự trên đảm bảo state/recovery rõ trước khi model sử dụng feature, không thêm migration chỉ vì có metadata mới.

## External compatibility facts and evidence status

Official [Agent Skills specification](https://agentskills.io/specification), inspected **2026-10-10**, describes YAML-frontmatter `SKILL.md`, required name/description, optional license/compatibility/metadata, experimental allowed-tools and progressive metadata/instruction/resource loading. It permits scripts and additional files. This profile borrows that outer organization while restricting YAML, paths, resources and operations; **no full Agent Skills compatibility claim**. Byte/count/persistence/authority rules here are local proposals, not attributed upstream requirements. The inspected page exposed no immutable revision identifier; URL/date are retrieval provenance, not an upstream version pin.

**VI:** Format compatibility khác execution compatibility. Package hợp lệ ở client khác có thể bị profile này từ chối. `allowed-tools` là data, không phải permission; nguồn origin cũng là launcher attestation, chưa phải xác thực publisher.

Inspected working-tree SHA-256 fingerprints, not future implementation freeze:

| File | SHA-256 |
|---|---|
| `service/context.py` | `eadf2fcfa8e619953c893d6a972da1cb743a88aecfaa56aaf984c783b35eb2d6` |
| `service/harness.py` | `32bf1208b869b91774f62b59ba121a41c0200bd9bcfc429dcb4fc5039d5fdb96` |
| `service/storage.py` | `5124d010d24b9dda3f8facc2548be20f90134e968a3c1b11457702b1d99a3b3a` |
| `service/recovery.py` | `bed65f6ebeb8d208922f787e34f6ec08c51c1f4f6e66ef99e08dd8da87216d46` |
| `service/protocol.py` | `7d06d34885c7485c87fa148ab0878c99d35a81c77f81d4190c2fb4339e606af2` |
| frozen context specification | `4a508b119174d057296def4e4348d87f2da65e064c436215497277cd8079317e` |

Evidence status: source inspected; upstream format facts reported from official documentation; design/trace/test outcomes proposed or derived. Skills runtime, provider behavior, task benefit and human mastery are not demonstrated. Independent design review resolved the provenance-walk bound; root records the design freeze separately. Future implementation follows the ordered gates above. No runtime source, release artifact, paid-execution setting or human mastery record changed for this proposal.
