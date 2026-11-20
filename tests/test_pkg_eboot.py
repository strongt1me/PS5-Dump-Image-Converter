# -*- coding: utf-8 -*-
"""Das SDK der ``eboot.bin`` in einem ``.pkg`` (20.11.2026): ``pkg_eboot`` liest AES-XTS und Kraken-Bloecke wie Dump Forge.

Zuvor blieb ein ``.pkg`` "nicht zu sagen": Forge nennt das SDK der Programme nur bei einem Spiel mit ``fakelib/``, ein herabgesetztes Spiel
ohne ``fakelib/`` im Paket wurde nach der ``param.json`` beurteilt und zu Unrecht als BACKPORT-beduerftig beanstandet.

Geprueft wird hier

* die Schluessel-Ableitung und AES-128-XTS gegen Werte aus Forges eigenen Tests (``crypto.rs``, ``xts.rs``);
* die Bausteine des Kraken-Decoders gegen Forges Testwerte und gegen eine eigene Rechnung (Byte-Mischung);
* mit der **echten Forge-Befehlszeile** gebaute Pakete: das SDK (Original und herabgesetzt, Gegenprobe), jede Datei Byte fuer Byte
  zurueckgelesen (so laufen LZ-Haelften, Huffman-Felder und rohe Haelften durch den Decoder) und ein daraus selbst verschluesseltes
  Paket (AES-XTS), das Forge selbst gegenliest, damit das Testpaket nicht nur dem eigenen Leser gefaellt;
* das Verhalten bei allem, was sich nicht lesen laesst (kein Paket, PS4, Update, Verkaufsfassung, fremder Passcode, abgeschnitten).

Gemessen ausserhalb der Tests (20.11.2026, echte Pakete): Arkanoid (394 MB, Forge): 744 von 744 Dateien, zusammen 1 GB, Byte fuer Byte gleich
Forges Entpackung; LEGO Batman (34 GB, 450.835 Bloecke): SDK 12.00 = Forges ``backport_firmware``, Dateigroesse und Blockzahl gleich; ein
verschluesseltes DLC-Paket (zwei Kraken-Bloecke) liest sich bis in die Metadaten; ein Paket mit Verdichtung "QuickZ" lehnt Forge selbst ab -
hier ebenso ``""``.
"""
from __future__ import annotations

import bisect
import hashlib
import io
import json
import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))
sys.path.insert(0, str(PROJEKT / "tests"))

import pruefumgebung                                        # noqa: E402,F401
from ps5_validator.utils import forge_cli as fc             # noqa: E402
from ps5_validator.utils import pkg_eboot as pe             # noqa: E402
from ps5_validator.utils import programm_sdk as ps          # noqa: E402
from test_backport_erkennung_programme import als_self, baue_elf, herabgesetzt   # noqa: E402

_EXE = fc.werkzeug_suchen([str(PROJEKT)])
_PARAM = {"contentId": "EP9999-PPSA99999_00-TESTSPIEL0000001", "titleId": "PPSA99999", "contentVersion": "01.000.000",
          "masterVersion": "01.00", "applicationCategoryType": 0, "applicationDrmType": "standard",
          "conceptId": "100000", "requiredSystemSoftwareVersion": "0x1120000000000000",
          "sdkVersion": "0x1000000000000000",
          "localizedParameters": {"defaultLanguage": "en-US", "en-US": {"titleName": "Testspiel"}}}


def _sha3(daten: bytes) -> bytes:
    return hashlib.sha3_256(daten).digest()


def _bits(*teile: str) -> bytes:
    """Bitfolge MSB zuerst als Bytes, mit Nullen aufgefuellt."""
    text = "".join(teile)
    text += "0" * (-len(text) % 8)
    return bytes(int(text[i:i + 8], 2) for i in range(0, len(text), 8))


class SchluesselUndXtsTests(unittest.TestCase):
    """Bekannte Antwortwerte aus Forges ``crypto.rs`` und ``xts.rs``."""

    def test_schluesselableitung_wie_im_echten_dlc_paket(self) -> None:
        """Forges Test ``key_derivation_matches_real_package``: Werte aus hashlib/hmac fuer die Kennung und Saat eines echten Pakets."""
        saat = bytes([0x3a, 0xce, 0x52, 0x0f, 0x1d, 0xdb, 0xd3, 0xcb, 0x8a, 0xcb, 0xc4, 0x54, 0x3f, 0x95, 0xfb, 0xa6])
        schluessel = pe.schluessel_ableiten("EP7579-PPSA17599_00-EXP33DLC10000PS5", pe.STANDARD_PASSCODE, saat)
        daten, tweak = "66cb5805c75c915a157f8ab9ccb80cab", "04c9c2c17ea72b2be706be8ae56c9bff"
        self.assertEqual(bytes.fromhex(daten) + bytes.fromhex(tweak), schluessel, "Daten-Schluessel zuerst, dann der Tweak-Schluessel")

    def test_eine_andere_kennung_oder_ein_anderer_passcode_gibt_andere_schluessel(self) -> None:
        saat = bytes(range(16))
        basis = pe.schluessel_ableiten("EP7579-PPSA17599_00-EXP33DLC10000PS5", pe.STANDARD_PASSCODE, saat)
        self.assertNotEqual(basis, pe.schluessel_ableiten("EP7579-PPSA17599_00-EXP33DLC10000PS6", pe.STANDARD_PASSCODE, saat))
        self.assertNotEqual(basis, pe.schluessel_ableiten("EP7579-PPSA17599_00-EXP33DLC10000PS5", "1" * 32, saat))
        self.assertNotEqual(basis, pe.schluessel_ableiten("EP7579-PPSA17599_00-EXP33DLC10000PS5", pe.STANDARD_PASSCODE, bytes(16)))
        self.assertEqual(32, len(basis))

    def test_xts_wie_in_forges_test(self) -> None:
        """Forges Test ``full_block_data_and_signed_sectors``: Schluessel 0..15 (Daten) und 16..31 (Tweak), Klartext ``i * 7``, Sektor 5."""
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        schluessel = bytes(range(16)) + bytes(range(16, 32))
        klar = bytes((i * 7) & 0xFF for i in range(0x10000))
        for sektor, erste, pruefsumme in (
            (5, "7cd15324d71af9c318a1a7cd1cdf33e4", "4b08520fde76f492d305b9bf740a294a0ccd64cbbd3e2783aebdd06c9353c483"),
            (pe._SIGNIERT | 5, "20e0ed830c5b7fa7536743e0f93b91fb", "e4b131dcb9d6fadb69de4ff7b0737f3f519ec6e57b5119c2a3148b53f2e54d42"),
        ):
            with self.subTest(sektor=hex(sektor)):
                e = Cipher(algorithms.AES(schluessel), modes.XTS(struct.pack("<Q", sektor) + bytes(8))).encryptor()
                chiffre = e.update(klar) + e.finalize()
                self.assertEqual(erste, chiffre[:16].hex(), "die Bibliothek rechnet XTS wie Forge (Schluesselfolge, Tweak)")
                self.assertEqual(pruefsumme, _sha3(chiffre).hex())
                self.assertEqual(klar, pe._xts_entschluesseln(schluessel, sektor, chiffre))


class KrakenBausteineTests(unittest.TestCase):
    """Forges Testwerte (``kraken/huff.rs``) und die Byte-Mischung gegen eine eigene Rechnung."""

    def test_huffman_ein_symbol_verbraucht_den_ganzen_koerper(self) -> None:
        self.assertEqual(bytes(100), pe._huffman(bytes([0, 0x40, 0]), 100))
        self.assertEqual(b"\xab" * 100, pe._huffman(bytes([0, 0x6a, 0xc0]), 100))
        for kaputt in (bytes([0, 0x40]), bytes([0, 0x40, 0, 0])):
            with self.subTest(koerper=kaputt.hex()), self.assertRaises(pe.PaketFehler):
                pe._huffman(kaputt, 100)

    def test_eine_codelaenge_ueber_dem_laengsten_code_wird_abgelehnt(self) -> None:
        """Forges Test ``a_code_length_past_the_longest_is_refused``: alte Tabelle, dünn besetzt, zwei Symbole, 4-Bit-Laengen, 'A' mit Laenge 16."""
        koerper = _bits("0", "0", "00000010", "100", "01000001", "1111").ljust(16, b"\0")
        with self.assertRaises(pe.PaketFehler) as r:
            pe._huffman(koerper, 16)
        self.assertEqual("verfahren", r.exception.art)

    def test_felder_roh_mit_zwei_und_drei_byte_kopf(self) -> None:
        self.assertEqual((b"hello", 8), pe._feld(b"\x00\x00\x05hello", 0, 8, 100))
        self.assertEqual((b"hello", 7), pe._feld(b"\x80\x05hello", 0, 7, 100))
        self.assertEqual((b"llo", 6), pe._feld(b"xx\x00\x00\x03llo", 2, 8, 100), "ab einer Stelle mitten im Puffer")

    def test_felder_die_ueber_ihren_abschnitt_laufen_oder_zu_gross_sind_werden_abgelehnt(self) -> None:
        for q, ende, hoechstens in ((b"\x00\x00\x09hello", 8, 100), (b"\x00\x00\x05hello", 8, 4), (b"\x00", 1, 100), (b"\x30\x00\x00", 3, 100)):
            with self.subTest(q=q), self.assertRaises(pe.PaketFehler):
                pe._feld(q, 0, ende, hoechstens)

    def test_bitleser_vorwaerts_und_rueckwaerts(self) -> None:
        q = bytes([0xA5, 0x5A, 0xFF, 0x00, 0x12, 0x34])
        v = pe._BitLeser(q, 0, len(q), False)
        self.assertEqual((0xA, 0x5, 0x5A, 0xFF), (v.holen(4), v.holen(4), v.holen(8), v.holen(8)))
        r = pe._BitLeser(q, 0, len(q), True)
        self.assertEqual((0x34, 0x12), (r.holen(8), r.holen(8)), "rueckwaerts: das letzte Byte zuerst, MSB zuerst")
        self.assertEqual(0, pe._BitLeser(bytes([0xFF, 0xFF, 0xFF, 0xFF]), 0, 4, False).nullen())
        self.assertEqual(7, pe._BitLeser(bytes([0x01, 0x00, 0x00, 0x00]), 0, 4, False).nullen(), "sieben fuehrende Nullen vor dem ersten Bit")

    def test_die_mischung_ist_die_umkehrung_der_zerlegung_nach_feldern(self) -> None:
        """Gespeichert ist jede 64-KiB-Einheit nach Feldern zerlegt (erst das erste Feld aller Vektoren, dann das zweite ...); ein Rest bleibt."""
        zufall = random.Random(7)
        for muster, felder in enumerate(pe._MISCHUNGEN):
            if not felder:
                continue
            with self.subTest(muster=muster):
                schritt = sum(felder)
                original = bytes(zufall.randrange(256) for _ in range(0x10000 + 0x2345))
                gemischt = bytearray()
                for ab in range(0, len(original), pe._MISCHUNG_EINHEIT):
                    stueck = original[ab:ab + pe._MISCHUNG_EINHEIT]
                    n = len(stueck) // schritt
                    teil = bytearray()
                    off = 0
                    for f in felder:
                        for v in range(n):
                            teil += stueck[v * schritt + off:v * schritt + off + f]
                        off += f
                    teil += stueck[n * schritt:]
                    gemischt += teil
                heraus = bytearray(gemischt)
                pe._entmischen(heraus, muster)
                self.assertEqual(original, bytes(heraus))

    def test_ein_block_wird_nach_dem_entpacken_entmischt(self) -> None:
        """``_block_entpacken`` wendet die Mischung des Blocks an: ein roh abgelegter, gemischter Block kommt in Ordnung heraus."""
        zufall = random.Random(11)
        original = bytes(zufall.randrange(256) for _ in range(0x4000))
        for muster in (0, 3, 8):
            with self.subTest(muster=muster):
                felder = pe._MISCHUNGEN[muster]
                schritt = sum(felder) or 1
                n = len(original) // schritt
                gemischt = bytearray()
                off = 0
                for f in felder:
                    for v in range(n):
                        gemischt += original[v * schritt + off:v * schritt + off + f]
                    off += f
                gemischt += original[n * schritt:]
                b = pe._Beschrieben()
                b.logisch, b.laenge, b.abgelegt_ab, b.gerade_laenge, b.abgelegt_laenge = 0, len(original), 0, len(original), len(original)
                b.gerade_lz = b.ungerade_lz = False
                b.modus, b.mischung = 0, muster
                self.assertEqual(original, pe._block_entpacken(bytes(gemischt) if felder else original, b))

    def test_keine_mischung_laesst_die_bytes_und_eine_unbekannte_wird_abgelehnt(self) -> None:
        daten = bytearray(b"abcdef" * 100)
        pe._entmischen(daten, 0)
        self.assertEqual(b"abcdef" * 100, bytes(daten))
        with self.assertRaises(pe.PaketFehler):
            pe._entmischen(daten, 13)

    def test_die_form_der_beschreibung(self) -> None:
        """``mount.rs shape``: ``00 00 04`` vor den Saetzen heisst Kraken; sonst entscheidet die Laenge zwischen Kraken, flach und beidem."""
        dateien, ublocks, saetze = 3, 7, 4                  # 7 Einhaengebloecke: die flache Laenge ist kleiner als die Kraken-Laenge + Rest
        w0 = (dateien - 1) | 2 << 24 | ublocks << 32
        w1 = (saetze - 2) << 24
        fidx_ende = 16 + dateien * 6
        satz_ab = -(-(fidx_ende + (ublocks // 8 + 1) * 10) // 8) * 8 + 3
        flach_laenge = fidx_ende + (-(-ublocks // 8) + 1) * 10 + saetze * 9
        self.assertEqual((51, 90), (satz_ab, flach_laenge), "die Rechnung des Tests selbst")
        kopf = struct.pack("<QQ", w0, w1)

        def blob(laenge: int, marke: bytes) -> bytes:
            roh = bytearray(kopf + bytes(laenge - 16))
            roh[satz_ab - 3:satz_ab] = marke
            return bytes(roh)

        self.assertEqual("kraken", pe._form(blob(satz_ab + saetze * 9, b"\x00\x00\x04"), w0, w1), "die Marke 00 00 04 sagt es")
        self.assertEqual("kraken", pe._form(blob(flach_laenge, b"\x00\x00\x04"), w0, w1), "auch bei flacher Laenge")
        self.assertEqual("beides", pe._form(blob(flach_laenge, b"\x01\x02\x03"), w0, w1), "andere Marke, genau die flache Laenge: beides moeglich")
        self.assertEqual("kraken", pe._form(blob(flach_laenge + 5, b"\x01\x02\x03"), w0, w1), "andere Marke, laenger als flach: Kraken")
        self.assertEqual("flach", pe._form(blob(flach_laenge - 5, b"\x01\x02\x03"), w0, w1), "andere Marke und zu kurz fuer die Saetze: flach")
        self.assertEqual("flach", pe._form(kopf + bytes(10), w0, w1), "nicht einmal bis zur Marke: flach")


def _feld_roh(daten: bytes) -> bytes:
    """Ein rohes Feld (Art 0) mit dem Kopf zu drei Bytes."""
    n = len(daten)
    return bytes([(n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF]) + daten


def _lz_haelfte(saat: bytes, literale: bytes, befehle: bytes, codes: bytes, laengen: bytes, abstandsbits: bytes, *, skaliert: bool) -> bytes:
    """Eine LZ-Haelfte von Hand: Saat, Ueberlauf-Rahmung, vier rohe Felder, die Abstandsbits - so, wie ``kraken.rs`` sie beschreibt."""
    return saat + b"\x80" + _feld_roh(literale) + _feld_roh(befehle) + (b"\x80" if skaliert else b"") + _feld_roh(codes) + _feld_roh(laengen) + abstandsbits


def _bezug(saat: bytes, ergebnis_laenge: int, literale: bytes, befehle: "list[tuple[int, int, int, int]]", delta: bool) -> bytes:
    """Dieselbe Haelfte nach der Beschreibung Byte fuer Byte gerechnet (eigene, einfache Rechnung): Befehle ``(Literale, Art, Abstand, Treffer)``."""
    aus = bytearray(saat)
    lit_ab = 0
    letzter = 8
    for lit, _art, abstand, treffer in befehle:
        for j in range(lit):
            b = literale[lit_ab + j]
            aus.append((b + aus[len(aus) - letzter]) & 0xFF if delta else b)
        lit_ab += lit
        letzter = abstand
        for _ in range(treffer):
            aus.append(aus[len(aus) - abstand])
    for j in range(len(literale) - lit_ab):
        b = literale[lit_ab + j]
        aus.append((b + aus[len(aus) - letzter]) & 0xFF if delta else b)
    assert len(aus) == ergebnis_laenge
    return bytes(aus)


class LzHaelfteVonHandTests(unittest.TestCase):
    """``_lz_haelfte`` gegen von Hand gebaute Haelften - auch die Wege, die Forges Encoder heute nicht schreibt (skalierte Abstaende, Delta-Literale)."""

    SAAT = b"ABCDEFGH"

    def _lauf(self, haelfte: bytes, laenge: int, delta: bool = False) -> bytes:
        aus = bytearray(laenge)
        pe._lz_haelfte(haelfte, aus, 0, laenge, delta)
        return bytes(aus)

    def test_neuer_abstand_im_ueblichen_code(self) -> None:
        # Befehl: 2 Literale, neuer Abstand 8 (Art 3), Treffer 8 (Code 6); Abstandscode 0 + vier Nullbits; Rest: 6 Literale
        literale = b"xy123456"
        haelfte = _lz_haelfte(self.SAAT, literale, bytes([(3 << 6) | (6 << 2) | 2]), b"\x00", b"", b"\x00", skaliert=False)
        erwartet = _bezug(self.SAAT, 24, literale, [(2, 3, 8, 8)], delta=False)
        self.assertEqual(self.SAAT + b"xy" + b"CDEFGHxy" + b"123456", erwartet, "die Rechnung des Tests selbst")
        self.assertEqual(erwartet, self._lauf(haelfte, 24))

    def test_skalierter_abstand(self) -> None:
        """``0x80`` vor den Abstandscodes: Code ``(Bits << 3) | Rest`` mit Abstand ``((8 + Rest) << Bits | Bits-Wert) - 8`` (einmal von Forge geschrieben)."""
        # (Rest, Bits-Wert, Literale vor dem Treffer, Abstand): Abstand 8, 16 und 17
        for rest, bit, vorlauf, abstand in ((0, 0, 2, 8), (4, 0, 8, 16), (4, 1, 9, 17)):
            with self.subTest(abstand=abstand):
                self.assertEqual(abstand, (((8 + rest) << 1) | bit) - 8, "die Rechnung des Tests selbst")
                literale = bytes(range(0x61, 0x61 + vorlauf)) + b"12"
                lit_feld = vorlauf if vorlauf < 3 else 3                       # ab 3 Literalen steht die Laenge (3 + v) im Laengenfeld
                befehl = (3 << 6) | (6 << 2) | lit_feld
                laengen = b"" if vorlauf < 3 else bytes([vorlauf - 3])
                haelfte = _lz_haelfte(self.SAAT, literale, bytes([befehl]), bytes([(1 << 3) | rest]), laengen, bytes([bit << 7]), skaliert=True)
                erwartet = _bezug(self.SAAT, 8 + vorlauf + 8 + 2, literale, [(vorlauf, 3, abstand, 8)], delta=False)
                self.assertEqual(erwartet, self._lauf(haelfte, len(erwartet)))

    def test_wiederverwendeter_abstand_und_ueberlappender_treffer(self) -> None:
        """Befehl 1 setzt Abstand 8; Befehl 2 (Art 0 = zuletzt benutzter) kopiert 20 Bytes mit Abstand 8: die Kopie liest, was sie eben schrieb."""
        literale = b"xy"
        befehle = [(2, 3, 8, 8), (0, 0, 8, 20)]
        haelfte = _lz_haelfte(self.SAAT, literale, bytes([(3 << 6) | (6 << 2) | 2, (0 << 6) | (15 << 2) | 0]), b"\x00", b"\x03",
                              b"\x00", skaliert=False)
        erwartet = _bezug(self.SAAT, 8 + 2 + 8 + 20, literale, befehle, delta=False)
        self.assertEqual(erwartet, self._lauf(haelfte, len(erwartet)))

    def test_delta_literale_addieren_das_byte_im_letzten_abstand(self) -> None:
        literale = b"\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a"
        befehle = [(2, 3, 8, 8)]
        haelfte = _lz_haelfte(self.SAAT, literale, bytes([(3 << 6) | (6 << 2) | 2]), b"\x00", b"", b"\x00", skaliert=False)
        erwartet = _bezug(self.SAAT, 8 + 2 + 8 + 8, literale, befehle, delta=True)
        self.assertEqual(erwartet, self._lauf(haelfte, len(erwartet), delta=True))
        self.assertNotEqual(self._lauf(haelfte, len(erwartet), delta=False), erwartet, "ohne Delta kommt anderes heraus")

    def test_fehlerhafte_haelften_werden_abgelehnt(self) -> None:
        gut = _lz_haelfte(self.SAAT, b"xy123456", bytes([(3 << 6) | (6 << 2) | 2]), b"\x00", b"", b"\x00", skaliert=False)
        faelle = {
            "ohne_ueberlauf_rahmung": self.SAAT + b"\x00" + gut[9:],
            "zu_kurz": gut[:10],
            "abstand_zu_gross": _lz_haelfte(self.SAAT, b"xy123456", bytes([(3 << 6) | (6 << 2) | 2]), b"\xF0", b"", b"\x00", skaliert=False),
            "falsche_laenge": gut,
        }
        for name, haelfte in faelle.items():
            with self.subTest(fall=name), self.assertRaises(pe.PaketFehler):
                self._lauf(haelfte, 25 if name == "falsche_laenge" else 24)


def _spiel(ordner: Path, eboot: bytes, *, gross: bool = True) -> "dict[str, bytes]":
    """Ein kleines Spiel mit Daten, die Kraken verschieden stark verdichtet (Text, Nullen, Muster, Zufall); gibt die Dateien zurueck."""
    zufall = random.Random(20261120)
    text = (" ".join("wort%d" % zufall.randrange(400) for _ in range(60000))).encode()
    inhalte = {
        "eboot.bin": eboot,
        "sce_sys/param.json": json.dumps(_PARAM).encode("utf-8"),
        "daten/text.txt": text[:300_000] if gross else text[:5000],
        "daten/nullen.bin": bytes(400_000) if gross else bytes(3000),
        "daten/muster.bin": (bytes(range(256)) * 2000 + b"\x00\x01\x02" * 20000) if gross else bytes(range(256)) * 10,
        # Zufall verdichtet nicht: gross genug, dass das abgelegte Abbild mehr als zwoelf Aussenbloecke hat (dann stehen die Bloecke in einer
        # indirekten Tabelle) und ganze 256-KiB-Bloecke roh abgelegt sind
        "daten/zufall.bin": zufall.randbytes(1_000_000) if gross else zufall.randbytes(2000),
        "daten/klein.dat": b"x" * 7,
    }
    for rel, daten in inhalte.items():
        ziel = ordner / rel
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_bytes(daten)
    return inhalte


def _paket_bauen(spiel: Path, ziel: Path) -> None:
    erg = subprocess.run([_EXE, "convert", str(spiel), "--to", "pkg", "-o", str(ziel)], capture_output=True, text=True)
    if erg.returncode != 0:
        raise AssertionError("Forge baut das Testpaket nicht: " + (erg.stdout + erg.stderr)[-600:])


def _verschluesseln(paket: bytes, passcode: str = pe.STANDARD_PASSCODE, *, umgekehrt: bool = False) -> bytes:
    """Aus einem Klartext-Paket (Forge) ein AES-XTS-Paket machen: Saat in den Oberblock, ICV und Spiel-Pruefsumme neu, alle anderen Aussenbloecke
    mit XTS verschluesseln (Sektor = Index vor dem Oberblock, danach mit Bit 47). Die imagedigs bleiben, sie gelten dem Klartext.

    ``umgekehrt``: die andere Lesart (Bit 47 vor dem Oberblock, danach der Index) - so signiert Sony einige Bloecke vor dem Oberblock."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    p = bytearray(paket)
    pfs_ab, pfs_gr, ober_abs, cnt_ab = struct.unpack_from("<Q", p, 0x10)[0], struct.unpack_from("<Q", p, 0x18)[0], \
        struct.unpack_from("<Q", p, 0x20)[0], struct.unpack_from("<Q", p, 0x58)[0]
    ober = (ober_abs - pfs_ab) // pe.BLOCK
    kennung = bytes(p[cnt_ab + 0x40:cnt_ab + 0x64]).split(b"\0")[0].decode()
    saat = bytes(range(0xA0, 0xB0))
    block = bytearray(p[ober_abs:ober_abs + pe.BLOCK])
    block[0x370:0x380] = saat
    pruef = bytearray(block[:0x5A0])
    pruef[0x380:0x3A0] = bytes(32)
    block[0x380:0x3A0] = _sha3(bytes(pruef))
    schluessel = pe.schluessel_ableiten(kennung, passcode, saat)
    for i in range(pfs_gr // pe.BLOCK):
        ab = pfs_ab + i * pe.BLOCK
        if i == ober:
            p[ab:ab + pe.BLOCK] = block
            continue
        sektor = i if i < ober else (1 << 47) | i
        if umgekehrt:
            sektor = (1 << 47) | i if i < ober else i
        e = Cipher(algorithms.AES(schluessel), modes.XTS(struct.pack("<Q", sektor) + bytes(8))).encryptor()
        p[ab:ab + pe.BLOCK] = e.update(bytes(p[ab:ab + pe.BLOCK])) + e.finalize()
    p[0x30:0x50] = _sha3(bytes(block))
    # Der Oberblock steht unveraendert (nicht verschluesselt) im Abbild, seine imagedigs-Pruefsumme (byteverkehrt) gilt aber dem neuen Inhalt.
    pruefsummen = pe._behaelter_lesen(pe._Paket(io.BytesIO(paket)), cnt_ab).eintrag(pe._ID_BILDPRUEFSUMMEN)
    p[pruefsummen[0] + ober * 32:pruefsummen[0] + ober * 32 + 32] = bytes(reversed(_sha3(bytes(block))))
    return bytes(p)


def _beschreibung_aendern(paket: bytes, aendern) -> bytes:
    """Ein Klartext-Paket, dessen Beschreibung (``naps_pkg_layout.dat``) ``aendern(blob_bytes)`` im ersten Aussenblock umschreibt; die imagedigs-Pruefsumme
    des Blocks wird nachgezogen. ``aendern`` bekommt das ``bytearray`` des Blocks (die Beschreibung beginnt an dessen Anfang)."""
    with io.BytesIO(paket) as fh:
        nr = pe._beschreibungsdatei(pe._aussenwelt(fh, pe.STANDARD_PASSCODE)).blocknummer(0)
    return _aussenblock_aendern(paket, nr, aendern)


def _aussenblock_aendern(paket: bytes, nr: int, aendern) -> bytes:
    """Ein Klartext-Paket, dessen Aussenblock ``nr`` ``aendern(bytearray)`` umschreibt; die imagedigs-Pruefsumme des Blocks wird nachgezogen."""
    p = bytearray(paket)
    pfs_ab, cnt_ab = struct.unpack_from("<Q", p, 0x10)[0], struct.unpack_from("<Q", p, 0x58)[0]
    ab = pfs_ab + nr * pe.BLOCK
    block = bytearray(p[ab:ab + pe.BLOCK])
    aendern(block)
    p[ab:ab + pe.BLOCK] = block
    pruefsummen = pe._behaelter_lesen(pe._Paket(io.BytesIO(paket)), cnt_ab).eintrag(pe._ID_BILDPRUEFSUMMEN)
    p[pruefsummen[0] + nr * 32:pruefsummen[0] + nr * 32 + 32] = bytes(reversed(_sha3(bytes(block))))
    return bytes(p)


def _marke_ab(block: bytes) -> int:
    """Wo in der Beschreibung die drei Bytes vor den Saetzen stehen (``00 00 04``) - gerechnet wie ``mount.rs shape``."""
    w0, w1 = struct.unpack_from("<QQ", block, 0)
    dateien, mischung, ublocks, aussen = (w0 & 0xFFFFFF) + 1, (w0 >> 28) & 0xF, (w0 >> 32) & 0xFFFFFF, w1 & 0xFFFFFF
    fidx_ende = 16 + (aussen + mischung) * 8 + dateien * 6
    return -(-(fidx_ende + (ublocks // 8 + 1) * 10) // 8) * 8


@unittest.skipUnless(_EXE, "fuer diese Plattform liegt keine Dump-Forge-Befehlszeile bei")
class MitEchterForgeBefehlszeileTests(unittest.TestCase):
    """Pakete, die Dump Forge selbst baut (Kraken, Klartext-Abbild) - und daraus ein verschluesseltes."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._temp.cleanup)
        cls.ordner = Path(cls._temp.name)
        cls.pakete: "dict[str, str]" = {}
        cls.inhalte: "dict[str, bytes]" = {}
        for name, elf in (("orig", als_self(baue_elf(0x10000038, davor=0x180000))), ("tief", herabgesetzt(baue_elf(0x10000038, davor=0x180000), 7)),
                          ("nah", herabgesetzt(baue_elf(0x10000038), 5))):
            spiel = cls.ordner / ("spiel_" + name)
            inhalte = _spiel(spiel, elf)
            if name == "orig":
                cls.inhalte = inhalte
            ziel = cls.ordner / (name + ".pkg")
            _paket_bauen(spiel, ziel)
            cls.pakete[name] = str(ziel)

    def test_das_sdk_wird_gelesen_original_und_herabgesetzt(self) -> None:
        for name, erwartet in (("orig", "10.00"), ("tief", "7.00"), ("nah", "5.00")):
            with self.subTest(paket=name):
                self.assertEqual(erwartet, pe.eboot_sdk(self.pakete[name]))
                self.assertEqual(erwartet, ps.eboot_sdk(self.pakete[name]), "``programm_sdk.eboot_sdk`` nimmt ein .pkg auch")
                self.assertEqual(erwartet, fc.quellfakten({}, self.pakete[name]).eboot_sdk)

    def test_jede_datei_kommt_byte_fuer_byte_zurueck(self) -> None:
        with open(self.pakete["orig"], "rb") as fh:
            inneres = pe.oeffnen(fh)
            for rel, daten in self.inhalte.items():
                if rel in ("sce_sys/param.json", "eboot.bin"):
                    # die param.json schreibt Forge auch in den Behaelter; die eboot.bin baut es um (PS5-SELF-Kopf statt der PS4-Kennung
                    # des Testprogramms) - ihr SDK prueft ``test_das_sdk_wird_gelesen_...``, ihre Gleichheit mit Forges Entpackung die Messung
                    # an Arkanoid (26 MB, Byte fuer Byte gleich)
                    continue
                with self.subTest(datei=rel):
                    stelle = inneres.datei(rel)
                    self.assertIsNotNone(stelle, rel)
                    self.assertEqual(len(daten), stelle[1])
                    self.assertEqual(daten, inneres.lesen(rel, 0, len(daten)))

    def test_ein_bereich_mitten_in_einer_datei_und_ueber_blockgrenzen(self) -> None:
        daten = self.inhalte["daten/text.txt"]
        with open(self.pakete["orig"], "rb") as fh:
            inneres = pe.oeffnen(fh)
            for ab, n in ((0, 10), (123_456, 4000), (len(daten) - 17, 17), (0x3FFF0, 0x40), (len(daten) - 5, 100)):
                with self.subTest(ab=ab, n=n):
                    self.assertEqual(daten[ab:ab + n], inneres.lesen("daten/text.txt", ab, n))
            self.assertEqual(b"", inneres.lesen("daten/text.txt", len(daten) + 10, 10))

    def test_ein_kleiner_bereich_entpackt_nur_die_bloecke_die_er_beruehrt(self) -> None:
        """Bei einem Spiel von 100 GB zaehlt jeder Block: Ein Bereich am Anfang einer Datei (immer ein Blockanfang) braucht genau einen Block,
        einer ueber eine Blockgrenze zwei - nicht den davor."""
        from unittest import mock
        with open(self.pakete["orig"], "rb") as fh:
            inneres = pe.oeffnen(fh)
            logisch, _g = inneres.datei("daten/muster.bin")
            punkt = inneres.punkt                              # unmittelbar der Einhaengepunkt: ohne die Metadaten-Bloecke von ``datei``
            i = bisect.bisect_right(punkt._starts, logisch) - 1
            self.assertEqual(logisch, punkt.bloecke[i].logisch, "Vorbedingung: die Datei beginnt an einem Blockanfang")
            grenze = punkt.bloecke[i].laenge
            with mock.patch.object(pe, "_block_entpacken", wraps=pe._block_entpacken) as zaehler:
                punkt._zwischen.clear()
                punkt.lesen(logisch, 100)
                self.assertEqual(1, zaehler.call_count, "ein Bereich am Blockanfang: nur sein Block, nicht der davor")
                zaehler.reset_mock()
                punkt._zwischen.clear()
                punkt.lesen(logisch + grenze - 10, 20)
                self.assertEqual(2, zaehler.call_count, "ueber eine Blockgrenze: zwei Bloecke")

    def test_es_sind_mehrere_bloecke_und_alle_arten_gewesen(self) -> None:
        """Der Aufbau der Testdaten fuehrt durch LZ-Haelften, Huffman-Felder und rohe Haelften - sonst waere das Rundreisen oben zu schwach."""
        with open(self.pakete["orig"], "rb") as fh:
            inneres = pe.oeffnen(fh)
            bloecke = inneres.punkt.bloecke
        self.assertGreater(len(bloecke), 4)
        self.assertTrue(any(b.gerade_lz for b in bloecke), "LZ-Haelften")
        self.assertTrue(any(not b.gerade_lz and b.abgelegt_laenge == b.laenge for b in bloecke), "ganz roh abgelegte Bloecke (Zufall)")
        gesehen: "set[str]" = set()
        orig_feld = pe._feld

        def zaehlen(q, ab, ende, hoechstens):
            gesehen.add("huffman" if (q[ab] >> 4) & 7 == 2 else "roh")
            return orig_feld(q, ab, ende, hoechstens)

        from unittest import mock
        with mock.patch.object(pe, "_feld", side_effect=zaehlen), open(self.pakete["orig"], "rb") as fh:
            inneres = pe.oeffnen(fh)
            for rel in ("daten/text.txt", "daten/muster.bin", "daten/nullen.bin"):
                inneres.lesen(rel, 0, len(self.inhalte[rel]))
        self.assertEqual({"huffman", "roh"}, gesehen)

    def test_quellfakten_gegenprobe_ein_herabgesetztes_paket_wird_nicht_beanstandet_das_original_schon(self) -> None:
        """Die Luecke: ein ``.pkg`` ohne ``fakelib/``, dessen Programme herabgesetzt sind (die ``param.json`` verlangt noch 10.00/11.20)."""
        tief = fc.quellfakten_lesen(_EXE, self.pakete["tief"])
        orig = fc.quellfakten_lesen(_EXE, self.pakete["orig"])
        self.assertIsNotNone(tief)
        self.assertIsNotNone(orig)
        self.assertEqual(("10.00", "11.20", ""), (tief.sdk, tief.firmware, tief.backport_firmware), "Forge sieht hier nur die param.json")
        self.assertEqual("7.00", tief.eboot_sdk)
        self.assertTrue(tief.herabgesetzt)
        self.assertFalse(tief.backport_noetig("9.99"))
        self.assertTrue(tief.backport_schon_da("9.99"))
        self.assertEqual("10.00", orig.eboot_sdk)
        self.assertFalse(orig.herabgesetzt)
        self.assertTrue(orig.backport_noetig("9.99"), "ein unveraendertes Spiel wird weiter beanstandet")

    def test_ein_verschluesseltes_paket_wird_gelesen_und_forge_liest_es_auch(self) -> None:
        nativ = os.path.join(self.ordner, "nativ.pkg")
        Path(nativ).write_bytes(_verschluesseln(Path(self.pakete["tief"]).read_bytes()))
        erg = subprocess.run([_EXE, "inspect", nativ, "--json"], capture_output=True, text=True)
        self.assertEqual(0, erg.returncode, "Forge liest das Testpaket - sonst taugt es als Gegenprobe nicht: " + erg.stderr[-300:])
        self.assertTrue(any("native AES-XTS" in z for z in json.loads(erg.stdout)["details"]), "und sieht es als verschluesselt")
        self.assertEqual("7.00", pe.eboot_sdk(nativ))
        with open(nativ, "rb") as fh:
            inneres = pe.oeffnen(fh)
            for rel in ("daten/text.txt", "daten/zufall.bin"):
                self.assertEqual(self.inhalte[rel], inneres.lesen(rel, 0, len(self.inhalte[rel])), rel)

    def test_auch_die_andere_sektor_lesart_wird_gelesen(self) -> None:
        """Sony signiert einige Bloecke schon vor dem Oberblock: der Leser probiert beide Sektoren und nimmt den, dessen Pruefsumme passt."""
        nativ = os.path.join(self.ordner, "nativ_umgekehrt.pkg")
        Path(nativ).write_bytes(_verschluesseln(Path(self.pakete["tief"]).read_bytes(), umgekehrt=True))
        self.assertEqual("7.00", pe.eboot_sdk(nativ))
        with open(nativ, "rb") as fh:
            inneres = pe.oeffnen(fh)
            self.assertEqual(self.inhalte["daten/text.txt"], inneres.lesen("daten/text.txt", 0, len(self.inhalte["daten/text.txt"])))

    def test_ein_anderes_verdichtungsverfahren_wird_abgelehnt_wie_bei_forge(self) -> None:
        """Alan Wake Remastered (40 GB) meldet Verdichtung 0 (QuickZ): Forge lehnt es ab (``unsupported codec``), das Programm sagt ``""``."""
        original = Path(self.pakete["tief"]).read_bytes()
        self.assertEqual("7.00", pe.eboot_sdk(self.pakete["tief"]), "Vorbedingung: das unveraenderte Paket liest sich")
        for wert in (0, 1, 3):
            with self.subTest(verdichtung=wert):
                ziel = os.path.join(self.ordner, "verdichtung_%d.pkg" % wert)
                Path(ziel).write_bytes(_beschreibung_aendern(original, lambda b, w=wert: b.__setitem__(3, (b[3] & ~3) | w)))
                self.assertEqual("", pe.eboot_sdk(ziel))
                with open(ziel, "rb") as fh, self.assertRaises(pe.PaketFehler) as r:
                    pe.oeffnen(fh)
                self.assertEqual("verfahren", r.exception.art)
                self.assertIn("Verdichtung %d" % wert, str(r.exception))
                erg = subprocess.run([_EXE, "inspect", ziel, "--json"], capture_output=True, text=True)
                self.assertNotEqual(0, erg.returncode, "Forge lehnt es ebenfalls ab: " + erg.stderr[-200:])
                self.assertIn("unsupported codec", erg.stderr)

    def test_eine_andere_marke_vor_den_saetzen_wird_ohne_die_strengen_pruefungen_gelesen(self) -> None:
        """Fremde Bauwerkzeuge schreiben dort ``00 00 55`` oder ``00 00 06``; ihre Bloecke liegen wie die der anderen."""
        original = Path(self.pakete["tief"]).read_bytes()

        def umschreiben(block: bytearray) -> None:
            ab = _marke_ab(bytes(block))
            self.assertEqual(b"\x00\x00\x04", bytes(block[ab:ab + 3]), "Vorbedingung: Forge schreibt 00 00 04")
            block[ab:ab + 3] = b"\x00\x00\x55"

        ziel = os.path.join(self.ordner, "marke55.pkg")
        Path(ziel).write_bytes(_beschreibung_aendern(original, umschreiben))
        self.assertEqual("7.00", pe.eboot_sdk(ziel))
        with open(ziel, "rb") as fh:
            inneres = pe.oeffnen(fh)
            self.assertEqual(self.inhalte["daten/muster.bin"], inneres.lesen("daten/muster.bin", 0, len(self.inhalte["daten/muster.bin"])))

    def _zufallsstelle(self) -> "tuple[int, int]":
        """``(Stelle im Paket, Stelle in zufall.bin)`` eines Bytes in roh abgelegten Daten von ``zufall.bin`` (Zufall verdichtet nicht)."""
        in_datei = 600_000
        with open(self.pakete["orig"], "rb") as fh:
            inneres = pe.oeffnen(fh)
            logisch, _groesse = inneres.datei("daten/zufall.bin")
            punkt = inneres.punkt
            b = punkt.bloecke[bisect.bisect_right(punkt._starts, logisch + in_datei) - 1]
            self.assertEqual(b.laenge, b.abgelegt_laenge, "Vorbedingung: der Block liegt roh, byteweise wie die Datei")
            ab = b.abgelegt_ab + (logisch + in_datei - b.logisch)
            nr = punkt.bild.blocknummer(ab // pe.BLOCK)
        pfs_ab = struct.unpack_from("<Q", Path(self.pakete["orig"]).read_bytes()[:0x20], 0x10)[0]
        return pfs_ab + nr * pe.BLOCK + ab % pe.BLOCK, in_datei

    def test_ein_veraendertes_byte_in_rohen_daten_wird_von_der_pruefsumme_bemerkt(self) -> None:
        """Roh abgelegte Daten haben keine Struktur, die ein Fehler stoert: Nur die imagedigs-Pruefsumme des Aussenblocks verraet ihn."""
        voll = bytearray(Path(self.pakete["orig"]).read_bytes())
        stelle, in_datei = self._zufallsstelle()
        voll[stelle] ^= 0x01
        ziel = os.path.join(self.ordner, "zufall_verfaelscht.pkg")
        Path(ziel).write_bytes(bytes(voll))
        with open(ziel, "rb") as fh:
            inneres = pe.oeffnen(fh)
            with self.assertRaises(pe.PaketFehler) as r:
                inneres.lesen("daten/zufall.bin", in_datei - 10, 100)
            self.assertEqual("beschaedigt", r.exception.art)
        with open(self.pakete["orig"], "rb") as fh:
            self.assertEqual(self.inhalte["daten/zufall.bin"][in_datei - 10:in_datei + 90], pe.oeffnen(fh).lesen("daten/zufall.bin", in_datei - 10, 100))

    def test_die_bloecke_hinter_den_zwoelf_direkten_stehen_in_einer_tabelle_die_geprueft_wird(self) -> None:
        original = Path(self.pakete["orig"]).read_bytes()
        with io.BytesIO(original) as fh:
            welt = pe._aussenwelt(fh, pe.STANDARD_PASSCODE)
            uroot = welt.kind(0, "uroot")
            dinode = welt.knoten[welt.kind(uroot, "pfs_image.dat")]
        _digest, tabelle = dinode.indirekt[0]
        self.assertNotEqual(0, tabelle, "Vorbedingung: das abgelegte Abbild hat mehr als zwoelf Bloecke")
        with open(self.pakete["orig"], "rb") as fh:
            bild = pe.oeffnen(fh).punkt.bild
            self.assertGreater(bild.noetig, 16, "Vorbedingung: Block 15 gibt es")
            erst = [bild.blocknummer(k) for k in range(bild.noetig)]
        self.assertEqual(len(set(erst)), len(erst), "jeder Block des Abbilds liegt in einem eigenen Aussenblock")
        # ein Zeiger der Tabelle (Platz 3 = Block 15 der Datei) wird veraendert und die imagedigs-Pruefsumme des Tabellenblocks nachgezogen:
        # nur der Eintrag der Tabelle im Dinode (``derzeit digest``) verraet es noch
        kaputt = _aussenblock_aendern(original, tabelle, lambda b: b.__setitem__(slice(3 * 36 + 32, 3 * 36 + 33), bytes([b[3 * 36 + 32] ^ 1])))
        ziel = os.path.join(self.ordner, "tabelle_verfaelscht.pkg")
        Path(ziel).write_bytes(kaputt)
        # schon das Oeffnen stoesst darauf: die Metadaten liegen am Ende des Abbilds, hinter der Tabelle
        with open(ziel, "rb") as fh, self.assertRaises(pe.PaketFehler) as r:
            pe.oeffnen(fh)
        self.assertEqual("beschaedigt", r.exception.art)
        self.assertIn("Blocktabelle", str(r.exception))
        self.assertEqual("", pe.eboot_sdk(ziel))

    def test_strenge_pruefung_nur_bei_der_ueblichen_marke(self) -> None:
        """Bei ``00 00 04`` muss das Nibble, das ein Satz fuer den naechsten traegt, zum Anfang des Blocks passen; fremde Marken lassen das offen."""
        original = Path(self.pakete["tief"]).read_bytes()

        def nibble_setzen(block: bytearray) -> None:
            ab = _marke_ab(bytes(block)) + 3
            block[ab + 8] = (block[ab + 8] & 0x0F) | 0x50            # Satz 0 (Anker): Nibble 5 statt 0

        def marke_und_nibble(block: bytearray) -> None:
            ab = _marke_ab(bytes(block))
            block[ab:ab + 3] = b"\x00\x00\x55"
            nibble_setzen(block)

        streng = os.path.join(self.ordner, "nibble_streng.pkg")
        Path(streng).write_bytes(_beschreibung_aendern(original, nibble_setzen))
        with open(streng, "rb") as fh, self.assertRaises(pe.PaketFehler) as r:
            pe.oeffnen(fh)
        self.assertEqual("beschaedigt", r.exception.art)
        self.assertIn("Nibble", str(r.exception))
        self.assertEqual("", pe.eboot_sdk(streng))
        locker = os.path.join(self.ordner, "nibble_locker.pkg")
        Path(locker).write_bytes(_beschreibung_aendern(original, marke_und_nibble))
        self.assertEqual("7.00", pe.eboot_sdk(locker))

    def test_ein_fremder_passcode_ergibt_nichts(self) -> None:
        nativ = os.path.join(self.ordner, "nativ_fremd.pkg")
        Path(nativ).write_bytes(_verschluesseln(Path(self.pakete["tief"]).read_bytes(), "1" * 32))
        self.assertEqual("", pe.eboot_sdk(nativ), "mit dem Vorgabe-Passcode nicht zu lesen")
        with open(nativ, "rb") as fh, self.assertRaises(pe.PaketFehler) as r:
            pe.oeffnen(fh)
        self.assertEqual("passcode", r.exception.art)
        self.assertEqual("7.00", pe.eboot_sdk(nativ, "1" * 32), "mit dem richtigen Passcode schon")

    def test_ein_abgeschnittenes_oder_beschaedigtes_paket_ergibt_nichts(self) -> None:
        voll = Path(self.pakete["orig"]).read_bytes()
        for name, daten in (("halb", voll[:len(voll) // 2]), ("kopf", voll[:0x200]), ("ohne_ende", voll[:-70_000])):
            with self.subTest(fall=name):
                ziel = os.path.join(self.ordner, "kaputt_%s.pkg" % name)
                Path(ziel).write_bytes(daten)
                self.assertEqual("", pe.eboot_sdk(ziel))
        zerstoert = bytearray(voll)
        ab = struct.unpack_from("<Q", zerstoert, 0x10)[0] + 5 * pe.BLOCK
        zerstoert[ab + 100:ab + 164] = bytes(64)             # ein Aussenblock, dessen Pruefsumme nicht mehr passt
        ziel = os.path.join(self.ordner, "kaputt_block.pkg")
        Path(ziel).write_bytes(bytes(zerstoert))
        with open(ziel, "rb") as fh:
            try:
                inneres = pe.oeffnen(fh)
                for rel in self.inhalte:
                    if rel != "sce_sys/param.json" and inneres.datei(rel):
                        inneres.lesen(rel, 0, len(self.inhalte[rel]))
            except pe.PaketFehler as fehler:
                self.assertEqual("beschaedigt", fehler.art)
            else:
                self.fail("der beschaedigte Aussenblock blieb unbemerkt")


class DateisucheTests(unittest.TestCase):
    """``_Inneres.datei`` ueber einem Stand-in der Verzeichnisse (ohne Paket)."""

    def _inneres(self) -> "pe._Inneres":
        regal = {4: [(10, 2, "EBOOT.BIN"), (11, 3, "sce_sys"), (12, 2, "readme.txt")], 11: [(13, 2, "Param.JSON")]}
        inodes = {10: (0x81A4, 100, 0x1000), 11: (0x41ED, 0, 0), 12: (0x81A4, 5, 0x2000), 13: (0x81A4, 40, 0x3000)}

        class Attrappe(pe._Inneres):
            def __init__(self) -> None:
                self.meta_basis = 1 << 40

            def verzeichnis(self, nr):
                return regal[nr]

            def inode(self, nr):
                return inodes[nr]

        return Attrappe()

    def test_genau_geschrieben_und_gleich_gross(self) -> None:
        inneres = self._inneres()
        self.assertIsNone(inneres.datei("eboot.bin"), "die Schreibung muss stimmen ...")
        self.assertEqual((0x1000, 100), inneres.datei("eboot.bin", True), "... ausser es soll gleich gross gelten")
        self.assertEqual((0x2000, 5), inneres.datei("readme.txt"))
        self.assertEqual((0x3000, 40), inneres.datei("sce_sys/param.json", True))
        self.assertIsNone(inneres.datei("sce_sys/param.json"))

    def test_ordner_und_fehlendes(self) -> None:
        inneres = self._inneres()
        self.assertIsNone(inneres.datei("sce_sys", True), "ein Ordner ist keine Datei")
        self.assertIsNone(inneres.datei("gibt_es_nicht", True))
        self.assertIsNone(inneres.datei("readme.txt/unter", True), "unter einer Datei gibt es nichts")
        self.assertIsNone(inneres.datei("", True))


class NichtLesbaresTests(unittest.TestCase):
    """Alles, was kein lesbares Debug-Paket ist, ergibt ``""`` - mit der richtigen Art im Fehler, ohne Ausnahme nach aussen."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="pkgeboot_")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _datei(self, name: str, daten: bytes) -> str:
        pfad = os.path.join(self.tmp, name)
        Path(pfad).write_bytes(daten)
        return pfad

    def _art(self, pfad: str) -> str:
        with open(pfad, "rb") as fh, self.assertRaises(pe.PaketFehler) as r:
            pe.oeffnen(fh)
        return r.exception.art

    def test_kein_paket(self) -> None:
        for name, daten in (("leer.pkg", b""), ("kurz.pkg", b"\x7fFIH" + bytes(20)), ("zufall.pkg", os.urandom(300_000)),
                            ("text.pkg", b"hallo " * 10000)):
            with self.subTest(datei=name):
                pfad = self._datei(name, daten)
                self.assertEqual("", pe.eboot_sdk(pfad))
                self.assertEqual("", ps.eboot_sdk(pfad))
                self.assertEqual("kein-ps5", self._art(pfad))

    def test_ps4_update_und_verkaufsfassung(self) -> None:
        kopf = bytearray(0x100)
        self.assertEqual("kein-ps5", self._art(self._datei("ps4.pkg", b"\x7fCNT" + bytes(0x2000))))
        self.assertEqual("update", self._art(self._datei("update.pkg", b"\x7fLIH" + bytes(0x2000))))
        kopf[:4] = b"\x7fFIH"
        kopf[5] = 0x80
        pfad = self._datei("verkauf.pkg", bytes(kopf) + bytes(0x2000))
        self.assertEqual("verkauf", self._art(pfad))
        self.assertEqual("", pe.eboot_sdk(pfad))

    def test_ein_paket_mit_widerspruechlichem_kopf_ist_beschaedigt(self) -> None:
        for name, aendern in (("pfs_ab", lambda k: struct.pack_into("<Q", k, 0x10, 0x123)),
                              ("pfs_groesse", lambda k: struct.pack_into("<Q", k, 0x18, 0x12345)),
                              ("zu_gross", lambda k: struct.pack_into("<Q", k, 0x18, 1 << 40)),
                              ("blockgroesse", lambda k: struct.pack_into("<Q", k, 0x60, 0x1000))):
            with self.subTest(feld=name):
                kopf = bytearray(0x100)
                kopf[:4] = b"\x7fFIH"
                struct.pack_into("<Q", kopf, 0x10, 0x10000)
                struct.pack_into("<Q", kopf, 0x18, 0x10000)
                struct.pack_into("<Q", kopf, 0x20, 0x10000)
                struct.pack_into("<Q", kopf, 0x58, 0x20000)
                struct.pack_into("<Q", kopf, 0x60, 0x10000)
                aendern(kopf)
                pfad = self._datei("k_%s.pkg" % name, bytes(kopf).ljust(0x40000, b"\0"))
                self.assertEqual("beschaedigt", self._art(pfad))
                self.assertEqual("", pe.eboot_sdk(pfad))

    def test_fehlende_datei_und_endungen(self) -> None:
        self.assertEqual("", pe.eboot_sdk(os.path.join(self.tmp, "gibt_es_nicht.pkg")))
        self.assertEqual("", ps.eboot_sdk(os.path.join(self.tmp, "gibt_es_nicht.pkg")))

    def test_unerwartete_fehler_beim_lesen_ergeben_nichts(self) -> None:
        from unittest import mock
        pfad = self._datei("x.pkg", b"\x7fFIH" + bytes(0x400))
        for fehler in (OSError("x"), ValueError("x"), struct.error("x"), KeyError("x"), IndexError("x"), OverflowError("x"), ImportError("x"), MemoryError()):
            with self.subTest(fehler=type(fehler).__name__), mock.patch.object(pe, "oeffnen", side_effect=fehler):
                self.assertEqual("", pe.eboot_sdk(pfad))


if __name__ == "__main__":
    unittest.main()
