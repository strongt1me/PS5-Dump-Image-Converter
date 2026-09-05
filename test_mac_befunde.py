# -*- coding: utf-8 -*-
"""Zwei Meldungen eines Mac-Anwenders vom 06.09.2026.

**Meldung 1 - der ganze Bildschirm fror beim ersten Start ein.** Der Hinweis
auf macOS App Translocation ist ein *modaler* Dialog mit ``parent=self.root``
und wird 1200 ms nach dem Start eingeplant. In dieser Zeit steht das
Wurzelfenster noch auf ``-alpha 0.0``; sichtbar wird es erst am Ende des
Startablaufs, und dazwischen liegt ein ``root.update()``, das alle faelligen
Auftraege abarbeitet.

Dauert der Aufbau laenger als 1200 ms, geht der Dialog dort auf, waehrend das
Fenster unsichtbar ist. Ohne gemerkte Geometrie ist es zugleich
bildschirmfuellend maximiert und hat den Fokus erzwungen - ein unsichtbares
Fenster liegt ueber allem und wartet auf einen Klick, den niemand sehen kann.
Der Hinweis erscheint nur bei Translokation, also genau beim ersten Start
einer frisch geladenen ``.app``; deshalb traf es den Anwender einmal.

**Meldung 2 - die Konsole stuerzte mit einer Kernel-Panic ab**, nachdem auf
dem Mac ein .ffpfsc gebaut worden war. Der Lauf selbst meldete nichts. Eine
mac-eigene Ursache liess sich nicht finden - der Bauweg hat keine einzige
Plattformweiche -, wohl aber drei stille Luecken im exFAT-Weg, den die
Vorgabe-Bauform nimmt. Der rohe PFS-Weg faengt alle drei laut ab:

* Eine Quelldatei, die beim Lesen weniger liefert als ihr ``st_size`` sagte,
  wurde mit Nullen aufgefuellt. Gemessen: 200 000 Nullen mitten im
  eboot.bin, Abbild exakt gleich gross, keine Meldung. Fuer den SELF-Lader
  der Konsole ist das eine Segmenttabelle, die in Nullen zeigt - und der
  Lader sitzt im Kernel.
* Nicht-ASCII-Namen liefen durch. ``_upcase_ascii`` ist genau das, was der
  Name sagt, und der NameHash passt dann nicht zur Up-Case-Tabelle der
  Konsole. macOS liefert Namen zerlegt (NFD), Windows zusammengesetzt.
* Symlinks wurden stillschweigend verworfen. Ein Dump ueber ``rsync -a``,
  eine ``.dmg`` oder ein SMB-Laufwerk kann welche tragen.

Dazu kam, dass **ab Werk gar nichts nachgeprueft wurde**: Der exFAT-Zweig
fragte nur ``args.verify`` ab, waehrend ``--verify-structure`` per Vorgabe
auf True steht - der Schalter wurde dort nie ausgewertet.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))
sys.path.insert(0, str(PROJEKT / "MkPFS-1.0.0"))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("mac_befunde")

from mkpfs import exfat_writer as ew                        # noqa: E402
import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
import tkinter as tk                                        # noqa: E402


def _dump(wurzel: Path) -> Path:
    """Ein Dump, wie ihn das Programm erwartet."""
    quelle = wurzel / "dump"
    (quelle / "sce_sys").mkdir(parents=True)
    (quelle / "sce_sys" / "param.json").write_bytes(b'{"titleId":"TEST00000"}')
    (quelle / "eboot.bin").write_bytes(b"E" * 300_000)
    return quelle


class _KurzeDatei:
    """Ein Dateiobjekt, das frueher aufhoert, als seine Groesse verspricht."""

    def __init__(self, fh, grenze: int) -> None:
        self._fh, self._grenze, self._gelesen = fh, grenze, 0

    def read(self, menge: int = -1) -> bytes:
        if self._gelesen >= self._grenze:
            return b""
        rest = self._grenze - self._gelesen
        stueck = self._fh.read(rest if menge < 0 else min(menge, rest))
        self._gelesen += len(stueck)
        return stueck

    def __enter__(self):
        return self

    def __exit__(self, *_fehler):
        self._fh.close()


class ExfatSchreiberTests(unittest.TestCase):
    """Der exFAT-Weg muss so laut sein wie der rohe PFS-Weg."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mac_befund_")
        self.quelle = _dump(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def _bauen(self) -> bytes:
        return b"".join(ew.iter_exfat_image(self.quelle))

    def test_ein_heiler_baum_geht_durch(self):
        """Die Vorbedingung - sonst sagten die uebrigen Tests nichts aus."""
        abbild = self._bauen()
        self.assertGreater(len(abbild), 0)
        # Nicht die "E" im ganzen Abbild zaehlen - Verzeichniseintraege
        # tragen ebenfalls welche. Gefragt ist der zusammenhaengende Block.
        stelle = abbild.find(b"E" * 4096)
        self.assertGreater(stelle, 0)
        laenge = len(abbild[stelle:]) - len(abbild[stelle:].lstrip(b"E"))
        self.assertEqual(300_000, laenge)

    def test_eine_kurz_gelesene_datei_wird_abgewiesen(self):
        echt = Path.open

        def haken(selbst, *args, **kwargs):
            fh = echt(selbst, *args, **kwargs)
            return _KurzeDatei(fh, 100_000) if selbst.name == "eboot.bin" else fh

        with mock.patch.object(Path, "open", haken):
            with self.assertRaises(ew.ExfatBuildError) as fehler:
                self._bauen()
        self.assertIn("300000", str(fehler.exception))
        self.assertIn("100000", str(fehler.exception))

    def test_der_alte_zustand_waere_still_gewesen(self):
        """Der Beleg fuer die Schwere - nicht fuer das Verhalten.

        Ohne diese Gegenrechnung stuende oben nur, dass jetzt eine Ausnahme
        kommt, nicht warum das noetig war: Das Abbild blieb exakt gleich
        gross, und die fehlenden Bytes standen als Nullen im eboot.bin.
        """
        heil = self._bauen()
        stelle = heil.find(b"E" * 4096)
        self.assertGreater(stelle, 0)
        # So sah der Bereich vor dem Fix aus: gleiche Laenge, ein Drittel
        # Inhalt, zwei Drittel Nullen.
        nachgebaut = heil[:stelle] + b"E" * 100_000 + bytes(200_000) \
            + heil[stelle + 300_000:]
        self.assertEqual(len(heil), len(nachgebaut),
                         "Die Groesse haette es nie verraten")
        self.assertEqual(200_000, nachgebaut[stelle:stelle + 300_000].count(b"\x00"))

    def test_ein_nfd_name_wird_abgewiesen(self):
        # Genau die Form, in der macOS Namen liefert: ASCII plus
        # kombinierendes Zeichen.
        (self.quelle / "Café.bin").write_bytes(b"x")
        with self.assertRaises(ew.ExfatBuildError) as fehler:
            self._bauen()
        self.assertIn("non-ASCII", str(fehler.exception))

    @unittest.skipUnless(hasattr(os, "symlink"), "keine Verweise moeglich")
    def test_ein_symlink_wird_abgewiesen(self):
        try:
            os.symlink(self.quelle / "eboot.bin", self.quelle / "verweis.bin")
        except (OSError, NotImplementedError) as exc:
            self.skipTest("Verweise hier nicht anlegbar: %s" % exc)
        with self.assertRaises(ew.ExfatBuildError) as fehler:
            self._bauen()
        self.assertIn("symlink", str(fehler.exception).lower())

    def test_die_fehlerklasse_ist_ein_runtimeerror(self):
        # Aufrufer, die breit fangen, sollen weiter greifen - genau wie bei
        # pfs.BuildError, das ebenfalls davon erbt.
        self.assertTrue(issubclass(ew.ExfatBuildError, RuntimeError))


class NachpruefungTests(unittest.TestCase):
    """Ab Werk lief nach dem Packen keine einzige Kontrolle."""

    def test_der_exfat_zweig_fragt_nicht_mehr_nur_nach_verify(self):
        """Ueber den Syntaxbaum der Funktion, nicht ueber die ganze Datei."""
        import ast
        import io as _io
        with _io.open(PROJEKT / "MkPFS-1.0.0" / "mkpfs" / "cli.py",
                      "rb") as fh:
            baum = ast.parse(fh.read().decode("utf-8"))
        knoten = next(k for k in ast.walk(baum)
                      if isinstance(k, ast.FunctionDef)
                      and k.name == "_run_exfat_pack")
        rufe = {k.func.id for k in ast.walk(knoten)
                if isinstance(k, ast.Call) and isinstance(k.func, ast.Name)}
        self.assertIn("_resolve_pack_verification_mode", rufe,
                      "Der exFAT-Zweig wertet --verify-structure nicht aus")

    def test_die_pruefstufe_schnell_gibt_keine_schalter_mit(self):
        """Das ist gewollt - und erst dadurch wirkt die mkpfs-Vorgabe.

        Solange der exFAT-Zweig sie ignorierte, hiess "schnell" in
        Wahrheit "gar nicht".
        """
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui.mkpfs_verify = "schnell"
        self.assertEqual([], gui._mkpfs_pruef_argumente())

    def test_die_stufe_aus_schaltet_wirklich_ab(self):
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui.mkpfs_verify = "aus"
        self.assertEqual(["--no-verify-structure"], gui._mkpfs_pruef_argumente())

    def test_der_hilfetext_stimmt_jetzt(self):
        from ps5_validator.utils import i18n
        text = i18n.STRINGS["verify.hint"]["de"]
        self.assertIn("prüft die Struktur", text)


class TranslokationsHinweisTests(unittest.TestCase):
    """Der modale Hinweis darf nicht am unsichtbaren Fenster haengen."""

    def _gui(self, sichtbar: bool, alpha: float):
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._t = lambda s, **kw: s
        self.geplant: list[int] = []

        class _Fenster:
            def winfo_viewable(_s):
                return 1 if sichtbar else 0

            def attributes(_s, name, *wert):
                if name == "-alpha":
                    return alpha
                raise tk.TclError(name)

            def after(_s, ms, rueckruf):
                self.geplant.append(ms)

        gui.root = _Fenster()
        return gui

    def test_am_sichtbaren_fenster_kommt_der_hinweis(self):
        gui = self._gui(sichtbar=True, alpha=1.0)
        with mock.patch.object(APP.messagebox, "showwarning") as warnung:
            gui._macos_translokation_hinweis_zeigen()
        warnung.assert_called_once()
        self.assertEqual([], self.geplant, "Es wurde unnoetig gewartet")

    def test_am_durchsichtigen_fenster_wartet_er(self):
        """Der Kern: alpha 0.0 heisst unsichtbar, auch wenn Tk es
        als 'viewable' meldet."""
        gui = self._gui(sichtbar=True, alpha=0.0)
        with mock.patch.object(APP.messagebox, "showwarning") as warnung:
            gui._macos_translokation_hinweis_zeigen()
        warnung.assert_not_called()
        self.assertEqual([250], self.geplant)

    def test_am_nicht_abgebildeten_fenster_wartet_er_auch(self):
        gui = self._gui(sichtbar=False, alpha=1.0)
        with mock.patch.object(APP.messagebox, "showwarning") as warnung:
            gui._macos_translokation_hinweis_zeigen()
        warnung.assert_not_called()
        self.assertEqual([250], self.geplant)

    def test_er_wartet_nicht_ewig(self):
        gui = self._gui(sichtbar=False, alpha=0.0)
        with mock.patch.object(APP.messagebox, "showwarning") as warnung:
            gui._macos_translokation_hinweis_zeigen(
                versuch=APP.PS5ConverterGUI._MACOS_HINWEIS_VERSUCHE)
        warnung.assert_not_called()
        self.assertEqual([], self.geplant, "Er plant sich endlos neu ein")

    def test_ohne_alpha_unterstuetzung_kommt_er_trotzdem(self):
        """Auf Systemen ohne -alpha gibt es das Problem nicht."""
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._t = lambda s, **kw: s

        class _Fenster:
            def winfo_viewable(_s):
                return 1

            def attributes(_s, *_a):
                raise tk.TclError("-alpha nicht unterstuetzt")

            def after(_s, *_a):
                raise AssertionError("haette nicht warten duerfen")

        gui.root = _Fenster()
        with mock.patch.object(APP.messagebox, "showwarning") as warnung:
            gui._macos_translokation_hinweis_zeigen()
        warnung.assert_called_once()

    def test_der_einplaner_ruft_die_wartende_fassung(self):
        """Nicht mehr die Messagebox unmittelbar - sonst waere alles umsonst."""
        import ast
        import io as _io
        with _io.open(APP.__file__, "rb") as fh:
            baum = ast.parse(fh.read().decode("utf-8"))
        knoten = next(k for k in ast.walk(baum)
                      if isinstance(k, ast.FunctionDef)
                      and k.name == "_macos_translokation_melden")
        # Der Rueckruf wird als Attribut uebergeben, nicht aufgerufen - also
        # nach Attributnamen suchen und nicht nach Aufrufen.
        namen = {k.attr for k in ast.walk(knoten) if isinstance(k, ast.Attribute)}
        self.assertIn("_macos_translokation_hinweis_zeigen", namen)
        self.assertNotIn("showwarning", namen)


if __name__ == "__main__":
    unittest.main(verbosity=2)
