"""The compare harness: API contract, skip rule, report and command line.

These tests use tiny path counts and time budgets. They check that the harness measures
and reports consistently, not how fast anything is.
"""

import os

import pytest

import derivkit
from derivkit import comparison
from derivkit.__main__ import main
from derivkit.comparison import VR_METHODS, plot_accuracy_vs_time, write_report
from derivkit.monte_carlo import McConfig, european
from derivkit.types import OptionType, VanillaSpec, VarianceReduction

SPEC = VanillaSpec(
    spot=100.0, strike=100.0, rate=0.05, dividend=0.0, vol=0.2, time=1.0, type=OptionType.CALL
)

THREAD_VARS = comparison._THREAD_VARS


@pytest.fixture(autouse=True)
def restore_thread_settings(monkeypatch):
    """The command line pins BLAS to one thread through os.environ; undo that per test."""
    saved = {var: os.environ.get(var) for var in THREAD_VARS}
    monkeypatch.setattr(comparison, "_pinned", comparison._pinned)
    yield
    for var, value in saved.items():
        if value is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = value


def test_compare_reports_every_available_backend():
    cfg = McConfig(paths=3000, seed=4, vr=VarianceReduction.ANTITHETIC)
    report = derivkit.compare(SPEC, cfg, repeats=3)

    assert [r.backend for r in report.rows] == list(derivkit.available_backends())
    assert report.reference == derivkit.price(SPEC)
    assert not report.skipped
    for row in report.rows:
        direct = european(SPEC, cfg, backend=row.backend)
        assert (row.value, row.stderr) == (direct.value, direct.error_estimate)
        assert row.abs_error == abs(row.value - report.reference)
        assert row.seconds.runs == 3
        assert 0.0 < row.seconds.min <= row.seconds.median <= row.seconds.max
        assert row.paths_per_second == pytest.approx(cfg.paths / row.seconds.median)
    table = report.table()
    assert "Abs. error vs BS" in table and "Paths / s" in table


def test_compare_takes_several_configs_and_gives_speed_ratios():
    configs = [McConfig(paths=n, seed=1) for n in (2000, 4000)]
    report = derivkit.compare(SPEC, configs, backends=["python"], repeats=1)
    assert [(r.backend, r.paths) for r in report.rows] == [("python", 2000), ("python", 4000)]
    assert report.speed_ratios() == []  # nothing to compare python against


def test_configs_that_differ_only_by_seed_stay_separate():
    names = [b for b in ("python", "cpp") if b in derivkit.available_backends()]
    configs = [McConfig(paths=2000, seed=1), McConfig(paths=2000, seed=2)]
    report = derivkit.compare(SPEC, configs, backends=names, repeats=1)
    none = VarianceReduction.NONE
    assert report.configs() == [(none, 2000, 1), (none, 2000, 2)]
    assert [s.seed for s in report.speed_ratios()] == ([1, 2] if len(names) == 2 else [])
    assert "| Seed |" in report.table()


def test_compare_skips_runs_over_the_time_limit_and_says_so():
    report = derivkit.compare(
        SPEC, McConfig(paths=50_000_000), backends=["python"], repeats=1, max_run_seconds=1.0
    )
    assert report.rows == []
    (skipped,) = report.skipped
    assert (skipped.backend, skipped.paths) == ("python", 50_000_000)
    assert "over the 1 s per-run limit" in skipped.reason
    assert "Not run" in report.table()


def test_the_pilot_run_never_exceeds_the_run_it_is_sizing(monkeypatch):
    seen = []
    real = comparison.european

    def spy(spec, cfg, **kwargs):
        seen.append(cfg.paths)
        return real(spec, cfg, **kwargs)

    monkeypatch.setattr(comparison, "european", spy)
    derivkit.compare(SPEC, McConfig(paths=500), backends=["python"], repeats=1, max_run_seconds=60)
    assert max(seen) == 500


def test_compare_rejects_bad_arguments():
    with pytest.raises(ValueError, match="unknown backend"):
        derivkit.compare(SPEC, backends=["fortran"])
    with pytest.raises(ValueError, match="repeats"):
        derivkit.compare(SPEC, repeats=0)
    for budgets in ((0.0,), (float("inf"),), (float("nan"),), ()):
        with pytest.raises(ValueError, match="budgets"):
            derivkit.accuracy_per_second(SPEC, budgets=budgets)


def test_compare_leaves_the_callers_environment_alone():
    pytest.importorskip("numpy")  # with NumPy loaded it is too late to pin, so nothing may change
    before = {var: os.environ.get(var) for var in THREAD_VARS}
    comparison._pinned = False
    assert comparison.pin_to_one_thread() is False
    report = derivkit.compare(SPEC, McConfig(paths=2000), backends=["python"], repeats=1)
    assert report.threads_pinned is False
    assert before == {var: os.environ.get(var) for var in THREAD_VARS}


def test_accuracy_per_second_gives_more_paths_and_less_error_to_bigger_budgets():
    methods = [VR_METHODS["none"], VR_METHODS["both"]]
    report = derivkit.accuracy_per_second(
        SPEC, budgets=(0.005, 0.02), vr_methods=methods, repeats=2, calibration_seconds=0.005
    )
    backends = derivkit.available_backends()
    assert len(report.rows) == len(backends) * len(methods) * 2
    assert len(report.calibrations) == len(backends) * len(methods)
    for name in backends:
        for vr in methods:
            small, big = (r for r in report.rows if r.backend == name and r.vr == vr)
            assert (small.budget, big.budget) == (0.005, 0.02)
            assert big.paths > small.paths
            assert big.stderr < small.stderr
    assert "Standard error reached in a fixed time" in report.table()


def test_command_line_prints_tables_and_writes_the_report(tmp_path, capsys):
    report = tmp_path / "out" / "RESULTS.md"
    argv = ["compare", "--paths", "2e3", "--repeats", "1", "--backends", "python"]
    argv += ["--vr", "none", "cv", "--budgets", "0.005", "--calibration-seconds", "0.005"]
    argv += ["--report", str(report)]
    assert main(argv) == 0

    printed = capsys.readouterr().out
    assert "**No variance reduction**" in printed and "**Control variate**" in printed
    assert "Standard error reached in a fixed time" in printed
    text = report.read_text()
    assert "python -m derivkit compare --paths 2e3" in text  # the exact command is recorded
    for heading in ("## Accuracy per second", "## Fixed path counts", "| CPU |", "| Python |"):
        assert heading in text


@pytest.mark.parametrize(
    "bad",
    [
        ["--paths", "inf"],
        ["--paths", "nan"],
        ["--paths", "2.5"],
        ["--paths", "1"],
        ["--budgets", "0"],
        ["--budgets", "inf"],
        ["--budgets", "nan"],
        ["--repeats", "0"],
        ["--max-run-seconds", "-1"],
    ],
)
def test_command_line_rejects_bad_numbers_before_running_anything(bad, capsys, monkeypatch):
    monkeypatch.setattr(comparison, "european", lambda *a, **k: pytest.fail("ran a simulation"))
    with pytest.raises(SystemExit) as excinfo:
        main(["compare", *bad])
    assert excinfo.value.code == 2
    assert "error: argument" in capsys.readouterr().err


def test_command_line_rejects_plot_without_budgets(capsys):
    assert main(["compare", "--paths", "2000", "--plot", "x.png"]) == 2
    assert "--plot needs --budgets" in capsys.readouterr().err


def test_report_with_no_measurements_is_still_written(tmp_path):
    empty = derivkit.compare(SPEC, [], backends=["python"])
    assert "No measurements were taken." in empty.table()
    write_report(tmp_path / "R.md", "python -m derivkit compare", empty, None)
    assert "No measurements were taken." in (tmp_path / "R.md").read_text()
    with pytest.raises(ValueError, match="nothing to report"):
        write_report(tmp_path / "R.md", "python -m derivkit compare", None, None)


def test_commit_is_only_reported_from_a_source_checkout(monkeypatch, tmp_path):
    assert comparison._checkout_root() is not None  # the tests run from the repository
    installed = tmp_path / "site-packages" / "derivkit" / "comparison.py"
    monkeypatch.setattr(comparison, "__file__", str(installed))
    assert comparison._checkout_root() is None
    assert comparison.environment()["derivkit"] == derivkit.__version__


def test_plot_is_written_without_touching_the_matplotlib_backend(tmp_path):
    matplotlib = pytest.importorskip("matplotlib")
    before = matplotlib.get_backend()
    # Three methods: an odd number leaves one cell of the 2 x 2 grid empty.
    three_methods = [VR_METHODS[name] for name in ("none", "antithetic", "cv")]
    report = derivkit.accuracy_per_second(
        SPEC,
        budgets=(0.005, 0.01),
        vr_methods=three_methods,
        backends=["python"],
        repeats=1,
        calibration_seconds=0.005,
    )
    png = tmp_path / "plots" / "accuracy.png"
    plot_accuracy_vs_time(report, png)
    assert png.read_bytes().startswith(b"\x89PNG")
    assert matplotlib.get_backend() == before
    write_report(tmp_path / "R.md", "python -m derivkit compare", None, report, png)
    text = (tmp_path / "R.md").read_text()
    assert "![Standard error against time budget](plots/accuracy.png)" in text


def test_plotting_an_empty_report_says_why(tmp_path):
    pytest.importorskip("matplotlib")
    empty = derivkit.accuracy_per_second(SPEC, budgets=(0.005,), vr_methods=[], repeats=1)
    assert empty.rows == []
    with pytest.raises(ValueError, match="no measurements"):
        plot_accuracy_vs_time(empty, tmp_path / "empty.png")
