/* TRASC PCM playback endpoint. SPDX-License-Identifier: MIT; see audio-LICENSE.
 * ALSA plug converts Windows formats to 48 kHz stereo S16_LE. The Android
 * playback head supplies the clock; writes are bounded and nonblocking there.
 * Protocol: little-endian uint32 words, followed by interleaved PCM bytes.
 */
#define _GNU_SOURCE
#include <alsa/asoundlib.h>
#include <alsa/pcm_external.h>
#include <errno.h>
#include <poll.h>
#include <stdint.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>

struct endpoint { snd_pcm_ioplug_t io; int fd; uint64_t played, written; uint32_t last; snd_pcm_uframes_t boundary; };

static int send_bytes(int fd, const void *data, size_t size) {
    const char *p = data;
    while (size) {
        ssize_t n = send(fd, p, size, MSG_NOSIGNAL);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return -ENODEV;
        p += n; size -= n;
    }
    return 0;
}
static int reply(struct endpoint *p, uint32_t *value) {
    unsigned char *data = (void *)value; size_t size = 4;
    while (size) {
        ssize_t n = recv(p->fd, data, size, 0);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return -ENODEV;
        data += n; size -= n;
    }
    return 0;
}
static int command(struct endpoint *p, uint32_t cmd, uint32_t *value) {
    if (p->fd < 0 || send_bytes(p->fd, &cmd, 4) < 0) return -ENODEV;
    return reply(p, value);
}
static int start(snd_pcm_ioplug_t *io) {
    uint32_t status; struct endpoint *p = io->private_data;
    return command(p, 1, &status) < 0 || status ? -ENODEV : 0;
}
static int stop(snd_pcm_ioplug_t *io) {
    uint32_t status; struct endpoint *p = io->private_data;
    if (p->fd < 0) return 0;
    if (command(p, 2, &status) < 0 || status) return -ENODEV;
    p->played = p->written = p->last = 0;
    return 0;
}
static snd_pcm_sframes_t position(snd_pcm_ioplug_t *io) {
    struct endpoint *p = io->private_data; uint32_t head;
    if (command(p, 3, &head) < 0) return -ENODEV;
    p->played += (uint32_t)(head - p->last); p->last = head;
    /* Returning modulo the small ring loses a whole-buffer advance after a
     * scheduling pause. Use ALSA's large boundary so an empty ring stays writable.
     */
    return p->played % p->boundary;
}
static snd_pcm_sframes_t transfer(snd_pcm_ioplug_t *io, const snd_pcm_channel_area_t *areas,
                                  snd_pcm_uframes_t offset, snd_pcm_uframes_t size) {
    struct endpoint *p = io->private_data;
    if (areas[0].step != 32 || areas[0].first % 8) return -EINVAL;
    if (size > 4096) size = 4096;
    uint32_t header[] = {4, (uint32_t)size}, accepted;
    const char *data = (const char *)areas[0].addr + areas[0].first / 8 + offset * 4;
    if (send_bytes(p->fd, header, sizeof(header)) < 0 || send_bytes(p->fd, data, size * 4) < 0 || reply(p, &accepted) < 0)
        return -ENODEV;
    if (accepted > size) return -EIO;
    p->written += accepted;
    return accepted ? (snd_pcm_sframes_t)accepted : -EAGAIN;
}
static int prepare(snd_pcm_ioplug_t *io) {
    struct endpoint *p = io->private_data; uint32_t status;
    if (command(p, 5, &status) < 0 || status) return -ENODEV;
    p->played = p->written = p->last = 0;
    return 0;
}
static int hw_free(snd_pcm_ioplug_t *io) {
    struct endpoint *p = io->private_data;
    if (p->fd >= 0) close(p->fd);
    p->fd = -1; return 0;
}
static int sw_params(snd_pcm_ioplug_t *io, snd_pcm_sw_params_t *params) {
    struct endpoint *p = io->private_data;
    return snd_pcm_sw_params_get_boundary(params, &p->boundary);
}
static int hw_params(snd_pcm_ioplug_t *io, snd_pcm_hw_params_t *params) {
    (void)params;
    struct endpoint *p = io->private_data; struct sockaddr_un addr = {.sun_family = AF_UNIX};
    const char *path = getenv("TRASC_AUDIO_SOCKET");
    if (!path || strlen(path) >= sizeof(addr.sun_path)) return -EINVAL;
    hw_free(io);
    p->fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (p->fd < 0) return -errno;
    struct timeval timeout = {.tv_sec = 1};
    setsockopt(p->fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    setsockopt(p->fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
    strcpy(addr.sun_path, path);
    uint32_t header[] = {0x50414c54, 1, 48000, 2, (uint32_t)io->buffer_size}, status;
    if (connect(p->fd, (void *)&addr, sizeof(addr)) < 0 || send_bytes(p->fd, header, sizeof(header)) < 0 || reply(p, &status) < 0 || status) {
        hw_free(io); return -ENODEV;
    }
    return 0;
}
static int drain(snd_pcm_ioplug_t *io) {
    struct endpoint *p = io->private_data;
    /* ALSA changes PREPARED to DRAINING before invoking this callback. */
    if (start(io) < 0) return -ENODEV;
    /* Maximum advertised buffer is one second. Bound a lost-device drain. */
    for (int i = 0; i < 400; i++) {
        if (position(io) < 0) return -ENODEV;
        if (p->played >= p->written) return 0;
        struct timespec delay = {.tv_nsec = 5000000}; nanosleep(&delay, NULL);
    }
    return -EIO;
}
static int close_pcm(snd_pcm_ioplug_t *io) { hw_free(io); free(io->private_data); return 0; }
static const snd_pcm_ioplug_callback_t callbacks = {
    .start = start, .stop = stop, .pointer = position, .transfer = transfer,
    .prepare = prepare, .hw_params = hw_params, .hw_free = hw_free, .sw_params = sw_params, .drain = drain, .close = close_pcm
};
SND_PCM_PLUGIN_DEFINE_FUNC(trasc) {
    (void)root; (void)conf;
    if (stream != SND_PCM_STREAM_PLAYBACK) return -ENODEV;
    struct endpoint *p = calloc(1, sizeof(*p));
    if (!p) return -ENOMEM;
    p->fd = -1; p->boundary = 1; p->io.version = SND_PCM_IOPLUG_VERSION;
    p->io.flags = SND_PCM_IOPLUG_FLAG_BOUNDARY_WA;
    p->io.name = "TRASC Android audio"; p->io.callback = &callbacks; p->io.private_data = p;
    p->io.poll_fd = -1;
    int err = snd_pcm_ioplug_create(&p->io, name, stream, mode);
    if (err < 0) { free(p); return err; }
    /* ALSA's rate/format conversion plugins require an mmap-capable slave.
     * For MMAP access ALSA allocates a local ring and calls transfer at commit;
     * ordinary RW access continues to call transfer directly (mmap_rw stays 0).
     */
    const unsigned access[] = {SND_PCM_ACCESS_RW_INTERLEAVED, SND_PCM_ACCESS_MMAP_INTERLEAVED};
    const unsigned format[] = {SND_PCM_FORMAT_S16_LE};
    if ((err = snd_pcm_ioplug_set_param_list(&p->io, SND_PCM_IOPLUG_HW_ACCESS, 2, access)) < 0 ||
        (err = snd_pcm_ioplug_set_param_list(&p->io, SND_PCM_IOPLUG_HW_FORMAT, 1, format)) < 0 ||
        (err = snd_pcm_ioplug_set_param_minmax(&p->io, SND_PCM_IOPLUG_HW_CHANNELS, 2, 2)) < 0 ||
        (err = snd_pcm_ioplug_set_param_minmax(&p->io, SND_PCM_IOPLUG_HW_RATE, 48000, 48000)) < 0 ||
        (err = snd_pcm_ioplug_set_param_minmax(&p->io, SND_PCM_IOPLUG_HW_PERIOD_BYTES, 128, 32768)) < 0 ||
        (err = snd_pcm_ioplug_set_param_minmax(&p->io, SND_PCM_IOPLUG_HW_BUFFER_BYTES, 256, 192000)) < 0 ||
        (err = snd_pcm_ioplug_set_param_minmax(&p->io, SND_PCM_IOPLUG_HW_PERIODS, 2, 16)) < 0) {
        snd_pcm_ioplug_delete(&p->io); return err;
    }
    *pcmp = p->io.pcm; return 0;
}
SND_PCM_PLUGIN_SYMBOL(trasc);
