# Immutable skills: first capture slice

Date: **2026-10-11**, Asia/Ho_Chi_Minh. Status: **FROZEN BEFORE IMPLEMENTATION; reviewed by an independent Astra agent**. Huy authorizes building immutable skills starting with the smallest slice. This delivery implements dependency step 2 of [the frozen full design](immutable-skills-spec-2026-10-10.md): bounded immutable capture, exact serializers/validation and one authored fixture. The original design remains unchanged. Broker loading/disclosure, model requests and typed recovery follow later in their specified dependency order; no runtime activation is claimed here.

## Purpose, owners and invariant

A trusted launcher selects an explicit local skill root. The importer validates bounded source bytes and publishes scoped immutable artifacts; a catalog binds those packages. The artifact store owns bytes, the catalog owns membership and the caller owns declared provenance. None owns execution authority. Existing RuntimeStore, capabilities, protocol, providers, harness, checkpoints, billing and historical artifacts remain unchanged in this slice.

The distinguishing experiment captures resource `OK\n`, changes the origin to `BAD\n`, then resolves the snapshot: returned bytes remain `OK\n`. Separately corrupt the stored original: resolution refuses. A correct content digest is insufficient if its package/catalog/scope association is wrong. Results are AI engineering evidence; Huy's mastery remains unassessed.

**VI:** Một snapshot đúng phải độc lập với source sau lúc capture, nhưng vẫn phải kiểm integrity khi đọc. Skill là dữ liệu; slice này không thể cấp quyền gọi tool hay thay checkpoint.

## Clarifications fixed before code

- Use exactly **PyYAML 6.0.3**, pinned in project requirements and `uv.lock`, with its pure-Python event parser; do not call constructors/`load`/`safe_load`. Reject forbidden events before constructing mappings. Node count is scalar plus collection-start events; root mapping has depth 1. Plain scalar tokens such as `yes`, `123` and `null` stay strings; JSON integer fields still reject booleans. Reject YAML directives, explicit tags, aliases, anchors, merge keys, sequences, duplicate keys and multiple documents. A bounded parser state machine constructs only string/mapping objects after event checks. [Official event API](https://pyyaml.org/wiki/PyYAMLDocumentation), [fixed release metadata](https://pypi.org/pypi/PyYAML/6.0.3/json), inspected October11. This is a compatibility pin, not a latest-version claim.
- All config limit values must equal the frozen table's exact integers; no lower/higher override in this first profile. Depth/node checks remain exercised at parser level even when later metadata validation would reject the structure. Some byte caps are dominated by stricter inner caps; do not invent reachable passing boundary cases.
- Frontmatter starts `---\n` and ends at an exact LF-terminated `---\n` delimiter line. Its byte cap counts YAML payload excluding delimiter lines. Body starts immediately after the closing LF and remains byte-exact. Full `SKILL.md` cap includes all bytes. Preserve the original UTF-8/LF/no-BOM/no-NUL rule. Nested metadata entry/scalar limits apply to the `metadata` mapping; named limits and total frontmatter cap constrain other fields.
- Count directory entries excluding the package root; path depth counts every relative component (`references/checklist.md` has depth 2). Traverse trusted root ancestors as well as descendants with no-follow directory descriptors; relative input roots use lexical absolute paths without resolving symlinks first. Reject unsupported OS descriptor primitives explicitly. Within the package, all files/directories stay on the root device. Reject file hardlinks and all nonregular files; nonblocking file opens precede kind validation. Inventory rechecks and per-file identity/size/time checks provide the bounded quiescent-fixture guarantee, not atomic capture under hostile concurrent mutation.
- Content types are `text/markdown` for full skill/body, `text/plain` for text resources, and `application/json` for config/package/catalog. Closed references validate scope, digest, strict size and exact expected content type. Canonical artifact JSON must re-encode identically. Resolving a catalog re-parses full captured `SKILL.md` and checks metadata/body equality, package naming/provenance and resource membership, all bounds and captured resource bytes; valid individual hashes cannot excuse inconsistent associations.
- Minimal shared artifact change: `LocalArtifacts.get` and `S3Artifacts.get` gain optional keyword-only `max_bytes`. A supplied limit is a positive non-bool integer; effective read cap is the smaller of this limit and the store's existing cap. Read at most cap+1 before size/hash validation. Existing omitted-argument calls retain behavior. Skills validate references before calling the bounded reader. Do not implement a second artifact filesystem reader.

## Frozen public seams and data shapes

Module `service/skills.py` owns these trusted control-plane data operations. It exposes a bounded `SkillError(ValueError)` with a stable `code` and sanitized message; no host path, input dump or parser traceback in public messages. Internal exceptions may be chained only if public delivery never exposes that traceback. Tests inspect exact codes where relevant.

```python
def default_skills_config(origin, source_revision, catalog_revision): ...
def validate_skills_config(config): ...
def parse_skill_file(raw, package_name, config): ...
def capture_skill_catalog(package_roots, artifacts, tenant_id, task_id, config): ...
def read_catalog_snapshot(artifacts, tenant_id, task_id, capture, config): ...
def read_skill_resource_snapshot(artifacts, tenant_id, task_id, capture, config,
                                 package_digest, path, offset, limit): ...
```

`parse_skill_file` returns `(validated_metadata, exact_body_bytes)`. `capture_skill_catalog` accepts an explicit bounded sequence of package-root paths and returns exactly `{config_ref,config_digest,catalog_ref,catalog_digest}`. Config/package/catalog persisted records retain the original frozen exact fields and hashes. Zero or more than one root is rejected; duplicate/case-folded names are rejected before selecting anything. Failed capture may leave unreferenced content-addressed artifacts but returns no partial catalog or execution state.

`read_catalog_snapshot` returns trusted ephemeral `{config,catalog,packages}` where each package is `{manifest,package_digest,body,resources}`; body is exact bytes, resources map exact relative paths to bytes. These in-memory objects are data copies, not new persisted schemas. Every call validates captured scoped artifacts, including associations above. It never reads the source directory. `read_skill_resource_snapshot` verifies that snapshot then returns the original design's exact base64 resource value `{catalog_digest,package_digest,path,digest,offset,total_size,size,next_offset,eof,encoding,data}`. Range checks exclude booleans and enforce positive limit, EOF and the fixed read/result caps.

These helpers do **not** check loaded/disclosed membership, current owner or accepted model response. Future broker code must establish those conditions before using them. Do not expose them as tools or name them authority/activation APIs. Load-result rendering/wrapping is deferred until broker provenance exists, so wrapper-size claims remain pending.

## Changes, tests and exit

Bounded edits: new `service/skills.py`; optional read caps in `service/artifacts.py`; PyYAML pin/lock addition without upgrading existing packages; one authored `workloads/skills/verified-repair-guide/` with `SKILL.md`, `references/checklist.md` and `assets/example.json`; package-data and future curated-export selection for those exact owned fixture assets; independent tests and a local trace. The 42-task benchmark registry and its locks remain unchanged. Existing release archives/wheels/manifests remain immutable historical candidates; this slice does not refresh or inherit their installed acceptance.

Independent tests exercise parser rejection and bounded growth, descriptor-based traversal/races/file kinds, fixed config validation, source mutation versus artifact corruption, deterministic identities, origin/path/scope association, strict serialized record validation, detached return objects, exact UTF-8 byte chunks, artifact cap+1 and source-to-wheel fixture presence. S1 proves only that capture does not execute or mutate capabilities; S6 covers snapshot membership/scope/bytes, **not** future broker disclosure/owner enforcement. S7/A1–A4/R1–R4 remain future runtime gates. Inject publication/read failures: no successful partial catalog; orphans grant no state. Preserve negative evidence.

Before acceptance, independent review tests plausible flawed alternatives and requires repairs without weakening the contract. Run focused new tests plus affected artifact/package/context regressions and Ruff; broaden only for changed dependencies or unresolved behavior. Record source hashes before/after verification, parser/toolchain versions, fixture/catalog identities and preserved original files. Reconcile core docs and context to **capture foundation delivered, runtime skills pending**. Paid execution, account discovery, installation/scripts triggered by skills, provider calls, GPU/hosting, publication and human mastery remain disabled or unclaimed as applicable.
