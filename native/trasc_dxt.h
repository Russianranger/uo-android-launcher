/* SPDX-License-Identifier: MIT
 * TRASC S3TC decode for GLES hosts. Input is packed BC blocks, output RGBA8.
 * Keep compressed guest storage/strides; only the host texture is expanded.
 */
#ifndef TRASC_DXT_H
#define TRASC_DXT_H
#include <stdint.h>
#include <stdlib.h>
#include <limits.h>

static unsigned trasc_dxt_u16(const uint8_t *p) { return p[0] | ((unsigned)p[1] << 8); }
static void trasc_dxt_rgb(unsigned c, uint8_t *p)
{
    p[0] = ((c >> 11) * 255 + 15) / 31;
    p[1] = (((c >> 5) & 63) * 255 + 31) / 63;
    p[2] = ((c & 31) * 255 + 15) / 31;
    p[3] = 255;
}
/* kind: 1=DXT1 RGB, 2=DXT1 RGBA, 3=DXT3, 5=DXT5. */
static uint8_t *trasc_dxt_decode(const uint8_t *src, size_t size, unsigned w,
                                unsigned h, unsigned depth, unsigned kind)
{
    if (!w || !h || !depth || (kind != 1 && kind != 2 && kind != 3 && kind != 5)) return NULL;
    size_t bx = ((size_t)w + 3) / 4, by = ((size_t)h + 3) / 4, block = kind <= 2 ? 8 : 16;
    if (bx > SIZE_MAX / by || bx * by > SIZE_MAX / block / depth ||
        size < bx * by * block * depth || (size_t)w > SIZE_MAX / h / depth / 4) return NULL;
    uint8_t *out = malloc((size_t)w * h * depth * 4);
    if (!out) return NULL;
    for (unsigned z = 0; z < depth; ++z) for (size_t yb = 0; yb < by; ++yb) for (size_t xb = 0; xb < bx; ++xb) {
        const uint8_t *b = src + (((size_t)z * by + yb) * bx + xb) * block;
        const uint8_t *c = b + (kind <= 2 ? 0 : 8);
        unsigned c0 = trasc_dxt_u16(c), c1 = trasc_dxt_u16(c + 2);
        uint8_t colors[4][4], alpha[8];
        trasc_dxt_rgb(c0, colors[0]); trasc_dxt_rgb(c1, colors[1]);
        if (c0 > c1 || kind > 2) {
            for (unsigned k = 0; k < 3; ++k) {
                colors[2][k] = (2 * colors[0][k] + colors[1][k]) / 3;
                colors[3][k] = (colors[0][k] + 2 * colors[1][k]) / 3;
            }
            colors[2][3] = colors[3][3] = 255;
        } else {
            for (unsigned k = 0; k < 3; ++k) {
                colors[2][k] = (colors[0][k] + colors[1][k]) / 2;
                colors[3][k] = 0;
            }
            colors[2][3] = 255; colors[3][3] = kind == 2 ? 0 : 255;
        }
        uint64_t ai = 0;
        if (kind == 5) {
            alpha[0] = b[0]; alpha[1] = b[1];
            unsigned n = b[0] > b[1] ? 7 : 5;
            for (unsigned i = 1; i < n; ++i) alpha[i + 1] = ((n - i) * b[0] + i * b[1]) / n;
            if (n == 5) { alpha[6] = 0; alpha[7] = 255; }
            for (unsigned i = 0; i < 6; ++i) ai |= (uint64_t)b[i + 2] << (8 * i);
        }
        for (unsigned y = 0; y < 4; ++y) for (unsigned x = 0; x < 4; ++x) {
            if (xb * 4 + x >= w || yb * 4 + y >= h) continue;
            unsigned p = y * 4 + x, index = (c[4 + y] >> (2 * x)) & 3;
            uint8_t *dst = out + (((size_t)z * h + yb * 4 + y) * w + xb * 4 + x) * 4;
            for (unsigned k = 0; k < 4; ++k) dst[k] = colors[index][k];
            if (kind == 3) dst[3] = ((b[p / 2] >> (4 * (p % 2))) & 15) * 17;
            if (kind == 5) dst[3] = alpha[(ai >> (3 * p)) & 7];
        }
    }
    return out;
}
#endif
