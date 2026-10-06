# -*- coding: utf-8 -*-
"""Tests fuer ``ps5_validator.utils.ps4pkg_aufgaben`` - die Aufgabenliste und ihre Arbeiten.

Drei Teile: die **Warteschlange** (Reihenfolge, Zustaende, Abbruch), die
**Arbeiten** mit untergeschobenem Werkzeug, und - wenn OrbisPkgTool
mitgeliefert ist - dieselben Arbeiten **Ende zu Ende** an echten
Minipaketen (Basis und Patch werden mit dem Werkzeug selbst gebaut).
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import orbispkg, ps4pkg_aufgaben as au, ps4pkg_ota, ps4pkg_updates   # noqa: E402
from ps5_validator.utils.ps4pkg_bibliothek import (PkgEintrag, TYP_BASIS, TYP_UPDATE, TYP_ZUSATZ,  # noqa: E402
                                                    lese_paket)


def t(schluessel: str, **werte) -> str:
    """Ein Uebersetzer, der den Schluessel samt Werten zeigt - so sieht der Test, was gemeldet wurde."""
    return schluessel + ("" if not werte else " " + ",".join("%s=%s" % (k, werte[k]) for k in sorted(werte)))


def _bis(bedingung, grenze: float = 10.0) -> bool:
    ende = time.monotonic() + grenze
    while time.monotonic() < ende:
        if bedingung():
            return True
        time.sleep(0.01)
    return False


class WarteschlangeTests(unittest.TestCase):

    def setUp(self) -> None:
        self.aenderungen = []
        self.schlange = au.Warteschlange(bei_aenderung=lambda: self.aenderungen.append(1))

    def tearDown(self) -> None:
        self.schlange.alle_abbrechen()
        _bis(lambda: not self.schlange.beschaeftigt, 5)

    def _warte_auf_ende(self) -> None:
        self.assertTrue(_bis(lambda: self.schlange.offen == 0), "Die Warteschlange wurde nicht fertig.")

    def test_aufgaben_laufen_nacheinander(self) -> None:
        reihenfolge: list[str] = []
        gleichzeitig = [0, 0]

        def arbeit(name: str):
            def _a(aufgabe: au.Aufgabe) -> None:
                gleichzeitig[0] += 1
                gleichzeitig[1] = max(gleichzeitig[1], gleichzeitig[0])
                reihenfolge.append(name)
                time.sleep(0.05)
                gleichzeitig[0] -= 1
            return _a

        for name in ("eins", "zwei", "drei"):
            self.schlange.hinzufuegen("test", name, arbeit(name))
        self._warte_auf_ende()
        self.assertEqual(["eins", "zwei", "drei"], reihenfolge)
        self.assertEqual(1, gleichzeitig[1], "Es liefen zwei Aufgaben zugleich.")
        self.assertEqual([au.FERTIG] * 3, [a.status for a in self.schlange.schnappschuss()])
        self.assertEqual([100.0] * 3, [a.prozent for a in self.schlange.schnappschuss()])

    def test_der_fenstertakt_bekommt_jede_aenderung_gemeldet(self) -> None:
        self.schlange.hinzufuegen("test", "x", lambda a: None)
        self._warte_auf_ende()
        self.assertGreaterEqual(len(self.aenderungen), 3, "neu, laeuft, fertig")

    def test_ein_fehler_stoppt_die_naechste_nicht(self) -> None:
        def kaputt(a: au.Aufgabe) -> None:
            raise au.AufgabeFehler("werkzeug", "Klartext", grund="x")

        def wirft(a: au.Aufgabe) -> None:
            raise RuntimeError("boese")

        erste = self.schlange.hinzufuegen("test", "kaputt", kaputt)
        zweite = self.schlange.hinzufuegen("test", "wirft", wirft)
        dritte = self.schlange.hinzufuegen("test", "gut", lambda a: None)
        self._warte_auf_ende()
        stand = {a.kennung: a for a in self.schlange.schnappschuss()}
        self.assertEqual(au.FEHLER, stand[erste.kennung].status)
        self.assertEqual("Klartext", stand[erste.kennung].fehler)
        self.assertEqual(au.FEHLER, stand[zweite.kennung].status)
        self.assertIn("RuntimeError: boese", stand[zweite.kennung].fehler)
        self.assertEqual(au.FERTIG, stand[dritte.kennung].status)

    def test_orbisfehler_ist_ein_fehler_der_aufgabe(self) -> None:
        def a(aufgabe: au.Aufgabe) -> None:
            raise orbispkg.OrbisFehler("Werkzeug fehlt")

        aufgabe = self.schlange.hinzufuegen("test", "x", a)
        self._warte_auf_ende()
        self.assertEqual(au.FEHLER, self.schlange.aufgabe(aufgabe.kennung).status)

    def test_eine_wartende_aufgabe_laesst_sich_streichen(self) -> None:
        sperre = threading.Event()
        self.schlange.hinzufuegen("test", "haelt", lambda a: sperre.wait(5))
        wartend = self.schlange.hinzufuegen("test", "wartet", lambda a: self.fail("darf nicht laufen"))
        self.assertTrue(self.schlange.abbrechen(wartend.kennung))
        sperre.set()
        self._warte_auf_ende()
        self.assertEqual(au.ABGEBROCHEN, self.schlange.aufgabe(wartend.kennung).status)

    def test_eine_laufende_aufgabe_sieht_den_abbruch(self) -> None:
        gestartet = threading.Event()

        def langsam(a: au.Aufgabe) -> None:
            gestartet.set()
            for _ in range(500):
                a.pruefen_abbruch()
                time.sleep(0.01)

        aufgabe = self.schlange.hinzufuegen("test", "langsam", langsam)
        self.assertTrue(gestartet.wait(5))
        self.schlange.abbrechen(aufgabe.kennung)
        self._warte_auf_ende()
        self.assertEqual(au.ABGEBROCHEN, self.schlange.aufgabe(aufgabe.kennung).status)

    def test_abbrechen_beendet_auch_den_prozess_in_der_ablage(self) -> None:
        gestartet = threading.Event()
        beendet: list[bool] = []

        class Prozess:
            def terminate(self) -> None:
                beendet.append(True)

        def a(aufgabe: au.Aufgabe) -> None:
            aufgabe.prozess_ablage["prozess"] = Prozess()
            gestartet.set()
            _bis(lambda: aufgabe.abbruch_verlangt, 5)
            aufgabe.pruefen_abbruch()

        aufgabe = self.schlange.hinzufuegen("test", "x", a)
        self.assertTrue(gestartet.wait(5))
        self.schlange.abbrechen(aufgabe.kennung)
        self._warte_auf_ende()
        self.assertEqual([True], beendet)

    def test_beendete_aufgaben_lassen_sich_nicht_mehr_abbrechen(self) -> None:
        aufgabe = self.schlange.hinzufuegen("test", "x", lambda a: None)
        self._warte_auf_ende()
        self.assertFalse(self.schlange.abbrechen(aufgabe.kennung))
        self.assertFalse(self.schlange.abbrechen(99999))

    def test_entfernen_und_leeren(self) -> None:
        sperre = threading.Event()
        laufend = self.schlange.hinzufuegen("test", "haelt", lambda a: sperre.wait(5))
        self.assertTrue(_bis(lambda: self.schlange.aufgabe(laufend.kennung).status == au.LAEUFT))
        self.assertFalse(self.schlange.entfernen(laufend.kennung), "Eine laufende Aufgabe bleibt in der Liste.")
        fertig = self.schlange.hinzufuegen("test", "fertig", lambda a: None)
        sperre.set()
        self._warte_auf_ende()
        self.assertTrue(self.schlange.entfernen(fertig.kennung))
        self.assertEqual(1, self.schlange.erledigte_leeren())
        self.assertEqual([], self.schlange.schnappschuss())

    def test_wiederholen_stellt_hinten_an(self) -> None:
        zaehler = [0]

        def a(aufgabe: au.Aufgabe) -> None:
            zaehler[0] += 1
            if zaehler[0] == 1:
                raise au.AufgabeFehler("werkzeug", "erster Versuch")

        erste = self.schlange.hinzufuegen("test", "x", a, quelle="q", ziel="z")
        self._warte_auf_ende()
        neu = self.schlange.wiederholen(erste.kennung)
        self.assertIsNotNone(neu)
        self.assertNotEqual(erste.kennung, neu.kennung)
        self._warte_auf_ende()
        self.assertEqual(au.FERTIG, self.schlange.aufgabe(neu.kennung).status)
        self.assertEqual(("q", "z"), (neu.quelle, neu.ziel))
        gut = self.schlange.hinzufuegen("test", "gut", lambda a: None)
        self._warte_auf_ende()
        self.assertIsNone(self.schlange.wiederholen(gut.kennung), "Nur Gescheitertes wird wiederholt.")

    def test_ohne_automatik_startet_nur_auf_zuruf(self) -> None:
        schlange = au.Warteschlange(automatisch=False)
        gelaufen: list[str] = []
        schlange.hinzufuegen("test", "a", lambda a: gelaufen.append("a"))
        schlange.hinzufuegen("test", "b", lambda a: gelaufen.append("b"))
        time.sleep(0.2)
        self.assertEqual([], gelaufen)
        schlange.naechste_starten()
        self.assertTrue(_bis(lambda: gelaufen == ["a"]))
        time.sleep(0.2)
        self.assertEqual(["a"], gelaufen, "Es soll immer nur eine auf Zuruf laufen.")
        schlange.naechste_starten()
        self.assertTrue(_bis(lambda: gelaufen == ["a", "b"]))

    def test_aufgaben_waehrend_des_laufs_werden_mitgenommen(self) -> None:
        sperre = threading.Event()
        gelaufen: list[str] = []
        self.schlange.hinzufuegen("test", "a", lambda a: (sperre.wait(5), gelaufen.append("a")))
        self.assertTrue(_bis(lambda: self.schlange.beschaeftigt))
        self.schlange.hinzufuegen("test", "b", lambda a: gelaufen.append("b"))
        sperre.set()
        self._warte_auf_ende()
        self.assertEqual(["a", "b"], gelaufen)

    def test_der_schnappschuss_ist_eine_kopie(self) -> None:
        aufgabe = self.schlange.hinzufuegen("test", "x", lambda a: a.melden("Text", 40))
        self._warte_auf_ende()
        kopie = self.schlange.schnappschuss()[0]
        kopie.text = "veraendert"
        self.assertEqual("Text", self.schlange.aufgabe(aufgabe.kennung).text)

    def test_das_protokoll_der_aufgabe_ist_begrenzt(self) -> None:
        def a(aufgabe: au.Aufgabe) -> None:
            for i in range(2000):
                aufgabe.schreiben("zeile %d" % i)

        aufgabe = self.schlange.hinzufuegen("test", "x", a)
        self._warte_auf_ende()
        protokoll = self.schlange.aufgabe(aufgabe.kennung).protokoll
        self.assertEqual(500, len(protokoll))
        self.assertEqual("zeile 1999", protokoll[-1])

    def test_prozent_wird_begrenzt(self) -> None:
        a = au.Aufgabe(kennung=1, art="x", titel="x")
        a.melden("t", 250)
        self.assertEqual(100.0, a.prozent)
        a.melden("t", -5)
        self.assertEqual(0.0, a.prozent)
        a.melden("nur Text")
        self.assertEqual(0.0, a.prozent)


class HilfenTests(unittest.TestCase):

    def test_zielordnernamen(self) -> None:
        basis = PkgEintrag(pfad="/x/a.pkg", title_id="CUSA00775", typ=TYP_BASIS)
        patch = PkgEintrag(pfad="/x/b.pkg", title_id="CUSA16627", typ=TYP_UPDATE, app_ver="01.02")
        dlc = PkgEintrag(pfad="/x/c.pkg", title_id="CUSA16627", typ=TYP_ZUSATZ,
                         content_id="UP0000-CUSA16627_00-DLCPACK000000001")
        self.assertEqual("CUSA00775", au.zielordner_name(basis))
        self.assertEqual("CUSA16627_patch_01.02", au.zielordner_name(patch))
        self.assertEqual("CUSA16627_dlc_DLCPACK000000001", au.zielordner_name(dlc))

    def test_zielordnername_ohne_title_id_nimmt_den_dateinamen(self) -> None:
        e = PkgEintrag(pfad="/x/Mein Spiel.pkg")
        self.assertEqual("Mein Spiel", au.zielordner_name(e))

    def test_freier_platz_auch_fuer_fehlende_ordner(self) -> None:
        with tempfile.TemporaryDirectory() as wo:
            self.assertGreater(au.freier_platz(os.path.join(wo, "gibt", "es", "nicht")), 0)

    def test_lange_pfade_bekommen_unter_windows_das_praefix(self) -> None:
        kurz = os.path.join(tempfile.gettempdir(), "x")
        self.assertEqual(kurz, au._lang(kurz) if sys.platform != "win32" else au._lang(kurz))
        if sys.platform == "win32":
            lang = "C:\\" + "\\".join(["abcdefghij" * 3] * 10)
            self.assertTrue(au._lang(lang).startswith("\\\\?\\C:\\"))
            self.assertEqual("\\\\?\\UNC\\server\\share\\" + "x" * 250,
                             au._lang("\\\\server\\share\\" + "x" * 250))


class DumpOrdnerTests(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.wo = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _roh(self, image0: dict, sc0: dict) -> Path:
        roh = self.wo / "roh"
        for wurzel, dateien in (("Image0", image0), ("Sc0", sc0)):
            for rel, inhalt in dateien.items():
                pfad = roh / wurzel / rel
                pfad.parent.mkdir(parents=True, exist_ok=True)
                pfad.write_bytes(inhalt)
        return roh

    def test_spieldateien_nach_oben_systemdateien_nach_sce_sys(self) -> None:
        roh = self._roh({"eboot.bin": b"E", "data/a.bin": b"A", "sce_module/libc.prx": b"L"},
                        {"param.sfo": b"S", "trophy/trophy00.trp": b"T", "icon0.png": b"I"})
        erg = au.dump_ordner_machen(str(roh))
        self.assertEqual({"dateien": 3, "systemdateien": 3}, erg)
        self.assertEqual(b"E", (roh / "eboot.bin").read_bytes())
        self.assertEqual(b"A", (roh / "data" / "a.bin").read_bytes())
        self.assertEqual(b"S", (roh / "sce_sys" / "param.sfo").read_bytes())
        self.assertEqual(b"T", (roh / "sce_sys" / "trophy" / "trophy00.trp").read_bytes())
        self.assertFalse((roh / "Image0").exists())
        self.assertFalse((roh / "Sc0").exists())

    def test_ein_vorhandenes_sce_sys_im_spiel_wird_verschmolzen(self) -> None:
        roh = self._roh({"sce_sys/about/right.sprx": b"R", "sce_sys/param.sfo": b"ALT", "eboot.bin": b"E"},
                        {"param.sfo": b"NEU", "icon0.png": b"I"})
        au.dump_ordner_machen(str(roh))
        self.assertEqual(b"R", (roh / "sce_sys" / "about" / "right.sprx").read_bytes())
        self.assertEqual(b"NEU", (roh / "sce_sys" / "param.sfo").read_bytes(), "Sc0 gewinnt.")
        self.assertEqual(b"I", (roh / "sce_sys" / "icon0.png").read_bytes())

    def test_ohne_sc0_geht_es_auch(self) -> None:
        roh = self._roh({"eboot.bin": b"E"}, {})
        self.assertEqual({"dateien": 1, "systemdateien": 0}, au.dump_ordner_machen(str(roh)))

    def test_ohne_image0_ist_es_ein_fehler(self) -> None:
        roh = self._roh({}, {"param.sfo": b"S"})
        with self.assertRaises(au.AufgabeFehler) as ctx:
            au.dump_ordner_machen(str(roh))
        self.assertEqual("ohne_image0", ctx.exception.schluessel)

    def test_ordner_mit_gleichem_namen_werden_zusammengelegt(self) -> None:
        roh = self._roh({"data/a.bin": b"A", "data/tief/x.bin": b"X"}, {})
        (roh / "data").mkdir(exist_ok=True)
        (roh / "data" / "schon_da.bin").write_bytes(b"D")
        au.dump_ordner_machen(str(roh))
        self.assertEqual({"a.bin", "tief", "schon_da.bin"}, {p.name for p in (roh / "data").iterdir()})

    def test_viele_dateien(self) -> None:
        image0 = {"d%02d/f%03d.bin" % (i % 7, i): b"x" for i in range(300)}
        roh = self._roh(image0, {"param.sfo": b"S"})
        erg = au.dump_ordner_machen(str(roh))
        self.assertEqual(300, erg["dateien"])
        self.assertEqual(300, sum(1 for p in roh.rglob("f*.bin")))

    def test_das_ordnen_meldet_sich_nach_je_einigen_dateien(self) -> None:
        """Ein Spiel hat Zehntausende Dateien - das Umordnen darf nicht still sein."""
        image0 = {"d%02d/f%03d.bin" % (i % 7, i): b"x" for i in range(300)}
        roh = self._roh(image0, {"param.sfo": b"S"})
        meldungen: list[int] = []
        # Sieben Ordner zu je rund 43 Dateien wechseln als Ganzes den Platz: Gezaehlt wird je Ordner, also
        # kommt bei einem Schritt von 50 die Meldung nach dem 2., 4. und 6. Ordner (86, 172, 258 Dateien).
        with mock.patch.object(au, "ORDNEN_SCHRITT", 50):
            erg = au.dump_ordner_machen(str(roh), meldungen.append)
        self.assertEqual(300, erg["dateien"])
        self.assertEqual(3, len(meldungen))
        self.assertEqual(sorted(meldungen), meldungen)
        self.assertLessEqual(max(meldungen), 301, "Gezaehlt werden Dateien, nicht Ordner.")

    def test_die_zahl_stimmt_auch_mit_meldungen(self) -> None:
        roh = self._roh({"a.bin": b"1", "x/b.bin": b"2", "x/y/c.bin": b"3"}, {})
        (roh / "x").mkdir(exist_ok=True)                 # zwingt zum Zusammenlegen statt Verschieben
        self.assertEqual(3, au._verschmelzen(str(roh / "Image0"), str(roh), lambda n: None))

    def test_aufraeumen_sagt_nur_bescheid_wenn_es_etwas_zu_loeschen_gibt(self) -> None:
        sagt = []
        (self.wo / "arbeit").mkdir()
        (self.wo / "arbeit" / "datei").write_bytes(b"x")
        au._aufraeumen(str(self.wo / "arbeit"), lambda: sagt.append(1))
        self.assertEqual([1], sagt)
        self.assertFalse((self.wo / "arbeit").exists())
        au._aufraeumen(str(self.wo / "gibt_es_nicht"), lambda: sagt.append(2))
        self.assertEqual([1], sagt, "Ein fehlender Ordner braucht keine Meldung.")
        au._aufraeumen(str(self.wo / "gibt_es_nicht"))            # ohne Rueckruf geht es auch

    def test_der_aufraeumer_schreibt_in_den_status_der_aufgabe(self) -> None:
        a = au.Aufgabe(kennung=1, art="entpacken", titel="t")
        (self.wo / "arbeit").mkdir()
        au._aufraeumer(a, lambda schluessel, **w: "Text:" + schluessel)(str(self.wo / "arbeit"))
        self.assertEqual("Text:ps4ota.status_raeume_auf", a.text)
        self.assertFalse((self.wo / "arbeit").exists())


class _FalschesWerkzeug:
    """Tauscht ``orbispkg`` gegen Antworten, die der Test bestimmt."""

    def __init__(self, testfall: unittest.TestCase) -> None:
        self.aufrufe: list[tuple[str, tuple, dict]] = []
        self.liste_antwort: "list | Exception" = [orbispkg.ListenEintrag(False, 100, "Image0/eboot.bin")]
        self.entpacken_fn = None
        self.zusammenfuehren_fn = None
        for name in ("liste", "entpacken", "zusammenfuehren", "neu_packen", "pruefen", "tiefenpruefung",
                     "projekt_erzeugen", "bauen"):
            p = mock.patch.object(orbispkg, name, side_effect=self._nachbau(name))
            p.start()
            testfall.addCleanup(p.stop)

    def _nachbau(self, name: str):
        def _f(*args, **kwargs):
            self.aufrufe.append((name, args, kwargs))
            fn = getattr(self, name + "_fn", None)
            if fn is not None:
                return fn(*args, **kwargs)
            if name == "liste":
                if isinstance(self.liste_antwort, Exception):
                    raise self.liste_antwort
                return self.liste_antwort
            raise AssertionError("nicht vorbereitet: " + name)
        return _f


class ArbeitEntpackenTests(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.wo = Path(self._tmp.name)
        self.pkg = self.wo / "spiel.pkg"
        self.pkg.write_bytes(b"x" * 1000)
        self.falsch = _FalschesWerkzeug(self)
        self.a = au.Aufgabe(kennung=1, art="entpacken", titel="x")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _entpacken_baut(self, mit_image0: bool = True, ok: bool = True, abgebrochen: bool = False):
        def fn(paket, ziel, **kw):
            os.makedirs(ziel, exist_ok=True)
            if mit_image0:
                Path(ziel, "Image0").mkdir()
                Path(ziel, "Image0", "eboot.bin").write_bytes(b"E")
                Path(ziel, "Sc0").mkdir()
                Path(ziel, "Sc0", "param.sfo").write_bytes(b"S")
            kw["fortschritt"](1, 2, "Image0/eboot.bin")
            return orbispkg.EntpackErgebnis(ok=ok, dateien_ok=2, dateien_gesamt=2, abgebrochen=abgebrochen,
                                            meldung="" if ok else "Werkzeug sagt nein")
        self.falsch.entpacken_fn = fn

    def test_erfolg_dump_form(self) -> None:
        self._entpacken_baut()
        ziel = self.wo / "aus" / "CUSA00001"
        au.arbeit_entpacken(self.a, str(self.pkg), str(ziel), t)
        self.assertEqual(b"E", (ziel / "eboot.bin").read_bytes())
        self.assertEqual(b"S", (ziel / "sce_sys" / "param.sfo").read_bytes())
        self.assertFalse(Path(str(ziel) + ".partial").exists())
        self.assertEqual(str(ziel), self.a.ergebnis)
        self.assertEqual(100.0, self.a.prozent)

    def test_erfolg_rohform_behaelt_image0_und_sc0(self) -> None:
        self._entpacken_baut()
        ziel = self.wo / "roh"
        au.arbeit_entpacken(self.a, str(self.pkg), str(ziel), t, dump_form=False)
        self.assertTrue((ziel / "Image0" / "eboot.bin").is_file())
        self.assertTrue((ziel / "Sc0" / "param.sfo").is_file())

    def test_das_ziel_darf_nicht_bestehen(self) -> None:
        ziel = self.wo / "da"
        ziel.mkdir()
        with self.assertRaises(au.AufgabeFehler) as ctx:
            au.arbeit_entpacken(self.a, str(self.pkg), str(ziel), t)
        self.assertEqual("ziel_existiert", ctx.exception.schluessel)
        self.assertEqual([], self.falsch.aufrufe, "Es wurde schon etwas gestartet.")

    def test_ein_teilstand_wird_vorher_weggeraeumt(self) -> None:
        self._entpacken_baut()
        ziel = self.wo / "z"
        teil = Path(str(ziel) + ".partial")
        teil.mkdir()
        (teil / "alt.bin").write_bytes(b"alt")
        au.arbeit_entpacken(self.a, str(self.pkg), str(ziel), t)
        self.assertFalse((ziel / "alt.bin").exists())

    def test_zu_wenig_platz(self) -> None:
        self.falsch.liste_antwort = [orbispkg.ListenEintrag(False, 10 ** 15, "Image0/riesig.bin")]
        with self.assertRaises(au.AufgabeFehler) as ctx:
            au.arbeit_entpacken(self.a, str(self.pkg), str(self.wo / "z"), t)
        self.assertEqual("kein_platz", ctx.exception.schluessel)
        self.assertEqual(10 ** 15, ctx.exception.werte["noetig"])

    def test_ein_unlesbares_paket(self) -> None:
        self.falsch.liste_antwort = orbispkg.OrbisFehler("Not a PKG")
        with self.assertRaises(au.AufgabeFehler) as ctx:
            au.arbeit_entpacken(self.a, str(self.pkg), str(self.wo / "z"), t)
        self.assertEqual("paket_unlesbar", ctx.exception.schluessel)

    def test_ein_werkzeugfehler_raeumt_auf(self) -> None:
        self._entpacken_baut(ok=False)
        ziel = self.wo / "z"
        with self.assertRaises(au.AufgabeFehler) as ctx:
            au.arbeit_entpacken(self.a, str(self.pkg), str(ziel), t)
        self.assertEqual("werkzeug", ctx.exception.schluessel)
        self.assertFalse(ziel.exists())
        self.assertFalse(Path(str(ziel) + ".partial").exists())

    def test_abbruch_raeumt_auf(self) -> None:
        self._entpacken_baut(abgebrochen=True, ok=False)
        ziel = self.wo / "z"
        with self.assertRaises(au.AufgabeAbgebrochen):
            au.arbeit_entpacken(self.a, str(self.pkg), str(ziel), t)
        self.assertFalse(Path(str(ziel) + ".partial").exists())

    def test_ohne_image0_kein_ergebnis(self) -> None:
        self._entpacken_baut(mit_image0=False)
        ziel = self.wo / "z"
        with self.assertRaises(au.AufgabeFehler) as ctx:
            au.arbeit_entpacken(self.a, str(self.pkg), str(ziel), t)
        self.assertEqual("ohne_image0", ctx.exception.schluessel)
        self.assertFalse(ziel.exists())
        self.assertFalse(Path(str(ziel) + ".partial").exists())

    def test_der_fortschritt_wird_gemeldet(self) -> None:
        self._entpacken_baut()
        au.arbeit_entpacken(self.a, str(self.pkg), str(self.wo / "z"), t)
        self.assertTrue(any("status_entpacke" in z for z in [self.a.text] + self.a.protokoll)
                        or self.a.text.startswith("ps4ota.status_entpackt"))


class ArbeitenMitFalschemWerkzeugTests(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.wo = Path(self._tmp.name)
        self.basis = self.wo / "basis.pkg"
        self.update = self.wo / "update.pkg"
        self.basis.write_bytes(b"b" * 2000)
        self.update.write_bytes(b"u" * 500)
        self.falsch = _FalschesWerkzeug(self)
        self.a = au.Aufgabe(kennung=7, art="x", titel="x")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_zusammenfuehren_nutzt_einen_eigenen_arbeitsordner_und_raeumt_ihn_weg(self) -> None:
        ausgabe = self.wo / "aus" / "m.pkg"
        arbeitsorte: list[str] = []

        def fn(basis, update, aus, **kw):
            arbeitsorte.append(kw["arbeitsordner"])
            os.makedirs(kw["arbeitsordner"])
            Path(kw["arbeitsordner"], "zwischen.bin").write_bytes(b"z")
            Path(aus).write_bytes(b"fertig")
            kw["fortschritt"]("Building", 50)
            return orbispkg.BauErgebnis(ok=True, ausgabe=aus)

        self.falsch.zusammenfuehren_fn = fn
        fremd = self.wo / "meine_arbeit"
        fremd.mkdir()
        (fremd / "wichtig.txt").write_text("bleibt")
        au.arbeit_zusammenfuehren(self.a, str(self.basis), str(self.update), str(ausgabe), t,
                                  arbeitsordner=str(fremd))
        self.assertEqual(str(fremd / ".ps4ota_arbeit_7"), arbeitsorte[0])
        self.assertFalse((fremd / ".ps4ota_arbeit_7").exists(), "Der Unterordner wird weggeraeumt.")
        self.assertTrue((fremd / "wichtig.txt").is_file(), "Der Ordner des Anwenders bleibt unberuehrt.")
        self.assertEqual(str(ausgabe), self.a.ergebnis)

    def test_zusammenfuehren_ohne_platz(self) -> None:
        with mock.patch.object(au, "freier_platz", return_value=100):
            with self.assertRaises(au.AufgabeFehler) as ctx:
                au.arbeit_zusammenfuehren(self.a, str(self.basis), str(self.update), str(self.wo / "m.pkg"), t)
        self.assertEqual("kein_platz", ctx.exception.schluessel)
        self.assertEqual([], self.falsch.aufrufe)

    def test_zusammenfuehren_fehler_loescht_nichts_vom_anwender_und_raeumt_den_arbeitsordner(self) -> None:
        def fn(basis, update, aus, **kw):
            os.makedirs(kw["arbeitsordner"])
            return orbispkg.BauErgebnis(ok=False, meldung="Update PKG must be a Patch PKG")

        self.falsch.zusammenfuehren_fn = fn
        with self.assertRaises(au.AufgabeFehler) as ctx:
            au.arbeit_zusammenfuehren(self.a, str(self.basis), str(self.update), str(self.wo / "m.pkg"), t)
        self.assertEqual("werkzeug", ctx.exception.schluessel)
        self.assertIn("Patch", ctx.exception.text)
        self.assertEqual([], [p for p in self.wo.iterdir() if p.name.startswith(".ps4ota")])
        self.assertTrue(self.basis.is_file() and self.update.is_file())

    def test_zusammenfuehren_abbruch_entfernt_die_halbe_ausgabe(self) -> None:
        ausgabe = self.wo / "m.pkg"

        def fn(basis, update, aus, **kw):
            Path(aus).write_bytes(b"halb")
            return orbispkg.BauErgebnis(ok=False, abgebrochen=True)

        self.falsch.zusammenfuehren_fn = fn
        with self.assertRaises(au.AufgabeAbgebrochen):
            au.arbeit_zusammenfuehren(self.a, str(self.basis), str(self.update), str(ausgabe), t)
        self.assertFalse(ausgabe.exists())

    def test_ziel_darf_nicht_bestehen_fuer_alle_baeuer(self) -> None:
        da = self.wo / "da.pkg"
        da.write_bytes(b"x")
        for aufruf in (
            lambda: au.arbeit_zusammenfuehren(self.a, str(self.basis), str(self.update), str(da), t),
            lambda: au.arbeit_neu_packen(self.a, str(self.basis), str(da), t),
            lambda: au.arbeit_bauen(self.a, str(self.wo), str(da), t),
        ):
            with self.assertRaises(au.AufgabeFehler) as ctx:
                aufruf()
            self.assertEqual("ziel_existiert", ctx.exception.schluessel)
        self.assertEqual(b"x", da.read_bytes())

    def test_neu_packen(self) -> None:
        ausgabe = self.wo / "neu.pkg"

        def fn(paket, aus, **kw):
            Path(aus).write_bytes(b"neu")
            return orbispkg.BauErgebnis(ok=True, ausgabe=aus)

        self.falsch.neu_packen_fn = fn
        au.arbeit_neu_packen(self.a, str(self.basis), str(ausgabe), t, pruefen_danach=True, arbeiter=4)
        name, args, kw = self.falsch.aufrufe[-1]
        self.assertEqual("neu_packen", name)
        self.assertTrue(kw["pruefen_danach"])
        self.assertEqual(4, kw["arbeiter"])
        self.assertEqual(str(ausgabe), self.a.ergebnis)

    def test_pruefen_einfach_und_tief(self) -> None:
        self.falsch.pruefen_fn = lambda paket, **kw: (True, "Integrity OK : all 20 entries verified")
        self.falsch.tiefenpruefung_fn = lambda paket, **kw: orbispkg.Pruefergebnis(True, "", ["[1/8] x"])
        au.arbeit_pruefen(self.a, str(self.basis), t)
        self.assertEqual(["pruefen"], [n for n, _, _ in self.falsch.aufrufe])
        au.arbeit_pruefen(self.a, str(self.basis), t, tief=True)
        self.assertIn("tiefenpruefung", [n for n, _, _ in self.falsch.aufrufe])
        self.assertIn("[1/8] x", self.a.protokoll)

    def test_pruefen_fehlschlag(self) -> None:
        self.falsch.pruefen_fn = lambda paket, **kw: (False, "Integrity FAILED : 2 mismatch(es)")
        with self.assertRaises(au.AufgabeFehler) as ctx:
            au.arbeit_pruefen(self.a, str(self.basis), t)
        self.assertEqual("pruefung", ctx.exception.schluessel)

    def test_tiefpruefung_fehlschlag_traegt_den_hinweis(self) -> None:
        self.falsch.pruefen_fn = lambda paket, **kw: (True, "Integrity OK")
        self.falsch.tiefenpruefung_fn = lambda paket, **kw: orbispkg.Pruefergebnis(False, "PFSC kaputt", ["[3/8]"])
        with self.assertRaises(au.AufgabeFehler) as ctx:
            au.arbeit_pruefen(self.a, str(self.basis), t, tief=True)
        self.assertEqual("tiefpruefung", ctx.exception.schluessel)
        self.assertIn("ps4ota.log_tiefpruefung_hinweis", self.a.protokoll)

    def test_bauen_braucht_param_sfo(self) -> None:
        ordner = self.wo / "dump"
        ordner.mkdir()
        (ordner / "eboot.bin").write_bytes(b"E")
        with self.assertRaises(au.AufgabeFehler) as ctx:
            au.arbeit_bauen(self.a, str(ordner), str(self.wo / "x.pkg"), t)
        self.assertEqual("ohne_param_sfo", ctx.exception.schluessel)

    def test_bauen_erzeugt_gp4_dann_baut_und_raeumt_den_arbeitsordner(self) -> None:
        ordner = self.wo / "dump"
        (ordner / "sce_sys").mkdir(parents=True)
        (ordner / "sce_sys" / "param.sfo").write_bytes(b"S")
        ausgabe = self.wo / "x.pkg"

        def projekt(ordner_, gp4, **kw):
            Path(gp4).write_text("<gp4/>")
            return orbispkg.LaufErgebnis(0, [], [])

        def bauen(gp4, ordner_, aus, **kw):
            self.assertTrue(os.path.isfile(gp4))
            Path(aus).write_bytes(b"pkg")
            return orbispkg.BauErgebnis(ok=True, ausgabe=aus)

        self.falsch.projekt_erzeugen_fn = projekt
        self.falsch.bauen_fn = bauen
        au.arbeit_bauen(self.a, str(ordner), str(ausgabe), t, patch=True)
        self.assertEqual(["projekt_erzeugen", "bauen"], [n for n, _, _ in self.falsch.aufrufe])
        self.assertTrue(self.falsch.aufrufe[0][2]["patch"])
        self.assertEqual([], [p for p in self.wo.iterdir() if p.name.startswith(".ps4ota")])
        self.assertTrue(ausgabe.is_file())

    def test_ein_gescheiterter_bau_laesst_keine_halbe_datei(self) -> None:
        ordner = self.wo / "dump"
        (ordner / "sce_sys").mkdir(parents=True)
        (ordner / "sce_sys" / "param.sfo").write_bytes(b"S")
        ausgabe = self.wo / "x.pkg"
        self.falsch.projekt_erzeugen_fn = lambda o, g, **kw: (Path(g).write_text("<gp4/>"), orbispkg.LaufErgebnis(0, [], []))[1]

        def bauen(gp4, ordner_, aus, **kw):
            Path(aus).write_bytes(b"halb")
            return orbispkg.BauErgebnis(ok=False, meldung="kaputt")

        self.falsch.bauen_fn = bauen
        with self.assertRaises(au.AufgabeFehler):
            au.arbeit_bauen(self.a, str(ordner), str(ausgabe), t)
        self.assertFalse(ausgabe.exists())


class ArbeitenNetzTests(unittest.TestCase):

    def setUp(self) -> None:
        self.a = au.Aufgabe(kennung=3, art="x", titel="x")

    def test_update_laden(self) -> None:
        info = ps4pkg_updates.UpdateInfo(title_id="CUSA00775", version="01.09")

        def laden(info_, ordner, *, fortschritt, abbruch):
            fortschritt(50, 100)
            return os.path.join(ordner, "CUSA00775-patch-v01.09.pkg")

        with mock.patch.object(ps4pkg_updates, "herunterladen", side_effect=laden):
            au.arbeit_update_laden(self.a, info, "/zielordner", t)
        self.assertTrue(self.a.ergebnis.endswith("CUSA00775-patch-v01.09.pkg"))
        self.assertEqual(100.0, self.a.prozent)

    def test_update_laden_fehler_und_abbruch(self) -> None:
        info = ps4pkg_updates.UpdateInfo(title_id="CUSA00775", version="01.09")
        with mock.patch.object(ps4pkg_updates, "herunterladen",
                               side_effect=ps4pkg_updates.UpdateFehler("hash", "Teil 2")):
            with self.assertRaises(au.AufgabeFehler) as ctx:
                au.arbeit_update_laden(self.a, info, "/z", t)
        self.assertEqual("update_hash", ctx.exception.schluessel)
        with mock.patch.object(ps4pkg_updates, "herunterladen",
                               side_effect=ps4pkg_updates.UpdateFehler("abgebrochen")):
            with self.assertRaises(au.AufgabeAbgebrochen):
                au.arbeit_update_laden(self.a, info, "/z", t)

    def test_ota_dpi_ablauf(self) -> None:
        aufrufe: list[str] = []

        class Falscher:
            def __init__(self, ip, api_port, web_port=0, zeit=15.0):
                aufrufe.append("init %s:%s web=%s" % (ip, api_port, web_port))

            def hochladen(self, pfad, *, fortschritt=None, abbruch=None, **kw):
                aufrufe.append("hochladen " + pfad)
                fortschritt(50, 100)
                return {"ok": True}

            def warten(self, *, abbruch=None, zeitgrenze=0, bei_ping=None, **kw):
                aufrufe.append("warten")
                bei_ping({"busy": True})
                return {}

        with mock.patch.object(ps4pkg_ota, "DpiClient", Falscher):
            au.arbeit_ota_dpi(self.a, "C:/x/spiel.pkg", "10.0.0.5", 12800, t, web_port=12801)
        self.assertEqual(["init 10.0.0.5:12800 web=12801", "hochladen C:/x/spiel.pkg", "warten"], aufrufe)
        self.assertEqual("10.0.0.5", self.a.ergebnis)
        self.assertEqual(100.0, self.a.prozent)

    def test_ota_dpi_fehler_und_abbruch(self) -> None:
        class Wirft:
            def __init__(self, *a, **k):
                pass

            def hochladen(self, *a, **k):
                raise ps4pkg_ota.OtaFehler("netz", "keine Verbindung")

        with mock.patch.object(ps4pkg_ota, "DpiClient", Wirft):
            with self.assertRaises(au.AufgabeFehler) as ctx:
                au.arbeit_ota_dpi(self.a, "x.pkg", "10.0.0.5", 12800, t)
        self.assertEqual("ota_netz", ctx.exception.schluessel)

        class Bricht(Wirft):
            def hochladen(self, *a, **k):
                raise ps4pkg_ota.OtaAbgebrochen()

        with mock.patch.object(ps4pkg_ota, "DpiClient", Bricht):
            with self.assertRaises(au.AufgabeAbgebrochen):
                au.arbeit_ota_dpi(self.a, "x.pkg", "10.0.0.5", 12800, t)

    def test_ota_rpi_ablauf_und_fehler(self) -> None:
        gesehen: dict = {}

        def senden(ip, dateien, **kw):
            gesehen.update(ip=ip, dateien=dateien, **kw)
            kw["fortschritt"](ps4pkg_ota.RpiFortschritt(laenge=100, uebertragen=40, rest_sekunden=9), 40)
            return 1

        with mock.patch.object(ps4pkg_ota, "rpi_senden", side_effect=senden):
            au.arbeit_ota_rpi(self.a, ["a.pkg", "b.pkg"], "10.0.0.7", 12800, t, eigene_ip="10.0.0.1", server_port=8080)
        self.assertEqual(("10.0.0.7", ["a.pkg", "b.pkg"], "10.0.0.1", 8080),
                         (gesehen["ip"], gesehen["dateien"], gesehen["eigene_ip"], gesehen["server_port"]))
        self.assertEqual("10.0.0.7", self.a.ergebnis)
        with mock.patch.object(ps4pkg_ota, "rpi_senden",
                               side_effect=ps4pkg_ota.OtaFehler("konsole_fehler", "Fehlercode 0x1")):
            with self.assertRaises(au.AufgabeFehler) as ctx:
                au.arbeit_ota_rpi(self.a, ["a.pkg"], "10.0.0.7", 12800, t)
        self.assertEqual("ota_konsole_fehler", ctx.exception.schluessel)


@unittest.skipUnless(orbispkg.verfuegbar(), "OrbisPkgTool ist fuer diese Plattform nicht mitgeliefert.")
class EndeZuEndeTests(unittest.TestCase):
    """Mit dem echten Werkzeug: Minipakete bauen, entpacken, zusammenfuehren, neu packen, pruefen."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.wo = Path(cls._tmp.name)
        cls.basis = cls._paket("basis", "gd", "01.00",
                               {"eboot.bin": b"BASIS" * 400, "data/a.bin": b"A" * 5000, "data/b.bin": b"B" * 3000})
        cls.patch = cls._paket("patch", "gp", "01.05",
                               {"data/b.bin": b"NEU-B" * 700, "data/c.bin": b"C" * 2000})

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    @classmethod
    def _paket(cls, name: str, kategorie: str, app_ver: str, dateien: dict) -> Path:
        quelle = cls.wo / name / "Image0"
        (quelle / "sce_sys").mkdir(parents=True)
        sfo = str(quelle / "sce_sys" / "param.sfo")
        for args in (["sfo", "create", sfo, "--title", "Aufgabentest", "--title-id", "TEST00005",
                      "--content-id", "UP0000-TEST00005_00-0000000000000000"],
                     ["sfo", "set", sfo, "CATEGORY", kategorie],
                     ["sfo", "set", sfo, "APP_VER", app_ver]):
            assert orbispkg._laufen(args).rueckgabe == 0
        for rel, inhalt in dateien.items():
            pfad = quelle / rel
            pfad.parent.mkdir(parents=True, exist_ok=True)
            pfad.write_bytes(inhalt)
        gp4 = cls.wo / (name + ".gp4")
        assert orbispkg.projekt_erzeugen(str(quelle), str(gp4), patch=kategorie == "gp").rueckgabe == 0
        ziel = cls.wo / (name + ".pkg")
        erg = orbispkg.bauen(str(gp4), str(quelle), str(ziel))
        assert erg.ok, erg.meldung
        return ziel

    def setUp(self) -> None:
        self.a = au.Aufgabe(kennung=11, art="x", titel="x")

    def test_entpacken_ergibt_einen_dump_ordner(self) -> None:
        ziel = self.wo / "dump_basis"
        au.arbeit_entpacken(self.a, str(self.basis), str(ziel), t)
        self.assertEqual(b"BASIS" * 400, (ziel / "eboot.bin").read_bytes())
        self.assertEqual(b"A" * 5000, (ziel / "data" / "a.bin").read_bytes())
        sfo = lese_paket(str(self.basis))
        self.assertTrue(sfo.lesbar, sfo.fehler)
        self.assertTrue((ziel / "sce_sys" / "param.sfo").is_file())
        self.assertFalse((ziel / "Image0").exists())
        self.assertFalse(Path(str(ziel) + ".partial").exists())

    def test_zusammenfuehren_legt_das_update_ueber_die_basis(self) -> None:
        ausgabe = self.wo / "zusammen" / "m.pkg"
        au.arbeit_zusammenfuehren(self.a, str(self.basis), str(self.patch), str(ausgabe), t,
                                  pruefen_danach=True)
        self.assertTrue(ausgabe.is_file())
        zusammen = lese_paket(str(ausgabe))
        self.assertTrue(zusammen.lesbar, zusammen.fehler)
        self.assertEqual("01.05", zusammen.app_ver)
        ziel = self.wo / "dump_zusammen"
        au.arbeit_entpacken(au.Aufgabe(kennung=12, art="x", titel="x"), str(ausgabe), str(ziel), t)
        self.assertEqual(b"A" * 5000, (ziel / "data" / "a.bin").read_bytes())
        self.assertEqual(b"NEU-B" * 700, (ziel / "data" / "b.bin").read_bytes(), "Das Update ersetzt die Datei.")
        self.assertEqual(b"C" * 2000, (ziel / "data" / "c.bin").read_bytes())
        self.assertEqual([], [p for p in (self.wo / "zusammen").iterdir() if p.name.startswith(".ps4ota")])

    def test_zusammenfuehren_von_zwei_basispaketen_scheitert_klar(self) -> None:
        with self.assertRaises(au.AufgabeFehler) as ctx:
            au.arbeit_zusammenfuehren(self.a, str(self.basis), str(self.basis), str(self.wo / "x.pkg"), t)
        self.assertEqual("werkzeug", ctx.exception.schluessel)
        self.assertIn("Patch", ctx.exception.text)
        self.assertFalse((self.wo / "x.pkg").exists())

    def test_neu_packen_und_pruefen(self) -> None:
        ausgabe = self.wo / "neu.pkg"
        au.arbeit_neu_packen(self.a, str(self.basis), str(ausgabe), t, pruefen_danach=True)
        self.assertTrue(ausgabe.is_file())
        au.arbeit_pruefen(au.Aufgabe(kennung=13, art="x", titel="x"), str(ausgabe), t, tief=True)

    def test_bauen_aus_einem_entpackten_ordner(self) -> None:
        dump = self.wo / "dump_fuer_bau"
        au.arbeit_entpacken(self.a, str(self.basis), str(dump), t)
        ausgabe = self.wo / "gebaut.pkg"
        au.arbeit_bauen(au.Aufgabe(kennung=14, art="x", titel="x"), str(dump), str(ausgabe), t, pruefen_danach=True)
        neu = lese_paket(str(ausgabe))
        self.assertTrue(neu.lesbar, neu.fehler)
        self.assertEqual("TEST00005", neu.title_id)
        pfade = {e.pfad for e in orbispkg.liste(str(ausgabe)) if not e.ist_ordner}
        self.assertIn("Image0/eboot.bin", pfade)
        self.assertIn("Image0/data/a.bin", pfade)
        self.assertEqual([], [p for p in self.wo.iterdir() if p.name.startswith(".ps4ota")])

    def test_die_warteschlange_fuehrt_das_alles_nacheinander_aus(self) -> None:
        schlange = au.Warteschlange()
        ziel = self.wo / "ueber_schlange"
        e1 = schlange.hinzufuegen("entpacken", "e", lambda a: au.arbeit_entpacken(a, str(self.basis), str(ziel), t))
        e2 = schlange.hinzufuegen("pruefen", "p", lambda a: au.arbeit_pruefen(a, str(self.basis), t))
        self.assertTrue(_bis(lambda: schlange.offen == 0, 60))
        stand = {a.kennung: a.status for a in schlange.schnappschuss()}
        self.assertEqual({e1.kennung: au.FERTIG, e2.kennung: au.FERTIG}, stand)
        self.assertTrue((ziel / "eboot.bin").is_file())


if __name__ == "__main__":
    unittest.main()
