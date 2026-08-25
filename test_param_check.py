"""Tests fuer die inhaltliche Pruefung und Reparatur der param.json.

Bis v1.8.50 pruefte das Programm die Datei nur mit ``json.loads``. Alles, was
syntaktisch stimmt und trotzdem auf der Konsole scheitert, kam durch. Diese
Tests halten fest, dass genau diese Faelle jetzt auffallen - und dass die
Reparatur sie aufloest, ohne vorhandene Angaben wegzuwerfen.

Die Wertelisten stammen aus den Referenzwerkzeugen unter ``PS5 SDK usw/``.
Deren Beispieldateien dienen hier als Pruefstein: Liegt der Ordner vor, muss
die vollstaendige Datei aus LibProsperoPKG fehlerfrei durchgehen und die
knappe aus dem ps5-payload-sdk ohne Fehler (nur mit Warnungen) - anders herum
waere die Pruefung entweder zu lasch oder zu streng.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from collections import OrderedDict
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import param_check as pc
from ps5_validator.utils.param_manifest import APPLICATION_DRM_TYPES

REFERENZ_VOLLSTAENDIG = (
    PROJEKT / "PS5 SDK usw" / "LibProsperoPKG-2.5" / "LibProsperoPKG-2.5"
    / "src" / "HomebrewTest" / "sce_sys" / "param.json"
)
REFERENZ_KNAPP = (
    PROJEKT / "PS5 SDK usw" / "PS5_PAYLOAD_SDK" / "samples" / "install_app"
    / "FAKE02932" / "sce_sys" / "param.json"
)


def _gueltiges_dokument(**abweichungen) -> "OrderedDict[str, object]":
    """Ein Dokument, das die Pruefung fehlerfrei besteht."""
    doc: "OrderedDict[str, object]" = OrderedDict([
        ("titleId", "PPSA12345"),
        ("contentId", "UP0001-PPSA12345_00-ABCDEFGH12345678"),
        ("conceptId", "12345"),
        ("applicationCategoryType", 0),
        ("applicationDrmType", "standard"),
        ("contentBadgeType", 2),
        ("attribute", 0),
        ("attribute2", 0),
        ("attribute3", 0),
        ("contentVersion", "01.000.000"),
        ("masterVersion", "01.00"),
        ("ageLevel", pc.vollstaendiger_altersblock()),
        ("localizedParameters", OrderedDict([
            ("defaultLanguage", "en-US"),
            ("en-US", OrderedDict([("titleName", "Testspiel")])),
        ])),
        ("gameIntent", OrderedDict([
            ("permittedIntents", [OrderedDict([("intentType", "launchActivity")])]),
        ])),
    ])
    doc.update(abweichungen)
    return doc


class GrundlagenTests(unittest.TestCase):
    """Ein sauberes Dokument darf keine Fehler erzeugen."""

    def test_gueltiges_dokument_ohne_fehler(self):
        befund = pc.pruefe_daten(_gueltiges_dokument())
        self.assertTrue(befund.ok, befund.fehler)
        self.assertEqual(befund.art, "base")

    def test_drm_liste_kommt_aus_dem_manifest_modul(self):
        # Zwei Wahrheiten im selben Programm waeren eine zu viel: Der
        # Manifest-Editor fuehrt dieselbe Liste.
        self.assertEqual(pc.DRM_TYPEN, frozenset(APPLICATION_DRM_TYPES))
        self.assertEqual(sorted(pc.DRM_TYPEN), ["free", "freemium", "standard"])

    def test_art_erkennung(self):
        self.assertEqual(pc.art_erkennen(_gueltiges_dokument()), "base")
        self.assertEqual(
            pc.art_erkennen(_gueltiges_dokument(targetContentVersion="01.001.000")),
            "patch")
        self.assertEqual(
            pc.art_erkennen(_gueltiges_dokument(disc=[{"role": "Play Disc"}])),
            "disc")


class FehlerfaelleTests(unittest.TestCase):
    """Genau die Faelle, die json.loads durchgelassen hat."""

    def _fehler(self, **abweichungen) -> list[str]:
        return pc.pruefe_daten(_gueltiges_dokument(**abweichungen)).fehler

    def test_version_als_zahl(self):
        # Der haeufigste Fall: Wer die Datei im Editor "aufraeumt", macht aus
        # "01.000.000" schnell 1.0 - und verliert die fuehrende Null.
        fehler = self._fehler(contentVersion=1.0)
        self.assertTrue(any("Zahl" in f for f in fehler), fehler)
        # Und nur einmal gemeldet, nicht zweimal.
        self.assertEqual(len([f for f in fehler if "contentVersion" in f]), 1, fehler)

    def test_content_id_nennt_andere_title_id(self):
        fehler = self._fehler(contentId="UP0001-PPSA99999_00-ABCDEFGH12345678")
        self.assertTrue(any("PPSA99999" in f and "PPSA12345" in f for f in fehler), fehler)

    def test_anwendungstyp_im_drm_feld(self):
        # 'upgradable' und 'demo' sind Anwendungstypen, keine DRM-Werte. Die
        # Referenz bildet sie auf 'standard' bzw. 'free' ab.
        for falsch, gemeint in (("upgradable", "standard"), ("demo", "free")):
            with self.subTest(wert=falsch):
                fehler = self._fehler(applicationDrmType=falsch)
                self.assertTrue(any(gemeint in f for f in fehler), fehler)

    def test_unbekannter_drm_wert(self):
        fehler = self._fehler(applicationDrmType="irgendwas")
        self.assertTrue(any("unbekannt" in f for f in fehler), fehler)

    def test_fehlender_sprachblock(self):
        fehler = self._fehler(localizedParameters=OrderedDict([
            ("defaultLanguage", "de-DE"),
            ("en-US", OrderedDict([("titleName", "Test")])),
        ]))
        self.assertTrue(any("de-DE" in f for f in fehler), fehler)

    def test_leerer_titelname(self):
        fehler = self._fehler(localizedParameters=OrderedDict([
            ("defaultLanguage", "en-US"),
            ("en-US", OrderedDict([("titleName", "   ")])),
        ]))
        self.assertTrue(any("titleName" in f for f in fehler), fehler)

    def test_harte_pflichtfelder(self):
        for feld in pc.HARTE_PFLICHTFELDER:
            with self.subTest(feld=feld):
                doc = _gueltiges_dokument()
                del doc[feld]
                befund = pc.pruefe_daten(doc)
                self.assertFalse(befund.ok)
                self.assertTrue(any(feld in f for f in befund.fehler), befund.fehler)

    def test_weiche_pflichtfelder_sind_nur_warnungen(self):
        # Homebrew fuehrt regelmaessig nur eine Handvoll Felder und laeuft.
        for feld in pc.WEICHE_PFLICHTFELDER:
            with self.subTest(feld=feld):
                doc = _gueltiges_dokument()
                del doc[feld]
                befund = pc.pruefe_daten(doc)
                self.assertTrue(befund.ok, f"{feld}: {befund.fehler}")

    def test_wahrheitswert_statt_ganzzahl(self):
        fehler = self._fehler(attribute=True)
        self.assertTrue(any("Wahrheitswert" in f for f in fehler), fehler)

    def test_altersfreigabe_ohne_default(self):
        fehler = self._fehler(ageLevel=OrderedDict([("DE", 0)]))
        self.assertTrue(any("default" in f for f in fehler), fehler)


class FirmwareTests(unittest.TestCase):
    """Die Hex-Felder rechnen in BCD, nicht binaer."""

    def test_umrechnung_hin_und_zurueck(self):
        roh = pc.firmware_aus_text("5.50")
        self.assertEqual(roh, 0x0550000000000000)
        self.assertEqual(pc.firmware_als_text(roh), "05.50")

    def test_bcd_nicht_binaer(self):
        # 0x50 ist nicht 50 dezimal: Waere die Umrechnung binaer, kaeme 0x32
        # heraus und jede Grenzpruefung laege daneben.
        self.assertEqual((pc.firmware_aus_text("1.14") >> 48) & 0xFF, 0x14)

    def test_zu_hohe_firmware_wird_gemeldet(self):
        doc = _gueltiges_dokument(requiredSystemSoftwareVersion="0x0700000000000000")
        befund = pc.pruefe_daten(doc, hoechste_firmware="5.50")
        self.assertTrue(any("Systemupdate" in f for f in befund.fehler), befund.fehler)

    def test_passende_firmware_geht_durch(self):
        doc = _gueltiges_dokument(requiredSystemSoftwareVersion="0x0500000000000000")
        befund = pc.pruefe_daten(doc, hoechste_firmware="5.50")
        self.assertTrue(befund.ok, befund.fehler)

    def test_hexfeld_mit_falschem_format(self):
        befund = pc.pruefe_daten(_gueltiges_dokument(sdkVersion="1.14"))
        self.assertFalse(befund.ok)


class DateiTests(unittest.TestCase):
    """Lesen von der Platte - BOM, Kodierung, Syntax."""

    def setUp(self):
        self.ordner = tempfile.mkdtemp(prefix="param_check_")
        os.makedirs(os.path.join(self.ordner, "sce_sys"), exist_ok=True)
        self.pfad = os.path.join(self.ordner, "sce_sys", "param.json")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.ordner, ignore_errors=True)

    def _schreiben(self, roh: bytes) -> None:
        with open(self.pfad, "wb") as datei:
            datei.write(roh)

    def test_fehlende_datei(self):
        befund = pc.pruefe_datei(self.pfad)
        self.assertTrue(befund.fehlt)
        self.assertTrue(befund.unlesbar)
        self.assertFalse(befund.reparierbar)

    def test_bom_ist_ein_fehler(self):
        # Genau daran scheitert die Konsole, waehrend jeder Editor die Datei
        # anstandslos anzeigt.
        text = json.dumps(_gueltiges_dokument())
        self._schreiben(b"\xef\xbb\xbf" + text.encode("utf-8"))
        befund = pc.pruefe_datei(self.pfad, nachbarn_pruefen=False)
        self.assertTrue(any("BOM" in f for f in befund.fehler), befund.fehler)

    def test_utf16_wird_abgelehnt(self):
        self._schreiben(json.dumps(_gueltiges_dokument()).encode("utf-16"))
        befund = pc.pruefe_datei(self.pfad, nachbarn_pruefen=False)
        self.assertTrue(befund.unlesbar)

    def test_komma_vor_klammer(self):
        self._schreiben(b'{"titleId": "PPSA12345",}')
        befund = pc.pruefe_datei(self.pfad, nachbarn_pruefen=False)
        self.assertTrue(befund.unlesbar)
        self.assertTrue(any("Komma" in f for f in befund.fehler), befund.fehler)

    def test_syntaxfehler_nennt_die_zeile(self):
        self._schreiben(b'{\n  "titleId": "PPSA12345"\n  "contentId": "x"\n}')
        befund = pc.pruefe_datei(self.pfad, nachbarn_pruefen=False)
        self.assertTrue(any("Zeile" in f for f in befund.fehler), befund.fehler)

    def test_fehlendes_icon_ist_eine_warnung(self):
        self._schreiben(json.dumps(_gueltiges_dokument()).encode("utf-8"))
        befund = pc.pruefe_datei(self.pfad)
        self.assertTrue(befund.ok, befund.fehler)
        self.assertTrue(any("icon0.png" in w for w in befund.warnungen), befund.warnungen)

    def test_ordnername_gegen_title_id(self):
        # Der Ordner heisst hier nach dem Zufallsnamen des Temp-Verzeichnisses,
        # traegt also kein Title-ID-Muster - das ist ein Hinweis, kein Fehler.
        self._schreiben(json.dumps(_gueltiges_dokument()).encode("utf-8"))
        befund = pc.pruefe_datei(self.pfad)
        self.assertTrue(any("übergeordnete Ordner" in h for h in befund.hinweise),
                        befund.hinweise)


class ReparaturTests(unittest.TestCase):
    """Reparieren heisst berichtigen, nicht ueberschreiben."""

    def test_vorhandene_angaben_bleiben(self):
        doc = _gueltiges_dokument(contentVersion=1.0)
        doc["localizedParameters"]["en-US"]["titleName"] = "Mein Spiel"
        neu, aenderungen = pc.repariere(doc)
        self.assertEqual(neu["localizedParameters"]["en-US"]["titleName"], "Mein Spiel")
        self.assertEqual(neu["contentVersion"], "01.000.000")
        self.assertTrue(aenderungen)

    def test_reparatur_loest_den_befund_auf(self):
        doc = _gueltiges_dokument(
            contentVersion=1.0,
            applicationDrmType="upgradable",
            contentId="UP0001-PPSA99999_00-ABCDEFGH12345678",
        )
        self.assertFalse(pc.pruefe_daten(doc).ok)
        neu, _ = pc.repariere(doc, title_id="PPSA12345")
        befund = pc.pruefe_daten(neu)
        self.assertTrue(befund.ok, befund.fehler)

    def test_content_id_wird_auf_die_title_id_abgeglichen(self):
        doc = _gueltiges_dokument(contentId="UP0001-PPSA99999_00-ABCDEFGH12345678")
        neu, _ = pc.repariere(doc, title_id="PPSA12345")
        self.assertEqual(neu["contentId"][7:16], "PPSA12345")
        # Die Kennung am Ende bleibt erhalten - sie steht so auch im Paket.
        self.assertTrue(neu["contentId"].endswith("ABCDEFGH12345678"))

    def test_anwendungstyp_wird_auf_den_drm_wert_gezogen(self):
        neu, _ = pc.repariere(_gueltiges_dokument(applicationDrmType="demo"))
        self.assertEqual(neu["applicationDrmType"], "free")

    def test_knappe_datei_wird_aufgefuellt(self):
        doc = OrderedDict([
            ("titleId", "FAKE02932"),
            ("applicationCategoryType", 0),
            ("localizedParameters", OrderedDict([
                ("defaultLanguage", "en-US"),
                ("en-US", OrderedDict([("titleName", "FAKE02932")])),
            ])),
        ])
        neu, aenderungen = pc.repariere(doc)
        self.assertTrue(pc.pruefe_daten(neu).ok)
        self.assertIn("ageLevel", neu)
        self.assertEqual(len(neu["ageLevel"]), len(pc.LAENDER) + 1)
        self.assertTrue(aenderungen)

    def test_defaultlanguage_steht_vorn(self):
        neu, _ = pc.repariere(_gueltiges_dokument())
        self.assertEqual(list(neu["localizedParameters"])[0], "defaultLanguage")

    def test_neu_anlegen_ist_gueltig(self):
        doc = pc.neu_anlegen(title_id="PPSA12345", titel="Testspiel")
        befund = pc.pruefe_daten(doc)
        self.assertTrue(befund.ok, befund.fehler)
        self.assertEqual(pc.titel_aus_daten(doc), "Testspiel")

    def test_neu_anlegen_knapp(self):
        doc = pc.neu_anlegen(title_id="FAKE02932", vollstaendig=False)
        # Auch die knappe Fassung muss die harten Pflichtfelder tragen.
        befund = pc.pruefe_daten(doc)
        self.assertTrue(befund.ok, befund.fehler)


class ReferenzdateiTests(unittest.TestCase):
    """Gegenprobe an den mitgelieferten Referenzwerkzeugen.

    Sie laufen nur, wenn der Ordner ``PS5 SDK usw/`` vorliegt - er ist reines
    Nachschlagematerial und weder im Repository noch im Auslieferungsstand.
    """

    @unittest.skipUnless(REFERENZ_VOLLSTAENDIG.is_file(),
                         "LibProsperoPKG-Beispiel nicht vorhanden")
    def test_vollstaendige_referenz_ohne_fehler(self):
        befund = pc.pruefe_datei(str(REFERENZ_VOLLSTAENDIG))
        self.assertTrue(befund.ok, befund.fehler)

    @unittest.skipUnless(REFERENZ_KNAPP.is_file(),
                         "payload-sdk-Beispiel nicht vorhanden")
    def test_knappe_referenz_ohne_fehler(self):
        # Drei Felder, laeuft auf der Konsole: Waere die Pruefung strenger,
        # meldete sie jedes Homebrew faelschlich als kaputt.
        befund = pc.pruefe_datei(str(REFERENZ_KNAPP))
        self.assertTrue(befund.ok, befund.fehler)
        self.assertTrue(befund.warnungen)


class ValidatorTests(unittest.TestCase):
    """Aufgabe 8 prueft die param.json inhaltlich mit."""

    def setUp(self):
        self.ordner = tempfile.mkdtemp(prefix="param_dump_")
        os.makedirs(os.path.join(self.ordner, "sce_sys"))
        with open(os.path.join(self.ordner, "eboot.bin"), "wb") as datei:
            datei.write(b"X" * 64)
        with open(os.path.join(self.ordner, "sce_sys", "icon0.png"), "wb") as datei:
            datei.write(b"P" * 32)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.ordner, ignore_errors=True)

    def _param_schreiben(self, doc) -> None:
        pfad = os.path.join(self.ordner, "sce_sys", "param.json")
        with open(pfad, "w", encoding="utf-8") as datei:
            json.dump(doc, datei)

    def test_defekte_param_json_faellt_auf(self):
        from ps5_validator.modules.dump_validator import DumpValidator

        self._param_schreiben(_gueltiges_dokument(contentVersion=1.0))
        ergebnis = DumpValidator(threads=1).validate(self.ordner)
        block = ergebnis.summary.get("param_json")
        self.assertIsNotNone(block, "Der Validator meldet keinen param.json-Block")
        self.assertTrue(block["fehler"])
        self.assertTrue(block["reparierbar"])
        self.assertTrue(any("param.json" in e for e in ergebnis.errors), ergebnis.errors)

    def test_gute_param_json_stoert_nicht(self):
        from ps5_validator.modules.dump_validator import DumpValidator

        self._param_schreiben(_gueltiges_dokument())
        ergebnis = DumpValidator(threads=1).validate(self.ordner)
        block = ergebnis.summary.get("param_json")
        self.assertIsNotNone(block)
        self.assertEqual(block["fehler"], [])
        self.assertFalse(any("param.json" in e for e in ergebnis.errors), ergebnis.errors)


class _StummerFortschritt:
    """Ersatz fuer die ProgressEngine: nimmt alles entgegen, tut nichts.

    Der Ablauftest interessiert sich fuer das Urteil, nicht fuer den Balken.
    """

    _payload_total = 1.0

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class AblaufTests(unittest.TestCase):
    """Aufgabe 8 im Ganzen - vom fehlenden param.json bis zum Urteil.

    Bis v1.8.52 lief die param.json-Behandlung *nach* dem Durchlauf. Da die
    Datei in ``CRITICAL_FILES`` steht, stand das Urteil FEHLGESCHLAGEN da
    schon fest: Der Nutzer las "param.json wurde neu erstellt - Pruefung
    bestanden" und bekam darueber ein rotes Fehlerfenster.
    """

    def setUp(self):
        from ps5_validator.utils.param_manifest import (
            NPTITLE_MAGIC, NPTITLE_TITLE_ID_OFFSET)

        self.ordner = tempfile.mkdtemp(prefix="param_ablauf_")
        os.makedirs(os.path.join(self.ordner, "sce_sys"))
        with open(os.path.join(self.ordner, "eboot.bin"), "wb") as datei:
            datei.write(b"X" * 4096)
        with open(os.path.join(self.ordner, "sce_sys", "pfs-version.dat"), "wb") as datei:
            datei.write(b"01.002.000")
        # nptitle.dat nach dem Layout des Lesers, damit die Title-ID ohne
        # Ordnernamen und ohne Netz gefunden wird.
        roh = bytearray(b"\x00" * (NPTITLE_TITLE_ID_OFFSET + 32))
        roh[:len(NPTITLE_MAGIC)] = NPTITLE_MAGIC
        roh[NPTITLE_TITLE_ID_OFFSET:NPTITLE_TITLE_ID_OFFSET + 12] = b"PPSA00003_00"
        with open(os.path.join(self.ordner, "sce_sys", "nptitle.dat"), "wb") as datei:
            datei.write(bytes(roh))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.ordner, ignore_errors=True)

    def _gui(self, *, antwort: bool):
        import types

        from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI

        gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
        gui.protokoll = []
        gui._append_to_log = gui.protokoll.append
        gui.root = types.SimpleNamespace(after=lambda *a, **k: None)
        gui.progress_engine = _StummerFortschritt()
        gui.task_progress = 0.0
        gui.is_running = True
        gui.mkpfs_dir = ""
        gui._extract_embedded_mkpfs = lambda: ""
        gui._set_status = lambda *a, **k: None
        gui._get_worker_count = lambda vorgabe: 1
        # Kein Netzzugriff im Test; die Rueckfrage wird hier beantwortet.
        gui._online_nachschlag_erlaubt = lambda: False
        gui._param_frage = lambda *a, **k: antwort
        return gui

    def test_angelegte_param_json_rettet_den_lauf(self):
        pfad = os.path.join(self.ordner, "sce_sys", "param.json")
        self.assertFalse(os.path.exists(pfad))

        gui = self._gui(antwort=True)
        bestanden = gui._mode_dump_validator(self.ordner)
        protokoll = "".join(gui.protokoll)

        self.assertTrue(os.path.isfile(pfad), "param.json wurde nicht angelegt")
        self.assertTrue(bestanden, "Aufgabe 8 meldet einen Fehlschlag, obwohl "
                                   "die param.json im selben Lauf entstand:\n"
                                   + protokoll[-1500:])
        self.assertIn("BESTANDEN", protokoll)
        self.assertNotIn("FEHLGESCHLAGEN", protokoll)

    def test_abgelehnte_hilfe_bleibt_ein_fehlschlag(self):
        gui = self._gui(antwort=False)
        bestanden = gui._mode_dump_validator(self.ordner)

        self.assertFalse(bestanden, "Ohne param.json darf der Lauf nicht bestehen")
        self.assertIn("FEHLGESCHLAGEN", "".join(gui.protokoll))


class AnbindungTests(unittest.TestCase):
    """Die Bauwege und Aufgabe 8 gehen ueber dieselbe Pruefung."""

    QUELLE = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"

    @classmethod
    def setUpClass(cls):
        cls.text = cls.QUELLE.read_text(encoding="utf-8")

    def test_kein_blosses_json_loads_mehr(self):
        # Frueher stand an drei Stellen derselbe Block mit json.loads. Taucht
        # er wieder auf, ist die inhaltliche Pruefung dort umgangen.
        self.assertNotIn('json.loads(param_json_path.read_text(encoding="utf-8"))',
                         self.text)

    def test_alle_drei_bauwege_nutzen_die_pruefung(self):
        self.assertEqual(self.text.count("_ensure_param_json("), 4)  # 3 Aufrufe + Definition

    def test_validator_bietet_die_reparatur_an(self):
        self.assertIn("_validator_param_json_anbieten", self.text)

    def test_param_json_kommt_vor_der_pruefung(self):
        # Die param.json steht in CRITICAL_FILES. Wird sie erst nach dem
        # Durchlauf angelegt, ist das Urteil schon gefaellt: Der Nutzer las
        # "param.json wurde neu erstellt - Pruefung bestanden" und bekam
        # darueber ein rotes Fehlerfenster (bis v1.8.52).
        anfang = self.text.index("            if is_dir:")
        ende = self.text.index("            elif is_exfat:", anfang)
        block = self.text[anfang:ende]
        self.assertIn("_validator_param_json_anbieten(src)", block)
        self.assertLess(
            block.index("_validator_param_json_anbieten(src)"),
            block.index("result = _run_validator("),
            "Die param.json wird wieder erst nach dem Durchlauf behandelt.",
        )

    def test_pruefaufgaben_reden_nicht_von_konvertierung(self):
        # Aufgabe 8 und die Inspektion wandeln nichts um. Der Hinweis auf
        # einen mkpfs-Exit-Code verwies dort auf einen Schritt, den es in
        # diesen Aufgaben gar nicht gibt.
        self.assertNotIn('"Die Konvertierung ist fehlgeschlagen.', self.text)
        self.assertIn('if mode in ("inspect", "dump_validator"):', self.text)
        self.assertIn('self._t("dialog.msg.check_found_problems")', self.text)

    def test_fehlermeldungen_in_beiden_sprachen(self):
        from ps5_validator.utils.i18n import STRINGS

        for schluessel in (
            "dialog.title.check_found_problems",
            "dialog.msg.check_found_problems",
            "dialog.msg.conversion_failed",
            "dialog.msg.ffpkg_build_failed",
        ):
            self.assertIn(schluessel, STRINGS)
            for sprache in ("de", "en"):
                self.assertTrue(STRINGS[schluessel].get(sprache), schluessel)

    def test_meldungen_in_beiden_sprachen(self):
        from ps5_validator.utils.i18n import STRINGS, translate

        for schluessel in (
            "dialog.msg.param_json_offer_repair",
            "dialog.title.param_json_findings",
            "log.manual.param_json_findings",
            "log.manual.param_json_ok",
            "log.manual.param_json_repaired",
            "log.manual.param_json_repair_declined",
            "log.manual.param_json_repair_failed",
            "log.manual.param_json_backup",
            "validator.param_json_heading",
            "validator.param_json_missing",
        ):
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, STRINGS)
                for sprache in ("de", "en"):
                    self.assertNotEqual(translate(sprache, schluessel), schluessel)


class CliSchalterTests(unittest.TestCase):
    """Die Rueckfragen im nicht-interaktiven Betrieb."""

    def _oberflaeche(self, **eigenschaften):
        import PS5ImageConverter_Pro_FINAL_revised as APP

        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._cli_mode = True
        gui._cli_param_repair = False
        gui._cli_param_online = False
        for name, wert in eigenschaften.items():
            setattr(gui, name, wert)
        return gui

    def test_ohne_schalter_wird_abgelehnt(self):
        gui = self._oberflaeche()
        self.assertFalse(gui._param_frage("t", "m"))
        self.assertFalse(gui._param_frage("t", "m", online=True))

    def test_reparaturschalter_wirkt_nur_auf_die_reparatur(self):
        # --yes darf den Online-Nachschlag nicht nebenbei mitentscheiden:
        # dabei geht die Title-ID an einen fremden Dienst.
        gui = self._oberflaeche(_cli_param_repair=True)
        self.assertTrue(gui._param_frage("t", "m"))
        self.assertFalse(gui._param_frage("t", "m", online=True))

    def test_onlineschalter_wirkt_nur_auf_den_nachschlag(self):
        gui = self._oberflaeche(_cli_param_online=True)
        self.assertFalse(gui._param_frage("t", "m"))
        self.assertTrue(gui._param_frage("t", "m", online=True))

    def test_parser_kennt_beide_schalter(self):
        import PS5ImageConverter_Pro_FINAL_revised as APP

        args = APP._build_cli_parser().parse_args(
            ["--cli", "--task", "1", "--source", "x",
             "--param-json-reparieren", "--param-json-online"])
        self.assertTrue(args.param_json_reparieren)
        self.assertTrue(args.param_json_online)

    def test_standardmaessig_beide_aus(self):
        import PS5ImageConverter_Pro_FINAL_revised as APP

        args = APP._build_cli_parser().parse_args(
            ["--cli", "--task", "1", "--source", "x"])
        self.assertFalse(args.param_json_reparieren)
        self.assertFalse(args.param_json_online)


if __name__ == "__main__":
    unittest.main(verbosity=2)
