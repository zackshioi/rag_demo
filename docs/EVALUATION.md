# Policy Copilot — Evaluation-Driven Development (EDD)

**Status:** Draft v1.0 · **Date:** 2026-06-29 · Companion to `PRD.md` §11, `GOVERNANCE.md`, `DEVELOPMENT_RULES.md`

This is how we keep Policy Copilot trustworthy *over time*: a closed loop where real usage produces traces, traces are evaluated and diagnosed, fixes are gated by automated evals in CI, and only passing changes ship. This pattern is **Evaluation-Driven Development (EDD)** — an industry best practice for LLM products (see Sources).

> The loop: **trace → eval & observe → diagnose → gate (if pass) → release → (back to trace)**.

```
   ┌──────────────────────────────────────────────────────────────────────┐
   │                            continuous loop                             │
   ▼                                                                        │
1 Trace ──▶ 2 Eval & observe ──▶ 3 Diagnose ──▶ 4 Gate ──▶ 5 Release ───────┘
 (record)    (RAGAS / Bedrock)   (error analysis  (GitHub   (alias canary
                                  → new golden)    Actions)   + rollback)
```

The **diagnose** stage is the engine: real failures become new golden cases, which strengthen the gate. We follow **error-analysis-first** — write evals for errors we actually observe in traces, not metrics we imagine.

---

## 1. Trace

Capture one structured record per answer: question, retrieved chunks + scores, answer, citations, refused flag, model + prompt version, latency, (later) tokens + cost.

| | Local (Phase 1–2) | Production (Phase 3+) |
|---|---|---|
| Store | `src/policy_copilot/tracing.py` → `data/traces/traces.jsonl` (git-ignored) | Bedrock model-invocation logging → CloudWatch / S3 |
| Trigger | every `agent.answer()` call (best-effort, never blocks the answer) | every `InvokeAgent` (+ `enableTrace`) |

Same record shape across both, so the diagnose/eval code is reused when we move to Bedrock.

## 2. Eval & observe

**Offline (the gate's exam):** run the golden set, compute metrics.
- **RAGAS** (Phase 1–2, local): faithfulness, response_relevancy, context_precision, context_recall.
- **Bedrock RAG Evaluation** (Phase 4+, LLM-as-judge): faithfulness, citation precision/coverage, correctness, refusal.
- **Governance tests** (ours): refusal precision (out-of-corpus), numeric correctness (verbatim), citation resolves to a real chunk.

**Online (observe):** sample ~5% of production traces → LLM-as-judge scores faithfulness + refusal correctness → written back as custom CloudWatch metrics; drift monitoring on score/embedding distributions.

## 3. Diagnose (error analysis) — the engine

The step that makes the loop improve rather than just measure:
1. Pull failing / low-score traces (`tracing.load_traces()` + `notebooks/error_analysis.ipynb`).
2. Read each, write a one-line "what went wrong".
3. **Categorise** failure modes, e.g.: `retrieval-missed-table` · `number-paraphrased` · `should-have-refused` · `wrong-citation`.
4. **Count** them — fix the most frequent first.
5. Turn each recurring failure into **new golden case(s)** (`evals/golden.jsonl`) + a targeted check; fix the cause (prompt / chunking / threshold).

This is where a self-hosted trace UI (Tier 2 below) pays off — annotating traces by hand is far faster with one.

## 4. Gate (CI/CD — GitHub Actions)

- **`ci.yml`** (built): ruff + black + mypy + pytest on every PR.
- **`eval.yml`** (Phase 6): on PR **and** nightly — run the golden set, publish a score report as a PR comment, and **block merge if any threshold regresses**:

| Metric | Threshold |
|---|---|
| faithfulness | ≥ 0.75 |
| refusal precision (out-of-corpus) | ≥ 0.95 |
| numeric correctness | ≥ 0.90 |
| context recall / precision | ≥ 0.70 / ≥ 0.70 |

- Eval is only meaningful against **pinned versions** (model, prompt, retrieval config) — keep them locked so a score is attributable to a change.
- Nightly run catches drift even when no PR is open.

## 5. Release

Passes the gate **and** is not worse than the current version on the golden set → ship via shadow → canary → full (multi-alias + app-layer split), version pinned, one-step rollback by re-pointing the alias.

---

## Tool stack (recommended)

> Principle: **core self-owned, data local, auditable** (fits the governance story); add a UI tool only when trace volume needs it, and self-host it.

| Tier | Scope | Tools |
|---|---|---|
| **1 — required** (in-repo, in CI) | trace + eval + gate + diagnose | `tracing.py` (JSONL) · `evals/` (RAGAS + golden set) · `eval.yml` · `error_analysis.ipynb`. Offline, reproducible, zero external service. |
| **2 — recommended** (self-hosted OSS) | richer diagnose UI + prompt versioning | **Langfuse** (Apache-2.0, OTEL-native, datasets/scores/prompt management) — primary; **Arize Phoenix** (ELv2, strong RAG eval, one-line local) — lighter alternative. Ingest the same traces; keep self-hosted so data stays local. |
| **3 — production** (Phase 3+) | managed eval + observability | Bedrock RAG Evaluation · model-invocation logging · CloudWatch. Langfuse can also ingest Bedrock OTEL. |

## Sending traces to Langfuse (Tier-2 — how it works)

When `LANGFUSE_*` keys are set, each answer is mirrored to a self-hosted Langfuse
(start it with `infra/langfuse/README.md`) as **one clean nested trace**:

1. **`@observe`** decorates `answer()` / `answer_agentic()` → a root business span
   (`answer` / `answer_agentic`) that stays *active for the whole call*
   (`capture_input=False` so the FAISS index isn't serialised).
2. **Auto-instrumentation** (`setup_auto_instrumentation`, OpenTelemetry +
   `opentelemetry-instrumentation-anthropic`) turns every Claude call into a
   `generation` with model + token usage. Because the `@observe` span is active,
   each generation **nests under it** → Langfuse computes **native cost**, and the
   tree reads `answer_agentic → generation (round 1) → generation (round 2)`.
3. **`finalize_langfuse()`** (called inside the decorated fn, so it targets the
   current span) attaches business semantics: `set_current_trace_io`
   (question/answer), `update_current_span` (model, refused, tokens, cost, error,
   latency) and `score_current_trace` (refused, plus top_score /
   citations_resolve / numbers_verbatim when present).

This is the recommended combo — **auto-instrument for the LLM call's token/cost +
a manual span for business semantics** — unified into a *single* trace instead of
two separate ones. The SDK batches and flushes asynchronously (background interval
`LANGFUSE_FLUSH_INTERVAL=1s` / `LANGFUSE_FLUSH_AT=15`, plus an `atexit` shutdown),
so no per-call flush is needed.

The whole sink is **best-effort** (`try/except`, no-op without keys): observability
must never break an answer.

## Phasing (build evals as real traces accumulate — the EDD way)

- **Now (Tier-1 skeleton):** `tracing.py` (answer() writes traces) · `evals/golden.jsonl` seed · `error_analysis.ipynb`. So we collect real data from Phase 1.
- **Phase 6:** full RAGAS / Bedrock Eval · `eval.yml` gate · online sampling + drift · (optional) Langfuse.

Golden set note: it starts as a hand-picked seed and grows two ways — (a) **auto-built from FinanceBench** gold answers + evidence, and (b) **from diagnose** (real failures become cases).

---

## Sources
- [Hamel Husain & Shreya Shankar — LLM Evals FAQ (error-analysis-first)](https://hamel.dev/blog/posts/evals-faq/) · [Why AI evals are the hottest skill](https://www.lennysnewsletter.com/p/why-ai-evals-are-the-hottest-new-skill)
- [arXiv: Evaluation-Driven Development & Operations of LLM Agents — process model & reference architecture](https://arxiv.org/pdf/2411.13768)
- [AWS Well-Architected GenAI Lens — integrate evaluation into CI/CD](https://docs.aws.amazon.com/wellarchitected/latest/generative-ai-lens/genops01-bp01.html)
- [Langfuse vs Phoenix (ZenML)](https://www.zenml.io/blog/langfuse-vs-phoenix) · [Arize Phoenix (GitHub)](https://github.com/arize-ai/phoenix)
