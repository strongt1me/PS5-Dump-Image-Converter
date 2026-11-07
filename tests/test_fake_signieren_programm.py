# -*- coding: utf-8 -*-
"""Fake-Signatur im Programm: Rueckfrage vor dem Lauf, Einbauschritt, Einstellung, Texte in fuenf Sprachen."""
from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))
sys.path.insert(0, str(PROJEKT / "tests"))

import pruefumgebung                                          # noqa: E402
pruefumgebung.umlenken("fake_signieren_programm")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import fake_signieren as fs       # noqa: E402
from ps5_validator.utils import ps5_backport as bp         # noqa: E402
from ps5_validator.utils.i18n import STRINGS, SUPPORTED_LANGUAGES, translate   # noqa: E402
from test_backport import baue_elf                         # noqa: E402

G = APP.PS5ConverterGUI


def _elf() -> bytes:
    daten = bytearray(baue_elf())
    struct.pack_into("<H", daten, 0x10, fs.ET_SCE_EXEC_ASLR)
    return bytes(daten)


class _App:
    """Eine Oberflaeche ohne Fenster: nur das, was die Fake-Signatur anfasst."""

    def __init__(self, variablen: dict | None = None) -> None:
        self.log: list[str] = []
        self.status: list[str] = []
        self.is_running = True
        self._cli_mode = False
        self._lauf_variablen = dict(variablen or {})
        self.fragen: list[tuple] = []
        self.antwort = True
        self._ampr_ordner_ist_kopie = True

    # --- was die Methoden brauchen ---
    def _t(self, schluessel: str, **werte) -> str:
        return translate("de", schluessel, **werte)

    def _append_to_log(self, text: str) -> None:
        self.log.append(text)

    def _set_status(self, text: str) -> None:
        self.status.append(text)

    def _tk_wert(self, name: str, vorgabe=None):
        return self._lauf_variablen.get(name, vorgabe)

    def _ask_yesno_threadsafe(self, titel: str, text: str, default_yes: bool = True) -> bool:
        self.fragen.append((titel, text, default_yes))
        return self.antwort

    _MODE_TARGET_OPTIONS = G._MODE_TARGET_OPTIONS

    # --- die echten Methoden ---
    _integration_fake_signieren = G._integration_fake_signieren
    _fake_vor_dem_lauf_klaeren = G._fake_vor_dem_lauf_klaeren


class _Spiel(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.w = Path(tmp.name)
        (self.w / "sce_sys").mkdir()
        (self.w / "sce_sys" / "param.json").write_text("{}")
        (self.w / "eboot.bin").write_bytes(_elf())
        (self.w / "libx.prx").write_bytes(_elf())

    def _sauber(self) -> None:
        (self.w / "eboot.bin").write_bytes(bp.elf_signieren(_elf()))
        (self.w / "libx.prx").write_bytes(bp.elf_signieren(_elf()))


class EinbauschrittTests(_Spiel):
    def test_signiert_und_meldet(self) -> None:
        app = _App()
        self.assertTrue(app._integration_fake_signieren(str(self.w)))
        self.assertEqual([], fs.unsignierte_finden(str(self.w)))
        text = "".join(app.log)
        self.assertIn("2 unsignierte Programme", text)
        self.assertIn("Fertig: 2 signiert, 0 Fehler", text)
        self.assertFalse((self.w / "eboot.bin.orig").exists(), "in einer Kopie braucht es keine Sicherung")

    def test_im_original_bleibt_eine_orig(self) -> None:
        app = _App()
        app._ampr_ordner_ist_kopie = False
        self.assertTrue(app._integration_fake_signieren(str(self.w)))
        self.assertTrue((self.w / "eboot.bin.orig").exists())
        self.assertIn(".orig", "".join(app.log))

    def test_ohne_unsignierte_nichts_zu_tun(self) -> None:
        self._sauber()
        vorher = (self.w / "eboot.bin").read_bytes()
        app = _App()
        self.assertTrue(app._integration_fake_signieren(str(self.w)))
        self.assertIn("nichts zu tun", "".join(app.log))
        self.assertEqual(vorher, (self.w / "eboot.bin").read_bytes())

    def test_abbruch_gibt_false_zurueck(self) -> None:
        app = _App()
        app.is_running = False
        self.assertFalse(app._integration_fake_signieren(str(self.w)))
        self.assertEqual(2, len(fs.unsignierte_finden(str(self.w))), "nichts geschrieben")

    def test_ein_fehler_wird_gemeldet_der_lauf_geht_weiter(self) -> None:
        (self.w / "kaputt.elf").write_bytes(_elf()[:0x50])
        app = _App()
        self.assertTrue(app._integration_fake_signieren(str(self.w)))
        text = "".join(app.log)
        self.assertIn("Nicht signiert: kaputt.elf", text)
        self.assertIn("2 signiert, 1 Fehler", text)

    def test_viele_dateien_werden_gekuerzt_gemeldet(self) -> None:
        for i in range(25):
            (self.w / ("m%02d.prx" % i)).write_bytes(_elf())
        app = _App()
        app._integration_fake_signieren(str(self.w))
        self.assertEqual(20, "".join(app.log).count("Signiert: "))
        self.assertIn("und 7 weitere", "".join(app.log))


class RueckfrageTests(_Spiel):
    def test_fragt_bei_unsignierten_programmen_und_schaltet_fuer_den_lauf_ein(self) -> None:
        app = _App()
        app._fake_vor_dem_lauf_klaeren("pack_folder", str(self.w))
        self.assertEqual(1, len(app.fragen))
        titel, text, vorgabe = app.fragen[0]
        self.assertIn("Unsignierte Programme gefunden", titel)
        self.assertIn("2 unsignierte Programme", text)
        self.assertTrue(vorgabe)
        self.assertTrue(app._lauf_variablen["fake_signieren_var"])
        self.assertIn("in diesem Lauf fake-signiert", "".join(app.log))

    def test_nein_laesst_alles_wie_es_ist(self) -> None:
        app = _App()
        app.antwort = False
        app._fake_vor_dem_lauf_klaeren("pack_folder", str(self.w))
        self.assertNotIn("fake_signieren_var", app._lauf_variablen)
        self.assertIn("bleiben unverändert", "".join(app.log))

    def test_ohne_unsignierte_programme_keine_frage(self) -> None:
        self._sauber()
        app = _App()
        app._fake_vor_dem_lauf_klaeren("pack_folder", str(self.w))
        self.assertEqual([], app.fragen)
        self.assertNotIn("fake_signieren_var", app._lauf_variablen)

    def test_einstellung_an_dann_keine_frage_und_kein_durchgang(self) -> None:
        app = _App({"fake_signieren_var": True})
        with mock.patch.object(fs, "unsignierte_finden", side_effect=AssertionError("kein Durchgang")) as suche:
            app._fake_vor_dem_lauf_klaeren("pack_folder", str(self.w))
        suche.assert_not_called()
        self.assertEqual([], app.fragen)

    def test_kommandozeile_fragt_nicht_sondern_empfiehlt(self) -> None:
        app = _App()
        app._cli_mode = True
        app._fake_vor_dem_lauf_klaeren("pack_folder", str(self.w))
        self.assertEqual([], app.fragen)
        self.assertIn("EINSTELLUNGEN", "".join(app.log))
        self.assertNotIn("fake_signieren_var", app._lauf_variablen)

    def test_sammelkonvertierung_und_andere_aufgaben_fragen_nicht(self) -> None:
        for mode in ("batch_convert", "inspect", "dump_validator"):
            with self.subTest(mode=mode):
                app = _App()
                app._fake_vor_dem_lauf_klaeren(mode, str(self.w))
                self.assertEqual([], app.fragen)

    def test_abbild_und_fehlender_pfad_werden_nicht_durchsucht(self) -> None:
        abbild = self.w / "Spiel.ffpfsc"
        abbild.write_bytes(b"x")
        for quelle in (str(abbild), str(self.w / "gibt_es_nicht")):
            with self.subTest(quelle=quelle):
                app = _App()
                with mock.patch.object(fs, "unsignierte_finden", side_effect=AssertionError("kein Durchgang")) as suche:
                    app._fake_vor_dem_lauf_klaeren("pack_folder", quelle)
                suche.assert_not_called()
                self.assertEqual([], app.fragen)


class AnbindungTests(unittest.TestCase):
    def test_die_variable_gehoert_zum_stand_eines_laufs(self) -> None:
        self.assertIn("fake_signieren_var", G._LAUF_VARIABLEN)

    def test_einstellung_heisst_wie_im_dialog(self) -> None:
        self.assertEqual("integrate_fake_signieren", G._FAKE_SIGNIEREN_SETTING)

    def test_integration_gewaehlt_kennt_die_fake_signatur(self) -> None:
        app = _App({"fake_signieren_var": True})
        app._integration_gewaehlt = G._integration_gewaehlt.__get__(app)
        self.assertTrue(app._integration_gewaehlt())
        app = _App()
        app._integration_gewaehlt = G._integration_gewaehlt.__get__(app)
        self.assertFalse(app._integration_gewaehlt())

    def test_der_einbau_ruft_den_schritt_nach_dem_backport_und_vor_ampr(self) -> None:
        reihenfolge: list[str] = []
        app = _App({"fake_signieren_var": True, "backport_integrate_var": True})
        app._integration_gewaehlt = G._integration_gewaehlt.__get__(app)
        app._integration_anwenden = G._integration_anwenden.__get__(app)
        app._integration_backport = lambda ordner: reihenfolge.append("backport") or True
        app._integration_fake_signieren = lambda ordner: reihenfolge.append("fake") or True
        app._integration_dlc = lambda ordner: reihenfolge.append("dlc") or True
        app._integration_ampr = lambda ordner, nur_playgo=False: reihenfolge.append("ampr") or True
        app._ampr_wird_eingebaut = lambda: True
        app._playgo_wird_eingebaut = lambda: False
        app._integration_erledigt = False
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(tmp, app._integration_anwenden(tmp))
        self.assertEqual(["backport", "fake", "ampr"], reihenfolge)

    def test_ein_abbruch_im_schritt_bricht_den_einbau_ab(self) -> None:
        app = _App({"fake_signieren_var": True})
        app._integration_gewaehlt = G._integration_gewaehlt.__get__(app)
        app._integration_anwenden = G._integration_anwenden.__get__(app)
        app._integration_fake_signieren = lambda ordner: False
        app._ampr_wird_eingebaut = lambda: False
        app._playgo_wird_eingebaut = lambda: False
        app._integration_erledigt = False
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual("", app._integration_anwenden(tmp))


class TexteTests(unittest.TestCase):
    SCHLUESSEL = (
        "settings_dialog.fake_section", "settings_dialog.fake_hint", "settings_dialog.fake_checkbox",
        "status.fake_pruefen", "dialog.title.fake_empfohlen", "dialog.msg.fake_empfohlen", "main.fake_status",
        "main.fake_suche", "main.fake_keine", "main.fake_start", "main.fake_fortschritt", "main.fake_datei",
        "main.fake_weitere", "main.fake_gesichert", "main.fake_fehler", "main.fake_fertig", "main.fake_empfohlen",
        "main.fake_bleibt_aus", "main.fake_eingeschaltet",
    )

    def test_alle_texte_in_allen_sprachen_mit_gleichen_platzhaltern(self) -> None:
        import string
        formatierer = string.Formatter()
        for schluessel in self.SCHLUESSEL:
            self.assertIn(schluessel, STRINGS)
            felder = {s: {f for _, f, _, _ in formatierer.parse(STRINGS[schluessel][s]) if f}
                      for s in SUPPORTED_LANGUAGES}
            for s in SUPPORTED_LANGUAGES:
                with self.subTest(schluessel=schluessel, sprache=s):
                    self.assertTrue(STRINGS[schluessel][s].strip())
                    self.assertEqual(felder["de"], felder[s])

    def test_log_zeilen_enden_mit_zeilenumbruch(self) -> None:
        for schluessel in self.SCHLUESSEL:
            if schluessel.startswith("main.fake_") and schluessel not in ("main.fake_status", "main.fake_fortschritt"):
                for s in SUPPORTED_LANGUAGES:
                    with self.subTest(schluessel=schluessel, sprache=s):
                        self.assertTrue(STRINGS[schluessel][s].endswith("\n"))


if __name__ == "__main__":
    unittest.main()
