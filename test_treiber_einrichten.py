# -*- coding: utf-8 -*-
"""Treiber fuer ein virtuelles Geraet einrichten - der Ablauf von devcon.

Anlass (gemessen am 19.09.2026): OSFMount lag da, sein Treiber osfdisk nicht.
Der Diagnosebericht riet zu ``pnputil /add-driver ... /install`` - das legt
das virtuelle Geraet ``root\\osfdisk`` aber nicht an, und ohne Geraet kein
Treiber. ``treiber_einrichten`` macht es wie ``devcon``: erst den Treiber auf
ein vorhandenes Geraet, fehlt es, das Geraet anlegen und noch einmal.

Geprueft wird der Ablauf gegen eine nachgebaute Windows-Schnittstelle (jeder
Zweig, auch das Aufraeumen). Echt aufgerufen wird nur, was nichts veraendert:
``SetupDiGetINFClassW`` liest die Klasse aus einer INF. Anlegen und
Installieren braucht Administratorrechte und aendert das System - das
geschieht nur auf Klick im Programm, nie in dieser Pruefung.
"""
from __future__ import annotations

import ctypes
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import treiber_einrichten as te    # noqa: E402

HWID = "root\\osfdisk"


class _Windows:
    """Nachgebaute Schnittstelle: schreibt jeden Aufruf mit.

    ``geraet_da``: Gibt es das Geraet schon? ``fehler``: Schritt -> Code, an
    dem der jeweilige Aufruf scheitert (``treiber2`` = zweiter Versuch).
    """

    def __init__(self, *, geraet_da: bool, fehler: "dict | None" = None,
                 neustart: bool = False) -> None:
        self.geraet_da = geraet_da
        self.fehler = dict(fehler or {})
        self.neustart = neustart
        self.aufrufe: list[str] = []
        self.versuche = 0

    def treiber_installieren(self, hardware_id: str, inf: str) -> bool:
        self.versuche += 1
        self.aufrufe.append("treiber")
        schluessel = "treiber" if self.versuche == 1 else "treiber2"
        if schluessel in self.fehler:
            raise te.WindowsFehler(te.SCHRITT_TREIBER, self.fehler[schluessel])
        if not self.geraet_da:
            raise te.WindowsFehler(te.SCHRITT_TREIBER, te.ERROR_NO_SUCH_DEVINST)
        return self.neustart

    def geraet_anlegen(self, inf: str, hardware_id: str) -> object:
        self.aufrufe.append("anlegen")
        if "anlegen" in self.fehler:
            raise te.WindowsFehler(te.SCHRITT_GERAET, self.fehler["anlegen"])
        self.geraet_da = True
        return "geraet-1"

    def geraet_entfernen(self, geraet: object) -> None:
        self.aufrufe.append("entfernen")
        if "entfernen" in self.fehler:
            raise te.WindowsFehler(te.SCHRITT_GERAET, self.fehler["entfernen"])
        self.geraet_da = False

    def freigeben(self, geraet: object) -> None:
        self.aufrufe.append("freigeben")


class AblaufTests(unittest.TestCase):

    def setUp(self) -> None:
        self.ordner = tempfile.mkdtemp(prefix="treiber_")
        self.addCleanup(shutil.rmtree, self.ordner, True)
        self.inf = os.path.join(self.ordner, "osfdisk.inf")
        with open(self.inf, "w", encoding="ascii") as datei:
            datei.write("[Version]\n")

    def _einrichten(self, api: _Windows) -> te.Ergebnis:
        return te.einrichten(self.inf, HWID, api=api, windows=True)

    def test_vorhandenes_geraet_bekommt_nur_den_treiber(self) -> None:
        api = _Windows(geraet_da=True)
        e = self._einrichten(api)
        self.assertTrue(e.ok)
        self.assertFalse(e.geraet_angelegt)
        self.assertEqual(["treiber"], api.aufrufe, "Ein vorhandenes Geraet wurde neu angelegt")

    def test_fehlendes_geraet_wird_angelegt_dann_der_treiber(self) -> None:
        """Der gemessene Fall: weder Geraet noch Treiber."""
        api = _Windows(geraet_da=False)
        e = self._einrichten(api)
        self.assertTrue(e.ok)
        self.assertTrue(e.geraet_angelegt)
        self.assertEqual(["treiber", "anlegen", "treiber", "freigeben"], api.aufrufe)

    def test_neustart_wird_weitergegeben(self) -> None:
        for da in (True, False):
            with self.subTest(geraet_da=da):
                self.assertTrue(self._einrichten(_Windows(geraet_da=da, neustart=True)).neustart)
        self.assertFalse(self._einrichten(_Windows(geraet_da=True)).neustart)

    def test_anderer_fehler_legt_kein_geraet_an(self) -> None:
        """Nur "kein passendes Geraet" fuehrt zum Anlegen - sonst entstuende
        bei jedem Fehlschlag ein weiteres root\\osfdisk."""
        api = _Windows(geraet_da=True, fehler={"treiber": te.ERROR_ACCESS_DENIED})
        e = self._einrichten(api)
        self.assertFalse(e.ok)
        self.assertEqual((te.SCHRITT_TREIBER, te.ERROR_ACCESS_DENIED), (e.schritt, e.code))
        self.assertNotIn("anlegen", api.aufrufe)

    def test_anlegen_scheitert(self) -> None:
        api = _Windows(geraet_da=False, fehler={"anlegen": te.ERROR_ACCESS_DENIED})
        e = self._einrichten(api)
        self.assertFalse(e.ok)
        self.assertEqual((te.SCHRITT_GERAET, te.ERROR_ACCESS_DENIED), (e.schritt, e.code))
        self.assertEqual(["treiber", "anlegen"], api.aufrufe)

    def test_treiber_scheitert_nach_dem_anlegen_das_geraet_geht_wieder(self) -> None:
        """Kein verwaistes Geraet ohne Treiber zuruecklassen."""
        api = _Windows(geraet_da=False, fehler={"treiber2": te.ERROR_FILE_HASH_NOT_IN_CATALOG})
        e = self._einrichten(api)
        self.assertFalse(e.ok)
        self.assertEqual(te.ERROR_FILE_HASH_NOT_IN_CATALOG, e.code)
        self.assertTrue(e.geraet_angelegt)
        self.assertTrue(e.entfernt)
        self.assertFalse(api.geraet_da)
        self.assertEqual(["treiber", "anlegen", "treiber", "entfernen", "freigeben"], api.aufrufe)

    def test_scheitert_auch_das_entfernen_wird_trotzdem_freigegeben(self) -> None:
        api = _Windows(geraet_da=False, fehler={"treiber2": te.ERROR_CANCELLED,
                                                  "entfernen": te.ERROR_ACCESS_DENIED})
        e = self._einrichten(api)
        self.assertFalse(e.ok)
        self.assertFalse(e.entfernt)
        self.assertEqual(te.ERROR_CANCELLED, e.code)
        self.assertEqual("freigeben", api.aufrufe[-1])

    def test_ohne_inf_kein_aufruf(self) -> None:
        api = _Windows(geraet_da=True)
        e = te.einrichten(os.path.join(self.ordner, "fehlt.inf"), HWID, api=api, windows=True)
        self.assertEqual(te.INF_FEHLT, e.schritt)
        self.assertEqual([], api.aufrufe)

    def test_ausserhalb_von_windows_kein_aufruf(self) -> None:
        api = _Windows(geraet_da=True)
        e = te.einrichten(self.inf, HWID, api=api, windows=False)
        self.assertEqual(te.NICHT_WINDOWS, e.schritt)
        self.assertEqual([], api.aufrufe)

    def test_die_inf_geht_mit_vollem_pfad_hinaus(self) -> None:
        """UpdateDriverForPlugAndPlayDevicesW verlangt den vollen Pfad."""
        gesehen: list = []

        class _Merkt(_Windows):
            def treiber_installieren(self, hardware_id, inf):
                gesehen.append(inf)
                return super().treiber_installieren(hardware_id, inf)

        alt = os.getcwd()
        self.addCleanup(os.chdir, alt)
        os.chdir(self.ordner)
        te.einrichten("osfdisk.inf", HWID, api=_Merkt(geraet_da=True), windows=True)
        self.assertEqual(1, len(gesehen))
        self.assertTrue(os.path.isabs(gesehen[0]), gesehen[0])
        self.assertTrue(os.path.samefile(self.inf, gesehen[0]))


class BausteinTests(unittest.TestCase):

    def test_hardware_id_als_multi_sz(self) -> None:
        daten = te.hardware_id_multi_sz(HWID)
        self.assertEqual(HWID.encode("utf-16-le") + b"\x00\x00\x00\x00", daten)

    def test_strukturgroessen_wie_in_windows(self) -> None:
        """cbSize falsch -> ERROR_INVALID_USER_BUFFER, und nur beim Anwender."""
        self.assertEqual(16, ctypes.sizeof(te._GUID))
        erwartet = 32 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
        self.assertEqual(erwartet, ctypes.sizeof(te._SP_DEVINFO_DATA))

    def test_fehlercodes_als_vorzeichenlose_zahl(self) -> None:
        self.assertEqual(te.ERROR_NO_SUCH_DEVINST,
                         te.WindowsFehler(te.SCHRITT_TREIBER, -0x1FFFFDF5).code)

    def test_jeder_bekannte_fehler_hat_einen_satz(self) -> None:
        from ps5_validator.utils.i18n import STRINGS
        for schluessel in set(te.BEKANNTE_FEHLER.values()) | {
                te.KEINE_RECHTE, te.INF_FEHLT, te.NICHT_WINDOWS, "unbekannt", "ohne_code"}:
            with self.subTest(fehler=schluessel):
                eintrag = STRINGS.get("treiber.fehler." + schluessel) or {}
                self.assertTrue(eintrag.get("de") and eintrag.get("en"))
        for schritt in (te.SCHRITT_KLASSE, te.SCHRITT_GERAET, te.SCHRITT_TREIBER):
            with self.subTest(schritt=schritt):
                eintrag = STRINGS.get("treiber.schritt." + schritt) or {}
                self.assertIn("{grund}", eintrag.get("de", ""))
                self.assertIn("{grund}", eintrag.get("en", ""))

    @unittest.skipUnless(os.name == "nt", "FormatMessage gibt es nur unter Windows")
    def test_systemtext_nur_wo_windows_einen_kennt(self) -> None:
        self.assertTrue(te.systemtext(te.ERROR_ACCESS_DENIED))
        # Gemessen: Zu SetupAPI-Codes liefert FormatMessage "<no description>".
        self.assertEqual("", te.systemtext(te.ERROR_NO_SUCH_DEVINST))


@unittest.skipUnless(os.name == "nt", "setupapi.dll gibt es nur unter Windows")
class EchteLesestelleTests(unittest.TestCase):
    """SetupDiGetINFClassW liest nur - das darf die Pruefung wirklich aufrufen."""

    def test_klasse_aus_einer_nachgebauten_inf(self) -> None:
        ordner = tempfile.mkdtemp(prefix="inf_")
        self.addCleanup(shutil.rmtree, ordner, True)
        inf = os.path.join(ordner, "probe.inf")
        with open(inf, "w", encoding="ascii") as datei:
            datei.write('[Version]\nSignature="$WINDOWS NT$"\nClass=SCSIAdapter\n'
                        "ClassGUID={4D36E97B-E325-11CE-BFC1-08002BE10318}\n")
        guid, name = te.SetupApi().inf_klasse(inf)
        self.assertEqual("SCSIAdapter", name)
        self.assertEqual("{4D36E97B-E325-11CE-BFC1-08002BE10318}", te.guid_text(guid))

    def test_fehlende_inf_meldet_den_schritt(self) -> None:
        with self.assertRaises(te.WindowsFehler) as fall:
            te.SetupApi().inf_klasse(os.path.join(tempfile.gettempdir(), "gibt_es_nicht_4711.inf"))
        self.assertEqual(te.SCHRITT_KLASSE, fall.exception.schritt)
        self.assertNotEqual(0, fall.exception.code)

    def test_die_echte_osfdisk_inf_falls_installiert(self) -> None:
        inf = r"C:\Program Files\OSFMount\win10\osfdisk.inf"
        if not os.path.isfile(inf):
            self.skipTest("OSFMount ist hier nicht installiert")
        guid, name = te.SetupApi().inf_klasse(inf)
        self.assertEqual("SCSIAdapter", name)
        self.assertEqual("{4D36E97B-E325-11CE-BFC1-08002BE10318}", te.guid_text(guid))


if __name__ == "__main__":
    unittest.main(verbosity=2)
