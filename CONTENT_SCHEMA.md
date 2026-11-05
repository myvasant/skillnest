# Content schema and authoring guide

All curriculum content lives in `content/` as YAML and is validated by
[`src/content/schema.ts`](src/content/schema.ts) (Zod, strict objects) and
[`src/content/build.ts`](src/content/build.ts) (cross-references). The app never
hard-codes lessons: adding a file is enough for it to appear everywhere
(curriculum graph, search, paths, recommendations, interview prep).

```
content/
  stages/NN-<stage>.yaml     # the knowledge graph: stages → modules → concepts
  lessons/<stage>/<name>.yaml# full interactive lessons (one per concept)
  glossary/<topic>.yaml      # terms, each linked to a concept (several files are merged)
  paths.yaml                 # goal-based learning paths (targets only)
  projects/<id>.yaml         # progressive projects
  interview/<topic>.yaml     # interview question banks (files sharing a category id are merged)
```

## Commands

| Command | What it checks |
|---|---|
| `npm run validate:content` | Schema + cross-references (fast, no Python). Add `-- --strict` to fail on warnings. |
| `npm run test:content` | Executes **every** Python example, prediction answer, exercise solution, tracer program and project milestone solution in Pyodide (CPython 3.14), the same runtime learners use. Also checks that starter code does *not* already pass. |
| `npm run dev` | Live reload; validation errors appear in the browser overlay. |

## Identifiers

`lowercase` words joined by `.` or `-`: `python.variables`, `git.merge-conflicts`.
Concept ids are prefixed with their stage id (`python.`, `cs.`, `rag.` …). Item
ids only need to be unique inside their lesson; the global id is
`<lessonId>/<itemId>` (used in saved progress — **never rename a published
item id**, or learners lose their history for it).

## Stage files (the knowledge graph)

```yaml
id: python
order: 2                 # unique, sets display order
title: Python — Absolute Beginner to Advanced
shortTitle: Python
summary: One or two sentences.
why: Why this stage matters for the learning goal.
modules:
  - { id: basics, title: First steps, summary: ... }
concepts:
  - id: python.variables
    title: Variables and assignment
    module: basics                 # must be a module of this stage
    level: beginner                # beginner | intermediate | advanced
    priority: essential            # essential | supporting | advanced | optional | technology-specific
    summary: What it is, in one sentence a beginner understands.
    why: (optional) the problem it solves.
    keyIdeas: [ ... ]              # 2–5 bullets, shown as the outline when there is no lesson
    misconceptions: [ ... ]
    requires: [python.first-program]   # prerequisites (graph edges); no cycles
    extends: []                    # builds on and deepens another concept
    contrastsWith: []              # made symmetric automatically
    confusedWith: []               # made symmetric automatically
    tools: []                      # e.g. [pytest, Ruff]
    interview: (optional) what interviewers expect
    production: (optional) production considerations
    sources:                       # official docs / specifications preferred
      - { title: ..., url: https://..., publisher: ..., version: "3.14" }
```

Derived automatically (do not write): `requiredBy`, `extendedBy`, the lesson,
items, projects, interview questions and glossary terms attached to a concept,
and `depth` (longest prerequisite chain).

**Prerequisite rules.** List only *direct* prerequisites — what a learner must
already understand to follow this concept. Transitive ones are inferred. A
prerequisite may live in another stage (e.g. `python.profiling` requires
`cs.complexity`). Cycles are rejected.

## Lessons

```yaml
id: python.variables          # usually equals the concept id
concept: python.variables     # exactly one lesson per concept
title: Variables and Assignment
subtitle: Names that refer to values        # optional
estimatedMinutes: 35
reviewedOn: 2026-10-22        # last human review of the prose
summary: ...
objectives: [ ... ]           # observable skills: "Predict…", "Write…", "Explain…"
sources: [ {title, url, publisher} ]       # at least one
sections: [ ... ]
items: [ ... ]                # assessment items, referenced from sections or the mastery check
masteryCheck:
  passThreshold: 0.8          # 0.5–1
  items: [ ... ]              # >= 3 item ids; include a code or debug item
cheatsheet: (markdown)
```

### Sections

```yaml
- id: reassignment
  title: Reassignment and updating values
  kind: walkthrough   # intro | why | mental-model | concept | walkthrough | internals | mistakes | debugging | practice | application | interview | summary
  depth: core         # core (default) | deep — deep sections are hidden until "Show deep dives"
  blocks: [ ... ]
```

Learner progress tracks section ids (resume, "sections read"), so keep them stable.

### Blocks

| type | fields | notes |
|---|---|---|
| `markdown` | `body`, `depth` | GitHub-flavoured Markdown. Internal links: `[text](concept:id)`, `[text](lesson:id)`, `[text](glossary:id)`, `[text](project:id)`, `[text](interview:id)` — all validated. |
| `code` | `code`, `language`, `runnable`, `expectedOutput`, `expectError`, `stdin`, `status`, `annotations[{line,text}]`, `caption`, `id` | Python blocks are **executed by the content tests**. With `expectedOutput` the output must match exactly (trailing whitespace ignored) and the UI shows "Verified output". `expectError: NameError` asserts the example raises. `status: illustrative` (not executed — say why in the caption) or `pseudocode`. Only Python can be `runnable`. |
| `callout` | `variant`, `title`, `body` | `tip`, `note`, `warning`, `misconception`, `analogy`, `deep-dive`, `production`, `interview`. |
| `visualization` | `component`, `title`, `caption`, `props` | See below; props are validated. |
| `item` | `ref` | Embeds an assessment item inline (practice mode). |

### Assessment items

Every item has `id`, `type`, `skill`, `prompt` (markdown), `explanation`
(the reasoning shown after answering), optional `difficulty` (1–3) and
`concepts` (defaults to the lesson concept).

Skills — use a spread across a lesson, because mastery requires evidence from at least two:
`recognition`, `explanation`, `prediction`, `implementation`, `debugging`, `transfer`, `design`.

| type | extra fields | grading |
|---|---|---|
| `mcq` | `options[{id, text, correct, feedback}]` | Exactly the chosen option; each option's `feedback` explains *why* (write feedback for wrong options that names the misconception). Options are shuffled deterministically. |
| `true-false` | `answer` | |
| `predict-output` | `code`, `answer`, `wrongAnswers[{answer, feedback}]` | Normalised exact match. `answer` is verified by running `code`. Add `wrongAnswers` for the predictable misconceptions. |
| `code` / `debug` | `starterCode`, `solution`, `tests[{name, code}]`, `hints[]`, `stdin`, `expectedOutput`, `feedback[{when, message}]` | Tests are Python run after the learner's program, in its namespace. The solution must pass all tests; the starter must not. |
| `explain` | `rubric[]`, `modelAnswer` | Self-assessed against the rubric (≥ 75% of points = correct). Labelled "self-assessed" in the UI and excluded from reviews. |
| `parsons` | `solution`, `distractors[]`, `expectedOutput` | Learner orders lines. With `expectedOutput` the arrangement is *run* (so any valid order passes); otherwise it must match `solution` exactly. |

**Test helpers available inside `tests[].code`:**

| helper | meaning |
|---|---|
| `output()` / `output_lines()` | What the learner's program printed (lines with trailing spaces removed). |
| `source` | The learner's code as a string (use `ast.parse(source)` for structure checks). |
| `uses("For", "While")` | True if the code contains any of these AST node types. |
| `calls("sorted")` | True if the code calls a function/method with this name. |
| `defined("total")` | True if the program defined this name. |
| `run_program("3\n4\n")` | Re-run the whole program with other stdin; returns its output (raises on error). |
| any learner name | Functions and variables the learner defined, e.g. `assert add(2, 3) == 5`. |

Write assertion messages a beginner can act on:
`assert total == 180, f"total should be 180, but it is {total!r}."`

Guard against hard-coding with structure checks or by re-running with
changed inputs (see `python.numbers` → `split-bill`).

**Feedback rules** (`feedback`) match the run result *after* grading fails.
All given conditions must hold: `outputEquals`, `outputContains`, `errorType`,
`errorMessageContains`, `codeContains`, `codeMatches` (regex). Use them for
known misconceptions, e.g. printing `"total"` instead of `total`.

### Visualizations

| component | props |
|---|---|
| `python-tracer` | `code`, `stdin?`, `showPrimitivesAsObjects` (default true), `maxSteps` | Real `sys.settrace` trace in Pyodide: frames, names → objects, output. |
| `step-diagram` | `nodes[{id,label,x,y,detail?,shape?}]`, `edges[{id,from,to,label?}]`, `steps[{title,body,active[],payload?}]`, `width`, `height` | Data-driven diagram for lifecycles and pipelines (HTTP, RAG, agents, CI/CD…). `active` lists node/edge ids lit in that step. |
| `vector-similarity` | `a`, `b` (2-D) | Dot product, cosine similarity, Euclidean distance with draggable vectors. |
| `complexity-growth` | `maxN` | Operation counts for common Big-O classes. |
| `graph-traversal` | `nodes[{id,x,y}]`, `edges[[a,b]]`, `start`, `directed` | BFS/DFS with visible frontier. |
| `gradient-descent` | `target`, `start`, `learningRate` | Minimising (x − target)². |
| `sql-join` | `left`, `right` tables `{name,key,columns,rows}` | INNER/LEFT/RIGHT/FULL join results. |
| `neural-forward` | `inputs` | A 2-2-1 network; weights adjustable. |
| `attention` | `tokens` | Scaled dot-product attention weights. |

## Glossary, paths, projects, interview questions

* **Glossary** (`glossary/*.yaml`, each `{terms: [...]}`): `{id, term, aliases[], definition, concept?}`. Ids and terms must be unique across all files. Link from prose with `[term](glossary:id)`.
* **Paths** (`paths.yaml`): `{id, title, role, summary, outcomes[], targets[]}`. Only list *targets*: the path is the prerequisite closure of the targets, ordered topologically, so paths share the graph instead of duplicating it.
* **Projects** (`projects/*.yaml`): problem, prerequisites (`concepts`), acceptance criteria, architecture, `environment: browser | local`, setup, milestones (`tests` + `solution` for in-browser milestones; local projects ship pytest suites under `projects/<id>/`), testing, security, extensions, rubric.
* **Interview** (`interview/*.yaml`): `category {id,title,summary}` and questions `{id, level: junior|mid|senior, kind, concepts[], question, answer, keyPoints[], followUps[], pitfalls[]}`.

## Teaching standards (checklist for every lesson)

1. **Why before how.** Open with the problem the concept solves.
2. **One new idea at a time**, smallest example first; define every new term (link the glossary).
3. **Mental model** that stays accurate later (e.g. names → objects, not boxes). Say when a model is simplified.
4. **How it works inside** (as a `deep` section if it would overwhelm beginners).
5. **Common mistakes** with the actual error message and the fix.
6. **Practice across skills**: predict, implement, debug, transfer to a new situation.
7. **Mastery check uses new items** (not the practice ones) and includes code.
8. Use only concepts that are prerequisites (or explicitly preview later ones with a link).
9. Accuracy: state version-specific behaviour (Python 3.14 in the browser); prefer official docs as sources; never invent references.
10. Inclusive, plain English; avoid jargon without definition; no culture-specific assumptions without explanation.

## Browser runtime constraints for examples

* Python 3.14 (Pyodide) — the standard library is available, but the WebAssembly runtime has important platform limits: no network sockets, operating-system threads, process pools or subprocesses.
* The current worker executes learner code synchronously. The current JavaScript runtime also cannot provide the WebAssembly stack switching needed by `asyncio.run()`. A coroutine object can be created and inspected, but full event-loop examples must be marked `status: illustrative` and verified locally with CPython.
* `threading`, `concurrent.futures` thread/process pools, `multiprocessing`, `subprocess` and full `asyncio` execution must not be marked runnable in this browser runtime. Explain the local CPython environment needed to run them.
* `input()` reads from `stdin` (one line per call). Provide `stdin` on blocks/items that need it.
* The file system is virtual (`/home/pyodide`); files written in one run persist until the page reloads, so examples should create the files they read.
* Third-party packages (numpy, pandas…) are not available to verified examples; mark such code `status: illustrative` and explain how to run it locally.
* Programs are stopped after 8 s and output is capped at 200,000 characters.

## Worked example: adding a lesson

1. Make sure the concept exists in `content/stages/…` (add it with its `requires` if not).
2. Create `content/lessons/python/strings.yaml` with `id`/`concept: python.strings`.
3. Write sections, then items, then the mastery check.
4. `npm run validate:content` — fix any reported path.
5. `npm run test:content` — every example and solution is executed.
6. `npm run dev` and read it as a learner. The lesson now appears in the curriculum graph, search, paths and recommendations automatically.
