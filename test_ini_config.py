"""Tests fuer ps5_validator.utils.ini_config (flaches key=value-INI-Format)."""
import unittest

from ps5_validator.utils.ini_config import (
    mehrfach_schluessel,
    merge_flat_ini,
    parse_flat_ini,
    render_flat_ini,
)


class IniConfigTests(unittest.TestCase):
    def test_parse_ignores_comments_and_blank_lines(self) -> None:
        text = "\n".join([
            "# comment", "; also a comment", "", "debug=1", "scan_depth=2",
        ])
        parsed = parse_flat_ini(text)
        self.assertEqual(parsed, {"debug": "1", "scan_depth": "2"})

    def test_parse_strips_whitespace_around_key_and_value(self) -> None:
        parsed = parse_flat_ini("  key  =  value with spaces  ")
        self.assertEqual(parsed, {"key": "value with spaces"})

    def test_parse_last_duplicate_key_wins(self) -> None:
        parsed = parse_flat_ini("debug=0\ndebug=1")
        self.assertEqual(parsed["debug"], "1")

    def test_render_skips_empty_values(self) -> None:
        text = render_flat_ini({"debug": "1", "empty": "", "none_value": None})
        self.assertIn("debug=1", text)
        self.assertNotIn("empty=", text)
        self.assertNotIn("none_value=", text)

    def test_render_with_header_comment(self) -> None:
        text = render_flat_ini({"debug": "1"}, header_comment="Generated\nDo not edit by hand")
        lines = text.splitlines()
        self.assertEqual(lines[0], "# Generated")
        self.assertEqual(lines[1], "# Do not edit by hand")
        self.assertIn("debug=1", lines)

    def test_roundtrip(self) -> None:
        data = {"a": "1", "b": "two words", "c": "3"}
        text = render_flat_ini(data)
        self.assertEqual(parse_flat_ini(text), data)


class MergeFlatIniTests(unittest.TestCase):
    """Zurückschreiben darf den Aufbau der Datei nicht zerstören.

    Die Konfigurationen auf der Konsole sind Vorlagen, in denen fast alles als
    Kommentar erklärt ist – `/data/shadowmount/config.ini` hat 146 Zeilen und
    keinen einzigen aktiven Eintrag. Ein Neuaufbau aus dem Wörterbuch hätte
    daraus drei Zeilen gemacht.
    """

    VORLAGE = (
        "# ShadowMount runtime config example\n"
        "#\n"
        "# 1. Uncomment only the parameters you really want to override.\n"
        "\n"
        "## scanpath=/data/homebrew\n"
        "# mount_timeout=15\n"
        "debug=1\n"
        "verbose=0\n"
    )

    def test_kommentare_und_leerzeilen_bleiben(self) -> None:
        ergebnis = merge_flat_ini(self.VORLAGE, {"debug": "1", "verbose": "0"})
        self.assertIn("# ShadowMount runtime config example", ergebnis)
        self.assertIn("## scanpath=/data/homebrew", ergebnis)
        self.assertIn("# mount_timeout=15", ergebnis)
        self.assertIn("", ergebnis.splitlines())

    def test_bestehender_wert_wird_geaendert(self) -> None:
        ergebnis = merge_flat_ini(self.VORLAGE, {"debug": "0", "verbose": "0"})
        self.assertIn("debug=0", ergebnis)
        self.assertNotIn("debug=1", ergebnis)

    def test_neuer_eintrag_wird_angehaengt(self) -> None:
        ergebnis = merge_flat_ini(self.VORLAGE, {"debug": "1", "verbose": "0", "mount_timeout": "30"},
                                  header_comment="Testlauf")
        self.assertIn("mount_timeout=30", ergebnis)
        self.assertIn("# Testlauf", ergebnis)
        # Die auskommentierte Vorlagenzeile bleibt daneben bestehen.
        self.assertIn("# mount_timeout=15", ergebnis)

    def test_entfernter_eintrag_wird_auskommentiert_nicht_geloescht(self) -> None:
        ergebnis = merge_flat_ini(self.VORLAGE, {"debug": "1"})
        self.assertIn("# verbose=0", ergebnis)
        self.assertNotIn("\nverbose=0", ergebnis)

    def test_geleerter_wert_wird_auskommentiert(self) -> None:
        ergebnis = merge_flat_ini(self.VORLAGE, {"debug": "", "verbose": "0"})
        self.assertIn("# debug=1", ergebnis)

    def test_ohne_aenderung_bleibt_die_datei_gleich(self) -> None:
        daten = parse_flat_ini(self.VORLAGE)
        ergebnis = merge_flat_ini(self.VORLAGE, daten)
        self.assertEqual(ergebnis.strip(), self.VORLAGE.strip())

    def test_reine_kommentardatei_verliert_nichts(self) -> None:
        """Der Fall der Konsole: Vorlage ohne einen einzigen aktiven Eintrag."""
        vorlage = "\n".join(f"# Zeile {i}" for i in range(1, 41)) + "\n"
        ergebnis = merge_flat_ini(vorlage, {"neuer_schluessel": "1"}, header_comment="Kopf")
        self.assertGreaterEqual(len(ergebnis.splitlines()), 41)
        self.assertIn("# Zeile 40", ergebnis)
        self.assertIn("neuer_schluessel=1", ergebnis)


class WiederholbareSchluesselTests(unittest.TestCase):
    """Ein Schluessel darf auf mehreren Zeilen stehen - und muss es bleiben.

    Die Anleitung von ShadowMount+ fuehrt sieben solche Schluessel, darunter
    ``scanpath``: "can be repeated on multiple lines". Ein Woerterbuch kann das
    nicht abbilden - :func:`parse_flat_ini` behaelt nur den letzten Wert.

    Bis zum 05.09.2026 schrieb :func:`merge_flat_ini` diesen einen Wert
    daraufhin in **jede** Zeile des Schluessels. Aus drei Suchpfaden wurde
    dreimal derselbe; die uebrigen waren nicht nur geloescht, sondern durch
    Dubletten ersetzt. Das wiegt schwer, weil dieselbe Anleitung sagt: "If at
    least one scanpath=... is present, only those custom paths are used" - an
    den verlorenen Orten sucht die Konsole also nie wieder.
    """

    VORLAGE = "\n".join([
        "# ShadowMount+",
        "scanpath=/mnt/usb0",
        "scanpath=/mnt/usb1",
        "scanpath=/data/spiele",
        "image_ro=Spiel.ffpkg",
        "image_ro=Anderes.ffpkg",
        "api_port=9021",
    ])

    def test_mehrfache_werden_erkannt(self) -> None:
        self.assertEqual({"scanpath", "image_ro"},
                         mehrfach_schluessel(self.VORLAGE))

    def test_einfache_gelten_nicht_als_mehrfach(self) -> None:
        """Sonst waere gleich die halbe Datei unveraenderlich."""
        self.assertNotIn("api_port", mehrfach_schluessel(self.VORLAGE))

    def test_auskommentierte_zaehlen_nicht(self) -> None:
        """Die Vorlage der Konsole fuehrt Beispiele als Kommentar - dreimal
        ``## scanpath=...`` macht den Schluessel nicht wiederholt."""
        text = "scanpath=/mnt/usb0\n# scanpath=/data/homebrew\n; scanpath=/x"
        self.assertEqual(set(), mehrfach_schluessel(text))

    def test_alle_zeilen_ueberleben_das_zurueckschreiben(self) -> None:
        daten = parse_flat_ini(self.VORLAGE)
        daten["api_port"] = "9099"          # eine echte Aenderung daneben
        ergebnis = merge_flat_ini(self.VORLAGE, daten)
        self.assertEqual(
            ["scanpath=/mnt/usb0", "scanpath=/mnt/usb1", "scanpath=/data/spiele"],
            [z for z in ergebnis.splitlines() if z.startswith("scanpath=")],
            "Die Suchpfade wurden veraendert - an den verlorenen Orten sucht "
            "die Konsole nie wieder.")
        self.assertEqual(
            ["image_ro=Spiel.ffpkg", "image_ro=Anderes.ffpkg"],
            [z for z in ergebnis.splitlines() if z.startswith("image_ro=")])
        # Was einfach dasteht, muss weiterhin aenderbar sein.
        self.assertIn("api_port=9099", ergebnis)

    def test_auch_ein_geaenderter_wert_richtet_keinen_schaden_an(self) -> None:
        """Der Editor zeigt nur einen Wert - was der Anwender damit tut, darf
        die uebrigen Zeilen nicht treffen."""
        daten = parse_flat_ini(self.VORLAGE)
        daten["scanpath"] = "/etwas/ganz/anderes"
        ergebnis = merge_flat_ini(self.VORLAGE, daten)
        self.assertNotIn("/etwas/ganz/anderes", ergebnis)
        self.assertEqual(
            3, len([z for z in ergebnis.splitlines() if z.startswith("scanpath=")]))


if __name__ == "__main__":
    unittest.main()
