# -*- coding: utf-8 -*-
"""Tests fuer das Lesen des Paketkopfs (``bibliothek_paket``): ``.pkg`` und ``.fpkg`` ohne die Datei zu laden.

Die Pakete entstehen hier im Test: ein CNT-Kopf von 0x5A0 Byte, die Eintragstabelle und ein paar Eintraege - wie
sie an echten PS4-Paketen der Festplatte gemessen wurden (Magic, Zahl und Lage der Tabelle, ``param.sfo`` und
``icon0.png`` unverschluesselt). Geprueft wird, was gelesen wird, was nicht, und dass nie die ganze Datei geladen wird.
"""
from __future__ import annotations

import builtins
import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ps5_validator.utils import bibliothek_paket as bp

CONTENT_ID = "EP0001-CUSA00775_00-TETRISGAME000000"
SFO = b"\x00PSF" + b"s" * 200
ICON = b"\x89PNG\r\n\x1a\n" + b"i" * 300


def _cnt(eintraege: dict[int, bytes], *, content_id: str = CONTENT_ID, verschluesselt: tuple[int, ...] = (),
         anzahl: int | None = None, tabelle: int = bp.KOPF_GROESSE) -> bytes:
    """Ein Paket aus Kopf, Tabelle und Eintraegen - Lagen gelten ab dem Anfang des Kopfs."""
    n = len(eintraege)
    kopf = bytearray(bp.KOPF_GROESSE)
    kopf[0:4] = bp.CNT_MAGIC
    struct.pack_into(">I", kopf, 0x10, n if anzahl is None else anzahl)
    struct.pack_into(">I", kopf, 0x18, tabelle)
    kopf[0x40:0x40 + len(content_id)] = content_id.encode("ascii")
    daten_ab = bp.KOPF_GROESSE + n * bp.EINTRAG_GROESSE
    zeilen, daten, lage = [], b"", daten_ab
    for kennung, inhalt in eintraege.items():
        flags = bp.EINTRAG_VERSCHLUESSELT if kennung in verschluesselt else 0
        zeilen.append(struct.pack(">IIIIII8x", kennung, 0, flags, 0, lage, len(inhalt)))
        daten += inhalt
        lage += len(inhalt)
    return bytes(kopf) + b"".join(zeilen) + daten


def _fih(cnt: bytes, basis: int = 0x10000) -> bytes:
    """Ein FIH-Abbild: Kopf mit der Lage des eingebetteten CNT bei +0x58, dahinter das CNT bei ``basis``."""
    kopf = bytearray(0x100)
    kopf[0:4] = bp.FIH_MAGIC
    kopf[5] = 0x80
    struct.pack_into("<Q", kopf, 0x58, basis)
    return bytes(kopf) + b"\x00" * (basis - len(kopf)) + cnt


class PaketLesenTests(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="paket_")
        self.ordner = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _datei(self, name: str, inhalt: bytes) -> str:
        pfad = self.ordner / name
        pfad.write_bytes(inhalt)
        return str(pfad)

    def test_liest_content_id_sfo_und_titelbild(self) -> None:
        pfad = self._datei("a.pkg", _cnt({0x1000: SFO, 0x1200: ICON, 0x1006: b"x" * 1000}))
        teile = bp.paket_lesen(pfad)
        self.assertEqual("cnt", teile["art"])
        self.assertEqual(CONTENT_ID, teile["content_id"])
        self.assertEqual(SFO, teile["sfo"])
        self.assertEqual(ICON, teile["icon"])
        self.assertIsNone(teile["json"])

    def test_liest_die_param_json_eines_ps5_pakets(self) -> None:
        nutzlast = json.dumps({"titleId": "PPSA01234", "localizedParameters": {}}).encode("utf-8") + b"\x00"
        teile = bp.paket_lesen(self._datei("b.pkg", _cnt({0x2000: nutzlast}, content_id="EP0001-PPSA01234_00-X")))
        self.assertEqual({"titleId": "PPSA01234", "localizedParameters": {}}, teile["json"])
        self.assertEqual("EP0001-PPSA01234_00-X", teile["content_id"])
        self.assertIsNone(teile["sfo"])

    def test_ein_fih_abbild_wird_ueber_den_eingebetteten_kopf_gelesen(self) -> None:
        pfad = self._datei("c.pkg", _fih(_cnt({0x1000: SFO, 0x1200: ICON})))
        teile = bp.paket_lesen(pfad)
        self.assertEqual("fih", teile["art"])
        self.assertEqual(SFO, teile["sfo"])
        self.assertEqual(ICON, teile["icon"])

    def test_ein_verschluesselter_eintrag_wird_nicht_angefasst(self) -> None:
        pfad = self._datei("d.pkg", _cnt({0x1000: SFO, 0x1200: ICON}, verschluesselt=(0x1200,)))
        teile = bp.paket_lesen(pfad)
        self.assertEqual(SFO, teile["sfo"])
        self.assertIsNone(teile["icon"], "Ein verschluesselter Eintrag wird nicht gelesen - und nichts entschluesselt.")

    def test_fehlende_eintraege_sind_none_das_paket_bleibt_lesbar(self) -> None:
        teile = bp.paket_lesen(self._datei("e.pkg", _cnt({0x1006: b"nur etwas anderes"})))
        self.assertEqual(CONTENT_ID, teile["content_id"])
        self.assertIsNone(teile["sfo"])
        self.assertIsNone(teile["icon"])

    def test_was_kein_paket_ist_liefert_none(self) -> None:
        for name, inhalt in (("leer.pkg", b""), ("kurz.pkg", b"\x7fCNT"), ("text.pkg", b"nichts" * 100),
                             ("delta.pkg", b"\x7fLIH" + b"\x00" * 0x200)):
            with self.subTest(name=name):
                self.assertIsNone(bp.paket_lesen(self._datei(name, inhalt)))
        self.assertIsNone(bp.paket_lesen(str(self.ordner / "gibtesnicht.pkg")))

    def test_ein_unplausibler_kopf_liefert_none(self) -> None:
        for name, paket in (
                ("zuviele.pkg", _cnt({0x1000: SFO}, anzahl=bp.MAX_EINTRAEGE + 1)),
                ("keine.pkg", _cnt({0x1000: SFO}, anzahl=0)),
                ("tabelle_draussen.pkg", _cnt({0x1000: SFO}, tabelle=10 ** 9)),
                ("abgeschnitten.pkg", _cnt({0x1000: SFO, 0x1200: ICON})[:bp.KOPF_GROESSE + 10])):
            with self.subTest(name=name):
                self.assertIsNone(bp.paket_lesen(self._datei(name, paket)))

    def test_ein_fih_ohne_gueltigen_eingebetteten_kopf_liefert_none(self) -> None:
        kopf = bytearray(0x100)
        kopf[0:4] = bp.FIH_MAGIC
        struct.pack_into("<Q", kopf, 0x58, 10 ** 12)         # weit hinter dem Dateiende
        self.assertIsNone(bp.paket_lesen(self._datei("f.pkg", bytes(kopf) + b"\x00" * 100)))

    def test_ein_eintrag_ausserhalb_der_datei_oder_zu_gross_wird_uebergangen(self) -> None:
        paket = bytearray(_cnt({0x1000: SFO, 0x1200: ICON}))
        # Eintrag 2 (icon0): Groesse hinter das Dateiende setzen.
        stelle = bp.KOPF_GROESSE + bp.EINTRAG_GROESSE + 20
        struct.pack_into(">I", paket, stelle, len(paket) * 2)
        teile = bp.paket_lesen(self._datei("g.pkg", bytes(paket)))
        self.assertEqual(SFO, teile["sfo"])
        self.assertIsNone(teile["icon"])
        struct.pack_into(">I", paket, stelle, bp.MAX_EINTRAG_BYTES + 1)
        self.assertIsNone(bp.paket_lesen(self._datei("h.pkg", bytes(paket)))["icon"])

    def test_die_datei_wird_nie_ganz_gelesen(self) -> None:
        """Ein Paket hat Gigabyte - gelesen werden darf nur Kopf, Tabelle und die kleinen Eintraege."""
        gross = _cnt({0x1000: SFO, 0x1200: ICON}) + b"\x00" * (12 * 1024 * 1024)
        pfad = self._datei("gross.pkg", gross)
        gelesen = {"bytes": 0}
        echtes_open = builtins.open

        class _Zaehler:
            def __init__(self, datei) -> None:
                self._datei = datei

            def read(self, n=-1):
                daten = self._datei.read(n)
                gelesen["bytes"] += len(daten)
                return daten

            def __getattr__(self, name):
                return getattr(self._datei, name)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return self._datei.__exit__(*exc)

        def _oeffnen(datei, modus="r", *a, **k):
            roh = echtes_open(datei, modus, *a, **k)
            return _Zaehler(roh) if str(datei) == pfad else roh

        with mock.patch.object(bp, "open", _oeffnen, create=True):
            teile = bp.paket_lesen(pfad)
        self.assertEqual(ICON, teile["icon"])
        self.assertLess(gelesen["bytes"], 64 * 1024, "Gelesen wurden %d Byte - das Paket wurde geladen." % gelesen["bytes"])
        self.assertGreater(os.path.getsize(pfad), 12 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main(verbosity=2)
