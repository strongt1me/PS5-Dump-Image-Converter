# -*- coding: utf-8 -*-
"""Die Abschlusspruefung eines .ffpfs/.ffpfsc richtet sich nach der Pruefstufe (10.11.2026).

Bis v1.9.95 dekodierte sie **immer** jeden Block - unabhaengig von der Stufe und zusaetzlich zu MkPFS, das in der
exFAT-Bauform dieselbe Datei nach dem Bauen schon vollstaendig dekodiert hatte. Gemessen an einem echten Dump
(12,4 GB, 20 Kerne, NVMe): Bau 63 s, MkPFS-Pruefung +15 s, Abschlusspruefung +22 s einfaedig.

Jetzt (``Pruefstand._abschluss_nur_aufbau``):

* ``aus``: nur der Aufbau;
* ``schnell``: nur der Aufbau, **wenn** MkPFS die Nutzdaten dieser Datei gerade geprueft hat und sie seitdem unveraendert
  ist - sonst jeder Block wie bisher;
* ``voll`` und ohne Angabe: jeder Block wie bisher.

Die Pruefungen laufen in eigenen Prozessen: Hier kann laengst ein anderes ``mkpfs`` geladen sein.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
MKPFS_ORDNER = PROJEKT / "MkPFS-1.1.0"
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("abschluss_stufe")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402

SKRIPT = r'''
import json, os, random, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])          # MkPFS-1.1.0
sys.path.insert(0, sys.argv[2])          # Projekt
basis = Path(sys.argv[3])
stufe = sys.argv[4]                      # aus | schnell | voll | keine
gemerkt = sys.argv[5] == "ja"
beschaedigen = sys.argv[6] == "ja"

from mkpfs import cli, pfs
from ps5_validator.utils import abbild_pruefen

quelle = basis / "quelle"
(quelle / "data").mkdir(parents=True)
zufall = random.Random(7)
for nr in range(6):
    # Verdichtbar (16 Zeichen = 4 Bit je Byte), damit Bloecke wirklich als zlib gespeichert werden und eine
    # Beschaedigung beim Dekodieren auffaellt.
    inhalt = bytes(zufall.choice(b"0123456789abcdef") for _ in range(512 * 1024))
    (quelle / "data" / ("datei%d.bin" % nr)).write_bytes(inhalt)
ziel = basis / "abbild.ffpfsc"
rc = cli.main(["pack", "folder", "--compress", "--no-adjust-output-file-extension", "--version", "PS5",
               "--inode-bits", "32", "--cpu-count", "2", "--compression-level", "6", "--block-size", "65536",
               "--no-verify-structure", str(quelle), str(ziel)])
if beschaedigen:
    groesse = ziel.stat().st_size
    with open(ziel, "r+b") as f:
        for anteil in range(25, 90, 3):
            f.seek(groesse * anteil // 100)
            f.write(b"\xff" * 64)

aufrufe = {"verify": 0, "inspect": []}
_verify, _inspect = pfs.verify_pfs_image, pfs.inspect_pfs_image


def verify_gezaehlt(*a, **k):
    aufrufe["verify"] += 1
    return _verify(*a, **k)


def inspect_gezaehlt(*a, **k):
    aufrufe["inspect"].append(bool(k.get("verify_payloads", True)))
    return _inspect(*a, **k)


pfs.verify_pfs_image = verify_gezaehlt
pfs.inspect_pfs_image = inspect_gezaehlt

angaben = {"text": lambda s, **w: s, "mkpfs_ordner_holen": lambda: sys.argv[1],
           "nutzdaten_geprueft": lambda _p: gemerkt}
if stufe != "keine":
    angaben["pruefstufe"] = lambda: stufe
stand = abbild_pruefen.Pruefstand(**angaben)
r = stand._verify_output_artifact("pack_folder", str(ziel))
print("ERGEBNIS:" + json.dumps({"rc": rc, "ok": r["ok"], "method": r["method"], "detail": r["detail"],
                                "verify_aufrufe": aufrufe["verify"], "inspect_payloads": aufrufe["inspect"]}))
'''


def _lauf(stufe: str, gemerkt: bool, beschaedigen: bool = False) -> dict:
    with tempfile.TemporaryDirectory(prefix="ps5conv_stufe_") as tmp:
        fertig = subprocess.run(
            [sys.executable, "-c", SKRIPT, str(MKPFS_ORDNER), str(PROJEKT), tmp, stufe,
             "ja" if gemerkt else "nein", "ja" if beschaedigen else "nein"],
            capture_output=True, text=True, timeout=300, cwd=tmp)
    zeilen = [z for z in fertig.stdout.splitlines() if z.startswith("ERGEBNIS:")]
    if not zeilen:
        raise AssertionError("keine Ausgabe:\n%s\n%s" % (fertig.stdout[-800:], fertig.stderr[-800:]))
    return json.loads(zeilen[-1][len("ERGEBNIS:"):])


class AbschlusspruefungNachStufe(unittest.TestCase):
    def test_voll_ohne_merker_dekodiert_jeden_block(self) -> None:
        e = _lauf("voll", gemerkt=False)
        self.assertTrue(e["ok"], e)
        self.assertEqual("mkpfs-verify", e["method"])
        self.assertEqual(1, e["verify_aufrufe"])

    def test_voll_mit_merker_liest_nur_den_aufbau(self) -> None:
        """MkPFS hat diese Datei gerade selbst vollstaendig dekodiert (exFAT-Bauform mit ``--verify``): nicht zweimal."""
        e = _lauf("voll", gemerkt=True)
        self.assertTrue(e["ok"], e)
        self.assertEqual("mkpfs-struktur", e["method"])
        self.assertEqual(0, e["verify_aufrufe"])
        self.assertEqual([False], e["inspect_payloads"])

    def test_ohne_angabe_gilt_voll(self) -> None:
        """Alle, die den Pruefstand ohne die neuen Rueckrufe bauen, verhalten sich wie bisher."""
        e = _lauf("keine", gemerkt=False)
        self.assertEqual("mkpfs-verify", e["method"])
        self.assertEqual(1, e["verify_aufrufe"])

    def test_schnell_nimmt_aufbau_und_stichprobe(self) -> None:
        for gemerkt in (False, True):
            with self.subTest(gemerkt=gemerkt):
                e = _lauf("schnell", gemerkt=gemerkt)
                self.assertTrue(e["ok"], e)
                self.assertEqual("mkpfs-stichprobe", e["method"])
                self.assertEqual(0, e["verify_aufrufe"], "nicht jeder Block darf dekodiert werden")
                # inspect_pfs_image laeuft zweimal (Aufbau, dann ``open_inner_file_view``) - nie mit Nutzdaten
                self.assertTrue(e["inspect_payloads"] and not any(e["inspect_payloads"]),
                                "inspect_pfs_image ohne Nutzdaten: %s" % e["inspect_payloads"])
                self.assertIn("mkpfs_stichprobe", e["detail"])

    def test_aus_liest_nur_den_aufbau(self) -> None:
        e = _lauf("aus", gemerkt=False)
        self.assertTrue(e["ok"], e)
        self.assertEqual("mkpfs-struktur", e["method"])
        self.assertEqual(0, e["verify_aufrufe"])
        self.assertEqual([False], e["inspect_payloads"])


class BeschaedigungWirdGefunden(unittest.TestCase):
    """Das Testabbild ist klein (ein Stueck zu 128 Bloecken): die Stichprobe deckt es ganz ab."""

    def test_voll_findet_eine_beschaedigte_nutzlast(self) -> None:
        e = _lauf("voll", gemerkt=False, beschaedigen=True)
        self.assertFalse(e["ok"], "die Beschaedigung muss auffallen: %s" % e)
        self.assertEqual("mkpfs-verify", e["method"])

    def test_schnell_findet_sie_in_einem_kleinen_abbild(self) -> None:
        e = _lauf("schnell", gemerkt=False, beschaedigen=True)
        self.assertFalse(e["ok"], e)
        self.assertEqual("mkpfs-stichprobe", e["method"])

    def test_nur_aufbau_findet_sie_bewusst_nicht(self) -> None:
        """Der Preis der Stufe "aus": Der Aufbau ist heil, die Nutzdaten waeren es nicht."""
        e = _lauf("aus", gemerkt=False, beschaedigen=True)
        self.assertEqual("mkpfs-struktur", e["method"])
        self.assertEqual(0, e["verify_aufrufe"])


class MerkerTests(unittest.TestCase):
    """``_mkpfs_pruefung_merken`` und ``_nutzdaten_vom_bau_geprueft`` am Hauptfenster (ohne Tk)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="ps5conv_merker_")
        self.addCleanup(self.tmp.cleanup)
        self.pfad = os.path.join(self.tmp.name, "spiel.ffpfsc")
        Path(self.pfad).write_bytes(b"x" * 4096)
        self.gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)

    def _aufruf(self, *zusatz: str) -> list[str]:
        return ["pack", "folder", "--compress", *zusatz, "--no-adjust-output-file-extension", "--version", "PS5",
                "--cpu-count", "8", "--compression-level", "9", "--block-size", "65536", "C:/quelle", self.pfad]

    def _merken(self, aufruf: list[str]) -> None:
        APP.PS5ConverterGUI._mkpfs_pruefung_merken(self.gui, aufruf)

    def _gilt(self) -> bool:
        return APP.PS5ConverterGUI._nutzdaten_vom_bau_geprueft(self.gui, self.pfad)

    def test_exfat_bauform_mit_pruefung_wird_gemerkt(self) -> None:
        self._merken(self._aufruf())                       # "schnell": keine Pruefschalter
        self.assertTrue(self._gilt())

    def test_voll_wird_gemerkt(self) -> None:
        self._merken(self._aufruf("--verify"))
        self.assertTrue(self._gilt())

    def test_abgeschaltete_pruefung_wird_nicht_gemerkt(self) -> None:
        for schalter in ("--no-verify-structure", "--skip-verification"):
            with self.subTest(schalter=schalter):
                self.gui.__dict__.pop("_mkpfs_nutzdaten_geprueft", None)
                self._merken(self._aufruf(schalter))
                self.assertFalse(self._gilt())

    def test_pfs_bauform_wird_nicht_gemerkt(self) -> None:
        """``--raw``: MkPFS prueft dort bei "schnell" nur die Struktur - die Nutzdaten blieben ungeprueft."""
        self._merken(self._aufruf("--raw"))
        self.assertFalse(self._gilt())

    def test_pack_file_wird_nicht_gemerkt(self) -> None:
        aufruf = self._aufruf()
        aufruf[1] = "file"
        self._merken(aufruf)
        self.assertFalse(self._gilt())

    def test_geaenderte_datei_gilt_nicht_mehr(self) -> None:
        self._merken(self._aufruf())
        self.assertTrue(self._gilt())
        with open(self.pfad, "ab") as f:                   # wie eine Kopie/ein Ersetzen: andere Groesse
            f.write(b"y")
        self.assertFalse(self._gilt())

    def test_gleiche_groesse_aber_neue_zeit_gilt_nicht_mehr(self) -> None:
        self._merken(self._aufruf())
        st = os.stat(self.pfad)
        os.utime(self.pfad, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
        self.assertFalse(self._gilt())

    def test_anderer_pfad_gilt_nicht(self) -> None:
        self._merken(self._aufruf())
        anderer = os.path.join(self.tmp.name, "kopie.ffpfsc")
        Path(anderer).write_bytes(b"x" * 4096)
        self.assertFalse(APP.PS5ConverterGUI._nutzdaten_vom_bau_geprueft(self.gui, anderer))

    def test_fehlende_datei_und_leerer_merker(self) -> None:
        self.assertFalse(self._gilt())
        self._merken(self._aufruf())
        os.remove(self.pfad)
        self.assertFalse(self._gilt())

    def test_kurzer_oder_kaputter_aufruf_wirft_nicht(self) -> None:
        for aufruf in ([], ["pack"], ["pack", "folder"], ["pack", "folder", "a", "b"]):
            with self.subTest(aufruf=aufruf):
                self._merken(list(aufruf))


class AufrufErkennungTests(unittest.TestCase):
    """``pfad_mit_geprueften_nutzdaten``: welche MkPFS-Aufrufe die Nutzdaten ihrer Ausgabe selbst geprueft haben."""

    @staticmethod
    def _f(aufruf):
        from ps5_validator.utils.abbild_pruefen import pfad_mit_geprueften_nutzdaten
        return pfad_mit_geprueften_nutzdaten(aufruf)

    BASIS = ["pack", "folder", "--compress", "--version", "PS5", "C:/quelle", "D:/ziel.ffpfsc"]

    def test_exfat_bauform_ohne_weitere_schalter(self) -> None:
        self.assertEqual("D:/ziel.ffpfsc", self._f(list(self.BASIS)))

    def test_voll(self) -> None:
        self.assertEqual("D:/ziel.ffpfsc", self._f(self.BASIS[:3] + ["--verify"] + self.BASIS[3:]))

    def test_keine_nutzdatenpruefung_bei_diesen_schaltern(self) -> None:
        for schalter in ("--raw", "--no-verify-structure", "--skip-verification"):
            with self.subTest(schalter=schalter):
                self.assertIsNone(self._f(self.BASIS[:3] + [schalter] + self.BASIS[3:]))

    def test_andere_befehle_und_kaputte_listen(self) -> None:
        self.assertIsNone(self._f(["pack", "file"] + self.BASIS[2:]))
        self.assertIsNone(self._f(["verify", "folder", "a", "b"]))
        for kaputt in ([], ["pack"], ["pack", "folder"], ["pack", "folder", "a"], None):
            with self.subTest(kaputt=kaputt):
                self.assertIsNone(self._f(kaputt))   # type: ignore[arg-type]


class AufrufFuerStufeTests(unittest.TestCase):
    """``mkpfs_aufruf_fuer_stufe``: Bei "schnell" entfaellt MkPFS' eigene Dekodierung, weil eine Stichprobe folgt."""

    BASIS = AufrufErkennungTests.BASIS

    @staticmethod
    def _f(aufruf, stufe):
        from ps5_validator.utils.abbild_pruefen import mkpfs_aufruf_fuer_stufe
        return mkpfs_aufruf_fuer_stufe(aufruf, stufe)

    def test_schnell_in_der_exfat_bauform_schaltet_mkpfs_pruefung_ab(self) -> None:
        neu = self._f(list(self.BASIS), "schnell")
        self.assertEqual(["pack", "folder", "--no-verify-structure"] + self.BASIS[2:], neu)
        self.assertEqual(self.BASIS[-2:], neu[-2:], "Quelle und Ziel bleiben die letzten beiden")

    def test_alles_andere_bleibt_unveraendert(self) -> None:
        for name, aufruf, stufe in (
                ("voll", list(self.BASIS), "voll"),
                ("aus", list(self.BASIS), "aus"),
                ("unbekannt", list(self.BASIS), "irgendwas"),
                ("raw", self.BASIS[:3] + ["--raw"] + self.BASIS[3:], "schnell"),
                ("schon_aus", self.BASIS[:3] + ["--no-verify-structure"] + self.BASIS[3:], "schnell"),
                ("verify", self.BASIS[:3] + ["--verify"] + self.BASIS[3:], "schnell"),
                ("pack_file", ["pack", "file"] + self.BASIS[2:], "schnell"),
                ("tree", ["tree", "C:/quelle"], "schnell")):
            with self.subTest(fall=name):
                self.assertEqual(aufruf, self._f(list(aufruf), stufe))

    def test_die_eingabeliste_wird_nicht_veraendert(self) -> None:
        eingabe = list(self.BASIS)
        self._f(eingabe, "schnell")
        self.assertEqual(self.BASIS, eingabe)


class _Ansicht:
    """Ersatz fuer ``_LogicalFileView`` des eingebetteten MkPFS."""

    def __init__(self, bloecke: int, komprimiert: bool = True, fehler_bei=(), laengen=None) -> None:
        self._compressed = komprimiert
        self._lbs = 65536
        self._base = 4096
        schritt = 100
        self._offsets = laengen or [i * schritt for i in range(bloecke + 1)]
        self.dekodiert: list[int] = []
        self._fehler_bei = set(fehler_bei)

    def _decode_block(self, index: int) -> bytes:
        self.dekodiert.append(index)
        if index in self._fehler_bei:
            raise ValueError("zlib kaputt")
        return b"x" * self._lbs


class _Griff:
    def __init__(self) -> None:
        self.zu = False

    def close(self) -> None:
        self.zu = True


class StichprobeTests(unittest.TestCase):
    """``stichprobe_dekodieren`` mit einer Nachbildung der Ansicht: Auswahl, Tabellenpruefung, Fehler, Abbruch."""

    def _lauf(self, ansicht, *, abbruch=None, getsize=10 ** 12, zufall=None):
        import types
        from unittest import mock

        from ps5_validator.utils import abbild_pruefen
        import random

        griff = _Griff()
        pfs = types.ModuleType("mkpfs.pfs")
        pfs.open_inner_file_view = lambda _bild: None if ansicht is None else (ansicht, griff, "inner.exfat")  # type: ignore[attr-defined]
        paket = types.ModuleType("mkpfs")
        with mock.patch.dict(sys.modules, {"mkpfs": paket, "mkpfs.pfs": pfs}), \
                mock.patch.object(abbild_pruefen.os.path, "getsize", return_value=getsize):
            try:
                ergebnis = abbild_pruefen.stichprobe_dekodieren(
                    Path("abbild.ffpfsc"), abbruch=abbruch, zufall=zufall or random.Random(3))
            finally:
                self.griff = griff
        return ergebnis

    def test_etwa_ein_prozent_in_stuecken_zu_128_bloecken_erstes_und_letztes_immer(self) -> None:
        a = _Ansicht(100_000)
        e = self._lauf(a)
        stuecke = {i // 128 for i in a.dekodiert}
        self.assertEqual(8, len(stuecke))                       # 1 % = 1000 Bloecke = 8 Stuecke
        self.assertIn(0, stuecke)
        self.assertIn(781, stuecke)                             # letztes Stueck (32 Bloecke)
        self.assertEqual(len(a.dekodiert), e["geprueft"])
        self.assertEqual(100_000, e["bloecke"])
        self.assertEqual([], e["fehler"])
        self.assertEqual(len(set(a.dekodiert)), len(a.dekodiert), "kein Block doppelt")

    def test_hoechstens_128_stuecke(self) -> None:
        a = _Ansicht(5_000_000)
        self._lauf(a)
        self.assertEqual(128, len({i // 128 for i in a.dekodiert}))

    def test_mindestens_vier_stuecke(self) -> None:
        a = _Ansicht(3_000)                                      # 24 Stuecke, 1 % waere 1
        self._lauf(a)
        self.assertEqual(4, len({i // 128 for i in a.dekodiert}))

    def test_kleines_abbild_wird_ganz_dekodiert(self) -> None:
        a = _Ansicht(100)
        e = self._lauf(a)
        self.assertEqual(list(range(100)), sorted(a.dekodiert))
        self.assertEqual(100, e["geprueft"])

    def test_zufall_wechselt_zwischen_den_laeufen(self) -> None:
        import random
        a1, a2 = _Ansicht(100_000), _Ansicht(100_000)
        self._lauf(a1, zufall=random.Random(1))
        self._lauf(a2, zufall=random.Random(2))
        self.assertNotEqual(sorted(a1.dekodiert), sorted(a2.dekodiert))

    def test_unmoegliche_blocklaenge_faellt_in_der_tabelle_auf(self) -> None:
        a = _Ansicht(0, laengen=[0, 100, 100, 250, 300, 70000])   # Block 1 hat Laenge 0, Block 4 ist laenger als 64 KiB
        e = self._lauf(a)
        self.assertEqual(0, e["geprueft"])
        self.assertEqual([], a.dekodiert, "bei kaputter Tabelle wird nichts dekodiert")
        self.assertTrue(any(f.startswith("Block 1:") for f in e["fehler"]), e)

    def test_abgeschnittene_datei_faellt_auf(self) -> None:
        e = self._lauf(_Ansicht(100), getsize=500)                # Tabelle reicht bis 4096 + 10000
        self.assertEqual(0, e["geprueft"])
        self.assertTrue(e["fehler"] and "Tabelle" in e["fehler"][0], e)

    def test_dekodierfehler_wird_gemeldet(self) -> None:
        a = _Ansicht(100, fehler_bei=(5,))
        e = self._lauf(a)
        self.assertTrue(any(f.startswith("Block 5:") for f in e["fehler"]), e)
        self.assertEqual(5, e["geprueft"], "Bloecke 0..4 waren gut, danach bricht das Stueck ab")

    def test_nicht_anwendbar_gibt_none(self) -> None:
        self.assertIsNone(self._lauf(None))                       # mehrere Dateien, signiert, leer ...
        self.assertTrue(self.griff is not None)
        self.assertIsNone(self._lauf(_Ansicht(100, komprimiert=False)))
        self.assertTrue(self.griff.zu)
        self.assertIsNone(self._lauf(_Ansicht(0)))

    def test_abbruch_wirft_und_der_griff_wird_geschlossen(self) -> None:
        from ps5_validator.utils import abbild_pruefen
        with self.assertRaises(abbild_pruefen._PruefungAbgebrochen):
            self._lauf(_Ansicht(100_000), abbruch=lambda: True)
        self.assertTrue(self.griff.zu)

    def test_griff_wird_immer_geschlossen(self) -> None:
        self._lauf(_Ansicht(100))
        self.assertTrue(self.griff.zu)

    def test_ohne_vorgegebenen_zufall_laeuft_es(self) -> None:
        import types
        from unittest import mock

        from ps5_validator.utils import abbild_pruefen
        a, griff = _Ansicht(50_000), _Griff()
        pfs = types.ModuleType("mkpfs.pfs")
        pfs.open_inner_file_view = lambda _b: (a, griff, "x")  # type: ignore[attr-defined]
        with mock.patch.dict(sys.modules, {"mkpfs": types.ModuleType("mkpfs"), "mkpfs.pfs": pfs}), \
                mock.patch.object(abbild_pruefen.os.path, "getsize", return_value=10 ** 12):
            e = abbild_pruefen.stichprobe_dekodieren(Path("x"))
        self.assertEqual([], e["fehler"])
        self.assertGreater(e["geprueft"], 0)


class VerdrahtungTests(unittest.TestCase):
    """Die Nahtstellen und der Aufruf stehen im Hauptmodul (Quelltextsuche, wie bei den anderen Verdrahtungstests)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")

    def test_pruefstand_bekommt_stufe_und_merker(self) -> None:
        self.assertIn('pruefstufe=lambda: getattr(self, "mkpfs_verify", "schnell")', self.text)
        self.assertIn("nutzdaten_geprueft=self._nutzdaten_vom_bau_geprueft", self.text)

    def test_aufruf_wird_je_stufe_angepasst_bevor_mkpfs_laeuft(self) -> None:
        i = self.text.index("def _execute_mkpfs(")
        j = self.text.index("def _execute_mkpfs_einmal(", i)
        rumpf = self.text[i:j]
        self.assertIn("abbild_pruefen.mkpfs_aufruf_fuer_stufe(", rumpf)
        self.assertLess(rumpf.index("mkpfs_aufruf_fuer_stufe("), rumpf.index("_execute_mkpfs_einmal("))

    def test_merker_wird_nach_erfolgreichem_mkpfs_lauf_gesetzt(self) -> None:
        i = self.text.index("def _execute_mkpfs(")
        j = self.text.index("def _execute_mkpfs_einmal(", i)
        rumpf = self.text[i:j]
        self.assertIn("self._mkpfs_pruefung_merken(aufruf)", rumpf)
        self.assertLess(rumpf.index("if ok:"), rumpf.index("self._mkpfs_pruefung_merken(aufruf)"))


if __name__ == "__main__":
    unittest.main()
