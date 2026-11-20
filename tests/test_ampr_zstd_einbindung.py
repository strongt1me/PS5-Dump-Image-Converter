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
    "ampr_pack.voll_pruefen", "ampr_pack.voll_pruefen_hint", "ampr_pack.voll_pruefen_gesperrt",
    "ampr_zstd.pruefung_voll", "ampr_zstd.pruefung_stichprobe",
    "ampr_zstd.index_fehlt", "ampr_zstd.index_groesse", "ampr_zstd.index_passt_nicht", "ampr.index_zu_lang",
    "ampr_ng.indexspeicher_zu_klein", "ampr_ng.indexspeicher_neuere_fassung", "ampr_ng.indexspeicher_ohne_pack",
    "ampr_zstd.schon_gepackt", "ampr_zstd.lz4_pack_vorhanden", "ampr.assets_index_kept", "ampr_zstd.pack_nur_ng",
    "ampr_zstd.pack_pruefung_fehlgeschlagen", "ampr_zstd.ftp_pack_nur_ng",
    "ampr_zstd.pack_nur_ng_raus", "ampr_zstd.ftp_pack_frage", "ampr_zstd.ftp_pack_status", "backport.log_emu_bleibt",
    "amprgen.q_zstd", "amprgen.q_zstd_why", "amprgen.q_zstd_stop", "amprgen.q_zstd_stop_why", "amprgen.q_zstd_go", "amprgen.q_zstd_go_why",
    "amprgen.zstd_appmeta_hinweis",
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
    _ampr_zstd_index_abgleichen = APP.PS5ConverterGUI._ampr_zstd_index_abgleichen
    _ng_indexspeicher_warnen = APP.PS5ConverterGUI._ng_indexspeicher_warnen
    _AMPR_NG_VARIANTEN = APP.PS5ConverterGUI._AMPR_NG_VARIANTEN
    _phase_dauer_melden = APP.PS5ConverterGUI._phase_dauer_melden
    _stufe_start = APP.PS5ConverterGUI._stufe_start             # die Stufenzeile (207375e) ruft sie je Abschnitt
    _stufe_ende = APP.PS5ConverterGUI._stufe_ende
    _dauer_text = staticmethod(APP.PS5ConverterGUI._dauer_text)

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
    _AMPR_VOLL_PRUEFEN_SETTING = APP.PS5ConverterGUI._AMPR_VOLL_PRUEFEN_SETTING
    _ampr_voll_pruefen = APP.PS5ConverterGUI._ampr_voll_pruefen

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
            "Daten/a.txt": b"abc " * 100_000,
            "Daten/b.bin": os.urandom(40_000),
        }.items():
            voll = os.path.join(self.spiel, *rel.split("/"))
            os.makedirs(os.path.dirname(voll), exist_ok=True)
            Path(voll).write_bytes(daten)
        self.index = os.path.join(self.spiel, "ampr_emu.index")
        # Ein echter Index wie im Programm: der Abgleich vor dem Packen (``_ampr_zstd_index_abgleichen``) liest ihn.
        APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)._build_ampr_index_local(Path(self.spiel), Path(self.index))
        self.ausgabe = self.spiel + "_ampr_zstd"

    def test_abweichung_zum_ampr_index_bricht_vor_dem_packen_ab(self) -> None:
        """NG verwirft das ganze Pack, wenn eine gepackte Datei im ampr_emu.index fehlt oder anders gross ist."""
        Path(self.spiel, "Daten", "a.txt").write_bytes(b"anders")                          # Groesse weicht ab
        Path(self.spiel, "Daten", "neu.bin").write_bytes(b"x" * 100)                      # fehlt im Index
        s = _Stub()
        self.assertFalse(s._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng"}))
        self.assertIn("ampr_zstd.index_passt_nicht", s.text())
        self.assertIn("ampr_zstd.index_groesse [('expected', 400000), ('path', 'Daten/a.txt'), ('size', 6)]", s.text())
        self.assertIn("ampr_zstd.index_fehlt [('path', 'Daten/neu.bin')]", s.text())
        self.assertFalse(z.ist_gepackt(self.spiel), "nichts gepackt")
        self.assertFalse(os.path.exists(os.path.join(self.ausgabe, z.bandname(0))))

    def test_index_lesen_passt_zum_schreiber_des_programms(self) -> None:
        daten = Path(self.index).read_bytes()
        gelesen = z.ampr_index_lesen(daten)
        self.assertEqual(len(Path(self.spiel, "Daten", "a.txt").read_bytes()), gelesen["Daten/a.txt"])
        self.assertEqual({"eboot.bin", "sce_sys/param.json", "fakelib/libSceAmpr.sprx", "Daten/a.txt", "Daten/b.bin"},
                         set(gelesen))
        self.assertEqual([], z.ampr_index_abgleichen([("Daten/a.txt", 400_000)], gelesen))
        with self.assertRaises(z.ZstdPackFehler):
            z.ampr_index_lesen(daten[:60])
        with self.assertRaises(z.ZstdPackFehler):
            z.ampr_index_lesen(b"AMPRIDX2" + daten[8:])

    def test_indexspeicher_zu_klein_warnt_und_packt_trotzdem(self) -> None:
        """Die Rechnung ist nicht an der Konsole gemessen: nur eine Warnung (mit Vorschlag), kein Abbruch."""
        from ps5_validator.utils import ng_indexspeicher
        gerechnet: list = []
        echt = ng_indexspeicher.pruefen

        def pruefen(fassung, idx, art="", pack=None):
            gerechnet.append((fassung, idx.dateien, art, pack.dateien if pack else None))
            if art:
                return ng_indexspeicher.Befund(ng_indexspeicher.MODELL_035, False, "x", 62 * ng_indexspeicher.MIB,
                                               55 * ng_indexspeicher.MIB)
            return echt(fassung, idx, art, pack)

        s = _Stub()
        with mock.patch.object(ng_indexspeicher, "pruefen", pruefen):
            self.assertTrue(s._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng", "version": "0.3.5"}), s.text())
        self.assertEqual(("0.3.5", 5, "zstd", 2), gerechnet[0], "Index-Eintraege und die zwei gepackten Dateien")
        self.assertIn("ampr_ng.indexspeicher_zu_klein [('cap', '55'), ('need', '62'), ('version', '0.3.5')]", s.text())
        self.assertIn("ampr_ng.indexspeicher_ohne_pack", s.text())
        self.assertTrue(z.ist_gepackt(self.spiel), "gepackt wird trotzdem")

    def test_zu_kleiner_speicher_empfiehlt_die_neueste_ng_fassung(self) -> None:
        """Reicht der Speicher der gewaehlten Fassung nicht, die neueste (``NEUESTE_FASSUNG``) aber doch, nennt die Zeile sie beim Namen."""
        from ps5_validator.utils import ng_indexspeicher as ngi
        neueste = ngi.NEUESTE_FASSUNG

        def pruefen(fassung, idx, art="", pack=None, ordner=None):
            if fassung == neueste:
                return ngi.Befund(ngi.modell_fuer(fassung), True, "", 0, 0)
            return ngi.Befund(ngi.modell_fuer(fassung), False, "x", 62 * ngi.MIB, 55 * ngi.MIB)

        pack = ngi.Kopf(0, 5, 10, 2)
        s = _Stub()
        with mock.patch.object(ngi, "pruefen", pruefen):
            befund = s._ng_indexspeicher_warnen(self.index, {"variant": "ng", "version": "0.3.5"}, "zstd", pack)
        self.assertFalse(befund.passt)
        self.assertIn("ampr_ng.indexspeicher_neuere_fassung [('version', '%s')]" % neueste, s.text())
        self.assertNotIn("ampr_ng.indexspeicher_ohne_pack", s.text())

    def test_die_neueste_fassung_empfiehlt_sich_nicht_selbst(self) -> None:
        """Gegenprobe: Ist schon die neueste gewaehlt und reicht es nicht, steht keine Empfehlung da."""
        from ps5_validator.utils import ng_indexspeicher as ngi
        neueste = ngi.NEUESTE_FASSUNG

        def pruefen(fassung, idx, art="", pack=None, ordner=None):
            return ngi.Befund(ngi.modell_fuer(fassung), False, "x", 90 * ngi.MIB, 80 * ngi.MIB)

        s = _Stub()
        with mock.patch.object(ngi, "pruefen", pruefen):
            befund = s._ng_indexspeicher_warnen(self.index, {"variant": "ng", "version": neueste}, "zstd", ngi.Kopf(0, 5, 10, 2))
        self.assertFalse(befund.passt)
        self.assertIn("ampr_ng.indexspeicher_zu_klein", s.text())
        self.assertNotIn("ampr_ng.indexspeicher_neuere_fassung", s.text())

    def test_gleiches_modell_wie_die_neueste_empfiehlt_nichts(self) -> None:
        """Eine Fassung mit demselben Modell wie die neueste (z. B. 0.5.3 neben 0.5.0) bekommt die Empfehlung nie - auch nicht,
        wenn die Rechnung der neuesten (hier gestellt) durchgehen wuerde; sie wuerde nichts aendern."""
        from ps5_validator.utils import ng_indexspeicher as ngi
        neueste = ngi.NEUESTE_FASSUNG
        gleiche = "%s.3" % ".".join(neueste.split(".")[:2])     # 0.5.3 bei neuester 0.5.0
        self.assertEqual(ngi.modell_fuer(gleiche), ngi.modell_fuer(neueste), "Voraussetzung: gleiches Modell")

        def pruefen(fassung, idx, art="", pack=None, ordner=None):
            if fassung == neueste:
                return ngi.Befund(ngi.modell_fuer(fassung), True, "", 0, 0)
            return ngi.Befund(ngi.modell_fuer(fassung), False, "x", 90 * ngi.MIB, 80 * ngi.MIB)

        s = _Stub()
        with mock.patch.object(ngi, "pruefen", pruefen):
            befund = s._ng_indexspeicher_warnen(self.index, {"variant": "ng", "version": gleiche}, "zstd", ngi.Kopf(0, 5, 10, 2))
        self.assertFalse(befund.passt)
        self.assertNotIn("ampr_ng.indexspeicher_neuere_fassung", s.text())

    def test_indexspeicher_wird_nur_fuer_ng_gerechnet(self) -> None:
        s = _Stub()
        self.assertIsNone(s._ng_indexspeicher_warnen(self.index, {"variant": "test-pack", "version": "0.4.2.1"}))
        self.assertIsNone(s._ng_indexspeicher_warnen(self.index, {"variant": "ng", "version": "0.3.4"}), "vor 0.3.5 kein Modell")
        befund = s._ng_indexspeicher_warnen(self.index, {"variant": "ng", "version": "0.4.0-beta"})
        self.assertTrue(befund.passt)
        self.assertNotIn("ampr_ng.indexspeicher", s.text())

    def test_schon_gepackt_ohne_originale_wird_nicht_neu_gepackt(self) -> None:
        """Gesamtpruefung 14.11.2026, P1: Das neue Pack haette das alte ersetzt und nur noch die losen Dateien genannt."""
        s = _Stub()
        self.assertTrue(s._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng"}), s.text())
        z.originale_entfernen(self.spiel, z.index_laden(self.spiel))
        self.assertFalse(os.path.exists(os.path.join(self.spiel, "Daten", "a.txt")))
        vorher = Path(self.spiel, z.INDEX_NAME).read_bytes()
        s2 = _Stub()
        self.assertFalse(s2._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng"}))
        self.assertIn("ampr_zstd.schon_gepackt", s2.text())
        self.assertEqual(vorher, Path(self.spiel, z.INDEX_NAME).read_bytes(), "das alte Pack bleibt")
        ziel = os.path.join(self._tmp, "entpackt")
        z.entpacken_in_neuen_ordner(self.spiel, ziel)
        self.assertEqual(b"abc " * 100_000, Path(ziel, "Daten", "a.txt").read_bytes())

    def test_gegenprobe_mit_originalen_wird_neu_gepackt(self) -> None:
        """Liegt jede gepackte Datei noch lose daneben, ist das alte Pack eine Doppelung - neu packen ist erlaubt."""
        s = _Stub()
        self.assertTrue(s._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng"}), s.text())
        s2 = _Stub(stufe=5)
        self.assertTrue(s2._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng"}), s2.text())
        self.assertNotIn("ampr_zstd.schon_gepackt", s2.text())
        z.pruefen(self.spiel, self.spiel)

    def _einbau_gui(self, verfahren: str = "zstd"):
        g = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        g._log = []
        g._append_to_log = g._log.append
        g._t = lambda k, **kw: k
        g._set_status = lambda *a, **k: None
        g.is_running = True
        g._ampr_methode = lambda: APP.AMPR_METHODE_ASSETPACK
        g._ampr_pack_verfahren = lambda: verfahren
        g._tk_wert = lambda name, vorgabe="": "NG"
        g._ampr_auswahl_beim_start = lambda: {"NG": {"path": "x", "variant": "ng"}}
        g._ampr_apply_library = lambda *a, **k: True
        g._playgo_wird_eingebaut = lambda: False
        g._titel_nutzt_playgo = lambda ordner: ""
        return g

    def test_ein_pack_ohne_originale_bleibt_mit_seinem_index(self) -> None:
        """R2-P4/R4-2: Kein neuer ampr_emu.index und kein neues Pack - und auch kein Abbruch: Pack und Index bleiben, wie sie sind
        (wie das "Nein" auf die Index-Frage). Gegenprobe im naechsten Test: mit allen Originalen wird gefragt."""
        s = _Stub()
        self.assertTrue(s._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng"}), s.text())
        index_vorher = Path(self.index).read_bytes()
        pack_vorher = Path(self.spiel, z.INDEX_NAME).read_bytes()
        z.originale_entfernen(self.spiel, z.index_laden(self.spiel))
        for verfahren in ("zstd", "lz4"):
            with self.subTest(verfahren=verfahren):
                g = self._einbau_gui(verfahren)
                self.assertEqual("ampr_zstd.schon_gepackt", g._ampr_pack_hindernis(self.spiel))
                with mock.patch.object(g, "_ampr_index_neubau_erlaubt", side_effect=AssertionError("gefragt")) as frage, \
                        mock.patch.object(g, "_build_ampr_index_local", side_effect=AssertionError("Index neu")) as bau, \
                        mock.patch.object(g, "_ampr_assetpakete_bauen", side_effect=AssertionError("gepackt")) as packen:
                    self.assertTrue(g._integration_ampr(self.spiel))
                frage.assert_not_called()
                bau.assert_not_called()
                packen.assert_not_called()
                self.assertIn("ampr_zstd.schon_gepackt", g._log)
                self.assertIn("ampr.assets_index_kept", g._log)
                self.assertEqual(index_vorher, Path(self.index).read_bytes())
                self.assertEqual(pack_vorher, Path(self.spiel, z.INDEX_NAME).read_bytes())

    def test_gegenprobe_mit_originalen_entscheidet_die_index_frage(self) -> None:
        s = _Stub()
        self.assertTrue(s._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng"}), s.text())
        g = self._einbau_gui("zstd")
        self.assertEqual("", g._ampr_pack_hindernis(self.spiel))
        with mock.patch.object(g, "_ampr_index_neubau_erlaubt", return_value=False) as frage:
            self.assertTrue(g._integration_ampr(self.spiel))
        frage.assert_called_once()

    def test_lz4_pack_bei_gewaehltem_zstd(self) -> None:
        Path(self.spiel, "ampr_assets-main-lane00-vol00-000.pak").write_bytes(b"AMPRPAK4" + bytes(64))
        self.assertEqual("ampr_zstd.lz4_pack_vorhanden", self._einbau_gui("zstd")._ampr_pack_hindernis(self.spiel))
        self.assertEqual("", self._einbau_gui("lz4")._ampr_pack_hindernis(self.spiel), "mit LZ4 entscheidet der LZ4-Weg")

    def test_lz4_pack_im_ordner_bricht_ab(self) -> None:
        Path(self.spiel, "ampr_assets-main-lane00-vol00-000.pak").write_bytes(b"AMPRPAK4" + bytes(64))
        s = _Stub()
        self.assertFalse(s._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng"}))
        self.assertIn("ampr_zstd.lz4_pack_vorhanden", s.text())
        self.assertFalse(z.ist_gepackt(self.spiel))

    def _ohne_originale(self) -> None:
        s = _Stub()
        self.assertTrue(s._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng"}), s.text())
        z.originale_entfernen(self.spiel, z.index_laden(self.spiel))

    def test_abbruch_bei_der_packpruefung_ist_kein_pack_befund(self) -> None:
        """R5-1: Brach der Anwender die Suche ab, stand "schon gepackt" im Protokoll, und der Einbau lief mit True weiter."""
        self._ohne_originale()
        g = self._einbau_gui("zstd")
        g.is_running = False
        self.assertEqual("ampr_pack.abgebrochen", g._ampr_pack_hindernis(self.spiel))
        with mock.patch.object(g, "_ampr_apply_library", side_effect=AssertionError("getauscht")) as tausch:
            self.assertFalse(g._integration_ampr(self.spiel))
        tausch.assert_not_called()
        self.assertNotIn("ampr_zstd.schon_gepackt", g._log)
        self.assertNotIn("ampr.assets_index_kept", g._log)

    def test_lz4_reste_neben_dem_zstd_pack_nur_bei_gewaehltem_zstd(self) -> None:
        """R5-2: zstd-Pack mit allen Originalen plus LZ4-Rest - mit LZ4 gewaehlt kein Hindernis. Ohne Originale geht das zstd-Pack
        den LZ4-Resten vor (sonst griffe die NG-Sperre aus R5-3 nicht)."""
        s = _Stub()
        self.assertTrue(s._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng"}), s.text())
        Path(self.spiel, "ampr_assets-main-lane00-vol00-000.pak").write_bytes(b"AMPRPAK4" + bytes(64))
        self.assertEqual("", self._einbau_gui("lz4")._ampr_pack_hindernis(self.spiel))
        self.assertEqual("ampr_zstd.lz4_pack_vorhanden", self._einbau_gui("zstd")._ampr_pack_hindernis(self.spiel))
        z.originale_entfernen(self.spiel, z.index_laden(self.spiel))
        for verfahren in ("zstd", "lz4"):
            with self.subTest(verfahren=verfahren):
                self.assertEqual("ampr_zstd.schon_gepackt", self._einbau_gui(verfahren)._ampr_pack_hindernis(self.spiel))

    def test_andere_fassung_als_ng_tauscht_die_bibliothek_nicht(self) -> None:
        """R5-3: Ein zstd-Pack ohne alle Originale liest nur NG - eine andere Fassung haette libSceAmpr.sprx getauscht und das Spiel
        unlesbar gemacht. Gegenproben: nur PlayGo tauscht nichts und laeuft durch; mit NG laeuft es durch (Test weiter oben)."""
        self._ohne_originale()
        for verfahren in ("zstd", "lz4"):
            with self.subTest(verfahren=verfahren):
                g = self._einbau_gui(verfahren)
                g._ampr_auswahl_beim_start = lambda: {"NG": {"path": "x", "variant": "test-pack"}}
                with mock.patch.object(g, "_ampr_apply_library", side_effect=AssertionError("getauscht")) as tausch:
                    self.assertFalse(g._integration_ampr(self.spiel))
                tausch.assert_not_called()
                self.assertIn("ampr_zstd.pack_nur_ng", g._log)
        g = self._einbau_gui("lz4")
        g._ampr_auswahl_beim_start = lambda: {"NG": {"path": "x", "variant": "test-pack"}}
        with mock.patch.object(g, "_ampr_apply_library", side_effect=AssertionError("getauscht")) as tausch:
            self.assertTrue(g._integration_ampr(self.spiel, nur_playgo=True))
        tausch.assert_not_called()
        self.assertNotIn("ampr_zstd.pack_nur_ng", g._log)

    def test_lesefehler_bei_der_packpruefung_endet_mit_grund(self) -> None:
        """R6-1: Seit die Pruefung vor dem Bibliothekstausch steht, fiel ein OSError (Datei verschwindet beim Durchsuchen) als Ausnahme
        aus dem Einbau, statt mit Grund im Protokoll False zu liefern."""
        self._ohne_originale()
        g = self._einbau_gui("zstd")
        with mock.patch.object(z, "dateien_auswaehlen", side_effect=FileNotFoundError("weg")), \
                mock.patch.object(g, "_ampr_apply_library", side_effect=AssertionError("getauscht")) as tausch:
            self.assertFalse(g._integration_ampr(self.spiel))
        tausch.assert_not_called()
        self.assertIn("ampr_zstd.pack_pruefung_fehlgeschlagen", g._log)

    def _vorab_gui(self, variante: str):
        g = self._einbau_gui("zstd")
        g._integration_gewaehlt = lambda: True
        g._ampr_wird_eingebaut = lambda: True
        g._ampr_auswahl_beim_start = lambda: {"NG": {"path": "x", "variant": variante}}
        return g

    def test_die_ng_sperre_greift_vor_der_arbeitskopie(self) -> None:
        """R6-3: Die Sperre fiel erst in _integration_ampr - nach Arbeitskopie, Backport und DLC EMU."""
        self._ohne_originale()
        g = self._vorab_gui("test-pack")
        with mock.patch.object(g, "_integration_arbeitskopie", side_effect=AssertionError("kopiert")) as kopie:
            self.assertEqual("", g._integration_anwenden(self.spiel, ist_quellordner=True))
        kopie.assert_not_called()
        self.assertIn("ampr_zstd.pack_nur_ng", g._log)
        # Gegenprobe: mit NG geht es zur Arbeitskopie weiter.
        g = self._vorab_gui("ng")
        with mock.patch.object(g, "_integration_arbeitskopie", return_value="") as kopie:
            self.assertEqual("", g._integration_anwenden(self.spiel, ist_quellordner=True))
        kopie.assert_called_once()
        self.assertNotIn("ampr_zstd.pack_nur_ng", g._log)

    def test_vorabpruefung_ohne_pack_fragt_nichts_ab(self) -> None:
        """Ohne zstd-Pack in der Wurzel nur ein listdir - die Auswahl des Starts wird gar nicht gelesen (Tests mit schmalen Stubs)."""
        g = self._vorab_gui("test-pack")
        g._ampr_auswahl_beim_start = mock.Mock(side_effect=AssertionError("gelesen"))
        g._ampr_wird_eingebaut = mock.Mock(side_effect=AssertionError("gefragt"))
        self.assertTrue(g._ampr_einbau_passt_zum_pack(self.spiel))
        self.assertTrue(g._ampr_einbau_passt_zum_pack(os.path.join(self._tmp, "gibt_es_nicht")))
        g._ampr_auswahl_beim_start.assert_not_called()          # ein except Exception im Programm schluckte den Fehler sonst still
        g._ampr_wird_eingebaut.assert_not_called()

    def _ftp_gui(self, variante: str, wurzel: list):
        g = self._einbau_gui()
        eintraege = [{"lib": "libSceAmpr.sprx", "version": "0.9", "variant": variante, "path": "x"},
                     {"lib": "libScePlayGo.sprx", "version": "0.9", "variant": variante, "path": "y"}]
        g._ampr_scan_version_store = lambda store: eintraege
        g._fakelib_ordnername = lambda: "fakelib"
        g._ampr_ng_hinweis = lambda *a, **k: None
        g._ampr_ftp_list_entries = lambda ftp, pfad: [(n, {"type": "file"}) for n in wurzel]
        g._ampr_ftp_upload_file = mock.Mock(return_value=True)
        return g

    def test_ftp_set_kommt_nicht_in_einen_zstd_ordner(self) -> None:
        """R6-2: "APR-EMU uebertragen" legte ohne Wunsch die neueste Fassung von drakmor neben ein zstd-Pack. Seit R7-3 meldet sich die
        Sperre als eigene Ausnahme, damit der Picker nachfragen kann - hinuebergegangen ist dann noch nichts."""
        set_libs = ("libSceAmpr.sprx", "libScePlayGo.sprx")
        for libs in ((), set_libs):
            with self.subTest(libs=libs):
                g = self._ftp_gui("test-pack", ["eboot.bin", "AMPR_ZSTD.INDEX", "ampr_zstd-000.pak"])
                with self.assertRaises(APP._AmprFtpPackSperre) as ctx:
                    g._ampr_ftp_apply_set(object(), "/data/ps5/PPSA00000", "x", libs=libs)
                self.assertEqual("/data/ps5/PPSA00000", ctx.exception.args[0])
                g._ampr_ftp_upload_file.assert_not_called()
                self.assertIn("ampr_zstd.ftp_pack_nur_ng", g._log)
        # Nach ausdruecklicher Zusage des Anwenders (R7-3) geht das Set doch hinueber.
        g = self._ftp_gui("test-pack", ["eboot.bin", "ampr_zstd.index"])
        self.assertEqual((2, 0), g._ampr_ftp_apply_set(object(), "/data/ps5/PPSA00000", "x", libs=set_libs, pack_sperre=False))
        self.assertEqual(2, g._ampr_ftp_upload_file.call_count)
        # Gegenproben: NG kommt hinueber, und ohne zstd-Pack auch die andere Fassung.
        for variante, wurzel in (("ng", ["ampr_zstd.index"]), ("test-pack", ["eboot.bin", "ampr_emu.index"])):
            with self.subTest(variante=variante, wurzel=wurzel):
                g = self._ftp_gui(variante, wurzel)
                self.assertEqual((2, 0), g._ampr_ftp_apply_set(object(), "/data/ps5/PPSA00000", "x", libs=set_libs))
                self.assertNotIn("ampr_zstd.ftp_pack_nur_ng", g._log)

    def test_der_zweite_aufruf_nach_der_zusage_protokolliert_die_fassungen_nicht_noch_einmal(self) -> None:
        """R9: Nach "Ja" ruft der Picker ``_ampr_ftp_apply_set`` erneut - ``ampr.selected_version`` stand dann doppelt im Protokoll."""
        set_libs = ("libSceAmpr.sprx", "libScePlayGo.sprx")
        g = self._ftp_gui("test-pack", ["eboot.bin", "ampr_zstd.index"])
        with self.assertRaises(APP._AmprFtpPackSperre):
            g._ampr_ftp_apply_set(object(), "/data/ps5/PPSA00000", "x", libs=set_libs)
        self.assertEqual(2, g._log.count("ampr.selected_version"), "der erste Aufruf nennt beide Fassungen")
        self.assertEqual((2, 0), g._ampr_ftp_apply_set(object(), "/data/ps5/PPSA00000", "x", libs=set_libs,
                                                       pack_sperre=False, wiederholung=True))
        self.assertEqual(2, g._log.count("ampr.selected_version"), "der zweite nennt sie nicht noch einmal")
        # Gegenprobe: ohne wiederholung steht es auch beim zweiten Mal da.
        g._ampr_ftp_apply_set(object(), "/data/ps5/PPSA00000", "x", libs=set_libs, pack_sperre=False)
        self.assertEqual(4, g._log.count("ampr.selected_version"))
        # Dasselbe fuer "nichts gefunden": Der erste Aufruf nennt es, die Wiederholung nicht.
        g = self._ftp_gui("test-pack", ["eboot.bin"])
        self.assertEqual((0, 0), g._ampr_ftp_apply_set(object(), "/data/ps5/PPSA00000", "x", version="9.9", libs=set_libs))
        self.assertEqual(2, g._log.count("ampr.no_match_in_store"))
        g._ampr_ftp_apply_set(object(), "/data/ps5/PPSA00000", "x", version="9.9", libs=set_libs, wiederholung=True)
        self.assertEqual(2, g._log.count("ampr.no_match_in_store"), "die Wiederholung nennt es nicht noch einmal")
        g._ampr_ftp_apply_set(object(), "/data/ps5/PPSA00000", "x", version="9.9", libs=set_libs)
        self.assertEqual(4, g._log.count("ampr.no_match_in_store"), "Gegenprobe: ohne wiederholung steht es wieder da")

    def test_ng_wird_an_der_datei_erkannt(self) -> None:
        """R7-2: Ein von Hand benannter Ordner im Versionsordner ("0.4.1") ergibt die Variante "standard", auch wenn NG darin liegt -
        dann sperrte der Einbau zu Unrecht. Es entscheidet die Datei; nur eine nicht lesbare Datei faellt auf die Variante zurueck."""
        g = self._einbau_gui()
        ng = Path(self._tmp, "ng.sprx")
        ng.write_bytes(b"x" + APP.PS5ConverterGUI._AMPR_NG_KENNZEICHEN + b"y")
        alt = Path(self._tmp, "alt.sprx")
        alt.write_bytes(b"drakmor")
        self.assertTrue(g._ampr_bibliothek_ist_ng({"path": str(ng)}))
        self.assertTrue(g._ampr_bibliothek_ist_ng({"path": str(ng), "variant": "standard"}), "handbenannter Ordner")
        self.assertFalse(g._ampr_bibliothek_ist_ng({"path": str(alt)}))
        self.assertFalse(g._ampr_bibliothek_ist_ng({"path": str(alt), "variant": "ng"}), "die Datei sagt es, nicht das Etikett")
        self.assertFalse(g._ampr_bibliothek_ist_ng({"path": None}))
        self.assertFalse(g._ampr_bibliothek_ist_ng({}))
        # Nicht lesbar: die Variante entscheidet (Tests und Auswahlen ohne Datei).
        weg = str(Path(self._tmp, "gibt_es_nicht.sprx"))
        self.assertTrue(g._ampr_bibliothek_ist_ng({"path": weg, "variant": "NG"}))
        self.assertTrue(g._ampr_bibliothek_ist_ng({"path": weg, "variant": "ng-debug"}))
        self.assertFalse(g._ampr_bibliothek_ist_ng({"path": weg, "variant": "test-pack"}))

    def test_handbenanntes_ng_wird_im_einbau_nicht_gesperrt(self) -> None:
        self._ohne_originale()
        ng = Path(self._tmp, "ng.sprx")
        ng.write_bytes(b"x" + APP.PS5ConverterGUI._AMPR_NG_KENNZEICHEN + b"y")
        g = self._einbau_gui("zstd")
        g._ampr_auswahl_beim_start = lambda: {"NG": {"path": str(ng), "variant": "standard"}}
        with mock.patch.object(g, "_ampr_apply_library", return_value=True) as tausch:
            self.assertTrue(g._integration_ampr(self.spiel))
        tausch.assert_called_once()
        self.assertNotIn("ampr_zstd.pack_nur_ng", g._log)

    def test_ftp_picker_fragt_vor_der_ablehnung_nach(self) -> None:
        """R7-3: Der Grund steht im Picker (Statuszeile), und das Set geht nach ausdruecklichem Ja doch hinueber; Vorgabe ist Nein."""
        g = self._einbau_gui()
        with mock.patch.object(APP.messagebox, "askyesno", return_value=True) as frage:
            self.assertTrue(g._ampr_ftp_pack_nachfragen("fenster", "/data/ps5/PPSA00000"))
        titel, text = frage.call_args.args
        self.assertEqual("ampr.picker_title", titel)
        self.assertEqual("ampr_zstd.ftp_pack_frage", text)
        self.assertEqual("no", frage.call_args.kwargs["default"])
        self.assertEqual("fenster", frage.call_args.kwargs["parent"])
        with mock.patch.object(APP.messagebox, "askyesno", return_value=False):
            self.assertFalse(g._ampr_ftp_pack_nachfragen("fenster", "/x"))

    def test_der_picker_behandelt_die_sperre(self) -> None:
        import ast
        import inspect
        quelle = inspect.getsource(APP.PS5ConverterGUI._show_ampr_ftp_picker)
        baum = ast.parse("class _K:\n" + quelle)
        getauscht = next(k for k in ast.walk(baum) if isinstance(k, ast.FunctionDef) and k.name == "_getauscht"
                         and "_AmprFtpPackSperre" in ast.unparse(k))
        # Struktur: die Sperre steht ganz vorn, dort fragt der Picker; Ja ruft im Faden erneut ohne Sperre, Nein setzt die Statuszeile.
        erste = getauscht.body[0]
        self.assertIsInstance(erste, ast.If)
        self.assertEqual("isinstance(fehler, _AmprFtpPackSperre)", ast.unparse(erste.test))
        frage = next(k for k in erste.body if isinstance(k, ast.If))
        self.assertEqual("self._ampr_ftp_pack_nachfragen(win, pfad)", ast.unparse(frage.test))
        ja = ast.unparse(ast.Module(body=frage.body, type_ignores=[]))
        nein = ast.unparse(ast.Module(body=frage.orelse, type_ignores=[]))
        self.assertIn("_im_faden(", ja)
        # Die beiden Aufrufe von _ampr_ftp_apply_set im Picker: der erste mit den Vorgaben (Sperre an), der zweite nach "Ja" - und die
        # Schluesselwoerter gehoeren zu demselben Aufruf.
        aufrufe = [k for k in ast.walk(ast.parse("class _K:\n" + quelle))
                   if isinstance(k, ast.Call) and ast.unparse(k.func) == "self._ampr_ftp_apply_set"]
        woerter = sorted(sorted(kw.arg for kw in k.keywords) for k in aufrufe)
        self.assertEqual([[], ["pack_sperre", "wiederholung"]], woerter)
        zweiter = next(k for k in aufrufe if k.keywords)
        self.assertEqual({"pack_sperre": False, "wiederholung": True}, {kw.arg: kw.value.value for kw in zweiter.keywords})
        self.assertNotIn("pack_sperre=False", nein)
        self.assertIn("status_var.set(self._t('ampr_zstd.ftp_pack_status'))", nein)
        self.assertIsInstance(erste.body[-1], ast.Return, "danach nicht noch 'fehlgeschlagen' melden")

    # --- R7-1: der Backport laesst ein vorhandenes AMPR EMU / NG liegen --------------------------------------------------

    def _backport_gui(self, satz_lib: str):
        g = self._einbau_gui()
        werte = {"backport_fw_var": 4, "ampr_integrate_var": False, "ampr_playgo_var": False}
        g._tk_wert = lambda n, d=None: werte.get(n, d)
        g._load_setting = lambda k, d=None: d
        g._backport_ziel_deckung_melden = lambda *a, **k: None
        g._backport_luecken_melden = lambda *a, **k: None
        g._backport_korrekturen_anwenden = lambda *a, **k: []
        g._backport_fremdlibs_klaeren = lambda *a, **k: []
        g._backport_param_json = lambda *a, **k: 0
        g._backport_fakelib_basis = lambda: self._tmp
        g._backport_fakelib_minimal = lambda: False
        g._backport_fakelib_auswahl = lambda basis, firmware, ordner: [satz_lib, os.path.join(os.path.dirname(satz_lib), "libSceFoo.sprx")]
        g._fakelib_ordnername = lambda: "fakelib"
        return g

    def _satz(self) -> str:
        satz = os.path.join(self._tmp, "satz")
        os.makedirs(satz)
        Path(satz, "libSceAmpr.sprx").write_bytes(b"[AMPR_EMU] drakmor " * 50)
        Path(satz, "libSceFoo.sprx").write_bytes(b"foo")
        return os.path.join(satz, "libSceAmpr.sprx")

    def test_backport_beim_erstellen_ueberschreibt_ng_nicht(self) -> None:
        """Jeder Bibliothekssatz bringt libSceAmpr.sprx von drakmor mit; sie ersetzte NG in einem zstd-Ordner ohne Originale."""
        self._ohne_originale()
        lib = Path(self.spiel, "fakelib", "libSceAmpr.sprx")
        lib.parent.mkdir(exist_ok=True)
        ng = b"..ampr-emu-ng 0.4.0.." + bytes(300)
        lib.write_bytes(ng)
        g = self._backport_gui(self._satz())
        self.assertTrue(g._integration_backport(self.spiel), g._log)
        self.assertEqual(ng, lib.read_bytes(), "NG wurde ueberschrieben")
        self.assertEqual(b"foo", Path(self.spiel, "fakelib", "libSceFoo.sprx").read_bytes(), "die uebrigen Bibliotheken kommen weiter")
        self.assertTrue(z.ist_gepackt(self.spiel))
        self.assertIn("backport.log_emu_bleibt", g._log)

    def test_gegenprobe_backport_ohne_vorhandenes_emu_kopiert_den_satz(self) -> None:
        satz_lib = self._satz()
        for nummer, vorhanden in enumerate((None, b"Sony-Original " * 40)):
            with self.subTest(vorhanden=vorhanden):
                spiel = os.path.join(self._tmp, "ohne_%d" % nummer)
                os.makedirs(os.path.join(spiel, "fakelib"))
                ziel = Path(spiel, "fakelib", "libSceAmpr.sprx")
                if vorhanden is not None:
                    ziel.write_bytes(vorhanden)
                g = self._backport_gui(satz_lib)
                self.assertTrue(g._integration_backport(spiel), g._log)
                self.assertIn(b"[AMPR_EMU]", ziel.read_bytes(), "ohne Emulator im Spiel gilt der Satz wie bisher")
                self.assertNotIn("backport.log_emu_bleibt", g._log)

    # --- R8-2: der Generationen-Assistent ("pro Spiel") fragt bei zstd-Pack und Nicht-NG-Fassung ------------------------------

    def _gen_gui(self, antwort: str = "stop", pack_auf_konsole: bool = False):
        g = self._einbau_gui()
        g._ampr_gen_frage = mock.Mock(return_value=antwort)
        g._ampr_ftp_zstd_pack_da = mock.Mock(return_value=pack_auf_konsole)
        return g

    def _lib(self, variante: str = "test-pack", lib: str = "libSceAmpr.sprx") -> dict:
        return {"lib": lib, "path": os.path.join(self._tmp, "gibt_es_nicht.sprx"), "variant": variante}

    def test_der_assistent_fragt_bei_zstd_pack_und_nicht_ng(self) -> None:
        Path(self.spiel, z.INDEX_NAME).write_bytes(b"x")
        for antwort, soll in (("weiter", True), ("stop", False), ("", False)):
            with self.subTest(antwort=antwort):
                g = self._gen_gui(antwort)
                self.assertIs(soll, g._ampr_gen_zstd_vertraeglich("fenster", None, True, self.spiel, [self._lib()]))
                g._ampr_gen_frage.assert_called_once()
                args = g._ampr_gen_frage.call_args.args
                self.assertEqual(("fenster", "amprgen.q_zstd", "amprgen.q_zstd_why"), args[:3])
                self.assertEqual(["stop", "weiter"], [o[0] for o in args[3]], "Vorgabe ist das Erste: Abbrechen")

    def test_der_assistent_fragt_sonst_nicht(self) -> None:
        Path(self.spiel, z.INDEX_NAME.upper()).write_bytes(b"x")          # Schreibung egal
        faelle = {
            "NG": ([self._lib("ng")], self.spiel),
            "NG-Debug": ([self._lib("ng-debug")], self.spiel),
            "nur PlayGo": ([self._lib("test-pack", "libScePlayGo.sprx")], self.spiel),
            "fester Weg ohne Spielordner": ([self._lib()], ""),
            "keine Bibliothek": ([], self.spiel),
        }
        for name, (libs, ordner) in faelle.items():
            with self.subTest(fall=name):
                g = self._gen_gui()
                self.assertTrue(g._ampr_gen_zstd_vertraeglich("fenster", None, True, ordner, libs))
                g._ampr_gen_frage.assert_not_called()
        # ohne zstd-Pack: nichts zu fragen, auch bei einer anderen Fassung als NG
        ohne = os.path.join(self._tmp, "ohne_pack")
        os.makedirs(ohne)
        Path(ohne, "ampr_emu.index").write_bytes(b"x")
        g = self._gen_gui()
        self.assertTrue(g._ampr_gen_zstd_vertraeglich("fenster", None, True, ohne, [self._lib()]))
        self.assertTrue(g._ampr_gen_zstd_vertraeglich("fenster", None, True, os.path.join(self._tmp, "weg"), [self._lib()]))
        g._ampr_gen_frage.assert_not_called()

    def test_der_assistent_fragt_auf_der_konsole_nach_dem_index_im_spielordner(self) -> None:
        g = self._gen_gui("weiter", pack_auf_konsole=True)
        self.assertTrue(g._ampr_gen_zstd_vertraeglich("fenster", "ftp", False, "/data/ps5/PPSA00000", [self._lib()]))
        g._ampr_ftp_zstd_pack_da.assert_called_once_with("ftp", "/data/ps5/PPSA00000")
        g._ampr_gen_frage.assert_called_once()
        g = self._gen_gui("stop", pack_auf_konsole=False)
        self.assertTrue(g._ampr_gen_zstd_vertraeglich("fenster", "ftp", False, "/data/ps5/PPSA00000", [self._lib()]))
        g._ampr_gen_frage.assert_not_called()

    def test_ein_abbild_nur_aus_appmeta_bekommt_einen_hinweis_statt_der_frage(self) -> None:
        """R9-1: Ein eingehaengtes Abbild hat keinen Ordner, in den sich sehen liesse (``/system_data/priv/appmeta/<ID>``) - dort lag nie
        ein ampr_zstd.index, also wurde nie gefragt. Eine Frage bei jedem Abbild waere zu viel; es bleibt der Hinweis im Protokoll."""
        zeilen: list[str] = []
        g = self._gen_gui("stop", pack_auf_konsole=True)
        self.assertTrue(g._ampr_gen_zstd_vertraeglich("fenster", "ftp", False, "/system_data/priv/appmeta/PPSA00000", [self._lib()],
                                                      "appmeta", zeilen.append))
        self.assertEqual(["!! amprgen.zstd_appmeta_hinweis"], zeilen)
        g._ampr_gen_frage.assert_not_called()
        g._ampr_ftp_zstd_pack_da.assert_not_called()
        # ohne Protokollzeile (Aufrufer ohne melde) kein Fehler; mit NG gar kein Hinweis
        self.assertTrue(g._ampr_gen_zstd_vertraeglich("fenster", "ftp", False, "/x", [self._lib()], "appmeta"))
        zeilen.clear()
        self.assertTrue(g._ampr_gen_zstd_vertraeglich("fenster", "ftp", False, "/x", [self._lib("ng")], "appmeta", zeilen.append))
        self.assertEqual([], zeilen)
        # Gegenprobe: ein Spiel mit Ordner auf der Konsole (herkunft leer) wird weiter gefragt.
        g = self._gen_gui("weiter", pack_auf_konsole=True)
        self.assertTrue(g._ampr_gen_zstd_vertraeglich("fenster", "ftp", False, "/data/ps5/PPSA00000", [self._lib()], "", zeilen.append))
        g._ampr_gen_frage.assert_called_once()
        self.assertEqual([], zeilen)

    def test_der_assistent_ruft_die_frage_nach_der_fassungswahl(self) -> None:
        import ast
        import inspect
        quelle = inspect.getsource(APP.PS5ConverterGUI._ampr_gen_automatik)
        baum = ast.parse("class _K:\n" + quelle)
        zeilen = {k.value: k.lineno for k in ast.walk(baum)
                  if isinstance(k, ast.Constant) and k.value in ("amprgen.lib_chosen", "amprgen.step_config")}
        frage = next(k for k in ast.walk(baum) if isinstance(k, ast.If) and "_ampr_gen_zstd_vertraeglich" in ast.unparse(k.test))
        self.assertEqual("not self._ampr_gen_zstd_vertraeglich(fenster, ftp, lokal, spielpfad, gewaehlt_libs, herkunft, melde)",
                         ast.unparse(frage.test))
        self.assertLess(zeilen["amprgen.lib_chosen"], frage.lineno, "erst die Fassungen, dann die Frage")
        self.assertLess(frage.lineno, zeilen["amprgen.step_config"], "vor dem Ablegen und vor der config.ini")
        self.assertTrue(any(isinstance(k, ast.Return) for k in frage.body), "Nein bricht ab")
        self.assertIn("amprgen.cancelled", ast.unparse(ast.Module(body=frage.body, type_ignores=[])))

    def test_emulator_bleibt_nur_fuer_ampr_und_playgo_mit_kennzeichen(self) -> None:
        from ps5_validator.utils import ps5_backport as bp
        ordner = Path(self._tmp, "emu")
        ordner.mkdir()
        (ordner / "libSceAmpr.sprx").write_bytes(b"..ampr-emu-ng 0.4.0..")        # NG
        (ordner / "libScePlayGo.sprx").write_bytes(b"playgo_stub.dat")
        (ordner / "libSceFoo.sprx").write_bytes(b"[AMPR_EMU]")                    # Kennzeichen, aber keine AMPR-/PlayGo-Datei
        self.assertTrue(bp.emulator_bleibt(str(ordner / "libSceAmpr.sprx")))
        self.assertTrue(bp.emulator_bleibt(str(ordner / "libScePlayGo.sprx")))
        self.assertFalse(bp.emulator_bleibt(str(ordner / "libSceFoo.sprx")))
        (ordner / "libSceAmpr.sprx").write_bytes(b"Sony-Original")
        self.assertFalse(bp.emulator_bleibt(str(ordner / "libSceAmpr.sprx")), "ein Sony-Original bleibt nicht")
        self.assertFalse(bp.emulator_bleibt(str(ordner / "gibt_es_nicht" / "libSceAmpr.sprx")))

    def test_das_backport_fenster_haelt_es_wie_der_einbau(self) -> None:
        import ast
        import inspect
        quelle = inspect.getsource(APP.PS5ConverterGUI._backport_worker)
        baum = ast.parse("class _K:\n" + quelle)
        self.assertIn("backport.log_emu_bleibt", quelle)
        # Struktur, nicht nur Text: In der Schleife ueber die Bibliotheken steht das Kopieren im else-Zweig der Emulator-Pruefung.
        schleife = next(k for k in ast.walk(baum) if isinstance(k, ast.For) and ast.unparse(k.iter) == "quellen"
                        and "emulator_bleibt" in ast.unparse(k))
        pruefung = next(k for k in schleife.body if isinstance(k, ast.If))
        self.assertEqual("ps5_backport.emulator_bleibt(ziel_datei)", ast.unparse(pruefung.test))
        self.assertNotIn("copy2", ast.unparse(ast.Module(body=pruefung.body, type_ignores=[])))
        self.assertIn("shutil.copy2(quelle, ziel_datei)", ast.unparse(ast.Module(body=pruefung.orelse, type_ignores=[])))
        self.assertNotIn("count=len(quellen)", ast.unparse(baum), "die Statuszeile zaehlt nur, was wirklich kopiert wird")

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

    def test_ohne_schalter_wird_nur_eine_stichprobe_geprueft_und_das_protokoll_sagt_es(self) -> None:
        """Nutzerwunsch 12.11.2026 (Forge-Vorbild): Vorgabe ist die Stichprobe, mit dem Schalter alles."""
        s = _Stub()
        self.assertTrue(s._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng"}), s.text())
        self.assertIn("ampr_zstd.pruefung_stichprobe", s.text())
        self.assertNotIn("ampr_zstd.pruefung_voll", s.text())
        self.assertIn("ampr_pack.geprueft", s.text())

    def test_mit_schalter_wird_vollstaendig_geprueft(self) -> None:
        s = _Stub()
        s.einstellungen = {"ampr_voll_pruefen": True}
        self.assertTrue(s._ampr_zstdpakete_bauen(self.spiel, self.index, {"variant": "ng"}), s.text())
        self.assertIn("ampr_zstd.pruefung_voll", s.text())
        self.assertNotIn("ampr_zstd.pruefung_stichprobe", s.text())

    def test_der_schalter_liest_auch_text_aus_einer_handgeschriebenen_einstellung(self) -> None:
        s = _Stub()
        for wert, soll in ((True, True), (False, False), ("true", True), ("Ja", True), ("0", False), ("", False),
                           (None, False), (1, True)):
            s.einstellungen = {"ampr_voll_pruefen": wert}
            self.assertEqual(soll, s._ampr_voll_pruefen(), repr(wert))

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
