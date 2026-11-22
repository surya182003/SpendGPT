"""Manual integration tests against a REAL LM Studio server.

These send real prompts to the model loaded in LM Studio, so they are excluded
from the normal test run (pytest.ini adds -m "not lmstudio") and are skipped
automatically when the server cannot be reached.

    cd backend
    pytest -m lmstudio -v -s
    # another machine / port:
    LM_STUDIO_BASE_URL=http://192.168.1.20:1234/v1 pytest -m lmstudio -v -s
"""
import os

import pytest

from app.services.lmstudio_service import LMStudioClient

pytestmark = pytest.mark.lmstudio

# Reads LM_STUDIO_BASE_URL / LM_STUDIO_MODEL / LM_STUDIO_API_KEY from the environment.
# enabled=True because conftest disables LM Studio for the regular tests.
live_client = LMStudioClient(enabled=True) if os.getenv("LM_STUDIO_LIVE", "1") != "0" else None

requires_lmstudio = pytest.mark.skipif(
    live_client is None or not live_client.is_available(),
    reason="LM Studio server not reachable (start it and load a model - see docs/AI_ENGINEERING.md)",
)

PROMPT = [
    {"role": "system", "content": "You are a test assistant. Answer in one short sentence."},
    {"role": "user", "content": "Reply with the word OK and nothing else."},
]


@requires_lmstudio
def test_status_and_loaded_models():
    status = live_client.status()
    print("\nLM Studio status:", status)
    assert status["models"]


@requires_lmstudio
def test_sync_prompt_gets_a_response():
    # Generous max_tokens: reasoning models spend tokens "thinking" first.
    reply = live_client.chat(PROMPT, temperature=0, max_tokens=300)
    print("\nLM Studio replied:", repr(reply))
    assert isinstance(reply, str) and reply.strip()


@requires_lmstudio
@pytest.mark.anyio
async def test_async_prompt_gets_a_response():
    reply = await live_client.achat(PROMPT, temperature=0, max_tokens=300)
    print("\nLM Studio replied (async):", repr(reply))
    assert reply.strip()


@requires_lmstudio
def test_structured_json_output():
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string", "enum": ["yes", "no"]}},
        "required": ["answer"],
        "additionalProperties": False,
    }
    data = live_client.chat_json(
        [{"role": "user", "content": "Is Tesco a supermarket? Answer yes or no as JSON."}], schema, max_tokens=300
    )
    print("\nLM Studio JSON:", data)
    assert data.get("answer") in ("yes", "no")
