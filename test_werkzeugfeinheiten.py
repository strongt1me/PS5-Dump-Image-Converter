# -*- coding: utf-8 -*-
"""Sechs Befunde aus der Werkzeugpruefung, die sich am Aufbau festmachen lassen.

Alle vom 04.09.2026, alle am Quelltext nachgewiesen:

* Der Autoloader-Schnappschuss legte jede Zieldatei mit ``open(..., "wb")``
  an, **bevor** das ``RETR`` lief - dieselbe Klasse wie beim ``debug.log``.
  Brach die Uebertragung ab, blieb eine 0-Byte- oder halbe Datei im
  Schnappschussordner liegen; gezaehlt wurde sie nicht, zu sehen war sie
  trotzdem, und beim Zurueckspielen ginge sie mit auf die Konsole.
* Fehler einzelner Dateien vermerkte er nur mit ``logger.debug``. Der Logger
  schreibt im Auslieferungsstand nichts - der Anwender erfuhr also nie, dass
  etwas fehlt.
* Bei FileZilla stand der ganze Auswahlblock eine Ebene zu weit links und lief
  auch dann, wenn die automatische Installation geglueckt war.
* Schlug sie fehl, blieb "FileZilla wird installiert..." dauerhaft in der
  Statuszeile stehen.
* Der JS Loader trug einen deutschen Knopftext fest im Quelltext, obwohl er
  seit jeher zweisprachig in ``i18n.py`` liegt.
* Sein Sendefaden meldete ueber ``win.after`` statt ueber
  ``_spaeter_im_fenster`` - schliesst der Anwender das Fenster waehrend des
  Sendens, wirft Tk im Faden.

Dazu die Credits-Bildlaufleiste: Sie wurde nach der Flaeche gepackt und war
deshalb ein Stummel in der Ecke.
"""
from __future__ import annotations

import ast
import os
import sys
import unittest

PROJEKT = os.path.dirname(os.path.abspath(__file__))
if PROJEKT not in sys.path:
    sys.path.insert(0, PROJEKT)

import pruefumgebung

pruefumgebung.umlenken("werkzeugfeinheiten")

from ps5_validator.utils.i18n import STRINGS

HAUPTDATEI = os.path.join(PROJEKT, "PS5ImageConverter_Pro_FINAL_revised.py")


class _Quelltext(unittest.TestCase):
    """Gemeinsamer Zugriff auf den Syntaxbaum des Hauptmoduls."""

    @classmethod
    def setUpClass(cls) -> None:
        with open(HAUPTDATEI, encoding="utf-8", errors="replace") as datei:
            cls.quelle = datei.read()
        cls.baum = ast.parse(cls.quelle)

    def _methode(self, name: str):
        klasse = next(k for k in self.baum.body
                      if isinstance(k, ast.ClassDef) and k.name == "PS5ConverterGUI")
        for k in klasse.body:
            if isinstance(k, ast.FunctionDef) and k.name == name:
                return k
        self.fail("Methode %s nicht gefunden" % name)


class AutoloaderSchnappschussTests(_Quelltext):
    """Kein RETR darf direkt in die Zieldatei gehen."""

    def test_es_wird_daneben_geschrieben(self) -> None:
        fenster = self._methode("_show_autoloader")
        # Jedes open(..., "wb") in diesem Fenster muss auf einen Pfad gehen,
        # der nicht das Ziel selbst ist - erkennbar am Namen "zwischen".
        offen = [k for k in ast.walk(fenster)
                 if isinstance(k, ast.Call) and getattr(k.func, "id", "") == "open"
                 and any(isinstance(a, ast.Constant) and a.value == "wb"
                         for a in k.args)]
        self.assertTrue(offen, "Kein Schreibzugriff gefunden - Pruefung greift nicht.")
        for aufruf in offen:
            ziel = aufruf.args[0]
            with self.subTest(zeile=aufruf.lineno):
                self.assertTrue(
                    isinstance(ziel, ast.Name) and ziel.id == "zwischen",
                    "Zeile %d schreibt direkt in die Zieldatei - bricht die "
                    "Uebertragung ab, bleibt eine halbe Datei liegen."
                    % aufruf.lineno)

    def test_am_ende_wird_umbenannt(self) -> None:
        fenster = self._methode("_show_autoloader")
        umbenannt = [k for k in ast.walk(fenster)
                     if isinstance(k, ast.Call)
                     and getattr(k.func, "attr", "") == "replace"
                     and getattr(getattr(k.func, "value", None), "id", "") == "os"]
        self.assertTrue(umbenannt,
                        "Die Zwischendatei wird nirgends an ihren Platz gerueckt.")

    def test_misslungene_dateien_werden_gemeldet(self) -> None:
        """Frueher nur logger.debug - und der schreibt ausgeliefert nichts."""
        self.assertIn("autoloader.snapshot_incomplete", self.quelle)
        for sprache in ("de", "en"):
            with self.subTest(sprache=sprache):
                text = STRINGS["autoloader.snapshot_incomplete"][sprache]
                self.assertIn("{count}", text)
                self.assertIn("{names}", text)


class FileZillaAuswahlTests(_Quelltext):
    """Der Auswahldialog gehoert in das "wenn nichts gefunden"."""

    def test_der_dialogblock_liegt_im_richtigen_zweig(self) -> None:
        weiter = self._methode("_filezilla_weiter")
        # Die Dateidialoge duerfen nicht auf der obersten Ebene der Methode
        # stehen, sondern muessen unterhalb eines "if" liegen.
        oberste = [k for k in weiter.body
                   if isinstance(k, ast.Expr) or isinstance(k, ast.Assign)]
        namen = []
        for knoten in oberste:
            for k in ast.walk(knoten):
                if isinstance(k, ast.Call) and getattr(k.func, "attr", "") in (
                        "askdirectory", "askopenfilename"):
                    namen.append(k.lineno)
        self.assertEqual(
            [], namen,
            "In Zeile(n) %s steht ein Auswahldialog unbedingt - er erscheint "
            "dann auch nach einer geglueckten Installation." % namen)

    def test_die_statuszeile_wird_zurueckgenommen(self) -> None:
        """Sonst steht dort dauerhaft 'FileZilla wird installiert...'."""
        weiter = self._methode("_filezilla_weiter")
        bereit = [k for k in ast.walk(weiter)
                  if isinstance(k, ast.Constant) and k.value == "main.status_ready"]
        self.assertTrue(
            bereit,
            "Auf dem Fehlschlagweg bleibt die Installationsmeldung stehen.")


class JsLoaderTests(_Quelltext):
    """Fester Text und ein ungesicherter Rueckweg."""

    def test_der_knopftext_kommt_aus_i18n(self) -> None:
        self.assertNotIn('text="Log-Server starten', self.quelle)
        self.assertIn("jsloader.start_logserver_button", self.quelle)

    def test_der_sendefaden_meldet_ueber_spaeter_im_fenster(self) -> None:
        fenster = self._methode("_show_js_loader")
        senden = [f for f in ast.walk(fenster)
                  if isinstance(f, ast.FunctionDef) and f.name == "_do_send"]
        self.assertEqual(1, len(senden), "Der Sendefaden wurde umbenannt.")
        ueber_after = [k.lineno for k in ast.walk(senden[0])
                       if isinstance(k, ast.Call)
                       and getattr(k.func, "attr", "") == "after"]
        self.assertEqual(
            [], ueber_after,
            "Zeile(n) %s melden ueber win.after. Schliesst der Anwender das "
            "Fenster waehrend des Sendens, wirft Tk im Faden." % ueber_after)
        abgesichert = [k for k in ast.walk(senden[0])
                       if isinstance(k, ast.Call)
                       and getattr(k.func, "attr", "") == "_spaeter_im_fenster"]
        self.assertGreaterEqual(len(abgesichert), 2,
                                "Erfolgs- und Fehlerzweig brauchen beide den "
                                "abgesicherten Rueckweg.")


class CreditsLeisteTests(_Quelltext):
    """Die Bildlaufleiste muss vor der Flaeche gepackt werden."""

    def test_die_leiste_kommt_zuerst(self) -> None:
        fenster = self._methode("_show_credits")
        reihenfolge = []
        for k in ast.walk(fenster):
            if not (isinstance(k, ast.Call) and getattr(k.func, "attr", "") == "pack"):
                continue
            ziel = getattr(getattr(k.func, "value", None), "id", "")
            if ziel in ("vsb", "scroll_canvas"):
                reihenfolge.append((k.lineno, ziel))
        reihenfolge.sort()
        namen = [n for _z, n in reihenfolge]
        self.assertEqual(
            ["vsb", "scroll_canvas"], namen[:2],
            "Der Canvas wird vor der Leiste gepackt und nimmt den Hohlraum "
            "zuerst - die Leiste bleibt ein Stummel in der Ecke. Gefunden: %s"
            % namen)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class ParamEditorTests(_Quelltext):
    """Zwei Wege, auf denen der Editor Arbeit verlor."""

    def test_entfernen_leert_auch_das_schnellfeld(self) -> None:
        """Sonst schreibt _save den alten Wert wieder zurueck.

        Die Zeile verschwand aus der Tabelle, stand in der gespeicherten Datei
        aber weiterhin drin - und zwar bei genau den Schluesseln, die man am
        ehesten von Hand entfernt: titleId, contentId, applicationDrmType,
        contentVersion.
        """
        editor = self._methode("_render_param_manifest_editor")
        entfernen = [f for f in ast.walk(editor)
                     if isinstance(f, ast.FunctionDef) and f.name == "_remove_row"]
        self.assertEqual(1, len(entfernen), "_remove_row wurde umbenannt.")
        fasst_an = [k for k in ast.walk(entfernen[0])
                    if isinstance(k, ast.Name) and k.id == "quick_keys"]
        self.assertTrue(
            fasst_an,
            "_remove_row laesst die Schnellfelder unberuehrt - _save schreibt "
            "den alten Wert dann wieder nach data zurueck.")

    def test_schliessen_fragt_bei_ungespeicherten_aenderungen(self) -> None:
        """Vorher rief der Knopf blank win.destroy."""
        editor = self._methode("_render_param_manifest_editor")
        namen = {f.name for f in ast.walk(editor)
                 if isinstance(f, ast.FunctionDef)}
        self.assertIn("_beim_schliessen", namen,
                      "Es gibt keinen eigenen Schliessweg mehr.")
        self.assertIn("_etwas_geaendert", namen,
                      "Ohne Vergleich weiss das Fenster nicht, ob es fragen muss.")

        # Vorhanden zu sein genuegt nicht - der Weg muss auch benutzt werden.
        # Beim Schreiben dieser Pruefung gemessen: Setzt man den Knopf wieder
        # auf win.destroy und nimmt das protocol heraus, blieb die Fassung,
        # die nur die Funktionsnamen abfragte, gruen.
        knopf_faellt_darauf = [
            k for k in ast.walk(editor)
            if isinstance(k, ast.Call)
            and getattr(k.func, "attr", "") == "Button"
            and any(w.arg == "command"
                    and getattr(w.value, "id", "") == "_beim_schliessen"
                    for w in k.keywords)]
        self.assertTrue(
            knopf_faellt_darauf,
            "Kein Knopf ruft _beim_schliessen - der Schliessknopf geht wieder "
            "an der Rueckfrage vorbei.")

        # Und das Fensterkreuz muss denselben Weg nehmen; der Umschalter in
        # der Titelleiste geht ueber dieses Protokoll.
        protokoll = [
            k for k in ast.walk(editor)
            if isinstance(k, ast.Call)
            and getattr(k.func, "attr", "") == "protocol"
            and any(isinstance(a, ast.Constant) and a.value == "WM_DELETE_WINDOW"
                    for a in k.args)
            and any(getattr(a, "id", "") == "_beim_schliessen" for a in k.args)]
        self.assertTrue(protokoll,
                        "WM_DELETE_WINDOW zeigt nicht auf _beim_schliessen - "
                        "ueber das Kreuz geht die Arbeit kommentarlos verloren.")

    def test_die_rueckfrage_gibt_es_zweisprachig(self) -> None:
        for name in ("param_manifest.discard_title",
                     "param_manifest.discard_message"):
            with self.subTest(schluessel=name):
                self.assertIn(name, STRINGS)
                for sprache in ("de", "en"):
                    self.assertTrue(STRINGS[name].get(sprache, "").strip())


class PkgMergerKennungTests(_Quelltext):
    """Ein leerer Basisname zerlegte den Fensteraufbau.

    ``_try_parse_name`` liefert fuer eine Datei namens ``_0.pkg`` das Paar
    ``("", "0")``. Ein leeres ``iid`` ist in Tk die Wurzel des Baums;
    ``insert()`` quittiert das mit ``TclError: Item  already exists``, und der
    Aufbau brach mitten in der Schleife ab - Kopfzeile ohne Liste, ohne
    Knopfreihe.
    """

    def test_ein_leerer_basisname_kommt_wirklich_vor(self) -> None:
        """Ohne das waere die Behebung unten grundlos."""
        from ps5_validator.utils.pkg_merger import _try_parse_name

        self.assertEqual(("", "0"), _try_parse_name("_0.pkg"))

    def test_tk_lehnt_ein_leeres_iid_ab(self) -> None:
        """Die Gegenprobe zur Behebung - gemessen, nicht angenommen."""
        try:
            import tkinter as tk
            from tkinter import ttk
        except Exception:                        # pragma: no cover
            self.skipTest("Ohne Tk nicht pruefbar")
        wurzel = tk._default_root or tk.Tk()
        wurzel.withdraw()
        baum = ttk.Treeview(wurzel, columns=("a",), show="headings")
        try:
            with self.assertRaises(tk.TclError):
                baum.insert("", "end", iid="", values=("x",))
        finally:
            baum.destroy()

    def test_die_kennung_kommt_nicht_mehr_aus_dem_namen(self) -> None:
        # Die Tabelle wird in _render_pkg_merger_window gefuellt, nicht
        # in _show_pkg_merger_dialog - jenes sucht nur die Saetze.
        fenster = self._methode("_render_pkg_merger_window")
        gesehen = 0
        for aufruf in ast.walk(fenster):
            if not (isinstance(aufruf, ast.Call)
                    and getattr(aufruf.func, "attr", "") == "insert"):
                continue
            for wort in aufruf.keywords:
                if wort.arg != "iid":
                    continue
                with self.subTest(zeile=aufruf.lineno):
                    self.assertFalse(
                        isinstance(wort.value, ast.Attribute)
                        and wort.value.attr == "base_name",
                        "Zeile %d nimmt wieder den Basisnamen als Kennung - "
                        "ist er leer, bricht der Fensteraufbau ab."
                        % aufruf.lineno)
                    gesehen += 1
        self.assertTrue(gesehen, "Kein insert mit iid gefunden - die Pruefung "
                                 "greift nicht mehr.")


class KlogZeitstempelTests(_Quelltext):
    """Die Empfangszeit muss beim Empfang festgehalten werden.

    Der Zeitstempel entstand erst beim Zeichnen (``datetime.now()`` in
    ``_formatted``), gespeichert wurde nur die nackte Zeile. ``_reapply_filter``
    haengt an ``filter_var.trace_add`` und zeichnet bei **jedem Tastendruck**
    im Filterfeld alles neu - danach trugen alle laengst empfangenen Zeilen die
    aktuelle Uhrzeit. In einem Kernel-Protokoll ist gerade der zeitliche
    Zusammenhang das, weswegen man hineinsieht.
    """

    def test_die_zeit_wird_nicht_beim_zeichnen_gebildet(self) -> None:
        fenster = self._methode("_show_klog_window")
        formatiert = [f for f in ast.walk(fenster)
                      if isinstance(f, ast.FunctionDef) and f.name == "_formatted"]
        self.assertEqual(1, len(formatiert), "_formatted wurde umbenannt.")
        jetzt = [k.lineno for k in ast.walk(formatiert[0])
                 if isinstance(k, ast.Call)
                 and getattr(k.func, "attr", "") == "now"]
        self.assertEqual(
            [], jetzt,
            "Zeile(n) %s bilden die Zeit erst beim Zeichnen - beim Filtern "
            "bekommt dann jede alte Zeile die aktuelle Uhrzeit." % jetzt)

    def test_die_zeit_kommt_als_wert_herein(self) -> None:
        fenster = self._methode("_show_klog_window")
        formatiert = next(f for f in ast.walk(fenster)
                          if isinstance(f, ast.FunctionDef) and f.name == "_formatted")
        namen = [a.arg for a in formatiert.args.args]
        self.assertIn("zeit", namen,
                      "_formatted bekommt die Empfangszeit nicht uebergeben.")

    def test_gespeichert_wird_zeile_und_zeit(self) -> None:
        fenster = self._methode("_show_klog_window")
        gerendert = next(f for f in ast.walk(fenster)
                         if isinstance(f, ast.FunctionDef) and f.name == "_render_line")
        angehaengt = [k for k in ast.walk(gerendert)
                      if isinstance(k, ast.Call)
                      and getattr(k.func, "attr", "") == "append"]
        self.assertTrue(angehaengt, "Es wird nichts mehr gespeichert.")
        for k in angehaengt:
            with self.subTest(zeile=k.lineno):
                self.assertTrue(
                    k.args and isinstance(k.args[0], ast.Tuple),
                    "Zeile %d speichert wieder nur die nackte Zeile - die "
                    "Empfangszeit ist damit verloren." % k.lineno)


class BibliothekQuelleTests(_Quelltext):
    """Die Sammelauswahl muss mit zurueckgesetzt werden.

    Aufgabe 5 arbeitet nicht mit ``source_path``, sondern mit
    ``_batch_sources``. Wer dort mehrere Dateien gewaehlt hatte und danach aus
    der Bibliothek einen Eintrag als Quelle uebernahm, sah im Quellfeld die
    neue Datei - konvertiert wurden beim Start aber weiter die alten. Das Feld
    log damit ueber das, was wirklich geschieht.
    """

    def test_die_uebernahme_raeumt_die_sammelauswahl(self) -> None:
        fenster = self._methode("_render_library_window")
        nehmen = [f for f in ast.walk(fenster)
                  if isinstance(f, ast.FunctionDef) and f.name == "_use_as_source"]
        self.assertEqual(1, len(nehmen), "_use_as_source wurde umbenannt.")
        raeumt = [k for k in ast.walk(nehmen[0])
                  if isinstance(k, ast.Attribute) and k.attr == "_batch_sources"]
        self.assertTrue(
            raeumt,
            "_use_as_source laesst _batch_sources stehen - Aufgabe 5 "
            "konvertiert danach die alten Dateien weiter.")
