"""LLM backend selection — Anthropic API (default) or AWS Bedrock (Phase 3).

The messages loop is identical either way; only the *client* and the *model id*
differ. Switch with `LLM_BACKEND=bedrock`.

On Bedrock we run in `ap-southeast-2` (Sydney) via the **AU inference profile**
`au.anthropic.claude-sonnet-4-6`, which routes only within Australian Regions
(ap-southeast-2 / ap-southeast-4) — i.e. data stays in-country, the data-residency
story for a regulated AU bank. Auth comes from the standard AWS credential chain
(`aws configure`); no Anthropic API key is needed in this mode.
"""

from __future__ import annotations

import os
from typing import Any

import anthropic

BACKEND = os.environ.get("LLM_BACKEND", "api")
AWS_REGION = os.environ.get("AWS_REGION", "ap-southeast-2")

if BACKEND == "bedrock":
    MODEL = os.environ.get("BEDROCK_MODEL", "au.anthropic.claude-sonnet-4-6")
else:
    MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")


def make_client() -> Any:
    """Return the Anthropic client for the configured backend (same messages API)."""
    if BACKEND == "bedrock":
        return anthropic.AnthropicBedrock(aws_region=AWS_REGION)
    return anthropic.Anthropic()
