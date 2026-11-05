# -*- coding: utf-8 -*-
"""Tests fuer die Betriebspruefung der Diagnose (``betriebsdiagnose``).

Die Pruefregeln arbeiten auf schlichten Datensaetzen, die Messfunktionen auf echten Dateien in einem Testordner - ein
Fenster braucht nur der letzte Teil (Anschluss an das Programm).

Anlass (03.11.2026): Der Bericht sagte "Darstellung: keine Auffaelligkeit", obwohl im Protokoll ein ERROR mit
Rueckverfolgung stand, der OSFMount-Treiber fehlte und kein Administratorrecht da war. Jede Klasse hier haelt eine
solche Fehlerklasse fest - jeweils mit Gegenprobe (ohne die Ursache schlaegt nichts an).
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))
# MkPFS: ohne den Pfad scheitert das Laden des Hauptprogramms in AnschlussTests.
sys.path.insert(0, str(PROJEKT / "MkPFS-1.1.0"))

# Einstellungen des Anwenders fernhalten - beim Import, wie in allen Pruefstaenden (nie zur Laufzeit: Eine spaeter
# erzeugte Programminstanz einer anderen Testdatei las sonst diesen Ordner und seine gemerkten Einstellungen; zwei
# Zielformat-Tests aus test_debuglauf_befunde schlugen deshalb an). Der Ordner gehoert nur dieser Datei.
import pruefumgebung                                          # noqa: E402
pruefumgebung.umlenken("betriebsdiagnose", leeren=True)

from ps5_validator.utils import anzeige_diagnose as ad       # noqa: E402
from ps5_validator.utils import betriebsdiagnose as bd       # noqa: E402
from ps5_validator.utils.i18n import STRINGS                 # noqa: E402

JETZT = datetime.datetime(2026, 11, 3, 20, 0, 0)


def _kennungen(befunde) -> list[str]:
    return sorted(b.kennung for b in befunde)


class _Ordner(unittest.TestCase):
    def setUp(self) -> None:
        self.ordner = tempfile.mkdtemp(prefix="betriebsdiag_")
        self.addCleanup(shutil.rmtree, self.ordner, True)

    def schreiben(self, name: str, inhalt: bytes = b"x") -> str:
        pfad = os.path.join(self.ordner, name)
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        with open(pfad, "wb") as datei:
            datei.write(inhalt)
        return pfad


# ---------------------------------------------------------------------------
class ProtokollTests(_Ordner):

    def _log(self, *zeilen: str) -> str:
        pfad = self.schreiben("ps5converter.log", "\n".join(zeilen).encode("utf-8"))
        return pfad

    @staticmethod
    def _zeit(stunden_zurueck: float) -> str:
        return (JETZT - datetime.timedelta(hours=stunden_zurueck)).strftime("%Y-%m-%d %H:%M:%S")

    def test_ein_error_mit_rueckverfolgung_wird_gelesen(self) -> None:
        pfad = self._log(
            "%s [ERROR   ] PS5Converter.x: Aufgabe gescheitert" % self._zeit(2),
            "Traceback (most recent call last):",
            '  File "a.py", line 1, in f',
            "    os.replace(a, b)",
            "PermissionError: [WinError 5] Zugriff verweigert",
            "%s [INFO    ] PS5Converter: danach" % self._zeit(1))
        ok, eintraege = bd.protokoll_lesen(pfad)
        self.assertTrue(ok)
        fehler = [e for e in eintraege if e.stufe == "ERROR"]
        self.assertEqual(1, len(fehler))
        self.assertTrue(fehler[0].rueckverfolgung)
        self.assertIn("PermissionError", fehler[0].text, "die Ausnahme steht im Befund, nicht nur 'gescheitert'")

    def test_ein_aelterer_error_ist_eine_warnung_ein_neuer_ein_fehler(self) -> None:
        pfad = self._log("%s [ERROR   ] alt: kaputt" % self._zeit(5), "%s [ERROR   ] neu: kaputt anders" % self._zeit(1))
        ok, eintraege = bd.protokoll_lesen(pfad)
        sitzung = JETZT - datetime.timedelta(hours=2)
        befunde = bd.pruefe_protokoll(bd.Protokolllage(eintraege, JETZT, sitzung, ok))
        stufen = {b.text.split(": ", 1)[1].split()[0]: b.schwere for b in befunde}
        self.assertEqual({"alt:": ad.WARNUNG, "neu:": ad.FEHLER}, stufen)

    def test_fehler_ausserhalb_der_frist_zaehlen_nicht(self) -> None:
        pfad = self._log("%s [ERROR   ] uralt: kaputt" % self._zeit(bd.PROTOKOLL_FRIST_H + 1))
        ok, eintraege = bd.protokoll_lesen(pfad)
        self.assertEqual([], bd.pruefe_protokoll(bd.Protokolllage(eintraege, JETZT, None, ok)))

    def test_ohne_fehler_kein_befund(self) -> None:
        """Gegenprobe: nur INFO."""
        pfad = self._log("%s [INFO    ] alles gut" % self._zeit(1))
        ok, eintraege = bd.protokoll_lesen(pfad)
        self.assertEqual([], bd.pruefe_protokoll(bd.Protokolllage(eintraege, JETZT, None, ok)))

    def test_warnungen_sind_hinweise(self) -> None:
        pfad = self._log("%s [WARNING ] Fenster nicht schliessbar" % self._zeit(1))
        ok, eintraege = bd.protokoll_lesen(pfad)
        befunde = bd.pruefe_protokoll(bd.Protokolllage(eintraege, JETZT, None, ok))
        self.assertEqual([("HINWEIS", "protokoll_warnung")], [(b.schwere, b.kennung) for b in befunde])

    def test_gleiche_fehler_mit_anderen_zahlen_sind_eine_gruppe(self) -> None:
        pfad = self._log(*("%s [ERROR   ] Datei %d nicht lesbar" % (self._zeit(1), n) for n in range(7)))
        ok, eintraege = bd.protokoll_lesen(pfad)
        befunde = bd.pruefe_protokoll(bd.Protokolllage(eintraege, JETZT, None, ok))
        self.assertEqual(1, len(befunde))
        self.assertTrue(befunde[0].text.startswith("7x ERROR"))

    def test_nur_die_haeufigsten_arten_stehen_einzeln_da(self) -> None:
        pfad = self._log(*("%s [ERROR   ] Art%s kaputt" % (self._zeit(1), "abcdefgh"[n]) for n in range(8)))
        ok, eintraege = bd.protokoll_lesen(pfad)
        befunde = bd.pruefe_protokoll(bd.Protokolllage(eintraege, JETZT, None, ok))
        self.assertEqual(bd.PROTOKOLL_GRUPPEN_MAX + 1, len(befunde))
        self.assertIn("3 weitere Fehlerarten", befunde[-1].text)

    def test_fehlende_datei_ist_in_ordnung_unlesbare_nicht(self) -> None:
        self.assertEqual((True, ()), bd.protokoll_lesen(os.path.join(self.ordner, "gibt-es-nicht.log")))
        self.assertEqual(["protokoll_unlesbar"], _kennungen(bd.pruefe_protokoll(bd.Protokolllage(lesbar=False))))

    def test_nur_das_ende_der_datei_wird_gelesen(self) -> None:
        zeilen = ["%s [ERROR   ] Zeile%06d" % (self._zeit(1), n) for n in range(5000)]
        pfad = self._log(*zeilen)
        _ok, eintraege = bd.protokoll_lesen(pfad, schwanz_bytes=20000)
        self.assertLess(len(eintraege), 5000)
        self.assertTrue(eintraege[-1].text.endswith("Zeile004999"))
        self.assertRegex(eintraege[0].text, r"Zeile\d{6}$", "die angebrochene erste Zeile ist verworfen")


# ---------------------------------------------------------------------------
class ResteTests(_Ordner):

    def test_namen_werden_richtig_eingeordnet(self) -> None:
        erwartet = {
            "ps5conv_ps5pkg_abc": bd.ART_ARBEIT, "ps4dib_arbeit": bd.ART_ARBEIT,
            "CUSA00775.partial": bd.ART_TEIL, "Spiel.ffpfsc.tmp": bd.ART_TEIL,
            "..UP8016-X.pkg.c49.build.tmp.x.cnt.tmp": bd.ART_TEIL,
            ".ps5conv_tmp_write_test_xyz": bd.ART_PROBE, ".ps5conv_doktor_probe": bd.ART_PROBE,
            # Gegenproben: kein Rest
            "notizen.txt": "", "Spiel.ffpfsc": "", "x.tmp": "", "ps5conv_pruefung": "",
            "ps5converter_meta_cache": "",
        }
        for name, art in erwartet.items():
            with self.subTest(name=name):
                self.assertEqual(art, bd.rest_art(name))

    def test_suchen_findet_nur_reste_und_misst_ihre_groesse(self) -> None:
        self.schreiben("ps5conv_ps5pkg_a/Spiel/eboot.bin", b"x" * 1000)
        self.schreiben("CUSA1.partial/Image0/a.bin", b"y" * 500)
        self.schreiben("Spiel.exfat.tmp", b"z" * 300)
        self.schreiben(".ps5conv_tmp_write_test_q", b"")
        self.schreiben("normal.txt", b"nicht")
        reste = {os.path.basename(r.pfad): r for r in bd.reste_suchen([self.ordner])}
        self.assertEqual({"ps5conv_ps5pkg_a", "CUSA1.partial", "Spiel.exfat.tmp", ".ps5conv_tmp_write_test_q"},
                         set(reste))
        self.assertEqual(1000, reste["ps5conv_ps5pkg_a"].bytes)
        self.assertEqual(500, reste["CUSA1.partial"].bytes)
        self.assertEqual(300, reste["Spiel.exfat.tmp"].bytes)
        self.assertEqual(bd.ART_PROBE, reste[".ps5conv_tmp_write_test_q"].art)

    def test_derselbe_ordner_zweimal_zaehlt_einmal(self) -> None:
        self.schreiben("ps5conv_a/x.bin")
        self.assertEqual(1, len(bd.reste_suchen([self.ordner, self.ordner.upper() if os.name == "nt" else self.ordner])))

    def test_das_zeitbudget_wird_eingehalten(self) -> None:
        for n in range(30):
            self.schreiben("ps5conv_a/d%d.bin" % n, b"x" * 10)
        reste = bd.reste_suchen([self.ordner], zeitbudget=-1.0)
        self.assertTrue(reste[0].unvollstaendig)

    def test_ein_alter_arbeitsordner_ohne_laufende_aufgabe_ist_eine_warnung(self) -> None:
        reste = (bd.Rest("E:/x/ps5conv_a", bd.ART_ARBEIT, 5 * 1024 ** 3, 3 * 3600),)
        befunde = bd.pruefe_reste(bd.Restelage(reste, arbeit_laeuft=False))
        self.assertEqual([("WARNUNG", "reste_liegen_geblieben")], [(b.schwere, b.kennung) for b in befunde])
        self.assertIn("5.0 GB", befunde[0].text)

    def test_waehrend_einer_aufgabe_gehoeren_die_ordner_zu_ihr(self) -> None:
        reste = (bd.Rest("E:/x/ps5conv_a", bd.ART_ARBEIT, 5 * 1024 ** 3, 3 * 3600),)
        self.assertEqual([], bd.pruefe_reste(bd.Restelage(reste, arbeit_laeuft=True)))

    def test_ein_junger_ordner_koennte_zu_einem_anlaufenden_lauf_gehoeren(self) -> None:
        reste = (bd.Rest("E:/x/ps5conv_a", bd.ART_ARBEIT, 100, bd.RESTE_MINDESTALTER_S - 1),)
        self.assertEqual([], bd.pruefe_reste(bd.Restelage(reste)))

    def test_schreibproben_sind_nur_ein_hinweis(self) -> None:
        reste = (bd.Rest("C:/t/.ps5conv_tmp_write_test_a", bd.ART_PROBE, 0, 86400),)
        befunde = bd.pruefe_reste(bd.Restelage(reste))
        self.assertEqual([("HINWEIS", "schreibprobe_liegt")], [(b.schwere, b.kennung) for b in befunde])

    def test_viele_reste_werden_zusammengefasst(self) -> None:
        reste = tuple(bd.Rest("E:/x/ps5conv_%d" % n, bd.ART_ARBEIT, 10, 3600) for n in range(20))
        befunde = bd.pruefe_reste(bd.Restelage(reste))
        self.assertEqual(1, len(befunde))
        self.assertIn("20 Arbeitsordner", befunde[0].text)
        self.assertIn("14 weitere", befunde[0].text)


# ---------------------------------------------------------------------------
class RessourcenTests(unittest.TestCase):

    def test_normalbetrieb_gibt_nichts(self) -> None:
        self.assertEqual([], bd.pruefe_ressourcen(bd.Ressourcenlage(gdi=700, user=300, handles=900, faeden=8)))

    def test_stufen(self) -> None:
        for feld, warn, fehl in (("gdi", bd.GDI_WARNUNG, bd.GDI_FEHLER), ("user", bd.USER_WARNUNG, bd.USER_FEHLER),
                                 ("handles", bd.HANDLES_WARNUNG, bd.HANDLES_FEHLER),
                                 ("faeden", bd.FADEN_WARNUNG, bd.FADEN_FEHLER)):
            with self.subTest(feld=feld):
                unten = bd.pruefe_ressourcen(bd.Ressourcenlage(**{feld: warn - 1}))
                mitte = bd.pruefe_ressourcen(bd.Ressourcenlage(**{feld: warn}))
                oben = bd.pruefe_ressourcen(bd.Ressourcenlage(**{feld: fehl}))
                self.assertEqual([], unten)
                self.assertEqual("WARNUNG", mitte[0].schwere)
                self.assertEqual("FEHLER", oben[0].schwere)

    def test_werkzeug_ohne_auftrag_ist_verwaist(self) -> None:
        """03.11.2026: OrbisPkgTool/ffpfsc-pkg-tool liefen nach ABBRECHEN und nach dem Schliessen weiter."""
        befunde = bd.pruefe_ressourcen(bd.Ressourcenlage(werkzeuge=("orbispkgtool", "ffpfsc-pkg-tool")))
        self.assertEqual([("WARNUNG", "prozess_verwaist")], [(b.schwere, b.kennung) for b in befunde])
        self.assertIn("ffpfsc-pkg-tool", befunde[0].text)

    def test_werkzeug_mit_laufendem_auftrag_ist_in_ordnung(self) -> None:
        self.assertEqual([], bd.pruefe_ressourcen(bd.Ressourcenlage(werkzeuge=("orbispkgtool",), arbeit_laeuft=True)))

    def test_ohne_psutil_zaehlt_das_programm_selbst_mit(self) -> None:
        befunde = bd.pruefe_ressourcen(bd.Ressourcenlage(getrackte_werkzeuge=2))
        self.assertEqual(["prozess_verwaist"], _kennungen(befunde))

    def test_messen_liefert_echte_werte(self) -> None:
        lage = bd.ressourcen_messen()
        self.assertGreaterEqual(lage.faeden, 1)
        self.assertGreater(lage.handles, 0)
        self.assertGreaterEqual(lage.gdi, 0)
        self.assertGreaterEqual(lage.user, 0)

    def test_ein_fremdes_kind_ist_kein_werkzeug_ein_werkzeugname_schon(self) -> None:
        """Gegenprobe: ein ``python``-Kind zaehlt nicht; mit dem Namen in der Liste zaehlt es."""
        import subprocess  # noqa: PLC0415
        kind = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(kind.kill)
        time.sleep(0.5)
        self.assertEqual((), bd.ressourcen_messen().werkzeuge)
        with mock.patch.object(bd, "WERKZEUG_PROZESSE", ("python",)):
            self.assertGreaterEqual(len(bd.ressourcen_messen().werkzeuge), 1)


# ---------------------------------------------------------------------------
class WiederaufnahmeTests(_Ordner):

    def _datei(self, jobs: dict) -> str:
        return self.schreiben("runtime_checkpoint.json", json.dumps({"jobs": jobs}).encode("utf-8"))

    def test_lesen(self) -> None:
        pfad = self._datei({"a": {"state": "in_progress", "updated": "2026-11-03T13:57:39", "mode": "pack_folder",
                                  "src": "E:/x"}, "b": {"state": "done", "updated": "x"}})
        ok, punkte = bd.wiederaufnahme_lesen(pfad)
        self.assertTrue(ok)
        self.assertEqual(["in_progress", "done"], [p.zustand for p in punkte])
        self.assertEqual(datetime.datetime(2026, 11, 3, 13, 57, 39), punkte[0].aktualisiert)
        self.assertIsNone(punkte[1].aktualisiert)

    def test_fehlende_datei_ist_in_ordnung_kaputte_nicht(self) -> None:
        self.assertEqual((True, ()), bd.wiederaufnahme_lesen(os.path.join(self.ordner, "nein.json")))
        kaputt = self.schreiben("kaputt.json", b"{nicht json")
        ok, _ = bd.wiederaufnahme_lesen(kaputt)
        self.assertFalse(ok)
        self.assertEqual(["wiederaufnahme_unlesbar"], _kennungen(bd.pruefe_wiederaufnahme(
            bd.Wiederaufnahmelage(lesbar=False))))

    def test_frisch_unfertig_ist_ein_hinweis_uralt_eine_warnung(self) -> None:
        punkte = (bd.Wiederaufnahmepunkt("in_progress", JETZT - datetime.timedelta(hours=2), "pack_folder", "E:/a"),
                  bd.Wiederaufnahmepunkt("in_progress", JETZT - datetime.timedelta(days=30), "pack_folder", "E:/b"))
        befunde = bd.pruefe_wiederaufnahme(bd.Wiederaufnahmelage(punkte, JETZT))
        self.assertEqual({("HINWEIS", "wiederaufnahme_offen"), ("WARNUNG", "wiederaufnahme_veraltet")},
                         {(b.schwere, b.kennung) for b in befunde})

    def test_fertige_und_laufende_zaehlen_nicht(self) -> None:
        punkte = (bd.Wiederaufnahmepunkt("done", JETZT, "x", "y"),)
        self.assertEqual([], bd.pruefe_wiederaufnahme(bd.Wiederaufnahmelage(punkte, JETZT)))
        offen = (bd.Wiederaufnahmepunkt("in_progress", JETZT - datetime.timedelta(days=30), "x", "y"),)
        self.assertEqual([], bd.pruefe_wiederaufnahme(bd.Wiederaufnahmelage(offen, JETZT, arbeit_laeuft=True)))


# ---------------------------------------------------------------------------
class EinstellungenTests(_Ordner):

    def _config(self, daten: dict) -> str:
        return self.schreiben("konfig/paths.json", json.dumps(daten).encode("utf-8"))

    def test_fehlende_pfade_werden_gemeldet_vorhandene_nicht(self) -> None:
        da = os.path.join(self.ordner, "da")
        os.makedirs(da)
        weg = os.path.join(self.ordner, "weg")
        cfg = self._config({"ps4dib_ziel": da, "ps5pkg_ziel": weg, "temp_dir": weg,
                            "library_scan_folders": [da, weg], "theme": "dunkel", "language": "de",
                            "karte_deckkraft": 63, "filezilla_path": "", "netz_ordner": "\\\\server\\share"})
        lage = bd.einstellungen_messen(cfg)
        self.assertTrue(lage.lesbar and lage.ordner_beschreibbar)
        self.assertEqual({("ps5pkg_ziel", weg), ("temp_dir", weg), ("library_scan_folders", weg)},
                         set(lage.fehlende_pfade))
        self.assertEqual(5, lage.geprueft, "Werte ohne Pfad und UNC-Pfade zaehlen nicht mit")
        befunde = bd.pruefe_einstellungen(lage)
        self.assertEqual([("HINWEIS", "gemerkter_pfad_fehlt")], [(b.schwere, b.kennung) for b in befunde])

    def test_alles_vorhanden_gibt_nichts(self) -> None:
        da = os.path.join(self.ordner, "da")
        os.makedirs(da)
        self.assertEqual([], bd.pruefe_einstellungen(bd.einstellungen_messen(self._config({"ps4dib_ziel": da}))))

    def test_kaputte_datei_ist_ein_fehler(self) -> None:
        cfg = self.schreiben("konfig/paths.json", b"{kaputt")
        befunde = bd.pruefe_einstellungen(bd.einstellungen_messen(cfg))
        self.assertEqual([("FEHLER", "einstellungen_unlesbar")], [(b.schwere, b.kennung) for b in befunde])

    def test_bom_wird_gelesen(self) -> None:
        """PowerShell 5.1 schreibt die Datei mit BOM (siehe project_einstellungen_bom)."""
        cfg = self.schreiben("konfig/paths.json", b"\xef\xbb\xbf" + json.dumps({"theme": "dunkel"}).encode("utf-8"))
        self.assertTrue(bd.einstellungen_messen(cfg).lesbar)

    def test_ohne_datei_ist_in_ordnung(self) -> None:
        self.assertEqual([], bd.pruefe_einstellungen(bd.einstellungen_messen(
            os.path.join(self.ordner, "neu", "paths.json"))))

    def test_nicht_schreibbar_und_voll(self) -> None:
        befunde = bd.pruefe_einstellungen(bd.Einstellungslage(ordner_beschreibbar=False, ordner_frei_mb=20))
        self.assertEqual({"einstellungen_nicht_schreibbar", "einstellungen_voll"}, {b.kennung for b in befunde})
        self.assertTrue(all(b.schwere == "FEHLER" for b in befunde))


# ---------------------------------------------------------------------------
class SprachenTests(unittest.TestCase):

    def test_alle_texte_des_programms_sind_vollstaendig(self) -> None:
        """Der Waechter: 5 Sprachen, nichts leer, Platzhalter wie im Deutschen - fuer jeden der Texte."""
        lage = bd.sprachen_messen(STRINGS)
        self.assertGreater(lage.schluessel, 4000)
        self.assertEqual([], bd.pruefe_sprachen(lage), (lage.fehlend[:3], lage.leer[:3], lage.platzhalter[:3]))

    def test_gegenprobe_fehlend_leer_und_platzhalter(self) -> None:
        texte = {
            "ok": {s: "Hallo {name}" for s in bd.SPRACHEN},
            "fehlt": {"de": "a", "en": "a", "es": "a", "it": "a"},
            "leer": {"de": "a", "en": "a", "es": " ", "it": "a", "fr": "a"},
            "platz": {"de": "a {x}", "en": "a {y}", "es": "a {x}", "it": "a {x}", "fr": "a {x}"},
            "kaputt": "kein dict",
        }
        lage = bd.sprachen_messen(texte)
        self.assertEqual({("fehlt", "fr"), ("kaputt", "*")}, set(lage.fehlend))
        self.assertEqual({("leer", "es")}, set(lage.leer))
        self.assertEqual({("platz", "en")}, set(lage.platzhalter))
        befunde = {b.kennung: b.schwere for b in bd.pruefe_sprachen(lage)}
        self.assertEqual({"text_fehlt": "FEHLER", "text_leer": "WARNUNG", "text_platzhalter": "FEHLER"}, befunde)


# ---------------------------------------------------------------------------
class WerkzeugeTests(_Ordner):
    """Die mitgelieferten Programme und .NET (der Doktor pruefte bisher nur Python-Module und Ordner)."""

    def test_vorhandene_programme_gehen_durch(self) -> None:
        exe = self.schreiben("tool.exe", b"MZ")
        lage = bd.werkzeuge_messen({"tool": lambda: exe}, dotnet=lambda: "C:/dotnet")
        self.assertEqual((), lage.fehlend)
        self.assertTrue(lage.dotnet_da)
        self.assertEqual([], bd.pruefe_werkzeuge(lage))

    def test_fehlendes_leeres_und_kaputtes_wird_benannt(self) -> None:
        leer = self.schreiben("leer.exe", b"")
        weg = os.path.join(self.ordner, "weg.exe")

        def kaputt() -> str:
            raise RuntimeError("Suche kaputt")
        lage = bd.werkzeuge_messen({"a": lambda: "", "b": lambda: weg, "c": lambda: leer, "d": kaputt})
        gruende = dict(lage.fehlend)
        self.assertEqual("nicht gefunden", gruende["a"])
        self.assertTrue(gruende["b"].startswith("Datei fehlt"))
        self.assertTrue(gruende["c"].startswith("Datei ist leer"))
        self.assertIn("Suche kaputt", gruende["d"])
        befunde = bd.pruefe_werkzeuge(lage)
        self.assertEqual(4, len(befunde))
        self.assertTrue(all(b.kennung == "werkzeug_fehlt" and b.schwere == "WARNUNG" for b in befunde))

    def test_fehlendes_dotnet_ist_eine_warnung_unbekanntes_keine(self) -> None:
        self.assertEqual(["dotnet_fehlt"], _kennungen(bd.pruefe_werkzeuge(bd.werkzeuge_messen({}, dotnet=lambda: ""))))
        self.assertEqual([], bd.pruefe_werkzeuge(bd.werkzeuge_messen({})), "nicht gefragt = nicht gemeldet")

    def test_orbispkgtool_fehlt_ausserhalb_von_windows_ohne_befund(self) -> None:
        """Es gibt OrbisPkgTool nur als Windows-Bau. Die Mac-CI wurde am 05.11.2026 rot, weil die Betriebspruefung
        sein Fehlen dort als WARNUNG zaehlte und ``--anzeige-diagnose`` damit 1 lieferte."""
        suchen = {"OrbisPkgTool (PS4 PKG)": lambda: "", "ffpfsc-pkg-tool (PS5 PKG)": lambda: ""}
        for plattform in ("darwin", "linux"):
            lage = bd.werkzeuge_messen(suchen, plattform=plattform)
            self.assertEqual([("ffpfsc-pkg-tool (PS5 PKG)", "nicht gefunden")], list(lage.fehlend), plattform)
            self.assertEqual(1, lage.geprueft, plattform)
        # Gegenprobe: Unter Windows bleibt es ein Befund (dort wird es mitgeliefert).
        lage = bd.werkzeuge_messen(suchen, plattform="win32")
        self.assertEqual({"OrbisPkgTool (PS4 PKG)", "ffpfsc-pkg-tool (PS5 PKG)"}, {n for n, _ in lage.fehlend})
        self.assertEqual(2, lage.geprueft)

    def test_die_echten_programme_dieses_baums_sind_da(self) -> None:
        """Der Waechter am echten Baum: faellt eines weg (Virenscanner, falsches Entpacken), schlaegt er an."""
        from ps5_validator.utils import orbispkg, ps5_pkg_werkzeug as wz, prospero_pkg_tool as ppt  # noqa: PLC0415
        wurzeln = [str(PROJEKT)]
        lage = bd.werkzeuge_messen({"ffpfsc-pkg-tool": lambda: wz.werkzeug_suchen(wurzeln),
                                    "ProsperoPkgTool": lambda: ppt.werkzeug_suchen(wurzeln),
                                    "OrbisPkgTool": orbispkg.werkzeug_finden})
        self.assertEqual((), lage.fehlend)


# ---------------------------------------------------------------------------
class AbhaengigkeitenTests(_Ordner):

    def _req(self, text: str) -> str:
        return self.schreiben("requirements.txt", text.encode("utf-8"))

    def test_abweichungen_und_fehlende(self) -> None:
        pfad = self._req("Pillow==13.0.0\npsutil==7.2.2\nlz4==4.4.5  # Kommentar\nzlib-ng\n# nur Kommentar\n")
        installiert = {"Pillow": "13.0.0", "psutil": "7.0.0"}
        lage = bd.abhaengigkeiten_messen(pfad, installiert=lambda n: installiert.get(n, ""), plattform="win32")
        self.assertEqual(3, lage.geprueft, "zlib-ng ist nicht festgenagelt")
        self.assertEqual({("psutil", "7.2.2", "7.0.0"), ("lz4", "4.4.5", "")}, set(lage.abweichungen))
        befunde = {b.kennung: b.schwere for b in bd.pruefe_abhaengigkeiten(lage)}
        self.assertEqual({"paket_fehlt": "WARNUNG", "paket_abweichend": "HINWEIS"}, befunde)

    def test_alles_passt(self) -> None:
        pfad = self._req("Pillow==13.0.0\n")
        lage = bd.abhaengigkeiten_messen(pfad, installiert=lambda n: "13.0.0")
        self.assertEqual([], bd.pruefe_abhaengigkeiten(lage))
        self.assertEqual(1, lage.geprueft)

    def test_plattformzeilen_gelten_nur_dort(self) -> None:
        pfad = self._req('pythonnet==3.2.1; sys_platform == "win32"\npywebview==6.2.1; sys_platform == "win32"\n')
        unter_linux = bd.abhaengigkeiten_messen(pfad, installiert=lambda n: "", plattform="linux")
        self.assertEqual(0, unter_linux.geprueft)
        unter_windows = bd.abhaengigkeiten_messen(pfad, installiert=lambda n: "", plattform="win32")
        self.assertEqual(2, unter_windows.geprueft)

    def test_ohne_datei_entfaellt_die_pruefung(self) -> None:
        """Eine gebaute EXE hat keine requirements.txt (und keine Paket-Metadaten) - sonst fehlte jedes Paket."""
        lage = bd.abhaengigkeiten_messen(os.path.join(self.ordner, "nein.txt"))
        self.assertEqual(0, lage.geprueft)
        self.assertNotIn("Python-Pakete (requirements.txt)", bd.pruefe_alles(abhaengigkeiten=lage).geprueft)

    def test_die_echte_requirements_datei_passt_zur_umgebung(self) -> None:
        lage = bd.abhaengigkeiten_messen(str(PROJEKT / "requirements.txt"))
        self.assertGreater(lage.geprueft, 5)
        self.assertEqual((), lage.abweichungen)


# ---------------------------------------------------------------------------
class OptimierungTests(unittest.TestCase):

    def test_alte_abdeckung_ist_ein_hinweis(self) -> None:
        zeilen = ["Testabdeckung: 47.6 % (12648 Zeilen ungeprüft, gemessen vor 70.7 Tagen)"]
        befunde = bd.pruefe_optimierung(zeilen)
        self.assertEqual([("HINWEIS", "abdeckung_veraltet")], [(b.schwere, b.kennung) for b in befunde])
        self.assertIn("47.6", befunde[0].text)

    def test_frische_abdeckung_und_fehlende_zeile_geben_nichts(self) -> None:
        self.assertEqual([], bd.pruefe_optimierung(["Testabdeckung: 47.6 % (1 Zeilen ungeprüft, gemessen vor 2.0 Tagen)"]))
        self.assertEqual([], bd.pruefe_optimierung(["Durchsatz: seit dem Start lief keine Aufgabe"]))


# ---------------------------------------------------------------------------
class AbstuerzeTests(unittest.TestCase):

    def test_normalbetrieb(self) -> None:
        self.assertEqual([], bd.pruefe_abstuerze(bd.Absturzlage()))

    def test_jede_art_meldet_sich(self) -> None:
        befunde = bd.pruefe_abstuerze(bd.Absturzlage(unbehandelte_fehler=2, absturzdatei_bytes=4096,
                                                     absturzdatei="C:/t/ps5converter_absturz.txt", abzug_aktiv=False))
        self.assertEqual({("FEHLER", "unbehandelte_fehler"), ("WARNUNG", "harter_absturz"),
                          ("WARNUNG", "absturzabzug_aus")}, {(b.schwere, b.kennung) for b in befunde})


# ---------------------------------------------------------------------------
class AbschnittslesenTests(unittest.TestCase):
    """Was Doktor, Werkzeugpflege, Fremdwerkzeuge und Zusicherungen schon melden, zaehlt jetzt mit."""

    def test_doktor(self) -> None:
        zeilen = ["[ ok ] Python 3.14.6", "[ -- ] Zielordner: nicht gesetzt",
                  "[ !! ] Ohne Administratorrechte - .ffpkg bauen brauchen sie", "[FEHL] Temp-Ordner: gibt es nicht",
                  "       eingerueckte Erklaerung", "Doktor: 15 geprueft, 1 Hinweis, 1 Fehler"]
        befunde = bd.pruefe_doktor(zeilen)
        self.assertEqual([("FEHLER", "doktor_fehler"), ("HINWEIS", "doktor_hinweis")],
                         sorted((b.schwere, b.kennung) for b in befunde))
        self.assertIn("Administratorrechte", [b for b in befunde if b.kennung == "doktor_hinweis"][0].text)
        self.assertEqual([], bd.pruefe_doktor(["[ ok ] alles", "[ -- ] egal"]))

    def test_doktor_marken_stimmen_mit_dem_hauptmodul(self) -> None:
        """Die Marken sind hier abgeschrieben - aendert das Hauptmodul sie, faellt die Auswertung still aus."""
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        self.assertIn('DOKTOR_HINWEIS = "%s"' % bd.DOKTOR_HINWEIS, quelle)
        self.assertIn('DOKTOR_FEHLER = "%s"' % bd.DOKTOR_FEHLER, quelle)

    def test_werkzeugpflege(self) -> None:
        zeilen = ["Nutzlasten gefunden: 63", "ohne Zeile in der Lizenzdatei: foo.elf",
                  "Zeile ohne Datei im Ordner: bar.elf", "ohne Fassung im Dateinamen: a.elf"]
        befunde = bd.pruefe_werkzeugpflege(zeilen)
        self.assertEqual(2, len(befunde))
        self.assertTrue(all(b.schwere == "WARNUNG" for b in befunde))
        self.assertEqual([], bd.pruefe_werkzeugpflege(["Abgleich mit THIRD_PARTY_LICENSES.md: in Ordnung"]))

    def test_fremdwerkzeuge(self) -> None:
        befunde = bd.pruefe_fremdwerkzeuge(["Dokan-Treiber: bereit", "OSFMount-Treiber: NICHT INSTALLIERT – Abhilfe"])
        self.assertEqual([("HINWEIS", "fremdwerkzeug_fehlt")], [(b.schwere, b.kennung) for b in befunde])

    def test_eigenschaften(self) -> None:
        self.assertEqual([], bd.pruefe_eigenschaften(["Eigenschaften: 69 Zusicherungen geprüft, alle erfüllt"]))
        befunde = bd.pruefe_eigenschaften(["Eigenschaften: 69 Zusicherungen geprüft, 1 VERLETZT"])
        self.assertEqual([("FEHLER", "eigenschaft_verletzt")], [(b.schwere, b.kennung) for b in befunde])


# ---------------------------------------------------------------------------
class ZusammenfassungTests(unittest.TestCase):

    def test_pruefe_alles_nennt_was_geprueft_wurde(self) -> None:
        erg = bd.pruefe_alles(abstuerze=bd.Absturzlage(), doktor=["[ ok ] x"])
        self.assertEqual(["Abstürze und Fangnetze", "Doktor"], erg.geprueft)
        self.assertEqual([], erg.befunde)
        self.assertEqual([], bd.pruefe_alles().geprueft, "ohne jede Messung steht dort nichts")

    def test_befunde_sind_nach_schwere_sortiert(self) -> None:
        erg = bd.pruefe_alles(doktor=["[ !! ] a", "[FEHL] b"], abstuerze=bd.Absturzlage(absturzdatei_bytes=1))
        self.assertEqual(["FEHLER", "WARNUNG", "HINWEIS"], [b.schwere for b in erg.befunde])

    def test_zeilen_ohne_befund_und_mit_befund(self) -> None:
        sauber = bd.bericht_zeilen(bd.pruefe_alles(abstuerze=bd.Absturzlage()))
        self.assertEqual("Betrieb: keine Auffälligkeit", sauber[0])
        self.assertIn("geprüft: Abstürze und Fangnetze", sauber[1])
        self.assertEqual(2, len(sauber))
        mit = bd.bericht_zeilen(bd.pruefe_alles(doktor=["[FEHL] kaputt"]))
        self.assertEqual("Betrieb: 1 x FEHLER", mit[0])
        self.assertTrue(mit[-1].startswith("FEHLER [doktor_fehler]"))

    def test_leere_messung_sagt_es_ausdruecklich(self) -> None:
        self.assertIn("nichts (keine Messung möglich)", bd.bericht_zeilen(bd.pruefe_alles())[1])

    def test_gesamturteil_zaehlt_darstellung_und_betrieb(self) -> None:
        darstellung = ad.Pruefergebnis([ad.Befund(ad.WARNUNG, "x", "y")])
        betrieb = bd.pruefe_alles(doktor=["[FEHL] a", "[ !! ] b"])
        self.assertEqual("Gesamt: 1 x FEHLER, 1 x WARNUNG, 1 x HINWEIS (Darstellung 1, Betrieb 2)",
                         bd.gesamturteil(darstellung, betrieb))
        self.assertEqual("Gesamt: keine Auffälligkeit (Darstellung und Betrieb geprüft)",
                         bd.gesamturteil(ad.Pruefergebnis(), bd.pruefe_alles()))

    def test_sauber_zaehlt_hinweise_nicht(self) -> None:
        hinweis = bd.pruefe_alles(doktor=["[ !! ] nur ein Hinweis"])
        self.assertTrue(bd.sauber(ad.Pruefergebnis(), hinweis))
        warnung = bd.pruefe_alles(abstuerze=bd.Absturzlage(absturzdatei_bytes=1))
        self.assertFalse(bd.sauber(ad.Pruefergebnis(), warnung))
        self.assertFalse(bd.sauber(ad.Pruefergebnis([ad.Befund(ad.FEHLER, "x", "y")]), bd.pruefe_alles()))

    def test_uebersetzte_vorlagen_gelten_kaputte_fallen_zurueck(self) -> None:
        betrieb = bd.pruefe_alles(doktor=["[FEHL] a"])
        self.assertEqual("Operation: 1 x ERROR", bd.zusammenfassung(
            betrieb, {"betrieb_zaehlung": "Operation: {teile}", "betrieb_anzahl": "{anzahl} x {schwere}",
                      "schwere_fehler": "ERROR"}))
        self.assertEqual("Betrieb: 1 x FEHLER", bd.zusammenfassung(betrieb, {"betrieb_zaehlung": "kaputt {falsch}"}))

    def test_jede_kopfzeile_ist_in_allen_sprachen_uebersetzt(self) -> None:
        for kennung in bd.MELDUNGEN:
            with self.subTest(kennung=kennung):
                eintrag = STRINGS["betrieb." + kennung]
                self.assertEqual(set(bd.SPRACHEN), set(eintrag))
                for sprache in bd.SPRACHEN:
                    self.assertTrue(eintrag[sprache].strip())
        self.assertIn("diagnostics.report_section_betrieb", STRINGS)


# ---------------------------------------------------------------------------
class LaufwerkeTests(unittest.TestCase):
    """Liegengebliebene OSFMount-/Dokan-Laufwerke (04.11.2026: X:, Y:, Z: und W: standen nach Abbruechen im Explorer)."""

    def test_keine_laufwerke_kein_befund(self) -> None:
        self.assertEqual([], bd.pruefe_laufwerke(bd.Laufwerkslage()))

    def test_laeuft_eine_aufgabe_gehoeren_die_laufwerke_zu_ihr(self) -> None:
        lage = bd.Laufwerkslage((("W", bd.ART_DOKAN),), arbeit_laeuft=True)
        self.assertEqual([], bd.pruefe_laufwerke(lage))

    def test_befund_nennt_buchstaben_und_den_weg_zum_aushaengen(self) -> None:
        lage = bd.Laufwerkslage((("X", bd.ART_OSFMOUNT), ("Y", bd.ART_OSFMOUNT), ("W", bd.ART_DOKAN)))
        befunde = bd.pruefe_laufwerke(lage)
        self.assertEqual(1, len(befunde))
        self.assertEqual(bd.HINWEIS, befunde[0].schwere, "Ob jemand das Abbild bewusst einhaengte, sieht man nicht")
        text = befunde[0].text
        for stueck in ("3 eingehängte", "X: (OSFMount-Abbild)", "Y: (OSFMount-Abbild)", "W: (UFS2 über Dokan)",
                       "OSFMount.com -d -m X:", "dokanctl /u W"):
            self.assertIn(stueck, text)

    @unittest.skipUnless(sys.platform == "win32", "Laufwerke gibt es hier nur unter Windows")
    def test_die_messung_liefert_nur_buchstaben_mit_bekannter_art(self) -> None:
        lage = bd.laufwerke_messen()
        for buchstabe, art in lage.laufwerke:
            self.assertRegex(buchstabe, r"^[D-Z]$")
            self.assertIn(art, (bd.ART_OSFMOUNT, bd.ART_DOKAN))

    def test_waehrend_einer_aufgabe_wird_nicht_gemessen(self) -> None:
        self.assertEqual((), bd.laufwerke_messen(arbeit_laeuft=True).laufwerke)


# ---------------------------------------------------------------------------
class AnschlussTests(unittest.TestCase):
    """Der Bericht des Programms: Gesamturteil oben, Abschnitt "Betriebspruefung", keine doppelte Arbeit."""

    @classmethod
    def setUpClass(cls) -> None:
        import tkinter as tk  # noqa: PLC0415
        import PS5ImageConverter_Pro_FINAL_revised as app_modul  # noqa: PLC0415
        cls.wurzel = tk._default_root or tk.Tk()
        cls.wurzel.withdraw()
        cls.app = app_modul.PS5ConverterGUI(cls.wurzel)
        cls.app._current_language = "de"

    @unittest.skipUnless(sys.platform == "win32", "GDI/USER-Objekte gibt es nur unter Windows")
    def test_gdi_und_user_objekte_eines_prozesses_mit_fenster_werden_gemessen(self) -> None:
        """Mit einem Fenster hat der Prozess GDI- und USER-Objekte; 0 hiesse, dass die Messung still ausfaellt."""
        self.wurzel.update_idletasks()
        lage = bd.ressourcen_messen()
        self.assertGreater(lage.gdi, 0)
        self.assertGreater(lage.user, 0)

    def test_die_betriebspruefung_laeuft_und_prueft_alles(self) -> None:
        erg = self.app._betrieb_pruefen()
        self.assertEqual(15, len(erg.geprueft), erg.geprueft)
        self.assertIn("eingehängte Laufwerke", erg.geprueft)
        self.assertIs(erg, self.app._letzte_betrieb_pruefung)

    def test_der_bericht_hat_gesamturteil_und_abschnitt(self) -> None:
        text = self.app._build_diagnostic_report_text()
        zeilen = text.splitlines()
        darstellung = next(i for i, z in enumerate(zeilen) if z.startswith("Darstellung:"))
        self.assertTrue(zeilen[darstellung + 1].startswith("Gesamt:"), zeilen[darstellung:darstellung + 3])
        self.assertIn(self.app._t("diagnostics.report_section_betrieb"), zeilen)
        self.assertEqual(1, sum(1 for z in zeilen if z.startswith("geprüft: ")))

    def test_ein_nackter_bericht_hat_den_abschnitt_nicht(self) -> None:
        """Gegenprobe: ohne Rueckruf aendert sich am Bericht nichts (die alten Tests bauen so)."""
        from ps5_validator.utils.diagnose_befund import Diagnosebericht  # noqa: PLC0415
        text = Diagnosebericht().bericht_text()
        self.assertNotIn("Betriebsprüfung", text)
        self.assertNotIn("Gesamt:", text)

    def test_doktor_und_co_laufen_im_bericht_nur_einmal(self) -> None:
        with mock.patch.object(type(self.app), "_diagnose_doktor", autospec=True,
                               side_effect=lambda s: ["[ ok ] x"]) as doktor:
            self.app._build_diagnostic_report_text()
        self.assertEqual(1, doktor.call_count)

    def test_orbispkgtool_fehlt_unter_linux_und_mac_ohne_warnung_im_programm(self) -> None:
        """Der Weg des Programms (nicht nur der reinen Messung): ``_betrieb_pruefen`` darf dort nichts melden."""
        from ps5_validator.utils import orbispkg  # noqa: PLC0415

        class _MacSys:
            """``sys`` aus Sicht der Betriebsdiagnose: nur ``platform`` weicht ab (der Rest bleibt echt)."""
            platform = "darwin"

            def __getattr__(self, name):
                return getattr(sys, name)

        with mock.patch.object(orbispkg, "werkzeug_finden", return_value=""):
            unter_windows = self.app._betrieb_pruefen() if sys.platform == "win32" else None
            with mock.patch.object(bd, "sys", _MacSys()):
                unter_mac = self.app._betrieb_pruefen()
        self.assertFalse([b for b in unter_mac.befunde if "OrbisPkgTool" in b.text], unter_mac.befunde)
        if unter_windows is not None:
            self.assertTrue([b for b in unter_windows.befunde if "OrbisPkgTool" in b.text],
                            "Gegenprobe: Unter Windows muss das Fehlen auffallen.")

    def test_ein_verwaister_prozess_wird_im_bericht_gemeldet(self) -> None:
        lage = bd.Ressourcenlage(werkzeuge=("orbispkgtool",))
        with mock.patch.object(bd, "ressourcen_messen", return_value=lage):
            erg = self.app._betrieb_pruefen()
        self.assertIn("prozess_verwaist", [b.kennung for b in erg.befunde])


if __name__ == "__main__":
    unittest.main()
