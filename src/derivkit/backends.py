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
"""

from __future__ import annotations

import importlib
from types import ModuleType

BACKENDS: tuple[str, ...] = ("python", "numpy", "cpp")

_HOW_TO_GET = {
    "numpy": "it needs NumPy (pip install numpy)",
    "cpp": (
        "it needs the compiled extension (pip install pybind11, then "
        "cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build; "
        "see 'Build the C++ back end' in README.md)"
    ),
}


class BackendUnavailableError(ImportError):
    """The requested Monte Carlo back end is not installed or not built."""


def kernel(backend: str) -> ModuleType:
    """Return the kernel module for `backend`, importing optional ones on first use."""
    if backend not in BACKENDS:
        choices = ", ".join(repr(b) for b in BACKENDS)
        raise ValueError(f"unknown backend {backend!r}; choose one of {choices}")
    if backend == "python":
        from derivkit import _mc_python

        return _mc_python
    try:
        return importlib.import_module(f"derivkit._mc_{backend}")
    except ImportError as exc:
        raise BackendUnavailableError(
            f"backend {backend!r} is not available: {_HOW_TO_GET[backend]}"
        ) from exc


def available_backends() -> tuple[str, ...]:
    """Back ends that can be used right now, in the order of `BACKENDS`."""
    found = []
    for name in BACKENDS:
        try:
            kernel(name)
        except BackendUnavailableError:
            continue
        found.append(name)
    return tuple(found)
