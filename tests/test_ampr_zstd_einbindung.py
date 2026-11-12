"""Tests fuer die Einbindung der zstd-Packs ins Programm (``_ampr_zstdpakete_bauen``, Einstellungen, Kommandozeile)."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("ampr_zstd_einbindung")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import ampr_zstdpack as z          # noqa: E402
from ps5_validator.utils import i18n                        # noqa: E402

SCHLUESSEL = [
    "settings_dialog.verfahren_label", "settings_dialog.verfahren_lz4", "settings_dialog.verfahren_zstd",
    "settings_dialog.verfahren_hint", "settings_dialog.zstd_stufe_label", "settings_dialog.zstd_stufe_5",
    "settings_dialog.zstd_stufe_9", "settings_dialog.zstd_stufe_19", "settings_dialog.zstd_stufe_22",
    "ampr_zstd.bibliothek_fehlt", "ampr_zstd.nur_ng", "ampr_zstd.start", "ampr_zstd.status", "ampr_zstd.auswahl",
    "ampr_zstd.pfad_ungueltig", "ampr_zstd.nichts_zu_packen", "ampr_zstd.gepackt", "ampr_zstd.uebernommen",
    "ampr_zstd.hinweis_ng", "ampr_zstd.fehlgeschlagen", "ampr_zstd.ausgabe_belegt", "ampr_zstd.pfad_doppelt",
    "ampr_zstd.zu_viele_baender", "ampr_zstd.index_pruefsumme", "ampr_zstd.band_ungueltig",
    "ampr_zstd.band_pruefsumme", "ampr_zstd.regeln", "ampr_zstd.regeln_ignoriert", "ampr_zstd.regeln_lose",
    "ampr_zstd.regeldatei_fehlt", "settings_dialog.regeldatei_label", "settings_dialog.regeldatei_hint",
    "settings_dialog.regeldatei_keine", "settings_dialog.regeldatei_waehlen", "settings_dialog.regeldatei_entfernen",
    "filetype.toml", "dialog.title.choose_regeldatei",
    "ampr_zstd.arbeiter", "log.phase_dauer", "phase.entpacken", "phase.integration", "phase.zstd_packen",
    "phase.zstd_pruefen", "phase.zstd_uebernehmen", "phase.zstd_originale", "phase.abbild_bauen",
]


class UebersetzungsTests(unittest.TestCase):
    def test_alle_schluessel_in_allen_sprachen(self) -> None:
        for schluessel in SCHLUESSEL:
            self.assertIn(schluessel, i18n.STRINGS, schluessel)
            for sprache in i18n.SUPPORTED_LANGUAGES:
                self.assertTrue(i18n.STRINGS[schluessel].get(sprache), "%s fehlt auf %s" % (schluessel, sprache))

    def test_platzhalter_sind_in_allen_sprachen_gleich(self) -> None:
        import re
        for schluessel in SCHLUESSEL:
            mengen = {s: set(re.findall(r"\{(\w+)\}", i18n.STRINGS[schluessel][s])) for s in i18n.SUPPORTED_LANGUAGES}
            self.assertEqual(1, len({frozenset(m) for m in mengen.values()}), "%s: %s" % (schluessel, mengen))


class _Stub:
    """Gerade so viel Programm, wie ``_ampr_zstdpakete_bauen`` anfasst."""

    _AMPR_NG_KENNZEICHEN = b"ampr-emu-ng"
    _ampr_ist_ng_datei = classmethod(APP.PS5ConverterGUI._ampr_ist_ng_datei.__func__)
    _ampr_zstdpakete_bauen = APP.PS5ConverterGUI._ampr_zstdpakete_bauen
    _phase_dauer_melden = APP.PS5ConverterGUI._phase_dauer_melden

    def __init__(self, stufe: int = 3) -> None:
        self.protokoll: list[str] = []
        self.status: list[str] = []
        self.is_running = True
        self._stufe = stufe
        self._ampr_originale_weglassen = False
        self._ampr_ordner_ist_kopie = False
        self._pack_infotext = "x"
        self.hinweis_gerufen = 0

    def _t(self, schluessel: str, **kw) -> str:
        return "%s %s" % (schluessel, sorted(kw.items())) if kw else schluessel

    def _append_to_log(self, text: str) -> None:
        self.protokoll.append(str(text))

    def _set_status(self, text: str) -> None:
        self.status.append(text)

    regelquelle = ""
    einstellungen: dict = {}
    _AMPR_ZSTD_REGELDATEI_SETTING = APP.PS5ConverterGUI._AMPR_ZSTD_REGELDATEI_SETTING
    _ampr_zstd_regeldatei = APP.PS5ConverterGUI._ampr_zstd_regeldatei

    def _load_setting(self, name, vorgabe=None):
        return self.einstellungen.get(name, vorgabe)

    def _ampr_eigenes_profil_uebernehmen(self, ausgabe: str) -> str:
        """Wie das Original: kopiert die Regeldatei neben dem Spielordner nach ``ausgabe/ampr_pack.toml``."""
        if not self.regelquelle:
            return ""
        os.makedirs(ausgabe, exist_ok=True)
        ziel = os.path.join(ausgabe, "ampr_pack.toml")
        shutil.copy2(self.regelquelle, ziel)
        return ziel

    def _ampr_zstd_stufe(self) -> int:
        return self._stufe

    def _ampr_pack_arbeiter(self) -> int:
        return 2

    _ampr_zstd_arbeiter = APP.PS5ConverterGUI._ampr_zstd_arbeiter

    def _ampr_pack_fortschritt(self, prozent: float, phase: str) -> None:
        self.letzter_fortschritt = (prozent, phase)

    def _fmt_bytes(self, n: int) -> str:
        return "%d B" % n

    def _ampr_pack_konsolenhinweis(self, ordner: str) -> None:
        self.hinweis_gerufen += 1

    def text(self) -> str:
        return "\n".join(self.protokoll)


@unittest.skipUnless(z.verfuegbar(), "zstandard fehlt")
class BauenTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="zstd_einbindung_")
        self.addCleanup(shutil.rmtree, self._tmp, True)
        self.spiel = os.path.join(self._tmp, "Spiel")
        for rel, daten in {
            "eboot.bin": b"ELF" + bytes(500),
            "sce_sys/param.json": b"{}",
            "fakelib/libSceAmpr.sprx": b"..ampr-emu-ng 0.3.0..",
            "ampr_emu.index": b"AMPRIDX3",
            "Daten/a.txt": b"abc " * 100_000,
            "Daten/b.bin": os.urandom(40_000),
        }.items():
            voll = os.path.join(self.spiel, *rel.split("/"))
            os.makedirs(os.path.dirname(voll), exist_ok=True)
            Path(voll).write_bytes(daten)
        self.index = os.path.join(self.spiel, "ampr_emu.index")
        self.ausgabe = self.spiel + "_ampr_zstd"

    def test_ng_wird_gepackt_und_uebernommen(self) -> None:
        s = _Stub()
        self.assertTrue(s._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng"}), s.text())
        self.assertTrue(z.ist_gepackt(self.spiel))
        self.assertTrue(os.path.isfile(os.path.join(self.spiel, z.bandname(0))))
        self.assertTrue(os.path.isfile(os.path.join(self.spiel, "Daten", "a.txt")), "Originale bleiben ohne Wunsch")
        self.assertFalse(os.path.exists(self.ausgabe), "kein Rest neben dem Spielordner")
        self.assertEqual(1, s.hinweis_gerufen)
        self.assertEqual("", s._pack_infotext)
        z.pruefen(self.spiel, self.spiel)
        self.assertIn("ampr_zstd.hinweis_ng", s.text())

    def test_protokoll_nennt_dauer_je_abschnitt_und_die_packfaeden(self) -> None:
        """Forum-Bericht 12.11.2026: Wo die Zeit eines langen Laufs blieb, muss das Protokoll zeigen."""
        s = _Stub()
        self.assertTrue(s._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng"}), s.text())
        zeilen = [z_ for z_ in s.protokoll if z_.startswith("log.phase_dauer")]
        phasen = [p for z_ in zeilen for p in ("phase.zstd_packen", "phase.zstd_pruefen", "phase.zstd_uebernehmen")
                  if "'%s'" % p in z_]
        self.assertEqual(["phase.zstd_packen", "phase.zstd_pruefen", "phase.zstd_uebernehmen"], phasen, s.text())
        self.assertTrue(all("0:00:0" in z_ for z_ in zeilen), zeilen)
        alle = min(32, os.cpu_count() or 2)
        self.assertTrue(any(z_.startswith("ampr_zstd.arbeiter") and "('count', %d)" % alle in z_
                            for z_ in s.protokoll), "ohne gespeicherte Zahl packt zstd mit allen Kernen (wie Forge)")

    def test_gespeicherte_workerzahl_gilt_fuer_zstd_die_vorgabe_nicht(self) -> None:
        s = _Stub()
        self.assertEqual(0, s._ampr_zstd_arbeiter(), "nichts gespeichert: alle Kerne")
        s.einstellungen = {"worker_count": 3}
        try:
            self.assertEqual(3, s._ampr_zstd_arbeiter())
            self.assertTrue(s._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng"}), s.text())
            self.assertTrue(any("('count', 3)" in z_ for z_ in s.protokoll if z_.startswith("ampr_zstd.arbeiter")))
            s.einstellungen = {"worker_count": "kaputt"}
            self.assertEqual(0, s._ampr_zstd_arbeiter(), "unlesbar: nie ein Absturz, alle Kerne")
        finally:
            _Stub.einstellungen = {}

    def test_originale_entfernen_hat_eine_eigene_dauerzeile(self) -> None:
        s = _Stub()
        s._ampr_originale_weglassen = True
        s._ampr_ordner_ist_kopie = True
        self.assertTrue(s._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng"}), s.text())
        self.assertTrue(any("'phase.zstd_originale'" in z_ for z_ in s.protokoll), s.text())

    def test_dauer_text_zeigt_stunden(self) -> None:
        f = APP.PS5ConverterGUI._dauer_text
        self.assertEqual("0:00:00", f(0))
        self.assertEqual("0:01:05", f(65.4))
        self.assertEqual("11:59:59", f(11 * 3600 + 59 * 60 + 59))
        self.assertEqual("0:00:00", f(-3), "nie negativ")

    def test_fehler_beim_melden_stoert_den_lauf_nicht(self) -> None:
        class Kaputt(_Stub):
            def _append_to_log(self, text: str) -> None:
                raise RuntimeError("Protokoll kaputt")
        Kaputt()._phase_dauer_melden("phase.zstd_packen", 0.0)   # darf nichts werfen

    def test_andere_fassung_wird_abgelehnt_und_nichts_geschrieben(self) -> None:
        for variante in ("test-pack", "test-debug-pack", "0.4.2.1"):
            s = _Stub()
            self.assertFalse(s._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": variante}), variante)
            self.assertIn("ampr_zstd.nur_ng", s.text())
            self.assertFalse(z.ist_gepackt(self.spiel))
            self.assertFalse(os.path.exists(self.ausgabe))

    def test_ohne_angabe_entscheidet_die_bibliothek(self) -> None:
        s = _Stub()
        self.assertTrue(s._ampr_zstdpakete_bauen(self.spiel, self.index, {}), "die Bibliothek im Ordner ist NG")
        shutil.rmtree(self.spiel + "_x", True)
        for name in os.listdir(self.spiel):
            if z.ist_packname(name):
                os.remove(os.path.join(self.spiel, name))
        Path(self.spiel, "fakelib", "libSceAmpr.sprx").write_bytes(b"sony original")
        s2 = _Stub()
        self.assertFalse(s2._ampr_zstdpakete_bauen(self.spiel, self.index, {}))
        self.assertIn("ampr_zstd.nur_ng", s2.text())

    def test_originale_weglassen_nur_bei_arbeitskopie(self) -> None:
        s = _Stub()
        s._ampr_originale_weglassen = True
        self.assertTrue(s._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng"}))
        self.assertTrue(os.path.isfile(os.path.join(self.spiel, "Daten", "a.txt")), "keine Arbeitskopie: bleibt")
        self.assertIn("ampr_pack.originale_nicht_im_quellordner", s.text())
        for name in os.listdir(self.spiel):
            if z.ist_packname(name):
                os.remove(os.path.join(self.spiel, name))
        s2 = _Stub()
        s2._ampr_originale_weglassen = True
        s2._ampr_ordner_ist_kopie = True
        self.assertTrue(s2._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng"}), s2.text())
        self.assertFalse(os.path.exists(os.path.join(self.spiel, "Daten")), "gepackte Originale sind weg")
        self.assertTrue(os.path.isfile(os.path.join(self.spiel, "eboot.bin")))
        self.assertIn("ampr_pack.originale_entfernt", s2.text())
        z.pruefen(self.spiel)                                   # der Satz traegt den Inhalt allein

    def test_abbruch_hinterlaesst_nichts(self) -> None:
        s = _Stub()
        s.is_running = False
        self.assertFalse(s._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng"}))
        self.assertFalse(z.ist_gepackt(self.spiel))
        self.assertFalse(os.path.exists(self.ausgabe))

    def test_fehler_beim_packen_ergibt_false_und_raeumt_auf(self) -> None:
        s = _Stub()
        with mock.patch.object(z, "pruefen", side_effect=z.ZstdPackFehler("ampr_zstd.inhalt_anders: x")):
            self.assertFalse(s._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng"}))
        self.assertIn("ampr_zstd.fehlgeschlagen", s.text())
        self.assertFalse(z.ist_gepackt(self.spiel), "geprueft wird vor der Uebernahme")
        self.assertFalse(os.path.exists(self.ausgabe))

    def test_eigene_regeln_bestimmen_was_lose_bleibt(self) -> None:
        regeldatei = os.path.join(self._tmp, "regeln.toml")
        Path(regeldatei).write_text(
            '[pack]\ndefault_action = "compress"\n[[rule]]\naction = "loose"\ninclude = "Daten/b.*"\n',
            encoding="utf-8")
        s = _Stub()
        s.regelquelle = regeldatei
        self.assertTrue(s._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng"}), s.text())
        index = z.index_laden(self.spiel)
        self.assertEqual(["Daten/a.txt"], [d.pfad for d in index.dateien], "b.bin bleibt wegen der Regel lose")
        self.assertTrue(os.path.isfile(os.path.join(self.spiel, "Daten", "b.bin")))
        self.assertIn("ampr_zstd.regeln_lose", s.text())
        self.assertFalse(os.path.exists(self.ausgabe), "auch die Kopie der Regeldatei wird weggeraeumt")

    def test_kaputte_regeln_brechen_ab_ohne_zu_schreiben(self) -> None:
        regeldatei = os.path.join(self._tmp, "regeln.toml")
        Path(regeldatei).write_text("das ist [kein toml", encoding="utf-8")
        s = _Stub()
        s.regelquelle = regeldatei
        self.assertFalse(s._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng"}))
        self.assertIn("ampr_zstd.fehlgeschlagen", s.text())
        self.assertFalse(z.ist_gepackt(self.spiel))
        self.assertFalse(os.path.exists(self.ausgabe))

    def _regeldatei_in_einstellungen(self) -> str:
        regeldatei = os.path.join(self._tmp, "global.toml")
        Path(regeldatei).write_text(
            '[pack]\ndefault_action = "compress"\n[[rule]]\naction = "loose"\ninclude = "Daten/b.*"\n',
            encoding="utf-8")
        return regeldatei

    def test_regeldatei_aus_den_einstellungen_gilt_ohne_datei_neben_dem_spiel(self) -> None:
        s = _Stub()
        s.einstellungen = {"ampr_zstd_regeldatei": self._regeldatei_in_einstellungen()}
        self.assertTrue(s._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng"}), s.text())
        self.assertEqual(["Daten/a.txt"], [d.pfad for d in z.index_laden(self.spiel).dateien])
        self.assertTrue(os.path.isfile(os.path.join(self.spiel, "Daten", "b.bin")))
        self.assertIn("ampr_zstd.regeln_lose", s.text())
        self.assertFalse(os.path.exists(self.ausgabe))

    def test_die_datei_neben_dem_spiel_geht_der_einstellung_vor(self) -> None:
        nebenan = os.path.join(self._tmp, "nebenan.toml")
        Path(nebenan).write_text('[pack]\ndefault_action = "compress"\n', encoding="utf-8")   # packt alles
        s = _Stub()
        s.regelquelle = nebenan
        s.einstellungen = {"ampr_zstd_regeldatei": self._regeldatei_in_einstellungen()}
        self.assertTrue(s._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng"}), s.text())
        self.assertEqual(["Daten/a.txt", "Daten/b.bin"], sorted(d.pfad for d in z.index_laden(self.spiel).dateien))

    def test_fehlende_regeldatei_wird_gemeldet_und_es_gilt_die_vorgabe(self) -> None:
        s = _Stub()
        s.einstellungen = {"ampr_zstd_regeldatei": os.path.join(self._tmp, "gibt_es_nicht.toml")}
        self.assertTrue(s._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng"}), s.text())
        self.assertIn("ampr_zstd.regeldatei_fehlt", s.text())
        self.assertEqual(["Daten/a.txt", "Daten/b.bin"], sorted(d.pfad for d in z.index_laden(self.spiel).dateien))

    def test_kaputte_regeldatei_aus_den_einstellungen_bricht_ab(self) -> None:
        kaputt = os.path.join(self._tmp, "kaputt.toml")
        Path(kaputt).write_text("das ist [kein toml", encoding="utf-8")
        s = _Stub()
        s.einstellungen = {"ampr_zstd_regeldatei": kaputt}
        self.assertFalse(s._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng"}))
        self.assertFalse(z.ist_gepackt(self.spiel))
        self.assertFalse(os.path.exists(self.ausgabe))

    def test_ohne_einstellung_ist_alles_beim_alten(self) -> None:
        s = _Stub()
        s.einstellungen = {}
        self.assertEqual("", s._ampr_zstd_regeldatei())
        s.einstellungen = {"ampr_zstd_regeldatei": "   "}
        self.assertEqual("", s._ampr_zstd_regeldatei())

    def test_ohne_bibliothek(self) -> None:
        s = _Stub()
        with mock.patch.object(z, "_zstd", None):
            self.assertFalse(s._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng"}))
        self.assertIn("ampr_zstd.bibliothek_fehlt", s.text())


class EinstellungTests(unittest.TestCase):
    class _App:
        _AMPR_PACK_VERFAHREN_SETTING = APP.PS5ConverterGUI._AMPR_PACK_VERFAHREN_SETTING
        _AMPR_ZSTD_STUFE_SETTING = APP.PS5ConverterGUI._AMPR_ZSTD_STUFE_SETTING
        _ampr_pack_verfahren = APP.PS5ConverterGUI._ampr_pack_verfahren
        _ampr_zstd_stufe = APP.PS5ConverterGUI._ampr_zstd_stufe

        def __init__(self, gespeichert: dict) -> None:
            self.gespeichert = gespeichert
            self._cli_ampr_pack_verfahren = None
            self._cli_ampr_zstd_stufe = None

        def _load_setting(self, name, vorgabe=None):
            return self.gespeichert.get(name, vorgabe)

    def test_vorgabe_ist_lz4(self) -> None:
        self.assertEqual("lz4", self._App({})._ampr_pack_verfahren())
        self.assertEqual("lz4", self._App({"ampr_pack_verfahren": "quatsch"})._ampr_pack_verfahren())
        self.assertEqual("lz4", self._App({"ampr_pack_verfahren": None})._ampr_pack_verfahren())

    def test_gespeichert_und_kommandozeile(self) -> None:
        app = self._App({"ampr_pack_verfahren": "zstd"})
        self.assertEqual("zstd", app._ampr_pack_verfahren())
        app._cli_ampr_pack_verfahren = "lz4"
        self.assertEqual("lz4", app._ampr_pack_verfahren(), "die Kommandozeile geht vor")
        self.assertEqual("zstd", self._App({"ampr_pack_verfahren": " ZSTD "})._ampr_pack_verfahren())

    def test_stufe(self) -> None:
        self.assertEqual(z.STUFE_VORGABE, self._App({})._ampr_zstd_stufe())
        self.assertEqual(19, self._App({"ampr_zstd_stufe": 19})._ampr_zstd_stufe())
        self.assertEqual(z.STUFE_VORGABE, self._App({"ampr_zstd_stufe": 99})._ampr_zstd_stufe())
        app = self._App({"ampr_zstd_stufe": 19})
        app._cli_ampr_zstd_stufe = 3
        self.assertEqual(3, app._ampr_zstd_stufe())


class KommandozeileTests(unittest.TestCase):
    def test_schalter(self) -> None:
        parser = APP._build_cli_parser()
        args = parser.parse_args(["--cli", "--ampr-pack-verfahren", "zstd", "--ampr-zstd-stufe", "12"])
        self.assertEqual("zstd", args.ampr_pack_verfahren)
        self.assertEqual(12, args.ampr_zstd_stufe)
        leer = parser.parse_args(["--cli"])
        self.assertIsNone(leer.ampr_pack_verfahren)
        self.assertIsNone(leer.ampr_zstd_stufe)
        with self.assertRaises(SystemExit):
            parser.parse_args(["--cli", "--ampr-pack-verfahren", "brotli"])


if __name__ == "__main__":
    unittest.main()
