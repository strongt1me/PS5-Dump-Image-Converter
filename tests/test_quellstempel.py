# -*- coding: utf-8 -*-
"""Quelle auf Aenderung pruefen, bevor ein Ergebnis sie ersetzt (nach Dump Forge: ``SourceStamp``, Nutzerwahl 13.11.2026).

Ein Selbst-Ziel (``.exfat`` als ``.exfat``, ``.ffpfsc`` als ``.ffpfsc``) wird neben der Quelle gebaut und danach mit ``os.replace``
an deren Stelle gesetzt. Hat sich die Quelle in den Stunden dazwischen veraendert (ueberschrieben, ausgetauscht, erweitert), passt
das Ergebnis nicht mehr zu ihr: Es wird nicht uebernommen und bleibt als ``.neu`` liegen.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("quellstempel")

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


class QuellstempelTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.quelle = Path(self._tmp.name) / "Spiel.exfat"
        self.quelle.write_bytes(b"alt" * 1000)
        self.app = GUI.__new__(GUI)
        self.protokoll: list[str] = []
        self.app._append_to_log = self.protokoll.append
        self.app._t = lambda schluessel, **w: schluessel + " " + " ".join("%s=%s" % kv for kv in sorted(w.items()))
        self.app._lauf_quelle = str(self.quelle)

    def _bauen(self) -> str:
        """Wie ein Weg: Bauziel neben der Quelle holen, dort das Ergebnis schreiben."""
        bau = self.app._bauziel_neben_quelle(str(self.quelle))
        self.assertEqual(str(self.quelle) + ".neu", bau)
        Path(bau).write_bytes(b"neu" * 500)
        return bau

    def test_eine_unveraenderte_quelle_wird_ersetzt(self):
        bau = self._bauen()
        ergebnis = self.app._bauziel_uebernehmen(bau, str(self.quelle))
        self.assertEqual(str(self.quelle), ergebnis)
        self.assertEqual(b"neu" * 500, self.quelle.read_bytes())
        self.assertFalse(os.path.exists(bau))
        self.assertFalse(any("quelle_geaendert" in z for z in self.protokoll))

    def test_eine_erweiterte_quelle_wird_nicht_ersetzt(self):
        bau = self._bauen()
        with self.quelle.open("ab") as fh:
            fh.write(b"x")
        ergebnis = self.app._bauziel_uebernehmen(bau, str(self.quelle))
        self.assertEqual(bau, ergebnis, "kein Erfolg: der Aufrufer erkennt den Fehlschlag am Pfad")
        self.assertEqual(b"alt" * 1000 + b"x", self.quelle.read_bytes(), "die Quelle bleibt, wie der Anwender sie hinterliess")
        self.assertTrue(os.path.exists(bau), "das fertige Ergebnis bleibt liegen")
        self.assertTrue(any("log.selbstziel_quelle_geaendert" in z for z in self.protokoll), self.protokoll)

    def test_eine_nur_neu_datierte_quelle_wird_nicht_ersetzt(self):
        bau = self._bauen()
        st = os.stat(self.quelle)
        os.utime(self.quelle, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
        self.assertEqual(bau, self.app._bauziel_uebernehmen(bau, str(self.quelle)))

    def test_eine_ausgetauschte_datei_gleicher_groesse_und_zeit_wird_erkannt(self):
        bau = self._bauen()
        st = os.stat(self.quelle)
        if not st.st_ino:
            self.skipTest("das Dateisystem meldet keine Datei-ID")
        ersatz = Path(self._tmp.name) / "ersatz.bin"
        ersatz.write_bytes(b"neu" * 1000)                           # gleiche Groesse, anderer Inhalt
        os.utime(ersatz, ns=(st.st_atime_ns, st.st_mtime_ns))        # gleiche Zeit
        os.replace(ersatz, self.quelle)                              # eine andere Datei an dieser Stelle
        self.assertEqual(bau, self.app._bauziel_uebernehmen(bau, str(self.quelle)),
                         "die Datei-ID unterscheidet, was Groesse und Zeit nicht sagen")

    def test_ohne_gemerkten_stempel_wird_wie_frueher_ersetzt(self):
        bau = str(self.quelle) + ".neu"
        Path(bau).write_bytes(b"neu" * 500)
        self.assertEqual(str(self.quelle), self.app._bauziel_uebernehmen(bau, str(self.quelle)))

    def test_der_stempel_gilt_nur_fuer_einen_lauf(self):
        bau = self._bauen()
        with self.quelle.open("ab") as fh:
            fh.write(b"x")
        self.assertEqual(bau, self.app._bauziel_uebernehmen(bau, str(self.quelle)))
        # Naechster Lauf mit demselben Pfad: neuer Stempel, die jetzt gueltige Quelle wird normal ersetzt.
        bau2 = self._bauen()
        self.assertEqual(str(self.quelle), self.app._bauziel_uebernehmen(bau2, str(self.quelle)))

    def test_ein_alter_stempel_stoert_einen_spaeteren_weg_ohne_neuen_bau_nicht(self):
        bau = self._bauen()
        self.assertEqual(str(self.quelle), self.app._bauziel_uebernehmen(bau, str(self.quelle)))
        # Die Quelle ist jetzt das Ergebnis; ein weiterer Aufruf ohne neuen Bau darf nicht an einem Altstempel scheitern.
        bau2 = str(self.quelle) + ".neu"
        Path(bau2).write_bytes(b"z" * 10)
        self.assertEqual(str(self.quelle), self.app._bauziel_uebernehmen(bau2, str(self.quelle)))

    def test_ein_ordner_bekommt_keinen_stempel(self):
        ordner = Path(self._tmp.name) / "Dump"
        ordner.mkdir()
        self.assertIsNone(GUI._quellstempel(str(ordner)))
        self.assertIsNone(GUI._quellstempel(str(Path(self._tmp.name) / "gibt_es_nicht")))
        self.assertIsNotNone(GUI._quellstempel(str(self.quelle)))

    def test_der_stempel_unterscheidet_groesse_zeit_und_datei(self):
        a = GUI._quellstempel(str(self.quelle))
        self.assertEqual(4, len(a))
        self.assertEqual(3000, a[0])
        self.assertEqual(a, GUI._quellstempel(str(self.quelle)), "wiederholbar")

    def test_der_text_steht_in_allen_sprachen(self):
        from ps5_validator.utils.i18n import STRINGS, SUPPORTED_LANGUAGES
        for sprache in SUPPORTED_LANGUAGES:
            text = STRINGS["log.selbstziel_quelle_geaendert"][sprache]
            self.assertIn("{quelle}", text, sprache)
            self.assertIn("{neu}", text, sprache)


if __name__ == "__main__":
    unittest.main()
