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


class FortschrittTests(unittest.TestCase):
    """Der Anwender muss sehen, dass das Programm arbeitet.

    Zwei Meldungen aus dem Betrieb, beide am 08.09.2026:

    * Beim Anlegen der Arbeitskopie **flackerte** die Anzeige. Jedes Setzen
      des Groessentextes laesst ``_set_progress`` die eingebrannten
      Beschriftungen neu zeichnen; im Balkentakt waren das zehn
      Neuzeichnungen je Sekunde.
    * Beim Packen bewegte sich **gar nichts**. ``ampr_pack.py`` schreibt
      seinen Fortschritt auf stderr, aber die Zeilen landeten nur im
      Protokoll.
    """

    def test_fortschrittszeilen_werden_gelesen(self):
        f = ap.fortschritt_lesen
        self.assertEqual(f("[pack   0%] scanning: files 0/300"), (0.0, "scanning"))
        self.assertEqual(
            f("[pack  42%] packing: files 120/300, 1.2 GiB/3.4 GiB"),
            (42.0, "packing"))
        self.assertEqual(f("[pack 100%] finalizing: files 300/300"),
                         (100.0, "finalizing"))

    def test_gewoehnliche_zeilen_sind_kein_fortschritt(self):
        """Gegenprobe - sonst verschwaenden echte Meldungen im Balken."""
        for zeile in ("error: irgendetwas ging schief",
                      "LOG  gewoehnliche Zeile",
                      "", "   ", "[pack] ohne Zahl",
                      "packing 42%"):
            with self.subTest(zeile=zeile):
                self.assertIsNone(ap.fortschritt_lesen(zeile))

    def test_der_lauf_trennt_fortschritt_von_meldung(self):
        """Fortschrittszeilen gehoeren an den Balken, nicht ins Protokoll.

        Das Werkzeug schreibt viele davon; im Protokoll waeren sie nur
        Rauschen zwischen den Meldungen, auf die es ankommt.
        """
        import ast
        quelle = Path(ap.__file__).read_text(encoding="utf-8")
        for knoten in ast.walk(ast.parse(quelle)):
            if isinstance(knoten, ast.FunctionDef) and knoten.name == "_lauf":
                text = ast.unparse(knoten)
                self.assertIn("fortschritt_lesen", text)
                self.assertIn("else:", text,
                              "Ohne den else-Zweig gingen die "
                              "Fortschrittszeilen zusaetzlich ins Protokoll")
                return
        self.fail("_lauf heisst nicht mehr so - dieser Test misst dann nichts.")

    def test_die_groessenangabe_hat_einen_eigenen_takt(self):
        """Sonst flackert die Anzeige.

        Geprueft wird an beiden Stellen, die im Takt melden: dem Kopieren
        der Arbeitskopie und dem Packen. Beide brauchen einen zweiten,
        langsameren Takt fuer den Text - der Balken selbst kostet nichts,
        der Text zieht ein Neuzeichnen nach sich.
        """
        haupt = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8")
        for name in ("_KOPIE_GROESSE_TAKT_SEKUNDEN",
                     "_PACK_GROESSE_TAKT_SEKUNDEN"):
            self.assertIn(name, haupt, "%s fehlt - die Anzeige flackert wieder"
                          % name)

    def test_die_pruefphase_laesst_eine_uhr_laufen(self):
        """"verify" meldet nichts - ohne Uhr saehe das Fenster tot aus."""
        haupt = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8")
        self.assertIn("_ampr_pack_uhr_starten", haupt)
        self.assertIn("_ampr_pack_uhr_stoppen", haupt)
        # Angehalten wird im finally - sonst tickt sie nach einem Fehler
        # weiter und ueberschreibt die Fehlermeldung in der Statuszeile.
        # Gemessen an der AUFRUFstelle, nicht an der Definition: Die steht
        # frueher in der Datei, und ein index()-Treffer landete dort.
        import ast
        for knoten in ast.walk(ast.parse(haupt)):
            if (isinstance(knoten, ast.FunctionDef)
                    and knoten.name == "_ampr_assetpakete_bauen"):
                text = ast.unparse(knoten)
                self.assertIn("_ampr_pack_uhr_starten", text)
                self.assertIn("finally", text)
                self.assertIn("_ampr_pack_uhr_stoppen", text)
                return
        self.fail("_ampr_assetpakete_bauen heisst nicht mehr so - dieser "
                  "Test misst dann nichts.")


class RueckwegTests(unittest.TestCase):
    """Ein gepacktes Backup muss sich wieder entpacken lassen.

    Das geht, weil dieses Programm die Originaldateien **nie** entfernt: Ein
    Asset-Pack liegt daneben, nicht anstelle von etwas. Gemessen am
    08.09.2026 an einem Ordner mit elf Dateien - Packen legte sechs dazu,
    aenderte und entfernte nichts.

    Der Rueckweg ist deshalb kein Entpacken, sondern ein Loeschen: Manifest,
    ``.runtime``, die Baender - und die Pruefsummenbeilage, falls sie
    jemand mit hineingelegt hat.
    """

    @staticmethod
    def _ordner(basis):
        app0 = Path(basis, "app0")
        (app0 / "assets").mkdir(parents=True)
        (app0 / "assets" / "t.dat").write_bytes(b"X" * 4096)
        (app0 / "eboot.bin").write_bytes(bytes([127]) + b"ELF" + bytes(512))
        (app0 / "ampr_emu.index").write_bytes(b"AMPRIDX3" + bytes(64))
        return app0

    def test_findet_genau_die_packdateien(self):
        import tempfile
        with tempfile.TemporaryDirectory() as basis:
            app0 = self._ordner(basis)
            for name in (ap.MANIFEST_NAME, ap.LAUFZEIT_NAME,
                         ap.PRUEFSUMMEN_NAME,
                         "ampr_assets-assets-lane00-vol00-000.pak"):
                (app0 / name).write_bytes(b"x")
            gefunden = ap.packdateien_finden(str(app0))
            self.assertEqual(len(gefunden), 4, gefunden)
            # Gegenprobe: Was nicht dazugehoert, bleibt draussen.
            for fremd in ("eboot.bin", "ampr_emu.index"):
                self.assertNotIn(fremd, gefunden)

    def test_ohne_pack_eine_leere_liste(self):
        import tempfile
        with tempfile.TemporaryDirectory() as basis:
            app0 = self._ordner(basis)
            self.assertEqual(ap.packdateien_finden(str(app0)), [])

    def test_unlesbar_ist_nicht_leer(self):
        """``None`` heisst "konnte nicht nachsehen" - nicht "nichts da".

        Wer beides gleich behandelt, meldet "nichts zu entfernen", ohne
        hingesehen zu haben.
        """
        self.assertIsNone(ap.packdateien_finden(""))
        self.assertIsNone(ap.packdateien_finden(
            os.path.join(str(PROJEKT), "gibt-es-nicht-xyz")))

    def test_entfernen_stellt_den_alten_stand_her(self):
        import hashlib, tempfile

        def inventar(w):
            r = {}
            for stamm, _u, namen in os.walk(w):
                for n in namen:
                    p = os.path.join(stamm, n)
                    r[os.path.relpath(p, w).replace(os.sep, "/")] =                         hashlib.sha256(open(p, "rb").read()).hexdigest()
            return r

        with tempfile.TemporaryDirectory() as basis:
            app0 = self._ordner(basis)
            vorher = inventar(str(app0))
            for name in (ap.MANIFEST_NAME, ap.LAUFZEIT_NAME,
                         "ampr_assets-a-lane00-vol00-000.pak",
                         "ampr_assets-a-lane01-vol00-001.pak"):
                (app0 / name).write_bytes(b"x" * 32)

            weg = ap.pack_entfernen(str(app0))
            self.assertEqual(weg, 4)
            self.assertEqual(inventar(str(app0)), vorher,
                             "Der Ordner ist nicht wieder der von vorher")

    def test_ohne_pack_wird_nichts_geloescht(self):
        import tempfile
        with tempfile.TemporaryDirectory() as basis:
            app0 = self._ordner(basis)
            meldungen = []
            self.assertEqual(
                ap.pack_entfernen(str(app0), melden=meldungen.append), 0)
            self.assertTrue((app0 / "eboot.bin").is_file())
            self.assertIn("ampr_pack.nichts_zu_entfernen", meldungen)

    def test_unlesbarer_ordner_wirft(self):
        """Lieber ein Fehler als ein stilles "nichts zu tun"."""
        with self.assertRaises(ap.PackFehler):
            ap.pack_entfernen("")

    def test_der_knopf_und_die_aktion_sind_da(self):
        haupt = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8")
        self.assertIn("ampr.btn_pack_remove", haupt, "Der Knopf fehlt")
        self.assertIn('action == "ampr_pack_remove"', haupt,
                      "Die Aktion wird nicht behandelt")
        self.assertIn('"ampr_pack_remove"', haupt)
        # Auch ueber die Kommandozeile erreichbar - sonst waere der Weg
        # nur im Fenster da und in keinem Ablauf.
        stelle = haupt.index("--ampr-action")
        self.assertIn("ampr_pack_remove", haupt[stelle:stelle + 400])


class RueckwegBleibtWegTests(unittest.TestCase):
    """Das Herausnehmen darf im selben Lauf nicht rueckgaengig gemacht werden.

    Am 08.09.2026 an einer echten Arbeitskopie gemessen: Aufgabe 7 mit
    ``ampr_pack_remove`` entfernte die sechs Packdateien und legte sie
    unmittelbar danach wieder an. Der Grund steckt in der Ablauffolge: Die
    Aktion setzt ``changed``, und der Block dahinter baut bei eingestellter
    Methode "Asset-Pack" ein Pack, wenn sich etwas geaendert hat. Beides
    zusammen hob sich auf.

    Sichtbar war davon nichts - das Protokoll meldete "Erfolgreich
    abgeschlossen", und im Ordner lagen weiterhin Manifest, Laufzeitdatei
    und vier Baender. Wer das Pack loswerden wollte, hatte es noch.
    """

    @classmethod
    def setUpClass(cls):
        cls.quelle = (Path(__file__).resolve().parent
                      / "PS5ImageConverter_Pro_FINAL_revised.py"
                      ).read_text(encoding="utf-8")

    def _packblock(self) -> str:
        """Der Block in Aufgabe 7, der das Pack baut."""
        stelle = self.quelle.index("if (changed and action != \"ampr_pack_remove\"")
        return self.quelle[stelle:stelle + 400]

    def test_die_aktion_ist_vom_packbau_ausgenommen(self):
        # Wirft KeyError/ValueError, wenn die Bedingung wieder fehlt.
        block = self._packblock()
        self.assertIn("AMPR_METHODE_ASSETPACK", block,
                      "Der gefundene Block ist nicht der Packbau.")

    def test_der_packbau_haengt_weiter_an_der_methode(self):
        """Anker: Ohne diese Bedingung packte Aufgabe 7 immer - dann waere
        die Ausnahme oben zwar da, aber sie schuetzte das Falsche.
        """
        block = self._packblock()
        self.assertIn("self._ampr_methode() == AMPR_METHODE_ASSETPACK", block)
        self.assertIn("_ampr_assetpakete_bauen", block)

    def test_die_uebrigen_aktionen_bleiben_drin(self):
        """Nur diese eine Aktion ist ausgenommen, nicht etwa jede."""
        block = self._packblock()
        for aktion in ("ampr_apply", "ampr_index", "ampr_restore"):
            with self.subTest(aktion=aktion):
                self.assertNotIn('action != "%s"' % aktion, block,
                                 "%s wurde mit ausgenommen - dann greift die "
                                 "neue Methode dort nicht mehr." % aktion)


class FassungsschreibweiseTests(unittest.TestCase):
    """Die Klapplisten-Beschriftung muss auch als --ampr-version taugen.

    Das Fenster zeigt "0.4.2.1 test-pack" - Fassung und Variante in einem
    Stueck -, und so steht es auch in den Einstellungen. Wer das ablas und
    in die Kommandozeile uebernahm, bekam bis v1.9.9 "Keine passende Datei
    im Versionsordner (Version 0.4.2.1 test-pack, Variante *)". Die Meldung
    deutete auf eine fehlende Fassung, dabei stimmte nur die Schreibweise
    nicht. Am 08.09.2026 bin ich beim Durchtesten selbst darauf
    hereingefallen und habe den Befund erst falsch erklaert.
    """

    @staticmethod
    def _spec(version="", variant=""):
        import argparse
        import PS5ImageConverter_Pro_FINAL_revised as APP
        args = argparse.Namespace(
            ampr_action="ampr_apply", ampr_store="", ampr_version=version,
            ampr_variant=variant, ampr_lib=[], ampr_source="",
            ampr_no_backup=False, ampr_no_index=False)
        return APP._build_ampr_automation(args)

    def test_zusammengesetzt_wird_getrennt(self):
        s = self._spec("0.4.2.1 test-pack")
        self.assertEqual("0.4.2.1", s.get("ampr_version"))
        self.assertEqual("test-pack", s.get("ampr_variant"))

    def test_variante_mit_leerzeichen_bleibt_ganz(self):
        """"no debug" ist eine Variante und keine zwei."""
        s = self._spec("0.2.7.6 no debug")
        self.assertEqual("0.2.7.6", s.get("ampr_version"))
        self.assertEqual("no debug", s.get("ampr_variant"))

    def test_getrennte_angabe_bleibt_wie_sie_war(self):
        s = self._spec("0.4.2.1", "test-pack")
        self.assertEqual("0.4.2.1", s.get("ampr_version"))
        self.assertEqual("test-pack", s.get("ampr_variant"))

    def test_ausdrueckliche_variante_sticht(self):
        s = self._spec("0.4.2.1 test-pack", "test-debug-pack")
        self.assertEqual("0.4.2.1", s.get("ampr_version"))
        self.assertEqual("test-debug-pack", s.get("ampr_variant"))

    def test_ohne_variante_bleibt_sie_offen(self):
        """Anker: Eine leere Variante darf nicht als "" durchgereicht werden -
        der Sucher nimmt dann die erste passende, und genau das ist gewollt.
        """
        s = self._spec("0.4.2.1")
        self.assertEqual("0.4.2.1", s.get("ampr_version"))
        self.assertIsNone(s.get("ampr_variant"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
