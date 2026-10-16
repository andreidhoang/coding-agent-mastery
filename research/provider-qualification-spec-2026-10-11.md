# Offline provider qualification and prepared-repair handoff

Date: **2026-10-11**. Status: **FROZEN before implementation**. Owner: reference control plane. This slice addresses the next essential hackathon G1/G2 preparation seam; it does not complete either live gate. Paid/live inference, GPU rental and publication stay disabled.

## Purpose and first principles

A supplied provider approval is a policy assertion. A protocol transcript is an observation. A repair task is a separate authority object. Bind the three without converting an observation into permission. Reuse `ProviderApproval`, `Harness`, `RuntimeStore`, `LocalArtifacts`, native Nebius parsing/accounting and the existing repair CLI. No parallel runtime, provider adapter, benchmark evaluator, automatic recovery or hosted service.

**VI:** Một receipt chứng minh đã nhận bytes; nó không tự chứng minh model có trên account, giá đang đúng, hoặc người dùng cho phép trả tiền. Slice này nối các identity để lần chạy thật sau này có thể kiểm tra đúng cấu hình và đúng task.

## Public surface and ownership

Add `service/qualification.py` and `service/qualification_cli.py`, registered by the existing `agent-lab` CLI. Four commands:

- `qualification-prepare --output NEW --repair-output EXISTING --execution-deadline UNIX --review-deadline UNIX`: freeze a new manifest against one existing **unstarted** repair prepared by the supported repair CLI/API. No provider traffic, candidate execution or repair-state writes. Local immutable Docker image inspection is allowed solely to revalidate the existing environment identity.
- `qualification-run --output PATH`: execute exactly one offline native mock probe. There is no live/network/credential option and no environment credential discovery.
- `qualification-report --output PATH`: validate and inspect saved immutable evidence, without dispatch or retry.
- `qualification-handoff --output PATH --repair-output EXISTING`: revalidate all evidence/current source and the identical still-unstarted prepared repair; publish an immutable advisory handoff inside qualification output. It never calls repair-run, edits repair authority or enables execution.

Python entry points `prepare_qualification`, `run_qualification`, `read_qualification_report`, `create_qualification_handoff` match those operations. Return JSON-compatible detached data. CLI output should clearly show offline evidence, live gates pending and no execution authority.

The repair RuntimeStore owns the original task. The qualification RuntimeStore owns a separate synthetic probe. Artifacts own immutable evidence bytes; output files are write-once indexes. The caller owns local control-plane directories, not hostile filesystem isolation. Concurrent downstream repair start is not locked by an advisory handoff: it certifies a point-in-time snapshot only.

## Frozen inputs and strict identity

The manifest has exact keys/schema and canonical bytes; reject duplicate JSON keys, bool-as-int, unknown/missing fields, unsupported values and malformed digests. The manifest type must be immutable with detached exports. Freeze:

1. Offline-only mode, fixed probe revision, one owned harmless text fixture, read_file then finish, max two model turns, bounded context, finite explicit ordered deadlines, and synthetic ledger budget equal to two existing provider-envelope bounds (with overflow validation).
2. The exact validated `ProviderApproval` including original evidence kind/identity and rate snapshot. Never relabel mock or operator-verified inputs as live-observed. The default synthetic fixture uses nonzero rates so accounting tests distinguish dropped liabilities. No secrets or headers.
3. The complete relative `.py` path set and byte hashes of the service package, including subpackages. Resolve package files from the running installation. Compare the entire set and bytes at run and handoff; manifest/report validation must not silently regenerate identities after drift. Preserve uv.lock/schema/workload assets.
4. Prepared repair binding: tenant/task identity, service incarnation, generation, complete contract and private-input **digests**, image identity, snapshot/frontier digest. Read exact original private input bytes using their artifact digest and existing repository/recipe/approval validators; revalidate repository/base/recipe/provider/model/rates and image/environment consistency. Do not copy private recipe cases, issue or repository contents into public qualification artifacts. Require expected single queued repair node, generation1, no attempts, dispatches, sandboxes, candidates, checkpoints, verifications or reviews. Reject canceled/started/drifted/missing roots.

Inspect the existing repair DB without modifying it: SQLite read-only snapshot/backup into a disposable copy followed by existing RuntimeStore read APIs is acceptable. Never bootstrap a missing input DB. Qualification output must be fresh/exclusive and must not overlap the prepared repair root; immutable indexes use atomic no-overwrite publication. Frozen state is not an assertion of account availability or prices.

## Execution and failure contracts

Internally create an exact HTTPX Client with all transport routes restricted to MockTransport and a literal synthetic key; enforce isolation independently of approval evidence kind. Credentials present in environment have no effect. No caller-supplied live client, endpoint override, redirect path or enable flag. Fixed mock replies retain opaque assistant fields and produce one read_file call, then one finish call. Run through existing Harness and its intent-before-send ledger; tools receive only read_file/finish capability on the owned fixture. No candidate source execution, shell, verifier call, GPU or model catalog lookup.

Publish a durable exclusive started marker **before first dispatch**. A repeated command may return a verified completed report; if there is a marker without final evidence, fail closed and retain DB/artifacts for inspection. Never create a fresh attempt/task to retry. Concurrent callers cannot both execute. Any failed/malformed/ambiguous response retains its raw receipt and normal billing semantics; timeout/Unknown retains unresolved liability, never resends and cannot pass or hand off. Distinguish parsed usage charge from tool-protocol failure: malformed tool content can have settled billing, invalid model/usage cannot infer zero charge. Synthetic ledger amounts are not real payments.

Retire the synchronous trusted local probe reservation only after its work stops, using explicit local retirement evidence; this must not settle Unknown billing, authorize replacement, or claim physical GPU/container retirement. No automatic recovery. A process death before final evidence remains interrupted and inspectable.

## Evidence and handoff

Content-addressed report bundle binds manifest and source identities, exact durable request/raw-response refs, dispatch snapshot/frontier, committed events and error category (never secret-bearing exception strings). Validate all linked refs, sizes/scopes/digests and required histories before reporting pass/handoff; a summary's boolean is never the sole oracle. No provider header or key persistence.

The successful check must independently derive from stored records: exactly two native requests; first assistant opaque message preserved in second request; broker-produced read result has the matching tool_call_id and exact fixture bytes; second finish is only a completion proposal; all required dispatches and usage are valid/settled; fixture unchanged. Report explicit `offline_mock`, original supplied evidence separately, `live_observed=false`, `g1_passed=false`, `g2_passed=false`, `execution_authority=false`. Account/catalog/current prices and useful live repair remain unobserved.

Handoff is allowed only for a valid successful offline transcript and exact current prepared repair binding. Record qualification manifest/report/source and repair binding identities. Export the unchanged approval only if needed; do not create a new approval or modify evidence-kind/rates. A repeated identical handoff converges on the original bytes, while corruption/drift rejects. It is advisory preparation for the existing repair CLI, never a permission token consumed by dispatch.

## Distinguishing tests and delivery order

1. Freeze this spec and record its digest before code. Implementation and independent test agents receive the contract separately.
2. Positive two-request native continuation uses existing store/adapter/harness, exact raw refs/opaque linkage, settled nonzero synthetic ledger; original repair state remains byte/logically unchanged.
3. Network-negative checks even with ambient credentials/operator evidence; no outbound socket/catalog or GPU/subprocess except declared image inspection. No live enable flag.
4. Strict schema/type and source-set drift; approval/model/rate/task/image/frontier changes reject; private inputs/keys do not leak. Prepared-state start/cancel and directory overlap reject.
5. Failure/duplicate controls: timeout and bad usage retain liability, malformed tool/native response does not qualify, duplicate run never resends, interrupted marker never restarts, concurrent run admits once; corrupt/missing raw refs or forged pass summary blocks handoff.
6. Independent review and targeted mutation controls against lost-native-history, Unknown retry or dropped evidence validation. Repair any findings, retain negative results and rerun affected checks. Appropriate existing native/repair/accounting/CLI/package regressions; no needless full backend retest when unchanged.
7. Extend standalone installed acceptance with this slice. New candidate in a fresh directory, reuse verified local wheelhouse and unchanged builder; fresh outside-checkout Python -I, network denied, no source imports, origins match manifest. Preserve rc1/rc2 byte-for-byte. No fresh-machine/bit-repro/live/production claim from this gate.
8. After acceptance, update core docs/context/coverage/hackathon/release navigation and a compact first-principles trace. Human mastery remains unchanged. Record exact artifacts, test counts, failures, source identities and remaining live authorization/account/model/rates/budget/task gates.

Primary existing references: `service/repair_provider.py`, `service/repair_cli.py`, `service/repair.py`, `service/harness.py`, `service/providers.py`, `service/storage.py`, `tests/test_nebius_provider.py`, [readiness plan](system-readiness-plan-2026-10-11.md), [hackathon gates](../hackathon/README.md). Official [Nebius integration guidance](https://dev.nebius.com/cookbook/opencode-nebius-token-factory) and [API docs](https://api.tokenfactory.nebius.com/docs), inspected 2026-10-11 in the priority review, distinguish current account/catalog inputs from generic integration examples. No model ID, price or account availability is inferred from that documentation.
