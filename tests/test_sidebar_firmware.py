# -*- coding: utf-8 -*-
"""Firmware-Zeilen ueber dem Cover der Seitenleiste (Nutzerwunsch 11.11.2026).

Gleich oberhalb des Spielcovers steht die Firmware, die das Spiel braucht ("Benoetigte Firmware: 4.51"); ist ein
Backport eingebaut, darunter dessen Firmware ("Backport: Firmware 7"). Der Backport zeigt sich an den Bibliotheken
(``fakelib/FW<n>`` oder ``fakelib/fw<nn>``), nicht an einer param.json - ein Dump ohne Marke gilt als nicht
zurueckportiert. Die beiden Zeilen sind immer zwei Zeilen hoch, damit das Cover nicht springt, wenn der
Backport-Befund aus dem Faden nachtraeglich eintrifft.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("sidebar_firmware")

from ps5_validator.utils.i18n import STRINGS                # noqa: E402

HAUPT = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"

try:
    import tkinter as tk
    from PIL import Image
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                            # pragma: no cover
    TK_DA = False


def _lade():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPT)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


class _SofortThread:
    """Ersatz fuer ``threading.Thread``: laeuft gleich im Aufrufer (der Test hat keine Hauptschleife)."""

    def __init__(self, target=None, **_kw) -> None:
        self._ziel = target

    def start(self) -> None:
        self._ziel()


class FirmwareKurzTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.klasse = _lade().PS5ConverterGUI

    def test_formen(self):
        f = self.klasse._firmware_kurz
        self.assertEqual("4.51", f("04.51.00.00"))
        self.assertEqual("10.00", f("10.00.00.00"))
        self.assertEqual("7.00", f("7.00"))
        self.assertEqual("", f("–"))
        self.assertEqual("", f(""))
        self.assertEqual("", f(None))
        self.assertEqual("", f("Unbekannt"))

    def test_texte_in_allen_sprachen(self):
        for schluessel in ("sidebar.fw_required", "sidebar.fw_backport"):
            for sprache in ("de", "en", "es", "it", "fr"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    self.assertIn("{fw}", STRINGS[schluessel][sprache])
        for schluessel in ("sidebar.fw_pack", "sidebar.fw_pack_kurz"):
            for sprache in ("de", "en", "es", "it", "fr"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    self.assertIn("{verfahren}", STRINGS[schluessel][sprache])

    def test_das_verfahren_der_packs_wird_aus_den_dateinamen_bestimmt(self):
        """``einbauten_bewerten``: zstd-Dateien beginnen mit ``ampr_zstd``, alles andere der Asset-Schicht ist LZ4."""
        from ps5_validator.utils import ampr_zstdpack as zp
        from ps5_validator.utils import bibliothek as bib
        ist_pack = self.klasse._ist_ampr_asset_datei
        self.assertTrue(zp.INDEX_NAME.startswith(bib.ZSTD_PACK_PRAEFIX))
        self.assertTrue(zp.bandname(0).startswith(bib.ZSTD_PACK_PRAEFIX))
        for dateien, assetpack, verfahren in (
                (["ampr_assets.index", "ampr_assets-000.pak"], True, "lz4"),
                ([zp.bandname(0), zp.bandname(1)], True, "zstd"),
                (["ampr_assets-000.pak", zp.bandname(0)], True, "zstd"),
                (["eboot.bin", "data/ampr_zstd-000.pak"], False, ""),            # nur an der Wurzel
                (["eboot.bin", "sce_sys/param.json"], False, ""),
                # Eine fremde .pak in der Wurzel (eigene Spieldaten) zaehlt wie bisher als Asset-Schicht, ist aber nicht "LZ4" (18.11.2026).
                (["data.pak"], True, ""),
                (["data.pak", "ampr_assets-000.pak"], True, "lz4"),
                (["data.pak", zp.bandname(0)], True, "zstd"),
                (["ampr_assets.index.runtime"], True, "lz4")):
            with self.subTest(dateien=dateien):
                ergebnis = bib.einbauten_bewerten(dateien, assetpack_datei=ist_pack)
                self.assertEqual((assetpack, verfahren), (ergebnis["assetpack"], ergebnis["packverfahren"]))


class WaechterTests(unittest.TestCase):
    """Die Hoehe der Zeilen geht in jede Rechnung des Cover-Platzes ein - sonst ueberlappen sie sich bei niedrigem Fenster."""

    @classmethod
    def setUpClass(cls) -> None:
        import ast
        text = HAUPT.read_text(encoding="utf-8")
        zeilen = text.splitlines()
        cls.funktionen = {}
        for k in ast.walk(ast.parse(text)):
            if isinstance(k, ast.FunctionDef):
                cls.funktionen[k.name] = "\n".join(zeilen[k.lineno - 1:k.end_lineno])

    def test_die_hoehe_geht_in_breite_zentrierung_und_vorschau_ein(self):
        for name in ("_sidebar_cover_width", "_center_sidebar_cover", "_update_sidebar_preview"):
            with self.subTest(name):
                self.assertIn("_sidebar_fw_hoehe", self.funktionen[name])

    def test_die_zeilen_verschwinden_mit_dem_cover(self):
        quelle = self.funktionen["_update_sidebar_preview"]
        self.assertGreaterEqual(quelle.count("_sidebar_fw_label.pack_forget()"), 2)     # kein Cover / Fehlerzweig

    def test_die_ansichten_nehmen_sie_mit(self):
        self.assertIn('"_sidebar_fw_label"', self.funktionen["_ansicht_erste_widgets"])

    def test_die_infobox_fuettert_sie(self):
        self.assertIn("_sidebar_firmware_aktualisieren(", self.funktionen["_update_info_box"])


@unittest.skipUnless(TK_DA, "keine Anzeige")
class FensterTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade()
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="ps5conv_fw_")
        self.addCleanup(tmp.cleanup)
        self.ohne = os.path.join(tmp.name, "ohne")
        self.mit = os.path.join(tmp.name, "mit")
        os.makedirs(self.ohne)
        os.makedirs(os.path.join(self.mit, "fakelib"))
        Path(self.mit, "fakelib", "FW7").touch()
        Path(self.mit, "fakelib", "libc.prx").write_bytes(b"x")
        self.app._sidebar_fw_merker = {}
        self.app._sidebar_fw_quelle = None
        self.app._sidebar_fw_backport = ""
        self.app._sidebar_fw_zusatz = ()
        self.app._sidebar_fw_sdk = ""
        self.app._sidebar_fw_chips_setzen([])
        self.addCleanup(self.app._sidebar_fw_chips_setzen, [])
        for muster in (mock.patch.object(self.haupt.threading, "Thread", _SofortThread),
                       mock.patch.object(self.app, "_spaeter_im_fenster",
                                         side_effect=lambda _f, cb, *a: (cb(*a), True)[1])):
            muster.start()
            self.addCleanup(muster.stop)

    def _text(self) -> str:
        return str(self.app._sidebar_fw_label.cget("text"))

    def test_benoetigte_firmware_ohne_backport(self):
        self.app._sidebar_firmware_aktualisieren({"required_firmware": "04.51.00.00"}, self.ohne)
        zeilen = self._text().split("\n")
        self.assertEqual(2, len(zeilen), "immer zwei Zeilen - das Cover darf nicht springen")
        self.assertEqual(self.app._t("sidebar.fw_required", fw="4.51"), zeilen[0])
        self.assertEqual("", zeilen[1].strip())

    def test_backport_zeile_bei_marke_in_fakelib(self):
        self.app._sidebar_firmware_aktualisieren({"required_firmware": "10.00.00.00"}, self.mit)
        zeilen = self._text().split("\n")
        self.assertEqual(self.app._t("sidebar.fw_required", fw="10.00"), zeilen[0])
        self.assertEqual(self.app._t("sidebar.fw_backport", fw="7"), zeilen[1])

    # ---------------- SDK-Stand als Rueckfall (Nutzerwunsch 18.11.2026) ----------------
    # Anlass: "Arkanoid - Eternal Battle" - die param.json nennt weder requiredSystemSoftwareVersion noch sdkVersion, die
    # eboot.bin traegt SDK 4.00 (gemessen). Die Seitenleiste zeigte nichts; jetzt den SDK-Stand, als "SDK" beschriftet.
    def _sdk(self, wert=("4.00", "")):
        return mock.patch.object(self.app, "_sdk_stand_lesen", return_value=wert)

    def test_ohne_firmware_in_den_metadaten_zeigt_die_zeile_den_sdk_stand_der_eboot(self):
        with self._sdk() as lesen:
            self.app._sidebar_firmware_aktualisieren({}, self.ohne)
        zeilen = self._text().split("\n")
        self.assertEqual(2, len(zeilen), "immer zwei Zeilen - das Cover darf nicht springen")
        self.assertEqual(self.app._t("sidebar.fw_sdk", fw="4.00"), zeilen[0])
        self.assertEqual("", zeilen[1].strip())
        self.assertEqual([(self.app._t("sidebar.fw_chip_sdk", fw="4.00"), "neutral")], self._kacheln())
        lesen.assert_called_once_with(self.ohne)

    def test_der_sdk_stand_heisst_sdk_und_nicht_benoetigte_firmware(self):
        """Er sagt, womit das Spiel gebaut ist - nicht, was die Konsole mindestens braucht."""
        with self._sdk():
            self.app._sidebar_firmware_aktualisieren({}, self.ohne)
        self.assertNotIn(self.app._t("sidebar.fw_required", fw="4.00"), self._text())
        self.assertIn("SDK", self._text())

    def test_eine_firmware_aus_den_metadaten_geht_vor_und_die_eboot_wird_nicht_gelesen(self):
        with self._sdk() as lesen:
            self.app._sidebar_firmware_aktualisieren({"required_firmware": "10.00.00.00"}, self.ohne)
        self.assertEqual(self.app._t("sidebar.fw_required", fw="10.00"), self._text().split("\n")[0])
        self.assertEqual([(self.app._t("sidebar.fw_chip", fw="10.00"), "neutral")], self._kacheln())
        lesen.assert_not_called()

    def test_kommt_beides_zusammen_an_gewinnt_die_firmware(self):
        """Der Faden meldet den SDK-Stand womoeglich erst, nachdem die Metadaten die Firmware nachgeliefert haben."""
        self.app._sidebar_fw_text_setzen("9.00", "", (), "4.00")
        self.assertEqual(self.app._t("sidebar.fw_required", fw="9.00"), self._text().split("\n")[0])
        self.assertEqual([(self.app._t("sidebar.fw_chip", fw="9.00"), "neutral")], self._kacheln())

    def test_ohne_firmware_und_ohne_lesbaren_sdk_stand_bleibt_die_zeile_leer(self):
        with self._sdk(("", "")):
            self.app._sidebar_firmware_aktualisieren({}, self.ohne)
        self.assertEqual("", self._text().split("\n")[0].strip())
        self.assertEqual([], self._kacheln())

    def test_bei_einem_backport_steht_der_sdk_stand_nur_in_der_zweiten_zeile(self):
        with self._sdk(("7.00", "")) as lesen:
            self.app._sidebar_firmware_aktualisieren({}, self.mit)
        zeilen = self._text().split("\n")
        self.assertEqual("", zeilen[0].strip(), "nicht doppelt: dort ist es die Firmware des Backports, nicht des Spiels")
        self.assertEqual(self.app._t("sidebar.fw_backport", fw="7.00"), zeilen[1])
        lesen.assert_called_once()

    def test_ein_abbild_wird_nicht_auf_gut_glueck_gelesen(self):
        abbild = os.path.join(os.path.dirname(self.ohne), "spiel.exfat")
        Path(abbild).write_bytes(b"x" * 64)
        with self._sdk() as lesen:
            self.app._sidebar_firmware_aktualisieren({}, abbild)
        self.assertEqual("", self._text().split("\n")[0].strip())
        lesen.assert_not_called()

    def test_der_sdk_stand_wird_je_ordner_nur_einmal_gelesen(self):
        with self._sdk() as lesen:
            self.app._sidebar_firmware_aktualisieren({}, self.ohne)
            self.app._sidebar_fw_quelle = None                     # dieselbe Wahl noch einmal (etwa ein Sprachwechsel zurueck)
            self.app._sidebar_firmware_aktualisieren({}, self.ohne)
        lesen.assert_called_once()
        self.assertEqual(self.app._t("sidebar.fw_sdk", fw="4.00"), self._text().split("\n")[0])

    def test_der_zwischenspeicher_unterscheidet_mit_und_ohne_firmware(self):
        """Erst mit Firmware (kein SDK gelesen), dann derselbe Ordner ohne: Der leere Eintrag darf nicht gelten."""
        with self._sdk() as lesen:
            self.app._sidebar_firmware_aktualisieren({"required_firmware": "10.00.00.00"}, self.ohne)
            self.app._sidebar_firmware_aktualisieren({"required_firmware": "10.00.00.00"}, self.mit)   # andere Quelle dazwischen
            self.app._sidebar_firmware_aktualisieren({}, self.ohne)
        self.assertEqual(self.app._t("sidebar.fw_sdk", fw="4.00"), self._text().split("\n")[0])
        self.assertGreaterEqual(lesen.call_count, 1)

    def test_die_neuen_texte_gibt_es_in_allen_sprachen(self):
        for schluessel in ("sidebar.fw_sdk", "sidebar.fw_chip_sdk"):
            for sprache in ("de", "en", "es", "it", "fr"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    text = STRINGS[schluessel][sprache]
                    self.assertIn("{fw}", text)
                    self.assertIn("SDK", text)

    # ---------------- gepackte Spiele (LZ4, zstd) - Nutzerwunsch 17.11.2026 ----------------
    def _packordner(self, name: str, dateien, backport: bool = False) -> str:
        """Ein Spielordner mit Dateien an der Wurzel (und auf Wunsch der FW7-Marke eines Backports)."""
        ordner = os.path.join(os.path.dirname(self.ohne), name)
        os.makedirs(os.path.join(ordner, "fakelib"))
        Path(ordner, "fakelib", "libc.prx").write_bytes(b"x")
        if backport:
            Path(ordner, "fakelib", "FW7").touch()
        for datei in dateien:
            Path(ordner, datei).write_bytes(b"x")
        return ordner

    _LZ4 = ("ampr_assets.index", "ampr_assets.index.runtime", "ampr_assets-000.pak")
    _ZSTD = ("ampr_zstd.index", "ampr_zstd-000.pak")

    def test_ein_lz4_pack_steht_allein_ausgeschrieben_in_der_zweiten_zeile(self):
        self.app._sidebar_firmware_aktualisieren({"required_firmware": "10.00.00.00"}, self._packordner("lz4", self._LZ4))
        zeilen = self._text().split("\n")
        self.assertEqual(2, len(zeilen), "weiter zwei Zeilen - das Cover darf nicht springen")
        self.assertEqual(self.app._t("sidebar.fw_required", fw="10.00"), zeilen[0])
        self.assertEqual(self.app._t("sidebar.fw_pack", verfahren="LZ4"), zeilen[1])

    def test_ein_zstd_pack_steht_ebenso_dort(self):
        self.app._sidebar_firmware_aktualisieren({"required_firmware": "10.00.00.00"}, self._packordner("zstd", self._ZSTD))
        self.assertEqual(self.app._t("sidebar.fw_pack", verfahren="zstd"), self._text().split("\n")[1])

    def test_mit_backport_und_pack_teilen_sie_sich_die_zweite_zeile(self):
        self.app._sidebar_firmware_aktualisieren({"required_firmware": "10.00.00.00"},
                                                 self._packordner("beides", self._LZ4, backport=True))
        zeilen = self._text().split("\n")
        self.assertEqual(2, len(zeilen))
        self.assertEqual("%s · %s" % (self.app._t("sidebar.fw_backport", fw="7"),
                                           self.app._t("sidebar.fw_pack_kurz", verfahren="LZ4")), zeilen[1])

    def test_ohne_pack_bleibt_die_zweite_zeile_wie_sie_war(self):
        self.app._sidebar_firmware_aktualisieren({"required_firmware": "10.00.00.00"}, self._packordner("keins", ()))
        self.assertEqual("", self._text().split("\n")[1].strip())

    def test_ein_spiel_mit_beiden_verfahren_gilt_als_zstd(self):
        self.app._sidebar_firmware_aktualisieren({"required_firmware": "10.00.00.00"},
                                                 self._packordner("beide", self._LZ4 + self._ZSTD))
        self.assertEqual(self.app._t("sidebar.fw_pack", verfahren="zstd"), self._text().split("\n")[1])

    def test_das_protokoll_nennt_das_verfahren_des_packs(self):
        """``[Pruefung] ... bereits eingebaut - Asset-Pack (LZ4)``: vorher stand dort nur "Asset-Pack"."""
        for ordner, name in ((self._packordner("p_lz4", self._LZ4), "Asset-Pack (LZ4)"),
                             (self._packordner("p_zstd", self._ZSTD), "Asset-Pack (zstd)")):
            with self.subTest(erwartet=name):
                zeilen = "".join(self.app._quelle_einbauten_zeilen(ordner))
                self.assertIn(name, zeilen)

    def test_ein_paket_wird_ueber_dump_forge_gelesen(self):
        """Ein ``.pkg`` liest die eigene Sicht nicht: Forges Befund bestimmt auch das Verfahren."""
        from ps5_validator.utils import forge_cli as fc
        pkg = os.path.join(os.path.dirname(self.ohne), "Spiel.pkg")
        Path(pkg).write_bytes(b"pkg")
        for gepackt, erwartet in (("lz4", "lz4"), ("zstd", "zstd"), ("", "")):
            with self.subTest(gepackt=gepackt), \
                    mock.patch.object(self.haupt.PS5ConverterGUI, "_quellfakten_der_quelle", return_value=fc.QuellFakten(gepackt=gepackt)):
                ergebnis = self.app._einbauten_der_quelle(pkg)
                self.assertEqual(erwartet, ergebnis["packverfahren"])
                self.assertEqual(bool(erwartet), ergebnis["assetpack"])

    # ---------------- kleine Kacheln je Rolle (Nutzerwahl 17.11.2026) ----------------
    def _kacheln(self) -> "list[tuple[str, str]]":
        """(Text, Art) der Kacheln ueber dem Cover, in der Reihenfolge, in der sie stehen."""
        label = self.app._sidebar_fw_label
        return [(str(k._text), art) for k, (_t, art) in zip(label._chip_widgets, label._chips)]

    def test_die_firmware_steht_als_graue_kachel_da(self):
        self.app._sidebar_firmware_aktualisieren({"required_firmware": "10.00.00.00"}, self.ohne)
        self.assertEqual([(self.app._t("sidebar.fw_chip", fw="10.00"), "neutral")], self._kacheln())

    def test_backport_und_pack_sind_je_eine_kachel_in_der_farbe_ihrer_rolle(self):
        self.app._sidebar_firmware_aktualisieren({"required_firmware": "10.00.00.00"},
                                                 self._packordner("rollen", self._LZ4, backport=True))
        self.assertEqual([(self.app._t("sidebar.fw_chip", fw="10.00"), "neutral"),
                          (self.app._t("sidebar.fw_chip_backport", fw="7"), "backport"),
                          ("LZ4", "assetpack")], self._kacheln())

    def test_ein_zstd_pack_ist_eine_kachel_zstd(self):
        self.app._sidebar_firmware_aktualisieren({"required_firmware": "10.00.00.00"}, self._packordner("kz", self._ZSTD))
        self.assertEqual(["zstd"], [t for t, a in self._kacheln() if a == "assetpack"])

    def test_die_kacheln_sind_pillen_im_label_und_ohne_hand_als_zeiger(self):
        self.app._sidebar_firmware_aktualisieren({"required_firmware": "10.00.00.00"},
                                                 self._packordner("pillen", self._LZ4, backport=True))
        label = self.app._sidebar_fw_label
        self.assertTrue(label._chips_aktiv)
        self.assertEqual(3, len(label._chip_widgets))
        for kachel in label._chip_widgets:
            with self.subTest(kachel=kachel._text):
                self.assertIsInstance(kachel, self.haupt.RoundedButton)
                self.assertTrue(kachel._pille)
                self.assertEqual("place", kachel.winfo_manager())
                self.assertEqual(str(label), str(kachel.place_info()["in"]), "ueber dem Firmware-Label: Mit ihm werden sie ein- und ausgeblendet")
                self.assertEqual(str(label.master), str(kachel.master), "Geschwister des Labels: Es schneidet sie nicht ab")
                self.assertEqual("", str(kachel.cget("cursor")), "keine Hand: eine Kachel zeigt an, sie ist kein Knopf")
                self.assertIsNone(kachel._command)
        # nebeneinander, von links nach rechts in der Reihenfolge der Liste
        _WURZEL.update_idletasks()
        xs = [int(k.place_info()["x"]) for k in label._chip_widgets]
        self.assertEqual(sorted(xs), xs)
        self.assertLess(xs[0], 0, "mittig: die erste Kachel liegt links der Mitte")

    def test_der_text_bleibt_die_grundlage_und_die_hoehe_aendert_sich_nicht(self):
        self.app._sidebar_firmware_aktualisieren({"required_firmware": "10.00.00.00"},
                                                 self._packordner("grundlage", self._LZ4, backport=True))
        import tkinter.font as tkfont
        label = self.app._sidebar_fw_label
        self.assertEqual(2, len(str(label.cget("text")).split("\n")), "weiter zwei Textzeilen: das Cover darf nicht springen")
        self.assertEqual(2 * int(tkfont.Font(font=label.cget("font")).metrics("linespace")) + self.app._SIDEBAR_FW_ABSTAND,
                         self.app._sidebar_fw_hoehe())

    def test_ein_neuer_stand_ersetzt_die_kacheln_und_raeumt_die_alten_weg(self):
        self.app._sidebar_firmware_aktualisieren({"required_firmware": "10.00.00.00"}, self._packordner("alt", self._LZ4))
        alt = list(self.app._sidebar_fw_label._chip_widgets)
        self.assertEqual(2, len(alt))
        self.app._sidebar_firmware_aktualisieren({"required_firmware": "04.51.00.00"}, self.ohne)
        self.assertEqual(1, len(self.app._sidebar_fw_label._chip_widgets))
        self.assertTrue(all(not k.winfo_exists() for k in alt), "die alten Kacheln sind zerstoert, nicht nur verdeckt")

    def test_ohne_angaben_gibt_es_keine_kacheln_und_der_text_steht_wieder(self):
        self.app._sidebar_firmware_aktualisieren({"required_firmware": "10.00.00.00"}, self.ohne)
        self.app._sidebar_firmware_aktualisieren({}, self._packordner("leer", ()))      # neue Quelle, ohne Metadaten und ohne Einbauten
        label = self.app._sidebar_fw_label
        self.assertEqual([], list(label._chip_widgets))
        self.assertFalse(label._chips_aktiv)

    def test_die_gleiche_anzeige_baut_die_kacheln_nicht_neu(self):
        self.app._sidebar_firmware_aktualisieren({"required_firmware": "10.00.00.00"}, self.ohne)
        erste = list(self.app._sidebar_fw_label._chip_widgets)
        self.app._sidebar_fw_chips_setzen(list(self.app._sidebar_fw_label._chips))
        self.assertEqual(erste, list(self.app._sidebar_fw_label._chip_widgets), "kein Flackern bei jedem Neuzeichnen")

    def test_ein_designwechsel_baut_die_kacheln_mit_den_neuen_farben(self):
        self.app._sidebar_firmware_aktualisieren({"required_firmware": "10.00.00.00"}, self.ohne)
        alt = list(self.app._sidebar_fw_label._chip_widgets)
        with mock.patch.dict(self.app._COLORS, {"fg_secondary": "#123456", "fg_primary": "#abcdef"}):
            self.app._sidebar_fw_chips_setzen(list(self.app._sidebar_fw_label._chips))
            neu = list(self.app._sidebar_fw_label._chip_widgets)
        self.assertNotEqual(alt, neu)
        self.assertTrue(all(not k.winfo_exists() for k in alt))

    def test_das_label_zeigt_mit_kacheln_nur_den_bildausschnitt(self):
        """``_redraw_sidebar_captions`` stellt ``compound="none"`` (nur das Bild; ``"image"`` kennt Tk nicht), solange Kacheln da
        sind - sonst stuende der Text daneben."""
        import ast
        text = HAUPT.read_text(encoding="utf-8")
        baum = ast.parse(text)
        funktion = next(k for k in ast.walk(baum) if isinstance(k, ast.FunctionDef) and k.name == "_redraw_sidebar_captions")
        quelle = "\n".join(text.splitlines()[funktion.lineno - 1:funktion.end_lineno])
        self.assertIn("_chips_aktiv", quelle)
        self.assertIn('compound="none"', quelle)
        self.assertNotIn('compound="image"', quelle)
        self.assertIn("_sidebar_fw_ohne_bild", quelle, "auch ohne Seitenleistenbild")
        ohne_bild = next(k for k in ast.walk(baum) if isinstance(k, ast.FunctionDef) and k.name == "_sidebar_fw_ohne_bild")
        self.assertIn('compound="none"', "\n".join(text.splitlines()[ohne_bild.lineno - 1:ohne_bild.end_lineno]))

    def test_jeder_compound_wert_den_das_programm_setzt_kennt_tk(self):
        """Ein unbekannter Wert (``"image"``) warf einen TclError, den die Zeichenroutine still verschluckte: Die Kacheln blieben
        ohne Bildausschnitt, der Text stand daneben (am echten Programm gemessen, 17.11.2026)."""
        gueltig = {"none", "bottom", "top", "left", "right", "center"}
        for wert in ("none", "center"):
            self.assertIn(wert, gueltig)
        label = self.app._sidebar_fw_label
        for wert in ("none", "center"):
            with self.subTest(compound=wert):
                label.config(compound=wert)                  # wirft bei einem Wert, den Tk nicht kennt
                self.assertEqual(wert, str(label.cget("compound")))
        label.config(compound="center")
        with self.assertRaises(tk.TclError):
            label.config(compound="image")

    def test_das_pack_ist_auch_in_einem_zwischengespeicherten_ergebnis_da(self):
        """Der Bildspeicher merkt Ergebnisse je Abbild - ohne die neue Regelnummer fehlte dort das Verfahren."""
        from ps5_validator.utils import bibliothek as bib
        self.assertGreaterEqual(bib.EINBAU_REGEL, 3)

    def test_ein_zwischenstand_ohne_metadaten_nimmt_nichts_weg(self):
        self.app._sidebar_firmware_aktualisieren({"required_firmware": "04.51.00.00"}, self.ohne)
        vorher = self._text()
        self.app._sidebar_firmware_aktualisieren({}, self.ohne)          # Schnellvorschau derselben Quelle
        self.assertEqual(vorher, self._text())

    def test_ein_quellwechsel_leert_die_zeilen(self):
        self.app._sidebar_firmware_aktualisieren({"required_firmware": "10.00.00.00"}, self.mit)
        self.app._sidebar_firmware_aktualisieren({}, self.ohne)          # neue Quelle, noch ohne Metadaten
        self.assertEqual(["", ""], [z.strip() for z in self._text().split("\n")])

    def test_zeilen_stehen_ueber_dem_cover_ohne_ueberlappung(self):
        app = self.app
        cover = Image.new("RGB", (512, 512), (40, 90, 160))
        app.source_path = tk.StringVar(master=_WURZEL, value=self.ohne)
        try:
            app._update_sidebar_preview(cover, "Testspiel")
            _WURZEL.update_idletasks()
            fw, bild, titel = (app._sidebar_fw_label, app._sidebar_preview_img_label,
                               app._sidebar_preview_title_label)
            self.assertEqual("pack", fw.winfo_manager())
            self.assertEqual("pack", bild.winfo_manager())
            slaves = [str(w) for w in fw.master.pack_slaves()]
            self.assertLess(slaves.index(str(fw)), slaves.index(str(bild)), "die Zeilen stehen ueber dem Cover")
            self.assertLess(slaves.index(str(bild)), slaves.index(str(titel)))
            # Verschwindet das Cover, verschwinden die Zeilen mit.
            app._update_sidebar_preview(None, "")
            self.assertEqual("", fw.winfo_manager())
        finally:
            app._update_sidebar_preview(None, "")


if __name__ == "__main__":
    unittest.main()
