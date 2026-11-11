# -*- coding: utf-8 -*-
"""Unvollstaendige Downloads (``.teil``) lassen sich loeschen (Nutzerwunsch 11.11.2026).

Ein abgebrochener oder gescheiterter Download laesst seine Teildatei liegen, damit er spaeter an derselben Stelle
weitermacht. Wer ihn nicht mehr will, hatte im Programm keinen Weg, sie wieder loszuwerden - nach einem Neustart tauchte
sie nirgends mehr auf. Jetzt: Knopf "Teildatei loeschen" im Download-Fenster (auch fuer Reste frueherer Laeufe, die
das Fenster aus dem Speicherort liest) und in den beiden Ladefenstern der Update-Pakete.
"""
from __future__ import annotations

import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("teil_loeschen")

from ps5_validator.utils import ps5_downloads as dl         # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

HAUPT = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"
NAME = "UP8016-PPSA19015_00-0489895718491618.pkg"
NAME2 = "UP8016-PPSA19016_00-0489895718491619.pkg"


def _datei(pfad: str, inhalt: bytes = b"x" * 100) -> str:
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, "wb") as f:
        f.write(inhalt)
    return pfad


class DateiLogikTests(unittest.TestCase):

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="ps5conv_teil_")
        self.addCleanup(tmp.cleanup)
        self.basis = tmp.name

    def _ziel(self, art: str = dl.ART_UPDATE, name: str = NAME) -> str:
        return dl.zielpfad(self.basis, art, name)

    def test_loescht_teildatei_und_merkdateien(self):
        ziel = self._ziel()
        for pfad in dl.teil_anhaenge(ziel):
            _datei(pfad)
        frei, fehler = dl.teil_loeschen(ziel)
        self.assertEqual(("", 300), (fehler, frei))
        self.assertEqual([], [p for p in dl.teil_anhaenge(ziel) if os.path.exists(p)])

    def test_die_fertige_datei_bleibt(self):
        ziel = _datei(self._ziel(), b"fertig")
        _datei(dl.teildatei(ziel))
        dl.teil_loeschen(ziel)
        self.assertTrue(os.path.isfile(ziel), "die fertige .pkg darf nie mitgeloescht werden")
        self.assertFalse(os.path.exists(dl.teildatei(ziel)))

    def test_nichts_da_ist_kein_fehler(self):
        self.assertEqual((0, ""), dl.teil_loeschen(self._ziel()))

    def test_ein_fremder_pfad_wird_nicht_angefasst(self):
        """Der Pfad muss auf .pkg enden - sonst wuerde ein falsch uebergebener Name eine fremde Datei treffen."""
        fremd = _datei(os.path.join(self.basis, "notizen.txt.teil"))
        frei, fehler = dl.teil_loeschen(os.path.join(self.basis, "notizen.txt"))
        self.assertEqual(0, frei)
        self.assertNotEqual("", fehler)
        self.assertTrue(os.path.isfile(fremd))

    def test_teildateien_listet_beide_ordner(self):
        _datei(dl.teildatei(self._ziel(dl.ART_UPDATE, NAME)), b"a" * 10)
        _datei(dl.teildatei(self._ziel(dl.ART_PATCH, NAME2)), b"b" * 20)
        _datei(self._ziel(dl.ART_UPDATE, "UP8016-PPSA19017_00-0489895718491620.pkg"))           # fertig: nicht dabei
        _datei(os.path.join(dl.zielordner(self.basis, dl.ART_UPDATE), "fremd.teil"))             # keine Content-ID
        gefunden = {e["dateiname"]: e for e in dl.teildateien(self.basis)}
        self.assertEqual({NAME, NAME2}, set(gefunden))
        self.assertEqual("10", gefunden[NAME]["teil_bytes"])
        self.assertEqual(dl.ART_PATCH, gefunden[NAME2]["art"])
        self.assertEqual(self._ziel(dl.ART_UPDATE, NAME), gefunden[NAME]["pfad"])

    def test_ohne_speicherort_gibt_es_nichts(self):
        self.assertEqual([], dl.teildateien(""))


class QuelltextTests(unittest.TestCase):
    """Die Verdrahtung im Hauptmodul."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = HAUPT.read_text(encoding="utf-8")

    def _funktion(self, name: str) -> str:
        zeilen = self.text.splitlines()
        baum = ast.parse(self.text)
        for k in ast.walk(baum):
            if isinstance(k, ast.FunctionDef) and k.name == name:
                return "\n".join(zeilen[k.lineno - 1:k.end_lineno])
        self.fail(name)

    def test_beide_ladefenster_haben_den_knopf(self):
        for name in ("_sony_ladefenster", "_ps4_ladefenster"):
            with self.subTest(name):
                quelle = self._funktion(name)
                self.assertIn("ps5upd.knopf_loeschen", quelle)
                self.assertIn("_teildateien_loeschen_fragen([ziel]", quelle)

    def test_das_download_fenster_hat_den_knopf_und_zeigt_reste(self):
        quelle = self._funktion("_show_downloads_manager")
        self.assertIn("downloads.action_delete_partial", quelle)
        self.assertIn("ps5_downloads.teildateien(", quelle)

    def test_eine_unvollstaendige_zeile_blockiert_die_adresse_nicht(self):
        """Wer die Adresse wieder einfuegt, setzt fort - die Zeile darf sie nicht als doppelt abweisen."""
        self.assertIn('not in ("failed", "cancelled", "partial")', self._funktion("_download_aufnehmen"))

    def test_die_frage_kommt_vor_dem_loeschen(self):
        quelle = self._funktion("_teildateien_loeschen_fragen")
        self.assertLess(quelle.index("askyesno"), quelle.index("teil_loeschen("))

    def test_texte_in_allen_sprachen(self):
        for schluessel in ("downloads.action_delete_partial", "downloads.action_delete_partial_hint",
                           "downloads.state_partial", "downloads.delete_title", "downloads.delete_confirm",
                           "downloads.delete_nothing", "downloads.delete_running", "downloads.delete_failed",
                           "downloads.delete_log", "ps5upd.knopf_loeschen", "ps5upd.teil_geloescht"):
            for sprache in ("de", "en", "es", "it", "fr"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    self.assertTrue(STRINGS[schluessel].get(sprache), "Text fehlt")


try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                            # pragma: no cover
    TK_DA = False


def _knopf_mit_text(wurzel, text: str):
    """Der Knopf (Pillen-Canvas) mit dieser Beschriftung irgendwo unter ``wurzel``."""
    for kind in wurzel.winfo_children():
        try:
            if kind.cget("text") == text and hasattr(kind, "invoke"):
                return kind
        except tk.TclError:
            pass
        treffer = _knopf_mit_text(kind, text)
        if treffer is not None:
            return treffer
    return None


@unittest.skipUnless(TK_DA, "keine Anzeige")
class FensterTests(unittest.TestCase):
    """Mit dem echten Download-Fenster (Speicherort auf einen Testordner umgebogen)."""

    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util

        name = "hauptprogramm"
        if name in sys.modules:
            haupt = sys.modules[name]
        else:
            spec = importlib.util.spec_from_file_location(name, HAUPT)
            haupt = importlib.util.module_from_spec(spec)
            sys.modules[name] = haupt
            spec.loader.exec_module(haupt)
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"          # sonst gilt im Volllauf die Sprache des zuletzt geladenen Pruefmoduls

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="ps5conv_teil_fenster_")
        self.addCleanup(tmp.cleanup)
        self.basis = tmp.name
        self.ziel = dl.zielpfad(self.basis, dl.ART_UPDATE, NAME)
        _datei(dl.teildatei(self.ziel), b"x" * 2048)
        _datei(dl.merkdatei(self.ziel), b"{}")
        muster = mock.patch.object(self.app, "_download_basis", return_value=self.basis)
        muster.start()
        self.addCleanup(muster.stop)
        self.app._downloads.clear()
        self.addCleanup(self._schliessen)

    def _schliessen(self) -> None:
        fenster = getattr(self.app, "_downloads_win", None)
        if fenster is not None:
            try:
                fenster.destroy()
            except tk.TclError:
                pass
        self.app._downloads_win = None
        self.app._downloads_tree = None
        self.app._downloads.clear()

    def _oeffnen(self):
        self.app._show_downloads_manager()
        self.app._downloads_win.update()
        return self.app._downloads_win, self.app._downloads_tree

    def test_der_rest_einer_alten_sitzung_steht_in_der_liste(self):
        _win, baum = self._oeffnen()
        zeilen = [baum.item(i, "values") for i in baum.get_children()]
        self.assertEqual(1, len(zeilen))
        self.assertEqual(NAME, zeilen[0][0])
        self.assertIn("partial", {e.get("status") for e in self.app._downloads.values()})

    def test_loeschen_nach_ja_entfernt_dateien_und_zeile(self):
        win, baum = self._oeffnen()
        baum.selection_set(baum.get_children()[0])
        knopf = _knopf_mit_text(win, self.app._t("downloads.action_delete_partial"))
        self.assertIsNotNone(knopf)
        with mock.patch.object(self.haupt.messagebox, "askyesno", return_value=True) as frage:
            knopf.invoke()
        frage.assert_called_once()
        self.assertEqual([], [p for p in dl.teil_anhaenge(self.ziel) if os.path.exists(p)])
        self.assertEqual((), baum.get_children())
        self.assertEqual({}, self.app._downloads)

    def test_nach_nein_bleibt_alles(self):
        win, baum = self._oeffnen()
        baum.selection_set(baum.get_children()[0])
        knopf = _knopf_mit_text(win, self.app._t("downloads.action_delete_partial"))
        with mock.patch.object(self.haupt.messagebox, "askyesno", return_value=False):
            knopf.invoke()
        self.assertTrue(os.path.isfile(dl.teildatei(self.ziel)))
        self.assertEqual(1, len(baum.get_children()))

    def test_ohne_auswahl_wird_nichts_geloescht(self):
        win, _baum = self._oeffnen()
        knopf = _knopf_mit_text(win, self.app._t("downloads.action_delete_partial"))
        with mock.patch.object(self.haupt.messagebox, "askyesno") as frage, \
                mock.patch.object(self.haupt.messagebox, "showinfo") as hinweis:
            knopf.invoke()
        frage.assert_not_called()
        hinweis.assert_called_once()
        self.assertTrue(os.path.isfile(dl.teildatei(self.ziel)))

    def test_ein_laufender_download_wird_nicht_geloescht(self):
        win, baum = self._oeffnen()
        iid = baum.get_children()[0]
        self.app._downloads[iid]["status"] = "running"
        baum.selection_set(iid)
        knopf = _knopf_mit_text(win, self.app._t("downloads.action_delete_partial"))
        with mock.patch.object(self.haupt.messagebox, "askyesno") as frage, \
                mock.patch.object(self.haupt.messagebox, "showinfo") as hinweis:
            knopf.invoke()
        frage.assert_not_called()
        self.assertEqual(self.app._t("downloads.delete_running"), hinweis.call_args.args[1])
        self.assertTrue(os.path.isfile(dl.teildatei(self.ziel)))

    def test_ein_gescheiterter_download_wird_mit_seiner_zeile_entfernt(self):
        win, baum = self._oeffnen()
        iid = baum.get_children()[0]
        self.app._downloads[iid]["status"] = "cancelled"
        self.app._downloads[iid]["url"] = "http://gst.prod.dl.playstation.net/x"
        baum.selection_set(iid)
        knopf = _knopf_mit_text(win, self.app._t("downloads.action_delete_partial"))
        with mock.patch.object(self.haupt.messagebox, "askyesno", return_value=True):
            knopf.invoke()
        self.assertFalse(os.path.exists(dl.teildatei(self.ziel)))
        self.assertEqual((), baum.get_children())

    def test_die_adresse_erneut_einfuegen_setzt_die_zeile_fort_statt_doppelt_abzuweisen(self):
        _win, baum = self._oeffnen()
        adresse = ("http://gst.prod.dl.playstation.net/gst/prod/00/PPSA19015_00/app/pkg/5/f_"
                   + "2f6a8429bc090a765d66f5d3d46b0db710967ef4b40c57005ba8e5ce4b6abff4/" + NAME)
        with mock.patch.object(self.app, "_download_worker") as worker:
            ergebnis = self.app._download_aufnehmen(adresse, sammel=True)
        self.assertEqual("neu", ergebnis)
        self.assertEqual(1, len(baum.get_children()), "keine zweite Zeile")
        worker.assert_called()


@unittest.skipUnless(TK_DA, "keine Anzeige")
class SpielInfoTests(unittest.TestCase):
    """Spiel-Info - Updates & Patches: Knopf loescht die angefangenen Downloads des gezeigten Spiels."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = sys.modules.get("hauptprogramm")
        if cls.haupt is None:
            import importlib.util

            spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPT)
            cls.haupt = importlib.util.module_from_spec(spec)
            sys.modules["hauptprogramm"] = cls.haupt
            spec.loader.exec_module(cls.haupt)
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="ps5conv_teil_info_")
        self.addCleanup(tmp.cleanup)
        self.basis = tmp.name
        self.eigenes = dl.zielpfad(self.basis, dl.ART_UPDATE, NAME)             # PPSA19015
        self.fremdes = dl.zielpfad(self.basis, dl.ART_PATCH, NAME2)             # PPSA19016
        for ziel in (self.eigenes, self.fremdes):
            _datei(dl.teildatei(ziel), b"x" * 512)
        for muster in (mock.patch.object(self.app, "_download_basis", return_value=self.basis),
                       mock.patch.object(self.app, "_cached_title_id", "PPSA19015")):
            muster.start()
            self.addCleanup(muster.stop)
        self.app._downloads.clear()
        self.app._sony_lauf = None
        self.app._ps4_lauf = None
        self.addCleanup(self._zu)

    def _zu(self) -> None:
        popup = getattr(self.app, "_info_popup", None)
        if popup is not None:
            try:
                popup.destroy()
            except tk.TclError:
                pass
        self.app._info_popup = None
        self.app._downloads.clear()

    def _knopf(self):
        popup = self.app._build_info_popup()
        popup.update_idletasks()      # kein update(): ein vom Programmstart geplanter Rueckruf schliesst das Popup sonst
        knopf = _knopf_mit_text(popup, self.app._t("info_popup.teil_loeschen"))
        self.assertIsNotNone(knopf, "Knopf fehlt im Info-Fenster")
        return knopf

    def test_loescht_nur_die_teildaten_dieses_spiels(self):
        knopf = self._knopf()
        with mock.patch.object(self.haupt.messagebox, "askyesno", return_value=True):
            knopf.invoke()
        self.assertFalse(os.path.exists(dl.teildatei(self.eigenes)))
        self.assertTrue(os.path.isfile(dl.teildatei(self.fremdes)), "das andere Spiel darf nicht betroffen sein")

    def test_nein_laesst_alles_liegen(self):
        knopf = self._knopf()
        with mock.patch.object(self.haupt.messagebox, "askyesno", return_value=False):
            knopf.invoke()
        self.assertTrue(os.path.isfile(dl.teildatei(self.eigenes)))

    def test_ohne_angefangenen_download_gibt_es_einen_hinweis(self):
        os.remove(dl.teildatei(self.eigenes))
        knopf = self._knopf()
        with mock.patch.object(self.haupt.messagebox, "askyesno") as frage, \
                mock.patch.object(self.haupt.messagebox, "showinfo") as hinweis:
            knopf.invoke()
        frage.assert_not_called()
        self.assertEqual(self.app._t("info_popup.teil_keine"), hinweis.call_args.args[1])

    def test_ein_laufender_ladevorgang_bleibt_unberuehrt(self):
        self.app._sony_lauf = {"aktiv": True, "ziel": self.eigenes}
        knopf = self._knopf()
        with mock.patch.object(self.haupt.messagebox, "askyesno") as frage, \
                mock.patch.object(self.haupt.messagebox, "showinfo") as hinweis:
            knopf.invoke()
        frage.assert_not_called()
        self.assertEqual(self.app._t("downloads.delete_running"), hinweis.call_args.args[1])
        self.assertTrue(os.path.isfile(dl.teildatei(self.eigenes)))


class LadefensterTests(unittest.TestCase):
    """Die Frage ist die Huerde vor dem Loeschen, auch fuer die Ladefenster (gemeinsamer Helfer)."""

    def test_nein_loescht_nichts(self):
        haupt = sys.modules.get("hauptprogramm")
        if haupt is None:
            self.skipTest("Hauptprogramm nicht geladen")
        app = haupt.PS5ConverterGUI.__new__(haupt.PS5ConverterGUI)
        app.root = None                      # die Fragen sind gemockt; ``parent or self.root`` wird nur gelesen
        app._t = lambda schluessel, **k: schluessel
        app._fmt_bytes = lambda n: str(n)
        app._append_to_log = lambda *_a, **_k: None
        with tempfile.TemporaryDirectory() as ordner:
            ziel = os.path.join(ordner, NAME)
            _datei(dl.teildatei(ziel))
            with mock.patch.object(haupt.messagebox, "askyesno", return_value=False):
                self.assertEqual([], app._teildateien_loeschen_fragen([ziel]))
            self.assertTrue(os.path.isfile(dl.teildatei(ziel)))
            with mock.patch.object(haupt.messagebox, "askyesno", return_value=True):
                self.assertEqual([ziel], app._teildateien_loeschen_fragen([ziel]))
            self.assertFalse(os.path.exists(dl.teildatei(ziel)))


if __name__ == "__main__":
    unittest.main()
