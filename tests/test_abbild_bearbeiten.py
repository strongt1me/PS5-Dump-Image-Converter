# -*- coding: utf-8 -*-
"""Abbild bearbeiten: die Dateiarbeit im entpackten Spielordner (``utils/abbild_bearbeiten.py``)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import abbild_bearbeiten as ab   # noqa: E402


class _Basis(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.t = Path(tmp.name)
        self.w = self.t / "Spiel"
        for rel, daten in {
            "eboot.bin": b"ELF-eboot",
            "sce_sys/param.json": b"{}",
            "sce_sys/icon0.png": b"PNG",
            "Media/a.dat": b"aaa",
            "Media/Sub/b.dat": b"bbb",
        }.items():
            voll = self.w / rel
            voll.parent.mkdir(parents=True, exist_ok=True)
            voll.write_bytes(daten)
        self.w_s = str(self.w)

    def grund(self, funktion, *args, **kw) -> str:
        with self.assertRaises(ab.BearbeitenFehler) as ctx:
            funktion(*args, **kw)
        return ctx.exception.schluessel


class NamenTests(unittest.TestCase):
    def test_gueltige_namen(self) -> None:
        for name in ("a.txt", "Datei mit Leerzeichen.bin", "ä.dat", ".hidden", "x"):
            self.assertEqual(name, ab.name_pruefen(name))

    def test_ungueltige_namen(self) -> None:
        faelle = {
            "": "bearbeiten.name_leer", "   ": "bearbeiten.name_leer",
            ".": "bearbeiten.name_ungueltig", "..": "bearbeiten.name_ungueltig",
            "a/b": "bearbeiten.name_ungueltig", "a\\b": "bearbeiten.name_ungueltig",
            "a:b": "bearbeiten.name_ungueltig", "a*b": "bearbeiten.name_ungueltig",
            "a?b": "bearbeiten.name_ungueltig", "a\x01b": "bearbeiten.name_ungueltig",
            "ende.": "bearbeiten.name_ungueltig", " vorn": "bearbeiten.name_ungueltig",
            "hinten ": "bearbeiten.name_ungueltig",
            "CON": "bearbeiten.name_reserviert", "nul.txt": "bearbeiten.name_reserviert",
            "Com3": "bearbeiten.name_reserviert", "x" * 256: "bearbeiten.name_zu_lang",
        }
        for name, schluessel in faelle.items():
            with self.subTest(name=name[:20]):
                with self.assertRaises(ab.BearbeitenFehler) as ctx:
                    ab.name_pruefen(name)
                self.assertEqual(schluessel, ctx.exception.schluessel)

    def test_kein_text_ist_ungueltig(self) -> None:
        with self.assertRaises(ab.BearbeitenFehler):
            ab.name_pruefen(None)       # type: ignore[arg-type]


class PfadTests(_Basis):
    def test_normalisieren(self) -> None:
        self.assertEqual("", ab.rel_normalisieren(""))
        self.assertEqual("", ab.rel_normalisieren("."))
        self.assertEqual("", ab.rel_normalisieren("/"))
        self.assertEqual("Media/a.dat", ab.rel_normalisieren("Media\\a.dat"))
        self.assertEqual("Media/a.dat", ab.rel_normalisieren("Media//./a.dat/"))
        self.assertEqual("bearbeiten.pfad_ausserhalb", self.grund(ab.rel_normalisieren, "/Media/a.dat"),
                         "ein fuehrender Schraegstrich ist ein absoluter Pfad")

    def test_ausbruchsversuche(self) -> None:
        for rel in ("../x", "Media/../../x", "..", "C:/Windows", "C:x", "\\\\server\\share", "//server/share"):
            with self.subTest(rel=rel):
                self.assertEqual("bearbeiten.pfad_ausserhalb", self.grund(ab.aufloesen, self.w_s, rel))

    def test_aufloesen_bleibt_in_der_wurzel(self) -> None:
        pfad = ab.aufloesen(self.w_s, "Media/a.dat")
        self.assertTrue(os.path.samefile(pfad, self.w / "Media" / "a.dat"))
        self.assertEqual(os.path.realpath(self.w_s), os.path.realpath(ab.aufloesen(self.w_s, "")))

    def _verknuepfung_anlegen(self, ziel: Path, link: Path) -> None:
        try:
            os.symlink(ziel, link, target_is_directory=True)
            return
        except (OSError, NotImplementedError):
            pass
        if sys.platform != "win32":
            self.skipTest("Verknuepfungen nicht erlaubt")
        # Windows ohne Entwicklermodus: eine Junction braucht kein Recht und wird genauso behandelt.
        import subprocess
        erg = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(ziel)], capture_output=True)
        if erg.returncode != 0:
            self.skipTest("weder Symlink noch Junction anlegbar")

    def test_verknuepfung_wird_abgewiesen(self) -> None:
        aussen = self.t / "aussen"
        aussen.mkdir()
        (aussen / "geheim.txt").write_text("x")
        self._verknuepfung_anlegen(aussen, self.w / "Media" / "weg")
        self.assertEqual("bearbeiten.verknuepfung", self.grund(ab.aufloesen, self.w_s, "Media/weg/geheim.txt"))
        self.assertEqual("bearbeiten.verknuepfung", self.grund(ab.loeschen, self.w_s, "Media/weg/geheim.txt"))
        self.assertTrue((aussen / "geheim.txt").exists(), "ausserhalb bleibt alles heil")


class AuflistenTests(_Basis):
    def test_baum(self) -> None:
        eintraege = ab.auflisten(self.w_s)
        rels = [e.rel for e in eintraege]
        self.assertEqual(sorted(rels, key=lambda r: r.lower()), sorted(rels, key=lambda r: r.lower()))
        self.assertIn("Media", rels)
        self.assertLess(rels.index("Media"), rels.index("Media/a.dat"), "Ordner vor ihrem Inhalt")
        self.assertLess(rels.index("Media/Sub"), rels.index("Media/Sub/b.dat"))
        ordner = {e.rel for e in eintraege if e.ist_ordner}
        self.assertEqual({"Media", "Media/Sub", "sce_sys"}, ordner)
        groessen = {e.rel: e.groesse for e in eintraege if not e.ist_ordner}
        self.assertEqual(9, groessen["eboot.bin"])
        self.assertEqual(3, groessen["Media/a.dat"])

    def test_fehlender_ordner_ist_leer(self) -> None:
        self.assertEqual([], ab.auflisten(str(self.t / "gibt_es_nicht")))


class LoeschenTests(_Basis):
    def test_datei_loeschen(self) -> None:
        p = ab.Protokoll()
        ab.loeschen(self.w_s, "Media/a.dat", protokoll=p)
        self.assertFalse((self.w / "Media" / "a.dat").exists())
        self.assertEqual([ab.Aenderung("loeschen", "Media/a.dat")], p.aenderungen)

    def test_loeschen_meldet_vor_dem_loeschen(self) -> None:
        gemeldet: list[tuple[str, bool]] = []
        ab.loeschen(self.w_s, "Media/a.dat",
                    melden=lambda rel: gemeldet.append((rel, (self.w / "Media" / "a.dat").exists())))
        self.assertEqual([("Media/a.dat", True)], gemeldet, "gemeldet wird, solange die Datei noch da ist")
        # Abgelehntes (geschuetzt) meldet nichts - es wird ja nichts geloescht
        gemeldet.clear()
        self.assertEqual("bearbeiten.geschuetzt", self.grund(ab.loeschen, self.w_s, "eboot.bin", melden=gemeldet.append))
        self.assertEqual([], gemeldet)

    def test_ordner_loeschen(self) -> None:
        ab.loeschen(self.w_s, "Media")
        self.assertFalse((self.w / "Media").exists())
        self.assertTrue((self.w / "eboot.bin").exists())

    def test_geschuetztes_nur_mit_erzwingen(self) -> None:
        for rel in ("eboot.bin", "EBOOT.BIN", "sce_sys/param.json", "sce_sys", "sce_sys/"):
            with self.subTest(rel=rel):
                self.assertEqual("bearbeiten.geschuetzt", self.grund(ab.loeschen, self.w_s, rel))
        self.assertTrue((self.w / "eboot.bin").exists())
        self.assertTrue((self.w / "sce_sys" / "param.json").exists())
        ab.loeschen(self.w_s, "eboot.bin", erzwingen=True)
        self.assertFalse((self.w / "eboot.bin").exists())

    def test_ungeschuetzte_datei_im_geschuetzten_ordner(self) -> None:
        ab.loeschen(self.w_s, "sce_sys/icon0.png")
        self.assertFalse((self.w / "sce_sys" / "icon0.png").exists())
        self.assertTrue((self.w / "sce_sys" / "param.json").exists())

    def test_fehler(self) -> None:
        self.assertEqual("bearbeiten.wurzel", self.grund(ab.loeschen, self.w_s, ""))
        self.assertEqual("bearbeiten.nicht_gefunden", self.grund(ab.loeschen, self.w_s, "Media/gibts.dat"))
        self.assertEqual("bearbeiten.pfad_ausserhalb", self.grund(ab.loeschen, self.w_s, "../Spiel"))
        self.assertTrue(self.w.exists())

    def test_ein_io_fehler_wird_gemeldet_und_nicht_protokolliert(self) -> None:
        p = ab.Protokoll()
        with mock.patch.object(ab.os, "unlink", side_effect=PermissionError("gesperrt")):
            self.assertEqual("bearbeiten.io", self.grund(ab.loeschen, self.w_s, "Media/a.dat", protokoll=p))
        self.assertEqual(0, p.anzahl())
        self.assertTrue((self.w / "Media" / "a.dat").exists())


class UmbenennenTests(_Basis):
    def test_datei_umbenennen(self) -> None:
        p = ab.Protokoll()
        neu = ab.umbenennen(self.w_s, "Media/a.dat", "z.dat", protokoll=p)
        self.assertEqual("Media/z.dat", neu)
        self.assertFalse((self.w / "Media" / "a.dat").exists())
        self.assertEqual(b"aaa", (self.w / "Media" / "z.dat").read_bytes())
        self.assertEqual([ab.Aenderung("umbenennen", "Media/a.dat", "Media/z.dat")], p.aenderungen)

    def test_ordner_umbenennen_nimmt_den_inhalt_mit(self) -> None:
        self.assertEqual("Medien", ab.umbenennen(self.w_s, "Media", "Medien"))
        self.assertEqual(b"bbb", (self.w / "Medien" / "Sub" / "b.dat").read_bytes())

    def test_nur_die_schreibung_aendern(self) -> None:
        self.assertEqual("Media/A.DAT", ab.umbenennen(self.w_s, "Media/a.dat", "A.DAT"))
        self.assertIn("A.DAT", os.listdir(self.w / "Media"))

    def test_vergebener_name_auch_in_anderer_schreibung(self) -> None:
        (self.w / "Media" / "z.dat").write_bytes(b"z")
        self.assertEqual("bearbeiten.name_vergeben", self.grund(ab.umbenennen, self.w_s, "Media/a.dat", "z.dat"))
        self.assertEqual("bearbeiten.name_vergeben", self.grund(ab.umbenennen, self.w_s, "Media/a.dat", "Z.DAT"))
        self.assertEqual(b"aaa", (self.w / "Media" / "a.dat").read_bytes())

    def test_geschuetztes_und_fehler(self) -> None:
        self.assertEqual("bearbeiten.geschuetzt", self.grund(ab.umbenennen, self.w_s, "eboot.bin", "x.bin"))
        self.assertEqual("bearbeiten.geschuetzt", self.grund(ab.umbenennen, self.w_s, "sce_sys", "sys"))
        self.assertEqual("bearbeiten.gleicher_name", self.grund(ab.umbenennen, self.w_s, "Media/a.dat", "a.dat"))
        self.assertEqual("bearbeiten.name_ungueltig", self.grund(ab.umbenennen, self.w_s, "Media/a.dat", "../x"))
        self.assertEqual("bearbeiten.name_ungueltig", self.grund(ab.umbenennen, self.w_s, "Media/a.dat", "Sub/x"))
        self.assertEqual("bearbeiten.nicht_gefunden", self.grund(ab.umbenennen, self.w_s, "Media/nix", "y"))
        self.assertEqual("bearbeiten.wurzel", self.grund(ab.umbenennen, self.w_s, "", "y"))
        ab.umbenennen(self.w_s, "eboot.bin", "eboot_alt.bin", erzwingen=True)
        self.assertTrue((self.w / "eboot_alt.bin").exists())


class ErsetzenTests(_Basis):
    def _quelle(self, inhalt: bytes = b"NEU") -> str:
        q = self.t / "neu.bin"
        q.write_bytes(inhalt)
        return str(q)

    def test_inhalt_wird_ersetzt_name_bleibt(self) -> None:
        p = ab.Protokoll()
        ab.ersetzen(self.w_s, "Media/a.dat", self._quelle(b"NEUER INHALT"), protokoll=p)
        self.assertEqual(b"NEUER INHALT", (self.w / "Media" / "a.dat").read_bytes())
        self.assertEqual(["a.dat"], [n for n in os.listdir(self.w / "Media") if n.endswith(".dat")])
        self.assertEqual(ab.Aenderung("ersetzen", "Media/a.dat", "neu.bin"), p.aenderungen[0])

    def test_keine_zwischendateien_bleiben(self) -> None:
        ab.ersetzen(self.w_s, "Media/a.dat", self._quelle())
        self.assertEqual([], [n for n in os.listdir(self.w / "Media") if n.startswith(".bearbeiten_")])

    def test_scheitert_das_kopieren_bleibt_die_alte_datei(self) -> None:
        with mock.patch.object(ab.shutil, "copyfile", side_effect=OSError("Platte voll")):
            self.assertEqual("bearbeiten.io", self.grund(ab.ersetzen, self.w_s, "Media/a.dat", self._quelle()))
        self.assertEqual(b"aaa", (self.w / "Media" / "a.dat").read_bytes())
        self.assertEqual([], [n for n in os.listdir(self.w / "Media") if n.startswith(".bearbeiten_")])

    def test_fehler(self) -> None:
        self.assertEqual("bearbeiten.keine_datei", self.grund(ab.ersetzen, self.w_s, "Media", self._quelle()))
        self.assertEqual("bearbeiten.keine_datei", self.grund(ab.ersetzen, self.w_s, "Media/nix.dat", self._quelle()))
        self.assertEqual("bearbeiten.quelle_fehlt", self.grund(ab.ersetzen, self.w_s, "Media/a.dat",
                                                              str(self.t / "gibt_es_nicht")))
        self.assertEqual("bearbeiten.quelle_fehlt", self.grund(ab.ersetzen, self.w_s, "Media/a.dat", str(self.t)))
        self.assertEqual("bearbeiten.wurzel", self.grund(ab.ersetzen, self.w_s, "", self._quelle()))
        self.assertEqual("bearbeiten.pfad_ausserhalb", self.grund(ab.ersetzen, self.w_s, "../x", self._quelle()))

    def test_geschuetzte_datei_darf_ersetzt_werden(self) -> None:
        """Eine neue eboot.bin einsetzen ist ein gewollter Fall (Patch); nur Loeschen/Umbenennen sind gesperrt."""
        ab.ersetzen(self.w_s, "eboot.bin", self._quelle(b"PATCHED"))
        self.assertEqual(b"PATCHED", (self.w / "eboot.bin").read_bytes())


class HinzufuegenTests(_Basis):
    def _quelle(self, name: str = "neu.bin", inhalt: bytes = b"NEU") -> str:
        q = self.t / name
        q.write_bytes(inhalt)
        return str(q)

    def test_datei_hinzufuegen(self) -> None:
        p = ab.Protokoll()
        neu = ab.hinzufuegen(self.w_s, "Media", self._quelle(), protokoll=p)
        self.assertEqual("Media/neu.bin", neu)
        self.assertEqual(b"NEU", (self.w / "Media" / "neu.bin").read_bytes())
        self.assertEqual(ab.Aenderung("hinzufuegen", "Media/neu.bin", "neu.bin"), p.aenderungen[0])

    def test_in_die_wurzel_und_unter_anderem_namen(self) -> None:
        self.assertEqual("x.cfg", ab.hinzufuegen(self.w_s, "", self._quelle(), "x.cfg"))
        self.assertTrue((self.w / "x.cfg").exists())

    def test_vorhandenes_wird_nicht_ueberschrieben(self) -> None:
        self.assertEqual("bearbeiten.name_vergeben", self.grund(ab.hinzufuegen, self.w_s, "Media", self._quelle("a.dat")))
        self.assertEqual("bearbeiten.name_vergeben", self.grund(ab.hinzufuegen, self.w_s, "Media", self._quelle("A.DAT")))
        self.assertEqual(b"aaa", (self.w / "Media" / "a.dat").read_bytes())

    def test_fehler(self) -> None:
        self.assertEqual("bearbeiten.kein_ordner", self.grund(ab.hinzufuegen, self.w_s, "Media/a.dat", self._quelle()))
        self.assertEqual("bearbeiten.kein_ordner", self.grund(ab.hinzufuegen, self.w_s, "Nix", self._quelle()))
        self.assertEqual("bearbeiten.pfad_ausserhalb", self.grund(ab.hinzufuegen, self.w_s, "..", self._quelle()))
        self.assertEqual("bearbeiten.quelle_fehlt", self.grund(ab.hinzufuegen, self.w_s, "Media", str(self.t / "nix")))
        self.assertEqual("bearbeiten.name_ungueltig", self.grund(ab.hinzufuegen, self.w_s, "Media", self._quelle(), "a/b"))


class OrdnerTests(_Basis):
    def test_ordner_anlegen(self) -> None:
        p = ab.Protokoll()
        self.assertEqual("Media/Neu", ab.ordner_anlegen(self.w_s, "Media", "Neu", protokoll=p))
        self.assertTrue((self.w / "Media" / "Neu").is_dir())
        self.assertEqual(ab.Aenderung("ordner", "Media/Neu"), p.aenderungen[0])

    def test_fehler(self) -> None:
        self.assertEqual("bearbeiten.name_vergeben", self.grund(ab.ordner_anlegen, self.w_s, "", "media"))
        self.assertEqual("bearbeiten.kein_ordner", self.grund(ab.ordner_anlegen, self.w_s, "Nix", "x"))
        self.assertEqual("bearbeiten.name_ungueltig", self.grund(ab.ordner_anlegen, self.w_s, "", "a:b"))


class SpielPruefenTests(_Basis):
    def test_vollstaendig(self) -> None:
        self.assertEqual([], ab.spiel_pruefen(self.w_s))

    def test_fehlendes_wird_genannt(self) -> None:
        ab.loeschen(self.w_s, "eboot.bin", erzwingen=True)
        self.assertEqual(["eboot.bin"], ab.spiel_pruefen(self.w_s))
        ab.loeschen(self.w_s, "sce_sys/param.json", erzwingen=True)
        self.assertEqual(["eboot.bin", "sce_sys/param.json"], ab.spiel_pruefen(self.w_s))


class ProtokollTests(unittest.TestCase):
    def test_zaehlung(self) -> None:
        p = ab.Protokoll()
        p.merken("loeschen", "a")
        p.merken("loeschen", "b")
        p.merken("ersetzen", "c", "d")
        self.assertEqual(3, p.anzahl())
        self.assertEqual({"loeschen": 2, "ersetzen": 1}, p.zaehlung())


if __name__ == "__main__":
    unittest.main()
