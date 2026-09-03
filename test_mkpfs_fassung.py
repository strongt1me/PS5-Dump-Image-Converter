# -*- coding: utf-8 -*-
"""Bewacht die eingebettete MkPFS-Engine.

Angelegt am 03.09.2026, als 0.0.9 durch 1.0.0 ersetzt wurde.

Der Austausch war moeglich, weil die Engine ihre Schnittstelle behalten
hat: dieselben 125 Funktionen in ``pfs.py``, kein entfallener
Unterbefehl, kein entfallener Schalter. Drei Dinge sind dabei aber
beinahe still verlorengegangen, und die stehen hier:

* Der **Rueckfall auf Standard-zlib**, wenn ``zlib_ng`` auf dem Rechner
  fehlt. In 0.0.9 stand er oben in ``pfs.py``; 1.0.0 hat das Packen in
  ein eigenes Modul verlegt und bricht dort mit ``ImportError`` ab. Der
  Rueckfall ist als ``_ensure_backend_with_fallback`` wieder da - eine
  Zutat dieses Projekts, siehe ``MkPFS-1.0.0/UPSTREAM.md``.
* Das **Rechenwerk**. 1.0.0 stellt ``--compression-backend`` auf
  ``auto`` und bevorzugt damit ``isal``, das mit einer eigenen
  Stufenskala arbeitet. Diese Fassung legt sich auf ``zlib-ng`` fest.
* Die **Namen, die das Programm benutzt**. Sie werden hier nicht im
  Quelltext gesucht, sondern am geladenen Modul abgefragt.

Gefragt wird jeweils nach der Sache, nicht nach der Schreibweise: Der
Rueckfall wird ausgeloest statt gelesen, und die Fassungsnummer steht
nicht in der Erwartung, sondern wird zwischen Ordner, ``__version__``
und der Vorgabe des Programms **abgeglichen**.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from ps5_validator.utils import werkzeuge_bereitstellen as wb

PROJEKT = Path(__file__).resolve().parent


def _engine_ordner() -> list[Path]:
    """Alle Ordner im Stamm, die das Programm als Engine ansehen wuerde."""
    return [p for p in sorted(PROJEKT.glob("MkPFS-*"), reverse=True)
            if (p / "mkpfs" / "__init__.py").is_file()]


def _im_unterprozess(ordner: Path, skript: str,
                     *argumente: str) -> subprocess.CompletedProcess[str]:
    """Fuehrt ``skript`` mit ``ordner`` als erstem Argument aus.

    Eigener Prozess, weil in diesem hier laengst ein ``mkpfs`` geladen
    sein kann - womoeglich das aus ``site-packages``.
    """
    return subprocess.run(
        [sys.executable, "-c", skript, str(ordner), *argumente],
        capture_output=True, text=True, timeout=120)


class FassungTests(unittest.TestCase):
    """Ordner, ``__version__`` und die Vorgabe muessen dasselbe sagen."""

    def test_genau_eine_engine_im_stamm(self) -> None:
        """Zwei Ordner waeren kein Nebeneinander, sondern eine Weiche.

        ``ffpfs_validator._ensure_mkpfs_importable`` sortiert ``MkPFS-*``
        mit ``reverse=True`` und nimmt den ersten;
        ``PS5ImageConverter_Pro.spec`` sammelt dagegen alle ein. In der
        EXE laegen dann beide, und welche gewinnt, entschiede die
        Sortierung.
        """
        ordner = _engine_ordner()
        self.assertEqual(1, len(ordner),
                         "Genau ein MkPFS-* wird erwartet, gefunden: "
                         + ", ".join(p.name for p in ordner))

    def test_ordnername_nennt_die_verlangte_fassung(self) -> None:
        verlangt = wb.MKPFS_ERFORDERLICHE_FASSUNG
        self.assertEqual([f"MkPFS-{verlangt}"],
                         [p.name for p in _engine_ordner()])

    def test_die_engine_meldet_dieselbe_fassung(self) -> None:
        """Nicht der Ordnername entscheidet, sondern das Paket selbst."""
        lauf = _im_unterprozess(
            _engine_ordner()[0],
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "import mkpfs; print(mkpfs.__version__)")
        self.assertEqual(0, lauf.returncode, lauf.stderr[-400:])
        self.assertEqual(wb.MKPFS_ERFORDERLICHE_FASSUNG, lauf.stdout.strip())


class SchnittstelleTests(unittest.TestCase):
    """Die Namen, an denen das Programm haengt."""

    #: Modul -> Namen, die das Programm daraus holt. Zusammengetragen aus
    #: dem Monolithen, ``ffpfs_validator``, ``abbild_metadaten``,
    #: ``abbild_pruefen`` und ``ps4_werkzeug``.
    ERWARTET = {
        "mkpfs.pfs": ("inspect_pfs_image", "open_inner_file_view",
                      "parse_image_header", "parse_image_inodes",
                      "parse_superroot_and_indexes", "build_tree_from_uroot",
                      "read_image_bytes", "read_image_inode_payload",
                      "decode_inode_payload", "verify_pfs_image",
                      "fold_inner_name_to_ascii",
                      "resolve_single_file_inner_name"),
        "mkpfs.exfat": ("ExfatReader", "open_exfat"),
        "mkpfs.exfat_writer": ("iter_exfat_image",),
        "mkpfs.ampr": ("ensure_ampr_index",),
        "mkpfs.cli": ("cli_mkpfs_main",),
    }

    SKRIPT = (
        "import sys, importlib\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "fehlt = []\n"
        "for eintrag in sys.argv[2:]:\n"
        "    modul, _, name = eintrag.partition(':')\n"
        "    if not hasattr(importlib.import_module(modul), name):\n"
        "        fehlt.append(eintrag)\n"
        "print(' '.join(fehlt))\n")

    def test_alle_benutzten_namen_sind_da(self) -> None:
        eintraege = [f"{modul}:{name}"
                     for modul, namen in self.ERWARTET.items()
                     for name in namen]
        lauf = _im_unterprozess(_engine_ordner()[0], self.SKRIPT, *eintraege)
        self.assertEqual(0, lauf.returncode, lauf.stderr[-600:])
        self.assertEqual("", lauf.stdout.strip(),
                         "Diese Namen fehlen der Engine: " + lauf.stdout.strip())

    def test_der_abgleich_findet_auch_etwas(self) -> None:
        """Gegenprobe: ein erfundener Name muss gemeldet werden."""
        lauf = _im_unterprozess(_engine_ordner()[0], self.SKRIPT,
                                "mkpfs.pfs:gibt_es_nicht")
        self.assertEqual(0, lauf.returncode, lauf.stderr[-400:])
        self.assertEqual("mkpfs.pfs:gibt_es_nicht", lauf.stdout.strip())

    def test_ampr_index_laeuft_weiter_ohne_die_neuen_angaben(self) -> None:
        """1.0.0 hat ``ensure_ampr_index`` drei Angaben angehaengt.

        Sie haben Vorgaben, und die Vorgaben muessen den alten Weg
        beschreiben - sonst erzeugt das Programm keinen AMPR-Index mehr,
        ohne dass etwas rot wird. Das Programm ruft die Funktion mit
        ``ensure_ampr_index(root_path, enabled=True)``.
        """
        lauf = _im_unterprozess(
            _engine_ordner()[0],
            "import sys, inspect\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "from mkpfs.ampr import ensure_ampr_index\n"
            "s = inspect.signature(ensure_ampr_index)\n"
            "ohne = [n for n, p in s.parameters.items()\n"
            "        if n != 'source_root'\n"
            "        and p.default is inspect.Parameter.empty]\n"
            "print('OHNE_VORGABE:' + ','.join(ohne))\n"
            "print('create_if_missing=%r'\n"
            "      % (s.parameters['create_if_missing'].default\n"
            "         if 'create_if_missing' in s.parameters else 'fehlt',))\n")
        self.assertEqual(0, lauf.returncode, lauf.stderr[-400:])
        zeilen = lauf.stdout.split()
        self.assertEqual("OHNE_VORGABE:", zeilen[0],
                         "Ein neuer Pflichtwert wuerde den Aufruf im "
                         "Programm umwerfen: " + zeilen[0])
        # False heisst: es wird immer neu gebaut - das Verhalten von 0.0.9.
        self.assertEqual("create_if_missing=False", zeilen[1])


class RueckfallTests(unittest.TestCase):
    """Der Patch dieses Projekts an ``compression.py``."""

    SPERRE = (
        "import sys\n"
        "class Sperre:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.startswith('zlib_ng'):\n"
        "            raise ImportError('gesperrt')\n"
        "        return None\n"
        "sys.meta_path.insert(0, Sperre())\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from mkpfs import compression as comp\n"
        "roh = b'abcdefgh' * 4096\n"
        "zurueck = comp.decompress_block(comp.compress_block(roh, level=9))\n"
        "print(comp.get_backend_name(), zurueck == roh)\n")

    def test_ohne_zlib_ng_wird_weitergearbeitet(self) -> None:
        lauf = _im_unterprozess(_engine_ordner()[0], self.SPERRE)
        self.assertEqual(0, lauf.returncode,
                         "Ohne zlib_ng bricht die Engine ab - der Rueckfall "
                         "aus 0.0.9 fehlt:\n" + lauf.stderr[-600:])
        self.assertEqual("zlib True", lauf.stdout.strip())

    def test_die_sperre_wirkt_ueberhaupt(self) -> None:
        """Gegenprobe: ohne Sperre muss ein anderes Rechenwerk herauskommen.

        Sonst bewiese der Test darueber nur, dass zlib_ng gar nicht
        installiert ist.
        """
        lauf = _im_unterprozess(
            _engine_ordner()[0],
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "from mkpfs import compression as comp; "
            "comp.compress_block(b'x' * 64, level=9); "
            "print(comp.get_backend_name())")
        self.assertEqual(0, lauf.returncode, lauf.stderr[-400:])
        self.assertEqual("zlib-ng", lauf.stdout.strip(),
                         "Auf diesem Rechner fehlt zlib_ng - dann sagt der "
                         "Rueckfalltest daneben nichts.")


class BackendTests(unittest.TestCase):
    """Das festgelegte Rechenwerk und der Weg, auf dem es hinausgeht."""

    def setUp(self) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt

        self.haupt = haupt

    def test_das_festgelegte_backend_kennt_die_engine(self) -> None:
        lauf = _im_unterprozess(
            _engine_ordner()[0],
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "from mkpfs import compression as comp; "
            "comp.set_backend(sys.argv[2]); print(comp.get_backend_name())",
            self.haupt.MKPFS_BACKEND)
        self.assertEqual(0, lauf.returncode,
                         f"MKPFS_BACKEND={self.haupt.MKPFS_BACKEND!r} kennt "
                         f"die Engine nicht:\n{lauf.stderr[-400:]}")
        self.assertEqual(self.haupt.MKPFS_BACKEND, lauf.stdout.strip())

    def test_packaufrufe_bekommen_das_backend(self) -> None:
        for unterbefehl in ("folder", "file"):
            with self.subTest(unterbefehl=unterbefehl):
                ergebnis = self.haupt.mkpfs_argumente_mit_backend(
                    ["pack", unterbefehl, "--compression-level", "9", "q", "z"])
                self.assertEqual(
                    ["pack", unterbefehl,
                     "--compression-backend", self.haupt.MKPFS_BACKEND,
                     "--compression-level", "9", "q", "z"],
                    ergebnis)

    def test_andere_aufrufe_bleiben_unberuehrt(self) -> None:
        """``unpack``, ``verify``, ``tree`` und ``inspect`` kennen ihn nicht."""
        for args in (["unpack", "--overwrite", "q", "z"],
                     ["verify", "q"], ["tree", "q"], ["inspect", "q"],
                     ["pack"], []):
            with self.subTest(args=args):
                self.assertEqual(
                    args, self.haupt.mkpfs_argumente_mit_backend(list(args)))

    def test_eine_eigene_angabe_wird_nicht_ueberschrieben(self) -> None:
        args = ["pack", "file", "--compression-backend", "zlib", "q", "z"]
        self.assertEqual(args, self.haupt.mkpfs_argumente_mit_backend(list(args)))


class OberflaecheTests(unittest.TestCase):
    """Die mitgelieferte Oberflaeche gehoert nicht hierher."""

    def test_die_engine_bringt_keine_oberflaeche_mit(self) -> None:
        """``mkpfs/gui/`` verlangt customtkinter und Pillow.

        Das Programm bringt sein eigenes Fenster mit; dieselbe
        Entscheidung wie bei PS4 FFPFSC. Siehe ``UPSTREAM.md``.
        """
        self.assertFalse((_engine_ordner()[0] / "mkpfs" / "gui").exists(),
                         "mkpfs/gui/ liegt im Projekt, siehe UPSTREAM.md")

    def test_kein_modul_verlangt_die_oberflaechenpakete(self) -> None:
        lauf = _im_unterprozess(
            _engine_ordner()[0],
            "import sys, importlib, pkgutil\n"
            "class Sperre:\n"
            "    def find_spec(self, name, path=None, target=None):\n"
            "        if name.split('.')[0] in ('customtkinter', 'PIL'):\n"
            "            raise ImportError('gesperrt: ' + name)\n"
            "        return None\n"
            "sys.meta_path.insert(0, Sperre())\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "import mkpfs\n"
            "for m in pkgutil.iter_modules(mkpfs.__path__):\n"
            "    if m.name != '__main__':\n"
            "        importlib.import_module('mkpfs.' + m.name)\n"
            "print('alle geladen')\n")
        self.assertEqual(0, lauf.returncode,
                         "Ein Engine-Modul verlangt ein Oberflaechenpaket:\n"
                         + lauf.stderr[-600:])
        self.assertEqual("alle geladen", lauf.stdout.strip())


class StandTests(unittest.TestCase):
    """Die Fassungsnummer taugt nicht zum Vergleichen.

    Die Vorlage wird unter derselben Nummer weitergepflegt. Der am
    31.08.2026 eingebettete Stand und der am 03.09.2026 nachgezogene
    melden beide ``1.0.0`` und unterscheiden sich in drei Dateien.
    :class:`FassungTests` oben gleicht Ordnername, ``__version__`` und
    Vorgabe ab - alle drei stimmen ueberein, waehrend der Code
    auseinanderlaeuft. Diese Klasse haengt deshalb an der Sache.
    """

    def test_die_lizenz_liegt_bei_der_engine(self) -> None:
        """GPL-3.0 verlangt den Text beim Quellcode, den er deckt.

        Bis zum 03.09.2026 war MkPFS die einzige eingebettete
        Fremdkomponente ohne ihn - ProsperoPkg, PS4 FFPFSC, UFS2Tool
        und pgo_stub trugen ihren laengst. Die Nennung in
        ``THIRD_PARTY_LICENSES.md`` sagt, wozu die Engine dient, und
        ersetzt den Lizenztext nicht.
        """
        lizenz = _engine_ordner()[0] / "LICENSE"
        self.assertTrue(lizenz.is_file(),
                        "Der GPL-3.0-Text der Engine fehlt: %s" % lizenz)
        self.assertIn("GNU GENERAL PUBLIC LICENSE",
                      lizenz.read_text(encoding="utf-8", errors="replace"))

    #: Fragt das Modul ab, statt die Datei zu suchen. Die Felder von
    #: ``GameMetadata`` stehen mit dabei, weil sie es sind, die den
    #: Stand vom 03.09.2026 ausmachen - eine Datei dieses Namens
    #: koennte auch leer sein.
    GAME_METADATA = "\n".join((
        "import sys, inspect",
        "sys.path.insert(0, sys.argv[1])",
        "from mkpfs.game_metadata import read_game_metadata, GameMetadata",
        "print('SIGNATUR', inspect.signature(read_game_metadata))",
        "print('FELDER', ' '.join(GameMetadata.__dataclass_fields__))",
    ))

    def test_der_neuere_stand_ist_daran_zu_erkennen(self) -> None:
        """``game_metadata.py`` kam mit dem Stand vom 03.09.2026 dazu.

        Es ist der verlaessliche Anhaltspunkt, solange die Nummer
        gleich bleibt - das Modul selbst wird vom Programm nicht
        gebraucht und von keinem Engine-Modul importiert.

        **Gefragt wird nach dem Modul, nicht nach der Datei.** Die
        erste Fassung dieser Pruefung sah nur nach, ob eine Datei
        ``game_metadata.py`` existiert - eine leere haette genuegt.
        Der Anwender hat am 03.09.2026 darauf hingewiesen, dass es um
        ``read_game_metadata()`` geht. Jetzt wird das Modul geladen
        und nach seinem Inhalt gefragt.
        """
        lauf = _im_unterprozess(_engine_ordner()[0], self.GAME_METADATA)
        self.assertEqual(
            0, lauf.returncode,
            "mkpfs.game_metadata laesst sich nicht laden - dann liegt "
            "hier der aeltere Stand oder eine unvollstaendige Datei, "
            "obwohl __version__ weiterhin 1.0.0 meldet:\n"
            + lauf.stderr[-600:])

        ausgabe = lauf.stdout
        self.assertIn("SIGNATUR (file_path", ausgabe,
                      "read_game_metadata nimmt keinen Pfad mehr entgegen: "
                      + ausgabe)
        # Die Angaben, um derentwillen das Modul ueberhaupt geprueft
        # wird. Bewusst nicht alle zwoelf - sonst faellt die Pruefung
        # bei jeder harmlosen Erweiterung der Vorlage.
        for feld in ("content_id", "title_id", "game_title",
                     "has_apr_emu", "file_size"):
            with self.subTest(feld=feld):
                self.assertIn(feld, ausgabe,
                              "GameMetadata kennt '%s' nicht mehr." % feld)

    def test_die_abfrage_wuerde_ein_fehlendes_modul_melden(self) -> None:
        """Gegenprobe: ohne das Modul muss die Abfrage scheitern.

        Ohne sie waere nicht belegt, dass oben ueberhaupt etwas
        gemessen wird - siehe die Lehre aus dem Waechter, der nur den
        alten Namen suchte.
        """
        lauf = _im_unterprozess(
            _engine_ordner()[0],
            "\n".join((
                "import sys",
                "class Sperre:",
                "    def find_spec(self, name, path=None, target=None):",
                "        if name == 'mkpfs.game_metadata':",
                "            raise ImportError('gesperrt')",
                "        return None",
                "sys.meta_path.insert(0, Sperre())",
                "sys.path.insert(0, sys.argv[1])",
                "from mkpfs.game_metadata import read_game_metadata",
                "print('SIGNATUR unerwartet erreichbar')",
            )))
        self.assertNotEqual(
            0, lauf.returncode,
            "Die Sperre hat nicht gegriffen - dann sagt die Pruefung "
            "oben nichts darueber aus, ob das Modul wirklich da ist.")


class PrueflisteTests(unittest.TestCase):
    """Die PS5-Pruefliste und die Bauform.

    ``verify_pfs_image`` treibt Aufgabe 8. Ein Container der Bauform
    **exFAT-in-PFS** traegt auf PFS-Ebene nur eine einzige Nutzlast;
    ``sce_sys/param.json`` und ``eboot.bin`` liegen eine Ebene tiefer.
    Der aeltere Stand meldete sie deshalb als fehlend - drei Warnungen
    fuer Dateien, die da sind, bei jedem Container der Vorgabe-Bauform.

    Gemessen wird, nicht gelesen: Beide Faelle werden wirklich gebaut
    und geprueft. Der zweite ist die Gegenprobe - ohne ihn wuerde ein
    Stand durchgehen, der die Pruefliste einfach ganz abgeschaltet hat.
    """

    #: Baut zwei Container aus derselben Quelle und meldet je Fehler-
    #: und Warnungszahl. Eigener Prozess wegen sys.path, siehe oben.
    #: Zusammengesetzt statt als ein Textblock, damit hier keine
    #: Escapefolgen stehen, die eine spaetere Umschrift zerlegt.
    SKRIPT = "\n".join((
        "import contextlib, io, json, os, shutil, sys, tempfile",
        "from pathlib import Path",
        "sys.path.insert(0, sys.argv[1])",
        "from mkpfs.cli import cli_mkpfs_main",
        "from mkpfs.pfs import verify_pfs_image",
        # Nicht TemporaryDirectory als Kontext: Der Prozess steht mit
        # os.chdir IN dem Ordner, und Windows loescht kein Verzeichnis,
        # das das Arbeitsverzeichnis eines Prozesses ist (WinError 32).
        # Das Aufraeumen liess die Pruefung uebersprungen werden - und
        # eine uebersprungene Pruefung bewacht nichts.
        "vorher = os.getcwd()",
        "ordner = tempfile.mkdtemp()",
        "try:",
        "    os.chdir(ordner)",
        "    quelle = Path('quelle')",
        "    (quelle / 'sce_sys').mkdir(parents=True)",
        "    (quelle / 'sce_sys' / 'param.json').write_text(json.dumps(",
        "        {'titleId': 'CUSA00000',",
        "         'contentId': 'UP0000-CUSA00000_00-PROBE0000000000'}))",
        "    (quelle / 'eboot.bin').write_bytes(",
        "        bytes([127]) + b'ELF' + bytes(4092))",
        "    def fahre(*args):",
        "        sys.argv = ['mkpfs'] + list(args)",
        "        with contextlib.redirect_stdout(io.StringIO()):",
        "            return cli_mkpfs_main()",
        "    fahre('pack', 'folder', 'quelle', 'exfat_in_pfs.ffpfsc')",
        "    fahre('pack', 'folder', 'quelle', 'innen.ffpfs', '--raw',",
        "          '--no-compress', '--no-adjust-output-file-extension')",
        "    fahre('pack', 'file', 'innen.ffpfs', 'pfs_in_pfs.ffpfsc')",
        "    for name in ('exfat_in_pfs.ffpfsc', 'pfs_in_pfs.ffpfsc'):",
        "        with contextlib.redirect_stdout(io.StringIO()):",
        "            i = verify_pfs_image(Path(name))",
        "        print('%s %d %d' % (",
        "            name.split('.')[0],",
        "            len(list(getattr(i, 'errors', []) or [])),",
        "            len(list(getattr(i, 'warnings', []) or []))))",
        "finally:",
        "    os.chdir(vorher)",
        "    shutil.rmtree(ordner, ignore_errors=True)",
    ))

    @classmethod
    def setUpClass(cls) -> None:
        lauf = _im_unterprozess(_engine_ordner()[0], cls.SKRIPT)
        if lauf.returncode != 0:
            raise unittest.SkipTest(
                "Die Probecontainer liessen sich nicht bauen: "
                + lauf.stderr[-600:])
        cls.gemessen = {}
        for zeile in lauf.stdout.splitlines():
            teile = zeile.split()
            if len(teile) == 3 and teile[1].isdigit():
                cls.gemessen[teile[0]] = (int(teile[1]), int(teile[2]))

    def test_exfat_in_pfs_bekommt_keine_falschen_warnungen(self) -> None:
        """Die Vorgabe-Bauform. Vor dem 03.09.2026 waren es drei."""
        self.assertIn("exfat_in_pfs", self.gemessen)
        fehler, warnungen = self.gemessen["exfat_in_pfs"]
        self.assertEqual(0, fehler)
        self.assertEqual(
            0, warnungen,
            "Die Pruefliste laeuft wieder ueber die PFS-Ebene eines "
            "exFAT-Containers. Fehlt _pfs_wraps_single_exfat in pfs.py?")

    def test_die_pruefliste_laeuft_ueberhaupt_noch(self) -> None:
        """Die Gegenprobe.

        Ein PFS-in-PFS traegt ebenfalls genau einen Datei-Inode - nur
        eben einen PFS statt eines exFAT. Hier muss die Pruefliste
        anschlagen. Tut sie es nicht, ist sie nicht praezisiert,
        sondern abgeschaltet.

        Dass sie das auch bei vollstaendiger Quelle tut, ist ein
        Mangel der Vorlage und fuer deren Entwickler vermerkt; siehe
        ``MkPFS-1.0.0/UPSTREAM.md``.
        """
        self.assertIn("pfs_in_pfs", self.gemessen)
        _fehler, warnungen = self.gemessen["pfs_in_pfs"]
        self.assertGreater(
            warnungen, 0,
            "Die PS5-Pruefliste meldet gar nichts mehr - dann prueft "
            "sie auch dort nicht, wo sie soll.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
