# Execution, provider and supported-repair code audit — 2026-10-10

Status: **read-only implementation audit; four reproduced findings, fixes proposed**. This report is the only persistent file created by this audit. CPU subprocesses and HTTPX MockTransport were used; no Docker daemon, live inference, paid API, GPU or cloud execution was started. Findings refer to the source digests below, before any subsequent integration fixes.

## Scope and authority

Read `AGENTS.md`, `context/current-state.md`, the selected H0 runtime packet, the execution/protocol/recovery rules in `capstone/07-reference-implementation-spec.md`, and current coverage/gaps in `capstone/08-implementation-coverage.md`. The source inventory inspected was:

| Source | Responsibility checked |
|---|---|
| `providers.py`, `protocol.py` | Adapter request/response identity, complete proposals, usage, error diagnostics, linkage |
| `harness.py`, `context.py` | Intent before dispatch, immutable response retention, Unknown replay, checkpoints, whole-history validation |
| `execution.py`, `verification.py` | Trusted workspace versus candidate process boundary, Docker instance ownership/retirement, protected fixture grader |
| `repositories.py` | Explicit immutable text intake, protected paths, pinned descriptor reads, selected-file Git provenance |
| `repair_provider.py`, `repair_verification.py` | Public approval, mock isolation, private stateless-function cases, identity-bound verdict/retirement |
| `repair.py`, `repair_cli.py`, `repair_demo.py`, `repair_reporting.py`, `cli.py` | Oracle-free native controller, pause/resume, final-receipt reuse, opt-in dispatch, evidence projection |

Corresponding tests were inventoried; the prior execution audit, live harness, native-provider duplicate-call regression and representative supported-repair recovery tests were read selectively and run as detailed below. This is not a proof over every interleaving or a rerun of the complete suite.

**VI:** Audit này tìm lỗi trong cơ chế đã tuyên bố hỗ trợ. Không coi các feature chưa làm như GPU runner hay active-case crash recovery là bug mới, và không suy ra năng lực model thật từ mock.

## E1 — P1: incomplete Docker inventory can release a physical slot

**Evidence:** [DockerSandbox.close — local-only](../docs/github-snapshot.md#omitted-local-evidence) derives `retired` solely from `exit_code == 0` and empty output at line 474. It does not require an acknowledged completed inventory operation. With `reason='timeout'`, empty output and exit zero, it returns `retired=True`, resets `provisioning_attempted`, and labels the observation “acknowledged inventory.” `PythonFunctionVerifier` trusts this retirement report; [RepairEngine._checks — local-only](../docs/github-snapshot.md#omitted-local-evidence) then retires the separately reserved verifier slot.

A real local CPU launcher test confirmed that timeout plus exit zero is possible: a Python process installs a SIGTERM handler that calls `sys.exit(0)`, then sleeps. `bounded_process(..., timeout=.1)` returned `{'exit_code': 0, 'reason': 'timeout', 'output': b'', 'truncated': False, 'process_group_retired': True}`. Thus this does not depend on an impossible test record.

Minimal reproduced counterexample (no actual container):

```python
from unittest.mock import patch
from service.execution import DockerSandbox
s = DockerSandbox('sha256:' + 'a' * 64)
s.provisioning_attempted = s.created = True
s.container_id = 'b' * 64
with patch('service.execution.bounded_process', return_value={
    'exit_code': 0, 'reason': 'timeout', 'output': b'',
    'process_group_retired': False, 'truncated': False,
}):
    assert s.close()['retired'] is True  # observed defect
```

**Minimal fix contract:** the launcher owns process-completion evidence; DockerSandbox owns physical-instance evidence; RuntimeStore owns slot release. A successful authoritative launcher observation requires exit zero, `reason == 'exited'`, `process_group_retired is True`, and no truncation. Apply a single narrow predicate consistently to container binding ([line 286 — local-only](../docs/github-snapshot.md#omitted-local-evidence)), nonce recovery ([line 306 — local-only](../docs/github-snapshot.md#omitted-local-evidence)), create/start/copy, final inventory, and image inspection in legacy LinuxVerifier. Known instance ID and nonce remain immutable. Incomplete inventory retains the slot and provisioning state. A failed `docker rm` followed by a complete acknowledged inventory proving the owned ID absent may still establish container retirement; do not require removal exit zero unnecessarily. Report removal acknowledgement using the same completion semantics.

**Distinguishing experiment:** parameterize exit-zero timeout, output-limit/truncated, and unretired launcher observations at every identity/retirement gate. No such observation may grant a container binding or successful retirement. Preserve passing cases for nonce match and failed-remove/complete-absent-inventory. Use complete process records in mock fixtures instead of defaulting missing evidence to success.

**Scope:** this repairs the current synchronous lifecycle. It does not deliver the already documented write-ahead physical-instance journal or process-loss recovery supervisor.

## E2 — P1: Anthropic follows an injected client's cross-host redirect with its API key

**Evidence:** [AnthropicMessages.receive — local-only](../docs/github-snapshot.md#omitted-local-evidence) does not set `follow_redirects=False` on its individual `stream` request. The default client disables redirects, but the public constructor accepts an injected HTTPX client. Under `follow_redirects=True`, a mock 307 response redirected the request and `x-api-key` to a second host. Native Nebius already disables redirects per dispatch.

Measured request list, using only a synthetic dummy credential and MockTransport:

```text
https://api.anthropic.com/v1/messages     x-api-key=AUDIT-DUMMY-KEY
https://other-host.invalid/receiver      x-api-key=AUDIT-DUMMY-KEY
```

Reproduction: construct `httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)`. Handler returns a 307 with `Location: https://other-host.invalid/receiver` on request one and a complete mock response on request two. Pass this client to `AnthropicMessages(..., enable_network=True)` and call `request(...)`. Two requests were observed.

**Minimal fix contract:** the adapter owns the frozen destination for every dispatch, regardless of ordinary client redirect defaults. Pass `follow_redirects=False` directly to `stream`. Do not silently retry the redirect or change endpoint. In the harness, preserve the existing Unknown handling and reservation because no trusted bill/effect reconciliation has occurred.

**Distinguishing experiment:** HTTPX MockTransport with redirect-enabled client and 301/302/303/307/308 responses must observe exactly one request to the official endpoint and no redirected credential/request body. No real credential or network connection is needed.

## E3 — P2: Anthropic completions do not enforce frozen response model identity

**Evidence:** [parse_anthropic_response — local-only](../docs/github-snapshot.md#omitted-local-evidence) validates role/type/stop/content/tools/usage but never checks `raw['model']`. [AnthropicMessages.complete — local-only](../docs/github-snapshot.md#omitted-local-evidence) and [Harness.run — local-only](../docs/github-snapshot.md#omitted-local-evidence) pass no expected model. A complete mock response with `model='other-model'` was accepted as terminal for a `frozen-model` request. Missing model is also accepted by current mocks. Nebius explicitly checks the response model.

**Minimal fix contract:** response proposals must match the explicitly frozen adapter identity. Add an expected-model argument to the Anthropic semantic parser, required by live adapter/harness callers; preserve fixture compatibility deliberately if the pure scripted parser remains independent. Reject missing, malformed or differing identities before tools or completion checkpoints. Preserve the raw response artifact and the separation between trustworthy usage processing and proposal validation; do not move all semantic checks before raw persistence or simply discard the bill on a rejected completion. Any permitted provider aliases need a separately frozen mapping, not unconditional acceptance. The pricing interpretation of an actual provider returning another model remains a live-conformance issue; these mocks prove proposal identity behavior only.

**Distinguishing experiment:** missing and changed response model with otherwise valid usage and a valid write proposal must retain exact raw bytes, dispatch no tool, create no completion checkpoint and issue no new request on replay. An exact model response must still work. Update live mock fixtures to include their explicit model rather than weakening the new check.

## E4 — P1: Anthropic history rejects a duplicate call only after a new tool effect

**Evidence:** the [pre-dispatch history validation — local-only](../docs/github-snapshot.md#omitted-local-evidence) is conditional on `native`. Anthropic/scripted proposals only validate duplicate IDs within the current response, then rely on the next turn's `project_context` for whole-history linkage. A repeated old ID may be preceded by a new valid write in the same response. The write executes before whole-history rejection. The broker prevents replay of the old effect but does not undo the new effect.

Reproduced with a real temporary SQLite store, LocalArtifacts and Workspace; all source bytes were disposable:

```python
model = ScriptedModel([
    [ToolCall('repeat', 'read_file', {'path': 'a.py'})],
    [ToolCall('new', 'replace_text', {
        'path': 'a.py', 'expected_digest': digest_bytes(b'old'),
        'old': 'old', 'new': 'new',
     }), ToolCall('repeat', 'read_file', {'path': 'a.py'})],
])
# Harness(..., max_turns=3).run(...) raises ProtocolError on the third turn.
# Observed workspace afterward: {'a.py': 'new'}.
```

Measured rejection was `duplicate or misplaced tool use`; a `replace_text` dispatch was durably present. The scripted adapter shares the exact affected Anthropic proposal path. Native's corresponding existing regression rejects before the new effect.

**Minimal fix contract:** validate the complete proposed assistant message against prior exact messages, with synthetic matching result envelopes, before admitting any tool from that response. Use `validate_linkage` for Anthropic and `validate_nebius_linkage` for native; preserve opaque blocks and original response bytes. No source/workspace mutation, completion proposal, or checkpoint may follow an invalid call-history proposal. Billing/raw evidence stays separate and retained.

**Distinguishing experiment:** first turn has one known read ID; second response has a new write followed by the reused read ID. Assert unchanged workspace and no new tool dispatch, while the second model receipt is retained. Also test reused finish IDs and valid multi-call batches. This is a targeted parity refactor, not a universal provider abstraction.

**VI:** Ví dụ E4: model gửi `[edit mới, call cũ bị trùng]`. Parse từng call đều đúng chưa đủ; cả lịch sử phải hợp lệ trước khi chạy edit đầu tiên. E1 tương tự ở tầng máy: output rỗng sau timeout không chứng minh container đã biến mất.

## Checks measured in this audit

The following bounded baseline selection passed unchanged, demonstrating that the current tests do not detect these newly reproduced cases:

```sh
.venv/bin/python -m pytest -q \
  tests/test_live_harness.py tests/test_audit_execution.py -m 'not docker' \
  tests/test_nebius_provider.py::test_duplicate_call_id_across_turns_rejected_before_second_effect \
  tests/test_repair.py::test_uncertain_test_cleanup_retains_auxiliary_slot_and_refuses_resume \
  tests/test_repair.py::test_known_final_receipt_survives_publication_crash_without_retesting
```

Result: **25 passed, 4 Docker tests deselected, 1 existing Starlette/httpx deprecation warning, 3.00 seconds**. Separate inline CPU reproductions established E1–E4 as described above. No full regression suite was rerun, and no proposed fix has been tested by this read-only audit.

## Correct boundaries and known gaps preserved

- Native non-success diagnostics remain bounded, sanitized, non-authoritative records; they cannot authorize tools after reconciliation. Configured credential filtering is not general DLP. No new defect was reproduced in that reviewed path.
- Supported repair's private recipe inputs stay outside worker/public artifact access. Final checks use a fresh container per stateless case and trusted external comparison. The function bridge returns candidate assertions/values, not a trusted verdict. Passing receipt identity and actual model capability remain separate claims.
- Clean checkpoint replacement, completed final-receipt reuse, Unknown blocking and uncertain test-environment retention are implemented. Active-case controller loss lacks a durable physical-instance journal and is expressly unsupported; that is an existing coverage gap, not E1.
- FrozenRepository is bounded control-plane intake, not isolation against a hostile concurrently mutating host filesystem. Workspace similarly handles trusted control-plane bytes; candidate Python executes in separate containers. Do not expand this audit into host race hardening without changing the supported threat model.
- Context overflow fails closed. Automatic accepted compaction, LSP, GPU recipes, profiler protocols, failure-evidence promotion and arbitrary repository execution remain proposed or documented gaps. NVIDIA NV-S0 is CPU numerical evidence only.

For NVIDIA alignment, repair E1 before reusing lifecycle evidence in NV-S1. E2–E4 strengthen current provider/controller contracts and should be fixed without adding a second executor or evaluator. Keep the next shared failure-evidence adapter scoped to its existing spec; GPU source/build/measurement needs its own explicit contracts and authorized hardware envelope. Current hackathon repair/access delivery remains the priority; paid execution remains disabled.

## Pre-fix source identities

```text
service/providers.py fa370e8688d366969ccb67984b4a28154af8487bb16243e892a8f7a8917e56bf
service/protocol.py 68e310ed998b64a649a29465cee158ef2cf5f8eaba7df6dfeba7b789a757049d
service/harness.py ff3b3b6fc9270760fcbd8766aa70ce38cf4374e159977177d0795d8f35e48bd7
service/context.py 214401dd83868ab2b4c79a50d119c9af9d6088fa4a58eab6a04e18825282cd4a
service/execution.py 6059854ea39ba403b769c44e2205bbdbb94fa94e552b3061295462ccb194aa6a
service/verification.py 7d74ab3ce0ff4377f4e4c8c49c11e4bdd926179aa455130a65cedca34fe66f60
service/repositories.py b39676ea101aec719582124a414702a60efb6e125bfdabed4fd571802cb5597b
service/repair.py 363add06b7bb398fcc78557a752b27eabe6cf6fe67ac460fcc96e93c0c0c29bb
service/repair_cli.py 0823244953f997f30a9f896dec0ec798c123b5032c4b2b3a5b8f47c2cb576ab5
service/repair_demo.py 6bdc067a863bf5f6a3c8ab46623f46862dcec3363ed590a5e364756bf71f1016
service/repair_provider.py b91fd7a95ef527d7118f3c10522196b286670c2eb035c83e99d3ed5d76b0354d
service/repair_reporting.py f87e035e7f6bf8fe9e8ad5fe5389d96075a2722750d422ffd8e6ac2d356c68da
service/repair_verification.py a0ce818578c99865fb7e8ee5fb8eab1dbd6ca7383d95f3fd8d1608998effa6bd
service/cli.py fe0fd2084eac33d6423cef90e9f49a10b41cebc48fff13c87a286a38db85a0ea
```
