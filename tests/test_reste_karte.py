# -*- coding: utf-8 -*-
"""Reste-Karte und Reihenfolge der Startdateien (nach Dump Forge, Nutzerwahl 13.11.2026)."""
from __future__ import annotations

import importlib.util
import os
import queue
import re
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("reste_karte")

from ps5_validator.utils import betriebsdiagnose as bd       # noqa: E402
from ps5_validator.utils import reste_karte as rk            # noqa: E402


def _lade():
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", ROOT / "PS5ImageConverter_Pro_FINAL_revised.py")
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


HAUPT = _lade()
GUI = HAUPT.PS5ConverterGUI
QUELLE = (ROOT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")


def _loeschen(pfad: str) -> bool:
    shutil.rmtree(pfad, ignore_errors=True)
    return not os.path.exists(pfad)


class _Basis(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ziel = Path(self._tmp.name) / "Ziel"
        self.ziel.mkdir()
        self.quelle = Path(self._tmp.name) / "Quelle" / "Spiel.exfat"
        self.quelle.parent.mkdir()
        self.quelle.write_bytes(b"q" * 100)


class FindenTests(_Basis):
    def test_ohne_ergebnis_gibt_es_keine_reste(self):
        self.assertEqual([], rk.finden(str(self.ziel / "Spiel.ffpfsc"), str(self.quelle), zielordner=str(self.ziel)))
        self.assertEqual([], rk.finden("", str(self.quelle)))

    def test_ein_unfertiges_abbild_wird_gefunden(self):
        (self.ziel / "Spiel.ffpfsc").write_bytes(b"x" * 1234)
        reste = rk.finden(str(self.ziel / "Spiel.ffpfsc"), str(self.quelle), zielordner=str(self.ziel))
        self.assertEqual(1, len(reste))
        self.assertEqual((rk.ART_ERGEBNIS, 1234, False), (reste[0].art, reste[0].bytes, reste[0].ordner))

    def test_ein_halber_spielordner_mit_inhalt(self):
        ordner = self.ziel / "Spiel"
        (ordner / "sce_sys").mkdir(parents=True)
        (ordner / "eboot.bin").write_bytes(b"e" * 10)
        (ordner / "sce_sys" / "param.json").write_bytes(b"{}")
        reste = rk.finden(str(ordner), str(self.quelle), zielordner=str(self.ziel))
        self.assertTrue(reste[0].ordner)
        self.assertEqual(12, reste[0].bytes)

    def test_teil_und_baudateien_daneben(self):
        for endung in (".teil", ".neu", ".part", ".partial"):
            (self.ziel / ("Spiel.exfat" + endung)).write_bytes(b"t" * 5)
        reste = rk.finden(str(self.ziel / "Spiel.exfat"), str(self.quelle), zielordner=str(self.ziel))
        self.assertEqual({".teil", ".neu", ".part", ".partial"}, {Path(r.pfad).suffix for r in reste})
        self.assertTrue(all(r.art == rk.ART_NEBEN for r in reste))

    def test_ein_ausdruecklich_benannter_zielpfad_gehoert_dem_anwender(self):
        (self.ziel / "Mein.ffpfsc").write_bytes(b"x")
        sonst = Path(self._tmp.name) / "anderswo"
        sonst.mkdir()
        self.assertEqual([], rk.finden(str(sonst / "Mein.ffpfsc"), str(self.quelle), zielordner=str(self.ziel)))

    def test_die_groesse_ist_begrenzt_durch_das_zeitbudget(self):
        ordner = self.ziel / "Gross"
        ordner.mkdir()
        for i in range(30):
            (ordner / ("f%d.bin" % i)).write_bytes(b"x" * 10)
        reste = rk.finden(str(ordner), str(self.quelle), zielordner=str(self.ziel), zeitbudget=-1.0)
        self.assertTrue(reste[0].mindestens)


class SchutzTests(_Basis):
    def test_die_quelle_selbst_wird_nie_angeboten(self):
        """Selbst-Ziel: .exfat -> .exfat im selben Ordner. Das Ergebnis ist die Quelle."""
        reste = rk.finden(str(self.quelle), str(self.quelle), zielordner=str(self.quelle.parent))
        self.assertEqual([], reste)

    def test_der_ordner_um_die_quelle_wird_nie_angeboten(self):
        spiel = self.ziel / "Spiel"
        (spiel / "sce_sys").mkdir(parents=True)
        (spiel / "eboot.bin").write_bytes(b"e")
        self.assertEqual([], rk.finden(str(self.ziel), str(spiel / "eboot.bin"), zielordner=str(self.ziel.parent)))

    def test_ein_ordner_der_quelle_wird_nie_angeboten(self):
        spiel = self.ziel / "Spiel"
        spiel.mkdir()
        (spiel / "Ergebnis").mkdir()
        self.assertEqual([], rk.finden(str(spiel / "Ergebnis"), str(spiel), zielordner=str(spiel)))

    def test_eine_neu_datei_neben_der_quelle_wird_angeboten_die_quelle_nicht(self):
        neu = Path(str(self.quelle) + ".neu")
        neu.write_bytes(b"n" * 9)
        reste = rk.finden(str(self.quelle), str(self.quelle), zielordner=str(self.quelle.parent))
        self.assertEqual([str(neu)], [r.pfad for r in reste])

    def test_schuetzen_im_einzelnen(self):
        self.assertTrue(rk.schuetzen("", "x"))
        self.assertTrue(rk.schuetzen(os.path.abspath(os.sep), "x"), "eine Laufwerkswurzel")
        self.assertFalse(rk.schuetzen(str(self.ziel / "a"), ""))
        self.assertTrue(rk.schuetzen(str(self.quelle), str(self.quelle)))
        self.assertTrue(rk.schuetzen(str(self.quelle.parent), str(self.quelle)))
        self.assertTrue(rk.schuetzen(str(self.quelle / "unter"), str(self.quelle)))
        self.assertFalse(rk.schuetzen(str(self.ziel / "a"), str(self.quelle)))

    def test_ein_gleich_beginnender_name_ist_kein_unterordner(self):
        self.assertFalse(rk.schuetzen(str(self.ziel / "Spiel2"), str(self.ziel / "Spiel")))
        self.assertFalse(rk.liegt_in(str(self.ziel / "Spiel2"), str(self.ziel / "Spiel")))


class EntfernenTests(_Basis):
    def test_entfernt_datei_und_ordner_und_laesst_die_quelle(self):
        datei = self.ziel / "Spiel.ffpfsc"
        datei.write_bytes(b"x")
        ordner = self.ziel / "Spiel"
        (ordner / "sce_sys").mkdir(parents=True)
        (ordner / "eboot.bin").write_bytes(b"e")
        reste = [rk.Rest(str(datei), rk.ART_ERGEBNIS, 1, False), rk.Rest(str(ordner), rk.ART_ERGEBNIS, 1, True)]
        weg, fehler = rk.entfernen(reste, str(self.quelle), ordner_loeschen=_loeschen, datei_loeschen=os.remove)
        self.assertEqual([str(datei), str(ordner)], weg)
        self.assertEqual([], fehler)
        self.assertFalse(datei.exists() or ordner.exists())
        self.assertTrue(self.quelle.exists())

    def test_beim_entfernen_schuetzt_die_quelle_noch_einmal(self):
        weg, fehler = rk.entfernen([rk.Rest(str(self.quelle), rk.ART_ERGEBNIS, 100, False)], str(self.quelle),
                                   ordner_loeschen=_loeschen, datei_loeschen=os.remove)
        self.assertEqual([], weg)
        self.assertEqual([(str(self.quelle), "geschuetzt")], fehler)
        self.assertTrue(self.quelle.exists())

    def test_ein_fehler_beim_loeschen_wird_gemeldet_und_stoppt_den_rest_nicht(self):
        a = self.ziel / "a.teil"
        b = self.ziel / "b.teil"
        a.write_bytes(b"1")
        b.write_bytes(b"2")

        def kaputt(pfad):
            if pfad.endswith("a.teil"):
                raise PermissionError("gesperrt")
            os.remove(pfad)
        weg, fehler = rk.entfernen([rk.Rest(str(a), rk.ART_NEBEN, 1, False), rk.Rest(str(b), rk.ART_NEBEN, 1, False)],
                                   str(self.quelle), ordner_loeschen=_loeschen, datei_loeschen=kaputt)
        self.assertEqual([str(b)], weg)
        self.assertEqual("gesperrt", fehler[0][1])

    def test_ein_ordner_der_nicht_ganz_weg_ist_wird_gemeldet(self):
        ordner = self.ziel / "Spiel"
        ordner.mkdir()
        weg, fehler = rk.entfernen([rk.Rest(str(ordner), rk.ART_ERGEBNIS, 0, True)], str(self.quelle),
                                   ordner_loeschen=lambda p: False, datei_loeschen=os.remove)
        self.assertEqual([], weg)
        self.assertEqual(1, len(fehler))

    def test_was_schon_weg_ist_zaehlt_als_entfernt(self):
        weg, fehler = rk.entfernen([rk.Rest(str(self.ziel / "weg.teil"), rk.ART_NEBEN, 0, False)], str(self.quelle),
                                   ordner_loeschen=_loeschen, datei_loeschen=os.remove)
        self.assertEqual(1, len(weg))
        self.assertEqual([], fehler)


class DiagnoseTests(unittest.TestCase):
    def test_die_betriebsdiagnose_kennt_teil_und_neu_als_reste(self):
        for name in ("Spiel.exfat.teil", "Spiel.ffpfsc.neu", "Spiel.ffpkg.part", "Spiel.ffpfs.tmp", "Spiel.exfat.partial"):
            self.assertEqual(bd.ART_TEIL, bd.rest_art(name), name)
        for name in ("Spiel.teil", "notiz.neu", "Spiel.exfat", "neu.txt"):
            self.assertEqual("", bd.rest_art(name), name)


class StartdateienZuletztTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.q = Path(self._tmp.name) / "q"
        self.z = Path(self._tmp.name) / "z"
        (self.q / "sce_sys").mkdir(parents=True)
        (self.q / "sce_sys" / "param.json").write_bytes(b"{}")
        (self.q / "eboot.bin").write_bytes(b"e")
        for name in ("a.bin", "b.bin", "Daten"):
            (self.q / name).mkdir() if name == "Daten" else (self.q / name).write_bytes(b"x")
        (self.q / "Daten" / "x.pak").parent.mkdir(exist_ok=True)
        (self.q / "Daten" / "x.pak").write_bytes(b"y")
        self.app = GUI.__new__(GUI)
        self.app._append_to_log = lambda _z: None
        self.app._t = lambda k, **w: k
        self.reihenfolge: list[str] = []
        original = shutil.move

        def merkend(quelle, ziel, *a, **kw):
            self.reihenfolge.append(os.path.basename(quelle))
            return original(quelle, ziel, *a, **kw)
        self._patch = mock.patch.object(shutil, "move", merkend)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_sce_sys_und_eboot_kommen_zuletzt_eboot_ganz_am_ende(self):
        self.assertEqual([], self.app._move_tree_into(str(self.q), str(self.z)))
        self.assertEqual("eboot.bin", self.reihenfolge[-1])
        self.assertEqual("sce_sys", self.reihenfolge[-2])
        self.assertEqual({"a.bin", "b.bin", "Daten"}, set(self.reihenfolge[:-2]))
        self.assertTrue((self.z / "eboot.bin").exists() and (self.z / "sce_sys" / "param.json").exists())

    def test_gross_und_kleinschreibung_zaehlt_nicht(self):
        os.rename(self.q / "eboot.bin", self.q / "EBOOT.BIN")
        os.rename(self.q / "sce_sys", self.q / "SCE_SYS")
        self.app._move_tree_into(str(self.q), str(self.z))
        self.assertEqual(["SCE_SYS", "EBOOT.BIN"], self.reihenfolge[-2:])

    def test_nur_im_wurzelordner_nicht_in_unterordnern(self):
        (self.q / "Daten" / "eboot.bin").write_bytes(b"e2")
        (self.q / "Daten" / "a.txt").write_bytes(b"a")
        self.z.mkdir()
        (self.z / "Daten").mkdir()                       # vorhandener Zielordner: es wird zusammengefuehrt, Ebene fuer Ebene
        self.app._move_tree_into(str(self.q), str(self.z))
        unten = [n for n in self.reihenfolge if n in ("eboot.bin", "a.txt", "x.pak")]
        self.assertIn("a.txt", unten)
        self.assertEqual("eboot.bin", self.reihenfolge[-1], "die oberste eboot.bin kommt zuletzt")

    def test_der_alte_aufruf_ohne_neues_argument_geht_weiter(self):
        melder: list[int] = []
        self.assertEqual([], self.app._move_tree_into(str(self.q), str(self.z), melder.append))
        self.assertTrue(melder)


class VerdrahtungTests(unittest.TestCase):
    def _app(self, ausgabe, **kw):
        app = GUI.__new__(GUI)
        app.protokoll: list[str] = []
        app._append_to_log = app.protokoll.append
        app._t = lambda k, **w: k + " " + " ".join("%s=%s" % kv for kv in sorted(w.items()))
        app._fmt_bytes = lambda n: "%d B" % n
        app.task_final_output_path = ausgabe
        app._cli_mode = kw.get("cli", False)
        app.root = None if kw.get("ohne_fenster") else object()
        app.geplant = []
        app._hauptfaden_planen = lambda f, ms=0: app.geplant.append(f)
        return app

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ziel = Path(self._tmp.name) / "Ziel"
        self.ziel.mkdir()
        self.src = Path(self._tmp.name) / "Quelle.exfat"
        self.src.write_bytes(b"q")

    def test_ein_unfertiges_ergebnis_kommt_ins_protokoll_und_auf_die_karte(self):
        halb = self.ziel / "Spiel.ffpfsc"
        halb.write_bytes(b"x" * 10)
        app = self._app(str(halb))
        app._reste_nach_lauf("pack_file", str(self.src), str(self.ziel))
        self.assertTrue(any("log.reste_gefunden" in z for z in app.protokoll), app.protokoll)
        self.assertTrue(any("log.reste_zeile" in z and "Spiel.ffpfsc" in z for z in app.protokoll))
        self.assertEqual(1, len(app.geplant), "die Karte wird im Hauptfaden eingeplant")

    def test_auf_der_kommandozeile_gibt_es_nur_das_protokoll(self):
        halb = self.ziel / "Spiel.ffpfsc"
        halb.write_bytes(b"x")
        app = self._app(str(halb), cli=True)
        app._reste_nach_lauf("pack_file", str(self.src), str(self.ziel))
        self.assertTrue(app.protokoll)
        self.assertEqual([], app.geplant)

    def test_ohne_reste_bleibt_alles_still(self):
        app = self._app(str(self.ziel / "gibt_es_nicht.ffpfsc"))
        app._reste_nach_lauf("pack_file", str(self.src), str(self.ziel))
        self.assertEqual(([], []), (app.protokoll, app.geplant))

    def test_andere_aufgaben_haben_keine_karte(self):
        halb = self.ziel / "Spiel.ffpfsc"
        halb.write_bytes(b"x")
        for modus in ("inspect", "dump_validator", "ampr_manager", "batch_convert"):
            app = self._app(str(halb))
            app._reste_nach_lauf(modus, str(self.src), str(self.ziel))
            self.assertEqual(([], []), (app.protokoll, app.geplant), modus)

    def test_die_quelle_wird_nie_gemeldet(self):
        app = self._app(str(self.src))
        app._reste_nach_lauf("pack_file", str(self.src), str(self.src.parent))
        self.assertEqual(([], []), (app.protokoll, app.geplant))

    def test_ein_fehler_in_der_karte_stoert_den_lauf_nicht(self):
        halb = self.ziel / "Spiel.ffpfsc"
        halb.write_bytes(b"x")
        app = self._app(str(halb))
        with mock.patch.object(rk, "finden", side_effect=RuntimeError("kaputt")):
            app._reste_nach_lauf("pack_file", str(self.src), str(self.ziel))

    def test_der_lauf_ruft_die_karte_nach_einem_misserfolg_im_finally(self):
        i = QUELLE.index("def _run_engine_thread")
        ausschnitt = QUELLE[i:QUELLE.index("    def _run_flexible_conversion", i)]
        self.assertIsNotNone(re.search(
            r"finally:.*?self\._selbstziel_reste_entfernen\(\)\s+# Hat der Lauf nicht geklappt[^\n]*\n"
            r"\s+if not success:\s+self\._reste_nach_lauf\(mode, src, dst\)", ausschnitt, re.S))

    def test_alle_aufgaben_mit_ergebnis_sind_erfasst(self):
        ziel_modi = set(GUI._MODE_TARGET_OPTIONS) - {"batch_convert"}
        self.assertLessEqual(ziel_modi, GUI._RESTE_AUFGABEN)


class FensterTests(unittest.TestCase):
    """Die Karte mit echtem Fenster: zeigt Pfad und Knoepfe, Entfernen loescht, Behalten laesst liegen."""

    @classmethod
    def setUpClass(cls):
        try:
            import tkinter as tk
            cls.tk = tk
            cls.wurzel = tk._default_root or tk.Tk()
            cls.wurzel.withdraw()
        except Exception:                        # pragma: no cover
            raise unittest.SkipTest("keine Anzeige verfuegbar")
        cls.app = HAUPT.PS5ConverterGUI(cls.wurzel)
        cls.app._current_language = "de"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ziel = Path(self._tmp.name) / "Ziel"
        self.ziel.mkdir()
        self.src = Path(self._tmp.name) / "Quelle.exfat"
        self.src.write_bytes(b"q")
        self.log: list[str] = []
        self._alt = self.app._append_to_log
        self.app._append_to_log = self.log.append
        self.addCleanup(lambda: setattr(self.app, "_append_to_log", self._alt))
        # Der Loeschfaden gibt dem Hauptfaden Rueckrufe auf; ohne ``mainloop`` wuerde ``root.after`` aus dem Faden abgewiesen.
        self._geplant: "queue.Queue[tuple]" = queue.Queue()
        self.app._hauptfaden_planen = lambda rueckruf, *args, ms=0: (self._geplant.put((rueckruf, args)), True)[1]
        self.addCleanup(lambda: self.app.__dict__.pop("_hauptfaden_planen", None))

    def _sammle(self, widget, art, treffer=None):
        treffer = [] if treffer is None else treffer
        for kind in widget.winfo_children():
            if kind.__class__.__name__ == art:
                treffer.append(kind)
            self._sammle(kind, art, treffer)
        return treffer

    def _fenster(self, reste):
        vorher = {k for k in self.wurzel.winfo_children()}
        self.app._reste_karte_zeigen(reste, str(self.src))
        neu = [k for k in self.wurzel.winfo_children() if k not in vorher and isinstance(k, self.tk.Toplevel)]
        self.assertEqual(1, len(neu))
        neu[0].update_idletasks()
        self.addCleanup(lambda: neu[0].winfo_exists() and neu[0].destroy())
        return neu[0]

    def _knopf(self, fenster, text):
        for k in self._sammle(fenster, "Button"):
            if str(k.cget("text")) == text:
                return k
        self.fail("kein Knopf %r" % text)

    def test_die_karte_nennt_pfad_und_art(self):
        halb = self.ziel / "Spiel"
        halb.mkdir()
        (halb / "a.bin").write_bytes(b"x" * 3)
        fenster = self._fenster(rk.finden(str(halb), str(self.src), zielordner=str(self.ziel)))
        texte = [str(w.cget("text")) for w in self._sammle(fenster, "Label")]
        self.assertIn(str(halb), texte)
        self.assertIn(self.app._t("reste.art_ordner"), texte)

    def test_entfernen_loescht_den_rest_und_laesst_die_quelle(self):
        halb = self.ziel / "Spiel.ffpfsc"
        halb.write_bytes(b"x" * 10)
        fenster = self._fenster(rk.finden(str(halb), str(self.src), zielordner=str(self.ziel)))
        self._knopf(fenster, self.app._t("reste.entfernen")).invoke()
        self._warten(fenster)                                # das Loeschen laeuft in einem eigenen Faden, nicht im Hauptfaden
        self.assertFalse(halb.exists())
        self.assertTrue(self.src.exists())
        self.assertTrue(any("log.reste_entfernt" in z or "Rest entfernt" in z for z in self.log), self.log)
        self.assertFalse(fenster.winfo_exists())

    def test_entfernen_loescht_nicht_im_hauptfaden_und_sperrt_den_knopf(self):
        halb = self.ziel / "Spiel.ffpfsc"
        halb.write_bytes(b"x" * 10)
        fenster = self._fenster(rk.finden(str(halb), str(self.src), zielordner=str(self.ziel)))
        knopf = self._knopf(fenster, self.app._t("reste.entfernen"))
        faeden = []
        echt = rk.entfernen

        def aufzeichnen(*args, **kwargs):
            faeden.append(threading.current_thread())
            return echt(*args, **kwargs)
        with mock.patch.object(rk, "entfernen", aufzeichnen):
            knopf.invoke()
            self.assertEqual(("disabled",), knopf.state(), "kein zweiter Klick, solange geloescht wird")
            self._warten(fenster)
        self.assertEqual(1, len(faeden))
        self.assertIsNot(threading.main_thread(), faeden[0], "ein grosser Ordner darf die Oberflaeche nicht anhalten")
        self.assertFalse(halb.exists())

    def test_entfernen_wartet_bis_keine_aufgabe_mehr_laeuft(self):
        """Eine neue Aufgabe kann in denselben Zielordner schreiben: Die Karte bleibt offen, nichts wird geloescht."""
        halb = self.ziel / "Spiel.ffpfsc"
        halb.write_bytes(b"x" * 10)
        fenster = self._fenster(rk.finden(str(halb), str(self.src), zielordner=str(self.ziel)))
        alt = getattr(self.app, "is_running", False)
        self.app.is_running = True
        self.addCleanup(setattr, self.app, "is_running", alt)
        self._knopf(fenster, self.app._t("reste.entfernen")).invoke()
        self.wurzel.update()
        self.assertTrue(halb.exists())
        self.assertTrue(fenster.winfo_exists())
        self.assertTrue(any(self.app._t("log.reste_laeuft_noch") in z for z in self.log), self.log)
        self.app.is_running = False                          # danach geht es
        self._knopf(fenster, self.app._t("reste.entfernen")).invoke()
        self._warten(fenster)
        self.assertFalse(halb.exists())

    def _warten(self, fenster, sekunden=15.0):
        """Fuehrt die Rueckrufe aus, die der Loeschfaden dem Hauptfaden aufgibt (``root.after`` aus einem Faden geht nur in ``mainloop``)."""
        ende = time.monotonic() + sekunden
        while time.monotonic() < ende:
            try:
                rueckruf, args = self._geplant.get(timeout=0.05)
            except queue.Empty:
                if not fenster.winfo_exists():
                    break
                continue
            rueckruf(*args)
            self.wurzel.update()
            if not fenster.winfo_exists():
                break

    def test_behalten_laesst_alles_liegen(self):
        halb = self.ziel / "Spiel.ffpfsc"
        halb.write_bytes(b"x" * 10)
        fenster = self._fenster(rk.finden(str(halb), str(self.src), zielordner=str(self.ziel)))
        self._knopf(fenster, self.app._t("reste.behalten")).invoke()
        self.assertTrue(halb.exists())
        self.assertFalse(fenster.winfo_exists())


class TexteTests(unittest.TestCase):
    def test_alle_texte_in_allen_sprachen(self):
        from ps5_validator.utils.i18n import STRINGS, SUPPORTED_LANGUAGES
        felder = {"reste.titel": (), "reste.untertitel": (), "reste.erklaerung": (), "reste.art_datei": (),
                  "reste.art_ordner": (), "reste.art_neben": (), "reste.groesse": ("size",),
                  "reste.groesse_mindestens": ("size",), "reste.entfernen": (), "reste.behalten": (),
                  "log.reste_gefunden": ("anzahl", "size"), "log.reste_zeile": ("pfad", "groesse"),
                  "log.reste_entfernt": ("pfad",), "log.reste_fehler": ("pfad", "fehler"), "log.reste_behalten": (),
                  "log.reste_laeuft_noch": ()}
        for key, namen in felder.items():
            for sprache in SUPPORTED_LANGUAGES:
                text = STRINGS[key][sprache]
                self.assertTrue(text, "%s/%s" % (key, sprache))
                for feld in namen:
                    self.assertIn("{%s}" % feld, text, "%s/%s" % (key, sprache))


class StandUndNebenendungenTests(unittest.TestCase):
    """Pruefbericht 14.11.2026: Die Karte darf kein inzwischen neues Ergebnis entfernen; ``.neu.teil`` und ``.teil.tmp`` sind Reste."""

    def setUp(self) -> None:
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="reste_stand_")
        self.addCleanup(__import__("shutil").rmtree, self.tmp, True)
        self.ziel = os.path.join(self.tmp, "ziel")
        os.makedirs(self.ziel)
        self.quelle = os.path.join(self.tmp, "quelle", "spiel.exfat")
        os.makedirs(os.path.dirname(self.quelle))
        open(self.quelle, "wb").write(b"q")

    def datei(self, name: str, inhalt: bytes = b"x" * 100) -> str:
        pfad = os.path.join(self.ziel, name)
        open(pfad, "wb").write(inhalt)
        return pfad

    def test_ein_inzwischen_geaendertes_ergebnis_bleibt_stehen(self) -> None:
        ergebnis = self.datei("Spiel.exfat")
        reste = rk.finden(ergebnis, self.quelle, zielordner=self.ziel)
        self.assertEqual([ergebnis], [r.pfad for r in reste])
        self.datei("Spiel.exfat", b"y" * 5000)                       # ein neuer Lauf hat das Ergebnis fertig geschrieben
        weg, fehler = rk.entfernen(reste, self.quelle, ordner_loeschen=lambda p: False, datei_loeschen=os.remove)
        self.assertEqual([], weg)
        self.assertEqual([(ergebnis, "geaendert seit dem Finden")], fehler)
        self.assertTrue(os.path.exists(ergebnis))

    def test_ein_unveraenderter_rest_wird_entfernt(self) -> None:
        teil = self.datei("Spiel.exfat.teil")
        reste = rk.finden(os.path.join(self.ziel, "Spiel.exfat"), self.quelle, zielordner=self.ziel)
        weg, fehler = rk.entfernen(reste, self.quelle, ordner_loeschen=lambda p: False, datei_loeschen=os.remove)
        self.assertEqual([teil], weg)
        self.assertEqual([], fehler)
        self.assertFalse(os.path.exists(teil))

    def test_selbstziel_und_zwischendatei_werden_gefunden(self) -> None:
        ergebnis = os.path.join(self.ziel, "Spiel.exfat")
        namen = [self.datei("Spiel.exfat.neu.teil"), self.datei("Spiel.exfat.teil.tmp"), self.datei("Spiel.exfat.teil"),
                 self.datei("Spiel.exfat.neu.teil.tmp")]
        gefunden = {r.pfad for r in rk.finden(ergebnis, self.quelle, zielordner=self.ziel)}
        self.assertEqual(set(namen), gefunden)

    def test_ein_ordner_wird_an_seiner_zeit_erkannt(self) -> None:
        ordner = os.path.join(self.ziel, "Spiel")
        os.makedirs(ordner)
        reste = rk.finden(ordner, self.quelle, zielordner=self.ziel)
        self.assertEqual(1, len(reste))
        os.makedirs(os.path.join(ordner, "neu"))                      # Inhalt kam hinzu (die Zeit des Ordners bewegt sich dabei nicht immer: gesetzt wird sie unten)
        os.utime(ordner, ns=(reste[0].stand[1] + 10**9, reste[0].stand[1] + 10**9))
        weg, fehler = rk.entfernen(reste, self.quelle, ordner_loeschen=lambda p: True, datei_loeschen=os.remove)
        self.assertEqual([], weg)
        self.assertEqual(1, len(fehler))


if __name__ == "__main__":
    unittest.main()
