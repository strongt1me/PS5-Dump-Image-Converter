# -*- coding: utf-8 -*-
"""Ein geschlossenes Fenster gibt alles wieder her: GDI-Objekte, Tk-Bilder, Widgets.

Am 05.10.2026 stuerzte die volle Testreihe bei rund 75 Prozent mit ``0x80000003`` ab, mitten in
``create_image``: Der Prozess hatte das Limit von **10 000 GDI-Objekten** erreicht, das Windows je
Prozess erlaubt. Gemessen an einem Fenster, das auf- und wieder zugeht, kamen drei Ursachen zusammen:

1. ``iconbitmap(datei)`` je Toplevel: Tk gibt die geladenen Symbole nie frei - 19 GDI- und 6 USER-Objekte
   je Fenster. Jetzt laedt nur das Hauptfenster die Datei, als Vorgabe fuer alle weiteren.
2. ``LoadImageW`` je Fenster fuer die Taskleiste: nochmal 6 GDI-Objekte, ebenfalls nie freigegeben. Die
   Symbole werden jetzt einmal geladen und geteilt.
3. Eine ``trace_add``-Spur, die das Fenster oder ein Widget haelt: Ihr Tcl-Befehl steht im Befehlsverzeichnis
   des Interpreters und haelt den Rueckruf - und damit Widget, Bilder und Zeichner - fuer immer am Leben
   (``Ps4DumpImageFenster``, ``ChipGruppe``, ``SuchFeld``, ``RunderHaken``, ``Drehknopf``). Dazu hatte jedes
   PS4-Fenster seinen eigenen Zeichner mit bis zu 600 Tk-Bildern.

Gemessen vorher je Fenster: 93 GDI, 8 USER, 69 Tk-Bilder (PS4-Fenster) bzw. 24 GDI, 8 USER (jedes Toplevel
des Programms); nachher 0.
"""
from __future__ import annotations

import ast
import ctypes
import gc
import sys
import tkinter as tk
import unittest
import weakref
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

try:
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover - ohne Anzeige
    TK_DA = False
    _WURZEL = None

from ps5_validator.utils import bibliothek_raster as raster   # noqa: E402


def _gui_objekte() -> tuple[int, int]:
    """(GDI-Objekte, USER-Objekte) dieses Prozesses - nur unter Windows."""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    user32.GetGuiResources.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    prozess = kernel32.GetCurrentProcess()
    return int(user32.GetGuiResources(prozess, 0)), int(user32.GetGuiResources(prozess, 1))


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class SpurTests(unittest.TestCase):
    """``spur_bis_zerstoert``: Die Spur geht mit dem Widget - und das Widget wird frei."""

    def test_die_spur_geht_mit_dem_widget(self) -> None:
        var = tk.StringVar(master=_WURZEL)
        widget = tk.Frame(_WURZEL)
        aufrufe: list[int] = []
        raster.spur_bis_zerstoert(widget, var, lambda *_a: aufrufe.append(1))
        var.set("a")
        self.assertEqual([1], aufrufe)
        widget.destroy()
        var.set("b")
        self.assertEqual([1], aufrufe, "Die Spur lief nach dem Zerstoeren weiter.")
        self.assertEqual((), tuple(var.trace_info()))

    def test_das_widget_wird_frei(self) -> None:
        class Zeile(tk.Frame):
            def __init__(self, master, var):
                super().__init__(master)
                raster.spur_bis_zerstoert(self, var, self._geaendert)

            def _geaendert(self, *_a) -> None:
                pass

        var = tk.StringVar(master=_WURZEL)
        zeile = Zeile(_WURZEL, var)
        merker = weakref.ref(zeile)
        zeile.destroy()
        del zeile
        gc.collect()
        self.assertIsNone(merker(), "Das Widget haengt noch an seiner Spur.")

    def test_eine_spur_ohne_die_hilfe_haelt_das_widget_fest(self) -> None:
        """Die Gegenprobe: So war es - und deshalb gibt es die Hilfe."""
        class Zeile(tk.Frame):
            def __init__(self, master, var):
                super().__init__(master)
                var.trace_add("write", self._geaendert)

            def _geaendert(self, *_a) -> None:
                pass

        var = tk.StringVar(master=_WURZEL)
        zeile = Zeile(_WURZEL, var)
        merker = weakref.ref(zeile)
        zeile.destroy()
        del zeile
        gc.collect()
        self.assertIsNotNone(merker())
        for name in [k for _m, k in var.trace_info()]:
            var.trace_remove("write", name)


@unittest.skipUnless(TK_DA and sys.platform == "win32", "GDI-Objekte gibt es nur unter Windows")
class FensterLeckTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def _messen(self, erzeuger, anzahl: int = 12) -> tuple[float, float]:
        """GDI und USER je Fenster, nachdem es erzeugt, gezeigt und wieder zerstoert wurde."""
        for _ in range(3):                         # Anlauf: Caches, Schriften, geteilte Symbole
            erzeuger().destroy()
        gc.collect()
        _WURZEL.update()
        gdi0, user0 = _gui_objekte()
        for _ in range(anzahl):
            fenster = erzeuger()
            _WURZEL.update()
            fenster.destroy()
            _WURZEL.update()
            del fenster
            gc.collect()
        gdi1, user1 = _gui_objekte()
        return (gdi1 - gdi0) / anzahl, (user1 - user0) / anzahl

    def test_ein_fenster_des_programms_kostet_nichts_bleibendes(self) -> None:
        gdi, user = self._messen(lambda: self.app._build_modern_toplevel("Probe", 300, 200))
        self.assertLess(gdi, 2.0, "Je Fenster bleiben %.1f GDI-Objekte stehen" % gdi)
        self.assertLess(user, 1.0, "Je Fenster bleiben %.1f USER-Objekte stehen" % user)

    def test_das_dump_image_fenster_gibt_alles_wieder_her(self) -> None:
        from ps5_validator.ui import ps4_dump_image
        bilder0 = len(_WURZEL.tk.call("image", "names"))
        # Was andere Tests dieses Prozesses offen liessen, zaehlt hier nicht: nur die Fenster dieses Tests.
        schon_da = [weakref.ref(o) for o in gc.get_objects() if isinstance(o, ps4_dump_image.Ps4DumpImageFenster)]

        def oeffnen():
            fenster = ps4_dump_image.Ps4DumpImageFenster(self.app, self.haupt.UI_SCHRIFT, self.haupt.MONO_SCHRIFT,
                                            self.haupt.pt)
            fenster._schliesst = True
            win = fenster.win
            try:
                fenster.warteschlange.alle_abbrechen()
            except Exception:                      # noqa: BLE001
                pass
            return win

        gdi, user = self._messen(oeffnen, anzahl=8)
        self.assertLess(gdi, 4.0, "Je PS4-Fenster bleiben %.1f GDI-Objekte stehen (vorher 93)" % gdi)
        self.assertLess(user, 2.0, "Je PS4-Fenster bleiben %.1f USER-Objekte stehen" % user)
        gc.collect()
        alt = [r() for r in schon_da]
        neu = [o for o in gc.get_objects()
               if isinstance(o, ps4_dump_image.Ps4DumpImageFenster) and not any(o is a for a in alt)]
        self.assertEqual([], neu, "Geschlossene PS4-Fenster leben noch.")
        self.assertLess(len(_WURZEL.tk.call("image", "names")) - bilder0, 150,
                        "Die Tk-Bilder wachsen mit jedem Fenster.")

    def test_haken_und_drehknopf_geben_ihre_spur_frei(self) -> None:
        var = tk.BooleanVar(master=_WURZEL)
        zahl = tk.IntVar(master=_WURZEL, value=3)
        rahmen = tk.Frame(_WURZEL)
        haken = self.app._runder_haken(rahmen, "x", var)
        knopf = self.haupt.Drehknopf(rahmen, zahl, 1, 8)
        haken.pack()
        knopf.pack()
        _WURZEL.update_idletasks()
        self.assertTrue(var.trace_info() and zahl.trace_info())
        rahmen.destroy()
        self.assertEqual((), tuple(var.trace_info()), "Die Spur des Hakens blieb")
        self.assertEqual((), tuple(zahl.trace_info()), "Die Spur des Drehknopfs blieb")


class QuelltextTests(unittest.TestCase):
    """Wer ein Symbol setzt, laedt es nicht je Fenster neu."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")

    def test_loadimage_steht_nur_im_zwischenspeicher(self) -> None:
        self.assertEqual(2, self.quelle.count("LoadImageW("),
                         "Ein Symbol je Fenster zu laden kostet 6 GDI-Objekte, die nie frei werden.")
        anfang = self.quelle.index("def _win32_symbole(")
        ende = self.quelle.index("def _apply_win32_window_icon(", anfang)
        self.assertEqual(2, self.quelle[anfang:ende].count("LoadImageW("))

    def test_nur_das_hauptfenster_ruft_iconbitmap_mit_datei(self) -> None:
        anfang = self.quelle.index("def _apply_icon_to_window(")
        block = self.quelle[anfang:anfang + 1800]
        self.assertIn("isinstance(win_any, tk.Tk)", block)
        self.assertIn("iconbitmap(default=icon_file)", block)

    def test_kein_fenster_haengt_eine_nackte_spur_an(self) -> None:
        """Eine Spur an einer Variablen haelt ihr Widget fuer immer am Leben - in Fenstern nur mit der Hilfe.

        ``variable.trace_add`` stellt einen Tcl-Befehl in das Verzeichnis des Interpreters; er haelt den
        Rueckruf, also Fenster, Bilder und Zeichner. ``spur_bis_zerstoert(widget, variable, rueckruf)`` nimmt
        die Spur mit dem Widget wieder weg. Erlaubt ist die nackte Spur nur in ``__init__``: Die Variablen
        des Hauptfensters leben so lange wie das Programm.
        """
        funde = []
        for klasse in ast.walk(ast.parse(self.quelle)):
            if not (isinstance(klasse, ast.ClassDef) and klasse.name == "PS5ConverterGUI"):
                continue
            for fn in klasse.body:
                if not isinstance(fn, ast.FunctionDef) or fn.name == "__init__":
                    continue
                for k in ast.walk(fn):
                    if (isinstance(k, ast.Call) and isinstance(k.func, ast.Attribute)
                            and k.func.attr in ("trace_add", "trace", "trace_variable")):
                        funde.append("%s:%d" % (fn.name, k.lineno))
        self.assertEqual([], funde, "Eine Spur ohne bibliothek_raster.spur_bis_zerstoert haelt ihr Fenster fest")


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class OtaZerstoerungTests(unittest.TestCase):
    """Wird das PS4-Fenster von aussen zerstoert, haengt das Programm nicht am toten Objekt."""

    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def test_destroy_von_aussen_raeumt_das_programm_auf(self) -> None:
        from ps5_validator.ui import ps4_dump_image
        fenster = ps4_dump_image.oeffnen(self.app, self.haupt.UI_SCHRIFT, self.haupt.MONO_SCHRIFT, self.haupt.pt)
        self.assertIs(fenster, getattr(self.app, ps4_dump_image.FENSTER_ATTRIBUT))
        fenster.win.destroy()
        self.assertIsNone(getattr(self.app, ps4_dump_image.FENSTER_ATTRIBUT, None),
                          "Das Programm haelt das zerstoerte Fenster weiter fest")
        self.assertTrue(fenster._schliesst)
        self.assertTrue(fenster._z["scan_abbruch"], "Ein laufender Scan erfaehrt nicht, dass das Fenster weg ist")

    def test_ein_anderes_fenster_bleibt_unberuehrt(self) -> None:
        """Zerstoert wird ein alter Fensterrahmen - das aktuelle Objekt des Programms bleibt stehen."""
        from ps5_validator.ui import ps4_dump_image
        erstes = ps4_dump_image.oeffnen(self.app, self.haupt.UI_SCHRIFT, self.haupt.MONO_SCHRIFT, self.haupt.pt)
        zweites = ps4_dump_image.Ps4DumpImageFenster(self.app, self.haupt.UI_SCHRIFT, self.haupt.MONO_SCHRIFT,
                                        self.haupt.pt)
        self.addCleanup(self._wegraeumen, erstes, zweites)
        zweites.win.destroy()
        self.assertIs(erstes, getattr(self.app, ps4_dump_image.FENSTER_ATTRIBUT),
                      "Das Zerstoeren eines fremden Fensters nahm dem Programm sein aktuelles")

    @staticmethod
    def _wegraeumen(*fenster) -> None:
        for f in fenster:
            try:
                f.win.destroy()
            except tk.TclError:
                pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
