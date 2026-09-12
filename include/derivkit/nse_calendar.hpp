#pragma once

#include <chrono>
#include <string>

namespace derivkit::nse {

/// NSE equity / F&O session: 09:15-15:30 IST (UTC+05:30).
constexpr std::chrono::minutes kIstOffset{5 * 60 + 30};
constexpr std::chrono::minutes kOpenIst{9 * 60 + 15};
constexpr std::chrono::minutes kCloseIst{15 * 60 + 30};
constexpr double kSessionHours = 6.25;
constexpr double kVolYearTradingDays = 252.0;
constexpr double kRateYearDays = 365.25;

[[nodiscard]] bool is_trading_day(std::chrono::year_month_day ymd);
[[nodiscard]] bool is_trading_day(const std::string& iso_date);

[[nodiscard]] std::chrono::year_month_day parse_iso_date(const std::string& iso_date);

/// Previous (or same-day) session close used as the print time of the LTP.
[[nodiscard]] std::chrono::sys_seconds snap_as_of(std::chrono::system_clock::time_point now);

/// NSE F&O expiry print: 15:30 IST on `expiry_iso_date`.
[[nodiscard]] std::chrono::sys_seconds expiry_close(const std::string& expiry_iso_date);

struct Clock {
    std::chrono::sys_seconds as_of{};     ///< UTC
    std::chrono::sys_seconds expiry{};    ///< UTC
    std::string as_of_ist;
    std::string expiry_ist;
    double time_rate = 0.0;      ///< ACT/365.25, calendar (discounting)
    double time_vol = 0.0;       ///< NSE trading days / 252 (diffusion)
    double trading_days = 0.0;   ///< including a fraction of the current session
    bool snapped_to_close = false;
};

/// Snap `as_of` to the last print if the market is shut, then measure time to expiry.
[[nodiscard]] Clock clock_to_expiry(const std::string& expiry_iso_date,
                                    std::chrono::system_clock::time_point as_of =
                                        std::chrono::system_clock::now());

[[nodiscard]] std::string format_ist(std::chrono::sys_seconds utc);

}  // namespace derivkit::nse
