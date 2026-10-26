# -*- coding: utf-8 -*-
"""Backport: Hinweis auf fremde AMPR-/PlayGo-Bibliotheken im Dump (25.10.2026).

Anlass: Hollow Knight (PPSA34971, Firmware 4.03) und der Backport mit und ohne Ersatzbibliotheken - derselbe Absturz
``0xa0020104`` direkt nach ``libSceSysmodule``. Der Dump brachte ``fakelib/libSceAmpr.sprx`` und ``libScePlayGo.sprx`` eines
anderen Werkzeugs mit; der mitgelieferte Satz hat keine von beiden und fasst sie nicht an. Behoben hat es das Ersetzen durch die
Dateien aus AMPR EMU. Das Protokoll soll deshalb darauf hinweisen und AMPR EMU samt PlayGo empfehlen.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402,F401
from ps5_validator.utils import ps5_backport as bp          # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"


def _lade_hauptprogramm():
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


class _Dump:
    """Ein Dump-Ordner im Temp, mit frei waehlbaren Dateien."""

    def __init__(self, testfall: unittest.TestCase) -> None:
        self.wurzel = tempfile.mkdtemp(prefix="fremdlib_")
        testfall.addCleanup(self._weg)

    def _weg(self) -> None:
        import shutil
        shutil.rmtree(self.wurzel, ignore_errors=True)

    def lege(self, rel: str, daten: bytes) -> None:
        pfad = os.path.join(self.wurzel, rel)
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        with open(pfad, "wb") as fh:
            fh.write(daten)


SONY = b"\x7fELF" + b"\x00" * 64 + b"libSceAmpr original"


class FindenTests(unittest.TestCase):
    def test_ohne_fakelib_kein_befund(self) -> None:
        self.assertEqual([], bp.fremde_ampr_playgo(_Dump(self).wurzel))

    def test_fremde_bibliotheken_werden_genannt(self) -> None:
        d = _Dump(self)
        d.lege("fakelib/libSceAmpr.sprx", SONY)
        d.lege("fakelib/libScePlayGo.sprx", SONY)
        self.assertEqual(["fakelib/libSceAmpr.sprx", "fakelib/libScePlayGo.sprx"], bp.fremde_ampr_playgo(d.wurzel))

    def test_amprs_emu_und_playgo_stub_sind_nicht_fremd(self) -> None:
        d = _Dump(self)
        d.lege("fakelib/libSceAmpr.sprx", b"\x7fELF.....[AMPR_EMU] 0.4.2.1")
        d.lege("fakelib/libScePlayGo.sprx", b"\x7fELF.....playgo_stub.dat")
        self.assertEqual([], bp.fremde_ampr_playgo(d.wurzel))

    def test_andere_bibliotheken_zaehlen_nicht(self) -> None:
        d = _Dump(self)
        d.lege("fakelib/libSceAudioOut.sprx", SONY)
        d.lege("fakelib/libSceAmpr.sprx.orig", SONY)
        self.assertEqual([], bp.fremde_ampr_playgo(d.wurzel))

    def test_auch_fakelib2_und_andere_schreibweise(self) -> None:
        d = _Dump(self)
        d.lege("fakelib2/LIBSCEAMPR.SPRX", SONY)
        self.assertEqual(["fakelib2/LIBSCEAMPR.SPRX"], bp.fremde_ampr_playgo(d.wurzel))

    def test_der_mitgelieferte_satz_hat_beide_nicht(self) -> None:
        """Die Voraussetzung des Hinweises: Der Satz ersetzt Ampr/PlayGo nie - sonst waere der Hinweis falsch."""
        basis = PROJEKT / "Backport_Fakelibs"
        for stand in bp.firmwares_mit_bestand(str(basis)):
            with self.subTest(firmware=stand):
                namen = {os.path.basename(p).lower() for p in bp.fakelib_dateien(str(basis), stand)}
                self.assertFalse(namen & set(bp.AMPR_PLAYGO_BIBLIOTHEKEN), namen)


class KlaerenTests(unittest.TestCase):
    """Die Frage und die Behebung: AMPR EMU und der PlayGo-Stub ersetzen die fremden Dateien."""

    EMU = b"\x7fELF.....[AMPR_EMU] 0.4.2.1"
    STUB = b"\x7fELF.....playgo_stub.dat"

    def setUp(self) -> None:
        modul = _lade_hauptprogramm()
        self.app = modul.PS5ConverterGUI.__new__(modul.PS5ConverterGUI)
        self.log: list[str] = []
        self.fragen: list[tuple] = []
        self.antwort = True
        self.app._append_to_log = self.log.append
        self.app._t = lambda schluessel, **werte: STRINGS[schluessel]["de"].format(**werte)
        self.app._smgen_texte = lambda: {}
        self.app._cli_mode = False
        self.app._tk_wert = lambda name, vorgabe=None: {"ampr_version_var": "0.4.2.1"}.get(name, vorgabe)
        self.quelle = tempfile.mkdtemp(prefix="ampr_quelle_")
        self.addCleanup(__import__("shutil").rmtree, self.quelle, True)
        self.emu = os.path.join(self.quelle, "libSceAmpr.sprx")
        self.stub = os.path.join(self.quelle, "libScePlayGo.sprx")
        Path(self.emu).write_bytes(self.EMU)
        Path(self.stub).write_bytes(self.STUB)
        self.app._ampr_versionsauswahl = {"0.4.2.1": {"path": self.emu}}
        self.app._ampr_playgo_zur_version = lambda eintrag: self.stub

        def frage(titel, text, default_yes=True):
            self.fragen.append((titel, text))
            return self.antwort
        self.app._ask_yesno_threadsafe = frage
        self.index: list[str] = []
        self.app._ampr_index_neubau_erlaubt = lambda ordner, **kw: True
        self.app._build_ampr_index_local = lambda ordner, pfad: (self.index.append(str(pfad)) or (7, 0))

    def _dump_mit_beiden(self) -> str:
        d = _Dump(self)
        d.lege("fakelib/libSceAmpr.sprx", SONY)
        d.lege("fakelib/libScePlayGo.sprx", SONY)
        return d.wurzel

    def test_einbau_ja_schaltet_fuer_den_lauf_an_und_aendert_noch_nichts(self) -> None:
        ordner = self._dump_mit_beiden()
        self.assertEqual([], self.app._backport_fremdlibs_klaeren(ordner))
        self.assertEqual(1, len(self.fragen))
        self.assertIn("fakelib/libSceAmpr.sprx", self.fragen[0][1])
        self.assertTrue(self.app._fremdlibs_beheben)
        self.assertEqual(SONY, Path(ordner, "fakelib", "libSceAmpr.sprx").read_bytes(), "ersetzt wird spaeter im Einbau")
        self.assertIn("[OK]", self.log[0])
        # Der Einbau nimmt AMPR EMU und PlayGo jetzt mit - die Kaestchen selbst bleiben aus.
        self.assertTrue(self.app._ampr_wird_eingebaut())
        self.assertTrue(self.app._playgo_wird_eingebaut())

    def test_einbau_nein_laesst_alles_und_warnt(self) -> None:
        self.antwort = False
        ordner = self._dump_mit_beiden()
        bleiben = self.app._backport_fremdlibs_klaeren(ordner)
        self.assertEqual(2, len(bleiben))
        self.assertFalse(getattr(self.app, "_fremdlibs_beheben", False))
        self.assertFalse(self.app._ampr_wird_eingebaut())
        self.assertIn("[WARNUNG]", self.log[0])

    def test_baut_der_lauf_beides_ein_wird_nicht_gefragt(self) -> None:
        self.assertEqual([], self.app._backport_fremdlibs_klaeren(self._dump_mit_beiden(), True, True))
        self.assertEqual([], self.fragen)
        self.assertEqual([], self.log)

    def test_nur_was_nicht_ersetzt_wird_wird_gefragt(self) -> None:
        self.app._backport_fremdlibs_klaeren(self._dump_mit_beiden(), ampr_an=True)
        self.assertEqual(1, len(self.fragen))
        self.assertNotIn("libSceAmpr.sprx", self.fragen[0][1])
        self.assertIn("libScePlayGo.sprx", self.fragen[0][1])

    def test_ohne_fremde_dateien_wird_nichts_gefragt(self) -> None:
        self.assertEqual([], self.app._backport_fremdlibs_klaeren(_Dump(self).wurzel))
        self.assertEqual(([], []), (self.fragen, self.log))

    def test_ohne_waehlbare_fassung_oder_ohne_dialog_bleibt_es_beim_hinweis(self) -> None:
        self.app._ampr_versionsauswahl = {}
        self.assertEqual(2, len(self.app._backport_fremdlibs_klaeren(self._dump_mit_beiden())))
        self.assertEqual([], self.fragen)
        self.app._ampr_versionsauswahl = {"0.4.2.1": {"path": self.emu}}
        self.app._cli_mode = True
        self.assertEqual(2, len(self.app._backport_fremdlibs_klaeren(self._dump_mit_beiden())))
        self.assertEqual([], self.fragen)

    def test_fenster_ja_ersetzt_beide_sichert_die_originale_und_baut_den_index(self) -> None:
        ordner = self._dump_mit_beiden()
        self.assertEqual([], self.app._backport_fremdlibs_klaeren(ordner, fassung="0.4.2.1"))
        fakelib = Path(ordner, "fakelib")
        self.assertEqual(self.EMU, (fakelib / "libSceAmpr.sprx").read_bytes())
        self.assertEqual(self.STUB, (fakelib / "libScePlayGo.sprx").read_bytes())
        self.assertEqual(SONY, (fakelib / "libSceAmpr.sprx.orig").read_bytes(), "das fremde Original bleibt erhalten")
        self.assertEqual(SONY, (fakelib / "libScePlayGo.sprx.orig").read_bytes())
        self.assertEqual(1, len(self.index))
        self.assertEqual([], bp.fremde_ampr_playgo(ordner), "danach ist nichts Fremdes mehr da")
        self.assertIn("ersetzt", self.log[-1])

    def test_fenster_nein_aendert_keine_datei(self) -> None:
        self.antwort = False
        ordner = self._dump_mit_beiden()
        self.assertEqual(2, len(self.app._backport_fremdlibs_klaeren(ordner, fassung="0.4.2.1")))
        self.assertEqual(SONY, Path(ordner, "fakelib", "libSceAmpr.sprx").read_bytes())
        self.assertEqual([], self.index)

    def test_fenster_scheitert_der_index_bleibt_die_warnung(self) -> None:
        def kaputt(ordner, pfad):
            raise RuntimeError("kein Platz")
        self.app._build_ampr_index_local = kaputt
        bleiben = self.app._backport_fremdlibs_klaeren(self._dump_mit_beiden(), fassung="0.4.2.1")
        self.assertEqual(2, len(bleiben))
        self.assertTrue(any("kein Platz" in z for z in self.log))

    def test_nur_eine_fremde_datei_ersetzt_nur_diese(self) -> None:
        d = _Dump(self)
        d.lege("fakelib/libSceAmpr.sprx", SONY)
        d.lege("fakelib/libScePlayGo.sprx", self.STUB)
        self.assertEqual([], self.app._backport_fremdlibs_klaeren(d.wurzel, fassung="0.4.2.1"))
        self.assertEqual(self.EMU, Path(d.wurzel, "fakelib", "libSceAmpr.sprx").read_bytes())
        self.assertFalse(Path(d.wurzel, "fakelib", "libScePlayGo.sprx.orig").exists())


class TexteUndAufrufeTests(unittest.TestCase):
    def test_die_texte_stehen_in_allen_fuenf_sprachen(self) -> None:
        for schluessel in ("main.integrate_backport_fremd", "main.integrate_backport_fremd_an",
                           "backport.log_fremd_behoben", "dialog.msg.backport_fremd", "dialog.title.backport_fremd"):
            for sprache in ("de", "en", "es", "it", "fr"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    text = STRINGS[schluessel][sprache]
                    self.assertTrue(text.strip())
                    text.format(namen="x")
                    if schluessel.startswith(("main.", "backport.")):
                        self.assertTrue(text.endswith("\n"))
                    if schluessel in ("main.integrate_backport_fremd", "dialog.msg.backport_fremd"):
                        self.assertIn("0xa0020104", text)

    def test_beide_wege_rufen_den_hinweis(self) -> None:
        """Einbau beim Erstellen und BACKPORT-Fenster - ohne den Aufruf bliebe der Hinweis stumm."""
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        glatt = quelle.replace("\r\n", "\n")
        self.assertIn('self._backport_fremdlibs_klaeren(ordner, bool(self._tk_wert("ampr_integrate_var", False)),', glatt)
        self.assertIn("self._backport_fremdlibs_klaeren(ordner, fassung=", glatt)
        # Der Einbau liest die Kaestchen ueber die Helfer, die die Behebung kennen.
        self.assertIn("ampr_an = self._ampr_wird_eingebaut()", glatt)
        self.assertIn("playgo_an = self._playgo_wird_eingebaut()", glatt)
        self.assertIn("self._backport_ampr_fassung = ", glatt)


if __name__ == "__main__":
    unittest.main()
