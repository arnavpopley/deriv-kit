"""The compare harness: API contract, skip rule, report and command line.

These tests use tiny path counts and time budgets. They check that the harness measures
and reports consistently, not how fast anything is.
"""

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

# The command line has no flag for the calibration length, so the CLI test shortens the
# default (0.2 s per calibration run) to keep the suite quick.
FAST_CALIBRATION = {**comparison.accuracy_per_second.__kwdefaults__, "calibration_seconds": 0.005}


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


def test_compare_skips_runs_over_the_time_limit_and_says_so():
    report = derivkit.compare(
        SPEC, McConfig(paths=50_000_000), backends=["python"], repeats=1, max_run_seconds=1.0
    )
    assert report.rows == []
    (skipped,) = report.skipped
    assert (skipped.backend, skipped.paths) == ("python", 50_000_000)
    assert "over the 1 s per-run limit" in skipped.reason
    assert "Not run" in report.table()


def test_compare_rejects_bad_arguments():
    with pytest.raises(ValueError, match="unknown backend"):
        derivkit.compare(SPEC, backends=["fortran"])
    with pytest.raises(ValueError, match="repeats"):
        derivkit.compare(SPEC, repeats=0)
    with pytest.raises(ValueError, match="budgets"):
        derivkit.accuracy_per_second(SPEC, budgets=(0.0,))


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


def test_command_line_prints_tables_and_writes_the_report(tmp_path, capsys, monkeypatch):
    report = tmp_path / "out" / "RESULTS.md"
    argv = ["compare", "--paths", "2e3", "--repeats", "1", "--backends", "python"]
    argv += ["--vr", "none", "cv", "--budgets", "0.005", "--report", str(report)]
    monkeypatch.setattr(comparison.accuracy_per_second, "__kwdefaults__", FAST_CALIBRATION)
    assert main(argv) == 0

    printed = capsys.readouterr().out
    assert "**No variance reduction**" in printed and "**Control variate**" in printed
    assert "Standard error reached in a fixed time" in printed
    text = report.read_text()
    assert "python -m derivkit compare --paths 2e3" in text  # the exact command is recorded
    for heading in ("## Accuracy per second", "## Fixed path counts", "| CPU |", "| Python |"):
        assert heading in text


def test_command_line_rejects_plot_without_budgets(capsys):
    assert main(["compare", "--paths", "2000", "--plot", "x.png"]) == 2
    assert "--plot needs --budgets" in capsys.readouterr().err


def test_plot_is_written(tmp_path):
    pytest.importorskip("matplotlib")
    report = derivkit.accuracy_per_second(
        SPEC, budgets=(0.005, 0.01), backends=["python"], repeats=1, calibration_seconds=0.005
    )
    png = tmp_path / "plots" / "accuracy.png"
    plot_accuracy_vs_time(report, png)
    assert png.read_bytes().startswith(b"\x89PNG")
    write_report(tmp_path / "R.md", "python -m derivkit compare", None, report, png)
    text = (tmp_path / "R.md").read_text()
    assert "![Standard error against time budget](plots/accuracy.png)" in text
