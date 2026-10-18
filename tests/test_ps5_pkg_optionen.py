# -*- coding: utf-8 -*-
"""Der Dialog "Optionen" des PS5-PKG-Fensters (11.10.2026, Nutzerwunsch: "es fehlt der komplette Bereich Einstellungen").

Vorlage war der Dialog "Optionen" der eigenen PKG-App des Nutzers; uebernommen sind die Register, die es in diesem Fenster
gibt: Bibliothek, Darstellung, Ausgabe & Vorgaben, Wartung. Geprueft wird die Regelschicht ohne Oberflaeche
(``utils/ps5_pkg_optionen``) und der Dialog am wirklichen Fenster - mit Attrappen statt Werkzeug und Dateidialogen.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("ps5pkgoptionen")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.ui import ps5_pkg_fenster as fz          # noqa: E402
from ps5_validator.ui import ps5_pkg_optionen as ui         # noqa: E402
from ps5_validator.utils import ps5_pkg_optionen as opt     # noqa: E402
from ps5_validator.utils import ps5_pkg_werkzeug as wz      # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False


def _pumpen(sekunden: float) -> None:
    ende = time.time() + sekunden
    while time.time() < ende:
        _WURZEL.update()
        time.sleep(0.02)


def _warten(bedingung, grenze: float = 15.0) -> bool:
    ende = time.time() + grenze
    while not bedingung() and time.time() < ende:
        _WURZEL.update()
        time.sleep(0.02)
    return bool(bedingung())


def _rollbares_canvas(widget) -> "tk.Canvas | None":
    """Sucht rekursiv das Canvas aus ``_build_scrollable_body`` (erkennbar an ``yscrollcommand``)."""
    if isinstance(widget, tk.Canvas) and str(widget.cget("yscrollcommand")):
        return widget
    for kind in widget.winfo_children():
        treffer = _rollbares_canvas(kind)
        if treffer is not None:
            return treffer
    return None


class RegelTests(unittest.TestCase):
    def test_die_schluessel_stimmen_mit_denen_des_fensters_ueberein(self) -> None:
        self.assertEqual(fz.EINST_ZIEL, opt.ZIEL)
        self.assertEqual(fz.EINST_FORMAT, opt.FORMAT)
        self.assertEqual(fz.EINST_AKTION, opt.AKTION)
        self.assertEqual(fz.EINST_BIBLIOTHEK, opt.BIBLIOTHEK)

    def test_jede_vorgabe_ist_ein_erlaubter_wert(self) -> None:
        for schluessel, wert in opt.STANDARD.items():
            with self.subTest(schluessel=schluessel):
                self.assertEqual(wert, opt.normalisieren(schluessel, wert))

    def test_falsche_werte_werden_abgelehnt(self) -> None:
        for schluessel, wert in ((opt.REKURSIV, "ja"), (opt.COVER, 1), (opt.SORTIERUNG, "alter"), (opt.AKTION, "bauen"),
                                 (opt.FORMAT, "pkg"), (opt.ZIEL, 5), (opt.TEMP_ORDNER, 5),
                                 (opt.ORDNER, "C:/x"), (opt.ORDNER, [1, 2]),
                                 (opt.BIBLIOTHEK, ["", "a"]), ("gibt_es_nicht", True),
                                 (opt.PATCH_MODUS, "ja"), (opt.PATCH_MODUS, 1),
                                 (opt.MIN_FW_VERSION, "9"), (opt.MIN_FW_VERSION, "abc")):
            with self.subTest(schluessel=schluessel, wert=wert):
                self.assertIsNone(opt.normalisieren(schluessel, wert))

    def test_patch_modus_und_min_fw_version(self) -> None:
        self.assertEqual(False, opt.normalisieren(opt.PATCH_MODUS, False))
        self.assertEqual(True, opt.normalisieren(opt.PATCH_MODUS, True))
        self.assertEqual("", opt.normalisieren(opt.MIN_FW_VERSION, ""))
        self.assertEqual("9.00", opt.normalisieren(opt.MIN_FW_VERSION, "9.00"))
        self.assertEqual("9.00", opt.normalisieren(opt.MIN_FW_VERSION, " 9.00 "))
        self.assertEqual("9,00", opt.normalisieren(opt.MIN_FW_VERSION, "9,00"))

    def test_listen_verlieren_doppelte_und_das_ziel_den_rand(self) -> None:
        self.assertEqual(["a", "b"], opt.normalisieren(opt.ORDNER, ["a", "b", "a"]))
        self.assertEqual("C:/x", opt.normalisieren(opt.ZIEL, "  C:/x "))
        self.assertEqual("C:/y", opt.normalisieren(opt.TEMP_ORDNER, "  C:/y "))
        self.assertEqual("", opt.normalisieren(opt.TEMP_ORDNER, ""))

    def test_passcode_leer_oder_genau_32_druckbare_zeichen(self) -> None:
        self.assertEqual("", opt.normalisieren(opt.PASSCODE, ""))
        self.assertEqual("x" * 32, opt.normalisieren(opt.PASSCODE, "x" * 32))
        self.assertEqual(" " * 32, opt.normalisieren(opt.PASSCODE, " " * 32), "Leerzeichen sind druckbar")
        for falsch in ("x" * 31, "x" * 33, "ä" * 32, "x" * 31 + "\n", "x" * 31 + "\t"):
            with self.subTest(wert=falsch):
                self.assertIsNone(opt.normalisieren(opt.PASSCODE, falsch))

    def test_builder_kennt_nur_lpp_und_ppt(self) -> None:
        self.assertEqual("lpp", opt.normalisieren(opt.BUILDER, "lpp"))
        self.assertEqual("ppt", opt.normalisieren(opt.BUILDER, "ppt"))
        for falsch in ("", "LPP", "anderes", None, 1):
            with self.subTest(wert=falsch):
                self.assertIsNone(opt.normalisieren(opt.BUILDER, falsch))
        self.assertEqual("lpp", opt.STANDARD[opt.BUILDER])

    def test_passcode_wird_in_der_rueckfrage_nicht_im_klartext_gezeigt(self) -> None:
        geheim = ("geheim" * 6)[:32]
        self.assertEqual(32, len(geheim))
        zeilen = opt.unterschiede({opt.PASSCODE: ""}, {opt.PASSCODE: geheim})
        self.assertEqual(1, len(zeilen))
        self.assertNotIn("geheim", zeilen[0])
        self.assertIn("gesetzt", zeilen[0])

    def test_lesen_ersetzt_unbrauchbares_durch_die_vorgabe(self) -> None:
        gelesen = opt.lesen(lambda schluessel, vorgabe: "kaputt")
        self.assertEqual(opt.STANDARD[opt.SORTIERUNG], gelesen[opt.SORTIERUNG])
        self.assertEqual([], gelesen[opt.ORDNER])
        self.assertEqual(set(opt.BEKANNT), set(gelesen))

    def test_import_meldet_unbekanntes_und_falsches(self) -> None:
        gueltig, probleme = opt.importieren_pruefen({opt.COVER: False, "fremd": 1, opt.SORTIERUNG: "x"})
        self.assertEqual({opt.COVER: False}, gueltig)
        self.assertEqual(2, len(probleme))
        self.assertTrue(any("fremd" in p for p in probleme))
        self.assertTrue(any(opt.SORTIERUNG in p for p in probleme))

    def test_import_einer_leeren_oder_fremden_datei(self) -> None:
        for daten in ([], "text", 5, None):
            with self.subTest(daten=daten):
                gueltig, probleme = opt.importieren_pruefen(daten)
                self.assertEqual({}, gueltig)
                self.assertTrue(probleme)
        gueltig, probleme = opt.importieren_pruefen({})
        self.assertEqual({}, gueltig)
        self.assertTrue(probleme, "eine leere Datei ist ein Problem, kein stilles Nichts")

    def test_unterschiede_nennen_nur_was_sich_aendert(self) -> None:
        alt = dict(opt.STANDARD)
        zeilen = opt.unterschiede(alt, {opt.COVER: False, opt.SORTIERUNG: "titel"})
        self.assertEqual(1, len(zeilen))
        self.assertIn(opt.COVER, zeilen[0])

    def test_zuruecksetzen_beruehrt_bibliothek_und_ordner_nicht(self) -> None:
        werte = opt.zuruecksetzen_werte()
        self.assertNotIn(opt.BIBLIOTHEK, werte)
        self.assertNotIn(opt.ORDNER, werte)
        self.assertEqual(opt.STANDARD, werte)
        self.assertIsNot(opt.STANDARD, werte, "eine Kopie - niemand soll die Vorgaben veraendern")

    def test_die_suche_geht_tief_findet_spielordner_und_meidet_papierkorb(self) -> None:
        with tempfile.TemporaryDirectory() as wurzel:
            def datei(*teile: str) -> str:
                pfad = os.path.join(wurzel, *teile)
                os.makedirs(os.path.dirname(pfad), exist_ok=True)
                Path(pfad).write_bytes(b"x")
                return pfad

            a = datei("a", "b", "tief.pkg")
            oben = datei("oben.PKG")
            datei("spiel", "sce_sys", "param.json")
            datei("spiel", "innen.pkg")                       # in einem Spielordner wird nicht weitergesucht
            datei("$RECYCLE.BIN", "weg.pkg")
            datei("a", "text.txt")
            gefunden = opt.ordner_durchsuchen(wurzel, wz.ordner_ist_spiel)
            self.assertEqual({a, oben, os.path.join(wurzel, "spiel")}, set(gefunden))

    def test_ein_spielordner_ist_seine_eigene_quelle(self) -> None:
        with tempfile.TemporaryDirectory() as wurzel:
            os.makedirs(os.path.join(wurzel, "sce_sys"))
            Path(wurzel, "sce_sys", "param.json").write_text("{}", encoding="utf-8")
            self.assertEqual([wurzel], opt.ordner_durchsuchen(wurzel, wz.ordner_ist_spiel))

    def test_die_grenze_schuetzt_vor_einem_ganzen_laufwerk(self) -> None:
        with tempfile.TemporaryDirectory() as wurzel:
            for i in range(30):
                Path(wurzel, "p%02d.pkg" % i).write_bytes(b"x")
            self.assertEqual(10, len(opt.ordner_durchsuchen(wurzel, wz.ordner_ist_spiel, grenze=10)))

    def test_jeder_neue_text_ist_zweisprachig(self) -> None:
        for schluessel, text in STRINGS.items():
            if schluessel.startswith("ps5pkg.opt_") or schluessel in ("ps5pkg.nav_options", "ps5pkg.selected_caption",
                                                                       "ps5pkg.meta_method"):
                with self.subTest(schluessel=schluessel):
                    self.assertTrue(text["de"].strip() and text["en"].strip())
                    self.assertNotEqual("", text["de"])


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class DialogTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        self.ordner = tempfile.mkdtemp(prefix="ps5pkg_opt_")
        self.addCleanup(lambda: APP._rmtree_force(self.ordner, ignore_errors=True))
        self.pakete = {}
        for name, titel, tid, groesse in (("alpha.pkg", "Alpha Spiel", "PPSA00001", 2 * 1024 ** 3),
                                          ("beta.pkg", "Beta Rennen", "PPSA00002", 700 * 1024 ** 2)):
            pfad = os.path.join(self.ordner, name)
            Path(pfad).write_bytes(b"pkg")
            self.pakete[pfad] = wz.PaketInfo(
                pfad=pfad, groesse=groesse, typ="FullDebug", content_id="EP0000-%s_00-TESTTESTTESTTEST" % tid,
                title_id=tid, titel=titel, param={"contentVersion": "01.000.000", "conceptId": "1",
                                                  "applicationCategoryType": 0})
        for s in (mock.patch.object(fz.Ps5PkgFenster, "_werkzeug", return_value="werkzeug"),
                  mock.patch.object(wz, "dotnet_ordner", return_value="dotnet"),
                  mock.patch.object(wz, "lesen", side_effect=lambda w, p, a=None, **k: self.pakete[p])):
            s.start()
            self.addCleanup(s.stop)
        self.dialoge: dict[str, list] = {"info": [], "fehler": [], "frage": []}
        for name, ziel, antwort in (("showinfo", "info", None), ("showerror", "fehler", None), ("askyesno", "frage", True)):
            m = mock.patch.object(fz.messagebox, name, side_effect=lambda *a, _z=ziel, _r=antwort, **k: (
                self.dialoge[_z].append(a), _r)[1])
            m.start()
            self.addCleanup(m.stop)
        for schluessel in (*opt.STANDARD, opt.ORDNER, opt.BIBLIOTHEK):
            self.app._save_setting(schluessel, [] if schluessel in (opt.ORDNER, opt.BIBLIOTHEK) else opt.STANDARD[schluessel])
        self.f = fz.oeffnen(self.app, APP.UI_SCHRIFT, APP.MONO_SCHRIFT, APP.pt)
        self.addCleanup(self._schliessen)

    def _schliessen(self) -> None:
        try:
            if self.f.win.winfo_exists():
                self.f._job = None
                self.f._uebergabe = None
                self.f.win.destroy()
        except tk.TclError:
            pass
        _pumpen(0.05)

    def _laden(self) -> None:
        self.f._pakete_hinzufuegen(list(self.pakete), waehlen=True)
        self.assertTrue(_warten(lambda: len(self.f.pakete) == len(self.pakete) and self.f.aktuell is not None))

    def _dialog(self) -> "ui.Optionen":
        self.f._optionen_oeffnen()
        _pumpen(0.3)
        dialog = getattr(self.f, ui.DIALOG_ATTRIBUT)
        self.assertIsNotNone(dialog)
        return dialog

    def _gespeichert(self, schluessel: str):
        return self.app._load_setting(schluessel, None)

    # ---------------- Aufbau ----------------
    def test_die_navigation_hat_den_eintrag_optionen(self) -> None:
        self.assertEqual(["umwandeln", "bibliothek", "extras", "optionen"], list(self.f._nav))
        self.assertEqual("Optionen", self.f._nav["optionen"][2].cget("text"))

    def test_der_eintrag_optionen_ist_anklickbar_und_keine_seite(self) -> None:
        """Ein erzeugtes Klickereignis erreicht ein verdecktes Fenster nicht - geprueft wird die Bindung und der Weg dahinter."""
        for widget in self.f._nav["optionen"]:
            self.assertTrue(widget.bind("<Button-1>"), "Klick nicht gebunden")
        self.assertNotIn("optionen", self.f.seiten, "Optionen ist ein Dialog, keine Seite")
        self.assertIn(self.f.aktuelle_seite, ("umwandeln", "bibliothek"))

    def test_der_dialog_hat_fuenf_register_und_ein_zweiter_aufruf_holt_ihn_nach_vorn(self) -> None:
        dialog = self._dialog()
        self.assertEqual(["bibliothek", "darstellung", "ausgabe", "bau", "wartung"], list(dialog._register_tabs))
        self.assertEqual(["Bibliothek", "Darstellung", "Ausgabe & Vorgaben", "Bau", "Wartung"],
                         [t.cget("text") for t, _s in dialog._register_tabs.values()])
        self.assertIs(dialog, ui.oeffnen(self.f))
        for schluessel in dialog._register_tabs:
            dialog.zeigen(schluessel)                      # keines wirft

    def test_register_bau_rollt_statt_abzuschneiden(self) -> None:
        """Nutzerfrage 18.10.2026 nach dem Extras-Fund im Fenster "PS5 PKG Dump & Image

        Converter": gibt es noch weitere solche Stellen? Gemessen: Das Register "Bau"
        (~10 Abschnitte) reichte 948 px gegen 845 px sichtbar ueber den Rand hinaus - selbst
        nachdem sich der Dialog schon auf seinen Inhalt vergroessert hatte. Die anderen
        Register (z. B. "Ausgabe & Vorgaben": 805 px gegen 845 px) passten und bleiben
        unveraendert ohne Canvas.
        """
        dialog = self._dialog()
        dialog.zeigen("bau")
        _pumpen(0.1)
        rahmen = dialog._register_rahmen["bau"]
        canvas = _rollbares_canvas(rahmen)
        self.assertIsNotNone(canvas, "Das Register Bau hat kein rollbares Canvas.")
        rahmen.update_idletasks()
        region = canvas.bbox("all")
        self.assertIsNotNone(region)
        self.assertGreater(region[3] - region[1], canvas.winfo_height(),
                           "Die rund zehn Abschnitte sollten den sichtbaren Bereich ueberragen.")
        for schluessel in ("ausgabe", "bibliothek"):
            dialog.zeigen(schluessel)
            _pumpen(0.05)
            self.assertIsNone(_rollbares_canvas(dialog._register_rahmen[schluessel]),
                              "Register %s brauchte bislang kein Canvas." % schluessel)

    def test_das_passcode_feld_ist_verdeckt_und_laesst_sich_anzeigen(self) -> None:
        dialog = self._dialog()
        self.assertEqual("•", str(dialog.passcode_feld.cget("show")))
        dialog.passcode_zeigen_var.set(True)
        dialog._passcode_anzeige()
        self.assertEqual("", str(dialog.passcode_feld.cget("show")))
        dialog.schliessen()

    def test_ein_ungueltiger_passcode_blockiert_das_speichern(self) -> None:
        dialog = self._dialog()
        dialog.passcode_var.set("zu kurz")
        with mock.patch.object(ui.messagebox, "showerror") as fehler:
            dialog.speichern()
        fehler.assert_called_once()
        self.assertTrue(dialog.win.winfo_exists())
        self.assertEqual("ausgabe", next(k for k, (t, _s) in dialog._register_tabs.items()
                                         if str(t.cget("fg")) == dialog.c["fg_accent"]))
        self.assertEqual("", self.app._load_setting(opt.PASSCODE, "nicht gesetzt"), "der ungueltige Wert wurde nicht gespeichert")
        dialog.schliessen()

    def test_ein_gueltiger_passcode_wird_gespeichert_und_bei_jedem_lauf_benutzt(self) -> None:
        self._laden()
        passcode = ("x" * 32)
        dialog = self._dialog()
        dialog.passcode_var.set(passcode)
        dialog.speichern()
        _pumpen(0.3)
        self.assertEqual(passcode, self._gespeichert(opt.PASSCODE))
        self.assertEqual(passcode, self.f._passcode())
        with mock.patch.object(wz, "pruefen", return_value={"pass": 1, "warn": 0, "fail": 0, "results": []}) as pruefen:
            self.f._lauf_pruefen(self.f.aktuell, "", "pruefen")
            self.assertTrue(_warten(lambda: self.f._z.get("fertig") is not None))
        self.assertEqual(passcode, pruefen.call_args.kwargs["passcode"])

    def test_der_dialog_zeigt_die_gespeicherten_werte(self) -> None:
        self.app._save_setting(opt.COVER, False)
        self.app._save_setting(opt.SORTIERUNG, "groesse")
        self.app._save_setting(opt.ORDNER, [self.ordner])
        self.app._save_setting(opt.TEMP_ORDNER, self.ordner)
        dialog = self._dialog()
        self.assertFalse(dialog.cover_var.get())
        self.assertEqual("Größe", dialog.sort_var.get())
        self.assertEqual([self.ordner], dialog.ordner)
        self.assertEqual(1, dialog.ordner_liste.size())
        self.assertEqual(self.ordner, dialog.temp_ordner_var.get())

    def test_temp_ordner_ist_leer_solange_niemand_einen_waehlt(self) -> None:
        """Nutzerwunsch: nur bei Bedarf gesetzt - leer aendert nichts am bisherigen Verhalten."""
        dialog = self._dialog()
        self.assertEqual("", dialog.temp_ordner_var.get())
        dialog.speichern()
        _pumpen(0.2)
        self.assertEqual("", self._gespeichert(opt.TEMP_ORDNER))

    def test_ein_gewaehlter_temp_ordner_wird_gespeichert_und_von_arbeitsordner_benutzt(self) -> None:
        dialog = self._dialog()
        dialog.temp_ordner_var.set(self.ordner)
        dialog.speichern()
        _pumpen(0.2)
        self.assertEqual(self.ordner, self._gespeichert(opt.TEMP_ORDNER))
        self.assertEqual(self.ordner, self.f._arbeitsordner())

    def test_die_quellenliste_zeigt_die_bibliothek(self) -> None:
        self._laden()
        dialog = self._dialog()
        self.assertEqual(sorted(self.pakete), sorted(dialog.quellen_liste.get(0, "end")))

    # ---------------- Abbrechen / Speichern ----------------
    def test_abbrechen_aendert_nichts(self) -> None:
        dialog = self._dialog()
        dialog.cover_var.set(False)
        dialog.sort_var.set("Größe")
        dialog.schliessen()
        _pumpen(0.2)
        self.assertTrue(self.f._cover_an())
        self.assertEqual("titel", self.app._load_setting(opt.SORTIERUNG, "titel"))
        self.assertIsNone(getattr(self.f, ui.DIALOG_ATTRIBUT))

    def test_speichern_setzt_alles_um(self) -> None:
        self._laden()
        dialog = self._dialog()
        dialog.cover_var.set(False)
        dialog.sort_var.set("Größe")
        dialog.rekursiv_var.set(True)
        dialog.oeffnen_var.set(True)
        dialog.ziel_var.set(self.ordner)
        dialog.aktion_var.set("Extrahieren")
        dialog.format_var.set("exFAT (.exfat)")
        dialog.builder_var.set("ProsperoPkgTool")
        dialog.speichern()
        _pumpen(0.3)
        self.assertIs(False, self._gespeichert(opt.COVER))
        self.assertEqual("groesse", self._gespeichert(opt.SORTIERUNG))
        self.assertIs(True, self._gespeichert(opt.REKURSIV))
        self.assertIs(True, self._gespeichert(opt.OEFFNEN))
        self.assertEqual(self.ordner, self._gespeichert(opt.ZIEL))
        self.assertEqual("exfat", self._gespeichert(opt.FORMAT))
        self.assertEqual("extrahieren", self._gespeichert(opt.AKTION))
        self.assertEqual("ppt", self._gespeichert(opt.BUILDER))
        self.assertEqual("ppt", self.f._builder())
        # ... und im Fenster selbst
        self.assertEqual(self.ordner, self.f.ziel_var.get())
        self.assertEqual("extrahieren", self.f.aktion_var.get())
        self.assertEqual("exfat", self.f.format_schluessel)
        self.assertIsNone(self.app._sidebar_cover_source, "Cover aus: kein Cover in der Seitenleiste")
        reihenfolge = list(self.f.liste.get_children())
        self.assertEqual(sorted(self.pakete, key=lambda p: -self.pakete[p].groesse), reihenfolge, "nach Groesse sortiert")
        self.assertIsNone(getattr(self.f, ui.DIALOG_ATTRIBUT))

    def test_ein_fehlendes_ziel_wird_erst_nach_rueckfrage_gespeichert(self) -> None:
        dialog = self._dialog()
        dialog.ziel_var.set(os.path.join(self.ordner, "gibt-es-nicht"))
        with mock.patch.object(ui.messagebox, "askyesno", return_value=False) as frage:
            dialog.speichern()
        frage.assert_called_once()
        self.assertTrue(dialog.win.winfo_exists(), "bei Nein bleibt der Dialog offen")
        self.assertEqual("", self.app._load_setting(opt.ZIEL, ""))
        dialog.schliessen()

    def test_eine_quelle_entfernen_nimmt_sie_aus_der_bibliothek(self) -> None:
        self._laden()
        dialog = self._dialog()
        erste = dialog.quellen_liste.get(0)
        dialog.quellen_liste.selection_set(0)
        dialog._quelle_weg()
        self.assertEqual(1, dialog.quellen_liste.size())
        self.assertEqual(2, len(self.f.pakete), "bis zum Speichern bleibt alles, wie es war")
        dialog.speichern()
        _pumpen(0.3)
        self.assertNotIn(erste, [i.pfad for i in self.f.pakete])
        self.assertEqual(1, len(self.f.pakete))
        self.assertEqual([i.pfad for i in self.f.pakete], self.app._load_setting(fz.EINST_BIBLIOTHEK, []))
        self.assertTrue(os.path.isfile(erste), "die Datei selbst bleibt immer")
        self.assertIsNotNone(self.f.aktuell, "eine andere Quelle rueckt nach")

    def test_ein_bibliotheksordner_bringt_seine_pakete_beim_speichern(self) -> None:
        dialog = self._dialog()
        with mock.patch.object(ui.filedialog, "askdirectory", return_value=self.ordner):
            dialog._ordner_hinzu()
        self.assertEqual([os.path.normpath(self.ordner)], dialog.ordner)
        dialog.speichern()
        self.assertTrue(_warten(lambda: len(self.f.pakete) == len(self.pakete)), "die Suche traegt die Pakete ein")
        self.assertEqual([os.path.normpath(self.ordner)], self.app._load_setting(opt.ORDNER, []))

    def test_ein_ordner_wird_nur_einmal_aufgenommen_und_laesst_sich_entfernen(self) -> None:
        dialog = self._dialog()
        with mock.patch.object(ui.filedialog, "askdirectory", return_value=self.ordner):
            dialog._ordner_hinzu()
            dialog._ordner_hinzu()
        self.assertEqual(1, len(dialog.ordner))
        dialog.ordner_liste.selection_set(0)
        dialog._ordner_weg()
        self.assertEqual([], dialog.ordner)
        dialog.schliessen()

    def test_beim_start_wird_die_bibliothek_aktualisiert_wenn_gewuenscht(self) -> None:
        self.app._save_setting(opt.ORDNER, [self.ordner])
        self.app._save_setting(opt.START_SCAN, True)
        self.f._bibliothek_laden()
        self.assertTrue(_warten(lambda: len(self.f.pakete) == len(self.pakete)))

    def test_beim_start_wird_nichts_gesucht_wenn_nicht_gewuenscht(self) -> None:
        self.app._save_setting(opt.ORDNER, [self.ordner])
        self.app._save_setting(opt.START_SCAN, False)
        self.f._bibliothek_laden()
        _pumpen(1.0)
        self.assertEqual(0, len(self.f.pakete))

    # ---------------- Wartung ----------------
    def test_export_schreibt_die_optionen_als_json(self) -> None:
        self._laden()
        dialog = self._dialog()
        dialog.cover_var.set(False)
        ziel = os.path.join(self.ordner, "export.json")
        with mock.patch.object(ui.filedialog, "asksaveasfilename", return_value=ziel):
            dialog._exportieren()
        daten = json.loads(Path(ziel).read_text(encoding="utf-8"))
        self.assertIs(False, daten[opt.COVER])
        self.assertEqual(sorted(self.pakete), sorted(daten[opt.BIBLIOTHEK]))
        self.assertEqual(set(opt.BEKANNT), set(daten))
        dialog.schliessen()

    def test_import_fuellt_nur_die_felder_und_speichert_nichts(self) -> None:
        dialog = self._dialog()
        datei = os.path.join(self.ordner, "import.json")
        Path(datei).write_text(json.dumps({opt.COVER: False, opt.SORTIERUNG: "titel_id", "fremd": 1}), encoding="utf-8")
        with mock.patch.object(ui.filedialog, "askopenfilename", return_value=datei):
            dialog._importieren()
        self.assertFalse(dialog.cover_var.get())
        self.assertEqual("Titel-ID", dialog.sort_var.get())
        self.assertTrue(self.f._cover_an(), "gespeichert wird erst mit Speichern")
        frage = self.dialoge["frage"][-1][1]
        self.assertIn("Unbekannt: fremd", frage)
        dialog.schliessen()

    def test_import_einer_kaputten_datei_meldet_den_fehler(self) -> None:
        dialog = self._dialog()
        datei = os.path.join(self.ordner, "kaputt.json")
        Path(datei).write_text("{nicht json", encoding="utf-8")
        with mock.patch.object(ui.filedialog, "askopenfilename", return_value=datei):
            dialog._importieren()
        self.assertEqual(1, len(self.dialoge["fehler"]))
        self.assertTrue(dialog.cover_var.get(), "nichts geaendert")
        dialog.schliessen()

    def test_import_ohne_unterschied_sagt_das(self) -> None:
        dialog = self._dialog()
        datei = os.path.join(self.ordner, "gleich.json")
        Path(datei).write_text(json.dumps({opt.COVER: True}), encoding="utf-8")
        with mock.patch.object(ui.filedialog, "askopenfilename", return_value=datei):
            dialog._importieren()
        self.assertEqual(1, len(self.dialoge["info"]))
        dialog.schliessen()

    def test_zuruecksetzen_setzt_die_felder_aber_nicht_die_bibliothek(self) -> None:
        self.app._save_setting(opt.ORDNER, [self.ordner])
        dialog = self._dialog()
        dialog.cover_var.set(False)
        dialog.sort_var.set("Größe")
        dialog._zuruecksetzen()
        self.assertTrue(dialog.cover_var.get())
        self.assertEqual("Titel", dialog.sort_var.get())
        self.assertEqual([self.ordner], dialog.ordner)
        dialog.schliessen()

    # ---------------- Wirkung im Fenster ----------------
    def test_builder_ist_lpp_ohne_gespeicherten_wert(self) -> None:
        self.assertEqual("lpp", self.f._builder())

    def test_ein_ungueltig_gespeicherter_builder_faellt_auf_lpp_zurueck(self) -> None:
        self.app._save_setting(opt.BUILDER, "irgendwas")
        self.assertEqual("lpp", self.f._builder())

    def test_paket_bauen_mit_ppt_ohne_werkzeug_meldet_den_fehler(self) -> None:
        self._laden()
        self.app._save_setting(opt.BUILDER, "ppt")
        with mock.patch.object(fz.ppt, "werkzeug_suchen", return_value=""):
            self.f._bauen_starten(self.f.aktuell, self.ordner)
        self.assertEqual(1, len(self.dialoge["fehler"]))
        self.assertIn("ProsperoPkgTool", self.dialoge["fehler"][0][1])

    def test_ausgabeordner_oeffnen_nur_mit_der_option(self) -> None:
        with mock.patch.object(self.f, "_ausgabe_oeffnen") as oeffnen:
            self.f._ausgabe_nach_erfolg()
            oeffnen.assert_not_called()
            self.app._save_setting(opt.OEFFNEN, True)
            self.f._ausgabe_nach_erfolg()
            oeffnen.assert_called_once()

    def test_die_sortierung_wirkt_auf_die_liste(self) -> None:
        self._laden()
        for sortierung, erwartet in (("titel", ["alpha.pkg", "beta.pkg"]), ("titel_id", ["alpha.pkg", "beta.pkg"]),
                                     ("groesse", ["alpha.pkg", "beta.pkg"])):
            self.app._save_setting(opt.SORTIERUNG, sortierung)
            self.f._liste_fuellen()
            self.assertEqual(erwartet, [os.path.basename(p) for p in self.f.liste.get_children()], sortierung)
        # Groesse: die groessere zuerst - bei vertauschten Groessen kehrt sich die Reihenfolge um
        self.pakete[os.path.join(self.ordner, "beta.pkg")].groesse = 9 * 1024 ** 3
        self.app._save_setting(opt.SORTIERUNG, "groesse")
        self.f._liste_fuellen()
        self.assertEqual(["beta.pkg", "alpha.pkg"], [os.path.basename(p) for p in self.f.liste.get_children()])

    def test_das_cover_laesst_sich_ausschalten(self) -> None:
        self._laden()
        self.app._save_setting(opt.COVER, False)
        self.f._cover_zeigen(self.f.aktuell)
        self.assertIsNone(self.f._cover)
        self.assertEqual("", str(self.f.cover_label.cget("text")))
        self.app._save_setting(opt.COVER, True)
        self.f._cover_zeigen(self.f.aktuell)
        self.assertEqual(STRINGS["ps5pkg.no_cover"]["de"], str(self.f.cover_label.cget("text")),
                         "eingeschaltet, aber ohne Bild im Paket: der Hinweis steht wieder da")

    def test_das_schliessen_des_fensters_schliesst_den_dialog(self) -> None:
        dialog = self._dialog()
        self.f._schliessen()
        _pumpen(0.3)
        self.assertFalse(self.f.win.winfo_exists())
        self.assertFalse(dialog.win.winfo_exists())


if __name__ == "__main__":
    unittest.main()
