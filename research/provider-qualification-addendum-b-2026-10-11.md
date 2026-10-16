# Qualification addendum B: preserve sanitized HTTP diagnostics

Date: **2026-10-11**, frozen during independent review. The [original spec](provider-qualification-spec-2026-10-11.md) remains unchanged. Its phrase “No provider header or key persistence” means no credentials, authorization headers or request headers in qualification evidence. The fixed successful probe emits no provider headers.

For injected HTTP-error controls, retain the existing adapter/harness contract: bounded, allowlisted nonsecret **response** diagnostics may be preserved as evidence, without tool authority, inferred zero billing or resend permission. Do not strip these existing diagnostics or alter the approved error-envelope protocol merely to satisfy broader wording in a new wrapper spec. [The original HTTP evidence contract](../hackathon/06-http-error-evidence-contract.md) remains authoritative for that path. Paid/live execution stays disabled.

**VI:** Request header có thể chứa credential nên không được lưu. Response diagnostic đã được allowlist là evidence khác; giữ nó không có nghĩa error được cấp quyền chạy tool hay bill được coi là0.
