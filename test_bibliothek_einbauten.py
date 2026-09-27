# -*- coding: utf-8 -*-
"""Einbauten je Titel in der Bibliothek - und der Start auf der PS5 (27.09.2026).

Wuensche des Nutzers:

* "Leider wird nicht angezeigt, wenn sich ein AMPR EMU, PlayGo oder Backport
  bereits im Spiel befindet. Ist es moeglich dieses anzeigen zu lassen in der
  Bibliothek?"
* "Kannst du bitte noch einen Knopf einbauen, damit man von der Bibliothek aus
  die Spiele starten kann auf der PS5."

Bewacht wird:

* Die Bewertung folgt der Reihenfolge von ShadowMount+ 1.7beta2, gemessen am
  Quelltext (``sm_fakelib.c``): erst ``backports/<ID>/fakelib2`` und
  ``.../fakelib``, dann dieselben im Spiel; ``fakelib2`` verdeckt ``fakelib``.
* Rechner: Dump-Ordner direkt, Abbilder ueber die innere Ebene (ein echtes
  exFAT-Abbild, im Test gebaut), ``.ffpkg`` heisst "nicht ermittelbar" -
  nie "keine". Das Ergebnis eines Abbilds merkt sich der Bildspeicher in einem
  eigenen Feld (in den Angaben haette es die Firmware-Abfrage uebersprungen).
* Konsole: ``backports``-Ordner zuerst, dann der Dump-Ordner; nur Listen.
* Anzeige: Detailzeile, Marken auf der Kachel (ueber das Bild gelegt, sie
  verschieben nichts), Spalte der Liste.
* Starten: Rueckfrage vorher, websrv ueber ``titelstart``, bei "nicht
  erreichbar" websrv nur auf Zuruf starten.
"""
from __future__ import annotations

import ast
import io
import os
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
pruefumgebung.umlenken("bibliothek_einbauten")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import bibliothek as bib           # noqa: E402
from ps5_validator.utils import titelstart                  # noqa: E402
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
MKPFS_ORDNER = PROJEKT / "MkPFS-1.0.0"
GUI = APP.PS5ConverterGUI
ASSET = GUI._ist_ampr_asset_datei


def _bewerten(dateien, **k):
    return bib.einbauten_bewerten(dateien, assetpack_datei=ASSET, **k)


def _schleife_bis(bedingung, grenze: float = 15.0) -> bool:
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


def _dump(basis: Path, name: str, dateien: dict[str, bytes]) -> str:
    ordner = basis / name
    (ordner / "sce_sys").mkdir(parents=True)
    (ordner / "eboot.bin").write_bytes(b"\0" * 16)
    for rel, inhalt in dateien.items():
        ziel = ordner / rel
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_bytes(inhalt)
    return str(ordner)


def _bare_gui():
    gui = GUI.__new__(GUI)
    gui._current_language = "de"
    gui._COLORS = dict(GUI._THEMES["dunkel"])
    return gui


# ---------------------------------------------------------------------------
# Die Bewertung - ohne Tk
# ---------------------------------------------------------------------------

class BewertungTests(unittest.TestCase):

    def test_ohne_bibliotheksordner(self) -> None:
        erg = _bewerten(["eboot.bin", "sce_sys/param.json"])
        self.assertEqual("", erg["ordner"])
        self.assertFalse(any(erg[k] for k in ("ampr", "playgo", "backport", "assetpack")))

    def test_alle_drei_in_fakelib(self) -> None:
        erg = _bewerten(["fakelib/libSceAmpr.sprx", "fakelib/libScePlayGo.sprx",
                         "fakelib/fw10/libSceRtc.sprx", "fakelib/fw9/libSceRtc.sprx",
                         "fakelib/notizen.txt"])
        self.assertEqual("fakelib", erg["ordner"])
        self.assertTrue(erg["ampr"])
        self.assertTrue(erg["playgo"])
        self.assertEqual(["fw9", "fw10"], erg["backport"], "Zahlenfolge, nicht Textfolge")
        self.assertFalse(erg["verdeckt"])

    def test_fakelib2_hat_vorrang_und_verdeckt(self) -> None:
        """ShadowMount+ 1.7beta2: der erste vorhandene Ordner gilt, fakelib2 zuerst."""
        erg = _bewerten(["fakelib/libSceAmpr.sprx", "fakelib2/libScePlayGo.sprx"])
        self.assertEqual("fakelib2", erg["ordner"])
        self.assertTrue(erg["verdeckt"])
        self.assertFalse(erg["ampr"], "AMPR liegt im verdeckten fakelib - wirkt nicht")
        self.assertTrue(erg["playgo"])

    def test_sicherung_und_fremde_ordner_zaehlen_nicht(self) -> None:
        for pfad in ("fakelib/libSceAmpr.sprx.orig", "meinfakelibordner/libSceAmpr.sprx",
                     "libSceAmpr.sprx", "sce_module/libSceAmpr.sprx",
                     "fakelib/sub/libSceAmpr.sprx"):
            with self.subTest(pfad=pfad):
                self.assertFalse(_bewerten([pfad])["ampr"])

    def test_huelle_rueckstrich_und_schreibweise(self) -> None:
        for pfad in ("app0/fakelib/libSceAmpr.sprx", "app0\\fakelib\\libSceAmpr.sprx",
                     "./Fakelib/LIBSCEAMPR.SPRX", "/fakelib/libSceAmpr.sprx"):
            with self.subTest(pfad=pfad):
                self.assertTrue(_bewerten([pfad])["ampr"])

    def test_asset_pack_nur_in_der_wurzel(self) -> None:
        self.assertTrue(_bewerten(["ampr_assets.index"])["assetpack"])
        self.assertTrue(_bewerten(["band_00.pak"])["assetpack"])
        self.assertFalse(_bewerten(["Media/ampr_assets.index"])["assetpack"])

    def test_ordner_ohne_dateien_aus_ftp_listen(self) -> None:
        erg = _bewerten([], ordner=["fakelib", "fakelib/fw12"])
        self.assertEqual("fakelib", erg["ordner"])
        self.assertEqual(["fw12"], erg["backport"])


class KonsoleTests(unittest.TestCase):
    """Die Konsole ueber eine nachgebaute Verzeichnisliste - nur Listen."""

    FS = {
        "/data/homebrew": {"dirs": ["backports", "PPSA00002-app"], "files": []},
        "/data/homebrew/backports": {"dirs": ["PPSA00001"], "files": []},
        "/data/homebrew/backports/PPSA00001": {"dirs": ["fakelib"], "files": []},
        "/data/homebrew/backports/PPSA00001/fakelib": {
            "dirs": [], "files": [("libSceAmpr.sprx", 10)]},
        "/data/homebrew/PPSA00002-app": {
            "dirs": ["fakelib2", "sce_sys"], "files": [("eboot.bin", 1), ("x.pak", 5)]},
        "/data/homebrew/PPSA00002-app/fakelib2": {
            "dirs": ["fw10"], "files": [("libScePlayGo.sprx", 3)]},
    }

    def setUp(self) -> None:
        self.gelistet: list = []

    def _auflisten(self, _ftp, pfad: str) -> dict:
        self.gelistet.append(pfad)
        if pfad not in self.FS:
            raise OSError("550 %s" % pfad)
        return self.FS[pfad]

    def _ist_ordner(self, _ftp, pfad: str) -> bool:
        return pfad in self.FS

    def test_ein_dump_ordner(self) -> None:
        erg = bib.einbauten_auf_konsole(None, "/data/homebrew/PPSA00002-app",
                                         auflisten=self._auflisten, assetpack_datei=ASSET)
        self.assertEqual("fakelib2", erg["ordner"])
        self.assertTrue(erg["playgo"])
        self.assertEqual(["fw10"], erg["backport"])
        self.assertTrue(erg["assetpack"])
        self.assertNotIn("/data/homebrew/PPSA00002-app/sce_sys", self.gelistet,
                         "Nur die Bibliotheksordner werden aufgelistet.")

    def test_unlesbar_ist_keine_antwort(self) -> None:
        self.assertIsNone(bib.einbauten_auf_konsole(None, "/weg", auflisten=self._auflisten))

    def test_backports_je_kennung(self) -> None:
        funde = bib.backports_auf_konsole(None, ["/data/homebrew", "/mnt/usb0/homebrew"],
                                          ist_ordner=self._ist_ordner,
                                          auflisten=self._auflisten)
        self.assertEqual({"PPSA00001": ["/data/homebrew/backports/PPSA00001"]}, funde)

    def test_die_seite_nimmt_backports_vor_dem_spiel(self) -> None:
        gui = _bare_gui()
        eintraege = [
            {"path": "/user/app/PPSA00001", "kind": "installiert", "title_id": "PPSA00001",
             "ps5": True, "meta": {}},
            {"path": "/data/homebrew/PPSA00002-app", "kind": "folder",
             "title_id": "PPSA00002", "ps5": True, "meta": {}},
            {"path": "/mnt/usb0/spiel.ffpkg", "kind": "ffpkg", "title_id": "PPSA00003",
             "ps5": True, "meta": {}},
            {"path": "/user/app/PPSA00004", "kind": "installiert", "title_id": "PPSA00004",
             "ps5": True, "meta": {}},
        ]
        with mock.patch.object(GUI, "_AMPR_GEN_SCANPFADE", ("/data/homebrew",)), \
                mock.patch.object(gui, "_ampr_ftp_is_dir", self._ist_ordner), \
                mock.patch.object(gui, "_ampr_ftp_browse", self._auflisten):
            erg = gui._bibliothek_ps5_einbauten(None, eintraege)
        self.assertTrue(erg["/user/app/PPSA00001"]["ampr"])
        self.assertEqual("/data/homebrew/backports/PPSA00001",
                         erg["/user/app/PPSA00001"]["ueber"])
        self.assertTrue(erg["/data/homebrew/PPSA00002-app"]["playgo"])
        self.assertEqual({"zustand": "unbekannt", "grund": "konsole_abbild"},
                         erg["/mnt/usb0/spiel.ffpkg"])
        self.assertEqual({"zustand": "unbekannt", "grund": "installiert"},
                         erg["/user/app/PPSA00004"])


class BildspeicherTests(unittest.TestCase):

    def setUp(self) -> None:
        self._ordner = tempfile.TemporaryDirectory()
        self.addCleanup(self._ordner.cleanup)
        self.speicher = bib.Bildspeicher(os.path.join(self._ordner.name, "cover"))
        self.datei = os.path.join(self._ordner.name, "spiel.ffpfsc")
        Path(self.datei).write_bytes(b"x")

    def test_einbauten_stehen_neben_den_angaben(self) -> None:
        self.speicher.einbauten_schreiben(self.datei, {"zustand": "ok", "ampr": True,
                                                       "backport": ["fw10"]})
        self.assertEqual({}, self.speicher.angaben_lesen(self.datei),
                         "In den Angaben haelt die Firmware-Abfrage sie fuer 'gelesen'.")
        self.assertEqual(["fw10"], self.speicher.einbauten_lesen(self.datei)["backport"])
        self.assertFalse(self.speicher.kennt_ohne_bild(self.datei))

    def test_ein_neues_abbild_hat_neue_einbauten(self) -> None:
        self.speicher.einbauten_schreiben(self.datei, {"zustand": "ok", "ampr": True})
        Path(self.datei).write_bytes(b"neu gebaut, anders gross")
        self.assertIsNone(self.speicher.einbauten_lesen(self.datei))


# ---------------------------------------------------------------------------
# Das Hauptprogramm - Rechner
# ---------------------------------------------------------------------------

class RechnerTests(unittest.TestCase):

    def setUp(self) -> None:
        self._ordner = tempfile.TemporaryDirectory()
        self.addCleanup(self._ordner.cleanup)
        self.basis = Path(self._ordner.name)
        self.gui = _bare_gui()
        self.gui.mkpfs_dir = str(MKPFS_ORDNER)
        self.speicher = bib.Bildspeicher(str(self.basis / "cover"))
        self.gui._bibliothek_bildspeicher = lambda: self.speicher

    def test_ein_dump_ordner(self) -> None:
        pfad = _dump(self.basis, "PPSA00001-app", {
            "fakelib/libSceAmpr.sprx": b"a", "fakelib/libScePlayGo.sprx": b"p",
            "fakelib/fw10/libSceRtc.sprx": b"r", "ampr_assets.index": b"i"})
        erg = self.gui._bibliothek_einbauten({"path": pfad, "kind": "folder"})
        self.assertEqual("ok", erg["zustand"])
        self.assertTrue(erg["ampr"] and erg["playgo"] and erg["assetpack"])
        self.assertEqual(["fw10"], erg["backport"])

    def test_ohne_einbau_heisst_keine(self) -> None:
        pfad = _dump(self.basis, "PPSA00002-app", {})
        erg = self.gui._bibliothek_einbauten({"path": pfad, "kind": "folder"})
        self.assertEqual(("ok", ""), (erg["zustand"], erg["ordner"]))

    def test_ffpkg_ist_nicht_ermittelbar(self) -> None:
        datei = self.basis / "spiel.ffpkg"
        datei.write_bytes(b"\0" * 64)
        self.assertEqual({"zustand": "unbekannt", "grund": "format"},
                         self.gui._bibliothek_einbauten({"path": str(datei), "kind": "ffpkg"}))

    def test_ein_echtes_exfat_abbild_und_der_speicher(self) -> None:
        sys.path.insert(0, str(MKPFS_ORDNER))
        self.addCleanup(lambda: sys.path.remove(str(MKPFS_ORDNER))
                        if str(MKPFS_ORDNER) in sys.path else None)
        from mkpfs import exfat_writer                      # noqa: PLC0415
        quelle = Path(_dump(self.basis, "PPSA00003", {
            "sce_sys/param.json": b'{"titleId":"PPSA00003"}',
            "fakelib/libSceAmpr.sprx": b"a" * 100,
            "fakelib/fw11/libSceRtc.sprx": b"r" * 100}))
        abbild = self.basis / "PPSA00003.exfat"
        abbild.write_bytes(b"".join(exfat_writer.iter_exfat_image(quelle)))
        erg = self.gui._bibliothek_einbauten({"path": str(abbild), "kind": "exfat"})
        self.assertEqual("ok", erg["zustand"])
        self.assertTrue(erg["ampr"])
        self.assertFalse(erg["playgo"])
        self.assertEqual(["fw11"], erg["backport"])
        # Beim zweiten Mal aus dem Speicher - das Abbild wird nicht mehr geoeffnet.
        with mock.patch.object(self.gui, "_container_dateien",
                               side_effect=AssertionError("wieder geoeffnet")) as lesen:
            self.assertTrue(self.gui._bibliothek_einbauten(
                {"path": str(abbild), "kind": "exfat"})["ampr"])
        lesen.assert_not_called()

    def test_unlesbares_abbild_wird_nicht_gemerkt(self) -> None:
        datei = self.basis / "kaputt.ffpfsc"
        datei.write_bytes(b"\0" * 64)
        with mock.patch.object(self.gui, "_container_dateien", return_value=None):
            erg = self.gui._bibliothek_einbauten({"path": str(datei), "kind": "ffpfsc"})
        self.assertEqual({"zustand": "unbekannt", "grund": "unlesbar"}, erg)
        self.assertIsNone(self.speicher.einbauten_lesen(str(datei)))

    def test_der_bildlader_liest_danach_die_einbauten(self) -> None:
        pfad = _dump(self.basis, "PPSA00004-app", {"fakelib/libSceAmpr.sprx": b"a"})
        eintraege = [{"path": pfad, "kind": "folder", "meta": {}}]
        geliefert: list = []
        self.gui._bibliothek_generation = 77
        self.gui._bibliothek_cover_datei = lambda _p: ""
        vorher = set(threading.enumerate())
        self.gui._bibliothek_bilder_nachladen(
            None, eintraege, generation=77,
            einbauten=(eintraege, lambda e, erg: geliefert.append((e["path"], erg))))
        for faden in set(threading.enumerate()) - vorher:
            faden.join(10)
        self.assertEqual(1, len(geliefert))
        self.assertTrue(geliefert[0][1]["ampr"])


class KonsolenladerTests(unittest.TestCase):
    """Der Bildlader der Konsole: eine Sitzung, und ohne Verbindung kein 'keine'."""

    def setUp(self) -> None:
        self._ordner = tempfile.TemporaryDirectory()
        self.addCleanup(self._ordner.cleanup)
        self.gui = _bare_gui()
        self.speicher = bib.Bildspeicher(os.path.join(self._ordner.name, "cover"))
        self.gui._bibliothek_bildspeicher = lambda: self.speicher
        self.gui._bibliothek_ps5_adresse = lambda: "192.0.2.1"
        self.gui._ps5_ftp_port = lambda: 2121
        self.gui._bibliothek_generation = 5

    def _laufen(self, eintraege, einbauten) -> list:
        verbunden: list = []

        def _verbinden(*a, **_k):
            verbunden.append(a)
            raise OSError("keine Konsole")

        vorher = set(threading.enumerate())
        with mock.patch.object(self.gui, "_ampr_ftp_connect", _verbinden):
            self.gui._bibliothek_ps5_bilder_nachladen(None, eintraege, generation=5,
                                                      einbauten=einbauten)
            for faden in set(threading.enumerate()) - vorher:
                faden.join(10)
        return verbunden

    def test_nichts_offen_heisst_keine_verbindung(self) -> None:
        self.assertEqual([], self._laufen([], ([], lambda *_a: None)))

    def test_ohne_verbindung_heisst_nicht_ermittelbar(self) -> None:
        geliefert: list = []
        eintraege = [{"path": "/data/homebrew/PPSA00001-app", "kind": "folder",
                      "title_id": "PPSA00001", "ps5": True, "meta": {}}]
        verbunden = self._laufen(eintraege, (eintraege, lambda e, erg: geliefert.append(erg)))
        self.assertEqual(1, len(verbunden), "Genau ein Verbindungsversuch.")
        self.assertEqual([{"zustand": "unbekannt", "grund": "keine_verbindung"}], geliefert)


# ---------------------------------------------------------------------------
# Texte und Quelltext
# ---------------------------------------------------------------------------

class TexteTests(unittest.TestCase):

    def test_zusammengesetzte_schluessel_gibt_es(self) -> None:
        schluessel = (["library.einbauten_grund." + g for g in (
            "format", "unlesbar", "konsole_abbild", "installiert", "keine_verbindung")]
            + [s for _m, s in GUI._KACHEL_MARKEN])
        for k in schluessel:
            for sprache in ("de", "en"):
                with self.subTest(schluessel=k, sprache=sprache):
                    self.assertTrue(STRINGS[k][sprache])

    def test_der_klick_liest_nicht_selbst(self) -> None:
        """Einbauten eines Abbilds zu lesen heisst, es zu oeffnen - nie im Klick."""
        baum = ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))
        seite = next(k for k in ast.walk(baum)
                     if isinstance(k, ast.FunctionDef) and k.name == "_render_library_window")
        zeigen = next(k for k in ast.walk(seite)
                      if isinstance(k, ast.FunctionDef) and k.name == "_details_zeigen")
        # Nur was der Klick selbst ruft - eingebettete Faden-Funktionen
        # (``_holen``) zaehlen nicht, sie laufen spaeter im Hintergrund.
        direkt = set()
        offen = list(ast.iter_child_nodes(zeigen))
        while offen:
            knoten = offen.pop()
            if isinstance(knoten, (ast.FunctionDef, ast.Lambda)):
                continue
            if isinstance(knoten, ast.Call):
                direkt.add(getattr(knoten.func, "attr", getattr(knoten.func, "id", "")))
            offen.extend(ast.iter_child_nodes(knoten))
        self.assertNotIn("_bibliothek_cover_datei", direkt,
                         "Die Pruefung zaehlt Faden-Funktionen mit.")
        self.assertNotIn("_bibliothek_einbauten", direkt)
        self.assertNotIn("_container_dateien", direkt)
        self.assertIn("_einbauten_anstossen", direkt)

    def test_der_start_fragt_vorher(self) -> None:
        baum = ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))
        starten = next(k for k in ast.walk(baum)
                       if isinstance(k, ast.FunctionDef) and k.name == "_starten")
        text = ast.unparse(starten)
        self.assertLess(text.index("askyesno"), text.index("_start_senden("))


# ---------------------------------------------------------------------------
# Die Seite am wirklichen Programm
# ---------------------------------------------------------------------------

@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class SeitenTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = GUI(_WURZEL)
        cls.app._current_language = "de"
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
        # Die Detailspalte fragt sonst nach Updates - und ginge dafuer ins Netz.
        cls._online = mock.patch.object(cls.app, "_metadaten_online_erlaubt",
                                        return_value=False)
        cls._online.start()
        cls._ordner = tempfile.TemporaryDirectory()
        basis = Path(cls._ordner.name)
        cls.alle = _dump(basis, "PPSA01325-alle", {
            "fakelib/libSceAmpr.sprx": b"a", "fakelib/libScePlayGo.sprx": b"p",
            "fakelib/fw10/libSceRtc.sprx": b"r"})
        cls.verdeckt = _dump(basis, "PPSA01326-verdeckt", {
            "fakelib/libSceAmpr.sprx": b"a", "fakelib2/leer.txt": b""})
        cls.ohne = _dump(basis, "PPSA01327-ohne", {})
        cls.ffpkg = str(basis / "PPSA01328.ffpkg")
        Path(cls.ffpkg).write_bytes(b"\0" * 64)
        cls.eintraege = [
            {"path": cls.alle, "kind": "folder", "size": None,
             "meta": {"title": "Astro Bot", "title_id": "PPSA01325"}},
            {"path": cls.verdeckt, "kind": "folder", "size": None,
             "meta": {"title": "Verdeckt", "title_id": "PPSA01326"}},
            {"path": cls.ohne, "kind": "folder", "size": None,
             "meta": {"title": "Ohne", "title_id": "PPSA01327"}},
            {"path": cls.ffpkg, "kind": "ffpkg", "size": 64,
             "meta": {"title": "Paket", "title_id": "PPSA01328"}},
        ]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app._konsole_seite_setzen("uebersicht")
        cls.app._ansicht_setzen("umwandeln")
        _WURZEL.update()
        cls._online.stop()
        cls._speichern.stop()
        cls._laden.stop()
        cls._ordner.cleanup()

    def setUp(self) -> None:
        self.app._ansicht_setzen("konsole")
        self.app._konsole_seite_setzen("bibliothek")
        _WURZEL.update()
        self.zustand = self.app._bibliothek
        self.zustand["ansicht"]["einbauten"].clear()
        self.zustand["eintraege"][:] = [dict(e) for e in self.eintraege]
        self.zustand["filtern"]()
        pfade = [e["path"] for e in self.eintraege]
        self.assertTrue(_schleife_bis(
            lambda: all(p in self.zustand["ansicht"]["einbauten"] for p in pfade)),
            "Die Einbauten kamen nicht an.")

    def tearDown(self) -> None:
        self.zustand["ansicht"]["gewaehlt"] = ""
        self.zustand["eintraege"].clear()
        self.zustand["filtern"]()

    def _eintrag(self, pfad: str) -> dict:
        return next(e for e in self.zustand["eintraege"] if e["path"] == pfad)

    def test_die_detailzeile(self) -> None:
        feld = self.zustand["zeilen"]["einbauten"]
        c = self.app._COLORS
        erwartet = {
            self.alle: ("AMPR EMU · PlayGo · BACKPORT (fw10)", c["fg_success"]),
            self.verdeckt: ("fakelib2 verdeckt fakelib", c["fg_warning"]),
            self.ohne: (STRINGS["library.einbauten_keine"]["de"], c["fg_secondary"]),
            self.ffpkg: ("nicht ermittelbar", c["fg_secondary"]),
        }
        for pfad, (stueck, farbe) in erwartet.items():
            with self.subTest(pfad=os.path.basename(pfad)):
                self.zustand["details"](self._eintrag(pfad))
                self.assertIn(stueck, feld.cget("text"))
                self.assertEqual(farbe, str(feld.cget("fg")))

    def test_marken_auf_der_kachel_verschieben_nichts(self) -> None:
        eintrag = self._eintrag(self.alle)
        texte = [m.cget("text") for m in eintrag.get("_kachel_marken", [])]
        self.assertEqual(["AMPR", "PlayGo", "BACKPORT"], texte)
        self.assertTrue(all(m.winfo_manager() == "place" for m in eintrag["_kachel_marken"]))
        self.assertEqual([], self._eintrag(self.ohne).get("_kachel_marken", []))
        self.assertEqual([], self._eintrag(self.ffpkg).get("_kachel_marken", []))
        kachel = eintrag["_kachel"]
        _WURZEL.update_idletasks()
        vorher = (kachel.winfo_reqwidth(), kachel.winfo_reqheight())
        self.app._bibliothek_kachel_marken(eintrag, {"zustand": "ok", "ampr": True})
        _WURZEL.update_idletasks()
        self.assertEqual(vorher, (kachel.winfo_reqwidth(), kachel.winfo_reqheight()))
        self.assertEqual(["AMPR"], [m.cget("text") for m in eintrag["_kachel_marken"]])

    def test_die_spalte_der_liste(self) -> None:
        baum = self.zustand["liste"]
        zellen = {baum.set(iid, "path"): baum.set(iid, "einbauten")
                  for iid in baum.get_children()}
        self.assertEqual("AMPR · PlayGo · BACKPORT", zellen[self.alle])
        self.assertEqual("–", zellen[self.ohne])
        self.assertEqual("?", zellen[self.ffpkg])


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class StartTests(unittest.TestCase):
    """Der Knopf "Auf PS5 starten" - ohne Konsole, websrv nachgebaut."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = GUI(_WURZEL)
        cls.app._current_language = "de"
        cls._laden = mock.patch.object(
            cls.app, "_load_setting",
            side_effect=lambda k, v=None, _alt=cls.app._load_setting:
            {"library_scan_folders": [], "library_quelle": "pc",
             "library_ansicht": "kacheln"}.get(k, _alt(k, v)))
        cls._laden.start()
        cls._speichern = mock.patch.object(cls.app, "_save_setting", lambda k, v: None)
        cls._speichern.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app._konsole_seite_setzen("uebersicht")
        cls.app._ansicht_setzen("umwandeln")
        _WURZEL.update()
        cls._speichern.stop()
        cls._laden.stop()

    def setUp(self) -> None:
        self.app._ansicht_setzen("konsole")
        self.app._konsole_seite_setzen("bibliothek")
        _WURZEL.update()
        self.zustand = self.app._bibliothek
        self.eintrag = {"path": "C:/x/PPSA01325-app", "kind": "folder", "size": None,
                        "meta": {"title": "Astro Bot", "title_id": "PPSA01325"}}
        self.zustand["eintraege"][:] = [self.eintrag]
        self.zustand["ansicht"]["gewaehlt"] = self.eintrag["path"]
        adresse = mock.patch.object(self.app, "_bibliothek_ps5_adresse",
                                    return_value="192.0.2.1")
        adresse.start()
        self.addCleanup(adresse.stop)

    def tearDown(self) -> None:
        self.zustand["ansicht"]["gewaehlt"] = ""
        self.zustand["eintraege"].clear()

    def _status(self) -> str:
        return self.zustand["ansicht"]["status"][0]

    def test_nein_heisst_keine_anfrage(self) -> None:
        with mock.patch.object(APP.messagebox, "askyesno", return_value=False), \
                mock.patch.object(APP.titelstart, "titel_starten") as starten:
            self.zustand["starten"]()
        starten.assert_not_called()

    def test_ja_startet_ueber_websrv(self) -> None:
        with mock.patch.object(APP.messagebox, "askyesno", return_value=True) as frage, \
                mock.patch.object(APP.titelstart, "titel_starten",
                                  return_value=(titelstart.GESTARTET, "")) as starten:
            self.zustand["starten"]()
            self.assertTrue(_schleife_bis(lambda: self._status() == "library.start_gesendet"))
        starten.assert_called_once_with("192.0.2.1", "PPSA01325")
        self.assertIn("PPSA01325", frage.call_args[0][1])
        self.assertIn("beendet", frage.call_args[0][1], "Die Rueckfrage warnt nicht.")

    def test_ohne_websrv_wird_er_nur_auf_zuruf_gestartet(self) -> None:
        antworten = iter([(titelstart.NICHT_ERREICHBAR, "refused"),
                          (titelstart.GESTARTET, "")])
        with mock.patch.object(APP.messagebox, "askyesno", return_value=True) as frage, \
                mock.patch.object(APP.titelstart, "titel_starten",
                                  side_effect=lambda *_a: next(antworten)) as starten, \
                mock.patch.object(self.app, "_konsole_dienst_starten",
                                  return_value=True) as dienst:
            self.zustand["starten"]()
            self.assertTrue(_schleife_bis(lambda: self._status() == "library.start_gesendet"))
        self.assertEqual(2, frage.call_count, "Start und websrv - je eine Frage.")
        dienst.assert_called_once()
        self.assertEqual(("websrv", "192.0.2.1"), dienst.call_args[0][:2])
        self.assertEqual(2, starten.call_count)

    def test_abgelehnt_sagt_es(self) -> None:
        with mock.patch.object(APP.messagebox, "askyesno", return_value=True), \
                mock.patch.object(APP.messagebox, "showwarning") as warnung, \
                mock.patch.object(APP.titelstart, "titel_starten",
                                  return_value=(titelstart.ABGELEHNT, "HTTP 503")):
            self.zustand["starten"]()
            self.assertTrue(_schleife_bis(lambda: warnung.called))
        self.assertIn("PPSA01325", warnung.call_args[0][1])
        self.assertEqual("library.start_gescheitert", self._status())

    def test_der_knopf_steht_in_der_detailspalte(self) -> None:
        knopf = self.zustand["start_knopf"]
        self.assertEqual("KleinAccent.TButton", str(knopf.cget("style")))
        self.assertEqual(STRINGS["library.btn_starten"]["de"], knopf.cget("text"))
        self.assertIs(self.zustand["detail"], knopf.master.master)


if __name__ == "__main__":
    unittest.main(verbosity=2)
