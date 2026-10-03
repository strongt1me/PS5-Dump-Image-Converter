# -*- coding: utf-8 -*-
"""Der Suchlauf der Bibliothek im Hauptprogramm: Einlesen, gemerkte Angaben, Pakete, Fortschritt und Abbrechen (03.10.2026).

Zwei Gruppen:

* ``EintraegeLesenTests`` - die Methoden ``_library_funde``, ``_library_eintraege`` und ``_bibliothek_paket_angaben``
  an einem Programmobjekt ohne Fenster: Reihenfolge trotz Nebenlaeufigkeit, Zaehlung, Abbruch, gemerkte Angaben von
  Abbildern und Paketen (nie von Dump-Ordnern, nie von Fehlschlaegen), Pakete mit Titel, Kennung und Bild.
* ``SuchlaufSeiteTests`` - die Verdrahtung der Seite mit dem Fortschrittsfenster: Der Lauf meldet seine Stufen der Reihe
  nach, die Bildlader bekommen die Anzeige (Filtern und Sortieren nicht), ein neuer Lauf und ein Fehler beenden die alte
  Anzeige, "Abbrechen" macht die Faeden veraltet und sagt es in der Statuszeile. Das Fenster selbst ist in
  ``test_bibliothek_raster.SuchlaufAnzeigeTests`` geprueft - hier steht an seiner Stelle eine Attrappe.
* ``OhneHauptschleifeTests`` - die echte Seite mit dem echten Fenster, ohne Hauptschleife wie in fast allen Tests: Es
  darf kein Fortschrittsfenster stehen bleiben (im ersten Volllauf am 03.10.2026 blieb eines sichtbar stehen).
"""
from __future__ import annotations

import os
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import PS5ImageConverter_Pro_FINAL_revised as APP  # noqa: E402
from ps5_validator.utils import bibliothek as bestand  # noqa: E402
from ps5_validator.utils import bibliothek_paket as paket  # noqa: E402
from ps5_validator.utils import bibliothek_raster as raster  # noqa: E402

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False


def _sfo(werte: dict) -> bytes:
    """Eine param.sfo, wie PS4-Titel sie tragen (Zeichenketten UTF-8, Zahlen als 32 Bit)."""
    schluessel, daten, eintraege = b"", b"", []
    for name, wert in werte.items():
        if isinstance(wert, int):
            roh, art = struct.pack("<I", wert), 0x0404
        else:
            roh, art = str(wert).encode("utf-8") + b"\0", 0x0204
        eintraege.append((len(schluessel), art, len(roh), len(roh), len(daten)))
        schluessel += name.encode("utf-8") + b"\0"
        daten += roh
    while len(schluessel) % 4:
        schluessel += b"\0"
    key_ptr = 20 + 16 * len(eintraege)
    kopf = b"\0PSF" + struct.pack("<IIII", 0x0101, key_ptr, key_ptr + len(schluessel), len(eintraege))
    return kopf + b"".join(struct.pack("<HHIII", *e) for e in eintraege) + schluessel + daten


def _paket(ordner: Path, name: str, werte: dict | None, icon: bytes | None,
           content_id: str = "EP0001-CUSA00775_00-TETRISGAME000000") -> Path:
    """Ein PS4-Paket aus Kopf, Tabelle und den Eintraegen param.sfo und icon0.png."""
    eintraege: dict[int, bytes] = {}
    if werte is not None:
        eintraege[0x1000] = _sfo(werte)
    if icon is not None:
        eintraege[0x1200] = icon
    kopf = bytearray(paket.KOPF_GROESSE)
    kopf[0:4] = paket.CNT_MAGIC
    struct.pack_into(">I", kopf, 0x10, len(eintraege))
    struct.pack_into(">I", kopf, 0x18, paket.KOPF_GROESSE)
    kopf[0x40:0x40 + len(content_id)] = content_id.encode("ascii")
    lage = paket.KOPF_GROESSE + len(eintraege) * paket.EINTRAG_GROESSE
    tabelle, daten = b"", b""
    for kennung, inhalt in eintraege.items():
        tabelle += struct.pack(">IIIIII8x", kennung, 0, 0, 0, lage + len(daten), len(inhalt))
        daten += inhalt
    pfad = ordner / name
    pfad.write_bytes(bytes(kopf) + tabelle + daten + b"\0" * 4096)
    return pfad


def _dump(ordner: Path, kennung: str = "PPSA00001") -> Path:
    (ordner / "sce_sys").mkdir(parents=True, exist_ok=True)
    (ordner / "sce_sys" / "param.json").write_text('{"titleId": "%s"}' % kennung, encoding="utf-8")
    (ordner / "eboot.bin").write_bytes(b"\x7fELF" + b"\0" * 64)
    return ordner


def _png_bytes() -> bytes:
    import io
    from PIL import Image
    puffer = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 30, 30)).save(puffer, "PNG")
    return puffer.getvalue()


def _gui_ohne_fenster(speicher_ordner: str):
    """Ein Programmobjekt ohne Tk-Fenster mit eigenem Bildspeicher (kein Zugriff auf den Ordner des Anwenders)."""
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui._preview_cache = {}
    gui._preview_report_dir_cache = {}
    gui._bibliothek_bilder = bestand.Bildspeicher(speicher_ordner)
    return gui


class EintraegeLesenTests(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="suchlauf_")
        self.addCleanup(self._tmp.cleanup)
        self.wurzel = Path(self._tmp.name) / "sicherungen"
        self.wurzel.mkdir()
        self.gui = _gui_ohne_fenster(os.path.join(self._tmp.name, "bilder"))

    # --- Dump-Ordner ---------------------------------------------------------------------------------
    def test_die_reihenfolge_bleibt_trotz_nebenlaeufigkeit(self) -> None:
        for n in range(12):
            _dump(self.wurzel / ("Spiel %02d" % n), "PPSA%05d" % n)
        funde = self.gui._library_funde(str(self.wurzel))
        eintraege = self.gui._library_eintraege(funde)
        self.assertEqual([f["pfad"] for f in funde], [e["path"] for e in eintraege])
        self.assertEqual(["PPSA%05d" % n for n in range(12)], [e["meta"]["title_id"] for e in eintraege])

    def test_der_fortschritt_zaehlt_jeden_eintrag_genau_einmal(self) -> None:
        for n in range(9):
            _dump(self.wurzel / ("Spiel %02d" % n))
        meldungen: list[tuple[int, int, str]] = []
        sperre = threading.Lock()

        def _melden(getan: int, gesamt: int, name: str) -> None:
            with sperre:
                meldungen.append((getan, gesamt, name))

        self.gui._library_eintraege(self.gui._library_funde(str(self.wurzel)), fortschritt=_melden)
        self.assertEqual(list(range(1, 10)), sorted(m[0] for m in meldungen))
        self.assertEqual({9}, {m[1] for m in meldungen})
        self.assertEqual({"Spiel %02d" % n for n in range(9)}, {m[2] for m in meldungen})

    def test_die_ordner_werden_nebenlaeufig_gelesen(self) -> None:
        """Warten auf die Platte ueberlappt: vier Ordner zugleich statt einer nach dem anderen."""
        for n in range(8):
            _dump(self.wurzel / ("Spiel %02d" % n))
        gleichzeitig = {"jetzt": 0, "hoechstens": 0}
        sperre = threading.Lock()

        def _lesen(pfad, deep_scan=False):
            with sperre:
                gleichzeitig["jetzt"] += 1
                gleichzeitig["hoechstens"] = max(gleichzeitig["hoechstens"], gleichzeitig["jetzt"])
            time.sleep(0.05)
            with sperre:
                gleichzeitig["jetzt"] -= 1
            return {"title": os.path.basename(pfad)}

        self.gui._read_game_meta = _lesen
        eintraege = self.gui._library_eintraege(self.gui._library_funde(str(self.wurzel)))
        self.assertEqual(8, len(eintraege))
        self.assertGreater(gleichzeitig["hoechstens"], 1, "Die Ordner wurden nacheinander gelesen.")
        self.assertLessEqual(gleichzeitig["hoechstens"], self.gui._SCAN_FAEDEN)

    def test_der_abbruch_verhindert_das_einlesen(self) -> None:
        for n in range(6):
            _dump(self.wurzel / ("Spiel %02d" % n))
        gelesen: list[str] = []
        self.gui._read_game_meta = lambda pfad, deep_scan=False: gelesen.append(pfad) or {}
        funde = self.gui._library_funde(str(self.wurzel))
        self.assertEqual([], self.gui._library_eintraege(funde, abbruch=lambda: True))
        self.assertEqual([], gelesen)

    def test_ein_fehler_beim_einlesen_geht_nicht_verloren(self) -> None:
        for n in range(4):
            _dump(self.wurzel / ("Spiel %02d" % n))

        def _kaputt(pfad, deep_scan=False):
            raise RuntimeError("Platte weg")

        self.gui._read_game_meta = _kaputt
        with self.assertRaises(RuntimeError):
            self.gui._library_eintraege(self.gui._library_funde(str(self.wurzel)))

    def test_dump_ordner_werden_nie_im_bildspeicher_gemerkt(self) -> None:
        """Die Aenderungszeit eines Ordners sagt nichts ueber die param.json darin."""
        for n in range(3):
            _dump(self.wurzel / ("Spiel %02d" % n))
        self.gui._library_eintraege(self.gui._library_funde(str(self.wurzel)))
        index = self.gui._bibliothek_bilder
        for fund in self.gui._library_funde(str(self.wurzel)):
            self.assertIsNone(index.scan_lesen(fund["pfad"]))

    # --- Abbilder ------------------------------------------------------------------------------------
    def _abbild(self, name: str = "Spiel.ffpfsc") -> str:
        pfad = self.wurzel / name
        pfad.write_bytes(b"x" * 4096)
        return str(pfad)

    def test_ein_abbild_wird_nur_einmal_geoeffnet(self) -> None:
        pfad = self._abbild()
        aufrufe: list[str] = []
        png = _png_bytes()

        def _leser(p):
            aufrufe.append(p)
            return {"title": "Echter Titel", "title_id": "CUSA03877", "version": "01.00"}, png

        self.gui._bibliothek_abbild_angaben = _leser
        fund = [{"pfad": pfad, "art": "ffpfsc", "groesse": 4096, "name": "Spiel"}]
        erst = self.gui._library_eintraege(fund)
        zweit = self.gui._library_eintraege(fund)
        self.assertEqual(1, len(aufrufe), "Das Abbild wurde beim zweiten Lauf noch einmal geoeffnet.")
        self.assertEqual("Echter Titel", erst[0]["meta"]["title"])
        self.assertEqual("Echter Titel", zweit[0]["meta"]["title"])
        self.assertTrue(self.gui._bibliothek_bilder.lesen(pfad),
                        "Das Titelbild gehoert gleich mit in den Speicher - die Bildstufe soll nicht noch einmal oeffnen.")

    def test_ein_ersetztes_abbild_wird_neu_gelesen(self) -> None:
        pfad = self._abbild()
        aufrufe: list[str] = []
        self.gui._bibliothek_abbild_angaben = lambda p: (aufrufe.append(p) or {"title": "Titel"}, None)
        fund = [{"pfad": pfad, "art": "ffpfsc", "groesse": 4096, "name": "Spiel"}]
        self.gui._library_eintraege(fund)
        time.sleep(0.01)
        Path(pfad).write_bytes(b"y" * 8192)
        self.gui._library_eintraege(fund)
        self.assertEqual(2, len(aufrufe))

    def test_ein_fehlschlag_wird_nicht_gemerkt(self) -> None:
        """Platte im Schlaf, Datei gesperrt: Der naechste Lauf soll es wieder versuchen."""
        pfad = self._abbild()
        aufrufe: list[str] = []
        self.gui._bibliothek_abbild_angaben = lambda p: (aufrufe.append(p) or {}, None)
        fund = [{"pfad": pfad, "art": "ffpfsc", "groesse": 4096, "name": "Spiel"}]
        self.gui._library_eintraege(fund)
        self.gui._library_eintraege(fund)
        self.assertEqual(2, len(aufrufe))
        self.assertIsNone(self.gui._bibliothek_bilder.scan_lesen(pfad))

    def test_der_dateiname_ergaenzt_was_die_datei_nicht_sagt_und_wird_mit_gemerkt(self) -> None:
        pfad = self._abbild("PPSA19015 Arcade Game Zone (01.003.000).exfat")
        self.gui._bibliothek_abbild_angaben = lambda p: ({"title": "Arcade Game Zone"}, None)
        fund = [{"pfad": pfad, "art": "exfat", "groesse": 4096, "name": "x"}]
        meta = self.gui._library_eintraege(fund)[0]["meta"]
        self.assertEqual("Arcade Game Zone", meta["title"], "Was die Datei sagt, geht vor dem Namen.")
        self.assertEqual("PPSA19015", meta["title_id"])
        self.assertEqual("01.003.000", meta["version"])
        gemerkt = self.gui._bibliothek_bilder.scan_lesen(pfad)
        self.assertEqual("PPSA19015", gemerkt["title_id"])

    def test_ohne_titelbild_im_abbild_wird_keines_gemerkt(self) -> None:
        """Der allgemeine Leser der Bildstufe darf es noch versuchen - "kein Bild" ist hier keine Auskunft."""
        pfad = self._abbild()
        self.gui._bibliothek_abbild_angaben = lambda p: ({"title": "Titel"}, None)
        self.gui._library_eintraege([{"pfad": pfad, "art": "ffpfsc", "groesse": 4096, "name": "Spiel"}])
        self.assertFalse(self.gui._bibliothek_bilder.kennt_ohne_bild(pfad))
        self.assertEqual("", self.gui._bibliothek_bilder.lesen(pfad))

    def test_ohne_bildspeicher_wird_trotzdem_gelesen(self) -> None:
        pfad = self._abbild()
        self.gui._bibliothek_abbild_angaben = lambda p: ({"title": "Titel"}, None)
        with mock.patch.object(self.gui, "_bibliothek_bildspeicher", side_effect=OSError("kein Ordner")):
            eintraege = self.gui._library_eintraege(
                [{"pfad": pfad, "art": "ffpfsc", "groesse": 4096, "name": "Spiel"}])
        self.assertEqual("Titel", eintraege[0]["meta"]["title"])

    # --- Pakete --------------------------------------------------------------------------------------
    def test_ein_paket_bekommt_titel_kennung_fassung_firmware_und_bild(self) -> None:
        icon = _png_bytes()
        pfad = _paket(self.wurzel, "Tetris_CUSA00775.pkg",
                      {"TITLE": "Tetris Ultimate", "TITLE_ID": "CUSA00775", "APP_VER": "01.02",
                       "SYSTEM_VER": 0x05050000, "CATEGORY": "gd", "CONTENT_ID": "EP0001-CUSA00775_00-TETRISGAME000000"},
                      icon)
        eintraege = self.gui._library_scan_folder(str(self.wurzel))
        self.assertEqual(1, len(eintraege))
        eintrag = eintraege[0]
        self.assertEqual(("pkg", str(pfad)), (eintrag["kind"], eintrag["path"]))
        meta = eintrag["meta"]
        self.assertEqual("Tetris Ultimate", meta["title"])
        self.assertEqual("CUSA00775", meta["title_id"])
        self.assertEqual("01.02", meta["version"])
        self.assertEqual("EP0001-CUSA00775_00-TETRISGAME000000", meta["content_id"])
        self.assertIn("required_firmware", meta)
        self.assertTrue(eintrag["size"] > 0)
        stelle = self.gui._bibliothek_bilder.lesen(str(pfad))
        self.assertTrue(stelle and os.path.isfile(stelle), "Das Titelbild kam nicht in den Bildspeicher.")
        with open(stelle, "rb") as f:
            self.assertEqual(icon, f.read())

    def test_ein_fpkg_zaehlt_wie_ein_pkg(self) -> None:
        _paket(self.wurzel, "Spiel.fpkg", {"TITLE": "Fake Spiel", "TITLE_ID": "CUSA12345"}, None,
               content_id="EP9999-CUSA12345_00-FAKE")
        eintraege = self.gui._library_scan_folder(str(self.wurzel))
        self.assertEqual(["fpkg"], [e["kind"] for e in eintraege])
        self.assertEqual("Fake Spiel", eintraege[0]["meta"]["title"])

    def test_ein_paket_wird_nur_einmal_gelesen(self) -> None:
        _paket(self.wurzel, "Spiel.pkg", {"TITLE": "Titel", "TITLE_ID": "CUSA00001"}, _png_bytes())
        with mock.patch.object(paket, "paket_lesen", wraps=paket.paket_lesen) as leser:
            self.gui._library_scan_folder(str(self.wurzel))
            self.gui._library_scan_folder(str(self.wurzel))
        self.assertEqual(1, leser.call_count)

    def test_ein_kaputtes_paket_bleibt_in_der_liste_mit_dem_dateinamen(self) -> None:
        """Eine Bibliothek, die an einer Datei scheitert, zeigt gar nichts - hier bleibt der Name."""
        (self.wurzel / "CUSA00001 Kaputtes Spiel.pkg").write_bytes(b"kein paket" * 100)
        eintraege = self.gui._library_scan_folder(str(self.wurzel))
        self.assertEqual(1, len(eintraege))
        self.assertEqual("CUSA00001", eintraege[0]["meta"].get("title_id"))

    def test_das_titelbild_eines_pakets_kommt_ohne_neues_oeffnen(self) -> None:
        pfad = _paket(self.wurzel, "Spiel.pkg", {"TITLE": "Titel", "TITLE_ID": "CUSA00001"}, _png_bytes())
        self.gui._library_scan_folder(str(self.wurzel))
        with mock.patch.object(paket, "paket_lesen", side_effect=AssertionError("Paket noch einmal geoeffnet")) as leser:
            datei = self.gui._bibliothek_cover_datei(str(pfad))
        leser.assert_not_called()
        self.assertTrue(datei and os.path.isfile(datei))

    def test_ein_paket_ohne_bild_wird_als_bildlos_gemerkt(self) -> None:
        pfad = _paket(self.wurzel, "Spiel.pkg", {"TITLE": "Titel", "TITLE_ID": "CUSA00001"}, None)
        self.assertEqual("", self.gui._bibliothek_cover_datei(str(pfad)))
        self.assertTrue(self.gui._bibliothek_bilder.kennt_ohne_bild(str(pfad)))
        with mock.patch.object(paket, "paket_lesen", side_effect=AssertionError("noch einmal geoeffnet")) as leser:
            self.assertEqual("", self.gui._bibliothek_cover_datei(str(pfad)))
        leser.assert_not_called()

    def test_das_bild_eines_pakets_mit_lesefehler_wird_nicht_als_bildlos_gemerkt(self) -> None:
        pfad = _paket(self.wurzel, "Spiel.pkg", {"TITLE": "Titel"}, _png_bytes())
        with mock.patch.object(self.gui, "_bibliothek_paket_angaben", side_effect=OSError("Platte weg")):
            self.assertEqual("", self.gui._bibliothek_cover_datei(str(pfad)))
        self.assertFalse(self.gui._bibliothek_bilder.kennt_ohne_bild(str(pfad)))

    def test_gemischter_bestand_behaelt_die_reihenfolge_der_funde(self) -> None:
        _dump(self.wurzel / "A Dump")
        _paket(self.wurzel, "B Paket.pkg", {"TITLE": "B", "TITLE_ID": "CUSA00002"}, None)
        self._abbild("C Abbild.ffpfsc")
        self.gui._bibliothek_abbild_angaben = lambda p: ({"title": "C"}, None)
        funde = self.gui._library_funde(str(self.wurzel))
        eintraege = self.gui._library_eintraege(funde)
        self.assertEqual([f["pfad"] for f in funde], [e["path"] for e in eintraege])
        self.assertEqual({"folder", "pkg", "ffpfsc"}, {e["kind"] for e in eintraege})

    def test_ein_dump_ordner_als_scan_ordner_liefert_den_einen_titel(self) -> None:
        spiel = _dump(self.wurzel / "Dirt 5", "PPSA01234")
        eintraege = self.gui._library_scan_folder(str(spiel))
        self.assertEqual(1, len(eintraege))
        self.assertEqual(("folder", str(spiel)), (eintraege[0]["kind"], eintraege[0]["path"]))
        self.assertEqual("PPSA01234", eintraege[0]["meta"]["title_id"])


class _Attrappe:
    """Statt des Fortschrittsfensters: schreibt mit, was die Seite meldet."""

    alle: list["_Attrappe"] = []

    def __init__(self, seite, zeichner, phasen, **kw) -> None:
        self.seite, self.phasen, self.kw = seite, phasen, kw
        self.meldungen: list[tuple] = []
        self.beendet = False
        self.beenden_aufrufe = 0
        _Attrappe.alle.append(self)

    def melden(self, stufe, getan=None, gesamt=None, text="", letzte=False) -> None:
        self.meldungen.append((stufe, getan, gesamt, text))

    def beenden(self) -> None:
        self.beendet = True
        self.beenden_aufrufe += 1

    def schliessen(self) -> None:
        """Sofort zu - fuer die Seite, die zugeht oder neu beginnt."""
        self.beendet = True
        self.geschlossen = True

    geschlossen = False

    def abbrechen(self) -> None:
        """Was der Knopf tut: erst die Seite verstaendigen, dann zumachen."""
        self.kw["abbrechen"]()
        self.beenden()

    @property
    def stufen(self) -> list[str]:
        gesehen: list[str] = []
        for stufe, *_rest in self.meldungen:
            if not gesehen or gesehen[-1] != stufe:
                gesehen.append(stufe)
        return gesehen


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class SuchlaufSeiteTests(unittest.TestCase):
    """Die Seite verdrahtet ihren Suchlauf mit dem Fortschrittsfenster."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        cls._einstellungen: dict = {"library_scan_folders": [], "library_quelle": "pc",
                                    "library_ansicht": "kacheln"}
        cls._laden = mock.patch.object(
            cls.app, "_load_setting",
            side_effect=lambda k, v=None, _alt=cls.app._load_setting: cls._einstellungen.get(k, _alt(k, v)))
        cls._laden.start()
        cls._speichern = mock.patch.object(cls.app, "_save_setting",
                                           lambda k, v: cls._einstellungen.__setitem__(k, v))
        cls._speichern.start()
        cls._online = mock.patch.object(cls.app, "_metadaten_online_erlaubt", return_value=False)
        cls._online.start()
        cls._attrappe = mock.patch.object(raster, "SuchlaufAnzeige", _Attrappe)
        cls._attrappe.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._attrappe.stop()
        cls._online.stop()
        cls._speichern.stop()
        cls._laden.stop()
        cls.app._konsole_seite_setzen("uebersicht")
        cls.app._ansicht_setzen("umwandeln")
        _WURZEL.update()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="suchseite_")
        self.addCleanup(self._tmp.cleanup)
        self.wurzel = Path(self._tmp.name)
        for n in range(5):
            _dump(self.wurzel / ("Spiel %d" % n), "PPSA0000%d" % n)
        _Attrappe.alle.clear()
        self._einstellungen["library_scan_folders"] = [str(self.wurzel)]
        self._einstellungen["library_quelle"] = "pc"
        self.app._ansicht_setzen("konsole")
        # Die Seite neu bauen: Beim Bauen beginnt der erste Suchlauf von selbst.
        alt = getattr(self.app, "_bibliothek_seite", None)
        if alt is not None:
            alt.destroy()
            self.app._bibliothek_seite = None
        self.app._konsole_seite_setzen("bibliothek")
        self.zustand = self.app._bibliothek

    def tearDown(self) -> None:
        self.zustand["ansicht"]["suchlauf"] += 1            # laufende Faeden aufgeben lassen
        self._laufen()

    @staticmethod
    def _laufen(millisekunden: int = 30) -> None:
        """Eine echte Hauptschleife fuer einen Moment.

        ``update()`` genuegt nicht: Ein Arbeitsfaden, der ``after`` ruft, kommt nur dann durch, wenn der
        Hauptfaden in ``mainloop`` ist - sonst wirft Tk ``main thread is not in main loop``, und die Seite
        schluckt es (``_spaeter_im_fenster``). Das Ergebnis des Suchlaufs kaeme nie an.
        """
        _WURZEL.after(millisekunden, _WURZEL.quit)
        _WURZEL.mainloop()

    def _warten(self, bedingung, sekunden: float = 15.0) -> bool:
        ende = time.monotonic() + sekunden
        while time.monotonic() < ende:
            self._laufen()
            if bedingung():
                return True
        self._laufen()
        return bool(bedingung())

    def test_der_erste_suchlauf_legt_eine_anzeige_an_und_meldet_die_stufen_der_reihe_nach(self) -> None:
        self.assertEqual(1, len(_Attrappe.alle), "Beim Aufbau der Seite beginnt ein Suchlauf - mit einer Anzeige.")
        anzeige = _Attrappe.alle[0]
        self.assertTrue(self._warten(lambda: anzeige.beendet), "Die Anzeige wurde nie beendet.")
        self.assertEqual(["ordner", "angaben", "bilder", "einbauten"], anzeige.stufen)
        angaben = [m for m in anzeige.meldungen if m[0] == "angaben"]
        self.assertEqual((5, 5), (angaben[-1][1], angaben[-1][2]))
        bilder = [m for m in anzeige.meldungen if m[0] == "bilder"]
        self.assertEqual((5, 5), (bilder[-1][1], bilder[-1][2]))
        self.assertEqual(5, len(self.zustand["eintraege"]))

    def test_die_anzeige_traegt_die_stufen_des_rechners_und_den_hinweis(self) -> None:
        anzeige = _Attrappe.alle[0]
        self.assertEqual(("ordner", "angaben", "bilder", "einbauten"), anzeige.phasen.namen)
        self.assertEqual("library.scan_stufe_angaben", anzeige.kw["stufen"]["angaben"])
        self.assertEqual("library.scan_hinweis", anzeige.kw["hinweis"])
        self.assertTrue(callable(anzeige.kw["abbrechen"]))
        self._warten(lambda: anzeige.beendet)

    def test_der_lauf_zaehlt_die_funde_im_ordnertext(self) -> None:
        anzeige = _Attrappe.alle[0]
        self._warten(lambda: anzeige.beendet)
        texte = [m[3] for m in anzeige.meldungen if m[0] == "ordner"]
        self.assertTrue(texte)
        self.assertIn("5 gefunden", texte[-1])

    def test_ein_neuer_lauf_beendet_die_alte_anzeige(self) -> None:
        erste = _Attrappe.alle[0]
        self._warten(lambda: erste.beendet)
        with mock.patch.object(self.app, "_library_eintraege", side_effect=lambda *a, **k: time.sleep(0.5) or []):
            self.zustand["neu_suchen"]()
            zweite = _Attrappe.alle[-1]
            self.zustand["neu_suchen"]()
            dritte = _Attrappe.alle[-1]
            self.assertIsNot(zweite, dritte)
            self.assertTrue(zweite.beendet, "Ein neuer Lauf muss das Fenster des alten schliessen.")

    def test_ein_neuer_lauf_schliesst_die_alte_anzeige_sofort(self) -> None:
        """Nicht ueber after, sondern gleich: Sonst stuende das alte Fenster noch einen Augenblick neben dem neuen."""
        self._warten(lambda: _Attrappe.alle[0].beendet)
        with mock.patch.object(self.app, "_library_eintraege", side_effect=lambda *a, **k: time.sleep(0.3) or []):
            self.zustand["neu_suchen"]()
            zweite = _Attrappe.alle[-1]
            self.zustand["neu_suchen"]()
        self.assertTrue(zweite.geschlossen)

    def test_mit_der_seite_geht_auch_das_fortschrittsfenster_zu(self) -> None:
        """Das Fenster ist ein eigenes Toplevel: Beim Neuaufbau der Seite mitten im Suchlauf ginge es sonst nie zu."""
        self._warten(lambda: _Attrappe.alle[0].beendet)
        freigabe = threading.Event()
        with mock.patch.object(self.app, "_library_eintraege",
                               side_effect=lambda *a, **k: freigabe.wait(5) and [] or []):
            self.zustand["neu_suchen"]()
            anzeige = _Attrappe.alle[-1]
            self.assertFalse(anzeige.geschlossen)
            vorher = self.zustand["ansicht"]["suchlauf"]
            self.app._bibliothek_seite.destroy()
            self.assertTrue(anzeige.geschlossen, "Mit der Seite blieb das Fortschrittsfenster stehen.")
            self.assertGreater(self.zustand["ansicht"]["suchlauf"], vorher)
            freigabe.set()
        self.app._bibliothek_seite = None

    def test_ein_fehler_im_faden_beendet_die_anzeige(self) -> None:
        self._warten(lambda: _Attrappe.alle[0].beendet)
        with mock.patch.object(self.app, "_library_eintraege", side_effect=RuntimeError("Platte weg")), \
                mock.patch.object(threading, "excepthook", lambda *_a: None):
            self.zustand["neu_suchen"]()
            anzeige = _Attrappe.alle[-1]
            self.assertTrue(self._warten(lambda: anzeige.beendet),
                            "Nach einem Fehler im Faden blieb das Fenster stehen.")

    def test_ein_fehler_beim_zeigen_der_ergebnisse_schliesst_das_fenster(self) -> None:
        """Die Lader beenden die Anzeige - scheitert schon das Zeigen davor, tut es sonst niemand."""
        self._warten(lambda: _Attrappe.alle[0].beendet)
        gemeldet: list = []
        with mock.patch.object(self.app, "_bibliothek_bilder_nachladen",
                               side_effect=RuntimeError("Raster kaputt")), \
                mock.patch.object(_WURZEL, "report_callback_exception", lambda *a: gemeldet.append(a)):
            self.zustand["neu_suchen"]()
            anzeige = _Attrappe.alle[-1]
            self.assertTrue(self._warten(lambda: anzeige.geschlossen),
                            "Nach einem Fehler beim Zeigen blieb das Fortschrittsfenster stehen.")
        self.assertTrue(gemeldet, "Der Fehler selbst darf nicht verschluckt werden.")

    def test_ein_fehler_beim_zeigen_der_konsolenergebnisse_schliesst_das_fenster(self) -> None:
        gemeldet: list = []
        with mock.patch.object(self.app, "_bibliothek_ps5_scannen", lambda *a, **k: ([], "")), \
                mock.patch.object(self.app, "_bibliothek_ps5_bilder_nachladen",
                                  side_effect=RuntimeError("Raster kaputt")), \
                mock.patch.object(_WURZEL, "report_callback_exception", lambda *a: gemeldet.append(a)):
            self.zustand["quelle"].set("ps5")
            self.zustand["quelle_gewechselt"]()
            anzeige = _Attrappe.alle[-1]
            self.assertTrue(self._warten(lambda: anzeige.geschlossen),
                            "Nach einem Fehler beim Zeigen blieb das Fortschrittsfenster stehen.")
        self.assertTrue(gemeldet, "Der Fehler selbst darf nicht verschluckt werden.")

    def test_abbrechen_macht_die_faeden_veraltet_und_sagt_es_in_der_statuszeile(self) -> None:
        self._warten(lambda: _Attrappe.alle[0].beendet)
        freigabe = threading.Event()
        eingetreten = threading.Event()
        gesehen = {"abbruch": None}

        def _einlesen(funde, abbruch=None, fortschritt=None):
            eingetreten.set()
            freigabe.wait(10)
            gesehen["abbruch"] = abbruch() if abbruch else None
            return []

        with mock.patch.object(self.app, "_library_eintraege", _einlesen):
            vorher = self.zustand["ansicht"]["suchlauf"]
            self.zustand["eintraege"].clear()
            self.zustand["neu_suchen"]()
            anzeige = _Attrappe.alle[-1]
            self.assertEqual(vorher + 1, self.zustand["ansicht"]["suchlauf"])
            # Erst abbrechen, wenn der Faden mitten im Einlesen steckt - sonst gibt er schon vorher auf
            # und die Frage, ob er sich fuer veraltet haelt, wuerde nie gestellt.
            self.assertTrue(self._warten(eingetreten.is_set), "Der Faden kam nie zum Einlesen.")
            anzeige.abbrechen()
            self.assertEqual(vorher + 2, self.zustand["ansicht"]["suchlauf"], "Abbrechen zaehlt den Suchlauf weiter.")
            self.assertEqual("library.scan_abgebrochen", self.zustand["ansicht"]["status"][0])
            self.assertIsNone(self.zustand["ansicht"]["fortschritt"])
            freigabe.set()
            self.assertTrue(self._warten(lambda: gesehen["abbruch"] is not None))
            self.assertTrue(gesehen["abbruch"], "Der Faden haelt sich nicht fuer veraltet.")
            for _ in range(10):
                self._laufen()
        self.assertEqual([], self.zustand["eintraege"], "Das Ergebnis eines abgebrochenen Laufs darf nicht angezeigt werden.")
        self.assertEqual("library.scan_abgebrochen", self.zustand["ansicht"]["status"][0])

    def test_nur_ein_suchlauf_gibt_seine_anzeige_an_die_lader(self) -> None:
        """Filtern und Sortieren lassen kein Fenster aufgehen: Ihre Lader bekommen keine Anzeige."""
        aufrufe: list = []
        with mock.patch.object(self.app, "_bibliothek_bilder_nachladen",
                               side_effect=lambda *a, **k: aufrufe.append(k.get("fortschritt"))):
            self.zustand["neu_suchen"]()
            anzeige = _Attrappe.alle[-1]
            self.assertTrue(self._warten(lambda: len(aufrufe) >= 1))
            self.assertIs(anzeige, aufrufe[0])
            self.zustand["filtern"]()
            self.assertIsNone(aufrufe[-1], "Ein blosses Filtern gab dem Lader eine Anzeige.")

    # --- Pakete: Karte, Knoepfe, Umwandlung -------------------------------------------------------------
    @staticmethod
    def _paket_eintrag(art: str = "pkg", kennung: str = "CUSA00775") -> dict:
        name = "Tetris." + art
        return {"path": "E:\\Pakete\\" + name, "kind": art, "name": name, "size": 130 * 2 ** 20,
                "meta": {"title": "Tetris Ultimate", "title_id": kennung, "version": "01.00",
                         "required_firmware": "05.05.00.00", "content_id": "EP0001-%s_00-X" % kennung}}

    def _knoepfe(self, eintrag: dict) -> dict[str, bool]:
        return {spec.name: spec.aktiv for spec in self.zustand["inhalt"](eintrag)["knoepfe"]}

    def test_ein_paket_traegt_format_chip_und_plakette_aber_keine_einbau_chips(self) -> None:
        for art, chip in (("pkg", "PKG"), ("fpkg", "FPKG")):
            with self.subTest(art=art):
                eintrag = self._paket_eintrag(art)
                inhalt = self.zustand["inhalt"](eintrag)
                self.assertEqual((chip, "neutral"), inhalt["chips"][0])
                self.assertEqual("PS4", inhalt["plattform"])
                # Der Einbau-Durchgang meldet "unbekannt/format" - bei einem Paket soll das nicht auf der Karte stehen.
                self.zustand["ansicht"]["einbauten"][eintrag["path"]] = {"zustand": "unbekannt", "grund": "format"}
                self.assertEqual([(chip, "neutral")], self.zustand["inhalt"](eintrag)["chips"])
                self.zustand["ansicht"]["einbauten"].pop(eintrag["path"], None)

    def test_ein_ps5_paket_zeigt_die_plakette_ps5(self) -> None:
        self.assertEqual("PS5", self.zustand["inhalt"](self._paket_eintrag("pkg", "PPSA01234"))["plattform"])

    def test_die_knoepfe_eines_pakets(self) -> None:
        """Starten wie bei jedem Titel mit gueltiger Kennung; Kopieren nie; Konvertieren nur fuer ein PS4-.pkg."""
        self.assertEqual({"info": True, "start": True, "kopieren": False, "konvertieren": True},
                         self._knoepfe(self._paket_eintrag("pkg", "CUSA00775")))
        self.assertEqual({"info": True, "start": True, "kopieren": False, "konvertieren": False},
                         self._knoepfe(self._paket_eintrag("fpkg", "CUSA00775")))
        self.assertEqual({"info": True, "start": True, "kopieren": False, "konvertieren": False},
                         self._knoepfe(self._paket_eintrag("pkg", "PPSA01234")))

    def test_ein_gesperrter_paketknopf_sagt_warum(self) -> None:
        eintrag = self._paket_eintrag("fpkg")
        for name in ("kopieren", "konvertieren"):
            with self.subTest(knopf=name):
                self.zustand["gesperrt"](name, eintrag)
                erwartet = self.app._t("library.gesperrt_%s_paket" % name)
                self.assertFalse(erwartet.startswith("library."), "Fuer den Hinweis fehlt die Uebersetzung.")
                self.assertEqual(erwartet, self.zustand["ansicht"]["status"][1]["text"])

    def test_konvertieren_eines_ps4_pakets_oeffnet_das_umwandlungsfenster_mit_der_datei(self) -> None:
        eintrag = self._paket_eintrag("pkg")
        with mock.patch.object(self.app, "_show_ps4_pkg_converter") as fenster:
            self.zustand["aktion"]("konvertieren", eintrag)
        fenster.assert_called_once_with()
        self.assertEqual(eintrag["path"], self.app._ps4pkg_vorgabe)
        self.app._ps4pkg_vorgabe = ""

    def test_konvertieren_eines_fpkg_oeffnet_nichts_und_setzt_keine_quelle(self) -> None:
        eintrag = self._paket_eintrag("fpkg")
        quelle_vorher = self.app.source_path.get()
        with mock.patch.object(self.app, "_show_ps4_pkg_converter") as fenster:
            self.zustand["aktion"]("konvertieren", eintrag)
        fenster.assert_not_called()
        self.assertEqual(quelle_vorher, self.app.source_path.get())

    def test_das_umwandlungsfenster_uebernimmt_die_vorgabe_einmalig(self) -> None:
        if not APP._ps4ffpsc_wurzel() or not APP._ps4ffpsc_entpacker():
            self.skipTest("Das PS4-Werkzeug ist in dieser Umgebung nicht eingerichtet.")
        pfad = "E:\\Pakete\\Tetris.pkg"
        vorher = set(self.app.root.winfo_children())

        def _eintraege() -> list:
            neu = [w for w in self.app.root.winfo_children() if w not in vorher and isinstance(w, tk.Toplevel)]
            gefunden: list = []

            def _suche(widget) -> None:
                for kind in widget.winfo_children():
                    if isinstance(kind, tk.Entry):
                        name = str(kind.cget("textvariable"))
                        if name:
                            gefunden.append(self.app.root.globalgetvar(name))
                    _suche(kind)

            for fenster in neu:
                _suche(fenster)
            return gefunden

        self.app._ps4pkg_vorgabe = pfad
        self.app._show_ps4_pkg_converter()
        try:
            self.assertIn(os.path.normpath(pfad), _eintraege(), "Die Datei steht nicht im Quellfeld.")
            self.assertEqual("", self.app._ps4pkg_vorgabe, "Die Vorgabe gilt nur fuer ein Oeffnen.")
        finally:
            for w in list(self.app.root.winfo_children()):
                if w not in vorher and isinstance(w, tk.Toplevel):
                    w.destroy()

    def test_die_ps5_suche_bekommt_fortschritt_und_abbruch_und_ihre_lader_die_anzeige(self) -> None:
        empfangen: dict = {}
        lader: list = []

        def _scannen(*a, **k):
            empfangen.update(k)
            return [], ""

        with mock.patch.object(self.app, "_bibliothek_ps5_scannen", _scannen), \
                mock.patch.object(self.app, "_bibliothek_ps5_bilder_nachladen",
                                  side_effect=lambda *a, **k: lader.append(k.get("fortschritt"))):
            self.zustand["quelle"].set("ps5")
            self.zustand["quelle_gewechselt"]()
            anzeige = _Attrappe.alle[-1]
            self.assertTrue(self._warten(lambda: bool(lader)))
        self.assertEqual(("konsole", "ablagen", "angaben", "kennungen", "installiert", "bilder", "einbauten"),
                         anzeige.phasen.namen)
        self.assertEqual("library.scan_hinweis_ps5", anzeige.kw["hinweis"])
        self.assertEqual(anzeige.melden, empfangen["fortschritt"])
        self.assertTrue(callable(empfangen["abbruch"]))
        self.assertIs(anzeige, lader[0])
        self.zustand["quelle"].set("pc")
        self.zustand["quelle_gewechselt"]()


class BeendenTests(unittest.TestCase):
    """Liegengebliebene Lader duerfen das Ende des Programms nicht aufhalten (04.10.2026).

    Die Ordner liefen zuerst ueber ``concurrent.futures.ThreadPoolExecutor``. Auf dessen Faeden wartet Python beim
    Beenden - auch auf Daemon-Faeden -, und jeder Auftrag, der dann noch Tk aus dem Faden rief, wartete rund 1 s.
    Gemessen: Prozessende 6,4 s nach dem Skriptende bei 24 Dump-Ordnern, mit eigenen Daemon-Faeden 0,0 s.
    """

    SKRIPT = "\n".join((
        "import sys, threading, time",
        "sys.path.insert(0, sys.argv[1])",
        "import PS5ImageConverter_Pro_FINAL_revised as APP",
        "auftraege = [lambda: time.sleep(30) for _ in range(4)]",
        "threading.Thread(target=APP.PS5ConverterGUI._nebenlaeufig, args=(auftraege, 4, 'probe'),",
        "                 daemon=True).start()",
        "time.sleep(0.5)",
        "print('LAEUFT', sorted(t.name for t in threading.enumerate() if t.name.startswith('probe')), flush=True)",
    ))

    def test_offene_auftraege_halten_das_beenden_nicht_auf(self) -> None:
        beginn = time.monotonic()
        lauf = subprocess.run([sys.executable, "-c", self.SKRIPT, str(PROJEKT)], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=120)
        dauer = time.monotonic() - beginn
        self.assertEqual(0, lauf.returncode, lauf.stderr[-600:])
        self.assertIn("LAEUFT ['probe-1', 'probe-2', 'probe-3', 'probe-4']", lauf.stdout,
                      "Die vier Faeden liefen gar nicht - dann misst der Test nichts.")
        self.assertLess(dauer, 25.0, "Das Programm wartete beim Beenden auf liegengebliebene Auftraege "
                                     "(%.1f s; die Auftraege schlafen 30 s)." % dauer)

    def test_ein_fehler_kommt_nach_dem_warten_heraus(self) -> None:
        erledigt: list[int] = []

        def _gut(n: int) -> None:
            time.sleep(0.05)
            erledigt.append(n)

        def _kaputt() -> None:
            raise ValueError("Platte weg")

        with self.assertRaises(ValueError):
            APP.PS5ConverterGUI._nebenlaeufig([lambda: _gut(1), _kaputt, lambda: _gut(2), lambda: _gut(3)], 2,
                                              "probe", nebenher=lambda: _gut(0))
        self.assertEqual([0, 1, 2, 3], sorted(erledigt), "Die uebrigen Auftraege liefen nicht zu Ende.")


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class OhneHauptschleifeTests(unittest.TestCase):
    """Die echte Seite und das echte Fortschrittsfenster - ohne Hauptschleife, wie in fast allen Tests.

    Im ersten Volllauf nach dem Einbau (03.10.2026) konnte der Arbeitsfaden sein Ergebnis nicht in die Seite reichen
    (``main thread is not in main loop``), niemand beendete die Anzeige, und nach 0,4 s stand ein **sichtbares** Fenster
    "Spiele auf dem Rechner suchen" - fuer den Rest des Laufs. Daneben ging eine Rueckfrage in ``test_ordner_einbau``
    von selbst zu, bevor der Test sie bedienen konnte (sichtbare Fenster sind dort als Ausloeser bekannt).
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory(prefix="suchlauf_ohne_schleife_")
        cls.wurzel = Path(cls._tmp.name)
        for n in range(3):
            _dump(cls.wurzel / ("Spiel %d" % n), "PPSA0001%d" % n)
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        einstellungen = {"library_scan_folders": [str(cls.wurzel)], "library_quelle": "pc",
                         "library_ansicht": "kacheln"}
        cls._laden = mock.patch.object(
            cls.app, "_load_setting",
            side_effect=lambda k, v=None, _alt=cls.app._load_setting: einstellungen.get(k, _alt(k, v)))
        cls._laden.start()
        cls._speichern = mock.patch.object(cls.app, "_save_setting", lambda k, v: einstellungen.__setitem__(k, v))
        cls._speichern.start()
        cls._online = mock.patch.object(cls.app, "_metadaten_online_erlaubt", return_value=False)
        cls._online.start()
        _WURZEL.withdraw()

    @classmethod
    def tearDownClass(cls) -> None:
        seite = getattr(cls.app, "_bibliothek_seite", None)
        if seite is not None and seite.winfo_exists():
            seite.destroy()
        cls._online.stop()
        cls._speichern.stop()
        cls._laden.stop()
        _WURZEL.update()
        cls._tmp.cleanup()

    def _offene_fortschrittsfenster(self) -> list:
        titel = {self.app._t("library.scan_titel_pc"), self.app._t("library.scan_titel_ps5")}
        return [w for w in _WURZEL.winfo_children()
                if isinstance(w, tk.Toplevel) and w.winfo_exists() and w.title() in titel]

    def test_ohne_hauptschleife_bleibt_kein_fortschrittsfenster_stehen(self) -> None:
        self.assertEqual([], self._offene_fortschrittsfenster(), "Ein anderer Test liess eines stehen.")
        self.app._ansicht_setzen("konsole")
        alt = getattr(self.app, "_bibliothek_seite", None)
        if alt is not None:
            alt.destroy()
            self.app._bibliothek_seite = None
        self.app._konsole_seite_setzen("bibliothek")
        anzeige = self.app._bibliothek["ansicht"]["fortschritt"]
        self.assertIsInstance(anzeige, raster.SuchlaufAnzeige, "Hier soll das echte Fenster laufen, keine Attrappe.")
        ende = time.monotonic() + 2.0          # deutlich ueber der Verzoegerung von 0,4 s und der Wache von 0,25 s
        while time.monotonic() < ende:
            _WURZEL.update()
            time.sleep(0.02)
        self.assertTrue(anzeige.beendet, "Niemand hat die Anzeige beendet.")
        self.assertEqual([], [w.title() for w in self._offene_fortschrittsfenster()],
                         "Ohne Hauptschleife blieb ein Fortschrittsfenster stehen.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
