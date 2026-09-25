# -*- coding: utf-8 -*-
"""Die Bibliothek als Seite der Ansicht KONSOLE (25.09.2026).

Wuensche des Nutzers, die hier festgehalten werden:

* "den Knopf oben (Bibliothek) in die neue Ansicht (Konsole) anstatt den
  Klog-Knopf": kein Knopf BIBLIOTHEK mehr in der Titelleiste; in der Ansicht
  KONSOLE steht "3. Bibliothek" an der Stelle des Kernel-Protokolls, KLOG
  bleibt oben.
* "die Funktionen vom Knopf holen und dem Knopf Senden (Spiel) in die
  Bibliothek": "Spiel holen" und "Zurueckspielen" sind in ihr aufgegangen -
  sie holt und sendet jetzt auch Ordner, startet den App-Dumper und oeffnet
  den Dateimanager der PS5.
* "Rechts als Seite": wie ActRemoteLink, kein eigenes Fenster.
* Aus dem "PKG Viewer" (Loopayeh, MIT; nur Ideen): mehr Angaben mit
  Firmware-Abgleich, Update-Vergleich, einheitlich umbenennen samt
  Rueckgaengig, Titelbild speichern/kopieren, Angaben kopieren.

Dazu zwei Befunde, die beim Bauen auffielen und hier bewacht werden: Die
Titelleiste faltete nach einem Sprachwechsel nicht neu, und die Tk-Wurzel
der Tests hatte je nach Reihenfolge 96 statt 120 dpi (conftest.py).
"""
from __future__ import annotations

import ast
import json
import os
import string
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("bibliothek_seite")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import bibliothek as bib           # noqa: E402
from ps5_validator.utils import plattform                   # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False

HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"
_BAUM: list = []


def _baum() -> ast.Module:
    if not _BAUM:
        _BAUM.append(ast.parse(HAUPTDATEI.read_text(encoding="utf-8")))
    return _BAUM[0]


def _methode(name: str) -> ast.FunctionDef:
    klasse = next(k for k in _baum().body
                  if isinstance(k, ast.ClassDef) and k.name == "PS5ConverterGUI")
    return next(k for k in klasse.body
                if isinstance(k, ast.FunctionDef) and k.name == name)


def _innere(aussen: str, innen: str) -> ast.FunctionDef:
    return next(k for k in ast.walk(_methode(aussen))
                if isinstance(k, ast.FunctionDef) and k.name == innen)


def _aufgerufen(knoten) -> set:
    namen = set()
    for k in ast.walk(knoten):
        if isinstance(k, ast.Call):
            ziel = k.func
            namen.add(ziel.attr if isinstance(ziel, ast.Attribute)
                      else getattr(ziel, "id", ""))
    return namen


def _platzhalter(text: str) -> set:
    return {feld for _v, feld, _f, _k in string.Formatter().parse(text) if feld}


def _eintrag(pfad: str, **meta) -> dict:
    angaben = {"title": "Elden Ring", "title_id": "PPSA04610",
               "version": "01.017.000",
               "content_id": "EP0700-PPSA04610_00-ELDENRING0000000"}
    angaben.update(meta)
    return {"path": pfad, "kind": "folder" if os.path.isdir(pfad) else "ffpfsc",
            "meta": angaben, "size": None}


def _schleife_bis(bedingung, grenze: float = 10.0) -> bool:
    """Eine echte Hauptschleife, bis ``bedingung`` gilt - Rueckrufe aus
    Faeden kommen nur an, solange mainloop laeuft."""
    ende = time.monotonic() + grenze

    def _takt() -> None:
        if bedingung() or time.monotonic() > ende:
            _WURZEL.quit()
        else:
            _WURZEL.after(20, _takt)

    _WURZEL.after(0, _takt)
    _WURZEL.mainloop()
    return bool(bedingung())


# ---------------------------------------------------------------------------
# Die Logik im Modul bibliothek - ohne Tk
# ---------------------------------------------------------------------------

class NamenUndFassungenTests(unittest.TestCase):

    def test_region_kommt_zuerst_aus_der_content_id(self) -> None:
        self.assertEqual("EU", bib.region_kurz({"content_id": "EP0700-PPSA04610_00-X"}))
        self.assertEqual("US", bib.region_kurz({"content_id": "UP9000-PPSA26344_00-X",
                                                "region": "Europa"}))
        self.assertEqual("EU", bib.region_kurz({"region": "Europa"}))
        self.assertEqual("JP", bib.region_kurz({"region": "JPN"}))
        self.assertEqual("", bib.region_kurz({"region": "–"}))

    def test_fassung_kurz(self) -> None:
        self.assertEqual("1.8.0", bib.fassung_kurz("01.008.000"))
        self.assertEqual("4.40.100", bib.fassung_kurz("04.040.100"))
        self.assertEqual("1.0 beta", bib.fassung_kurz("1.0 beta"))

    def test_fassungen_werden_als_zahlen_verglichen(self) -> None:
        self.assertEqual(-1, bib.fassung_vergleichen("01.008.000", "01.010.000"))
        self.assertEqual(0, bib.fassung_vergleichen("1.8", "01.008.000"))
        self.assertEqual(1, bib.fassung_vergleichen("01.018.000", "01.017.000"))
        self.assertIsNone(bib.fassung_vergleichen("", "01.000.000"))

    def test_firmware_in_beiden_schreibweisen(self) -> None:
        self.assertEqual((10, 0), bib.firmware_teile("10.00.00.00"))
        self.assertEqual((9, 0), bib.firmware_teile("9.00"))
        self.assertEqual((12, 0), bib.firmware_teile("12000020"))
        self.assertEqual((10, 50), bib.firmware_teile("0x1050000000000000"))
        self.assertIsNone(bib.firmware_teile("–"))
        self.assertEqual("13.00", bib.firmware_kurz("13.00.00.00"))
        self.assertEqual("", bib.firmware_kurz(""))

    def test_firmware_vergleich_sagt_wann_backport_noetig_ist(self) -> None:
        self.assertEqual(1, bib.firmware_vergleichen("13.00.00.00", "12000020"))
        self.assertEqual(-1, bib.firmware_vergleichen("09.00.00.00", "12000020"))
        self.assertEqual(0, bib.firmware_vergleichen("12.00", "12000020"))
        self.assertIsNone(bib.firmware_vergleichen("13.00.00.00", ""))

    def test_die_vier_namensformen(self) -> None:
        angaben = _eintrag("x")["meta"]
        erwartet = {
            "titel_kennung_fassung_region": "Elden Ring - PPSA04610 - v1.17.0 - EU",
            "kennung_titel_fassung": "PPSA04610 Elden Ring (01.017.000)",
            "kennung_titel": "PPSA04610 Elden Ring",
            "kennung": "PPSA04610",
        }
        self.assertEqual(tuple(erwartet), bib.NAMENSFORMEN)
        for form, name in erwartet.items():
            with self.subTest(form=form):
                self.assertEqual(name, bib.neuer_name(angaben, form))

    def test_ohne_title_id_gibt_es_keinen_namen(self) -> None:
        self.assertEqual("", bib.neuer_name({"title": "Nur ein Titel"},
                                            "titel_kennung_fassung_region"))
        self.assertEqual("", bib.neuer_name({"title_id": "–"}, "kennung"))

    def test_verbotene_zeichen_fallen_weg(self) -> None:
        name = bib.neuer_name({"title": 'Tom: "Ein" Spiel?', "title_id": "PPSA00001"},
                              "kennung_titel")
        self.assertEqual("PPSA00001 Tom Ein Spiel", name)


class UmbenennenTests(unittest.TestCase):

    def setUp(self) -> None:
        self._ordner = tempfile.TemporaryDirectory()
        self.addCleanup(self._ordner.cleanup)
        self.basis = self._ordner.name
        self.protokolle = os.path.join(self.basis, "protokolle")

    def _datei(self, name: str) -> str:
        pfad = os.path.join(self.basis, name)
        Path(pfad).write_bytes(b"abbild")
        return pfad

    def test_der_plan_kennt_alle_zustaende(self) -> None:
        bereit = self._datei("elden.ffpfsc")
        gleich = self._datei("Elden Ring - PPSA04610 - v1.17.0 - EU.ffpkg")
        zweites = self._datei("elden_kopie.ffpfsc")
        ohne = self._datei("ohne.ffpfsc")
        belegt = self._datei("stray.exfat")
        self._datei("Stray - PPSA02100 - v1.5.0 - US.exfat")
        ordner = os.path.join(self.basis, "dump")
        os.makedirs(ordner)
        eintraege = [
            _eintrag(bereit),
            _eintrag(gleich),
            _eintrag(zweites),
            _eintrag(ohne, title_id=""),
            _eintrag(belegt, title="Stray", title_id="PPSA02100", version="01.005.000",
                     content_id="UP4040-PPSA02100_00-X"),
            dict(_eintrag("/mnt/usb0/Spiel.ffpfsc"), ps5=True),
            _eintrag(os.path.join(self.basis, "weg.ffpfsc")),
            _eintrag(ordner, title="Astro Bot", title_id="PPSA12345",
                     version="01.020.000", content_id="EP9000-PPSA12345_00-X"),
        ]
        plan = bib.umbenennen_planen(eintraege, "titel_kennung_fassung_region")
        zustaende = [z["zustand"] for z in plan]
        self.assertEqual([bib.BEREIT, bib.GLEICH, bib.DOPPELT, bib.OHNE_KENNUNG,
                          bib.ZIEL_VORHANDEN, bib.AUF_KONSOLE, bib.FEHLT, bib.BEREIT],
                         zustaende)
        self.assertEqual("Elden Ring - PPSA04610 - v1.17.0 - EU.ffpfsc",
                         os.path.basename(plan[0]["neu"]))
        self.assertEqual("Astro Bot - PPSA12345 - v1.20.0 - EU",
                         os.path.basename(plan[7]["neu"]),
                         "Ein Ordner bekommt keine Endung.")

    def test_nur_die_schreibweise_anders_ist_bereit(self) -> None:
        klein = self._datei("ppsa04610.ffpfsc")
        plan = bib.umbenennen_planen([_eintrag(klein)], "kennung")
        self.assertEqual(bib.BEREIT, plan[0]["zustand"])

    def test_ausfuehren_und_rueckgaengig(self) -> None:
        alt = self._datei("elden.ffpfsc")
        plan = bib.umbenennen_planen([_eintrag(alt)], "kennung_titel")
        ergebnis = bib.umbenennen_ausfuehren(plan, self.protokolle)
        neu = os.path.join(self.basis, "PPSA04610 Elden Ring.ffpfsc")
        self.assertEqual([(alt, neu)], ergebnis["erledigt"])
        self.assertTrue(os.path.exists(neu))
        self.assertFalse(os.path.exists(alt))
        liste = bib.protokolle(self.protokolle)
        self.assertEqual([ergebnis["protokoll"]], liste)
        with open(liste[0], encoding="utf-8") as datei:
            self.assertEqual([[alt, neu]], json.load(datei)["paare"])
        zurueck = bib.rueckgaengig(liste[0])
        self.assertEqual([(neu, alt)], zurueck["erledigt"])
        self.assertTrue(os.path.exists(alt))
        self.assertEqual([], bib.protokolle(self.protokolle),
                         "Ein erledigtes Protokoll wird nicht noch einmal angeboten.")

    def test_abgewaehlte_zeilen_bleiben_wie_sie_sind(self) -> None:
        alt = self._datei("elden.ffpfsc")
        plan = bib.umbenennen_planen([_eintrag(alt)], "kennung")
        plan[0]["gewaehlt"] = False
        ergebnis = bib.umbenennen_ausfuehren(plan, self.protokolle)
        self.assertEqual([], ergebnis["erledigt"])
        self.assertTrue(os.path.exists(alt))
        self.assertEqual("", ergebnis["protokoll"])

    def test_ein_spaeter_aufgetauchtes_ziel_wird_nicht_ueberschrieben(self) -> None:
        alt = self._datei("elden.ffpfsc")
        plan = bib.umbenennen_planen([_eintrag(alt)], "kennung")
        dazwischen = self._datei("PPSA04610.ffpfsc")
        Path(dazwischen).write_bytes(b"fremd")
        ergebnis = bib.umbenennen_ausfuehren(plan, self.protokolle)
        self.assertEqual([(alt, bib.ZIEL_VORHANDEN)], ergebnis["fehler"])
        self.assertEqual(b"fremd", Path(dazwischen).read_bytes())


class BildspeicherAngabenTests(unittest.TestCase):

    def setUp(self) -> None:
        self._ordner = tempfile.TemporaryDirectory()
        self.addCleanup(self._ordner.cleanup)
        self.speicher = bib.Bildspeicher(os.path.join(self._ordner.name, "cover"))
        self.datei = os.path.join(self._ordner.name, "spiel.ffpfsc")
        Path(self.datei).write_bytes(b"x")

    def test_angaben_allein_heissen_nicht_ohne_bild(self) -> None:
        self.speicher.angaben_schreiben(self.datei, {"required_firmware": "10.00.00.00"})
        self.assertEqual({"required_firmware": "10.00.00.00"},
                         self.speicher.angaben_lesen(self.datei))
        self.assertFalse(self.speicher.kennt_ohne_bild(self.datei),
                         "Ein Eintrag nur mit Angaben galt als 'hat kein Titelbild'.")

    def test_ein_bild_laesst_die_angaben_stehen(self) -> None:
        self.speicher.angaben_schreiben(self.datei, {"sdk": "10.00.00.00"})
        self.speicher.schreiben(self.datei, b"\x89PNG")
        self.assertEqual({"sdk": "10.00.00.00"}, self.speicher.angaben_lesen(self.datei))
        self.assertTrue(self.speicher.lesen(self.datei))

    def test_umziehen_nimmt_bild_und_angaben_mit(self) -> None:
        self.speicher.schreiben(self.datei, b"\x89PNG")
        self.speicher.angaben_schreiben(self.datei, {"sdk": "10.00.00.00"})
        alter_schluessel = self.speicher.schluessel(self.datei)
        neu = os.path.join(self._ordner.name, "Spiel neu.ffpfsc")
        os.rename(self.datei, neu)
        self.assertTrue(self.speicher.umziehen(alter_schluessel, neu))
        self.assertTrue(self.speicher.lesen(neu))
        self.assertEqual({"sdk": "10.00.00.00"}, self.speicher.angaben_lesen(neu))


class ZwischenablageTests(unittest.TestCase):

    def test_leere_daten_gehen_nicht_hinein(self) -> None:
        self.assertFalse(plattform.bild_in_zwischenablage(b""))

    def test_linux_ohne_werkzeug_sagt_nein(self) -> None:
        with mock.patch.object(plattform, "IST_WINDOWS", False), \
                mock.patch.object(plattform, "IST_MACOS", False), \
                mock.patch.object(plattform.shutil, "which", return_value=None), \
                mock.patch.object(plattform.subprocess, "run") as starten:
            self.assertFalse(plattform.bild_in_zwischenablage(b"\x89PNG"))
        starten.assert_not_called()

    def test_linux_wartet_nicht_auf_die_ausgabe(self) -> None:
        """xclip/wl-copy bleiben stehen - mit abgefangener Ausgabe hinge run()."""
        with mock.patch.object(plattform, "IST_WINDOWS", False), \
                mock.patch.object(plattform, "IST_MACOS", False), \
                mock.patch.object(plattform.shutil, "which", return_value="/usr/bin/xclip"), \
                mock.patch.object(plattform.subprocess, "run",
                                  return_value=mock.Mock(returncode=0)) as starten:
            self.assertTrue(plattform.bild_in_zwischenablage(b"\x89PNG"))
        _befehl, kwargs = starten.call_args
        self.assertIs(plattform.subprocess.DEVNULL, kwargs["stdout"])
        self.assertIs(plattform.subprocess.DEVNULL, kwargs["stderr"])


# ---------------------------------------------------------------------------
# Das Hauptmodul - am Syntaxbaum und an Texten
# ---------------------------------------------------------------------------

class KnoepfeUndTitelleisteTests(unittest.TestCase):

    def test_die_titelleiste_hat_keinen_knopf_bibliothek(self) -> None:
        namen = [n for n, _s, _b in APP.PS5ConverterGUI._FALTBARE_TITELKNOEPFE]
        self.assertNotIn("_btn_library_title", namen)
        self.assertIn("_btn_klog_title", namen, "KLOG bleibt oben.")
        self.assertNotIn("self._btn_library_title =",
                         HAUPTDATEI.read_text(encoding="utf-8"))

    def test_die_ansicht_konsole_hat_sechs_knoepfe(self) -> None:
        kennungen = [k for _s, k in APP.PS5ConverterGUI._KONSOLE_KNOEPFE]
        self.assertEqual(["dienste", "spielstaende", "bibliothek", "remoteplay",
                          "prosperolight", "actremotelink"], kennungen)
        for nummer, (schluessel, _k) in enumerate(APP.PS5ConverterGUI._KONSOLE_KNOEPFE,
                                                  start=1):
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    self.assertTrue(STRINGS[schluessel][sprache].startswith("%d. " % nummer))

    def test_holen_senden_und_klog_sind_keine_knoepfe_mehr(self) -> None:
        klasse = APP.PS5ConverterGUI
        for kennung in ("spiel_holen", "zurueckspielen", "klog"):
            with self.subTest(kennung=kennung):
                self.assertNotIn(kennung, klasse._KONSOLE_FENSTER)
        for methode in ("_show_konsole_spiel_holen", "_show_konsole_zurueckspielen",
                        "_show_library_window", "_konsole_schliessen_bewachen"):
            with self.subTest(methode=methode):
                self.assertFalse(hasattr(klasse, methode))

    def test_drei_seiten_mit_bauplan(self) -> None:
        klasse = APP.PS5ConverterGUI
        self.assertEqual({"uebersicht", "actremotelink", "bibliothek"},
                         set(klasse._KONSOLE_SEITENBAU))
        for seite, (_attr, bauen, _knopf) in klasse._KONSOLE_SEITENBAU.items():
            with self.subTest(seite=seite):
                self.assertTrue(callable(getattr(klasse, bauen, None)))
        self.assertEqual("_konsole_bibliothek_umschalten",
                         klasse._KONSOLE_SEITEN["bibliothek"])

    def test_der_warnhinweis_nennt_den_knopf_nicht_fest(self) -> None:
        for sprache in ("de", "en"):
            text = STRINGS["remoteplay.warn_schreibt"][sprache]
            self.assertIn("{knopf}", text)
            self.assertNotIn("8. ActRemoteLink", text)


class SeitenQuelltextTests(unittest.TestCase):

    def test_als_quelle_uebernehmen_schaltet_zur_umwandlung(self) -> None:
        fn = _innere("_render_library_window", "_use_as_source")
        self.assertIn("_ansicht_setzen", _aufgerufen(fn))
        self.assertNotIn("destroy", _aufgerufen(fn))

    def test_konsoleneintraege_finden_ihr_bild_h9_2(self) -> None:
        """H9-2: Die Detailspalte fragte mit dem Konsolenpfad und bekam nie ein Bild."""
        self.assertIn("_bibliothek_ps5_merkname",
                      _aufgerufen(_innere("_render_library_window", "_details_zeigen")))
        self.assertIn("_bibliothek_ps5_merkname",
                      _aufgerufen(_methode("_bibliothek_ps5_bilder_nachladen")))

    def test_der_update_vergleich_fragt_den_schalter_vorher(self) -> None:
        text = ast.unparse(_innere("_render_library_window", "_update_anstossen"))
        self.assertLess(text.index("_metadaten_online_erlaubt()"),
                        text.index("threading.Thread"))

    def test_spiel_info_und_bibliothek_lesen_dieselbe_seite(self) -> None:
        self.assertIn("_patchseite_lesen", _aufgerufen(_methode("_fetch_patches_async")))
        self.assertIn("_patchseite_lesen", _aufgerufen(_methode("_patchliste_holen")))
        self.assertNotIn("urlopen", _aufgerufen(_methode("_fetch_patches_async")))

    def test_sprachwechsel_faltet_die_titelleiste(self) -> None:
        """Ohne das stand nach DE -> EN -> DE der linke Knopf abgeschnitten da."""
        text = ast.unparse(_methode("_apply_language"))
        self.assertIn("self._titelleiste_anpassen", text)
        self.assertIn("self._bibliothek['beschriften']()", text)

    def test_die_uebersicht_merkt_sich_die_firmware(self) -> None:
        """Am Ende der Pruefung legt der Takt die Firmware ab - einmal.

        Am wirklichen Takt gemessen: Eine Textsuche nach dem Schluessel fand
        ihn auch im ``_load_setting`` daneben und blieb gruen, als das
        Speichern fehlte (Gegenprobe 25.09.2026).
        """
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._konsole_tafel_stand = {"konsole": mock.Mock(firmware="12.00")}
        gui._konsole_tafel_laeuft = {"aktiv": False}
        gui._konsole_tafel_zustand = mock.Mock()
        gui._konsole_tafel_status = mock.Mock()
        gui._konsole_tafel_knopf = mock.Mock()
        gui._konsole_tafel_zustandstext = lambda stand: ""
        gui._konsole_tafel_statustext = lambda stand, aktiv: ""
        gespeichert: dict = {}
        gui._load_setting = lambda schluessel, vorgabe=None: gespeichert.get(schluessel, vorgabe)
        gui._save_setting = mock.Mock(side_effect=gespeichert.__setitem__)
        APP.PS5ConverterGUI._konsole_tafel_takt(gui)
        self.assertEqual("12.00", gespeichert.get("konsole_firmware"))
        APP.PS5ConverterGUI._konsole_tafel_takt(gui)
        self.assertEqual(1, gui._save_setting.call_count,
                         "Dieselbe Firmware nicht bei jedem Takt schreiben.")

    def test_die_ordneruebertragung_schliesst_ueber_den_takt(self) -> None:
        """Der Faden legt nur ``ende`` ab; ein after() aus ihm kaeme nur mit
        laufender Hauptschleife an (Durchsicht H3-14)."""
        methode = _methode("_bibliothek_ordner_uebertragen")
        arbeit = next(k for k in ast.walk(methode)
                      if isinstance(k, ast.FunctionDef) and k.name == "_arbeit")
        self.assertNotIn("_spaeter_im_fenster", _aufgerufen(arbeit))
        self.assertIn("lauf['ende'] = True", ast.unparse(arbeit))
        self.assertIn("_abschluss", _aufgerufen(next(
            k for k in ast.walk(methode)
            if isinstance(k, ast.FunctionDef) and k.name == "_anzeigen")))

    def test_die_kachelunterzeile_bricht_um(self) -> None:
        text = ast.unparse(_methode("_bibliothek_kacheln_setzen"))
        self.assertIn("'\\n'.join", text)
        self.assertIn("wraplength=kante", text)

    def test_alle_knoepfe_der_seite_sind_kompakt(self) -> None:
        """Mit dem normalen Knopf (Polsterung 18/11) passte die Seite nicht in 700 px."""
        for knoten in ast.walk(_methode("_render_library_window")):
            if not (isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Attribute)
                    and knoten.func.attr == "Button"
                    and getattr(knoten.func.value, "id", "") == "ttk"):
                continue
            stil = next((w.value for w in knoten.keywords if w.arg == "style"), None)
            with self.subTest(zeile=knoten.lineno):
                self.assertIsNotNone(stil, "ttk.Button ohne kompakten Stil")
                if isinstance(stil, ast.Constant):
                    self.assertIn(stil.value, ("Klein.TButton", "KleinAccent.TButton"))

    def test_statuszeilen_passen_zu_ihren_texten(self) -> None:
        """_status(...) umgeht die Platzhalterpruefung von test_i18n."""
        fn = _methode("_render_library_window")
        gesehen = 0
        for k in ast.walk(fn):
            if not (isinstance(k, ast.Call) and getattr(k.func, "id", "") == "_status"
                    and k.args and isinstance(k.args[0], ast.Constant)):
                continue
            schluessel = k.args[0].value
            gegeben = {w.arg for w in k.keywords}
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    self.assertEqual(_platzhalter(STRINGS[schluessel][sprache]), gegeben)
            gesehen += 1
        self.assertGreaterEqual(gesehen, 5, "Die Pruefung findet kaum Aufrufe.")

    def test_zusammengesetzte_schluessel_gibt_es(self) -> None:
        schluessel = (["library.zustand." + z for z in (
            bib.BEREIT, bib.GLEICH, bib.OHNE_KENNUNG, bib.ZIEL_VORHANDEN,
            bib.DOPPELT, bib.AUF_KONSOLE, bib.FEHLT)]
            + ["library.form." + f for f in bib.NAMENSFORMEN]
            + ["library.update_" + a for a in ("aus", "fehler", "keine")])
        for k in schluessel:
            with self.subTest(schluessel=k):
                self.assertTrue(STRINGS[k]["de"])
                self.assertTrue(STRINGS[k]["en"])
                self.assertEqual(set(), _platzhalter(STRINGS[k]["de"]))


class PatchlisteTests(unittest.TestCase):
    """Der Update-Vergleich geht ohne Freigabe nicht ins Netz."""

    def _gui(self):
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._current_language = "de"
        gui._patch_cache = {}
        gui._PATCH_CACHE_TTL = 3600          # wie im Konstruktor
        return gui

    def test_ohne_freigabe_nur_der_zwischenspeicher(self) -> None:
        # Gezaehlt, nicht geworfen: _patchseite_lesen faengt jede Ausnahme ab
        # und meldet "gescheitert" - also dasselbe ([], False) wie die Sperre.
        # Mit side_effect=AssertionError blieb die Gegenprobe gruen.
        gui = self._gui()
        with mock.patch.object(APP.urllib.request, "urlopen",
                               side_effect=OSError("ins Netz")) as netz:
            self.assertEqual(([], False), gui._patchliste_holen("PPSA01234", online=False))
            eintrag = ("PS5", "01.002.000", "1 GB", "10.00", "2026-03-12", True, "")
            gui._patch_cache["PPSA01234"] = (time.time(), [eintrag])
            self.assertEqual(([eintrag], True),
                             gui._patchliste_holen("PPSA01234", online=False))
        netz.assert_not_called()

    def test_eine_gescheiterte_abfrage_kommt_nicht_in_den_speicher(self) -> None:
        gui = self._gui()
        with mock.patch.object(APP.urllib.request, "urlopen", side_effect=OSError("weg")):
            self.assertEqual(([], False), gui._patchliste_holen("PPSA01234", online=True))
        self.assertNotIn("PPSA01234", gui._patch_cache)

    def test_keine_updates_ist_eine_antwort(self) -> None:
        gui = self._gui()
        antwort = mock.MagicMock()
        antwort.__enter__.return_value.read.return_value = b"<html>404 - not here</html>"
        with mock.patch.object(APP.urllib.request, "urlopen", return_value=antwort):
            self.assertEqual(([], True), gui._patchliste_holen("PPSA01234", online=True))
        self.assertEqual([], gui._patch_cache["PPSA01234"][1])

    def test_die_neueste_fassung(self) -> None:
        liste = [("PS5", "01.010.000", "", "", "", False, ""),
                 ("PS5", "01.002.000", "", "", "", False, "")]
        self.assertEqual("01.010.000", APP.PS5ConverterGUI._neueste_aus_patchliste(liste)[1])
        liste.append(("PS5", "01.005.000", "", "", "", True, ""))
        self.assertEqual("01.005.000", APP.PS5ConverterGUI._neueste_aus_patchliste(liste)[1],
                         "Die Seite markiert die neueste selbst - das gilt.")
        self.assertIsNone(APP.PS5ConverterGUI._neueste_aus_patchliste([]))


# ---------------------------------------------------------------------------
# Die Seite am wirklichen Programm
# ---------------------------------------------------------------------------

@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class SeiteTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        # Weder Suchordner noch PS5: Der Aufbau soll nichts suchen.
        cls._einstellungen = {"library_scan_folders": [], "library_quelle": "pc",
                              "library_ansicht": "kacheln"}
        cls._laden = mock.patch.object(
            cls.app, "_load_setting",
            side_effect=lambda k, v=None, _alt=cls.app._load_setting:
            cls._einstellungen.get(k, _alt(k, v)))
        cls._laden.start()
        cls._speichern = mock.patch.object(cls.app, "_save_setting",
                                           lambda k, v: cls._einstellungen.__setitem__(k, v))
        cls._speichern.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._speichern.stop()
        cls._laden.stop()
        cls.app._konfiguration_schreiben({"ansicht": "umwandeln"})

    def tearDown(self) -> None:
        self.app._konsole_seite_setzen("uebersicht")
        self.app._ansicht_setzen("umwandeln", speichern=False)
        _WURZEL.update()

    def _seite(self) -> dict:
        self.app._ansicht_setzen("konsole", speichern=False)
        self.app._konsole_seite_setzen("bibliothek")
        _WURZEL.update()
        return self.app._bibliothek

    @staticmethod
    def _gezeigt(widget) -> bool:
        return bool(widget is not None and widget.winfo_manager())

    def _knopf(self, schluessel: str):
        for knopf, s in self.app._konsole_knoepfe:
            if s == schluessel:
                return knopf
        self.fail("Knopf %s fehlt" % schluessel)

    def test_der_knopf_zeigt_die_seite_und_nimmt_sie_wieder(self) -> None:
        app = self.app
        app._ansicht_setzen("konsole", speichern=False)
        vorher = {t.name for t in threading.enumerate()}
        app._konsole_bibliothek_umschalten()
        _WURZEL.update()
        seite = app._bibliothek_seite
        self.assertTrue(self._gezeigt(seite))
        lage = seite.grid_info()
        self.assertEqual((1, 1), (int(lage["row"]), int(lage["column"])))
        self.assertFalse(self._gezeigt(app._konsole_tafel))
        self.assertEqual(app._COLORS["fg_accent"], self._knopf("konsole.btn_bibliothek")._bg)
        neu = {t.name for t in threading.enumerate()} - vorher
        self.assertFalse({n for n in neu if n.startswith("bibliothek")},
                         "Ohne Suchordner startet der Aufbau keinen Suchlauf.")
        app._konsole_bibliothek_umschalten()
        _WURZEL.update()
        self.assertFalse(self._gezeigt(seite))
        self.assertTrue(self._gezeigt(app._konsole_tafel))
        self.assertEqual(app._COLORS["bg_card"], self._knopf("konsole.btn_bibliothek")._bg)

    def test_die_seiten_verdraengen_einander(self) -> None:
        self._seite()
        self.app._konsole_seite_setzen("actremotelink")
        _WURZEL.update()
        self.assertFalse(self._gezeigt(self.app._bibliothek_seite))
        self.assertTrue(self._gezeigt(self.app._rpassist_seite))
        self.assertEqual(self.app._COLORS["bg_card"], self._knopf("konsole.btn_bibliothek")._bg)

    def test_die_knopfreihen_gehoeren_zur_quelle(self) -> None:
        zustand = self._seite()
        texte = {q: [k.cget("text") for k in knoepfe]
                 for q, knoepfe in zustand["knoepfe"].items()}
        self.assertEqual([self.app._t(s) for s in (
            "library.use_as_source_button", "library.upload_knopf",
            "library.btn_umbenennen", "library.btn_alle_umbenennen",
            "library.btn_rueckgaengig", "library.reveal_in_explorer_button")], texte["pc"])
        self.assertEqual([self.app._t(s) for s in (
            "library.download_knopf", "holen.btn_dump", "library.btn_dateimanager",
            "library.rescan_button")], texte["ps5"])
        pc, ps5 = (zustand["knoepfe"][q][0].master for q in ("pc", "ps5"))
        self.assertTrue(self._gezeigt(pc))
        self.assertFalse(self._gezeigt(ps5))
        with mock.patch.object(self.app, "_bibliothek_ps5_scannen", return_value=([], "")):
            zustand["quelle"].set("ps5")
            zustand["quelle_gewechselt"]()
            try:
                self.assertTrue(self._gezeigt(ps5))
                self.assertFalse(self._gezeigt(pc))
            finally:
                zustand["quelle"].set("pc")
                zustand["quelle_gewechselt"]()

    def test_die_firmware_zeile_sagt_wann_backport_noetig_ist(self) -> None:
        zustand = self._seite()
        with tempfile.TemporaryDirectory() as ordner, \
                mock.patch.object(self.app, "_konsole_firmware", return_value="12000020"), \
                mock.patch.object(self.app, "_metadaten_online_erlaubt", return_value=False):
            for verlangt, rolle, stueck in (("13.00.00.00", "fg_warning", "BACKPORT"),
                                           ("09.00.00.00", "fg_success", "9.00")):
                eintrag = _eintrag(ordner, required_firmware=verlangt, sdk=verlangt)
                zustand["details"](eintrag)
                feld = zustand["zeilen"]["firmware"]
                with self.subTest(verlangt=verlangt):
                    self.assertIn(stueck, feld.cget("text"))
                    self.assertIn("12.00", feld.cget("text"))
                    self.assertEqual(self.app._COLORS[rolle], str(feld.cget("fg")))
                    self.assertIn("SDK", zustand["zeilen"]["sdk"].cget("text"))

    def test_die_update_zeile_aus_dem_zwischenspeicher(self) -> None:
        zustand = self._seite()
        zustand["ansicht"]["updates"].clear()
        self.app._patch_cache["PPSA04610"] = (time.time(), [
            ("PS5", "01.018.000", "1 GB", "10.00", "2026-03-12 10:00:00", True, "")])
        self.addCleanup(self.app._patch_cache.pop, "PPSA04610", None)
        with tempfile.TemporaryDirectory() as ordner, \
                mock.patch.object(self.app, "_metadaten_online_erlaubt", return_value=False), \
                mock.patch.object(self.app, "_konsole_firmware", return_value="12000020"):
            zustand["details"](_eintrag(ordner, required_firmware="10.00.00.00"))
            feld = zustand["zeilen"]["update"]
            self.assertTrue(_schleife_bis(lambda: "01.018.000" in feld.cget("text")),
                            "Keine Update-Zeile: %r" % feld.cget("text"))
            self.assertIn("2026-03-12", feld.cget("text"))
            self.assertEqual(self.app._COLORS["fg_warning"], str(feld.cget("fg")))

    def test_ohne_freigabe_und_speicher_steht_update_aus(self) -> None:
        zustand = self._seite()
        zustand["ansicht"]["updates"].clear()
        with tempfile.TemporaryDirectory() as ordner, \
                mock.patch.object(self.app, "_metadaten_online_erlaubt", return_value=False), \
                mock.patch.object(APP.urllib.request, "urlopen",
                                  side_effect=AssertionError("ins Netz")) as netz:
            zustand["details"](_eintrag(ordner, title_id="PPSA09999",
                                        required_firmware="10.00.00.00"))
            self.assertEqual(self.app._t("library.update_aus"),
                             zustand["zeilen"]["update"].cget("text"))
            netz.assert_not_called()

    def test_als_quelle_uebernehmen(self) -> None:
        zustand = self._seite()
        with tempfile.TemporaryDirectory() as ordner:
            eintrag = _eintrag(ordner)
            zustand["eintraege"].append(eintrag)
            self.addCleanup(zustand["eintraege"].remove, eintrag)
            zustand["ansicht"]["gewaehlt"] = ordner
            with mock.patch.object(self.app, "_validate_source_path", return_value=""):
                zustand["knoepfe"]["pc"][0].invoke()
            _WURZEL.update()
            self.assertEqual(ordner, self.app.source_path.get())
            self.assertFalse(self.app._ansicht_ist_konsole(),
                             "Nach der Uebernahme geht es zurueck zur Umwandlung.")

    def test_umbenennen_und_rueckgaengig_ziehen_alles_nach(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            alt = os.path.join(ordner, "elden.ffpfsc")
            Path(alt).write_bytes(b"abbild")
            speicher = self.app._bibliothek_bildspeicher()
            speicher.schreiben(alt, b"\x89PNG")
            self.app.source_path.set(alt)
            gemeldet: list = []
            plan = bib.umbenennen_planen([_eintrag(alt)], "kennung_titel")
            self.app._bibliothek_umbenennen_anwenden(
                plan, lambda ergebnis, zurueck: gemeldet.append((ergebnis, zurueck)))
            neu = os.path.join(ordner, "PPSA04610 Elden Ring.ffpfsc")
            self.assertTrue(os.path.exists(neu))
            self.assertEqual(neu, self.app.source_path.get(), "Das Quellfeld folgt dem Namen.")
            self.assertTrue(speicher.lesen(neu), "Das Titelbild zog nicht mit um.")
            self.assertFalse(gemeldet[0][1])
            with mock.patch.object(APP.messagebox, "askyesno", return_value=True):
                self.app._bibliothek_rueckgaengig(
                    lambda ergebnis, zurueck: gemeldet.append((ergebnis, zurueck)))
            self.assertTrue(os.path.exists(alt))
            self.assertEqual(alt, self.app.source_path.get())
            self.assertTrue(gemeldet[1][1])
            self.app.source_path.set("")

    def test_das_umbenennen_fenster_einzeln(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            alt = os.path.join(ordner, "elden.ffpfsc")
            Path(alt).write_bytes(b"abbild")
            vorher = set(_WURZEL.winfo_children())
            gemeldet: list = []
            self.app._bibliothek_umbenennen_fenster(
                [_eintrag(alt)], einzeln=True,
                fertig=lambda ergebnis, zurueck: gemeldet.append(ergebnis))
            _WURZEL.update()
            fenster = next(w for w in _WURZEL.winfo_children() if w not in vorher)
            try:
                # Ohne die Combobox der Namensform - sie ist in ttk ein Entry.
                felder = [w for w in self._alle(fenster) if isinstance(w, tk.ttk.Entry)
                          and not isinstance(w, tk.ttk.Combobox)]
                self.assertEqual(1, len(felder))
                self.assertEqual("Elden Ring - PPSA04610 - v1.17.0 - EU.ffpfsc",
                                 felder[0].get())
                self._knopf_mit(fenster, self.app._t("library.btn_umbenennen")).invoke()
                _WURZEL.update()
            finally:
                if fenster.winfo_exists():
                    fenster.destroy()
            self.assertTrue(os.path.exists(
                os.path.join(ordner, "Elden Ring - PPSA04610 - v1.17.0 - EU.ffpfsc")))
            self.assertEqual(1, len(gemeldet))

    def test_das_umbenennen_fenster_fuer_alle_ohne_auswahl(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            dateien = []
            for name in ("a.ffpfsc", "b.ffpfsc"):
                pfad = os.path.join(ordner, name)
                Path(pfad).write_bytes(b"x")
                dateien.append(pfad)
            eintraege = [_eintrag(dateien[0]),
                         _eintrag(dateien[1], title="Stray", title_id="PPSA02100")]
            vorher = set(_WURZEL.winfo_children())
            self.app._bibliothek_umbenennen_fenster(eintraege, einzeln=False,
                                                    fertig=lambda *_a: None)
            _WURZEL.update()
            fenster = next(w for w in _WURZEL.winfo_children() if w not in vorher)
            try:
                tabelle = next(w for w in self._alle(fenster) if isinstance(w, tk.ttk.Treeview))
                self.assertEqual(2, len(tabelle.get_children()))
                self._knopf_mit(fenster, self.app._t("library.btn_keine")).invoke()
                with mock.patch.object(APP.messagebox, "showinfo") as hinweis:
                    self._knopf_mit(fenster, self.app._t("library.btn_umbenennen")).invoke()
                hinweis.assert_called_once()
            finally:
                if fenster.winfo_exists():
                    fenster.destroy()
            self.assertTrue(all(os.path.exists(p) for p in dateien),
                            "Ohne Auswahl wurde trotzdem umbenannt.")

    def test_die_seite_folgt_dem_sprachwechsel(self) -> None:
        zustand = self._seite()
        pc = zustand["knoepfe"]["pc"]
        self.app._current_language = "en"
        try:
            self.app._apply_language()
            _WURZEL.update()
            self.assertEqual("Use as source", pc[0].cget("text"))
            self.assertEqual("Rename all", pc[3].cget("text"))
            self.assertEqual(STRINGS["library.no_entry_selected"]["en"],
                             zustand["zeilen"]["titel"].cget("text"))
        finally:
            self.app._current_language = "de"
            self.app._apply_language()
            _WURZEL.update()
        self.assertEqual("Als Quelle übernehmen", pc[0].cget("text"))

    @staticmethod
    def _alle(widget):
        offen = list(widget.winfo_children())
        while offen:
            kind = offen.pop()
            offen.extend(kind.winfo_children())
            yield kind

    def _knopf_mit(self, fenster, text: str):
        for w in self._alle(fenster):
            try:
                if str(w.cget("text")) == text:
                    return w
            except Exception:  # noqa: BLE001
                continue
        self.fail("Kein Knopf %r" % text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
