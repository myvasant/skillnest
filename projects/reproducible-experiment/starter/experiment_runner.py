"""A small, reproducible experiment runner with local JSON tracking (starter).

An experiment is described by a TOML config. Running it trains and evaluates a scikit-learn model with
fixed seeds and writes everything needed to trust, repeat and compare the result into a run folder::

    runs/<run_id>/
      params.json      the resolved config and its hash
      metrics.json     cross-validation and test metrics
      meta.json        run id, config hash, library versions (and a start time only if you inject one)
      artefacts/       predictions.csv, confusion_matrix.json, run.log

Command line::

    python solution/experiment_runner.py run experiment.toml --runs-dir runs
    python solution/experiment_runner.py compare --runs-dir runs --metric test_roc_auc

MLflow is optional: :func:`log_to_mlflow` imports it only when called.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import sklearn
from sklearn.base import ClassifierMixin
from sklearn.datasets import load_breast_cancer, make_classification
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, log_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

DATASETS: tuple[str, ...] = ("breast_cancer", "synthetic")
MODELS: tuple[str, ...] = ("logistic_regression", "random_forest")
TOP_LEVEL_KEYS: frozenset[str] = frozenset({"name", "seed", "data", "model", "evaluation"})
DATA_KEYS: frozenset[str] = frozenset({"dataset", "test_size"})
EVALUATION_KEYS: frozenset[str] = frozenset({"cv_folds"})


# ---------------------------------------------------------------------------
# Milestone 1: configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExperimentConfig:
    """Everything that determines a run's result. Two equal configs must give equal metrics."""

    name: str
    seed: int
    dataset: str = "breast_cancer"
    test_size: float = 0.25
    cv_folds: int = 5
    model: str = "logistic_regression"
    params: dict[str, Any] = field(default_factory=dict)


def config_from_dict(raw: Mapping[str, Any]) -> ExperimentConfig:
    """Build and validate a config from the nested TOML structure.

    Expected shape: top-level ``name`` and ``seed``; tables ``[data]`` (``dataset``, ``test_size``),
    ``[model]`` (``type`` plus estimator parameters) and ``[evaluation]`` (``cv_folds``).

    Raises:
        ValueError: on unknown keys (a typo must not be silently ignored), missing ``name``/``seed``,
            or out-of-range values.
    """
    # TODO: reject unknown keys with _reject_unknown() at the top level, in [data] and in [evaluation].
    # TODO: require name and seed; copy the [model] table, pop its "type" (default logistic_regression);
    #   the remaining [model] keys are the estimator params.
    # TODO: build ExperimentConfig(...) with the defaults from the dataclass, call validate_config, return
    #   it.
    raise NotImplementedError("TODO: implement config_from_dict()")


def validate_config(config: ExperimentConfig) -> None:
    """Raise ``ValueError`` with a precise message if any field is invalid."""
    # TODO: name: re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name) — it becomes a folder name.
    # TODO: seed: a non-negative int (and not a bool); dataset in DATASETS; 0 < test_size < 1;
    #   cv_folds an int >= 2; model in MODELS. Raise ValueError naming the field and the bad value.
    raise NotImplementedError("TODO: implement validate_config()")


def load_config(path: Path | str) -> ExperimentConfig:
    """Read a TOML config file (stdlib ``tomllib``) and validate it."""
    # TODO: open the file in binary mode and use tomllib.load, then config_from_dict.
    raise NotImplementedError("TODO: implement load_config()")


def config_to_dict(config: ExperimentConfig) -> dict[str, Any]:
    """The config in the same nested shape as the TOML file (round-trips with :func:`config_from_dict`)."""
    # TODO: return the nested TOML shape: name, seed, data{dataset, test_size},
    #   model{type, **params sorted by key}, evaluation{cv_folds}.
    raise NotImplementedError("TODO: implement config_to_dict()")


def config_hash(config: ExperimentConfig) -> str:
    """SHA-256 of the canonical JSON of the config (sorted keys, no spaces): 64 hex characters.

    Equal configs give equal hashes regardless of key order in the file.
    """
    # TODO: json.dumps(config_to_dict(config), sort_keys=True, separators=(",", ":")),
    #   then hashlib.sha256(text.encode("utf-8")).hexdigest().
    raise NotImplementedError("TODO: implement config_hash()")


def make_run_id(config: ExperimentConfig) -> str:
    """A deterministic run id: ``<name>-<first 8 hex chars of the config hash>``."""
    # TODO: f"{config.name}-{config_hash(config)[:8]}" — deterministic, never a timestamp.
    raise NotImplementedError("TODO: implement make_run_id()")


def with_overrides(config: ExperimentConfig, overrides: Mapping[str, Any]) -> ExperimentConfig:
    """Return a copy with some fields changed; ``"params.C"`` changes one model parameter.

    Raises:
        ValueError: for unknown fields; the result is validated like any config.
    """
    # TODO: keys starting with "params." change one model parameter (copy config.params first!);
    #   other keys must be dataclass fields (ExperimentConfig.__dataclass_fields__), else ValueError.
    # TODO: use dataclasses.replace, then validate_config on the result.
    raise NotImplementedError("TODO: implement with_overrides()")


def _reject_unknown(section: Mapping[str, Any], allowed: frozenset[str], where: str) -> None:
    unknown = sorted(set(section) - allowed)
    if unknown:
        raise ValueError(f"unknown key(s) {unknown} at {where}; allowed: {sorted(allowed)}")


# ---------------------------------------------------------------------------
# Milestone 2: seeds, data, model and a deterministic evaluation
# ---------------------------------------------------------------------------


def derive_seed(seed: int, label: str) -> int:
    """Derive an independent, reproducible seed for one component (``"split"``, ``"cv"``, ``"model"``).

    ``int(sha256(f"{seed}:{label}").hexdigest()[:8], 16)`` — the same inputs always give the same
    seed, and changing how one component is seeded does not shift the others.
    """
    # TODO: int(hashlib.sha256(f"{seed}:{label}".encode()).hexdigest()[:8], 16).
    raise NotImplementedError("TODO: implement derive_seed()")


def load_dataset(config: ExperimentConfig) -> tuple[pd.DataFrame, pd.Series]:
    """Load the configured dataset as ``(X, y)`` with a binary 0/1 target.

    ``breast_cancer`` is bundled with scikit-learn; ``synthetic`` is generated by
    ``make_classification`` from a seed derived from ``config.seed``.
    """
    if config.dataset == "breast_cancer":
        data = load_breast_cancer(as_frame=True)
        return data.data.copy(), data.target.astype("int64").rename("target")
    X, y = make_classification(
        n_samples=600,
        n_features=12,
        n_informative=5,
        n_redundant=2,
        class_sep=1.0,
        random_state=derive_seed(config.seed, "data"),
    )
    columns = [f"f{i}" for i in range(X.shape[1])]
    return pd.DataFrame(X, columns=columns), pd.Series(y, name="target", dtype="int64")


def build_model(config: ExperimentConfig) -> ClassifierMixin:
    """Create the configured estimator with its seed fixed.

    Raises:
        ValueError: if ``config.params`` contains a parameter the estimator does not accept.
    """
    # TODO: seed = derive_seed(config.seed, "model").
    # TODO: logistic_regression: Pipeline([("scaler", StandardScaler()), ("model", LogisticRegression(
    #   max_iter=5000, random_state=seed))]); params are set with the "model__" prefix.
    # TODO: random_forest: RandomForestClassifier(n_estimators=100, n_jobs=1, random_state=seed).
    # TODO: raise ValueError for params the estimator does not have (compare with estimator.get_params()),
    #   then model.set_params(...).
    raise NotImplementedError("TODO: implement build_model()")


@dataclass(frozen=True)
class Outcome:
    """What one training run produced (before anything is written to disk)."""

    metrics: dict[str, float]
    predictions: pd.DataFrame
    confusion: list[list[int]]
    events: tuple[str, ...]


def train_and_evaluate(config: ExperimentConfig) -> Outcome:
    """Split, cross-validate on train, fit on train, evaluate on test — all seeded from the config.

    Returns:
        Metrics ``cv_roc_auc_mean``, ``cv_roc_auc_std``, ``test_accuracy``, ``test_f1``,
        ``test_roc_auc``, ``test_log_loss``; a predictions table (``row, y_true, y_score, y_pred``);
        the test confusion matrix; and human-readable events for ``run.log``.
    """
    # TODO: load_dataset; train_test_split(stratify=y, random_state=derive_seed(seed, "split")).
    # TODO: cross_val_score(build_model(config), X_train, y_train, scoring="roc_auc",
    #   cv=StratifiedKFold(config.cv_folds, shuffle=True, random_state=derive_seed(seed, "cv"))).
    # TODO: fit a fresh build_model on train; scores = predict_proba(X_test)[:, 1]; pred = scores >= 0.5.
    # TODO: metrics (plain floats): cv_roc_auc_mean, cv_roc_auc_std (np.std), test_accuracy, test_f1,
    #   test_roc_auc, test_log_loss. predictions columns: row (X_test index), y_true, y_score, y_pred.
    # TODO: confusion = confusion_matrix(y_test, pred).tolist(); events = a few lines for run.log
    #   (no timestamps!). Return Outcome(metrics, predictions, confusion, events).
    raise NotImplementedError("TODO: implement train_and_evaluate()")


# ---------------------------------------------------------------------------
# Milestone 3: tracking — params, metrics and artefacts in a run folder
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunResult:
    """A finished, tracked run."""

    run_id: str
    run_dir: Path
    params: dict[str, Any]
    metrics: dict[str, float]


def environment_info() -> dict[str, str]:
    """Versions that can change results: Python, platform and the numeric libraries."""
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit-learn": sklearn.__version__,
    }


def write_json(path: Path, data: Any) -> Path:
    """Write ``data`` as stable, human-readable JSON (sorted keys, 2-space indent, trailing newline)."""
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def start_run(runs_dir: Path | str, run_id: str, overwrite: bool = False) -> Path:
    """Create ``runs_dir/run_id`` and its ``artefacts`` folder.

    Raises:
        ValueError: if ``run_id`` is not a plain folder name (no separators or ``..``).
        FileExistsError: if the run exists and ``overwrite`` is False — results are never silently
            replaced.
    """
    # TODO: validate run_id with the same pattern as names (and no "..") -> ValueError.
    # TODO: raise FileExistsError if runs_dir/run_id exists and not overwrite.
    # TODO: create run_dir/"artefacts" (parents=True, exist_ok=True) and return run_dir.
    raise NotImplementedError("TODO: implement start_run()")


def log_params(run_dir: Path, config: ExperimentConfig) -> Path:
    """Write ``params.json``: the nested config plus its hash."""
    # TODO: write_json(run_dir / "params.json", {"config": config_to_dict(config), "config_hash": ...}).
    raise NotImplementedError("TODO: implement log_params()")


def log_metrics(run_dir: Path, metrics: Mapping[str, float]) -> Path:
    """Write ``metrics.json``. Values must be finite numbers."""
    # TODO: raise ValueError for values that are not finite numbers (np.isfinite);
    # TODO: write_json(run_dir / "metrics.json", {name: float(value)}).
    raise NotImplementedError("TODO: implement log_metrics()")


def log_artefact(run_dir: Path, name: str, content: str | bytes | pd.DataFrame | dict | list) -> Path:
    """Save one artefact under ``artefacts/``: text, bytes, a DataFrame (CSV) or JSON-able data.

    Raises:
        ValueError: if ``name`` is not a plain file name — ``"../params.json"`` must not escape the
            artefacts folder.
    """
    # TODO: reject names that are empty, contain a path (Path(name).name != name, or a backslash) or start
    #   with ".".
    # TODO: DataFrame -> CSV (index=False, lineterminator="\n"); bytes -> write_bytes; str -> write_text;
    #   anything else -> write_json.
    raise NotImplementedError("TODO: implement log_artefact()")


def run_experiment(
    config: ExperimentConfig,
    runs_dir: Path | str,
    run_id: str | None = None,
    overwrite: bool = False,
    clock: Callable[[], str] | None = None,
) -> RunResult:
    """Train, evaluate and track one run.

    Args:
        config: The experiment.
        runs_dir: Parent folder for run folders.
        run_id: Defaults to :func:`make_run_id` (deterministic).
        overwrite: Replace an existing run folder with the same id.
        clock: Optional function returning a timestamp string for ``meta.json``. Injected rather than
            read from the wall clock so tests (and reruns) stay deterministic.
    """
    # TODO: rid = run_id or make_run_id(config); outcome = train_and_evaluate(config);
    # TODO: run_dir = start_run(...); log params, metrics and the three artefacts
    #   (predictions.csv, confusion_matrix.json, run.log);
    # TODO: meta.json: run_id, config_hash, environment_info(), and started_at = clock() ONLY if clock is
    #   given.
    # TODO: return RunResult(rid, run_dir, config_to_dict(config), outcome.metrics).
    raise NotImplementedError("TODO: implement run_experiment()")


def sweep(
    base: ExperimentConfig, overrides: Sequence[Mapping[str, Any]], runs_dir: Path | str
) -> list[RunResult]:
    """Run ``base`` once per override set (for example several seeds or values of C)."""
    # TODO: one run_experiment(with_overrides(base, o), runs_dir) per override mapping.
    raise NotImplementedError("TODO: implement sweep()")


# ---------------------------------------------------------------------------
# Milestone 4: compare runs
# ---------------------------------------------------------------------------


def flatten(data: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten nested dicts with dotted keys: ``{"model": {"C": 1}} -> {"model.C": 1}``."""
    # TODO: recursive: nested Mappings become dotted keys; other values are copied as they are.
    raise NotImplementedError("TODO: implement flatten()")


def load_runs(runs_dir: Path | str) -> pd.DataFrame:
    """One row per run folder that has ``params.json`` and ``metrics.json``.

    Columns: ``run_id``, the flattened config (``name``, ``seed``, ``data.dataset``, ``model.type``,
    ``model.C`` ...) and every metric. Sorted by ``run_id``; folders without both files are skipped.
    """
    # TODO: for each sub-folder (sorted) that has params.json AND metrics.json:
    #   row = {"run_id": folder name, **flatten(params["config"]), **metrics}.
    # TODO: return pd.DataFrame(rows).
    raise NotImplementedError("TODO: implement load_runs()")


def compare_runs(
    runs_dir: Path | str, metric: str = "test_roc_auc", higher_is_better: bool = True
) -> pd.DataFrame:
    """Load runs and sort them by ``metric`` (best first, ties by ``run_id``).

    Raises:
        ValueError: if there are no runs or no run has the metric.
    """
    # TODO: ValueError if there are no runs or the metric column is missing.
    # TODO: sort by [metric, run_id] (best first) and reset the index.
    raise NotImplementedError("TODO: implement compare_runs()")


def varying_columns(runs: pd.DataFrame) -> list[str]:
    """Config columns whose value differs between runs — what the comparison is really about."""
    # TODO: config columns are "name", "seed" and dotted names; keep those with more than one distinct value
    #   (compare as strings so mixed types and NaN work).
    raise NotImplementedError("TODO: implement varying_columns()")


def comparison_report(runs: pd.DataFrame, metric: str = "test_roc_auc") -> str:
    """A Markdown report: what varied, a table of runs (best first) and the best run."""
    # TODO: ValueError for an empty table. Lines: "# Experiment comparison", a sentence naming the varying
    #   settings in backticks, a Markdown table (run_id, varying columns, cv_*/test_* metrics; floats
    #   with 4 decimals), then "**Best run:** `<run_id>` with <metric> = <value>.".
    raise NotImplementedError("TODO: implement comparison_report()")


# ---------------------------------------------------------------------------
# Milestone 5 (optional): MLflow
# ---------------------------------------------------------------------------


def log_to_mlflow(result: RunResult, tracking_uri: str, experiment_name: str | None = None) -> str:
    """Mirror a tracked run into MLflow (optional dependency, imported only here).

    Logs flattened params, metrics and the run's artefacts folder, tagged with our run id.

    Returns:
        The MLflow run id.

    Raises:
        ModuleNotFoundError: with install instructions if MLflow is not installed.
    """
    # TODO: OPTIONAL (the test is skipped unless mlflow is installed). Import mlflow inside this function.
    # TODO: mlflow.set_tracking_uri(tracking_uri); mlflow.set_experiment(experiment_name or the config
    #   name).
    # TODO: inside `with mlflow.start_run(run_name=result.run_id) as active:` call
    #   set_tag("groundwork.run_id", ...),
    #   log_params(flatten(result.params)), log_metrics(result.metrics) and
    #   log_artifacts(str(result.run_dir / "artefacts")).
    # TODO: return active.info.run_id.
    raise NotImplementedError("TODO: implement log_to_mlflow()")


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    """``run <config.toml>`` or ``compare`` from the command line."""
    parser = argparse.ArgumentParser(description="Reproducible experiment runner")
    sub = parser.add_subparsers(dest="command", required=True)
    run_p = sub.add_parser("run", help="run one experiment from a TOML config")
    run_p.add_argument("config", type=Path)
    run_p.add_argument("--runs-dir", type=Path, default=Path("runs"))
    run_p.add_argument("--seed", type=int, help="override the config's seed")
    run_p.add_argument("--overwrite", action="store_true")
    cmp_p = sub.add_parser("compare", help="compare all runs in a folder")
    cmp_p.add_argument("--runs-dir", type=Path, default=Path("runs"))
    cmp_p.add_argument("--metric", default="test_roc_auc")
    args = parser.parse_args(argv)
    if args.command == "run":
        config = load_config(args.config)
        if args.seed is not None:
            config = with_overrides(config, {"seed": args.seed})
        try:
            result = run_experiment(config, args.runs_dir, overwrite=args.overwrite)
        except FileExistsError as exc:
            print(f"error: {exc}")
            return 1
        print(f"{result.run_id}: " + ", ".join(f"{k}={v:.4f}" for k, v in result.metrics.items()))
    else:
        print(comparison_report(compare_runs(args.runs_dir, args.metric), args.metric))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
