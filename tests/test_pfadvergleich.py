# -*- coding: utf-8 -*-
"""``pfadvergleich``: dieselbe Datei auch in anderer Schreibung erkennen (Gesamtpruefung 14.11.2026, Befund S-A).

Nachgestellt wird macOS (APFS ohne Gross/Klein-Unterscheidung) auf NTFS: ``os.path.normcase`` wird durch die POSIX-Fassung ersetzt,
die nichts faltet - das Dateisystem darunter unterscheidet Gross/Klein trotzdem nicht. So verhielt sich der Konverter unter macOS
und auf exFAT unter Linux: ``Spiel.FFPKG`` und ``Spiel.ffpkg`` galten als verschieden, und der Ueberschreib-Zweig loeschte die Quelle.
"""
from __future__ import annotations

import os
import posixpath
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import pfadvergleich as pv            # noqa: E402
from ps5_validator.utils import quelle_loeschen as ql          # noqa: E402

_WIE_MACOS = mock.patch("os.path.normcase", posixpath.normcase)


def _faltet_das_dateisystem(ordner: str) -> bool:
    probe = os.path.join(ordner, "GrossKlein.probe")
    Path(probe).write_bytes(b"1")
    try:
        return os.path.exists(os.path.join(ordner, "grossklein.PROBE"))
    finally:
        os.remove(probe)


class _Ablage(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.wurzel = os.path.join(tmp.name, "arbeit")
        os.makedirs(self.wurzel)
        if not _faltet_das_dateisystem(self.wurzel):
            self.skipTest("Dieses Dateisystem unterscheidet Gross/Klein - der Fall ist hier nicht nachstellbar")


class GleicherOrtTests(_Ablage):
    def test_andere_schreibung_ist_dieselbe_datei(self) -> None:
        quelle = os.path.join(self.wurzel, "Spiel.FFPKG")
        Path(quelle).write_bytes(b"q")
        with _WIE_MACOS:
            self.assertNotEqual(os.path.normcase(quelle), os.path.normcase(os.path.join(self.wurzel, "Spiel.ffpkg")))
            self.assertTrue(pv.gleicher_ort(quelle, os.path.join(self.wurzel, "Spiel.ffpkg")))

    def test_zwei_dateien_sind_verschieden(self) -> None:
        """Gegenprobe: zwei echte Dateien."""
        a = os.path.join(self.wurzel, "a.ffpkg")
        b = os.path.join(self.wurzel, "b.ffpkg")
        Path(a).write_bytes(b"a")
        Path(b).write_bytes(b"b")
        with _WIE_MACOS:
            self.assertFalse(pv.gleicher_ort(a, b))

    def test_fehlt_eine_datei_entscheidet_der_text(self) -> None:
        a = os.path.join(self.wurzel, "a.ffpkg")
        Path(a).write_bytes(b"a")
        self.assertTrue(pv.gleicher_ort(a, a))
        self.assertFalse(pv.gleicher_ort(a, os.path.join(self.wurzel, "fehlt.ffpkg")))
        self.assertFalse(pv.gleicher_ort("", a))

    def test_dateinummer_null_zaehlt_nicht(self) -> None:
        """Manche Netzlaufwerke melden fuer jede Datei die Nummer 0 - dann waere alles "dasselbe"."""
        a = os.path.join(self.wurzel, "a.ffpkg")
        b = os.path.join(self.wurzel, "b.ffpkg")
        Path(a).write_bytes(b"a")
        Path(b).write_bytes(b"b")
        null = SimpleNamespace(st_ino=0, st_dev=7)
        with mock.patch("os.stat", return_value=null):
            self.assertFalse(pv.gleicher_ort(a, b))


class LiegtInTests(_Ablage):
    def test_andere_schreibung_des_ordners(self) -> None:
        os.makedirs(os.path.join(self.wurzel, "Spiele", "Astro"))
        innen = os.path.join(self.wurzel, "spiele", "Astro", "eboot.bin")
        with _WIE_MACOS:
            self.assertTrue(pv.liegt_in(innen, os.path.join(self.wurzel, "Spiele")))
            self.assertTrue(pv.liegt_in(os.path.join(self.wurzel, "SPIELE"), os.path.join(self.wurzel, "Spiele")))

    def test_aehnlicher_name_liegt_nicht_darin(self) -> None:
        """Gegenprobe: ``Spiele2`` liegt nicht in ``Spiele``, auch nicht ueber die Dateinummer."""
        os.makedirs(os.path.join(self.wurzel, "Spiele"))
        os.makedirs(os.path.join(self.wurzel, "Spiele2", "x"))
        with _WIE_MACOS:
            self.assertFalse(pv.liegt_in(os.path.join(self.wurzel, "Spiele2", "x"), os.path.join(self.wurzel, "Spiele")))
        self.assertFalse(pv.liegt_in(os.path.join(self.wurzel, "Spiele2"), os.path.join(self.wurzel, "Spiele")))

    def test_nicht_vorhandener_ordner(self) -> None:
        self.assertFalse(pv.liegt_in(os.path.join(self.wurzel, "a", "b"), os.path.join(self.wurzel, "fehlt")))
        self.assertTrue(pv.liegt_in(os.path.join(self.wurzel, "a", "b"), os.path.join(self.wurzel, "a")))   # Text reicht
        self.assertFalse(pv.liegt_in("", self.wurzel))


@unittest.skipUnless(os.name == "nt", "Junctions und Klon-Fall nur unter Windows")
class WindowsTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.wurzel = tmp.name
        self.echt = os.path.join(self.wurzel, "Spiele")
        os.makedirs(self.echt)
        Path(self.echt, "Spiel.exfat").write_bytes(b"q")

    def _junction(self) -> str:
        import subprocess
        link = os.path.join(self.wurzel, "Verweis")
        erg = subprocess.run(["cmd", "/c", "mklink", "/J", link, self.echt], capture_output=True, text=True)
        if erg.returncode != 0 or not os.path.isdir(link):
            self.skipTest("Junction nicht anlegbar")
        self.addCleanup(lambda: os.path.isdir(link) and os.rmdir(link))
        return link

    def test_junction_ist_derselbe_ort(self) -> None:
        link = self._junction()
        self.assertTrue(pv.gleicher_ort(os.path.join(link, "Spiel.exfat"), os.path.join(self.echt, "Spiel.exfat")))
        self.assertTrue(pv.liegt_in(os.path.join(link, "neu", "x.bin"), self.echt))

    def test_reste_karte_bietet_die_quelle_nie_an(self) -> None:
        """R2-A1: Selbst-Ziel ueber eine Junction (oder in anderer Schreibung) - die Quelle stand als "Ergebnis" auf der Karte."""
        from ps5_validator.utils import reste_karte as rk
        link = self._junction()
        quelle = os.path.join(self.echt, "Spiel.exfat")
        ausgabe = os.path.join(link, "Spiel.exfat")
        self.assertTrue(rk.schuetzen(ausgabe, quelle))
        self.assertEqual([], rk.finden(ausgabe, quelle, zielordner=link))
        self.assertTrue(os.path.exists(quelle))

    def test_aliase_ueber_die_dateinummer(self) -> None:
        """R3-A1: realpath allein erkannte Hardlinks, ``\\\\?\\``-Pfade und ``\\\\localhost\\C$`` nicht - ein Selbst-Ziel ueber einen
        solchen Weg loeschte die Quelle vor dem Bau. Die Dateinummer gilt deshalb weiter mit."""
        a = os.path.join(self.echt, "Spiel.exfat")
        hart = os.path.join(self.wurzel, "Hardlink.exfat")
        try:
            os.link(a, hart)
        except OSError:
            self.skipTest("Hardlink nicht anlegbar")
        self.assertTrue(pv.gleicher_ort(a, hart))
        self.assertTrue(pv.gleicher_ort("\\\\?\\" + os.path.abspath(a), a))
        self.assertFalse(pv.gleicher_ort(a, os.path.join(self.wurzel, "fehlt.exfat")))

    def test_klone_gelten_im_zweifel_als_derselbe_ort(self) -> None:
        """Gleiche Seriennummer und Datei-ID (geklonte Datentraeger): Schutzfrage - im Zweifel derselbe Ort, dann wird daneben gebaut.
        Gegenprobe: zwei Dateien mit verschiedener Nummer sind verschieden."""
        a = os.path.join(self.echt, "Spiel.exfat")
        b = os.path.join(self.wurzel, "Klon.exfat")
        Path(b).write_bytes(b"q")
        gleich = SimpleNamespace(st_ino=4711, st_dev=99, st_mode=0o100644)
        with mock.patch("os.stat", return_value=gleich):
            self.assertTrue(pv.gleicher_ort(a, b))
        self.assertFalse(pv.gleicher_ort(a, b))

    def test_liegt_in_text_fragt_das_dateisystem_nicht(self) -> None:
        """R3-A4: Ein nicht erreichbares Netzlaufwerk blockiert realpath ~21 s - wo die Oberflaeche wartet, nur der Text."""
        with mock.patch("os.path.realpath", side_effect=AssertionError("Dateisystem gefragt")) as realpath, \
                mock.patch("os.stat", side_effect=AssertionError("Dateisystem gefragt")) as stat:
            self.assertTrue(pv.liegt_in_text(os.path.join(self.echt, "x"), self.echt))
            self.assertFalse(pv.liegt_in_text(os.path.join(self.wurzel, "Spiele2", "x"), self.echt))
        realpath.assert_not_called()
        stat.assert_not_called()


class HauptfadenOhneDateisystemTests(unittest.TestCase):
    """R3-A4: Beim Start der Sammelkonvertierung (Hauptfaden) und beim Aufraeumen der Arbeitsordner nur der Textvergleich."""

    def test_die_beiden_stellen(self) -> None:
        text = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        self.assertIn("_passt = any(pfadvergleich.liegt_in_text(eintrag, src) for eintrag in _liste)", text)
        rumpf = text[text.index("    def _sweep_stale_temp_dirs("):]
        rumpf = rumpf[:rumpf.index("\n    def ", 10)]
        self.assertIn("pfadvergleich.liegt_in_text(pfad, eintrag.path)", rumpf)
        self.assertNotIn("pfadvergleich.liegt_in(", rumpf)


class QuelleLoeschenWieMacosTests(_Ablage):
    """``quelle_loeschen.pruefen`` vergleicht Quelle und Ergebnis ueber :mod:`pfadvergleich`."""

    def test_selbst_ziel_in_anderer_schreibung(self) -> None:
        quelle = os.path.join(self.wurzel, "Spiel.EXFAT")
        Path(quelle).write_bytes(b"x" * 9)
        stempel = ql.stempel_nehmen(quelle)
        with _WIE_MACOS:
            self.assertEqual("gleicher_pfad", ql.pruefen(quelle, os.path.join(self.wurzel, "Spiel.exfat"), stempel))

    def test_ergebnis_im_quellordner_in_anderer_schreibung(self) -> None:
        quelle = os.path.join(self.wurzel, "Spiel")
        os.makedirs(os.path.join(quelle, "aus"))
        Path(quelle, "eboot.bin").write_bytes(b"e")
        Path(quelle, "aus", "Spiel.exfat").write_bytes(b"e" * 9)
        ergebnis = os.path.join(self.wurzel, "SPIEL", "aus", "Spiel.exfat")
        with _WIE_MACOS:
            self.assertEqual("ergebnis_in_quelle", ql.pruefen(quelle, ergebnis, ql.stempel_nehmen(quelle)))

    def test_gegenprobe_getrennte_ordner(self) -> None:
        quelle = os.path.join(self.wurzel, "Spiel")
        os.makedirs(quelle)
        Path(quelle, "eboot.bin").write_bytes(b"e")
        os.makedirs(os.path.join(self.wurzel, "aus"))
        ergebnis = os.path.join(self.wurzel, "aus", "Spiel.exfat")
        Path(ergebnis).write_bytes(b"e" * 9)
        with _WIE_MACOS:
            self.assertEqual("", ql.pruefen(quelle, ergebnis, ql.stempel_nehmen(quelle)))


class GeschuetztTests(unittest.TestCase):
    """Befund A4: geschuetzte Namen klein verglichen, die Stammregel nur fuer Ordner."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.heim = os.path.join(tmp.name, "Heim")
        os.makedirs(os.path.join(self.heim, "Documents"))
        os.makedirs(os.path.join(self.heim, "Spiele"))

    def test_documents_auch_ohne_faltung(self) -> None:
        with _WIE_MACOS, mock.patch("os.path.expanduser", return_value=self.heim):
            self.assertTrue(ql._gefaehrlich(os.path.join(self.heim, "Documents")))
            self.assertFalse(ql._gefaehrlich(os.path.join(self.heim, "Spiele")))   # Gegenprobe

    def test_einhaengepunkte_sind_geschuetzt(self) -> None:
        """R2-A3: Ein USB-Stick unter Linux/macOS ist ein Ordner - ``/Volumes/STICK`` mit einem Dump in der Wurzel."""
        stick = os.path.join(self.heim, "Spiele")
        with mock.patch("os.path.ismount", side_effect=lambda p: os.path.normcase(p) == os.path.normcase(stick)):
            self.assertTrue(ql._gefaehrlich(stick))
        self.assertFalse(ql._gefaehrlich(stick), "Gegenprobe: derselbe Ordner ohne Einhaengung")

    def test_unterordner_der_sammelordner(self) -> None:
        for pfad in ("/home/bob", "/Users/Shared", "/Volumes/STICK", "/media/anna", "/mnt/usb", "/run/media/anna", "/home/bob/"):
            with self.subTest(pfad=pfad):
                self.assertTrue(ql.unter_sammelordner(pfad))
        for pfad in ("/home/bob/Spiele", "/Volumes/STICK/PPSA01234", "/opt/x", "/homes/x"):
            with self.subTest(pfad=pfad):
                self.assertFalse(ql.unter_sammelordner(pfad))

    def test_datei_direkt_in_der_wurzel_ist_keine_wurzel(self) -> None:
        wurzel_datei = os.path.join(os.path.abspath(os.sep), "Spiel.ffpkg")
        with mock.patch("os.path.isfile", return_value=True):
            self.assertFalse(ql._gefaehrlich(wurzel_datei))
        with mock.patch("os.path.isfile", return_value=False):                    # ein Ordner dort bleibt geschuetzt
            self.assertTrue(ql._gefaehrlich(wurzel_datei))


class EngineUeberschreibTests(_Ablage):
    """Der Weg, an dem der Befund gemessen wurde: ``_run_engine_thread`` mit Ziel = Quellordner, Quelle ``Spiel.FFPKG``."""

    def _lauf(self) -> "tuple[str, dict]":
        import PS5ImageConverter_Pro_FINAL_revised as APP

        src = os.path.join(self.wurzel, "Spiel.FFPKG")
        Path(src).write_bytes(b"ORIGINAL-FFPKG")
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._current_language = "de"
        gui.is_running = True
        gui._append_to_log = lambda *a, **k: None
        for name in ("_checkpoint_reste_raeumen", "_save_paths", "_save_runtime_checkpoint", "_set_status",
                     "_reset_ui_after_task", "_speicher_beobachtung_starten", "_speicher_beobachtung_beenden",
                     "_selbstziel_reste_entfernen", "_reste_nach_lauf", "_temp_reste_nach_aufgabe_abraeumen",
                     "_hauptfaden_planen", "_ampr_vor_dem_lauf_klaeren", "_backport_vor_dem_lauf_klaeren",
                     "_ampr_ng_vor_dem_lauf_hinweisen",
                     "_playgo_vor_dem_lauf_klaeren", "_dlc_vor_dem_lauf_klaeren", "_fake_vor_dem_lauf_klaeren",
                     "_quellbericht_ins_protokoll"):
            setattr(gui, name, lambda *a, **k: None)
        gui._snapshot_exit_cleanup_paths = lambda: set()
        gui._archiv_schatten_vorbereiten = lambda *a, **k: True
        gui._lauf_quelle_loeschen = False
        gui._get_selected_target_type = lambda: "ffpkg"
        gui._ausgabe_stamm = lambda s, standard, fmt: standard
        gui._ask_yesno_threadsafe = lambda *a, **k: True               # "Zieldatei existiert - ueberschreiben?" -> Ja
        gui._abschlusspruefung = lambda *a, **k: {}
        gui._write_task_report = lambda **k: ""
        gui._fehlergrund_ermitteln = lambda *a: ""
        gesehen: dict = {}

        def flexibel(mode, s, d):
            gesehen["quelle_beim_bau"] = os.path.exists(s)
            return False

        gui._run_flexible_conversion = flexibel
        with _WIE_MACOS:
            erwartet = gui._get_expected_output_path("ffpkg_to_ffpfsc", src, self.wurzel)
            self.assertNotEqual(os.path.basename(erwartet), "Spiel.FFPKG")      # Vorbedingung: andere Schreibung
            gui._run_engine_thread("ffpkg_to_ffpfsc", src, self.wurzel)
        return src, gesehen

    def test_die_quelle_bleibt(self) -> None:
        src, gesehen = self._lauf()
        self.assertTrue(gesehen.get("quelle_beim_bau"), "Die Quelle war schon vor dem Bau geloescht.")
        self.assertEqual(b"ORIGINAL-FFPKG", Path(src).read_bytes())

    def test_gegenprobe_mit_dem_alten_textvergleich(self) -> None:
        """Mit dem Vergleich von vorher (nur normcase) verschwindet die Quelle - der Test misst also den Befund."""
        alt = lambda a, b: os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))  # noqa: E731
        with mock.patch.object(pv, "gleicher_ort", alt):
            src, gesehen = self._lauf()
        self.assertFalse(gesehen.get("quelle_beim_bau"))
        self.assertFalse(os.path.exists(src))


if __name__ == "__main__":
    unittest.main(verbosity=2)
