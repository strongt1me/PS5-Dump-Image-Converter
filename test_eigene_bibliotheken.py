# -*- coding: utf-8 -*-
"""Der Ordner ``libs``: eigene Bibliotheken statt der mitgelieferten.

Wer eine selbst gebaute ``LibProsperoPkg.dll`` in ``libs`` legt, soll damit
bauen koennen, ohne im Projekt etwas anzufassen. Die entscheidende Zusage
ist deshalb nicht "die eigene Datei wird benutzt", sondern:

**Der mitgelieferte Werkzeugordner bleibt dabei Byte fuer Byte unberuehrt.**

Denn er ist git-verfolgt. Wuerde das Programm dort hineinschreiben, waere
jeder Bau mit eigener Bibliothek eine Aenderung am Projekt - und die
Werkzeugpruefung (``werkzeugstaende``) wuerde sie melden. Genau das misst
:meth:`EinsatzordnerTests.test_mitgeliefertes_werkzeug_bleibt_unberuehrt`.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ps5_validator.utils import eigene_bibliotheken as eb   # noqa: E402

PROJEKT = Path(__file__).resolve().parent


def _werkzeugordner_bauen(wo: Path) -> Path:
    """Ein Werkzeugordner, wie ProsperoPkg-2.5/win-x64 einer ist."""
    ordner = wo / "werkzeug"
    ordner.mkdir(parents=True)
    (ordner / "prosperopkg.exe").write_bytes(b"MZ-werkzeug")
    (ordner / "LibProsperoPkg.dll").write_bytes(b"mitgeliefert" * 10)
    (ordner / "prosperopkg.runtimeconfig.json").write_text("{}", encoding="utf-8")
    return ordner


class NamenTests(unittest.TestCase):

    def test_managed_assembly_heisst_ueberall_dll(self):
        """.NET-Assemblys tragen auch unter Linux und macOS ``.dll``."""
        self.assertIn("LibProsperoPkg.dll", eb.bekannte_namen())

    def test_native_bibliothek_je_plattform(self):
        namen = eb.bekannte_namen()
        # Die Windows-Schreibweise wird ueberall mitgenommen.
        self.assertIn("libScePubTools.dll", namen)
        if sys.platform == "linux":
            self.assertIn("libScePubTools.so", namen)
        if sys.platform == "darwin":
            self.assertIn("libScePubTools.dylib", namen)

    def test_ordnername(self):
        self.assertEqual("libs", eb.ORDNER)

    def test_ordner_liegt_im_projekt(self):
        """Der Ordner gehoert ins Projekt - samt Anleitung."""
        self.assertTrue((PROJEKT / "libs").is_dir())
        self.assertTrue((PROJEKT / "libs" / "README.md").is_file())


class GefundeneTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.libs = Path(self._tmp.name) / "libs"
        self.libs.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_leerer_ordner_findet_nichts(self):
        self.assertEqual({}, eb.gefundene(str(self.libs)))
        self.assertEqual([], eb.stand(str(self.libs)))

    def test_eigene_datei_wird_gefunden(self):
        (self.libs / "LibProsperoPkg.dll").write_bytes(b"eigen")
        gefunden = eb.gefundene(str(self.libs))
        self.assertEqual(["LibProsperoPkg.dll"], list(gefunden))

    def test_leere_datei_zaehlt_nicht(self):
        """0 Byte ist ein Versehen, kein Ersatz."""
        (self.libs / "LibProsperoPkg.dll").write_bytes(b"")
        self.assertEqual({}, eb.gefundene(str(self.libs)))

    def test_fremde_namen_werden_nicht_beachtet(self):
        (self.libs / "irgendwas.dll").write_bytes(b"xx")
        (self.libs / "README.md").write_text("Anleitung", encoding="utf-8")
        self.assertEqual({}, eb.gefundene(str(self.libs)))

    def test_begleitdateien_kommen_mit_der_assembly(self):
        """.pdb und .xml gehoeren zur DLL - allein bewirken sie nichts."""
        (self.libs / "LibProsperoPkg.dll").write_bytes(b"eigen")
        (self.libs / "LibProsperoPkg.pdb").write_bytes(b"symbole")
        (self.libs / "LibProsperoPkg.xml").write_bytes(b"<doc/>")
        gefunden = eb.gefundene(str(self.libs))
        self.assertEqual({"LibProsperoPkg.dll", "LibProsperoPkg.pdb",
                          "LibProsperoPkg.xml"}, set(gefunden))

    def test_begleitdatei_allein_bewirkt_nichts(self):
        (self.libs / "LibProsperoPkg.pdb").write_bytes(b"symbole")
        self.assertEqual({}, eb.gefundene(str(self.libs)))

    def test_sdk_unterordner_wird_gemeldet_aber_nicht_benutzt(self):
        """Ein SDK-Baukasten in libs/sdk ist ein anderer Bauweg, kein Tausch."""
        (self.libs / "sdk" / "toolchain").mkdir(parents=True)
        (self.libs / "sdk" / "toolchain" / "prospero-pub-cmd.exe").write_bytes(b"MZ")
        self.assertEqual({}, eb.gefundene(str(self.libs)),
                         "Unterordner duerfen nicht als Bibliothek zaehlen")
        self.assertEqual(["sdk"], eb.unbenutzte_ordner(str(self.libs)))

    def test_ohne_unterordner_keine_meldung(self):
        self.assertEqual([], eb.unbenutzte_ordner(str(self.libs)))

    def test_stand_nennt_groesse_und_pruefsumme(self):
        (self.libs / "LibProsperoPkg.dll").write_bytes(b"eigen")
        eintrag = eb.stand(str(self.libs))[0]
        self.assertEqual("LibProsperoPkg.dll", eintrag["name"])
        self.assertEqual(5, eintrag["bytes"])
        self.assertEqual(64, len(eintrag["sha256"]))


class EinsatzordnerTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        wo = Path(self._tmp.name)
        self.werkzeug = _werkzeugordner_bauen(wo)
        self.libs = wo / "libs"
        self.libs.mkdir()
        self.arbeit = wo / "einstellungen"
        self.arbeit.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_ohne_eigene_bleibt_alles_wie_es_war(self):
        """Der Normalfall darf nicht einmal eine Kopie kosten."""
        ordner = eb.einsatzordner(str(self.werkzeug), str(self.arbeit),
                                  str(self.libs))
        self.assertEqual(str(self.werkzeug), ordner)
        self.assertEqual([], list(self.arbeit.iterdir()))

    def test_eigene_datei_wird_eingesetzt(self):
        (self.libs / "LibProsperoPkg.dll").write_bytes(b"meine-eigene")
        ordner = eb.einsatzordner(str(self.werkzeug), str(self.arbeit),
                                  str(self.libs))
        self.assertNotEqual(str(self.werkzeug), ordner)
        kopie = Path(ordner)
        self.assertEqual(b"meine-eigene",
                         (kopie / "LibProsperoPkg.dll").read_bytes())
        # Der Rest des Werkzeugs muss mitgekommen sein, sonst startet nichts.
        self.assertEqual(b"MZ-werkzeug", (kopie / "prosperopkg.exe").read_bytes())
        self.assertTrue((kopie / "prosperopkg.runtimeconfig.json").is_file())

    def test_mitgeliefertes_werkzeug_bleibt_unberuehrt(self):
        """Die Kernzusage: im Projektordner wird nichts ueberschrieben."""
        vorher = {p.name: p.read_bytes()
                  for p in self.werkzeug.iterdir() if p.is_file()}
        (self.libs / "LibProsperoPkg.dll").write_bytes(b"meine-eigene")
        eb.einsatzordner(str(self.werkzeug), str(self.arbeit), str(self.libs))
        nachher = {p.name: p.read_bytes()
                   for p in self.werkzeug.iterdir() if p.is_file()}
        self.assertEqual(vorher, nachher)
        self.assertEqual(b"mitgeliefert" * 10,
                         (self.werkzeug / "LibProsperoPkg.dll").read_bytes())

    def test_zweiter_lauf_kopiert_nicht_noch_einmal(self):
        (self.libs / "LibProsperoPkg.dll").write_bytes(b"meine-eigene")
        ordner = eb.einsatzordner(str(self.werkzeug), str(self.arbeit),
                                  str(self.libs))
        marke = Path(ordner) / "prosperopkg.exe"
        zeit = marke.stat().st_mtime_ns
        zweiter = eb.einsatzordner(str(self.werkzeug), str(self.arbeit),
                                   str(self.libs))
        self.assertEqual(ordner, zweiter)
        self.assertEqual(zeit, marke.stat().st_mtime_ns,
                         "unveraendert heisst: nicht noch einmal spiegeln")

    def test_neue_fassung_wird_uebernommen(self):
        """Erkannt wird das an der Pruefsumme, nicht am Datum."""
        (self.libs / "LibProsperoPkg.dll").write_bytes(b"erste")
        ordner = eb.einsatzordner(str(self.werkzeug), str(self.arbeit),
                                  str(self.libs))
        (self.libs / "LibProsperoPkg.dll").write_bytes(b"zweite-fassung")
        eb.einsatzordner(str(self.werkzeug), str(self.arbeit), str(self.libs))
        self.assertEqual(b"zweite-fassung",
                         (Path(ordner) / "LibProsperoPkg.dll").read_bytes())

    def test_herausgenommene_datei_faellt_auf_das_mitgelieferte_zurueck(self):
        """Datei wieder aus libs heraus - und alles ist wie vorher."""
        datei = self.libs / "LibProsperoPkg.dll"
        datei.write_bytes(b"meine-eigene")
        eb.einsatzordner(str(self.werkzeug), str(self.arbeit), str(self.libs))
        datei.unlink()
        ordner = eb.einsatzordner(str(self.werkzeug), str(self.arbeit),
                                  str(self.libs))
        self.assertEqual(str(self.werkzeug), ordner)

    def test_beide_bibliotheken_zusammen(self):
        (self.libs / "LibProsperoPkg.dll").write_bytes(b"verwaltet")
        native = [n for n in eb.bekannte_namen() if n.startswith("libScePub")][0]
        (self.libs / native).write_bytes(b"nativ")
        ordner = Path(eb.einsatzordner(str(self.werkzeug), str(self.arbeit),
                                       str(self.libs)))
        self.assertEqual(b"verwaltet", (ordner / "LibProsperoPkg.dll").read_bytes())
        self.assertEqual(b"nativ", (ordner / native).read_bytes())


class SelbsttestTests(unittest.TestCase):
    """Passt die eigene Bibliothek ueberhaupt zur Huelle?

    Am 23.09.2026 lag eine echte ``LibProsperoPkg.dll`` in ``libs`` - aber
    Fassung **1.2.0.0** fuer .NET 9, waehrend die mitgelieferte Huelle gegen
    **2.6.0.0** gebunden ist. Der Tausch wirkte, und danach scheiterte jeder
    Aufruf an ``Could not load file or assembly``. Zwei echte Tests wurden
    dadurch rot. Seitdem prueft das Programm die Kopie, bevor es sie benutzt.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ordner = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _probe_schreiben(self, ausgabe: str) -> str:
        """Ein winziges Programm, das eine feste Zeile ausgibt."""
        if sys.platform == "win32":
            name = "probe.cmd"
            (self.ordner / name).write_text(
                "@echo off\r\necho %s\r\n" % ausgabe, encoding="utf-8")
        else:
            name = "probe.sh"
            pfad = self.ordner / name
            pfad.write_text("#!/bin/sh\necho '%s'\n" % ausgabe,
                            encoding="utf-8")
            pfad.chmod(0o755)
        return name

    def test_ladefehler_wird_erkannt(self):
        name = self._probe_schreiben(
            "[FEHLER] FileNotFoundException: Could not load file or assembly "
            "'LibProsperoPkg, Version=2.6.0.0'")
        taugt, grund = eb.kopie_taugt(str(self.ordner), programm=name)
        self.assertFalse(taugt)
        self.assertIn("LibProsperoPkg", grund)

    def test_saubere_ausgabe_gilt_als_tauglich(self):
        name = self._probe_schreiben("RESULT: READY")
        taugt, grund = eb.kopie_taugt(str(self.ordner), programm=name)
        self.assertTrue(taugt, grund)
        self.assertEqual("", grund)

    def test_fehlendes_programm(self):
        taugt, grund = eb.kopie_taugt(str(self.ordner), programm="gibt_es_nicht.exe")
        self.assertFalse(taugt)
        self.assertIn("fehlt", grund)

    def test_nicht_startbares_programm_ist_kein_urteil(self):
        """Startet die Huelle gar nicht, liegt es nicht an der Bibliothek.

        Die Huelle kommt aus dem eigenen Ordner; laesst sie sich nicht
        ausfuehren (Virenwaechter, fremde Architektur), haette das
        mitgelieferte Werkzeug dasselbe Problem. Geurteilt wird nur ueber
        das, was messbar ist - sonst wuerde eine voellig gesunde eigene
        Bibliothek wegen eines fremden Problems verworfen.
        """
        pfad = self.ordner / "kaputt.exe"
        pfad.write_bytes(b"kein gueltiges Programm")
        taugt, grund = eb.kopie_taugt(str(self.ordner), programm="kaputt.exe")
        self.assertTrue(taugt)
        self.assertEqual("", grund)

    def test_der_pruefgriff_erzwingt_das_laden(self):
        """Ohne Argumente laedt .NET die Bibliothek gar nicht erst.

        Deshalb ruft der Selbsttest ``read`` auf eine Datei, die es nicht
        gibt - genau daran ist der Fehler am 23.09.2026 aufgefallen, nachdem
        ein argumentloser Aufruf "taugt" gemeldet hatte.
        """
        self.assertEqual("read", eb.SELBSTTEST[0])
        self.assertIn("--source", eb.SELBSTTEST)

    def test_untauglich_wird_gemerkt_und_nicht_benutzt(self):
        werkzeug = _werkzeugordner_bauen(self.ordner)
        libs = self.ordner / "libs"
        libs.mkdir()
        (libs / "LibProsperoPkg.dll").write_bytes(b"passt-nicht")
        arbeit = self.ordner / "kfg"
        arbeit.mkdir()
        kopie = arbeit / eb.KOPIE_NAME
        kopie.mkdir()
        with open(kopie / eb.MERKZETTEL, "w", encoding="utf-8") as datei:
            import json as _json
            _json.dump({"LibProsperoPkg.dll": eb.pruefsumme(
                str(libs / "LibProsperoPkg.dll")),
                "_fassung": eb.MERKZETTEL_FASSUNG,
                "_untauglich": "Could not load file or assembly"}, datei)

        ordner = eb.einsatzordner(str(werkzeug), str(arbeit), str(libs))
        self.assertEqual(str(werkzeug), ordner,
                         "eine als untauglich erkannte Bibliothek darf nicht "
                         "doch benutzt werden")
        self.assertIn("Could not load", eb.letzter_befund(str(arbeit)))

    def test_ohne_befund_leerer_text(self):
        self.assertEqual("", eb.letzter_befund(str(self.ordner)))


class VerdrahtungTests(unittest.TestCase):
    """Greift der Ordner ueberhaupt im Bauweg?"""

    def test_prosperopkg_zieht_eigene_bibliotheken_vor(self):
        from ps5_validator.utils import prosperopkg
        self.assertTrue(hasattr(prosperopkg, "_eigene_bibliotheken_vorziehen"))
        quelle = Path(prosperopkg.__file__).read_text(encoding="utf-8")
        self.assertIn("_eigene_bibliotheken_vorziehen(pfad)", quelle,
                      "werkzeug_finden muss den Umweg nehmen")

    def test_ohne_eigene_bleibt_der_pfad_der_mitgelieferte(self):
        from ps5_validator.utils import prosperopkg
        pfad = prosperopkg.werkzeug_finden()
        if not pfad:
            self.skipTest("Werkzeug nicht mitgeliefert")
        if eb.gefundene():
            self.skipTest("im Projekt liegt gerade eine eigene Bibliothek")
        self.assertIn(prosperopkg.WERKZEUGORDNER, pfad)

    def test_diagnose_meldet_den_zustand(self):
        """Der Bericht muss sagen, mit welcher Bibliothek gebaut wurde.

        Sonst waere ein Fehlerbild aus einem Lauf mit eigener DLL nicht von
        einem mit der mitgelieferten zu unterscheiden.
        """
        from ps5_validator.utils import diagnose_befund
        self.assertTrue(hasattr(diagnose_befund.Diagnosebericht,
                                "_diagnose_eigene_bibliotheken"))
        zeilen = diagnose_befund.Diagnosebericht._diagnose_eigene_bibliotheken(
            diagnose_befund.Diagnosebericht.__new__(
                diagnose_befund.Diagnosebericht))
        self.assertTrue(zeilen)
        self.assertIn("Eigene Bibliotheken", " ".join(str(z) for z in zeilen))




class VeralteteKopieTests(unittest.TestCase):
    """Eine Kopie aus einer aelteren Fassung des Mechanismus.

    Am 23.09.2026 gemessen: In einem Einstellungsordner, den niemand mehr
    auf dem Schirm hatte, lag eine Arbeitskopie aus einem frueheren Lauf -
    angelegt, bevor es den Selbsttest gab. Ihr Merkzettel passte zu den
    Pruefsummen, also wurde weder neu gespiegelt noch geprueft, und die
    unpassende Bibliothek blieb in Benutzung. Zwei echte Tests fielen
    daran. Die Fassungsnummer im Merkzettel macht solche Kopien ungueltig.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        wo = Path(self._tmp.name)
        self.werkzeug = _werkzeugordner_bauen(wo)
        self.libs = wo / "libs"
        self.libs.mkdir()
        (self.libs / "LibProsperoPkg.dll").write_bytes(b"eigene-fassung")
        self.arbeit = wo / "kfg"
        self.arbeit.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _merkzettel_schreiben(self, inhalt: dict) -> Path:
        import json as _json
        kopie = self.arbeit / eb.KOPIE_NAME
        kopie.mkdir(parents=True, exist_ok=True)
        (kopie / "veraltet.txt").write_bytes(b"Rest aus dem alten Lauf")
        with open(kopie / eb.MERKZETTEL, "w", encoding="utf-8") as datei:
            _json.dump(inhalt, datei)
        return kopie

    def test_merkzettel_ohne_fassung_gilt_als_veraltet(self):
        kopie = self._merkzettel_schreiben(
            {"LibProsperoPkg.dll": eb.pruefsumme(
                str(self.libs / "LibProsperoPkg.dll"))})
        eb.einsatzordner(str(self.werkzeug), str(self.arbeit), str(self.libs))
        self.assertFalse((kopie / "veraltet.txt").exists(),
                         "eine veraltete Kopie muss frisch gespiegelt werden")

    def test_neuer_merkzettel_traegt_die_fassung(self):
        eb.einsatzordner(str(self.werkzeug), str(self.arbeit), str(self.libs))
        import json as _json
        with open(self.arbeit / eb.KOPIE_NAME / eb.MERKZETTEL,
                  encoding="utf-8") as datei:
            self.assertEqual(eb.MERKZETTEL_FASSUNG,
                             _json.load(datei).get("_fassung"))

    def test_gleiche_fassung_wird_nicht_neu_gespiegelt(self):
        eb.einsatzordner(str(self.werkzeug), str(self.arbeit), str(self.libs))
        marke = self.arbeit / eb.KOPIE_NAME / "prosperopkg.exe"
        zeit = marke.stat().st_mtime_ns
        eb.einsatzordner(str(self.werkzeug), str(self.arbeit), str(self.libs))
        self.assertEqual(zeit, marke.stat().st_mtime_ns)


class MacSuchwurzelTests(unittest.TestCase):
    """Auf dem Mac gehoert ``libs`` NEBEN die .app, nicht hinein.

    ``Contents/Resources`` ist beim Signieren versiegelt - eine dort
    abgelegte Datei macht das Buendel ungueltig, und auf Apple Silicon
    startet es dann gar nicht mehr (am 25.08.2026 im CI erlebt). Deshalb
    sucht das Modul zusaetzlich in dem Ordner, in dem die .app liegt.
    """

    def test_neben_der_app_wird_gesucht(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as ordner:
            wo = Path(ordner)
            exe = wo / "PS5 Converter.app" / "Contents" / "MacOS"
            exe.mkdir(parents=True)
            (wo / "libs").mkdir()
            with mock.patch.object(sys, "platform", "darwin"),                     mock.patch.object(sys, "argv", [str(exe / "programm")]):
                wurzeln = eb._suchwurzeln()
                self.assertIn(str(wo), wurzeln,
                              "der Ordner neben der .app muss dabei sein")

    def test_resources_wird_nicht_benutzt(self):
        """Dort abzulegen wuerde die Signatur brechen - also nie suchen."""
        from unittest import mock
        with tempfile.TemporaryDirectory() as ordner:
            exe = Path(ordner) / "App.app" / "Contents" / "MacOS"
            exe.mkdir(parents=True)
            with mock.patch.object(sys, "platform", "darwin"),                     mock.patch.object(sys, "argv", [str(exe / "programm")]):
                wurzeln = eb._suchwurzeln()
        self.assertFalse([w for w in wurzeln if w.endswith("Resources")])

    def test_auf_windows_keine_zusatzwurzel(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as ordner:
            exe = Path(ordner) / "MacOS"
            exe.mkdir(parents=True)
            with mock.patch.object(sys, "platform", "win32"),                     mock.patch.object(sys, "argv", [str(exe / "programm.exe")]):
                wurzeln = eb._suchwurzeln()
        self.assertNotIn(str(Path(ordner).parent), wurzeln)


if __name__ == "__main__":
    unittest.main()
