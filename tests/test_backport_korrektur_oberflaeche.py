# -*- coding: utf-8 -*-
"""BACKPORT-Zusaetze im Programm: Einhaengung in beide Ablaeufe, Meldungen, Haken.

Die Zusaetze selbst (``backport_korrektur``) prueft ``test_backport_korrektur``. Hier geht es darum, dass das Programm
sie zur richtigen Zeit ruft: das Profil VOR dem Herabsetzen (die SHA-256 des Originals ist danach nicht mehr zu bilden),
Profil und Stubs NACH dem Einbau der Ersatzbibliotheken (erst dann steht fest, was wirklich fehlt).
"""
from __future__ import annotations

import ast
import gzip
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("backport_korrektur_oberflaeche")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import backport_korrektur as bk    # noqa: E402
from ps5_validator.utils import ps5_backport as bp          # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

from test_backport_korrektur import baue_elf, IMPORTE, CODE  # noqa: E402

GUI = APP.PS5ConverterGUI
HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"


def _gui(einstellungen: dict | None = None):
    gui = GUI.__new__(GUI)
    gui.protokoll = []
    gui._append_to_log = gui.protokoll.append
    gui._t = lambda schluessel, **w: schluessel + str(sorted(w.items()))
    einstellungen = einstellungen or {}
    gui._load_setting = lambda schluessel, vorgabe=None: einstellungen.get(schluessel, vorgabe)
    return gui


def _methode(name: str) -> str:
    with io.open(HAUPTDATEI, encoding="utf-8") as fh:
        baum = ast.parse(fh.read())
    klasse = next(k for k in ast.walk(baum) if isinstance(k, ast.ClassDef) and k.name == "PS5ConverterGUI")
    return ast.unparse(next(m for m in klasse.body if isinstance(m, ast.FunctionDef) and m.name == name))


def _tabelle(basis: Path, firmware: int, exporte: dict) -> None:
    ordner = basis / str(firmware)
    ordner.mkdir(parents=True, exist_ok=True)
    with gzip.open(ordner / bp.FIRMWARE_EXPORTE_DATEI, "wb") as datei:
        datei.write(json.dumps({"firmware": firmware, "staende": ["x"], "exporte": exporte}).encode("utf-8"))


class VerdrahtungTests(unittest.TestCase):
    """Die Reihenfolge entscheidet - sie steht im Quelltext beider Ablaeufe."""

    def _pruefe(self, name: str, schleife: str):
        text = _methode(name)
        i_vorbereiten = text.find("self._backport_korrekturen_vorbereiten(ordner, firmware)")
        i_schleife = text.find(schleife)
        i_anwenden = text.find("self._backport_korrekturen_anwenden(")
        i_melden = text.find("self._backport_luecken_melden(")
        self.assertGreater(i_vorbereiten, 0, "%s: Profil wird nicht vorbereitet" % name)
        self.assertGreater(i_schleife, 0, "%s: Schleife nicht gefunden (Test anpassen)" % name)
        self.assertLess(i_vorbereiten, i_schleife, "%s: Das Original muss gemessen werden, bevor herabgesetzt wird" % name)
        self.assertGreater(i_anwenden, i_schleife)
        self.assertLess(i_anwenden, i_melden, "%s: Die Restmeldung muss die Stubs kennen" % name)
        self.assertIn("neutralisiert", text[i_melden:i_melden + 160])
        i_fakelibs = text.find("self._backport_fakelib_auswahl(")
        self.assertGreater(i_anwenden, i_fakelibs, "%s: Stubs erst NACH dem Einbau der Ersatzbibliotheken" % name)

    def test_einbau_beim_erstellen(self):
        self._pruefe("_integration_backport", "ps5_backport.kandidaten(ordner):")

    def test_backport_fenster(self):
        self._pruefe("_backport_worker", "enumerate(dateien, 1)")

    def test_backport_ordner_ablauf(self):
        """Der dritte Weg ("Nur Backport-Ordner erstellen"): Profil vorher messen, Zusaetze auf das Ergebnis."""
        text = _methode("_render_backport_window")
        i_vorbereiten = text.find("self._backport_korrekturen_vorbereiten(ordner, firmware)")
        i_bauen = text.find("ps5_backport.backport_ordner_bauen(")
        i_anwenden = text.find("self._backport_korrekturen_anwenden(", i_bauen)
        self.assertGreater(i_vorbereiten, 0)
        self.assertLess(i_vorbereiten, i_bauen, "Das Original muss gemessen werden, bevor gebaut wird")
        self.assertGreater(i_anwenden, i_bauen)
        self.assertIn("ergebnis['ziel']", text[i_anwenden:i_anwenden + 120], "die Zusaetze wirken auf den Ergebnisordner")
        self.assertIn("abgebrochen", text[i_bauen:i_anwenden], "nach einem Abbruch wird nichts mehr angewendet")

    def test_haken_stehen_im_backport_fenster_und_speichern_sich(self):
        with io.open(HAUPTDATEI, encoding="utf-8") as fh:
            quelle = fh.read()
        for schluessel in ("backport.option_stubs", "backport.option_profile", '"backport_stubs"', '"backport_profile"'):
            self.assertIn(schluessel, quelle, schluessel)
        # Beide Vorgaben sind Nein: Die Zusaetze aendern Spielcode.
        self.assertIn('self._load_setting("backport_stubs", False)', quelle)
        self.assertIn('self._load_setting("backport_profile", False)', quelle)

    def test_jeder_status_hat_eine_meldung(self):
        status = {getattr(bk, n) for n in dir(bk) if n.startswith("P_")}
        self.assertEqual(set(GUI._KORR_PROFIL_MELDUNG), status)
        for schluessel in GUI._KORR_PROFIL_MELDUNG.values():
            self.assertIn(schluessel, STRINGS)

    def test_alle_texte_in_allen_sprachen_mit_denselben_platzhaltern(self):
        import re
        schluessel = [k for k in STRINGS if k.startswith(("backport.korr_", "backport.option_stubs",
                                                          "backport.option_profile", "backport.option_korr",
                                                          "backport.state_korrekturen"))]
        self.assertGreaterEqual(len(schluessel), 20)
        for k in schluessel:
            platzhalter = {sprache: set(re.findall(r"\{(\w+)\}", text)) for sprache, text in STRINGS[k].items()}
            with self.subTest(schluessel=k):
                self.assertEqual(set(STRINGS[k]), {"de", "en", "es", "it", "fr"})
                self.assertEqual(len({frozenset(p) for p in platzhalter.values()}), 1, platzhalter)
                for text in STRINGS[k].values():
                    self.assertTrue(text.strip())


class VorbereitenTests(unittest.TestCase):

    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.dump = Path(self.t.name) / "dump"
        (self.dump / "sce_sys").mkdir(parents=True)
        (self.dump / "sce_sys" / "param.json").write_text(json.dumps({"titleId": "PPSA23559"}), encoding="utf-8")

    def test_haken_aus_tut_nichts(self):
        gui = _gui()
        self.assertIsNone(gui._backport_korrekturen_vorbereiten(str(self.dump), 4))
        self.assertEqual(gui.protokoll, [])

    def test_haken_an_aber_titel_ohne_profil(self):
        (self.dump / "sce_sys" / "param.json").write_text(json.dumps({"titleId": "PPSA00000"}), encoding="utf-8")
        gui = _gui({"backport_profile": True})
        vorb = gui._backport_korrekturen_vorbereiten(str(self.dump), 4)
        self.assertEqual(vorb.aktiv, ())
        self.assertEqual(len(gui.protokoll), 1)
        self.assertIn("backport.korr_profil_kein", gui.protokoll[0])
        self.assertIn("PPSA00000", gui.protokoll[0])

    def test_profil_gefunden_aber_andere_zielfirmware(self):
        gui = _gui({"backport_profile": True})
        vorb = gui._backport_korrekturen_vorbereiten(str(self.dump), 6)
        self.assertEqual((vorb.aktiv, len(vorb.uebergangen)), ((), 1))
        self.assertIn("backport.korr_profil_firmware", gui.protokoll[0])

    def test_profil_gefunden_und_passend(self):
        gui = _gui({"backport_profile": True})
        vorb = gui._backport_korrekturen_vorbereiten(str(self.dump), 4)
        self.assertEqual(len(vorb.aktiv), 1)
        self.assertIn("backport.korr_profil_gefunden", gui.protokoll[0])
        self.assertIn("Anno 117", gui.protokoll[0])

    def test_eigener_profilordner_kommt_vor_dem_mitgelieferten(self):
        with tempfile.TemporaryDirectory() as t:
            gui = _gui({"backport_fakelib_ordner": t})
            ordner = gui._backport_profil_ordner()
            self.assertEqual(ordner[0], os.path.join(t, bk.PROFIL_ORDNER))
            self.assertTrue(ordner[-1].endswith(bk.PROFIL_ORDNER))
            self.assertEqual(len(ordner), 2)


class AnwendenTests(unittest.TestCase):
    """``_backport_korrekturen_anwenden`` an einem kleinen Dump mit kuenstlichem eboot."""

    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        wurzel = Path(self.t.name)
        self.dump = wurzel / "dump"
        self.dump.mkdir()
        self.elf, self.info = baue_elf(IMPORTE, CODE)
        (self.dump / "eboot.bin").write_bytes(self.elf)
        self.basis = wurzel / "basis"
        _tabelle(self.basis, 4, {"libkernel": ["KKKKKKKKKKK"]})
        # Gemeldet werden: AAAA, NH6x (libkernel), BBBB (libSceAcm), CCCC (schwach), DDDD (libSceFoo)

    def _anwenden(self, gui, vorb=None, **kw):
        return gui._backport_korrekturen_anwenden(str(self.dump), 4, str(self.basis), [], vorb, **kw)

    def test_beides_aus_tut_nichts_und_liest_nichts(self):
        gui = _gui()
        self.assertEqual(self._anwenden(gui), set())
        self.assertEqual(gui.protokoll, [])
        self.assertEqual((self.dump / "eboot.bin").read_bytes(), self.elf)

    def test_stubs_neutralisieren_die_luecken_und_melden_es(self):
        gui = _gui({"backport_stubs": True})
        status = []
        neutral = self._anwenden(gui, status=status.append)
        self.assertEqual(neutral, {("libkernel", "AAAAAAAAAAA"), ("libkernel", "NH6xARDOVv8"),
                                   ("libSceAcm", "BBBBBBBBBBB"), ("libSceFoo", "DDDDDDDDDDD")},
                         "der schwache Import CCCC bleibt aussen vor")
        elf = bk.elf_aus_bytes((self.dump / "eboot.bin").read_bytes())
        self.assertEqual(bp.dateityp((self.dump / "eboot.bin").read_bytes()), bp.TYP_SELF)
        self.assertEqual(len([z for z in gui.protokoll if z.startswith("backport.korr_stub[")]), 4)
        summe = [z for z in gui.protokoll if z.startswith("backport.korr_stub_summe")]
        self.assertEqual(len(summe), 1)
        self.assertIn("('anzahl', 4)", summe[0])
        self.assertIn("('dateien', 1)", summe[0])
        self.assertEqual(status, ["backport.state_korrekturen[]"])
        va_nh6 = self.info["plt"][1]
        self.assertEqual(elf[va_nh6:va_nh6 + 15], bk.STUB_AUSGABEN_MINUS1.bytes_)

    def test_ohne_luecken_wird_nichts_geaendert(self):
        _tabelle(self.basis, 4, {"libkernel": ["AAAAAAAAAAA", "NH6xARDOVv8"], "libSceAcm": ["BBBBBBBBBBB"],
                                 "libSceFoo": ["CCCCCCCCCCC", "DDDDDDDDDDD"]})
        gui = _gui({"backport_stubs": True})
        self.assertEqual(self._anwenden(gui), set())
        self.assertEqual([z.split("[")[0] for z in gui.protokoll], ["backport.korr_stub_keine"])
        self.assertEqual((self.dump / "eboot.bin").read_bytes(), self.elf)

    def test_ohne_exporttabelle_meldet_es_und_aendert_nichts(self):
        gui = _gui({"backport_stubs": True})
        neutral = gui._backport_korrekturen_anwenden(str(self.dump), 9, str(self.basis), [], None)
        self.assertEqual(neutral, set())
        self.assertIn("backport.korr_stub_ohne_tabelle", gui.protokoll[0])
        self.assertEqual((self.dump / "eboot.bin").read_bytes(), self.elf)

    def test_schreibfehler_bricht_den_backport_nicht(self):
        """Ein unerwarteter Fehler in den Zusaetzen wird gemeldet; der fertige Backport bleibt, wie er ist."""
        gui = _gui({"backport_stubs": True})
        alt = bk.korrekturen_anwenden

        def kaputt(*_a, **_k):
            raise RuntimeError("unerwartet")

        bk.korrekturen_anwenden = kaputt
        try:
            neutral = self._anwenden(gui)
        finally:
            bk.korrekturen_anwenden = alt
        self.assertEqual(neutral, set())
        self.assertTrue(any(z.startswith("backport.korr_fehler") and "unerwartet" in z for z in gui.protokoll))

    def test_profil_wird_gemeldet(self):
        d = {"format": 1, "titel_id": "PPSA00001", "name": "Test", "fassung": "1", "firmware": [4], "dateien": [{
            "pfad": "eboot.bin", "sha256_elf": __import__("hashlib").sha256(self.elf).hexdigest(),
            "patches": [{"zweck": "x", "va": hex(self.info["code"] + 2 - 0x4000), "alt": "7526", "neu": "eb26"}]}]}
        profil = bk.profil_aus_dict(d)
        vorb = bk.profile_vorbereiten(str(self.dump), [profil], "PPSA00001", 4)
        gui = _gui({"backport_profile": True})
        self._anwenden(gui, vorb)
        meldung = [z for z in gui.protokoll if z.startswith("backport.korr_profil_angewendet")]
        self.assertEqual(len(meldung), 1)
        self.assertIn("('datei', 'eboot.bin')", meldung[0])
        self.assertIn("('patches', 1)", meldung[0])
        elf = bk.elf_aus_bytes((self.dump / "eboot.bin").read_bytes())
        self.assertEqual(elf[self.info["code"] + 2:self.info["code"] + 4], b"\xeb\x26")


class LueckenmeldungTests(unittest.TestCase):
    """Was ein Stub erledigt hat, ist keine offene Luecke mehr."""

    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        wurzel = Path(self.t.name)
        self.dump = wurzel / "dump"
        self.dump.mkdir()
        elf, _info = baue_elf([("libkernel", "AAAAAAAAAAA", False), ("libkernel", "BBBBBBBBBBB", False)], CODE)
        (self.dump / "eboot.bin").write_bytes(elf)
        self.basis = wurzel / "basis"
        _tabelle(self.basis, 4, {"libkernel": ["KKKKKKKKKKK"]})

    def test_ohne_stubs_wird_gewarnt(self):
        gui = _gui()
        gui._backport_luecken_melden(str(self.basis), 4, str(self.dump), [])
        self.assertEqual(len(gui.protokoll), 1)
        self.assertIn("('total', 2)", gui.protokoll[0])

    def test_neutralisiertes_zaehlt_nicht_mehr(self):
        gui = _gui()
        gui._backport_luecken_melden(str(self.basis), 4, str(self.dump), [], {("libkernel", "AAAAAAAAAAA")})
        self.assertEqual(len(gui.protokoll), 1)
        self.assertIn("('total', 1)", gui.protokoll[0])

    def test_alles_neutralisiert_keine_warnung(self):
        gui = _gui()
        gui._backport_luecken_melden(str(self.basis), 4, str(self.dump), [],
                                     {("libkernel", "AAAAAAAAAAA"), ("libkernel", "BBBBBBBBBBB")})
        self.assertEqual(gui.protokoll, [])


if __name__ == "__main__":
    unittest.main()
