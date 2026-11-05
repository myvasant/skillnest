# Contributing

## Setup

```powershell
npm install          # also copies the Pyodide runtime into public/pyodide
npm run dev          # http://localhost:5173
```

Requirements: Node 22.12+ (20.19+ works for the app; Vitest 5 needs 22.12+), a Chromium browser (Edge or Chrome) for
end-to-end tests, and Python 3.11+ only if you work on the local project kits.

## Before opening a change

```powershell
npm run check        # validate content, typecheck, lint, unit + content tests, build
npm run test:e2e     # end-to-end journey (needs Edge or Chrome)
npm run test:projects  # if you touched projects/
```

## Code guidelines

* TypeScript strict mode; no `any` except at deliberate boundaries (visualization registry).
* Keep logic in pure functions (`src/engine`, `src/storage/actions.ts`, `src/content/build.ts`) and test it; keep React
  components presentational where possible.
* Prefer browser-native elements and the small primitives in `src/components/ui.tsx` over new dependencies. Any new
  dependency must be free, permissively licensed and recorded in `COST_AND_LICENSES.md`.
* Accessibility: semantic elements, labels for every control, visible focus, keyboard operation, no information by
  colour alone, respect reduced motion.
* Never introduce network calls in core features. If something optional needs the internet, label it in the UI and
  in `COST_AND_LICENSES.md`.
* Formatting is Prettier (160 columns); `npm run format` fixes it.

## Content guidelines

Read [CONTENT_SCHEMA.md](CONTENT_SCHEMA.md). In short:

* One concept per lesson; open with *why*; one idea at a time; accurate mental models; real error messages.
* Every Python example has `expectedOutput` (or is explicitly `illustrative`), and every exercise has tests that
  guard against hard-coding; mastery checks use new items and include code.
* Cite official documentation; never invent references; run `npm run check:links` for new URLs.
* **Never rename published ids** (concepts, lessons, sections, items, milestones, interview questions): learners'
  saved progress refers to them. Add new ids instead and retire old ones in a migration if needed.

## Progress schema changes

Bump `PROGRESS_SCHEMA_VERSION` in `src/storage/progress.ts`, add a step to `migrate()` that converts the previous
version, and add a unit test with a real document of the old version.

## Commit messages

Imperative mood, describe the learner-visible effect first (e.g. "Add binary search lesson with tracer").
