import os

import pytest

from derivkit.backends import BACKENDS, available_backends

# CI sets DERIVKIT_REQUIRE_BACKENDS=numpy,cpp on the job that builds the extension, so a
# back end that silently failed to build shows up as a failure instead of a skip.
REQUIRED = {
    name.strip()
    for name in os.environ.get("DERIVKIT_REQUIRE_BACKENDS", "").split(",")
    if name.strip()
}
if REQUIRED - set(BACKENDS):
    # A typo here would quietly turn "required" back into "skipped".
    raise pytest.UsageError(
        f"DERIVKIT_REQUIRE_BACKENDS names unknown back ends {sorted(REQUIRED - set(BACKENDS))}; "
        f"choose from {', '.join(BACKENDS)}"
    )


def require_backend(name: str) -> str:
    if name not in available_backends():
        if name in REQUIRED:
            pytest.fail(f"back end {name!r} is required by DERIVKIT_REQUIRE_BACKENDS but missing")
        pytest.skip(f"back end {name!r} is not available")
    return name


def usable_backends() -> tuple[str, ...]:
    """Back ends to compare with each other: the available ones plus any that are required.

    A required back end that is missing stays in the list, so using it raises instead of
    quietly dropping out of the comparison.
    """
    available = available_backends()
    return tuple(b for b in BACKENDS if b in available or b in REQUIRED)


@pytest.fixture(params=BACKENDS)
def backend(request) -> str:
    """Run the test once per Monte Carlo back end, skipping those not installed."""
    return require_backend(request.param)


@pytest.fixture
def cpp_backend() -> str:
    return require_backend("cpp")
