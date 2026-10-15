# -*- coding: utf-8 -*-
"""Mitgelieferte Packprofile (ASTRO BOT, UFC 6, Unity, Insomniac).

Die Profile stammen aus danthespal/MkPFS.CSharp (GPL-3.0). Geprueft wird,
dass sie lesbar sind, dass ``profil_integriert_fuer`` die richtigen Titel
erkennt - und nur die -, dass ein Profil des Anwenders nie ueberschrieben
wird und dass das echte Packwerkzeug sie annimmt.
"""
from __future__ import annotations

import json
import os
import struct
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))
sys.path.insert(0, str(PROJEKT / "MkPFS-1.1.0"))
sys.path.insert(0, str(PROJEKT / "AMPR_PackTools-4.0"))

from ps5_validator.utils import ampr_assetpakete as ap  # noqa: E402


def _sfo(title_id: str) -> bytes:
    """Kleinste gueltige param.sfo mit einem Eintrag TITLE_ID."""
    schluessel = b"TITLE_ID\x00"
    daten = title_id.encode("ascii") + b"\x00" * (16 - len(title_id))
    schl_start = 0x14 + 16
    dat_start = schl_start + len(schluessel)
    kopf = b"\x00PSF" + struct.pack("<I", 0x101) + struct.pack(
        "<III", schl_start, dat_start, 1)
    eintrag = struct.pack("<HHIII", 0, 0x204, len(title_id) + 1, 16, 0)
    return kopf + eintrag + schluessel + daten


def _spiel(wurzel: Path, title_id: str = "") -> Path:
    app0 = wurzel / "app0"
    (app0 / "sce_sys").mkdir(parents=True)
    (app0 / "eboot.bin").write_bytes(b"\x7fELF" + b"\x00" * 2048)
    if title_id:
        (app0 / "sce_sys" / "param.sfo").write_bytes(_sfo(title_id))
    return app0


class ProfileSindLesbar(unittest.TestCase):
    def test_index_nennt_jede_datei_und_jede_datei_ist_toml(self):
        index = json.loads(Path(ap.PROFIL_ORDNER, "index.json").read_text("utf-8"))
        text = json.dumps(index)
        for dateiname in ap.MITGELIEFERTE_PROFILE.values():
            with self.subTest(profil=dateiname):
                pfad = Path(ap.PROFIL_ORDNER, dateiname)
                self.assertTrue(pfad.is_file(), "%s fehlt" % dateiname)
                self.assertIn(dateiname, text, "index.json kennt %s nicht" % dateiname)
                daten = tomllib.loads(pfad.read_text("utf-8"))
                self.assertIn("pack", daten)
                self.assertTrue(daten.get("rule"), "%s hat keine Regeln" % dateiname)


class Erkennung(unittest.TestCase):
    def _erkannt(self, app0: Path) -> str:
        return ap.profil_integriert_fuer(str(app0))[0]

    def test_title_id_aus_sfo(self):
        with tempfile.TemporaryDirectory() as basis:
            app0 = _spiel(Path(basis), "PPSA21567")
            self.assertEqual("PPSA21567", ap.title_id_aus_sfo(str(app0)))

    def test_title_ids_der_beiden_einzelprofile(self):
        for title_id, profil in (("PPSA21567", "astrobot.toml"),
                                 ("PPSA23566", "ufc6-PPSA23566.toml")):
            with self.subTest(title_id=title_id), tempfile.TemporaryDirectory() as basis:
                app0 = _spiel(Path(basis), title_id)
                name, pfad = ap.profil_integriert_fuer(str(app0))
                self.assertEqual(title_id, name)
                self.assertEqual(profil, os.path.basename(pfad))

    def test_fremde_title_id_ohne_merkmale_bekommt_nichts(self):
        with tempfile.TemporaryDirectory() as basis:
            app0 = _spiel(Path(basis), "PPSA00001")
            self.assertEqual(("", ""), ap.profil_integriert_fuer(str(app0)))

    def test_kaputte_oder_fehlende_sfo_wirft_nicht(self):
        with tempfile.TemporaryDirectory() as basis:
            app0 = _spiel(Path(basis))
            self.assertEqual("", ap.title_id_aus_sfo(str(app0)))
            (app0 / "sce_sys" / "param.sfo").write_bytes(b"\x00PSF" + b"\xff" * 40)
            self.assertEqual("", ap.title_id_aus_sfo(str(app0)))
            self.assertEqual(("", ""), ap.profil_integriert_fuer(""))

    def test_unity_an_den_metadaten(self):
        with tempfile.TemporaryDirectory() as basis:
            app0 = _spiel(Path(basis), "PPSA00002")
            daten = app0 / "Media" / "il2cpp_data" / "Metadata"
            daten.mkdir(parents=True)
            (daten / "global-metadata.dat").write_bytes(b"x" * 64)
            self.assertEqual("Unity", self._erkannt(app0))

    def test_insomniac_braucht_dag_toc_und_d_an_der_wurzel(self):
        with tempfile.TemporaryDirectory() as basis:
            app0 = _spiel(Path(basis), "PPSA00003")
            (app0 / "dag").write_bytes(b"x")
            (app0 / "toc").write_bytes(b"x")
            self.assertEqual("", self._erkannt(app0), "ohne d/ ist es kein Insomniac")
            (app0 / "d").mkdir()
            self.assertEqual("Insomniac", self._erkannt(app0))

    def test_viele_toc_dateien_in_unterordnern_sind_kein_insomniac(self):
        """Frostbite (UFC 6) hat reichlich .toc - das darf nichts ausloesen."""
        with tempfile.TemporaryDirectory() as basis:
            app0 = _spiel(Path(basis), "PPSA00004")
            (app0 / "Data" / "Win32").mkdir(parents=True)
            for i in range(5):
                (app0 / "Data" / "Win32" / ("layout%d.toc" % i)).write_bytes(b"x")
            (app0 / "Data" / "toc").write_bytes(b"x")
            (app0 / "Data" / "dag").write_bytes(b"x")
            (app0 / "d").mkdir()
            self.assertEqual("", self._erkannt(app0))


class Schreiben(unittest.TestCase):
    def test_integriertes_profil_traegt_die_kennzeile_und_wird_erneuert(self):
        with tempfile.TemporaryDirectory() as basis:
            wurzel = Path(basis)
            app0 = _spiel(wurzel, "PPSA21567")
            ziel = str(wurzel / "ampr_pack.toml")
            ap.profil_schreiben(ziel, 2, str(app0))
            erste = Path(ziel).read_text("utf-8").splitlines()[0]
            self.assertTrue(erste.startswith(ap.PROFIL_KENNZEILE), erste)
            self.assertIn("PPSA21567", erste)
            self.assertTrue(ap.profil_ist_eigenes(ziel))
            tomllib.loads(Path(ziel).read_text("utf-8"))
            # Wird beim naechsten Lauf neu geschrieben, nicht als fremd behandelt.
            Path(ziel).write_text(Path(ziel).read_text("utf-8") + "\n# alt\n", "utf-8")
            ap.profil_schreiben(ziel, 2, str(app0))
            self.assertNotIn("# alt", Path(ziel).read_text("utf-8"))

    def test_profil_des_anwenders_bleibt_auch_bei_bekanntem_titel(self):
        with tempfile.TemporaryDirectory() as basis:
            wurzel = Path(basis)
            app0 = _spiel(wurzel, "PPSA21567")
            ziel = wurzel / "ampr_pack.toml"
            eigenes = "# mein eigenes Profil\n[pack]\ndefault_action = \"loose\"\n"
            ziel.write_text(eigenes, "utf-8")
            ap.profil_schreiben(str(ziel), 2, str(app0))
            self.assertEqual(eigenes, ziel.read_text("utf-8"))
            self.assertFalse(ap.profil_ist_eigenes(str(ziel)))

    def test_unbekannter_titel_bekommt_das_standardprofil(self):
        with tempfile.TemporaryDirectory() as basis:
            wurzel = Path(basis)
            app0 = _spiel(wurzel, "PPSA00001")
            ziel = str(wurzel / "ampr_pack.toml")
            ap.profil_schreiben(ziel, 0, str(app0))
            self.assertNotIn("integriertes Profil",
                             Path(ziel).read_text("utf-8").splitlines()[0])
            self.assertEqual("loose", tomllib.loads(
                Path(ziel).read_text("utf-8"))["pack"]["default_action"])


@unittest.skipUnless(ap.einsatzbereit()[0], "Packwerkzeug oder lz4 fehlt")
class EchterPacklauf(unittest.TestCase):
    """Das echte Packwerkzeug nimmt jedes mitgelieferte Profil an."""

    def _packen(self, titel: str, marker) -> dict:
        from test_ampr_assetpakete import _index_bauen
        with tempfile.TemporaryDirectory(prefix="ampr_profil_") as basis:
            wurzel = Path(basis)
            app0 = _spiel(wurzel, titel)
            (app0 / "assets").mkdir()
            for i in range(3):
                (app0 / "assets" / ("t%d.dat" % i)).write_bytes(
                    ((b"ABCDEFGH" * 512) + bytes([i])) * 24)
            marker(app0)
            index = _index_bauen(app0)
            profil = ap.profil_schreiben(str(wurzel / "profil.toml"), 2, str(app0))
            self.assertIn("integriertes Profil",
                          Path(profil).read_text("utf-8").splitlines()[0])
            ergebnis = ap.packen(str(app0), str(index), str(wurzel / "packed"), profil)
            lose = set(ergebnis.get("loose_paths") or [])
            self.assertIn("eboot.bin", lose, "eboot.bin darf nie in ein Band")
            return ergebnis

    def test_astrobot(self):
        self._packen("PPSA21567", lambda app0: None)

    def test_ufc6(self):
        self._packen("PPSA23566", lambda app0: None)

    def test_unity(self):
        def marke(app0):
            ordner = app0 / "Media" / "il2cpp_data" / "Metadata"
            ordner.mkdir(parents=True)
            (ordner / "global-metadata.dat").write_bytes(b"x" * 64)
            (app0 / "Media" / "StreamingAssets").mkdir()
            (app0 / "Media" / "StreamingAssets" / "a.bin").write_bytes(
                b"PACKBAR " * 4096)
        self._packen("PPSA00002", marke)

    def test_insomniac(self):
        def marke(app0):
            (app0 / "dag").write_bytes(b"x" * 64)
            (app0 / "toc").write_bytes(b"x" * 64)
            (app0 / "d").mkdir()
            (app0 / "d" / "x.bin").write_bytes(b"PACKBAR " * 4096)
        self._packen("PPSA00003", marke)


if __name__ == "__main__":
    unittest.main()
