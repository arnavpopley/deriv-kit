#pragma once

#include "derivkit/types.hpp"

#include <string>
#include <vector>

namespace derivkit::groww {

struct Contract {
    std::string trading_symbol;
    double strike = 0.0;
    OptionType type = OptionType::Call;
    double ltp = 0.0;
    double open_interest = 0.0;
    double volume = 0.0;
    double groww_iv = 0.0;     ///< decimal (Groww sends percent)
    double groww_delta = 0.0;
    double groww_gamma = 0.0;
    double groww_theta = 0.0;  ///< per day, Groww units
    double groww_vega = 0.0;   ///< per 1 vol-point, Groww units
    double groww_rho = 0.0;
};

struct Chain {
    std::string source;  ///< "live" or "fixture"
    std::string underlying;
    std::string exchange = "NSE";
    std::string expiry_date;  ///< YYYY-MM-DD
    double spot = 0.0;
    double rate = 0.065;
    double dividend = 0.012;
    double year_fraction = 0.0;  ///< 0 → compute from expiry vs now
    std::vector<Contract> contracts;
};

struct ClientConfig {
    std::string access_token;
    std::string api_key;
    std::string api_secret;
    std::string totp;
    std::string exchange = "NSE";
    std::string underlying = "NIFTY";
    std::string expiry_date;  ///< empty → nearest listed expiry
    std::string fixture_path;
    bool force_fixture = false;
};

[[nodiscard]] ClientConfig from_env();

/// Parse a Groww option-chain JSON body (live payload or the bundled fixture).
[[nodiscard]] Chain parse_option_chain(const std::string& json_text);

[[nodiscard]] Chain load_fixture(const std::string& path);

/// Resolve a bearer token: `GROWW_ACCESS_TOKEN`, or API key + secret/TOTP.
[[nodiscard]] std::string resolve_access_token(const ClientConfig& cfg);

[[nodiscard]] std::vector<std::string> list_expiries(const ClientConfig& cfg,
                                                     const std::string& token);

[[nodiscard]] std::string nearest_expiry(const std::vector<std::string>& dates,
                                         const std::string& today_iso);

/// Live Groww option chain, or the bundled fixture if no credentials are set.
[[nodiscard]] Chain load_chain(const ClientConfig& cfg);

[[nodiscard]] double years_to_expiry(const std::string& expiry_iso_date);

}  // namespace derivkit::groww
