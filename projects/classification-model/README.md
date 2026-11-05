# Classification model without leakage

Train a classifier the way you would at work: seeded, stratified train/validation/test splits; a
scikit-learn `Pipeline` that owns its preprocessing; a baseline to beat; precision, recall, F1 and
ROC-AUC; model selection on the validation split only; and a single look at the held-out test set.

```text
load_data ─► split_data ─► train ──► Pipeline(StandardScaler → LogisticRegression).fit
                         ├► val   ──► compare_models / select_c   (choose C here)
                         └► test  ──► final_report                 (look once, at the end)
```

## Dataset

scikit-learn's bundled **Breast Cancer Wisconsin (Diagnostic)** dataset (`load_breast_cancer`, no
download): 569 tumours, 30 numeric features computed from digitised images of fine-needle aspirates,
212 malignant and 357 benign.

**Licence and limitations.** The data comes from the UCI Machine Learning Repository (W. Wolberg,
W. Street, O. Mangasarian, 1995), licensed CC BY 4.0; scikit-learn itself is BSD-3-Clause. It is
small, old, from one institution, and the features are already engineered, so scores are much higher
than you should expect on real clinical data. It is a teaching dataset — never use a model trained
here for medical decisions.

## Setup

Windows (PowerShell):

```powershell
cd projects/classification-model
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

macOS / Linux:

```bash
cd projects/classification-model
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Running the tests

```bash
python -m pytest                     # your code in starter/
python -m pytest -k Milestone4       # one milestone
```

Against the reference solution:

```powershell
$env:GW_TARGET="solution"; python -m pytest; Remove-Item Env:GW_TARGET   # Windows PowerShell
```

```bash
GW_TARGET=solution python -m pytest                                      # macOS / Linux
```

Run the whole workflow: `python starter/classification_model.py`.

## Milestones

Work in `starter/classification_model.py`.

1. **Data and splits** — `load_data` (make *malignant* the positive class) and `split_data`
   (seeded, stratified, disjoint train/validation/test; sizes are fractions of the whole dataset).
2. **Pipeline and baseline** — `build_pipeline(C)` (scaler + logistic regression) and
   `build_baseline()` (`DummyClassifier(strategy="prior")`).
3. **Metrics and comparison** — `evaluate` (accuracy, precision, recall, F1, ROC-AUC at a threshold)
   and `compare_models` (fit clones on train, score on validation).
4. **No leakage, then the quality bar** — `select_c` (validation only), `train_final`,
   `final_report`. Tests prove the scaler's means are the training means, that poisoning the test
   split does not change model selection, and that the held-out test set clears ROC-AUC ≥ 0.97,
   F1 ≥ 0.92 and recall ≥ 0.90 while the baseline sits at ROC-AUC 0.5.
