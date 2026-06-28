# Policy Copilot — Product Requirements Document

**Document type:** Production PRD (portfolio demonstrator) · **Owner:** AI Engineering · **Status:** Draft v1.0 · **Date:** 2026-06-26 · **Region:** AWS `ap-southeast-2` (Sydney) · **Classification:** Internal

---

## 1. Executive Summary

Policy Copilot is a citation-grounded RAG agent that lets bank employees ask natural-language questions about internal policy, financial, legal, and HR documents and receive answers with verbatim source attribution — or an explicit "not found" when the corpus cannot support an answer. It is built entirely on AWS-native managed services (Claude on Amazon Bedrock, Bedrock Knowledge Bases, Bedrock Agents) with the Anthropic SDK tool-use loop as the orchestration contract, deployed in Sydney for data residency. The design treats the hard problem of regulated AI as **trust and governance, not retrieval accuracy** — every answer is traceable, every figure is quoted not generated, and quality is continuously measured rather than assumed. This document specifies the product, the three governance disciplines (model governance, change control, operational monitoring), a quantified evaluation plan, and a six-phase, cost-aware delivery path.

---

## 2. Problem & Business Context

Bank employees lose measurable time hunting through policy PDFs, intranet pages, and contract repositories; the alternative — asking a colleague or compliance — adds latency and load. Generic LLM chat is unacceptable in this setting for three reasons regulators and risk teams care about:

- **Hallucinated facts and figures** — an invented interest rate, threshold, or clause is a compliance incident, not a UX defect.
- **No provenance** — an answer a reviewer cannot trace to a source document is unauditable and therefore unusable for any controlled process.
- **Silent failure** — model and data drift degrade answer quality invisibly; the system keeps responding confidently while becoming wrong.

The governing thesis of this project: **AI failures in regulated industries come from trust and governance gaps, not technology limits.** Policy Copilot is therefore scoped as a *governance demonstrator* that happens to do RAG, not a RAG demo that bolts on governance later.

---

## 3. Goals & Success Metrics

| Goal | Metric | Target |
|---|---|---|
| Faithful answers | RAGAS faithfulness (offline + online) | **≥ 0.75** |
| Correct refusals | Refusal precision on out-of-corpus questions | **≥ 0.95** |
| Numeric integrity | Numeric correctness within tolerance (`math` set) | **≥ 0.90** |
| Retrieval quality | RAGAS context_recall / context_precision | **≥ 0.70 / ≥ 0.70** |
| Responsiveness | End-to-end p95 latency | **≤ 6 s** |
| Unit economics | Cost per query (model + retrieval) | **≤ US$0.03** |
| Traceability | Answers with ≥1 resolvable citation | **100%** of non-refusals |

**Quantified ROI proxies (illustrative, for the business case):**

- **Hours saved per query:** assume manual lookup averages 8–12 min; Copilot returns in <10 s. At ~6 min net saving × 500 queries/day ≈ **50 staff-hours/day** reclaimed.
- **Cost per query** ≤ US$0.03 vs. fully-loaded analyst lookup cost of ~US$4–6 → **>99% marginal cost reduction** per lookup.
- **Error-rate reduction:** refusal precision ≥ 0.95 on out-of-scope questions converts the dominant compliance risk (confident wrong answers) into a measured, bounded one.
- These are *proxies for the business case*, not audited savings; production sign-off requires a live A/B against current process (see §14).

---

## 4. Users & Personas

| Persona | Need | What "good" looks like |
|---|---|---|
| **Frontline employee** (RM, ops, branch) | Fast, trustworthy answer to a policy/procedure question | Answer + citation in seconds, or honest "not found" |
| **Compliance / Risk reviewer** | Verify an answer is grounded and traceable | Every claim links to source text; refusals are correct |
| **Model Risk / Validation (2nd line)** | Evidence the model is inventoried, tiered, validated | Model card, eval results, sign-off record |
| **AI Platform Engineer (1st line)** | Operate, monitor, roll back safely | Dashboards, eval gate, version pinning, audit log |
| **Internal Auditor (3rd line)** | Reconstruct any past answer and its controls | Immutable audit trail of prompt, version, sources, output |

---

## 5. Scope

**In scope**
- Q&A over an enterprise document corpus with citations and refusal behaviour
- Retrieval exposed as a model-callable tool (function calling)
- Managed RAG (Knowledge Base) and managed orchestration (Agent) on Bedrock
- Bedrock Guardrails (PII redaction, denied topics)
- Offline CI eval gate + online sampled eval
- The three governance disciplines (§8)

**Out of scope (this iteration)**
- Document *write*/update workflows; Copilot is read-only over the corpus
- Multi-turn transactional actions (no money movement, no system-of-record writes)
- Authn/authz, SSO, and document-level entitlement enforcement (assumed provided by host platform — see §14)
- Multilingual corpus (English only)
- Fine-tuning / custom model training (RAG + prompting only)
- Real customer PII data — demonstrator uses the public FinanceBench benchmark (§10)

---

## 6. Functional Requirements

| ID | Requirement |
|---|---|
| F-1 | User submits a NL question; system returns an answer **or** an explicit refusal. |
| F-2 | Retrieval is invoked via **tool use / function calling** (`search_documents(query, k)` → ranked chunks with source IDs). |
| F-3 | Every non-refusal answer carries **≥1 citation** resolving to source chunk text and document ID. |
| F-4 | **Numeric facts are quoted verbatim** from retrieved source spans; the model must not compute or paraphrase figures it cannot point to. Math answers cite the source span used. |
| F-5 | If retrieved context does not support an answer, the system responds **"NOT FOUND / I don't know"** rather than guessing (out-of-scope / out-of-corpus cases). |
| F-6 | **Guardrails** redact PII and block denied topics on both input and output. |
| F-7 | Each request emits an **audit record**: timestamp, user, question, model+version, prompt/config version, retrieved source IDs, tool calls, final answer, guardrail events. |
| F-8 | Answers degrade gracefully: retrieval empty → refusal; tool error → safe error message, never a fabricated answer. |
| F-9 | Online traffic is **5% sampled** for automated quality scoring written back to traces. |

---

## 7. Non-Functional Requirements

| Dimension | Requirement |
|---|---|
| **Latency** | p95 ≤ 6 s end-to-end (retrieval + generation); retrieval p95 ≤ 1.5 s. |
| **Cost** | ≤ US$0.03/query steady-state. Default vector store is **Amazon S3 Vectors** (GA Dec 2025, Sydney-supported, no standing OCU floor — pay-per-use). OpenSearch Serverless is an *optional upgrade* only when hybrid search or high-QPS/low-latency is needed; it carries a fixed OCU standing cost (see §12). |
| **Security** | All data and inference in `ap-southeast-2`; encryption at rest (KMS) + in transit (TLS); least-privilege IAM per service; no data leaves region. |
| **Data residency** | Bedrock model invocation, KB, Agent, vector store all Sydney-resident. Confirm chosen Claude model is available in `ap-southeast-2` or via AU-resident cross-region inference profile (see §14). |
| **Availability** | Best-effort for demonstrator; managed services inherit AWS SLAs. No custom HA required this phase. |
| **Auditability** | Audit log immutable (append-only), retained ≥ regulatory minimum (assume 7 yrs for the production target). |
| **Privacy** | No model training on user data; Bedrock does not retain prompts/outputs for training. |

---

## 8. Responsible AI & Governance *(first-class section)*

The premise: in regulated banking, **the failure mode is silent quality degradation, not downtime.** A system that returns wrong-but-confident answers passes every uptime check. These three disciplines exist to make that failure mode *visible and controlled*.

### 8.1 Model Governance

| Control | Implementation |
|---|---|
| **Model inventory** | Single registered entry: Claude (on Bedrock), model ID + version pinned, owner, purpose, data classification. |
| **Risk tiering** | Internal-facing, read-only, human-in-the-loop advisory → **EU AI Act "limited risk"**; mapped to bank's internal model-risk tier. Documented rationale. |
| **Validation sign-off** | 2nd-line Model Risk reviews eval evidence (§11) and signs off before any promotion to "production" status. No sign-off → stays in shadow. |
| **Model card** | Maintained artifact: intended use, training-data provenance (vendor), known limitations, eval results, guardrail config, out-of-scope uses, refusal behaviour. |
| **Accountability** | RACI: AI Platform Eng *owns/operates*; Model Risk *validates/approves*; Compliance *monitors*; Internal Audit *reviews*. Named roles, not "the team." |
| **Regulatory alignment** | **APRA CPS 230** (operational risk, critical-ops resilience), **CPS 234** (information security), **SR 11-7** (model risk: development/validation/governance lifecycle), **EU AI Act** (risk tiering + transparency obligations). Each mapped to a concrete control above. |

### 8.2 Change Control

> No change reaches production except through code review + a passing eval gate.

- **PR + CI eval gate (GitHub Actions):** every PR runs the golden-dataset eval (§11) as a required status check; merge blocked if thresholds in §3 regress. Implementation in `DEVELOPMENT_RULES.md`.
- **Version pinning:** model ID/version, prompt template, retrieval config, and Guardrail version are all pinned and recorded per release. Bedrock-native versioning is used where available (Prompt Management `CreatePromptVersion`, Agent/Flow versions + aliases).
- **Prompt/config versioning:** prompts and agent instructions are versioned artifacts in source control + Bedrock Prompt Management, not console-edited free text.
- **Rollout discipline:** **shadow** (runs silently, scored, no user impact) → **canary** (small % of live traffic) → **full**. Each gate requires eval + monitoring green. ⚠️ Note: a single Bedrock Agent/Flow alias points to exactly one version (`RoutingConfiguration` max = 1) — true canary is done with **multiple aliases + an app-layer traffic split**, not weighting inside one alias.
- **Rollback:** re-point the alias to the last-known-good immutable version — one step.
- **Audit log:** who changed what, when, with which eval result and approval — append-only.

### 8.3 Operational Monitoring

| Class | Signals | Why it matters |
|---|---|---|
| **System health** | p95/p99 latency, error rate, throttles | Baseline availability |
| **Quality (the critical one)** | Online sampled (5%) RAGAS faithfulness, refusal rate, citation-resolution rate | Catches **silent quality degradation** — the real risk |
| **Drift** | Embedding/query distribution shift vs. baseline | Corpus or usage drifting away from validated conditions |
| **Cost** | Cost-per-query, KB/vector-store spend | ROI integrity + runaway-spend alarm |
| **Safety** | Guardrail trips (PII redactions, denied topics), refusal anomalies | Compliance evidence + early-warning |

Alerting is **quality-first**: a stable-latency / rising-unfaithfulness trend pages before any uptime alarm would.

### 8.4 Cross-cutting safety controls

- **Bedrock Guardrails:** PII detection/redaction (incl. `US_BANK_ACCOUNT_NUMBER`, `SWIFT_CODE`), denied topics, content + prompt-attack filters — applied input and output. Enforced platform-wide via the IAM condition key `bedrock:GuardrailIdentifier` so **no Claude call can bypass the guardrail**.
- **Numeric-hallucination prevention:** the agent instructions mandate that figures be **quoted verbatim from retrieved source spans**; ungrounded numbers trigger refusal. Backed at runtime by the Guardrails **contextual grounding check** (per-response grounding + relevance scores 0–1 with a configurable threshold), and validated offline by the `math` and faithfulness evals.
- **Citation / source attribution:** non-refusal answers must cite resolvable source chunks (F-3). Bedrock KB `RetrieveAndGenerate` returns citations natively; the self-built path can use Anthropic's native Citations feature (available on Bedrock Converse).
- **"Say I don't know":** out-of-scope/unsupported questions return an explicit refusal (F-5), measured by refusal precision (§11).
- **Formal-logic policy check (optional, regional caveat):** Guardrails **Automated Reasoning checks** (GA Aug 2025) can mathematically verify answers against authored policy rules. ⚠️ Detect-mode only and **not available in `ap-southeast-2`** (US/EU regions only) — see §14 open question on data residency.

See `GOVERNANCE.md` for the full mechanism-by-mechanism breakdown with source links.

---

## 9. Technical Architecture

All five mandatory pillars, AWS-native, Sydney-resident. See `ARCHITECTURE.md` for the detailed component breakdown.

```
                          ┌──────────────────────────────────────────────┐
   Employee question ─────▶│  Application / API layer (ap-southeast-2)     │
                          │  Anthropic SDK tool-use loop (the contract)   │  ◀── Pillar 1
                          └───────────────┬──────────────────────────────┘
                                          │ invoke
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
                  │                          │   │   client, pinned ver.)  │
                  └───────────────┬──────────┘   └─────────────────────────┘
                                  │ retrieve                  ▲ Pillar 2 = the tool-use binding
                  ┌───────────────▼──────────────────────────┐
                  │  Amazon Bedrock Knowledge Base            │  ◀── Pillar 4
                  │  chunk → embed → S3 Vectors (default)     │
                  │  [OpenSearch Serverless = opt. upgrade]   │
                  │  vector store (managed RAG)               │
                  └───────────────────────────────────────────┘

   Cross-cutting: CloudWatch (health/quality/cost) · KMS · IAM least-privilege ·
   Audit log (append-only) · GitHub Actions CI eval gate · 5% online eval write-back to traces
```

**Pillar mapping**

| # | Pillar | Where it lives |
|---|---|---|
| 1 | Anthropic SDK (Python) | App layer messages API + tool-use loop; locally via `Anthropic`, on AWS via `AnthropicBedrock` |
| 2 | Tool use / function calling | `search_documents` tool the model decides to call |
| 3 | Claude on Amazon Bedrock | Inference via `AnthropicBedrock` client, region-pinned |
| 4 | Bedrock Knowledge Bases | Managed chunk/embed/index over corpus → **S3 Vectors** (default), OpenSearch Serverless (optional upgrade) |
| 5 | Bedrock Agents | Managed orchestration + governance instructions + Guardrails. (Forward-looking: AWS steers new agentic builds toward **Bedrock AgentCore**, GA Oct 2025 — see §14.) |

**Supporting AWS services:** S3 (source corpus + S3 Vectors store), CloudWatch (monitoring/alarms), KMS (encryption), IAM (least-privilege), CloudTrail (control-plane audit). CI/CD via **GitHub Actions**; infra as code via CloudFormation/CDK `AWS::Bedrock::*`.

---

## 10. Data Plan

**Primary corpus — FinanceBench** (`PatronusAI/financebench`): 150 expert-written (CFA) Q&A over **real SEC filings** (10-K / 10-Q / 8-K / earnings) from 40 US companies. Each row: `question`, `answer`, `evidence` (gold supporting text), `doc_name` → source PDF, plus `doc_type`, `company`, `gics_sector`. **License: CC-BY-NC-4.0 — demonstrator only; a production deployment needs a commercial or internal corpus.**

- The 150 questions span **84 unique documents**. For a cost-aware demo we take a **reproducible lean subset of 8 documents** (most-questioned first; `select_documents`), covering **40 questions** and ~**1,583 pages / 4.9M chars** — genuine "needle-in-a-haystack" retrieval over full filings (e.g. PepsiCo's 10-K alone is 503 pages).
- Subset: AMD, American Express, Boeing, PepsiCo, Amcor, Ulta Beauty, 3M (10-K + 10-Q) — across IT, financials, industrials, consumer, materials.
- PDFs are fetched from the FinanceBench GitHub repo and parsed **locally with `pymupdf4llm` → Markdown** (Phase 1); on AWS the same PDFs are parsed by **Bedrock KB** (Phase 4). Same documents, two parsers — the "evolvable, not rewritten" principle.

**Dual-use evidence (retrieval ground truth):**
1. **Corpus:** the full parsed filings are uploaded to S3, chunked, embedded, indexed — what retrieval searches.
2. **Gold context:** each row's `evidence` is the gold supporting passage, enabling RAGAS `context_recall` / `context_precision` and citation checks — did retrieval find the *right* passage inside a 100+ page filing.

**Governance slices:**
- Faithfulness, numeric correctness, and citations → from **FinanceBench** (numeric-heavy real filings).
- **Refusal / "I don't know"** → FinanceBench has **no labelled unanswerable set**, so we use **out-of-corpus questions**: since only 8 of the 84 documents are ingested, questions whose source filing is absent must be answered "NOT FOUND" rather than guessed. Same-domain, single data source.

**No real PII** is used; Guardrails are validated against synthetic PII injected into test queries.

---

## 11. Evaluation Plan *(first-class section)*

See `PROGRESS.md` Phase 6 for execution tracking and `GOVERNANCE.md` for tooling detail.

**Two complementary engines:**
- **Bedrock RAG Evaluation (LLM-as-a-judge)** — AWS-native, GA Mar 2025. Primary engine for the CI gate. Native metrics include faithfulness/groundedness, **citation precision**, **citation coverage**, correctness, completeness, plus responsible-AI metrics (**Refusal**, harmfulness, stereotyping). Can evaluate the Bedrock KB directly or bring-your-own responses.
- **RAGAS** — open-source, supplementary cross-check and the engine for the local Phases 1–2 (before Bedrock is wired). Note: `answer_relevancy` is now `response_relevancy` in current RAGAS.

**Core metrics** (offline gate + online sample):

| Metric | What it catches | Threshold |
|---|---|---|
| faithfulness / groundedness | Answer grounded in retrieved context (anti-hallucination) | ≥ 0.75 |
| response_relevancy | Answer addresses the question | ≥ 0.70 |
| context_precision | Retrieved chunks are relevant (low noise) | ≥ 0.70 |
| context_recall | The needed context was retrieved | ≥ 0.70 |

**Category-specific governance tests** (the regulated-finance differentiators):

| Test | Dataset slice | Metric | Threshold |
|---|---|---|---|
| **Refusal** *(most important)* | FinanceBench out-of-corpus questions | Refusal precision — said "NOT FOUND" instead of hallucinating | **≥ 0.95** |
| **Numeric correctness** | FinanceBench numeric questions | Figure correct within tolerance, quoted from source | **≥ 0.90** |
| Faithfulness & citation | FinanceBench (40) | Groundedness + citation precision | faith ≥ 0.75 |
| Answer correctness | FinanceBench (40) | Correct vs. expert (CFA) answer | ≥ 0.80 |

**Offline (CI gate, GitHub Actions):** the golden set (FinanceBench: 40 in-corpus + out-of-corpus refusal questions) runs on every PR; any threshold regression blocks merge (§8.2). Results attach to the model card.

**Online (production):** **5% of live traffic** is sampled, scored for faithfulness + refusal behaviour by an automated judge, and **written back to the request traces** for dashboards and drift detection (§8.3). Note: this is a customer-built loop (sample logged invocations → score via Bedrock Evaluations / `ApplyGuardrail` → write back as custom CloudWatch metrics), not a single managed toggle. This is how silent degradation surfaces.

---

## 12. Phased Delivery Plan & Milestones

Each phase is independently demo-able and proves one pillar. Costs are rough demo-scale estimates (USD). Live status tracked in `PROGRESS.md`.

| Phase | Goal | What it proves | Rough cost | Demo |
|---|---|---|---|---|
| **1 — Local RAG** | FAISS + Anthropic SDK over the corpus | Pillar 1; baseline retrieval+answer works | ~US$1–5 (API only) | CLI: question → cited answer locally |
| **2 — Agentic tool-use** | Retrieval as a `search_documents` tool in the SDK tool-use loop | Pillar 2; model *decides* to retrieve, multi-step | ~US$2–8 (API) | Trace showing tool call → answer |
| **3 — Claude on Bedrock** | Swap `Anthropic` → `AnthropicBedrock`, region-pinned | Pillar 3; AWS-native, data-resident inference | ~US$2–8 | Same loop, now Sydney Bedrock |
| **4 — Bedrock Knowledge Base** | Managed chunk/embed/index → **S3 Vectors** (default) | Pillar 4; managed RAG | **Pay-per-use, no standing OCU floor** (S3 Vectors); a few US$ for the demo corpus. OpenSearch only if upgraded | KB-backed retrieval w/ native citations; ingestion job |
| **5 — Bedrock Agent** | Agent + governance instructions + Guardrails | Pillar 5; managed orchestration, refusal/citation/PII enforced | ~US$5–15 | Agent refuses out-of-scope; redacts PII; grounding check |
| **6 — Evaluation** | Bedrock RAG Eval + RAGAS + category governance tests; GitHub Actions CI gate + online sample | Cross-cutting; the trust evidence | ~US$5–15 (judge calls) | Eval report + CI gate blocking a bad change |

**Cost discipline:** Phases 1–3 are near-free. With **S3 Vectors as the default store, Phase 4 no longer carries a large standing cost** (pay-per-use) — the earlier "delete the same day" urgency applied to OpenSearch Serverless, which is now an optional upgrade only. Still tear down demo infra when idle as hygiene. Total demo budget target **< US$100**.

**Milestones:** M1 = Phases 1–2 (local agentic RAG). M2 = Phases 3–5 (fully AWS-native governed agent). M3 = Phase 6 (eval gate + dashboards) → demo-ready.

---

## 13. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Numeric hallucination | Med | High | Quote-verbatim rule (F-4); `math` eval ≥ 0.90; refuse if ungrounded |
| Confident wrong answer on out-of-scope Q | Med | High | Refusal precision ≥ 0.95; out-of-corpus refusal gate; agent refusal instructions |
| **Silent quality degradation** | Med | High | Online 5% sampling (Bedrock Eval/grounding check) + drift monitoring; quality-first alerting |
| Vector-store cost overrun | Low | Med | S3 Vectors default (pay-per-use, no OCU floor); only adopt OpenSearch when hybrid/high-QPS justifies it; cost alarm |
| Automated Reasoning not in `ap-southeast-2` | High | Med | Treat formal-logic check as optional; rely on contextual grounding check (region-available) for the demo; revisit if US/EU processing is acceptable (§14) |
| Claude model not in `ap-southeast-2` | Med | High | Verify availability / AU cross-region inference profile before Phase 3 (§14) |
| Retrieval misses correct passage | Med | Med | context_recall ≥ 0.70 gate; tune chunking; dual-use ground truth |
| PII leakage | Low | High | Guardrails redaction in+out; no real PII in demo; validate with synthetic PII |
| Eval set small (FinanceBench 40 + refusal 20) to be conclusive | High | Med | Treat as gate not proof; expand subset / golden set before production sign-off |
| Prompt/config drift via console edits | Med | Med | All prompts/config version-controlled; no console free-text in prod |

---

## 14. Assumptions & Open Questions

**Assumptions**
- Authentication, authorisation, and document-level entitlements are provided by the host platform; Copilot is read-only and entitlement-agnostic in this iteration.
- The chosen Claude model is available in `ap-southeast-2` directly or via an Australia-resident cross-region inference profile (to be confirmed before Phase 3).
- The public FinanceBench dataset (real SEC filings) is an acceptable proxy for internal documents for demonstrator purposes; its CC-BY-NC licence is demo-only, so production uses a commercial/internal corpus under the same controls.
- Audit-log retention target of 7 years reflects a typical regulatory minimum; actual period set by the client's records policy.
- Vector store defaults to S3 Vectors; OpenSearch Serverless adopted only if hybrid search / high-QPS is required.
- Demo infrastructure is torn down when idle as hygiene (no longer cost-critical now S3 Vectors has no OCU floor).

**Open questions**
1. Which exact Claude model/version is pinned for production, and is it region-resident in Sydney?
2. What is the real production query volume (drives cost, capacity, and ROI numbers)?
3. Who are the *named* accountable owners for the RACI in §8.1 at the client?
4. What is the client's internal model-risk tier mapping vs. the EU AI Act "limited risk" classification used here?
5. What live A/B baseline (current manual process timing/cost) will validate the ROI proxies in §3?
6. Required audit-log retention period and immutability standard (WORM/Object Lock)?
7. Acceptable numeric tolerance band for the `math` correctness metric — exact match vs. ±rounding?
8. **Data residency vs. Automated Reasoning checks:** that Guardrails feature runs only in US/EU regions, not `ap-southeast-2`. Is US/EU processing of policy-check payloads acceptable, or do we forgo it and rely on the contextual grounding check (Sydney-available)?
9. **Orchestration target:** classic Bedrock Agents (current pillar 5) vs. **Bedrock AgentCore** (GA Oct 2025, AWS's forward direction) for a multi-year build — evaluate before production hardening.
10. Does the demo need hybrid (keyword + vector) retrieval? If yes, plan app-layer BM25+RRF (demo) or OpenSearch (production), since S3 Vectors is semantic-only.
