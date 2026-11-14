# -*- coding: utf-8 -*-
"""Das Fenster "Abbild bearbeiten", Weg "Direkt aendern": ein ``.exfat``, ``.ffpkg`` oder ``.ffpfs`` wird ohne Entpacken in place
geaendert (14.11.2026).

Die Dateiarbeit hat ihre eigene Testdatei (``test_exfat_bearbeiten``). Hier wird geprueft, was das Fenster daraus macht: Oeffnen mit
Rueckfrage, Baum aus dem Abbild, Aenderungen im Speicher, "Aenderungen anwenden" im Hintergrund, Abweisung ohne Platz, Rueckspielen
eines liegengebliebenen Journals, Verwerfen.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))
sys.path.insert(0, str(PROJEKT / "MkPFS-1.1.0"))

from mkpfs.exfat_writer import iter_exfat_image             # noqa: E402

from ps5_validator.ui import abbild_bearbeiten_fenster as fz   # noqa: E402
from ps5_validator.utils import exfat_bearbeiten as eb       # noqa: E402
from ps5_validator.utils import spielbaum as sb              # noqa: E402

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:   # noqa: BLE001
    TK_DA = False
    _WURZEL = None

CL = 65536


def _inh(name: str, n: int) -> bytes:
    stueck = hashlib.sha256(name.encode()).digest()
    return (stueck * (n // len(stueck) + 1))[:n]


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class DirektTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    @classmethod
    def tearDownClass(cls) -> None:
        zustand = getattr(_WURZEL, "_ablegen_admin_zustand", None)
        if zustand is not None and sys.platform == "win32":
            import ctypes
            user32 = ctypes.windll.user32
            user32.SetWindowLongPtrW.restype = ctypes.c_void_p
            user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
            for hwnd, vorher in zustand["alte"].items():
                user32.SetWindowLongPtrW(hwnd, -4, vorher)
            del _WURZEL._ablegen_admin_zustand

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="direkt_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.inhalt = {
            "eboot.bin": _inh("eboot", 3000),
            "sce_sys/param.json": b"{}",
            "data/gross.bin": _inh("gross", 5 * CL + 1),
            "data/mittel.pak": _inh("mittel", 2 * CL),
            "Media/video.bin": _inh("video", 3 * CL - 1),
        }
        ordner = os.path.join(self.tmp, "quelle")
        for rel, daten in self.inhalt.items():
            voll = os.path.join(ordner, *rel.split("/"))
            os.makedirs(os.path.dirname(voll), exist_ok=True)
            Path(voll).write_bytes(daten)
        self.bild = os.path.join(self.tmp, "Spiel.exfat")
        with open(self.bild, "wb") as fh:
            for stueck in iter_exfat_image(Path(ordner)):
                fh.write(stueck)
        patcher = mock.patch.object(self.app, "_get_runtime_temp_dir", return_value=self.tmp)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.win = self.haupt.abbild_bearbeiten_fenster.oeffnen(
            self.app, self.haupt.UI_SCHRIFT, self.haupt.MONO_SCHRIFT, self.haupt.pt)
        self.addCleanup(self._schliessen)
        self.f = self.win._bearbeiten

    def _schliessen(self) -> None:
        try:
            self.f._direkt_schliessen()
            self.win.destroy()
        except tk.TclError:
            pass

    def oeffnen(self) -> None:
        self.f.bild_var.set(self.bild)
        with mock.patch.object(fz.messagebox, "askyesno", return_value=True):
            self.f._direkt_oeffnen()
        self.assertIsNotNone(self.f.direkt, "Direkt geoeffnet")

    def warten(self) -> None:
        """Die echte Hauptschleife, bis der Hintergrundfaden fertig gemeldet hat (``update()`` reicht fuer Faeden nicht)."""
        def pruefen() -> None:
            if not self.f.beschaeftigt:
                _WURZEL.quit()
            else:
                _WURZEL.after(30, pruefen)
        ids = [_WURZEL.after(30, pruefen), _WURZEL.after(30000, _WURZEL.quit)]
        try:
            _WURZEL.mainloop()
        finally:
            for i in ids:                                                  # ein liegengebliebener Zeitgeber wuerde die naechste Schleife beenden
                try:
                    _WURZEL.after_cancel(i)
                except tk.TclError:
                    pass

    def lesen(self) -> "dict[str, bytes]":
        with sb.ExfatBaum(self.bild) as baum:
            return {rel: b"".join(d.lesen()) for rel, d in baum.suchen().items()}

    # ---- Oeffnen ---------------------------------------------------------------------------------------------
    def test_nur_exfat_geht_direkt(self) -> None:
        andere = os.path.join(self.tmp, "Spiel.ffpfsc")
        Path(andere).write_bytes(b"x")
        self.f.bild_var.set(andere)
        with mock.patch.object(fz.messagebox, "showwarning") as warnung:
            self.f._direkt_oeffnen()
        warnung.assert_called_once()
        self.assertIsNone(self.f.direkt)

    def test_ohne_zustimmung_wird_nichts_geoeffnet(self) -> None:
        self.f.bild_var.set(self.bild)
        with mock.patch.object(fz.messagebox, "askyesno", return_value=False):
            self.f._direkt_oeffnen()
        self.assertIsNone(self.f.direkt)

    def test_die_rueckfrage_nennt_das_abbild_selbst(self) -> None:
        self.f.bild_var.set(self.bild)
        with mock.patch.object(fz.messagebox, "askyesno", return_value=False) as frage:
            self.f._direkt_oeffnen()
        text = frage.call_args[0][1]
        self.assertIn(self.bild, text)
        self.assertIn("nicht eine Kopie", text)

    def test_der_baum_kommt_aus_dem_abbild_und_die_knoepfe_sind_frei(self) -> None:
        self.oeffnen()
        alle = set(self.f.baum.get_children("")) | set(self.f.baum.get_children("data"))
        self.assertTrue({"eboot.bin", "data", "Media", "sce_sys", "data/gross.bin", "data/mittel.pak"} <= alle, alle)
        for knopf in self.f.aenderungs_knoepfe:
            self.assertNotEqual("disabled", str(knopf["state"]))
        self.assertEqual("disabled", str(self.f.speichern_knopf["state"]), "ohne Aenderung gibt es nichts anzuwenden")
        self.assertEqual("Änderungen anwenden", str(self.f.speichern_knopf["text"]))
        self.assertEqual("disabled", str(self.f.format_box["state"]))
        self.assertIn("Frei im Abbild", self.f.status_var.get())

    def test_ein_liegengebliebenes_journal_wird_beim_oeffnen_zurueckgespielt_und_gemeldet(self) -> None:
        original = Path(self.bild).read_bytes()
        a = eb.ExfatAbbild(self.bild)
        a.loeschen("data/gross.bin")
        a._metadaten_planen()
        stellen = []
        for offset, neu in a._plan.stellen:
            a._fh.seek(offset)
            stellen.append((offset, a._fh.read(len(neu))))
        for offset, neu in a._plan.stellen:                                 # das Abbild veraendern, als waere das Programm abgestuerzt
            a._fh.seek(offset)
            a._fh.write(neu)
        a._fh.flush()
        eb._journal_schreiben(eb.journal_pfad(self.bild), stellen)
        a.schliessen()
        self.assertNotEqual(original, Path(self.bild).read_bytes())
        self.oeffnen()
        self.assertEqual(original, Path(self.bild).read_bytes())
        self.assertFalse(os.path.exists(eb.journal_pfad(self.bild)))
        self.assertIn("rückgängig gemacht", self.f.status_var.get())

    # ---- Aendern und Anwenden --------------------------------------------------------------------------------
    def test_aendern_im_speicher_und_anwenden_im_hintergrund(self) -> None:
        self.oeffnen()
        vorher = Path(self.bild).read_bytes()
        neu = os.path.join(self.tmp, "neu.bin")
        Path(neu).write_bytes(_inh("neu", 2 * CL + 3))
        with mock.patch.object(fz.messagebox, "askyesno", return_value=True):
            self.f.baum.selection_set("data/gross.bin")
            self.f._loeschen()
        self.assertEqual(vorher, Path(self.bild).read_bytes(), "bis zum Anwenden bleibt die Datei, wie sie ist")
        self.assertFalse(self.f.baum.exists("data/gross.bin"), "der Baum zeigt schon den neuen Stand")
        self.f.baum.selection_set("data")
        with mock.patch.object(fz.filedialog, "askopenfilenames", return_value=(neu,)):
            self.f._hinzufuegen()
        self.assertTrue(self.f.baum.exists("data/neu.bin"))
        self.f.baum.selection_set("data/mittel.pak")
        with mock.patch.object(fz.simpledialog, "askstring", return_value="umbenannt.pak"):
            self.f._umbenennen()
        self.assertTrue(self.f.baum.exists("data/umbenannt.pak"))
        self.assertEqual(3, self.f.direkt_offen)
        self.assertNotEqual("disabled", str(self.f.speichern_knopf["state"]))
        self.assertTrue(self.f._hat_ungespeichertes())
        with mock.patch.object(fz.messagebox, "showinfo"):
            self.f._speichern()
            self.assertTrue(self.f.beschaeftigt)
            self.warten()
        self.assertFalse(self.f.beschaeftigt)
        self.assertEqual(0, self.f.direkt_offen)
        erwartet = dict(self.inhalt)
        del erwartet["data/gross.bin"]
        erwartet["data/umbenannt.pak"] = erwartet.pop("data/mittel.pak")
        erwartet["data/neu.bin"] = _inh("neu", 2 * CL + 3)
        self.assertEqual(erwartet, self.lesen())
        self.assertFalse(os.path.exists(eb.journal_pfad(self.bild)))
        with eb.ExfatAbbild(self.bild) as a:
            self.assertEqual([], a.pruefen())

    def test_ohne_platz_wird_abgewiesen_und_nichts_vorgemerkt(self) -> None:
        self.oeffnen()
        gross = os.path.join(self.tmp, "riesig.bin")
        Path(gross).write_bytes(_inh("riesig", 4 * CL))
        self.f.baum.selection_set("data")
        with mock.patch.object(fz.filedialog, "askopenfilenames", return_value=(gross,)), \
                mock.patch.object(fz.messagebox, "showerror") as fehler:
            self.f._hinzufuegen()
        fehler.assert_called_once()
        self.assertIn("nicht genug Platz", fehler.call_args[0][1])
        self.assertIn("Entpacken", fehler.call_args[0][1])
        self.assertEqual(0, self.f.direkt_offen)
        self.assertFalse(self.f._hat_ungespeichertes())

    def test_ein_vergebener_name_wird_abgewiesen(self) -> None:
        self.oeffnen()
        self.f.baum.selection_set("data/mittel.pak")
        with mock.patch.object(fz.simpledialog, "askstring", return_value="GROSS.BIN"), \
                mock.patch.object(fz.messagebox, "showerror") as fehler:
            self.f._umbenennen()
        fehler.assert_called_once()
        self.assertEqual(0, self.f.direkt_offen)

    def test_neuer_ordner_und_ersetzen(self) -> None:
        self.oeffnen()
        ersatz = os.path.join(self.tmp, "ersatz.bin")
        Path(ersatz).write_bytes(b"kurz")
        self.f.baum.selection_set("data/gross.bin")
        with mock.patch.object(fz.filedialog, "askopenfilename", return_value=ersatz):
            self.f._ersetzen()
        self.f.baum.selection_set("Media")
        with mock.patch.object(fz.simpledialog, "askstring", return_value="Saves"):
            self.f._neuer_ordner()
        self.assertTrue(self.f.baum.exists("Media/Saves"))
        with mock.patch.object(fz.messagebox, "showinfo"):
            self.f._speichern()
            self.warten()
        gelesen = self.lesen()
        self.assertEqual(b"kurz", gelesen["data/gross.bin"])
        with sb.ExfatBaum(self.bild) as baum:
            baum.dateien()
            self.assertIn("Media/Saves", baum.ordner())

    def test_eboot_und_param_sind_auch_direkt_geschuetzt(self) -> None:
        """Wie im Weg ueber den Arbeitsordner: nicht loeschen, nicht umbenennen - auch nicht den Ordner, der sie enthaelt."""
        self.oeffnen()
        for rel, art in (("eboot.bin", "_loeschen"), ("sce_sys/param.json", "_loeschen"), ("sce_sys", "_loeschen"),
                         ("eboot.bin", "_umbenennen"), ("sce_sys", "_umbenennen")):
            with self.subTest(rel=rel, art=art):
                self.f.baum.selection_set(rel)
                with mock.patch.object(fz.messagebox, "showerror") as fehler, \
                        mock.patch.object(fz.messagebox, "askyesno", return_value=True) as frage, \
                        mock.patch.object(fz.simpledialog, "askstring", return_value="anders") as name:
                    getattr(self.f, art)()
                fehler.assert_called_once()
                frage.assert_not_called()
                name.assert_not_called()
                self.assertEqual(0, self.f.direkt_offen)
        self.f.baum.selection_set("eboot.bin")
        ersatz = os.path.join(self.tmp, "gepatcht.bin")
        Path(ersatz).write_bytes(b"\x7fELF gepatcht")
        with mock.patch.object(fz.filedialog, "askopenfilename", return_value=ersatz):
            self.f._ersetzen()
        self.assertEqual(1, self.f.direkt_offen, "Ersetzen bleibt erlaubt (gepatchte eboot.bin)")

    def test_ein_ordner_kann_nicht_ersetzt_werden(self) -> None:
        self.oeffnen()
        self.f.baum.selection_set("data")
        with mock.patch.object(fz.messagebox, "showinfo") as info, \
                mock.patch.object(fz.filedialog, "askopenfilename") as dialog:
            self.f._ersetzen()
        info.assert_called_once()
        dialog.assert_not_called()

    # ---- Verwerfen und Wechsel -------------------------------------------------------------------------------
    def test_schliessen_mit_vorgemerkten_aenderungen_fragt_und_verwirft(self) -> None:
        self.oeffnen()
        vorher = Path(self.bild).read_bytes()
        self.f.baum.selection_set("data/gross.bin")
        with mock.patch.object(fz.messagebox, "askyesno", return_value=True):
            self.f._loeschen()
        with mock.patch.object(fz.messagebox, "askyesno", return_value=False) as frage:
            self.f._schliessen()
        frage.assert_called_once()
        self.assertTrue(self.win.winfo_exists())
        with mock.patch.object(fz.messagebox, "askyesno", return_value=True):
            self.f._schliessen()
        self.assertEqual(vorher, Path(self.bild).read_bytes(), "Verworfene Aenderungen schreiben nichts")
        self.assertFalse(os.path.exists(eb.journal_pfad(self.bild)))

    def test_entpacken_beendet_den_direkten_zugriff(self) -> None:
        self.oeffnen()
        with mock.patch.object(fz, "aufgabe_starten", return_value=False):
            self.f._entpacken()
        self.assertIsNone(self.f.direkt)
        self.assertEqual(0, self.f.direkt_offen)

    def test_das_schliessen_des_fensters_gibt_die_datei_frei(self) -> None:
        self.oeffnen()
        self.win.destroy()
        os.rename(self.bild, self.bild + ".x")                              # unter Windows nur moeglich, wenn niemand die Datei offen hat
        os.rename(self.bild + ".x", self.bild)

    # ---- .ffpkg und .ffpfs (seit dem 14.11.2026) ---------------------------------------------------------------
    def _anderes_abbild(self, art: str) -> None:
        from ps5_validator.utils import abbild_strom, ufs2_schreiber
        liste = [(rel, len(d), (lambda d=d: iter([d]))) for rel, d in self.inhalt.items()]
        self.bild = os.path.join(self.tmp, "Spiel_%s.%s" % (len(os.listdir(self.tmp)), art))
        if art == "ffpkg":
            ufs2_schreiber.planen(liste, (), profil=ufs2_schreiber.Ufs2Profil(65536, 65536, 4096, 0, 262144)).schreiben(self.bild)
        else:
            abbild_strom.ffpfs_schreiben(liste, self.bild, block_size=CL)

    def _gelesen(self, art: str) -> "dict[str, bytes]":
        baum = sb.Ufs2Baum(self.bild) if art == "ffpkg" else sb.PfsBaum(self.bild)
        with baum:
            return {d.rel: b"".join(d.lesen(1 << 20)) for d in baum.dateien()}

    def test_ffpkg_und_ffpfs_lassen_sich_direkt_aendern(self) -> None:
        from ps5_validator.utils import abbild_direkt
        neu = os.path.join(self.tmp, "neu.bin")
        Path(neu).write_bytes(_inh("neu", 2 * CL + 3))
        for art, status in (("ffpkg", "Frei im Abbild"), ("ffpfs", "wächst bei Bedarf")):
            with self.subTest(art):
                self._anderes_abbild(art)
                self.oeffnen()
                self.assertEqual("." + art, self.f.format_var.get())
                self.assertIn(status, self.f.status_var.get())
                with mock.patch.object(fz.messagebox, "askyesno", return_value=True):
                    self.f.baum.selection_set("data/gross.bin")
                    self.f._loeschen()
                self.f.baum.selection_set("data")
                with mock.patch.object(fz.filedialog, "askopenfilenames", return_value=(neu,)):
                    self.f._hinzufuegen()
                self.f.baum.selection_set("data/mittel.pak")
                with mock.patch.object(fz.simpledialog, "askstring", return_value="umbenannt.pak"):
                    self.f._umbenennen()
                self.assertEqual(3, self.f.direkt_offen)
                with mock.patch.object(fz.messagebox, "showinfo"):
                    self.f._speichern()
                    self.warten()
                self.assertEqual(0, self.f.direkt_offen)
                self.f._direkt_schliessen()
                erwartet = dict(self.inhalt)
                del erwartet["data/gross.bin"]
                erwartet["data/umbenannt.pak"] = erwartet.pop("data/mittel.pak")
                erwartet["data/neu.bin"] = _inh("neu", 2 * CL + 3)
                self.assertEqual(erwartet, self._gelesen(art))
                editor = abbild_direkt.oeffnen(self.bild)
                try:
                    self.assertEqual([], editor.pruefen())
                finally:
                    editor.schliessen()

    def test_ein_abbild_mit_falschem_inhalt_wird_gemeldet(self) -> None:
        self.bild = os.path.join(self.tmp, "Kaputt.ffpkg")
        Path(self.bild).write_bytes(b"x" * 200_000)
        self.f.bild_var.set(self.bild)
        with mock.patch.object(fz.messagebox, "askyesno", return_value=True), \
                mock.patch.object(fz.messagebox, "showerror") as fehler:
            self.f._direkt_oeffnen()
        fehler.assert_called_once()
        self.assertIsNone(self.f.direkt)


class QuelltextTests(unittest.TestCase):
    def test_jede_aenderung_hat_einen_direkten_weg(self) -> None:
        text = Path(fz.__file__).read_text(encoding="utf-8")
        for name in ("loeschen", "umbenennen", "ersetzen", "hinzufuegen", "neuer_ordner"):
            with self.subTest(name=name):
                self.assertIn("return self._direkt_%s()" % name, text)
        self.assertIn("return self._direkt_anwenden()", text)


if __name__ == "__main__":
    unittest.main()
