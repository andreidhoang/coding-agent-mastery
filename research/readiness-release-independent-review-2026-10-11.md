# Readiness release independent acceptance review

Date: 2026-10-11. Authority: [frozen readiness release contract](readiness-release-spec-2026-10-11.md) and [original offline release contract](offline-release-spec-2026-10-10.md). This lane owns only the standalone acceptance script and its test evidence. Product source, historical October10 release and live/paid execution are unchanged by this lane.

## Pre-freeze acceptance review

The root-authored extension was inspected against installed-only acceptance. Its initial bytes and issues are preserved under `runs/system-readiness-2026-10-11/release-tests/acceptance-before-independent-review.{py,json}`.

Four acceptance weaknesses were repaired before the new manifest freeze:

- A separate interpreter importing two modules could not establish the actual worker's origins. The configured-service case now narrowly instruments the product's exact child launch during that case. The same installed interpreter calls the original `service.offline_server.main` with unchanged worker arguments, environment, working directory and inherited ownership descriptors. The actual child records its PID, interpreter and every loaded product source origin/hash at exit. Socket connections remain denied. This observational wrapper is reported explicitly; independently measured unmodified loopback HTTP remains separate serving evidence.
- New skills request equality could accept Python Boolean/integer aliases. Captured payloads now reconstruct the canonical accepted request wrapper and must match the manifest/intent digest; raw wire bytes have a separate hash. The case asserts typed post-turn checkpoint schema/kind, exact same-response `not_disclosed` failure, unchanged authority during restore, exact native transcript, original primary provenance, fresh chain/checkpoint lineage and advancing epochs.
- A GPU `not_run` string alone was weaker than the no-execution contract. The installed planner runs with `execute=False` and a launch control that raises on child execution, asserts no Torch import/hardware samples and verifies every plan source hash against installed bytes and the frozen manifest. Missing installed `uv.lock` remains an explicit null identity.
- Journaled wrong-candidate acceptance could pass on infrastructure error. It now requires an actual assertion mismatch and `outcome=fail` with no boundary failures, exact tree/grader/environment identities, per-instance bound/absence observations matching immutable IDs/nonces/daemon identity, and a separate Docker inventory showing each container absent. Known cleanup remains read-only and produces no verification receipt or money.

Syntax compilation, actual-worker wrapper compilation and Ruff passed. The acceptance source is quiet at SHA-256 `846ebe94e0ea3015fbf4bbcd2a6723aedb3dcfb78c1c08a245ad50657719f6a0`.

## Measured installed candidate

The reviewed source was frozen into **161 curated entries**, built as the new `releases/offline-2026-10-11-rc2` candidate and installed offline into `/private/tmp/coding-agent-offline-2026-10-11-rc2/venv`. The isolated install used **19 original local lock/hash/size-checked dependency wheels**, yielding 20 distributions including the product on Python3.12.11. No wheel download, live-provider call, Docker image pull or GPU work occurred in this lane. The separate dependency-preparation record owns prior public binary acquisition.

Two operation-document commands were corrected with root authorization before freeze: the service requires `serve --config PATH`; the GPU planner requires `--config PATH`. Their existing parsers and the builder freeze/build/install flags were inspected. No product source defect or source edit was required during installed execution.

| Identity | SHA-256 |
|---|---|
| Frozen manifest bytes | `ca90e48380625a9db0132794b3fdc8794e447c977413882d9abc391cfdb6aa3d` |
| Manifest selected-content identity | `db2da4b05367baf2a9eb27a05ce724a4b4d24270055a982dba8dc5435dbc1ccc` |
| Source archive | `20bf57b166b78b631862b163654ff43c3922c4b11e734eff21c54d4819f703e5` |
| Product wheel | `04650f6afa9117febf841f604bb251600d4bd3aa3ab8d1dd014fa89f4a3f1545` |
| Standalone acceptance source | `846ebe94e0ea3015fbf4bbcd2a6723aedb3dcfb78c1c08a245ad50657719f6a0` |
| Installed acceptance summary | `c4364fd5ed56fa2c0a037644973a98ab6bfb7e17c6a8f883c76402c1fd036e97` |

The shipped standalone script passed under fresh installed Python `-I` from an external directory, with checkout, stage and historical exports forbidden. **38 parent product modules** and **22 modules in each of two actual instrumented worker processes** had installed origins and bytes matching the manifest. Builder installation separately checked every shipped product source and asset. Final source checks confirmed all161 frozen entries unchanged; the entire October10 candidate retained its299 regular-file identities.

Observed acceptance:

- Existing repair/context/Unknown gates passed: native mocked repair five requests, separate pause2/resume3 processes and epochs1→2, exact native checkpoint history, independent patch application, immutable report replay, retained Unknown liability and no resend.
- Skills made three native mocked requests with accepted loaded counts `[0,1,1]`, three typed post-turn checkpoints, two store/artifact-reader reopens and epochs1→2→3. The denied same-response resource read remained `not_disclosed`; origin mutation did not change captured resource bytes. Canonical captured request identities, original primary provenance, fresh checkpoint chains and restore-without-authority invariants passed.
- Configured serving reached review_eligible/pending through actual child PIDs77937 and78090, with credential-gated catalog, duplicate task identity and unchanged completed execution across duplicate submissions and clean restart. The declared observation wrapper surrounds the installed original entrypoint with unchanged worker args/env/fds/cwd. This ASGI-plus-child result does not claim unmodified loopback HTTP evidence.
- GPU planning remained `not_run`, imported no Torch, made no child launch or hardware sample, and matched all seven source hashes to the manifest. Installed `uv.lock` was absent and the plan's lock identity was correctly null.
- The real supported Docker verifier rejected the authored wrong candidate through assertion mismatch, journaled **two distinct immutable container instances**, recorded matching bound/absence evidence on the original daemon, and independently confirmed both IDs absent. Known cleanup retry was read-only, all instances/slot were retired, and no verification receipt or charge was manufactured. Process-loss recovery strength remains in separate source-level evidence.

Raw driver/runtime/install logs, requests, checkpoints, database/artifact bytes, daemon/image observations and hash inventory are retained in [release test evidence — local-only](../docs/github-snapshot.md#omitted-local-evidence). The installed run passed on its first attempt; its dependency deprecation diagnostic is preserved in raw stderr. Pre-freeze acceptance weaknesses and their original script remain preserved separately.

This proves a local installed reference on the measured Mac with mocked inference and the existing local Docker profile. It establishes no live-model score, GPU measurement, public access, hosted production, fresh-machine portability, byte-rebuild study or human mastery. Paid execution remains disabled.

**VI:** Probe ở process khác chỉ chứng minh interpreter có thể import, chưa chứng minh worker thật đã dùng code đó. Bản test đo chính child đã chạy và ghi rõ wrapper quan sát. Tương tự, `not_run` và `failed` phải đi cùng nguyên nhân và identity cụ thể; không lấy lỗi hạ tầng thay cho bằng chứng candidate sai.
