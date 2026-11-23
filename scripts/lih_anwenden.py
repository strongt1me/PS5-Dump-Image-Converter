"""LIH-Nachbau Stufe 2: spielt ein Patchpaket (``\\x7fLIH``) in sein Basispaket ein, wie es die Konsole tut, und schreibt das
gepatchte Gesamtpaket (FIH | Aussenimage | CNT, ohne SI-Zip) - jeder Block wird gegen ``imagedigs`` des Ziel-CNT geprueft.

Aufruf::

    python scripts/lih_anwenden.py <Basis.pkg> <Patch.pkg> <Ziel.pkg>

Grundlage ist ``update-relocinfo.dat`` aus dem Zip des Patches (Eintrag i = Zielpaketblock i: Basisblock oder
0x10000000 | Block der Patchdatei); siehe ``scripts/lih_tabellen.py``. Liest Basis und Patch nur.
"""
from __future__ import annotations

import hashlib
import io
import os
import struct
import sys
import time
import zipfile

BLOCK = 0x10000
PATCHMARKE = 0x10000000


def be32(b: bytes, o: int) -> int:
    return struct.unpack_from(">I", b, o)[0]


def imagedigs(cnt: bytes) -> bytes:
    n, tab = be32(cnt, 0x10), be32(cnt, 0x18)
    for i in range(n):
        if be32(cnt, tab + i * 0x20) == 0x040A:
            o, s = be32(cnt, tab + i * 0x20 + 16), be32(cnt, tab + i * 0x20 + 20)
            return cnt[o:o + s]
    raise ValueError("imagedigs fehlt")


def main(basis_pfad: str, patch_pfad: str, ziel_pfad: str) -> int:
    with open(patch_pfad, "rb") as p:
        lih = p.read(BLOCK)
        if lih[:4] != b"\x7fLIH":
            print("kein \\x7fLIH-Patchpaket")
            return 2
        cnt_at, cnt_groesse = struct.unpack_from("<QQ", lih, 0x30)
        zip_at, zip_groesse = struct.unpack_from("<QQ", lih, 0x40)
        p.seek(cnt_at)
        cnt = p.read(cnt_groesse)
        p.seek(zip_at)
        z = zipfile.ZipFile(io.BytesIO(p.read(zip_groesse)))
        u = z.read("common/update-relocinfo.dat")
    n = struct.unpack_from("<I", u, 0x14)[0]
    tabelle = struct.unpack_from("<%dI" % n, u, 0x1000)
    digs = imagedigs(cnt)
    if len(digs) // 32 != n - 1:
        print(f"imagedigs hat {len(digs) // 32} Bloecke, die Tabelle {n - 1}")
        return 1
    print(f"Ziel: {n} Paketbloecke + CNT ({cnt_groesse} Bytes) -> {ziel_pfad}")
    fehler, aus_basis, aus_patch, start = 0, 0, 0, time.monotonic()
    with open(basis_pfad, "rb") as b, open(patch_pfad, "rb") as p, open(ziel_pfad + ".teil", "wb") as aus:
        for i, quelle in enumerate(tabelle):
            if quelle & PATCHMARKE and quelle != 0xFFFFFFFF:
                p.seek((quelle & ~PATCHMARKE) * BLOCK)
                blk = p.read(BLOCK)
                aus_patch += 1
            else:
                b.seek(quelle * BLOCK)
                blk = b.read(BLOCK)
                aus_basis += 1
            if len(blk) != BLOCK:
                print(f"Block {i}: nur {len(blk)} Bytes gelesen")
                return 1
            if i and hashlib.sha3_256(blk).digest()[::-1] != digs[(i - 1) * 32:i * 32]:
                fehler += 1
                if fehler <= 5:
                    print(f"  Block {i}: Pruefsumme passt nicht (Quelle {quelle:#x})")
            aus.write(blk)
            if i % 50000 == 0 and i:
                print(f"  {i}/{n} Bloecke, {time.monotonic() - start:.0f} s", flush=True)
        aus.write(cnt)
    if fehler:
        print(f"FEHLER: {fehler} Bloecke mit falscher Pruefsumme - Ziel bleibt als .teil liegen")
        return 1
    os.replace(ziel_pfad + ".teil", ziel_pfad)
    print(f"fertig: {aus_basis} Bloecke aus der Basis, {aus_patch} aus dem Patch, alle {n - 1} Imagebloecke "
          f"gegen imagedigs geprueft, {time.monotonic() - start:.0f} s")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(*sys.argv[1:]))
