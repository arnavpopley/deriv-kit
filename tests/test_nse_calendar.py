from datetime import datetime, timezone

from derivkit.nse_calendar import clock_to_expiry, expiry_close, format_ist, is_trading_day, snap_as_of


def test_nse_calendar():
    assert is_trading_day("2026-09-11")
    assert not is_trading_day("2026-09-12")
    assert not is_trading_day("2026-09-13")
    assert not is_trading_day("2026-09-14")
    assert is_trading_day("2026-09-15")
    assert is_trading_day("2026-11-08")

    fri_close = expiry_close("2026-09-11")
    assert format_ist(fri_close) == "2026-09-11 15:30 IST"

    sat_utc = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
    assert snap_as_of(sat_utc) == fri_close

    clk = clock_to_expiry("2026-09-15", sat_utc)
    assert clk.snapped_to_close
    assert clk.as_of == fri_close
    assert abs(clk.trading_days - 1.0) <= 1e-12
    assert abs(clk.time_vol - 1.0 / 252.0) <= 1e-12
    assert abs(clk.time_rate - 4.0 / 365.25) <= 1e-12

    clk = clock_to_expiry("2026-09-15", fri_close)
    assert not clk.snapped_to_close
    assert abs(clk.trading_days - 1.0) <= 1e-12
    assert abs(clk.time_vol - 1.0 / 252.0) <= 1e-12
