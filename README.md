# MyGPT

MyGPT is a personal AI workspace with authenticated conversations, streaming
responses, memory, document retrieval, image analysis, and voice features.

## Development setup

Use Python 3.11 or newer and Node.js 20 or newer.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set a real `JWT_SECRET_KEY` in `backend/.env`. Keep `APP_ENV=development` for
local work. For a deployed backend, set `APP_ENV=production`, configure
`JWT_SECRET_KEY`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, and `CORS_ORIGINS`.

Start the backend from the `backend` directory:

```powershell
uvicorn app:app --reload --port 8000
```

In a second terminal:

```powershell
cd mygpt-ui
npm install
$env:NEXT_PUBLIC_API_URL = "http://127.0.0.1:8000"
npm run dev
```

Open `http://localhost:3000`.

## Accuracy and speed

The default `llama3.2:1b` model is a lightweight fallback. It starts quickly,
but it will make more reasoning and coding mistakes than a larger model. For
better accuracy on a local machine, install a model that fits available RAM,
for example:

```powershell
ollama pull qwen2.5:7b
```

Then set `OLLAMA_MODEL=qwen2.5:7b` in `backend/.env`. Keep the 1B model for
low-memory machines. `OLLAMA_TEMPERATURE=0.2` is intentional: it makes factual
and code answers more consistent. The agent now avoids unnecessary web/RAG
calls, keeps the model warm, and answers deterministic time/math requests
without an extra LLM round trip.

## Verification

```powershell
cd mygpt-ui
npm run lint
npm run build

cd ..
python -m compileall -q backend
node backend/test_copy_button.js
python backend/test_agent_context.py
```

The privacy script writes users and vector indexes to the local development
database. Run it only against disposable test data after installing all
backend dependencies:

```powershell
python backend/test_privacy.py
```

Never deploy `backend/agents/app.py` as a separate service. It is only a
compatibility import for older commands and forwards to the authenticated app.
