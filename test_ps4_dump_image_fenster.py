# -*- coding: utf-8 -*-
"""Das Fenster „PS4 PKG Dump & Image Converter“ (``ps5_validator/ui/ps4_dump_image.py``), seit 07.10.2026.

Es ersetzt „PS4 PKG -> OTA“ und „PS4 PKG -> ffpfsc“. Die Arbeit hinter den Knoepfen pruefen
``test_ps4_abbild.py`` und ``test_ps4_fortschritt.py``; hier geht es um das Fenster selbst: Es oeffnet und
schliesst sauber, ein PS5-Titel bekommt beim Update-Suchen den Hinweis statt einer Netzanfrage, ein
bereits entpacktes Spiel wird als Quelle erkannt.

Sonys Update-Adresse antwortet mit dem PS4-Verfahren fuer 16 gemessene PPSA-Titel mit 404 (die Gegenprobe
mit CUSA03877: 200), ein Verfahren fuer die PS5 ist oeffentlich nirgends belegt - das Fenster fragt dort
deshalb nicht, sondern sagt es.
"""
from __future__ import annotations

import os
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

try:
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover - ohne Anzeige
    TK_DA = False
    _WURZEL = None

from ps5_validator.ui import ps4_dump_image as fenster_modul   # noqa: E402
from ps5_validator.utils import ps4_abbild as ab               # noqa: E402
from ps5_validator.utils.i18n import STRINGS                   # noqa: E402


class _Probe:
    """Nur die Teile des Fensters, die ``_update_online`` anfasst."""

    def __init__(self, title_id: str) -> None:
        self.spiel = ab.Spiel(title_id=title_id, titel="X")
        self.status: list[str] = []
        self.log: list[str] = []
        self._z: dict = {}
        self.t = lambda schluessel, **w: STRINGS[schluessel]["de"].format(**w)

    def _frei(self) -> bool:
        return True

    def _gewaehlt(self):
        return [self.spiel]

    def _status(self, text: str) -> None:
        self.status.append(text)

    def _protokoll(self, text: str) -> None:
        self.log.append(text)

    def _warnung(self, *a, **k) -> None:
        raise AssertionError("keine Warnung erwartet")

    def _knoepfe_pruefen(self) -> None:
        pass


class Ps5UpdateTests(unittest.TestCase):

    def test_bei_ps5_wird_nicht_im_netz_gefragt(self) -> None:
        f = _Probe("PPSA01284")
        with mock.patch.object(fenster_modul.upd, "nachsehen") as netz, \
                mock.patch.object(fenster_modul.threading, "Thread") as faden:
            fenster_modul.Ps4DumpImageFenster._update_online(f)   # type: ignore[arg-type]
        netz.assert_not_called()
        faden.assert_not_called()
        self.assertEqual(f.status, f.log)
        self.assertIn("PS5-Titel", f.log[0])

    def test_ps4_titel_fragen_weiter_im_netz(self) -> None:
        f = _Probe("CUSA03877")
        with mock.patch.object(fenster_modul.threading, "Thread") as faden:
            fenster_modul.Ps4DumpImageFenster._update_online(f)   # type: ignore[arg-type]
        faden.assert_called_once()
        self.assertTrue(f._z["update_laeuft"])
        self.assertNotIn("PS5-Titel", " ".join(f.log))

    def test_texte_sind_zweisprachig_und_nennen_den_grund(self) -> None:
        text = STRINGS["ps4ota.update_ps5_hinweis"]
        self.assertNotEqual(text["de"], text["en"])
        self.assertIn("PS5", text["en"])


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class FensterTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def _fenster(self):
        f = fenster_modul.oeffnen(self.app, self.haupt.UI_SCHRIFT, self.haupt.MONO_SCHRIFT, self.haupt.pt)
        self.addCleanup(lambda: f.win.winfo_exists() and f.win.destroy())
        _WURZEL.update()
        return f

    def test_titel_und_ein_einziges_fenster(self) -> None:
        f = self._fenster()
        self.assertEqual("PS4 PKG Dump & Image Converter", f.win.title())
        self.assertIs(f, fenster_modul.oeffnen(self.app, self.haupt.UI_SCHRIFT, self.haupt.MONO_SCHRIFT,
                                               self.haupt.pt))

    def test_die_formate_stehen_zur_wahl(self) -> None:
        f = self._fenster()
        self.assertEqual(set(ab.FORMATE), set(f._formate))

    def test_ein_entpacktes_spiel_laesst_nur_abbilder_zu(self) -> None:
        """Meldung 07.10.2026: Bei \"Entpacktes PS4-Spiel\" durfte \"Dump-Ordner\" gewaehlt werden."""
        f = self._fenster()
        f.format_var.set(f._formate[ab.FORMAT_DUMP])
        f.art_var.set(fenster_modul.QUELLE_DUMP)
        _WURZEL.update()
        werte = tuple(f.format_box.cget("values"))
        self.assertEqual({f._formate[ab.FORMAT_FFPFSC], f._formate[ab.FORMAT_EXFAT]}, set(werte))
        self.assertEqual(f._formate[ab.FORMAT_FFPFSC], f.format_var.get(), "Ein ungueltiges Format wird ersetzt.")
        f.art_var.set(fenster_modul.QUELLE_ORDNER)
        self.assertEqual(set(ab.FORMATE), set(f._formate))
        self.assertEqual(len(f._formate), len(tuple(f.format_box.cget("values"))))

    def test_ein_druck_auf_einen_quellknopf_oeffnet_die_wahl(self) -> None:
        f = self._fenster()
        for art, dialog in ((fenster_modul.QUELLE_ORDNER, "askdirectory"), (fenster_modul.QUELLE_DATEIEN, "askopenfilenames"),
                            (fenster_modul.QUELLE_DUMP, "askdirectory")):
            with self.subTest(art=art), mock.patch.object(fenster_modul.filedialog, dialog, return_value="") as dlg:
                f.art_var.set(art)
                f._quelle_gewaehlt()
                dlg.assert_called_once()

    def test_die_gewaehlte_quelle_wird_gleich_eingelesen_ohne_eingabefeld(self) -> None:
        """Seit 07.10.2026 gibt es kein Pfadfeld mehr: Die Wahl im Dialog gilt und liest ein."""
        quelle = (PROJEKT / "ps5_validator" / "ui" / "ps4_dump_image.py").read_text(encoding="utf-8")
        self.assertNotIn("pw.Entry(pfad_reihe", quelle)
        f = self._fenster()
        f.art_var.set(fenster_modul.QUELLE_ORDNER)
        with tempfile.TemporaryDirectory() as tmp,                 mock.patch.object(fenster_modul.filedialog, "askdirectory", return_value=tmp),                 mock.patch.object(f, "_einlesen") as lesen:
            f._quelle_waehlen()
            lesen.assert_called_once()
            self.assertEqual(os.path.normpath(tmp), f.quelle_var.get())

    def test_die_quellknoepfe_rufen_die_wahl_auf(self) -> None:
        quelle = (PROJEKT / "ps5_validator" / "ui" / "ps4_dump_image.py").read_text(encoding="utf-8")
        self.assertIn("command=self._quelle_gewaehlt", quelle)

    def test_schliessen_setzt_das_programm_zurueck(self) -> None:
        f = self._fenster()
        f._schliessen()
        _WURZEL.update()
        self.assertIsNone(getattr(self.app, fenster_modul.FENSTER_ATTRIBUT, None))

    def test_ein_entpacktes_spiel_wird_als_quelle_erkannt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sfo = Path(tmp) / "sce_sys"
            sfo.mkdir()
            sys.path.insert(0, str(PROJEKT))
            from test_ps4_abbild import _sfo
            (sfo / "param.sfo").write_bytes(_sfo({"TITLE_ID": "CUSA00001", "TITLE": "Testspiel", "APP_VER": "01.05"}))
            f = self._fenster()
            f.art_var.set(fenster_modul.QUELLE_DUMP)
            f.quelle_var.set(tmp)
            f._einlesen()
            self.assertIn("CUSA00001", f.spiele)
            self.assertEqual(os.path.abspath(tmp), f.spiele["CUSA00001"].dump_ordner)
            self.assertEqual(("CUSA00001",), tuple(f.liste.get_children()))

    def test_ein_ordner_ohne_param_sfo_wird_gemeldet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            f = self._fenster()
            f.art_var.set(fenster_modul.QUELLE_DUMP)
            f.quelle_var.set(tmp)
            f._einlesen()
            self.assertEqual({}, f.spiele)
            self.assertEqual(STRINGS["ps4dib.dump_ohne_sfo"]["de"], f.status_var.get())


if __name__ == "__main__":
    unittest.main()
