#!/usr/bin/env python3
"""Sichert den Riegel gegen das Zerschiessen gepackter AMPR-Asset-Packs ab.

Seit Fassung 0.4.2.1 (06.09.2026) kann der AMPR EMU Spieldaten in ``.pak``
Baender packen. Ausgeliefert wird dann ein Buendel aus ``ampr_emu.index``,
``ampr_assets.index``, dessen ``.runtime`` und den Baendern - alle mit **einer
gemeinsamen Build-ID**. Die fileIds im Pack-Manifest sind die Satznummern aus
den AMPRIDX3-Saetzen, also aus genau dem Index, den dieses Programm nach jedem
Einbau des AMPR EMU neu baut.

Ein Neubau vergibt diese Nummern neu. Danach zeigt das Manifest ins Leere und
der AMPR EMU meldet "fileId and path disagree". Wurden die Quelldateien beim
Packen entfernt (``remove-packed-sources``), kennt der neue Index sie
ueberhaupt nicht mehr - dann ist nichts mehr zu retten.

Geprueft werden drei Dinge:

1. **Die Erkennung unterscheidet drei Zustaende**, nicht zwei: gefunden, nicht
   gefunden, und *nicht nachsehbar*. Der dritte ist der wichtige. Ein Leser,
   der einen Fehler zu "nicht gefunden" macht, meldet dem Anwender guten
   Gewissens, es sei alles in Ordnung, obwohl er nie hingesehen hat. Dieselbe
   Falle steckte in der AMPR-Anzeige (siehe test_ampr_anzeige).
2. **Ohne Asset-Schicht wird nicht gefragt.** Ein Riegel, der bei jedem
   normalen Spiel ein Fenster aufmacht, wird weggeklickt und schuetzt dann
   niemanden mehr.
3. **Jede Stelle, die einen Index baut, geht durch den Riegel.** Das prueft
   ein Waechter ueber den Syntaxbaum: Er sucht die Aufrufe selbst, statt sich
   auf eine gepflegte Liste zu verlassen. Eine sechste Baustelle faellt damit
   auf, sobald sie entsteht.
"""

from __future__ import annotations

import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import pruefumgebung  # noqa: E402

pruefumgebung.umlenken()

import PS5ImageConverter_Pro_FINAL_revised as hauptprogramm  # noqa: E402

GUI = hauptprogramm.PS5ConverterGUI
QUELLE = ROOT / "PS5ImageConverter_Pro_FINAL_revised.py"


class _Attrappe:
    """Das Noetigste einer GUI, ohne Tk.

    Die geprueften Methoden fassen nur Klassenkonstanten, ``_t`` und die
    beiden CLI-Merker an - eine echte Oberflaeche waere hier nur Ballast und
    wuerde den Lauf an eine Anzeige binden.
    """

    _AMPR_ASSET_DATEIEN = GUI._AMPR_ASSET_DATEIEN
    _AMPR_ASSET_ENDUNG = GUI._AMPR_ASSET_ENDUNG

    # Als classmethod uebernehmen, nicht als Funktion: Sie liest die beiden
    # Konstanten ueber cls, und die stehen hier daneben.
    _ist_ampr_asset_datei = GUI.__dict__["_ist_ampr_asset_datei"]
    _ampr_asset_pack_vorhanden = GUI._ampr_asset_pack_vorhanden
    _ampr_index_neubau_erlaubt = GUI._ampr_index_neubau_erlaubt
    _ampr_index_neubau_erlaubt_roh = GUI._ampr_index_neubau_erlaubt_roh

    def __init__(self, *, cli: bool = False, trotzdem: bool = False):
        self._cli_mode = cli
        self._cli_ampr_assets = trotzdem
        self.protokoll: list[str] = []
        self.gefragt = 0

    def _t(self, schluessel, **werte):
        return schluessel

    def _append_to_log(self, text):
        self.protokoll.append(str(text))

    def _ask_yesno_threadsafe(self, titel, text, default_yes=True):
        self.gefragt += 1
        return False


class ErkennungTests(unittest.TestCase):
    """Was zaehlt als Asset-Schicht - und was heisst "nicht nachsehbar"?"""

    def test_namen_werden_erkannt(self):
        for name in ("ampr_assets.index", "AMPR_ASSETS.INDEX",
                     "ampr_assets.index.runtime", "ampr_pack_0000.pak",
                     "irgendwas.PAK", "/app0/ampr_assets.index",
                     r"C:\spiel\ampr_pack_0001.pak"):
            with self.subTest(name=name):
                self.assertTrue(GUI._ist_ampr_asset_datei(name), name)

    def test_gegenprobe_normale_namen(self):
        """Sonst pruefte der Test oben nur, dass irgendetwas True liefert."""
        for name in ("ampr_emu.index", "eboot.bin", "libSceAmpr.sprx",
                     "param.json", "paket.pkg", "", "ampr_assets.index.crc"):
            with self.subTest(name=name):
                self.assertFalse(GUI._ist_ampr_asset_datei(name), name)

    def test_ordner_ohne_schicht(self):
        with tempfile.TemporaryDirectory() as ordner:
            Path(ordner, "eboot.bin").write_bytes(b"x")
            Path(ordner, "ampr_emu.index").write_bytes(b"x")
            self.assertIs(_Attrappe()._ampr_asset_pack_vorhanden(ordner), False)

    def test_ordner_mit_schicht(self):
        with tempfile.TemporaryDirectory() as ordner:
            Path(ordner, "ampr_assets.index").write_bytes(b"x")
            self.assertIs(_Attrappe()._ampr_asset_pack_vorhanden(ordner), True)

    def test_ordner_mit_band(self):
        with tempfile.TemporaryDirectory() as ordner:
            Path(ordner, "ampr_pack_0000.pak").write_bytes(b"x")
            self.assertIs(_Attrappe()._ampr_asset_pack_vorhanden(ordner), True)

    def test_nicht_nachsehbar_ist_nicht_nein(self):
        """Der Kern der Sache.

        Ein Pfad, der kein Ordner ist, muss ``None`` liefern - nicht ``False``.
        Mit ``glob`` oder ``is_file`` waere hier stillschweigend "nichts
        gefunden" herausgekommen, und der Riegel haette nie gegriffen.
        """
        with tempfile.TemporaryDirectory() as ordner:
            datei = Path(ordner, "keine_ordner.txt")
            datei.write_bytes(b"x")
            self.assertIsNone(_Attrappe()._ampr_asset_pack_vorhanden(str(datei)))
            self.assertIsNone(_Attrappe()._ampr_asset_pack_vorhanden(
                os.path.join(ordner, "gibt-es-nicht")))
            self.assertIsNone(_Attrappe()._ampr_asset_pack_vorhanden(""))

    def test_glob_haette_den_fehler_verschluckt(self):
        """Gegenprobe zur Bauart, nicht zum Ergebnis.

        Belegt, dass die Wahl von ``os.scandir`` kein Geschmacksurteil ist:
        Dieselbe Frage mit ``glob`` beantwortet, verschluckt den Fehler.
        """
        import glob as glob_modul
        with tempfile.TemporaryDirectory() as ordner:
            datei = Path(ordner, "keine_ordner.txt")
            datei.write_bytes(b"x")
            self.assertEqual(glob_modul.glob(str(datei / "*.pak")), [],
                             "glob meldet hier eine leere Liste statt eines "
                             "Fehlers - deshalb scandir")


class RiegelTests(unittest.TestCase):
    """Wann wird gefragt, wann nicht, und was passiert ohne Fenster?"""

    def test_ohne_schicht_wird_nicht_gefragt(self):
        with tempfile.TemporaryDirectory() as ordner:
            Path(ordner, "eboot.bin").write_bytes(b"x")
            app = _Attrappe()
            self.assertTrue(app._ampr_index_neubau_erlaubt(ordner))
            self.assertEqual(app.gefragt, 0,
                             "Ein Riegel, der bei jedem normalen Spiel fragt, "
                             "wird weggeklickt und schuetzt dann nichts mehr.")

    def test_mit_schicht_wird_gefragt(self):
        with tempfile.TemporaryDirectory() as ordner:
            Path(ordner, "ampr_assets.index").write_bytes(b"x")
            app = _Attrappe()
            self.assertFalse(app._ampr_index_neubau_erlaubt(ordner))
            self.assertEqual(app.gefragt, 1)

    def test_unlesbar_wird_auch_gefragt(self):
        """"Konnte nicht nachsehen" fuehrt zur Frage, nicht zum Durchwinken."""
        with tempfile.TemporaryDirectory() as ordner:
            datei = Path(ordner, "keine_ordner.txt")
            datei.write_bytes(b"x")
            app = _Attrappe()
            self.assertFalse(app._ampr_index_neubau_erlaubt(str(datei)))
            self.assertEqual(app.gefragt, 1)

    def test_cli_baut_ohne_schalter_nicht(self):
        with tempfile.TemporaryDirectory() as ordner:
            Path(ordner, "ampr_pack_0000.pak").write_bytes(b"x")
            app = _Attrappe(cli=True)
            self.assertFalse(app._ampr_index_neubau_erlaubt(ordner))
            self.assertEqual(app.gefragt, 0, "im CLI gibt es kein Fenster")
            self.assertIn("ampr.assets_cli_skipped", app.protokoll)

    def test_cli_mit_schalter_baut(self):
        with tempfile.TemporaryDirectory() as ordner:
            Path(ordner, "ampr_pack_0000.pak").write_bytes(b"x")
            app = _Attrappe(cli=True, trotzdem=True)
            self.assertTrue(app._ampr_index_neubau_erlaubt(ordner))
            self.assertIn("ampr.assets_cli_allowed", app.protokoll)

    def test_ja_schalter_entscheidet_das_nicht_mit(self):
        """``--ja`` darf den Riegel nicht mitentscheiden.

        Im CLI-Betrieb ersetzt ``_run_cli`` ``messagebox.askyesno`` durch eine
        Funktion, die stets ``--ja`` zurueckgibt. Genau deshalb liest der
        Riegel einen **eigenen** Merker - sonst wuerde ein Schalter fuer
        Ueberschreib-Rueckfragen nebenbei ein Spiel unbrauchbar machen.
        """
        quelle = QUELLE.read_text(encoding="utf-8")
        self.assertIn("_cli_ampr_assets", quelle)
        baum = ast.parse(quelle)
        gefunden = False
        for knoten in ast.walk(baum):
            if (isinstance(knoten, ast.FunctionDef)
                    and knoten.name == "_ampr_index_neubau_erlaubt_roh"):
                text = ast.unparse(knoten)
                gefunden = True
                self.assertIn("_cli_ampr_assets", text)
                for verboten in ("_cli_yes", "cli_ja", "args.ja"):
                    self.assertNotIn(verboten, text)
        self.assertTrue(gefunden, "Die Rueckfrage-Methode heisst nicht mehr so "
                                  "- dieser Test misst dann nichts.")


class ZweiSchreiberTests(unittest.TestCase):
    """Unsere Fassung und die von MkPFS muessen dieselbe Datei liefern.

    Es gibt zwei Wege, einen ``ampr_emu.index`` zu schreiben:
    ``_build_ampr_index_local`` im Hauptprogramm (auch fuer den FTP-Weg, ueber
    ``_ampr_write_index``) und ``mkpfs.ampr.build_ampr_index`` im eingebetteten
    Werkzeug. Beide beschreiben denselben Ordner - laufen sie auseinander,
    haengt es vom Weg ab, welche Datei auf der Konsole landet, und der
    Unterschied faellt erst dort auf.

    Am 07.09.2026 wurde behauptet, sie erzeugten bereits unterschiedliche
    Indexe. Nachgemessen: Sie sind byteweise gleich. Diese Pruefung haelt das
    fest, statt sich auf die Messung von damals zu verlassen.
    """

    @staticmethod
    def _spielordner(basis: Path) -> Path:
        spiel = basis / "spiel"
        (spiel / "sce_sys").mkdir(parents=True)
        (spiel / "fakelib").mkdir()
        for name, inhalt in (("eboot.bin", b"E" * 100),
                             ("sce_sys/param.json", b"{}"),
                             ("fakelib/libSceAmpr.sprx", b"A" * 50),
                             ("daten.bin", b"D" * 1000)):
            (spiel / name).write_bytes(inhalt)
        return spiel

    def test_beide_wege_liefern_dieselbe_datei(self):
        import tkinter as tk
        try:
            wurzel = tk._default_root or tk.Tk()
            wurzel.withdraw()
        except Exception:                       # pragma: no cover
            raise unittest.SkipTest("keine Anzeige verfuegbar")
        app = GUI(wurzel)
        if not app.mkpfs_dir:
            app.mkpfs_dir = app._extract_embedded_mkpfs()
        if not app.mkpfs_dir:
            self.skipTest("MkPFS nicht auspackbar")
        if app.mkpfs_dir not in sys.path:
            sys.path.insert(0, app.mkpfs_dir)
        from mkpfs.ampr import build_ampr_index  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as ordner:
            basis = Path(ordner)
            spiel = self._spielordner(basis)
            unser, fremd = basis / "unser.index", basis / "fremd.index"
            app._build_ampr_index_local(spiel, unser)
            build_ampr_index(spiel, fremd)
            self.assertEqual(
                unser.read_bytes(), fremd.read_bytes(),
                "Die beiden Index-Schreiber liefern verschiedene Dateien. "
                "Dann haengt es vom gewaehlten Weg ab, welcher Index auf der "
                "Konsole landet - und der Unterschied faellt erst dort auf.")
            self.assertGreater(unser.stat().st_size, 0)


class SchalterWirktTests(unittest.TestCase):
    """``--ampr-no-index`` muss auch bei einem APR-Titel greifen.

    Der Schalter setzt ``spec["ampr_rebuild_index"] = False``. Eine der beiden
    Baustellen im selben Ablauf las das, die andere nicht:
    ``_prepare_ampr_support`` rief ``_auto_generate_ampr_index`` unbedingt auf
    und baute den Index doch neu. Bei einem erkannten APR-Titel - also genau
    dort, wo der AMPR EMU ueberhaupt eine Rolle spielt - war der Schalter
    damit wirkungslos.
    """

    def _funktion(self, name):
        baum = ast.parse(QUELLE.read_text(encoding="utf-8"))
        for knoten in ast.walk(baum):
            if (isinstance(knoten, ast.FunctionDef) and knoten.name == name):
                return knoten
        return None

    def test_prepare_ampr_support_liest_den_schalter(self):
        funktion = self._funktion("_prepare_ampr_support")
        self.assertIsNotNone(
            funktion,
            "_prepare_ampr_support heisst nicht mehr so - dieser Test misst "
            "dann nichts mehr.")
        text = ast.unparse(funktion)
        self.assertIn("_auto_generate_ampr_index", text,
                      "Der Bauaufruf ist weg - dann passt dieser Test nicht "
                      "mehr zum Quelltext.")
        self.assertIn(
            "ampr_rebuild_index", text,
            "_prepare_ampr_support baut den Index, ohne --ampr-no-index zu "
            "beachten.")

    def test_schalter_ist_verdrahtet(self):
        """Gegenprobe: Der Schalter fuellt den Wert ueberhaupt."""
        parser = hauptprogramm._build_cli_parser()
        self.assertFalse(parser.parse_args([]).ampr_no_index)
        self.assertTrue(parser.parse_args(["--ampr-no-index"]).ampr_no_index)


class AlleBaustellenTests(unittest.TestCase):
    """Waechter: Geht jede Stelle, die einen Index baut, durch den Riegel?

    Gesucht wird ueber den Syntaxbaum, nicht ueber eine gepflegte Liste von
    Zeilennummern: Eine Liste veraltet beim ersten Umbau, und dieser Test
    meldete dann "alles gut" ueber einen Stand, den es nicht mehr gibt.
    """

    #: Aufrufe, die einen ampr_emu.index entstehen lassen.
    BAUAUFRUFE = ("ensure_ampr_index", "_build_ampr_index_local",
                  "_ampr_write_index")

    #: Die Weiterleitungen selbst - dort gehoert kein Riegel hin, sie bauen
    #: nur, was ihre Aufrufer entschieden haben.
    WEITERLEITUNGEN = frozenset({"_build_ampr_index_local", "_ampr_write_index"})

    RIEGEL = ("_ampr_index_neubau_erlaubt", "_ampr_index_neubau_erlaubt_roh")

    @staticmethod
    def _aufrufname(knoten: ast.Call) -> str:
        ziel = knoten.func
        if isinstance(ziel, ast.Attribute):
            return ziel.attr
        if isinstance(ziel, ast.Name):
            return ziel.id
        return ""

    @classmethod
    def _aeusserste_funktionen(cls, knoten):
        """Nur die aeussersten Funktionen - ohne in sie hineinzusteigen.

        Der Riegel steht in der Methode, der Bauaufruf oft in einer darin
        verschachtelten worker-Funktion. Wer beide getrennt betrachtet,
        meldet die innere faelschlich als ungesichert - genau das tat dieser
        Test in seiner ersten Fassung.
        """
        for kind in ast.iter_child_nodes(knoten):
            if isinstance(kind, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield kind          # und bewusst nicht weiter hinein
            else:
                yield from cls._aeusserste_funktionen(kind)

    def _funktionen(self):
        baum = ast.parse(QUELLE.read_text(encoding="utf-8"))
        yield from self._aeusserste_funktionen(baum)

    def test_waechter_findet_ueberhaupt_baustellen(self):
        """Ankerpruefung.

        Ohne sie waere der Test unten stumm richtig, sobald sich einer der
        Aufrufnamen aendert: Er haette dann null Stellen zu pruefen und
        meldete Erfolg.
        """
        anzahl = sum(
            1 for f in self._funktionen()
            if f.name not in self.WEITERLEITUNGEN
            for k in ast.walk(f)
            if isinstance(k, ast.Call) and self._aufrufname(k) in self.BAUAUFRUFE
        )
        self.assertGreaterEqual(
            anzahl, 4,
            "Es wurden weniger Bauaufrufe gefunden als bekannt (fuenf am "
            "07.09.2026). Entweder wurde umgebaut - dann gehoert dieser Test "
            "nachgezogen - oder die Auswertung passt nicht mehr zum Quelltext.")

    def test_jede_baustelle_hat_ihren_riegel(self):
        ungesichert = []
        for funktion in self._funktionen():
            if funktion.name in self.WEITERLEITUNGEN:
                continue
            text = ast.unparse(funktion)
            baut = any(
                isinstance(k, ast.Call)
                and self._aufrufname(k) in self.BAUAUFRUFE
                for k in ast.walk(funktion))
            if not baut:
                continue
            if not any(riegel in text for riegel in self.RIEGEL):
                ungesichert.append("%s (Zeile %d)"
                                   % (funktion.name, funktion.lineno))
        self.assertEqual(
            ungesichert, [],
            "Diese Stellen bauen einen ampr_emu.index, ohne vorher zu "
            "pruefen, ob eine gepackte Asset-Schicht danebenliegt. Ein "
            "Neubau macht deren Manifest unbrauchbar.")


if __name__ == "__main__":
    unittest.main()
