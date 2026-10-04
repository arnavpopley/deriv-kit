"""Compare the Monte Carlo back ends on accuracy and speed.

    import derivkit
    from derivkit.monte_carlo import McConfig

    spec = derivkit.VanillaSpec(spot=100, strike=100, rate=0.05, vol=0.2, time=1.0)
    print(derivkit.compare(spec, McConfig(paths=1_000_000, seed=1)).table())
    print(derivkit.accuracy_per_second(spec, budgets=(0.1, 1.0)).table())

From the command line: `python -m derivkit compare --help`.

Two views of the same question:

`compare` fixes the number of paths and reports what each back end did with them: price,
standard error, absolute error against the Black-Scholes closed form, run time and paths
per second.

`accuracy_per_second` fixes the time instead and reports the error each back end reaches
in it. That is the fairer question, because it charges each variance-reduction method
its own cost and each back end its own speed.

Every number these functions return is measured in this process. Nothing is estimated.
"""

from __future__ import annotations

import math
import os
import platform
import statistics
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from derivkit import backends as _backends
from derivkit.black_scholes import price
from derivkit.monte_carlo import McConfig, european
from derivkit.result import PricingResult
from derivkit.types import OptionType, VanillaSpec, VarianceReduction, validate

VR_METHODS: dict[str, VarianceReduction] = {
    "none": VarianceReduction.NONE,
    "antithetic": VarianceReduction.ANTITHETIC,
    "cv": VarianceReduction.CONTROL_VARIATE,
    "both": VarianceReduction.ANTITHETIC | VarianceReduction.CONTROL_VARIATE,
}

VR_LABELS = {
    "none": "No variance reduction",
    "antithetic": "Antithetic",
    "cv": "Control variate",
    "both": "Antithetic + control variate",
}

DEFAULT_BUDGETS = (0.1, 1.0, 10.0)

Progress = Callable[[str], None]


def vr_name(vr: VarianceReduction) -> str:
    """Short name ("none", "antithetic", "cv", "both") for a variance-reduction setting."""
    for name, flags in VR_METHODS.items():
        if flags == vr:
            return name
    raise ValueError(f"unknown variance reduction {vr!r}")


# --------------------------------------------------------------------------------------
# Measurement
# --------------------------------------------------------------------------------------

_THREAD_VARS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)
_pinned_in_time: bool | None = None


def pin_to_one_thread() -> bool:
    """Ask BLAS and OpenMP runtimes for a single thread, so the comparison is like for like.

    These libraries read the variables when they load, so this only takes effect if NumPy
    has not been imported yet. Returns whether the request was made in time. Either way
    each row reports CPU time over wall time, which shows what actually happened.
    """
    global _pinned_in_time
    if _pinned_in_time is None:  # only the first call can be in time; remember its answer
        _pinned_in_time = "numpy" not in sys.modules
        for var in _THREAD_VARS:
            os.environ[var] = "1"
    return _pinned_in_time


@dataclass(frozen=True)
class Timing:
    """Wall-clock seconds over `runs` timed runs (after the warm-up)."""

    median: float
    min: float
    max: float
    runs: int


def _timed(
    fn: Callable[[], PricingResult], repeats: int, warmup: int
) -> tuple[PricingResult, Timing, float]:
    """Run `fn` `warmup` times untimed, then `repeats` times timed.

    Returns the last result, the timing, and CPU time divided by wall time over the timed
    runs (1.0 means one busy thread).
    """
    for _ in range(warmup):
        fn()
    walls = []
    cpu = 0.0
    result = None
    for _ in range(repeats):
        cpu_start = time.process_time()
        start = time.perf_counter()
        result = fn()
        walls.append(time.perf_counter() - start)
        cpu += time.process_time() - cpu_start
    timing = Timing(statistics.median(walls), min(walls), max(walls), repeats)
    return result, timing, cpu / sum(walls)


def _rate(
    spec: VanillaSpec, cfg: McConfig, backend: str, target_seconds: float
) -> tuple[float, int]:
    """One quick run to learn roughly how many paths per second `backend` manages.

    Returns (paths per second, a path count that should take about `target_seconds`).
    """
    pilot = 20_000
    start = time.perf_counter()
    european(spec, McConfig(paths=pilot, seed=cfg.seed, vr=cfg.vr), backend=backend)
    rate = pilot / (time.perf_counter() - start)
    return rate, max(pilot, int(rate * target_seconds))


def _resolve_backends(backends: Iterable[str] | None) -> tuple[str, ...]:
    if backends is None:
        return _backends.available_backends()
    names = tuple(backends)
    for name in names:
        _backends.kernel(name)  # raises a clear error if unknown or unavailable
    return names


def _check_repeats(repeats: int, warmup: int) -> None:
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    if warmup < 0:
        raise ValueError("warmup must be non-negative")


@dataclass(frozen=True)
class CompareRow:
    """One back end pricing one configuration."""

    backend: str
    vr: VarianceReduction
    paths: int
    value: float
    stderr: float
    abs_error: float  # |value - Black-Scholes|
    seconds: Timing
    paths_per_second: float  # paths / median seconds
    cpu_per_wall: float


@dataclass(frozen=True)
class Skipped:
    """A measurement that was not taken, and why."""

    backend: str
    vr: VarianceReduction
    paths: int
    reason: str


@dataclass
class CompareReport:
    spec: VanillaSpec
    reference: float  # Black-Scholes closed form
    repeats: int
    warmup: int
    threads_pinned: bool
    rows: list[CompareRow] = field(default_factory=list)
    skipped: list[Skipped] = field(default_factory=list)

    def speed_ratios(self) -> list[tuple[VarianceReduction, int, str, str, float]]:
        """(vr, paths, faster-if-above-1 back end, baseline, ratio of median run times).

        A ratio of 2 means the first back end ran the same paths in half the time.
        """
        by_key = {(r.vr, r.paths, r.backend): r for r in self.rows}
        out = []
        for vr, paths in dict.fromkeys((r.vr, r.paths) for r in self.rows):
            for fast, base in (("cpp", "numpy"), ("cpp", "python"), ("numpy", "python")):
                a, b = by_key.get((vr, paths, fast)), by_key.get((vr, paths, base))
                if a and b:
                    out.append((vr, paths, fast, base, b.seconds.median / a.seconds.median))
        return out

    def table(self) -> str:
        return _compare_tables(self)


def compare(
    spec: VanillaSpec,
    configs: McConfig | Iterable[McConfig] | None = None,
    *,
    backends: Iterable[str] | None = None,
    repeats: int = 7,
    warmup: int = 1,
    max_run_seconds: float | None = None,
    progress: Progress | None = None,
) -> CompareReport:
    """Price one European option with every back end and time each one.

    `configs` is one `McConfig` (paths, seed, variance reduction) or several; every back
    end gets exactly the same ones. `backends` defaults to all that are available.
    Each run time is the median of `repeats` timed runs after `warmup` untimed ones.

    If `max_run_seconds` is set, a back end whose single run is estimated to take longer
    is skipped for that configuration and listed in `report.skipped` with the reason.
    """
    _check_repeats(repeats, warmup)
    validate(spec)
    if configs is None:
        configs = McConfig()
    if isinstance(configs, McConfig):
        configs = [configs]
    pinned = pin_to_one_thread()
    names = _resolve_backends(backends)
    report = CompareReport(spec, price(spec), repeats, warmup, pinned)
    for cfg in configs:
        for name in names:
            if max_run_seconds is not None:
                rate, _ = _rate(spec, cfg, name, 0.0)
                estimate = cfg.paths / rate
                if estimate > max_run_seconds:
                    reason = (
                        f"one run estimated at {estimate:.0f} s, "
                        f"over the {max_run_seconds:g} s per-run limit"
                    )
                    report.skipped.append(Skipped(name, cfg.vr, cfg.paths, reason))
                    if progress:
                        progress(
                            f"skip   {name:<6} {cfg.paths:>12,} paths  {vr_name(cfg.vr)}: {reason}"
                        )
                    continue
            if progress:
                progress(f"timing {name:<6} {cfg.paths:>12,} paths  {vr_name(cfg.vr)}")
            result, timing, cpu = _timed(
                lambda cfg=cfg, name=name: european(spec, cfg, backend=name), repeats, warmup
            )
            report.rows.append(
                CompareRow(
                    backend=name,
                    vr=cfg.vr,
                    paths=cfg.paths,
                    value=result.value,
                    stderr=result.error_estimate,
                    abs_error=abs(result.value - report.reference),
                    seconds=timing,
                    paths_per_second=cfg.paths / timing.median,
                    cpu_per_wall=cpu,
                )
            )
    return report


@dataclass(frozen=True)
class BudgetRow:
    """One back end, one variance-reduction method, one time budget."""

    backend: str
    vr: VarianceReduction
    budget: float  # seconds allowed
    paths: int  # paths that fit: calibrated rate x budget
    seconds: float  # measured wall time of the run
    value: float
    stderr: float
    abs_error: float


@dataclass(frozen=True)
class Calibration:
    """How the paths-per-second rate behind a budget row was measured."""

    backend: str
    vr: VarianceReduction
    paths: int
    seconds: Timing
    paths_per_second: float


@dataclass
class BudgetReport:
    spec: VanillaSpec
    reference: float
    seed: int
    budgets: tuple[float, ...]
    repeats: int
    warmup: int
    threads_pinned: bool
    rows: list[BudgetRow] = field(default_factory=list)
    calibrations: list[Calibration] = field(default_factory=list)

    def table(self) -> str:
        return _budget_tables(self)


def accuracy_per_second(
    spec: VanillaSpec,
    budgets: Sequence[float] = DEFAULT_BUDGETS,
    *,
    seed: int = 1,
    vr_methods: Iterable[VarianceReduction] | None = None,
    backends: Iterable[str] | None = None,
    repeats: int = 7,
    warmup: int = 1,
    calibration_seconds: float = 0.2,
    progress: Progress | None = None,
) -> BudgetReport:
    """The error each back end reaches in a fixed time, per variance-reduction method.

    For each back end and method the paths-per-second rate is measured first (median of
    `repeats` runs of about `calibration_seconds` each, after `warmup`). Each budget is
    then one run of rate x budget paths, and the row records how long that run really
    took, its standard error and its absolute error against Black-Scholes.
    """
    _check_repeats(repeats, warmup)
    validate(spec)
    if not budgets or min(budgets) <= 0.0:
        raise ValueError("budgets must be positive")
    methods = list(VR_METHODS.values()) if vr_methods is None else list(vr_methods)
    pinned = pin_to_one_thread()
    names = _resolve_backends(backends)
    reference = price(spec)
    report = BudgetReport(spec, reference, seed, tuple(budgets), repeats, warmup, pinned)
    for vr in methods:
        for name in names:
            if progress:
                progress(f"calibrating {name:<6} {vr_name(vr)}")
            _, n_cal = _rate(spec, McConfig(seed=seed, vr=vr), name, calibration_seconds)
            cal_cfg = McConfig(paths=n_cal, seed=seed, vr=vr)
            _, timing, _ = _timed(
                lambda cal_cfg=cal_cfg, name=name: european(spec, cal_cfg, backend=name),
                repeats,
                warmup,
            )
            rate = n_cal / timing.median
            report.calibrations.append(Calibration(name, vr, n_cal, timing, rate))
            for budget in report.budgets:
                paths = max(2, int(rate * budget))
                if progress:
                    progress(f"  {budget:g} s budget: {paths:,} paths")
                cfg = McConfig(paths=paths, seed=seed, vr=vr)
                start = time.perf_counter()
                result = european(spec, cfg, backend=name)
                elapsed = time.perf_counter() - start
                report.rows.append(
                    BudgetRow(
                        backend=name,
                        vr=vr,
                        budget=budget,
                        paths=paths,
                        seconds=elapsed,
                        value=result.value,
                        stderr=result.error_estimate,
                        abs_error=abs(result.value - reference),
                    )
                )
    return report


# --------------------------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------------------------


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, check=False, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def _cpu_model() -> str:
    if sys.platform == "darwin":
        model = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
    elif sys.platform.startswith("linux"):
        model = ""
        try:
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                if line.lower().startswith(("model name", "hardware")):
                    model = line.split(":", 1)[1].strip()
                    break
        except OSError:
            pass
    else:
        model = ""
    model = model or platform.processor() or "unknown"
    return f"{model} ({os.cpu_count()} logical cores, {platform.machine()})"


def environment() -> dict[str, str]:
    """What the numbers were measured on: hardware, OS, interpreter, libraries, compiler."""
    from derivkit import __version__

    info = {
        "CPU": _cpu_model(),
        "OS": platform.platform(),
        "Python": (
            f"{platform.python_implementation()} {platform.python_version()} "
            f"({platform.python_compiler().strip()})"
        ),
    }
    available = _backends.available_backends()
    if "numpy" in available:
        import numpy as np

        try:
            blas = np.__config__.show(mode="dicts")["Build Dependencies"]["blas"]["name"]
        except (AttributeError, KeyError, TypeError):
            blas = "unknown"
        info["NumPy"] = f"{np.__version__} (generator PCG64, BLAS {blas})"
    else:
        info["NumPy"] = "not installed"
    if "cpp" in available:
        build = _backends.kernel("cpp").build_info()
        info["C++ compiler"] = build["compiler"]
        info["C++ build"] = (
            f"{build['build_type']}, flags `{build['cxx_flags']}`, pybind11 {build['pybind11']}"
        )
    else:
        info["C++ compiler"] = "extension not built"
    root = Path(__file__).resolve().parents[2]
    commit = _run(["git", "rev-parse", "--short", "HEAD"], cwd=root)
    if commit:
        changed = _run(["git", "status", "--porcelain"], cwd=root)
        dirty = " plus uncommitted changes" if changed else ""
        info["derivkit"] = f"{__version__} (commit {commit}{dirty})"
    else:
        info["derivkit"] = __version__
    return info


# --------------------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------------------


def _sci(x: float) -> str:
    """1.23 x 10^-4, the notation used throughout the docs."""
    if x == 0.0:
        return "0"
    exponent = math.floor(math.log10(abs(x)))
    mantissa = x / 10.0**exponent
    if round(mantissa, 2) >= 10.0:  # 9.999 rounds up to 10.00
        mantissa, exponent = mantissa / 10.0, exponent + 1
    return f"{mantissa:.2f} x 10^{exponent}"


def _seconds(t: float) -> str:
    return f"{t:.4g}"


def _millions(rate: float) -> str:
    return f"{rate / 1e6:.2f} M"


def _times(ratio: float) -> str:
    """A speed ratio to three significant figures: 0.47x, 6.83x, 68.6x, 142x."""
    digits = 2 if ratio < 10.0 else 1 if ratio < 100.0 else 0
    return f"{ratio:.{digits}f}x"


def _md_table(headers: Sequence[str], rows: Iterable[Sequence[str]], left: int = 1) -> str:
    """A GitHub-flavoured Markdown table; the first `left` columns are left-aligned."""
    lines = ["| " + " | ".join(headers) + " |"]
    rule = ("---" if i < left else "---:" for i in range(len(headers)))
    lines.append("| " + " | ".join(rule) + " |")
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def describe(spec: VanillaSpec) -> str:
    kind = "call" if spec.type is OptionType.CALL else "put"
    return (
        f"European {kind}, S = {spec.spot:g}, K = {spec.strike:g}, r = {spec.rate:.2%}, "
        f"q = {spec.dividend:.2%}, vol = {spec.vol:.2%}, T = {spec.time:g}"
    )


def _compare_tables(report: CompareReport) -> str:
    parts = [f"{describe(report.spec)}. Black-Scholes = {report.reference:.8f}."]
    for vr in dict.fromkeys(r.vr for r in report.rows):
        rows = [
            (
                r.backend,
                f"{r.paths:,}",
                f"{r.value:.6f}",
                _sci(r.stderr),
                _sci(r.abs_error),
                _seconds(r.seconds.median),
                _seconds(r.seconds.min),
                _seconds(r.seconds.max),
                _millions(r.paths_per_second),
                f"{r.cpu_per_wall:.2f}",
            )
            for r in report.rows
            if r.vr == vr
        ]
        headers = (
            "Back end",
            "Paths",
            "Price",
            "Std. error",
            "Abs. error vs BS",
            "Run time, median (s)",
            "min (s)",
            "max (s)",
            "Paths / s",
            "CPU / wall",
        )
        parts.append(f"**{VR_LABELS[vr_name(vr)]}**\n\n" + _md_table(headers, rows))
    ratios = report.speed_ratios()
    if ratios:
        parts.append(
            "**Speed ratios** (same paths; above 1 means the first back end is faster)\n\n"
            + _ratio_table(report)
        )
    if report.skipped:
        parts.append(
            "**Not run**\n\n"
            + "\n".join(
                f"- {s.backend}, {s.paths:,} paths, {VR_LABELS[vr_name(s.vr)].lower()}: {s.reason}"
                for s in report.skipped
            )
        )
    return "\n\n".join(parts)


def _ratio_table(report: CompareReport) -> str:
    pairs = list(dict.fromkeys((fast, base) for _, _, fast, base, _ in report.speed_ratios()))
    lookup = {(vr, paths, fast, base): x for vr, paths, fast, base, x in report.speed_ratios()}
    rows = []
    for vr, paths in dict.fromkeys((r.vr, r.paths) for r in report.rows):
        cells = []
        for fast, base in pairs:
            ratio = lookup.get((vr, paths, fast, base))
            cells.append("not run" if ratio is None else _times(ratio))
        rows.append((VR_LABELS[vr_name(vr)], f"{paths:,}", *cells))
    headers = ("Variance reduction", "Paths", *(f"{fast} vs {base}" for fast, base in pairs))
    return _md_table(headers, rows)


def _budget_tables(report: BudgetReport) -> str:
    names = list(dict.fromkeys(r.backend for r in report.rows))
    by_key = {(r.vr, r.budget, r.backend): r for r in report.rows}
    summary = []
    detail = []
    for vr in dict.fromkeys(r.vr for r in report.rows):
        for budget in report.budgets:
            cells = [_sci(by_key[(vr, budget, n)].stderr) for n in names]
            summary.append((VR_LABELS[vr_name(vr)], f"{budget:g} s", *cells))
            for n in names:
                r = by_key[(vr, budget, n)]
                detail.append(
                    (
                        VR_LABELS[vr_name(vr)],
                        f"{budget:g} s",
                        n,
                        f"{r.paths:,}",
                        _seconds(r.seconds),
                        f"{r.value:.6f}",
                        _sci(r.stderr),
                        _sci(r.abs_error),
                    )
                )
    parts = [
        f"{describe(report.spec)}. Black-Scholes = {report.reference:.8f}.",
        "**Standard error reached in a fixed time** (smaller is better)\n\n"
        + _md_table(("Variance reduction", "Time budget", *names), summary, left=2),
        "**Detail of each budget run**\n\n"
        + _md_table(
            (
                "Variance reduction",
                "Time budget",
                "Back end",
                "Paths",
                "Measured time (s)",
                "Price",
                "Std. error",
                "Abs. error vs BS",
            ),
            detail,
            left=3,
        ),
    ]
    return "\n\n".join(parts)


def _calibration_table(report: BudgetReport) -> str:
    rows = [
        (
            VR_LABELS[vr_name(c.vr)],
            c.backend,
            f"{c.paths:,}",
            _seconds(c.seconds.median),
            _seconds(c.seconds.min),
            _seconds(c.seconds.max),
            _millions(c.paths_per_second),
        )
        for c in report.calibrations
    ]
    headers = (
        "Variance reduction",
        "Back end",
        "Calibration paths",
        "Run time, median (s)",
        "min (s)",
        "max (s)",
        "Paths / s",
    )
    return _md_table(headers, rows, left=2)


# --------------------------------------------------------------------------------------
# Plot and written report
# --------------------------------------------------------------------------------------

# One fixed colour per back end, so a back end keeps its colour when another is missing.
_SERIES_COLOURS = {"python": "#2a78d6", "numpy": "#eb6834", "cpp": "#1baf7a"}
_SURFACE = "#fcfcfb"
_INK = "#0b0b0b"
_INK_SECONDARY = "#52514e"
_INK_MUTED = "#898781"
_GRID = "#e1e0d9"
_AXIS = "#c3c2b7"


def require_matplotlib():
    """Import matplotlib or explain how to get it. Call before a long run that ends in a plot."""
    try:
        import matplotlib
    except ImportError as exc:
        raise RuntimeError("the plot needs matplotlib (pip install matplotlib)") from exc
    return matplotlib


def plot_accuracy_vs_time(report: BudgetReport, path: str | os.PathLike[str]) -> None:
    """Save the accuracy-per-second view as a PNG: one panel per variance-reduction method."""
    matplotlib = require_matplotlib()
    matplotlib.use("Agg")  # draw straight to a file; no window needed
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedFormatter, FixedLocator, NullLocator

    methods = list(dict.fromkeys(r.vr for r in report.rows))
    names = list(dict.fromkeys(r.backend for r in report.rows))
    cols = 2 if len(methods) > 1 else 1
    nrows = math.ceil(len(methods) / cols)
    fonts = {
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Arial", "DejaVu Sans"],
    }

    def points(vr: VarianceReduction, name: str) -> list[tuple[float, float]]:
        """(measured seconds, standard error) for one line, in time order."""
        rows = (r for r in report.rows if r.vr == vr and r.backend == name)
        return sorted((r.seconds, r.stderr) for r in rows)

    width, height = max(4.8 * cols, 7.6), 3.0 * nrows + 2.0  # inches
    with plt.rc_context(fonts):
        fig, axes = plt.subplots(
            nrows, cols, sharex=True, sharey=True, squeeze=False, figsize=(width, height)
        )
        fig.patch.set_facecolor(_SURFACE)
        # Margins in inches, so the header and axis titles keep their size at any grid shape.
        fig.subplots_adjust(
            left=0.95 / width,
            right=1.0 - 0.25 / width,
            top=1.0 - 1.35 / height,
            bottom=0.85 / height,
            hspace=0.32,
            wspace=0.06,
        )
        budgets = sorted(report.budgets)
        for ax, vr in zip(axes.flat, methods):
            ax.set_facecolor(_SURFACE)
            for name in names:
                pts = points(vr, name)
                xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                ax.plot(
                    xs,
                    ys,
                    color=_SERIES_COLOURS.get(name, _INK_MUTED),
                    linewidth=2,
                    solid_capstyle="round",
                    solid_joinstyle="round",
                    marker="o",
                    markersize=7,
                    markeredgecolor=_SURFACE,
                    markeredgewidth=1.5,
                    label=name,
                    zorder=3,
                )
            ax.set_xscale("log")
            ax.set_yscale("log")
            ax.set_xlim(min(budgets) / 2.0, max(budgets) * 5.0)  # room on the right for labels
            ax.xaxis.set_major_locator(FixedLocator(budgets))
            ax.xaxis.set_major_formatter(FixedFormatter([f"{b:g} s" for b in budgets]))
            ax.xaxis.set_minor_locator(NullLocator())
            ax.yaxis.set_minor_locator(NullLocator())
            ax.set_title(VR_LABELS[vr_name(vr)], loc="left", fontsize=10.5, color=_INK, pad=8)
            ax.grid(True, which="major", color=_GRID, linewidth=0.8)
            ax.set_axisbelow(True)
            for side in ("top", "right"):
                ax.spines[side].set_visible(False)
            for side in ("left", "bottom"):
                ax.spines[side].set_color(_AXIS)
            ax.tick_params(colors=_INK_MUTED, labelsize=9, length=0)
        for ax in axes.flat[len(methods):]:
            ax.set_visible(False)

        # Name each line at its right-hand end. This runs after every panel is drawn
        # because the shared axis limits are only final then. Labels share one x position,
        # and labels closer than one line of text are spread apart just enough to be read.
        min_gap = 11.0 * fig.dpi / 72.0  # 11 points, in pixels
        for ax, vr in zip(axes.flat, methods):
            ends = []
            for name in names:
                last = points(vr, name)[-1]
                ends.append([ax.transData.transform(last)[1], last[0], name])
            ends.sort()
            for lower, upper in zip(ends, ends[1:]):
                upper[0] = max(upper[0], lower[0] + min_gap)
            x_label = max(end[1] for end in ends)
            for y_pixels, _, name in ends:
                y_data = ax.transData.inverted().transform((0.0, y_pixels))[1]
                ax.annotate(
                    name,
                    (x_label, y_data),
                    xytext=(9, 0),
                    textcoords="offset points",
                    va="center",
                    fontsize=9,
                    color=_INK_SECONDARY,
                )
        left = 0.3 / width
        fig.text(
            left,
            1.0 - 0.42 / height,
            "Standard error reached in a fixed time budget",
            fontsize=13,
            fontweight="bold",
            color=_INK,
        )
        fig.text(
            left,
            1.0 - 0.72 / height,
            f"{describe(report.spec)}. Single thread. Lower is better.",
            fontsize=9.5,
            color=_INK_SECONDARY,
        )
        handles, labels = axes.flat[0].get_legend_handles_labels()
        fig.legend(
            handles,
            labels,
            loc="upper right",
            bbox_to_anchor=(1.0 - 0.15 / width, 1.0 - 0.18 / height),
            ncol=len(names),
            frameon=False,
            fontsize=9.5,
            labelcolor=_INK_SECONDARY,
            handlelength=1.6,
            columnspacing=1.4,
        )
        fig.supxlabel(
            "Time budget (points sit at the measured run time)",
            fontsize=9.5,
            color=_INK_SECONDARY,
            y=0.22 / height,
        )
        fig.supylabel(
            "Standard error of the price", fontsize=9.5, color=_INK_SECONDARY, x=0.3 / width
        )
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=200, facecolor=_SURFACE)
        plt.close(fig)


def write_report(
    path: str | os.PathLike[str],
    command: str,
    fixed: CompareReport | None,
    budget: BudgetReport | None,
    plot: str | os.PathLike[str] | None = None,
) -> None:
    """Write the measurements, the exact command and the environment to a Markdown file."""
    path = Path(path)
    first = fixed or budget
    if first is None:
        raise ValueError("nothing to report")
    out = [
        "# Monte Carlo back-end comparison",
        "Every number in this file was measured on the machine described below by the command "
        "shown. Nothing is estimated or carried over from another machine.",
        "## How this was produced",
        f"```bash\n{command}\n```",
        f"Run finished {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z')}.",
        _md_table(("Item", "Value"), environment().items(), left=2),
        "## What was priced",
        f"{describe(first.spec)}. Black-Scholes closed form = {first.reference:.12f}.",
        "## Method",
        "\n".join(_method_notes(fixed, budget)),
    ]
    if budget is not None:
        out.append("## Accuracy per second (the main result)")
        if plot is not None:
            image = os.path.relpath(plot, path.parent)
            out.append(f"![Standard error against time budget]({image})")
        out.append(budget.table().split("\n\n", 1)[1])
        out.append("**Calibration behind the budgets**\n\n" + _calibration_table(budget))
    if fixed is not None:
        out.append("## Fixed path counts")
        out.append(fixed.table().split("\n\n", 1)[1])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(out) + "\n")


def _method_notes(fixed: CompareReport | None, budget: BudgetReport | None) -> list[str]:
    first = fixed or budget
    pinned = (
        "BLAS and OpenMP were pinned to one thread before NumPy was imported."
        if first.threads_pinned
        else "NumPy was already imported, so BLAS could not be pinned to one thread."
    )
    notes = [
        "- Every back end is called through the same public function, "
        "`derivkit.monte_carlo.european(spec, cfg, backend=...)`, with the same option, seed, "
        "path count and variance-reduction setting.",
        "- python and cpp use the same generator (mt19937_64 + Box-Muller), so with one seed "
        "they produce the same price. numpy uses its own generator (PCG64), so its price "
        "differs within the standard error.",
        f"- Single thread. {pinned} The CPU / wall column is process CPU time divided by "
        "wall time: 1.00 means one busy thread.",
        "- Timer: `time.perf_counter()` around the call. Garbage collection is left on.",
        "- Abs. error vs BS is the error of that one run. It is a single draw from a "
        "distribution whose width is the standard error, so the standard error is the "
        "steadier measure of accuracy.",
    ]
    if fixed is not None:
        notes.append(
            f"- Fixed path counts: {fixed.warmup} untimed warm-up run, then {fixed.repeats} "
            "timed runs; the table shows the median, minimum and maximum. Paths / s is paths "
            "divided by the median."
        )
    if budget is not None:
        notes.append(
            f"- Time budgets: the paths-per-second rate is measured first ({budget.warmup} "
            f"warm-up, then the median of {budget.repeats} runs, shown in the calibration "
            "table). Each budget is then one run of rate x budget paths; the table shows "
            "the time that run really took."
        )
    return notes
