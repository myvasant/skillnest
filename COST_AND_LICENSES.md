# Cost and licences

**Total required cost: ₹0.** No paid APIs, subscriptions, hosting, databases, accounts, fonts, icons or datasets are
required for any core feature. Everything runs on your computer.

## Runtime dependencies (shipped to the browser)

| Package | Version | Licence | Purpose | Internet | Account |
|---|---|---|---|---|---|
| react, react-dom | 19.3 | MIT | UI | No | No |
| react-router | 7.18 | MIT | Routing | No | No |
| zod | 4.6 | MIT | Content and progress validation | No | No |
| pyodide | 314.0.7 | MPL-2.0 (CPython inside: PSF licence) | Python 3.14 in the browser, served locally | No (core); optional packages from CDN | No |
| codemirror, @codemirror/*, @lezer/* | 6.x | MIT | Code editor and syntax highlighting | No | No |
| react-markdown, remark-gfm | 10.1, 4.0 | MIT | Safe Markdown rendering | No | No |
| lucide-react | 1.61 | ISC | Icons | No | No |

## Development and test tools

| Tool | Licence | Purpose |
|---|---|---|
| Vite 8, @vitejs/plugin-react | MIT | Dev server and build |
| TypeScript 6.0 | Apache-2.0 | Type checking (6.0 rather than 7.x because typescript-eslint supports < 6.1) |
| Tailwind CSS 4 | MIT | Styling |
| Vitest 5, jsdom, Testing Library | MIT | Unit and content tests |
| Playwright 1.64 | Apache-2.0 | End-to-end tests, driving your installed Edge or Chrome (no browser download needed) |
| ESLint 10, typescript-eslint, Prettier | MIT | Linting and formatting |
| yaml, tsx | ISC, MIT | YAML parsing, running TS scripts |
| pytest, Ruff | MIT | Python project tests and linting |
| FastAPI, Pydantic, pydantic-settings | MIT | Backend projects |
| httpx, uvicorn, Starlette | BSD-3-Clause | Backend projects |
| NumPy, pandas, scikit-learn | BSD-3-Clause (NumPy bundles some 0BSD/MIT/Zlib/CC0 parts) | Data and ML projects |

A scan of all 367 installed npm packages found only permissive licences: MIT (309), Apache-2.0 (21), ISC (15),
BSD-2-Clause (8), MPL-2.0 (5: Pyodide, lightningcss), BSD-3-Clause (3), MIT-0, BlueOak-1.0.0, CC0-1.0 (mdn-data),
and CC-BY-4.0 (caniuse-lite data, attribution in its package). No copyleft (GPL/AGPL) packages are used.

## Fonts, icons, images, datasets

* **Fonts:** system fonts only (Segoe UI / SF / system-ui; Cascadia Code / Consolas for code). Nothing is downloaded.
* **Icons:** Lucide (ISC). **Images:** none; all diagrams are generated SVG.
* **Datasets:** projects generate synthetic data with fixed seeds or use datasets bundled inside scikit-learn
  (e.g. Iris, Breast Cancer Wisconsin, Diabetes — distributed with scikit-learn under its BSD licence; see each
  project's README for dataset notes).

## What needs the internet

| Feature | Needs internet? |
|---|---|
| Lessons, quizzes, exercises, tracer, playground (standard library), search, progress, projects pages | No |
| `npm install` / `pip install` (first setup) | Yes, once |
| Loading optional Pyodide packages (numpy, pandas, scikit-learn…) in the playground | Yes, first time (≈3–25 MB each), from the official Pyodide CDN |
| Opening external documentation links | Yes |
| Optional local LLMs for advanced projects (Ollama) | Download once; then offline |

## Optional AI

Core learning never calls an AI model. Some advanced projects include an **optional** adapter for a local model
served by [Ollama](https://ollama.com) on `localhost`. Nothing is downloaded automatically.

Rough hardware guide for local models (quantised, 4-bit): 1–3 B parameter models need ~2–4 GB of free RAM and run
on most laptops (slowly on CPU); 7–8 B models need ~6–8 GB RAM (or a GPU with ~6 GB VRAM) and several GB of disk
each. Every AI-backed project ships a deterministic fake model so its tests and core behaviour work without any model.

## Free vs open source vs free tier vs open weights

* **Free software / open source:** you may use, study, modify and share the software (e.g. MIT, Apache-2.0, BSD,
  MPL). Everything Groundwork depends on is in this category.
* **Free of charge (freeware):** no price, but not necessarily open or modifiable.
* **Free tier:** a paid service with a no-cost allowance that can change or end. Groundwork depends on **no** free
  tier. Some curriculum topics mention hosted tools (for example LangSmith); their terms must be checked before use
  and are never required.
* **Open-weight model:** the trained weights are downloadable, but training data and code may not be, and the licence
  may restrict use (e.g. acceptable-use policies, user thresholds).
* **Open-source AI model:** per the Open Source Initiative's Open Source AI Definition, the weights, code and enough
  information about the training data to reproduce the system are available under open terms. Few models qualify;
  check each model's licence before use.

## Curriculum sources

Lessons and outlines link to official documentation and specifications; text is original and links are attributed.
Run `npm run check:links` to re-check that every cited URL still resolves (results in `content/link-report.json`,
shown next to each source).
