# -*- coding: utf-8 -*-
"""Teilschritte dürfen den Balken nicht roh beschreiben.

Ein Teilschritt - die Arbeitskopie vor der Integration, das Packen der
AMPR-Asset-Bänder - kennt seinen eigenen Fortschritt von 0 bis 100, aber
nicht, wo im Gesamtlauf er steht. Wer diesen Rohwert über ``_set_progress``
direkt auf den Balken schreibt, kämpft gegen ``_update_progress_gui``: Der
Takt setzt 80 ms später wieder den Gesamtwert, und der Balken zappelt.

Gemessen wurde das nicht hier, sondern **beim Anwender**, in den
Diagnoseberichten seiner eigenen Läufe:

    v1.9.6    207 s Lauf     keine Auffälligkeit
    v1.9.12    45 s Lauf      26 Rücksprünge, bis  2,6 % -> 0,0 %
    v1.9.12  1769 s Lauf     284 Rücksprünge, bis 100,0 % -> 0,0 %
    v1.9.12  4453 s Lauf     567 Rücksprünge, bis 100,0 % -> 0,0 %

Beide Melder sind erst nach v1.9.6 dazugekommen - deshalb ist der ältere
Bericht sauber. Die Folge war nicht nur Optik: ``_stillstand_uhr`` erkennt
einen Aufhänger daran, dass sich weder Balken noch Statustext bewegen, und
schrieb bei jedem größeren Lauf einen Stapelabzug als ERROR ins Protokoll.
Am 10.09.2026 schon bei einem 5,6-GB-Titel nachgestellt: Meldung nach genau
120 s, mitten in der Arbeitskopie.

Die Prüfungen hier messen die Eigenschaft, nicht die Schreibweise: Eine
Suche nach ``_set_progress(`` im Quelltext stirbt still, sobald jemand den
Aufruf verschiebt.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HAUPTDATEI = Path(__file__).resolve().parent / "PS5ImageConverter_Pro_FINAL_revised.py"


def _lade_hauptprogramm():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


class _Aufzeichnung:
    """Trägt genau die Felder, die die beiden Melder anfassen.

    ``_set_progress`` wird mitgeschrieben statt ausgeführt: Die Prüfung will
    wissen, **womit** es gerufen wurde. Ein Zahlenwert als erstes Argument ist
    der Fehler, den es hier zu verhindern gilt; ``None`` heißt "nur Text".
    """

    def __init__(self, haupt):
        self._haupt = haupt
        self.task_progress = 0.0
        self.is_running = True
        self._teilschritt_merker = None
        self._pack_letzte_phase = ""
        self._pack_letzte_phase_zeit = 0.0
        self.balkenwerte: list[object] = []
        self.statuszeilen: list[str] = []
        self.verlauf: list[float] = []
        # Die Zaehler, die ``_update_progress_gui`` auswertet ("Quelle 3").
        self._copy_total_bytes = 0
        self._copy_done_bytes = 0
        self._copy_total_exact = False
        self._copy_rate_bps = 0.0
        self._copy_rate_trend = ""
        self._pack_infotext = ""

    # --- die geprüften Methoden, an die Attrappe gebunden -----------------
    def _teilschritt_melden(self, schluessel, anteil, spanne):
        self._haupt.PS5ConverterGUI._teilschritt_melden(
            self, schluessel, anteil, spanne)
        self.verlauf.append(self.task_progress)

    def _ampr_pack_fortschritt(self, prozent, phase):
        self._haupt.PS5ConverterGUI._ampr_pack_fortschritt(self, prozent, phase)

    def _kopieren_mit_fortschritt(self, quelle, ziel, gesamt):
        # Was ``_integration_arbeitskopie`` sonst davor setzt.
        self._copy_total_bytes = max(1, int(gesamt or 0))
        self._copy_done_bytes = 0
        self._copy_total_exact = True
        self._haupt.PS5ConverterGUI._kopieren_mit_fortschritt(
            self, quelle, ziel, gesamt)

    # --- was die Melder benutzen -----------------------------------------
    _KOPIE_TAKT_SEKUNDEN = 0.0
    _KOPIE_GROESSE_TAKT_SEKUNDEN = 0.0
    _PACK_GROESSE_TAKT_SEKUNDEN = 0.0

    @property
    def _KOPIE_BALKEN_SPANNE(self):
        return self._haupt.PS5ConverterGUI._KOPIE_BALKEN_SPANNE

    @property
    def _PACK_BALKEN_SPANNE(self):
        return self._haupt.PS5ConverterGUI._PACK_BALKEN_SPANNE

    def _set_progress(self, value, show_percent=True, size_text=None,
                      percent_value=None):
        self.balkenwerte.append(value)

    def _set_status(self, text):
        self.statuszeilen.append(str(text))

    def _t(self, schluessel, **werte):
        # Mit den Werten, sonst laesst sich nicht pruefen, ob der Platzhalter
        # ueberhaupt gefuellt wurde.
        if not werte:
            return schluessel
        return schluessel + " " + " ".join(
            "%s=%s" % (k, v) for k, v in sorted(werte.items()))

    def _fmt_bytes(self, zahl):
        return "%d B" % int(zahl)


class TeilschrittAbbildungTests(unittest.TestCase):
    """``_teilschritt_melden`` bildet ab statt zu überschreiben."""

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()

    def test_rohwert_landet_im_zugewiesenen_abschnitt(self):
        """0 bis 100 des Teilschritts werden zu 0 bis `spanne` im Ganzen."""
        a = _Aufzeichnung(self.haupt)
        a._teilschritt_melden("kopie", 0.0, 4.0)
        self.assertEqual(a.task_progress, 0.0)
        a._teilschritt_melden("kopie", 50.0, 4.0)
        self.assertAlmostEqual(a.task_progress, 2.0)
        a._teilschritt_melden("kopie", 100.0, 4.0)
        self.assertAlmostEqual(a.task_progress, 4.0)

    def test_basis_ist_der_stand_beim_ersten_aufruf(self):
        """Mitten im Lauf gerufen, rechnet der Melder ab dem Ist-Stand weiter.

        ``_integration_anwenden`` kommt in den mehrstufigen Wegen erst bei über
        90 % vor. Ein Melder, der dort bei 0 anfinge, wäre ein Rücksprung von
        90 Punkten - genau der Fehler, den diese Datei verhindert.
        """
        a = _Aufzeichnung(self.haupt)
        a.task_progress = 90.0
        a._teilschritt_melden("kopie", 0.0, 4.0)
        self.assertEqual(a.task_progress, 90.0)
        a._teilschritt_melden("kopie", 100.0, 4.0)
        self.assertAlmostEqual(a.task_progress, 94.0)

    def test_laeuft_nie_rueckwaerts(self):
        """Auch ein sinkender Rohwert senkt den Balken nicht."""
        a = _Aufzeichnung(self.haupt)
        for anteil in (10.0, 40.0, 90.0, 5.0, 60.0, 0.0, 100.0):
            a._teilschritt_melden("kopie", anteil, 4.0)
        self.assertEqual(a.verlauf, sorted(a.verlauf),
                         "Der Gesamtfortschritt ist gesunken: %r" % (a.verlauf,))

    def test_neue_phase_setzt_nicht_zurueck(self):
        """Das Packwerkzeug fängt je Phase wieder bei 0 an - der Balken nicht.

        Genau hier entstanden die Sprünge von 100 % auf 0 %: ``ampr_pack.py``
        meldet ``[pack 100%] packing`` und gleich darauf ``[pack 0%] writing``.
        """
        a = _Aufzeichnung(self.haupt)
        a._teilschritt_melden("ampr_pack:packing", 100.0, 2.0)
        stand = a.task_progress
        a._teilschritt_melden("ampr_pack:writing", 0.0, 2.0)
        self.assertGreaterEqual(a.task_progress, stand)
        a._teilschritt_melden("ampr_pack:writing", 100.0, 2.0)
        self.assertAlmostEqual(a.task_progress, stand + 2.0)

    def test_unsinnige_werte_bewegen_nichts(self):
        """Ein kaputter Rohwert darf den Balken nicht verstellen."""
        a = _Aufzeichnung(self.haupt)
        a.task_progress = 12.0
        for murks in (None, "viel", float("nan")):
            a._teilschritt_melden("kopie", murks, 4.0)
        self.assertGreaterEqual(a.task_progress, 12.0)
        self.assertLessEqual(a.task_progress, 16.0)

    def test_deckel_bei_99_5(self):
        """Ein Teilschritt darf die Aufgabe nie auf 100 % ziehen."""
        a = _Aufzeichnung(self.haupt)
        a.task_progress = 99.0
        a._teilschritt_melden("kopie", 100.0, 40.0)
        self.assertLessEqual(a.task_progress, 99.5)


class MelderSchreibenNichtAufDenBalkenTests(unittest.TestCase):
    """Die beiden Melder fassen ``progress_var`` nicht an."""

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()

    def test_ampr_pack_meldet_ueber_den_gesamtfortschritt(self):
        a = _Aufzeichnung(self.haupt)
        for prozent, phase in ((0, "packing"), (42, "packing"),
                               (100, "packing"), (0, "writing"), (100, "writing")):
            a._ampr_pack_fortschritt(float(prozent), phase)
        self.assertEqual(
            [], a.balkenwerte,
            "Der Melder hat den Balken angefasst: %r" % (a.balkenwerte,))
        self.assertGreater(a.task_progress, 0.0,
                           "Der Gesamtfortschritt hat sich nicht bewegt.")
        self.assertTrue(
            a._pack_infotext,
            "Das Groessenfeld bekam nichts - waehrend des Packens stuende "
            "rechts vom Balken nichts.")
        self.assertIn("100", a._pack_infotext)

    def test_ampr_pack_nennt_die_phase_in_der_statuszeile(self):
        """Ohne bewegten Statustext hält ``_stillstand_uhr`` das für Stillstand."""
        a = _Aufzeichnung(self.haupt)
        a._ampr_pack_fortschritt(10.0, "packing")
        self.assertTrue(a.statuszeilen,
                        "Die Statuszeile blieb stehen - die Uhr meldet Stillstand.")

    def test_arbeitskopie_meldet_ueber_den_gesamtfortschritt(self):
        """Eine echte Kopie, kein Nachbau - der Melder hängt an os.walk."""
        import tempfile
        a = _Aufzeichnung(self.haupt)
        with tempfile.TemporaryDirectory() as basis:
            quelle = os.path.join(basis, "dump")
            os.makedirs(os.path.join(quelle, "sce_sys"))
            gesamt = 0
            for name in ("eboot.bin", "sce_sys/param.json", "daten.pak"):
                pfad = os.path.join(quelle, name)
                with open(pfad, "wb") as f:
                    f.write(b"x" * 4096)
                gesamt += 4096
            ziel = os.path.join(basis, "kopie")
            a._kopieren_mit_fortschritt(quelle, ziel, gesamt)

            self.assertTrue(os.path.isfile(os.path.join(ziel, "eboot.bin")))
            self.assertTrue(
                os.path.isfile(os.path.join(ziel, "sce_sys", "param.json")),
                "Unterordner gingen verloren.")

        # Der Balken wird nicht mehr selbst gesetzt - das macht der Takt aus
        # den Byte-Zaehlern, und der fuellt damit auch das Groessenfeld.
        self.assertEqual(
            [], a.balkenwerte,
            "Der Melder hat den Balken angefasst: %r" % (a.balkenwerte,))
        self.assertEqual(
            gesamt, a._copy_done_bytes,
            "Am Ende muss der Zaehler auf der vollen Groesse stehen.")
        self.assertTrue(a._copy_total_exact,
                        "Ohne das zeigt das Groessenfeld keine GB-Angabe.")
        self.assertGreater(a._copy_rate_bps, 0.0,
                           "Ohne Rate fehlen MB/s und Restzeit.")
        self.assertTrue(
            any("/" in z for z in a.statuszeilen),
            "Die Statuszeile trug keine laufenden Zahlen: %r" % (a.statuszeilen,))


class SetProgressOhneBalkenTests(unittest.TestCase):
    """``_set_progress(None, ...)`` setzt nur den Text."""

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()

    def _probe(self):
        haupt = self.haupt

        class _Label:
            def __init__(self):
                self.text = "alt"

            def cget(self, _n):
                return self.text

            def config(self, text=None, **_k):
                if text is not None:
                    self.text = text

        class _Var:
            def __init__(self):
                self.wert = 42.0
                self.geschrieben = 0

            def set(self, w):
                self.wert = w
                self.geschrieben += 1

        class _Wurzel:
            @staticmethod
            def after(_ms, fn=None, *a):
                if fn is not None:
                    fn(*a)

        class _Probe:
            pass

        p = _Probe()
        p.progress_var = _Var()
        p.percent_label = _Label()
        p.size_label = _Label()
        p.root = _Wurzel()
        p._schedule_caption_redraw = lambda *_a, **_k: None
        p._redraw_content_captions = lambda *_a, **_k: None
        p._set_progress = haupt.PS5ConverterGUI._set_progress.__get__(p)
        return p

    def test_none_laesst_balken_und_prozentzahl_stehen(self):
        p = self._probe()
        p._set_progress(None, size_text="1 GB / 3 GB")
        self.assertEqual(p.progress_var.wert, 42.0)
        self.assertEqual(p.progress_var.geschrieben, 0)
        self.assertEqual(p.percent_label.text, "alt")
        self.assertEqual(p.size_label.text, "1 GB / 3 GB")

    def test_zahl_setzt_den_balken_weiterhin(self):
        """Die Gegenprobe: Der gewöhnliche Weg darf sich nicht geändert haben."""
        p = self._probe()
        p._set_progress(77.0)
        self.assertEqual(p.progress_var.wert, 77.0)
        self.assertEqual(p.progress_var.geschrieben, 1)




class FehlergrundTests(unittest.TestCase):
    """Die Fehlermeldung nennt Gemessenes, keine Beispiele.

    Bis zum 10.09.2026 stand im Meldungstext selbst "z. B. mkpfs Exit-Code
    oder Disk-Full-Meldung". Beides war geraten - das Programm hatte weder
    den Rückgabewert in der Meldung noch den Platz je nachgesehen. Der
    Anwender las die beiden Beispiele zusammen mit der Protokollzeile
    "[WARNUNG] mkpfs beendet mit Exit-Code 1" als **einen** Befund
    ("Code 1 Disc-Full") und suchte einen vollen Datenträger. Es gab keinen.
    """

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()

    def _probe(self, exitcode=None, ziel="", temp=""):
        haupt = self.haupt

        class _Feld:
            def __init__(self, wert):
                self._wert = wert

            def get(self):
                return self._wert

        class _Probe:
            pass

        p = _Probe()
        if exitcode is not None:
            p._letzter_mkpfs_exitcode = exitcode
        p.dest_path = _Feld(ziel)
        p._get_runtime_temp_dir = lambda: temp
        p._t = lambda s, **w: (s + " " + " ".join(
            "%s=%s" % (k, v) for k, v in sorted(w.items()))).strip()
        p._fmt_bytes = lambda z: "%d B" % int(z)
        p._PLATZ_VERDACHT_BYTES = haupt.PS5ConverterGUI._PLATZ_VERDACHT_BYTES
        p._fehlergrund_ermitteln = haupt.PS5ConverterGUI._fehlergrund_ermitteln.__get__(p)
        return p

    def test_ohne_erkenntnis_bleibt_die_meldung_stumm(self):
        """Was nicht gemessen ist, wird auch nicht behauptet."""
        p = self._probe()
        self.assertEqual(p._fehlergrund_ermitteln(None), "")

    def test_rueckgabewert_wird_genannt(self):
        p = self._probe(exitcode=1)
        text = p._fehlergrund_ermitteln(None)
        self.assertIn("fehlergrund.mkpfs_code", text)
        self.assertIn("code=1", text)

    def test_rueckgabewert_null_ist_kein_grund(self):
        """Ein sauber beendeter Packlauf gehört nicht in die Fehlerliste."""
        p = self._probe(exitcode=0)
        self.assertNotIn("mkpfs_code", p._fehlergrund_ermitteln(None))

    def test_pruefbefund_wird_uebernommen(self):
        p = self._probe()
        text = p._fehlergrund_ermitteln(
            {"ok": False, "detail": "Ausgabepfad existiert nicht."})
        self.assertIn("fehlergrund.pruefung", text)
        self.assertIn("Ausgabepfad existiert nicht.", text)

    def test_platz_nur_wenn_wirklich_knapp(self):
        """Der freie Platz kommt aus disk_usage, nicht aus einer Annahme."""
        import shutil as _sh
        import tempfile
        haupt = self.haupt
        with tempfile.TemporaryDirectory() as ordner:
            p = self._probe(ziel=ordner, temp=ordner)
            echt = _sh.disk_usage
            try:
                _sh.disk_usage = lambda _p: type("U", (), {"free": 100})()
                haupt.shutil.disk_usage = _sh.disk_usage
                text = p._fehlergrund_ermitteln(None)
                self.assertIn("fehlergrund.platz_ziel", text)
                self.assertIn("fehlergrund.platz_temp", text)

                _sh.disk_usage = lambda _p: type("U", (), {"free": 500 * 1024 ** 3})()
                haupt.shutil.disk_usage = _sh.disk_usage
                self.assertEqual(p._fehlergrund_ermitteln(None), "",
                                 "Reichlich Platz wurde als Ursache gemeldet.")
            finally:
                _sh.disk_usage = echt
                haupt.shutil.disk_usage = echt

    def test_alles_zusammen_als_liste(self):
        p = self._probe(exitcode=2)
        text = p._fehlergrund_ermitteln({"detail": "Datei ist leer (0 Bytes)."})
        self.assertEqual(len(text.splitlines()), 2)
        self.assertTrue(all(z.startswith("- ") for z in text.splitlines()))

    def test_knapper_speicher_wird_genannt(self):
        """Abbrueche mit [Errno 22] fielen am 10.-12.09.2026 alle unter 50 MB."""
        p = self._probe()
        p._SPEICHER_VERDACHT_MB = self.haupt.PS5ConverterGUI._SPEICHER_VERDACHT_MB
        p._speicher_tiefpunkt_mb = 12
        self.assertIn("fehlergrund.speicher_knapp", p._fehlergrund_ermitteln(None))

    def test_ausreichender_speicher_ist_kein_grund(self):
        p = self._probe()
        p._SPEICHER_VERDACHT_MB = self.haupt.PS5ConverterGUI._SPEICHER_VERDACHT_MB
        p._speicher_tiefpunkt_mb = 1500
        self.assertEqual(p._fehlergrund_ermitteln(None), "",
                         "Reichlich Speicher wurde als Ursache gemeldet.")

    def test_ohne_messung_wird_nichts_behauptet(self):
        """Ohne psutil gibt es keinen Tiefpunkt - dann auch keinen Hinweis."""
        p = self._probe()
        p._speicher_tiefpunkt_mb = None
        self.assertEqual(p._fehlergrund_ermitteln(None), "")

    def test_die_beobachtung_merkt_sich_den_tiefpunkt(self):
        """Gemessen wird am echten Faden, mit gestellten Speicherwerten."""
        import time

        haupt = self.haupt
        if haupt.psutil is None:
            self.skipTest("psutil fehlt")

        class _Probe:
            pass

        p = _Probe()
        p.is_running = True
        p._SPEICHER_TAKT_S = 0.01
        p._speicher_beobachtung_starten = (
            haupt.PS5ConverterGUI._speicher_beobachtung_starten.__get__(p))
        p._speicher_beobachtung_beenden = (
            haupt.PS5ConverterGUI._speicher_beobachtung_beenden.__get__(p))

        werte = [900, 40, 700]
        aufrufe = []

        class _Stand:
            def __init__(self, mb):
                self.available = mb * 1024 ** 2

        def _gestellt():
            aufrufe.append(1)
            if len(aufrufe) > len(werte):
                raise RuntimeError("Ende der gestellten Werte")
            return _Stand(werte[len(aufrufe) - 1])

        echt = haupt.psutil.virtual_memory
        haupt.psutil.virtual_memory = _gestellt
        try:
            p._speicher_beobachtung_starten()
            frist = time.time() + 5.0
            while len(aufrufe) <= len(werte) and time.time() < frist:
                time.sleep(0.01)
        finally:
            p._speicher_beobachtung_beenden()
            haupt.psutil.virtual_memory = echt
        self.assertEqual(40, p._speicher_tiefpunkt_mb)

    def test_die_messung_haengt_wirklich_am_aufgabenlauf(self):
        """Start im try, Ende im finally, und gestartet vor der Fehlermeldung."""
        import ast

        baum = ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))
        methode = next(k for k in ast.walk(baum)
                       if isinstance(k, ast.FunctionDef)
                       and k.name == "_run_engine_thread")

        def zeilen_von(knoten, attr):
            return [n.lineno for n in ast.walk(knoten)
                    if isinstance(n, ast.Attribute) and n.attr == attr]

        treffer = []
        for knoten in ast.walk(methode):
            if isinstance(knoten, ast.Try) and knoten.finalbody:
                ende = [z for st in knoten.finalbody
                        for z in zeilen_von(st, "_speicher_beobachtung_beenden")]
                start = [z for st in knoten.body
                         for z in zeilen_von(st, "_speicher_beobachtung_starten")]
                if ende and start:
                    treffer.append((start[0], knoten))
        self.assertTrue(treffer, "Start und Ende der Messung haengen nicht im "
                                 "selben try/finally von _run_engine_thread.")
        start_zeile, knoten = treffer[0]
        meldung = zeilen_von(methode, "_fehlergrund_ermitteln")
        self.assertTrue(meldung)
        self.assertLess(start_zeile, min(meldung),
                        "Die Messung startet erst nach der Fehlermeldung.")

    # -- MemoryError traegt keinen Text -----------------------------------
    #
    # Am 20.09.2026 gemessen: Ein Bau nach .ffpfsc starb mit MemoryError in
    # MkPFS (_iter_logical_blocks, "buffer += piece"), frei waren 0,8 GB.
    # str(MemoryError()) ist "" - im Fenster stand "abgebrochen:" und
    # dahinter nichts.

    def _fehlertext_probe(self, tiefpunkt=None):
        haupt = self.haupt

        class _Probe:
            pass

        p = _Probe()
        if tiefpunkt is not None:
            p._speicher_tiefpunkt_mb = tiefpunkt
        p._t = lambda s, **w: (s + " " + " ".join(
            "%s=%s" % (k, v) for k, v in sorted(w.items()))).strip()
        p._fmt_bytes = lambda z: "%d B" % int(z)
        p._fehlertext_der_ausnahme = (
            haupt.PS5ConverterGUI._fehlertext_der_ausnahme.__get__(p))
        return p

    def test_speichermangel_bekommt_einen_eigenen_satz(self):
        p = self._fehlertext_probe(tiefpunkt=None)
        p._speicher_tiefpunkt_mb = None
        text = p._fehlertext_der_ausnahme(MemoryError())
        self.assertIn("fehler.speicher_erschoepft", text)
        self.assertNotEqual(str(MemoryError()), text,
                            "Der leere Text der Ausnahme darf nicht durchschlagen.")

    def test_der_gemessene_tiefpunkt_steht_mit_drin(self):
        p = self._fehlertext_probe(tiefpunkt=820)
        text = p._fehlertext_der_ausnahme(MemoryError())
        self.assertIn("fehler.speicher_erschoepft_tief", text)
        self.assertIn("%d B" % (820 * 1024 ** 2), text)

    def test_ohne_messung_wird_kein_wert_erfunden(self):
        p = self._fehlertext_probe()
        text = p._fehlertext_der_ausnahme(MemoryError())
        self.assertIn("fehler.speicher_erschoepft", text)
        self.assertNotIn("size=", text)

    def test_jede_andere_ausnahme_behaelt_ihren_text(self):
        p = self._fehlertext_probe()
        self.assertEqual(p._fehlertext_der_ausnahme(OSError("Datei fehlt")),
                         "Datei fehlt")

    def test_textlose_ausnahmen_nennen_wenigstens_die_art(self):
        p = self._fehlertext_probe()
        self.assertEqual(p._fehlertext_der_ausnahme(KeyboardInterrupt()),
                         "KeyboardInterrupt")

    def test_der_engine_faden_benutzt_den_helfer_wirklich(self):
        """Eine Reparatur, die nur der Test ruft, hilft niemandem."""
        import ast

        baum = ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))
        methode = next(k for k in ast.walk(baum)
                       if isinstance(k, ast.FunctionDef)
                       and k.name == "_run_engine_thread")
        self.assertTrue(
            [n for n in ast.walk(methode)
             if isinstance(n, ast.Attribute) and n.attr == "_fehlertext_der_ausnahme"],
            "_run_engine_thread meldet den Fehlertext an _fehlertext_der_ausnahme vorbei.")


class QuellgroesseMeldetUndBrichtAbTests(unittest.TestCase):
    """Das Vermessen der Quelle darf nicht stumm und nicht endlos sein.

    Am 12.09.2026 an Aufgabe 8 gemessen: ``_get_path_size`` lief mit
    ``os.walk`` **37 Minuten** über einen 51-GB-Dump mit 17.000 Dateien auf
    einer USB-exFAT-Platte. Sieben der acht Aufrufer riefen es blank auf -
    ohne ``progress_cb`` und ohne ``cancel_check``. Zwei Folgen:

    * Die Anzeige stand still, und die eingebaute Aufhänger-Erkennung schrieb
      nach zwei Minuten einen Stapelabzug ins Protokoll - mitten in einem
      völlig normalen Lauf. Genau dieses Bild ließ den Anwender glauben, die
      Aufgaben seien seit v1.9.7 kaputt.
    * **Abbrechen ging nicht.** Wer es sich anders überlegte, saß die
      37 Minuten ab.

    Gemessen wird an einem echten Ordner, nicht an einer Nachbildung: Eine
    gestellte ``os.walk`` hätte weder die Laufzeit noch das Stillstehen
    gezeigt.
    """

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()

    def _app(self):
        import tkinter as tk
        wurzel = tk._default_root or tk.Tk()
        wurzel.withdraw()
        return self.haupt.PS5ConverterGUI(wurzel)

    def test_das_vermessen_meldet_sich_unterwegs(self):
        app = self._app()
        gemeldet = []
        echt = app._set_progress
        app._set_progress = lambda *a, **k: (
            gemeldet.append(k.get("size_text", "")), echt(*a, **k))[1]
        status = []
        echt_status = app._set_status
        app._set_status = lambda text: (status.append(text), echt_status(text))[1]
        app.is_running = True
        app._quellgroesse_mit_meldung(str(HAUPTDATEI.parent))
        mit_text = [g for g in gemeldet if g]
        self.assertTrue(mit_text,
                        "Das Vermessen lief stumm - die Aufhaenger-Erkennung "
                        "haelt das fuer einen Absturz.")
        # Das Groessenfeld allein reicht nicht: der Anzeige-Takt setzt es alle
        # 100 ms neu, und _stillstand_uhr beobachtet nur Balken und
        # Statuszeile. Bis v1.9.24 schrieb sie trotz der Meldung nach 120 s
        # einen Stapelabzug als ERROR ins Protokoll.
        self.assertTrue([s for s in status if s],
                        "Das Vermessen meldet sich nicht in der Statuszeile - "
                        "die Stillstand-Uhr sieht nur die.")

    def test_der_abbruch_greift_mitten_im_vermessen(self):
        import threading
        import time

        app = self._app()
        app.is_running = True
        ganz = app._quellgroesse_mit_meldung(str(HAUPTDATEI.parent))

        app.is_running = True

        def _stoppen():
            time.sleep(0.3)
            app.is_running = False

        threading.Thread(target=_stoppen, daemon=True).start()
        teil = app._quellgroesse_mit_meldung(str(HAUPTDATEI.parent))
        self.assertLess(teil, ganz,
                        "Der Abbruch wirkte nicht - der Lauf zaehlte zu Ende.")

    def test_kein_aufrufer_vermisst_mehr_blank(self):
        """Der Wächter über die Stellen selbst.

        Sieben Aufrufer waren betroffen; ein achter (Aufgabe 1) hatte
        schon immer einen eigenen, aufwendigeren Melder. Käme ein neuer
        blanker Aufruf dazu, fiele das sonst erst dem Anwender auf.
        """
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        self.assertNotIn(
            "task_total_source_bytes = self._get_path_size(src)", quelle,
            "Hier vermisst wieder jemand ohne Meldung und ohne Abbruch.")
        self.assertIn("def _quellgroesse_mit_meldung", quelle)
        # Die Arbeitskopie war die letzte stumme Stelle (15.09.2026 gemeldet):
        # Sie vermass den Dump **vor** der Rueckfrage und vor der ersten
        # Protokollzeile - fuer den Anwender sah das nach einem Haenger aus.
        self.assertNotIn(
            "groesse = self._get_path_size(quelle)", quelle,
            "Die Arbeitskopie vermisst wieder blank - ohne Anzeige und ohne "
            "Abbruch sieht das fuer den Anwender nach einem Haenger aus.")

    # -- Der Text darf nicht blinken --------------------------------------
    #
    # Vom Anwender gemeldet (20.09.2026): "beim Quelle vermessen wird die
    # Fortschrittsanzeige nicht korrekt angezeigt. Es blinkt zwischendurch
    # der Text, der rechts daneben erscheint."
    #
    # Am echten Widget nachgemessen: Der Melder schrieb den Text einmal je
    # Sekunde, und der Anzeige-Takt setzte ihn 100 ms spaeter wieder auf ""
    # (in dieser Phase greift keiner seiner Zweige). Sichtbar war er
    # **5 % der Zeit**; mit dem Merker 98 %.

    def _vermessungslage(self, app) -> None:
        """Der Zustand, den ein Lauf waehrend des Vermessens wirklich hat."""
        app.is_running = True
        app.monitor_active = False   # kein Selbst-Neustart des Takts im Test
        app.task_total_source_bytes = 0
        app.task_uncompressed_str = ""
        app.task_stored_str = ""
        app._pack_infotext = ""
        app._copy_total_bytes = 0
        app._monitor_total_bytes = 0
        app._monitor_done_bytes = 0

    def test_der_takt_loescht_den_vermessungstext_nicht(self):
        app = self._app()
        self._vermessungslage(app)
        text = "Quelle wird vermessen: 1234 Dateien, 12.3 GB"
        app._mess_infotext = text
        app._set_progress(None, size_text=text)
        app.root.update()
        self.assertEqual(str(app.size_label.cget("text")), text)

        # Und jetzt der Takt, der ihn bisher weggewischt hat.
        app._update_progress_gui()
        app.root.update()
        self.assertEqual(
            str(app.size_label.cget("text")), text,
            "Der Anzeige-Takt hat den Vermessungstext geloescht - er blinkt "
            "dann einmal je Sekunde kurz auf.")

    def test_ohne_merker_bleibt_das_feld_leer(self):
        """Die Gegenrichtung: Ohne Merker gehoert das Feld dem Takt."""
        app = self._app()
        self._vermessungslage(app)
        app._mess_infotext = ""
        app._set_progress(None, size_text="steht noch da")
        app.root.update()
        app._update_progress_gui()
        app.root.update()
        self.assertEqual(str(app.size_label.cget("text")), "")

    def test_der_merker_wird_danach_geraeumt(self):
        """Sonst steht "wird vermessen" noch beim Kopieren und Packen da."""
        app = self._app()
        self._vermessungslage(app)
        app._mess_infotext = "Rest vom vorigen Lauf"
        app._quellgroesse_mit_meldung(str(HAUPTDATEI.parent))
        self.assertEqual(getattr(app, "_mess_infotext", ""), "")

    def test_der_melder_setzt_den_merker_wirklich(self):
        """Eine Reparatur, die nur der Test setzt, hilft niemandem."""
        import ast

        baum = ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))
        methode = next(k for k in ast.walk(baum)
                       if isinstance(k, ast.FunctionDef)
                       and k.name == "_quellgroesse_mit_meldung")
        setzt = [z for z in ast.walk(methode)
                 if isinstance(z, ast.Assign)
                 and any(isinstance(t, ast.Attribute)
                         and t.attr == "_mess_infotext" for t in z.targets)]
        self.assertGreaterEqual(
            len(setzt), 2,
            "_quellgroesse_mit_meldung muss den Merker setzen UND wieder "
            "raeumen.")
        # Und der Takt muss ihn lesen.
        takt = next(k for k in ast.walk(baum)
                    if isinstance(k, ast.FunctionDef)
                    and k.name == "_update_progress_gui")
        self.assertTrue(
            [n for n in ast.walk(takt)
             if isinstance(n, ast.Constant) and n.value == "_mess_infotext"],
            "_update_progress_gui fragt den Merker nicht ab.")


class VerschiebenUeberLaufwerkeTests(unittest.TestCase):
    """Das Verschieben ins Ziel darf nicht stumm sein.

    Vom Anwender gemeldet (20.09.2026): "wenn die Arbeitskopie nicht in den
    Temp Ordner gelegt wird, sieht man leider auch keinen Fortschritt. Es
    blinkt zwar nicht, aber man sieht auch nicht, dass kopiert wird."

    Die Ursache: ``shutil.move`` benennt nur um, **solange Quelle und Ziel
    auf demselben Datenträger liegen**. Liegen sie auf verschiedenen, kopiert
    es jede Datei Byte für Byte und löscht sie danach - bei einem Spielordner
    zig Gigabyte. ``_move_tree_into`` hatte dafür weder eine Meldung noch
    einen Zähler: Der Balken stand bei 95 %, das Größenfeld war leer.
    """

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()

    def _probe(self):
        haupt = self.haupt

        class _Probe:
            pass

        p = _Probe()
        p.protokoll = []
        p.statuszeilen = []
        p._append_to_log = p.protokoll.append
        p._set_status = p.statuszeilen.append
        p._t = lambda s, **w: s
        p._fmt_bytes = lambda n: "%d B" % int(n)
        # Die beiden Methoden an die Attrappe binden; die statischen werden
        # unverändert übernommen - ein ``__get__`` schöbe ihnen die Attrappe
        # als erstes Argument unter.
        for name in ("_move_tree_into", "_verschiebemelder"):
            setattr(p, name, getattr(haupt.PS5ConverterGUI, name).__get__(p))
        for name in ("_gleicher_datentraeger", "_baumgroesse_still"):
            setattr(p, name, getattr(haupt.PS5ConverterGUI, name))
        return p

    def _baum(self, wurzel, plan):
        for rel, groesse in plan:
            pfad = os.path.join(wurzel, *rel.split("/"))
            os.makedirs(os.path.dirname(pfad), exist_ok=True)
            with open(pfad, "wb") as fh:
                fh.write(b"x" * groesse)

    def test_jede_verschobene_datei_wird_gemeldet(self):
        import tempfile

        plan = [("eboot.bin", 4096), ("sce_sys/param.json", 512),
                ("daten/tief/karte0.dat", 8192), ("daten/karte1.dat", 1024)]
        with tempfile.TemporaryDirectory(prefix="verschieb_") as basis:
            quelle = os.path.join(basis, "von")
            ziel = os.path.join(basis, "nach")
            self._baum(quelle, plan)
            p = self._probe()
            gemeldet = []
            fehler = p._move_tree_into(quelle, ziel, melden=gemeldet.append)
            self.assertEqual(fehler, [])
            self.assertEqual(sum(gemeldet), sum(g for _r, g in plan),
                             "Die gemeldeten Bytes decken sich nicht mit dem, "
                             "was wirklich verschoben wurde.")
            for rel, groesse in plan:
                pfad = os.path.join(ziel, *rel.split("/"))
                self.assertTrue(os.path.isfile(pfad), rel)
                self.assertEqual(os.path.getsize(pfad), groesse, rel)

    def test_ohne_melder_verschiebt_es_wie_bisher(self):
        """Der Zusatz darf den Regelfall nicht verändern."""
        import tempfile

        with tempfile.TemporaryDirectory(prefix="verschieb_") as basis:
            quelle = os.path.join(basis, "von")
            ziel = os.path.join(basis, "nach")
            self._baum(quelle, [("a/b.bin", 32)])
            p = self._probe()
            self.assertEqual(p._move_tree_into(quelle, ziel), [])
            self.assertTrue(os.path.isfile(os.path.join(ziel, "a", "b.bin")))

    def test_gleiches_laufwerk_braucht_keine_anzeige(self):
        import tempfile

        with tempfile.TemporaryDirectory(prefix="verschieb_") as basis:
            p = self._probe()
            self.assertTrue(p._gleicher_datentraeger(basis, basis))
            self.assertIsNone(
                p._verschiebemelder(os.path.join(basis, "von"),
                                    os.path.join(basis, "nach")),
                "Ein Umbenennen auf demselben Datentraeger braucht keine "
                "Anzeige - und soll das Groessenfeld nicht kurz umschreiben.")

    @unittest.skipUnless(os.name == "nt", "Laufwerksbuchstaben nur unter Windows")
    def test_verschiedene_laufwerke_werden_erkannt(self):
        p = self._probe()
        self.assertFalse(p._gleicher_datentraeger(r"C:\a\b", r"E:\c\d"))
        self.assertTrue(p._gleicher_datentraeger(r"C:\a\b", r"c:\c\d"),
                        "Gross- und Kleinschreibung des Buchstabens zaehlt nicht.")

    def test_der_melder_fuellt_die_zaehler_der_anzeige(self):
        """Über dieselben Zähler wie die Arbeitskopie, kein zweites Getriebe."""
        import tempfile

        with tempfile.TemporaryDirectory(prefix="verschieb_") as basis:
            quelle = os.path.join(basis, "von")
            self._baum(quelle, [("gross.bin", 4096)])
            p = self._probe()
            p._dump_inhalt_gemessen = (os.path.normcase(os.path.abspath(quelle)),
                                       1, 4096)
            p._gleicher_datentraeger = lambda _a, _b: False   # den Fall erzwingen
            melden = p._verschiebemelder(quelle, os.path.join(basis, "nach"))
            self.assertIsNotNone(melden)
            self.assertEqual(p._copy_total_bytes, 4096)
            self.assertTrue(p._copy_total_exact)
            # Der erste Aufruf meldet immer: Der Takt zaehlt ab 0.0, und
            # jede monotone Zeit liegt mehr als eine Sekunde darueber.
            melden(4096)
            self.assertEqual(p._copy_done_bytes, 4096)
            self.assertTrue([z for z in p.statuszeilen if z],
                            "Die Statuszeile bleibt stumm - die Stillstand-Uhr "
                            "haelt das fuer einen Aufhaenger.")
            self.assertIn("log.verschieben_ueber_laufwerke", p.protokoll)

    def test_die_aufrufstelle_reicht_den_melder_wirklich_durch(self):
        """Eine Reparatur, die nur der Test ruft, hilft niemandem."""
        import ast

        baum = ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))
        rufe = [k for k in ast.walk(baum)
                if isinstance(k, ast.Call)
                and isinstance(k.func, ast.Attribute)
                and k.func.attr == "_move_tree_into"]
        self.assertTrue(rufe)
        mit_melder = [k for k in rufe
                      if any(s.arg == "melden" for s in k.keywords)]
        self.assertTrue(
            mit_melder,
            "Keine Aufrufstelle reicht einen Melder durch - dann verschiebt "
            "es wieder stumm ueber Laufwerksgrenzen.")

    def test_die_groesse_kommt_aus_der_vorhandenen_messung(self):
        """Ein zweiter Durchlauf über den Baum wäre verschwendet."""
        import ast

        baum = ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))
        methode = next(k for k in ast.walk(baum)
                       if isinstance(k, ast.FunctionDef)
                       and k.name == "_pruefe_dump_vollstaendig")
        self.assertTrue(
            [z for z in ast.walk(methode)
             if isinstance(z, ast.Assign)
             and any(isinstance(t, ast.Attribute)
                     and t.attr == "_dump_inhalt_gemessen" for t in z.targets)],
            "_pruefe_dump_vollstaendig merkt das Ergebnis seines Durchlaufs "
            "nicht - dann muesste das Verschieben neu vermessen.")

    def test_auch_das_herausholen_aus_dem_container_zaehlt_mit(self):
        """Die zweite stille Stelle: Dateien lagen direkt im Container.

        Sie schrieb nur die Statuszeile; Balken und Größenfeld blieben leer,
        weil in dieser Phase keiner der Zweige des Anzeige-Takts greift.
        """
        import ast

        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        anfang = quelle.index("def _melde_kopie")
        ende = quelle.index("copy_function=_kopiere_und_melde", anfang)
        block = quelle[anfang:ende]
        for merkmal in ("_copy_done_bytes", "_copy_rate_bps"):
            self.assertIn(
                merkmal, block,
                "Das Herausholen aus dem Container meldet wieder nur in die "
                "Statuszeile - Balken und Groessenfeld bleiben leer.")
        # Und die Gesamtgroesse kommt auch hier aus der vorhandenen Messung.
        vorspann = quelle[quelle.index("log.auto.0159"):anfang]
        self.assertIn("_dump_inhalt_gemessen", vorspann,
                      "Ohne Gesamtgroesse gaebe es keinen ehrlichen Balken - "
                      "sie steht aus der Vollstaendigkeitspruefung bereit.")

    def test_die_zaehler_werden_nach_beiden_stellen_geraeumt(self):
        """Sonst zeigt das Größenfeld die Kopierzahlen in der nächsten Phase.

        Dieselbe Falle, die ``_integration_arbeitskopie`` mit ihrem
        ``finally`` längst vermeidet.
        """
        import ast

        baum = ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))
        setzt_null = [
            z.lineno for z in ast.walk(baum)
            if isinstance(z, ast.Assign)
            and any(isinstance(t, ast.Attribute)
                    and t.attr == "_copy_total_bytes" for t in z.targets)
            and isinstance(z.value, ast.Constant) and z.value.value == 0]
        self.assertGreaterEqual(
            len(setzt_null), 3,
            "Mindestens drei Stellen muessen die Kopierzaehler wieder "
            "raeumen: Arbeitskopie, Container-Herausholen, Verschieben.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
