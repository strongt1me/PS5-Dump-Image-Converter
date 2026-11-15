# -*- coding: utf-8 -*-
"""ZIP-Archive als Quelle ohne Entpackordner (Strom, 14.11.2026): Schattenordner, Strom aus dem Archiv, Rueckfall auf vollstaendiges Entpacken.

Der Weg: Das Feld QUELLE zeigt einen Schattenordner mit nur ``sce_sys`` und ``eboot.bin`` (Name und Aufbau wie der entpackte Spielordner);
das Spiel liest der Strom beim Umwandeln direkt aus dem Archiv (``archiv_baum.ZipBaum``). Braucht ein Weg den Ordner doch, wird er vorher
vollstaendig entpackt - mit einem halben Ordner arbeitet nie ein Weg weiter.
"""
from __future__ import annotations

import ast
import os
import shutil
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import test_exfat_strom_weg as T                            # noqa: E402  (Harness: _gui, _spiel)
from ps5_validator.utils import ampr_zstdpack as z           # noqa: E402
from ps5_validator.utils import quelle_loeschen              # noqa: E402
from ps5_validator.utils import spielbaum as sb              # noqa: E402

GUI = T.GUI
APP = T.APP


def _gui(tmp: str):
    g = T._gui(tmp)
    g._archiv_schatten = {}
    g._archiv_herkunft = {}
    return g


class _Grundlage(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="archivstrom_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.makedirs(os.path.join(self.tmp, "temp"))
        self.inhalt = T._spiel()
        self.spiel = os.path.join(self.tmp, "Spiel")                  # dasselbe Spiel als Ordner, zum Vergleichen
        for rel, daten in self.inhalt.items():
            voll = os.path.join(self.spiel, *rel.split("/"))
            os.makedirs(os.path.dirname(voll), exist_ok=True)
            Path(voll).write_bytes(daten)
        self.zip = self._zip("Mein Spiel.zip")
        self.entpackt = os.path.join(self.tmp, "entpackt")
        os.makedirs(self.entpackt)
        self.ziel = os.path.join(self.tmp, "ziel")
        os.makedirs(self.ziel)

    def _zip(self, name: str, extra: "dict[str, bytes] | None" = None, wurzel: str = "Spiel") -> str:
        pfad = os.path.join(self.tmp, name)
        daten = dict(self.inhalt)
        daten.update(extra or {})
        with zipfile.ZipFile(pfad, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel, inhalt in daten.items():
                zf.writestr((wurzel + "/" if wurzel else "") + rel, inhalt)
        return pfad

    def schatten(self, g, archiv: "str | None" = None) -> str:
        spiel = g._archiv_schatten_anlegen(archiv or self.zip, self.entpackt, "")
        self.assertIsNotNone(spiel, "\n".join(g._log_lines))
        return spiel


class SchattenTests(_Grundlage):
    def test_nur_sce_sys_und_eboot_mit_dem_namen_des_spielordners(self) -> None:
        g = _gui(self.tmp)
        spiel = self.schatten(g)
        self.assertEqual("Spiel", os.path.basename(spiel))
        gefunden = sorted(os.path.relpath(os.path.join(o, n), spiel).replace(os.sep, "/")
                          for o, _d, ns in os.walk(spiel) for n in ns)
        self.assertEqual(sorted(r for r in self.inhalt if r == "eboot.bin" or r.startswith("sce_sys/")), gefunden)
        for rel in gefunden:
            self.assertEqual(self.inhalt[rel], Path(spiel, *rel.split("/")).read_bytes(), rel)

    def test_das_archiv_ist_registriert_und_die_groesse_ist_die_des_spiels(self) -> None:
        g = _gui(self.tmp)
        spiel = self.schatten(g)
        info = g._archiv_schatten_info(spiel)
        self.assertEqual(self.zip, info["archiv"])
        self.assertFalse(info["voll"])
        gesamt = sum(len(v) for v in self.inhalt.values())
        self.assertEqual(gesamt, info["groesse"])
        self.assertEqual(gesamt, g._get_path_size(spiel), "Die Anzeige zeigte sonst die 7 KB des Schattenordners")
        self.assertEqual(self.zip, g._quelle_zum_loeschen(spiel))

    def test_archiv_ohne_spiel_geht_nicht_und_wird_gemeldet(self) -> None:
        pfad = os.path.join(self.tmp, "ohne.zip")
        with zipfile.ZipFile(pfad, "w") as zf:
            zf.writestr("liesmich.txt", b"kein Spiel")
        g = _gui(self.tmp)
        self.assertIsNone(g._archiv_schatten_anlegen(pfad, self.entpackt, ""))
        self.assertTrue(any("nicht direkt gelesen" in z_ or "not read directly" in z_ for z_ in g._log_lines), g._log_lines)
        self.assertEqual({}, g._archiv_schatten)

    def test_dlc_ordner_neben_dem_spiel_heisst_ganz_entpacken(self) -> None:
        """Gesamtpruefung 14.11.2026, S-D: Der Schattenordner traegt nur das Spiel - DLC EMU faende die "-ac"-Ordner daneben nicht."""
        dlc = "UP0001-PPSA01234_00-ABCDEFGHIJKLMNOP-ac"
        pfad = self._zip("mit_dlc.zip", wurzel="Spiel")
        with zipfile.ZipFile(pfad, "a") as zf:
            zf.writestr(dlc + "/data/dlc.bin", b"d" * 100)
        g = _gui(self.tmp)
        self.assertIsNone(g._archiv_schatten_anlegen(pfad, self.entpackt, ""))
        self.assertTrue(any(dlc in z_ for z_ in g._log_lines), g._log_lines)
        self.assertEqual({}, g._archiv_schatten)

    def test_gegenprobe_ohne_dlc_bleibt_es_beim_schatten(self) -> None:
        pfad = self._zip("ohne_dlc.zip", wurzel="Spiel")
        with zipfile.ZipFile(pfad, "a") as zf:
            zf.writestr("Liesmich/info.txt", b"kein DLC")
        g = _gui(self.tmp)
        self.assertIsNotNone(g._archiv_schatten_anlegen(pfad, self.entpackt, ""))

    def test_weitere_passwoerter_aus_den_einstellungen(self) -> None:
        g = _gui(self.tmp)
        self.assertEqual([], g._archiv_weitere_passwoerter())
        g.einstellungen["archiv_passwoerter"] = ["a", "", "b"]
        self.assertEqual(["a", "b"], g._archiv_weitere_passwoerter())
        g.einstellungen["archiv_passwoerter"] = " x , y ,, z"
        self.assertEqual(["x", "y", "z"], g._archiv_weitere_passwoerter())
        g.einstellungen["archiv_passwoerter"] = 5
        self.assertEqual([], g._archiv_weitere_passwoerter())

    def test_das_zwoelf_stunden_aufraeumen_laesst_das_gewaehlte_archiv_stehen(self) -> None:
        """Gesamtpruefung 14.11.2026, S-I: Ein Archiv von gestern als Quelle - sein Entpackordner ist alt, aber nicht verwaist."""
        basis = os.path.join(self.tmp, "arbeit")
        os.makedirs(basis)
        g = _gui(self.tmp)
        gewaehlt = os.path.join(basis, "ps5conv_archiv_gestern")
        verwaist = os.path.join(basis, "ps5conv_archiv_vorgestern")
        spiel = g._archiv_schatten_anlegen(self.zip, gewaehlt, "")
        self.assertIsNotNone(spiel)
        os.makedirs(os.path.join(verwaist, "Spiel"))
        alt = time.time() - 30 * 3600
        for ordner in (gewaehlt, verwaist):
            os.utime(ordner, (alt, alt))
        g._get_runtime_temp_dir = lambda *a, **k: basis
        g._stale_temp_swept = False
        g._sweep_stale_temp_dirs()
        self.assertTrue(os.path.isdir(spiel), "die gewaehlte Quelle bleibt")
        self.assertFalse(os.path.exists(verwaist), "Gegenprobe: ein echter alter Rest wird weiter weggeraeumt")

    def test_ein_gewoehnlicher_ordner_ist_kein_schatten(self) -> None:
        g = _gui(self.tmp)
        self.assertIsNone(g._archiv_schatten_info(self.spiel))
        self.assertIsNone(g._archiv_schatten_baum(self.spiel))
        self.assertEqual(self.spiel, g._quelle_zum_loeschen(self.spiel))


class VollstaendigTests(_Grundlage):
    def _alles(self, ordner: str) -> "dict[str, bytes]":
        return {os.path.relpath(os.path.join(o, n), ordner).replace(os.sep, "/"): Path(o, n).read_bytes()
                for o, _d, ns in os.walk(ordner) for n in ns}

    def test_vollstaendig_entpackt_den_rest(self) -> None:
        g = _gui(self.tmp)
        spiel = self.schatten(g)
        g._archiv_schatten_vollstaendig(spiel)
        self.assertEqual(self.inhalt, self._alles(spiel))
        self.assertTrue(g._archiv_schatten_info(spiel)["voll"])
        self.assertIsNone(g._archiv_schatten_baum(spiel), "Ein vollstaendiger Ordner wird nicht mehr aus dem Archiv gelesen")
        self.assertEqual(sum(len(v) for v in self.inhalt.values()), g._get_path_size(spiel))
        g._archiv_schatten_vollstaendig(spiel)                       # ein zweites Mal schadet nicht

    def test_leere_ordner_im_archiv_entstehen(self) -> None:
        pfad = os.path.join(self.tmp, "leer.zip")
        with zipfile.ZipFile(pfad, "w") as zf:
            for rel, daten in self.inhalt.items():
                zf.writestr("Spiel/" + rel, daten)
            zf.writestr(zipfile.ZipInfo("Spiel/save/leer/"), b"")
        g = _gui(self.tmp)
        spiel = self.schatten(g, pfad)
        g._archiv_schatten_vollstaendig(spiel)
        self.assertTrue(os.path.isdir(os.path.join(spiel, "save", "leer")))

    def test_ein_geaendertes_archiv_wird_nicht_entpackt(self) -> None:
        g = _gui(self.tmp)
        spiel = self.schatten(g)
        st = os.stat(self.zip)
        os.utime(self.zip, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
        with self.assertRaises(OSError) as ctx:
            g._archiv_schatten_vollstaendig(spiel)
        self.assertIn("geändert", str(ctx.exception))
        self.assertFalse(g._archiv_schatten_info(spiel)["voll"])
        self.assertFalse(os.path.exists(os.path.join(spiel, "Media", "text.txt")), "Es darf nichts Halbes entstehen")

    def test_ein_passwortfehler_wird_zum_oserror(self) -> None:
        """R2-A6: Wird das Archiv waehrend des Laufs gegen ein verschluesseltes getauscht, entkam der PasswortFehler jedem Aufrufer."""
        from ps5_validator.utils import archiv_quelle
        g = _gui(self.tmp)
        spiel = self.schatten(g)
        with mock.patch.object(APP.archiv_baum.ZipBaum, "dateien",
                               side_effect=archiv_quelle.PasswortFehler("Das Archiv ist verschluesselt")):
            with self.assertRaises(OSError):
                g._archiv_schatten_vollstaendig(spiel)
        self.assertFalse(g._archiv_schatten_info(spiel)["voll"])

    def test_abbruch_waehrend_des_entpackens_ist_ein_fehler_und_kein_halber_ordner(self) -> None:
        g = _gui(self.tmp)
        spiel = self.schatten(g)
        g.is_running = False                                         # der Lauf wurde abgebrochen
        with self.assertRaises(OSError):
            g._archiv_schatten_vollstaendig(spiel)
        self.assertFalse(g._archiv_schatten_info(spiel)["voll"])

    def test_zu_wenig_platz(self) -> None:
        g = _gui(self.tmp)
        spiel = self.schatten(g)
        g._archiv_schatten[g._archiv_schluessel(spiel)]["groesse"] = 1 << 60
        with self.assertRaises(OSError):
            g._archiv_schatten_vollstaendig(spiel)


class VorbereitenTests(_Grundlage):
    def _vorbereiten(self, ziel: str, *, strom: bool, mode: str = "pack_folder") -> "tuple":
        g = _gui(self.tmp)
        spiel = self.schatten(g)
        g._lauf_zielformat = ziel
        g._strom_fuer_ordner_gewaehlt = lambda: strom
        g._strom_nach_container_gewaehlt = lambda ordner=False: strom
        g._strom_nach_ffpfs_gewaehlt = lambda ordner=False: strom
        g._strom_nach_ffpkg_gewaehlt = lambda: strom
        return g, spiel, g._archiv_schatten_vorbereiten(mode, spiel)

    def test_abbild_als_ziel_mit_strom_bleibt_ein_schatten(self) -> None:
        for ziel in ("exfat", "ffpfsc", "ffpfs", "ffpkg"):
            with self.subTest(ziel=ziel):
                g, spiel, ok = self._vorbereiten(ziel, strom=True)
                self.assertTrue(ok)
                self.assertFalse(g._archiv_schatten_info(spiel)["voll"])
                self.assertFalse(os.path.exists(os.path.join(spiel, "Media", "text.txt")))

    def test_alles_andere_bekommt_den_ganzen_ordner(self) -> None:
        for name, ziel, strom, mode in (("Ziel Ordner", "folder", True, "pack_folder"),
                                        ("Strom aus", "exfat", False, "pack_folder"),
                                        ("andere Aufgabe", "exfat", True, "ampr_manager"),
                                        ("ohne Zielformat", "", True, "pack_folder")):
            with self.subTest(name):
                g, spiel, ok = self._vorbereiten(ziel, strom=strom, mode=mode)
                self.assertTrue(ok)
                self.assertTrue(g._archiv_schatten_info(spiel)["voll"])
                self.assertEqual(self.inhalt["Media/zufall.bin"], Path(spiel, "Media", "zufall.bin").read_bytes())

    def test_scheitert_das_entpacken_meldet_es_der_lauf_statt_weiterzumachen(self) -> None:
        g, spiel, _ok = self._vorbereiten("exfat", strom=True)
        st = os.stat(self.zip)
        os.utime(self.zip, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
        g._strom_fuer_ordner_gewaehlt = lambda: False
        self.assertFalse(g._archiv_schatten_vorbereiten("pack_folder", spiel))

    def test_ein_geloeschtes_archiv_beendet_den_lauf_mit_meldung(self) -> None:
        """Gesamtpruefung 14.11.2026, S-E/A3: ZipBaum warf ausserhalb des try - der Faden starb, is_running blieb stehen."""
        g, spiel, _ok = self._vorbereiten("exfat", strom=True)
        os.remove(self.zip)
        g._strom_fuer_ordner_gewaehlt = lambda: False
        self.assertFalse(g._archiv_schatten_vorbereiten("pack_folder", spiel))
        self.assertTrue(any("kein Archiv" in z_ for z_ in g._log_lines), g._log_lines)
        self.assertFalse(g._archiv_schatten_info(spiel)["voll"])


@unittest.skipUnless(z.verfuegbar(), "zstandard fehlt")
class StromTests(_Grundlage):
    def _abbild(self, ordner: str, ziel: str):
        g = _gui(self.tmp)
        ok = g._mode_exfat_umpacken_strom(ordner, ziel, ordner=True)
        return g, ok

    def test_das_ergebnis_gleicht_dem_aus_dem_entpackten_ordner(self) -> None:
        g = _gui(self.tmp)
        spiel = self.schatten(g)
        ok = g._mode_exfat_umpacken_strom(spiel, self.ziel, ordner=True)
        self.assertTrue(ok, "\n".join(g._log_lines))
        ausgabe = os.path.join(self.ziel, "Spiel.exfat")
        self.assertTrue(os.path.isfile(ausgabe))
        ziel2 = os.path.join(self.tmp, "ziel2")
        os.makedirs(ziel2)
        g2, ok2 = self._abbild(self.spiel, ziel2)
        self.assertTrue(ok2, "\n".join(g2._log_lines))
        with sb.ExfatBaum(ausgabe) as a, sb.ExfatBaum(os.path.join(ziel2, "Spiel.exfat")) as b:
            da, db = a.suchen(), b.suchen()
            self.assertEqual(sorted(da), sorted(db))
            for rel in da:
                if rel in ("sce_sys/param.json", "sce_sys/param.json.alt"):
                    continue                                         # die contentId steht in beiden, aber nicht notwendig gleich
                self.assertEqual(b"".join(db[rel].lesen()), b"".join(da[rel].lesen()), rel)
            self.assertIn("ampr_zstd-000.pak", da)
        # Es wurde nichts entpackt: Der Schattenordner ist unveraendert klein, das Archiv wurde nicht angefasst.
        self.assertFalse(g._archiv_schatten_info(spiel)["voll"])
        self.assertFalse(os.path.exists(os.path.join(spiel, "Media", "text.txt")))
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))

    def test_geht_der_strom_nicht_wird_der_rest_vor_dem_bisherigen_weg_entpackt(self) -> None:
        """Packdateien in der Quelle schicken den Lauf auf den bisherigen Weg (``None``): Der braucht den ganzen Ordner."""
        archiv = self._zip("mit_packs.zip", extra={"ampr_zstd-000.pak": b"x" * 100})
        g = _gui(self.tmp)
        spiel = self.schatten(g, archiv)
        self.assertFalse(os.path.exists(os.path.join(spiel, "Media", "text.txt")))
        ergebnis = g._mode_exfat_umpacken_strom(spiel, self.ziel, ordner=True)
        self.assertIsNone(ergebnis, "\n".join(g._log_lines))
        self.assertTrue(g._archiv_schatten_info(spiel)["voll"])
        for rel, daten in self.inhalt.items():
            self.assertEqual(daten, Path(spiel, *rel.split("/")).read_bytes(), rel)
        self.assertEqual(b"x" * 100, Path(spiel, "ampr_zstd-000.pak").read_bytes())

    def test_scheitert_das_entpacken_im_rueckfall_endet_der_weg_mit_false(self) -> None:
        """Gesamtpruefung 14.11.2026, S-F: Der OSError lief bis aus der Sammelschleife - die uebrigen Dateien kamen nicht dran."""
        archiv = self._zip("mit_packs2.zip", extra={"ampr_zstd-000.pak": b"x" * 100})
        g = _gui(self.tmp)
        spiel = self.schatten(g, archiv)
        g._archiv_schatten[g._archiv_schluessel(spiel)]["groesse"] = 1 << 60       # kein Platz fuer den Rest
        self.assertIs(False, g._mode_exfat_umpacken_strom(spiel, self.ziel, ordner=True))
        self.assertFalse(g._archiv_schatten_info(spiel)["voll"])
        self.assertTrue(any("Archiv" in z_ for z_ in g._log_lines), g._log_lines)

    def test_ein_gewoehnlicher_ordner_wird_vom_rueckfall_nicht_beruehrt(self) -> None:
        g = _gui(self.tmp)
        leer = os.path.join(self.tmp, "leer")
        os.makedirs(leer)
        self.assertIsNone(g._mode_exfat_umpacken_strom(leer, self.ziel, ordner=True))     # leerer Ordner: bisheriger Weg
        self.assertEqual({}, g._archiv_schatten)

    def test_das_archiv_wird_nach_dem_lauf_geloescht_wenn_der_anwender_es_wollte(self) -> None:
        g = _gui(self.tmp)
        spiel = self.schatten(g)
        self.assertTrue(g._mode_exfat_umpacken_strom(spiel, self.ziel, ordner=True), "\n".join(g._log_lines))
        quelle = g._quelle_zum_loeschen(spiel)
        self.assertEqual(self.zip, quelle)
        g._lauf_quelle_loeschen = True
        stempel = quelle_loeschen.stempel_nehmen(quelle)
        self.assertTrue(g._quelle_nach_erfolg_loeschen(quelle, os.path.join(self.ziel, "Spiel.exfat"), stempel))
        self.assertFalse(os.path.exists(self.zip), "Gelöscht wird das Archiv, nicht der Schattenordner")


class QuelltextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = Path(APP.__file__).read_text(encoding="utf-8")

    def _methode(self, name: str) -> str:
        baum = ast.parse(self.text)
        knoten = next(k for k in ast.walk(baum) if isinstance(k, ast.FunctionDef) and k.name == name)
        return ast.get_source_segment(self.text, knoten) or ""

    def test_das_fenster_legt_bei_einem_zip_den_schatten_an_und_entpackt_sonst_wie_bisher(self) -> None:
        quelle = self._methode("_archiv_als_quelle")
        self.assertIn('self._archiv_schatten_anlegen(archiv, ziel, passwort)', quelle)
        self.assertIn('endung == ".zip" and self._archiv_strom_gewaehlt()', quelle)
        self.assertIn("archiv_quelle.entpacken(", quelle, "Der bisherige Weg muss bleiben (7z, rar, AES, Rueckfall)")

    def test_der_lauf_bereitet_den_schatten_vor_dem_start_vor(self) -> None:
        quelle = self._methode("_run_engine_thread")
        i = quelle.index("self._archiv_schatten_vorbereiten(mode, src)")
        self.assertLess(i, quelle.index("self._get_expected_output_path(mode, src, dst)"))

    def test_der_strom_liest_den_schatten_aus_dem_archiv_und_der_rueckfall_entpackt(self) -> None:
        quelle = self._methode("_mode_exfat_umpacken_strom")
        self.assertIn("self._archiv_schatten_baum(src, is_ignored_name)", quelle)
        self.assertRegex(self.text, r"@_strom_rueckfall_entpackt_archiv\s+@_strom_rueckfall_nimmt_verzicht_zurueck\s+def _mode_exfat_umpacken_strom")

    def test_nur_ein_zip_wird_im_strom_gelesen(self) -> None:
        """7z und rar sind meist solide gepackt: Jede Datei braeuchte das Dekodieren von vorn."""
        self.assertIn('endung == ".zip"', self._methode("_archiv_als_quelle"))


if __name__ == "__main__":
    unittest.main()
