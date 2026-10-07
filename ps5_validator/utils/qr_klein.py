# -*- coding: utf-8 -*-
"""Ein QR-Code fuer einen kurzen Text - die Adresse einer Weboberflaeche, damit ein Handy sie abfotografieren kann.

Byte-Modus, Fehlerkorrektur M, Versionen 1 bis 6 (bis 106 Byte), Maske 0 - das genuegt fuer eine Adresse wie
``http://192.168.1.94:5905/``. Keine Bibliothek noetig.

Herkunft: eine Uebertragung nach Python von ``webhb/qr.c`` aus **webhb 0.4.1** (GPL-3.0-oder-neuer; Copyright (C) 2025
EchoStretch, (C) 2026 slopmaster33; Quelle: https://github.com/EchoStretch/ps5-app-dumper bzw. das webhb-Archiv).
Der Aufbau folgt ISO 18004; die Uebertragung ist gegen das C-Original geprueft (gleiche Module fuer gleiche Eingaben,
``test_qr_klein.py``). Dieses Programm steht seit dem 07.10.2026 unter GPL-3.0-oder-neuer, beides vertraegt sich.
"""
from __future__ import annotations

MAX_VERSION = 6

#: Stufe M: (Gesamtzahl der Codewoerter, Fehlerkorrektur-Codewoerter je Block, Zahl der Bloecke) je Version.
_VERSIONEN = {1: (26, 10, 1), 2: (44, 16, 1), 3: (70, 26, 1), 4: (100, 18, 2), 5: (134, 24, 2), 6: (172, 16, 4)}
#: Mitte des Ausrichtungsmusters, Versionen 2 bis 6.
_AUSRICHTUNG = {2: 18, 3: 22, 4: 26, 5: 30, 6: 34}

_EXP = [0] * 512
_LOG = [0] * 256


def _gf_init() -> None:
    if _EXP[1]:
        return
    v = 1
    for i in range(255):
        _EXP[i] = v
        _LOG[v] = i
        v <<= 1
        if v & 0x100:
            v ^= 0x11D
    for i in range(255, 512):
        _EXP[i] = _EXP[i - 255]


def _mul(a: int, b: int) -> int:
    return _EXP[_LOG[a] + _LOG[b]] if (a and b) else 0


def _rs(daten: list[int], ec: int) -> list[int]:
    """Reed-Solomon-Paritaet von ``daten`` mit ``ec`` Symbolen."""
    gen = [0] * 64
    gen[0] = 1
    for i in range(ec):
        for j in range(i + 1, 0, -1):
            gen[j] = gen[j - 1] ^ _mul(gen[j], _EXP[i])
        gen[0] = _mul(gen[0], _EXP[i])
    out = [0] * ec
    for byte in daten:
        f = byte ^ out[0]
        out = out[1:] + [0]
        if f:
            for j in range(ec):
                out[j] ^= _mul(gen[ec - 1 - j], f)
    return out


class _Matrix:
    """Module als Zahlen: Bit 0 = dunkel, Bit 1 = Funktionsmuster."""

    def __init__(self, groesse: int) -> None:
        self.n = groesse
        self.m = [[0] * groesse for _ in range(groesse)]

    def setze(self, r: int, c: int, dunkel: int) -> None:
        self.m[r][c] = 2 | (1 if dunkel else 0)


def _sucher(q: _Matrix, r0: int, c0: int) -> None:
    for r in range(-1, 8):
        for c in range(-1, 8):
            rr, cc = r0 + r, c0 + c
            if rr < 0 or cc < 0 or rr >= q.n or cc >= q.n:
                continue
            an = (0 <= r <= 6 and 0 <= c <= 6) and (r in (0, 6) or c in (0, 6) or (2 <= r <= 4 and 2 <= c <= 4))
            q.setze(rr, cc, an)


def _muster(q: _Matrix, version: int) -> None:
    _sucher(q, 0, 0)
    _sucher(q, 0, q.n - 7)
    _sucher(q, q.n - 7, 0)
    for i in range(8, q.n - 8):
        q.setze(6, i, i % 2 == 0)
        q.setze(i, 6, i % 2 == 0)
    if version >= 2:
        a = _AUSRICHTUNG[version]
        for r in range(-2, 3):
            for c in range(-2, 3):
                q.setze(a + r, a + c, r in (-2, 2) or c in (-2, 2) or (r == 0 and c == 0))
    for i in range(8):
        q.setze(8, i if i < 6 else i + 1, 0)
        q.setze(i if i < 6 else i + 1, 8, 0)
    q.setze(8, 8, 0)
    for i in range(8):
        q.setze(8, q.n - 1 - i, 0)
        q.setze(q.n - 1 - i, 8, 0)
    q.setze(q.n - 8, 8, 1)


def _format(q: _Matrix, maske: int) -> None:
    bits = (0 << 3) | maske                       # Stufe M = 00
    rest = bits << 10
    for i in range(14, 9, -1):
        if rest & (1 << i):
            rest ^= 0x537 << (i - 10)
    f = ((bits << 10) | rest) ^ 0x5412
    for i in range(15):
        b = (f >> i) & 1
        if i < 6:
            q.setze(i, 8, b)
        elif i < 8:
            q.setze(i + 1, 8, b)
        elif i == 8:
            q.setze(8, 7, b)
        else:
            q.setze(8, 14 - i, b)
        if i < 8:
            q.setze(8, q.n - 1 - i, b)
        else:
            q.setze(q.n - 15 + i, 8, b)


def erzeuge(text: str) -> list[list[bool]]:
    """Die Module des QR-Codes (``True`` = dunkel), ohne Ruhezone.

    Raises:
        ValueError: Der Text ist laenger als 106 Byte (UTF-8) und passt in keine der Versionen 1 bis 6.
    """
    _gf_init()
    roh = list(text.encode("utf-8"))
    laenge = len(roh)
    version = 0
    for v in range(1, MAX_VERSION + 1):
        gesamt, ec, bloecke = _VERSIONEN[v]
        if gesamt - ec * bloecke >= laenge + 2:
            version = v
            break
    if not version:
        raise ValueError("Der Text ist zu lang fuer einen QR-Code dieser Bauart (hoechstens 106 Byte).")

    gesamt, ec, bloecke = _VERSIONEN[version]
    daten_cw = gesamt - ec * bloecke
    je_block = daten_cw // bloecke

    daten = [0] * 256
    bit = 0

    def put(wert: int, n: int) -> None:
        nonlocal bit
        for k in range(n - 1, -1, -1):
            if (wert >> k) & 1:
                daten[bit // 8] |= 0x80 >> (bit % 8)
            bit += 1

    put(4, 4)
    put(laenge, 8)
    for b in roh:
        put(b, 8)
    if bit + 4 <= daten_cw * 8:
        bit += 4
    bit = (bit + 7) // 8 * 8
    k = 0
    for i in range(bit // 8, daten_cw):
        daten[i] = 0x11 if k % 2 else 0xEC
        k += 1

    ecc = [_rs(daten[b * je_block:(b + 1) * je_block], ec) for b in range(bloecke)]
    final: list[int] = []
    for i in range(je_block):
        for b in range(bloecke):
            final.append(daten[b * je_block + i])
    for i in range(ec):
        for b in range(bloecke):
            final.append(ecc[b][i])

    q = _Matrix(17 + 4 * version)
    _muster(q, version)

    r, richtung, i = q.n - 1, -1, 0
    c = q.n - 1
    while c > 0:
        if c == 6:
            c -= 1
        while True:
            for k in range(2):
                cc = c - k
                if q.m[r][cc] & 2:
                    continue
                b = (final[i // 8] >> (7 - i % 8)) & 1 if i < gesamt * 8 else 0
                i += 1
                if (r + cc) % 2 == 0:
                    b ^= 1
                q.m[r][cc] = b
            r += richtung
            if r < 0 or r >= q.n:
                r -= richtung
                richtung = -richtung
                break
        c -= 2
    _format(q, 0)
    return [[bool(q.m[r][c] & 1) for c in range(q.n)] for r in range(q.n)]


def als_bild(text: str, modul: int = 8, ruhezone: int = 4):
    """Der Code als Pillow-Bild (schwarz auf weiss, mit Ruhezone) - ``modul`` Bildpunkte je Modul."""
    from PIL import Image
    module = erzeuge(text)
    n = len(module)
    gesamt = (n + 2 * ruhezone) * modul
    bild = Image.new("1", (gesamt, gesamt), 1)
    punkte = bild.load()
    for r in range(n):
        for c in range(n):
            if module[r][c]:
                x0, y0 = (c + ruhezone) * modul, (r + ruhezone) * modul
                for y in range(y0, y0 + modul):
                    for x in range(x0, x0 + modul):
                        punkte[x, y] = 0
    return bild.convert("RGB")
