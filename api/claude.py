"""Calls to Claude (Anthropic API) that return JSON matching a schema
(structured outputs), through the official SDK.

Every caller has a way to work without Claude: ClaudeUnavailable is raised
when the key is missing, the API fails, or the answer cannot be used, and
the caller falls back (rule-based text, error message) instead of breaking.
Nothing here logs the content sent to Claude nor the key.
"""
import json
import logging
import os
from typing import Any, Dict, List, Union

import anthropic

logger = logging.getLogger(__name__)

# Reading long documents and judging: the most capable Opus
MODEL = "claude-opus-5-5"
# Re-runs a request declined by a safety classifier on Anthropic's recommended model
FALLBACK_BETA = "server-side-fallback-2026-07-01"


# Tests only: an httpx2 transport answering in place of the API
TRANSPORT = None


class ClaudeUnavailable(Exception):
    pass


def configured() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())


async def json_call(system: str, content: Union[str, List[Dict[str, Any]]], schema: Dict[str, Any], *,
                    model: str = MODEL, effort: str = "medium", max_tokens: int = 16000,
                    timeout: float = 240) -> Dict[str, Any]:
    """One request, the answer parsed as JSON. Streamed, so that a long
    answer on long documents is not cut by the HTTP timeout."""
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise ClaudeUnavailable("ANTHROPIC_API_KEY not set")
    client = anthropic.AsyncAnthropic(
        api_key=key, timeout=timeout, max_retries=1,
        **({"http_client": anthropic.DefaultAsyncHttpxClient(transport=TRANSPORT)} if TRANSPORT else {}))
    try:
        async with client.beta.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": content}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        ) as stream:
            message = await stream.get_final_message()
    except anthropic.RateLimitError:
        logger.error("Anthropic API: rate limited")
        raise ClaudeUnavailable("rate limited")
    except anthropic.APIStatusError as e:
        logger.error(f"Anthropic API error {e.status_code}: {str(e.message)[:300]}")
        # The message says what was refused (never the content sent)
        raise ClaudeUnavailable(f"API error {e.status_code}: {str(e.message)[:300]}")
    except anthropic.APIConnectionError as e:
        logger.error(f"Anthropic API unreachable: {type(e).__name__}")
        raise ClaudeUnavailable("unreachable")
    finally:
        await client.close()

    if message.stop_reason == "refusal":
        logger.error("Anthropic API: request declined")
        raise ClaudeUnavailable("refusal")
    if message.stop_reason == "max_tokens":
        logger.error("Anthropic API: answer cut at max_tokens")
        raise ClaudeUnavailable("truncated")
    text = next((b.text for b in message.content if b.type == "text"), None)
    try:
        data = json.loads(text or "")
    except ValueError:
        logger.error("Anthropic API: answer is not JSON")
        raise ClaudeUnavailable("invalid answer")
    usage = message.usage
    logger.info(f"Claude {message.model}: {usage.input_tokens} tokens in, {usage.output_tokens} out")
    return data


def strict_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Structured outputs want every object closed and fully required, and do
    not take length constraints: a schema written for tools, made fit."""
    out = {k: v for k, v in schema.items() if k not in ("minItems", "maxItems", "minLength", "maxLength")}
    if out.get("type") == "object":
        props = {k: strict_schema(v) for k, v in (out.get("properties") or {}).items()}
        out.update(properties=props, required=list(props), additionalProperties=False)
    if out.get("type") == "array" and isinstance(out.get("items"), dict):
        out["items"] = strict_schema(out["items"])
    return out


def nullable(schema: Dict[str, Any]) -> Dict[str, Any]:
    return {"anyOf": [schema, {"type": "null"}]}
