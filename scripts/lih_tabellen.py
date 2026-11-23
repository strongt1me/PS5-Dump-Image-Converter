"""Stufe 1 des LIH-Nachbaus (Update-/Patchpakete, ``\\x7fLIH``): rechnet die Tabellen eines Patchpakets aus Basis und Ziel neu
und haelt sie byteweise gegen ein echtes, mit Sonys Werkzeug gebautes Patchpaket. Liest nur, schreibt nichts.

Aufruf::

    python scripts/lih_tabellen.py <Basis.pkg> <Patch.pkg> [--sonys-auswahl]

Gerechnet wird, was sich aus Basis, gepatchtem Gesamtpaket (FIH/CNT im Patch) und der Blockzuordnung ergibt:
LIH-Kopf, die vier ``\\x7fRLC``-Tabellen (origin/target/update/gathered), ``relocinfoset.dat`` (``\\x7fRIS``) mit Bitfeldern
und Pruefsummen, die CNT-Eintraege 0x40B/0x40C. Die Blockzuordnung (welcher Zielblock aus welchem Basisblock) waehlt Sonys
Werkzeug nach einer Regel, die nicht nur an den Blockprüfsummen haengt; ``--sonys-auswahl`` uebernimmt sie aus dem echten
Patch (dann muss alles byte-gleich sein), ohne den Schalter rechnet das Skript sie selbst (eindeutige Prüfsumme) und meldet,
wie weit sie abweicht. Formatbeschreibung: Memory ``project_lih_patch_nachbau_2026-11-22``.

Gemessen am 22./23.11.2026 an LEGO Batman (PPSA16833, Basis 34 GB, zwei Backport-Patches).
"""
from __future__ import annotations

import hashlib
import io
import struct
import sys
import zipfile
from pathlib import Path

BLOCK = 0x10000
RLC_KOPF = 0x1000
DATUM = 0x20221019                      # steht in jedem RLC/RIS-Kopf der Proben (Werkzeugstand?)
KEIN = 0xFFFFFFFF
PATCHMARKE = 0x10000000


def le32(b: bytes, o: int) -> int:
    return struct.unpack_from("<I", b, o)[0]


def le64(b: bytes, o: int) -> int:
    return struct.unpack_from("<Q", b, o)[0]


def be32(b: bytes, o: int) -> int:
    return struct.unpack_from(">I", b, o)[0]


def sha3(d: bytes) -> bytes:
    return hashlib.sha3_256(d).digest()


def cnt_eintraege(f, cnt_at: int) -> dict[int, bytes]:
    f.seek(cnt_at)
    kopf = f.read(0x1000)
    if kopf[:4] != b"\x7fCNT":
        raise ValueError("kein \\x7fCNT bei %#x" % cnt_at)
    n, tab = be32(kopf, 0x10), be32(kopf, 0x18)
    f.seek(cnt_at + tab)
    zeilen = f.read(n * 0x20)
    aus = {}
    for i in range(n):
        eid, off, groesse = be32(zeilen, i * 0x20), be32(zeilen, i * 0x20 + 16), be32(zeilen, i * 0x20 + 20)
        f.seek(cnt_at + off)
        aus[eid] = f.read(groesse)
    return aus


def bloecke(imagedigs: bytes) -> list:
    """Paketblock-Index -> Digest (Index 0 = FIH, ohne Digest)."""
    return [None] + [imagedigs[i:i + 32] for i in range(0, len(imagedigs), 32)]


def rlc_kopf(art: int, n: int, ziel_digest: bytes, basis_digest: bytes, basis_n: int, extra: dict) -> bytearray:
    k = bytearray(RLC_KOPF)
    k[0:4] = b"\x7fRLC"
    struct.pack_into("<HH", k, 4, art, 1)
    struct.pack_into("<IIIIII", k, 0x10, BLOCK, n, RLC_KOPF + 4 * n, DATUM, RLC_KOPF, 4 * n)
    for off, wert in extra.items():
        struct.pack_into("<I", k, off, wert)
    k[0xA0:0xC0] = basis_digest
    struct.pack_into("<BBBBI", k, 0x100, 1, 0, 1, 1, n)
    k[0x120:0x140] = ziel_digest
    if art != 1:
        struct.pack_into("<BBBBI", k, 0x140, 0, 0, 1, 1, basis_n)
        k[0x160:0x180] = basis_digest
    return k


def playgo_ende(playgo_chunk_dat: bytes) -> int:
    """RLC origin@0x3C: Ende (Offset + Groesse, in Bloecken) des PlayGo-mchunks 1 aus der playgo-chunk.dat des Ziels;
    hat sie nur einen mchunk (Forge-Pakete), das Ende von mchunk 0. Die mchunk-Tabelle steht laut plgx-Kopf bei u32 @0xD8
    (Laenge @0xDC), Eintraege (u64 Offset, u64 Groesse). Gedeutet an einem Sony-Beispiel (LEGO Batman), Forge-Fall ungeprueft."""
    tab, laenge = le32(playgo_chunk_dat, 0xD8), le32(playgo_chunk_dat, 0xDC)
    k = 1 if laenge >= 0x20 else 0
    return (le64(playgo_chunk_dat, tab + 0x10 * k) + le64(playgo_chunk_dat, tab + 0x10 * k + 8)) // BLOCK


def rlc(kopf: bytearray, werte: list[int]) -> bytes:
    return bytes(kopf) + struct.pack("<%dI" % len(werte), *werte)


def bitfeld(bits: list[bool]) -> bytes:
    feld = bytearray((len(bits) + 7) // 8)
    for i, b in enumerate(bits):
        if b:
            feld[i >> 3] |= 1 << (i & 7)
    return bytes(feld)


def ris(origin_rlc: bytes, n: int, ziel_digest: bytes, basis_digest: bytes, gesetzt: list[bool]) -> bytes:
    daten_off = 0x440
    daten_groesse = (len(origin_rlc) + 0xF) // 0x10 * 0x10
    bmp_off = daten_off + daten_groesse
    bmp = bytearray(b"\x7fbmp" + struct.pack("<I", 3))
    for feld in (bitfeld(gesetzt), bytes((n + 7) // 8), bytes((n + 7) // 8)):
        satz = b"\x7fbit" + struct.pack("<I", n) + feld
        bmp += satz + bytes((-len(satz)) % 8)
    gesamt = bmp_off + len(bmp)
    r = bytearray(gesamt)
    r[0:4] = b"\x7fRIS"
    struct.pack_into("<HH", r, 4, 0, 1)
    struct.pack_into("<IIII", r, 0x10, BLOCK, 1, 0, DATUM)
    struct.pack_into("<IIII", r, 0x20, gesamt, 0, 0x400, 0x40)
    struct.pack_into("<QQQQ", r, 0x30, daten_off, daten_groesse, bmp_off, len(bmp))
    # 0x400: Satzkopf 01000101 / 00000101, dann Ort und Laenge der eingebetteten origin-RLC, dann SHA3 davon
    r[0x400:0x408] = bytes([1, 0, 1, 1, 0, 0, 1, 1])
    struct.pack_into("<QQQ", r, 0x408, 0, daten_off, len(origin_rlc))
    r[0x420:0x440] = sha3(origin_rlc)
    r[daten_off:daten_off + len(origin_rlc)] = origin_rlc
    r[bmp_off:] = bmp
    struct.pack_into("<BBBBI", r, 0x80, 1, 0, 1, 1, n)
    r[0xA0:0xC0] = ziel_digest
    r[0xC0:0xE0] = basis_digest
    r[0xE0:0x100] = sha3(bytes(r[0x400:0x440]))
    r[0x100:0x120] = sha3(bytes(bmp))                       # SHA3 des ganzen \x7fbmp-Abschnitts
    r[0x3E0:0x400] = sha3(bytes(r[:0x3E0]))                 # zuletzt: SHA3 des Kopfs davor
    return bytes(r)


def vergleich(name: str, neu: bytes, echt: bytes) -> bool:
    if neu == echt:
        print(f"  [GLEICH]   {name} ({len(echt)} Bytes)")
        return True
    if len(neu) != len(echt):
        print(f"  [ANDERS]   {name}: Laenge {len(neu)} statt {len(echt)}")
    diff = [i for i in range(min(len(neu), len(echt))) if neu[i] != echt[i]]
    print(f"  [ANDERS]   {name}: {len(diff)} Bytes verschieden, erste bei {[hex(x) for x in diff[:8]]}")
    return False


def main(argv: list[str]) -> int:
    basis_pfad, patch_pfad = Path(argv[1]), Path(argv[2])
    sonys_auswahl = "--sonys-auswahl" in argv
    with open(basis_pfad, "rb") as f:
        bfih = f.read(BLOCK)
        bcnt = cnt_eintraege(f, le64(bfih, 0x58))
    with open(patch_pfad, "rb") as f:
        lih = f.read(BLOCK)
        if lih[:4] != b"\x7fLIH":
            print("kein \\x7fLIH-Patchpaket")
            return 2
        f.seek(le64(lih, 0x20))
        zfih = f.read(BLOCK)
        cnt_at, cnt_groesse = le64(lih, 0x30), le64(lih, 0x38)
        zcnt = cnt_eintraege(f, cnt_at)
        f.seek(le64(lih, 0x40))
        z = zipfile.ZipFile(io.BytesIO(f.read(le64(lih, 0x48))))
        echt = {i.filename.split("/")[-1]: z.read(i) for i in z.infolist()}
        datenbloecke = list(range(2, cnt_at // BLOCK))           # Patchdatei-Bloecke 2.. (0 = LIH-Kopf, 1 = FIH)
        f.seek(2 * BLOCK)
        patch_sha = {}
        for k in datenbloecke:
            patch_sha.setdefault(sha3(f.read(BLOCK))[::-1], k)

    B, T = bloecke(bcnt[0x040A]), bloecke(zcnt[0x040A])
    n, basis_n = len(T), len(B)
    zd, bd = zfih[0x70:0x90], bfih[0x70:0x90]
    print(f"Basis {basis_n} Paketbloecke, Ziel {n}, Patch traegt {len(datenbloecke)} Datenbloecke")

    echt_origin = echt["origin-relocinfo.dat"]
    sony = list(struct.unpack_from("<%dI" % n, echt_origin, RLC_KOPF))
    if sonys_auswahl:
        origin = sony
    else:
        wo: dict = {}
        for j, d in enumerate(B):
            if d is not None:
                wo.setdefault(d, []).append(j)
        origin = [KEIN] + [wo[T[i]][0] if T[i] in wo and len(wo[T[i]]) == 1 else KEIN for i in range(1, n)]
        gleich = sum(1 for a, b in zip(origin, sony) if a == b)
        print(f"Eigene Auswahl (eindeutige Pruefsumme): {sum(x != KEIN for x in origin)} wiederverwendet, "
              f"Sony {sum(x != KEIN for x in sony)}; gleiche Eintraege {gleich} von {n}")

    # gathered: Zielblock -> Block der Patchdatei. Der Patch traegt jeden nicht wiederverwendeten Zielblock der Reihe nach
    # (Block 1 = FIH, dann 2, 3, ...), auch doppelte (Nullbloecke) - also fortlaufend, nicht nach Pruefsumme.
    gathered, k = [], 1
    for i in range(n):
        if origin[i] != KEIN:
            gathered.append(KEIN)
        else:
            gathered.append(k)
            k += 1
    falsch = sum(1 for i in range(1, n) if gathered[i] != KEIN and patch_sha.get(T[i]) is None)
    if k - 1 != len(datenbloecke) + 1 or falsch:
        print(f"  Die Auswahl braucht {k - 1} Patchbloecke (der Patch traegt {len(datenbloecke) + 1}); "
              f"{falsch} Zielbloecke gibt es im Patch gar nicht - so nicht darstellbar")
    update = [origin[i] if origin[i] != KEIN else (PATCHMARKE | gathered[i]) for i in range(n)]
    wieder = sum(1 for x in origin if x != KEIN)
    aus_patch = sum(1 for x in gathered if x != KEIN)

    # origin@0x3C: Ende (Offset + Groesse, in Bloecken) des PlayGo-Teilstuecks (mchunk) 1 aus der playgo-chunk.dat des Ziels.
    # Die mchunk-Tabelle steht laut plgx-Kopf bei u32 @0xD8, Eintraege (u64 Offset, u64 Groesse). Gedeutet aus einem Beispiel
    # (LEGO Batman: mchunk 0 = Bloecke 0..517627, mchunk 1 = 517628, Feld = 517629) - eine Vermutung, an weiteren Paketen pruefen.
    o3c = playgo_ende(zcnt[0x1001])
    if o3c != le32(echt_origin, 0x3C):
        print(f"  origin@0x3C: gerechnet {o3c}, im Patch {le32(echt_origin, 0x3C)} - Deutung stimmt hier nicht")
    origin_kopf = rlc_kopf(0, n, zd, bd, basis_n, {0x30: 1, 0x34: 1, 0x38: wieder, 0x3C: o3c})
    neu = {
        "origin-relocinfo.dat": rlc(origin_kopf, origin),
        "target-relocinfo.dat": rlc(origin_kopf, origin),
        "update-relocinfo.dat": rlc(rlc_kopf(2, n, zd, bd, basis_n, {0x2C: 2, 0xC0: wieder, 0xC4: aus_patch}), update),
        "gathered-relocinfo.dat": rlc(rlc_kopf(1, n, zd, bd, basis_n, {0x28: cnt_at // BLOCK}), gathered),
    }
    neu["relocinfoset.dat"] = ris(neu["origin-relocinfo.dat"], n, zd, bd, [x != KEIN for x in origin])
    print(f"\nTabellen (origin@0x3C = {o3c}, aus der PlayGo-Tabelle gerechnet):")
    alle = True
    for name, daten in neu.items():
        alle &= vergleich(name, daten, echt[name])
    alle &= vergleich("CNT 0x40B (origin-RLC-Kopf)", neu["origin-relocinfo.dat"][:RLC_KOPF], zcnt[0x040B])
    alle &= vergleich("CNT 0x40C (target-RLC-Kopf)", neu["target-relocinfo.dat"][:RLC_KOPF], zcnt[0x040C])
    alle &= vergleich("Zip origin-playgo-chunk.dat = Basis-CNT 0x1001", bcnt[0x1001], echt["origin-playgo-chunk.dat"])
    alle &= vergleich("Zip target-playgo-chunk.dat = Basis-CNT 0x1001", bcnt[0x1001], echt["target-playgo-chunk.dat"])
    alle &= vergleich("Zip playgo-chunk.dat = Ziel-CNT 0x1001", zcnt[0x1001], echt["playgo-chunk.dat"])
    alle &= vergleich("CNT 0x2100/0x2101 = Basis-param.json", bcnt[0x2000] + bcnt[0x2000], zcnt[0x2100] + zcnt[0x2101])

    lk = bytearray(BLOCK)
    lk[0:4] = b"\x7fLIH"
    struct.pack_into("<HH", lk, 4, 0, 1)
    struct.pack_into("<IIQ", lk, 0x10, BLOCK, cnt_at // BLOCK, patch_pfad.stat().st_size)
    struct.pack_into("<QQQQQQ", lk, 0x20, BLOCK, BLOCK, cnt_at, cnt_groesse, le64(lih, 0x40), le64(lih, 0x48))
    alle &= vergleich("LIH-Kopf", bytes(lk), lih)
    print("\nErgebnis:", "alles byte-gleich" if alle else "Abweichungen (siehe oben)")
    return 0 if alle else 1


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv))
