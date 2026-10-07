# -*- coding: utf-8 -*-
"""Tests fuer ``ps5_validator.utils.ps4pkg_updates`` - offizielle Updates eines PS4-Titels.

Das Netz bleibt aussen: ``holen`` und ``oeffnen`` sind Rueckrufe, die hier
Nachbildungen sind. Die XML und das JSON haben die Form, die OrbisPkgTool
(``Psn/UpdateCheck.cs``) auswertet.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import ps4pkg_updates as upd   # noqa: E402

XML = """<?xml version="1.0" encoding="UTF-8"?>
<titlepatch titleid="CUSA00775" status="alive">
  <tag name="CUSA00775_00" mandatory="true">
    <package version="01.09" size="1234567" digest="ABCDEF" manifest_url="http://dl.example/CUSA00775.json"
             content_id="EP0000-CUSA00775_00-TETRISULTIMATE00" system_ver="0x05050000" type="patch"
             remaster="false" patchgo="true"/>
  </tag>
</titlepatch>
"""

STUECKE = [b"A" * 1000, b"B" * 1000, b"C" * 500]


def _json(teile=None) -> str:
    teile = teile or STUECKE
    versatz = 0
    pieces = []
    for i, daten in enumerate(teile):
        pieces.append({"url": "http://dl.example/teil%d.pkg" % i, "fileOffset": versatz,
                       "fileSize": len(daten), "hashValue": hashlib.sha256(daten).hexdigest().upper()})
        versatz += len(daten)
    return json.dumps({"originalFileSize": versatz, "packageDigest": "XYZ",
                       "numberOfSplitFiles": len(teile), "pieces": pieces})


class AdresseTests(unittest.TestCase):

    def test_die_adresse_hat_die_bekannte_form(self) -> None:
        url = upd.update_url("CUSA00775")
        teile = url.split("/")
        self.assertEqual("http:", teile[0])
        self.assertEqual("gs-sec.ww.np.dl.playstation.net", teile[2])
        self.assertEqual(["plo", "np", "CUSA00775"], teile[3:6])
        self.assertRegex(teile[6], r"^[0-9a-f]{64}$")
        self.assertEqual("CUSA00775-ver.xml", teile[7])

    def test_der_hmac_ist_der_ueber_np_titleid(self) -> None:
        erwartet = hmac.new(upd.HMAC_SCHLUESSEL, b"np_CUSA00775", hashlib.sha256).hexdigest()
        self.assertEqual(erwartet, upd.update_url("CUSA00775").split("/")[6])
        self.assertNotEqual(upd.update_url("CUSA00775").split("/")[6], upd.update_url("CUSA00776").split("/")[6])

    def test_der_schluessel_ist_32_byte_lang(self) -> None:
        self.assertEqual(32, len(upd.HMAC_SCHLUESSEL))

    def test_ungueltige_title_ids(self) -> None:
        for schlecht in ("", "cusa00775", "CUSA0077", "CUSA007750", "PPSA01234 ", "../x", None):
            with self.subTest(wert=schlecht):
                self.assertFalse(upd.title_id_gueltig(schlecht))   # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            upd.update_url("nicht")

    def test_ps5_form_ist_formal_gueltig_der_server_kennt_sie_nicht(self) -> None:
        self.assertTrue(upd.title_id_gueltig("PPSA01234"))

    def test_ps5_kennungen_werden_erkannt(self) -> None:
        """07.10.2026: Fuer PS5-Titel gibt es keine Online-Abfrage (16 PPSA-Titel -> alle 404)."""
        for ps5 in ("PPSA01234", "PPSS12345", "PPSA99005"):
            with self.subTest(wert=ps5):
                self.assertTrue(upd.ist_ps5(ps5))
        for kein in ("CUSA03877", "PCSA00001", "", "PPSA0123", "PPSA012345", "ppsa01234", None):
            with self.subTest(wert=kein):
                self.assertFalse(upd.ist_ps5(kein))   # type: ignore[arg-type]


class AuswertenTests(unittest.TestCase):

    def test_die_xml(self) -> None:
        info = upd.xml_auswerten(XML)
        self.assertIsNotNone(info)
        self.assertEqual("CUSA00775", info.title_id)
        self.assertEqual("CUSA00775_00", info.tag)
        self.assertTrue(info.pflicht)
        self.assertEqual("01.09", info.version)
        self.assertEqual(1234567, info.groesse)
        self.assertEqual("http://dl.example/CUSA00775.json", info.verzeichnis_url)
        self.assertEqual("EP0000-CUSA00775_00-TETRISULTIMATE00", info.content_id)
        self.assertEqual("0x05050000", info.system_ver)
        self.assertFalse(info.remaster)
        self.assertTrue(info.patchgo)

    def test_xml_als_bytes(self) -> None:
        self.assertEqual("01.09", upd.xml_auswerten(XML.encode("utf-8")).version)

    def test_keine_update_angabe(self) -> None:
        for text in ("", "kein xml", "<a/>", "<titlepatch titleid='X'/>", "<titlepatch><tag name='a'/></titlepatch>",
                     "<html><body>404</body></html>"):
            with self.subTest(text=text[:30]):
                self.assertIsNone(upd.xml_auswerten(text))

    def test_das_verzeichnis(self) -> None:
        verz = upd.verzeichnis_auswerten(_json())
        self.assertEqual(2500, verz.gesamtgroesse)
        self.assertEqual(3, verz.anzahl)
        self.assertEqual([0, 1000, 2000], [t.versatz for t in verz.teile])
        self.assertEqual([1000, 1000, 500], [t.groesse for t in verz.teile])
        self.assertEqual(hashlib.sha256(STUECKE[0]).hexdigest(), verz.teile[0].hash, "Der Hash wird kleingeschrieben.")

    def test_die_teile_werden_nach_versatz_geordnet(self) -> None:
        roh = json.loads(_json())
        roh["pieces"].reverse()
        verz = upd.verzeichnis_auswerten(json.dumps(roh))
        self.assertEqual([0, 1000, 2000], [t.versatz for t in verz.teile])

    def test_unbrauchbares_verzeichnis(self) -> None:
        self.assertIsNone(upd.verzeichnis_auswerten("kein json"))
        self.assertIsNone(upd.verzeichnis_auswerten("[1, 2]"))
        leer = upd.verzeichnis_auswerten("{}")
        self.assertEqual([], leer.teile)
        ohne_url = upd.verzeichnis_auswerten(json.dumps({"pieces": [{"fileSize": 5}, "x", None]}))
        self.assertEqual([], ohne_url.teile)


class NachsehenTests(unittest.TestCase):

    def test_ein_update_samt_verzeichnis(self) -> None:
        angefragt: list[str] = []

        def holen(adresse: str):
            angefragt.append(adresse)
            return XML if adresse.endswith("-ver.xml") else _json()

        info = upd.nachsehen("CUSA00775", holen)
        self.assertEqual("01.09", info.version)
        self.assertEqual(3, len(info.verzeichnis.teile))
        self.assertTrue(angefragt[0].endswith("CUSA00775-ver.xml"))
        self.assertEqual("http://dl.example/CUSA00775.json", angefragt[1])

    def test_kein_update_bei_404(self) -> None:
        def holen(adresse: str):
            raise upd.UpdateFehler("nicht_gefunden", adresse)

        self.assertIsNone(upd.nachsehen("CUSA00001", holen))

    def test_ein_netzfehler_wird_weitergegeben(self) -> None:
        def holen(adresse: str):
            raise upd.UpdateFehler("netz", "keine Verbindung")

        with self.assertRaises(upd.UpdateFehler) as ctx:
            upd.nachsehen("CUSA00001", holen)
        self.assertEqual("netz", ctx.exception.schluessel)

    def test_ohne_verzeichnis_bleibt_die_fassung_bekannt(self) -> None:
        def holen(adresse: str):
            if adresse.endswith("-ver.xml"):
                return XML
            raise upd.UpdateFehler("netz", "weg")

        info = upd.nachsehen("CUSA00775", holen)
        self.assertEqual("01.09", info.version)
        self.assertIsNone(info.verzeichnis)

    def test_die_xml_ohne_inhalt_heisst_kein_update(self) -> None:
        self.assertIsNone(upd.nachsehen("CUSA00001", lambda a: ""))

    def test_fehlt_die_title_id_in_der_xml_wird_die_angefragte_eingesetzt(self) -> None:
        info = upd.nachsehen("CUSA00999", lambda a: XML.replace('titleid="CUSA00775"', "") if a.endswith(".xml") else "{}")
        self.assertEqual("CUSA00999", info.title_id)

    def test_eine_ungueltige_id_wirft_vor_dem_netz(self) -> None:
        def holen(adresse: str):
            raise AssertionError("nicht ans Netz gehen")

        with self.assertRaises(ValueError):
            upd.nachsehen("kaputt", holen)

    def test_standard_holen_uebersetzt_fehler(self) -> None:
        import urllib.request
        from unittest import mock

        def wirft(code):
            return urllib.error.HTTPError("http://x", code, "msg", {}, None)

        with mock.patch.object(urllib.request, "urlopen", side_effect=wirft(404)):
            with self.assertRaises(upd.UpdateFehler) as ctx:
                upd.standard_holen("http://x")
            self.assertEqual("nicht_gefunden", ctx.exception.schluessel)
        with mock.patch.object(urllib.request, "urlopen", side_effect=wirft(500)):
            with self.assertRaises(upd.UpdateFehler) as ctx:
                upd.standard_holen("http://x")
            self.assertEqual("http", ctx.exception.schluessel)
        with mock.patch.object(urllib.request, "urlopen", side_effect=urllib.error.URLError("weg")):
            with self.assertRaises(upd.UpdateFehler) as ctx:
                upd.standard_holen("http://x")
            self.assertEqual("netz", ctx.exception.schluessel)


class VergleichTests(unittest.TestCase):

    def test_ist_neuer(self) -> None:
        self.assertTrue(upd.ist_neuer("01.10", "01.09"))
        self.assertFalse(upd.ist_neuer("01.09", "01.09"))
        self.assertFalse(upd.ist_neuer("01.08", "01.09"))
        self.assertTrue(upd.ist_neuer("1.05", ""))
        self.assertTrue(upd.ist_neuer("02.00", "1.99"))

    def test_dateiname(self) -> None:
        info = upd.UpdateInfo(title_id="CUSA00775", version="01.09")
        self.assertEqual("CUSA00775-patch-v01.09.pkg", upd.dateiname_vorschlag(info))
        seltsam = upd.UpdateInfo(title_id="CUSA00775", version="1/2:x")
        self.assertNotIn("/", upd.dateiname_vorschlag(seltsam))
        self.assertNotIn(":", upd.dateiname_vorschlag(seltsam))


class _Antwort(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class HerunterladenTests(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.wo = Path(self._tmp.name)
        self.info = upd.xml_auswerten(XML)
        self.info.verzeichnis = upd.verzeichnis_auswerten(_json())
        self.aufrufe: list[str] = []

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _oeffnen(self, daten: "list[bytes] | None" = None, stoeren: "dict | None" = None):
        teile = daten or STUECKE

        def oeffnen(adresse: str):
            self.aufrufe.append(adresse)
            nummer = int(adresse.rsplit("teil", 1)[1].split(".")[0])
            if stoeren and nummer in stoeren:
                raise stoeren[nummer]
            return _Antwort(teile[nummer])

        return oeffnen

    def test_die_teile_ergeben_die_ganze_datei(self) -> None:
        meldungen: list[tuple[int, int]] = []
        pfad = upd.herunterladen(self.info, str(self.wo), oeffnen=self._oeffnen(),
                                 fortschritt=lambda a, g: meldungen.append((a, g)))
        self.assertEqual(b"".join(STUECKE), Path(pfad).read_bytes())
        self.assertEqual("CUSA00775-patch-v01.09.pkg", os.path.basename(pfad))
        self.assertEqual((2500, 2500), meldungen[-1])
        self.assertFalse(os.path.exists(pfad + ".teil"))
        self.assertFalse(os.path.exists(pfad + ".teil.fertig"))

    def test_ein_beschaedigtes_teil_wird_erkannt(self) -> None:
        kaputt = [STUECKE[0], b"X" * 1000, STUECKE[2]]
        with self.assertRaises(upd.UpdateFehler) as ctx:
            upd.herunterladen(self.info, str(self.wo), oeffnen=self._oeffnen(kaputt))
        self.assertEqual("hash", ctx.exception.schluessel)
        self.assertIn("Teil 2", ctx.exception.text)
        self.assertFalse((self.wo / "CUSA00775-patch-v01.09.pkg").exists(), "Eine kaputte Datei bekommt keinen Namen.")

    def test_ein_netzfehler_haelt_an_und_laesst_das_fertige_liegen(self) -> None:
        with self.assertRaises(upd.UpdateFehler) as ctx:
            upd.herunterladen(self.info, str(self.wo),
                              oeffnen=self._oeffnen(stoeren={1: urllib.error.URLError("weg")}))
        self.assertEqual("netz", ctx.exception.schluessel)
        teil = self.wo / "CUSA00775-patch-v01.09.pkg.teil"
        self.assertTrue(teil.is_file())
        self.assertEqual("1", (self.wo / "CUSA00775-patch-v01.09.pkg.teil.fertig").read_text())

    def test_fortsetzen_ueberspringt_fertige_teile(self) -> None:
        with self.assertRaises(upd.UpdateFehler):
            upd.herunterladen(self.info, str(self.wo),
                              oeffnen=self._oeffnen(stoeren={1: urllib.error.URLError("weg")}))
        self.aufrufe.clear()
        pfad = upd.herunterladen(self.info, str(self.wo), oeffnen=self._oeffnen())
        self.assertEqual(b"".join(STUECKE), Path(pfad).read_bytes())
        self.assertEqual(["http://dl.example/teil1.pkg", "http://dl.example/teil2.pkg"], self.aufrufe,
                         "Das erste Teil war fertig und darf nicht noch einmal geladen werden.")

    def test_eine_marke_ohne_teildatei_beginnt_von_vorn(self) -> None:
        (self.wo / "CUSA00775-patch-v01.09.pkg.teil.fertig").write_text("2")
        pfad = upd.herunterladen(self.info, str(self.wo), oeffnen=self._oeffnen())
        self.assertEqual(b"".join(STUECKE), Path(pfad).read_bytes())
        self.assertEqual(3, len(self.aufrufe))

    def test_abbruch(self) -> None:
        with self.assertRaises(upd.UpdateFehler) as ctx:
            upd.herunterladen(self.info, str(self.wo), oeffnen=self._oeffnen(), abbruch=lambda: True)
        self.assertEqual("abgebrochen", ctx.exception.schluessel)

    def test_http_fehler(self) -> None:
        fehler = urllib.error.HTTPError("http://dl.example/teil0.pkg", 403, "Forbidden", {}, None)
        with self.assertRaises(upd.UpdateFehler) as ctx:
            upd.herunterladen(self.info, str(self.wo), oeffnen=self._oeffnen(stoeren={0: fehler}))
        self.assertEqual("http", ctx.exception.schluessel)

    def test_ohne_teile(self) -> None:
        self.info.verzeichnis = None
        with self.assertRaises(upd.UpdateFehler) as ctx:
            upd.herunterladen(self.info, str(self.wo), oeffnen=self._oeffnen())
        self.assertEqual("ohne_teile", ctx.exception.schluessel)

    def test_falsche_groesse_eines_teils(self) -> None:
        self.info.verzeichnis.teile[2].hash = ""   # ohne Hash zaehlt nur die Groesse
        self.info.verzeichnis.teile[2].groesse = 999
        with self.assertRaises(upd.UpdateFehler) as ctx:
            upd.herunterladen(self.info, str(self.wo), oeffnen=self._oeffnen())
        self.assertEqual("hash", ctx.exception.schluessel)


class FirmwareTextTests(unittest.TestCase):
    """Sony nennt ``system_ver`` als Zahl - angezeigt wird die Firmware (07.10.2026: stand roh da)."""

    def test_dezimal_und_hex_geben_dieselbe_fassung(self) -> None:
        self.assertEqual("4.73", upd.system_ver_text("74645504"))
        self.assertEqual("4.73", upd.system_ver_text("0x04730000"))
        self.assertEqual("5.05", upd.system_ver_text(0x05050000))
        self.assertEqual("9.00", upd.system_ver_text("150994944"))

    def test_unlesbares_bleibt_stehen(self) -> None:
        self.assertEqual("", upd.system_ver_text(""))
        self.assertEqual("abc", upd.system_ver_text("abc"))
        self.assertEqual("0", upd.system_ver_text("0"))

    def test_die_update_info_liefert_den_text(self) -> None:
        self.assertEqual("4.73", upd.UpdateInfo(system_ver="74645504").firmware_text)


class PruefsummeTests(unittest.TestCase):
    """Sonys ``hashValue`` ist je Teil eine SHA-1 (40 Stellen) - SHA-256 galt bis 07.10.2026 faelschlich."""

    def test_die_laenge_bestimmt_das_verfahren(self) -> None:
        self.assertEqual("sha1", upd._pruefsumme_fuer("a" * 40).name)
        self.assertEqual("sha256", upd._pruefsumme_fuer("b" * 64).name)
        self.assertIsNone(upd._pruefsumme_fuer("xyz"))
        self.assertIsNone(upd._pruefsumme_fuer(""))

    def test_ein_teil_mit_sha1_wird_angenommen_ein_falsches_nicht(self) -> None:
        daten = b"Testteil" * 1000

        def mit_hash(wert: str):
            teil = upd.UpdateTeil(url="http://x/a.pkg", versatz=0, groesse=len(daten), hash=wert)
            info = upd.UpdateInfo(title_id="CUSA00001", version="01.00",
                                  verzeichnis=upd.UpdateVerzeichnis(gesamtgroesse=len(daten), teile=[teil]))
            with tempfile.TemporaryDirectory() as ordner:
                return upd.herunterladen(info, ordner, oeffnen=lambda adresse: io.BytesIO(daten)) and True

        self.assertTrue(mit_hash(hashlib.sha1(daten).hexdigest()))
        with self.assertRaises(upd.UpdateFehler) as ctx:
            mit_hash("0" * 40)
        self.assertEqual("hash", ctx.exception.schluessel)


if __name__ == "__main__":
    unittest.main()
