#pragma once

#include <cmath>
#include <cstdlib>
#include <iostream>
#include <string>

namespace derivkit::test {

struct Counters {
    int passed = 0;
    int failed = 0;
};

inline Counters& counters() {
    static Counters c;
    return c;
}

inline void expect(bool cond, const char* expr, const char* file, int line) {
    if (cond) {
        ++counters().passed;
        return;
    }
    ++counters().failed;
    std::cerr << "FAIL " << file << ":" << line << "  " << expr << "\n";
}

inline void expect_near(double a, double b, double tol, const char* expr, const char* file,
                        int line) {
    if (std::isfinite(a) && std::isfinite(b) && std::abs(a - b) <= tol) {
        ++counters().passed;
        return;
    }
    ++counters().failed;
    std::cerr << "FAIL " << file << ":" << line << "  " << expr << "  got " << a << " expected "
              << b << " tol " << tol << "\n";
}

inline int summarize(const char* suite) {
    std::cout << suite << ": " << counters().passed << " passed, " << counters().failed
              << " failed\n";
    return counters().failed == 0 ? 0 : 1;
}

}  // namespace derivkit::test

#define CHECK(cond) ::derivkit::test::expect(static_cast<bool>(cond), #cond, __FILE__, __LINE__)
#define CHECK_NEAR(a, b, tol) \
    ::derivkit::test::expect_near((a), (b), (tol), #a " ~= " #b, __FILE__, __LINE__)
