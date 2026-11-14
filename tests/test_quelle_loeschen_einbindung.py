# -*- coding: utf-8 -*-
"""Quelle nach Erfolg loeschen im Hauptprogramm: Haken, Rueckfrage, Kommandozeile, Loeschen nur wenn alles stimmt (14.11.2026)."""
from __future__ import annotations

import ast
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402,F401
import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import i18n, quelle_loeschen       # noqa: E402

GUI = APP.PS5ConverterGUI
SPRACHEN = ("de", "en", "es", "it", "fr")


def _gui(*, loeschen: bool = True) -> "GUI":
    g = GUI.__new__(GUI)
    g._log = []
    g._append_to_log = g._log.append
    g._t = lambda schluessel, **w: i18n.translate("de", schluessel, **w)
    g._lauf_quelle_loeschen = loeschen
    return g


class _Ablage(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.wurzel = Path(tmp.name) / "arbeit" / "tief"
        self.wurzel.mkdir(parents=True)
        self.quelle = self.wurzel / "Spiel"
        (self.quelle / "sce_sys").mkdir(parents=True)
        (self.quelle / "eboot.bin").write_bytes(b"x" * 100)
        (self.quelle / "sce_sys" / "param.json").write_bytes(b"{}")
        self.ergebnis = self.wurzel / "aus" / "Spiel.exfat"
        self.ergebnis.parent.mkdir()
        self.ergebnis.write_bytes(b"e" * 50)
        self.stempel = quelle_loeschen.stempel_nehmen(str(self.quelle))


class LoeschenNachErfolgTests(_Ablage):
    def test_alles_stimmt_die_quelle_wird_geloescht(self) -> None:
        g = _gui()
        self.assertTrue(g._quelle_nach_erfolg_loeschen(str(self.quelle), str(self.ergebnis), self.stempel))
        self.assertFalse(self.quelle.exists())
        self.assertTrue(self.ergebnis.exists(), "Das Ergebnis darf nie angefasst werden.")
        self.assertTrue(any("Quelle gelöscht" in z for z in g._log), g._log)

    def test_ohne_den_haken_bleibt_alles(self) -> None:
        g = _gui(loeschen=False)
        self.assertFalse(g._quelle_nach_erfolg_loeschen(str(self.quelle), str(self.ergebnis), self.stempel))
        self.assertTrue(self.quelle.exists())
        self.assertEqual([], g._log)

    def test_geaenderte_quelle_bleibt_mit_grund_im_protokoll(self) -> None:
        (self.quelle / "dazu.bin").write_bytes(b"jemand war hier")
        g = _gui()
        self.assertFalse(g._quelle_nach_erfolg_loeschen(str(self.quelle), str(self.ergebnis), self.stempel))
        self.assertTrue(self.quelle.exists())
        self.assertTrue(any("seit dem Start geändert" in z for z in g._log), g._log)

    def test_fehlendes_ergebnis_bleibt(self) -> None:
        self.ergebnis.unlink()
        g = _gui()
        self.assertFalse(g._quelle_nach_erfolg_loeschen(str(self.quelle), str(self.ergebnis), self.stempel))
        self.assertTrue(self.quelle.exists())
        self.assertTrue(any("Ergebnis fehlt" in z for z in g._log), g._log)

    def test_selbst_ziel_loescht_nichts(self) -> None:
        """Das Ergebnis hat die Quelle ersetzt (gleicher Pfad): Ein Loeschen risse das Ergebnis mit."""
        g = _gui()
        datei = self.wurzel / "x.exfat"
        datei.write_bytes(b"neu")
        stempel = quelle_loeschen.stempel_nehmen(str(datei))
        self.assertFalse(g._quelle_nach_erfolg_loeschen(str(datei), str(datei), stempel))
        self.assertTrue(datei.exists())

    def test_ohne_stempel_bleibt(self) -> None:
        g = _gui()
        self.assertFalse(g._quelle_nach_erfolg_loeschen(str(self.quelle), str(self.ergebnis), None))
        self.assertTrue(self.quelle.exists())

    def test_fehler_beim_loeschen_ist_eine_warnung_und_kein_absturz(self) -> None:
        g = _gui()
        with mock.patch.object(quelle_loeschen, "loeschen", return_value="Zugriff verweigert"):
            self.assertFalse(g._quelle_nach_erfolg_loeschen(str(self.quelle), str(self.ergebnis), self.stempel))
        self.assertTrue(any("nicht (ganz) löschen" in z and "Zugriff verweigert" in z for z in g._log), g._log)

    def test_datei_als_quelle(self) -> None:
        alt = self.wurzel / "alt.ffpfsc"
        alt.write_bytes(b"q" * 20)
        g = _gui()
        self.assertTrue(g._quelle_nach_erfolg_loeschen(str(alt), str(self.ergebnis), quelle_loeschen.stempel_nehmen(str(alt))))
        self.assertFalse(alt.exists())


class RueckfrageTests(unittest.TestCase):
    def _frage(self, antwort, mode: str = "universal_convert", quellen=None):
        g = _gui()
        g._batch_sources = quellen or []
        with mock.patch.object(APP.messagebox, "askyesnocancel", return_value=antwort) as frage:
            ergebnis = g._quelle_loeschen_bestaetigen(mode, "D:\\Spiele\\Spiel")
        return ergebnis, frage

    def test_ja_nein_abbrechen(self) -> None:
        for antwort in (True, False, None):
            with self.subTest(antwort=antwort):
                self.assertIs(antwort, self._frage(antwort)[0])

    def test_die_frage_nennt_die_quelle(self) -> None:
        _e, frage = self._frage(True)
        self.assertIn("D:\\Spiele\\Spiel", frage.call_args[0][1])

    def test_sammelkonvertierung_nennt_alle_quellen_und_kuerzt_lange_listen(self) -> None:
        quellen = ["D:\\Q\\Spiel%02d" % i for i in range(12)]
        _e, frage = self._frage(True, mode="batch_convert", quellen=quellen)
        text = frage.call_args[0][1]
        self.assertIn("Spiel00", text)
        self.assertIn("Spiel07", text)
        self.assertNotIn("Spiel11", text)
        self.assertIn("...", text)


class TexteTests(unittest.TestCase):
    def test_jeder_grund_der_pruefung_ist_in_allen_sprachen_uebersetzt(self) -> None:
        baum = ast.parse(Path(quelle_loeschen.__file__).read_text(encoding="utf-8"))
        pruefen = next(k for k in ast.walk(baum) if isinstance(k, ast.FunctionDef) and k.name == "pruefen")
        gruende = {r.value.value for r in ast.walk(pruefen)
                   if isinstance(r, ast.Return) and isinstance(r.value, ast.Constant) and r.value.value}
        self.assertGreaterEqual(len(gruende), 9)
        for grund in sorted(gruende):
            for sprache in SPRACHEN:
                with self.subTest(grund=grund, sprache=sprache):
                    text = i18n.translate(sprache, "quelle_loeschen.grund." + grund)
                    self.assertTrue(text and text != "quelle_loeschen.grund." + grund, "Text fehlt")

    def test_die_uebrigen_texte_gibt_es_in_allen_sprachen(self) -> None:
        for schluessel in ("main.quelle_loeschen", "dialog.title.quelle_loeschen", "dialog.msg.quelle_loeschen_frage",
                           "log.quelle_geloescht", "log.quelle_bleibt", "log.quelle_loeschen_fehler"):
            for sprache in SPRACHEN:
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    text = i18n.translate(sprache, schluessel, quellen="Q", pfad="P", grund="G", fehler="F")
                    self.assertTrue(text and text != schluessel)

    def test_platzhalter_der_frage_stimmen_in_jeder_sprache(self) -> None:
        for sprache in SPRACHEN:
            self.assertIn("{quellen}", i18n.STRINGS["dialog.msg.quelle_loeschen_frage"][sprache])


class QuelltextTests(unittest.TestCase):
    """Die Verdrahtung: Wer sie ausbaut, merkt es hier."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = Path(APP.__file__).read_text(encoding="utf-8")

    def _methode(self, name: str) -> str:
        baum = ast.parse(self.text)
        knoten = next(k for k in ast.walk(baum) if isinstance(k, ast.FunctionDef) and k.name == name)
        return ast.get_source_segment(self.text, knoten) or ""

    def test_die_rueckfrage_kommt_vor_dem_start_und_abbrechen_startet_nichts(self) -> None:
        quelle = self._methode("_launch_task")
        i_frage = quelle.index("_quelle_loeschen_bestaetigen")
        self.assertLess(i_frage, quelle.index("self.is_running = True"))
        self.assertLess(i_frage, quelle.index("threading.Thread("))
        stuecke = quelle[i_frage: i_frage + 300]
        self.assertRegex(stuecke, r"if antwort is None:\s+return")

    def test_der_arbeitsfaden_merkt_sich_den_stand_und_loescht_nach_dem_erfolg(self) -> None:
        quelle = self._methode("_run_engine_thread")
        # Bei einem Archiv als Quelle (Entpackordner oder Schattenordner) zeigt das Loeschen auf das Archiv, nicht auf den Ordner.
        self.assertIn("quelle_loeschen.stempel_nehmen(self._quelle_zum_loeschen(src))", quelle)
        self.assertIn("_quelle_nach_erfolg_loeschen(", quelle)
        # das Loeschen steht im Zweig des Erfolgs, nicht im Zweig des Abbruchs oder Fehlers
        i = quelle.index("_quelle_nach_erfolg_loeschen(")
        zweig_start = quelle.rfind("if completion_ok:", 0, i)
        zweig_ende = quelle.find("else:", i)
        self.assertGreater(zweig_start, 0)
        self.assertGreater(zweig_ende, i)

    def test_die_sammelkonvertierung_loescht_je_quelle_nach_deren_erfolg(self) -> None:
        quelle = self._methode("_run_flexible_conversion")
        self.assertIn("quelle_loeschen.stempel_nehmen(anzeige)", quelle)
        self.assertRegex(quelle, r"if item_ok:\s+self\._append_to_log\([^\n]+\n\s+self\._quelle_nach_erfolg_loeschen\(anzeige, output_path, quellstempel\)")
        # der Stempel entsteht VOR dem Entpacken eines Archivs
        self.assertLess(quelle.index("quelle_loeschen.stempel_nehmen(anzeige)"), quelle.index("_archiv_blockierend_entpacken("))

    def test_der_haken_wird_nicht_gespeichert(self) -> None:
        """Eine Wahl, die Daten endgueltig loescht, gilt nie von allein beim naechsten Start."""
        self.assertIn("self.quelle_loeschen_var = tk.BooleanVar(value=False)", self.text)
        self.assertNotRegex(self.text, r"_save_setting\(\s*[\"']quelle_loeschen")

    def test_die_kommandozeile_kennt_den_schalter_und_der_lauf_liest_ihn(self) -> None:
        self.assertIn('"--quelle-loeschen"', self.text)
        self.assertIn('app._cli_quelle_loeschen = bool(getattr(args, "quelle_loeschen", False))', self.text)
        self.assertIn('self._lauf_quelle_loeschen = bool(getattr(self, "_cli_quelle_loeschen", False))', self.text)

    def test_nur_lesende_und_aendernde_aufgaben_sind_ausgenommen(self) -> None:
        self.assertEqual(("inspect", "dump_validator", "ampr_manager"), GUI._QUELLE_LOESCHEN_AUSSER)


if __name__ == "__main__":
    unittest.main()
