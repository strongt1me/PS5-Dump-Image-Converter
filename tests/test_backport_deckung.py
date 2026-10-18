# -*- coding: utf-8 -*-
"""Prueft die Deckung eines Spiels gegen einen entpackten Firmware-Stand.

**Warum es diese Pruefung gibt.** Bis zum 07.09.2026 sagte das Programm vor
einem Backport nichts darueber, ob die Zielfirmware ueberhaupt liefert, was
das Spiel verlangt. Aufgefallen waere eine Luecke erst auf der Konsole - und
zwar ohne Meldung: Das Spiel startet dann einfach nicht.

**Warum auf NID-Ebene und nicht auf Bibliotheksebene.** Ein Vergleich ganzer
Bibliotheksnamen taugt dafuer nicht. Gemessen an zehn Dumps meldete er fuer
Firmware 12.00 dieselbe Liste wie fuer 7.01, obwohl ein SDK-10-Spiel auf
12.00 laeuft: Namen wie ``libScePosix`` oder ``libSceAudioOut2`` haben gar
keine eigene Datei, sie stecken in einem Nachbarmodul. Erst der Vergleich
einzelner Funktionen trennt echte Luecken von scheinbaren.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import ps5_backport as b  # noqa: E402


class FirmwareBestandErkennen(unittest.TestCase):
    """``ist_firmware_bestand`` und die Wahl des vollstaendigsten Standes."""

    def _stand(self, wurzel: Path, name: str, anzahl: int) -> Path:
        ordner = wurzel / name / "system" / "common" / "lib"
        ordner.mkdir(parents=True)
        for i in range(anzahl):
            (ordner / ("libSce%02d.sprx" % i)).write_bytes(b"\x7fELF" + b"\x00" * 60)
        return wurzel / name

    def test_leerer_ordner_ist_kein_bestand(self):
        with tempfile.TemporaryDirectory() as basis:
            self.assertFalse(b.ist_firmware_bestand(basis))
            self.assertFalse(b.ist_firmware_bestand(""))

    def test_ordner_ohne_module_ist_kein_bestand(self):
        with tempfile.TemporaryDirectory() as basis:
            (Path(basis) / "system" / "common" / "lib").mkdir(parents=True)
            self.assertFalse(b.ist_firmware_bestand(basis),
                             "Ein leerer lib-Ordner ist noch kein Bestand")

    def test_bestand_wird_erkannt(self):
        with tempfile.TemporaryDirectory() as basis:
            stand = self._stand(Path(basis), "9.40", 3)
            self.assertTrue(b.ist_firmware_bestand(str(stand)))

    def test_vollstaendigster_stand_gewinnt(self):
        """Der duennere Stand meldete sonst reihenweise Falschbefunde.

        Echte Entpackungen sind unterschiedlich vollstaendig: 9.60 fuehrt
        273 Bibliotheken, 9.40 dagegen 543. Wer den duenneren nimmt, haelt
        vorhandene Funktionen faelschlich fuer fehlend.
        """
        with tempfile.TemporaryDirectory() as basis:
            wurzel = Path(basis)
            self._stand(wurzel, "9.00", 2)
            self._stand(wurzel, "9.40", 9)
            self._stand(wurzel, "9.60", 3)
            gewaehlt = b.firmware_ordner_fuer(str(wurzel), 9)
            self.assertEqual(os.path.basename(gewaehlt), "9.40")

    def test_falsche_hauptversion_wird_uebergangen(self):
        with tempfile.TemporaryDirectory() as basis:
            wurzel = Path(basis)
            self._stand(wurzel, "7.61", 5)
            self.assertEqual(b.firmware_ordner_fuer(str(wurzel), 9), "")
            self.assertTrue(b.firmware_ordner_fuer(str(wurzel), 7))

    def test_zehn_ist_nicht_eins(self):
        """``10.01`` darf nicht als Hauptversion 1 durchgehen."""
        with tempfile.TemporaryDirectory() as basis:
            wurzel = Path(basis)
            self._stand(wurzel, "10.01", 4)
            self.assertEqual(b.firmware_ordner_fuer(str(wurzel), 1), "")
            self.assertTrue(b.firmware_ordner_fuer(str(wurzel), 10))

    def test_fehlende_basis_ist_kein_fehler(self):
        self.assertEqual(b.firmware_ordner_fuer("", 9), "")
        self.assertEqual(b.firmware_ordner_fuer(r"X:\gibt-es-nicht", 9), "")


class DeckungOhneBestand(unittest.TestCase):
    """Ohne lesbaren Bestand darf nichts behauptet werden."""

    def test_leerer_bestand_meldet_nichts(self):
        with tempfile.TemporaryDirectory() as basis:
            ergebnis = b.firmware_deckung([], basis)
            self.assertEqual(ergebnis["bestand"], 0)
            self.assertEqual(ergebnis["fehlend"], {})
            self.assertEqual(ergebnis["verlangt"], 0)


class SdkTabelle(unittest.TestCase):
    """Die Firmware-Profile - Form und Grenzen."""

    def test_elf_bis_zwoelf_vorhanden(self):
        for stand in range(1, 13):
            self.assertIn(stand, b.SDK_PAARE)

    def test_hauptbyte_ist_bcd_firmware(self):
        """``0x11000043`` gehoert zu Firmware 11, nicht 17."""
        for stand, (ps5, _ps4) in b.SDK_PAARE.items():
            hoch = (ps5 >> 24) & 0xFF
            erwartet = int("%d" % stand, 16) if stand < 10 else int(str(stand), 16)
            self.assertEqual(hoch, erwartet,
                             "FW %d traegt 0x%02X im Hauptbyte" % (stand, hoch))

    def test_nebenversion_ist_null(self):
        """Alle Eintraege zielen auf x.00 - so wie die Vorlage es tut."""
        for stand, (ps5, _ps4) in b.SDK_PAARE.items():
            self.assertEqual((ps5 >> 16) & 0xFF, 0,
                             "FW %d hat eine Nebenversion != 00" % stand)

    def test_ps4_seite_steigt_streng(self):
        werte = [paar[1] for _s, paar in sorted(b.SDK_PAARE.items())]
        self.assertEqual(werte, sorted(werte),
                         "Die PS4-Partnerwerte muessen monoton steigen")

    def test_firmware_text(self):
        self.assertEqual(b.firmware_text(0x11000043), "11.00")
        self.assertEqual(b.firmware_text(0x07000038), "7.00")


class FakelibBestand(unittest.TestCase):
    """``firmwares_mit_bestand`` - die Auswahl folgt den Dateien."""

    def test_ohne_basis_leer(self):
        self.assertEqual(b.firmwares_mit_bestand(""), ())
        self.assertEqual(b.firmwares_mit_bestand(r"X:\gibt-es-nicht"), ())

    def test_selbst_ergaenzter_satz_zaehlt(self):
        """Der eigentliche Zweck: 8 und 10 ohne Codeaenderung waehlbar."""
        with tempfile.TemporaryDirectory() as basis:
            for stand in (4, 8, 10):
                ordner = Path(basis) / str(stand) / "fakelib"
                ordner.mkdir(parents=True)
                (ordner / "libSceAgc.sprx").write_bytes(b"\x7fELF")
            self.assertEqual(b.firmwares_mit_bestand(basis), (4, 8, 10))

    def test_ordner_ohne_bibliothek_zaehlt_nicht(self):
        with tempfile.TemporaryDirectory() as basis:
            (Path(basis) / "9" / "fakelib").mkdir(parents=True)
            (Path(basis) / "9" / "fakelib" / "liesmich.txt").write_text("x")
            self.assertEqual(b.firmwares_mit_bestand(basis), ())

    def test_stand_ohne_sdk_paar_wird_uebergangen(self):
        """Ohne SDK-Paar liesse sich der Modulkopf nicht schreiben."""
        with tempfile.TemporaryDirectory() as basis:
            ordner = Path(basis) / "13" / "fakelib"
            ordner.mkdir(parents=True)
            (ordner / "libSceAgc.sprx").write_bytes(b"\x7fELF")
            self.assertNotIn(13, b.firmwares_mit_bestand(basis))


class FwDateipfadTabelle(unittest.TestCase):
    """``fw_dateipfad_tabelle`` -- Firmware-Bibliothek nach Datei."""

    def _fw_stand(self, wurzel: Path, *dateinamen: str) -> Path:
        """Legt einen minimalen FW-Stand an (system/common/lib/)."""
        lib_dir = wurzel / "system" / "common" / "lib"
        lib_dir.mkdir(parents=True, exist_ok=True)
        for name in dateinamen:
            (lib_dir / name).write_bytes(b"\x7fELF" + b"\x00" * 60)
        return wurzel

    def test_leerer_ordner_gibt_leere_tabelle(self):
        self.assertEqual(b.fw_dateipfad_tabelle(""), {})
        self.assertEqual(b.fw_dateipfad_tabelle(r"X:\gibt-es-nicht"), {})

    def test_tabelle_enthaelt_bibliotheksnamen_und_pfad(self):
        with tempfile.TemporaryDirectory() as basis:
            stand = self._fw_stand(Path(basis), "libSceAgc.sprx")
            datei = str(stand / "system" / "common" / "lib" / "libSceAgc.sprx")

            def _mock(pfad):
                return {"importe": {}, "exporte": {"libSceAgc": {"AAAAAAAAAAA"}},
                        "import_bibliotheken": {}, "export_bibliotheken": {}}

            alt = b.symbole_aus_datei
            b.symbole_aus_datei = _mock
            try:
                tabelle = b.fw_dateipfad_tabelle(str(stand))
            finally:
                b.symbole_aus_datei = alt

            self.assertIn("libSceAgc", tabelle)
            nids, pfad = tabelle["libSceAgc"]
            self.assertIn("AAAAAAAAAAA", nids)
            self.assertEqual(os.path.basename(pfad), "libSceAgc.sprx")

    def test_keine_sprx_keine_eintraege(self):
        with tempfile.TemporaryDirectory() as basis:
            lib_dir = Path(basis) / "system" / "common" / "lib"
            lib_dir.mkdir(parents=True)
            (lib_dir / "liesmich.txt").write_text("x")
            self.assertEqual(b.fw_dateipfad_tabelle(str(basis)), {})

    def test_unbekannte_lib_wird_uebergangen(self):
        """Exporte mit leerem oder '?'-Namen landen nicht in der Tabelle."""
        with tempfile.TemporaryDirectory() as basis:
            stand = self._fw_stand(Path(basis), "unbekannt.sprx")

            def _mock(pfad):
                return {"importe": {}, "exporte": {"?": {"AAAAAAAAAAA"}},
                        "import_bibliotheken": {}, "export_bibliotheken": {}}

            alt = b.symbole_aus_datei
            b.symbole_aus_datei = _mock
            try:
                tabelle = b.fw_dateipfad_tabelle(str(stand))
            finally:
                b.symbole_aus_datei = alt

            self.assertEqual(tabelle, {})

    def test_zwei_dateien_verschiedene_bibliotheken(self):
        with tempfile.TemporaryDirectory() as basis:
            stand = self._fw_stand(Path(basis), "libA.sprx", "libB.sprx")

            def _mock(pfad):
                name = os.path.basename(pfad).replace(".sprx", "")
                return {"importe": {}, "exporte": {name: {"NID%s" % name}},
                        "import_bibliotheken": {}, "export_bibliotheken": {}}

            alt = b.symbole_aus_datei
            b.symbole_aus_datei = _mock
            try:
                tabelle = b.fw_dateipfad_tabelle(str(stand))
            finally:
                b.symbole_aus_datei = alt

            self.assertIn("libA", tabelle)
            self.assertIn("libB", tabelle)


class FehlendeLibsErmitteln(unittest.TestCase):
    """``fehlende_libs_ermitteln`` -- Luecken zwischen Spiel, Fakelibs und FW."""

    def _fw_stand(self, wurzel: Path, dateiname: str) -> Path:
        lib_dir = wurzel / "system" / "common" / "lib"
        lib_dir.mkdir(parents=True, exist_ok=True)
        (lib_dir / dateiname).write_bytes(b"\x7fELF" + b"\x00" * 60)
        return wurzel

    def test_alles_abgedeckt_ergibt_leere_liste(self):
        """Wenn die vorhandenen Fakelibs alle NIDs liefern, kein Ergebnis."""
        def _mock(pfad):
            if pfad == "spiel":
                return {"importe": {"libSceAgc": {"AAAAAAAAAAA"}},
                        "exporte": {}, "import_bibliotheken": {}, "export_bibliotheken": {}}
            return {"importe": {}, "exporte": {"libSceAgc": {"AAAAAAAAAAA"}},
                    "import_bibliotheken": {}, "export_bibliotheken": {}}

        alt = b.symbole_aus_datei
        b.symbole_aus_datei = _mock
        try:
            ergebnis = b.fehlende_libs_ermitteln(["spiel"], ["fakelib"], "")
        finally:
            b.symbole_aus_datei = alt

        self.assertEqual(ergebnis, [])

    def test_fehlende_lib_in_firmware_gefunden(self):
        with tempfile.TemporaryDirectory() as basis:
            stand = self._fw_stand(Path(basis), "libSceNet.sprx")

            def _mock(pfad):
                if pfad == "spiel":
                    return {"importe": {"libSceNet": {"NNNNNNNNNNN"}},
                            "exporte": {}, "import_bibliotheken": {}, "export_bibliotheken": {}}
                if os.path.basename(pfad) == "libSceNet.sprx":
                    return {"importe": {}, "exporte": {"libSceNet": {"NNNNNNNNNNN"}},
                            "import_bibliotheken": {}, "export_bibliotheken": {}}
                return {"importe": {}, "exporte": {},
                        "import_bibliotheken": {}, "export_bibliotheken": {}}

            alt = b.symbole_aus_datei
            b.symbole_aus_datei = _mock
            try:
                ergebnis = b.fehlende_libs_ermitteln(["spiel"], [], str(stand))
            finally:
                b.symbole_aus_datei = alt

            self.assertEqual(len(ergebnis), 1)
            lib, pfad = ergebnis[0]
            self.assertEqual(lib, "libSceNet")
            self.assertEqual(os.path.basename(pfad), "libSceNet.sprx")

    def test_lib_nicht_in_firmware_wird_uebergangen(self):
        """Die Konsole liefert manche Bibliotheken selbst – kein Fehler."""
        with tempfile.TemporaryDirectory() as basis:
            stand = self._fw_stand(Path(basis), "libSceOther.sprx")

            def _mock(pfad):
                if pfad == "spiel":
                    return {"importe": {"libkernel": {"KKKKKKKKKKK"}},
                            "exporte": {}, "import_bibliotheken": {}, "export_bibliotheken": {}}
                if os.path.basename(pfad) == "libSceOther.sprx":
                    return {"importe": {}, "exporte": {"libSceOther": {"OOOOOOOOOOO"}},
                            "import_bibliotheken": {}, "export_bibliotheken": {}}
                return {"importe": {}, "exporte": {},
                        "import_bibliotheken": {}, "export_bibliotheken": {}}

            alt = b.symbole_aus_datei
            b.symbole_aus_datei = _mock
            try:
                ergebnis = b.fehlende_libs_ermitteln(["spiel"], [], str(stand))
            finally:
                b.symbole_aus_datei = alt

            self.assertEqual(ergebnis, [])

    def test_eine_datei_mehrere_libs_nur_einmal(self):
        """Eine FW-Datei, die zwei Libs abdeckt, erscheint nur einmal."""
        with tempfile.TemporaryDirectory() as basis:
            stand = self._fw_stand(Path(basis), "libSceCombo.sprx")

            def _mock(pfad):
                if pfad == "spiel":
                    return {"importe": {"libSceA": {"AAAAAAAAAAA"},
                                        "libSceB": {"BBBBBBBBBBB"}},
                            "exporte": {}, "import_bibliotheken": {}, "export_bibliotheken": {}}
                if os.path.basename(pfad) == "libSceCombo.sprx":
                    return {"importe": {}, "exporte": {
                        "libSceA": {"AAAAAAAAAAA"}, "libSceB": {"BBBBBBBBBBB"}},
                            "import_bibliotheken": {}, "export_bibliotheken": {}}
                return {"importe": {}, "exporte": {},
                        "import_bibliotheken": {}, "export_bibliotheken": {}}

            alt = b.symbole_aus_datei
            b.symbole_aus_datei = _mock
            try:
                ergebnis = b.fehlende_libs_ermitteln(["spiel"], [], str(stand))
            finally:
                b.symbole_aus_datei = alt

            # Nur eine Zeile, obwohl zwei Bibliotheken fehlen
            self.assertEqual(len(ergebnis), 1)
            _, pfad = ergebnis[0]
            self.assertEqual(os.path.basename(pfad), "libSceCombo.sprx")


class FakelibsAusFirmwareKopieren(unittest.TestCase):
    """``fakelibs_aus_firmware_kopieren`` -- Kopiervorgang und Ergebnis-Dict."""

    def _fw_stand(self, wurzel: Path, dateiname: str) -> Path:
        lib_dir = wurzel / "system" / "common" / "lib"
        lib_dir.mkdir(parents=True, exist_ok=True)
        (lib_dir / dateiname).write_bytes(b"\x7fELF" + b"\x00" * 60)
        return wurzel

    def test_keine_kandidaten_gibt_null_kopiert(self):
        ergebnis = b.fakelibs_aus_firmware_kopieren([], [], "", "")
        self.assertEqual(ergebnis["kopiert"], 0)
        self.assertEqual(ergebnis["uebersprungen"], 0)
        self.assertEqual(ergebnis["dateien"], [])

    def test_datei_wird_kopiert(self):
        with tempfile.TemporaryDirectory() as tmp:
            wurzel = Path(tmp)
            stand = self._fw_stand(wurzel / "fw", "libSceNet.sprx")
            ziel = str(wurzel / "fakelib")

            def _mock(pfad):
                if pfad == "spiel":
                    return {"importe": {"libSceNet": {"NNNNNNNNNNN"}},
                            "exporte": {}, "import_bibliotheken": {}, "export_bibliotheken": {}}
                if os.path.basename(pfad) == "libSceNet.sprx":
                    return {"importe": {}, "exporte": {"libSceNet": {"NNNNNNNNNNN"}},
                            "import_bibliotheken": {}, "export_bibliotheken": {}}
                return {"importe": {}, "exporte": {},
                        "import_bibliotheken": {}, "export_bibliotheken": {}}

            alt = b.symbole_aus_datei
            b.symbole_aus_datei = _mock
            try:
                ergebnis = b.fakelibs_aus_firmware_kopieren(
                    ["spiel"], [], str(stand), ziel)
            finally:
                b.symbole_aus_datei = alt

            self.assertEqual(ergebnis["kopiert"], 1)
            self.assertEqual(ergebnis["uebersprungen"], 0)
            self.assertIn("libSceNet.sprx", ergebnis["dateien"])
            self.assertTrue(os.path.isfile(os.path.join(ziel, "libSceNet.sprx")))

    def test_vorhandene_zieldatei_wird_uebersprungen(self):
        """Schon vorhandene Dateien werden nicht ueberschrieben."""
        with tempfile.TemporaryDirectory() as tmp:
            wurzel = Path(tmp)
            stand = self._fw_stand(wurzel / "fw", "libSceNet.sprx")
            ziel = wurzel / "fakelib"
            ziel.mkdir()
            (ziel / "libSceNet.sprx").write_bytes(b"vorhand")

            def _mock(pfad):
                if pfad == "spiel":
                    return {"importe": {"libSceNet": {"NNNNNNNNNNN"}},
                            "exporte": {}, "import_bibliotheken": {}, "export_bibliotheken": {}}
                if os.path.basename(pfad) == "libSceNet.sprx":
                    return {"importe": {}, "exporte": {"libSceNet": {"NNNNNNNNNNN"}},
                            "import_bibliotheken": {}, "export_bibliotheken": {}}
                return {"importe": {}, "exporte": {},
                        "import_bibliotheken": {}, "export_bibliotheken": {}}

            alt = b.symbole_aus_datei
            b.symbole_aus_datei = _mock
            try:
                ergebnis = b.fakelibs_aus_firmware_kopieren(
                    ["spiel"], [], str(stand), str(ziel))
            finally:
                b.symbole_aus_datei = alt

            self.assertEqual(ergebnis["kopiert"], 0)
            self.assertEqual(ergebnis["uebersprungen"], 1)
            # Originaldatei unberuehrt
            self.assertEqual((ziel / "libSceNet.sprx").read_bytes(), b"vorhand")

    def test_ergebnis_dateinamen_sortiert(self):
        with tempfile.TemporaryDirectory() as tmp:
            wurzel = Path(tmp)
            lib_dir = wurzel / "fw" / "system" / "common" / "lib"
            lib_dir.mkdir(parents=True)
            for name in ("libZ.sprx", "libA.sprx"):
                (lib_dir / name).write_bytes(b"\x7fELF" + b"\x00" * 60)
            ziel = str(wurzel / "fakelib")

            def _mock(pfad):
                if pfad == "spiel":
                    return {"importe": {"libZ": {"ZZZZZZZZZZZ"}, "libA": {"AAAAAAAAAAA"}},
                            "exporte": {}, "import_bibliotheken": {}, "export_bibliotheken": {}}
                bname = os.path.basename(pfad).replace(".sprx", "")
                return {"importe": {}, "exporte": {bname: {"NIDNIDNIDNI"}},
                        "import_bibliotheken": {}, "export_bibliotheken": {}}

            alt = b.symbole_aus_datei
            b.symbole_aus_datei = _mock
            try:
                ergebnis = b.fakelibs_aus_firmware_kopieren(
                    ["spiel"], [], str(wurzel / "fw"), ziel)
            finally:
                b.symbole_aus_datei = alt

            self.assertEqual(ergebnis["dateien"], sorted(ergebnis["dateien"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
