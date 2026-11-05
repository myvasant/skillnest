# Security and privacy

## Threat model

Groundwork is a single-user application that runs on your own computer: a static web app served from
`localhost`, curriculum content shipped with the repository, Python executed in your browser, and progress stored
in your browser. It has **no accounts, no server-side storage, no analytics and no telemetry**.

| Asset | Threats considered | Mitigations |
|---|---|---|
| Your progress and code drafts | Loss (cleared storage, corrupted data), tampering via imports | Synchronous saves; validation on load; unreadable data is backed up under a separate key instead of being discarded; export/import with schema validation, a size limit and explicit confirmation before replacing data. |
| The browser page | Script injection through content or imported files | Markdown is rendered to React elements (no raw HTML); URLs are restricted to `http(s)`, `mailto`, in-app paths and validated internal schemes; external links use `rel="noopener noreferrer"`. Imports are parsed as JSON and validated — never executed. |
| Your computer | Learner code doing something harmful | Learner code runs in Pyodide (WebAssembly) inside a Web Worker. See the execution boundary below. |
| Your privacy | Data leaving the device | Nothing is sent anywhere. The E2E suite asserts that core learning makes **no** request to any host other than localhost. Optional package downloads (Pyodide CDN) happen only when you click "load package". |

## Python execution boundary (be precise about what this is)

* Code runs in **WebAssembly in a dedicated Web Worker**. It cannot touch the page DOM, `localStorage` (where
  progress lives) or your real file system; it sees a virtual, in-memory file system that disappears on reload.
* **Time limit:** the main thread terminates the worker after 8 s (16 s for step-through traces) and starts a fresh
  interpreter. **Output** is capped at 200,000 characters. **Traces** stop at 300–2,000 steps.
* **Memory:** bounded by the browser's WebAssembly limits; a program that allocates aggressively can make the tab
  slow until the worker is terminated (use *Restart Python runtime* in Settings).
* **Network:** Pyodide exposes a `js` bridge, so code can make browser network requests (subject to CORS) just like
  any web page. It cannot open raw sockets.
* This is an **isolation boundary for your own learning code, not a hardened sandbox for hostile code.** Do not paste
  code you do not understand from untrusted sources — the same advice applies to any terminal.

## Local projects

Starter kits in `projects/` run with your own Python on your own machine, with your user's permissions. They are
designed to be safe (no network by default, temp directories in tests, sandboxed file access in agent projects), but
review code before running it, use a virtual environment, never commit `.env` files (they are git-ignored), and keep
real credentials out of exercises.

## Development servers

`npm run dev` and `npm run preview` bind to `localhost` only. Do not expose them to a network without adding the
usual protections (Vite's dev server is not designed to be public).

## Dependencies and supply chain

* All runtime and build dependencies are free/open-source with permissive licences
  (see [COST_AND_LICENSES.md](COST_AND_LICENSES.md)). `npm install` reported 0 known vulnerabilities at the time of
  writing; re-run `npm audit` and `pip-audit` periodically.
* Versions are pinned through `package-lock.json`. The Pyodide runtime is copied from the pinned npm package rather
  than fetched at run time.

## Known limitations

* Progress is not encrypted at rest; anyone with access to your browser profile can read it (it contains learning
  data only).
* Clearing browser site data deletes progress — export backups.
* Optional CDN package loads trust the official Pyodide CDN (jsDelivr) over HTTPS.
* Content and link checks verify that sources **resolve**, not that their content is unchanged.

## Reporting

This is a personal, local project. If you find a security issue in it, open an issue in your own repository or fix
it directly; do not include personal data in reports.
