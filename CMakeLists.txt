cmake_minimum_required(VERSION 3.16)

project(derivkit
    VERSION 1.0.0
    DESCRIPTION "C++ derivatives pricing toolkit with analytic, tree, and Monte Carlo engines"
    LANGUAGES CXX
)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

option(DERIVKIT_BUILD_TESTS "Build unit tests" ON)
option(DERIVKIT_BUILD_EXAMPLES "Build example programs" ON)
option(DERIVKIT_WERROR "Treat warnings as errors" OFF)
option(DERIVKIT_SANITIZE "Enable address and UB sanitizers" OFF)

include(GNUInstallDirs)

add_library(derivkit
    src/types.cpp
    src/math.cpp
    src/rng.cpp
    src/black_scholes.cpp
    src/implied_vol.cpp
    src/implied_forward.cpp
    src/nse_calendar.cpp
    src/trees.cpp
    src/monte_carlo.cpp
)
add_library(derivkit::derivkit ALIAS derivkit)

target_include_directories(derivkit
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/src
)

target_compile_features(derivkit PUBLIC cxx_std_20)

function(derivkit_warnings target)
    if(MSVC)
        target_compile_options(${target} PRIVATE /W4)
        if(DERIVKIT_WERROR)
            target_compile_options(${target} PRIVATE /WX)
        endif()
    else()
        target_compile_options(${target} PRIVATE -Wall -Wextra -Wpedantic -Wshadow)
        if(DERIVKIT_WERROR)
            target_compile_options(${target} PRIVATE -Werror)
        endif()
    endif()
    if(DERIVKIT_SANITIZE AND NOT MSVC)
        target_compile_options(${target} PRIVATE -fsanitize=address,undefined)
        target_link_options(${target} PRIVATE -fsanitize=address,undefined)
    endif()
endfunction()

derivkit_warnings(derivkit)

if(DERIVKIT_BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()

if(DERIVKIT_BUILD_EXAMPLES)
    add_subdirectory(examples)
endif()

install(TARGETS derivkit
    EXPORT derivkitTargets
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)
install(DIRECTORY include/derivkit DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
install(EXPORT derivkitTargets
    FILE derivkitTargets.cmake
    NAMESPACE derivkit::
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/derivkit
)

include(CMakePackageConfigHelpers)
configure_package_config_file(
    cmake/derivkitConfig.cmake.in
    ${CMAKE_CURRENT_BINARY_DIR}/derivkitConfig.cmake
    INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/derivkit
)
write_basic_package_version_file(
    ${CMAKE_CURRENT_BINARY_DIR}/derivkitConfigVersion.cmake
    VERSION ${PROJECT_VERSION}
    COMPATIBILITY SameMajorVersion
)
install(FILES
    ${CMAKE_CURRENT_BINARY_DIR}/derivkitConfig.cmake
    ${CMAKE_CURRENT_BINARY_DIR}/derivkitConfigVersion.cmake
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/derivkit
)
