# -*- coding: utf-8 -*-
"""``fakelib_dateien_fuer_ziel`` / ``luecken_ohne_ersatz``: Auswahl nach der
tatsaechlichen Deckungsluecke der Zielfirmware statt nach den Importen des
Spiels.

**Warum es diese Auswahl gibt.** An Anno 117 (PPSA23559) und zuvor an Mordhau
legten sowohl der volle FW4-Satz als auch "Nur benötigte Bibliotheken" die
FW4-Audio-Ersatzdateien (libSceAjm, libSceAudioOut, ...) ins Spiel, weil es
sie importiert - obwohl die Zielfirmware diese Funktionen vollstaendig selbst
mitbringt. Die ueberfluessigen Dateien brachen den Start mit ``0xa0020104``
ab; erst ohne sie (nur Agc/AgcDriver/Ampr/PlayGo) startete das Spiel, siehe
Memory ``project-anno117-backport-fw4-2026-11-02``.
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import ps5_backport as b  # noqa: E402


def _exporttabelle_schreiben(basis: Path, firmware: int, exporte: dict) -> None:
    ordner = basis / str(firmware)
    ordner.mkdir(parents=True, exist_ok=True)
    daten = {"firmware": firmware, "staende": ["x.xx"], "exporte": exporte}
    with gzip.open(ordner / b.FIRMWARE_EXPORTE_DATEI, "wb") as datei:
        datei.write(json.dumps(daten).encode("utf-8"))


def _fakelib_satz(basis: Path, firmware: int, *namen: str) -> None:
    ordner = basis / str(firmware) / "fakelib"
    ordner.mkdir(parents=True, exist_ok=True)
    for name in namen:
        (ordner / name).write_bytes(b"\x7fELF" + b"\x00" * 60)
    (ordner / ("FW%d" % firmware)).write_bytes(b"")


class FakelibDateienFuerZiel(unittest.TestCase):
    """Nur Bibliotheken, die eine Luecke der Zielfirmware schliessen, bleiben."""

    def test_von_der_firmware_bereits_gedeckte_bibliothek_entfaellt(self):
        """Fall Anno 117: Spiel importiert libSceAudioOut, die Zielfirmware
        fuehrt die verlangte Funktion aber schon selbst."""
        with tempfile.TemporaryDirectory() as t:
            basis = Path(t)
            _fakelib_satz(basis, 4, "libSceAgc.sprx", "libSceAudioOut.sprx")
            _exporttabelle_schreiben(basis, 4, {
                "libSceAudioOut": ["AAAAAAAAAAA"],   # die Konsole hat die Funktion schon
                # libSceAgc fehlt in der Tabelle -> echte Luecke
            })

            def _mock(pfad):
                name = os.path.basename(pfad)
                if name == "spiel":
                    return {"importe": {"libSceAgc": {"GGGGGGGGGGG"},
                                        "libSceAudioOut": {"AAAAAAAAAAA"}},
                            "exporte": {}, "import_bibliotheken": {}, "export_bibliotheken": {}}
                if name == "libSceAgc.sprx":
                    return {"importe": {}, "exporte": {"libSceAgc": {"GGGGGGGGGGG"}},
                            "import_bibliotheken": {}, "export_bibliotheken": {}}
                return {"importe": {}, "exporte": {"libSceAudioOut": {"AAAAAAAAAAA"}},
                        "import_bibliotheken": {}, "export_bibliotheken": {}}

            alt = b.symbole_aus_datei
            b.symbole_aus_datei = _mock
            try:
                ergebnis = b.fakelib_dateien_fuer_ziel(str(basis), 4, ["spiel"])
            finally:
                b.symbole_aus_datei = alt

            self.assertIsNotNone(ergebnis)
            namen = {os.path.basename(p) for p in ergebnis}
            self.assertIn("libSceAgc.sprx", namen)
            self.assertNotIn("libSceAudioOut.sprx", namen)
            self.assertIn("FW4", namen)

    def test_datei_mit_mehreren_bibliotheksnamen_nur_bei_echter_nid_deckung(self):
        """Eine Datei kann mehrere Bibliotheksnamen exportieren (gemessen an
        Assassin's Creed Black Flag, 02.11.2026: ``libSceAudioOut.sprx``
        exportiert nebenbei auch ``libSceAudioOut2`` und drei weitere Namen).
        Ein Abgleich nur auf Namensebene wuerde die ganze Datei schon nehmen,
        wenn IRGENDEIN mitgefuehrter Name irgendeine Luecke hat - auch wenn
        die Datei die konkret fehlende Funktion unter diesem Namen gar nicht
        liefert."""
        with tempfile.TemporaryDirectory() as t:
            basis = Path(t)
            _fakelib_satz(basis, 4, "libSceFoo.sprx")
            _exporttabelle_schreiben(basis, 4, {
                "libSceFoo": ["F1F1F1F1F1F"],   # vollstaendig gedeckt
                "libSceBar": ["B1B1B1B1B1B"],   # B2 fehlt - aber nicht von dieser Datei geliefert
            })

            def _mock(pfad):
                name = os.path.basename(pfad)
                if name == "spiel":
                    return {"importe": {"libSceFoo": {"F1F1F1F1F1F"},
                                        "libSceBar": {"B1B1B1B1B1B", "B2B2B2B2B2B"}},
                            "exporte": {}, "import_bibliotheken": {}, "export_bibliotheken": {}}
                # libSceFoo.sprx fuehrt zwei Namen; "libSceBar" exportiert hier nur B1, nicht das
                # fehlende B2 - die Datei hilft also nicht gegen die echte Luecke.
                return {"importe": {},
                        "exporte": {"libSceFoo": {"F1F1F1F1F1F"}, "libSceBar": {"B1B1B1B1B1B"}},
                        "import_bibliotheken": {}, "export_bibliotheken": {}}

            alt = b.symbole_aus_datei
            b.symbole_aus_datei = _mock
            try:
                ergebnis = b.fakelib_dateien_fuer_ziel(str(basis), 4, ["spiel"])
            finally:
                b.symbole_aus_datei = alt

            namen = {os.path.basename(p) for p in ergebnis}
            self.assertNotIn("libSceFoo.sprx", namen)

    def test_ampr_und_playgo_bleiben_immer(self):
        """An Mordhau bestaetigt: ohne AMPR/PlayGo stuerzt ein PlayGo-Titel
        trotz vollstaendiger Firmware-Deckung ab."""
        with tempfile.TemporaryDirectory() as t:
            basis = Path(t)
            _fakelib_satz(basis, 4, "libSceAmpr.sprx", "libScePlayGo.sprx")
            _exporttabelle_schreiben(basis, 4, {
                "libSceAmpr": ["MMMMMMMMMMM"], "libScePlayGo": ["PPPPPPPPPPP"],
            })

            def _mock(pfad):
                if os.path.basename(pfad) == "spiel":
                    return {"importe": {"libkernel": {"KKKKKKKKKKK"}},
                            "exporte": {}, "import_bibliotheken": {}, "export_bibliotheken": {}}
                return {"importe": {}, "exporte": {}, "import_bibliotheken": {},
                        "export_bibliotheken": {}}

            alt = b.symbole_aus_datei
            b.symbole_aus_datei = _mock
            try:
                ergebnis = b.fakelib_dateien_fuer_ziel(str(basis), 4, ["spiel"])
            finally:
                b.symbole_aus_datei = alt

            namen = {os.path.basename(p) for p in ergebnis}
            self.assertIn("libSceAmpr.sprx", namen)
            self.assertIn("libScePlayGo.sprx", namen)

    def test_ohne_exporttabelle_gibt_none_zurueck(self):
        """Kein mitgelieferter Stand (z.B. selbst ergaenzte Firmware 8-10) ->
        der Aufrufer faellt auf das bisherige Verhalten zurueck."""
        with tempfile.TemporaryDirectory() as t:
            basis = Path(t)
            _fakelib_satz(basis, 8, "libSceAgc.sprx")
            self.assertIsNone(b.fakelib_dateien_fuer_ziel(str(basis), 8, ["spiel"]))

    def test_ohne_lesbare_importe_gibt_none_zurueck(self):
        with tempfile.TemporaryDirectory() as t:
            basis = Path(t)
            _fakelib_satz(basis, 4, "libSceAgc.sprx")
            _exporttabelle_schreiben(basis, 4, {"libSceAgc": ["GGGGGGGGGGG"]})

            def _mock(_pfad):
                return {"importe": {}, "exporte": {}, "import_bibliotheken": {},
                        "export_bibliotheken": {}}

            alt = b.symbole_aus_datei
            b.symbole_aus_datei = _mock
            try:
                self.assertIsNone(b.fakelib_dateien_fuer_ziel(str(basis), 4, ["spiel"]))
            finally:
                b.symbole_aus_datei = alt


class LueckenOhneErsatz(unittest.TestCase):
    """``luecken_ohne_ersatz`` -- was nach dem Einbau noch fehlt."""

    def test_gedeckte_luecke_fehlt_nicht_mehr(self):
        with tempfile.TemporaryDirectory() as t:
            basis = Path(t)
            # Eine leere Tabelle zaehlt in firmware_exporte_laden als "nicht lesbar" (wie bei
            # firmware_exporttabelle) - darum hier eine fremde Bibliothek, die nichts beitraegt.
            _exporttabelle_schreiben(basis, 4, {"unbeteiligt": ["ZZZZZZZZZZZ"]})

            def _mock(pfad):
                name = os.path.basename(pfad)
                if name == "spiel":
                    return {"importe": {"libSceAgc": {"GGGGGGGGGGG"}},
                            "exporte": {}, "import_bibliotheken": {}, "export_bibliotheken": {}}
                return {"importe": {}, "exporte": {"libSceAgc": {"GGGGGGGGGGG"}},
                        "import_bibliotheken": {}, "export_bibliotheken": {}}

            alt = b.symbole_aus_datei
            b.symbole_aus_datei = _mock
            try:
                ergebnis = b.luecken_ohne_ersatz(str(basis), 4, ["spiel"], ["fakelib/libSceAgc.sprx"])
            finally:
                b.symbole_aus_datei = alt

            self.assertEqual(ergebnis, {})

    def test_ungedeckte_kernbibliothek_bleibt_als_luecke(self):
        """Fall Anno 117: libkernel fehlt auf der Zielfirmware und keine
        Ersatzbibliothek deckt es - genau das, was ``KERNBIBLIOTHEKEN``
        benennt."""
        with tempfile.TemporaryDirectory() as t:
            basis = Path(t)
            _exporttabelle_schreiben(basis, 4, {"libkernel": ["AAAAAAAAAAA"]})

            def _mock(pfad):
                if os.path.basename(pfad) == "spiel":
                    return {"importe": {"libkernel": {"AAAAAAAAAAA", "BBBBBBBBBBB"}},
                            "exporte": {}, "import_bibliotheken": {}, "export_bibliotheken": {}}
                return {"importe": {}, "exporte": {}, "import_bibliotheken": {},
                        "export_bibliotheken": {}}

            alt = b.symbole_aus_datei
            b.symbole_aus_datei = _mock
            try:
                ergebnis = b.luecken_ohne_ersatz(str(basis), 4, ["spiel"], [])
            finally:
                b.symbole_aus_datei = alt

            self.assertEqual(ergebnis, {"libkernel": ["BBBBBBBBBBB"]})
            self.assertIn("libkernel", b.KERNBIBLIOTHEKEN)

    def test_ohne_exporttabelle_gibt_none_zurueck(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertIsNone(b.luecken_ohne_ersatz(str(t), 9, ["spiel"], []))


class KandidatenOhneSicherungen(unittest.TestCase):
    """``kandidaten`` -- ``.esbak``-Sicherungen (im Anno-117-Dump gefunden,
    Urheber unbekannt) zaehlen nicht als patchbare Datei (sonst wird die
    Sicherung selbst ueberschrieben und signiert, siehe Memory
    ``project-anno117-backport-fw4-2026-11-02``)."""

    def test_esbak_wird_uebersprungen(self):
        with tempfile.TemporaryDirectory() as t:
            ordner = Path(t)
            (ordner / "libc.prx").write_bytes(b"\x7fELF" + b"\x00" * 60)
            (ordner / "libc.prx.esbak").write_bytes(b"\x7fELF" + b"\x00" * 60)
            ergebnis = {os.path.basename(p) for p in b.kandidaten(str(ordner))}
            self.assertIn("libc.prx", ergebnis)
            self.assertNotIn("libc.prx.esbak", ergebnis)

    def test_bak_bleibt_wie_bisher_aussen_vor(self):
        with tempfile.TemporaryDirectory() as t:
            ordner = Path(t)
            (ordner / "eboot.bin.bak").write_bytes(b"\x7fELF" + b"\x00" * 60)
            self.assertEqual(b.kandidaten(str(ordner)), [])


if __name__ == "__main__":
    unittest.main()
