# Reproducible experiment runner

Build a small experiment runner that makes ML results repeatable and comparable: a TOML config, fixed
and derived seeds, a run folder with `params.json`, `metrics.json`, `meta.json` and artefacts, and a
comparison report across runs. MLflow is an optional extra.

```text
experiment.toml ─► load_config ─► train_and_evaluate (seeded split, CV, fit, test)
                                         │
                       run_experiment ───┴─► runs/<name>-<hash8>/
                                               params.json  metrics.json  meta.json
                                               artefacts/predictions.csv  confusion_matrix.json  run.log
runs/ ─► load_runs ─► compare_runs ─► comparison_report (Markdown)
```

## Datasets

* `breast_cancer` — scikit-learn's bundled Breast Cancer Wisconsin (Diagnostic) data (569 rows, 30
  features; no download). Source: UCI Machine Learning Repository (Wolberg, Street, Mangasarian,
  1995), licensed CC BY 4.0. Small, old and single-source: fine for practising experiment tracking,
  not for medical conclusions.
* `synthetic` — `sklearn.datasets.make_classification` (600 rows, 12 features) generated from a seed
  derived from the config. No personal data; its difficulty is set by the generator, so scores say
  nothing about real problems. scikit-learn is BSD-3-Clause licensed.

## Setup

Windows (PowerShell):

```powershell
cd projects/reproducible-experiment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

macOS / Linux:

```bash
cd projects/reproducible-experiment
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### Optional: MLflow

Milestone 5 mirrors runs into [MLflow](https://mlflow.org/). It is **optional**: the core project and
the default test run work without it, and its test is skipped (`pytest.importorskip("mlflow")`) when
MLflow is not installed. MLflow is a large install (~100 MB with dependencies); to try it:

```bash
python -m pip install mlflow
python -m pytest -k Mlflow
mlflow ui --backend-store-uri ./mlruns    # browse runs at http://127.0.0.1:5000 (local only)
```

## Running the tests

```bash
python -m pytest                     # your code in starter/
python -m pytest -k Milestone3       # one milestone
```

Against the reference solution:

```powershell
$env:GW_TARGET="solution"; python -m pytest; Remove-Item Env:GW_TARGET   # Windows PowerShell
```

```bash
GW_TARGET=solution python -m pytest                                      # macOS / Linux
```

Use the CLI once your code passes:

```bash
python starter/experiment_runner.py run experiment.toml --runs-dir runs
python starter/experiment_runner.py run experiment.toml --runs-dir runs --seed 7
python starter/experiment_runner.py compare --runs-dir runs --metric test_roc_auc
```

Running the same config twice into the same folder fails on purpose (`FileExistsError`): results are
never silently replaced. Use `--overwrite` if you mean it.

## Milestones

Work in `starter/experiment_runner.py`.

1. **Config** — `config_from_dict` (reject unknown keys), `validate_config`, `load_config` (stdlib
   `tomllib`), `config_to_dict`, `config_hash` (SHA-256 of canonical JSON), `make_run_id`,
   `with_overrides`.
2. **Seeds and deterministic training** — `derive_seed`, `build_model`, `train_and_evaluate`
   (identical configs give identical metrics to the last digit).
3. **Tracking** — `start_run`, `log_params`, `log_metrics`, `log_artefact` (no path traversal),
   `run_experiment` (an injected `clock`, never the wall clock), `sweep`.
4. **Comparison** — `flatten`, `load_runs`, `compare_runs`, `varying_columns`, `comparison_report`.
5. **Optional: MLflow** — `log_to_mlflow` imports MLflow only inside the function.
