#include "derivkit/nse_calendar.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>

namespace derivkit::nse {
namespace {

using namespace std::chrono;

constexpr int ymd_key(year_month_day ymd) {
    return static_cast<int>(ymd.year()) * 10000 +
           static_cast<int>(static_cast<unsigned>(ymd.month())) * 100 +
           static_cast<int>(static_cast<unsigned>(ymd.day()));
}

year_month_day ist_date(sys_seconds utc) {
    return year_month_day{floor<days>(utc + kIstOffset)};
}

minutes ist_tod(sys_seconds utc) {
    const auto ist = utc + kIstOffset;
    return duration_cast<minutes>(ist - floor<days>(ist));
}

sys_seconds ist_on(year_month_day ymd, minutes tod) {
    return sys_seconds{sys_days{ymd} + (tod - kIstOffset)};
}

bool is_weekend(year_month_day ymd) {
    const weekday wd{sys_days{ymd}};
    return wd == Saturday || wd == Sunday;
}

// NSE cash + F&O weekday holidays, calendar 2026 (Muhurat 8 Nov counted as open).
constexpr std::array<int, 16> kHolidays2026 = {
    20260115, 20260126, 20260303, 20260326, 20260331, 20260403, 20260414, 20260501,
    20260528, 20260626, 20260914, 20261002, 20261020, 20261110, 20261124, 20261225};

year_month_day prev_calendar_day(year_month_day ymd) {
    return year_month_day{sys_days{ymd} - days{1}};
}

}  // namespace

bool is_trading_day(year_month_day ymd) {
    if (!ymd.ok()) {
        return false;
    }
    const int key = ymd_key(ymd);
    if (key == 20261108) {  // Diwali Laxmi Pujan Muhurat session
        return true;
    }
    if (is_weekend(ymd)) {
        return false;
    }
    return std::find(kHolidays2026.begin(), kHolidays2026.end(), key) == kHolidays2026.end();
}

bool is_trading_day(const std::string& iso_date) { return is_trading_day(parse_iso_date(iso_date)); }

year_month_day parse_iso_date(const std::string& iso_date) {
    if (iso_date.size() < 10) {
        throw std::invalid_argument("date must be YYYY-MM-DD");
    }
    const int y = std::stoi(iso_date.substr(0, 4));
    const unsigned m = static_cast<unsigned>(std::stoi(iso_date.substr(5, 2)));
    const unsigned d = static_cast<unsigned>(std::stoi(iso_date.substr(8, 2)));
    const year_month_day ymd{year{y} / month{m} / day{d}};
    if (!ymd.ok()) {
        throw std::invalid_argument("invalid calendar date: " + iso_date);
    }
    return ymd;
}

sys_seconds expiry_close(const std::string& expiry_iso_date) {
    return ist_on(parse_iso_date(expiry_iso_date), kCloseIst);
}

sys_seconds snap_as_of(system_clock::time_point now) {
    auto utc = time_point_cast<seconds>(now);
    auto ymd = ist_date(utc);
    const minutes tod = ist_tod(utc);

    if (is_trading_day(ymd)) {
        if (tod >= kCloseIst) {
            return ist_on(ymd, kCloseIst);
        }
        if (tod >= kOpenIst) {
            return utc;
        }
    }
    ymd = prev_calendar_day(ymd);
    while (!is_trading_day(ymd)) {
        ymd = prev_calendar_day(ymd);
    }
    return ist_on(ymd, kCloseIst);
}

std::string format_ist(sys_seconds utc) {
    const auto ist = utc + kIstOffset;
    const year_month_day ymd{floor<days>(ist)};
    const auto tod = ist - sys_seconds{sys_days{ymd}};
    const auto hh = duration_cast<hours>(tod);
    const auto mm = duration_cast<minutes>(tod - hh);
    std::ostringstream oss;
    oss << static_cast<int>(ymd.year()) << '-' << std::setw(2) << std::setfill('0')
        << static_cast<unsigned>(ymd.month()) << '-' << std::setw(2)
        << static_cast<unsigned>(ymd.day()) << ' ' << std::setw(2) << hh.count() << ':'
        << std::setw(2) << mm.count() << " IST";
    return oss.str();
}

double trading_days_remaining(sys_seconds as_of, sys_seconds expiry) {
    if (as_of >= expiry) {
        return 1.0 / (kVolYearTradingDays * 24.0);  // one hour of vol time
    }
    double remaining = 0.0;
    const auto as_of_ymd = ist_date(as_of);
    if (is_trading_day(as_of_ymd)) {
        const auto close = ist_on(as_of_ymd, kCloseIst);
        if (as_of < close) {
            const auto open = ist_on(as_of_ymd, kOpenIst);
            const auto start = as_of < open ? open : as_of;
            const double hours = duration<double, std::ratio<3600>>(close - start).count();
            remaining += std::clamp(hours / kSessionHours, 0.0, 1.0);
        }
    }

    auto d = as_of_ymd;
    const auto expiry_ymd = ist_date(expiry);
    d = year_month_day{sys_days{d} + std::chrono::days{1}};
    while (d <= expiry_ymd) {
        if (is_trading_day(d)) {
            remaining += 1.0;
        }
        d = year_month_day{sys_days{d} + std::chrono::days{1}};
    }
    return std::max(remaining, 1.0 / (kVolYearTradingDays * 24.0));
}

Clock clock_to_expiry(const std::string& expiry_iso_date, system_clock::time_point as_of_in) {
    Clock c;
    const auto raw = time_point_cast<seconds>(as_of_in);
    c.as_of = snap_as_of(as_of_in);
    c.snapped_to_close = c.as_of != raw;
    c.expiry = expiry_close(expiry_iso_date);
    c.as_of_ist = format_ist(c.as_of);
    c.expiry_ist = format_ist(c.expiry);
    const double secs = duration<double>(c.expiry - c.as_of).count();
    c.time_rate = std::max(secs / (kRateYearDays * 24.0 * 3600.0), 1.0 / (kRateYearDays * 24.0));
    c.trading_days = trading_days_remaining(c.as_of, c.expiry);
    c.time_vol = c.trading_days / kVolYearTradingDays;
    return c;
}

}  // namespace derivkit::nse
