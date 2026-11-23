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

PROJEKT = Path(__file__).resolve().parent.parent
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
        for teil in ("windows/7z.exe", "windows/7z.dll", "linux-x64/7zz", "macos-arm64/7zz", "macos-x64/7zz", "License.txt"):
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

    def _verschluesselt(self, t: str, passwort: str = "geheim123", endung: str = ".7z") -> tuple[Path, Path]:
        quelle = Path(t) / "q" / "Spiel"
        _spiel(quelle)
        archiv = Path(t) / ("geheim" + endung)
        # CREATE_NO_WINDOW gibt es nur unter Windows - anderswo lehnt subprocess das Argument mit ValueError ab.
        subprocess.run([SIEBENZIP, "a", str(archiv), str(quelle), "-p" + passwort, "-mhe=on", "-bso0", "-bsp0"],
                       check=True, stdin=subprocess.DEVNULL,
                       creationflags=0x08000000 if sys.platform == "win32" else 0)
        return quelle, archiv

    def test_verschluesseltes_archiv_ohne_passwort_meldet_den_passwortfehler(self) -> None:
        """14.10.2026: Eine passwortgeschuetzte .rar brach mit "7-Zip meldet Fehler (Code 255): ... Break signaled" ab -
        7-Zip fragte auf der Konsole nach dem Passwort und las nichts. Jetzt ein eigener Fehler, nach dem das Programm fragt."""
        with tempfile.TemporaryDirectory() as t:
            _quelle, archiv = self._verschluesselt(t)
            with self.assertRaises(archiv_quelle.PasswortFehler):
                archiv_quelle.entpacken(str(archiv), str(Path(t) / "ziel"), wurzeln=[str(PROJEKT)],
                                        popen_extra={"creationflags": 0x08000000})

    def test_falsches_passwort_ist_ein_passwortfehler_und_ersetzt_sich_nicht_still(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            _quelle, archiv = self._verschluesselt(t, passwort="pippo")
            # Ein vom Anwender genanntes Passwort gilt allein - die bekannten kommen dann nicht dazu.
            with self.assertRaises(archiv_quelle.PasswortFehler):
                archiv_quelle.entpacken(str(archiv), str(Path(t) / "ziel"), wurzeln=[str(PROJEKT)],
                                        popen_extra={"creationflags": 0x08000000}, passwort="falsch")

    def test_mit_dem_richtigen_passwort_wird_entpackt(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            quelle, archiv = self._verschluesselt(t)
            wurzel = archiv_quelle.entpacken(str(archiv), str(Path(t) / "ziel"), wurzeln=[str(PROJEKT)],
                                             popen_extra={"creationflags": 0x08000000}, passwort="geheim123")
            for datei in ("eboot.bin", "Media/a.dat", "sce_sys/param.json"):
                self.assertEqual((quelle / datei).read_bytes(), (Path(wurzel) / datei).read_bytes())

    def test_die_bekannten_passwoerter_der_szene_werden_selbst_probiert(self) -> None:
        for passwort in archiv_quelle.BEKANNTE_PASSWOERTER:
            with self.subTest(passwort=passwort), tempfile.TemporaryDirectory() as t:
                quelle, archiv = self._verschluesselt(t, passwort=passwort)
                wurzel = archiv_quelle.entpacken(str(archiv), str(Path(t) / "ziel"), wurzeln=[str(PROJEKT)],
                                                 popen_extra={"creationflags": 0x08000000})
                self.assertEqual((quelle / "eboot.bin").read_bytes(), (Path(wurzel) / "eboot.bin").read_bytes())

    def test_ein_unverschluesseltes_archiv_ignoriert_ein_passwort(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            quelle, archiv = self._bauen(t, ".7z")
            wurzel = archiv_quelle.entpacken(str(archiv), str(Path(t) / "ziel"), wurzeln=[str(PROJEKT)],
                                             popen_extra={"creationflags": 0x08000000}, passwort="irgendwas")
            self.assertEqual((quelle / "eboot.bin").read_bytes(), (Path(wurzel) / "eboot.bin").read_bytes())

    def test_ein_fehlversuch_laesst_nichts_im_entpackordner_zurueck(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            _quelle, archiv = self._verschluesselt(t, passwort="unbekannt-xyz")
            ziel = Path(t) / "ziel"
            with self.assertRaises(archiv_quelle.PasswortFehler):
                archiv_quelle.entpacken(str(archiv), str(ziel), wurzeln=[str(PROJEKT)],
                                        popen_extra={"creationflags": 0x08000000})
            self.assertEqual([], list(ziel.iterdir()))

    def test_rar_endung_geht_den_siebenzip_weg(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            archiv = Path(t) / "x.rar"
            archiv.write_bytes(b"Rar!\x1a\x07\x01\x00" + os.urandom(200))
            with self.assertRaises(archiv_quelle.ArchivFehler) as ctx:
                archiv_quelle.entpacken(str(archiv), str(Path(t) / "ziel"), wurzeln=[str(PROJEKT)],
                                        popen_extra={"creationflags": 0x08000000})
            self.assertIn("7-Zip", str(ctx.exception))


class AbbruchImGrossenEintragTests(unittest.TestCase):
    """Gesamtpruefung 23.11.2026 (Gegenlese): ``z.extract`` einer Datei von mehreren GB lief ohne Abbruchfrage durch; 7-Zip wurde nur
    zwischen zwei Stuecken Ausgabe gefragt. Jetzt: grosse ZIP-Eintraege stueckweise, der 7-Zip-Prozess liegt fuer das Beenden bereit."""

    def test_ein_grosser_zip_eintrag_haelt_beim_abbruch_mitten_drin_an(self) -> None:
        from unittest import mock
        with tempfile.TemporaryDirectory() as t:
            archiv = Path(t) / "spiel.zip"
            with zipfile.ZipFile(archiv, "w", zipfile.ZIP_STORED) as z:
                z.writestr("PPSA01234/sce_sys/param.json", "{}")
                z.writestr("PPSA01234/gross.bin", b"x" * 40_000)
            gefragt = []

            def abbruch() -> bool:
                gefragt.append(1)
                return len(gefragt) > 5            # mitten im grossen Eintrag

            ziel = Path(t) / "ziel"
            with mock.patch.object(archiv_quelle, "_STROM_AB", 1000), mock.patch.object(archiv_quelle, "_STROM_STUECK", 4096):
                with self.assertRaises(archiv_quelle.ArchivFehler) as f:
                    archiv_quelle.entpacken(str(archiv), str(ziel), abbruch=abbruch)
            self.assertIn("abgebrochen", str(f.exception))
            halb = ziel / "PPSA01234" / "gross.bin"
            self.assertLess(halb.stat().st_size, 40_000, "abgebrochen mitten in der Datei, nicht danach")
            # Gegenprobe: ohne Abbruch kommt die Datei ganz und gleich an
            ziel2 = Path(t) / "ziel2"
            with mock.patch.object(archiv_quelle, "_STROM_AB", 1000), mock.patch.object(archiv_quelle, "_STROM_STUECK", 4096):
                archiv_quelle.entpacken(str(archiv), str(ziel2))
            self.assertEqual(b"x" * 40_000, (ziel2 / "PPSA01234" / "gross.bin").read_bytes())

    def test_ein_name_mit_sonderzeichen_geht_den_gewohnten_weg(self) -> None:
        self.assertTrue(archiv_quelle._name_schlicht("PPSA01234/data/a.bin"))
        for name in ("a/b:c.bin", "a/..", "punkt./x", "", "a/x?.bin"):
            with self.subTest(name=name):
                self.assertFalse(archiv_quelle._name_schlicht(name))

    @unittest.skipUnless(SIEBENZIP, "7-Zip fehlt")
    def test_der_siebenzip_prozess_liegt_in_der_ablage(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            quelle = Path(t) / "q" / "PPSA01234"
            _spiel(quelle)
            archiv = Path(t) / "spiel.7z"
            subprocess.run([SIEBENZIP, "a", str(archiv), str(quelle), "-bso0", "-bsp0"], check=True, stdin=subprocess.DEVNULL,
                           creationflags=0x08000000 if sys.platform == "win32" else 0)
            ablage: dict = {}
            archiv_quelle.entpacken(str(archiv), str(Path(t) / "ziel"), wurzeln=[str(PROJEKT)], prozess_ablage=ablage)
            self.assertIn("prozess", ablage)
            self.assertEqual(0, ablage["prozess"].returncode)


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

    def test_beenden_waehrend_des_entpackens_fragt_haelt_an_und_raeumt_weg(self) -> None:
        """Gesamtpruefung 23.11.2026: Schliessen waehrend des Entpackens kam ohne Rueckfrage durch, 7-Zip lief weiter, der halbe
        Entpackordner blieb liegen. Jetzt zaehlt das Entpacken als laufende Arbeit (Rueckfrage beim Beenden), ``on_closing`` setzt
        ``_archiv_abbruch``, und der Faden raeumt den Ordner selbst weg - ohne Fehlermeldung."""
        import inspect
        import threading as _threading
        from unittest import mock
        gestartet = _threading.Event()

        def entpacken_bis_zum_abbruch(archiv, ziel, *, abbruch=None, **_k):
            Path(ziel, "halb.bin").write_bytes(b"x" * 100)
            gestartet.set()
            while not (abbruch and abbruch()):
                self.time.sleep(0.01)
            raise self.haupt.archiv_quelle.ArchivFehler("abgebrochen")

        with tempfile.TemporaryDirectory() as t:
            archiv = Path(t) / "gross.7z"
            archiv.write_bytes(b"7z")
            self.addCleanup(setattr, self.app, "_archiv_laeuft", False)
            with mock.patch.object(self.haupt.archiv_quelle, "siebenzip_suchen", return_value="7z.exe"), \
                    mock.patch.object(self.haupt.archiv_quelle, "entpacken", entpacken_bis_zum_abbruch), \
                    mock.patch.object(self.haupt.PS5ConverterGUI, "_archiv_braucht_entpacken", return_value=False), \
                    mock.patch.object(self.haupt.messagebox, "showerror") as fehler:
                self.app._archiv_als_quelle(str(archiv))
                self.assertTrue(gestartet.wait(10))
                ordner = self.app._archiv_ordner
                self.assertTrue(os.path.isdir(ordner))
                self.assertTrue(self.app._arbeit_laeuft(), "das Entpacken zaehlt beim Beenden als laufende Arbeit")
                self.app._archiv_abbruch.set()                          # was on_closing nach dem "Ja" tut
                self.app._archiv_faden.join(10)
                self.assertFalse(self.app._archiv_faden.is_alive())
                self.assertFalse(os.path.isdir(ordner), "der halbe Entpackordner ist weg")
                while self.offen:
                    rueckruf, args = self.offen.pop(0)
                    rueckruf(*args)
            fehler.assert_not_called()
        quelle = inspect.getsource(self.haupt.PS5ConverterGUI.on_closing)
        self.assertIn("_archiv_abbruch.set()", quelle)
        self.assertIn("_archiv_faden.join(", quelle)
        self.assertIn("_siebenzip.kill()", quelle, "7-Zip wird beim Beenden sofort angehalten (Gegenlese 23.11.2026)")
        self.assertIn("_beenden_faden", quelle, "ein zweiter Klick auf X startet keinen zweiten Abbau")

    def test_beenden_kurz_nach_dem_entpacken_meldet_nichts_und_raeumt_weg(self) -> None:
        """Gegenlese 23.11.2026: Das Entpacken war schon fertig, als beendet wurde - trotzdem lief _archiv_fertig mitten im Abbau
        (setzte die Quelle oder zeigte eine Meldung), und der Entpackordner blieb liegen."""
        import threading as _threading
        from unittest import mock
        gestartet = _threading.Event()

        def entpacken_fertig_beim_abbruch(archiv, ziel, *, abbruch=None, **_k):
            spiel = Path(ziel, "PPSA01234")
            (spiel / "sce_sys").mkdir(parents=True)
            (spiel / "sce_sys" / "param.json").write_text("{}", encoding="utf-8")
            gestartet.set()
            while not (abbruch and abbruch()):
                self.time.sleep(0.01)
            return str(spiel)                                   # fertig - der Abbruch kam erst danach

        with tempfile.TemporaryDirectory() as t:
            archiv = Path(t) / "fertig.7z"
            archiv.write_bytes(b"7z")
            self.addCleanup(setattr, self.app, "_archiv_laeuft", False)
            self.app.source_path.set("VORHER")
            with mock.patch.object(self.haupt.archiv_quelle, "siebenzip_suchen", return_value="7z.exe"), \
                    mock.patch.object(self.haupt.archiv_quelle, "entpacken", entpacken_fertig_beim_abbruch), \
                    mock.patch.object(self.haupt.PS5ConverterGUI, "_archiv_braucht_entpacken", return_value=False), \
                    mock.patch.object(self.haupt.PS5ConverterGUI, "_archiv_fertig") as fertig:
                self.app._archiv_als_quelle(str(archiv))
                self.assertTrue(gestartet.wait(10))
                ordner = self.app._archiv_ordner
                self.app._archiv_abbruch.set()
                self.app._archiv_faden.join(10)
                while self.offen:
                    rueckruf, args = self.offen.pop(0)
                    rueckruf(*args)
            fertig.assert_not_called()
            self.assertFalse(os.path.isdir(ordner))

    def test_waehrend_eines_laufs_kein_neues_archiv(self) -> None:
        """Gesamtpruefung 14.11.2026, A5: Ein neues Archiv raeumte den Entpackordner des alten weg - vielleicht die laufende Quelle."""
        from unittest import mock
        with tempfile.TemporaryDirectory() as t:
            archiv = self._zip(t)
            alt = Path(t) / "ps5conv_archiv_alt"
            alt.mkdir()
            vorher = getattr(self.app, "_archiv_ordner", "")
            self.app._archiv_ordner = str(alt)
            self.addCleanup(setattr, self.app, "_archiv_ordner", vorher)
            self.app.source_path.set("VORHER")
            self.app.is_running = True
            self.addCleanup(setattr, self.app, "is_running", False)
            with mock.patch.object(self.haupt.messagebox, "showwarning") as warnung:
                self.app._archiv_als_quelle(str(archiv))
            warnung.assert_called_once()
            self.assertTrue(alt.is_dir(), "der Entpackordner des laufenden Archivs bleibt")
            self.assertEqual("VORHER", self.app.source_path.get())
            self.assertFalse(getattr(self.app, "_archiv_laeuft", False))

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

    def _verschluesseltes_spiel(self, t: str, passwort: str = "geheim123") -> Path:
        quelle = Path(t) / "q" / "PPSA01234"
        _spiel(quelle)
        archiv = Path(t) / "geheim.7z"
        # CREATE_NO_WINDOW gibt es nur unter Windows - anderswo lehnt subprocess das Argument mit ValueError ab.
        subprocess.run([SIEBENZIP, "a", str(archiv), str(quelle), "-p" + passwort, "-mhe=on", "-bso0", "-bsp0"],
                       check=True, stdin=subprocess.DEVNULL,
                       creationflags=0x08000000 if sys.platform == "win32" else 0)
        return archiv

    def test_ein_archiv_mit_bekanntem_passwort_wird_ohne_rueckfrage_zur_quelle(self) -> None:
        from unittest import mock
        with tempfile.TemporaryDirectory() as t:
            archiv = self._verschluesseltes_spiel(t, "DLPSGAME.COM")
            self.app.source_path.set("")
            with mock.patch.object(self.haupt.PS5ConverterGUI, "_passwort_dialog") as frage:
                self.app._archiv_als_quelle(str(archiv))
                self._warten()
                self._warten()
            self.addCleanup(lambda: __import__("shutil").rmtree(self.app._archiv_ordner, ignore_errors=True))
            frage.assert_not_called()
            self.assertTrue(self.app.source_path.get().endswith("PPSA01234"), self.app.source_path.get())

    def test_ein_unbekanntes_passwort_wird_erfragt_und_ein_falsches_noch_einmal(self) -> None:
        from unittest import mock
        with tempfile.TemporaryDirectory() as t:
            archiv = self._verschluesseltes_spiel(t)
            self.app.source_path.set("")
            with mock.patch.object(self.haupt.PS5ConverterGUI, "_passwort_dialog",
                                   side_effect=["falsch", "geheim123"]) as frage:
                for _ in range(4):
                    if _ == 0:
                        self.app._archiv_als_quelle(str(archiv))
                    self._warten()
            self.addCleanup(lambda: __import__("shutil").rmtree(self.app._archiv_ordner, ignore_errors=True))
            self.assertEqual(2, frage.call_count, "Erst unbekannt, dann falsch: zweimal gefragt")
            self.assertTrue(self.app.source_path.get().endswith("PPSA01234"), self.app.source_path.get())

    def test_ein_abgebrochenes_passwortfenster_laesst_die_quelle_stehen(self) -> None:
        from unittest import mock
        with tempfile.TemporaryDirectory() as t:
            archiv = self._verschluesseltes_spiel(t)
            self.app.source_path.set("VORHER")
            with mock.patch.object(self.haupt.PS5ConverterGUI, "_passwort_dialog", return_value="") as frage:
                self.app._archiv_als_quelle(str(archiv))
                self._warten()
                self._warten()
            frage.assert_called_once()
            self.assertEqual("VORHER", self.app.source_path.get())
            self.assertFalse(getattr(self.app, "_archiv_laeuft", False))
            self.assertFalse(os.path.isdir(self.app._archiv_ordner), "Der halbe Entpackordner wird weggeraeumt")

    def test_dump_ordner_oeffnet_ohne_zwischenfrage_gleich_die_ordnerwahl(self) -> None:
        """14.10.2026: Die Zwischenfrage "Ordner oder Archiv" entfaellt; das Archiv waehlt der Knopf daneben."""
        from unittest import mock
        self.app.current_mode.set("pack_folder")
        with tempfile.TemporaryDirectory() as t, \
                mock.patch.object(self.haupt.PS5ConverterGUI, "_auswahl_dialog") as frage, \
                mock.patch.object(self.haupt.filedialog, "askdirectory", return_value=t) as ordner, \
                mock.patch.object(self.haupt.PS5ConverterGUI, "_validate_source_path", return_value=""):
            self.app._browse_source()
        frage.assert_not_called()
        ordner.assert_called_once()

    def test_der_archivknopf_waehlt_ein_archiv_und_uebernimmt_es(self) -> None:
        from unittest import mock
        with tempfile.TemporaryDirectory() as t:
            archiv = self._zip(t)
            with mock.patch.object(self.haupt.filedialog, "askopenfilename", return_value=str(archiv)) as datei, \
                    mock.patch.object(self.app, "_archiv_als_quelle") as uebernehmen:
                self.app._browse_archiv()
            self.assertIn("*.zip *.7z *.rar", str(datei.call_args.kwargs["filetypes"]))
            uebernehmen.assert_called_once_with(os.path.normpath(str(archiv)))

    def test_ein_abgebrochener_archivdialog_aendert_nichts(self) -> None:
        from unittest import mock
        with mock.patch.object(self.haupt.filedialog, "askopenfilename", return_value=""), \
                mock.patch.object(self.app, "_archiv_als_quelle") as uebernehmen:
            self.app._browse_archiv()
        uebernehmen.assert_not_called()

    def test_der_archivknopf_steht_nur_bei_aufgabe_1_neben_dump_ordner(self) -> None:
        app = self.app
        _WURZEL.deiconify()
        self.addCleanup(_WURZEL.withdraw)
        app.current_mode.set("pack_folder")
        app._src_archiv_stand = None
        for _ in range(4):          # Platz machen verschiebt "Dump Ordner": erst nach dem Nachziehen stimmt es
            _WURZEL.update()
            app._src_archiv_platzieren()
        _WURZEL.update()
        knopf, haupt = app.src_archiv_btn, app.src_browse_btn
        self.assertEqual("place", knopf.winfo_manager(), "Aufgabe 1: der Archiv-Knopf ist da")
        self.assertLess(knopf.winfo_x() + knopf.winfo_reqwidth(), haupt.winfo_x(), "links neben Dump Ordner")
        self.assertEqual(haupt.winfo_y(), knopf.winfo_y())
        app.current_mode.set("pack_folder")
        for modus in ("unpack_to_exfat", "batch_convert", "dump_validator"):
            with self.subTest(modus=modus):
                app.current_mode.set(modus)
                app._src_archiv_stand = None
                app._src_archiv_platzieren()
                self.assertEqual("", knopf.winfo_manager(), "Nur Aufgabe 1 hat den Archiv-Knopf")
        app.current_mode.set("pack_folder")
        app._src_archiv_stand = None
        app._src_archiv_platzieren()

    def test_die_texte_gibt_es_in_beiden_sprachen(self) -> None:
        from ps5_validator.utils.i18n import STRINGS
        for schluessel in [k for k in STRINGS if k.startswith("quelle.")] + ["filetype.archive", "dialog.title.choose_archive"]:
            with self.subTest(schluessel=schluessel):
                self.assertTrue(STRINGS[schluessel]["de"].strip() and STRINGS[schluessel]["en"].strip())
                self.assertNotEqual(STRINGS[schluessel]["de"], STRINGS[schluessel]["en"])


if __name__ == "__main__":
    unittest.main()
