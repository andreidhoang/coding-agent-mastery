# Independent offline qualification review

Date: **2026-10-11**. Outcome: **accepted for the frozen offline source slice after one repaired evidence-binding finding**. Installed acceptance and broader regression delivery belong to the integration owner's separate record. Paid/live inference, GPU use and public execution remain disabled. This review does not establish G1, live G2, production readiness or human mastery.

The reviewer read the frozen specification and existing runtime before candidate implementation, recorded [ten independent failure oracles — local-only](../docs/github-snapshot.md#omitted-local-evidence), and reviewed `service/qualification.py`, `service/qualification_cli.py` and CLI integration after the candidate stabilized. The [original specification](provider-qualification-spec-2026-10-11.md) remains unchanged. [Addendum A](provider-qualification-addendum-a-2026-10-11.md) maps “unstarted” to the existing running-task/pending-node representation; [addendum B](provider-qualification-addendum-b-2026-10-11.md) preserves existing sanitized response diagnostics while forbidding credential/request-header persistence.

**VI:** Gate review này kiểm tra cơ chế offline có đúng contract không. `operator-verified` vẫn chỉ là input được người vận hành khai báo; transcript mock không biến nó thành live observation hay quyền trả tiền.

## Repaired finding: a report could be attached to a different manifest

The original probe contract did not bind the qualification manifest digest. On the preserved initial candidate, the reviewer copied a genuine successful run, changed its execution/review deadlines by 500 seconds, and republished the manifest/start/report indexes with consistent new content hashes. The authority database, requests, responses and accounting were untouched. Both report validation and advisory handoff accepted the changed manifest. The [original reproduction — local-only](../docs/github-snapshot.md#omitted-local-evidence), [reproduction script — local-only](../docs/github-snapshot.md#omitted-local-evidence) and initial source copy remain preserved. The independent test author separately reproduced deadline and prepared-task transplantation failures.

The repair binds the manifest digest inside the [durable probe contract](../service/qualification.py#L348). The [report derivation](../service/qualification.py#L377) requires the exact normalized contract, digest and budget limit, verifies node/owner/dispatch/checkpoint/retirement relationships, and reconstructs both complete native requests through the disabled approved adapter. The same deadline attack now rejects at the durable contract comparison. Rewriting an index can no longer change which frozen plan the existing authority record actually executed.

**VI:** Hash của một file chỉ chứng minh nội dung của file đó. Nếu ledger chưa giữ identity của manifest, attacker có thể tạo một manifest mới rồi cập nhật các index bên ngoài. Khi manifest digest nằm trong contract đã được dispatch, thay deadline/task sẽ không còn khớp với chính ledger và transcript.

## Independent measurements

The reviewer authored and ran [six additional controls — local-only](../docs/github-snapshot.md#omitted-local-evidence); [all six passed — local-only](../docs/github-snapshot.md#omitted-local-evidence) on the fixed source:

- A real SQLite WAL contained committed data absent from the main database. The read-only backup included it. Original main-database and WAL bytes remained identical through prepare, run and handoff; shared-memory reader coordination is not asserted byte-stable.
- An operator-verified input with an ambient synthetic API key/proxy and denied Python socket connections completed only the internal mock. Public qualification files contained neither the private issue canary nor the ambient key; original claims remained distinct from offline observation. The synthetic ledger charged four units and retained no settled-run reservation.
- Starting an attempt on the prepared repair after qualification caused handoff rejection without a handoff file.
- Real nested `.py` addition, deletion and byte modification in a disposable service source tree each caused rejection before the started marker. This tests enumeration/checking against actual files; it is not an additional installed-package acceptance claim.
- A missing repair root was rejected without creating that root or an output preparation.
- The canonical deadline reindex attack was rejected by report and handoff after the fix.

The independent test lane separately recorded **43 passing tests** and three deliberate mutation failures. The reviewer inspected its mutation plugin, failing assertions and logs: dropping native opaque history prevented qualification; bypassing evidence validation made the missing-receipt test fail; deleting failed-run state to retry Unknown changed task/report identity and failed the no-retry oracle. These were disposable per-process mutations with preserved logs, not product source edits. See the [test-lane record — local-only](../docs/github-snapshot.md#omitted-local-evidence). The reviewer did not rerun those unchanged checks merely to duplicate their counts.

**VI:** Negative controls cho thấy test phân biệt được cơ chế sai: mất native history, bỏ kiểm tra receipt, hoặc tạo task mới để né Unknown đều bị bắt. Test pass chỉ áp dụng cho phạm vi đã chạy; không được suy ra model thật sửa code tốt hoặc provider thật hỗ trợ account/model này.

## Boundaries and source identity

No unresolved blocking finding remains in this bounded source review. The upstream task remains a point-in-time binding, not a lock against later repair start. The local control-plane filesystem and authority database are trusted; this is not hostile-user tamper resistance. Actual provider/model/catalog/rates, useful live repair, paid execution, fresh-machine reproduction and public judge access remain unmeasured. Docker was used only for existing immutable image inspection in these reviewer controls; no candidate function or container workload ran.

The exact reviewed package and supporting evidence identities are in [review verification — local-only](../docs/github-snapshot.md#omitted-local-evidence). Core reviewed module SHA-256: `6222e11f4f89cc65d2c9f3479f14b5c6873c242b94333c21a6e577c114a45cee`. The verification file also binds all service `.py` paths/bytes, the frozen contracts, reviewer controls, negative reproduction, and inspected mutation logs.
