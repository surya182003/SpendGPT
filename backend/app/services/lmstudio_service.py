"""Client for a local LM Studio server (OpenAI-compatible API).

LM Studio serves http://localhost:1234/v1 by default:
    GET  /v1/models            -> models LM Studio can serve
    POST /v1/chat/completions  -> chat completion

Only the FastAPI backend talks to LM Studio. The React app calls SpendGPT's own
/api/ai/* endpoints, so keep "Enable CORS" OFF in LM Studio's server settings.

Both sync (`chat`, `chat_json`) and async (`achat`, `achat_json`) methods exist.
Async endpoints use the async ones so a slow generation does not block a worker
thread. Every caller must handle LMStudioError: SpendGPT keeps working (with
template-based fallbacks) when LM Studio is not running.
"""
import json
import logging
import re
from functools import lru_cache

import httpx

from app.config import (
    LM_STUDIO_API_KEY,
    LM_STUDIO_BASE_URL,
    LM_STUDIO_CONNECT_TIMEOUT,
    LM_STUDIO_ENABLED,
    LM_STUDIO_MODEL,
    LM_STUDIO_TIMEOUT,
)

logger = logging.getLogger(__name__)

# Reasoning models (Qwen3, DeepSeek-R1, ...) may prepend their chain of thought.
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


# -- errors -------------------------------------------------------------------------
class LMStudioError(RuntimeError):
    """Base class: LM Studio is disabled, unreachable, or gave an unusable answer."""

    reason = "error"


class LMStudioDisabledError(LMStudioError):
    reason = "disabled"


class LMStudioConnectionError(LMStudioError):
    """Server not running, wrong URL, or connection refused."""

    reason = "connection"


class LMStudioTimeoutError(LMStudioError):
    """Connected, but no complete answer within the timeout."""

    reason = "timeout"


class LMStudioModelError(LMStudioError):
    """No chat model loaded, or the configured LM_STUDIO_MODEL is not available."""

    reason = "model_unavailable"


class LMStudioResponseError(LMStudioError):
    """HTTP error status, malformed body, empty or invalid output."""

    reason = "invalid_response"


def _error_text(response: httpx.Response) -> str | None:
    try:
        error = response.json().get("error")
    except (ValueError, AttributeError):
        return None
    if isinstance(error, dict):
        error = error.get("message")
    return str(error) if error else None


# -- client -------------------------------------------------------------------------
class LMStudioClient:
    def __init__(
        self,
        base_url: str = LM_STUDIO_BASE_URL,
        model: str = LM_STUDIO_MODEL,
        timeout: float = LM_STUDIO_TIMEOUT,
        enabled: bool = LM_STUDIO_ENABLED,
        api_key: str = LM_STUDIO_API_KEY,
        connect_timeout: float = LM_STUDIO_CONNECT_TIMEOUT,
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.enabled = enabled
        self._timeout = httpx.Timeout(timeout, connect=connect_timeout)
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._transport = transport  # injected by tests

    def __repr__(self) -> str:  # never include the API key
        return f"LMStudioClient(base_url={self.base_url!r}, model={self.model!r}, enabled={self.enabled})"

    # -- shared request/response handling -------------------------------------------
    def _check_enabled(self) -> None:
        if not self.enabled:
            raise LMStudioDisabledError("LM Studio integration is disabled (LM_STUDIO_ENABLED=false).")

    def _sync_client(self) -> httpx.Client:
        return httpx.Client(timeout=self._timeout, headers=self._headers, transport=self._transport)

    def _async_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self._timeout, headers=self._headers, transport=self._transport)

    def _translate(self, exc: httpx.HTTPError) -> LMStudioError:
        logger.warning("LM Studio request to %s failed: %s", self.base_url, type(exc).__name__)
        if isinstance(exc, httpx.TimeoutException):
            return LMStudioTimeoutError("LM Studio did not respond in time.")
        if isinstance(exc, httpx.ConnectError):
            return LMStudioConnectionError(
                f"Cannot connect to LM Studio at {self.base_url}. Is the local server running?"
            )
        return LMStudioResponseError(f"LM Studio request failed: {exc}")

    def _json(self, response: httpx.Response, model: str | None = None) -> dict:
        if response.status_code >= 400:
            detail = _error_text(response)
            message = f"LM Studio returned HTTP {response.status_code}" + (f": {detail}" if detail else "")
            if response.status_code == 404 or (detail and "model" in detail.lower()):
                hint = f" (requested model: {model!r})" if model else ""
                raise LMStudioModelError(message + hint)
            raise LMStudioResponseError(message)
        try:
            data = response.json()
        except ValueError as exc:
            raise LMStudioResponseError("LM Studio returned a non-JSON response.") from exc
        if not isinstance(data, dict):
            raise LMStudioResponseError("LM Studio returned an unexpected response.")
        return data

    @staticmethod
    def _model_ids(data: dict) -> list[str]:
        models = data.get("data")
        if not isinstance(models, list):
            raise LMStudioResponseError("LM Studio /models response has no 'data' list.")
        return [m.get("id", "") for m in models if isinstance(m, dict) and m.get("id")]

    @staticmethod
    def _pick_model(models: list[str]) -> str:
        """Fallback when LM Studio's own model list is unavailable: first non-embedding id."""
        chat_models = [m for m in models if "embed" not in m.lower()]
        if not chat_models:
            raise LMStudioModelError(
                "No chat model is available in LM Studio. Download one and load it (see docs/AI_ENGINEERING.md)."
            )
        return chat_models[0]

    def _native_models_url(self) -> str | None:
        """LM Studio's own REST list (/api/v0/models), which says each model's type and state."""
        return self.base_url[: -len("/v1")] + "/api/v0/models" if self.base_url.endswith("/v1") else None

    @staticmethod
    def _pick_native(data) -> str | None:
        """Best chat model from /api/v0/models: loaded first, then the largest context window.

        The OpenAI-style /v1/models list can't tell models apart. LM Studio may list small
        helper models (e.g. a 40M-parameter "phonon" model with a 2k context) before the
        real chat model, and with just-in-time loading it lists every downloaded model.
        """
        models = data.get("data") if isinstance(data, dict) else None
        if not isinstance(models, list):
            return None
        chat = [m for m in models if isinstance(m, dict) and m.get("id") and m.get("type") in ("llm", "vlm")]
        if not chat:
            return None
        best = max(chat, key=lambda m: (m.get("state") == "loaded",
                                        m.get("loaded_context_length") or m.get("max_context_length") or 0))
        return best["id"]

    def _native_pick_sync(self) -> str | None:
        url = self._native_models_url()
        if not url:
            return None
        try:
            with self._sync_client() as http:
                response = http.get(url)
            return self._pick_native(response.json()) if response.status_code < 400 else None
        except (httpx.HTTPError, ValueError):
            return None

    async def _native_pick_async(self) -> str | None:
        url = self._native_models_url()
        if not url:
            return None
        try:
            async with self._async_client() as http:
                response = await http.get(url)
            return self._pick_native(response.json()) if response.status_code < 400 else None
        except (httpx.HTTPError, ValueError):
            return None

    def resolve_model(self) -> str:
        """The model chat requests will use: LM_STUDIO_MODEL, else the best loaded chat model."""
        self._check_enabled()
        return self.model or self._native_pick_sync() or self._pick_model(self.list_models())

    async def aresolve_model(self) -> str:
        self._check_enabled()
        return self.model or await self._native_pick_async() or self._pick_model(await self.alist_models())

    @staticmethod
    def _payload(model, messages, temperature, max_tokens, response_format) -> dict:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if response_format:
            payload["response_format"] = response_format
        return payload

    @staticmethod
    def _content(data: dict) -> str:
        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LMStudioResponseError("LM Studio response has no message content.") from exc
        content = _THINK_RE.sub("", str(content)).strip()
        if not content:
            raise LMStudioResponseError("LM Studio returned an empty answer.")
        return content

    @staticmethod
    def _json_format(schema: dict, name: str) -> dict:
        return {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}}

    @staticmethod
    def _parse_json(text: str) -> dict:
        try:
            data = json.loads(_FENCE_RE.sub("", text.strip()))
        except ValueError as exc:
            raise LMStudioResponseError("LM Studio did not return valid JSON.") from exc
        if not isinstance(data, dict):
            raise LMStudioResponseError("LM Studio returned JSON that is not an object.")
        return data

    @staticmethod
    def _status(models: list[str], configured: str, error: LMStudioError | None,
                active: str | None = None) -> dict:
        reason = error.reason if error else None
        if not error and configured and configured not in models:
            # With JIT loading LM Studio may still load it on demand, so report, don't fail.
            reason = "model_unavailable"
        elif not error and not any("embed" not in m.lower() for m in models):
            reason = "model_unavailable"
        return {
            "available": error is None and reason is None,
            "reason": reason,
            "models": models,
            "configured_model": configured or None,
            "active_model": active if error is None and reason is None else None,
        }

    # -- sync API -------------------------------------------------------------------
    def list_models(self) -> list[str]:
        self._check_enabled()
        try:
            with self._sync_client() as http:
                return self._model_ids(self._json(http.get(f"{self.base_url}/models")))
        except httpx.HTTPError as exc:
            raise self._translate(exc) from exc

    def is_available(self) -> bool:
        try:
            return bool(self.list_models())
        except LMStudioError:
            return False

    def status(self) -> dict:
        try:
            models = self.list_models()
        except LMStudioError as exc:
            return self._status([], self.model, exc)
        try:
            active = self.resolve_model()
        except LMStudioError:
            active = None
        return self._status(models, self.model, None, active)

    def chat(self, messages: list[dict], temperature: float = 0.3, max_tokens: int = 600,
             response_format: dict | None = None) -> str:
        self._check_enabled()
        model = self.resolve_model()
        payload = self._payload(model, messages, temperature, max_tokens, response_format)
        try:
            with self._sync_client() as http:
                data = self._json(http.post(f"{self.base_url}/chat/completions", json=payload), model)
        except httpx.HTTPError as exc:
            raise self._translate(exc) from exc
        return self._content(data)

    def chat_json(self, messages: list[dict], schema: dict, name: str = "result", **kwargs) -> dict:
        """Ask for a JSON object matching `schema` (LM Studio structured output)."""
        text = self.chat(messages, temperature=0, response_format=self._json_format(schema, name), **kwargs)
        return self._parse_json(text)

    # -- async API ------------------------------------------------------------------
    async def alist_models(self) -> list[str]:
        self._check_enabled()
        try:
            async with self._async_client() as http:
                return self._model_ids(self._json(await http.get(f"{self.base_url}/models")))
        except httpx.HTTPError as exc:
            raise self._translate(exc) from exc

    async def ais_available(self) -> bool:
        try:
            return bool(await self.alist_models())
        except LMStudioError:
            return False

    async def astatus(self) -> dict:
        try:
            models = await self.alist_models()
        except LMStudioError as exc:
            return self._status([], self.model, exc)
        try:
            active = await self.aresolve_model()
        except LMStudioError:
            active = None
        return self._status(models, self.model, None, active)

    async def achat(self, messages: list[dict], temperature: float = 0.3, max_tokens: int = 600,
                    response_format: dict | None = None) -> str:
        self._check_enabled()
        model = await self.aresolve_model()
        payload = self._payload(model, messages, temperature, max_tokens, response_format)
        try:
            async with self._async_client() as http:
                data = self._json(await http.post(f"{self.base_url}/chat/completions", json=payload), model)
        except httpx.HTTPError as exc:
            raise self._translate(exc) from exc
        return self._content(data)

    async def achat_json(self, messages: list[dict], schema: dict, name: str = "result", **kwargs) -> dict:
        text = await self.achat(messages, temperature=0, response_format=self._json_format(schema, name), **kwargs)
        return self._parse_json(text)


@lru_cache
def get_lmstudio_client() -> LMStudioClient:
    """FastAPI dependency (one shared client); tests override it."""
    return LMStudioClient()
