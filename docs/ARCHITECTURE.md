# Policy Copilot — Technical Architecture

**Status:** Draft v1.0 · **Date:** 2026-06-26 · **Region:** AWS `ap-southeast-2` (Sydney) · Companion to `PRD.md`

This document expands PRD §9 into a buildable architecture: the five mandatory pillars, the request lifecycle, component contracts, AWS service map, and the governance/security controls that wrap every call.

---

## 1. Design Principles

1. **Trust over cleverness.** Every answer is traceable to source; ungrounded figures are refused, not generated.
2. **Managed-first.** Prefer Bedrock-managed RAG/orchestration over self-built infrastructure — fewer moving parts to validate and audit.
3. **The tool-use loop is the contract.** Retrieval is always a *tool the model calls*, never an implicit pre-fetch. This keeps the agent's reasoning auditable across all phases (local → Bedrock).
4. **Region lock.** Data, embeddings, and inference never leave `ap-southeast-2`.
5. **Evolvable, not rewritten.** The local Phase-1/2 architecture and the Bedrock Phase-3/4/5 architecture share the same logical interfaces (`search_documents`, the messages loop), so phases swap implementations without redesign.

---

## 2. Logical Architecture (target state — Phases 3–5)

```
                          ┌──────────────────────────────────────────────┐
   Employee question ─────▶│  Application / API layer (ap-southeast-2)     │
                          │  Anthropic SDK tool-use loop (the contract)   │  ◀── Pillar 1
                          └───────────────┬──────────────────────────────┘
                                          │ invoke_agent
                          ┌───────────────▼──────────────────────────────┐
                          │  Amazon Bedrock Agent                         │  ◀── Pillar 5
                          │  (governance instructions: cite, quote        │
                          │   numbers verbatim, refuse if unsupported)    │
                          │   ── Bedrock Guardrails (PII / denied topics) │
                          └───────┬───────────────────────┬──────────────┘
                                  │ tool call             │ generate
                  ┌───────────────▼──────────┐   ┌────────▼───────────────┐
                  │  Tool: search_documents  │   │  Claude on Bedrock      │  ◀── Pillar 3
                  │  (function calling)      │   │  (AnthropicBedrock      │
                  │   → KB Retrieve API      │   │   client, pinned ver.)  │
                  └───────────────┬──────────┘   └─────────────────────────┘
                                  │ retrieve                  ▲ Pillar 2 = the tool-use binding
                  ┌───────────────▼──────────────────────────┐
                  │  Amazon Bedrock Knowledge Base            │  ◀── Pillar 4
                  │  chunk → embed (Titan/Cohere) →           │
                  │  OpenSearch Serverless vector store       │
                  └───────────────┬──────────────────────────┘
                                  │ source-of-truth
                  ┌───────────────▼──────────────────────────┐
                  │  Amazon S3 — deduped document corpus      │
                  └───────────────────────────────────────────┘

   Cross-cutting: CloudWatch (health/quality/cost) · KMS (encryption) ·
   IAM (least-privilege) · CloudTrail (control-plane audit) ·
   Audit log (append-only) · CI eval gate · 5% online eval write-back
```

---

## 3. The Five Pillars — Component Detail

### Pillar 1 — Anthropic SDK (Python)
- **Role:** the orchestration contract. The app drives a messages API loop: send user turn → receive `tool_use` → execute tool → return `tool_result` → repeat until `end_turn`.
- **Local (Phase 1–2):** `from anthropic import Anthropic`.
- **AWS (Phase 3+):** `from anthropic import AnthropicBedrock` — identical loop, region-pinned client.
- **Why it matters:** one code path proves the reasoning loop locally (cheap) before any AWS spend, then swaps client without restructuring.

### Pillar 2 — Tool Use / Function Calling
- **Tool:** `search_documents(query: str, k: int = 5) -> list[Chunk]`.
- **Contract:** returns ranked chunks, each `{source_id, document_id, text, score}`.
- **Discipline:** the model *decides* when to retrieve; multi-hop questions may call it more than once. Empty result → the model must refuse (F-5), never fabricate.
- This binding is identical whether the tool wraps FAISS (Phase 2) or the Bedrock KB Retrieve API (Phase 4+).

### Pillar 3 — Claude on Amazon Bedrock
- **Client:** `AnthropicBedrock(aws_region="ap-southeast-2")`.
- **Model:** pinned ID + version (recorded in model card; see open question PRD §14.1 on Sydney availability / cross-region inference profile).
- **Why Bedrock:** AWS-native auth (IAM), data residency, no prompt/output retention for training, single billing/audit plane.

### Pillar 4 — Bedrock Knowledge Bases (managed RAG)
- **Pipeline:** S3 corpus → managed chunking → embeddings (Titan/Cohere) → **S3 Vectors** index (default).
- **Retrieval:** `bedrock-agent-runtime:Retrieve` (or `RetrieveAndGenerate`), returning chunks with native source attribution used for citations.
- **Vector store choice (verified):**
  - **S3 Vectors (default)** — GA Dec 2025, `ap-southeast-2` supported, **pay-per-use with no OCU floor** (~90% cheaper at scale per AWS), ~100 ms warm latency. **Semantic-only — no native hybrid (keyword+vector) search**, limited metadata filters (no `startsWith`/`stringContains`).
  - **OpenSearch Serverless (optional upgrade)** — adopt when you need hybrid search, rich metadata filtering, or low-latency high-QPS. Carries the standing OCU cost; provision only when justified, tear down when idle.
  - **Tiered pattern (AWS-recommended):** S3 Vectors as the cheap base, export "hot" vectors to OpenSearch when QPS/latency demand it.
- **Hybrid retrieval:** if keyword+vector is needed in the demo without OpenSearch, do it at the app layer — vector via S3 Vectors + in-process BM25 (e.g. SQLite FTS5 / `rank-bm25`), fused with Reciprocal Rank Fusion (RRF); optionally add a Bedrock reranker over over-fetched candidates. Production scale → OpenSearch native hybrid.
- **KB variants (verified):** *customer-managed* KB gives full chunking control + `RetrieveAndGenerate`; the newer *Bedrock-managed* KB auto-owns the store but restricts chunking and does **not** support `RetrieveAndGenerate`. Pick customer-managed for citation/chunking control.

### Pillar 5 — Bedrock Agents (managed orchestration)
- **Role:** hosts the agent instructions (system prompt encoding governance: cite sources, quote numbers verbatim, refuse if unsupported), wires the KB as an action/knowledge source, and attaches Guardrails.
- **Invocation:** `bedrock-agent-runtime:InvokeAgent` (with `enableTrace: true` for the audit trail).
- **Governance instructions** live here as a versioned artifact, not console free-text (PRD §8.2).
- **Versioning/rollout:** Agent `DRAFT` → immutable numbered versions → aliases (Dev/Staging/Prod). ⚠️ One alias = one version (`RoutingConfiguration` max = 1); **canary = multiple aliases + app-layer traffic split**, rollback = re-point alias.
- **Forward-looking:** AWS positions **Bedrock AgentCore** (GA Oct 2025) as the framework-agnostic managed-orchestration direction. Classic Bedrock Agents remains GA ("you can continue to do so"), no published EOL. Evaluate AgentCore for a multi-year build (PRD §14.9).

---

## 4. Request Lifecycle (target state)

1. **Ingress** — app receives question, attaches request ID + user context, opens an audit record.
2. **Input guardrail** — Bedrock Guardrails scan/redact PII and block denied topics / prompt attacks before the model sees the text.
3. **Agent invocation** — app calls `InvokeAgent`; the Agent (Claude on Bedrock) reasons over the question.
4. **Tool call** — Agent emits a `search_documents` tool call → KB `Retrieve` returns ranked chunks with source IDs.
5. **Grounded generation** — Agent composes the answer **using only retrieved spans**; figures quoted verbatim; citations attached. If chunks don't support an answer → explicit refusal.
6. **Output guardrail** — Guardrails re-scan the output (PII, denied topics) **and run the contextual grounding check** (grounding + relevance scores vs. threshold) to catch ungrounded/hallucinated answers.
7. **Response + audit** — answer + citations returned; audit record finalized (model+version, prompt/config version, retrieved source IDs, tool calls, guardrail events, final answer).
8. **Sampling** — 5% of traffic forked to async eval (faithfulness, refusal correctness) written back to traces (PRD §8.3, §11).

---

## 5. Phase Evolution — what changes per phase

| Concern | Phase 1–2 (local) | Phase 3 | Phase 4 | Phase 5 |
|---|---|---|---|---|
| Inference client | `Anthropic` | `AnthropicBedrock` | same | via Agent |
| Retrieval backend | FAISS (local) | FAISS | Bedrock KB → **S3 Vectors** | Bedrock KB → S3 Vectors |
| Orchestration | app-side SDK loop | app-side SDK loop | app-side SDK loop | Bedrock Agent |
| Guardrails | prompt-only | prompt-only | prompt-only | Bedrock Guardrails (+ grounding check) |
| Citations | from FAISS chunks | same | from KB source attribution | from KB via Agent |
| Eval engine | RAGAS (local) | RAGAS | RAGAS + Bedrock RAG Eval | Bedrock RAG Eval + RAGAS |

The **logical interfaces are stable**; only implementations swap. This is the core of the "evolvable, not rewritten" principle.

---

## 6. AWS Service Map

| Service | Purpose | Notes |
|---|---|---|
| Amazon Bedrock (Claude) | Inference | `AnthropicBedrock`, version-pinned |
| Bedrock Knowledge Bases | Managed RAG | chunk/embed/index |
| Bedrock Agents | Orchestration | governance instructions + KB wiring; versions + aliases |
| Bedrock Guardrails | Safety | PII redaction, denied topics, prompt-attack, contextual grounding check; enforced via IAM `bedrock:GuardrailIdentifier` |
| Bedrock Evaluations | Quality | LLM-as-judge RAG eval (offline gate + sampled online) |
| Amazon S3 + **S3 Vectors** | Source corpus + vector store | deduped `context` documents; pay-per-use vector index (default) |
| OpenSearch Serverless | Vector store (optional) | only for hybrid search / high-QPS — standing OCU cost |
| Amazon CloudWatch | Monitoring | health/quality/cost metrics + alarms; model-invocation logs |
| AWS KMS | Encryption | at-rest keys for S3/vector store |
| AWS IAM | Access control | least-privilege per service role |
| AWS CloudTrail | Control-plane audit | who-did-what on AWS resources |
| GitHub Actions | CI/CD | eval gate, IaC deploy, lint/test |
| CloudFormation / CDK `AWS::Bedrock::*` | Infra as code | KB, Agent, Guardrail, Prompt, Flow resources |

---

## 7. Security & Data Residency

- **Region lock:** every service provisioned in `ap-southeast-2`; no cross-region calls except an AU-resident inference profile if required for model availability (PRD §14.1).
- **Encryption:** KMS at rest (S3, OpenSearch), TLS in transit.
- **IAM:** distinct least-privilege roles for app, Agent, KB ingestion; no wildcard resource grants.
- **No training retention:** Bedrock does not retain prompts/outputs for training.
- **Audit:** application audit log (append-only, ≥7yr target) for *answers*; CloudTrail for *infrastructure changes*.

---

## 8. Observability Hooks (feeds PRD §8.3)

| Signal class | Source | Surfaced in |
|---|---|---|
| Latency p95/p99, errors, throttles | Bedrock/CloudWatch metrics | CloudWatch dashboard |
| Faithfulness, refusal rate, citation-resolution | 5% async eval write-back (Bedrock Eval / `ApplyGuardrail`) → custom CloudWatch metrics | traces + dashboard |
| Per-answer grounding | Agent trace + Guardrails grounding-check scores | traces + dashboard |
| Embedding/query drift | sampled embedding stats vs baseline | drift monitor |
| Cost per query, vector spend | Cost Explorer + per-request token accounting | cost dashboard + alarm |
| Guardrail trips | `GuardrailTrace` / Guardrails events | safety dashboard |
| Full request/response audit | Bedrock model-invocation logging → CloudWatch/S3 | audit store |

**Alerting is quality-first:** rising unfaithfulness with stable latency must page before any uptime alarm would (PRD §8.3).

**Verified caveats:** (1) online LLM-as-judge is a customer-built sampling + write-back loop, not a managed toggle — Bedrock Evaluations is batch/job-oriented. (2) Model-invocation logs store the **original unmasked input** even when Guardrails redacts PII downstream — apply CloudWatch Logs data protection.

---

## 9. Open Architecture Questions

Tracked against PRD §14. Architecture-specific:
- Embedding model choice (Titan vs Cohere) and its `ap-southeast-2` availability.
- Chunking strategy/size for the `context` corpus (affects context_precision/recall — PRD §11). Note: customer-managed KB locks chunking after the data source connects.
- Whether to use Agent `RetrieveAndGenerate` vs. explicit `Retrieve` + app-side generation for tighter citation control (note: Bedrock-managed KB does not support `RetrieveAndGenerate`).
- Audit-log store: append-only S3 with Object Lock (WORM) vs. dedicated ledger.
- Does the demo need hybrid retrieval? If yes → app-layer BM25+RRF (cheap) vs. OpenSearch (production). S3 Vectors is semantic-only.
- Classic Bedrock Agents vs. Bedrock AgentCore as the orchestration target for production hardening (PRD §14.9).
- Automated Reasoning checks region gap: feature is US/EU-only, not `ap-southeast-2` (PRD §14.8).
