"""Die Ablagewege von ShadowMountPlus - Global, Emulatoren, pro Spiel.

ShadowMountPlus liest Bibliotheken aus drei Quellen, und sie verhalten sich
nicht gleich. Bis v1.8.98 kannte das Programm nur die erste:

* **pro Spiel** - `<Spiel>/fakelib` oder `<scanpath>/backports/<TID>/fakelib*`.
* **global** - der Ordner aus `global_fakelib_path`, voreingestellt
  `/data/shadowmount/fakelib`. Er gilt fuer jedes erfasste Spiel; ab alpha8
  wird er vollstaendig in den Cache kopiert (`copy_dir_with_mode` in
  `sm_fakelib.c`), es kommen also auch neue Dateien hinzu.
* **Emulatoren** - der Ordner aus `emulators_path`, erst ab 1.7 alpha8. Hier
  gilt eine Einschraenkung, die man leicht uebersieht: In
  `copy_emulator_files_to_cache` steht vor dem Kopieren

      if (stat(source_file, &source_st) != 0 || !S_ISREG(source_st.st_mode))
        continue;

  Eine Datei wird also nur uebernommen, wenn es sie im fakelib des Spiels
  **schon gibt**. Wer `libSceAmpr.sprx` allein dorthin legt, aendert bei einem
  Spiel ohne diese Bibliothek gar nichts - ohne jede Meldung.

Belege: `config.ini.example` und `src/sm_fakelib.c` aus
`PS5 SDK usw/ShadowMountPlus-1.7alpha6` bzw. `-1.7alpha8`.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI
from ps5_validator.utils import shadowmount_generation as sg

QUELLE = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
    encoding="utf-8")


def _gui(gemerkt: str = "auto") -> PS5ConverterGUI:
    """Prueflings-Instanz mit festgelegter Einstellung.

    ``_load_setting`` wird abgefangen: Sonst laese der Test die echte
    paths.json des Nutzers, und das Ergebnis haenge daran, was dort steht.
    """
    gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
    gui._t = lambda schluessel, **kw: schluessel
    gui._append_to_log = lambda *_a, **_k: None
    gui._load_setting = lambda schluessel, vorgabe: (
        gemerkt if schluessel == "ampr_ablage" else vorgabe)
    return gui


class ReferenzTests(unittest.TestCase):
    """Was die Anleitungen sagen - nachgebildet im Referenzmodul."""

    def test_die_alte_fassung_kennt_keine_emulatoren(self) -> None:
        kennungen = [o["kennung"] for o in sg.orte(sg.ALT)]
        self.assertNotIn(sg.ORT_EMUS, kennungen)
        self.assertIn(sg.ORT_GLOBAL, kennungen)

    def test_die_neue_fassung_kennt_alle_vier(self) -> None:
        kennungen = [o["kennung"] for o in sg.orte(sg.NEU)]
        for erwartet in (sg.ORT_BACKPORT, sg.ORT_SPIEL, sg.ORT_GLOBAL,
                         sg.ORT_EMUS):
            with self.subTest(ort=erwartet):
                self.assertIn(erwartet, kennungen)

    def test_globaler_ordner_ist_der_standardpfad(self) -> None:
        for generation in (sg.ALT, sg.NEU):
            with self.subTest(generation=generation):
                ziel = sg.ablageziel(generation, sg.ORT_GLOBAL)
                self.assertEqual(ziel["pfad"], "/data/shadowmount/fakelib")
                self.assertTrue(ziel["wirkt"])

    def test_ein_eigener_pfad_aus_der_config_gewinnt(self) -> None:
        """Steht in der config.ini ein anderer Ordner, gilt der."""
        ziel = sg.ablageziel(sg.NEU, sg.ORT_GLOBAL, pfad="/mnt/usb0/fakelib")
        self.assertEqual(ziel["pfad"], "/mnt/usb0/fakelib")

    def test_emulatoren_wirken_in_der_alten_fassung_nicht(self) -> None:
        """Sonst legte man Dateien ab, die niemand liest."""
        ziel = sg.ablageziel(sg.ALT, sg.ORT_EMUS)
        self.assertFalse(ziel["wirkt"])
        self.assertIn("alpha8", ziel["hinweis"])

    def test_emulatoren_nennen_ihre_einschraenkung(self) -> None:
        """Nur gleichnamige Dateien werden ersetzt - das muss dastehen."""
        ziel = sg.ablageziel(sg.NEU, sg.ORT_EMUS)
        self.assertEqual(ziel["pfad"], "/data/shadowmount/emus")
        self.assertIn("schon liegen", ziel["hinweis"])

    def test_feste_orte_haben_keinen_unterordner(self) -> None:
        """Ein Name hier hiesse: eine Ebene zu tief ablegen."""
        for ort in (sg.ORT_GLOBAL, sg.ORT_EMUS):
            with self.subTest(ort=ort):
                with self.assertRaises(ValueError):
                    sg.ablageordner(sg.NEU, ort)

    def test_jeder_weg_nennt_seinen_schalter(self) -> None:
        self.assertIn("global_fakelib",
                      sg.config_schluessel_fuer(sg.NEU, sg.ORT_GLOBAL))
        self.assertIn("update_emulators",
                      sg.config_schluessel_fuer(sg.NEU, sg.ORT_EMUS))
        # Die alte Fassung hat den Schalter nicht - also auch keinen Namen.
        self.assertEqual((), sg.config_schluessel_fuer(sg.ALT, sg.ORT_EMUS))

    def test_ein_unterordner_im_globalen_ordner_wird_beanstandet(self) -> None:
        meldungen = sg.beanstandungen(sg.NEU, sg.ORT_GLOBAL, ["fakelib"])
        self.assertTrue(meldungen)
        self.assertIn("direkt", meldungen[0])


class WahlTests(unittest.TestCase):
    """Die gemerkte Wahl - und was bei Unsinn passiert."""

    def test_vorgabe_ist_pro_spiel(self) -> None:
        self.assertEqual(_gui("auto")._ampr_ablage_wahl(),
                         PS5ConverterGUI.ABLAGE_AUTO)

    def test_gemerkte_wahl_wird_gelesen(self) -> None:
        self.assertEqual(_gui("global")._ampr_ablage_wahl(), sg.ORT_GLOBAL)
        self.assertEqual(_gui("emus")._ampr_ablage_wahl(), sg.ORT_EMUS)

    def test_unbekannter_wert_faellt_zurueck(self) -> None:
        """Eine Datei aus einer neueren Fassung darf nichts sprengen."""
        self.assertEqual(_gui("mondschein")._ampr_ablage_wahl(),
                         PS5ConverterGUI.ABLAGE_AUTO)

    def test_ohne_leser_gilt_die_vorgabe(self) -> None:
        """Halb aufgebaute Instanz - kein AttributeError."""
        gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
        self.assertEqual(gui._ampr_ablage_wahl(), PS5ConverterGUI.ABLAGE_AUTO)

    def test_unsinn_wird_nicht_gemerkt(self) -> None:
        geschrieben: list[tuple] = []
        gui = _gui()
        gui._save_setting = lambda k, v: geschrieben.append((k, v))
        gui._ampr_ablage_merken("mondschein")
        self.assertEqual(geschrieben, [])
        gui._ampr_ablage_merken(sg.ORT_GLOBAL)
        self.assertEqual(geschrieben, [("ampr_ablage", sg.ORT_GLOBAL)])


class ConfigPfadTests(unittest.TestCase):
    """Den Ordner aus der config.ini herauslesen."""

    def test_leerer_text_heisst_standard(self) -> None:
        gui = _gui()
        self.assertEqual(gui._ampr_gen_config_pfad("", sg.ORT_GLOBAL), "")

    def test_auskommentierter_schluessel_zaehlt_nicht(self) -> None:
        """ShadowMountPlus liefert die Datei komplett auskommentiert aus."""
        gui = _gui()
        text = "# global_fakelib_path=/data/shadowmount/fakelib\n"
        self.assertEqual(gui._ampr_gen_config_pfad(text, sg.ORT_GLOBAL), "")

    def test_gesetzter_schluessel_gewinnt(self) -> None:
        gui = _gui()
        text = "global_fakelib_path=/mnt/usb0/eigen\nemulators_path=/data/e\n"
        self.assertEqual(gui._ampr_gen_config_pfad(text, sg.ORT_GLOBAL),
                         "/mnt/usb0/eigen")
        self.assertEqual(gui._ampr_gen_config_pfad(text, sg.ORT_EMUS),
                         "/data/e")


class AblegenTests(unittest.TestCase):
    """Der lokale Weg - er fehlte bis v1.8.98 vollstaendig.

    ``_ampr_gen_automatik`` rief ``_ampr_gen_ablegen`` auf, aber die Methode
    gab es nicht. Wer ohne Konsole arbeitete, lief in einen AttributeError,
    den der Sammelfang als "fehlgeschlagen" meldete - abgelegt wurde nie
    etwas.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="ampr_ablegen_")
        self.wurzel = Path(self._tmp.name)
        self.quelle = self.wurzel / "quelle"
        self.quelle.mkdir()
        self.lib = self.quelle / "libSceAmpr.sprx"
        self.lib.write_bytes(b"AMPR-EMU-NEU")
        self.gui = _gui()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_die_methode_gibt_es_ueberhaupt(self) -> None:
        """Gegenprobe zum Fehler: der Aufruf darf nicht ins Leere gehen."""
        self.assertTrue(callable(getattr(PS5ConverterGUI,
                                         "_ampr_gen_ablegen", None)))
        self.assertIn("_ampr_gen_ablegen(", QUELLE)

    def test_dateien_landen_im_ziel(self) -> None:
        ziel = self.wurzel / "spiel" / "fakelib"
        zeilen = self.gui._ampr_gen_ablegen(
            sg.NEU, sg.ORT_SPIEL, lokal=True, ziel=str(ziel),
            dateien=[str(self.lib)])
        self.assertTrue((ziel / "libSceAmpr.sprx").is_file())
        self.assertEqual((ziel / "libSceAmpr.sprx").read_bytes(),
                         b"AMPR-EMU-NEU")
        self.assertTrue(any("placed" in z for z in zeilen))

    def test_ein_vorhandenes_original_wird_gesichert(self) -> None:
        ziel = self.wurzel / "spiel" / "fakelib"
        ziel.mkdir(parents=True)
        (ziel / "libSceAmpr.sprx").write_bytes(b"ORIGINAL")
        self.gui._ampr_gen_ablegen(sg.NEU, sg.ORT_SPIEL, lokal=True,
                                   ziel=str(ziel), dateien=[str(self.lib)])
        self.assertEqual((ziel / "libSceAmpr.sprx.orig").read_bytes(),
                         b"ORIGINAL")

    def test_die_sicherung_wird_nicht_ueberschrieben(self) -> None:
        """Sonst laege beim zweiten Lauf die Ersatzdatei als Original da."""
        ziel = self.wurzel / "spiel" / "fakelib"
        ziel.mkdir(parents=True)
        (ziel / "libSceAmpr.sprx").write_bytes(b"ORIGINAL")
        for _ in range(2):
            self.gui._ampr_gen_ablegen(sg.NEU, sg.ORT_SPIEL, lokal=True,
                                       ziel=str(ziel), dateien=[str(self.lib)])
        self.assertEqual((ziel / "libSceAmpr.sprx.orig").read_bytes(),
                         b"ORIGINAL")

    def test_der_ftp_weg_gehoert_nicht_hierher(self) -> None:
        with self.assertRaises(ValueError):
            self.gui._ampr_gen_ablegen(sg.NEU, sg.ORT_SPIEL, lokal=False,
                                       ziel=str(self.wurzel), dateien=[])


class AutomatikTests(unittest.TestCase):
    """Was der Quelltext der Automatik zusagt."""

    def _rumpf(self) -> str:
        anfang = QUELLE.index("def _ampr_gen_automatik(self")
        return QUELLE[anfang:QUELLE.index(chr(10) + "    def ", anfang + 10)]

    def test_der_gewaehlte_weg_wird_gelesen(self) -> None:
        self.assertIn("self._ampr_ablage_wahl()", self._rumpf())

    def test_ohne_konsole_bricht_ein_fester_weg_ab(self) -> None:
        """Global und Emulatoren sind Ordner auf der Konsole."""
        rumpf = self._rumpf()
        self.assertIn("amprgen.place_needs_console", rumpf)

    def test_die_spielwahl_wird_uebersprungen(self) -> None:
        rumpf = self._rumpf()
        self.assertIn("if lokal and not fester_weg:", rumpf)
        self.assertIn("elif not fester_weg:", rumpf)

    def test_die_config_wird_nur_einmal_gelesen(self) -> None:
        """Zweimal abholen kostet eine FTP-Runde und bringt nichts."""
        rumpf = self._rumpf()
        self.assertEqual(rumpf.count("self._ampr_gen_config_lesen(ftp)"), 1)

    def test_der_abgeschaltete_schalter_wird_gemeldet(self) -> None:
        self.assertIn("amprgen.place_key_off", self._rumpf())


class FensterTests(unittest.TestCase):
    """Was im rahmenlosen Auswahlfenster stehen muss."""

    def _rumpf(self) -> str:
        anfang = QUELLE.index("    def _show_ampr_auswahl(self)")
        return QUELLE[anfang:QUELLE.index(chr(10) + "    def ", anfang + 10)]

    def test_alle_drei_wege_stehen_zur_wahl(self) -> None:
        self.assertIn("self.ABLAGE_WEGE", self._rumpf())
        self.assertEqual(PS5ConverterGUI.ABLAGE_WEGE,
                         ("auto", sg.ORT_GLOBAL, sg.ORT_EMUS))

    def test_die_wahl_traegt_nicht_allein_ueber_farbe(self) -> None:
        """Sonst waere sie mit Farbsehschwaeche nicht zu erkennen.

        Der Haken darf im Quelltext als Zeichen oder als Escape stehen -
        gemeint ist dasselbe. Geprueft wird die Aussage, nicht die
        Schreibweise.
        """
        rumpf = self._rumpf()
        haken = "✓" in rumpf or chr(92) + "u2713" in rumpf
        self.assertTrue(haken, "Der gewaehlte Weg traegt nur ueber die Farbe")

    def test_beide_anleitungen_sind_verknuepft(self) -> None:
        self.assertIn("self._show_ampr_anleitung(g)", self._rumpf())
        for generation in (sg.ALT, sg.NEU):
            with self.subTest(generation=generation):
                self.assertIn(generation, PS5ConverterGUI._AMPR_ANLEITUNGEN)


class AnleitungTests(unittest.TestCase):
    """Die mitgelieferten Anleitungen."""

    def test_die_alte_anleitung_liegt_im_repo(self) -> None:
        name = PS5ConverterGUI._AMPR_ANLEITUNGEN[sg.ALT]
        self.assertTrue((PROJEKT / "Anleitungen" / name).is_file(),
                        "%s fehlt" % name)

    def test_der_ordner_wird_mitgebaut(self) -> None:
        """Ohne Eintrag im .spec waere der Knopf in der EXE leer."""
        for spec in ("PS5ImageConverter_Pro.spec",
                     "PS5ImageConverter_Pro_linux.spec",
                     "PS5ImageConverter_Pro_macos.spec"):
            with self.subTest(spec=spec):
                text = (PROJEKT / spec).read_text(encoding="utf-8")
                self.assertIn("'Anleitungen'", text)

    def test_der_doktor_sieht_nach(self) -> None:
        """Fehlt der Ordner in der EXE, faellt es sonst erst beim Druecken auf."""
        anfang = QUELLE.index("# -- Mitgelieferte Werkzeuge ---")
        block = QUELLE[anfang:anfang + 1400]
        self.assertIn('("Anleitungen", "Anleitungen", False)', block)

    def test_eine_fehlende_anleitung_meldet_sich(self) -> None:
        """Ein Knopf, der stumm nichts tut, laesst den Nutzer raten."""
        anfang = QUELLE.index("    def _show_ampr_anleitung(self")
        rumpf = QUELLE[anfang:QUELLE.index(chr(10) + "    def ", anfang + 10)]
        self.assertIn("ampr_auswahl.anleitung_fehlt", rumpf)


if __name__ == "__main__":
    unittest.main(verbosity=2)
