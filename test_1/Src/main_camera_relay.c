#include <stdint.h>
#include "camera_frame.h"

#define REG32(a) (*(volatile uint32_t *)(a))
#define RCC_CR REG32(0x40021000UL)
#define RCC_CFGR REG32(0x40021004UL)
#define RCC_APB2ENR REG32(0x40021018UL)
#define RCC_APB1ENR REG32(0x4002101CUL)
#define GPIOA_CRL REG32(0x40010800UL)
#define GPIOA_CRH REG32(0x40010804UL)
#define GPIOA_BSRR REG32(0x40010810UL)
#define ESP_UART 0x40013800UL
#define PC_UART 0x40004400UL
#define UART_REG(base, offset) REG32((base) + (offset))

static volatile uint32_t milliseconds;
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
    /* HSI/2 x16 = 64 MHz, APB1 = 32 MHz, APB2 = 64 MHz. */
    RCC_CR |= 1UL;
    while (!(RCC_CR & (1UL << 1))) {}
    RCC_CFGR &= ~3UL;
    while (RCC_CFGR & (3UL << 2)) {}
    RCC_CR &= ~(1UL << 24);
    while (RCC_CR & (1UL << 25)) {}
    REG32(0x40022000UL) = (1UL << 4) | 2UL; /* Flash prefetch + 2 wait states. */
    RCC_CFGR = (4UL << 8) | (14UL << 18);
    RCC_CR |= 1UL << 24;
    while (!(RCC_CR & (1UL << 25))) {}
    RCC_CFGR |= 2UL;
    while ((RCC_CFGR & (3UL << 2)) != (2UL << 2)) {}
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
    RCC_APB2ENR |= (1UL << 2) | (1UL << 14);
    RCC_APB1ENR |= 1UL << 17;
    (void)RCC_APB2ENR; (void)RCC_APB1ENR;
    /* PA2/PA9 TX: AF push-pull; PA3/PA10 RX: input pull-up; PA5 LD2 output. */
    GPIOA_BSRR = (1UL << 3) | (1UL << 10) | (1UL << 21);
    GPIOA_CRL = (GPIOA_CRL & ~((15UL << 20) | 0xFF00UL)) |
                (2UL << 20) | 0x8A00UL;
    GPIOA_CRH = (GPIOA_CRH & ~0xFF0UL) | 0x8A0UL;
    uart_init(ESP_UART, 64000000UL);
    uart_init(PC_UART, 32000000UL);
    REG32(0xE000E014UL) = 64000UL - 1;
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
        } else if (status & (1UL << 5)) {
            enqueue(&to_esp, (uint8_t)UART_REG(PC_UART, 4));
        }
        transmit(&to_pc, PC_UART);
        transmit(&to_esp, ESP_UART);
        /* Deliver the ESP's baud acknowledgement at the old rate first. */
        if (pending_baud && to_pc.head == to_pc.tail && to_esp.head == to_esp.tail &&
            (UART_REG(PC_UART, 0) & (1UL << 6)) &&
            (UART_REG(ESP_UART, 0) & (1UL << 6))) {
            UART_REG(ESP_UART, 8) = (64000000UL + pending_baud / 2) / pending_baud;
            UART_REG(PC_UART, 8) = (32000000UL + pending_baud / 2) / pending_baud;
            pending_baud = 0;
            baud_reply_used = 0;
        }
        esp_link_active = camera_link_recent(valid_frames, last_valid_frame_ms, now);
        GPIOA_BSRR = esp_link_active ? (1UL << 5) : (1UL << 21);
    }
}
