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
        # Bis v1.9.29 stand hier pnputil - das legt das Geraet root\osfdisk
        # nicht an. Der Rat zeigt jetzt auf Punkt 19, der es anlegt.
        self.assertIn("Punkt 19", zeile)
        self.assertNotIn("pnputil", zeile)

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
        self.assertIn("Punkt 19", zeile)

    def test_jeder_mangel_nennt_einen_weg(self) -> None:
        """Wo Punkt 19 hilft, sagt es der Bericht - auch bei fehlender Datei."""
        for kwargs in ({"start": None}, {"start": 1, "speicher": True, "datei": False,
                                         "geraet": True},
                       {"start": ot.START_DEAKTIVIERT, "speicher": True, "datei": True,
                        "geraet": True}):
            with self.subTest(**{k: str(v) for k, v in kwargs.items()}):
                zeile = ot.berichtszeile(self._zustand(**kwargs))
                self.assertIn("Punkt 19", zeile)
                self.assertNotIn("pnputil", zeile)

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
        # Ohne Versuch kein Satz ueber einen Versuch.
        self.assertIn("|versuch=", grund)
        self.assertNotIn("osfmount.versuch_gescheitert", grund)

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


class EinrichtenTests(_Installiert):
    """Punkt 19 richtet den fehlenden Treiber selbst ein - ohne Download.

    Gemessen am 19.09.2026: OSFMount da, Treiber nicht. Punkt 19 haette das
    Programm erneut still installiert - und die stille Installation laesst
    den Treiber hier aus. Jetzt kommt er aus dem Programmordner, wie bei
    ``devcon install``. Anlegen und Installieren aendern das System; hier ist
    ``treiber_einrichten.einrichten`` ersetzt und schreibt nur mit.
    """

    def _gui(self, *, programme=None):
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        folge = iter(programme or [])
        gui._find_osfmount = lambda: next(folge, str(self.programm))
        gui._t = lambda k, **w: k + "".join("|%s=%s" % (a, b) for a, b in sorted(w.items()))
        gui.protokoll = []
        gui._append_to_log = gui.protokoll.append
        gui._set_status = lambda *_a, **_k: None
        gui._get_runtime_temp_dir = lambda: str(self.ordner)
        return gui

    def _ausfuehren(self, gui, *, zustaende, admin=True, ergebnis=None, fehler=None):
        from ps5_validator.utils import treiber_einrichten as te
        aufrufe: dict = {"einrichten": [], "download": [], "installer": []}
        fuehler = iter(zustaende)

        def _einrichten(inf, hardware_id, **_kw):
            aufrufe["einrichten"].append((inf, hardware_id))
            if fehler is not None:
                raise fehler
            return ergebnis if ergebnis is not None else te.Ergebnis(True)

        with mock.patch.object(APP, "IST_WINDOWS", True), \
                mock.patch.object(ot.os, "name", "nt"), \
                mock.patch.object(ot, "echte_messfuehler",
                                  lambda: _fuehler(**next(fuehler))), \
                mock.patch.object(APP, "_is_admin", lambda: admin), \
                mock.patch.object(te, "einrichten", _einrichten), \
                mock.patch.object(APP.urllib.request, "urlretrieve",
                                  lambda *a, **k: aufrufe["download"].append(a)), \
                mock.patch.object(gui, "_run_subprocess_logged",
                                  lambda befehl, **k: aufrufe["installer"].append(befehl) or 0):
            ok = gui._install_osfmount()
        return ok, aufrufe

    FEHLT = {"start": None, "speicher": False}
    BEREIT = {"start": 3, "speicher": True, "datei": True, "geraet": True}

    def test_nur_der_treiber_fehlt_nichts_wird_geladen(self) -> None:
        ok, aufrufe = self._ausfuehren(self._gui(), zustaende=[self.FEHLT])
        self.assertTrue(ok)
        self.assertEqual([(str(self.inf), ot.HARDWARE_ID)], aufrufe["einrichten"])
        self.assertEqual([], aufrufe["download"], "OSFMount wurde erneut heruntergeladen")
        self.assertEqual([], aufrufe["installer"])

    def test_ohne_adminrechte_wird_nichts_versucht(self) -> None:
        from ps5_validator.utils import treiber_einrichten as te
        gui = self._gui()
        ok, aufrufe = self._ausfuehren(gui, zustaende=[self.FEHLT], admin=False)
        self.assertFalse(ok)
        self.assertEqual([], aufrufe["einrichten"])
        self.assertEqual(te.KEINE_RECHTE, gui._osfmount_letzter_versuch.schritt)
        self.assertTrue(any("treiber.fehler.keine_rechte" in z for z in gui.protokoll))

    def test_stille_installation_ohne_treiber_wird_nachgeholt(self) -> None:
        """Nicht installiert -> laden, still installieren, Treiber nachholen."""
        gui = self._gui(programme=[""])
        ok, aufrufe = self._ausfuehren(gui, zustaende=[self.FEHLT])
        self.assertTrue(ok)
        self.assertEqual(1, len(aufrufe["download"]))
        self.assertIn("/VERYSILENT", aufrufe["installer"][0])
        self.assertEqual([(str(self.inf), ot.HARDWARE_ID)], aufrufe["einrichten"])

    def test_bereit_tut_nichts(self) -> None:
        ok, aufrufe = self._ausfuehren(self._gui(), zustaende=[self.BEREIT])
        self.assertTrue(ok)
        self.assertEqual({"einrichten": [], "download": [], "installer": []}, aufrufe)

    def test_gescheitertes_einrichten_steht_im_fehlerfenster(self) -> None:
        from ps5_validator.utils import treiber_einrichten as te
        gui = self._gui()
        ok, _ = self._ausfuehren(
            gui, zustaende=[self.FEHLT],
            ergebnis=te.Ergebnis(False, te.SCHRITT_GERAET, te.ERROR_ACCESS_DENIED))
        self.assertFalse(ok)
        with mock.patch.object(ot, "echte_messfuehler", lambda: _fuehler(**self.FEHLT)), \
                mock.patch.object(ot.os, "name", "nt"):
            grund = gui._osfmount_fehlergrund()
        self.assertIn("osfmount.versuch_gescheitert", grund)
        self.assertIn("treiber.schritt.geraet", grund)
        self.assertIn("treiber.fehler.rechte", grund)

    def test_eine_ausnahme_wird_ein_ergebnis(self) -> None:
        """Etwa eine fehlende DLL - das Fehlerfenster braucht trotzdem einen Grund."""
        from ps5_validator.utils import treiber_einrichten as te
        gui = self._gui()
        ok, _ = self._ausfuehren(gui, zustaende=[self.FEHLT], fehler=OSError("newdev fehlt"))
        self.assertFalse(ok)
        self.assertEqual(te.SCHRITT_TREIBER, gui._osfmount_letzter_versuch.schritt)
        self.assertIn("treiber.fehler.ohne_code", gui._treiber_fehlertext(gui._osfmount_letzter_versuch))

    def test_neustart_kommt_in_die_erfolgsmeldung(self) -> None:
        from ps5_validator.utils import treiber_einrichten as te
        gui = self._gui()
        self._ausfuehren(gui, zustaende=[self.FEHLT], ergebnis=te.Ergebnis(True, neustart=True))
        self.assertEqual("osfmount.neustart_noetig", gui._osfmount_erfolgshinweis())
        self._ausfuehren(gui, zustaende=[self.FEHLT], ergebnis=te.Ergebnis(True))
        self.assertEqual("", gui._osfmount_erfolgshinweis())

    def test_punkt_19_setzt_zurueck_und_gibt_den_hinweis_mit(self) -> None:
        from ps5_validator.utils import treiber_einrichten as te
        gui = self._gui()
        gui._osfmount_letzter_versuch = te.Ergebnis(False, te.SCHRITT_GERAET, 5)
        mitgegeben: dict = {}
        gui._run_background_installer = lambda **kw: mitgegeben.update(kw)
        gui._install_osfmount_background()
        self.assertIsNone(gui._osfmount_letzter_versuch)
        self.assertEqual(gui._osfmount_erfolgshinweis, mitgegeben["erfolgshinweis"])

    def test_fehlertext_eines_unbekannten_codes(self) -> None:
        from ps5_validator.utils import treiber_einrichten as te
        gui = self._gui()
        versuch = te.Ergebnis(False, te.SCHRITT_TREIBER, 0xE0000999)
        with mock.patch.object(te, "systemtext", lambda _c: ""):
            text = gui._treiber_fehlertext(versuch)
        self.assertIn("treiber.schritt.treiber", text)
        self.assertIn("code=0xE0000999", text)
        with mock.patch.object(te, "systemtext", lambda _c: "Systemsatz"):
            self.assertIn("Systemsatz", gui._treiber_fehlertext(versuch))

    def test_die_erfolgsmeldung_traegt_den_zusatz(self) -> None:
        import threading
        gui = self._gui()
        gui.is_running = False
        gui._resource_install_running = False
        rueckrufe: list = []
        fertig = threading.Event()
        gui.root = mock.Mock()
        gui.root.after = lambda _ms, fn: (rueckrufe.append(fn), fertig.set())
        pruefungen = iter([False, True])
        gui._run_background_installer(
            title="OSFMount", install_func=lambda: True,
            verify_func=lambda: next(pruefungen), nur_windows=False,
            erfolgshinweis=lambda: "ZUSATZ-XYZ")
        self.assertTrue(fertig.wait(10), "Der Installer-Faden kam nicht zurueck")
        with mock.patch.object(APP.messagebox, "showinfo") as meldung:
            rueckrufe[0]()
        self.assertIn("ZUSATZ-XYZ", str(meldung.call_args))


if __name__ == "__main__":
    unittest.main(verbosity=2)
