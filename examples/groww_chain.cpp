#include "derivkit/derivkit.hpp"
#include "groww_api.hpp"

#include "nlohmann/json.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

#ifndef DERIVKIT_FIXTURE
#define DERIVKIT_FIXTURE "examples/data/nifty_chain.json"
#endif

namespace {

struct Args {
    derivkit::groww::ClientConfig client;
    int nearby = 5;
    bool run_mc = false;
    bool json_out = false;
    bool help = false;
    std::optional<double> rate;
    std::optional<double> dividend;
    std::optional<std::string> as_of;  // YYYY-MM-DD, session close that day
};

void usage() {
    std::cout
        << "Price a Groww option chain with derivkit.\n\n"
        << "  groww_chain [UNDERLYING] [flags]\n\n"
        << "Live (Groww Trading API):\n"
        << "  GROWW_ACCESS_TOKEN   daily bearer token from Groww -> Trading APIs\n"
        << "  GROWW_API_KEY        + GROWW_API_SECRET  (checksum flow)\n"
        << "  GROWW_API_KEY        + GROWW_TOTP        (TOTP flow)\n"
        << "  GROWW_UNDERLYING     default NIFTY (BANKNIFTY, FINNIFTY, RELIANCE, ...)\n"
        << "  GROWW_EXPIRY         YYYY-MM-DD; default = nearest listed expiry\n\n"
        << "Flags:\n"
        << "  --expiry YYYY-MM-DD  override expiry\n"
        << "  --as-of YYYY-MM-DD   valuation date (snapped to last NSE session close)\n"
        << "  --strikes N          N listed strikes either side of spot (default 5)\n"
        << "  --rate R             continuous risk-free rate; skips implied PCP\n"
        << "  --div Q              dividend / index yield; skips implied PCP\n"
        << "  --fixture PATH       force the bundled/offline JSON chain\n"
        << "  --mc                 also run antithetic+CV Monte Carlo on ATM\n"
        << "  --json               emit machine-readable rows\n"
        << "  --help\n\n"
        << "Without credentials the bundled NIFTY fixture is priced so the example\n"
        << "always runs. Index options on NSE are European; equity options too.\n"
        << "Default pricing is Black-76 with an implied forward from put-call parity,\n"
        << "NSE business-day vol time (trading days / 252), and ACT/365.25 discounting.\n";
}

Args parse_args(int argc, char** argv) {
    Args a;
    a.client = derivkit::groww::from_env();
    a.client.fixture_path = DERIVKIT_FIXTURE;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        auto need = [&](const char* name) -> std::string {
            if (i + 1 >= argc) {
                throw std::runtime_error(std::string("missing value for ") + name);
            }
            return argv[++i];
        };
        if (arg == "--help" || arg == "-h") {
            a.help = true;
        } else if (arg == "--expiry") {
            a.client.expiry_date = need("--expiry");
        } else if (arg == "--as-of") {
            a.as_of = need("--as-of");
        } else if (arg == "--strikes") {
            a.nearby = std::stoi(need("--strikes"));
        } else if (arg == "--rate") {
            a.rate = std::stod(need("--rate"));
        } else if (arg == "--div") {
            a.dividend = std::stod(need("--div"));
        } else if (arg == "--fixture") {
            a.client.fixture_path = need("--fixture");
            a.client.force_fixture = true;
        } else if (arg == "--mc") {
            a.run_mc = true;
        } else if (arg == "--json") {
            a.json_out = true;
        } else if (!arg.empty() && arg[0] != '-') {
            a.client.underlying = arg;
        } else {
            throw std::runtime_error("unknown flag: " + arg);
        }
    }
    return a;
}

struct Side {
    const derivkit::groww::Contract* call = nullptr;
    const derivkit::groww::Contract* put = nullptr;
};

}  // namespace

int main(int argc, char** argv) {
    using namespace derivkit;
    try {
        Args args = parse_args(argc, argv);
        if (args.help) {
            usage();
            return 0;
        }

        groww::Chain chain = groww::load_chain(args.client);
        if (chain.spot <= 0.0) {
            throw std::runtime_error("option chain did not include underlying_ltp");
        }
        if (chain.expiry_date.empty()) {
            throw std::runtime_error("missing expiry_date");
        }

        std::chrono::system_clock::time_point as_of = std::chrono::system_clock::now();
        if (args.as_of) {
            as_of = nse::expiry_close(*args.as_of);
        }
        const nse::Clock clk = nse::clock_to_expiry(chain.expiry_date, as_of);

        std::map<double, Side> by_strike;
        for (const auto& c : chain.contracts) {
            if (c.type == OptionType::Call) {
                by_strike[c.strike].call = &c;
            } else {
                by_strike[c.strike].put = &c;
            }
        }

        const bool override_carry = args.rate.has_value() || args.dividend.has_value();
        ForwardFit fit;
        if (!override_carry) {
            std::vector<CallPutQuote> quotes;
            for (const auto& [k, side] : by_strike) {
                if (side.call == nullptr || side.put == nullptr) {
                    continue;
                }
                if (!(side.call->ltp > 0.0 && side.put->ltp > 0.0)) {
                    continue;
                }
                CallPutQuote q;
                q.strike = k;
                q.call = side.call->ltp;
                q.put = side.put->ltp;
                q.weight = std::min(side.call->volume, side.put->volume) +
                           std::min(side.call->open_interest, side.put->open_interest);
                if (!(q.weight > 0.0)) {
                    q.weight = 1.0;
                }
                quotes.push_back(q);
            }
            fit = imply_forward(chain.spot, clk.time_rate, quotes);
        }

        double rate = args.rate.value_or(chain.rate);
        double dividend = args.dividend.value_or(chain.dividend);
        double forward = forward_price(chain.spot, rate, dividend, clk.time_rate);
        double df = discount_factor(rate, clk.time_rate);
        const char* carry_src = "overrides";
        if (!override_carry && fit.ok) {
            forward = fit.forward;
            df = fit.discount;
            rate = fit.rate;
            dividend = fit.dividend;
            carry_src = fit.method;
        } else if (!override_carry) {
            carry_src = "defaults (pcp failed)";
        }

        std::vector<double> strikes;
        for (const auto& c : chain.contracts) {
            if (strikes.empty() || strikes.back() != c.strike) {
                strikes.push_back(c.strike);
            }
        }
        std::sort(strikes.begin(), strikes.end(), [&](double a, double b) {
            return std::abs(a - chain.spot) < std::abs(b - chain.spot);
        });
        const std::size_t keep =
            std::min(strikes.size(), static_cast<std::size_t>(2 * args.nearby + 1));
        strikes.resize(keep);
        std::sort(strikes.begin(), strikes.end());

        nlohmann::json rows = nlohmann::json::array();

        std::cout << chain.underlying << "  " << chain.exchange << "  expiry " << clk.expiry_ist
                  << "  as-of " << clk.as_of_ist;
        if (clk.snapped_to_close) {
            std::cout << " (snapped to last close)";
        }
        std::cout << "  [" << chain.source << "]\n";
        std::cout << std::fixed << std::setprecision(4) << "T_rate=" << clk.time_rate
                  << "  T_vol=" << clk.time_vol << std::setprecision(2) << " ("
                  << clk.trading_days << " trading days)  spot=" << chain.spot
                  << "  F=" << forward << std::setprecision(6) << "  DF=" << df
                  << std::setprecision(4) << "  r=" << rate << "  q=" << dividend << "  ["
                  << carry_src << "]\n\n";

        std::cout << std::left << std::setw(22) << "symbol" << std::right << std::setw(4) << "cp"
                  << std::setw(8) << "K" << std::setw(10) << "LTP" << std::setw(10) << "BS"
                  << std::setw(10) << "Rs" << std::setw(8) << "iv%" << std::setw(8) << "ivG%"
                  << std::setw(8) << "volpts"
                  << "\n";

        double atm_diff = 1e300;
        const groww::Contract* atm = nullptr;

        for (const auto& c : chain.contracts) {
            if (std::find(strikes.begin(), strikes.end(), c.strike) == strikes.end()) {
                continue;
            }
            if (c.ltp <= 0.0) {
                continue;
            }

            bs::BlackSpec spec{
                .forward = forward,
                .strike = c.strike,
                .discount = df,
                .vol = c.groww_iv > 0.0 ? c.groww_iv : 0.15,
                .time_vol = clk.time_vol,
                .type = c.type,
            };

            const double bs_px = bs::price(spec);
            const double rupees = bs_px - c.ltp;

            bs::BlackSpec iv_spec = spec;
            iv_spec.vol = 0.2;
            const auto iv = bs::implied_vol(iv_spec, c.ltp);
            const double iv_pct = iv.converged ? iv.vol * 100.0 : 0.0;
            const double groww_iv_pct = c.groww_iv * 100.0;
            const double volpts = iv.converged ? 100.0 * (iv.vol - c.groww_iv) : 0.0;

            std::cout << std::left << std::setw(22) << c.trading_symbol << std::right << std::setw(4)
                      << (c.type == OptionType::Call ? "CE" : "PE") << std::setw(8)
                      << static_cast<int>(c.strike) << std::fixed << std::setprecision(2)
                      << std::setw(10) << c.ltp << std::setw(10) << bs_px << std::setw(10) << rupees
                      << std::setprecision(2) << std::setw(8);
            if (iv.converged) {
                std::cout << iv_pct;
            } else {
                std::cout << "n/a";
            }
            std::cout << std::setw(8) << groww_iv_pct << std::setw(8);
            if (iv.converged) {
                std::cout << volpts;
            } else {
                std::cout << "n/a";
            }
            std::cout << "\n";

            nlohmann::json row = {
                {"symbol", c.trading_symbol},
                {"type", c.type == OptionType::Call ? "CE" : "PE"},
                {"strike", c.strike},
                {"ltp", c.ltp},
                {"bs", bs_px},
                {"residual_rs", rupees},
                {"iv_groww", c.groww_iv},
                {"oi", c.open_interest},
                {"volume", c.volume},
            };
            if (iv.converged) {
                row["iv_from_ltp"] = iv.vol;
                row["vol_points"] = volpts;
            }
            rows.push_back(std::move(row));

            const double dist = std::abs(c.strike - chain.spot);
            if (c.type == OptionType::Call && dist < atm_diff) {
                atm_diff = dist;
                atm = &c;
            }
        }

        std::cout << "\nLTP = Groww last traded price.  BS is Black-76 using Groww IV, the "
                     "implied (or override) forward, and T_vol.\n"
                  << "Rs = BS - LTP (rupees).  iv% is derivkit implied vol from LTP; ivG% is "
                     "Groww's published IV.\n"
                  << "volpts = 100 * (iv_from_LTP - Groww_IV).  T_rate is ACT/365.25; T_vol is "
                     "NSE trading days / 252.\n";

        if (args.run_mc && atm != nullptr) {
            VanillaSpec spec{
                .spot = forward,
                .strike = atm->strike,
                .rate = 0.0,
                .dividend = 0.0,
                .vol = atm->groww_iv > 0.0 ? atm->groww_iv : 0.15,
                .time = clk.time_vol,
                .type = atm->type,
            };
            mc::McConfig cfg;
            cfg.paths = 40000;
            cfg.seed = 7;
            cfg.vr = VarianceReduction::Antithetic | VarianceReduction::ControlVariate;
            const auto mc_px = mc::european(spec, cfg);
            const double mc_df = df * mc_px.value;
            const bs::BlackSpec blk{
                .forward = forward,
                .strike = atm->strike,
                .discount = df,
                .vol = spec.vol,
                .time_vol = clk.time_vol,
                .type = atm->type,
            };
            std::cout << "\nATM Monte Carlo (" << atm->trading_symbol << "): " << std::fixed
                      << std::setprecision(4) << mc_df << "  stderr=" << std::scientific
                      << (df * mc_px.error_estimate) << "  vs Black-76 " << std::fixed
                      << bs::price(blk) << "\n";
        }

        if (args.json_out) {
            nlohmann::json out;
            out["underlying"] = chain.underlying;
            out["expiry"] = chain.expiry_date;
            out["spot"] = chain.spot;
            out["forward"] = forward;
            out["discount"] = df;
            out["rate"] = rate;
            out["dividend"] = dividend;
            out["carry_source"] = carry_src;
            out["as_of_ist"] = clk.as_of_ist;
            out["expiry_ist"] = clk.expiry_ist;
            out["time_rate"] = clk.time_rate;
            out["time_vol"] = clk.time_vol;
            out["trading_days"] = clk.trading_days;
            out["source"] = chain.source;
            out["rows"] = rows;
            std::cout << "\n" << out.dump(2) << "\n";
        }
        return 0;
    } catch (const std::exception& ex) {
        std::cerr << "groww_chain: " << ex.what() << "\n";
        return 1;
    }
}
