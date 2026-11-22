# SpendGPT
An AI-powered student finance copilot featuring local ML transaction categorization, anomaly detection, and a local LLM (LM Studio) for conversational money insights. Fully stack-implemented using React, FastAPI, MySQL, and layered architecture.

SpendGPT– AI Student Finance Copilot | React, FastAPI, MySQL, Local LLM (LM Studio)

* Building a full-stack finance copilot with a React frontend and FastAPI backend, using a layered architecture with
  MySQL for persistence.
* Implementing local ML models for automatic transaction categorisation and anomaly detection, paired with a
  local LLM (LM Studio) for conversational money insight

## Requirements

- Python 3.12+
- Node.js 20+ (only for the frontend)

## 1. Install Python dependencies

From the repository root:

```bash
python -m pip install -r requirements.txt
```

`indra-ocr` (the receipt OCR engine) is a large install. You only need it to upload real receipt images.
The backend and all tests work without it. To skip it:

```bash
grep -v indra-ocr requirements.txt > req-no-ocr.txt
python -m pip install -r req-no-ocr.txt
```

On Windows PowerShell, use `Get-Content requirements.txt | Select-String -NotMatch indra-ocr | Set-Content req-no-ocr.txt` for the first line.

## 2. Run the backend (FastAPI)

Run these from the `backend/` folder so Python can import `app`:

```bash
cd backend
python -m app.seed              # optional: creates demo accounts
uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Interactive API docs (try every endpoint in the browser): http://localhost:8000/docs
- Health check: http://localhost:8000/health

`python -m app.seed` creates these demo accounts (for local use only):

| Email | Password |
|---|---|
| demo@example.com | DemoPass123 |
| test@example.com | TestPass123 |

### Database

By default the backend uses a local SQLite file at `backend/spendgpt.db`, created automatically on first start.
To use MySQL/TiDB instead, set `DATABASE_URL` before starting:

```bash
# bash
export DATABASE_URL="mysql+pymysql://user:password@host:port/database"
# PowerShell
$env:DATABASE_URL = "mysql+pymysql://user:password@host:port/database"
```

Other settings:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | SQLite at `backend/spendgpt.db` | Database connection |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:5174` | Frontend URLs allowed to call the API |

The categories table is not seeded by `app.seed`, so `/api/categories/` returns an empty list on a fresh SQLite database.

## 3. Run the frontend (React + Vite)

The frontend is still in progress and doesn't call the backend yet.

```bash
cd frontend
npm install
npm run dev                     # http://localhost:5173
```

## 4. OCR scripts

Run from `database/ocr/`:

```bash
cd database/ocr
python test_reciept.py                      # parser on sample receipt text, no OCR engine needed
python ocr.py test_images/aldi_test.jpeg    # full OCR + save to TiDB
```

`ocr.py` needs `indra-ocr` installed and a `database/.env` file with `TIDB_HOST`, `TIDB_PORT`, `TIDB_USER`,
`TIDB_PASSWORD` and `TIDB_DATABASE`.

## AI features (LM Studio)

The AI features run locally through LM Studio's OpenAI-compatible server
(`http://localhost:1234/v1`). The React app only calls the FastAPI `/api/ai/*`
endpoints and never calls LM Studio directly. For model download, server setup,
configuration and tests, see [docs/AI_ENGINEERING.md](docs/AI_ENGINEERING.md).

## 5. Run the tests

From the repository root (or from `backend/`):

```bash
pytest
```

Useful options:

```bash
pytest -v                                  # list every test by name
pytest backend/tests/test_budgets.py       # one file
pytest -k login                            # only tests with "login" in the name
pytest -x                                  # stop at the first failure
```

If `pytest` isn't found, use `python -m pytest`.

The tests use a temporary in-memory database, so they never touch `spendgpt.db` or TiDB. OCR is faked in the
upload tests, so `indra-ocr` isn't needed.

**Reading the result:** the last line should look like `271 passed, 4 deselected, 4 xfailed` (the 4 deselected are the live LM Studio tests). Each `xfailed` test marks a
known bug and is expected to fail. When you fix one, its test reports as failing until you delete the
`@pytest.mark.xfail(...)` line above it, which turns it into a normal test.

| Test file | Covers |
|---|---|
| `backend/tests/test_auth.py` | Register and login |
| `backend/tests/test_transactions.py` | Transactions |
| `backend/tests/test_budgets.py` | Budgets and overlap rules |
| `backend/tests/test_receipts.py` | Receipt upload and AI receipt endpoints |
| `backend/tests/test_ocr_parser.py` | OCR text parser (money, totals, dates, sample receipts) |
| `backend/tests/test_health_and_categories.py` | Health check and categories |
| `backend/tests/test_lmstudio_service.py` | LM Studio client (mocked server) |
| `backend/tests/test_categorization.py` | AI transaction categorisation |
| `backend/tests/test_anomaly.py` | Unusual-spending detection and alerts |

`backend/tests/test_lmstudio_live.py` talks to a real LM Studio server, so it is excluded by default.
Run it by hand with `pytest -m lmstudio -v -s` while LM Studio is running.

### Continuous integration

GitHub Actions runs the full test suite on every pull request and every push to `main`
(see `.github/workflows/tests.yml`). A green tick on a PR means all tests passed; a red cross means
something broke. Click **Details** next to the check to see which test failed.

You can also run it by hand from the repo's **Actions** tab → **Tests** → **Run workflow**.
