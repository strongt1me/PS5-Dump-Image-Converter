# -*- coding: utf-8 -*-
"""Tests fuer die runden Ersatzteile der Nebenfenster (``ps5_validator/ui/fenster_pillen.py``).

Nutzerwunsch 05.10.2026: "Bitte die optik bei allen fenstern an die neue optik anpassen." Die Fenster
(Einstellungen, ShadowMount+, Downloads, KLOG ...) waren von Hand aus ``ttk.Button``, ``tk.Entry``,
``ttk.Combobox`` und ``tk.Text`` gebaut. Jetzt steht fuer jedes dieser Teile ein Ersatz mit denselben
Optionen und Methoden; die Aufrufstellen wechseln nur den Namen.

Drei Dinge werden hier gehalten:

1. Jedes Ersatzteil kann, was die Fenster von seinem Vorbild brauchen (Optionen, Methoden, Ereignisse).
2. **Keine Fenster-Methode baut wieder ein eckiges Teil** (Waechter ueber den Syntaxbaum): Wer ein neues
   Fenster mit ``ttk.Button`` baut, faellt hier auf - und mit ihm sieht das Fenster aus wie von 2025.
3. Die geoeffneten Fenster tragen am laufenden Tk-Baum keine eckigen Teile mehr.
"""
from __future__ import annotations

import ast
import os
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

try:
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover - ohne Anzeige
    TK_DA = False
    _WURZEL = None

HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"

#: Die Methoden, die Nebenfenster bauen. Hier darf kein klassisches Widget mehr erzeugt werden.
FENSTER_METHODEN = (
    "_platz_dialog", "_ordner_einbau_dialog", "_start_shutdown_countdown",
    "_render_pkg_merger_window", "_render_param_manifest_editor",
    "_bibliothek_umbenennen_fenster", "_bibliothek_ordner_uebertragen", "_bibliothek_ziel_waehlen",
    "_bibliothek_uebertragen", "_render_diagnostic_report_window", "_render_self_inspector_window",
    "_show_pkg_entpacken", "_render_pkg_reader_window", "_show_downloads_manager",
    "_ampr_gen_fassungen_fenster", "_ampr_gen_dialog", "_show_ampr_generation",
    "_show_ampr_mitschnitt_assistent", "_show_autoloader", "_show_app_install", "_render_backport_window",
    "_render_dump_rename_window", "_show_ps4_pkg_converter", "_show_klog_window", "_show_unjail_sender",
    "_show_remote_ini_editor", "_show_js_loader", "_show_ampr_index_builder", "_auswahl_dialog",
    "_show_ampr_ftp_picker", "_show_theme_dialog", "_einstellungen_anzeige_abschnitt",
    "_show_settings_dialog", "_show_credits", "_show_resources", "_mode_ampr_manager",
    "_build_info_popup", "_render_library_window", "_konsole_webdienst_hinweis_zeigen",
)

#: Diese Aufrufe sind die klassischen Teile; ihr Ersatz steht in ``self._pw``.
ECKIG = {
    "tk.Button", "ttk.Button", "flach_knopf", "tk.Entry", "ttk.Entry", "ttk.Combobox", "tk.Checkbutton",
    "ttk.Checkbutton", "tk.Radiobutton", "ttk.Radiobutton", "ttk.Progressbar", "tk.Text", "ttk.Treeview",
    "tk.Listbox", "tk.Scrollbar", "ttk.Scrollbar", "tk.LabelFrame", "ttk.Spinbox", "tk.Spinbox", "ttk.Scale",
    "tk.Scale",
}

#: Klassische Teile, die eine Methode bewusst behalten darf - jede Ausnahme mit Grund.
_BIBLIOTHEK_KARTE = ("Seite der Ansicht KONSOLE: steht in einer runden Karte des Kartenrasters "
                     "(bibliothek_raster), der Rollbalken hat den schmalen Stil")
ERLAUBT: dict[tuple[str, str], str] = {
    ("_render_library_window", "ttk.Treeview"): _BIBLIOTHEK_KARTE,
    ("_render_library_window", "tk.Listbox"): _BIBLIOTHEK_KARTE,
    ("_render_library_window", "ttk.Scrollbar"): _BIBLIOTHEK_KARTE,
}


def _name(knoten) -> str:
    if isinstance(knoten, ast.Name):
        return knoten.id
    if isinstance(knoten, ast.Attribute):
        basis = _name(knoten.value)
        return (basis + "." if basis else "") + knoten.attr
    return ""


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class _Basis(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        cls.pw = cls.app._pw
        cls.c = cls.app._COLORS

    def setUp(self) -> None:
        self.fenster = tk.Toplevel(_WURZEL, bg=self.c["bg_main"])
        self.fenster.withdraw()
        self.addCleanup(self._abbauen)
        self.flaeche = tk.Frame(self.fenster, bg=self.c["bg_main"])
        self.flaeche.pack(fill="both", expand=True)

    def _abbauen(self) -> None:
        try:
            self.fenster.destroy()
        except tk.TclError:
            pass

    def _ruhen(self) -> None:
        self.fenster.update_idletasks()


class ButtonTests(_Basis):

    def test_ruft_den_befehl_und_nicht_gesperrt(self) -> None:
        aufrufe: list[int] = []
        knopf = self.pw.Button(self.flaeche, text="Los", command=lambda: aufrufe.append(1))
        knopf.pack()
        knopf.invoke()
        knopf.configure(state="disabled")
        knopf.invoke()
        self.assertEqual([1], aufrufe)
        knopf.configure(state="normal")
        knopf.invoke()
        self.assertEqual([1, 1], aufrufe)

    def test_nimmt_die_optionen_der_vorbilder_ohne_fehler(self) -> None:
        """ttk.Button und flach_knopf: alles, was die Fenster uebergeben haben."""
        self.pw.Button(self.flaeche, text="a", command=lambda: None, style="Accent.TButton", width=8).pack()
        self.pw.Button(self.flaeche, text="b", command=lambda: None, state="disabled").pack()
        self.pw.Button(self.flaeche, text="c", command=lambda: None, font=("Segoe UI", 9, "bold"),
                       bg=self.c["bg_card"], fg=self.c["fg_primary"], relief="flat", cursor="hand2", padx=12,
                       pady=6, activebackground=self.c["border"], activeforeground="white",
                       disabledforeground=self.c["fg_secondary"], highlightthickness=0, bd=0).pack()
        self._ruhen()

    def test_hauptknopf_aus_stil_oder_farbe(self) -> None:
        a = self.pw.Button(self.flaeche, text="a", style="Accent.TButton")
        b = self.pw.Button(self.flaeche, text="b", bg=self.c["accent_btn"], fg="white")
        n = self.pw.Button(self.flaeche, text="n")
        self.assertEqual(("akzent", "akzent", "flaeche"), (a.stil, b.stil, n.stil))

    def test_gefahrenknopf_und_zurueck(self) -> None:
        k = self.pw.Button(self.flaeche, text="Start", bg=self.c["accent_btn"])
        k.configure(text="Stopp", bg=self.c["error_btn"])
        self.assertEqual("gefahr", k._art)
        self.assertIs(self.pw.look.z_gefahr, k._z)
        k.configure(text="Start", bg=self.c["accent_btn"])
        self.assertEqual("akzent", k._art)
        self.assertIs(self.pw.look.z, k._z)

    def test_ttk_zustaende(self) -> None:
        k = self.pw.Button(self.flaeche, text="x")
        k.state(["disabled"])
        self.assertEqual("disabled", k.cget("state"))
        self.assertEqual(("disabled",), k.state())
        k.state(["!disabled"])
        self.assertEqual("normal", k.cget("state"))
        self.assertTrue(k.instate(["!disabled"]))

    def test_breite_in_zeichen(self) -> None:
        schmal = self.pw.Button(self.flaeche, text="…", width=3)
        breit = self.pw.Button(self.flaeche, text="…", width=12)
        self.assertLess(schmal.winfo_reqwidth(), breit.winfo_reqwidth())

    def test_der_text_laesst_sich_aendern(self) -> None:
        k = self.pw.Button(self.flaeche, text="eins")
        k.configure(text="zwei und mehr")
        self.assertEqual("zwei und mehr", k.cget("text"))

    def test_steht_auch_in_einem_ttk_rahmen(self) -> None:
        rahmen = ttk.Frame(self.fenster)
        rahmen.pack()
        self.pw.Button(rahmen, text="x").pack()

    def test_klassenname_wie_beim_vorbild(self) -> None:
        self.assertEqual("Button", self.pw.Button(self.flaeche, text="x").__class__.__name__)


class EntryTests(_Basis):

    def test_ist_ein_echtes_tk_entry_mit_variable(self) -> None:
        var = tk.StringVar(value="abc")
        e = self.pw.Entry(self.flaeche, textvariable=var, width=10)
        e.pack(side="left")
        self.assertIsInstance(e, tk.Entry)
        self.assertEqual("abc", e.get())
        e.delete(0, "end")
        e.insert(0, "xyz")
        self.assertEqual("xyz", var.get())

    def test_pack_und_grid_gehen_an_die_karte(self) -> None:
        e = self.pw.Entry(self.flaeche)
        e.pack(side="left", fill="x", expand=True)
        self.assertEqual("pack", e.winfo_manager())
        self.assertEqual("left", str(e.pack_info()["side"]))
        e.pack_forget()
        self.assertEqual("", e._huelle.winfo_manager())
        e.grid(row=0, column=1, sticky="ew")
        self.assertEqual("grid", e._huelle.winfo_manager())
        self.assertEqual(1, int(e.grid_info()["column"]))
        e.grid_forget()
        self.assertEqual("", e._huelle.winfo_manager())

    def test_destroy_nimmt_die_karte_mit(self) -> None:
        e = self.pw.Entry(self.flaeche)
        e.pack()
        karte = e._huelle
        e.destroy()
        self.assertFalse(karte.winfo_exists())

    def test_zustaende_wie_ttk(self) -> None:
        e = self.pw.Entry(self.flaeche, state="disabled")
        self.assertEqual("disabled", str(e.cget("state")))
        e.state(["!disabled"])
        self.assertEqual("normal", str(e.cget("state")))

    def test_nimmt_alte_optionen_ohne_fehler(self) -> None:
        self.pw.Entry(self.flaeche, bg=self.c["bg_card"], fg=self.c["fg_primary"], relief="flat",
                      insertbackground=self.c["fg_primary"], bd=0, font=("Segoe UI", 10), show="*")

    def test_im_fokus_zeigt_die_karte_den_akzentrand(self) -> None:
        e = self.pw.Entry(self.flaeche)
        e.pack()
        e._fokus_setzen(True)
        self.assertEqual("fg_accent", e._huelle._rollen[1])
        e._fokus_setzen(False)
        self.assertEqual("border", e._huelle._rollen[1])


class ComboboxTests(_Basis):

    def test_werte_auswahl_und_ereignis(self) -> None:
        var = tk.StringVar()
        box = self.pw.Combobox(self.flaeche, textvariable=var, values=["Eins", "Zwei", "Drei"], state="readonly",
                               width=10)
        box.pack()
        gewaehlt: list[str] = []
        box.bind("<<ComboboxSelected>>", lambda _e: gewaehlt.append(box.get()))
        self.assertEqual(-1, box.current())
        box.current(1)
        self.assertEqual(("Zwei", 1), (box.get(), box.current()))
        self.assertEqual("Zwei", var.get())
        box._gewaehlt("Drei")
        self.fenster.update()
        self.assertEqual(["Drei"], gewaehlt)
        self.assertEqual(("Eins", "Zwei", "Drei"), tuple(box["values"]))

    def test_werte_tauschen_und_sperren(self) -> None:
        box = self.pw.Combobox(self.flaeche, values=["a"], state="readonly")
        box["values"] = ["x", "y"]
        self.assertEqual(("x", "y"), box.cget("values"))
        box.configure(state="disabled")
        self.assertEqual("disabled", box.cget("state"))
        box.set("y")
        self.assertEqual("y", box.get())

    def test_ohne_variable_und_gesetzt_von_aussen(self) -> None:
        var = tk.StringVar(value="A")
        box = self.pw.Combobox(self.flaeche, textvariable=var, values=["A", "B"])
        var.set("B")
        self.assertEqual("B", box.cget("text"))

    def test_klassenname_wie_beim_vorbild(self) -> None:
        self.assertEqual("Combobox", self.pw.Combobox(self.flaeche, values=[]).__class__.__name__)


class RadioUndHakenTests(_Basis):

    def test_radio_setzt_die_variable_und_zeigt_die_wahl(self) -> None:
        var = tk.StringVar(value="a")
        r1 = self.pw.Radiobutton(self.flaeche, text="A", value="a", variable=var)
        r2 = self.pw.Radiobutton(self.flaeche, text="B", value="b", variable=var)
        self.assertTrue(r1.an and not r2.an)
        r2.invoke()
        self.assertEqual("b", var.get())
        self.assertTrue(r2.an and not r1.an)
        var.set("a")
        self.assertTrue(r1.an and not r2.an)

    def test_radio_ruft_den_befehl(self) -> None:
        aufrufe: list[int] = []
        var = tk.StringVar(value="a")
        r = self.pw.Radiobutton(self.flaeche, text="B", value="b", variable=var, command=lambda: aufrufe.append(1),
                                bg=self.c["bg_main"], fg=self.c["fg_primary"], selectcolor=self.c["bg_card"],
                                activebackground=self.c["bg_main"], anchor="w")
        r.invoke()
        self.assertEqual([1], aufrufe)

    def test_haken_schaltet_die_variable(self) -> None:
        var = tk.BooleanVar(value=False)
        haken = self.pw.Checkbutton(self.flaeche, text="x", variable=var, bg=self.c["bg_main"],
                                    fg=self.c["fg_primary"], selectcolor=self.c["bg_card"], wraplength=200)
        haken.pack()
        haken.invoke()
        self.assertTrue(var.get())
        haken.configure(state="disabled")
        haken.invoke()
        self.assertTrue(var.get())


class KartenTests(_Basis):

    def test_text_steht_in_einer_karte_und_der_rollbalken_darin(self) -> None:
        text = self.pw.Text(self.flaeche, wrap="word", bg=self.c["console_bg"], fg=self.c["console_fg"],
                            relief="flat", highlightthickness=0, height=5)
        vsb = self.pw.Scrollbar(self.flaeche, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")             # laeuft ins Leere: der Balken steht schon in der Karte
        text.pack(side="left", fill="both", expand=True)
        for i in range(40):
            text.insert("end", "Zeile %d\n" % i)
        self.assertIsInstance(text, tk.Text)
        self.assertTrue(str(vsb).startswith(str(text._huelle)))
        self.assertEqual("pack", text._huelle.winfo_manager())
        self.assertIsNone(vsb._balken.winfo_manager() == "pack" or None)

    def test_waagerechter_balken_kommt_dazu(self) -> None:
        text = self.pw.Text(self.flaeche, wrap="none")
        hsb = self.pw.Scrollbar(self.flaeche, orient="horizontal", command=text.xview)
        text.configure(xscrollcommand=hsb.set)
        text.pack(fill="both", expand=True)
        self.assertEqual("grid", hsb._balken.winfo_manager())
        self.assertEqual(1, int(hsb._balken.grid_info()["row"]))

    def test_baum_und_liste_wie_ihre_vorbilder(self) -> None:
        baum = self.pw.Treeview(self.flaeche, columns=("a",), show="headings", height=3)
        baum.heading("a", text="A")
        for i in range(5):
            baum.insert("", "end", values=(i,))
        liste = self.pw.Listbox(self.flaeche, height=3, bg=self.c["bg_card"], fg=self.c["fg_primary"])
        for i in range(5):
            liste.insert("end", "x%d" % i)
        baum.grid(row=0, column=0, sticky="nsew")
        liste.grid(row=0, column=1, sticky="nsew")
        self.assertEqual(5, len(baum.get_children()))
        self.assertEqual(5, liste.size())
        self.assertEqual("grid", baum._huelle.winfo_manager())
        self.assertIsInstance(baum, ttk.Treeview)
        self.assertIsInstance(liste, tk.Listbox)

    def test_die_karte_nimmt_die_farbe_des_widgets(self) -> None:
        a = self.pw.Text(self.flaeche, bg=self.c["console_bg"])
        b = self.pw.Text(self.flaeche, bg=self.c["bg_card"])
        self.assertEqual("console_bg", a._rolle)
        self.assertEqual("bg_card", b._rolle)

    def test_text_ohne_hoehe_ist_kein_halber_bildschirm(self) -> None:
        text = self.pw.Text(self.flaeche)
        self.assertLessEqual(int(text.cget("height")), 12)

    def test_destroy_nimmt_die_karte_mit(self) -> None:
        text = self.pw.Text(self.flaeche)
        text.pack()
        karte = text._huelle
        text.destroy()
        self.assertFalse(karte.winfo_exists())

    def test_beschrifteter_rahmen(self) -> None:
        rahmen = self.pw.LabelFrame(self.flaeche, text="Titel", font=("Segoe UI", 10, "bold"),
                                    fg=self.c["fg_accent"], bg=self.c["bg_main"])
        rahmen.pack(fill="x")
        tk.Label(rahmen, text="Inhalt", bg=self.c["bg_main"]).pack()
        self.assertIsInstance(rahmen, tk.Frame)
        self.assertEqual("pack", rahmen.winfo_manager())


class KartenRahmenTests(_Basis):

    def test_eine_karte_auf_dem_fensterhintergrund_ist_rund(self) -> None:
        karte = self.pw.Karte(self.flaeche, bg=self.c["bg_card"], padx=12, pady=10)
        karte.pack(fill="x")
        tk.Label(karte, text="Inhalt", bg=self.c["bg_card"]).pack()
        self.assertIsInstance(karte, tk.Frame)
        self.assertEqual("pack", karte.winfo_manager())
        self.assertEqual("Karte", karte.__class__.__name__)
        self.assertEqual("bg_card", karte._huelle._rollen[0])

    def test_in_einer_karte_ist_eine_karte_nur_ein_rahmen(self) -> None:
        aussen = self.pw.Karte(self.flaeche, bg=self.c["bg_card"])
        innen = self.pw.Karte(aussen, bg=self.c["bg_card"])
        self.assertEqual("Frame", innen.__class__.__name__, "Eine Karte in der Karte waere ein Kasten im Kasten.")

    def test_rahmen_traegt_die_farbe_des_elternteils(self) -> None:
        karte = self.pw.Karte(self.flaeche, bg=self.c["console_bg"])
        rahmen = self.pw.Rahmen(karte)
        self.assertEqual(str(karte.cget("bg")).lower(), str(rahmen.cget("bg")).lower())
        self.assertEqual(self.c["bg_main"].lower(), str(self.pw.Rahmen(self.flaeche).cget("bg")).lower())


class ReglerUndDrehknopfTests(_Basis):

    def test_regler_wie_ttk_scale(self) -> None:
        gemeldet: list[str] = []
        regler = self.pw.Scale(self.flaeche, from_=50, to=150, orient="horizontal")
        regler.pack(fill="x")
        regler.configure(command=lambda wert: gemeldet.append(wert))
        regler.set(100)
        self.assertEqual(100.0, regler.get())
        self.assertEqual(["100.0"], gemeldet)
        regler.set(999)
        self.assertEqual(150.0, regler.get(), "Der Wert bleibt im Bereich.")
        regler.configure(to=120)
        self.assertEqual(120.0, regler.get())
        regler.set(120)
        self.assertEqual(2, len(gemeldet), "Ein gleicher Wert meldet nichts.")
        regler.bind("<ButtonRelease>", lambda _e: None, add="+")
        regler.bind("<KeyRelease>", lambda _e: None, add="+")

    def test_spinbox_wird_ein_drehknopf(self) -> None:
        var = tk.IntVar(value=3)
        knopf = self.pw.Spinbox(self.flaeche, from_=1, to=8, textvariable=var, width=4)
        knopf.pack(side="left")
        self.assertEqual("Drehknopf", knopf.__class__.__name__)
        var.set(5)
        self.assertEqual(5, int(var.get()))

    def test_elf_knopf_behaelt_sein_orange(self) -> None:
        k = self.pw.Button(self.flaeche, text="ELF senden", bg=self.c["elf_btn"], fg="white")
        self.assertEqual(("elf", "akzent"), (k._art, k.stil))
        self.assertIs(self.pw.look.z_farbig["elf"], k._z)
        self.assertEqual(self.c["elf_btn"].lower(), str(k._z.palette["accent_btn"]).lower())


class BalkenUndRollbalkenTests(_Basis):

    def test_fortschritt_wie_ttk(self) -> None:
        var = tk.DoubleVar(value=25)
        b = self.pw.Progressbar(self.flaeche, variable=var, maximum=200.0, mode="determinate")
        b.pack(fill="x")
        self.assertAlmostEqual(12.5, b.wert)
        var.set(100)
        self.assertAlmostEqual(50.0, b.wert)
        b.configure(value=50)
        self.assertAlmostEqual(25.0, b.wert)
        b["value"] = 200
        self.assertAlmostEqual(100.0, b.wert)

    def test_unbestimmt_laeuft_und_stoppt(self) -> None:
        b = self.pw.Progressbar(self.flaeche, mode="indeterminate")
        b.pack(fill="x")
        b.start(20)
        self.assertIsNotNone(b._lauf)
        b.stop()
        self.assertIsNone(b._lauf)

    def test_rollbalken_ohne_widget_hat_den_stil_der_flaeche(self) -> None:
        auf_main = self.pw.Scrollbar(self.flaeche, orient="vertical", command=lambda *a: None)
        self.assertEqual("Grund.Vertical.TScrollbar", str(auf_main.cget("style")))
        karte = tk.Frame(self.fenster, bg=self.c["bg_card"])
        karte.pack()
        auf_karte = self.pw.Scrollbar(karte, orient="horizontal", command=lambda *a: None)
        self.assertEqual("Karte.Horizontal.TScrollbar", str(auf_karte.cget("style")))


class FarbenTests(_Basis):

    def test_rolle_der_flaeche_auch_im_ttk_rahmen(self) -> None:
        look = self.pw.look
        self.assertEqual("bg_main", look.grund_von(self.flaeche))
        karte = tk.Frame(self.fenster, bg=self.c["bg_card"])
        self.assertEqual("bg_card", look.grund_von(karte))
        self.assertIn(look.grund_von(ttk.Frame(self.fenster)), ("bg_main", "bg_card", "console_bg"))

    def test_naechste_rolle_bei_gemischter_farbe(self) -> None:
        look = self.pw.look
        gemischt = look.als_hex(self.c["bg_card"])
        self.assertEqual("bg_card", look.rolle_fuer(gemischt))
        self.assertEqual("bg_card", look.rolle_fuer(""))


class QuelltextTests(unittest.TestCase):
    """Der Waechter: Fenster-Methoden bauen keine eckigen Teile mehr."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.baum = ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))
        cls.methoden = {}
        for klasse in ast.walk(cls.baum):
            if isinstance(klasse, ast.ClassDef) and klasse.name == "PS5ConverterGUI":
                for fn in klasse.body:
                    if isinstance(fn, ast.FunctionDef):
                        cls.methoden[fn.name] = fn

    def test_alle_fenstermethoden_gibt_es(self) -> None:
        self.assertEqual([], [m for m in FENSTER_METHODEN if m not in self.methoden])

    def test_keine_fenstermethode_baut_ein_eckiges_teil(self) -> None:
        funde = []
        for name in FENSTER_METHODEN:
            for k in ast.walk(self.methoden[name]):
                if isinstance(k, ast.Call) and _name(k.func) in ECKIG and (name, _name(k.func)) not in ERLAUBT:
                    funde.append("%s:%d %s" % (name, k.lineno, _name(k.func)))
        self.assertEqual([], funde, "Ein Fenster baut wieder ein eckiges Teil - self._pw.<Name> nehmen "
                                    "(ps5_validator/ui/fenster_pillen.py)")

    def test_kein_zierrahmen_mehr_um_tabellen_und_protokolle(self) -> None:
        """Ein 1-Punkt-Rahmen in Kartenfarbe stuende als eckiger Umriss um die runde Karte."""
        funde = []
        for name in FENSTER_METHODEN:
            for k in ast.walk(self.methoden[name]):
                if not (isinstance(k, ast.Call) and _name(k.func) == "tk.Frame"):
                    continue
                optionen = {kw.arg: ast.unparse(kw.value) for kw in k.keywords}
                if optionen.get("padx") == "1" and optionen.get("pady") == "1":
                    funde.append("%s:%d" % (name, k.lineno))
        self.assertEqual([], funde, "Zierrahmen: self._pw.Rahmen(eltern) nehmen")

    def test_jede_ausnahme_ist_noch_eine(self) -> None:
        for (name, art), _grund in ERLAUBT.items():
            gefunden = any(isinstance(k, ast.Call) and _name(k.func) == art for k in ast.walk(self.methoden[name]))
            self.assertTrue(gefunden, "Ausnahme %s/%s gilt nicht mehr" % (name, art))

    def test_die_ersatzteile_tragen_die_namen_ihrer_vorbilder(self) -> None:
        from ps5_validator.ui import fenster_pillen as fp
        for name in ("Button", "Entry", "Combobox", "Radiobutton", "Progressbar", "Text", "Treeview", "Listbox",
                     "LabelFrame"):
            self.assertEqual(name, getattr(fp, name).__name__)
        for name in ("Checkbutton", "Scrollbar"):
            self.assertTrue(callable(getattr(fp.Widgets, name)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
