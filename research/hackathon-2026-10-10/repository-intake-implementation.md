# E1 frozen repository intake evidence

AI-authored implementation and local checks, 2026-10-10. Scope: [E1 contract](../../hackathon/04-execution-specification.md). Read project instructions, current state and selected H0 reference-runtime packet before implementing. Human mastery evidence is unchanged.

The intake owner copies only declared UTF-8 text files into an immutable mapping and freezes a writable subset. Tree identity reuses the existing `sha256-text-tree-v1`; manifest identity also binds repository ID, writable paths and optional base Git commit. Neither digest confers execution authority. A tiny trace is `app.py` bytes -> copied string -> immutable mapping -> tree digest -> detached manifest; subsequent source-file or returned-dictionary mutation cannot alter that snapshot.

**VI:** `tree_digest` là identity của bytes đã chọn, không phải identity toàn Git history. `from_files` nhận provenance do trusted caller khai; chỉ `freeze_repository(..., expected_commit=...)` mới tự kiểm tra checkout. Test do AI chạy không được coi là prediction hay teach-back của Huy.

Implemented entry points: [FrozenRepository](../../service/repositories.py#L73), `from_files(repo_id, files, allowed_paths, base_git_commit=None)`, `as_dict()`, `from_dict(manifest)` and [freeze_repository](../../service/repositories.py#L290). Serialization schema 1 has exactly `schema`, `repo_id`, `files`, `allowed_paths`, `base_git_commit`, `tree_digest`, `manifest_digest`; imports perform no candidate execution. Writable paths serialize sorted and may be empty.

Limits are 50 files, 128KiB per file and 256KiB total, counted as UTF-8 bytes. Accepted suffixes are `.py`, `.md`, `.txt`, `.json`, `.toml`; names are canonical bounded ASCII with conservative dot, secret/credential, private/oracle/reference and bridge exclusions. Case aliases and file/directory collisions reject. Source descriptors use `O_NOFOLLOW` for root ancestors, root, directory components and leaf; FIFO/nonregular, invalid UTF-8, binary control content, missing file and oversize reject. This boundary does not detect credentials embedded inside otherwise permitted text.

Optional Git provenance supports ordinary in-root `.git` directories only. Read-only plumbing checks exact HEAD, selected index entries, committed blob sizes/bytes and selected working executable modes, then rechecks source bytes and HEAD. FSMonitor, hooks, global/system configuration and replacement objects are disabled; metadata symlinks, gitfiles/worktrees, alternates and grafts reject. Unselected dirt does not invalidate **selected-file** provenance, and no whole-checkout cleanliness is claimed. Default intake uses no Git. This is trusted control-plane intake, not broad hostile filesystem or process isolation.

**VI:** Nếu file ngoài danh sách thay đổi, snapshot vẫn đúng vì chỉ khai các file đã chọn. Không nói checkout sạch toàn bộ. Đường chạy mặc định không cần Git và luôn để `base_git_commit=None`; model không được tự gán commit từ tree digest.

AI prediction before checks: mutable aliases, symlink traversal, manifest tampering, oversized text and selected Git dirt should reject before candidate code executes. Measured focused checks: **65 passed in 3.88s**, `uv run pytest tests/test_repositories.py -q`; `uv run ruff check service/repositories.py tests/test_repositories.py`: **all checks passed**. Controls include exact CRLF preservation, subsequent file mutation, all four symlink positions, FIFO rejection, exact byte-limit acceptance, UTF-8 byte counting, duplicate/case aliases, writable subset, integrity/schema rejection, nested selected Git files, unrelated dirt, wrong HEAD, untracked/staged/working/mode changes, and a hook/FSMonitor marker that remained absent. No paid calls, deployments or global-suite result are claimed.

Source SHA-256 at this check:

- `service/repositories.py`: `b39676ea101aec719582124a414702a60efb6e125bfdabed4fd571802cb5597b`
- `tests/test_repositories.py`: `e317308db2c054bd5f3a20479087ca5760f876fc1e52c5c58b69ca8a740bd615`

Next owner action: integrate the unchanged public API with the repair runner and recipe, verify its exact reserved bridge filename, and independently review the integrated boundary. Current learning stage remains H0; implementation evidence is separate from human mastery.
