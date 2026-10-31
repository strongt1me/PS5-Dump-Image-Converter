# -*- coding: utf-8 -*-
"""Der Host des WebKit Autoloaders wird nicht mehr mitgeliefert, sondern beim Klick geladen (seit v1.9.90).

Dieser Teil: ``werkzeug_updates.webkit_host_holen`` - rein gegen eine Nachbildung des Netzes. Die Seite (Fortschritt,
Start, Fehlermeldungen) prueft test_webkit_seite.HostLadenTests; die Bauplaene und der Ordner KlassenTests unten.

Ins Netz geht kein Test.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("webkit_host_holen")

from ps5_validator.utils import werkzeug_updates as wu      # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402
from webkit_host_attrappen import (BASIS_ADRESSE, FREIGABEN, FakeNetz,  # noqa: E402
                                   freigabe as _freigabe, inhalt as _inhalt)

class HostHolenTests(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.basis = self._tmp.name

    def _ordner(self) -> Path:
        return Path(wu.update_ordner(self.basis)) / wu.ORT_WEBKIT

    def _holen(self, art, fassung, netz, **kw):
        return wu.webkit_host_holen(art, fassung, self.basis, netz, **kw)

    def test_der_host_kommt_geprueft_an_seinen_platz(self) -> None:
        for art, name in (("exe", "webkit-autoloader-host_v0.6.2.exe"), ("py", "webkit-autoloader-host_v0.6.2.py")):
            with self.subTest(art=art):
                netz = FakeNetz(FREIGABEN)
                ergebnis = self._holen(art, "0.6.2", netz)
                self.assertEqual("", ergebnis.fehler, ergebnis)
                self.assertEqual(str(self._ordner() / name), ergebnis.pfad)
                self.assertEqual(_inhalt(name), Path(ergebnis.pfad).read_bytes())
                self.assertEqual([BASIS_ADRESSE + "v0.6.2/" + name], netz.geladen, "nur diese eine Datei")

    def test_es_gilt_die_gewaehlte_fassung_nicht_die_neueste(self) -> None:
        netz = FakeNetz(FREIGABEN)
        ergebnis = self._holen("exe", "0.6.1", netz)
        self.assertTrue(ergebnis.pfad.endswith("host_v0.6.1.exe"), ergebnis)
        self.assertEqual([BASIS_ADRESSE + "v0.6.1/webkit-autoloader-host_v0.6.1.exe"], netz.geladen)

    def test_eine_vorabmarke_zaehlt_nicht_als_die_fassung(self) -> None:
        """``v0.6.0-pre-4488577`` ist nicht ``v0.6.0`` - die Fassung 0.6.0 ist die fertige."""
        netz = FakeNetz([_freigabe("v0.6.0-pre-4488577")])
        ergebnis = self._holen("exe", "0.6.0", netz)
        self.assertEqual(wu.HOST_KEINE_FREIGABE, ergebnis.fehler)
        self.assertEqual([], netz.geladen)

    def test_ohne_netz_bleibt_nichts_liegen_und_es_wird_gemeldet(self) -> None:
        ergebnis = self._holen("exe", "0.6.2", FakeNetz(FREIGABEN, ausfall=OSError("getaddrinfo failed")))
        self.assertEqual(wu.HOST_NETZ, ergebnis.fehler)
        self.assertIn("getaddrinfo", ergebnis.detail)
        self.assertEqual("", ergebnis.pfad)
        self.assertFalse(self._ordner().exists())

    def test_anfragegrenze_und_serverfehler_haben_je_ihren_grund(self) -> None:
        self.assertEqual(wu.HOST_LIMIT, self._holen("exe", "0.6.2", FakeNetz(FREIGABEN, status=429)).fehler)
        self.assertEqual(wu.HOST_NETZ, self._holen("exe", "0.6.2", FakeNetz(FREIGABEN, status=503)).fehler)

    def test_eine_unbekannte_fassung_wird_nicht_durch_eine_andere_ersetzt(self) -> None:
        netz = FakeNetz(FREIGABEN)
        ergebnis = self._holen("exe", "9.9.9", netz)
        self.assertEqual((wu.HOST_KEINE_FREIGABE, "v9.9.9"), (ergebnis.fehler, ergebnis.detail))
        self.assertEqual([], netz.geladen)

    def test_fehlt_der_anhang_wird_nichts_geladen(self) -> None:
        netz = FakeNetz([_freigabe("v0.6.2", ohne=("webkit-autoloader-host_v0.6.2.py",))])
        self.assertEqual(wu.HOST_KEINE_DATEI, self._holen("py", "0.6.2", netz).fehler)
        self.assertEqual([], netz.geladen)
        self.assertEqual("", self._holen("exe", "0.6.2", netz).fehler, "die andere Art desselben Release geht")

    def test_ohne_pruefsumme_in_der_freigabe_wird_nichts_geladen(self) -> None:
        """Ein Programm, das gleich gestartet wird, nimmt man nicht ungeprueft."""
        netz = FakeNetz([_freigabe("v0.6.2", ohne_summe=True)])
        ergebnis = self._holen("exe", "0.6.2", netz)
        self.assertEqual(wu.HOST_OHNE_SUMME, ergebnis.fehler)
        self.assertEqual([], netz.geladen)
        self.assertFalse(self._ordner().exists())

    def test_eine_verfaelschte_datei_wird_verworfen(self) -> None:
        netz = FakeNetz(FREIGABEN)
        netz.verfaelscht = True
        ergebnis = self._holen("exe", "0.6.2", netz)
        self.assertEqual(wu.HOST_PRUEFSUMME, ergebnis.fehler)
        self.assertEqual("", ergebnis.pfad)
        uebrig = list(self._ordner().glob("*")) if self._ordner().exists() else []
        self.assertEqual([], uebrig, "weder Datei noch Teildatei darf bleiben")
        zwischen = [p.name for p in Path(wu.update_ordner(self.basis)).glob(".*.teil")]
        self.assertEqual([], zwischen)

    def test_eine_adresse_ausserhalb_von_github_wird_nie_geladen(self) -> None:
        netz = FakeNetz([_freigabe("v0.6.2", adresse="https://evil.example/")])
        ergebnis = self._holen("exe", "0.6.2", netz)
        self.assertNotEqual("", ergebnis.fehler)
        self.assertEqual([], netz.geladen)

    def test_unbrauchbare_angaben_gehen_nicht_ins_netz(self) -> None:
        netz = FakeNetz(FREIGABEN)
        for art, fassung in (("elf", "0.6.2"), ("exe", "../0.6.2"), ("exe", ""), ("exe", "0.6.2/x")):
            with self.subTest(art=art, fassung=fassung):
                self.assertEqual(wu.HOST_SONST, self._holen(art, fassung, netz).fehler)
        self.assertEqual([], netz.geladen)

    def test_der_fortschritt_wird_gemeldet(self) -> None:
        meldungen: list = []
        self._holen("exe", "0.6.2", FakeNetz(FREIGABEN), melden=lambda was, **w: meldungen.append((was, w)))
        hole = [w for was, w in meldungen if was == "hole"]
        self.assertTrue(hole)
        self.assertEqual(hole[-1]["fertig"], hole[-1]["gesamt"])
        self.assertEqual("webkit-autoloader-host_v0.6.2.exe", hole[-1]["text"])

    def test_ein_gesetzter_abbruch_laedt_nichts(self) -> None:
        netz = FakeNetz(FREIGABEN)
        abbruch = threading.Event()
        abbruch.set()
        self.assertEqual(wu.HOST_ABGEBROCHEN, self._holen("exe", "0.6.2", netz, abbruch=abbruch).fehler)
        self.assertEqual([], netz.geladen)

    def test_jeder_grund_hat_einen_text_in_allen_sprachen(self) -> None:
        for code in wu.HOST_GRUENDE:
            for sprache in ("de", "en", "es", "it", "fr"):
                with self.subTest(code=code, sprache=sprache):
                    self.assertTrue(STRINGS["webkit.dl_grund_" + code][sprache])


class KlassenTests(unittest.TestCase):
    """Was mit dem Programm ausgeliefert wird - und was nicht."""

    SPECS = ("PS5ImageConverter_Pro.spec", "PS5ImageConverter_Pro_linux.spec", "PS5ImageConverter_Pro_macos.spec")

    def test_die_bauplaene_nehmen_die_hosts_nicht_mehr_mit(self) -> None:
        for name in self.SPECS:
            with self.subTest(spec=name):
                text = (PROJEKT / name).read_text(encoding="utf-8")
                self.assertIn("webkit-autoloader-host_", text, "die Ausnahme muss im Plan stehen")
                self.assertNotIn("_datas.append((_webkit, 'PS5 WebKit Autoloader'))", text,
                                 "der ganze Ordner darf nicht mehr als Ganzes mit")

    def test_die_bauplaene_nehmen_installer_und_symbole_weiter_mit(self) -> None:
        """Nachgestellt: dieselbe Auswahl wie in der .spec - Installer und Bilder ja, Hosts nein."""
        ordner = PROJEKT / "PS5 WebKit Autoloader"
        mit = [d for d in sorted(os.listdir(ordner))
               if not d.lower().startswith("webkit-autoloader-host_") and (ordner / d).is_file()]
        self.assertTrue(any(d.startswith("webkit-autoloader-installer_") for d in mit))
        self.assertTrue(any(d.endswith(".png") for d in mit))
        self.assertFalse([d for d in mit if d.lower().endswith((".exe", ".py"))], "keine Host-Datei darf mit")
        self.assertIn("symbol_host_exe.png", mit, "die Symbole ueber den Knoepfen bleiben")
        for name in self.SPECS:
            text = (PROJEKT / name).read_text(encoding="utf-8")
            self.assertIn("_wk_datei.lower().startswith('webkit-autoloader-host_')", text)

    def test_das_programm_laedt_nur_von_den_erlaubten_adressen(self) -> None:
        self.assertTrue(wu.adresse_erlaubt(BASIS_ADRESSE + "v0.6.2/x.exe"))
        self.assertFalse(wu.adresse_erlaubt("https://evil.example/x.exe"))


if __name__ == "__main__":
    unittest.main()
