# -*- coding: utf-8 -*-
"""Runde Bausteine fuer „PS4 PKG -> OTA“ und seine Dialoge.

Das Fenster traegt die Pillenform des Programms (Nutzerwunsch vom 05.10.2026:
„den Inhalt an der neuen Optik anpassen, runde Pillenknoepfe usw.“). Knoepfe,
Chips, Felder, Klapplisten und Karten sind dieselben gezeichneten Teile wie in
der Bibliothek (``bibliothek_raster``, ``bibliothek_zeichnen``) - nur das
Ankreuzfeld kommt vom Hauptprogramm (``gui._runder_haken``), weil es dort
gezeichnet wird.

Was dieses Modul dazutut:

* :class:`FlachZeichner` - der Zeichner der Bibliothek ohne den Schein um den
  Akzentknopf. Der Schein macht den Knopf drei Handbreit hoeher und rueckt ihn
  aus der Zeile; in einer dichten Knopfzeile stoert das (in der Bibliothek hat
  "Starten" genug Luft dafuer).
* :class:`EingabePille` - ein Textfeld als Pille mit Breite in Zeichen (das
  Suchfeld der Bibliothek hat keine) und sichtbarem Fokus.
* :class:`AuswahlPille` - die Klappliste als Pille: zeigt den Wert, ein Klick
  oeffnet ein Menue (so macht es die Bibliothek bei der Sortierung).
* :class:`FortschrittsPille` - ein Balken mit runden Enden.
* :class:`Look` - was Fenster und Dialoge brauchen, mit der Farbe der Flaeche
  darunter von selbst (``grund_von``).

Dieses Modul kennt das Hauptprogramm nicht; es braucht nur ``gui._COLORS`` und
``gui._runder_haken``. Die Texte kommen von den Aufrufern.
"""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from PIL import Image, ImageTk

from ps5_validator.utils import bibliothek_raster as raster
from ps5_validator.utils import bibliothek_zeichnen as zeichnen

logger = logging.getLogger("PS5Converter.ui.ps4_ota_bausteine")

#: Die Rollen der Palette, auf denen die Bausteine stehen koennen.
GRUND_ROLLEN = ("bg_card", "bg_main", "console_bg")


# ---------------------------------------------------------------------------
# Zeichner ohne Schein
# ---------------------------------------------------------------------------

class FlachZeichner(raster.Zeichner):
    """Der Zeichner der Bibliothek, aber der Akzentknopf bleibt eine glatte Pille.

    Mit Schein ragt das Bild des Akzentknopfs ringsum ueber ihn hinaus; der
    Knopf wird dadurch hoeher und breiter als seine Nachbarn und sitzt um
    einige Punkte tiefer (der Schein rutscht nach unten). Hier haelt ``glow_rand``
    null Pixel frei, und das Bild ist nur der Verlauf.
    """

    def knopf_foto(self, stil: str, zustand: str, breite: int, hoehe: int):
        if stil != "akzent":
            return super().knopf_foto(stil, zustand, breite, hoehe)
        farben = zeichnen.knopf_farben(self.palette, "akzent", zustand)
        foto = self.foto(("knopf_flach", zustand, breite, hoehe), lambda: zeichnen.akzent_knopf(
            breite, hoehe, hoehe / 2.0, farben["links"], farben["rechts"], "")[0])
        return foto, (0, 0)

    def glow_versatz(self, zustand: str) -> tuple[int, int]:
        return (0, 0)

    def glow_rand(self, stil: str) -> tuple[int, int, int]:
        return (0, 0, 0)


# ---------------------------------------------------------------------------
# Knoepfe freigeben und sperren
# ---------------------------------------------------------------------------

def freigeben(knopf, an: bool) -> None:
    """Gibt einen Knopf frei oder sperrt ihn - gezeichnet wird nur bei einer Aenderung."""
    wunsch = "normal" if an else "disabled"
    try:
        if str(knopf.cget("state")) != wunsch:
            knopf.configure(state=wunsch)
    except tk.TclError:
        pass


def ist_frei(knopf) -> bool:
    """Ob ein Knopf (``KartenKnopf``, ``AuswahlPille``) bedienbar ist."""
    try:
        return str(knopf.cget("state")) != "disabled"
    except tk.TclError:
        return False


# ---------------------------------------------------------------------------
# Das Menue unter einem Knopf
# ---------------------------------------------------------------------------

def menue_unter(knopf, zeichner: raster.Zeichner, werte: list[str], aktuell: str,
                gewaehlt: Callable[[str], None]) -> None:
    """Oeffnet unter ``knopf`` ein Menue mit ``werte``; ein Klick ruft ``gewaehlt(wert)``.

    Gefuellt und eingefaerbt wird bei jedem Oeffnen - so folgt es Sprache und
    Design ohne eigene Pflege (wie das Sortiermenue der Bibliothek).
    """
    p = zeichner.palette
    menue = tk.Menu(knopf, tearoff=0, bg=p["bg_card"], fg=p["fg_primary"], activebackground=p["accent_btn"],
                    activeforeground="white", selectcolor=p["fg_accent"], font=zeichner.schrift_angabe("knopf"))
    wahl = tk.StringVar(master=knopf, value=aktuell)
    for wert in werte:
        menue.add_radiobutton(label=wert, value=wert, variable=wahl, command=lambda w=wert: gewaehlt(w))
    try:
        menue.tk_popup(knopf.winfo_rootx(), knopf.winfo_rooty() + knopf.winfo_height())
    finally:
        menue.grab_release()


# ---------------------------------------------------------------------------
# Eingabefeld als Pille
# ---------------------------------------------------------------------------

class EingabePille(raster.RundeKarte):
    """Ein Textfeld als Pille - Breite in Zeichen, Rand im Fokus in der Akzentfarbe.

    Wie das Suchfeld der Bibliothek, aber ohne Platzhalter und mit der Breite
    eines ``tk.Entry``: Ein Feld fuer Adresse oder Port soll nicht die ganze
    Zeile fuellen. Wer die Pille mit ``fill="x"`` packt, bekommt trotzdem ein
    breites Feld.

    Args:
        breite: Breite in Zeichen (wie ``tk.Entry(width=...)``).
        luft: Senkrechter Abstand ueber und unter dem Text bei 100 %.
    """

    def __init__(self, master: tk.Misc, zeichner: raster.Zeichner, variable: tk.Variable, breite: int = 20,
                 *, grund: str = "bg_card", luft: float = 4.0) -> None:
        super().__init__(master, zeichner, fuellung="console_bg", rand="border", grund=grund, radius=None,
                         polster=(14, 3))
        p = zeichner.palette
        self.variable = variable
        self._fokus_an = False
        self.eingabe = tk.Entry(self.innen, textvariable=variable, width=int(breite), relief="flat", bd=0,
                                highlightthickness=0, bg=p["console_bg"], fg=p["fg_primary"],
                                insertbackground=p["fg_primary"], selectbackground=p["accent_btn"],
                                selectforeground="#ffffff", disabledbackground=p["console_bg"],
                                disabledforeground=p["fg_secondary"], readonlybackground=p["console_bg"],
                                font=zeichner.schrift_angabe("eingabe"))
        self.eingabe.pack(fill="x", expand=True, ipady=zeichner.px(luft))
        self.eingabe.bind("<FocusIn>", lambda _e: self._fokus_setzen(True), add="+")
        self.eingabe.bind("<FocusOut>", lambda _e: self._fokus_setzen(False), add="+")

    def _fokus_setzen(self, an: bool) -> None:
        """Im Fokus zeichnet die Pille ihren Rand in der Akzentfarbe - so sieht man, wo man tippt."""
        if an == self._fokus_an:
            return
        self._fokus_an = an
        fuellung, _rand, grund = self._rollen
        self._rollen = (fuellung, "fg_accent" if an else "border", grund)
        try:
            self._bild_neu()
        except tk.TclError:
            pass

    @property
    def hat_fokus(self) -> bool:
        return self._fokus_an

    def neu_faerben(self) -> None:
        super().neu_faerben()
        p = self._z.palette
        try:
            self.eingabe.configure(bg=p["console_bg"], fg=p["fg_primary"], insertbackground=p["fg_primary"],
                                   selectbackground=p["accent_btn"])
        except tk.TclError:
            pass


# ---------------------------------------------------------------------------
# Klappliste als Pille
# ---------------------------------------------------------------------------

class AuswahlPille(raster.KartenKnopf):
    """Eine Klappliste als Pille: zeigt den gewaehlten Wert, ein Klick oeffnet das Menue.

    Haengt an einer ``tk.StringVar`` - wer sie von aussen setzt, sieht die
    Pille mitziehen. Die Breite folgt dem **laengsten** Wert, nicht dem
    gewaehlten: Sonst huepfte die Zeile bei jeder Wahl.

    Args:
        werte: Die Auswahl (Texte). ``werte_setzen`` tauscht sie spaeter aus.
        befehl: Wird nach einer Wahl gerufen, wenn die Variable gesetzt ist.
        mindestbreite: Untergrenze der Breite bei 100 %.
    """

    def __init__(self, master: tk.Misc, zeichner: raster.Zeichner, variable: tk.StringVar, werte: list,
                 befehl: "Callable[[], None] | None" = None, *, grund: str = "bg_card", hoehe: float = 30,
                 mindestbreite: float = 110) -> None:
        self._variable = variable
        self._werte = [str(w) for w in werte]
        self._befehl = befehl
        self._mindestbreite = mindestbreite
        super().__init__(master, zeichner, str(variable.get()), command=self._menue_zeigen, stil="auswahl",
                         grund=grund, breite=self._breite_fuer(zeichner, self._werte, mindestbreite), hoehe=hoehe,
                         chevron=True)
        self._spur = variable.trace_add("write", self._nachziehen)
        self.bind("<Destroy>", self._weg, add="+")

    @staticmethod
    def _breite_fuer(zeichner: raster.Zeichner, werte: list, mindest: float) -> int:
        text = max((zeichner.messen("knopf", w) for w in werte), default=0)
        return max(zeichner.px(mindest), text + zeichner.px(48))

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

    def _menue_zeigen(self) -> None:
        menue_unter(self, self._z, self._werte, str(self._variable.get()), self.waehlen)

    def waehlen(self, wert: str) -> None:
        """Setzt die Auswahl (wie ein Klick im Menue) und ruft ``befehl``."""
        if str(self._variable.get()) != wert:
            self._variable.set(wert)
        if self._befehl is not None:
            self._befehl()

    @property
    def werte(self) -> list[str]:
        return list(self._werte)

    def werte_setzen(self, werte: list) -> None:
        """Tauscht die Auswahl aus (die Regionen kommen erst nach dem Einlesen)."""
        self._werte = [str(w) for w in werte]
        self._breite_fest = self._breite_fuer(self._z, self._werte, self._mindestbreite)
        self._groesse_setzen()
        self._zeichnen()


# ---------------------------------------------------------------------------
# Fortschrittsbalken mit runden Enden
# ---------------------------------------------------------------------------

class FortschrittsPille(tk.Canvas):
    """Ein Balken mit runden Enden: Rinne und Fuellung als Pille, Fuellung mit Verlauf.

    ``setzen(prozent)`` nimmt 0 bis 100; ausserhalb wird abgeschnitten. Die
    Fuellung ist nie schmaler als ihre eigene Rundung - ein Balken auf einem
    Prozent soll nicht als Strich aus dem Rand ragen.
    """

    def __init__(self, master: tk.Misc, zeichner: raster.Zeichner, *, grund: str = "bg_card", hoehe: float = 12,
                 breite: float = 220) -> None:
        self._z = zeichner
        self._grund = grund
        self._wert = 0.0
        self._foto = None
        super().__init__(master, bg=zeichner.palette.get(grund, "#000000"), bd=0, highlightthickness=0,
                         height=zeichner.px(hoehe), width=zeichner.px(breite))
        self.bind("<Configure>", lambda _e: self._zeichnen(), add="+")

    @property
    def wert(self) -> float:
        return self._wert

    def setzen(self, prozent: float) -> None:
        try:
            neu = max(0.0, min(100.0, float(prozent)))
        except (TypeError, ValueError):
            neu = 0.0
        if neu == self._wert:
            return
        self._wert = neu
        self._zeichnen()

    def neu_faerben(self) -> None:
        try:
            tk.Canvas.configure(self, bg=self._z.palette.get(self._grund, "#000000"))
        except tk.TclError:
            return
        self._zeichnen()

    def _zeichnen(self) -> None:
        try:
            b, h = int(self.winfo_width()), int(self.winfo_height())
        except tk.TclError:
            return
        if b < 6 or h < 4:
            return
        p = self._z.palette
        faktor = max(1.0, self._z.faktor)
        bild = zeichnen.rund_rechteck(b, h, h / 2.0, p["console_bg"], p["border"], faktor)
        if self._wert > 0:
            rand = max(2, int(round(2 * faktor)))
            innen_h = max(2, h - 2 * rand)
            innen_b = max(innen_h, int(round((b - 2 * rand) * self._wert / 100.0)))
            links = str(p["accent_btn"])
            fuellung = zeichnen.verlauf_rechteck(innen_b, innen_h, innen_h / 2.0, links,
                                                 zeichnen.farbton_verschieben(links, 32.0))
            bild.alpha_composite(fuellung, (rand, rand))
        self._foto = ImageTk.PhotoImage(bild, master=self)
        self.delete("all")
        self.create_image(0, 0, image=self._foto, anchor="nw")


# ---------------------------------------------------------------------------
# Das Aussehen als Ganzes
# ---------------------------------------------------------------------------

class Look:
    """Baut die runden Teile fuer ein Fenster - auf der Farbe, auf der sie stehen.

    Args:
        gui: Das Hauptprogramm (``_COLORS``, ``_KARTEN_ECKE``, ``_runder_haken``).
        schrift: Name der Oberflaechenschrift.
        mono: Name der Festbreitenschrift.
        pt: ``(punkte) -> punkte`` des Programms.
    """

    def __init__(self, gui, schrift: str, mono: str, pt: Callable[[int], int]) -> None:
        self.g = gui
        self.F = schrift
        self.M = mono
        self.pt = pt
        self.z = FlachZeichner(gui.root, lambda: gui._COLORS, schrift, pt)

    @classmethod
    def gemeinsam(cls, gui, schrift: str, mono: str, pt: Callable[[int], int]) -> "Look":
        """Das Aussehen dieses Programms - einmal gebaut und von allen Fenstern geteilt.

        Ein ``Look`` bringt einen eigenen Zeichner mit, und der haelt bis zu 600 Tk-Bilder. Hatte jedes
        Fenster seinen eigenen, blieben die Bilder nach dem Schliessen stehen, solange irgendein Rueckruf das
        Fenster hielt (gemessen am 05.10.2026: 69 Tk-Bilder und 93 GDI-Objekte je geschlossenem Fenster).
        Das Hauptprogramm haelt eines fuer alle (``gui._pw.look``, siehe ``fenster_pillen``); ohne das legt
        diese Methode eines an und merkt es sich.
        """
        teile = getattr(gui, "_pw", None)
        vorhanden = getattr(teile, "look", None)
        if isinstance(vorhanden, Look):
            return vorhanden
        eigenes = gui.__dict__.get("_look_gemeinsam")
        if not isinstance(eigenes, Look):
            eigenes = gui.__dict__["_look_gemeinsam"] = cls(gui, schrift, mono, pt)
        return eigenes

    # --- Farben ---------------------------------------------------------------
    @property
    def c(self) -> dict:
        return self.z.palette

    def hintergrund(self, widget) -> str:
        """Die Hintergrundfarbe eines Elternteils - fuer Beschriftungen, die auf ihm stehen."""
        try:
            return str(widget.cget("bg"))
        except tk.TclError:
            return str(self.c.get("bg_card", "#000000"))

    def grund_von(self, widget) -> str:
        """Die Rolle der Palette, deren Farbe ``widget`` traegt (``bg_card`` ohne Treffer)."""
        farbe = self.hintergrund(widget).lower()
        for rolle in GRUND_ROLLEN:
            if str(self.c.get(rolle, "")).lower() == farbe:
                return rolle
        return "bg_card"

    # --- Flaechen ---------------------------------------------------------------
    def karte(self, eltern, fuellung: str = "bg_card", polster: tuple = (14, 10), *,
              fuellend: bool = False) -> raster.RundeKarte:
        """Eine runde Flaeche; die Widgets kommen in ``karte.innen``."""
        return raster.RundeKarte(eltern, self.z, fuellung=fuellung, rand="border", grund=self.grund_von(eltern),
                                 radius=self.g._KARTEN_ECKE, polster=polster, fuellend=fuellend)

    def fluss(self, eltern, abstand: tuple = (8, 6)) -> raster.FlussZeile:
        """Eine Zeile, die umbricht, wenn die Breite nicht reicht - ihre Kinder gehoeren ihr."""
        return raster.FlussZeile(eltern, self.z, grund=self.grund_von(eltern), abstand=abstand)

    def baumrahmen(self, eltern, hoehe: int = 110) -> tk.Frame:
        """Ein Rahmen fuer eine Tabelle, der seine Groesse **nicht** von ihr borgt.

        Eine ``ttk.Treeview`` mit dehnbaren Spalten weitet beim ersten Zeichnen
        ihre Spalten auf die zugeteilte Breite, und ihre angeforderte Breite ist
        danach genau diese. Das Fenster hielt das fuer Platzbedarf und wuchs von
        1260 auf 1580 Punkte (gemessen am 05.10.2026). Mit ``pack_propagate(False)``
        bleibt der Rahmen bei der kleinen Wunschgroesse, und die Tabelle fuellt
        ihn trotzdem.
        """
        rahmen = tk.Frame(eltern, bg=self.hintergrund(eltern), width=100, height=self.z.px(hoehe))
        rahmen.pack_propagate(False)
        return rahmen

    # --- Knoepfe und Felder ---------------------------------------------------------
    def knopf(self, eltern, text: str, befehl, *, akzent: bool = False, chevron: bool = False, fett: bool = False,
              hoehe: float = 30, breite: "int | None" = None) -> raster.KartenKnopf:
        """Ein Knopf als Pille; ``akzent`` ist der Hauptknopf (Verlauf, ohne Schein)."""
        return raster.KartenKnopf(eltern, self.z, text, befehl, "akzent" if akzent else "flaeche",
                                  grund=self.grund_von(eltern), breite=breite, hoehe=hoehe, chevron=chevron,
                                  fett=fett or akzent)

    def chips(self, eltern, optionen: list, variable: tk.StringVar, befehl=None, *,
              hoehe: float = 28) -> raster.ChipGruppe:
        """Eine Reihe Chips, von denen genau einer gewaehlt ist (Reiter, Zielart)."""
        return raster.ChipGruppe(eltern, self.z, optionen, variable, befehl=befehl,
                                 grund=self.grund_von(eltern), hoehe=hoehe)

    def eingabe(self, eltern, variable: tk.Variable, breite: int = 20, *, luft: float = 4.0) -> EingabePille:
        return EingabePille(eltern, self.z, variable, breite, grund=self.grund_von(eltern), luft=luft)

    def suche(self, eltern, variable: tk.StringVar, platzhalter: str) -> raster.SuchFeld:
        """Das Suchfeld der Bibliothek (mit Platzhalter)."""
        return raster.SuchFeld(eltern, self.z, variable, platzhalter, grund=self.grund_von(eltern))

    def auswahl(self, eltern, variable: tk.StringVar, werte: list, befehl=None, *,
                hoehe: float = 30, mindestbreite: float = 110) -> AuswahlPille:
        return AuswahlPille(eltern, self.z, variable, werte, befehl, grund=self.grund_von(eltern), hoehe=hoehe,
                            mindestbreite=mindestbreite)

    def menue_knopf(self, eltern, text: str, werte_holen: Callable[[], list], gewaehlt: Callable[[str], None], *,
                    hoehe: float = 30, breite: "int | None" = None) -> raster.KartenKnopf:
        """Ein Knopf mit Pfeil, der unter sich ein Menue mit ``werte_holen()`` oeffnet."""
        knopf = raster.KartenKnopf(eltern, self.z, text, None, "auswahl", grund=self.grund_von(eltern),
                                   breite=breite or (self.z.messen("knopf", text) + self.z.px(48)), hoehe=hoehe,
                                   chevron=True)
        knopf.configure(command=lambda: menue_unter(knopf, self.z, [str(w) for w in werte_holen()], "", gewaehlt))
        return knopf

    def haken(self, eltern, text: str, variable: tk.BooleanVar, *, command=None, farbe: str = "fg_primary"):
        """Ein Ankreuzfeld in Pillenform (gezeichnet vom Hauptprogramm)."""
        return self.g._runder_haken(eltern, text, variable, command=command, schrift=(self.F, self.pt(9)), farbe=farbe)

    def balken(self, eltern, *, breite: float = 220, hoehe: float = 12) -> FortschrittsPille:
        return FortschrittsPille(eltern, self.z, grund=self.grund_von(eltern), hoehe=hoehe, breite=breite)

    def rollbalken(self, eltern, orient: str, befehl, *, tief: bool = False) -> ttk.Scrollbar:
        """Ein schmaler Rollbalken ohne Pfeile, mit der Rinne in der Farbe der Flaeche.

        ``tief``: fuer Flaechen in der Farbe des Status-Logs (``console_bg``). Waagerecht
        gibt es ihn nur fuer die Kartenfarbe.
        """
        senkrecht = orient == "vertical"
        stil = ("Tief" if tief and senkrecht else "Karte") + (".Vertical" if senkrecht else ".Horizontal") + ".TScrollbar"
        return ttk.Scrollbar(eltern, orient=orient, command=befehl, style=stil)

    # --- Texte -----------------------------------------------------------------------------
    def beschriftung(self, eltern, text: str = "", *, farbe: str = "fg_secondary", groesse: int = 9,
                     fett: bool = False, **kw) -> tk.Label:
        schrift = (self.F, self.pt(groesse), "bold") if fett else (self.F, self.pt(groesse))
        optionen = dict(text=text, font=schrift, bg=self.hintergrund(eltern), fg=self.c.get(farbe, farbe), anchor="w")
        optionen.update(kw)
        return tk.Label(eltern, **optionen)

    def hinweis(self, eltern, text: str, farbe: "str | None" = None) -> tk.Label:
        """Ein kleiner Text, der mit der Breite umbricht."""
        beschriftung = tk.Label(eltern, text=text, font=(self.F, self.pt(8)), bg=self.hintergrund(eltern),
                                fg=self.c.get(farbe or "fg_secondary", farbe), anchor="w", justify="left",
                                wraplength=700)
        beschriftung.bind("<Configure>", lambda e: beschriftung.configure(wraplength=max(120, e.width - 8)))
        return beschriftung
