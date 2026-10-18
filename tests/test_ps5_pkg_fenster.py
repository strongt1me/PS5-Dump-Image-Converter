# -*- coding: utf-8 -*-
"""Das Fenster „PS5 PKG Dump & Image Converter“ (``ui/ps5_pkg_fenster.py``, seit v1.9.71) - am wirklichen Programm.

Das Werkzeug ``ffpfsc-pkg-tool`` wird durch Attrappen ersetzt (Paket lesen, pruefen, entpacken); der echte Ablauf
wurde am 09.10.2026 mit einem 528-MB-PS5-Paket von Hand gemessen: Pruefen 0,8 s, Extrahieren 193 Dateien,
Umwandeln zu .ffpfsc ueber Aufgabe 1 in 52 s (416,8 MB, Aufgabe 1 meldet Erfolg).
"""
from __future__ import annotations

import os
import re
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
pruefumgebung.umlenken("ps5pkgfenster")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.ui import ps5_pkg_fenster as fz          # noqa: E402
from ps5_validator.utils import ps5_pkg_optionen as opt     # noqa: E402
from ps5_validator.utils import ps5_pkg_werkzeug as wz      # noqa: E402
from ps5_validator.utils import prospero_pkg_tool as ppt    # noqa: E402
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
    """Sucht rekursiv das Canvas aus ``_build_scrollable_body`` (erkennbar an ``yscrollcommand``).

    Eine runde Karte (``pw.Karte``) zeichnet ihre Ecken selbst oft ueber ein eigenes,
    viel kleineres Canvas - ohne den Filter auf ``yscrollcommand`` faende eine
    Tiefensuche zuerst eines von denen.
    """
    if isinstance(widget, tk.Canvas) and str(widget.cget("yscrollcommand")):
        return widget
    for kind in widget.winfo_children():
        treffer = _rollbares_canvas(kind)
        if treffer is not None:
            return treffer
    return None


def _schleife(grenze: float, bis=None) -> None:
    """Eine echte Hauptschleife fuer hoechstens ``grenze`` Sekunden.

    Rueckrufe aus Arbeitsfaeden (``root.after``, etwa ``_im_hauptfaden`` fuer Rueckfragen) kommen nur an, solange
    wirklich eine Hauptschleife laeuft - ``update()`` allein genuegt nicht (siehe test_webkit_seite).
    """
    ende = time.monotonic() + grenze

    def _takt() -> None:
        if (bis is not None and bis()) or time.monotonic() > ende:
            _WURZEL.quit()
        else:
            _WURZEL.after(10, _takt)

    _WURZEL.after(0, _takt)
    _WURZEL.mainloop()


def _ende(f, grenze: float = 20.0) -> bool:
    """Wartet in einer echten Hauptschleife, bis der Auftrag des Fensters zu Ende ist."""
    _schleife(grenze, bis=lambda: f._job is None)
    return f._job is None


def _info(name: str, titel: str, title_id: str, groesse: int = 2 * 1024 ** 3, pfad: str = "") -> "wz.PaketInfo":
    return wz.PaketInfo(pfad=pfad or name, groesse=groesse, typ="FullDebug", content_id="EP0000-%s_00-TESTTESTTESTTEST" % title_id,
                        title_id=title_id, titel=titel,
                        param={"contentVersion": "01.000.000", "conceptId": "1", "applicationCategoryType": 0})


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class FensterTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        self.app._current_language = "de"
        self.ordner = tempfile.mkdtemp(prefix="ps5pkg_test_")
        self.addCleanup(lambda: APP._rmtree_force(self.ordner, ignore_errors=True))
        self.pakete = {}
        for name, titel, tid, groesse in (("alpha.pkg", "Alpha Spiel", "PPSA00001", 2 * 1024 ** 3),
                                          ("beta.pkg", "Beta Rennen", "PPSA00002", 700 * 1024 ** 2)):
            pfad = os.path.join(self.ordner, name)
            Path(pfad).write_bytes(b"pkg")
            self.pakete[pfad] = _info(name, titel, tid, groesse, pfad)
        stuetzen = (
            mock.patch.object(fz.Ps5PkgFenster, "_werkzeug", return_value="werkzeug"),
            mock.patch.object(wz, "dotnet_ordner", return_value="dotnet"),
            mock.patch.object(wz, "lesen", side_effect=lambda w, p, a=None, **k: self.pakete[p]),
        )
        for s in stuetzen:
            s.start()
            self.addCleanup(s.stop)
        self.dialoge: dict[str, list] = {"info": [], "fehler": [], "frage": []}
        for name, ziel, antwort in (("showinfo", "info", None), ("showerror", "fehler", None), ("askyesno", "frage", True)):
            m = mock.patch.object(fz.messagebox, name, side_effect=lambda *a, _z=ziel, _r=antwort, **k: (
                self.dialoge[_z].append(a), _r)[1])
            m.start()
            self.addCleanup(m.stop)
        # Die Einstellungen des Fensters stehen im umgelenkten Ordner - frueher gespeichertes soll nichts vorgeben.
        for schluessel, wert in ((fz.EINST_AKTION, fz.AKTION_UMWANDELN), (fz.EINST_FORMAT, "ffpfsc"),
                                 (fz.EINST_BIBLIOTHEK, []), (fz.EINST_ZIEL, "")):
            self.app._save_setting(schluessel, wert)
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

    def _laden(self, *namen: str) -> None:
        pfade = [p for p in self.pakete if os.path.basename(p) in namen] or list(self.pakete)
        self.f._pakete_hinzufuegen(pfade, waehlen=True)
        self.assertTrue(_warten(lambda: len(self.f.pakete) == len(pfade) and self.f.aktuell is not None))

    # ---------------- Aufbau ----------------
    def test_das_fenster_hat_alle_seiten_und_fuenf_kacheln(self) -> None:
        f = self.f
        self.assertEqual({"umwandeln", "bibliothek", "extras"}, set(f.seiten))
        self.assertEqual(["ffpkg", "ffpfsc", "ffpfs", "exfat", "pkg"], list(f._kacheln))
        self.assertEqual("ffpfsc", f.format_schluessel)
        self.assertEqual("umwandeln", f.aktion_var.get())

    def test_die_seite_extras_rollt_statt_abzuschneiden(self) -> None:
        """Nutzerbefund 18.10.2026: vier Karten stapeln sich auf "Extras" - bei

        kleineren Fenstern reichten sie ueber den sichtbaren Bereich hinaus,
        ohne jede Moeglichkeit zu rollen (der Entpacken-Knopf, der ganze
        Aufbauen-Bereich der dritten Karte und die vierte Karte waren nicht
        erreichbar). Seitdem baut ``_seite_extras`` den Inhalt in ein Canvas
        aus ``_build_scrollable_body``.
        """
        f = self.f
        f._seite_zeigen("extras")
        _pumpen(0.05)
        seite = f.seiten["extras"]
        canvas = _rollbares_canvas(seite)
        self.assertIsNotNone(canvas, "Die Seite Extras hat kein rollbares Canvas.")
        seite.update_idletasks()
        region = canvas.bbox("all")
        self.assertIsNotNone(region)
        self.assertGreater(region[3] - region[1], canvas.winfo_height(),
                           "Vier Karten sollten den sichtbaren Bereich im Testfenster ueberragen.")

    def test_die_seite_umwandeln_rollt_statt_abzuschneiden(self) -> None:
        """Nutzerbefund 18.10.2026, erweiterte Suche: QUELLE+ZIELFORMAT+AUFTRAG reichten

        bei knapper Fensterhoehe ebenso ueber den sichtbaren Bereich hinaus. Nur die linke
        Spalte bekam ein Canvas - die rechte (ERGEBNIS+Protokoll) soll unveraendert ueber
        die volle Zeilenhoehe von "seite" mitwachsen, nicht auf ihre Inhaltsgroesse
        schrumpfen.
        """
        f = self.f
        f._seite_zeigen("umwandeln")
        _pumpen(0.05)
        seite = f.seiten["umwandeln"]
        seite.update_idletasks()
        canvas = _rollbares_canvas(seite)
        self.assertIsNotNone(canvas, "Die Seite Umwandeln hat kein rollbares Canvas.")
        region = canvas.bbox("all")
        self.assertIsNotNone(region)
        self.assertGreater(region[3] - region[1], canvas.winfo_height(),
                           "QUELLE+ZIELFORMAT+AUFTRAG sollten den sichtbaren Bereich im Testfenster ueberragen.")
        self.assertEqual(seite.winfo_height(), f.spalte_rechts.winfo_height(),
                         "Die rechte Spalte soll weiterhin die volle Zeilenhoehe einnehmen.")
        self.assertTrue(f.ergebnis_karte.winfo_ismapped())
        self.assertTrue(f.protokoll.winfo_ismapped())

    def test_die_seite_bibliothek_rollt_statt_abzuschneiden(self) -> None:
        """Nutzerbefund 18.10.2026, erweiterte Suche: COVER+TECH in der schmalen rechten

        Spalte (420 px) reichten ebenso ueber den sichtbaren Bereich hinaus.
        """
        f = self.f
        f._seite_zeigen("bibliothek")
        _pumpen(0.05)
        seite = f.seiten["bibliothek"]
        seite.update_idletasks()
        canvas = _rollbares_canvas(seite)
        self.assertIsNotNone(canvas, "Die Seite Bibliothek hat kein rollbares Canvas.")
        region = canvas.bbox("all")
        self.assertIsNotNone(region)
        self.assertGreater(region[3] - region[1], canvas.winfo_height(),
                           "COVER+TECH sollten den sichtbaren Bereich im Testfenster ueberragen.")

    def test_ein_zweites_oeffnen_holt_das_offene_fenster(self) -> None:
        zweites = fz.oeffnen(self.app, APP.UI_SCHRIFT, APP.MONO_SCHRIFT, APP.pt)
        self.assertIs(self.f, zweites)

    def test_arbeitsordner_ohne_eigene_einstellung_bleibt_wie_bisher(self) -> None:
        """Nutzerwunsch: der Temp-Ordner der Optionen wirkt nur bei Bedarf - leer aendert nichts."""
        self.app._save_setting(opt.TEMP_ORDNER, "")
        with mock.patch.object(self.app, "_get_runtime_temp_dir", return_value=self.ordner):
            self.assertEqual(self.ordner, self.f._arbeitsordner())

    def test_arbeitsordner_nimmt_den_eigenen_temp_ordner_wenn_er_da_ist(self) -> None:
        eigener = tempfile.mkdtemp(prefix="ps5pkg_eigenertemp_", dir=self.ordner)
        self.app._save_setting(opt.TEMP_ORDNER, eigener)
        with mock.patch.object(self.app, "_get_runtime_temp_dir", return_value=self.ordner):
            self.assertEqual(eigener, self.f._arbeitsordner())

    def test_arbeitsordner_faellt_zurueck_wenn_der_eigene_temp_ordner_fehlt(self) -> None:
        """Z. B. ein abgezogener USB-Stick - der Temp-Ordner der Optionen darf nie einen Absturz ausloesen."""
        self.app._save_setting(opt.TEMP_ORDNER, os.path.join(self.ordner, "gibt-es-nicht"))
        with mock.patch.object(self.app, "_get_runtime_temp_dir", return_value=self.ordner):
            self.assertEqual(self.ordner, self.f._arbeitsordner())

    def test_kein_menueeintrag_mehr_unter_weitere_tools(self) -> None:
        """Bis zum 12.10.2026 abends stand hier ein eigener Knopf; seitdem ist "FPKG" eine Unterseite von
        Aufgabe 7 "PKG / FPKG" in der Seitenleiste UMWANDELN (``ui/pkg_fpkg_seite.py``, Nutzerwunsch)."""
        paare = dict(self.app._MORE_TOOLS_ENTRIES)
        self.assertNotIn("titlebar.ps5pkg", paare)
        self.assertNotIn("titlebar.ps5pkg", STRINGS)
        self.assertTrue(callable(getattr(self.app, "_show_ps5_pkg_converter")))
        with mock.patch.object(fz, "oeffnen") as oeffnen:
            self.app._show_ps5_pkg_converter()
        oeffnen.assert_called_once()

    def test_knopfleiste_steht_buendig_mit_den_karten(self) -> None:
        """13.10.2026 (Bild des Nutzers): "Umwandlung starten" und "Abbrechen" ragten links ueber die Karten hinaus."""
        f = self.f
        f.win.update_idletasks()
        _pumpen(0.3)
        seite_x = f.seiten["umwandeln"].winfo_rootx()
        nav_rahmen = f._nav["umwandeln"][0]
        nav_rechts = nav_rahmen.master.winfo_rootx() + nav_rahmen.master.winfo_width()
        for knopf in (f.start_knopf, f.abbrechen_knopf):
            self.assertGreaterEqual(knopf.winfo_rootx(), nav_rechts, "Der Knopf ragt in die Navigation hinein.")
        self.assertLessEqual(abs(f.start_knopf.winfo_rootx() - seite_x), 4,
                             "Der Startknopf steht nicht an der linken Kante der Karten.")
        self.assertGreater(f.abbrechen_knopf.winfo_rootx(), f.start_knopf.winfo_rootx())

    def test_das_protokoll_liegt_unter_dem_ergebnis_und_ist_sichtbar(self) -> None:
        """13.10.2026: In der Karte AUFTRAG bekam das Protokoll keine Hoehe - der Text war nicht zu sehen."""
        f = self.f
        f._protokoll("Probezeile im Protokoll")
        f.win.update_idletasks()
        _pumpen(0.3)
        karte = f.ergebnis_karte
        # Das Pillen-Kit setzt Textfeld und Karte in runde Rahmen; beide liegen unterhalb der rechten Spalte.
        for teil in (f.protokoll, karte):
            self.assertTrue(str(teil).startswith(str(f.spalte_rechts) + "."), "Protokoll und Ergebnis: dieselbe Spalte.")
        self.assertGreaterEqual(f.protokoll.winfo_rooty(), karte.winfo_rooty() + karte.winfo_height(),
                                "Das Protokoll muss unter dem Ergebnis stehen.")
        self.assertGreaterEqual(f.protokoll.winfo_height(), 60, "Das Protokoll ist zu niedrig, um gelesen zu werden.")
        self.assertGreaterEqual(f.protokoll.winfo_width(), 200)
        self.assertIn("Probezeile im Protokoll", f.protokoll.get("1.0", "end"))

    def test_kein_cover_und_kein_vorschauknopf_mehr_in_der_rechten_spalte(self) -> None:
        """13.10.2026 (Nutzerwunsch): Das Cover steht in der Seitenleiste, "Vorschau oeffnen" ist entfallen."""
        for name in ("cover_vorschau", "vorschau_knopf", "_vorschau_oeffnen"):
            self.assertFalse(hasattr(self.f, name), name)
        self.assertNotIn("ps5pkg.preview_open", STRINGS)

    def test_die_paketwahl_zeigt_cover_und_angaben_in_seitenleiste_und_info_box(self) -> None:
        """Wie bei den Aufgaben 1 bis 6 (``_update_info_box``): Cover, Titel, Title-ID, Groesse und Format."""
        from PIL import Image
        pfad = next(p for p in self.pakete if p.endswith("alpha.pkg"))
        png = Path(self.ordner) / "icon0.png"
        Image.new("RGB", (64, 64), (200, 40, 40)).save(png)
        self.pakete[pfad].icon = str(png)
        self._laden("alpha.pkg")
        app = self.app
        self.assertEqual("Alpha Spiel", app._meta_labels["title"].get())
        self.assertEqual("PPSA00001", app._meta_labels["title_id"].get())
        self.assertNotIn(app._info_src_size_var.get(), ("", "–"))
        self.assertEqual(STRINGS["ps5pkg.meta_method"]["de"], app._info_method_var.get())
        self.assertIsNotNone(app._sidebar_cover_source, "Das Cover muss in der Seitenleiste stehen.")
        self.assertEqual("Alpha Spiel", app._sidebar_preview_title_label.cget("text"))
        # Was aus der Quelle der Aufgaben 1 bis 6 stammt, gehoert nicht zu diesem Paket
        self.assertEqual("–", app._meta_labels["sdk_stand"].get())
        self.assertEqual("–", app._meta_labels["ampr_emu"].get())

    def test_ohne_cover_bleibt_der_titel_in_der_seitenleiste(self) -> None:
        self._laden("beta.pkg")
        self.assertEqual("Beta Rennen", self.app._meta_labels["title"].get())
        self.assertIsNone(self.app._sidebar_cover_source)

    def test_zuruecksetzen_nimmt_die_angaben_wieder_heraus(self) -> None:
        from PIL import Image
        pfad = next(p for p in self.pakete if p.endswith("alpha.pkg"))
        png = Path(self.ordner) / "icon1.png"
        Image.new("RGB", (64, 64), (40, 200, 40)).save(png)
        self.pakete[pfad].icon = str(png)
        self._laden("alpha.pkg")
        self.assertIsNotNone(self.app._sidebar_cover_source)
        fz.spielinfo_zuruecksetzen(self.app)
        _pumpen(0.3)
        self.assertIsNone(self.app._sidebar_cover_source)
        self.assertNotEqual("Alpha Spiel", self.app._meta_labels["title"].get())

    def test_die_seitenwahl(self) -> None:
        self.f._seite_zeigen("bibliothek")
        self.assertEqual("bibliothek", self.f.aktuelle_seite)
        self.f._seite_zeigen("umwandeln")
        self.assertEqual("umwandeln", self.f.aktuelle_seite)

    # ---------------- Pakete lesen, Bibliothek ----------------
    def test_pakete_werden_gelesen_und_angezeigt(self) -> None:
        self._laden()
        f = self.f
        self.assertEqual(2, len(f.liste.get_children()))
        self.assertEqual("2 von 2 Spielen", f.zaehler_var.get())
        self.assertTrue(f.aktuell.pfad.endswith("alpha.pkg"))
        self.assertEqual("PPSA00001 — Alpha Spiel", f.paket_titel.cget("text"))
        self.assertEqual("PPSA00001", f.ergebnis_var["title_id"].get())
        self.assertEqual(14, len(f.tech.get_children()))
        spalten = [f.liste.item(i, "values") for i in f.liste.get_children()]
        self.assertEqual(["Alpha Spiel", "Beta Rennen"], [s[0] for s in spalten])
        self.assertTrue(all(s[2] == "Debug PKG" for s in spalten))

    def test_die_bibliothek_wird_gemerkt(self) -> None:
        self._laden()
        gemerkt = self.app._load_setting(fz.EINST_BIBLIOTHEK, [])
        self.assertEqual(sorted(self.pakete), sorted(gemerkt))

    def test_oeffnen_scannt_die_gemerkte_bibliothek_nicht_von_selbst(self) -> None:
        """Nutzerwunsch 18.10.2026: "Beim Oeffnen ... soll bitte nicht ... bereits etwas

        gescannt werden. Man soll bitte zuerst manuell waehlen muessen, erst dann soll
        gescannt werden." Ein frisches Fenster mit gemerkter Bibliothek las die Pakete
        bis dahin ungefragt neu ein.
        """
        self.app._save_setting(fz.EINST_BIBLIOTHEK, list(self.pakete))
        neu = fz.Ps5PkgFenster(self.app, APP.UI_SCHRIFT, APP.MONO_SCHRIFT, APP.pt)
        try:
            _pumpen(0.3)
            self.assertEqual([], neu.pakete, "Das blosse Oeffnen hat von selbst gelesen.")
            self.assertEqual(0, len(neu.liste.get_children()))
            # Der Knopf AKTUALISIEREN ist die manuelle Wahl - er holt die gemerkte Bibliothek nach.
            neu._bibliothek_aktualisieren()
            self.assertTrue(_warten(lambda: len(neu.pakete) == len(self.pakete)))
            self.assertEqual(2, len(neu.liste.get_children()))
        finally:
            neu._job = None
            neu._uebergabe = None
            neu.win.destroy()
            _pumpen(0.05)

    def test_die_suche_filtert_und_zeigt_einen_hinweis(self) -> None:
        self._laden()
        f = self.f
        self.assertEqual("", f._suche_text())
        self.assertEqual(STRINGS["ps5pkg.search_hint"]["de"], f.suche_var.get())
        for suche, anzahl in (("titel:alpha", 1), ("-alpha", 1), ("größe:>1GB", 1), ("id:ppsa", 2), ("zzz", 0)):
            with self.subTest(suche=suche):
                f._suche_hinweis_setzen(False)
                f.suche_var.set(suche)
                self.assertEqual(anzahl, len(f.liste.get_children()))
        f.suche_var.set("")
        f._suche_hinweis_setzen(True)
        self.assertEqual(2, len(f.liste.get_children()))

    def test_ein_ordner_wird_eine_ebene_tief_durchsucht(self) -> None:
        unter = os.path.join(self.ordner, "sub")
        os.makedirs(os.path.join(unter, "tief"))
        for pfad in (os.path.join(unter, "c.pkg"), os.path.join(unter, "d.txt"), os.path.join(unter, "tief", "e.pkg")):
            Path(pfad).write_bytes(b"x")
        gefunden = [os.path.basename(p) for p in self.f._pkg_in(self.ordner)]
        self.assertEqual(["alpha.pkg", "beta.pkg", "c.pkg"], gefunden)

    def test_ohne_pkg_kommt_ein_hinweis(self) -> None:
        text = os.path.join(self.ordner, "nur.txt")
        Path(text).write_text("x")
        self.f._pakete_hinzufuegen([text])
        self.assertEqual(1, len(self.dialoge["info"]))
        self.assertEqual([], self.f.pakete)

    def test_ein_nicht_lesbares_paket_steht_im_protokoll(self) -> None:
        kaputt = os.path.join(self.ordner, "kaputt.pkg")
        Path(kaputt).write_bytes(b"x")
        with mock.patch.object(wz, "lesen", side_effect=wz.Fehler("nicht lesbar")):
            self.f._pakete_hinzufuegen([kaputt])
            _warten(lambda: "nicht lesbar" in self.f.protokoll.get("1.0", "end"), 10)
        self.assertIn("kaputt.pkg", self.f.protokoll.get("1.0", "end"))
        self.assertEqual([], self.f.pakete)

    # ---------------- Format und Aktion ----------------
    def test_die_formatwahl_wird_gemerkt_und_gefaerbt(self) -> None:
        self._laden("alpha.pkg")
        f = self.f
        f._format_waehlen("exfat")
        self.assertEqual("exfat", self.app._load_setting(fz.EINST_FORMAT, ""))
        self.assertEqual("accent_btn", f._kacheln["exfat"][0]._rollen[0])
        self.assertEqual("bg_main", f._kacheln["ffpfsc"][0]._rollen[0])
        self.assertEqual("Alpha Spiel [PPSA00001].exfat", f.ergebnis_var["output"].get())

    def test_die_ausgabe_je_aktion(self) -> None:
        self._laden("alpha.pkg")
        f = self.f
        f.format_schluessel = "ffpfsc"
        for aktion, soll in (("umwandeln", "Alpha Spiel [PPSA00001].ffpfsc"), ("extrahieren", "Alpha Spiel [PPSA00001]"),
                             ("pruefen", "-")):
            with self.subTest(aktion=aktion):
                f.aktion_var.set(aktion)
                f._aktion_geaendert()
                self.assertEqual(soll, f.ergebnis_var["output"].get())
        f.aktion_var.set("extrahieren")
        f._aktion_geaendert()
        self.assertTrue(all(k._rollen[0] == "bg_main" for k, _a, _b in f._kacheln.values()), "keine Kachel gewaehlt")

    # ---------------- Pruefen ----------------
    def test_pruefen_zeigt_das_ergebnis_und_die_befunde(self) -> None:
        self._laden("alpha.pkg")
        f = self.f
        f.aktion_var.set("pruefen")
        f._aktion_geaendert()
        antwort = {"pass": 30, "warn": 0, "fail": 1, "results": [
            {"Check": "ok", "Level": "pass", "Message": "gut"},
            {"Check": "license.license.dat", "Level": "fail", "Message": "missing"}]}
        with mock.patch.object(wz, "pruefen", return_value=antwort):
            f._starten()
            self.assertTrue(_warten(lambda: f._job is None))
        self.assertIn("30 bestanden", f.auftrag_var.get())
        self.assertIn("1 Fehler", f.auftrag_var.get())
        log = f.protokoll.get("1.0", "end")
        self.assertIn("[FAIL] license.license.dat: missing", log)
        self.assertNotIn("[PASS]", log)
        self.assertIn("[BEFUND]", log)
        self.assertNotIn("Fehlgeschlagen", f.auftrag_var.get())

    def test_pruefen_ohne_befund_ist_ok(self) -> None:
        self._laden("alpha.pkg")
        f = self.f
        f.aktion_var.set("pruefen")
        with mock.patch.object(wz, "pruefen", return_value={"pass": 33, "warn": 0, "fail": 0, "results": []}):
            f._starten()
            self.assertTrue(_warten(lambda: f._job is None))
        self.assertIn("[OK]", f.protokoll.get("1.0", "end"))

    # ---------------- Extrahieren ----------------
    def _entpacken_attrappe(self, inhalt=("eboot.bin", "sce_sys/param.json")):
        def extrahieren(werkzeug, paket, ziel, *, zeile=None, fortschritt=None, abbruch=None, **_kw):
            for i, name in enumerate(inhalt, 1):
                datei = Path(ziel) / name
                datei.parent.mkdir(parents=True, exist_ok=True)
                datei.write_bytes(b"x")
                if fortschritt:
                    fortschritt(i * 100 // len(inhalt), name)
            return "OK - extracted %d file(s) to %s" % (len(inhalt), ziel)
        return extrahieren

    def test_extrahieren_schreibt_den_dump_ordner(self) -> None:
        self._laden("alpha.pkg")
        f = self.f
        ziel = os.path.join(self.ordner, "ziel")
        os.makedirs(ziel)
        f.ziel_var.set(ziel)
        f.aktion_var.set("extrahieren")
        f._aktion_geaendert()
        with mock.patch.object(wz, "extrahieren", side_effect=self._entpacken_attrappe()):
            f._starten()
            self.assertTrue(_warten(lambda: f._job is None))
        dump = os.path.join(ziel, "Alpha Spiel [PPSA00001]")
        self.assertTrue(os.path.isfile(os.path.join(dump, "eboot.bin")))
        self.assertTrue(os.path.isfile(os.path.join(dump, "sce_sys", "param.json")))
        self.assertTrue(f.auftrag_var.get().startswith("Fertig"))
        self.assertEqual(100.0, float(f.balken["value"]))
        self.assertEqual(dump, f._z.get("ausgabe"))

    def test_ohne_zielordner_wird_nicht_gestartet(self) -> None:
        self._laden("alpha.pkg")
        f = self.f
        f.ziel_var.set("")
        f.aktion_var.set("extrahieren")
        with mock.patch.object(wz, "extrahieren") as lauf:
            f._starten()
        lauf.assert_not_called()
        self.assertEqual(1, len(self.dialoge["fehler"]))
        self.assertIsNone(f._job)

    def test_ein_vorhandener_ordner_wird_nur_mit_haken_ersetzt(self) -> None:
        self._laden("alpha.pkg")
        f = self.f
        ziel = os.path.join(self.ordner, "ziel")
        dump = os.path.join(ziel, "Alpha Spiel [PPSA00001]")
        os.makedirs(dump)
        Path(dump, "alt.txt").write_text("alt")
        f.ziel_var.set(ziel)
        f.aktion_var.set("extrahieren")
        with mock.patch.object(wz, "extrahieren", side_effect=self._entpacken_attrappe()) as lauf:
            f._starten()
            lauf.assert_not_called()
            self.assertEqual(1, len(self.dialoge["info"]))
            self.assertTrue(os.path.isfile(os.path.join(dump, "alt.txt")), "ohne Haken bleibt alles")
            f.ueberschreiben_var.set(True)
            f._starten()
            self.assertTrue(_warten(lambda: f._job is None))
        self.assertFalse(os.path.exists(os.path.join(dump, "alt.txt")))
        self.assertTrue(os.path.isfile(os.path.join(dump, "eboot.bin")))

    def test_ein_fehler_beim_entpacken_wird_gemeldet(self) -> None:
        self._laden("alpha.pkg")
        f = self.f
        f.ziel_var.set(self.ordner)
        f.aktion_var.set("extrahieren")
        with mock.patch.object(wz, "extrahieren", side_effect=wz.Fehler("[error] kaputt")):
            f._starten()
            self.assertTrue(_warten(lambda: f._job is None))
        self.assertIn("Fehlgeschlagen", f.auftrag_var.get())
        self.assertIn("kaputt", f.protokoll.get("1.0", "end"))
        self.assertTrue(f.start_knopf.winfo_exists())

    def test_abbrechen_beendet_den_auftrag(self) -> None:
        self._laden("alpha.pkg")
        f = self.f
        f.ziel_var.set(self.ordner)
        f.aktion_var.set("umwandeln")

        def langsam(werkzeug, paket, ziel, *, abbruch=None, **_kw):
            Path(ziel).mkdir(parents=True, exist_ok=True)
            Path(ziel, "halb.bin").write_bytes(b"x")
            ende = time.time() + 20
            while time.time() < ende:
                if abbruch and abbruch():
                    raise wz.Fehler("abgebrochen")
                time.sleep(0.02)
            return "OK"

        with mock.patch.object(wz, "extrahieren", side_effect=langsam):
            f._starten()
            _pumpen(0.5)
            self.assertIsNotNone(f._job)
            f._abbrechen()
            self.assertTrue(_warten(lambda: f._job is None, 10))
        self.assertIn("Fehlgeschlagen", f.auftrag_var.get())
        self.assertEqual([], [o for o in f._staging if os.path.isdir(o)], "der halbe Entpackordner ist weg")

    # ---------------- Umwandeln = entpacken + Aufgabe 1 ----------------
    def _aufgabe_1_attrappe(self, ok: bool = True, laeuft: bool = True, dauer: float = 0.8):
        gesehen: dict = {}

        def starten() -> None:
            app = self.app
            gesehen["modus"] = app.current_mode.get()
            gesehen["quelle"] = app.source_path.get()
            gesehen["quelle_da"] = os.path.isfile(os.path.join(app.source_path.get(), "eboot.bin"))
            gesehen["ziel"] = app.dest_path.get()
            gesehen["format"] = app.target_format.get()
            if laeuft:
                app.is_running = True
                app._last_task_ok = False

                def fertig() -> None:
                    app.is_running = False
                    app._last_task_ok = ok
                _WURZEL.after(int(dauer * 1000), fertig)

        return starten, gesehen

    def _zustand_sichern(self) -> None:
        app = self.app
        alt = (app.current_mode.get(), app.source_path.get(), app.dest_path.get(), app.target_format.get(),
               getattr(app, "is_running", False), getattr(app, "_last_task_ok", False))

        def zurueck() -> None:
            app.is_running = alt[4]
            app._last_task_ok = alt[5]
            app._set_mode_from_sidebar(alt[0])
            app.source_path.set(alt[1])
            app.dest_path.set(alt[2])
            app.target_format.set(alt[3])
        self.addCleanup(zurueck)

    def test_umwandeln_entpackt_und_uebergibt_an_aufgabe_1(self) -> None:
        self._zustand_sichern()
        self._laden("alpha.pkg")
        f = self.f
        ziel = os.path.join(self.ordner, "ziel")
        os.makedirs(ziel)
        f.ziel_var.set(ziel)
        f.aktion_var.set("umwandeln")
        f._format_waehlen("ffpfsc")
        starten, gesehen = self._aufgabe_1_attrappe()
        with mock.patch.object(wz, "extrahieren", side_effect=self._entpacken_attrappe()), \
                mock.patch.object(self.app, "_launch_task", side_effect=starten):
            f._starten()
            self.assertTrue(_warten(lambda: f._job is None and f._uebergabe is None, 20))
        self.assertEqual("pack_folder", gesehen["modus"])
        self.assertTrue(gesehen["quelle"].endswith("Alpha Spiel [PPSA00001]"))
        self.assertTrue(gesehen["quelle_da"], "beim Start von Aufgabe 1 liegt der entpackte Ordner da")
        self.assertEqual(ziel, gesehen["ziel"])
        self.assertEqual(self.app._zielformat_label("ffpfsc", "pack_folder", gesehen["quelle"]), gesehen["format"])
        self.assertTrue(f.auftrag_var.get().startswith("Fertig"))
        self.assertEqual([], [o for o in f._staging if os.path.isdir(o)], "der Entpackordner wird abgeraeumt")
        self.assertFalse(os.path.isdir(os.path.dirname(gesehen["quelle"])))

    def test_hat_aufgabe_1_nichts_gebaut_wird_es_nicht_als_fertig_gemeldet(self) -> None:
        self._zustand_sichern()
        self._laden("alpha.pkg")
        f = self.f
        f.ziel_var.set(self.ordner)
        f.aktion_var.set("umwandeln")
        starten, _gesehen = self._aufgabe_1_attrappe(laeuft=False)
        with mock.patch.object(wz, "extrahieren", side_effect=self._entpacken_attrappe()), \
                mock.patch.object(self.app, "_launch_task", side_effect=starten):
            f._starten()
            self.assertTrue(_warten(lambda: f._job is None and f._uebergabe is None, 20))
        self.assertIn("Fehlgeschlagen", f.auftrag_var.get())
        self.assertIn(STRINGS["ps5pkg.log_convert_not_done"]["de"], f.protokoll.get("1.0", "end"))

    def test_scheitert_aufgabe_1_steht_nicht_fertig_da(self) -> None:
        self._zustand_sichern()
        self._laden("alpha.pkg")
        f = self.f
        f.ziel_var.set(self.ordner)
        f.aktion_var.set("umwandeln")
        starten, _gesehen = self._aufgabe_1_attrappe(ok=False)
        with mock.patch.object(wz, "extrahieren", side_effect=self._entpacken_attrappe()), \
                mock.patch.object(self.app, "_launch_task", side_effect=starten):
            f._starten()
            self.assertTrue(_warten(lambda: f._job is None and f._uebergabe is None, 20))
        self.assertIn("Fehlgeschlagen", f.auftrag_var.get())

    def test_laeuft_im_hauptfenster_eine_aufgabe_wird_nicht_umgewandelt(self) -> None:
        self._zustand_sichern()
        self._laden("alpha.pkg")
        f = self.f
        f.ziel_var.set(self.ordner)
        f.aktion_var.set("umwandeln")
        self.app.is_running = True
        with mock.patch.object(wz, "extrahieren") as lauf:
            f._starten()
        lauf.assert_not_called()
        self.assertEqual(1, len(self.dialoge["info"]))
        self.assertIsNone(f._job)

    def test_ohne_dotnet_wird_nicht_gestartet(self) -> None:
        self._laden("alpha.pkg")
        f = self.f
        f.ziel_var.set(self.ordner)
        with mock.patch.object(wz, "dotnet_ordner", return_value=""), mock.patch.object(wz, "extrahieren") as lauf:
            f._starten()
        lauf.assert_not_called()
        self.assertEqual(1, len(self.dialoge["fehler"]))

    def test_ohne_werkzeug_wird_nicht_gestartet(self) -> None:
        self._laden("alpha.pkg")
        f = self.f
        f.ziel_var.set(self.ordner)
        with mock.patch.object(fz.Ps5PkgFenster, "_werkzeug", return_value=""), mock.patch.object(wz, "extrahieren") as lauf:
            f._starten()
        lauf.assert_not_called()
        self.assertEqual(1, len(self.dialoge["fehler"]))

    # ---------------- Spielordner als Quelle, Bau eines Pakets ----------------
    def _spielordner(self, name: str = "Spiel", titel: str = "Gamma Spiel", tid: str = "PPSA00003",
                     cid: str = "UP0000-PPSA00003_00-GAMMAGAMMAGAMMA0") -> str:
        ordner = os.path.join(self.ordner, name)
        os.makedirs(os.path.join(ordner, "sce_sys"))
        Path(ordner, "eboot.bin").write_bytes(b"\x7fELF" + bytes(100))
        Path(ordner, "sce_sys", "param.json").write_text(__import__("json").dumps({
            "titleId": tid, "contentId": cid, "contentVersion": "01.002.000", "applicationCategoryType": 0,
            "localizedParameters": {"defaultLanguage": "en-US", "en-US": {"titleName": titel}}}), encoding="utf-8")
        from PIL import Image
        Image.new("RGB", (8, 8), "red").save(os.path.join(ordner, "sce_sys", "icon0.png"))
        return ordner

    def _spielordner_laden(self, **kw) -> str:
        ordner = self._spielordner(**kw)
        self.f._pakete_hinzufuegen([ordner], waehlen=True)
        self.assertTrue(_warten(lambda: self.f.aktuell is not None and self.f.aktuell.pfad == ordner))
        return ordner

    def test_ein_spielordner_wird_gelesen_und_angezeigt(self) -> None:
        ordner = self._spielordner_laden()
        f = self.f
        info = f.aktuell
        self.assertTrue(info.ist_ordner)
        self.assertEqual(("Gamma Spiel", "PPSA00003", "UP0000-PPSA00003_00-GAMMAGAMMAGAMMA0"),
                         (info.titel, info.title_id, info.content_id))
        self.assertGreater(info.groesse, 100)
        self.assertTrue(os.path.isfile(info.icon) and not info.icon.startswith(ordner), "das Cover ist eine Kopie")
        self.assertEqual("Dump-Ordner", f.liste.item(ordner, "values")[2])
        self.assertEqual("Spielordner", f.paket_typ.cget("text"))
        self.assertEqual("Spielordner (Dump)", dict(f.tech.item(i, "values") for i in f.tech.get_children())["Quelle"])

    def test_ein_ordner_mit_spielordnern_und_paketen_liefert_alles(self) -> None:
        self._spielordner(name="a_spiel")
        self._spielordner(name="b_spiel", titel="Delta", tid="PPSA00004", cid="UP0000-PPSA00004_00-DELTADELTADELTA00")
        gefunden = [os.path.basename(p) for p in self.f._quellen_in(self.ordner)]
        self.assertEqual(["alpha.pkg", "beta.pkg", "a_spiel", "b_spiel"], gefunden)
        self.assertEqual([os.path.join(self.ordner, "a_spiel")], self.f._quellen_in(os.path.join(self.ordner, "a_spiel")))

    def test_fuer_einen_spielordner_gibt_es_nur_erstellen_und_umwandeln(self) -> None:
        self._spielordner_laden()
        f = self.f
        self.assertTrue(f._aktion_moeglich("umwandeln"))
        self.assertFalse(f._aktion_moeglich("extrahieren"))
        self.assertFalse(f._aktion_moeglich("pruefen"))
        self.assertTrue(f._format_moeglich("pkg"))
        f.aktion_var.set("pruefen")
        f._paket_waehlen(f.aktuell)
        self.assertEqual("umwandeln", f.aktion_var.get(), "eine Aktion, die es hier nicht gibt, springt zurueck")

    def test_die_kachel_paket_gibt_es_nur_fuer_einen_spielordner(self) -> None:
        self._laden("alpha.pkg")
        f = self.f
        self.assertFalse(f._format_moeglich("pkg"))
        f._format_waehlen("pkg")
        self.assertEqual("ffpfsc", f.format_schluessel)
        self.assertIn("Spielordner", f.status_var.get())
        ordner = self._spielordner_laden()
        f._format_waehlen("pkg")
        self.assertEqual("pkg", f.format_schluessel)
        self.assertEqual("accent_btn", f._kacheln["pkg"][0]._rollen[0])
        self.assertTrue(f.ergebnis_var["output"].get().startswith("UP0000-PPSA00003_00-GAMMAGAMMAGAMMA0"))
        self.assertTrue(ordner)
        self.f._pakete_hinzufuegen([os.path.join(self.ordner, "alpha.pkg")], waehlen=True)
        self.assertTrue(_warten(lambda: f.aktuell is not None and not f.aktuell.ist_ordner))
        self.assertEqual("ffpfsc", f.format_schluessel, "fuer ein Paket springt die Wahl zurueck")

    def test_beim_schliessen_bleibt_der_spielordner_unberuehrt(self) -> None:
        ordner = self._spielordner_laden()
        kopie = os.path.dirname(self.f.aktuell.icon)
        self.assertTrue(os.path.isdir(kopie))
        self.f.win.destroy()
        _pumpen(0.1)
        self.assertTrue(os.path.isfile(os.path.join(ordner, "sce_sys", "icon0.png")))
        self.assertTrue(os.path.isfile(os.path.join(ordner, "sce_sys", "param.json")))
        self.assertTrue(os.path.isfile(os.path.join(ordner, "eboot.bin")))
        self.assertFalse(os.path.exists(kopie), "nur die Kopie des Covers wird entfernt")

    def _bauen_vorbereiten(self, bauen_attrappe, **kw) -> tuple[str, str]:
        ordner = self._spielordner_laden(**kw)
        f = self.f
        ziel = os.path.join(self.ordner, "ziel")
        os.makedirs(ziel)
        f.ziel_var.set(ziel)
        f._format_waehlen("pkg")
        # Die Reparatur der param.json (Aufgabe 1) hat ihre eigenen Tests; hier wird sie abgelehnt.
        reparatur = mock.patch.object(self.app, "_offer_repair_param_json", return_value=False)
        reparatur.start()
        self.addCleanup(reparatur.stop)
        return ordner, ziel

    def test_bauen_schreibt_das_paket_und_prueft_es(self) -> None:
        ordner, ziel = self._bauen_vorbereiten(None)
        f = self.f
        aufrufe = {}

        def bauen(werkzeug, quelle, zielordner, **kw):
            aufrufe.update(kw, quelle=quelle, ziel=zielordner, temp_da=os.path.isdir(kw["temp"]))
            kw["fortschritt"](50, "Media/x.bundle")
            pfad = os.path.join(zielordner, "UP0000-PPSA00003_00-GAMMAGAMMAGAMMA0-A0102-V0102.pkg")
            Path(pfad).write_bytes(b"pkg")
            return pfad

        with mock.patch.object(wz, "bauen", side_effect=bauen), mock.patch.object(wz, "pruefen", return_value={
                "pass": 36, "warn": 0, "fail": 0, "results": []}):
            f._starten()
            self.assertTrue(_warten(lambda: f._job is None, 20))
        self.assertEqual(ordner, aufrufe["quelle"])
        self.assertEqual(ziel, aufrufe["ziel"])
        self.assertEqual("UP0000-PPSA00003_00-GAMMAGAMMAGAMMA0", aufrufe["content_id"])
        self.assertEqual(("PPSA00003", "Gamma Spiel", "01.002.000"), (aufrufe["title_id"], aufrufe["titel"], aufrufe["version"]))
        self.assertTrue(aufrufe["temp_da"])
        self.assertEqual(ziel, os.path.dirname(aufrufe["temp"]), "der Arbeitsordner liegt im Zielordner")
        self.assertFalse(os.path.exists(aufrufe["temp"]), "und wird danach entfernt")
        self.assertTrue(f.auftrag_var.get().startswith("Fertig. Paket: UP0000-PPSA00003"))
        log = f.protokoll.get("1.0", "end")
        self.assertIn("[OK] Prüfung: 36 bestanden", log)
        self.assertIn("Debug-Paket (FPKG)", log)
        self.assertEqual(ziel, f._z.get("ausgabe"))
        self.assertEqual(100.0, float(f.balken_gesamt["value"]))

    def test_ppt_baut_in_eine_datei_nicht_in_den_zielordner(self) -> None:
        """17.10.2026 (Funktionspruefung an einem echten Spiel): ppt.bauen() erwartet in "ziel" den
        vollstaendigen Dateipfad (anders als wz.bauen(), das selbst einen Namen im Zielordner waehlt) - der
        blosse Zielordner endete beim echten ProsperoPkgTool immer mit "Access to the path '...' is denied",
        weil es dort eine Datei zu OEFFNEN versuchte, wo ein Ordner lag."""
        ordner, ziel = self._bauen_vorbereiten(None)
        f = self.f
        self.app._save_setting(opt.BUILDER, "ppt")
        self.addCleanup(lambda: self.app._save_setting(opt.BUILDER, "lpp"))
        aufrufe = {}

        def bauen(werkzeug, quelle, ziel_datei, **kw):
            aufrufe["ziel"] = ziel_datei
            Path(ziel_datei).write_bytes(b"pkg")
            return ziel_datei

        with mock.patch.object(fz.Ps5PkgFenster, "_werkzeug_ppt", return_value="prospero"), \
                mock.patch.object(ppt, "bauen", side_effect=bauen), mock.patch.object(wz, "pruefen", return_value={
                "pass": 1, "warn": 0, "fail": 0, "results": []}):
            f._starten()
            self.assertTrue(_warten(lambda: f._job is None, 20))
        self.assertNotEqual(ziel, aufrufe["ziel"], "ppt.bauen() darf nicht den blossen Zielordner bekommen")
        self.assertEqual(ziel, os.path.dirname(aufrufe["ziel"]), "die Datei muss im Zielordner liegen")
        self.assertTrue(aufrufe["ziel"].endswith(".pkg"))
        self.assertTrue(os.path.isfile(aufrufe["ziel"]))

    def test_ein_gescheiterter_bau_raeumt_unfertiges_weg(self) -> None:
        ordner, ziel = self._bauen_vorbereiten(None)
        f = self.f
        alt = os.path.join(ziel, "alt.pkg")
        Path(alt).write_bytes(b"alt")

        def bauen(werkzeug, quelle, zielordner, **kw):
            Path(zielordner, "halb.pkg").write_bytes(b"halb")
            raise wz.Fehler("[error] kaputt")

        with mock.patch.object(wz, "bauen", side_effect=bauen):
            f._starten()
            self.assertTrue(_warten(lambda: f._job is None, 20))
        self.assertFalse(os.path.exists(os.path.join(ziel, "halb.pkg")))
        self.assertTrue(os.path.isfile(alt), "was vorher da war, bleibt")
        self.assertIn("Fehlgeschlagen", f.auftrag_var.get())
        self.assertEqual([], [n for n in os.listdir(ziel) if n.startswith("ps5conv_pkgbau_")], "der Arbeitsordner ist weg")
        self.assertTrue(os.path.isfile(os.path.join(ordner, "eboot.bin")), "der Spielordner bleibt unberuehrt")

    def test_abbrechen_beim_bauen(self) -> None:
        ordner, ziel = self._bauen_vorbereiten(None)
        f = self.f

        def bauen(werkzeug, quelle, zielordner, *, abbruch=None, **kw):
            Path(zielordner, "halb.pkg").write_bytes(b"x")
            ende = time.time() + 20
            while time.time() < ende:
                if abbruch():
                    raise wz.Fehler("abgebrochen")
                time.sleep(0.02)
            return "x"

        with mock.patch.object(wz, "bauen", side_effect=bauen):
            f._starten()
            _pumpen(0.5)
            self.assertIsNotNone(f._job)
            f._abbrechen()
            self.assertTrue(_warten(lambda: f._job is None, 10))
        self.assertEqual([], os.listdir(ziel))

    def test_ohne_gueltige_content_id_wird_nicht_gebaut(self) -> None:
        self._spielordner_laden(cid="kaputt")
        f = self.f
        f.ziel_var.set(self.ordner)
        f._format_waehlen("pkg")
        with mock.patch.object(wz, "bauen") as bauen:
            f._starten()
        bauen.assert_not_called()
        self.assertEqual(1, len(self.dialoge["fehler"]))
        self.assertIsNone(f._job)

    def test_eine_beanstandete_param_json_fragt_nach(self) -> None:
        self._bauen_vorbereiten(None)
        f = self.f

        class Befund:
            ok = False

            def als_text(self, mit_hinweisen=False):
                return ["[FEHLER] applicationDrmType 'upgradable' ist ein Anwendungstyp"]

        with mock.patch("ps5_validator.utils.param_check.pruefe_datei", return_value=Befund()), \
                mock.patch.object(fz.messagebox, "askyesno", return_value=False) as frage, \
                mock.patch.object(wz, "bauen") as bauen:
            f._starten()
        frage.assert_called_once()
        self.assertIn("applicationDrmType", frage.call_args.args[1])
        bauen.assert_not_called()
        self.assertIsNone(f._job)

    def test_eine_repariert_param_json_wird_neu_gelesen_und_gebaut(self) -> None:
        ordner, ziel = self._bauen_vorbereiten(None)
        f = self.f
        param_pfad = os.path.join(ordner, "sce_sys", "param.json")

        class Befund:
            ok = False

            def als_text(self, mit_hinweisen=False):
                return ["[FEHLER] applicationDrmType 'upgradable' ist ein Anwendungstyp"]

        def reparieren(quellordner, befund) -> bool:
            import json
            daten = json.loads(Path(param_pfad).read_text(encoding="utf-8"))
            daten["applicationDrmType"] = "standard"
            daten["titleId"] = "PPSA00009"
            daten["contentId"] = "UP0000-PPSA00009_00-REPARIERTREPARIE"
            Path(param_pfad).write_text(json.dumps(daten), encoding="utf-8")
            return True

        gebaut = {}

        def bauen(werkzeug, quelle, zielordner, **kw):
            gebaut.update(kw)
            pfad = os.path.join(zielordner, "x-A0102-V0102.pkg")
            Path(pfad).write_bytes(b"p")
            return pfad

        with mock.patch("ps5_validator.utils.param_check.pruefe_datei", return_value=Befund()), \
                mock.patch.object(self.app, "_offer_repair_param_json", side_effect=reparieren) as repar, \
                mock.patch.object(fz.messagebox, "askyesno") as frage, \
                mock.patch.object(wz, "bauen", side_effect=bauen), \
                mock.patch.object(wz, "pruefen", return_value={"pass": 1, "warn": 0, "fail": 0, "results": []}):
            f._starten()
            self.assertTrue(_warten(lambda: f._job is None, 20))
        repar.assert_called_once()
        frage.assert_not_called()
        self.assertEqual(("UP0000-PPSA00009_00-REPARIERTREPARIE", "PPSA00009"), (gebaut["content_id"], gebaut["title_id"]))
        self.assertEqual("PPSA00009", f.aktuell.title_id)
        self.assertTrue(f.auftrag_var.get().startswith("Fertig"))

    def test_ein_vorhandenes_paket_gleichen_namens_wird_nur_mit_haken_ersetzt(self) -> None:
        ordner, ziel = self._bauen_vorbereiten(None)
        f = self.f
        alt = os.path.join(ziel, "UP0000-PPSA00003_00-GAMMAGAMMAGAMMA0-A0102-V0102.pkg")
        Path(alt).write_bytes(b"alt")
        fremd = os.path.join(ziel, "UP0000-PPSA00099_00-ANDERESANDERES000-A0100-V0100.pkg")
        Path(fremd).write_bytes(b"fremd")

        def bauen(werkzeug, quelle, zielordner, **kw):
            Path(alt).write_bytes(b"neu")
            return alt

        with mock.patch.object(wz, "bauen", side_effect=bauen) as lauf, \
                mock.patch.object(wz, "pruefen", return_value={"pass": 1, "warn": 0, "fail": 0, "results": []}):
            f._starten()
            lauf.assert_not_called()
            self.assertEqual(1, len(self.dialoge["info"]))
            self.assertEqual(b"alt", Path(alt).read_bytes())
            f.ueberschreiben_var.set(True)
            f._starten()
            self.assertTrue(_warten(lambda: f._job is None, 20))
        self.assertEqual(b"neu", Path(alt).read_bytes())
        self.assertEqual(b"fremd", Path(fremd).read_bytes(), "ein anderes Paket bleibt, wie es ist")

    def test_der_platz_wird_vor_dem_bauen_geprueft(self) -> None:
        self._bauen_vorbereiten(None)
        f = self.f
        info = f.aktuell
        info.groesse = 10 * 1024 ** 3
        wenig = mock.Mock(free=1024 ** 3)
        with mock.patch.object(fz.shutil, "disk_usage", return_value=wenig), mock.patch.object(wz, "bauen") as bauen:
            f._starten()
        bauen.assert_not_called()
        self.assertEqual(1, len(self.dialoge["fehler"]), "weniger als die Haelfte: Absage")
        knapp = mock.Mock(free=int(info.groesse * 1.2))
        with mock.patch.object(fz.shutil, "disk_usage", return_value=knapp), \
                mock.patch.object(fz.messagebox, "askyesno", return_value=False) as frage, \
                mock.patch.object(wz, "bauen") as bauen:
            f._starten()
        frage.assert_called()
        bauen.assert_not_called()

    def test_ein_paket_wird_nicht_entpackt_wenn_der_arbeitsplatz_fehlt(self) -> None:
        self._laden("alpha.pkg")
        f = self.f
        f.ziel_var.set(self.ordner)
        f.aktion_var.set("umwandeln")
        with mock.patch.object(fz.shutil, "disk_usage", return_value=mock.Mock(free=1000)), \
                mock.patch.object(wz, "extrahieren") as lauf:
            f._starten()
        lauf.assert_not_called()
        self.assertEqual(1, len(self.dialoge["fehler"]))

    def test_ein_spielordner_geht_ohne_entpacken_an_aufgabe_1(self) -> None:
        self._zustand_sichern()
        ordner = self._spielordner_laden()
        f = self.f
        ziel = os.path.join(self.ordner, "ziel")
        os.makedirs(ziel)
        f.ziel_var.set(ziel)
        f._format_waehlen("exfat")
        gesehen = {}

        def starten() -> None:
            gesehen["quelle"] = self.app.source_path.get()
            gesehen["format"] = self.app.target_format.get()
            self.app.is_running = True
            self.app._last_task_ok = False

            def fertig() -> None:
                self.app.is_running = False
                self.app._last_task_ok = True
            _WURZEL.after(500, fertig)

        with mock.patch.object(wz, "extrahieren") as entpacken, mock.patch.object(self.app, "_launch_task", side_effect=starten):
            f._starten()
            self.assertTrue(_warten(lambda: f._uebergabe is None, 20))
        entpacken.assert_not_called()
        self.assertEqual(ordner, gesehen["quelle"])
        self.assertEqual(self.app._zielformat_label("exfat", "pack_folder", ordner), gesehen["format"])
        self.assertTrue(f.auftrag_var.get().startswith("Fertig"))
        self.assertTrue(os.path.isfile(os.path.join(ordner, "eboot.bin")), "der Spielordner wird nicht aufgeraeumt")

    # ---------------- Schliessen ----------------
    def test_beim_schliessen_wird_aufgeraeumt(self) -> None:
        cover = tempfile.mkdtemp(prefix="ps5conv_pkgcover_")
        staging = tempfile.mkdtemp(prefix="ps5conv_ps5pkg_")
        self.f._cover_ordner.append(cover)
        self.f._staging.append(staging)
        self.f.win.destroy()
        _pumpen(0.1)
        self.assertFalse(os.path.exists(cover))
        self.assertFalse(os.path.exists(staging))
        self.assertIsNone(getattr(self.app, fz.FENSTER_ATTRIBUT, None))

    def test_laeuft_ein_auftrag_fragt_das_schliessen_nach(self) -> None:
        self.f._job = {"art": "extrahieren", "info": None, "ziel": ""}
        self.dialoge["frage"].clear()
        with mock.patch.object(fz.messagebox, "askyesno", return_value=False) as frage:
            self.f._schliessen()
        frage.assert_called_once()
        self.assertTrue(self.f.win.winfo_exists())
        self.f._job = None

    # ---------------- Auf die PS5 entpacken (seit v1.9.72) ----------------
    def _konsole(self, **einstellung):
        """Fenster mit geladenem Paket, Aktion "Auf die PS5 entpacken" und eingetragener Adresse samt Ordner."""
        self._laden("alpha.pkg")
        f = self.f
        alt = f.adresse_var.get()
        self.addCleanup(f.adresse_var.set, alt)               # dieselbe Variable wie in der Ansicht KONSOLE
        f.adresse_var.set(einstellung.get("adresse", "10.0.0.5"))
        f.fern_var.set(einstellung.get("fern", "/mnt/usb0/Alpha"))
        f.aktion_var.set(fz.AKTION_KONSOLE)
        f._aktion_geaendert()
        return f

    def _direkt(self, ergebnis=None, fehler=None, vorhanden=False, ja_nein_abbrechen=None, bestaetigt=True):
        """Ersetzt FTP und pkg_direkt: gibt die Aufrufe zurueck. ``ja_nein_abbrechen`` ist die Antwort der Dreifachfrage."""
        aufrufe: list = []
        fragen: list = []

        def direkt(werkzeug, paket, adresse, fern, **kw):
            aufrufe.append({"werkzeug": werkzeug, "paket": paket, "adresse": adresse, "fern": fern,
                            "fortsetzen": kw.get("fortsetzen")})
            if fehler is not None:
                raise fehler
            stand = ergebnis or fz.ftp.Fortschritt(dateien=3, dateien_gesamt=3, bytes=3 * 1024 ** 2, bytes_gesamt=3 * 1024 ** 2)
            kw["auf_fortschritt"](stand)
            return stand

        stuetzen = (
            mock.patch.object(fz.pkg_direkt, "direkt_entpacken", side_effect=direkt),
            mock.patch.object(fz.ftp, "vorhanden", return_value=vorhanden),
            mock.patch.object(fz.messagebox, "askyesnocancel",
                              side_effect=lambda *a, **k: (fragen.append(a), ja_nein_abbrechen)[1]),
            mock.patch.object(fz.messagebox, "askyesno",
                              side_effect=lambda *a, **k: (fragen.append(a), bestaetigt)[1]),
        )
        for s in stuetzen:
            s.start()
            self.addCleanup(s.stop)
        return aufrufe, fragen

    def test_die_aktion_zeigt_adresse_und_ordner_statt_des_zielordners(self) -> None:
        f = self._konsole()
        self.assertEqual("pack", f.fern_reihe.winfo_manager())
        self.assertEqual("", f.ziel_reihe.winfo_manager(), "der Zielordner auf dem PC passt hier nicht")
        self.assertEqual("", f.ueberschreiben.winfo_manager())
        self.assertEqual("10.0.0.5:/mnt/usb0/Alpha", f.ergebnis_var["output"].get())
        self.assertTrue(all(k._rollen[0] == "bg_main" for k, _a, _b in f._kacheln.values()), "keine Kachel gewaehlt")
        f.aktion_var.set("extrahieren")
        f._aktion_geaendert()
        self.assertEqual("", f.fern_reihe.winfo_manager())
        self.assertEqual("pack", f.ziel_reihe.winfo_manager())
        self.assertEqual("pack", f.ueberschreiben.winfo_manager())

    def test_ein_spielordner_kennt_die_aktion_nicht(self) -> None:
        self._laden("alpha.pkg")
        self.f.aktuell.pfad = self.ordner
        self.f.aktuell.typ = wz.TYP_ORDNER
        self.assertFalse(self.f._aktion_moeglich(fz.AKTION_KONSOLE))
        self.assertTrue(self.f._aktion_moeglich(fz.AKTION_UMWANDELN))

    def test_die_vier_aktionen_stehen_in_einer_umbrechenden_zeile(self) -> None:
        self.assertEqual({"umwandeln", "extrahieren", "pruefen", "konsole"}, set(self.f._aktion_knoepfe))
        _pumpen(0.5)                    # die Zeile legt ihre Kinder erst nach dem ersten Groessenereignis
        for knopf in self.f._aktion_knoepfe.values():
            self.assertEqual("place", knopf.winfo_manager(), "FlussZeile setzt mit place - sie bricht um statt abzuschneiden")

    def test_ohne_adresse_wird_nicht_gestartet(self) -> None:
        f = self._konsole(adresse="  ")
        aufrufe, _fragen = self._direkt()
        f._starten()
        self.assertIsNone(f._job)
        self.assertEqual([], aufrufe)
        self.assertIn(STRINGS["ps5pkg.err_no_address"]["de"], [d[1] for d in self.dialoge["fehler"]])

    def test_die_wurzel_der_konsole_ist_kein_ziel(self) -> None:
        f = self._konsole(fern=" / ")
        aufrufe, _fragen = self._direkt()
        f._starten()
        self.assertIsNone(f._job)
        self.assertEqual([], aufrufe)
        self.assertIn(STRINGS["ps5pkg.err_no_remote"]["de"], [d[1] for d in self.dialoge["fehler"]])

    def test_entpacken_auf_die_ps5_ruft_pkg_direkt_und_meldet_fertig(self) -> None:
        f = self._konsole(fern="mnt/usb0/Alpha/")
        aufrufe, fragen = self._direkt()
        f._starten()
        self.assertTrue(_ende(f))
        self.assertEqual(1, len(aufrufe))
        self.assertEqual(("10.0.0.5", "/mnt/usb0/Alpha", False), (aufrufe[0]["adresse"], aufrufe[0]["fern"], aufrufe[0]["fortsetzen"]))
        self.assertEqual(next(iter(self.pakete)), aufrufe[0]["paket"])
        self.assertEqual(1, len(fragen), "eine Bestaetigung mit Groesse und Dauer")
        self.assertIn("/mnt/usb0/Alpha", fragen[0][1])
        self.assertTrue(f.auftrag_var.get().startswith("Fertig. Auf die PS5 entpackt: /mnt/usb0/Alpha"), f.auftrag_var.get())
        self.assertEqual(100.0, float(f.balken["value"]))
        log = f.protokoll.get("1.0", "end")
        self.assertIn("Fertig: 3 Dateien", log)
        self.assertEqual("/mnt/usb0/Alpha", f.fern_var.get(), "der Ordner steht danach normalisiert da")
        self.assertEqual("/mnt/usb0/Alpha", self.app._load_setting(fz.EINST_FERN, ""), "und ist gemerkt")

    def test_ein_vorhandenes_ziel_fragt_dreifach_und_gibt_fortsetzen_weiter(self) -> None:
        f = self._konsole()
        for antwort, fortsetzen in ((True, True), (False, False)):
            with self.subTest(antwort=antwort):
                aufrufe, fragen = self._direkt(vorhanden=True, ja_nein_abbrechen=antwort)
                f._starten()
                self.assertTrue(_ende(f))
                self.assertEqual(1, len(fragen), "nur die Dreifachfrage, keine zweite Bestaetigung")
                self.assertEqual([fortsetzen], [a["fortsetzen"] for a in aufrufe])

    def test_abbrechen_bei_der_dreifachfrage_sendet_nichts(self) -> None:
        f = self._konsole()
        aufrufe, fragen = self._direkt(vorhanden=True, ja_nein_abbrechen=None)
        f._starten()
        self.assertTrue(_ende(f))
        self.assertEqual([], aufrufe)
        self.assertEqual(STRINGS["ps5pkg.console_nothing"]["de"], f.auftrag_var.get())
        self.assertNotIn("Fehlgeschlagen", f.auftrag_var.get())
        self.assertEqual(0.0, float(f.balken_gesamt["value"]))

    def test_ohne_bestaetigung_wird_nichts_gesendet(self) -> None:
        f = self._konsole()
        aufrufe, _fragen = self._direkt(bestaetigt=False)
        f._starten()
        self.assertTrue(_ende(f))
        self.assertEqual([], aufrufe)
        self.assertEqual(STRINGS["ps5pkg.console_nothing"]["de"], f.auftrag_var.get())

    def test_ein_abbruch_nach_einer_datei_ist_kein_fehlschlag(self) -> None:
        f = self._konsole()
        stand = fz.ftp.Fortschritt(dateien=2, dateien_gesamt=9, bytes=1024, bytes_gesamt=9 * 1024, abgebrochen=True)
        self._direkt(ergebnis=stand)
        f._starten()
        self.assertTrue(_ende(f))
        self.assertIn("Abgebrochen nach 2 Dateien", f.auftrag_var.get())
        self.assertIn("/mnt/usb0/Alpha", f.auftrag_var.get())
        self.assertNotIn("Fehlgeschlagen", f.auftrag_var.get())

    def test_ein_fehler_beim_entpacken_auf_die_ps5_wird_gemeldet(self) -> None:
        f = self._konsole()
        self._direkt(fehler=fz.ftp.FtpFehler("10.0.0.5:2121 nicht erreichbar"))
        f._starten()
        self.assertTrue(_ende(f))
        self.assertIn("Fehlgeschlagen", f.auftrag_var.get())
        self.assertIn("[FEHLER] 10.0.0.5:2121 nicht erreichbar", f.protokoll.get("1.0", "end"))

    def test_der_fortschritt_zeigt_datei_und_menge(self) -> None:
        f = self._konsole()
        stand = fz.ftp.Fortschritt(dateien=1, dateien_gesamt=4, bytes=5 * 1024 ** 2, bytes_gesamt=20 * 1024 ** 2,
                                   aktuell="Media/big.dat")
        self._direkt(ergebnis=stand)
        f._starten()
        self.assertTrue(_ende(f))
        self.assertEqual(25.0, f._z["prozent"])
        for stueck in ("Media/big.dat", "2 von 4", "5.0 MB"):
            self.assertIn(stueck, f._z["schritt_text"])


class TexteTests(unittest.TestCase):

    def test_alle_schluessel_gibt_es_in_beiden_sprachen(self) -> None:
        quelle = (PROJEKT / "ps5_validator" / "ui" / "ps5_pkg_fenster.py").read_text(encoding="utf-8")
        # Vorsaetze mit Unterstrich am Ende (``ps5pkg.col_`` ...) werden unten mit ihren Endungen eingesetzt.
        schluessel = {s for s in re.findall(r'"(ps5pkg\.[a-z_0-9]+)"', quelle) if not s.endswith("_")}
        schluessel |= {"ps5pkg.col_" + s for s in ("titel", "title_id", "quelle", "groesse", "version")}
        schluessel |= {"ps5pkg.res_" + s for s in ("output", "title_id", "content", "size", "free")}
        schluessel |= {"ps5pkg.prop_" + s for s in ("title", "source", "size", "title_id", "content_id", "concept", "version",
                                                      "master", "firmware", "sdk", "category", "drm", "badge", "language")}
        schluessel |= {"ps5pkg.log_start_" + s for s in ("pruefen", "extrahieren", "umwandeln", "bauen", "konsole")}
        fehlend = sorted(s for s in schluessel if s not in STRINGS)
        self.assertEqual([], fehlend)
        gleich_erlaubt = {"ps5pkg.window_title", "ps5pkg.src_debug_short", "ps5pkg.lib_title",
                          "ps5pkg.card_cover", "ps5pkg.col_version", "ps5pkg.prop_title_id", "ps5pkg.start_button",
                          "ps5pkg.meta_method", "ps5pkg.btn_update"}
        for s in sorted(schluessel):
            with self.subTest(schluessel=s):
                self.assertTrue(STRINGS[s]["de"].strip() and STRINGS[s]["en"].strip())
                if s not in gleich_erlaubt:
                    self.assertNotEqual(STRINGS[s]["de"], STRINGS[s]["en"])

    def test_die_platzhalter_stimmen_in_beiden_sprachen(self) -> None:
        for s, werte in STRINGS.items():
            if not s.startswith("ps5pkg."):
                continue
            with self.subTest(schluessel=s):
                self.assertEqual(sorted(re.findall(r"\{(\w+)\}", werte["de"])), sorted(re.findall(r"\{(\w+)\}", werte["en"])))


if __name__ == "__main__":
    unittest.main()
