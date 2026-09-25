# -*- coding: utf-8 -*-
"""Waechter fuer Befunde der Durchsicht, Runde 10 (24.09.2026): falsche Ergebnisse.

* **H10-3** - Umbenennen nur der Schreibweise: unter Linux auf exFAT ein
  stilles Nichts, gemeldet als Erfolg.
* **H10-5** - BACKPORT-Deckung: eine ausgefallene Pruefung hiess "alle 0
  Funktionen vorhanden".
* **U2-6** - Aktualisierungen: "(liblz4 1.9.4)" wurde zur vierten Stelle.
* **U2-7** - Aktualisierungen: ohne eine Antwort "alles auf dem Stand".
* **H3-13** - mountvol /D nahm nur den Buchstaben weg und galt als Aushaengen.
* **H9-8** - Bibliothek: Abbruch beim Verbinden startete trotzdem den RETR.
* **H12-7b** - Bibliothek: Hochladen loeschte das Ziel vor dem Umbenennen.
* **H9-11** - Bibliothek: nach einem Verbindungsabriss galten alle uebrigen
  Titel als "ohne Bild".
* **U1-7** - PKG-Leser: Klartext-Marke an falscher Stelle gesucht (die
  Pruefungen stehen in test_pkg_reader.py).
* **H10-10** - PS4-Hinweis: ein Lauf raeumte den des naechsten ab.
* **H7-4** - AMPR-Methode: nach einem Sprachwechsel still "Normal".
* **H7-10** - Arbeitskopie: nicht lesbare Unterordner still uebersprungen.
"""
from __future__ import annotations

import ast
import ftplib
import os
import shutil
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("durchsicht_runde10")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import aktualisierungen as ak      # noqa: E402
from ps5_validator.utils import konsole_ftp as kf           # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False


_BAUM: list = []


def _baum() -> ast.Module:
    if not _BAUM:
        _BAUM.append(ast.parse(Path(APP.__file__).read_text(encoding="utf-8")))
    return _BAUM[0]


def _methode(name: str) -> ast.FunctionDef:
    return next(k for k in ast.walk(_baum())
                if isinstance(k, ast.FunctionDef) and k.name == name)


def _gui():
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui._current_language = "de"
    gui.protokoll = []
    gui._append_to_log = gui.protokoll.append
    gui.root = _WURZEL
    return gui


def _ordner(test: unittest.TestCase, praefix: str) -> Path:
    pfad = Path(tempfile.mkdtemp(prefix=praefix))
    test.addCleanup(shutil.rmtree, pfad, True)
    return pfad


def _schleife_bis(bedingung, grenze: float = 15.0) -> bool:
    """Echte Ereignisschleife, bis ``bedingung`` gilt (siehe Runde 8)."""
    ende = time.monotonic() + grenze

    def _takt() -> None:
        if bedingung() or time.monotonic() > ende:
            _WURZEL.quit()
        else:
            _WURZEL.after(20, _takt)

    _WURZEL.after(20, _takt)
    _WURZEL.mainloop()
    return bool(bedingung())


def _faden_laeuft(name: str) -> bool:
    return any(f.name == name for f in threading.enumerate())


# ---------------------------------------------------------------- U2-6 / U2-7

class AktualisierungenTests(unittest.TestCase):
    """U2-6/U2-7: Fassungen vergleichen, Kopfzeile ehrlich."""

    def test_klammerzusatz_zaehlt_nicht_zur_fassung(self) -> None:
        self.assertEqual((4, 4, 5, 0), ak.fassung_teile("4.4.5 (liblz4 1.9.4)"))
        self.assertEqual(0, ak.vergleiche("4.4.5 (liblz4 1.9.4)", "4.4.5"))
        teil = ak.Bestandteil("lz4", "4.4.5 (liblz4 1.9.4)", ak.PYPI, "lz4")
        self.assertEqual(ak.AKTUELL, ak.beurteile(teil, "4.4.5").zustand)

    def test_andere_schreibweisen_bleiben(self) -> None:
        self.assertEqual((1, 8, 70, 0), ak.fassung_teile("v1.8.70"))
        self.assertEqual((1, 8, 70, 0), ak.fassung_teile("Release 1.8.70"))

    def test_ohne_antwort_nicht_auf_dem_stand(self) -> None:
        alle_fehler = [ak.Befund("a", "1", "", ak.FEHLER),
                       ak.Befund("b", "2", "", ak.FEHLER)]
        text = ak.zusammenfassung(alle_fehler)
        self.assertNotIn("auf dem Stand", text)
        self.assertIn("keine Quelle hat geantwortet", text)
        self.assertIn("2 nicht abfragbar", text)
        ohne_quelle = [ak.Befund("a", "1", "", ak.UNBEKANNT)]
        self.assertNotIn("auf dem Stand", ak.zusammenfassung(ohne_quelle))

    def test_mit_antwort_weiter_auf_dem_stand(self) -> None:
        befunde = [ak.Befund("a", "1", "1", ak.AKTUELL),
                   ak.Befund("b", "1", "", ak.FEHLER)]
        self.assertIn("auf dem Stand", ak.zusammenfassung(befunde))


# ---------------------------------------------------------------- H10-5

class BackportDeckungTests(unittest.TestCase):
    """H10-5: Eine ausgefallene Pruefung ist keine bestandene."""

    def _melden(self, ergebnis: dict) -> str:
        gui = _gui()
        gui._load_setting = lambda _schluessel, _vorgabe=None: "C:/firmware"
        with mock.patch.object(APP.ps5_backport, "firmware_ordner_fuer",
                               lambda _basis, _fw: "C:/firmware/7.61"), \
                mock.patch.object(APP.ps5_backport, "kandidaten", lambda _o: []), \
                mock.patch.object(APP.ps5_backport, "firmware_deckung",
                                  lambda _d, _s: ergebnis):
            gui._backport_ziel_deckung_melden(tempfile.gettempdir(), 7)
        return "".join(gui.protokoll)

    def test_unlesbarer_firmware_stand(self) -> None:
        text = self._melden({"bestand": 0, "verlangt": 0, "fehlend": {},
                             "ohne_datei": []})
        self.assertNotIn("angeforderten Funktionen sind vorhanden", text)
        self.assertIn("keine Exporttabelle", text)

    def test_unlesbare_spieldateien(self) -> None:
        text = self._melden({"bestand": 40, "verlangt": 0, "fehlend": {},
                             "ohne_datei": []})
        self.assertNotIn("angeforderten Funktionen sind vorhanden", text)
        self.assertIn("Spieldateien", text)

    def test_echte_deckung_wird_weiter_gemeldet(self) -> None:
        text = self._melden({"bestand": 40, "verlangt": 12, "fehlend": {},
                             "ohne_datei": []})
        self.assertIn("Alle 12 angeforderten Funktionen sind vorhanden", text)


# ---------------------------------------------------------------- H3-13

class MountvolTests(unittest.TestCase):
    """H3-13: mountvol /D ist kein Aushaengen."""

    def test_nur_der_buchstabe_ist_kein_erfolg(self) -> None:
        gui = _gui()

        def _lauf(befehl, **_k):
            erfolg = befehl and befehl[0] == "mountvol"
            return types.SimpleNamespace(returncode=0 if erfolg else 1)

        with mock.patch.object(APP.sys, "platform", "win32"), \
                mock.patch.object(APP.PS5ConverterGUI, "_volume_handles_freigeben"), \
                mock.patch.object(APP.subprocess, "run", _lauf), \
                mock.patch.object(APP.time, "sleep"), \
                mock.patch.object(APP, "ctypes", mock.MagicMock()):
            ergebnis = gui._safe_dismount_drive("X", "osfmount.com", log=False,
                                                retries=1)
        self.assertFalse(ergebnis, "Nur der Buchstabe ist weg - das Abbild haengt noch.")
        text = "".join(gui.protokoll)
        self.assertIn("mountvol", text, "Auch bei log=False muss die Warnung kommen.")
        self.assertNotIn("erfolgreich", text)


# ---------------------------------------------------------------- H9-11

class _BildFtp:
    """Ein FTP-Dienst, der fuer jedes Bild dasselbe antwortet."""

    def __init__(self, fehler: BaseException) -> None:
        self.fehler = fehler
        self.abgerufen: list = []

    def retrbinary(self, befehl, _schreiber):
        self.abgerufen.append(befehl)
        raise self.fehler

    def quit(self):
        return "221"

    def close(self):
        return None


class BibliothekBilderTests(unittest.TestCase):
    """H9-11: Verbindung weg heisst nicht "ohne Bild"."""

    def _laden(self, fehler: BaseException):
        gui = _gui()
        ftp = _BildFtp(fehler)
        gesetzt: list = []
        speicher = types.SimpleNamespace(lesen=lambda _n: "",
                                         schreiben=lambda _n, _b: "bild.png")
        gui._load_setting = lambda _schluessel, _vorgabe=None: "127.0.0.1"
        gui._ps5_ftp_port = lambda: 2121
        gui._bibliothek_bildspeicher = lambda: speicher
        gui._ampr_ftp_connect = lambda *_a, **_k: ftp
        gui._spaeter_im_fenster = lambda _f, _rueckruf, *werte: gesetzt.append(werte)
        gui._bibliothek_generation = 7
        eintraege = [{"path": "/mnt/usb0/Spiel%d.ffpfsc" % n, "kind": "ffpfsc",
                      "title_id": "PPSA0000%d" % n, "_bildfeld": object()}
                     for n in range(3)]
        gui._bibliothek_ps5_bilder_nachladen(None, eintraege, generation=7)
        for faden in list(threading.enumerate()):
            if faden.name == "bibliothek-ps5-bilder":
                faden.join(10)
        return gui, ftp, gesetzt

    def test_abriss_merkt_nichts_als_ohne_bild(self) -> None:
        gui, _ftp, gesetzt = self._laden(OSError("Verbindung abgerissen"))
        self.assertEqual(set(), gui._bibliothek_ps5_ohne_bild,
                         "Nach einem Abriss gelten alle uebrigen Titel als ohne Bild.")
        self.assertEqual(3, len(gesetzt), "Nicht jede Kachel wurde zurueckgesetzt.")

    def test_absage_des_servers_heisst_ohne_bild(self) -> None:
        gui, _ftp, _gesetzt = self._laden(ftplib.error_perm("550 No such file"))
        self.assertEqual(3, len(gui._bibliothek_ps5_ohne_bild))


# ---------------------------------------------------------------- H10-3

class SchreibweiseTests(unittest.TestCase):
    """H10-3: Nur die Schreibweise aendern - und es auch tun."""

    def test_wie_exfat_unter_linux(self) -> None:
        basis = _ordner(self, "r10_name_")
        (basis / "spiel").mkdir()
        echt = os.rename

        def _gleiche_inode(alt, neu):
            # Wie der Kern auf exFAT unter Linux: beide Namen treffen dieselbe
            # Inode - kein Fehler, keine Aenderung.
            if os.path.normcase(os.path.abspath(alt)) == os.path.normcase(os.path.abspath(neu)):
                return
            echt(alt, neu)

        with mock.patch.object(APP.os, "rename", _gleiche_inode):
            APP.PS5ConverterGUI._ordner_umbenennen(
                str(basis / "spiel"), str(basis / "Spiel"), True)
        self.assertEqual(["Spiel"], os.listdir(basis))

    def test_scheitert_der_zweite_schritt_bleibt_der_alte_name(self) -> None:
        basis = _ordner(self, "r10_name_")
        (basis / "spiel").mkdir()
        echt = os.rename

        def _zweiter_scheitert(alt, neu):
            if os.path.basename(neu) == "Spiel":
                raise PermissionError(13, "gesperrt", neu)
            echt(alt, neu)

        with mock.patch.object(APP.os, "rename", _zweiter_scheitert):
            with self.assertRaises(OSError):
                APP.PS5ConverterGUI._ordner_umbenennen(
                    str(basis / "spiel"), str(basis / "Spiel"), True)
        self.assertEqual(["spiel"], os.listdir(basis))

    def test_das_fenster_sieht_nach(self) -> None:
        text = ast.unparse(_methode("_render_dump_rename_window"))
        self.assertIn("self._ordner_umbenennen(ordner, ziel, nur_schreibweise)", text)
        self.assertIn("os.listdir(", text)


# ---------------------------------------------------------------- H10-10

class Ps4HinweisTests(unittest.TestCase):
    """H10-10: Jeder Lauf raeumt nur seinen eigenen Hinweis ab."""

    @staticmethod
    def _stand(uhr=None) -> dict:
        return {"gezeigt": set(), "laeuft": False, "fenster": None,
                "fertig": False, "uhr": uhr}

    def test_der_naechste_lauf_bleibt_unberuehrt(self) -> None:
        gui = _gui()
        erster, zweiter = self._stand(), self._stand(uhr="after#weck")
        gui._ps4_hinweis_stand = zweiter
        abgestellt: list = []
        gui.root = types.SimpleNamespace(after_cancel=abgestellt.append)
        gui._ps4_hinweis_aufraeumen(erster)
        self.assertTrue(erster["fertig"])
        self.assertFalse(zweiter["fertig"], "Der Hinweis des naechsten Laufs ist abgeraeumt.")
        self.assertEqual("after#weck", zweiter["uhr"])
        self.assertEqual([], abgestellt)

    def test_der_faden_reicht_seinen_stand_mit(self) -> None:
        aufrufe = [k for k in ast.walk(_baum())
                   if isinstance(k, ast.Call)
                   and getattr(k.func, "attr", "") == "_spaeter_im_fenster"
                   and len(k.args) >= 2
                   and getattr(k.args[1], "attr", "") == "_ps4_hinweis_aufraeumen"]
        self.assertEqual(2, len(aufrufe))
        for aufruf in aufrufe:
            with self.subTest(zeile=aufruf.lineno):
                self.assertEqual(3, len(aufruf.args),
                                 "Der Faden raeumt den aktuellen statt seinen Hinweis ab.")


# ---------------------------------------------------------------- H7-4

class AmprMethodeTests(unittest.TestCase):
    """H7-4: Die Methode des Laufs ueberlebt einen Sprachwechsel."""

    def _gui(self, text: str, tabelle: dict):
        gui = _gui()
        gui.ampr_methode_var = types.SimpleNamespace(get=lambda: text)
        gui._ampr_methode_options = dict(tabelle)
        return gui

    @staticmethod
    def _im_faden(aufruf):
        ergebnis: list = []
        faden = threading.Thread(target=lambda: ergebnis.append(aufruf()))
        faden.start()
        faden.join(10)
        return ergebnis[0]

    def test_sprachwechsel_waehrend_des_laufs(self) -> None:
        deutsch = {"Normal": APP.AMPR_METHODE_NORMAL,
                   "Asset-Pack": APP.AMPR_METHODE_ASSETPACK}
        gui = self._gui("Asset-Pack", deutsch)
        gui._lauf_variablen_festhalten()
        self.assertEqual(APP.AMPR_METHODE_ASSETPACK, gui._lauf_variablen["_ampr_methode"])
        # Waehrend des Laufs auf Englisch umgeschaltet: neue Tabelle.
        gui._ampr_methode_options = {"Normal": APP.AMPR_METHODE_NORMAL,
                                     "Asset pack": APP.AMPR_METHODE_ASSETPACK}
        self.assertEqual(APP.AMPR_METHODE_ASSETPACK, self._im_faden(gui._ampr_methode),
                         "Der Lauf faellt nach dem Sprachwechsel still auf Normal.")


# ---------------------------------------------------------------- H7-10

class ArbeitskopieTests(unittest.TestCase):
    """H7-10: Ein nicht lesbarer Unterordner bricht die Kopie ab."""

    def test_nicht_lesbarer_ordner_ist_ein_fehler(self) -> None:
        basis = _ordner(self, "r10_kopie_")
        quelle, ziel = basis / "dump", basis / "kopie"
        (quelle / "sce_sys").mkdir(parents=True)
        (quelle / "eboot.bin").write_bytes(b"E" * 64)
        (quelle / "sce_sys" / "param.json").write_bytes(b"{}")
        gui = _gui()
        gui.is_running = True
        gui._set_status = lambda *_a, **_k: None
        gesperrt = os.path.normcase(str(quelle / "sce_sys"))
        echt = os.scandir

        def _scandir(pfad="."):
            if os.path.normcase(os.fspath(pfad)) == gesperrt:
                raise PermissionError(13, "Zugriff verweigert", os.fspath(pfad))
            return echt(pfad)

        with mock.patch.object(os, "scandir", _scandir):
            with self.assertRaises(OSError):
                gui._kopieren_mit_fortschritt(str(quelle), str(ziel), 66)


# ---------------------------------------------------------------- Bibliothek

class _UebertragungsFtp:
    """Speicher-FTP fuer die Bibliotheksuebertragung (H9-8, H12-7b)."""

    def __init__(self, dateien=None, *, umbenennen_scheitert: bool = False) -> None:
        self.dateien = dict(dateien or {})
        self.umbenennen_scheitert = umbenennen_scheitert
        self.retr: list = []

    def retrbinary(self, befehl, schreiber, blocksize=8192, rest=None):
        self.retr.append(befehl)
        schreiber(self.dateien.get(befehl.split(" ", 1)[1], b""))
        return "226"

    def storbinary(self, befehl, strom, blocksize=8192, callback=None, rest=None):
        daten = b""
        while True:
            block = strom.read(blocksize)
            if not block:
                break
            daten += block
        self.dateien[befehl.split(" ", 1)[1]] = daten
        return "226"

    def rename(self, alt, neu):
        if alt not in self.dateien:
            raise ftplib.error_perm("550 %s: No such file" % alt)
        if self.umbenennen_scheitert and alt.endswith(kf.ZWISCHEN_ENDUNG):
            raise ftplib.error_perm("550 Umbenennen abgewiesen")
        self.dateien[neu] = self.dateien.pop(alt)
        return "250"

    def delete(self, pfad):
        if pfad not in self.dateien:
            raise ftplib.error_perm("550 %s: No such file" % pfad)
        del self.dateien[pfad]
        return "250"

    def quit(self):
        return "221"

    def close(self):
        return None


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class BibliothekUebertragungTests(unittest.TestCase):
    """H9-8 und H12-7b - am wirklichen Programm."""

    ENTFERNT = "/mnt/usb0/Spiel.ffpfsc"

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        _WURZEL.update_idletasks()

    def setUp(self) -> None:
        import gc
        gc.collect()

    def tearDown(self) -> None:
        import gc
        gc.collect()

    def _ersetzen(self, ziel, name: str, wert) -> None:
        flicken = mock.patch.object(ziel, name, wert)
        flicken.start()
        self.addCleanup(flicken.stop)

    def _uebertragen(self, richtung: str, oertlich: str, verbinden):
        self._ersetzen(self.app, "_ampr_ftp_connect", verbinden)
        self._ersetzen(self.app, "_ps5_ftp_port", lambda: 2121)
        for name in ("showinfo", "showwarning"):
            self._ersetzen(APP.messagebox, name, lambda *_a, **_k: None)
        self._ersetzen(APP.messagebox, "askyesno", lambda *_a, **_k: True)
        vorher = set(_WURZEL.winfo_children())
        self.app._bibliothek_uebertragen(_WURZEL, richtung=richtung, oertlich=oertlich,
                                         entfernt=self.ENTFERNT, groesse=3)
        _WURZEL.update()
        neu = [w for w in _WURZEL.winfo_children() if w not in vorher]
        self.assertTrue(neu, "Es wurde kein Fenster geoeffnet")
        for fenster in neu:
            self.addCleanup(lambda f=fenster: f.winfo_exists() and f.destroy())
        return neu[-1]

    def test_abbruch_beim_verbinden_startet_keinen_retr(self) -> None:
        ftp = _UebertragungsFtp({self.ENTFERNT: b"ABC"})
        verbunden, weiter = threading.Event(), threading.Event()

        def _verbinden(*_a, **_k):
            verbunden.set()
            weiter.wait(10)
            return ftp

        ziel = _ordner(self, "r10_bib_") / "Spiel.ffpfsc"
        fenster = self._uebertragen("runter", str(ziel), _verbinden)
        try:
            self.assertTrue(verbunden.wait(10))
            knopf = next(w for w in _alle(fenster)
                         if _text(w) == self.app._t("action.cancel"))
            knopf.invoke()
        finally:
            weiter.set()
        self.assertTrue(_schleife_bis(lambda: not _faden_laeuft("bibliothek-transfer")))
        self.assertEqual([], ftp.retr,
                         "Nach dem Abbruch lief ein RETR an - der legt ftpsrv lahm.")
        self.assertFalse(os.path.exists(str(ziel) + ".part"))

    def test_abgewiesenes_umbenennen_laesst_das_abbild(self) -> None:
        ftp = _UebertragungsFtp({self.ENTFERNT: b"ALT"}, umbenennen_scheitert=True)
        self._ersetzen(self.app, "_ftp_datei_vorhanden", lambda _ftp, _pfad: True)
        self._ersetzen(self.app, "_ask_yesno_threadsafe", lambda *_a, **_k: True)
        quelle = _ordner(self, "r10_bib_") / "Spiel.ffpfsc"
        quelle.write_bytes(b"NEU")
        self._uebertragen("hoch", str(quelle), lambda *_a, **_k: ftp)
        self.assertTrue(_schleife_bis(lambda: not _faden_laeuft("bibliothek-transfer")))
        self.assertEqual({self.ENTFERNT: b"ALT"}, ftp.dateien,
                         "Auf der Konsole fehlt danach das alte Abbild.")


def _alle(widget):
    for kind in widget.winfo_children():
        yield kind
        yield from _alle(kind)


def _text(widget) -> str:
    try:
        return str(widget.cget("text"))
    except tk.TclError:
        return ""


# ---------------------------------------------------------------- Muster

class UmbenennenMusterTests(unittest.TestCase):
    """Auf der Konsole wird nur ueber konsole_ftp.umbenennen umbenannt.

    Zweimal stand dasselbe Muster im Programm - Ziel loeschen, dann
    umbenennen (H12-7, H12-7b). Scheitert das Umbenennen, ist beides weg.
    """

    def test_kein_direktes_ftp_umbenennen(self) -> None:
        direkt = [k.lineno for k in ast.walk(_baum())
                  if isinstance(k, ast.Call)
                  and getattr(k.func, "attr", "") == "rename"
                  and not (isinstance(k.func.value, ast.Name) and k.func.value.id == "os")]
        self.assertEqual([], direkt,
                         "Zeile(n) %s benennen auf der Konsole direkt um." % direkt)


# ---------------------------------------------------------------- Texte

class TexteTests(unittest.TestCase):
    def test_zweisprachig_mit_platzhaltern(self) -> None:
        for schluessel, platzhalter in (
                ("backport.deckung_stand_unlesbar", ("{stand}",)),
                ("backport.deckung_spiel_unlesbar", ("{stand}",)),
                ("dump_rename.case_unchanged", ("{name}",)),
                ("log.auto.0024", ("{v0}",))):
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    text = STRINGS[schluessel].get(sprache, "")
                    self.assertTrue(text.strip())
                    for stelle in platzhalter:
                        self.assertIn(stelle, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
