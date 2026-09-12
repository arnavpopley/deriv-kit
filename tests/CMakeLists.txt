add_library(derivkit_harness INTERFACE)
target_include_directories(derivkit_harness INTERFACE ${CMAKE_CURRENT_SOURCE_DIR})

function(derivkit_test name)
    add_executable(${name} ${name}.cpp)
    target_link_libraries(${name} PRIVATE derivkit derivkit_harness)
    derivkit_warnings(${name})
    add_test(NAME ${name} COMMAND ${name})
endfunction()

derivkit_test(test_math)
derivkit_test(test_black_scholes)
derivkit_test(test_implied_vol)
derivkit_test(test_implied_forward)
derivkit_test(test_nse_calendar)
derivkit_test(test_trees)
derivkit_test(test_monte_carlo)

add_executable(test_groww test_groww.cpp ${CMAKE_SOURCE_DIR}/examples/groww_api.cpp)
target_include_directories(test_groww PRIVATE
    ${CMAKE_SOURCE_DIR}/examples
    ${CMAKE_CURRENT_SOURCE_DIR}
)
target_include_directories(test_groww SYSTEM PRIVATE
    ${CMAKE_SOURCE_DIR}/third_party
)
target_link_libraries(test_groww PRIVATE derivkit derivkit_harness)
target_compile_definitions(test_groww PRIVATE
    DERIVKIT_FIXTURE="${CMAKE_SOURCE_DIR}/examples/data/nifty_chain.json"
)
derivkit_warnings(test_groww)
add_test(NAME test_groww COMMAND test_groww)
