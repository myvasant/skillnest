# Testing

Groundwork treats learning content as code: every claim that can be executed is executed.

## Commands

| Command | What it does | Needs |
|---|---|---|
| `npm run validate:content` | Validates all YAML (schemas, ids, prerequisites, cycles, internal links, item references, visualization props). `-- --strict` also fails on warnings. | Node |
| `npm run typecheck` | `tsc --noEmit` over app, scripts and tests. | Node |
| `npm run lint` / `npm run format:check` | ESLint (incl. React hooks rules) / Prettier. | Node |
| `npm test` | All Vitest suites: unit + content verification (below). | Node (Pyodide runs under Node) |
| `npm run test:content` | Only the Pyodide-based content and runner tests. | Node |
| `npm run test:e2e` | Builds the app, serves it with `vite preview`, and runs Playwright in your **installed Edge** (`PW_CHANNEL=chrome` for Chrome, `PW_CHANNEL=bundled` after `npx playwright install chromium`). | Node + Edge/Chrome |
| `npm run test:projects` | For every local project kit: the reference solution must pass all tests and the starter must fail at least one. Uses `.venv` if present. | Python 3.11+ with the kit requirements |
| `npm run lint:python` | Ruff over `python/` and `projects/`. | Ruff |
| `npm run check:links` | Checks every external URL in content and records results in `content/link-report.json` (shown in the UI). | Internet |
| `npm run check` | validate → typecheck → lint → test → build. | Node |

Python environment for project kits:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install pytest ruff fastapi httpx uvicorn pydantic pydantic-settings numpy pandas scikit-learn
npm run test:projects
```

## Continuous integration

`.github/workflows/ci.yml` runs on pushes to `main`, pull requests and manual dispatch. The quality job uses Node 22, installs the lockfile with `npm ci`, checks formatting, then runs `npm run check` (content validation, typecheck, lint, unit/content tests and production build). A dependent browser job installs Playwright Chromium and runs the full E2E suite with `PW_CHANNEL=bundled`. The workflow uses read-only repository permissions and does not require secrets or paid services.

## Test layers

**Unit (`tests/unit`)**
* Content compiler: valid fixtures, and one test per validation rule (duplicate ids, unknown prerequisites, self
  references, cycles, strict keys, lessons for unknown concepts, broken item refs, MCQs without a correct option,
  unknown/invalid visualizations, broken internal links, unknown path targets, symmetric relations); the real
  curriculum compiles without errors and is topologically ordered.
* Engines: review schedule transitions, mastery statuses (latest-attempt rule, weak detection, mastery-check rule
  requiring code), recommendation priorities (new learner, continue, next with reason, due reviews first,
  unmet prerequisites, done).
* Storage: export/import round trip, rejection of foreign/corrupt/newer files with clear messages, defaults, history
  cap, persistence across store instances (close/reopen), unreadable data backup, save failures, no-storage mode,
  reset keeping theme.
* Helpers: output normalisation and diffs, prediction grading and misconception feedback, feedback rules, error
  explanations, search ranking and prefix matching, graph layout.
* Visualization maths: cosine/dot/distance, BFS/DFS order, gradient-descent updates and divergence, SQL joins,
  neural forward pass, attention weights and causal mask, complexity ordering.

**Content verification (`tests/content`, Pyodide under Node)**
* Every Python code block runs; blocks with `expectedOutput` must match exactly; `expectError` blocks must raise.
* Every `python-tracer` program runs without error.
* Every prediction question's answer equals the real output, and no listed "wrong answer" equals it.
* Every exercise's reference solution passes all of its tests (and matches `expectedOutput`), and its **starter code
  does not pass** (so tests actually test something).
* Every Parsons solution produces its expected output; every browser-project milestone solution passes its tests.
* Runner integration: stdout/stderr, input events, EOF on missing input, tracebacks without runner frames, syntax
  errors, output limit, `sys.exit`, isolation between runs, restoring patched builtins, trace events/frames/stable
  object labels/step limits, grading helpers, `run_program`, syntax-error short-circuit, error-after-pass, captured
  test output — and the SQL-join visualizer cross-checked against real SQLite for all join types.

**End-to-end (`tests/e2e`, Playwright against the production build)**
* `journey.spec.ts` — the complete first learning journey: open → curriculum → lesson → step-through visualization
  → run code → exercise with a wrong attempt and targeted feedback → fix → misconception feedback on a prediction →
  mastery check → saved progress → close and reopen → resume and recommendation → export → reset → import → restored.
  A second test checks the next recommendation after mastering two lessons.
* `resilience.spec.ts` — infinite loop stopped, explained and recovered; beginner error explanation; unsupported
  module message; unknown lesson and route pages; **no external network requests** during core learning; continued
  operation after the network disconnects; keyboard search; skip link; mobile navigation drawer; theme persistence.

## What is not automatically verified

* Prose accuracy is reviewed by people, not tests (each lesson records `reviewedOn`).
* Visual design and screen-reader experience are checked manually (keyboard paths and roles are covered by E2E).
* Docker builds, GitHub Actions workflows and optional integrations (Ollama, MLflow, Redis, LangGraph, the official
  MCP SDK) in project kits are documented manual steps; their tests are skipped unless the dependency is installed.
* Link checks confirm a URL resolves, not that its content still supports the claim.
