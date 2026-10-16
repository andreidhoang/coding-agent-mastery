# Qualification addendum A: existing prepared-state vocabulary

Date: **2026-10-11**, frozen during implementation inspection and before prepared-state integration. The [original frozen specification](provider-qualification-spec-2026-10-11.md) remains unchanged.

The original phrase “single queued repair node” describes an unstarted task semantically, not a new persisted status. Existing `RepairEngine.submit` calls `RuntimeStore.set_graph`, whose supported representation is task `execution_state=running`, one node `repair` with `status=pending` and `epoch=0`, generation1, and no attempts, dispatches, sandboxes, candidates, checkpoints, verifications or reviews. Qualification must accept exactly this existing prepared representation and reject any started/canceled/drifted state. Do not add a queue state or alter repair/runtime authority to satisfy prose terminology.

The source-bound handoff remains advisory for that exact unstarted snapshot. It grants no execution authority and does not lock future repair admission. Paid/live execution stays disabled.

**VI:** Tên state có thể dễ gây hiểu nhầm: task đang `running` nghĩa graph đã được nhận; chưa có attempt thì worker chưa chạy. Ta kiểm tra dữ liệu thực tế cùng nhau, không suy rằng chỉ một chữ `running` chứng minh đã gọi model.
