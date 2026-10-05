"""Monte Carlo back ends: one pricing API, three interchangeable kernels.

    "python"  standard library only, always available (the default and the reference)
    "numpy"   NumPy-vectorised; needs NumPy
    "cpp"     C++20 kernel behind a pybind11 extension; needs the extension to be built

A kernel is a module `derivkit._mc_<name>` with two entry points:

    EuropeanSampler(spec, seed, antithetic)    with .advance(paths) and .moments()
    asian_moments(spec, steps, paths, seed, antithetic)

Both report a `WelfordPair`. Validation, the control-variate finish and result naming are
shared code in `monte_carlo`, so the back ends cannot drift apart on anything but the
path loop itself.

The cpp kernel also has a choice of random number generator, `rng`:

    "reproducible"  the default: mt19937_64 + Box-Muller, the same stream as "python",
                    so the two return the same price for the same seed
    "fast"          xoshiro256++ + ziggurat: 1.6 to 1.9 times the paths per second
                    (benchmarks/RESULTS.md), and a stream of its own. Repeatable for a
                    seed, but it matches neither "python" nor "numpy" digit for digit

"python" and "numpy" have one generator each, so they accept only the default.
"""

from __future__ import annotations

import importlib
import warnings
from types import ModuleType

BACKENDS: tuple[str, ...] = ("python", "numpy", "cpp")
RNGS: tuple[str, ...] = ("reproducible", "fast")
DEFAULT_RNG = "reproducible"

_HOW_TO_GET = {
    "numpy": "it needs NumPy (pip install numpy)",
    "cpp": (
        "it needs the compiled extension (pip install pybind11, then "
        "cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build; "
        "see 'Build the C++ back end' in README.md)"
    ),
}


# The module whose absence means "not installed" or "not built". Any other import failure
# means the back end is there but broken, and the user needs to see the real error.
_OPTIONAL_MODULE = {"numpy": "numpy", "cpp": "derivkit._mc_cpp_ext"}


class BackendUnavailableError(ImportError):
    """The requested Monte Carlo back end is not installed, not built, or failed to load.

    `missing` is True when it is simply absent, False when it is present but broken.
    """

    def __init__(self, message: str, missing: bool = True) -> None:
        super().__init__(message)
        self.missing = missing


def kernel(backend: str) -> ModuleType:
    """Return the kernel module for `backend`, importing optional ones on first use."""
    if backend not in BACKENDS:
        choices = ", ".join(repr(b) for b in BACKENDS)
        raise ValueError(f"unknown backend {backend!r}; choose one of {choices}")
    if backend == "python":
        from derivkit import _mc_python

        return _mc_python
    module = f"derivkit._mc_{backend}"
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        absent = (module, _OPTIONAL_MODULE[backend])
        missing = isinstance(exc, ModuleNotFoundError) and exc.name in absent
        if missing:
            reason = _HOW_TO_GET[backend]
        else:
            reason = f"it is installed but failed to load ({type(exc).__name__}: {exc})"
        raise BackendUnavailableError(
            f"backend {backend!r} is not available: {reason}", missing=missing
        ) from exc


def rng_arguments(backend: str, rng: str) -> dict[str, str]:
    """Keyword arguments that select generator `rng` in the kernel for `backend`.

    The default needs none: it is each kernel's standard generator. Only the cpp kernel
    has another one, so asking any other back end for it is an error, not a silent
    fallback to a generator the caller did not choose.
    """
    if rng not in RNGS:
        choices = ", ".join(repr(r) for r in RNGS)
        raise ValueError(f"unknown rng {rng!r}; choose one of {choices}")
    if rng == DEFAULT_RNG:
        return {}
    if backend != "cpp":
        raise ValueError(
            f"rng={rng!r} needs backend='cpp'; backend {backend!r} has one generator"
        )
    return {"rng": rng}


def available_backends() -> tuple[str, ...]:
    """Back ends that can be used right now, in the order of `BACKENDS`.

    A back end that is present but fails to load is left out with a RuntimeWarning, so a
    broken build is not mistaken for one that was never installed.
    """
    found = []
    for name in BACKENDS:
        try:
            kernel(name)
        except BackendUnavailableError as exc:
            if not exc.missing:
                warnings.warn(str(exc), RuntimeWarning, stacklevel=2)
            continue
        found.append(name)
    return tuple(found)
