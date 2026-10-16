# Environment recovery addendum A: fixture verifier source identity

**2026-10-11 — frozen before the identity change.** Implementation inspection corrects one assumption in the [parent specification](environment-recovery-spec-2026-10-11.md): `PythonFunctionVerifier.environment_for` already binds controller/execution source, whereas `LinuxVerifier.environment_digest` previously bound the image, architecture, RPC source and limits only.

Add the current verifier-controller and execution-module SHA256 identities to newly calculated Linux verifier environment digests. This makes the measured implementation explicit for the actual consumer. New tasks use this new identity; old task contracts, saved approvals, results and release artifacts remain byte-preserved. Reopening an old contract with a changed verifier must reject environment drift, never silently reinterpret it. This is source identity, not binary/daemon attestation or proof of hostile containment. Keep the default non-journaled execution behavior unchanged apart from this deliberate environment version difference. Extend appropriate source-drift tests and installed checks; no schema/lock/provider permission changes.

**VI:** Source verifier thay đổi thì môi trường đo đã khác dù Docker image giống nhau. Digest mới phải phản ánh code mới; kết quả lịch sử vẫn giữ digest cũ, không sửa evidence cho khớp.
