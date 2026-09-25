# -*- coding: utf-8 -*-
"""Der Knopf „PKG entpacken" unter WEITERE TOOLS.

Entpackt werden PS4-Pakete ueber den Entpacker, den „PS4 PKG -> ffpfsc"
schon mitbringt; PS5-Pakete werden erkannt und abgewiesen (siehe
``pkg_entpacken``). Am 21.09.2026 am echten Paket gemessen (Tetris Ultimate,
124 MB): Erfolg, Weigerung bei vorhandenem Ziel, Abbruch raeumt auf.

Hier wird das ohne echten Entpacker nachgestellt: ``subprocess.Popen`` ist
durch einen Stellvertreter ersetzt, der Zeilen wie der echte liefert und den
Teilordner anlegt. So laesst sich jeder Ausgang pruefen - auch die, die am
echten Paket kaum herbeizufuehren sind (kein Platz, Rueckgabe 0 ohne
"fertig").
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ps5_validator.utils import pkg_entpacken as pe  # noqa: E402
from ps5_validator.utils.i18n import STRINGS  # noqa: E402

HAUPTDATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "PS5ImageConverter_Pro_FINAL_revised.py")

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover
    TK_DA = False
    _WURZEL = None


def _lade_hauptprogramm():
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


def _ereignis(art: str, jetzt: int, gesamt: int, dateien: int = 0) -> str:
    return json.dumps({"event": art, "bytes_current": jetzt,
                       "bytes_total": gesamt, "files_current": dateien,
                       "files_total": 3, "files": dateien}) + "\n"


class _FalscherLauf:
    """Stellvertreter fuer ``subprocess.Popen`` des Entpackers.

    Legt den Ausgabeordner an (wie der echte Entpacker), liefert die
    vorgegebenen Zeilen und endet mit ``rc``.
    """

    def __init__(self, zeilen, rc=0):
        self._zeilen = zeilen
        self._rc = rc
        self.returncode = None
        self.beendet = False
        self.befehl = None

    def __call__(self, befehl, **_kwargs):
        self.befehl = befehl
        ausgabe = befehl[befehl.index("--output") + 1]
        os.makedirs(ausgabe, exist_ok=True)
        with open(os.path.join(ausgabe, "eboot.bin"), "wb") as datei:
            datei.write(b"\0" * 16)
        self.stdout = iter(self._zeilen)
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def terminate(self):
        self.beendet = True
        self.stdout = iter(())

    def wait(self):
        self.returncode = -15 if self.beendet else self._rc
        return self.returncode


class PaketArtTests(unittest.TestCase):
    def _datei(self, ordner, name, inhalt):
        pfad = os.path.join(ordner, name)
        with open(pfad, "wb") as datei:
            datei.write(inhalt)
        return pfad

    def test_ps4_ps5_und_fremdes(self):
        with tempfile.TemporaryDirectory() as ordner:
            self.assertEqual("ps4", pe.paket_art(self._datei(ordner, "a.pkg", b"\x7fCNT" + b"\0" * 8)))
            self.assertEqual("ps5", pe.paket_art(self._datei(ordner, "b.pkg", b"\x7fFIH" + b"\0" * 8)))
            self.assertEqual("", pe.paket_art(self._datei(ordner, "c.pkg", b"PK\x03\x04")))
            self.assertEqual("", pe.paket_art(self._datei(ordner, "d.pkg", b"")))
            self.assertEqual("", pe.paket_art(os.path.join(ordner, "fehlt.pkg")))

    def test_update_paket_ist_keine_fremde_datei(self):
        """PS5-Update-Paket (Delta, Kennung LIH) - erkannt seit 23.09.2026.

        Vorher hiess es "keine PKG-Datei", was nicht stimmt und nicht hilft.
        """
        with tempfile.TemporaryDirectory() as ordner:
            self.assertEqual("ps5_delta", pe.paket_art(self._datei(ordner, "e.pkg", b"\x7fLIH" + b"\0" * 8)))


class ZielordnerNameTests(unittest.TestCase):
    def test_spiel_patch_dlc(self):
        self.assertEqual("CUSA00775", pe.zielordner_name(
            {"title_id": "CUSA00775", "kind": "base"}, "x.pkg"))
        self.assertEqual("CUSA16627_patch_01.02", pe.zielordner_name(
            {"title_id": "CUSA16627", "kind": "patch", "app_version": "01.02"}, "x.pkg"))
        self.assertEqual("CUSA16627_dlc_OFFROAD0US", pe.zielordner_name(
            {"title_id": "CUSA16627", "kind": "dlc", "entitlement_label": "OFFROAD0US"}, "x.pkg"))

    def test_ohne_title_id_der_dateiname(self):
        self.assertEqual("Mein Paket", pe.zielordner_name({}, r"C:\a\Mein Paket.pkg"))

    def test_verbotene_zeichen_fallen_weg(self):
        name = pe.zielordner_name({"title_id": "CUSA1:2*3", "kind": "base"}, "x.pkg")
        for zeichen in '<>:"/\\|?*':
            self.assertNotIn(zeichen, name)


class PruefenTests(unittest.TestCase):
    def _lauf(self, stdout="", stderr="", rc=0):
        return mock.Mock(stdout=stdout, stderr=stderr, returncode=rc)

    def test_liest_die_letzte_json_zeile(self):
        antwort = json.dumps({"supported": True, "title_id": "CUSA00775"})
        with mock.patch.object(pe.subprocess, "run",
                               return_value=self._lauf("Vorrede\n" + antwort + "\n")) as lauf:
            info = pe.pruefen("x.exe", "a.pkg")
        self.assertEqual("CUSA00775", info["title_id"])
        # --fast immer: ohne stuerzt der Entpacker beim Pruefsummenlauf ab.
        self.assertIn("--fast", lauf.call_args[0][0])

    def test_stapelueberlauf_wird_benannt(self):
        with mock.patch.object(pe.subprocess, "run",
                               return_value=self._lauf(rc=-1073741571)):
            info = pe.pruefen("x.exe", "a.pkg")
        self.assertFalse(info["supported"])
        self.assertIn("0xC00000FD", info["reason"])

    def test_fehlendes_werkzeug_ist_keine_ausnahme(self):
        with mock.patch.object(pe.subprocess, "run", side_effect=OSError("weg")):
            info = pe.pruefen("x.exe", "a.pkg")
        self.assertFalse(info["supported"])


class EntpackenTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.basis = self._tmp.name
        self.ziel = os.path.join(self.basis, "CUSA00775")

    def tearDown(self):
        self._tmp.cleanup()

    def _laufen(self, zeilen, rc=0, **kwargs):
        falsch = _FalscherLauf(zeilen, rc)
        with mock.patch.object(pe.subprocess, "Popen", falsch):
            erg = pe.entpacken("x.exe", "a.pkg", self.ziel, **kwargs)
        return erg, falsch

    def test_erfolg_benennt_den_teilstand_um(self):
        ereignisse, zeilen = [], []
        erg, falsch = self._laufen(
            ["Hallo\n", _ereignis("extract_start", 0, 300),
             _ereignis("extract_progress", 100, 300, 1),
             _ereignis("extract_complete", 300, 300, 3)],
            melden=zeilen.append, fortschritt=ereignisse.append)
        self.assertTrue(erg["ok"], erg)
        self.assertEqual("", erg["grund"])
        self.assertEqual(300, erg["bytes"])
        self.assertTrue(os.path.isfile(os.path.join(self.ziel, "eboot.bin")))
        self.assertFalse(os.path.exists(self.ziel + ".partial"))
        self.assertEqual(["Hallo"], zeilen)
        self.assertEqual("finish", ereignisse[-1]["event"])
        # Geschrieben wird in den Teilordner, nicht ins Ziel.
        self.assertEqual(self.ziel + ".partial",
                         falsch.befehl[falsch.befehl.index("--output") + 1])

    def test_vorhandenes_ziel_wird_nicht_angefasst(self):
        os.makedirs(self.ziel)
        with mock.patch.object(pe.subprocess, "Popen") as popen:
            erg = pe.entpacken("x.exe", "a.pkg", self.ziel)
        self.assertEqual("ziel_existiert", erg["grund"])
        popen.assert_not_called()

    @unittest.skipUnless(sys.platform == "win32", "Pfadgrenze gilt nur unter Windows")
    def test_zu_langer_zielpfad(self):
        self.ziel = os.path.join(self.basis, "x" * (pe.MAX_ZIELPFAD + 5))
        with mock.patch.object(pe.subprocess, "Popen") as popen:
            erg = pe.entpacken("x.exe", "a.pkg", self.ziel)
        self.assertEqual("pfad_zu_lang", erg["grund"])
        popen.assert_not_called()

    def test_werkzeugfehler_raeumt_auf(self):
        ereignisse = []
        erg, _f = self._laufen([_ereignis("extract_start", 0, 300)], rc=3,
                               fortschritt=ereignisse.append)
        self.assertEqual("werkzeug_fehler", erg["grund"])
        self.assertEqual(3, erg["rc"])
        self.assertFalse(os.path.exists(self.ziel))
        self.assertFalse(os.path.exists(self.ziel + ".partial"))
        # Das Aufraeumen wird angesagt - keine stille Aktion.
        self.assertIn("cleanup", [e["event"] for e in ereignisse])

    def test_rueckgabe_null_ohne_fertig_ist_kein_erfolg(self):
        erg, _f = self._laufen([_ereignis("extract_start", 0, 300),
                                _ereignis("extract_progress", 100, 300)], rc=0)
        self.assertFalse(erg["ok"])
        self.assertEqual("unvollstaendig", erg["grund"])
        self.assertFalse(os.path.exists(self.ziel))

    def test_abbruch(self):
        zaehler = {"n": 0}

        def fort(_e):
            zaehler["n"] += 1

        erg, falsch = self._laufen(
            [_ereignis("extract_start", 0, 300)] +
            [_ereignis("extract_progress", i, 300) for i in range(10)],
            fortschritt=fort, abbruch=lambda: zaehler["n"] >= 2)
        self.assertEqual("abgebrochen", erg["grund"])
        self.assertTrue(falsch.beendet)
        self.assertFalse(os.path.exists(self.ziel))
        self.assertFalse(os.path.exists(self.ziel + ".partial"))

    def test_zu_wenig_platz_bricht_sofort_ab(self):
        platz = mock.Mock(free=100)
        with mock.patch.object(pe.shutil, "disk_usage", return_value=platz):
            erg, falsch = self._laufen([_ereignis("extract_start", 0, 10 ** 12),
                                        _ereignis("extract_complete", 10 ** 12, 10 ** 12)])
        self.assertEqual("kein_platz", erg["grund"])
        self.assertEqual(10 ** 12, erg["noetig"])
        self.assertEqual(100, erg["frei"])
        self.assertTrue(falsch.beendet)
        self.assertFalse(os.path.exists(self.ziel))

    def test_alter_teilstand_wird_vorher_weggeraeumt(self):
        alt = self.ziel + ".partial"
        os.makedirs(alt)
        with open(os.path.join(alt, "rest.bin"), "wb") as datei:
            datei.write(b"alt")
        erg, _f = self._laufen([_ereignis("extract_start", 0, 3),
                                _ereignis("extract_complete", 3, 3)])
        self.assertTrue(erg["ok"])
        self.assertFalse(os.path.exists(os.path.join(self.ziel, "rest.bin")))


class TexteTests(unittest.TestCase):
    def test_jeder_grund_hat_einen_text(self):
        for grund in pe.GRUENDE:
            if grund == "abgebrochen":
                continue
            with self.subTest(grund=grund):
                eintrag = STRINGS.get("pkgentpacken.grund_" + grund)
                self.assertIsNotNone(eintrag)
                self.assertTrue(eintrag.get("de"))
                self.assertTrue(eintrag.get("en"))

    def test_alle_schluessel_des_fensters_sind_zweisprachig(self):
        with open(HAUPTDATEI, encoding="utf-8") as datei:
            quelle = datei.read()
        import re
        # "pkgentpacken.grund_" ist nur ein Praefix, zusammengesetzt mit der
        # Kennung - die Texte dazu prueft test_jeder_grund_hat_einen_text.
        schluessel = {k for k in re.findall(r'"(pkgentpacken\.[a-z_]+)"', quelle)
                      if not k.endswith("_")}
        schluessel.add("titlebar.pkg_entpacken")
        self.assertGreater(len(schluessel), 20)
        for k in sorted(schluessel):
            with self.subTest(schluessel=k):
                self.assertTrue(k in STRINGS, "Schluessel fehlt: " + k)
                self.assertTrue(STRINGS[k].get("de"))
                self.assertTrue(STRINGS[k].get("en"))


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class FensterTests(unittest.TestCase):
    """Das Fenster baut sich auf; ein PS5-Paket wird abgewiesen."""

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)
        # Im Volllauf gilt sonst die Sprache des zuletzt importierten
        # Pruefmoduls (siehe test_qualitaetslauf.SpracheImPruefstandTests).
        cls.app._current_language = "de"

    def test_menueeintrag(self):
        self.assertIn(("titlebar.pkg_entpacken", "_show_pkg_entpacken"),
                      self.haupt.PS5ConverterGUI._MORE_TOOLS_ENTRIES)

    def _oeffnen(self):
        vorher = set(_WURZEL.winfo_children())
        self.app._show_pkg_entpacken()
        _WURZEL.update_idletasks()
        neu = [w for w in _WURZEL.winfo_children()
               if w not in vorher and isinstance(w, tk.Toplevel)]
        self.assertTrue(neu, "Kein Fenster geöffnet.")
        return neu[0]

    @staticmethod
    def _widgets(widget):
        for kind in widget.winfo_children():
            yield kind
            yield from FensterTests._widgets(kind)

    def _knopf(self, fenster, schluessel):
        text = self.app._t(schluessel)
        for w in self._widgets(fenster):
            try:
                if str(w.cget("text")) == text:
                    return w
            except tk.TclError:
                continue
        self.fail("Knopf fehlt: " + text)

    def test_fenster_oeffnet(self):
        fenster = self._oeffnen()
        try:
            self.assertEqual(self.app._t("pkgentpacken.window_title"), fenster.title())
            self.assertEqual("disabled", str(self._knopf(fenster, "pkgentpacken.abort_button").cget("state")))
            self.assertEqual("disabled", str(self._knopf(fenster, "pkgentpacken.open_button").cget("state")))
        finally:
            fenster.destroy()

    def test_ps5_paket_wird_abgewiesen_ohne_lauf(self):
        with tempfile.TemporaryDirectory() as ordner:
            paket = os.path.join(ordner, "ps5.pkg")
            with open(paket, "wb") as datei:
                datei.write(b"\x7fFIH" + b"\0" * 32)
            fenster = self._oeffnen()
            try:
                eingaben = [w for w in self._widgets(fenster) if isinstance(w, tk.Entry)]
                eingaben[0].insert(0, paket)
                eingaben[1].insert(0, ordner)
                with mock.patch.object(self.haupt, "messagebox") as box, \
                        mock.patch.object(self.haupt.threading, "Thread") as faden:
                    self._knopf(fenster, "pkgentpacken.start_button").invoke()
                box.showinfo.assert_called_once()
                self.assertIn("ps5.pkg", box.showinfo.call_args[0][1])
                faden.assert_not_called()
            finally:
                fenster.destroy()


if __name__ == "__main__":
    unittest.main(verbosity=2)
