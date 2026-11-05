# Architecture

Groundwork is a **local-first, static single-page application**. There is no application server, database
server or account system: the curriculum is compiled into the build, Python runs in the browser, and progress
is stored in the browser. This is the simplest architecture that meets the requirements (zero cost, works
offline, private by default) and it keeps every learning feature testable on one machine.

```
                         build time                                   run time (your browser)
 ┌──────────────────────────────────────────┐        ┌────────────────────────────────────────────────────────┐
 │ content/**/*.yaml                        │        │  React SPA (Vite build, code-split per screen/lesson)  │
 │   stages · lessons · glossary · paths    │        │                                                        │
 │   projects · interview                   │        │  ┌─────────────┐   ┌──────────────┐   ┌─────────────┐  │
 │        │                                 │        │  │ Lesson view │──▶│ Python client│──▶│ Web Worker  │  │
 │        ▼  src/content/schema.ts (Zod)    │        │  │ Exercises   │   │ (timeouts,   │   │ Pyodide     │  │
 │   validate + cross-check (build.ts)      │──────▶ │  │ Tracer      │◀──│  queue)      │◀──│ gw_runner.py│  │
 │        │                                 │ virtual│  └─────────────┘   └──────────────┘   └─────────────┘  │
 │        ▼  scripts/vite-content-plugin.ts │ modules│  ┌─────────────┐   ┌──────────────┐                    │
 │   curriculum index · lesson chunks ·     │        │  │ Engines:    │◀─▶│ Progress     │──▶ localStorage    │
 │   search docs · projects · interview     │        │  │ mastery,    │   │ store (Zod-  │    (one versioned  │
 └──────────────────────────────────────────┘        │  │ review,     │   │ validated)   │     JSON document) │
                                                     │  │ recommend,  │   └──────────────┘                    │
  tests/content: every Python snippet, answer and    │  │ search      │        ▲ export / import (JSON file)  │
  solution is executed in Pyodide under Node.         │  └─────────────┘                                       │
                                                     └────────────────────────────────────────────────────────┘
```

## Source layout

| Path | Responsibility |
|---|---|
| `content/` | The curriculum as data (see [CONTENT_SCHEMA.md](CONTENT_SCHEMA.md)). |
| `src/content/` | `schema.ts` (Zod schemas), `build.ts` (validation, knowledge-graph derivation, paths, search docs — pure and isomorphic), `load.ts` (Node file reading), `runtime.ts` (browser access to virtual modules), `visualizationSchemas.ts`. |
| `scripts/vite-content-plugin.ts` | Compiles content into virtual modules; validation errors fail the build and show in the dev overlay; HMR on content edits. |
| `python/gw_runner.py` | Runs, traces and grades learner code inside Pyodide. Shared by the browser worker and the test-suite. |
| `src/python/` | Worker (`worker.ts`), main-thread client with timeouts and a request queue (`client.ts`), protocol and types, Pyodide glue (`host.ts`). |
| `src/engine/` | Deterministic, unit-tested logic: `mastery.ts`, `review.ts`, `recommend.ts`, `feedback.ts`, `errors.ts` (beginner explanations), `output.ts`, `search.ts`, `layout.ts` (DAG layout). |
| `src/storage/` | Progress schema, migrations, export/import (`progress.ts`), pure state transitions (`actions.ts`), persistent store (`store.ts`). |
| `src/features/` | Screens: dashboard, lesson (+ mastery check), assessment items, code runner, visualizations, curriculum explorer and concept pages, paths and diagnostics, review, playground, projects, interview prep, glossary, settings, layout/search. |
| `src/components/` | Small UI primitives (no third-party component kit), Markdown renderer, CodeMirror editor, static highlighter. |
| `projects/` | Local project starter kits: starter code, pytest suites, reference solutions. |
| `tests/` | `unit/` (engines, storage, content compiler, visualization maths), `content/` (Pyodide execution of all content, runner integration), `e2e/` (Playwright). |

## Key decisions and trade-offs

1. **Static SPA, no backend.** Learning data is personal and small; a server would add hosting cost, auth and
   failure modes without improving learning. *Trade-off:* no automatic multi-device sync — export/import a JSON
   backup instead. A FastAPI backend remains an option if sync or shared classrooms are ever needed.
2. **Vite + React 19 + TypeScript + Tailwind CSS v4.** Next.js was not used: server rendering and routing
   conventions bring no benefit to an offline, client-only app. No component library: native elements (`dialog`,
   `details`, inputs) plus ~10 small primitives keep the bundle and the dependency surface small.
3. **Content as YAML validated by Zod at build time.** YAML is pleasant for multi-line prose and code; strict
   schemas catch typos; cross-reference validation catches broken links, unknown prerequisites, cycles, missing
   tests and invalid visualization props. The same compiler runs in Vite, the CLI and the tests. Each lesson is
   its own lazy chunk.
4. **Python in the browser with Pyodide in a Web Worker.** Real CPython 3.14 (WebAssembly), the same runtime in
   the browser and in Node tests, so "verified output" means verified in the learner's runtime. The worker keeps
   the UI responsive; the only reliable way to stop an infinite loop is terminating the worker, so the client does
   that after 8 s and transparently starts a fresh interpreter. Tracing uses `sys.settrace` and snapshots frames and
   reachable objects (with stable object labels), so the tracer shows what CPython actually did.
5. **Progress in localStorage as one versioned JSON document.** Data is a few hundred KB at most; synchronous
   writes mean closing the tab never loses work; the document is validated on load and import, unreadable data is
   backed up rather than discarded, and `schemaVersion` + `migrate()` handle future changes. IndexedDB or SQLite
   (OPFS) would add complexity without a current need.
6. **Deterministic, transparent learning engines.** Mastery, spaced review (Leitner boxes 1/3/7/16/35/90 days) and
   recommendations are plain functions with documented rules and unit tests; every recommendation states its
   reason. No AI is needed for core learning.
7. **Search without a library.** A small scorer over pre-built documents (titles weighted over bodies, prefix
   matching for the last word, all words required) is fast for thousands of documents and fully testable.
8. **Visualizations as a registry.** Lessons reference visualizations by id with props validated at build time.
   The general `step-diagram` is data-driven (nodes, edges, steps in YAML), so new lifecycle/pipeline diagrams need
   no code. Each interactive visualization's maths is a pure, unit-tested function; the SQL join visualizer is
   cross-checked against SQLite.
9. **Local-first and offline.** The Pyodide runtime is copied from `node_modules` into the build, so core Python
   needs no CDN. After start-up, production builds prefetch every screen and lesson chunk so the app keeps working
   if the network drops. Only optional packages (numpy, pandas…) are fetched from the official Pyodide CDN, on
   explicit request.
10. **Two kinds of projects.** Beginner projects run in the browser and are graded by the same engine as
    exercises. Later projects run on the learner's machine as starter kits with pytest suites; a script verifies
    that every reference solution passes and every starter fails.

## Request flows

**Running an exercise.** `CodeExercise` → `python.grade(code, tests)` → queued → worker → `gw_runner.grade_json`
executes the program as `__main__` with redirected stdout/stdin, then each test in a copy of the program's
namespace with helper functions → JSON result → UI shows checks, misconception feedback rules, output diff and a
beginner explanation of any error → `recordAttempt` updates progress (practice mode).

**Mastery check.** Items run in *assessment mode* (one attempt, no hints) → `scoreMasteryCheck` (score ≥ threshold
**and** at least one code/debug item solved) → `completeMasteryCheck` marks the concept mastered and schedules the
first review → `recommend()` proposes the next step with its reason.

**Recommendation.** Due reviews → weak concepts → started lessons (continue or take the mastery check) → next
concept in the active path whose lesson exists (or its earliest unmet prerequisite) → done.

## Performance notes

* Initial JS ≈ 106 KB gzip (React, router, curriculum index); CodeMirror (~90 KB gzip), Markdown and each screen are
  lazy chunks. The Pyodide runtime (~13 MB, cached by the browser) loads in the background on pages that run Python.
* The curriculum index includes every concept outline (~400 concepts); lesson bodies, projects, interview questions
  and search documents are separate chunks.
