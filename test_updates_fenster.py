# -*- coding: utf-8 -*-
"""Tests fuer das Fenster „Updates“ und seine Anbindung an das Hauptprogramm.

Das Fenster fragt nur ueber die ``FakeNetz`` aus ``test_werkzeug_updates`` - **nichts geht ins Netz** (jeder Test
sperrt ``urlopen`` und prueft am Ende, dass er nie gerufen wurde: ein Stub mit ``side_effect=AssertionError``
beweist allein nichts, ein ``except Exception`` dazwischen schluckt ihn, siehe ``test_qualitaetslauf``).

Gemessen wird, was der Anwender sieht und bedient: die Liste, die Haken, die Knoepfe, die Zeilen im Protokoll und
dass eine geholte Datei danach dort gefunden wird, wo das Programm sie braucht (``_konsole_payload_datei``,
Schnellauswahl, WebKit-Seite).
"""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                    # noqa: E402
pruefumgebung.umlenken("updates_fenster")

try:
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                      # pragma: no cover - ohne Anzeige
    TK_DA = False
    _WURZEL = None

from ps5_validator.utils import werkzeug_updates as wu     # noqa: E402
from ps5_validator.utils.i18n import STRINGS               # noqa: E402
from test_werkzeug_updates import (AMPR, HELLOWORLD, RELEASES, WEBKIT, FakeNetz,   # noqa: E402
                                   github_roh, inhalt)

#: Eine neuere elfldr-Fassung und ein neues PKG Manager 1.6.0 - zwei ladbare Werkzeuge.
NEUE_FREIGABEN = dict(RELEASES)
NEUE_FREIGABEN['ps5-payload-dev/elfldr'] = [('v0.27', False, '2026-10-12', ['elfldr-ps5.elf'])] + RELEASES[
    'ps5-payload-dev/elfldr']
NEUE_FREIGABEN['itsPLK/ps5-pkg-manager'] = [('v1.6.0', False, '2026-10-12', ['pkg-manager_v1.6.0.elf'])] + RELEASES[
    'itsPLK/ps5-pkg-manager']


class _TorNetz(FakeNetz):
    """Antwortet erst, wenn das Tor aufgeht - so laesst sich eine laufende Pruefung festhalten."""

    def __init__(self, *a, **k) -> None:
        super().__init__(*a, **k)
        self.tor = threading.Event()

    def abfragen(self, quelle, etag=""):
        self.tor.wait(15)
        return super().abfragen(quelle, etag)


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class FensterTestBasis(unittest.TestCase):
    """Das Programmfenster, eine feste Ablage und eine Nachbildung des Netzes."""

    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        self.wurzel = tempfile.mkdtemp(prefix="uf_wurzel_")
        self.basis = tempfile.mkdtemp(prefix="uf_basis_")
        self.addCleanup(shutil.rmtree, self.wurzel, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.basis, ignore_errors=True)
        for ort, namen in ((wu.ORT_PAYLOADS, HELLOWORLD), (wu.ORT_WEBKIT, WEBKIT)):
            ordner = os.path.join(self.wurzel, ort)
            os.makedirs(ordner)
            for name in namen:
                Path(ordner, name).write_bytes(b"x")
        for ordner in ("MkPFS-1.1.0", "UFS2Tool-4.1", "OrbisPkgTool-1.0.0", "PS5-Wee-Tools-0.1.8", "7-Zip-26.00",
                       "AMPR_PackTools-4.0", "PS4FFPFSC-0.2.9", "helloworld/unjail-ps5app-payload-1.2"):
            os.makedirs(os.path.join(self.wurzel, *ordner.split("/")), exist_ok=True)
        self.netz = FakeNetz(releases=NEUE_FREIGABEN)
        self.app._updates_basis = lambda: self.basis
        self.app._mitgeliefert_finden = lambda rel, datei=False: os.path.join(self.wurzel, rel)
        self.app._updates_ampr_vorhanden = lambda: list(AMPR)
        self.app._updates_ampr_ordner = lambda: os.path.join(self.basis, "AMPR EMU updates")
        self.app._updates_geholt = mock.Mock()
        # Aufraeumen der Gegenstaende am Programmfenster - es ist geteilt.
        for name in ("_updates_basis", "_mitgeliefert_finden", "_updates_ampr_vorhanden", "_updates_ampr_ordner",
                     "_updates_geholt"):
            self.addCleanup(self.app.__dict__.pop, name, None)
        # Nie ins Netz: Auch die echte Klasse wird gesperrt.
        patcher = mock.patch.object(wu.urllib.request, "urlopen")
        self.urlopen = patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(lambda: self.urlopen.assert_not_called())
        from ps5_validator.ui import updates_fenster
        self.uf = updates_fenster
        self.fenster = None

    def tearDown(self) -> None:
        fenster = self.fenster
        if fenster is not None:
            fenster._abbruch.set()
            tor = getattr(self.netz, "tor", None)
            if tor is not None:
                tor.set()
            ende = time.time() + 10
            while fenster._laeuft() and time.time() < ende:
                time.sleep(0.01)
            try:
                if fenster.win.winfo_exists():
                    fenster.win.destroy()
            except tk.TclError:
                pass
        _WURZEL.update()
        self.app.__dict__.pop(self.uf.FENSTER_ATTRIBUT, None)

    def oeffnen(self, automatisch: bool = True):
        self.fenster = self.uf.oeffnen(self.app, self.haupt.UI_SCHRIFT, self.haupt.MONO_SCHRIFT, self.haupt.pt,
                                       netz=self.netz, automatisch=automatisch)
        return self.fenster

    def warten(self, fenster=None, sekunden: float = 20.0) -> None:
        """Bis die Arbeit zu Ende ist und der Takt ihr Ergebnis uebernommen hat."""
        fenster = fenster or self.fenster
        ende = time.time() + sekunden
        while time.time() < ende:
            fenster._takt_arbeiten()
            _WURZEL.update()
            if fenster._arbeit is None:
                return
            time.sleep(0.01)
        self.fail("Die Arbeit des Fensters ist nach %d s nicht fertig" % sekunden)

    @staticmethod
    def zeile(fenster, schluessel: str) -> dict:
        werte = fenster.liste.item(schluessel, "values")
        return dict(zip(("haken", "name", "lokal", "neu", "status"), werte))


class ErsterZustandTests(FensterTestBasis):

    def test_ohne_pruefung_zeigt_das_fenster_den_lokalen_stand_und_fragt_nichts(self) -> None:
        f = self.oeffnen(automatisch=False)
        self.assertEqual([], self.netz.gefragt)
        gruppen = [i for i in f.liste.get_children() if i.startswith(self.uf.GRUPPEN_ZEILE)]
        self.assertEqual([self.uf.GRUPPEN_ZEILE + g for g in wu.GRUPPEN], gruppen)
        werkzeuge = [i for i in f.liste.get_children() if not i.startswith(self.uf.GRUPPEN_ZEILE)]
        self.assertEqual([w.schluessel for w in wu.WERKZEUGE], werkzeuge)
        elfldr = self.zeile(f, "elfldr")
        self.assertEqual(("elfldr", "0.26", "–", "nicht geprüft"),
                         (elfldr["name"], elfldr["lokal"], elfldr["neu"], elfldr["status"]))
        self.assertEqual("Kein Vergleich", self.zeile(f, "appinst")["status"])
        self.assertEqual("", elfldr["haken"])

    def test_knoepfe_vor_der_ersten_pruefung(self) -> None:
        f = self.oeffnen(automatisch=False)
        self.assertEqual("normal", str(f.pruefen_knopf.cget("state")))
        for knopf in (f.holen_knopf, f.abbrechen_knopf, f.alle_knopf, f.keine_knopf, f.seite_knopf):
            self.assertEqual("disabled", str(knopf.cget("state")))

    def test_ein_zweites_oeffnen_holt_dasselbe_fenster_nach_vorn(self) -> None:
        f = self.oeffnen(automatisch=False)
        self.assertIs(f, self.uf.oeffnen(self.app, self.haupt.UI_SCHRIFT, self.haupt.MONO_SCHRIFT, self.haupt.pt,
                                         netz=self.netz, automatisch=True))
        self.assertEqual([], self.netz.gefragt, "Das zweite Oeffnen prueft nicht noch einmal")

    def test_oeffnen_mit_automatik_prueft_sofort(self) -> None:
        f = self.oeffnen(automatisch=True)
        self.warten()
        self.assertEqual(len(wu.quellen(wu.WERKZEUGE)), len(self.netz.gefragt))
        self.assertTrue(f.befunde)


class PruefenImFensterTests(FensterTestBasis):

    def test_die_liste_zeigt_nach_der_pruefung_das_urteil(self) -> None:
        f = self.oeffnen()
        self.warten()
        elfldr = self.zeile(f, "elfldr")
        self.assertEqual(("0.26", "0.27", "Neue Fassung", "☐"),
                         (elfldr["lokal"], elfldr["neu"], elfldr["status"], elfldr["haken"]))
        self.assertEqual("Aktuell", self.zeile(f, "ftpsrv")["status"])
        self.assertEqual("Mitgeliefert ist neuer", self.zeile(f, "game-compressor")["status"])
        sieben = self.zeile(f, "7zip")
        self.assertEqual(("26.00", "26.04", "Neu – von Hand einbauen", ""),
                         (sieben["lokal"], sieben["neu"], sieben["status"], sieben["haken"]))
        self.assertEqual("Kein Vergleich", self.zeile(f, "bdj-unpatch")["status"])
        self.assertIn("Neue Fassung", self.zeile(f, "pkgmgr")["status"])

    def test_die_statuszeile_zaehlt(self) -> None:
        f = self.oeffnen()
        self.warten()
        text = f.status_text()
        self.assertTrue(text.startswith("Geprüft: 2 zum Herunterladen"), text)
        self.assertIn("0 nicht erreichbar", text)

    def test_der_zwischenspeicher_liegt_in_der_ablage(self) -> None:
        self.oeffnen()
        self.warten()
        gespeichert = wu.speicher_lesen(self.basis)
        self.assertEqual(sorted(wu.quellen(wu.WERKZEUGE)), sorted(gespeichert))
        self.assertTrue(os.path.isfile(os.path.join(self.basis, wu.UNTERORDNER, wu.SPEICHER_DATEI)))

    def test_eine_zweite_pruefung_nutzt_den_etag(self) -> None:
        f = self.oeffnen()
        self.warten()
        erste = len(self.netz.gefragt)
        f.pruefen_starten()
        self.warten()
        zweite = self.netz.gefragt[erste:]
        self.assertEqual(erste, len(zweite))
        self.assertTrue(all(etag for _q, etag in zweite), "Die zweite Pruefung fragt bedingt (If-None-Match)")

    def test_das_protokoll_nennt_die_pruefung(self) -> None:
        f = self.oeffnen()
        self.warten()
        text = f.protokoll.get("1.0", "end")
        self.assertIn("[Updates] Prüfe %d Quellen" % len(wu.WERKZEUGE), text)

    def test_ein_netzfehler_steht_in_der_zeile_und_in_den_einzelheiten(self) -> None:
        self.netz.ausfaelle["ps5-payload-dev/gdbsrv"] = wu.Antwort(429, "", "", 1760000000)
        self.netz.ausfaelle["owendswang/ps5-aria2"] = OSError("Name or service not known")
        f = self.oeffnen()
        self.warten()
        self.assertEqual("Nicht erreichbar", self.zeile(f, "gdbsrv")["status"])
        f._details_zeigen("gdbsrv")
        details = f.details.get("1.0", "end")
        self.assertIn("60 Anfragen je Stunde", details)
        self.assertIn("Wieder möglich ab", details)
        f._details_zeigen("aria2")
        self.assertIn("nicht erreichbar", f.details.get("1.0", "end"))
        self.assertIn("Name or service", f.details.get("1.0", "end"))
        self.assertIn("2 nicht erreichbar", f.status_text())

    def test_ein_gespeicherter_stand_traegt_sein_datum(self) -> None:
        # Erste Pruefung gelingt, die zweite scheitert: Die Zeile zeigt das Urteil von vorhin - mit Datum.
        f = self.oeffnen()
        self.warten()
        self.netz.ausfaelle["ps5-payload-dev/elfldr"] = OSError("weg")
        f.pruefen_starten()
        self.warten()
        status = self.zeile(f, "elfldr")["status"]
        self.assertTrue(status.startswith("Neue Fassung (Stand "), status)

    def test_abbrechen_haelt_weitere_anfragen_zurueck(self) -> None:
        self.netz = _TorNetz(releases=NEUE_FREIGABEN)
        f = self.oeffnen()
        ende = time.time() + 5
        while not self.netz.gefragt and time.time() < ende:
            _WURZEL.update()
            time.sleep(0.01)
        self.assertTrue(f._laeuft())
        self.assertEqual("normal", str(f.abbrechen_knopf.cget("state")))
        self.assertEqual("disabled", str(f.pruefen_knopf.cget("state")))
        f._abbrechen()
        self.assertEqual("Breche ab …", f.status_text())
        self.netz.tor.set()
        self.warten()
        self.assertEqual("Abgebrochen.", f.status_text())
        self.assertLess(len(self.netz.gefragt), len(wu.quellen(wu.WERKZEUGE)))
        self.assertEqual("normal", str(f.pruefen_knopf.cget("state")))

    def test_scheitert_die_pruefung_ganz_bleibt_das_fenster_bedienbar(self) -> None:
        with mock.patch.object(wu, "pruefen", side_effect=RuntimeError("kaputt")):
            f = self.oeffnen()
            self.warten()
        self.assertIn("fehlgeschlagen", f.status_text())
        self.assertEqual("normal", str(f.pruefen_knopf.cget("state")))
        self.assertTrue(f.befunde, "Die Liste bleibt, wie sie war")

    def test_schliessen_waehrend_der_arbeit_fragt_nach(self) -> None:
        self.netz = _TorNetz(releases=NEUE_FREIGABEN)
        f = self.oeffnen()
        ende = time.time() + 5
        while not self.netz.gefragt and time.time() < ende:
            _WURZEL.update()
            time.sleep(0.01)
        with mock.patch.object(self.uf.messagebox, "askyesno", return_value=False) as frage:
            f._schliessen()
        frage.assert_called_once()
        self.assertTrue(f.win.winfo_exists())
        self.assertFalse(f._abbruch.is_set())
        with mock.patch.object(self.uf.messagebox, "askyesno", return_value=True):
            f._schliessen()
        self.assertTrue(f._abbruch.is_set())
        self.assertFalse(_WURZEL.tk.call("winfo", "exists", str(f.win)) == 1)
        self.assertIsNone(getattr(self.app, self.uf.FENSTER_ATTRIBUT, None))

    def test_schliessen_ohne_arbeit_fragt_nicht(self) -> None:
        f = self.oeffnen(automatisch=False)
        with mock.patch.object(self.uf.messagebox, "askyesno") as frage:
            f._schliessen()
        frage.assert_not_called()

    def test_zwischen_fadenende_und_takt_gilt_das_fenster_noch_als_beschaeftigt(self) -> None:
        f = self.oeffnen()
        ende = time.time() + 20
        while f._laeuft() and time.time() < ende:
            time.sleep(0.005)           # kein update(): der Takt uebernimmt das Ergebnis noch nicht
        self.assertFalse(f._laeuft(), "Der Faden ist zu Ende")
        self.assertTrue(f._beschaeftigt(), "Sein Ergebnis wartet noch darauf, vom Takt uebernommen zu werden")
        wartend = f._post.z["befunde"]
        gefragt = len(self.netz.gefragt)
        f.pruefen_starten()             # ein Start in dieser Luecke vermischte die Ergebnisse beider Laeufe
        self.assertEqual(gefragt, len(self.netz.gefragt))
        self.assertIs(wartend, f._post.z["befunde"])
        self.assertEqual("disabled", str(f.pruefen_knopf.cget("state")), "Der Knopf wartet auf den Takt")
        self.warten()
        self.assertFalse(f._beschaeftigt())
        self.assertEqual("normal", str(f.pruefen_knopf.cget("state")))


class AuswahlUndHolenTests(FensterTestBasis):

    def test_ankreuzen_zaehlt_und_beschriftet_den_knopf(self) -> None:
        f = self.oeffnen()
        self.warten()
        self.assertEqual("Herunterladen", f.holen_knopf.cget("text"))
        f._umschalten("elfldr")
        self.assertEqual("☑", self.zeile(f, "elfldr")["haken"])
        self.assertEqual({"elfldr"}, f.gewaehlt)
        text = f.holen_knopf.cget("text")
        self.assertTrue(text.startswith("Herunterladen: 1 ("), text)
        self.assertEqual("normal", str(f.holen_knopf.cget("state")))
        f._umschalten("elfldr")
        self.assertEqual("☐", self.zeile(f, "elfldr")["haken"])
        self.assertEqual("disabled", str(f.holen_knopf.cget("state")))

    def test_was_nur_gemeldet_wird_hat_keinen_haken(self) -> None:
        f = self.oeffnen()
        self.warten()
        for schluessel in ("7zip", "ftpsrv", "game-compressor", "appinst"):
            f._umschalten(schluessel)
            self.assertEqual(set(), f.gewaehlt, schluessel)
            self.assertEqual("", self.zeile(f, schluessel)["haken"], schluessel)

    def test_alle_neuen_und_abwaehlen(self) -> None:
        f = self.oeffnen()
        self.warten()
        f._alle_neuen()
        self.assertEqual({"elfldr", "pkgmgr"}, f.gewaehlt)
        self.assertTrue(f.holen_knopf.cget("text").startswith("Herunterladen: 2 ("))
        f._auswahl_aufheben()
        self.assertEqual(set(), f.gewaehlt)
        self.assertEqual("☐", self.zeile(f, "pkgmgr")["haken"])

    def test_ein_klick_auf_die_haken_spalte_schaltet_um(self) -> None:
        f = self.oeffnen()
        self.warten()
        f.liste.update_idletasks()
        f.liste.see("elfldr")
        _WURZEL.update()
        kasten = f.liste.bbox("elfldr", "#1")
        self.assertTrue(kasten, "Die Zeile ist nicht sichtbar")
        f.liste.event_generate("<Button-1>", x=kasten[0] + 5, y=kasten[1] + 5)
        _WURZEL.update()
        self.assertEqual({"elfldr"}, f.gewaehlt)
        namen = f.liste.bbox("elfldr", "name")
        f.liste.event_generate("<Button-1>", x=namen[0] + 5, y=namen[1] + 5)
        _WURZEL.update()
        self.assertEqual({"elfldr"}, f.gewaehlt, "Ein Klick auf den Namen waehlt nur die Zeile aus")

    def test_leertaste_schaltet_die_gewaehlte_zeile_um(self) -> None:
        f = self.oeffnen()
        self.warten()
        f.liste.selection_set("pkgmgr")
        f.liste.focus("pkgmgr")
        self.assertEqual("break", f._leertaste())
        self.assertEqual({"pkgmgr"}, f.gewaehlt)

    def test_kein_umschalten_waehrend_der_arbeit(self) -> None:
        self.netz = _TorNetz(releases=NEUE_FREIGABEN)
        f = self.oeffnen()
        f._umschalten("elfldr")
        f._alle_neuen()
        self.assertEqual(set(), f.gewaehlt)

    def test_herunterladen_legt_die_datei_ab_und_das_urteil_wird_aktuell(self) -> None:
        f = self.oeffnen()
        self.warten()
        f._umschalten("elfldr")
        f._herunterladen()
        self.assertEqual("disabled", str(f.holen_knopf.cget("state")))
        self.assertEqual("normal", str(f.abbrechen_knopf.cget("state")))
        self.warten()
        ziel = os.path.join(self.basis, wu.UNTERORDNER, "helloworld", "elfldr-ps5_v0.27.elf")
        self.assertEqual(inhalt("elfldr-ps5.elf"), Path(ziel).read_bytes())
        zeile = self.zeile(f, "elfldr")
        self.assertEqual(("0.27", "0.27", "Aktuell (geholt)", ""),
                         (zeile["lokal"], zeile["neu"], zeile["status"], zeile["haken"]))
        self.assertEqual({"pkgmgr"}, {b.werkzeug.schluessel for b in f.befunde if b.ladbar},
                        "Das zweite neue Werkzeug bleibt ladbar")
        self.assertEqual("Fertig: 1 Datei(en) geholt.", f.status_text())
        protokoll = f.protokoll.get("1.0", "end")
        self.assertIn("[Updates] Lade elfldr …", protokoll)
        self.assertIn("[Updates] Abgelegt: " + ziel, protokoll)
        self.assertIn("Werkzeug-Updates", protokoll)
        self.app._updates_geholt.assert_called_once()
        self.assertEqual(set(), f.gewaehlt)

    def test_nach_dem_holen_findet_das_programm_die_neue_datei(self) -> None:
        f = self.oeffnen()
        self.warten()
        self.assertTrue(self.app._konsole_payload_datei("pkgmgr*.elf").endswith("pkgmgr_v1.5.0.elf"))
        f._umschalten("pkgmgr")
        f._herunterladen()
        self.warten()
        pfad = self.app._konsole_payload_datei("pkgmgr*.elf")
        self.assertEqual(os.path.join(self.basis, wu.UNTERORDNER, "helloworld", "pkgmgr_v1.6.0.elf"), pfad)
        # Die Dienstetabelle zeigt die Fassung der Datei, die das Programm nimmt.
        from ps5_validator.utils import konsole_dienste
        self.assertEqual("1.6.0", konsole_dienste.version_aus_dateiname(pfad))

    def test_feste_payloads_bleiben_bei_der_mitgelieferten_datei(self) -> None:
        # elfldr, ftpsrv und klogsrv: Das Programm bleibt in Tabelle, Start und eigenen Abläufen bei der geprüften
        # Datei - eine geholte neuere liegt nur in der Schnellauswahl bereit.
        f = self.oeffnen()
        self.warten()
        f._umschalten("elfldr")
        f._herunterladen()
        self.warten()
        self.assertTrue(os.path.isfile(os.path.join(self.basis, wu.UNTERORDNER, "helloworld", "elfldr-ps5_v0.27.elf")))
        for muster in ("elfldr*.elf", "elfldr-ps5_v*.elf"):
            self.assertTrue(self.app._konsole_payload_datei(muster).endswith("elfldr-ps5_v0.26.elf"), muster)
        self.assertEqual("Aktuell (geholt)", self.zeile(f, "elfldr")["status"], "Das Fenster zeigt, was geholt ist")

    def test_beschaedigter_download_wird_nicht_abgelegt(self) -> None:
        f = self.oeffnen()
        self.warten()
        befund = next(b for b in f.befunde if b.werkzeug.schluessel == "elfldr")
        self.netz.verfaelscht.add(befund.teile[0].adresse)
        f._umschalten("elfldr")
        f._herunterladen()
        self.warten()
        self.assertFalse(os.path.exists(os.path.join(self.basis, wu.UNTERORDNER, "helloworld")))
        self.assertIn("SHA-256", f.protokoll.get("1.0", "end"))
        self.assertIn("1 Fehler", f.status_text())
        self.assertEqual("Neue Fassung", self.zeile(f, "elfldr")["status"], "Weiter ladbar")
        self.app._updates_geholt.assert_not_called()

    def test_ampr_wird_ueber_ampr_updates_abgelegt(self) -> None:
        self.app._updates_ampr_vorhanden = lambda: [("0.3.6.2", "no debug")]
        f = self.oeffnen()
        self.warten()
        ampr = self.zeile(f, "ampr-emu")
        self.assertEqual("Neue Fassung", ampr["status"])
        self.assertEqual("0.4.2.1", ampr["neu"])
        f._umschalten("ampr-emu")
        f._herunterladen()
        self.warten()
        sprx = [p for p in Path(self.basis, "AMPR EMU updates").rglob("libSceAmpr.sprx")]
        self.assertGreaterEqual(len(sprx), 3)
        self.assertIn("[Updates] AMPR EMU:", f.protokoll.get("1.0", "end"))

    def test_abbrechen_beim_holen(self) -> None:
        f = self.oeffnen()
        self.warten()
        f._umschalten("elfldr")
        original = self.netz.laden
        gate = threading.Event()

        def laden(adresse, pfad, fortschritt=None, abbruch=None):
            gate.wait(10)
            return original(adresse, pfad, fortschritt, abbruch)

        self.netz.laden = laden
        f._herunterladen()
        f._abbrechen()
        gate.set()
        self.warten()
        self.assertEqual("Abgebrochen.", f.status_text())
        self.assertFalse(os.path.exists(os.path.join(self.basis, wu.UNTERORDNER, "helloworld")))


class EinzelheitenTests(FensterTestBasis):

    def _text(self, f, schluessel: str) -> str:
        f._details_zeigen(schluessel)
        return f.details.get("1.0", "end").strip()

    def test_einzelheiten_einer_neuen_fassung(self) -> None:
        f = self.oeffnen()
        self.warten()
        text = self._text(f, "elfldr")
        self.assertIn("Mitgeliefert: 0.26", text)
        self.assertIn("Freigabe: 0.27 vom 2026-10-12", text)
        self.assertIn("Dateien: elfldr-ps5_v0.27.elf (", text)
        self.assertIn("mitgelieferten Datei", text, "Der Hinweis zu den festen Namen")

    def test_einzelheiten_eines_hinweis_werkzeugs(self) -> None:
        f = self.oeffnen()
        self.warten()
        text = self._text(f, "7zip")
        self.assertIn("Freigabe: 26.04", text)
        self.assertIn("Handarbeit", text)
        self.assertNotIn("Dateien:", text)

    def test_ohne_auswahl_steht_ein_hinweis(self) -> None:
        f = self.oeffnen(automatisch=False)
        self.assertEqual("Einen Eintrag wählen, um Einzelheiten zu sehen.", self._text(f, ""))

    def test_ein_klick_auf_eine_kopfzeile_zeigt_keine_einzelheiten(self) -> None:
        f = self.oeffnen()
        self.warten()
        f.liste.selection_set(self.uf.GRUPPEN_ZEILE + wu.GRUPPE_PAYLOAD)
        f._zeile_gewaehlt()
        self.assertEqual("Einen Eintrag wählen, um Einzelheiten zu sehen.", f.details.get("1.0", "end").strip())
        self.assertEqual("", f._aktuelle_zeile())

    def test_freigabe_seite_und_ordner(self) -> None:
        f = self.oeffnen()
        self.warten()
        self.assertEqual("disabled", str(f.seite_knopf.cget("state")))
        f.liste.selection_set("elfldr")
        f._zeile_gewaehlt()
        self.assertEqual("normal", str(f.seite_knopf.cget("state")))
        with mock.patch.object(self.uf.webbrowser, "open") as oeffnen:
            f._seite_oeffnen()
        oeffnen.assert_called_once_with("https://github.com/ps5-payload-dev/elfldr/releases/tag/v0.27")
        with mock.patch.object(self.uf.plattform, "datei_oeffnen") as ordner:
            f._ordner_oeffnen()
        ordner.assert_called_once_with(os.path.join(self.basis, wu.UNTERORDNER))
        self.assertTrue(os.path.isdir(os.path.join(self.basis, wu.UNTERORDNER)))

    def test_scheitern_seite_oder_ordner_steht_es_im_protokoll(self) -> None:
        f = self.oeffnen()
        self.warten()
        ablage = os.path.join(self.basis, wu.UNTERORDNER)
        f.liste.selection_set("elfldr")
        f._zeile_gewaehlt()
        with mock.patch.object(self.uf.webbrowser, "open", return_value=False):
            f._seite_oeffnen()
        with mock.patch.object(self.uf.plattform, "datei_oeffnen", return_value=False):
            f._ordner_oeffnen()
        with mock.patch.object(self.uf.os, "makedirs", side_effect=OSError("kein Zugriff")), \
                mock.patch.object(self.uf.plattform, "datei_oeffnen") as ordner:
            f._ordner_oeffnen()
        ordner.assert_not_called()
        protokoll = f.protokoll.get("1.0", "end")
        self.assertIn("[Updates] Die Seite ließ sich nicht öffnen: "
                      "https://github.com/ps5-payload-dev/elfldr/releases/tag/v0.27", protokoll)
        self.assertEqual(2, protokoll.count("[Updates] Der Ordner ließ sich nicht öffnen: " + ablage), protokoll)

    def test_ein_geglueckter_aufruf_schreibt_nichts_ins_protokoll(self) -> None:
        f = self.oeffnen()
        self.warten()
        f.liste.selection_set("elfldr")
        f._zeile_gewaehlt()
        vorher = f.protokoll.get("1.0", "end")
        with mock.patch.object(self.uf.webbrowser, "open", return_value=True), \
                mock.patch.object(self.uf.plattform, "datei_oeffnen", return_value=True):
            f._seite_oeffnen()
            f._ordner_oeffnen()
        self.assertEqual(vorher, f.protokoll.get("1.0", "end"))

    def test_groesse_text(self) -> None:
        self.assertEqual("0 B", self.uf.groesse_text(0))
        self.assertEqual("512 B", self.uf.groesse_text(512))
        self.assertEqual("1,5 KB", self.uf.groesse_text(1536))
        self.assertEqual("24,5 MB", self.uf.groesse_text(int(24.5 * 1024 ** 2)))
        self.assertEqual("1,0 GB", self.uf.groesse_text(1024 ** 3))
        self.assertEqual("0 B", self.uf.groesse_text(-5))


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class KnopfAufDerKonsolenseiteTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        # Die Seite entsteht erst beim ersten Zeigen der Ansicht KONSOLE.
        cls.app._ansicht_setzen("konsole")
        cls.app._konsole_seite_setzen("uebersicht")
        _WURZEL.update()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app._konsole_seite_setzen("uebersicht")
        cls.app._ansicht_setzen("umwandeln")

    def test_der_knopf_steht_rechts_oben_im_kopf_der_seite(self) -> None:
        knopf = self.app._konsole_tafel_updates_knopf
        self.assertEqual("right", knopf.pack_info()["side"])
        self.assertEqual(self.app._konsole_tafel_kopf, knopf.master)
        self.assertEqual("Updates", knopf.cget("text"))

    def test_der_knopf_gehoert_nicht_zu_den_gesperrten_waehrend_ein_dienst_laeuft(self) -> None:
        self.assertNotIn(self.app._konsole_tafel_updates_knopf, self.app._konsole_tafel_knoepfe)

    def test_der_knopf_steht_nicht_in_der_knopfreihe_unter_der_tabelle(self) -> None:
        # Dort wurde es bei der Mindestbreite eng (vier Knoepfe 785 px, die Reihe 704): Die Reihe bricht um, und
        # "Updates" hat seinen Platz, der nie vom Umbruch abhaengt.
        reihe = self.app._konsole_tafel_knopfreihe
        self.assertNotIn(self.app._konsole_tafel_updates_knopf, reihe.winfo_children())
        self.assertEqual(4, len(reihe.winfo_children()), "Starten, Favoriten, Weboberflaeche, QR-Code")

    def test_die_beschriftung_folgt_dem_sprachwechsel(self) -> None:
        knopf = self.app._konsole_tafel_updates_knopf
        eintraege = [schluessel for widget, schluessel, _attr, _kw in self.app._i18n_widgets if widget is knopf]
        self.assertEqual(["dienste.updates_button"], eintraege)
        self.assertEqual("Updates", STRINGS["dienste.updates_button"]["en"])

    def test_der_knopf_oeffnet_und_schliesst_das_fenster(self) -> None:
        from ps5_validator.ui import updates_fenster
        with tempfile.TemporaryDirectory() as basis, \
                mock.patch.object(wu, "Netz", FakeNetz), \
                mock.patch.object(wu.urllib.request, "urlopen") as urlopen:
            self.app._updates_basis = lambda: basis
            self.addCleanup(self.app.__dict__.pop, "_updates_basis", None)
            self.app._konsole_tafel_updates_knopf.invoke()
            fenster = getattr(self.app, updates_fenster.FENSTER_ATTRIBUT)
            self.assertTrue(fenster.win.winfo_exists())
            ende = time.time() + 20
            while time.time() < ende and fenster._arbeit is not None:
                fenster._takt_arbeiten()
                _WURZEL.update()
                time.sleep(0.01)
            self.assertIsNone(fenster._arbeit)
            self.app._konsole_tafel_updates_knopf.invoke()           # zweiter Druck schliesst
            _WURZEL.update()
            self.assertFalse(_WURZEL.tk.call("winfo", "exists", str(fenster.win)) == 1)
            urlopen.assert_not_called()


class QuelltextTests(unittest.TestCase):
    """Texte und Aufrufe des Fensters - gemessen am Syntaxbaum, nicht am Auge."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.quelle = (PROJEKT / "ps5_validator" / "ui" / "updates_fenster.py").read_text(encoding="utf-8")
        cls.baum = ast.parse(cls.quelle)

    def test_jeder_textschluessel_des_fensters_ist_uebersetzt(self) -> None:
        schluessel = set(re.findall(r'"(updates\.[a-z_]+)"', self.quelle)) | {"dienste.updates_button"}
        fehlen = sorted(s for s in schluessel if s not in STRINGS or not (STRINGS[s].get("de") and STRINGS[s].get("en")))
        self.assertEqual([], fehlen)
        self.assertGreater(len(schluessel), 25)

    def test_jeder_zugeordnete_schluessel_ist_uebersetzt(self) -> None:
        from ps5_validator.ui import updates_fenster as uf
        for tabelle in (uf.STATUS_TEXTE, uf.MELDUNG_TEXTE, uf.GRUPPEN_TEXTE):
            for schluessel in tabelle.values():
                self.assertIn(schluessel, STRINGS)
        for status in (wu.STATUS_NICHT_GEPRUEFT, wu.STATUS_NEU, wu.STATUS_NEU_HINWEIS, wu.STATUS_AKTUELL,
                       wu.STATUS_NEUER, wu.STATUS_UNKLAR, wu.STATUS_FEHLER, wu.STATUS_OHNE_QUELLE):
            self.assertIn(status, uf.STATUS_TEXTE)
        for meldung in (wu.MELDUNG_NETZ, wu.MELDUNG_LIMIT, wu.MELDUNG_NICHT_GEFUNDEN, wu.MELDUNG_ANTWORT,
                        wu.MELDUNG_ABGEBROCHEN, wu.MELDUNG_KEINE_FREIGABE, wu.MELDUNG_KEINE_DATEI,
                        wu.MELDUNG_LOKAL_UNLESBAR, wu.MELDUNG_FASSUNG_UNKLAR):
            self.assertIn(meldung, uf.MELDUNG_TEXTE)
        for gruppe in wu.GRUPPEN:
            self.assertIn(gruppe, uf.GRUPPEN_TEXTE)

    def test_die_vorgemerkten_protokollzeilen_tragen_genau_ihre_platzhalter(self) -> None:
        platz = re.compile(r"\{([A-Za-z_][A-Za-z_0-9]*)[^{}]*\}")
        stellen = 0
        for knoten in ast.walk(self.baum):
            if not (isinstance(knoten, ast.Tuple) and len(knoten.elts) == 2
                    and isinstance(knoten.elts[0], ast.Constant) and isinstance(knoten.elts[0].value, str)
                    and knoten.elts[0].value.startswith("updates.log_") and isinstance(knoten.elts[1], ast.Dict)):
                continue
            schluessel = knoten.elts[0].value
            gegeben = {k.value for k in knoten.elts[1].keys if isinstance(k, ast.Constant)}
            gebraucht = set()
            for sprache in ("de", "en"):
                gebraucht |= set(platz.findall(STRINGS[schluessel][sprache]))
            self.assertEqual(gebraucht, gegeben, schluessel)
            stellen += 1
        self.assertGreaterEqual(stellen, 5)

    def test_das_fenster_fasst_im_arbeitsfaden_kein_tk_an_und_uebersetzt_nichts(self) -> None:
        for name in ("_pruefen_arbeit", "_holen_arbeit", "melden", "abliefern"):
            funktion = next(n for n in ast.walk(self.baum) if isinstance(n, ast.FunctionDef) and n.name == name)
            text = ast.get_source_segment(self.quelle, funktion)
            for verboten in (".configure(", ".insert(", ".delete(", ".set(", "self.t(", "self._status(", "self._protokoll(",
                             "self.liste", "self.win", "messagebox", "tk."):
                self.assertNotIn(verboten, text, "%s fasst im Arbeitsfaden %s an" % (name, verboten))

    def test_die_faeden_bekommen_nie_das_fenster(self) -> None:
        # Faellt der letzte Verweis auf das Fenster in einem Arbeitsfaden, ruft dort tk.Variable.__del__ Tcl auf
        # ("main thread is not in main loop") - gemessen an den Tests dieses Fensters.
        klasse = next(k for k in self.baum.body if isinstance(k, ast.ClassDef) and k.name == "UpdatesFenster")
        methoden = {f.name for f in klasse.body if isinstance(f, ast.FunctionDef)}
        faeden = [k for k in ast.walk(self.baum) if isinstance(k, ast.Call)
                  and getattr(k.func, "attr", "") == "Thread"]
        self.assertEqual(2, len(faeden), "Pruefen und Holen")
        for aufruf in faeden:
            ziel = next(kw.value for kw in aufruf.keywords if kw.arg == "target")
            self.assertIsInstance(ziel, ast.Name, "Das Ziel eines Fadens ist eine Funktion, keine Methode des Fensters")
            args = next(kw.value for kw in aufruf.keywords if kw.arg == "args")
            for element in args.elts:
                self.assertFalse(isinstance(element, ast.Name) and element.id == "self",
                                 "Ein Faden bekommt self - und damit das Fenster")
                gebunden = (isinstance(element, ast.Attribute) and isinstance(element.value, ast.Name)
                            and element.value.id == "self" and element.attr in methoden)
                self.assertFalse(gebunden, "Ein Faden bekommt eine Methode des Fensters - und damit das Fenster")

    def test_das_fenster_benutzt_keine_tk_variable(self) -> None:
        for knoten in ast.walk(self.baum):
            if isinstance(knoten, ast.Call):
                name = getattr(knoten.func, "attr", "") or getattr(knoten.func, "id", "")
                self.assertNotIn(name, ("StringVar", "IntVar", "BooleanVar", "DoubleVar"), "tk-Variable im Fenster")

    def test_das_fenster_ruft_nirgends_urlopen(self) -> None:
        self.assertNotIn("urlopen", self.quelle)
        self.assertNotIn("urllib", self.quelle, "Das Netz steckt allein in werkzeug_updates.Netz")


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class AnbindungTests(unittest.TestCase):
    """Die Stellen im Hauptprogramm, die geholte Dateien kennen muessen."""

    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        self.wurzel = tempfile.mkdtemp(prefix="an_wurzel_")
        self.basis = tempfile.mkdtemp(prefix="an_basis_")
        self.addCleanup(shutil.rmtree, self.wurzel, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.basis, ignore_errors=True)
        self.app._updates_basis = lambda: self.basis
        self.app._mitgeliefert_finden = lambda rel, datei=False: os.path.join(self.wurzel, rel)
        self.addCleanup(self.app.__dict__.pop, "_updates_basis", None)
        self.addCleanup(self.app.__dict__.pop, "_mitgeliefert_finden", None)

    def _legen(self, ort: str, *namen: str, geholt: bool = False) -> str:
        ordner = os.path.join(self.basis, wu.UNTERORDNER, ort) if geholt else os.path.join(self.wurzel, ort)
        os.makedirs(ordner, exist_ok=True)
        for name in namen:
            Path(ordner, name).write_bytes(b"x")
        return ordner

    def test_payload_datei_nimmt_die_hoechste_fassung_beider_ordner(self) -> None:
        hello = self._legen("helloworld", "websrv-ps5_v0.33.elf", "websrv-ps5_v0.34.elf")
        self.assertEqual(os.path.join(hello, "websrv-ps5_v0.34.elf"),
                         self.app._konsole_payload_datei("websrv-ps5*.elf"))
        neu = self._legen("helloworld", "websrv-ps5_v0.35.elf", geholt=True)
        self.assertEqual(os.path.join(neu, "websrv-ps5_v0.35.elf"), self.app._konsole_payload_datei("websrv-ps5*.elf"))

    def test_bei_den_festen_payloads_gilt_nur_der_mitgelieferte_ordner(self) -> None:
        hello = self._legen("helloworld", "ftpsrv-ps5_v0.21.1.elf", "ftpsrv-ps5_v1.16-ng-stable.elf",
                            "elfldr-ps5_v0.26.elf", "klogsrv-ps5_v0.9.elf")
        self._legen("helloworld", "ftpsrv-ps5_v1.20.elf", "elfldr-ps5_v0.27.elf", "klogsrv-ps5_v0.10.elf", geholt=True)
        for muster, soll in (("ftpsrv-ps5*.elf", "ftpsrv-ps5_v1.16-ng-stable.elf"),
                             ("elfldr*.elf", "elfldr-ps5_v0.26.elf"), ("klogsrv*.elf", "klogsrv-ps5_v0.9.elf")):
            self.assertEqual(os.path.join(hello, soll), self.app._konsole_payload_datei(muster), muster)

    def test_die_festen_namen_des_programms_haengen_an_festen_eintraegen(self) -> None:
        # Waechter: Was das Programm in eigenen Ablaeufen beim Namen nimmt, darf eine geholte Datei nie ersetzen -
        # sonst liefen Tabelle, Start und diese Ablaeufe auseinander.
        import re
        from ps5_validator.utils import konsole_dienste as kd
        from ps5_validator.utils import payload_versand
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        namen = [payload_versand.ELFLDR_NAME,
                 re.search(r'_FTPSRV_PAYLOAD_NAME = "([^"]+)"', quelle).group(1),
                 re.search(r'_KLOG_PAYLOAD = "([^"]+)"', quelle).group(1)]
        import fnmatch
        for name in namen:
            eintraege = [d for d in kd.KATALOG if d.payload_muster and fnmatch.fnmatchcase(name, d.payload_muster)]
            self.assertTrue(eintraege, "Kein Katalogeintrag trifft %s" % name)
            for d in eintraege:
                self.assertTrue(wu.ist_fest(d.payload_muster), "%s (%s) ist nicht fest" % (d.schluessel, name))

    def test_payload_datei_ohne_muster_und_ohne_treffer(self) -> None:
        self._legen("helloworld", "a_v1.elf")
        self.assertEqual("", self.app._konsole_payload_datei(""))
        self.assertEqual("", self.app._konsole_payload_datei("gibtesnicht*.elf"))

    def test_payload_datei_findet_eine_geholte_auch_ohne_mitgelieferten_ordner(self) -> None:
        neu = self._legen("helloworld", "a_v2.elf", geholt=True)
        self.assertEqual(os.path.join(neu, "a_v2.elf"), self.app._konsole_payload_datei("a_v*.elf"))

    def test_die_neue_sortierung_waehlt_im_echten_ordner_dieselbe_datei_wie_die_alte(self) -> None:
        # Die Regressionsprobe: Fuer jedes Muster des Katalogs wird im echten helloworld/ dieselbe Datei gewaehlt
        # wie vorher (``_webkit_versionsschluessel``) - die neue Ordnung ist eine Obermenge.
        from ps5_validator.utils import konsole_dienste
        echt = sorted(n.name for n in (PROJEKT / "helloworld").iterdir() if n.is_file())
        alt = self.haupt.PS5ConverterGUI._webkit_versionsschluessel
        muster_liste = {m for d in konsole_dienste.KATALOG for m in (d.payload_muster, d.datei_muster) if m}
        muster_liste |= {w.muster for w in wu.WERKZEUGE if w.muster and w.ordner == wu.ORT_PAYLOADS}
        gemessen = 0
        for muster in sorted(muster_liste):
            treffer = [n for n in echt if re.fullmatch(wu.fnmatch.translate(muster), n, re.IGNORECASE)]
            if len(treffer) < 2:
                continue
            self.assertEqual(max(treffer, key=alt), max(treffer, key=wu.datei_schluessel), muster)
            gemessen += 1
        self.assertGreaterEqual(gemessen, 2, "ftpsrv und OnionHEN liegen mehrfach im Ordner")

    def test_webkit_fassungen_kommen_aus_beiden_ordnern(self) -> None:
        mitgeliefert = self._legen(wu.ORT_WEBKIT, "webkit-autoloader-host_v0.6.1.exe",
                                   "webkit-autoloader-host_v0.6.1.py", "webkit-autoloader-installer_v0.6.1.elf")
        self.app._webkit_ordner = lambda: mitgeliefert
        self.addCleanup(self.app.__dict__.pop, "_webkit_ordner", None)
        self.assertEqual(["0.6.1"], self.app._webkit_fassungen_liste())
        geholt = self._legen(wu.ORT_WEBKIT, "webkit-autoloader-host_v0.7.0.exe", "webkit-autoloader-host_v0.7.0.py",
                             "webkit-autoloader-installer_v0.7.0.elf", geholt=True)
        self.assertEqual(["0.7.0", "0.6.1"], self.app._webkit_fassungen_liste())
        self.assertEqual(os.path.join(geholt, "webkit-autoloader-installer_v0.7.0.elf"),
                         self.app._webkit_datei("elf"), "Ohne Wahl gewinnt die hoechste")
        self.assertEqual(os.path.join(mitgeliefert, "webkit-autoloader-host_v0.6.1.exe"),
                         self.app._webkit_datei("exe", "0.6.1"))
        self.assertEqual(os.path.join(geholt, "webkit-autoloader-host_v0.7.0.py"),
                         self.app._webkit_datei("py", "0.7.0"))

    def test_webkit_ohne_geholte_dateien_wie_bisher(self) -> None:
        mitgeliefert = self._legen(wu.ORT_WEBKIT, "webkit-autoloader-installer_v0.5.2.elf")
        self.app._webkit_ordner = lambda: mitgeliefert
        self.addCleanup(self.app.__dict__.pop, "_webkit_ordner", None)
        self.assertEqual(["0.5.2"], self.app._webkit_fassungen_liste())
        self.assertEqual(os.path.join(mitgeliefert, "webkit-autoloader-installer_v0.5.2.elf"),
                         self.app._webkit_datei("elf"))
        self.app._webkit_ordner = lambda: ""
        self.assertEqual([], self.app._webkit_fassungen_liste())
        self.assertEqual("", self.app._webkit_datei("elf"))

    def test_gleichnamige_webkit_datei_gilt_aus_dem_mitgelieferten_ordner(self) -> None:
        mitgeliefert = self._legen(wu.ORT_WEBKIT, "webkit-autoloader-installer_v0.6.1.elf")
        self._legen(wu.ORT_WEBKIT, "webkit-autoloader-installer_v0.6.1.elf", geholt=True)
        self.app._webkit_ordner = lambda: mitgeliefert
        self.addCleanup(self.app.__dict__.pop, "_webkit_ordner", None)
        self.assertEqual(os.path.join(mitgeliefert, "webkit-autoloader-installer_v0.6.1.elf"),
                         self.app._webkit_datei("elf"))

    def test_die_dienstetabelle_wird_nach_dem_holen_neu_gefuellt(self) -> None:
        gefuellt = []
        self.app._konsole_tafel_letzte = ["uebersicht"]
        self.addCleanup(self.app.__dict__.pop, "_konsole_tafel_letzte", None)
        with mock.patch.object(self.app, "_konsole_tafel_fuellen", side_effect=gefuellt.append):
            self.app._updates_geholt()
        self.assertEqual([["uebersicht"]], gefuellt)
        del self.app._konsole_tafel_letzte
        with mock.patch.object(self.app, "_konsole_tafel_fuellen") as nichts:
            self.app._updates_geholt()
        nichts.assert_not_called()

    def test_die_ampr_hilfen_des_programms(self) -> None:
        paare = self.app._updates_ampr_vorhanden()
        self.assertTrue(all(isinstance(p, tuple) and len(p) == 2 for p in paare))
        self.assertTrue(self.app._updates_ampr_ordner().endswith("AMPR EMU updates"))

    def test_der_einstellungsordner_folgt_der_umlenkung(self) -> None:
        self.app.__dict__.pop("_updates_basis", None)
        self.assertEqual(os.environ["PS5CONV_KONFIGORDNER"], self.app._updates_basis())


if __name__ == "__main__":
    unittest.main()
