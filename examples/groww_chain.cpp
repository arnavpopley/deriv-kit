#include "derivkit/derivkit.hpp"
#include "groww_api.hpp"

#include "nlohmann/json.hpp"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <iostream>
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
    int nearby = 5;  // strikes on each side of ATM
    bool run_mc = false;
    bool json_out = false;
    bool help = false;
};

void usage() {
    std::cout
        << "Price a Groww option chain with derivkit.\n\n"
        << "  groww_chain [UNDERLYING] [flags]\n\n"
        << "Live (Groww Trading API):\n"
        << "  GROWW_ACCESS_TOKEN   daily bearer token from Groww → Trading APIs\n"
        << "  GROWW_API_KEY        + GROWW_API_SECRET  (checksum flow)\n"
        << "  GROWW_API_KEY        + GROWW_TOTP        (TOTP flow)\n"
        << "  GROWW_UNDERLYING     default NIFTY (BANKNIFTY, FINNIFTY, RELIANCE, ...)\n"
        << "  GROWW_EXPIRY         YYYY-MM-DD; default = nearest listed expiry\n\n"
        << "Flags:\n"
        << "  --expiry YYYY-MM-DD  override expiry\n"
        << "  --strikes N          N listed strikes either side of spot (default 5)\n"
        << "  --rate R             continuous risk-free rate (default 0.065)\n"
        << "  --div Q              dividend / index yield (default 0.012)\n"
        << "  --fixture PATH       force the bundled/offline JSON chain\n"
        << "  --mc                 also run antithetic+CV Monte Carlo on ATM\n"
        << "  --json               emit machine-readable rows\n"
        << "  --help\n\n"
        << "Without credentials the bundled NIFTY fixture is priced so the example\n"
        << "always runs. Index options on NSE are European; equity options too.\n";
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
        } else if (arg == "--strikes") {
            a.nearby = std::stoi(need("--strikes"));
        } else if (arg == "--rate" || arg == "--div") {
            (void)need(arg.c_str());
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

// Re-parse rate/div properly — keep a simple second pass in main.
struct Overrides {
    std::optional<double> rate;
    std::optional<double> dividend;
};

Overrides parse_overrides(int argc, char** argv) {
    Overrides o;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if ((arg == "--rate" || arg == "--div" || arg == "--expiry" || arg == "--strikes" ||
             arg == "--fixture") &&
            i + 1 < argc) {
            if (arg == "--rate") {
                o.rate = std::stod(argv[++i]);
            } else if (arg == "--div") {
                o.dividend = std::stod(argv[++i]);
            } else {
                ++i;
            }
        }
    }
    return o;
}

}  // namespace

int main(int argc, char** argv) {
    using namespace derivkit;
    try {
        Args args = parse_args(argc, argv);
        if (args.help) {
            usage();
            return 0;
        }
        const Overrides ov = parse_overrides(argc, argv);

        groww::Chain chain = groww::load_chain(args.client);
        if (ov.rate) {
            chain.rate = *ov.rate;
        }
        if (ov.dividend) {
            chain.dividend = *ov.dividend;
        }
        if (chain.spot <= 0.0) {
            throw std::runtime_error("option chain did not include underlying_ltp");
        }
        if (chain.expiry_date.empty()) {
            throw std::runtime_error("missing expiry_date");
        }

        const double T =
            chain.year_fraction > 0.0 ? chain.year_fraction : groww::years_to_expiry(chain.expiry_date);

        // Unique strikes, pick those nearest the spot.
        std::vector<double> strikes;
        for (const auto& c : chain.contracts) {
            if (strikes.empty() || strikes.back() != c.strike) {
                strikes.push_back(c.strike);
            }
        }
        std::sort(strikes.begin(), strikes.end(), [&](double a, double b) {
            return std::abs(a - chain.spot) < std::abs(b - chain.spot);
        });
        const std::size_t keep = std::min(strikes.size(), static_cast<std::size_t>(2 * args.nearby + 1));
        strikes.resize(keep);
        std::sort(strikes.begin(), strikes.end());

        nlohmann::json rows = nlohmann::json::array();

        std::cout << chain.underlying << "  " << chain.exchange << "  expiry " << chain.expiry_date
                  << "  T=" << std::fixed << std::setprecision(4) << T << "y"
                  << "  spot=" << std::setprecision(2) << chain.spot
                  << "  r=" << std::setprecision(3) << chain.rate
                  << "  q=" << chain.dividend << "  [" << chain.source << "]\n\n";

        std::cout << std::left << std::setw(22) << "symbol" << std::right << std::setw(4) << "cp"
                  << std::setw(8) << "K" << std::setw(10) << "LTP" << std::setw(10) << "BS"
                  << std::setw(10) << "LR" << std::setw(8) << "iv%" << std::setw(8) << "ivG%"
                  << std::setw(8) << "dlt" << std::setw(8) << "dltG" << std::setw(10) << "mispx%"
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

            VanillaSpec spec{
                .spot = chain.spot,
                .strike = c.strike,
                .rate = chain.rate,
                .dividend = chain.dividend,
                .vol = c.groww_iv > 0.0 ? c.groww_iv : 0.15,
                .time = T,
                .type = c.type,
            };

            const double bs_px = bs::price(spec);
            const auto g = bs::greeks(spec);
            const auto lr = tree::leisen_reimer(spec, 101);

            VanillaSpec iv_spec = spec;
            iv_spec.vol = 0.2;
            const auto iv = bs::implied_vol(iv_spec, c.ltp);
            const double iv_pct = iv.converged ? iv.vol * 100.0 : 0.0;
            const double groww_iv_pct = c.groww_iv * 100.0;
            const double mispx = 100.0 * (bs_px - c.ltp) / c.ltp;

            std::cout << std::left << std::setw(22) << c.trading_symbol << std::right << std::setw(4)
                      << (c.type == OptionType::Call ? "CE" : "PE") << std::setw(8)
                      << static_cast<int>(c.strike) << std::fixed << std::setprecision(2)
                      << std::setw(10) << c.ltp << std::setw(10) << bs_px << std::setw(10)
                      << lr.value << std::setprecision(2) << std::setw(8) << iv_pct << std::setw(8)
                      << groww_iv_pct << std::setprecision(3) << std::setw(8) << g.delta
                      << std::setw(8) << c.groww_delta << std::setprecision(2) << std::setw(10)
                      << mispx << "\n";

            rows.push_back({
                {"symbol", c.trading_symbol},
                {"type", c.type == OptionType::Call ? "CE" : "PE"},
                {"strike", c.strike},
                {"ltp", c.ltp},
                {"bs", bs_px},
                {"leisen_reimer", lr.value},
                {"iv_from_ltp", iv.vol},
                {"iv_groww", c.groww_iv},
                {"delta", g.delta},
                {"delta_groww", c.groww_delta},
                {"gamma", g.gamma},
                {"vega_per_vol", g.vega},
                {"mispricing_pct", mispx},
                {"oi", c.open_interest},
                {"volume", c.volume},
            });

            const double dist = std::abs(c.strike - chain.spot);
            if (c.type == OptionType::Call && dist < atm_diff) {
                atm_diff = dist;
                atm = &c;
            }
        }

        std::cout << "\nLTP = Groww last traded price.  BS uses Groww IV.  LR = Leisen–Reimer "
                     "N=101.\n"
                  << "iv% is derivkit implied vol from LTP; ivG% is Groww's published IV.\n"
                  << "mispx% = (BS − LTP) / LTP.  Delta is per 1 point of spot.\n";

        if (args.run_mc && atm != nullptr) {
            VanillaSpec spec{
                .spot = chain.spot,
                .strike = atm->strike,
                .rate = chain.rate,
                .dividend = chain.dividend,
                .vol = atm->groww_iv > 0.0 ? atm->groww_iv : 0.15,
                .time = T,
                .type = atm->type,
            };
            mc::McConfig cfg;
            cfg.paths = 40000;
            cfg.seed = 7;
            cfg.vr = VarianceReduction::Antithetic | VarianceReduction::ControlVariate;
            const auto mc_px = mc::european(spec, cfg);
            std::cout << "\nATM Monte Carlo (" << atm->trading_symbol << "): " << std::fixed
                      << std::setprecision(4) << mc_px.value << "  stderr=" << std::scientific
                      << mc_px.error_estimate << "  vs BS " << std::fixed
                      << bs::price(spec) << "\n";
        }

        if (args.json_out) {
            nlohmann::json out;
            out["underlying"] = chain.underlying;
            out["expiry"] = chain.expiry_date;
            out["spot"] = chain.spot;
            out["source"] = chain.source;
            out["year_fraction"] = T;
            out["rows"] = rows;
            std::cout << "\n" << out.dump(2) << "\n";
        }
        return 0;
    } catch (const std::exception& ex) {
        std::cerr << "groww_chain: " << ex.what() << "\n";
        return 1;
    }
}
