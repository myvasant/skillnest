# Implementation roadmap and verified status

**Project:** Groundwork — local-first technical learning platform  
**Audit date:** 4 November 2026  
**Specification:** `Platform_prompt.txt` (21 sections)

## Executive status

The supplied project is a substantial local-first learning application, not a blank scaffold. It uses React 19, TypeScript and Vite; structured YAML content validated with Zod; a generated prerequisite graph and goal-based paths; browser-local progress storage; a Pyodide Web Worker; deterministic assessment and mastery logic; project kits; interview banks; and interactive visualisations.

The largest remaining gap is curriculum depth. There are **414 concepts across 21 stages and 85 modules**. **280 concepts (67.6%) have full lessons**; 134 remain outline-only. **271/271 essential concepts (100.0%) have full lessons**, leaving **0 essential concepts** to author. This is not yet the complete beginner-to-production curriculum requested.

| Inventory | Current count |
|---|---:|
| Stages / modules / concepts | 21 / 85 / 414 |
| Essential concepts | 271 |
| Full lessons / outline-only concepts | 280 / 134 |
| Lesson sections / assessment items | 1,916 / 1,850 |
| Code blocks / runnable code blocks | 1,258 / 1,153 |
| Projects / milestones | 28 / 132 |
| Glossary terms / interview questions | 507 / 212 |
| Goal-based learning paths | 10 |
| Concept-source references | 961 (953 map to URLs marked OK in the saved report) |

## Requirement status

| Requirement | Status | Evidence and remaining work |
|---|---|---|
| Zero-cost, local-first core | Implemented in source | Static SPA, local curriculum and localStorage; no mandatory paid service, account or cloud backend. First dependency install requires network access. |
| App shell and required pages | Implemented in source | Dashboard, curriculum, concept/lesson, paths, review, playground, projects, interviews, glossary, visual explorer and settings. Browser E2E is not currently verified in this environment. |
| Structured curriculum engine | Implemented and schema-validated | YAML, Zod schemas, content loader/compiler and reusable renderers. A new lesson can be added without changing UI components. |
| Prerequisite graph and learning paths | Implemented in source | 414 concepts, prerequisite edges, diagnostics and 10 goal-based paths. Acyclic graph and reference checks passed in the current audit. |
| Python execution | Implemented with documented limits | Pyodide in a worker, timeouts, output limits and exercise grading. This is not a hardened sandbox for hostile code. |
| Progress and data management | Implemented in source; E2E pending | Versioned local persistence, cross-tab updates, export/import, reset and diagnostics. Full browser restoration journey still needs execution. |
| Assessments and mastery | Implemented for authored lessons | 1,850 items, feedback, code tests and deterministic mastery. Coverage depends on missing lesson content. |
| Visual learning | Partially implemented | Several accurate interactive visualisations exist; not every concept has a suitable visual explanation. |
| Projects | Partially implemented | 28 project specifications and 132 milestones; starter/reference kits and automated tests exist, but not every project is a complete deployable product. |
| Interview practice | Partially implemented | 212 questions exist; dedicated timed sessions, answer history and richer rubric workflow remain. |
| Search and glossary | Implemented in source | Global index spans lessons, concepts, glossary, projects, exercises and interview questions; browser behaviour still needs E2E confirmation. |
| Security, accessibility and performance | Partially implemented/documented | Worker isolation boundary, privacy and security documentation, accessibility tests and responsive UI exist. Manual screen-reader, keyboard, mobile and adversarial reviews remain. |
| Required documentation | Implemented as files; keep status current | README, architecture, curriculum, audit, schema, contributing, costs/licenses, security, testing and roadmap files are present. |
| Production build and release validation | Not verified here | Copied dependencies are for Windows; Linux is missing the matching Rolldown/esbuild native bindings. Do a clean `npm ci` on target Windows and run the full checks. |

## Curriculum coverage matrix

| # | Domain | Concepts | Essential | Full lessons | Essential full | Coverage | Assessments | Essential missing |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | Foundations | 16 | 12 | 13 | 12 | 81% | 90 | 0 |
| 2 | Python | 61 | 42 | 48 | 42 | 79% | 571 | 0 |
| 3 | CS & Engineering | 34 | 20 | 22 | 20 | 65% | 162 | 0 |
| 4 | Git & Linux | 21 | 14 | 14 | 14 | 67% | 63 | 0 |
| 5 | Networking & HTTP | 20 | 14 | 14 | 14 | 70% | 66 | 0 |
| 6 | Backend | 18 | 14 | 14 | 14 | 78% | 66 | 0 |
| 7 | Databases | 19 | 13 | 13 | 13 | 68% | 81 | 0 |
| 8 | Maths & Stats | 19 | 14 | 14 | 14 | 74% | 83 | 0 |
| 9 | Data Analysis | 11 | 8 | 8 | 8 | 73% | 32 | 0 |
| 10 | Data Engineering | 17 | 9 | 9 | 9 | 53% | 36 | 0 |
| 11 | Machine Learning | 25 | 16 | 16 | 16 | 64% | 101 | 0 |
| 12 | Deep Learning | 20 | 13 | 13 | 13 | 65% | 69 | 0 |
| 13 | GenAI & LLMs | 19 | 14 | 14 | 14 | 74% | 94 | 0 |
| 14 | RAG | 19 | 14 | 14 | 14 | 74% | 75 | 0 |
| 15 | LLM Frameworks | 12 | 2 | 2 | 2 | 17% | 8 | 0 |
| 16 | Agentic AI | 21 | 11 | 11 | 11 | 52% | 66 | 0 |
| 17 | Graphs & Knowledge | 11 | 5 | 5 | 5 | 45% | 20 | 0 |
| 18 | MLOps & Production | 23 | 15 | 15 | 15 | 65% | 60 | 0 |
| 19 | Security & Responsible AI | 11 | 10 | 10 | 10 | 91% | 63 | 0 |
| 20 | System Design | 9 | 6 | 6 | 6 | 67% | 24 | 0 |
| 21 | Interviews | 8 | 5 | 5 | 5 | 62% | 20 | 0 |
| | **Total** | **414** | **271** | **280** | **271** | **67.6%** | **1850** | **0** |

## Work completed in this implementation sequence

- Fixed a malformed YAML flow-map label in the SQLite lesson.
- Hardened cross-tab progress storage against malformed JSON and schema-invalid updates; added a regression test.
- Added foundational computer and binary-data lessons.
- Completed all essential Python and CS & Engineering concepts, including logging, configuration, concurrency, asyncio, secure coding, data structures, algorithms, testing, code review and architecture fundamentals.
- Completed all essential Git/Linux and Networking/HTTP concepts, including version control, merge conflicts, remotes, Linux permissions/processes, SSH, network layers, TLS, HTTP semantics, REST and systematic debugging.
- Completed all essential Backend and Database concepts, including API design, validation, middleware, dependency injection, async endpoints, authentication/authorization, caching, SQL, indexes, query plans, transactions and migrations. The original SQL joins lesson was preserved.
- Completed all essential Maths/Statistics, Data Analysis and Data Engineering concepts, including NumPy/pandas foundations, data cleaning, EDA, feature engineering, ETL/ELT, orchestration, data modelling, incremental pipelines and data quality.
- Completed all essential Machine Learning and Deep Learning concepts, including supervised/unsupervised learning, core algorithms, model evaluation, leakage, regularisation, gradients, optimisation, embeddings, tokenisation and Transformers.
- Completed all essential GenAI/LLM and RAG concepts, including prompting, model APIs, structured output, tool calling, model selection/licensing, evaluation, cost/latency, ingestion, chunking, embeddings, hybrid search, access control, grounding and RAG failure analysis.
- Completed all essential LLM Framework, Agentic AI and Graph/Knowledge concepts, including framework trade-offs, tool design, state, human approval, sandboxing, agent evaluation/security, property graphs, traversal and knowledge graphs.
- Completed all essential MLOps/Production, Security/Responsible AI, System Design and Interview concepts, including containers, CI/CD, experiment tracking, serving, observability, monitoring, incident response, threat modelling, privacy, LLM security, scalability, cloud fundamentals and interview communication.
- Expanded the authored curriculum from 114 to **280 full lessons** in this implementation sequence. All **271 essential concepts** now have full lessons; 134 supporting/advanced/optional concepts remain outline-only.

## Verification performed in this pass

| Check | Result | Notes |
|---|---|---|
| Zod schema validation | **Passed** | Compiled the project's actual `schema.ts` and validated 21 stages, 280 lessons, 28 projects, 14 glossary files, 14 interview files and `paths.yaml`; zero schema errors. |
| Curriculum graph references and cycles | **Passed** | All 414 concept IDs and prerequisite references resolve; graph is acyclic. |
| New lesson examples and exercise solutions | **Passed for this batch** | 166 new lessons added in this implementation sequence. Runnable Python examples compiled and executed; reference exercise solutions passed their embedded assertions; unfinished starters did not pass. |
| TypeScript typecheck | **Passed** | `tsc --noEmit` completed successfully after the content additions. |
| ESLint | **Passed** | ESLint completed with no findings. |
| Prettier on new lesson files and audit docs | **Passed** | New lesson files and the updated roadmap/audit were checked. The whole repository still has 16 pre-existing formatting findings in unrelated files. |
| Unit/content test runner | **Blocked** | Vitest cannot start because the copied dependency tree lacks `@rolldown/binding-wasm32-wasi`. |
| `npm run validate:content` | **Blocked** | `tsx` invokes esbuild, but the copied tree contains `@esbuild/win32-x64` rather than the Linux binary. Direct Zod validation above succeeded. |
| Production build | **Blocked** | Vite fails before bundling because `@rolldown/binding-linux-x64-gnu` is missing from the copied Windows-only dependency tree. |
| Playwright E2E | **Not run** | Requires a clean install and browser runtime. |
| Fresh Windows install | **Not run** | Must be verified on the target machine. |

## Remaining work — next priorities

### P0 — Reproducible release validation

1. On Windows, extract the source package and run `npm ci` from the lockfile; do not reuse `node_modules` copied from another operating system.
2. Run `npm run check`, `npm run test:e2e`, `npm run test:projects`, `npm run lint:python`, `npm run format:check` and `npm run check:links`.
3. Resolve failures that are actual project defects; report environment-specific failures separately.

### P1 — Expand supporting and advanced curriculum

All **271 essential concepts now have full lessons**. The remaining **134 concepts** are supporting knowledge, advanced specialisations, optional enrichments or technology-specific implementations. Expand them in prerequisite order, with particular attention to deeper Data Analysis, Data Engineering, LLM Frameworks, Graphs, MLOps, System Design and Interview content.

Do not promote a supporting or optional concept to essential merely to inflate coverage; retain the documented priority model and add full lessons where they materially support the target learning paths.

### P2 — Close non-curriculum feature gaps

- Extend project workflow with learner submissions/artifacts, review and milestone-level feedback where useful.
- Build a fuller interview mode with timed practice, answer evaluation, coding tasks and session history.
- Complete visual explanations selectively where diagrams materially improve understanding.
- Run manual accessibility, responsive/mobile, offline and hostile-input reviews.
- Re-run the external source-link checker; the saved link report is dated 23 October 2026 and is not a fresh verification.

### P3 — Optional enhancements

- Optional local-model assistance with explicit consent, hardware checks and deterministic non-AI alternatives.
- Optional local Cypher/graph database sandbox.
- Optional offline package mirror for NumPy/pandas exercises.
- Do not introduce multi-device sync unless the user explicitly accepts a server-backed mode; local-first privacy is the current default.

**Completion is not claimed.** All 271 essential concepts now have full lessons, but 134 supporting/advanced concepts remain outline-only, some feature workflows remain partially implemented, and production build, browser E2E and fresh-install acceptance remain unverified.
