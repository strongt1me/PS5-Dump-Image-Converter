# -*- coding: utf-8 -*-
"""Neuversuch eines Packlaufs bei erschoepftem Arbeitsspeicher (seit v1.9.70).

``_execute_mkpfs`` startet den Lauf mit halber Kernzahl neu, wenn die Engine ``MemoryError`` ausgab. Die Huelle
wird hier mit einem Ersatz fuer den Einzellauf geprueft - ob ein echter MkPFS-Lauf bei knappem Speicher so endet,
ist damit nicht belegt (am 20.09.2026 endete einer in ``_iter_logical_blocks`` mit ``MemoryError``).
"""
from __future__ import annotations

import queue
import sys
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import PS5ImageConverter_Pro_FINAL_revised as haupt   # noqa: E402
from ps5_validator.utils.i18n import STRINGS          # noqa: E402

PACK = ["pack", "folder", "--compress", "--cpu-count", "8", "--compression-level", "9", "QUELLE", "ZIEL.tmpbau"]


class Huelle:
    """Gerade genug Anwendung fuer ``_execute_mkpfs``: Einzellauf und Protokoll sind Ersatz."""

    _execute_mkpfs = haupt.PS5ConverterGUI._execute_mkpfs
    _kerne_im_aufruf = staticmethod(haupt.PS5ConverterGUI._kerne_im_aufruf)
    _aufruf_mit_kernen = staticmethod(haupt.PS5ConverterGUI._aufruf_mit_kernen)
    _SPEICHER_NEUVERSUCHE = haupt.PS5ConverterGUI._SPEICHER_NEUVERSUCHE
    _letzter_mkpfs_speicher = False

    def __init__(self, ergebnisse) -> None:
        self.is_running = True
        self.ergebnisse = list(ergebnisse)      # je Lauf: (ok, speicher)
        self.aufrufe: list[list[str]] = []
        self.log: list[str] = []
        self.aufgeraeumt: list[str] = []
        self.aufraeumen_klappt = True

    def _execute_mkpfs_einmal(self, args, **_kw) -> bool:
        self.aufrufe.append(list(args))
        ok, speicher = self.ergebnisse.pop(0)
        self._letzter_mkpfs_speicher = speicher
        return ok

    def _append_to_log(self, text: str) -> None:
        self.log.append(text)

    def _t(self, schluessel: str, **kw) -> str:
        return schluessel + repr(sorted(kw.items()))

    def _cleanup_stale_mkpfs_output(self, pfad: str) -> bool:
        self.aufgeraeumt.append(pfad)
        return self.aufraeumen_klappt


def lauf(ergebnisse, args=PACK):
    huelle = Huelle(ergebnisse)
    with mock.patch.object(haupt.time, "sleep"):
        ok = huelle._execute_mkpfs(list(args))
    return huelle, ok


def kerne(aufruf) -> int:
    return int(aufruf[aufruf.index("--cpu-count") + 1])


class HuelleTests(unittest.TestCase):

    def test_ohne_fehler_ein_einziger_lauf(self) -> None:
        h, ok = lauf([(True, False)])
        self.assertTrue(ok)
        self.assertEqual(1, len(h.aufrufe))
        self.assertEqual([], h.log)

    def test_speichermangel_halbiert_die_kerne_bis_es_klappt(self) -> None:
        h, ok = lauf([(False, True), (False, True), (True, False)])
        self.assertTrue(ok)
        self.assertEqual([8, 4, 2], [kerne(a) for a in h.aufrufe])
        self.assertEqual(["ZIEL.tmpbau"] * 2, h.aufgeraeumt)
        self.assertEqual(2, len(h.log))

    def test_andere_fehler_werden_nicht_wiederholt(self) -> None:
        h, ok = lauf([(False, False)])
        self.assertFalse(ok)
        self.assertEqual(1, len(h.aufrufe))

    def test_nach_drei_neuversuchen_ist_schluss(self) -> None:
        h, ok = lauf([(False, True)] * 4, PACK[:3] + ["--cpu-count", "16"] + PACK[5:])
        self.assertFalse(ok)
        self.assertEqual([16, 8, 4, 2], [kerne(a) for a in h.aufrufe])

    def test_mit_einem_kern_gibt_es_nichts_zu_halbieren(self) -> None:
        args = PACK[:3] + ["--cpu-count", "1"] + PACK[5:]
        h, ok = lauf([(False, True)], args)
        self.assertFalse(ok)
        self.assertEqual(1, len(h.aufrufe))

    def test_ohne_cpu_count_im_aufruf_bleibt_es_beim_einzellauf(self) -> None:
        h, ok = lauf([(False, True)], ["unpack", "file", "QUELLE", "ZIEL"])
        self.assertFalse(ok)
        self.assertEqual(1, len(h.aufrufe))

    def test_ein_abbruch_startet_nicht_neu(self) -> None:
        huelle = Huelle([(False, True)])
        huelle.is_running = False
        with mock.patch.object(haupt.time, "sleep"):
            self.assertFalse(huelle._execute_mkpfs(list(PACK)))
        self.assertEqual(1, len(huelle.aufrufe))

    def test_kann_das_halbe_ergebnis_nicht_weg_wird_nicht_weitergelaufen(self) -> None:
        huelle = Huelle([(False, True), (True, False)])
        huelle.aufraeumen_klappt = False
        with mock.patch.object(haupt.time, "sleep"):
            self.assertFalse(huelle._execute_mkpfs(list(PACK)))
        self.assertEqual(1, len(huelle.aufrufe))

    def test_der_urspruengliche_aufruf_bleibt_unveraendert(self) -> None:
        ursprung = list(PACK)
        huelle = Huelle([(False, True), (True, False)])
        with mock.patch.object(haupt.time, "sleep"):
            huelle._execute_mkpfs(ursprung)
        self.assertEqual(PACK, ursprung)


class SchreiberTests(unittest.TestCase):

    def _schreiber(self):
        return haupt._QueueWriter(queue.Queue())

    def test_memoryerror_im_protokoll_wird_bemerkt(self) -> None:
        s = self._schreiber()
        s.write("Traceback (most recent call last):\n  File x\nMemoryError\n")
        self.assertTrue(s.speicher)

    def test_ein_beendeter_arbeiterprozess_zaehlt_auch(self) -> None:
        s = self._schreiber()
        s.write("concurrent.futures.process.BrokenProcessPool: A process in the pool was terminated abruptly\n")
        self.assertTrue(s.speicher)

    def test_normale_ausgabe_ist_kein_speichermangel(self) -> None:
        s = self._schreiber()
        s.write("[####] 48% compress ETA 1s\nFertig\n")
        self.assertFalse(s.speicher)

    def test_die_zeilen_gehen_weiter_unveraendert_in_die_warteschlange(self) -> None:
        q: queue.Queue = queue.Queue()
        s = haupt._QueueWriter(q)
        s.write("MemoryError\nrest")
        s.flush()
        self.assertEqual(["MemoryError", "rest"], [q.get_nowait(), q.get_nowait()])


class TextTests(unittest.TestCase):

    def test_meldung_in_beiden_sprachen(self) -> None:
        eintrag = STRINGS["mkpfs.speicher_neuversuch"]
        for sprache in ("de", "en"):
            for feld in ("{alt}", "{neu}", "{nr}", "{max}"):
                self.assertIn(feld, eintrag[sprache])
        self.assertNotEqual(eintrag["de"], eintrag["en"])


if __name__ == "__main__":
    unittest.main()
