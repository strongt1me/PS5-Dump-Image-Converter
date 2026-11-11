# -*- coding: utf-8 -*-
"""Behobene Befunde der Gesamtpruefung vom 11.11.2026 (Reihenfolge wie in der Befundliste).

Hier stehen die Pruefungen, die in keiner der bestehenden Testdateien zu Hause sind. Zu jedem Befund gehoert eine
Gegenprobe: ohne die Korrektur schlaegt der Test an.

* D4  Asset-Pack-Uebernahme: Manifest zuletzt
* D9  PS4-Update-Download: HTTP 416 und gescheitertes Umbenennen
* D2/D3 Rueckfragetexte nennen das Loeschen in allen fuenf Sprachen
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import ampr_assetpakete as ap       # noqa: E402
from ps5_validator.utils import i18n                          # noqa: E402
from ps5_validator.utils import ps5_updates as pu             # noqa: E402

SPRACHEN = ("de", "en", "es", "it", "fr")


# ------------------------------------------------------------------------------------------------------- D4
class UebernahmeReihenfolgeTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.aus = Path(tmp.name) / "aus"
        self.app0 = Path(tmp.name) / "app0"
        self.aus.mkdir()
        self.app0.mkdir()
        (self.aus / ap.MANIFEST_NAME).write_bytes(b"NEU")
        (self.aus / ap.LAUFZEIT_NAME).write_bytes(b"R")
        (self.aus / ap.PRUEFSUMMEN_NAME).write_bytes(b"C")
        for name in ("band_0.pak", "band_1.pak"):
            (self.aus / name).write_bytes(name.encode() * 10)
        # ein frueherer, vollstaendiger Satz
        (self.app0 / ap.MANIFEST_NAME).write_bytes(b"ALT")
        for name in ("band_0.pak", "band_1.pak"):
            (self.app0 / name).write_bytes(b"alt")

    def _uebernehmen(self) -> int:
        return ap.bestand_uebernehmen(str(self.aus), str(self.app0), baender=["band_0.pak", "band_1.pak"])

    def test_das_manifest_kommt_als_letztes_an_seinen_platz(self) -> None:
        reihenfolge: list[str] = []
        echt = os.replace

        def merke(quelle, ziel):
            reihenfolge.append(os.path.basename(ziel))
            return echt(quelle, ziel)

        with mock.patch.object(ap.os, "replace", merke):
            self.assertEqual(5, self._uebernehmen())
        self.assertEqual(ap.MANIFEST_NAME, reihenfolge[-1])
        self.assertEqual(5, len(reihenfolge))
        self.assertEqual(b"NEU", (self.app0 / ap.MANIFEST_NAME).read_bytes())

    def _ersetzen_scheitert_bei(self, nummer: int):
        echt = os.replace
        zaehler = [0]

        def fehler(quelle, ziel):
            zaehler[0] += 1
            if zaehler[0] == nummer:
                raise PermissionError(32, "Die Datei wird von einem anderen Prozess verwendet")
            return echt(quelle, ziel)

        return mock.patch.object(ap.os, "replace", fehler)

    def test_scheitert_das_erste_ersetzen_bleibt_der_alte_satz_ganz(self) -> None:
        with self._ersetzen_scheitert_bei(1):
            with self.assertRaises(ap.PackFehler):
                self._uebernehmen()
        self.assertEqual(b"ALT", (self.app0 / ap.MANIFEST_NAME).read_bytes())
        self.assertEqual(b"alt", (self.app0 / "band_0.pak").read_bytes())
        self.assertEqual(b"alt", (self.app0 / "band_1.pak").read_bytes())
        self.assertEqual([], [n for n in os.listdir(self.app0) if n.endswith(".uebernahme")])

    def test_scheitert_ein_spaeteres_ersetzen_gilt_kein_mischsatz_als_vollstaendig(self) -> None:
        """Frueher ging das Manifest zuerst: neues Manifest neben alten Baendern. Jetzt gibt es ohne vollstaendigen
        Satz auch kein Manifest."""
        with self._ersetzen_scheitert_bei(3):
            with self.assertRaises(ap.PackFehler):
                self._uebernehmen()
        self.assertFalse((self.app0 / ap.MANIFEST_NAME).exists(), "kein Manifest neben gemischten Baendern")
        self.assertEqual([], [n for n in os.listdir(self.app0) if n.endswith(".uebernahme")])


# ------------------------------------------------------------------------------------------------------- D9
class _Antwort:
    status = 200

    def __init__(self, daten: bytes, status: int = 200):
        self.status = status
        self.headers = {"Content-Length": str(len(daten))}
        self._daten = daten

    def read(self, n=-1):
        stueck, self._daten = self._daten[:n if n and n > 0 else None], self._daten[n if n and n > 0 else len(self._daten):]
        return stueck

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def _oeffner_fuer(daten: bytes, content_range: str | None):
    """Ein Server, der auf jede Bereichsanfrage mit 416 antwortet (``content_range`` als Kopfzeile, wenn gesetzt)."""
    anfragen: list[str] = []

    class _Oeffner:
        def open(self, anfrage, timeout=None):
            bereich = anfrage.get_header("Range") or ""
            anfragen.append(bereich)
            if bereich:
                kopf = {"Content-Range": content_range} if content_range else {}
                raise urllib.error.HTTPError(anfrage.full_url, 416, "Range Not Satisfiable", kopf, None)
            return _Antwort(daten)

    return _Oeffner, anfragen


class Download416Tests(unittest.TestCase):
    def setUp(self) -> None:
        hosts = mock.patch.object(pu, "ERLAUBTE_HOSTS", ("127.0.0.1",))
        hosts.start()
        self.addCleanup(hosts.stop)
        schlaf = mock.patch.object(pu.netz_abbruch, "schlafen", return_value=False)
        schlaf.start()
        self.addCleanup(schlaf.stop)
        tmp = tempfile.TemporaryDirectory(prefix="gp_416_")
        self.addCleanup(tmp.cleanup)
        self.ziel = os.path.join(tmp.name, "Update", "Spiel.pkg")
        self.daten = os.urandom(1000)

    def _teil_anlegen(self, daten: bytes) -> str:
        teil = pu.teildatei(self.ziel)
        os.makedirs(os.path.dirname(teil), exist_ok=True)
        Path(teil).write_bytes(daten)
        return teil

    def test_vollstaendige_teildatei_wird_abgeschlossen_statt_http_416(self) -> None:
        """Das Umbenennen war beim letzten Mal gescheitert: Die ``.teil`` ist vollstaendig, jeder neue Start bekam
        auf ``Range: bytes=<Groesse>-`` vom Server 416 und dauerhaft "HTTP 416"."""
        teil = self._teil_anlegen(self.daten)
        oeffner, anfragen = _oeffner_fuer(self.daten, "bytes */1000")
        with mock.patch.object(pu, "_oeffner", oeffner):
            self.assertEqual(self.ziel, pu.datei_laden("http://127.0.0.1/x.pkg", self.ziel, versuche=2))
        self.assertEqual(["bytes=1000-"], anfragen)
        self.assertEqual(self.daten, Path(self.ziel).read_bytes())
        self.assertFalse(os.path.exists(teil))

    def test_zu_grosse_teildatei_wird_verworfen_und_neu_geladen(self) -> None:
        teil = self._teil_anlegen(self.daten + b"ueberhang")
        oeffner, anfragen = _oeffner_fuer(self.daten, "bytes */1000")
        with mock.patch.object(pu, "_oeffner", oeffner):
            pu.datei_laden("http://127.0.0.1/x.pkg", self.ziel, versuche=2)
        self.assertEqual(["bytes=1009-", ""], anfragen)
        self.assertEqual(self.daten, Path(self.ziel).read_bytes())
        self.assertFalse(os.path.exists(teil))

    def test_416_ohne_inhaltsbereich_laedt_ebenfalls_neu(self) -> None:
        self._teil_anlegen(self.daten[:400])
        oeffner, anfragen = _oeffner_fuer(self.daten, None)
        with mock.patch.object(pu, "_oeffner", oeffner):
            pu.datei_laden("http://127.0.0.1/x.pkg", self.ziel, versuche=2)
        self.assertEqual(["bytes=400-", ""], anfragen)
        self.assertEqual(self.daten, Path(self.ziel).read_bytes())

    def test_ein_anderer_httpfehler_bleibt_ein_httpfehler(self) -> None:
        class _Oeffner:
            def open(self, anfrage, timeout=None):
                raise urllib.error.HTTPError(anfrage.full_url, 404, "Not Found", {}, None)

        with mock.patch.object(pu, "_oeffner", _Oeffner):
            with self.assertRaises(pu.UpdateFehler) as ctx:
                pu.datei_laden("http://127.0.0.1/x.pkg", self.ziel, versuche=1)
        self.assertEqual("ps5upd.http|404", str(ctx.exception))

    def test_umbenennen_scheitert_dann_bleibt_die_vollstaendige_teildatei_und_der_naechste_start_schliesst_ab(self) -> None:
        oeffner, _anfragen = _oeffner_fuer(self.daten, "bytes */1000")
        echt = os.replace

        def gesperrt(quelle, ziel):
            raise PermissionError(32, "Die Datei wird von einem anderen Prozess verwendet")

        with mock.patch.object(pu, "_oeffner", oeffner), mock.patch.object(pu.os, "replace", gesperrt):
            with self.assertRaises(pu.UpdateFehler) as ctx:
                pu.datei_laden("http://127.0.0.1/x.pkg", self.ziel, versuche=2)
        self.assertTrue(str(ctx.exception).startswith("ps5upd.speichern|"), str(ctx.exception))
        teil = pu.teildatei(self.ziel)
        self.assertEqual(self.daten, Path(teil).read_bytes(), "die vollstaendige Teildatei bleibt liegen")
        self.assertFalse(os.path.exists(self.ziel))
        # zweiter Start: Der Server antwortet auf den Bereich mit 416 - der Download gilt als fertig.
        with mock.patch.object(pu, "_oeffner", oeffner), mock.patch.object(pu.os, "replace", echt):
            pu.datei_laden("http://127.0.0.1/x.pkg", self.ziel, versuche=2)
        self.assertEqual(self.daten, Path(self.ziel).read_bytes())

    def test_umbenennen_gelingt_nach_kurzem_festhalten(self) -> None:
        oeffner, _anfragen = _oeffner_fuer(self.daten, "bytes */1000")
        echt = os.replace
        versuche = [0]

        def zweiter_versuch(quelle, ziel):
            versuche[0] += 1
            if versuche[0] < 3:
                raise PermissionError(32, "Virenscanner")
            return echt(quelle, ziel)

        with mock.patch.object(pu, "_oeffner", oeffner), mock.patch.object(pu.os, "replace", zweiter_versuch):
            pu.datei_laden("http://127.0.0.1/x.pkg", self.ziel, versuche=2)
        self.assertEqual(3, versuche[0])
        self.assertEqual(self.daten, Path(self.ziel).read_bytes())

    def test_der_fehlerschluessel_ist_in_allen_sprachen_da(self) -> None:
        for sprache in SPRACHEN:
            text = i18n.STRINGS["ps5upd.speichern"][sprache]
            self.assertIn("{detail}", text, sprache)


# ------------------------------------------------------------------------------------------------- D2 / D3
class RueckfrageTexteTests(unittest.TestCase):
    """Wer "Ja" sagt, muss wissen, dass vorhandene Ergebnisse vor dem Bau geloescht werden."""

    LOESCHEN = {"de": "gelöscht", "en": "deleted", "es": "elimina", "it": "eliminat", "fr": "supprim"}

    def test_einzellauf_nennt_das_loeschen_und_die_folge_in_jeder_sprache(self) -> None:
        for sprache in SPRACHEN:
            text = i18n.STRINGS["dialog.msg.target_file_exists_overwrite_confirm"][sprache]
            self.assertIn("{path}", text, sprache)
            self.assertIn(self.LOESCHEN[sprache], text, sprache)

    def test_sammelkonvertierung_nennt_alle_ergebnisse_und_dump_ordner(self) -> None:
        for sprache in SPRACHEN:
            text = i18n.STRINGS["batch.ueberschreiben_frage"][sprache]
            self.assertIn("{pfad}", text, sprache)
            self.assertIn(self.LOESCHEN[sprache], text, sprache)


# --------------------------------------------------------------------------------------- S1 / S2 / D6 (Hauptmodul)
import PS5ImageConverter_Pro_FINAL_revised as APP             # noqa: E402

GUI = APP.PS5ConverterGUI


class _FalschesPopen:
    """Ersatz fuer ``subprocess.Popen``: legt beim Start die Dateien an, die UFS2Tool angeblich herausschreibt."""

    def __init__(self, dateien: dict[str, int], rueckgabe: int = 0):
        self.dateien = dateien
        self.rueckgabe = rueckgabe

    def __call__(self, args, **_kw):
        ziel = args[3]
        for rel, groesse in self.dateien.items():
            voll = os.path.join(ziel, *rel.replace("\\", "/").split("/"))
            os.makedirs(os.path.dirname(voll), exist_ok=True)
            with open(voll, "wb") as fh:
                fh.write(b"x" * groesse)
        proc = mock.MagicMock()
        proc.stdout.readline.return_value = ""
        proc.returncode = self.rueckgabe
        return proc


def _gui_fuer_entpacken() -> "APP.PS5ConverterGUI":
    gui = GUI.__new__(GUI)
    gui.protokoll = []
    gui._t = lambda schluessel, **_w: schluessel
    gui._append_to_log = gui.protokoll.append
    gui._set_status = lambda *_a, **_k: None
    gui._extract_ufs2tool = lambda: "UFS2Tool.exe"
    gui.is_running = True
    gui.task_progress = 0.0
    gui._fmt_bytes = lambda n: str(n)
    gui._teilschritt_melden = lambda *_a, **_k: None
    gui._ENTPACK_TAKT_S = 60.0
    return gui


class ToterPowerShellCodeTests(unittest.TestCase):
    """SEC7: Der PowerShell-``Copy-Item``-Block mit Dateinamen aus dem Abbild war nie erreichbar und ist entfernt."""

    def test_kein_copy_item_mit_abbildnamen_mehr(self) -> None:
        quelle = Path(APP.__file__).read_text(encoding="utf-8", errors="replace")
        self.assertNotIn("Copy-Item -LiteralPath", quelle)
        anfang = quelle.index("def _extract_ffpkg_to_folder_via_ufs2tool(")
        self.assertNotIn("powershell.exe", quelle[anfang:anfang + 30000])


class UnterbefehlSollAbgleichTests(unittest.TestCase):
    """S2: ``UFS2Tool extract`` mit Rueckgabewert 0 und einer Datei galt als vollstaendig."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ziel = os.path.join(tmp.name, "dump")

    def _lauf(self, geschrieben: dict[str, int], soll: dict[str, int] | None) -> tuple[bool, list[str]]:
        gui = _gui_fuer_entpacken()
        with mock.patch.object(APP.subprocess, "Popen", _FalschesPopen(geschrieben)):
            ok = gui._ffpkg_ueber_unterbefehl_entpacken("x.ffpkg", self.ziel, soll=soll)
        return ok, gui.protokoll

    def test_fehlende_datei_wird_trotz_rueckgabewert_null_erkannt(self) -> None:
        ok, protokoll = self._lauf({"eboot.bin": 10}, {"eboot.bin": 10, "data/a.bin": 5})
        self.assertFalse(ok)
        self.assertTrue(any("ufs2_extract.incomplete_failed" in z for z in protokoll), protokoll)

    def test_zu_kleine_datei_wird_erkannt(self) -> None:
        ok, _protokoll = self._lauf({"eboot.bin": 10, "data/a.bin": 3}, {"eboot.bin": 10, "data/a.bin": 5})
        self.assertFalse(ok)

    def test_vollstaendiges_ergebnis_besteht(self) -> None:
        ok, protokoll = self._lauf({"eboot.bin": 10, "data\\a.bin": 5}, {"eboot.bin": 10, "data\\a.bin": 5})
        self.assertTrue(ok, protokoll)

    def test_ohne_sollliste_bleibt_es_beim_alten_verhalten(self) -> None:
        ok, _protokoll = self._lauf({"eboot.bin": 10}, None)
        self.assertTrue(ok)

    def test_der_grossdateiweg_gibt_die_sollliste_weiter(self) -> None:
        quelle = Path(APP.__file__).read_text(encoding="utf-8", errors="replace")
        self.assertIn("soll=dict(quell_dateien)", quelle)


class SollListeLesefehlerTests(unittest.TestCase):
    """S1: Ein beim Auflisten nicht lesbares Verzeichnis fehlte still in der Soll-Liste und damit im Abgleich."""

    @classmethod
    def setUpClass(cls) -> None:
        quelle = Path(APP.__file__).read_text(encoding="utf-8", errors="replace")
        anfang = quelle.index("def _extract_ffpkg_to_folder_via_ufs2tool(")
        cls.rumpf = quelle[anfang:anfang + 30000]

    def test_walk_meldet_fehler_und_listet_neu(self) -> None:
        self.assertIn("os.walk(drive + \"\\\\\", onerror=_liste_fehler)", self.rumpf)
        self.assertIn("for _liste_versuch in range(3):", self.rumpf)
        self.assertIn("ufs2_extract.source_unreadable", self.rumpf)

    def test_kein_stilles_verschlucken_mehr_beim_auflisten(self) -> None:
        listing = self.rumpf[self.rumpf.index("liste_fehler: list[str] = []"):self.rumpf.index("source_listed")]
        self.assertNotIn("except Exception:", listing)
        self.assertNotIn("pass", listing)

    def test_text_in_allen_sprachen(self) -> None:
        for sprache in SPRACHEN:
            text = i18n.STRINGS["ufs2_extract.source_unreadable"][sprache]
            self.assertIn("{count}", text, sprache)
            self.assertIn("{names}", text, sprache)


class UnvollstaendigerOrdnerTests(unittest.TestCase):
    """D6: Scheitert das Verschieben ins Ziel, steht dort ein unvollstaendiger Dump - er bekommt ein Kennzeichen."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.w = Path(tmp.name)

    def test_ordner_wird_umbenannt(self) -> None:
        ziel = self.w / "Spiel"
        ziel.mkdir()
        (ziel / "eboot.bin").write_bytes(b"x")
        neu = GUI._unvollstaendigen_ordner_kennzeichnen(str(ziel))
        self.assertEqual(str(self.w / "Spiel.unvollstaendig"), neu)
        self.assertFalse(ziel.exists())
        self.assertTrue((self.w / "Spiel.unvollstaendig" / "eboot.bin").is_file())

    def test_ein_frueheres_kennzeichen_wird_nicht_ueberschrieben(self) -> None:
        (self.w / "Spiel.unvollstaendig").mkdir()
        (self.w / "Spiel.unvollstaendig" / "alt.txt").write_bytes(b"alt")
        ziel = self.w / "Spiel"
        ziel.mkdir()
        neu = GUI._unvollstaendigen_ordner_kennzeichnen(str(ziel))
        self.assertEqual(str(self.w / "Spiel.unvollstaendig2"), neu)
        self.assertTrue((self.w / "Spiel.unvollstaendig" / "alt.txt").is_file())

    def test_fehlender_ordner_ist_kein_fehler(self) -> None:
        self.assertEqual("", GUI._unvollstaendigen_ordner_kennzeichnen(str(self.w / "gibt_es_nicht")))

    def test_aufgabe_4_ruft_es_nach_dem_fehlschlag_des_verschiebens(self) -> None:
        quelle = Path(APP.__file__).read_text(encoding="utf-8", errors="replace")
        stelle = quelle.index("self._unvollstaendigen_ordner_kennzeichnen(final_dst)")
        davor = quelle[max(0, stelle - 900):stelle]
        self.assertIn("unpack.move_failed", davor)

    def test_text_in_allen_sprachen(self) -> None:
        for sprache in SPRACHEN:
            self.assertIn("{name}", i18n.STRINGS["unpack.move_unvollstaendig"][sprache], sprache)


# ------------------------------------------------------------------------------------------------------ SEC2
from ps5_validator.utils import ps4pkg_updates as upd4        # noqa: E402


class Ps4UpdateAdressenTests(unittest.TestCase):
    """SEC2: Die Update-Antwort nennt weitere Adressen und eine Title-ID; beides darf nichts ausserhalb von Sony oder
    des Zielordners erreichen."""

    def test_nur_sonys_domaene_ist_erlaubt(self) -> None:
        for gut in ("http://gs-sec.ww.np.dl.playstation.net/plo/np/CUSA00001/ab/CUSA00001-ver.xml",
                    "https://gs2.ww.prod.dl.playstation.net/x.json", "http://PLAYSTATION.NET/a"):
            self.assertTrue(upd4.url_erlaubt(gut), gut)
        for schlecht in ("file:///C:/Windows/win.ini", "file://localhost/etc/passwd", "http://evil.example/x",
                         "http://playstation.net.evil.example/x", "http://notplaystation.net/x",
                         "ftp://gs2.ww.prod.dl.playstation.net/x", "", "gs2.ww.prod.dl.playstation.net/x",
                         "http://user@evil.example/#.playstation.net", "http://evil.example\\@gs2.playstation.net/"):
            self.assertFalse(upd4.url_erlaubt(schlecht), schlecht)

    def test_standard_holen_oeffnet_keine_fremde_adresse(self) -> None:
        with mock.patch.object(upd4.urllib.request, "urlopen") as urlopen:
            for adresse in ("file:///C:/Windows/win.ini", "http://evil.example/x.json"):
                with self.assertRaises(upd4.UpdateFehler) as ctx:
                    upd4.standard_holen(adresse)
                self.assertEqual("host_fremd", ctx.exception.schluessel)
            urlopen.assert_not_called()

    def test_nach_einer_umleitung_wird_nichts_von_einem_fremden_host_gelesen(self) -> None:
        antwort = mock.MagicMock()
        antwort.__enter__.return_value = antwort
        antwort.url = "http://evil.example/geheim"
        with mock.patch.object(upd4.urllib.request, "urlopen", return_value=antwort):
            with self.assertRaises(upd4.UpdateFehler) as ctx:
                upd4.standard_holen("http://gs2.ww.prod.dl.playstation.net/x.json")
        self.assertEqual("host_fremd", ctx.exception.schluessel)
        antwort.read.assert_not_called()

    def test_fremde_verzeichnisadresse_wird_nicht_geholt(self) -> None:
        xml = ('<titlepatch titleid="CUSA00775"><tag name="a"><package version="01.09" size="5" '
               'manifest_url="http://evil.example/m.json"/></tag></titlepatch>')
        angefragt: list[str] = []

        def holen(adresse: str):
            angefragt.append(adresse)
            if adresse.endswith("-ver.xml"):
                return xml
            return upd4.standard_holen(adresse)             # wie im Programm: die echte Funktion prueft den Host

        info = upd4.nachsehen("CUSA00775", holen)
        self.assertIsNotNone(info)
        self.assertIsNone(info.verzeichnis, "die fremde Adresse darf kein Verzeichnis liefern")

    def test_title_id_aus_der_antwort_kommt_nur_in_der_erwarteten_form_in_den_dateinamen(self) -> None:
        for boese in ("..\\..\\boese", "../x", "C:\\x", "CUSA00775\\..\\..\\y", "", "cusa00775"):
            info = upd4.xml_auswerten('<titlepatch titleid="%s"><tag name="a"><package version="1"/></tag></titlepatch>'
                                      % boese.replace("\\", "\\\\").replace('"', "&quot;"))
            self.assertEqual("", info.title_id, boese)
        info = upd4.xml_auswerten('<titlepatch titleid="CUSA00775"><tag name="a"><package version="1"/></tag></titlepatch>')
        self.assertEqual("CUSA00775", info.title_id)

    def test_nachsehen_nimmt_bei_fremder_title_id_die_angefragte(self) -> None:
        xml = '<titlepatch titleid="..\\x"><tag name="a"><package version="01.09"/></tag></titlepatch>'
        info = upd4.nachsehen("CUSA00775", lambda a: xml)
        self.assertEqual("CUSA00775", info.title_id)
        self.assertEqual("CUSA00775-patch-v01.09.pkg", upd4.dateiname_vorschlag(info))

    def test_dateiname_enthaelt_nie_ein_trennzeichen(self) -> None:
        for titel in ("..\\..\\x", "a/b", "C:x", "", "CUSA00775"):
            for version in ("1/2", "..", "../..", "a\\b", "", "..\\.."):
                name = upd4.dateiname_vorschlag(upd4.UpdateInfo(title_id=titel, version=version))
                self.assertEqual(os.path.basename(name), name, (titel, version))
                self.assertNotIn("\\", name)
                self.assertNotIn(":", name)
                self.assertFalse(name.startswith("."), name)

    def test_herunterladen_oeffnet_keine_fremde_teiladresse(self) -> None:
        teil = upd4.UpdateTeil(url="file:///C:/Windows/win.ini", versatz=0, groesse=10, hash="")
        info = upd4.UpdateInfo(title_id="CUSA00001", version="01.00",
                               verzeichnis=upd4.UpdateVerzeichnis(gesamtgroesse=10, teile=[teil]))
        with tempfile.TemporaryDirectory() as ordner:
            with mock.patch.object(upd4.urllib.request, "urlopen") as urlopen:
                with self.assertRaises(upd4.UpdateFehler) as ctx:
                    upd4.herunterladen(info, ordner)
            urlopen.assert_not_called()
        self.assertEqual("host_fremd", ctx.exception.schluessel)

    def test_text_in_allen_sprachen(self) -> None:
        for sprache in SPRACHEN:
            self.assertIn("{grund}", i18n.STRINGS["ps4ota.fehler_update_host_fremd"][sprache], sprache)


# ----------------------------------------------------------------------------------------------- SEC3 / SEC4
from ps5_validator.utils import arbeitsordner                  # noqa: E402


class InstallerOrdnerTests(unittest.TestCase):
    """SEC3: Ein Installer, der gleich mit Administratorrechten startet, liegt nicht im offenen Arbeitsordner."""

    def test_der_ordner_ist_neu_privat_und_nicht_der_arbeitsordner(self) -> None:
        a, b = GUI._installer_ordner(), GUI._installer_ordner()
        try:
            self.assertNotEqual(a, b)
            for pfad in (a, b):
                self.assertTrue(os.path.isdir(pfad))
                self.assertTrue(os.path.basename(pfad).startswith("ps5conv_setup_"))
                standard = arbeitsordner.standard_ordner()
                if standard:
                    self.assertNotEqual(os.path.normcase(os.path.dirname(pfad)), os.path.normcase(standard))
                self.assertEqual(os.path.normcase(tempfile.gettempdir()), os.path.normcase(os.path.dirname(pfad)))
        finally:
            for pfad in (a, b):
                os.rmdir(pfad)

    def test_keiner_der_drei_installer_liegt_mehr_im_arbeitsordner(self) -> None:
        quelle = Path(APP.__file__).read_text(encoding="utf-8", errors="replace")
        for name in ("filezilla_setup.exe", "osfmount_setup.exe", "DokanSetup.exe"):
            self.assertNotIn('self._get_runtime_temp_dir(), "%s"' % name, quelle, name)
            self.assertIn('os.path.join(installer_ordner, "%s")' % name, quelle, name)
        self.assertEqual(3, quelle.count("_rmtree_force(installer_ordner)"), "jeder Installer raeumt seinen Ordner auf")


class FilezillaFundTests(unittest.TestCase):
    """SEC4: Die Ausweichsuche startet kein fremdes ``filezilla.exe`` aus einem entpackten Archiv, und ein Fund aus
    dem blossen Laufwerksdurchlauf wird erst nach Rueckfrage gestartet."""

    def _gui(self) -> "APP.PS5ConverterGUI":
        gui = GUI.__new__(GUI)
        gui._t = lambda schluessel, **w: schluessel + str(w)
        gui._set_status = lambda *_a, **_k: None
        return gui

    def test_ohne_fenster_wird_nicht_gestartet(self) -> None:
        gui = self._gui()
        gui.root = None
        gui._ask_yesno_threadsafe = mock.Mock(side_effect=AssertionError("darf nicht fragen"))
        self.assertFalse(gui._filezilla_fund_bestaetigen("D:\\x\\filezilla.exe"))
        gui._ask_yesno_threadsafe.assert_not_called()

    def test_nein_ist_vorbelegt_und_zaehlt(self) -> None:
        gui = self._gui()
        gui.root = object()
        gui._ask_yesno_threadsafe = mock.Mock(return_value=False)
        self.assertFalse(gui._filezilla_fund_bestaetigen("D:\\x\\filezilla.exe"))
        _args, kwargs = gui._ask_yesno_threadsafe.call_args
        self.assertIs(False, kwargs.get("default_yes"), "ein versehentliches Enter darf nichts starten")
        gui._ask_yesno_threadsafe = mock.Mock(return_value=True)
        self.assertTrue(gui._filezilla_fund_bestaetigen("D:\\x\\filezilla.exe"))

    def test_eine_fehlgeschlagene_rueckfrage_ist_ein_nein(self) -> None:
        gui = self._gui()
        gui.root = object()
        gui._ask_yesno_threadsafe = mock.Mock(side_effect=RuntimeError("Fenster weg"))
        self.assertFalse(gui._filezilla_fund_bestaetigen("D:\\x\\filezilla.exe"))

    def test_der_fund_der_suche_wird_vor_dem_merken_bestaetigt(self) -> None:
        quelle = Path(APP.__file__).read_text(encoding="utf-8", errors="replace")
        anfang = quelle.index("found = self._find_filezilla_by_scan()")
        block = quelle[anfang:anfang + 700]
        self.assertLess(block.index("self._filezilla_fund_bestaetigen(found)"),
                        block.index("self._remember_filezilla_path(found)"))

    def _suche(self, wurzel: Path, arbeit: Path | None = None) -> "str | None":
        gui = self._gui()
        gui._feste_laufwerke = lambda: [str(wurzel)]
        gui._get_runtime_temp_dir = lambda anlegen=True: str(arbeit or wurzel / "gibt_es_nicht_arbeitsordner")
        leer = {k: "" for k in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")}
        with mock.patch.dict(os.environ, leer):
            return gui._find_filezilla_by_scan(time_budget=20.0)

    def test_ein_entpacktes_archiv_im_arbeitsordner_wird_nicht_gefunden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            w = Path(tmp)
            fremd = w / "Temp - Dump-Image Converter" / "ps5conv_archiv_1" / "FileZilla"
            fremd.mkdir(parents=True)
            (fremd / "filezilla.exe").write_bytes(b"MZ")
            self.assertIsNone(self._suche(w))

    def test_der_eingestellte_arbeitsordner_wird_uebersprungen_auch_mit_anderem_namen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            w = Path(tmp)
            arbeit = w / "Mein Arbeitsordner"
            (arbeit / "x").mkdir(parents=True)
            (arbeit / "x" / "filezilla.exe").write_bytes(b"MZ")
            self.assertIsNone(self._suche(w, arbeit))

    def test_ein_gewoehnlicher_ort_wird_weiter_gefunden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            w = Path(tmp)
            (w / "Tools" / "FileZilla").mkdir(parents=True)
            exe = w / "Tools" / "FileZilla" / "filezilla.exe"
            exe.write_bytes(b"MZ")
            self.assertEqual(os.path.normcase(str(exe)), os.path.normcase(self._suche(w) or ""))

    def test_text_in_allen_sprachen(self) -> None:
        for sprache in SPRACHEN:
            self.assertIn("{pfad}", i18n.STRINGS["filezilla.fund_frage"][sprache], sprache)
            self.assertTrue(i18n.STRINGS["filezilla.fund_titel"][sprache], sprache)


# ------------------------------------------------------------------------------------------------------ SEC5
import collections                                              # noqa: E402
import zipfile                                                  # noqa: E402

from ps5_validator.utils import archiv_quelle as aq            # noqa: E402

_Platte = collections.namedtuple("_Platte", "total used free")


class ArchivPlatzTests(unittest.TestCase):
    """SEC5: Die Platzpruefung vor dem Start sah nur die Archivgroesse; ausgepackt fuellte ein Archiv das Laufwerk."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.w = Path(tmp.name)
        self.zip = self.w / "spiel.zip"
        with zipfile.ZipFile(self.zip, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("Spiel/sce_sys/param.json", "{}")
            z.writestr("Spiel/eboot.bin", b"\0" * (4 * 1024 * 1024))       # klein gepackt, 4 MiB entpackt
        self.ziel = self.w / "aus"

    def test_zip_zu_wenig_platz_wird_vor_dem_entpacken_erkannt(self) -> None:
        with mock.patch.object(aq.shutil, "disk_usage", return_value=_Platte(10**12, 10**12 - 3 * 1024 * 1024, 3 * 1024 * 1024)):
            with self.assertRaises(aq.ArchivFehler) as ctx:
                aq.entpacken(str(self.zip), str(self.ziel), platz_reserve=0)
        self.assertIn("Zu wenig Platz", str(ctx.exception))
        self.assertEqual([], list(self.ziel.rglob("*.bin")), "es wurde nichts entpackt")

    def test_zip_die_reserve_zaehlt_mit(self) -> None:
        frei = 5 * 1024 * 1024                  # reicht fuer 4 MiB, aber nicht fuer 4 MiB plus 2 MiB Reserve
        with mock.patch.object(aq.shutil, "disk_usage", return_value=_Platte(10**12, 10**12 - frei, frei)):
            with self.assertRaises(aq.ArchivFehler):
                aq.entpacken(str(self.zip), str(self.ziel), platz_reserve=2 * 1024 * 1024)
            wurzel = aq.entpacken(str(self.zip), str(self.w / "aus2"), platz_reserve=512 * 1024)
        self.assertTrue(os.path.isfile(os.path.join(wurzel, "sce_sys", "param.json")))

    def test_zip_mit_genug_platz_wird_wie_vorher_entpackt(self) -> None:
        wurzel = aq.entpacken(str(self.zip), str(self.ziel))
        self.assertTrue(os.path.isfile(os.path.join(wurzel, "eboot.bin")))

    def test_siebenzip_wird_bei_knappem_platz_angehalten(self) -> None:
        archiv = self.w / "spiel.7z"
        archiv.write_bytes(b"7z")
        zustand = {"gekillt": False}

        class _Prozess:
            def __init__(self, *_a, **_k):
                self.stdout = self
                self.returncode = None

            def read(self, _n):
                return b"." if not zustand["gekillt"] else b""

            def kill(self):
                zustand["gekillt"] = True

            def wait(self):
                return 0

        with mock.patch.object(aq, "siebenzip_suchen", return_value="7z.exe"), \
                mock.patch.object(aq.subprocess, "Popen", _Prozess), \
                mock.patch.object(aq.shutil, "disk_usage", return_value=_Platte(10**12, 10**12 - 100, 100)):
            with self.assertRaises(aq.ArchivFehler) as ctx:
                aq.entpacken(str(archiv), str(self.ziel), passwort="x")
        self.assertIn("Zu wenig Platz", str(ctx.exception))
        self.assertTrue(zustand["gekillt"], "7-Zip muss angehalten werden, bevor das Laufwerk voll ist")

    def test_siebenzip_mit_genug_platz_laeuft_durch(self) -> None:
        archiv = self.w / "spiel.7z"
        archiv.write_bytes(b"7z")
        stuecke = [b"50%", b""]

        class _Prozess:
            def __init__(self, *_a, **_k):
                self.stdout = self

            def read(self, _n):
                return stuecke.pop(0) if stuecke else b""

            def wait(self):
                return 0

        with mock.patch.object(aq, "siebenzip_suchen", return_value="7z.exe"), \
                mock.patch.object(aq.subprocess, "Popen", _Prozess), \
                mock.patch.object(aq.shutil, "disk_usage", return_value=_Platte(10**12, 0, 10**12)):
            aq.entpacken(str(archiv), str(self.ziel), passwort="x")


# ------------------------------------------------------------------------------------------------------- S5
class AssetPackScannenTests(unittest.TestCase):
    """S5: "In neuen Ordner entpacken" liess einen nicht lesbaren Unterordner still aus - Ergebnis "erfolgreich"."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.w = Path(tmp.name)
        (self.w / "a").mkdir()
        (self.w / "a" / "x.bin").write_bytes(b"x")
        (self.w / "b").mkdir()
        (self.w / "b" / "y.bin").write_bytes(b"y")

    def _scandir_mit_sperre(self, gesperrt: str):
        echt = os.scandir

        def scandir(pfad="."):
            if os.path.basename(str(pfad)) == gesperrt:
                raise PermissionError(13, "Zugriff verweigert", str(pfad))
            return echt(pfad)

        return mock.patch.object(ap.os, "scandir", scandir)

    def test_nachsichtig_bleibt_wie_vorher(self) -> None:
        with self._scandir_mit_sperre("b"):
            namen = sorted(rel for rel, _v, _o in ap._dateien_scannen(str(self.w)))
        self.assertIn("a/x.bin", namen)
        self.assertNotIn("b/y.bin", namen)

    def test_streng_meldet_den_nicht_lesbaren_ordner(self) -> None:
        with self._scandir_mit_sperre("b"):
            with self.assertRaises(ap.PackFehler) as ctx:
                list(ap._dateien_scannen(str(self.w), streng=True))
        self.assertIn("b nicht lesbar", str(ctx.exception))

    def test_streng_ohne_fehler_liefert_alles(self) -> None:
        namen = sorted(rel for rel, _v, _o in ap._dateien_scannen(str(self.w), streng=True))
        self.assertEqual(["a", "a/x.bin", "b", "b/y.bin"], namen)

    def test_der_entpacker_fuer_neue_ordner_scannt_streng(self) -> None:
        quelle = Path(ap.__file__).read_text(encoding="utf-8")
        anfang = quelle.index("def entpacken_in_neuen_ordner(")
        self.assertIn("_dateien_scannen(str(ordner), streng=True)", quelle[anfang:anfang + 6000])


# ------------------------------------------------------------------------------------------------------- S8
from ps5_validator.utils import bibliothek as bib             # noqa: E402


class UmbenennenProtokollTests(unittest.TestCase):
    """S8: Ein Protokoll, das sich nicht schreiben liess, war nur eine ``log.warning`` - "Rueckgaengig" fand nichts."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.w = Path(tmp.name)
        (self.w / "alt.pkg").write_bytes(b"x")
        self.plan = [{"alt": str(self.w / "alt.pkg"), "neu": str(self.w / "neu.pkg"),
                      "zustand": bib.BEREIT, "gewaehlt": True}]

    def test_ohne_schreibfehler_gibt_es_ein_protokoll_und_keinen_fehler(self) -> None:
        erg = bib.umbenennen_ausfuehren(self.plan, str(self.w / "log"))
        self.assertEqual(1, len(erg["erledigt"]))
        self.assertTrue(os.path.isfile(erg["protokoll"]))
        self.assertEqual("", erg["protokoll_fehler"])

    def test_scheitert_das_protokoll_nennt_das_ergebnis_den_grund(self) -> None:
        with mock.patch.object(bib, "_protokoll_schreiben", side_effect=PermissionError(13, "Zugriff verweigert")):
            erg = bib.umbenennen_ausfuehren(self.plan, str(self.w / "log"))
        self.assertEqual(1, len(erg["erledigt"]), "umbenannt wurde trotzdem")
        self.assertTrue((self.w / "neu.pkg").is_file())
        self.assertEqual("", erg["protokoll"])
        self.assertIn("Zugriff verweigert", erg["protokoll_fehler"])

    def test_nichts_erledigt_kein_protokollfehler(self) -> None:
        erg = bib.umbenennen_ausfuehren([], str(self.w / "log"))
        self.assertEqual("", erg["protokoll_fehler"])

    def test_die_oberflaeche_zeigt_den_hinweis(self) -> None:
        gui = GUI.__new__(GUI)
        meldungen: list[str] = []
        gui._t = lambda schluessel, **w: schluessel + str(w)
        gui._append_to_log = meldungen.append
        gui.root = None
        gui._bibliothek_bildspeicher = lambda: mock.MagicMock()
        gui._bibliothek_protokollordner = lambda: str(self.w / "log")
        gui._bibliothek_umbenannt = lambda *_a, **_k: None
        gefragt: list[tuple] = []
        gesehen: list[dict] = []
        with mock.patch.object(bib, "_protokoll_schreiben", side_effect=OSError("Platte voll")), \
                mock.patch.object(APP.messagebox, "showwarning", lambda *a, **k: gefragt.append(a)):
            gui._bibliothek_umbenennen_anwenden(self.plan, lambda erg, rueck: gesehen.append(erg))
        self.assertTrue(any("library.protokoll_fehlt" in m and "Platte voll" in m for m in meldungen), meldungen)
        self.assertEqual(1, len(gefragt))
        self.assertEqual(1, len(gesehen))

    def test_text_in_allen_sprachen(self) -> None:
        for sprache in SPRACHEN:
            self.assertIn("{fehler}", i18n.STRINGS["library.protokoll_fehlt"][sprache], sprache)


# ------------------------------------------------------------------------------------------------------- C2
import queue as _queue                                          # noqa: E402
import re as _re                                                # noqa: E402
import threading as _threading                                  # noqa: E402


class SchreiberUndCacheNebenlaeufigTests(unittest.TestCase):
    def test_queuewriter_verliert_und_verstuemmelt_nichts_bei_mehreren_faeden(self) -> None:
        q: "_queue.Queue[str]" = _queue.Queue()
        schreiber = APP._QueueWriter(q)
        faeden, je_faden = 8, 1500
        fehler: list[BaseException] = []

        def lauf(nr: int) -> None:
            try:
                for k in range(je_faden):
                    schreiber.write("zeile-%d-%d\n" % (nr, k))
                    schreiber.write("a-%d-%d\nb-%d-%d\n" % (nr, k, nr, k))        # mehrere Zeilen in einem Aufruf
            except BaseException as exc:  # noqa: BLE001
                fehler.append(exc)

        t = [_threading.Thread(target=lauf, args=(n,)) for n in range(faeden)]
        for x in t:
            x.start()
        for x in t:
            x.join(60)
        schreiber.flush()
        zeilen = []
        while not q.empty():
            zeilen.append(q.get_nowait())
        self.assertEqual([], fehler)
        self.assertEqual(faeden * je_faden * 3, len(zeilen))
        muster = _re.compile(r"^(zeile|a|b)-\d+-\d+$")
        self.assertEqual([], [z for z in zeilen if not muster.match(z)][:5])

    def test_queuewriter_traegt_eine_sperre(self) -> None:
        self.assertTrue(hasattr(APP._QueueWriter(_queue.Queue()), "_sperre"))

    def test_vorschau_cache_haelt_die_obergrenze_auch_unter_last(self) -> None:
        gui = GUI.__new__(GUI)
        gui._preview_cache = {}
        gui._PREVIEW_CACHE_MAX = 20
        fehler: list[BaseException] = []

        def lauf(nr: int) -> None:
            try:
                for k in range(2000):
                    gui._preview_cache_eintragen(("pfad-%d-%d" % (nr, k % 50), k), ({}, None))
            except BaseException as exc:  # noqa: BLE001
                fehler.append(exc)

        t = [_threading.Thread(target=lauf, args=(n,)) for n in range(6)]
        for x in t:
            x.start()
        for x in t:
            x.join(60)
        self.assertEqual([], fehler)
        self.assertLessEqual(len(gui._preview_cache), 20)

    def test_vorschau_cache_wirft_den_aeltesten_hinaus_und_ersetzt_einen_vorhandenen_schluessel(self) -> None:
        gui = GUI.__new__(GUI)
        gui._preview_cache = {}
        gui._PREVIEW_CACHE_MAX = 3
        for n in range(3):
            gui._preview_cache_eintragen(("k", n), n)
        gui._preview_cache_eintragen(("k", 1), "neu")                  # vorhanden: ersetzt, wirft nichts hinaus
        self.assertEqual([("k", 0), ("k", 1), ("k", 2)], sorted(gui._preview_cache))
        self.assertEqual("neu", gui._preview_cache[("k", 1)])
        gui._preview_cache_eintragen(("k", 9), 9)                      # voll: der aelteste (k, 0) geht
        self.assertNotIn(("k", 0), gui._preview_cache)
        self.assertEqual(3, len(gui._preview_cache))

    def test_kein_unbewachtes_pop_next_iter_mehr_im_programm(self) -> None:
        quelle = Path(APP.__file__).read_text(encoding="utf-8", errors="replace")
        self.assertNotIn("self._preview_cache.pop(next(iter(self._preview_cache)))", quelle)


if __name__ == "__main__":
    unittest.main()
