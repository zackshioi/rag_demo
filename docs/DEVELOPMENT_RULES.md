# Policy Copilot — Development Rules (DevOps / MLOps / AIOps)

**Status:** Draft v1.0 · **Date:** 2026-06-26 · **Remote:** GitHub · **CI/CD:** GitHub Actions · Companion to `PRD.md` §8.2 and `PROGRESS.md`

This is the operating manual: how code, prompts, infra, and models move from a laptop to production through gates. Capability claims about AWS tooling were verified against official docs (2025–2026); source links inline. Where a common assumption is wrong, it's flagged with ⚠️.

> The three terms, kept distinct:
> - **DevOps** — ship software & infrastructure reliably.
> - **MLOps / LLMOps (AWS: FMOps)** — manage the prompt/model/eval lifecycle.
> - **AIOps** — operate the AI in production (monitor, detect, respond).

---

## 1. Repository conventions

```
rag_demo/
├── README.md
├── docs/                      # PRD, ARCHITECTURE, GOVERNANCE, this file, PROGRESS
├── src/                       # app: SDK tool-use loop, retrieval, agent client
├── evals/                     # golden dataset + RAGAS / Bedrock-eval harness
├── infra/                     # IaC: CloudFormation / CDK (AWS::Bedrock::*)
├── prompts/                   # versioned prompt + agent-instruction artifacts
└── .github/workflows/         # ci.yml, eval.yml, deploy.yml
```

- **Language:** Python. Match surrounding style; lint with `ruff`, format with `black`, type-check with `mypy` where typed.
- **Secrets:** never commit. Local via `.env` (git-ignored); CI via **GitHub OIDC → short-lived AWS role** (no long-lived access keys).
- **Data:** the dataset is public (FinanceBench, CC-BY-NC — demo only). Treat downloaded PDFs and the derived corpus/index as build artifacts — git-ignore caches under `data/`.

---

## 2. DevOps — git, PR, and Infrastructure-as-Code

### 2.1 Branch & PR rules
- `main` is protected: **no direct pushes**, PR + green checks required, ≥1 review.
- Branch from `main`; conventional, scoped commits.
- Every commit message ends with the project's standard co-author trailer (see repo policy).
- A PR cannot merge unless **CI (`ci.yml`) and the eval gate (`eval.yml`) pass** (§4).

### 2.2 Infrastructure-as-Code (verified)
All core Bedrock primitives are first-class IaC resources — provision everything as code, never click-ops in prod.
- **CloudFormation `AWS::Bedrock::*`:** `Agent`, `AgentAlias`, `KnowledgeBase`, `DataSource`, `Guardrail`, `GuardrailVersion`, `Flow`, `FlowVersion`, `FlowAlias`, `Prompt`, `PromptVersion`, `ApplicationInferenceProfile`, `AutomatedReasoningPolicy`, … — [CFN reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/AWS_Bedrock.html)
- **CDK:** L1 (`CfnAgent`, `CfnKnowledgeBase`) in `aws-cdk-lib.aws_bedrock`; L2 moving to official `@aws-cdk/aws-bedrock-alpha`. ⚠️ The `awslabs/generative-ai-cdk-constructs` L2 Bedrock constructs are **deprecated** — migrate to the alpha package. KB L2 is still being completed (track aws/aws-cdk #36592); for KB-as-code today prefer CFN L1 / Terraform. — [CDK bedrock](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_bedrock-readme.html)
- **Terraform:** `aws_bedrockagent_knowledge_base`, `aws_bedrock_guardrail` (+ `_version`), `aws_bedrockagent_data_source`, etc.; AWS-IA module `aws-ia/bedrock/aws`. — [TF KB](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagent_knowledge_base)
- **Region:** all resources pinned to `ap-southeast-2`.

---

## 3. MLOps / LLMOps — prompt, model, and eval lifecycle

### 3.1 Versioning & pinning (verified)
- **Prompts / agent instructions:** versioned in git (`prompts/`) **and** in **Bedrock Prompt Management** — `CreatePromptVersion` takes an immutable, incrementing snapshot (from v1). ⚠️ No console free-text editing in prod. — [Prompt versions](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-management-version-create.html)
- **Agents:** `DRAFT` → immutable numbered versions; aliases give stable endpoints. — [Agent deploy](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-deploy.html)
- **Flows (if used):** `CreateFlowVersion` + `CreateFlowAlias` (Dev/Staging/Prod). — [Flow deploy](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-deploy.html)
- **Pinned per release:** model ID + version, prompt version, retrieval config, Guardrail version, embedding model. Recorded in the release notes + system model card.

### 3.2 The model card
Maintained as a system card (SageMaker Model Card or a docs artifact): intended use, risk tier, known limits, **latest eval results**, guardrail config, out-of-scope uses, refusal behaviour. Updated on every promotion to prod; reviewed by 2nd-line Model Risk for sign-off (PRD §8.1).

### 3.3 FMOps reference (AWS)
We are the **"Consumer"** persona in AWS's FMOps model (prompt/integrate FMs, don't train) — so our lifecycle emphasis is: prompt version control, retrieval/agent complexity, hallucination/drift risk, and cost governance.
- Sources: [FMOps/LLMOps](https://aws.amazon.com/blogs/machine-learning/fmops-llmops-operationalize-generative-ai-and-differences-with-mlops/) · [Well-Architected GenAI Lens](https://docs.aws.amazon.com/wellarchitected/latest/generative-ai-lens/generative-ai-lens.html)

---

## 4. The eval gate — GitHub Actions (the heart of change control)

> No change reaches production except through code review + a passing eval gate (PRD §8.2).

**`.github/workflows/eval.yml`** (required PR check):
1. Check out PR; set up Python; assume AWS role via OIDC.
2. Run the golden-set eval (FinanceBench: 40 in-corpus + out-of-corpus refusal) (`evals/`):
   - Local phases → **RAGAS** (faithfulness, response_relevancy, context_precision, context_recall).
   - KB live → **Bedrock RAG Evaluation** (LLM-as-judge: faithfulness, citation precision/coverage, refusal) as primary.
   - Category governance tests: refusal precision (out-of-corpus), numeric correctness, faithfulness + citation, answer correctness.
3. **Fail the job (block merge) if any threshold regresses** below PRD §3:
   faithfulness ≥ 0.75 · refusal precision ≥ 0.95 · numeric correctness ≥ 0.90 · context_recall/precision ≥ 0.70.
4. Publish the score report as a PR artifact / comment; attach to the model card on merge.

AWS explicitly recommends integrating evaluation into CI/CD (Well-Architected GenAI Lens, using Bedrock Evaluations or `fmeval`; RAGAS is a valid supplementary third-party engine). — [GenOps eval-in-CI](https://docs.aws.amazon.com/wellarchitected/latest/generative-ai-lens/genops01-bp01.html)

**`ci.yml`** runs lint + unit tests on every PR (fast feedback, separate from the eval gate).

---

## 5. AIOps — rollout, rollback, observability

### 5.1 Rollout & rollback (verified — corrects a common assumption)
- Promotion path: **shadow → canary → full** (PRD §8.2).
- ⚠️ **A single Bedrock Agent/Flow alias points to exactly one version** (`RoutingConfiguration` **max = 1**). Unlike Lambda, an alias **cannot weight-split traffic across versions.** True canary = **two aliases (`prod` + `canary`) + an app-layer traffic split**. — [AgentAlias reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrock-agentalias.html)
- **Rollback** = re-point the alias to the prior immutable version — one step, clean.

### 5.2 Observability (feeds `GOVERNANCE.md` §3)
- `InvokeAgent` with `enableTrace: true` → `TracePart` (rationale, FM prompts, KB queries, guardrail assessments) — the audit trail.
- Model-invocation logging → CloudWatch/S3; CloudWatch metrics + alarms; optional AgentCore OTEL observability for fleets.
- **Online quality loop is customer-built** (sample → judge → write back custom CloudWatch metrics) — see `GOVERNANCE.md` §3.1.

### 5.3 Deploy workflow
**`.github/workflows/deploy.yml`** (on merge to `main`, environment-gated): assume AWS role via OIDC → `cdk deploy` / CFN deploy to the target env → run smoke + a thin eval slice against the deployed alias → on failure, re-point alias to last-known-good.

---

## 6. Tool → discipline mapping

| Layer | Concern | Tooling |
|---|---|---|
| **DevOps / IaC** | provision & ship | GitHub + GitHub Actions; CloudFormation `AWS::Bedrock::*` / CDK / Terraform; GitHub OIDC → AWS |
| **MLOps / LLMOps** | prompt/model/eval lifecycle | Bedrock Prompt Management (versions); Agent/Flow versions + aliases; Bedrock Evaluations / RAGAS eval gate; model card |
| **AIOps / runtime** | rollout, rollback, observe | multi-alias canary + app-layer split; alias re-point rollback; `enableTrace`; invocation logging; CloudWatch; AgentCore observability |

---

## 7. Verified caveats

1. **Alias traffic-splitting:** not supported inside one Bedrock alias — canary needs app-layer routing (§5.1).
2. **KB L2 CDK constructs in transition:** use CFN L1 / Terraform / (deprecated) awslabs for KB-as-code until the alpha package completes KB support.
3. **RAGAS-in-CI** is a community pattern; AWS-endorsed CI engines are **Bedrock Evaluations** and **`fmeval`** — we use Bedrock Eval as primary, RAGAS as supplementary.
4. **OIDC role scoping:** keep the CI deploy role least-privilege and environment-scoped; no wildcard Bedrock/admin grants.
