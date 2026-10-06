# -*- coding: utf-8 -*-
"""Die runde Optik fuer die Nebenfenster - Ersatzteile mit den Namen und Optionen von tk/ttk.

Nutzerwunsch vom 05.10.2026: "Bitte die optik bei allen fenstern an die neue optik
anpassen." Die Ansichten UMWANDELN und KONSOLE, die Bibliothek und das Fenster
"PS4 PKG -> OTA" tragen sie schon: Knoepfe, Felder und Klapplisten als Pille,
Haken als gerundete Kaestchen, Tabellen und Protokolle in runden Karten.

Die uebrigen Fenster (Einstellungen, ShadowMount+, Downloads, KLOG ...) waren von
Hand mit ``ttk.Button``, ``tk.Entry``, ``ttk.Combobox`` und ``tk.Text`` gebaut. Statt
sie alle neu zu schreiben, steht hier fuer jedes dieser Teile ein Ersatz, der
dieselben Optionen nimmt und dieselben Methoden kennt - die Aufrufstelle wechselt
nur den Namen (``ttk.Button(...)`` -> ``self._pw.Button(...)``), alles andere
(Platz, Befehle, Variablen) bleibt, wie es war. Das war der Wunsch schon bei den
Ansichten: "alles am selben Platz, aber mit runden Ecken".

* ``Button`` (Pille; ``style="Accent.TButton"`` oder blaue Farbe = Hauptknopf,
  rote Farbe = Gefahrenknopf; dehnt sich bei ``fill="x"``),
* ``Entry`` (ein echtes ``tk.Entry`` in einer Pille; ``pack``/``grid`` gehen an die Pille),
* ``Combobox`` (Pille mit Pfeil und Menue; ``get``/``set``/``current``/``values``),
* ``Radiobutton`` (ein Chip, der die Variable setzt), ``Checkbutton`` (der runde Haken
  des Hauptprogramms), ``Progressbar`` (Balken mit runden Enden),
* ``Text``, ``Treeview``, ``Listbox`` (echte Widgets in einer runden Karte; ein
  ``Scrollbar(command=widget.yview)`` steht von selbst *in* der Karte),
* ``Scrollbar`` (schmal, in der Farbe der Flaeche).

Dieses Modul kennt das Hauptprogramm nur ueber ``gui._COLORS``, ``gui._KARTEN_ECKE``,
``gui._runder_haken`` und ``gui.root``.
"""
from __future__ import annotations

import logging
import sys
import tkinter as tk
import types
from tkinter import ttk
from typing import Any, Callable

from ps5_validator.ui import ps4_ota_bausteine as bausteine
from ps5_validator.utils import bibliothek_raster as raster
from ps5_validator.utils import bibliothek_zeichnen as zeichnen

logger = logging.getLogger("PS5Converter.ui.fenster_pillen")

#: Wie die Flaeche heisst, auf der ein Teil steht - die Rolle in der Palette.
#: ``header_bg`` ist die Titelleiste der rahmenlosen Fenster (Ressourcen, Info-Popup).
_ROLLEN_GRUND = ("bg_card", "bg_main", "console_bg", "header_bg")

#: Rollbalkenstile je Flaechenrolle (das Hauptprogramm legt sie an: ``_SCHMALE_ROLLBALKEN``).
_ROLLBALKEN_PRAEFIX = {"bg_card": "Karte", "console_bg": "Tief", "bg_main": "Grund"}


# ---------------------------------------------------------------------------
# Gefahrenknopf: dieselbe Pille, aber in der roten Farbe des Designs
# ---------------------------------------------------------------------------

class FarbZeichner(bausteine.FlachZeichner):
    """Der Zeichner fuer einen Hauptknopf in einer anderen Farbe als der blauen.

    ``akzent`` faerbt mit ``accent_btn``; hier steht dort die Farbe der gewaehlten Rolle - ``error_btn`` fuer
    Knoepfe, die etwas beenden (Log-Server anhalten), ``elf_btn`` fuer "ELF senden" im Y2JB-Fenster, das so
    sein Orange behaelt (die Farbe sagt dort, welcher Weg gemeint ist).
    """

    def __init__(self, wurzel: tk.Misc, palette: Callable[[], dict], familie: str, pt: Callable[[float], float],
                 farbrolle: str) -> None:
        super().__init__(wurzel, palette, familie, pt)
        self._farbrolle = farbrolle

    @property
    def palette(self) -> dict:
        p = dict(super().palette)
        farbe = p.get(self._farbrolle)
        if farbe:
            p["accent_btn"] = farbe
        return p


#: Knopfarten mit eigener Farbe: Name -> Rolle der Palette.
_KNOPF_FARBEN = {"gefahr": "error_btn", "elf": "elf_btn"}


# ---------------------------------------------------------------------------
# Das Aussehen als Ganzes - mit Farbe der Flaeche darunter
# ---------------------------------------------------------------------------

class FensterLook(bausteine.Look):
    """``Look`` der OTA-Bausteine, dazu: die Rolle jeder Flaeche zuverlaessig finden.

    Nebenfenster bauen aus ``tk.Frame`` *und* ``ttk.Frame``; ein ttk-Rahmen kennt kein
    ``bg``, seine Farbe steht im Stil. Findet sich keine Rolle mit genau dieser
    Farbe (eine gemischte Feldfarbe), gilt die naechstliegende.
    """

    def __init__(self, gui, schrift: str, mono: str, pt: Callable[[int], int]) -> None:
        super().__init__(gui, schrift, mono, pt)
        self.z_farbig = {art: FarbZeichner(gui.root, lambda: gui._COLORS, schrift, pt, rolle)
                         for art, rolle in _KNOPF_FARBEN.items()}
        self.z_gefahr = self.z_farbig["gefahr"]

    # --- Farben ---------------------------------------------------------------
    def als_hex(self, farbe: str) -> str:
        """Jede Tk-Farbe ("white", "#fff") als #rrggbb."""
        try:
            r, g, b = (wert // 257 for wert in self.g.root.winfo_rgb(str(farbe)))
        except tk.TclError:
            return "#000000"
        return "#%02x%02x%02x" % (r, g, b)

    def farbe_von(self, widget) -> str:
        """Die Farbe der Flaeche, auf der ``widget`` steht: der naechste Vorfahr mit eigener Farbe."""
        knoten = widget
        for _ in range(24):
            if knoten is None:
                break
            try:
                return self.als_hex(str(knoten.cget("bg")))
            except tk.TclError:
                try:
                    stil = str(knoten.cget("style")) or knoten.winfo_class()
                    farbe = ttk.Style().lookup(stil, "background")
                    if farbe:
                        return self.als_hex(str(farbe))
                except tk.TclError:
                    pass
            knoten = getattr(knoten, "master", None)
        return self.als_hex(self.c.get("bg_card", "#000000"))

    def rolle_fuer(self, farbe, standard: str = "bg_card", rollen: tuple = _ROLLEN_GRUND) -> str:
        """Die Rolle der Palette, deren Farbe ``farbe`` am naechsten kommt (genau gleich gewinnt)."""
        if not farbe:
            return standard
        ziel = self.als_hex(str(farbe)).lower()
        beste, abstand = standard, None
        for rolle in rollen:
            kandidat = str(self.c.get(rolle, "")).lower()
            if not kandidat.startswith("#") or len(kandidat) != 7:
                continue
            if kandidat == ziel:
                return rolle
            d = sum((int(kandidat[i:i + 2], 16) - int(ziel[i:i + 2], 16)) ** 2 for i in (1, 3, 5))
            if abstand is None or d < abstand:
                beste, abstand = rolle, d
        return beste

    def grund_von(self, widget) -> str:
        return self.rolle_fuer(self.farbe_von(widget))

    def hintergrund(self, widget) -> str:
        return self.farbe_von(widget)

    # --- Knopfarten ---------------------------------------------------------------
    def knopfart(self, style: str = "", bg=None) -> str:
        """``flaeche`` (Vorgabe), ``akzent`` (Hauptknopf), ``gefahr`` oder ``elf`` - aus Stil oder Farbe."""
        name = str(style or "")
        if "Accent" in name:
            return "akzent"
        if "Error" in name:
            return "gefahr"
        if bg:
            hex_ = self.als_hex(str(bg)).lower()
            if hex_ == self.als_hex(str(self.c.get("accent_btn", ""))).lower():
                return "akzent"
            for art, rolle in _KNOPF_FARBEN.items():
                if hex_ == self.als_hex(str(self.c.get(rolle, ""))).lower():
                    return art
        return "flaeche"

    def zeichner_fuer(self, art: str) -> raster.Zeichner:
        return self.z_farbig.get(art, self.z)

    def rollbalken_stil(self, master, orient: str) -> str:
        rolle = self.grund_von(master)
        praefix = _ROLLBALKEN_PRAEFIX.get(rolle, "Karte")
        richtung = "Vertical" if str(orient) == "vertical" else "Horizontal"
        return "%s.%s.TScrollbar" % (praefix, richtung)


# ---------------------------------------------------------------------------
# Knoepfe, die sich bei fill="x" dehnen
# ---------------------------------------------------------------------------

class _Dehnbar:
    """Ein gezeichneter Knopf, der bei ``fill="x"`` die ganze Breite einnimmt.

    ``KartenKnopf`` malt in seiner natuerlichen Groesse oben links. Ein Knopf oder eine
    Klappliste, die ihre Zeile fuellen soll (``pack(fill="x", expand=True)``), bliebe so ein
    Stueck links im Feld stehen - hier wird in der wirklichen Breite gezeichnet.
    """

    def _zeichnen(self) -> None:
        self.delete("all")
        links, oben, _unten = self._rand
        breite = self._b
        try:
            gedehnt = int(self.winfo_width()) - 2 * links
            if gedehnt > breite + 1:
                breite = gedehnt
        except tk.TclError:
            pass
        spec = raster.KnopfSpec(name="knopf", text=self._text, stil=self.stil, aktiv=self._state != "disabled",
                                chevron=self._chevron, fett=self._fett)
        try:
            self._knopf = raster.knopf_zeichnen(self, self._z, spec, links, oben, breite, self._h,
                                                zustand=self._zustand())
            if self._fokus and self._state != "disabled":
                ring = self._z.palette.get("fg_accent", "#7fb2ff")
                self.create_line(links + 3, oben + self._h - 2, links + breite - 3, oben + self._h - 2,
                                 fill=ring, width=max(1, int(self._z.faktor)))
        except tk.TclError:
            pass
        tk.Canvas.configure(self, cursor="arrow" if self._state == "disabled" else "hand2")

    def _bei_groesse(self, ereignis: Any) -> None:
        if int(ereignis.width) != getattr(self, "_gemalt_breite", -1):
            self._gemalt_breite = int(ereignis.width)
            self._zeichnen()


# ---------------------------------------------------------------------------
# Button
# ---------------------------------------------------------------------------

#: Optionen, die ein tk.Button/ttk.Button kennt und die eine Pille nicht braucht.
_KNOPF_KOSMETIK = ("relief", "bd", "borderwidth", "highlightthickness", "highlightbackground", "highlightcolor",
                   "padx", "pady", "activebackground", "activeforeground", "disabledforeground", "anchor",
                   "justify", "cursor", "overrelief", "compound", "underline", "wraplength", "default",
                   "repeatdelay", "repeatinterval", "image", "bitmap", "textvariable", "font", "fg", "foreground",
                   "background", "padding")


class Button(_Dehnbar, raster.KartenKnopf):
    """Ersatz fuer ``tk.Button``, ``ttk.Button`` und ``flach_knopf``: eine Pille.

    ``style="Accent.TButton"`` oder eine blaue ``bg`` machen den Hauptknopf (Verlauf),
    ``Error.TButton`` oder eine rote ``bg`` einen Gefahrenknopf, ``Klein.TButton`` einen
    flacheren. ``width`` zaehlt wie beim tk.Button in Zeichen.
    """

    def __init__(self, master, look: FensterLook, text: str = "", command=None, style: str = "",
                 state: str = "normal", width=None, bg=None, **legacy: Any) -> None:
        for name in _KNOPF_KOSMETIK:
            legacy.pop(name, None)
        self._look = look
        self._style = str(style or "")
        self._art = look.knopfart(self._style, bg)
        self._zeichen_breite = width
        klein = self._style.startswith("Klein")
        z = look.zeichner_fuer(self._art)
        stil = "flaeche" if self._art == "flaeche" else "akzent"
        super().__init__(master, z, str(text), command, stil, grund=look.grund_von(master),
                         breite=self._feste_breite(z, klein) if width else None,
                         hoehe=26 if klein else 30, fett=stil == "akzent",
                         state="disabled" if str(state) == "disabled" else "normal", **legacy)
        self.bind("<Configure>", self._bei_groesse, add="+")

    # --- Groesse ------------------------------------------------------------------
    def _feste_breite(self, z: raster.Zeichner, klein: bool) -> int:
        """``width`` Zeichen breit wie bei tk.Button - nie schmaler als hoch (eine runde Pille)."""
        zeichen = z.messen("knopf", "0") * int(self._zeichen_breite)
        return max(zeichen + 2 * z.px(10), z.px(26 if klein else 30))

    # --- tk-Schnittstelle ---------------------------------------------------------
    def configure(self, cnf: Any = None, **kwargs: Any) -> Any:  # noqa: A003 - bewusst tk-kompatibel
        if cnf:
            kwargs = dict(cnf, **kwargs)
        neu_art = None
        if "style" in kwargs:
            self._style = str(kwargs.pop("style") or "")
            neu_art = self._look.knopfart(self._style, kwargs.get("bg"))
        elif "bg" in kwargs:
            neu_art = self._look.knopfart(self._style, kwargs["bg"])
        if "width" in kwargs:
            self._zeichen_breite = kwargs.pop("width")
            self._breite_fest = (self._feste_breite(self._z, self._style.startswith("Klein"))
                                 if self._zeichen_breite else None)
            kwargs["_neu"] = True
        for name in _KNOPF_KOSMETIK:
            if name not in ("bg", "background"):
                kwargs.pop(name, None)
        kwargs.pop("background", None)
        neu = bool(kwargs.pop("_neu", False))
        super().configure(**kwargs)
        if neu_art is not None and neu_art != self._art:
            self._art = neu_art
            self._z = self._look.zeichner_fuer(neu_art)
            self._basis_stil = "flaeche" if neu_art == "flaeche" else "akzent"
            self._fett = self._basis_stil == "akzent"
            neu = True
        if neu:
            self._groesse_setzen()
            self._zeichnen()

    config = configure

    def state(self, zustaende: Any = None) -> tuple:
        """Wie ``ttk.Button.state``: ``["disabled"]`` sperrt, ``["!disabled"]`` gibt frei."""
        if zustaende is not None:
            for eintrag in ([zustaende] if isinstance(zustaende, str) else list(zustaende)):
                if eintrag == "disabled":
                    self.configure(state="disabled")
                elif eintrag == "!disabled":
                    self.configure(state="normal")
        return ("disabled",) if self._state == "disabled" else ()

    def instate(self, zustaende: Any, befehl: "Callable | None" = None) -> Any:
        """Wie ``ttk.Button.instate`` fuer ``disabled``/``!disabled``."""
        liste = [zustaende] if isinstance(zustaende, str) else list(zustaende)
        gesperrt = self._state == "disabled"
        passt = all((gesperrt if e == "disabled" else not gesperrt) for e in liste if e in ("disabled", "!disabled"))
        if passt and befehl is not None:
            return befehl()
        return passt


# ---------------------------------------------------------------------------
# Combobox
# ---------------------------------------------------------------------------

class Combobox(_Dehnbar, raster.KartenKnopf):
    """Ersatz fuer ``ttk.Combobox`` (nur auswaehlen): eine Pille mit Pfeil, ein Klick oeffnet das Menue.

    Kennt ``get``, ``set``, ``current``, ``values`` (auch als ``box["values"]``), ``state``
    (``readonly``/``normal`` bedienbar, ``disabled`` gesperrt), ``textvariable`` und das Ereignis
    ``<<ComboboxSelected>>``. ``width`` zaehlt in Zeichen, ohne Angabe passt sich die Pille dem
    laengsten Wert an.
    """

    def __init__(self, master, look: FensterLook, textvariable: "tk.Variable | None" = None, values: Any = (),
                 state: str = "readonly", width=None, postcommand: "Callable | None" = None,
                 **legacy: Any) -> None:
        for name in ("font", "style", "justify", "exportselection", "height", "cursor", "takefocus",
                     "background", "foreground", "bg", "fg"):
            legacy.pop(name, None)
        self._look = look
        self._auswahl_befehle: list = []
        #: Was ``cget("state")`` im freigegebenen Zustand nennt: ``readonly`` (Vorgabe) oder ``normal``.
        self._wunsch = str(state) if str(state) != "disabled" else "readonly"
        self._variable = textvariable if textvariable is not None else tk.StringVar(master=master)
        self._werte = [str(w) for w in (values or ())]
        self._postcommand = postcommand
        self._zeichen_breite = width
        z = look.z
        super().__init__(master, z, str(self._variable.get()), self._menue_zeigen, "auswahl",
                         grund=look.grund_von(master), breite=self._breite_fuer(z), hoehe=30, chevron=True,
                         state="disabled" if str(state) == "disabled" else "normal", **legacy)
        self._spur = self._variable.trace_add("write", self._nachziehen)
        self.bind("<Destroy>", self._weg, add="+")
        self.bind("<Configure>", self._bei_groesse, add="+")

    # --- Groesse ---------------------------------------------------------------------
    def _breite_fuer(self, z: raster.Zeichner) -> int:
        luft = z.px(48)
        if self._zeichen_breite:
            return max(z.messen("knopf", "0") * int(self._zeichen_breite) + luft, z.px(90))
        text = max((z.messen("knopf", w) for w in self._werte), default=0)
        return max(z.px(110), text + luft)

    def _weg(self, ereignis: Any) -> None:
        if ereignis.widget is not self:
            return
        try:
            self._variable.trace_remove("write", self._spur)
        except (tk.TclError, ValueError):
            pass

    def _nachziehen(self, *_a: Any) -> None:
        try:
            self.configure(text=str(self._variable.get()))
        except tk.TclError:
            pass

    # --- Menue -------------------------------------------------------------------------
    def _menue_zeigen(self) -> None:
        if self._postcommand is not None:
            try:
                self._postcommand()
            except Exception as exc:  # noqa: BLE001
                logger.debug("postcommand der Klappliste: %s", exc)
        if not self._werte:
            return
        bausteine.menue_unter(self, self._z, self._werte, str(self._variable.get()), self._gewaehlt)

    def _gewaehlt(self, wert: str) -> None:
        self.set(wert)
        self.event_generate("<<ComboboxSelected>>")

    # ``<<ComboboxSelected>>`` laeuft ueber eine eigene Liste statt ueber Tk: ``event_generate`` erreicht ein
    # Widget in einem verborgenen Fenster nicht (und Fenster unter einem verborgenen Elternfenster bleiben
    # verborgen). So kommt die Auswahl immer an - mit einem Ereignis, das ``widget`` kennt.
    def bind(self, sequence: "str | None" = None, func: "Callable | None" = None, add: Any = None) -> Any:
        if sequence == "<<ComboboxSelected>>" and func is not None:
            if add not in ("+", True):
                self._auswahl_befehle.clear()
            self._auswahl_befehle.append(func)
            return "auswahl%d" % len(self._auswahl_befehle)
        return super().bind(sequence, func, add)

    def event_generate(self, sequence: str, **kw: Any) -> Any:
        if sequence != "<<ComboboxSelected>>":
            return super().event_generate(sequence, **kw)
        ereignis = types.SimpleNamespace(widget=self, x=0, y=0, type="VirtualEvent", keysym="")
        for befehl in list(self._auswahl_befehle):
            try:
                befehl(ereignis)
            except Exception:  # noqa: BLE001 - wie Tk: ueber den Meldeweg des Programms
                self._root().report_callback_exception(*sys.exc_info())
        return None

    # --- ttk.Combobox-Schnittstelle ------------------------------------------------------
    def get(self) -> str:
        return str(self._variable.get())

    def set(self, wert: Any) -> None:
        if str(self._variable.get()) != str(wert):
            self._variable.set(str(wert))
        else:
            self._nachziehen()

    def current(self, index: "int | None" = None) -> int:
        """Ohne Argument der Index des Werts (``-1``, wenn er nicht in der Liste steht); mit Index setzt es."""
        if index is None:
            try:
                return self._werte.index(self.get())
            except ValueError:
                return -1
        if 0 <= int(index) < len(self._werte):
            self.set(self._werte[int(index)])
        return int(index)

    @property
    def values(self) -> tuple:
        return tuple(self._werte)

    def _werte_setzen(self, werte: Any) -> None:
        self._werte = [str(w) for w in (werte or ())]
        self._breite_fest = self._breite_fuer(self._z)
        self._groesse_setzen()
        self._zeichnen()

    def configure(self, cnf: Any = None, **kwargs: Any) -> Any:  # noqa: A003 - bewusst tk-kompatibel
        if cnf:
            kwargs = dict(cnf, **kwargs)
        if "values" in kwargs:
            self._werte_setzen(kwargs.pop("values"))
        if "textvariable" in kwargs:
            neu = kwargs.pop("textvariable")
            try:
                self._variable.trace_remove("write", self._spur)
            except (tk.TclError, ValueError):
                pass
            self._variable = neu if neu is not None else tk.StringVar(master=self)
            self._spur = self._variable.trace_add("write", self._nachziehen)
            kwargs["text"] = str(self._variable.get())
        if "postcommand" in kwargs:
            self._postcommand = kwargs.pop("postcommand")
        if "state" in kwargs and str(kwargs["state"]) != "disabled":
            self._wunsch = str(kwargs["state"])
        if "width" in kwargs:
            self._zeichen_breite = kwargs.pop("width")
            self._breite_fest = self._breite_fuer(self._z)
            kwargs["_neu"] = True
        for name in ("font", "style", "justify", "exportselection", "height", "background", "foreground"):
            kwargs.pop(name, None)
        neu_zeichnen = bool(kwargs.pop("_neu", False))
        raster.KartenKnopf.configure(self, **kwargs)
        if neu_zeichnen:
            self._groesse_setzen()
            self._zeichnen()

    config = configure

    def cget(self, key: str) -> Any:
        if key == "state":
            return "disabled" if self._state == "disabled" else self._wunsch
        if key == "values":
            return tuple(self._werte)
        if key == "textvariable":
            return str(self._variable)
        if key == "width":
            return self._zeichen_breite or 0
        return super().cget(key)

    def __setitem__(self, key: str, wert: Any) -> None:
        self.configure(**{key: wert})

    def state(self, zustaende: Any = None) -> tuple:
        if zustaende is not None:
            for eintrag in ([zustaende] if isinstance(zustaende, str) else list(zustaende)):
                if eintrag == "disabled":
                    self.configure(state="disabled")
                elif eintrag == "!disabled":
                    self.configure(state="normal")
        return ("disabled",) if self._state == "disabled" else ()

# ---------------------------------------------------------------------------
# Radiobutton als Chip
# ---------------------------------------------------------------------------

class Radiobutton(_Dehnbar, raster.KartenKnopf):
    """Ersatz fuer ``tk.Radiobutton``/``ttk.Radiobutton``: ein Chip, der ``variable`` auf ``value`` setzt.

    Der gewaehlte Chip steht hell, die uebrigen dunkel - wie die Reiter und Filter der Bibliothek.
    """

    def __init__(self, master, look: FensterLook, text: str = "", value: Any = "", variable: "tk.Variable | None" = None,
                 command: "Callable | None" = None, state: str = "normal", **legacy: Any) -> None:
        for name in _KNOPF_KOSMETIK + ("selectcolor", "indicatoron", "style", "width", "bg"):
            legacy.pop(name, None)
        self._look = look
        self._wert = value
        self._variable = variable
        self._befehl = command
        super().__init__(master, look.z, str(text), self._gewaehlt, "chip", grund=look.grund_von(master),
                         hoehe=28, an=False, state="disabled" if str(state) == "disabled" else "normal", **legacy)
        self._spur = None
        if variable is not None:
            self._spur = variable.trace_add("write", self._variable_geaendert)
            self._variable_geaendert()
        self.bind("<Destroy>", self._weg, add="+")

    def _weg(self, ereignis: Any) -> None:
        if ereignis.widget is not self or self._variable is None or self._spur is None:
            return
        try:
            self._variable.trace_remove("write", self._spur)
        except (tk.TclError, ValueError):
            pass

    def _variable_geaendert(self, *_a: Any) -> None:
        try:
            an = self._variable is not None and str(self._variable.get()) == str(self._wert)
            if an != self._an:
                self.configure(an=an)
        except tk.TclError:
            pass

    def _gewaehlt(self) -> None:
        if self._variable is not None and str(self._variable.get()) != str(self._wert):
            self._variable.set(self._wert)
        if self._befehl is not None:
            self._befehl()

    def select(self) -> None:
        if self._variable is not None:
            self._variable.set(self._wert)

    def configure(self, cnf: Any = None, **kwargs: Any) -> Any:  # noqa: A003 - bewusst tk-kompatibel
        if cnf:
            kwargs = dict(cnf, **kwargs)
        if "command" in kwargs:
            self._befehl = kwargs.pop("command")
        for name in _KNOPF_KOSMETIK + ("selectcolor", "indicatoron", "style", "width"):
            kwargs.pop(name, None)
        raster.KartenKnopf.configure(self, **kwargs)

    config = configure


# ---------------------------------------------------------------------------
# Eingabefeld
# ---------------------------------------------------------------------------

class _Huelle:
    """Wer in einer runden Karte steht, wird ueber die Karte angeordnet.

    Die Ersatzteile ``Entry``, ``Text``, ``Treeview`` und ``Listbox`` sind **echte** Widgets ihrer
    Art - nur steht eine runde Karte (``_huelle``) um sie. ``pack``, ``grid`` und ``place`` des
    Widgets gehen deshalb an die Karte, ebenso ``*_forget`` und ``*_info``; sonst stuende das Widget
    ohne Rundung auf dem Fenster und die Karte leer daneben.
    """

    _huelle: tk.Misc

    def pack_configure(self, cnf: Any = None, **kw: Any) -> None:
        self._huelle.pack_configure(cnf or {}, **kw)

    pack = pack_configure

    def grid_configure(self, cnf: Any = None, **kw: Any) -> None:
        self._huelle.grid_configure(cnf or {}, **kw)

    grid = grid_configure

    def place_configure(self, cnf: Any = None, **kw: Any) -> None:
        self._huelle.place_configure(cnf or {}, **kw)

    place = place_configure

    def pack_forget(self) -> None:
        self._huelle.pack_forget()

    forget = pack_forget

    def grid_forget(self) -> None:
        self._huelle.grid_forget()

    def grid_remove(self) -> None:
        self._huelle.grid_remove()

    def place_forget(self) -> None:
        self._huelle.place_forget()

    def pack_info(self) -> dict:
        return self._huelle.pack_info()

    def grid_info(self) -> dict:
        return self._huelle.grid_info()

    def place_info(self) -> dict:
        return self._huelle.place_info()

    def winfo_manager(self) -> str:
        return self._huelle.winfo_manager()

    def lift(self, ueber: Any = None) -> None:
        self._huelle.lift(ueber)

    tkraise = lift

    def lower(self, unter: Any = None) -> None:
        self._huelle.lower(unter)

    def destroy(self) -> None:
        """Baut die Karte samt Widget ab - und nicht beide doppelt (die Karte ruft ``destroy`` der Kinder)."""
        if getattr(self, "_abgebaut", False):
            super().destroy()                  # type: ignore[misc]
            return
        self._abgebaut = True
        try:
            self._huelle.destroy()
        except tk.TclError:
            pass


class Entry(_Huelle, tk.Entry):
    """Ersatz fuer ``tk.Entry`` und ``ttk.Entry``: ein echtes Textfeld in einer Pille.

    Im Fokus zeichnet die Pille ihren Rand in der Akzentfarbe - so sieht man, wo man tippt.
    ``width`` zaehlt in Zeichen wie immer; ``fill="x"`` macht das Feld breit.
    """

    #: Optionen, die nur ein tk.Entry kannte und die die Pille selbst setzt.
    _FARBEN = ("bg", "background", "fg", "foreground", "relief", "bd", "borderwidth", "highlightthickness",
               "highlightbackground", "highlightcolor", "insertbackground", "insertwidth", "selectbackground",
               "selectforeground", "disabledbackground", "disabledforeground", "readonlybackground", "style",
               "padding")

    def __init__(self, master, look: FensterLook, **opt: Any) -> None:
        z = look.z
        p = z.palette
        for name in self._FARBEN:
            opt.pop(name, None)
        schrift = opt.pop("font", None) or z.schrift_angabe("eingabe")
        karte = raster.RundeKarte(master, z, fuellung="console_bg", rand="border", grund=look.grund_von(master),
                                  radius=None, polster=(14, 3))
        tk.Entry.__init__(self, karte.innen, relief="flat", bd=0, highlightthickness=0, bg=p["console_bg"],
                          fg=p["fg_primary"], insertbackground=p["fg_primary"], selectbackground=p["accent_btn"],
                          selectforeground="#ffffff", disabledbackground=p["console_bg"],
                          disabledforeground=p["fg_secondary"], readonlybackground=p["console_bg"],
                          font=schrift, **opt)
        self._huelle = karte
        self._look = look
        self._fokus_an = False
        tk.Pack.pack_configure(self, fill="x", expand=True, ipady=z.px(3))
        tk.Entry.bind(self, "<FocusIn>", lambda _e: self._fokus_setzen(True), add="+")
        tk.Entry.bind(self, "<FocusOut>", lambda _e: self._fokus_setzen(False), add="+")

    def _fokus_setzen(self, an: bool) -> None:
        if an == self._fokus_an:
            return
        self._fokus_an = an
        fuellung, _rand, grund = self._huelle._rollen
        self._huelle._rollen = (fuellung, "fg_accent" if an else "border", grund)
        try:
            self._huelle._bild_neu()
        except tk.TclError:
            pass

    def state(self, zustaende: Any = None) -> tuple:
        """Wie ``ttk.Entry.state``: ``disabled``/``readonly`` und deren Verneinung."""
        if zustaende is not None:
            for eintrag in ([zustaende] if isinstance(zustaende, str) else list(zustaende)):
                if eintrag == "disabled":
                    self.configure(state="disabled")
                elif eintrag == "readonly":
                    self.configure(state="readonly")
                elif eintrag in ("!disabled", "!readonly"):
                    self.configure(state="normal")
        gesetzt = str(self.cget("state"))
        return () if gesetzt == "normal" else (gesetzt,)


# ---------------------------------------------------------------------------
# Text, Tabelle, Liste in einer runden Karte - Rollbalken stehen in der Karte
# ---------------------------------------------------------------------------

class _Zwischenhalter:
    """Der Rollbalken, den die Karte schon enthaelt - mit stummen ``pack``/``grid``.

    Die Aufrufstelle baut ``Scrollbar(master, command=text.yview)`` und packt ihn danach neben das
    Widget. Steht das Widget in einer Karte, gehoert der Balken *hinein*: Er ist dort schon
    angeordnet, und die Anweisungen der Aufrufstelle laufen ins Leere. Alles andere (``set``,
    ``get``, ``configure`` ...) geht an den echten Balken.
    """

    _STUMM = ("pack", "pack_configure", "grid", "grid_configure", "place", "place_configure", "pack_forget",
              "grid_forget", "grid_remove", "place_forget", "forget", "lift", "lower", "tkraise")

    def __init__(self, balken: ttk.Scrollbar) -> None:
        object.__setattr__(self, "_balken", balken)

    def __getattr__(self, name: str) -> Any:
        if name in _Zwischenhalter._STUMM:
            return lambda *a, **k: None
        return getattr(self._balken, name)

    def __str__(self) -> str:
        return str(self._balken)

    def __bool__(self) -> bool:
        return True


class _MitKarte(_Huelle):
    """Gemeinsames fuer ``Text``, ``Treeview`` und ``Listbox``: Karte, innen angeordnet mit ``grid``."""

    _vsb: "ttk.Scrollbar | None"
    _hsb: "ttk.Scrollbar | None"

    def _karte_bauen(self, master, look: FensterLook, rolle: str) -> raster.RundeKarte:
        karte = raster.RundeKarte(master, look.z, fuellung=rolle, rand="border", grund=look.grund_von(master),
                                  radius=look.g._KARTEN_ECKE, polster=(8, 6), fuellend=True)
        karte.innen.grid_rowconfigure(0, weight=1)
        karte.innen.grid_columnconfigure(0, weight=1)
        self._huelle = karte
        self._look = look
        self._rolle = rolle
        self._vsb = None
        self._hsb = None
        return karte

    def _einsetzen(self) -> None:
        tk.Grid.grid_configure(self, row=0, column=0, sticky="nsew")

    def rollbalken_innen(self, achse: str) -> ttk.Scrollbar:
        """Der Balken dieser Achse in der Karte - angelegt beim ersten Mal."""
        senkrecht = achse == "vertical"
        vorhanden = self._vsb if senkrecht else self._hsb
        if vorhanden is not None:
            return vorhanden
        karte = self._huelle
        stil = "%s.%s.TScrollbar" % (_ROLLBALKEN_PRAEFIX.get(self._rolle, "Karte"),
                                     "Vertical" if senkrecht else "Horizontal")
        befehl = self.yview if senkrecht else self.xview
        balken = ttk.Scrollbar(karte.innen, orient=achse, command=befehl, style=stil)
        if senkrecht:
            balken.grid(row=0, column=1, sticky="ns", padx=(4, 0))
            self._vsb = balken
        else:
            balken.grid(row=1, column=0, sticky="ew", pady=(4, 0))
            self._hsb = balken
        return balken


class Text(_MitKarte, tk.Text):
    """Ersatz fuer ``tk.Text``: ein echtes Textfeld in einer runden Karte (Protokolle, Berichte)."""

    _FARBEN = ("relief", "bd", "borderwidth", "highlightthickness", "highlightbackground", "highlightcolor",
               "bg", "background")

    def __init__(self, master, look: FensterLook, **opt: Any) -> None:
        rolle = look.rolle_fuer(opt.get("bg") or opt.get("background"), standard="console_bg",
                                rollen=("console_bg", "bg_card", "bg_main"))
        for name in self._FARBEN:
            opt.pop(name, None)
        karte = self._karte_bauen(master, look, rolle)
        p = look.z.palette
        opt.setdefault("fg", p["fg_primary"])
        opt.setdefault("insertbackground", p["fg_primary"])
        opt.setdefault("selectbackground", p["accent_btn"])
        opt.setdefault("padx", 4)
        opt.setdefault("pady", 2)
        # Ein tk.Text ohne Hoehe will 24 Zeilen - in einem Fenster mit Protokoll machte das den Platzbedarf
        # riesig (App direkt installieren: 1120 Punkte). Mit expand fuellt es den Rest ohnehin aus.
        opt.setdefault("height", 10)
        tk.Text.__init__(self, karte.innen, relief="flat", bd=0, highlightthickness=0, bg=p[rolle], **opt)
        self._einsetzen()


class Treeview(_MitKarte, ttk.Treeview):
    """Ersatz fuer ``ttk.Treeview``: die Tabelle in einer runden Karte."""

    def __init__(self, master, look: FensterLook, **opt: Any) -> None:
        stil = str(opt.get("style") or "Treeview")
        try:
            feld = ttk.Style().lookup(stil, "fieldbackground") or ttk.Style().lookup(stil, "background")
        except tk.TclError:
            feld = ""
        rolle = look.rolle_fuer(feld, standard="bg_card", rollen=("bg_card", "console_bg", "bg_main"))
        karte = self._karte_bauen(master, look, rolle)
        ttk.Treeview.__init__(self, karte.innen, **opt)
        self._einsetzen()


class LabelFrame(_Huelle, tk.Frame):
    """Ersatz fuer ``tk.LabelFrame``: eine runde Umrisskarte mit der Ueberschrift darueber.

    Die Kinder entstehen im Inneren und tragen weiter die Farbe, die sie vom LabelFrame kannten
    (die Karte hat die Fuellung der Flaeche, auf der sie steht - nur der Rand ist rund und sichtbar).
    ``pack``/``grid`` gehen an den aeusseren Rahmen mit Ueberschrift und Karte.
    """

    def __init__(self, master, look: FensterLook, text: str = "", font=None, fg=None, bg=None,
                 **_legacy: Any) -> None:
        z = look.z
        p = z.palette
        grund_rolle = look.rolle_fuer(bg, standard=look.grund_von(master)) if bg else look.grund_von(master)
        aussen = tk.Frame(master, bg=look.farbe_von(master))
        if text:
            tk.Label(aussen, text=text, font=font or z.schrift_angabe("klein_fett"),
                     fg=fg or p["fg_accent"], bg=look.farbe_von(master), anchor="w").pack(
                         fill="x", padx=z.px(6), pady=(0, z.px(3)))
        karte = raster.RundeKarte(aussen, z, fuellung=grund_rolle, rand="border", grund=look.grund_von(master),
                                  radius=look.g._KARTEN_ECKE, polster=(2, 2))
        karte.pack(fill="both", expand=True)
        tk.Frame.__init__(self, karte.innen, bg=p[grund_rolle], bd=0, highlightthickness=0)
        tk.Pack.pack_configure(self, fill="both", expand=True)
        self._huelle = aussen
        self._look = look


class Karte(_Huelle, tk.Frame):
    """Ersatz fuer einen ``tk.Frame`` in Kartenfarbe (``bg_card``/``console_bg``) auf dem Fensterhintergrund.

    Eine runde Karte mit Rand; die Kinder entstehen darin. ``padx``/``pady`` sind der Abstand zwischen Rand
    und Inhalt. Steht der Rahmen schon auf einer Flaeche derselben Farbe (eine Zeile *in* einer Karte), ist er
    nur ein Rahmen - das macht :meth:`Widgets.Karte`; eine Karte in der Karte waere ein Kasten im Kasten.
    """

    def __init__(self, master, look: FensterLook, rolle: str, padx: int = 0, pady: int = 0, **legacy: Any) -> None:
        z = look.z
        p = z.palette
        for name in ("bd", "borderwidth", "highlightthickness", "highlightbackground", "highlightcolor", "relief",
                     "cursor", "bg", "background"):
            legacy.pop(name, None)
        karte = raster.RundeKarte(master, z, fuellung=rolle, rand="border", grund=look.grund_von(master),
                                  radius=look.g._KARTEN_ECKE, polster=(max(6, int(padx)), max(4, int(pady))))
        tk.Frame.__init__(self, karte.innen, bg=p[rolle], bd=0, highlightthickness=0, **legacy)
        tk.Pack.pack_configure(self, fill="both", expand=True)
        self._huelle = karte
        self._look = look


class Listbox(_MitKarte, tk.Listbox):
    """Ersatz fuer ``tk.Listbox``: die Liste in einer runden Karte."""

    _FARBEN = ("relief", "bd", "borderwidth", "highlightthickness", "highlightbackground", "highlightcolor",
               "bg", "background")

    def __init__(self, master, look: FensterLook, **opt: Any) -> None:
        rolle = look.rolle_fuer(opt.get("bg") or opt.get("background"), standard="console_bg",
                                rollen=("console_bg", "bg_card", "bg_main"))
        for name in self._FARBEN:
            opt.pop(name, None)
        karte = self._karte_bauen(master, look, rolle)
        p = look.z.palette
        opt.setdefault("fg", p["fg_primary"])
        opt.setdefault("selectbackground", p["accent_btn"])
        opt.setdefault("selectforeground", "#ffffff")
        opt.setdefault("activestyle", "none")
        tk.Listbox.__init__(self, karte.innen, relief="flat", bd=0, highlightthickness=0, bg=p[rolle], **opt)
        self._einsetzen()


# ---------------------------------------------------------------------------
# Balken
# ---------------------------------------------------------------------------

class Progressbar(bausteine.FortschrittsPille):
    """Ersatz fuer ``ttk.Progressbar``: ein Balken mit runden Enden.

    Versteht ``maximum``, ``value`` (auch ``balken["value"] = x``), ``variable`` und ``mode``.
    ``indeterminate`` laeuft als wandernder Abschnitt zwischen ``start()`` und ``stop()``.
    """

    def __init__(self, master, look: FensterLook, orient: str = "horizontal", length: "int | None" = None,
                 mode: str = "determinate", maximum: float = 100.0, value: float = 0.0,
                 variable: "tk.Variable | None" = None, **_legacy: Any) -> None:
        self._maximum = float(maximum) or 100.0
        self._modus = str(mode)
        self._variable = variable
        self._lauf: "str | None" = None
        self._phase = 0.0
        super().__init__(master, look.z, grund=look.grund_von(master), hoehe=12,
                         breite=(length / look.z.faktor) if length else 220)
        self._spur = None
        if variable is not None:
            self._spur = variable.trace_add("write", self._aus_variable)
            self._aus_variable()
        elif value:
            self.configure(value=value)
        self.bind("<Destroy>", self._weg, add="+")

    def _weg(self, ereignis: Any) -> None:
        if ereignis.widget is not self:
            return
        self.stop()
        if self._variable is not None and self._spur is not None:
            try:
                self._variable.trace_remove("write", self._spur)
            except (tk.TclError, ValueError):
                pass

    def _aus_variable(self, *_a: Any) -> None:
        try:
            wert = float(self._variable.get())
        except (tk.TclError, ValueError, AttributeError):
            wert = 0.0
        self.setzen(100.0 * wert / self._maximum)

    def configure(self, cnf: Any = None, **kwargs: Any) -> Any:  # noqa: A003 - bewusst tk-kompatibel
        if cnf:
            kwargs = dict(cnf, **kwargs)
        if "maximum" in kwargs:
            self._maximum = float(kwargs.pop("maximum")) or 100.0
        if "mode" in kwargs:
            self._modus = str(kwargs.pop("mode"))
        if "value" in kwargs:
            wert = float(kwargs.pop("value"))
            self.setzen(100.0 * wert / self._maximum)
        if "variable" in kwargs:
            self._variable = kwargs.pop("variable")
        for name in ("orient", "length", "style", "takefocus", "phase"):
            kwargs.pop(name, None)
        if kwargs:
            tk.Canvas.configure(self, **kwargs)

    config = configure

    def cget(self, key: str) -> Any:
        if key == "value":
            return self._wert * self._maximum / 100.0
        if key == "maximum":
            return self._maximum
        if key == "mode":
            return self._modus
        return super().cget(key)

    def __setitem__(self, key: str, wert: Any) -> None:
        self.configure(**{key: wert})

    def __getitem__(self, key: str) -> Any:
        return self.cget(key)

    def step(self, menge: float = 1.0) -> None:
        self.configure(value=min(self._maximum, self.cget("value") + float(menge)))

    # --- unbestimmt ----------------------------------------------------------------
    def start(self, intervall: int = 50) -> None:
        """Startet den wandernden Abschnitt (``mode="indeterminate"``)."""
        if self._lauf is not None:
            return
        self._wandern(max(20, int(intervall)))

    def _wandern(self, intervall: int) -> None:
        try:
            if not self.winfo_exists():
                self._lauf = None
                return
        except tk.TclError:
            self._lauf = None
            return
        self._phase = (self._phase + 3.0) % 130.0
        self._zeichnen_wandernd()
        self._lauf = self.after(intervall, self._wandern, intervall)

    def stop(self) -> None:
        if self._lauf is not None:
            try:
                self.after_cancel(self._lauf)
            except tk.TclError:
                pass
            self._lauf = None
        self._phase = 0.0
        try:
            self._zeichnen()
        except tk.TclError:
            pass

    def _zeichnen_wandernd(self) -> None:
        from PIL import ImageTk  # noqa: PLC0415
        try:
            b, h = int(self.winfo_width()), int(self.winfo_height())
        except tk.TclError:
            return
        if b < 6 or h < 4:
            return
        p = self._z.palette
        faktor = max(1.0, self._z.faktor)
        bild = zeichnen.rund_rechteck(b, h, h / 2.0, p["console_bg"], p["border"], faktor)
        rand = max(2, int(round(2 * faktor)))
        innen_h = max(2, h - 2 * rand)
        breite = max(innen_h, int((b - 2 * rand) * 0.3))
        start = int((b - 2 * rand + breite) * (self._phase / 130.0)) - breite
        links = str(p["accent_btn"])
        stueck = zeichnen.verlauf_rechteck(breite, innen_h, innen_h / 2.0, links,
                                           zeichnen.farbton_verschieben(links, 32.0))
        x0 = max(0, start)
        x1 = min(b - 2 * rand, start + breite)
        if x1 > x0:
            bild.alpha_composite(stueck.crop((x0 - start, 0, x1 - start, innen_h)), (rand + x0, rand))
        self._foto = ImageTk.PhotoImage(bild, master=self)
        self.delete("all")
        self.create_image(0, 0, image=self._foto, anchor="nw")


class Scale(tk.Canvas):
    """Ersatz fuer ``ttk.Scale`` (waagerecht): eine Rinne als Pille mit rundem Griff.

    Versteht ``from_``, ``to``, ``command`` (mit dem neuen Wert, wie ttk), ``get``, ``set`` und
    ``configure(to=..., command=...)``; Klick und Ziehen setzen den Wert, Pfeiltasten verschieben ihn um
    ein Hundertstel des Bereichs. ``<ButtonRelease>`` und ``<KeyRelease>`` bindet die Aufrufstelle wie bisher.
    """

    def __init__(self, master, look: FensterLook, from_: float = 0.0, to: float = 100.0, orient: str = "horizontal",
                 command: "Callable | None" = None, variable: "tk.Variable | None" = None, value: "float | None" = None,
                 length: "int | None" = None, **_legacy: Any) -> None:
        self._look = look
        self._von, self._bis = float(from_), float(to)
        self._wert = float(value) if value is not None else self._von
        self._befehl = command
        self._variable = variable
        self._foto = None
        self._zieht = False
        z = look.z
        super().__init__(master, bg=look.farbe_von(master), bd=0, highlightthickness=0, takefocus=1, cursor="hand2",
                         height=z.px(26), width=length or z.px(220))
        if variable is not None:
            try:
                self._wert = float(variable.get())
            except (tk.TclError, ValueError):
                pass
        self.bind("<Configure>", lambda _e: self._zeichnen(), add="+")
        self.bind("<Button-1>", self._zeiger, add="+")
        self.bind("<B1-Motion>", self._zeiger, add="+")
        self.bind("<Left>", lambda _e: self._schritt(-1), add="+")
        self.bind("<Right>", lambda _e: self._schritt(1), add="+")
        self.bind("<FocusIn>", lambda _e: self._zeichnen(), add="+")
        self.bind("<FocusOut>", lambda _e: self._zeichnen(), add="+")

    # --- Wert ----------------------------------------------------------------------
    def get(self) -> float:
        return self._wert

    def set(self, wert: Any) -> None:
        """Setzt den Wert (auf den Bereich begrenzt) und ruft - wie ``ttk.Scale.set`` - den Befehl."""
        neu = max(min(self._von, self._bis), min(max(self._von, self._bis), float(wert)))
        if neu == self._wert:
            return
        self._wert = neu
        if self._variable is not None:
            try:
                self._variable.set(neu)
            except tk.TclError:
                pass
        self._zeichnen()
        if self._befehl is not None:
            self._befehl(str(neu))

    def _schritt(self, richtung: int) -> None:
        self.set(self._wert + richtung * (self._bis - self._von) / 100.0)

    def _zeiger(self, ereignis: Any) -> None:
        breite = max(1, int(self.winfo_width()))
        rand = self._griff() // 2 + 2
        anteil = (float(ereignis.x) - rand) / max(1, breite - 2 * rand)
        self.focus_set()
        self.set(self._von + max(0.0, min(1.0, anteil)) * (self._bis - self._von))

    def configure(self, cnf: Any = None, **kwargs: Any) -> Any:  # noqa: A003 - bewusst tk-kompatibel
        if cnf:
            kwargs = dict(cnf, **kwargs)
        neu = False
        if "to" in kwargs:
            self._bis = float(kwargs.pop("to"))
            self._wert = max(min(self._von, self._bis), min(max(self._von, self._bis), self._wert))
            neu = True
        if "from_" in kwargs:
            self._von = float(kwargs.pop("from_"))
            neu = True
        if "command" in kwargs:
            self._befehl = kwargs.pop("command")
        if "value" in kwargs:
            self._wert = float(kwargs.pop("value"))
            neu = True
        for name in ("orient", "style", "length", "variable"):
            kwargs.pop(name, None)
        if kwargs:
            tk.Canvas.configure(self, **kwargs)
        if neu:
            self._zeichnen()

    config = configure

    def cget(self, key: str) -> Any:
        eigene = {"to": self._bis, "from": self._von, "from_": self._von, "value": self._wert}
        if key in eigene:
            return eigene[key]
        return super().cget(key)

    def __setitem__(self, key: str, wert: Any) -> None:
        self.configure(**{key: wert})

    # --- Zeichnen ------------------------------------------------------------------
    def _griff(self) -> int:
        return self._look.z.px(18)

    def _zeichnen(self) -> None:
        from PIL import Image, ImageTk  # noqa: PLC0415
        try:
            b, h = int(self.winfo_width()), int(self.winfo_height())
        except tk.TclError:
            return
        if b < 20 or h < 8:
            return
        z = self._look.z
        p = z.palette
        faktor = max(1.0, z.faktor)
        griff = min(self._griff(), h)
        rinne_h = max(6, z.px(8))
        rand = griff // 2 + 2
        spanne = (self._bis - self._von) or 1.0
        anteil = max(0.0, min(1.0, (self._wert - self._von) / spanne))
        mitte_x = rand + int(round(anteil * (b - 2 * rand)))
        bild = Image.new("RGBA", (b, h), (0, 0, 0, 0))
        oben = (h - rinne_h) // 2
        rinne = zeichnen.rund_rechteck(b - 2 * (rand - griff // 2 + 1), rinne_h, rinne_h / 2.0, p["console_bg"],
                                       p["border"], faktor)
        bild.alpha_composite(rinne, (rand - griff // 2 + 1, oben))
        if mitte_x > rand:
            links = str(p["accent_btn"])
            gefuellt = zeichnen.verlauf_rechteck(max(rinne_h, mitte_x - rand + griff // 2), max(2, rinne_h - 4),
                                                 (rinne_h - 4) / 2.0, links, zeichnen.farbton_verschieben(links, 32.0))
            bild.alpha_composite(gefuellt, (rand - griff // 2 + 2, oben + 2))
        fokus = self.focus_get() is self
        kopf = zeichnen.rund_rechteck(griff, griff, griff / 2.0, p["bg_card"] if not fokus else p["fg_accent"],
                                      p["fg_accent"], faktor)
        bild.alpha_composite(kopf, (mitte_x - griff // 2, (h - griff) // 2))
        self._foto = ImageTk.PhotoImage(bild, master=self)
        self.delete("all")
        self.create_image(0, 0, image=self._foto, anchor="nw")


# ---------------------------------------------------------------------------
# Die Fabrik: so kommt das Hauptprogramm an die Teile
# ---------------------------------------------------------------------------

class Widgets:
    """Die Ersatzteile fuer ein Programm: ``self._pw.Button(master, text=..., command=...)`` usw.

    Die Methoden heissen wie die Klassen von tk und ttk, die sie ersetzen, und nehmen deren
    Optionen. Das Aussehen (``look``) gehoert dem Programm - es folgt dessen Palette.
    """

    def __init__(self, gui, schrift: str, mono: str, pt: Callable[[int], int]) -> None:
        self.g = gui
        self.F = schrift
        self.pt = pt
        self.look = FensterLook(gui, schrift, mono, pt)

    def Button(self, master, **opt: Any) -> Button:
        return Button(master, self.look, **opt)

    def Entry(self, master, **opt: Any) -> Entry:
        return Entry(master, self.look, **opt)

    def Combobox(self, master, **opt: Any) -> Combobox:
        return Combobox(master, self.look, **opt)

    def Radiobutton(self, master, **opt: Any) -> Radiobutton:
        return Radiobutton(master, self.look, **opt)

    def Checkbutton(self, master, text: str = "", variable=None, command=None, font=None, fg=None,
                    **legacy: Any):
        """Der runde Haken des Hauptprogramms - ``state`` und ``wraplength`` werden uebernommen bzw. ignoriert."""
        haken = self.g._runder_haken(master, text, variable, command=command,
                                     schrift=font or (self.F, self.pt(9)), farbe=fg or "fg_primary")
        haken.configure(bg=self.look.farbe_von(master))
        zustand = legacy.get("state")
        if zustand:
            haken.configure(state=zustand)
        return haken

    def Progressbar(self, master, **opt: Any) -> Progressbar:
        return Progressbar(master, self.look, **opt)

    def Text(self, master, **opt: Any) -> Text:
        return Text(master, self.look, **opt)

    def Treeview(self, master, **opt: Any) -> Treeview:
        return Treeview(master, self.look, **opt)

    def Listbox(self, master, **opt: Any) -> Listbox:
        return Listbox(master, self.look, **opt)

    def LabelFrame(self, master, **opt: Any) -> LabelFrame:
        return LabelFrame(master, self.look, **opt)

    def Karte(self, master, bg: "str | None" = None, padx: int = 0, pady: int = 0, **opt: Any):
        """Ein Rahmen in Kartenfarbe: auf dem Fensterhintergrund eine runde Karte, in einer Karte nur ein Rahmen."""
        rolle = self.look.rolle_fuer(bg, standard="bg_card", rollen=("bg_card", "console_bg", "bg_main"))
        if rolle == self.look.grund_von(master):
            return tk.Frame(master, bg=self.look.z.palette[rolle], padx=padx, pady=pady, **{
                k: v for k, v in opt.items() if k not in ("relief", "bd", "borderwidth", "highlightthickness")})
        return Karte(master, self.look, rolle, padx=padx, pady=pady, **opt)

    def Rahmen(self, master, **opt: Any) -> tk.Frame:
        """Ein unsichtbarer Rahmen in der Farbe seines Elternteils (der alte 1-Punkt-Zierrahmen um Tabellen)."""
        return tk.Frame(master, bg=self.look.farbe_von(master), **opt)

    def Scale(self, master, **opt: Any) -> Scale:
        return Scale(master, self.look, **opt)

    def Spinbox(self, master, from_: int = 0, to: int = 9, textvariable: "tk.Variable | None" = None, **_legacy: Any):
        """Ein Drehknopf statt der Spinbox - wie im Hauptfenster (kleine Pfeile sind schwer zu treffen)."""
        if textvariable is None:
            textvariable = tk.IntVar(master=master, value=int(from_))
        return self.g._fenster_drehknopf(master, textvariable, int(from_), int(to),
                                         hintergrund=self.look.farbe_von(master))

    def Scrollbar(self, master, orient: str = "vertical", command=None, style: "str | None" = None, **opt: Any):
        """Ein Rollbalken. Gehoert ``command`` zu einem Widget in einer Karte, steht er in der Karte."""
        ziel = getattr(command, "__self__", None)
        if isinstance(ziel, _MitKarte):
            return _Zwischenhalter(ziel.rollbalken_innen("vertical" if str(orient) == "vertical" else "horizontal"))
        return ttk.Scrollbar(master, orient=orient, command=command,
                             style=style or self.look.rollbalken_stil(master, orient), **opt)
