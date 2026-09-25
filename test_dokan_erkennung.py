# -*- coding: utf-8 -*-
"""Dokan: nur Dokan 2 taugt fuer mount_udf.

Die Laufzeit dokan2.dll spricht nur mit dem Kerneltreiber dokan2.sys. Bis
zum 19.09.2026 galt auch dokan1.sys oder dokan.sys als Treiber - ein Rest
aus Dokan 1 neben einer dokan2.dll hiess "einsatzbereit", Punkt 20
installierte nichts, und mount_udf scheiterte trotzdem. Gemessen auf dem
Entwicklungsrechner: Dokan 2.3.1 legt dokan2.sys und dokan2.dll ab.

Geprueft wird gegen ein nachgebautes SystemRoot. Die echte dokan2.dll des
Rechners darf dabei nicht mitzaehlen - sie liegt im Suchpfad und liesse
sich laden. Deshalb ist ``ctypes.WinDLL`` in jedem Fall ersetzt.

Seit dem 19.09.2026 steht die Pruefung in ``dokan_treiber``, und der
Diagnosebericht nennt Dokan unter den Fremdwerkzeugen: jedes Urteil, der
Weg in den Bericht und die Abhilfe - der Knopf "Dokan2-Treiber
installieren" wird nur dort empfohlen, wo er auch etwas tut.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("dokan_erkennung")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import dokan_treiber as dt          # noqa: E402
from ps5_validator.utils.diagnose_befund import Diagnosebericht  # noqa: E402


class DokanErkennungTests(unittest.TestCase):
    """``_find_dokan_driver`` gegen ein nachgebautes SystemRoot."""

    def setUp(self) -> None:
        self.wurzel = Path(tempfile.mkdtemp(prefix="sysroot_"))
        self.addCleanup(shutil.rmtree, self.wurzel, True)
        (self.wurzel / "System32" / "drivers").mkdir(parents=True)
        self.gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)

    def _ablegen(self, *namen: str) -> None:
        for name in namen:
            ordner = self.wurzel / "System32"
            if name.endswith(".sys"):
                ordner = ordner / "drivers"
            (ordner / name).write_bytes(b"MZ")

    def _erkannt(self, *, dll_ladbar: bool = False) -> bool:
        """Misst mit dem nachgebauten SystemRoot - nie mit dem echten."""
        if dll_ladbar:
            laden = mock.Mock(return_value=object())
        else:
            laden = mock.Mock(side_effect=OSError("nicht gefunden"))
        with mock.patch.dict(os.environ, {"SystemRoot": str(self.wurzel)}), \
                mock.patch.object(APP.sys, "platform", "win32"), \
                mock.patch("ctypes.WinDLL", laden, create=True):
            return self.gui._find_dokan_driver()

    def test_dokan2_vollstaendig(self) -> None:
        self._ablegen("dokan2.sys", "dokan2.dll")
        self.assertTrue(self._erkannt())

    def test_dokan1_treiber_neben_dokan2_dll_ist_nicht_bereit(self) -> None:
        """Der Fall, der bis zum 19.09.2026 als "einsatzbereit" galt."""
        self._ablegen("dokan1.sys", "dokan2.dll")
        self.assertFalse(self._erkannt())

    def test_alter_dokan_treiber_neben_dokan2_dll_ist_nicht_bereit(self) -> None:
        self._ablegen("dokan.sys", "dokan2.dll")
        self.assertFalse(self._erkannt())

    def test_nur_dokan1_ist_nicht_bereit(self) -> None:
        self._ablegen("dokan1.sys", "dokan1.dll")
        self.assertFalse(self._erkannt())

    def test_treiber_ohne_laufzeit_ist_nicht_bereit(self) -> None:
        self._ablegen("dokan2.sys")
        self.assertFalse(self._erkannt())

    def test_laufzeit_ueber_den_suchpfad_zaehlt(self) -> None:
        """dokan2.dll muss nicht in System32 liegen - ladbar genuegt."""
        self._ablegen("dokan2.sys")
        self.assertTrue(self._erkannt(dll_ladbar=True))

    def test_ausserhalb_von_windows_nie(self) -> None:
        self._ablegen("dokan2.sys", "dokan2.dll")
        with mock.patch.dict(os.environ, {"SystemRoot": str(self.wurzel)}), \
                mock.patch.object(APP.sys, "platform", "linux"):
            self.assertFalse(self.gui._find_dokan_driver())

    def test_die_entscheidung_faellt_im_modul(self) -> None:
        """Eine Pruefung fuer Programm und Bericht - kein zweites Getriebe."""
        for antwort in (True, False):
            with self.subTest(antwort=antwort), \
                    mock.patch.object(APP.sys, "platform", "win32"), \
                    mock.patch.object(dt, "dateien_bereit",
                                      return_value=antwort) as bereit:
                self.assertIs(antwort, self.gui._find_dokan_driver())
                bereit.assert_called_once_with()


def _fuehler(*, treiber=(), im_system=False, ladbar=False, start=None, fehler=None):
    def _treiber():
        if fehler:
            raise fehler
        return tuple(treiber)
    return dt.Messfuehler(treiberdateien=_treiber,
                          laufzeit_im_system=lambda: im_system,
                          laufzeit_ladbar=lambda: ladbar,
                          dienst_start=lambda: start)


#: Je Urteil ein Zustand, wie ihn die Lesestellen liefern koennten.
FAELLE = {
    dt.BEREIT: dict(treiber=("dokan2.sys",), im_system=True, start=2),
    dt.NICHT_INSTALLIERT: dict(),
    dt.NUR_DOKAN1: dict(treiber=("dokan1.sys",)),
    dt.TREIBER_FEHLT: dict(treiber=("dokan1.sys",), im_system=True),
    dt.LAUFZEIT_FEHLT: dict(treiber=("dokan2.sys",), start=2),
    dt.DIENST_FEHLT: dict(treiber=("dokan2.sys",), im_system=True),
    dt.DEAKTIVIERT: dict(treiber=("dokan2.sys",), im_system=True, start=4),
}


class UrteilTests(unittest.TestCase):
    """``dokan_treiber.zustand`` - jedes Urteil und sein Text."""

    def test_jedes_urteil(self) -> None:
        self.assertGreaterEqual(len(FAELLE), 7)
        for urteil, fall in FAELLE.items():
            with self.subTest(urteil=urteil):
                self.assertEqual(urteil, dt.zustand(_fuehler(**fall), windows=True).urteil)

    def test_laufzeit_ueber_den_suchpfad_zaehlt(self) -> None:
        f = _fuehler(treiber=("dokan2.sys",), ladbar=True, start=3)
        self.assertEqual(dt.BEREIT, dt.zustand(f, windows=True).urteil)

    def test_bereit_nennt_dienst_und_fassung(self) -> None:
        z = dt.zustand(_fuehler(**FAELLE[dt.BEREIT]), windows=True)
        zeile = dt.berichtszeile(z, fassung="2.3.1.1000")
        self.assertTrue(zeile.startswith("bereit"), zeile)
        self.assertIn("Start=2", zeile)
        self.assertIn("Fassung 2.3.1.1000", zeile)

    def test_der_fall_von_v1_9_28_nennt_den_alten_treiber(self) -> None:
        """dokan1.sys neben dokan2.dll - bis v1.9.28 hiess das "bereit"."""
        zeile = dt.berichtszeile(dt.zustand(_fuehler(**FAELLE[dt.TREIBER_FEHLT]),
                                            windows=True))
        self.assertIn("dokan2.sys fehlt", zeile)
        self.assertIn("dokan1.sys gehört zu Dokan 1", zeile)

    def test_eine_scheiternde_lesestelle_kippt_nichts(self) -> None:
        z = dt.zustand(_fuehler(fehler=PermissionError("Zugriff verweigert")), windows=True)
        self.assertEqual(dt.UNBEKANNT, z.urteil)
        self.assertIn("Zugriff verweigert", dt.berichtszeile(z))

    def test_ausserhalb_von_windows_nichts_zu_sagen(self) -> None:
        z = dt.zustand(_fuehler(**FAELLE[dt.BEREIT]), windows=False)
        self.assertEqual(dt.NICHT_WINDOWS, z.urteil)
        self.assertEqual("", dt.berichtszeile(z))


class AbhilfeTests(unittest.TestCase):
    """Der Knopf wird nur empfohlen, wo ``_find_dokan_driver`` Nein sagt.

    Sagt es Ja, meldet der Knopf "bereits installiert" und laedt nichts.
    Liegen die Dateien da und nur der Dienst fehlt, taete er also nichts -
    dort muss der Bericht zur Neuinstallation raten.
    """

    def test_dateien_bereit_passt_zum_urteil(self) -> None:
        mit_dateien = {dt.BEREIT, dt.DIENST_FEHLT, dt.DEAKTIVIERT}
        for urteil, fall in FAELLE.items():
            with self.subTest(urteil=urteil):
                self.assertEqual(urteil in mit_dateien, dt.dateien_bereit(_fuehler(**fall)))

    def test_knopf_nur_wo_er_etwas_tut(self) -> None:
        knopf = "Dokan2-Treiber installieren"
        for urteil, fall in FAELLE.items():
            if urteil == dt.BEREIT:
                continue
            with self.subTest(urteil=urteil):
                f = _fuehler(**fall)
                zeile = dt.berichtszeile(dt.zustand(f, windows=True))
                if dt.dateien_bereit(f):
                    self.assertNotIn(knopf, zeile)
                    self.assertIn("neu installieren", zeile)
                else:
                    self.assertIn(knopf, zeile)

    def test_bei_bereiten_dateien_laedt_der_knopf_nichts(self) -> None:
        """Beleg fuer die Aussage oben - ausgefuehrt, nicht nachgelesen."""
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._find_dokan_driver = lambda: True
        geladen: list = []
        with mock.patch.object(APP.sys, "platform", "win32"), \
                mock.patch.object(gui, "_installer_laden",
                                  lambda *a, **_k: geladen.append(a), create=True):
            self.assertTrue(gui._install_dokan2_silent())
        self.assertEqual([], geladen)


@unittest.skipUnless(os.name == "nt", "Registry und Treiberordner gibt es nur unter Windows")
class EchteLesestellenTests(unittest.TestCase):
    """Die Lesestellen gegen das echte System - an Eintraegen, die es gibt.

    BasicDisplay ist auf jedem Windows 10/11 ein Dienst mit ``Start``.
    Ohne diese Probe meldete ein falscher Registry-Pfad still "fehlt".
    """

    def test_dienst_eines_vorhandenen_treibers(self) -> None:
        with mock.patch.object(dt, "DIENST", "BasicDisplay"):
            self.assertIsInstance(dt._dienst_start_lesen(), int)

    def test_erfundener_dienst_fehlt(self) -> None:
        with mock.patch.object(dt, "DIENST", "gibtesnicht12345"):
            self.assertIsNone(dt._dienst_start_lesen())

    def test_dateien_im_nachgebauten_systemordner(self) -> None:
        wurzel = Path(tempfile.mkdtemp(prefix="sysroot_"))
        self.addCleanup(shutil.rmtree, wurzel, True)
        (wurzel / "System32" / "drivers").mkdir(parents=True)
        (wurzel / "System32" / "drivers" / "dokan1.sys").write_bytes(b"MZ")
        (wurzel / "System32" / "dokan2.dll").write_bytes(b"MZ")
        with mock.patch.dict(os.environ, {"SystemRoot": str(wurzel)}):
            self.assertEqual(("dokan1.sys",), dt._treiberdateien_lesen())
            self.assertTrue(dt._laufzeit_im_system_lesen())
            self.assertEqual(str(wurzel / "System32" / "dokan2.dll"), dt.laufzeit_pfad())


@unittest.skipUnless(os.name == "nt", "Dokan gibt es nur unter Windows")
class BerichtTests(unittest.TestCase):
    """Die Zeile kommt im Diagnosebericht an - unter den Fremdwerkzeugen."""

    def _zeilen(self, fall: dict, fassung: str = "") -> tuple[list[str], list[str]]:
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._load_setting = lambda _k, v=None: v
        leer = tempfile.mkdtemp(prefix="pf_")
        self.addCleanup(shutil.rmtree, leer, True)
        gefragt: list[str] = []

        def _fassung(pfad: str) -> str:
            gefragt.append(pfad)
            return fassung

        # Ohne OSFMount am Standardort - sonst liefe dessen Pruefung samt
        # pnputil mit, und die Zeile hinge am Zustand dieses Rechners.
        with mock.patch.dict(os.environ, {"ProgramFiles": leer}), \
                mock.patch.object(dt, "echte_messfuehler", lambda: _fuehler(**fall)), \
                mock.patch.object(Diagnosebericht, "_dateifassung", staticmethod(_fassung)):
            return gui._diagnose_werkzeuge(), gefragt

    def test_bereit_mit_fassung_der_laufzeit(self) -> None:
        zeilen, gefragt = self._zeilen(FAELLE[dt.BEREIT], fassung="2.3.1.1000")
        dokan = [z for z in zeilen if z.startswith("Dokan-Treiber:")]
        self.assertEqual(1, len(dokan), zeilen)
        self.assertIn("bereit", dokan[0])
        self.assertIn("Fassung 2.3.1.1000", dokan[0])
        self.assertEqual([dt.laufzeit_pfad()], gefragt)

    def test_der_alte_treiber_steht_als_befund_da(self) -> None:
        zeilen, _gefragt = self._zeilen(FAELLE[dt.TREIBER_FEHLT])
        self.assertTrue(any(z.startswith("Dokan-Treiber: UNVOLLSTÄNDIG") for z in zeilen),
                        zeilen)

    def test_ohne_dokan_sagt_der_bericht_wozu_es_dient(self) -> None:
        zeilen, gefragt = self._zeilen(FAELLE[dt.NICHT_INSTALLIERT])
        dokan = [z for z in zeilen if z.startswith("Dokan-Treiber:")]
        self.assertEqual(1, len(dokan), zeilen)
        self.assertIn(".ffpkg", dokan[0])
        self.assertEqual([], gefragt, "Ohne Laufzeit gibt es keine Fassung zu lesen")


if __name__ == "__main__":
    unittest.main(verbosity=2)
