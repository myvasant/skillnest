# Model evaluation app: slices, fairness, calibration and cost

Evaluate a saved classifier the way a model review board would: load it safely, break performance
down by group, measure fairness gaps, check calibration, choose the decision threshold from the real
costs of mistakes, and write it all up as a Markdown report.

```text
model.pkl + model.pkl.sha256 ─► load_model (verify SHA-256, then unpickle)
validation ─► select_threshold(cost_fp, cost_fn) ─► threshold
test ─► slice_metrics / fairness_gaps / confusion_matrices   (at that threshold)
     ─► calibration_table / brier_score / ECE / calibration_by_group
     ─► EvaluationResult ─► render_report ─► report.md
```

## The data

`make_applicants(n_rows=6000, seed=0)` (provided) generates a synthetic loan book: `income`,
`debt_ratio`, `years_employed`, `prior_defaults`, a `group` column (`A` 70%, `B` 30%) and the label
`default`. Group B has lower incomes **and** an extra risk none of the features capture. The provided
`train_reference_model` never sees the group — yet, as you will measure, it flags group B far more
often and under-predicts B's risk while over-predicting A's.

**Licence and limitations.** The data is generated in code by this project; there is no real person
behind any row and the groups stand for any protected attribute. Effects were chosen to make problems
visible, not to describe any real lending population. Exact numbers may differ slightly between
library versions; the tests check the patterns.

## Setup

Windows (PowerShell):

```powershell
cd projects/model-evaluation-app
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

macOS / Linux:

```bash
cd projects/model-evaluation-app
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
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

Produce a model and a report: `python starter/model_evaluation.py --out-dir evaluation --cost-fn 5`.

## Security note: pickle

`pickle.loads` can execute arbitrary code embedded in the file. **Only load models you trust.** The
SHA-256 check detects a file that changed after its digest was recorded (corruption or tampering);
it does not make an untrusted file safe, and an attacker who can rewrite both the model and its
`.sha256` file defeats it — keep trusted digests somewhere the model's author cannot edit (a model
registry or a signed manifest). Hash and unpickle the *same bytes* so the file cannot change between
the check and the load.

## Milestones

Work in `starter/model_evaluation.py`.

1. **Save and load safely** — `save_model` (pickle + `.sha256` sidecar) and `load_model` (refuse to
   unpickle without a matching digest).
2. **Slices and fairness** — `confusion_counts`, `rates`, `slice_metrics`, `confusion_matrices`,
   `fairness_gaps` (demographic parity, disparate impact, equal opportunity, equalized odds).
3. **Calibration** — `calibration_table`, `brier_score`, `expected_calibration_error`,
   `calibration_by_group`.
4. **Threshold by cost** — `expected_cost`, `cost_curve`, `select_threshold`, `bayes_threshold`.
5. **The report** — `evaluate_saved_model` (threshold from validation, metrics on test),
   `render_report`, `write_report`.
