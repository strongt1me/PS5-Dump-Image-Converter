# -*- coding: utf-8 -*-
"""``paket_lesen()`` - PS5-Pakete lesen, die der eigene Entpacker nicht oeffnet.

Bis v1.9.2 bot die Huelle um LibProsperoPkg nur ``build`` an, obwohl die
mitgelieferte Bibliothek auch lesen kann. Der eigene Entpacker des Programms
kommt an PS5-Pakete nicht heran - an 31 Dateien gemessen, siehe die
Projektnotizen. Seither gibt es ``read``.

Zwei Ebenen werden geprueft, und die Trennung ist Absicht:

* **Die Auswertung** der Werkzeugausgabe laeuft gegen vorgegebene Zeilen.
  Sie braucht kein Werkzeug und keine Datei und laeuft deshalb ueberall.
* **Der echte Lauf** braucht beides. Er wird uebersprungen, wo eines fehlt -
  ein uebersprungener Test ist ehrlicher als einer, der nichts prueft.

Der wichtigste Fall ist der dritte Rueckgabewert: "keine PS5-PKG" ist eine
**Feststellung**, kein Fehler. Wer eine beliebige Datei hineinreicht, soll
das angezeigt bekommen, ohne eine Ausnahme fangen zu muessen.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import prosperopkg  # noqa: E402


#: Eine gekuerzte, aber echte Ausgabe von ``read`` an einem CNT-Paket.
CNT_AUSGABE = [
    r"Datei                : X:\probe.pkg",
    "Groesse              : 85458944",
    "Typ                  : Meta",
    "Magic                : 7F-43-4E-54",
    "ContentId            : ED1633-PKGI13337_00-0000000000000000",
    "Flags                : 0x00000001",
    "ContentFlags         : 0x0A000000",
    "IstPatch             : False",
    "EntryCount           : 23",
    "BodyOffset           : 8192",
    "ENTRY\t-\t0x0020\t10240\t256\tencrypted\t3",
    "ENTRY\tparam.sfo\t0x1000\t20080\t1832\tplain\t0",
    "ENTRY\tpic1.png\t0x1006\t577488\t602421\tplain\t0",
    "HINWEIS: Nur der aeussere Container wird gelesen; die eingebettete "
    "PFS bleibt verschluesselt.",
    "RESULT: Meta",
]

FIH_AUSGABE = [
    "Typ                  : FullDebug",
    "ContentId            : IV9999-CUSA99999_00-XXXXXXXXXXXXXXXX",
    "FihSignedByte        : 0x00",
    "FihIsOfficial        : False",
    "FihFormatVersion     : 3",
    "FihPfsImageOffset    : 65536",
    "FihPfsImageSize      : 29556736",
    "ErwarteteGroesse     : 29622272",
    "UNVOLLSTAENDIG: 4096 Bytes fehlen",
    "RESULT: FullDebug",
]

KEINE_AUSGABE = [
    r"Datei                : X:\irgendwas.exe",
    "Groesse              : 162304",
    "Typ                  : (keine PS5-PKG)",
    "RESULT: NOT_A_PS5_PKG",
]


def _mit_ausgabe(zeilen, code=0):
    """Ersetzt den Werkzeuglauf durch eine vorgegebene Ausgabe."""
    return mock.patch.object(prosperopkg, "_laufen_lassen",
                             lambda *a, **k: (code, list(zeilen)))


class AuswertungTests(unittest.TestCase):
    def test_ein_cnt_paket_wird_zerlegt(self) -> None:
        with _mit_ausgabe(CNT_AUSGABE):
            r = prosperopkg.paket_lesen("egal.pkg")
        self.assertTrue(r["ist_pkg"])
        self.assertEqual("Meta", r["typ"])
        self.assertEqual("ED1633-PKGI13337_00-0000000000000000",
                         r["kopf"]["ContentId"])
        self.assertEqual(3, len(r["eintraege"]))

    def test_eintraege_tragen_ihre_angaben(self) -> None:
        with _mit_ausgabe(CNT_AUSGABE):
            r = prosperopkg.paket_lesen("egal.pkg")
        param = next(e for e in r["eintraege"] if e["name"] == "param.sfo")
        self.assertEqual(20080, param["offset"])
        self.assertEqual(1832, param["groesse"])
        self.assertFalse(param["verschluesselt"])

    def test_ein_namenloser_eintrag_bleibt_leer(self) -> None:
        """Nicht jeder Eintrag steht in der Namenstabelle."""
        with _mit_ausgabe(CNT_AUSGABE):
            r = prosperopkg.paket_lesen("egal.pkg")
        ohne = [e for e in r["eintraege"] if not e["name"]]
        self.assertEqual(1, len(ohne))
        self.assertTrue(ohne[0]["verschluesselt"])
        self.assertEqual(3, ohne[0]["schluesselindex"])

    def test_hinweis_und_ergebnis_landen_nicht_im_kopf(self) -> None:
        """Sonst stuenden sie als Kopffelder da, die es nicht gibt."""
        with _mit_ausgabe(CNT_AUSGABE):
            r = prosperopkg.paket_lesen("egal.pkg")
        self.assertNotIn("RESULT", r["kopf"])
        self.assertNotIn("HINWEIS", r["kopf"])


class FinalisiertTests(unittest.TestCase):
    def test_der_fih_kopf_kommt_mit(self) -> None:
        with _mit_ausgabe(FIH_AUSGABE):
            r = prosperopkg.paket_lesen("egal.pkg")
        self.assertEqual("FullDebug", r["typ"])
        self.assertEqual("3", r["kopf"]["FihFormatVersion"])
        self.assertEqual("False", r["kopf"]["FihIsOfficial"])

    def test_eine_unvollstaendige_datei_nennt_die_fehlenden_bytes(self) -> None:
        """Der haeufigste Fall, in dem eine PKG kaputt aussieht.

        Ein geteilter Satz endet vor dem, was der Kopf ankuendigt. Das ist
        kein Schaden, sondern ein fehlendes Teil - und der Unterschied
        gehoert benannt.
        """
        with _mit_ausgabe(FIH_AUSGABE):
            r = prosperopkg.paket_lesen("egal.pkg")
        self.assertEqual(4096, r["unvollstaendig"])

    def test_ein_vollstaendiges_paket_meldet_null(self) -> None:
        ohne = [z for z in FIH_AUSGABE if not z.startswith("UNVOLLSTAENDIG")]
        with _mit_ausgabe(ohne):
            r = prosperopkg.paket_lesen("egal.pkg")
        self.assertEqual(0, r["unvollstaendig"])


class KeinPaketTests(unittest.TestCase):
    """Der dritte Rueckgabewert ist eine Feststellung, kein Fehler."""

    def test_keine_ausnahme(self) -> None:
        with _mit_ausgabe(KEINE_AUSGABE, code=3):
            r = prosperopkg.paket_lesen("irgendwas.exe")   # darf nicht werfen
        self.assertFalse(r["ist_pkg"])
        self.assertEqual([], r["eintraege"])

    def test_ein_echter_fehler_wirft_weiterhin(self) -> None:
        """Gegenprobe - sonst schluckte die Nachsicht oben jeden Fehler."""
        with _mit_ausgabe(["[FEHLER] IOException: kaputt"], code=3):
            with self.assertRaises(prosperopkg.ProsperoFehler):
                prosperopkg.paket_lesen("egal.pkg")


class ZahlTests(unittest.TestCase):
    """Eine unlesbare Zahl darf die uebrigen Angaben nicht mitnehmen."""

    def test_unsinn_wird_null(self) -> None:
        kaputt = [z for z in CNT_AUSGABE if not z.startswith("ENTRY")]
        kaputt.append("ENTRY\tx.bin\t0x1\tviele\twenige\tplain\tkeiner")
        with _mit_ausgabe(kaputt):
            r = prosperopkg.paket_lesen("egal.pkg")
        e = r["eintraege"][0]
        self.assertEqual(0, e["offset"])
        self.assertEqual("x.bin", e["name"], "Der Name ging mit verloren.")


class EchterLaufTests(unittest.TestCase):
    """Mit Werkzeug und echter Datei - sonst uebersprungen."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.werkzeug = prosperopkg.werkzeug_finden()
        except Exception:
            cls.werkzeug = ""
        cls.probe = ""
        for kandidat in (
            r"D:\PS5\PS5 Hack\PS5 SDK usw\Evox_PS5PKG_files\PS5PKG_FPKGi_v1.10.0.pkg",
            r"D:\PS5\PS5 Hack\PS5 SDK usw\PS5 PKG\PS5  PKG\Disc Player.pkg",
        ):
            if os.path.isfile(kandidat):
                cls.probe = kandidat
                break

    def setUp(self) -> None:
        if not self.werkzeug:
            self.skipTest("prosperopkg liegt auf dieser Anlage nicht bei.")
        if not self.probe:
            self.skipTest("Keine PS5-PKG zum Nachmessen vorhanden.")

    def test_eine_echte_pkg_wird_gelesen(self) -> None:
        r = prosperopkg.paket_lesen(self.probe)
        self.assertTrue(r["ist_pkg"])
        self.assertIn(r["typ"], ("Meta", "FullDebug", "FullRetail"))
        self.assertTrue(r["kopf"].get("ContentId"),
                        "Keine Content-ID gelesen.")
        self.assertTrue(r["eintraege"], "Keine Eintraege gelesen.")

    def test_eine_fremde_datei_gilt_als_keine_pkg(self) -> None:
        """Gegenprobe an einer Datei, die sicher keine PKG ist."""
        r = prosperopkg.paket_lesen(self.werkzeug)
        self.assertFalse(r["ist_pkg"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
