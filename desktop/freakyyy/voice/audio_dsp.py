"""Freakyyy's voice finishing chain - same filter graph and coefficients as the
Android FreakyyyAudioProcessor (and the FFmpeg chain behind freakyyy-morning-v5):

    highpass=f=80, equalizer=f=180:w=1:g=-2, equalizer=f=3000:w=1:g=2,
    acompressor=threshold=0.08:ratio=2:attack=15:release=120:makeup=1.5,
    loudnorm=I=-16:TP=-1.5:LRA=7

Biquads are vectorised with numpy; the compressor/limiter envelopes are
sample-recursive and run in a tight loop (fast enough for speech).
"""
from __future__ import annotations

import math

import numpy as np


def _biquad(b0, b1, b2, a1, a2):
    return np.array([b0, b1, b2], dtype=np.float64), np.array([1.0, a1, a2], dtype=np.float64)


def _highpass(sr, f, q):
    w0 = 2 * math.pi * f / sr
    alpha = math.sin(w0) / (2 * q)
    c = math.cos(w0)
    a0 = 1 + alpha
    return _biquad((1 + c) / 2 / a0, -(1 + c) / a0, (1 + c) / 2 / a0, -2 * c / a0, (1 - alpha) / a0)


def _peaking(sr, f, q, gain_db):
    a = 10 ** (gain_db / 40)
    w0 = 2 * math.pi * f / sr
    alpha = math.sin(w0) / (2 * q)
    c = math.cos(w0)
    a0 = 1 + alpha / a
    return _biquad((1 + alpha * a) / a0, -2 * c / a0, (1 - alpha * a) / a0, -2 * c / a0, (1 - alpha / a) / a0)


class _Filter:
    """Transposed direct-form II biquad with state kept between chunks."""

    def __init__(self, coeffs):
        self.b, self.a = coeffs
        self.z = np.zeros(2)

    def reset(self):
        self.z[:] = 0

    def process(self, x: np.ndarray) -> np.ndarray:
        try:
            from scipy.signal import lfilter  # optional fast path
            y, self.z = lfilter(self.b, self.a, x, zi=self.z)
            return y
        except ImportError:
            b0, b1, b2 = self.b
            _, a1, a2 = self.a
            z1, z2 = self.z
            y = np.empty_like(x)
            for i, v in enumerate(x):
                o = b0 * v + z1
                z1 = b1 * v - a1 * o + z2
                z2 = b2 * v - a2 * o
                y[i] = o
            self.z[:] = (z1, z2)
            return y


class FreakyyyAudioProcessor:
    def __init__(self, sample_rate: int = 24_000):
        sr = sample_rate
        self.sr = sr
        self.filters = [
            _Filter(_highpass(sr, 80.0, 0.707)),
            _Filter(_peaking(sr, 180.0, 1.0, -2.0)),
            _Filter(_peaking(sr, 3000.0, 1.0, 2.0)),
        ]
        # acompressor (RMS detection, 2.828 soft knee)
        threshold, self.ratio, knee = 0.08, 2.0, 2.82843
        self.makeup = 1.5
        self.attack = min(1.0, 1.0 / (15.0 * sr / 4000.0))
        self.release = min(1.0, 1.0 / (120.0 * sr / 4000.0))
        self.thres = math.log(threshold)
        lin_knee_start = threshold / math.sqrt(knee)
        self.adj_knee_start = lin_knee_start ** 2
        self.knee_start = math.log(lin_knee_start)
        self.knee_stop = math.log(threshold * math.sqrt(knee))
        self.comp_knee_stop = (self.knee_stop - self.thres) / self.ratio + self.thres
        self.lin_slope = 0.0
        # loudness
        self.target_lufs = -16.0
        self.ceiling = 10 ** ((-1.5 - 0.3) / 20)
        self.k_shelf = _Filter(self._k_shelf(sr))
        self.k_hp = _Filter(self._k_highpass(sr))
        self.hist_energy = 0.0
        self.hist_weight = 0.0
        self.current_gain = None
        self.lookahead = max(1, sr // 200)
        self.rel = 1 - math.exp(-1 / (0.06 * sr))
        self.env = 1.0

    @staticmethod
    def _k_shelf(sr):
        g, q, f = 3.999843853973347, 0.7071752369554196, 1681.974450955533
        k = math.tan(math.pi * f / sr)
        vh = 10 ** (g / 20)
        vb = vh ** 0.4996667741545416
        a0 = 1 + k / q + k * k
        return _biquad((vh + vb * k / q + k * k) / a0, 2 * (k * k - vh) / a0, (vh - vb * k / q + k * k) / a0,
                       2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0)

    @staticmethod
    def _k_highpass(sr):
        q, f = 0.5003270373238773, 38.13547087602444
        k = math.tan(math.pi * f / sr)
        a0 = 1 + k / q + k * k
        return _biquad(1.0, -2.0, 1.0, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0)

    def reset(self):
        for f in self.filters:
            f.reset()
        self.k_shelf.reset()
        self.k_hp.reset()
        self.lin_slope = 0.0
        self.env = 1.0

    # ---------------------------------------------------------------
    def process(self, samples: np.ndarray) -> np.ndarray:
        x = samples.astype(np.float64)
        for f in self.filters:
            x = f.process(x)
        x = self._compress(x)
        x = self._normalize(x)
        return self._limit(x).astype(np.float32)

    def _compress(self, x: np.ndarray) -> np.ndarray:
        out = np.empty_like(x)
        slope = self.lin_slope
        att, rel = self.attack, self.release
        thres, ratio, adj = self.thres, self.ratio, self.adj_knee_start
        ks, kst, cks = self.knee_start, self.knee_stop, self.comp_knee_stop
        makeup = self.makeup
        width = kst - ks
        for i, v in enumerate(x):
            d = v * v
            slope += (d - slope) * (att if d > slope else rel)
            g = 1.0
            if slope > adj:
                s = math.log(slope) * 0.5
                gain = (s - thres) / ratio + thres
                if s < kst:
                    t = (s - ks) / width
                    m0, m1 = width, width / ratio
                    p0, p1 = ks, cks
                    gain = ((2 * p0 + m0 - 2 * p1 + m1) * t ** 3 + (-3 * p0 - 2 * m0 + 3 * p1 - m1) * t * t
                            + m0 * t + p0)
                g = math.exp(gain - s)
            out[i] = v * g * makeup
        self.lin_slope = slope
        return out

    def _normalize(self, x: np.ndarray) -> np.ndarray:
        w = self.k_hp.process(self.k_shelf.process(x))
        block, hop = int(self.sr * 0.4), int(self.sr * 0.1)
        if len(w) < block:
            blocks = [float(np.mean(w * w))] if len(w) else []
        else:
            blocks = [float(np.mean(w[s:s + block] ** 2)) for s in range(0, len(w) - block + 1, hop)]
        abs_gate = 10 ** ((-70 + 0.691) / 10)
        passed = [b for b in blocks if b > abs_gate]
        if passed:
            rel_gate = np.mean(passed) * 0.1
            gated = [b for b in passed if b > rel_gate] or passed
            self.hist_energy = self.hist_energy * 0.5 + float(np.mean(gated))
            self.hist_weight = self.hist_weight * 0.5 + 1.0
        if self.hist_weight:
            lufs = -0.691 + 10 * math.log10(self.hist_energy / self.hist_weight)
            target = 10 ** (max(-12.0, min(18.0, self.target_lufs - lufs)) / 20)
        else:
            target = self.current_gain or 1.0
        start = self.current_gain if self.current_gain is not None else target
        ramp = max(1, min(len(x), int(self.sr * 0.15)))
        gains = np.full(len(x), target)
        gains[:ramp] = start + (target - start) * (np.arange(1, ramp + 1) / ramp)
        self.current_gain = target
        return x * gains

    def _limit(self, x: np.ndarray) -> np.ndarray:
        a = np.abs(x)
        required = np.where(a > self.ceiling, self.ceiling / np.maximum(a, 1e-12), 1.0)
        n, L = len(x), self.lookahead
        # forward min over look-ahead window, then box smoothing
        padded = np.concatenate([required, np.ones(L)])
        from numpy.lib.stride_tricks import sliding_window_view
        held = sliding_window_view(padded, L + 1).min(axis=1)[:n]
        smooth = np.convolve(np.concatenate([np.ones(L - 1), held]), np.ones(L) / L, mode="valid")[:n]
        out = np.empty_like(x)
        env, rel = self.env, self.rel
        for i in range(n):
            s = smooth[i]
            env = s if s < env else env + (s - env) * rel
            out[i] = x[i] * min(env, required[i])
        self.env = env
        return out
