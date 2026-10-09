# -*- coding: utf-8 -*-
"""Archive als Quelle (``utils/archiv_quelle.py``, seit v1.9.70).

``.zip`` und ``.7z`` werden mit echten Archiven geprueft (das ``.7z`` baut das mitgelieferte 7-Zip selbst). Ein
``.rar`` laesst sich hier nicht erzeugen - 7-Zip kann RAR nur lesen -, ein echter RAR-Lauf ist deshalb nicht belegt.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import archiv_quelle   # noqa: E402

SIEBENZIP = archiv_quelle.siebenzip_suchen([str(PROJEKT)])


def _spiel(wurzel: Path) -> None:
    (wurzel / "sce_sys").mkdir(parents=True)
    (wurzel / "sce_sys" / "param.json").write_text("{}", encoding="utf-8")
    (wurzel / "eboot.bin").write_bytes(b"\x7fSELF" + os.urandom(2000))
    (wurzel / "Media").mkdir()
    (wurzel / "Media" / "a.dat").write_bytes(b"x" * 5000)


class SiebenzipTests(unittest.TestCase):

    def test_das_mitgelieferte_siebenzip_wird_gefunden(self) -> None:
        wurzel = [str(PROJEKT)]
        gefunden = archiv_quelle.siebenzip_suchen(wurzel)
        self.assertTrue(gefunden)
        self.assertTrue(os.path.isfile(gefunden))

    def test_alle_drei_plattformen_liegen_im_ordner(self) -> None:
        for teil in ("windows/7z.exe", "windows/7z.dll", "linux-x64/7zz", "macos/7zz", "License.txt"):
            with self.subTest(datei=teil):
                self.assertTrue((PROJEKT / archiv_quelle.ORDNER / teil).is_file())

    def test_ohne_alles_wird_nichts_gefunden(self) -> None:
        import shutil
        from unittest import mock
        with mock.patch.object(shutil, "which", return_value=None), \
                mock.patch.dict(os.environ, {"ProgramFiles": "Z:/gibt-es-nicht",
                                             "ProgramFiles(x86)": "Z:/gibt-es-nicht"}):
            self.assertEqual("", archiv_quelle.siebenzip_suchen([]))


class WurzelTests(unittest.TestCase):

    def test_spiel_direkt_am_stamm(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            _spiel(Path(t))
            self.assertEqual(t, archiv_quelle.spielwurzel(t))

    def test_spiel_eine_ebene_tiefer(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            _spiel(Path(t) / "PPSA01234")
            self.assertEqual(str(Path(t) / "PPSA01234"), archiv_quelle.spielwurzel(t))

    def test_spiel_zwischen_mehreren_geschwistern(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "Readme").mkdir()
            (Path(t) / "Readme" / "x.txt").write_text("x")
            _spiel(Path(t) / "Spiel")
            self.assertEqual(str(Path(t) / "Spiel"), archiv_quelle.spielwurzel(t))

    def test_ohne_spiel_bleibt_der_stamm(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "irgendwas").mkdir()
            self.assertEqual(t, archiv_quelle.spielwurzel(t))


class ZipTests(unittest.TestCase):

    def test_zip_wird_entpackt_und_der_spielordner_gefunden(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            quelle = Path(t) / "q" / "Mein Spiel"
            _spiel(quelle)
            archiv = Path(t) / "spiel.zip"
            with zipfile.ZipFile(archiv, "w", zipfile.ZIP_DEFLATED) as z:
                for datei in quelle.rglob("*"):
                    z.write(datei, datei.relative_to(quelle.parent))
            meldungen: list[str] = []
            ziel = Path(t) / "ziel"
            wurzel = archiv_quelle.entpacken(str(archiv), str(ziel), melden=meldungen.append)
            self.assertEqual(str(ziel / "Mein Spiel"), wurzel)
            self.assertEqual((quelle / "eboot.bin").read_bytes(), (Path(wurzel) / "eboot.bin").read_bytes())
            self.assertIn("100%", meldungen)

    def test_zip_mit_pfad_nach_oben_wird_abgelehnt(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            archiv = Path(t) / "boese.zip"
            with zipfile.ZipFile(archiv, "w") as z:
                z.writestr("../draussen.txt", "x")
            with self.assertRaises(archiv_quelle.ArchivFehler):
                archiv_quelle.entpacken(str(archiv), str(Path(t) / "ziel"))
            self.assertFalse((Path(t) / "draussen.txt").exists())

    def test_kaputtes_zip_gibt_eine_meldung(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            archiv = Path(t) / "kaputt.zip"
            archiv.write_bytes(b"das ist kein zip")
            with self.assertRaises(archiv_quelle.ArchivFehler):
                archiv_quelle.entpacken(str(archiv), str(Path(t) / "ziel"))

    def test_abbruch_stoppt_das_entpacken(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            archiv = Path(t) / "a.zip"
            with zipfile.ZipFile(archiv, "w") as z:
                for i in range(5):
                    z.writestr("d%d.txt" % i, "x")
            with self.assertRaises(archiv_quelle.ArchivFehler):
                archiv_quelle.entpacken(str(archiv), str(Path(t) / "z"), abbruch=lambda: True)


@unittest.skipUnless(SIEBENZIP and sys.platform == "win32", "baut das 7z mit dem Windows-7-Zip")
class SiebenzipArchivTests(unittest.TestCase):

    def _bauen(self, t: str, endung: str) -> tuple[Path, Path]:
        quelle = Path(t) / "q" / "Spiel"
        _spiel(quelle)
        archiv = Path(t) / ("spiel" + endung)
        subprocess.run([SIEBENZIP, "a", str(archiv), str(quelle), "-bso0", "-bsp0"], check=True,
                       stdin=subprocess.DEVNULL, creationflags=0x08000000)
        return quelle, archiv

    def test_siebenzip_archiv_wird_entpackt(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            quelle, archiv = self._bauen(t, ".7z")
            meldungen: list[str] = []
            wurzel = archiv_quelle.entpacken(str(archiv), str(Path(t) / "ziel"), wurzeln=[str(PROJEKT)],
                                             melden=meldungen.append,
                                             popen_extra={"creationflags": 0x08000000})
            self.assertEqual(str(Path(t) / "ziel" / "Spiel"), wurzel)
            for datei in ("eboot.bin", "Media/a.dat", "sce_sys/param.json"):
                self.assertEqual((quelle / datei).read_bytes(), (Path(wurzel) / datei).read_bytes())

    def test_kaputtes_siebenzip_archiv_gibt_eine_meldung(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            archiv = Path(t) / "kaputt.7z"
            archiv.write_bytes(b"7z\xbc\xaf\x27\x1c" + os.urandom(300))
            with self.assertRaises(archiv_quelle.ArchivFehler) as ctx:
                archiv_quelle.entpacken(str(archiv), str(Path(t) / "ziel"), wurzeln=[str(PROJEKT)],
                                        popen_extra={"creationflags": 0x08000000})
            self.assertIn("7-Zip", str(ctx.exception))

    def test_rar_endung_geht_den_siebenzip_weg(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            archiv = Path(t) / "x.rar"
            archiv.write_bytes(b"Rar!\x1a\x07\x01\x00" + os.urandom(200))
            with self.assertRaises(archiv_quelle.ArchivFehler) as ctx:
                archiv_quelle.entpacken(str(archiv), str(Path(t) / "ziel"), wurzeln=[str(PROJEKT)],
                                        popen_extra={"creationflags": 0x08000000})
            self.assertIn("7-Zip", str(ctx.exception))


class EingabeTests(unittest.TestCase):

    def test_ist_archiv(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            for endung, soll in ((".zip", True), (".7Z", True), (".rar", True), (".exfat", False), (".txt", False)):
                datei = Path(t) / ("a" + endung)
                datei.write_bytes(b"x")
                with self.subTest(endung=endung):
                    self.assertEqual(soll, archiv_quelle.ist_archiv(str(datei)))
            self.assertFalse(archiv_quelle.ist_archiv(str(Path(t) / "gibt-es-nicht.zip")))


try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover - ohne Anzeige
    TK_DA = False
    _WURZEL = None


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class FensterTests(unittest.TestCase):
    """Aufgabe 1 mit einem Archiv als Quelle - am echten Programm, ein ZIP mit Spielordner."""

    @classmethod
    def setUpClass(cls) -> None:
        import time
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt
        cls.time = time
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        cls.app.current_mode.set("pack_folder")
        # Ohne laufende Hauptschleife lehnt Tk ``after`` aus einem Arbeitsfaden ab (und
        # ``_hauptfaden_planen`` verschluckt das): Die Rueckrufe werden eingesammelt und
        # im Hauptfaden abgearbeitet - was in der Hauptschleife ``after`` taete.
        cls.offen = []
        cls.app._hauptfaden_planen = lambda rueckruf, *a, ms=0: (cls.offen.append((rueckruf, a)), True)[1]

    def _zip(self, t: str) -> Path:
        quelle = Path(t) / "q" / "PPSA01234"
        (quelle / "sce_sys").mkdir(parents=True)
        (quelle / "sce_sys" / "param.json").write_text(
            '{"titleId": "PPSA01234", "contentId": "IV0000-PPSA01234_00-TESTARCHIV000000", '
            '"localizedParameters": {"defaultLanguage": "de-DE", "de-DE": {"titleName": "Probe"}}}',
            encoding="utf-8")
        (quelle / "eboot.bin").write_bytes(b"ELF" + bytes(4092))
        archiv = Path(t) / "spiel.zip"
        with zipfile.ZipFile(archiv, "w", zipfile.ZIP_DEFLATED) as z:
            for datei in quelle.rglob("*"):
                z.write(datei, datei.relative_to(quelle.parent))
        return archiv

    def _warten(self) -> None:
        ende = self.time.time() + 30
        while getattr(self.app, "_archiv_laeuft", False) and self.time.time() < ende:
            while self.offen:
                rueckruf, args = self.offen.pop(0)
                rueckruf(*args)
            _WURZEL.update()
            self.time.sleep(0.02)
        for _ in range(10):
            _WURZEL.update()

    def test_ein_zip_wird_zur_quelle(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            archiv = self._zip(t)
            self.app.source_path.set("")
            self.app._archiv_als_quelle(str(archiv))
            self._warten()
            quelle = self.app.source_path.get()
            self.addCleanup(lambda: __import__("shutil").rmtree(self.app._archiv_ordner, ignore_errors=True))
            self.assertTrue(quelle.endswith("PPSA01234"), quelle)
            self.assertTrue(os.path.isfile(os.path.join(quelle, "sce_sys", "param.json")))
            self.assertEqual("", self.app._validate_source_path(quelle, "pack_folder"))

    def test_ein_archiv_ohne_spiel_wird_gemeldet_und_aendert_die_quelle_nicht(self) -> None:
        from unittest import mock
        with tempfile.TemporaryDirectory() as t:
            archiv = Path(t) / "leer.zip"
            with zipfile.ZipFile(archiv, "w") as z:
                z.writestr("nur/eine.txt", "x")
            self.app.source_path.set("VORHER")
            with mock.patch.object(self.haupt.messagebox, "showerror") as fehler:
                self.app._archiv_als_quelle(str(archiv))
                self._warten()
            self.addCleanup(lambda: __import__("shutil").rmtree(self.app._archiv_ordner, ignore_errors=True))
            fehler.assert_called_once()
            self.assertEqual("VORHER", self.app.source_path.get())

    def test_7z_ohne_siebenzip_wird_vor_dem_entpacken_gemeldet(self) -> None:
        from unittest import mock
        with tempfile.TemporaryDirectory() as t:
            archiv = Path(t) / "x.7z"
            archiv.write_bytes(b"7z")
            with mock.patch.object(self.haupt.archiv_quelle, "siebenzip_suchen", return_value=""),                     mock.patch.object(self.haupt.messagebox, "showerror") as fehler:
                self.app._archiv_als_quelle(str(archiv))
            fehler.assert_called_once()
            self.assertFalse(getattr(self.app, "_archiv_laeuft", False))

    def test_die_quellwahl_bietet_ordner_und_archiv_an(self) -> None:
        from unittest import mock
        with tempfile.TemporaryDirectory() as t:
            archiv = self._zip(t)
            with mock.patch.object(self.haupt.PS5ConverterGUI, "_auswahl_dialog",
                                   return_value=self.app._t("quelle.art_archiv")) as frage,                     mock.patch.object(self.haupt.filedialog, "askopenfilename", return_value=str(archiv)),                     mock.patch.object(self.app, "_archiv_als_quelle") as uebernehmen:
                self.app._browse_source()
            self.assertEqual(2, len(frage.call_args.args[2]))
            uebernehmen.assert_called_once_with(os.path.normpath(str(archiv)))

    def test_die_texte_gibt_es_in_beiden_sprachen(self) -> None:
        from ps5_validator.utils.i18n import STRINGS
        for schluessel in [k for k in STRINGS if k.startswith("quelle.")] + ["filetype.archive", "dialog.title.choose_archive"]:
            with self.subTest(schluessel=schluessel):
                self.assertTrue(STRINGS[schluessel]["de"].strip() and STRINGS[schluessel]["en"].strip())
                self.assertNotEqual(STRINGS[schluessel]["de"], STRINGS[schluessel]["en"])


if __name__ == "__main__":
    unittest.main()
