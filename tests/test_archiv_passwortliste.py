# -*- coding: utf-8 -*-
"""Passwortliste fuer Archive und ZIP ohne Entpackordner auch in Sammelkonvertierung und Kommandozeile (14.11.2026).

* ``archiv_quelle.entpacken`` probiert nach den bekannten Szene-Passwoertern die Liste des Anwenders (Einstellung
  ``archiv_passwoerter``) - auch fuer .7z/.rar, die immer entpackt werden. Ein ausdruecklich genanntes Passwort gilt allein.
* EINSTELLUNGEN hat einen Abschnitt ARCHIV-PASSWOERTER: Getipptes wird als Liste gespeichert (Kommas, ohne Leere und Doppelte).
* ``_archiv_blockierend_entpacken(schatten=True)`` legt ein ZIP nur als Schattenordner an; die Sammelkonvertierung tut das, wenn
  der Weg zum Zielformat es im Strom liest, und entpackt sonst gleich vollstaendig (``_archiv_schatten_vorbereiten`` mit dem
  Zielformat). Beim Wegraeumen verschwinden auch die Eintraege der Tabellen.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import archiv_quelle   # noqa: E402

SIEBENZIP = archiv_quelle.siebenzip_suchen([str(PROJEKT)])

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:   # noqa: BLE001
    TK_DA = False
    _WURZEL = None


def _spiel(wurzel: Path) -> None:
    (wurzel / "sce_sys").mkdir(parents=True)
    (wurzel / "sce_sys" / "param.json").write_text("{}", encoding="utf-8")
    (wurzel / "eboot.bin").write_bytes(b"\x7fSELF" + bytes(2000))
    (wurzel / "Media").mkdir()
    (wurzel / "Media" / "a.dat").write_bytes(b"x" * 5000)


def _zip_mit_spiel(ordner: Path, name: str) -> Path:
    archiv = ordner / name
    with zipfile.ZipFile(archiv, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("sce_sys/param.json", "{}")
        z.writestr("eboot.bin", b"ELF" + bytes(4092))
        z.writestr("Media/gross.bin", b"m" * 50_000)
    return archiv


def _siebenzip(quelle: Path, archiv: Path, passwort: str, *zusatz: str) -> None:
    subprocess.run([SIEBENZIP, "a", *zusatz, str(archiv), "-p" + passwort, "-bso0", "-bsp0", "."], check=True,
                   cwd=str(quelle), stdin=subprocess.DEVNULL, creationflags=0x08000000 if sys.platform == "win32" else 0)


@unittest.skipUnless(SIEBENZIP, "7-Zip nicht gefunden")
class ModulTests(unittest.TestCase):
    def _verschluesselt(self, t: str, passwort: str) -> Path:
        quelle = Path(t) / "q"
        _spiel(quelle)
        archiv = Path(t) / "geheim.7z"
        _siebenzip(quelle, archiv, passwort, "-mhe=on")
        return archiv

    def entpacken(self, archiv: Path, ziel: Path, **kw) -> str:
        return archiv_quelle.entpacken(str(archiv), str(ziel), wurzeln=[str(PROJEKT)], popen_extra={"creationflags": 0x08000000}, **kw)

    def test_die_liste_des_anwenders_wird_nach_den_bekannten_probiert(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            archiv = self._verschluesselt(t, "meins-xyz")
            with self.assertRaises(archiv_quelle.PasswortFehler):
                self.entpacken(archiv, Path(t) / "ohne")
            wurzel = self.entpacken(archiv, Path(t) / "mit", weitere_passwoerter=["anderes", "meins-xyz"])
            self.assertEqual(b"x" * 5000, (Path(wurzel) / "Media" / "a.dat").read_bytes())

    def test_ein_genanntes_passwort_gilt_allein(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            archiv = self._verschluesselt(t, "meins-xyz")
            with self.assertRaises(archiv_quelle.PasswortFehler):
                self.entpacken(archiv, Path(t) / "ziel", passwort="falsch", weitere_passwoerter=["meins-xyz"])


class _MitApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not TK_DA:
            raise unittest.SkipTest("Keine Anzeige verfuegbar")
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.t = Path(tmp.name)
        (self.t / "arbeit").mkdir()
        self.konfig = str(self.t / "paths.json")
        Path(self.konfig).write_text("{}", encoding="utf-8")
        patches = [mock.patch.object(self.app, "_get_config_path", return_value=self.konfig),
                   mock.patch.object(self.app, "_get_runtime_temp_dir", return_value=str(self.t / "arbeit")),
                   mock.patch.object(self.app, "_append_to_log")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.app.__dict__["_settings_cache"] = None
        self.addCleanup(lambda: self.app.__dict__.__setitem__("_settings_cache", None))


class DialogTests(_MitApp):
    def _sammle(self, widget, art, treffer=None):
        treffer = [] if treffer is None else treffer
        for kind in widget.winfo_children():
            if kind.__class__.__name__ == art:
                treffer.append(kind)
            self._sammle(kind, art, treffer)
        return treffer

    def test_der_abschnitt_speichert_die_getippte_liste(self) -> None:
        self.app._show_settings_dialog()
        dlg = [k for k in _WURZEL.winfo_children() if isinstance(k, tk.Toplevel) and k.winfo_exists()][-1]
        self.addCleanup(lambda: dlg.winfo_exists() and dlg.destroy())
        dlg.update_idletasks()
        texte = [str(w.cget("text")) for w in self._sammle(dlg, "Label")]
        self.assertIn("ARCHIV-PASSWÖRTER", texte)
        self.assertTrue(any("pippo" in x for x in texte), "der Hinweis nennt die bekannten Passwoerter")
        leer = [e for e in self._sammle(dlg, "Entry") if e.get() == ""]
        eingabe = None
        for kandidat in leer:
            skript = kandidat.bind("<KeyRelease>")
            if skript:
                eingabe = kandidat
                break
        self.assertIsNotNone(eingabe, "ein leeres Feld mit Tastenbehandlung")
        eingabe.insert(0, " eins , zwei,,eins, drei ")
        behandler = re.search(r"\[(\S+) ", eingabe.bind("<KeyRelease>")).group(1)
        dlg.tk.call(behandler, "x")
        dlg.update()
        gespeichert = json.loads(Path(self.konfig).read_text(encoding="utf-8"))
        self.assertEqual(["eins", "zwei", "drei"], gespeichert.get("archiv_passwoerter"))
        self.assertEqual(["eins", "zwei", "drei"], self.app._archiv_weitere_passwoerter())
        self.assertTrue(any("3 eigene Passwörter" in str(w.cget("text")) for w in self._sammle(dlg, "Label")))


class BlockierendTests(_MitApp):
    def test_mit_schatten_kommt_nur_sce_sys_und_eboot_heraus(self) -> None:
        archiv = _zip_mit_spiel(self.t, "Spiel.zip")
        wurzel, entpackt, fehler = self.app._archiv_blockierend_entpacken(str(archiv), schatten=True)
        self.assertEqual("", fehler)
        self.assertTrue(os.path.isfile(os.path.join(wurzel, "sce_sys", "param.json")))
        self.assertFalse(os.path.exists(os.path.join(wurzel, "Media")), "das Spiel bleibt im Archiv")
        self.assertEqual(str(archiv), self.app._archiv_schatten_info(wurzel)["archiv"])
        self.assertEqual(str(archiv), self.app._quelle_zum_loeschen(wurzel))
        self.app._archiv_ordner_wegraeumen(entpackt)
        self.assertFalse(os.path.exists(entpackt))
        self.assertIsNone(self.app._archiv_schatten_info(wurzel), "die Tabelle vergisst den weggeraeumten Ordner")
        self.assertEqual(wurzel, self.app._quelle_zum_loeschen(wurzel))

    def test_ohne_schatten_oder_ohne_strom_wird_entpackt(self) -> None:
        archiv = _zip_mit_spiel(self.t, "Spiel.zip")
        wurzel, entpackt, fehler = self.app._archiv_blockierend_entpacken(str(archiv))
        self.assertEqual("", fehler)
        self.assertTrue(os.path.isfile(os.path.join(wurzel, "Media", "gross.bin")))
        self.app._archiv_ordner_wegraeumen(entpackt)
        with mock.patch.object(self.app, "_archiv_strom_gewaehlt", return_value=False):
            wurzel, entpackt, fehler = self.app._archiv_blockierend_entpacken(str(archiv), schatten=True)
        self.assertTrue(os.path.isfile(os.path.join(wurzel, "Media", "gross.bin")))
        self.app._archiv_ordner_wegraeumen(entpackt)

    @unittest.skipUnless(SIEBENZIP, "7-Zip nicht gefunden")
    def test_ein_zip_mit_einem_passwort_der_liste_wird_als_schatten_gelesen(self) -> None:
        quelle = self.t / "q"
        _spiel(quelle)
        archiv = self.t / "geheim.zip"
        _siebenzip(quelle, archiv, "listen-passwort", "-tzip", "-mem=ZipCrypto")
        Path(self.konfig).write_text(json.dumps({"archiv_passwoerter": ["listen-passwort"]}), encoding="utf-8")
        self.app.__dict__["_settings_cache"] = None
        wurzel, entpackt, fehler = self.app._archiv_blockierend_entpacken(str(archiv), schatten=True)
        self.assertEqual("", fehler)
        self.assertEqual("listen-passwort", self.app._archiv_schatten_info(wurzel)["passwort"])
        self.app._archiv_ordner_wegraeumen(entpackt)


class SammelTests(_MitApp):
    """Die Schleife von Aufgabe 5: Umwandlung und Pruefung sind ersetzt, gemessen wird, was beim Umwandeln daliegt."""

    def setUp(self) -> None:
        super().setUp()
        (self.t / "ziel").mkdir()
        self.gesehen: "list[tuple[str, bool, bool]]" = []       # (Quelle, Media da, Schattenordner)
        app = self.app
        app.is_running = True
        app.root = None
        patches = [
            mock.patch.object(app, "_batch_spiel_zeigen"),
            mock.patch.object(app, "_batch_cover_vorladen"),
            mock.patch.object(app, "_conversion_block_reason", return_value=""),
            mock.patch.object(app, "_batch_ueberschreiben_klaeren", return_value=True),
            mock.patch.object(app, "_batch_arbeitskopien_raeumen"),
            mock.patch.object(app, "_verify_output_artifact", return_value={"ok": True, "detail": "ok"}),
            mock.patch.object(app, "_execute_conversion_by_type", side_effect=self._umwandeln),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def _umwandeln(self, source_type, target_type, src, dst):
        info = self.app._archiv_schatten_info(src)
        self.gesehen.append((src, os.path.isfile(os.path.join(src, "Media", "gross.bin")), bool(info and not info.get("voll"))))
        self.app.task_final_output_path = os.path.join(dst, os.path.basename(src) + ".x")
        return True

    def _lauf(self, ziel: str, im_strom: bool):
        archiv = _zip_mit_spiel(self.t, "Spiel.zip")
        self.app._batch_sources = [str(archiv)]
        with mock.patch.object(self.app, "_get_selected_target_type", return_value=ziel), \
                mock.patch.object(self.app, "_archiv_schatten_im_strom", return_value=im_strom) as frage:
            ok = self.app._run_flexible_conversion("batch_convert", str(archiv), str(self.t / "ziel"))
        return ok, frage

    def test_liest_der_strom_das_ziel_bleibt_es_ein_schattenordner(self) -> None:
        ok, frage = self._lauf("ffpfsc", True)
        self.assertTrue(ok)
        self.assertEqual([("Spiel", False, True)], [(os.path.basename(s), m, sch) for s, m, sch in self.gesehen])
        self.assertIn(mock.call("pack_folder", "ffpfsc"), frage.call_args_list)
        self.assertEqual([], os.listdir(self.t / "arbeit"))

    def test_braucht_der_weg_einen_ordner_wird_vorher_ganz_entpackt(self) -> None:
        ok, _frage = self._lauf("folder", False)
        self.assertTrue(ok)
        self.assertEqual([("Spiel", True, False)], [(os.path.basename(s), m, sch) for s, m, sch in self.gesehen])
        self.assertEqual([], os.listdir(self.t / "arbeit"))


class KommandozeileTests(unittest.TestCase):
    def test_aufgabe_1_auf_der_kommandozeile_legt_einen_schattenordner_an(self) -> None:
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        self.assertIn('sources[0], passwort=str(getattr(args, "archiv_passwort", "") or ""), schatten=True)', quelle)
        self.assertIn('abbruch=lambda: not self.is_running, schatten=True)', quelle)
        self.assertIn('self._archiv_schatten_vorbereiten("pack_folder", spielordner, target_type)', quelle)


if __name__ == "__main__":
    unittest.main()
