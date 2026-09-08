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



if __name__ == "__main__":
    unittest.main(verbosity=2)
