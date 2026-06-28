# Policy Copilot — Governance & Detection (verified)

**Status:** Draft v1.0 · **Date:** 2026-06-26 · Companion to `PRD.md` §8 and `ARCHITECTURE.md`

This document is the mechanism-by-mechanism breakdown of *how* governance and quality detection are actually done on Amazon Bedrock. Every capability below was verified against official AWS / Anthropic / RAGAS documentation (2025–2026); source links are inline. Where a capability is a customer-built pattern rather than a managed feature, it is flagged.

> Core premise (PRD §8): in regulated banking the failure mode is **silent quality degradation, not downtime.** These controls exist to make that failure mode visible, measurable, and controlled.

---

## 1. Pre-deployment: governance & evaluation

### 1.1 Bedrock RAG / Knowledge Base Evaluation (LLM-as-a-judge) — GA
AWS-native batch evaluation that runs an LLM judge over the RAG system. **GA since 2025-03-20.** Can evaluate a Bedrock Knowledge Base directly *or* bring-your-own responses from any RAG system.
- **Retrieval metrics:** context relevance; context coverage (needs ground truth).
- **Retrieve-and-generate metrics:** correctness, completeness, helpfulness, logical coherence, **faithfulness (hallucination vs. retrieved chunks)**, **citation precision**, **citation coverage**, plus responsible-AI metrics: **harmfulness, stereotyping, refusal.**
- Scores 0–1, averaged across the prompt set, with per-metric report cards. Custom LLM-judge rubrics supported.
- This is the **primary CI-gate engine** once the KB is live (Phase 6).
- Sources: [RAG eval results](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-eval-llm-results.html) · [GA announcement](https://aws.amazon.com/about-aws/whats-new/2025/03/amazon-bedrock-rag-evaluation-generally-available/) · [LLM-as-a-judge blog](https://aws.amazon.com/blogs/aws/new-rag-evaluation-and-llm-as-a-judge-capabilities-in-amazon-bedrock/)

### 1.2 RAGAS (open-source, complementary)
Used for the local Phases 1–2 (before Bedrock is wired) and as a supplementary cross-check. Core metrics confirmed current: **faithfulness, response_relevancy** (renamed from `answer_relevancy`), **context_precision, context_recall**.
- Source: [RAGAS metrics](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/)

### 1.3 Model governance — SageMaker Model Cards
AWS's model-governance tooling lives in **SageMaker**, not Bedrock. Model Cards document intended use, risk rating, and eval results in one auditable artifact; integrate with Model Registry for sign-off workflows. For a Bedrock-hosted Claude (which we don't train) the card documents *our application/system* (intended use, risk tier, eval results, guardrail config), not model weights. There is **no automatic Bedrock→Model Card integration** — it's a documentation practice.
- Sources: [Model Cards](https://docs.aws.amazon.com/sagemaker/latest/dg/model-cards.html) · [ML governance](https://aws.amazon.com/sagemaker/ai/ml-governance/)

### 1.4 Category-specific governance tests (our additions)
Derived from the dataset (PRD §10/§11): refusal precision on out-of-corpus questions (≥0.95), numeric correctness on FinanceBench numeric questions (≥0.90), faithfulness + citation, and answer correctness on in-corpus questions. These are the regulated-finance differentiators on top of generic RAG metrics.

---

## 2. Runtime: Bedrock Guardrails

Guardrails apply to Claude via `InvokeModel`, `Converse`, `InvokeAgent`, `RetrieveAndGenerate`, or the standalone `ApplyGuardrail` API.

| Policy | What it does |
|---|---|
| **Sensitive info (PII)** | ML-based detection of PII incl. `US_BANK_ACCOUNT_NUMBER`, `SWIFT_CODE`, + custom regex. Per-entity **block** or **mask/redact**, input and output. |
| **Denied topics** | Refuse defined topics (e.g. unlicensed investment advice). |
| **Content filters** | Hate, insults, sexual, violence, misconduct, and **prompt attack** (jailbreak/injection) with configurable strength. |
| **Word filters** | Custom blocklists + managed profanity. |
| **Contextual grounding check** | **The core anti-hallucination control.** Takes grounding source + query + response; returns **two 0–1 scores — grounding** (is the answer supported by the source) and **relevance** (does it answer the query). Threshold configurable 0–0.99; below threshold → flagged/blocked as hallucination. AWS's worked example is a banking-fees assistant. Limits: 100k chars source / 1k query / 5k response; supports QA/summarisation/paraphrase, **not** multi-turn chatbot QA. |

- Sources: [Guardrails components](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-components.html) · [Sensitive filters](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-sensitive-filters.html) · [Contextual grounding check](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-contextual-grounding-check.html)

### 2.1 Automated Reasoning checks — GA, with a residency caveat
Uses **formal logic / mathematical proof** (not pattern matching) to validate responses against policies you author from a source document; returns auditable explanations citing the specific rules (VALID / INVALID / TRANSLATION_AMBIGUOUS / TOO_COMPLEX). **GA 2025-08-06.**
- ⚠️ **Detect-mode only** — returns findings, does **not** block; the app decides to serve/rewrite/re-prompt.
- ⚠️ **English (US) only, no streaming**, and **available only in US/EU regions (us-east-1/2, us-west-2, eu-central-1, eu-west-1, eu-west-3) — NOT `ap-southeast-2`.** This conflicts with Sydney data residency → tracked as PRD §14.8 open question. For the demo, rely on the contextual grounding check (Sydney-available).
- Sources: [Automated Reasoning checks](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-automated-reasoning-checks.html) · [GA announcement](https://aws.amazon.com/about-aws/whats-new/2025/08/automated-reasoning-checks-amazon-bedrock-guardrails/)

### 2.2 Guardrail enforcement (governance over the guardrail itself)
IAM condition key **`bedrock:GuardrailIdentifier`** forces a specific guardrail on all Invoke/Converse calls; non-matching requests are rejected. This is how we guarantee **no Claude call escapes the guardrail** — a strong control for audit.
- Source: [IAM policy-based enforcement](https://aws.amazon.com/blogs/machine-learning/amazon-bedrock-guardrails-announces-iam-policy-based-enforcement-to-deliver-safe-ai-interactions/)

### 2.3 Citations
- Bedrock KB `RetrieveAndGenerate` returns a native `citations` array (cited text + typed source location + metadata).
- Self-built path: Anthropic's **native Citations** feature (`"citations": {"enabled": true}`) guarantees cited text points to valid document locations and doesn't count toward output tokens; available via **Bedrock Converse**.
- Sources: [RetrieveAndGenerate](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_RetrieveAndGenerate.html) · [Anthropic Citations](https://docs.anthropic.com/en/docs/build-with-claude/citations)

---

## 3. Online / production detection & monitoring

| Mechanism | What it gives | Source |
|---|---|---|
| **Model invocation logging** | Full request + response bodies, metadata, token counts, caller `identity.arn` → CloudWatch Logs and/or S3. Off by default. The raw audit feed + input for sampled judging. | [docs](https://docs.aws.amazon.com/bedrock/latest/userguide/model-invocation-logging.html) |
| **CloudWatch metrics** | Near-real-time invocation count, tokens, latency, errors; set alarms. | [docs](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/model-invocations.html) |
| **Bedrock Agents traces** | Per-`InvokeAgent` trace: rationale, KB lookup queries, retrieved references, `GuardrailTrace` (shows `GUARDRAIL_INTERVENED` + per-policy assessments), FailureTrace. Audit *which chunks grounded each answer*. | [docs](https://docs.aws.amazon.com/bedrock/latest/userguide/trace-events.html) |
| **AgentCore Observability** | OpenTelemetry spans/metrics/logs (sessions, latency, tokens, errors) → CloudWatch dashboards. For agent fleets on the AgentCore runtime. | [docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability.html) |

### 3.1 Online quality monitoring loop (customer-built)
> ⚠️ This is an **architecture, not a managed toggle.** Bedrock Evaluations is batch/job-oriented; there is no native "online LLM-as-judge on live traffic" switch.

Pattern: enable invocation logging → CloudWatch/S3 → **sample 5%** of logged interactions → score them offline via Bedrock Evaluations (LLM-judge) or `ApplyGuardrail` (contextual grounding) → **write scores back as custom CloudWatch metrics** → dashboards + alarms.
- Source: [Monitoring GenAI with Bedrock + CloudWatch](https://aws.amazon.com/blogs/mt/monitoring-generative-ai-applications-using-amazon-bedrock-and-amazon-cloudwatch-integration/)

**Alerting is quality-first:** a stable-latency / rising-unfaithfulness trend must page before any uptime alarm would (PRD §8.3).

### 3.2 Compliance logging caveats
- Model-invocation logs store the **original, unmasked input** even when Guardrails redacts PII downstream → apply **CloudWatch Logs data protection**.
- Enable **CloudTrail data events** for `InvokeAgent`, `Retrieve`/`RetrieveAndGenerate`, and S3 Vectors ops (`AWS::S3Vectors::*`) — these are not management events by default (extra cost).
- Sources: [model-invocation-logging](https://docs.aws.amazon.com/bedrock/latest/userguide/model-invocation-logging.html) · [Bedrock CloudTrail](https://docs.aws.amazon.com/bedrock/latest/userguide/logging-using-cloudtrail.html)

---

## 4. Platform compliance posture (for the audit pack)

Both the managed and self-built paths inherit the same Bedrock platform controls — the key point for sign-off:
- **Data protection:** Bedrock does not share data with model providers or use it to train FMs; per-Region isolated deployment; KMS, TLS 1.2+, PrivateLink, FIPS endpoints.
- **Compliance programs:** SOC 1/2/3, ISO 27001/27017/27018/27701, **ISO/IEC 42001 (AI management)**, FedRAMP Moderate, HIPAA-eligible, GDPR. FSI-specific guidance via the AWS Well-Architected Financial Services Industry Lens.
- Sources: [security & privacy](https://aws.amazon.com/bedrock/security-privacy-responsible-ai/) · [compliance](https://aws.amazon.com/bedrock/security-compliance/) · [FSI Lens — GenAI security](https://docs.aws.amazon.com/wellarchitected/latest/financial-services-industry-lens/generative-ai-security-and-governance.html)

---

## 5. Mapping to the three disciplines (PRD §8)

| Discipline | Mechanisms here |
|---|---|
| **Model governance** (§8.1) | SageMaker Model Card (system card), risk tiering, validation sign-off gated on §1 eval evidence |
| **Change control** (§8.2) | Eval gate (§1.1/§1.2) in GitHub Actions; version pinning + Bedrock Prompt Management — see `DEVELOPMENT_RULES.md` |
| **Operational monitoring** (§8.3) | §3 — invocation logging, CloudWatch, Agent traces, sampled judge loop; quality-first alerting |

---

## 6. Verified caveats / open items

1. **No native online LLM-as-judge toggle** — the sampling + write-back loop (§3.1) is customer-built.
2. **No direct Bedrock→Model Card integration** — Model Cards are a SageMaker/documentation practice.
3. **Automated Reasoning checks not in `ap-southeast-2`** (US/EU only) — residency decision needed (PRD §14.8).
4. Contextual grounding check's internal scoring algorithm is not publicly disclosed (inputs/thresholds/behaviour are).
5. "Up to 99% verification accuracy" for Automated Reasoning is AWS marketing, not an independent benchmark.
6. Bias/fairness tooling is the SageMaker (Clarify / Model Cards) path; no native Bedrock model-card-with-bias-metrics feature was found.
