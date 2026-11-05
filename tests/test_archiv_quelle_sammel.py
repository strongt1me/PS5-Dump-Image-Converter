# -*- coding: utf-8 -*-
"""Archive als Quelle in der Sammelkonvertierung (Aufgabe 5) und auf der Kommandozeile (Aufgabe 1).

Fuer Aufgabe 1 im Fenster gibt es ``test_archiv_quelle.py`` (seit v1.9.70). Hier: der blockierende Entpackweg
(``_archiv_blockierend_entpacken``), die Annahme eines Archivs als Quelle von Aufgabe 5 und der Lauf durch die
Schleife der Sammelkonvertierung, in der jedes Archiv erst drankommt, wenn es gebraucht wird.
"""
from __future__ import annotations

import os
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

try:
    import tkinter as tk
    _WURZEL = tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:   # noqa: BLE001 - keine Anzeige
    TK_DA = False
    _WURZEL = None


def _zip_mit_spiel(ordner: Path, name: str, *, unterordner: str = "") -> Path:
    """Ein ZIP mit einem Mini-Spiel; ``unterordner`` leer = das Spiel liegt an der Wurzel des Archivs."""
    archiv = ordner / name
    kopf = (unterordner.rstrip("/") + "/") if unterordner else ""
    with zipfile.ZipFile(archiv, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(kopf + "sce_sys/param.json", "{}")
        z.writestr(kopf + "eboot.bin", b"ELF" + bytes(4092))
    return archiv


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class BlockierendEntpackenTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        self.app._append_to_log = mock.Mock()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.t = Path(tmp.name)
        # Der Arbeitsordner liegt im Testordner: Es bleibt nichts im echten Temp-Ordner liegen.
        patcher = mock.patch.object(self.app, "_get_runtime_temp_dir", return_value=str(self.t / "arbeit"))
        (self.t / "arbeit").mkdir()
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_spiel_an_der_archivwurzel_heisst_wie_das_archiv(self) -> None:
        archiv = _zip_mit_spiel(self.t, "Mein Spiel.zip")
        wurzel, entpackt, fehler = self.app._archiv_blockierend_entpacken(str(archiv))
        self.assertEqual("", fehler)
        self.assertEqual("Mein Spiel", os.path.basename(wurzel), "nicht der Zufallsname des Entpackordners")
        self.assertTrue(os.path.isfile(os.path.join(wurzel, "sce_sys", "param.json")))
        self.assertTrue(os.path.basename(entpackt).startswith("ps5conv_archiv_"))

    def test_spiel_im_unterordner_wird_gefunden(self) -> None:
        archiv = _zip_mit_spiel(self.t, "x.zip", unterordner="PPSA01234")
        wurzel, entpackt, fehler = self.app._archiv_blockierend_entpacken(str(archiv))
        self.assertEqual("", fehler)
        self.assertEqual("PPSA01234", os.path.basename(wurzel))

    def test_archiv_ohne_spiel_ist_ein_fehler_und_hinterlaesst_nichts(self) -> None:
        archiv = self.t / "leer.zip"
        with zipfile.ZipFile(archiv, "w") as z:
            z.writestr("nur/eine.txt", "x")
        wurzel, entpackt, fehler = self.app._archiv_blockierend_entpacken(str(archiv))
        self.assertEqual(("", ""), (wurzel, entpackt))
        self.assertTrue(fehler)
        self.assertEqual([], os.listdir(self.t / "arbeit"), "der Entpackordner ist weg")

    def test_kein_zip_ist_ein_fehler(self) -> None:
        archiv = self.t / "kaputt.zip"
        archiv.write_bytes(b"das ist kein zip")
        _wurzel, entpackt, fehler = self.app._archiv_blockierend_entpacken(str(archiv))
        self.assertEqual("", entpackt)
        self.assertTrue(fehler)
        self.assertEqual([], os.listdir(self.t / "arbeit"))

    def test_7z_ohne_siebenzip_wird_gemeldet(self) -> None:
        archiv = self.t / "x.7z"
        archiv.write_bytes(b"7z")
        with mock.patch.object(self.haupt.archiv_quelle, "siebenzip_suchen", return_value=""):
            _wurzel, entpackt, fehler = self.app._archiv_blockierend_entpacken(str(archiv))
        self.assertEqual("", entpackt)
        self.assertTrue(fehler)
        self.assertEqual([], os.listdir(self.t / "arbeit"), "vor dem Anlegen eines Ordners gemeldet")

    def test_wegraeumen_entfernt_nur_eigene_entpackordner(self) -> None:
        fremd = self.t / "wichtig"
        fremd.mkdir()
        (fremd / "a.txt").write_text("x")
        self.app._archiv_ordner_wegraeumen(str(fremd))
        self.assertTrue((fremd / "a.txt").is_file(), "ein Ordner ohne das Kennzeichen bleibt")
        eigen = self.t / "ps5conv_archiv_probe"
        eigen.mkdir()
        self.app._archiv_ordner_wegraeumen(str(eigen))
        self.assertFalse(eigen.exists())
        self.app._archiv_ordner_wegraeumen("")        # leer: nichts zu tun, kein Fehler


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class AnnahmeTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def test_aufgabe_5_nimmt_ein_archiv_an(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            for endung in (".zip", ".7z", ".rar", ".ZIP"):
                with self.subTest(endung=endung):
                    pfad = Path(t) / ("spiel" + endung)
                    pfad.write_bytes(b"x")
                    self.assertEqual("", self.app._validate_source_path(str(pfad), "batch_convert"))

    def test_aufgabe_5_lehnt_andere_dateien_weiter_ab(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            pfad = Path(t) / "notizen.txt"
            pfad.write_bytes(b"x")
            self.assertNotEqual("", self.app._validate_source_path(str(pfad), "batch_convert"))

    def test_andere_aufgaben_nehmen_kein_archiv_an(self) -> None:
        """Nur Aufgabe 1 (eigener Weg) und 5 kennen Archive; die uebrigen Pruefungen bleiben wie sie waren."""
        with tempfile.TemporaryDirectory() as t:
            pfad = Path(t) / "spiel.zip"
            pfad.write_bytes(b"x")
            for modus in ("unpack_to_exfat", "pack_file", "ffpkg_to_ffpfsc", "universal_convert", "dump_validator"):
                with self.subTest(modus=modus):
                    self.assertNotEqual("", self.app._validate_source_path(str(pfad), modus))

    def test_ein_archiv_bleibt_in_der_sammelliste_stehen(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            pfad = Path(t) / "spiel.zip"
            pfad.write_bytes(b"x")
            self.assertEqual([str(pfad)], self.app._sammelquellen_aufloesen([str(pfad)]))

    def test_der_dateidialog_der_sammelkonvertierung_zeigt_archive(self) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        with mock.patch.object(haupt.filedialog, "askopenfilenames", return_value=()) as dialog, \
                mock.patch.object(self.app, "_auswahl_dialog", return_value=self.app._t("batch.wahl_dateien")):
            self.app._sammelquellen_waehlen(".")
        self.assertIn("*.zip *.7z *.rar", str(dialog.call_args.kwargs["filetypes"]))


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class SchleifenTests(unittest.TestCase):
    """Die Schleife von Aufgabe 5 mit Archiven in der Liste - Umwandlung und Pruefung sind ersetzt."""

    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.t = Path(tmp.name)
        (self.t / "arbeit").mkdir()
        (self.t / "ziel").mkdir()
        self.gesehen: list[tuple[str, bool]] = []     # (Quelle, existierte der Ordner beim Umwandeln)
        app = self.app
        app.is_running = True
        app.root = None                                # kein Fenster: keine Rueckfragen der Vorpruefung
        patches = [
            mock.patch.object(app, "_get_runtime_temp_dir", return_value=str(self.t / "arbeit")),
            mock.patch.object(app, "_get_selected_target_type", return_value="ffpfsc"),
            mock.patch.object(app, "_batch_spiel_zeigen"),
            mock.patch.object(app, "_batch_cover_vorladen"),
            mock.patch.object(app, "_append_to_log"),
            mock.patch.object(app, "_conversion_block_reason", return_value=""),
            mock.patch.object(app, "_batch_ueberschreiben_klaeren", return_value=True),
            mock.patch.object(app, "_batch_arbeitskopien_raeumen"),
            mock.patch.object(app, "_verify_output_artifact", return_value={"ok": True, "detail": "ok"}),
            mock.patch.object(app, "_execute_conversion_by_type", side_effect=self._umwandeln),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def _umwandeln(self, source_type, target_type, src, dst):
        self.gesehen.append((src, os.path.isfile(os.path.join(src, "sce_sys", "param.json"))))
        self.app.task_final_output_path = os.path.join(dst, os.path.basename(src) + ".ffpfsc")
        return True

    def _lauf(self, quellen: list[Path]):
        self.app._batch_sources = [str(q) for q in quellen]
        ok = self.app._run_flexible_conversion("batch_convert", str(quellen[0]), str(self.t / "ziel"))
        return ok, self.app.task_batch_results

    def test_ein_archiv_wird_entpackt_umgewandelt_und_wieder_entfernt(self) -> None:
        archiv = _zip_mit_spiel(self.t, "Spiel Eins.zip")
        ok, ergebnisse = self._lauf([archiv])
        self.assertTrue(ok)
        self.assertEqual(1, len(self.gesehen))
        quelle, da = self.gesehen[0]
        self.assertTrue(da, "beim Umwandeln lag der entpackte Spielordner da")
        self.assertEqual("Spiel Eins", os.path.basename(quelle))
        self.assertEqual(str(archiv), ergebnisse[0]["source"], "das Ergebnis nennt das Archiv, nicht den Temp-Ordner")
        self.assertEqual([], os.listdir(self.t / "arbeit"), "nach dem Lauf liegt nichts mehr da")

    def test_mehrere_archive_und_ein_ordner_nacheinander(self) -> None:
        a = _zip_mit_spiel(self.t, "A.zip")
        b = _zip_mit_spiel(self.t, "B.zip", unterordner="PPSA00002")
        ordner = self.t / "C"
        (ordner / "sce_sys").mkdir(parents=True)
        (ordner / "sce_sys" / "param.json").write_text("{}")
        (ordner / "eboot.bin").write_bytes(b"ELF" + bytes(100))
        ok, ergebnisse = self._lauf([a, ordner, b])
        self.assertTrue(ok)
        self.assertEqual(["A", "C", "PPSA00002"], [os.path.basename(s) for s, _ in self.gesehen])
        self.assertTrue(all(da for _s, da in self.gesehen))
        self.assertEqual([str(a), str(ordner), str(b)], [e["source"] for e in ergebnisse])
        self.assertEqual([], os.listdir(self.t / "arbeit"))

    def test_bei_jedem_archiv_liegt_hoechstens_ein_entpackordner_da(self) -> None:
        """Platz: Das Archiv davor wird weggeraeumt, bevor das naechste entpackt wird."""
        a = _zip_mit_spiel(self.t, "A.zip")
        b = _zip_mit_spiel(self.t, "B.zip")
        anzahl: list[int] = []

        def umwandeln(source_type, target_type, src, dst):
            anzahl.append(len(os.listdir(self.t / "arbeit")))
            return self._umwandeln(source_type, target_type, src, dst)

        with mock.patch.object(self.app, "_execute_conversion_by_type", side_effect=umwandeln):
            ok, _ergebnisse = self._lauf([a, b])
        self.assertTrue(ok)
        self.assertEqual([1, 1], anzahl)

    def test_ein_kaputtes_archiv_ist_ein_fehlschlag_aber_die_naechste_quelle_laeuft(self) -> None:
        kaputt = self.t / "kaputt.zip"
        kaputt.write_bytes(b"kein zip")
        gut = _zip_mit_spiel(self.t, "Gut.zip")
        ok, ergebnisse = self._lauf([kaputt, gut])
        self.assertFalse(ok)
        self.assertEqual([False, True], [e["ok"] for e in ergebnisse])
        self.assertEqual(str(kaputt), ergebnisse[0]["source"])
        self.assertTrue(ergebnisse[0]["detail"])
        self.assertEqual(1, len(self.gesehen), "nur das gute Archiv wurde umgewandelt")
        self.assertEqual([], os.listdir(self.t / "arbeit"))

    def test_ein_archiv_ohne_spiel_ist_ein_fehlschlag(self) -> None:
        leer = self.t / "nichts.zip"
        with zipfile.ZipFile(leer, "w") as z:
            z.writestr("a.txt", "x")
        ok, ergebnisse = self._lauf([leer])
        self.assertFalse(ok)
        self.assertEqual([], self.gesehen)
        self.assertFalse(ergebnisse[0]["ok"])

    def test_abbruch_vor_dem_archiv_laesst_nichts_liegen(self) -> None:
        a = _zip_mit_spiel(self.t, "A.zip")
        b = _zip_mit_spiel(self.t, "B.zip")

        def umwandeln(source_type, target_type, src, dst):
            self.app.is_running = False                  # Abbruch waehrend des ersten Archivs
            return self._umwandeln(source_type, target_type, src, dst)

        with mock.patch.object(self.app, "_execute_conversion_by_type", side_effect=umwandeln):
            ok, _ergebnisse = self._lauf([a, b])
        self.assertFalse(ok)
        self.assertEqual(1, len(self.gesehen), "das zweite Archiv kam nicht mehr dran")
        self.assertEqual([], os.listdir(self.t / "arbeit"), "auch beim Abbruch ist der Entpackordner weg")

    def test_das_passwort_der_kommandozeile_wird_weitergereicht(self) -> None:
        archiv = _zip_mit_spiel(self.t, "A.zip")
        self.app._cli_archiv_passwort = "geheim"
        self.addCleanup(lambda: setattr(self.app, "_cli_archiv_passwort", ""))
        echt = self.app._archiv_blockierend_entpacken
        with mock.patch.object(self.app, "_archiv_blockierend_entpacken", side_effect=echt) as entpacken:
            self._lauf([archiv])
        self.assertEqual("geheim", entpacken.call_args.kwargs["passwort"])


class KommandozeileTests(unittest.TestCase):

    def test_der_schalter_steht_in_der_hilfe(self) -> None:
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        self.assertIn('"--archiv-passwort"', quelle)
        self.assertIn("archiv_quelle.ist_archiv(sources[0])", quelle, "Aufgabe 1 entpackt ein Archiv als --source")

    def test_endungen_sind_dieselben_wie_im_modul(self) -> None:
        from ps5_validator.utils import abbild_pruefen
        self.assertIs(abbild_pruefen._ARCHIV_ENDUNGEN, archiv_quelle.ENDUNGEN)


if __name__ == "__main__":
    unittest.main()
