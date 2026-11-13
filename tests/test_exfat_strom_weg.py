# -*- coding: utf-8 -*-
"""``.exfat`` -> ``.exfat`` mit zstd-Asset-Pack **ohne Zwischenordner** (Stufe 3, Etappe 4): der ganze Weg an einer kleinen echten Quelle.

Das Hauptprogramm-Objekt ist echt (``__new__`` ohne Fenster, wie ``test_exfat_folder_build``); ersetzt sind nur die Teile, die ein Fenster,
das Netz oder die Einstellungsdatei brauchen. Der Einbau selbst (``_integration_anwenden``) ist durch eine kleine Nachbildung ersetzt, die
dieselben Bausteine ruft wie ``_integration_ampr``: Bibliothek in den Ueberlagerungsordner, ``ampr_emu.index`` ueber die Ansicht, Packs
messen (``_ampr_zstdpakete_bauen``). Geprueft wird am Ergebnis: Abbild lesbar, Systemdateien da, Originale weg, Packs gleich der Quelle,
Index nennt jede Datei, Quelle unveraendert, kein Rest im Temp-Ordner.
"""
from __future__ import annotations

import json
import os
import shutil
import struct
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "MkPFS-1.1.0"))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("exfat_strom_weg")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from mkpfs.exfat_writer import iter_exfat_image              # noqa: E402

from ps5_validator.utils import ampr_zstdpack as z           # noqa: E402
from ps5_validator.utils import spielbaum as sb              # noqa: E402
from ps5_validator.utils.param_manifest import create_default_param   # noqa: E402

GUI = APP.PS5ConverterGUI
NG_LIB = b"MZ-ampr-emu-ng-" + bytes(range(256)) * 8


def _zufall(n: int, startwert: int = 1) -> bytes:
    import hashlib
    aus = bytearray()
    zaehler = startwert
    while len(aus) < n:
        aus += hashlib.sha256(str(zaehler).encode()).digest()
        zaehler += 1
    return bytes(aus[:n])


def _spiel() -> dict[str, bytes]:
    param = json.dumps(create_default_param(title_id="PPSA04263", title="Test Game")).encode("utf-8")
    return {
        "eboot.bin": b"\x7fELF" + bytes(2000),
        "sce_sys/param.json": param,
        "sce_sys/icon0.png": _zufall(5000, 2),
        "fakelib/libSceAmpr.sprx": b"original-lib" * 20,
        "sce_module/libc.prx": b"prx" * 100,
        "Media/text.txt": b"Hallo Welt\n" * 80_000,
        "Media/zufall.bin": _zufall(300_000, 3),
        "data/genau.bin": b"A" * z.CHUNK_SIZE,
        "data/klein.cfg": b"a=1\n",
        "data/leer.bin": b"",
        "data/prog.bin": b"\x7fELF" + bytes(500),                     # Programm mit anderem Namen (Backport-Kandidat)
    }


class _Var:
    def __init__(self, wert) -> None:
        self._w = wert

    def get(self):
        return self._w


class _Fortschritt:
    def __getattr__(self, name):
        return lambda *a, **k: None


class _Label:
    def config(self, **_k) -> None:
        pass


class _Wurzel:
    def after(self, _ms, callback) -> None:
        callback()


def _gui(tmp: str, *, weglassen: bool = True, backport: bool = False) -> "GUI":
    g = GUI.__new__(GUI)
    protokoll: list[str] = []
    g._log_lines = protokoll
    g._append_to_log = protokoll.append
    g._set_status = lambda text: None
    g._fmt_bytes = lambda n: str(n)
    g.is_running = True
    g.root = _Wurzel()
    g.status_label = _Label()
    g.progress_engine = _Fortschritt()
    g.mkpfs_dir = str((ROOT / "MkPFS-1.1.0").resolve())
    g._extract_embedded_mkpfs = lambda anlegen=True: str((ROOT / "MkPFS-1.1.0").resolve())
    g.task_progress = 0.0
    g.task_total_source_bytes = 0
    g._copy_total_bytes = g._copy_done_bytes = 0
    g._copy_total_exact = True
    g._copy_rate_bps = 0.0
    g._copy_rate_trend = ""
    g._online_nachschlag_erlaubt = lambda: False
    g._ask_yesno_threadsafe = lambda *a, **k: True
    g._notify_param_json_problem = lambda missing: None
    g.wahl = {"ampr_integrate_var": True, "ampr_pack_methode": True, "backport_integrate_var": backport}
    g._tk_wert = lambda name, vorgabe=False: g.wahl.get(name, vorgabe)
    g.einstellungen = {}
    g._load_setting = lambda name, vorgabe=None: g.einstellungen.get(name, vorgabe)
    g._ampr_wird_eingebaut = lambda: True
    g._ampr_methode = lambda: APP.AMPR_METHODE_ASSETPACK
    g._ampr_pack_verfahren = lambda: "zstd"
    g._ampr_zstd_stufe = lambda: 3
    g._ampr_zstd_arbeiter = lambda: 2
    g._ampr_pack_fortschritt = lambda prozent, phase: None
    g._ampr_pack_konsolenhinweis = lambda ordner: g._append_to_log("KONSOLENHINWEIS")
    g._ampr_originale_weglassen = weglassen
    g._pack_infotext = ""
    g._quellgroesse_mit_meldung = lambda pfad: 1
    g._mkdtemp = lambda prefix, dir_path=None: tempfile.mkdtemp(prefix=prefix, dir=os.path.join(tmp, "temp"))
    g._dump_ordner_basis = lambda dst: None
    g._bauziel_neben_quelle = lambda final: final
    g._bauziel_uebernehmen = lambda ist, final: final
    g._ampr_zstd_regeldatei = lambda: ""

    def integration(ordner: str, **_k) -> str:
        """Nachbildung von ``_integration_ampr`` mit denselben Bausteinen."""
        fakelib = os.path.join(ordner, "fakelib")
        os.makedirs(fakelib, exist_ok=True)
        with open(os.path.join(fakelib, "libSceAmpr.sprx"), "wb") as fh:
            fh.write(NG_LIB)
        g._ampr_ordner_ist_kopie = True
        index = Path(ordner) / "ampr_emu.index"
        g._build_ampr_index_local(Path(ordner), index)
        g._ampr_zstdpakete_bauen(ordner, str(index), {"variant": ""})
        return ordner

    g._integration_anwenden = integration
    return g


def _index_zeilen(pfad: str) -> list[tuple[int, str]]:
    """``(Groesse, Pfad)`` aus einem AMPRIDX3."""
    d = Path(pfad).read_bytes()
    magic, _v, rec_size, anzahl, blob_len, _hoff, _hs, _hn = struct.unpack_from("<8sIIQQQII", d, 0)
    assert magic == b"AMPRIDX3"
    kopf = struct.calcsize("<8sIIQQQII")
    blob_start = kopf + anzahl * rec_size
    zeilen = []
    for i in range(anzahl):
        off, laenge, groesse, _mtime = struct.unpack_from("<IIQq", d, kopf + i * rec_size)
        zeilen.append((groesse, d[blob_start + off:blob_start + off + laenge].decode("utf-8")))
    return zeilen


class _Grundlage(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="exfatstrom_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.makedirs(os.path.join(self.tmp, "temp"))
        self.inhalt = _spiel()
        self.spiel = os.path.join(self.tmp, "spiel")
        for rel, daten in self.inhalt.items():
            voll = os.path.join(self.spiel, *rel.split("/"))
            os.makedirs(os.path.dirname(voll), exist_ok=True)
            Path(voll).write_bytes(daten)
        self.quelle = os.path.join(self.tmp, "spiel.exfat")
        with open(self.quelle, "wb") as fh:
            for stueck in iter_exfat_image(Path(self.spiel)):
                fh.write(stueck)
        self.stempel = (os.path.getsize(self.quelle), os.stat(self.quelle).st_mtime_ns)
        self.ziel = os.path.join(self.tmp, "ziel")
        os.makedirs(self.ziel)


@unittest.skipUnless(z.verfuegbar(), "zstandard fehlt")
class StromWegTests(_Grundlage):
    def lauf(self, **kw):
        g = _gui(self.tmp, **kw)
        ergebnis = g._mode_exfat_umpacken_strom(self.quelle, self.ziel)
        return g, ergebnis

    def test_ganzer_weg(self) -> None:
        g, ok = self.lauf()
        self.assertTrue(ok, "\n".join(g._log_lines))
        ausgabe = os.path.join(self.ziel, "spiel.exfat")
        self.assertTrue(os.path.isfile(ausgabe))
        with sb.ExfatBaum(ausgabe) as neu:
            dateien = neu.suchen()
            # Systemdateien da, mit der eingebauten Bibliothek
            self.assertEqual(NG_LIB, b"".join(dateien["fakelib/libSceAmpr.sprx"].lesen()))
            for rel in ("eboot.bin", "sce_sys/icon0.png", "sce_module/libc.prx"):
                self.assertEqual(self.inhalt[rel], b"".join(dateien[rel].lesen()), rel)
            # param.json wird vor dem Einbau geprueft und ergaenzt (contentId); die bisherige Fassung liegt als .alt daneben
            self.assertIn(b"contentId", b"".join(dateien["sce_sys/param.json"].lesen()))
            self.assertEqual(self.inhalt["sce_sys/param.json"], b"".join(dateien["sce_sys/param.json.alt"].lesen()))
            # gepackte Originale weg, leere Datei und Index/Packs da
            gepackt = {"Media/text.txt", "Media/zufall.bin", "data/genau.bin", "data/klein.cfg", "data/prog.bin"}
            for rel in gepackt:
                self.assertNotIn(rel, dateien, rel)
            self.assertIn("data/leer.bin", dateien)
            self.assertIn("ampr_emu.index", dateien)
            self.assertIn("ampr_zstd.index", dateien)
            self.assertIn("ampr_zstd-000.pak", dateien)
            # Die Packs enthalten genau die Originale: Rundlauf gegen den Ausgangsordner
            packs = os.path.join(self.tmp, "gelesen")
            os.makedirs(packs)
            for rel, d in dateien.items():
                if z.ist_packname(rel):
                    Path(packs, rel).write_bytes(b"".join(d.lesen()))
            index = z.pruefen(packs, self.spiel)
            self.assertEqual(gepackt, {d.pfad for d in index.dateien})
            # Der Index nennt jede Datei des Spiels (gepackt oder lose), ohne sich selbst
            index_pfad = os.path.join(self.tmp, "ampr_emu.index")
            Path(index_pfad).write_bytes(b"".join(dateien["ampr_emu.index"].lesen()))
            zeilen = _index_zeilen(index_pfad)
            groessen = {rel: d.groesse for rel, d in dateien.items()}
        erwartet = {("/app0/" + rel, len(d)) for rel, d in self.inhalt.items()
                    if rel not in ("fakelib/libSceAmpr.sprx", "sce_sys/param.json")}
        erwartet.add(("/app0/fakelib/libSceAmpr.sprx", len(NG_LIB)))
        erwartet.add(("/app0/sce_sys/param.json", groessen["sce_sys/param.json"]))
        erwartet.add(("/app0/sce_sys/param.json.alt", groessen["sce_sys/param.json.alt"]))
        self.assertEqual(erwartet, {(p, g_) for g_, p in zeilen})

    def test_mit_dem_echten_einbau(self) -> None:
        """Wie ``test_ganzer_weg``, aber mit dem echten ``_integration_anwenden`` -> ``_integration_ampr`` statt der Nachbildung."""
        g = _gui(self.tmp)
        g._integration_anwenden = GUI._integration_anwenden.__get__(g)
        g._integration_ampr = GUI._integration_ampr.__get__(g)
        lib = os.path.join(self.tmp, "libSceAmpr.sprx")
        Path(lib).write_bytes(NG_LIB)
        g.ampr_integrate_var = _Var(True)
        g.wahl["ampr_version_var"] = "0.4.2.1 test"
        g._ampr_auswahl_beim_start = lambda: {"0.4.2.1 test": {"path": lib, "variant": ""}}
        g._playgo_wird_eingebaut = lambda: False
        g._playgo_beim_einbau_fragen = False
        g._cli_mode = True
        ok = g._mode_exfat_umpacken_strom(self.quelle, self.ziel)
        self.assertTrue(ok, "\n".join(g._log_lines))
        with sb.ExfatBaum(os.path.join(self.ziel, "spiel.exfat")) as neu:
            dateien = neu.suchen()
            self.assertEqual(NG_LIB, b"".join(dateien["fakelib/libSceAmpr.sprx"].lesen()))
            self.assertIn("fakelib/libSceAmpr.sprx.orig", dateien)                # das Original des Spiels als Sicherung
            self.assertEqual(self.inhalt["fakelib/libSceAmpr.sprx"],
                             b"".join(dateien["fakelib/libSceAmpr.sprx.orig"].lesen()))
            self.assertIn("ampr_zstd.index", dateien)
            self.assertNotIn("Media/text.txt", dateien)
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))

    def test_quelle_unveraendert_kein_rest(self) -> None:
        g, ok = self.lauf()
        self.assertTrue(ok)
        self.assertEqual(self.stempel, (os.path.getsize(self.quelle), os.stat(self.quelle).st_mtime_ns))
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")), "Ueberlagerungsordner nicht weggeraeumt")
        self.assertEqual(["spiel.exfat"], os.listdir(self.ziel))
        self.assertIsNone(g._strom_ansicht)
        self.assertIsNone(g._strom_plan)

    def test_mit_originalen(self) -> None:
        g, ok = self.lauf(weglassen=False)
        self.assertTrue(ok, "\n".join(g._log_lines))
        with sb.ExfatBaum(os.path.join(self.ziel, "spiel.exfat")) as neu:
            dateien = neu.suchen()
            self.assertEqual(self.inhalt["Media/zufall.bin"], b"".join(dateien["Media/zufall.bin"].lesen()))
            self.assertIn("ampr_zstd-000.pak", dateien)

    def test_stufen_und_protokoll(self) -> None:
        g, ok = self.lauf()
        self.assertTrue(ok)
        text = "\n".join(g._log_lines)
        self.assertIn("KONSOLENHINWEIS", text)
        folge = g._stufen
        for schluessel in ("phase.ueberlagerung", "phase.integration", "phase.messen", "phase.schreiben", "phase.pruefen"):
            self.assertEqual("fertig", folge.zustand(schluessel), schluessel)

    def test_backport_zieht_programmdateien_mit(self) -> None:
        """Mit Backport kommt auch ``data/prog.bin`` (ELF-Kennung, anderer Name) in den Ueberlagerungsordner."""
        ohne, ok = self.lauf()
        self.assertTrue(ok, "\n".join(ohne._log_lines))
        self.assertTrue(any("5 von 11" in z_ for z_ in ohne._log_lines), "\n".join(ohne._log_lines))
        shutil.rmtree(self.ziel)
        os.makedirs(self.ziel)
        mit, ok = self.lauf(backport=True)
        self.assertTrue(ok, "\n".join(mit._log_lines))
        self.assertTrue(any("6 von 11" in z_ for z_ in mit._log_lines), "\n".join(mit._log_lines))

    def test_packs_schon_in_der_quelle_bleibt_beim_alten_weg(self) -> None:
        voll = os.path.join(self.spiel, "ampr_zstd.index")
        Path(voll).write_bytes(b"alt")
        with open(self.quelle, "wb") as fh:
            for stueck in iter_exfat_image(Path(self.spiel)):
                fh.write(stueck)
        g, ergebnis = self.lauf()
        self.assertIsNone(ergebnis)
        self.assertEqual([], os.listdir(self.ziel))

    def test_kein_exfat(self) -> None:
        Path(self.quelle).write_bytes(b"\0" * 4096)
        g, ergebnis = self.lauf()
        self.assertIsNone(ergebnis)

    def test_unzulaessiger_name_vor_der_arbeit(self) -> None:
        """Ein Name, den der exFAT-Schreiber nicht abbilden kann, wird gemeldet, ehe etwas gelesen oder gemessen wird."""
        echt = sb.ExfatBaum.dateien

        def mit_umlaut(baum):
            return echt(baum) + [sb.BaumDatei("data/ü.bin", 1, lambda _s: iter([b"x"]))]

        sb.ExfatBaum.dateien = mit_umlaut
        self.addCleanup(setattr, sb.ExfatBaum, "dateien", echt)
        g, ergebnis = self.lauf()
        self.assertFalse(ergebnis)
        self.assertEqual([], os.listdir(self.ziel))
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))
        self.assertTrue(any("non-ASCII" in z_ for z_ in g._log_lines), "\n".join(g._log_lines))

    def test_abbruch_laesst_nichts_zurueck(self) -> None:
        g = _gui(self.tmp)
        original = g._ampr_pack_fortschritt

        def abbrechen(prozent, phase):
            g.is_running = False
        g._ampr_pack_fortschritt = abbrechen
        ok = g._mode_exfat_umpacken_strom(self.quelle, self.ziel)
        self.assertFalse(ok)
        self.assertEqual([], os.listdir(self.ziel))
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))

    def test_quelle_aendert_sich_waehrend_des_laufs(self) -> None:
        g = _gui(self.tmp)
        urspruenglich = g._integration_anwenden

        def integration(ordner, **k):
            erg = urspruenglich(ordner, **k)
            with open(self.quelle, "ab") as fh:                    # die Quelle waechst nach dem Messen
                fh.write(b"\0" * 512)
            return erg
        g._integration_anwenden = integration
        ok = g._mode_exfat_umpacken_strom(self.quelle, self.ziel)
        self.assertFalse(ok)
        self.assertEqual([], os.listdir(self.ziel))
        self.assertTrue(any("geändert" in z_ or "geaendert" in z_ or "quelle_geaendert" in z_ for z_ in g._log_lines),
                        "\n".join(g._log_lines))


class WegwahlTests(unittest.TestCase):
    def _probe(self, **kw):
        g = GUI.__new__(GUI)
        g.einstellungen = kw.get("einstellungen", {})
        g._load_setting = lambda name, vorgabe=None: g.einstellungen.get(name, vorgabe)
        g._ampr_wird_eingebaut = lambda: kw.get("ampr", True)
        g._ampr_methode = lambda: kw.get("methode", APP.AMPR_METHODE_ASSETPACK)
        g._ampr_pack_verfahren = lambda: kw.get("verfahren", "zstd")
        return g

    @unittest.skipUnless(z.verfuegbar(), "zstandard fehlt")
    def test_nur_ampr_assetpack_zstd(self) -> None:
        self.assertTrue(self._probe()._strom_weg_gewaehlt())
        self.assertFalse(self._probe(verfahren="lz4")._strom_weg_gewaehlt())
        self.assertFalse(self._probe(methode="normal")._strom_weg_gewaehlt())
        self.assertFalse(self._probe(ampr=False)._strom_weg_gewaehlt())

    @unittest.skipUnless(z.verfuegbar(), "zstandard fehlt")
    def test_einstellung_schaltet_aus(self) -> None:
        self.assertFalse(self._probe(einstellungen={"exfat_strom": False})._strom_weg_gewaehlt())

    def test_platzbedarf_ohne_entpacktes_spiel(self) -> None:
        g = self._probe()
        g._quellgroesse_ermitteln = lambda src: 150 * 1024 ** 3
        g._estimate_unpack_space_requirement = lambda src: None
        g._integration_gewuenscht = lambda: True
        g._umhuellt_neu_packen = False
        temp, ziel, dump = g._platzbedarf_je_quelle("spiel.exfat", "exfat")
        self.assertEqual(0, dump)
        self.assertLess(temp, 10 * 1024 ** 3, "Temp-Platz darf nicht mit dem Spiel wachsen")
        self.assertEqual(int(150 * 1024 ** 3 * g._PLATZFAKTOR_ZIEL["exfat"]), ziel)
        # kleine Quelle: nie mehr als die Quelle selbst
        g._quellgroesse_ermitteln = lambda src: 500 * 1024 ** 2
        self.assertEqual(500 * 1024 ** 2, g._platzbedarf_je_quelle("spiel.exfat", "exfat")[0])
        # LZ4 (alter Weg): der Arbeitsordner braucht wieder das ganze Spiel
        g._quellgroesse_ermitteln = lambda src: 150 * 1024 ** 3
        g._ampr_pack_verfahren = lambda: "lz4"
        self.assertGreater(g._platzbedarf_je_quelle("spiel.exfat", "exfat")[0], 150 * 1024 ** 3)

    def test_umpacken_ruft_den_strom_zuerst(self) -> None:
        g = GUI.__new__(GUI)
        g._strom_weg_gewaehlt = lambda: True
        g._mode_exfat_umpacken_strom = lambda src, dst: "strom"
        self.assertEqual("strom", g._mode_exfat_umpacken("a", "b"))


if __name__ == "__main__":
    unittest.main()
