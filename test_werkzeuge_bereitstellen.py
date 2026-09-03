# -*- coding: utf-8 -*-
"""Prueft ps5_validator.utils.werkzeuge_bereitstellen.

Sechster Schnitt der Trennung: die MkPFS-Engine und UFS2Tool bereitstellen.
Mit 18 Aufrufstellen der meistgerufene Block, der bisher herausgeloest
wurde.

**Der Schwerpunkt liegt auf den Suchwurzeln**, und das hat einen Grund. Im
Monolithen bildete der Quelltext seine Wurzel mit
``os.path.dirname(os.path.abspath(__file__))``. Aus
``ps5_validator/utils/`` heraus zeigt ``__file__`` woanders hin. Der Fehler
waere fast sicher **nicht** aufgefallen: ``os.getcwd()`` steht in derselben
Liste, also findet ein Start aus dem Projektordner alles weiterhin. Erst
ein Start von woanders liefert einen leeren Pfad - ohne Ausnahme, ohne
Protokollzeile.

Genau dieser Fall wird hier geprueft, und zwar so, wie er auftritt: mit
gewechseltem Arbeitsverzeichnis.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from ps5_validator.utils import werkzeuge_bereitstellen as wb

PROJEKT = Path(__file__).resolve().parent


class SuchwurzelTests(unittest.TestCase):
    """Die Wurzeln muessen den Projektstamm auch von aussen finden."""

    def test_der_projektstamm_ist_dabei(self) -> None:
        self.assertIn(str(PROJEKT), wb.suchwurzeln())

    def test_auch_aus_einem_fremden_arbeitsverzeichnis(self) -> None:
        """Der eigentliche Zweck der vierten Wurzel.

        Ohne sie faende das Modul nach dem Umzug nichts mehr, sobald das
        Programm nicht aus dem Projektordner heraus gestartet wird - und
        zwar lautlos.
        """
        vorher = os.getcwd()
        with tempfile.TemporaryDirectory() as fremd:
            try:
                os.chdir(fremd)
                wurzeln = wb.suchwurzeln()
            finally:
                os.chdir(vorher)
        self.assertIn(str(PROJEKT), wurzeln,
                      "Der Projektstamm faellt aus der Wurzelliste, sobald "
                      "das Arbeitsverzeichnis woanders liegt.")

    def test_keine_doppelten_und_keine_leeren(self) -> None:
        wurzeln = wb.suchwurzeln()
        self.assertEqual(len(wurzeln), len(set(wurzeln)))
        self.assertTrue(all(w for w in wurzeln))

    def test_alle_wurzeln_sind_absolut(self) -> None:
        for wurzel in wb.suchwurzeln():
            with self.subTest(wurzel=wurzel):
                self.assertTrue(os.path.isabs(wurzel))


class KennungTests(unittest.TestCase):
    def test_die_kennung_passt_zu_dieser_plattform(self) -> None:
        kennung = wb.ufs2tool_kennung()
        self.assertIn(kennung, ("win-x64", "linux-x64", "osx-arm64",
                                "osx-x64", ""))

    def test_unter_windows_immer_win_x64(self) -> None:
        if not wb.IST_WINDOWS:
            self.skipTest("nur unter Windows aussagekraeftig")
        self.assertEqual(wb.ufs2tool_kennung(), "win-x64")


class PruefsummeTests(unittest.TestCase):
    """Ein fehlender Pruefwert ist kein Grund abzulehnen - ein falscher schon."""

    def _bauen(self, ordner: str, inhalt: bytes, summe: str | None) -> str:
        pfad = os.path.join(ordner, "UFS2Tool.exe")
        with open(pfad, "wb") as griff:
            griff.write(inhalt)
        if summe is not None:
            with open(os.path.join(ordner, "pruefsummen.json"), "w",
                      encoding="utf-8") as griff:
                json.dump({"plattformen": {"win-x64": {"sha256": summe}}}, griff)
        return pfad

    def test_ohne_liste_wird_nicht_geprueft(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            pfad = self._bauen(ordner, b"egal", None)
            wb.ufs2tool_pruefsumme(ordner, "win-x64", pfad)   # darf nicht werfen

    def test_die_richtige_summe_geht_durch(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            inhalt = b"echte Datei"
            pfad = self._bauen(ordner, inhalt,
                               hashlib.sha256(inhalt).hexdigest())
            wb.ufs2tool_pruefsumme(ordner, "win-x64", pfad)

    def test_eine_falsche_summe_bricht_ab(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            pfad = self._bauen(ordner, b"etwas anderes", "0" * 64)
            with self.assertRaises(RuntimeError):
                wb.ufs2tool_pruefsumme(ordner, "win-x64", pfad)

    def test_eine_unsinnige_summe_wird_uebergangen(self) -> None:
        """Kein 64-stelliger Hex-Wert - dann gibt es nichts zu vergleichen."""
        with tempfile.TemporaryDirectory() as ordner:
            pfad = self._bauen(ordner, b"x", "kein hash")
            wb.ufs2tool_pruefsumme(ordner, "win-x64", pfad)

    def test_eine_kaputte_liste_bricht_nicht_ab(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            pfad = self._bauen(ordner, b"x", None)
            with open(os.path.join(ordner, "pruefsummen.json"), "w",
                      encoding="utf-8") as griff:
                griff.write("{kein json")
            wb.ufs2tool_pruefsumme(ordner, "win-x64", pfad)


class Ufs2toolTests(unittest.TestCase):
    def _wurzel_mit_bau(self, ordner: str) -> str:
        kennung = wb.ufs2tool_kennung() or "win-x64"
        ziel = os.path.join(ordner, kennung)
        os.makedirs(ziel)
        name = "UFS2Tool.exe" if kennung.startswith("win") else "UFS2Tool"
        with open(os.path.join(ziel, name), "wb") as griff:
            griff.write(b"Werkzeug")
        return ordner

    def test_der_gemerkte_pfad_spart_die_suche(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            schon_da = os.path.join(ordner, "UFS2Tool.exe")
            with open(schon_da, "wb") as griff:
                griff.write(b"x")

            def _nie(_name):
                raise AssertionError("Es wurde trotz Zwischenspeicher gesucht.")

            self.assertEqual(
                wb.ufs2tool_bereitstellen(_nie, gemerkt=schon_da), schon_da)

    def test_ein_verschwundener_pfad_loest_neue_suche_aus(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            wurzel = self._wurzel_mit_bau(ordner)
            pfad = wb.ufs2tool_bereitstellen(
                lambda _n: wurzel, gemerkt=os.path.join(ordner, "weg.exe"))
            self.assertTrue(os.path.isfile(pfad))

    def test_der_bau_wird_gefunden(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            wurzel = self._wurzel_mit_bau(ordner)
            pfad = wb.ufs2tool_bereitstellen(lambda _n: wurzel)
            self.assertTrue(os.path.isfile(pfad))
            self.assertIn(wb.ufs2tool_kennung() or "win-x64", pfad)

    def test_ein_fehlender_bau_sagt_welcher_pfad_fehlt(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            with self.assertRaises(RuntimeError) as fall:
                wb.ufs2tool_bereitstellen(lambda _n: ordner)
            self.assertIn("UFS2Tool", str(fall.exception))

    def test_der_ordnername_wird_hereingereicht(self) -> None:
        """wurzel_finden bekommt den mitgelieferten Ordnernamen."""
        gefragt: list[str] = []

        def _merken(name):
            gefragt.append(name)
            return "/gibt/es/nicht"

        with self.assertRaises(RuntimeError):
            wb.ufs2tool_bereitstellen(_merken)
        self.assertEqual(gefragt, [wb.UFS2TOOL_ORDNER])


class MkpfsTests(unittest.TestCase):
    def _zip_bauen(self, ordner: str, fassung: str) -> str:
        pfad = os.path.join(ordner, f"MkPFS-{fassung}.zip")
        with zipfile.ZipFile(pfad, "w") as archiv:
            archiv.writestr("mkpfs/__init__.py", "# Engine\n")
            archiv.writestr("mkpfs/kern.py", "# mehr\n")
        return pfad

    def test_der_mitgelieferte_quellordner_wird_gefunden(self) -> None:
        """Im Projekt liegt MkPFS-1.0.0 - das ist der uebliche Fall."""
        gefunden = wb._quellordner_finden(wb.MKPFS_ERFORDERLICHE_FASSUNG)
        self.assertIsNotNone(gefunden, "Der mitgelieferte Ordner fehlt.")
        self.assertTrue(os.path.isfile(
            os.path.join(gefunden, "mkpfs", "__init__.py")))

    def test_der_quellordner_wird_auch_von_aussen_gefunden(self) -> None:
        """Derselbe Fall, aber mit fremdem Arbeitsverzeichnis."""
        vorher = os.getcwd()
        with tempfile.TemporaryDirectory() as fremd:
            try:
                os.chdir(fremd)
                gefunden = wb._quellordner_finden(wb.MKPFS_ERFORDERLICHE_FASSUNG)
            finally:
                os.chdir(vorher)
        self.assertIsNotNone(
            gefunden,
            "Ausserhalb des Projektordners findet das Modul die Engine nicht "
            "mehr - genau der stille Fehler, den der Umzug vermeiden soll.")

    def test_ohne_quelle_und_ohne_zip_bleibt_es_leer(self) -> None:
        meldungen: list[str] = []
        with tempfile.TemporaryDirectory() as temp:
            ergebnis = wb.mkpfs_bereitstellen(
                temp, fassung="99.99.99", melden=meldungen.append)
        self.assertEqual(ergebnis, "")
        self.assertTrue(any("0010" in m for m in meldungen),
                        "Es fehlt die Meldung, dass nichts gefunden wurde.")

    def test_eine_zip_wird_entpackt(self) -> None:
        meldungen: list[str] = []
        vorher = os.getcwd()
        with tempfile.TemporaryDirectory() as ordner:
            self._zip_bauen(ordner, "99.99.99")
            temp = os.path.join(ordner, "temp")
            os.makedirs(temp)
            try:
                os.chdir(ordner)          # damit die ZIP ueber cwd gefunden wird
                ergebnis = wb.mkpfs_bereitstellen(
                    temp, fassung="99.99.99", melden=meldungen.append)
            finally:
                os.chdir(vorher)
            self.assertTrue(os.path.isdir(os.path.join(ergebnis, "mkpfs")),
                            "Das Paket liegt nicht unter dem Rueckgabepfad.")
        self.assertTrue(any("0012" in m or "0013" in m for m in meldungen))

    def test_ein_zweiter_lauf_nutzt_das_bereits_entpackte(self) -> None:
        vorher = os.getcwd()
        with tempfile.TemporaryDirectory() as ordner:
            self._zip_bauen(ordner, "99.99.99")
            temp = os.path.join(ordner, "temp")
            os.makedirs(temp)
            try:
                os.chdir(ordner)
                erst = wb.mkpfs_bereitstellen(temp, fassung="99.99.99")
                zweite: list[str] = []
                nochmal = wb.mkpfs_bereitstellen(
                    temp, fassung="99.99.99", melden=zweite.append)
            finally:
                os.chdir(vorher)
        self.assertEqual(erst, nochmal)
        self.assertTrue(any("0011" in m for m in zweite),
                        "Der zweite Lauf hat erneut entpackt.")

    def test_ohne_melder_arbeitet_es_trotzdem(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(
                wb.mkpfs_bereitstellen(temp, fassung="99.99.99"), "")


class MonolithTests(unittest.TestCase):
    def test_die_weiterleitungen_stehen_noch(self) -> None:
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8", errors="replace")
        for name in ("_ufs2tool_plattform", "_ufs2tool_pruefsumme",
                     "_extract_ufs2tool", "_extract_embedded_mkpfs"):
            with self.subTest(name=name):
                self.assertIn("def " + name, quelle, name + " fehlt")

    def test_die_beiden_statischen_bleiben_statisch(self) -> None:
        """test_ufs2tool_runtime_bundle ruft sie an der Klasse.

        Ohne @staticmethod rutschte das erste Argument auf self, und die
        Pruefsumme liefe still gegen die falschen Werte.
        """
        from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI

        for name in ("_ufs2tool_plattform", "_ufs2tool_pruefsumme"):
            with self.subTest(name=name):
                self.assertIsInstance(
                    PS5ConverterGUI.__dict__[name], staticmethod)

    def test_mitgeliefert_finden_bleibt_im_monolithen(self) -> None:
        """Es kennt die macOS-Regel zu Contents/Resources.

        test_plattformschicht.py liest dort den Rohquelltext - und die Regel
        stuende im neuen Modul nirgends.
        """
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8", errors="replace")
        self.assertIn("def _mitgeliefert_finden", quelle)

    def test_die_konstanten_stehen_nur_noch_einmal(self) -> None:
        """UFS2TOOL_ORDNER stand zweimal wortgleich in der Datei."""
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8", errors="replace")
        zeilen = [z for z in quelle.splitlines()
                  if z.startswith("UFS2TOOL_ORDNER")]
        self.assertEqual(len(zeilen), 1, "Die Doppelung ist zurueck.")

    def test_das_modul_kennt_keine_oberflaeche(self) -> None:
        quelle = (PROJEKT / "ps5_validator" / "utils"
                  / "werkzeuge_bereitstellen.py").read_text(
                      encoding="utf-8", errors="replace")
        for verboten in ("import tkinter", "tk.", "ttk.", "messagebox"):
            self.assertNotIn(verboten, quelle, "unerwartet: " + verboten)


if __name__ == "__main__":
    unittest.main()


class LaufzeitpaketeTests(unittest.TestCase):
    """Die Pakete, die die Engine zur Laufzeit braucht.

    Diese 84 Zeilen wurden bis zum 31.08.2026 von **keinem einzigen Test
    ausgefuehrt** - der einzige Treffer im Projekt schaltet sie ab
    (``test_ffpfsc_entpacken.py``, ``lambda: True``). Das ist bei Code,
    der ``pip --target`` in einen fremden Ordner startet, die eigentliche
    Gefahr des Umzugs gewesen.
    """

    def test_was_schon_da_ist_wird_nicht_installiert(self) -> None:
        """zstandard und die uebrigen liegen hier - pip bleibt still."""
        gestartet: list = []
        fertig = wb.laufzeitpakete_sicherstellen(
            tempfile.gettempdir(),
            pip_kommando=lambda *a, **k: ["pip"],
            prozess_starten=lambda *a, **k: gestartet.append(a) or (0, ""))
        self.assertTrue(fertig)
        self.assertEqual(gestartet, [],
                         "pip wurde gestartet, obwohl nichts fehlte.")

    def test_ohne_rueckrufe_wirft_es_nicht(self) -> None:
        """Die Vorgaben muessen tragen - sonst platzt es beim ersten Lauf."""
        with self.assertRaises(TypeError):
            wb.laufzeitpakete_sicherstellen(tempfile.gettempdir())

    def test_der_konfigordner_wird_benutzt(self) -> None:
        """Er ist der Ort, an den pip --target installieren wuerde."""
        quelle = (PROJEKT / "ps5_validator" / "utils"
                  / "werkzeuge_bereitstellen.py").read_text(
                      encoding="utf-8", errors="replace")
        anfang = quelle.index("def laufzeitpakete_sicherstellen(")
        self.assertIn("konfigordner", quelle[anfang:anfang + 4000])

    def test_die_weiterleitung_haelt_die_sitzungsflagge(self) -> None:
        """Sie gehoert zur Instanz, nicht zum Werkzeug.

        Ohne sie liefe die Pruefung bei jedem Engine-Start erneut.
        """
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8", errors="replace")
        anfang = quelle.index("def _ensure_mkpfs_runtime_dependencies")
        rumpf = quelle[anfang:quelle.index("\n    def ", anfang + 10)]
        self.assertIn("_mkpfs_runtime_deps_ok", rumpf)
        self.assertIn("laufzeitpakete_sicherstellen", rumpf)
