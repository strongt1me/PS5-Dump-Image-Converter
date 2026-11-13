# -*- coding: utf-8 -*-
"""Der Bau des ampr_emu.index braucht pro Datei kein ``Path.resolve`` mehr und meldet sich beim Zaehlen.

Anlass (12.11.2026): Beim Bau eines exFAT aus einem Spiel mit 84.219 Dateien meldete die Ueberwachung "Anzeige steht seit
120 s still"; der Faden stand in ``_build_ampr_index_local`` bei ``Path.resolve`` (gemessen 140 us je Datei, ``stat`` 7 us).
Die Auswahl der Dateien darf sich dadurch nicht aendern - das prueft ``test_ampr_assets`` byte genau gegen das Skript des
Entwicklers; hier steht, was das Tempo und die Anzeige angeht.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("ampr_index_tempo")

import importlib.util                                        # noqa: E402


def _lade():
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", ROOT / "PS5ImageConverter_Pro_FINAL_revised.py")
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


GUI = _lade().PS5ConverterGUI


class IndexTempoTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.basis = Path(self._tmp.name)
        self.spiel = self.basis / "spiel"
        for i in range(600):
            datei = self.spiel / ("ordner%02d" % (i % 12)) / ("datei%04d.bin" % i)
            datei.parent.mkdir(parents=True, exist_ok=True)
            datei.write_bytes(b"x" * (i % 7))
        (self.spiel / "eboot.bin").write_bytes(b"ELF")
        self.index = self.basis / "ampr_emu.index"

    def _bauen(self, app) -> tuple[int, int]:
        return app._build_ampr_index_local(self.spiel, self.index)

    def test_je_datei_wird_kein_resolve_aufgerufen(self):
        app = GUI.__new__(GUI)
        echt = Path.resolve
        aufrufe = []

        def zaehlen(selbst, *a, **k):
            aufrufe.append(str(selbst))
            return echt(selbst, *a, **k)

        with mock.patch.object(Path, "resolve", zaehlen):
            anzahl, _doppelt = self._bauen(app)
        self.assertEqual(601, anzahl)
        self.assertLessEqual(len(aufrufe), 6, "nur die Wurzel und die Ausgabe, nicht jede Datei: %d Aufrufe" % len(aufrufe))

    def test_die_indexdatei_selbst_und_ihre_tmp_kommen_nicht_hinein(self):
        app = GUI.__new__(GUI)
        self._bauen(app)
        # Jetzt liegen Index und (angelegt) eine .tmp im Spielordner - als Ausgabe im Spiel selbst.
        im_spiel = self.spiel / "ampr_emu.index"
        (self.spiel / "ampr_emu.index.tmp").write_bytes(b"alt")
        anzahl, _d = app._build_ampr_index_local(self.spiel, im_spiel)
        self.assertEqual(601, anzahl, "Ausgabe und .tmp zaehlen nicht mit")
        anzahl2, _d = app._build_ampr_index_local(self.spiel, im_spiel)
        self.assertEqual(601, anzahl2, "auch beim zweiten Bau mit vorhandener Indexdatei dasselbe")

    def test_ein_verweis_auf_die_indexdatei_wird_weiter_erkannt(self):
        app = GUI.__new__(GUI)
        ziel = self.spiel / "ampr_emu.index"
        self._bauen(app)
        app._build_ampr_index_local(self.spiel, ziel)
        try:
            os.symlink(ziel, self.spiel / "verweis.bin")
        except (OSError, NotImplementedError):
            self.skipTest("Verweise nicht anlegbar (Rechte)")
        anzahl, _d = app._build_ampr_index_local(self.spiel, ziel)
        self.assertEqual(601, anzahl, "ein Verweis auf die Indexdatei ist nicht Teil des Spiels")

    def test_der_verweiszweig_ohne_rechte_zum_anlegen_von_verweisen(self):
        """Wie oben, aber ohne echten Verweis: ``lstat`` meldet einen, ``resolve`` fuehrt auf die Indexdatei bzw. woandershin."""
        import stat as _stat
        app = GUI.__new__(GUI)
        ziel = self.spiel / "ampr_emu.index"
        self._bauen(app)
        app._build_ampr_index_local(self.spiel, ziel)
        for name in ("auf_den_index.bin", "woandershin.bin"):
            (self.spiel / name).write_bytes(b"abc")
        echt_lstat, echt_resolve = Path.lstat, Path.resolve

        def lstat(selbst, *a, **k):
            if selbst.name in ("auf_den_index.bin", "woandershin.bin"):
                echt = echt_lstat(selbst, *a, **k)
                return os.stat_result((_stat.S_IFLNK | 0o777,) + tuple(echt)[1:])
            return echt_lstat(selbst, *a, **k)

        def resolve(selbst, *a, **k):
            if selbst.name == "auf_den_index.bin":
                return echt_resolve(ziel)
            return echt_resolve(selbst, *a, **k)

        with mock.patch.object(Path, "lstat", lstat), mock.patch.object(Path, "resolve", resolve):
            anzahl, _d = app._build_ampr_index_local(self.spiel, ziel)
        # 601 Dateien des Spiels + "woandershin.bin" (Verweis auf etwas anderes, bleibt) - ohne "auf_den_index.bin".
        self.assertEqual(602, anzahl)

    def test_ein_kaputter_verweis_bricht_den_bau_nicht(self):
        app = GUI.__new__(GUI)
        try:
            os.symlink(self.basis / "gibt_es_nicht", self.spiel / "kaputt.bin")
        except (OSError, NotImplementedError):
            self.skipTest("Verweise nicht anlegbar (Rechte)")
        anzahl, _d = self._bauen(app)
        self.assertEqual(601, anzahl)

    def test_beim_zaehlen_kommt_hoechstens_je_sekunde_ein_lebenszeichen(self):
        app = GUI.__new__(GUI)
        meldungen: list[str] = []
        app._set_status = meldungen.append
        app._t = lambda schluessel, **w: "%s %s" % (schluessel, w.get("count"))
        takt = iter(x * 1.5 for x in range(100000))                     # jeder Aufruf: 1,5 s weiter
        with mock.patch("time.monotonic", lambda: next(takt)):
            self._bauen(app)
        # Geprueft wird nur alle 256 Dateien: bei 601 Dateien an der 256. und der 512.
        self.assertEqual(2, len(meldungen), meldungen)
        self.assertTrue(all(m.startswith("ampr.index_zaehlt ") for m in meldungen), meldungen)
        zahlen = [int(m.split()[-1]) for m in meldungen]
        self.assertEqual(sorted(zahlen), zahlen, "die Zahl waechst")
        self.assertTrue(all(z % 256 == 0 for z in zahlen))

    def test_ohne_zeitverlauf_kommt_keine_meldungsflut(self):
        app = GUI.__new__(GUI)
        meldungen: list[str] = []
        app._set_status = meldungen.append
        app._t = lambda schluessel, **w: schluessel
        with mock.patch("time.monotonic", lambda: 1000.0):
            self._bauen(app)
        self.assertEqual([], meldungen, "ohne eine verstrichene Sekunde keine Meldung")

    def test_eine_halb_gebaute_instanz_ohne_anzeige_baut_weiter(self):
        app = GUI.__new__(GUI)                           # kein _set_status, kein _t (wie in vielen Pruefstaenden)
        self.assertEqual(601, self._bauen(app)[0])

    def test_ein_fehler_in_der_anzeige_bricht_den_bau_nicht(self):
        app = GUI.__new__(GUI)
        app._t = lambda schluessel, **w: schluessel
        app._set_status = mock.Mock(side_effect=RuntimeError("Anzeige weg"))
        takt = iter(x * 2.0 for x in range(100000))
        with mock.patch("time.monotonic", lambda: next(takt)):
            self.assertEqual(601, self._bauen(app)[0])
        self.assertTrue(app._set_status.called)

    def test_der_text_steht_in_allen_sprachen(self):
        from ps5_validator.utils.i18n import STRINGS, SUPPORTED_LANGUAGES
        for sprache in SUPPORTED_LANGUAGES:
            self.assertIn("{count}", STRINGS["ampr.index_zaehlt"][sprache], sprache)


if __name__ == "__main__":
    unittest.main()
