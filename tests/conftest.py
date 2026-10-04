import os

import pytest

from derivkit.backends import BACKENDS, available_backends

# CI sets DERIVKIT_REQUIRE_BACKENDS=numpy,cpp on the job that builds the extension, so a
# back end that silently failed to build shows up as a failure instead of a skip.
REQUIRED = {b for b in os.environ.get("DERIVKIT_REQUIRE_BACKENDS", "").split(",") if b}


def require_backend(name: str) -> str:
    if name not in available_backends():
        if name in REQUIRED:
            pytest.fail(f"back end {name!r} is required by DERIVKIT_REQUIRE_BACKENDS but unavailable")
        pytest.skip(f"back end {name!r} is not available")
    return name


@pytest.fixture(params=BACKENDS)
def backend(request) -> str:
    """Run the test once per Monte Carlo back end, skipping those not installed."""
    return require_backend(request.param)
