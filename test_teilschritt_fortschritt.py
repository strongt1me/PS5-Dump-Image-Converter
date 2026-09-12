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

if __name__ == "__main__":
    unittest.main(verbosity=2)
