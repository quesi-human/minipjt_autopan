#ifndef SERVO_COMMAND_H
#define SERVO_COMMAND_H
#include <stdint.h>

/* P<angle>\n sets the pan target; S\n stops; R\n restores boot baud.
 * These commands are consumed locally, never forwarded to the camera.
 */
typedef struct {
    uint32_t active, value, digits, invalid, stop;
} servo_command_t;

/* Return 0: forward; 1: consumed; 2: angle; 3: stop; 4: reset link. */
static inline int servo_command_feed(servo_command_t *p, uint8_t byte)
{
    if (!p->active) {
        if (byte != 'P' && byte != 'S' && byte != 'R') return 0;
        p->active = 1;
        p->value = p->digits = p->invalid = 0;
        p->stop = byte == 'R' ? 2U : (uint32_t)(byte == 'S');
        return 1;
    }
    if (byte == '\n') {
        p->active = 0;
        if (p->invalid) return 1;
        if (p->stop) return p->stop == 2U ? 4 : 3;
        return p->digits && p->value <= 180U ? 2 : 1;
    }
    if (byte == '\r') return 1;
    if (p->stop || byte < '0' || byte > '9' || p->digits >= 3U) {
        p->invalid = 1;
    } else {
        p->value = p->value * 10U + (uint32_t)(byte - '0');
        ++p->digits;
    }
    return 1;
}
#endif
