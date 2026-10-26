# -*- coding: utf-8 -*-
"""``fakelib_dateien_benoetigt`` / ``fakelib_unnoetige``: Einschraenkung des
Ersatzsatzes auf das, was das Spiel tatsaechlich importiert.

**Warum es diese Einschraenkung gibt.** Mehrere Berichte in der Szene
(drakmor/ShadowMountPlus Issues #169 und #173) zeigen Spiele, die mit dem
vollen Ersatzsatz beim Start abstuerzen oder haengen und erst nach
Beschraenkung auf die wirklich gebrauchten Bibliotheken starten - genau das,
was diese Funktionen anbieten (Haekchen "Nur benötigte Bibliotheken",
Vorgabe Nein).
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


class FakelibDateienBenoetigt(unittest.TestCase):
    """``fakelib_dateien_benoetigt`` -- nur importierte Bibliotheken bleiben."""

    def _satz(self, wurzel: Path, firmware: int, *namen: str) -> Path:
        ordner = wurzel / str(firmware) / "fakelib"
        ordner.mkdir(parents=True)
        for name in namen:
            (ordner / name).write_bytes(b"\x7fELF" + b"\x00" * 60)
        (ordner / ("FW%d" % firmware)).write_bytes(b"")
        return wurzel

    def test_nur_importierte_bibliothek_bleibt(self):
        with tempfile.TemporaryDirectory() as basis:
            self._satz(Path(basis), 4, "libSceAgc.sprx", "libSceNgs2.sprx")

            def _mock(pfad):
                name = os.path.basename(pfad)
                if name == "spiel":
                    return {"importe": {"libSceAgc": {"AAAAAAAAAAA"}},
                            "exporte": {}, "import_bibliotheken": {}, "export_bibliotheken": {}}
                if name == "libSceAgc.sprx":
                    return {"importe": {}, "exporte": {"libSceAgc": {"AAAAAAAAAAA"}},
                            "import_bibliotheken": {}, "export_bibliotheken": {}}
                return {"importe": {}, "exporte": {"libSceNgs2": {"NNNNNNNNNNN"}},
                        "import_bibliotheken": {}, "export_bibliotheken": {}}

            alt = b.symbole_aus_datei
            b.symbole_aus_datei = _mock
            try:
                ergebnis = b.fakelib_dateien_benoetigt(basis, 4, ["spiel"])
            finally:
                b.symbole_aus_datei = alt

            namen = {os.path.basename(p) for p in ergebnis}
            self.assertIn("libSceAgc.sprx", namen)
            self.assertNotIn("libSceNgs2.sprx", namen)

    def test_markierungsdatei_bleibt_immer(self):
        with tempfile.TemporaryDirectory() as basis:
            self._satz(Path(basis), 4, "libSceAgc.sprx")

            def _mock(pfad):
                if os.path.basename(pfad) == "spiel":
                    return {"importe": {"libSceAgc": {"AAAAAAAAAAA"}},
                            "exporte": {}, "import_bibliotheken": {}, "export_bibliotheken": {}}
                return {"importe": {}, "exporte": {"libSceAgc": {"AAAAAAAAAAA"}},
                        "import_bibliotheken": {}, "export_bibliotheken": {}}

            alt = b.symbole_aus_datei
            b.symbole_aus_datei = _mock
            try:
                ergebnis = b.fakelib_dateien_benoetigt(basis, 4, ["spiel"])
            finally:
                b.symbole_aus_datei = alt

            namen = {os.path.basename(p) for p in ergebnis}
            self.assertIn("FW4", namen)

    def test_ohne_lesbare_importtabelle_bleibt_der_volle_satz(self):
        """Eine Einschraenkung ohne Grundlage waere schlimmer als keine."""
        with tempfile.TemporaryDirectory() as basis:
            self._satz(Path(basis), 4, "libSceAgc.sprx", "libSceNgs2.sprx")

            def _mock(_pfad):
                return {"importe": {}, "exporte": {}, "import_bibliotheken": {},
                        "export_bibliotheken": {}}

            alt = b.symbole_aus_datei
            b.symbole_aus_datei = _mock
            try:
                voll = b.fakelib_dateien(basis, 4)
                ergebnis = b.fakelib_dateien_benoetigt(basis, 4, ["spiel"])
            finally:
                b.symbole_aus_datei = alt

            self.assertEqual(sorted(ergebnis), sorted(voll))

    def test_fallback_auf_dateinamen_ohne_exporttabelle(self):
        """Liest sich die Exporttabelle einer Ersatzbibliothek nicht aus,
        zaehlt ihr Dateiname wie in ``deckung_pruefen``."""
        with tempfile.TemporaryDirectory() as basis:
            self._satz(Path(basis), 4, "libSceAgc.sprx")

            def _mock(pfad):
                if os.path.basename(pfad) == "spiel":
                    return {"importe": {"libSceAgc": {"AAAAAAAAAAA"}},
                            "exporte": {}, "import_bibliotheken": {}, "export_bibliotheken": {}}
                # Keine lesbare Exporttabelle -> Fallback auf den Dateinamen.
                return {"importe": {}, "exporte": {}, "import_bibliotheken": {},
                        "export_bibliotheken": {}}

            alt = b.symbole_aus_datei

            def _mock2(pfad):
                if os.path.basename(pfad) == "spiel":
                    return _mock(pfad)
                return {"importe": {}, "exporte": {"?": set()}, "import_bibliotheken": {},
                        "export_bibliotheken": {}}

            b.symbole_aus_datei = _mock2
            try:
                ergebnis = b.fakelib_dateien_benoetigt(basis, 4, ["spiel"])
            finally:
                b.symbole_aus_datei = alt

            namen = {os.path.basename(p) for p in ergebnis}
            self.assertIn("libSceAgc.sprx", namen)


class FakelibUnnoetige(unittest.TestCase):
    """``fakelib_unnoetige`` -- Komplement zu ``fakelib_dateien_benoetigt``."""

    def _satz(self, wurzel: Path, firmware: int, *namen: str) -> Path:
        ordner = wurzel / str(firmware) / "fakelib"
        ordner.mkdir(parents=True)
        for name in namen:
            (ordner / name).write_bytes(b"\x7fELF" + b"\x00" * 60)
        return wurzel

    def test_unbenutzte_bibliothek_wird_genannt(self):
        with tempfile.TemporaryDirectory() as basis:
            self._satz(Path(basis), 4, "libSceAgc.sprx", "libSceNgs2.sprx")

            def _mock(pfad):
                name = os.path.basename(pfad)
                if name == "spiel":
                    return {"importe": {"libSceAgc": {"AAAAAAAAAAA"}},
                            "exporte": {}, "import_bibliotheken": {}, "export_bibliotheken": {}}
                if name == "libSceAgc.sprx":
                    return {"importe": {}, "exporte": {"libSceAgc": {"AAAAAAAAAAA"}},
                            "import_bibliotheken": {}, "export_bibliotheken": {}}
                return {"importe": {}, "exporte": {"libSceNgs2": {"NNNNNNNNNNN"}},
                        "import_bibliotheken": {}, "export_bibliotheken": {}}

            alt = b.symbole_aus_datei
            b.symbole_aus_datei = _mock
            try:
                ergebnis = b.fakelib_unnoetige(basis, 4, ["spiel"])
            finally:
                b.symbole_aus_datei = alt

            self.assertEqual(ergebnis, ["libSceNgs2.sprx"])

    def test_alles_benoetigt_ergibt_leere_liste(self):
        with tempfile.TemporaryDirectory() as basis:
            self._satz(Path(basis), 4, "libSceAgc.sprx")

            def _mock(pfad):
                if os.path.basename(pfad) == "spiel":
                    return {"importe": {"libSceAgc": {"AAAAAAAAAAA"}},
                            "exporte": {}, "import_bibliotheken": {}, "export_bibliotheken": {}}
                return {"importe": {}, "exporte": {"libSceAgc": {"AAAAAAAAAAA"}},
                        "import_bibliotheken": {}, "export_bibliotheken": {}}

            alt = b.symbole_aus_datei
            b.symbole_aus_datei = _mock
            try:
                ergebnis = b.fakelib_unnoetige(basis, 4, ["spiel"])
            finally:
                b.symbole_aus_datei = alt

            self.assertEqual(ergebnis, [])


if __name__ == "__main__":
    unittest.main()
