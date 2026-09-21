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
# Das Indexskript des Entwicklers - die Vorlage, an der sich der Index messen
# lassen muss (siehe test_ampr_assets.IndexWieBeimEntwicklerTests).
sys.path.insert(0, str(PROJEKT / "AMPR_PackTools-4.0"))

from ps5_validator.utils import ampr_assetpakete as ap  # noqa: E402


def _index_bauen(app0: Path) -> Path:
    """ampr_emu.index mit dem Skript des Entwicklers."""
    import build_ampr_index

    index = app0 / "ampr_emu.index"
    rc = build_ampr_index.build_index_local(app0, index, False)
    if rc != 0:
        raise AssertionError("build_ampr_index.py endete mit %d" % rc)
    return index


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


class ProfilErneuernTests(unittest.TestCase):
    """Ein eigenes Profil wird neu geschrieben, eines des Anwenders nie.

    Bis zum 17.09.2026 blieb jedes vorhandene Profil stehen. Ein
    abgebrochener Lauf liess das Profil im Ausgabeordner neben dem
    Spielordner zurueck (Ghost of Yotei, 12.09.2026), und alle spaeteren
    Laeufe packten mit diesem alten Stand weiter.
    """

    def test_altes_eigenes_profil_wird_ersetzt(self):
        import tempfile
        with tempfile.TemporaryDirectory() as basis:
            pfad = os.path.join(basis, "ampr_pack.toml")
            with open(pfad, "w", encoding="utf-8") as datei:
                datei.write(ap.PROFIL_KENNZEILE + " - alter Stand\n[pack]\n")
            ap.profil_schreiben(pfad)
            with open(pfad, encoding="utf-8") as datei:
                self.assertEqual(datei.read(), ap.standardprofil_text())

    def test_profil_des_anwenders_bleibt(self):
        import tempfile
        with tempfile.TemporaryDirectory() as basis:
            pfad = os.path.join(basis, "ampr_pack.toml")
            eigen = "# aus Mitschnitten erzeugt\n[pack]\nworkers = 3\n"
            with open(pfad, "w", encoding="utf-8") as datei:
                datei.write(eigen)
            ap.profil_schreiben(pfad)
            with open(pfad, encoding="utf-8") as datei:
                self.assertEqual(datei.read(), eigen)
            self.assertFalse(ap.profil_ist_eigenes(pfad))

    def test_das_erzeugte_profil_gilt_als_eigenes(self):
        """Gegenprobe zur Erkennung: sonst wuerde nie etwas ersetzt."""
        import tempfile
        with tempfile.TemporaryDirectory() as basis:
            pfad = ap.profil_schreiben(os.path.join(basis, "neu.toml"))
            self.assertTrue(ap.profil_ist_eigenes(pfad))


class LoseDateienTests(unittest.TestCase):
    """Abschnitt 5: "every listed file remains in /app0"."""

    def test_fehlende_lose_datei_wird_gemeldet(self):
        import tempfile
        with tempfile.TemporaryDirectory() as app0:
            os.makedirs(os.path.join(app0, "sce_sys"))
            with open(os.path.join(app0, "sce_sys", "param.json"), "wb") as fh:
                fh.write(b"{}")
            zeilen = [
                {"path": "/app0/sce_sys/param.json", "packed": False},
                {"path": "/app0/eboot.bin", "packed": False},
                {"path": "/app0/daten/weg.dat", "packed": True},
            ]
            self.assertEqual(ap.lose_fehlend(zeilen, app0), ["/app0/eboot.bin"],
                             "Nur die fehlende lose Datei zaehlt - gepackte "
                             "duerfen fehlen, sie liegen im Band.")


class SpeicherblockTests(unittest.TestCase):
    """Die Speicherrechnung aus Abschnitt 8 der Anleitung des Entwicklers."""

    MIB = 1024 * 1024

    def _laufzeit(self, entpackt_mib: int, physisch_mib: int) -> dict:
        return {"decoded_cache_bytes": entpackt_mib * self.MIB,
                "physical_cache_bytes": physisch_mib * self.MIB,
                "workers": 4, "latency_reserve_workers": 1}

    def test_beispiel_aus_der_anleitung(self):
        """7.439.926 Bloecke: 85,16 MiB Manifest, 0,03 MiB Index, 96/64 MiB
        Caches, vier Arbeiter - "about 345.19 MiB, leaving 38.81 MiB"."""
        bedarf = ap.speicherbedarf(int(85.16 * self.MIB), int(0.03 * self.MIB),
                                   self._laufzeit(96, 64))
        self.assertAlmostEqual(bedarf / self.MIB, 345.19, places=2)
        self.assertAlmostEqual((ap.POOL_BYTES - bedarf) / self.MIB, 38.81, places=2)
        self.assertEqual(
            ap.laufzeit_einpassen(int(85.16 * self.MIB), int(0.03 * self.MIB),
                                  self._laufzeit(96, 64)),
            self._laufzeit(96, 64), "Passt mit Luft - nichts zu aendern")

    def test_zu_wenig_luft_verkleinert_den_entpackten_cache(self):
        """120 MiB: "totals about 369.19 MiB and leaves 14.81 MiB" - unter den
        16 MiB Luft, also wird der entpackte Cache kleiner, im 16-KiB-Raster."""
        manifest, index = int(85.16 * self.MIB), int(0.03 * self.MIB)
        passend = ap.laufzeit_einpassen(manifest, index, self._laufzeit(120, 64))
        self.assertIsNotNone(passend)
        self.assertLess(passend["decoded_cache_bytes"], 120 * self.MIB)
        self.assertEqual(passend["physical_cache_bytes"], 64 * self.MIB)
        self.assertEqual(passend["decoded_cache_bytes"] % ap.CACHE_RASTER, 0)
        self.assertLessEqual(ap.speicherbedarf(manifest, index, passend),
                             ap.POOL_BYTES - ap.POOL_LUFT)

    def test_ohne_platz_fuer_das_manifest_kein_ergebnis(self):
        self.assertIsNone(ap.laufzeit_einpassen(300 * self.MIB, 12 * self.MIB,
                                                self._laufzeit(96, 32)))

    def test_ohne_laufzeitdatei_gelten_die_vorgaben(self):
        """Keine .runtime: die einkompilierten 128/32 MiB zaehlen."""
        self.assertEqual(ap.laufzeit_einpassen(10 * self.MIB, 1 * self.MIB, {}),
                         ap.LAUFZEIT_VORGABE)


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
        # Gut komprimierbar - sonst bliebe ein falsch nicht ausgeschlossenes
        # Stueck ohnehin lose, und der Test saehe den Fehler nicht.
        fuellung = b"PACKBAR " * 4096
        (app0 / "fakelib").mkdir()
        (app0 / "fakelib" / "FW7").write_bytes(fuellung)
        (app0 / "fakelib" / "libSceAmpr.sprx.orig").write_bytes(fuellung)
        for name in ("apr_emu.log", "ampr_emu.log", "playgo_stub.dat"):
            (app0 / name).write_bytes(fuellung)
        # Seit dem 20.09.2026: Was die Systemschicht selbst liest. PlayGo
        # holt playgo.pgm und die pgc_*_dummy_file am AMPR EMU vorbei; die
        # veroeffentlichten Profile fuehren sie unter "MUST REMAIN LOOSE".
        (app0 / "cache_ps5").mkdir()
        for name in ("playgo.pgm", "game.sprig.packman", "pgc_00_dummy_file"):
            (app0 / "cache_ps5" / name).write_bytes(fuellung)
        # Filme - lose in jedem echten Profil. Einmal in der Wurzel und
        # einmal tief verschachtelt (so liegt es bei FF7 Rebirth).
        (app0 / "movies").mkdir()
        (app0 / "movies" / "intro.mp4").write_bytes(fuellung)
        (app0 / "end" / "content" / "movie").mkdir(parents=True)
        (app0 / "end" / "content" / "movie" / "vorspann.mp4").write_bytes(fuellung)
        return app0

    def test_systemdateien_bleiben_lose(self):
        import tempfile

        with tempfile.TemporaryDirectory(prefix="ampr_pack_test_") as basis:
            wurzel = Path(basis)
            app0 = self._baum(wurzel)
            index = _index_bauen(app0)

            raus = wurzel / "packed"
            profil = ap.profil_schreiben(str(wurzel / "profil.toml"), arbeiter=2)
            ergebnis = ap.packen(str(app0), str(index), str(raus), profil)

            lose = set(ergebnis.get("loose_paths") or [])
            for pflicht in ("eboot.bin", "libSceTest.sprx",
                            "sce_sys/param.sfo", "sce_module/libc.prx"):
                self.assertIn(pflicht, lose,
                              "%s wurde gepackt - das Spiel startet dann nicht"
                              % pflicht)
            # Seit dem 17.09.2026: Bibliotheksordner (liest ShadowMount+ am
            # AMPR EMU vorbei) samt Markierung und Sicherung, die
            # Laufzeitprotokolle und die PlayGo-Einstellung. apr_emu.log in der
            # Wurzel nimmt schon der Index nicht auf - geprueft wird deshalb
            # ueber "list --json", was wirklich gepackt ist.
            gepackt = {str(zeile.get("path")) for zeile in
                       ap.liste(str(raus / ap.MANIFEST_NAME)) if zeile.get("packed")}
            self.assertIn("/app0/assets/t0.dat", gepackt,
                          "Die Liste nennt die Nutzdaten nicht - dann misst "
                          "die Pruefung darunter nichts.")
            for pflicht in ("fakelib/FW7", "fakelib/libSceAmpr.sprx.orig",
                            "apr_emu.log", "ampr_emu.log", "playgo_stub.dat",
                            # Nachgetragen am 20.09.2026, nachdem Ghost of
                            # Yotei, Assassin's Creed Shadows und Rise of the
                            # Ronin mit Asset-Pack nicht liefen: Diese Dateien
                            # liest die Systemschicht, nicht der Emulator.
                            "cache_ps5/playgo.pgm",
                            "cache_ps5/game.sprig.packman",
                            "cache_ps5/pgc_00_dummy_file",
                            "movies/intro.mp4",
                            "end/content/movie/vorspann.mp4"):
                self.assertNotIn("/app0/" + pflicht, gepackt,
                                 "%s liegt im Band" % pflicht)

            # Die Nutzdaten sollen sehr wohl im Band liegen, sonst haette
            # die Ausschlussliste zu weit gegriffen.
            for datei in ("assets/t0.dat", "assets/t3.dat"):
                self.assertNotIn(datei, lose,
                                 "%s haette gepackt werden sollen" % datei)

            # Und die Baender muessen den Inhalt Byte fuer Byte tragen.
            ap.pruefen(str(raus / ap.MANIFEST_NAME), app0=str(app0))

    def test_uebernahme_bringt_einen_pruefbaren_satz(self):
        """Der Satz im Spielordner muss fuer sich allein pruefbar sein.

        Bis zum 17.09.2026 blieb die ``.crc`` im Ausgabeordner - beim Bau
        eines Abbilds im Temp-Verzeichnis, das danach geloescht wurde. Die
        Baender im Abbild liessen sich damit nie wieder pruefen oder
        auspacken. Geprueft wird deshalb nicht die Dateiliste, sondern ob
        ``verify --root`` gegen den Satz **im Spielordner** durchlaeuft.
        """
        import tempfile

        with tempfile.TemporaryDirectory(prefix="ampr_pack_test_") as basis:
            wurzel = Path(basis)
            app0 = self._baum(wurzel)
            index = _index_bauen(app0)

            raus = wurzel / "packed"
            profil = ap.profil_schreiben(str(wurzel / "profil.toml"))
            ap.packen(str(app0), str(index), str(raus), profil)
            baender = ap.bandnamen(ap.uebersicht(str(raus / ap.MANIFEST_NAME)))
            self.assertTrue(baender, "Das Manifest nennt keine Baender")
            ap.bestand_uebernehmen(str(raus), str(app0), baender=baender)

            im_spiel = set(os.listdir(app0))
            for name in (ap.MANIFEST_NAME, ap.LAUFZEIT_NAME, ap.PRUEFSUMMEN_NAME,
                         *baender):
                self.assertIn(name, im_spiel)
            # Der Ausgabeordner ist weg - geprueft wird allein der Satz im Spiel.
            ap.bestand_aufraeumen(str(raus), baender, ganz=True)
            self.assertFalse(raus.exists())
            ap.pruefen(str(app0 / ap.MANIFEST_NAME), app0=str(app0))

    def test_nur_die_genannten_baender_gehen_mit(self):
        """Ein liegen gebliebenes Band eines frueheren Laufs bleibt draussen."""
        import tempfile

        with tempfile.TemporaryDirectory(prefix="ampr_pack_test_") as basis:
            wurzel = Path(basis)
            app0 = self._baum(wurzel)
            index = _index_bauen(app0)
            raus = wurzel / "packed"
            profil = ap.profil_schreiben(str(wurzel / "profil.toml"))
            ap.packen(str(app0), str(index), str(raus), profil)
            baender = ap.bandnamen(ap.uebersicht(str(raus / ap.MANIFEST_NAME)))
            (raus / "ampr_assets-alt-lane09-vol00-099.pak").write_bytes(b"alt")

            ap.bestand_uebernehmen(str(raus), str(app0), baender=baender)
            self.assertNotIn("ampr_assets-alt-lane09-vol00-099.pak", os.listdir(app0))

            # Gegenrichtung: Fehlt ein genanntes Band, landet nichts vom Satz
            # im Ziel - auch nicht Manifest und Laufzeitdatei.
            (raus / baender[0]).unlink()
            leer = wurzel / "leer"
            leer.mkdir()
            with self.assertRaises(ap.PackFehler):
                ap.bestand_uebernehmen(str(raus), str(leer), baender=baender)
            self.assertEqual([], os.listdir(leer))


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
        """Ohne diesen Aufruf gaebe es die vierte Stufe wieder nicht.

        Ueber den Syntaxbaum der Methode, nicht ueber die ersten 6000 Zeichen
        ab ihrem Namen: Die Methode wuchs am 17.09.2026 darueber hinaus, und
        der Ausschnitt haette die Uebernahme nicht mehr enthalten.
        """
        import ast
        haupt = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8")
        knoten = next(k for k in ast.walk(ast.parse(haupt))
                      if isinstance(k, ast.FunctionDef)
                      and k.name == "_ampr_assetpakete_bauen")
        block = ast.unparse(knoten)
        # Die Uebernahme in den Spielordner muss NACH allen Pruefungen der
        # Bereitschaftsliste stehen - sonst laege ein unbrauchbarer Bestand
        # schon im Spiel.
        # Seit dem 20.09.2026 wird die Dateiliste einmal geholt und zweimal
        # befragt: erst auf Systemdateien im Band, dann auf fehlende lose
        # Dateien. Beides vor der Uebernahme.
        reihenfolge = ["ampr_assetpakete.pruefen(", "ampr_assetpakete.uebersicht(",
                       "grenzen_ueberschritten(", "ampr_assetpakete.liste(",
                       "systemdateien_im_pack(", "lose_fehlend(",
                       "_ampr_pack_speicher_einpassen(", "bestand_uebernehmen(",
                       "_ampr_pack_konsolenhinweis("]
        stellen = [block.index(teil) for teil in reihenfolge]
        self.assertEqual(stellen, sorted(stellen),
                         "Reihenfolge verletzt: %s" % reihenfolge)



class FilmordnerTests(unittest.TestCase):
    """Filmordner kommen aus dem Baum, nicht aus einer festen Liste.

    Das Werkzeug vergleicht mit ``fnmatch.fnmatchcase``, also genau nach
    Schreibung. Ein festes ``movies/**`` traf deshalb
    ``Media/StreamingAssets/Movies/`` nicht - am 20.09.2026 an "Wer wird
    Millionaer" gemessen: 17 von 17 Filmen landeten im Band, obwohl die
    Ausschlussliste "movies" kannte.
    """

    def _baum(self, wurzel: Path, ordner: list[str]) -> None:
        for rel in ordner:
            (wurzel / rel).mkdir(parents=True, exist_ok=True)
            (wurzel / rel / "film.mp4").write_bytes(b"x" * 16)

    def test_schreibung_kommt_aus_dem_dateisystem(self):
        import tempfile

        with tempfile.TemporaryDirectory(prefix="ampr_film_") as basis:
            wurzel = Path(basis)
            self._baum(wurzel, ["Media/StreamingAssets/Movies",
                                "data/prein/video",
                                "end/content/movie",
                                "assets/Textures"])
            muster = ap.filmordner_muster(str(wurzel))
            self.assertIn("Media/StreamingAssets/Movies/**", muster)
            self.assertIn("data/prein/video/**", muster)
            self.assertIn("end/content/movie/**", muster)
            self.assertNotIn("assets/Textures/**", muster)

    def test_ohne_filmordner_bleibt_die_liste_leer(self):
        import tempfile

        with tempfile.TemporaryDirectory(prefix="ampr_film_") as basis:
            self._baum(Path(basis), ["assets/daten"])
            self.assertEqual(ap.filmordner_muster(basis), ())

    def test_unlesbarer_ordner_wirft_nicht(self):
        self.assertEqual(ap.filmordner_muster(r"Z:\gibt-es-nicht"), ())

    def test_die_muster_stehen_im_profil(self):
        text = ap.standardprofil_text(2, ("Media/StreamingAssets/Movies/**",))
        daten = tomllib.loads(text)
        self.assertIn("Media/StreamingAssets/Movies/**",
                      daten["rule"][0]["exclude"])
        # Die festen Muster duerfen dabei nicht verlorengehen.
        self.assertIn("eboot.bin", daten["rule"][0]["exclude"])

    def test_systemdateien_mit_abweichender_schreibung(self):
        """``PlayGo.pgm`` muss im Profil stehen, nicht erst am Riegel haengen."""
        import tempfile

        with tempfile.TemporaryDirectory(prefix="ampr_sys_") as basis:
            wurzel = Path(basis)
            (wurzel / "cache_ps5").mkdir()
            for name in ("PlayGo.pgm", "Game.Sprig.PACKMAN",
                         "PGC_Game_Dummy_File", "textur.dat"):
                (wurzel / "cache_ps5" / name).write_bytes(b"x" * 16)
            muster = ap.systemdateien_muster(str(wurzel))
            self.assertIn("cache_ps5/PlayGo.pgm", muster)
            self.assertIn("cache_ps5/Game.Sprig.PACKMAN", muster)
            self.assertIn("cache_ps5/PGC_Game_Dummy_File", muster)
            self.assertNotIn("cache_ps5/textur.dat", muster)

    def test_videos_im_pack_werden_gemeldet(self):
        gemeldet = ap.videos_im_pack([
            {"path": "/app0/Media/StreamingAssets/Movies/a.mp4", "packed": True},
            {"path": "/app0/d/movie/b.bk2", "packed": True},
            {"path": "/app0/assets/t.dat", "packed": True},
            {"path": "/app0/movies/c.mp4", "packed": False},
        ])
        self.assertEqual(gemeldet, ["/app0/Media/StreamingAssets/Movies/a.mp4",
                                    "/app0/d/movie/b.bk2"])

    def test_video_meldung_ist_kein_abbruch(self):
        """Belegt ist nur die Praxis der Profile, nicht ein Schaden.

        Deshalb steht der Aufruf im Bauweg **nicht** vor einem ``return
        False`` - anders als bei den Systemdateien.
        """
        import ast

        haupt = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8")
        knoten = next(k for k in ast.walk(ast.parse(haupt))
                      if isinstance(k, ast.FunctionDef)
                      and k.name == "_ampr_assetpakete_bauen")
        for zweig in ast.walk(knoten):
            if not isinstance(zweig, ast.If):
                continue
            quelle = ast.unparse(zweig.test)
            if "videos" not in quelle:
                continue
            rueckgaben = [k for k in ast.walk(zweig)
                          if isinstance(k, ast.Return)]
            self.assertEqual(rueckgaben, [],
                             "Die Videowarnung bricht den Bau ab - sie soll nur melden")
            break
        else:
            self.fail("Kein Zweig, der videos prueft")


class DirektleserTests(unittest.TestCase):
    """Engines, die ihre Daten am Emulator vorbei lesen.

    Am 20.09.2026 an der Konsole gemessen ("Wer wird Millionaer", ohne
    Originale gebaut, Debug-Bau des AMPR EMU 0.4.2.1): Fuer fuenf Dateien
    der Unity-Laufzeit meldete der Emulator ``io.hook.error ... No such
    file or directory``, im ganzen Mitschnitt stand keine einzige
    ``apr.pack``-Zeile, und das Spiel beendete sich nach dem Start. Mit
    denselben Baendern **und** den Originalen daneben lief es durch.
    """

    def _unity(self, wurzel: Path, datenordner: str) -> None:
        (wurzel / datenordner).mkdir(parents=True, exist_ok=True)
        for name in ("data.unity3d", "globalgamemanagers",
                     "ScriptingAssemblies.json", "RuntimeInitializeOnLoads.json"):
            (wurzel / datenordner / name).write_bytes(b"x" * 16)
        (wurzel / datenordner / "Metadata").mkdir(exist_ok=True)
        (wurzel / datenordner / "Metadata" / "global-metadata.dat").write_bytes(b"x")

    def test_unity_wird_erkannt(self):
        import tempfile

        with tempfile.TemporaryDirectory(prefix="ampr_dl_") as basis:
            wurzel = Path(basis)
            self._unity(wurzel, "Media")
            (wurzel / "eboot.bin").write_bytes(b"x")
            engine, merkmale = ap.direktleser_merkmale(str(wurzel))
            self.assertEqual(engine, "Unity")
            self.assertIn("Media/data.unity3d", merkmale)
            self.assertIn("Media/Metadata/global-metadata.dat", merkmale)
            self.assertEqual(len(merkmale), 5)

    def test_der_datenordner_darf_heissen_wie_er_will(self):
        """Unity legt ihn je nach Projekt anders an - gemessen unter Media/."""
        import tempfile

        for ordner in ("Media", "Spiel_Data", "Data", "tief/drin/Game_Data"):
            with tempfile.TemporaryDirectory(prefix="ampr_dl_") as basis:
                self._unity(Path(basis), ordner)
                engine, merkmale = ap.direktleser_merkmale(basis)
                self.assertEqual(engine, "Unity", ordner)
                self.assertIn(ordner + "/data.unity3d", merkmale)

    def test_ein_titel_ohne_engine_bleibt_leer(self):
        import tempfile

        with tempfile.TemporaryDirectory(prefix="ampr_dl_") as basis:
            wurzel = Path(basis)
            (wurzel / "daten").mkdir()
            (wurzel / "daten" / "karte0.dat").write_bytes(b"x" * 64)
            (wurzel / "eboot.bin").write_bytes(b"x")
            self.assertEqual(ap.direktleser_merkmale(basis), ("", ()))

    def test_unlesbarer_ordner_wirft_nicht(self):
        self.assertEqual(ap.direktleser_merkmale(r"Z:\gibt-es-nicht"), ("", ()))

    def test_der_hauptbestand_wird_nicht_ausgeschlossen(self):
        """Die Folge ist "Originale bleiben", nicht "alles lose".

        ``data.unity3d`` traegt praktisch das ganze Spiel. Stuende es in
        der Ausschlussliste, bliebe fast alles lose und das Pack waere
        sinnlos - deshalb entscheidet der Riegel beim Entfernen, nicht das
        Profil.
        """
        for name in ("data.unity3d", "globalgamemanagers"):
            self.assertNotIn(name, ap.NIE_PACKEN, name)
            self.assertNotIn(name, ap.SYSTEMDATEIEN, name)
        # Die Metadaten dagegen sind klein und muessen lose bleiben.
        self.assertIn("global-metadata.dat", ap.NIE_PACKEN)


class DirektleserRiegelTests(unittest.TestCase):
    """Mit dem Programmprofil bleiben die Originale - immer.

    Der dritte Riegel - nach den Systemdateien im Band und den fehlenden
    losen Dateien. Er greift **vor** dem Entfernen, denn danach ist nichts
    mehr zu retten.

    **Umgedreht am 21.09.2026.** Bis dahin genuegte es, dass ``DIREKTLESER``
    keine Engine fand. Die Tabelle kennt fuenf Unity-Dateinamen, und
    "Arkanoid - Eternal Battle" ist keine davon - ein eigenes Geruest mit
    FMOD-Banks und .gnf-Atlanten. Der Riegel liess die Originale fallen, das
    Abbild stuerzte an der Konsole ab, dieselbe Quelle mit Originalen lief.
    Zwei von zwei Versuchen ohne Originale endeten so (vorher Ghost of
    Yotei), und **kein** Titel hat je gezeigt, dass Baender gelesen werden.

    Eine Aufzaehlung von Engines kann das nicht sichern - sie muesste jede
    kuenftige schon kennen, und der Fehlschlag trifft den Anwender erst an
    der Konsole.
    """

    def _fenster(self):
        import PS5ImageConverter_Pro_FINAL_revised as APP

        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._protokoll = []
        gui._append_to_log = gui._protokoll.append
        gui._t = lambda schluessel, **werte: (
            schluessel if not werte else "%s %s" % (schluessel, sorted(werte.values())))
        return gui

    def _unity_ordner(self, basis: str) -> str:
        wurzel = Path(basis)
        (wurzel / "Media" / "Metadata").mkdir(parents=True)
        (wurzel / "Media" / "data.unity3d").write_bytes(b"x" * 32)
        (wurzel / "Media" / "Metadata" / "global-metadata.dat").write_bytes(b"x")
        (wurzel / "eboot.bin").write_bytes(b"x")
        return str(wurzel)

    def test_unity_haelt_die_originale_fest(self):
        import tempfile

        with tempfile.TemporaryDirectory(prefix="ampr_riegel_") as basis:
            gui = self._fenster()
            darf = gui._ampr_direktleser_riegel(self._unity_ordner(basis), True)
            self.assertFalse(darf, "Bei Unity darf nicht entfernt werden.")
            text = "\n".join(gui._protokoll)
            self.assertIn("ampr_pack.direktleser_erkannt", text)
            self.assertIn("Unity", text)
            self.assertIn("ampr_pack.direktleser_riegel", text)
            self.assertIn("ampr_pack.direktleser_ausweg", text)
            self.assertIn("Media/data.unity3d", text,
                          "Die gefundenen Dateien gehoeren in die Meldung.")

    def test_ein_eigenes_profil_entscheidet_der_anwender(self):
        """Wer aus Mitschnitten packt, weiss, was der Titel ueber APR liest."""
        import tempfile

        with tempfile.TemporaryDirectory(prefix="ampr_riegel_") as basis:
            gui = self._fenster()
            self.assertTrue(
                gui._ampr_direktleser_riegel(self._unity_ordner(basis), False))
            self.assertEqual(gui._protokoll, [])

    def test_ohne_erkannte_engine_bleiben_die_originale_trotzdem(self):
        """Der Fall Arkanoid: nicht erkannt, und doch ein Direktleser.

        Bis zum 21.09.2026 gab der Riegel hier frei
        (``test_ohne_merkmal_laeuft_alles_wie_bisher``) - und genau so ist
        ein Abbild entstanden, das an der Konsole abstuerzte.
        """
        import tempfile

        with tempfile.TemporaryDirectory(prefix="ampr_riegel_") as basis:
            (Path(basis) / "daten").mkdir()
            (Path(basis) / "daten" / "karte0.dat").write_bytes(b"x" * 64)
            gui = self._fenster()
            self.assertFalse(
                gui._ampr_direktleser_riegel(basis, True),
                "Ohne Mitschnitt darf nichts entfernt werden - eine nicht "
                "erkannte Engine ist kein Beweis, dass sie ueber APR liest.")
            text = "\n".join(gui._protokoll)
            self.assertIn("ampr_pack.riegel_ohne_erkennung", text)
            self.assertIn("ampr_pack.direktleser_ausweg", text,
                          "Der Ausweg (eigenes Packprofil) muss dastehen.")
            self.assertNotIn(
                "ampr_pack.direktleser_erkannt", text,
                "Es wurde keine Engine erkannt - dann darf auch keine "
                "genannt werden.")

    def test_die_erkennung_bleibt_als_auskunft(self):
        """Bei einer bekannten Engine soll die Meldung den Namen nennen.

        Der Riegel sperrt jetzt ohnehin - aber "weil es Unity ist" hilft dem
        Anwender mehr als "weil kein Mitschnitt vorliegt".
        """
        import tempfile

        with tempfile.TemporaryDirectory(prefix="ampr_riegel_") as basis:
            gui = self._fenster()
            gui._ampr_direktleser_riegel(self._unity_ordner(basis), True)
            text = "\n".join(gui._protokoll)
            self.assertIn("Unity", text)
            self.assertNotIn(
                "ampr_pack.riegel_ohne_erkennung", text,
                "Bei erkannter Engine gehoert die konkrete Begruendung hin, "
                "nicht die allgemeine.")

    def test_nur_ein_eigenes_profil_gibt_frei(self):
        """Die einzige Tuer, die offen bleibt - an beiden Faellen geprueft."""
        import tempfile

        for name, aufbauen in (("Unity erkannt", True), ("nicht erkannt", False)):
            with self.subTest(fall=name):
                with tempfile.TemporaryDirectory(prefix="ampr_riegel_") as basis:
                    if aufbauen:
                        self._unity_ordner(basis)
                    else:
                        (Path(basis) / "x.dat").write_bytes(b"x")
                    gui = self._fenster()
                    self.assertTrue(
                        gui._ampr_direktleser_riegel(basis, False),
                        "Mit einem Profil aus Mitschnitten entscheidet der "
                        "Anwender.")
                    self.assertEqual(gui._protokoll, [])

    def test_der_riegel_haengt_wirklich_vor_dem_entfernen(self):
        """Eine Pruefung, die nur der Test ruft, schuetzt keine Datei."""
        import ast

        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8")
        baum = ast.parse(quelle)
        methode = next(k for k in ast.walk(baum)
                       if isinstance(k, ast.FunctionDef)
                       and k.name == "_ampr_assetpakete_bauen")
        zeilen = {}
        for knoten in ast.walk(methode):
            if isinstance(knoten, ast.Attribute):
                zeilen.setdefault(knoten.attr, []).append(knoten.lineno)
        self.assertIn("_ampr_direktleser_riegel", zeilen,
                      "Der Riegel wird im Baulauf gar nicht gefragt.")
        self.assertIn("_ampr_originale_entfernen", zeilen)
        self.assertLess(min(zeilen["_ampr_direktleser_riegel"]),
                        min(zeilen["_ampr_originale_entfernen"]),
                        "Gefragt wird erst nach dem Entfernen - zu spaet.")

    def test_der_hinweis_ohne_mitschnitte_steht_im_baulauf(self):
        """Wer ohne Originale baut, soll den Vorbehalt vorher lesen."""
        import ast

        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8")
        baum = ast.parse(quelle)
        methode = next(k for k in ast.walk(baum)
                       if isinstance(k, ast.FunctionDef)
                       and k.name == "_ampr_assetpakete_bauen")
        texte = [n.value for n in ast.walk(methode)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        self.assertIn("ampr_pack.originale_weglassen_risiko", texte)

    def test_das_handbuch_erklaert_den_fall(self):
        handbuch = (PROJEKT / "BENUTZERHANDBUCH.html").read_text(encoding="utf-8")
        for stelle in ("data.unity3d", "global-metadata.dat", "Unity",
                       "_ampr_pack.toml"):
            self.assertIn(stelle, handbuch, "%s fehlt im Handbuch" % stelle)


class EigenesProfilTests(unittest.TestCase):
    """Der Weg am Riegel vorbei: ein Profil aus Konsolen-Mitschnitten.

    Gepackt wird in einem Ordner neben der Arbeitskopie, und die liegt in
    einem frisch erzeugten Temp-Ordner - dort kann niemand vorher etwas
    ablegen. Ohne diese Uebernahme waere die Ausnahme fuer eigene Profile
    also unerreichbar, und der Riegel haette kein Ventil.
    """

    def _fenster(self, quelle: str):
        import PS5ImageConverter_Pro_FINAL_revised as APP

        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._protokoll = []
        gui._append_to_log = gui._protokoll.append
        gui._t = lambda schluessel, **werte: (
            schluessel if not werte else "%s %s" % (schluessel, sorted(map(str, werte.values()))))
        gui._ampr_quelle_original = quelle
        return gui

    MITSCHNITT = (
        '[[rule]]\nmatch = ["daten/**"]\naction = "pack"\n'
        'compression = "lz4"\n')

    def test_ein_profil_daneben_wird_genommen(self):
        import tempfile

        with tempfile.TemporaryDirectory(prefix="ampr_prof_") as basis:
            spiel = Path(basis) / "Mein Spiel"
            spiel.mkdir()
            (Path(basis) / "Mein Spiel_ampr_pack.toml").write_text(
                self.MITSCHNITT, encoding="utf-8")
            ausgabe = Path(basis) / "Mein Spiel_ampr_pack"

            gui = self._fenster(str(spiel))
            ziel = gui._ampr_eigenes_profil_uebernehmen(str(ausgabe))
            self.assertTrue(ziel)
            self.assertTrue(os.path.isfile(ziel))
            self.assertIn("ampr_pack.eigenes_profil_uebernommen",
                          "\n".join(gui._protokoll))
            # Und es gilt ab jetzt als Profil des Anwenders - der Baulauf
            # schreibt es damit nicht um.
            self.assertFalse(ap.profil_ist_eigenes(ziel))
            unveraendert = Path(ziel).read_text(encoding="utf-8")
            ap.profil_schreiben(ziel, 2, str(spiel))
            self.assertEqual(Path(ziel).read_text(encoding="utf-8"), unveraendert)

    def test_eine_kopie_unseres_profils_zaehlt_nicht(self):
        """Sonst haette der Riegel ein Ventil, das nichts weiss."""
        import tempfile

        with tempfile.TemporaryDirectory(prefix="ampr_prof_") as basis:
            spiel = Path(basis) / "Mein Spiel"
            spiel.mkdir()
            (Path(basis) / "Mein Spiel_ampr_pack.toml").write_text(
                ap.standardprofil_text(2), encoding="utf-8")
            gui = self._fenster(str(spiel))
            self.assertEqual(
                gui._ampr_eigenes_profil_uebernehmen(str(Path(basis) / "aus")), "")
            self.assertIn("ampr_pack.eigenes_profil_ist_unseres",
                          "\n".join(gui._protokoll))

    def test_ohne_datei_geschieht_nichts(self):
        import tempfile

        with tempfile.TemporaryDirectory(prefix="ampr_prof_") as basis:
            spiel = Path(basis) / "Mein Spiel"
            spiel.mkdir()
            gui = self._fenster(str(spiel))
            self.assertEqual(
                gui._ampr_eigenes_profil_uebernehmen(str(Path(basis) / "aus")), "")
            self.assertEqual(gui._protokoll, [])

    def test_ohne_gemerkte_quelle_geschieht_nichts(self):
        """Aus einem Abbild entpackt - dann gibt es keinen Ordner daneben."""
        gui = self._fenster("")
        self.assertEqual(gui._ampr_eigenes_profil_uebernehmen("egal"), "")
        self.assertEqual(gui._protokoll, [])

    def test_die_uebernahme_steht_vor_dem_profilschreiben(self):
        import ast

        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8")
        baum = ast.parse(quelle)
        methode = next(k for k in ast.walk(baum)
                       if isinstance(k, ast.FunctionDef)
                       and k.name == "_ampr_assetpakete_bauen")
        zeilen = {}
        for knoten in ast.walk(methode):
            if isinstance(knoten, ast.Attribute):
                zeilen.setdefault(knoten.attr, []).append(knoten.lineno)
        self.assertIn("_ampr_eigenes_profil_uebernehmen", zeilen,
                      "Ein eigenes Profil wird nie gesucht.")
        self.assertLess(min(zeilen["_ampr_eigenes_profil_uebernehmen"]),
                        min(zeilen["profil_schreiben"]),
                        "Gesucht wird erst nach dem Schreiben - zu spaet.")

    def test_die_quelle_wird_vor_der_arbeitskopie_gemerkt(self):
        """Danach ist es ein Temp-Ordner - daneben liegt nie ein Profil."""
        import ast

        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8")
        baum = ast.parse(quelle)
        methode = next(k for k in ast.walk(baum)
                       if isinstance(k, ast.FunctionDef)
                       and k.name == "_integration_anwenden")
        merken = [n.lineno for n in ast.walk(methode)
                  if isinstance(n, ast.Attribute)
                  and n.attr == "_ampr_quelle_original"]
        kopie = [n.lineno for n in ast.walk(methode)
                 if isinstance(n, ast.Attribute)
                 and n.attr == "_integration_arbeitskopie"]
        self.assertTrue(merken, "_integration_anwenden merkt die Quelle nicht.")
        self.assertTrue(kopie)
        self.assertLess(min(merken), min(kopie))

    def test_jeder_lauf_faengt_ohne_alte_quelle_an(self):
        """Sonst zieht Lauf 2 das Profil aus Lauf 1 herein."""
        import ast

        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8")
        baum = ast.parse(quelle)
        methode = next(k for k in ast.walk(baum)
                       if isinstance(k, ast.FunctionDef)
                       and k.name == "_run_engine_thread")
        geleert = [z for z in ast.walk(methode)
                   if isinstance(z, ast.Assign)
                   and any(isinstance(t, ast.Attribute)
                           and t.attr == "_ampr_quelle_original" for t in z.targets)
                   and isinstance(z.value, ast.Constant) and z.value.value == ""]
        self.assertTrue(geleert,
                        "_run_engine_thread leert _ampr_quelle_original nicht.")


class KonsolenhinweisTests(unittest.TestCase):
    """Was die Konsole braucht, sagt das Programm beim Bauen.

    Auf Wunsch des Nutzers (20.09.2026): Einstellungen von ShadowMount+ und
    der PlayGo-Stub gehoeren dorthin, wo das Abbild entsteht - und ins
    Handbuch. Wer erst beim nicht startenden Spiel davon erfaehrt, hat
    Stunden Bauzeit umsonst aufgewendet.
    """

    def _fenster(self, merkmal: str = ""):
        import PS5ImageConverter_Pro_FINAL_revised as APP

        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._protokoll = []
        gui._append_to_log = gui._protokoll.append
        gui._t = lambda schluessel, **werte: (
            schluessel if not werte else "%s %s" % (schluessel, sorted(werte.values())))
        gui._titel_nutzt_playgo = classmethod(lambda _cls, _o: merkmal).__get__(gui)
        return gui

    def test_beide_einstellungen_werden_genannt(self):
        gui = self._fenster()
        gui._ampr_pack_konsolenhinweis("egal")
        text = "\n".join(gui._protokoll)
        self.assertIn("ampr_pack.konsole_titel", text)
        self.assertIn("ampr_pack.konsole_fakelib", text)
        self.assertIn("ampr_pack.konsole_global", text)

    def test_playgo_nur_wenn_der_titel_es_erklaert(self):
        ohne = self._fenster(merkmal="")
        ohne._ampr_pack_konsolenhinweis("egal")
        self.assertNotIn("ampr_pack.konsole_playgo", "\n".join(ohne._protokoll))

        mit = self._fenster(merkmal="sce_sys/playgo-scenario.json")
        mit._ampr_pack_konsolenhinweis("egal")
        zeile = next(z for z in mit._protokoll if z.startswith("ampr_pack.konsole_playgo"))
        self.assertIn("playgo-scenario.json", zeile,
                      "Das gefundene Merkmal gehoert in die Meldung")

    def test_hinweis_auf_die_originale_nur_wenn_sie_bleiben(self):
        bleibt = self._fenster()
        bleibt._ampr_originale_weglassen = False
        bleibt._ampr_pack_konsolenhinweis("egal")
        self.assertIn("ampr_pack.konsole_originale", "\n".join(bleibt._protokoll))

        weg = self._fenster()
        weg._ampr_originale_weglassen = True
        weg._ampr_pack_konsolenhinweis("egal")
        self.assertNotIn("ampr_pack.konsole_originale", "\n".join(weg._protokoll))

    def test_eine_unlesbare_quelle_bricht_nichts_ab(self):
        """Der Hinweis ist Beiwerk - er darf den fertigen Bau nicht kippen."""
        import PS5ImageConverter_Pro_FINAL_revised as APP

        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._protokoll = []
        gui._append_to_log = gui._protokoll.append
        gui._t = lambda schluessel, **werte: schluessel

        def _wirft(_ordner):
            raise OSError("kein Zugriff")
        gui._titel_nutzt_playgo = _wirft
        gui._ampr_pack_konsolenhinweis("egal")
        self.assertIn("ampr_pack.konsole_fakelib", "\n".join(gui._protokoll))

    def test_das_handbuch_nennt_beide_einstellungen(self):
        """Zweite Haelfte des Auftrags: es muss auch im Handbuch stehen."""
        handbuch = (PROJEKT / "BENUTZERHANDBUCH.html").read_text(encoding="utf-8")
        for stelle in ("backport_fakelib", "global_fakelib_priority",
                       "playgo-scenario.json", "playgo.pgm"):
            self.assertIn(stelle, handbuch, "%s fehlt im Handbuch" % stelle)


class SystemdateienImPackTests(unittest.TestCase):
    """Der zweite Riegel: gefragt wird das fertige Manifest, nicht das Profil.

    Warum es beide braucht: Die Ausschlussliste steht im Profil, und ein
    Anwender darf ein eigenes Profil hinterlegen. Am 20.09.2026 lag genau
    deshalb ein Abbild von Ghost of Yotei vor, dessen Manifest 84.182 von
    84.219 Dateien als PACK fuehrte - darunter cache_ps5/playgo.pgm, die 23
    pgc_*_dummy_file und game.sprig.packman. Mit "Originale weglassen"
    verschwanden sie aus /app0, und das Spiel stuerzte 0,2 s nach dem Start
    ab (SIGSEGV auf 0x20, im Spielcode, mit jeder EMU-Fassung).
    """

    def _zeile(self, pfad: str, gepackt: bool = True) -> dict:
        return {"path": pfad, "packed": gepackt, "size": 4096}

    def test_unity_metadaten_werden_erkannt(self):
        """An der Konsole gemessen (20.09.2026): ohne diese Datei kein Start.

        Der Debug-Bau des Emulators meldete beim Start von "Wer wird
        Millionaer" (ohne Originale gebaut)
        ``io.hook.error function=open errno=2 ... path=/app0/Media/Metadata/
        global-metadata.dat``, danach beendete sich das Spiel selbst. Die
        Unity-Laufzeit liest die IL2CPP-Metadaten an der Emulation vorbei.
        """
        self.assertEqual(
            ap.systemdateien_im_pack([
                self._zeile("/app0/Media/Metadata/global-metadata.dat")]),
            ["/app0/Media/Metadata/global-metadata.dat"])
        self.assertIn("global-metadata.dat", ap.NIE_PACKEN)
        self.assertIn("**/global-metadata.dat", ap.NIE_PACKEN)

    def test_playgo_und_verwandte_werden_erkannt(self):
        getroffen = ap.systemdateien_im_pack([
            self._zeile("/app0/cache_ps5/playgo.pgm"),
            self._zeile("/app0/cache_ps5/game.sprig.packman"),
            self._zeile("/app0/cache_ps5/pgc_game_dummy_file"),
            self._zeile("/app0/cache_ps5/pgc_lang_arabic_dummy_file"),
            self._zeile("/app0/assets/t0.dat"),
        ])
        self.assertEqual(getroffen, [
            "/app0/cache_ps5/playgo.pgm",
            "/app0/cache_ps5/game.sprig.packman",
            "/app0/cache_ps5/pgc_game_dummy_file",
            "/app0/cache_ps5/pgc_lang_arabic_dummy_file",
        ])

    def test_lose_gefuehrte_systemdatei_ist_in_ordnung(self):
        """Lose ist der gewollte Zustand - nur im Band ist sie ein Fehler."""
        self.assertEqual(ap.systemdateien_im_pack([
            self._zeile("/app0/cache_ps5/playgo.pgm", gepackt=False)]), [])

    def test_nutzdaten_loesen_keinen_fehlalarm_aus(self):
        self.assertEqual(ap.systemdateien_im_pack([
            self._zeile("/app0/cache_ps5/meshes/ui_movie_text.xmesh"),
            self._zeile("/app0/sounds/scream/_streams/sfx/a.xvag"),
            self._zeile("/app0/cache_ps5/bitmaps/x.sps")]), [])

    def test_grossschreibung_zaehlt_nicht(self):
        """Die Laufzeit vergleicht Pfade ohne Ruecksicht auf die Schreibung."""
        self.assertEqual(
            ap.systemdateien_im_pack([self._zeile("/app0/cache_ps5/PlayGo.PGM")]),
            ["/app0/cache_ps5/PlayGo.PGM"])

    def test_leere_liste_bleibt_still(self):
        self.assertEqual(ap.systemdateien_im_pack([]), [])
        self.assertEqual(ap.systemdateien_im_pack([{"kein": "pfad"}]), [])


class WoDieMethodeGreiftTests(unittest.TestCase):
    """Wo die neue Methode greift - und unter welcher Bedingung.

    Bis zum 08.09.2026 hing sie allein am Kaestchen "AMPR EMU" beim
    Erstellen; danach baute auch Aufgabe 7 nach jedem Eingriff Baender. Am
    17.09.2026 wurde das ausgebaut: Aufgabe 7 war nur noch der AMPR EMU
    Manager.

    Seit v1.9.36 baut sie wieder - aber **nur auf Knopfdruck**. Der Ausbau
    galt nie dem Bauen selbst, sondern dem Automatismus drumherum. Genau den
    prueft dieser Test jetzt, statt das Bauen zu verbieten.
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

    def test_in_aufgabe_sieben_nur_auf_knopfdruck(self):
        """Der Punkt, an dem es am 17.09.2026 scheiterte.

        Damals baute der Block nach **jedem** Eingriff Baender - auch nach
        Wiederherstellen und Entfernen, und auch nach einer laengst
        abgeschalteten Einstellung. Gebaut werden darf nur unter
        ``action == "ampr_assetpack"``.
        """
        import ast
        knoten = self._funktion("_mode_ampr_manager")
        self.assertIsNotNone(knoten, "_mode_ampr_manager heisst nicht mehr so")
        rufe = [k for k in ast.walk(knoten) if isinstance(k, ast.Call)
                and isinstance(k.func, ast.Attribute)
                and k.func.attr == "_ampr_assetpakete_bauen"]
        self.assertEqual(
            1, len(rufe),
            "Erwartet genau einen Aufruf - den aus dem Knopf. Gefunden: %d"
            % len(rufe))

        def _prueft_die_aktion(test) -> bool:
            """Steht in der Bedingung ein Vergleich action == 'ampr_assetpack'?

            Die Textsuche taugt hier nicht: Der Name steht auch als Argument
            in ``spec.get('ampr_assetpack')`` und wuerde den Test gruen
            halten, waere die Aktionspruefung ausgebaut.
            """
            for k in ast.walk(test):
                if not isinstance(k, ast.Compare):
                    continue
                if not (isinstance(k.left, ast.Name) and k.left.id == "action"):
                    continue
                for op, rechts in zip(k.ops, k.comparators):
                    if (isinstance(op, ast.Eq)
                            and isinstance(rechts, ast.Constant)
                            and rechts.value == "ampr_assetpack"):
                        return True
            return False

        eltern = [k for k in ast.walk(knoten)
                  if isinstance(k, ast.If) and rufe[0] in list(ast.walk(k))]
        self.assertTrue(
            any(_prueft_die_aktion(k.test) for k in eltern),
            "Der Aufruf haengt an keiner Aktionspruefung - dann baut wieder "
            "jeder Eingriff Baender.")

    def test_aufgabe_sieben_greift_nur_lesend_ins_packmodul(self):
        """Entfernen bleibt draussen.

        Ohne die Originale neben den Baendern waere ein "Asset-Pack
        entfernen" der Weg, die Spieldaten zu loeschen. Erlaubt sind allein
        die beiden Abfragen, die der Knopf vor dem Bauen braucht.
        """
        import ast
        knoten = self._funktion("_mode_ampr_manager")
        self.assertIsNotNone(knoten, "_mode_ampr_manager heisst nicht mehr so")
        aufrufe = [k for k in ast.walk(knoten) if isinstance(k, ast.Call)
                   and isinstance(k.func, ast.Attribute)]
        self.assertTrue(aufrufe, "Keine Aufrufe gefunden - der Test misst nichts")
        ins_modul = {k.func.attr for k in aufrufe
                     if isinstance(k.func.value, ast.Name)
                     and k.func.value.id == "ampr_assetpakete"}
        erlaubt = {"variante_kann_packen", "einsatzbereit"}
        self.assertLessEqual(
            ins_modul, erlaubt,
            "Aufgabe 7 greift neu ins Packmodul: %s" % sorted(ins_modul - erlaubt))


class GrundWirdUebersetztTests(unittest.TestCase):
    """`einsatzbereit()` gibt einen Schluessel zurueck, keinen Satz.

    Am 20.09.2026 stand er roh im Fenster: "Das Packwerkzeug steht nicht
    bereit: ampr_pack.werkzeug_fehlt". Der Docstring der Funktion sagt es
    ausdruecklich - trotzdem faellt es leicht durch, weil die Meldung
    vollstaendig aussieht.

    Geprueft wird das ganze Hauptmodul, nicht nur die eine Stelle: Wer
    `einsatzbereit()` das naechste Mal aufruft, faellt in dieselbe Grube.
    """

    HAUPT = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"

    @staticmethod
    def _ist_uebersetzungsruf(knoten) -> bool:
        """Ist das ein Aufruf von ``self._t(...)`` oder ``_t(...)``?"""
        import ast
        if not isinstance(knoten, ast.Call):
            return False
        ziel = knoten.func
        if isinstance(ziel, ast.Attribute):
            return ziel.attr == "_t"
        return isinstance(ziel, ast.Name) and ziel.id == "_t"

    def _gruende_der_funktion(self, funktion) -> set:
        """Welche Namen haelt diese Funktion aus ``einsatzbereit()``?"""
        import ast
        namen = set()
        for k in ast.walk(funktion):
            if not isinstance(k, ast.Assign):
                continue
            wert = k.value
            if not (isinstance(wert, ast.Call)
                    and isinstance(wert.func, ast.Attribute)
                    and wert.func.attr == "einsatzbereit"):
                continue
            for ziel in k.targets:
                # `bereit, grund = ...` - der Grund ist der zweite Eintrag.
                if isinstance(ziel, ast.Tuple) and len(ziel.elts) == 2:
                    zweiter = ziel.elts[1]
                    if isinstance(zweiter, ast.Name):
                        namen.add(zweiter.id)
        return namen

    def test_kein_roher_schluessel_in_einer_meldung(self):
        import ast
        baum = ast.parse(self.HAUPT.read_text(encoding="utf-8"))
        stellen = 0
        funde = []
        for funktion in ast.walk(baum):
            if not isinstance(funktion, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            gruende = self._gruende_der_funktion(funktion)
            if not gruende:
                continue
            stellen += 1
            for k in ast.walk(funktion):
                if not self._ist_uebersetzungsruf(k):
                    continue
                for wort in k.keywords:
                    if not (isinstance(wort.value, ast.Name)
                            and wort.value.id in gruende):
                        continue
                    funde.append("%s (Zeile %d): %s=%s"
                                 % (funktion.name, wort.value.lineno,
                                    wort.arg, wort.value.id))
        self.assertGreaterEqual(
            stellen, 1,
            "Keine Funktion ruft mehr `einsatzbereit()` in der Form "
            "`bereit, grund = ...` auf - der Test misst nichts.")
        self.assertEqual(
            [], funde,
            "Ein Uebersetzungsschluessel steht roh in einer Meldung. Er "
            "gehoert in ein eigenes _t(...):\n  " + "\n  ".join(funde))

    def test_der_vertrag_steht_im_docstring(self):
        """Wer die Funktion liest, muss es erfahren."""
        import inspect
        text = inspect.getdoc(ap.einsatzbereit) or ""
        self.assertIn("schluessel", text.lower(),
                      "Der Docstring sagt nicht mehr, dass der Grund ein "
                      "Uebersetzungsschluessel ist - dann faellt die naechste "
                      "Stelle wieder darauf herein.")


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


class AufgabeSiebenOhneAssetPackTests(unittest.TestCase):
    """Aufgabe 7 baut und entfernt seit dem 17.09.2026 keine Asset-Packs.

    Bis dahin gab es dort den Knopf "Asset-Pack entfernen" (Kommandozeile:
    ``--ampr-action ampr_pack_remove``). Er loeschte Manifest, .runtime und
    Baender in der Annahme, die Originale laegen daneben - gemessen am
    08.09.2026 an einem Ordner mit elf Dateien. Seit gepackte Originale beim
    Erstellen weggelassen werden koennen, stimmt die Annahme nicht mehr: Der
    Rueckweg haette dann die Spieldaten geloescht. Der Anwender hat
    entschieden, ihn herauszunehmen statt ihn abzusichern; Aufgabe 7 bleibt
    der AMPR EMU Manager (siehe auch AufgabeSiebenFasstPackNichtAnTests in
    test_debuglauf_befunde.py fuer das Verhalten).
    """

    RUECKWEG_TEXTE = (
        "ampr.btn_pack_remove", "progress.prepare.remove_asset_pack",
        "ampr_pack.entfernt", "ampr_pack.entfernt_datei",
        "ampr_pack.nichts_zu_entfernen", "ampr_pack.ordner_unlesbar",
        "ampr_pack.entfernen_fehlgeschlagen",
    )

    def test_die_kommandozeile_kennt_die_aktion_nicht_mehr(self):
        import PS5ImageConverter_Pro_FINAL_revised as APP
        parser = APP._build_cli_parser()
        aktion = next((a for a in parser._actions
                       if "--ampr-action" in a.option_strings), None)
        self.assertIsNotNone(aktion, "--ampr-action gibt es nicht mehr")
        self.assertNotIn("ampr_pack_remove", aktion.choices)
        # Die Aktionen des AMPR EMU Managers bleiben alle.
        for bleibt in ("ampr_apply", "ampr_restore", "ampr_remove",
                       "ampr_index", "ampr_ftp_index"):
            with self.subTest(aktion=bleibt):
                self.assertIn(bleibt, aktion.choices)

    def test_weder_knopf_noch_aktion_im_manager(self):
        """Am Syntaxbaum: keine Zeichenkette des Rueckwegs in Aufgabe 7."""
        import ast
        haupt = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8")
        knoten = next((k for k in ast.walk(ast.parse(haupt))
                       if isinstance(k, ast.FunctionDef)
                       and k.name == "_mode_ampr_manager"), None)
        self.assertIsNotNone(knoten, "_mode_ampr_manager heisst nicht mehr so")
        texte = {k.value for k in ast.walk(knoten)
                 if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        # Gegenstueck: Die uebrigen Knoepfe stehen als Zeichenketten darin -
        # sonst saehe dieser Test gar nichts.
        self.assertIn("ampr.btn_index_only", texte)
        self.assertIn("ampr_index", texte)
        self.assertNotIn("ampr.btn_pack_remove", texte)
        self.assertNotIn("ampr_pack_remove", texte)

    def test_das_packmodul_hat_keinen_rueckweg_mehr(self):
        self.assertFalse(hasattr(ap, "pack_entfernen"))
        self.assertFalse(hasattr(ap, "packdateien_finden"))
        # Was der Bauweg beim Erstellen braucht, ist weiter da.
        self.assertTrue(callable(getattr(ap, "quellen_entfernen", None)))

    def test_die_texte_des_rueckwegs_sind_weg(self):
        from ps5_validator.utils import i18n
        for schluessel in self.RUECKWEG_TEXTE:
            with self.subTest(schluessel=schluessel):
                self.assertNotIn(schluessel, i18n.STRINGS)
        hinweis = i18n.STRINGS.get("ampr.aufgabe7_ohne_assetpack") or {}
        self.assertIn("Aufgabe 7", hinweis.get("de", ""))
        self.assertIn("Task 7", hinweis.get("en", ""))


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


class PipeStauTests(unittest.TestCase):
    """Der stdout-Puffer des Packwerkzeugs wird nebenher geleert.

    ``_lauf`` startet den Unterprozess mit ``stdout=PIPE`` **und**
    ``stderr=PIPE``. Wuerde stdout erst nach der stderr-Schleife gelesen,
    bliebe sein Puffer waehrend des ganzen Laufs stehen - unter Windows
    rund 64 KB. Schreibt das Werkzeug mehr, blockiert es, und der
    Elternprozess wartet auf ein stderr-EOF, das nie kommt.

    **Dieser Fall ist nicht gemessen.** Ein Lauf ueber 4000 Dateien am
    12.09.2026 brachte 664 Byte auf stdout - das Abschluss-JSON nennt nur
    die *nicht* gepackten Dateien, und das waren zwei. Der Waechter steht
    trotzdem: Ein Titel mit vielen unkomprimierbaren Dateien fuellt die
    Liste, und dann haengt der Lauf ohne jede Meldung.

    Der Absturz vom selben Tag hatte eine andere Ursache - siehe
    ``StromabsicherungTests``.
    """

    QUELLE = (Path(__file__).resolve().parent / "ps5_validator" / "utils"
              / "ampr_assetpakete.py")

    def test_stdout_wird_nebenher_geleert(self):
        text = self.QUELLE.read_text(encoding="utf-8")
        self.assertIn("threading.Thread", text,
                      "Ohne eigenen Leser staut sich der stdout-Puffer.")
        self.assertIn("_stdout_leeren", text)

    def test_stdout_wird_nicht_erst_am_ende_gelesen(self):
        """Geprueft wird der Code, nicht der Text.

        Der erste Anlauf suchte die alte Zeile im ganzen Modul - und fand
        sie im Kommentar, der sie erklaert. Ein Waechter, der auf seine
        eigene Beschreibung anschlaegt, taugt nichts.
        """
        import ast

        baum = ast.parse(self.QUELLE.read_text(encoding="utf-8"))
        lauf = next(k for k in ast.walk(baum)
                    if isinstance(k, ast.FunctionDef) and k.name == "_lauf")
        # Jeder Aufruf von prozess.stdout.read() im Rumpf von _lauf.
        blockierend = [
            k for k in ast.walk(lauf)
            if isinstance(k, ast.Call)
            and isinstance(k.func, ast.Attribute)
            and k.func.attr == "read"
            and isinstance(k.func.value, ast.Attribute)
            and k.func.value.attr == "stdout"]
        self.assertEqual([], blockierend,
                         "stdout mit read() am Stueck zu lesen laesst den "
                         "Puffer volllaufen, solange die stderr-Schleife "
                         "noch laeuft.")

    def test_der_leser_wird_auch_eingesammelt(self):
        """Ohne ``join`` koennte die Ausgabe unvollstaendig sein."""
        text = self.QUELLE.read_text(encoding="utf-8")
        self.assertIn("leser.join", text)


class StromabsicherungTests(unittest.TestCase):
    """Ohne Konsole darf ``print`` die Aufgabe nicht zum Absturz bringen.

    Am 12.09.2026 vom Anwender gemeldet, mit Bildschirmfoto: Die fertige
    Programmdatei stuerzte beim Asset-Pack ab, zwei Tracebacks
    uebereinander, beide ``OSError: [Errno 22] Invalid argument``. Der
    erste in ``ampr_pack.py`` Zeile 290 - einem schlichten ``print``.

    Die Ursache: Die Programmdatei ist mit ``console=False`` gebaut. Ruft
    sie sich selbst mit ``--ampr-pack`` auf und leitet niemand die Stroeme
    um, ist ``sys.stderr`` unbrauchbar - und das Werkzeug schreibt seinen
    ganzen Fortschritt dorthin. Weil sein Fehlerbehandler es ebenfalls mit
    ``print`` versucht, wirft der gleich noch einmal.

    Der Strom ist dabei **nicht** ``None`` - er existiert und taugt nur
    nichts. Eine Pruefung auf ``is None`` ginge daran vorbei.
    """

    HAUPT = Path(__file__).resolve().parent / "PS5ImageConverter_Pro_FINAL_revised.py"

    class _KaputterStrom:
        """So verhaelt sich ``sys.stderr`` in einer console=False-EXE."""

        def write(self, _text):
            raise OSError(22, "Invalid argument")

        def flush(self):
            raise OSError(22, "Invalid argument")

    @classmethod
    def setUpClass(cls):
        import importlib.util
        if "hauptprogramm" in sys.modules:
            cls.haupt = sys.modules["hauptprogramm"]
            return
        spec = importlib.util.spec_from_file_location("hauptprogramm", cls.HAUPT)
        modul = importlib.util.module_from_spec(spec)
        sys.modules["hauptprogramm"] = modul
        spec.loader.exec_module(modul)
        cls.haupt = modul

    def test_ohne_absicherung_scheitert_print(self):
        """Der Anker: Ohne die Reparatur tritt der Fehler wirklich auf."""
        echt = sys.stderr
        sys.stderr = self._KaputterStrom()
        try:
            with self.assertRaises(OSError) as gefangen:
                print("Fortschritt", file=sys.stderr, flush=True)
            self.assertEqual(22, gefangen.exception.errno)
        finally:
            sys.stderr = echt

    def test_mit_absicherung_laeuft_print_durch(self):
        echt = sys.stderr
        sys.stderr = self._KaputterStrom()
        try:
            self.haupt._stroeme_absichern()
            print("Fortschritt", file=sys.stderr, flush=True)
        finally:
            sys.stderr = echt

    def test_ein_brauchbarer_strom_bleibt_unangetastet(self):
        """Sonst ginge die Ausgabe eines CLI-Laufs ins Leere."""
        import io as _io

        echt = sys.stderr
        eigener = _io.StringIO()
        sys.stderr = eigener
        try:
            self.haupt._stroeme_absichern()
            self.assertIs(eigener, sys.stderr,
                          "Ein funktionierender Strom darf nicht ersetzt werden.")
        finally:
            sys.stderr = echt

    def test_die_absicherung_haengt_wirklich_im_selbstaufruf(self):
        """Eine Reparatur, die nur der Test ruft, schuetzt niemanden."""
        text = self.HAUPT.read_text(encoding="utf-8")
        stelle = text.index("def _run_ampr_pack_subcommand")
        ende = text.index("def _is_admin", stelle)
        self.assertIn("_stroeme_absichern()", text[stelle:ende],
                      "Der Selbstaufruf muss die Stroeme absichern, bevor "
                      "das Werkzeug laeuft.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
