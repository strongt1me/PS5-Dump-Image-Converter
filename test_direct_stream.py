# -*- coding: utf-8 -*-
"""Direct Stream - mitgeliefert und im Programm selbst gestartet (seit 05.10.2026).

Geprueft wird, was sonst erst im gebauten Programm oder beim Anwender auffiele:

* der mitgelieferte Ordner ist unveraendert (``herkunft.json``) und traegt keine
  Tests - ``pytest`` im Projektstamm saehe sie und braeuchte ``pyftpdlib``,
* jeder Import des Werkzeugs steht in den ``hiddenimports`` aller drei ``.spec``:
  PyInstaller sieht ihn nicht, weil das Werkzeug als Datenordner beiliegt und
  zur Laufzeit aus der Datei geladen wird (so fehlten schon ``tomllib`` und
  ``lz4`` in der EXE),
* der Server laeuft wirklich - gestartet und abgefragt, nicht nachgelesen: alle
  vier Dateien der Oberflaeche mit dem richtigen Typ, ``Host`` und Sitzungsmarke
  werden geprueft, "Quit app" der Seite beendet ihn, ein Neustart bekommt eine
  frische Marke,
* Adresse und FTP-Port der Konsole werden eingetragen - aber nie ueber eine
  gespeicherte Adresse geschrieben,
* der Knopf "8. Direct Stream" startet einmal, zeigt dieselbe Sitzung wieder,
  meldet Fehler und zeigt die Marke nicht in Kopfzeile und Protokoll,
* Beenden mit laufender Uebertragung fragt vorher; ein Server ohne Arbeit
  schliesst still.
"""
from __future__ import annotations

import ast
import hashlib
import http.client
import importlib.util
import json
import mimetypes
import os
import shutil
import socket
import string
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("direct_stream")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import direct_stream               # noqa: E402
from ps5_validator.utils.diagnose_befund import Diagnosebericht  # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

ORDNER = PROJEKT / direct_stream.ORDNER
HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"
SPECS = ("PS5ImageConverter_Pro.spec", "PS5ImageConverter_Pro_linux.spec",
         "PS5ImageConverter_Pro_macos.spec")
#: Neben den Dateien des Werkzeugs liegen nur diese beiden von uns.
EIGENE_BEIGABEN = {"UPSTREAM.md", "herkunft.json"}
#: Die eigenen Module des Werkzeugs - sie sind keine Fremdimporte.
EIGENE_MODULE = {"transfer_core", "ps5_streamer"}
#: Nur die Einzelinstanz-Sperre von ``main()`` braucht sie; sie laeuft im Programm nie.
NUR_SPERRE = {"fcntl", "msvcrt"}

try:
    import tkinter as tk
    # Eine Wurzel je Prozess, nie zerstoeren - siehe test_fensterlayout.py.
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    tk = None
    _WURZEL = None
    _TK_DA = False


def _text(kennung: str, /, **werte) -> str:
    return STRINGS[kennung]["de"].format(**werte)


def _werkzeug_importe() -> dict[str, set[str]]:
    """Was das Werkzeug importiert - am Syntaxbaum, auch in Funktionen."""
    namen: dict[str, set[str]] = {}
    for datei in ORDNER.rglob("*.py"):
        for knoten in ast.walk(ast.parse(datei.read_text(encoding="utf-8"))):
            if isinstance(knoten, ast.Import):
                for alias in knoten.names:
                    if alias.name.split(".")[0] not in EIGENE_MODULE:
                        namen.setdefault(alias.name, set()).add(datei.name)
            elif (isinstance(knoten, ast.ImportFrom) and knoten.level == 0
                  and knoten.module and knoten.module.split(".")[0] not in EIGENE_MODULE):
                namen.setdefault(knoten.module, set()).add(datei.name)
                # "from http import server" holt ein Untermodul - das muss
                # PyInstaller ebenso kennen.
                for alias in knoten.names:
                    voll = "%s.%s" % (knoten.module, alias.name)
                    try:
                        if importlib.util.find_spec(voll) is not None:
                            namen.setdefault(voll, set()).add(datei.name)
                    except (ImportError, ValueError):
                        continue
    return namen


def _hauptmodul_importe() -> set[str]:
    """Was das Hauptmodul auf oberster Ebene importiert - das steckt ohnehin im Bau."""
    baum = ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))
    namen: set[str] = set()
    stapel = list(baum.body)
    while stapel:
        knoten = stapel.pop()
        if isinstance(knoten, ast.Import):
            namen.update(a.name for a in knoten.names)
        elif isinstance(knoten, ast.ImportFrom) and knoten.level == 0 and knoten.module:
            namen.add(knoten.module)
        elif isinstance(knoten, ast.Try):
            stapel.extend(knoten.body + knoten.orelse + knoten.finalbody)
            for zweig in knoten.handlers:
                stapel.extend(zweig.body)
    return namen


def _hiddenimports(spec: str) -> set[str]:
    baum = ast.parse((PROJEKT / spec).read_text(encoding="utf-8"))
    for knoten in ast.walk(baum):
        if (isinstance(knoten, ast.keyword) and knoten.arg == "hiddenimports"
                and isinstance(knoten.value, ast.List)):
            return {e.value for e in knoten.value.elts
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    return set()


class OrdnerTests(unittest.TestCase):
    """Der mitgelieferte Ordner - vollstaendig, unveraendert, ohne Tests."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.herkunft = json.loads((ORDNER / "herkunft.json").read_text(encoding="utf-8"))

    def test_jede_datei_ist_byte_gleich_mit_dem_quellarchiv(self) -> None:
        dateien = self.herkunft["dateien"]
        self.assertGreaterEqual(len(dateien), 10)
        for rel, soll in dateien.items():
            with self.subTest(datei=rel):
                daten = (ORDNER / rel).read_bytes()
                self.assertEqual(soll["bytes"], len(daten))
                self.assertEqual(soll["sha256"], hashlib.sha256(daten).hexdigest())

    def test_nichts_liegt_zusaetzlich_im_ordner(self) -> None:
        vorhanden = {p.relative_to(ORDNER).as_posix() for p in ORDNER.rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts}
        self.assertEqual(set(self.herkunft["dateien"]) | EIGENE_BEIGABEN, vorhanden)

    def test_keine_tests_im_ordner(self) -> None:
        """pytest im Projektstamm sammelte sie ein - und scheiterte an pyftpdlib."""
        self.assertFalse((ORDNER / "tests").exists())
        self.assertEqual([], [p.name for p in ORDNER.rglob("test_*.py")])

    def test_die_lizenz_liegt_bei(self) -> None:
        kopf = (ORDNER / "LICENSE").read_text(encoding="utf-8")[:120]
        self.assertTrue(kopf.startswith("MIT License"))

    def test_die_fassung_wird_gelesen(self) -> None:
        self.assertEqual("2.8.1", direct_stream.fassung_lesen(str(ORDNER)))
        self.assertEqual("2.8.1", self.herkunft["fassung"])
        self.assertTrue(direct_stream.ORDNER.endswith("2.8.1"))

    def test_ohne_ordner_keine_fassung(self) -> None:
        self.assertEqual("", direct_stream.fassung_lesen(""))
        self.assertEqual("", direct_stream.fassung_lesen(str(PROJEKT / "gibt_es_nicht")))

    def test_die_lizenzdatei_des_projekts_nennt_es(self) -> None:
        text = (PROJEKT / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")
        zeile = next(z for z in text.splitlines()
                     if "Direct Stream for PlayStation 5 2.8.1" in z)
        self.assertIn("MIT-Lizenz", zeile)
        self.assertIn("DirectStream-2.8.1/LICENSE", zeile)


class BauTests(unittest.TestCase):
    """Was PyInstaller nicht sieht, muss in den drei Bauplaenen stehen."""

    def test_die_pruefung_findet_ueberhaupt_importe(self) -> None:
        """Anker - sonst waere der Test darunter stumm richtig."""
        importe = _werkzeug_importe()
        for erwartet in ("ftplib", "http.server", "ssl", "urllib.error", "mimetypes",
                         "secrets", "signal"):
            with self.subTest(modul=erwartet):
                self.assertIn(erwartet, importe)
        for spec in SPECS:
            with self.subTest(spec=spec):
                self.assertGreater(len(_hiddenimports(spec)), 20)

    def test_jeder_import_des_werkzeugs_steht_im_bauplan(self) -> None:
        schon_da = _hauptmodul_importe() | {"os", "sys"}
        benoetigt = set(_werkzeug_importe()) - schon_da - NUR_SPERRE
        self.assertIn("http.server", benoetigt)
        for spec in SPECS:
            with self.subTest(spec=spec):
                fehlend = sorted(benoetigt - _hiddenimports(spec))
                self.assertEqual([], fehlend,
                                 "%s: Importe des Werkzeugs fehlen in hiddenimports - "
                                 "im Bau liesse sich Direct Stream sonst nicht laden." % spec)

    def test_fcntl_und_msvcrt_stehen_nur_in_der_sperre(self) -> None:
        """Die Ausnahme oben gilt nur, solange nichts anderes sie braucht."""
        baum = ast.parse((ORDNER / "ps5_streamer.py").read_text(encoding="utf-8"))
        gefunden: dict[str, set[str]] = {}
        for funktion in ast.walk(baum):
            if not isinstance(funktion, ast.FunctionDef):
                continue
            for knoten in ast.walk(funktion):
                if isinstance(knoten, ast.Import):
                    for alias in knoten.names:
                        if alias.name in NUR_SPERRE:
                            gefunden.setdefault(alias.name, set()).add(funktion.name)
        self.assertEqual({"fcntl": {"_lock_instance"}, "msvcrt": {"_lock_instance"}}, gefunden)
        for knoten in baum.body:
            if isinstance(knoten, ast.Import):
                self.assertFalse({a.name for a in knoten.names} & NUR_SPERRE,
                                 "fcntl/msvcrt stehen jetzt auf oberster Ebene.")
        # Und das Programm ruft die Sperre nie: kein "_lock_instance" im Hilfsmodul.
        quelle = (PROJEKT / "ps5_validator" / "utils" / "direct_stream.py").read_text(encoding="utf-8")
        self.assertNotIn(".main(", quelle)
        self.assertNotIn("_lock_instance(", quelle)

    def test_jeder_bauplan_bettet_den_ordner_ein(self) -> None:
        aufruf = "_dateien_ohne_pycache(_direct_stream, '%s')" % direct_stream.ORDNER
        for spec in SPECS:
            with self.subTest(spec=spec):
                text = (PROJEKT / spec).read_text(encoding="utf-8")
                self.assertGreaterEqual(text.count(aufruf), 1)

    def test_der_macos_ablauf_springt_bei_aenderungen_im_ordner_an(self) -> None:
        text = (PROJEKT / ".github" / "workflows" / "macos-buendel.yml").read_text(encoding="utf-8")
        self.assertIn("'%s/**'" % direct_stream.ORDNER, text)


class ModulTests(unittest.TestCase):
    """Das Werkzeug aus der Datei laden - und was das Programm von ihm braucht."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.modul = direct_stream.module_laden(str(ORDNER))

    def test_die_benutzten_namen_gibt_es(self) -> None:
        """Eine neue Fassung, die einen davon umbenennt, faellt hier auf."""
        for name in ("ThreadingHTTPServer", "Handler", "Manager", "DEFAULTS", "VERSION",
                     "validated_settings", "atomic_json"):
            with self.subTest(name=name):
                self.assertTrue(hasattr(self.modul, name), name)
        self.assertEqual("2.8.1", self.modul.VERSION)
        for name in ("lock", "current", "snapshot", "stop"):
            with self.subTest(manager=name):
                self.assertTrue(hasattr(self.modul.Manager, name) or name in ("lock", "current"),
                                name)

    def test_ein_zweiter_aufruf_liefert_dasselbe_modul(self) -> None:
        self.assertIs(self.modul, direct_stream.module_laden(str(ORDNER)))

    def test_die_beiden_module_sind_eingetragen(self) -> None:
        """transfer_core legt eine @dataclass an, und die schlaegt ihr Modul in sys.modules nach."""
        self.assertIs(self.modul, sys.modules["ps5_streamer"])
        self.assertIn("transfer_core", sys.modules)
        self.assertTrue(sys.modules["transfer_core"].SourceInfo)

    def test_eine_fehlende_datei_wird_gemeldet(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ds_fehlt_") as leer:
            shutil.copy(ORDNER / "ps5_streamer.py", leer)
            with self.assertRaises(direct_stream.DirectStreamFehler) as ctx:
                direct_stream.module_laden(leer)
        self.assertIn("transfer_core.py", str(ctx.exception))

    def test_ein_kaputtes_modul_hinterlaesst_nichts_halbes(self) -> None:
        vorher = {n: sys.modules.get(n) for n in ("transfer_core", "ps5_streamer")}
        with tempfile.TemporaryDirectory(prefix="ds_kaputt_") as kopie:
            shutil.copy(ORDNER / "ps5_streamer.py", kopie)
            Path(kopie, "transfer_core.py").write_text("raise RuntimeError('kaputt')\n",
                                                       encoding="utf-8")
            with self.assertRaises(direct_stream.DirectStreamFehler) as ctx:
                direct_stream.module_laden(kopie)
        self.assertIn("kaputt", str(ctx.exception))
        for name, alt in vorher.items():
            with self.subTest(modul=name):
                self.assertIs(alt, sys.modules.get(name))

    def test_der_datenordner_liegt_im_einstellungsordner(self) -> None:
        self.assertEqual(os.path.join("x", "DirectStream"), direct_stream.datenordner("x"))


class VorbelegenTests(unittest.TestCase):
    """Adresse und FTP-Port der Konsole eintragen - aber nie ueber eine gespeicherte."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.modul = direct_stream.module_laden(str(ORDNER))

    def setUp(self) -> None:
        self.ordner = tempfile.mkdtemp(prefix="ds_vorbelegen_")
        self.addCleanup(shutil.rmtree, self.ordner, True)
        self.datei = Path(self.ordner, "state.json")

    def _lesen(self) -> dict:
        return json.loads(self.datei.read_text(encoding="utf-8"))

    def test_ohne_adresse_kommt_nur_der_zielordner(self) -> None:
        self.assertFalse(direct_stream.vorbelegen(self.modul, self.ordner, "", 2121),
                         "Ohne Adresse meldet es keine eingetragene Adresse.")
        einstellungen = self._lesen()["settings"]
        self.assertEqual("", einstellungen["host"])
        self.assertEqual(direct_stream.ZIELORDNER, einstellungen["folder"])
        self.assertEqual(self.modul.DEFAULTS["port"], einstellungen["port"],
                         "Ohne Adresse bleibt auch der Port beim Vorgabewert.")
        vorher = self.datei.read_bytes()
        self.assertFalse(direct_stream.vorbelegen(self.modul, self.ordner, "   ", 2121))
        self.assertEqual(vorher, self.datei.read_bytes(), "Ein zweites Mal aendert nichts.")

    def test_der_zielordner_ist_data_homebrew(self) -> None:
        """Wunsch des Nutzers vom 06.10.2026 - dort sucht ShadowMount+ immer."""
        self.assertEqual("/data/homebrew", direct_stream.ZIELORDNER)
        self.assertNotEqual(direct_stream.ZIELORDNER, self.modul.DEFAULTS["folder"],
                            "Das Werkzeug bringt einen anderen Ordner mit - sonst braeuchte es das nicht.")

    def test_frischer_ordner_traegt_adresse_port_und_zielordner_ein(self) -> None:
        self.assertTrue(direct_stream.vorbelegen(self.modul, self.ordner, "192.0.2.7", 2121))
        zustand = self._lesen()
        einstellungen = zustand["settings"]
        self.assertEqual("192.0.2.7", einstellungen["host"])
        self.assertEqual(2121, einstellungen["port"])
        self.assertEqual(direct_stream.ZIELORDNER, einstellungen["folder"])
        for schluessel, wert in self.modul.DEFAULTS.items():
            if schluessel not in ("host", "port", "folder"):
                with self.subTest(schluessel=schluessel):
                    self.assertEqual(wert, einstellungen[schluessel],
                                     "Mehr als Adresse, Port und Zielordner wurde veraendert.")
        self.assertNotIn("password", einstellungen)
        self.assertEqual([], zustand["jobs"])
        self.assertEqual("2.8.1", zustand["version"])

    def test_ohne_port_bleibt_der_vorgabewert(self) -> None:
        self.assertTrue(direct_stream.vorbelegen(self.modul, self.ordner, "192.0.2.7"))
        self.assertEqual(self.modul.DEFAULTS["port"], self._lesen()["settings"]["port"])

    def test_gespeicherte_adresse_und_zielordner_bleiben(self) -> None:
        self.datei.write_text(json.dumps({"version": "2.8.1", "jobs": [],
                                          "settings": {"host": "10.0.0.5", "port": 1337,
                                                       "folder": "/mnt/usb0"}}),
                              encoding="utf-8")
        vorher = self.datei.read_bytes()
        self.assertFalse(direct_stream.vorbelegen(self.modul, self.ordner, "192.0.2.7", 2121))
        self.assertEqual(vorher, self.datei.read_bytes(), "Die Datei wurde angefasst.")

    def test_ein_gespeicherter_zielordner_bleibt_auch_bei_neuer_adresse(self) -> None:
        self.datei.write_text(json.dumps({"version": "2.8.1", "jobs": [],
                                          "settings": {"host": "", "folder": "/mnt/usb0"}}),
                              encoding="utf-8")
        self.assertTrue(direct_stream.vorbelegen(self.modul, self.ordner, "192.0.2.7", 2121))
        einstellungen = self._lesen()["settings"]
        self.assertEqual("/mnt/usb0", einstellungen["folder"])
        self.assertEqual("192.0.2.7", einstellungen["host"])

    def test_eine_gespeicherte_adresse_ohne_zielordner_bekommt_ihn(self) -> None:
        self.datei.write_text(json.dumps({"version": "2.8.1", "jobs": [],
                                          "settings": {"host": "10.0.0.5", "port": 1337}}),
                              encoding="utf-8")
        self.assertFalse(direct_stream.vorbelegen(self.modul, self.ordner, "192.0.2.7", 2121),
                         "Die Adresse wurde nicht eingetragen - also nicht melden.")
        einstellungen = self._lesen()["settings"]
        self.assertEqual("10.0.0.5", einstellungen["host"])
        self.assertEqual(1337, einstellungen["port"])
        self.assertEqual(direct_stream.ZIELORDNER, einstellungen["folder"])

    def test_leere_adresse_wird_gefuellt_und_die_warteschlange_bleibt(self) -> None:
        job = {"id": "abc", "name": "x.pkg", "source": "http://example.com/x.pkg",
               "kind": "url", "state": "paused"}
        self.datei.write_text(json.dumps({"version": "2.8.1", "jobs": [job],
                                          "settings": {"host": "", "streams": 8}}),
                              encoding="utf-8")
        self.assertTrue(direct_stream.vorbelegen(self.modul, self.ordner, "192.0.2.7", 2121))
        zustand = self._lesen()
        self.assertEqual([job], zustand["jobs"])
        self.assertEqual(8, zustand["settings"]["streams"], "Eine eigene Einstellung ging verloren.")
        self.assertEqual("192.0.2.7", zustand["settings"]["host"])

    def test_beschaedigte_datei_wird_nicht_angefasst(self) -> None:
        self.datei.write_text("{ das ist kein json", encoding="utf-8")
        self.assertFalse(direct_stream.vorbelegen(self.modul, self.ordner, "192.0.2.7", 2121))
        self.assertEqual("{ das ist kein json", self.datei.read_text(encoding="utf-8"))

    def test_eine_untaugliche_adresse_bleibt_draussen(self) -> None:
        for adresse in ("http://192.0.2.7", "192.0.2.7:2121", "a b", "x" * 300):
            with self.subTest(adresse=adresse):
                self.assertFalse(direct_stream.vorbelegen(self.modul, self.ordner, adresse, 2121))
                einstellungen = self._lesen()["settings"]
                self.assertEqual("", einstellungen["host"])
                self.assertEqual(direct_stream.ZIELORDNER, einstellungen["folder"],
                                 "Der Zielordner kommt trotzdem hinein.")


class ServerTests(unittest.TestCase):
    """Ein echter Server auf 127.0.0.1 - gestartet, abgefragt, beendet."""

    def setUp(self) -> None:
        self.ordner = tempfile.mkdtemp(prefix="ds_server_")
        self.addCleanup(shutil.rmtree, self.ordner, True)

    def _starten(self, **optionen) -> "direct_stream.Sitzung":
        sitzung = direct_stream.starten(str(ORDNER), os.path.join(self.ordner, "daten"),
                                        **optionen)
        self.addCleanup(sitzung.beenden)
        return sitzung

    @staticmethod
    def _anfrage(sitzung, pfad, *, host=None, marke=None, methode="GET", koerper=None):
        verbindung = http.client.HTTPConnection("127.0.0.1", sitzung.port, timeout=10)
        kopf = {"Host": host or "127.0.0.1:%d" % sitzung.port}
        if marke:
            kopf["X-Session-Token"] = marke
        daten = None
        if koerper is not None:
            daten = json.dumps(koerper).encode("utf-8")
            kopf["Content-Type"] = "application/json"
        try:
            verbindung.request(methode, pfad, body=daten, headers=kopf)
            antwort = verbindung.getresponse()
            return antwort.status, antwort.getheader("Content-Type"), antwort.read()
        finally:
            verbindung.close()

    def test_start_adresse_und_marke(self) -> None:
        sitzung = self._starten()
        self.assertTrue(sitzung.laeuft)
        self.assertGreater(sitzung.port, 1023)
        self.assertGreaterEqual(len(sitzung.marke), 32)
        self.assertEqual("http://127.0.0.1:%d/#session=%s" % (sitzung.port, sitzung.marke),
                         sitzung.url)

    def test_er_lauscht_nur_auf_der_rueckschleife(self) -> None:
        sitzung = self._starten()
        self.assertEqual("127.0.0.1", sitzung._server.server_address[0])

    def test_die_vier_dateien_der_oberflaeche_mit_richtigem_typ(self) -> None:
        sitzung = self._starten()
        for pfad, typ, datei in (("/", "text/html", "index.html"),
                                 ("/app.js", "text/javascript", "app.js"),
                                 ("/style.css", "text/css", "style.css"),
                                 ("/icon.svg", "image/svg+xml", "icon.svg")):
            with self.subTest(pfad=pfad):
                status, antwort_typ, inhalt = self._anfrage(sitzung, pfad)
                self.assertEqual(200, status)
                self.assertEqual(typ, antwort_typ)
                self.assertEqual((ORDNER / "web" / datei).read_bytes(), inhalt)

    def test_ein_falscher_typ_in_der_registry_stoert_nicht(self) -> None:
        """Windows liest die Typen aus der Registry; ein falsches .js liesse die Seite leer."""
        alt = mimetypes.guess_type("x.js")[0] or "text/javascript"
        mimetypes.add_type("text/plain", ".js")
        self.addCleanup(mimetypes.add_type, alt, ".js")
        sitzung = self._starten()
        self.assertEqual("text/javascript", self._anfrage(sitzung, "/app.js")[1])

    def test_ein_fremder_host_wird_abgewiesen(self) -> None:
        sitzung = self._starten()
        self.assertEqual(403, self._anfrage(sitzung, "/", host="beispiel.test:80")[0])
        self.assertEqual(403, self._anfrage(sitzung, "/", host="127.0.0.1")[0])

    def test_die_schnittstelle_braucht_die_marke(self) -> None:
        sitzung = self._starten()
        self.assertEqual(401, self._anfrage(sitzung, "/api/state")[0])
        self.assertEqual(401, self._anfrage(sitzung, "/api/state", marke="falsch")[0])
        status, _typ, inhalt = self._anfrage(sitzung, "/api/state", marke=sitzung.marke)
        self.assertEqual(200, status)
        self.assertEqual("2.8.1", json.loads(inhalt)["version"])

    def test_adresse_und_port_stehen_in_den_einstellungen(self) -> None:
        sitzung = self._starten(host="192.0.2.7", ftp_port=2121)
        self.assertTrue(sitzung.vorbelegt)
        einstellungen = sitzung.stand()["settings"]
        self.assertEqual("192.0.2.7", einstellungen["host"])
        self.assertEqual(2121, einstellungen["port"])
        status, _typ, inhalt = self._anfrage(sitzung, "/api/state", marke=sitzung.marke)
        self.assertEqual(200, status)
        self.assertEqual("192.0.2.7", json.loads(inhalt)["settings"]["host"])

    def test_ohne_adresse_bleiben_die_vorgaben(self) -> None:
        sitzung = self._starten()
        self.assertFalse(sitzung.vorbelegt)
        self.assertEqual("", sitzung.stand()["settings"]["host"])
        # Der Zielordner des Programms gilt schon ab dem ersten Start - auch ohne Adresse.
        self.assertEqual(direct_stream.ZIELORDNER, sitzung.stand()["settings"]["folder"])

    def test_beenden_haelt_an_speichert_und_gibt_den_anschluss_frei(self) -> None:
        sitzung = self._starten(host="192.0.2.7", ftp_port=2121)
        port = sitzung.port
        anfang = time.monotonic()
        self.assertTrue(sitzung.beenden())
        self.assertLess(time.monotonic() - anfang, 5.0)
        self.assertFalse(sitzung.laeuft)
        self.assertTrue(sitzung.beenden(), "Ein zweites Beenden muss folgenlos bleiben.")
        zustand = json.loads(Path(sitzung.ordner, "state.json").read_text(encoding="utf-8"))
        self.assertEqual("192.0.2.7", zustand["settings"]["host"])
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", port), timeout=1).close()

    def test_quit_app_der_seite_beendet_den_server(self) -> None:
        sitzung = self._starten()
        status, _typ, _inhalt = self._anfrage(sitzung, "/api/shutdown", marke=sitzung.marke,
                                              methode="POST", koerper={})
        self.assertEqual(200, status)
        ende = time.monotonic() + 5.0
        while sitzung.laeuft and time.monotonic() < ende:
            time.sleep(0.05)
        self.assertFalse(sitzung.laeuft, "Der Server lief nach 'Quit app' weiter.")

    def test_jeder_start_bekommt_port_und_marke_neu(self) -> None:
        erste = self._starten()
        zweite = direct_stream.starten(str(ORDNER), os.path.join(self.ordner, "daten2"))
        self.addCleanup(zweite.beenden)
        self.assertNotEqual(erste.port, zweite.port)
        self.assertNotEqual(erste.marke, zweite.marke)
        # Die Marke der einen gilt nicht an der anderen.
        self.assertEqual(401, self._anfrage(zweite, "/api/state", marke=erste.marke)[0])
        self.assertEqual(200, self._anfrage(zweite, "/api/state", marke=zweite.marke)[0])

    def test_uebertraegt_nur_bei_einem_laufenden_auftrag(self) -> None:
        sitzung = self._starten()
        self.assertFalse(sitzung.uebertraegt())
        manager = sitzung._server.manager
        with manager.lock:
            manager.current = "auftrag"
        try:
            self.assertTrue(sitzung.uebertraegt())
        finally:
            with manager.lock:
                manager.current = None
        self.assertFalse(sitzung.uebertraegt())

    def test_ein_besetzter_ordner_ist_ein_fehler_des_aufrufers(self) -> None:
        """Ist der Datenordner eine Datei, scheitert der Start mit OSError - nicht still."""
        blockade = os.path.join(self.ordner, "datei")
        Path(blockade).write_text("x", encoding="utf-8")
        with self.assertRaises(OSError):
            direct_stream.starten(str(ORDNER), blockade)


def _knopf_programm(test: unittest.TestCase) -> "APP.PS5ConverterGUI":
    """Ein Programm ohne Oberflaeche - fuer den Knopf selbst."""
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui._t = lambda k, **w: k + "".join("|%s=%s" % (a, b) for a, b in sorted(w.items()))
    gui.root = None
    gui._current_language = "de"
    gui.protokoll = []
    gui._append_to_log = gui.protokoll.append
    gui.geoeffnet = []
    gui._webansicht_oeffnen = lambda adresse, name, herkunft: gui.geoeffnet.append(
        (adresse, name, herkunft))
    gui._ps5_ip = lambda default="": "192.0.2.9"
    gui._ps5_ftp_port = lambda: 2121
    daten = tempfile.mkdtemp(prefix="ds_knopf_")
    test.addCleanup(shutil.rmtree, daten, True)
    flicken = mock.patch.object(APP, "_direct_stream_datenordner",
                                lambda: os.path.join(daten, "DirectStream"))
    flicken.start()
    test.addCleanup(flicken.stop)
    test.addCleanup(gui._direct_stream_beenden)
    return gui


class KnopfTests(unittest.TestCase):
    """Der Knopf "8. Direct Stream" - ohne echtes Fenster, Dialoge aufgezeichnet."""

    def setUp(self) -> None:
        self.gui = _knopf_programm(self)
        self.dialoge: list = []
        for name in ("showerror", "showwarning", "showinfo"):
            flicken = mock.patch.object(
                APP.messagebox, name,
                lambda *a, _n=name, **_k: self.dialoge.append((_n,) + a))
            flicken.start()
            self.addCleanup(flicken.stop)

    def _logzeilen(self, schluessel: str) -> list:
        """Die Protokollzeilen zu einem Schluessel - ohne den Zeilenumbruch am Ende."""
        return [z.rstrip("\n") for z in self.gui.protokoll if z.startswith(schluessel)]

    def test_der_knopf_ist_der_achte_und_eine_direktaktion(self) -> None:
        klasse = APP.PS5ConverterGUI
        self.assertEqual(("konsole.btn_directstream", "directstream"), klasse._KONSOLE_KNOEPFE[7])
        self.assertEqual("_konsole_directstream_oeffnen", klasse._KONSOLE_AKTIONEN["directstream"])
        self.assertTrue(callable(getattr(klasse, "_konsole_directstream_oeffnen")))
        # Er schickt nichts an die Konsole: kein Payload, kein Webdienst, keine Seite.
        self.assertNotIn("directstream", klasse._KONSOLE_WEBDIENSTE)
        self.assertNotIn("directstream", klasse._KONSOLE_SEITEN)
        self.assertNotIn("directstream", klasse._KONSOLE_SEITENBAU)
        self.assertNotIn("directstream", klasse._KONSOLE_FENSTER)
        for sprache in ("de", "en"):
            self.assertEqual("8. Direct Stream", STRINGS["konsole.btn_directstream"][sprache])

    def test_der_knopf_startet_und_zeigt_die_seite(self) -> None:
        self.gui._konsole_directstream_oeffnen()
        sitzung = self.gui._direct_stream_sitzung
        self.assertIsNotNone(sitzung)
        self.assertTrue(sitzung.laeuft)
        self.assertEqual([(sitzung.url, "directstream.titel", "uebersicht")], self.gui.geoeffnet)
        self.assertTrue(sitzung.url.startswith("http://127.0.0.1:"))
        self.assertIn("#session=", sitzung.url)
        self.assertEqual([], self.dialoge)

    def test_adresse_und_ftp_port_kommen_aus_dem_programm(self) -> None:
        self.gui._konsole_directstream_oeffnen()
        einstellungen = self.gui._direct_stream_sitzung.stand()["settings"]
        self.assertEqual("192.0.2.9", einstellungen["host"])
        self.assertEqual(2121, einstellungen["port"])
        self.assertEqual(1, len(self._logzeilen("directstream.log_vorbelegt|adresse=192.0.2.9|port=2121")))

    def test_das_protokoll_nennt_den_port_aber_nie_die_marke(self) -> None:
        self.gui._konsole_directstream_oeffnen()
        sitzung = self.gui._direct_stream_sitzung
        zeilen = self._logzeilen("directstream.log_gestartet")
        self.assertEqual(["directstream.log_gestartet|port=%d" % sitzung.port], zeilen)
        self.assertFalse([z for z in self.gui.protokoll if sitzung.marke in z],
                         "Die Sitzungsmarke steht im Protokoll.")

    def test_ein_zweiter_druck_zeigt_dieselbe_sitzung(self) -> None:
        self.gui._konsole_directstream_oeffnen()
        erste = self.gui._direct_stream_sitzung
        self.gui._konsole_directstream_oeffnen()
        self.assertIs(erste, self.gui._direct_stream_sitzung)
        self.assertEqual(2, len(self.gui.geoeffnet))
        self.assertEqual(self.gui.geoeffnet[0], self.gui.geoeffnet[1])
        self.assertEqual(1, len(self._logzeilen("directstream.log_gestartet")),
                         "Der Start wurde zweimal gemeldet.")

    def test_nach_dem_ende_der_sitzung_startet_der_naechste_druck_eine_neue(self) -> None:
        """Die Seite hat "Quit app" bekommen oder der Server ist sonst zu."""
        self.gui._konsole_directstream_oeffnen()
        erste = self.gui._direct_stream_sitzung
        self.assertTrue(erste.beenden())
        self.gui._konsole_directstream_oeffnen()
        zweite = self.gui._direct_stream_sitzung
        self.assertIsNot(erste, zweite)
        self.assertTrue(zweite.laeuft)
        self.assertNotEqual(erste.url, zweite.url)
        self.assertEqual(2, len(self._logzeilen("directstream.log_gestartet")))
        # Die Adresse steht seit dem ersten Start in der Datei: nicht noch einmal melden.
        self.assertEqual(1, len(self._logzeilen("directstream.log_vorbelegt")))
        self.assertEqual("192.0.2.9", zweite.stand()["settings"]["host"])

    def test_ohne_bekannte_adresse_startet_er_trotzdem(self) -> None:
        self.gui._ps5_ip = lambda default="": ""
        self.gui._konsole_directstream_oeffnen()
        sitzung = self.gui._direct_stream_sitzung
        self.assertTrue(sitzung.laeuft)
        self.assertEqual("", sitzung.stand()["settings"]["host"])
        self.assertEqual([], self._logzeilen("directstream.log_vorbelegt"))
        self.assertEqual([], self.dialoge, "Der Knopf darf an der Adresse nicht scheitern.")

    def test_die_adresse_aus_dem_feld_gilt_vor_der_gemerkten(self) -> None:
        self.gui._konsole_tafel_ip = types.SimpleNamespace(get=lambda: " 192.0.2.77 ")
        self.assertEqual("192.0.2.77", self.gui._direct_stream_adresse())
        # Ein Zwischenstand beim Tippen taugt nicht - dann die gemerkte.
        self.gui._konsole_tafel_ip = types.SimpleNamespace(get=lambda: "192.0.2.")
        self.assertEqual("192.0.2.9", self.gui._direct_stream_adresse())
        self.gui._ps5_ip = lambda default="": "19."
        self.assertEqual("", self.gui._direct_stream_adresse())

    def test_ein_startfehler_wird_gemeldet_und_oeffnet_nichts(self) -> None:
        with mock.patch.object(direct_stream, "starten", side_effect=OSError("Anschluss belegt")):
            self.gui._konsole_directstream_oeffnen()
        self.assertIsNone(self.gui._direct_stream_sitzung)
        self.assertEqual([], self.gui.geoeffnet)
        self.assertEqual([("showerror", "directstream.titel",
                           "directstream.start_fehler|fehler=Anschluss belegt")],
                         [d[:3] for d in self.dialoge])
        self.assertEqual(["directstream.log_fehler|fehler=Anschluss belegt"],
                         self._logzeilen("directstream.log_fehler"))

    def test_ohne_den_ordner_eine_klare_meldung(self) -> None:
        with mock.patch.object(APP, "_direct_stream_wurzel", lambda: ""):
            self.gui._konsole_directstream_oeffnen()
        self.assertIsNone(self.gui._direct_stream_sitzung)
        self.assertEqual([], self.gui.geoeffnet)
        self.assertEqual([("showerror", "directstream.titel",
                           "directstream.fehlt|ordner=%s" % direct_stream.ORDNER)],
                         [d[:3] for d in self.dialoge])

    def test_der_ordner_wird_gefunden(self) -> None:
        self.assertEqual(os.path.normcase(str(ORDNER)), os.path.normcase(APP._direct_stream_wurzel()))

    def test_ein_ordner_ohne_kern_zaehlt_nicht(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ds_ohnekern_") as halb:
            shutil.copy(ORDNER / "ps5_streamer.py", halb)
            with mock.patch.object(APP.PS5ConverterGUI, "_mitgeliefert_finden",
                                   staticmethod(lambda _name: halb)):
                self.assertEqual("", APP._direct_stream_wurzel())

class OrtTests(unittest.TestCase):
    """Wo Direct Stream schreibt - nie neben das Programm, nie in ein macOS-Buendel."""

    def test_der_datenordner_liegt_im_einstellungsordner(self) -> None:
        erwartet = os.path.join(APP._system_konfigurationsordner(), direct_stream.DATENORDNER_NAME)
        self.assertEqual(erwartet, APP._direct_stream_datenordner())
        self.assertEqual(os.path.normcase(os.environ[pruefumgebung.UMGEBUNGSNAME]),
                         os.path.normcase(os.path.dirname(APP._direct_stream_datenordner())),
                         "Der Test schreibt nicht in den Einstellungsordner des Anwenders.")

    def test_er_liegt_nicht_neben_dem_programm(self) -> None:
        """Wer neben die Programmdatei schreibt, bricht unter macOS die Signatur des Buendels."""
        programm = os.path.dirname(os.path.abspath(APP.__file__))
        self.assertNotEqual(os.path.normcase(programm),
                            os.path.normcase(os.path.dirname(APP._direct_stream_datenordner())))


class MarkeTests(unittest.TestCase):
    """Die Sitzungsmarke steht nie in Kopfzeile, Statuszeile oder Protokoll."""

    def test_die_adresse_ohne_fragment(self) -> None:
        f = APP.PS5ConverterGUI._adresse_ohne_marke
        self.assertEqual("http://127.0.0.1:5000/", f("http://127.0.0.1:5000/#session=geheim"))
        self.assertEqual("http://10.0.0.5:7070/", f("http://10.0.0.5:7070/"))
        self.assertEqual("", f(""))
        self.assertEqual("", f(None))

    def test_die_kopfzeile_zeigt_sie_nicht(self) -> None:
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._t = lambda k, **w: k
        gui._webseite = object()
        gui._webseite_titel = mock.Mock()
        gui._webseite_adresse = mock.Mock()
        gui._webseite_melden = lambda: None
        gui._webseite_name_schluessel = "directstream.titel"
        gui._webseite_url = "http://127.0.0.1:5000/#session=geheim"
        gui._webseite_beschriften()
        gui._webseite_adresse.set.assert_called_once_with("http://127.0.0.1:5000/")

    def test_die_statuszeile_zeigt_sie_nicht(self) -> None:
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._t = lambda k, **w: "%s|%s" % (k, w.get("adresse", ""))
        gui._webseite_engine = types.SimpleNamespace(zustand="bereit", navigation=None)
        gui._webseite_status = mock.Mock()
        gui._webseite_url = "http://127.0.0.1:5000/#session=geheim"
        gui._webseite_melden()
        gui._webseite_status.set.assert_called_once_with("webseite.laedt|http://127.0.0.1:5000/")

    def test_der_browser_ausweg_oeffnet_voll_und_protokolliert_ohne(self) -> None:
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._t = lambda k, **w: "%s|%s|%s" % (k, w.get("adresse", ""), w.get("grund", ""))
        zeilen: list = []
        gui._append_to_log = zeilen.append
        with mock.patch.object(APP.webbrowser, "open") as oeffnen:
            gui._webseite_im_browser_statt("http://127.0.0.1:5000/#session=geheim", "Grund")
        oeffnen.assert_called_once_with("http://127.0.0.1:5000/#session=geheim")
        self.assertEqual(["webseite.log_browser|http://127.0.0.1:5000/|Grund\n"], zeilen)


class _AttrappeSitzung:
    """Steht fuer einen laufenden Server - mit Fuehrung ueber das, was mit ihm geschah."""

    def __init__(self, uebertraegt: bool, ablauf: list) -> None:
        self.laeuft = True
        self._uebertraegt = uebertraegt
        self._ablauf = ablauf
        self.beendet = 0

    def uebertraegt(self) -> bool:
        return self._uebertraegt

    def beenden(self, frist: float = 6.0) -> bool:
        self.beendet += 1
        self._ablauf.append("beenden")
        self.laeuft = False
        return True


class BeendenAblaufTests(unittest.TestCase):
    """Die Regeln des Beendens ohne Fenster - Aufrufe in Quelltextreihenfolge."""

    def setUp(self) -> None:
        self.gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)

    def test_ohne_sitzung_ist_nichts_zu_tun(self) -> None:
        self.assertFalse(self.gui._direct_stream_uebertraegt())
        self.gui._direct_stream_beenden()          # darf nicht werfen
        self.assertIsNone(self.gui._direct_stream_sitzung)

    def test_uebertraegt_braucht_einen_laufenden_server_und_einen_auftrag(self) -> None:
        ablauf: list = []
        self.gui._direct_stream_sitzung = _AttrappeSitzung(True, ablauf)
        self.assertTrue(self.gui._direct_stream_uebertraegt())
        self.gui._direct_stream_sitzung._uebertraegt = False
        self.assertFalse(self.gui._direct_stream_uebertraegt())
        self.gui._direct_stream_sitzung._uebertraegt = True
        self.gui._direct_stream_sitzung.laeuft = False
        self.assertFalse(self.gui._direct_stream_uebertraegt(),
                         "Ein schon beendeter Server uebertraegt nichts.")

    def test_beenden_haelt_an_und_vergisst_die_sitzung(self) -> None:
        ablauf: list = []
        sitzung = _AttrappeSitzung(False, ablauf)
        self.gui._direct_stream_sitzung = sitzung
        self.gui._direct_stream_beenden()
        self.assertEqual(1, sitzung.beendet)
        self.assertIsNone(self.gui._direct_stream_sitzung)
        self.gui._direct_stream_beenden()
        self.assertEqual(1, sitzung.beendet, "Zweimal beendet.")

    def test_hangt_der_server_wird_es_nur_protokolliert(self) -> None:
        sitzung = _AttrappeSitzung(False, [])
        sitzung.beenden = lambda frist=6.0: False
        self.gui._direct_stream_sitzung = sitzung
        with self.assertLogs(APP.logger, level="WARNING"):
            self.gui._direct_stream_beenden()
        self.assertIsNone(self.gui._direct_stream_sitzung)

    @staticmethod
    def _rufe(knoten: ast.AST) -> list:
        aufrufe = [k for k in ast.walk(knoten) if isinstance(k, ast.Call)]
        aufrufe.sort(key=lambda k: (k.lineno, k.col_offset))
        return [getattr(k.func, "attr", getattr(k.func, "id", "")) for k in aufrufe]

    def test_der_quelltext_fragt_vor_dem_abbau_und_beendet_davor(self) -> None:
        klasse = next(k for k in ast.walk(ast.parse(HAUPTDATEI.read_text(encoding="utf-8")))
                      if isinstance(k, ast.ClassDef) and k.name == "PS5ConverterGUI")
        closing = next(m for m in klasse.body
                       if isinstance(m, ast.FunctionDef) and m.name == "on_closing")
        shutdown = next(k for k in ast.walk(closing)
                        if isinstance(k, ast.FunctionDef) and k.name == "_shutdown")
        self.assertIn("_direct_stream_uebertraegt", self._rufe(closing))
        rufe = self._rufe(shutdown)
        self.assertIn("_direct_stream_beenden", rufe)
        self.assertLess(rufe.index("_auf_pkg_merge_warten"), rufe.index("_direct_stream_beenden"))
        self.assertLess(rufe.index("_direct_stream_beenden"), rufe.index("_force_dismount_all"))
        self.assertLess(rufe.index("_direct_stream_beenden"), rufe.index("_hauptfaden_planen"))


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class BeendenFensterTests(unittest.TestCase):
    """on_closing am echten Fenster - Abbau und Dialoge aufgezeichnet."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        # Der Aufbau zeigt und maximiert die Wurzel - Rueckfragen erschienen
        # sonst echt auf dem Bildschirm (siehe test_ordner_einbau.FensterTests).
        _WURZEL.withdraw()
        for kind in _WURZEL.winfo_children():
            if isinstance(kind, tk.Toplevel):
                kind.withdraw()

    def setUp(self) -> None:
        app = self.app
        app._werkzeugfenster.clear()
        self.ablauf: list[str] = []
        self.fragen: list[str] = []
        self.zerstoert = threading.Event()
        echt_planen = app._hauptfaden_planen

        def _planen(rueckruf, *args, **kwargs):
            # Das Hauptfenster wirklich zu zerstoeren, nahme allen Tests die
            # Wurzel - hier wird nur festgehalten, dass es so weit kam.
            if rueckruf == app.root.destroy:
                self.ablauf.append("destroy")
                self.zerstoert.set()
                return True
            return echt_planen(rueckruf, *args, **kwargs)

        for name, wert in (("_force_dismount_all", lambda: self.ablauf.append("dismount")),
                           ("_cleanup_exit_temp_targets", lambda **_k: None),
                           ("_fenstergeometrie_merken", lambda: None),
                           ("_hauptfaden_planen", _planen),
                           ("_append_to_log", lambda *_a, **_k: None)):
            flicken = mock.patch.object(app, name, wert)
            flicken.start()
            self.addCleanup(flicken.stop)
        self.addCleanup(self._aufraeumen)

    def _aufraeumen(self) -> None:
        self.app._direct_stream_sitzung = None
        _WURZEL.update()

    @staticmethod
    def _schleife_bis(bedingung, frist: float) -> bool:
        """Echte mainloop, bis ``bedingung`` gilt - Faeden melden sich nur dann."""
        ende = time.monotonic() + frist

        def _wache() -> None:
            if bedingung() or time.monotonic() >= ende:
                _WURZEL.quit()
                return
            _WURZEL.after(20, _wache)

        _WURZEL.after(20, _wache)
        _WURZEL.mainloop()
        return bool(bedingung())

    def _ja(self, _titel, text, **_k) -> bool:
        self.fragen.append(text)
        return True

    def _nein(self, _titel, text, **_k) -> bool:
        self.fragen.append(text)
        return False

    def test_laufende_uebertragung_fragt_und_nein_laesst_alles_laufen(self) -> None:
        sitzung = _AttrappeSitzung(True, self.ablauf)
        self.app._direct_stream_sitzung = sitzung
        with mock.patch.object(APP.messagebox, "askyesno", self._nein):
            self.app.on_closing()
        self._schleife_bis(lambda: False, 0.4)
        self.assertEqual([_text("directstream.quit_confirm")], self.fragen)
        self.assertEqual([], self.ablauf, "Nach Nein wurde beendet oder abgebaut.")
        self.assertEqual(0, sitzung.beendet)
        self.assertIs(sitzung, self.app._direct_stream_sitzung)

    def test_ja_beendet_den_server_vor_dem_abbau(self) -> None:
        sitzung = _AttrappeSitzung(True, self.ablauf)
        self.app._direct_stream_sitzung = sitzung
        with mock.patch.object(APP.messagebox, "askyesno", self._ja):
            self.app.on_closing()
        self.assertTrue(self._schleife_bis(self.zerstoert.is_set, 10.0))
        self.assertEqual([_text("directstream.quit_confirm")], self.fragen)
        self.assertEqual(["beenden", "dismount", "destroy"], self.ablauf)
        self.assertIsNone(self.app._direct_stream_sitzung)

    def test_ein_server_ohne_arbeit_schliesst_still(self) -> None:
        sitzung = _AttrappeSitzung(False, self.ablauf)
        self.app._direct_stream_sitzung = sitzung
        frage = mock.Mock(side_effect=AssertionError("unerwartete Frage"))
        with mock.patch.object(APP.messagebox, "askyesno", frage):
            self.app.on_closing()
        self.assertTrue(self._schleife_bis(self.zerstoert.is_set, 10.0))
        frage.assert_not_called()
        self.assertEqual(["beenden", "dismount", "destroy"], self.ablauf)

    def test_ohne_server_keine_frage_und_nichts_zu_beenden(self) -> None:
        self.app._direct_stream_sitzung = None
        frage = mock.Mock(side_effect=AssertionError("unerwartete Frage"))
        with mock.patch.object(APP.messagebox, "askyesno", frage):
            self.app.on_closing()
        self.assertTrue(self._schleife_bis(self.zerstoert.is_set, 10.0))
        frage.assert_not_called()
        self.assertEqual(["dismount", "destroy"], self.ablauf)

    def test_ein_echter_server_endet_mit_dem_programm(self) -> None:
        daten = tempfile.mkdtemp(prefix="ds_ende_")
        self.addCleanup(shutil.rmtree, daten, True)
        sitzung = direct_stream.starten(str(ORDNER), os.path.join(daten, "DirectStream"))
        self.addCleanup(sitzung.beenden)
        self.app._direct_stream_sitzung = sitzung
        frage = mock.Mock(side_effect=AssertionError("unerwartete Frage"))
        with mock.patch.object(APP.messagebox, "askyesno", frage):
            self.app.on_closing()
        self.assertTrue(self._schleife_bis(self.zerstoert.is_set, 10.0))
        frage.assert_not_called()
        self.assertFalse(sitzung.laeuft, "Der Server lief nach dem Beenden weiter.")


class TexteTests(unittest.TestCase):
    """Jeder Text von Knopf 8 gibt es zweisprachig - und seine Platzhalter stimmen."""

    @classmethod
    def setUpClass(cls) -> None:
        baum = ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))
        cls.aufrufe: dict[str, list[set[str]]] = {}
        for knoten in ast.walk(baum):
            if (isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Attribute)
                    and knoten.func.attr == "_t" and knoten.args
                    and isinstance(knoten.args[0], ast.Constant)
                    and isinstance(knoten.args[0].value, str)
                    and knoten.args[0].value.startswith("directstream.")):
                cls.aufrufe.setdefault(knoten.args[0].value, []).append(
                    {k.arg for k in knoten.keywords if k.arg})

    def test_die_pruefung_findet_die_aufrufe(self) -> None:
        for erwartet in ("directstream.titel", "directstream.fehlt", "directstream.start_fehler",
                         "directstream.log_fehler", "directstream.log_gestartet",
                         "directstream.log_vorbelegt", "directstream.quit_confirm"):
            with self.subTest(schluessel=erwartet):
                self.assertIn(erwartet, self.aufrufe)

    def test_jeder_benutzte_text_ist_zweisprachig(self) -> None:
        for schluessel in sorted(self.aufrufe):
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    self.assertTrue(STRINGS[schluessel].get(sprache, "").strip())

    def test_die_platzhalter_passen_zu_den_aufrufen(self) -> None:
        for schluessel, aufrufe in sorted(self.aufrufe.items()):
            for sprache in ("de", "en"):
                felder = {f for _t, f, _s, _c in string.Formatter().parse(STRINGS[schluessel][sprache]) if f}
                for uebergeben in aufrufe:
                    with self.subTest(schluessel=schluessel, sprache=sprache):
                        self.assertEqual(felder, uebergeben,
                                         "Platzhalter und Aufruf passen nicht zusammen.")

    def test_kein_text_des_knopfes_bleibt_ungenutzt(self) -> None:
        vorhanden = {k for k in STRINGS if k.startswith("directstream.")}
        self.assertEqual(vorhanden, set(self.aufrufe))

    def test_die_texte_sagen_was_gemeint_ist(self) -> None:
        self.assertIn("127.0.0.1", STRINGS["directstream.log_gestartet"]["de"])
        self.assertIn("Warteschlange", STRINGS["directstream.quit_confirm"]["de"])
        self.assertIn("queue", STRINGS["directstream.quit_confirm"]["en"])


class BerichtTests(unittest.TestCase):
    """Der Diagnosebericht fuehrt es unter dem, was mitgeliefert wird."""

    def test_der_werkzeugbestand_nennt_die_fassung(self) -> None:
        bericht = Diagnosebericht(mitgeliefert_finden=lambda rel: str(PROJEKT / rel))
        teile = {t.name: t for t in bericht._bestandteile_sammeln()}
        self.assertIn("Direct Stream", teile)
        self.assertEqual("2.8.1", teile["Direct Stream"].fassung)
        # Eine oeffentliche Quelle ist nicht bekannt - also keine Abfrage.
        self.assertEqual("ohne_quelle", teile["Direct Stream"].art)

    def test_ohne_den_ordner_kein_eintrag(self) -> None:
        bericht = Diagnosebericht(mitgeliefert_finden=lambda rel: str(PROJEKT / "gibt_es_nicht" / rel))
        self.assertNotIn("Direct Stream", {t.name for t in bericht._bestandteile_sammeln()})


if __name__ == "__main__":
    unittest.main(verbosity=2)
