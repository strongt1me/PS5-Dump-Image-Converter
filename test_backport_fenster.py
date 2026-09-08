# -*- coding: utf-8 -*-
"""Das BACKPORT-Fenster: Analyse im Arbeitsfaden, Platz und Quellordner.

Vier Befunde vom 04.09.2026:

* **M006** – ``_analysieren`` las jede Kandidatendatei vollstaendig
  (``fh.read()``) im Oberflaechenfaden, ohne Fortschrittsanzeige. Bei einem
  PS5-Dump sind das die eboot.bin und jede .prx/.sprx des ganzen Baums. Das
  lief beim Oeffnen des Fensters und noch einmal bei jedem Wechsel der
  Ziel-Firmware; die Statuszeile stand derweil auf "Bereit.".
* **M005** – Brach der Lauf ab, gab es nur eine Zeile in der Statuszeile:
  kein Protokolleintrag, kein Dialog. Der Erfolgsfall tut beides.
* **M007** – Die Sicherung kopierte den ganzen Dump-Ordner, ohne vorher den
  freien Platz zu pruefen. Bei einem PS5-Spiel sind das 40 bis 100 GB ein
  zweites Mal.
* **M009** – Beim Waehlen wurde nur geprueft, ob der Pfad ein Ordner ist.
  ``ps5_backport.kandidaten`` laeuft danach rekursiv ueber den ganzen Baum.

Geprueft wird am Syntaxbaum und an echten Ordnern - nicht ueber
Zeichenkettensuche im Quelltext.
"""
from __future__ import annotations

import ast
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("backport_fenster")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402

HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"


class _Quelltext(unittest.TestCase):
    """Gemeinsame Grundlage: der Syntaxbaum des Fensters."""

    @classmethod
    def setUpClass(cls):
        with io.open(HAUPTDATEI, encoding="utf-8") as fh:
            cls.quelle = fh.read()
        cls.baum = ast.parse(cls.quelle)

    def _methode(self, name: str) -> ast.FunctionDef:
        for k in ast.walk(self.baum):
            if isinstance(k, ast.FunctionDef) and k.name == name:
                return k
        self.fail("Methode %s gibt es nicht mehr" % name)

    def _innere(self, aussen: str, innen: str) -> ast.FunctionDef:
        for k in ast.walk(self._methode(aussen)):
            if isinstance(k, ast.FunctionDef) and k.name == innen:
                return k
        self.fail("%s enthaelt kein %s mehr" % (aussen, innen))


class AnalyseImFadenTests(_Quelltext):
    """Das Lesen gehoert nicht in den Oberflaechenfaden."""

    def test_die_analyse_startet_einen_faden(self):
        m = self._innere("_render_backport_window", "_analysieren")
        faeden = [k for k in ast.walk(m) if isinstance(k, ast.Call)
                  and "Thread" in ast.dump(k.func)]
        self.assertTrue(faeden,
                        "Die Analyse liest wieder im Oberflaechenfaden - bei "
                        "einem grossen Dump steht das Fenster dann still.")

    def test_der_lesende_teil_fasst_kein_tk_an(self):
        """Im Arbeitsfaden darf nichts in den Baum geschrieben werden."""
        m = self._innere("_render_backport_window", "_analyse_lauf")
        verboten = []
        for k in ast.walk(m):
            if not isinstance(k, ast.Call):
                continue
            name = getattr(k.func, "attr", "")
            if name in ("insert", "delete", "set", "configure", "config"):
                # baum.set/insert und stand_var.set gehoeren in den Hauptfaden.
                ziel = getattr(getattr(k.func, "value", None), "id", "")
                if ziel in ("baum", "stand_var", "analyse_btn", "start_btn"):
                    verboten.append((k.lineno, ziel, name))
        self.assertEqual([], verboten,
                         "Aus dem Arbeitsfaden heraus an Tk: %s" % (verboten,))

    def test_das_ergebnis_kommt_ueber_den_hausweg_zurueck(self):
        m = self._innere("_render_backport_window", "_analyse_lauf")
        aufrufe = [getattr(k.func, "attr", "") for k in ast.walk(m)
                   if isinstance(k, ast.Call)]
        self.assertIn("_spaeter_im_fenster", aufrufe,
                      "Ueber root.after statt _spaeter_im_fenster - dann "
                      "faellt es um, wenn das Fenster inzwischen zu ist.")

    def test_zwei_laeufe_gleichzeitig_gehen_nicht(self):
        """Die Firmware-Klappliste loest die Analyse bei jedem Wechsel aus."""
        m = self._innere("_render_backport_window", "_analysieren")
        quelle = ast.get_source_segment(self.quelle, m) or ""
        self.assertIn('laeuft["aktiv"]', quelle)


class PlatzpruefungTests(_Quelltext):
    """Die Sicherung verdoppelt den Platzbedarf."""

    def test_es_gibt_eine_pruefung_vor_dem_kopieren(self):
        self._methode("_backport_platz_pruefen")

    def test_sie_laeuft_im_hauptstrang_nicht_im_arbeiter(self):
        """Eine Rueckfrage aus dem Arbeitsfaden waere der bekannte Fehler."""
        arbeiter = self._methode("_backport_worker")
        aufrufe = [getattr(k.func, "attr", "") for k in ast.walk(arbeiter)
                   if isinstance(k, ast.Call)]
        self.assertNotIn("_backport_platz_pruefen", aufrufe,
                         "Die Pruefung zeigt einen Dialog - im Arbeitsfaden "
                         "waere das falsch.")
        starter = self._innere("_render_backport_window", "_starten")
        aufrufe_start = [getattr(k.func, "attr", "") for k in ast.walk(starter)
                         if isinstance(k, ast.Call)]
        self.assertIn("_backport_platz_pruefen", aufrufe_start)

    def test_bei_reichlich_platz_wird_nicht_gefragt(self):
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._t = lambda k, **kw: k
        gui._fmt_bytes = lambda n: "%d B" % n
        gui._append_to_log = lambda *_a: None
        with tempfile.TemporaryDirectory(prefix="bp_platz_") as basis:
            dump = os.path.join(basis, "spiel")
            os.makedirs(dump)
            with io.open(os.path.join(dump, "eboot.bin"), "wb") as fh:
                fh.write(b"x" * 1024)
            gui._get_path_size = lambda _p, **_k: 1024
            self.assertIs(True, gui._backport_platz_pruefen(dump, None))

    def test_bei_zu_wenig_platz_wird_gefragt(self):
        """Und ohne Zustimmung wird abgebrochen (None)."""
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._t = lambda k, **kw: k
        gui._fmt_bytes = lambda n: "%d B" % n
        gui._append_to_log = lambda *_a: None
        gefragt: list = []
        with tempfile.TemporaryDirectory(prefix="bp_platz2_") as basis:
            dump = os.path.join(basis, "spiel")
            os.makedirs(dump)
            # Groesser als jeder freie Platz.
            gui._get_path_size = lambda _p, **_k: 1 << 62
            from unittest import mock
            with mock.patch.object(APP.messagebox, "askyesno",
                                   lambda *a, **k: gefragt.append(a) or False):
                self.assertIsNone(gui._backport_platz_pruefen(dump, None))
        self.assertTrue(gefragt, "Es wurde gar nicht gefragt.")

    def test_bei_zustimmung_geht_es_ohne_sicherung_weiter(self):
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._t = lambda k, **kw: k
        gui._fmt_bytes = lambda n: "%d B" % n
        gui._append_to_log = lambda *_a: None
        with tempfile.TemporaryDirectory(prefix="bp_platz3_") as basis:
            dump = os.path.join(basis, "spiel")
            os.makedirs(dump)
            gui._get_path_size = lambda _p, **_k: 1 << 62
            from unittest import mock
            with mock.patch.object(APP.messagebox, "askyesno",
                                   lambda *a, **k: True):
                self.assertIs(False, gui._backport_platz_pruefen(dump, None))

    def test_nicht_messbar_haelt_den_lauf_nicht_auf(self):
        """Ein Netzlaufwerk kann die Auskunft verweigern."""
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._t = lambda k, **kw: k
        gui._fmt_bytes = lambda n: "%d B" % n
        gui._append_to_log = lambda *_a: None

        def _wirft(*_a, **_k):
            raise OSError("nicht messbar")
        gui._get_path_size = _wirft
        with tempfile.TemporaryDirectory(prefix="bp_platz4_") as basis:
            self.assertIs(True, gui._backport_platz_pruefen(basis, None))


class AbbruchmeldungTests(_Quelltext):
    """Ein Fehlschlag meldet sich so deutlich wie ein Erfolg."""

    def test_der_fehlerzweig_schreibt_ins_protokoll_und_zeigt_einen_dialog(self):
        arbeiter = self._methode("_backport_worker")
        # Den aeusseren except-Block finden.
        versuche = [k for k in ast.walk(arbeiter) if isinstance(k, ast.Try)]
        self.assertTrue(versuche)
        fehlerzweige = [h for v in versuche for h in v.handlers]
        aufrufe = {getattr(k.func, "attr", "") for h in fehlerzweige
                   for k in ast.walk(h) if isinstance(k, ast.Call)}
        self.assertIn("_append_to_log", aufrufe,
                      "Der Fehlschlag steht nur in der Statuszeile - die ist "
                      "beim naechsten Lauf weg.")

        # Die blosse Anwesenheit von showerror genuegt NICHT: Beim ersten
        # Anlauf fand dieser Test es in der Definition von _fehlermeldung,
        # obwohl der Aufruf entfernt war - die Gegenprobe blieb gruen.
        # Geprueft wird deshalb, dass die Funktion, die den Dialog zeigt,
        # auch wirklich eingeplant wird.
        zeiger: set[str] = set()
        for h in fehlerzweige:
            for k in ast.walk(h):
                if not (isinstance(k, ast.Call)
                        and getattr(k.func, "attr", "") == "after"):
                    continue
                for a in k.args:
                    if isinstance(a, ast.Name):
                        zeiger.add(a.id)
                    elif isinstance(a, ast.Lambda):
                        zeiger.update(n.id for n in ast.walk(a)
                                      if isinstance(n, ast.Name))
        dialogtraeger = {f.name for h in fehlerzweige for f in ast.walk(h)
                         if isinstance(f, ast.FunctionDef)
                         and any(getattr(c.func, "attr", "") == "showerror"
                                 for c in ast.walk(f) if isinstance(c, ast.Call))}
        self.assertTrue(dialogtraeger,
                        "Der Erfolgsfall zeigt einen Dialog, der Fehlschlag "
                        "nicht - genau verkehrt herum.")
        self.assertTrue(dialogtraeger & zeiger,
                        "Der Dialog ist zwar geschrieben, wird aber nie "
                        "eingeplant: %s wird nirgends an after() uebergeben."
                        % ", ".join(sorted(dialogtraeger)))


class QuellordnerTests(_Quelltext):
    """Nicht jeder Ordner ist ein Dump."""

    def test_die_wahl_prueft_den_ordner(self):
        m = self._methode("_show_backport")
        aufrufe = [getattr(k.func, "attr", "") for k in ast.walk(m)
                   if isinstance(k, ast.Call)]
        self.assertIn("_looks_like_dump_folder", aufrufe,
                      "Jeder Ordner wird angenommen - und danach rekursiv "
                      "durchsucht und kopiert.")

    def test_der_vorhandene_helfer_wird_benutzt_statt_einer_eigenen_abfrage(self):
        """Er laesst auch einen Dump ohne param.json durch, wenn eine
        eboot.bin dasteht - genau die, um die es dem Backport geht."""
        self.assertTrue(APP.PS5ConverterGUI._looks_like_dump_folder(
            str(PROJEKT)) in (True, False))
        with tempfile.TemporaryDirectory(prefix="bp_quelle_") as basis:
            self.assertFalse(APP.PS5ConverterGUI._looks_like_dump_folder(basis))
            with io.open(os.path.join(basis, "eboot.bin"), "wb") as fh:
                fh.write(b"x")
            self.assertTrue(APP.PS5ConverterGUI._looks_like_dump_folder(basis))


class SprachfuehrungTests(unittest.TestCase):
    """Die Beanstandungen kommen aus einem Modul ohne i18n - und trotzdem
    zweisprachig.

    ``shadowmount_generation`` darf ``i18n`` nicht importieren; es soll ohne
    die Oberflaeche benutzbar bleiben. Bis zum 05.09.2026 lieferte es deshalb
    feste deutsche Saetze, und die standen unuebersetzt im Protokoll und in
    der Kollisionswarnung - auch wenn das Programm auf Englisch lief. Seither
    reicht die Oberflaeche Textvorlagen herein, wie bei ``pkg_merger``.
    """

    def _kollision(self, sprache: str) -> str:
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._t = lambda k, _s=sprache, **kw: APP.i18n_translate(_s, k, **kw)
        with tempfile.TemporaryDirectory(prefix="fakelib_kol_") as d:
            os.makedirs(os.path.join(d, "fakelib"))
            os.makedirs(os.path.join(d, "fakelib2"))
            return gui._fakelib_kollision(d)

    def test_das_helfermodul_kennt_i18n_nicht(self):
        """Die Hausregel - sonst haengt es an der Oberflaeche."""
        from ps5_validator.utils import shadowmount_generation as smg
        with io.open(smg.__file__, encoding="utf-8") as fh:
            quelle = fh.read()
        self.assertNotIn("import i18n", quelle)
        self.assertNotIn("from ps5_validator.utils.i18n", quelle)

    def test_die_englische_warnung_traegt_keinen_deutschen_satz(self):
        englisch = self._kollision("en")
        self.assertTrue(englisch, "Es kam gar keine Warnung.")
        for deutsch in ("Beide Ordner vorhanden", "Im Spielordner liegt",
                        "bleibt ungenutzt", "wird der dort ignoriert"):
            self.assertNotIn(deutsch, englisch,
                             "Deutscher Satz in der englischen Oberflaeche: %r"
                             % deutsch)

    def test_die_deutsche_warnung_bleibt_deutsch(self):
        deutsch = self._kollision("de")
        self.assertIn("Beide Ordner vorhanden", deutsch)

    def test_fuer_jede_kennung_gibt_es_einen_text(self):
        """Eine fehlende Vorlage faellt sonst erst im Betrieb auf."""
        from ps5_validator.utils import shadowmount_generation as smg
        from ps5_validator.utils.i18n import STRINGS
        for kennung in smg.MELDUNGEN:
            with self.subTest(kennung=kennung):
                self.assertIn("smgen." + kennung, STRINGS)

    def test_ohne_vorlagen_bleibt_es_beim_eingebauten_satz(self):
        """Das Modul muss allein benutzbar bleiben."""
        from ps5_validator.utils import shadowmount_generation as smg
        meldungen = smg.beanstandungen(smg.NEU, smg.ORT_SPIEL,
                                       ["fakelib", "fakelib2"])
        self.assertTrue(meldungen)
        self.assertIn("Spielordner", meldungen[0])

    def test_eine_unbrauchbare_vorlage_sprengt_nichts(self):
        """Ein Platzhalter, den es nicht gibt, darf die Pruefung nicht kippen."""
        from ps5_validator.utils import shadowmount_generation as smg
        meldungen = smg.beanstandungen(
            smg.NEU, smg.ORT_SPIEL, ["fakelib", "fakelib2"],
            texte={"spiel_fakelib2_wirkungslos": "kaputt {gibtsnicht}"})
        self.assertTrue(meldungen)
        self.assertNotIn("{gibtsnicht}", meldungen[0])


class RueckfrageNenntDieSicherungTests(unittest.TestCase):
    """Die Rueckfrage muss sagen, ob es einen Weg zurueck gibt.

    Sie sagte bis v1.9.11 nur "Die Originale werden dabei ersetzt.
    Fortfahren?". Ob eine Sicherung angelegt wird, stand nirgends - und wer
    den Haken abgewaehlt hatte, bestaetigte ohne zu wissen, dass es keinen
    Rueckweg gibt.

    Bricht der Lauf mittendrin ab, ist der Dump zum Teil bearbeitet: einige
    Dateien herabgesetzt, andere nicht. Genau das sagte das Programm erst
    **hinterher**, in backport.error_message.

    Damit die Frage ehrlich gestellt werden kann, muss die Platzpruefung
    vorher laufen - sie kann eine gewuenschte Sicherung noch in ein "ohne
    Sicherung weiter" verwandeln.
    """

    @classmethod
    def setUpClass(cls):
        import ast
        from pathlib import Path
        cls.quelle = (Path(__file__).resolve().parent
                      / "PS5ImageConverter_Pro_FINAL_revised.py"
                      ).read_text(encoding="utf-8")
        # Ueber den Syntaxbaum, nicht ueber eine Textsuche nach
        # "def _starten": Diesen Namen gibt es mehrfach, und die erste
        # Fundstelle liegt im AMPR-Fenster. Genau darauf bin ich beim
        # Schreiben dieser Pruefung hereingefallen.
        baum = ast.parse(cls.quelle)
        fenster = next(k for k in ast.walk(baum)
                       if isinstance(k, ast.FunctionDef)
                       and k.name == "_render_backport_window")
        starten = next(k for k in ast.walk(fenster)
                       if isinstance(k, ast.FunctionDef) and k.name == "_starten")
        cls.rumpf = ast.unparse(starten)

    def test_die_rueckfrage_nennt_den_sicherungsstand(self):
        self.assertIn("backport.confirm_backup", self.rumpf)
        self.assertIn("backport.confirm_no_backup", self.rumpf)

    def test_die_platzpruefung_laeuft_vor_der_rueckfrage(self):
        """Sonst steht beim Fragen noch nicht fest, was gilt."""
        platz = self.rumpf.index("_backport_platz_pruefen")
        frage = self.rumpf.index("backport.confirm_message")
        self.assertLess(platz, frage,
                        "Die Platzpruefung steht wieder hinter der "
                        "Rueckfrage - dann nennt die Rueckfrage einen "
                        "Sicherungsstand, der noch gar nicht feststeht.")

    def test_beide_texte_gibt_es_in_zwei_sprachen(self):
        from ps5_validator.utils import i18n
        for schluessel in ("backport.confirm_backup", "backport.confirm_no_backup"):
            with self.subTest(schluessel=schluessel):
                eintrag = i18n.STRINGS.get(schluessel)
                self.assertIsNotNone(eintrag)
                for sprache in i18n.SUPPORTED_LANGUAGES:
                    self.assertTrue(eintrag.get(sprache), sprache)

    def test_die_warnung_ohne_sicherung_ist_deutlich(self):
        """Anker: Ein lauwarmer Satz taete es hier nicht."""
        from ps5_validator.utils import i18n
        text = i18n.STRINGS["backport.confirm_no_backup"]["de"]
        self.assertIn("KEINE", text)
        self.assertIn("nicht r", text)      # "nicht rueckgaengig"


if __name__ == "__main__":
    unittest.main()
