# -*- coding: utf-8 -*-
"""Die Bauform: was zwischen Huelle und Spieldateien liegt.

Angelegt am 03.09.2026.

Ein Container kann auf zwei Arten entstehen, und beide sind gueltig:

* **exFAT im Container** - ein einziger ``pack folder``-Aufruf. Die Engine
  wickelt den Ordner in ein exFAT-Abbild und komprimiert es im selben
  Durchgang. Die Anleitung der Engine nennt das die stabilste Form fuer
  Spielsicherungen. Seit dem 03.09.2026 die Vorgabe.
* **PFS im Container** - erst ein rohes inneres PFS
  (``pack folder --raw --no-compress``), dann der aeussere Container darum
  (``pack file``). So hat dieses Programm bis dahin immer gebaut.

An 200 MB gemessen: 1,3 s gegen 6,3 s bei gleicher Ergebnisgroesse. Der
Unterschied ist das doppelte Schreiben - der zweistufige Weg legt das
innere PFS erst auf die Platte.

**Wie hier geprueft wird.** Nicht am Wortlaut des Quelltextes: Eine
Attrappe faengt die Argumente ab, mit denen das Programm die Engine
aufruft. Faellt eine dieser Pruefungen, hat sich die Sache geaendert, nicht
die Schreibweise.
"""
from __future__ import annotations

import pathlib
import sys
import tempfile
import importlib.util
import unittest

PROJEKT = pathlib.Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import PS5ImageConverter_Pro_FINAL_revised as APP
from ps5_validator.utils.i18n import BAUFORM_KEYS, STRINGS


def _gui(bauform: str) -> APP.PS5ConverterGUI:
    """Eine Programminstanz, deren Engine-Aufrufe mitgeschrieben werden.

    Die Attrappe legt die Zieldatei jedes Aufrufs an. Ohne das bricht der
    zweistufige Weg nach dem ersten Aufruf ab, weil er auf das innere PFS
    wartet - und die Messung zaehlte einen Aufruf statt zwei.
    """
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui.bauform = bauform
    gui.is_running = True
    gui.task_total_source_bytes = 1000
    gui._current_language = "de"
    gui._append_to_log = lambda *_a, **_k: None
    gui._save_runtime_checkpoint = lambda **_k: None
    gui._ensure_param_json = lambda _s: True
    gui._mkpfs_pruef_argumente = lambda: []
    gui._wait_for_pending_mkpfs_background = lambda _p: None
    gui._cleanup_stale_mkpfs_output = lambda _p: None
    gui._decide_pack_output_staging = lambda p: p
    gui._finalize_staged_pack_output = lambda p, _f: p
    gui._seed_preview_cache_from_source = lambda *_a: None
    gui._get_path_size = lambda _p: 1000
    gui._resolve_pack_profile = lambda *_a: {
        "profile": "Test", "size_gb": 1, "level": 9,
        "cpu": 4, "cores": 8, "block_size": 65536}
    gui._mkdtemp = lambda **_k: tempfile.mkdtemp()
    gui.aufrufe: list[list[str]] = []

    def ausfuehren(argumente, **_kwargs):
        gui.aufrufe.append(list(argumente))
        pathlib.Path(argumente[-1]).write_bytes(b"x")
        return True

    gui._execute_mkpfs = ausfuehren
    return gui


def _dump(ordner: pathlib.Path) -> pathlib.Path:
    """Legt das Mindeste an, das der Packweg vor sich sehen will."""
    quelle = ordner / "dump"
    (quelle / "sce_sys").mkdir(parents=True)
    (quelle / "eboot.bin").write_bytes(b"\x7fELF")
    return quelle


class Aufgabe1Tests(unittest.TestCase):
    """``_mode_pack_folder_mkpfs`` - der Weg von Aufgabe 1 und 6."""

    def _packen(self, bauform: str) -> APP.PS5ConverterGUI:
        with tempfile.TemporaryDirectory() as t:
            ordner = pathlib.Path(t)
            gui = _gui(bauform)
            ergebnis = gui._mode_pack_folder_mkpfs(
                str(_dump(ordner)), t, str(ordner / "ziel.ffpfsc"),
                10.0, 50.0, 90.0, lambda _p: None, lambda _s: None)
            self.assertTrue(ergebnis, "Der Packweg hat aufgegeben.")
            return gui

    def test_exfat_braucht_einen_einzigen_aufruf(self) -> None:
        gui = self._packen(APP.BAUFORM_EXFAT)
        self.assertEqual(1, len(gui.aufrufe),
                         "Erwartet ist ein Durchgang ohne Zwischendatei.")
        self.assertEqual(["pack", "folder"], gui.aufrufe[0][:2])

    def test_exfat_packt_nicht_roh(self) -> None:
        """Ohne ``--raw`` wickelt die Engine das exFAT selbst - genau darum geht es."""
        gui = self._packen(APP.BAUFORM_EXFAT)
        self.assertNotIn("--raw", gui.aufrufe[0])
        self.assertIn("--compress", gui.aufrufe[0])

    def test_exfat_meldet_einen_schritt(self) -> None:
        """Die Anzeige darf keine zweite Phase erwarten, die es nicht gibt."""
        gui = self._packen(APP.BAUFORM_EXFAT)
        self.assertEqual(1, gui.task_num_steps)

    def test_pfs_braucht_zwei_aufrufe(self) -> None:
        gui = self._packen(APP.BAUFORM_PFS)
        self.assertEqual(2, len(gui.aufrufe))
        self.assertEqual(["pack", "folder"], gui.aufrufe[0][:2])
        self.assertEqual(["pack", "file"], gui.aufrufe[1][:2])

    def test_pfs_packt_das_innere_roh_und_unkomprimiert(self) -> None:
        """Ohne --raw entstuende eine Ebene mehr, mit Kompression doppelt gepackt."""
        gui = self._packen(APP.BAUFORM_PFS)
        self.assertIn("--raw", gui.aufrufe[0])
        self.assertIn("--no-compress", gui.aufrufe[0])

    def test_pfs_komprimiert_erst_aussen(self) -> None:
        gui = self._packen(APP.BAUFORM_PFS)
        self.assertIn("--compress", gui.aufrufe[1])

    def test_pfs_meldet_zwei_schritte(self) -> None:
        gui = self._packen(APP.BAUFORM_PFS)
        self.assertEqual(2, gui.task_num_steps)

    def test_beide_wege_nennen_dieselbe_kompressionsstufe(self) -> None:
        """Die Bauform darf an der Stufe nichts aendern."""
        exfat = self._packen(APP.BAUFORM_EXFAT).aufrufe[0]
        pfs = self._packen(APP.BAUFORM_PFS).aufrufe[1]
        for argumente in (exfat, pfs):
            with self.subTest(aufruf=argumente[:2]):
                self.assertIn("--compression-level", argumente)
                self.assertEqual("9", argumente[argumente.index("--compression-level") + 1])


class QuellformTests(unittest.TestCase):
    """``_bauform_der_quelle`` - Aufgabe 7 packt zurueck, wie es hereinkam.

    Bis zum 03.09.2026 entstand dort immer PFS-in-PFS. Wer ein
    exFAT-in-PFS bearbeitete, bekam stillschweigend die andere Form.
    """

    def _gui_mit_befund(self, befund: dict) -> APP.PS5ConverterGUI:
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui.bauform = APP.BAUFORM_EXFAT
        modul = sys.modules["ps5_validator.modules.ffpfs_validator"]
        self._echt = modul.ermittle_bauform
        modul.ermittle_bauform = lambda _p: befund
        self.addCleanup(setattr, modul, "ermittle_bauform", self._echt)
        return gui

    @classmethod
    def setUpClass(cls) -> None:
        import ps5_validator.modules.ffpfs_validator  # noqa: F401

    def test_eine_exfat_quelle_kommt_als_exfat_zurueck(self) -> None:
        gui = self._gui_mit_befund({"bauform": "exfat"})
        self.assertEqual(APP.BAUFORM_EXFAT, gui._bauform_der_quelle("egal.ffpfsc"))

    def test_eine_pfs_quelle_kommt_als_pfs_zurueck(self) -> None:
        gui = self._gui_mit_befund({"bauform": "pfs"})
        self.assertEqual(APP.BAUFORM_PFS, gui._bauform_der_quelle("egal.ffpfsc"))

    def test_eine_fremde_bauform_faellt_auf_die_einstellung(self) -> None:
        """"flach", "ufs2" und "dreifach" sind keine der beiden Formen."""
        for fremd in ("flach", "ufs2", "dreifach", ""):
            with self.subTest(bauform=fremd):
                gui = self._gui_mit_befund({"bauform": fremd})
                self.assertEqual(gui.bauform, gui._bauform_der_quelle("egal.ffpfsc"))

    def test_ein_fehler_beim_ermitteln_faellt_auf_die_einstellung(self) -> None:
        """Die Datei kann weg sein - dann raten wir nicht."""
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui.bauform = APP.BAUFORM_PFS
        modul = sys.modules["ps5_validator.modules.ffpfs_validator"]
        echt = modul.ermittle_bauform

        def wirft(_pfad):
            raise OSError("Datei ist weg")

        modul.ermittle_bauform = wirft
        self.addCleanup(setattr, modul, "ermittle_bauform", echt)
        self.assertEqual(APP.BAUFORM_PFS, gui._bauform_der_quelle("weg.ffpfsc"))


class VorgabeTests(unittest.TestCase):
    """Was gilt, solange niemand etwas eingestellt hat."""

    def test_die_vorgabe_ist_exfat(self) -> None:
        self.assertEqual(APP.BAUFORM_EXFAT, APP.BAUFORM_VORGABE)

    def test_es_gibt_genau_zwei_formen(self) -> None:
        self.assertEqual([APP.BAUFORM_EXFAT, APP.BAUFORM_PFS],
                         [wert for _schluessel, wert in BAUFORM_KEYS])

    def test_beide_formen_haben_beschriftung_und_hinweis(self) -> None:
        """Der Hinweis steht neben der Auswahl - er soll die Wahl erklaeren."""
        for schluessel, wert in BAUFORM_KEYS:
            with self.subTest(bauform=wert):
                for name in (schluessel, f"bauform.{wert}.hint"):
                    eintrag = STRINGS.get(name)
                    self.assertIsNotNone(eintrag, f"{name} fehlt in der Textquelle.")
                    self.assertTrue(eintrag.get("de") and eintrag.get("en"))

    def test_die_beschriftung_der_gruppe_und_ihr_tooltip_gibt_es(self) -> None:
        for name in ("bauform.label", "bauform.tooltip"):
            with self.subTest(schluessel=name):
                eintrag = STRINGS.get(name)
                self.assertIsNotNone(eintrag)
                self.assertTrue(eintrag.get("de") and eintrag.get("en"))


class BeideOberflaechenTests(unittest.TestCase):
    """Die Wahl muss in beiden Fassungen ankommen."""

    def test_der_bedienzustand_fuehrt_sie(self) -> None:
        from ps5_validator.ui.bedienzustand import Bedienzustand

        self.assertTrue(hasattr(Bedienzustand(), "bauform_var"))

    @unittest.skipUnless(
        importlib.util.find_spec("ps5_validator.ui.wpf") is not None,
        "Diese Auslieferung bringt nur die Tk-Oberflaeche mit.")
    def test_das_wpf_fenster_nimmt_sie_entgegen(self) -> None:
        """Sonst zeigte die WPF-Fassung die Wahl nicht an."""
        import inspect

        from ps5_validator.ui.wpf.hauptfenster import Programmfenster
        from ps5_validator.ui.wpf.pfadkarte import Pfadkarte

        for klasse in (Programmfenster, Pfadkarte):
            with self.subTest(klasse=klasse.__name__):
                self.assertIn("bauformen",
                              inspect.signature(klasse.__init__).parameters)

    def test_die_tk_fassung_kennt_den_handler(self) -> None:
        for name in ("_on_bauform_changed", "_bauform_hinweis_setzen"):
            with self.subTest(name=name):
                self.assertTrue(callable(getattr(APP.PS5ConverterGUI, name, None)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
