# CI pipeline for a small Python library

You maintain `ci_textkit`, a tiny text-utility library (`slugify`, `word_frequencies`,
`parse_key_values`). Contributors keep breaking it: a pull request passes on their laptop
with Python 3.13 and fails for users on 3.11; another one quietly deletes half the tests.
Your job is to put a **continuous integration (CI) pipeline** in front of the main branch:
every push and pull request is linted, tested on four Python versions and rejected if test
coverage drops below 90%.

## What you build

1. The library itself, so there is something worth protecting (milestone 1).
2. A GitHub Actions workflow, `.github/workflows/ci.yml` (milestones 2-4):
   triggers, least-privilege permissions, concurrency, a lint job, a test job on a Python
   version matrix, and a coverage gate.

## Where the workflow lives (important)

GitHub only runs workflows stored in `.github/workflows/` **at the root of a repository**.
This kit lives inside the Groundwork repository, so nothing here is executed by GitHub:

| File | Role |
|---|---|
| `starter/.github/workflows/ci.yml` | **your** workflow (a skeleton with TODOs) |
| `.github/workflows/ci.yml` | the reference workflow (what `GW_TARGET=solution` checks) |

The tests read the workflow file and check its structure with a tiny YAML-subset reader
defined in `tests/test_ci_textkit.py` (no PyYAML needed). They cannot *run* the workflow:
that only happens on GitHub. To see it run for real, see "Run it on GitHub" below.

## Setup

Windows (PowerShell):

```powershell
cd projects/ci-pipeline
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

macOS / Linux:

```bash
cd projects/ci-pipeline
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

`requirements-dev.txt` holds the tools CI installs (pytest, pytest-cov, ruff). The library
itself uses only the standard library. Python 3.11 or newer is required.

## Running the tests

```powershell
python -m pytest                 # all milestones, against starter/
python -m pytest -k Milestone1   # one milestone at a time
$env:GW_TARGET="solution"; python -m pytest; Remove-Item Env:GW_TARGET   # the reference
```

```bash
python -m pytest
python -m pytest -k Milestone1
GW_TARGET=solution python -m pytest
```

Run the same checks CI runs (coverage needs `pytest-cov` from `requirements-dev.txt`):

```bash
ruff check .
ruff format --check .
python -m pytest --cov=ci_textkit --cov-report=term-missing --cov-fail-under=90
```

`ruff.toml` in this folder holds the lint rules, so your machine and CI agree.

## Milestones

1. **The library under test** (`TestMilestone1Library`) - implement the three functions in
   `starter/ci_textkit.py` from their docstrings: accents stripped and word-boundary
   shortening in `slugify`, deterministic tie-breaking in `word_frequencies`, line-numbered
   `KeyValueError`s in `parse_key_values`.
2. **Triggers, permissions, concurrency** (`TestMilestone2Triggers`) - run on `push` and
   `pull_request` (never `pull_request_target`), `permissions: contents: read`, and a
   `concurrency` group that cancels superseded runs.
3. **A matrix job** (`TestMilestone3MatrixJob`) - `runs-on` and `timeout-minutes` on every
   job, a `fail-fast: false` matrix of quoted Python versions (`"3.11"` to `"3.14"`),
   `actions/checkout` and `actions/setup-python` pinned to a version, pip caching, install
   from `requirements-dev.txt`, and `ruff check`.
4. **Quality gates** (`TestMilestone4QualityGates`) - pytest with
   `--cov=ci_textkit --cov-fail-under=90`, tests only after lint passes (`needs: lint` or an
   earlier step), no `${{ secrets.* }}` and no `${{ github.event.* }}` interpolated into
   `run:` commands, version ranges in `requirements-dev.txt`.
5. **Run it on GitHub** (manual, no automated test) - see below. Break the build on purpose
   (delete a test so coverage drops, add an unused import) and watch it go red.

## Run it on GitHub (optional, needs a free GitHub account)

1. Copy this folder somewhere outside Groundwork and make it a repository root.
2. Replace `.github/workflows/ci.yml` with your `starter/.github/workflows/ci.yml`.
3. `git init`, commit, create an empty GitHub repository and push to `main`.
4. Open the **Actions** tab. Tests run against `starter/` (your code) because that is the
   default `conftest.py` target.

## Layout

```
ci-pipeline/
  .github/workflows/ci.yml          reference workflow (kit root = repository root)
  conftest.py                       selects starter/ or solution/; workflow_path fixture
  requirements-dev.txt              pytest, pytest-cov, ruff
  ruff.toml                         lint/format rules used locally and in CI
  starter/ci_textkit.py             your library (TODOs)
  starter/.github/workflows/ci.yml  your workflow (TODOs)
  solution/ci_textkit.py            reference library
  tests/test_ci_textkit.py          library tests + workflow structure checks
```
