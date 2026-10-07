# -*- coding: utf-8 -*-
"""Die Arbeit hinter „PS4 PKG Dump & Image Converter“ (``ps4_abbild``) - mit Nachbildungen der Werkzeuge.

OrbisPkgTool und PS4 FFPFSC laufen hier nicht: ``orbispkg.entpacken`` legt Dateien nach einer Tabelle an,
``lauf`` ist eine Funktion, die den Befehl aufzeichnet. Geprueft wird, was dieses Modul entscheidet:
Gruppierung, Einspielreihenfolge, Aufbau des Ordners, die Befehlszeile an PS4 FFPFSC, Aufraeumen, Abbruch.
"""
from __future__ import annotations

import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import orbispkg                      # noqa: E402
from ps5_validator.utils import ps4_abbild as ab               # noqa: E402
from ps5_validator.utils import ps4pkg_aufgaben as au          # noqa: E402
from ps5_validator.utils import ps4pkg_bibliothek as bib       # noqa: E402
from ps5_validator.utils.i18n import STRINGS                   # noqa: E402


def _t(schluessel: str, **werte) -> str:
    return STRINGS[schluessel]["de"].format(**werte)


def _eintrag(pfad, typ, title_id="CUSA00001", app_ver="01.00", groesse=1000, titel="Testspiel", content_id="",
             lesbar=True) -> bib.PkgEintrag:
    return bib.PkgEintrag(pfad=pfad, groesse=groesse, lesbar=lesbar, title_id=title_id, titel=titel, typ=typ,
                          app_ver=app_ver, content_id=content_id)


def _sfo(werte: dict) -> bytes:
    """Eine kleine param.sfo (nur Zeichenketten)."""
    schluessel = b""
    daten = b""
    eintraege = []
    for name, wert in werte.items():
        roh = str(wert).encode("utf-8") + b"\x00"
        eintraege.append((len(schluessel), len(daten), len(roh)))
        schluessel += name.encode("ascii") + b"\x00"
        daten += roh + b"\x00" * ((4 - len(roh) % 4) % 4)
    schluessel += b"\x00" * ((4 - len(schluessel) % 4) % 4)
    k_start = 0x14 + 16 * len(eintraege)
    d_start = k_start + len(schluessel)
    kopf = b"\x00PSF" + struct.pack("<IIII", 0x101, k_start, d_start, len(eintraege))
    tabelle = b""
    for schl_off, d_off, laenge in eintraege:
        tabelle += struct.pack("<HHIII", schl_off, 0x0204, laenge, laenge, d_off)
    return kopf + tabelle + schluessel + daten


class GruppierenTests(unittest.TestCase):

    def test_basis_updates_und_zusaetze_je_titel(self) -> None:
        eintraege = [
            _eintrag("b.pkg", bib.TYP_BASIS),
            _eintrag("u2.pkg", bib.TYP_UPDATE, app_ver="01.10"),
            _eintrag("u1.pkg", bib.TYP_UPDATE, app_ver="01.02"),
            _eintrag("d.pkg", bib.TYP_ZUSATZ, content_id="EP0000-CUSA00001_00-DLCEINS0000000001"),
            _eintrag("x.pkg", bib.TYP_BASIS, title_id="CUSA00002", titel="Anderes"),
        ]
        spiele = ab.spiele_gruppieren(eintraege)
        self.assertEqual(["CUSA00002", "CUSA00001"], [s.title_id for s in spiele])   # nach Titel geordnet
        s = {s.title_id: s for s in spiele}["CUSA00001"]
        self.assertEqual("b.pkg", s.basis.pfad)
        self.assertEqual(["01.02", "01.10"], [u.app_ver for u in s.updates])
        self.assertEqual(1, len(s.zusaetze))
        self.assertEqual("01.10", s.version)
        self.assertTrue(s.baubar)
        self.assertEqual(["b.pkg", "u1.pkg", "u2.pkg"], [p.pfad for p in s.pakete()])
        self.assertEqual(["b.pkg", "u1.pkg", "u2.pkg", "d.pkg"], [p.pfad for p in s.pakete(True)])

    def test_update_ohne_basis_ist_nicht_baubar(self) -> None:
        s = ab.spiele_gruppieren([_eintrag("u.pkg", bib.TYP_UPDATE, app_ver="01.05")])[0]
        self.assertFalse(s.baubar)
        self.assertEqual("01.05", s.version)

    def test_unlesbares_und_fremdes_zaehlt_nicht(self) -> None:
        eintraege = [_eintrag("a.pkg", bib.TYP_BASIS, lesbar=False), _eintrag("b.pkg", bib.TYP_BASIS, title_id=""),
                     _eintrag("c.pkg", bib.TYP_BASIS, title_id="kein-id")]
        self.assertEqual([], ab.spiele_gruppieren(eintraege))

    def test_zwei_basen_ergeben_die_hoehere_fassung(self) -> None:
        s = ab.spiele_gruppieren([_eintrag("alt.pkg", bib.TYP_BASIS, app_ver="01.00"),
                                  _eintrag("neu.pkg", bib.TYP_BASIS, app_ver="01.02")])[0]
        self.assertEqual("neu.pkg", s.basis.pfad)
        self.assertTrue(s.mehrere_basen)

    def test_zwei_updates_gleicher_fassung_ergeben_eines(self) -> None:
        s = ab.spiele_gruppieren([_eintrag("b.pkg", bib.TYP_BASIS), _eintrag("u.pkg", bib.TYP_UPDATE, app_ver="01.05"),
                                  _eintrag("u2.pkg", bib.TYP_UPDATE, app_ver="01.05")])[0]
        self.assertEqual(1, len(s.updates))

    def test_titel_kommt_von_der_basis(self) -> None:
        s = ab.spiele_gruppieren([_eintrag("u.pkg", bib.TYP_UPDATE, titel="Update-Name", app_ver="01.01"),
                                  _eintrag("b.pkg", bib.TYP_BASIS, titel="Spielname")])[0]
        self.assertEqual("Spielname", s.titel)


class DumpLesenTests(unittest.TestCase):

    def test_flacher_ordner_und_app_aufbau(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            flach = Path(tmp) / "flach"
            (flach / "sce_sys").mkdir(parents=True)
            (flach / "sce_sys" / "param.sfo").write_bytes(
                _sfo({"TITLE_ID": "CUSA00775", "TITLE": "Tetris", "APP_VER": "01.09"}))
            s = ab.spiel_aus_dump(str(flach))
            self.assertIsNotNone(s)
            self.assertEqual(("CUSA00775", "Tetris", "01.09"), (s.title_id, s.titel, s.version))
            self.assertTrue(s.baubar)
            dumper = Path(tmp) / "dumper"
            (dumper / "app" / "sce_sys").mkdir(parents=True)
            (dumper / "app" / "sce_sys" / "param.sfo").write_bytes(_sfo({"TITLE_ID": "CUSA00001", "TITLE": "X"}))
            self.assertEqual("CUSA00001", ab.spiel_aus_dump(str(dumper)).title_id)

    def test_kein_spiel_ergibt_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(ab.spiel_aus_dump(tmp))
            (Path(tmp) / "sce_sys").mkdir()
            (Path(tmp) / "sce_sys" / "param.sfo").write_bytes(_sfo({"TITLE_ID": "kaputt"}))
            self.assertIsNone(ab.spiel_aus_dump(tmp))

    def test_zusatzkennung_sind_die_letzten_16_zeichen(self) -> None:
        e = _eintrag("d.pkg", bib.TYP_ZUSATZ, content_id="EP0000-CUSA00001_00-ABCDEFGHIJKLMNOP")
        self.assertEqual("ABCDEFGHIJKLMNOP", ab.zusatz_kennung(e))
        self.assertEqual("dlc", ab.zusatz_kennung(_eintrag("dlc.pkg", bib.TYP_ZUSATZ)))


class _Entpacker:
    """Ersatz fuer ``orbispkg.entpacken``: legt je Paket Dateien in Image0/Sc0 an."""

    def __init__(self, inhalt: dict) -> None:
        self.inhalt = inhalt
        self.aufrufe: list[str] = []

    def __call__(self, paket, ziel, *, passcode=None, fortschritt=None, **_):
        self.aufrufe.append(os.path.basename(paket))
        for rel, text in self.inhalt[os.path.basename(paket)].items():
            ziel_datei = Path(ziel) / rel
            ziel_datei.parent.mkdir(parents=True, exist_ok=True)
            ziel_datei.write_bytes(text.encode("utf-8"))
        if fortschritt:
            fortschritt(1, 1, "datei")
        return orbispkg.EntpackErgebnis(ok=True, dateien_ok=len(self.inhalt[os.path.basename(paket)]))


def _liste(paket, passcode=None, **_):
    """Ersatz fuer ``orbispkg.liste``: eine Datei von 1000 Bytes (klein, damit kein Waechter anlaeuft)."""
    return [orbispkg.ListenEintrag(ist_ordner=False, groesse=0, pfad="Image0/x")]


def _aufgabe() -> au.Aufgabe:
    return au.Aufgabe(kennung=7, art="abbild", titel="x")


class DumpTests(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.spiel = ab.Spiel(
            title_id="CUSA00001", titel="Testspiel",
            basis=_eintrag(str(self.tmp / "basis.pkg"), bib.TYP_BASIS, groesse=900),
            updates=[_eintrag(str(self.tmp / "u1.pkg"), bib.TYP_UPDATE, app_ver="01.01", groesse=50),
                     _eintrag(str(self.tmp / "u2.pkg"), bib.TYP_UPDATE, app_ver="01.02", groesse=50)],
            zusaetze=[_eintrag(str(self.tmp / "dlc.pkg"), bib.TYP_ZUSATZ, groesse=10,
                               content_id="EP0000-CUSA00001_00-DLCEINS000000001")])
        self.inhalt = {
            "basis.pkg": {"Image0/eboot.bin": "EBOOT-1", "Image0/data/a.bin": "A-basis", "Image0/data/b.bin": "B-basis",
                          "Sc0/param.sfo": "SFO-basis"},
            "u1.pkg": {"Image0/data/a.bin": "A-u1", "Sc0/param.sfo": "SFO-u1"},
            "u2.pkg": {"Image0/data/c.bin": "C-u2", "Sc0/param.sfo": "SFO-u2"},
            "dlc.pkg": {"Image0/dlc.dat": "DLC", "Sc0/param.sfo": "SFO-dlc"},
        }
        self.entpacker = _Entpacker(self.inhalt)
        for ziel, ersatz in (("entpacken", self.entpacker), ("liste", _liste)):
            patcher = mock.patch.object(orbispkg, ziel, ersatz)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _lies(self, ordner: Path, rel: str) -> str:
        return (ordner / rel).read_text(encoding="utf-8")

    def test_updates_liegen_in_der_reihenfolge_ihrer_fassung_darueber(self) -> None:
        ziel = self.tmp / "ausgabe" / "dump"
        ab.dump_bereitstellen(_aufgabe(), self.spiel, str(ziel), _t)
        self.assertEqual(["basis.pkg", "u1.pkg", "u2.pkg"], self.entpacker.aufrufe)
        self.assertEqual("EBOOT-1", self._lies(ziel, "eboot.bin"))
        self.assertEqual("A-u1", self._lies(ziel, "data/a.bin"))       # vom Update ersetzt
        self.assertEqual("B-basis", self._lies(ziel, "data/b.bin"))    # unberuehrt
        self.assertEqual("C-u2", self._lies(ziel, "data/c.bin"))       # neu vom zweiten Update
        self.assertEqual("SFO-u2", self._lies(ziel, "sce_sys/param.sfo"))   # die neueste param.sfo gewinnt
        self.assertFalse((ziel / "Image0").exists())
        self.assertFalse((ziel / "Sc0").exists())

    def test_nichts_bleibt_ausser_dem_ziel(self) -> None:
        ziel = self.tmp / "ausgabe" / "dump"
        ab.dump_bereitstellen(_aufgabe(), self.spiel, str(ziel), _t)
        self.assertEqual(["dump"], sorted(os.listdir(ziel.parent)))

    def test_dumper_aufbau_mit_dlc(self) -> None:
        ziel = self.tmp / "ausgabe" / "dump"
        ab.dump_bereitstellen(_aufgabe(), self.spiel, str(ziel), _t, mit_dlc=True, dumper_aufbau=True)
        self.assertEqual("EBOOT-1", self._lies(ziel, "app/eboot.bin"))
        self.assertEqual("A-u1", self._lies(ziel, "app/data/a.bin"))
        self.assertEqual("DLC", self._lies(ziel, "addcont/DLCEINS000000001/dlc.dat"))
        self.assertEqual("SFO-dlc", self._lies(ziel, "addcont/DLCEINS000000001/sce_sys/param.sfo"))
        self.assertIn("dlc.pkg", self.entpacker.aufrufe)

    def test_ohne_dlc_wird_kein_zusatz_entpackt(self) -> None:
        ab.dump_bereitstellen(_aufgabe(), self.spiel, str(self.tmp / "d"), _t)
        self.assertNotIn("dlc.pkg", self.entpacker.aufrufe)

    def test_ein_vorhandenes_ziel_wird_nie_angefasst(self) -> None:
        ziel = self.tmp / "da"
        ziel.mkdir()
        (ziel / "wichtig.txt").write_text("x")
        with self.assertRaises(au.AufgabeFehler) as f:
            ab.dump_bereitstellen(_aufgabe(), self.spiel, str(ziel), _t)
        self.assertEqual("ziel_existiert", f.exception.schluessel)
        self.assertEqual(["wichtig.txt"], os.listdir(ziel))

    def test_ohne_basis_kein_dump(self) -> None:
        spiel = ab.Spiel(title_id="CUSA00001", updates=self.spiel.updates)
        with self.assertRaises(au.AufgabeFehler) as f:
            ab.dump_bereitstellen(_aufgabe(), spiel, str(self.tmp / "d"), _t)
        self.assertEqual("ohne_basis", f.exception.schluessel)
        self.assertEqual([], self.entpacker.aufrufe)

    def test_abbruch_raeumt_auf_und_legt_nichts_ab(self) -> None:
        a = _aufgabe()
        a.abbruch.set()
        ziel = self.tmp / "ausgabe" / "dump"
        with self.assertRaises(au.AufgabeAbgebrochen):
            ab.dump_bereitstellen(a, self.spiel, str(ziel), _t)
        self.assertFalse(ziel.exists())
        self.assertFalse(Path(str(ziel) + ".partial").exists())

    def test_ein_fehlschlag_des_werkzeugs_raeumt_auf(self) -> None:
        def kaputt(paket, ziel, **_):
            os.makedirs(ziel, exist_ok=True)
            return orbispkg.EntpackErgebnis(ok=False, meldung="Paket beschaedigt")
        ziel = self.tmp / "ausgabe" / "dump"
        with mock.patch.object(orbispkg, "entpacken", kaputt):
            with self.assertRaises(au.AufgabeFehler) as f:
                ab.dump_bereitstellen(_aufgabe(), self.spiel, str(ziel), _t)
        self.assertEqual("werkzeug", f.exception.schluessel)
        self.assertFalse(Path(str(ziel) + ".partial").exists())
        self.assertFalse(ziel.exists())

    def test_der_balken_steigt_und_endet_bei_bis(self) -> None:
        a = _aufgabe()
        stande: list[float] = []
        original = a.melden

        def merk(text, prozent=None):
            original(text, prozent)
            stande.append(a.prozent)
        a.melden = merk   # type: ignore[method-assign]
        ab.dump_bereitstellen(a, self.spiel, str(self.tmp / "d"), _t, von=0.0, bis=35.0)
        self.assertTrue(all(0.0 <= s <= 35.0 for s in stande), stande)
        self.assertEqual(sorted(stande), stande)
        self.assertGreater(max(stande), 30.0)

    def test_arbeit_dump_meldet_fertig(self) -> None:
        a = _aufgabe()
        ziel = self.tmp / "ziel" / "CUSA00001"
        ab.arbeit_dump(a, self.spiel, str(ziel), _t)
        self.assertEqual(str(ziel), a.ergebnis)
        self.assertEqual(100.0, a.prozent)
        self.assertTrue((ziel / "eboot.bin").is_file())


class _Schnell(ab._Groessenwaechter):
    """Der Waechter mit kurzem Takt, damit der Test nicht Sekunden wartet."""

    def __init__(self, ordner, melden) -> None:
        super().__init__(ordner, melden, takt=0.02)


class GroessenwaechterTests(unittest.TestCase):

    def test_ordnergroesse_zaehlt_alle_dateien_darunter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a" / "b").mkdir(parents=True)
            (Path(tmp) / "x.bin").write_bytes(b"1" * 100)
            (Path(tmp) / "a" / "y.bin").write_bytes(b"1" * 200)
            (Path(tmp) / "a" / "b" / "z.bin").write_bytes(b"1" * 300)
            self.assertEqual(600, ab.ordner_groesse(tmp))
            self.assertEqual(0, ab.ordner_groesse(str(Path(tmp) / "gibt-es-nicht")))

    def test_der_waechter_meldet_und_endet_mit_dem_kontext(self) -> None:
        gemeldet: list[int] = []
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "f.bin").write_bytes(b"1" * 500)
            with ab._Groessenwaechter(tmp, gemeldet.append, takt=0.02):
                import time
                time.sleep(0.25)
            nach = len(gemeldet)
            import time as _t
            _t.sleep(0.1)
        self.assertGreaterEqual(nach, 2)
        self.assertEqual({500}, set(gemeldet))
        self.assertEqual(nach, len(gemeldet), "nach dem Ende meldet er nichts mehr")

    def test_der_balken_springt_mit_den_bytes_auch_ohne_neue_datei(self) -> None:
        """Eine riesige Datei: Dateizahl steht still, die Bytes bewegen den Balken (Befund 07.10.2026)."""
        a = _aufgabe()
        waehrend: list[float] = []
        with tempfile.TemporaryDirectory() as tmp:
            ziel = os.path.join(tmp, "dump")

            def entpacken(paket, zielordner, *, fortschritt=None, **_):
                os.makedirs(zielordner, exist_ok=True)
                fortschritt(1, 2, "gross.bin")
                for teil in range(4):
                    with open(os.path.join(zielordner, "gross.bin"), "ab") as f:
                        f.write(b"1" * 250)
                    import time
                    time.sleep(0.08)
                waehrend.append(a.prozent)       # vor dem Ordnen am Ende (das setzt den Balken auf 92)
                return orbispkg.EntpackErgebnis(ok=True)

            with mock.patch.object(orbispkg, "entpacken", entpacken), \
                    mock.patch.object(orbispkg, "liste",
                                      lambda *x, **k: [orbispkg.ListenEintrag(False, 1000, "Image0/gross.bin")]), \
                    mock.patch.object(ab, "_Groessenwaechter", _Schnell), \
                    mock.patch.object(au, "dump_ordner_machen", lambda *x, **k: {"dateien": 0}):
                ab._teil_entpacken(a, "p.pkg", ziel, _t, 0.0, 100.0, None)
        # 1/2 Dateien waeren 45 %; mit den Bytes (1000 von 1000) muss der Balken waehrend des Entpackens weiter sein.
        self.assertEqual(1, len(waehrend))
        self.assertGreater(waehrend[0], 60.0, waehrend)
        self.assertLessEqual(waehrend[0], 90.0)


class AbbildTests(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.spiel = ab.Spiel(
            title_id="CUSA00001", titel="Testspiel",
            basis=_eintrag(str(self.tmp / "basis.pkg"), bib.TYP_BASIS, groesse=900),
            updates=[_eintrag(str(self.tmp / "u1.pkg"), bib.TYP_UPDATE, app_ver="01.01", groesse=50)],
            zusaetze=[_eintrag(str(self.tmp / "dlc.pkg"), bib.TYP_ZUSATZ, groesse=10,
                               content_id="EP0000-CUSA00001_00-DLCEINS000000001")])
        inhalt = {"basis.pkg": {"Image0/eboot.bin": "E", "Sc0/param.sfo": "S"},
                  "u1.pkg": {"Image0/x.bin": "X", "Sc0/param.sfo": "S1"},
                  "dlc.pkg": {"Image0/d.dat": "D", "Sc0/param.sfo": "SD"}}
        for ziel_, ersatz in (("entpacken", _Entpacker(inhalt)), ("liste", _liste)):
            patcher = mock.patch.object(orbispkg, ziel_, ersatz)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.befehle: list[list[str]] = []
        self.dump_beim_lauf: dict = {}

    def _lauf(self, rc=0, zeilen=("stage 1/5: x", "stage 3/5: y"), fehlt_abbild=False):
        def lauf(argumente, *, arbeitsordner, zeile_callback, fortschritt_callback=None, prozess_ablage=None,
                 json_modus=False):
            self.befehle.append(list(argumente))
            dump = argumente[argumente.index("--dump-dir") + 1] if "--dump-dir" in argumente else ""
            if dump:
                self.dump_beim_lauf["ordner"] = dump
                self.dump_beim_lauf["dateien"] = sorted(
                    str(p.relative_to(dump)).replace("\\", "/") for p in Path(dump).rglob("*") if p.is_file())
            for z in zeilen:
                zeile_callback(z)
            if fortschritt_callback:
                fortschritt_callback({"scope": "mkpfs", "phase": "compress", "current": 1, "total": 2})
            if rc == 0 and not fehlt_abbild:
                ziel = argumente[argumente.index("--output-dir") + 1]
                fmt = argumente[argumente.index("--output-format") + 1]
                (Path(ziel) / ("CUSA00001-A0101-V0101." + fmt)).write_bytes(b"abbild")
            return rc, ""
        return lauf

    def _abbild(self, **kw):
        a = _aufgabe()
        ziel = str(self.tmp / "ziel")
        arbeit = str(self.tmp / "arbeit")
        with mock.patch.object(ab.ps4_werkzeug, "abbild_pruefen",
                               return_value={"dateien": 3, "fehlend": [], "ps4": True, "fehler": ""}):
            ab.arbeit_abbild(a, self.spiel, ziel, kw.pop("format_", "ffpfsc"), _t, arbeitsordner=arbeit,
                             lauf=kw.pop("lauf", None) or self._lauf(), engine_orbis=kw.pop("engine_orbis", True), **kw)
        return a, ziel, arbeit

    def test_ffpfsc_bekommt_den_fertigen_dump_ordner(self) -> None:
        a, ziel, arbeit = self._abbild(stufe=5, worker=3)
        befehl = self.befehle[0]
        self.assertEqual(["build", "CUSA00001", "--dump-dir"], befehl[:3])
        self.assertEqual(["--output-format", "ffpfsc", "--compression-level", "5", "--compression-workers", "3",
                          "--dlc-mode", "off"], [befehl[i] for i in (
                              befehl.index("--output-format"), befehl.index("--output-format") + 1,
                              befehl.index("--compression-level"), befehl.index("--compression-level") + 1,
                              befehl.index("--compression-workers"), befehl.index("--compression-workers") + 1,
                              befehl.index("--dlc-mode"), befehl.index("--dlc-mode") + 1)])
        self.assertIn("--console-log", befehl)
        # Der Dump-Ordner war beim Lauf fertig: flach, Update eingespielt, neueste param.sfo.
        self.assertEqual(["eboot.bin", "sce_sys/param.sfo", "x.bin"], self.dump_beim_lauf["dateien"])

    def test_nach_dem_lauf_bleibt_nichts_vom_zwischenstand(self) -> None:
        a, ziel, arbeit = self._abbild()
        self.assertEqual(["CUSA00001-A0101-V0101.ffpfsc"], os.listdir(ziel))
        self.assertEqual([], [n for n in os.listdir(arbeit) if n.startswith(("lauf_", "quelle_"))])
        self.assertFalse(os.path.exists(self.dump_beim_lauf["ordner"]))

    def test_die_quelle_ueberschneidet_sich_nicht_mit_dem_arbeitsordner_des_werkzeugs(self) -> None:
        """PS4 FFPFSC lehnt sonst ab: Die Quelle ueberschneide sich mit seinem Arbeitsordner."""
        self._abbild()
        befehl = self.befehle[0]
        quelle = os.path.normcase(os.path.abspath(befehl[befehl.index("--dump-dir") + 1]))
        for schalter in ("--work-dir", "--unpacked-dir"):
            werkzeug = os.path.normcase(os.path.abspath(befehl[befehl.index(schalter) + 1]))
            self.assertFalse(quelle == werkzeug or quelle.startswith(werkzeug + os.sep), schalter)
            self.assertFalse(werkzeug.startswith(quelle + os.sep), schalter)

    def test_der_wegwerf_ordner_wird_verbraucht_die_quelle_des_nutzers_nicht(self) -> None:
        self._abbild()
        self.assertIn("--consume-dump", self.befehle[0])
        self.befehle.clear()
        dump = self.tmp / "fertig"
        dump.mkdir()
        self.spiel = ab.Spiel(title_id="CUSA00001", titel="X", dump_ordner=str(dump))
        self._abbild()
        self.assertNotIn("--consume-dump", self.befehle[0])

    def test_exfat_wird_durchgereicht(self) -> None:
        self._abbild(format_="exfat")
        self.assertEqual("exfat", self.befehle[0][self.befehle[0].index("--output-format") + 1])

    def test_mit_dlc_im_dumper_aufbau(self) -> None:
        self._abbild(mit_dlc=True)
        befehl = self.befehle[0]
        self.assertEqual("single-experimental", befehl[befehl.index("--dlc-mode") + 1])
        self.assertEqual(["addcont/DLCEINS000000001/d.dat", "addcont/DLCEINS000000001/sce_sys/param.sfo",
                          "app/eboot.bin", "app/sce_sys/param.sfo", "app/x.bin"], self.dump_beim_lauf["dateien"])

    def test_ohne_orbispkg_der_bisherige_weg_ueber_die_pakete(self) -> None:
        self._abbild(engine_orbis=False)
        befehl = self.befehle[0]
        self.assertNotIn("--dump-dir", befehl)
        paare = [befehl[i + 1] for i, x in enumerate(befehl) if x == "--pkg-file"]
        self.assertEqual([self.spiel.basis.pfad, self.spiel.updates[0].pfad], paare)

    def test_ein_entpacktes_spiel_geht_unveraendert_an_ps4ffpfsc(self) -> None:
        dump = self.tmp / "fertig"
        dump.mkdir()
        spiel = ab.Spiel(title_id="CUSA00001", titel="X", dump_ordner=str(dump))
        self.spiel = spiel
        self._abbild()
        befehl = self.befehle[0]
        self.assertEqual(str(dump), befehl[befehl.index("--dump-dir") + 1])
        self.assertTrue(dump.is_dir(), "die Quelle des Nutzers bleibt stehen")

    def test_fehlschlag_ergibt_aufgabefehler_und_raeumt_auf(self) -> None:
        a = _aufgabe()
        arbeit = self.tmp / "arbeit"
        with self.assertRaises(au.AufgabeFehler) as f:
            ab.arbeit_abbild(a, self.spiel, str(self.tmp / "ziel"), "ffpfsc", _t, arbeitsordner=str(arbeit),
                             lauf=self._lauf(rc=3, zeilen=("irgendwas", "boese Zeile")), engine_orbis=True)
        self.assertEqual("abbild", f.exception.schluessel)
        self.assertEqual(3, f.exception.werte["code"])
        self.assertIn("boese Zeile", f.exception.werte["grund"])
        self.assertEqual([], [n for n in os.listdir(arbeit) if n.startswith("lauf_")])

    def test_abbruch_waehrend_des_laufs(self) -> None:
        a = _aufgabe()

        def lauf(argumente, *, arbeitsordner, zeile_callback, **_):
            a.abbruch.set()
            return 1, ""
        with self.assertRaises(au.AufgabeAbgebrochen):
            ab.arbeit_abbild(a, self.spiel, str(self.tmp / "ziel"), "ffpfsc", _t,
                             arbeitsordner=str(self.tmp / "arbeit"), lauf=lauf, engine_orbis=True)
        self.assertEqual([], [n for n in os.listdir(self.tmp / "arbeit") if n.startswith("lauf_")])

    def test_der_balken_nutzt_die_ganze_skala(self) -> None:
        a, _ziel, _arbeit = self._abbild()
        self.assertEqual(100.0, a.prozent)

    def test_stufen_aus_dem_protokoll_gehen_in_den_status(self) -> None:
        a = _aufgabe()
        texte: list[str] = []
        original = a.melden
        a.melden = lambda text, prozent=None: (texte.append(text), original(text, prozent))   # type: ignore[method-assign]
        with mock.patch.object(ab.ps4_werkzeug, "abbild_pruefen",
                               return_value={"dateien": 1, "fehlend": [], "ps4": True, "fehler": ""}):
            ab.arbeit_abbild(a, self.spiel, str(self.tmp / "ziel"), "ffpfsc", _t,
                             arbeitsordner=str(self.tmp / "arbeit"), lauf=self._lauf(), engine_orbis=True)
        self.assertTrue(any("Schritt 3 von 5" in x for x in texte), texte)

    def test_falsches_format_wird_abgelehnt(self) -> None:
        with self.assertRaises(ValueError):
            ab.arbeit_abbild(_aufgabe(), self.spiel, str(self.tmp / "z"), "dump", _t,
                             arbeitsordner=str(self.tmp / "a"), lauf=self._lauf(), engine_orbis=True)

    def test_platz_wird_vor_dem_start_geprueft(self) -> None:
        with mock.patch.object(au, "freier_platz", return_value=10):
            with self.assertRaises(au.AufgabeFehler) as f:
                ab.arbeit_abbild(_aufgabe(), self.spiel, str(self.tmp / "z"), "ffpfsc", _t,
                                 arbeitsordner=str(self.tmp / "a"), lauf=self._lauf(), engine_orbis=True)
        self.assertEqual("kein_platz", f.exception.schluessel)
        self.assertEqual([], self.befehle)


class PaketTests(unittest.TestCase):

    def test_zusammenfuehren_nimmt_das_neueste_update(self) -> None:
        spiel = ab.Spiel(title_id="CUSA00001", titel="Spiel: Teil",
                         basis=_eintrag("b.pkg", bib.TYP_BASIS),
                         updates=[_eintrag("u1.pkg", bib.TYP_UPDATE, app_ver="01.01"),
                                  _eintrag("u2.pkg", bib.TYP_UPDATE, app_ver="01.07")])
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(au, "arbeit_zusammenfuehren") as zusammen:
            ab.arbeit_pkg_zusammen(_aufgabe(), spiel, tmp, _t, arbeiter=4)
        args = zusammen.call_args
        self.assertEqual("b.pkg", args.args[1])
        self.assertEqual("u2.pkg", args.args[2])
        name = os.path.basename(args.args[3])
        self.assertTrue(name.endswith("[CUSA00001] [v01.07].pkg"), name)
        self.assertNotIn(":", name)
        self.assertEqual(4, args.kwargs["arbeiter"])

    def test_ohne_update_oder_basis_ein_klarer_fehler(self) -> None:
        nur_basis = ab.Spiel(title_id="CUSA00001", basis=_eintrag("b.pkg", bib.TYP_BASIS))
        with self.assertRaises(au.AufgabeFehler) as f:
            ab.arbeit_pkg_zusammen(_aufgabe(), nur_basis, ".", _t)
        self.assertEqual("ohne_update", f.exception.schluessel)
        nur_update = ab.Spiel(title_id="CUSA00001", updates=[_eintrag("u.pkg", bib.TYP_UPDATE)])
        with self.assertRaises(au.AufgabeFehler) as f:
            ab.arbeit_pkg_zusammen(_aufgabe(), nur_update, ".", _t)
        self.assertEqual("ohne_basis", f.exception.schluessel)


class TexteTests(unittest.TestCase):

    def test_jeder_fehlerschluessel_hat_einen_text(self) -> None:
        for schluessel in ("ohne_basis", "ohne_update", "abbild", "kein_platz", "ziel_existiert", "werkzeug"):
            with self.subTest(schluessel=schluessel):
                self.assertIn("ps4ota.fehler_" + schluessel, STRINGS)

    def test_neue_texte_sind_zweisprachig(self) -> None:
        for schluessel in [k for k in STRINGS if k.startswith("ps4dib.")]:
            with self.subTest(schluessel=schluessel):
                self.assertTrue(STRINGS[schluessel]["de"] and STRINGS[schluessel]["en"])
                self.assertNotEqual(STRINGS[schluessel]["de"], STRINGS[schluessel]["en"])

    def test_platzbedarf(self) -> None:
        spiel = ab.Spiel(title_id="CUSA00001", basis=_eintrag("b.pkg", bib.TYP_BASIS, groesse=1000))
        self.assertEqual((0, 2200), ab.platz_noetig(spiel, ab.FORMAT_DUMP))
        self.assertEqual((2200, 1300), ab.platz_noetig(spiel, ab.FORMAT_FFPFSC))
        self.assertEqual((0, 0), ab.platz_noetig(ab.Spiel(title_id="CUSA00001", dump_ordner="x"), ab.FORMAT_FFPFSC))


if __name__ == "__main__":
    unittest.main()
