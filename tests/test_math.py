from derivkit.math import norm_cdf, norm_inv, norm_pdf, norm_sf


def test_norm_basics():
    assert abs(norm_cdf(0.0) - 0.5) <= 1e-15
    assert abs(norm_cdf(1.0) - 0.8413447460685429) <= 1e-14
    assert abs(norm_cdf(-1.0) - 0.15865525393145705) <= 1e-14
    assert abs(norm_pdf(0.0) - 0.3989422804014327) <= 1e-15
    assert abs(norm_sf(1.0) - (1.0 - norm_cdf(1.0))) <= 1e-15


def test_norm_inv_roundtrip():
    for i in range(1, 40):
        p = 2.0 ** (-i)
        if p == 0.0:
            continue
        assert abs(norm_cdf(norm_inv(p)) - p) <= 1e-14
        assert abs(norm_cdf(norm_inv(1.0 - p)) - (1.0 - p)) <= 1e-14
    for i in range(1, 20):
        p = 0.05 * i
        assert abs(norm_inv(norm_cdf(norm_inv(p))) - norm_inv(p)) <= 1e-12


def test_norm_inv_rejects_zero():
    try:
        norm_inv(0.0)
    except ValueError:
        return
    raise AssertionError("expected ValueError")
