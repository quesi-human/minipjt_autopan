cmake_minimum_required(VERSION 3.20)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
include(${CMAKE_CURRENT_SOURCE_DIR}/cmake/gcc-arm-none-eabi.cmake)
project(test_1 LANGUAGES C ASM)

add_executable(test_1 Src/main_camera_relay.c Src/startup_stm32f103xb.S)
set_target_properties(test_1 PROPERTIES SUFFIX ".elf")
target_include_directories(test_1 PRIVATE Inc)
target_compile_definitions(test_1 PRIVATE STM32F103xB=1)
target_compile_options(test_1 PRIVATE
    -mcpu=cortex-m3 -mthumb -Wall -Wextra -Wpedantic
    -ffreestanding -ffunction-sections -fdata-sections
    $<$<CONFIG:Debug>:-O0;-g3>
    $<$<CONFIG:Release>:-Os>
)
set(linker_script ${CMAKE_CURRENT_SOURCE_DIR}/stm32f103xb_flash.ld)
set_target_properties(test_1 PROPERTIES LINK_DEPENDS "${linker_script}")
target_link_options(test_1 PRIVATE
    -mcpu=cortex-m3 -mthumb -nostdlib
    -T${linker_script}
    -Wl,--gc-sections,-Map=${CMAKE_CURRENT_BINARY_DIR}/test_1.map
    -Wl,--print-memory-usage
)
