# -*- coding: utf-8 -*-
"""Automatische Suche nach neuen NG-Fassungen beim Programmstart (Nutzerwunsch 15.11.2026).

Bewacht wird hier:

* Ab Werk **an** (Nutzerwunsch 15.11.2026; zuerst als "aus" gebaut): die einzige Abfrage, die das Programm ungefragt macht. Mit
  abgeschaltetem Haken geht nichts ins Netz, und der Aufruf steht in ``main()``, nie im Konstruktor (Tests, Diagnose und
  Kommandozeile bauen das Programm ebenfalls).
* Eingeschaltet: hoechstens einmal am Tag (``auto_faellig``), nur ``quer3q/ampr-emu-ng`` (nicht drakmor), Pruefsumme gegen GitHub,
  Vorabfassungen nie, jeder Schritt im Protokoll; eine neu geholte NG-Fassung wird - wie bisher - die zstd-Vorgabe, und das
  Protokoll sagt, dass sie an der Konsole nicht geprueft ist.
* Eine Abfrage ohne Antwort oder mit Fehlschlag beim Holen zaehlt nicht als erledigt und wird beim naechsten Start wiederholt.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import queue
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("ng_auto")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import ampr_updates as au          # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

G = APP.PS5ConverterGUI
QUELLE = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
JETZT = datetime.datetime(2026, 11, 15, 20, 0, 0)

SCHLUESSEL = ("ampr.auto_start", "ampr.auto_neue_vorgabe", "settings_dialog.ng_auto_section",
              "settings_dialog.ng_auto_checkbox", "settings_dialog.ng_auto_hint", "settings_dialog.ng_auto_jetzt",
              "ampr.update_anzeige_laeuft", "ampr.update_anzeige_schon", "ampr.update_anzeige_ende")


def _eintrag(version: str, variante: str) -> dict:
    return {"lib": "libSceAmpr.sprx", "version": version, "variant": variante, "size": 1000,
            "path": "/x/%s %s/libSceAmpr.sprx" % (version, variante), "sha256": "", "quelle": "beilage"}


def _ng_antwort(*fassungen: str, vorab: str = "") -> bytes:
    """Releases-Antwort von quer3q/ampr-emu-ng; der Inhalt jedes Anhangs ist sein Name (Digest = SHA-256 des Namens)."""
    freigaben = []
    for fassung in list(fassungen) + ([vorab] if vorab else []):
        freigaben.append({
            "tag_name": "v" + fassung, "draft": False, "prerelease": fassung == vorab,
            "assets": [{"name": name, "size": 4, "digest": "sha256:" + hashlib.sha256(name.encode()).hexdigest(),
                        "browser_download_url": "http://beispiel.invalid/ng/%s/%s" % (fassung, name)}
                       for name in ("libSceAmpr-debug.sprx", "libSceAmpr.sprx", "SHA256SUMS")]})
    return json.dumps(freigaben).encode("utf-8")


def _drakmor_antwort(fassung: str) -> bytes:
    return json.dumps([{"tag_name": fassung, "assets": [{
        "name": "libSceAmpr.sprx-%s-test-nopack" % fassung, "size": 4,
        "browser_download_url": "http://beispiel.invalid/drakmor/%s" % fassung}]}]).encode("utf-8")


class FaelligTests(unittest.TestCase):
    def test_nie_gefragt_oder_unbrauchbar_ist_faellig(self) -> None:
        for zuletzt in ("", None, "gestern", "2026-13-45", "   "):
            with self.subTest(zuletzt=zuletzt):
                self.assertTrue(au.auto_faellig(zuletzt, JETZT))

    def test_ein_tag_abstand(self) -> None:
        self.assertFalse(au.auto_faellig((JETZT - datetime.timedelta(hours=23, minutes=59)).isoformat(), JETZT))
        self.assertTrue(au.auto_faellig((JETZT - datetime.timedelta(hours=24)).isoformat(), JETZT))
        self.assertTrue(au.auto_faellig((JETZT - datetime.timedelta(days=9)).isoformat(), JETZT))

    def test_eine_zeit_in_der_zukunft_haelt_die_suche_nicht_auf(self) -> None:
        """Verstellte Uhr: Sonst stuende die Suche auf Tage, bis die Zeit eingeholt waere."""
        self.assertTrue(au.auto_faellig((JETZT + datetime.timedelta(days=3)).isoformat(), JETZT))

    def test_zeitzonen_werden_vertragen(self) -> None:
        mit_zone = (JETZT - datetime.timedelta(hours=1)).replace(tzinfo=datetime.timezone.utc).isoformat()
        self.assertFalse(au.auto_faellig(mit_zone, JETZT))

    def test_das_modul_bleibt_ohne_netzcode(self) -> None:
        quelle = Path(au.__file__).read_text(encoding="utf-8")
        for verboten in ("urlopen", "urllib.request", "requests.", "socket.", "http.client"):
            self.assertNotIn(verboten, quelle)


class AnfrageTests(unittest.TestCase):
    """Die Kopfzeile ``Accept`` von ``_ampr_lade_adresse``: GitHub antwortet auf die Liste der Freigaben mit 415, wenn dort
    ``application/octet-stream`` steht (gemessen 15.11.2026 an api.github.com) - das Programm schickte es bei jeder Abfrage."""

    def _akzeptiert(self, adresse: str) -> str:
        gesehen: list = []

        class _Antwort:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b"[]"

        def _oeffnen(anfrage, timeout=None):
            gesehen.append(anfrage)
            return _Antwort()

        gui = G.__new__(G)
        with mock.patch.object(APP.urllib.request, "urlopen", _oeffnen):
            self.assertEqual(b"[]", gui._ampr_lade_adresse(adresse))
        return gesehen[0].get_header("Accept")

    def test_die_freigabenliste_wird_als_json_angefragt(self) -> None:
        for projekt in (au.PROJEKT, au.NG_PROJEKT):
            with self.subTest(projekt=projekt):
                self.assertEqual("application/vnd.github+json", self._akzeptiert(au.ADRESSE % projekt))

    def test_ein_anhang_wird_als_datei_geholt(self) -> None:
        self.assertEqual("application/octet-stream",
                         self._akzeptiert("https://github.com/quer3q/ampr-emu-ng/releases/download/v0.4.1/libSceAmpr.sprx"))


class QuelltextTests(unittest.TestCase):
    def test_der_aufruf_steht_in_main_und_nicht_im_konstruktor(self) -> None:
        self.assertIn("root.after(app._NG_AUTO_VERZOEGERUNG_MS, app._ng_automatisch_pruefen)", QUELLE)
        anfang = QUELLE.index("def __init__(self, root: tk.Tk, start_leer")
        ende = QUELLE.index("\n    def ", anfang + 10)
        self.assertNotIn("_ng_automatisch_pruefen", QUELLE[anfang:ende], "der Konstruktor darf nie ins Netz")
        self.assertEqual(1, QUELLE.count("app._ng_automatisch_pruefen"))

    def test_ab_werk_an(self) -> None:
        self.assertEqual("ng_auto_pruefen", au.AUTO_EINSTELLUNG)
        self.assertIs(au.AUTO_VORGABE, True, "Nutzerwunsch 15.11.2026: standardmaessig eingeschaltet")
        self.assertGreaterEqual(QUELLE.count("self._load_setting(ampr_updates.AUTO_EINSTELLUNG, ampr_updates.AUTO_VORGABE)"), 2,
                                "Dialog und Start lesen die Einstellung mit derselben Vorgabe - sie laufen nie auseinander")
        self.assertNotIn("AUTO_EINSTELLUNG, False)", QUELLE, "keine zweite, abweichende Vorgabe im Programm")

    def test_die_texte_gibt_es_in_allen_sprachen(self) -> None:
        for schluessel in SCHLUESSEL:
            for sprache in ("de", "en", "es", "it", "fr"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    self.assertTrue(STRINGS[schluessel][sprache].strip())
        for sprache in ("de", "en", "es", "it", "fr"):
            self.assertIn("{fassung}", STRINGS["ampr.auto_neue_vorgabe"][sprache])


class AblaufTests(unittest.TestCase):
    """``_ng_automatisch_pruefen`` und ``_ampr_updates_arbeiten`` mit Attrappen statt Netz."""

    NG_DA = [_eintrag("0.4.1", "ng"), _eintrag("0.4.1", "ng-debug")]
    DRAKMOR_DA = [_eintrag("0.4.2.1", "test-nopack")]

    def _gui(self, antworten: dict, einstellungen: dict | None = None, bestand: list | None = None):
        gui = G.__new__(G)
        self.protokoll: list[str] = []
        self.anfragen: list[str] = []
        self.einstellungen = dict(einstellungen or {})
        self.ordner = tempfile.mkdtemp(prefix="ng_auto_")
        self.nachgeladen: list[int] = []
        gui._ampr_alle_fassungen = lambda *a, **k: list(bestand if bestand is not None else self.DRAKMOR_DA + self.NG_DA)
        gui._melde_im_hauptstrang = self.protokoll.append
        gui._append_to_log = self.protokoll.append
        gui._t = lambda schluessel, **w: schluessel + ("|" + "|".join("%s=%s" % kv for kv in sorted(w.items())) if w else "")
        gui._load_setting = lambda k, d=None: self.einstellungen.get(k, d)
        gui._save_setting = lambda k, v: self.einstellungen.__setitem__(k, v)
        gui._hauptfaden_planen = lambda f, *a, **k: f()
        gui._ampr_updates_ordner = lambda: self.ordner
        gui._ampr_versionsliste_nachladen = lambda: self.nachgeladen.append(1)

        def _lade(adresse: str) -> bytes:
            self.anfragen.append(adresse)
            for teil, antwort in antworten.items():
                if teil in adresse:
                    if isinstance(antwort, Exception):
                        raise antwort
                    return antwort(adresse) if callable(antwort) else antwort
            raise AssertionError("unerwartete Adresse " + adresse)

        gui._ampr_lade_adresse = _lade
        # Der Strang laeuft hier gleich im Aufruf mit.
        gui._ampr_nach_updates_sehen = (lambda danach=None, nur_ng=False, auto=False:
                                        gui._ampr_updates_arbeiten(danach, nur_ng=nur_ng, auto=auto))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.ordner, ignore_errors=True))
        return gui

    @staticmethod
    def _anhang(adresse: str) -> bytes:
        """Der Inhalt eines Anhangs ist sein Name (so ist der Digest in ``_ng_antwort`` gebaut)."""
        return adresse.rsplit("/", 1)[1].encode()

    def _antworten(self, ng: bytes) -> dict:
        return {"api.github.com/repos/quer3q/ampr-emu-ng": ng, "beispiel.invalid/ng/": self._anhang,
                "api.github.com/repos/drakmor/ampr_emu": _drakmor_antwort("0.4.2.1")}

    def test_ab_werk_ist_die_suche_an(self) -> None:
        """Ohne gespeicherte Einstellung (frische Installation) sucht und holt das Programm beim Start."""
        gui = self._gui(self._antworten(_ng_antwort("0.5.0", "0.4.1")))
        gui._ng_automatisch_pruefen()
        self.assertTrue(self.anfragen, "es wurde gefragt")
        self.assertTrue(os.path.isfile(au.zielpfad(self.ordner, "0.5.0", "ng")))
        self.assertEqual("ampr.auto_start", self.protokoll[0], "und es steht im Protokoll")
        self.assertNotIn(au.AUTO_EINSTELLUNG, self.einstellungen, "die Vorgabe wird nicht erst gespeichert")

    def test_abgeschaltet_geht_nichts_ins_netz(self) -> None:
        gui = self._gui(self._antworten(_ng_antwort("0.5.0")), {au.AUTO_EINSTELLUNG: False})
        gui._ng_automatisch_pruefen()
        self.assertEqual([], self.anfragen)
        self.assertEqual([], self.protokoll, "auch keine Zeile im Protokoll: es geschieht ja nichts")
        self.assertNotIn(au.AUTO_ZULETZT, self.einstellungen)

    def test_eingeschaltet_holt_nur_ng_und_prueft_die_summe(self) -> None:
        gui = self._gui(self._antworten(_ng_antwort("0.5.0", "0.4.1")), {au.AUTO_EINSTELLUNG: True})
        gui._ng_automatisch_pruefen()
        self.assertTrue(self.anfragen, "es wurde gefragt")
        self.assertTrue(all("quer3q/ampr-emu-ng" in a or "/ng/" in a for a in self.anfragen),
                        "nur NG, nicht drakmor: %s" % self.anfragen)
        for variante, name in (("ng", b"libSceAmpr.sprx"), ("ng-debug", b"libSceAmpr-debug.sprx")):
            ziel = au.zielpfad(self.ordner, "0.5.0", variante)
            self.assertTrue(os.path.isfile(ziel), ziel)
            self.assertEqual(name, Path(ziel).read_bytes())
        self.assertFalse(os.path.exists(au.zielpfad(self.ordner, "0.4.1", "ng")), "was schon da ist, kommt nicht noch einmal")
        self.assertEqual("ampr.auto_start", self.protokoll[0])
        self.assertIn("ampr.auto_neue_vorgabe|fassung=0.5.0", self.protokoll)
        self.assertEqual([1], self.nachgeladen, "die Listen werden danach aufgefrischt")
        datetime.datetime.fromisoformat(self.einstellungen[au.AUTO_ZULETZT])      # eine lesbare Zeit

    def test_nicht_faellig_kein_netz(self) -> None:
        jetzt = datetime.datetime.now().isoformat(timespec="seconds")
        gui = self._gui(self._antworten(_ng_antwort("0.5.0")), {au.AUTO_EINSTELLUNG: True, au.AUTO_ZULETZT: jetzt})
        gui._ng_automatisch_pruefen()
        self.assertEqual([], self.anfragen)
        self.assertEqual([], self.protokoll)

    def test_ohne_antwort_wird_beim_naechsten_start_wiederholt(self) -> None:
        gui = self._gui(self._antworten(OSError("kein Netz")) | {"api.github.com/repos/quer3q/ampr-emu-ng": OSError("kein Netz")},
                        {au.AUTO_EINSTELLUNG: True})
        gui._ng_automatisch_pruefen()
        self.assertNotIn(au.AUTO_ZULETZT, self.einstellungen, "keine Antwort - nicht als erledigt vermerkt")
        self.assertFalse(any("auto_neue_vorgabe" in z for z in self.protokoll))
        self.assertEqual([], self.nachgeladen)

    # --- Ohne Netz: still, und es wird nichts geholt (Wunsch des Nutzers, 15.11.2026) ---

    def _offline(self, fehler: Exception | None = None):
        fehler = fehler or OSError("kein Netz")
        return self._gui(self._antworten(fehler) | {"api.github.com/repos/quer3q/ampr-emu-ng": fehler},
                         {au.AUTO_EINSTELLUNG: True})

    def test_offline_erscheint_keine_meldung(self) -> None:
        """Weder die Zeile "Suche laeuft" noch eine Fehlermeldung: Das Protokoll bleibt leer."""
        gui = self._offline()
        gui._ng_automatisch_pruefen()
        self.assertEqual([], self.protokoll, "Protokoll: %s" % self.protokoll)

    def test_offline_wird_nichts_geholt(self) -> None:
        """Eine Anfrage (die Liste, die ins Leere geht), kein Versuch, eine Datei zu laden."""
        gui = self._offline()
        gui._ng_automatisch_pruefen()
        self.assertEqual(1, len(self.anfragen), self.anfragen)
        self.assertIn("api.github.com/repos/quer3q/ampr-emu-ng", self.anfragen[0])
        self.assertEqual([], os.listdir(self.ordner), "nichts abgelegt")
        self.assertNotIn(au.AUTO_ZULETZT, self.einstellungen)
        self.assertEqual([], self.nachgeladen)

    def test_offline_jeder_art_bleibt_still(self) -> None:
        """Namensaufloesung, Zeitueberschreitung, HTTP-Fehler: Fuer die Automatik ist es dasselbe."""
        import socket
        import urllib.error
        fehler = (socket.gaierror(11001, "getaddrinfo failed"), TimeoutError("timed out"),
                  urllib.error.URLError("[Errno 11001] getaddrinfo failed"),
                  urllib.error.HTTPError("https://api.github.com/x", 403, "rate limit exceeded", {}, None))
        for f in fehler:
            with self.subTest(fehler=type(f).__name__):
                gui = self._offline(f)
                gui._ng_automatisch_pruefen()
                self.assertEqual([], self.protokoll, self.protokoll)
                self.assertEqual(1, len(self.anfragen))
                self.assertNotIn(au.AUTO_ZULETZT, self.einstellungen)

    def test_offline_steht_der_grund_in_der_protokolldatei(self) -> None:
        """Verschwiegen wird nur die Meldung im Fenster: Wer nachsieht, findet die Ursache in der Protokolldatei."""
        gui = self._offline(OSError("kein Netz fuer den Test"))
        with self.assertLogs("PS5Converter", level="INFO") as aufnahme:
            gui._ng_automatisch_pruefen()
        self.assertTrue(any("kein Netz fuer den Test" in z for z in aufnahme.output), aufnahme.output)
        self.assertFalse(any(z.startswith(("WARNING", "ERROR", "CRITICAL")) for z in aufnahme.output),
                         "eine Betriebsdiagnose ueber das Protokoll sieht darin keinen Fehler")

    def test_reisst_die_verbindung_beim_holen_ab_wird_nichts_weiter_versucht(self) -> None:
        antworten = self._antworten(_ng_antwort("0.5.0"))
        antworten["beispiel.invalid/ng/"] = lambda adresse: (_ for _ in ()).throw(OSError("abgebrochen"))
        gui = self._gui(antworten, {au.AUTO_EINSTELLUNG: True})
        gui._ng_automatisch_pruefen()
        dateien = [a for a in self.anfragen if "beispiel.invalid/ng/" in a]
        self.assertEqual(1, len(dateien), "nach dem ersten Abbruch keine weitere Datei: %s" % dateien)
        self.assertFalse(any(z.startswith("ampr.update_fehler") for z in self.protokoll), self.protokoll)
        self.assertNotIn(au.AUTO_ZULETZT, self.einstellungen, "beim naechsten Start noch einmal")
        self.assertFalse(any("auto_neue_vorgabe" in z for z in self.protokoll))

    def test_der_knopf_meldet_den_fehler_weiter(self) -> None:
        """Wer den Knopf drueckt, bekommt die Fehlermeldung - sie hat er ja bestellt."""
        gui = self._offline()
        gui._ampr_updates_arbeiten(None, nur_ng=True)
        self.assertTrue(any(z.startswith("ampr.update_suche") for z in self.protokoll), self.protokoll)
        self.assertTrue(any(z.startswith("ampr.update_fehler") for z in self.protokoll), self.protokoll)

    def test_die_zeile_suche_laeuft_kommt_erst_nach_der_antwort(self) -> None:
        gui = self._gui(self._antworten(_ng_antwort("0.4.1")), {au.AUTO_EINSTELLUNG: True})
        gui._ng_automatisch_pruefen()
        self.assertEqual("ampr.auto_start", self.protokoll[0])
        self.assertFalse(any(z.startswith("ampr.update_suche") for z in self.protokoll),
                         "die Automatik kuendigt die Anfrage nicht vorher an")

    def test_nichts_neues_zaehlt_als_erledigt_und_sagt_keine_neue_vorgabe(self) -> None:
        gui = self._gui(self._antworten(_ng_antwort("0.4.1")), {au.AUTO_EINSTELLUNG: True})
        gui._ng_automatisch_pruefen()
        self.assertIn(au.AUTO_ZULETZT, self.einstellungen)
        self.assertTrue(any(z.startswith("ampr.update_aktuell") for z in self.protokoll))
        self.assertFalse(any("auto_neue_vorgabe" in z for z in self.protokoll))
        self.assertEqual([], os.listdir(self.ordner), "nichts abgelegt")

    def test_ein_fehlschlag_beim_holen_wird_wiederholt(self) -> None:
        antworten = self._antworten(_ng_antwort("0.5.0"))
        antworten["beispiel.invalid/ng/"] = lambda adresse: (_ for _ in ()).throw(OSError("abgebrochen"))
        gui = self._gui(antworten, {au.AUTO_EINSTELLUNG: True})
        gui._ng_automatisch_pruefen()
        self.assertNotIn(au.AUTO_ZULETZT, self.einstellungen, "morgen nicht, sondern beim naechsten Start noch einmal")
        self.assertFalse(any("auto_neue_vorgabe" in z for z in self.protokoll), "nichts abgelegt, keine neue Vorgabe")
        self.assertFalse(any(z.startswith("ampr.update_fehler") for z in self.protokoll),
                         "ein Verbindungsabbruch ist keine Meldung wert")

    def test_vorabfassungen_werden_nie_geholt(self) -> None:
        gui = self._gui(self._antworten(_ng_antwort("0.4.1", vorab="0.6.0")), {au.AUTO_EINSTELLUNG: True})
        gui._ng_automatisch_pruefen()
        self.assertFalse(any("0.6.0" in a for a in self.anfragen), self.anfragen)
        self.assertFalse(os.path.exists(au.zielpfad(self.ordner, "0.6.0", "ng")))

    def test_eine_falsche_pruefsumme_kommt_nicht_in_den_bestand(self) -> None:
        antworten = self._antworten(_ng_antwort("0.5.0"))
        antworten["beispiel.invalid/ng/"] = lambda adresse: b"manipuliert!"
        gui = self._gui(antworten, {au.AUTO_EINSTELLUNG: True})
        gui._ng_automatisch_pruefen()
        self.assertFalse(os.path.exists(au.zielpfad(self.ordner, "0.5.0", "ng")))
        self.assertTrue(any("Pruefsumme" in z for z in self.protokoll), self.protokoll)
        self.assertNotIn(au.AUTO_ZULETZT, self.einstellungen)

    def test_der_knopf_ohne_automatik_vermerkt_keine_zeit_und_meldet_keine_vorgabe(self) -> None:
        """"Jetzt suchen" in den Einstellungen und der Knopf im AMPR EMU Manager: nur holen, die Automatik bleibt unberuehrt."""
        gui = self._gui(self._antworten(_ng_antwort("0.5.0")))
        gui._ampr_updates_arbeiten(None, nur_ng=True)
        self.assertTrue(os.path.isfile(au.zielpfad(self.ordner, "0.5.0", "ng")))
        self.assertNotIn(au.AUTO_ZULETZT, self.einstellungen)
        self.assertFalse(any("auto_neue_vorgabe" in z for z in self.protokoll))
        self.assertTrue(all("drakmor" not in a for a in self.anfragen), "nur_ng fragt drakmor nicht")

    def test_ohne_nur_ng_fragt_der_knopf_weiter_beide(self) -> None:
        gui = self._gui(self._antworten(_ng_antwort("0.4.1")))
        gui._ampr_updates_arbeiten(None)
        self.assertTrue(any("drakmor" in a for a in self.anfragen))
        self.assertTrue(any("quer3q" in a for a in self.anfragen))

    def test_eine_kaputte_einstellung_stoert_den_start_nicht(self) -> None:
        gui = self._gui(self._antworten(_ng_antwort("0.5.0")))
        gui._load_setting = mock.Mock(side_effect=RuntimeError("kaputt"))
        gui._ng_automatisch_pruefen()          # wirft nicht
        self.assertEqual([], self.anfragen)

    # --- Rueckmeldung an die Einstellungen (Nutzer, 16.11.2026: man sah dort nicht, ob gesucht wird) ---

    def test_die_rueckmeldung_bekommt_dieselben_zeilen_wie_das_protokoll(self) -> None:
        gui = self._gui(self._antworten(_ng_antwort("0.4.1")))
        zeilen: list[str] = []
        gui._ampr_updates_arbeiten(None, nur_ng=True, rueckmeldung=zeilen.append)
        self.assertEqual(self.protokoll, zeilen)
        self.assertEqual(["ampr.update_suche|quelle=" + au.NG_PROJEKT, "ampr.update_aktuell|neueste=NG 0.4.1"], zeilen,
                         "erst 'Suche laeuft', dann das Ergebnis")

    def test_neu_geholt_endet_mit_der_geholt_zeile(self) -> None:
        gui = self._gui(self._antworten(_ng_antwort("0.5.0", "0.4.1")))
        zeilen: list[str] = []
        gui._ampr_updates_arbeiten(None, nur_ng=True, rueckmeldung=zeilen.append)
        self.assertTrue(zeilen[0].startswith("ampr.update_suche"), zeilen)
        self.assertTrue(zeilen[1].startswith("ampr.update_gefunden"), zeilen)
        self.assertTrue(zeilen[-1].startswith("ampr.update_geholt"), zeilen)

    def test_ohne_netz_meldet_die_rueckmeldung_den_fehler(self) -> None:
        """Von Hand gedrueckt darf der Fehler sichtbar sein (nur die Automatik beim Start bleibt still)."""
        gui = self._gui(self._antworten(OSError("kein Netz")) | {"api.github.com/repos/quer3q/ampr-emu-ng": OSError("kein Netz")})
        zeilen: list[str] = []
        gui._ampr_updates_arbeiten(None, nur_ng=True, rueckmeldung=zeilen.append)
        self.assertEqual(["ampr.update_suche|quelle=" + au.NG_PROJEKT, "ampr.update_fehler|fehler=kein Netz"], zeilen)


class NachUpdatesSehenTests(unittest.TestCase):
    """Der echte ``_ampr_nach_updates_sehen`` (mit Strang): ``rueckmeldung`` und ``fertig`` kommen im Hauptstrang an."""

    def _gui(self, arbeiten):
        gui = G.__new__(G)
        gui._hauptfaden_planen = lambda f, *a, **k: f(*a)
        gui._ampr_updates_arbeiten = arbeiten
        return gui

    def test_fertig_kommt_nach_der_letzten_zeile(self) -> None:
        ereignisse: list[str] = []
        ende = threading.Event()

        def _arbeiten(danach=None, nur_ng=False, auto=False, rueckmeldung=None):
            rueckmeldung("eins")
            rueckmeldung("zwei")
            return True

        gui = self._gui(_arbeiten)
        gui._ampr_nach_updates_sehen(None, nur_ng=True, rueckmeldung=ereignisse.append,
                                     fertig=lambda: (ereignisse.append("fertig"), ende.set()))
        self.assertTrue(ende.wait(10), "der Lauf kam nicht zu Ende")
        self.assertEqual(["eins", "zwei", "fertig"], ereignisse)
        self.assertFalse(gui._ampr_update_laeuft, "danach darf wieder gesucht werden")

    def test_fertig_kommt_auch_nach_einem_fehler(self) -> None:
        ende = threading.Event()

        def _arbeiten(danach=None, nur_ng=False, auto=False, rueckmeldung=None):
            raise RuntimeError("kaputt")

        gui = self._gui(_arbeiten)
        with mock.patch.object(threading, "excepthook", lambda *a: None):             # der Strang bricht gewollt ab
            gui._ampr_nach_updates_sehen(None, nur_ng=True, fertig=ende.set)
            self.assertTrue(ende.wait(10), "ohne 'fertig' bliebe der Knopf in den Einstellungen fuer immer gesperrt")
        self.assertFalse(gui._ampr_update_laeuft)

    def test_laeuft_schon_eine_suche_startet_keine_zweite(self) -> None:
        gerufen: list[str] = []
        gui = self._gui(lambda *a, **k: gerufen.append("arbeiten"))
        gui._ampr_update_laeuft = True
        gui._ampr_nach_updates_sehen(None, nur_ng=True, rueckmeldung=gerufen.append, fertig=lambda: gerufen.append("fertig"))
        time.sleep(0.2)
        self.assertEqual([], gerufen)
        self.assertTrue(gui._ampr_update_laeuft, "die laufende Suche bleibt unangetastet")


class _Variable:
    """Vertritt eine ``tk.StringVar`` (die braucht ein Fenster): merkt sich nur den Text."""

    def __init__(self, wirft: Exception | None = None) -> None:
        self.text = ""
        self._wirft = wirft

    def set(self, text: str) -> None:
        if self._wirft is not None:
            raise self._wirft
        self.text = text


class _Knopf:
    """Vertritt den Knopf: ``state`` und ob sein Fenster noch da ist."""

    def __init__(self, existiert: bool = True) -> None:
        self.state = "normal"
        self.existiert = existiert

    def configure(self, **optionen) -> None:
        self.state = optionen.get("state", self.state)

    def winfo_exists(self) -> int:
        return 1 if self.existiert else 0


class SucheMitAnzeigeTests(unittest.TestCase):
    """``_ampr_suche_mit_anzeige``: die gemeinsame Anzeige fuer die Knoepfe in den Einstellungen und im AMPR EMU Manager.

    Nutzerwunsch 16.11.2026: Wer auf "Nach Aktualisierungen suchen" drueckt, soll dort sehen, dass gesucht wird.
    """

    def _gui(self):
        gui = G.__new__(G)
        gui._t = lambda schluessel, **w: schluessel
        gui._ampr_nach_updates_sehen = mock.Mock()
        return gui

    def test_sofort_steht_da_dass_gesucht_wird_und_der_knopf_ist_gesperrt(self) -> None:
        gui, knopf, anzeige = self._gui(), _Knopf(), _Variable()
        danach = lambda: None                                                              # noqa: E731
        gui._ampr_suche_mit_anzeige(knopf, anzeige, danach, nur_ng=True)
        self.assertEqual("ampr.update_anzeige_laeuft", anzeige.text)
        self.assertEqual("disabled", knopf.state)
        gui._ampr_nach_updates_sehen.assert_called_once()
        self.assertIs(danach, gui._ampr_nach_updates_sehen.call_args.args[0])
        self.assertTrue(gui._ampr_nach_updates_sehen.call_args.kwargs["nur_ng"])

    def test_der_manager_sucht_ohne_nur_ng(self) -> None:
        gui = self._gui()
        gui._ampr_suche_mit_anzeige(_Knopf(), _Variable(), lambda: None)
        self.assertFalse(gui._ampr_nach_updates_sehen.call_args.kwargs["nur_ng"], "der Manager fragt beide Quellen")

    def test_das_ergebnis_ersetzt_die_zeile_und_das_ende_gibt_den_knopf_frei(self) -> None:
        gui, knopf, anzeige = self._gui(), _Knopf(), _Variable()
        gui._ampr_suche_mit_anzeige(knopf, anzeige)
        kwargs = gui._ampr_nach_updates_sehen.call_args.kwargs
        kwargs["rueckmeldung"]("[AMPR] Sehe bei drakmor/ampr_emu nach neueren Fassungen…")
        kwargs["rueckmeldung"]("[AMPR] Nichts Neues – die Quelle führt 0.4.2.1, und das liegt bereits vor.")
        self.assertEqual("disabled", knopf.state, "solange der Lauf geht, bleibt er gesperrt")
        kwargs["fertig"]()
        self.assertEqual("normal", knopf.state)
        self.assertEqual("Nichts Neues – die Quelle führt 0.4.2.1, und das liegt bereits vor.", anzeige.text,
                         "ohne das [AMPR]-Kuerzel, und das Ergebnis bleibt stehen")

    def test_ohne_eigene_zeile_steht_am_ende_ein_neutraler_schluss(self) -> None:
        gui, knopf, anzeige = self._gui(), _Knopf(), _Variable()
        gui._ampr_suche_mit_anzeige(knopf, anzeige)
        gui._ampr_nach_updates_sehen.call_args.kwargs["fertig"]()
        self.assertEqual("ampr.update_anzeige_ende", anzeige.text)
        self.assertEqual("normal", knopf.state)

    def test_laeuft_schon_eine_suche_sagt_die_anzeige_es(self) -> None:
        gui, knopf, anzeige = self._gui(), _Knopf(), _Variable()
        gui._ampr_update_laeuft = True
        gui._ampr_suche_mit_anzeige(knopf, anzeige)
        self.assertEqual("ampr.update_anzeige_schon", anzeige.text)
        self.assertEqual("normal", knopf.state, "gesperrt wird nur, wer die Suche selbst gestartet hat")
        gui._ampr_nach_updates_sehen.assert_not_called()

    def test_ein_zerstoertes_fenster_stoert_die_rueckrufe_nicht(self) -> None:
        """Der Lauf dauert bis zu einer halben Minute: Wer das Fenster inzwischen schliesst, bekommt keinen Fehler."""
        import tkinter
        gui, knopf, anzeige = self._gui(), _Knopf(), _Variable()
        gui._ampr_suche_mit_anzeige(knopf, anzeige)
        kwargs = gui._ampr_nach_updates_sehen.call_args.kwargs
        anzeige._wirft = tkinter.TclError("zerstoert")
        kwargs["rueckmeldung"]("[AMPR] x")            # wirft nicht
        # Und ein Lauf ohne eigene Zeile: Auch das Setzen des neutralen Schlusses wirft nichts nach aussen.
        gui2, knopf2, anzeige2 = self._gui(), _Knopf(), _Variable()
        gui2._ampr_suche_mit_anzeige(knopf2, anzeige2)
        anzeige2._wirft = tkinter.TclError("zerstoert")
        gui2._ampr_nach_updates_sehen.call_args.kwargs["fertig"]()
        self.assertEqual("normal", knopf2.state, "der Knopf wird trotzdem freigegeben")

    def test_ein_knopf_ohne_fenster_wird_nicht_mehr_angefasst(self) -> None:
        gui, knopf, anzeige = self._gui(), _Knopf(), _Variable()
        gui._ampr_suche_mit_anzeige(knopf, anzeige)
        knopf.existiert = False
        gui._ampr_nach_updates_sehen.call_args.kwargs["fertig"]()
        self.assertEqual("disabled", knopf.state, "ein Knopf, den es nicht mehr gibt, wird nicht freigegeben")

    def test_der_manager_benutzt_die_gemeinsame_anzeige(self) -> None:
        """Der Knopf im AMPR EMU Manager ruft nicht mehr ``_ampr_nach_updates_sehen`` selbst (dann sah man dort nichts)."""
        anfang = QUELLE.index("    def _mode_ampr_manager(")
        ende = QUELLE.index("\n    def ", anfang + 10)
        manager = QUELLE[anfang:ende]
        self.assertIn("self._ampr_suche_mit_anzeige(_such_knopf, _such_text, _refresh_versions)", manager)
        self.assertNotIn("self._ampr_nach_updates_sehen(", manager)


try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:   # noqa: BLE001 - ohne Anzeige entfallen die Fenstertests
    tk = None
    _WURZEL = None
    TK_DA = False


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class DialogTests(unittest.TestCase):
    """EINSTELLUNGEN: Abschnitt "AMPR EMU NG: NEUE FASSUNGEN" mit Haken (ab Werk aus) und Knopf "Jetzt suchen"."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.konfig = os.path.join(tmp.name, "paths.json")
        Path(self.konfig).write_text("{}", encoding="utf-8")
        for p in (mock.patch.object(self.app, "_get_config_path", return_value=self.konfig),
                  mock.patch.object(self.app, "_append_to_log")):
            p.start()
            self.addCleanup(p.stop)
        self.app.__dict__["_settings_cache"] = None
        self.addCleanup(lambda: self.app.__dict__.__setitem__("_settings_cache", None))

    @staticmethod
    def _alle(widget, treffer=None):
        treffer = [] if treffer is None else treffer
        for kind in widget.winfo_children():
            treffer.append(kind)
            DialogTests._alle(kind, treffer)
        return treffer

    @staticmethod
    def _mit_text(widgets, text):
        gefunden = []
        for w in widgets:
            try:
                if str(w.cget("text")) == text:
                    gefunden.append(w)
            except (tk.TclError, AttributeError, ValueError):
                continue
        return gefunden

    def _dialog(self):
        self.app._show_settings_dialog()
        dlg = [k for k in _WURZEL.winfo_children() if isinstance(k, tk.Toplevel) and k.winfo_exists()][-1]
        self.addCleanup(lambda: dlg.winfo_exists() and dlg.destroy())
        dlg.update_idletasks()
        return dlg

    def test_haken_ab_werk_an_speichert_beim_umschalten(self) -> None:
        dlg = self._dialog()
        alle = self._alle(dlg)
        self.assertTrue(self._mit_text(alle, "AMPR EMU NG: NEUE FASSUNGEN"), "der Abschnitt ist da")
        haken = self._mit_text(alle, STRINGS["settings_dialog.ng_auto_checkbox"]["de"])
        self.assertEqual(1, len(haken))
        self.assertEqual(1, int(dlg.getvar(str(haken[0].cget("variable")))), "ab Werk an")
        haken[0].invoke()
        self.assertIs(json.loads(Path(self.konfig).read_text(encoding="utf-8")).get(au.AUTO_EINSTELLUNG), False,
                      "abgeschaltet und gespeichert")
        haken[0].invoke()
        self.assertIs(json.loads(Path(self.konfig).read_text(encoding="utf-8")).get(au.AUTO_EINSTELLUNG), True)

    def test_knopf_jetzt_suchen_fragt_nur_ng_und_ohne_automatik(self) -> None:
        dlg = self._dialog()
        knopf = self._mit_text(self._alle(dlg), STRINGS["settings_dialog.ng_auto_jetzt"]["de"])
        self.assertEqual(1, len(knopf))
        with mock.patch.object(self.app, "_ampr_nach_updates_sehen") as sehen:
            knopf[0].invoke()
        sehen.assert_called_once()
        self.assertTrue(callable(sehen.call_args.args[0]), "die Listen werden danach aufgefrischt")
        self.assertTrue(sehen.call_args.kwargs.get("nur_ng"))
        self.assertFalse(sehen.call_args.kwargs.get("auto"), "von Hand: keine Zeit vermerken, keine Automatik")

    # --- Man sieht, dass gesucht wird (Nutzer, 16.11.2026) ---

    def _texte(self, dlg) -> list[str]:
        """Alles, was im Dialog als Beschriftung steht - auch Zeilen, die ueber eine ``textvariable`` laufen."""
        texte: list[str] = []
        for w in self._alle(dlg):
            try:
                variable = str(w.cget("textvariable"))
                texte.append(str(dlg.getvar(variable)) if variable else str(w.cget("text")))
            except (tk.TclError, AttributeError, ValueError):
                continue
        return texte

    def _knopf_jetzt(self, dlg):
        knopf = self._mit_text(self._alle(dlg), STRINGS["settings_dialog.ng_auto_jetzt"]["de"])
        self.assertEqual(1, len(knopf))
        return knopf[0]

    def test_nach_dem_druck_steht_da_dass_gesucht_wird_und_der_knopf_ist_gesperrt(self) -> None:
        dlg = self._dialog()
        knopf = self._knopf_jetzt(dlg)
        laeuft = STRINGS["ampr.update_anzeige_laeuft"]["de"]
        self.assertNotIn(laeuft, self._texte(dlg), "vorher steht dort nichts")
        with mock.patch.object(self.app, "_ampr_nach_updates_sehen") as sehen:
            knopf.invoke()
        self.assertIn(laeuft, self._texte(dlg), "sofort sichtbar, noch bevor GitHub antwortet")
        self.assertEqual("disabled", str(knopf.cget("state")), "ein zweiter Druck waehrend der Suche bewirkt nichts")
        # Der Lauf meldet sich zu Ende: der Knopf ist wieder frei, und ohne eigene Zeile steht ein neutraler Schluss da.
        sehen.call_args.kwargs["fertig"]()
        self.assertEqual("normal", str(knopf.cget("state")))
        self.assertIn(STRINGS["ampr.update_anzeige_ende"]["de"], self._texte(dlg))
        self.assertNotIn(laeuft, self._texte(dlg))

    def test_das_ergebnis_ersetzt_die_laeuft_zeile_und_bleibt_nach_dem_ende_stehen(self) -> None:
        dlg = self._dialog()
        knopf = self._knopf_jetzt(dlg)
        with mock.patch.object(self.app, "_ampr_nach_updates_sehen") as sehen:
            knopf.invoke()
        zeile, fertig = sehen.call_args.kwargs["rueckmeldung"], sehen.call_args.kwargs["fertig"]
        zeile("[AMPR] Sehe bei quer3q/ampr-emu-ng nach neueren Fassungen…")
        zeile("[AMPR] Nichts Neues – die Quelle führt NG 0.4.1, und das liegt bereits vor.")
        fertig()
        texte = self._texte(dlg)
        self.assertIn("Nichts Neues – die Quelle führt NG 0.4.1, und das liegt bereits vor.", texte, "ohne das [AMPR]-Kürzel")
        self.assertNotIn(STRINGS["ampr.update_anzeige_ende"]["de"], texte, "das Ergebnis wird nicht uebermalt")
        self.assertFalse(any(t.startswith("[AMPR]") for t in texte))

    def test_laeuft_schon_eine_suche_sagt_der_dialog_es(self) -> None:
        dlg = self._dialog()
        knopf = self._knopf_jetzt(dlg)
        self.app.__dict__["_ampr_update_laeuft"] = True
        self.addCleanup(lambda: self.app.__dict__.__setitem__("_ampr_update_laeuft", False))
        with mock.patch.object(self.app, "_ampr_nach_updates_sehen") as sehen:
            knopf.invoke()
        sehen.assert_not_called()
        self.assertIn(STRINGS["ampr.update_anzeige_schon"]["de"], self._texte(dlg))
        self.assertEqual("normal", str(knopf.cget("state")), "gesperrt wird nur, wenn dieser Knopf die Suche gestartet hat")

    def test_ganzer_weg_mit_echtem_strang_und_attrappe_statt_netz(self) -> None:
        """Knopf -> Strang -> Zeile unter dem Knopf -> Knopf wieder frei; GitHub ist durch eine Attrappe ersetzt."""
        dlg = self._dialog()
        knopf = self._knopf_jetzt(dlg)
        ordner = tempfile.mkdtemp(prefix="ng_dialog_")
        self.addCleanup(lambda: __import__("shutil").rmtree(ordner, ignore_errors=True))
        bestand = [_eintrag("0.4.1", "ng"), _eintrag("0.4.1", "ng-debug")]
        # Im Test laeuft keine mainloop: ``root.after`` aus dem Strang wirft dann "main thread is not in main loop". Die
        # Rueckrufe des Strangs landen deshalb in einer Warteschlange, die der Test im Hauptstrang abarbeitet.
        warteschlange: queue.Queue = queue.Queue()

        def _planen(rueckruf, *args, ms: int = 0) -> bool:
            warteschlange.put(lambda: rueckruf(*args))
            return True

        def _abarbeiten() -> None:
            while True:
                try:
                    warteschlange.get_nowait()()
                except queue.Empty:
                    return

        with mock.patch.object(self.app, "_ampr_lade_adresse", return_value=_ng_antwort("0.4.1")), \
                mock.patch.object(self.app, "_ampr_alle_fassungen", return_value=bestand), \
                mock.patch.object(self.app, "_ampr_updates_ordner", return_value=ordner), \
                mock.patch.object(self.app, "_hauptfaden_planen", _planen):
            knopf.invoke()
            frist = time.monotonic() + 15
            while time.monotonic() < frist and (self.app.__dict__.get("_ampr_update_laeuft")
                                                or str(knopf.cget("state")) == "disabled"):
                _abarbeiten()
                _WURZEL.update()
                time.sleep(0.02)
            _abarbeiten()
            _WURZEL.update()
        texte = self._texte(dlg)
        self.assertTrue(any("Nichts Neues" in t and "NG 0.4.1" in t for t in texte), texte)
        self.assertEqual("normal", str(knopf.cget("state")), "nach dem Lauf wieder frei")


if __name__ == "__main__":
    unittest.main()
