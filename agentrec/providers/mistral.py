"""
Mistral chat-completions adapter (``api.mistral.ai/v1/chat/completions``).

Mistral speaks the **same chat-completions dialect as OpenAI** — ``messages``
with ``system``/``user``/``assistant``/``tool`` roles, ``tools`` as
``{"type": "function", "function": {...}}``, assistant ``tool_calls``, SSE
``chat.completion.chunk`` deltas, ``prompt_tokens``/``completion_tokens`` usage
and a native ``response_format: {"type": "json_object"}`` JSON mode.  So this
adapter *is* :class:`~agentrec.providers.openai.OpenAIAdapter`, overriding only
the three places Mistral genuinely differs:

* **tool_choice spelling** — Mistral forces a tool call with ``"any"`` where
  OpenAI says ``"required"`` (both map to the neutral ``"required"``);
* **tool-call ids** — Mistral validates ``tool_call_id`` against
  ``^[a-zA-Z0-9]{9}$``, so an id carried over from another provider (Anthropic
  ``toolu_…``, OpenAI ``call_…``) or synthesized for a hand-built conversation
  is remapped to a stable 9-character form;
* **no o-series quirk** — every Mistral model takes ``max_tokens`` and sampling
  params (Magistral, Mistral's reasoning model, included), so OpenAI's
  ``max_completion_tokens`` special-case never applies.

Decoding, usage normalisation and conversation extraction are inherited
unchanged: a Mistral response is an OpenAI ``choices[0].message`` document (or
SSE delta stream), and ``prompt_tokens``/``completion_tokens`` map onto the
disjoint token buckets via the inherited generic normalisation (Mistral reports
no cache token detail).

The core paths — non-streaming and streaming (SSE) decoding, request building,
usage normalisation and a forced tool call — are **verified against the live
API** by ``tests/test_live_mistral.py`` (run against ``mistral-small-latest``;
skips without a key).  Like Gemini, Mistral's Python SDK does not route through
httpx, so live *recording* is unavailable — seed a corpus by importing Mistral
traffic via ``agentrec import`` and/or use Mistral as a migration *target*.
"""
from __future__ import annotations

import hashlib

from .openai import OpenAIAdapter


class MistralAdapter(OpenAIAdapter):
    name = "mistral"
    host_patterns = ("mistral",)
    # The current naming families: mistral-* (large/medium/small/saba/embed),
    # the open-weight open-mistral-*/open-mixtral-*, codestral-*, ministral-*,
    # pixtral-* (vision), magistral-* (reasoning) and devstral-*.  None of these
    # prefixes overlap the OpenAI/Anthropic/Gemini ones, so routing stays
    # unambiguous regardless of registration order.
    model_patterns = (
        "mistral-",
        "open-mistral-",
        "open-mixtral-",
        "codestral-",
        "ministral-",
        "pixtral-",
        "magistral-",
        "devstral-",
    )
    api_key_env = "MISTRAL_API_KEY"

    chat_url = "https://api.mistral.ai/v1/chat/completions"

    #: Mistral forces a tool call with "any" (OpenAI spells it "required").
    _required_tool_choice = "any"

    def _is_reasoning_model(self, model: str) -> bool:
        # No Mistral model uses the OpenAI o-series wire quirks: all take
        # max_tokens and temperature (Magistral reasons but bills the same way).
        return False

    def _wire_call_id(self, call_id: str) -> str:
        # Mistral rejects a tool_call_id that is not exactly 9 alphanumerics, so
        # remap any neutral id (a recorded cross-provider id, or our synthesized
        # "call_N") to a stable 9-char form.  Hashing is a pure function of the
        # input, so an assistant call and its matching tool result still agree.
        if len(call_id) == 9 and call_id.isascii() and call_id.isalnum():
            return call_id  # already valid (e.g. a Mistral-recorded id) — keep it
        return hashlib.sha1(call_id.encode("utf-8")).hexdigest()[:9]

    def _stream_body_fields(self) -> dict:
        # Mistral already returns a final usage chunk when streaming and rejects
        # OpenAI's stream_options field, so only flip the stream flag.
        return {"stream": True}
