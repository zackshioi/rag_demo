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

## Phase 1 — Local RAG (Pillar 1: Anthropic SDK) · ⬜

**Goal:** FAISS + Anthropic SDK answer questions over the corpus with citations.
**Proves:** baseline retrieve+answer works end-to-end, locally, near-zero cost.
**Cost:** ~US$1–5 (API only). **Demo:** CLI — question → cited answer.

- [x] Load `llmware/rag_instruct_benchmark_tester`; inspect 6 categories (`src/policy_copilot/data.py`) — real labels: `core`/`not_found_classification`/`boolean`/`math_basic`/`complex_qa`/`summary`
- [x] Dedup `context` column → local document corpus (200 rows → 51 docs)
- [ ] Build FAISS index (embed chunks)
- [ ] `Anthropic` messages loop: retrieve → ground → answer with citations
- [ ] Refusal behaviour when retrieval is empty/weak (F-5)
- [ ] CLI demo script

**Exit criteria:** cited answers on `core_qa` samples; refuses on obvious out-of-scope.

---

## Phase 2 — Agentic tool-use (Pillar 2: Function calling) · ⬜

**Goal:** retrieval exposed as `search_documents` tool inside the SDK tool-use loop.
**Proves:** model *decides* to retrieve; multi-step reasoning is auditable.
**Cost:** ~US$2–8 (API). **Demo:** trace showing tool call → answer.

- [ ] Define `search_documents(query, k)` tool schema
- [ ] Implement tool-use loop (`tool_use` → `tool_result` → repeat)
- [ ] Support multi-hop (>1 retrieval) for `complex_qa`
- [ ] Emit per-request trace (tool calls, sources, answer) — audit precursor (F-7)
- [ ] Verify verbatim-number behaviour on `math` samples (F-4)

**Exit criteria:** tool-call trace visible; numbers quoted from source, not generated.

---

## Phase 3 — Claude on Bedrock (Pillar 3) · ⬜

**Goal:** swap `Anthropic` → `AnthropicBedrock`, region-pinned to `ap-southeast-2`.
**Proves:** AWS-native, data-resident inference; same loop.
**Cost:** ~US$2–8. **Demo:** identical loop now running on Sydney Bedrock.

- [ ] **BLOCKER CHECK:** confirm Claude model available in `ap-southeast-2` or AU cross-region profile (PRD §14.1)
- [ ] IAM role + least-privilege Bedrock invoke policy
- [ ] Swap client to `AnthropicBedrock`; pin model ID + version
- [ ] Record pinned version in model card
- [ ] Re-run Phase 1/2 demos against Bedrock

**Exit criteria:** same answers/citations via Bedrock; version pinned & recorded.

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
- [ ] Validate refusal on `not_found`; PII redaction + grounding-check on synthetic-PII queries

**Exit criteria:** governed agent demo — correct refusal + PII redaction + grounding-check observed.

---

## Phase 6 — Evaluation (cross-cutting) · ⬜

**Goal:** Bedrock RAG Eval + RAGAS + category governance tests; GitHub Actions CI gate + online sample.
**Proves:** the trust evidence.
**Cost:** ~US$5–15 (judge calls). **Demo:** eval report + CI gate blocking a bad change.

- [ ] RAGAS harness (local, Phases 1–2): faithfulness, response_relevancy, context_precision, context_recall
- [ ] Bedrock RAG Evaluation (LLM-as-judge) once KB is live: faithfulness, citation precision/coverage, refusal
- [ ] Use dual-use `context` as gold for context_recall/precision (PRD §10)
- [ ] Refusal-precision test on `not_found` (target ≥ 0.95)
- [ ] Numeric-correctness test on `math` (target ≥ 0.90, within tolerance)
- [ ] Baseline accuracy on `core_qa`; boolean exact-match
- [ ] **GitHub Actions workflow**: run golden-set eval on every PR as a required check (block on threshold regression — PRD §8.2)
- [ ] 5% online sampling → score (Bedrock Eval / `ApplyGuardrail`) → write back as custom CloudWatch metrics (PRD §8.3)

**Exit criteria (production thresholds, PRD §3/§11):**

| Metric | Target | Actual |
|---|---|---|
| faithfulness | ≥ 0.75 | — |
| refusal precision (`not_found`) | ≥ 0.95 | — |
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
