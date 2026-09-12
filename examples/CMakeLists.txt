add_executable(vanilla_comparison vanilla_comparison.cpp)
add_executable(american_put american_put.cpp)
add_executable(variance_reduction variance_reduction.cpp)
add_executable(convergence convergence.cpp)
add_executable(implied_vol implied_vol.cpp)
add_executable(groww_chain groww_chain.cpp groww_api.cpp)

target_include_directories(groww_chain PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
)
target_include_directories(groww_chain SYSTEM PRIVATE
    ${CMAKE_SOURCE_DIR}/third_party
)
target_compile_definitions(groww_chain PRIVATE
    DERIVKIT_FIXTURE="${CMAKE_SOURCE_DIR}/examples/data/nifty_chain.json"
)

foreach(example vanilla_comparison american_put variance_reduction convergence implied_vol groww_chain)
    target_link_libraries(${example} PRIVATE derivkit)
    derivkit_warnings(${example})
endforeach()
