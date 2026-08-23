# -*- coding: utf-8 -*-
"""Tests gegen zusammengequetschte Bedienelemente in den Werkzeugfenstern.

Hintergrund: Wird eine dehnbare Liste (``pack(fill="both", expand=True)``) vor
einer festen Knopfleiste gepackt, beansprucht sie den gesamten Raum. Reicht die
Fensterhöhe nicht, bekommt die Knopfleiste nur den Rest – gemessen 24 statt 51
Pixel, wodurch die Beschriftungen wegfallen und die Knöpfe leer aussehen. Genau
das trat im BACKPORT- und im DOWNLOADS-Fenster auf.

Zweiter Fall: Eine ``StringVar``, die nur lokal gehalten wird, verschwindet mit
dem Ende der Funktion. Eine daran gebundene Combobox zeigt danach nichts mehr an,
obwohl das Widget selbst weiterlebt.

Beide Fälle lassen sich nur am laufenden Tk-Baum messen, nicht am Quelltext.
Ohne verfügbare Anzeige werden die Tests übersprungen.
"""
from pathlib import Path
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HAUPTDATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "PS5ImageConverter_Pro_FINAL_revised.py")

try:
    import tkinter as tk
    _WURZEL = tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover
    TK_DA = False
    _WURZEL = None


def _lade_hauptprogramm():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


def _sammle(widget, art):
    """Alle Nachfahren einer Widget-Klasse."""
    treffer = []
    try:
        kinder = widget.winfo_children()
    except Exception:
        return treffer
    for kind in kinder:
        if kind.__class__.__name__ == art:
            treffer.append(kind)
        treffer += _sammle(kind, art)
    return treffer


def _gequetschte_knoepfe(fenster):
    """Sichtbare Knöpfe, die weniger Platz bekommen als sie anfordern.

    Knöpfe in einer bewusst höhenbegrenzten Leiste (``pack_propagate(False)``,
    etwa die eigene Titelzeile) zählen nicht – dort ist die Höhe Absicht.
    """
    zu_klein = []
    for knopf in _sammle(fenster, "Button"):
        if not knopf.winfo_ismapped():
            continue
        try:
            eltern = knopf.nametowidget(knopf.winfo_parent())
            if not eltern.pack_propagate():
                continue
        except Exception:
            pass
        if (knopf.winfo_height() < knopf.winfo_reqheight()
                or knopf.winfo_width() < knopf.winfo_reqwidth()):
            zu_klein.append(
                f"{knopf.cget('text')!r}: {knopf.winfo_width()}x{knopf.winfo_height()}"
                f" statt {knopf.winfo_reqwidth()}x{knopf.winfo_reqheight()}")
    return zu_klein


def _leere_comboboxen(fenster):
    """Comboboxen, die Werte anbieten, aber keinen anzeigen."""
    leer = []
    for box in _sammle(fenster, "Combobox"):
        try:
            if box.cget("values") and not box.get():
                leer.append(str(box))
        except Exception:
            pass
    return leer


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class FensterLayoutTests(unittest.TestCase):
    """Öffnet die selbst gebauten Werkzeugfenster und misst sie aus."""

    @classmethod
    def setUpClass(cls):
        haupt = _lade_hauptprogramm()
        cls.haupt = haupt
        # Keine echten Dialoge während der Messung.
        for name in ("askopenfilename", "askdirectory", "asksaveasfilename"):
            setattr(haupt.filedialog, name, lambda *a, **k: "")
        for name in ("showinfo", "showwarning", "showerror"):
            setattr(haupt.messagebox, name, lambda *a, **k: None)
        cls.app = haupt.PS5ConverterGUI(_WURZEL)

    def _oeffne(self, aufruf):
        vorher = {str(w) for w in _WURZEL.winfo_children()}
        aufruf()
        _WURZEL.update_idletasks()
        neu = [w for w in _WURZEL.winfo_children()
               if str(w) not in vorher and isinstance(w, tk.Toplevel)
               and w.winfo_exists()]
        self.assertTrue(neu, "Es wurde kein Fenster geöffnet")
        fenster = neu[-1]
        fenster.update_idletasks()
        return fenster

    def _schliesse(self, fenster):
        try:
            fenster.destroy()
        except Exception:
            pass
        self.app._downloads_win = None
        self.app._downloads_tree = None
        _WURZEL.update_idletasks()

    def test_backport_knoepfe_voll_sichtbar(self):
        fenster = self._oeffne(
            lambda: self.app._render_backport_window(os.path.dirname(HAUPTDATEI)))
        try:
            zu_klein = _gequetschte_knoepfe(fenster)
            self.assertEqual(zu_klein, [], f"Gequetscht: {zu_klein}")
            knoepfe = [b for b in _sammle(fenster, "Button") if b.winfo_ismapped()]
            self.assertEqual(len(knoepfe), 3, "Erwartet: Starten, Nur prüfen, Schließen")
            for knopf in knoepfe:
                self.assertTrue(str(knopf.cget("text")).strip(),
                                "Knopf ohne Beschriftung")
        finally:
            self._schliesse(fenster)

    def test_backport_auswahlfelder_zeigen_einen_wert(self):
        """Beide Klapplisten im Backport-Fenster: Firmware und Bibliotheksordner.

        Der Bibliotheksordner (fakelib/fakelib2) kam dazu, weil ShadowMount+ nur
        einen von beiden einhaengt und fakelib2 bevorzugt. Geprueft wird, dass
        keine der Listen leer bleibt - das war der Fehler, den eine nur lokal
        gehaltene StringVar ausloeste.
        """
        fenster = self._oeffne(
            lambda: self.app._render_backport_window(os.path.dirname(HAUPTDATEI)))
        try:
            self.assertEqual(_leere_comboboxen(fenster), [],
                             "Eine Auswahl ist leer")
            boxen = _sammle(fenster, "Combobox")
            self.assertEqual(len(boxen), 2, "Erwartet: Firmware und Bibliotheksordner")
            for box in boxen:
                self.assertGreaterEqual(box.current(), 0, "Kein Eintrag ausgewählt")
                self.assertTrue(str(box.get()).strip(), "Auswahl ohne Text")

            from ps5_validator.utils import ps5_backport as bp
            werte = [str(b.get()) for b in boxen]
            # Voreinstellung ist die Firmware mit Ersatzbibliotheken.
            self.assertTrue(any(f"{bp.FIRMWARE_STANDARD}.00" in w for w in werte),
                            f"Firmware-Vorgabe fehlt: {werte}")
            # Und einer der beiden bekannten Ordnernamen.
            self.assertTrue(any(w.strip().lower() in bp.FAKELIB_ORDNERNAMEN
                                for w in werte),
                            f"Bibliotheksordner fehlt: {werte}")
        finally:
            self._schliesse(fenster)

    def test_downloads_knoepfe_voll_sichtbar(self):
        fenster = self._oeffne(self.app._show_downloads_manager)
        try:
            zu_klein = _gequetschte_knoepfe(fenster)
            self.assertEqual(zu_klein, [], f"Gequetscht: {zu_klein}")
        finally:
            self._schliesse(fenster)

    def test_remote_ini_editor_knoepfe_voll_sichtbar(self):
        # ShadowMount+ und MicroMount teilen sich diesen Editor.
        fenster = self._oeffne(self.app._show_shadowmount_editor)
        try:
            zu_klein = _gequetschte_knoepfe(fenster)
            self.assertEqual(zu_klein, [], f"Gequetscht: {zu_klein}")
        finally:
            self._schliesse(fenster)

    def test_js_loader_knoepfe_voll_sichtbar(self):
        fenster = self._oeffne(self.app._show_js_loader)
        try:
            zu_klein = _gequetschte_knoepfe(fenster)
            self.assertEqual(zu_klein, [], f"Gequetscht: {zu_klein}")
        finally:
            self._schliesse(fenster)

    def test_pkg_merger_knoepfe_ueberhaupt_sichtbar(self):
        """Hier war die Knopfleiste komplett aus dem Fenster gedrängt.

        Weder "Zusammenführen" noch "Schließen" waren zu sehen – gemessen null
        sichtbare Knöpfe. Ein reiner Größenvergleich hätte das nicht gefunden,
        weil unsichtbare Knöpfe gar nicht erst mitgezählt werden.
        """
        import tempfile
        import shutil
        ordner = tempfile.mkdtemp(prefix="merger_test_")
        try:
            for teil in range(3):
                ziel = os.path.join(ordner, f"Spiel (01.003.000)_{teil}.pkg")
                with io.open(ziel, "wb") as fh:
                    fh.write(b"\x7fCNT" + bytes(1024))
            self.haupt.filedialog.askdirectory = lambda *a, **k: ordner
            fenster = self._oeffne(self.app._show_pkg_merger_dialog)
            try:
                sichtbar = [b for b in _sammle(fenster, "Button") if b.winfo_ismapped()]
                self.assertEqual(len(sichtbar), 2,
                                 "Zusammenführen und Schließen müssen sichtbar sein")
                self.assertEqual(_gequetschte_knoepfe(fenster), [])
            finally:
                self._schliesse(fenster)
        finally:
            shutil.rmtree(ordner, ignore_errors=True)


class QuelltextTests(unittest.TestCase):
    """Sichert die Packreihenfolge auch dort ab, wo sie leicht verrutscht."""

    @classmethod
    def setUpClass(cls):
        with io.open(HAUPTDATEI, encoding="utf-8") as fh:
            cls.quelle = fh.read()

    def test_backport_packt_knopfreihe_vor_der_liste(self):
        knopf = self.quelle.index('knopfreihe.pack(side="bottom", fill="x")')
        liste = self.quelle.index('rahmen.pack(fill="both", expand=True, padx=16, pady=(8, 6))')
        self.assertLess(knopf, liste,
                        "Die Knopfreihe muss vor der dehnbaren Liste gepackt werden")

    def test_pkg_merger_packt_knopfreihe_vor_dem_koerper(self):
        anfang = self.quelle.index("def _render_pkg_merger_window(")
        ende = self.quelle.index("def _show_param_manifest_editor(", anfang)
        block = self.quelle[anfang:ende]
        knopf = block.index('btn_row.pack(side="bottom", fill="x")')
        koerper = block.index('body.pack(fill="both", expand=True)')
        self.assertLess(knopf, koerper)

    def test_remote_ini_packt_knopfreihe_vor_dem_koerper(self):
        # Nur innerhalb dieser Methode suchen: 'body.pack(...)' kommt im
        # Programm mehrfach vor, in anderen Fenstern völlig zu Recht.
        anfang = self.quelle.index("def _show_remote_ini_editor(")
        ende = self.quelle.index("def _show_js_loader(", anfang)
        block = self.quelle[anfang:ende]
        knopf = block.index('btn_row.pack(side="bottom", fill="x")')
        koerper = block.index('body.pack(fill="both", expand=True)')
        self.assertLess(knopf, koerper,
                        "Die Knopfreihe muss vor dem dehnbaren Körper gepackt werden")

    def test_backport_firmware_box_ohne_lokale_stringvar(self):
        # Eine nur lokal gehaltene StringVar würde eingesammelt.
        stelle = self.quelle.index('fw_box = ttk.Combobox(')
        block = self.quelle[stelle:stelle + 200]
        self.assertNotIn("textvariable", block)

    def test_ziel_firmware_faellt_sauber_zurueck(self):
        # current() liefert -1, wenn nichts gewählt ist; ein direkter Zugriff
        # nähme dann stillschweigend den letzten Eintrag.
        stelle = self.quelle.index("def _ziel_firmware()")
        block = self.quelle[stelle:stelle + 700]
        self.assertIn("0 <= stelle < len(", block)
        self.assertIn("return ps5_backport.FIRMWARE_STANDARD", block)


class TabellenkopfTests(unittest.TestCase):
    """Kopfzeile und Daten einer Spalte muessen denselben Anker haben.

    ``tree.column(..., anchor="w")`` stellt nur die Daten links; die Kopfzeile
    zentriert Tk weiter. Bei schmalen Spalten faellt das kaum auf, bei einem
    maximierten Fenster stehen Ueberschrift und Werte weit auseinander - im
    param.json-Editor stand "Schluessel" auf halber Spaltenbreite, waehrend die
    Werte am linken Rand begannen.
    """

    def setUp(self):
        import PS5ImageConverter_Pro_FINAL_revised as APP

        with io.open(APP.__file__, encoding="utf-8") as datei:
            self.quelle = datei.read()

    def _heading_aufrufe(self):
        """Alle .heading(...)-Aufrufe samt ihrer Argumente, ueber Zeilen hinweg."""
        import re

        treffer = []
        for anfang in (m.start() for m in re.finditer(r"\.heading\(", self.quelle)):
            tiefe, i = 0, anfang + len(".heading")
            while i < len(self.quelle):
                if self.quelle[i] == "(":
                    tiefe += 1
                elif self.quelle[i] == ")":
                    tiefe -= 1
                    if tiefe == 0:
                        treffer.append(self.quelle[anfang:i + 1])
                        break
                i += 1
        return treffer

    def test_jede_kopfzeile_hat_einen_anker(self):
        ohne = [a for a in self._heading_aufrufe() if "anchor" not in a]
        self.assertEqual(ohne, [], f"{len(ohne)} Kopfzeile(n) ohne anchor")

    def test_es_gibt_ueberhaupt_kopfzeilen(self):
        # Schutz vor einem Test, der nur deshalb gruen ist, weil er nichts findet.
        self.assertGreaterEqual(len(self._heading_aufrufe()), 10)


@unittest.skipUnless(_WURZEL is not None, "keine Anzeige verfuegbar")
class FenstergroesseTests(unittest.TestCase):
    """Jedes Werkzeugfenster muss seinen eigenen Inhalt fassen.

    Die Masse sind von Hand eingetragen. Waechst der Inhalt, bleibt die
    Zahl stehen und die unterste Knopfreihe rutscht aus dem Fenster - der
    Nutzer muss es erst groesser ziehen, um an "Schliessen" zu kommen.

    Am 19.08.2026 an einer Bildschirmaufnahme nachgemessen: acht von zehn
    pruefbaren Fenstern waren zu klein. Dem AMPR-Index fehlten 265 Pixel
    Hoehe, dem Diagnosebericht 137, dem JS Loader 101.
    """

    @classmethod
    def setUpClass(cls):
        haupt = _lade_hauptprogramm()
        cls.haupt = haupt
        for name in ("askopenfilename", "askdirectory", "asksaveasfilename"):
            setattr(haupt.filedialog, name, lambda *a, **k: "")
        for name in ("showinfo", "showwarning", "showerror"):
            setattr(haupt.messagebox, name, lambda *a, **k: None)
        haupt.messagebox.askyesno = lambda *a, **k: False
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        _WURZEL.update_idletasks()

    def _messen(self, aufruf):
        """Oeffnet ein Fenster und liefert (ist_breite, ist_hoehe, noetig...)."""
        import time

        vorher = {str(w) for w in _WURZEL.winfo_children()}
        aufruf()
        # Das Fenster waechst verzoegert auf seinen Inhalt (80/400 ms).
        for _ in range(12):
            _WURZEL.update()
            time.sleep(0.05)
        neu = [w for w in _WURZEL.winfo_children()
               if str(w) not in vorher and isinstance(w, tk.Toplevel)
               and w.winfo_exists()]
        self.assertTrue(neu, "Es wurde kein Fenster geoeffnet")
        fenster = neu[-1]
        fenster.update_idletasks()
        masse = fenster.geometry().split("+")[0].split("x")
        ist = (int(masse[0]), int(masse[1]))
        noetig = (fenster.winfo_reqwidth(), fenster.winfo_reqheight())
        try:
            fenster.destroy()
        except Exception:
            pass
        for attribut in ("_downloads_win", "_downloads_tree", "_klog_win"):
            if hasattr(self.app, attribut):
                setattr(self.app, attribut, None)
        _WURZEL.update_idletasks()
        return ist, noetig

    def _pruefen(self, name, aufruf):
        ist, noetig = self._messen(aufruf)
        self.assertGreaterEqual(
            ist[1], noetig[1] - 2,
            "%s ist %d px zu niedrig - die unterste Knopfreihe liegt "
            "ausserhalb des Fensters." % (name, noetig[1] - ist[1]))
        self.assertGreaterEqual(
            ist[0], noetig[0] - 2,
            "%s ist %d px zu schmal." % (name, noetig[0] - ist[0]))

    def test_autoloader_fasst_seinen_inhalt(self):
        # Ohne Adresse: Sonst holt das Fenster beim Oeffnen von der echten
        # Konsole - ein Test darf nicht ins Netz greifen.
        alt = self.app._ps5_ip
        self.app._ps5_ip = lambda default="": ""
        try:
            self._pruefen("ps5_autoloader", self.app._show_autoloader)
        finally:
            self.app._ps5_ip = alt

    def test_ampr_index_fasst_seinen_inhalt(self):
        self._pruefen("AMPR-Index", self.app._show_ampr_index_builder)

    def test_diagnosebericht_fasst_seinen_inhalt(self):
        self._pruefen("Diagnosebericht", self.app._show_diagnostic_report)

    def test_js_loader_fasst_seinen_inhalt(self):
        self._pruefen("JS Loader", self.app._show_js_loader)

    def test_klog_fasst_seinen_inhalt(self):
        self._pruefen("KLOG", self.app._show_klog_window)

    def test_debug_pkg_fasst_seinen_inhalt(self):
        self._pruefen("Debug-PKG", self.app._show_debug_pkg_builder)

    def test_downloads_fasst_seinen_inhalt(self):
        self._pruefen("Downloads", self.app._show_downloads_manager)

    def test_design_fasst_seinen_inhalt(self):
        self._pruefen("Design", self.app._show_theme_dialog)

    def test_backport_fasst_seinen_inhalt(self):
        self._pruefen("Backport", lambda: self.app._render_backport_window(
            os.path.dirname(HAUPTDATEI)))


    def test_ps4_pkg_knoepfe_bleiben_erreichbar(self):
        """Die Knopfreihe muss auch auf einem kurzen Bildschirm sichtbar sein.

        Der Ablageort-Kasten aus v1.8.74 macht das Fenster hoeher als der
        Bildschirm hier hergibt (854 noetig, 784 moeglich). Entscheidend ist
        dann nicht, dass alles zu sehen ist, sondern dass EINLESEN, ABBILD
        ERSTELLEN, ABBRECHEN und SCHLIESSEN erreichbar bleiben. Dafuer wird
        die Knopfreihe mit ``before=`` vor dem dehnbaren Koerper gepackt.
        """
        import time

        if not self.haupt._ps4ffpsc_wurzel():
            self.skipTest("Eingebettetes PS4-Werkzeug nicht vorhanden")
        vorher = {str(w) for w in _WURZEL.winfo_children()}
        self.app._show_ps4_pkg_converter()
        ende = time.perf_counter() + 3.0
        while time.perf_counter() < ende:
            _WURZEL.update()
            time.sleep(0.01)
        neu = [w for w in _WURZEL.winfo_children()
               if str(w) not in vorher and isinstance(w, tk.Toplevel)
               and w.winfo_exists()]
        self.assertTrue(neu, "Es wurde kein Fenster geoeffnet")
        fenster = neu[-1]
        fenster.update_idletasks()
        knoepfe = [b for b in _sammle(fenster, "Button")
                   if b.winfo_ismapped()]
        masse = []
        for knopf in knoepfe:
            unten = (knopf.winfo_rooty() - fenster.winfo_rooty()
                     + knopf.winfo_height())
            masse.append((str(knopf.cget("text"))[:20], knopf.winfo_height(),
                          knopf.winfo_reqheight(), unten,
                          fenster.winfo_height()))
        try:
            fenster.destroy()
        except Exception:
            pass
        _WURZEL.update_idletasks()

        self.assertTrue(masse, "Keine Knoepfe gefunden")
        for text, hoehe, noetig, unten, fensterhoehe in masse:
            with self.subTest(knopf=text):
                self.assertGreaterEqual(
                    hoehe, noetig - 2,
                    "Knopf %r ist auf %d statt %d px zusammengequetscht."
                    % (text, hoehe, noetig))
                self.assertLessEqual(
                    unten, fensterhoehe,
                    "Knopf %r endet bei %d, das Fenster ist nur %d px hoch - "
                    "er liegt ausserhalb." % (text, unten, fensterhoehe))

    def test_der_wachstumsschritt_haengt_am_gemeinsamen_bau(self):
        # Sechzehn Fenster entstehen ueber _build_modern_toplevel. Faellt
        # der Aufruf dort weg, sind sie alle wieder betroffen.
        quelle = io.open(HAUPTDATEI, encoding="utf-8").read()
        anfang = quelle.index("    def _build_modern_toplevel(")
        block = quelle[anfang:anfang + 3000]
        self.assertIn("_fenster_auf_inhalt_wachsen(", block)
        self.assertNotIn("win.after_idle(lambda: self._fenster_auf_inhalt_wachsen",
                         block,
                         "after_idle laeuft zu frueh - mehrere Erbauer rufen "
                         "selbst update_idletasks().")


class DesignwechselFarbenTests(unittest.TestCase):
    """Die Schriftfarben muessen einen Design-Wechsel im Betrieb ueberstehen.

    Zwei Fehler dieser Art in zwei Versionen:

    * v1.8.62 hellte "PRUEFUNG NACH DEM PACKEN" auf, trug es aber nicht in die
      Rollentabelle von _apply_caption_colors() ein - beim ersten Wechsel waere
      die Aenderung wieder verschwunden.
    * v1.8.63 trug das Kaestchen zum Herunterfahren ein, doch _apply_theme()
      setzte danach fg_secondary noch einmal fest darueber. Beim Start war es
      hell, nach dem ersten Wechsel wieder grau.

    Beides war am Quelltext nicht zu sehen. Deshalb wird hier die Farbe am
    lebenden Widget gemessen, nach jedem Wechsel.
    """

    BESCHRIFTUNGEN = (
        "src_title", "format_title", "perf_title",
        "format_info_label", "dest_title", "temp_title", "shutdown_check",
        "status_label", "telemetry_label",
    )

    @classmethod
    def setUpClass(cls):
        haupt = _lade_hauptprogramm()
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        _WURZEL.update_idletasks()

    @classmethod
    def tearDownClass(cls):
        # Nicht im hellen Design stehen lassen - der naechste Test in
        # derselben Wurzel saehe sonst fremde Farben.
        try:
            cls.app._apply_theme("dunkel")
            _WURZEL.update_idletasks()
        except Exception:
            pass

    def _messen(self, design):
        self.app._apply_theme(design)
        _WURZEL.update_idletasks()
        soll = self.app._COLORS["fg_primary"]
        abweichend = []
        for name in self.BESCHRIFTUNGEN:
            widget = getattr(self.app, name, None)
            self.assertIsNotNone(widget, "%s fehlt" % name)
            ist = str(widget.cget("foreground"))
            if ist.lower() != soll.lower():
                abweichend.append((name, ist))
        return soll, abweichend

    def test_alle_designs_und_zurueck(self):
        # Hin und zurueck, weil ein Fehler nur in eine Richtung auftreten kann.
        for design in ("dunkel", "mittel", "hell", "dunkel", "hell", "mittel", "dunkel"):
            soll, abweichend = self._messen(design)
            self.assertEqual(
                abweichend, [],
                "Nach dem Wechsel auf '%s' (fg_primary=%s) tragen diese "
                "Beschriftungen eine fremde Farbe: %s" % (design, soll, abweichend))

    def test_kein_zweiter_schreiber_fuer_das_kaestchen(self):
        # Der konkrete Rueckfall: _apply_theme() setzte die Schriftfarbe des
        # Kaestchens noch einmal fest, nachdem die Rollentabelle sie gesetzt
        # hatte. Zwei Schreiber auf derselben Eigenschaft - der zweite gewinnt.
        with io.open(HAUPTDATEI, encoding="utf-8") as fh:
            quelle = fh.read()
        self.assertNotIn('self.shutdown_check.configure(' + '\r\n'
                         + '                    bg=c["bg_card"], fg=c["fg_secondary"]',
                         quelle,
                         "_apply_theme setzt die Schriftfarbe wieder fest.")


class RueckrufNachSchliessenTests(unittest.TestCase):
    """Ein Arbeitsfaden darf nicht abstuerzen, wenn sein Fenster schon zu ist.

    Gefunden am 20.08.2026 beim Durchgang durch alle Werkzeugfenster: Das
    Bibliotheksfenster wurde geschlossen, waehrend sein Suchlauf noch lief.
    Der Faden rief ``win.after(0, _finish)`` und starb an
    "RuntimeError: main thread is not in main loop" - im Programm unsichtbar,
    im Fehlerbericht ein Absturz, der keiner ist.
    """

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()
        cls.app = cls.haupt.PS5ConverterGUI.__new__(cls.haupt.PS5ConverterGUI)

    def test_offenes_fenster_nimmt_den_rueckruf(self):
        fenster = tk.Toplevel(_WURZEL)
        _WURZEL.update_idletasks()
        try:
            self.assertTrue(self.app._spaeter_im_fenster(fenster, lambda: None))
        finally:
            fenster.destroy()

    def test_geschlossenes_fenster_ergibt_false_statt_ausnahme(self):
        fenster = tk.Toplevel(_WURZEL)
        _WURZEL.update_idletasks()
        fenster.destroy()
        _WURZEL.update_idletasks()
        self.assertFalse(self.app._spaeter_im_fenster(fenster, lambda: None))

    def test_ohne_fenster(self):
        self.assertFalse(self.app._spaeter_im_fenster(None, lambda: None))

    def test_aus_einem_arbeitsfaden(self):
        # Der eigentliche Fall: Tk wirft nur, wenn der Aufruf aus einem
        # anderen Faden kommt. Ein Test im Hauptfaden wuerde ihn verfehlen.
        import threading
        fenster = tk.Toplevel(_WURZEL)
        _WURZEL.update_idletasks()
        fenster.destroy()
        _WURZEL.update_idletasks()

        ergebnis = []

        def faden():
            try:
                ergebnis.append(self.app._spaeter_im_fenster(fenster, lambda: None))
            except Exception as exc:
                ergebnis.append("AUSNAHME: %s" % exc)

        t = threading.Thread(target=faden)
        t.start()
        t.join(timeout=5)
        self.assertEqual(ergebnis, [False], ergebnis)

    def test_die_beiden_bekannten_stellen_nutzen_den_helfer(self):
        with io.open(HAUPTDATEI, encoding="utf-8") as fh:
            quelle = fh.read()
        self.assertIn("self._spaeter_im_fenster(win, _finish)", quelle,
                      "Der Suchlauf des Bibliotheksfensters ruft wieder direkt after().")
        self.assertNotIn("win.after(0, _finish)", quelle)
class FensterbindungTests(unittest.TestCase):
    """Werkzeugfenster duerfen nicht hinter das Hauptfenster rutschen.

    Gemeldet am 22.08.2026: Oeffnet man ein Werkzeugfenster und drueckt
    danach einen anderen Knopf, verschwindet das erste. Der Grund ist
    nicht das Oeffnen des zweiten Fensters, sondern der Klick aufs
    Hauptfenster, der noetig ist, um an den Knopf zu kommen: Er holt das
    Hauptfenster nach vorn, und besitzerlose Fenster fallen dahinter.

    An der Z-Reihenfolge von Windows nachgemessen - drei offene Fenster,
    nach einem Klick lagen zwei darunter. Mit ``transient()`` bleibt
    keines mehr zurueck.
    """

    @classmethod
    def setUpClass(cls):
        cls.quelle = (Path(HAUPTDATEI).read_text(encoding="utf-8")
                      if isinstance(HAUPTDATEI, str)
                      else HAUPTDATEI.read_text(encoding="utf-8"))

    def _methode(self, name: str) -> str:
        # Nicht "(self" mitsuchen: Mehrere dieser Methoden haben eine
        # mehrzeilige Signatur, "self" steht dort erst in der
        # naechsten Zeile.
        anfang = self.quelle.index("    def %s(" % name)
        weiter = self.quelle.index(chr(10) + "    def ", anfang + 10)
        return self.quelle[anfang:weiter]

    def test_der_gemeinsame_erbauer_bindet(self) -> None:
        self.assertIn("_fenster_an_hauptfenster_binden",
                      self._methode("_build_modern_toplevel"))

    def test_der_helfer_ordnet_zu(self) -> None:
        rumpf = self._methode("_fenster_an_hauptfenster_binden")
        self.assertIn("transient(", rumpf,
                      "Ohne transient faellt das Fenster wieder zurueck.")

    def test_der_taskleisteneintrag_wird_zurueckgeholt(self) -> None:
        """transient kostet ihn sonst - der war hier ausdruecklich gewollt."""
        rumpf = self._methode("_fenster_an_hauptfenster_binden")
        self.assertIn("_taskleisteneintrag_zurueckholen", rumpf)
        stil = self._methode("_taskleisteneintrag_zurueckholen")
        self.assertIn("_WS_EX_APPWINDOW", stil)
        self.assertIn("IST_WINDOWS", stil,
                      "Der Stil gilt nur unter Windows.")

    def test_der_stil_kommt_ohne_flackern_aus(self) -> None:
        """Aus- und Einblenden waere bei jedem Oeffnen sichtbar gewesen.

        Am 22.08.2026 gemessen: Der Stil allein genuegt, die Taskleiste
        nimmt ihn ohne ShowWindow an.
        """
        stil = self._methode("_taskleisteneintrag_zurueckholen")
        self.assertNotIn("ShowWindow", stil)

    def test_auch_die_fenster_neben_dem_erbauer_sind_gebunden(self) -> None:
        """Drei entstehen direkt - darunter CREDITS aus der Werkzeugleiste."""
        for methode in ("_show_credits", "_show_ampr_ftp_picker"):
            with self.subTest(methode=methode):
                self.assertIn("_fenster_an_hauptfenster_binden",
                              self._methode(methode))

    def test_rahmenlose_einblendungen_bleiben_unangetastet(self) -> None:
        """Sie haben kein eigenes Fensterverhalten - transient waere sinnlos."""
        for methode in ("_build_info_popup", "_show_resources", "_show_splash"):
            with self.subTest(methode=methode):
                rumpf = self._methode(methode)
                self.assertIn("overrideredirect", rumpf)
                self.assertNotIn("_fenster_an_hauptfenster_binden", rumpf)


class UmschalterTests(unittest.TestCase):
    """Derselbe Knopf schliesst das Fenster wieder.

    Gewuenscht am 23.08.2026: Der erste Druck oeffnet, der zweite
    schliesst - statt ein zweites Fenster darueberzulegen.

    Geprueft wird an einem eigens angehaengten Probe-Fenster, nicht an
    einem echten Werkzeug: Der Umschalter soll fuer jedes Fenster gelten,
    und ein Probe-Fenster haelt den Test von den Eigenheiten einzelner
    Werkzeuge frei.
    """

    @classmethod
    def setUpClass(cls):
        haupt = _lade_hauptprogramm()
        cls.haupt = haupt
        for name in ("askopenfilename", "askdirectory", "asksaveasfilename"):
            setattr(haupt.filedialog, name, lambda *a, **k: "")
        for name in ("showinfo", "showwarning", "showerror"):
            setattr(haupt.messagebox, name, lambda *a, **k: None)
        cls.app = haupt.PS5ConverterGUI(_WURZEL)

    def setUp(self):
        self.app._werkzeugfenster.clear()
        self.geoeffnet = []

    def tearDown(self):
        for fenster in self.geoeffnet:
            try:
                if fenster.winfo_exists():
                    fenster.destroy()
            except tk.TclError:
                pass
        self.app._werkzeugfenster.clear()

    def _probe(self, name="_probe_fenster", schliessbar=True):
        """Haengt eine Methode an, die ein schlichtes Fenster oeffnet."""
        app = self.app
        merker = self.geoeffnet

        def oeffnen():
            fenster = tk.Toplevel(_WURZEL)
            merker.append(fenster)
            app._fenster_an_hauptfenster_binden(fenster)
            if not schliessbar:
                # Wie ein Fenster, das waehrend eines Laufs nicht zugeht.
                fenster.protocol("WM_DELETE_WINDOW", lambda: None)

        setattr(app, name, oeffnen)
        return name

    def test_erster_druck_oeffnet(self):
        name = self._probe()
        self.app._werkzeugfenster_umschalten(name)
        _WURZEL.update_idletasks()
        fenster = self.app._werkzeugfenster.get(name)
        self.assertIsNotNone(fenster, "Es wurde kein Fenster gemerkt")
        self.assertTrue(fenster.winfo_exists())

    def test_zweiter_druck_schliesst(self):
        name = self._probe()
        self.app._werkzeugfenster_umschalten(name)
        _WURZEL.update_idletasks()
        fenster = self.app._werkzeugfenster[name]

        self.app._werkzeugfenster_umschalten(name)
        _WURZEL.update_idletasks()
        self.assertFalse(fenster.winfo_exists(),
                         "Der zweite Druck hat nicht geschlossen")
        self.assertNotIn(name, self.app._werkzeugfenster)

    def test_dritter_druck_oeffnet_wieder(self):
        name = self._probe()
        for _ in range(3):
            self.app._werkzeugfenster_umschalten(name)
            _WURZEL.update_idletasks()
        self.assertTrue(self.app._werkzeugfenster[name].winfo_exists())

    def test_von_hand_geschlossen_zaehlt_auch(self):
        """Wer ueber das X schliesst, bekommt beim naechsten Druck wieder eines.

        Ohne das Vergessen bliebe ein toter Eintrag stehen, und der naechste
        Druck haette nichts zu schliessen und nichts zu oeffnen.
        """
        name = self._probe()
        self.app._werkzeugfenster_umschalten(name)
        _WURZEL.update_idletasks()
        self.app._werkzeugfenster[name].destroy()
        _WURZEL.update_idletasks()
        self.assertNotIn(name, self.app._werkzeugfenster,
                         "Der Eintrag haette verschwinden muessen")

        self.app._werkzeugfenster_umschalten(name)
        _WURZEL.update_idletasks()
        self.assertTrue(self.app._werkzeugfenster[name].winfo_exists())

    def test_ein_fenster_darf_sich_weigern(self):
        """Laeuft gerade etwas, bleibt das Fenster stehen.

        Der Umschalter geht ueber ``WM_DELETE_WINDOW``, damit die
        Ruecksprachen und Abbruchwaechter der Fenster gelten. Ein hartes
        ``destroy()`` koennte einen Lauf mitten im Schreiben abschneiden.
        """
        name = self._probe(name="_probe_stur", schliessbar=False)
        self.app._werkzeugfenster_umschalten(name)
        _WURZEL.update_idletasks()
        fenster = self.app._werkzeugfenster[name]

        self.app._werkzeugfenster_umschalten(name)
        _WURZEL.update_idletasks()
        self.assertTrue(fenster.winfo_exists(),
                        "Das Fenster wurde gegen seinen Willen geschlossen")
        self.assertIs(self.app._werkzeugfenster.get(name), fenster,
                      "Es muss gemerkt bleiben, sonst gibt es ein zweites")


class UmschalterVerdrahtungTests(unittest.TestCase):
    """Die Knoepfe muessen ueber den Umschalter gehen, nicht daran vorbei."""

    @classmethod
    def setUpClass(cls):
        cls.quelle = (Path(HAUPTDATEI).read_text(encoding="utf-8")
                      if isinstance(HAUPTDATEI, str)
                      else HAUPTDATEI.read_text(encoding="utf-8"))

    def test_fensterknoepfe_gehen_ueber_den_umschalter(self):
        for methode in ("_show_credits", "_show_js_loader",
                        "_show_shadowmount_editor", "_show_diagnostic_report",
                        "_show_ampr_alte_methode", "_show_ampr_neue_methode",
                        "_show_library_window", "_show_klog_window_geprueft"):
            with self.subTest(methode=methode):
                self.assertIn('self._werkzeugknopf("%s")' % methode,
                              self.quelle)
                self.assertNotIn("command=self.%s," % methode, self.quelle)

    def test_die_menues_ebenfalls(self):
        """Auch das Untermenue und die eingefaltete Liste."""
        self.assertNotIn("command=getattr(self,", self.quelle)
        self.assertIn("self._werkzeugknopf(_befehl_name)", self.quelle)
        self.assertIn("self._werkzeugknopf(befehl)", self.quelle)

    def test_fremdprogramme_bleiben_aussen_vor(self):
        """FileZilla und das Handbuch oeffnen kein eigenes Fenster."""
        for methode in ("_launch_filezilla", "_open_benutzerhandbuch"):
            with self.subTest(methode=methode):
                self.assertIn("command=self.%s," % methode, self.quelle)
                self.assertNotIn('self._werkzeugknopf("%s")' % methode,
                                 self.quelle)






if __name__ == "__main__":
    unittest.main(verbosity=2)
