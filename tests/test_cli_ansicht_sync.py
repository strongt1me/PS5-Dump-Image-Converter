# -*- coding: utf-8 -*-
"""Der CLI-Modus muss die Konfig-Anzeige an die echte Aufgabe angleichen.

Hintergrund (13.09.2026): Das CLI-Fortschrittsfenster zeigte den Standard-
Aufbauzustand - Kopf "1. Dump-Ordner konvertieren" und die BAUFORM-Auswahl -,
obwohl in Wahrheit eine andere Aufgabe mit einem anderen Zielformat lief.
Ursache: ``_run_cli`` setzte ``current_mode.set(mode)`` statt
``_set_mode_from_sidebar(mode)`` und zog nach dem Setzen des Zielformats die
BAUFORM-Sichtbarkeit nicht nach.

Zwei Waechter:
* verhaltensbasiert - die CLI-Setup-Folge erzeugt eine stimmige Ansicht;
* quelltextbasiert - ``_run_cli`` benutzt diese Folge wirklich.
"""
from __future__ import annotations

import io
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HAUPTDATEI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "PS5ImageConverter_Pro_FINAL_revised.py")

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover
    TK_DA = False
    _WURZEL = None


def _lade_hauptprogramm():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class CliAnsichtSyncVerhalten(unittest.TestCase):
    """Die Folge, die _run_cli fahren soll, ergibt eine stimmige Ansicht."""

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)
        cls.dummy = tempfile.mkdtemp(prefix="cli_sync_")

    def _cli_setup(self, mode, fmt):
        """Bildet die (reparierte) CLI-Setup-Folge nach."""
        self.app.source_path.set(self.dummy)
        self.app._set_mode_from_sidebar(mode)
        if fmt:
            self.app.target_format.set(self.app._t("format." + fmt))
            self.app._format_hinweis_setzen(mode)
        _WURZEL.update_idletasks()

    def test_kopf_folgt_der_aufgabe(self):
        self._cli_setup("pack_file", "ffpkg")  # Aufgabe 3, exFAT -> .ffpkg
        erwartet = self.app._t("mode.pack_file").split(" (")[0]
        self.assertEqual(self.app.header_label.cget("text"), erwartet)

    def test_bauform_verborgen_bei_ffpkg(self):
        self._cli_setup("pack_file", "ffpkg")
        self.assertFalse(self.app.bauform_combo.winfo_ismapped(),
                         "BAUFORM darf bei .ffpkg nicht sichtbar sein")

    def test_bauform_sichtbar_bei_ffpfsc(self):
        self._cli_setup("pack_folder", "ffpfsc")  # Aufgabe 1 -> .ffpfsc
        self.assertTrue(self.app.bauform_combo.winfo_ismapped(),
                        "BAUFORM muss bei .ffpfsc sichtbar sein")


class RunCliNutztAnsichtsSync(unittest.TestCase):
    """_run_cli muss die Ansicht wirklich angleichen (nicht nur current_mode.set)."""

    @classmethod
    def setUpClass(cls):
        quelle = open(HAUPTDATEI, encoding="utf-8").read()
        m = re.search(r"\ndef _run_cli\(.*?\n(?=\ndef |\Z)", quelle, re.S)
        assert m, "_run_cli nicht gefunden"
        cls.rumpf = m.group(0)

    def test_setzt_modus_ueber_sidebar_helfer(self):
        self.assertIn("_set_mode_from_sidebar(", self.rumpf,
                      "_run_cli soll _set_mode_from_sidebar nutzen, damit Kopf/"
                      "Formatoptionen/BAUFORM zur echten Aufgabe passen.")

    def test_zieht_bauform_nach_dem_zielformat_nach(self):
        # Nach target_format.set(...) muss die Sichtbarkeit neu gesetzt werden.
        pos_format = self.rumpf.find("target_format.set(")
        self.assertGreater(pos_format, -1, "target_format.set fehlt in _run_cli")
        rest = self.rumpf[pos_format:]
        self.assertTrue(
            "_format_hinweis_setzen(" in rest or "_bauform_sichtbarkeit_setzen(" in rest,
            "Nach dem Setzen des Zielformats muss die BAUFORM-Sichtbarkeit "
            "nachgezogen werden.")

    def test_warnt_wenn_das_format_still_wechselt(self) -> None:
        """17.10.2026: '--format folder' ohne AMPR EMU/BACKPORT wurde klanglos zu '.ffpfsc'.

        Gemessen an einem echten Dump (PPSA19015 Arcade Game Zone, 618 MB): ohne jede
        Integration lief die Aufgabe durch, aber das Protokoll sagte nirgends, dass
        statt "Dump-Ordner" tatsaechlich ".ffpfsc" entstand - erst die Ausgabedatei
        verriet es. ``_on_integration_changed`` (ueber ``_refresh_target_format_options``)
        wirft ein nicht mehr gueltiges Label auf den ersten Eintrag zurueck; _run_cli
        muss das danach erkennen und melden, statt es durchzulassen (Projektregel
        "keine stillen Aktionen").
        """
        pos_integration = self.rumpf.find("_on_integration_changed(")
        self.assertGreater(pos_integration, -1, "_on_integration_changed fehlt in _run_cli")
        vorher = self.rumpf[:pos_integration]
        nachher = self.rumpf[pos_integration:]
        self.assertIn("angefordertes_label", vorher,
                     "Das angeforderte Format muss VOR der Aktualisierung gemerkt werden - "
                     "sonst ist der Vergleich danach gegen sich selbst.")
        self.assertIn("target_format.get() != angefordertes_label", nachher,
                     "_run_cli muss nach _on_integration_changed pruefen, ob das "
                     "Zielformat noch das angeforderte ist.")
        self.assertIn("WARNUNG", nachher[nachher.find("target_format.get() != angefordertes_label"):],
                     "Ein stiller Formatwechsel braucht eine gedruckte Meldung.")


class AmprManagerUeberCliErreichbar(unittest.TestCase):
    """17.10.2026: '--mode ampr_manager' war seit der Umbenennung von Aufgabe 7 (12.10.2026) nicht mehr
    erreichbar - valid_modes kam nur noch aus _MODE_OPTIONS (den acht Aufgaben der Seitenleiste), und
    ampr_manager steht seitdem nicht mehr darin (KONSOLE Knopf 9). Jeder --ampr-*-Aufruf endete mit
    "[FEHLER] Unbekannter Modus: ampr_manager", bevor die eigentliche --ampr-action-Pruefung je lief -
    echt am Programm gemessen, nicht nur am Quelltext."""

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()

    def test_ampr_manager_kommt_bis_zur_aktionspruefung(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ampr_cli_quelle_") as quelle:
            args = self.haupt._build_cli_parser().parse_args(
                ["--cli", "--mode", "ampr_manager", "--source", quelle])
            ausgabe = io.StringIO()
            with redirect_stderr(ausgabe):
                rc = self.haupt._run_cli(args)
        text = ausgabe.getvalue()
        self.assertNotIn("Unbekannter Modus", text,
                         "ampr_manager muss die Modus-Pruefung bestehen (nur ueber --mode waehlbar).")
        self.assertIn("--ampr-action", text,
                     "Ohne --ampr-action soll die Aktionspruefung des AMPR EMU Manager greifen.")
        self.assertEqual(2, rc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
