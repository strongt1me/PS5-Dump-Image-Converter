# -*- coding: utf-8 -*-
"""Tests fuer das Fenster „PS4 PKG -> OTA“ (``ps5_validator/ui/ps4_ota.py``) und seine Dialoge.

Das Fenster wird echt gebaut (auf der gemeinsamen, verborgenen Tk-Wurzel); Dialoge,
Netzzugriffe und das Werkzeug sind durch Attrappen ersetzt. Pakete entstehen
synthetisch (Kopf, Eintragstabelle, param.sfo - siehe ``test_ps4pkg_bibliothek``).
"""
from __future__ import annotations

import gc
import io
import os
import re
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("ps4_ota_fenster")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.ui import ps4_ota, ps4_ota_bausteine as bs, ps4_ota_dialoge as dlg   # noqa: E402
from ps5_validator.utils import bibliothek_raster as raster   # noqa: E402
from ps5_validator.utils import ps4pkg_aufgaben as au, ps4pkg_bibliothek as bib   # noqa: E402
from ps5_validator.utils import ps4pkg_ota as ota, ps4pkg_updates as upd, orbispkg   # noqa: E402
from ps5_validator.utils.i18n import STRINGS               # noqa: E402
from test_ps4pkg_bibliothek import paket_bauen              # noqa: E402

try:
    import tkinter as tk
    from tkinter import ttk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False

DEUTSCH = re.compile(
    r"[\u00e4\u00f6\u00fc\u00c4\u00d6\u00dc\u00df]|\b(?:der|die|das|und|nicht|wird|Datei|Dateien|Ordner|Fehler|Paket|Pakete|"
    r"Aufgabe|Aufgaben|Sammlung|Abbrechen|Entpacken|Einlesen|Zielordner|Bilder|Protokoll)\b")


def _png_bytes() -> bytes:
    from PIL import Image
    puffer = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 40, 40)).save(puffer, "PNG")
    return puffer.getvalue()


def _bis(bedingung, grenze: float = 10.0) -> bool:
    ende = time.monotonic() + grenze
    while time.monotonic() < ende:
        _WURZEL.update()
        if bedingung():
            return True
        time.sleep(0.02)
    return False


def _alle(widget):
    for kind in widget.winfo_children():
        yield kind
        yield from _alle(kind)


def _texte(fenster) -> list[str]:
    """Alles, was der Anwender im Fenster lesen kann: Beschriftungen, Knoepfe, Chips, Spaltenkoepfe.

    Gezeichnete Knoepfe (``KartenKnopf``, ``AuswahlPille``) haben keine ``text``-Option, nennen ihre
    Beschriftung aber ueber ``diagnose_beschriftung`` - dieselbe Stelle, die die Darstellungspruefung nutzt.
    """
    erg: list[str] = []
    for w in _alle(fenster):
        try:
            if "text" in w.keys() and str(w.cget("text")).strip():
                erg.append(str(w.cget("text")))
        except tk.TclError:
            pass
        beschriftung = getattr(w, "diagnose_beschriftung", None)
        if callable(beschriftung) and str(beschriftung()).strip():
            erg.append(str(beschriftung()))
        if isinstance(w, ttk.Treeview):
            for s in w["columns"]:
                erg.append(str(w.heading(s, "text")))
    return erg


#: Was in diesem Fenster **nicht** mehr vorkommen darf: Es ist durchgehend rund (Pillenform).
ECKIGE_TEILE = (ttk.Button, tk.Button, ttk.Combobox, ttk.Notebook, ttk.Progressbar, ttk.Entry, tk.Radiobutton,
                tk.Checkbutton, ttk.Checkbutton, ttk.Radiobutton, ttk.Spinbox)


def _eckige(fenster) -> list[str]:
    """Alle Teile, die nicht in Pillenform gezeichnet sind - samt eckigem ``tk.Entry`` ausserhalb einer Pille."""
    eckig = []
    for w in _alle(fenster):
        if isinstance(w, ECKIGE_TEILE):
            eckig.append("%s (%s)" % (w.winfo_class(), w))
        elif isinstance(w, tk.Entry) and not isinstance(w.master.master, (raster.RundeKarte,)) \
                and not isinstance(w.master, raster.RundeKarte):
            eckig.append("Entry ausserhalb einer Pille (%s)" % w)
    return eckig


@unittest.skipUnless(_TK_DA, "Ohne Tk keine Fensterprobe.")
class FensterTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.wo = Path(self._tmp.name)
        icon = _png_bytes()
        self.basis = paket_bauen(self.wo / "a.pkg", titel="Alpha Spiel", title_id="CUSA00001", kategorie="gd",
                                 content_id="UP0000-CUSA00001_00-AAAAAAAAAAAAAAAA", mit_namen=True)
        self.update = paket_bauen(self.wo / "sub" / "b.pkg", titel="Alpha Spiel", title_id="CUSA00001",
                                  kategorie="gp", app_ver="01.05", content_id="UP0000-CUSA00001_00-AAAAAAAAAAAAAAAA")
        self.dlc = paket_bauen(self.wo / "c.pkg", titel="Alpha DLC", title_id="CUSA00001", kategorie="ac",
                               content_id="EP0000-CUSA00001_00-DLCPACK000000001")
        self.fremd = paket_bauen(self.wo / "d.pkg", titel="Beta", title_id="CUSA00002", kategorie="gd",
                                 content_id="JP0000-CUSA00002_00-BBBBBBBBBBBBBBBB", flags=0x83000001)
        (self.wo / "kaputt.pkg").write_bytes(b"x" * 50)
        self.fenster = ps4_ota.Ps4OtaFenster(self.app, APP.UI_SCHRIFT, APP.MONO_SCHRIFT, APP.pt, autoladen=False)
        # Kein Test geht ans Netz oder oeffnet ein Fenster: Rueckfragen und Dateidialoge sind Attrappen.
        self._patches = [
            mock.patch.object(ps4_ota.messagebox, "showinfo"),
            mock.patch.object(ps4_ota.messagebox, "showwarning"),
            mock.patch.object(ps4_ota.messagebox, "showerror"),
            mock.patch.object(ps4_ota.messagebox, "askyesno", return_value=True),
            mock.patch.object(ps4_ota.filedialog, "askdirectory", return_value=""),
            mock.patch.object(ps4_ota.filedialog, "asksaveasfilename", return_value=""),
            mock.patch.object(ps4_ota.filedialog, "askopenfilenames", return_value=()),
        ]
        self.mb = {}
        for p in self._patches:
            self.mb[p.attribute] = p.start()

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        try:
            self.fenster.warteschlange.alle_abbrechen()
            self.fenster._schliesst = True
            self.fenster.win.destroy()
        except tk.TclError:
            pass
        self._tmp.cleanup()
        gc.collect()

    # --- Hilfen ------------------------------------------------------------
    def _einlesen(self) -> None:
        self.fenster._einlesen([str(self.wo)], ersetzen=True)
        self.assertTrue(_bis(lambda: len(self.fenster.pakete) == 5 and not self.fenster._z.get("scan_laeuft")
                             and not self.fenster._z.get("scan_fertig")),
                        "Das Einlesen wurde nicht fertig.")
        _WURZEL.update()

    def _zeilen(self) -> list[tuple]:
        return [self.fenster.baum.item(i, "values") for i in self.fenster.baum.get_children()]

    def _waehle(self, *dateien: str) -> None:
        iids = [i for i, e in self.fenster._iid_eintrag.items() if e.datei in dateien]
        self.fenster.baum.selection_set(iids)
        self.fenster._auswahl_verarbeiten()
        _WURZEL.update()

    # --- Aufbau ----------------------------------------------------------------
    def test_das_fenster_hat_alle_reiter_und_knoepfe(self) -> None:
        self.assertEqual("PS4 PKG → OTA", self.fenster.win.title())
        reiter = [chip.cget("text") for chip in self.fenster._reiter.chips]
        self.assertEqual([STRINGS["ps4ota.tab_" + k]["de"] for k in ps4_ota.REITER], reiter)
        self.assertEqual(("info", "dateien", "bilder", "interna", "update", "ota", "aufgaben", "protokoll"),
                         ps4_ota.REITER)
        self.assertEqual({"entpacken", "ffpfsc", "zusammen", "neu_packen", "pruefen", "umbenennen",
                          "verschieben", "ota", "mehr"}, set(self.fenster.knoepfe))

    def test_ohne_auswahl_sind_die_aktionen_gesperrt(self) -> None:
        for name in ("entpacken", "ffpfsc", "zusammen", "neu_packen", "pruefen", "ota"):
            self.assertFalse(bs.ist_frei(self.fenster.knoepfe[name]), name)
        self.assertTrue(bs.ist_frei(self.fenster.knoepfe["mehr"]))

    def test_das_fenster_hat_einen_schliessen_knopf(self) -> None:
        """Es hat Laeufe - wie die anderen Fenster mit Laeufen soll es sich nicht nur ueber das X schliessen lassen."""
        knopf = self.fenster._schliessen_knopf
        self.assertEqual(STRINGS["action.close"]["de"], knopf.cget("text"))
        self.assertEqual("right", knopf.pack_info()["side"])
        knopf.invoke()
        self.assertFalse(self.fenster.win.winfo_exists())

    def test_alles_im_fenster_ist_rund(self) -> None:
        """Nutzerwunsch 05.10.2026: Der Inhalt in der Optik des Programms - runde Pillenknoepfe usw."""
        self.assertEqual([], _eckige(self.fenster.win))
        pillen = [w for w in _alle(self.fenster.win) if isinstance(w, raster.KartenKnopf)]
        self.assertGreaterEqual(len(pillen), 30, "Knoepfe, Chips und Klapplisten sind gezeichnete Pillen.")
        karten = [w for w in _alle(self.fenster.win) if isinstance(w, raster.RundeKarte)]
        self.assertGreaterEqual(len(karten), 8, "Kopfkarte, Tabelle, Seitenkarte, Felder, Bildkarten ...")

    def test_der_hauptknopf_ist_ein_akzentknopf_ohne_schein(self) -> None:
        ota_knopf = self.fenster.knoepfe["ota"]
        self.assertEqual("akzent", ota_knopf._basis_stil)
        andere = self.fenster.knoepfe["entpacken"]
        _WURZEL.update_idletasks()
        self.assertEqual(andere.winfo_reqheight(), ota_knopf.winfo_reqheight(),
                         "Ein Schein machte den Knopf hoeher als seine Nachbarn und rueckte ihn aus der Zeile.")

    def test_das_fenster_waechst_beim_aufbau_nicht(self) -> None:
        """Befund vom 05.10.2026: Die Tabellen weiteten ihre Spalten, das Fenster ging von 1260 auf 1580."""
        _WURZEL.update()
        time.sleep(0.5)
        _WURZEL.update()
        self.assertEqual(1260, self.fenster.win.winfo_width())

    def test_ein_zweites_oeffnen_holt_das_erste_nach_vorn(self) -> None:
        self.app._ps4_ota_fenster = None
        with mock.patch.object(ps4_ota, "Ps4OtaFenster", return_value=self.fenster) as klasse:
            erstes = ps4_ota.oeffnen(self.app, APP.UI_SCHRIFT, APP.MONO_SCHRIFT, APP.pt)
            zweites = ps4_ota.oeffnen(self.app, APP.UI_SCHRIFT, APP.MONO_SCHRIFT, APP.pt)
        self.assertIs(erstes, zweites)
        self.assertEqual(1, klasse.call_count)
        self.app._ps4_ota_fenster = None

    # --- Einlesen und Tabelle ------------------------------------------------------
    def test_die_tabelle_zeigt_alle_pakete_auch_das_unlesbare(self) -> None:
        self._einlesen()
        zeilen = self._zeilen()
        self.assertEqual(5, len(zeilen))
        dateien = {z[0]: z for z in zeilen}
        self.assertEqual("Alpha Spiel", dateien["a.pkg"][1])
        self.assertEqual("CUSA00001", dateien["a.pkg"][2])
        self.assertEqual(STRINGS["ps4ota.typ_patch"]["de"], dateien["b.pkg"][3])
        self.assertEqual("1.05", dateien["b.pkg"][4])
        self.assertEqual("US", dateien["a.pkg"][5])
        self.assertEqual("JP", dateien["d.pkg"][5])
        self.assertEqual(STRINGS["ps4ota.echt_official"]["de"], dateien["d.pkg"][8])
        self.assertIn("nicht lesbar", dateien["kaputt.pkg"][1])
        self.assertIn("5 Pakete", self.fenster.status_var.get())

    def test_sortieren_nach_einer_spalte_und_zurueck(self) -> None:
        self._einlesen()
        self.fenster._sortieren("groesse")
        self.fenster._sortieren("groesse")      # zweiter Klick: absteigend
        groessen = [e.groesse for e in self.fenster.sicht]
        self.assertEqual(sorted(groessen, reverse=True), groessen)
        self.fenster._sortieren("datei")
        self.assertEqual(sorted(e.datei.lower() for e in self.fenster.sicht), [e.datei.lower() for e in self.fenster.sicht])

    def test_suche_und_filter(self) -> None:
        self._einlesen()
        self.fenster.suche_var.set("beta")
        _WURZEL.update()
        self.assertEqual(["d.pkg"], [z[0] for z in self._zeilen()])
        self.fenster.suche_var.set("")
        self.fenster.typ_var.set(STRINGS["ps4ota.typ_patch"]["de"])
        self.fenster._tabelle_neu()
        self.assertEqual(["b.pkg"], [z[0] for z in self._zeilen()])
        self.fenster._filter_loeschen()
        self.assertEqual(5, len(self._zeilen()))
        self.fenster.echt_var.set(STRINGS["ps4ota.echt_official"]["de"])
        self.fenster._tabelle_neu()
        self.assertEqual(["d.pkg"], [z[0] for z in self._zeilen()])

    def test_die_regionsliste_folgt_den_paketen(self) -> None:
        self._einlesen()
        werte = self.fenster._region_box.werte
        self.assertEqual([STRINGS["ps4ota.alle"]["de"], "EU", "JP", "US"], werte)

    def test_gruppieren_legt_gruppenknoten_an(self) -> None:
        self._einlesen()
        self.fenster.gruppe_var.set(STRINGS["ps4ota.col_title_id"]["de"])
        self.fenster._tabelle_neu()
        gruppen = self.fenster.baum.get_children()
        self.assertTrue(all(g.startswith("g:") for g in gruppen))
        self.assertEqual({"g:CUSA00001", "g:CUSA00002", "g:-"}, set(gruppen))
        # Eine Gruppe zu waehlen heisst, alle ihre Pakete zu waehlen.
        self.fenster.baum.selection_set("g:CUSA00001")
        self.assertEqual(3, len(self.fenster._gewaehlt()))

    def test_die_auswahl_bleibt_nach_dem_neuaufbau(self) -> None:
        self._einlesen()
        self._waehle("a.pkg")
        self.fenster._tabelle_neu()
        self.assertEqual(["a.pkg"], [e.datei for e in self.fenster._gewaehlt()])

    def test_neu_einlesen_nimmt_neue_dateien_mit_und_kennt_nur_gemerkte_ordner(self) -> None:
        self.fenster._merken(ps4_ota.EINST_QUELLEN, [str(self.wo)])
        self.fenster._neu_einlesen()
        self.assertTrue(_bis(lambda: len(self.fenster.pakete) == 5 and not self.fenster._z.get("scan_fertig")))
        paket_bauen(self.wo / "neu.pkg", titel="Neu", title_id="CUSA00003")
        self.fenster._neu_einlesen()
        self.assertTrue(_bis(lambda: len(self.fenster.pakete) == 6 and not self.fenster._z.get("scan_fertig")))

    def test_ohne_gemerkte_ordner_sagt_neu_einlesen_es(self) -> None:
        self.fenster._merken(ps4_ota.EINST_QUELLEN, [])
        self.fenster._neu_einlesen()
        self.mb["showwarning"].assert_called()

    def test_liste_leeren(self) -> None:
        self._einlesen()
        self.fenster._liste_leeren()
        self.assertEqual([], self.fenster.pakete)
        self.assertEqual([], self._zeilen())
        self.assertEqual([], self.fenster._einstellung(ps4_ota.EINST_QUELLEN, ["x"]))

    # --- Einzelheiten ------------------------------------------------------------------
    def test_die_auswahl_fuellt_info_interna_und_aktionen(self) -> None:
        self._einlesen()
        self._waehle("a.pkg")
        werte = {self.fenster.info_baum.set(i, "feld"): self.fenster.info_baum.set(i, "wert")
                 for i in self.fenster.info_baum.get_children()}
        self.assertEqual("Alpha Spiel", werte[STRINGS["ps4ota.col_titel"]["de"]])
        self.assertEqual("UP0000-CUSA00001_00-AAAAAAAAAAAAAAAA", werte["Content ID"])
        self.assertEqual("0x04008000", werte["SYSTEM_VER"])
        self.assertEqual("4.00", werte[STRINGS["ps4ota.info_min_fw"]["de"]])
        kennungen = {self.fenster.interna_baum.set(i, "kennung") for i in self.fenster.interna_baum.get_children()}
        self.assertEqual({"0x0200", "0x0400", "0x1000", "0x1200"}, kennungen)
        namen = {self.fenster.interna_baum.set(i, "kennung"): self.fenster.interna_baum.set(i, "name")
                 for i in self.fenster.interna_baum.get_children()}
        self.assertEqual("param.sfo", namen["0x1000"])
        self.assertEqual("1 ausgewählt", self.fenster.auswahl_var.get())
        for name in ("entpacken", "ffpfsc", "pruefen", "neu_packen", "ota"):
            self.assertTrue(bs.ist_frei(self.fenster.knoepfe[name]), name)

    def test_zusammenfuehren_ist_nur_bei_update_oder_einzelnem_spiel_frei(self) -> None:
        self._einlesen()
        self._waehle("a.pkg")
        self.assertTrue(bs.ist_frei(self.fenster.knoepfe["zusammen"]))
        self._waehle("c.pkg")
        self.assertFalse(bs.ist_frei(self.fenster.knoepfe["zusammen"]), "Ein Zusatzinhalt allein reicht nicht.")
        self._waehle("b.pkg")
        self.assertTrue(bs.ist_frei(self.fenster.knoepfe["zusammen"]))
        self._waehle("a.pkg", "d.pkg")
        self.assertFalse(bs.ist_frei(self.fenster.knoepfe["zusammen"]), "Zwei Spiele ergeben kein Paar.")

    def test_neu_packen_nur_bei_genau_einem_paket(self) -> None:
        self._einlesen()
        self._waehle("a.pkg", "b.pkg")
        self.assertFalse(bs.ist_frei(self.fenster.knoepfe["neu_packen"]))

    def test_ein_unlesbares_paket_sperrt_die_aktionen(self) -> None:
        self._einlesen()
        self._waehle("kaputt.pkg")
        self.assertFalse(bs.ist_frei(self.fenster.knoepfe["entpacken"]))

    def test_bilder_werden_geladen_und_gezeigt(self) -> None:
        # a.pkg traegt kein echtes PNG: Das Fenster zeigt "Bild nicht lesbar" statt abzustuerzen.
        self._einlesen()
        self._waehle("a.pkg")
        self.assertTrue(_bis(lambda: self.fenster._bild_labels["icon0"].cget("text") != ""))
        text = self.fenster._bild_labels["icon0"].cget("text")
        self.assertIn(text, (STRINGS["ps4ota.bild_fehler"]["de"], STRINGS["ps4ota.bild_keins"]["de"]))

    def test_ein_echtes_png_wird_als_bild_gezeigt(self) -> None:
        pfad = paket_bauen(self.wo / "bild.pkg", titel="Bild", title_id="CUSA00009")
        roh = bytearray(pfad.read_bytes())
        png = _png_bytes()
        # den Icon-Eintrag (0x1200) durch ein echtes PNG ersetzen: Lage und Groesse im Eintrag anpassen
        tabelle = 0x2000
        import struct
        for i in range(3):
            kennung, = struct.unpack_from(">I", roh, tabelle + i * 0x20)
            if kennung == 0x1200:
                _k, _n, _f1, _f2, off, _g = struct.unpack_from(">IIIIII", roh, tabelle + i * 0x20)
                roh[off:off + len(png)] = png
                struct.pack_into(">I", roh, tabelle + i * 0x20 + 20, len(png))
        pfad.write_bytes(bytes(roh))
        self.fenster._einlesen([str(self.wo)], ersetzen=True)
        self.assertTrue(_bis(lambda: len(self.fenster.pakete) == 6 and not self.fenster._z.get("scan_fertig")))
        self._waehle("bild.pkg")
        self.assertTrue(_bis(lambda: "icon0" in self.fenster._bilder))

    def test_dateien_reiter_baut_den_baum_aus_der_liste(self) -> None:
        self._einlesen()
        liste = [orbispkg.ListenEintrag(True, 0, "Image0"), orbispkg.ListenEintrag(True, 0, "Image0/data"),
                 orbispkg.ListenEintrag(False, 5000, "Image0/data/a.bin"), orbispkg.ListenEintrag(False, 10, "Image0/eboot.bin"),
                 orbispkg.ListenEintrag(True, 0, "Sc0"), orbispkg.ListenEintrag(False, 1668, "Sc0/param.sfo")]
        with mock.patch.object(orbispkg, "verfuegbar", return_value=True), \
                mock.patch.object(orbispkg, "liste", return_value=liste):
            self._waehle("a.pkg")
            self.fenster._notizbuch_waehlen("dateien")
            _WURZEL.update()
            self.assertTrue(_bis(lambda: self.fenster._dateien_eintraege), "Der Inhalt kam nicht an.")
        self.assertEqual({"Image0/data/a.bin", "Image0/eboot.bin", "Sc0/param.sfo"},
                         {self.fenster._dateien_eintraege[i] for i in self.fenster._dateien_ist_datei})
        self.assertIn("3", self.fenster.dateien_status.get())

    def test_dateien_auswahl_pfade_nimmt_ordner_als_alle_dateien_darunter(self) -> None:
        self._einlesen()
        liste = [orbispkg.ListenEintrag(True, 0, "Image0"), orbispkg.ListenEintrag(True, 0, "Image0/data"),
                 orbispkg.ListenEintrag(False, 5, "Image0/data/a.bin"), orbispkg.ListenEintrag(False, 6, "Image0/data/b.bin"),
                 orbispkg.ListenEintrag(True, 0, "Image0/leer"), orbispkg.ListenEintrag(False, 7, "Image0/eboot.bin")]
        with mock.patch.object(orbispkg, "verfuegbar", return_value=True), \
                mock.patch.object(orbispkg, "liste", return_value=liste):
            self._waehle("a.pkg")
            self.fenster._dateien_laden(erzwingen=True)
            self.assertTrue(_bis(lambda: self.fenster._dateien_eintraege))
        knoten = {p: i for i, p in self.fenster._dateien_eintraege.items()}
        self.fenster.dateien_baum.selection_set([knoten["Image0/data"], knoten["Image0/leer"]])
        self.assertEqual(["Image0/data/a.bin", "Image0/data/b.bin"], self.fenster._dateien_auswahl_pfade())

    def test_ohne_werkzeug_sagt_der_dateien_reiter_es(self) -> None:
        self._einlesen()
        with mock.patch.object(orbispkg, "verfuegbar", return_value=False):
            self._waehle("a.pkg")
            self.fenster._dateien_laden(erzwingen=True)
        self.assertEqual(STRINGS["ps4ota.dateien_ohne_werkzeug"]["de"], self.fenster.dateien_status.get())

    # --- Aufgaben ----------------------------------------------------------------------------
    def _arbeiten_ersetzen(self, **fns):
        """Ersetzt ``au.arbeit_*`` durch schnelle Attrappen; gibt die Aufrufliste zurueck."""
        aufrufe: list[tuple] = []
        for name in ("arbeit_entpacken", "arbeit_zusammenfuehren", "arbeit_neu_packen", "arbeit_pruefen",
                     "arbeit_bauen", "arbeit_update_laden", "arbeit_ota_dpi", "arbeit_ota_rpi"):
            def _f(a, *args, _name=name, **kw):
                aufrufe.append((_name, args, kw))
                if _name in fns:
                    fns[_name](a, *args, **kw)
                else:
                    a.ergebnis = "ergebnis"
            p = mock.patch.object(au, name, side_effect=_f)
            p.start()
            self.addCleanup(p.stop)
        return aufrufe

    def _aufgaben_fertig(self, anzahl: int) -> bool:
        return _bis(lambda: sum(1 for a in self.fenster.warteschlange.schnappschuss() if a.status in au.ENDZUSTAENDE) >= anzahl)

    def test_entpacken_legt_je_paket_eine_aufgabe_an(self) -> None:
        self._einlesen()
        aufrufe = self._arbeiten_ersetzen()
        self._waehle("a.pkg", "d.pkg")
        antwort = {"ziel": str(self.wo / "aus"), "dump_form": True, "oeffnen": False, "passcode": None}
        with mock.patch.object(dlg, "frage_entpacken", return_value=antwort), \
                mock.patch.object(orbispkg, "verfuegbar", return_value=True):
            self.fenster._aktion_entpacken()
        self.assertTrue(self._aufgaben_fertig(2))
        ziele = sorted(os.path.basename(a[1][1]) for a in aufrufe if a[0] == "arbeit_entpacken")
        self.assertEqual(["CUSA00001", "CUSA00002"], ziele)
        self.assertEqual(2, len(self.fenster.aufg_baum.get_children()))
        self.assertEqual("aufgaben", self.fenster._aktuelle_seite())
        self.assertEqual("pack", self.fenster._seiten["aufgaben"].winfo_manager(), "Nur die gewaehlte Seite steht.")
        self.assertEqual("", self.fenster._seiten["info"].winfo_manager())

    def test_das_ziel_des_entpackens_wird_gemerkt(self) -> None:
        self._einlesen()
        self._arbeiten_ersetzen()
        self._waehle("a.pkg")
        antwort = {"ziel": str(self.wo / "merk"), "dump_form": False, "oeffnen": False, "passcode": None}
        with mock.patch.object(dlg, "frage_entpacken", return_value=antwort), \
                mock.patch.object(orbispkg, "verfuegbar", return_value=True):
            self.fenster._aktion_entpacken()
        self.assertEqual(str(self.wo / "merk"), self.fenster._einstellung(ps4_ota.EINST_ZIEL, ""))

    def test_abbrechen_im_dialog_tut_nichts(self) -> None:
        self._einlesen()
        aufrufe = self._arbeiten_ersetzen()
        self._waehle("a.pkg")
        with mock.patch.object(dlg, "frage_entpacken", return_value=None), \
                mock.patch.object(orbispkg, "verfuegbar", return_value=True):
            self.fenster._aktion_entpacken()
        self.assertEqual([], aufrufe)
        self.assertEqual([], self.fenster.warteschlange.schnappschuss())

    def test_ohne_werkzeug_meldet_die_aktion_es_und_legt_nichts_an(self) -> None:
        self._einlesen()
        self._waehle("a.pkg")
        with mock.patch.object(orbispkg, "verfuegbar", return_value=False):
            self.fenster._aktion_pruefen()
            self.fenster._aktion_neu_packen()
        self.assertEqual(2, self.mb["showerror"].call_count)
        self.assertEqual([], self.fenster.warteschlange.schnappschuss())

    def test_ohne_werkzeug_entpackt_der_bisherige_entpacker(self) -> None:
        """OrbisPkgTool gibt es nur fuer Windows - Linux und macOS behalten den Entpacker des PS4 FFPFSC."""
        self._einlesen()
        self._waehle("a.pkg")
        with mock.patch.object(orbispkg, "verfuegbar", return_value=False), \
                mock.patch.object(self.app, "_show_pkg_entpacken", create=True) as altes_fenster:
            self.fenster._aktion_entpacken()
        altes_fenster.assert_called_once_with()
        self.mb["showerror"].assert_not_called()
        self.assertEqual([], self.fenster.warteschlange.schnappschuss())

    def test_mit_werkzeug_bleibt_der_bisherige_entpacker_zu(self) -> None:
        self._einlesen()
        self._arbeiten_ersetzen()
        self._waehle("a.pkg")
        antwort = {"ziel": str(self.wo / "aus"), "dump_form": True, "oeffnen": False, "passcode": None}
        with mock.patch.object(orbispkg, "verfuegbar", return_value=True), \
                mock.patch.object(dlg, "frage_entpacken", return_value=antwort), \
                mock.patch.object(self.app, "_show_pkg_entpacken", create=True) as altes_fenster:
            self.fenster._aktion_entpacken()
        altes_fenster.assert_not_called()

    def test_das_mehr_menue_bietet_den_paketkopf_an_und_ruft_den_bisherigen_leser(self) -> None:
        erfasst = []
        with mock.patch.object(tk.Menu, "tk_popup", lambda menue, x, y: erfasst.append(menue)):
            self.fenster.knoepfe["mehr"].invoke()
        menue = erfasst[0]
        gesucht = STRINGS["ps4ota.mehr_container_lesen"]["de"]
        position = next((i for i in range(menue.index("end") + 1)
                         if menue.type(i) == "command" and menue.entrycget(i, "label") == gesucht), None)
        self.assertIsNotNone(position, "Der Paketkopf-Leser fehlt im Mehr-Menue.")
        with mock.patch.object(self.app, "_show_pkg_reader", create=True) as leser:
            menue.invoke(position)
        leser.assert_called_once_with()

    def test_zusammenfuehren_findet_das_spiel_zum_update(self) -> None:
        self._einlesen()
        aufrufe = self._arbeiten_ersetzen()
        self._waehle("b.pkg")
        antwort = {"ausgabe": str(self.wo / "m.pkg"), "pruefen": True, "modus": "store", "arbeiter": 2}
        with mock.patch.object(dlg, "frage_zusammenfuehren", return_value=antwort) as frage, \
                mock.patch.object(orbispkg, "verfuegbar", return_value=True):
            self.fenster._aktion_zusammenfuehren()
        basis, update = frage.call_args.args[2], frage.call_args.args[3]
        self.assertEqual(("a.pkg", "b.pkg"), (basis.datei, update.datei))
        self.assertTrue(self._aufgaben_fertig(1))
        name, args, kw = aufrufe[0]
        self.assertEqual("arbeit_zusammenfuehren", name)
        self.assertEqual((basis.pfad, update.pfad, antwort["ausgabe"]), args[:3])
        self.assertEqual((True, "store", 2), (kw["pruefen_danach"], kw["pfsc_modus"], kw["arbeiter"]))

    def test_zusammenfuehren_vom_spiel_aus_nimmt_das_neueste_update(self) -> None:
        self._einlesen()
        self._arbeiten_ersetzen()
        spaeter = paket_bauen(self.wo / "sub" / "b2.pkg", titel="Alpha Spiel", title_id="CUSA00001",
                              kategorie="gp", app_ver="01.09")
        self.fenster._einlesen([str(self.wo)], ersetzen=True)
        self.assertTrue(_bis(lambda: len(self.fenster.pakete) == 6 and not self.fenster._z.get("scan_fertig")))
        self._waehle("a.pkg")
        with mock.patch.object(dlg, "frage_zusammenfuehren", return_value=None) as frage, \
                mock.patch.object(orbispkg, "verfuegbar", return_value=True):
            self.fenster._aktion_zusammenfuehren()
        self.assertEqual("b2.pkg", frage.call_args.args[3].datei)

    def test_zusammenfuehren_ohne_passendes_spiel_sagt_es(self) -> None:
        self._einlesen()
        self.fenster.pakete = [e for e in self.fenster.pakete if e.datei != "a.pkg"]
        self.fenster._tabelle_neu()
        self._waehle("b.pkg")
        with mock.patch.object(orbispkg, "verfuegbar", return_value=True), \
                mock.patch.object(dlg, "frage_zusammenfuehren") as frage:
            self.fenster._aktion_zusammenfuehren()
        frage.assert_not_called()
        self.mb["showwarning"].assert_called()

    def test_pruefen_legt_je_paket_eine_aufgabe_an(self) -> None:
        self._einlesen()
        aufrufe = self._arbeiten_ersetzen()
        self._waehle("a.pkg", "b.pkg")
        with mock.patch.object(orbispkg, "verfuegbar", return_value=True):
            self.fenster._aktion_pruefen()
        self.assertTrue(self._aufgaben_fertig(2))
        self.assertEqual(2, len([a for a in aufrufe if a[0] == "arbeit_pruefen"]))
        self.assertFalse(aufrufe[0][2].get("tief"))

    def test_neu_packen_und_bauen(self) -> None:
        self._einlesen()
        aufrufe = self._arbeiten_ersetzen()
        self._waehle("a.pkg")
        with mock.patch.object(orbispkg, "verfuegbar", return_value=True), \
                mock.patch.object(dlg, "frage_neu_packen",
                                  return_value={"ausgabe": str(self.wo / "n.pkg"), "pruefen": False, "modus": "compressed", "arbeiter": 1}), \
                mock.patch.object(dlg, "frage_bauen",
                                  return_value={"quelle": str(self.wo), "ausgabe": str(self.wo / "b.pkg"), "patch": True,
                                                "pruefen": False, "modus": "compressed", "arbeiter": 1}):
            self.fenster._aktion_neu_packen()
            self.fenster._aktion_bauen()
        self.assertTrue(self._aufgaben_fertig(2))
        self.assertEqual(["arbeit_neu_packen", "arbeit_bauen"], [a[0] for a in aufrufe])
        self.assertTrue(aufrufe[1][2]["patch"])

    def test_ein_fehler_erscheint_in_der_liste_und_im_protokoll(self) -> None:
        self._einlesen()

        def wirft(a, *args, **kw):
            raise au.AufgabeFehler("werkzeug", "Klartext", grund="Das Werkzeug sagt nein")

        self._arbeiten_ersetzen(arbeit_pruefen=wirft)
        self._waehle("a.pkg")
        with mock.patch.object(orbispkg, "verfuegbar", return_value=True):
            self.fenster._aktion_pruefen()
        self.assertTrue(self._aufgaben_fertig(1))
        # Die Liste zieht der Takt nach (alle 150 ms) - erst warten, dann lesen.
        status = STRINGS["ps4ota.aufg_fehler"]["de"]

        def zeile():
            kinder = self.fenster.aufg_baum.get_children()
            return self.fenster.aufg_baum.item(kinder[0], "values") if kinder else ()

        self.assertTrue(_bis(lambda: len(zeile()) == 5 and zeile()[2] == status), "Die Liste zeigt den Fehler nicht.")
        self.assertIn("Das Werkzeug sagt nein", zeile()[4], "Der Grund steht uebersetzt in der Liste.")
        vorsatz = STRINGS["ps4ota.log_aufgabe_fehler"]["de"].split("{")[0]
        self.assertTrue(_bis(lambda: vorsatz in self.fenster.protokoll.get("1.0", "end")))

    def test_abbrechen_wiederholen_entfernen_leeren(self) -> None:
        self._einlesen()
        sperre = threading.Event()

        def haelt(a, *args, **kw):
            sperre.wait(5)
            a.pruefen_abbruch()

        self._arbeiten_ersetzen(arbeit_pruefen=haelt)
        self._waehle("a.pkg", "b.pkg")
        with mock.patch.object(orbispkg, "verfuegbar", return_value=True):
            self.fenster._aktion_pruefen()
        self.assertTrue(_bis(lambda: any(a.status == au.LAEUFT for a in self.fenster.warteschlange.schnappschuss())))
        _WURZEL.update()
        kennungen = self.fenster.aufg_baum.get_children()
        self.assertEqual(2, len(kennungen))
        self.fenster.aufg_baum.selection_set(kennungen[0])
        self.fenster._aufgaben_knoepfe()
        self.assertTrue(bs.ist_frei(self.fenster.aufg_knoepfe["abbrechen"]))
        self.assertFalse(bs.ist_frei(self.fenster.aufg_knoepfe["entfernen"]), "Eine laufende Aufgabe bleibt.")
        self.fenster._aufgabe_abbrechen()
        self.fenster.aufg_baum.selection_set(kennungen[1])
        self.fenster._aufgabe_abbrechen()
        sperre.set()
        self.assertTrue(self._aufgaben_fertig(2))
        _WURZEL.update()
        self.fenster._aufgaben_anzeigen()
        stati = [self.fenster.aufg_baum.set(k, "status") for k in self.fenster.aufg_baum.get_children()]
        self.assertEqual([STRINGS["ps4ota.aufg_abgebrochen"]["de"]] * 2, stati)
        self.fenster.aufg_baum.selection_set(kennungen[0])
        self.fenster._aufgaben_knoepfe()
        self.assertTrue(bs.ist_frei(self.fenster.aufg_knoepfe["wiederholen"]))
        self.fenster._aufgaben_leeren()
        _WURZEL.update()
        self.fenster._aufgaben_anzeigen()
        self.assertEqual((), self.fenster.aufg_baum.get_children())

    def test_beim_schliessen_mit_laufenden_aufgaben_wird_gefragt_und_abgebrochen(self) -> None:
        self._einlesen()
        sperre = threading.Event()
        self._arbeiten_ersetzen(arbeit_pruefen=lambda a, *x, **k: (sperre.wait(5), a.pruefen_abbruch()))
        self._waehle("a.pkg")
        with mock.patch.object(orbispkg, "verfuegbar", return_value=True):
            self.fenster._aktion_pruefen()
        self.assertTrue(_bis(lambda: self.fenster.warteschlange.beschaeftigt))
        self.mb["askyesno"].return_value = False
        self.fenster._schliessen()
        self.assertTrue(self.fenster.win.winfo_exists(), "Bei Nein bleibt das Fenster offen.")
        self.mb["askyesno"].return_value = True
        self.fenster._schliessen()
        sperre.set()
        self.assertTrue(_bis(lambda: self.fenster.warteschlange.offen == 0))

    # --- Umbenennen und Verschieben ----------------------------------------------------------------
    def test_umbenennen_fuehrt_den_plan_aus_und_zieht_die_tabelle_nach(self) -> None:
        self._einlesen()
        self._waehle("a.pkg")
        plan_geben = {}

        def frage(gui, eltern, titel, untertitel, optionen, plan_fn, *a, **kw):
            plan_geben["optionen"] = optionen
            return {"plan": plan_fn("v2", "")}

        with mock.patch.object(dlg, "frage_vorschau", side_effect=frage):
            self.fenster._aktion_umbenennen()
        self.assertEqual(12, len(plan_geben["optionen"]), "zehn Muster, eigenes und Installationsreihenfolge")
        self.assertTrue((self.wo / "Alpha Spiel [CUSA00001].pkg").is_file())
        self.assertFalse((self.wo / "a.pkg").exists())
        self.assertIn("Alpha Spiel [CUSA00001].pkg", [z[0] for z in self._zeilen()])

    def test_verschieben_sortiert_in_unterordner(self) -> None:
        self._einlesen()
        self._waehle("a.pkg", "d.pkg")

        def frage(gui, eltern, titel, untertitel, optionen, plan_fn, *a, **kw):
            return {"plan": plan_fn("title_id", str(self.wo / "sortiert"))}

        with mock.patch.object(dlg, "frage_vorschau", side_effect=frage):
            self.fenster._aktion_verschieben()
        self.assertTrue((self.wo / "sortiert" / "CUSA00001" / "a.pkg").is_file())
        self.assertTrue((self.wo / "sortiert" / "CUSA00002" / "d.pkg").is_file())

    def test_ein_fehlschlag_beim_umbenennen_wird_gemeldet(self) -> None:
        self._einlesen()
        e = next(x for x in self.fenster.pakete if x.datei == "a.pkg")
        plan = [bib.Umbenennung(e.pfad, str(self.wo / "d.pkg"))]     # Ziel besteht schon
        self.fenster._plan_ausfuehren(plan)
        self.mb["showwarning"].assert_called()
        self.assertTrue((self.wo / "a.pkg").is_file())

    # --- Mehr-Menue ------------------------------------------------------------------------------------
    def test_duplikate_und_updates_ohne_spiel(self) -> None:
        self._einlesen()
        self.fenster._pruefung_duplikate()
        self.assertIn(STRINGS["ps4ota.duplikate_keine"]["de"], self.mb["showinfo"].call_args.args)
        kopie = paket_bauen(self.wo / "kopie_von_a.pkg", titel="Alpha Spiel", title_id="CUSA00001", kategorie="gd",
                            content_id="UP0000-CUSA00001_00-AAAAAAAAAAAAAAAA")
        self.fenster._einlesen([str(self.wo)], ersetzen=True)
        self.assertTrue(_bis(lambda: len(self.fenster.pakete) == 6 and not self.fenster._z.get("scan_fertig")))
        self.fenster._pruefung_duplikate()
        self.assertIn("kopie_von_a.pkg", self.mb["showinfo"].call_args.args[1])
        self.fenster.pakete = [e for e in self.fenster.pakete if e.typ != bib.TYP_BASIS]
        self.fenster._pruefung_ohne_basis()
        self.assertIn("Alpha Spiel", self.mb["showinfo"].call_args.args[1])

    def test_liste_exportieren(self) -> None:
        self._einlesen()
        ziel = self.wo / "liste.csv"
        self.mb["asksaveasfilename"].return_value = str(ziel)
        self.fenster._liste_exportieren()
        zeilen = ziel.read_text(encoding="utf-8-sig").splitlines()
        self.assertEqual(1 + 5, len(zeilen), "Kopfzeile und alle fuenf Pakete - auch das unlesbare steht drin")
        self.assertTrue(any("CUSA00002" in z for z in zeilen))

    def test_kopieren_und_aus_liste_entfernen(self) -> None:
        self._einlesen()
        self._waehle("a.pkg")
        self.fenster._kopieren("title_id")
        self.assertEqual("CUSA00001", self.fenster.win.clipboard_get())
        self.fenster._aus_liste_entfernen()
        self.assertNotIn("a.pkg", [e.datei for e in self.fenster.pakete])

    def test_ffpfsc_reicht_die_pakete_an_den_vorhandenen_konverter(self) -> None:
        self._einlesen()
        self._waehle("a.pkg", "d.pkg")
        with mock.patch.object(self.app, "_show_ps4_pkg_converter", create=True) as konverter:
            self.fenster._aktion_ffpfsc()
        konverter.assert_called_once()
        pfade = self.app._ps4pkg_vorgabe.split(os.pathsep)
        self.assertEqual({"a.pkg", "d.pkg"}, {os.path.basename(p) for p in pfade})

    # --- Updates --------------------------------------------------------------------------------------------
    def test_update_online_nachsehen_und_laden(self) -> None:
        self._einlesen()
        self._waehle("a.pkg")
        info = upd.UpdateInfo(title_id="CUSA00001", version="01.09", groesse=2500, system_ver="0x05050000",
                              verzeichnis=upd.UpdateVerzeichnis(gesamtgroesse=2500, teile=[
                                  upd.UpdateTeil("http://x/t0", 0, 2500, "")]))
        with mock.patch.object(upd, "nachsehen", return_value=info) as nachsehen:
            self.fenster._aktion_update_online()
            self.assertTrue(_bis(lambda: "CUSA00001" in self.fenster._update_info))
        nachsehen.assert_called_once_with("CUSA00001")
        text = self.fenster.update_text.get("1.0", "end")
        self.assertIn("01.09", text)
        self.assertIn(STRINGS["ps4ota.update_neuer"]["de"], text, "01.09 ist neuer als der Stand 01.05.")
        self.assertTrue(bs.ist_frei(self.fenster.update_laden))
        zeile = next(self.fenster.baum.item(i, "values") for i in self.fenster.baum.get_children()
                     if self.fenster.baum.item(i, "values")[0] == "a.pkg")
        self.assertEqual("01.09", zeile[9], "Die Spalte Online zeigt die Fassung.")
        # Laden: Rueckfrage bejaht, Ordner gewaehlt -> Aufgabe
        aufrufe = self._arbeiten_ersetzen()
        self.mb["askdirectory"].return_value = str(self.wo / "updates")
        self.fenster._aktion_update_laden()
        self.assertTrue(self._aufgaben_fertig(1))
        self.assertEqual("arbeit_update_laden", aufrufe[0][0])

    def test_kein_update_online(self) -> None:
        self._einlesen()
        self._waehle("a.pkg")
        with mock.patch.object(upd, "nachsehen", return_value=None):
            self.fenster._aktion_update_online()
            self.assertTrue(_bis(lambda: "CUSA00001" in self.fenster._online))
        _WURZEL.update()
        self.assertEqual("", self.fenster._online["CUSA00001"])
        self.assertIn("CUSA00001", self.fenster.update_text.get("1.0", "end"))

    def test_ein_netzfehler_beim_update_wird_gezeigt(self) -> None:
        self._einlesen()
        self._waehle("a.pkg")
        with mock.patch.object(upd, "nachsehen", side_effect=upd.UpdateFehler("netz", "keine Verbindung")):
            self.fenster._aktion_update_online()
            self.assertTrue(_bis(lambda: "keine Verbindung" in self.fenster.update_text.get("1.0", "end")))

    def test_alle_titel_online_prueft_nur_cusa_titel(self) -> None:
        self._einlesen()
        gefragt: list[str] = []

        def nachsehen(title_id):
            gefragt.append(title_id)
            return upd.UpdateInfo(title_id=title_id, version="02.00") if title_id == "CUSA00001" else None

        with mock.patch.object(upd, "nachsehen", side_effect=nachsehen), mock.patch.object(ps4_ota.time, "sleep", lambda s: None):
            self.fenster._aktion_alle_online()
            self.assertTrue(_bis(lambda: self.fenster._online.get("CUSA00001") == "02.00"))
        self.assertEqual(["CUSA00001", "CUSA00002"], sorted(gefragt))

    # --- OTA -----------------------------------------------------------------------------------------------------
    def test_die_ota_zielart_blendet_die_pc_zeile_ein_und_aus(self) -> None:
        self.fenster.ota_art_var.set(ps4_ota.ART_RPI)
        self.fenster._ota_art_geaendert()
        _WURZEL.update()
        self.assertEqual("pack", self.fenster.ota_rpi_zeile.winfo_manager())
        self.assertTrue(bs.ist_frei(self.fenster.ota_pruefen))
        self.assertTrue(bs.ist_frei(self.fenster.ota_loeschen))
        self.fenster.ota_art_var.set(ps4_ota.ART_DPI)
        self.fenster._ota_art_geaendert()
        _WURZEL.update()
        self.assertEqual("", self.fenster.ota_rpi_zeile.winfo_manager())
        self.assertFalse(bs.ist_frei(self.fenster.ota_pruefen), "Pruefen und Deinstallieren gibt es nur beim RPI.")
        self.assertFalse(bs.ist_frei(self.fenster.ota_loeschen))

    def test_ein_klick_auf_den_chip_stellt_die_zielart_um(self) -> None:
        """Die Zielart ist eine Chipgruppe an ``ota_art_var``; der Klick ruft ``_ota_art_geaendert``."""
        chips = {chip.cget("text"): chip for chip in self.fenster.ota_art_chips.chips}
        self.assertEqual({STRINGS["ps4ota.ota_art_dpi"]["de"], STRINGS["ps4ota.ota_art_rpi"]["de"]}, set(chips))
        chips[STRINGS["ps4ota.ota_art_rpi"]["de"]].invoke()
        self.assertEqual(ps4_ota.ART_RPI, self.fenster.ota_art_var.get())
        self.assertTrue(bs.ist_frei(self.fenster.ota_pruefen))
        self.assertEqual(ps4_ota.ART_RPI, self.mb_einstellung())

    def mb_einstellung(self) -> str:
        return str(self.fenster._einstellung(ps4_ota.EINST_ART, ""))

    def test_das_pc_menue_bietet_automatisch_und_die_adressen_an(self) -> None:
        erfasst = []

        def popup(menue, x, y):
            erfasst.append(menue)

        with mock.patch.object(tk.Menu, "tk_popup", popup), \
                mock.patch.object(ota, "lokale_adressen", return_value=["10.0.0.5", "192.168.0.9"]):
            self.fenster.ota_pc_menue.invoke()
        self.assertEqual(1, len(erfasst))
        menue = erfasst[0]
        eintraege = [menue.entrycget(i, "label") for i in range(menue.index("end") + 1)]
        self.assertEqual([STRINGS["ps4ota.ota_pc_auto"]["de"], "10.0.0.5", "192.168.0.9"], eintraege)
        menue.invoke(2)
        self.assertEqual("192.168.0.9", self.fenster.ota_pc_var.get())

    def test_ota_senden_dpi_legt_je_paket_eine_aufgabe_an(self) -> None:
        self._einlesen()
        aufrufe = self._arbeiten_ersetzen()
        self.fenster.ota_art_var.set(ps4_ota.ART_DPI)
        self.fenster.ota_ip_var.set("192.168.0.20")
        self.fenster.ota_port_var.set("12800")
        self._waehle("a.pkg", "d.pkg")
        self.fenster._aktion_ota_senden()
        self.assertTrue(self._aufgaben_fertig(2))
        self.assertEqual(["arbeit_ota_dpi"] * 2, [a[0] for a in aufrufe])
        self.assertEqual(("192.168.0.20", 12800), aufrufe[0][1][1:3])
        self.assertEqual("192.168.0.20", self.fenster._einstellung(ps4_ota.EINST_IP, ""))

    def test_ota_senden_rpi_ist_eine_aufgabe_fuer_alle(self) -> None:
        self._einlesen()
        aufrufe = self._arbeiten_ersetzen()
        self.fenster.ota_art_var.set(ps4_ota.ART_RPI)
        self.fenster.ota_ip_var.set("192.168.0.21")
        self.fenster.ota_pc_var.set("192.168.0.5")
        self.fenster.ota_serverport_var.set("8080")
        self._waehle("a.pkg", "d.pkg")
        self.fenster._aktion_ota_senden()
        self.assertTrue(self._aufgaben_fertig(1))
        name, args, kw = aufrufe[0]
        self.assertEqual("arbeit_ota_rpi", name)
        self.assertEqual(2, len(args[0]))
        self.assertEqual(("192.168.0.5", 8080), (kw["eigene_ip"], kw["server_port"]))

    def test_ota_ohne_gueltige_adresse_oder_port_sendet_nichts(self) -> None:
        self._einlesen()
        aufrufe = self._arbeiten_ersetzen()
        self._waehle("a.pkg")
        self.fenster.ota_ip_var.set("keine adresse")
        self.fenster._aktion_ota_senden()
        self.fenster.ota_ip_var.set("192.168.0.20")
        self.fenster.ota_port_var.set("99999")
        self.fenster._aktion_ota_senden()
        self.assertEqual([], aufrufe)
        self.assertEqual(2, self.mb["showwarning"].call_count)

    def test_ota_nein_bei_der_rueckfrage_sendet_nichts(self) -> None:
        self._einlesen()
        aufrufe = self._arbeiten_ersetzen()
        self.fenster.ota_ip_var.set("192.168.0.20")
        self._waehle("a.pkg")
        self.mb["askyesno"].return_value = False
        self.fenster._aktion_ota_senden()
        self.assertEqual([], aufrufe)

    def test_erkennen_waehlt_die_passende_zielart(self) -> None:
        self.fenster.ota_ip_var.set("192.168.0.20")
        with mock.patch.object(ota, "erkennen", return_value=ota.ART_RPI):
            self.fenster._ota_erkennen()
            self.assertTrue(_bis(lambda: self.fenster.ota_art_var.get() == ps4_ota.ART_RPI))
        self.assertEqual(STRINGS["ps4ota.ota_erkannt_rpi"]["de"], self.fenster.ota_erkannt.get())
        with mock.patch.object(ota, "erkennen", return_value=""):
            self.fenster._ota_erkennen()
            self.assertTrue(_bis(lambda: self.fenster.ota_erkannt.get() == STRINGS["ps4ota.ota_nichts"]["de"]))

    def test_ist_installiert_und_deinstallieren(self) -> None:
        self._einlesen()
        self._waehle("a.pkg")
        self.fenster.ota_art_var.set(ps4_ota.ART_RPI)
        self.fenster.ota_ip_var.set("192.168.0.21")
        with mock.patch.object(ota.RpiClient, "ist_installiert", return_value=True):
            self.fenster._ota_installiert()
            self.assertTrue(_bis(lambda: "CUSA00001" in self.fenster.ota_status_var.get()
                                 and "installiert" in self.fenster.ota_status_var.get()))
        with mock.patch.object(ota.RpiClient, "deinstallieren") as weg:
            self.fenster._ota_deinstallieren("game", "CUSA00001")
            self.assertTrue(_bis(lambda: weg.called))
        weg.assert_called_once_with("game", "CUSA00001")
        self.mb["askyesno"].return_value = False
        with mock.patch.object(ota.RpiClient, "deinstallieren") as weg2:
            self.fenster._ota_deinstallieren("game", "CUSA00001")
            time.sleep(0.2)
        weg2.assert_not_called()

    # --- Sprache ---------------------------------------------------------------------------------------------------
    def test_die_deutsche_oberflaeche_hat_keinen_schluessel_als_text(self) -> None:
        for text in _texte(self.fenster.win):
            self.assertFalse(text.startswith("ps4ota."), "Ein Schluessel steht roh in der Oberflaeche: " + text)


@unittest.skipUnless(_TK_DA, "Ohne Tk keine Fensterprobe.")
class EnglischTests(unittest.TestCase):
    """Die Oberflaeche auf Englisch nachgebaut: Es darf nichts Deutsches stehen bleiben."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "en"
        cls.fenster = ps4_ota.Ps4OtaFenster(cls.app, APP.UI_SCHRIFT, APP.MONO_SCHRIFT, APP.pt, autoladen=False)
        _WURZEL.update()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fenster._schliesst = True
        try:
            cls.fenster.win.destroy()
        except tk.TclError:
            pass
        cls.app._current_language = "de"

    def test_keine_deutschen_texte_in_der_englischen_oberflaeche(self) -> None:
        for text in _texte(self.fenster.win):
            self.assertFalse(text.startswith("ps4ota."), text)
            self.assertIsNone(DEUTSCH.search(text), "Deutsch in der englischen Oberflaeche: %r" % text)

    def test_die_dialoge_auf_englisch(self) -> None:
        paket = bib.PkgEintrag(pfad=os.path.join(tempfile.gettempdir(), "x.pkg"), lesbar=True, titel="T", title_id="CUSA00001",
                               typ=bib.TYP_BASIS, app_ver="01.00")
        update = bib.PkgEintrag(pfad=os.path.join(tempfile.gettempdir(), "y.pkg"), lesbar=True, titel="T", title_id="CUSA00001",
                                typ=bib.TYP_UPDATE, app_ver="01.05")
        bauer = [
            lambda: dlg.baue_entpacken(self.app, self.fenster.win, [paket], {}, APP.UI_SCHRIFT, APP.pt),
            lambda: dlg.baue_zusammenfuehren(self.app, self.fenster.win, paket, update, {}, APP.UI_SCHRIFT, APP.pt),
            lambda: dlg.baue_neu_packen(self.app, self.fenster.win, paket, {}, APP.UI_SCHRIFT, APP.pt),
            lambda: dlg.baue_bauen(self.app, self.fenster.win, {}, APP.UI_SCHRIFT, APP.pt),
            lambda: dlg.baue_vorschau(self.app, self.fenster.win, "Rename", "x", [("a", "A")], lambda k, e: [],
                                      APP.UI_SCHRIFT, APP.pt),
        ]
        for bau in bauer:
            r, _ok = bau()
            try:
                _WURZEL.update()
                for text in _texte(r.win):
                    self.assertFalse(text.startswith("ps4ota."), text)
                    self.assertIsNone(DEUTSCH.search(text), "Deutsch im englischen Dialog: %r" % text)
            finally:
                r.win.destroy()


@unittest.skipUnless(_TK_DA, "Ohne Tk keine Fensterprobe.")
class DialogTests(unittest.TestCase):
    """Die Dialoge ohne ``wait_window``: Felder setzen, den Knopf druecken, die Antwort lesen."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        cls.eltern = tk.Toplevel(_WURZEL)
        cls.eltern.withdraw()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.eltern.destroy()

    def setUp(self) -> None:
        self._p = [mock.patch.object(dlg.messagebox, "showwarning")]
        self.warnung = self._p[0].start()
        self.paket = bib.PkgEintrag(pfad=os.path.join(tempfile.gettempdir(), "spiel.pkg"), lesbar=True, titel="Mein Spiel",
                                    title_id="CUSA00001", typ=bib.TYP_BASIS, app_ver="01.00")
        self.update = bib.PkgEintrag(pfad=os.path.join(tempfile.gettempdir(), "upd.pkg"), lesbar=True, titel="Mein Spiel",
                                     title_id="CUSA00001", typ=bib.TYP_UPDATE, app_ver="01.05")

    def tearDown(self) -> None:
        self._p[0].stop()

    def _drücken(self, r, ok) -> dict:
        ok.invoke()
        _WURZEL.update()
        return r.antwort

    def test_die_dialoge_sind_rund_und_der_kopf_steht_oben(self) -> None:
        """Pillenform wie das Fenster; und der Kopf (Titel, Untertitel) oben - er stand unter dem Inhalt."""
        bauer = [
            lambda: dlg.baue_entpacken(self.app, self.eltern, [self.paket], {}, APP.UI_SCHRIFT, APP.pt),
            lambda: dlg.baue_zusammenfuehren(self.app, self.eltern, self.paket, self.update, {}, APP.UI_SCHRIFT, APP.pt),
            lambda: dlg.baue_neu_packen(self.app, self.eltern, self.paket, {}, APP.UI_SCHRIFT, APP.pt),
            lambda: dlg.baue_bauen(self.app, self.eltern, {}, APP.UI_SCHRIFT, APP.pt),
            lambda: dlg.baue_vorschau(self.app, self.eltern, "Rename", "x", [("a", "A")], lambda k, e: [],
                                      APP.UI_SCHRIFT, APP.pt, eigene_eingabe=True, feld_titel="Muster",
                                      mit_ordnerwahl=True),
        ]
        for nummer, bau in enumerate(bauer):
            r, _ok = bau()
            with self.subTest(dialog=nummer):
                try:
                    _WURZEL.update()
                    self.assertEqual([], _eckige(r.win))
                    # Ueber die Packreihenfolge, nicht ueber winfo_y: Ein Toplevel unter einem verborgenen
                    # Elternfenster bleibt verborgen und rechnet sein Layout nicht (winfo_y ist dann ueberall 0).
                    # Bis 05.10.2026 stand es trotzdem auf dem Schirm - ein ``iconbitmap(datei)`` je Fenster
                    # blendete es nebenbei ein (und kostete 19 GDI-Objekte, die nie frei wurden).
                    reihenfolge = r.win.pack_slaves()
                    self.assertLess(reihenfolge.index(r.kopf_rahmen), reihenfolge.index(r.koerper),
                                    "Der Kopf steht ueber dem Inhalt.")
                    self.assertEqual("top", str(r.kopf_rahmen.pack_info()["side"]))
                    self.assertEqual("top", str(r.koerper.pack_info()["side"]))
                    self.assertEqual("bottom", str(r.knopfreihe.pack_info()["side"]), "Die Knoepfe stehen unten.")
                finally:
                    r.win.destroy()

    def test_entpacken_antwort(self) -> None:
        r, ok = dlg.baue_entpacken(self.app, self.eltern, [self.paket], {"ziel": "C:/ziel"}, APP.UI_SCHRIFT, APP.pt)
        r.felder["dump"].set(False)
        r.felder["oeffnen"].set(True)
        antwort = self._drücken(r, ok)
        self.assertEqual({"ziel": "C:/ziel", "dump_form": False, "oeffnen": True, "passcode": None}, antwort)

    def test_entpacken_ohne_ziel_und_mit_falschem_passcode(self) -> None:
        r, ok = dlg.baue_entpacken(self.app, self.eltern, [self.paket], {}, APP.UI_SCHRIFT, APP.pt)
        self.assertEqual({}, self._drücken(r, ok))
        self.warnung.assert_called_once()
        r.felder["ziel"].set("C:/ziel")
        r.felder["passcode"].set("zu kurz")
        self.assertEqual({}, self._drücken(r, ok))
        self.assertEqual(2, self.warnung.call_count)
        r.felder["passcode"].set("1" * 32)
        self.assertEqual("1" * 32, self._drücken(r, ok)["passcode"])

    def test_zusammenfuehren_antwort_und_vorgabename(self) -> None:
        r, ok = dlg.baue_zusammenfuehren(self.app, self.eltern, self.paket, self.update, {"ordner": "C:/aus"},
                                         APP.UI_SCHRIFT, APP.pt)
        self.assertEqual("Mein Spiel [CUSA00001] [1.05] merged.pkg", r.felder["name"].get())
        r.felder["modus"].set("store")
        r.felder["arbeiter"].set("0")
        r.felder["pruefen"].set(True)
        antwort = self._drücken(r, ok)
        self.assertEqual(os.path.join("C:/aus", "Mein Spiel [CUSA00001] [1.05] merged.pkg"), antwort["ausgabe"])
        self.assertEqual(("store", 0, True), (antwort["modus"], antwort["arbeiter"], antwort["pruefen"]))

    def test_zusammenfuehren_haengt_pkg_an_und_prueft_die_zahl(self) -> None:
        r, ok = dlg.baue_zusammenfuehren(self.app, self.eltern, self.paket, self.update, {"ordner": "C:/aus"},
                                         APP.UI_SCHRIFT, APP.pt)
        r.felder["name"].set("ohne endung")
        r.felder["arbeiter"].set("viele")
        self.assertEqual({}, self._drücken(r, ok))
        r.felder["arbeiter"].set("2")
        self.assertTrue(self._drücken(r, ok)["ausgabe"].endswith("ohne endung.pkg"))

    def test_neu_packen_antwort(self) -> None:
        r, ok = dlg.baue_neu_packen(self.app, self.eltern, self.paket, {"ordner": "C:/aus"}, APP.UI_SCHRIFT, APP.pt)
        self.assertEqual("spiel_repack.pkg", r.felder["name"].get())
        self.assertEqual(os.path.join("C:/aus", "spiel_repack.pkg"), self._drücken(r, ok)["ausgabe"])

    def test_bauen_prueft_den_ordner(self) -> None:
        with tempfile.TemporaryDirectory() as wo:
            r, ok = dlg.baue_bauen(self.app, self.eltern, {"quelle": wo, "ziel": os.path.join(wo, "x.pkg")}, APP.UI_SCHRIFT, APP.pt)
            self.assertEqual({}, self._drücken(r, ok), "Ohne sce_sys/param.sfo ist es kein Dump-Ordner.")
            self.warnung.assert_called_once()
            os.makedirs(os.path.join(wo, "sce_sys"))
            Path(wo, "sce_sys", "param.sfo").write_bytes(b"x")
            r.felder["patch"].set(True)
            antwort = self._drücken(r, ok)
            self.assertEqual((wo, True), (antwort["quelle"], antwort["patch"]))

    def test_vorschau_zeigt_den_plan_und_gibt_ihn_zurueck(self) -> None:
        plan = [bib.Umbenennung("C:/a/alt.pkg", "C:/a/neu.pkg"), bib.Umbenennung("C:/a/gleich.pkg", "C:/a/gleich.pkg")]
        r, ok = dlg.baue_vorschau(self.app, self.eltern, "Rename", "x", [("a", "Muster A"), ("b", "Muster B")],
                                  lambda k, e: plan if k == "a" else [], APP.UI_SCHRIFT, APP.pt)
        baum = r.felder["baum"]
        self.assertEqual(2, len(baum.get_children()))
        self.assertTrue(bs.ist_frei(ok))
        antwort = self._drücken(r, ok)
        self.assertEqual(1, len(antwort["plan"]), "Nur, was sich aendert, kommt zurueck.")
        self.assertEqual("neu.pkg", os.path.basename(antwort["plan"][0].ziel))

    def test_vorschau_ohne_aenderung_sperrt_den_knopf(self) -> None:
        r, ok = dlg.baue_vorschau(self.app, self.eltern, "Rename", "x", [("a", "A")],
                                  lambda k, e: [bib.Umbenennung("C:/a/x.pkg", "C:/a/x.pkg")], APP.UI_SCHRIFT, APP.pt)
        self.assertFalse(bs.ist_frei(ok))
        r.win.destroy()

    def test_vorschau_folgt_dem_eigenen_muster(self) -> None:
        gesehen = []

        def plan(kennung, eingabe):
            gesehen.append(eingabe)
            return [bib.Umbenennung("C:/a/x.pkg", "C:/a/%s.pkg" % (eingabe or "leer"))]

        r, ok = dlg.baue_vorschau(self.app, self.eltern, "Rename", "x", [("eigen", "Eigenes")], plan,
                                  APP.UI_SCHRIFT, APP.pt, eigene_eingabe=True, eingabe_text="{TITLE}", feld_titel="Muster")
        r.felder["eingabe"].set("NEU")
        _WURZEL.update()
        self.assertIn("NEU", gesehen)
        r.win.destroy()


class SchluesselTests(unittest.TestCase):
    """Jeder Text, den der Quelltext anfordert, steht in beiden Sprachen in der Tabelle."""

    DATEIEN = ("ps4_ota.py", "ps4_ota_dialoge.py")
    #: Vorsaetze, an die der Quelltext ein Wort haengt (``"ps4ota.col_" + spalte``) - samt den Woertern.
    FAMILIEN = {
        "ps4ota.col_": ("datei", "titel", "title_id", "typ", "version", "region", "fw", "groesse", "echtheit", "online", "ordner"),
        "ps4ota.tab_": ("info", "dateien", "bilder", "interna", "update", "ota", "aufgaben", "protokoll"),
        "ps4ota.bild_": ("icon0", "pic0", "pic1"),
        "ps4ota.interna_": ("kennung", "name", "groesse", "offset", "verschluesselt"),
        "ps4ota.aufg_": ("abbrechen", "wiederholen", "entfernen", "leeren", "oeffnen"),
        "ps4ota.aufg_col_": ("art", "titel", "status", "prozent", "meldung"),
        #: Die Fehlergruende haengt der Quelltext an den Vorsatz; ``test_die_fehlergruende_...`` zaehlt sie einzeln.
        "ps4ota.fehler_": (),
    }

    def _gebrauchte(self) -> set[str]:
        import ps5_validator.ui as ui
        import ps5_validator.utils as utils
        schluessel: set[str] = set()
        ordner = list(ui.__path__) + list(utils.__path__)
        for wo in ordner:
            for name in os.listdir(wo):
                if name.endswith(".py") and (name.startswith("ps4_ota") or name.startswith("ps4pkg_")):
                    text = open(os.path.join(wo, name), encoding="utf-8").read()
                    for m in re.finditer(r"""["'](ps4ota\.[A-Za-z0-9_]+)["']""", text):
                        schluessel.add(m.group(1))
        return schluessel

    def test_jeder_feste_schluessel_ist_zweisprachig(self) -> None:
        fehlen = []
        for k in sorted(self._gebrauchte()):
            if k in self.FAMILIEN:     # ein Vorsatz, kein Schluessel
                continue
            eintrag = STRINGS.get(k)
            if not eintrag or not eintrag.get("de") or not eintrag.get("en"):
                fehlen.append(k)
        self.assertEqual([], fehlen)

    def test_jedes_wort_einer_familie_hat_seinen_schluessel(self) -> None:
        fehlen = [vorsatz + wort for vorsatz, worte in self.FAMILIEN.items() for wort in worte
                  if not (STRINGS.get(vorsatz + wort, {}).get("de") and STRINGS.get(vorsatz + wort, {}).get("en"))]
        self.assertEqual([], fehlen)

    def test_die_fehlergruende_der_aufgaben_sind_uebersetzt(self) -> None:
        """Jeder ``AufgabeFehler``-Schluessel und jeder OTA-/Update-Fehler hat einen Text."""
        import ps5_validator.utils as utils
        text = open(os.path.join(list(utils.__path__)[-1], "ps4pkg_aufgaben.py"), encoding="utf-8").read()
        genannt = set(re.findall(r'AufgabeFehler\(\s*"([a-z0-9_]+)"', text))
        # "ota_" und "update_" sind Vorsaetze: Dort haengt der Quelltext den Schluessel des Fehlers an.
        genannt -= {"ota_", "update_"}
        genannt |= {"update_" + k for k in ("hash", "netz", "http", "ohne_teile", "schreiben", "nicht_gefunden")}
        genannt |= {"ota_" + k for k in ("netz", "abgelehnt", "antwort", "http", "fremd", "konsole_fehler", "server_start",
                                          "keine_adresse", "zeit", "zu_gross", "keine_pkg", "leer", "lesen", "ohne_web_port")}
        fehlen = [k for k in sorted(genannt) if not STRINGS.get("ps4ota.fehler_" + k)]
        self.assertEqual([], fehlen)

    def test_platzhalter_beider_sprachen_stimmen_ueberein(self) -> None:
        falsch = []
        for k, e in STRINGS.items():
            if k.startswith("ps4ota."):
                de = set(re.findall(r"\{([a-z_0-9]+)\}", e["de"]))
                en = set(re.findall(r"\{([a-z_0-9]+)\}", e["en"]))
                if de != en:
                    falsch.append((k, de ^ en))
        self.assertEqual([], falsch)


if __name__ == "__main__":
    unittest.main()
