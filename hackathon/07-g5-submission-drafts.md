# G5 submission drafts

Drafted **2026-10-15** by AI at Huy's request ("ok G5, license Apache-2.0"). **Status: draft, unpublished.** Every `[G1]`/`[G2]` slot waits for measured live evidence; every `[Huy]` slot is Huy's own text. Nothing here is a measured claim, and no publish, push or post happens without Huy's yes at that moment. The requirement IDs (HR…) refer to the [requirements ledger](02-delivery-and-submission.md#mandatory-requirements-ledger).

**VI:** File này là bản nháp G5 viết sớm, vì giám khảo có thể chấm chỉ từ mô tả và video (HR14). Các ô `[G1]`/`[G2]` chỉ được điền bằng số đo thật sau khi chạy live. Các ô `[Huy]` là phần em tự viết, AI không viết thay. Mục giải thích cơ chế bên trong (implementation detail) được cố ý giữ ở mức đã có trong [thiết kế sản phẩm](01-product-and-system-design.md), cho đến khi em xong S0, để không lộ đáp án.

Decisions already made: license **Apache-2.0** (Huy, 2026-10-15), matching the existing [LICENSE](../release/LICENSE) and [NOTICE](../release/NOTICE) templates. Track: **Coding and Agentic Engineering**.

## 1. Devpost fields (HR11, HR16)

**Project name** `[Huy]` (working title: *Verified Repair*).

**Tagline** (≤200 characters): An NVIDIA `[G1: model name]` agent on Nebius Token Factory that repairs a Python bug and hands back a diff checked by an independent verifier, with every token of cost accounted for.

### What it does (purpose)

A maintainer of a small Python service has a reproducible behavior bug. A coding agent can propose a fix, but the maintainer still has to answer one question: *should I accept this patch?* An agent's own "tests pass" message does not answer it.

Verified Repair takes a frozen repository snapshot, an issue, the files the agent may edit and a spending ceiling. An NVIDIA open model (`[G1: model ID]`) served by Nebius Token Factory reads the code, edits it and runs the developer tests in a loop. When it proposes completion, a separate verifier runs private checks against the exact candidate tree in a fresh container. The maintainer receives:

- a unified diff;
- before/after test evidence;
- a final verdict bound to the exact candidate bytes;
- a cost ledger that separates settled, reserved and unknown cost;
- a pending human-review decision. The tool never merges anything itself.

Measured result: `[G2: task, outcome, cost per verified fix with all attempts in the denominator]`.

### How we built it (implementation)

- **Model path:** native Nebius Token Factory chat-completions requests to `[G1: exact NVIDIA model ID]`, with the API key held only in the server environment.
- **Durable runtime:** one worker harness over a transactional store. Each model turn, tool effect and verification is recorded with its own identity, so the report can be reconstructed from stored evidence rather than from the agent's narrative.
- **Spending ceiling:** a frozen ceiling and deadlines are required inputs. Cost is admitted before each call and reconciled from provider usage afterward.
- **Independent verifier:** private expected outputs never enter the worker's workspace. Each check runs in a fresh Docker container against the exact candidate tree. A candidate printing "PASS" cannot create a verifier receipt.
- **Report:** offline HTML/JSON with the exact stored diff, identity-matched verdict and escaped untrusted text.

`[Hold until S0 is done: one paragraph on how a single live turn is admitted, charged and recorded.]`

### How it behaves

`[G2: one end-to-end trace in plain words: issue → failing test → edit → test → completion proposal → verifier verdict → cost]`

Supported scope, stated plainly: single-module, standard-library Python functions with JSON-serializable inputs. No dependency installation, no arbitrary repository shell commands, no hostile-code isolation claim.

### Challenges

`[G1/G2: the first live failure, written as an incident record: symptom; the observation that separated host, provider, library and our own code; fix or open gate; author]`

### Accomplishments

`[G2: only measured items]`

### What we learned

`[Huy]`

### What's next

The product direction is chosen after G2 by one preregistered discovery experiment with kill criteria ([D043](../context/decision-log.md#d043-production-evidence-is-the-primary-track)). Do not promise features here that are not built.

### Built with

Nebius Token Factory; NVIDIA `[G1: model ID]`; Python 3.12; SQLite; Docker; FastAPI `[confirm the product path uses it before listing]`.

## 2. Technology feedback (HR12)

Fill this only from actual G1/G2 use. Use one record per observation:

| Field | Entry |
|---|---|
| Tool/model and task | `[G1]` |
| Onboarding steps and time observed | `[Huy]` |
| What worked | `[G1/G2]` |
| Reproducible problem, request ID, date, sanitized snippet | `[G1/G2]` |
| Workaround | `[G1/G2]` |
| Impact on the product | `[G1/G2]` |
| Would we reuse it, and why | `[Huy]` |

Documentation conflicts already found in the [provider audit](../research/hackathon-2026-10-10/provider-and-research.md) are research observations. Report them as experienced problems only after reproducing them.

## 3. In-period development statement (HR13)

**Records show:** the earliest dated project decision is D001 on 2026-10-08, and the [archive — local-only](../docs/github-snapshot.md#omitted-local-evidence) inputs are dated 2026-10-08, both inside the submission window that opened on August 26. Third-party reference source (the pinned Codex snapshot) and NVIDIA model weights are not redistributed.

**Huy confirms:** `[Huy: whether any product code or design predates August 26, and if so, what changed during the window]`.

Do not assert that nothing predates August 26 until Huy confirms it.

## 4. Video script (HR10)

The shot plan is the [2:40 demonstration storyboard](02-delivery-and-submission.md#demonstration-storyboard); this section adds only the spoken lines. Record a genuine live run. Label any replayed or accelerated footage on screen.

| Time | Spoken line (draft) |
|---|---|
| 0:00–0:20 | "This function returns the wrong result for `[G2: case]`. A coding agent can propose a fix, but as the maintainer I still have to decide whether to trust it." |
| 0:20–0:35 | "I give Verified Repair the issue, the files it may edit, and a hard spending ceiling of `[G2]`. The agent runs on NVIDIA `[G1: model name]`, served by **Nebius Token Factory**." |
| 0:35–1:15 | "The model reads the code, runs the failing test, edits the function and runs the test again." (Show one failure and the diff, not a scrolling terminal.) |
| 1:15–1:45 | **Conditional on a live restart being exercised.** Otherwise cut this segment and say once: "Restart is supported locally; we did not show it live." |
| 1:45–2:15 | "The agent's own test run is not the verdict. An independent verifier checks the exact candidate in a fresh container. Here is the diff, the verdict and the cost: `[G2: settled / unknown]`." |
| 2:15–2:40 | "Scope today: small standard-library Python functions. The source is open under Apache-2.0; links are below." |

Decision for Huy: whether the restart segment stays (it depends on G3, which comes only after G5).

## 5. Public README draft (HR09, HR08)

This becomes `release/README.md` only when the next release candidate (rc5) is built, because rc4's frozen manifest binds the current bytes. Draft text:

> # Verified Repair
>
> An NVIDIA `[G1: model name]` coding agent, served by Nebius Token Factory, repairs a bug in a small Python function. An independent verifier then checks the exact candidate in a fresh container. You get a diff, the evidence and an itemized cost, and the merge decision stays with you.
>
> ## Quick start
> `[rc5: exact install command, supported Python version, required local Docker image, judge-access instructions]`
>
> ## How Nebius and NVIDIA are used
> Every model turn is a Nebius Token Factory request to `[G1: model ID]`. The key is read from the server environment variable `NEBIUS_API_KEY` and is never written to approvals, payloads or reports.
>
> ## Supported scope and limits
> Single-module, standard-library Python functions; one worker; a fresh container per verification case. Not supported: arbitrary repositories, dependency installation, hostile-code isolation, GPU workloads.
>
> ## What the verifier caught and missed — Huy
> `[Huy: written after the G2 verifier receipt card (verdicts on the three controls, forgery attempts, false-accept and false-reject counts)]`
>
> ## Cost per verified fix
> `[G2: all attempts, including failures, in the denominator]`
>
> ## First live incident
> `[G1/G2 incident record]`
>
> ## License
> Apache-2.0 (see LICENSE and NOTICE). Third-party dependencies keep their own licenses. No model weights are redistributed.

## 6. Public snapshot plan (HR07, HR05)

Do not hand-write a path list. The release builder's `freeze` phase already selects the product: the `PRODUCTS` roots `service`, `evals`, `compute` and `workloads` ([build_offline_release.py:34](../scripts/build_offline_release.py#L34)), plus the release templates, `pyproject.toml` and `uv.lock`, excluding dot-directories and forbidden parts. `runs/`, `control-inputs`, `study/`, `context/`, `research/`, `archive/`, `references/`, `docs/` and `capstone/` are not product roots.

Order, each step after G2 has frozen product behavior:

1. `freeze` a new manifest and diff it against the [rc4 manifest — local-only](../docs/github-snapshot.md#omitted-local-evidence).
2. Secret scan of the staged archive: `NEBIUS`, `Bearer`, key-shaped strings, absolute home paths, any client material (D045).
3. Confirm the oracle and private control inputs stay outside worker intake.
4. Build and install offline, then run the shipped acceptance.
5. Check that GitHub detects the Apache-2.0 license, then do a logged-out read of the public page.
6. Huy's explicit yes before creating the public repository and before each push.

## 7. Decisions Huy owns before Oct 17

**(a) Judge access (HR06, HR14).** The rules need a functioning demo or test-build URL, free to judges through Dec 16 03:00 Vietnam. Hosted public deployment is currently off. A build that requires judges to bring their own paid key does not count.

| Option | What it needs | Cost and reversibility |
|---|---|---|
| A. Funded hosted gateway | Server-held key, per-judge task quota, uptime through Dec 16; lifts the hosted-deployment hold | Ongoing hosting plus inference inside the D042 ceiling; turning it off ends access, so it is hard to reverse during judging |
| B. Downloadable test build with a restricted credential path supplied privately | Restricted funded gateway or credential that is not our server key (whether Nebius can scope a key this way is **unverified**); judges also need local Docker | Inference only, inside the ceiling; install burden on judges; credential can be revoked |

Either option is weaker than the video for judges who do not test, so HR10/HR11 quality matters regardless.

**(b) Restart segment in the video:** keep only if a live restart is exercised.

**(c) Project name and tagline.**
