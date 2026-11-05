"""Behaviour tests for the experiment runner, grouped by milestone.

Runs are written to pytest's ``tmp_path``; nothing depends on the wall clock or the network.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import experiment_runner as er
import pandas as pd
import pytest

EXAMPLE_TOML = """
name = "logreg-test"
seed = 42

[data]
dataset = "synthetic"
test_size = 0.25

[model]
type = "logistic_regression"
C = 0.5

[evaluation]
cv_folds = 3
"""

# The same experiment with keys in a different order.
REORDERED_TOML = """
seed = 42
name = "logreg-test"

[evaluation]
cv_folds = 3

[model]
C = 0.5
type = "logistic_regression"

[data]
test_size = 0.25
dataset = "synthetic"
"""


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    path = tmp_path / "experiment.toml"
    path.write_text(EXAMPLE_TOML, encoding="utf-8")
    return path


@pytest.fixture
def config() -> er.ExperimentConfig:
    return er.ExperimentConfig(
        name="logreg-test", seed=42, dataset="synthetic", test_size=0.25, cv_folds=3, params={"C": 0.5}
    )


class TestMilestone1Config:
    """Milestone 1: load, validate, hash and override configs."""

    def test_load_config(self, config_file: Path, config: er.ExperimentConfig) -> None:
        loaded = er.load_config(config_file)
        assert loaded == config
        assert loaded.model == "logistic_regression" and loaded.params == {"C": 0.5}

    def test_round_trip(self, config: er.ExperimentConfig) -> None:
        nested = er.config_to_dict(config)
        assert nested["model"] == {"type": "logistic_regression", "C": 0.5}
        assert nested["data"] == {"dataset": "synthetic", "test_size": 0.25}
        assert er.config_from_dict(nested) == config

    def test_hash_ignores_key_order(self, tmp_path: Path, config_file: Path) -> None:
        other = tmp_path / "reordered.toml"
        other.write_text(REORDERED_TOML, encoding="utf-8")
        assert er.config_hash(er.load_config(config_file)) == er.config_hash(er.load_config(other))

    def test_hash_is_sha256_of_canonical_json(self, config: er.ExperimentConfig) -> None:
        canonical = json.dumps(er.config_to_dict(config), sort_keys=True, separators=(",", ":"))
        assert er.config_hash(config) == hashlib.sha256(canonical.encode()).hexdigest()

    def test_hash_changes_with_any_setting(self, config: er.ExperimentConfig) -> None:
        base = er.config_hash(config)
        assert er.config_hash(er.with_overrides(config, {"seed": 43})) != base
        assert er.config_hash(er.with_overrides(config, {"params.C": 0.6})) != base

    def test_run_id(self, config: er.ExperimentConfig) -> None:
        run_id = er.make_run_id(config)
        assert run_id == f"logreg-test-{er.config_hash(config)[:8]}"
        assert run_id == er.make_run_id(er.ExperimentConfig(**config.__dict__)), "deterministic, no clock"

    @pytest.mark.parametrize(
        "raw",
        [
            {"name": "x", "seed": 1, "modle": {}},  # typo at top level
            {"name": "x", "seed": 1, "data": {"datset": "synthetic"}},  # typo in [data]
            {"name": "x"},  # no seed
            {"name": "x", "seed": -1},
            {"name": "x", "seed": 1.5},
            {"name": "../escape", "seed": 1},
            {"name": "x", "seed": 1, "data": {"dataset": "imagenet"}},
            {"name": "x", "seed": 1, "data": {"test_size": 1.0}},
            {"name": "x", "seed": 1, "evaluation": {"cv_folds": 1}},
            {"name": "x", "seed": 1, "model": {"type": "xgboost"}},
        ],
    )
    def test_invalid_configs(self, raw: dict) -> None:
        with pytest.raises(ValueError):
            er.config_from_dict(raw)

    def test_with_overrides(self, config: er.ExperimentConfig) -> None:
        changed = er.with_overrides(config, {"seed": 7, "params.C": 2.0, "params.max_iter": 100})
        assert changed.seed == 7 and changed.params == {"C": 2.0, "max_iter": 100}
        assert config.seed == 42 and config.params == {"C": 0.5}, "the original config is unchanged"
        with pytest.raises(ValueError):
            er.with_overrides(config, {"colour": "red"})
        with pytest.raises(ValueError):
            er.with_overrides(config, {"test_size": 2.0})


class TestMilestone2SeedsAndTraining:
    """Milestone 2: derived seeds, data, model and a deterministic evaluation."""

    def test_derive_seed(self) -> None:
        expected = int(hashlib.sha256(b"42:split").hexdigest()[:8], 16)
        assert er.derive_seed(42, "split") == expected
        assert er.derive_seed(42, "split") != er.derive_seed(42, "model")
        assert er.derive_seed(42, "split") != er.derive_seed(43, "split")

    def test_datasets(self, config: er.ExperimentConfig) -> None:
        X, y = er.load_dataset(config)
        assert X.shape == (600, 12) and set(y.unique()) == {0, 1}
        X2, _ = er.load_dataset(er.with_overrides(config, {"seed": 1}))
        assert not X.equals(X2), "synthetic data is generated from the config seed"
        Xb, yb = er.load_dataset(er.with_overrides(config, {"dataset": "breast_cancer"}))
        assert Xb.shape == (569, 30)

    def test_build_model_sets_params_and_seed(self, config: er.ExperimentConfig) -> None:
        model = er.build_model(config)
        params = model.get_params()
        assert params["model__C"] == 0.5
        assert params["model__random_state"] == er.derive_seed(42, "model")
        forest = er.build_model(
            er.ExperimentConfig(name="rf", seed=3, model="random_forest", params={"max_depth": 4})
        )
        assert forest.get_params()["max_depth"] == 4
        assert forest.get_params()["random_state"] == er.derive_seed(3, "model")

    def test_build_model_rejects_unknown_params(self, config: er.ExperimentConfig) -> None:
        with pytest.raises(ValueError, match="gamma"):
            er.build_model(er.with_overrides(config, {"params.gamma": 1}))

    def test_same_config_same_results(self, config: er.ExperimentConfig) -> None:
        a, b = er.train_and_evaluate(config), er.train_and_evaluate(config)
        assert a.metrics == b.metrics, "identical configs must give identical metrics, to the last digit"
        pd.testing.assert_frame_equal(a.predictions, b.predictions)
        assert set(a.metrics) == {
            "cv_roc_auc_mean", "cv_roc_auc_std", "test_accuracy", "test_f1", "test_roc_auc", "test_log_loss",
        }  # fmt: skip
        assert list(a.predictions.columns) == ["row", "y_true", "y_score", "y_pred"]
        assert len(a.predictions) == 150, "25% of 600 rows"

    def test_random_forest_is_deterministic_too(self) -> None:
        rf = er.ExperimentConfig(
            name="rf",
            seed=5,
            dataset="synthetic",
            cv_folds=3,
            model="random_forest",
            params={"n_estimators": 30},
        )
        assert er.train_and_evaluate(rf).metrics == er.train_and_evaluate(rf).metrics
        other = er.train_and_evaluate(er.with_overrides(rf, {"seed": 6}))
        assert not other.predictions.equals(er.train_and_evaluate(rf).predictions)

    def test_quality(self, config: er.ExperimentConfig) -> None:
        metrics = er.train_and_evaluate(config).metrics
        assert metrics["test_roc_auc"] > 0.85 and metrics["cv_roc_auc_mean"] > 0.85


class TestMilestone3Tracking:
    """Milestone 3: the run folder — params, metrics, artefacts and metadata."""

    def test_run_folder_layout(self, config: er.ExperimentConfig, tmp_path: Path) -> None:
        result = er.run_experiment(config, tmp_path / "runs")
        run_dir = tmp_path / "runs" / er.make_run_id(config)
        assert result.run_dir == run_dir and result.run_id == run_dir.name
        for name in ("params.json", "metrics.json", "meta.json"):
            assert (run_dir / name).is_file(), f"{name} is missing from the run folder"
        for name in ("predictions.csv", "confusion_matrix.json", "run.log"):
            assert (run_dir / "artefacts" / name).is_file(), f"artefacts/{name} is missing"

    def test_json_contents(self, config: er.ExperimentConfig, tmp_path: Path) -> None:
        result = er.run_experiment(config, tmp_path)
        params = json.loads((result.run_dir / "params.json").read_text(encoding="utf-8"))
        assert params == {"config": er.config_to_dict(config), "config_hash": er.config_hash(config)}
        metrics = json.loads((result.run_dir / "metrics.json").read_text(encoding="utf-8"))
        assert metrics == result.metrics
        meta = json.loads((result.run_dir / "meta.json").read_text(encoding="utf-8"))
        assert meta["run_id"] == result.run_id and meta["config_hash"] == er.config_hash(config)
        assert {"python", "numpy", "pandas", "scikit-learn"} <= set(meta["environment"])
        assert "started_at" not in meta, "no wall-clock time unless a clock is injected"
        matrix = json.loads(
            (result.run_dir / "artefacts" / "confusion_matrix.json").read_text(encoding="utf-8")
        )
        assert sum(map(sum, matrix)) == 150

    def test_reruns_are_byte_identical(self, config: er.ExperimentConfig, tmp_path: Path) -> None:
        a = er.run_experiment(config, tmp_path / "a")
        b = er.run_experiment(config, tmp_path / "b")
        for name in ("params.json", "metrics.json", "artefacts/predictions.csv", "artefacts/run.log"):
            assert (a.run_dir / name).read_bytes() == (b.run_dir / name).read_bytes(), f"{name} differs"

    def test_injected_clock(self, config: er.ExperimentConfig, tmp_path: Path) -> None:
        result = er.run_experiment(config, tmp_path, clock=lambda: "2026-01-01T00:00:00Z")
        meta = json.loads((result.run_dir / "meta.json").read_text(encoding="utf-8"))
        assert meta["started_at"] == "2026-01-01T00:00:00Z"

    def test_never_overwrites_silently(self, config: er.ExperimentConfig, tmp_path: Path) -> None:
        er.run_experiment(config, tmp_path)
        with pytest.raises(FileExistsError):
            er.run_experiment(config, tmp_path)
        er.run_experiment(config, tmp_path, overwrite=True)
        custom = er.run_experiment(config, tmp_path, run_id="my-run")
        assert custom.run_dir == tmp_path / "my-run"

    @pytest.mark.parametrize("bad", ["../outside", "a/b", "a\\b", ".hidden", ""])
    def test_artefact_names_cannot_escape(self, tmp_path: Path, bad: str) -> None:
        run_dir = er.start_run(tmp_path, "r1")
        with pytest.raises(ValueError):
            er.log_artefact(run_dir, bad, "x")

    def test_artefact_types(self, tmp_path: Path) -> None:
        run_dir = er.start_run(tmp_path, "r1")
        er.log_artefact(run_dir, "notes.txt", "hello")
        er.log_artefact(run_dir, "blob.bin", b"\x00\x01")
        er.log_artefact(run_dir, "table.csv", pd.DataFrame({"a": [1, 2]}))
        er.log_artefact(run_dir, "data.json", {"k": [1, 2]})
        art = run_dir / "artefacts"
        assert (art / "notes.txt").read_text(encoding="utf-8") == "hello"
        assert (art / "blob.bin").read_bytes() == b"\x00\x01"
        assert (art / "table.csv").read_text(encoding="utf-8") == "a\n1\n2\n"
        assert json.loads((art / "data.json").read_text(encoding="utf-8")) == {"k": [1, 2]}

    def test_bad_run_ids_and_metrics(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            er.start_run(tmp_path, "../up")
        run_dir = er.start_run(tmp_path, "ok")
        with pytest.raises(ValueError):
            er.log_metrics(run_dir, {"auc": float("nan")})


class TestMilestone4Comparison:
    """Milestone 4: load and compare runs, and write the report."""

    @pytest.fixture
    def runs_dir(self, config: er.ExperimentConfig, tmp_path: Path) -> Path:
        runs = tmp_path / "runs"
        er.sweep(config, [{"params.C": 0.01}, {"params.C": 1.0}, {"params.C": 100.0}], runs)
        (runs / "crashed-run").mkdir()  # a run that never finished: no metrics.json
        return runs

    def test_flatten(self) -> None:
        assert er.flatten({"a": 1, "b": {"c": 2, "d": {"e": 3}}}) == {"a": 1, "b.c": 2, "b.d.e": 3}

    def test_load_runs(self, runs_dir: Path) -> None:
        runs = er.load_runs(runs_dir)
        assert len(runs) == 3, "folders without params.json and metrics.json are skipped"
        assert {"run_id", "seed", "model.type", "model.C", "data.dataset", "test_roc_auc"} <= set(
            runs.columns
        )
        assert list(runs["run_id"]) == sorted(runs["run_id"])

    def test_compare_runs_sorts_best_first(self, runs_dir: Path) -> None:
        ranked = er.compare_runs(runs_dir, "test_roc_auc")
        assert ranked["test_roc_auc"].is_monotonic_decreasing
        by_loss = er.compare_runs(runs_dir, "test_log_loss", higher_is_better=False)
        assert by_loss["test_log_loss"].is_monotonic_increasing

    def test_compare_runs_errors(self, runs_dir: Path, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            er.compare_runs(runs_dir, "speed")
        (tmp_path / "empty").mkdir()
        with pytest.raises(ValueError):
            er.compare_runs(tmp_path / "empty")

    def test_varying_columns(self, runs_dir: Path) -> None:
        assert er.varying_columns(er.load_runs(runs_dir)) == ["model.C"]

    def test_comparison_report(self, runs_dir: Path) -> None:
        ranked = er.compare_runs(runs_dir, "test_roc_auc")
        text = er.comparison_report(ranked, "test_roc_auc")
        assert text.startswith("# Experiment comparison")
        assert "`model.C`" in text, "say which settings varied"
        assert f"**Best run:** `{ranked.loc[0, 'run_id']}`" in text
        table_rows = [line for line in text.splitlines() if line.startswith("| logreg-test")]
        assert len(table_rows) == 3
        assert table_rows[0].startswith(f"| {ranked.loc[0, 'run_id']} |"), "best run first"


class TestMilestone5OptionalMlflow:
    """Milestone 5 (optional): mirror a run into MLflow. Skipped unless mlflow is installed."""

    def test_log_to_mlflow(self, config: er.ExperimentConfig, tmp_path: Path) -> None:
        mlflow = pytest.importorskip("mlflow")
        result = er.run_experiment(config, tmp_path / "runs")
        uri = (tmp_path / "mlruns").as_uri()
        mlflow_run_id = er.log_to_mlflow(result, uri, experiment_name="groundwork-test")
        run = mlflow.tracking.MlflowClient(tracking_uri=uri).get_run(mlflow_run_id)
        assert run.data.metrics["test_roc_auc"] == pytest.approx(result.metrics["test_roc_auc"])
        assert run.data.params["model.C"] == "0.5"
        assert run.data.tags["groundwork.run_id"] == result.run_id
