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
pip install -r requirements.txt   # from the repo root; includes the test tools
pytest                      # automated tests: mocked LM Studio (httpx.MockTransport), no server needed
pytest -m lmstudio -v -s    # manual integration test against a real, running LM Studio
```

The live tests skip themselves when the server is unreachable.

---

## 2. Transaction categorisation

`backend/app/services/categorization_service.py`

### 2.1 Design

Predictions always map onto rows of the existing `categories` table. The model predicts a
category **name**, which is resolved to the live `category_id` with a lookup on
`categories.category_name`. If a predicted name does not exist in the database, no id is
invented and the result falls back to the default. There is no text category column.

Tiers, tried in order. The first confident answer wins:

| # | Source    | How | Confidence |
|---|-----------|-----|------------|
| 1 | `history` | The same user's earlier transactions from the same (normalised) merchant, by majority vote. Scoped to that user. | 0.9 × vote share |
| 2 | `rule`    | Whole-word keyword rules for Irish merchants (`MERCHANT_RULES`). The longest keyword wins, so "Tesco Mobile" beats "Tesco". | 0.95 |
| 3 | `ml`      | Character n-gram (2–5) TF-IDF + logistic regression (`tfidf-char-logreg-v1`), trained on the seed transactions and receipt items. Used only when probability ≥ 0.6. | model probability |
| 4 | `llm`     | LM Studio with a JSON schema that restricts the answer to the category names in the database. Off-list answers are rejected. | 0.7 |
| 5 | `default` | "Other", confidence 0. Automatic save paths leave `category_id` NULL in this case. | 0 |

The LLM is **not** used for routine categorisation. Rules and ML handle known merchants in
microseconds. The LLM tier is only used by `POST /api/ai/categorize` when `use_llm=true`, so
saving a transaction never waits on a model.

The service also handles messy input:

* Missing merchant or description: an empty value or the receipt placeholder "Unknown" counts as missing.
* Unknown merchants: low ML probability falls through to the LLM tier or the default. The service never guesses.
* Receipts (`categorize_receipt`): the merchant is tried first. If it is unknown, the receipt items vote,
  weighted by line total, using item rules and then ML.
* OCR noise: `normalize_text` strips accents and punctuation. `model_text` also strips store numbers and
  generic tokens ("stores", "ltd", "ie", city names) before the ML step.

### 2.2 Training data and future improvements

* The model trains lazily on the team's seed data (`database/transactions.csv` and
  `categories.csv`, plus `receipt_items.csv` item names labelled with their transaction's category).
  That is 1,021 transactions over 9 categories and 30 distinct merchants.
* `retrain_from_database(db)` retrains on the seed data plus every labelled transaction in the
  database, as data accumulates. The model is versioned through `MODEL_VERSION`, and
  `CategoryModel.build_pipeline()` is the single place to swap in a different estimator.

### 2.3 Evaluation

Run `python -m app.services.categorization_eval` from `backend/`. Results on the seed dataset:

| Experiment | Accuracy | Macro-F1 |
|------------|---------:|---------:|
| Majority-class baseline | 0.310 | 0.053 |
| ML only, stratified 5-fold (merchants seen in training) | 1.000 | 1.000 |
| ML only, leave-merchant-out GroupKFold (**unseen merchants**) | 0.229 | 0.098 |
| Rules only, clean seed merchants (coverage 100%)* | 1.000 | 1.000 |
| Hybrid rules → ML, OCR-style noisy names (stripped suffixes) | 1.000 | 1.000 |
| Hybrid rules → ML, OCR-style noisy names (**unstripped suffixes**) | 0.986 | 0.896 |

\* Optimistic, because the rule list was written to include the seed merchants.

How to read these results:

* The seed data has only 30 merchants, so random splits measure memorisation (1.0).
  The leave-merchant-out score (0.229) is the honest number for new brands. Character n-grams
  cannot infer that an unseen brand name is a café. This is why the rule list and the
  optional LLM tier exist.
* The first noisy-variant run (before `model_text`) found a spurious feature: " STORES" pushed
  predictions towards Groceries because of "Dunnes Stores", and the hybrid abstained or erred
  on 9 of 1,021. Stripping generic store tokens fixed this and raised unseen-merchant
  accuracy from 0.185 to 0.229.
* On noisy names with suffixes that preprocessing does not strip, the hybrid abstains to
  "Other" (14 cases) rather than guessing. The lower macro-F1 reflects those abstentions.

`tests/test_categorization.py` checks the category_id mapping, unknown and missing input, user
scoping of history, the LLM tier (mocked), receipts, and a regression guard on these metrics.

---

## 3. Unusual-spending detection and alerts

`backend/app/services/anomaly_service.py`, `backend/app/models/alert.py`

### 3.1 Method

Student histories are small, so the detector uses robust statistics instead of a model that
needs a lot of training data. Every flag has a `message` and a plain-language `explanation`.
Flags never call spending fraud. They say a payment is unusual for this user, and suggest
checking a bank statement if it isn't recognised.

| Flag | Rule | Alert type stored |
|------|------|-------------------|
| `amount_outlier` | Robust z-score `0.6745·(x − median)/MAD` > 3.5 (Iglewicz & Hoaglin) against the user's **earlier transactions in the same category**, and at least €15 above the typical amount. Constant bills (MAD = 0) only count when the amount doubles. | `large_transaction` |
| `possible_duplicate` | Same merchant and amount on the same or next day. Skipped for `is_recurring` transactions and for habitual same-price purchases (3 or more earlier identical amounts, e.g. a daily coffee). | `possible_duplicate` |
| `category_spike` | This month's category spend is at least 1.5× its average over the previous 1–3 months and at least €30 above it. Needs 2 or more earlier months. | `spending_spike` |

**Insufficient history.** A category is judged only after 5 earlier transactions in it. Categories
below that are listed in the report's `notes` rather than compared with other categories. An
earlier version fell back to "all spending", and the evaluation showed that this flagged every
early rent payment as "30× your typical spending", so the fallback was removed. The report's
`history_status` is `insufficient`, `limited` or `ok`.

### 3.2 Alerts

Flags are stored in the **existing `alerts` table**. `Alert` mirrors `database/SpendGPT.sql`
column for column, and no schema change was made. `store_alerts()` avoids duplicates on
re-analysis: transaction flags are keyed on (user, alert_type, related_transaction_id), and
spikes on (user, type, category and month). No `is_anomaly` or `anomaly_reason` columns are
added to `transactions`.

### 3.3 Evaluation

Run `python -m app.services.anomaly_eval` from `backend/`. It uses the 1,021 seed transactions
across 5 users:

* **Clean data:** 21 transactions (2.1%) flagged as unusually large, e.g. concert tickets in an
  Entertainment history of cinema and pub visits.
* **Injected over-spends:** 6 non-recurring transactions per user (30 total) set to *factor ×* that
  user's median in the category:

  | Factor | Precision | Recall | F1 |
  |-------:|----------:|-------:|---:|
  | 1.5× | — | 0.000 | — |
  | 2× | 1.000 | 0.067 | 0.125 |
  | 3× | 1.000 | 0.600 | 0.750 |
  | 4× | 1.000 | 0.933 | 0.966 |
  | 6× | 1.000 | 0.967 | 0.983 |

  1.5× is deliberately *not* flagged, because it is within normal variation (for example, weekly
  shops vary a lot). Injection is relative to the median, not the original amount, because
  tripling a small €14 top-up gives a normal €43 grocery bill.
* **Seeded alerts:** only 1 of the 12 `large_transaction` alerts in `database/alerts.csv` is also
  flagged. Those seeded alerts appear to use a fixed amount threshold (e.g. "€57.37 at Amazon.ie"),
  while this detector is relative to the user's own history.

---

## 4. Financial insights and AI advisor

`backend/app/services/insights_service.py`

### 4.1 Design

Python calculates every figure from the user's own rows in the existing `users`, `transactions`,
`categories` and `budgets` tables. LM Studio only puts those figures into words. No tables or
columns were added.

| Insight | How it is calculated |
|---------|----------------------|
| Income | `users.monthly_income` × months covered, with the current month pro-rated. Transactions are all spending, so this is the only income source in the schema. If income is not set, income, net and savings rate are `None` and a note says so. |
| Spending | Sum of the user's transactions in the period. Transactions dated after today are ignored. |
| By category | Total, share, transaction count, monthly average and recurring share per category. Transactions without a category are grouped as "Uncategorised". The essential/discretionary split comes from `categories.spend_type`. |
| Highest categories | The top 3 categories by total. |
| Monthly pattern | Every calendar month in the period, including months with no spending. Also: the average over complete months, the highest and lowest month, the trend (the last complete month vs. the earlier ones, ±10%), and the projected total for the current month. |
| Budgets | Each budget overlapping the period, compared with the spending in its own dates and category (a NULL category means all spending). Status is `over`, `at_risk` (≥ 80% used, or projected to go over at the current pace) or `on_track`. |
| Savings opportunities | Over-budget categories; non-essential categories averaging at least €25 a month (a suggested 20% cut); frequent small purchases (6 or more of €12 or less at one merchant); recurring non-essential payments. |
| Recommendations | Rule-based and prioritised (`high`, `medium`, `low`) from the figures above. |

The period defaults to 6 months (at most 24). It starts at the month of the user's first
transaction if that is later, so a new user's income isn't counted for months with no data.
`history_status` is `empty`, `limited` (fewer than 10 transactions or under 2 months) or `ok`.

### 4.2 LM Studio explanations and the advisor

* `explain_insights` / `aexplain_insights` write a short plain-language summary of the report.
* `ask_advisor` / `aask_advisor` answer the student's question using the report's figures.
  Earlier chat turns can be passed in; only the last 6 `user`/`assistant` turns are sent, and any
  other roles are dropped. Questions must be 1–500 characters.
* Only aggregates go to the model (`llm_facts`): no names, emails, merchants or individual
  transactions.
* **Figure check.** The model is told to use only the given figures. `unsupported_figures` also
  checks every amount and percentage in the reply against the report (a 1% or ±1 rounding
  difference is allowed). A reply with an invented figure is replaced by the template text, with
  reason `unverified_figures`.
* **Fallback.** If LM Studio is disabled, offline or returns an error, a template summary built
  from the same figures is returned. The result is an `AIText` with `source` set to `llm` or
  `fallback`, and a `reason`.

### 4.3 Tests

`tests/test_insights.py` covers:

* the totals, category, monthly and budget calculations;
* user isolation and missing data (no transactions, no income, no category, future dates);
* savings opportunities and recommendations;
* a cross-check against the seed transactions;
* the LLM paths: the prompt contents, no personal data in the prompt, the offline fallback,
  rejected invented figures, and the advisor's chat history.

---

## 5. AI API (FastAPI)

The AI endpoints are on the existing `/api/ai` router (`backend/app/controllers/ai_controller.py`), next
to the existing receipt endpoints. Their schemas are in `backend/app/schemas/ai_schema.py`. They identify
the user by `user_id`, like the rest of the API, and IDs are limited to `1..2147483647`. The React app
calls only these endpoints and never LM Studio. In tests, LM Studio is replaced through
`app.dependency_overrides[get_lmstudio_client]`.

| Method & path | Purpose |
|---------------|---------|
| `GET /api/ai/status` | Whether LM Studio is reachable (`available`, `reason`, `models`). |
| `POST /api/ai/categorize` | Suggests a category for `merchant_name`/`description`. Nothing is saved. Optional `user_id` (uses that user's history first) and `use_llm` (LM Studio for unknown merchants). |
| `POST /api/ai/users/{user_id}/anomalies/scan?lookback_days=90` | Checks recent transactions and stores new flags as alerts, without duplicates. Returns the flags and `alerts_created`. |
| `GET /api/ai/users/{user_id}/alerts?unread_only=false&limit=50` | The user's alerts, newest first. |
| `PATCH /api/ai/users/{user_id}/alerts/{alert_id}/read` | Marks one of the user's alerts as read. |
| `GET /api/ai/users/{user_id}/insights?months=6&explain=true` | The insights report (section 4). With `explain=true` it also includes `explanation` (`text`, `source`, `reason`). |
| `POST /api/ai/users/{user_id}/chat` | Advisor. Body: `{"question": "...", "history": [{"role": "user"/"assistant", "content": "..."}], "months": 6}`. Returns `{answer, source, reason}`. |

**Existing endpoints.** Request and response shapes are unchanged:

* `POST /api/transactions/`: if no `category_id` is sent, the transaction is categorised from history,
  rules or the ML model. The LLM is never used here, so saving never waits on a model, and unknown
  merchants stay `NULL`.
* `POST /api/receipts/upload`: categorised the same way, using `categorize_receipt`, which falls back
  to the receipt's items when the merchant is unknown.
* After either save, the new transaction is checked for unusual spending and any flags are stored in
  `alerts`.
* `PUT /api/transactions/{id}` doesn't recategorise, because the user's choice wins.

Both automatic steps are in `app/services/ai_pipeline.py`. If one fails, it is logged and the save still
succeeds.

**Errors.**

* 404: unknown user, or an alert belonging to someone else.
* 422: invalid input, such as an empty or over-long question, an unknown chat role, more than 20 history
  turns, `months` outside 1–24, or an out-of-range ID.
* If LM Studio is down, the endpoints still return 200, with `source: "fallback"` and the reason.

No tables or columns were added, and the queries are standard SQL that works on MySQL and TiDB.
`tests/test_ai_api.py` tests every endpoint, the save-path integration and route conflicts. The
endpoints are also covered by `pytest -m fuzz`.
