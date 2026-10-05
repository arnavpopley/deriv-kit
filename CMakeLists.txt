# Builds the optional C++ Monte Carlo back end (derivkit._mc_cpp_ext).
#
#   pip install pybind11
#   cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
#   cmake --build build
#
# The Python package itself is built by hatchling (pyproject.toml) and needs none of this.
cmake_minimum_required(VERSION 3.18)

project(derivkit_mc_cpp
    DESCRIPTION "C++20 Monte Carlo kernel for derivkit"
    LANGUAGES CXX
)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Release unless told otherwise. For GCC and Clang, CMake's Release flags are -O3 -DNDEBUG.
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

option(DERIVKIT_WERROR "Treat warnings as errors" OFF)
option(DERIVKIT_SANITIZE "Build with AddressSanitizer and UndefinedBehaviorSanitizer" OFF)

# Sanitizers add run-time checks for memory errors (reading past an array, using freed
# memory) and undefined behaviour (signed overflow, bad shifts, bad casts). They make the
# code several times slower, so this is a testing build, never a benchmarking one. The
# Python interpreter itself is not built this way, so the sanitizer's run-time library has
# to be loaded first; .github/workflows/ci.yml shows how.
if(DERIVKIT_SANITIZE)
    set(DERIVKIT_SANITIZE_FLAGS
        -fsanitize=address,undefined -fno-sanitize-recover=undefined -fno-omit-frame-pointer)
    add_compile_options(${DERIVKIT_SANITIZE_FLAGS})
    add_link_options(${DERIVKIT_SANITIZE_FLAGS})
    if(CMAKE_CXX_COMPILER_ID STREQUAL "Clang")
        # Clang links its run-time library statically unless told otherwise; a shared one
        # is what can be loaded ahead of Python. (Apple clang and GCC already use one.)
        add_link_options(-shared-libasan)
    endif()
endif()

# Use the interpreter of the active virtual environment, or pass -DPython_EXECUTABLE=...
find_package(Python 3.11 REQUIRED COMPONENTS Interpreter Development.Module)

# A pip-installed pybind11 keeps its CMake package inside site-packages; ask it where.
if(NOT pybind11_DIR)
    execute_process(
        COMMAND "${Python_EXECUTABLE}" -m pybind11 --cmakedir
        OUTPUT_VARIABLE _pybind11_dir
        OUTPUT_STRIP_TRAILING_WHITESPACE
        RESULT_VARIABLE _pybind11_rc
        ERROR_QUIET
    )
    if(_pybind11_rc EQUAL 0)
        set(pybind11_DIR "${_pybind11_dir}")
    endif()
endif()
find_package(pybind11 CONFIG REQUIRED)

# NO_EXTRAS: skip pybind11's default link-time optimisation and symbol stripping, so the
# flags below are the whole story. The hot loop sits in one .cpp file with its RNG in a
# header, so nothing performance-critical crosses a file boundary.
pybind11_add_module(_mc_cpp_ext MODULE NO_EXTRAS
    cpp/bindings.cpp
    cpp/monte_carlo.cpp
)

# -ffp-contract=off: do not fuse a*b+c into one fused multiply-add. A fused operation
# rounds once instead of twice, which changes the last digit and would stop the C++ kernel
# matching the pure-Python one bit for bit. -ffast-math is deliberately not used.
set(DERIVKIT_KERNEL_FLAGS -ffp-contract=off)
set(DERIVKIT_WARNING_FLAGS -Wall -Wextra -Wpedantic -Wshadow)
if(DERIVKIT_WERROR)
    list(APPEND DERIVKIT_WARNING_FLAGS -Werror)
endif()
target_compile_options(_mc_cpp_ext PRIVATE ${DERIVKIT_KERNEL_FLAGS} ${DERIVKIT_WARNING_FLAGS})

# Record the optimisation-relevant flags inside the module (see build_info()).
string(TOUPPER "${CMAKE_BUILD_TYPE}" _config)
list(JOIN DERIVKIT_KERNEL_FLAGS " " _kernel_flags)
list(JOIN DERIVKIT_SANITIZE_FLAGS " " _sanitize_flags)  # empty unless DERIVKIT_SANITIZE is on
string(STRIP
    "${CMAKE_CXX_FLAGS} ${CMAKE_CXX_FLAGS_${_config}} ${CMAKE_CXX20_STANDARD_COMPILE_OPTION} ${_kernel_flags} ${_sanitize_flags}"
    _all_flags
)
target_compile_definitions(_mc_cpp_ext PRIVATE
    DERIVKIT_CXX_FLAGS="${_all_flags}"
    DERIVKIT_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
)

# Optional profiling program (not built by default):
#   cmake --build build --target where_time_goes && ./build/where_time_goes
add_executable(where_time_goes EXCLUDE_FROM_ALL
    benchmarks/where_time_goes.cpp
    cpp/monte_carlo.cpp
)
target_include_directories(where_time_goes PRIVATE cpp)
target_compile_options(where_time_goes PRIVATE ${DERIVKIT_KERNEL_FLAGS} ${DERIVKIT_WARNING_FLAGS})

# Optional microbenchmark of the two normal generators on their own (not built by default):
#   cmake --build build --target rng_speed && ./build/rng_speed
add_executable(rng_speed EXCLUDE_FROM_ALL benchmarks/rng_speed.cpp)
target_include_directories(rng_speed PRIVATE cpp)
target_compile_options(rng_speed PRIVATE ${DERIVKIT_KERNEL_FLAGS} ${DERIVKIT_WARNING_FLAGS})

# Put the built module next to the Python sources so `import derivkit._mc_cpp_ext` works
# for an editable install and for pytest without an install step.
set_target_properties(_mc_cpp_ext PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/src/derivkit"
)
