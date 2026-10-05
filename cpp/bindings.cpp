// Python binding for the C++ Monte Carlo kernel.
//
// pybind11 is a header-only library that generates the glue between Python's C API and
// C++ functions. Compiling this file produces a shared library that Python can import as
// `derivkit._mc_cpp_ext`. The Python side of the boundary is src/derivkit/_mc_cpp.py.
//
// Only plain numbers and booleans cross the boundary. No Python object is kept alive by
// C++ and no C++ pointer is handed to Python except the samplers, which Python owns.
#include "monte_carlo.hpp"

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>  // converts std::vector<double> to a Python list

#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

namespace py = pybind11;
namespace mc = derivkit::mc;

// Filled in by CMake so a benchmark report can state exactly how this file was built.
#ifndef DERIVKIT_CXX_FLAGS
#define DERIVKIT_CXX_FLAGS "unknown"
#endif
#ifndef DERIVKIT_BUILD_TYPE
#define DERIVKIT_BUILD_TYPE "unknown"
#endif

namespace {

// (n, mean_x, mean_y, m2_x, m2_y, c_xy). pybind11 converts a std::tuple into a Python tuple.
using Moments = std::tuple<std::uint64_t, double, double, double, double, double>;

Moments to_tuple(const derivkit::WelfordPair& w) {
    return {w.n, w.mean_x, w.mean_y, w.m2_x, w.m2_y, w.c_xy};
}

mc::VanillaSpec make_spec(double spot, double strike, double rate, double dividend, double vol,
                          double time, bool is_call) {
    return {spot, strike, rate, dividend, vol, time,
            is_call ? mc::OptionType::Call : mc::OptionType::Put};
}

// Compiler name and version, from macros the compiler defines about itself.
std::string compiler() {
#if defined(__apple_build_version__)
    return std::string("Apple clang ") + __clang_version__;
#elif defined(__clang__)
    return std::string("Clang ") + __clang_version__;
#elif defined(__GNUC__)
    return std::string("GCC ") + __VERSION__;
#else
    return "unknown";
#endif
}

// The samplers exist once per generator (see monte_carlo.hpp). These two function
// templates register one of them under a given Python name, so the binding code is written
// once and used for both the reproducible and the fast variant.
template <class Sampler>
void bind_european(py::module_& m, const char* name) {
    // py::class_ exposes a C++ class as a Python type. Python holds each instance through
    // a smart pointer and deletes the C++ object when the Python object is collected.
    py::class_<Sampler>(m, name)
        // py::init with a lambda: a custom constructor that turns plain arguments into a spec.
        .def(py::init([](double spot, double strike, double rate, double dividend, double vol,
                         double time, bool is_call, std::uint64_t seed, bool antithetic) {
                 return Sampler(make_spec(spot, strike, rate, dividend, vol, time, is_call),
                                seed, antithetic);
             }),
             py::arg("spot"), py::arg("strike"), py::arg("rate"), py::arg("dividend"),
             py::arg("vol"), py::arg("time"), py::arg("is_call"), py::arg("seed"),
             py::arg("antithetic"))
        // The call_guard releases Python's global interpreter lock (GIL) while the C++
        // loop runs and takes it back before the result is converted. The loop touches no
        // Python objects, so this is safe, and other Python threads are not frozen for
        // the length of a long simulation. The simulation itself still uses one thread.
        .def("advance", &Sampler::advance, py::arg("paths"),
             py::call_guard<py::gil_scoped_release>(), "Simulate `paths` more paths.")
        .def(
            "moments", [](const Sampler& s) { return to_tuple(s.moments()); },
            "Return (n, mean_x, mean_y, m2_x, m2_y, c_xy).");
}

template <class Sampler>
void bind_asian(py::module_& m, const char* name) {
    py::class_<Sampler>(m, name)
        .def(py::init([](double spot, double strike, double rate, double dividend, double vol,
                         double time, bool is_call, std::uint32_t steps, std::uint64_t seed,
                         bool antithetic) {
                 // If the constructor throws std::invalid_argument, pybind11 catches it
                 // and raises ValueError in Python.
                 return Sampler(make_spec(spot, strike, rate, dividend, vol, time, is_call),
                                steps, seed, antithetic);
             }),
             py::arg("spot"), py::arg("strike"), py::arg("rate"), py::arg("dividend"),
             py::arg("vol"), py::arg("time"), py::arg("is_call"), py::arg("steps"),
             py::arg("seed"), py::arg("antithetic"))
        .def("advance", &Sampler::advance, py::arg("paths"),
             py::call_guard<py::gil_scoped_release>(), "Simulate `paths` more paths.")
        .def(
            "moments", [](const Sampler& s) { return to_tuple(s.moments()); },
            "Return (n, mean_x, mean_y, m2_x, m2_y, c_xy).");
}

// The first `count` normal draws of a generator, for tests that look at the stream itself.
template <class Rng>
std::vector<double> draws(std::uint64_t seed, std::size_t count) {
    std::vector<double> z(count);
    Rng rng(seed);
    rng.fill(z);
    return z;
}

}  // namespace

// This macro defines the function Python calls when it imports the module. The first
// argument must match the file name of the built library; `m` is the module object.
PYBIND11_MODULE(_mc_cpp_ext, m) {
    m.doc() = "C++20 Monte Carlo kernel for derivkit (single-threaded).";

    // "Reproducible" samplers draw the same stream as the pure-Python engine. "Fast" ones
    // use xoshiro256++ with a ziggurat sampler: their own stream, fixed by the seed.
    bind_european<mc::EuropeanSampler>(m, "EuropeanSampler");
    bind_european<mc::FastEuropeanSampler>(m, "FastEuropeanSampler");
    bind_asian<mc::AsianSampler>(m, "AsianSampler");
    bind_asian<mc::FastAsianSampler>(m, "FastAsianSampler");

    m.def(
        "normal_draws",
        [](const std::string& rng, std::uint64_t seed, std::size_t count) {
            if (rng == "reproducible") {
                return draws<derivkit::NormalRng>(seed, count);
            }
            if (rng == "fast") {
                return draws<derivkit::FastNormalRng>(seed, count);
            }
            throw std::invalid_argument("unknown rng '" + rng + "'");
        },
        py::arg("rng"), py::arg("seed"), py::arg("count"),
        "The first `count` N(0, 1) draws of the named generator, as a list.");

    m.def(
        "build_info",
        [] {
            py::dict info;
            info["compiler"] = compiler();
            info["cxx_standard"] = static_cast<long>(__cplusplus);
            info["build_type"] = DERIVKIT_BUILD_TYPE;
            info["cxx_flags"] = DERIVKIT_CXX_FLAGS;
            info["pybind11"] = std::to_string(PYBIND11_VERSION_MAJOR) + "." +
                               std::to_string(PYBIND11_VERSION_MINOR) + "." +
                               std::to_string(PYBIND11_VERSION_PATCH);
            return info;
        },
        "Compiler, flags and versions this extension was built with.");
}
