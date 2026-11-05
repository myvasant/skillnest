# Production AI app (capstone): a summarise / answer service

Wrapping a model call in an HTTP endpoint takes ten lines. Running it in production
takes the rest of this project: the model is slow and sometimes down, users paste
100-page documents or text that says "ignore your instructions", the same request
arrives a hundred times, logs must not leak what users wrote, and you need evidence that
a model change did not make answers worse.

You build a FastAPI service with two endpoints backed by a **pluggable model**:

```text
POST /v1/summarise  {"text": "..."}                          -> {"summary": "...", "model": "...", "cached": false}
POST /v1/answer     {"question": "...", "context": "..."}    -> {"answer": "...",  "model": "...", "cached": false}
GET  /health                                                 -> {"status": "ok", "model": "fake-extractive"}
```

By default the model is `FakeModel`, a deterministic extractive "model" written in plain
Python, so everything runs offline and tests are reproducible. An optional `OllamaModel`
adapter talks to a free local LLM over HTTP.

Example session (fake model):

```text
$ curl -s -X POST localhost:8000/v1/answer -H "content-type: application/json" \
    -d '{"question": "When did the bridge open?", "context": "The bridge was designed in 1923. The bridge opened in 1932."}'
{"answer":"The bridge opened in 1932.","model":"fake-extractive","cached":false}

$ curl -s -X POST localhost:8000/v1/summarise -H "content-type: application/json" -d '{"text": "   "}'
{"detail":[{"type":"value_error","loc":["body","text"],"msg":"Value error, must not be empty or only whitespace",...}]}   (422)

log: {"attempts": 1, "cached": false, "duration_ms": 0.412, "event": "model_call", "input_chars": 80,
      "input_hash": "3f1c9a0e5b7d2c44", "model": "fake-extractive", "outcome": "ok", "task": "answer"}
```

## Setup

Windows (PowerShell):

```powershell
cd projects/production-ai-app
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

macOS / Linux:

```bash
cd projects/production-ai-app
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Run the service (use `--app-dir solution` for the reference):

```bash
python -m uvicorn --app-dir starter --factory ai_service:create_app --port 8000
```

Then open `http://127.0.0.1:8000/docs` for the interactive OpenAPI page.

Run the evaluation:

```bash
python starter/ai_eval.py                 # fake model, data/eval_set.jsonl, threshold 0.8
python solution/ai_eval.py --threshold 0.95   # the reference scores 0.900 -> FAIL
```

## Running the tests

```powershell
python -m pytest                    # everything, against starter/
python -m pytest -k Milestone1      # one milestone at a time
$env:GW_TARGET="solution"; python -m pytest; Remove-Item Env:GW_TARGET
```

```bash
python -m pytest
python -m pytest -k Milestone1
GW_TARGET=solution python -m pytest
```

No test uses the network, sleeps, or reads the wall clock: time comes from a fake clock,
`sleep` is a fake that advances it, and the Ollama adapter is tested with
`httpx.MockTransport`. One optional test (`test_real_ollama_round_trip`, marked
`network`) talks to a real Ollama and is skipped unless you set `GW_OLLAMA_MODEL`.

## Milestones

1. **Model interface and fake** (`TestMilestone1Model`) - `FakeModel` (extractive
   summary, keyword-overlap answer, "I don't know" fallback) and `build_prompt`, which
   fences untrusted text in `<document>`/`<question>` tags that user text cannot close.
2. **API and input limits** (`TestMilestone2Api`) - Pydantic bodies (no blank fields, no
   unknown fields: 422), size limits checked before the model is called (413), the two
   POST endpoints and `AIService.run`.
3. **HTTP adapter with timeouts** (`TestMilestone3Adapter`) - `OllamaModel.complete`:
   non-streaming `POST /api/generate`, per-call timeout passed to httpx, errors
   classified as transient (timeouts, connection errors, 429, 5xx) or permanent.
4. **Retries with backoff** (`TestMilestone4Retries`) - `backoff_delay` (exponential,
   capped, jittered), `call_with_retries` (transient only, max attempts, overall
   deadline), and status codes 503 (+`Retry-After`), 504 and 502 with generic messages.
5. **Response cache** (`TestMilestone5Cache`) - `TTLCache` (expiry with an injected clock,
   LRU eviction), `cache_key` (SHA-256 of task, model and normalised input), failures not
   cached, `cached: true` in responses.
6. **Logs and evaluation** (`TestMilestone6LogsAndEval`) - one JSON log event per call
   with sizes and a hash but never user text; `ai_eval.py` loads a labelled JSONL set,
   computes keyword recall and exits non-zero below the threshold.

## Optional: a real local model with Ollama

Everything above works without this. To try a real LLM (free, runs locally):

1. Install Ollama from <https://ollama.com> and run `ollama pull llama3.2:1b`.
   Hardware: the 1B model is about 1.3 GB on disk and runs on a laptop CPU with 8 GB of
   RAM; expect a few seconds per answer on CPU (much faster with a supported GPU). Larger
   models answer better but need more memory and time.
2. Start the service with the adapter:

   ```powershell
   $env:AI_MODEL="ollama:llama3.2:1b"; python -m uvicorn --app-dir solution --factory ai_service:create_app
   ```

   ```bash
   AI_MODEL=ollama:llama3.2:1b python -m uvicorn --app-dir solution --factory ai_service:create_app
   ```

   `OLLAMA_URL` changes the server address (default `http://localhost:11434`). The default
   `call_timeout` is 20 s; raise it in `ServiceSettings` for slow hardware.
3. Evaluate it: `python solution/ai_eval.py --model ollama:llama3.2:1b --threshold 0.7`.
4. Run the opt-in test: `$env:GW_OLLAMA_MODEL="llama3.2:1b"; python -m pytest -m network`
   (bash: `GW_OLLAMA_MODEL=llama3.2:1b python -m pytest -m network`).

Real model output is not deterministic across versions and hardware, which is exactly why
the default tests use the fake.

## Layout

```
production-ai-app/
  conftest.py               selects starter/ or solution/; registers the `network` marker
  requirements.txt          fastapi, uvicorn, httpx, pydantic, pytest
  data/eval_set.jsonl       10 labelled cases (summarise + answer)
  starter/ai_service.py     your service (TODOs per milestone)
  starter/ai_eval.py        your evaluation script (milestone 6)
  solution/ai_service.py    reference service
  solution/ai_eval.py       reference evaluation script
  tests/test_ai_service.py  tests, one class per milestone
```
