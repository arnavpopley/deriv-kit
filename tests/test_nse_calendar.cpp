#include "derivkit/nse_calendar.hpp"
#include "harness.hpp"

#include <chrono>
#include <string>

int main() {
    using namespace std::chrono;
    using derivkit::nse::clock_to_expiry;
    using derivkit::nse::expiry_close;
    using derivkit::nse::format_ist;
    using derivkit::nse::is_trading_day;
    using derivkit::nse::snap_as_of;

    CHECK(is_trading_day("2026-09-11"));
    CHECK(!is_trading_day("2026-09-12"));  // Saturday
    CHECK(!is_trading_day("2026-09-13"));  // Sunday
    CHECK(!is_trading_day("2026-09-14"));  // Ganesh Chaturthi
    CHECK(is_trading_day("2026-09-15"));
    CHECK(is_trading_day("2026-11-08"));  // Muhurat session

    const auto fri_close = expiry_close("2026-09-11");
    CHECK(format_ist(fri_close) == "2026-09-11 15:30 IST");

    // Saturday afternoon IST is shut; snap to Friday's 15:30 IST print.
    const sys_seconds sat_utc{sys_days{year{2026} / 9 / 12} + hours{12}};  // 17:30 IST
    const auto snapped = snap_as_of(sat_utc);
    CHECK(snapped == fri_close);

    auto clk = clock_to_expiry("2026-09-15", sat_utc);
    CHECK(clk.snapped_to_close);
    CHECK(clk.as_of == fri_close);
    CHECK_NEAR(clk.trading_days, 1.0, 1e-12);
    CHECK_NEAR(clk.time_vol, 1.0 / 252.0, 1e-12);
    CHECK_NEAR(clk.time_rate, 4.0 / 365.25, 1e-12);

    // Already at Friday close: no further snap. Mon 14 is a holiday, so only
    // Tuesday 15 remains as a trading day into the weekly expiry.
    clk = clock_to_expiry("2026-09-15", fri_close);
    CHECK(!clk.snapped_to_close);
    CHECK_NEAR(clk.trading_days, 1.0, 1e-12);
    CHECK_NEAR(clk.time_vol, 1.0 / 252.0, 1e-12);

    return derivkit::test::summarize("test_nse_calendar");
}
