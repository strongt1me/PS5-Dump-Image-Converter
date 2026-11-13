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
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

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


@unittest.skipUnless(z.verfuegbar(), "zstandard fehlt")
class OrdnerStromTests(_Grundlage):
    """Etappe 6: Dump-Ordner -> ``.exfat`` mit zstd-Asset-Pack, ohne Arbeitskopie des Spiels."""

    def lauf(self, **kw):
        g = _gui(self.tmp, **kw)
        return g, g._mode_exfat_umpacken_strom(self.spiel, self.ziel, ordner=True)

    def _abzug(self) -> dict[str, tuple[int, int]]:
        """Pfad -> (Groesse, Aenderungszeit) aller Dateien des Spielordners."""
        erg = {}
        for wurzel, _o, namen in os.walk(self.spiel):
            for n in namen:
                voll = os.path.join(wurzel, n)
                st = os.stat(voll)
                erg[os.path.relpath(voll, self.spiel)] = (st.st_size, st.st_mtime_ns)
        return erg

    def test_ganzer_weg_gleicht_dem_exfat_weg(self) -> None:
        g, ok = self.lauf()
        self.assertTrue(ok, "\n".join(g._log_lines))
        ausgabe = os.path.join(self.ziel, "spiel.exfat")
        self.assertTrue(os.path.isfile(ausgabe))
        # Dasselbe Ergebnis wie aus der .exfat-Quelle desselben Spiels (Ablauf, Packs, Index byteweise)
        ziel2 = os.path.join(self.tmp, "ziel2")
        os.makedirs(ziel2)
        g2 = _gui(self.tmp)
        self.assertTrue(g2._mode_exfat_umpacken_strom(self.quelle, ziel2), "\n".join(g2._log_lines))
        with sb.ExfatBaum(ausgabe) as a, sb.ExfatBaum(os.path.join(ziel2, "spiel.exfat")) as b:
            da, db = a.suchen(), b.suchen()
            self.assertEqual(sorted(da), sorted(db))
            for rel in da:
                if rel in ("sce_sys/param.json", "sce_sys/param.json.alt"):
                    continue                         # die contentId steht in beiden, aber nicht notwendig gleich
                self.assertEqual(b"".join(db[rel].lesen()), b"".join(da[rel].lesen()), rel)
            for rel in ("eboot.bin", "sce_sys/icon0.png"):
                self.assertEqual(self.inhalt[rel], b"".join(da[rel].lesen()), rel)
            self.assertEqual(NG_LIB, b"".join(da["fakelib/libSceAmpr.sprx"].lesen()))
            self.assertNotIn("Media/text.txt", da)               # gepackt, Original weg
            self.assertIn("ampr_zstd-000.pak", da)

    def test_ordner_bleibt_unberuehrt_und_nichts_im_temp(self) -> None:
        vorher = self._abzug()
        g, ok = self.lauf()
        self.assertTrue(ok, "\n".join(g._log_lines))
        self.assertEqual(vorher, self._abzug(), "Der Spielordner des Anwenders wurde veraendert")
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))
        self.assertEqual(["spiel.exfat"], os.listdir(self.ziel))

    def test_einbau_bekommt_den_ordner_als_herkunft(self) -> None:
        """Eigenes Packprofil und DLC-Nachbarn werden neben dem Spielordner gesucht (``herkunft``), eine Arbeitskopie gibt es nicht."""
        g = _gui(self.tmp)
        gesehen = {}
        urspruenglich = g._integration_anwenden

        def integration(ordner, **k):
            gesehen.update(k)
            gesehen["ordner"] = ordner
            return urspruenglich(ordner, **k)
        g._integration_anwenden = integration
        self.assertTrue(g._mode_exfat_umpacken_strom(self.spiel, self.ziel, ordner=True))
        self.assertEqual(self.spiel, gesehen["herkunft"])
        self.assertNotEqual(os.path.abspath(self.spiel), os.path.abspath(gesehen["ordner"]))
        self.assertNotIn("ist_quellordner", gesehen)                         # nie nach einer Arbeitskopie fragen

    def test_exfat_quelle_gibt_keine_herkunft(self) -> None:
        g = _gui(self.tmp)
        gesehen = {}
        urspruenglich = g._integration_anwenden
        g._integration_anwenden = lambda ordner, **k: (gesehen.update(k), urspruenglich(ordner, **k))[1]
        self.assertTrue(g._mode_exfat_umpacken_strom(self.quelle, self.ziel))
        self.assertEqual("", gesehen["herkunft"])

    def test_ausgabename_aus_dem_ordnernamen(self) -> None:
        andere = os.path.join(self.tmp, "Mein Spiel 1.05")
        os.rename(self.spiel, andere)
        self.spiel = andere
        g, ok = self.lauf()
        self.assertTrue(ok, "\n".join(g._log_lines))
        self.assertEqual(["Mein Spiel 1.05.exfat"], os.listdir(self.ziel))

    def test_packs_schon_im_ordner_bleibt_beim_alten_weg(self) -> None:
        Path(self.spiel, "ampr_zstd.index").write_bytes(b"alt")
        g, ergebnis = self.lauf()
        self.assertIsNone(ergebnis)
        self.assertEqual([], os.listdir(self.ziel))

    def test_verweise_im_ordner_bleiben_beim_alten_weg(self) -> None:
        """Ein Verweis (hier: eine Datei, die ``islink`` als Verweis meldet - echte Symlinks brauchen unter Windows Rechte)."""
        from unittest import mock
        Path(self.spiel, "verweis.bin").write_bytes(b"x")
        echt = os.path.islink
        with mock.patch("os.path.islink", side_effect=lambda p: os.fspath(p).endswith("verweis.bin") or echt(p)):
            g, ergebnis = self.lauf()
        self.assertIsNone(ergebnis)
        self.assertEqual([], os.listdir(self.ziel))
        self.assertTrue(any("Verweise" in z_ or "links" in z_ for z_ in g._log_lines), "\n".join(g._log_lines))

    def test_leerer_ordner_bleibt_beim_alten_weg(self) -> None:
        leer = os.path.join(self.tmp, "leer")
        os.makedirs(leer)
        g = _gui(self.tmp)
        self.assertIsNone(g._mode_exfat_umpacken_strom(leer, self.ziel, ordner=True))

    def test_kein_ordner(self) -> None:
        g = _gui(self.tmp)
        self.assertIsNone(g._mode_exfat_umpacken_strom(os.path.join(self.tmp, "gibtsnicht"), self.ziel, ordner=True))

    def test_ordner_aendert_sich_waehrend_des_laufs(self) -> None:
        g = _gui(self.tmp)
        urspruenglich = g._integration_anwenden

        def integration(ordner, **k):
            erg = urspruenglich(ordner, **k)
            Path(self.spiel, "data", "neu.bin").write_bytes(b"jemand hat etwas abgelegt")
            return erg
        g._integration_anwenden = integration
        self.assertFalse(g._mode_exfat_umpacken_strom(self.spiel, self.ziel, ordner=True))
        self.assertEqual([], os.listdir(self.ziel))
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))

    def test_abbruch_laesst_nichts_zurueck(self) -> None:
        g = _gui(self.tmp)

        def abbrechen(prozent, phase):
            g.is_running = False
        g._ampr_pack_fortschritt = abbrechen
        self.assertFalse(g._mode_exfat_umpacken_strom(self.spiel, self.ziel, ordner=True))
        self.assertEqual([], os.listdir(self.ziel))
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))

    def test_folder_to_exfat_nimmt_den_strom_zuerst(self) -> None:
        g = GUI.__new__(GUI)
        g._strom_fuer_ordner_gewaehlt = lambda: True
        aufrufe = []
        g._mode_exfat_umpacken_strom = lambda src, dst, ordner=False: aufrufe.append((src, dst, ordner)) or "strom"
        self.assertEqual("strom", g._mode_folder_to_exfat("a", "b"))
        self.assertEqual([("a", "b", True)], aufrufe)

    def test_folder_to_exfat_faellt_auf_den_alten_weg_zurueck(self) -> None:
        g = GUI.__new__(GUI)
        g._strom_fuer_ordner_gewaehlt = lambda: True
        g._mode_exfat_umpacken_strom = lambda src, dst, ordner=False: None
        g._ausgabe_stamm = lambda *a, **k: "x"
        g._integration_anwenden = lambda src, **k: ""                       # der alte Weg beginnt hier und endet gleich
        self.assertFalse(g._mode_folder_to_exfat("a", "b"))

    def test_platzbedarf_fuer_ordner_ohne_arbeitskopie(self) -> None:
        g = GUI.__new__(GUI)
        g._strom_fuer_ordner_gewaehlt = lambda: True
        g._quellgroesse_ermitteln = lambda src: 150 * 1024 ** 3
        g._estimate_unpack_space_requirement = lambda src: None
        g._integration_gewuenscht = lambda: True
        g._umhuellt_neu_packen = False
        temp, ziel, dump = g._platzbedarf_je_quelle(self.spiel, "exfat")
        self.assertLess(temp, 10 * 1024 ** 3, "Eine Arbeitskopie des Spiels darf nicht mehr eingerechnet werden")
        self.assertEqual(0, dump)
        g._strom_fuer_ordner_gewaehlt = lambda: False
        self.assertGreater(g._platzbedarf_je_quelle(self.spiel, "exfat")[0], 150 * 1024 ** 3)


@unittest.skipUnless(z.verfuegbar(), "zstandard fehlt")
class PfsStromTests(_Grundlage):
    """Etappe 7: ``.ffpfsc``/``.ffpfs`` -> ``.exfat`` mit zstd-Asset-Pack, ohne das Spiel zu entpacken."""

    def setUp(self) -> None:
        super().setUp()
        from mkpfs import consts
        from mkpfs.pfs import build_pfs, build_pfs_stream_single_file
        self.huelle = os.path.join(self.tmp, "huelle.ffpfsc")
        build_pfs_stream_single_file(
            source_file=Path(self.quelle), output_path=Path(self.huelle), block_size=65536,
            pfs_version=consts.PFS_VERSION_PS5, case_insensitive=True, zlib_level=6, threshold_gain=0, min_file_gain=0,
            min_compress_size=0, cpu_count=1, compress=True)
        self.flach = os.path.join(self.tmp, "flach.ffpfs")
        build_pfs(source_root=Path(self.spiel), output_path=Path(self.flach), block_size=65536,
                  pfs_version=consts.PFS_VERSION_PS5, inode_bits=32, case_insensitive=True, signed=False, compress=False,
                  threshold_gain=0, cpu_count=1, zlib_level=6, dry_run=False, verbose=False)

    def lauf(self, quelle: str, **kw):
        g = _gui(self.tmp, **kw)
        return g, g._mode_exfat_umpacken_strom(quelle, self.ziel, pfs=True)

    def test_huelle_gleicht_dem_weg_aus_der_exfat(self) -> None:
        g, ok = self.lauf(self.huelle)
        self.assertTrue(ok, "\n".join(g._log_lines))
        ziel2 = os.path.join(self.tmp, "ziel2")
        os.makedirs(ziel2)
        g2 = _gui(self.tmp)
        self.assertTrue(g2._mode_exfat_umpacken_strom(self.quelle, ziel2), "\n".join(g2._log_lines))
        with sb.ExfatBaum(os.path.join(self.ziel, "huelle.exfat")) as a, sb.ExfatBaum(os.path.join(ziel2, "spiel.exfat")) as b:
            da, db = a.suchen(), b.suchen()
            self.assertEqual(sorted(da), sorted(db))
            for rel in da:
                if rel in ("sce_sys/param.json", "sce_sys/param.json.alt"):
                    continue
                self.assertEqual(b"".join(db[rel].lesen()), b"".join(da[rel].lesen()), rel)
            self.assertNotIn("Media/text.txt", da)                  # gepackt, Original weg
            self.assertIn("ampr_zstd-000.pak", da)

    def test_flaches_pfs(self) -> None:
        g, ok = self.lauf(self.flach)
        self.assertTrue(ok, "\n".join(g._log_lines))
        with sb.ExfatBaum(os.path.join(self.ziel, "flach.exfat")) as neu:
            dateien = neu.suchen()
            self.assertEqual(NG_LIB, b"".join(dateien["fakelib/libSceAmpr.sprx"].lesen()))
            self.assertEqual(self.inhalt["eboot.bin"], b"".join(dateien["eboot.bin"].lesen()))
            self.assertIn("ampr_zstd.index", dateien)

    def test_quelle_unveraendert_kein_rest(self) -> None:
        vorher = {p: (os.path.getsize(p), os.stat(p).st_mtime_ns) for p in (self.huelle, self.flach)}
        for quelle in (self.huelle, self.flach):
            g, ok = self.lauf(quelle)
            self.assertTrue(ok, "\n".join(g._log_lines))
        self.assertEqual(vorher, {p: (os.path.getsize(p), os.stat(p).st_mtime_ns) for p in (self.huelle, self.flach)})
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))

    def test_spiel_nicht_im_wurzelordner_bleibt_beim_alten_weg(self) -> None:
        """Liegt das Spiel in einem Unterordner des Abbilds, packt der bisherige Weg es aus (er sucht die Ebene)."""
        from mkpfs import consts
        from mkpfs.pfs import build_pfs
        tief = os.path.join(self.tmp, "tief")
        for rel, daten in self.inhalt.items():
            voll = os.path.join(tief, "PPSA04263", *rel.split("/"))
            os.makedirs(os.path.dirname(voll), exist_ok=True)
            Path(voll).write_bytes(daten)
        abbild = os.path.join(self.tmp, "tief.ffpfs")
        build_pfs(source_root=Path(tief), output_path=Path(abbild), block_size=65536, pfs_version=consts.PFS_VERSION_PS5,
                  inode_bits=32, case_insensitive=True, signed=False, compress=False, threshold_gain=0, cpu_count=1,
                  zlib_level=6, dry_run=False, verbose=False)
        g, ergebnis = self.lauf(abbild)
        self.assertIsNone(ergebnis)
        self.assertEqual([], os.listdir(self.ziel))

    def test_kein_abbild_bleibt_beim_alten_weg(self) -> None:
        kaputt = os.path.join(self.tmp, "kaputt.ffpfsc")
        Path(kaputt).write_bytes(b"\0" * 8192)
        g, ergebnis = self.lauf(kaputt)
        self.assertIsNone(ergebnis)
        self.assertEqual([], os.listdir(self.ziel))

    def test_packs_schon_im_abbild_bleibt_beim_alten_weg(self) -> None:
        from mkpfs import consts
        from mkpfs.pfs import build_pfs
        Path(self.spiel, "ampr_zstd.index").write_bytes(b"alt")
        abbild = os.path.join(self.tmp, "mit_packs.ffpfs")
        build_pfs(source_root=Path(self.spiel), output_path=Path(abbild), block_size=65536,
                  pfs_version=consts.PFS_VERSION_PS5, inode_bits=32, case_insensitive=True, signed=False, compress=False,
                  threshold_gain=0, cpu_count=1, zlib_level=6, dry_run=False, verbose=False)
        g, ergebnis = self.lauf(abbild)
        self.assertIsNone(ergebnis)

    def test_abbruch_laesst_nichts_zurueck(self) -> None:
        g = _gui(self.tmp)

        def abbrechen(prozent, phase):
            g.is_running = False
        g._ampr_pack_fortschritt = abbrechen
        self.assertFalse(g._mode_exfat_umpacken_strom(self.huelle, self.ziel, pfs=True))
        self.assertEqual([], os.listdir(self.ziel))
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))

    def test_abbild_aendert_sich_waehrend_des_laufs(self) -> None:
        kopie = os.path.join(self.tmp, "kopie.ffpfsc")
        shutil.copyfile(self.huelle, kopie)
        g = _gui(self.tmp)
        urspruenglich = g._integration_anwenden

        def integration(ordner, **k):
            erg = urspruenglich(ordner, **k)
            with open(kopie, "ab") as fh:
                fh.write(b"\0" * 512)
            return erg
        g._integration_anwenden = integration
        self.assertFalse(g._mode_exfat_umpacken_strom(kopie, self.ziel, pfs=True))
        self.assertEqual([], os.listdir(self.ziel))

    # -- Aufgabe 2 nimmt den Strom zuerst -------------------------------------------------------------------------------
    def _aufgabe2(self, *, checkpoint=None, strom_ergebnis="strom"):
        g = GUI.__new__(GUI)
        aufrufe: list[tuple] = []
        g._strom_weg_gewaehlt = lambda: True
        g._mode_exfat_umpacken_strom = lambda src, dst, **kw: aufrufe.append((src, dst, kw)) or strom_ergebnis
        g._ausgabe_stamm = lambda *a, **k: "x"
        g._active_resume_checkpoint = checkpoint

        class _Stopp(Exception):
            pass

        def stopp(*a, **k):
            raise _Stopp()
        g._mkdtemp = stopp
        g._quellgroesse_mit_meldung = stopp
        g._append_to_log = lambda *a, **k: None
        try:
            ergebnis = g._mode_unpack_to_exfat(self.huelle, self.ziel)
        except _Stopp:
            ergebnis = "alter weg"
        except Exception:                                             # noqa: BLE001 - alles danach gehoert dem alten Weg
            ergebnis = "alter weg"
        return ergebnis, aufrufe

    def test_aufgabe2_ruft_den_strom_zuerst(self) -> None:
        ergebnis, aufrufe = self._aufgabe2()
        self.assertEqual("strom", ergebnis)
        self.assertEqual([(os.path.abspath(self.huelle), os.path.abspath(self.ziel), {"pfs": True})], aufrufe)

    def test_aufgabe2_faellt_auf_den_alten_weg_zurueck(self) -> None:
        ergebnis, aufrufe = self._aufgabe2(strom_ergebnis=None)
        self.assertEqual("alter weg", ergebnis)
        self.assertEqual(1, len(aufrufe))

    def test_aufgabe2_setzt_einen_unterbrochenen_lauf_fort(self) -> None:
        zwischenstand = os.path.join(self.tmp, "alter_zwischenstand")
        os.makedirs(zwischenstand)
        ergebnis, aufrufe = self._aufgabe2(checkpoint={"tmp_dir": zwischenstand, "stage": "task2_step1_done"})
        self.assertEqual([], aufrufe, "Mit vorhandenem Zwischenstand soll der alte Weg fortsetzen, nicht der Strom neu anfangen")

    def test_platzbedarf_ffpfsc_ohne_entpacktes_spiel(self) -> None:
        g = GUI.__new__(GUI)
        g._strom_weg_gewaehlt = lambda: True
        g._quellgroesse_ermitteln = lambda src: 60 * 1024 ** 3
        g._estimate_unpack_space_requirement = lambda src: 150 * 1024 ** 3
        g._integration_gewuenscht = lambda: True
        g._umhuellt_neu_packen = False
        temp, ziel, dump = g._platzbedarf_je_quelle("spiel.ffpfsc", "exfat")
        self.assertLess(temp, 10 * 1024 ** 3, "Das entpackte Spiel darf nicht mehr im Arbeitsordner eingerechnet werden")
        self.assertEqual(0, dump)
        self.assertEqual(int(150 * 1024 ** 3 // 2 * g._PLATZFAKTOR_ZIEL["exfat"]), ziel)
        g._strom_weg_gewaehlt = lambda: False
        self.assertGreaterEqual(g._platzbedarf_je_quelle("spiel.ffpfsc", "exfat")[0], 150 * 1024 ** 3)


@unittest.skipUnless(z.verfuegbar(), "zstandard fehlt")
class FfpfscAusgabeTests(_Grundlage):
    """Etappe 8: Ergebnis als ``.ffpfsc`` (PFS mit einem inneren, komprimierten exFAT) statt als ``.exfat``, im selben Strom."""

    def setUp(self) -> None:
        super().setUp()
        from mkpfs import consts
        from mkpfs.pfs import build_pfs_stream_single_file
        self.huelle = os.path.join(self.tmp, "huelle.ffpfsc")
        build_pfs_stream_single_file(
            source_file=Path(self.quelle), output_path=Path(self.huelle), block_size=65536,
            pfs_version=consts.PFS_VERSION_PS5, case_insensitive=True, zlib_level=6, threshold_gain=0, min_file_gain=0,
            min_compress_size=0, cpu_count=1, compress=True)

    def gui(self, **kw):
        g = _gui(self.tmp, **kw)
        g._resolve_pack_profile = lambda mode, groesse: {
            "profile": "t", "level": 3, "cpu": 1, "cores": 1, "block_size": 65536, "size_gb": 0.0, "verify_after": True}
        g._format_phase_status = lambda text, **k: text
        return g

    def lauf(self, quelle, **kw):
        g = self.gui()
        return g, g._mode_exfat_umpacken_strom(quelle, self.ziel, ziel="ffpfsc", **kw)

    def _namen(self, pfad: str) -> dict:
        with sb.PfsBaum(pfad) as baum:
            return {d.rel: b"".join(d.lesen()) for d in baum.dateien()}

    def test_aus_exfat_gleicht_dem_exfat_ergebnis(self) -> None:
        g, ok = self.lauf(self.quelle)
        self.assertTrue(ok, "\n".join(g._log_lines))
        self.assertEqual(["spiel.ffpfsc"], os.listdir(self.ziel))
        ziel2 = os.path.join(self.tmp, "ziel2")
        os.makedirs(ziel2)
        g2 = self.gui()
        self.assertTrue(g2._mode_exfat_umpacken_strom(self.quelle, ziel2), "\n".join(g2._log_lines))
        als_container = self._namen(os.path.join(self.ziel, "spiel.ffpfsc"))
        with sb.ExfatBaum(os.path.join(ziel2, "spiel.exfat")) as b:
            als_exfat = {d.rel: b"".join(d.lesen()) for d in b.dateien()}
        self.assertEqual(sorted(als_exfat), sorted(als_container))
        for rel in als_exfat:
            if rel in ("sce_sys/param.json", "sce_sys/param.json.alt"):
                continue
            self.assertEqual(als_exfat[rel], als_container[rel], rel)
        self.assertEqual(NG_LIB, als_container["fakelib/libSceAmpr.sprx"])
        self.assertNotIn("Media/text.txt", als_container)          # gepackt, Original weg
        self.assertIn("ampr_zstd-000.pak", als_container)

    def test_innere_datei_heisst_wie_die_titelid(self) -> None:
        from mkpfs.pfs import inspect_pfs_image
        g, ok = self.lauf(self.quelle)
        self.assertTrue(ok, "\n".join(g._log_lines))
        befund = inspect_pfs_image(Path(self.ziel, "spiel.ffpfsc"), verify_payloads=False)
        self.assertEqual(["PPSA04263.exfat"], list(befund.file_inodes))

    def test_aus_ordner(self) -> None:
        g, ok = self.lauf(self.spiel, ordner=True)
        self.assertTrue(ok, "\n".join(g._log_lines))
        self.assertEqual(["spiel.ffpfsc"], os.listdir(self.ziel))
        dateien = self._namen(os.path.join(self.ziel, "spiel.ffpfsc"))
        self.assertIn("ampr_zstd.index", dateien)
        self.assertEqual(self.inhalt["eboot.bin"], dateien["eboot.bin"])

    def test_aus_ffpfsc(self) -> None:
        g, ok = self.lauf(self.huelle, pfs=True)
        self.assertTrue(ok, "\n".join(g._log_lines))
        self.assertEqual(["huelle.ffpfsc"], os.listdir(self.ziel))
        self.assertIn("ampr_zstd.index", self._namen(os.path.join(self.ziel, "huelle.ffpfsc")))

    def test_quelle_unveraendert_kein_rest(self) -> None:
        vorher = {p: (os.path.getsize(p), os.stat(p).st_mtime_ns) for p in (self.quelle, self.huelle)}
        for quelle, kw in ((self.quelle, {}), (self.huelle, {"pfs": True})):
            shutil.rmtree(self.ziel)
            os.makedirs(self.ziel)
            g, ok = self.lauf(quelle, **kw)
            self.assertTrue(ok, "\n".join(g._log_lines))
            self.assertEqual(1, len(os.listdir(self.ziel)), os.listdir(self.ziel))
        self.assertEqual(vorher, {p: (os.path.getsize(p), os.stat(p).st_mtime_ns) for p in (self.quelle, self.huelle)})
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))

    def test_ersetzt_ein_vorhandenes_ziel_erst_am_ende(self) -> None:
        altes = os.path.join(self.ziel, "spiel.ffpfsc")
        Path(altes).write_bytes(b"alt")
        g = self.gui()
        echt = g._verify_exfat_liste
        gesehen: list[bytes] = []

        def pruefen(pfad, strom, mkpfs_ordner=""):
            gesehen.append(Path(altes).read_bytes())                  # waehrend der Rueckleseprobe
            return echt(pfad, strom, mkpfs_ordner)
        g._verify_exfat_liste = pruefen
        self.assertTrue(g._mode_exfat_umpacken_strom(self.quelle, self.ziel, ziel="ffpfsc"), "\n".join(g._log_lines))
        self.assertEqual([b"alt"], gesehen, "das alte Ziel bleibt bis zur Uebernahme unberuehrt")
        self.assertNotEqual(b"alt", Path(altes).read_bytes())

    def test_abbruch_laesst_nichts_zurueck(self) -> None:
        g = self.gui()

        def abbrechen(prozent, phase):
            g.is_running = False
        g._ampr_pack_fortschritt = abbrechen
        self.assertFalse(g._mode_exfat_umpacken_strom(self.quelle, self.ziel, ziel="ffpfsc"))
        self.assertEqual([], os.listdir(self.ziel))
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))

    def test_abbruch_beim_schreiben_laesst_nichts_zurueck(self) -> None:
        g = self.gui()
        echt = g._phase_dauer_melden

        def melden(schluessel, start):
            echt(schluessel, start)
            if schluessel == "phase.messen":
                g.is_running = False
        g._phase_dauer_melden = melden
        self.assertFalse(g._mode_exfat_umpacken_strom(self.quelle, self.ziel, ziel="ffpfsc"))
        self.assertEqual([], os.listdir(self.ziel))

    def test_quelle_aendert_sich_waehrend_des_laufs(self) -> None:
        kopie = os.path.join(self.tmp, "kopie.exfat")
        shutil.copyfile(self.quelle, kopie)
        g = self.gui()
        urspruenglich = g._integration_anwenden

        def integration(ordner, **k):
            erg = urspruenglich(ordner, **k)
            with open(kopie, "ab") as fh:
                fh.write(b"\0" * 512)
            return erg
        g._integration_anwenden = integration
        self.assertFalse(g._mode_exfat_umpacken_strom(kopie, self.ziel, ziel="ffpfsc"))
        self.assertEqual([], os.listdir(self.ziel))

    def test_fehler_beim_schreiben_laesst_nichts_zurueck(self) -> None:
        g = self.gui()
        with mock.patch.object(APP.abbild_strom, "ffpfsc_schreiben", side_effect=OSError("Platte voll")):
            self.assertFalse(g._mode_exfat_umpacken_strom(self.quelle, self.ziel, ziel="ffpfsc"))
        self.assertEqual([], os.listdir(self.ziel))
        self.assertTrue(any("Platte voll" in z_ for z_ in g._log_lines), "\n".join(g._log_lines))

    def test_ein_beschaedigtes_ergebnis_wird_nicht_uebernommen(self) -> None:
        """Die Rueckleseprobe liest das Ergebnis ueber das innere exFAT: Stimmt etwas nicht, bleibt das Ziel leer."""
        g = self.gui()
        echt = APP.abbild_strom.ffpfsc_schreiben

        def beschaedigt(*a, **k):
            erg = echt(*a, **k)
            ziel = a[1]
            daten = bytearray(Path(ziel).read_bytes())
            for i in range(len(daten) // 2, len(daten) // 2 + 3000):
                daten[i] ^= 0xFF
            Path(ziel).write_bytes(bytes(daten))
            return erg
        with mock.patch.object(APP.abbild_strom, "ffpfsc_schreiben", side_effect=beschaedigt):
            self.assertFalse(g._mode_exfat_umpacken_strom(self.quelle, self.ziel, ziel="ffpfsc"))
        self.assertEqual([], os.listdir(self.ziel))

    # -- Pruefstufe (aus / schnell / voll) ---------------------------------------------------------------------------------
    def _mit_stufe(self, stufe):
        g = self.gui()
        if stufe is not None:
            g.mkpfs_verify = stufe
        aufrufe: list[str] = []
        echt = APP.abbild_strom.pfs_pruefen

        def pruefen(pfad, **kw):
            aufrufe.append(pfad)
            return echt(pfad, **kw)
        return g, aufrufe, mock.patch.object(APP.abbild_strom, "pfs_pruefen", side_effect=pruefen)

    def test_stufe_schnell_und_voll_pruefen_den_ganzen_container(self) -> None:
        for stufe in (None, "schnell", "voll"):
            with self.subTest(stufe=stufe):
                shutil.rmtree(self.ziel)
                os.makedirs(self.ziel)
                g, aufrufe, patch = self._mit_stufe(stufe)
                with patch:
                    self.assertTrue(g._mode_exfat_umpacken_strom(self.quelle, self.ziel, ziel="ffpfsc"), "\n".join(g._log_lines))
                self.assertEqual(1, len(aufrufe), "die Pruefung laeuft einmal, am .teil")
                self.assertTrue(aufrufe[0].endswith(".ffpfsc.teil"), aufrufe[0])
                self.assertTrue(any("geprüft" in z_ or "checked" in z_ for z_ in g._log_lines), "\n".join(g._log_lines))

    def test_stufe_aus_pruft_nicht(self) -> None:
        g, aufrufe, patch = self._mit_stufe("aus")
        with patch:
            self.assertTrue(g._mode_exfat_umpacken_strom(self.quelle, self.ziel, ziel="ffpfsc"), "\n".join(g._log_lines))
        self.assertEqual([], aufrufe)

    def test_ein_fehler_der_pruefung_verwirft_das_ergebnis(self) -> None:
        """Die Rueckleseprobe laesst alles durch (sie zieht nur eine Stichprobe) - die Pruefung des ganzen Containers faengt es."""
        g = self.gui()
        g._verify_exfat_liste = lambda *a, **k: {"checked": True, "ok": True, "detail": "x"}
        echt = APP.abbild_strom.ffpfsc_schreiben

        def beschaedigt(*a, **k):
            erg = echt(*a, **k)
            daten = bytearray(Path(a[1]).read_bytes())
            for i in range(len(daten) // 2, len(daten) // 2 + 3000):
                daten[i] ^= 0xFF
            Path(a[1]).write_bytes(bytes(daten))
            return erg
        with mock.patch.object(APP.abbild_strom, "ffpfsc_schreiben", side_effect=beschaedigt):
            self.assertFalse(g._mode_exfat_umpacken_strom(self.quelle, self.ziel, ziel="ffpfsc"))
        self.assertEqual([], os.listdir(self.ziel))
        self.assertTrue(any("unvollständig" in z_ or "incomplete" in z_ for z_ in g._log_lines), "\n".join(g._log_lines))

    def test_abbruch_waehrend_der_pruefung(self) -> None:
        g = self.gui()

        def abbrechen(pfad, **kw):
            g.is_running = False
            raise APP.abbild_strom.StromAbgebrochen("abgebrochen")
        with mock.patch.object(APP.abbild_strom, "pfs_pruefen", side_effect=abbrechen):
            self.assertFalse(g._mode_exfat_umpacken_strom(self.quelle, self.ziel, ziel="ffpfsc"))
        self.assertEqual([], os.listdir(self.ziel))
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))

    # -- Einhaengen ------------------------------------------------------------------------------------------------------
    def _verteiler(self, **eigenschaften):
        g = GUI.__new__(GUI)
        aufrufe: list[tuple] = []
        g._strom_weg_gewaehlt = lambda: eigenschaften.get("strom", True)
        g._strom_fuer_ordner_gewaehlt = lambda: eigenschaften.get("strom", True)
        g._strom_erlaubt = lambda *, einbau_noetig: eigenschaften.get("strom", True)
        g._ffpkg_output_path = lambda *a: (_ for _ in ()).throw(RuntimeError("alter weg"))
        g._mode_exfat_umpacken_strom = lambda src, dst, **kw: aufrufe.append((src, dst, kw)) or eigenschaften.get("ergebnis", "strom")
        g._ausgabe_stamm = lambda *a, **k: "x"
        g._mkdtemp = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("alter weg"))
        g._integration_anwenden = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("alter weg"))
        g._integration_erledigt = eigenschaften.get("erledigt", False)
        return g, aufrufe

    def test_exfat_zu_ffpfsc_nimmt_den_strom(self) -> None:
        g, aufrufe = self._verteiler()
        self.assertEqual("strom", g._mode_abbild_zu_ffpfs("a.exfat", "d", quelle="exfat", uncompressed=False))
        self.assertEqual([("a.exfat", "d", {"pfs": False, "ziel": "ffpfsc"})], aufrufe)

    def test_ffpfsc_zu_ffpfsc_nimmt_den_strom_mit_pfs(self) -> None:
        g, aufrufe = self._verteiler()
        g._mode_abbild_zu_ffpfs("a.ffpfsc", "d", quelle="ffpfsc", uncompressed=False)
        self.assertEqual([("a.ffpfsc", "d", {"pfs": True, "ziel": "ffpfsc"})], aufrufe)

    def test_ffpfs_ziel_nimmt_den_strom(self) -> None:
        """Etappe 11: Auch die flache ``.ffpfs`` entsteht im Strom, aus jedem Abbild als Quelle."""
        for quelle, kw in (("exfat", {"pfs": False}), ("ffpfsc", {"pfs": True}), ("ffpkg", {"ufs2": True})):
            g, aufrufe = self._verteiler()
            self.assertEqual("strom", g._mode_abbild_zu_ffpfs("a." + quelle, "d", quelle=quelle, uncompressed=True), quelle)
            self.assertEqual([("a." + quelle, "d", dict(kw, ziel="ffpfs"))], aufrufe, quelle)

    def test_ohne_strom_oder_bei_none_der_alte_weg(self) -> None:
        for eig in ({"strom": False}, {"ergebnis": None}):
            for unkomprimiert in (False, True):
                g, _aufrufe = self._verteiler(**eig)
                with self.assertRaises(RuntimeError, msg=(eig, unkomprimiert)):
                    g._mode_abbild_zu_ffpfs("a.exfat", "d", quelle="exfat", uncompressed=unkomprimiert)

    def test_ffpfsc_umpacken_zur_flachen_datei_nimmt_den_strom(self) -> None:
        g, aufrufe = self._verteiler()
        self.assertEqual("strom", g._mode_ffpfsc_umpacken("a.ffpfsc", "d", uncompressed=True))
        self.assertEqual([("a.ffpfsc", "d", {"pfs": True, "ziel": "ffpfs"})], aufrufe)

    def test_ffpfs_zu_ffpfsc_umpacken_nimmt_den_strom(self) -> None:
        """Etappe 12: Auch die Richtung zur ``.ffpfsc`` (z. B. eine ``.ffpfs`` neu komprimieren) braucht keinen Dump-Ordner."""
        g, aufrufe = self._verteiler()
        self.assertEqual("strom", g._mode_ffpfsc_umpacken("a.ffpfs", "d", uncompressed=False))
        self.assertEqual([("a.ffpfs", "d", {"pfs": True, "ziel": "ffpfsc"})], aufrufe)

    def test_ffpfsc_umpacken_zur_ffpfsc_in_der_bauform_pfs_bleibt_beim_alten_weg(self) -> None:
        g, aufrufe = self._verteiler()
        g.bauform = APP.BAUFORM_PFS
        with self.assertRaises(RuntimeError):
            g._mode_ffpfsc_umpacken("a.ffpfs", "d", uncompressed=False)
        self.assertEqual([], aufrufe)

    def test_ffpfsc_umpacken_ohne_strom_oder_bei_none_der_alte_weg(self) -> None:
        for eig in ({"strom": False}, {"ergebnis": None}):
            for unkomprimiert in (False, True):
                g, _aufrufe = self._verteiler(**eig)
                with self.assertRaises(RuntimeError, msg=(eig, unkomprimiert)):
                    g._mode_ffpfsc_umpacken("a.ffpfsc", "d", uncompressed=unkomprimiert)

    def test_ffpkg_als_ziel_nimmt_den_strom(self) -> None:
        """Etappe 13: Auch die ``.ffpkg`` als Ausgabe entsteht im Strom (eigener UFS2-Schreiber), aus jeder Quelle."""
        for name, aufruf, erwartet in (
                ("exfat", lambda g: g._mode_exfat_to_ffpkg("a.exfat", "d"), ("a.exfat", "d", {"ziel": "ffpkg"})),
                ("ffpfsc", lambda g: g._mode_ffpfsc_to_ffpkg("a.ffpfsc", "d"), ("a.ffpfsc", "d", {"pfs": True, "ziel": "ffpkg"})),
                ("ffpkg", lambda g: g._mode_ffpkg_to_ffpkg("a.ffpkg", "d"), ("a.ffpkg", "d", {"ufs2": True, "ziel": "ffpkg"})),
                ("ordner", lambda g: g._mode_folder_to_ffpkg(self.spiel, "d"), (self.spiel, "d", {"ordner": True, "ziel": "ffpkg"}))):
            with self.subTest(name):
                g, aufrufe = self._verteiler()
                self.assertEqual("strom", aufruf(g))
                self.assertEqual([erwartet], aufrufe)

    def test_ffpkg_als_ziel_ohne_strom_oder_bei_none_der_alte_weg(self) -> None:
        for eig in ({"strom": False}, {"ergebnis": None}):
            for name, aufruf in (("exfat", lambda g: g._mode_exfat_to_ffpkg("a.exfat", "d")),
                                 ("ffpfsc", lambda g: g._mode_ffpfsc_to_ffpkg("a.ffpfsc", "d")),
                                 ("ffpkg", lambda g: g._mode_ffpkg_to_ffpkg("a.ffpkg", "d")),
                                 ("ordner", lambda g: g._mode_folder_to_ffpkg(self.spiel, "d"))):
                with self.subTest(eig=eig, quelle=name):
                    g, _aufrufe = self._verteiler(**eig)
                    with self.assertRaises(RuntimeError):
                        aufruf(g)

    def test_ordner_zu_ffpfsc_nimmt_den_strom(self) -> None:
        g, aufrufe = self._verteiler()
        self.assertEqual("strom", g._mode_pack_folder(self.spiel, "d"))
        self.assertEqual([(self.spiel, "d", {"ordner": True, "ziel": "ffpfsc"})], aufrufe)

    def test_ordner_zu_ffpfs_nimmt_den_strom(self) -> None:
        g, aufrufe = self._verteiler()
        self.assertEqual("strom", g._mode_pack_folder(self.spiel, "d", uncompressed=True))
        self.assertEqual([(self.spiel, "d", {"ordner": True, "ziel": "ffpfs"})], aufrufe)

    def test_pack_folder_nach_erledigtem_einbau_nicht(self) -> None:
        for unkomprimiert in (False, True):
            g, aufrufe = self._verteiler(erledigt=True)
            with self.assertRaises(RuntimeError, msg=unkomprimiert):
                g._mode_pack_folder(self.spiel, "d", uncompressed=unkomprimiert)
            self.assertEqual([], aufrufe)

    def test_platzbedarf_fuer_den_container(self) -> None:
        g = GUI.__new__(GUI)
        g._strom_weg_gewaehlt = lambda: True
        g._strom_fuer_ordner_gewaehlt = lambda: True
        g._quellgroesse_ermitteln = lambda src: 150 * 1024 ** 3
        g._estimate_unpack_space_requirement = lambda src: None
        g._integration_gewuenscht = lambda: True
        g._umhuellt_neu_packen = False
        temp, ziel, dump = g._platzbedarf_je_quelle(self.spiel, "ffpfsc")
        self.assertLess(temp, 10 * 1024 ** 3)
        self.assertEqual(0, dump)
        self.assertEqual(int(150 * 1024 ** 3 * g._PLATZFAKTOR_ZIEL["ffpfsc"]), ziel)
        temp, _ziel, _dump = g._platzbedarf_je_quelle("spiel.exfat", "ffpfsc")
        self.assertLess(temp, 10 * 1024 ** 3)

    def test_platzbedarf_fuer_die_ffpkg(self) -> None:
        g = GUI.__new__(GUI)
        g._strom_erlaubt = lambda *, einbau_noetig: True
        g._quellgroesse_ermitteln = lambda src: 150 * 1024 ** 3
        g._estimate_unpack_space_requirement = lambda src: None
        g._integration_gewuenscht = lambda: True
        g._umhuellt_neu_packen = False
        for quelle in (self.spiel, "spiel.exfat"):
            temp, ziel, dump = g._platzbedarf_je_quelle(quelle, "ffpkg")
            self.assertLess(temp, 10 * 1024 ** 3, quelle)
            self.assertEqual(0, dump)
            self.assertEqual(int(150 * 1024 ** 3 * g._PLATZFAKTOR_ZIEL["ffpkg"]), ziel)
        g._strom_erlaubt = lambda *, einbau_noetig: False                    # ohne Strom wieder der Zwischenordner
        self.assertGreater(g._platzbedarf_je_quelle("spiel.exfat", "ffpkg")[0], 10 * 1024 ** 3)

    def test_platzbedarf_fuer_die_flache_datei(self) -> None:
        g = GUI.__new__(GUI)
        g._strom_weg_gewaehlt = lambda: True
        g._strom_fuer_ordner_gewaehlt = lambda: True
        g._quellgroesse_ermitteln = lambda src: 150 * 1024 ** 3
        g._estimate_unpack_space_requirement = lambda src: None
        g._integration_gewuenscht = lambda: True
        g._umhuellt_neu_packen = False
        for quelle in (self.spiel, "spiel.exfat"):
            temp, ziel, dump = g._platzbedarf_je_quelle(quelle, "ffpfs")
            self.assertLess(temp, 10 * 1024 ** 3, quelle)
            self.assertEqual(0, dump)
            self.assertEqual(int(150 * 1024 ** 3 * g._PLATZFAKTOR_ZIEL["ffpfs"]), ziel)
        g._strom_weg_gewaehlt = lambda: False                                # ohne Strom wieder der Zwischenordner
        g._strom_fuer_ordner_gewaehlt = lambda: False
        self.assertGreater(g._platzbedarf_je_quelle("spiel.exfat", "ffpfs")[0], 10 * 1024 ** 3)


@unittest.skipUnless(z.verfuegbar(), "zstandard fehlt")
class FfpfsAusgabeTests(_Grundlage):
    """Etappe 11: Ergebnis als flache ``.ffpfs`` (die Spieldateien direkt im PFS) im Strom - ohne exFAT, ohne Zwischenordner."""

    PATCH = b"\x7fELF" + b"EINGEBAUT"

    def setUp(self) -> None:
        super().setUp()
        from mkpfs import consts
        from mkpfs.pfs import build_pfs_stream_single_file
        self.huelle = os.path.join(self.tmp, "huelle.ffpfsc")
        build_pfs_stream_single_file(
            source_file=Path(self.quelle), output_path=Path(self.huelle), block_size=65536,
            pfs_version=consts.PFS_VERSION_PS5, case_insensitive=True, zlib_level=6, threshold_gain=0, min_file_gain=0,
            min_compress_size=0, cpu_count=1, compress=True)

    def gui(self, **kw):
        g = _gui(self.tmp, **kw)
        g._resolve_pack_profile = lambda mode, groesse: {
            "profile": "t", "level": 3, "cpu": 1, "cores": 1, "block_size": 65536, "size_gb": 0.0, "verify_after": True}
        g._format_phase_status = lambda text, **k: text
        return g

    def gui_nur_einbau(self, einbau: bool = True):
        """Ohne Pack: der Einbau aendert nur ``eboot.bin`` und legt eine Bibliothek ab."""
        g = self.gui()
        patch = self.PATCH

        def integration(ordner, **k):
            if einbau:
                Path(ordner, "eboot.bin").write_bytes(patch)
                os.makedirs(os.path.join(ordner, "fakelib"), exist_ok=True)
                Path(ordner, "fakelib", "neu.sprx").write_bytes(b"neue Bibliothek")
            g._ampr_ordner_ist_kopie = True
            return ordner
        g._integration_anwenden = integration
        return g

    def lauf(self, quelle, g=None, **kw):
        g = g or self.gui()
        return g, g._mode_exfat_umpacken_strom(quelle, self.ziel, ziel="ffpfs", **kw)

    def _gelesen(self, pfad: str) -> "dict[str, bytes]":
        with sb.PfsBaum(pfad) as baum:
            dateien = {d.rel: b"".join(d.lesen()) for d in baum.dateien()}
            self.assertEqual("pfs", baum.art, "die Spieldateien liegen direkt im PFS, kein inneres Abbild")
            return dateien

    def test_aus_jeder_quelle_mit_zstd_pack(self) -> None:
        for quelle, kw in ((self.quelle, {}), (self.huelle, {"pfs": True}), (self.spiel, {"ordner": True})):
            with self.subTest(quelle=os.path.basename(quelle)):
                shutil.rmtree(self.ziel)
                os.makedirs(self.ziel)
                g, ok = self.lauf(quelle, **kw)
                self.assertTrue(ok, "\n".join(g._log_lines))
                namen = os.listdir(self.ziel)
                self.assertEqual([os.path.splitext(os.path.basename(quelle))[0] + ".ffpfs"], namen)
                dateien = self._gelesen(os.path.join(self.ziel, namen[0]))
                self.assertEqual(self.inhalt["eboot.bin"], dateien["eboot.bin"])
                self.assertEqual(NG_LIB, dateien["fakelib/libSceAmpr.sprx"])
                self.assertNotIn("Media/text.txt", dateien)                  # gepackt, Original weg
                self.assertIn("ampr_zstd-000.pak", dateien)
                self.assertIn("ampr_zstd.index", dateien)

    def test_dieselben_dateien_wie_im_exfat_ergebnis(self) -> None:
        g, ok = self.lauf(self.quelle)
        self.assertTrue(ok, "\n".join(g._log_lines))
        als_ffpfs = self._gelesen(os.path.join(self.ziel, "spiel.ffpfs"))
        ziel2 = os.path.join(self.tmp, "ziel2")
        os.makedirs(ziel2)
        g2 = self.gui()
        self.assertTrue(g2._mode_exfat_umpacken_strom(self.quelle, ziel2), "\n".join(g2._log_lines))
        with sb.ExfatBaum(os.path.join(ziel2, "spiel.exfat")) as b:
            als_exfat = {d.rel: b"".join(d.lesen()) for d in b.dateien()}
        self.assertEqual(sorted(als_exfat), sorted(als_ffpfs))
        for rel in als_exfat:
            if rel not in ("sce_sys/param.json", "sce_sys/param.json.alt"):
                self.assertEqual(als_exfat[rel], als_ffpfs[rel], rel)

    def test_ein_ordnerweg_baut_dieselbe_datei(self) -> None:
        """Der bisherige Weg (Ordner -> ``build_pfs`` flach) und der Strom ergeben **byteweise dieselbe** ``.ffpfs``."""
        from mkpfs import consts
        from mkpfs.pbar import Progress
        from mkpfs.pfs import build_pfs
        with mock.patch("mkpfs.pfs.time.time", return_value=1_700_000_000.0):     # die Zeit steckt im Kopf und in den Inodes
            g, ok = self.lauf(self.quelle)
            self.assertTrue(ok, "\n".join(g._log_lines))
            strom_datei = Path(self.ziel, "spiel.ffpfs")
            # derselbe Inhalt als Ordner: was der Strom geschrieben hat, wird ausgelesen und mit dem Ordnerweg neu gebaut
            ordner = os.path.join(self.tmp, "nachbau")
            for rel, daten in self._gelesen(str(strom_datei)).items():
                voll = os.path.join(ordner, *rel.split("/"))
                os.makedirs(os.path.dirname(voll), exist_ok=True)
                Path(voll).write_bytes(daten)
            nachbau = os.path.join(self.tmp, "nachbau.ffpfs")
            build_pfs(source_root=Path(ordner), output_path=Path(nachbau), block_size=65536,
                      pfs_version=consts.PFS_VERSION_PS5, inode_bits=32, case_insensitive=True, signed=False, compress=False,
                      threshold_gain=0, cpu_count=1, zlib_level=6, dry_run=False, verbose=False,
                      progress=Progress(enabled=False))
        self.assertEqual(Path(nachbau).read_bytes(), strom_datei.read_bytes())

    def test_ohne_pack_nur_einbau_und_ohne_jeden_einbau(self) -> None:
        for einbau in (True, False):
            for quelle, kw in ((self.quelle, {}), (self.huelle, {"pfs": True}), (self.spiel, {"ordner": True})):
                with self.subTest(einbau=einbau, quelle=os.path.basename(quelle)):
                    shutil.rmtree(self.ziel)
                    os.makedirs(self.ziel)
                    g, ok = self.lauf(quelle, self.gui_nur_einbau(einbau), **kw)
                    self.assertTrue(ok, "\n".join(g._log_lines))
                    dateien = self._gelesen(os.path.join(self.ziel, os.listdir(self.ziel)[0]))
                    erwartet = dict(self.inhalt)
                    if einbau:
                        erwartet["eboot.bin"] = self.PATCH
                        erwartet["fakelib/neu.sprx"] = b"neue Bibliothek"
                    for rel in ("sce_sys/param.json", "sce_sys/param.json.alt"):
                        dateien.pop(rel, None)
                        erwartet.pop(rel, None)
                    self.assertEqual(sorted(erwartet), sorted(dateien))
                    for rel, daten in erwartet.items():
                        self.assertEqual(daten, dateien[rel], rel)
                    self.assertFalse([r for r in dateien if z.ist_packname(r)], "es entsteht kein Pack")

    def test_flache_ffpfs_als_quelle_zur_ffpfsc_und_zurueck(self) -> None:
        """Etappe 12: ``.ffpfs`` (flach) -> ``.ffpfsc`` -> ``.ffpfs`` ohne Dump-Ordner; der Inhalt bleibt derselbe."""
        g, ok = self.lauf(self.quelle, self.gui_nur_einbau(False))
        self.assertTrue(ok, "\n".join(g._log_lines))
        flach = os.path.join(self.tmp, "flach.ffpfs")
        shutil.move(os.path.join(self.ziel, "spiel.ffpfs"), flach)
        ziel2 = os.path.join(self.tmp, "ziel2")
        os.makedirs(ziel2)
        g2 = self.gui_nur_einbau(False)
        self.assertTrue(g2._mode_exfat_umpacken_strom(flach, ziel2, pfs=True, ziel="ffpfsc"), "\n".join(g2._log_lines))
        with sb.PfsBaum(os.path.join(ziel2, "flach.ffpfsc")) as baum:
            als_container = {d.rel: b"".join(d.lesen()) for d in baum.dateien()}
            self.assertEqual("exfat", baum.art)
        self.assertEqual(self._gelesen(flach), als_container)
        ziel3 = os.path.join(self.tmp, "ziel3")
        os.makedirs(ziel3)
        g3 = self.gui_nur_einbau(False)
        self.assertTrue(g3._mode_exfat_umpacken_strom(os.path.join(ziel2, "flach.ffpfsc"), ziel3, pfs=True, ziel="ffpfs"),
                        "\n".join(g3._log_lines))
        self.assertEqual(self._gelesen(flach), self._gelesen(os.path.join(ziel3, "flach.ffpfs")))
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))

    def test_quelle_unveraendert_kein_rest(self) -> None:
        vorher = {p: (os.path.getsize(p), os.stat(p).st_mtime_ns) for p in (self.quelle, self.huelle)}
        for quelle, kw in ((self.quelle, {}), (self.huelle, {"pfs": True})):
            shutil.rmtree(self.ziel)
            os.makedirs(self.ziel)
            g, ok = self.lauf(quelle, **kw)
            self.assertTrue(ok, "\n".join(g._log_lines))
            self.assertEqual(1, len(os.listdir(self.ziel)), os.listdir(self.ziel))
        self.assertEqual(vorher, {p: (os.path.getsize(p), os.stat(p).st_mtime_ns) for p in (self.quelle, self.huelle)})
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))

    def test_ersetzt_ein_vorhandenes_ziel_erst_am_ende(self) -> None:
        altes = os.path.join(self.ziel, "spiel.ffpfs")
        Path(altes).write_bytes(b"alt")
        g = self.gui()
        echt = g._verify_exfat_liste
        gesehen: list[bytes] = []

        def pruefen(pfad, strom, mkpfs_ordner=""):
            gesehen.append(Path(altes).read_bytes())                  # waehrend der Rueckleseprobe
            self.assertTrue(pfad.endswith(".ffpfs.teil"), pfad)
            return echt(pfad, strom, mkpfs_ordner)
        g._verify_exfat_liste = pruefen
        self.assertTrue(g._mode_exfat_umpacken_strom(self.quelle, self.ziel, ziel="ffpfs"), "\n".join(g._log_lines))
        self.assertEqual([b"alt"], gesehen, "das alte Ziel bleibt bis zur Uebernahme unberuehrt")
        self.assertNotEqual(b"alt", Path(altes).read_bytes())

    def test_abbruch_laesst_nichts_zurueck(self) -> None:
        g = self.gui()

        def abbrechen(prozent, phase):
            g.is_running = False
        g._ampr_pack_fortschritt = abbrechen
        self.assertFalse(g._mode_exfat_umpacken_strom(self.quelle, self.ziel, ziel="ffpfs"))
        self.assertEqual([], os.listdir(self.ziel))
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))

    def test_abbruch_beim_schreiben_laesst_nichts_zurueck(self) -> None:
        g = self.gui()
        echt = APP.abbild_strom.ffpfs_schreiben

        def abbrechen(eintraege, ziel, **kw):
            g.is_running = False
            return echt(eintraege, ziel, **kw)
        with mock.patch.object(APP.abbild_strom, "ffpfs_schreiben", side_effect=abbrechen):
            self.assertFalse(g._mode_exfat_umpacken_strom(self.quelle, self.ziel, ziel="ffpfs"))
        self.assertEqual([], os.listdir(self.ziel))
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))

    def test_quelle_aendert_sich_waehrend_des_laufs(self) -> None:
        kopie = os.path.join(self.tmp, "kopie.exfat")
        shutil.copyfile(self.quelle, kopie)
        g = self.gui()
        urspruenglich = g._integration_anwenden

        def integration(ordner, **k):
            erg = urspruenglich(ordner, **k)
            with open(kopie, "ab") as fh:
                fh.write(b"\0" * 512)
            return erg
        g._integration_anwenden = integration
        self.assertFalse(g._mode_exfat_umpacken_strom(kopie, self.ziel, ziel="ffpfs"))
        self.assertEqual([], os.listdir(self.ziel))

    def test_fehler_beim_schreiben_laesst_nichts_zurueck(self) -> None:
        g = self.gui()
        with mock.patch.object(APP.abbild_strom, "ffpfs_schreiben", side_effect=OSError("Platte voll")):
            self.assertFalse(g._mode_exfat_umpacken_strom(self.quelle, self.ziel, ziel="ffpfs"))
        self.assertEqual([], os.listdir(self.ziel))
        self.assertTrue(any("Platte voll" in z_ for z_ in g._log_lines), "\n".join(g._log_lines))

    def test_ein_beschaedigtes_ergebnis_wird_nicht_uebernommen(self) -> None:
        """Die Rueckleseprobe liest das flache PFS mit dem Lesebaum: Stimmt etwas nicht, bleibt das Ziel leer."""
        g = self.gui()
        g.mkpfs_verify = "aus"                                         # nur die Rueckleseprobe, nicht die ganze Pruefung
        echt = APP.abbild_strom.ffpfs_schreiben
        self_inhalt = self.inhalt

        def beschaedigt(eintraege, ziel, **kw):
            erg = echt(eintraege, ziel, **kw)
            daten = bytearray(Path(ziel).read_bytes())
            kopf = daten.find(self_inhalt["eboot.bin"])                # die eboot.bin: gleiche Groesse, anderer Inhalt
            self.assertGreater(kopf, 0)
            daten[kopf + 100] ^= 0xFF
            Path(ziel).write_bytes(bytes(daten))
            return erg
        with mock.patch.object(APP.abbild_strom, "ffpfs_schreiben", side_effect=beschaedigt):
            self.assertFalse(g._mode_exfat_umpacken_strom(self.quelle, self.ziel, ziel="ffpfs"))
        self.assertEqual([], os.listdir(self.ziel))
        self.assertTrue(any("unvollständig" in z_ or "incomplete" in z_ for z_ in g._log_lines), "\n".join(g._log_lines))

    def test_stufe_schnell_und_voll_pruefen_das_ganze_abbild_aus_prueft_nicht(self) -> None:
        echt = APP.abbild_strom.pfs_pruefen
        for stufe, erwartet in ((None, 1), ("schnell", 1), ("voll", 1), ("aus", 0)):
            with self.subTest(stufe=stufe):
                shutil.rmtree(self.ziel)
                os.makedirs(self.ziel)
                g = self.gui()
                if stufe is not None:
                    g.mkpfs_verify = stufe
                aufrufe: list[str] = []

                def pruefen(pfad, **kw):
                    aufrufe.append(pfad)
                    return echt(pfad, **kw)
                with mock.patch.object(APP.abbild_strom, "pfs_pruefen", side_effect=pruefen):
                    self.assertTrue(g._mode_exfat_umpacken_strom(self.quelle, self.ziel, ziel="ffpfs"), "\n".join(g._log_lines))
                self.assertEqual(erwartet, len(aufrufe))

    def test_namen_die_ein_flaches_pfs_nicht_fasst_werden_vorab_gemeldet(self) -> None:
        """Nicht-ASCII-Namen fasst kein PFS; das sagt der Lauf vor der ersten Stunde Arbeit, nicht beim Schreiben."""
        os.makedirs(os.path.join(self.spiel, "data"), exist_ok=True)
        Path(self.spiel, "data", "ü.bin").write_bytes(b"x")
        g, ok = self.lauf(self.spiel, ordner=True)
        self.assertFalse(ok)
        self.assertEqual([], os.listdir(self.ziel))
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))

    def test_leere_verzeichnisse_gibt_es_im_flachen_pfs_nicht(self) -> None:
        """Wie im bisherigen Weg (``mkpfs pack folder --raw``): Ein flaches PFS kennt keine leeren Verzeichnisse."""
        os.makedirs(os.path.join(self.spiel, "savedata_leer"))
        g, ok = self.lauf(self.spiel, self.gui_nur_einbau(False), ordner=True)
        self.assertTrue(ok, "\n".join(g._log_lines))
        with sb.PfsBaum(os.path.join(self.ziel, os.listdir(self.ziel)[0])) as baum:
            baum.dateien()
            self.assertNotIn("savedata_leer", baum.ordner())


@unittest.skipUnless(z.verfuegbar(), "zstandard fehlt")
class FfpkgAusgabeTests(_Grundlage):
    """Etappe 13: Ergebnis als ``.ffpkg`` (UFS2) im Strom - eigener Schreiber, ohne UFS2Tool, ohne Administratorrechte."""

    PATCH = b"\x7fELF" + b"EINGEBAUT"

    def setUp(self) -> None:
        super().setUp()
        from ps5_validator.utils import ufs2_schreiber
        from mkpfs import consts
        from mkpfs.pfs import build_pfs_stream_single_file
        os.makedirs(os.path.join(self.spiel, "savedata_leer"))
        with open(self.quelle, "wb") as fh:                                  # die .exfat jetzt mit dem leeren Verzeichnis
            for stueck in iter_exfat_image(Path(self.spiel)):
                fh.write(stueck)
        self.huelle = os.path.join(self.tmp, "huelle.ffpfsc")
        build_pfs_stream_single_file(
            source_file=Path(self.quelle), output_path=Path(self.huelle), block_size=65536,
            pfs_version=consts.PFS_VERSION_PS5, case_insensitive=True, zlib_level=6, threshold_gain=0, min_file_gain=0,
            min_compress_size=0, cpu_count=1, compress=True)
        # eine .ffpkg als Quelle - ebenfalls mit dem eigenen Schreiber gebaut, kein UFS2Tool noetig
        self.ffpkg = os.path.join(self.tmp, "quelle.ffpkg")
        inhalte = dict(self.inhalt)
        plan = ufs2_schreiber.planen(
            [(rel, len(d), (lambda d=d: iter([d]))) for rel, d in inhalte.items()], ["savedata_leer"],
            profil=ufs2_schreiber.profil_aus_newfs(__import__("ps5_validator.utils.ffpkg_support",
                                                              fromlist=["x"]).primary_newfs_profile()))
        plan.schreiben(self.ffpkg)

    def gui(self, **kw):
        g = _gui(self.tmp, **kw)
        g._resolve_pack_profile = lambda mode, groesse: {
            "profile": "t", "level": 3, "cpu": 1, "cores": 1, "block_size": 65536, "size_gb": 0.0, "verify_after": True}
        g._format_phase_status = lambda text, **k: text
        # ohne Administratorrechte und ohne UFS2Tool: Der Strom darf beides nicht brauchen
        g._extract_ufs2tool = lambda *a, **k: (_ for _ in ()).throw(AssertionError("UFS2Tool wurde gebraucht"))
        return g

    def gui_nur_einbau(self, einbau: bool = True):
        g = self.gui()
        patch = self.PATCH

        def integration(ordner, **k):
            if einbau:
                Path(ordner, "eboot.bin").write_bytes(patch)
                os.makedirs(os.path.join(ordner, "fakelib"), exist_ok=True)
                Path(ordner, "fakelib", "neu.sprx").write_bytes(b"neue Bibliothek")
            g._ampr_ordner_ist_kopie = True
            return ordner
        g._integration_anwenden = integration
        return g

    def lauf(self, quelle, g=None, **kw):
        g = g or self.gui()
        with mock.patch.object(APP, "_is_admin", return_value=False):
            return g, g._mode_exfat_umpacken_strom(quelle, self.ziel, ziel="ffpkg", **kw)

    def _gelesen(self, pfad: str) -> "tuple[dict[str, bytes], list[str]]":
        with sb.Ufs2Baum(pfad) as baum:
            return {d.rel: b"".join(d.lesen()) for d in baum.dateien()}, baum.ordner()

    def test_aus_jeder_quelle_mit_zstd_pack(self) -> None:
        for quelle, kw in ((self.quelle, {}), (self.huelle, {"pfs": True}), (self.spiel, {"ordner": True}),
                           (self.ffpkg, {"ufs2": True})):
            with self.subTest(quelle=os.path.basename(quelle)):
                shutil.rmtree(self.ziel)
                os.makedirs(self.ziel)
                g, ok = self.lauf(quelle, **kw)
                self.assertTrue(ok, "\n".join(g._log_lines))
                namen = os.listdir(self.ziel)
                self.assertEqual([os.path.splitext(os.path.basename(quelle.rstrip("/\\")))[0] + ".ffpkg"], namen)
                dateien, ordner = self._gelesen(os.path.join(self.ziel, namen[0]))
                self.assertEqual(self.inhalt["eboot.bin"], dateien["eboot.bin"])
                self.assertEqual(NG_LIB, dateien["fakelib/libSceAmpr.sprx"])
                self.assertNotIn("Media/text.txt", dateien)                  # gepackt, Original weg
                self.assertIn("ampr_zstd-000.pak", dateien)
                self.assertIn("ampr_zstd.index", dateien)
                self.assertIn("savedata_leer", ordner, "ein leeres Verzeichnis bleibt")

    def test_ohne_pack_nur_einbau_und_ohne_jeden_einbau(self) -> None:
        for einbau in (True, False):
            for quelle, kw in ((self.quelle, {}), (self.huelle, {"pfs": True}), (self.spiel, {"ordner": True}),
                               (self.ffpkg, {"ufs2": True})):
                with self.subTest(einbau=einbau, quelle=os.path.basename(quelle)):
                    shutil.rmtree(self.ziel)
                    os.makedirs(self.ziel)
                    g, ok = self.lauf(quelle, self.gui_nur_einbau(einbau), **kw)
                    self.assertTrue(ok, "\n".join(g._log_lines))
                    dateien, ordner = self._gelesen(os.path.join(self.ziel, os.listdir(self.ziel)[0]))
                    erwartet = dict(self.inhalt)
                    if einbau:
                        erwartet["eboot.bin"] = self.PATCH
                        erwartet["fakelib/neu.sprx"] = b"neue Bibliothek"
                    for rel in ("sce_sys/param.json", "sce_sys/param.json.alt"):
                        dateien.pop(rel, None)
                        erwartet.pop(rel, None)
                    self.assertEqual(sorted(erwartet), sorted(dateien))
                    for rel, daten in erwartet.items():
                        self.assertEqual(daten, dateien[rel], rel)
                    self.assertIn("savedata_leer", ordner)
                    self.assertFalse([r for r in dateien if z.ist_packname(r)], "es entsteht kein Pack")

    def test_dasselbe_abbild_wie_der_schreiber_aus_der_liste(self) -> None:
        """Der Strom aendert nichts am Ergebnis: Aus den Dateien, die er geschrieben hat, baut der Schreiber (mit festem Zeitstempel) dasselbe."""
        from ps5_validator.utils import ffpkg_support as ffs
        from ps5_validator.utils import ufs2_schreiber
        fest = {"zeit": 1_700_000_000, "fs_id": (5, 6)}
        echt = ufs2_schreiber.planen

        def festgelegt(*a, **k):
            return echt(*a, **dict(k, **fest))
        with mock.patch.object(ufs2_schreiber, "planen", side_effect=festgelegt):
            g, ok = self.lauf(self.quelle, self.gui_nur_einbau(False))
        self.assertTrue(ok, "\n".join(g._log_lines))
        pfad = os.path.join(self.ziel, "spiel.ffpkg")
        dateien, ordner = self._gelesen(pfad)
        plan = echt([(rel, len(d), (lambda d=d: iter([d]))) for rel, d in dateien.items()], ordner,
                    profil=ufs2_schreiber.profil_aus_newfs(ffs.primary_newfs_profile()), **fest)
        daneben = os.path.join(self.tmp, "daneben.ffpkg")
        plan.schreiben(daneben)
        self.assertEqual(Path(daneben).read_bytes(), Path(pfad).read_bytes())

    def test_quelle_unveraendert_kein_rest(self) -> None:
        vorher = {p: (os.path.getsize(p), os.stat(p).st_mtime_ns) for p in (self.quelle, self.huelle, self.ffpkg)}
        for quelle, kw in ((self.quelle, {}), (self.huelle, {"pfs": True}), (self.ffpkg, {"ufs2": True})):
            shutil.rmtree(self.ziel)
            os.makedirs(self.ziel)
            g, ok = self.lauf(quelle, **kw)
            self.assertTrue(ok, "\n".join(g._log_lines))
            self.assertEqual(1, len(os.listdir(self.ziel)), os.listdir(self.ziel))
        self.assertEqual(vorher, {p: (os.path.getsize(p), os.stat(p).st_mtime_ns) for p in (self.quelle, self.huelle, self.ffpkg)})
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))

    def test_ersetzt_ein_vorhandenes_ziel_erst_am_ende(self) -> None:
        altes = os.path.join(self.ziel, "spiel.ffpkg")
        Path(altes).write_bytes(b"alt")
        g = self.gui()
        echt = g._verify_exfat_liste
        gesehen: list[bytes] = []

        def pruefen(pfad, strom, mkpfs_ordner=""):
            gesehen.append(Path(altes).read_bytes())
            self.assertTrue(pfad.endswith(".ffpkg.teil"), pfad)
            return echt(pfad, strom, mkpfs_ordner)
        g._verify_exfat_liste = pruefen
        g, ok = self.lauf(self.quelle, g)
        self.assertTrue(ok, "\n".join(g._log_lines))
        self.assertEqual([b"alt"], gesehen, "das alte Ziel bleibt bis zur Uebernahme unberuehrt")
        self.assertNotEqual(b"alt", Path(altes).read_bytes())

    def test_abbruch_laesst_nichts_zurueck(self) -> None:
        g = self.gui()

        def abbrechen(prozent, phase):
            g.is_running = False
        g._ampr_pack_fortschritt = abbrechen
        g, ok = self.lauf(self.quelle, g)
        self.assertFalse(ok)
        self.assertEqual([], os.listdir(self.ziel))
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))

    def test_abbruch_beim_schreiben_laesst_nichts_zurueck(self) -> None:
        g = self.gui()
        echt = APP.abbild_strom.ufs2_schreiben

        def abbrechen(plan, ziel, **kw):
            g.is_running = False
            return echt(plan, ziel, **kw)
        with mock.patch.object(APP.abbild_strom, "ufs2_schreiben", side_effect=abbrechen):
            g, ok = self.lauf(self.quelle, g)
        self.assertFalse(ok)
        self.assertEqual([], os.listdir(self.ziel))
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))

    def test_quelle_aendert_sich_waehrend_des_laufs(self) -> None:
        kopie = os.path.join(self.tmp, "kopie.exfat")
        shutil.copyfile(self.quelle, kopie)
        g = self.gui()
        urspruenglich = g._integration_anwenden

        def integration(ordner, **k):
            erg = urspruenglich(ordner, **k)
            with open(kopie, "ab") as fh:
                fh.write(b"\0" * 512)
            return erg
        g._integration_anwenden = integration
        g, ok = self.lauf(kopie, g)
        self.assertFalse(ok)
        self.assertEqual([], os.listdir(self.ziel))

    def test_fehler_beim_schreiben_laesst_nichts_zurueck(self) -> None:
        g = self.gui()
        with mock.patch.object(APP.abbild_strom, "ufs2_schreiben", side_effect=OSError("Platte voll")):
            g, ok = self.lauf(self.quelle, g)
        self.assertFalse(ok)
        self.assertEqual([], os.listdir(self.ziel))
        self.assertTrue(any("Platte voll" in z_ for z_ in g._log_lines), "\n".join(g._log_lines))

    def test_ein_beschaedigtes_ergebnis_wird_nicht_uebernommen(self) -> None:
        g = self.gui()
        echt = APP.abbild_strom.ufs2_schreiben
        inhalt = self.inhalt

        def beschaedigt(plan, ziel, **kw):
            erg = echt(plan, ziel, **kw)
            daten = bytearray(Path(ziel).read_bytes())
            kopf = daten.find(inhalt["eboot.bin"])                         # gleiche Groesse, anderer Inhalt
            self.assertGreater(kopf, 0)
            daten[kopf + 100] ^= 0xFF
            Path(ziel).write_bytes(bytes(daten))
            return erg
        with mock.patch.object(APP.abbild_strom, "ufs2_schreiben", side_effect=beschaedigt):
            g, ok = self.lauf(self.quelle, g)
        self.assertFalse(ok)
        self.assertEqual([], os.listdir(self.ziel))
        self.assertTrue(any("unvollständig" in z_ or "incomplete" in z_ for z_ in g._log_lines), "\n".join(g._log_lines))

    def test_stufe_voll_prueft_zusaetzlich_mit_ufs2tool_wo_es_geht(self) -> None:
        for stufe, moeglich, erwartet in (("voll", True, 1), ("voll", False, 0), ("schnell", True, 0), ("aus", True, 0)):
            with self.subTest(stufe=stufe, moeglich=moeglich):
                shutil.rmtree(self.ziel)
                os.makedirs(self.ziel)
                g = self.gui()
                g.mkpfs_verify = stufe
                g._ufs2tool_pruefung_moeglich = lambda m=moeglich: m
                aufrufe: list[str] = []
                g._validate_ffpkg_artifact = lambda pfad, **kw: aufrufe.append(pfad) or {"ok": True, "detail": "ok"}
                g, ok = self.lauf(self.quelle, g)
                self.assertTrue(ok, "\n".join(g._log_lines))
                self.assertEqual(erwartet, len(aufrufe))

    def test_eine_nicht_bestandene_ufs2tool_pruefung_verwirft_das_ergebnis(self) -> None:
        g = self.gui()
        g.mkpfs_verify = "voll"
        g._ufs2tool_pruefung_moeglich = lambda: True
        g._validate_ffpkg_artifact = lambda pfad, **kw: {"ok": False, "detail": "fsck: kaputt"}
        g, ok = self.lauf(self.quelle, g)
        self.assertFalse(ok)
        self.assertEqual([], os.listdir(self.ziel))
        self.assertTrue(any("fsck: kaputt" in z_ for z_ in g._log_lines), "\n".join(g._log_lines))

    def test_namen_die_ufs2_nicht_fasst_bleiben_beim_alten_weg(self) -> None:
        Path(self.spiel, "data").mkdir(exist_ok=True)
        Path(self.spiel, "data", "ü.bin").write_bytes(b"x")
        g, ergebnis = self.lauf(self.spiel, ordner=True)
        self.assertIsNone(ergebnis)
        self.assertEqual([], os.listdir(self.ziel))
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))
        self.assertTrue(any("UFS2" in z_ for z_ in g._log_lines), "\n".join(g._log_lines))


@unittest.skipUnless(z.verfuegbar(), "zstandard fehlt")
class DurchsichtBefundeTests(_Grundlage):
    """Befunde der unabhaengigen Durchsicht vom 13.11.2026: jeder hat hier seinen Test."""

    def gui(self, **kw):
        g = _gui(self.tmp, **kw)
        g._resolve_pack_profile = lambda mode, groesse: {
            "profile": "t", "level": 3, "cpu": 1, "cores": 1, "block_size": 65536, "size_gb": 0.0, "verify_after": True}
        g._format_phase_status = lambda text, **k: text
        return g

    def _ohne_log(self, g, *teile: str) -> None:
        text = "\n".join(g._log_lines)
        for teil in teile:
            self.assertNotIn(teil, text)

    # -- leere Verzeichnisse ---------------------------------------------------------------------------------------------------
    def _leere_ordner_anlegen(self) -> None:
        for leer in ("savedata_leer", "data/cache"):
            os.makedirs(os.path.join(self.spiel, *leer.split("/")), exist_ok=True)
        with open(self.quelle, "wb") as fh:
            for stueck in iter_exfat_image(Path(self.spiel)):
                fh.write(stueck)

    def test_leere_verzeichnisse_bleiben_erhalten_exfat_und_ordner_als_quelle(self) -> None:
        self._leere_ordner_anlegen()
        for quelle, kw in ((self.quelle, {}), (self.spiel, {"ordner": True})):
            for ziel in ("exfat", "ffpfsc"):
                with self.subTest(quelle=os.path.basename(quelle), ziel=ziel):
                    shutil.rmtree(self.ziel)
                    os.makedirs(self.ziel)
                    g = self.gui()
                    self.assertTrue(g._mode_exfat_umpacken_strom(quelle, self.ziel, ziel=ziel, **kw), "\n".join(g._log_lines))
                    ergebnis = os.path.join(self.ziel, os.listdir(self.ziel)[0])
                    with (sb.PfsBaum(ergebnis) if ziel == "ffpfsc" else sb.ExfatBaum(ergebnis)) as neu:
                        neu.dateien()
                        ordner = set(neu.ordner())
                    self.assertIn("savedata_leer", ordner)
                    self.assertIn("data/cache", ordner)
                    self.assertNotIn("Media", ordner, "ein Ordner, der nur gepackte Originale hielt, faellt mit weg")

    # -- eigenes Packprofil ----------------------------------------------------------------------------------------------------
    def test_das_profil_neben_dem_dump_ordner_gilt(self) -> None:
        profil = self.spiel + "_ampr_pack.toml"
        Path(profil).write_text('[pack]\ndefault_action = "compress"\n\n[[rule]]\naction = "loose"\ninclude = "Media/**"\n',
                                encoding="utf-8")
        g = self.gui()
        g._ampr_eigenes_profil_uebernehmen = GUI._ampr_eigenes_profil_uebernehmen.__get__(g)
        urspruenglich = g._integration_anwenden

        def integration(ordner, **k):
            g._ampr_quelle_original = k.get("herkunft", "")        # wie das echte ``_integration_anwenden``
            return urspruenglich(ordner, **k)
        g._integration_anwenden = integration
        self.assertTrue(g._mode_exfat_umpacken_strom(self.spiel, self.ziel, ordner=True), "\n".join(g._log_lines))
        self.assertTrue(any("ampr_pack" in z_ or "Profil" in z_ or "profile" in z_ for z_ in g._log_lines), "\n".join(g._log_lines))
        with sb.ExfatBaum(os.path.join(self.ziel, "spiel.exfat")) as neu:
            dateien = neu.suchen()
            self.assertIn("Media/text.txt", dateien, "laut Profil bleibt Media lose - nicht in das Pack")
            self.assertEqual(self.inhalt["Media/zufall.bin"], b"".join(dateien["Media/zufall.bin"].lesen()))

    def test_ohne_profil_wird_wie_bisher_gepackt(self) -> None:
        g = self.gui()
        g._ampr_eigenes_profil_uebernehmen = GUI._ampr_eigenes_profil_uebernehmen.__get__(g)
        g._ampr_quelle_original = ""
        self.assertTrue(g._mode_exfat_umpacken_strom(self.quelle, self.ziel), "\n".join(g._log_lines))
        with sb.ExfatBaum(os.path.join(self.ziel, "spiel.exfat")) as neu:
            self.assertNotIn("Media/text.txt", neu.suchen())

    # -- Fehler und Abbruch vor dem Schreiben ----------------------------------------------------------------------------------
    def test_abbruch_in_der_ueberlagerung_ist_keine_fehlermeldung(self) -> None:
        g = self.gui()
        with mock.patch.object(APP.abbild_strom, "schatten_fuellen", side_effect=z.ZstdPackFehler("ampr_pack.abgebrochen")):
            self.assertFalse(g._mode_exfat_umpacken_strom(self.quelle, self.ziel))
        self._ohne_log(g, "ampr_pack.abgebrochen", "ampr_zstd.fehlgeschlagen")
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))

    def test_ein_zstdfehler_kommt_uebersetzt_ins_protokoll(self) -> None:
        g = self.gui()
        g._t = lambda schluessel, **k: "T[%s]" % schluessel + "".join(" %s=%s" % kv for kv in sorted(k.items()))
        with mock.patch.object(APP.abbild_strom, "schatten_fuellen", side_effect=z.ZstdPackFehler("ampr_zstd.ausgabe_belegt")):
            self.assertFalse(g._mode_exfat_umpacken_strom(self.quelle, self.ziel))
        text = "\n".join(g._log_lines)
        self.assertIn("T[ampr_zstd.fehlgeschlagen] error=T[ampr_zstd.ausgabe_belegt]", text)

    def test_ein_lesefehler_der_quelle_wird_gemeldet_statt_durchzuschlagen(self) -> None:
        g = self.gui()
        with mock.patch.object(APP.abbild_strom, "schatten_fuellen", side_effect=sb.BaumFehler("Block kaputt")):
            self.assertFalse(g._mode_exfat_umpacken_strom(self.quelle, self.ziel))
        self.assertTrue(any("Block kaputt" in z_ for z_ in g._log_lines), "\n".join(g._log_lines))
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))

    def test_abbruch_im_strom_ist_keine_fehlermeldung(self) -> None:
        g = self.gui()
        echt = APP.abbild_strom.abbild_strom

        def abbrechend(*a, **k):
            yield next(iter(echt(*a, **k)))
            raise z.ZstdPackFehler("ampr_pack.abgebrochen")
        with mock.patch.object(APP.abbild_strom, "abbild_strom", abbrechend):
            self.assertFalse(g._mode_exfat_umpacken_strom(self.quelle, self.ziel))
            self.assertFalse(g._mode_exfat_umpacken_strom(self.quelle, self.ziel, ziel="ffpfsc"))
        self._ohne_log(g, "ampr_pack.abgebrochen")
        self.assertEqual([], os.listdir(self.ziel))

    # -- eboot.bin ---------------------------------------------------------------------------------------------------------------
    def test_ohne_eboot_bricht_der_lauf_vor_der_param_json_ab(self) -> None:
        for rel in list(self.inhalt):
            if rel.lower() == "eboot.bin":
                os.remove(os.path.join(self.spiel, rel))
        with open(self.quelle, "wb") as fh:
            for stueck in iter_exfat_image(Path(self.spiel)):
                fh.write(stueck)
        g = self.gui()
        g._ensure_param_json = lambda ordner: (_ for _ in ()).throw(AssertionError("param.json vor der eboot-Pruefung"))
        self.assertFalse(g._mode_exfat_umpacken_strom(self.quelle, self.ziel))
        self.assertTrue(any("eboot.bin" in z_ for z_ in g._log_lines), "\n".join(g._log_lines))
        self.assertEqual([], os.listdir(self.ziel))

    # -- Bauform ------------------------------------------------------------------------------------------------------------------
    def test_die_bauform_pfs_bekommt_den_bisherigen_weg(self) -> None:
        g = GUI.__new__(GUI)
        g._strom_weg_gewaehlt = lambda: True
        self.assertTrue(g._strom_nach_container_gewaehlt())                    # Vorgabe: exFAT
        g.bauform = APP.BAUFORM_EXFAT
        self.assertTrue(g._strom_nach_container_gewaehlt())
        g.bauform = APP.BAUFORM_PFS
        self.assertFalse(g._strom_nach_container_gewaehlt())
        g._strom_weg_gewaehlt = lambda: False
        g.bauform = APP.BAUFORM_EXFAT
        self.assertFalse(g._strom_nach_container_gewaehlt())

    def test_bauform_pfs_nimmt_die_einhaengestellen_nicht(self) -> None:
        for aufruf in (lambda g: g._mode_abbild_zu_ffpfs("a.exfat", "d", quelle="exfat", uncompressed=False),
                       lambda g: g._mode_abbild_zu_ffpfs("a.ffpfsc", "d", quelle="ffpfsc", uncompressed=False),
                       lambda g: g._mode_pack_folder(self.spiel, "d")):
            g = GUI.__new__(GUI)
            aufrufe: list[tuple] = []
            g._strom_weg_gewaehlt = lambda: True
            g.bauform = APP.BAUFORM_PFS
            g._mode_exfat_umpacken_strom = lambda *a, **k: aufrufe.append(a) or "strom"
            g._ausgabe_stamm = lambda *a, **k: "x"
            g._mkdtemp = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("alter weg"))
            g._integration_anwenden = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("alter weg"))
            g._integration_erledigt = False
            with self.assertRaises(RuntimeError):
                aufruf(g)
            self.assertEqual([], aufrufe)

    def test_platzbedarf_fuer_container_bei_bauform_pfs_nicht_als_strom(self) -> None:
        g = GUI.__new__(GUI)
        g._strom_weg_gewaehlt = lambda: True
        g.bauform = APP.BAUFORM_PFS
        g._quellgroesse_ermitteln = lambda src: 150 * 1024 ** 3
        g._estimate_unpack_space_requirement = lambda src: None
        g._integration_gewuenscht = lambda: True
        g._umhuellt_neu_packen = False
        self.assertGreater(g._platzbedarf_je_quelle("spiel.exfat", "ffpfsc")[0], 150 * 1024 ** 3)

    # -- zstd-Pruefung im Strom ---------------------------------------------------------------------------------------------------
    def _pruefen_argument(self, voll: bool, ziel: str = "exfat"):
        g = self.gui()
        g.einstellungen["ampr_voll_pruefen"] = voll
        gesehen: list = []
        echt = APP.abbild_strom.abbild_strom

        def beobachtet(*a, **k):
            gesehen.append(k.get("pruefen"))
            return echt(*a, **k)
        with mock.patch.object(APP.abbild_strom, "abbild_strom", beobachtet):
            self.assertTrue(g._mode_exfat_umpacken_strom(self.quelle, self.ziel, ziel=ziel), "\n".join(g._log_lines))
        return gesehen, g

    def test_vollstaendige_pruefung_entpackt_jeden_chunk(self) -> None:
        gesehen, g = self._pruefen_argument(True)
        self.assertEqual([True], gesehen)
        self.assertTrue(any("vollständig" in z_ or "full" in z_.lower() or "voll" in z_.lower() for z_ in g._log_lines),
                        "\n".join(g._log_lines))

    def test_ohne_den_schalter_eine_stichprobe(self) -> None:
        gesehen, g = self._pruefen_argument(False, ziel="ffpfsc")
        self.assertEqual(1, len(gesehen))
        self.assertIsInstance(gesehen[0], frozenset)
        self.assertTrue(gesehen[0])
        self.assertTrue(any("Stichprobe" in z_ or "sample" in z_.lower() for z_ in g._log_lines), "\n".join(g._log_lines))

    def test_ein_falsch_verdichtetes_pack_verwirft_das_ergebnis(self) -> None:
        g = self.gui()
        g.einstellungen["ampr_voll_pruefen"] = True
        echt = z.chunk_entpacken

        def verfaelscht(codec, gespeichert, erwartet):
            daten = bytearray(echt(codec, gespeichert, erwartet))
            daten[0] ^= 1
            return bytes(daten)
        with mock.patch.object(z, "chunk_entpacken", verfaelscht):
            self.assertFalse(g._mode_exfat_umpacken_strom(self.quelle, self.ziel))
            self.assertFalse(g._mode_exfat_umpacken_strom(self.quelle, self.ziel, ziel="ffpfsc"))
        self.assertEqual([], os.listdir(self.ziel))
        self.assertTrue(any("inhalt_anders" in z_ or "Inhalt" in z_ or "content" in z_.lower() for z_ in g._log_lines),
                        "\n".join(g._log_lines))

    # -- Warten auf einen frueheren MkPFS-Lauf -----------------------------------------------------------------------------------
    def test_der_container_wartet_auf_einen_abgebrochenen_mkpfs_lauf(self) -> None:
        g = self.gui()
        aufrufe: list[str] = []
        g._wait_for_pending_mkpfs_background = lambda ziel="", **k: aufrufe.append(ziel) or True
        self.assertTrue(g._mode_exfat_umpacken_strom(self.quelle, self.ziel, ziel="ffpfsc"), "\n".join(g._log_lines))
        self.assertEqual(1, len(aufrufe))
        self.assertTrue(aufrufe[0].endswith("spiel.ffpfsc"), aufrufe[0])

    def test_wird_das_warten_abgebrochen_beginnt_nichts(self) -> None:
        g = self.gui()
        g._wait_for_pending_mkpfs_background = lambda ziel="", **k: False
        self.assertFalse(g._mode_exfat_umpacken_strom(self.quelle, self.ziel, ziel="ffpfsc"))
        self.assertEqual([], os.listdir(self.ziel))


class NurEinbauTests(_Grundlage):
    """Etappe 9: Einbau **ohne** zstd-Pack (Backport, Fake-Signatur, DLC EMU, AMPR normal) und Umbau ganz ohne Einbau - im Strom.

    Der Einbau aendert nur wenige Dateien im Ueberlagerungsordner; alles andere kommt unveraendert aus der Quelle. Es gibt kein Pack
    (``_strom_plan`` bleibt leer), das Abbild entsteht aus der Ansicht.
    """

    PATCH = b"\x7fELF" + b"EINGEBAUT"

    def setUp(self) -> None:
        super().setUp()
        os.makedirs(os.path.join(self.spiel, "savedata_leer"))
        with open(self.quelle, "wb") as fh:                                  # die .exfat jetzt mit dem leeren Verzeichnis
            for stueck in iter_exfat_image(Path(self.spiel)):
                fh.write(stueck)
        from mkpfs import consts
        from mkpfs.pfs import build_pfs_stream_single_file
        self.huelle = os.path.join(self.tmp, "huelle.ffpfsc")
        build_pfs_stream_single_file(
            source_file=Path(self.quelle), output_path=Path(self.huelle), block_size=65536,
            pfs_version=consts.PFS_VERSION_PS5, case_insensitive=True, zlib_level=6, threshold_gain=0, min_file_gain=0,
            min_compress_size=0, cpu_count=1, compress=True)

    def gui(self, einbau: bool = True):
        g = _gui(self.tmp)
        g._resolve_pack_profile = lambda mode, groesse: {
            "profile": "t", "level": 3, "cpu": 1, "cores": 1, "block_size": 65536, "size_gb": 0.0, "verify_after": True}
        g._format_phase_status = lambda text, **k: text
        patch = self.PATCH

        def integration(ordner, **k):
            if einbau:
                Path(ordner, "eboot.bin").write_bytes(patch)                  # wie der Backport: Programmdatei ersetzt
                os.makedirs(os.path.join(ordner, "fakelib"), exist_ok=True)
                Path(ordner, "fakelib", "neu.sprx").write_bytes(b"neue Bibliothek")
            g._ampr_ordner_ist_kopie = True
            return ordner
        g._integration_anwenden = integration
        return g

    def _erwartet(self, einbau: bool) -> dict[str, bytes]:
        erwartet = dict(self.inhalt)
        if einbau:
            erwartet["eboot.bin"] = self.PATCH
            erwartet["fakelib/neu.sprx"] = b"neue Bibliothek"
        return erwartet

    def _gelesen(self, pfad: str, ziel: str) -> tuple[dict[str, bytes], list[str]]:
        with (sb.PfsBaum(pfad) if ziel == "ffpfsc" else sb.ExfatBaum(pfad)) as baum:
            dateien = {d.rel: b"".join(d.lesen()) for d in baum.dateien()}
            return dateien, baum.ordner()

    def _pruefen(self, g, ergebnis: str, ziel: str, einbau: bool) -> None:
        dateien, ordner = self._gelesen(ergebnis, ziel)
        erwartet = self._erwartet(einbau)
        for rel in ("sce_sys/param.json", "sce_sys/param.json.alt"):          # die param.json wird vor dem Einbau geprueft
            dateien.pop(rel, None)
            erwartet.pop(rel, None)
        self.assertEqual(sorted(erwartet), sorted(dateien))
        for rel, daten in erwartet.items():
            self.assertEqual(daten, dateien[rel], rel)
        self.assertIn("savedata_leer", ordner, "ein leeres Verzeichnis bleibt")
        self.assertFalse([r for r in dateien if z.ist_packname(r)], "es entsteht kein Pack")

    def _lauf(self, quelle: str, ziel: str, einbau: bool, **kw):
        g = self.gui(einbau)
        ok = g._mode_exfat_umpacken_strom(quelle, self.ziel, ziel=ziel, **kw)
        self.assertTrue(ok, "\n".join(g._log_lines))
        namen = os.listdir(self.ziel)
        self.assertEqual(1, len(namen), namen)
        return g, os.path.join(self.ziel, namen[0])

    def test_alle_quellen_und_ziele_mit_einbau(self) -> None:
        for quelle, kw in ((self.quelle, {}), (self.huelle, {"pfs": True}), (self.spiel, {"ordner": True})):
            for ziel in ("exfat", "ffpfsc"):
                with self.subTest(quelle=os.path.basename(quelle), ziel=ziel):
                    shutil.rmtree(self.ziel)
                    os.makedirs(self.ziel)
                    g, ergebnis = self._lauf(quelle, ziel, True, **kw)
                    self._pruefen(g, ergebnis, ziel, True)

    def test_ohne_jeden_einbau_wird_nichts_veraendert(self) -> None:
        """Ein Abbild umzubauen (z. B. .ffpfsc -> .exfat) braucht kein Entpacken: Das Ergebnis hat genau die Dateien der Quelle."""
        for quelle, kw in ((self.huelle, {"pfs": True}), (self.quelle, {})):
            with self.subTest(quelle=os.path.basename(quelle)):
                shutil.rmtree(self.ziel)
                os.makedirs(self.ziel)
                g, ergebnis = self._lauf(quelle, "exfat", False, **kw)
                self._pruefen(g, ergebnis, "exfat", False)

    def test_quelle_unveraendert_kein_rest(self) -> None:
        vorher = {p: (os.path.getsize(p), os.stat(p).st_mtime_ns) for p in (self.quelle, self.huelle)}
        self._lauf(self.huelle, "exfat", True, pfs=True)
        self.assertEqual(vorher, {p: (os.path.getsize(p), os.stat(p).st_mtime_ns) for p in (self.quelle, self.huelle)})
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))

    def test_der_ueberlagerungsordner_ist_klein(self) -> None:
        """Im Arbeitsordner liegt nur die Systemschicht (und was der Einbau ablegt), nicht das Spiel."""
        g = self.gui(True)
        gesehen: dict[str, int] = {}
        urspruenglich = g._integration_anwenden

        def integration(ordner, **k):
            gesehen["bytes"] = sum(f.stat().st_size for f in Path(ordner).rglob("*") if f.is_file())
            return urspruenglich(ordner, **k)
        g._integration_anwenden = integration
        self.assertTrue(g._mode_exfat_umpacken_strom(self.quelle, self.ziel))
        gross = sum(len(d) for rel, d in self.inhalt.items() if rel.startswith(("Media/", "data/")))
        self.assertLess(gesehen["bytes"], gross // 4)

    def test_fehlschlag_des_einbaus_laesst_nichts_zurueck(self) -> None:
        g = self.gui(True)
        g._integration_anwenden = lambda ordner, **k: ""
        self.assertFalse(g._mode_exfat_umpacken_strom(self.quelle, self.ziel))
        self.assertEqual([], os.listdir(self.ziel))
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))

    def test_eine_asset_schicht_in_der_quelle_bleibt_beim_alten_weg(self) -> None:
        """Ein neuer ``ampr_emu.index`` machte das Manifest einer LZ4-Schicht unbrauchbar - die Rueckfrage braucht den ganzen Ordner."""
        Path(self.spiel, APP.ampr_assetpakete.MANIFEST_NAME).write_bytes(b"manifest")
        with open(self.quelle, "wb") as fh:
            for stueck in iter_exfat_image(Path(self.spiel)):
                fh.write(stueck)
        g = self.gui(True)
        g._ist_ampr_asset_datei = GUI._ist_ampr_asset_datei
        self.assertIsNone(g._mode_exfat_umpacken_strom(self.quelle, self.ziel))
        self.assertEqual([], os.listdir(self.ziel))
        self.assertTrue(any("Asset" in z_ or "asset" in z_ for z_ in g._log_lines), "\n".join(g._log_lines))


def _ufs2_werkzeug() -> "str | None":
    if sys.platform != "win32":
        return None
    pfad = ROOT / "UFS2Tool-4.1" / "win-x64" / "UFS2Tool.exe"
    return str(pfad) if pfad.is_file() else None


@unittest.skipUnless(z.verfuegbar() and _ufs2_werkzeug(), "zstandard oder UFS2Tool (ohne Erhoehung startbar) fehlt")
class Ufs2StromTests(_Grundlage):
    """Etappe 10: ``.ffpkg`` (UFS2) als Quelle - gelesen mit dem eigenen Leser, ohne UFS2Tool, Dokan und Administratorrechte."""

    def setUp(self) -> None:
        super().setUp()
        from ps5_validator.utils import ffpkg_support as ffs
        os.makedirs(os.path.join(self.spiel, "savedata_leer"))
        self.ffpkg = os.path.join(self.tmp, "spiel.ffpkg")
        lauf = subprocess.run(
            ffs.build_newfs_directory_command(_ufs2_werkzeug(), self.spiel, self.ffpkg), capture_output=True, text=True,
            timeout=300, env=dict(os.environ, __COMPAT_LAYER="RunAsInvoker"))
        if lauf.returncode != 0 or not os.path.isfile(self.ffpkg):
            self.skipTest("UFS2Tool newfs scheiterte: %s" % (lauf.stdout or lauf.stderr)[-200:])

    def gui(self, einbau: str = "ampr"):
        g = _gui(self.tmp)
        g._resolve_pack_profile = lambda mode, groesse: {
            "profile": "t", "level": 3, "cpu": 1, "cores": 1, "block_size": 65536, "size_gb": 0.0, "verify_after": True}
        g._format_phase_status = lambda text, **k: text
        if einbau == "keiner":
            g._integration_anwenden = lambda ordner, **k: ordner
        return g

    def _gelesen(self, pfad: str, ziel: str) -> "tuple[dict[str, bytes], list[str]]":
        with (sb.PfsBaum(pfad) if ziel == "ffpfsc" else sb.ExfatBaum(pfad)) as baum:
            return {d.rel: b"".join(d.lesen()) for d in baum.dateien()}, baum.ordner()

    def test_ohne_einbau_gleicht_die_ausgabe_der_quelle(self) -> None:
        for ziel in ("exfat", "ffpfsc"):
            with self.subTest(ziel=ziel):
                shutil.rmtree(self.ziel)
                os.makedirs(self.ziel)
                g = self.gui("keiner")
                self.assertTrue(g._mode_exfat_umpacken_strom(self.ffpkg, self.ziel, ziel=ziel, ufs2=True), "\n".join(g._log_lines))
                ergebnis = os.path.join(self.ziel, os.listdir(self.ziel)[0])
                dateien, ordner = self._gelesen(ergebnis, ziel)
                for rel in ("sce_sys/param.json", "sce_sys/param.json.alt"):
                    dateien.pop(rel, None)
                erwartet = {k: v for k, v in self.inhalt.items() if k != "sce_sys/param.json"}
                self.assertEqual(sorted(erwartet), sorted(dateien))
                for rel, daten in erwartet.items():
                    self.assertEqual(daten, dateien[rel], rel)
                self.assertIn("savedata_leer", ordner)

    def test_mit_zstd_pack_aus_einer_ffpkg(self) -> None:
        for ziel in ("exfat", "ffpfsc"):
            with self.subTest(ziel=ziel):
                shutil.rmtree(self.ziel)
                os.makedirs(self.ziel)
                g = self.gui()
                self.assertTrue(g._mode_exfat_umpacken_strom(self.ffpkg, self.ziel, ziel=ziel, ufs2=True), "\n".join(g._log_lines))
                dateien, _ordner = self._gelesen(os.path.join(self.ziel, os.listdir(self.ziel)[0]), ziel)
                self.assertEqual(NG_LIB, dateien["fakelib/libSceAmpr.sprx"])
                self.assertIn("ampr_zstd-000.pak", dateien)
                self.assertNotIn("Media/text.txt", dateien)

    def test_quelle_unveraendert_und_nichts_im_temp(self) -> None:
        vorher = (os.path.getsize(self.ffpkg), os.stat(self.ffpkg).st_mtime_ns)
        g = self.gui()
        self.assertTrue(g._mode_exfat_umpacken_strom(self.ffpkg, self.ziel, ufs2=True), "\n".join(g._log_lines))
        self.assertEqual(vorher, (os.path.getsize(self.ffpkg), os.stat(self.ffpkg).st_mtime_ns))
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))

    def test_kein_unterbefehl_kein_dokan_keine_administratorrechte(self) -> None:
        """Der Strom braucht weder UFS2Tool noch ein Dokan-Laufwerk noch Administratorrechte."""
        g = self.gui("keiner")
        verboten = []
        for name in ("_extract_ufs2tool", "_find_dokan_driver", "_extract_ffpkg_to_folder_via_ufs2tool",
                     "_ffpkg_ueber_unterbefehl_entpacken"):
            stub = mock.Mock(side_effect=AssertionError("%s aufgerufen" % name))
            self.addCleanup(stub.assert_not_called)          # von aussen pruefen: ein except im Programm koennte den Fehler schlucken
            verboten.append(stub)
            setattr(g, name, stub)
        admin = mock.Mock(side_effect=AssertionError("Administratorrechte abgefragt"))
        self.addCleanup(admin.assert_not_called)
        with mock.patch.object(APP, "_is_admin", admin):
            self.assertTrue(g._mode_exfat_umpacken_strom(self.ffpkg, self.ziel, ufs2=True), "\n".join(g._log_lines))

    def test_ein_spiel_in_einem_unterordner_bleibt_beim_alten_weg(self) -> None:
        from ps5_validator.utils import ffpkg_support as ffs
        tief = os.path.join(self.tmp, "tief")
        for rel, daten in self.inhalt.items():
            voll = os.path.join(tief, "PPSA04263", *rel.split("/"))
            os.makedirs(os.path.dirname(voll), exist_ok=True)
            Path(voll).write_bytes(daten)
        abbild = os.path.join(self.tmp, "tief.ffpkg")
        lauf = subprocess.run(ffs.build_newfs_directory_command(_ufs2_werkzeug(), tief, abbild), capture_output=True, text=True,
                              timeout=300, env=dict(os.environ, __COMPAT_LAYER="RunAsInvoker"))
        self.assertEqual(0, lauf.returncode, lauf.stdout)
        g = self.gui()
        self.assertIsNone(g._mode_exfat_umpacken_strom(abbild, self.ziel, ufs2=True))
        self.assertEqual([], os.listdir(self.ziel))

    def test_verweise_im_abbild_bleiben_beim_alten_weg(self) -> None:
        echt = sb.Ufs2Baum.dateien

        def mit_verweis(baum):
            erg = echt(baum)
            baum.uebersprungen = ["verweis"]
            return erg
        g = self.gui()
        with mock.patch.object(sb.Ufs2Baum, "dateien", mit_verweis):
            self.assertIsNone(g._mode_exfat_umpacken_strom(self.ffpkg, self.ziel, ufs2=True))
        self.assertEqual([], os.listdir(self.ziel))

    def test_kein_ufs2_bleibt_beim_alten_weg(self) -> None:
        kaputt = os.path.join(self.tmp, "kaputt.ffpkg")
        Path(kaputt).write_bytes(bytes(300_000))
        g = self.gui()
        self.assertIsNone(g._mode_exfat_umpacken_strom(kaputt, self.ziel, ufs2=True))

    def test_abbruch_und_aenderung_waehrend_des_laufs(self) -> None:
        g = self.gui()

        def abbrechen(prozent, phase):
            g.is_running = False
        g._ampr_pack_fortschritt = abbrechen
        self.assertFalse(g._mode_exfat_umpacken_strom(self.ffpkg, self.ziel, ufs2=True))
        self.assertEqual([], os.listdir(self.ziel))
        kopie = os.path.join(self.tmp, "kopie.ffpkg")
        shutil.copyfile(self.ffpkg, kopie)
        g = self.gui()
        urspruenglich = g._integration_anwenden

        def integration(ordner, **k):
            erg = urspruenglich(ordner, **k)
            with open(kopie, "ab") as fh:
                fh.write(b"\0" * 512)
            return erg
        g._integration_anwenden = integration
        self.assertFalse(g._mode_exfat_umpacken_strom(kopie, self.ziel, ufs2=True))
        self.assertEqual([], os.listdir(self.ziel))

    # -- Einhaengen --------------------------------------------------------------------------------------------------------------
    def test_ffpkg_zu_exfat_nimmt_den_strom_zuerst(self) -> None:
        g = GUI.__new__(GUI)
        aufrufe: list[tuple] = []
        g._strom_weg_gewaehlt = lambda: True
        g._mode_exfat_umpacken_strom = lambda src, dst, **kw: aufrufe.append((src, dst, kw)) or "strom"
        self.assertEqual("strom", g._mode_ffpkg_to_exfat("a.ffpkg", "d"))
        self.assertEqual([("a.ffpkg", "d", {"ufs2": True})], aufrufe)

    def test_ffpkg_zu_exfat_faellt_zurueck(self) -> None:
        for strom, ergebnis in ((False, "strom"), (True, None)):
            g = GUI.__new__(GUI)
            g._strom_weg_gewaehlt = lambda s=strom: s
            g._mode_exfat_umpacken_strom = lambda src, dst, e=ergebnis, **kw: e
            g._mkdtemp = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("alter weg"))
            with self.assertRaises(RuntimeError):
                g._mode_ffpkg_to_exfat("a.ffpkg", "d")

    def test_ffpkg_zu_ffpfsc_mit_einbau_nimmt_den_strom(self) -> None:
        g = GUI.__new__(GUI)
        aufrufe: list[tuple] = []
        g._strom_weg_gewaehlt = lambda: True
        g._mode_exfat_umpacken_strom = lambda src, dst, **kw: aufrufe.append((src, dst, kw)) or "strom"
        self.assertEqual("strom", g._mode_abbild_zu_ffpfs("a.ffpkg", "d", quelle="ffpkg", uncompressed=False))
        self.assertEqual([("a.ffpkg", "d", {"ufs2": True, "ziel": "ffpfsc"})], aufrufe)

    def test_platzbedarf_ffpkg(self) -> None:
        g = GUI.__new__(GUI)
        g._strom_weg_gewaehlt = lambda: True
        g._quellgroesse_ermitteln = lambda src: 100 * 1024 ** 3
        g._estimate_unpack_space_requirement = lambda src: None
        g._integration_gewuenscht = lambda: True
        g._umhuellt_neu_packen = False
        temp, _ziel, dump = g._platzbedarf_je_quelle("spiel.ffpkg", "exfat")
        self.assertLess(temp, 10 * 1024 ** 3, "Im Arbeitsordner liegt nicht mehr das entpackte Spiel")
        self.assertEqual(0, dump)
        g._strom_weg_gewaehlt = lambda: False
        self.assertGreaterEqual(g._platzbedarf_je_quelle("spiel.ffpkg", "exfat")[0], 100 * 1024 ** 3)


class WegwahlTests(unittest.TestCase):
    def _probe(self, **kw):
        g = GUI.__new__(GUI)
        g.einstellungen = kw.get("einstellungen", {})
        g._load_setting = lambda name, vorgabe=None: g.einstellungen.get(name, vorgabe)
        g._ampr_wird_eingebaut = lambda: kw.get("ampr", True)
        g._ampr_methode = lambda: kw.get("methode", APP.AMPR_METHODE_ASSETPACK)
        g._ampr_pack_verfahren = lambda: kw.get("verfahren", "zstd")
        g._integration_gewaehlt = lambda: kw.get("einbau", kw.get("ampr", True))
        return g

    @unittest.skipUnless(z.verfuegbar(), "zstandard fehlt")
    def test_asset_pack_nur_mit_zstd(self) -> None:
        """AMPR mit der Methode Asset-Pack: zstd laeuft im Strom, LZ4 braucht einen Ordner und ein Werkzeug."""
        self.assertTrue(self._probe()._strom_weg_gewaehlt())
        self.assertTrue(self._probe()._strom_fuer_ordner_gewaehlt())
        self.assertFalse(self._probe(verfahren="lz4")._strom_weg_gewaehlt())
        self.assertFalse(self._probe(verfahren="lz4")._strom_fuer_ordner_gewaehlt())

    def test_jeder_andere_einbau_laeuft_im_strom(self) -> None:
        """Backport, Fake-Signatur, DLC EMU, PlayGo und AMPR ohne Pack aendern nur wenige Dateien: kein Entpacken noetig."""
        for name, kw in (("AMPR normal", {"methode": "normal"}),
                         ("ohne AMPR, mit Einbau (Backport usw.)", {"ampr": False, "einbau": True})):
            with self.subTest(name):
                self.assertTrue(self._probe(**kw)._strom_weg_gewaehlt())
                self.assertTrue(self._probe(**kw)._strom_fuer_ordner_gewaehlt())

    def test_ohne_einbau_nur_ein_abbild_als_quelle(self) -> None:
        """Ohne Einbau gibt es fuer ein Abbild keinen Grund zum Entpacken; ein Ordner wird vom bisherigen Weg ohnehin direkt gebaut."""
        probe = self._probe(ampr=False, einbau=False)
        self.assertTrue(probe._strom_weg_gewaehlt())
        self.assertFalse(probe._strom_fuer_ordner_gewaehlt())

    def test_nicht_entscheidbar_ist_der_alte_weg(self) -> None:
        g = self._probe()
        g._ampr_methode = lambda: (_ for _ in ()).throw(RuntimeError("Einstellungen nicht lesbar"))
        self.assertFalse(g._strom_weg_gewaehlt())
        self.assertFalse(g._strom_fuer_ordner_gewaehlt())

    def test_einstellung_schaltet_aus(self) -> None:
        for kw in ({}, {"ampr": False, "einbau": True}, {"ampr": False, "einbau": False}):
            probe = self._probe(einstellungen={"exfat_strom": False}, **kw)
            self.assertFalse(probe._strom_weg_gewaehlt())
            self.assertFalse(probe._strom_fuer_ordner_gewaehlt())

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
