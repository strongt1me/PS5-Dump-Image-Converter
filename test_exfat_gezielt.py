# -*- coding: utf-8 -*-
"""Gezielt in einem exFAT-Abbild lesen (``exfat_gezielt``) - gleich wie die Engine, ohne den ganzen Baum (03.10.2026).

Der Anlass: ``mkpfs.exfat.ExfatReader`` liefert Dateien nur ueber ``iter_files()``, und das liest jeden
Verzeichniscluster. Fuer ``DIRT5 (06.004.000).exfat`` (104 GB) brauchte die Bibliothek allein fuer die Angaben mehr
als vier Minuten - und noch einmal so lange fuer die Einbauten. Bewacht wird:

* ``GezielterZugriff``: findet Pfade ohne Beachtung der Schreibung, liest nur die Ordner auf dem Weg (gezaehlt),
  jeden hoechstens einmal, kommt mit einem Verzeichnis ueber mehrere Cluster zurecht, liest nie mehr als erlaubt.
* ``metadaten``: dasselbe Ergebnis wie ``read_game_metadata`` der Engine - an echten ``.exfat``-Abbildern und an einer
  ``.ffpfsc`` mit exFAT darin, auch bei fehlenden Dateien, kaputtem JSON und ungewoehnlichen Schreibungen. Der
  Austausch der Engine-Funktion wird in jedem Fall zurueckgenommen.
* ``einbau_pfade`` (ueber ``_container_dateien(..., gezielt=True)``): dieselben Einbauten wie mit allen Dateien, bei
  Huelle ``app0/``, ``fakelib2``, ``fw<NN>``-Ordnern und Asset-Pack in der Wurzel.
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))
MKPFS_ORDNER = PROJEKT / "MkPFS-1.0.0"
if str(MKPFS_ORDNER) not in sys.path:
    sys.path.insert(0, str(MKPFS_ORDNER))

import PS5ImageConverter_Pro_FINAL_revised as APP  # noqa: E402
from mkpfs import consts, exfat_writer  # noqa: E402
from mkpfs import game_metadata as gm  # noqa: E402
from mkpfs.exfat import ExfatReader  # noqa: E402
from mkpfs.pfs import build_pfs_stream_single_file  # noqa: E402
from ps5_validator.utils import bibliothek as bib  # noqa: E402
from ps5_validator.utils import exfat_gezielt as eg  # noqa: E402

GUI = APP.PS5ConverterGUI
ASSET = GUI._ist_ampr_asset_datei

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
       b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\xe2&\xb3\x00\x00\x00\x00IEND\xaeB`\x82")
PARAM = json.dumps({"contentId": "UP9000-PPSA99999_00-ABCDEFGHIJKLMNOP", "titleId": "PPSA99999",
                    "contentVersion": "01.234",
                    "localizedParameters": {"en-US": {"titleName": "Testspiel"}}}).encode("utf-8")


def _quelle(basis: Path, name: str, dateien: dict[str, bytes]) -> Path:
    quelle = basis / name
    quelle.mkdir(parents=True)
    for rel, inhalt in dateien.items():
        ziel = quelle / rel
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_bytes(inhalt)
    return quelle


def _abbild(quelle: Path) -> Path:
    ziel = quelle.with_suffix(".exfat")
    exfat_writer.write_exfat_image(quelle, ziel)
    return ziel


def _spiel() -> dict[str, bytes]:
    """Die Dateien eines kleinen Spiels: param.json, Titelbild, eboot - dazu, was der Test braucht."""
    return {"sce_sys/param.json": PARAM, "sce_sys/icon0.png": PNG, "eboot.bin": b"BOOT"}


class _Basis(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="exfat_gezielt_")
        self.addCleanup(self._tmp.cleanup)
        self.basis = Path(self._tmp.name)


class GezielterZugriffTests(_Basis):

    def _zugriff(self, dateien: dict[str, bytes], name: str = "a"):
        abbild = _abbild(_quelle(self.basis, name, dateien))
        fh = abbild.open("rb")
        self.addCleanup(fh.close)
        return eg.GezielterZugriff(ExfatReader(fh)), ExfatReader(fh)

    def test_findet_pfade_ohne_beachtung_der_schreibung_und_liest_die_bytes(self) -> None:
        zugriff, _leser = self._zugriff({"SCE_SYS/Param.JSON": PARAM, "Fakelib/LibSceAmpr.SPRX": b"x"})
        param = zugriff.suchen("sce_sys", "param.json")
        self.assertIsNotNone(param)
        self.assertEqual(PARAM, zugriff.lesen(param))
        self.assertIsNotNone(zugriff.suchen("FAKELIB", "libsceampr.sprx"))

    def test_nicht_vorhandenes_und_falsche_wege_sind_none(self) -> None:
        zugriff, _leser = self._zugriff(_spiel())
        self.assertIsNone(zugriff.suchen("sce_sys", "gibtesnicht.bin"))
        self.assertIsNone(zugriff.suchen("nirgends", "param.json"))
        self.assertIsNone(zugriff.suchen("eboot.bin", "darunter"), "Durch eine Datei gibt es keinen Weg.")

    def test_nur_die_ordner_auf_dem_weg_werden_gelesen(self) -> None:
        """Das Ziel der Sache: Ein Spiel mit vielen Ordnern kostet nicht mehr als eines mit wenigen."""
        dateien = _spiel()
        for n in range(60):
            dateien["daten/ebene%02d/unter/datei%02d.bin" % (n, n)] = b"d" * 10
        zugriff, leser = self._zugriff(dateien)
        param = zugriff.suchen("sce_sys", "param.json")
        self.assertEqual(PARAM, zugriff.lesen(param))
        self.assertEqual(2, zugriff.gelesene_ordner, "Wurzel und sce_sys - mehr nicht.")
        gezaehlt = {"n": 0}
        echt = leser._read_directory_entries

        def _zaehlen(*a, **k):
            gezaehlt["n"] += 1
            return echt(*a, **k)

        leser._read_directory_entries = _zaehlen
        list(leser.iter_files())
        self.assertGreater(gezaehlt["n"], 100, "Ohne diesen Befund misst der Vergleich nichts: Der volle Rundgang liest viele Ordner.")

    def test_ein_ordner_wird_hoechstens_einmal_gelesen(self) -> None:
        zugriff, _leser = self._zugriff(_spiel())
        for name in ("param.json", "icon0.png", "param.json"):
            self.assertIsNotNone(zugriff.suchen("sce_sys", name))
        self.assertEqual(2, zugriff.gelesene_ordner)

    def test_ein_verzeichnis_ueber_mehrere_cluster(self) -> None:
        """Rund 340 Dateien mit langem Namen fuellen einen 64-KiB-Cluster; hier sind es 420."""
        dateien = _spiel()
        for n in range(420):
            dateien["sce_sys/%s%03d.dat" % ("x" * 56, n)] = b"1"
        zugriff, _leser = self._zugriff(dateien)
        letzte = zugriff.suchen("sce_sys", "%s%03d.dat" % ("x" * 56, 419))
        self.assertIsNotNone(letzte, "Die letzte Datei eines Verzeichnisses ueber mehrere Cluster wurde nicht gefunden.")
        self.assertIsNotNone(zugriff.suchen("sce_sys", "param.json"))
        self.assertEqual(2, zugriff.gelesene_ordner)

    def test_lesen_beachtet_die_grenze_und_nimmt_nur_dateien(self) -> None:
        zugriff, _leser = self._zugriff({"sce_sys/gross.bin": b"g" * 5000, "sce_sys/leer.bin": b""})
        gross = zugriff.suchen("sce_sys", "gross.bin")
        self.assertEqual(b"g" * 5000, zugriff.lesen(gross, 10000))
        self.assertIsNone(zugriff.lesen(gross, 4999), "Groesser als erlaubt wird nicht gelesen.")
        self.assertIsNone(zugriff.lesen(zugriff.suchen("sce_sys", "leer.bin")))
        self.assertIsNone(zugriff.lesen(zugriff.suchen("sce_sys")), "Ein Ordner hat keine Bytes.")


def _felder(m) -> tuple:
    return (m.error, m.package_type, m.game_title, m.title_id, m.content_id, m.version, m.region,
            m.has_apr_emu, m.icon_bytes, m.file_size)


class MetadatenParitaetTests(_Basis):
    """Dasselbe Ergebnis wie ``read_game_metadata`` - nur ohne den ganzen Baum."""

    def _vergleichen(self, abbild: Path) -> None:
        echt = gm.read_game_metadata(abbild)
        gezielt = eg.metadaten(str(abbild), gm)
        self.assertIsNotNone(gezielt)
        self.assertEqual(_felder(echt), _felder(gezielt))

    def test_ein_vollstaendiges_abbild(self) -> None:
        abbild = _abbild(_quelle(self.basis, "a", _spiel() | {"fakelib/libSceAmpr.sprx": b"emu"}))
        self._vergleichen(abbild)
        gezielt = eg.metadaten(str(abbild), gm)
        self.assertEqual(("Testspiel", "PPSA99999", "UP9000-PPSA99999_00-ABCDEFGHIJKLMNOP", "01.234", "USA", True, PNG),
                         (gezielt.game_title, gezielt.title_id, gezielt.content_id, gezielt.version, gezielt.region,
                          gezielt.has_apr_emu, gezielt.icon_bytes))

    def test_ohne_emulation_ohne_bild_ohne_param_json(self) -> None:
        for name, dateien in (("ohne_emu", _spiel()),
                              ("ohne_bild", {"sce_sys/param.json": PARAM, "eboot.bin": b"B"}),
                              ("ohne_param", {"sce_sys/icon0.png": PNG, "eboot.bin": b"B"}),
                              ("ohne_sce_sys", {"eboot.bin": b"B", "daten/a.bin": b"x"})):
            with self.subTest(fall=name):
                self._vergleichen(_abbild(_quelle(self.basis, name, dateien)))

    def test_ungewoehnliche_schreibungen(self) -> None:
        abbild = _abbild(_quelle(self.basis, "gross", {
            "SCE_SYS/PARAM.JSON": PARAM, "SCE_SYS/ICON0.PNG": PNG, "FakeLib/LIBSCEAMPR.SPRX": b"e"}))
        self._vergleichen(abbild)
        self.assertTrue(eg.metadaten(str(abbild), gm).has_apr_emu)

    def test_kaputtes_json_wird_wie_in_der_engine_gemeldet(self) -> None:
        abbild = _abbild(_quelle(self.basis, "kaputt", {"sce_sys/param.json": b"{kein json", "sce_sys/icon0.png": PNG}))
        echt = gm.read_game_metadata(abbild)
        gezielt = eg.metadaten(str(abbild), gm)
        self.assertTrue(echt.error)
        self.assertEqual(echt.error, gezielt.error)

    def test_ein_zu_grosses_titelbild_wird_wie_in_der_engine_uebergangen(self) -> None:
        gross = PNG + b"\0" * (gm._MAX_ICON_SIZE + 10)
        abbild = _abbild(_quelle(self.basis, "gross_bild", {"sce_sys/param.json": PARAM, "sce_sys/icon0.png": gross}))
        self._vergleichen(abbild)
        self.assertIsNone(eg.metadaten(str(abbild), gm).icon_bytes)

    def test_eine_ffpfsc_mit_exfat_darin(self) -> None:
        exfat = _abbild(_quelle(self.basis, "innen", _spiel() | {"fakelib/libSceAmpr.sprx": b"emu"}))
        ausgabe = self.basis / "huelle.ffpfsc"
        build_pfs_stream_single_file(
            source_file=exfat, output_path=ausgabe, block_size=65536, pfs_version=consts.PFS_VERSION_PS5,
            case_insensitive=True, zlib_level=7, threshold_gain=0, min_file_gain=0, min_compress_size=0,
            cpu_count=1, compress=True)
        self._vergleichen(ausgabe)
        gezielt = eg.metadaten(str(ausgabe), gm)
        self.assertEqual("Testspiel", gezielt.game_title)
        self.assertEqual(PNG, gezielt.icon_bytes)
        self.assertTrue(gezielt.package_type.startswith("FFPFSC"))

    def test_die_angaben_kosten_nicht_mehr_ordner_je_groesserem_spiel(self) -> None:
        """Der Kern der Aenderung: Die Engine liest jeden Verzeichniscluster, ``metadaten`` nur drei Ordner."""
        dateien = _spiel() | {"fakelib/libSceAmpr.sprx": b"a"}
        for n in range(60):
            dateien["daten/ebene%02d/unter/datei%02d.bin" % (n, n)] = b"d"
        abbild = _abbild(_quelle(self.basis, "tief", dateien))
        zaehler = {"n": 0}
        echt = ExfatReader._read_directory_entries

        def _zaehlen(selbst, *a, **k):
            zaehler["n"] += 1
            return echt(selbst, *a, **k)

        with mock.patch.object(ExfatReader, "_read_directory_entries", _zaehlen):
            gezielt = eg.metadaten(str(abbild), gm)
            gelesen_gezielt = zaehler["n"]
            zaehler["n"] = 0
            engine = gm.read_game_metadata(abbild)
            gelesen_engine = zaehler["n"]
        self.assertEqual(_felder(engine), _felder(gezielt))
        self.assertLessEqual(gelesen_gezielt, 4, "Wurzel, sce_sys, fakelib (gelesen: %d)." % gelesen_gezielt)
        self.assertGreater(gelesen_engine, 100)

    def test_der_tausch_der_engine_funktion_wird_zurueckgenommen(self) -> None:
        original = gm._fill_from_exfat_reader
        abbild = _abbild(_quelle(self.basis, "a", _spiel()))
        eg.metadaten(str(abbild), gm)
        self.assertIs(original, gm._fill_from_exfat_reader)

    def test_auch_nach_einer_ausnahme_wird_zurueckgenommen(self) -> None:
        original = gm._fill_from_exfat_reader
        abbild = _abbild(_quelle(self.basis, "a", _spiel()))
        with mock.patch.object(gm, "read_game_metadata", side_effect=RuntimeError("boese")) as lesen:
            with self.assertRaises(RuntimeError):
                eg.metadaten(str(abbild), gm)
        lesen.assert_called_once()
        self.assertIs(original, gm._fill_from_exfat_reader, "Die Engine blieb ausgetauscht.")

    def test_andere_endungen_und_eine_fremde_engine_geben_none(self) -> None:
        self.assertIsNone(eg.metadaten(str(self.basis / "x.ffpkg"), gm))
        self.assertIsNone(eg.metadaten(str(self.basis / "x.pkg"), gm))
        fremd = type(sys)("mkpfs.game_metadata")
        fremd.read_game_metadata = lambda p: None
        self.assertIsNone(eg.metadaten(str(self.basis / "x.exfat"), fremd), "Fehlt ein benoetigter Name, ist nichts zu tun.")
        self.assertIsNone(eg.metadaten(str(self.basis / "x.exfat"), None))

    def test_gleichzeitige_aufrufe_stoeren_sich_nicht(self) -> None:
        abbilder = []
        for n in range(6):
            param = json.dumps({"titleId": "PPSA0000%d" % n, "contentId": "UP9000-PPSA0000%d_00-X" % n}).encode()
            abbilder.append(_abbild(_quelle(self.basis, "g%d" % n, {"sce_sys/param.json": param, "sce_sys/icon0.png": PNG})))
        ergebnisse: dict[int, str] = {}

        def _lauf(n: int) -> None:
            for _ in range(5):
                ergebnisse[n] = eg.metadaten(str(abbilder[n]), gm).title_id

        faeden = [threading.Thread(target=_lauf, args=(n,)) for n in range(6)]
        for f in faeden:
            f.start()
        for f in faeden:
            f.join(30)
        self.assertEqual({n: "PPSA0000%d" % n for n in range(6)}, ergebnisse)


class EinbauParitaetTests(_Basis):
    """Dieselben Einbauten wie mit der Liste aller Dateien."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.gui = GUI.__new__(GUI)
        cls.gui._current_language = "de"

    FAELLE = {
        "ampr_playgo_backport": {"fakelib/libSceAmpr.sprx": b"a", "fakelib/libScePlayGo.sprx": b"p",
                                 "fakelib/fw10/libSceRtc.sprx": b"r", "fakelib/fw11/libSceRtc.sprx": b"r"},
        "zwei_ordner": {"fakelib/libSceAmpr.sprx": b"a", "fakelib2/x.sprx": b"x"},
        "fakelib2_gewinnt": {"fakelib/libSceAmpr.sprx": b"a", "fakelib2/libSceAmpr.sprx": b"a"},
        "huelle_app0": {"app0/fakelib/libSceAmpr.sprx": b"a", "app0/fakelib/fw12/y.bin": b"y"},
        "asset_pack": {"ampr_assets.index": b"i", "fakelib/libSceAmpr.sprx": b"a"},
        "nur_ordner_ohne_dateien": {"daten/a.bin": b"a"},
        "nichts": {},
    }

    def _dateien(self, quelle: Path, gezielt: bool) -> list[str] | None:
        return self.gui._container_dateien(str(quelle.with_suffix(".exfat")), roh_exfat=True, gezielt=gezielt)

    def _bewertung(self, dateien) -> dict | None:
        if not dateien:
            return None
        erg = bib.einbauten_bewerten(dateien, assetpack_datei=ASSET)
        return erg

    def test_die_einbauten_sind_dieselben_wie_mit_allen_dateien(self) -> None:
        for name, zusatz in self.FAELLE.items():
            with self.subTest(fall=name):
                dateien = _spiel() | zusatz
                quelle = _quelle(self.basis, name, dateien)
                _abbild(quelle)
                voll = self._bewertung(self._dateien(quelle, False))
                gezielt = self._bewertung(self._dateien(quelle, True))
                self.assertEqual(voll, gezielt)

    def test_die_ergebnisse_sind_mehr_als_leere_antworten(self) -> None:
        """Gegenprobe zur Gegenprobe: Die Faelle unterscheiden sich wirklich."""
        erg = {}
        for name in ("ampr_playgo_backport", "fakelib2_gewinnt", "asset_pack", "huelle_app0"):
            quelle = _quelle(self.basis, name, _spiel() | self.FAELLE[name])
            _abbild(quelle)
            erg[name] = self._bewertung(self._dateien(quelle, True))
        self.assertTrue(erg["ampr_playgo_backport"]["ampr"] and erg["ampr_playgo_backport"]["playgo"])
        self.assertEqual(["fw10", "fw11"], erg["ampr_playgo_backport"]["backport"])
        self.assertEqual("fakelib2", erg["fakelib2_gewinnt"]["ordner"])
        self.assertTrue(erg["asset_pack"]["assetpack"])
        self.assertTrue(erg["huelle_app0"]["ampr"], "Die Huelle app0/ wird mitgelesen.")
        self.assertEqual(["fw12"], erg["huelle_app0"]["backport"])

    def test_ein_tiefer_baum_kostet_nicht_mehr_ordner(self) -> None:
        dateien = _spiel() | {"fakelib/libSceAmpr.sprx": b"a"}
        for n in range(60):
            dateien["daten/ebene%02d/unter/datei%02d.bin" % (n, n)] = b"d"
        quelle = _quelle(self.basis, "tief", dateien)
        abbild = _abbild(quelle)
        zaehler = {"n": 0}
        echt = ExfatReader._read_directory_entries

        def _zaehlen(selbst, *a, **k):
            zaehler["n"] += 1
            return echt(selbst, *a, **k)

        with mock.patch.object(ExfatReader, "_read_directory_entries", _zaehlen):
            self.gui._container_dateien(str(abbild), roh_exfat=True, gezielt=True)
            gezielt = zaehler["n"]
            zaehler["n"] = 0
            self.gui._container_dateien(str(abbild), roh_exfat=True, gezielt=False)
            voll = zaehler["n"]
        self.assertLessEqual(gezielt, 4, "Wurzel, sce_sys, fakelib - mehr nicht (gelesen: %d)." % gezielt)
        self.assertGreater(voll, 100)

    def test_eine_ffpfsc_mit_exfat_darin_liefert_dieselben_einbauten(self) -> None:
        quelle = _quelle(self.basis, "innen", _spiel() | self.FAELLE["ampr_playgo_backport"])
        exfat = _abbild(quelle)
        ausgabe = self.basis / "huelle.ffpfsc"
        build_pfs_stream_single_file(
            source_file=exfat, output_path=ausgabe, block_size=65536, pfs_version=consts.PFS_VERSION_PS5,
            case_insensitive=True, zlib_level=7, threshold_gain=0, min_file_gain=0, min_compress_size=0,
            cpu_count=1, compress=True)
        voll = self._bewertung(self.gui._container_dateien(str(ausgabe), gezielt=False))
        gezielt = self._bewertung(self.gui._container_dateien(str(ausgabe), gezielt=True))
        self.assertEqual(voll, gezielt)
        self.assertTrue(gezielt["ampr"])

    def test_ein_nicht_exfat_wird_weiter_ueber_den_pfs_weg_gelesen(self) -> None:
        """Die zweite Stufe (PFS-in-PFS) bleibt: ``gezielt`` betrifft nur exFAT."""
        kaputt = self.basis / "kein_exfat.exfat"
        kaputt.write_bytes(b"\0" * 4096)
        self.assertIsNone(self.gui._container_dateien(str(kaputt), roh_exfat=True, gezielt=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
