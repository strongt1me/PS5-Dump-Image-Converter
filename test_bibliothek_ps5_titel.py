# -*- coding: utf-8 -*-
"""Bibliothek, Quelle "PS5": die Konsole von selbst finden, alle ihre Spiele zeigen.

Wunsch des Nutzers vom 25.09.2026: "Bei der Bibliothek sollte, wenn man auf
PS5 klickt, die PS5 automatisch gefunden werden (wie beim AMPR EMU in
Aufgabe 7) und die Spiele von der PS5 anzeigen (auch die PKG-installierten
PS4-Spiele)."

Bis dahin verlangte die Bibliothek eine eingetragene Adresse und zeigte nur
Sicherungen aus den Ablageorten (``/data/homebrew`` usw.) - ein per PKG
installiertes Spiel kam nie vor.

Gemessen wird gegen eine Konsole im Speicher (:class:`_Konsole`): ein
Verzeichnisbaum hinter denselben FTP-Befehlen, die das Programm benutzt
(``pwd``, ``cwd``, ``mlsd``, ``retrbinary``). Ins Netz geht kein Test.
"""
from __future__ import annotations

import ast
import ftplib
import io
import json
import struct
import sys
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("bibliothek_ps5_titel")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import remoteplay                  # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False

APPMETA = APP.PS5ConverterGUI._AMPR_GEN_APPMETA


def _sfo(werte: dict) -> bytes:
    """Eine param.sfo, wie PS4-Titel sie tragen.

    Zeichenketten als UTF-8 (Format 0x0204), Zahlen wie ``SYSTEM_VER`` als
    32-Bit-Wert im Format 0x0404 - so steht es in echten Dateien, und der
    Leser des Programms bekommt es als Rohbytes.
    """
    schluessel = b""
    daten = b""
    eintraege = []
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
    data_ptr = key_ptr + len(schluessel)
    kopf = b"\0PSF" + struct.pack("<IIII", 0x0101, key_ptr, data_ptr, len(eintraege))
    tabelle = b"".join(struct.pack("<HHIII", *e) for e in eintraege)
    return kopf + tabelle + schluessel + daten


def _json(titel: str, kennung: str, **felder) -> bytes:
    daten = {"titleId": kennung,
             "localizedParameters": {"defaultLanguage": "de-DE",
                                     "de-DE": {"titleName": titel}}}
    daten.update(felder)
    return json.dumps(daten).encode()


#: Die Angaben der installierten Titel und der Sicherung in :func:`_bestand`.
ZWEI = {"contentVersion": "01.002.000",
        "requiredSystemSoftwareVersion": "0x0900000000000000",
        "sdkVersion": "0x0850000000000000",
        "contentId": "EP0001-PPSA00002_00-SPIELZWEI0000000"}
DREI = {"TITLE": "PS4 Spiel Drei", "TITLE_ID": "CUSA00003",
        "CONTENT_ID": "UP0001-CUSA00003_00-PS4SPIELDREI0000",
        "APP_VER": "01.05", "VERSION": "01.00", "SYSTEM_VER": 0x05050000}


class _Konsole:
    """Ein Verzeichnisbaum hinter den FTP-Befehlen, die das Programm benutzt."""

    def __init__(self, dateien: dict) -> None:
        self.dateien = dict(dateien)
        self.ordner = {"/"}
        for pfad in self.dateien:
            teile = pfad.strip("/").split("/")[:-1]
            for n in range(1, len(teile) + 1):
                self.ordner.add("/" + "/".join(teile[:n]))
        self.hier = "/"
        self.befehle: list = []

    def pwd(self) -> str:
        return self.hier

    def cwd(self, pfad: str) -> str:
        ziel = pfad if pfad.startswith("/") else self.hier.rstrip("/") + "/" + pfad
        ziel = "/" + ziel.strip("/") if ziel != "/" else "/"
        if ziel not in self.ordner:
            raise ftplib.error_perm("550 %s: No such directory" % pfad)
        self.hier = ziel
        return "250 ok"

    def mlsd(self, *_a, **_k):
        vorne = self.hier.rstrip("/") + "/"
        namen = {}
        for pfad in self.ordner:
            if pfad != self.hier and pfad.startswith(vorne) and "/" not in pfad[len(vorne):]:
                namen[pfad[len(vorne):]] = {"type": "dir"}
        for pfad, inhalt in self.dateien.items():
            if pfad.startswith(vorne) and "/" not in pfad[len(vorne):]:
                namen[pfad[len(vorne):]] = {"type": "file", "size": str(len(inhalt))}
        return iter(sorted(namen.items()))

    def retrbinary(self, befehl: str, rueckruf, *_a, **_k) -> str:
        pfad = befehl.split(" ", 1)[1]
        self.befehle.append(("RETR", pfad))
        if pfad not in self.dateien:
            raise ftplib.error_perm("550 %s: No such file" % pfad)
        rueckruf(self.dateien[pfad])
        return "226 ok"

    def quit(self) -> str:
        return "221 bye"

    def close(self) -> None:
        pass


def _bestand() -> dict:
    """Eine Konsole mit einer Sicherung und drei Titeln in appmeta.

    * ``/data/homebrew/Spiel Eins`` - ein Dump-Ordner (PPSA00001), der
      zugleich in appmeta steht: Er darf nur einmal in der Liste stehen.
    * ``PPSA00002`` - ein installiertes PS5-Spiel (param.json).
    * ``CUSA00003`` - ein per PKG installiertes PS4-Spiel (param.sfo).
    * ``NPXS40000`` - eine Systemanwendung: gehoert nicht in die Liste.
    """
    return {
        "/data/homebrew/Spiel Eins/eboot.bin": b"\x7fELF",
        "/data/homebrew/Spiel Eins/sce_sys/param.json": _json(
            "Spiel Eins", "PPSA00001", contentVersion="01.001.000",
            requiredSystemSoftwareVersion="0x0700000000000000"),
        APPMETA + "/PPSA00001/param.json": _json("Spiel Eins", "PPSA00001"),
        APPMETA + "/PPSA00002/param.json": _json("Spiel Zwei", "PPSA00002", **ZWEI),
        APPMETA + "/CUSA00003/param.sfo": _sfo(DREI),
        APPMETA + "/NPXS40000/param.json": _json("Einstellungen", "NPXS40000"),
    }


def _gui():
    """Ein Programmobjekt ohne Fenster - fuer Methoden, die keins brauchen."""
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui._current_language = "de"
    return gui


def _suchlauf(konsole: _Konsole):
    """Der Suchlauf der Quelle "PS5" gegen ``konsole`` - die Suche gilt als erfolgreich."""
    gui = _gui()
    with mock.patch.object(gui, "_bibliothek_ps5_finden",
                           return_value=("10.0.0.5", ""), create=True), \
            mock.patch.object(gui, "_ampr_ftp_connect", return_value=konsole):
        return gui._bibliothek_ps5_scannen()


class InstalliertTests(unittest.TestCase):
    """Die Titel aus appmeta: PS5 und PS4, ohne Systemanwendungen, ohne Doppelte."""

    def _scannen(self, konsole: _Konsole):
        return _suchlauf(konsole)

    def test_installierte_spiele_stehen_in_der_liste(self) -> None:
        eintraege, fehler = self._scannen(_Konsole(_bestand()))
        self.assertEqual("", fehler)
        nach_kennung = {e["title_id"]: e for e in eintraege}
        self.assertEqual({"PPSA00001", "PPSA00002", "CUSA00003"}, set(nach_kennung))
        self.assertEqual("folder", nach_kennung["PPSA00001"]["kind"],
                         "Die Sicherung bleibt die Sicherung - kein zweiter Eintrag.")
        for kennung, titel, plattform in (("PPSA00002", "Spiel Zwei", "PS5"),
                                          ("CUSA00003", "PS4 Spiel Drei", "PS4")):
            with self.subTest(kennung=kennung):
                eintrag = nach_kennung[kennung]
                self.assertEqual("installiert", eintrag["kind"])
                self.assertTrue(eintrag["installiert"])
                self.assertTrue(eintrag["ps5"])
                self.assertEqual(plattform, eintrag["plattform"])
                self.assertEqual(titel, eintrag["meta"]["title"])
                self.assertEqual(kennung, eintrag["meta"]["title_id"])

    def test_systemanwendungen_bleiben_draussen(self) -> None:
        eintraege, _fehler = self._scannen(_Konsole(_bestand()))
        self.assertFalse([e for e in eintraege if e["title_id"].startswith("NPXS")])

    def test_ohne_appmeta_bleibt_es_bei_den_sicherungen(self) -> None:
        bestand = {k: v for k, v in _bestand().items() if not k.startswith(APPMETA)}
        eintraege, fehler = self._scannen(_Konsole(bestand))
        self.assertEqual("", fehler)
        self.assertEqual(["folder"], [e["kind"] for e in eintraege])

    def test_ohne_namen_steht_die_kennung_da(self) -> None:
        bestand = _bestand()
        bestand[APPMETA + "/CUSA00004/icon0.png"] = b"\x89PNG"
        eintraege, _fehler = self._scannen(_Konsole(bestand))
        eintrag = next(e for e in eintraege if e["title_id"] == "CUSA00004")
        self.assertEqual("CUSA00004", eintrag["meta"]["title"])

    def test_die_konsole_wird_nur_gelesen(self) -> None:
        """appmeta gehoert der Konsole (Systembereich) - nur RETR, nie STOR/DELE."""
        konsole = _Konsole(_bestand())
        self._scannen(konsole)
        self.assertTrue(konsole.befehle)
        self.assertEqual({"RETR"}, {b[0] for b in konsole.befehle})


class AngabenTests(unittest.TestCase):
    """Fassung, Firmware, SDK und Content-ID der Titel auf der Konsole.

    Wunsch vom 26.09.2026 ("mach das mit Version und Firmware"): Ohne Fassung
    kann die Bibliothek kein Update vergleichen, ohne Firmware keinen
    BACKPORT-Hinweis geben. Bis dahin las sie auf der Konsole nur Name und
    Title-ID.
    """

    def _nach_kennung(self, bestand: dict | None = None) -> dict:
        eintraege, fehler = _suchlauf(_Konsole(bestand or _bestand()))
        self.assertEqual("", fehler)
        return {e["title_id"]: e for e in eintraege}

    def test_installiertes_ps5_spiel(self) -> None:
        meta = self._nach_kennung()["PPSA00002"]["meta"]
        self.assertEqual("Spiel Zwei", meta["title"])
        self.assertEqual("01.002.000", meta["version"])
        self.assertEqual("09.00.00.00", meta["required_firmware"])
        self.assertEqual("08.50.00.00", meta["sdk"])
        self.assertEqual(ZWEI["contentId"], meta["content_id"])

    def test_ps4_fassung_eines_patches_aus_app_ver(self) -> None:
        """In der param.sfo eines Patches traegt APP_VER die Fassung, VERSION bleibt 01.00."""
        meta = self._nach_kennung()["CUSA00003"]["meta"]
        self.assertEqual("PS4 Spiel Drei", meta["title"])
        self.assertEqual("01.05", meta["version"])
        self.assertEqual("05.05.00.00", meta["required_firmware"],
                         "SYSTEM_VER kommt als Rohbytes (Format 0x0404).")
        self.assertEqual(DREI["CONTENT_ID"], meta["content_id"])

    def test_neu_gemastertes_ps4_paket_aus_version(self) -> None:
        """Gemessen an der Konsole des Nutzers (26.09.2026): Gran Turismo 7,
        CATEGORY gd, APP_VER 01.00, VERSION 01.63 - der Stand steht in VERSION."""
        bestand = _bestand()
        bestand[APPMETA + "/CUSA24767/param.sfo"] = _sfo({
            "TITLE": "Gran Turismo 7", "TITLE_ID": "CUSA24767", "CATEGORY": "gd",
            "APP_VER": "01.00", "VERSION": "01.63", "SYSTEM_VER": 0x11008000})
        meta = self._nach_kennung(bestand)["CUSA24767"]["meta"]
        self.assertEqual("01.63", meta["version"])
        self.assertEqual("11.00.80.00", meta["required_firmware"])

    def test_ohne_app_ver_gilt_version(self) -> None:
        bestand = _bestand()
        bestand[APPMETA + "/CUSA00003/param.sfo"] = _sfo(
            {k: v for k, v in DREI.items() if k != "APP_VER"})
        self.assertEqual("01.00", self._nach_kennung(bestand)["CUSA00003"]["meta"]["version"])

    def test_eingehaengter_titel_aus_user_app(self) -> None:
        """Gemessen an der Konsole des Nutzers (26.09.2026, Styx CUSA03877): In appmeta
        nur eine knappe param.json, die volle param.sfo unter /user/app/<ID>/sce_sys."""
        bestand = _bestand()
        bestand[APPMETA + "/CUSA00009/param.json"] = json.dumps(
            {"titleId": "CUSA00009", "titleName": "Eingehaengt"}).encode()
        bestand["/user/app/CUSA00009/sce_sys/param.sfo"] = _sfo(dict(
            DREI, TITLE="Eingehaengt", TITLE_ID="CUSA00009", APP_VER="01.00",
            VERSION="01.02", SYSTEM_VER=0x04008000))
        meta = self._nach_kennung(bestand)["CUSA00009"]["meta"]
        self.assertEqual("Eingehaengt", meta["title"])
        self.assertEqual("01.02", meta["version"])
        self.assertEqual("04.00.80.00", meta["required_firmware"])

    def test_per_pkg_installiert_fragt_user_app_nicht(self) -> None:
        """appmeta ist vollstaendig - kein vergeblicher Umlauf nach /user/app."""
        konsole = _Konsole(_bestand())
        _suchlauf(konsole)
        self.assertFalse([p for _b, p in konsole.befehle if p.startswith("/user/app/")])

    def test_abbild_auf_der_konsole_bekommt_die_angaben_der_konsole(self) -> None:
        """Ein Abbild laesst sich ueber FTP nicht lesen - eingehaengt fuehrt die
        Konsole es aber in appmeta (6 von 9 Sicherungen beim Nutzer, 26.09.2026)."""
        bestand = _bestand()
        bestand["/data/homebrew/PPSA00010.ffpfsc"] = b"x" * 64
        bestand[APPMETA + "/PPSA00010/param.json"] = _json(
            "Spiel Zehn", "PPSA00010", contentVersion="01.012.000",
            requiredSystemSoftwareVersion="0x1000000000000000")
        nach_kennung = self._nach_kennung(bestand)
        eintrag = nach_kennung["PPSA00010"]
        self.assertEqual("ffpfsc", eintrag["kind"], "Bleibt die Sicherung - kein zweiter Eintrag.")
        self.assertEqual("01.012.000", eintrag["meta"]["version"])
        self.assertEqual("10.00.00.00", eintrag["meta"]["required_firmware"])
        self.assertEqual("Spiel Zehn", eintrag["meta"]["title"],
                         "Ein Name, der nur die Kennung ist, weicht dem der Konsole.")

    def test_ein_eigener_name_bleibt(self) -> None:
        bestand = _bestand()
        bestand["/data/homebrew/Mein Spiel PPSA00010.ffpfsc"] = b"x" * 64
        bestand[APPMETA + "/PPSA00010/param.json"] = _json(
            "Spiel Zehn", "PPSA00010", contentVersion="01.012.000")
        eintrag = self._nach_kennung(bestand)["PPSA00010"]
        self.assertEqual("Mein Spiel PPSA00010", eintrag["meta"]["title"])
        self.assertEqual("01.012.000", eintrag["meta"]["version"])

    def test_zwei_sicherungen_derselben_kennung_bleiben_ohne(self) -> None:
        """Welche von zweien die Konsole fuehrt, laesst sich nicht sagen."""
        bestand = _bestand()
        bestand["/data/homebrew/PPSA00010 alt.ffpfsc"] = b"x" * 64
        bestand["/data/homebrew/PPSA00010 neu.ffpkg"] = b"x" * 64
        bestand[APPMETA + "/PPSA00010/param.json"] = _json(
            "Spiel Zehn", "PPSA00010", contentVersion="01.012.000")
        eintraege, _fehler = _suchlauf(_Konsole(bestand))
        zehn = [e for e in eintraege if e["title_id"] == "PPSA00010"]
        self.assertEqual(2, len(zehn))
        self.assertEqual([None, None], [e["meta"].get("version") for e in zehn])

    def test_ergaenzen_nimmt_nur_was_fehlt(self) -> None:
        eintrag = {"title_id": "PPSA00010",
                   "meta": {"title": "PPSA00010", "title_id": "PPSA00010",
                            "version": "01.000.000", "sdk": "–"}}
        APP.PS5ConverterGUI._bibliothek_ps5_ergaenzen(
            eintrag, {"title": "Spiel Zehn", "version": "01.005.000", "sdk": "10.00.00.00",
                      "required_firmware": "10.00.00.00"})
        self.assertEqual({"title": "Spiel Zehn", "title_id": "PPSA00010",
                          "version": "01.000.000", "sdk": "10.00.00.00",
                          "required_firmware": "10.00.00.00"}, eintrag["meta"])

    def test_ein_dump_ordner_behaelt_seine_angaben(self) -> None:
        """Er bringt seine param.json selbst mit - appmeta wird dafuer nicht gefragt."""
        bestand = _bestand()
        bestand[APPMETA + "/PPSA00001/param.json"] = _json(
            "Spiel Eins", "PPSA00001", contentVersion="01.099.000")
        konsole = _Konsole(bestand)
        eintraege, _fehler = _suchlauf(konsole)
        eins = next(e for e in eintraege if e["title_id"] == "PPSA00001")
        self.assertEqual("01.001.000", eins["meta"]["version"])
        self.assertNotIn(("RETR", APPMETA + "/PPSA00001/param.json"), konsole.befehle)

    def test_die_sicherung_auf_der_konsole_auch(self) -> None:
        meta = self._nach_kennung()["PPSA00001"]["meta"]
        self.assertEqual("Spiel Eins", meta["title"])
        self.assertEqual("01.001.000", meta["version"])
        self.assertEqual("07.00.00.00", meta["required_firmware"])

    def test_ps4_dump_ordner_aus_der_param_sfo(self) -> None:
        """Ein PS4-Dump hat keine param.json - bis zum 26.09.2026 blieb er ohne Angaben."""
        bestand = _bestand()
        bestand["/data/homebrew/ps4dump/eboot.bin"] = b"\x7fELF"
        bestand["/data/homebrew/ps4dump/sce_sys/param.sfo"] = _sfo(
            dict(DREI, TITLE="PS4 Dump Fuenf", TITLE_ID="CUSA00005"))
        eintrag = self._nach_kennung(bestand)["CUSA00005"]
        self.assertEqual("folder", eintrag["kind"])
        self.assertEqual("PS4 Dump Fuenf", eintrag["meta"]["title"])
        self.assertEqual("01.05", eintrag["meta"]["version"])

    def test_title_id_aus_der_content_id(self) -> None:
        bestand = _bestand()
        bestand["/data/homebrew/ohne/eboot.bin"] = b"\x7fELF"
        bestand["/data/homebrew/ohne/sce_sys/param.json"] = json.dumps(
            {"titleName": "Ohne Kennung", "contentVersion": "01.000.000",
             "contentId": "EP0001-PPSA00007_00-OHNEKENNUNG00000"}).encode()
        eintrag = self._nach_kennung(bestand)["PPSA00007"]
        self.assertEqual("Ohne Kennung", eintrag["meta"]["title"])
        self.assertEqual("PPSA00007", eintrag["meta"]["title_id"])

    def test_der_name_wie_in_aufgabe_7(self) -> None:
        """Die Sprache der Datei zuerst - der Metadatenleser naehme en-US."""
        bestand = _bestand()
        roh = json.dumps({"titleId": "PPSA00002", "contentVersion": "01.002.000",
                          "localizedParameters": {
                              "defaultLanguage": "de-DE",
                              "de-DE": {"titleName": "Spiel Zwei"},
                              "en-US": {"titleName": "Game Two"}}}).encode()
        bestand[APPMETA + "/PPSA00002/param.json"] = roh
        meta = self._nach_kennung(bestand)["PPSA00002"]["meta"]
        self.assertEqual(_gui()._ampr_gen_name_aus_json(roh), meta["title"])
        self.assertEqual("Spiel Zwei", meta["title"])
        self.assertEqual("01.002.000", meta["version"])

    def test_keine_platzhalter_in_den_angaben(self) -> None:
        """Was die Datei nicht nennt, fehlt - kein "–", das wie ein Wert aussieht."""
        for kennung, eintrag in self._nach_kennung().items():
            with self.subTest(kennung=kennung):
                self.assertEqual([], [k for k, v in eintrag["meta"].items()
                                      if str(v).strip() in ("", "-", "–")])

    def test_die_datei_der_eigenen_plattform_zuerst(self) -> None:
        """Kein vergeblicher Umlauf je Titel nach der Datei der anderen Plattform."""
        konsole = _Konsole(_bestand())
        _suchlauf(konsole)
        geholt = [pfad for _befehl, pfad in konsole.befehle]
        self.assertIn(APPMETA + "/PPSA00002/param.json", geholt)
        self.assertNotIn(APPMETA + "/PPSA00002/param.sfo", geholt)
        self.assertIn(APPMETA + "/CUSA00003/param.sfo", geholt)
        self.assertNotIn(APPMETA + "/CUSA00003/param.json", geholt)

    def test_beide_sfo_leser_nehmen_die_hoehere_fassung(self) -> None:
        """Die param.sfo wird an zwei Stellen ausgewertet - sie duerfen nicht auseinanderlaufen."""
        gui = _gui()
        ohne = {k: v for k, v in DREI.items() if k not in ("APP_VER", "VERSION")}
        for werte, erwartet in ((DREI, "01.05"),                                      # Patch
                                (dict(ohne, APP_VER="01.00", VERSION="01.63"), "01.63"),  # Master
                                (dict(ohne, VERSION="01.02"), "01.02"),
                                (dict(ohne, APP_VER="01.07"), "01.07"),
                                (dict(ohne, APP_VER="01.10", VERSION="01.09"), "01.10")):
            roh = _sfo(werte)
            with self.subTest(erwartet=erwartet):
                self.assertEqual(erwartet, gui._meta_aus_sfo(APP.parse_sfo(roh))["version"])
                self.assertEqual(erwartet, gui._meta_from_param_sfo_bytes(roh)["version"])
        self.assertEqual("–", gui._meta_aus_sfo(APP.parse_sfo(_sfo(ohne)))["version"])
        self.assertEqual("–", gui._meta_from_param_sfo_bytes(_sfo(ohne))["version"])

    def test_was_als_ps4_titel_gilt(self) -> None:
        ist = APP.PS5ConverterGUI._bibliothek_ist_ps4
        self.assertTrue(ist({"plattform": "PS4", "title_id": "PPSA00001"}),
                        "Die Plattform des Suchlaufs gilt vor der Kennung.")
        self.assertFalse(ist({"plattform": "PS5", "title_id": "CUSA00001"}))
        self.assertTrue(ist({"meta": {"title_id": "CUSA00001"}}))
        self.assertTrue(ist({"title_id": "pusa00001"}))
        self.assertFalse(ist({"meta": {"title_id": "PPSA00001"}}))
        self.assertTrue(ist({"meta": {}}, {"title_id": "CUSA00001"}),
                        "Die nachgelesenen Angaben zaehlen mit.")
        self.assertFalse(ist({}))


class FindenTests(unittest.TestCase):
    """Die Konsole von selbst finden - dieselben Stufen wie Aufgabe 7."""

    def _gui(self, *, gespeichert: str = "", profile=(), antworten=(),
             rundruf=(), netz=()):
        gui = _gui()
        gui._bibliothek_ps5_host = ""
        einstellungen = {"ps5_ip": gespeichert}
        gui._load_setting = lambda k, v=None: einstellungen.get(k, v)
        gui._ampr_gen_profil_adressen = lambda: list(profile)
        gui._ampr_gen_ist_ps5 = lambda host, _port, **_k: host in antworten
        gui.netz_gefragt = []
        gui._ampr_gen_netz_absuchen = lambda _port, _melde: (
            gui.netz_gefragt.append(True) or list(netz))
        gui.gemerkt = []
        gui._ampr_gen_adresse_merken = lambda _f, _m, host: gui.gemerkt.append(host) or True
        gui.rundruf = list(rundruf)
        return gui

    def _finden(self, gui):
        meldungen: list = []
        with mock.patch.object(remoteplay, "suchen", lambda *_a, **_k: list(gui.rundruf)):
            host, fehler = gui._bibliothek_ps5_finden(None, meldungen.append)
        return host, fehler, meldungen

    def test_die_gespeicherte_adresse_zuerst(self) -> None:
        gui = self._gui(gespeichert="10.0.0.5", antworten={"10.0.0.5"})
        host, fehler, _m = self._finden(gui)
        self.assertEqual(("10.0.0.5", ""), (host, fehler))
        self.assertEqual([], gui.netz_gefragt, "Kein Netzdurchlauf, wenn sie antwortet.")
        self.assertEqual([], gui.gemerkt, "Nichts zu merken - sie steht schon da.")

    def test_per_rundruf_gefunden_und_zum_merken_angeboten(self) -> None:
        gui = self._gui(antworten={"10.0.0.9"},
                        rundruf=[remoteplay.Konsole(adresse="10.0.0.9", name="PS5",
                                                    status=200)])
        host, fehler, _m = self._finden(gui)
        self.assertEqual(("10.0.0.9", ""), (host, fehler))
        self.assertEqual(["10.0.0.9"], gui.gemerkt)
        self.assertEqual([], gui.netz_gefragt)
        self.assertEqual("10.0.0.9", gui._bibliothek_ps5_adresse(),
                         "Auch ohne Speichern gilt sie fuer diesen Programmlauf.")

    def test_konsole_ohne_ftp_wird_so_benannt(self) -> None:
        gui = self._gui(rundruf=[remoteplay.Konsole(adresse="10.0.0.9", name="PS5",
                                                    status=620)])
        host, fehler, _m = self._finden(gui)
        self.assertEqual("", host)
        self.assertIn("10.0.0.9", fehler)
        self.assertEqual([], gui.netz_gefragt,
                         "Die Konsole ist gefunden - das Netz abzusuchen bringt nichts.")

    def test_zuletzt_das_netz(self) -> None:
        gui = self._gui(gespeichert="10.0.0.5", antworten={"10.0.0.7"}, netz=["10.0.0.7"])
        host, fehler, meldungen = self._finden(gui)
        self.assertEqual(("10.0.0.7", ""), (host, fehler))
        self.assertEqual([True], gui.netz_gefragt)
        self.assertEqual(["10.0.0.7"], gui.gemerkt)
        self.assertTrue(meldungen, "Die Suche sagt, was sie tut.")

    def test_nichts_gefunden(self) -> None:
        gui = self._gui(gespeichert="10.0.0.5")
        host, fehler, _m = self._finden(gui)
        self.assertEqual("", host)
        self.assertEqual(gui._t("library.ps5_nicht_gefunden"), fehler)

    def test_der_suchlauf_meldet_den_fehler_der_suche(self) -> None:
        gui = _gui()
        verbunden: list = []
        with mock.patch.object(gui, "_bibliothek_ps5_finden",
                               return_value=("", "gibt es nicht"), create=True), \
                mock.patch.object(gui, "_ampr_ftp_connect",
                                  side_effect=lambda *a, **k: verbunden.append(a)):
            self.assertEqual(([], "gibt es nicht"), gui._bibliothek_ps5_scannen())
        self.assertEqual([], verbunden)


class AdresseTests(unittest.TestCase):

    def test_die_gefundene_geht_der_gespeicherten_vor(self) -> None:
        gui = _gui()
        gui._load_setting = lambda k, v=None: {"ps5_ip": "10.0.0.5"}.get(k, v)
        gui._bibliothek_ps5_host = ""
        self.assertEqual("10.0.0.5", gui._bibliothek_ps5_adresse())
        gui._bibliothek_ps5_host = "10.0.0.9"
        self.assertEqual("10.0.0.9", gui._bibliothek_ps5_adresse())

    def test_alle_stellen_der_bibliothek_nehmen_sie(self) -> None:
        """Titelbilder, Holen, Senden, App-Dumper, Dateimanager - dieselbe Adresse.

        Sonst fand die Bibliothek die Konsole, und gleich danach fanden die
        Titelbilder sie nicht, weil die Adresse nicht gespeichert war.
        """
        baum = ast.parse((PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py")
                         .read_text(encoding="utf-8"))
        for knoten in ast.walk(baum):
            if (isinstance(knoten, ast.FunctionDef) and knoten.name.startswith("_bibliothek")
                    and knoten.name not in ("_bibliothek_ps5_adresse",
                                            "_bibliothek_ps5_finden")):
                text = ast.unparse(knoten)
                with self.subTest(methode=knoten.name):
                    self.assertNotIn("_load_setting('ps5_ip'", text)
                    self.assertNotIn("self._ps5_ip()", text)
                    self.assertNotIn("ps5_ip_var", text,
                                     "Tk-Variable im Arbeitsfaden (Faden-Regel).")


def _alle(widget):
    for kind in widget.winfo_children():
        yield kind
        yield from _alle(kind)


def _schleife_bis(bedingung, grenze: float = 10.0) -> bool:
    import time
    ende = time.monotonic() + grenze
    while time.monotonic() < ende:
        _WURZEL.update()
        if bedingung():
            return True
        time.sleep(0.02)
    return False


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class SeiteTests(unittest.TestCase):
    """Die Bibliotheksseite mit Quelle "PS5"."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        _WURZEL.update_idletasks()

    def setUp(self) -> None:
        self.app._ansicht_setzen("konsole")
        self.app._konsole_seite_setzen("bibliothek")
        _WURZEL.update()
        self.zustand = self.app._bibliothek
        # Kein Test holt Titelbilder ueber FTP - der Lader bleibt still.
        flicken = mock.patch.object(self.app, "_bibliothek_ps5_bilder_nachladen",
                                    lambda *_a, **_k: None)
        flicken.start()
        self.addCleanup(flicken.stop)

    def tearDown(self) -> None:
        with mock.patch.object(self.app, "_bibliothek_ps5_scannen", return_value=([], "")):
            self.zustand["quelle"].set("pc")
            self.zustand["quelle_gewechselt"]()
        self.zustand["eintraege"].clear()
        self.app._konsole_seite_setzen("uebersicht")
        self.app._ansicht_setzen("umwandeln")
        _WURZEL.update()

    @staticmethod
    def _installiert(kennung: str = "CUSA00003", titel: str = "PS4 Spiel Drei") -> dict:
        return {"path": APPMETA + "/" + kennung, "kind": "installiert",
                "meta": {"title": titel, "title_id": kennung}, "size": None,
                "ps5": True, "installiert": True,
                "plattform": "PS4" if kennung.startswith("CUSA") else "PS5",
                "ablage": APPMETA, "title_id": kennung}

    def test_suchlauf_zeigt_sicherungen_und_installierte(self) -> None:
        sicherung = {"path": "/data/homebrew/Spiel Eins", "kind": "folder",
                     "meta": {"title": "Spiel Eins", "title_id": "PPSA00001"},
                     "size": None, "ps5": True, "ablage": "/data/homebrew",
                     "title_id": "PPSA00001"}
        gefunden = [sicherung, self._installiert()]
        aufrufe: list = []

        def _scannen(**benannt):
            aufrufe.append(benannt)
            benannt["status"](self.app._t("library.ps5_pruefe", host="10.0.0.5"))
            return list(gefunden), ""

        # Im Test laeuft keine Hauptschleife: after() aus dem Faden verfiele
        # dort mit "main thread is not in main loop". Die eingeplanten
        # Rueckrufe arbeitet deshalb der Test selbst im Hauptfaden ab - so wie
        # es die Hauptschleife im Programm tut.
        warteschlange: list = []

        def _einplanen(_fenster, rueckruf, *argumente):
            warteschlange.append((rueckruf, argumente))
            return True

        erwartet = self.app._t("library.ps5_status_titel", count=2,
                               sicherungen=1, installiert=1)

        def _abgearbeitet() -> bool:
            while warteschlange:
                rueckruf, argumente = warteschlange.pop(0)
                rueckruf(*argumente)
            return any(_text(w) == erwartet for w in _alle(self.app._bibliothek_seite)
                       if isinstance(w, tk.Label))

        with mock.patch.object(self.app, "_bibliothek_ps5_scannen", _scannen), \
                mock.patch.object(self.app, "_spaeter_im_fenster", _einplanen):
            self.zustand["quelle"].set("ps5")
            self.zustand["quelle_gewechselt"]()
            self.assertTrue(_schleife_bis(_abgearbeitet),
                            "Die Statuszeile nennt Sicherungen und installierte Titel.")
        self.assertEqual(2, len(self.zustand["eintraege"]))
        self.assertEqual(1, len(aufrufe))
        self.assertIs(self.app.root, aufrufe[0].get("fenster"),
                      "Rueckfragen der Suche gehen ans Hauptfenster.")
        self.assertTrue(callable(aufrufe[0].get("status")))
        art = STRINGS["library.art_installiert_ps4"]["de"]
        self.assertTrue(any(art in _text(w) for w in _alle(self.app._bibliothek_seite)
                            if isinstance(w, tk.Label)),
                        "Die Kachel nennt die Art des installierten Titels.")

    def test_holen_laedt_ein_installiertes_spiel_nicht(self) -> None:
        from tkinter import messagebox
        eintrag = self._installiert()
        self.zustand["eintraege"].append(eintrag)
        self.zustand["ansicht"]["gewaehlt"] = eintrag["path"]
        holen = self.zustand["knoepfe"]["ps5"][0]
        self.assertEqual(self.app._t("library.download_knopf"), _text(holen))
        with mock.patch.object(self.app, "_bibliothek_herunterladen") as laden, \
                mock.patch.object(messagebox, "showinfo") as hinweis:
            holen.invoke()
        laden.assert_not_called()
        hinweis.assert_called_once()
        self.assertEqual(self.app._t("library.installiert_nicht_holen",
                                     name="PS4 Spiel Drei"), hinweis.call_args[0][1])

    def test_fassung_und_firmware_in_der_detailspalte(self) -> None:
        """PS5-Titel: gegen die Konsole verglichen. PS4-Titel: genannt, nicht verglichen.

        Die Nummern der PS4-Systemsoftware haben mit der Firmware der PS5
        nichts zu tun, und BACKPORT bearbeitet nur PS5-Titel - ein "BACKPORT
        noetig" bei einem PS4-Spiel schickte den Anwender ins Leere.
        """
        ps5 = self._installiert("PPSA00002", "Spiel Zwei")
        ps5["meta"].update(version="01.002.000", required_firmware="13.00.00.00")
        ps4 = self._installiert()
        ps4["meta"].update(version="01.05", required_firmware="13.00.00.00")
        # Eine Sicherung eines PS4-Spiels auf der Konsole: ohne "plattform",
        # die Kennung entscheidet.
        ps4_ordner = {"path": "/data/homebrew/ps4dump", "kind": "folder",
                      "meta": {"title": "PS4 Dump", "title_id": "CUSA00008",
                               "required_firmware": "09.00.00.00"},
                      "size": None, "ps5": True, "ablage": "/data/homebrew",
                      "title_id": "CUSA00008"}
        feld = self.zustand["zeilen"]["firmware"]
        with mock.patch.object(self.app, "_konsole_firmware", return_value="12000020"), \
                mock.patch.object(self.app, "_metadaten_online_erlaubt", return_value=False), \
                mock.patch.object(APP.urllib.request, "urlopen",
                                  side_effect=AssertionError("ins Netz")) as netz:
            self.zustand["details"](ps5)
            self.assertIn("BACKPORT", feld.cget("text"))
            self.assertEqual(self.app._COLORS["fg_warning"], str(feld.cget("fg")))
            self.assertEqual(self.app._t("library.detail_fassung", fassung="01.002.000"),
                             self.zustand["zeilen"]["fassung"].cget("text"))
            for eintrag, fw, fassung in ((ps4, "13.00", "01.05"), (ps4_ordner, "9.00", "")):
                self.zustand["details"](eintrag)
                with self.subTest(eintrag=eintrag["path"]):
                    self.assertEqual(self.app._t("library.fw_ps4", fw=fw), feld.cget("text"))
                    self.assertEqual(self.app._COLORS["fg_secondary"], str(feld.cget("fg")))
                    self.assertEqual(
                        self.app._t("library.detail_fassung", fassung=fassung) if fassung else "",
                        self.zustand["zeilen"]["fassung"].cget("text"))
        netz.assert_not_called()

    def test_eine_sicherung_laesst_sich_weiter_holen(self) -> None:
        """Gegenstueck: Die Sperre trifft nur installierte Titel."""
        eintrag = {"path": "/data/homebrew/Spiel.ffpfsc", "kind": "ffpfsc",
                   "meta": {"title": "Spiel", "title_id": "PPSA00009"}, "size": 10,
                   "ps5": True, "ablage": "/data/homebrew", "title_id": "PPSA00009"}
        self.zustand["eintraege"].append(eintrag)
        self.zustand["ansicht"]["gewaehlt"] = eintrag["path"]
        with mock.patch.object(self.app, "_bibliothek_herunterladen") as laden:
            self.zustand["knoepfe"]["ps5"][0].invoke()
        laden.assert_called_once()


def _text(widget) -> str:
    try:
        return str(widget.cget("text"))
    except Exception:  # noqa: BLE001
        return ""


class TexteTests(unittest.TestCase):

    def test_keine_anzeige_setzt_das_format_selbst_zusammen(self) -> None:
        """Liste, Kachel und Detailspalte nennen die Art ueber denselben Helfer.

        Die Liste nahm bis zum 25.09.2026 ``format.<art>`` ohne Pruefung - fuer
        die installierten Titel stuende dort der Schluesselname.
        """
        baum = ast.parse((PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py")
                         .read_text(encoding="utf-8"))
        # _bibliothek_seite_bauen reicht nur weiter - die Seite baut
        # _render_library_window.
        # Im Syntaxbaum, nicht als Text: ast.unparse schreibt f"..." je nach
        # Inhalt mit einfachen oder doppelten Anfuehrungszeichen - die erste
        # Fassung dieser Pruefung suchte nur eine Schreibweise, und die
        # Gegenprobe ("Liste setzt format.<art> selbst zusammen") blieb gruen.
        for name in ("_render_library_window", "_bibliothek_kacheln_setzen"):
            methode = next(k for k in ast.walk(baum)
                           if isinstance(k, ast.FunctionDef) and k.name == name)
            selbst_gebaut = []
            for knoten in ast.walk(methode):
                if (isinstance(knoten, ast.JoinedStr) and knoten.values
                        and isinstance(knoten.values[0], ast.Constant)
                        and str(knoten.values[0].value).startswith("format.")):
                    selbst_gebaut.append(knoten.lineno)
                elif (isinstance(knoten, ast.Constant) and isinstance(knoten.value, str)
                      and knoten.value.startswith("format.%")):
                    selbst_gebaut.append(knoten.lineno)
            with self.subTest(methode=name):
                self.assertEqual([], selbst_gebaut)
                self.assertIn("_bibliothek_art_text", ast.unparse(methode))

    def test_art_der_installierten(self) -> None:
        gui = _gui()
        self.assertEqual(STRINGS["library.art_installiert_ps4"]["de"],
                         gui._bibliothek_art_text({"kind": "installiert", "plattform": "PS4"}))
        self.assertEqual(STRINGS["library.art_installiert_ps5"]["de"],
                         gui._bibliothek_art_text({"kind": "installiert", "plattform": "PS5"}))
        self.assertEqual(gui._t("format.ffpfsc"), gui._bibliothek_art_text({"kind": "ffpfsc"}))
        self.assertNotIn("format.", gui._bibliothek_art_text({"kind": "installiert"}))

    def test_neue_texte_zweisprachig(self) -> None:
        for schluessel in ("library.ps5_nicht_gefunden", "library.ps5_ohne_ftp",
                           "library.ps5_pruefe", "library.ps5_rundruf",
                           "library.art_installiert_ps4", "library.art_installiert_ps5",
                           "library.installiert_nicht_holen", "library.ps5_status_titel",
                           "library.q_welche_konsole", "library.q_welche_konsole_why",
                           "library.fw_ps4"):
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    self.assertTrue(STRINGS[schluessel].get(sprache))

    def test_das_handbuch_beschreibt_die_quelle_ps5(self) -> None:
        """Der Abschnitt "Bibliothek" - nicht irgendeine Stelle im Handbuch."""
        handbuch = (PROJEKT / "BENUTZERHANDBUCH.html").read_text(encoding="utf-8")
        anfang = handbuch.index("<h4>Bibliothek</h4>")
        # Leerraum zusammengefasst - ein neuer Zeilenumbruch im Fliesstext
        # soll die Pruefung nicht brechen.
        abschnitt = " ".join(handbuch[anfang:handbuch.index("<h4>", anfang + 4)].split())
        for stelle in ("installierten Spiele", "per PKG", "PS4", "Rundruf",
                       "FTP-Profile", "Aufgabe&nbsp;7", "nur Sicherungen",
                       "PS4-Systemsoftware", "APP_VER", "neu gemastertes Paket",
                       "die Konsole selbst zu diesem Titel führt",
                       STRINGS["library.art_installiert_ps4"]["de"].replace(" · ", "&nbsp;·&nbsp;")):
            with self.subTest(stelle=stelle):
                self.assertIn(stelle, abschnitt)


if __name__ == "__main__":
    unittest.main()
