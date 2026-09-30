#include <stdint.h>

#define REG32(a) (*(volatile uint32_t *)(a))
#define RCC_CR REG32(0x40023800UL)
#define RCC_CFGR REG32(0x40023808UL)
#define RCC_AHB1ENR REG32(0x40023830UL)
#define RCC_APB1ENR REG32(0x40023840UL)
#define GPIO_REG(base, offset) REG32((base) + (offset))
#define GPIOA 0x40020000UL
#define GPIOB 0x40020400UL
#define USART_SR REG32(0x40004400UL)
#define USART_DR REG32(0x40004404UL)
#define USART_BRR REG32(0x40004408UL)
#define USART_CR1 REG32(0x4000440CUL)
#define USART_CR2 REG32(0x40004410UL)
#define USART_CR3 REG32(0x40004414UL)
#define SYSTICK_CTRL REG32(0xE000E010UL)
#define SYSTICK_LOAD REG32(0xE000E014UL)
#define SYSTICK_VAL REG32(0xE000E018UL)

static volatile uint32_t milliseconds;
volatile uint32_t person_count;
volatile uint32_t led_mask;
volatile uint32_t received_packets;

void SystemInit(void)
{
    RCC_CR |= 1UL;
    while (!(RCC_CR & (1UL << 1))) {}
    RCC_CFGR &= ~3UL;
    while (RCC_CFGR & (3UL << 2)) {}
    RCC_CFGR &= ~((15UL << 4) | (7UL << 10) | (7UL << 13));
}

void SysTick_Handler(void) { milliseconds++; }

static void output_pin(uint32_t base, uint32_t pin)
{
    GPIO_REG(base, 0x18) = 1UL << (pin + 16);
    GPIO_REG(base, 0x04) &= ~(1UL << pin);
    GPIO_REG(base, 0x08) &= ~(3UL << (pin * 2));
    GPIO_REG(base, 0x0C) &= ~(3UL << (pin * 2));
    GPIO_REG(base, 0x00) = (GPIO_REG(base, 0x00) & ~(3UL << (pin * 2))) |
                         (1UL << (pin * 2));
}

static void set_leds(uint32_t mask)
{
    /* bit 0..3 = D4 PB5, D5 PB4, D6 PB10, D7 PA8. Active high. */
    uint32_t b = ((mask & 1UL) ? (1UL << 5) : 0UL) |
                 ((mask & 2UL) ? (1UL << 4) : 0UL) |
                 ((mask & 4UL) ? (1UL << 10) : 0UL);
    uint32_t all_b = (1UL << 5) | (1UL << 4) | (1UL << 10);
    GPIO_REG(GPIOB, 0x18) = b | ((all_b & ~b) << 16);
    GPIO_REG(GPIOA, 0x18) = (mask & 8UL) ? (1UL << 8) : (1UL << 24);
    led_mask = mask;
}

static void uart_put(char c)
{
    while (!(USART_SR & (1UL << 7))) {}
    USART_DR = (uint8_t)c;
}

static void uart_number(uint32_t value)
{
    char digits[10];
    uint32_t length = 0;
    do { digits[length++] = (char)('0' + value % 10); value /= 10; } while (value);
    while (length) uart_put(digits[--length]);
}

static void acknowledge(void)
{
    uart_put('A'); uart_put('C'); uart_put('K'); uart_put(' ');
    uart_number(person_count); uart_put(' '); uart_number(led_mask); uart_put('\n');
}

int main(void)
{
    RCC_AHB1ENR |= 3UL;
    RCC_APB1ENR |= 1UL << 17;
    (void)RCC_AHB1ENR;
    output_pin(GPIOB, 5); output_pin(GPIOB, 4); output_pin(GPIOB, 10);
    output_pin(GPIOA, 8); output_pin(GPIOA, 5);
    /* USART2 PA2/PA3 AF7, ST-LINK Virtual COM, HSI 16 MHz, 115200 8N1. */
    GPIO_REG(GPIOA, 0x00) = (GPIO_REG(GPIOA, 0x00) & ~((3UL << 4) | (3UL << 6))) |
                         (2UL << 4) | (2UL << 6);
    GPIO_REG(GPIOA, 0x20) = (GPIO_REG(GPIOA, 0x20) & ~((15UL << 8) | (15UL << 12))) |
                         (7UL << 8) | (7UL << 12);
    GPIO_REG(GPIOA, 0x0C) = (GPIO_REG(GPIOA, 0x0C) & ~((3UL << 4) | (3UL << 6))) |
                         (1UL << 6);
    USART_CR1 = 0; USART_CR2 = 0; USART_CR3 = 0;
    USART_BRR = 139UL;
    USART_CR1 = (1UL << 13) | (1UL << 3) | (1UL << 2);
    SYSTICK_LOAD = 16000UL - 1;
    SYSTICK_VAL = 0;
    SYSTICK_CTRL = 7UL;

    uint8_t packet[5];
    uint32_t used = 0, last_byte = 0, last_packet = 0;
    for (;;)
    {
        uint32_t now = milliseconds;
        if (used && now - last_byte > 50UL) used = 0;
        if (now - last_packet >= 1000UL)
        {
            person_count = 0; set_leds(0);
            GPIO_REG(GPIOA, 0x18) = 1UL << 21; /* LD2: link inactive */
        }
        uint32_t status = USART_SR;
        if (status & 15UL) { (void)USART_DR; used = 0; continue; }
        if (!(status & (1UL << 5))) continue;
        uint8_t byte = (uint8_t)USART_DR;
        if (!used && byte == '?') { acknowledge(); continue; }
        if (!used && byte != 0xA5) continue;
        packet[used++] = byte; last_byte = now;
        if (used != 5) continue;
        used = 0;
        if (packet[1] > 1 || packet[4] !=
            (uint8_t)(0x5A ^ packet[0] ^ packet[1] ^ packet[2] ^ packet[3])) continue;
        person_count = packet[2] | ((uint32_t)packet[3] << 8);
        uint32_t capped = person_count;
        uint32_t mask;
        if (packet[1]) { if (capped > 15) capped = 15; mask = capped; }
        else { if (capped > 4) capped = 4; mask = (1UL << capped) - 1UL; }
        set_leds(mask);
        last_packet = now; received_packets++;
        GPIO_REG(GPIOA, 0x18) = 1UL << 5; /* LD2: recent valid data */
        acknowledge();
    }
}
