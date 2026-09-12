#include "groww_api.hpp"

#include "nlohmann/json.hpp"

#include <algorithm>
#include <array>
#include <cctype>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace derivkit::groww {
namespace {

using json = nlohmann::json;

std::string env_or(const char* key) {
    const char* v = std::getenv(key);
    return v == nullptr ? std::string() : std::string(v);
}

std::string shell_quote(const std::string& s) {
    std::string out = "'";
    for (char c : s) {
        if (c == '\'') {
            out += "'\\''";
        } else {
            out += c;
        }
    }
    out += "'";
    return out;
}

std::string slurp_stream(FILE* fp) {
    std::string out;
    char buf[4096];
    while (std::fgets(buf, sizeof(buf), fp) != nullptr) {
        out += buf;
    }
    return out;
}

std::string run(const std::string& cmd) {
    FILE* fp = popen(cmd.c_str(), "r");
    if (fp == nullptr) {
        throw std::runtime_error("failed to run: " + cmd);
    }
    std::string out = slurp_stream(fp);
    const int rc = pclose(fp);
    if (rc != 0) {
        throw std::runtime_error("command failed (" + std::to_string(rc) + "): " + cmd +
                                 "\n" + out);
    }
    return out;
}

std::string curl_get(const std::string& url, const std::string& token) {
    std::ostringstream cmd;
    cmd << "curl -sS --fail --max-time 30"
        << " -H " << shell_quote("Accept: application/json")
        << " -H " << shell_quote("X-API-VERSION: 1.0");
    if (!token.empty()) {
        cmd << " -H " << shell_quote("Authorization: Bearer " + token);
    }
    cmd << " " << shell_quote(url);
    return run(cmd.str());
}

std::string curl_post_json(const std::string& url, const std::string& bearer,
                           const std::string& body) {
    std::ostringstream cmd;
    cmd << "curl -sS --fail --max-time 30 -X POST"
        << " -H " << shell_quote("Accept: application/json")
        << " -H " << shell_quote("Content-Type: application/json")
        << " -H " << shell_quote("X-API-VERSION: 1.0")
        << " -H " << shell_quote("Authorization: Bearer " + bearer)
        << " --data-binary " << shell_quote(body)
        << " " << shell_quote(url);
    return run(cmd.str());
}

std::string url_encode(const std::string& s) {
    std::ostringstream oss;
    oss << std::hex << std::uppercase;
    for (unsigned char c : s) {
        if (std::isalnum(c) || c == '-' || c == '_' || c == '.' || c == '~') {
            oss << static_cast<char>(c);
        } else {
            oss << '%' << std::setw(2) << std::setfill('0') << static_cast<int>(c);
        }
    }
    return oss.str();
}

// SHA-256 (FIPS 180-4), public-domain style compact implementation.
std::string sha256_hex(const std::string& message) {
    static const std::uint32_t k[64] = {
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4,
        0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe,
        0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f,
        0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
        0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
        0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
        0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116,
        0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
        0xc67178f2};

    auto rotr = [](std::uint32_t x, std::uint32_t n) {
        return (x >> n) | (x << (32 - n));
    };

    std::vector<std::uint8_t> data(message.begin(), message.end());
    const std::uint64_t bit_len = static_cast<std::uint64_t>(data.size()) * 8ull;
    data.push_back(0x80);
    while ((data.size() % 64) != 56) {
        data.push_back(0);
    }
    for (int i = 7; i >= 0; --i) {
        data.push_back(static_cast<std::uint8_t>((bit_len >> (i * 8)) & 0xff));
    }

    std::uint32_t h[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                          0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};

    for (std::size_t chunk = 0; chunk < data.size(); chunk += 64) {
        std::uint32_t w[64];
        for (int i = 0; i < 16; ++i) {
            w[i] = (static_cast<std::uint32_t>(data[chunk + i * 4]) << 24) |
                   (static_cast<std::uint32_t>(data[chunk + i * 4 + 1]) << 16) |
                   (static_cast<std::uint32_t>(data[chunk + i * 4 + 2]) << 8) |
                   (static_cast<std::uint32_t>(data[chunk + i * 4 + 3]));
        }
        for (int i = 16; i < 64; ++i) {
            const std::uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
            const std::uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16] + s0 + w[i - 7] + s1;
        }
        std::uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6],
                      hh = h[7];
        for (int i = 0; i < 64; ++i) {
            const std::uint32_t S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
            const std::uint32_t ch = (e & f) ^ ((~e) & g);
            const std::uint32_t temp1 = hh + S1 + ch + k[i] + w[i];
            const std::uint32_t S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
            const std::uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
            const std::uint32_t temp2 = S0 + maj;
            hh = g;
            g = f;
            f = e;
            e = d + temp1;
            d = c;
            c = b;
            b = a;
            a = temp1 + temp2;
        }
        h[0] += a;
        h[1] += b;
        h[2] += c;
        h[3] += d;
        h[4] += e;
        h[5] += f;
        h[6] += g;
        h[7] += hh;
    }

    std::ostringstream oss;
    oss << std::hex << std::setfill('0');
    for (int i = 0; i < 8; ++i) {
        oss << std::setw(8) << h[i];
    }
    return oss.str();
}

std::string today_iso() {
    using namespace std::chrono;
    const auto ymd = year_month_day{floor<days>(system_clock::now())};
    std::ostringstream oss;
    oss << static_cast<int>(ymd.year()) << '-' << std::setw(2) << std::setfill('0')
        << static_cast<unsigned>(ymd.month()) << '-' << std::setw(2) << static_cast<unsigned>(ymd.day());
    return oss.str();
}

Contract parse_leg(const json& node, double strike, OptionType type) {
    Contract c;
    c.strike = strike;
    c.type = type;
    c.trading_symbol = node.value("trading_symbol", "");
    c.ltp = node.value("ltp", 0.0);
    c.open_interest = node.value("open_interest", 0.0);
    c.volume = node.value("volume", 0.0);
    if (node.contains("greeks") && node["greeks"].is_object()) {
        const json& g = node["greeks"];
        c.groww_delta = g.value("delta", 0.0);
        c.groww_gamma = g.value("gamma", 0.0);
        c.groww_theta = g.value("theta", 0.0);
        c.groww_vega = g.value("vega", 0.0);
        c.groww_rho = g.value("rho", 0.0);
        c.groww_iv = g.value("iv", 0.0) / 100.0;  // percent → decimal
    }
    return c;
}

std::string extract_token(const json& body) {
    if (body.contains("token") && body["token"].is_string()) {
        return body["token"].get<std::string>();
    }
    if (body.contains("payload") && body["payload"].is_object()) {
        const json& p = body["payload"];
        if (p.contains("token") && p["token"].is_string()) {
            return p["token"].get<std::string>();
        }
        if (p.contains("access_token") && p["access_token"].is_string()) {
            return p["access_token"].get<std::string>();
        }
    }
    throw std::runtime_error("Groww token response did not contain a token field");
}

}  // namespace

ClientConfig from_env() {
    ClientConfig cfg;
    cfg.access_token = env_or("GROWW_ACCESS_TOKEN");
    cfg.api_key = env_or("GROWW_API_KEY");
    cfg.api_secret = env_or("GROWW_API_SECRET");
    cfg.totp = env_or("GROWW_TOTP");
    const std::string u = env_or("GROWW_UNDERLYING");
    if (!u.empty()) {
        cfg.underlying = u;
    }
    const std::string e = env_or("GROWW_EXPIRY");
    if (!e.empty()) {
        cfg.expiry_date = e;
    }
    const std::string fx = env_or("GROWW_FIXTURE");
    if (!fx.empty()) {
        cfg.fixture_path = fx;
    }
    return cfg;
}

Chain parse_option_chain(const std::string& json_text) {
    const json root = json::parse(json_text);
    if (root.contains("status") && root["status"].is_string() &&
        root["status"].get<std::string>() == "FAILURE") {
        std::string msg = "Groww API failure";
        if (root.contains("error")) {
            msg += ": " + root["error"].dump();
        }
        throw std::runtime_error(msg);
    }

    const json payload = root.contains("payload") ? root.at("payload") : root;
    Chain chain;
    chain.source = root.value("source", "live");
    chain.underlying = root.value("underlying", "NIFTY");
    chain.exchange = root.value("exchange", "NSE");
    chain.expiry_date = root.value("expiry_date", "");
    chain.rate = root.value("rate", 0.065);
    chain.dividend = root.value("dividend", 0.012);
    chain.year_fraction = root.value("year_fraction", 0.0);
    chain.spot = payload.value("underlying_ltp", 0.0);

    if (!payload.contains("strikes") || !payload["strikes"].is_object()) {
        throw std::runtime_error("option chain JSON is missing payload.strikes");
    }
    for (auto it = payload["strikes"].begin(); it != payload["strikes"].end(); ++it) {
        const double strike = std::stod(it.key());
        const json& node = it.value();
        if (node.contains("CE")) {
            chain.contracts.push_back(parse_leg(node["CE"], strike, OptionType::Call));
        }
        if (node.contains("PE")) {
            chain.contracts.push_back(parse_leg(node["PE"], strike, OptionType::Put));
        }
    }
    std::sort(chain.contracts.begin(), chain.contracts.end(),
              [](const Contract& a, const Contract& b) {
                  if (a.strike != b.strike) {
                      return a.strike < b.strike;
                  }
                  return a.type == OptionType::Call && b.type != OptionType::Call;
              });
    return chain;
}

Chain load_fixture(const std::string& path) {
    std::ifstream in(path);
    if (!in) {
        throw std::runtime_error("cannot open fixture: " + path);
    }
    std::ostringstream ss;
    ss << in.rdbuf();
    Chain c = parse_option_chain(ss.str());
    c.source = "fixture";
    return c;
}

std::string resolve_access_token(const ClientConfig& cfg) {
    if (!cfg.access_token.empty()) {
        return cfg.access_token;
    }
    if (cfg.api_key.empty()) {
        return {};
    }
    json body;
    if (!cfg.totp.empty()) {
        body["key_type"] = "totp";
        body["totp"] = cfg.totp;
    } else if (!cfg.api_secret.empty()) {
        const std::string ts = std::to_string(static_cast<long long>(std::time(nullptr)));
        body["key_type"] = "approval";
        body["timestamp"] = ts;
        body["checksum"] = sha256_hex(cfg.api_secret + ts);
    } else {
        throw std::runtime_error(
            "GROWW_API_KEY set but neither GROWW_API_SECRET nor GROWW_TOTP was provided");
    }
    const std::string raw =
        curl_post_json("https://api.groww.in/v1/token/api/access", cfg.api_key, body.dump());
    return extract_token(json::parse(raw));
}

std::vector<std::string> list_expiries(const ClientConfig& cfg, const std::string& token) {
    const std::string url = "https://api.groww.in/v1/historical/expiries?exchange=" +
                            url_encode(cfg.exchange) +
                            "&underlying_symbol=" + url_encode(cfg.underlying);
    const json body = json::parse(curl_get(url, token));
    json payload = body.contains("payload") ? body["payload"] : body;
    std::vector<std::string> out;
    if (payload.contains("expiries") && payload["expiries"].is_array()) {
        for (const auto& e : payload["expiries"]) {
            if (e.is_string()) {
                out.push_back(e.get<std::string>());
            }
        }
    }
    return out;
}

std::string nearest_expiry(const std::vector<std::string>& dates, const std::string& today_iso) {
    std::string best;
    for (const auto& d : dates) {
        if (d >= today_iso && (best.empty() || d < best)) {
            best = d;
        }
    }
    if (best.empty() && !dates.empty()) {
        best = *std::max_element(dates.begin(), dates.end());
    }
    return best;
}

Chain load_chain(const ClientConfig& cfg) {
    if (cfg.force_fixture || (!cfg.fixture_path.empty() && cfg.access_token.empty() &&
                              cfg.api_key.empty())) {
        return load_fixture(cfg.fixture_path);
    }

    const std::string token = resolve_access_token(cfg);
    if (token.empty()) {
        if (cfg.fixture_path.empty()) {
            throw std::runtime_error(
                "No Groww credentials. Set GROWW_ACCESS_TOKEN (or API key + secret), "
                "or pass --fixture.");
        }
        return load_fixture(cfg.fixture_path);
    }

    ClientConfig live = cfg;
    if (live.expiry_date.empty()) {
        const auto dates = list_expiries(live, token);
        live.expiry_date = nearest_expiry(dates, today_iso());
        if (live.expiry_date.empty()) {
            throw std::runtime_error("Groww returned no expiries for " + live.underlying);
        }
    }

    const std::string url = "https://api.groww.in/v1/option-chain/exchange/" +
                            url_encode(live.exchange) + "/underlying/" +
                            url_encode(live.underlying) +
                            "?expiry_date=" + url_encode(live.expiry_date);
    Chain chain = parse_option_chain(curl_get(url, token));
    chain.source = "live";
    chain.underlying = live.underlying;
    chain.exchange = live.exchange;
    chain.expiry_date = live.expiry_date;
    return chain;
}

double years_to_expiry(const std::string& expiry_iso_date) {
    if (expiry_iso_date.size() < 10) {
        throw std::invalid_argument("expiry must be YYYY-MM-DD");
    }
    const int y = std::stoi(expiry_iso_date.substr(0, 4));
    const int m = std::stoi(expiry_iso_date.substr(5, 2));
    const int d = std::stoi(expiry_iso_date.substr(8, 2));
    using namespace std::chrono;
    // NSE F&O expires at 15:30 IST = 10:00 UTC.
    const sys_seconds expiry =
        sys_days{year{y} / month{static_cast<unsigned>(m)} / day{static_cast<unsigned>(d)}} + 10h;
    const auto now = time_point_cast<seconds>(system_clock::now());
    const double secs = duration<double>(expiry - now).count();
    const double years = secs / (365.25 * 24.0 * 3600.0);
    return std::max(years, 1.0 / 365.25 / 24.0);  // at least one hour
}

}  // namespace derivkit::groww
