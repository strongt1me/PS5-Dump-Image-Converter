"""LIH-Nachbau Stufe 2: baut aus Basispaket und gepatchtem Gesamtpaket ein Update-/Patchpaket (``\\x7fLIH``).

Aufruf::

    python scripts/lih_bauen.py <Basis.pkg> <Ziel.pkg> <Ausgabe.pkg> --si <Patch-oder-Zip> [--auswahl <Patch.pkg>]
                                [--vergleich <echtes_Patch.pkg>]

- ``Ziel.pkg``: das gepatchte Gesamtpaket (FIH | Aussenimage | CNT [| SI]); sein CNT muss die Patch-Eintraege schon tragen
  (0x40B/0x40C, 0x2100/0x2101, param.json mit origin-/targetContentVersion) - in Stufe 2 aus ``lih_anwenden.py``.
- ``--si``: woher die Zip-Teile kommen, die dieses Skript (noch) nicht selbst rechnet: naps_meta_18/300/308 und
  playgo-chunk.crc/playgo-scenario.json des Ziels (ein echtes Patchpaket oder ein Ordner mit diesen Dateinamen).
- ``--auswahl``: Blockauswahl (origin-RLC) aus einem echten Patch uebernehmen; ohne: eigene Auswahl (eindeutige Pruefsumme).
- ``--vergleich``: das fertige Paket byteweise gegen ein echtes halten (Bereiche: Kopf, FIH, Datenbloecke, CNT, Zip-Teile).

Gerechnet werden: LIH-Kopf, Datenbloecke (jeder nicht wiederverwendete Zielblock der Reihe nach), RLC x4, relocinfoset,
naps_meta_301/302/304 (301/302/304 nach Deutung, siehe Memory), origin-/target-playgo-chunk.dat und -playgo-scenario.json
(aus der Basis), playgo-chunk.dat (aus dem Ziel), das Zip (gespeichert, alphabetisch, Zeit = pubtools.creationDate).
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import struct
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lih_tabellen as lt                          # noqa: E402

BLOCK = lt.BLOCK
KEIN = lt.KEIN


def cnt_lesen(f, cnt_at: int) -> tuple[bytes, dict[int, bytes]]:
    f.seek(cnt_at)
    kopf = f.read(0x1000)
    groesse = (struct.unpack_from(">Q", kopf, 0x28)[0] + BLOCK - 1) // BLOCK * BLOCK
    f.seek(cnt_at)
    roh = f.read(groesse)
    return roh, lt.cnt_eintraege(f, cnt_at)


def bereiche(flags: list[bool], versatz: int = 0) -> list[tuple[int, int]]:
    aus, start = [], None
    for i, fl in enumerate(flags):
        if fl and start is None:
            start = i
        if not fl and start is not None:
            aus.append((start + versatz, i - start))
            start = None
    if start is not None:
        aus.append((start + versatz, len(flags) - start))
    return aus


def naps_304(origin: list[int], basis_n: int, inner_blocks: int) -> bytes:
    """Basis-Image-Bereiche (Paketblock - 1), die das Ziel nicht wiederverwendet, innerhalb [1, inner_blocks);
    der letzte bekommt die Art 0x3E9 (Deutung an einem Beispiel)."""
    genutzt = set(x for x in origin if x != KEIN)
    frei = [(s, c) for s, c in bereiche([j not in genutzt for j in range(1, basis_n)]) if 1 <= s < inner_blocks]
    d = struct.pack("<QI", 0, 1)
    for k, (s, c) in enumerate(frei):
        d += struct.pack("<III", 0x3E9 if k == len(frei) - 1 else 0, s, c)
    return d


def naps_301_302(origin: list[int]) -> tuple[bytes, bytes]:
    neu = bereiche([x == KEIN for x in origin[1:]])          # Ziel-Image-Bereiche, die der Patch traegt
    (s1, c1) = neu[0]
    s2 = neu[1][0] if len(neu) > 1 else 0
    r = c1 * BLOCK
    d301 = struct.pack("<6Q", 0, 0, r, 0x3E9, r, 0x20000)
    d302 = struct.pack("<6Q", 0, s1 * BLOCK, r, 0x3E9, s2 * BLOCK, 0x20000)
    return d301, d302


def dos_zeit(text: str) -> tuple[int, int]:
    datum, uhr = text.split()
    j, mo, t = (int(x) for x in datum.split("-"))
    h, mi, s = (int(x) for x in uhr.split(":"))
    return (h << 11) | (mi << 5) | (s // 2), ((j - 1980) << 9) | (mo << 5) | t


def zip_bauen(mitglieder: dict[str, bytes], zeit: int, datum: int) -> bytes:
    lokal, zentral = bytearray(), bytearray()
    for name in sorted(mitglieder):
        d = mitglieder[name]
        crc = __import__("zlib").crc32(d) & 0xFFFFFFFF
        n = name.encode()
        off = len(lokal)
        lokal += struct.pack("<4sHHHHHIIIHH", b"PK\x03\x04", 20, 0, 0, zeit, datum, crc, len(d), len(d), len(n), 0) + n + d
        zentral += struct.pack("<4sHHHHHHIIIHHHHHII", b"PK\x01\x02", 0, 20, 0, 0, zeit, datum, crc, len(d), len(d), len(n),
                               0, 0, 0, 0, 0, off) + n
    ende = struct.pack("<4sHHHHIIH", b"PK\x05\x06", 0, 0, len(mitglieder), len(mitglieder), len(zentral), len(lokal), 0)
    return bytes(lokal + zentral + ende)


def si_quelle(pfad: str) -> dict[str, bytes]:
    p = Path(pfad)
    if p.is_dir():
        return {q.name: q.read_bytes() for q in p.iterdir() if q.is_file()}
    with open(p, "rb") as f:
        kopf = f.read(BLOCK)
        if kopf[:4] == b"\x7fLIH":
            zo, zs = struct.unpack_from("<QQ", kopf, 0x40)
            f.seek(zo)
            z = zipfile.ZipFile(io.BytesIO(f.read(zs)))
        else:
            z = zipfile.ZipFile(f)
        return {i.filename.split("/")[-1]: z.read(i) for i in z.infolist()}


def main(argv: list[str]) -> int:
    basis_pfad, ziel_pfad, aus_pfad = argv[1:4]
    opt = {argv[i]: argv[i + 1] for i in range(4, len(argv) - 1, 2)}
    with open(basis_pfad, "rb") as f:
        bfih = f.read(BLOCK)
        _bcnt_roh, bcnt = cnt_lesen(f, lt.le64(bfih, 0x58))
    with open(ziel_pfad, "rb") as f:
        zfih = f.read(BLOCK)
        zcnt_roh, zcnt = cnt_lesen(f, lt.le64(zfih, 0x58))
    B, T = lt.bloecke(bcnt[0x040A]), lt.bloecke(zcnt[0x040A])
    n, basis_n = len(T), len(B)
    zd, bd = zfih[0x70:0x90], bfih[0x70:0x90]
    if "--auswahl" in opt:
        o = si_quelle(opt["--auswahl"])["origin-relocinfo.dat"]
        origin = list(struct.unpack_from("<%dI" % n, o, lt.RLC_KOPF))
        print("Blockauswahl aus", opt["--auswahl"])
    else:
        wo: dict = {}
        for j, d in enumerate(B):
            if d is not None:
                wo.setdefault(d, []).append(j)
        # Den Bereich hinter dem inneren Abbild (Metadaten des aeusseren PFS) traegt Sonys Patch immer selbst - Dump Forge
        # liest ihn beim Oeffnen aus dem Patch ("outer block ... is the base game's", gemessen 23.11.2026). Ab Paketblock
        # inner_blocks - 1 des Ziels (FIH 0x90; bei LEGO Batman Sonys zweiter neuer Bereich) wird nichts wiederverwendet.
        schwanz = lt.le32(zfih, 0x90) - 1
        origin = [KEIN] + [wo[T[i]][0] if i < schwanz and T[i] in wo and len(wo[T[i]]) == 1 else KEIN
                           for i in range(1, n)]
        print(f"eigene Blockauswahl (eindeutige Pruefsumme, ab Paketblock {schwanz} immer aus dem Patch)")
    gathered, k = [], 1
    for x in origin:
        gathered.append(KEIN if x != KEIN else k)
        k += x == KEIN
    patchbloecke = k - 1                                    # inkl. FIH
    cnt_at = (2 + patchbloecke - 1) * BLOCK                 # Kopf, FIH, Datenbloecke
    update = [origin[i] if origin[i] != KEIN else (lt.PATCHMARKE | gathered[i]) for i in range(n)]
    wieder = sum(1 for x in origin if x != KEIN)
    o3c = lt.playgo_ende(zcnt[0x1001])
    okopf = lt.rlc_kopf(0, n, zd, bd, basis_n, {0x30: 1, 0x34: 1, 0x38: wieder, 0x3C: o3c})
    rlc = {
        "common/origin-relocinfo.dat": lt.rlc(okopf, origin),
        "common/target-relocinfo.dat": lt.rlc(okopf, origin),
        "common/update-relocinfo.dat": lt.rlc(lt.rlc_kopf(2, n, zd, bd, basis_n, {0x2C: 2, 0xC0: wieder, 0xC4: patchbloecke}),
                                              update),
        "common/gathered-relocinfo.dat": lt.rlc(lt.rlc_kopf(1, n, zd, bd, basis_n, {0x28: cnt_at // BLOCK}), gathered),
    }
    if zcnt[0x040B] != rlc["common/origin-relocinfo.dat"][:lt.RLC_KOPF]:
        print("WARNUNG: CNT 0x40B des Ziels passt nicht zum gerechneten origin-RLC-Kopf (anderer Bau oder andere Auswahl)")
    si = si_quelle(opt["--si"])
    cid = json.loads(zcnt[0x2000].decode("utf-8-sig"))["contentId"]
    d301, d302 = naps_301_302(origin)
    mitglieder = dict(rlc)
    mitglieder.update({
        "common/etc/relocinfoset.dat": lt.ris(rlc["common/origin-relocinfo.dat"], n, zd, bd, [x != KEIN for x in origin]),
        "common/etc/naps_meta_18.dat": si["naps_meta_18.dat"],
        "common/etc/naps_meta_300.dat": si["naps_meta_300.dat"],
        "common/etc/naps_meta_308.dat": si["naps_meta_308.dat"],
        "common/etc/naps_meta_301.dat": d301,
        "common/etc/naps_meta_302.dat": d302,
        "common/etc/naps_meta_304.dat": naps_304(origin, basis_n, lt.le32(bfih, 0x90)),
        "common/etc/playgo-chunk.dat": zcnt[0x1001],
        "common/etc/origin-playgo-chunk.dat": bcnt[0x1001],
        "common/etc/target-playgo-chunk.dat": bcnt[0x1001],
        f"config/{cid}/playgo-chunk.crc": si["playgo-chunk.crc"],
        # Forges SI-Zip traegt keine playgo-scenario.json; dann die des Ziel-Containers (0x3000, bei Sony derselbe Inhalt)
        f"config/{cid}/playgo-scenario.json": si.get("playgo-scenario.json", zcnt[0x3000]),
        f"config/{cid}/origin-playgo-scenario.json": bcnt[0x3000],
        f"config/{cid}/target-playgo-scenario.json": bcnt[0x3000],
    })
    # Zeitstempel der Zip-Teile: Sony nimmt pubtools.creationDate des Ziels; Forges param.json hat keinen, dann 2026-01-01.
    erstellt = (json.loads(zcnt[0x2000].decode("utf-8-sig")).get("pubtools") or {}).get("creationDate") or "2026-01-01 00:00:00"
    zipdaten = zip_bauen(mitglieder, *dos_zeit(erstellt))
    gesamt = cnt_at + len(zcnt_roh) + len(zipdaten)

    kopf = bytearray(BLOCK)
    kopf[0:4] = b"\x7fLIH"
    struct.pack_into("<HH", kopf, 4, 0, 1)
    struct.pack_into("<IIQ", kopf, 0x10, BLOCK, cnt_at // BLOCK, gesamt)
    struct.pack_into("<QQQQQQ", kopf, 0x20, BLOCK, BLOCK, cnt_at, len(zcnt_roh), cnt_at + len(zcnt_roh), len(zipdaten))
    with open(ziel_pfad, "rb") as z, open(aus_pfad + ".teil", "wb") as aus:
        aus.write(kopf)
        aus.write(zfih)
        for i in range(1, n):
            if origin[i] == KEIN:
                z.seek(i * BLOCK)
                aus.write(z.read(BLOCK))
        aus.write(zcnt_roh)
        aus.write(zipdaten)
    os.replace(aus_pfad + ".teil", aus_pfad)
    print(f"geschrieben: {aus_pfad} ({gesamt} Bytes; {patchbloecke - 1} Datenbloecke, {wieder} aus der Basis)")

    if "--vergleich" in opt:
        return vergleichen(aus_pfad, opt["--vergleich"])
    return 0


def vergleichen(neu_pfad: str, echt_pfad: str) -> int:
    gleich = True
    with open(neu_pfad, "rb") as a, open(echt_pfad, "rb") as b:
        # Bereiche nach dem Kopf des Originals; der eigene Kopf wird im ersten Bereich mitverglichen
        kb = b.read(BLOCK)
        bereiche_ = [("LIH-Kopf", 0, BLOCK), ("FIH", BLOCK, BLOCK)]
        ca, cs = struct.unpack_from("<QQ", kb, 0x30)
        za, zs = struct.unpack_from("<QQ", kb, 0x40)
        bereiche_ += [("Datenbloecke", 2 * BLOCK, ca - 2 * BLOCK), ("CNT", ca, cs), ("Zip", za, zs)]
        for name, off, laenge in bereiche_:
            a.seek(off)
            b.seek(off)
            ha, hb = hashlib.sha256(), hashlib.sha256()
            rest = laenge
            while rest:
                m = min(rest, 1 << 24)
                ha.update(a.read(m))
                hb.update(b.read(m))
                rest -= m
            ok = ha.digest() == hb.digest()
            gleich &= ok
            print(f"  [{'GLEICH' if ok else 'ANDERS'}]  {name} ({laenge} Bytes)")
        print("  Dateilaenge:", os.path.getsize(neu_pfad), "/", os.path.getsize(echt_pfad))
        gleich &= os.path.getsize(neu_pfad) == os.path.getsize(echt_pfad)
    if not gleich:
        zn, ze = si_quelle(neu_pfad), si_quelle(echt_pfad)
        for name in sorted(set(zn) | set(ze)):
            if zn.get(name) != ze.get(name):
                print(f"    Zip-Teil anders: {name}")
    print("Ergebnis:", "byte-gleich" if gleich else "Abweichungen")
    return 0 if gleich else 1


if __name__ == "__main__":
    if len(sys.argv) < 6 or "--si" not in sys.argv:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv))
