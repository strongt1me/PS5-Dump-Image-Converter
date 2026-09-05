# -*- coding: utf-8 -*-
"""Was das Download-Fenster ueberlebt, wenn man es schliesst und neu oeffnet.

Befunde M011 und M012 vom 04.09.2026.

Die Eintraege liegen unter der Zeilenkennung des Baums. Tk vergibt die je
Widget neu ab "I001", also war die Sorge: Nach dem Wiederoeffnen ueberschreibt
der erste neue Eintrag einen alten, vielleicht noch laufenden.

**Beides wurde nachgemessen** (Tk 8.6, echte ttk.Treeview):

* Zwei frische Baeume vergeben tatsaechlich beide ['I001','I002','I003'] - die
  Praemisse stimmt allgemein.
* Ein Baum, in den vorher iid="I001" gesetzt wurde, vergibt danach
  ['I002','I003','I004']. **Tk ueberspringt belegte Kennungen.**

Weil die noch laufenden Zeilen beim Oeffnen unter ihrer alten Kennung wieder
eingesetzt werden, kann ein laufender Download also nicht mehr ueberschrieben
werden. Das ist die Eigenschaft, auf der das Ganze steht - und die dieser Test
festhaelt, damit sie nicht unbemerkt wegfaellt.

Offen blieb, was hier ebenfalls geprueft wird: Fehlgeschlagene und
abgebrochene Downloads wurden beim Schliessen weggeworfen. Die halb geladene
.teil-Datei blieb liegen, tauchte aber nirgends mehr auf - "Erneut versuchen"
arbeitet ueber die Liste, und die Adresse laesst sich nicht rekonstruieren
(der Abschnitt ``f_<64 Hex>`` darin entsteht erst beim Aufloesen im Browser).
Ein abgebrochener 50-GB-Download war damit verloren, sobald das Fenster einmal
zu war.
"""
from __future__ import annotations

import ast
import io
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("downloads_wiedersehen")

try:
    import tkinter as tk
    from tkinter import ttk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                            # pragma: no cover
    TK_DA = False

HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"


@unittest.skipUnless(TK_DA, "keine Anzeige")
class KennungTests(unittest.TestCase):
    """Die Eigenschaft von Tk, auf der die Wiederherstellung ruht."""

    def _baum(self) -> "ttk.Treeview":
        baum = ttk.Treeview(_WURZEL, columns=("a",), show="headings")
        self.addCleanup(baum.destroy)
        return baum

    def test_zwei_frische_baeume_vergeben_dieselben_kennungen(self):
        """Die Praemisse des Befunds - ohne sie gaebe es kein Thema."""
        eins = [self._baum().insert("", "end", values=("x",)) for _ in range(3)]
        zwei = [self._baum().insert("", "end", values=("x",)) for _ in range(3)]
        self.assertEqual(eins, zwei)

    def test_tk_ueberspringt_belegte_kennungen(self):
        """Deshalb kann eine zurueckgeholte Zeile nicht ueberschrieben werden."""
        baum = self._baum()
        baum.insert("", "end", iid="I001", values=("alt",))
        neue = [baum.insert("", "end", values=("neu",)) for _ in range(3)]
        self.assertNotIn("I001", neue,
                         "Tk vergibt eine belegte Kennung neu - dann ist die "
                         "Wiederherstellung nicht mehr sicher.")

    def test_auch_bei_luecken(self):
        baum = self._baum()
        baum.insert("", "end", iid="I002", values=("alt",))
        baum.insert("", "end", iid="I005", values=("alt",))
        neue = [baum.insert("", "end", values=("neu",)) for _ in range(5)]
        self.assertNotIn("I002", neue)
        self.assertNotIn("I005", neue)


class WiederherstellungTests(unittest.TestCase):
    """Was beim Oeffnen aus der alten Sitzung zurueckkommt."""

    @classmethod
    def setUpClass(cls):
        with io.open(HAUPTDATEI, encoding="utf-8") as fh:
            cls.quelle = fh.read()
        cls.baum = ast.parse(cls.quelle)
        cls.fenster = next(k for k in ast.walk(cls.baum)
                           if isinstance(k, ast.FunctionDef)
                           and k.name == "_show_downloads_manager")

    def _behaltene_zustaende(self) -> set[str]:
        """Die Zustandsnamen, die die Bereinigung beim Oeffnen stehen laesst."""
        for k in ast.walk(self.fenster):
            if (isinstance(k, ast.Assign) and k.targets
                    and isinstance(k.targets[0], ast.Name)
                    and k.targets[0].id == "_BEHALTEN"):
                return {e.value for e in ast.walk(k.value)
                        if isinstance(e, ast.Constant) and isinstance(e.value, str)}
        self.fail("Die Liste der behaltenen Zustaende gibt es nicht mehr.")

    def test_ein_abgebrochener_download_ueberlebt_das_schliessen(self):
        """Sonst ist seine halb geladene Datei nicht mehr erreichbar."""
        behalten = self._behaltene_zustaende()
        for zustand in ("queued", "running", "failed", "cancelled"):
            with self.subTest(zustand=zustand):
                self.assertIn(zustand, behalten)

    def test_fertiges_wird_weiterhin_von_der_platte_gelesen(self):
        """"done" und "present" duerfen NICHT stehenbleiben.

        Sie kaemen sonst doppelt: einmal aus der alten Liste, einmal aus
        _vorhandene(), das die Platte liest.
        """
        behalten = self._behaltene_zustaende()
        self.assertNotIn("done", behalten)
        self.assertNotIn("present", behalten)

    def test_der_arbeiter_merkt_sich_groesse_und_fehler(self):
        """Beides sind sonst reine Ortsvariablen und nach dem Schliessen weg."""
        arbeiter = next(k for k in ast.walk(self.baum)
                        if isinstance(k, ast.FunctionDef)
                        and k.name == "_download_worker")
        gemerkt = set()
        for k in ast.walk(arbeiter):
            if (isinstance(k, ast.Subscript) and isinstance(k.slice, ast.Constant)
                    and isinstance(k.value, ast.Name) and k.value.id == "eintrag"):
                gemerkt.add(k.slice.value)
        self.assertIn("bytes", gemerkt,
                      "Ohne das bleibt die Groessenspalte nach dem "
                      "Wiederoeffnen dauerhaft leer.")
        self.assertIn("fehler", gemerkt,
                      "Ohne das steht in der wiederhergestellten Zeile kein "
                      "Grund mehr.")

    def test_der_schliessen_knopf_geht_nicht_am_aufraeumen_vorbei(self):
        """Nur das X der Titelleiste lief bisher den richtigen Weg."""
        # Nicht ueber den Text suchen: "action.close" steht auch am
        # Einfuege-Dialog dieses Fensters, und der zerstoert zu Recht sein
        # eigenes dlg. Geprueft wird die Eigenschaft - kein Knopf des Fensters
        # darf "win" direkt zerstoeren.
        direkt = []
        for k in ast.walk(self.fenster):
            if not (isinstance(k, ast.Call) and "action.close" in ast.dump(k)):
                continue
            for stichwort in k.keywords:
                if stichwort.arg != "command":
                    continue
                ziel = ast.dump(stichwort.value)
                if "'win'" in ziel and "'destroy'" in ziel:
                    direkt.append(k.lineno)
        self.assertEqual(
            [], direkt,
            "Zeile(n) %s zerstoeren das Fenster direkt und gehen am "
            "Aufraeumen vorbei - _downloads_win/_downloads_tree zeigen danach "
            "auf zerstoerte Widgets." % direkt)


if __name__ == "__main__":
    unittest.main()
