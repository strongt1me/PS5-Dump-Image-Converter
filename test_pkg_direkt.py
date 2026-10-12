# -*- coding: utf-8 -*-
"""PS5-Paket direkt auf die Konsole entpacken (``pkg_direkt``, seit v1.9.72; Auftrag des Nutzers vom 10.10.2026, "1 & 2").

Vorbild: fpkg2ftp (kvaps, GPL-3.0-or-later). Geprueft wird in drei Schichten:

* der Datenstrom des Werkzeugs (``stream-inner``): Rahmen lesen, kaputte und abgeschnittene Strome erkennen;
* der Ablauf gegen einen **echten** kleinen FTP-Server (``Attrappe`` aus ``test_ftp_fortsetzen``) und ein Fake-Werkzeug, das
  die Rahmen ausgibt und Fehler nachstellen kann (Absturz mitten in einer Datei, falsche Ausgabe, falscher Endrahmen);
* das **echte** Werkzeug: ein kleines PS5-Paket bauen, direkt auf die Attrappe entpacken, jede Datei per SHA-256 gegen
  ``extract-inner`` pruefen (nur wenn das gebaute Werkzeug ``stream-inner`` kennt und .NET da ist).
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402,F401
from ps5_validator.utils import konsole_ftp as kf            # noqa: E402
from ps5_validator.utils import pkg_direkt as pd             # noqa: E402
from ps5_validator.utils import ps5_pkg_werkzeug as wz       # noqa: E402
from test_ftp_fortsetzen import Attrappe                     # noqa: E402

#: Das Fake-Werkzeug. ``<Paket>`` ist eine JSON-Datei {"dateien": {pfad: groesse}, "modus": ...}; der Inhalt einer Datei
#: ergibt sich aus Pfad und Stelle (:func:`inhalt`). Modi: "" (richtig), "krumm" (keine Rahmen), "kein_start" (beginnt immer
#: bei 0), "stirb:<pfad>:<bytes>" (Absturz mitten in der Datei), "ende_falsch" (falsche Anzahl im Endrahmen),
#: "rueckgabe_3" (richtig, aber Rueckgabewert 3), "falscher_pfad" (liefert eine andere Datei).
FAKE = r'''
import json, struct, sys
args = sys.argv[1:]
assert args[0] == "stream-inner", args
paket = args[1]
plan = args[args.index("--plan") + 1]
cfg = json.load(open(paket, encoding="utf-8"))
dateien, modus = cfg["dateien"], cfg.get("modus", "")
aus = sys.stdout.buffer

def inhalt(pfad, ab, bis):
    rot = (len(pfad) + ab) % 256
    muster = bytes(range(256))
    muster = muster[rot:] + muster[:rot]
    return (muster * ((bis - ab) // 256 + 1))[:bis - ab]

def schreiben(b):
    aus.write(b)
    aus.flush()

if modus == "krumm":
    schreiben(b"Das ist kein Rahmen")
    sys.exit(0)
anzahl = 0
for zeile in open(plan, encoding="utf-8").read().splitlines():
    start, pfad = zeile.split("\t", 1)
    start = int(start)
    groesse = dateien[pfad]
    if modus == "kein_start" or start >= groesse:
        start = 0
    if modus == "falscher_pfad":
        pfad = pfad + ".x"
    name = pfad.encode("utf-8")
    schreiben(b"PKF1" + struct.pack("<I", len(name)) + name + struct.pack("<qq", groesse, start))
    rest = inhalt(pfad.removesuffix(".x"), start, groesse)
    if modus.startswith("stirb:") and pfad == modus.split(":")[1]:
        schreiben(rest[:int(modus.split(":")[2])])
        sys.stderr.write("[error] Absturz: kaputt\n")
        sys.stderr.flush()
        sys.exit(1)
    schreiben(rest)
    anzahl += 1
if modus == "ende_falsch":
    anzahl += 1
schreiben(b"PKE1" + struct.pack("<I", anzahl))
sys.stderr.write("[info] fertig\n")
sys.stderr.flush()
sys.exit(3 if modus == "rueckgabe_3" else 0)
'''


def inhalt(pfad: str, ab: int, bis: int) -> bytes:
    """Dieselbe Rechnung wie im Fake-Werkzeug."""
    rot = (len(pfad) + ab) % 256
    muster = bytes(range(256))
    muster = muster[rot:] + muster[:rot]
    return (muster * ((bis - ab) // 256 + 1))[:bis - ab]


def rahmen(pfad: str, groesse: int, start: int = 0, daten: "bytes | None" = None) -> bytes:
    name = pfad.encode("utf-8")
    kopf = b"PKF1" + struct.pack("<I", len(name)) + name + struct.pack("<qq", groesse, start)
    return kopf + (inhalt(pfad, start, groesse) if daten is None else daten)


def ende(anzahl: int) -> bytes:
    return b"PKE1" + struct.pack("<I", anzahl)


class _Haeppchen(io.RawIOBase):
    """Ein Rohr, das nie mehr als ein Byte auf einmal liefert - wie ein langsames Werkzeug."""

    def __init__(self, daten: bytes) -> None:
        self._d = io.BytesIO(daten)

    def readable(self) -> bool:
        return True

    def read(self, n: int = -1) -> bytes:
        return self._d.read(min(n, 1) if n and n > 0 else 1)


class RahmenTests(unittest.TestCase):
    def test_datei_und_ende(self) -> None:
        strom = io.BytesIO(rahmen("Media/a.dat", 700, 100, b"x" * 600) + ende(1))
        kopf = pd.rahmen_lesen(strom)
        self.assertEqual(pd.Rahmen("Media/a.dat", 700, 100), kopf)
        self.assertEqual(b"x" * 600, strom.read(600))
        self.assertEqual(1, pd.rahmen_lesen(strom))

    def test_ein_rohr_das_stueckweise_liefert(self) -> None:
        kopf = pd.rahmen_lesen(_Haeppchen(rahmen("a/b/c.bin", 5, 0, b"hallo")))
        self.assertEqual(pd.Rahmen("a/b/c.bin", 5, 0), kopf)

    def test_umlaute_im_pfad(self) -> None:
        self.assertEqual("Medien/Größe äöü.dat", pd.rahmen_lesen(io.BytesIO(rahmen("Medien/Größe äöü.dat", 1, 0, b"x"))).pfad)

    def test_nur_ein_endrahmen(self) -> None:
        self.assertEqual(0, pd.rahmen_lesen(io.BytesIO(ende(0))))

    def test_falsche_magie(self) -> None:
        with self.assertRaisesRegex(pd.StromFehler, "kein Rahmen"):
            pd.rahmen_lesen(io.BytesIO(b"Das ist keine Ausgabe des Werkzeugs"))

    def test_abgeschnitten_im_kopf_und_im_pfad(self) -> None:
        ganz = rahmen("Media/a.dat", 10, 0, b"x" * 10)
        for schnitt in (0, 2, 4, 6, 9, 12, 20, 30):
            with self.subTest(schnitt=schnitt), self.assertRaises(pd.StromFehler):
                pd.rahmen_lesen(io.BytesIO(ganz[:schnitt]))

    def test_unmoegliche_werte(self) -> None:
        for name, roh in (
                ("Pfadlaenge 0", b"PKF1" + struct.pack("<I", 0)),
                ("Pfadlaenge riesig", b"PKF1" + struct.pack("<I", 10 ** 6)),
                ("Groesse negativ", b"PKF1" + struct.pack("<I", 1) + b"a" + struct.pack("<qq", -1, 0)),
                ("Start hinter dem Ende", b"PKF1" + struct.pack("<I", 1) + b"a" + struct.pack("<qq", 5, 9)),
                ("Start negativ", b"PKF1" + struct.pack("<I", 1) + b"a" + struct.pack("<qq", 5, -1)),
                ("kein UTF-8", b"PKF1" + struct.pack("<I", 2) + b"\xff\xfe" + struct.pack("<qq", 5, 0))):
            with self.subTest(fall=name), self.assertRaises(pd.StromFehler):
                pd.rahmen_lesen(io.BytesIO(roh))


class BaumTests(unittest.TestCase):
    def test_dateien_und_ordner_sortiert(self) -> None:
        dateien, ordner = pd.dateien_und_ordner([
            {"path": "b", "type": "dir"}, {"path": "b/z.dat", "type": "file", "size": 5},
            {"path": "a", "type": "dir"}, {"path": "a/y.dat", "type": "file", "size": 0},
            {"path": "eboot.bin", "type": "file", "size": 9}, {"path": "leer", "type": "dir"}])
        self.assertEqual(["a/y.dat", "b/z.dat", "eboot.bin"], [d.pfad for d in dateien])
        self.assertEqual([0, 5, 9], [d.groesse for d in dateien])
        self.assertEqual(["a", "b", "leer"], ordner)

    def test_unsichere_pfade_werden_abgelehnt(self) -> None:
        for pfad in ("../aussen.dat", "a/../../b.dat", "/absolut.dat", "a//b.dat", "a/./b.dat", "", "a\\b.dat",
                     "a/b\nc.dat", "a/b\tc.dat"):
            with self.subTest(pfad=pfad), self.assertRaises(kf.FtpFehler):
                pd.dateien_und_ordner([{"path": pfad, "type": "file", "size": 1}])
        with self.assertRaises(kf.FtpFehler):
            pd.dateien_und_ordner([{"path": "../x", "type": "dir"}])

    def test_pfad_ok(self) -> None:
        for gut in ("a", "a/b", "Media/Größe.dat", "sce_sys/param.json", "a b/c d"):
            self.assertTrue(pd.pfad_ok(gut), gut)


DATEIEN = {"eboot.bin": 8192, "Media/big.dat": 600_000, "Media/sub/b.dat": 70_000, "Media/leer.bin": 0, "data/x.txt": 5,
           "sce_sys/param.json": 1258}
ORDNER = ["Media", "Media/sub", "Media/nichts", "data", "sce_sys"]


def baum() -> list[dict]:
    return ([{"path": p, "type": "file", "size": g} for p, g in DATEIEN.items()]
            + [{"path": o, "type": "dir"} for o in ORDNER])


class _Basis(unittest.TestCase):
    """Fake-Werkzeug und Attrappe je Test."""

    def setUp(self) -> None:
        self.ordner = Path(tempfile.mkdtemp(prefix="pkg_direkt_test_"))
        self.addCleanup(shutil.rmtree, self.ordner, ignore_errors=True)
        self.skript = self.ordner / "fake_werkzeug.py"
        self.skript.write_text(FAKE, encoding="utf-8")
        self.werkzeug = [sys.executable, str(self.skript)]
        self.wurzel = self.ordner / "konsole"
        self.wurzel.mkdir()
        self.arbeit = self.ordner / "arbeit"
        self.arbeit.mkdir()
        self.server: "Attrappe | None" = None

    def tearDown(self) -> None:
        if self.server is not None:
            self.server.schliessen()

    def start(self, **server) -> Attrappe:
        self.server = Attrappe(self.wurzel, **server)
        return self.server

    def paket(self, modus: str = "", dateien: "dict | None" = None) -> str:
        pfad = self.ordner / "paket.json"
        pfad.write_text(json.dumps({"dateien": dateien if dateien is not None else DATEIEN, "modus": modus}),
                        encoding="utf-8")
        return str(pfad)

    def laufen(self, modus: str = "", **kw):
        server = self.server or self.start()
        meldungen: list[str] = []
        kw.setdefault("pause", 0.05)
        stand = pd.direkt_entpacken(self.werkzeug, self.paket(modus, kw.pop("dateien", None)), "127.0.0.1", "/spiel",
                                    port=server.port, baum=kw.pop("baum", baum()), arbeitsordner=str(self.arbeit),
                                    zeile=meldungen.append, **kw)
        return stand, meldungen

    def gleich(self, pfad: str, erwartet_ab: int = 0) -> bool:
        datei = self.wurzel / "spiel" / pfad
        return datei.is_file() and datei.read_bytes() == inhalt(pfad, 0, DATEIEN[pfad])

    def alle_gleich(self) -> list[str]:
        return [p for p in DATEIEN if not self.gleich(p)]


class UebertragTests(_Basis):
    def test_alles_kommt_unveraendert_an_samt_ordnern(self) -> None:
        stand, meldungen = self.laufen()
        self.assertEqual([], self.alle_gleich())
        self.assertEqual((len(DATEIEN), sum(DATEIEN.values())), (stand.dateien, stand.bytes))
        self.assertEqual((len(DATEIEN), sum(DATEIEN.values())), (stand.dateien_gesamt, stand.bytes_gesamt))
        self.assertFalse(stand.abgebrochen)
        self.assertEqual((0, 0, 0), (stand.uebersprungen, stand.fortgesetzt, stand.wiederholt))
        self.assertTrue((self.wurzel / "spiel" / "Media" / "nichts").is_dir(), "ein leerer Ordner des Spiels fehlt")
        self.assertEqual(0, (self.wurzel / "spiel" / "Media" / "leer.bin").stat().st_size)
        self.assertIn("[info] fertig", meldungen, "die Meldungen des Werkzeugs (stderr) kommen an")

    def test_der_fortschritt_zaehlt_hoch_und_endet_beim_gesamten(self) -> None:
        zaehler = []
        self.laufen(auf_fortschritt=lambda s: zaehler.append((s.dateien, s.bytes, s.aktuell)))
        self.assertEqual(zaehler, sorted(zaehler, key=lambda z: z[1]), "die Bytes duerfen nie zurueckgehen")
        self.assertEqual((len(DATEIEN), sum(DATEIEN.values())), zaehler[-1][:2])
        self.assertIn("Media/big.dat", {z[2] for z in zaehler})

    def test_der_plan_liegt_nicht_mehr_im_arbeitsordner(self) -> None:
        self.laufen()
        self.assertEqual([], list(self.arbeit.iterdir()))

    def test_abriss_mitten_in_einer_datei_wird_fortgesetzt(self) -> None:
        server = self.start(abriss={"/spiel/Media/big.dat": 123_456})
        stand, _m = self.laufen()
        self.assertEqual([], self.alle_gleich())
        self.assertEqual((1, 1), (stand.wiederholt, stand.fortgesetzt))
        self.assertEqual([123_456], server.empfangen_von("STOR", "/spiel/Media/big.dat"))
        self.assertEqual([600_000 - 123_456], server.empfangen_von("APPE", "/spiel/Media/big.dat"))

    def test_ohne_appe_wird_die_datei_nach_dem_abriss_neu_gesendet(self) -> None:
        server = self.start(ohne_appe=True, abriss={"/spiel/Media/big.dat": 100_000})
        stand, _m = self.laufen()
        self.assertEqual([], self.alle_gleich())
        self.assertEqual([100_000, 600_000], server.empfangen_von("STOR", "/spiel/Media/big.dat"))
        self.assertEqual(0, stand.fortgesetzt)

    def test_fortsetzen_ueberspringt_fertige_und_haengt_angefangene_an(self) -> None:
        ziel = self.wurzel / "spiel"
        (ziel / "Media" / "sub").mkdir(parents=True)
        (ziel / "Media" / "sub" / "b.dat").write_bytes(inhalt("Media/sub/b.dat", 0, 70_000))         # fertig
        (ziel / "Media" / "big.dat").write_bytes(inhalt("Media/big.dat", 0, 250_000))                  # angefangen
        (ziel / "eboot.bin").write_bytes(b"x" * 20_000)                                                # groesser: neu
        server = self.start()
        stand, _m = self.laufen(fortsetzen=True)
        self.assertEqual([], self.alle_gleich())
        self.assertEqual((1, 1), (stand.uebersprungen, stand.fortgesetzt))
        self.assertEqual([], server.empfangen_von("STOR", "/spiel/Media/sub/b.dat"), "die fertige Datei wird nicht gesendet")
        self.assertEqual([350_000], server.empfangen_von("APPE", "/spiel/Media/big.dat"))
        self.assertEqual([8192], server.empfangen_von("STOR", "/spiel/eboot.bin"))
        self.assertEqual((len(DATEIEN), sum(DATEIEN.values())), (stand.dateien, stand.bytes), "alles zaehlt, auch das Uebersprungene")

    def test_ohne_fortsetzen_wird_alles_neu_geschrieben(self) -> None:
        ziel = self.wurzel / "spiel" / "Media" / "sub"
        ziel.mkdir(parents=True)
        (ziel / "b.dat").write_bytes(inhalt("Media/sub/b.dat", 0, 70_000))
        server = self.start()
        stand, _m = self.laufen(fortsetzen=False)
        self.assertEqual([70_000], server.empfangen_von("STOR", "/spiel/Media/sub/b.dat"))
        self.assertEqual((0, 0), (stand.uebersprungen, stand.fortgesetzt))

    def test_das_werkzeug_beginnt_bei_null_dann_wird_nicht_angehaengt(self) -> None:
        """Eine Datei, die das Werkzeug nicht mitten drin beginnen kann (nicht zusammenhaengend), kommt ganz."""
        ziel = self.wurzel / "spiel" / "Media"
        ziel.mkdir(parents=True)
        (ziel / "big.dat").write_bytes(inhalt("Media/big.dat", 0, 250_000))
        server = self.start()
        stand, _m = self.laufen("kein_start", fortsetzen=True)
        self.assertEqual([], self.alle_gleich(), "ein APPE der ganzen Datei haette sie verdoppelt")
        self.assertEqual([], server.empfangen_von("APPE", "/spiel/Media/big.dat"))
        self.assertEqual([600_000], server.empfangen_von("STOR", "/spiel/Media/big.dat"))
        self.assertEqual(0, stand.fortgesetzt)

    def test_abbruch_nur_zwischen_zwei_dateien(self) -> None:
        server = self.start()
        stand, _m = self.laufen(abbruch=lambda: server.verbindungen > 0 and len(server.empfangen) >= 2)
        self.assertTrue(stand.abgebrochen)
        self.assertEqual(2, stand.dateien)
        fertig = [p for p in DATEIEN if (self.wurzel / "spiel" / p).exists()]
        self.assertEqual(2, len(fertig))
        for p in fertig:
            self.assertTrue(self.gleich(p), "eine halbe Datei: " + p)

    def test_abbruch_vor_dem_ersten_byte(self) -> None:
        stand, _m = self.laufen(abbruch=lambda: True)
        self.assertTrue(stand.abgebrochen)
        self.assertEqual(0, stand.dateien)

    def test_das_werkzeug_stuerzt_mitten_in_einer_datei_ab(self) -> None:
        self.start()
        with self.assertRaises(pd.StromFehler) as fehler:
            self.laufen("stirb:Media/big.dat:200000")
        self.assertIn("Absturz: kaputt", str(fehler.exception), "die Fehlerzeile des Werkzeugs steht in der Meldung")
        self.assertEqual([], list(self.arbeit.iterdir()))

    def test_keine_rahmen_ist_ein_fehler(self) -> None:
        self.start()
        with self.assertRaisesRegex(pd.StromFehler, "kein Rahmen"):
            self.laufen("krumm")

    def test_ein_anderer_pfad_als_geplant_ist_ein_fehler(self) -> None:
        self.start()
        with self.assertRaisesRegex(pd.StromFehler, "statt"):
            self.laufen("falscher_pfad")

    def test_ein_falscher_endrahmen_ist_ein_fehler(self) -> None:
        self.start()
        with self.assertRaisesRegex(pd.StromFehler, "Endrahmen"):
            self.laufen("ende_falsch")

    def test_ein_rueckgabewert_ungleich_null_ist_ein_fehler(self) -> None:
        self.start()
        with self.assertRaisesRegex(pd.StromFehler, "Rueckgabewert 3"):
            self.laufen("rueckgabe_3")

    def test_ein_unsicherer_pfad_beendet_vor_dem_ersten_byte(self) -> None:
        server = self.start()
        with self.assertRaises(kf.FtpFehler):
            self.laufen(baum=[{"path": "../draussen.dat", "type": "file", "size": 1}], dateien={"../draussen.dat": 1})
        self.assertEqual(0, server.verbindungen, "gar nicht erst verbunden")

    def test_ein_leeres_paket(self) -> None:
        self.start()
        with self.assertRaisesRegex(kf.FtpFehler, "keine Dateien"):
            self.laufen(baum=[{"path": "a", "type": "dir"}])

    def test_das_werkzeug_laesst_sich_nicht_starten(self) -> None:
        server = self.start()
        with self.assertRaises(kf.FtpFehler):
            pd.direkt_entpacken(str(self.ordner / "gibt_es_nicht.exe"), self.paket(), "127.0.0.1", "/spiel", port=server.port,
                                baum=baum(), arbeitsordner=str(self.arbeit), pause=0.05)
        self.assertEqual([], list(self.arbeit.iterdir()), "die Plandatei bleibt nicht liegen")

    def test_keine_verbindung_gibt_eine_meldung(self) -> None:
        with self.assertRaises(kf.FtpFehler):
            pd.direkt_entpacken(self.werkzeug, self.paket(), "127.0.0.1", "/spiel", port=1, baum=baum(),
                                arbeitsordner=str(self.arbeit), pause=0.05)

    def test_nach_zu_vielen_abrissen_ist_schluss(self) -> None:
        self.start(abriss_immer={"/spiel/Media/big.dat"}, abriss_bytes=1000)
        with self.assertRaises(kf.FtpFehler):
            self.laufen(versuche=2)

    def test_der_ziel_ordner_darf_mit_und_ohne_schraegstrich_beginnen(self) -> None:
        server = self.start()
        pd.direkt_entpacken(self.werkzeug, self.paket(), "127.0.0.1", "spiel/", port=server.port, baum=baum(),
                            arbeitsordner=str(self.arbeit), pause=0.05)
        self.assertTrue(self.gleich("eboot.bin"))


def _echtes_werkzeug() -> str:
    pfad = wz.werkzeug_suchen([str(PROJEKT)])
    if not pfad or not wz.dotnet_ordner():
        return ""
    try:
        lauf = subprocess.run([pfad], capture_output=True, env=wz._umgebung(), timeout=60)   # noqa: SLF001
    except (OSError, subprocess.TimeoutExpired):
        return ""
    text = (lauf.stdout + lauf.stderr).decode("utf-8", errors="replace")
    return pfad if "stream-inner" in text else ""


@unittest.skipUnless(_echtes_werkzeug(), "das gebaute Werkzeug kennt stream-inner nicht (oder .NET fehlt)")
class EchtesWerkzeugTests(_Basis):
    """Ein kleines PS5-Paket mit dem echten Werkzeug bauen und direkt entpacken - jede Datei gegen extract-inner."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.werkzeug_pfad = _echtes_werkzeug()
        cls.basis = Path(tempfile.mkdtemp(prefix="pkg_direkt_echt_"))
        quelle, aus, temp = cls.basis / "quelle", cls.basis / "aus", cls.basis / "temp"
        for ordner in (quelle / "Media" / "sub", quelle / "data", aus, temp):
            ordner.mkdir(parents=True)
        zufall = random.Random(20261011)
        (quelle / "eboot.bin").write_bytes(bytes([0x54, 0x14, 0xF5, 0xEE]) + zufall.randbytes(8188))
        (quelle / "Media" / "big.dat").write_bytes(zufall.randbytes(3 * 1024 * 1024 + 123))
        (quelle / "Media" / "sub" / "b.dat").write_bytes(zufall.randbytes(70_001))
        (quelle / "Media" / "empty.bin").write_bytes(b"")
        (quelle / "data" / "x.txt").write_text("hallo", encoding="utf-8")
        lauf = subprocess.run([cls.werkzeug_pfad, "build", str(quelle), str(aus), "--content-id",
                               "UP9000-TEST00000_00-TESTSTREAM000001", "--title-id", "TEST00000", "--title", "Stromtest",
                               "--mode", "none", "--no-fake-sign", "--temp", str(temp)],
                              capture_output=True, env=wz._umgebung())   # noqa: SLF001
        pakete = list(aus.glob("*.pkg"))
        if lauf.returncode != 0 or not pakete:
            shutil.rmtree(cls.basis, ignore_errors=True)
            raise unittest.SkipTest("das Testpaket liess sich nicht bauen: %s" % lauf.stderr.decode("utf-8", "replace")[-200:])
        cls.paket_pfad = str(pakete[0])
        cls.baum = wz.baum(cls.werkzeug_pfad, cls.paket_pfad)
        cls.referenz = cls.basis / "referenz"
        liste = cls.basis / "alle.txt"
        liste.write_text("\n".join(e["path"] for e in cls.baum if e["type"] == "file") + "\n", encoding="utf-8")
        lauf = subprocess.run([cls.werkzeug_pfad, "extract-inner", cls.paket_pfad, str(cls.referenz), "--members", str(liste)],
                              capture_output=True, env=wz._umgebung())   # noqa: SLF001
        assert lauf.returncode == 0, lauf.stderr[-300:]

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.basis, ignore_errors=True)

    def _vergleichen(self) -> None:
        for eintrag in self.baum:
            if eintrag["type"] != "file":
                continue
            ziel = self.wurzel / "spiel" / eintrag["path"]
            soll = self.referenz / eintrag["path"]
            self.assertTrue(ziel.is_file(), eintrag["path"])
            self.assertEqual(hashlib.sha256(soll.read_bytes()).hexdigest(), hashlib.sha256(ziel.read_bytes()).hexdigest(),
                             eintrag["path"])

    def test_jede_datei_ist_gleich_dem_normalen_entpacken(self) -> None:
        server = self.start()
        stand = pd.direkt_entpacken(self.werkzeug_pfad, self.paket_pfad, "127.0.0.1", "/spiel", port=server.port,
                                    arbeitsordner=str(self.arbeit), pause=0.05, baum=self.baum)
        self._vergleichen()
        self.assertEqual(len([e for e in self.baum if e["type"] == "file"]), stand.dateien)

    def test_abriss_mitten_in_der_grossen_datei_mit_dem_echten_werkzeug(self) -> None:
        server = self.start(abriss={"/spiel/Media/big.dat": 1_500_000})
        stand = pd.direkt_entpacken(self.werkzeug_pfad, self.paket_pfad, "127.0.0.1", "/spiel", port=server.port,
                                    arbeitsordner=str(self.arbeit), pause=0.05, baum=self.baum)
        self._vergleichen()
        self.assertEqual((1, 1), (stand.wiederholt, stand.fortgesetzt))
        self.assertEqual([3 * 1024 * 1024 + 123 - 1_500_000], server.empfangen_von("APPE", "/spiel/Media/big.dat"))

    def test_fortsetzen_mit_dem_echten_werkzeug(self) -> None:
        ziel = self.wurzel / "spiel" / "Media"
        ziel.mkdir(parents=True)
        gross = (self.referenz / "Media" / "big.dat").read_bytes()
        (ziel / "big.dat").write_bytes(gross[:1_000_000])
        server = self.start()
        stand = pd.direkt_entpacken(self.werkzeug_pfad, self.paket_pfad, "127.0.0.1", "/spiel", port=server.port,
                                    arbeitsordner=str(self.arbeit), pause=0.05, baum=self.baum, fortsetzen=True)
        self._vergleichen()
        self.assertEqual(1, stand.fortgesetzt)
        self.assertEqual([len(gross) - 1_000_000], server.empfangen_von("APPE", "/spiel/Media/big.dat"))


if __name__ == "__main__":
    unittest.main()
