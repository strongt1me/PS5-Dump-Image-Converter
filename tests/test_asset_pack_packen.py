# -*- coding: utf-8 -*-
"""Der Knopf PACKEN im Fenster "Asset-Pack" (KONSOLE, Knopf 11): zstd-Packs direkt in einen fertigen Spielordner.

Anlass (17.11.2026, Forum-Frage): "Gibt es das Tool her, aus einem reinen Dump-Ordner wieder einen Dump-Ordner mit zstd zu
machen?" Das Fenster konnte bis dahin nur pruefen und entpacken; gebaut wurde ausschliesslich beim Erstellen eines Abbilds.

Abgesichert ist, was den Ordner des Anwenders schuetzt (er ist hier das Original, keine Arbeitskopie):

* gepackt wird in einen Nachbarordner, erst nach der Pruefung kommt etwas in den Spielordner;
* die Originale bleiben liegen, ausser der Anwender verlangt es - dann wird jedes Byte geprueft, nie nur eine Stichprobe;
* ein Ordner mit Asset-Pack, ohne eboot.bin, mit fremder AMPR-Fassung oder mit belegtem Zwischenordner wird nicht angefasst;
* ein Abbruch laesst weder einen Zwischenordner noch halbe Baender zurueck.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("asset_pack_packen")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import ampr_zstdpack as z          # noqa: E402
from ps5_validator.utils import i18n                        # noqa: E402

NEU = [
    "assetpack_tool.pack_button", "assetpack_tool.status_packing", "assetpack_tool.phase_vorbereiten",
    "assetpack_tool.msg_schon_gepackt", "assetpack_tool.msg_kein_spielordner", "assetpack_tool.ask_packen",
    "assetpack_tool.ask_originale", "assetpack_tool.pack_ordner_wurzel", "assetpack_tool.pack_lib_nicht_ng",
    "assetpack_tool.pack_lib_fehlt", "assetpack_tool.pack_index_gebaut", "assetpack_tool.pack_ausgabe_da",
    "assetpack_tool.pack_platz", "assetpack_tool.pack_hinweis", "assetpack_tool.pack_ok",
    "assetpack_tool.ask_lib_ueber_sm", "assetpack_tool.pack_lib_ueber_sm",
]

NG_BIB = b"..ampr-emu-ng 0.4.1.."


class UebersetzungsTests(unittest.TestCase):
    def test_alle_schluessel_in_allen_sprachen(self) -> None:
        for schluessel in NEU:
            self.assertIn(schluessel, i18n.STRINGS, schluessel)
            for sprache in i18n.SUPPORTED_LANGUAGES:
                self.assertTrue(i18n.STRINGS[schluessel].get(sprache), "%s fehlt auf %s" % (schluessel, sprache))

    def test_platzhalter_sind_in_allen_sprachen_gleich(self) -> None:
        import re
        for schluessel in NEU:
            mengen = {s: frozenset(re.findall(r"\{(\w+)\}", i18n.STRINGS[schluessel][s]))
                      for s in i18n.SUPPORTED_LANGUAGES}
            self.assertEqual(1, len(set(mengen.values())), "%s: %s" % (schluessel, mengen))

    def test_der_knopf_steht_im_fenster_zwischen_pruefen_und_entpacken(self) -> None:
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        a = quelle.index('("assetpack_tool.check_button", _pruefen)')
        b = quelle.index('("assetpack_tool.pack_button", _packen)')
        c = quelle.index('("assetpack_tool.unpack_button", _entpacken)')
        self.assertLess(a, b)
        self.assertLess(b, c)


class _Stub:
    """Gerade so viel Programm, wie ``_asset_pack_zstd_in_ordner`` anfasst - ohne Tk, ohne Hauptprotokoll."""

    _AMPR_SPRX_NAME = APP.PS5ConverterGUI._AMPR_SPRX_NAME
    _AMPR_INDEX_NAME = APP.PS5ConverterGUI._AMPR_INDEX_NAME
    _AMPR_NG_KENNZEICHEN = b"ampr-emu-ng"
    _ampr_ist_ng_datei = classmethod(APP.PS5ConverterGUI._ampr_ist_ng_datei.__func__)
    _asset_pack_zstd_in_ordner = APP.PS5ConverterGUI._asset_pack_zstd_in_ordner
    _dauer_text = staticmethod(APP.PS5ConverterGUI._dauer_text)
    _EIGENES_PROFIL_ENDUNG = APP.PS5ConverterGUI._EIGENES_PROFIL_ENDUNG
    _AMPR_ZSTD_REGELDATEI_SETTING = APP.PS5ConverterGUI._AMPR_ZSTD_REGELDATEI_SETTING
    _ampr_zstd_arbeiter = APP.PS5ConverterGUI._ampr_zstd_arbeiter

    def __init__(self) -> None:
        self.einstellungen: dict = {}
        self.voll = False
        self.hauptprotokoll: list[str] = []

    def _t(self, schluessel: str, **kw) -> str:
        return "%s %s" % (schluessel, sorted(kw.items())) if kw else schluessel

    def _load_setting(self, name, vorgabe=None):
        return self.einstellungen.get(name, vorgabe)

    def _ampr_zstd_stufe(self) -> int:
        return 3

    def _ampr_voll_pruefen(self) -> bool:
        return self.voll

    def _fmt_bytes(self, n: int) -> str:
        return "%d B" % n

    def _append_to_log(self, text: str) -> None:       # nur der Indexbauer meldet hierhin (Sonderfaelle der Pfade)
        self.hauptprotokoll.append(str(text))

    def _build_ampr_index_local(self, root: Path, output: Path):
        return APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)._build_ampr_index_local(root, output)


def _spiel(basis: str, mit_lib: bool = True) -> str:
    """Ein kleiner Dump-Ordner wie von der Konsole: eboot.bin, sce_sys, Nutzdaten."""
    spiel = os.path.join(basis, "Spiel")
    dateien = {
        "eboot.bin": b"ELF" + bytes(500),
        "sce_sys/param.json": b"{}",
        "Daten/a.txt": b"abc " * 100_000,
        "Daten/b.bin": bytes(range(256)) * 400,
        "Daten/unter/c.dat": b"xyz" * 50_000,
    }
    if mit_lib:
        dateien["fakelib/libSceAmpr.sprx"] = NG_BIB
    for rel, daten in dateien.items():
        voll = os.path.join(spiel, *rel.split("/"))
        os.makedirs(os.path.dirname(voll), exist_ok=True)
        Path(voll).write_bytes(daten)
    return spiel


def _inhalt(wurzel: str) -> dict[str, bytes]:
    erg = {}
    for ordner, _d, namen in os.walk(wurzel):
        for n in namen:
            voll = os.path.join(ordner, n)
            erg[os.path.relpath(voll, wurzel).replace(os.sep, "/")] = Path(voll).read_bytes()
    return erg


@unittest.skipUnless(z.verfuegbar(), "zstandard fehlt")
class KernTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="asset_pack_packen_")
        self.addCleanup(shutil.rmtree, self._tmp, True)
        self.spiel = _spiel(self._tmp)
        self.zeilen: list[str] = []
        self.s = _Stub()
        self.phasen: list[tuple[str, float]] = []

    def _lauf(self, **kw):
        kw.setdefault("abbruch", lambda: False)
        return self.s._asset_pack_zstd_in_ordner(
            self.spiel, melden=self.zeilen.append, phase=lambda n, a: self.phasen.append((n, a)), **kw)

    def test_packt_in_den_spielordner_und_laesst_die_originale(self) -> None:
        vorher = _inhalt(self.spiel)
        erg = self._lauf()
        self.assertTrue(z.ist_gepackt(self.spiel))
        self.assertTrue(os.path.isfile(os.path.join(self.spiel, z.bandname(0))))
        self.assertEqual(0, erg["originale_entfernt"])
        self.assertGreaterEqual(erg["dateien"], 3)
        nachher = _inhalt(self.spiel)
        for rel, daten in vorher.items():
            self.assertEqual(daten, nachher[rel], rel)        # keine Originaldatei angefasst
        self.assertFalse(os.path.exists(self.spiel + "_ampr_zstd"), "Der Zwischenordner blieb liegen")
        z.pruefen(self.spiel, self.spiel)                      # Byte fuer Byte gegen die Dateien im Ordner
        self.assertTrue({n for n, _a in self.phasen} >= {"packen", "pruefen"})

    def test_legt_einen_fehlenden_index_an_und_laesst_einen_vorhandenen(self) -> None:
        index = os.path.join(self.spiel, "ampr_emu.index")
        self.assertFalse(os.path.exists(index))
        self._lauf()
        self.assertTrue(os.path.isfile(index))
        self.assertIn("assetpack_tool.pack_index_gebaut", "\n".join(self.zeilen))

        # Zweiter Ordner mit vorhandenem Index: bleibt Byte fuer Byte.
        zweiter = _spiel(os.path.join(self._tmp, "zwei"))
        self.s._build_ampr_index_local(Path(zweiter), Path(zweiter, "ampr_emu.index"))
        vorher = Path(zweiter, "ampr_emu.index").read_bytes()
        self.zeilen.clear()
        self.s._asset_pack_zstd_in_ordner(zweiter, melden=self.zeilen.append, abbruch=lambda: False)
        self.assertEqual(vorher, Path(zweiter, "ampr_emu.index").read_bytes())
        self.assertNotIn("assetpack_tool.pack_index_gebaut", "\n".join(self.zeilen))

    def test_originale_entfernen_prueft_vorher_jedes_byte_und_entpacken_stellt_her(self) -> None:
        vorher = _inhalt(self.spiel)
        self.s.voll = False                                    # die Einstellung sagt "Stichprobe" ...
        erg = self._lauf(originale_entfernen=True)
        text = "\n".join(self.zeilen)
        self.assertIn("ampr_zstd.pruefung_voll", text)          # ... der Haken erzwingt trotzdem die Vollpruefung
        self.assertNotIn("ampr_zstd.pruefung_stichprobe", text)
        self.assertGreaterEqual(erg["originale_entfernt"], 3)
        self.assertFalse(os.path.exists(os.path.join(self.spiel, "Daten", "a.txt")))
        self.assertTrue(os.path.isfile(os.path.join(self.spiel, "eboot.bin")))      # Systemdateien bleiben
        z.entpacken_in_ordner(self.spiel)
        nachher = _inhalt(self.spiel)
        for rel, daten in vorher.items():
            self.assertEqual(daten, nachher[rel], rel)

    def test_ohne_haken_gilt_die_einstellung_stichprobe(self) -> None:
        self.s.voll = False
        self._lauf()
        self.assertIn("ampr_zstd.pruefung_stichprobe", "\n".join(self.zeilen))
        self.assertIn("ampr_pack.quellen_bleiben", "\n".join(self.zeilen))

    def test_fremde_ampr_fassung_wird_abgewiesen(self) -> None:
        Path(self.spiel, "fakelib", "libSceAmpr.sprx").write_bytes(b"drakmor 0.4.2.1")
        with self.assertRaises(z.ZstdPackFehler) as ctx:
            self._lauf()
        self.assertIn("assetpack_tool.pack_lib_nicht_ng", str(ctx.exception))
        self.assertFalse(z.ist_gepackt(self.spiel))
        self.assertFalse(os.path.exists(os.path.join(self.spiel, "ampr_emu.index")), "Nichts angelegt")

    def test_fehlende_bibliothek_mit_bestaetigung_packt_und_nennt_update_emulators(self) -> None:
        """NG laeuft auch ueber ShadowMount+ (Nutzer 17.11.2026): mit der Bestaetigung wird gepackt, der Hinweis nennt die Falle."""
        spiel = _spiel(os.path.join(self._tmp, "sm"), mit_lib=False)
        zeilen: list[str] = []
        self.s._asset_pack_zstd_in_ordner(spiel, melden=zeilen.append, abbruch=lambda: False, ng_ueber_shadowmount=True)
        self.assertTrue(z.ist_gepackt(spiel))
        self.assertIn("assetpack_tool.pack_lib_ueber_sm", "\n".join(zeilen))
        for sprache in i18n.SUPPORTED_LANGUAGES:        # die Falle steht in jeder Sprache im Hinweis und in der Frage
            for schluessel in ("assetpack_tool.pack_hinweis", "assetpack_tool.ask_lib_ueber_sm"):
                self.assertIn("update_emulators", i18n.STRINGS[schluessel][sprache], (schluessel, sprache))

    def test_bestaetigung_ersetzt_keine_fremde_bibliothek(self) -> None:
        """Eine drakmor-Bibliothek im Ordner bleibt ein Hindernis, auch mit der ShadowMount+-Bestaetigung."""
        Path(self.spiel, "fakelib", "libSceAmpr.sprx").write_bytes(b"drakmor 0.4.2.1")
        with self.assertRaises(z.ZstdPackFehler) as ctx:
            self._lauf(ng_ueber_shadowmount=True)
        self.assertIn("assetpack_tool.pack_lib_nicht_ng", str(ctx.exception))

    def test_fehlende_bibliothek_haelt_an_und_aendert_nichts(self) -> None:
        """Ohne Bestaetigung wird bei fehlender Bibliothek nicht gepackt; auch kein Index angelegt."""
        spiel = _spiel(os.path.join(self._tmp, "ohne"), mit_lib=False)
        vorher = _inhalt(spiel)
        with self.assertRaises(z.ZstdPackFehler) as ctx:
            self.s._asset_pack_zstd_in_ordner(spiel, melden=self.zeilen.append, abbruch=lambda: False)
        self.assertIn("assetpack_tool.pack_lib_fehlt", str(ctx.exception))
        self.assertFalse(z.ist_gepackt(spiel))
        self.assertEqual(vorher, _inhalt(spiel), "Der Ordner wurde veraendert")
        self.assertFalse(os.path.exists(spiel + "_ampr_zstd"))

    def test_belegter_zwischenordner_wird_nicht_angefasst(self) -> None:
        ausgabe = self.spiel + "_ampr_zstd"
        os.makedirs(ausgabe)
        Path(ausgabe, "meine.txt").write_bytes(b"gehoert dem Anwender")
        with self.assertRaises(z.ZstdPackFehler) as ctx:
            self._lauf()
        self.assertIn("assetpack_tool.pack_ausgabe_da", str(ctx.exception))
        self.assertEqual(b"gehoert dem Anwender", Path(ausgabe, "meine.txt").read_bytes())
        self.assertFalse(z.ist_gepackt(self.spiel))

    def test_laufwerkswurzel_wird_abgewiesen(self) -> None:
        wurzel = os.path.abspath(os.sep)
        with self.assertRaises(z.ZstdPackFehler) as ctx:
            self.s._asset_pack_zstd_in_ordner(wurzel, melden=self.zeilen.append, abbruch=lambda: False)
        self.assertIn("assetpack_tool.pack_ordner_wurzel", str(ctx.exception))

    def test_abbruch_laesst_nichts_zurueck(self) -> None:
        vorher = _inhalt(self.spiel)
        zaehler = {"n": 0}

        def _abbruch() -> bool:
            zaehler["n"] += 1
            return zaehler["n"] > 3           # nach der Suche, mitten im Packen

        with self.assertRaises(z.ZstdPackFehler):
            self.s._asset_pack_zstd_in_ordner(self.spiel, melden=self.zeilen.append, abbruch=_abbruch)
        self.assertFalse(os.path.exists(self.spiel + "_ampr_zstd"), "Zwischenordner blieb liegen")
        self.assertFalse(z.ist_gepackt(self.spiel))
        nachher = _inhalt(self.spiel)
        for rel, daten in vorher.items():
            self.assertEqual(daten, nachher[rel], rel)
        self.assertFalse([n for n in nachher if n.startswith("ampr_zstd")], "halbe Baender im Spielordner")

    def test_abbruch_in_der_pruefung_uebernimmt_nichts(self) -> None:
        with mock.patch.object(z, "pruefen", side_effect=z.ZstdPackFehler("ampr_pack.abgebrochen")):
            with self.assertRaises(z.ZstdPackFehler):
                self._lauf(originale_entfernen=True)
        self.assertFalse(z.ist_gepackt(self.spiel))
        self.assertTrue(os.path.isfile(os.path.join(self.spiel, "Daten", "a.txt")), "Original geloescht ohne Pruefung")
        self.assertFalse(os.path.exists(self.spiel + "_ampr_zstd"))

    def test_ein_fehler_beim_loeschen_der_originale_wird_gemeldet(self) -> None:
        with mock.patch.object(z, "originale_entfernen", side_effect=z.ZstdPackFehler("kaputt")):
            with self.assertRaises(z.ZstdPackFehler) as ctx:
                self._lauf(originale_entfernen=True)
        self.assertIn("ampr_pack.originale_fehlgeschlagen", str(ctx.exception))
        self.assertTrue(z.ist_gepackt(self.spiel), "Das Pack liegt vor dem Loeschen schon vollstaendig da")

    def test_nutzerregeln_neben_dem_ordner_halten_dateien_lose(self) -> None:
        Path(self.spiel + "_ampr_pack.toml").write_text(
            '[pack]\ndefault_action = "compress"\n\n[[rule]]\naction = "loose"\ninclude = ["Daten/unter/**"]\n',
            encoding="utf-8")
        self._lauf(originale_entfernen=True)
        self.assertTrue(os.path.isfile(os.path.join(self.spiel, "Daten", "unter", "c.dat")), "Lose Datei geloescht")
        self.assertFalse(os.path.exists(os.path.join(self.spiel, "Daten", "a.txt")))
        self.assertIn("ampr_zstd.regeln", "\n".join(self.zeilen))


try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                      # pragma: no cover
    tk = None
    _WURZEL = None
    TK_DA = False


def _schleife(grenze: float, bis=None) -> None:
    ende = time.monotonic() + grenze

    def _takt() -> None:
        if (bis is not None and bis()) or time.monotonic() > ende:
            _WURZEL.quit()
        else:
            _WURZEL.after(10, _takt)

    _WURZEL.after(0, _takt)
    _WURZEL.mainloop()


def _widgets(widget):
    for kind in widget.winfo_children():
        yield kind
        yield from _widgets(kind)


@unittest.skipUnless(TK_DA and z.verfuegbar(), "keine Anzeige oder zstandard fehlt")
class FensterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="asset_pack_packen_fenster_")
        self.addCleanup(shutil.rmtree, self._tmp, True)
        # Das Format der config.ini ist gemerkt (sonst fragte PACKEN einmal mit einem echten Fenster): ShadowMount+ bis beta11.
        self.app._sm_format_setzen("v1")
        self.addCleanup(self.app._sm_format_setzen, "")
        vorher = set(_WURZEL.winfo_children())
        self.app._show_asset_pack_werkzeug()
        _WURZEL.update_idletasks()
        neu = [w for w in _WURZEL.winfo_children() if w not in vorher and isinstance(w, tk.Toplevel)]
        self.assertTrue(neu, "Kein Fenster geoeffnet.")
        self.fenster = neu[0]
        self.addCleanup(self._schliessen)

    def _schliessen(self) -> None:
        try:
            if self.fenster.winfo_exists():
                self.fenster.destroy()
        except tk.TclError:
            pass
        self.app._asset_pack_win = None

    def _knopf(self, schluessel: str):
        text = self.app._t(schluessel)
        for w in _widgets(self.fenster):
            try:
                if str(w.cget("text")) == text:
                    return w
            except tk.TclError:
                continue
        self.fail("Knopf fehlt: " + text)

    def _ordner_eintragen(self, pfad: str) -> None:
        eintrag = next(w for w in _widgets(self.fenster) if w.winfo_class() in ("Entry", "TEntry"))
        eintrag.delete(0, "end")
        eintrag.insert(0, pfad)

    def _protokoll(self) -> str:
        for w in _widgets(self.fenster):
            if w.winfo_class() == "Text":
                return w.get("1.0", "end")
        self.fail("Kein Protokollfeld")

    def _fertig(self, grenze: float = 120.0) -> None:
        pruefen = self._knopf("assetpack_tool.check_button")
        _schleife(grenze, bis=lambda: str(pruefen.cget("state")) == "normal")
        self.assertEqual("normal", str(pruefen.cget("state")), "Der Lauf endete nicht")

    def test_knopf_ist_da_und_bei_leerem_fenster_frei(self) -> None:
        self.assertEqual("normal", str(self._knopf("assetpack_tool.pack_button").cget("state")))

    def test_ohne_ordner_wird_gewarnt(self) -> None:
        with mock.patch.object(APP.messagebox, "showwarning") as warnung, \
                mock.patch.object(APP.messagebox, "askyesno") as frage:
            self._knopf("assetpack_tool.pack_button").invoke()
        self.assertEqual(1, warnung.call_count)
        self.assertIn(self.app._t("assetpack_tool.msg_choose_folder"), warnung.call_args[0])
        frage.assert_not_called()

    def test_ordner_ohne_eboot_wird_abgewiesen(self) -> None:
        leer = os.path.join(self._tmp, "Elternordner")
        os.makedirs(os.path.join(leer, "Spiel1"))
        self._ordner_eintragen(leer)
        with mock.patch.object(APP.messagebox, "showwarning") as warnung, \
                mock.patch.object(APP.messagebox, "askyesno") as frage:
            self._knopf("assetpack_tool.pack_button").invoke()
        self.assertIn(self.app._t("assetpack_tool.msg_kein_spielordner"), warnung.call_args[0])
        frage.assert_not_called()

    def test_ordner_mit_asset_pack_wird_abgewiesen(self) -> None:
        spiel = _spiel(self._tmp)
        _Stub()._asset_pack_zstd_in_ordner(spiel, melden=lambda _z: None, abbruch=lambda: False)
        self._ordner_eintragen(spiel)
        with mock.patch.object(APP.messagebox, "showwarning") as warnung, \
                mock.patch.object(APP.messagebox, "askyesno") as frage:
            self._knopf("assetpack_tool.pack_button").invoke()
        self.assertIn(self.app._t("assetpack_tool.msg_schon_gepackt"), warnung.call_args[0])
        frage.assert_not_called()

    def test_absage_auf_die_erste_frage_aendert_nichts(self) -> None:
        spiel = _spiel(self._tmp)
        vorher = _inhalt(spiel)
        self._ordner_eintragen(spiel)
        with mock.patch.object(APP.messagebox, "askyesno", return_value=False) as frage:
            self._knopf("assetpack_tool.pack_button").invoke()
        self.assertEqual(1, frage.call_count)                  # keine zweite Frage nach den Originalen
        self.assertEqual(vorher, _inhalt(spiel))
        self.assertEqual("normal", str(self._knopf("assetpack_tool.check_button").cget("state")))

    def test_packen_mit_originalen_laeuft_bis_zum_ergebnis(self) -> None:
        spiel = _spiel(self._tmp)
        vorher = _inhalt(spiel)
        self._ordner_eintragen(spiel)
        with mock.patch.object(APP.messagebox, "askyesno", side_effect=[True, False]) as frage:
            self._knopf("assetpack_tool.pack_button").invoke()
            self._fertig()
        self.assertEqual(2, frage.call_count)
        text = self._protokoll()
        self.assertNotIn("[FEHLER]", text)
        self.assertIn("Fertig:", text)
        self.assertTrue(z.ist_gepackt(spiel))
        nachher = _inhalt(spiel)
        for rel, daten in vorher.items():
            self.assertEqual(daten, nachher[rel], rel)
        self.assertEqual(self.app._t("assetpack_tool.status_done"),
                         next(w for w in _widgets(self.fenster) if w.winfo_class() == "Label"
                              and str(w.cget("text")) == self.app._t("assetpack_tool.status_done")).cget("text"))
        # PRUEFEN erkennt das neue Pack (derselbe Ordner, ohne neu zu waehlen).
        self._knopf("assetpack_tool.check_button").invoke()
        self._fertig()
        self.assertIn(self.app._t("assetpack_tool.log_check_gut").strip(), self._protokoll())

    def test_ohne_bibliothek_fragt_das_fenster_zuerst_nach_shadowmount(self) -> None:
        spiel = _spiel(self._tmp, mit_lib=False)
        vorher = _inhalt(spiel)
        self._ordner_eintragen(spiel)
        with mock.patch.object(APP.messagebox, "askyesno", return_value=False) as frage:
            self._knopf("assetpack_tool.pack_button").invoke()
        self.assertEqual(1, frage.call_count)                      # Vorgabe Nein: nach der ersten Absage Schluss
        self.assertIn(self.app._t("assetpack_tool.ask_lib_ueber_sm"), frage.call_args[0])
        self.assertEqual("no", frage.call_args[1].get("default"))
        self.assertEqual(vorher, _inhalt(spiel))

    def test_die_schluessel_heissen_je_nach_shadowmount_fassung_anders(self) -> None:
        """Bis 1.7beta11 update_emulators/auto_update_ampr, ab 1.7beta12 [emulators] update_enabled (Nutzerhinweis 17.11.2026).

        Beide Schalter muessen genannt sein, wie im NG-Hinweis des Programms (``ampr.ng_update_emulators``).
        """
        for schluessel in ("assetpack_tool.ask_lib_ueber_sm", "assetpack_tool.pack_lib_ueber_sm",
                           "assetpack_tool.pack_hinweis"):
            self.app._sm_format_setzen("v1")
            alt = self.app._t(schluessel)
            self.assertIn("update_emulators=0", alt, schluessel)
            self.assertIn("auto_update_ampr=0", alt, schluessel)
            self.assertNotIn("update_enabled", alt, schluessel)
            self.app._sm_format_setzen("v2")
            neu = self.app._t(schluessel)
            self.assertIn("[emulators] update_enabled", neu, schluessel)
            self.assertIn("[emulators] auto_update_ampr", neu, schluessel)
            self.assertNotIn("update_emulators", neu, schluessel)

    def test_packen_klaert_das_format_vor_den_fragen(self) -> None:
        spiel = _spiel(self._tmp)
        self._ordner_eintragen(spiel)
        reihenfolge: list[str] = []
        with mock.patch.object(self.app, "_sm_format_klaeren", side_effect=lambda **kw: reihenfolge.append("format")), \
                mock.patch.object(APP.messagebox, "askyesno",
                                  side_effect=lambda *a, **kw: reihenfolge.append("frage") or False):
            self._knopf("assetpack_tool.pack_button").invoke()
        self.assertEqual(["format", "frage"], reihenfolge)

    def test_ohne_bibliothek_packt_das_fenster_nach_bestaetigung(self) -> None:
        spiel = _spiel(self._tmp, mit_lib=False)
        self._ordner_eintragen(spiel)
        with mock.patch.object(APP.messagebox, "askyesno", side_effect=[True, True, False]) as frage:
            self._knopf("assetpack_tool.pack_button").invoke()
            self._fertig()
        self.assertEqual(3, frage.call_count)                      # ShadowMount+, Packen, Originale
        text = self._protokoll()
        self.assertNotIn("[FEHLER]", text)
        self.assertIn("update_emulators", text)
        self.assertTrue(z.ist_gepackt(spiel))

    def test_packen_ohne_originale_und_wieder_entpacken(self) -> None:
        spiel = _spiel(self._tmp)
        vorher = _inhalt(spiel)
        self._ordner_eintragen(spiel)
        with mock.patch.object(APP.messagebox, "askyesno", side_effect=[True, True]):
            self._knopf("assetpack_tool.pack_button").invoke()
            self._fertig()
        self.assertNotIn("[FEHLER]", self._protokoll())
        self.assertFalse(os.path.exists(os.path.join(spiel, "Daten", "a.txt")))
        with mock.patch.object(APP.messagebox, "askyesnocancel", return_value=False), \
                mock.patch.object(APP.messagebox, "askyesno", return_value=True):
            self._knopf("assetpack_tool.unpack_button").invoke()
            self._fertig()
        nachher = _inhalt(spiel)
        for rel, daten in vorher.items():
            self.assertEqual(daten, nachher[rel], rel)
        self.assertFalse(z.ist_gepackt(spiel))


if __name__ == "__main__":
    unittest.main()
