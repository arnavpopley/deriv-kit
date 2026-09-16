"""Reproducible N(0,1) generator: Box-Muller on std::mt19937_64."""

from __future__ import annotations

import math

_NN = 312
_MM = 156
_MATRIX_A = 0xB5026F5AA96619E9
_UM = 0xFFFFFFFF80000000
_LM = 0x7FFFFFFF
_MASK64 = 0xFFFFFFFFFFFFFFFF


class Mt19937_64:
    """C++ std::mt19937_64, so Monte Carlo streams match the original library."""

    def __init__(self, seed: int = 5489) -> None:
        self._mt = [0] * _NN
        self._index = _NN
        self.seed(seed)

    def seed(self, seed: int) -> None:
        seed &= _MASK64
        self._mt[0] = seed
        for i in range(1, _NN):
            x = self._mt[i - 1]
            x ^= x >> 62
            x = (x * 6364136223846793005 + i) & _MASK64
            self._mt[i] = x
        self._index = _NN

    def __call__(self) -> int:
        if self._index >= _NN:
            self._twist()
        y = self._mt[self._index]
        self._index += 1
        y ^= (y >> 29) & 0x5555555555555555
        y ^= (y << 17) & 0x71D67FFFEDA60000
        y ^= (y << 37) & 0xFFF7EEE000000000
        y ^= y >> 43
        return y & _MASK64

    def _twist(self) -> None:
        mag = (0, _MATRIX_A)
        for i in range(_NN - _MM):
            x = (self._mt[i] & _UM) | (self._mt[i + 1] & _LM)
            self._mt[i] = self._mt[i + _MM] ^ (x >> 1) ^ mag[x & 1]
        for i in range(_NN - _MM, _NN - 1):
            x = (self._mt[i] & _UM) | (self._mt[i + 1] & _LM)
            self._mt[i] = self._mt[i + (_MM - _NN)] ^ (x >> 1) ^ mag[x & 1]
        x = (self._mt[_NN - 1] & _UM) | (self._mt[0] & _LM)
        self._mt[_NN - 1] = self._mt[_MM - 1] ^ (x >> 1) ^ mag[x & 1]
        self._index = 0


class NormalRng:
    """Box-Muller on top of mt19937_64. One engine per pricer call."""

    def __init__(self, seed: int) -> None:
        self._gen = Mt19937_64(seed)
        self._has_spare = False
        self._spare = 0.0

    def uniform(self) -> float:
        u = self._gen()
        if u == 0:
            u = 1
        return math.ldexp(float(u), -64)

    def normal(self) -> float:
        if self._has_spare:
            self._has_spare = False
            return self._spare
        u1 = self.uniform()
        u2 = self.uniform()
        r = math.sqrt(-2.0 * math.log(u1))
        theta = 2.0 * math.pi * u2
        self._spare = r * math.sin(theta)
        self._has_spare = True
        return r * math.cos(theta)

    def discard_spare(self) -> None:
        self._has_spare = False
