"""A small, reproducible experiment runner with local JSON tracking (reference solution).

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
    _reject_unknown(raw, TOP_LEVEL_KEYS, "top level")
    if "name" not in raw or "seed" not in raw:
        raise ValueError("config needs 'name' and 'seed'")
    data = dict(raw.get("data", {}))
    model = dict(raw.get("model", {}))
    evaluation = dict(raw.get("evaluation", {}))
    _reject_unknown(data, DATA_KEYS, "[data]")
    _reject_unknown(evaluation, EVALUATION_KEYS, "[evaluation]")
    model_type = model.pop("type", "logistic_regression")
    config = ExperimentConfig(
        name=str(raw["name"]),
        seed=raw["seed"],
        dataset=data.get("dataset", "breast_cancer"),
        test_size=data.get("test_size", 0.25),
        cv_folds=evaluation.get("cv_folds", 5),
        model=model_type,
        params=model,
    )
    validate_config(config)
    return config


def validate_config(config: ExperimentConfig) -> None:
    """Raise ``ValueError`` with a precise message if any field is invalid."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", config.name):
        raise ValueError(
            f"name {config.name!r}: use letters, digits, '.', '_' or '-' (it becomes a folder name)"
        )
    if not isinstance(config.seed, int) or isinstance(config.seed, bool) or config.seed < 0:
        raise ValueError(f"seed must be a non-negative integer, got {config.seed!r}")
    if config.dataset not in DATASETS:
        raise ValueError(f"dataset must be one of {DATASETS}, got {config.dataset!r}")
    if not 0 < config.test_size < 1:
        raise ValueError(f"test_size must be between 0 and 1, got {config.test_size}")
    if not isinstance(config.cv_folds, int) or config.cv_folds < 2:
        raise ValueError(f"cv_folds must be an integer >= 2, got {config.cv_folds!r}")
    if config.model not in MODELS:
        raise ValueError(f"model type must be one of {MODELS}, got {config.model!r}")


def load_config(path: Path | str) -> ExperimentConfig:
    """Read a TOML config file (stdlib ``tomllib``) and validate it."""
    with Path(path).open("rb") as fh:
        return config_from_dict(tomllib.load(fh))


def config_to_dict(config: ExperimentConfig) -> dict[str, Any]:
    """The config in the same nested shape as the TOML file (round-trips with :func:`config_from_dict`)."""
    return {
        "name": config.name,
        "seed": config.seed,
        "data": {"dataset": config.dataset, "test_size": config.test_size},
        "model": {"type": config.model, **dict(sorted(config.params.items()))},
        "evaluation": {"cv_folds": config.cv_folds},
    }


def config_hash(config: ExperimentConfig) -> str:
    """SHA-256 of the canonical JSON of the config (sorted keys, no spaces): 64 hex characters.

    Equal configs give equal hashes regardless of key order in the file.
    """
    canonical = json.dumps(config_to_dict(config), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def make_run_id(config: ExperimentConfig) -> str:
    """A deterministic run id: ``<name>-<first 8 hex chars of the config hash>``."""
    return f"{config.name}-{config_hash(config)[:8]}"


def with_overrides(config: ExperimentConfig, overrides: Mapping[str, Any]) -> ExperimentConfig:
    """Return a copy with some fields changed; ``"params.C"`` changes one model parameter.

    Raises:
        ValueError: for unknown fields; the result is validated like any config.
    """
    changes: dict[str, Any] = {}
    params = dict(config.params)
    for key, value in overrides.items():
        if key.startswith("params."):
            params[key.removeprefix("params.")] = value
        elif key in ExperimentConfig.__dataclass_fields__ and key != "params":
            changes[key] = value
        else:
            raise ValueError(f"unknown config field {key!r}")
    new = replace(config, **changes, params=params)
    validate_config(new)
    return new


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
    return int(hashlib.sha256(f"{seed}:{label}".encode()).hexdigest()[:8], 16)


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
    seed = derive_seed(config.seed, "model")
    if config.model == "logistic_regression":
        estimator: Any = LogisticRegression(max_iter=5000, random_state=seed)
        prefix = "model__"
        model: Any = Pipeline([("scaler", StandardScaler()), ("model", estimator)])
    else:
        estimator = RandomForestClassifier(n_estimators=100, n_jobs=1, random_state=seed)
        prefix = ""
        model = estimator
    unknown = sorted(set(config.params) - set(estimator.get_params()))
    if unknown:
        raise ValueError(f"{config.model} does not accept parameter(s) {unknown}")
    return model.set_params(**{prefix + k: v for k, v in config.params.items()})


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
    validate_config(config)
    X, y = load_dataset(config)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=config.test_size, stratify=y, random_state=derive_seed(config.seed, "split")
    )
    folds = StratifiedKFold(
        n_splits=config.cv_folds, shuffle=True, random_state=derive_seed(config.seed, "cv")
    )
    cv_scores = cross_val_score(build_model(config), X_train, y_train, cv=folds, scoring="roc_auc")
    model = build_model(config).fit(X_train, y_train)
    scores = model.predict_proba(X_test)[:, 1]
    pred = (scores >= 0.5).astype(int)
    metrics = {
        "cv_roc_auc_mean": float(np.mean(cv_scores)),
        "cv_roc_auc_std": float(np.std(cv_scores)),
        "test_accuracy": float(accuracy_score(y_test, pred)),
        "test_f1": float(f1_score(y_test, pred)),
        "test_roc_auc": float(roc_auc_score(y_test, scores)),
        "test_log_loss": float(log_loss(y_test, scores)),
    }
    predictions = pd.DataFrame(
        {"row": X_test.index.to_numpy(), "y_true": y_test.to_numpy(), "y_score": scores, "y_pred": pred}
    )
    events = (
        f"dataset {config.dataset}: {len(X)} rows, {X.shape[1]} features",
        f"split: {len(X_train)} train / {len(X_test)} test (seed {derive_seed(config.seed, 'split')})",
        f"cv: {config.cv_folds} folds, roc_auc {metrics['cv_roc_auc_mean']:.4f}"
        f" +/- {metrics['cv_roc_auc_std']:.4f}",
        f"test: roc_auc {metrics['test_roc_auc']:.4f}, f1 {metrics['test_f1']:.4f}",
    )
    return Outcome(metrics, predictions, confusion_matrix(y_test, pred).tolist(), events)


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
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", run_id) or ".." in run_id:
        raise ValueError(f"run id {run_id!r} must be a plain folder name")
    run_dir = Path(runs_dir) / run_id
    if run_dir.exists() and not overwrite:
        raise FileExistsError(
            f"run {run_id!r} already exists in {runs_dir}; pass overwrite=True to replace it"
        )
    (run_dir / "artefacts").mkdir(parents=True, exist_ok=True)
    return run_dir


def log_params(run_dir: Path, config: ExperimentConfig) -> Path:
    """Write ``params.json``: the nested config plus its hash."""
    return write_json(
        run_dir / "params.json", {"config": config_to_dict(config), "config_hash": config_hash(config)}
    )


def log_metrics(run_dir: Path, metrics: Mapping[str, float]) -> Path:
    """Write ``metrics.json``. Values must be finite numbers."""
    for key, value in metrics.items():
        if not isinstance(value, int | float) or not np.isfinite(value):
            raise ValueError(f"metric {key!r} must be a finite number, got {value!r}")
    return write_json(run_dir / "metrics.json", {k: float(v) for k, v in metrics.items()})


def log_artefact(run_dir: Path, name: str, content: str | bytes | pd.DataFrame | dict | list) -> Path:
    """Save one artefact under ``artefacts/``: text, bytes, a DataFrame (CSV) or JSON-able data.

    Raises:
        ValueError: if ``name`` is not a plain file name — ``"../params.json"`` must not escape the
            artefacts folder.
    """
    if not name or Path(name).name != name or name.startswith(".") or "\\" in name:
        raise ValueError(f"artefact name {name!r} must be a plain file name")
    path = run_dir / "artefacts" / name
    if isinstance(content, pd.DataFrame):
        content.to_csv(path, index=False, lineterminator="\n")
    elif isinstance(content, bytes):
        path.write_bytes(content)
    elif isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        write_json(path, content)
    return path


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
    rid = run_id or make_run_id(config)
    outcome = train_and_evaluate(config)
    run_dir = start_run(runs_dir, rid, overwrite=overwrite)
    log_params(run_dir, config)
    log_metrics(run_dir, outcome.metrics)
    log_artefact(run_dir, "predictions.csv", outcome.predictions)
    log_artefact(run_dir, "confusion_matrix.json", outcome.confusion)
    log_artefact(run_dir, "run.log", "\n".join(outcome.events) + "\n")
    meta: dict[str, Any] = {
        "run_id": rid,
        "config_hash": config_hash(config),
        "environment": environment_info(),
    }
    if clock is not None:
        meta["started_at"] = clock()
    write_json(run_dir / "meta.json", meta)
    return RunResult(rid, run_dir, config_to_dict(config), outcome.metrics)


def sweep(
    base: ExperimentConfig, overrides: Sequence[Mapping[str, Any]], runs_dir: Path | str
) -> list[RunResult]:
    """Run ``base`` once per override set (for example several seeds or values of C)."""
    return [run_experiment(with_overrides(base, o), runs_dir) for o in overrides]


# ---------------------------------------------------------------------------
# Milestone 4: compare runs
# ---------------------------------------------------------------------------


def flatten(data: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten nested dicts with dotted keys: ``{"model": {"C": 1}} -> {"model.C": 1}``."""
    flat: dict[str, Any] = {}
    for key, value in data.items():
        name = f"{prefix}{key}"
        if isinstance(value, Mapping):
            flat.update(flatten(value, prefix=f"{name}."))
        else:
            flat[name] = value
    return flat


def load_runs(runs_dir: Path | str) -> pd.DataFrame:
    """One row per run folder that has ``params.json`` and ``metrics.json``.

    Columns: ``run_id``, the flattened config (``name``, ``seed``, ``data.dataset``, ``model.type``,
    ``model.C`` ...) and every metric. Sorted by ``run_id``; folders without both files are skipped.
    """
    rows = []
    for run_dir in sorted(p for p in Path(runs_dir).iterdir() if p.is_dir()):
        params_path, metrics_path = run_dir / "params.json", run_dir / "metrics.json"
        if not (params_path.exists() and metrics_path.exists()):
            continue
        params = json.loads(params_path.read_text(encoding="utf-8"))
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        rows.append({"run_id": run_dir.name, **flatten(params["config"]), **metrics})
    return pd.DataFrame(rows)


def compare_runs(
    runs_dir: Path | str, metric: str = "test_roc_auc", higher_is_better: bool = True
) -> pd.DataFrame:
    """Load runs and sort them by ``metric`` (best first, ties by ``run_id``).

    Raises:
        ValueError: if there are no runs or no run has the metric.
    """
    runs = load_runs(runs_dir)
    if runs.empty:
        raise ValueError(f"no runs found in {runs_dir}")
    if metric not in runs.columns:
        raise ValueError(
            f"metric {metric!r} not found; available: {sorted(c for c in runs.columns if '.' not in c)}"
        )
    ordered = runs.sort_values([metric, "run_id"], ascending=[not higher_is_better, True])
    return ordered.reset_index(drop=True)


def varying_columns(runs: pd.DataFrame) -> list[str]:
    """Config columns whose value differs between runs — what the comparison is really about."""
    config_cols = [c for c in runs.columns if c in {"name", "seed"} or "." in c]
    return [c for c in config_cols if runs[c].astype(str).nunique(dropna=False) > 1]


def comparison_report(runs: pd.DataFrame, metric: str = "test_roc_auc") -> str:
    """A Markdown report: what varied, a table of runs (best first) and the best run."""
    if runs.empty:
        raise ValueError("no runs to report")
    varying = varying_columns(runs)
    metric_cols = [c for c in runs.columns if c.startswith(("cv_", "test_"))]
    columns = ["run_id", *varying, *[c for c in metric_cols if c not in varying]]
    header = "| " + " | ".join(columns) + " |"
    lines = [
        "# Experiment comparison",
        "",
        f"{len(runs)} run(s), ranked by `{metric}`. Varying settings: "
        + (", ".join(f"`{c}`" for c in varying) or "none (pure repeats)"),
        "",
        header,
        "|" + "---|" * len(columns),
    ]
    for row in runs[columns].to_dict("records"):
        cells = [f"{row[c]:.4f}" if isinstance(row[c], float) else str(row[c]) for c in columns]
        lines.append("| " + " | ".join(cells) + " |")
    best = runs.iloc[0]
    lines += ["", f"**Best run:** `{best['run_id']}` with {metric} = {best[metric]:.4f}.", ""]
    return "\n".join(lines)


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
    try:
        import mlflow
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on the environment
        raise ModuleNotFoundError("MLflow is optional: python -m pip install mlflow") from exc
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name or str(result.params["name"]))
    with mlflow.start_run(run_name=result.run_id) as active:
        mlflow.set_tag("groundwork.run_id", result.run_id)
        mlflow.log_params(flatten(result.params))
        mlflow.log_metrics(result.metrics)
        mlflow.log_artifacts(str(result.run_dir / "artefacts"))
        return str(active.info.run_id)


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
