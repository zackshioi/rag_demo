"""Bedrock Agent path (Phase 5) — managed orchestration via InvokeAgent.

The Bedrock Agent runs the retrieve -> reason -> answer loop *server-side*,
replacing the local manual ReAct loop (`tool_agent.py`): the Knowledge Base is
attached as its retrieval source and a Guardrail enforces PII masking + contextual
grounding. We call `InvokeAgent` and parse the streamed completion into the answer
text plus native citations (the KB's source S3 objects, mapped to `[DOC]` ids).

Config via env: `BEDROCK_AGENT_ID`, `BEDROCK_AGENT_ALIAS_ID` (defaults to the
built-in test alias), `AWS_REGION`.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from policy_copilot.tracing import record

AWS_REGION = os.environ.get("AWS_REGION", "ap-southeast-2")
AGENT_ID = os.environ.get("BEDROCK_AGENT_ID", "")
AGENT_ALIAS_ID = os.environ.get("BEDROCK_AGENT_ALIAS_ID", "TSTALIASID")
REFUSAL_TEXT = "NOT FOUND"


@dataclass(frozen=True)
class AgentAnswer:
    """A Bedrock-Agent answer with its native source citations."""

    text: str
    refused: bool
    citations: list[str]  # source doc stems, e.g. ["AMD_2022_10K"]


def answer_bedrock_agent(question: str, session_id: str | None = None) -> AgentAnswer:
    """Ask the managed Bedrock Agent; parse the streamed answer + citations."""
    import boto3

    client: Any = boto3.client("bedrock-agent-runtime", region_name=AWS_REGION)
    response = client.invoke_agent(
        agentId=AGENT_ID,
        agentAliasId=AGENT_ALIAS_ID,
        sessionId=session_id or uuid.uuid4().hex,
        inputText=question,
    )

    parts: list[str] = []
    citations: set[str] = set()
    for event in response["completion"]:
        chunk = event.get("chunk")
        if not chunk:
            continue
        parts.append(chunk["bytes"].decode("utf-8"))
        for citation in (chunk.get("attribution") or {}).get("citations", []):
            for ref in citation.get("retrievedReferences", []):
                uri = ((ref.get("location") or {}).get("s3Location") or {}).get("uri", "")
                if uri:
                    citations.add(PurePosixPath(uri).stem)

    text = "".join(parts).strip()
    # The managed agent may decline out-of-scope questions in its own words
    # (not always the literal "NOT FOUND"); treat an uncited decline as a refusal.
    lowered = text.lower()
    declined = (
        text.upper().startswith(REFUSAL_TEXT)
        or "can only answer" in lowered
        or "do not have" in lowered
        or "don't have" in lowered
    )
    refused = declined and not citations
    result = AgentAnswer(text=text, refused=refused, citations=sorted(citations))
    record(
        {
            "mode": "bedrock_agent",
            "question": question,
            "agent_id": AGENT_ID,
            "refused": result.refused,
            "answer": result.text,
            "citations": result.citations,
        }
    )
    return result


def main() -> None:
    """Demo: one in-corpus question (cited) and one out-of-corpus (refused).

    Requires BEDROCK_AGENT_ID (+ AWS creds). The managed agent runs the
    retrieve->reason->answer loop server-side, with the KB + guardrail attached.
    """
    for question in [
        "What was AMD's total net revenue in fiscal 2022?",
        "What is the capital of France?",
    ]:
        result = answer_bedrock_agent(question)
        print(f"Q: {question}")
        print(f"  refused  : {result.refused}")
        print(f"  citations: {result.citations}")
        print(f"  answer   : {result.text[:300]}")
        print()


if __name__ == "__main__":
    main()
