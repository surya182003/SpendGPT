# SpendGPT — AI Engineering

This document covers SpendGPT's AI features: the local LLM integration (LM Studio),
transaction categorisation, unusual-spending detection, financial insights and the
AI API used by the React app.

All AI runs locally. SpendGPT uses **LM Studio** as its local LLM platform through its
OpenAI-compatible API. No paid or external LLM service is used.

```
React (Vite)  ──HTTP──▶  FastAPI /api/ai/*  ──HTTP──▶  LM Studio (localhost:1234/v1)
                               │
                               ├── categorisation (rules + scikit-learn)
                               ├── anomaly detection (robust statistics)
                               ├── insights (SQL/Python figures, LLM explanation)
                               └── SQLAlchemy ──▶ transactions / categories / budgets / alerts
```

The browser never talks to LM Studio. Every AI request goes through FastAPI, which
scopes data to the requesting user before anything is sent to the model.

---

## 1. LM Studio setup

### 1.1 Install LM Studio and download a model

LM Studio does not ship with a model, so you need to download one first.

1. Install LM Studio from <https://lmstudio.ai> (macOS, Windows or Linux).
2. Open LM Studio → **Discover** (magnifier icon) and search for an instruction-tuned model.
   Recommended options:

   | Machine RAM / VRAM | Model (search term)          | Download size (Q4_K_M) |
   |--------------------|------------------------------|------------------------|
   | 8 GB               | `qwen2.5-3b-instruct`        | ~2 GB                  |
   | 8 GB               | `llama-3.2-3b-instruct`      | ~2 GB                  |
   | 16 GB+             | `qwen2.5-7b-instruct`        | ~4.7 GB                |
   | 16 GB+             | `meta-llama-3.1-8b-instruct` | ~4.9 GB                |

   Choose a **Q4_K_M** quantisation unless you have plenty of memory. Instruct models
   follow the "use only these numbers" rules more reliably than base models.
3. Or use the LM Studio CLI (`lms`, installed with LM Studio):

   ```bash
   lms get qwen2.5-7b-instruct      # download
   lms ls                           # list downloaded models
   lms load qwen2.5-7b-instruct     # load into memory
   ```

### 1.2 Start the local server

* GUI: **Developer** tab → **Start Server** (status should read *Running on port 1234*).
  Load the model from the model picker at the top.
* CLI: `lms server start` (and `lms load <model>` if no model is loaded).

Leave **Enable CORS** switched off. Only the backend should call LM Studio.

Check that it works:

```bash
curl http://localhost:1234/v1/models
# {"data":[{"id":"qwen2.5-7b-instruct", ...}], "object":"list"}
```

### 1.3 Configure the backend

Copy `backend/.env.example` to `backend/.env` (git-ignored) and adjust if needed:

| Variable                    | Default                    | Purpose |
|-----------------------------|----------------------------|---------|
| `LM_STUDIO_ENABLED`         | `true`                     | `false` turns LLM features off (fallback text is used). |
| `LM_STUDIO_BASE_URL`        | `http://localhost:1234/v1` | LM Studio server URL. |
| `LM_STUDIO_MODEL`           | *(empty)*                  | Model id from `/v1/models`. Empty means the first loaded chat model. |
| `LM_STUDIO_API_KEY`         | *(empty)*                  | Only if **Require API token** is enabled in LM Studio. Never commit it. |
| `LM_STUDIO_TIMEOUT`         | `60`                       | Seconds to wait for a full reply. |
| `LM_STUDIO_CONNECT_TIMEOUT` | `5`                        | Seconds to wait for a connection. |

```bash
cd backend
uvicorn app.main:app --reload --env-file .env
```

### 1.4 The LM Studio service (`backend/app/services/lmstudio_service.py`)

`LMStudioClient` wraps the OpenAI-compatible endpoints with `httpx`:

* `list_models()` / `alist_models()`: `GET /v1/models`
* `chat()` / `achat()`: `POST /v1/chat/completions` (sync and async)
* `chat_json()` / `achat_json()`: structured output using a JSON schema (`response_format`)
* `status()` / `astatus()`: availability summary for `GET /api/ai/status`

It also does the following:

* **Errors.** Every failure raises an `LMStudioError` subclass with a machine-readable `reason`:
  `disabled`, `connection` (server not running), `timeout`, `model_unavailable` (no chat
  model loaded, or `LM_STUDIO_MODEL` is not available), `invalid_response` (HTTP error,
  non-JSON body, missing or empty content, invalid JSON output).
* **Response checks.** It strips the `<think>…</think>` blocks that reasoning models
  emit, strips code fences around JSON, and rejects empty answers.
* **Credentials.** None are hardcoded. The API key comes from the environment, is only
  sent when set, and is never included in `repr()`.
* **Graceful degradation.** Callers catch `LMStudioError` and return deterministic,
  data-based fallback text, so SpendGPT keeps working without LM Studio.

### 1.5 Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest                      # automated tests: mocked LM Studio (httpx.MockTransport), no server needed
pytest -m lmstudio -v -s    # manual integration test against a real, running LM Studio
```

The live tests skip themselves when the server is unreachable.
