# Production trace log

Since [D046](../context/decision-log.md#d046-production-backward-learning-replaces-mastery-gates) (2026-10-16), learning is recorded as **production traces**, not module grades. A trace starts from something real, follows it down until Huy can predict and change it, and ends in something useful. There are no statuses, gates or quotas. The file name is kept so existing links still resolve.

**VI:** Không còn bảng "đã đạt / chưa đạt". Mỗi dòng là một lần em lần theo một thứ đang chạy thật, đào xuống đến tầng mà em tự đoán trước được và tự sửa được, rồi tạo ra một thứ có ích. Số dòng có bằng chứng thật mới là tiến độ.

## The loop

1. **Start from a real artifact.** A live run, an incident, a measured cost, a verifier verdict, or a production codebase read as the source of truth.
2. **Name the surprise.** What did not match what you expected? If you wrote an expectation before observing, compare against it.
3. **Trace down** the layers below, one at a time, with source links and concrete values.
4. **Stop** at the layer where you can predict the behavior and change it on purpose. Not every trace needs to reach hardware.
5. **Prove it.** A later run, test or fix where your prediction came true.
6. **Ship an output.** A fix with a regression test, a write-up, an upstream issue or pull request, or a new experiment. If the bottom of the trace shows something nobody has solved, record it as an experiment idea.

**Layers, from the user down:**

| # | Layer | In this project |
|---|---|---|
| 1 | User outcome | Verified fix, cost per verified fix, what the maintainer sees |
| 2 | Our harness | `service/`: harness, store, billing, verifier, report |
| 3 | Libraries and runtime | Python, SQLite/SQLAlchemy, HTTP client, Docker, processes |
| 4 | Protocol and provider | Nebius chat completions, HTTP, JSON, response fields |
| 5 | Serving | Batching, KV cache, scheduling, speculative decoding (vLLM, SGLang, TensorRT-LLM) |
| 6 | Model | Tokenization, attention, mixture-of-experts and hybrid layers, sampling |
| 7 | Kernels and numerics | Triton/CUDA, fused attention, precision |
| 8 | Hardware | Memory bandwidth, tensor cores, interconnect, roofline |
| 9 | Math and physics | Probability, queueing, information, conservation of money and tokens |

Through an API provider, layers 5–8 are **inferred, not observed**: we see only latency, usage and outputs. Observing them needs open serving source (read) or a self-hosted run, and GPU rental remains off until it is separately decided. Mark which layers a trace observed and which it inferred.

**VI:** Khi gọi model qua API, mình không nhìn thấy tầng serving, kernel hay phần cứng của Nebius. Mình chỉ suy ra từ độ trễ, số token và output. Muốn thấy thật thì phải đọc code serving mã nguồn mở hoặc tự chạy trên GPU (việc này chưa được duyệt). Ghi rõ tầng nào quan sát được, tầng nào chỉ suy luận.

## Where traces come from

A repository is worth tracing when it is on our real path (its code runs when our system runs, or it is a production system solving the same problem) and it is pinned to the exact version or commit we run. Reading any of them is fine; check its LICENSE file before copying code. Existence, license, archive state and recent activity were checked through the GitHub API on 2026-10-16.

**Ring 1: code that runs inside our process (observed).** The exact source is already installed in `.venv/lib/python3.12/site-packages/`, so these traces need no download. Runtime: Python 3.12.11, SQLite 3.47.1, Docker Engine 28.4.0.

| Our component | Production repository at our version |
|---|---|
| Model call over HTTP | `encode/httpx` 0.28.1 → `encode/httpcore` 1.0.9 → `python-hyper/h11` 0.16.0 → `python/cpython` 3.12 (`ssl`, `socket`) |
| Durable store | `sqlalchemy/sqlalchemy` 2.1.4 → `sqlite/sqlite` 3.47.1; `postgres/postgres` on the PostgreSQL path |
| Verifier containers | `docker/cli` and `moby/moby` 28.4 → `opencontainers/runc` → Linux namespaces and cgroups |
| Service API | `fastapi/fastapi` 0.142.4 → `Kludex/starlette` 1.7.0 → `Kludex/uvicorn` 0.54.0 → asyncio |
| Durable workflows (production extra) | `temporalio/sdk-python` 1.34.0 |
| CPU numerical reference | `pytorch/pytorch` 2.14.1 |

**Ring 2: production systems solving the same problem (comparators).** `openai/codex` (pinned at [9dd7988 — local-only](github-snapshot.md#omitted-local-evidence)), `SWE-agent/mini-swe-agent` (pinned at [04d809c — local-only](github-snapshot.md#omitted-local-evidence)), `SWE-agent/SWE-agent`, `SWE-bench/SWE-bench` (the closest public relative of our verifier), `OpenHands/OpenHands`, `harbor-framework/terminal-bench-1`, `google/gvisor` (stronger containment than runc), and `anthropics/claude-agent-sdk-python`.

**Ring 3: verifiers inside RL training.** `bytedance/SandboxFusion`, `verl-project/verl`, `huggingface/trl`, `NVIDIA-NeMo/RL`, `NVIDIA-NeMo/Gym` and `NVIDIA-NeMo/Skills`. Question for this ring: how a reward for code is computed, how a model can game it, and whether an exact-byte, receipt-bound verifier closes a gap. This is a hypothesis, not a result.

**Ring 4: the provider side (inferred only).** Serving: `vllm-project/vllm`, `sgl-project/sglang`, `NVIDIA/TensorRT-LLM`, `ai-dynamo/dynamo`. Kernels: `triton-lang/triton`, `Dao-AILab/flash-attention`, `NVIDIA/cutlass`. Training: `NVIDIA/Megatron-LM`, and `karpathy/nanochat`, whose `d2` run is in `~/.cache/nanochat`. Which engine Nebius Token Factory runs is not verified, so this code supplies hypotheses; our measured latency and usage are the evidence.

**Order, following the critical path:** G1 traces Ring 1 transport; G2 traces Docker and runc, with SWE-bench as the comparator; G5 judge access traces gVisor; after submission come Ring 3, then nanochat. Cloning a repository for its history and tests is a download and needs Huy's yes, with its size stated.

**VI:** Vòng 1 là code thật đang chạy trong tiến trình của mình, đã có sẵn trong `.venv`, nên trace không cần tải gì. Vòng 4 chỉ để đặt giả thuyết, vì mình không biết Nebius dùng engine nào. Bằng chứng là số đo từ chính các lần chạy của mình.

## Log

| Date | Starting artifact | Surprise or question | Deepest layer (observed / inferred) | What Huy can now predict or change (Huy's words) | Proof | Output | Concepts |
|---|---|---|---|---|---|---|---|

No traces recorded yet. The first is expected from the G1 live call. Use one [trace note](../study/templates/session-note.md) per row for the detail.

Only Huy writes the "What Huy can now predict or change" column. AI help is labeled in the trace note. A passing test or AI-written code never fills that column.

## Self-check menu (optional)

<a id="gate-rubric"></a>

Use any of these when you want to know whether you really understand something. None is required and none produces a status.

| Check | Question |
|---|---|
| Derive | Can I state the purpose, the core constraint and a counterexample from scratch? |
| Predict | Can I say what changes under a new input, ordering or failure, before seeing it, and what would prove me wrong? |
| Trace | Can I follow the decisive state or data with concrete values and owners? |
| Debug | Can I find and fix a fresh defect without weakening the check that caught it? |
| Transfer | Does the same principle explain an unfamiliar system, and which assumptions break there? |
| Retrieve | Days later, with my notes hidden, can I still explain it and handle a changed case? |

**VI:** Đây là công cụ tự kiểm tra, không phải bài thi. Dùng khi em muốn biết mình hiểu thật hay chỉ thấy quen.

## Concept index

H0–H15 remain the concept reference in the [learning plan](02-mastery-learning-plan.md). A trace lists the concepts it touched; nothing here needs to be completed in order.

| Module | Focus | Traces |
|---|---|---|
| H0 | Whole-system trace | — |
| H1 | State and minimal loop | — |
| H2 | Network wire and adapter | — |
| H3 | Tools, files and processes | — |
| H4 | Budgets and crash recovery | — |
| H5 | Context and cache | — |
| H6 | Repository retrieval | — |
| H7 | Authorization and isolation | — |
| H8 | Task evaluation | — |
| H9 | Extensions and integrations | — |
| H10 | Multiple agents | — |
| H11 | Durable service | — |
| H12 | Inference internals | — |
| H13 | Serving performance | — |
| H14 | Training trajectories | — |
| H15 | Capstone and research | — |

Engineering status lives in [coverage](../capstone/08-implementation-coverage.md) and the [release index](../releases/README.md), not here. The capstone milestones M0–M7 keep their own implementation gates.
