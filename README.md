# Policy Copilot

A citation-grounded **RAG agent** that answers employee questions about internal policy, financial, legal, and HR documents — with verbatim source attribution, or an explicit *"not found"* when the corpus can't support an answer. Built for a **regulated banking environment** on AWS-native managed services in `ap-southeast-2` (Sydney).

> **Thesis:** AI failures in regulated industries come from **trust and governance gaps, not technology limits.** Policy Copilot is a governance demonstrator that happens to do RAG — every answer is traceable, every figure is quoted not generated, and quality is continuously measured.

---

## Why it exists

Generic LLM chat fails in a bank for three reasons that risk and compliance teams care about: hallucinated facts/figures (a compliance incident), no provenance (unauditable), and silent quality degradation (it keeps answering confidently while becoming wrong). Policy Copilot is designed around making those failure modes **visible and controlled**.

---

## The five pillars (mandatory stack)

| # | Pillar | Role |
|---|---|---|
| 1 | **Anthropic SDK (Python)** | Messages API + tool-use loop — the orchestration contract |
| 2 | **Tool use / function calling** | Retrieval exposed as `search_documents`, a tool the model calls |
| 3 | **Claude on Amazon Bedrock** | AWS-native, region-pinned inference (`AnthropicBedrock`) |
| 4 | **Bedrock Knowledge Bases** | Managed RAG: chunk → embed → **S3 Vectors** (default; OpenSearch Serverless only for hybrid/high-QPS) |
| 5 | **Bedrock Agents** | Managed orchestration + governance instructions + Guardrails (AgentCore noted as forward direction) |

---

## Governance at a glance

Three first-class disciplines (full detail in `docs/PRD.md` §8):

- **Model governance** — model inventory, risk tiering (EU AI Act "limited risk"), validation sign-off, model card, RACI accountability, regulatory alignment (APRA CPS 230/234, SR 11-7).
- **Change control** — PR + **GitHub Actions** eval gate on a golden dataset, version pinning (model/prompt/config via git + Bedrock Prompt Management), shadow → canary → full rollout (multi-alias + app-layer split), one-step rollback, append-only audit log.
- **Operational monitoring** — health (latency, errors), **quality (online sampled faithfulness, refusal rate)**, drift, cost-per-query, safety (guardrail events). *Quality-first alerting* — silent degradation pages before any uptime alarm.

Plus: Bedrock Guardrails (PII redaction, denied topics, **contextual grounding check**), numeric-hallucination prevention (figures quoted verbatim), citation/source attribution, and "say I don't know" on out-of-scope questions. Full mechanism breakdown with sources in `docs/GOVERNANCE.md`.

---

## Evaluation

Two engines: **Bedrock RAG Evaluation** (AWS-native LLM-as-a-judge, GA Mar 2025) as the primary CI gate, **RAGAS** (faithfulness, response_relevancy, context_precision, context_recall) as the local/supplementary cross-check — **plus** category-specific governance tests:

| Test | Target |
|---|---|
| Faithfulness | ≥ 0.75 |
| **Refusal precision** (`not_found` — the key trust metric) | ≥ 0.95 |
| **Numeric correctness** (`math`, within tolerance) | ≥ 0.90 |
| context_recall / context_precision | ≥ 0.70 / ≥ 0.70 |

Offline as a CI gate; online on 5% sampled traffic written back to traces. Details in `docs/PRD.md` §11.

---

## Data

[`llmware/rag_instruct_benchmark_tester`](https://huggingface.co/datasets/llmware/rag_instruct_benchmark_tester) — 200 enterprise Q&A samples across 6 categories (core_qa 100, not_found 20, boolean 20, math 20, complex_qa 20, summary 20).

**Dual-use `context` trick:** the inline `context` column is reused two ways — deduped into the document corpus (to build the Knowledge Base) **and** as ground-truth context (to evaluate retrieval recall/precision). One dataset, self-contained corpus + retrieval ground truth, no extra labelling.

---

## Phased delivery

Each phase proves one pillar, is independently demo-able, and is cost-aware. Live status in `docs/PROGRESS.md`.

| Phase | Goal | Cost |
|---|---|---|
| 0 — Repo & CI foundation | git + GitHub Actions, branch protection | — |
| 1 — Local RAG | FAISS + Anthropic SDK | ~US$1–5 |
| 2 — Agentic tool-use | `search_documents` in the tool-use loop | ~US$2–8 |
| 3 — Claude on Bedrock | `AnthropicBedrock`, region-pinned | ~US$2–8 |
| 4 — Bedrock Knowledge Base | Managed RAG on **S3 Vectors** (pay-per-use, no OCU floor) | a few US$ |
| 5 — Bedrock Agent | Governance instructions + Guardrails | ~US$5–15 |
| 6 — Evaluation | Bedrock RAG Eval + RAGAS + governance tests | ~US$5–15 |

**Demo budget target: < US$100.** S3 Vectors removes the old OpenSearch standing-cost risk; OpenSearch is an optional upgrade only.

---

## Documentation

| Doc | Contents |
|---|---|
| [`docs/PRD.md`](docs/PRD.md) | Full product requirements — goals, scope, governance, evaluation, delivery |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Five pillars, request lifecycle, AWS service map, security/residency |
| [`docs/GOVERNANCE.md`](docs/GOVERNANCE.md) | Governance & detection mechanisms (Guardrails, eval, monitoring) with verified sources |
| [`docs/DEVELOPMENT_RULES.md`](docs/DEVELOPMENT_RULES.md) | DevOps/MLOps/AIOps: git+PR, GitHub Actions eval gate, IaC, versioning, rollout |
| [`docs/PROGRESS.md`](docs/PROGRESS.md) | Phase-by-phase task tracker, cost ledger, blockers |

> Capability claims about AWS services in these docs were verified against official AWS/Anthropic/RAGAS documentation (2025–2026). Source links live in `GOVERNANCE.md` and `DEVELOPMENT_RULES.md`.

---

## Region & residency

All data, embeddings, and inference stay in **`ap-southeast-2` (Sydney)**. No data leaves the region. Encryption at rest (KMS) + in transit (TLS); least-privilege IAM per service.
