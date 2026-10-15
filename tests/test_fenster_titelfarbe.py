# -*- coding: utf-8 -*-
"""Titelleisten in dunklem Graublau (``utils/fenster_titelfarbe.py``, seit v1.9.71; Design Hell bleibt hell).

Die Farben der Titelleiste lassen sich bei Windows nur setzen, nicht zurueckerfragen (``DwmGetWindowAttribute``
meldet fuer Farbe und Textfarbe ``E_INVALIDARG``). Die Aufrufe werden deshalb mit einem Ersatz fuer ``dwmapi``
geprueft; am echten Fenster belegt ist der Dunkelmodus (er laesst sich lesen) - und das Bild: Am 09.10.2026 wurden
vier echte Fenster aufgenommen (heute, #1F2733, #2A3441, #34404F), die Wahl fiel auf #2A3441.
"""
from __future__ import annotations

import ctypes
import gc
import sys
import tkinter as tk
import unittest
import weakref
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("titelfarbe")

from ps5_validator.utils import fenster_titelfarbe as tl   # noqa: E402

try:
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover - ohne Anzeige
    TK_DA = False
    _WURZEL = None


class Dwm:
    """Ersatz fuer ``ctypes.windll.dwmapi``: merkt sich jeden Aufruf."""

    def __init__(self, ergebnis: int = 0) -> None:
        self.aufrufe: list[tuple[int, int, int]] = []
        self.ergebnis = ergebnis

    def DwmSetWindowAttribute(self, hwnd, kennung, ablage, groesse):   # noqa: N802 - Name der Windows-Funktion
        wert = ctypes.cast(ablage, ctypes.POINTER(ctypes.c_uint)).contents.value
        self.aufrufe.append((hwnd.value, kennung.value, wert))
        return self.ergebnis


def _mit_ersatz(build: int = 26200, ergebnis: int = 0):
    dwm = Dwm(ergebnis)
    stuetzen = (mock.patch.object(tl, "_windows_build", return_value=build),
                mock.patch.object(tl, "_dwm", return_value=dwm),
                mock.patch.object(tl, "fenster_kennung", return_value=4242))
    return dwm, stuetzen


class FarbwertTests(unittest.TestCase):

    def test_farbe_als_colorref(self) -> None:
        self.assertEqual(0x0041342A, tl.farbwert("#2A3441"))
        self.assertEqual(0x00FFFFFF, tl.farbwert("#FFFFFF"))
        self.assertEqual(0x000000FF, tl.farbwert("#FF0000"))

    def test_ungueltige_farbe_wird_abgelehnt(self) -> None:
        for falsch in ("2A34", "#12345", "#1234567"):
            with self.subTest(falsch=falsch), self.assertRaises(ValueError):
                tl.farbwert(falsch)

    def test_das_gewaehlte_graublau_ist_b(self) -> None:
        self.assertEqual("#2A3441", tl.DUNKEL_BLAUGRAU)


class SchnittstelleTests(unittest.TestCase):

    def test_faerben_setzt_dunkelmodus_kappe_text_und_rand(self) -> None:
        dwm, (a, b, c) = _mit_ersatz()
        with a, b, c:
            self.assertTrue(tl.faerben(object()))
        farbe = tl.farbwert("#2A3441")
        self.assertEqual({(4242, 20, 1), (4242, 35, farbe), (4242, 36, tl.farbwert("#E8EDF4")), (4242, 34, farbe)},
                         set(dwm.aufrufe))
        self.assertEqual(4, len(dwm.aufrufe))

    def test_der_rand_hat_die_farbe_der_leiste(self) -> None:
        dwm, (a, b, c) = _mit_ersatz()
        with a, b, c:
            tl.faerben(object(), kappe="#102030")
        werte = {kennung: wert for _h, kennung, wert in dwm.aufrufe}
        self.assertEqual(werte[34], werte[35])
        self.assertEqual(tl.farbwert("#102030"), werte[35])

    def test_zuruecksetzen_gibt_dem_system_die_farben_zurueck(self) -> None:
        dwm, (a, b, c) = _mit_ersatz()
        with a, b, c:
            self.assertTrue(tl.zuruecksetzen(object()))
        self.assertEqual({(4242, 20, 0), (4242, 35, 0xFFFFFFFF), (4242, 36, 0xFFFFFFFF), (4242, 34, 0xFFFFFFFF)},
                         set(dwm.aufrufe))

    def test_ablehnung_durch_windows_wird_gemeldet(self) -> None:
        dwm, (a, b, c) = _mit_ersatz(ergebnis=0x80070057)
        with a, b, c:
            self.assertFalse(tl.faerben(object()))

    def test_vor_windows_11_geschieht_nichts(self) -> None:
        for build in (0, 19045, 21999):
            with self.subTest(build=build):
                dwm, (a, b, c) = _mit_ersatz(build=build)
                with a, b, c:
                    self.assertFalse(tl.faerben(object()))
                    self.assertFalse(tl.zuruecksetzen(object()))
                self.assertEqual([], dwm.aufrufe)

    def test_ab_windows_11_ist_es_moeglich(self) -> None:
        with mock.patch.object(tl, "_windows_build", return_value=22000):
            self.assertTrue(tl.unterstuetzt())
        with mock.patch.object(tl, "_windows_build", return_value=21999):
            self.assertFalse(tl.unterstuetzt())


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class FensterTests(unittest.TestCase):

    def _fenster(self, **optionen) -> tk.Toplevel:
        w = tk.Toplevel(_WURZEL, **optionen)
        w.geometry("200x80+40+40")
        w.update()
        self.addCleanup(w.destroy)
        return w

    def test_anwenden_faerbt_bei_dunklem_design_und_setzt_bei_hellem_zurueck(self) -> None:
        dwm, (a, b, _c) = _mit_ersatz()
        w = self._fenster()
        with a, b, mock.patch.object(tl, "fenster_kennung", return_value=777):
            self.assertTrue(tl.anwenden(w, True))
            self.assertIn((777, 35, tl.farbwert("#2A3441")), dwm.aufrufe)
            dwm.aufrufe.clear()
            self.assertTrue(tl.anwenden(w, False))
            self.assertIn((777, 35, 0xFFFFFFFF), dwm.aufrufe)
            self.assertNotIn((777, 35, tl.farbwert("#2A3441")), dwm.aufrufe)

    def test_ein_fenster_ohne_rahmen_bleibt_unberuehrt(self) -> None:
        dwm, (a, b, c) = _mit_ersatz()
        w = self._fenster()
        w.overrideredirect(True)
        with a, b, c:
            self.assertFalse(tl.anwenden(w, True))
        self.assertEqual([], dwm.aufrufe)

    def test_einrichten_faerbt_spaeter_geoeffnete_fenster(self) -> None:
        dwm, (a, b, _c) = _mit_ersatz()
        dunkel = [True]
        with a, b, mock.patch.object(tl, "fenster_kennung", side_effect=lambda w: int(w.winfo_id())):
            tl.einrichten(_WURZEL, lambda: dunkel[0])
            dwm.aufrufe.clear()
            w = tk.Toplevel(_WURZEL)
            w.geometry("200x80+40+40")
            self.addCleanup(w.destroy)
            w.update()
            gemeldet = {h for h, k, wert in dwm.aufrufe if k == 35 and wert == tl.farbwert("#2A3441")}
            self.assertIn(int(w.winfo_id()), gemeldet)

    def test_aktualisieren_zieht_offene_fenster_nach_dem_designwechsel_nach(self) -> None:
        dwm, (a, b, _c) = _mit_ersatz()
        dunkel = [True]
        w = self._fenster()
        with a, b, mock.patch.object(tl, "fenster_kennung", side_effect=lambda x: int(x.winfo_id())):
            tl.einrichten(_WURZEL, lambda: dunkel[0])
            dwm.aufrufe.clear()
            dunkel[0] = False
            tl.aktualisieren(_WURZEL)
            hell = {h for h, k, wert in dwm.aufrufe if k == 35 and wert == 0xFFFFFFFF}
            self.assertIn(int(w.winfo_id()), hell)
            dunkel[0] = True
            tl.einrichten(_WURZEL, lambda: True)

    def test_einrichten_bindet_nur_einmal(self) -> None:
        # Eine zweite Tk-Wurzel geht im selben Prozess nicht - es wird an der vorhandenen gezaehlt.
        with mock.patch.object(tl, "unterstuetzt", return_value=False):
            tl.einrichten(_WURZEL, lambda: True)
            vorher = (_WURZEL.bind_class("Toplevel", "<Map>"), _WURZEL.bind("<Map>"))
            tl.einrichten(_WURZEL, lambda: False)
            nachher = (_WURZEL.bind_class("Toplevel", "<Map>"), _WURZEL.bind("<Map>"))
            self.assertEqual(vorher, nachher)
            self.assertFalse(_WURZEL._fenster_titelfarbe_dunkel())
            tl.einrichten(_WURZEL, lambda: True)

    def test_einrichten_haelt_das_programmfenster_nicht_fest(self) -> None:
        """Die Wurzel lebt laenger als jedes Programmfenster und darf dessen Methode nicht festhalten.

        Gemessen im Volllauf am 09.10.2026: ``test_pruefaufraeumen`` fand das Programmfenster nach seiner Klasse
        noch lebendig - die Antwortfunktion ``_design_ist_dunkel`` hing als gebundene Methode an der Wurzel.
        """
        class Besitzer:
            def dunkel(self) -> bool:
                return False

        besitzer = Besitzer()
        spur = weakref.ref(besitzer)
        with mock.patch.object(tl, "unterstuetzt", return_value=False):
            tl.einrichten(_WURZEL, besitzer.dunkel)
            self.assertFalse(_WURZEL._fenster_titelfarbe_dunkel())
            del besitzer
            gc.collect()
            self.assertIsNone(spur(), "Die Wurzel haelt den Besitzer der Antwortfunktion fest")
            self.assertTrue(_WURZEL._fenster_titelfarbe_dunkel(), "Ohne Besitzer gilt dunkel")
            tl.einrichten(_WURZEL, lambda: True)

    def test_einrichten_bindet_neu_wenn_die_haken_zurueckgesetzt_wurden(self) -> None:
        """``conftest.py`` setzt die Bindungen der Wurzel nach der Klasse eines Programmfensters zurueck.

        Eine Merkmarke an der Wurzel liess das Neubinden damals ausfallen: drei Pruefungen waren im Volllauf rot
        und einzeln gruen (09.10.2026). Jetzt wird am Stand von Tk gemessen.
        """
        def ohne_unsere(skript: str, namen) -> str:
            return "".join(zeile + "\n" for zeile in skript.splitlines()
                           if not any(("[%s " % name) in zeile for name in namen))

        with mock.patch.object(tl, "unterstuetzt", return_value=False):
            tl.einrichten(_WURZEL, lambda: True)
            self.assertTrue(tl.ist_eingerichtet(_WURZEL))
            namen = _WURZEL._fenster_titelfarbe_bindung
            for ziel in ("Toplevel", str(_WURZEL)):
                _WURZEL.tk.call("bind", ziel, "<Map>", ohne_unsere(_WURZEL.tk.call("bind", ziel, "<Map>"), namen))
            self.assertFalse(tl.ist_eingerichtet(_WURZEL), "Ohne Haken an der Wurzel gilt sie nicht als eingerichtet")
            tl.einrichten(_WURZEL, lambda: True)
            self.assertTrue(tl.ist_eingerichtet(_WURZEL))
            self.assertNotEqual(namen, _WURZEL._fenster_titelfarbe_bindung, "Es wurde nicht neu gebunden")

    @unittest.skipUnless(sys.platform == "win32" and tl.unterstuetzt(), "Windows 11 noetig")
    def test_am_echten_fenster_nimmt_windows_den_dunklen_modus_an(self) -> None:
        w = self._fenster()
        hwnd = tl.fenster_kennung(w)

        def lesen() -> int:
            wert = ctypes.c_uint(99)
            hr = ctypes.windll.dwmapi.DwmGetWindowAttribute(ctypes.c_void_p(hwnd), ctypes.c_uint(20),
                                                            ctypes.byref(wert), ctypes.c_uint(4))
            self.assertEqual(0, hr)
            return wert.value

        self.assertTrue(tl.anwenden(w, True))
        self.assertEqual(1, lesen())
        self.assertTrue(tl.anwenden(w, False))
        self.assertEqual(0, lesen())


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class HauptprogrammTests(unittest.TestCase):
    """Am wirklichen Programm: der Haken faerbt neue Fenster, der Designwechsel zieht offene nach."""

    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        # Regel aus test_qualitaetslauf: Wer eine echte Oberflaeche baut, legt die Sprache fest.
        cls.app._current_language = "de"

    def _ersatz(self):
        dwm = Dwm()
        for stuetze in (mock.patch.object(tl, "_windows_build", return_value=26200),
                        mock.patch.object(tl, "_dwm", return_value=dwm),
                        mock.patch.object(tl, "fenster_kennung", side_effect=lambda w: int(w.winfo_id()))):
            stuetze.start()
            self.addCleanup(stuetze.stop)
        return dwm

    def _neues_fenster(self) -> tk.Toplevel:
        w = tk.Toplevel(_WURZEL)
        w.geometry("200x80+40+40")
        self.addCleanup(w.destroy)
        w.update()
        return w

    @staticmethod
    def _farben(dwm: Dwm, w: tk.Toplevel) -> list[int]:
        kennung = int(w.winfo_id())
        return [wert for h, k, wert in dwm.aufrufe if h == kennung and k == 35]

    def test_der_haken_ist_eingerichtet(self) -> None:
        self._ersatz()
        self.assertTrue(tl.ist_eingerichtet(_WURZEL))
        alt = self.app._current_theme
        self.addCleanup(self.app._apply_theme, alt)
        self.app._apply_theme("dunkel")
        self.assertTrue(_WURZEL._fenster_titelfarbe_dunkel())
        self.app._apply_theme("hell")
        self.assertFalse(_WURZEL._fenster_titelfarbe_dunkel(),
                         "Die Antwort der Wurzel folgt dem Design des Programms nicht")

    def test_ein_neues_fenster_bekommt_das_graublau(self) -> None:
        dwm = self._ersatz()
        self.assertTrue(self.app._design_ist_dunkel())
        w = self._neues_fenster()
        self.assertIn(tl.farbwert("#2A3441"), self._farben(dwm, w))

    def test_im_design_hell_bleibt_die_leiste_hell(self) -> None:
        dwm = self._ersatz()
        alt = self.app._current_theme
        self.app._apply_theme("hell")
        self.addCleanup(self.app._apply_theme, alt)
        self.assertFalse(self.app._design_ist_dunkel())
        w = self._neues_fenster()
        farben = self._farben(dwm, w)
        self.assertIn(0xFFFFFFFF, farben)
        self.assertNotIn(tl.farbwert("#2A3441"), farben)

    def test_der_designwechsel_zieht_offene_fenster_nach(self) -> None:
        dwm = self._ersatz()
        alt = self.app._current_theme
        self.app._apply_theme("dunkel")
        self.addCleanup(self.app._apply_theme, alt)
        w = self._neues_fenster()
        dwm.aufrufe.clear()
        self.app._apply_theme("hell")
        self.assertEqual(0xFFFFFFFF, self._farben(dwm, w)[-1])
        dwm.aufrufe.clear()
        self.app._apply_theme("metallisch")
        self.assertEqual(tl.farbwert("#2A3441"), self._farben(dwm, w)[-1])

    def test_das_hauptfenster_wird_mitgefaerbt(self) -> None:
        dwm = self._ersatz()
        self.app._apply_theme(self.app._current_theme)
        kennung = int(_WURZEL.winfo_id())
        self.assertTrue([1 for h, k, _w in dwm.aufrufe if h == kennung and k == 35])

    def test_die_haken_stehen_im_quelltext(self) -> None:
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        self.assertIn("self._fenster_titelfarben_einrichten()", quelle)
        self.assertIn("self._fenster_titelfarben_aktualisieren()", quelle)


if __name__ == "__main__":
    unittest.main()
