# Model Card — Policy Copilot

**Status:** v1.0 · **Last verified:** 2026-06-29 · Companion to `ARCHITECTURE.md`, `GOVERNANCE.md`, `EVALUATION.md`

Records the exact model + inference configuration in use, so any evaluation score
or production answer is attributable to a pinned version (a governance requirement
for a regulated bank). Update this card whenever the model, region, or backend
changes — and re-run the golden set against the new pin.

---

## Model

| Field | Value |
|---|---|
| **Model** | Claude Sonnet 4.6 (Anthropic) |
| **Selected via** | `LLM_BACKEND` env var (`llm.py`) — switches backend without code changes |

### Backend A — AWS Bedrock (Phase 3, default for AWS-native demo)

| Field | Value |
|---|---|
| Client | `anthropic.AnthropicBedrock` |
| **Pinned model id** | `au.anthropic.claude-sonnet-4-6` (Bedrock **AU inference profile**) |
| Region | `ap-southeast-2` (Sydney) |
| **Data residency** | AU profile routes **only** within `ap-southeast-2` / `ap-southeast-4` — inference data stays in Australia |
| Auth | AWS credential chain (SigV4); IAM `AmazonBedrockFullAccess` (demo; tighten later) |
| Access prerequisite | Anthropic *use case details* form submitted in the Bedrock console (account `545045833565`) |
| Enable with | `LLM_BACKEND=bedrock` (+ `AWS_REGION`, `BEDROCK_MODEL` overridable) |

### Backend B — Anthropic API (Phase 1–2 default)

| Field | Value |
|---|---|
| Client | `anthropic.Anthropic` |
| Pinned model id | `claude-sonnet-4-6` |
| Auth | `ANTHROPIC_API_KEY` |
| Enable with | `LLM_BACKEND=api` (default) |

---

## Retrieval (Phase 4)

Selected via `RETRIEVAL_BACKEND` (`retrieval.py`):

| Field | Value |
|---|---|
| **FAISS** (default) | local bge-base index over parsed chunks |
| **Bedrock KB** (`RETRIEVAL_BACKEND=kb`) | **MANAGED** KB `knowledge-base-zack-rag-demo`, id **`5EFMZLJGDE`**, `ap-southeast-2` |
| KB embeddings | Titan Text Embeddings V2 (1024-dim) |
| KB source | S3 `zack-rag-demo` (8 parsed `.md`) |
| KB cost | pay-per-use (indexed size + retrievals); **no standing fee** |
| Data residency | KB index + retrieval stay in `ap-southeast-2` |

KB excerpts map to `[DOC::NNNN]` citations (doc = S3 filename stem), so refusal and
the citation verifier are unchanged. KB relevance scores differ in scale from FAISS —
`REFUSAL_THRESHOLD` is FAISS-calibrated; revisit for KB (Phase 6).

---

## Pricing (per 1M tokens)

| | Input | Output |
|---|---|---|
| Claude Sonnet 4.6 (both backends) | $3.00 | $15.00 |

Tracked per answer via `cost_usd` (`agent.py`) and Langfuse. Bedrock on-demand
per-token rates match the Anthropic API; no subscription fee.

---

## Governance behaviour (same on both backends)

- **Grounded + cited** answers only; numbers quoted verbatim from retrieved context.
- **Refusal** when retrieval is weak (cheap pre-check) or the model returns `NOT FOUND`.
- **Deterministic verifier** (`tool_agent.verify`): citations must resolve to a real
  chunk (hard gate → refuse on fabrication) + numbers-verbatim score.
- **Safe degradation**: an API/network failure is caught, returned as `NOT FOUND`,
  and traced with `error=<type>` — never a fabricated answer.
- **Observability**: every answer traced (JSONL + Langfuse) with tokens, cost, error.

---

## Verification (2026-06-29, Bedrock `au.anthropic.claude-sonnet-4-6`)

| Case | Result |
|---|---|
| AMD net revenue 2022 (in corpus) | ✅ "$23.6 billion" `[AMD_2022_10K::0153]` |
| Boeing revenues 2022 (agentic, 1 search) | ✅ cited, `verified=True` |
| Capital of France (out of corpus) | ✅ `NOT FOUND` |

Same answers/citations as the Anthropic API backend — the swap is behaviour-preserving.
