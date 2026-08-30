# -*- coding: utf-8 -*-
"""Tests fuer die Direktinstallation einer Anwendung auf der PS5.

Dieses Werkzeug schreibt in die Systempartition der Konsole. Ein Fehler in
der Reihenfolge oder ein falsch gesetztes applicationCategoryType laesst
eine halb angemeldete Anwendung unter /system_ex zurueck, und die bekommt
man ohne FTP nicht wieder weg. Deshalb wird hier gegen einen nachgebauten
FTP-Dienst geprueft, nicht gegen die echte Konsole.
"""
import io
import json
import os
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import PS5ImageConverter_Pro_FINAL_revised as APP
from ps5_validator.utils import app_install, i18n, self_reader

HAUPTDATEI = str(PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py")


def _gui():
    """Programmobjekt ohne Tk - nur die Installationswege werden gebraucht."""
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui._t = lambda key, **kw: key
    return gui


def _fake_self(pfad, authority_id=0x3100000000000002, verschluesselt=False):
    """Schreibt ein SELF, das self_reader wirklich auswertet.

    Die Offsets stehen nicht zur Auswahl - self_reader rechnet den Platz des
    ext_info-Blocks aus dem ELF-Kopf aus. Mit e_phoff=0 und e_phnum=0 ergibt
    sich: Segmenttabelle ab 0x20, ELF-Kopf ab 0x40, ext_info ab 0x80. Wer
    hier daneben liegt, bekommt ein SELF ohne ext_info - und der Test prueft
    dann nichts mehr, ohne dass es auffaellt.
    """
    daten = bytearray(0xC0)
    struct.pack_into("<I", daten, 0x00, self_reader.SELF_MAGIC)
    daten[0x04:0x08] = bytes((0x00, 0x01, 0x01, 0x12))  # version, mode, endian, attr
    struct.pack_into("<I", daten, 0x08, 0x101)          # key_type
    struct.pack_into("<H", daten, 0x0C, 0xC0)           # header_size
    struct.pack_into("<H", daten, 0x0E, 0x100)          # meta_size
    struct.pack_into("<Q", daten, 0x10, 0x1000)         # file_size
    struct.pack_into("<H", daten, 0x18, 1)              # segment_count
    struct.pack_into("<H", daten, 0x1A, 0)              # flags

    seg_flags = self_reader.SEGMENT_FLAG_SIGNED | self_reader.SEGMENT_FLAG_BLOCKED
    if verschluesselt:
        seg_flags |= self_reader.SEGMENT_FLAG_ENCRYPTED
    struct.pack_into("<QQQQ", daten, 0x20, seg_flags, 0x1000, 0x100, 0x100)

    daten[0x40:0x48] = b"\x7fELF" + bytes((2, 1, 1, 0))  # 64 Bit, LE
    struct.pack_into("<H", daten, 0x50, 0xFE10)          # e_type ET_SCE_DYNEXEC
    struct.pack_into("<H", daten, 0x52, 0x3E)            # e_machine x86-64
    struct.pack_into("<I", daten, 0x54, 1)               # e_version
    struct.pack_into("<Q", daten, 0x58, 0x400)           # e_entry
    struct.pack_into("<Q", daten, 0x60, 0)               # e_phoff
    struct.pack_into("<H", daten, 0x78, 0)               # e_phnum

    struct.pack_into("<QQQQ", daten, 0x80, authority_id, 8, 0x07590001,
                     0x07590001)
    with open(pfad, "wb") as fh:
        fh.write(bytes(daten))


def _app_ordner(wurzel, kennung="FAKE02932", eboot=True, param=True,
                icon=True, param_system=False, kategorie=0):
    """Legt einen Anwendungsordner an, wie ihn das Werkzeug erwartet."""
    ordner = os.path.join(wurzel, kennung)
    os.makedirs(os.path.join(ordner, "sce_sys"), exist_ok=True)
    if eboot:
        _fake_self(os.path.join(ordner, "eboot.bin"))
    if param:
        inhalt = {
            "applicationCategoryType": kategorie,
            "localizedParameters": {
                "defaultLanguage": "en-US",
                "en-US": {"titleName": "Testkachel"},
            },
            "titleId": kennung,
        }
        with open(os.path.join(ordner, "sce_sys", "param.json"), "wb") as fh:
            fh.write(json.dumps(inhalt).encode("utf-8"))
    if icon:
        with open(os.path.join(ordner, "sce_sys", "icon0.png"), "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n")
    if param_system:
        with open(os.path.join(ordner, "sce_sys", "param.json.system"),
                  "wb") as fh:
            fh.write(b'{"titleId": "' + kennung.encode() + b'"}')
    return ordner


class _FtpNachbau:
    """Ein FTP-Dienst, so weit nachgebaut, wie dieses Fenster ihn benutzt."""

    def __init__(self, vorhandene_ordner=()):
        self.vorhanden = set(vorhandene_ordner)
        self.angelegt = []
        self.geschrieben = {}
        self.reihenfolge = []
        self.befehle = []

    def sendcmd(self, befehl):
        self.befehle.append(befehl)
        return "200 ok"

    #: Ordner, bei denen mkd scheitert und cwd ebenfalls - also ein
    #: echter Fehler und nicht "gibt es schon".
    unerreichbar: set = set()

    def mkd(self, pfad):
        if pfad in self.vorhanden or pfad in self.unerreichbar:
            raise OSError("550 geht nicht")
        self.vorhanden.add(pfad)
        self.angelegt.append(pfad)

    def cwd(self, pfad):
        if pfad in self.unerreichbar:
            raise OSError("550 kein Zugriff")
        if pfad not in self.vorhanden:
            raise OSError("550 nicht da")
        return "250 ok"

    def storbinary(self, befehl, strom):
        ziel = befehl.split(" ", 1)[1]
        self.geschrieben[ziel] = strom.read()
        self.reihenfolge.append(ziel)


class SelfNachbauTests(unittest.TestCase):
    """Der Testaufbau selbst - ein stummes Fixture prueft nichts."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_nachbau_traegt_ext_info_und_segmente(self):
        pfad = os.path.join(self.tmp, "eboot.bin")
        _fake_self(pfad)
        auskunft = self_reader.read_self(pfad)
        self.assertIsNotNone(auskunft.elf_header, "ELF-Kopf nicht gefunden")
        self.assertIsNotNone(auskunft.ext_info, "ext_info nicht gefunden")
        self.assertEqual(len(auskunft.segments), 1)
        self.assertEqual(auskunft.ext_info.authority_id, 0x3100000000000002)

    def test_verschluesseltes_segment_kommt_auch_an(self):
        pfad = os.path.join(self.tmp, "eboot.bin")
        _fake_self(pfad, verschluesselt=True)
        auskunft = self_reader.read_self(pfad)
        self.assertTrue(auskunft.segments[0].encrypted)


class KennungTests(unittest.TestCase):
    """Die Form der titleId - die Konsole ist hier streng."""

    def test_uebliche_kennung_geht_durch(self):
        self.assertTrue(app_install.kennung_gueltig("FAKE02932"))
        self.assertTrue(app_install.kennung_gueltig("BREW00001"))

    def test_zu_kurz_oder_zu_lang_faellt_durch(self):
        self.assertFalse(app_install.kennung_gueltig("FAKE0293"))
        self.assertFalse(app_install.kennung_gueltig("FAKE029321"))

    def test_kleinbuchstaben_und_ziffern_am_anfang_fallen_durch(self):
        self.assertFalse(app_install.kennung_gueltig("fake02932"))
        self.assertFalse(app_install.kennung_gueltig("12AB02932"))

    def test_buchstaben_im_zahlenteil_fallen_durch(self):
        self.assertFalse(app_install.kennung_gueltig("FAKE0293A"))


class ParamTests(unittest.TestCase):
    """param.json lesen und die beiden Fassungen daraus bauen."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_titelname_kommt_aus_der_vorgabesprache(self):
        param = {"localizedParameters": {"defaultLanguage": "de-DE",
                                         "de-DE": {"titleName": "Deutsch"},
                                         "en-US": {"titleName": "Englisch"}}}
        self.assertEqual(app_install.titelname(param), "Deutsch")

    def test_titelname_nimmt_sonst_irgendeine_sprache(self):
        param = {"localizedParameters": {"en-US": {"titleName": "Englisch"}}}
        self.assertEqual(app_install.titelname(param), "Englisch")

    def test_titelname_faellt_auf_den_ersatz_zurueck(self):
        self.assertEqual(app_install.titelname({}, "FAKE02932"), "FAKE02932")

    def test_installfassung_setzt_die_kategorie_auf_null(self):
        # Auch wenn in der Vorlage schon die Systemkategorie steht - sonst
        # laeuft das Registrieren ins Leere und niemand sieht, woran es lag.
        param = {"applicationCategoryType": app_install.KATEGORIE_SYSTEM,
                 "titleId": "FAKE02932"}
        gebaut = app_install.installfassung(param)
        self.assertEqual(gebaut["applicationCategoryType"],
                         app_install.KATEGORIE_INSTALL)
        self.assertEqual(param["applicationCategoryType"],
                         app_install.KATEGORIE_SYSTEM, "Vorlage veraendert")

    def test_systemfassung_setzt_die_systemkategorie(self):
        gebaut = app_install.systemfassung({"titleId": "FAKE02932"})
        self.assertEqual(gebaut["applicationCategoryType"], 33554432)

    def test_json_wird_ohne_bom_und_mit_zeilenende_geschrieben(self):
        roh = app_install.als_json({"titleId": "FAKE02932"})
        self.assertFalse(roh.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(roh.endswith(b"\n"))
        self.assertEqual(json.loads(roh.decode("utf-8"))["titleId"], "FAKE02932")

    def test_kaputtes_json_meldet_sich_verstaendlich(self):
        pfad = os.path.join(self.tmp, "param.json")
        with open(pfad, "wb") as fh:
            fh.write(b"{kein json")
        with self.assertRaises(app_install.AppInstallFehler) as fall:
            app_install.param_lesen(pfad)
        self.assertIn("param.json", str(fall.exception))


class PruefenTests(unittest.TestCase):
    """Was der Ordner mitbringen muss - und was das Werkzeug dazu sagt."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_vollstaendiger_ordner_ist_bereit(self):
        ordner = _app_ordner(self.tmp)
        angaben, fehler, _hinweise = app_install.pruefen(ordner)
        self.assertEqual(fehler, [])
        self.assertEqual(angaben.kennung, "FAKE02932")
        self.assertEqual(angaben.name, "Testkachel")
        self.assertTrue(angaben.icon)

    def test_fehlendes_eboot_wird_benannt(self):
        ordner = _app_ordner(self.tmp, eboot=False)
        angaben, fehler, _h = app_install.pruefen(ordner)
        self.assertIsNone(angaben)
        self.assertIn("eboot.bin", fehler[0])

    def test_loses_elf_wird_im_fehler_genannt(self):
        # Wer eine .elf ohne Umbenennen hineinlegt, soll das erfahren -
        # sonst sucht er den Fehler in der Konsole.
        ordner = _app_ordner(self.tmp, eboot=False)
        with open(os.path.join(ordner, "hello.elf"), "wb") as fh:
            fh.write(b"\x7fELF")
        _a, fehler, _h = app_install.pruefen(ordner)
        self.assertIn("hello.elf", fehler[0])

    def test_rohes_elf_als_eboot_wird_abgelehnt(self):
        ordner = _app_ordner(self.tmp, eboot=False)
        with open(os.path.join(ordner, "eboot.bin"), "wb") as fh:
            fh.write(b"\x7fELF" + b"\x00" * 60)
        _a, fehler, _h = app_install.pruefen(ordner)
        self.assertTrue(any("rohes ELF" in f for f in fehler), fehler)
        self.assertTrue(any("make_fself" in f for f in fehler), fehler)

    def test_ps4_param_sfo_wird_erkannt(self):
        ordner = _app_ordner(self.tmp, param=False)
        with open(os.path.join(ordner, "sce_sys", "param.sfo"), "wb") as fh:
            fh.write(b"\x00PSF")
        angaben, fehler, _h = app_install.pruefen(ordner)
        self.assertIsNone(angaben)
        self.assertIn("param.sfo", fehler[0])

    def test_fehlende_param_json_wird_benannt(self):
        ordner = _app_ordner(self.tmp, param=False)
        _a, fehler, _h = app_install.pruefen(ordner)
        self.assertIn("param.json", fehler[0])

    def test_krumme_kennung_wird_bemaengelt(self):
        ordner = _app_ordner(self.tmp, kennung="kurz")
        _a, fehler, _h = app_install.pruefen(ordner)
        self.assertTrue(any("ABCD12345" in f for f in fehler), fehler)

    def test_fehlendes_icon_ist_nur_ein_hinweis(self):
        ordner = _app_ordner(self.tmp, icon=False)
        _a, fehler, hinweise = app_install.pruefen(ordner)
        self.assertEqual(fehler, [])
        self.assertTrue(any("icon0.png" in h for h in hinweise), hinweise)

    def test_fehlende_systemfassung_ist_nur_ein_hinweis(self):
        ordner = _app_ordner(self.tmp)
        angaben, fehler, hinweise = app_install.pruefen(ordner)
        self.assertEqual(fehler, [])
        self.assertEqual(angaben.param_system, "")
        self.assertTrue(any("param.json.system" in h for h in hinweise), hinweise)

    def test_vorhandene_systemfassung_wird_benutzt(self):
        ordner = _app_ordner(self.tmp, param_system=True)
        angaben, _f, hinweise = app_install.pruefen(ordner)
        self.assertTrue(angaben.param_system)
        self.assertFalse(any("param.json.system" in h for h in hinweise))

    def test_verschluesseltes_segment_blockiert(self):
        ordner = _app_ordner(self.tmp, eboot=False)
        _fake_self(os.path.join(ordner, "eboot.bin"), verschluesselt=True)
        _a, fehler, _h = app_install.pruefen(ordner)
        self.assertTrue(any("verschluesselte Segmente" in f for f in fehler),
                        fehler)

    def test_echte_sony_autoritaet_blockiert(self):
        ordner = _app_ordner(self.tmp, eboot=False)
        _fake_self(os.path.join(ordner, "eboot.bin"),
                   authority_id=0x4500000000000001)
        _a, fehler, _h = app_install.pruefen(ordner)
        self.assertTrue(any("Sony-Autoritaet" in f for f in fehler), fehler)

    def test_fake_autoritaet_geht_durch_und_heisst_nicht_unbekannt(self):
        # 0x31 ist die Kategorie, die auch libSceAmpr traegt - das Modul, das
        # die Konsole nachweislich laedt.
        ordner = _app_ordner(self.tmp)
        angaben, fehler, _h = app_install.pruefen(ordner)
        self.assertEqual(fehler, [])
        self.assertNotIn("Unbekannt", angaben.autoritaet)

    def test_sdk_autoritaet_wird_abgelehnt(self):
        # 0x38 vergibt make_fself.py ohne weitere Angabe. Am 29.08.2026
        # gemessen: Damit kommt der Start bis zum Prozess und scheitert dann
        # am Entschluesseln der SELF-Bloecke. Dieselbe Anwendung mit 0x31
        # laeuft durch - deshalb ist das ein Fehler und kein Hinweis.
        ordner = _app_ordner(self.tmp, eboot=False)
        _fake_self(os.path.join(ordner, "eboot.bin"),
                   authority_id=0x3800000000000022)
        _a, fehler, _h = app_install.pruefen(ordner)
        self.assertTrue(any("0x38" in f for f in fehler), fehler)
        self.assertTrue(any("0x3100000000000002" in f for f in fehler),
                        "der Fehler muss sagen, womit stattdessen zu signieren ist")

    def test_der_fehler_nennt_den_beobachteten_code(self):
        ordner = _app_ordner(self.tmp, eboot=False)
        _fake_self(os.path.join(ordner, "eboot.bin"),
                   authority_id=0x3800000000000022)
        _a, fehler, _h = app_install.pruefen(ordner)
        self.assertTrue(any("CE-108262-9" in f for f in fehler), fehler)

    def test_ordner_der_keiner_ist(self):
        angaben, fehler, _h = app_install.pruefen(
            os.path.join(self.tmp, "gibtsnicht"))
        self.assertIsNone(angaben)
        self.assertIn("Kein Ordner", fehler[0])


class ZielpfadTests(unittest.TestCase):
    """Wohin auf der Konsole geschrieben wird."""

    def test_vier_ordner_in_beiden_baeumen(self):
        ziele = app_install.zielordner("FAKE02932")
        self.assertEqual(ziele, (
            "/system_ex/app/FAKE02932",
            "/system_ex/app/FAKE02932/sce_sys",
            "/user/app/FAKE02932",
            "/user/app/FAKE02932/sce_sys"))


class AntwortTests(unittest.TestCase):
    """Was die Konsole zurueckmeldet - und wie das gelesen wird."""

    def test_erfolgszeile_wird_erkannt(self):
        ok, text = app_install.antwort_beurteilen(
            "appinst: registriere 'FAKE02932' aus /user/app/\n"
            "appinst: 'FAKE02932' registriert")
        self.assertTrue(ok)
        self.assertIn("registriert", text)

    def test_die_ankuendigung_allein_zaehlt_nicht(self):
        # "registriere ..." steht vor dem Aufruf. Wer nur nach dem Wortstamm
        # sucht, meldet Erfolg, obwohl die Konsole abgebrochen hat.
        ok, _text = app_install.antwort_beurteilen(
            "appinst: registriere 'FAKE02932' aus /user/app/\n"
            "appinst: sceAppInstUtilAppInstallTitleDir: 8090000a")
        self.assertFalse(ok)

    def test_stille_wird_als_fehler_gewertet(self):
        ok, text = app_install.antwort_beurteilen("")
        self.assertFalse(ok)
        self.assertIn("9021", text)

    def test_fehlercode_kommt_im_text_zurueck(self):
        ok, text = app_install.antwort_beurteilen(
            "appinst: sceAppInstUtilInitialize: 8090000a")
        self.assertFalse(ok)
        self.assertIn("8090000a", text)


class UebertragungTests(unittest.TestCase):
    """Die Reihenfolge auf der Konsole - sie ist nicht beliebig."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ordner = _app_ordner(self.tmp)
        self.angaben = app_install.pruefen(self.ordner)[0]
        self.ftp = _FtpNachbau()
        self.gesendet = []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _uebertragen(self, antwort="appinst: 'FAKE02932' registriert"):
        gui = _gui()
        echt = app_install.payload_senden

        def _nachbau(host, daten, **kw):
            self.gesendet.append((host, len(daten)))
            return antwort
        app_install.payload_senden = _nachbau
        try:
            return gui._appinstall_uebertragen(
                self.ftp, self.angaben, "10.0.0.5", b"ELF", lambda t: None)
        finally:
            app_install.payload_senden = echt

    def test_alle_vier_ordner_werden_angelegt(self):
        self._uebertragen()
        self.assertEqual(set(self.ftp.angelegt),
                         set(app_install.zielordner("FAKE02932")))

    def test_mtrw_kommt_vor_dem_anlegen(self):
        self._uebertragen()
        self.assertEqual(self.ftp.befehle, [app_install.BESCHREIBBAR])

    def test_systemfassung_kommt_zuletzt(self):
        # Vor dem Registrieren geschrieben, sucht die Konsole die Anwendung
        # schon in /system_ex, waehrend sie noch unter /user/app liegt.
        self._uebertragen()
        self.assertEqual(self.ftp.reihenfolge[-1],
                         "/system_ex/app/FAKE02932/sce_sys/param.json")

    def test_payload_geht_erst_nach_allen_dateien_raus(self):
        self._uebertragen()
        vor_dem_payload = self.ftp.reihenfolge[:-1]
        for erwartet in ("/system_ex/app/FAKE02932/eboot.bin",
                         "/user/app/FAKE02932/sce_sys/param.json",
                         "/user/app/FAKE02932/sce_sys/icon0.png",
                         app_install.KENNUNGSDATEI):
            self.assertIn(erwartet, vor_dem_payload)

    def test_payload_geht_an_die_uebergebene_adresse(self):
        self._uebertragen()
        self.assertEqual(self.gesendet, [("10.0.0.5", 3)])

    def test_kennungsdatei_traegt_die_title_id(self):
        self._uebertragen()
        self.assertEqual(self.ftp.geschrieben[app_install.KENNUNGSDATEI],
                         b"FAKE02932\n")

    def test_hochgeladene_param_json_traegt_kategorie_null(self):
        self._uebertragen()
        roh = self.ftp.geschrieben["/user/app/FAKE02932/sce_sys/param.json"]
        self.assertEqual(
            json.loads(roh.decode("utf-8"))["applicationCategoryType"],
            app_install.KATEGORIE_INSTALL)

    def test_nachgereichte_param_json_traegt_die_systemkategorie(self):
        self._uebertragen()
        roh = self.ftp.geschrieben["/system_ex/app/FAKE02932/sce_sys/param.json"]
        self.assertEqual(
            json.loads(roh.decode("utf-8"))["applicationCategoryType"], 33554432)

    def test_abgelehntes_payload_bricht_vor_der_systemfassung_ab(self):
        with self.assertRaises(app_install.AppInstallFehler):
            self._uebertragen(antwort="appinst: /data/appinst.txt nicht lesbar")
        self.assertNotIn("/system_ex/app/FAKE02932/sce_sys/param.json",
                         self.ftp.geschrieben)

    def test_vorhandene_ordner_stoeren_nicht(self):
        self.ftp = _FtpNachbau(
            vorhandene_ordner=app_install.zielordner("FAKE02932"))
        self._uebertragen()
        self.assertEqual(self.ftp.angelegt, [])
        self.assertIn("/system_ex/app/FAKE02932/eboot.bin", self.ftp.geschrieben)

    def test_fehlendes_icon_laesst_den_rest_durchlaufen(self):
        self.ordner = _app_ordner(self.tmp, kennung="BREW00001", icon=False)
        self.angaben = app_install.pruefen(self.ordner)[0]
        self.ftp = _FtpNachbau()
        self._uebertragen(antwort="appinst: 'BREW00001' registriert")
        self.assertNotIn("/user/app/BREW00001/sce_sys/icon0.png",
                         self.ftp.geschrieben)
        self.assertIn("/system_ex/app/BREW00001/eboot.bin", self.ftp.geschrieben)


    def test_echter_ordnerfehler_bricht_ab(self):
        # Bis zur Durchsicht galt jede Ausnahme von mkd als "gibt es
        # schon". Fehlende Schreibrechte trotz MTRW sahen damit aus wie
        # ein vorhandener Ordner - und der Lauf schrieb weiter in eine
        # halb angelegte Installation.
        self.ftp.unerreichbar = {app_install.USER_APP + "/FAKE02932/sce_sys"}
        try:
            with self.assertRaises(app_install.AppInstallFehler):
                self._uebertragen()
        finally:
            self.ftp.unerreichbar = set()
        self.assertEqual(self.ftp.geschrieben, {},
                         "trotz unbrauchbarem Ordner geschrieben")

    def test_vorhandener_ordner_bleibt_folgenlos(self):
        # Die Gegenprobe: Was wirklich schon da ist, darf nicht stoeren.
        self.ftp = _FtpNachbau(
            vorhandene_ordner=app_install.zielordner("FAKE02932"))
        self._uebertragen()
        self.assertEqual(self.ftp.angelegt, [])
        self.assertIn("/system_ex/app/FAKE02932/eboot.bin", self.ftp.geschrieben)

    def test_der_elfldr_pfad_wird_durchgereicht(self):
        # Ohne ihn weckt payload_senden elfldr nicht, faellt auf den
        # Payload Manager zurueck - und der liefert keine Ausgabe, womit
        # antwort_beurteilen() zwangslaeufig fehlschlaegt.
        with io.open(HAUPTDATEI, "rb") as fh:
            quelle = fh.read().decode("utf-8")
        self.assertIn("elfldr_pfad=self._elfldr_payload_path()", quelle)
        self.assertNotIn("app_install.payload_senden(host, payload)", quelle)


class PayloadTests(unittest.TestCase):
    """Das mitgelieferte ELF - ohne das geht nichts."""

    def test_payload_liegt_bei_und_ist_ein_elf(self):
        with open(app_install.payload_finden(), "rb") as fh:
            self.assertEqual(fh.read(4), b"\x7fELF")

    def test_quelltext_liegt_daneben(self):
        # Das Payload stammt von GPL-3-Quellen ab; ohne den Quelltext waere
        # die Weitergabe nicht zulaessig.
        ordner = os.path.dirname(app_install.payload_finden())
        self.assertTrue(os.path.isfile(os.path.join(ordner, "appinst.c")))
        self.assertTrue(os.path.isfile(os.path.join(ordner, "NOTICE.md")))

    def test_payload_liest_die_kennung_zur_laufzeit(self):
        # Faellt es auf ein einkompiliertes TITLE_ID zurueck, taugt es nur
        # noch fuer genau eine Anwendung.
        ordner = os.path.dirname(app_install.payload_finden())
        with open(os.path.join(ordner, "appinst.c"), "rb") as fh:
            quelle = fh.read().decode("utf-8")
        self.assertIn(app_install.KENNUNGSDATEI, quelle)
        self.assertNotIn("-DTITLE_ID", quelle)


class OberflaecheTests(unittest.TestCase):
    """Verdrahtung im Hauptprogramm."""

    @classmethod
    def setUpClass(cls):
        with io.open(HAUPTDATEI, "rb") as fh:
            cls.quelle = fh.read().decode("utf-8")

    def test_werkzeug_steht_im_menue(self):
        self.assertIn('("titlebar.appinstall", "_show_app_install")',
                      self.quelle)

    def test_alle_texte_gibt_es_in_beiden_sprachen(self):
        for schluessel, werte in i18n.STRINGS.items():
            if (schluessel.startswith("appinstall.")
                    or schluessel == "titlebar.appinstall"):
                self.assertTrue(werte.get("de"), schluessel)
                self.assertTrue(werte.get("en"), schluessel)

    def test_erklaertext_nennt_den_gemessenen_fehlercode(self):
        # Ohne diese Zahl sucht der Anwender den Fehler bei sich.
        self.assertIn("CE-100096-6", i18n.STRINGS["appinstall.hint_why"]["de"])

    def test_erklaertext_nennt_beide_dienste(self):
        text = i18n.STRINGS["appinstall.hint_needs"]["de"]
        self.assertIn("2121", text)
        self.assertIn("9021", text)

    def test_erklaertexte_stehen_im_fenster(self):
        for schluessel in ("appinstall.hint_what", "appinstall.hint_why",
                           "appinstall.hint_needs"):
            self.assertIn(schluessel, self.quelle)

    def test_bericht_nennt_die_zielordner(self):
        gui = _gui()
        tmp = tempfile.mkdtemp()
        try:
            angaben = app_install.pruefen(_app_ordner(tmp))[0]
            text = gui._appinstall_bericht(angaben, [], [])
            self.assertIn("/system_ex/app/FAKE02932", text)
            self.assertIn("/user/app/FAKE02932", text)
            self.assertIn("Bereit zum Installieren", text)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_bericht_zeigt_fehler_vor_der_freigabe(self):
        gui = _gui()
        text = gui._appinstall_bericht(None, ["etwas stimmt nicht"], [])
        self.assertIn("FEHLER", text)
        self.assertNotIn("Bereit zum Installieren", text)



class DeeplinkTests(unittest.TestCase):
    """Die Bauform, die auf einer echten Konsole nachweislich laeuft.

    Abgelesen an sechs Kacheln, die dort zur Messzeit liefen: nur
    sce_sys/param.json und icon0.png unter /user/app, Kategorie 65536,
    deeplinkUri - kein eboot.bin, kein /system_ex.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_vollstaendige_angaben_sind_bereit(self):
        angaben, fehler, _h = app_install.deeplink_pruefen(
            "PLDM00002", "Testkachel", "http://127.0.0.1:8084/")
        self.assertEqual(fehler, [])
        self.assertEqual(angaben.art, app_install.ART_DEEPLINK)
        self.assertEqual(angaben.name, "Testkachel")

    def test_param_json_gleicht_den_laufenden_kacheln(self):
        param = app_install.deeplink_param("PLDM00002", "Test", "http://127.0.0.1:8084/")
        self.assertEqual(param["applicationCategoryType"], 65536)
        self.assertEqual(param["deeplinkUri"], "http://127.0.0.1:8084/")
        self.assertEqual(param["titleId"], "PLDM00002")
        self.assertNotIn("eboot", json.dumps(param))

    def test_ohne_namen_steht_die_kennung_da(self):
        param = app_install.deeplink_param("PLDM00002", "", "http://127.0.0.1:1/")
        self.assertEqual(
            param["localizedParameters"]["en-US"]["titleName"], "PLDM00002")

    def test_adresse_ohne_schema_wird_abgelehnt(self):
        _a, fehler, _h = app_install.deeplink_pruefen(
            "PLDM00002", "Test", "127.0.0.1:8084")
        self.assertTrue(any("http://" in f for f in fehler), fehler)

    def test_leere_adresse_wird_abgelehnt(self):
        _a, fehler, _h = app_install.deeplink_pruefen("PLDM00002", "Test", "")
        self.assertTrue(fehler)

    def test_krumme_kennung_wird_bemaengelt(self):
        _a, fehler, _h = app_install.deeplink_pruefen(
            "kurz", "Test", "http://127.0.0.1:1/")
        self.assertTrue(any("ABCD12345" in f for f in fehler), fehler)

    def test_fremde_adresse_ist_nur_ein_hinweis(self):
        _a, fehler, hinweise = app_install.deeplink_pruefen(
            "PLDM00002", "Test", "https://example.invalid/")
        self.assertEqual(fehler, [])
        self.assertTrue(any("Konsole selbst" in h for h in hinweise), hinweise)

    def test_fehlendes_symbolbild_ist_ein_fehler_wenn_angegeben(self):
        _a, fehler, _h = app_install.deeplink_pruefen(
            "PLDM00002", "Test", "http://127.0.0.1:1/",
            os.path.join(self.tmp, "gibtsnicht.png"))
        self.assertTrue(any("Symbolbild" in f for f in fehler), fehler)

    def test_nur_zwei_zielordner_system_ex_bleibt_unberuehrt(self):
        # Das ist der Kern des Unterschieds: /system_ex wird gar nicht
        # angefasst, und genau deshalb entsteht auch kein SELF, das die
        # Konsole entschluesseln muesste.
        ziele = app_install.deeplink_zielordner("PLDM00002")
        self.assertEqual(ziele, ("/user/app/PLDM00002",
                                 "/user/app/PLDM00002/sce_sys"))
        self.assertFalse(any("system_ex" in z for z in ziele))


class DeeplinkUebertragungTests(unittest.TestCase):
    """Was bei der Deeplink-Kachel auf der Konsole ankommt."""

    def setUp(self):
        self.angaben = app_install.deeplink_pruefen(
            "PLDM00002", "Testkachel", "http://127.0.0.1:8084/")[0]
        self.ftp = _FtpNachbau()

    def _uebertragen(self, antwort="appinst: 'PLDM00002' registriert"):
        gui = _gui()
        echt = app_install.payload_senden
        app_install.payload_senden = lambda *a, **k: antwort
        try:
            return gui._appinstall_uebertragen(
                self.ftp, self.angaben, "10.0.0.5", b"ELF", lambda t: None)
        finally:
            app_install.payload_senden = echt

    def test_kein_eboot_und_kein_system_ex(self):
        self._uebertragen()
        for ziel in self.ftp.geschrieben:
            self.assertNotIn("system_ex", ziel)
            self.assertNotIn("eboot.bin", ziel)

    def test_param_json_traegt_die_deeplink_kategorie(self):
        # Nicht 0 und nicht 33554432: Es wird nichts nachgereicht, also ist
        # die hochgeladene Fassung schon die endgueltige.
        self._uebertragen()
        roh = self.ftp.geschrieben["/user/app/PLDM00002/sce_sys/param.json"]
        param = json.loads(roh.decode("utf-8"))
        self.assertEqual(param["applicationCategoryType"], 65536)
        self.assertEqual(param["deeplinkUri"], "http://127.0.0.1:8084/")

    def test_nur_die_beiden_user_ordner_werden_angelegt(self):
        self._uebertragen()
        self.assertEqual(set(self.ftp.angelegt),
                         set(app_install.deeplink_zielordner("PLDM00002")))

    def test_kennungsdatei_wird_trotzdem_geschrieben(self):
        # Das Registrieren laeuft ueber dasselbe Payload wie beim anderen Weg.
        self._uebertragen()
        self.assertEqual(self.ftp.geschrieben[app_install.KENNUNGSDATEI],
                         b"PLDM00002\n")

    def test_abgelehntes_payload_bricht_ab(self):
        with self.assertRaises(app_install.AppInstallFehler):
            self._uebertragen(antwort="appinst: Lauf endet ohne Erfolg")

if __name__ == "__main__":
    unittest.main(verbosity=2)
