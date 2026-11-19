# -*- coding: utf-8 -*-
"""Die Groessenzaehlung eines Ordners: ``file_io.groesse_summieren`` und ``ps5_pkg_werkzeug.ordner_groesse`` (19.11.2026).

Gemessen am 18./19.11.2026: Ghost of Yotei (84.218 Dateien, 150,75 GB) brauchte mit ``os.walk`` und ``os.path.getsize`` je Datei 348 s,
mit ``os.scandir`` und ``DirEntry.stat()`` rund 14 s - bei denselben Dateien und denselben Bytes. Die Tests halten fest, dass die neue
Zaehlung dasselbe zaehlt wie die alte (Summe, Dateizahl), und was sie besser macht: Fehler werden nicht verschluckt, Verbindungen
(Junctions) nicht verfolgt, ein Abbruch greift auch in einem Ordner mit sehr vielen Dateien.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import file_io                    # noqa: E402
from ps5_validator.utils import ps5_pkg_werkzeug as wz     # noqa: E402


def _walk_summe(ordner: str) -> tuple[int, int]:
    """Die alte Zaehlung - Gegenstueck fuer den Vergleich."""
    summe = anzahl = 0
    for wurzel, _o, dateien in os.walk(ordner):
        for name in dateien:
            summe += os.path.getsize(os.path.join(wurzel, name))
            anzahl += 1
    return summe, anzahl


class _Baum(unittest.TestCase):
    def setUp(self) -> None:
        self.wurzel = tempfile.mkdtemp(prefix="groesse_zaehlen_")
        self.addCleanup(shutil.rmtree, self.wurzel, True)
        for relativ, inhalt in (("a.bin", b"x" * 10), ("u1/b.bin", b"y" * 200), ("u1/u2/c.bin", b"z" * 3000),
                                ("u1/u2/d.bin", b"w" * 40000), ("leer/.platzhalter", b"")):
            pfad = Path(self.wurzel, relativ)
            pfad.parent.mkdir(parents=True, exist_ok=True)
            pfad.write_bytes(inhalt)
        os.makedirs(os.path.join(self.wurzel, "ganz_leer"))

    def _verknuepfung(self, ziel: str, name: str) -> "str | None":
        """Legt ``name`` als Verknuepfung auf Ordner ``ziel`` an; ``None``, wenn das Recht fehlt (WinError 1314)."""
        pfad = os.path.join(self.wurzel, name)
        try:
            os.symlink(ziel, pfad, target_is_directory=True)
        except (OSError, NotImplementedError):
            return None
        return pfad

    def _verbindung(self, ziel: str, name: str) -> "str | None":
        """Legt ``name`` als NTFS-Verbindung (Junction) auf ``ziel`` an - ohne besondere Rechte; ``None`` ausserhalb von Windows."""
        if sys.platform != "win32":
            return None
        pfad = os.path.join(self.wurzel, name)
        lauf = subprocess.run(["cmd", "/c", "mklink", "/J", pfad, ziel], capture_output=True)
        return pfad if lauf.returncode == 0 and os.path.isdir(pfad) else None


class SummierenTests(_Baum):
    def test_summe_und_dateizahl_sind_die_der_alten_zaehlung(self) -> None:
        erg = file_io.groesse_summieren(self.wurzel)
        alt_summe, alt_anzahl = _walk_summe(self.wurzel)
        self.assertEqual((alt_summe, alt_anzahl), (erg.summe, erg.dateien))
        self.assertEqual(10 + 200 + 3000 + 40000, erg.summe)
        self.assertEqual((0, False), (erg.fehler, erg.abgebrochen))

    def test_ein_leerer_oder_fehlender_ordner(self) -> None:
        self.assertEqual((0, 0, 0), tuple(file_io.groesse_summieren(os.path.join(self.wurzel, "ganz_leer"))[:3]))
        erg = file_io.groesse_summieren(os.path.join(self.wurzel, "gibt_es_nicht"))
        self.assertEqual((0, 0, 1), (erg.summe, erg.dateien, erg.fehler), "ein nicht lesbarer Ordner ist ein Fehler, keine Groesse 0")

    def test_der_beobachter_bekommt_nach_jeder_datei_den_stand(self) -> None:
        stand: list = []
        file_io.groesse_summieren(self.wurzel, beobachter=lambda summe, dateien: stand.append((summe, dateien)))
        self.assertEqual(5, len(stand))
        self.assertEqual([1, 2, 3, 4, 5], [d for _s, d in stand])
        self.assertEqual(sorted(s for s, _d in stand), [s for s, _d in stand], "die Summe waechst")

    def test_fehler_werden_gezaehlt_nicht_geworfen(self) -> None:
        echt = os.scandir

        def scandir(pfad):
            if os.path.basename(str(pfad)) == "u2":
                raise PermissionError("verweigert")
            return echt(pfad)
        with mock.patch.object(os, "scandir", side_effect=scandir):
            erg = file_io.groesse_summieren(self.wurzel)
        self.assertEqual(1, erg.fehler)
        self.assertEqual(10 + 200, erg.summe, "u2 fehlt in der Summe - und der Fehler sagt es")

    def test_eine_datei_deren_groesse_nicht_zu_lesen_ist_zaehlt_als_fehler(self) -> None:
        echt = os.DirEntry.stat

        class _Eintrag:
            def __init__(self, e):
                self._e = e

            def __getattr__(self, name):
                return getattr(self._e, name)

            def stat(self, **kw):
                if self._e.name == "b.bin":
                    raise OSError("Datei weg")
                return echt(self._e, **kw)

        echt_scandir = os.scandir

        class _Verzeichnis:
            def __init__(self, pfad):
                self._it = echt_scandir(pfad)

            def __enter__(self):
                return (_Eintrag(e) for e in self._it.__enter__())

            def __exit__(self, *a):
                return self._it.__exit__(*a)
        with mock.patch.object(os, "scandir", side_effect=_Verzeichnis):
            erg = file_io.groesse_summieren(self.wurzel)
        self.assertEqual((1, 4), (erg.fehler, erg.dateien))

    def test_eine_ausnahme_der_rueckrufe_geht_an_den_aufrufer_und_zaehlt_nicht_als_verzeichnisfehler(self) -> None:
        """Beobachter und Abbruch sind Rueckrufe des Aufrufers: Ein ``OSError`` daraus (etwa beim Schreiben der Protokolldatei) liess
        sonst den Rest des Ordners still aus und kam nur als "ein Fehler" zurueck (Gegenlese 19.11.2026)."""
        def beobachter(_summe: int, _dateien: int) -> None:
            raise OSError("Protokoll nicht beschreibbar")

        def abbruch() -> bool:
            raise OSError("Abbruchabfrage kaputt")
        for name, kw in (("beobachter", {"beobachter": beobachter}), ("abbruch", {"abbruch": abbruch})):
            with self.subTest(rueckruf=name), self.assertRaises(OSError):
                file_io.groesse_summieren(self.wurzel, **kw)

    def test_ein_verzeichnis_das_mitten_im_lesen_scheitert_zaehlt_als_ein_fehler_und_behaelt_die_bisherige_summe(self) -> None:
        echt = os.scandir

        class _Bricht:
            def __init__(self, pfad):
                self._it = echt(pfad)

            def __enter__(self):
                def erzeugen():
                    for i, e in enumerate(self._it):
                        if i == 1:
                            raise PermissionError("mitten im Lesen")
                        yield e
                return erzeugen()

            def __exit__(self, *a):
                return self._it.__exit__(*a)

        def scandir(pfad):
            return _Bricht(pfad) if os.path.basename(str(pfad)) == "u1" else echt(pfad)
        with mock.patch.object(os, "scandir", side_effect=scandir):
            erg = file_io.groesse_summieren(self.wurzel)
        self.assertEqual(1, erg.fehler)
        self.assertGreaterEqual(erg.summe, 10, "was vorher gezaehlt war, bleibt")
        self.assertLess(erg.summe, 43210, "der Rest des Verzeichnisses fehlt - und der Fehler sagt es")

    def test_ein_verschwundener_eintrag_ist_kein_fehler_wie_bei_os_walk(self) -> None:
        """Gelesen, bevor die Datei verschwand (oder ein Symlink ohne Ziel): ``os.walk`` und ``getsize`` liessen sie still aus - das
        ganze Spiel darf deshalb nicht auf "Groesse unbekannt" stehen (Korrektur-Pruefung 19.11.2026; unter Linux/macOS fragt
        ``DirEntry.stat()`` wirklich ab)."""
        echt_scandir = os.scandir

        class _Eintrag:
            def __init__(self, e):
                self._e = e

            def __getattr__(self, name):
                return getattr(self._e, name)

            def stat(self, **kw):
                if self._e.name == "b.bin":
                    raise FileNotFoundError("verschwunden")
                return self._e.stat(**kw)

        class _Verzeichnis:
            def __init__(self, pfad):
                self._it = echt_scandir(pfad)

            def __enter__(self):
                return (_Eintrag(e) for e in self._it.__enter__())

            def __exit__(self, *a):
                return self._it.__exit__(*a)
        with mock.patch.object(os, "scandir", side_effect=_Verzeichnis):
            erg = file_io.groesse_summieren(self.wurzel)
        self.assertEqual((0, 4, 10 + 3000 + 40000), (erg.fehler, erg.dateien, erg.summe))

    def test_ein_unterordner_der_waehrend_des_zaehlens_verschwindet_ist_kein_fehler_die_wurzel_schon(self) -> None:
        echt = os.scandir

        def scandir(pfad):
            if os.path.basename(str(pfad)) == "u2":
                raise FileNotFoundError("verschwunden")
            return echt(pfad)
        with mock.patch.object(os, "scandir", side_effect=scandir):
            erg = file_io.groesse_summieren(self.wurzel)
        self.assertEqual((0, 10 + 200), (erg.fehler, erg.summe))
        self.assertEqual(1, file_io.groesse_summieren(os.path.join(self.wurzel, "gibt_es_nicht")).fehler, "die Wurzel selbst fehlt: Fehler")

    def test_ein_kaputter_symlink_macht_die_groesse_nicht_unbekannt(self) -> None:
        pfad = os.path.join(self.wurzel, "kaputt")
        try:
            os.symlink(os.path.join(self.wurzel, "gibt_es_nicht.bin"), pfad)
        except (OSError, NotImplementedError):
            self.skipTest("Verknuepfungen brauchen ein Recht (WinError 1314)")
        erg = file_io.groesse_summieren(self.wurzel)
        self.assertEqual((0, 5), (erg.fehler, erg.dateien))

    def test_genau_fragt_jede_datei_mit_os_stat_die_schnelle_zaehlung_keine(self) -> None:
        """Unter Windows bleibt ``DirEntry.stat().st_size`` bei einer Datei im Schreiben auf dem alten Stand (gemessen: 0 Bytes bei einem
        offenen Schreiber, ``os.stat`` 4 bis 400 MB): Der Fortschritt beim Kopieren braucht ``genau``."""
        with mock.patch.object(os, "stat", wraps=os.stat) as stat:
            schnell = file_io.groesse_summieren(self.wurzel)
        schnell_aufrufe = stat.call_count
        with mock.patch.object(os, "stat", wraps=os.stat) as stat:
            genau = file_io.groesse_summieren(self.wurzel, genau=True)
        self.assertEqual(0, schnell_aufrufe, "die schnelle Zaehlung ruft os.stat nicht je Datei")
        self.assertEqual(5, stat.call_count, "genau: ein os.stat je Datei")
        self.assertEqual(schnell, genau, "bei ruhenden Dateien dieselbe Summe")

    def test_genau_zaehlt_eine_offene_datei_im_schreiben_mit_ihrer_echten_groesse(self) -> None:
        pfad = os.path.join(self.wurzel, "wird_geschrieben.bin")
        with open(pfad, "wb") as datei:
            datei.write(b"\0" * (1024 * 1024))
            datei.flush()
            erg = file_io.groesse_summieren(self.wurzel, genau=True)
        self.assertEqual(43210 + 1024 * 1024, erg.summe)

    def test_abbruch_wird_je_verzeichnis_gefragt(self) -> None:
        aufrufe: list = []

        def abbruch() -> bool:
            aufrufe.append(1)
            return len(aufrufe) >= 2
        erg = file_io.groesse_summieren(self.wurzel, abbruch=abbruch)
        self.assertTrue(erg.abgebrochen)
        self.assertLess(erg.dateien, 5)

    def test_abbruch_greift_auch_in_einem_ordner_mit_sehr_vielen_dateien(self) -> None:
        gross = os.path.join(self.wurzel, "gross")
        os.makedirs(gross)
        for i in range(1300):
            Path(gross, "%04d.bin" % i).write_bytes(b"1")
        gefragt: list = []

        def abbruch() -> bool:
            gefragt.append(1)
            return len(gefragt) > 1                          # beim ersten Verzeichnis nicht, danach (alle 512 Dateien) ja
        erg = file_io.groesse_summieren(gross, abbruch=abbruch)
        self.assertTrue(erg.abgebrochen)
        self.assertLessEqual(erg.dateien, 512, "nach 512 Dateien ist Schluss, nicht erst am Ende des Ordners")

    def test_eine_verknuepfung_auf_einen_ordner_wird_nicht_verfolgt_und_nicht_gezaehlt(self) -> None:
        pfad = self._verknuepfung(os.path.join(self.wurzel, "u1"), "link_u1")
        if pfad is None:
            self.skipTest("Verknuepfungen brauchen ein Recht (WinError 1314)")
        erg = file_io.groesse_summieren(self.wurzel)
        self.assertEqual((10 + 200 + 3000 + 40000, 5), (erg.summe, erg.dateien), "wie os.walk: weder Ordnergroesse noch Inhalt")

    def test_eine_verbindung_wird_nach_vorgabe_nicht_verfolgt_auf_wunsch_schon(self) -> None:
        """``os.walk`` hielt eine Junction fuer einen gewoehnlichen Ordner: Zeigt sie auf einen Elternordner, lief es bis zur Pfadgrenze."""
        pfad = self._verbindung(os.path.join(self.wurzel, "u1"), "verbindung_u1")
        if pfad is None:
            self.skipTest("keine NTFS-Verbindung moeglich")
        ohne = file_io.groesse_summieren(self.wurzel)
        self.assertEqual((43210, 5), (ohne.summe, ohne.dateien), "die Verbindung zaehlt nicht doppelt")
        mit = file_io.groesse_summieren(self.wurzel, verbindungen_folgen=True)
        self.assertEqual((43210 + 40000 + 3000 + 200, 8), (mit.summe, mit.dateien), "wie das Hauptfenster bisher: folgen")

    def test_eine_verbindung_auf_den_elternordner_ist_keine_endlosschleife(self) -> None:
        pfad = self._verbindung(self.wurzel, os.path.join("u1", "u2", "zurueck"))
        if pfad is None:
            self.skipTest("keine NTFS-Verbindung moeglich")
        erg = file_io.groesse_summieren(self.wurzel)
        self.assertEqual((43210, 5), (erg.summe, erg.dateien))


class OrdnerGroesseTests(_Baum):
    def test_die_summe(self) -> None:
        zeilen: list = []
        self.assertEqual(43210, wz.ordner_groesse(self.wurzel, zeilen.append))
        self.assertEqual(1, len(zeilen))
        self.assertIn("5 Dateien", zeilen[0])

    def test_nicht_lesbares_wirft_und_warnt_statt_eine_teilsumme_zu_liefern(self) -> None:
        echt = os.scandir

        def scandir(pfad):
            if os.path.basename(str(pfad)) == "u2":
                raise PermissionError("verweigert")
            return echt(pfad)
        zeilen: list = []
        with mock.patch.object(os, "scandir", side_effect=scandir), self.assertRaises(OSError) as ctx:
            wz.ordner_groesse(self.wurzel, zeilen.append)
        self.assertIn("nicht lesbar", str(ctx.exception))
        self.assertEqual(1, len(zeilen))
        self.assertIn("[WARNUNG]", zeilen[0])
        self.assertIn("1 Eintraege", zeilen[0])

    def test_eine_teilsumme_steht_als_untergrenze_in_der_ausnahme(self) -> None:
        """Einzelne nicht lesbare Eintraege (``System Volume Information``): Die Summe ist eine untere Schranke und geht in die
        Platzpruefung ein - sie ist nur nicht die Groesse (Gegenlese 19.11.2026)."""
        echt = os.scandir

        def scandir(pfad):
            if os.path.basename(str(pfad)) == "u2":
                raise PermissionError("verweigert")
            return echt(pfad)
        zeilen: list = []
        with mock.patch.object(os, "scandir", side_effect=scandir), self.assertRaises(wz.GroesseUnvollstaendig) as ctx:
            wz.ordner_groesse(self.wurzel, zeilen.append)
        self.assertIsInstance(ctx.exception, OSError, "wer \"nicht lesbar\" schon abfaengt, funktioniert weiter")
        self.assertEqual((10 + 200, 3), (ctx.exception.summe, ctx.exception.dateien), "a.bin, b.bin und die leere Datei in leer/")
        self.assertIn("mindestens", zeilen[0])

    def test_ist_nichts_zu_zaehlen_gibt_es_keine_untergrenze(self) -> None:
        with self.assertRaises(OSError) as ctx:
            wz.ordner_groesse(os.path.join(self.wurzel, "gibt_es_nicht"))
        self.assertNotIsInstance(ctx.exception, wz.GroesseUnvollstaendig, "eine Untergrenze von 0 waere keine Angabe")

    def test_ordner_lesen_macht_aus_einer_teilsumme_eine_untergrenze_keine_unbekannte_groesse(self) -> None:
        sce = Path(self.wurzel, "sce_sys")
        sce.mkdir()
        sce.joinpath("param.json").write_text('{"titleId": "PPSA00001", "contentId": "UP0000-PPSA00001_00-AAAAAAAAAAAAAAAA"}',
                                              encoding="utf-8")
        with mock.patch.object(wz, "ordner_groesse", side_effect=wz.GroesseUnvollstaendig("2 Eintraege", 123, 4)):
            info = wz.ordner_lesen(self.wurzel, self.wurzel, groesse=True)
        self.addCleanup(shutil.rmtree, info.arbeit or self.wurzel, True)
        self.assertEqual((123, True, False, False), (info.groesse, info.groesse_unvollstaendig, info.groesse_unbekannt, info.groesse_offen))

    def test_der_fortschritt_kommt_im_meldeschritt(self) -> None:
        gross = os.path.join(self.wurzel, "gross")
        os.makedirs(gross)
        for i in range(7):
            Path(gross, "%d.bin" % i).write_bytes(b"1")
        gemeldet: list = []
        with mock.patch.object(wz, "GROESSE_MELDESCHRITT", 4):
            wz.ordner_groesse(self.wurzel, fortschritt=gemeldet.append)
        self.assertEqual([4, 8, 12], gemeldet, "12 Dateien (5 im Baum, 7 dazu), alle 4 eine Meldung")

    def test_ein_abbruch_wirft_groesse_abgebrochen(self) -> None:
        with self.assertRaises(wz.GroesseAbgebrochen):
            wz.ordner_groesse(self.wurzel, abbruch=lambda: True)

    def test_ordner_lesen_mit_groesse_macht_aus_einem_fehler_eine_unbekannte_groesse(self) -> None:
        sce = Path(self.wurzel, "sce_sys")
        sce.mkdir()
        sce.joinpath("param.json").write_text('{"titleId": "PPSA00001", "contentId": "UP0000-PPSA00001_00-AAAAAAAAAAAAAAAA"}',
                                              encoding="utf-8")
        with mock.patch.object(wz, "ordner_groesse", side_effect=OSError("Laufwerk weg")):
            info = wz.ordner_lesen(self.wurzel, self.wurzel, groesse=True)
        self.addCleanup(shutil.rmtree, info.arbeit or self.wurzel, True)
        self.assertEqual((0, True, False), (info.groesse, info.groesse_unbekannt, info.groesse_offen))


class PfadGroesseDesHauptfensters(_Baum):
    """``_get_path_size`` (Aufgaben 1-8): reicht ``genau`` und das Folgen von Verbindungen an die Zaehlung weiter (Gegenlese 19.11.2026:
    die Pruefung ``_poll`` sah nur den Text, kein Test rief die Funktion selbst)."""

    def _groesse(self, pfad: str, **kw) -> int:
        import types
        import PS5ImageConverter_Pro_FINAL_revised as app           # noqa: E402 - schwer, nur fuer diese Tests
        attrappe = types.SimpleNamespace(_archiv_schatten_info=lambda _p: None)
        return app.PS5ConverterGUI._get_path_size(attrappe, pfad, **kw)

    def test_genau_zaehlt_eine_offene_datei_im_schreiben_mit_ihrer_echten_groesse(self) -> None:
        pfad = os.path.join(self.wurzel, "wird_geschrieben.bin")
        with open(pfad, "wb") as datei:
            datei.write(b"\0" * (1024 * 1024))
            datei.flush()
            gemessen = self._groesse(self.wurzel, genau=True)
        self.assertEqual(43210 + 1024 * 1024, gemessen, "``genau=True`` kommt bei der Zaehlung an (``os.stat`` je Datei)")

    def test_genau_kommt_als_schluesselwort_an_die_zaehlung(self) -> None:
        with mock.patch.object(file_io, "groesse_summieren", wraps=file_io.groesse_summieren) as zaehlen:
            self._groesse(self.wurzel, genau=True)
            self._groesse(self.wurzel)
        self.assertEqual([True, False], [aufruf.kwargs.get("genau") for aufruf in zaehlen.call_args_list])
        self.assertTrue(all(aufruf.kwargs.get("verbindungen_folgen") is True for aufruf in zaehlen.call_args_list),
                        "das Hauptfenster folgt Verbindungen wie ``os.walk`` bisher")

    def test_eine_verbindung_wird_im_hauptfenster_wie_frueher_verfolgt(self) -> None:
        if self._verbindung(os.path.join(self.wurzel, "u1"), "verbindung_u1") is None:
            self.skipTest("keine NTFS-Verbindung moeglich")
        self.assertEqual(43210 + 40000 + 3000 + 200, self._groesse(self.wurzel))


class AbfrageDesZielsTests(unittest.TestCase):
    def test_wer_das_ziel_waehrend_des_kopierens_abfragt_verlangt_genaue_groessen(self) -> None:
        """Die Abfrager (``_poll`` der Kopier- und Entpackvorgaenge) lesen ein Ziel, in das gerade geschrieben wird: Die schnelle
        Zaehlung zeigte dort 0 Bytes statt des Standes (Korrektur-Pruefung 19.11.2026) - Prozent und MB/s standen still."""
        import ast
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8-sig")
        gefunden = []
        for f in ast.walk(ast.parse(quelle)):
            if isinstance(f, ast.FunctionDef) and f.name == "_poll":
                for a in ast.walk(f):
                    if isinstance(a, ast.Call) and isinstance(a.func, ast.Attribute) and a.func.attr == "_get_path_size":
                        gefunden.append(any(k.arg == "genau" and isinstance(k.value, ast.Constant) and k.value.value is True
                                            for k in a.keywords))
        self.assertGreaterEqual(len(gefunden), 2, "beide Abfrager gefunden")
        self.assertTrue(all(gefunden), "jeder Abfrager im Schreiben verlangt genau=True")


if __name__ == "__main__":
    unittest.main()
