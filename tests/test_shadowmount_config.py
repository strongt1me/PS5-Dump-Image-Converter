# -*- coding: utf-8 -*-
"""ShadowMount+ ab 1.7beta12: config.ini in Abschnitten + profiles.ini (Format 2).

Der Anlass (Nutzerwunsch 09.11.2026): "In der neuen Version von ShadowMount+ 1.7beta12 wird auch etwas an der
config.ini geaendert - das Programm soll fragen, welche Version laeuft, damit die config.ini korrekt behandelt
wird." Das Programm denkt in den Schluesseln der alten Fassungen; ``shadowmount_config`` uebersetzt an der
Dateigrenze: ``ansicht`` (Format 2 -> flacher Text in alten Schluesseln) und ``zurueckschreiben`` (nur die
Unterschiede zurueck ins Format 2, Kommentare und Unbekanntes bleiben).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import shadowmount_config as sc    # noqa: E402
from ps5_validator.utils.ini_config import parse_flat_ini, parse_flat_ini_multi   # noqa: E402

#: Verkuerzte Vorlage im Aufbau der config.ini.example von 1.7beta12 (alles ausser [config] auskommentiert).
VORLAGE = """\
# ShadowMountPlus main configuration: /data/shadowmount/config.ini
# Keep [config] version. Uncomment only settings you want to override.

[config]
version = 2

[general]
# Debug output to console and /data/shadowmount/debug.log.
# debug = on
# language = auto

[scan]
# depth = 1
# path = /data/homebrew
# path = /data/etaHEN/games

[mount]
# mode = ro

[emulators]
# Replace matching cached game fakelib files from path; excludes fakelib2 and PKGs.
# update_enabled = on
# path = /data/shadowmount/emus
"""

#: Eine benutzte Datei: einige Schluessel aktiv, zwei Suchpfade, ein Kommentar am Zeilenende, eine SMB-Verbindung.
BENUTZT = """\
[config]
version = 2

[general]
debug = on   # fuer die Fehlersuche
language = "de-DE"

[scan]
depth = 2
path = /data/homebrew
path = /mnt/usb0

[mount]
mode = ro

[fakelib]
enabled = on
global_priority = game

[emulators]
update_enabled = on
path = /data/shadowmount/emus

[smb:NAS]
path = smb://192.168.1.10/games
username = "user"
active = on
"""

PROFILE = """\
[config]
version = 2

[game:PPSA13197]
fakelib = emulators
ignore_global_fakelib = on

[image:Spiel [v1].exfat]
mount_mode = rw
sector_size = 4096
"""


class ErkennenTests(unittest.TestCase):
    def test_vorlage_und_benutzte_datei_sind_format_2(self) -> None:
        self.assertEqual(sc.FORMAT_V2, sc.format_erkennen(VORLAGE))
        self.assertEqual(sc.FORMAT_V2, sc.format_erkennen(BENUTZT))

    def test_flache_schluessel_sind_format_1(self) -> None:
        self.assertEqual(sc.FORMAT_V1, sc.format_erkennen("debug=1\nscanpath=/data/homebrew\n"))
        self.assertEqual(sc.FORMAT_V1, sc.format_erkennen("# Kommentar\n\nupdate_emulators = 0\n"))

    def test_leer_oder_nur_kommentare_beweist_nichts(self) -> None:
        for text in ("", "   \n", "# debug=1\n# scanpath=/data/homebrew\n", "; nur ein Kommentar\n"):
            with self.subTest(text=text):
                self.assertEqual("", sc.format_erkennen(text))

    def test_ein_auskommentierter_kopf_zaehlt_nicht(self) -> None:
        self.assertEqual("", sc.format_erkennen("# [smb:NAS]\n# path = smb://x\n"))


class AnsichtTests(unittest.TestCase):
    def test_die_benutzte_datei_in_alten_schluesseln(self) -> None:
        erwartet = "\n".join([
            sc.ANSICHT_MARKE,
            "debug=on",
            "language=de-DE",
            "scan_depth=2",
            "scanpath=/data/homebrew",
            "scanpath=/mnt/usb0",
            "mount_read_only=1",
            "backport_fakelib=on",
            "global_fakelib_priority=game",
            "update_emulators=on",
            "emulators_path=/data/shadowmount/emus",
            "",
        ])
        self.assertEqual(erwartet, sc.ansicht(BENUTZT))

    def test_profile_werden_zu_den_alten_zeilen(self) -> None:
        zeilen = sc.ansicht("", PROFILE).splitlines()
        self.assertIn("fakelib_mode=PPSA13197:emulators", zeilen)
        self.assertIn("global_fakelib_exclude=PPSA13197", zeilen)
        self.assertIn("image_rw=Spiel [v1].exfat", zeilen)
        self.assertIn("image_sector=Spiel [v1].exfat:4096", zeilen)

    def test_die_vorlage_zeigt_nichts_aktives(self) -> None:
        self.assertEqual(sc.ANSICHT_MARKE + "\n", sc.ansicht(VORLAGE))

    def test_smb_und_kommentare_kommen_nicht_vor(self) -> None:
        text = sc.ansicht(BENUTZT)
        self.assertNotIn("smb", text)
        self.assertNotIn("fuer die Fehlersuche", text)

    def test_die_ansicht_laesst_sich_wie_die_alte_datei_lesen(self) -> None:
        werte = parse_flat_ini(sc.ansicht(BENUTZT))
        self.assertEqual("on", werte["update_emulators"])
        self.assertEqual(["/data/homebrew", "/mnt/usb0"], parse_flat_ini_multi(sc.ansicht(BENUTZT))["scanpath"])


class RundlaufTests(unittest.TestCase):
    def test_unveraenderte_ansicht_aendert_nichts(self) -> None:
        config, profile, uebergangen = sc.zurueckschreiben(sc.ansicht(BENUTZT, PROFILE), BENUTZT, PROFILE)
        self.assertEqual((BENUTZT, PROFILE, []), (config, profile, uebergangen))

    def test_ein_wert_aendern_laesst_den_rest_wortgleich(self) -> None:
        neu = sc.ansicht(BENUTZT).replace("update_emulators=on", "update_emulators=0")
        config, _profile, uebergangen = sc.zurueckschreiben(neu, BENUTZT)
        self.assertEqual([], uebergangen)
        self.assertEqual(BENUTZT.replace("update_enabled = on", "update_enabled = off"), config)

    def test_auskommentierte_vorlage_wird_scharf_geschaltet(self) -> None:
        neu = sc.ansicht(VORLAGE) + "update_emulators=0\n"
        config, _p, _u = sc.zurueckschreiben(neu, VORLAGE)
        zeilen = config.splitlines()
        self.assertIn("update_enabled = off", zeilen)
        self.assertIn("# update_enabled = on", zeilen, "die Vorlage bleibt als Erklaerung stehen")
        self.assertEqual(zeilen.index("# update_enabled = on") + 1, zeilen.index("update_enabled = off"))
        self.assertEqual(sc.FORMAT_V2, sc.format_erkennen(config))
        self.assertEqual("off", parse_flat_ini(sc.ansicht(config))["update_emulators"])

    def test_schluessel_ohne_vorlage_landet_am_ende_seines_abschnitts(self) -> None:
        neu = sc.ansicht(BENUTZT) + "api_port=10102\n"
        config, _p, _u = sc.zurueckschreiben(neu, BENUTZT)
        self.assertIn("[api]\nport = 10102", config, "fehlender Abschnitt wird angelegt")
        self.assertTrue(config.index("[api]") > config.index("path = /data/shadowmount/emus"))

    def test_scanpfade_hinzufuegen_und_entfernen(self) -> None:
        mehr = sc.ansicht(BENUTZT) + "scanpath=/mnt/usb1\n"
        config, _p, _u = sc.zurueckschreiben(mehr, BENUTZT)
        self.assertEqual(["/data/homebrew", "/mnt/usb0", "/mnt/usb1"],
                         parse_flat_ini_multi(sc.ansicht(config))["scanpath"])
        weniger = sc.ansicht(BENUTZT).replace("scanpath=/data/homebrew\n", "")
        config2, _p, _u = sc.zurueckschreiben(weniger, BENUTZT)
        self.assertEqual(["/mnt/usb0"], parse_flat_ini_multi(sc.ansicht(config2))["scanpath"])
        self.assertIn("# path = /mnt/usb0", config2, "die uebrig gebliebene Zeile ist auskommentiert, nicht geloescht")

    def test_nur_lesen_und_schreibend_beim_einhaengen(self) -> None:
        neu = sc.ansicht(BENUTZT).replace("mount_read_only=1", "mount_read_only=0")
        config, _p, _u = sc.zurueckschreiben(neu, BENUTZT)
        self.assertIn("mode = rw", config)
        self.assertEqual("0", parse_flat_ini(sc.ansicht(config))["mount_read_only"])

    def test_werte_mit_raute_werden_in_anfuehrungszeichen_geschrieben(self) -> None:
        neu = sc.ansicht(BENUTZT).replace("language=de-DE", "language=a # b")
        config, _p, _u = sc.zurueckschreiben(neu, BENUTZT)
        self.assertIn('language = "a # b"', config)
        self.assertEqual("a # b", parse_flat_ini(sc.ansicht(config))["language"])

    def test_alles_andere_bleibt_stehen_smb_und_kommentar(self) -> None:
        neu = sc.ansicht(BENUTZT).replace("scan_depth=2", "scan_depth=1")
        config, _p, _u = sc.zurueckschreiben(neu, BENUTZT)
        self.assertIn("[smb:NAS]\npath = smb://192.168.1.10/games", config)
        self.assertIn("debug = on   # fuer die Fehlersuche", config)

    def test_neue_datei_bekommt_kopf_und_abschnitte(self) -> None:
        config, profile, _u = sc.zurueckschreiben("update_emulators=0\nscanpath=/data/homebrew\n", "", "")
        self.assertTrue(config.startswith("[config]\nversion = 2\n"))
        self.assertIn("[emulators]\nupdate_enabled = off", config)
        self.assertEqual("", profile, "ohne Profil-Aenderung wird profiles.ini nicht angelegt")

    def test_zeilenenden_der_datei_bleiben(self) -> None:
        crlf = BENUTZT.replace("\n", "\r\n")
        neu = sc.ansicht(crlf).replace("update_emulators=on", "update_emulators=0")
        config, _p, _u = sc.zurueckschreiben(neu, crlf)
        self.assertNotIn("\n\n", config.replace("\r\n", "\x00"))
        self.assertEqual(config.count("\r\n"), config.count("\n"))

    def test_schluessel_die_es_nicht_mehr_gibt_werden_gemeldet_nicht_geschrieben(self) -> None:
        neu = sc.ansicht(BENUTZT) + "kstuff_delay=5\n"
        config, _p, uebergangen = sc.zurueckschreiben(neu, BENUTZT)
        self.assertEqual(["kstuff_delay"], uebergangen)
        self.assertNotIn("kstuff", config)


class ProfilTests(unittest.TestCase):
    def test_modus_fuer_ein_spiel_anlegen_aendern_entfernen(self) -> None:
        neu = sc.ansicht("", PROFILE) + "fakelib_mode=PPSA00001:disabled\n"
        _c, profile, _u = sc.zurueckschreiben(neu, "", PROFILE)
        self.assertIn("[game:PPSA00001]\nfakelib = disabled", profile)
        geaendert = sc.ansicht("", profile).replace("PPSA13197:emulators", "PPSA13197:full")
        _c, profile2, _u = sc.zurueckschreiben(geaendert, "", profile)
        self.assertIn("fakelib = full", profile2)
        weg = sc.ansicht("", profile2).replace("fakelib_mode=PPSA00001:disabled\n", "")
        _c, profile3, _u = sc.zurueckschreiben(weg, "", profile2)
        self.assertIn("# fakelib = disabled", profile3)
        self.assertNotIn("PPSA00001:disabled", sc.ansicht("", profile3))

    def test_globale_fakelib_je_spiel_abschalten(self) -> None:
        neu = sc.ansicht("", "") + "global_fakelib_exclude=PPSA12345\n"
        _c, profile, _u = sc.zurueckschreiben(neu, "", "")
        self.assertIn("[game:PPSA12345]\nignore_global_fakelib = on", profile)
        self.assertTrue(profile.startswith("[config]\nversion = 2\n"))

    def test_alter_name_fakelib_exclude_wird_zu_disabled(self) -> None:
        neu = sc.ansicht("", "") + "fakelib_exclude=PPSA99999\n"
        _c, profile, _u = sc.zurueckschreiben(neu, "", "")
        self.assertIn("[game:PPSA99999]\nfakelib = disabled", profile)

    def test_abbilder_modus_und_sektorgroesse(self) -> None:
        neu = sc.ansicht("", "") + "image_ro=Test.exfat\nimage_sector=Test.exfat:512\n"
        _c, profile, _u = sc.zurueckschreiben(neu, "", "")
        self.assertIn("[image:Test.exfat]\nmount_mode = ro\nsector_size = 512", profile)

    def test_gross_klein_beim_titel_wird_nicht_doppelt_angelegt(self) -> None:
        neu = sc.ansicht("", PROFILE) + "fakelib_mode=ppsa13197:disabled\n"
        _c, profile, _u = sc.zurueckschreiben(neu, "", PROFILE)
        self.assertEqual(1, profile.lower().count("[game:ppsa13197]"))


class TextTests(unittest.TestCase):
    def test_meldungstexte_bekommen_die_neuen_namen(self) -> None:
        self.assertEqual("Stelle in der config.ini [emulators] update_enabled=0 ein.",
                         sc.uebersetzen("Stelle in der config.ini update_emulators=0 ein."))

    def test_gewoehnliche_woerter_bleiben(self) -> None:
        text = "Das debug.log zeigt die language und den Debug-Bau."
        self.assertEqual(text, sc.uebersetzen(text))

    def test_laengere_namen_werden_nicht_zerrissen(self) -> None:
        self.assertEqual("profiles.ini [game:ID] ignore_global_fakelib", sc.uebersetzen("global_fakelib_exclude"))
        self.assertEqual("[fakelib] global_enabled", sc.uebersetzen("global_fakelib"))

    def test_anzeigename_und_tabelle(self) -> None:
        self.assertEqual("[scan] path", sc.anzeigename("scanpath"))
        self.assertEqual("unbekannt", sc.anzeigename("unbekannt"))
        alt = [a for a, _s, _n in sc.SCHLUESSEL]
        self.assertEqual(len(alt), len(set(alt)), "jeder alte Schluessel nur einmal")
        neu = [(s, n) for _a, s, n in sc.SCHLUESSEL]
        self.assertEqual(len(neu), len(set(neu)), "jedes Paar Abschnitt/Schluessel nur einmal")
        self.assertEqual(36, len(sc.SCHLUESSEL), "sm_config_keys[] von 1.7beta12 hat 36 Eintraege")


if __name__ == "__main__":
    unittest.main()
