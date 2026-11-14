# -*- coding: utf-8 -*-
"""Das Fenster "Geraete im Netz" (``ui/geraete_fenster.py``): Suche im Faden, Liste, Quelle/Ziel waehlen, Adresse kopieren (14.11.2026)."""
from __future__ import annotations

import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

from ps5_validator.ui import geraete_fenster as gf           # noqa: E402
from ps5_validator.utils import geraete_suche as gs          # noqa: E402

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:   # noqa: BLE001
    TK_DA = False
    _WURZEL = None

NAS = gs.Geraet("MeinNAS", "192.168.1.20", "smb", 445)
FTP = gs.Geraet("Drucker", "192.168.1.30", "ftp", 21)
PC = gs.Geraet("192.168.1.50", "192.168.1.50", "wsd", 5357)


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class FensterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    @classmethod
    def tearDownClass(cls) -> None:
        zustand = getattr(_WURZEL, "_ablegen_admin_zustand", None)
        if zustand is not None and sys.platform == "win32":
            import ctypes
            user32 = ctypes.windll.user32
            user32.SetWindowLongPtrW.restype = ctypes.c_void_p
            user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
            for hwnd, vorher in zustand["alte"].items():
                user32.SetWindowLongPtrW(hwnd, -4, vorher)
            del _WURZEL._ablegen_admin_zustand

    def setUp(self) -> None:
        self.win = gf.oeffnen(self.app, self.haupt.UI_SCHRIFT, self.haupt.MONO_SCHRIFT, self.haupt.pt)
        self.addCleanup(self._schliessen)
        self.f = self.win._geraete

    def _schliessen(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def warten(self) -> None:
        """Die echte Hauptschleife, bis die Suche gemeldet hat, dass sie fertig ist."""
        def pruefen() -> None:
            if not self.f.suche_laeuft:
                _WURZEL.quit()
            else:
                _WURZEL.after(30, pruefen)
        ids = [_WURZEL.after(30, pruefen), _WURZEL.after(20000, _WURZEL.quit)]
        try:
            _WURZEL.mainloop()
        finally:
            for i in ids:                                                  # ein liegengebliebener Zeitgeber wuerde die naechste Schleife beenden
                try:
                    _WURZEL.after_cancel(i)
                except tk.TclError:
                    pass

    def _suche_mit(self, geraete: "list[gs.Geraet]") -> None:
        def falsche_suche(zeit, melden=None, abbruch=None, **_kw):
            for g in geraete:
                melden(g)
            return list(geraete)
        with mock.patch.object(gf.geraete_suche, "suchen", side_effect=falsche_suche):
            self.f._suchen()
            self.warten()

    def test_am_anfang_ist_alles_gesperrt_ausser_suchen(self) -> None:
        self.assertNotEqual("disabled", str(self.f.suchen_knopf["state"]))
        for knopf in (self.f.stopp_knopf, self.f.quelle_knopf, self.f.ziel_knopf, self.f.kopieren_knopf):
            self.assertEqual("disabled", str(knopf["state"]))

    def test_die_suche_fuellt_die_liste_und_meldet_das_ende(self) -> None:
        self._suche_mit([NAS, FTP, PC])
        self.assertFalse(self.f.suche_laeuft)
        self.assertEqual({"smb|192.168.1.20", "ftp|192.168.1.30", "wsd|192.168.1.50"}, set(self.f.baum.get_children("")))
        self.assertEqual("MeinNAS", self.f.baum.item("smb|192.168.1.20", "text"))
        self.assertIn("Windows-Freigabe", self.f.baum.item("smb|192.168.1.20", "values")[1])
        self.assertIn("3 Gerät", self.f.status_var.get())
        self.assertNotEqual("disabled", str(self.f.suchen_knopf["state"]))

    def test_ohne_treffer_steht_ein_hinweis(self) -> None:
        self._suche_mit([])
        self.assertIn("Nichts gefunden", self.f.status_var.get())

    def test_eine_neue_suche_leert_die_liste(self) -> None:
        self._suche_mit([NAS])
        self._suche_mit([PC])
        self.assertEqual(["wsd|192.168.1.50"], list(self.f.baum.get_children("")))

    def test_eine_ausnahme_in_der_suche_haengt_das_fenster_nicht_auf(self) -> None:
        with mock.patch.object(gf.geraete_suche, "suchen", side_effect=OSError("kein Netz")):
            self.f._suchen()
            self.warten()
        self.assertFalse(self.f.suche_laeuft)
        self.assertNotEqual("disabled", str(self.f.suchen_knopf["state"]))

    def test_nur_smb_und_rechner_lassen_sich_als_quelle_oder_ziel_waehlen(self) -> None:
        self._suche_mit([NAS, FTP])
        self.f.baum.selection_set("ftp|192.168.1.30")
        self.f._zustand_setzen()
        self.assertEqual("disabled", str(self.f.quelle_knopf["state"]))
        self.assertNotEqual("disabled", str(self.f.kopieren_knopf["state"]))
        self.f.baum.selection_set("smb|192.168.1.20")
        self.f._zustand_setzen()
        self.assertNotEqual("disabled", str(self.f.quelle_knopf["state"]))
        self.assertNotEqual("disabled", str(self.f.ziel_knopf["state"]))

    def test_quelle_waehlen_oeffnet_den_dialog_auf_der_freigabe_und_setzt_das_feld(self) -> None:
        self._suche_mit([NAS])
        self.f.baum.selection_set("smb|192.168.1.20")
        with mock.patch.object(gf.filedialog, "askdirectory", return_value="//192.168.1.20/Spiele/PPSA01234") as dialog:
            self.f._waehlen("quelle")
        self.assertEqual("\\\\192.168.1.20\\", dialog.call_args.kwargs["initialdir"])
        self.assertIn("MeinNAS", dialog.call_args.kwargs["title"])
        self.assertEqual("\\\\192.168.1.20\\Spiele\\PPSA01234", self.app.source_path.get())

    def test_ziel_waehlen(self) -> None:
        self._suche_mit([NAS])
        self.f.baum.selection_set("smb|192.168.1.20")
        with mock.patch.object(gf.filedialog, "askdirectory", return_value="D:/Ergebnisse"):
            self.f._waehlen("ziel")
        self.assertEqual("D:/Ergebnisse", self.app.dest_path.get())

    def test_abbrechen_im_dialog_aendert_nichts(self) -> None:
        self._suche_mit([NAS])
        self.f.baum.selection_set("smb|192.168.1.20")
        vorher = self.app.source_path.get()
        with mock.patch.object(gf.filedialog, "askdirectory", return_value=""):
            self.f._waehlen("quelle")
        self.assertEqual(vorher, self.app.source_path.get())

    def test_ein_ftp_geraet_wird_nicht_als_quelle_gesetzt(self) -> None:
        self._suche_mit([FTP])
        self.f.baum.selection_set("ftp|192.168.1.30")
        with mock.patch.object(gf.filedialog, "askdirectory") as dialog:
            self.f._waehlen("quelle")
        dialog.assert_not_called()
        self.assertIn("Windows-Freigabe", self.f.status_var.get())

    def test_adresse_kopieren(self) -> None:
        self._suche_mit([NAS, FTP])
        self.f.baum.selection_set("smb|192.168.1.20")
        self.f._kopieren()
        self.assertEqual("\\\\192.168.1.20\\", self.win.clipboard_get())
        self.f.baum.selection_set("ftp|192.168.1.30")
        self.f._kopieren()
        self.assertEqual("192.168.1.30", self.win.clipboard_get())

    def test_stoppen_bricht_die_laufende_suche_ab(self) -> None:
        freigabe = threading.Event()

        def haengende_suche(zeit, melden=None, abbruch=None, **_kw):
            freigabe.wait(5)
            return []
        with mock.patch.object(gf.geraete_suche, "suchen", side_effect=haengende_suche):
            self.f._suchen()
            self.assertTrue(self.f.suche_laeuft)
            self.assertEqual("disabled", str(self.f.suchen_knopf["state"]), "waehrend der Suche nicht doppelt starten")
            self.assertNotEqual("disabled", str(self.f.stopp_knopf["state"]))
            self.f._stoppen()
            self.assertTrue(self.f._abbrechen)
            freigabe.set()
            self.warten()
        self.assertFalse(self.f.suche_laeuft)


class MenueTests(unittest.TestCase):
    def test_der_eintrag_steht_in_weitere_tools_vor_den_fremdwerkzeugen(self) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        eintraege = [k for k, _b in haupt.PS5ConverterGUI._MORE_TOOLS_ENTRIES]
        self.assertIn("titlebar.geraete", eintraege)
        self.assertLess(eintraege.index("titlebar.abbild_bearbeiten"), eintraege.index("titlebar.geraete"))
        self.assertLess(eintraege.index("titlebar.geraete"), eintraege.index("titlebar.wee_tools"))
        self.assertTrue(callable(getattr(haupt.PS5ConverterGUI, "_show_geraete", None)))

    def test_alle_texte_gibt_es_in_allen_sprachen(self) -> None:
        from ps5_validator.utils import i18n
        schluessel = [k for k in i18n.STRINGS if k.startswith("geraete.")] + ["titlebar.geraete"]
        self.assertGreaterEqual(len(schluessel), 25)
        for k in schluessel:
            for sprache in ("de", "en", "es", "it", "fr"):
                with self.subTest(schluessel=k, sprache=sprache):
                    text = i18n.translate(sprache, k, n=1, pfad="P", text="T", geraet="G")
                    self.assertTrue(text and text != k)


if __name__ == "__main__":
    unittest.main()
