/* NUCLEO-F411RE: ESP32-CAM relay on D8/D2 and SG90 pan on D3. */
#include <stdint.h>
#include "camera_frame.h"
#include "servo_command.h"

#define REG32(a) (*(volatile uint32_t *)(a))
#define RCC_CR REG32(0x40023800UL)
#define RCC_PLLCFGR REG32(0x40023804UL)
#define RCC_CFGR REG32(0x40023808UL)
#define RCC_APB1RSTR REG32(0x40023820UL)
#define RCC_AHB1ENR REG32(0x40023830UL)
#define RCC_APB1ENR REG32(0x40023840UL)
#define RCC_APB2ENR REG32(0x40023844UL)
#define GPIOA_MODER REG32(0x40020000UL)
#define GPIOA_OSPEEDR REG32(0x40020008UL)
#define GPIOA_PUPDR REG32(0x4002000CUL)
#define GPIOA_BSRR REG32(0x40020018UL)
#define GPIOA_AFRL REG32(0x40020020UL)
#define GPIOA_AFRH REG32(0x40020024UL)
#define GPIOB_MODER REG32(0x40020400UL)
#define GPIOB_OTYPER REG32(0x40020404UL)
#define GPIOB_OSPEEDR REG32(0x40020408UL)
#define GPIOB_PUPDR REG32(0x4002040CUL)
#define GPIOB_AFRL REG32(0x40020420UL)
#define TIM2_CR1 REG32(0x40000000UL)
#define TIM2_SR REG32(0x40000010UL)
#define TIM2_EGR REG32(0x40000014UL)
#define TIM2_CCMR1 REG32(0x40000018UL)
#define TIM2_CCER REG32(0x40000020UL)
#define TIM2_PSC REG32(0x40000028UL)
#define TIM2_ARR REG32(0x4000002CUL)
#define TIM2_CCR2 REG32(0x40000038UL)
#define ESP_UART 0x40011000UL
#define PC_UART 0x40004400UL
#define CPU_HZ 96000000UL
#define PC_UART_HZ 48000000UL
#define SERVO_MIN_DEG 60UL
#define SERVO_MAX_DEG 120UL
#define SERVO_TIMEOUT_MS 500UL
#define UART_REG(base, offset) REG32((base) + (offset))

static volatile uint32_t milliseconds;
volatile uint32_t servo_angle = 90, servo_target = 90;
volatile uint32_t servo_commands, servo_stops, last_servo_command_ms;
static uint32_t last_servo_step_ms, last_command_byte_ms;
static servo_command_t servo_command;
volatile uint32_t valid_frames, invalid_frames, received_bytes;
volatile uint32_t uart_errors, pc_uart_errors, relay_overflows;
volatile uint32_t last_valid_frame_ms, last_rx_ms, esp_link_active;

typedef struct {
    uint8_t bytes[1024];
    uint16_t head, tail;
} queue_t;
static queue_t to_pc, to_esp;
static camera_frame_t frame;
static char baud_reply[24];
static uint32_t baud_reply_used, pending_baud;

static void track_baud_reply(uint8_t byte)
{
    if (byte == '\n') {
        uint32_t baud = 0;
        if (baud_reply_used > 5 && baud_reply[0] == 'B' &&
            baud_reply[1] == 'A' && baud_reply[2] == 'U' &&
            baud_reply[3] == 'D' && baud_reply[4] == ' ') {
            for (uint32_t i = 5; i < baud_reply_used; ++i) {
                if (baud_reply[i] < '0' || baud_reply[i] > '9') { baud = 0; break; }
                baud = baud * 10 + (uint32_t)(baud_reply[i] - '0');
            }
            if (baud == 115200 || baud == 230400 || baud == 460800 ||
                baud == 921600 || baud == 1500000 || baud == 2000000)
                pending_baud = baud;
        }
        baud_reply_used = 0;
    } else if (byte != '\r') {
        if (baud_reply_used < sizeof(baud_reply)) baud_reply[baud_reply_used++] = byte;
        else baud_reply_used = 0;
    }
}

void SystemInit(void)
{
    /* HSI 16MHz /16 *192 /2 = 96MHz; APB1=48MHz, APB2=96MHz.
     * TIM2 receives 96MHz because APB1 is prescaled by two.
     */
    RCC_CR |= 1UL;
    while (!(RCC_CR & (1UL << 1))) {}
    RCC_CFGR &= ~3UL;
    while (RCC_CFGR & (3UL << 2)) {}
    RCC_CR &= ~(1UL << 24);
    while (RCC_CR & (1UL << 25)) {}
    RCC_APB1ENR |= 1UL << 28; /* PWR clock. */
    (void)RCC_APB1ENR;
    REG32(0x40007000UL) |= 3UL << 14; /* Voltage scale 1. */
    REG32(0x40023C00UL) = (1UL << 10) | (1UL << 9) | (1UL << 8) | 3UL;
    RCC_PLLCFGR = 16UL | (192UL << 6) | (4UL << 24);
    RCC_CFGR = 4UL << 10;
    RCC_CR |= 1UL << 24;
    while (!(RCC_CR & (1UL << 25))) {}
    RCC_CFGR |= 2UL;
    while ((RCC_CFGR & (3UL << 2)) != (2UL << 2)) {}
    REG32(0xE000ED08UL) = 0x08000000UL;
}

static void servo_apply(void)
{
    /* Nominal 1..2ms mapping; conservative 60..120 degree travel. */
    TIM2_CCR2 = 1000UL + (servo_angle * 1000UL + 90UL) / 180UL;
}

static void servo_init(void)
{
    RCC_APB1RSTR |= 1UL;
    RCC_APB1RSTR &= ~1UL;
    /* PB3 AF1 = TIM2_CH2. Preserve PA13/PA14 SWD. */
    GPIOB_AFRL = (GPIOB_AFRL & ~(15UL << 12)) | (1UL << 12);
    GPIOB_OTYPER &= ~(1UL << 3);
    GPIOB_OSPEEDR &= ~(3UL << 6);
    GPIOB_PUPDR &= ~(3UL << 6);
    GPIOB_MODER = (GPIOB_MODER & ~(3UL << 6)) | (2UL << 6);
    TIM2_PSC = CPU_HZ / 1000000UL - 1;
    TIM2_ARR = 19999UL;
    TIM2_CCMR1 = (6UL << 12) | (1UL << 11); /* CH2 PWM1 + preload. */
    servo_apply();
    TIM2_CR1 = 1UL << 7;
    TIM2_EGR = 1;
    TIM2_SR = 0;
    TIM2_CCER = 1UL << 4;
    TIM2_CR1 |= 1;
}

static void servo_update(uint32_t now)
{
    /* Freeze on stale commands instead of continuing to an old target. */
    if (now - last_servo_command_ms >= SERVO_TIMEOUT_MS)
        servo_target = servo_angle;
    if (now - last_servo_step_ms < 20UL) return;
    last_servo_step_ms = now;
    if (servo_angle < servo_target) ++servo_angle;
    else if (servo_angle > servo_target) --servo_angle;
    servo_apply();
}

static int consume_servo_byte(uint8_t byte, uint32_t now)
{
    if (servo_command.active && now - last_command_byte_ms >= 100UL)
        servo_command.active = 0;
    last_command_byte_ms = now;
    int result = servo_command_feed(&servo_command, byte);
    if (result == 2) {
        uint32_t angle = servo_command.value;
        if (angle < SERVO_MIN_DEG) angle = SERVO_MIN_DEG;
        if (angle > SERVO_MAX_DEG) angle = SERVO_MAX_DEG;
        servo_target = angle;
        ++servo_commands;
        last_servo_command_ms = now;
    } else if (result == 3) {
        servo_target = servo_angle;
        ++servo_stops;
        last_servo_command_ms = now;
    } else if (result == 4) {
        /* PC recovery after a camera reset: restore both relay UARTs.
         * No acknowledgement is added to the binary JPEG stream.
         */
        UART_REG(ESP_UART, 8) = (CPU_HZ + 57600UL) / 115200UL;
        UART_REG(PC_UART, 8) = (PC_UART_HZ + 57600UL) / 115200UL;
        pending_baud = baud_reply_used = 0;
        to_pc.head = to_pc.tail = to_esp.head = to_esp.tail = 0;
        camera_frame_reset(&frame);
        servo_target = servo_angle;
    }
    return result != 0;
}

void SysTick_Handler(void) { milliseconds++; }

static void enqueue(queue_t *q, uint8_t byte)
{
    if ((uint16_t)(q->head - q->tail) == sizeof(q->bytes)) {
        relay_overflows++;
        return;
    }
    q->bytes[q->head++ & 1023U] = byte;
}

static void transmit(queue_t *q, uint32_t uart)
{
    if (q->head != q->tail && (UART_REG(uart, 0) & (1UL << 7)))
        UART_REG(uart, 4) = q->bytes[q->tail++ & 1023U];
}

static void uart_init(uint32_t uart, uint32_t clock)
{
    UART_REG(uart, 0x0C) = 0;
    UART_REG(uart, 0x10) = 0;
    UART_REG(uart, 0x14) = 0;
    UART_REG(uart, 0x08) = (clock + 57600UL) / 115200UL;
    UART_REG(uart, 0x0C) = (1UL << 13) | (1UL << 3) | (1UL << 2);
}

int main(void)
{
    RCC_AHB1ENR |= 3UL; /* GPIOA and GPIOB. */
    RCC_APB2ENR |= 1UL << 4; /* USART1: ESP32-CAM. */
    RCC_APB1ENR |= (1UL << 17) | 1UL; /* USART2 VCP and TIM2. */
    (void)RCC_AHB1ENR; (void)RCC_APB2ENR; (void)RCC_APB1ENR;
    /* PA2/PA3 = AF7 USART2; PA9/PA10 = AF7 USART1. PA5 = LD2. */
    GPIOA_AFRL = (GPIOA_AFRL & ~0xFF00UL) | 0x7700UL;
    GPIOA_AFRH = (GPIOA_AFRH & ~0xFF0UL) | 0x770UL;
    GPIOA_MODER = (GPIOA_MODER & ~((15UL << 4) | (3UL << 10) | (15UL << 18))) |
                  (10UL << 4) | (1UL << 10) | (10UL << 18);
    GPIOA_OSPEEDR |= (15UL << 4) | (15UL << 18);
    GPIOA_PUPDR = (GPIOA_PUPDR & ~((3UL << 6) | (3UL << 20))) |
                  (1UL << 6) | (1UL << 20);
    GPIOA_BSRR = 1UL << 21;
    servo_init();
    uart_init(ESP_UART, CPU_HZ);
    uart_init(PC_UART, PC_UART_HZ);
    REG32(0xE000E014UL) = CPU_HZ / 1000UL - 1;
    REG32(0xE000E018UL) = 0;
    REG32(0xE000E010UL) = 7;

    for (;;) {
        uint32_t now = milliseconds;
        if ((frame.header_used || frame.remaining) && now - last_rx_ms >= 1000UL) {
            invalid_frames++;
            camera_frame_reset(&frame);
        }
        uint32_t status = UART_REG(ESP_UART, 0);
        if (status & 15UL) {
            (void)UART_REG(ESP_UART, 4);
            uart_errors++;
            camera_frame_reset(&frame);
        } else if (status & (1UL << 5)) {
            uint8_t byte = (uint8_t)UART_REG(ESP_UART, 4);
            received_bytes++;
            last_rx_ms = now;
            /* Text replies only occur between binary camera frames. */
            if (!frame.remaining && !frame.header_used) track_baud_reply(byte);
            int result = camera_frame_feed(&frame, byte);
            if (result) baud_reply_used = 0;
            if (result > 0) { valid_frames++; last_valid_frame_ms = now; }
            else if (result < 0) invalid_frames++;
            enqueue(&to_pc, byte);
        }
        status = UART_REG(PC_UART, 0);
        if (status & 15UL) {
            (void)UART_REG(PC_UART, 4);
            pc_uart_errors++;
            servo_command.active = 0;
            servo_target = servo_angle;
        } else if (status & (1UL << 5)) {
            uint8_t byte = (uint8_t)UART_REG(PC_UART, 4);
            if (!consume_servo_byte(byte, now)) enqueue(&to_esp, byte);
        }
        transmit(&to_pc, PC_UART);
        transmit(&to_esp, ESP_UART);
        /* Deliver the ESP's baud acknowledgement at the old rate first. */
        if (pending_baud && to_pc.head == to_pc.tail && to_esp.head == to_esp.tail &&
            (UART_REG(PC_UART, 0) & (1UL << 6)) &&
            (UART_REG(ESP_UART, 0) & (1UL << 6))) {
            UART_REG(ESP_UART, 8) = (CPU_HZ + pending_baud / 2) / pending_baud;
            UART_REG(PC_UART, 8) = (PC_UART_HZ + pending_baud / 2) / pending_baud;
            pending_baud = 0;
            baud_reply_used = 0;
        }
        servo_update(now);
        esp_link_active = camera_link_recent(valid_frames, last_valid_frame_ms, now);
        GPIOA_BSRR = esp_link_active ? (1UL << 5) : (1UL << 21);
    }
}
