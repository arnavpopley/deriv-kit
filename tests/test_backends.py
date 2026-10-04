"""Back-end selection: defaults, error messages and the zero-dependency guarantee."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from derivkit import BACKENDS, BackendUnavailableError, available_backends
from derivkit.monte_carlo import (
    AdaptiveMcConfig,
    AsianConfig,
    McConfig,
    arithmetic_asian,
    european,
    european_adaptive,
)
from derivkit.types import OptionType, VanillaSpec

SRC = Path(__file__).resolve().parents[1] / "src"

SPEC = VanillaSpec(
    spot=100.0, strike=100.0, rate=0.05, dividend=0.0, vol=0.2, time=1.0, type=OptionType.CALL
)


def test_python_is_always_available_and_first():
    assert BACKENDS == ("python", "numpy", "cpp")
    assert available_backends()[0] == "python"


def test_default_backend_is_python():
    cfg = McConfig(paths=2000, seed=5)
    assert european(SPEC, cfg) == european(SPEC, cfg, backend="python")
    acfg = AdaptiveMcConfig(base=McConfig(seed=5), stderr_tol=0.2, batch=500, max_paths=4000)
    assert european_adaptive(SPEC, acfg) == european_adaptive(SPEC, acfg, backend="python")
    asian = AsianConfig(mc=McConfig(paths=200, seed=5), steps=10)
    assert arithmetic_asian(SPEC, asian) == arithmetic_asian(SPEC, asian, backend="python")


@pytest.mark.parametrize("engine", [european, european_adaptive, arithmetic_asian])
def test_unknown_backend_is_a_value_error(engine):
    with pytest.raises(ValueError, match="unknown backend 'fortran'"):
        engine(SPEC, backend="fortran")


@pytest.mark.parametrize(
    ("name", "hint"), [("numpy", "pip install numpy"), ("cpp", "cmake --build build")]
)
def test_unavailable_backend_says_how_to_get_it(monkeypatch, name, hint):
    # A None entry in sys.modules makes the import fail, as if the module were absent.
    monkeypatch.setitem(sys.modules, f"derivkit._mc_{name}", None)
    with pytest.raises(BackendUnavailableError, match=hint) as excinfo:
        european(SPEC, McConfig(paths=10), backend=name)
    assert f"backend {name!r} is not available" in str(excinfo.value)
    assert name not in available_backends()


def test_core_works_without_numpy_or_the_extension():
    """In a fresh interpreter with NumPy and the extension blocked, the default path prices
    and never tries to import either; asking for them raises the documented error."""
    script = """
import sys
sys.modules["numpy"] = None
sys.modules["derivkit._mc_cpp_ext"] = None
import derivkit
from derivkit.monte_carlo import McConfig, european
spec = derivkit.VanillaSpec(spot=100.0, strike=100.0, rate=0.05, vol=0.2, time=1.0)
result = european(spec, McConfig(paths=1000, seed=1))
assert result.work == 1000 and result.value > 0.0
assert derivkit.available_backends() == ("python",)
for name in ("numpy", "cpp"):
    try:
        european(spec, McConfig(paths=1000), backend=name)
    except derivkit.BackendUnavailableError:
        continue
    raise SystemExit(f"{name} should have been unavailable")
loaded = [m for m in sys.modules if m.startswith("derivkit._mc_") and sys.modules[m] is not None]
assert loaded == ["derivkit._mc_python"], loaded
print("ok")
"""
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    done = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, env=env, check=False
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "ok"
