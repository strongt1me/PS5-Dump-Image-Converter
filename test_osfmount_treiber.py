# -*- coding: utf-8 -*-
"""OSFMount: "vorhanden" heisst nicht "einsatzbereit".

Gemessen am 19.09.2026 auf dem Entwicklungsrechner: OSFMount 3.3.1000
installiert, der Diagnosebericht meldete "vorhanden, Fassung 3.3.1000" -
und der Treiber osfdisk fehlte ganz (kein Dienst, kein Paket im
Treiberspeicher, keine osfdisk.sys, kein Geraet). Der Rueckfall haette nichts
einhaengen koennen. ``osfmount_treiber`` prueft das jetzt, nur lesend.

Drei Teile: die Beurteilung mit eingesetzten Messfuehlern (jedes Urteil),
die echten Lesestellen gegen Eintraege, die es auf jedem Windows gibt
(BasicDisplay), und der Weg in den Diagnosebericht.
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
pruefumgebung.umlenken("osfmount_treiber")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import osfmount_treiber as ot      # noqa: E402


def _fuehler(*, start=None, speicher=None, datei=False, geraet=None, fehler=None):
    def _dienst():
        if fehler:
            raise fehler
        return start
    return ot.Messfuehler(dienst_start=_dienst,
                          im_treiberspeicher=lambda: speicher,
                          treiberdatei=lambda: datei,
                          geraet=lambda: geraet)


class _Installiert(unittest.TestCase):
    """Ein nachgebauter Programmordner: OSFMount.com und win10\\osfdisk.inf."""

    def setUp(self) -> None:
        self.ordner = Path(tempfile.mkdtemp(prefix="osfmount_"))
        self.addCleanup(shutil.rmtree, self.ordner, True)
        self.programm = self.ordner / "OSFMount.com"
        self.programm.write_bytes(b"MZ")
        (self.ordner / "win10").mkdir()
        self.inf = self.ordner / "win10" / "osfdisk.inf"
        self.inf.write_text("[Version]\n", encoding="ascii")

    def _zustand(self, **kwargs) -> ot.Treiberzustand:
        return ot.zustand(str(self.programm), fuehler=_fuehler(**kwargs), windows=True)


class UrteilTests(_Installiert):

    def test_der_gemessene_fall_programm_ohne_treiber(self) -> None:
        z = self._zustand(start=None, speicher=False, datei=False, geraet=False)
        self.assertEqual(ot.TREIBER_FEHLT, z.urteil)
        zeile = ot.berichtszeile(z)
        self.assertIn("NICHT INSTALLIERT", zeile)
        self.assertIn("weder Dienst noch Treiberpaket", zeile)
        self.assertIn('pnputil /add-driver "%s" /install' % self.inf, zeile)

    def test_paket_im_speicher_aber_kein_dienst(self) -> None:
        z = self._zustand(start=None, speicher=True)
        self.assertEqual(ot.TREIBER_FEHLT, z.urteil)
        self.assertIn("Treiberspeicher, der Dienst fehlt", ot.berichtszeile(z))

    def test_deaktiviert(self) -> None:
        z = self._zustand(start=ot.START_DEAKTIVIERT, speicher=True, datei=True, geraet=True)
        self.assertEqual(ot.DEAKTIVIERT, z.urteil)
        self.assertIn("Start=4", ot.berichtszeile(z))

    def test_treiberdatei_fehlt(self) -> None:
        z = self._zustand(start=1, speicher=True, datei=False, geraet=True)
        self.assertEqual(ot.DATEI_FEHLT, z.urteil)

    def test_adapter_fehlt(self) -> None:
        """Der Fall aus der fremden Anleitung: Treiber da, Geraet root\\osfdisk nicht."""
        z = self._zustand(start=3, speicher=True, datei=True, geraet=False)
        self.assertEqual(ot.ADAPTER_FEHLT, z.urteil)
        zeile = ot.berichtszeile(z)
        self.assertIn("root\\osfdisk", zeile)
        self.assertIn(str(self.inf), zeile)

    def test_bereit(self) -> None:
        z = self._zustand(start=3, speicher=True, datei=True, geraet=True)
        self.assertEqual(ot.BEREIT, z.urteil)
        self.assertTrue(ot.berichtszeile(z).startswith("bereit"))

    def test_ungelesenes_geraet_ist_kein_bereit(self) -> None:
        """None heisst nicht nachgesehen - daraus wird kein "bereit"."""
        z = self._zustand(start=3, speicher=True, datei=True, geraet=None)
        self.assertEqual(ot.UNBEKANNT, z.urteil)
        self.assertIn("nicht feststellbar", ot.berichtszeile(z))

    def test_eine_scheiternde_lesestelle_kippt_nichts(self) -> None:
        z = self._zustand(fehler=PermissionError("Zugriff verweigert"))
        self.assertEqual(ot.UNBEKANNT, z.urteil)
        self.assertIn("Zugriff verweigert", ot.berichtszeile(z))

    def test_ohne_osfmount_nichts_zu_sagen(self) -> None:
        z = ot.zustand(str(self.ordner / "fehlt.com"), fuehler=_fuehler(), windows=True)
        self.assertEqual(ot.NICHT_INSTALLIERT, z.urteil)
        self.assertEqual("", ot.berichtszeile(z))

    def test_ausserhalb_von_windows_nichts_zu_sagen(self) -> None:
        z = ot.zustand(str(self.programm), fuehler=_fuehler(), windows=False)
        self.assertEqual(ot.NICHT_WINDOWS, z.urteil)
        self.assertEqual("", ot.berichtszeile(z))


class InfFindenTests(_Installiert):

    def test_win10_hat_vorrang(self) -> None:
        (self.ordner / "win10old").mkdir()
        (self.ordner / "win10old" / "osfdisk.inf").write_text("x", encoding="ascii")
        self.assertEqual(str(self.inf), ot.inf_finden(str(self.ordner)))

    def test_sonst_irgendein_unterordner(self) -> None:
        shutil.rmtree(self.ordner / "win10")
        (self.ordner / "win7").mkdir()
        (self.ordner / "win7" / "osfdisk.inf").write_text("x", encoding="ascii")
        self.assertTrue(ot.inf_finden(str(self.ordner)).endswith(
            os.path.join("win7", "osfdisk.inf")))

    def test_ohne_inf_leer(self) -> None:
        shutil.rmtree(self.ordner / "win10")
        self.assertEqual("", ot.inf_finden(str(self.ordner)))


@unittest.skipUnless(os.name == "nt", "Registry und pnputil gibt es nur unter Windows")
class EchteLesestellenTests(unittest.TestCase):
    """Die Lesestellen gegen das echte System - an Eintraegen, die es gibt.

    BasicDisplay ist auf jedem Windows 10/11 ein Dienst mit einem Geraet unter
    Enum\\Root (gemessen: ``Enum\\Root\\BasicDisplay\\0000``, Service
    ``BasicDisplay``, HardwareID ``ROOT\\BasicDisplay``). Ohne diese Probe
    meldete ein falscher Registry-Pfad still "fehlt" - genau das Ergebnis,
    das auf dem Entwicklungsrechner ohnehin zu erwarten ist.
    """

    def test_dienst_und_geraet_eines_vorhandenen_treibers(self) -> None:
        with mock.patch.object(ot, "DIENST", "basicdisplay"), \
                mock.patch.object(ot, "HARDWARE_ID", "root\\basicdisplay"):
            self.assertIsInstance(ot._dienst_start_lesen(), int)
            self.assertTrue(ot._geraet_lesen())

    def test_erfundener_treiber_fehlt_ueberall(self) -> None:
        with mock.patch.object(ot, "DIENST", "gibtesnicht12345"), \
                mock.patch.object(ot, "HARDWARE_ID", "root\\gibtesnicht12345"):
            self.assertIsNone(ot._dienst_start_lesen())
            self.assertFalse(ot._geraet_lesen())
            self.assertIn(ot._im_treiberspeicher_lesen(), (False, None))


class BerichtTests(_Installiert):
    """Die Zeile kommt im Diagnosebericht an - unter dem Werkzeug OSFMount."""

    def _gui(self, gemerkt: str):
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._load_setting = lambda k, v=None: gemerkt if k == "osfmount_path" else v
        return gui

    @unittest.skipUnless(os.name == "nt", "OSFMount gibt es nur unter Windows")
    def test_gemerktes_osfmount_ohne_treiber(self) -> None:
        with mock.patch.object(ot, "echte_messfuehler",
                               lambda: _fuehler(start=None, speicher=False)):
            zeilen = self._gui(str(self.programm))._diagnose_werkzeuge()
        treiber = [z for z in zeilen if "OSFMount-Treiber" in z]
        self.assertEqual(1, len(treiber), zeilen)
        self.assertIn("NICHT INSTALLIERT", treiber[0])

    @unittest.skipUnless(os.name == "nt", "OSFMount gibt es nur unter Windows")
    def test_nicht_gemerkt_aber_am_standardort_installiert(self) -> None:
        """Gesucht wird OSFMount nicht mehr - installiert sein kann es trotzdem."""
        standard = self.ordner / "PF"
        (standard / "OSFMount").mkdir(parents=True)
        (standard / "OSFMount" / "OSFMount.com").write_bytes(b"MZ")
        with mock.patch.dict(os.environ, {"ProgramFiles": str(standard)}), \
                mock.patch.object(ot, "echte_messfuehler",
                                  lambda: _fuehler(start=3, speicher=True,
                                                   datei=True, geraet=True)):
            zeilen = self._gui("")._diagnose_werkzeuge()
        self.assertTrue(any("OSFMount-Treiber" in z and "bereit" in z for z in zeilen),
                        zeilen)

    def test_ohne_osfmount_keine_treiberzeile(self) -> None:
        with mock.patch.dict(os.environ, {"ProgramFiles": str(self.ordner / "leer")}):
            zeilen = self._gui("")._diagnose_werkzeuge()
        self.assertFalse([z for z in zeilen if "OSFMount-Treiber" in z])


class InstallerTests(_Installiert):
    """Punkt 19 "OSFMount installieren" - "gefunden" hiess bisher "einsatzbereit".

    Die Pruefung vor und nach der stillen Installation war
    ``_find_osfmount() is not None``. Auf dem Entwicklungsrechner haette
    Punkt 19 damit "bereits installiert und einsatzbereit" gemeldet und
    nichts getan - der Treiber fehlte.
    """

    def _gui(self):
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._find_osfmount = lambda: str(self.programm)
        gui._t = lambda k, **w: k + "".join("|%s=%s" % (a, b) for a, b in sorted(w.items()))
        return gui

    def test_punkt_19_prueft_programm_und_treiber(self) -> None:
        gui = self._gui()
        mitgegeben: dict = {}
        gui._run_background_installer = lambda **kw: mitgegeben.update(kw)
        gui._install_osfmount_background()
        self.assertEqual(gui._osfmount_einsatzbereit, mitgegeben["verify_func"])
        self.assertEqual(gui._osfmount_fehlergrund, mitgegeben["fehlergrund"])

    @unittest.skipUnless(os.name == "nt", "OSFMount gibt es nur unter Windows")
    def test_einsatzbereit_erst_mit_treiber(self) -> None:
        gui = self._gui()
        with mock.patch.object(ot, "echte_messfuehler",
                               lambda: _fuehler(start=None, speicher=False)):
            self.assertFalse(gui._osfmount_einsatzbereit())
        with mock.patch.object(ot, "echte_messfuehler",
                               lambda: _fuehler(start=3, speicher=True, datei=True, geraet=True)):
            self.assertTrue(gui._osfmount_einsatzbereit())

    @unittest.skipUnless(os.name == "nt", "OSFMount gibt es nur unter Windows")
    def test_fehlergrund_nennt_zustand_und_abhilfe(self) -> None:
        with mock.patch.object(ot, "echte_messfuehler",
                               lambda: _fuehler(start=None, speicher=False)):
            grund = self._gui()._osfmount_fehlergrund()
        self.assertIn("osfmount.treiber_nicht_bereit", grund)
        self.assertIn("zustand=osfmount.zustand.treiber_fehlt", grund)
        self.assertIn("inf=%s" % self.inf, grund)

    def test_ohne_osfmount_heisst_der_grund_nicht_gefunden(self) -> None:
        gui = self._gui()
        gui._find_osfmount = lambda: None
        with mock.patch.object(ot.os, "name", "nt"):
            self.assertEqual("osfmount.nicht_gefunden", gui._osfmount_fehlergrund())

    def test_jedes_urteil_hat_einen_text(self) -> None:
        from ps5_validator.utils.i18n import STRINGS
        for urteil in (ot.TREIBER_FEHLT, ot.DEAKTIVIERT, ot.DATEI_FEHLT,
                       ot.ADAPTER_FEHLT, ot.UNBEKANNT):
            with self.subTest(urteil=urteil):
                eintrag = STRINGS.get("osfmount.zustand." + urteil) or {}
                self.assertTrue(eintrag.get("de") and eintrag.get("en"))

    def test_das_fehlerfenster_nennt_den_grund(self) -> None:
        """Ohne Ausnahme gab es bisher keinen Grund - nur "nicht installiert"."""
        import threading
        gui = self._gui()
        gui.is_running = False
        gui._resource_install_running = False
        gui._set_status = lambda *_a, **_k: None
        gui._append_to_log = lambda *_a, **_k: None
        rueckrufe: list = []
        fertig = threading.Event()
        gui.root = mock.Mock()
        gui.root.after = lambda _ms, fn: (rueckrufe.append(fn), fertig.set())
        installiert: list = []
        gui._run_background_installer(
            title="OSFMount", install_func=lambda: installiert.append(1) or True,
            verify_func=lambda: False, nur_windows=False,
            fehlergrund=lambda: "GRUND-XYZ")
        self.assertTrue(fertig.wait(10), "Der Installer-Faden kam nicht zurueck")
        with mock.patch.object(APP.messagebox, "showerror") as fehlerfenster:
            rueckrufe[0]()
        self.assertEqual([1], installiert, "Installiert wurde gar nicht")
        self.assertIn("GRUND-XYZ", str(fehlerfenster.call_args))


if __name__ == "__main__":
    unittest.main(verbosity=2)
