# -*- coding: utf-8 -*-
"""Die Pruefung der Quelle in Worten (17.11.2026): ``quellbericht``, der Bericht im Protokoll der Aufgaben 1 bis 6 und die
Argumente von Dump Forge fuer ein Abbild aus einem Paket.

Nutzerwunsch: Der Anwender soll sehen, ob das Programm selbst erkannt hat, was im Spiel liegt (AMPR EMU, Asset-Packs, PlayGo,
DLC, BACKPORT) und ob etwas eingebaut werden muss - nicht nur, wenn eine Rueckfrage kommt.
"""
from __future__ import annotations

import itertools
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402,F401
from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI as GUI   # noqa: E402
from ps5_validator.utils import forge_cli as fc              # noqa: E402
from ps5_validator.utils import ps5_pkg_werkzeug as wz       # noqa: E402
from ps5_validator.utils import quellbericht as qb           # noqa: E402
from ps5_validator.utils.i18n import STRINGS, translate      # noqa: E402


def _t(schluessel: str, **w) -> str:
    return schluessel + ("|" + ",".join("%s=%s" % kv for kv in sorted(w.items())) if w else "")


def _stufen(liste) -> dict:
    return {z.schluessel: z.stufe for z in liste}


class ZeilenTests(unittest.TestCase):
    def test_jede_quelle_bekommt_fuenf_zeilen_in_der_reihenfolge_der_kaestchen(self) -> None:
        liste = qb.zeilen(fc.QuellFakten(), _t)
        self.assertEqual(list(qb.SCHLUESSEL), [z.schluessel for z in liste])

    def test_ampr_fehlt_wenn_das_spiel_libsceampr_laedt_und_nichts_mitbringt(self) -> None:
        f = fc.QuellFakten(ampr_importiert=True, ampr_fehlt=True)
        liste = qb.zeilen(f, _t)
        self.assertEqual(qb.STUFE_FEHLT, _stufen(liste)["ampr"])
        self.assertEqual("bericht.ampr_fehlt", liste[0].text)

    def test_ampr_ist_da_mit_dem_namen_der_laufzeit(self) -> None:
        for laufzeit, name in (("zstd", "ampr-emu-ng (zstd)"), ("other", "AMPR EMU"), ("forge_release", "Dump Forge"),
                               ("", "AMPR EMU")):
            with self.subTest(laufzeit=laufzeit):
                z = qb.zeilen(fc.QuellFakten(ampr_importiert=True, ampr_fehlt=False, laufzeit=laufzeit), _t)[0]
                self.assertEqual((qb.STUFE_OK, "bericht.ampr_da|laufzeit=%s" % name), (z.stufe, z.text))

    def test_ampr_nicht_noetig_und_nicht_zu_sagen_sind_zwei_verschiedene_dinge(self) -> None:
        nein = qb.zeilen(fc.QuellFakten(ampr_importiert=False, ampr_fehlt=False), _t)[0]
        unklar = qb.zeilen(fc.QuellFakten(ampr_fehlt=None), _t)[0]
        self.assertEqual((qb.STUFE_OK, "bericht.ampr_nicht_noetig"), (nein.stufe, nein.text))
        self.assertEqual((qb.STUFE_HINWEIS, "bericht.ampr_unbekannt"), (unklar.stufe, unklar.text),
                         "leer ist nicht Nein: ohne Angabe von Forge wird nichts geraten")

    # ---------------- Dump Forge setzt beim Paketbau seine eigene Laufzeit ein (gemessen 21.11.2026, Forge 0.5.6) ----------------
    @staticmethod
    def _laufzeit_fakten(**kw):
        werte = dict(ampr_importiert=True, ampr_fehlt=False, laufzeit="zstd", laufzeit_version="0.5.0", laufzeit_neu="0.4.2.1",
                     laufzeit_aktion="replace")
        werte.update(kw)
        return fc.QuellFakten(**werte)

    def test_quellfakten_liest_laufzeit_fassung_und_aktion_aus_forges_antwort(self) -> None:
        # So antwortet Forge 0.5.6 auf ein Spiel mit ampr-emu-ng 0.5.0 in fakelib/ (``inspect --json``, 21.11.2026).
        daten = {"lz4": {"imports_ampr": True, "packed": None, "manifest_error": None, "runtime": "zstd", "shipped_runtime_version": "0.4.2.1",
                         "runtime_version": "0.5.0", "runtime_action": "replace", "pack_runtime_action": "replace", "index": "stale"},
                 "zstd_packed": False, "emulators": [{"path": "fakelib/libSceAmpr.sprx", "name": "AMPR"}]}
        f = fc.quellfakten(daten)
        self.assertEqual(("zstd", "0.5.0", "0.4.2.1", "replace"), (f.laufzeit, f.laufzeit_version, f.laufzeit_neu, f.laufzeit_aktion))
        self.assertTrue(f.laufzeit_ersetzt)
        leer = fc.quellfakten({})
        self.assertEqual(("", "", ""), (leer.laufzeit_version, leer.laufzeit_neu, leer.laufzeit_aktion), "ohne Angabe nichts raten")
        self.assertFalse(leer.laufzeit_ersetzt)

    def test_laufzeit_ersetzt_nur_wenn_forge_sie_ersetzt(self) -> None:
        for name, kw, soll in (
                ("ampr-emu-ng wird ersetzt", {}, True),
                ("AMPR EMU (other) wird ersetzt", {"laufzeit": "other", "laufzeit_version": "0.3.6.6"}, True),
                ("Forges eigene Laufzeit bleibt", {"laufzeit": "forge_release", "laufzeit_aktion": "keep"}, False),
                ("keine Laufzeit im Spiel: Forge legt sie nur dazu", {"laufzeit": "none", "laufzeit_aktion": "install"}, False),
                ("ohne Angabe von Forge wird nichts geraten", {"laufzeit_aktion": ""}, False),
                ("das Spiel laedt libSceAmpr nicht", {"ampr_importiert": False}, False),
                ("ein gepacktes Spiel entpackt das Programm ohnehin", {"gepackt": "zstd"}, False)):
            with self.subTest(name):
                self.assertEqual(soll, self._laufzeit_fakten(**kw).laufzeit_ersetzt)

    def test_bei_einem_paket_sagt_der_bericht_welche_laufzeit_dump_forge_ersetzt(self) -> None:
        liste = qb.zeilen(self._laufzeit_fakten(), _t, forge_ergaenzt_ampr=True)
        z = liste[0]
        self.assertEqual((qb.STUFE_HINWEIS, "bericht.ampr_ersetzt|alt=ampr-emu-ng 0.5.0,neu=ampr_emu 0.4.2.1"), (z.stufe, z.text))
        self.assertEqual([], qb.fehlendes(liste), "ein Hinweis: nichts, was der Anwender einbauen muss (die Rueckfrage stellt das Fenster)")

    def test_ohne_paket_oder_ohne_austausch_bleibt_die_zeile_wie_sie_war(self) -> None:
        # Aufgaben 1 bis 6 (kein Paket): Dort baut Forge nichts, die Laufzeit des Spiels bleibt.
        z = qb.zeilen(self._laufzeit_fakten(), _t)[0]
        self.assertEqual((qb.STUFE_OK, "bericht.ampr_da|laufzeit=ampr-emu-ng (zstd)"), (z.stufe, z.text))
        z = qb.zeilen(self._laufzeit_fakten(laufzeit="forge_release", laufzeit_aktion="keep"), _t, forge_ergaenzt_ampr=True)[0]
        self.assertEqual((qb.STUFE_OK, "bericht.ampr_da|laufzeit=Dump Forge"), (z.stufe, z.text))

    def test_wandelt_dump_forge_ein_paket_direkt_in_ein_abbild_steht_der_austausch_auch_da(self) -> None:
        """``convert x.pkg --to ffpkg|exfat``: Forge ersetzt ampr-emu-ng auch dort ("any other job puts the release runtime in its
        place", Forge ``lz4.rs``). Vorher stand "[OK] vorhanden (ampr-emu-ng)", und im Abbild steckte danach ampr_emu."""
        liste = qb.zeilen(self._laufzeit_fakten(), _t, forge_wandelt=True)
        z = liste[0]
        self.assertEqual((qb.STUFE_HINWEIS, "bericht.ampr_ersetzt_umwandeln|alt=ampr-emu-ng 0.5.0,neu=ampr_emu 0.4.2.1"),
                         (z.stufe, z.text))
        self.assertEqual([], qb.fehlendes(liste), "ein Hinweis, keine Rueckfrage")
        # Auch ein gepacktes Spiel: Der direkte Weg reicht kein Entpacken mit, Forge wandelt die Quelle, wie sie ist (inspect.rs:
        # LZ4-Packs -> action(.., packs), zstd-Packs -> zstd_action mit Forges ampr-emu-ng). Korrektur-Pruefer 22.11.2026.
        lz4 = qb.zeilen(self._laufzeit_fakten(gepackt="lz4", laufzeit="other", laufzeit_version="0.3.6.6"), _t, forge_wandelt=True)[0]
        self.assertEqual((qb.STUFE_HINWEIS, "bericht.ampr_ersetzt_umwandeln|alt=AMPR EMU 0.3.6.6,neu=ampr_emu 0.4.2.1"),
                         (lz4.stufe, lz4.text))
        zstd = qb.zeilen(self._laufzeit_fakten(gepackt="zstd", laufzeit_version="0.4.1"), _t, forge_wandelt=True)[0]
        self.assertEqual((qb.STUFE_HINWEIS, "bericht.ampr_ersetzt_umwandeln|alt=ampr-emu-ng 0.4.1,neu=ampr-emu-ng"),
                         (zstd.stufe, zstd.text))
        # Gegenproben: Forges eigene Laufzeit bleibt; ohne Angabe von Forge wird nichts geraten.
        for kw in ({"laufzeit": "forge_release", "laufzeit_aktion": "keep"}, {"laufzeit_aktion": ""}, {"gepackt": "zstd", "laufzeit_aktion": "keep"}):
            with self.subTest(kw=kw):
                self.assertEqual(qb.STUFE_OK, qb.zeilen(self._laufzeit_fakten(**kw), _t, forge_wandelt=True)[0].stufe)
        for sprache in ("de", "en", "es", "it", "fr"):
            with self.subTest(sprache=sprache):
                text = STRINGS["bericht.ampr_ersetzt_umwandeln"][sprache].format(alt="ampr-emu-ng 0.5.0", neu="ampr_emu 0.4.2.1")
                self.assertIn("ampr-emu-ng 0.5.0", text)
                self.assertIn("ampr_emu 0.4.2.1", text)

    def test_der_direkte_weg_im_paketfenster_meldet_den_austausch(self) -> None:
        """``_abbild_direkt_moeglich`` ruft den Bericht mit ``forge_wandelt`` auf - sonst sieht der Anwender die Zeile nie."""
        from ps5_validator.ui import ps5_pkg_fenster as pf
        import inspect as _inspect
        quelle = _inspect.getsource(pf.Ps5PkgFenster._abbild_direkt_moeglich)
        self.assertEqual(1, quelle.count("self._quelle_pruefen(info, paket=False, forge_wandelt=True)"))
        quelle = _inspect.getsource(pf.Ps5PkgFenster._quelle_pruefen)
        self.assertEqual(1, quelle.count("forge_wandelt=forge_wandelt)"))

    def test_die_namen_der_laufzeiten_mit_fassung(self) -> None:
        for laufzeit, version, soll in (("zstd", "0.5.0", "ampr-emu-ng 0.5.0"), ("other", "0.3.6.6", "AMPR EMU 0.3.6.6"),
                                        ("other", "", "AMPR EMU"), ("forge_trace", "", "ampr_emu (Trace)"), ("", "", "AMPR EMU")):
            with self.subTest(laufzeit=laufzeit, version=version):
                self.assertEqual(soll, qb.laufzeit_name(fc.QuellFakten(laufzeit=laufzeit, laufzeit_version=version)))
        self.assertEqual("ampr_emu 0.4.2.1", qb.laufzeit_neu_name(fc.QuellFakten(laufzeit_neu="0.4.2.1")))
        self.assertEqual("ampr_emu", qb.laufzeit_neu_name(fc.QuellFakten()))

    def test_die_meldung_zur_laufzeit_gibt_es_in_allen_sprachen_und_nennt_den_weg(self) -> None:
        for sprache in ("de", "en", "es", "it", "fr"):
            with self.subTest(sprache=sprache):
                text = STRINGS["ps5pkg.laufzeit_frage"][sprache].format(alt="ampr-emu-ng 0.5.0", neu="ampr_emu 0.4.2.1")
                for stueck in ("ampr-emu-ng 0.5.0", "ampr_emu 0.4.2.1", "ShadowMount+", ".ffpkg", "AMPR EMU"):
                    self.assertIn(stueck, text)
                for schluessel in ("bericht.ampr_ersetzt", "ps5pkg.laufzeit_titel", "ps5pkg.laufzeit_log", "ps5pkg.laufzeit_abbruch"):
                    self.assertTrue(STRINGS[schluessel][sprache], schluessel)

    # ---------------- Dump Forge ab 0.6.0: ein .pkg traegt keine AMPR-Laufzeit (gemessen 26.11.2026) ----------------
    #: Der ``lz4``-Block, wie ihn ``inspect --json`` von Forge 0.6.0 fuer ein Spiel mit AMPR EMU 0.3.6.6 liefert (Crazy Chicken Shooter).
    LZ4_060 = {"imports_ampr": True, "packed": None, "manifest_error": None, "runtime": "other", "shipped_runtime_version": "0.4.2.1",
               "runtime_version": None, "runtime_action": "replace", "keep_runtime_action": "keep", "unpack_runtime_action": None,
               "pack_runtime_action": "replace", "pkg_runtime_action": "omit", "index": "stale", "keep_index": "ok"}

    def _fakten_060(self, **lz4) -> "fc.QuellFakten":
        block = dict(self.LZ4_060)
        block.update(lz4)
        emulatoren = [] if block["runtime"] == "none" else [{"path": "fakelib/libSceAmpr.sprx", "name": "AMPR"}]
        return fc.quellfakten({"lz4": block, "emulators": emulatoren})

    def test_forge_060_laesst_die_laufzeit_im_paket_weg_statt_sie_zu_ersetzen(self) -> None:
        f = self._fakten_060()
        self.assertEqual(("omit", "replace"), (f.laufzeit_aktion_paket, f.laufzeit_aktion))
        self.assertTrue(f.paket_ohne_laufzeit)
        self.assertTrue(f.laufzeit_entfaellt)
        self.assertFalse(f.laufzeit_ersetzt, "beim Paketbau gilt pkg_runtime_action, nicht runtime_action")
        ohne = self._fakten_060(runtime="none", runtime_action="install")
        self.assertTrue(ohne.paket_ohne_laufzeit)
        self.assertFalse(ohne.laufzeit_entfaellt, "ohne Laufzeit im Spiel entfaellt nichts")
        kein_import = fc.quellfakten({"lz4": dict(self.LZ4_060, imports_ampr=False)})
        self.assertFalse(kein_import.paket_ohne_laufzeit, "ein Spiel ohne libSceAmpr betrifft das nicht")

    def test_bis_057_bleibt_es_beim_ersetzen(self) -> None:
        """Gegenprobe: Ohne ``pkg_runtime_action`` (Forge bis 0.5.7) gilt weiter ``runtime_action``."""
        alt = {k: v for k, v in self.LZ4_060.items() if k not in ("pkg_runtime_action", "keep_runtime_action", "unpack_runtime_action",
                                                                 "keep_index")}
        f = fc.quellfakten({"lz4": alt, "emulators": [{"path": "fakelib/libSceAmpr.sprx", "name": "AMPR"}]})
        self.assertEqual("", f.laufzeit_aktion_paket)
        self.assertTrue(f.laufzeit_ersetzt)
        self.assertFalse(f.paket_ohne_laufzeit)
        self.assertFalse(f.laufzeit_entfaellt)
        self.assertEqual("ampr_emu 0.4.2.1", qb.laufzeit_neu_name(f))

    def test_der_bericht_zum_paket_sagt_dass_die_laufzeit_wegbleibt(self) -> None:
        z = qb.zeilen(self._fakten_060(), _t, forge_ergaenzt_ampr=True)[0]
        self.assertEqual((qb.STUFE_HINWEIS, "bericht.ampr_entfaellt|alt=AMPR EMU"), (z.stufe, z.text))
        self.assertEqual([], qb.fehlendes(qb.zeilen(self._fakten_060(), _t, forge_ergaenzt_ampr=True)))
        # ohne Paketbau (ein Abbild aus den Aufgaben 1 bis 6) bleibt die Laufzeit des Spiels, und der Bericht sagt nur, dass sie da ist
        z = qb.zeilen(self._fakten_060(), _t)[0]
        self.assertEqual((qb.STUFE_OK, "bericht.ampr_da|laufzeit=AMPR EMU"), (z.stufe, z.text))

    def test_fehlt_die_laufzeit_ist_das_beim_paket_von_forge_060_kein_mangel_und_forge_legt_nichts_dazu(self) -> None:
        f = self._fakten_060(runtime="none", runtime_action="install")
        self.assertIs(True, f.ampr_fehlt)
        liste = qb.zeilen(f, _t, forge_ergaenzt_ampr=True)
        self.assertEqual((qb.STUFE_HINWEIS, "bericht.ampr_paket_ohne"), (liste[0].stufe, liste[0].text))
        self.assertEqual([], qb.fehlendes(liste))
        # fuer ein Abbild fehlt er weiter
        self.assertEqual((qb.STUFE_FEHLT, "bericht.ampr_fehlt"), (qb.zeilen(f, _t)[0].stufe, qb.zeilen(f, _t)[0].text))

    def test_wandelt_forge_060_selbst_um_setzt_es_ampr_emu_ng_ein(self) -> None:
        """Gemessen 26.11.2026: "replacing the game's runtime ... with the bundled ampr-emu-ng 0.5.1" - nicht mehr ampr_emu 0.4.2.1,
        obwohl ``shipped_runtime_version`` die alte Nummer weiter nennt."""
        f = self._fakten_060()
        self.assertEqual("ampr-emu-ng", qb.laufzeit_neu_name(f))
        z = qb.zeilen(f, _t, forge_wandelt=True)[0]
        self.assertEqual((qb.STUFE_HINWEIS, "bericht.ampr_ersetzt_umwandeln|alt=AMPR EMU,neu=ampr-emu-ng"), (z.stufe, z.text))

    def test_die_texte_zur_weggelassenen_laufzeit_gibt_es_in_allen_sprachen(self) -> None:
        for sprache in ("de", "en", "es", "it", "fr"):
            with self.subTest(sprache=sprache):
                text = STRINGS["ps5pkg.laufzeit_weg_frage"][sprache].format(alt="AMPR EMU 0.3.6.6")
                for stueck in ("AMPR EMU 0.3.6.6", "ShadowMount+", ".ffpkg", "Kraken Mount", "ampr-emu-ng"):
                    self.assertIn(stueck, text)
                self.assertIn("AMPR EMU 0.3.6.6", STRINGS["bericht.ampr_entfaellt"][sprache].format(alt="AMPR EMU 0.3.6.6"))
                for schluessel in ("bericht.ampr_paket_ohne", "ps5pkg.laufzeit_weg_titel", "ps5pkg.laufzeit_weg_log",
                                   "ps5pkg.laufzeit_weg_abbruch", "bericht.einbau_paket"):
                    self.assertTrue(STRINGS[schluessel][sprache], schluessel)
                self.assertNotEqual(STRINGS["ps5pkg.laufzeit_weg_titel"][sprache], STRINGS["ps5pkg.laufzeit_titel"][sprache])

    def test_bei_einem_paket_von_dump_forge_ist_fehlendes_ampr_nur_ein_hinweis(self) -> None:
        f = fc.QuellFakten(ampr_importiert=True, ampr_fehlt=True)
        z = qb.zeilen(f, _t, forge_ergaenzt_ampr=True)[0]
        self.assertEqual((qb.STUFE_HINWEIS, "bericht.ampr_forge"), (z.stufe, z.text))
        self.assertEqual([], qb.fehlendes(qb.zeilen(f, _t, forge_ergaenzt_ampr=True)),
                         "Forge legt ihn selbst dazu: nichts, was der Anwender einbauen muss")

    def test_asset_packs_lz4_zstd_und_keine(self) -> None:
        for gepackt, schluessel in (("", "bericht.packs_keine"), ("lz4", "bericht.packs_lz4"), ("zstd", "bericht.packs_zstd")):
            with self.subTest(gepackt=gepackt):
                z = qb.zeilen(fc.QuellFakten(gepackt=gepackt), _t)[1]
                self.assertEqual(("packs", qb.STUFE_OK, schluessel), (z.schluessel, z.stufe, z.text))

    def test_playgo_fehlt_nur_wenn_inhalt_da_ist_und_der_stub_nicht(self) -> None:
        merkmal = "sce_sys/playgo-scenario.json"
        faelle = (
            (dict(playgo_merkmal=merkmal), qb.STUFE_FEHLT, "bericht.playgo_fehlt|merkmal=" + merkmal),
            (dict(playgo_merkmal=merkmal, emulatoren=("playgo",)), qb.STUFE_OK, "bericht.playgo_da"),
            (dict(emulatoren=("playgo",)), qb.STUFE_OK, "bericht.playgo_da"),
            (dict(), qb.STUFE_OK, "bericht.playgo_nicht_noetig"),
        )
        for fakten, stufe, text in faelle:
            with self.subTest(fakten=fakten):
                z = qb.zeilen(fc.QuellFakten(**fakten), _t)[2]
                self.assertEqual((stufe, text), (z.stufe, z.text))

    def test_dlc_fehlt_nur_wenn_zusatzinhalte_da_sind_und_niemand_sie_meldet(self) -> None:
        faelle = (
            (dict(dlc_vorhanden=True, dlc_merkmal="addcont0"), qb.STUFE_FEHLT, "bericht.dlc_fehlt|merkmal=addcont0"),
            (dict(dlc_vorhanden=True, dlc_emuliert=True), qb.STUFE_OK, "bericht.dlc_da"),
            (dict(), qb.STUFE_OK, "bericht.dlc_nicht_noetig"),
        )
        for fakten, stufe, text in faelle:
            with self.subTest(fakten=fakten):
                z = qb.zeilen(fc.QuellFakten(**fakten), _t)[3]
                self.assertEqual((stufe, text), (z.stufe, z.text))

    def test_backport_an_gemessenen_spielen(self) -> None:
        """Terminator 2D: SDK 10.00, Firmware 11.20; Arcade Game Zone mit BACKPORT: ``backport_firmware`` 7.00 (17.11.2026)."""
        terminator = dict(sdk="10.00", firmware="11.20", eboot_sdk="10.00")
        nur_param = dict(sdk="10.00", firmware="11.20")
        faelle = (
            (terminator, "7.99", qb.STUFE_FEHLT, "bericht.backport_fehlt|konsole=7.xx,spiel=11.20"),
            # Das SDK der Programme liess sich nicht lesen: Die Zeile sagt, dass nur die param.json urteilt.
            (nur_param, "7.99", qb.STUFE_FEHLT, "bericht.backport_fehlt_param|konsole=7.xx,spiel=11.20"),
            (dict(nur_param, backport_firmware="10.00"), "7.99", qb.STUFE_FEHLT,
             "bericht.backport_fehlt|konsole=7.xx,spiel=11.20"),
            # Nur die Module gelesen (eboot.bin unlesbar): das ist keine Messung der Programme - Urteil nach der param.json.
            (dict(nur_param, module_sdk="7.00"), "9.99", qb.STUFE_FEHLT,
             "bericht.backport_fehlt_param|konsole=9.xx,spiel=11.20"),
            (terminator, "12.00", qb.STUFE_OK, "bericht.backport_nicht_noetig|konsole=12.00,spiel=11.20"),
            (terminator, "", qb.STUFE_HINWEIS, "bericht.backport_konsole_unbekannt|spiel=11.20"),
            (dict(sdk="7.00", firmware="9.60", backport_vorhanden=True), "7.99", qb.STUFE_OK, "bericht.backport_da"),
            (dict(), "7.99", qb.STUFE_HINWEIS, "bericht.backport_unbekannt"),
        )
        for fakten, konsole, stufe, text in faelle:
            with self.subTest(fakten=fakten, konsole=konsole):
                z = qb.zeilen(fc.QuellFakten(**fakten), _t, konsole)[4]
                self.assertEqual((stufe, text), (z.stufe, z.text))

    def test_fehlendes_nennt_die_schluessel_in_der_reihenfolge(self) -> None:
        f = fc.QuellFakten(ampr_importiert=True, ampr_fehlt=True, dlc_vorhanden=True, dlc_merkmal="x",
                           playgo_merkmal="sce_sys/playgo-chunk.dat", sdk="10.00", firmware="11.20")
        self.assertEqual(["ampr", "playgo", "dlc", "backport"], qb.fehlendes(qb.zeilen(f, _t, "7.99")))
        self.assertEqual([], qb.fehlendes(qb.zeilen(fc.QuellFakten(), _t, "7.99")))

    def test_das_protokoll_hat_einen_titel_und_je_zeile_eine_marke(self) -> None:
        f = fc.QuellFakten(ampr_importiert=True, ampr_fehlt=True)
        text = qb.protokoll(qb.zeilen(f, _t), _t)
        self.assertEqual("bericht.titel", text[0])
        self.assertEqual(1 + len(qb.SCHLUESSEL), len(text))
        self.assertTrue(text[1].startswith("[FEHLT] "))
        self.assertTrue(all(z.startswith(("[OK] ", "[FEHLT] ", "[HINWEIS] ")) for z in text[1:]))

    def test_die_anzeige_der_firmware_der_konsole(self) -> None:
        self.assertEqual("7.xx", qb.konsole_anzeige("7.99"))
        self.assertEqual("12.00", qb.konsole_anzeige("12.00"))
        self.assertEqual("", qb.konsole_anzeige(None))                                  # type: ignore[arg-type]


class TexteTests(unittest.TestCase):
    """Jede Zeile gibt es in allen fuenf Sprachen und ohne offene Platzhalter - auch fuer jede Mischung der Fakten."""

    def test_alle_zeilen_aller_mischungen_in_allen_sprachen(self) -> None:
        sprachen = ("de", "en", "es", "it", "fr")
        gesehen = 0
        for ampr, gepackt, playgo, dlc, backport, konsole, forge in itertools.product(
                (None, False, True), ("", "lz4", "zstd"), (False, True), (False, True), (False, True), ("", "7.99", "12.00"),
                (False, True)):
            fakten = fc.QuellFakten(
                ampr_importiert=bool(ampr) or ampr is False, ampr_fehlt=ampr, gepackt=gepackt, laufzeit="zstd" if ampr is False else "",
                playgo_merkmal="sce_sys/playgo-chunk.dat" if playgo else "", dlc_vorhanden=dlc, dlc_merkmal="addcont0",
                sdk="10.00" if backport else "", firmware="11.20" if backport else "")
            for sprache in sprachen:
                liste = qb.zeilen(fakten, lambda k, _s=sprache, **w: translate(_s, k, **w), konsole, forge_ergaenzt_ampr=forge)
                for z in liste:
                    gesehen += 1
                    self.assertNotRegex(z.text, r"[{}]", "offener Platzhalter in %s: %s" % (sprache, z.text))
                    self.assertTrue(z.text.strip())
        self.assertGreater(gesehen, 1000)

    def test_die_texte_der_karte_und_der_rueckfrage_gibt_es_in_allen_sprachen(self) -> None:
        for schluessel in ("bericht.titel", "bericht.nicht_pruefbar", "bericht.einbau", "bericht.einbau_nichts",
                           "bericht.einbau_paket", "ps5pkg.einbau_nur_abbild", "ps5pkg.emu_zeile_ampr",
                           "ps5pkg.emu_frage_wahl", "ps5pkg.emu_frage_entpacken", "ps5pkg.emu_wahl_abbild",
                           "ps5pkg.emu_wahl_paket", "ps5pkg.emu_abbild_log", "ps5pkg.lebt_zeit", "ps5pkg.lebt_still",
                           "ps5pkg.log_bauer", "ps5pkg.job_abbild", "ps5pkg.log_start_abbild",
                           "ps5pkg.err_exists_abbild", "ps5pkg.log_einbau_braucht_ordner"):
            with self.subTest(schluessel=schluessel):
                self.assertEqual({"de", "en", "es", "it", "fr"}, set(STRINGS[schluessel]))
                platzhalter = {sp: set(re.findall(r"\{(\w+)\}", text)) for sp, text in STRINGS[schluessel].items()}
                self.assertEqual(1, len({frozenset(p) for p in platzhalter.values()}),
                                 "die Sprachen nennen verschiedene Platzhalter: %s" % platzhalter)

    def test_die_platzhalter_der_neuen_schluessel(self) -> None:
        erwartet = {"ps5pkg.lebt_zeit": {"dauer", "werkzeug"}, "ps5pkg.lebt_still": {"still"}, "ps5pkg.log_bauer": {"name"},
                    "ps5pkg.emu_frage_wahl": {"liste"}, "ps5pkg.emu_frage_entpacken": {"liste"},
                    "ps5pkg.emu_abbild_log": {"liste"}, "ps5pkg.log_einbau_braucht_ordner": {"liste"},
                    "ps5pkg.job_abbild": {"name"}, "ps5pkg.log_start_abbild": {"name"}, "bericht.einbau": {"liste"},
                    "bericht.ampr_da": {"laufzeit"}, "bericht.playgo_fehlt": {"merkmal"}, "bericht.dlc_fehlt": {"merkmal"},
                    "bericht.backport_fehlt": {"spiel", "konsole"}, "bericht.backport_nicht_noetig": {"spiel", "konsole"},
                    "bericht.backport_konsole_unbekannt": {"spiel"}}
        for schluessel, namen in erwartet.items():
            with self.subTest(schluessel=schluessel):
                self.assertEqual(namen, set(re.findall(r"\{(\w+)\}", STRINGS[schluessel]["de"])))


class ForgeArgumenteTests(unittest.TestCase):
    """``convert <Quelle> --to <Format>``: ein Abbild statt des Pakets, im Strom, ohne Zwischenordner."""

    def test_ohne_format_bleibt_es_das_paket_wie_bisher(self) -> None:
        self.assertEqual(["convert", "q", "--to", "pkg", "-o", "z", "--kraken", "fast"], fc.convert_argumente("q", "z"))

    def test_ein_abbild_hat_kein_kraken_und_nimmt_die_zlib_stufe_nur_beim_container(self) -> None:
        self.assertEqual(["convert", "q.pkg", "--to", "ffpkg", "-o", "z"], fc.convert_argumente("q.pkg", "z", format="ffpkg"))
        self.assertEqual(["convert", "q.pkg", "--to", "ffpfsc", "-o", "z", "--level", "3"],
                         fc.convert_argumente("q.pkg", "z", format="ffpfsc", stufe=3))
        for format in ("ffpkg", "ffpfs", "exfat"):
            with self.subTest(format=format):
                self.assertNotIn("--level", fc.convert_argumente("q", "z", format=format, stufe=3))
                self.assertNotIn("--kraken", fc.convert_argumente("q", "z", format=format))

    def test_threads_und_volle_pruefung_gelten_auch_fuer_ein_abbild(self) -> None:
        argumente = fc.convert_argumente("q", "z", format="exfat", kerne=4, voll_pruefen=True)
        self.assertEqual(["--threads", "4"], argumente[argumente.index("--threads"):argumente.index("--threads") + 2])
        self.assertIn("--full-verify", argumente)

    def test_unbekannte_formate_und_stufen_werden_abgelehnt(self) -> None:
        with self.assertRaises(wz.Fehler):
            fc.convert_argumente("q", "z", format="iso")
        self.assertNotIn("--level", fc.convert_argumente("q", "z", format="ffpfsc", stufe=11), "ausserhalb von 0 bis 9")

    def test_die_abbildziele_sind_die_vier_formate_des_programms(self) -> None:
        self.assertEqual({"ffpkg", "ffpfsc", "ffpfs", "exfat"}, set(fc.ABBILD_ZIELE))

    def test_der_stamm_des_namens_bleibt_in_der_grenze_von_forge(self) -> None:
        lang = "Ein sehr langer Titel eines Spiels, der weit ueber die Grenze von dreiundsechzig Bytes hinausgeht.ffpkg"
        kurz = fc.stamm_kuerzen(lang, fc.STAMM_GRENZE)
        self.assertTrue(kurz.endswith(".ffpkg"))
        self.assertLessEqual(len(os.path.splitext(kurz)[0].encode("utf-8")), 63)
        kurz = fc.stamm_kuerzen("ä" * 60 + ".ffpfsc", fc.STAMM_GRENZE_FFPFSC)
        self.assertLessEqual(len(os.path.splitext(kurz)[0].encode("utf-8")), 58)
        self.assertEqual("Spiel.exfat", fc.stamm_kuerzen("Spiel.exfat", 63))

    def test_ein_paket_ist_eine_datei_mit_der_endung_pkg(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            datei = os.path.join(ordner, "a.PKG")
            Path(datei).write_bytes(b"x")
            self.assertTrue(fc.ist_paket(datei))
            self.assertFalse(fc.ist_paket(os.path.join(ordner, "fehlt.pkg")))
            self.assertFalse(fc.ist_paket(ordner))
            Path(os.path.join(ordner, "a.zip")).write_bytes(b"x")
            self.assertFalse(fc.ist_paket(os.path.join(ordner, "a.zip")))


class ProtokollDerAufgabenTests(unittest.TestCase):
    """``_quellbericht_ins_protokoll``: nach den Rueckfragen, vor der Arbeit - und was der Lauf einbaut."""

    @staticmethod
    def _gui(fakten=None, einbau=(), konsole="7.99", laeuft=True):
        g = GUI.__new__(GUI)
        g._t = _t
        g.is_running = laeuft
        g._log = []
        g._append_to_log = g._log.append
        g._quellfakten_der_quelle = lambda src: fakten
        g._konsole_fw_bekannt = lambda: konsole
        g._einbau_liste = lambda: list(einbau)
        return g

    def test_der_bericht_und_was_eingebaut_wird_stehen_im_protokoll(self) -> None:
        g = self._gui(fc.QuellFakten(ampr_importiert=True, ampr_fehlt=True), einbau=("AMPR EMU (Asset-Pack, zstd)", "PlayGo"))
        g._quellbericht_ins_protokoll("pack_folder", "C:/x")
        self.assertEqual("bericht.titel", g._log[0])
        self.assertTrue(g._log[1].startswith("[FEHLT] bericht.ampr_fehlt"))
        self.assertEqual("bericht.einbau|liste=AMPR EMU (Asset-Pack, zstd), PlayGo", g._log[-1])

    def test_wird_nichts_eingebaut_steht_es_da(self) -> None:
        g = self._gui(fc.QuellFakten())
        g._quellbericht_ins_protokoll("pack_folder", "C:/x")
        self.assertEqual("bericht.einbau_nichts", g._log[-1])

    def test_laesst_sich_die_quelle_nicht_pruefen_steht_auch_das_da(self) -> None:
        g = self._gui(None, einbau=("DLC EMU",))
        g._quellbericht_ins_protokoll("pack_folder", "C:/x.zip")
        self.assertEqual(["bericht.nicht_pruefbar", "bericht.einbau|liste=DLC EMU"], g._log)

    def test_die_sammelkonvertierung_und_aufgaben_ohne_zielformat_schreiben_nichts(self) -> None:
        for modus in ("batch_convert", "inspect", "ampr_manager", "dump_validator"):
            with self.subTest(modus=modus):
                g = self._gui(fc.QuellFakten())
                g._quellbericht_ins_protokoll(modus, "C:/x")
                self.assertEqual([], g._log)

    def test_nach_einem_abbruch_wird_nichts_mehr_geschrieben(self) -> None:
        g = self._gui(fc.QuellFakten(), laeuft=False)
        g._quellbericht_ins_protokoll("pack_folder", "C:/x")
        self.assertEqual([], g._log)

    def test_ein_fehler_beim_lesen_haelt_den_lauf_nicht_auf(self) -> None:
        g = self._gui(fc.QuellFakten())
        g._quellfakten_der_quelle = mock.Mock(side_effect=RuntimeError("kaputt"))
        g._quellbericht_ins_protokoll("pack_folder", "C:/x")                     # wirft nicht
        self.assertEqual([], g._log)

    def test_die_firmware_der_konsole_wird_nie_erfragt(self) -> None:
        """Der Bericht ist eine Auskunft: Er liest ``_konsole_fw_bekannt`` und oeffnet kein Fenster."""
        g = self._gui(fc.QuellFakten(sdk="10.00", firmware="11.20"), konsole=None)
        g._konsole_firmware_erfragen = mock.Mock()
        g._quellbericht_ins_protokoll("pack_folder", "C:/x")
        g._konsole_firmware_erfragen.assert_not_called()
        self.assertIn("[HINWEIS] bericht.backport_konsole_unbekannt|spiel=11.20", g._log)

    def test_ein_paket_wird_von_forge_gelesen_wie_ein_abbild(self) -> None:
        """``.pkg`` als Quelle: Forge liest es im Strom (``inspect``), die Rueckfragen der Aufgaben gelten dann auch dort."""
        g = GUI.__new__(GUI)
        g.is_running = True
        g._forge_befehlszeile = lambda: "forge-exe"
        with tempfile.TemporaryDirectory() as ordner:
            paket = os.path.join(ordner, "a.pkg")
            Path(paket).write_bytes(b"x")
            with mock.patch.object(fc, "quellfakten_lesen", return_value=fc.QuellFakten()) as lesen:
                self.assertIsNotNone(g._quellfakten_der_quelle(paket))
            lesen.assert_called_once()
            self.assertIsNone(g._quellfakten_der_quelle(os.path.join(ordner, "a.zip")), "ein Archiv liest Forge hier nicht")


class EinbauListeTests(unittest.TestCase):
    @staticmethod
    def _gui(**stand):
        g = GUI.__new__(GUI)
        g._tk_wert = lambda name, vorgabe=None: stand.get(name, vorgabe)
        g._ampr_methode = lambda: stand.get("_methode", "normal")
        g._ampr_pack_verfahren = lambda: stand.get("_verfahren", "lz4")
        return g

    def test_nichts_angehakt_nichts_eingebaut(self) -> None:
        self.assertEqual([], self._gui()._einbau_liste())

    def test_jedes_kaestchen_steht_mit_seinem_namen_da(self) -> None:
        g = self._gui(ampr_integrate_var=True, ampr_playgo_var=True, dlc_integrate_var=True, backport_integrate_var=True,
                      backport_fw_var="7")
        self.assertEqual(["AMPR EMU", "PlayGo", "DLC EMU", "BACKPORT (FW 7)"], g._einbau_liste())

    def test_asset_pack_nennt_das_packverfahren(self) -> None:
        for verfahren, name in (("zstd", "zstd"), ("lz4", "LZ4")):
            with self.subTest(verfahren=verfahren):
                g = self._gui(ampr_integrate_var=True, _methode="asset-pack", _verfahren=verfahren)
                import PS5ImageConverter_Pro_FINAL_revised as APP
                g._ampr_methode = lambda: APP.AMPR_METHODE_ASSETPACK
                self.assertEqual(["AMPR EMU (Asset-Pack, %s)" % name], g._einbau_liste())


class QuelltextTests(unittest.TestCase):
    def test_der_bericht_steht_nach_den_rueckfragen_und_vor_der_arbeit(self) -> None:
        text = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        fake = text.index("self._fake_vor_dem_lauf_klaeren(mode, src)")
        bericht = text.index("self._quellbericht_ins_protokoll(mode, src)", fake)
        arbeit = text.index("success = self._run_flexible_conversion(mode, src, dst)", fake)
        self.assertLess(fake, bericht)
        self.assertLess(bericht, arbeit)
        self.assertEqual(1, text.count("self._quellbericht_ins_protokoll(mode, src)"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
