cmake_minimum_required(VERSION 3.20)
set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR arm)
set(CMAKE_C_COMPILER arm-none-eabi-gcc)
set(CMAKE_ASM_COMPILER arm-none-eabi-gcc)
set(CMAKE_OBJCOPY arm-none-eabi-objcopy)
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)
project(stm32_sg90 LANGUAGES C ASM)

add_executable(stm32_sg90 stm32.c stm32-sg90/startup_stm32f411.S)
set_target_properties(stm32_sg90 PROPERTIES SUFFIX ".elf")
target_include_directories(stm32_sg90 PRIVATE test_1/Inc stm32-sg90)
target_compile_options(stm32_sg90 PRIVATE
    -mcpu=cortex-m4 -mthumb -mfloat-abi=soft -Wall -Wextra -Wpedantic -Werror
    -ffreestanding -ffunction-sections -fdata-sections
    $<$<CONFIG:Debug>:-O0;-g3>
    $<$<CONFIG:Release>:-Os>
)
set(linker_script ${CMAKE_CURRENT_SOURCE_DIR}/stm32-sg90/stm32f411re.ld)
set_target_properties(stm32_sg90 PROPERTIES LINK_DEPENDS "${linker_script}")
target_link_options(stm32_sg90 PRIVATE
    -mcpu=cortex-m4 -mthumb -mfloat-abi=soft -nostdlib -T${linker_script}
    -Wl,--gc-sections,-Map=${CMAKE_CURRENT_BINARY_DIR}/stm32_sg90.map
    -Wl,--print-memory-usage
)
add_custom_command(TARGET stm32_sg90 POST_BUILD
    COMMAND ${CMAKE_OBJCOPY} -O binary
            $<TARGET_FILE:stm32_sg90> ${CMAKE_CURRENT_BINARY_DIR}/stm32_sg90.bin
    VERBATIM
)
