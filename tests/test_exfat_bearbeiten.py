# -*- coding: utf-8 -*-
"""Dateien direkt in einem exFAT-Abbild aendern (``exfat_bearbeiten``): umbenennen, loeschen, ersetzen, hinzufuegen, Undo-Journal.

Die Abbilder entstehen mit dem Schreiber von MkPFS (wie im Programm): 64-KiB-Cluster und **kein freier Cluster**. Geprueft wird dreifach:
mit der eigenen Ordnungspruefung (``ExfatAbbild.pruefen``), mit dem Leser des Programms (``spielbaum.ExfatBaum``) und - wo WSL da ist -
mit dem exFAT-Treiber des Linux-Kerns, der das Abbild einhaengt und jede Datei liest (ein unabhaengiger Zeuge: er prueft die
Satzpruefsummen und Namens-Hashes selbst).
"""
from __future__ import annotations

import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "MkPFS-1.1.0"))

from mkpfs.exfat_writer import iter_exfat_image             # noqa: E402

from ps5_validator.utils import exfat_bearbeiten as eb       # noqa: E402
from ps5_validator.utils import spielbaum as sb              # noqa: E402

CL = 65536


def _inh(name: str, n: int) -> bytes:
    """Deterministischer Inhalt der Laenge ``n``, der sich je Name unterscheidet."""
    stueck = hashlib.sha256(name.encode()).digest()
    return (stueck * (n // len(stueck) + 1))[:n]


class _Abbild(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="exfatbearb_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.pfad = os.path.join(self.tmp, "spiel.exfat")

    def bauen(self, dateien: "dict[str, bytes]", leere_ordner: "tuple[str, ...]" = ()) -> None:
        ordner = os.path.join(self.tmp, "quelle")
        shutil.rmtree(ordner, True)
        os.makedirs(ordner)
        for rel, daten in dateien.items():
            voll = os.path.join(ordner, *rel.split("/"))
            os.makedirs(os.path.dirname(voll), exist_ok=True)
            Path(voll).write_bytes(daten)
        for rel in leere_ordner:
            os.makedirs(os.path.join(ordner, *rel.split("/")), exist_ok=True)
        with open(self.pfad, "wb") as fh:
            for stueck in iter_exfat_image(Path(ordner)):
                fh.write(stueck)
        self.erwartet = dict(dateien)

    def lesen(self) -> "dict[str, bytes]":
        with sb.ExfatBaum(self.pfad) as baum:
            return {rel: b"".join(d.lesen()) for rel, d in baum.suchen().items()}

    def ordner(self) -> "list[str]":
        with sb.ExfatBaum(self.pfad) as baum:
            baum.dateien()
            return baum.ordner()

    def quelle(self, name: str, n: int) -> str:
        pfad = os.path.join(self.tmp, "neu_" + name.replace("/", "_"))
        Path(pfad).write_bytes(_inh(name, n))
        return pfad

    def pruefen(self) -> None:
        with eb.ExfatAbbild(self.pfad) as a:
            self.assertEqual([], a.pruefen())

    def dateien(self) -> "dict[str, bytes]":
        return {
            "eboot.bin": _inh("eboot.bin", 3000),
            "sce_sys/param.json": b'{"titleId":"PPSA00001"}',
            "data/gross.bin": _inh("gross", 5 * CL + 123),
            "data/mittel.pak": _inh("mittel", 2 * CL),
            "data/tief/klein.cfg": b"a=1\n",
            "data/tief/leer.bin": b"",
            "Media/video.bin": _inh("video", 3 * CL - 1),
        }


class AufbauTests(_Abbild):
    def test_ein_frisches_abbild_ist_in_ordnung_und_hat_keinen_freien_cluster(self) -> None:
        self.bauen(self.dateien())
        with eb.ExfatAbbild(self.pfad) as a:
            self.assertEqual([], a.pruefen())
            self.assertEqual(0, a.freie_cluster(), "Abbilder dieses Programms haben keinen freien Cluster")
            self.assertEqual(CL, a.cluster_groesse)
            namen = {n for n, _o, _g in a.auflisten()}
            self.assertEqual({"eboot.bin", "sce_sys", "data", "Media"}, namen)

    def test_keine_exfat_datei(self) -> None:
        Path(self.pfad).write_bytes(b"x" * 4096)
        with self.assertRaises(eb.ExfatBearbeitenFehler):
            eb.ExfatAbbild(self.pfad)

    def test_ohne_aenderung_wird_nichts_geschrieben(self) -> None:
        self.bauen(self.dateien())
        vorher = Path(self.pfad).read_bytes()
        with eb.ExfatAbbild(self.pfad) as a:
            a.speichern()
        self.assertEqual(vorher, Path(self.pfad).read_bytes())
        self.assertFalse(os.path.exists(eb.journal_pfad(self.pfad)))


class UmbenennenTests(_Abbild):
    def setUp(self) -> None:
        super().setUp()
        self.bauen(self.dateien())

    def test_datei_umbenennen_inhalt_und_rest_bleiben(self) -> None:
        with eb.ExfatAbbild(self.pfad) as a:
            a.umbenennen("data/mittel.pak", "umbenannt.pak")
            a.speichern()
        gelesen = self.lesen()
        erwartet = dict(self.erwartet)
        erwartet["data/umbenannt.pak"] = erwartet.pop("data/mittel.pak")
        self.assertEqual(erwartet, gelesen)
        self.pruefen()

    def test_laengerer_name_braucht_mehr_namenseintraege(self) -> None:
        lang = "ein_sehr_langer_dateiname_mit_vielen_zeichen_ueber_dreissig.bin"
        with eb.ExfatAbbild(self.pfad) as a:
            a.umbenennen("eboot.bin", lang)
            a.speichern()
        self.assertEqual(self.erwartet["eboot.bin"], self.lesen()[lang])
        self.pruefen()

    def test_nur_die_schreibung_aendern(self) -> None:
        with eb.ExfatAbbild(self.pfad) as a:
            a.umbenennen("eboot.bin", "EBOOT.BIN")
            a.speichern()
        self.assertIn("EBOOT.BIN", self.lesen())
        self.pruefen()

    def test_ordner_umbenennen_die_kinder_sind_unter_dem_neuen_pfad(self) -> None:
        with eb.ExfatAbbild(self.pfad) as a:
            a.umbenennen("data", "daten")
            a.speichern()
        gelesen = self.lesen()
        erwartet = {("daten/" + r[5:] if r.startswith("data/") else r): v for r, v in self.erwartet.items()}
        self.assertEqual(erwartet, gelesen)
        self.assertIn("daten/tief", self.ordner())
        self.pruefen()

    def test_ordner_und_danach_eine_datei_darin_in_einem_lauf(self) -> None:
        """Der Cache der umbenannten Ordner folgt dem neuen Pfad: Aenderungen davor und danach gelten beide."""
        with eb.ExfatAbbild(self.pfad) as a:
            a.umbenennen("data/tief/klein.cfg", "klein2.cfg")
            a.umbenennen("data", "daten")
            a.umbenennen("daten/tief/klein2.cfg", "klein3.cfg")
            a.speichern()
        self.assertEqual(b"a=1\n", self.lesen()["daten/tief/klein3.cfg"])
        self.pruefen()

    def test_vergebener_oder_unzulaessiger_name(self) -> None:
        with eb.ExfatAbbild(self.pfad) as a:
            with self.assertRaises(eb.ExfatBearbeitenFehler):
                a.umbenennen("data/mittel.pak", "GROSS.BIN")                 # Schreibung egal: gibt es schon
            with self.assertRaises(eb.ExfatBearbeitenFehler):
                a.umbenennen("data/mittel.pak", "a:b")
            with self.assertRaises(eb.ExfatBearbeitenFehler):
                a.umbenennen("data/mittel.pak", "")
            with self.assertRaises(eb.ExfatBearbeitenFehler):
                a.umbenennen("data/mittel.pak", "ende.")
            with self.assertRaises(eb.ExfatBearbeitenFehler):
                a.umbenennen("gibtsnicht", "x")
            a.speichern()
        self.assertEqual(self.erwartet, self.lesen(), "Nach abgelehnten Aenderungen bleibt alles wie es war")

    def test_der_vergebene_name_wird_ohne_beachtung_der_schreibung_erkannt(self) -> None:
        with eb.ExfatAbbild(self.pfad) as a:
            a.umbenennen("data/gross.bin", "x.bin")
            with self.assertRaises(eb.ExfatBearbeitenFehler):
                a.umbenennen("data/mittel.pak", "X.BIN")


class NamenUndLaengenTests(_Abbild):
    """Gesamtpruefung 14.11.2026, E6/E7."""

    def setUp(self) -> None:
        super().setUp()
        self.bauen({"eboot.bin": b"e", "sce_sys/param.json": b"{}", "a.bin": _inh("a", 10)})

    def _strom(self, a: "eb.ExfatAbbild", anfang: str) -> "tuple[eb._Satz, bytes]":
        s = [x for x in a._wurzel.saetze if x.name.startswith(anfang)][0]
        return s, bytes(a._wurzel.roh[s.anfang + 32: s.anfang + 64])

    def test_namen_ausserhalb_der_bmp_zaehlen_utf16_einheiten(self) -> None:
        name = "Spielstand_\U0001F600"                                        # 12 Zeichen, 13 UTF-16-Einheiten
        with eb.ExfatAbbild(self.pfad) as a:
            a.umbenennen("a.bin", name)
            a.speichern()
        with eb.ExfatAbbild(self.pfad) as a:
            s, strom = self._strom(a, "Spielstand")
            self.assertEqual(13, strom[3])
            self.assertEqual(name, s.name)
            self.assertEqual([], a.pruefen())
        # Gelesen mit dem eigenen gezielten Leser (der Leser von MkPFS kuerzt nach Zeichen - Fremdcode, nicht geaendert).
        from ps5_validator.utils import exfat_gezielt
        with eb.ExfatAbbild(self.pfad) as a:
            roh = bytes(a._wurzel.roh)
        self.assertIn(name, [e.name for e in exfat_gezielt._eintraege([roh[i:i + 32] for i in range(0, len(roh), 32)])])

    def test_zu_lang_in_utf16_wird_abgelehnt(self) -> None:
        with eb.ExfatAbbild(self.pfad) as a:
            with self.assertRaises(eb.ExfatBearbeitenFehler):
                a.umbenennen("a.bin", "\U0001F600" * 128)                       # 128 Zeichen, aber 256 Einheiten
            a.umbenennen("a.bin", "\U0001F600" * 127)                           # 254 Einheiten: geht
            a.speichern()
        with eb.ExfatAbbild(self.pfad) as a:
            self.assertIn("\U0001F600" * 127, [s.name for s in a._wurzel.saetze])
            self.assertEqual([], a.pruefen())

    def test_umbenennen_behaelt_die_gueltige_datenlaenge(self) -> None:
        """E7: In einem fremden Abbild kann ValidDataLength kleiner sein als DataLength - umbenennen setzte sie gleich."""
        with eb.ExfatAbbild(self.pfad) as a:
            s, _strom = self._strom(a, "a.bin")
            struct.pack_into("<Q", a._wurzel.roh, s.anfang + 32 + 8, 4)          # VDL 4 statt 10, wie ein fremdes Abbild es haette
            a.umbenennen("a.bin", "b.bin")
            _s, strom = self._strom(a, "b.bin")
            self.assertEqual(4, struct.unpack_from("<Q", strom, 8)[0])
            self.assertEqual(10, struct.unpack_from("<Q", strom, 0x18)[0])


class LoeschenTests(_Abbild):
    def setUp(self) -> None:
        super().setUp()
        self.bauen(self.dateien())

    def test_datei_loeschen_gibt_ihre_cluster_frei(self) -> None:
        with eb.ExfatAbbild(self.pfad) as a:
            n = a.loeschen("data/gross.bin")
            self.assertEqual(6, n)                                          # 5 Cluster plus 123 Bytes
            self.assertEqual(6, a.freie_cluster())
            a.speichern()
        erwartet = dict(self.erwartet)
        del erwartet["data/gross.bin"]
        self.assertEqual(erwartet, self.lesen())
        with eb.ExfatAbbild(self.pfad) as a:
            self.assertEqual([], a.pruefen())
            self.assertEqual(6, a.freie_cluster())

    def test_ordner_loeschen_samt_inhalt(self) -> None:
        with eb.ExfatAbbild(self.pfad) as a:
            a.loeschen("data")
            a.speichern()
        erwartet = {r: v for r, v in self.erwartet.items() if not r.startswith("data/")}
        self.assertEqual(erwartet, self.lesen())
        self.assertNotIn("data/tief", self.ordner())
        self.pruefen()

    def test_leere_datei_loeschen(self) -> None:
        with eb.ExfatAbbild(self.pfad) as a:
            self.assertEqual(0, a.loeschen("data/tief/leer.bin"))
            a.speichern()
        self.assertNotIn("data/tief/leer.bin", self.lesen())
        self.pruefen()

    def test_gelöschter_name_ist_wieder_frei(self) -> None:
        with eb.ExfatAbbild(self.pfad) as a:
            a.loeschen("data/mittel.pak")
            a.hinzufuegen("data/mittel.pak", self.quelle("m", 10))
            a.speichern()
        self.assertEqual(_inh("m", 10), self.lesen()["data/mittel.pak"])
        self.pruefen()


class HinzufuegenTests(_Abbild):
    def setUp(self) -> None:
        super().setUp()
        self.bauen(self.dateien())

    def test_ohne_freien_platz_kein_hinzufuegen_und_nichts_geschrieben(self) -> None:
        vorher = Path(self.pfad).read_bytes()
        with eb.ExfatAbbild(self.pfad) as a:
            with self.assertRaises(eb.PlatzFehlt):
                a.hinzufuegen("neu.bin", self.quelle("neu", CL + 1))
            a.speichern()
        self.assertEqual(vorher, Path(self.pfad).read_bytes())
        self.assertFalse(os.path.exists(eb.journal_pfad(self.pfad)))

    def test_nach_dem_loeschen_ist_platz(self) -> None:
        with eb.ExfatAbbild(self.pfad) as a:
            a.loeschen("data/gross.bin")                                    # 6 Cluster
            a.hinzufuegen("data/neu.bin", self.quelle("neu", 4 * CL + 7))   # 5 Cluster
            a.hinzufuegen("data/tief/auch.bin", self.quelle("auch", 10))    # 1 Cluster
            a.speichern()
        gelesen = self.lesen()
        self.assertEqual(_inh("neu", 4 * CL + 7), gelesen["data/neu.bin"])
        self.assertEqual(_inh("auch", 10), gelesen["data/tief/auch.bin"])
        with eb.ExfatAbbild(self.pfad) as a:
            self.assertEqual([], a.pruefen())
            self.assertEqual(0, a.freie_cluster())

    def test_leere_datei_braucht_keinen_cluster(self) -> None:
        leer = os.path.join(self.tmp, "leer")
        Path(leer).write_bytes(b"")
        with eb.ExfatAbbild(self.pfad) as a:
            a.hinzufuegen("data/leer2.bin", leer)
            a.speichern()
        self.assertEqual(b"", self.lesen()["data/leer2.bin"])
        self.pruefen()

    def test_zerstueckelter_platz_wird_ueber_die_fat_verkettet(self) -> None:
        """Zwei Luecken von je einem Cluster: Eine Datei von zwei Clustern passt nur verkettet."""
        self.bauen({"a": _inh("a", CL), "b": _inh("b", CL), "c": _inh("c", CL), "d": _inh("d", CL),
                    "eboot.bin": b"e", "sce_sys/param.json": b"{}"})
        with eb.ExfatAbbild(self.pfad) as a:
            a.loeschen("a")
            a.loeschen("c")
            a.hinzufuegen("zwei.bin", self.quelle("zwei", 2 * CL))
            a.speichern()
        self.assertEqual(_inh("zwei", 2 * CL), self.lesen()["zwei.bin"])
        self.assertEqual(_inh("b", CL), self.lesen()["b"])
        self.pruefen()

    def test_name_schon_vergeben(self) -> None:
        with eb.ExfatAbbild(self.pfad) as a:
            a.loeschen("data/gross.bin")
            with self.assertRaises(eb.ExfatBearbeitenFehler):
                a.hinzufuegen("data/MITTEL.PAK", self.quelle("x", 5))

    def test_ordner_anlegen_und_darin_eine_datei(self) -> None:
        with eb.ExfatAbbild(self.pfad) as a:
            a.loeschen("data/gross.bin")
            a.ordner_anlegen("saves")
            a.hinzufuegen("saves/slot1.sav", self.quelle("slot", 300))
            a.speichern()
        self.assertIn("saves", self.ordner())
        self.assertEqual(_inh("slot", 300), self.lesen()["saves/slot1.sav"])
        self.pruefen()

    def test_neuer_ordner_ist_leer_auch_wenn_im_cluster_alter_inhalt_steht(self) -> None:
        """Gesamtpruefung 14.11.2026, E1: Der Cluster eines neuen Ordners wurde bis zum Speichern von der Platte gelesen."""
        faelle = {"0xFF": b"\xff" * (2 * CL), "Satzbeginn 0x85": b"\x85\x05" + bytes(2 * CL - 2),
                  "File+Name": b"\x41" * 32 + b"\xc1" * 32 + bytes(3 * CL - 64)}
        for titel, alt in faelle.items():
            with self.subTest(titel):
                self.bauen({"eboot.bin": b"e" * 100, "sce_sys/param.json": b"{}", "alt.bin": alt})
                with eb.ExfatAbbild(self.pfad) as a:
                    a.loeschen("alt.bin")
                    a.ordner_anlegen("saves")
                    self.assertEqual([], a.auflisten("saves"))
                    a.hinzufuegen("saves/slot1.sav", self.quelle("slot", 300))
                    a.speichern()
                self.assertEqual(_inh("slot", 300), self.lesen()["saves/slot1.sav"])
                with eb.ExfatAbbild(self.pfad) as a:
                    self.assertEqual([("slot1.sav", False, 300)], a.auflisten("saves"))
                self.pruefen()

    def test_neuer_ordner_zeigt_keine_dateien_eines_geloeschten(self) -> None:
        self.bauen({"eboot.bin": b"e" * 100, "sce_sys/param.json": b"{}", "A/eins.bin": _inh("1", 10), "A/zwei.bin": _inh("2", CL)})
        with eb.ExfatAbbild(self.pfad) as a:
            a.loeschen("A")
            a.ordner_anlegen("B")
            self.assertEqual([], a.auflisten("B"), "keine Phantome aus Ordner A")
            a.hinzufuegen("B/meins.bin", self.quelle("meins", 2 * CL))
            a.speichern()
        self.assertEqual({"eboot.bin", "sce_sys/param.json", "B/meins.bin"}, set(self.lesen()))
        self.pruefen()

    def test_geplante_ordnerstelle_ueberschreibt_keine_neuen_daten(self) -> None:
        """Gesamtpruefung 14.11.2026, E2: Stelle in einem Ordner-Cluster, der frei wird und neue Dateidaten bekommt."""
        with eb.ExfatAbbild(self.pfad) as a:                                    # Fall A: Ordner anlegen, wieder loeschen
            a.loeschen("data/mittel.pak")
            a.ordner_anlegen("Neu")
            a.loeschen("Neu")
            a.hinzufuegen("x.bin", self.quelle("x", 2 * CL))
            a.speichern()
        self.assertEqual(_inh("x", 2 * CL), self.lesen()["x.bin"])
        self.pruefen()
        self.bauen(self.dateien())
        with eb.ExfatAbbild(self.pfad) as a:                                    # Fall B: Eintrag im Ordner aendern, Ordner loeschen
            a.loeschen("data/tief/klein.cfg")
            a.loeschen("data/tief")
            a.hinzufuegen("y.bin", self.quelle("y", 2 * CL))
            a.speichern()
        self.assertEqual(_inh("y", 2 * CL), self.lesen()["y.bin"])
        self.pruefen()

    def test_voller_ordner_waechst_um_einen_cluster(self) -> None:
        """Ein Ordner, dessen Cluster voll ist, bekommt einen weiteren; die Laenge im Elternordner folgt."""
        dateien = {"eboot.bin": b"e", "sce_sys/param.json": b"{}", "weg.bin": _inh("weg", 8 * CL)}
        for i in range(678):                                              # 678 x 3 Eintraege + 6 Wurzel-/Satzeintraege ~ 2040 von 2048
            dateien["f%04d" % i] = b""
        self.bauen(dateien)
        with eb.ExfatAbbild(self.pfad) as a:
            a.loeschen("weg.bin")
            vorher = len(a._wurzel.cluster)
            for i in range(6):
                a.hinzufuegen("g%03d.bin" % i, self.quelle("g%d" % i, 9))
            self.assertGreater(len(a._wurzel.cluster), vorher, "Der Wurzelordner haette wachsen muessen")
            a.speichern()
        gelesen = self.lesen()
        for i in range(6):
            self.assertEqual(_inh("g%d" % i, 9), gelesen["g%03d.bin" % i])
        self.assertEqual(678, sum(1 for r in gelesen if r.startswith("f")))
        self.pruefen()


class TransaktionTests(_Abbild):
    """Scheitert eine Aenderung mitten drin, steht im Speicher alles wieder wie vorher - nichts bleibt belegt, nichts wird vorgemerkt."""

    def test_scheitert_die_ordnererweiterung_leckt_der_vorher_zugeteilte_cluster_nicht(self) -> None:
        dateien = {"eboot.bin": b"e", "sce_sys/param.json": b"{}", "weg.bin": _inh("weg", CL)}
        for i in range(678):
            dateien["f%04d" % i] = b""
        self.bauen(dateien)
        vorher = Path(self.pfad).read_bytes()
        with eb.ExfatAbbild(self.pfad) as a:
            a.loeschen("weg.bin")                                          # genau ein freier Cluster
            a.hinzufuegen("g000.bin", self.quelle("g0", 9))                 # braucht ihn fuer die Daten - der Ordner ist noch nicht voll
            self.assertEqual(0, a.freie_cluster())
            a.loeschen("g000.bin")
            self.assertEqual(1, a.freie_cluster())
            # jetzt ist der Wurzelordner so gut wie voll; zwei neue Dateien: die erste passt, bei der zweiten muesste er wachsen
            a.hinzufuegen("h000.bin", self.quelle("h0", 0))                 # leer: kein Cluster
            a.hinzufuegen("h001.bin", self.quelle("h1", 0))
            frei = a.freie_cluster()
            geplant = (len(a._plan.stellen), len(a._plan.daten))
            with self.assertRaises(eb.PlatzFehlt):
                for i in range(2, 40):                                      # irgendwann ist der Ordner voll und er braucht den letzten Cluster
                    a.hinzufuegen("h%03d.bin" % i, self.quelle("h", 0))
                    a.hinzufuegen("d%03d.bin" % i, self.quelle("d%d" % i, 9))      # braucht einen Cluster fuer Daten
            self.assertEqual([], a.pruefen(), "Nach der abgelehnten Aenderung stimmt der Speicherstand")
            self.assertLessEqual(a.freie_cluster(), frei)
        self.assertEqual(vorher, Path(self.pfad).read_bytes(), "ohne speichern() bleibt das Abbild unberuehrt")

    def test_abgelehnte_aenderung_laesst_keine_vorgemerkten_daten_zurueck(self) -> None:
        self.bauen(self.dateien())
        vorher = Path(self.pfad).read_bytes()
        with eb.ExfatAbbild(self.pfad) as a:
            with self.assertRaises(eb.ExfatBearbeitenFehler):
                a.hinzufuegen("data/mittel.pak", self.quelle("x", 5))      # Name vergeben
            with self.assertRaises(eb.PlatzFehlt):
                a.hinzufuegen("neu.bin", self.quelle("neu", 3 * CL))       # kein Platz
            with self.assertRaises(eb.PlatzFehlt):
                a.ersetzen("data/mittel.pak", self.quelle("riesig", 9 * CL))
            self.assertEqual(([], []), (a._plan.stellen, a._plan.daten))
            self.assertEqual(set(), a._daten_cluster)
            a.speichern()
        self.assertEqual(vorher, Path(self.pfad).read_bytes())


class ErsetzenTests(_Abbild):
    def setUp(self) -> None:
        super().setUp()
        self.bauen(self.dateien())

    def test_kleiner_ersetzen_gibt_den_rest_frei(self) -> None:
        with eb.ExfatAbbild(self.pfad) as a:
            a.ersetzen("data/gross.bin", self.quelle("klein", CL // 2))     # war 6 Cluster, jetzt 1
            self.assertEqual(5, a.freie_cluster())
            a.speichern()
        self.assertEqual(_inh("klein", CL // 2), self.lesen()["data/gross.bin"])
        with eb.ExfatAbbild(self.pfad) as a:
            self.assertEqual([], a.pruefen())
            self.assertEqual(5, a.freie_cluster())

    def test_gleich_gross_ersetzen(self) -> None:
        with eb.ExfatAbbild(self.pfad) as a:
            a.ersetzen("data/mittel.pak", self.quelle("m2", 2 * CL))
            a.speichern()
        gelesen = self.lesen()
        self.assertEqual(_inh("m2", 2 * CL), gelesen["data/mittel.pak"])
        self.assertEqual(self.erwartet["data/gross.bin"], gelesen["data/gross.bin"])
        self.pruefen()

    def test_groesser_ersetzen_nur_mit_freiem_platz(self) -> None:
        vorher = Path(self.pfad).read_bytes()
        with eb.ExfatAbbild(self.pfad) as a:
            with self.assertRaises(eb.PlatzFehlt):
                a.ersetzen("data/mittel.pak", self.quelle("riesig", 9 * CL))
            self.assertEqual([], a.pruefen(), "Der Speicherstand nach der Ablehnung stimmt wieder")
            a.speichern()
        self.assertEqual(vorher, Path(self.pfad).read_bytes())
        # mit Luft: erst eine andere Datei loeschen, dann passt es
        with eb.ExfatAbbild(self.pfad) as a:
            a.loeschen("Media/video.bin")                                   # 3 Cluster
            a.ersetzen("data/mittel.pak", self.quelle("etwas", 4 * CL))     # braucht 4: 2 eigene + 2 freie
            a.speichern()
        self.assertEqual(_inh("etwas", 4 * CL), self.lesen()["data/mittel.pak"])
        self.pruefen()

    def test_ersetzen_durch_eine_leere_datei(self) -> None:
        leer = os.path.join(self.tmp, "leer")
        Path(leer).write_bytes(b"")
        with eb.ExfatAbbild(self.pfad) as a:
            a.ersetzen("data/mittel.pak", leer)
            a.speichern()
        self.assertEqual(b"", self.lesen()["data/mittel.pak"])
        self.pruefen()

    def test_ein_ordner_ist_kein_inhalt(self) -> None:
        with eb.ExfatAbbild(self.pfad) as a:
            with self.assertRaises(eb.ExfatBearbeitenFehler):
                a.ersetzen("data", self.quelle("x", 1))


class JournalTests(_Abbild):
    def setUp(self) -> None:
        super().setUp()
        self.bauen(self.dateien())
        self.original = Path(self.pfad).read_bytes()

    def _hart_abbrechen(self, a: "eb.ExfatAbbild", nach_daten: bool = False) -> None:
        """Nachbildung eines hart beendeten Programms: Das Journal liegt, das Abbild ist teilweise veraendert, nichts raeumt auf."""
        echt = eb.journal_zurueckspielen
        eb.journal_zurueckspielen = lambda _p, **_k: False
        try:
            if nach_daten:
                original_fsync = os.fsync
                aufrufe = {"n": 0}

                def fsync(fd):
                    aufrufe["n"] += 1
                    if aufrufe["n"] >= 2:                                    # 1: das Journal, 2: das Abbild - vor dem Ende abbrechen
                        raise SystemExit("hart beendet")
                    return original_fsync(fd)
                os.fsync = fsync
                try:
                    a.speichern()
                except SystemExit:
                    pass
                finally:
                    os.fsync = original_fsync
        finally:
            eb.journal_zurueckspielen = echt

    def test_hart_beendet_nach_dem_schreiben_wird_beim_naechsten_oeffnen_zurueckgespielt(self) -> None:
        a = eb.ExfatAbbild(self.pfad)
        a.loeschen("data/gross.bin")
        a.ersetzen("data/mittel.pak", self.quelle("neu", 5 * CL))            # nutzt die frei gewordenen Cluster, auch alte
        self._hart_abbrechen(a, nach_daten=True)
        a.schliessen()
        self.assertTrue(os.path.exists(eb.journal_pfad(self.pfad)), "Das Journal muss liegen bleiben")
        self.assertNotEqual(self.original, Path(self.pfad).read_bytes(), "Das Abbild war schon veraendert")
        with eb.ExfatAbbild(self.pfad) as b:                                  # Oeffnen spielt zurueck
            self.assertEqual([], b.pruefen())
        self.assertEqual(self.original, Path(self.pfad).read_bytes(), "Byte fuer Byte wie vorher")
        self.assertFalse(os.path.exists(eb.journal_pfad(self.pfad)))

    def test_geaenderte_quelldatei_wird_nicht_still_angepasst(self) -> None:
        """Gesamtpruefung 14.11.2026, E5: Zwischen Vormerken und Anwenden gewachsen oder geschrumpft - Fehler, Abbild wie vorher."""
        for titel, neue_laenge in (("gewachsen", 2 * CL + 50), ("geschrumpft", 10)):
            with self.subTest(titel):
                quelle = self.quelle("aendert_sich", 2 * CL)
                with eb.ExfatAbbild(self.pfad) as a:
                    a.loeschen("data/mittel.pak")
                    a.hinzufuegen("data/neu.bin", quelle)
                    Path(quelle).write_bytes(_inh("anders", neue_laenge))
                    with self.assertRaises(eb.ExfatBearbeitenFehler):
                        a.speichern()
                self.assertEqual(self.original, Path(self.pfad).read_bytes())
                self.assertFalse(os.path.exists(eb.journal_pfad(self.pfad)))

    def test_journalgrenze_greift_vor_dem_einlesen(self) -> None:
        """Gesamtpruefung 14.11.2026, E4: Bis dahin las ``speichern`` jeden zu sichernden Cluster ein und pruefte erst dann die Grenze."""
        gelesen = {"n": 0}
        with mock.patch.object(eb, "_JOURNAL_DATEN_MAX", CL), eb.ExfatAbbild(self.pfad) as a:
            a.loeschen("data/gross.bin")                                       # 6 Cluster frei
            a.hinzufuegen("data/neu.bin", self.quelle("neu", 5 * CL))           # 5 davon werden ueberschrieben - zu viel fuers Journal
            echt = a._fh.read

            def zaehlen(n: int = -1) -> bytes:
                daten = echt(n)
                gelesen["n"] += len(daten)
                return daten
            a._fh.read = zaehlen                                               # type: ignore[method-assign]
            with self.assertRaises(eb.PlatzFehlt):
                a.speichern()
        self.assertLessEqual(gelesen["n"], 2 * CL, "nur FAT und Bitmap, nicht die alten Dateicluster")
        self.assertEqual(self.original, Path(self.pfad).read_bytes())

    def test_fehler_mitten_im_schreiben_stellt_sofort_wieder_her(self) -> None:
        a = eb.ExfatAbbild(self.pfad)
        a.loeschen("Media/video.bin")
        a.hinzufuegen("neu.bin", self.quelle("neu", 2 * CL))

        def kaputt(_fh) -> None:
            raise OSError("Platte voll")
        a._plan.daten.append(kaputt)
        with self.assertRaises(OSError):
            a.speichern()
        a.schliessen()
        self.assertEqual(self.original, Path(self.pfad).read_bytes())
        self.assertFalse(os.path.exists(eb.journal_pfad(self.pfad)))

    def test_ein_unvollstaendiges_journal_heisst_es_wurde_noch_nichts_geaendert(self) -> None:
        a = eb.ExfatAbbild(self.pfad)
        a.loeschen("data/mittel.pak")
        a._metadaten_planen()
        stellen = []
        for offset, neu in a._plan.stellen:
            a._fh.seek(offset)
            stellen.append((offset, a._fh.read(len(neu))))
        eb._journal_schreiben(eb.journal_pfad(self.pfad), stellen)
        a.schliessen()
        roh = Path(eb.journal_pfad(self.pfad)).read_bytes()
        Path(eb.journal_pfad(self.pfad)).write_bytes(roh[:-5])              # abgeschnitten: ohne Ende-Marke
        self.assertFalse(eb.journal_zurueckspielen(self.pfad), "Ein unvollstaendiges Journal spielt nichts zurueck")
        self.assertFalse(os.path.exists(eb.journal_pfad(self.pfad)))
        self.assertEqual(self.original, Path(self.pfad).read_bytes())

    def test_ein_beschaedigtes_journal_wird_nicht_zurueckgespielt(self) -> None:
        eb._journal_schreiben(eb.journal_pfad(self.pfad), [(4096, b"x" * 64)])
        roh = bytearray(Path(eb.journal_pfad(self.pfad)).read_bytes())
        roh[-30] ^= 0xFF                                                      # ein Byte im Inhalt kippen: die Pruefsumme stimmt nicht
        Path(eb.journal_pfad(self.pfad)).write_bytes(bytes(roh))
        self.assertFalse(eb.journal_zurueckspielen(self.pfad))
        self.assertEqual(self.original, Path(self.pfad).read_bytes())

    def test_nach_einem_erfolg_bleibt_kein_journal(self) -> None:
        with eb.ExfatAbbild(self.pfad) as a:
            a.loeschen("data/mittel.pak")
            a.speichern()
        self.assertFalse(os.path.exists(eb.journal_pfad(self.pfad)))
        self.assertFalse(os.path.exists(eb.journal_pfad(self.pfad) + ".neu"))


def _wsl_pfad(pfad: str) -> str:
    laufwerk, rest = os.path.splitdrive(os.path.abspath(pfad))
    return "/mnt/%s%s" % (laufwerk[:1].lower(), rest.replace("\\", "/"))


def _wsl_pruefen(abbild: str, tmp: str) -> "dict[str, str] | None":
    """Haengt das Abbild in WSL (Ubuntu-26.04, als root, nur lesend) ein und liefert ``{Pfad: SHA-256}``; ``None``, wenn das nicht geht."""
    if os.name != "nt" or not shutil.which("wsl.exe"):
        return None
    skript = os.path.join(tmp, "wsl_pruefen.sh")
    with open(skript, "w", newline="\n") as fh:
        fh.write('#!/bin/bash\nMP=/tmp/exfat_bearb_mp\nmkdir -p "$MP"\n'
                 'mount -o loop,ro -t exfat "%s" "$MP" || exit 41\n'
                 'cd "$MP" && find . -type f -print0 | sort -z | xargs -0 -r sha256sum\n'
                 'echo "---ORDNER"\nfind . -type d | sort\n'
                 'cd / && umount "$MP"; rmdir "$MP"\n' % _wsl_pfad(abbild))
    try:
        erg = subprocess.run(["wsl.exe", "-d", "Ubuntu-26.04", "-u", "root", "--", "bash", _wsl_pfad(skript)],
                             capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if erg.returncode != 0:
        return None
    ausgabe = erg.stdout.replace("\x00", "")
    dateien, _, _ordner = ausgabe.partition("---ORDNER")
    ergebnis: "dict[str, str]" = {}
    for zeile in dateien.splitlines():
        if "  " in zeile:
            summe, _, name = zeile.partition("  ")
            ergebnis[name[2:] if name.startswith("./") else name] = summe.strip()
    return ergebnis


class LinuxKernTests(_Abbild):
    """Der exFAT-Treiber des Linux-Kerns als unabhaengiger Zeuge (nur wo WSL mit Ubuntu-26.04 da ist)."""

    def setUp(self) -> None:
        super().setUp()
        self.bauen(self.dateien())
        if _wsl_pruefen(self.pfad, self.tmp) is None:
            self.skipTest("Kein WSL (Ubuntu-26.04) zum Einhaengen")

    def _vergleichen(self, erwartet: "dict[str, bytes]") -> None:
        kern = _wsl_pruefen(self.pfad, self.tmp)
        self.assertIsNotNone(kern, "Der Linux-Kern kann das geaenderte Abbild nicht einhaengen")
        soll = {r: hashlib.sha256(v).hexdigest() for r, v in erwartet.items() if v}
        soll.update({r: hashlib.sha256(b"").hexdigest() for r, v in erwartet.items() if not v})
        self.assertEqual(soll, kern)

    def test_alle_aenderungen_zusammen(self) -> None:
        erwartet = dict(self.erwartet)
        with eb.ExfatAbbild(self.pfad) as a:
            a.umbenennen("data/mittel.pak", "ein_langer_neuer_name_fuer_die_datei.pak")
            erwartet["data/ein_langer_neuer_name_fuer_die_datei.pak"] = erwartet.pop("data/mittel.pak")
            a.umbenennen("Media", "Medien")
            erwartet["Medien/video.bin"] = erwartet.pop("Media/video.bin")
            a.loeschen("data/gross.bin")
            erwartet.pop("data/gross.bin")
            a.hinzufuegen("data/neu.bin", self.quelle("neu", 2 * CL + 5))        # 3 von 6 freien Clustern
            erwartet["data/neu.bin"] = _inh("neu", 2 * CL + 5)
            a.ersetzen("data/tief/klein.cfg", self.quelle("kl", CL + 9))
            erwartet["data/tief/klein.cfg"] = _inh("kl", CL + 9)
            a.ordner_anlegen("saves")
            a.hinzufuegen("saves/s1.sav", self.quelle("s1", 77))
            erwartet["saves/s1.sav"] = _inh("s1", 77)
            a.speichern()
        self._vergleichen(erwartet)
        self.pruefen()

    def test_nach_einem_zurueckgespielten_abbruch_ist_alles_wie_vorher(self) -> None:
        a = eb.ExfatAbbild(self.pfad)
        a.loeschen("data/gross.bin")
        a.hinzufuegen("x.bin", self.quelle("x", CL))

        def kaputt(_fh) -> None:
            raise OSError("Platte voll")
        a._plan.daten.append(kaputt)
        with self.assertRaises(OSError):
            a.speichern()
        a.schliessen()
        self._vergleichen(self.erwartet)


if __name__ == "__main__":
    unittest.main()
