# Policy Copilot — Progress Tracker

**Status:** Active · **Last updated:** 2026-06-26 · Companion to `PRD.md` and `ARCHITECTURE.md`

Single source of truth for delivery status across the six phases (PRD §12). Update the status column and checkboxes as work lands. Keep cost actuals current — Phase 4 standing cost is the one to watch.

---

## Status legend

`⬜ Not started` · `🟡 In progress` · `✅ Done` · `⛔ Blocked`

---

## Milestones

| Milestone | Scope | Status |
|---|---|---|
| **M0** — Repo + CI foundation | Phase 0 | ⬜ Not started |
| **M1** — Local agentic RAG | Phases 1–2 | ⬜ Not started |
| **M2** — AWS-native governed agent | Phases 3–5 | ⬜ Not started |
| **M3** — Demo-ready w/ eval gate | Phase 6 | ⬜ Not started |

---

## Phase 0 — Repo & CI foundation (DevOps) · ⬜

**Goal:** the git + GitHub Actions baseline so every later phase ships through a gate.
**Proves:** change control is real, not aspirational. See `DEVELOPMENT_RULES.md`.

- [x] `git init`; push to GitHub remote (`zackshioi/rag_demo`) — ⬜ still to do: protect `main` (PR required, no direct push) via GitHub Settings
- [x] `.gitignore` (Python, `.env`, AWS creds, data caches)
- [x] Project layout (`src/policy_copilot`, `tests/`, `evals/`, `infra/`, `prompts/`, `.github/workflows/`)
- [x] Python env via **uv** (Python 3.12 pinned, `pyproject.toml` + `uv.lock`); dev tools ruff/black/mypy/pytest — all green
- [x] GitHub Actions: `ci.yml` (ruff + black + mypy + pytest via uv, on every PR) — merged in PR #1
- [ ] GitHub Actions: `eval.yml` (golden-set eval gate — wired in Phase 6)
- [ ] Secrets via GitHub OIDC → AWS role (no long-lived keys)

**Exit criteria:** a PR runs CI automatically; `main` cannot be pushed directly.

---

## Phase 1 — Local RAG (Pillar 1: Anthropic SDK) · ✅

**Goal:** FAISS + Anthropic SDK answer questions over the corpus with citations.
**Proves:** baseline retrieve+answer works end-to-end, locally, near-zero cost.
**Cost:** ~US$1–5 (API only). **Demo:** CLI — question → cited answer.

- [x] **Primary dataset: FinanceBench** (`src/policy_copilot/financebench.py`) — 150 Q&A over real SEC filings
- [x] Lean subset: 8 filings downloaded + parsed with `pymupdf4llm` → Markdown, cached (1,583 pages / 40 questions)
- [x] Refusal test = out-of-corpus FinanceBench questions (source filing not in the subset) — single data source, no llmware
- [x] Exploration notebooks: `explore_financebench.ipynb`, `explore_retrieval.ipynb`, `explore_answer.ipynb`, `error_analysis.ipynb`
- [x] Chunking (structure-aware, ~1600 chars/240 overlap; `chunking.py`) — F1.3 → 8 filings = 3,812 chunks
- [x] Build FAISS index (bge-base embeddings, cosine; `index.py`) — F1.4 → 3,812 vectors, persisted
- [x] Retrieval function `search(query) → ranked chunks + scores` (`index.py`) — F1.5. (Exposing it as a model-callable *tool* is Phase 2 / F2.1.)
- [x] Local secrets scaffold: `.env.example` (committed) + git-ignored `.env` for the Anthropic key — F1.6 prep
- [x] `Anthropic` messages loop: retrieve → ground → answer with citations (`agent.py`, Claude Sonnet 4.6) — F1.6
- [x] Refusal behaviour: low-score pre-check (no API call) + `NOT FOUND` prompt rule + `refusal` stop_reason — F1.7
- [x] CLI demo script (`cli.py`): REPL + one-shot — F1.8
- [x] **EDD Tier-1 skeleton** (early start on Phase 6): `tracing.py` (every answer → `data/traces/traces.jsonl`), `evals/golden.jsonl` seed, `error_analysis.ipynb` (diagnose) — see `EVALUATION.md`. Each trace carries tokens + cost (`cost_usd`) + `error` (API failure → safe refusal, traced). Anthropic SDK **auto-instrumented** (OTEL / `opentelemetry-instrumentation-anthropic`) → Langfuse `generation` with native model/token/cost, **unified into one nested trace** via `@observe` + `finalize_langfuse` (business span → generations)
- [x] **EDD Tier-2 (optional): self-hosted Langfuse** via Podman (`infra/langfuse/`) — `answer()` mirrors traces to the local UI when `LANGFUSE_*` keys are set (best-effort, no-op without keys)

**Exit criteria:** ✅ cited answers on FinanceBench questions (AMD revenue → "$23.6 billion" [cited]); ✅ refuses on out-of-corpus questions; ✅ every Q&A traced for error analysis.

**Phase 1 complete.** Next: Phase 2 (expose retrieval as a model-callable tool).

---

## Phase 2 — Agentic tool-use (Pillar 2: Function calling) · 🟡

**Goal:** retrieval exposed as `search_documents` tool inside the SDK tool-use loop.
**Proves:** model *decides* to retrieve; multi-step reasoning is auditable.
**Cost:** ~US$2–8 (API). **Demo:** trace showing tool call → answer.

- [x] Define `search_documents(query, k)` tool schema (`tool_agent.py`) — F2.1
- [x] Manual ReAct tool-use loop (`tool_use` → `tool_result` → repeat, bounded `MAX_ROUNDS`) — F2.2
- [x] Multi-hop supported (loop lets Claude search again with refined queries) — F2.3
- [x] Per-answer trace of the whole trajectory (JSONL + **one nested Langfuse trace**: `answer_agentic` span → auto-instrumented `generation` per round, with native token/cost + verdict scores) — F2.5
- [x] **Deterministic verifier** (best-practice harness): citations must resolve (hard gate → refuse on fabrication) + numbers-verbatim score — strengthens F2.4
- [x] CLI `--agentic` flag; `notebooks/explore_agentic.ipynb`
- [ ] Tune/expand verifier on `math` slice in Phase 6 eval — F2.4 (full)

**Exit criteria:** ✅ trajectory visible (one nested Langfuse trace: `answer_agentic` → generations); ✅ Claude self-drives search; ✅ verifier blocks fabricated citations. Demo: AMD question → 1 search → cited answer (verdict pass); Netflix → search → NOT FOUND.

---

## Phase 3 — Claude on Bedrock (Pillar 3) · 🟡

**Goal:** swap `Anthropic` → `AnthropicBedrock`, region-pinned to `ap-southeast-2`.
**Proves:** AWS-native, data-resident inference; same loop.
**Cost:** ~US$2–8. **Demo:** identical loop now running on Sydney Bedrock.

- [x] **BLOCKER CHECK:** confirmed `au.anthropic.claude-sonnet-4-6` **ACTIVE** in `ap-southeast-2` — the **AU inference profile routes only within Australia** (ap-southeast-2 / ap-southeast-4), i.e. data stays in-country (PRD §14.1)
- [x] IAM: AWS managed `AmazonBedrockFullAccess` on a dedicated CLI user (demo; tighten to least-priv later)
- [x] Swap client to `AnthropicBedrock` via `LLM_BACKEND` switch (`llm.py`); pinned `au.anthropic.claude-sonnet-4-6`. `cost_usd` resolves profile ids; `response.usage` works on Bedrock (token/cost captured)
- [ ] Record pinned version in model card
- [ ] Re-run Phase 1/2 demos against Bedrock — ⛔ **blocked on AWS console: submit the Anthropic *use case details* form** (Bedrock returns 404 until then; our error-handling safely degrades to `NOT FOUND` + traces `error=NotFoundError`). Code verified to reach Bedrock; awaiting account approval (~15 min after form).

**Exit criteria:** same answers/citations via Bedrock; version pinned & recorded. *(Pending use-case-form approval, then re-run.)*

---

## Phase 4 — Bedrock Knowledge Base (Pillar 4) · ⬜

**Goal:** managed chunk/embed/index → **S3 Vectors** (default); retrieval via KB API.
**Proves:** managed RAG.
**Cost:** ✅ **S3 Vectors = pay-per-use, no OCU floor** (a few US$ for the demo corpus). OpenSearch Serverless only if hybrid/high-QPS is needed (then the standing OCU cost returns — tear down when idle).
**Demo:** KB-backed retrieval w/ native citations; ingestion job.

- [ ] Upload deduped corpus to S3 (`ap-southeast-2`)
- [ ] Use **customer-managed KB** (keeps chunking control + `RetrieveAndGenerate`); choose embedding model (Titan/Cohere) + chunking strategy
- [ ] Provision **S3 Vectors** index as the vector store (KMS-encrypted) — confirm `ap-southeast-2` in console
- [ ] Point `search_documents` tool at KB `Retrieve` API
- [ ] Validate native source attribution flows into citations
- [ ] (If hybrid needed) decide app-layer BM25+RRF vs OpenSearch upgrade
- [ ] Provision all KB/store via IaC (`AWS::Bedrock::KnowledgeBase` / CDK) for reproducible teardown

**Exit criteria:** answers cite KB-retrieved sources; reproducible via IaC.

---

## Phase 5 — Bedrock Agent (Pillar 5) · ⬜

**Goal:** Agent with governance instructions + Guardrails wraps the KB.
**Proves:** managed orchestration; refusal/citation/PII enforced by platform.
**Cost:** ~US$5–15. **Demo:** Agent refuses out-of-scope; redacts PII.

- [ ] Author Agent instructions (cite, quote-verbatim, refuse-if-unsupported) — versioned (git + Bedrock Prompt Management)
- [ ] Wire KB as knowledge source
- [ ] Create Bedrock Guardrails (PII redaction, denied topics, prompt-attack, **contextual grounding check** w/ threshold); attach in+out
- [ ] Enforce guardrail via IAM `bedrock:GuardrailIdentifier`
- [ ] `InvokeAgent` from app layer with `enableTrace: true`
- [ ] Set up Agent versions + aliases (Dev/Staging/Prod)
- [ ] Validate refusal on out-of-corpus questions; PII redaction + grounding-check on synthetic-PII queries

**Exit criteria:** governed agent demo — correct refusal + PII redaction + grounding-check observed.

---

## Phase 6 — Evaluation (cross-cutting) · ⬜

**Goal:** Bedrock RAG Eval + RAGAS + category governance tests; GitHub Actions CI gate + online sample.
**Proves:** the trust evidence.
**Cost:** ~US$5–15 (judge calls). **Demo:** eval report + CI gate blocking a bad change.

- [ ] RAGAS harness (local, Phases 1–2): faithfulness, response_relevancy, context_precision, context_recall
- [ ] Bedrock RAG Evaluation (LLM-as-judge) once KB is live: faithfulness, citation precision/coverage, refusal
- [ ] Use dual-use `context` as gold for context_recall/precision (PRD §10)
- [ ] Refusal-precision test on out-of-corpus questions (target ≥ 0.95)
- [ ] Numeric-correctness test on `math` (target ≥ 0.90, within tolerance)
- [ ] Baseline accuracy on `core_qa`; boolean exact-match
- [ ] **GitHub Actions workflow**: run golden-set eval on every PR as a required check (block on threshold regression — PRD §8.2)
- [ ] 5% online sampling → score (Bedrock Eval / `ApplyGuardrail`) → write back as custom CloudWatch metrics (PRD §8.3)

**Exit criteria (production thresholds, PRD §3/§11):**

| Metric | Target | Actual |
|---|---|---|
| faithfulness | ≥ 0.75 | — |
| refusal precision (out-of-corpus) | ≥ 0.95 | — |
| numeric correctness (`math`) | ≥ 0.90 | — |
| context_recall / precision | ≥ 0.70 / ≥ 0.70 | — |
| p95 latency | ≤ 6 s | — |
| cost / query | ≤ US$0.03 | — |

---

## Cost ledger (keep current)

| Phase | Estimated | Actual | Infra to delete |
|---|---|---|---|
| 1 | US$1–5 | — | — |
| 2 | US$2–8 | — | — |
| 3 | US$2–8 | — | — |
| 4 | a few US$ (S3 Vectors) | — | KB + S3 Vectors (cheap; tear down when idle) |
| 5 | US$5–15 | — | Agent, Guardrails (low cost) |
| 6 | US$5–15 | — | — |
| **Total target** | **< US$100** | — | (S3 Vectors removes the old OpenSearch standing-cost risk) |

> Note: the earlier "⚠️ OpenSearch Serverless / delete same day" line is retired — OpenSearch is now an optional upgrade, not the default store. Only reintroduce that standing cost if hybrid/high-QPS forces the upgrade.

---

## Open blockers / decisions

Mirror of PRD §14 — resolve before the dependent phase:
- [ ] **(Phase 3)** Claude model availability in `ap-southeast-2` / cross-region profile
- [ ] **(Phase 4)** embedding model + chunking strategy choice; confirm S3 Vectors in `ap-southeast-2` console
- [ ] **(Phase 4)** hybrid retrieval needed? → app-layer BM25+RRF vs OpenSearch upgrade
- [ ] **(Phase 5/6)** numeric tolerance band for `math` correctness
- [ ] **(Phase 5)** orchestration target: classic Bedrock Agents vs AgentCore (GA Oct 2025) for production
- [ ] **(Phase 5)** Automated Reasoning checks are US/EU-only (not Sydney) — accept US/EU processing or skip?
- [ ] Audit-log store decision (S3 Object Lock / WORM vs ledger)
