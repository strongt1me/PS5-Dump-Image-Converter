# -*- coding: utf-8 -*-
"""Firmware-Zeilen ueber dem Cover der Seitenleiste (Nutzerwunsch 11.11.2026).

Gleich oberhalb des Spielcovers steht die Firmware, die das Spiel braucht ("Benoetigte Firmware: 4.51"); ist ein
Backport eingebaut, darunter dessen Firmware ("Backport: Firmware 7"). Der Backport zeigt sich an den Bibliotheken
(``fakelib/FW<n>`` oder ``fakelib/fw<nn>``), nicht an einer param.json - ein Dump ohne Marke gilt als nicht
zurueckportiert. Die beiden Zeilen sind immer zwei Zeilen hoch, damit das Cover nicht springt, wenn der
Backport-Befund aus dem Faden nachtraeglich eintrifft.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("sidebar_firmware")

from ps5_validator.utils.i18n import STRINGS                # noqa: E402

HAUPT = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"

try:
    import tkinter as tk
    from PIL import Image
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                            # pragma: no cover
    TK_DA = False


def _lade():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPT)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


class _SofortThread:
    """Ersatz fuer ``threading.Thread``: laeuft gleich im Aufrufer (der Test hat keine Hauptschleife)."""

    def __init__(self, target=None, **_kw) -> None:
        self._ziel = target

    def start(self) -> None:
        self._ziel()


class FirmwareKurzTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.klasse = _lade().PS5ConverterGUI

    def test_formen(self):
        f = self.klasse._firmware_kurz
        self.assertEqual("4.51", f("04.51.00.00"))
        self.assertEqual("10.00", f("10.00.00.00"))
        self.assertEqual("7.00", f("7.00"))
        self.assertEqual("", f("–"))
        self.assertEqual("", f(""))
        self.assertEqual("", f(None))
        self.assertEqual("", f("Unbekannt"))

    def test_texte_in_allen_sprachen(self):
        for schluessel in ("sidebar.fw_required", "sidebar.fw_backport"):
            for sprache in ("de", "en", "es", "it", "fr"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    self.assertIn("{fw}", STRINGS[schluessel][sprache])


class WaechterTests(unittest.TestCase):
    """Die Hoehe der Zeilen geht in jede Rechnung des Cover-Platzes ein - sonst ueberlappen sie sich bei niedrigem Fenster."""

    @classmethod
    def setUpClass(cls) -> None:
        import ast
        text = HAUPT.read_text(encoding="utf-8")
        zeilen = text.splitlines()
        cls.funktionen = {}
        for k in ast.walk(ast.parse(text)):
            if isinstance(k, ast.FunctionDef):
                cls.funktionen[k.name] = "\n".join(zeilen[k.lineno - 1:k.end_lineno])

    def test_die_hoehe_geht_in_breite_zentrierung_und_vorschau_ein(self):
        for name in ("_sidebar_cover_width", "_center_sidebar_cover", "_update_sidebar_preview"):
            with self.subTest(name):
                self.assertIn("_sidebar_fw_hoehe", self.funktionen[name])

    def test_die_zeilen_verschwinden_mit_dem_cover(self):
        quelle = self.funktionen["_update_sidebar_preview"]
        self.assertGreaterEqual(quelle.count("_sidebar_fw_label.pack_forget()"), 2)     # kein Cover / Fehlerzweig

    def test_die_ansichten_nehmen_sie_mit(self):
        self.assertIn('"_sidebar_fw_label"', self.funktionen["_ansicht_erste_widgets"])

    def test_die_infobox_fuettert_sie(self):
        self.assertIn("_sidebar_firmware_aktualisieren(", self.funktionen["_update_info_box"])


@unittest.skipUnless(TK_DA, "keine Anzeige")
class FensterTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade()
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="ps5conv_fw_")
        self.addCleanup(tmp.cleanup)
        self.ohne = os.path.join(tmp.name, "ohne")
        self.mit = os.path.join(tmp.name, "mit")
        os.makedirs(self.ohne)
        os.makedirs(os.path.join(self.mit, "fakelib"))
        Path(self.mit, "fakelib", "FW7").touch()
        Path(self.mit, "fakelib", "libc.prx").write_bytes(b"x")
        self.app._sidebar_fw_merker = {}
        self.app._sidebar_fw_quelle = None
        self.app._sidebar_fw_backport = ""
        for muster in (mock.patch.object(self.haupt.threading, "Thread", _SofortThread),
                       mock.patch.object(self.app, "_spaeter_im_fenster",
                                         side_effect=lambda _f, cb, *a: (cb(*a), True)[1])):
            muster.start()
            self.addCleanup(muster.stop)

    def _text(self) -> str:
        return str(self.app._sidebar_fw_label.cget("text"))

    def test_benoetigte_firmware_ohne_backport(self):
        self.app._sidebar_firmware_aktualisieren({"required_firmware": "04.51.00.00"}, self.ohne)
        zeilen = self._text().split("\n")
        self.assertEqual(2, len(zeilen), "immer zwei Zeilen - das Cover darf nicht springen")
        self.assertEqual(self.app._t("sidebar.fw_required", fw="4.51"), zeilen[0])
        self.assertEqual("", zeilen[1].strip())

    def test_backport_zeile_bei_marke_in_fakelib(self):
        self.app._sidebar_firmware_aktualisieren({"required_firmware": "10.00.00.00"}, self.mit)
        zeilen = self._text().split("\n")
        self.assertEqual(self.app._t("sidebar.fw_required", fw="10.00"), zeilen[0])
        self.assertEqual(self.app._t("sidebar.fw_backport", fw="7"), zeilen[1])

    def test_ein_zwischenstand_ohne_metadaten_nimmt_nichts_weg(self):
        self.app._sidebar_firmware_aktualisieren({"required_firmware": "04.51.00.00"}, self.ohne)
        vorher = self._text()
        self.app._sidebar_firmware_aktualisieren({}, self.ohne)          # Schnellvorschau derselben Quelle
        self.assertEqual(vorher, self._text())

    def test_ein_quellwechsel_leert_die_zeilen(self):
        self.app._sidebar_firmware_aktualisieren({"required_firmware": "10.00.00.00"}, self.mit)
        self.app._sidebar_firmware_aktualisieren({}, self.ohne)          # neue Quelle, noch ohne Metadaten
        self.assertEqual(["", ""], [z.strip() for z in self._text().split("\n")])

    def test_zeilen_stehen_ueber_dem_cover_ohne_ueberlappung(self):
        app = self.app
        cover = Image.new("RGB", (512, 512), (40, 90, 160))
        app.source_path = tk.StringVar(master=_WURZEL, value=self.ohne)
        try:
            app._update_sidebar_preview(cover, "Testspiel")
            _WURZEL.update_idletasks()
            fw, bild, titel = (app._sidebar_fw_label, app._sidebar_preview_img_label,
                               app._sidebar_preview_title_label)
            self.assertEqual("pack", fw.winfo_manager())
            self.assertEqual("pack", bild.winfo_manager())
            slaves = [str(w) for w in fw.master.pack_slaves()]
            self.assertLess(slaves.index(str(fw)), slaves.index(str(bild)), "die Zeilen stehen ueber dem Cover")
            self.assertLess(slaves.index(str(bild)), slaves.index(str(titel)))
            # Verschwindet das Cover, verschwinden die Zeilen mit.
            app._update_sidebar_preview(None, "")
            self.assertEqual("", fw.winfo_manager())
        finally:
            app._update_sidebar_preview(None, "")


if __name__ == "__main__":
    unittest.main()
