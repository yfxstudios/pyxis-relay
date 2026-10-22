// pyxis-hdmi: plays the relay's live stream on the NanoPi R5C's HDMI port.
//
//   RTSP over TCP from the local relay (no demuxer buffering)
//   -> RTP depacketizer (H.264 / H.265) -> whole access units
//   -> Rockchip MPP hardware decoder (immediate output, no reordering delay)
//   -> NV12 dmabuf imported straight into a DRM/KMS plane (zero copy, hardware scaling)
//   -> vsync'd atomic page flips, paced by the stream's timestamps (even cadence)
//
// Waits for a screen to be plugged in, matches the TV's refresh rate to the stream's
// frame rate when the TV offers it, and goes black when the stream stops.
//
// Build: see build.sh (static aarch64/musl binary; MPP and libdrm linked in).

#define _GNU_SOURCE
#include <arpa/inet.h>
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <getopt.h>
#include <math.h>
#include <netdb.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <pthread.h>
#include <signal.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/eventfd.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#include <drm_fourcc.h>
#include <xf86drm.h>
#include <xf86drmMode.h>

#include <rockchip/mpp_buffer.h>
#include <rockchip/mpp_frame.h>
#include <rockchip/mpp_packet.h>
#include <rockchip/rk_mpi.h>

#ifndef DRM_FORMAT_NV15
#define DRM_FORMAT_NV15 fourcc_code('N', 'V', '1', '5')
#endif

// ------------------------------------------------------------------------- options

static const char *opt_url = "rtsp://127.0.0.1:8554/live/pyxis";
static const char *opt_card = "/dev/dri/card0";
static bool opt_no_display = false;     // decode only (benchmark)
static bool opt_match_rate = true;      // switch TV refresh to the stream's frame rate
static bool opt_low_latency = false;    // -L: show each frame at the next refresh, no smoothing buffer
static int opt_stats_every = 10;        // seconds between stats lines (0 = off)
static const char *opt_capture = NULL;  // writeback capture of the HDMI output (PPM)
static const char *opt_status = "/tmp/pyxis-hdmi.json";  // live status for the settings page
static int opt_capture_after = 90;      // ... after this many displayed frames

static volatile sig_atomic_t g_stop = 0;
static bool g_debug = false;  // PYXIS_HDMI_DEBUG=1: frame flags and flip timing

// ------------------------------------------------------------------------- helpers

static int64_t now_us(void) {
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return (int64_t)ts.tv_sec * 1000000 + ts.tv_nsec / 1000;
}

static void logf_(const char *fmt, ...) {
	va_list ap;
	va_start(ap, fmt);
	vfprintf(stdout, fmt, ap);  // stdout: procd logs it as daemon.info
	va_end(ap);
	fputc('\n', stdout);
}
#define LOG(...) logf_(__VA_ARGS__)

static void on_signal(int sig) { (void)sig; g_stop = 1; }

// Growable byte buffer.
typedef struct { uint8_t *d; size_t n, cap; } buf_t;
static void buf_reserve(buf_t *b, size_t extra) {
	if (b->n + extra <= b->cap) return;
	size_t c = b->cap ? b->cap : 65536;
	while (c < b->n + extra) c *= 2;
	b->d = realloc(b->d, c);
	if (!b->d) { LOG("out of memory"); exit(1); }
	b->cap = c;
}
static void buf_add(buf_t *b, const void *p, size_t n) { buf_reserve(b, n); memcpy(b->d + b->n, p, n); b->n += n; }
static void buf_startcode(buf_t *b) { static const uint8_t sc[4] = {0, 0, 0, 1}; buf_add(b, sc, 4); }

static int b64_val(int c) {
	if (c >= 'A' && c <= 'Z') return c - 'A';
	if (c >= 'a' && c <= 'z') return c - 'a' + 26;
	if (c >= '0' && c <= '9') return c - '0' + 52;
	if (c == '+' || c == '-') return 62;
	if (c == '/' || c == '_') return 63;
	return -1;
}
// Decodes base64 from s (up to a delimiter) into out; returns bytes written.
static size_t b64_decode(const char *s, size_t len, uint8_t *out, size_t outcap) {
	uint32_t acc = 0; int bits = 0; size_t n = 0;
	for (size_t i = 0; i < len; i++) {
		int v = b64_val((unsigned char)s[i]);
		if (v < 0) continue;  // '=' padding and anything else
		acc = (acc << 6) | (uint32_t)v; bits += 6;
		if (bits >= 8) { bits -= 8; if (n < outcap) out[n++] = (uint8_t)(acc >> bits); }
	}
	return n;
}

// ------------------------------------------------------------------------- RTSP

enum { CODEC_H264 = 0, CODEC_H265 = 1 };

typedef struct {
	int fd;
	char host[128];
	char port[8];
	char url[512];
	int cseq;
	char session[160];
	char base[512];
	char control[512];
	int codec;
	int pt;
	buf_t params;        // Annex-B parameter sets from the SDP
	uint8_t rb[1 << 16]; // receive buffer
	size_t rlen;
	int64_t last_keepalive;
} rtsp_t;

static int parse_url(rtsp_t *r, const char *url) {
	if (strncmp(url, "rtsp://", 7) != 0) return -1;
	snprintf(r->url, sizeof r->url, "%s", url);
	const char *h = url + 7;
	const char *slash = strchr(h, '/');
	size_t hl = slash ? (size_t)(slash - h) : strlen(h);
	char hp[160];
	if (hl >= sizeof hp) return -1;
	memcpy(hp, h, hl); hp[hl] = 0;
	char *colon = strrchr(hp, ':');
	if (colon) { *colon = 0; snprintf(r->port, sizeof r->port, "%s", colon + 1); }
	else snprintf(r->port, sizeof r->port, "554");
	snprintf(r->host, sizeof r->host, "%s", hp);
	return 0;
}

static int rtsp_connect(rtsp_t *r) {
	struct addrinfo hints = {0}, *res = NULL;
	hints.ai_family = AF_UNSPEC;
	hints.ai_socktype = SOCK_STREAM;
	if (getaddrinfo(r->host, r->port, &hints, &res) != 0) return -1;
	int fd = -1;
	for (struct addrinfo *a = res; a; a = a->ai_next) {
		fd = socket(a->ai_family, a->ai_socktype | SOCK_CLOEXEC, a->ai_protocol);
		if (fd < 0) continue;
		if (connect(fd, a->ai_addr, a->ai_addrlen) == 0) break;
		close(fd); fd = -1;
	}
	freeaddrinfo(res);
	if (fd < 0) return -1;
	int one = 1;
	setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
	int rcv = 4 << 20;  // 4 MB: room for 4K keyframes
	setsockopt(fd, SOL_SOCKET, SO_RCVBUF, &rcv, sizeof rcv);
	r->fd = fd;
	r->rlen = 0;
	return 0;
}

// Reads more bytes into the receive buffer. Returns bytes read, 0 on timeout, -1 on close/error.
static ssize_t rtsp_fill(rtsp_t *r, int timeout_ms) {
	if (r->rlen == sizeof r->rb) return -1;  // a single unit larger than the buffer: give up
	struct pollfd p = {r->fd, POLLIN, 0};
	int pr = poll(&p, 1, timeout_ms);
	if (pr == 0) return 0;
	if (pr < 0) return errno == EINTR ? 0 : -1;
	ssize_t n = recv(r->fd, r->rb + r->rlen, sizeof r->rb - r->rlen, 0);
	if (n <= 0) return -1;
	r->rlen += (size_t)n;
	return n;
}
static void rtsp_consume(rtsp_t *r, size_t n) {
	memmove(r->rb, r->rb + n, r->rlen - n);
	r->rlen -= n;
}

static int send_all(int fd, const char *s, size_t n) {
	while (n) {
		ssize_t w = send(fd, s, n, MSG_NOSIGNAL);
		if (w <= 0) { if (errno == EINTR) continue; return -1; }
		s += w; n -= (size_t)w;
	}
	return 0;
}

static int rtsp_send(rtsp_t *r, const char *method, const char *url, const char *extra) {
	char req[2048];
	int n = snprintf(req, sizeof req, "%s %s RTSP/1.0\r\nCSeq: %d\r\nUser-Agent: pyxis-hdmi\r\n%s%s%s%s\r\n",
	                 method, url, ++r->cseq, extra ? extra : "",
	                 r->session[0] ? "Session: " : "", r->session, r->session[0] ? "\r\n" : "");
	if (n <= 0 || (size_t)n >= sizeof req) return -1;
	return send_all(r->fd, req, (size_t)n);
}

// Finds header `name` in a response header block; copies its value.
static bool hdr_get(const char *hdrs, const char *name, char *out, size_t outcap) {
	size_t nl = strlen(name);
	for (const char *p = hdrs; p && *p; ) {
		const char *eol = strstr(p, "\r\n");
		if (!eol) break;
		if ((size_t)(eol - p) > nl && strncasecmp(p, name, nl) == 0 && p[nl] == ':') {
			const char *v = p + nl + 1;
			while (*v == ' ' || *v == '\t') v++;
			size_t vl = (size_t)(eol - v);
			if (vl >= outcap) vl = outcap - 1;
			memcpy(out, v, vl); out[vl] = 0;
			return true;
		}
		p = eol + 2;
	}
	return false;
}

// Reads one RTSP response (skipping any interleaved binary data before it).
// Returns the status code, or -1. Header block and body are returned in malloc'd strings.
static int rtsp_read_response(rtsp_t *r, char **hdrs_out, char **body_out, int timeout_ms) {
	int64_t deadline = now_us() + (int64_t)timeout_ms * 1000;
	for (;;) {
		// Skip interleaved RTP frames that may arrive before the response.
		while (r->rlen >= 4 && r->rb[0] == '$') {
			size_t len = ((size_t)r->rb[2] << 8) | r->rb[3];
			if (r->rlen < 4 + len) break;
			rtsp_consume(r, 4 + len);
		}
		if (r->rlen >= 4 && r->rb[0] != '$') {
			uint8_t *end = memmem(r->rb, r->rlen, "\r\n\r\n", 4);
			if (end) {
				size_t hlen = (size_t)(end - r->rb) + 4;
				char *h = strndup((char *)r->rb, hlen);
				char cl[32] = "0";
				hdr_get(h, "Content-Length", cl, sizeof cl);
				size_t blen = (size_t)strtoul(cl, NULL, 10);
				if (hlen + blen > sizeof r->rb) { free(h); return -1; }
				if (r->rlen >= hlen + blen) {
					int code = -1;
					if (strncmp(h, "RTSP/1.0 ", 9) == 0) code = atoi(h + 9);
					char *b = strndup((char *)r->rb + hlen, blen);
					rtsp_consume(r, hlen + blen);
					if (hdrs_out) *hdrs_out = h; else free(h);
					if (body_out) *body_out = b; else free(b);
					return code;
				}
				free(h);
			}
		}
		int left = (int)((deadline - now_us()) / 1000);
		if (left <= 0) return -1;
		if (rtsp_fill(r, left) < 0) return -1;
	}
}

static void add_param_set(rtsp_t *r, const char *b64, size_t len) {
	uint8_t tmp[1024];
	size_t n = b64_decode(b64, len, tmp, sizeof tmp);
	if (n) { buf_startcode(&r->params); buf_add(&r->params, tmp, n); }
}

// Parses the SDP: video codec, payload type, control URL and parameter sets.
static int parse_sdp(rtsp_t *r, const char *sdp) {
	bool in_video = false, found = false;
	char control[512] = "";
	r->params.n = 0;
	r->pt = -1;
	for (const char *p = sdp; *p; ) {
		const char *eol = p + strcspn(p, "\r\n");
		size_t ll = (size_t)(eol - p);
		char line[1024];
		if (ll >= sizeof line) ll = sizeof line - 1;
		memcpy(line, p, ll); line[ll] = 0;
		p = eol; while (*p == '\r' || *p == '\n') p++;

		if (strncmp(line, "m=", 2) == 0) {
			if (found && in_video) break;  // finished the first video section
			in_video = strncmp(line, "m=video", 7) == 0;
			if (in_video) {
				// m=video <port> <proto> <pt> ...
				char *s = line;
				for (int i = 0; i < 3 && s; i++) { s = strchr(s, ' '); if (s) s++; }
				r->pt = s ? atoi(s) : -1;
			}
			continue;
		}
		if (!in_video) continue;
		char codec[32];
		int pt;
		if (sscanf(line, "a=rtpmap:%d %31[^/]", &pt, codec) == 2 && pt == r->pt) {
			if (!strcasecmp(codec, "H264")) { r->codec = CODEC_H264; found = true; }
			else if (!strcasecmp(codec, "H265") || !strcasecmp(codec, "HEVC")) { r->codec = CODEC_H265; found = true; }
		} else if (strncmp(line, "a=control:", 10) == 0) {
			snprintf(control, sizeof control, "%s", line + 10);
		} else if (strncmp(line, "a=fmtp:", 7) == 0) {
			const char *keys[] = {"sprop-vps=", "sprop-sps=", "sprop-pps=", "sprop-parameter-sets="};
			for (int k = 0; k < 4; k++) {
				const char *v = strstr(line, keys[k]);
				if (!v) continue;
				v += strlen(keys[k]);
				size_t vl = strcspn(v, ";");
				// sprop-parameter-sets is a comma-separated list
				const char *q = v, *qe = v + vl;
				while (q < qe) {
					const char *c = memchr(q, ',', (size_t)(qe - q));
					if (!c) c = qe;
					add_param_set(r, q, (size_t)(c - q));
					q = c + 1;
				}
			}
		}
	}
	if (!found) return -1;
	if (strncmp(control, "rtsp://", 7) == 0) snprintf(r->control, sizeof r->control, "%s", control);
	else if (control[0] && strcmp(control, "*") != 0) {
		size_t bl = strlen(r->base);
		snprintf(r->control, sizeof r->control, "%s%s%s", r->base, (bl && r->base[bl - 1] == '/') ? "" : "/", control);
	} else snprintf(r->control, sizeof r->control, "%s", r->base);
	return 0;
}

// DESCRIBE + SETUP + PLAY. Returns 0, or the RTSP status (e.g. 404 when the stream is offline), or -1.
static int rtsp_open(rtsp_t *r) {
	char *h = NULL, *body = NULL;
	r->session[0] = 0;
	if (rtsp_connect(r) < 0) return -1;
	if (rtsp_send(r, "DESCRIBE", r->url, "Accept: application/sdp\r\n") < 0) return -1;
	int code = rtsp_read_response(r, &h, &body, 3000);
	if (code != 200) { free(h); free(body); return code > 0 ? code : -1; }
	if (!hdr_get(h, "Content-Base", r->base, sizeof r->base)) snprintf(r->base, sizeof r->base, "%s", r->url);
	int ok = parse_sdp(r, body);
	free(h); free(body); h = body = NULL;
	if (ok < 0) { LOG("stream has no H.264/H.265 video"); return -1; }

	if (rtsp_send(r, "SETUP", r->control, "Transport: RTP/AVP/TCP;unicast;interleaved=0-1\r\n") < 0) return -1;
	code = rtsp_read_response(r, &h, NULL, 3000);
	if (code != 200) { free(h); return code > 0 ? code : -1; }
	char sess[200];
	if (hdr_get(h, "Session", sess, sizeof sess)) {
		sess[strcspn(sess, ";")] = 0;
		snprintf(r->session, sizeof r->session, "%s", sess);
	}
	free(h); h = NULL;

	if (rtsp_send(r, "PLAY", r->base, "Range: npt=0.000-\r\n") < 0) return -1;
	code = rtsp_read_response(r, NULL, NULL, 3000);
	if (code != 200) return code > 0 ? code : -1;
	r->last_keepalive = now_us();
	return 0;
}

static void rtsp_close(rtsp_t *r) {
	if (r->fd >= 0) {
		if (r->session[0]) rtsp_send(r, "TEARDOWN", r->base, NULL);
		close(r->fd);
	}
	r->fd = -1;
}

// ------------------------------------------------------------------------- RTP -> access units

typedef struct {
	int codec;
	buf_t au;
	uint32_t ts;
	bool have_ts;
	bool corrupt;
	bool key;
	bool has_params;
	bool fu_open;
	uint16_t last_seq;
	bool have_seq;
	int64_t first_arrival;
	bool waiting_for_key;
	// frame-rate estimate from RTP timestamps (90 kHz): the mean of the last 128 frame
	// intervals. RTMP timestamps are whole milliseconds, so single intervals jitter
	// (41/42 ms at 24 fps); the mean over 128 frames is accurate to ~0.02%.
	uint32_t prev_ts;
	bool have_prev_ts;
	uint32_t deltas[128];
	int ndeltas, dhead;
	uint64_t dsum;
	// stream clock: RTP timestamps unwrapped past the 32-bit rollover, in microseconds
	int64_t ts64;
	int64_t au_stream_us;
	// counters (stats line)
	uint64_t au_out, au_dropped, seq_gaps, rtp_pkts;
} depay_t;

// arrival_us: local time the picture's first packet arrived; stream_us: its RTP timestamp
typedef void (*au_cb)(void *ctx, const uint8_t *d, size_t n, int64_t arrival_us, int64_t stream_us, bool key);

static bool nal_is_key(int codec, const uint8_t *nal) {
	if (codec == CODEC_H264) return (nal[0] & 0x1f) == 5;
	int t = (nal[0] >> 1) & 0x3f;
	return t >= 16 && t <= 21;
}
static bool nal_is_param(int codec, const uint8_t *nal) {
	if (codec == CODEC_H264) { int t = nal[0] & 0x1f; return t == 7 || t == 8; }
	int t = (nal[0] >> 1) & 0x3f;
	return t >= 32 && t <= 34;
}

static void depay_note_nal(depay_t *d, const uint8_t *nal) {
	if (nal_is_key(d->codec, nal)) d->key = true;
	if (nal_is_param(d->codec, nal)) d->has_params = true;
}

static void depay_reset_au(depay_t *d) {
	d->au.n = 0; d->corrupt = false; d->key = false; d->has_params = false; d->fu_open = false; d->have_ts = false;
}

static void depay_emit(depay_t *d, const buf_t *params, au_cb cb, void *ctx) {
	if (d->au.n == 0) { depay_reset_au(d); return; }
	if (d->corrupt) {
		d->waiting_for_key = true;  // never show a damaged picture; resume at the next keyframe
		d->au_dropped++;
	} else if (d->waiting_for_key && !d->key) {
		d->au_dropped++;  // drop until a keyframe arrives
	} else {
		d->au_out++;
		if (d->key) d->waiting_for_key = false;
		if (d->key && !d->has_params && params->n) {
			buf_t tmp = {0};
			buf_add(&tmp, params->d, params->n);
			buf_add(&tmp, d->au.d, d->au.n);
			cb(ctx, tmp.d, tmp.n, d->first_arrival, d->au_stream_us, true);
			free(tmp.d);
		} else {
			cb(ctx, d->au.d, d->au.n, d->first_arrival, d->au_stream_us, d->key);
		}
	}
	depay_reset_au(d);
}

// Returns 0 until there are enough frames for a reliable estimate (~4 s).
static double depay_fps(depay_t *d) {
	if (d->ndeltas < 96 || d->dsum == 0) return 0;
	return 90000.0 * d->ndeltas / (double)d->dsum;
}

static void depay_rtp(depay_t *d, const uint8_t *p, size_t n, const buf_t *params, au_cb cb, void *ctx) {
	if (n < 12 || (p[0] >> 6) != 2) return;
	bool marker = p[1] & 0x80;
	uint16_t seq = (uint16_t)((p[2] << 8) | p[3]);
	uint32_t ts = ((uint32_t)p[4] << 24) | ((uint32_t)p[5] << 16) | ((uint32_t)p[6] << 8) | p[7];
	size_t off = 12 + 4u * (p[0] & 0x0f);
	if (p[0] & 0x10) {  // header extension
		if (n < off + 4) return;
		off += 4 + 4u * ((p[off + 2] << 8) | p[off + 3]);
	}
	size_t end = n;
	if (p[0] & 0x20) { if (n == 0 || p[n - 1] > n) return; end -= p[n - 1]; }  // padding
	if (off >= end) return;
	const uint8_t *pl = p + off;
	size_t pn = end - off;

	d->rtp_pkts++;
	if (d->have_seq && (uint16_t)(d->last_seq + 1) != seq) { d->corrupt = true; d->seq_gaps++; }  // lost packet(s)
	d->last_seq = seq; d->have_seq = true;

	if (d->have_ts && ts != d->ts) depay_emit(d, params, cb, ctx);  // missed marker: new picture
	if (!d->have_ts) {
		d->ts = ts; d->have_ts = true; d->first_arrival = now_us();
		if (d->have_prev_ts) {
			uint32_t dt = ts - d->prev_ts;
			d->ts64 += (int32_t)dt;
			if (dt > 0 && dt < 90000) {
				if (d->ndeltas == 128) d->dsum -= d->deltas[d->dhead]; else d->ndeltas++;
				d->deltas[d->dhead] = dt;
				d->dsum += dt;
				d->dhead = (d->dhead + 1) % 128;
			}
		}
		d->prev_ts = ts; d->have_prev_ts = true;
		d->au_stream_us = d->ts64 * 100 / 9;  // 90 kHz -> us
	}

	if (d->codec == CODEC_H264) {
		int t = pl[0] & 0x1f;
		if (t >= 1 && t <= 23) {
			buf_startcode(&d->au); buf_add(&d->au, pl, pn); depay_note_nal(d, pl);
		} else if (t == 24) {  // STAP-A
			size_t i = 1;
			while (i + 2 <= pn) {
				size_t sz = ((size_t)pl[i] << 8) | pl[i + 1];
				i += 2;
				if (sz == 0 || i + sz > pn) { d->corrupt = true; break; }
				buf_startcode(&d->au); buf_add(&d->au, pl + i, sz); depay_note_nal(d, pl + i);
				i += sz;
			}
		} else if (t == 28) {  // FU-A
			if (pn < 2) return;
			uint8_t hdr = (uint8_t)((pl[0] & 0xe0) | (pl[1] & 0x1f));
			if (pl[1] & 0x80) {
				buf_startcode(&d->au); buf_add(&d->au, &hdr, 1); depay_note_nal(d, &hdr);
				d->fu_open = true;
			} else if (!d->fu_open) { d->corrupt = true; return; }
			buf_add(&d->au, pl + 2, pn - 2);
			if (pl[1] & 0x40) d->fu_open = false;
		}
	} else {
		if (pn < 2) return;
		int t = (pl[0] >> 1) & 0x3f;
		if (t < 48) {
			buf_startcode(&d->au); buf_add(&d->au, pl, pn); depay_note_nal(d, pl);
		} else if (t == 48) {  // aggregation packet
			size_t i = 2;
			while (i + 2 <= pn) {
				size_t sz = ((size_t)pl[i] << 8) | pl[i + 1];
				i += 2;
				if (sz < 2 || i + sz > pn) { d->corrupt = true; break; }
				buf_startcode(&d->au); buf_add(&d->au, pl + i, sz); depay_note_nal(d, pl + i);
				i += sz;
			}
		} else if (t == 49) {  // fragmentation unit
			if (pn < 3) return;
			uint8_t fu = pl[2];
			uint8_t hdr[2] = {(uint8_t)((pl[0] & 0x81) | ((fu & 0x3f) << 1)), pl[1]};
			if (fu & 0x80) {
				buf_startcode(&d->au); buf_add(&d->au, hdr, 2); depay_note_nal(d, hdr);
				d->fu_open = true;
			} else if (!d->fu_open) { d->corrupt = true; return; }
			buf_add(&d->au, pl + 3, pn - 3);
			if (fu & 0x40) d->fu_open = false;
		}
	}
	if (marker) depay_emit(d, params, cb, ctx);
}

// ------------------------------------------------------------------------- display (DRM/KMS)

// One KMS framebuffer per decoder buffer, keyed by the buffer itself and its dmabuf fd.
// (Not by mpp_buffer_get_index: it returns -1 for every buffer, which once mapped every
// frame onto the first framebuffer.)
typedef struct { uint32_t fb; uint32_t handle; MppBuffer buf; int dmafd; uint32_t w, h, fmt; } fbslot_t;

// Frame pacing. Each frame is shown at the first refresh at or after its due time, which
// follows the stream's own timestamps, so 24p on a 60 Hz screen gets an even 2-3-2-3
// cadence instead of whatever pattern network jitter produces.
#define PACE_QUEUE 8
#define PACE_WINDOW 72           // frames of arrival history (3 s at 24p)
#define PACE_LEAD_US 3000        // a frame is chosen this long before its refresh
#define PACE_MAX_JITTER_US 100000 // later than this is a stall, not jitter: show late frames as they come

typedef struct {
	int fd;
	bool atomic;
	uint32_t conn_id, crtc_id, plane_id, wb_conn_id;
	int crtc_index;
	bool connected;
	bool active;            // mode set and CRTC on
	drmModeModeInfo mode;
	uint32_t mode_blob;
	double stream_fps;      // what the current mode was chosen for
	// property ids
	uint32_t p_conn_crtc, p_crtc_active, p_crtc_mode;
	uint32_t p_fb, p_crtc, p_sx, p_sy, p_sw, p_sh, p_cx, p_cy, p_cw, p_ch;
	uint32_t p_wb_fb, p_wb_fence, p_wb_crtc;
	uint32_t p_color_enc, p_color_range;
	int64_t enc_val[3], range_val[2];  // enum values: BT.601/709/2020, limited/full (-1: absent)
	int64_t color_enc, color_range;    // values on the plane now (-1: unknown)
	fbslot_t slots[64];
	int nslots;
	// frames: on screen, flip in flight
	MppFrame front, pending;
	bool flip_pending;
	bool plane_on;
	int64_t last_frame_us;
	// frames waiting for their refresh (oldest first), with the time each is due
	struct { MppFrame f; int64_t due_us; } q[PACE_QUEUE];
	int nq;
	// vblank grid: time of a known vblank (from flip events) and the refresh period
	int64_t vbl_us;
	double period_us;
	int64_t decided_vbl_us;  // last vblank a frame was chosen for
	// pacing clock (see pace_due)
	bool clk_have;
	int64_t clk_raw_us, clk_st_us;
	int64_t lag[PACE_WINDOW];
	int nlag, lag_head;
	int64_t lag_off;
	bool have_off;
	// stats
	uint64_t shown, dropped, lat_sum_us, lat_n;
	uint64_t win_shown, win_lat_sum_us, win_lat_n;  // 1 s window for the status file
	// flip timing (debug)
	int64_t commit_us;
	int64_t last_vbl_us;
	int64_t dbg_c2e_min, dbg_c2e_max, dbg_c2e_sum, dbg_n;
	uint64_t dbg_holds[5];  // refreshes each frame stayed on screen: 1, 2, 3, 4, 5+
	// writeback capture
	bool capture_done;
	int captures;  // taken so far (PYXIS_HDMI_CAPTURES=N takes N, a few frames apart)
	uint64_t frames_since_capture;
} disp_t;

static uint32_t prop_id(int fd, uint32_t obj, uint32_t type, const char *name) {
	drmModeObjectProperties *props = drmModeObjectGetProperties(fd, obj, type);
	uint32_t id = 0;
	for (uint32_t i = 0; props && i < props->count_props && !id; i++) {
		drmModePropertyRes *p = drmModeGetProperty(fd, props->props[i]);
		if (p && !strcmp(p->name, name)) id = p->prop_id;
		drmModeFreeProperty(p);
	}
	drmModeFreeObjectProperties(props);
	return id;
}
static bool prop_str(int fd, uint32_t obj, uint32_t type, const char *name, char *out, size_t cap) {
	// Rockchip exposes plane names (e.g. "Esmart0-win0") as an enum/blob/string depending on kernel;
	// we read the plane's "NAME" property if present as an enum value name.
	drmModeObjectProperties *props = drmModeObjectGetProperties(fd, obj, type);
	bool ok = false;
	for (uint32_t i = 0; props && i < props->count_props && !ok; i++) {
		drmModePropertyRes *p = drmModeGetProperty(fd, props->props[i]);
		if (p && !strcmp(p->name, name) && (p->flags & DRM_MODE_PROP_ENUM)) {
			for (int e = 0; e < p->count_enums; e++)
				if (p->enums[e].value == props->prop_values[i]) { snprintf(out, cap, "%s", p->enums[e].name); ok = true; }
		}
		drmModeFreeProperty(p);
	}
	drmModeFreeObjectProperties(props);
	return ok;
}
// Value of the enum entry `entry` of property `name`, or -1.
static int64_t prop_enum(int fd, uint32_t obj, uint32_t type, const char *name, const char *entry) {
	drmModeObjectProperties *props = drmModeObjectGetProperties(fd, obj, type);
	int64_t v = -1;
	for (uint32_t i = 0; props && i < props->count_props && v < 0; i++) {
		drmModePropertyRes *p = drmModeGetProperty(fd, props->props[i]);
		if (p && !strcmp(p->name, name) && (p->flags & DRM_MODE_PROP_ENUM))
			for (int e = 0; e < p->count_enums; e++)
				if (!strcmp(p->enums[e].name, entry)) v = (int64_t)p->enums[e].value;
		drmModeFreeProperty(p);
	}
	drmModeFreeObjectProperties(props);
	return v;
}

static void release_frame(MppFrame *f) { if (*f) { mpp_frame_deinit(f); *f = NULL; } }

// The kernel shows the console's framebuffer (/dev/fb0) whenever no program drives the
// display. The service unbinds the text console, but the buffer keeps whatever was drawn
// last; blank it so the screen is black, not frozen console text.
static void blank_fbdev(void) {
	int fd = open("/dev/fb0", O_WRONLY | O_CLOEXEC);
	if (fd < 0) return;
	static const uint8_t zeros[65536];
	while (write(fd, zeros, sizeof zeros) > 0) {}
	close(fd);
}

static void disp_clear_slots(disp_t *d) {
	for (int i = 0; i < d->nslots; i++) {
		drmModeRmFB(d->fd, d->slots[i].fb);
		struct drm_gem_close gc = {.handle = d->slots[i].handle};
		drmIoctl(d->fd, DRM_IOCTL_GEM_CLOSE, &gc);
	}
	d->nslots = 0;
}

// Finds or creates a KMS framebuffer for a decoded frame's dmabuf.
static uint32_t disp_fb_for(disp_t *d, MppFrame f) {
	MppBuffer b = mpp_frame_get_buffer(f);
	if (!b) return 0;
	int dmafd = mpp_buffer_get_fd(b);
	uint32_t w = mpp_frame_get_width(f), h = mpp_frame_get_height(f);
	MppFrameFormat mf = mpp_frame_get_fmt(f) & MPP_FRAME_FMT_MASK;
	uint32_t fmt = (mf == MPP_FMT_YUV420SP_10BIT) ? DRM_FORMAT_NV15 : DRM_FORMAT_NV12;
	for (int i = 0; i < d->nslots; i++)
		if (d->slots[i].buf == b && d->slots[i].dmafd == dmafd && d->slots[i].w == w && d->slots[i].h == h && d->slots[i].fmt == fmt)
			return d->slots[i].fb;
	uint32_t handle = 0;
	if (drmPrimeFDToHandle(d->fd, dmafd, &handle)) { LOG("PRIME import failed: %s", strerror(errno)); return 0; }
	uint32_t hs = mpp_frame_get_hor_stride(f), vs = mpp_frame_get_ver_stride(f);
	uint32_t handles[4] = {handle, handle}, pitches[4] = {hs, hs}, offsets[4] = {0, hs * vs};
	uint32_t fb = 0;
	if (drmModeAddFB2(d->fd, w, h, fmt, handles, pitches, offsets, &fb, 0)) {
		LOG("AddFB2 %ux%u %.4s failed: %s", w, h, (char *)&fmt, strerror(errno));
		return 0;
	}
	if (d->nslots == 64) disp_clear_slots(d);
	d->slots[d->nslots++] = (fbslot_t){fb, handle, b, dmafd, w, h, fmt};
	return fb;
}

// Chooses the output mode: the screen's preferred resolution, at a refresh rate that is an
// exact multiple of the stream's frame rate, so every frame stays up equally long. A rate of
// 48 Hz or more is preferred (25p -> 50 Hz, 30p -> 60 Hz, 24p -> 48/120 Hz) for the lowest
// delay; failing that the stream's own rate (24p -> 24 Hz), which costs ~25 ms of delay over
// 60 Hz but avoids the 3-2-3-2 stutter of 24p on 60 Hz. Else the preferred mode.
static bool pick_mode(drmModeConnector *c, double fps, drmModeModeInfo *out) {
	if (c->count_modes == 0) return false;
	int pref = 0;
	for (int i = 0; i < c->count_modes; i++) if (c->modes[i].type & DRM_MODE_TYPE_PREFERRED) { pref = i; break; }
	drmModeModeInfo *p = &c->modes[pref];
	*out = *p;
	if (!opt_match_rate || fps < 10) return true;
	int best = -1; double best_score = 1e9;
	for (int i = 0; i < c->count_modes; i++) {
		drmModeModeInfo *m = &c->modes[i];
		if (m->hdisplay != p->hdisplay || m->vdisplay != p->vdisplay || (m->flags & DRM_MODE_FLAG_INTERLACE)) continue;
		double hz = (double)m->clock * 1000.0 / ((double)m->htotal * m->vtotal);
		if (hz < (opt_low_latency ? 47.9 : 23.0)) continue;  // low latency: never a slow refresh
		for (int mult = 1; mult <= 5; mult++) {
			double err = fabs(hz - fps * mult) / (fps * mult);
			if (err < 0.0005) {  // tight enough that 23.976 vs 24 (0.1%) don't match each other
				// lowest multiple that reaches 48 Hz first; below 48 Hz only as a fallback
				double score = (hz < 47.9 ? 100 : 0) + mult * 10 + err;
				if (score < best_score) { best_score = score; best = i; }
			}
		}
	}
	if (best >= 0) *out = c->modes[best];
	return true;
}

static int disp_init(disp_t *d) {
	memset(d, 0, sizeof *d);
	d->fd = open(opt_card, O_RDWR | O_CLOEXEC);
	if (d->fd < 0) { LOG("can't open %s: %s", opt_card, strerror(errno)); return -1; }
	drmSetClientCap(d->fd, DRM_CLIENT_CAP_UNIVERSAL_PLANES, 1);
	if (drmSetClientCap(d->fd, DRM_CLIENT_CAP_ATOMIC, 1)) { LOG("display driver lacks atomic modesetting"); return -1; }
	drmSetClientCap(d->fd, DRM_CLIENT_CAP_WRITEBACK_CONNECTORS, 1);
	drmModeRes *res = drmModeGetResources(d->fd);
	if (!res) { LOG("no display resources"); return -1; }
	for (int i = 0; i < res->count_connectors; i++) {
		drmModeConnector *c = drmModeGetConnectorCurrent(d->fd, res->connectors[i]);
		if (!c) continue;
		if (c->connector_type == DRM_MODE_CONNECTOR_HDMIA && !d->conn_id) d->conn_id = c->connector_id;
		if (c->connector_type == DRM_MODE_CONNECTOR_WRITEBACK && !d->wb_conn_id) d->wb_conn_id = c->connector_id;
		drmModeFreeConnector(c);
	}
	if (!d->conn_id) { LOG("no HDMI connector"); drmModeFreeResources(res); return -1; }
	// CRTC: one the connector's encoders can drive
	drmModeConnector *c = drmModeGetConnectorCurrent(d->fd, d->conn_id);
	uint32_t possible = 0;
	for (int i = 0; c && i < c->count_encoders; i++) {
		drmModeEncoder *e = drmModeGetEncoder(d->fd, c->encoders[i]);
		if (e) { possible |= e->possible_crtcs; drmModeFreeEncoder(e); }
	}
	drmModeFreeConnector(c);
	for (int i = 0; i < res->count_crtcs; i++)
		if (possible & (1u << i)) { d->crtc_id = res->crtcs[i]; d->crtc_index = i; break; }
	drmModeFreeResources(res);
	if (!d->crtc_id) { LOG("no display controller for HDMI"); return -1; }

	// Plane: NV12-capable and scalable. On the RK3568 the "Esmart" windows scale and take
	// NV12; "Smart" windows don't scale, so they're the last resort.
	drmModePlaneRes *pr = drmModeGetPlaneResources(d->fd);
	int best_rank = -1;
	for (uint32_t i = 0; pr && i < pr->count_planes; i++) {
		drmModePlane *p = drmModeGetPlane(d->fd, pr->planes[i]);
		if (!p) continue;
		bool nv12 = false;
		for (uint32_t f = 0; f < p->count_formats; f++) if (p->formats[f] == DRM_FORMAT_NV12) nv12 = true;
		if (nv12 && (p->possible_crtcs & (1u << d->crtc_index))) {
			char name[64] = "";
			prop_str(d->fd, p->plane_id, DRM_MODE_OBJECT_PLANE, "NAME", name, sizeof name);
			int rank = 1;
			if (!strncasecmp(name, "Esmart", 6)) rank = 3;
			else if (!strncasecmp(name, "Cluster", 7)) rank = 2;
			else if (!strncasecmp(name, "Smart", 5)) rank = 0;
			if (rank > best_rank) { best_rank = rank; d->plane_id = p->plane_id; LOG("candidate plane %u %s (rank %d)", p->plane_id, name[0] ? name : "?", rank); }
		}
		drmModeFreePlane(p);
	}
	drmModeFreePlaneResources(pr);
	if (!d->plane_id) { LOG("no NV12 plane for the HDMI display controller"); return -1; }

	d->p_conn_crtc = prop_id(d->fd, d->conn_id, DRM_MODE_OBJECT_CONNECTOR, "CRTC_ID");
	d->p_crtc_active = prop_id(d->fd, d->crtc_id, DRM_MODE_OBJECT_CRTC, "ACTIVE");
	d->p_crtc_mode = prop_id(d->fd, d->crtc_id, DRM_MODE_OBJECT_CRTC, "MODE_ID");
	const struct { uint32_t *dst; const char *n; } pp[] = {
		{&d->p_fb, "FB_ID"}, {&d->p_crtc, "CRTC_ID"}, {&d->p_sx, "SRC_X"}, {&d->p_sy, "SRC_Y"}, {&d->p_sw, "SRC_W"},
		{&d->p_sh, "SRC_H"}, {&d->p_cx, "CRTC_X"}, {&d->p_cy, "CRTC_Y"}, {&d->p_cw, "CRTC_W"}, {&d->p_ch, "CRTC_H"}};
	for (size_t i = 0; i < sizeof pp / sizeof pp[0]; i++) *pp[i].dst = prop_id(d->fd, d->plane_id, DRM_MODE_OBJECT_PLANE, pp[i].n);
	d->p_color_enc = prop_id(d->fd, d->plane_id, DRM_MODE_OBJECT_PLANE, "COLOR_ENCODING");
	d->p_color_range = prop_id(d->fd, d->plane_id, DRM_MODE_OBJECT_PLANE, "COLOR_RANGE");
	static const char *enc_names[3] = {"ITU-R BT.601 YCbCr", "ITU-R BT.709 YCbCr", "ITU-R BT.2020 YCbCr"};
	static const char *range_names[2] = {"YCbCr limited range", "YCbCr full range"};
	for (int i = 0; i < 3; i++) d->enc_val[i] = prop_enum(d->fd, d->plane_id, DRM_MODE_OBJECT_PLANE, "COLOR_ENCODING", enc_names[i]);
	for (int i = 0; i < 2; i++) d->range_val[i] = prop_enum(d->fd, d->plane_id, DRM_MODE_OBJECT_PLANE, "COLOR_RANGE", range_names[i]);
	d->color_enc = d->color_range = -1;
	if (d->wb_conn_id) {
		d->p_wb_fb = prop_id(d->fd, d->wb_conn_id, DRM_MODE_OBJECT_CONNECTOR, "WRITEBACK_FB_ID");
		d->p_wb_fence = prop_id(d->fd, d->wb_conn_id, DRM_MODE_OBJECT_CONNECTOR, "WRITEBACK_OUT_FENCE_PTR");
		d->p_wb_crtc = prop_id(d->fd, d->wb_conn_id, DRM_MODE_OBJECT_CONNECTOR, "CRTC_ID");
	}
	return 0;
}

// Turns other planes on our CRTC off (e.g. the text console) in the same commit.
static void add_other_planes_off(disp_t *d, drmModeAtomicReq *req) {
	drmModePlaneRes *pr = drmModeGetPlaneResources(d->fd);
	for (uint32_t i = 0; pr && i < pr->count_planes; i++) {
		if (pr->planes[i] == d->plane_id) continue;
		drmModePlane *p = drmModeGetPlane(d->fd, pr->planes[i]);
		if (p && p->crtc_id == d->crtc_id) {
			drmModeAtomicAddProperty(req, p->plane_id, prop_id(d->fd, p->plane_id, DRM_MODE_OBJECT_PLANE, "FB_ID"), 0);
			drmModeAtomicAddProperty(req, p->plane_id, prop_id(d->fd, p->plane_id, DRM_MODE_OBJECT_PLANE, "CRTC_ID"), 0);
		}
		drmModeFreePlane(p);
	}
	drmModeFreePlaneResources(pr);
}

static void disp_release_all(disp_t *d) {
	release_frame(&d->front); release_frame(&d->pending);
	for (int i = 0; i < d->nq; i++) release_frame(&d->q[i].f);
	d->nq = 0;
	d->flip_pending = false;
}

static void disp_plane_off(disp_t *d) {
	if (!d->active || !d->plane_on) return;
	drmModeAtomicReq *req = drmModeAtomicAlloc();
	drmModeAtomicAddProperty(req, d->plane_id, d->p_fb, 0);
	drmModeAtomicAddProperty(req, d->plane_id, d->p_crtc, 0);
	drmModeAtomicCommit(d->fd, req, 0, NULL);  // blocking: plane is off when this returns
	drmModeAtomicFree(req);
	d->plane_on = false;
	disp_release_all(d);
}

static int disp_modeset(disp_t *d, double fps) {
	drmModeConnector *c = drmModeGetConnector(d->fd, d->conn_id);  // full probe: fresh EDID/modes
	if (!c) return -1;
	drmModeModeInfo m;
	bool ok = pick_mode(c, fps, &m);
	drmModeFreeConnector(c);
	if (!ok) { LOG("HDMI: screen reports no modes"); return -1; }
	if (d->mode_blob) drmModeDestroyPropertyBlob(d->fd, d->mode_blob);
	d->mode_blob = 0;
	if (drmModeCreatePropertyBlob(d->fd, &m, sizeof m, &d->mode_blob)) return -1;
	drmModeAtomicReq *req = drmModeAtomicAlloc();
	drmModeAtomicAddProperty(req, d->crtc_id, d->p_crtc_mode, d->mode_blob);
	drmModeAtomicAddProperty(req, d->crtc_id, d->p_crtc_active, 1);
	drmModeAtomicAddProperty(req, d->conn_id, d->p_conn_crtc, d->crtc_id);
	drmModeAtomicAddProperty(req, d->plane_id, d->p_fb, 0);
	drmModeAtomicAddProperty(req, d->plane_id, d->p_crtc, 0);
	add_other_planes_off(d, req);
	int r = drmModeAtomicCommit(d->fd, req, DRM_MODE_ATOMIC_ALLOW_MODESET, NULL);
	drmModeAtomicFree(req);
	if (r) { LOG("HDMI modeset %s failed: %s", m.name, strerror(errno)); return -1; }
	disp_release_all(d);
	d->plane_on = false;
	d->mode = m;
	d->active = true;
	d->stream_fps = fps;
	double hz = (double)m.clock * 1000.0 / ((double)m.htotal * m.vtotal);
	d->period_us = 1e6 / hz;
	d->vbl_us = d->decided_vbl_us = 0;  // learned again from the first flip
	bool matched = false;
	for (int mult = 1; fps >= 10 && mult <= 5; mult++)
		if (fabs(hz - fps * mult) / (fps * mult) < 0.0005) matched = true;
	LOG("HDMI: %ux%u @ %.3f Hz%s", m.hdisplay, m.vdisplay, hz,
	    matched ? " (even cadence with the stream's frame rate)" : fps >= 10 ? " (the screen has no mode that is a multiple of the stream's frame rate)" : "");
	return 0;
}

static void disp_off(disp_t *d) {
	if (!d->active) return;
	drmModeAtomicReq *req = drmModeAtomicAlloc();
	drmModeAtomicAddProperty(req, d->plane_id, d->p_fb, 0);
	drmModeAtomicAddProperty(req, d->plane_id, d->p_crtc, 0);
	drmModeAtomicAddProperty(req, d->conn_id, d->p_conn_crtc, 0);
	drmModeAtomicAddProperty(req, d->crtc_id, d->p_crtc_active, 0);
	drmModeAtomicAddProperty(req, d->crtc_id, d->p_crtc_mode, 0);
	drmModeAtomicCommit(d->fd, req, DRM_MODE_ATOMIC_ALLOW_MODESET, NULL);
	drmModeAtomicFree(req);
	d->active = false;
	d->plane_on = false;
	d->vbl_us = d->decided_vbl_us = 0;
	disp_release_all(d);
}

static void disp_capture(disp_t *d);

// Starts a vsync'd flip to frame f (takes ownership on success).
static bool disp_flip(disp_t *d, MppFrame f) {
	uint32_t fb = disp_fb_for(d, f);
	if (!fb) return false;
	uint32_t sw = mpp_frame_get_width(f), sh = mpp_frame_get_height(f);
	uint32_t mw = d->mode.hdisplay, mh = d->mode.vdisplay;
	// Fit inside the screen, keeping the aspect ratio (letterbox / pillarbox).
	uint32_t dw = mw, dh = (uint32_t)((uint64_t)sh * mw / sw);
	if (dh > mh) { dh = mh; dw = (uint32_t)((uint64_t)sw * mh / sh); }
	dw &= ~1u; dh &= ~1u;
	uint32_t dx = (mw - dw) / 2, dy = (mh - dh) / 2;
	drmModeAtomicReq *req = drmModeAtomicAlloc();
	drmModeAtomicAddProperty(req, d->plane_id, d->p_fb, fb);
	drmModeAtomicAddProperty(req, d->plane_id, d->p_crtc, d->crtc_id);
	drmModeAtomicAddProperty(req, d->plane_id, d->p_sx, 0);
	drmModeAtomicAddProperty(req, d->plane_id, d->p_sy, 0);
	drmModeAtomicAddProperty(req, d->plane_id, d->p_sw, (uint64_t)sw << 16);
	drmModeAtomicAddProperty(req, d->plane_id, d->p_sh, (uint64_t)sh << 16);
	drmModeAtomicAddProperty(req, d->plane_id, d->p_cx, dx);
	drmModeAtomicAddProperty(req, d->plane_id, d->p_cy, dy);
	drmModeAtomicAddProperty(req, d->plane_id, d->p_cw, dw);
	drmModeAtomicAddProperty(req, d->plane_id, d->p_ch, dh);
	// YUV -> RGB matrix and range. Untagged streams follow the usual convention: BT.709 for
	// HD, BT.601 for SD (the PYXIS doesn't tag its stream; it's HD, so BT.709).
	MppFrameColorSpace cs = mpp_frame_get_colorspace(f);
	int enc = cs == MPP_FRAME_SPC_BT709 ? 1
	        : (cs == MPP_FRAME_SPC_BT470BG || cs == MPP_FRAME_SPC_SMPTE170M) ? 0
	        : (cs == MPP_FRAME_SPC_BT2020_NCL || cs == MPP_FRAME_SPC_BT2020_CL) ? 2
	        : sh > 576 ? 1 : 0;
	int64_t enc_v = d->enc_val[enc];
	int64_t range_v = d->range_val[mpp_frame_get_color_range(f) == MPP_FRAME_RANGE_JPEG ? 1 : 0];
	if (d->p_color_enc && enc_v >= 0 && enc_v != d->color_enc) drmModeAtomicAddProperty(req, d->plane_id, d->p_color_enc, (uint64_t)enc_v);
	if (d->p_color_range && range_v >= 0 && range_v != d->color_range) drmModeAtomicAddProperty(req, d->plane_id, d->p_color_range, (uint64_t)range_v);
	int r = drmModeAtomicCommit(d->fd, req, DRM_MODE_ATOMIC_NONBLOCK | DRM_MODE_PAGE_FLIP_EVENT, d);
	drmModeAtomicFree(req);
	if (r) {
		static int64_t last_log;
		if (now_us() - last_log > 5000000) { LOG("page flip failed: %s", strerror(errno)); last_log = now_us(); }
		return false;
	}
	if (enc_v >= 0) d->color_enc = enc_v;
	if (range_v >= 0) d->color_range = range_v;
	d->pending = f;
	d->flip_pending = true;
	d->plane_on = true;
	d->commit_us = now_us();
	return true;
}

static void on_flip(int fd, unsigned seq, unsigned sec, unsigned usec, unsigned crtc, void *user) {
	(void)fd; (void)seq; (void)sec; (void)usec; (void)crtc;
	disp_t *d = user;
	int64_t t = now_us();
	int64_t vbl = (int64_t)sec * 1000000 + usec;  // the refresh this flip landed on (CLOCK_MONOTONIC)
	if (vbl > 0 && vbl <= t) d->vbl_us = vbl;
	if (g_debug) {
		int64_t c2e = t - d->commit_us;  // commit -> "flip done" event
		if (!d->dbg_n) d->dbg_c2e_min = d->dbg_c2e_max = c2e;
		if (c2e < d->dbg_c2e_min) d->dbg_c2e_min = c2e;
		if (c2e > d->dbg_c2e_max) d->dbg_c2e_max = c2e;
		d->dbg_c2e_sum += c2e; d->dbg_n++;
		if (d->last_vbl_us && d->period_us > 0) {
			long holds = lround((vbl - d->last_vbl_us) / d->period_us);  // refreshes the previous frame stayed up
			if (holds >= 1) d->dbg_holds[holds > 5 ? 4 : holds - 1]++;
		}
		d->last_vbl_us = vbl;
	}
	if (d->pending) {
		int64_t arrival = mpp_frame_get_pts(d->pending);
		if (arrival > 0 && t > arrival) {
			d->lat_sum_us += (uint64_t)(t - arrival); d->lat_n++;
			d->win_lat_sum_us += (uint64_t)(t - arrival); d->win_lat_n++;
		}
	}
	d->win_shown++;
	release_frame(&d->front);
	d->front = d->pending;
	d->pending = NULL;
	d->flip_pending = false;
	d->shown++;
	d->frames_since_capture++;
}

// ------------------------------------------------------------------------- writeback capture (testing)

// Pixel formats the writeback unit accepts (WRITEBACK_PIXEL_FORMATS blob).
static int wb_formats(disp_t *d, uint32_t *out, int cap) {
	drmModeObjectProperties *props = drmModeObjectGetProperties(d->fd, d->wb_conn_id, DRM_MODE_OBJECT_CONNECTOR);
	int n = 0;
	for (uint32_t i = 0; props && i < props->count_props; i++) {
		drmModePropertyRes *p = drmModeGetProperty(d->fd, props->props[i]);
		if (p && !strcmp(p->name, "WRITEBACK_PIXEL_FORMATS")) {
			drmModePropertyBlobRes *b = drmModeGetPropertyBlob(d->fd, (uint32_t)props->prop_values[i]);
			if (b) {
				for (uint32_t k = 0; k < b->length / 4 && n < cap; k++) out[n++] = ((uint32_t *)b->data)[k];
				drmModeFreePropertyBlob(b);
			}
		}
		drmModeFreeProperty(p);
	}
	drmModeFreeObjectProperties(props);
	return n;
}

static void disp_capture(disp_t *d) {
	if (!d->wb_conn_id || !d->p_wb_fb || !d->front) { LOG("capture: no writeback connector or no frame"); d->capture_done = true; return; }
	uint32_t w = d->mode.hdisplay, h = d->mode.vdisplay;
	uint32_t fmts[64];
	int nf = wb_formats(d, fmts, 64);
	char list[400] = "";
	for (int i = 0; i < nf; i++) { char t[8]; snprintf(t, sizeof t, "%.4s ", (char *)&fmts[i]); strncat(list, t, sizeof list - strlen(list) - 1); }
	LOG("capture: writeback formats: %s", nf ? list : "(none listed)");
	// 32-bit RGB first, then 24-bit; the PPM writer handles both byte orders.
	const uint32_t want[] = {DRM_FORMAT_XRGB8888, DRM_FORMAT_ARGB8888, DRM_FORMAT_XBGR8888, DRM_FORMAT_ABGR8888, DRM_FORMAT_RGB888, DRM_FORMAT_BGR888};
	uint32_t fmt = 0;
	for (size_t k = 0; k < sizeof want / sizeof want[0] && !fmt; k++)
		for (int i = 0; i < nf; i++) if (fmts[i] == want[k]) { fmt = want[k]; break; }
	if (!fmt) { LOG("capture: no RGB writeback format"); d->capture_done = true; return; }
	uint32_t bpp = (fmt == DRM_FORMAT_RGB888 || fmt == DRM_FORMAT_BGR888) ? 24 : 32;
	struct drm_mode_create_dumb cd = {.width = w, .height = h, .bpp = bpp};
	if (drmIoctl(d->fd, DRM_IOCTL_MODE_CREATE_DUMB, &cd)) { LOG("capture: dumb buffer failed"); d->capture_done = true; return; }
	uint32_t fb = 0, handles[4] = {cd.handle}, pitches[4] = {cd.pitch}, offsets[4] = {0};
	if (drmModeAddFB2(d->fd, w, h, fmt, handles, pitches, offsets, &fb, 0)) { LOG("capture: AddFB2 failed: %s", strerror(errno)); d->capture_done = true; return; }
	{	// pre-fill with magenta, so any line the writeback didn't write is obvious
		struct drm_mode_map_dumb md0 = {.handle = cd.handle};
		drmIoctl(d->fd, DRM_IOCTL_MODE_MAP_DUMB, &md0);
		uint8_t *px0 = mmap(NULL, cd.size, PROT_WRITE, MAP_SHARED, d->fd, md0.offset);
		if (px0 != MAP_FAILED) {
			for (size_t i = 0; i + 2 < cd.size; i += bpp / 8) { px0[i] = 0xff; px0[i + 1] = 0; px0[i + 2] = 0xff; }
			munmap(px0, cd.size);
		}
	}
	int32_t fence = -1;
	drmModeAtomicReq *req = drmModeAtomicAlloc();
	drmModeAtomicAddProperty(req, d->wb_conn_id, d->p_wb_crtc, d->crtc_id);
	drmModeAtomicAddProperty(req, d->wb_conn_id, d->p_wb_fb, fb);
	drmModeAtomicAddProperty(req, d->wb_conn_id, d->p_wb_fence, (uint64_t)(uintptr_t)&fence);
	int r = drmModeAtomicCommit(d->fd, req, DRM_MODE_ATOMIC_ALLOW_MODESET, NULL);
	drmModeAtomicFree(req);
	if (r) { LOG("capture: writeback commit failed: %s", strerror(errno)); }
	else {
		if (fence >= 0) { struct pollfd p = {fence, POLLIN, 0}; poll(&p, 1, 2000); close(fence); }
		struct drm_mode_map_dumb md = {.handle = cd.handle};
		drmIoctl(d->fd, DRM_IOCTL_MODE_MAP_DUMB, &md);
		uint8_t *px = mmap(NULL, cd.size, PROT_READ, MAP_SHARED, d->fd, md.offset);
		char path[512];
		int ncap = getenv("PYXIS_HDMI_CAPTURES") ? atoi(getenv("PYXIS_HDMI_CAPTURES")) : 1;
		if (ncap > 1) snprintf(path, sizeof path, "%s.%03d", opt_capture, d->captures);
		else snprintf(path, sizeof path, "%s", opt_capture);
		FILE *f = px != MAP_FAILED ? fopen(path, "wb") : NULL;
		if (f) {
			fprintf(f, "P6\n%u %u\n255\n", w, h);
			uint32_t bytespp = bpp / 8;
			// little-endian DRM formats: XRGB8888 = B,G,R,X in memory; XBGR8888 = R,G,B,X;
			// RGB888 = B,G,R; BGR888 = R,G,B
			bool bgr_mem = (fmt == DRM_FORMAT_XRGB8888 || fmt == DRM_FORMAT_ARGB8888 || fmt == DRM_FORMAT_RGB888);
			for (uint32_t y = 0; y < h; y++)
				for (uint32_t x = 0; x < w; x++) {
					uint8_t *q = px + (size_t)y * cd.pitch + x * bytespp;
					uint8_t rgb[3] = {bgr_mem ? q[2] : q[0], q[1], bgr_mem ? q[0] : q[2]};
					fwrite(rgb, 1, 3, f);
				}
			fclose(f);
			LOG("capture: wrote %ux%u HDMI output (%.4s) to %s", w, h, (char *)&fmt, path);
		}
		if (px != MAP_FAILED) munmap(px, cd.size);
		// detach the writeback connector again
		req = drmModeAtomicAlloc();
		drmModeAtomicAddProperty(req, d->wb_conn_id, d->p_wb_crtc, 0);
		drmModeAtomicCommit(d->fd, req, DRM_MODE_ATOMIC_ALLOW_MODESET, NULL);
		drmModeAtomicFree(req);
	}
	drmModeRmFB(d->fd, fb);
	struct drm_mode_destroy_dumb dd = {.handle = cd.handle};
	drmIoctl(d->fd, DRM_IOCTL_MODE_DESTROY_DUMB, &dd);
	d->frames_since_capture = 0;
	int ncap = getenv("PYXIS_HDMI_CAPTURES") ? atoi(getenv("PYXIS_HDMI_CAPTURES")) : 1;
	if (++d->captures >= ncap) d->capture_done = true;
}

// ------------------------------------------------------------------------- decoder + pipeline

typedef struct {
	MppCtx ctx;
	MppApi *mpi;
	MppBufferGroup group;
	pthread_t out_thread;
	volatile bool running;
	int codec;
	// handoff to the display thread, oldest first
	pthread_mutex_t mu;
	MppFrame q[PACE_QUEUE];
	int64_t q_stream_us[PACE_QUEUE];
	int nq;
	// stream time of recent access units, found again by their pts (arrival time)
	struct { int64_t arrival_us, stream_us; } tmap[64];
	int tmap_head;
	int efd;
	// stats
	uint64_t decoded, errors, handoff_drops, dec_lat_sum_us, dec_lat_n;
	uint32_t width, height;
} dec_t;

static dec_t g_dec;
static disp_t g_disp;
static depay_t g_depay;
static volatile bool g_release_request = false;  // stream ended: display drops its frames
static pthread_mutex_t g_disp_mu = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t g_disp_cv = PTHREAD_COND_INITIALIZER;
static volatile double g_stream_fps = 0;

// Asks the display thread to let go of every decoded frame (and its framebuffers), and
// waits until it has. Needed before decoder buffers are freed or reallocated.
static void request_display_release(int efd) {
	if (opt_no_display) return;
	pthread_mutex_lock(&g_disp_mu);
	g_release_request = true;
	uint64_t one = 1;
	ssize_t wr = write(efd, &one, sizeof one);
	(void)wr;
	while (g_release_request && !g_stop) {
		struct timespec ts;
		clock_gettime(CLOCK_REALTIME, &ts);
		ts.tv_sec += 1;
		pthread_cond_timedwait(&g_disp_cv, &g_disp_mu, &ts);
	}
	pthread_mutex_unlock(&g_disp_mu);
}

static void dec_clear_handoff(dec_t *dc) {
	pthread_mutex_lock(&dc->mu);
	for (int i = 0; i < dc->nq; i++) mpp_frame_deinit(&dc->q[i]);
	dc->nq = 0;
	pthread_mutex_unlock(&dc->mu);
}

static void *dec_out_main(void *arg) {
	dec_t *dc = arg;
	while (dc->running) {
		MppFrame f = NULL;
		MPP_RET r = dc->mpi->decode_get_frame(dc->ctx, &f);
		if (r != MPP_OK || !f) continue;  // timeout (100 ms)
		if (mpp_frame_get_info_change(f)) {
			uint32_t w = mpp_frame_get_width(f), h = mpp_frame_get_height(f);
			size_t size = mpp_frame_get_buf_size(f);
			LOG("stream: %ux%u (stride %ux%u), %s", w, h, mpp_frame_get_hor_stride(f), mpp_frame_get_ver_stride(f),
			    dc->codec == CODEC_H264 ? "H.264" : "H.265");
			if (!dc->group) {
				if (mpp_buffer_group_get_internal(&dc->group, MPP_BUFFER_TYPE_DRM)) { LOG("can't allocate decoder buffers"); mpp_frame_deinit(&f); continue; }
				dc->mpi->control(dc->ctx, MPP_DEC_SET_EXT_BUF_GROUP, dc->group);
			} else {
				// new size mid-stream: the display may still show an old buffer
				dec_clear_handoff(dc);
				request_display_release(dc->efd);
				mpp_buffer_group_clear(dc->group);
			}
			// references + frames held by the display (front, pending, its queue, the handoff)
			mpp_buffer_group_limit_config(dc->group, size, 40);
			dc->width = w; dc->height = h;
			dc->mpi->control(dc->ctx, MPP_DEC_SET_INFO_CHANGE_READY, NULL);
			mpp_frame_deinit(&f);
			continue;
		}
		if (mpp_frame_get_eos(f) && !mpp_frame_get_buffer(f)) { mpp_frame_deinit(&f); continue; }
		if (mpp_frame_get_errinfo(f) || mpp_frame_get_discard(f)) { dc->errors++; mpp_frame_deinit(&f); continue; }
		dc->decoded++;
		if (g_debug && dc->decoded == 1)
			LOG("debug: first frame %ux%u stride %ux%u fmt 0x%x mode 0x%x (0 = progressive frame)",
			    mpp_frame_get_width(f), mpp_frame_get_height(f), mpp_frame_get_hor_stride(f),
			    mpp_frame_get_ver_stride(f), (unsigned)mpp_frame_get_fmt(f), (unsigned)mpp_frame_get_mode(f));
		int64_t arrival = mpp_frame_get_pts(f);
		int64_t t = now_us();
		if (arrival > 0 && t > arrival) { dc->dec_lat_sum_us += (uint64_t)(t - arrival); dc->dec_lat_n++; }
		if (opt_no_display) { mpp_frame_deinit(&f); continue; }
		pthread_mutex_lock(&dc->mu);
		int64_t st = INT64_MIN;
		for (int i = 0; i < 64; i++) if (dc->tmap[i].arrival_us == arrival) { st = dc->tmap[i].stream_us; break; }
		if (dc->nq == PACE_QUEUE) {  // display stalled: drop the oldest
			mpp_frame_deinit(&dc->q[0]);
			memmove(dc->q, dc->q + 1, sizeof dc->q[0] * (PACE_QUEUE - 1));
			memmove(dc->q_stream_us, dc->q_stream_us + 1, sizeof dc->q_stream_us[0] * (PACE_QUEUE - 1));
			dc->nq--; dc->handoff_drops++;
		}
		dc->q[dc->nq] = f; dc->q_stream_us[dc->nq] = st; dc->nq++;
		pthread_mutex_unlock(&dc->mu);
		uint64_t one = 1;
		ssize_t wr = write(dc->efd, &one, sizeof one);
		(void)wr;
	}
	return NULL;
}

static int dec_start(dec_t *dc, int codec) {
	dc->codec = codec;
	if (mpp_create(&dc->ctx, &dc->mpi)) return -1;
	RK_U32 split = 0;  // we hand over whole access units
	dc->mpi->control(dc->ctx, MPP_DEC_SET_PARSER_SPLIT_MODE, &split);
	if (mpp_init(dc->ctx, MPP_CTX_DEC, codec == CODEC_H264 ? MPP_VIDEO_CodingAVC : MPP_VIDEO_CodingHEVC)) {
		mpp_destroy(dc->ctx); dc->ctx = NULL; return -1;
	}
	RK_U32 immediate = 1;  // output each picture as soon as it's decoded (no reorder delay)
	dc->mpi->control(dc->ctx, MPP_DEC_SET_IMMEDIATE_OUT, &immediate);
	RK_U32 fast = 1;       // show the first keyframe right away
	dc->mpi->control(dc->ctx, MPP_DEC_SET_ENABLE_FAST_PLAY, &fast);
	RK_S64 in_to = -1;     // block in put_packet until the decoder has room
	dc->mpi->control(dc->ctx, MPP_SET_INPUT_TIMEOUT, &in_to);
	RK_S64 out_to = 100;   // ms
	dc->mpi->control(dc->ctx, MPP_SET_OUTPUT_TIMEOUT, &out_to);
	dc->running = true;
	pthread_create(&dc->out_thread, NULL, dec_out_main, dc);
	return 0;
}

static void dec_stop(dec_t *dc) {
	if (!dc->ctx) return;
	dc->running = false;
	pthread_join(dc->out_thread, NULL);
	dec_clear_handoff(dc);
	// The display must let go of frames from this decoder's buffers first.
	request_display_release(dc->efd);
	dc->mpi->reset(dc->ctx);
	mpp_destroy(dc->ctx);
	dc->ctx = NULL;
	if (dc->group) { mpp_buffer_group_put(dc->group); dc->group = NULL; }
	dc->width = dc->height = 0;
}

static void on_au(void *ctx, const uint8_t *d, size_t n, int64_t arrival, int64_t stream_us, bool key) {
	(void)key;
	dec_t *dc = ctx;
	pthread_mutex_lock(&dc->mu);
	dc->tmap[dc->tmap_head].arrival_us = arrival;
	dc->tmap[dc->tmap_head].stream_us = stream_us;
	dc->tmap_head = (dc->tmap_head + 1) % 64;
	pthread_mutex_unlock(&dc->mu);
	MppPacket pkt = NULL;
	if (mpp_packet_init(&pkt, (void *)d, n)) return;
	mpp_packet_set_pts(pkt, arrival);
	dc->mpi->decode_put_packet(dc->ctx, pkt);  // blocks until accepted (input timeout -1)
	mpp_packet_deinit(&pkt);
}

// ------------------------------------------------------------------------- status file

static void write_status(disp_t *d, double secs) {
	if (!opt_status) return;
	char tmp[256];
	snprintf(tmp, sizeof tmp, "%s.tmp", opt_status);
	FILE *f = fopen(tmp, "w");
	if (!f) return;
	double hz = d->active ? (double)d->mode.clock * 1000.0 / ((double)d->mode.htotal * d->mode.vtotal) : 0;
	fprintf(f, "{\"time\":%lld,\"screen\":%s,\"mode\":\"%s\",\"refresh_hz\":%.3f,\"showing\":%s,"
	           "\"stream\":\"%ux%u\",\"stream_fps\":%.2f,\"shown_fps\":%.1f,\"latency_ms\":%.1f,\"low_latency\":%s}\n",
	        (long long)time(NULL), d->connected ? "true" : "false",
	        d->active ? d->mode.name : "", hz, d->plane_on ? "true" : "false",
	        g_dec.width, g_dec.height, g_stream_fps, secs > 0 ? d->win_shown / secs : 0,
	        d->win_lat_n ? d->win_lat_sum_us / 1000.0 / d->win_lat_n : 0, opt_low_latency ? "true" : "false");
	fclose(f);
	rename(tmp, opt_status);
	d->win_shown = d->win_lat_sum_us = d->win_lat_n = 0;
}

// ------------------------------------------------------------------------- frame pacing

// When a frame should be on screen. Its stream timestamp, smoothed, plus the stream's
// current lag behind this clock (the most a frame has needed in the last few seconds to
// arrive and decode), so nearly every frame is ready before its turn and the screen
// keeps the stream's rhythm. 0 (show at once) if the frame's timestamp is unknown.
static int64_t pace_due(disp_t *d, int64_t stream_us, int64_t ready) {
	if (stream_us == INT64_MIN || opt_low_latency) return 0;
	double fps = g_stream_fps;
	int64_t st = stream_us;
	bool reset = !d->clk_have;
	if (!reset) {
		int64_t dt = stream_us - d->clk_raw_us;
		if (dt <= 0 || dt > 1000000) reset = true;  // new stream or a jump: start over
		else if (fps > 0) {
			// RTMP-sourced timestamps are whole milliseconds (41/42 ms apart at 24p):
			// follow them through a slow filter instead of copying the 1 ms wobble
			double per = 1e6 / fps;
			long k = lround(dt / per);
			if (k < 1) k = 1;
			int64_t pred = d->clk_st_us + llround(k * per);
			int64_t err = stream_us - pred;
			st = llabs(err) < 20000 ? pred + err / 16 : stream_us;
		}
	}
	if (reset) { d->nlag = d->lag_head = 0; d->have_off = false; }
	d->clk_have = true; d->clk_raw_us = stream_us; d->clk_st_us = st;

	int64_t lag = ready - st;
	d->lag[d->lag_head] = lag;
	d->lag_head = (d->lag_head + 1) % PACE_WINDOW;
	if (d->nlag < PACE_WINDOW) d->nlag++;
	int64_t lo = lag, hi = lag;
	for (int i = 0; i < d->nlag; i++) { if (d->lag[i] < lo) lo = d->lag[i]; if (d->lag[i] > hi) hi = d->lag[i]; }
	int64_t target = hi < lo + PACE_MAX_JITTER_US ? hi : lo + PACE_MAX_JITTER_US;
	if (!d->have_off || target > d->lag_off) d->lag_off = target;  // frames got later: follow at once
	else d->lag_off -= d->lag_off - target < 250 ? d->lag_off - target : 250;  // earlier: ease back
	d->have_off = true;
	return st + d->lag_off + PACE_LEAD_US;
}

// First refresh at or after time t, on the grid learned from flip events.
static int64_t vbl_at_or_after(disp_t *d, int64_t t) {
	double k = ceil((double)(t - d->vbl_us) / d->period_us);
	return d->vbl_us + llround(k * d->period_us);
}

// The next refresh to choose a frame for: one a commit can still make, not already decided.
static int64_t pace_next_vbl(disp_t *d, int64_t t) {
	int64_t v = vbl_at_or_after(d, t + 1000);
	int64_t half = (int64_t)(d->period_us / 2);
	if (v <= d->decided_vbl_us + half) v = vbl_at_or_after(d, d->decided_vbl_us + half);
	return v;
}

// Shows the newest queued frame that is due by the coming refresh (dropping older ones).
static void pace_present(disp_t *d, int64_t t) {
	if (!d->active || d->flip_pending || !d->nq) return;
	int pick = -1;
	// low latency: the newest frame, at the very next refresh; also before refresh timing is known
	if (opt_low_latency || !d->vbl_us) pick = d->nq - 1;
	else {
		int64_t v = pace_next_vbl(d, t);
		if (t < v - PACE_LEAD_US - 200) return;  // not time to choose yet
		d->decided_vbl_us = v;
		for (int i = 0; i < d->nq; i++) if (d->q[i].due_us <= v) pick = i;
	}
	if (pick < 0) return;
	for (int i = 0; i < pick; i++) { release_frame(&d->q[i].f); d->dropped++; }
	MppFrame f = d->q[pick].f;
	d->nq -= pick + 1;
	memmove(d->q, d->q + pick + 1, sizeof d->q[0] * (size_t)d->nq);
	if (!disp_flip(d, f)) release_frame(&f);
}

// ------------------------------------------------------------------------- display thread

static void *disp_main(void *arg) {
	(void)arg;
	disp_t *d = &g_disp;
	// libdrm calls page_flip_handler2 (with the CRTC id) when version >= 3
	drmEventContext ev = {.version = DRM_EVENT_CONTEXT_VERSION, .page_flip_handler2 = on_flip};
	int64_t last_hotplug = 0, last_status = now_us();
	while (!g_stop) {
		// sleep until an event, or until it's time to choose the frame for the next refresh
		int64_t wait = 250000, t0 = now_us();
		if (d->active && d->nq && !d->flip_pending) {
			wait = d->vbl_us && !opt_low_latency ? pace_next_vbl(d, t0) - PACE_LEAD_US - t0 : 0;
			if (wait < 0) wait = 0;
		}
		struct timespec to = {(time_t)(wait / 1000000), (long)(wait % 1000000) * 1000};
		struct pollfd p[2] = {{d->fd, POLLIN, 0}, {g_dec.efd, POLLIN, 0}};
		ppoll(p, 2, &to, NULL);
		if (p[0].revents & POLLIN) drmHandleEvent(d->fd, &ev);
		if (p[1].revents & POLLIN) { uint64_t v; ssize_t rd = read(g_dec.efd, &v, sizeof v); (void)rd; }

		// stream ended: let go of every frame so the decoder can be torn down
		pthread_mutex_lock(&g_disp_mu);
		if (g_release_request) {
			if (d->flip_pending) { struct pollfd q = {d->fd, POLLIN, 0}; if (poll(&q, 1, 200) > 0) drmHandleEvent(d->fd, &ev); }
			disp_plane_off(d);
			disp_release_all(d);
			disp_clear_slots(d);
			g_release_request = false;
			pthread_cond_broadcast(&g_disp_cv);
		}
		pthread_mutex_unlock(&g_disp_mu);

		int64_t t = now_us();
		if (t - last_hotplug > 1000000) {
			last_hotplug = t;
			drmModeConnector *c = drmModeGetConnectorCurrent(d->fd, d->conn_id);
			bool conn = c && c->connection == DRM_MODE_CONNECTED;
			drmModeFreeConnector(c);
			if (conn && !d->connected) { LOG("HDMI: screen connected"); d->connected = true; blank_fbdev(); disp_modeset(d, g_stream_fps); }
			if (!conn && d->connected) { LOG("HDMI: screen disconnected"); d->connected = false; disp_off(d); }
			// once the frame rate is known, re-pick the mode if a better-matching one exists
			if (d->active && opt_match_rate && g_stream_fps >= 10 && fabs(g_stream_fps - d->stream_fps) > 0.01) {
				drmModeConnector *cc = drmModeGetConnectorCurrent(d->fd, d->conn_id);
				drmModeModeInfo m;
				if (cc && pick_mode(cc, g_stream_fps, &m) && (m.clock != d->mode.clock || m.vtotal != d->mode.vtotal || m.htotal != d->mode.htotal))
					disp_modeset(d, g_stream_fps);
				else d->stream_fps = g_stream_fps;
				drmModeFreeConnector(cc);
			}
		}

		// newly decoded frames: queue each with the time it's due
		MppFrame in[PACE_QUEUE];
		int64_t in_st[PACE_QUEUE];
		int nin;
		pthread_mutex_lock(&g_dec.mu);
		nin = g_dec.nq;
		memcpy(in, g_dec.q, sizeof in[0] * (size_t)nin);
		memcpy(in_st, g_dec.q_stream_us, sizeof in_st[0] * (size_t)nin);
		g_dec.nq = 0;
		pthread_mutex_unlock(&g_dec.mu);
		t = now_us();
		for (int i = 0; i < nin; i++) {
			d->last_frame_us = t;
			if (!d->active) { release_frame(&in[i]); continue; }
			if (d->nq == PACE_QUEUE) {  // shouldn't happen (due times are at most ~0.1 s out): drop the oldest
				release_frame(&d->q[0].f); d->dropped++;
				memmove(d->q, d->q + 1, sizeof d->q[0] * (PACE_QUEUE - 1));
				d->nq--;
			}
			d->q[d->nq].f = in[i];
			d->q[d->nq].due_us = pace_due(d, in_st[i], t);
			d->nq++;
		}
		pace_present(d, now_us());

		// writeback capture for testing, once enough frames have been shown
		if (opt_capture && !d->capture_done && d->active && d->frames_since_capture >= (uint64_t)(d->captures ? 3 : (getenv("PYXIS_HDMI_CAPTURE_AFTER") ? atoi(getenv("PYXIS_HDMI_CAPTURE_AFTER")) : opt_capture_after)) && !d->flip_pending)
			disp_capture(d);

		// no frames for 2 s: black screen
		if (d->plane_on && !d->flip_pending && t - d->last_frame_us > 2000000) disp_plane_off(d);

		if (t - last_status >= 1000000) {
			write_status(d, (t - last_status) / 1e6); last_status = t;
			if (g_debug && d->dbg_n) {
				int64_t lo = 0, hi = 0;
				for (int i = 0; i < d->nlag; i++) { if (!i || d->lag[i] < lo) lo = d->lag[i]; if (!i || d->lag[i] > hi) hi = d->lag[i]; }
				LOG("debug: flips %lld | commit->event min %.1f avg %.1f max %.1f ms | frames held 1/2/3/4/5+ refreshes: %llu/%llu/%llu/%llu/%llu | arrival+decode jitter %.1f ms, pacing delay %.1f ms",
				    (long long)d->dbg_n, d->dbg_c2e_min / 1000.0, d->dbg_c2e_sum / 1000.0 / d->dbg_n, d->dbg_c2e_max / 1000.0,
				    (unsigned long long)d->dbg_holds[0], (unsigned long long)d->dbg_holds[1], (unsigned long long)d->dbg_holds[2],
				    (unsigned long long)d->dbg_holds[3], (unsigned long long)d->dbg_holds[4],
				    (hi - lo) / 1000.0, (d->lag_off - lo + PACE_LEAD_US) / 1000.0);
				d->dbg_n = d->dbg_c2e_sum = 0;
				memset(d->dbg_holds, 0, sizeof d->dbg_holds);
			}
		}
	}
	return NULL;
}

// ------------------------------------------------------------------------- main

// -l: list the connected screen's modes (for troubleshooting).
static int list_modes(void) {
	int fd = open(opt_card, O_RDWR | O_CLOEXEC);
	if (fd < 0) { LOG("can't open %s", opt_card); return 1; }
	drmModeRes *res = drmModeGetResources(fd);
	for (int i = 0; res && i < res->count_connectors; i++) {
		drmModeConnector *c = drmModeGetConnector(fd, res->connectors[i]);
		if (c && c->connector_type == DRM_MODE_CONNECTOR_HDMIA) {
			LOG("HDMI %s, %d modes:", c->connection == DRM_MODE_CONNECTED ? "connected" : "not connected", c->count_modes);
			for (int m = 0; m < c->count_modes; m++) {
				drmModeModeInfo *mi = &c->modes[m];
				double hz = (double)mi->clock * 1000.0 / ((double)mi->htotal * mi->vtotal);
				LOG("  %-10s %8.3f Hz%s%s", mi->name, hz, (mi->type & DRM_MODE_TYPE_PREFERRED) ? "  preferred" : "",
				    (mi->flags & DRM_MODE_FLAG_INTERLACE) ? "  interlaced" : "");
			}
		}
		drmModeFreeConnector(c);
	}
	drmModeFreeResources(res);
	close(fd);
	return 0;
}

static void usage(void) {
	fprintf(stderr,
	        "usage: pyxis-hdmi [options]\n"
	        "  -u URL        RTSP stream (default %s)\n"
	        "  -c CARD       DRM device (default %s)\n"
	        "  -n            decode only, no display (benchmark)\n"
	        "  -r            don't switch the TV's refresh rate to match the stream\n"
	        "  -L            lowest latency: each frame at the next refresh, no smoothing buffer, never a\n"
	        "                refresh below 48 Hz (motion is less even when the camera sends in bursts)\n"
	        "  -s SECONDS    stats interval (0 = off, default 10)\n"
	        "  -w FILE       capture the HDMI output once (writeback) to a PPM file, for testing\n"
	        "  -j FILE       live status file (default /tmp/pyxis-hdmi.json, '-' = none)\n"
	        "  -l            list the connected screen's modes and exit\n",
	        opt_url, opt_card);
}

int main(int argc, char **argv) {
	int o;
	while ((o = getopt(argc, argv, "u:c:nrLs:w:j:lh")) != -1) {
		switch (o) {
		case 'u': opt_url = optarg; break;
		case 'c': opt_card = optarg; break;
		case 'n': opt_no_display = true; break;
		case 'r': opt_match_rate = false; break;
		case 'L': opt_low_latency = true; break;
		case 's': opt_stats_every = atoi(optarg); break;
		case 'w': opt_capture = optarg; break;
		case 'j': opt_status = strcmp(optarg, "-") ? optarg : NULL; break;
		case 'l': setvbuf(stdout, NULL, _IOLBF, 0); return list_modes();
		default: usage(); return o == 'h' ? 0 : 2;
		}
	}
	setvbuf(stdout, NULL, _IOLBF, 0);
	g_debug = getenv("PYXIS_HDMI_DEBUG") && *getenv("PYXIS_HDMI_DEBUG") == '1';
	signal(SIGINT, on_signal);
	signal(SIGTERM, on_signal);
	signal(SIGPIPE, SIG_IGN);

	pthread_mutex_init(&g_dec.mu, NULL);
	g_dec.efd = eventfd(0, EFD_CLOEXEC | EFD_NONBLOCK);
	pthread_t disp_thread;
	if (!opt_no_display) {
		blank_fbdev();
		if (disp_init(&g_disp) < 0) return 1;
		pthread_create(&disp_thread, NULL, disp_main, NULL);
	}

	rtsp_t r = {.fd = -1};
	if (parse_url(&r, opt_url) < 0) { LOG("bad URL %s", opt_url); return 2; }
	LOG("pyxis-hdmi: reading %s (%s)", opt_url, opt_low_latency ? "lowest latency" : "smooth motion");
	int64_t last_stats = now_us();
	int last_open_code = 0;

	while (!g_stop) {
		int code = rtsp_open(&r);
		if (code != 0) {
			if (code != last_open_code) LOG(code == 404 ? "waiting for the camera's stream" : "relay not reachable (%d), retrying", code);
			last_open_code = code;
			rtsp_close(&r);
			for (int i = 0; i < 10 && !g_stop; i++) usleep(100000);
			continue;
		}
		last_open_code = 0;
		LOG("stream started (%s)", r.codec == CODEC_H264 ? "H.264" : "H.265");
		memset(&g_depay, 0, sizeof g_depay);
		g_depay.codec = r.codec;
		g_depay.waiting_for_key = true;
		if (dec_start(&g_dec, r.codec) < 0) { LOG("hardware decoder unavailable"); rtsp_close(&r); sleep(1); continue; }

		while (!g_stop) {
			// keepalive
			if (now_us() - r.last_keepalive > 20000000) {
				rtsp_send(&r, "GET_PARAMETER", r.base, NULL);
				r.last_keepalive = now_us();
			}
			// parse buffered interleaved frames
			bool progressed = true;
			while (progressed) {
				progressed = false;
				if (r.rlen >= 4 && r.rb[0] == '$') {
					size_t len = ((size_t)r.rb[2] << 8) | r.rb[3];
					if (r.rlen >= 4 + len) {
						if (r.rb[1] == 0) depay_rtp(&g_depay, r.rb + 4, len, &r.params, on_au, &g_dec);
						rtsp_consume(&r, 4 + len);
						progressed = true;
					}
				} else if (r.rlen >= 4 && !memcmp(r.rb, "RTSP", 4)) {
					uint8_t *end = memmem(r.rb, r.rlen, "\r\n\r\n", 4);
					if (end) {  // keepalive reply (no body)
						rtsp_consume(&r, (size_t)(end - r.rb) + 4);
						progressed = true;
					}
				} else if (r.rlen > 0 && r.rb[0] != '$' && r.rb[0] != 'R') {
					rtsp_consume(&r, 1);  // resync
					progressed = true;
				}
			}
			double fps = depay_fps(&g_depay);
			if (fps > 0) g_stream_fps = fps;
			if (rtsp_fill(&r, 3000) < 0) break;  // stream ended or relay restarted
			if (r.rlen == 0 && now_us() - g_depay.first_arrival > 5000000 && g_depay.first_arrival) break;

			if (opt_stats_every > 0 && now_us() - last_stats > (int64_t)opt_stats_every * 1000000) {
				double secs = (now_us() - last_stats) / 1e6;
				LOG("stats: rtp %llu pkts, %llu seq gaps | access units %.2f/s to decoder, %llu dropped",
				    (unsigned long long)g_depay.rtp_pkts, (unsigned long long)g_depay.seq_gaps,
				    g_depay.au_out / secs, (unsigned long long)g_depay.au_dropped);
				g_depay.rtp_pkts = g_depay.seq_gaps = g_depay.au_out = g_depay.au_dropped = 0;
				LOG("stats: %ux%u %.2f fps in | decoded %.1f/s, decode latency %.1f ms, errors %llu | shown %.1f/s, arrival->on-screen %.1f ms, dropped %llu+%llu",
				    g_dec.width, g_dec.height, g_stream_fps, g_dec.decoded / secs,
				    g_dec.dec_lat_n ? g_dec.dec_lat_sum_us / 1000.0 / g_dec.dec_lat_n : 0, (unsigned long long)g_dec.errors,
				    g_disp.shown / secs, g_disp.lat_n ? g_disp.lat_sum_us / 1000.0 / g_disp.lat_n : 0,
				    (unsigned long long)g_disp.dropped, (unsigned long long)g_dec.handoff_drops);
				g_dec.decoded = g_dec.errors = g_dec.dec_lat_sum_us = g_dec.dec_lat_n = g_dec.handoff_drops = 0;
				g_disp.shown = g_disp.dropped = g_disp.lat_sum_us = g_disp.lat_n = 0;
				last_stats = now_us();
			}
		}
		if (g_stop) break;  // shutting down: the display releases its frames first (below)
		LOG("stream stopped");
		rtsp_close(&r);
		dec_stop(&g_dec);
		g_stream_fps = 0;
	}

	// Shutdown order: display off (frees its frames), then the decoder and its buffers.
	if (!opt_no_display) {
		pthread_join(disp_thread, NULL);
		disp_plane_off(&g_disp);
		disp_off(&g_disp);
		disp_release_all(&g_disp);
		disp_clear_slots(&g_disp);
		blank_fbdev();
	}
	rtsp_close(&r);
	dec_stop(&g_dec);
	if (opt_status) unlink(opt_status);
	LOG("pyxis-hdmi: stopped");
	return 0;
}
