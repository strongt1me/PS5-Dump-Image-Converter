"""Regressionstest: Metadaten der Bibliothek für Containerdateien.

Gefunden beim Durchtesten aller Aufgaben: In einer reinen Containersammlung
(`D:\\exFAT Games`, `D:\\ffpfsc Games`) zeigte die Bibliothek bei **jedem**
Eintrag „–" statt Titel und ID. Grund: Die Metadaten wurden im Ordner *neben*
dem Container gesucht (`_read_game_meta(os.path.dirname(...))`) – dort liegt
`sce_sys/param.json` naturgemäß nie. Der Dateiname trägt beides in aller Regel.

Geprüft wird deshalb, dass Titel (und, wenn im Namen enthalten, die Title-ID)
aus dem Dateinamen abgeleitet werden und ein danebenliegender Dump-Ordner
weiterhin Vorrang hat.
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


def _gui() -> PS5ConverterGUI:
    """Testobjekt ohne Tk-Fenster, mit den vom Scan genutzten Zwischenspeichern."""
    gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
    gui._preview_cache = {}
    gui._preview_report_dir_cache = {}
    return gui


class BibliothekMetadatenTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="bibliothek_")
        self.ordner = Path(self._tmp.name)
        self.gui = _gui()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _container(self, name: str, groesse: int = 4096) -> Path:
        pfad = self.ordner / name
        pfad.write_bytes(b"\x00" * groesse)
        return pfad

    def test_titel_kommt_aus_dem_dateinamen(self):
        self._container("Arcade Game Zone (01.003.000).exfat")
        eintraege = self.gui._library_scan_folder(str(self.ordner))
        self.assertEqual(len(eintraege), 1)
        self.assertEqual(eintraege[0]["meta"]["title"], "Arcade Game Zone")

    def test_title_id_wird_erkannt(self):
        self._container("PPSA19015 Arcade Game Zone (01.003.000).ffpkg")
        meta = self.gui._library_scan_folder(str(self.ordner))[0]["meta"]
        self.assertEqual(meta["title_id"], "PPSA19015")
        self.assertEqual(meta["title"], "Arcade Game Zone")

    def test_version_wird_erkannt(self):
        self._container("Arkanoid - Eternal Battle (01.002.000).exfat")
        meta = self.gui._library_scan_folder(str(self.ordner))[0]["meta"]
        self.assertEqual(meta["version"], "01.002.000")

    def test_alle_containerarten_bekommen_metadaten(self):
        for name in ("Spiel A.exfat", "Spiel B.ffpfsc", "Spiel C.ffpfs", "Spiel D.ffpkg"):
            self._container(name)
        eintraege = self.gui._library_scan_folder(str(self.ordner))
        self.assertEqual(len(eintraege), 4)
        for eintrag in eintraege:
            with self.subTest(datei=eintrag["path"]):
                self.assertNotIn(eintrag["meta"]["title"], ("", "–", None))

    def test_danebenliegender_dump_ordner_hat_vorrang(self):
        """Liegt der echte Dump daneben, gelten dessen param.json-Werte."""
        self._container("Mein Spiel.ffpfsc")
        dump = self.ordner / "Mein Spiel"
        (dump / "sce_sys").mkdir(parents=True)
        (dump / "sce_sys" / "param.json").write_text(
            '{"titleId": "PPSA12345", "localizedParameters": '
            '{"defaultLanguage": "de-DE", "de-DE": {"titleName": "Echter Titel"}}}',
            encoding="utf-8",
        )
        (dump / "eboot.bin").write_bytes(b"\x00" * 16)
        eintraege = {e["kind"]: e for e in self.gui._library_scan_folder(str(self.ordner))}
        self.assertIn("ffpfsc", eintraege)
        self.assertEqual(eintraege["ffpfsc"]["meta"]["title_id"], "PPSA12345")

    def test_fremde_dateien_werden_uebergangen(self):
        (self.ordner / "notizen.txt").write_text("kein Container", encoding="utf-8")
        self.assertEqual(self.gui._library_scan_folder(str(self.ordner)), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
