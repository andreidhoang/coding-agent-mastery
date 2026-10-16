# X1–X4 execution fixes — 2026-10-10

AI-written bounded implementation against the frozen [refactor specification](codebase-refactor-spec-2026-10-10.md) and [execution audit](codebase-audit-2026-10-10-execution.md). No human mastery, live inference, paid execution, GPU or production-readiness result is inferred.

## Independent review correction: model identity before monetary settlement

The X3 addendum was frozen before this follow-up patch; [freeze record — local-only](../docs/github-snapshot.md#omitted-local-evidence) preserves its specification digest. Valid counters cannot bind the requested model's rates when the response model is missing or different. Both live adapters now check exact response identity immediately after strict decoding and before `ProviderEnvelope.charge`. The full raw response, including counters, remains immutable. Known received effect is `succeeded`, `actual_units` is `None`, billing stays `liability_unknown`, and the reservation remains. Replay validates the retained receipt, sends no new request, performs no tool and makes no charge calculation. Correct-model responses with malformed tool/finish semantics still independently settle trustworthy usage.

This correction supersedes the initial X3 settlement wording below only for wrong/missing response-model identity. The earlier measurements and implementation description remain as a dated initial delivery record. No already-settled historical record is rewritten. The reproduced issue is unsupported price attribution in mock evidence, not a measured real provider undercharge.

**VI:** Token count nói số lượng, còn `model` khóa cách áp giá. Nếu model sai hoặc thiếu, code giữ counters/raw nhưng không được biến chúng thành tiền settled bằng rate của model đã request. Replay không cấp lại quyền tính tiền hoặc chạy tool.

The revised test in `tests/test_codebase_execution.py` covers missing/wrong identity, tool/terminal response, both live protocols, and two invocations per case. A spy proves `ProviderEnvelope.charge` is never called; assertions require exact body retention, no checkpoints or tools, spent zero and full remaining reservation. It produced **8 failures, 58 deselected** before the billing patch, all because the old code settled the charge. The existing native `wrong_model` semantic control intentionally changed to unresolved billing under the frozen review correction; all eleven other semantic controls retain their original settled-usage expectation. No fixture/expectation changes were made elsewhere in this follow-up.

```text
.venv/bin/python -m pytest -q tests/test_codebase_execution.py tests/test_live_harness.py tests/test_nebius_provider.py -k 'bad_identity or invalid_semantics or unusable_message or live_adapter_runs or native_read_edit_finish or valid_multi_call or cache_premium'
28 passed, 118 deselected in 1.75s

.venv/bin/ruff check service/harness.py tests/test_codebase_execution.py tests/test_nebius_provider.py
All checks passed!
```

The new execution test file now contains 66 parametrized controls; the follow-up selected the affected identity/billing and valid-path cases rather than repeating all unrelated checks. Full integrated checks remain the coordinator's responsibility.

## Initial delivery record, before the billing correction

The supervisor owns launcher completion and immutable container observations; the durable harness owns response retention/accounting and tool admission. Receiving bytes is distinct from accepting proposals. Prediction: incomplete lifecycle observations and invalid model/history identities must reject before authority or effects, while valid controls retain existing behavior.

**VI:** Exit zero sau timeout không chứng minh inventory đã hoàn tất. Bản đầu đã giữ raw và settle charge khi response sai model; independent review chỉ ra rate chưa được chứng minh, nên phần sửa phía trên thay behavior đó bằng `liability_unknown`. Các số đo dưới đây thuộc bản đầu, không phải contract hiện hành.

### Initial changes

- **X1:** `service.execution._acknowledged_process_result` requires an integer exit zero, reason `exited`, `process_group_retired is True`, and `truncated is False`; absent fields fail closed. Applied to immutable-ID binding, nonce recovery, create/start/copy, final inventory and removal acknowledgement. A name-conflict rejection also requires complete normal launcher termination before clearing provisioning state. Incomplete candidate launcher completion triggers owned cleanup. An unacknowledged/failed removal followed by complete authoritative absence may still retire the instance. Incomplete inventory retains ownership/provisioning state.
- **X2:** Anthropic's credential-bearing `stream` call sets `follow_redirects=False` per request, overriding an injected redirect-enabled client. No fallback/retry added.
- **X3:** `parse_anthropic_response` accepts a backward-compatible optional `expected_model`; convenience adapter and live harness enforce exact identity, including receipt replay. Missing/wrong model rejects after exact raw bytes and trustworthy usage have been retained/settled. Offline/scripted parser compatibility remains. Existing successful/semantic-error mocks now explicitly identify their intended model; assertions are unchanged.
- **X4:** Both supported protocol paths validate the complete proposed assistant batch against prior history before any broker effect. Temporary complete result placeholders only validate linkage; they are never persisted. Duplicate prior read/finish IDs block a fresh edit even on the final permitted turn; replay sends no second request. Valid multi-call edit/finish remains supported.

`service/verification.py` legacy Linux image preflight was flagged to the authority owner for the same X1 predicate. `service/repair_verification.py` already has the equivalent completion checks; it was inspected and left untouched by this lane. No schema, route, public provider abstraction or external execution was added.

### Initial measured checks

Before source changes, the first 51 new parametrized controls yielded **45 failed, 6 passed**. Failures distinguished incomplete inventory/binding/start/copy, inaccurate removal acknowledgement, redirected credential dispatch, absent/wrong model acceptance and fresh-edit effects preceding cross-history rejection. Existing complete absence/valid batch controls passed. Four later missing-evidence and seven name-conflict controls extended the final new file to 62 tests.

After the patch:

```text
.venv/bin/python -m pytest -q tests/test_codebase_execution.py tests/test_live_harness.py tests/test_protocol.py tests/test_audit_controller.py tests/test_review_regressions.py tests/test_audit_execution.py -m 'not docker'
107 passed, 4 deselected in 2.41s

.venv/bin/python -m pytest -q tests/test_codebase_execution.py tests/test_nebius_provider.py::test_nebius_cache_premium_envelope_rejected_before_dispatch_and_anthropic_unchanged tests/test_nebius_provider.py::test_duplicate_call_id_across_turns_rejected_before_second_effect
64 passed in 0.87s

.venv/bin/ruff check service/execution.py service/providers.py service/harness.py tests/test_codebase_execution.py tests/test_live_harness.py tests/test_protocol.py tests/test_audit_controller.py tests/test_review_regressions.py
All checks passed!
```

Counts overlap; they are not a cumulative independent total. A previous broader focused run yielded 162 passed, 4 deselected, and one failure in the successful Anthropic cache-premium control because its mock omitted `model`; adding its exact intended `MODEL` preserved the test's original assertions and the targeted rerun passed. Snapshot dispatch order is not relied on by new tests because equal timestamps can reorder observations.

These results exercise mocked Docker observations, real temporary SQLite/artifacts/workspaces, and HTTPX MockTransport. Actual Docker lifecycle integration and the full integrated regression/lint pass belong to the coordinator's final verification. The synchronous lifecycle fix does not implement active-case crash recovery or a physical-instance write-ahead journal. Historical source/runs were preserved.
