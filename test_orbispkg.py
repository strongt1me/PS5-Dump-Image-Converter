# -*- coding: utf-8 -*-
"""Tests fuer ``ps5_validator.utils.orbispkg`` - die Anbindung von OrbisPkgTool.

Drei Teile:

* **Auswertung** - reine Funktionen, mit den Ausgaben, die das Werkzeug am
  05.10.2026 an einem echten PS4-Paket geliefert hat (``Mario Kart 64
  [PS2toPS4]``, 159 MB).
* **Prozessfuehrung** - ein echter Kindprozess (der Python-Interpreter selbst)
  spielt das Werkzeug: Zeilenenden ``\\r`` und ``\\n``, getrennte Strome,
  Abbruch, Zeitgrenze, Unicode.
* **Ende-zu-Ende** - wenn das Werkzeug mitgeliefert ist: ein winziges Paket
  bauen, lesen, entpacken, pruefen, neu packen. Ohne Werkzeug uebersprungen.
"""
from __future__ import annotations

import os
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import orbispkg as op   # noqa: E402

#: Die Ausgabe von ``info`` an dem echten Paket.
INFO_AUSGABE = """\
Title        : Mario Kart 64 [ PS2toPS4 ]
Title ID     : MOMK27926
Content ID   : UP9000-MOMK27926_00-SLUS867650000001
Type         : Game
Category     : gd
Content type : 0x1A  flags 0x0A000000
App version  : 01.00
System ver   : 0x04008000
Passcode     : passcode verified
"""

LISTE_AUSGABE = """\
D 0 Image0
F 473 Image0/config-emu-ps4.txt
D 0 Image0/docs
F 539 Image0/docs/revision.h
F 6730460 Image0/eboot.bin
F 13369344 Image0/image/disc01.iso
F 1668 Sc0/param.sfo
F 2544958 Sc0/pic0.png
"""

VALIDATE_FEHLSCHLAG = """\
  [1/8] Validating package header + entry table
  [2/8] Validating outer PFS structure
  [3/8] Validating PFSC
Validation: FAIL
  Reason: The archive entry was compressed using an unsupported compression method.
"""

VALIDATE_ERFOLG = """\
  [1/8] Validating package header + entry table
  [8/8] Validating complete
Validation: PASS
"""


class InfoTests(unittest.TestCase):

    def test_alle_felder_werden_gelesen(self) -> None:
        erg = op.info_auswerten(INFO_AUSGABE)
        self.assertEqual("Mario Kart 64 [ PS2toPS4 ]", erg.titel)
        self.assertEqual("MOMK27926", erg.title_id)
        self.assertEqual("UP9000-MOMK27926_00-SLUS867650000001", erg.content_id)
        self.assertEqual("Game", erg.typ)
        self.assertEqual("gd", erg.kategorie)
        self.assertEqual(0x1A, erg.content_type)
        self.assertEqual(0x0A000000, erg.content_flags)
        self.assertEqual("01.00", erg.app_version)
        self.assertEqual("0x04008000", erg.system_version)
        self.assertEqual("passcode verified", erg.passcode)

    def test_ein_titel_mit_doppelpunkt_bleibt_ganz(self) -> None:
        erg = op.info_auswerten("Title        : Spiel: Der Anfang\nTitle ID     : CUSA00001\n")
        self.assertEqual("Spiel: Der Anfang", erg.titel)
        self.assertEqual("CUSA00001", erg.title_id)

    def test_leere_ausgabe_wirft_nicht(self) -> None:
        erg = op.info_auswerten("")
        self.assertEqual("", erg.titel)
        self.assertEqual(0, erg.content_type)

    def test_unbekannte_zeilen_werden_uebergangen(self) -> None:
        erg = op.info_auswerten("[warn] irgendwas\nTitle ID     : CUSA00002\nunbekannt : x\n")
        self.assertEqual("CUSA00002", erg.title_id)


class ListeTests(unittest.TestCase):

    def test_ordner_und_dateien(self) -> None:
        eintraege = op.liste_auswerten(LISTE_AUSGABE)
        self.assertEqual(8, len(eintraege))
        self.assertTrue(eintraege[0].ist_ordner)
        self.assertEqual("Image0", eintraege[0].pfad)
        eboot = [e for e in eintraege if e.name == "eboot.bin"][0]
        self.assertFalse(eboot.ist_ordner)
        self.assertEqual(6730460, eboot.groesse)
        self.assertEqual("Image0/eboot.bin", eboot.pfad)

    def test_pfade_mit_leerzeichen(self) -> None:
        eintraege = op.liste_auswerten("F 12 Image0/Mein Ordner/eine Datei.txt\n")
        self.assertEqual(1, len(eintraege))
        self.assertEqual("Image0/Mein Ordner/eine Datei.txt", eintraege[0].pfad)
        self.assertEqual("eine Datei.txt", eintraege[0].name)

    def test_fremde_zeilen_fallen_weg(self) -> None:
        eintraege = op.liste_auswerten("[warn] x\nF abc Image0/x\nF 5 Image0/y\n\n")
        self.assertEqual(["Image0/y"], [e.pfad for e in eintraege])


class FortschrittTests(unittest.TestCase):

    def test_entpacken(self) -> None:
        zeile = "  [ 83%] 31/37  Image0/PS20220WD20050620.crack      "
        self.assertEqual((83, 31, 37, "Image0/PS20220WD20050620.crack"),
                         op.entpack_fortschritt(zeile))

    def test_entpacken_fertig_zeile(self) -> None:
        self.assertEqual((100, 37, 37, "done."),
                         op.entpack_fortschritt("  [100%] 37/37  done."))

    def test_entpacken_fremde_zeile(self) -> None:
        self.assertIsNone(op.entpack_fortschritt("Extracted 37/37 files in 0.5s."))

    def test_bauen(self) -> None:
        self.assertEqual((12, "Compressing", 34, 160),
                         op.bau_fortschritt("  [ 12%] Compressing (34/160 MB)   "))
        self.assertIsNone(op.bau_fortschritt("Built x.pkg (58.8 MB) in 0.9 s"))

    def test_schritt(self) -> None:
        self.assertEqual((3, 5, "Generating GP4 project..."),
                         op.schritt_auswerten("[3/5] Generating GP4 project..."))
        self.assertIsNone(op.schritt_auswerten("  Move: Sc0/x -> y"))

    def test_stufe(self) -> None:
        self.assertEqual(("Extracting base", "Image0/eboot.bin"),
                         op.stufe_auswerten("[Extracting base] Image0/eboot.bin"))
        self.assertEqual(("Building", "42%"), op.stufe_auswerten("[Building] 42%"))
        self.assertIsNone(op.stufe_auswerten("Merge complete in 1.0s"))


class ValidateTests(unittest.TestCase):

    def test_fehlschlag_mit_grund(self) -> None:
        erg = op.validate_auswerten(VALIDATE_FEHLSCHLAG)
        self.assertFalse(erg.bestanden)
        self.assertIn("unsupported compression method", erg.grund)
        self.assertEqual(3, len(erg.stufen))

    def test_erfolg(self) -> None:
        erg = op.validate_auswerten(VALIDATE_ERFOLG)
        self.assertTrue(erg.bestanden)
        self.assertEqual("", erg.grund)

    def test_ohne_urteil_gilt_als_nicht_bestanden(self) -> None:
        self.assertFalse(op.validate_auswerten("irgendwas").bestanden)


def _kindprogramm(wo: Path, quelltext: str) -> list[str]:
    """Ein Kindprogramm, das das Werkzeug spielt: (programm, [skript])."""
    skript = wo / "tool.py"
    skript.write_text(textwrap.dedent(quelltext), encoding="utf-8")
    return [str(skript)]


class LaufenTests(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.wo = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _lauf(self, quelltext: str, **kwargs):
        skript = _kindprogramm(self.wo, quelltext)
        return op._laufen(skript, programm=sys.executable, **kwargs)

    def test_zeilenenden_cr_und_lf_werden_geteilt(self) -> None:
        erg = self._lauf("""
            import sys
            sys.stdout.write("eins\\r  zwei\\r\\n drei\\nvier")
            sys.stdout.flush()
        """)
        self.assertEqual(0, erg.rueckgabe)
        self.assertEqual(["eins", "  zwei", " drei", "vier"], erg.ausgabe)

    def test_ausgabe_und_fehler_bleiben_getrennt(self) -> None:
        erg = self._lauf("""
            import sys
            print("A")
            print("[error] kaputt", file=sys.stderr)
            sys.exit(3)
        """)
        self.assertEqual(3, erg.rueckgabe)
        self.assertEqual(["A"], erg.ausgabe)
        self.assertEqual(["[error] kaputt"], erg.fehler)
        self.assertEqual("kaputt", erg.letzte_fehlerzeile)

    def test_unicode_kommt_heil_an(self) -> None:
        erg = self._lauf("""
            import sys
            sys.stdout.buffer.write("Pok\\u00e9mon \\u2013 \\u00c4\\u00d6\\u00dc\\n".encode("utf-8"))
        """)
        self.assertEqual(["Pok\u00e9mon \u2013 \u00c4\u00d6\u00dc"], erg.ausgabe)

    def test_der_rueckruf_bekommt_jede_zeile_im_aufrufer_faden(self) -> None:
        gesehen: list[tuple[str, str]] = []
        import threading
        faeden: set[int] = set()

        def _hoeren(strom: str, zeile: str) -> None:
            faeden.add(threading.get_ident())
            gesehen.append((strom, zeile))

        self._lauf("""
            import sys
            print("x1")
            print("y1", file=sys.stderr)
        """, bei_zeile=_hoeren)
        self.assertIn(("aus", "x1"), gesehen)
        self.assertIn(("fehler", "y1"), gesehen)
        self.assertEqual({threading.get_ident()}, faeden)

    def test_ein_werfender_rueckruf_bricht_nichts_ab(self) -> None:
        def _wirft(strom: str, zeile: str) -> None:
            raise RuntimeError("Absicht")

        erg = self._lauf("print('ok')", bei_zeile=_wirft)
        self.assertEqual(0, erg.rueckgabe)
        self.assertEqual(["ok"], erg.ausgabe)

    def test_abbruch_beendet_den_prozess(self) -> None:
        vorher = time.monotonic()
        erg = self._lauf("""
            import time
            print("start", flush=True)
            time.sleep(60)
        """, abbruch=lambda: True)
        self.assertTrue(erg.abgebrochen)
        self.assertLess(time.monotonic() - vorher, 20, "Der Abbruch hat nicht gegriffen.")

    def test_die_zeitgrenze_beendet_den_prozess(self) -> None:
        vorher = time.monotonic()
        erg = self._lauf("""
            import time
            time.sleep(60)
        """, zeitgrenze=0.5)
        self.assertTrue(erg.zeit_ueberschritten)
        self.assertFalse(erg.abgebrochen)
        self.assertLess(time.monotonic() - vorher, 20)

    def test_der_abbruch_wird_nicht_bei_jeder_zeile_gefragt(self) -> None:
        """Ein Entpacken meldet tausende Zeilen - die Abfrage soll nicht mitzaehlen."""
        fragen = []

        def _frage() -> bool:
            fragen.append(1)
            return False

        self._lauf("""
            import sys
            for i in range(3000):
                sys.stdout.write("zeile %d\\n" % i)
        """, abbruch=_frage)
        self.assertLess(len(fragen), 100)

    def test_ein_fehlendes_werkzeug_wirft(self) -> None:
        with mock.patch.object(op, "werkzeug_finden", return_value=""):
            with self.assertRaises(op.OrbisFehler) as ctx:
                op._laufen(["info", "x.pkg"])
        self.assertIn("OrbisPkgTool", str(ctx.exception))

    def test_die_meldung_laesst_sich_uebersetzen(self) -> None:
        with mock.patch.object(op, "werkzeug_finden", return_value=""):
            with self.assertRaises(op.OrbisFehler) as ctx:
                op._laufen(["info"], texte={"nicht_gefunden": "FEHLT {ordner} {plattform}"})
        self.assertTrue(str(ctx.exception).startswith("FEHLT OrbisPkgTool-1.0.0"))

    def test_ein_nicht_startbares_programm_wirft_orbisfehler(self) -> None:
        with self.assertRaises(op.OrbisFehler):
            op._laufen(["x"], programm=str(self.wo / "gibt_es_nicht.exe"))


class BefehleTests(unittest.TestCase):
    """Die Befehle, mit einem untergeschobenen ``_laufen``."""

    @staticmethod
    def _antwort(ausgabe=(), fehler=(), rc=0, **kw) -> op.LaufErgebnis:
        return op.LaufErgebnis(rc, list(ausgabe), list(fehler), **kw)

    def test_info_ruft_info_mit_dem_paket(self) -> None:
        with mock.patch.object(op, "_laufen",
                               return_value=self._antwort(INFO_AUSGABE.splitlines())) as lauf:
            erg = op.info("C:/x/spiel.pkg")
        self.assertEqual(["info", "C:/x/spiel.pkg"], lauf.call_args.args[0])
        self.assertEqual("MOMK27926", erg.title_id)

    def test_info_reicht_den_passcode_weiter(self) -> None:
        with mock.patch.object(op, "_laufen", return_value=self._antwort(INFO_AUSGABE.splitlines())) as lauf:
            op.info("a.pkg", passcode="1" * 32)
        self.assertEqual(["info", "a.pkg", "--passcode", "1" * 32], lauf.call_args.args[0])

    def test_info_fehler_wird_zu_orbisfehler(self) -> None:
        with mock.patch.object(op, "_laufen",
                               return_value=self._antwort(fehler=["[error] Not a PKG"], rc=1)):
            with self.assertRaises(op.OrbisFehler) as ctx:
                op.info("a.pkg")
        self.assertEqual("Not a PKG", str(ctx.exception))

    def test_liste(self) -> None:
        with mock.patch.object(op, "_laufen", return_value=self._antwort(LISTE_AUSGABE.splitlines())):
            self.assertEqual(8, len(op.liste("a.pkg")))

    def test_entpacken_meldet_fortschritt_und_zaehlt(self) -> None:
        def _falsch(argumente, **kw):
            self.assertEqual(["extract", "a.pkg", ziel, "--verbose"], argumente)
            for zeile in ["  [ 50%] 1/2  Image0/a.bin", "  [100%] 2/2  done."]:
                kw["bei_zeile"]("aus", zeile)
            return self._antwort(["  [100%] 2/2  done.", "Extracted 2/2 files in 0.1s."])

        meldungen: list[tuple[int, int, str]] = []
        with tempfile.TemporaryDirectory() as wo:
            ziel = os.path.join(wo, "aus")
            with mock.patch.object(op, "_laufen", side_effect=_falsch):
                erg = op.entpacken("a.pkg", ziel, fortschritt=lambda a, g, d: meldungen.append((a, g, d)))
            self.assertTrue(os.path.isdir(ziel))
        self.assertTrue(erg.ok)
        self.assertEqual((2, 2), (erg.dateien_ok, erg.dateien_gesamt))
        self.assertEqual([(1, 2, "Image0/a.bin"), (2, 2, "done.")], meldungen)

    def test_entpacken_nennt_fehlgeschlagene_dateien(self) -> None:
        def _falsch(argumente, **kw):
            kw["bei_zeile"]("fehler", "[warn] 2 file(s) failed:")
            kw["bei_zeile"]("fehler", "  Image0/a.bin: Zugriff verweigert")
            kw["bei_zeile"]("fehler", "  Image0/b.bin: gesperrt")
            return self._antwort(["Extracted 3/5 files in 1.0s."], rc=1)

        with tempfile.TemporaryDirectory() as wo:
            with mock.patch.object(op, "_laufen", side_effect=_falsch):
                erg = op.entpacken("a.pkg", os.path.join(wo, "x"))
        self.assertFalse(erg.ok)
        self.assertEqual(["Image0/a.bin: Zugriff verweigert", "Image0/b.bin: gesperrt"], erg.fehler)
        self.assertEqual((3, 5), (erg.dateien_ok, erg.dateien_gesamt))

    def test_entpacken_abbruch_ist_kein_ok(self) -> None:
        with tempfile.TemporaryDirectory() as wo:
            with mock.patch.object(op, "_laufen", return_value=self._antwort(rc=-1, abgebrochen=True)):
                erg = op.entpacken("a.pkg", os.path.join(wo, "x"))
        self.assertFalse(erg.ok)
        self.assertTrue(erg.abgebrochen)

    def test_einzelne_datei_nutzt_die_paket_doppelpunkt_schreibweise(self) -> None:
        with tempfile.TemporaryDirectory() as wo:
            with mock.patch.object(op, "_laufen", return_value=self._antwort()) as lauf:
                op.entpacken_eintrag("C:/p/a.pkg", "Image0/eboot.bin", os.path.join(wo, "o"))
        self.assertEqual(["extract", "C:/p/a.pkg:Image0/eboot.bin"], lauf.call_args.args[0][:2])

    def test_pruefen(self) -> None:
        ok = self._antwort(["Integrity OK : all 20 entries verified in 57 ms."])
        schlecht = self._antwort(["Integrity FAILED : 2 mismatch(es):", "  x"], rc=0)
        with mock.patch.object(op, "_laufen", return_value=ok):
            self.assertTrue(op.pruefen("a.pkg")[0])
        with mock.patch.object(op, "_laufen", return_value=schlecht):
            self.assertFalse(op.pruefen("a.pkg")[0])

    def test_tiefenpruefung(self) -> None:
        with mock.patch.object(op, "_laufen",
                               return_value=self._antwort(VALIDATE_FEHLSCHLAG.splitlines(), rc=1)) as lauf:
            erg = op.tiefenpruefung("a.pkg", fake_tolerant=True)
        self.assertFalse(erg.bestanden)
        self.assertIn("--fake-tolerant", lauf.call_args.args[0])

    def test_zusammenfuehren_baut_die_zeile(self) -> None:
        with tempfile.TemporaryDirectory() as wo:
            ausgabe = os.path.join(wo, "m.pkg")
            Path(ausgabe).write_bytes(b"x")
            stufen: list[tuple[str, "int | None"]] = []

            def _falsch(argumente, **kw):
                kw["bei_zeile"]("aus", "[Extracting base] Image0/eboot.bin")
                kw["bei_zeile"]("aus", "  [ 40%] Compressing (10/25 MB)")
                return self._antwort(["Merge complete in 1.0s: " + ausgabe,
                                      "Work directory kept: C:/arbeit"])

            with mock.patch.object(op, "_laufen", side_effect=_falsch) as lauf:
                erg = op.zusammenfuehren("b.pkg", "u.pkg", ausgabe, pruefen_danach=True,
                                         arbeiter=0, arbeitsordner="C:/arbeit", behalten=True,
                                         fortschritt=lambda t, p: stufen.append((t, p)))
        argumente = lauf.call_args.args[0]
        self.assertEqual(["merge", "b.pkg", "u.pkg", "--out", ausgabe], argumente[:5])
        for erwartet in ("--validate", "--keep-work"):
            self.assertIn(erwartet, argumente)
        self.assertEqual("0", argumente[argumente.index("--workers") + 1])
        self.assertEqual("C:/arbeit", argumente[argumente.index("--work-dir") + 1])
        self.assertTrue(erg.ok)
        self.assertEqual("C:/arbeit", erg.arbeitsordner_behalten)
        self.assertEqual([("Extracting base: Image0/eboot.bin", None),
                          ("Compressing (10/25 MB)", 40)], stufen)

    def test_ein_bau_ohne_ausgabedatei_gilt_als_misserfolg(self) -> None:
        with tempfile.TemporaryDirectory() as wo:
            with mock.patch.object(op, "_laufen",
                                   return_value=self._antwort(fehler=["[error] Merge failed: kein Update"], rc=1)):
                erg = op.zusammenfuehren("b.pkg", "u.pkg", os.path.join(wo, "m.pkg"))
        self.assertFalse(erg.ok)
        self.assertEqual("Merge failed: kein Update", erg.meldung)

    def test_neu_packen_und_bauen_stellen_die_zeile_zusammen(self) -> None:
        with tempfile.TemporaryDirectory() as wo:
            ziel = os.path.join(wo, "n.pkg")
            with mock.patch.object(op, "_laufen", return_value=self._antwort()) as lauf:
                op.neu_packen("a.pkg", ziel, pfsc_modus="store", arbeiter=4, pruefen_danach=True)
                repack = lauf.call_args.args[0]
                op.bauen("p.gp4", "Image0", ziel)
                bau = lauf.call_args.args[0]
        self.assertEqual(["repack", "a.pkg", "--out", ziel], repack[:4])
        self.assertIn("store", repack)
        self.assertIn("--validate", repack)
        self.assertEqual(["build", "p.gp4", "Image0", "--out", ziel], bau[:5])
        self.assertNotIn("--validate", bau)

    def test_projekt_erzeugen(self) -> None:
        with mock.patch.object(op, "_laufen", return_value=self._antwort()) as lauf:
            op.projekt_erzeugen("Image0", "p.gp4", patch=True, streng=True)
        self.assertEqual(["gp4gen", "Image0", "--out", "p.gp4", "--patch", "--strict-gengp4"],
                         lauf.call_args.args[0])


class FindenTests(unittest.TestCase):

    def test_ohne_ordner_leer(self) -> None:
        with tempfile.TemporaryDirectory() as wo:
            with mock.patch.object(op, "_suchwurzeln", return_value=[wo]):
                self.assertEqual("", op.werkzeug_finden())
                self.assertFalse(op.verfuegbar())

    def test_mit_ordner_gefunden(self) -> None:
        with tempfile.TemporaryDirectory() as wo:
            ziel = Path(wo) / op.WERKZEUGORDNER / op.plattformordner()
            ziel.mkdir(parents=True)
            (ziel / op.PROGRAMMNAME).write_bytes(b"x")
            with mock.patch.object(op, "_suchwurzeln", return_value=[wo]):
                self.assertEqual(str(ziel / op.PROGRAMMNAME), op.werkzeug_finden())

    def test_der_plattformordner_passt_zum_system(self) -> None:
        with mock.patch.object(op.sys, "platform", "win32"):
            self.assertEqual("win-x64", op.plattformordner())
        with mock.patch.object(op.sys, "platform", "darwin"), \
                mock.patch.object(op.platform, "machine", return_value="arm64"):
            self.assertEqual("osx-arm64", op.plattformordner())
        with mock.patch.object(op.sys, "platform", "darwin"), \
                mock.patch.object(op.platform, "machine", return_value="x86_64"):
            self.assertEqual("osx-x64", op.plattformordner())

    def test_die_fassung_steht_im_ordnernamen(self) -> None:
        self.assertEqual("1.0.0", op.version())


@unittest.skipUnless(op.verfuegbar(), "OrbisPkgTool ist fuer diese Plattform nicht mitgeliefert.")
class EndeZuEndeTests(unittest.TestCase):
    """Mit dem echten Werkzeug: ein winziges Paket bauen und wieder lesen."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.wo = Path(cls._tmp.name)
        quelle = cls.wo / "Image0"
        (quelle / "sce_sys").mkdir(parents=True)
        lauf = op._laufen(["sfo", "create", str(quelle / "sce_sys" / "param.sfo"),
                           "--title", "Mini Test", "--title-id", "TEST00001",
                           "--content-id", "UP0000-TEST00001_00-0000000000000000"])
        assert lauf.rueckgabe == 0, lauf.fehlertext
        (quelle / "eboot.bin").write_bytes(bytes(i % 251 for i in range(4096)))
        (quelle / "readme.txt").write_text("Hallo PS4 \u00c4\u00d6\u00dc", encoding="utf-8")
        cls.quelle = quelle
        cls.gp4 = cls.wo / "projekt.gp4"
        assert op.projekt_erzeugen(str(quelle), str(cls.gp4)).rueckgabe == 0
        cls.pkg = cls.wo / "mini.pkg"
        erg = op.bauen(str(cls.gp4), str(quelle), str(cls.pkg), pruefen_danach=True)
        assert erg.ok, erg.meldung

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_info(self) -> None:
        erg = op.info(str(self.pkg))
        self.assertEqual("TEST00001", erg.title_id)
        self.assertEqual("Mini Test", erg.titel)
        self.assertEqual("gd", erg.kategorie)

    def test_liste_nennt_die_dateien(self) -> None:
        pfade = {e.pfad for e in op.liste(str(self.pkg)) if not e.ist_ordner}
        self.assertIn("Image0/eboot.bin", pfade)
        self.assertIn("Image0/readme.txt", pfade)
        self.assertIn("Sc0/param.sfo", pfade)

    def test_entpacken_gibt_dieselben_bytes_zurueck(self) -> None:
        ziel = self.wo / "aus"
        meldungen: list[tuple[int, int, str]] = []
        erg = op.entpacken(str(self.pkg), str(ziel),
                           fortschritt=lambda a, g, d: meldungen.append((a, g, d)))
        self.assertTrue(erg.ok, erg.meldung)
        self.assertEqual((erg.dateien_ok, erg.dateien_gesamt), (erg.dateien_gesamt, erg.dateien_ok))
        self.assertEqual((self.quelle / "eboot.bin").read_bytes(),
                         (ziel / "Image0" / "eboot.bin").read_bytes())
        self.assertEqual("Hallo PS4 \u00c4\u00d6\u00dc",
                         (ziel / "Image0" / "readme.txt").read_text(encoding="utf-8"))
        self.assertTrue(meldungen, "Kein Fortschritt gemeldet.")
        self.assertEqual(meldungen[-1][0], meldungen[-1][1])

    def test_eine_einzelne_datei(self) -> None:
        ziel = self.wo / "einzeln"
        lauf = op.entpacken_eintrag(str(self.pkg), "Image0/eboot.bin", str(ziel))
        self.assertEqual(0, lauf.rueckgabe, lauf.fehlertext)
        gefunden = [p for p in ziel.rglob("eboot.bin")]
        self.assertEqual(1, len(gefunden))
        self.assertEqual((self.quelle / "eboot.bin").read_bytes(), gefunden[0].read_bytes())

    def test_pruefen_und_tiefenpruefung(self) -> None:
        self.assertTrue(op.pruefen(str(self.pkg))[0])
        self.assertTrue(op.tiefenpruefung(str(self.pkg)).bestanden)

    def test_neu_packen_liefert_ein_gleiches_paket(self) -> None:
        ziel = self.wo / "neu.pkg"
        erg = op.neu_packen(str(self.pkg), str(ziel), arbeitsordner=str(self.wo / "arbeit"))
        self.assertTrue(erg.ok, erg.meldung)
        pfade = {e.pfad: e.groesse for e in op.liste(str(ziel)) if not e.ist_ordner}
        self.assertEqual(4096, pfade["Image0/eboot.bin"])
        self.assertEqual("TEST00001", op.info(str(ziel)).title_id)

    def test_ein_unlesbares_paket_gibt_einen_klaren_fehler(self) -> None:
        kaputt = self.wo / "kaputt.pkg"
        kaputt.write_bytes(b"das ist kein Paket" * 100)
        with self.assertRaises(op.OrbisFehler):
            op.info(str(kaputt))


if __name__ == "__main__":
    unittest.main()
