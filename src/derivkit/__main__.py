"""`python -m derivkit <command>`. The one command so far is `compare`."""

from __future__ import annotations

import argparse
import shlex
import sys

from derivkit.backends import BACKENDS, BackendUnavailableError
from derivkit.comparison import (
    DEFAULT_BUDGETS,
    VR_METHODS,
    accuracy_per_second,
    compare,
    pin_to_one_thread,
    plot_accuracy_vs_time,
    require_matplotlib,
    write_report,
)
from derivkit.monte_carlo import McConfig
from derivkit.types import OptionType, VanillaSpec


def _count(text: str) -> int:
    """A path count; accepts 100000, 1e5 or 100_000."""
    value = float(text)
    if value != int(value) or value < 2:
        raise argparse.ArgumentTypeError(f"{text!r} is not a whole number of paths (at least 2)")
    return int(value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m derivkit", description="derivkit command line."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser(
        "compare",
        help="price one option with every Monte Carlo back end and compare accuracy and speed",
        description=(
            "Price one European option with every available Monte Carlo back end (python, "
            "numpy, cpp) and print price, standard error, error against Black-Scholes, run "
            "time and paths per second. With --budgets, also show the error each back end "
            "reaches in a fixed time."
        ),
    )
    option = c.add_argument_group("option")
    option.add_argument("--spot", type=float, default=100.0)
    option.add_argument("--strike", type=float, default=100.0)
    option.add_argument("--rate", type=float, default=0.05)
    option.add_argument("--dividend", type=float, default=0.0)
    option.add_argument("--vol", type=float, default=0.20)
    option.add_argument("--time", type=float, default=1.0)
    option.add_argument("--type", choices=("call", "put"), default="call")
    run = c.add_argument_group("what to run")
    run.add_argument(
        "--paths", type=_count, nargs="+", default=[100_000], metavar="N",
        help="path counts for the fixed-paths table, e.g. 1e5 1e6 1e7 (default: 1e5)",
    )
    run.add_argument("--seed", type=int, default=1)
    run.add_argument(
        "--vr", nargs="+", choices=(*VR_METHODS, "all"), default=["none"],
        help="variance-reduction methods to run (default: none)",
    )
    run.add_argument(
        "--backends", nargs="+", choices=BACKENDS, default=None,
        help="back ends to compare (default: every one that is available)",
    )
    run.add_argument(
        "--budgets", type=float, nargs="*", default=None, metavar="SECONDS",
        help="also run the accuracy-per-second view for these time budgets "
        f"(with no values: {' '.join(f'{b:g}' for b in DEFAULT_BUDGETS)})",
    )
    run.add_argument(
        "--repeats", type=int, default=7, help="timed runs per measurement (default: 7)"
    )
    run.add_argument(
        "--max-run-seconds", type=float, default=120.0,
        help="skip a back end at a path count if one run is estimated to take longer "
        "(default: 120)",
    )
    out = c.add_argument_group("output")
    out.add_argument(
        "--report", metavar="FILE.md", help="also write the results to a Markdown file"
    )
    out.add_argument(
        "--plot", metavar="FILE.png", help="save the accuracy-per-second plot (needs --budgets)"
    )
    return parser


def _progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _compare(args: argparse.Namespace, argv: list[str]) -> int:
    pin_to_one_thread()  # before anything imports NumPy
    spec = VanillaSpec(
        spot=args.spot,
        strike=args.strike,
        rate=args.rate,
        dividend=args.dividend,
        vol=args.vol,
        time=args.time,
        type=OptionType.CALL if args.type == "call" else OptionType.PUT,
    )
    names = list(VR_METHODS) if "all" in args.vr else list(dict.fromkeys(args.vr))
    methods = [VR_METHODS[n] for n in names]
    budgets = None if args.budgets is None else (tuple(args.budgets) or DEFAULT_BUDGETS)
    if args.plot and budgets is None:
        print("error: --plot needs --budgets", file=sys.stderr)
        return 2
    if args.plot:
        try:
            require_matplotlib()  # fail now, not after a long benchmark
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    configs = [McConfig(paths=n, seed=args.seed, vr=vr) for vr in methods for n in args.paths]
    try:
        fixed = compare(
            spec,
            configs,
            backends=args.backends,
            repeats=args.repeats,
            max_run_seconds=args.max_run_seconds,
            progress=_progress,
        )
        print(fixed.table())
        budget = None
        if budgets is not None:
            budget = accuracy_per_second(
                spec,
                budgets,
                seed=args.seed,
                vr_methods=methods,
                backends=args.backends,
                repeats=args.repeats,
                progress=_progress,
            )
            print()
            print(budget.table())
    except (BackendUnavailableError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.plot:
        plot_accuracy_vs_time(budget, args.plot)
        _progress(f"wrote {args.plot}")
    if args.report:
        command = "python -m derivkit " + shlex.join(argv)
        write_report(args.report, command, fixed, budget, args.plot)
        _progress(f"wrote {args.report}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = _parser().parse_args(argv)
    return _compare(args, argv)


if __name__ == "__main__":
    raise SystemExit(main())
