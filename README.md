# SpendGPT
An AI-powered student finance copilot featuring local ML transaction categorization, anomaly detection, and a local LLM (LM Studio) for conversational money insights. Fully stack-implemented using React, FastAPI, MySQL, and layered architecture.

SpendGPT– AI Student Finance Copilot | React, FastAPI, MySQL, Local LLM (LM Studio)

* Building a full-stack finance copilot with a React frontend and FastAPI backend, using a layered architecture with
  MySQL for persistence.
* Implementing local ML models for automatic transaction categorisation and anomaly detection, paired with a
  local LLM (LM Studio) for conversational money insight

## Python dependencies

Install the shared Python dependencies from the repository root:

```bash
python -m pip install -r requirements.txt
```

## AI features (LM Studio)

The AI features run locally through LM Studio's OpenAI-compatible server
(`http://localhost:1234/v1`). The React app only calls the FastAPI `/api/ai/*`
endpoints and never calls LM Studio directly. For model download, server setup,
configuration and tests, see [docs/AI_ENGINEERING.md](docs/AI_ENGINEERING.md).
