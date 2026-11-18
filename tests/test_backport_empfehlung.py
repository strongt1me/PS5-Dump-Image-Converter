# -*- coding: utf-8 -*-
"""BACKPORT: Rueckfrage vor dem Lauf, wenn das Spiel mehr verlangt, als die Konsole hat (17.11.2026).

Die Firmware der Konsole kennt das Programm, wenn die Ansicht KONSOLE sie gemessen hat (``_konsole_firmware``, Einstellung
``konsole_firmware``). Sonst fragt es **einmal**, merkt die Hauptversion (``konsole_firmware_angabe``) und schlaegt danach
BACKPORT vor, wenn das SDK der ``eboot.bin`` oder die verlangte Firmware der ``param.json`` mehr verlangen und das Spiel noch
nicht herabgesetzt ist. Ziel ist die hoechste Stufe mit Ersatzbibliotheken, die nicht ueber der Konsole liegt
(``ps5_backport.firmware_vorschlag``, wie im BACKPORT-Fenster). Die Zahlen unten sind an echten Abbildern gemessen
(Dump Forge ``inspect``):

* Arcade Game Zone: SDK 7.00, verlangte Firmware 9.60, kein Backport;
* dasselbe Spiel mit BACKPORT: ``backport_firmware`` "7.00" und fuenf Ersatzbibliotheken;
* Terminator 2D: SDK 10.00, verlangte Firmware 11.20;
* Crazy Chicken Shooter: SDK 2.00, Firmware 2.00.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402,F401
from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI as GUI   # noqa: E402
from ps5_validator.utils import forge_cli as fc              # noqa: E402

#: Die Stufen mit Ersatzbibliotheken, die das Programm mitliefert.
STUFEN = (4, 5, 6, 7)


def _daten(sdk: str = "", firmware: str = "", backport: int = 0, backport_firmware=None) -> dict:
    return {"sdk": sdk, "firmware": firmware, "backport": [{"path": "fakelib/x%d.sprx" % i} for i in range(backport)],
            "backport_firmware": backport_firmware}


def _f(sdk: str = "10.00", firmware: str = "11.20", **kw) -> "fc.QuellFakten":
    return fc.quellfakten(_daten(sdk, firmware, **kw))


class FaktenTests(unittest.TestCase):
    def test_das_meiste_von_sdk_und_firmware_zaehlt(self) -> None:
        for sdk, fw, haupt, text in (("7.00", "9.60", 9, "9.60"), ("10.00", "11.20", 11, "11.20"), ("12.00", "2.00", 12, "12.00"),
                                     ("2.00", "2.00", 2, "2.00"), ("", "", 0, ""), ("0.00", "0.00", 0, ""),
                                     ("10.01", "10.00", 10, "10.01")):
            with self.subTest(sdk=sdk, firmware=fw):
                f = fc.quellfakten(_daten(sdk, fw))
                self.assertEqual((haupt, text), (f.verlangt_haupt, f.verlangt_text))

    def test_aus_forges_antwort_gelesen(self) -> None:
        f = fc.quellfakten(_daten("7.00", "9.60"))
        self.assertEqual(("7.00", "9.60", False), (f.sdk, f.firmware, f.backport_vorhanden))

    def test_ein_schon_herabgesetztes_spiel_traegt_einen_backport(self) -> None:
        self.assertTrue(fc.quellfakten(_daten("7.00", "9.60", backport=5, backport_firmware="7.00")).backport_vorhanden)
        self.assertTrue(fc.quellfakten(_daten("7.00", "9.60", backport=3)).backport_vorhanden, "die Bibliotheken allein")

    def test_backport_firmware_allein_ist_kein_backport(self) -> None:
        """Forge setzt ``backport_firmware``, sobald irgendeine Datei in ``fakelib/`` liegt - auch bei einem Spiel nur mit AMPR EMU dort.

        Gemessen 18.11.2026 an einem Ordner mit ``eboot.bin``, ``param.json`` und ``fakelib/libSceAmpr.sprx``: ``backport`` leer,
        ``backport_firmware`` "2.00". Ein solches Spiel hat keinen Backport: Das Programm darf ihn weder als "bereits eingebaut"
        melden noch das Angebot unterdruecken.
        """
        daten = _daten("10.00", "11.20", backport_firmware="10.00")
        daten["emulators"] = [{"name": "AMPR", "path": "fakelib/libSceAmpr.sprx"}]
        fakten = fc.quellfakten(daten)
        self.assertFalse(fakten.backport_vorhanden)
        self.assertTrue(fakten.backport_noetig("7.99"), "es verlangt mehr als die Konsole hat und ist nicht herabgesetzt")
        self.assertFalse(fc.quellfakten(_daten("7.00", "9.60", backport_firmware="7.00")).backport_vorhanden, "das SDK allein")

    def test_wann_ein_backport_noetig_ist_an_gemessenen_spielen(self) -> None:
        """Verglichen wie in der Bibliothek: Haupt- UND Nebenversion; ``7.99`` = "irgendeine 7.xx"."""
        arcade, terminator, huhn = _f("7.00", "9.60"), _f("10.00", "11.20"), _f("2.00", "2.00")
        faelle = (
            (arcade, "7.99", True), (arcade, "8.99", True), (arcade, "9.00", True), (arcade, "9.60", False),
            (arcade, "9.99", False), (arcade, "12.00", False),
            (terminator, "7.99", True), (terminator, "10.99", True), (terminator, "11.00", True), (terminator, "11.20", False),
            (terminator, "11.99", False), (terminator, "12.00", False),
            (huhn, "1.99", True), (huhn, "2.00", False), (huhn, "7.99", False),
        )
        for fakten, konsole, erwartet in faelle:
            with self.subTest(spiel=fakten.verlangt_text, konsole=konsole):
                self.assertIs(erwartet, fakten.backport_noetig(konsole))

    def test_ohne_firmware_der_konsole_ist_nichts_noetig(self) -> None:
        for konsole in ("", "abc", "0.00", None):
            with self.subTest(konsole=konsole):
                self.assertFalse(_f().backport_noetig(konsole))                       # type: ignore[arg-type]

    def test_ein_herabgesetztes_spiel_braucht_keinen_zweiten_backport(self) -> None:
        self.assertFalse(_f("10.00", "11.20", backport=5, backport_firmware="7.00").backport_noetig("7.99"))

    def test_ein_spiel_ohne_angaben_braucht_nichts(self) -> None:
        self.assertFalse(fc.QuellFakten().backport_noetig("7.99"))
        self.assertFalse(_f("0.00", "0.00").backport_noetig("7.99"))


class KonsoleFirmwareTests(unittest.TestCase):
    @staticmethod
    def _gui(gemessen="", angabe="", antwort="7.xx"):
        g = GUI.__new__(GUI)
        g._speicher = {"konsole_firmware_angabe": angabe}
        g._load_setting = lambda schluessel, vorgabe: g._speicher.get(schluessel, vorgabe)
        g._save_setting = mock.Mock(side_effect=lambda schluessel, wert: g._speicher.__setitem__(schluessel, wert))
        g._konsole_firmware = lambda: gemessen                    # die vorhandene Messung der Ansicht KONSOLE
        g._t = lambda schluessel, **w: schluessel
        g._log = []
        g._append_to_log = g._log.append
        g._auswahl_dialog = object()                              # nur als Kennung fuer den Aufruf
        g._dialog_eintraege = []

        def im_hauptfaden(funktion, titel, frage, eintraege):
            g._dialog_eintraege = list(eintraege)
            return antwort

        g._im_hauptfaden = im_hauptfaden
        return g

    def test_gemessen_geht_vor_und_wird_wie_in_der_bibliothek_gelesen(self) -> None:
        for gemessen, erwartet in (("12.00", "12.00"), ("09.00.00.00", "9.00"), ("12000020", "12.00"), ("7.61", "7.61")):
            with self.subTest(gemessen=gemessen):
                self.assertEqual(erwartet, self._gui(gemessen, angabe="5")._konsole_fw_bekannt())

    def test_ohne_messung_gilt_die_angabe_als_hauptversion(self) -> None:
        for angabe, erwartet in (("7", "7.99"), ("12", "12.99"), ("13", "13.99"), ("1", "1.99")):
            with self.subTest(angabe=angabe):
                self.assertEqual(erwartet, self._gui(angabe=angabe)._konsole_fw_bekannt())

    def test_nie_gefragt_ist_none_und_nicht_angegeben_ist_leer(self) -> None:
        self.assertIsNone(self._gui()._konsole_fw_bekannt())
        for angabe in ("keine", "abc", "0", "100"):
            with self.subTest(angabe=angabe):
                self.assertEqual("", self._gui(angabe=angabe)._konsole_fw_bekannt())

    def test_die_anzeige_nennt_eine_genannte_hauptversion_als_xx(self) -> None:
        for firmware, erwartet in (("7.99", "7.xx"), ("12.99", "12.xx"), ("12.00", "12.00"), ("7.61", "7.61"), ("", "")):
            with self.subTest(firmware=firmware):
                self.assertEqual(erwartet, GUI._konsole_fw_anzeige(firmware))

    def test_die_antwort_wird_gemerkt_und_zurueckgegeben(self) -> None:
        g = self._gui(antwort="7.xx")
        self.assertEqual("7.99", g._konsole_firmware_erfragen())
        self.assertEqual("7", g._speicher["konsole_firmware_angabe"])
        self.assertEqual("7.99", g._konsole_fw_bekannt(), "danach wird nicht mehr gefragt")
        self.assertEqual(["main.konsole_fw_gemerkt"], g._log)

    def test_die_vorhandene_messung_der_konsole_wird_nie_ueberschrieben(self) -> None:
        g = self._gui(gemessen="12.00", antwort="7.xx")
        g._konsole_firmware_erfragen()
        self.assertEqual({"konsole_firmware_angabe"}, {c.args[0] for c in g._save_setting.call_args_list})

    def test_die_liste_reicht_von_1_xx_bis_13_xx_oder_neuer_und_beginnt_mit_nicht_angeben(self) -> None:
        g = self._gui()
        g._konsole_firmware_erfragen()
        self.assertEqual(["konsole_fw.keine"] + ["%d.xx" % n for n in range(1, 13)] + ["konsole_fw.neuer"], g._dialog_eintraege)

    def test_dreizehn_oder_neuer(self) -> None:
        g = self._gui(antwort="konsole_fw.neuer")
        self.assertEqual("13.99", g._konsole_firmware_erfragen())
        self.assertEqual("13", g._speicher["konsole_firmware_angabe"])

    def test_nicht_angeben_und_schliessen_heissen_nicht_noch_einmal_fragen(self) -> None:
        for antwort in ("konsole_fw.keine", ""):
            with self.subTest(antwort=antwort):
                g = self._gui(antwort=antwort)
                self.assertEqual("", g._konsole_firmware_erfragen())
                self.assertEqual("keine", g._speicher["konsole_firmware_angabe"])
                self.assertEqual("", g._konsole_fw_bekannt(), "leer = nicht angegeben, nicht None = ungefragt")
                self.assertEqual(["main.konsole_fw_keine"], g._log)

    def test_kommt_gar_keine_antwort_wird_nichts_gemerkt(self) -> None:
        """Das Hauptfenster ist weg (``_im_hauptfaden`` liefert ``None``): kein "Nicht angeben" auf Vorrat."""
        g = self._gui(antwort=None)
        self.assertEqual("", g._konsole_firmware_erfragen())
        g._save_setting.assert_not_called()
        self.assertIsNone(g._konsole_fw_bekannt())


class PlanTests(unittest.TestCase):
    """``_backport_plan``: braucht das Spiel BACKPORT, und fuer welche Stufe?"""

    @staticmethod
    def _gui(bekannt, antwort=""):
        g = GUI.__new__(GUI)
        g._konsole_fw_bekannt = mock.Mock(return_value=bekannt)
        g._konsole_firmware_erfragen = mock.Mock(return_value=antwort)
        g._backport_firmwares = lambda: STUFEN
        return g

    def test_das_ziel_ist_die_hoechste_stufe_mit_bibliotheken_nicht_ueber_der_konsole(self) -> None:
        for konsole, spiel, erwartet in (("7.99", _f("10.00", "11.20"), ("7.99", 7)), ("12.00", _f("13.00", "13.00"), ("12.00", 7)),
                                         ("5.99", _f("10.00", "11.20"), ("5.99", 5)), ("6.50", _f("7.00", "9.60"), ("6.50", 6))):
            with self.subTest(konsole=konsole):
                self.assertEqual(erwartet, self._gui(konsole)._backport_plan(spiel, erfragen=False))

    def test_unter_der_niedrigsten_stufe_gibt_es_kein_ziel(self) -> None:
        self.assertIsNone(self._gui("3.99")._backport_plan(_f(), erfragen=False))

    def test_reicht_die_konsole_oder_ist_das_spiel_herabgesetzt_gibt_es_keinen_plan(self) -> None:
        self.assertIsNone(self._gui("12.00")._backport_plan(_f("10.00", "11.20"), erfragen=False))
        self.assertIsNone(self._gui("7.99")._backport_plan(_f(backport=5, backport_firmware="7.00"), erfragen=False))
        self.assertIsNone(self._gui("7.99")._backport_plan(fc.QuellFakten(), erfragen=False))
        self.assertIsNone(self._gui("7.99")._backport_plan(None, erfragen=False))

    def test_unbekannt_fragt_nur_mit_erlaubnis_einmal(self) -> None:
        g = self._gui(None, antwort="7.99")
        self.assertIsNone(g._backport_plan(_f(), erfragen=False))
        g._konsole_firmware_erfragen.assert_not_called()
        self.assertEqual(("7.99", 7), g._backport_plan(_f(), erfragen=True))
        g._konsole_firmware_erfragen.assert_called_once_with()

    def test_nicht_angegeben_gibt_keinen_plan_und_fragt_nicht_noch_einmal(self) -> None:
        g = self._gui("")
        self.assertIsNone(g._backport_plan(_f(), erfragen=True))
        g._konsole_firmware_erfragen.assert_not_called()
        g = self._gui(None, antwort="")
        self.assertIsNone(g._backport_plan(_f(), erfragen=True))

    def test_ein_spiel_ohne_angaben_loest_keine_frage_nach_der_firmware_aus(self) -> None:
        g = self._gui(None, antwort="7.99")
        for fakten in (fc.QuellFakten(), _f("0.00", "0.00"), _f(backport=5, backport_firmware="7.00")):
            self.assertIsNone(g._backport_plan(fakten, erfragen=True))
        g._konsole_firmware_erfragen.assert_not_called()


class _Stand:
    @staticmethod
    def gui(*, fakten=None, plan=("7.99", 7), backport_an=False, cli=False, ja=True):
        g = GUI.__new__(GUI)
        stand = {"backport_integrate_var": backport_an}
        g._tk_wert = lambda name, vorgabe=None: stand.get(name, vorgabe)
        g._set_status = lambda *_a, **_k: None
        g._log = []
        g._append_to_log = g._log.append
        g._t = lambda schluessel, **w: schluessel + ("|" + ",".join("%s=%s" % kv for kv in sorted(w.items())) if w else "")
        g._cli_mode = cli
        g.is_running = True
        g._quellfakten_der_quelle = mock.Mock(return_value=fakten)
        g._backport_plan = mock.Mock(return_value=plan)
        g._backport_einschalten = mock.Mock()
        g._ask_yesno_threadsafe = mock.Mock(return_value=ja)
        return g


class FrageTests(unittest.TestCase):
    def test_gibt_es_einen_plan_wird_gefragt_und_mit_ja_eingeschaltet(self) -> None:
        g = _Stand.gui(fakten=_f("10.00", "11.20"))
        g._backport_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ask_yesno_threadsafe.assert_called_once()
        titel, text = g._ask_yesno_threadsafe.call_args.args
        self.assertEqual("dialog.title.backport_empfohlen", titel)
        self.assertEqual("dialog.msg.backport_empfohlen|konsole=7.xx,spiel=11.20,ziel=7", text)
        self.assertTrue(g._ask_yesno_threadsafe.call_args.kwargs.get("default_yes"), "vorbelegt ist Ja")
        g._backport_einschalten.assert_called_once_with(7)
        self.assertEqual(["main.backport_eingeschaltet|spiel=11.20,ziel=7"], g._log)
        g._backport_plan.assert_called_once()
        self.assertIs(True, g._backport_plan.call_args.kwargs["erfragen"], "mit Fenster darf nach der Firmware gefragt werden")

    def test_eine_gemessene_firmware_wird_im_text_genannt_wie_gemessen(self) -> None:
        g = _Stand.gui(fakten=_f("13.00", "13.00"), plan=("12.00", 7))
        g._backport_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        self.assertIn("konsole=12.00", g._ask_yesno_threadsafe.call_args.args[1])
        g._backport_einschalten.assert_called_once_with(7)

    def test_nein_laesst_es_aus_und_das_protokoll_sagt_es(self) -> None:
        g = _Stand.gui(fakten=_f(), ja=False)
        g._backport_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._backport_einschalten.assert_not_called()
        self.assertEqual(["main.backport_bleibt_aus|konsole=7.xx,spiel=11.20"], g._log)

    def test_ohne_plan_keine_frage(self) -> None:
        g = _Stand.gui(fakten=_f(), plan=None)
        g._backport_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ask_yesno_threadsafe.assert_not_called()
        self.assertEqual([], g._log)

    def test_ein_schon_angehakter_backport_wird_nicht_einmal_nachgesehen(self) -> None:
        g = _Stand.gui(fakten=_f(), backport_an=True)
        g._quellfakten_der_quelle = mock.Mock(side_effect=AssertionError("nicht noetig"))
        g._backport_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._quellfakten_der_quelle.assert_not_called()
        g._backport_plan.assert_not_called()

    def test_eine_nicht_lesbare_quelle_keine_frage(self) -> None:
        g = _Stand.gui(fakten=None)
        g._backport_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._backport_plan.assert_not_called()
        g._ask_yesno_threadsafe.assert_not_called()

    def test_sammelkonvertierung_und_andere_modi_fragen_nie(self) -> None:
        for modus in ("batch_convert", "inspect"):
            with self.subTest(modus=modus):
                g = _Stand.gui(fakten=_f())
                g._backport_vor_dem_lauf_klaeren(modus, "C:/x")
                g._quellfakten_der_quelle.assert_not_called()
                g._ask_yesno_threadsafe.assert_not_called()

    def test_die_kommandozeile_fragt_nie_und_nicht_nach_der_firmware_nur_ein_hinweis(self) -> None:
        g = _Stand.gui(fakten=_f(), cli=True)
        g._backport_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ask_yesno_threadsafe.assert_not_called()
        g._backport_einschalten.assert_not_called()
        self.assertIs(False, g._backport_plan.call_args.kwargs["erfragen"])
        self.assertEqual(["main.integrate_backport_empfohlen|konsole=7.xx,spiel=11.20"], g._log)

    def test_wird_der_lauf_waehrend_der_pruefung_beendet_kommt_keine_frage(self) -> None:
        g = _Stand.gui(fakten=_f())

        def beenden(_src):
            g.is_running = False
            return _f()

        g._quellfakten_der_quelle = mock.Mock(side_effect=beenden)
        g._backport_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._backport_plan.assert_not_called()
        g._ask_yesno_threadsafe.assert_not_called()


class EinschaltenTests(unittest.TestCase):
    @staticmethod
    def _gui():
        g = GUI.__new__(GUI)
        g.backport_integrate_var = mock.Mock()
        g.backport_fw_var = mock.Mock()
        g._on_integration_changed = mock.Mock()
        g._save_setting = mock.Mock()
        g.root = mock.Mock()
        return g

    def test_im_hauptfaden_haken_firmware_und_listen(self) -> None:
        g = self._gui()
        g._backport_einschalten(7)
        self.assertEqual({"backport_integrate_var": True, "backport_fw_var": "7"}, g._lauf_variablen)
        g.backport_integrate_var.set.assert_called_once_with(True)
        g.backport_fw_var.set.assert_called_once_with("7")
        g._save_setting.assert_called_once_with("integrate_backport_fw", "7")
        g._on_integration_changed.assert_called_once_with()

    def test_im_arbeitsfaden_gilt_der_stand_sofort_und_das_fenster_folgt(self) -> None:
        g = self._gui()
        g._lauf_variablen = {"ampr_integrate_var": True}
        faden = threading.Thread(target=lambda: g._backport_einschalten(7))
        faden.start()
        faden.join(10)
        self.assertEqual({"ampr_integrate_var": True, "backport_integrate_var": True, "backport_fw_var": "7"}, g._lauf_variablen)
        g.backport_integrate_var.set.assert_not_called()                  # Tk nur im Hauptfaden
        verzoegert, = g.root.after.call_args.args[1:]
        verzoegert()
        g.backport_integrate_var.set.assert_called_once_with(True)
        g._on_integration_changed.assert_called_once_with()


class BatchBackportTests(unittest.TestCase):
    """Sammelkonvertierung: BACKPORT je Spiel mit der Zielstufe (``_batch_emulatoren_klaeren``)."""

    @staticmethod
    def _gui(fakten: dict, *, bekannt="7.99", antwort="7.99", basis=None, cli=False, ja=True, fw_basis="6"):
        g = GUI.__new__(GUI)
        stand = dict(basis or {})
        stand.setdefault("backport_fw_var", fw_basis)
        g._tk_wert = lambda name, vorgabe=None: stand.get(name, vorgabe)
        g._set_status = lambda *_a, **_k: None
        g._log = []
        g._append_to_log = g._log.append
        g._t = lambda schluessel, **w: schluessel + ("|" + ",".join("%s=%s" % kv for kv in sorted(w.items())) if w else "")
        g._cli_mode = cli
        g.root = object()
        g.is_running = True
        g._ampr_auswahl_beim_start = lambda: {"0.4.2.1 NG": {"variant": "ng"}}
        g._quellfakten_der_quelle = mock.Mock(side_effect=lambda q: fakten.get(q))
        g._konsole_fw_bekannt = mock.Mock(return_value=bekannt)
        g._konsole_firmware_erfragen = mock.Mock(return_value=antwort)
        g._backport_firmwares = lambda: STUFEN
        g._ask_yesno_threadsafe = mock.Mock(return_value=ja)
        g._lauf_variablen = {"backport_fw_var": fw_basis}
        return g

    def test_nur_die_spiele_die_mehr_verlangen_bekommen_backport_mit_der_zielstufe(self) -> None:
        fakten = {"C:/A": _f("10.00", "11.20"), "C:/B": _f("5.00", "5.00"), "C:/C": _f("12.00", "12.00")}
        g = self._gui(fakten)
        g._batch_emulatoren_klaeren(["C:/A", "C:/B", "C:/C"])
        g._ask_yesno_threadsafe.assert_called_once()
        self.assertIn("batch.emu_zeile_backport|anzahl=2,namen=A, C", g._ask_yesno_threadsafe.call_args.args[1])
        self.assertEqual({"C:/A": {"backport_integrate_var": True}, "C:/C": {"backport_integrate_var": True}}, g._batch_je_spiel)
        self.assertIn("batch.emu_eingeschaltet|anzahl=2,emulator=BACKPORT (7.xx)", g._log)

    def test_die_zielstufe_liegt_unter_der_konsole_wenn_fuer_sie_keine_bibliotheken_da_sind(self) -> None:
        g = self._gui({"C:/A": _f("13.00", "13.00")}, bekannt="12.00")
        g._batch_emulatoren_klaeren(["C:/A"])
        self.assertEqual(7, g._batch_backport_fw)
        self.assertIn("emulator=BACKPORT (7.xx)", "\n".join(g._log))

    def test_die_firmware_gilt_je_spiel_und_wird_danach_zurueckgestellt(self) -> None:
        g = self._gui({"C:/A": _f("10.00", "11.20"), "C:/B": _f("5.00", "5.00")})
        g._batch_emulatoren_klaeren(["C:/A", "C:/B"])
        g._batch_emu_anwenden("C:/A")
        self.assertEqual((True, "7"), (g._lauf_variablen["backport_integrate_var"], g._lauf_variablen["backport_fw_var"]))
        g._batch_emu_anwenden("C:/B")
        self.assertEqual((False, "6"), (g._lauf_variablen["backport_integrate_var"], g._lauf_variablen["backport_fw_var"]),
                         "Spiel B bekommt weder den Haken noch die Firmware von Spiel A")

    def test_ein_gesetztes_backport_kaestchen_wird_nicht_noch_einmal_gefragt_und_seine_firmware_bleibt(self) -> None:
        g = self._gui({"C:/A": _f()}, basis={"backport_integrate_var": True})
        g._batch_emulatoren_klaeren(["C:/A"])
        g._ask_yesno_threadsafe.assert_not_called()
        g._konsole_fw_bekannt.assert_not_called()
        g._batch_emu_anwenden("C:/A")
        self.assertEqual("6", g._lauf_variablen["backport_fw_var"])

    def test_ist_die_firmware_unbekannt_wird_einmal_gefragt_wenn_ein_spiel_etwas_verlangt(self) -> None:
        g = self._gui({"C:/A": _f(), "C:/B": _f()}, bekannt=None, antwort="7.99")
        g._batch_emulatoren_klaeren(["C:/A", "C:/B"])
        g._konsole_firmware_erfragen.assert_called_once_with()
        self.assertEqual({"C:/A", "C:/B"}, set(g._batch_je_spiel))

    def test_verlangt_kein_spiel_etwas_wird_die_firmware_nicht_erfragt(self) -> None:
        g = self._gui({"C:/A": fc.QuellFakten(), "C:/B": _f("0.00", "0.00"), "C:/C": _f(backport=5, backport_firmware="7.00")},
                      bekannt=None)
        g._batch_emulatoren_klaeren(["C:/A", "C:/B", "C:/C"])
        g._konsole_firmware_erfragen.assert_not_called()
        g._ask_yesno_threadsafe.assert_not_called()

    def test_nicht_angegeben_heisst_kein_backport_in_der_sammelfrage(self) -> None:
        g = self._gui({"C:/A": _f()}, bekannt=None, antwort="")
        g._batch_emulatoren_klaeren(["C:/A"])
        g._ask_yesno_threadsafe.assert_not_called()
        self.assertEqual({}, g._batch_je_spiel)

    def test_unter_der_niedrigsten_stufe_gibt_es_kein_ziel_und_keine_zeile(self) -> None:
        g = self._gui({"C:/A": _f()}, bekannt="3.99")
        g._batch_emulatoren_klaeren(["C:/A"])
        g._ask_yesno_threadsafe.assert_not_called()
        self.assertEqual(0, g._batch_backport_fw)

    def test_auf_der_kommandozeile_wird_die_firmware_nie_erfragt_und_bekannt_nur_geschrieben(self) -> None:
        g = self._gui({"C:/A": _f()}, bekannt=None, cli=True)
        g._batch_emulatoren_klaeren(["C:/A"])
        g._konsole_firmware_erfragen.assert_not_called()
        self.assertEqual([], g._log)
        g = self._gui({"C:/A": _f()}, bekannt="7.99", cli=True)
        g._batch_emulatoren_klaeren(["C:/A"])
        g._ask_yesno_threadsafe.assert_not_called()
        self.assertEqual({}, g._batch_je_spiel)
        self.assertEqual(["[A] BACKPORT: main.integrate_backport_empfohlen|konsole=7.xx,spiel=11.20"], g._log)

    def test_mit_nein_bleibt_alles_wie_eingestellt(self) -> None:
        g = self._gui({"C:/A": _f()}, ja=False)
        g._batch_emulatoren_klaeren(["C:/A"])
        self.assertEqual({}, g._batch_je_spiel)
        g._batch_emu_anwenden("C:/A")
        self.assertEqual((False, "6"), (g._lauf_variablen["backport_integrate_var"], g._lauf_variablen["backport_fw_var"]))

    def test_die_vorpruefung_fragt_nach_der_arbeitskopie_auch_wegen_backport(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ordner = os.path.join(tmp, "Spiel")
            os.makedirs(ordner)
            g = GUI.__new__(GUI)
            g.root = object()
            g._t = lambda schluessel, **w: schluessel
            g._batch_ueberschreiben = False
            g._batch_arbeitskopie_vorab = None
            g._arbeitskopie_vorher_aktiv = lambda: False
            g._tk_wert = lambda name, vorgabe=None: False
            g._batch_je_spiel = {ordner: {"backport_integrate_var": True}}
            g._ask_yesno_threadsafe = mock.Mock(return_value=True)
            g._batch_vorpruefung([ordner], tmp, "ffpkg")
            g._ask_yesno_threadsafe.assert_called_once()


class FensterTests(unittest.TestCase):
    """Paketbau im PS5-Fenster: BACKPORT als Hinweiszeile in der gesammelten Frage (``_backport_zeile``)."""

    @staticmethod
    def _fenster(plan):
        from ps5_validator.ui import ps5_pkg_fenster as fz
        f = fz.Ps5PkgFenster.__new__(fz.Ps5PkgFenster)
        f.t = lambda schluessel, **w: schluessel + ("|" + ",".join("%s=%s" % kv for kv in sorted(w.items())) if w else "")
        f.g = mock.Mock()
        f.g._backport_plan.return_value = plan
        f.g._konsole_fw_anzeige = GUI._konsole_fw_anzeige
        return f

    def test_gibt_es_einen_plan_steht_die_zeile_da_und_darf_nach_der_firmware_gefragt_werden(self) -> None:
        f = self._fenster(("7.99", 7))
        fakten = _f("10.00", "11.20")
        self.assertEqual("ps5pkg.emu_zeile_backport|konsole=7.xx,spiel=11.20", f._backport_zeile(fakten))
        f.g._backport_plan.assert_called_once_with(fakten, erfragen=True)

    def test_eine_gemessene_firmware_steht_wie_gemessen_da(self) -> None:
        self.assertIn("konsole=12.00", self._fenster(("12.00", 7))._backport_zeile(_f("13.00", "13.00")))

    def test_ohne_plan_keine_zeile(self) -> None:
        self.assertEqual("", self._fenster(None)._backport_zeile(_f()))


class QuelltextTests(unittest.TestCase):
    def test_die_frage_steht_nach_ampr_und_vor_dem_ng_hinweis_und_den_anderen_rueckfragen(self) -> None:
        text = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        ampr = text.index("self._ampr_vor_dem_lauf_klaeren(mode, src)")
        backport = text.index("self._backport_vor_dem_lauf_klaeren(mode, src)", ampr)
        ng = text.index("self._ampr_ng_vor_dem_lauf_hinweisen()", ampr)
        playgo = text.index("self._playgo_vor_dem_lauf_klaeren(mode, src)", ampr)
        self.assertLess(ampr, backport)
        self.assertLess(backport, ng)
        self.assertLess(ng, playgo)
        self.assertEqual(1, text.count("self._backport_vor_dem_lauf_klaeren(mode, src)"))

    def test_die_vorhandene_firmware_der_konsole_wird_nicht_ueberschrieben(self) -> None:
        """Die Einstellung ``konsole_firmware`` schreibt die Ansicht KONSOLE (``_konsole_firmware``); die Angabe des Anwenders
        hat einen eigenen Schluessel."""
        text = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        self.assertIn('_KONSOLE_FW_SETTING = "konsole_firmware_angabe"', text)
        self.assertEqual(1, text.count("def _konsole_firmware(self)"), "die vorhandene Methode wird weiter benutzt, nicht ersetzt")

    def test_das_einstellungsfenster_kennt_die_firmware_der_konsole(self) -> None:
        text = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        self.assertIn('self._t("settings_dialog.konsole_fw_section")', text)
        self.assertIn("self._save_setting(self._KONSOLE_FW_SETTING, neu)", text)

    def test_alle_texte_gibt_es_in_fuenf_sprachen_mit_gleichen_platzhaltern(self) -> None:
        from ps5_validator.utils.i18n import STRINGS
        erwartet = {
            "status.backport_pruefen": [], "dialog.title.konsole_fw": [], "dialog.msg.konsole_fw": [],
            "konsole_fw.keine": [], "konsole_fw.neuer": [], "main.konsole_fw_gemerkt": ["firmware"], "main.konsole_fw_keine": [],
            "dialog.title.backport_empfohlen": [],
            "dialog.msg.backport_empfohlen": ["konsole", "spiel", "ziel", "ziel"],
            "main.integrate_backport_empfohlen": ["konsole", "spiel"], "main.backport_bleibt_aus": ["konsole", "spiel"],
            "main.backport_eingeschaltet": ["spiel", "ziel"],
            "settings_dialog.konsole_fw_section": [], "settings_dialog.konsole_fw_hint": [],
            "settings_dialog.konsole_fw_ungefragt": [], "batch.emu_zeile_backport": ["anzahl", "namen"],
            "ps5pkg.emu_zeile_backport": ["konsole", "spiel"], "ps5pkg.emu_titel": [], "ps5pkg.emu_frage": ["liste"],
            "ps5pkg.emu_log": [], "ps5pkg.emu_abgebrochen": [], "ps5pkg.emu_pruefen": [],
        }
        for schluessel, platzhalter in erwartet.items():
            with self.subTest(schluessel=schluessel):
                self.assertEqual({"de", "en", "es", "it", "fr"}, set(STRINGS[schluessel]))
                for sprache, text in STRINGS[schluessel].items():
                    self.assertTrue(text.strip(), sprache)
                    self.assertEqual(sorted(platzhalter), sorted(re.findall(r"\{(\w+)\}", text)), sprache)


if __name__ == "__main__":
    unittest.main()
