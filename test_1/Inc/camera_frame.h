#ifndef CAMERA_FRAME_H
#define CAMERA_FRAME_H
#include <stdint.h>

#define CAMERA_LINK_TIMEOUT_MS 2000UL
#define CAMERA_MAX_FRAME_BYTES (256UL * 1024UL)

typedef struct {
    uint8_t header[20];
    uint32_t header_used, remaining, size, crc, expected_crc;
    uint8_t markers_ok;
} camera_frame_t;

static inline uint32_t camera_u32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static inline void camera_frame_reset(camera_frame_t *p)
{
    p->header_used = 0;
    p->remaining = 0;
}

/* Stream ECAM header/payload; return 1 valid, -1 invalid, 0 incomplete.
 * Only the small header is buffered, never the full JPEG.
 */
static inline int camera_frame_feed(camera_frame_t *p, uint8_t byte)
{
    static const uint8_t magic[4] = {'E', 'C', 'A', 'M'};
    if (!p->remaining) {
        if (p->header_used < 4 && byte != magic[p->header_used]) {
            p->header_used = byte == 'E' ? 1UL : 0UL;
            if (p->header_used) p->header[0] = byte;
            return 0;
        }
        p->header[p->header_used++] = byte;
        if (p->header_used != 20) return 0;
        p->size = camera_u32(p->header + 4);
        p->expected_crc = camera_u32(p->header + 8);
        if (p->size < 4 || p->size > CAMERA_MAX_FRAME_BYTES ||
            !(p->header[16] | p->header[17]) || !(p->header[18] | p->header[19])) {
            camera_frame_reset(p);
            return -1;
        }
        p->remaining = p->size;
        p->crc = 0xFFFFFFFFUL;
        p->markers_ok = 1;
        return 0;
    }
    uint32_t index = p->size - p->remaining;
    if ((index == 0 && byte != 0xFF) || (index == 1 && byte != 0xD8) ||
        (p->remaining == 2 && byte != 0xFF) || (p->remaining == 1 && byte != 0xD9))
        p->markers_ok = 0;
    p->crc ^= byte;
    for (uint32_t bit = 0; bit < 8; ++bit)
        p->crc = (p->crc >> 1) ^ ((p->crc & 1UL) ? 0xEDB88320UL : 0UL);
    if (--p->remaining) return 0;
    int valid = (p->crc ^ 0xFFFFFFFFUL) == p->expected_crc && p->markers_ok;
    camera_frame_reset(p);
    return valid ? 1 : -1;
}

static inline int camera_link_recent(uint32_t seen, uint32_t last, uint32_t now)
{
    return seen && (uint32_t)(now - last) < CAMERA_LINK_TIMEOUT_MS;
}
#endif
