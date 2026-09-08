# -*- coding: utf-8 -*-
"""Prueft das Packprofil der neuen AMPR-EMU-Methode.

**Wogegen dieser Test steht.** Am 07.09.2026 trug die Ausschlussliste die
Systemdateien nur als ``**/eboot.bin`` - ein Muster, das mindestens ein
Verzeichnis davor verlangt und die Datei im Wurzelverzeichnis von ``/app0``
deshalb nicht trifft. Genau dort liegt sie. Ein Probelauf mit acht Dateien
packte ``eboot.bin`` mit; auf der Konsole waere das nicht als Fehlermeldung
aufgefallen, sondern als Spiel, das nicht mehr startet: Das Ladeprogramm
liest ``eboot.bin``, bevor der AMPR EMU ueberhaupt geladen ist.

Der Test packt deshalb wirklich - mit ``ampr_pack.py``, gegen einen echten
``ampr_emu.index`` - und sieht nach, was lose geblieben ist. Eine reine
Musterpruefung haette den Fehler nicht gefunden, denn die Muster waren ja
vorhanden; falsch war, was sie treffen.
"""
from __future__ import annotations

import os
import sys
import tomllib
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))
sys.path.insert(0, str(PROJEKT / "MkPFS-1.0.0"))

from ps5_validator.utils import ampr_assetpakete as ap  # noqa: E402


class ProfilAufbau(unittest.TestCase):
    """Das erzeugte Profil muss lesbar sein und das Richtige aussagen."""

    def test_profil_ist_gueltiges_toml(self):
        daten = tomllib.loads(ap.standardprofil_text())
        self.assertEqual(daten["pack"]["default_action"], "loose",
                         "Was keine Regel trifft, muss lose bleiben")
        self.assertEqual(len(daten["rule"]), 1)
        self.assertEqual(daten["rule"][0]["include"], ["**"])

    def test_arbeiterzahl_nur_wenn_gesetzt(self):
        ohne = tomllib.loads(ap.standardprofil_text(0))
        self.assertNotIn("workers", ohne["pack"],
                         "0 heisst: das Werkzeug entscheidet selbst")
        mit = tomllib.loads(ap.standardprofil_text(6))
        self.assertEqual(mit["pack"]["workers"], 6)

    def test_systemdateien_auch_ohne_verzeichnis(self):
        """Jedes ``**/x`` braucht ein ``x`` daneben - sonst faellt die
        Wurzelebene durch."""
        muster = set(ap.NIE_PACKEN)
        for eintrag in sorted(muster):
            if not eintrag.startswith("**/"):
                continue
            blank = eintrag[3:]
            self.assertIn(
                blank, muster,
                "%s trifft die Wurzelebene von /app0 nicht - %s fehlt"
                % (eintrag, blank))

    def test_variante_muss_packfaehig_sein(self):
        self.assertTrue(ap.variante_kann_packen("test-pack"))
        self.assertTrue(ap.variante_kann_packen("test-debug-pack"))
        self.assertFalse(ap.variante_kann_packen("test-nopack"),
                         "nopack liest keine Baender")
        self.assertFalse(ap.variante_kann_packen("no debug"))


@unittest.skipUnless(ap.einsatzbereit()[0],
                     "Packwerkzeug oder lz4 fehlt")
class EchterPacklauf(unittest.TestCase):
    """Packt einen kleinen Baum und sieht nach, was lose blieb."""

    def _baum(self, wurzel: Path) -> Path:
        app0 = wurzel / "app0"
        (app0 / "assets").mkdir(parents=True)
        (app0 / "sce_sys").mkdir(parents=True)
        (app0 / "sce_module").mkdir(parents=True)
        for i in range(4):
            (app0 / "assets" / ("t%d.dat" % i)).write_bytes(
                ((b"ABCDEFGH" * 512) + bytes([i])) * 24)
        # Die Dateien, die niemals in ein Band duerfen.
        (app0 / "eboot.bin").write_bytes(b"\x7fELF" + b"\x00" * 2048)
        (app0 / "libSceTest.sprx").write_bytes(b"\x7fELF" + b"\x00" * 2048)
        (app0 / "sce_sys" / "param.sfo").write_bytes(b"\x00PSF" + b"\x00" * 512)
        (app0 / "sce_module" / "libc.prx").write_bytes(b"\x7fELF" + b"\x00" * 512)
        return app0

    def test_systemdateien_bleiben_lose(self):
        import tempfile

        from mkpfs.ampr import build_ampr_index

        with tempfile.TemporaryDirectory(prefix="ampr_pack_test_") as basis:
            wurzel = Path(basis)
            app0 = self._baum(wurzel)
            index = app0 / "ampr_emu.index"
            build_ampr_index(app0, index)

            raus = wurzel / "packed"
            profil = ap.profil_schreiben(str(wurzel / "profil.toml"), arbeiter=2)
            ergebnis = ap.packen(str(app0), str(index), str(raus), profil)

            lose = set(ergebnis.get("loose_paths") or [])
            for pflicht in ("eboot.bin", "libSceTest.sprx",
                            "sce_sys/param.sfo", "sce_module/libc.prx"):
                self.assertIn(pflicht, lose,
                              "%s wurde gepackt - das Spiel startet dann nicht"
                              % pflicht)

            # Die Nutzdaten sollen sehr wohl im Band liegen, sonst haette
            # die Ausschlussliste zu weit gegriffen.
            for datei in ("assets/t0.dat", "assets/t3.dat"):
                self.assertNotIn(datei, lose,
                                 "%s haette gepackt werden sollen" % datei)

            # Und die Baender muessen den Inhalt Byte fuer Byte tragen.
            ap.pruefen(str(raus / ap.MANIFEST_NAME), app0=str(app0))

    def test_uebernahme_laesst_pruefsummen_zurueck(self):
        import tempfile

        from mkpfs.ampr import build_ampr_index

        with tempfile.TemporaryDirectory(prefix="ampr_pack_test_") as basis:
            wurzel = Path(basis)
            app0 = self._baum(wurzel)
            index = app0 / "ampr_emu.index"
            build_ampr_index(app0, index)

            raus = wurzel / "packed"
            profil = ap.profil_schreiben(str(wurzel / "profil.toml"))
            ap.packen(str(app0), str(index), str(raus), profil)
            ap.bestand_uebernehmen(str(raus), str(app0))

            im_spiel = set(os.listdir(app0))
            self.assertIn(ap.MANIFEST_NAME, im_spiel)
            self.assertIn(ap.LAUFZEIT_NAME, im_spiel)
            self.assertTrue(any(n.endswith(".pak") for n in im_spiel))
            self.assertNotIn(
                ap.PRUEFSUMMEN_NAME, im_spiel,
                "Die Konsole liest die Pruefsummenbeilage nie - sie bleibt "
                "beim PC-Bestand")


class EigenstaendigkeitTests(unittest.TestCase):
    """Die fertige Programmdatei muss ohne Nachinstallieren auskommen.

    Das ist das Versprechen der Auslieferung: eine Datei herunterladen,
    starten, arbeiten. Die neue AMPR-Methode brach es bis zum 07.09.2026
    gleich zweifach.

    ``_python_ruf`` suchte ``python3``/``python``/``py`` im System. Wer keines
    installiert hatte, bekam "Kein Python gefunden"; wer eines hatte, brauchte
    darin zusaetzlich ``lz4``. Dabei gibt es das Muster im Haus laengst: Das
    eingebettete PS4-Werkzeug laesst die Programmdatei sich **selbst** mit
    ``--ps4ffpsc`` aufrufen.

    Dazu kam, dass ``lz4`` in keiner ``.spec`` stand. Der Quelltext importiert
    es nirgends unmittelbar - PyInstaller sieht es deshalb nicht. In der
    fertigen Datei fehlte es also selbst dann, wenn der Bau es installiert
    hatte.
    """

    QUELLE = Path(ap.__file__)
    SPECS = ("PS5ImageConverter_Pro.spec",
             "PS5ImageConverter_Pro_linux.spec",
             "PS5ImageConverter_Pro_macos.spec")

    def setUp(self):
        self.merker = getattr(sys, "frozen", None)
        self.addCleanup(self._frozen_zurueck)

    def _frozen_zurueck(self):
        if self.merker is None:
            sys.__dict__.pop("frozen", None)
        else:
            sys.frozen = self.merker

    def test_gebuendelt_ruft_sich_selbst_auf(self):
        """Kein fremdes Python - die Programmdatei ist ihr eigener Interpreter."""
        sys.frozen = True
        self.assertEqual(ap._python_ruf(), [sys.executable, ap.SELBSTAUFRUF])

    def test_aus_der_quelle_laeuft_es_mit_demselben_python(self):
        sys.__dict__.pop("frozen", None)
        ruf = ap._python_ruf()
        self.assertEqual(ruf[0], sys.executable)
        self.assertTrue(ruf[1].endswith("ampr_pack.py"), ruf)

    def test_kein_suchen_nach_einem_python_im_system(self):
        """Der alte Weg darf nicht zurueckkommen.

        Er faellt nur beim Anwender auf, nie auf dem Entwicklungsrechner -
        dort ist immer ein Python installiert.
        """
        import ast
        quelle = self.QUELLE.read_text(encoding="utf-8")
        for knoten in ast.walk(ast.parse(quelle)):
            if (isinstance(knoten, ast.FunctionDef)
                    and knoten.name == "_python_ruf"):
                rumpf = [k for k in knoten.body
                         if not (isinstance(k, ast.Expr)
                                 and isinstance(k.value, ast.Constant)
                                 and isinstance(k.value.value, str))]
                text = chr(10).join(ast.unparse(k) for k in rumpf)
                self.assertNotIn("shutil.which", text)
                self.assertIn("SELBSTAUFRUF", text)
                return
        self.fail("_python_ruf heisst nicht mehr so - dieser Test misst dann "
                  "nichts.")

    def test_das_hauptprogramm_kennt_den_schalter(self):
        """Ohne die Gegenstelle liefe der Selbstaufruf ins Programmfenster."""
        haupt = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8")
        self.assertIn("ampr_assetpakete.SELBSTAUFRUF", haupt)
        self.assertIn("_run_ampr_pack_subcommand", haupt)

    def test_lz4_steht_in_allen_drei_specs(self):
        """Sonst fehlt es in der fertigen Datei, obwohl der Bau es hatte."""
        for name in self.SPECS:
            with self.subTest(spec=name):
                text = (PROJEKT / name).read_text(encoding="utf-8")
                self.assertIn("'lz4'", text,
                              "lz4 fehlt in den hiddenimports von " + name)

    @staticmethod
    def _importe(pfad):
        """Alle Module, die eine Datei einbindet."""
        import ast
        namen = set()
        baum = ast.parse(Path(pfad).read_text(encoding="utf-8"))
        for k in ast.walk(baum):
            if isinstance(k, ast.Import):
                for a in k.names:
                    namen.add(a.name)
            elif isinstance(k, ast.ImportFrom) and k.module and k.level == 0:
                namen.add(k.module)
        return namen

    def test_jedes_modul_des_packwerkzeugs_ist_erreichbar(self):
        """Was das Werkzeug einbindet, muss in der fertigen Datei liegen.

        ``ampr_pack.py`` und ``ampr_pack_format.py`` liegen als **Datenordner**
        bei. PyInstaller liest ihre Importe nicht - was sie brauchen, muss
        entweder das Hauptprogramm selbst einbinden oder in ``hiddenimports``
        stehen.

        Am 08.09.2026 fehlte so ``ctypes.util``. ``ctypes`` selbst ist
        eingebettet, samt ``_endian``, ``_layout`` und ``wintypes`` - das
        Untermodul ``util`` zieht aber nur herein, wer es ausdruecklich nennt.
        Die neue Methode brach beim Anwender ab, sobald sie loslief:
        ``ModuleNotFoundError: No module named 'ctypes.util'``. Auf dem
        Entwicklungsrechner faellt so etwas nie auf - dort laeuft alles gegen
        ein vollstaendiges Python.

        Die Regel ist bewusst streng: Ein ueberfluessiger Eintrag in
        ``hiddenimports`` kostet nichts, ein fehlender kostet den Anwender
        seinen Lauf.
        """
        ordner = ap.werkzeugordner_finden()
        if not ordner:
            self.skipTest("Werkzeugordner nicht mitgeliefert")
        gebraucht = set()
        for datei in ("ampr_pack.py", "ampr_pack_format.py"):
            gebraucht |= self._importe(os.path.join(ordner, datei))
        gebraucht -= {"__future__", "ampr_pack_format", "ampr_pack"}

        haupt_datei = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"
        vom_hauptprogramm = self._importe(haupt_datei)

        fehlend = {}
        for name in self.SPECS:
            spec = (PROJEKT / name).read_text(encoding="utf-8")
            offen = sorted(
                m for m in gebraucht
                if ("'%s'" % m) not in spec and m not in vom_hauptprogramm)
            if offen:
                fehlend[name] = offen
        self.assertEqual(
            fehlend, {},
            "Diese Module bindet das Packwerkzeug ein, sie stehen aber weder "
            "in den hiddenimports der .spec noch bindet sie das Hauptprogramm "
            "selbst ein - in der fertigen Datei fehlen sie dann.")

    def test_das_werkzeug_liegt_neben_seinem_formatmodul(self):
        """``ampr_pack`` importiert ``ampr_pack_format`` als Geschwister."""
        ordner = ap.werkzeugordner_finden()
        if not ordner:
            self.skipTest("Werkzeugordner nicht mitgeliefert")
        for datei in ("ampr_pack.py", "ampr_pack_format.py"):
            self.assertTrue(os.path.isfile(os.path.join(ordner, datei)), datei)


class VierteStufeTests(unittest.TestCase):
    """Die Manifestuebersicht und die harten Grenzen.

    Die Anleitung des Autors nennt vier Stufen, und die vierte lautet "Print
    the manifest summary". Bis zum 07.09.2026 lief sie nicht mit - das Modul
    hatte die Funktion, der Bauweg rief sie nie. Damit fehlte die einzige
    Stelle, an der die **tatsaechlichen** Zahlen gegen die Grenzen der
    Laufzeit gehalten werden; die Schaetzung aus der Profilerzeugung gilt
    danach ausdruecklich nicht mehr.

    Ein Bestand ueber einer Grenze ist dabei nicht langsam, sondern
    unbrauchbar - die Laufzeit laedt ihn gar nicht erst. Deshalb bricht der
    Bauweg ab, statt zu warnen.
    """

    def test_grenzen_wie_in_der_anleitung(self):
        self.assertEqual(ap.GRENZEN["files"], 2_000_000)
        self.assertEqual(ap.GRENZEN["chunks"], 16_000_000)
        self.assertEqual(ap.GRENZEN["packs"], 1_024)

    def test_genau_auf_der_grenze_ist_erlaubt(self):
        """"at most" heisst einschliesslich - ein Abbruch waere hier falsch."""
        self.assertEqual(ap.grenzen_ueberschritten({
            "files": 2_000_000, "chunks": 16_000_000,
            "packs": [0] * 1_024}), [])

    def test_eine_ueberschreitung_wird_gemeldet(self):
        risse = ap.grenzen_ueberschritten({
            "files": 2_000_001, "chunks": 5, "packs": [0]})
        self.assertEqual(risse, [("files", 2_000_001, 2_000_000)])

    def test_leere_uebersicht_reisst_nichts(self):
        """Fehlende Angaben duerfen keinen Abbruch ausloesen."""
        self.assertEqual(ap.grenzen_ueberschritten({}), [])

    def test_der_bauweg_ruft_die_uebersicht_und_bricht_ab(self):
        """Ohne diesen Aufruf gaebe es die vierte Stufe wieder nicht."""
        haupt = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8")
        stelle = haupt.index("def _ampr_assetpakete_bauen")
        block = haupt[stelle:stelle + 6000]
        self.assertIn("ampr_assetpakete.uebersicht(", block)
        self.assertIn("grenzen_ueberschritten(", block)
        # Die Uebernahme in den Spielordner muss NACH der Grenzpruefung
        # stehen - sonst laege der unbrauchbare Bestand schon im Spiel.
        self.assertLess(block.index("grenzen_ueberschritten("),
                        block.index("bestand_uebernehmen("),
                        "Die Grenzpruefung steht hinter der Uebernahme - dann "
                        "kommt sie zu spaet.")



class WoDieMethodeGreiftTests(unittest.TestCase):
    """Die neue Methode muss auf beiden Wegen greifen, nicht nur auf einem.

    Bis zum 08.09.2026 hing sie allein am Kaestchen "AMPR EMU" beim
    Erstellen. Wer sie waehlte und dann Aufgabe 7 benutzte, bekam
    stillschweigend den alten Weg - ohne Meldung, ohne Baender, und ohne dass
    im Fenster etwas anderes gestanden haette.
    """

    HAUPT = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"

    def _funktion(self, name):
        import ast
        for knoten in ast.walk(ast.parse(self.HAUPT.read_text(encoding="utf-8"))):
            if isinstance(knoten, ast.FunctionDef) and knoten.name == name:
                return knoten
        return None

    def test_beim_erstellen(self):
        knoten = self._funktion("_integration_ampr")
        self.assertIsNotNone(knoten, "_integration_ampr heisst nicht mehr so")
        import ast
        self.assertIn("_ampr_assetpakete_bauen", ast.unparse(knoten))

    def test_in_aufgabe_sieben(self):
        knoten = self._funktion("_mode_ampr_manager")
        self.assertIsNotNone(knoten, "_mode_ampr_manager heisst nicht mehr so")
        import ast
        text = ast.unparse(knoten)
        self.assertIn(
            "_ampr_assetpakete_bauen", text,
            "Aufgabe 7 baut keine Baender - wer die neue Methode gewaehlt hat, "
            "bekommt dort stillschweigend den alten Weg.")
        # Erst der Index, dann die Baender: ampr_pack.py liest den Index.
        self.assertLess(text.index("_build_ampr_index_local"),
                        text.index("_ampr_assetpakete_bauen"),
                        "Die Baender entstehen vor dem Index - ampr_pack.py "
                        "liest ihn aber, um die Dateien zuzuordnen.")


class KlapplisteTests(unittest.TestCase):
    """Bei der neuen Methode darf nur dastehen, was sie auch lesen kann.

    Vorher standen alle Fassungen in der Liste, und die untaugliche
    ``test-nopack`` als neueste sogar an erster Stelle. Der Anwender erfuhr
    erst aus dem Protokoll, dass seine Wahl nicht traegt - eine Liste, die
    etwas anbietet, das nicht geht, ist eine Falle.
    """

    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        try:
            cls.wurzel = tk._default_root or tk.Tk()
            cls.wurzel.withdraw()
        except Exception:                       # pragma: no cover
            raise unittest.SkipTest("keine Anzeige verfuegbar")
        import PS5ImageConverter_Pro_FINAL_revised as prog
        cls.prog = prog
        cls.app = prog.PS5ConverterGUI(cls.wurzel)

    def _umschalten(self, schluessel):
        self.app.ampr_methode_var.set(self.app._t(schluessel))
        self.app._on_ampr_methode_changed()
        return list(self.app.ampr_version_combo.cget("values"))

    def _mit_varianten(self, schluessel):
        """Die Liste samt der Variante je Eintrag."""
        eintraege = self._umschalten(schluessel)
        return {e: self.app._ampr_versionsauswahl[e]["variant"]
                for e in eintraege}

    def test_asset_pack_zeigt_nur_packfaehige(self):
        gefiltert = self._mit_varianten("ampr_pack.methode_neu")
        self.addCleanup(self._umschalten, "ampr_pack.methode_normal")
        if not gefiltert:
            self.skipTest("keine packfaehige Fassung im Bestand")
        for eintrag, variante in gefiltert.items():
            self.assertTrue(
                ap.variante_kann_packen(variante),
                "%r steht in der Packliste, kann aber keine Baender lesen"
                % eintrag)

    def test_normal_zeigt_keine_packfassungen(self):
        """Sie sind nur fuer die neue Methode gedacht.

        Umgekehrt zur Pruefung darueber: In der normalen Liste haben
        ``test-pack`` und ``test-debug-pack`` nichts zu suchen.
        """
        normal = self._mit_varianten("ampr_pack.methode_normal")
        if not normal:
            self.skipTest("kein gewoehnlicher Bestand vorhanden")
        for eintrag, variante in normal.items():
            self.assertFalse(
                ap.variante_kann_packen(variante),
                "%r ist eine Packfassung und gehoert nicht in die normale "
                "Liste" % eintrag)

    def test_die_beiden_listen_teilen_den_bestand_auf(self):
        """Zusammen ergeben sie alles - keine Fassung faellt heraus.

        Ein reiner Filter koennte eine Fassung in **beiden** Listen zeigen
        oder in keiner. Beides waere falsch: Der Anwender soll jede
        mitgelieferte Fassung genau einmal finden.
        """
        normal = set(self._mit_varianten("ampr_pack.methode_normal"))
        pack = set(self._mit_varianten("ampr_pack.methode_neu"))
        self.addCleanup(self._umschalten, "ampr_pack.methode_normal")
        self.assertEqual(normal & pack, set(),
                         "Diese Fassungen stehen in beiden Listen")
        alle = {
            "%s %s" % (e["version"], e["variant"])
            for e in self.app._ampr_alle_fassungen()
            if e.get("lib") == "libSceAmpr.sprx"
        }
        if not alle:
            self.skipTest("kein AMPR-Bestand vorhanden")
        self.assertEqual(
            normal | pack, alle,
            "Zusammen ergeben die beiden Listen nicht den ganzen Bestand - "
            "eine Fassung ist nirgends waehlbar.")

    def test_zurueck_auf_normal_zeigt_wieder_alles(self):
        alle = self._umschalten("ampr_pack.methode_normal")
        self._umschalten("ampr_pack.methode_neu")
        wieder = self._umschalten("ampr_pack.methode_normal")
        self.assertEqual(alle, wieder,
                         "Die Liste blieb nach dem Zurueckschalten beschnitten")

    def test_die_wahl_faellt_auf_eine_packfaehige(self):
        """Sonst stuende eine Fassung im Feld, die es in der Liste nicht gibt."""
        self._umschalten("ampr_pack.methode_normal")
        gefiltert = self._umschalten("ampr_pack.methode_neu")
        self.addCleanup(self._umschalten, "ampr_pack.methode_normal")
        if not gefiltert:
            self.skipTest("keine packfaehige Fassung im Bestand")
        self.assertIn(self.app.ampr_version_var.get(), gefiltert)


if __name__ == "__main__":
    unittest.main(verbosity=2)
