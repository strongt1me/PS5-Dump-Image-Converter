# -*- coding: utf-8 -*-
"""Die gezeichneten Teile der Bibliothek mit Tk: Knoepfe, Chips und das Kartenraster.

Die Bibliothek zeigt ihre Titel als Karten mit allen Knoepfen darin
(Infos & Metadaten, Starten, Kopieren, Konvertieren). Dieses Modul zeichnet sie.
Es kennt weder das Hauptprogramm noch die Konsole: Palette, Schrift und Texte
kommen als Rueckrufe herein, was ein Knopf tut, geht als Rueckruf hinaus. So
laesst sich alles mit einem verborgenen Tk-Fenster pruefen
(``test_bibliothek_raster.py``).

**Warum eine Zeichenflaeche und keine Widgets.** Jede Karte waere ein Dutzend
Widgets (Rahmen, Bild, Titel, Chips, vier Knoepfe); bei zweihundert Titeln
verlangsamt das Rasterlayout und das Rollen spuerbar. Auf einer Zeichenflaeche
ist eine Karte eine Handvoll Bilder und Texte, die Tk beim Rollen ohne jede
Layoutarbeit verschiebt. Dazu kommt: Eine Karte mit runden Ecken ist hier ein
RGBA-Bild, dessen Ecken durchsichtig sind - Tk legt es auf die Flaeche dahinter,
und die Ecken muessen nicht wissen, was dort liegt (Hintergrundbild, Farbe).
Treffer, Hover und Druck rechnet das Raster selbst nach (Rechtecke), nicht ueber
Tk-Ereignisse einzelner Elemente.

Fuer die Kopfleiste (wenige Knoepfe, Suchfeld) gibt es ``KartenKnopf`` als eigenes
Widget mit derselben Zeichnung: ein Canvas, der genau einen Knopf zeigt.
"""
from __future__ import annotations

import os
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from collections import OrderedDict
from dataclasses import dataclass, field
from tkinter import ttk
from typing import Any, Callable

from PIL import Image, ImageTk

from ps5_validator.utils import bibliothek_zeichnen as zeichnen
from ps5_validator.utils.bibliothek_fortschritt import Drossel, Phasen, Stand

def _rad_einheiten_vorgabe(ereignis: Any) -> int:
    """Rolleinheiten fuer ein Mausrad-Ereignis, wenn der Aufrufer keine eigene Regel mitgibt."""
    delta = int(getattr(ereignis, "delta", 0) or 0)
    if delta == 0:
        return 0
    schritte = max(1, abs(delta) // 120)
    return -3 * schritte if delta > 0 else 3 * schritte


#: Marke fuer "den sichtbaren Bereich der Flaeche noch erfragen" (``None`` heisst dort: nicht gemessen).
_ERFRAGEN = object()

#: Die Rollen der Palette, an denen ein gezeichnetes Bild haengt. Aendert sich
#: eine, sind alle zwischengespeicherten Bilder alt - sie stehen im Schluessel.
_PALETTE_ROLLEN = ("bg_main", "bg_card", "console_bg", "border", "fg_primary", "fg_secondary", "fg_accent",
                   "accent_btn", "fg_success", "fg_warning")


# ---------------------------------------------------------------------------
# Zeichner: gemeinsamer Zustand
# ---------------------------------------------------------------------------

class Zeichner:
    """Palette, Masse, Schriften und Bildspeicher - eine Instanz je Programmlauf.

    Args:
        wurzel: Ein Tk-Widget (nur fuer ``tk scaling``, Schriften und Fotos).
        palette: ``() -> dict`` - die aktive Palette. Jedes Mal frisch gelesen,
            damit ein Designwechsel von selbst ankommt.
        familie: Name der Oberflaechenschrift.
        pt: ``(punkte) -> punkte`` - die Punktgroessen-Umrechnung des Programms
            (unter macOS angehoben, sonst unveraendert).
    """

    #: Punktgroessen und Gewicht je Schriftrolle.
    SCHRIFTEN: dict[str, tuple[int, str]] = {
        "titel": (11, "bold"), "chip": (8, "bold"), "plakette": (8, "bold"),
        "knopf": (10, "normal"), "knopf_fett": (10, "bold"), "klein": (9, "normal"),
        "klein_fett": (9, "bold"), "kopf_titel": (14, "bold"), "kopf_unter": (9, "normal"),
        "eingabe": (10, "normal"), "filter": (9, "bold"),
    }

    def __init__(self, wurzel: tk.Misc, palette: Callable[[], dict], familie: str,
                 pt: Callable[[float], float] | None = None) -> None:
        self.wurzel = wurzel
        self._palette = palette
        self.familie = familie
        self._pt = pt or (lambda p: p)
        self._schriften: dict[str, tkfont.Font] = {}
        self._fotos: dict[tuple, Any] = {}
        self._poster: OrderedDict[tuple, tuple[Any, int]] = OrderedDict()
        self._poster_bytes = 0
        self._faktor: float | None = None

    # --- Masse ---------------------------------------------------------------------------------------
    @property
    def palette(self) -> dict:
        return self._palette()

    @property
    def faktor(self) -> float:
        """Anzeigeskalierung gegenueber 100 % (96 dpi): 1.0, bei 125 % rund 1.25.

        Einmal gemessen und gemerkt - ``tk scaling`` aendert sich nach dem Start
        nicht, und jede Pixelrechnung der Karten fragt danach. ``neu_messen``
        liest es noch einmal (Tests, die die Skalierung umstellen).
        """
        if self._faktor is None:
            try:
                self._faktor = max(0.5, float(self.wurzel.tk.call("tk", "scaling")) / (96.0 / 72.0))
            except (tk.TclError, ValueError, AttributeError):
                self._faktor = 1.0
        return self._faktor

    def neu_messen(self) -> None:
        self._faktor = None
        self.leeren()
        self.poster_leeren()

    def px(self, wert: float) -> int:
        return int(round(wert * self.faktor))

    # --- Schriften -------------------------------------------------------------------------------------
    def schrift_angabe(self, rolle: str) -> tuple:
        groesse, gewicht = self.SCHRIFTEN[rolle]
        return (self.familie, int(self._pt(groesse)), gewicht)

    def schrift(self, rolle: str) -> tkfont.Font:
        vorhanden = self._schriften.get(rolle)
        if vorhanden is None:
            vorhanden = tkfont.Font(root=self.wurzel, font=self.schrift_angabe(rolle))
            self._schriften[rolle] = vorhanden
        return vorhanden

    def messen(self, rolle: str, text: str) -> int:
        return int(self.schrift(rolle).measure(text))

    def zeilenhoehe(self, rolle: str) -> int:
        return int(self.schrift(rolle).metrics("linespace"))

    # --- Fotos -----------------------------------------------------------------------------------------
    def _farben_schluessel(self) -> tuple:
        palette = self.palette
        return tuple(str(palette.get(rolle, "")) for rolle in _PALETTE_ROLLEN)

    def foto(self, schluessel: tuple, erzeuger: Callable[[], "Image.Image"]) -> "ImageTk.PhotoImage":
        """Ein Tk-Foto aus dem Bildspeicher - gebaut, wenn es fehlt.

        Der Schluessel bekommt die Palette angehaengt; nach einem Designwechsel
        trifft deshalb kein altes Bild mehr, und der Speicher wird bei Bedarf
        geleert (``leeren``).
        """
        voll = (schluessel, self._farben_schluessel())
        foto = self._fotos.get(voll)
        if foto is None:
            if len(self._fotos) > 600:                  # Sicherung gegen unbegrenztes Wachstum
                self._fotos.clear()
            foto = ImageTk.PhotoImage(erzeuger(), master=self.wurzel)
            self._fotos[voll] = foto
        return foto

    def leeren(self) -> None:
        """Verwirft alle gemerkten Fotos (Designwechsel, Skalierung) - ausser den Titelbildern."""
        self._fotos.clear()

    # --- Titelbilder -------------------------------------------------------------------------------------
    #: Obergrenze fuer fertige Titelbilder im Bildspeicher (Byte). Ein Titelbild einer Karte
    #: ist rund 0,4 MB gross; die Grenze haelt rund 150 davon - mehr braucht kein Bildschirm.
    POSTER_SPEICHER = 64 * 2 ** 20

    def poster_foto(self, datei: str, breite: int, hoehe: int, radius: float) -> "ImageTk.PhotoImage | None":
        """Das fertige Titelbild einer Karte aus dem Bildspeicher - gebaut, wenn es fehlt.

        Filtern, Sortieren und Rollen zeichnen dieselben Karten immer wieder; ohne
        Speicher hiesse das jedes Mal Datei lesen, entpacken, verkleinern und
        runden (rund 10 ms je Karte). Der Schluessel enthaelt Aenderungszeit und
        Groesse der Datei, damit ein unter demselben Namen neu geladenes
        Titelbild das alte nicht trifft. Palettenunabhaengig: Ein Designwechsel
        laesst die Titelbilder stehen.

        Returns:
            Das Foto - oder ``None``, wenn sich die Datei nicht lesen laesst
            ("kein Titelbild"). Der Speicher ist nach Bytes begrenzt, die
            aeltesten Bilder gehen zuerst.
        """
        try:
            stand = os.stat(datei)
        except OSError:
            return None
        schluessel = (str(datei), stand.st_mtime_ns, stand.st_size, int(breite), int(hoehe), float(radius))
        treffer = self._poster.get(schluessel)
        if treffer is not None:
            self._poster.move_to_end(schluessel)
            return treffer[0]
        try:
            with Image.open(datei) as quelle:
                quelle.load()
                bild = zeichnen.poster_bild(quelle, breite, hoehe, radius)
            foto = ImageTk.PhotoImage(bild, master=self.wurzel)
        except Exception:                               # noqa: BLE001 - kaputte Datei: wie "kein Bild"
            return None
        groesse = bild.width * bild.height * 4
        self._poster[schluessel] = (foto, groesse)
        self._poster_bytes += groesse
        while self._poster_bytes > self.POSTER_SPEICHER and len(self._poster) > 1:
            _alt, (_foto, alt_groesse) = self._poster.popitem(last=False)
            self._poster_bytes -= alt_groesse
        return foto

    def poster_leeren(self) -> None:
        """Verwirft alle gemerkten Titelbilder (neue Skalierung: alle Groessen sind alt)."""
        self._poster.clear()
        self._poster_bytes = 0

    # --- Knopfbilder -------------------------------------------------------------------------------------
    def knopf_foto(self, stil: str, zustand: str, breite: int, hoehe: int) -> tuple["ImageTk.PhotoImage", tuple[int, int]]:
        """Das Bild eines Knopfs und der Versatz seines Rechtecks darin (wegen des Scheins)."""
        farben = zeichnen.knopf_farben(self.palette, stil, zustand)
        radius = hoehe / 2.0 if stil in ("chip", "chip_an") else self.px(10)
        schluessel = ("knopf", stil, zustand, breite, hoehe)
        if stil == "akzent":
            foto = self.foto(schluessel, lambda: zeichnen.akzent_knopf(
                breite, hoehe, radius, farben["links"], farben["rechts"], farben["glow"],
                glow_unschaerfe=self.px(7), glow_versatz=self.px(4))[0])
            return foto, self.glow_versatz(zustand)
        foto = self.foto(schluessel, lambda: zeichnen.rund_rechteck(
            breite, hoehe, radius, farben["fuellung"], farben["rand"], max(1.0, self.faktor)))
        return foto, (0, 0)

    def glow_versatz(self, zustand: str) -> tuple[int, int]:
        """Wo das Rechteck des Akzentknopfs in seinem Bild sitzt - ohne das Bild zu bauen.

        Rechnet dieselben Zahlen wie ``bibliothek_zeichnen.akzent_knopf``
        (Rand um den Knopf = zweifache Unschaerfe; oben um den Versatz weniger,
        weil der Schein nach unten rutscht). Ohne Schein (gesperrt, gedrueckt)
        ist das Bild so gross wie der Knopf.
        """
        if not zeichnen.knopf_farben(self.palette, "akzent", zustand)["glow"]:
            return (0, 0)
        pad = 2 * self.px(7)
        return (pad, max(0, pad - self.px(4)))

    def glow_rand(self, stil: str) -> tuple[int, int, int]:
        """Wie weit der Schein ueber den Knopf hinausragt: ``(links/rechts, oben, unten)``."""
        if stil != "akzent":
            return (0, 0, 0)
        pad = 2 * self.px(7)
        versatz = self.px(4)
        return (pad, max(0, pad - versatz), pad + versatz)


# ---------------------------------------------------------------------------
# Ein Knopf auf einer Zeichenflaeche
# ---------------------------------------------------------------------------

@dataclass
class KnopfSpec:
    """Was ein Knopf zeigt: Name, Beschriftung, Stil und ob er greift."""

    name: str
    text: str
    stil: str = "flaeche"          # akzent | flaeche | auswahl | chip | chip_an
    aktiv: bool = True
    chevron: bool = False
    fett: bool = False


@dataclass
class GezeichneterKnopf:
    """Die Tk-Elemente eines gezeichneten Knopfs - und sein Rechteck auf der Flaeche."""

    spec: KnopfSpec
    x: int
    y: int
    b: int
    h: int
    bild: int = 0
    text: int = 0
    chevron: int = 0
    zustand: str = "normal"
    fotos: dict = field(default_factory=dict)       # haelt Referenzen am Leben

    def enthaelt(self, px_: float, py_: float) -> bool:
        return self.x <= px_ < self.x + self.b and self.y <= py_ < self.y + self.h


def knopf_zeichnen(flaeche: tk.Canvas, zeichner: Zeichner, spec: KnopfSpec, x: int, y: int, b: int, h: int,
                   tags: tuple = (), zustand: str = "") -> GezeichneterKnopf:
    """Zeichnet einen Knopf auf ``flaeche`` - Bild, Beschriftung und gegebenenfalls Pfeil.

    ``zustand`` leer waehlt ``gesperrt`` (nicht aktiv) oder ``normal``.
    """
    if not zustand:
        zustand = "normal" if spec.aktiv else "gesperrt"
    knopf = GezeichneterKnopf(spec=spec, x=int(x), y=int(y), b=int(b), h=int(h), zustand=zustand)
    foto, (ox, oy) = zeichner.knopf_foto(spec.stil, zustand, int(b), int(h))
    knopf.fotos["bild"] = foto
    knopf.bild = flaeche.create_image(int(x) - ox, int(y) - oy, image=foto, anchor="nw", tags=tags)
    farben = zeichnen.knopf_farben(zeichner.palette, spec.stil, zustand)
    rolle = "knopf_fett" if spec.fett or spec.stil == "akzent" else "knopf"
    if spec.stil in ("chip", "chip_an"):
        rolle = "filter"
    schrift = zeichner.schrift_angabe(rolle)
    # Text auf einer Zeichenflaeche wird nie abgeschnitten: Was nicht in den Knopf passt (schmale
    # Karte, breitere Schrift unter Linux/macOS, andere Sprache), ragte sonst ueber seinen Rand hinaus.
    frei = int(b) - (zeichner.px(44) if spec.chevron else 2 * zeichner.px(8))
    text = _passend(zeichner, rolle, spec.text, frei)
    if spec.chevron:
        luft = zeichner.px(12)
        groesse = zeichner.px(14)
        cv = zeichner.foto(("chevron", groesse, farben["text"]),
                           lambda: zeichnen.chevron(groesse, farben["text"], max(1.4, 1.6 * zeichner.faktor)))
        knopf.fotos["chevron"] = cv
        knopf.chevron = flaeche.create_image(int(x + b - luft - groesse / 2.0), int(y + h / 2.0), image=cv,
                                             anchor="center", tags=tags)
        knopf.text = flaeche.create_text(int(x + luft), int(y + h / 2.0), text=text, anchor="w",
                                         fill=farben["text"], font=schrift, tags=tags)
    else:
        knopf.text = flaeche.create_text(int(x + b / 2.0), int(y + h / 2.0), text=text, anchor="center",
                                         fill=farben["text"], font=schrift, tags=tags)
    return knopf


def _passend(zeichner: Zeichner, rolle: str, text: str, breite: int) -> str:
    """``text`` auf eine Zeile von hoechstens ``breite`` Pixeln gekuerzt - mit ``…``, wenn er nicht passt."""
    text = str(text or "")
    if breite <= 0 or zeichner.messen(rolle, text) <= breite:
        return text
    zeilen = zeichnen.text_umbrechen(text, lambda t: zeichner.messen(rolle, t), breite, 1)
    return zeilen[0] if zeilen else text


def knopf_umfaerben(flaeche: tk.Canvas, zeichner: Zeichner, knopf: GezeichneterKnopf, zustand: str) -> None:
    """Setzt Bild und Textfarbe eines gezeichneten Knopfs auf einen neuen Zustand."""
    if knopf.zustand == zustand:
        return
    knopf.zustand = zustand
    spec = knopf.spec
    foto, (ox, oy) = zeichner.knopf_foto(spec.stil, zustand, knopf.b, knopf.h)
    knopf.fotos["bild"] = foto
    farben = zeichnen.knopf_farben(zeichner.palette, spec.stil, zustand)
    try:
        flaeche.itemconfigure(knopf.bild, image=foto)
        flaeche.coords(knopf.bild, knopf.x - ox, knopf.y - oy)
        flaeche.itemconfigure(knopf.text, fill=farben["text"])
        if knopf.chevron:
            groesse = zeichner.px(14)
            cv = zeichner.foto(("chevron", groesse, farben["text"]),
                               lambda: zeichnen.chevron(groesse, farben["text"], max(1.4, 1.6 * zeichner.faktor)))
            knopf.fotos["chevron"] = cv
            flaeche.itemconfigure(knopf.chevron, image=cv)
    except tk.TclError:
        pass


# ---------------------------------------------------------------------------
# Ein Knopf als Widget (Kopfleiste, Streifen unter der Liste)
# ---------------------------------------------------------------------------

class KartenKnopf(tk.Canvas):
    """Ein gezeichneter Knopf als eigenes Widget - dieselbe Zeichnung wie auf den Karten.

    Versteht ``configure(text=, command=, state=, an=)``, ``invoke()`` und
    ``cget("text")``; ``state`` ist ``normal`` oder ``disabled``. Chips sind
    Umschalter: ``an`` zeigt sie gewaehlt (``stil="chip"``). Mit der Tastatur
    erreichbar (Tab, Leertaste, Eingabe) und mit sichtbarem Fokusring.

    Args:
        grund: Rolle der Palette, auf der der Knopf steht (z. B. ``bg_card``) -
            der Canvas faerbt sich damit; beim Designwechsel ``neu_faerben``.
        breite: Breite in Pixeln, oder ``None`` fuer "so breit wie der Text".
        hoehe: Hoehe in Pixeln (vor der Skalierung, 100 %), oder ``None``.
    """

    def __init__(self, master: tk.Misc, zeichner: Zeichner, text: str = "", command: Callable | None = None,
                 stil: str = "flaeche", *, grund: str = "bg_card", breite: int | None = None,
                 hoehe: float | None = None, chevron: bool = False, fett: bool = False, an: bool = False,
                 state: str = "normal", gesperrt_befehl: Callable | None = None, **kwargs: Any) -> None:
        self._z = zeichner
        self._text = text
        self._command = command
        #: Ein gesperrter Knopf tut nichts - aber die Seite darf sagen, warum (Klick darauf).
        self._gesperrt_befehl = gesperrt_befehl
        self._gesperrt_gedrueckt = False
        self._basis_stil = stil
        self._an = bool(an)
        self._chevron = chevron
        self._fett = fett
        self._state = state
        self._grund = grund
        self._breite_fest = breite
        self._hoehe_pt = hoehe if hoehe is not None else (30 if stil in ("chip", "chip_an") else 34)
        self._hover = False
        self._gedrueckt = False
        self._fokus = False
        self._knopf: GezeichneterKnopf | None = None
        kwargs.setdefault("takefocus", 1)
        super().__init__(master, bd=0, highlightthickness=0, bg=self._z.palette.get(grund, "#000000"),
                         cursor="hand2", **kwargs)
        self._groesse_setzen()
        self.bind("<Enter>", self._betreten, add="+")
        self.bind("<Leave>", self._verlassen, add="+")
        self.bind("<ButtonPress-1>", self._druecken, add="+")
        self.bind("<ButtonRelease-1>", self._loslassen, add="+")
        self.bind("<FocusIn>", self._fokus_ein, add="+")
        self.bind("<FocusOut>", self._fokus_aus, add="+")
        self.bind("<space>", self._taste, add="+")
        self.bind("<Return>", self._taste, add="+")
        self._zeichnen()

    # --- Masse -----------------------------------------------------------------------------------------
    @property
    def stil(self) -> str:
        return "chip_an" if (self._basis_stil == "chip" and self._an) else self._basis_stil

    def _knopf_masse(self) -> tuple[int, int]:
        z = self._z
        h = z.px(self._hoehe_pt)
        if self._breite_fest is not None:
            return int(self._breite_fest), h
        rolle = "filter" if self._basis_stil in ("chip", "chip_an") else (
            "knopf_fett" if self._fett or self._basis_stil == "akzent" else "knopf")
        luft = z.px(16 if self._basis_stil in ("chip", "chip_an") else 18)
        extra = z.px(26) if self._chevron else 0
        return z.messen(rolle, self._text) + 2 * luft + extra, h

    def _groesse_setzen(self) -> None:
        b, h = self._knopf_masse()
        links, oben, unten = self._z.glow_rand(self.stil)
        self._b, self._h = b, h
        self._rand = (links, oben, unten)
        tk.Canvas.configure(self, width=b + 2 * links, height=h + oben + unten)

    # --- Zeichnen --------------------------------------------------------------------------------------
    def _zustand(self) -> str:
        if self._state == "disabled":
            return "gesperrt"
        if self._gedrueckt:
            return "gedrueckt"
        if self._hover:
            return "hover"
        return "normal"

    def _zeichnen(self) -> None:
        self.delete("all")
        links, oben, _unten = self._rand
        spec = KnopfSpec(name="knopf", text=self._text, stil=self.stil, aktiv=self._state != "disabled",
                         chevron=self._chevron, fett=self._fett)
        try:
            self._knopf = knopf_zeichnen(self, self._z, spec, links, oben, self._b, self._h,
                                         zustand=self._zustand())
            if self._fokus and self._state != "disabled":
                ring = self._z.palette.get("fg_accent", "#7fb2ff")
                self.create_line(links + 3, oben + self._h - 2, links + self._b - 3, oben + self._h - 2,
                                 fill=ring, width=max(1, int(self._z.faktor)))
        except tk.TclError:
            pass
        tk.Canvas.configure(self, cursor="arrow" if self._state == "disabled" else "hand2")

    def neu_faerben(self) -> None:
        """Nach einem Designwechsel: Grund und Zeichnung neu."""
        try:
            tk.Canvas.configure(self, bg=self._z.palette.get(self._grund, "#000000"))
        except tk.TclError:
            return
        self._groesse_setzen()
        self._zeichnen()

    # --- Ereignisse ------------------------------------------------------------------------------------
    def _betreten(self, _e: Any = None) -> None:
        self._hover = True
        self._zeichnen()

    def _verlassen(self, _e: Any = None) -> None:
        self._hover = False
        self._gedrueckt = False
        self._zeichnen()

    def _druecken(self, _e: Any = None) -> None:
        if self._state == "disabled":
            self._gesperrt_gedrueckt = True
            return
        self._gedrueckt = True
        self._zeichnen()

    def _innen(self, e: Any) -> bool:
        return e is None or (0 <= getattr(e, "x", 0) < int(self.winfo_width() or 1)
                             and 0 <= getattr(e, "y", 0) < int(self.winfo_height() or 1))

    def _loslassen(self, e: Any = None) -> None:
        war_gedrueckt, war_gesperrt = self._gedrueckt, self._gesperrt_gedrueckt
        self._gedrueckt = False
        self._gesperrt_gedrueckt = False
        self._zeichnen()
        if war_gesperrt and self._state == "disabled" and self._innen(e):
            if self._gesperrt_befehl is not None:
                self._gesperrt_befehl()
            return
        if not war_gedrueckt or self._state == "disabled":
            return
        if self._innen(e):
            self.invoke()

    def _fokus_ein(self, _e: Any = None) -> None:
        self._fokus = True
        self._zeichnen()

    def _fokus_aus(self, _e: Any = None) -> None:
        self._fokus = False
        self._zeichnen()

    def _taste(self, _e: Any = None) -> str:
        self.invoke()
        return "break"

    # --- Schnittstelle ---------------------------------------------------------------------------------
    def invoke(self) -> None:
        """Loest den Knopf aus - wie ein Klick; ein gesperrter tut nichts."""
        if self._state != "disabled" and self._command is not None:
            self._command()

    def configure(self, cnf: Any = None, **kwargs: Any) -> Any:  # noqa: A003 - bewusst tk-kompatibel
        if cnf:
            kwargs = dict(cnf, **kwargs)
        neu = False
        if "text" in kwargs:
            self._text = str(kwargs.pop("text"))
            neu = True
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if "state" in kwargs:
            self._state = "disabled" if str(kwargs.pop("state")) == "disabled" else "normal"
            neu = True
        if "an" in kwargs:
            self._an = bool(kwargs.pop("an"))
            neu = True
        if "bg" in kwargs:                              # Aufrufer aus dem Altbestand - die Rolle zaehlt
            kwargs.pop("bg")
        if "fg" in kwargs:
            kwargs.pop("fg")
        if kwargs:
            tk.Canvas.configure(self, **kwargs)
        if neu:
            self._groesse_setzen()
            self._zeichnen()
        return None

    config = configure

    def cget(self, key: str) -> Any:
        if key == "text":
            return self._text
        if key == "state":
            return self._state
        return super().cget(key)

    def __getitem__(self, key: str) -> Any:
        return self.cget(key)

    @property
    def an(self) -> bool:
        return self._an

    def diagnose_beschriftung(self) -> str:
        """Die Beschriftung - ein Canvas hat keine ``text``-Option (Darstellungspruefung)."""
        return " ".join(str(self._text or "").split())

    def diagnose_wunschmass(self) -> tuple[int, int]:
        """Wie gross der Knopf fuer seine Beschriftung sein muesste (Darstellungspruefung)."""
        z = self._z
        rolle = "filter" if self._basis_stil in ("chip", "chip_an") else (
            "knopf_fett" if self._fett or self._basis_stil == "akzent" else "knopf")
        extra = z.px(26) if self._chevron else 0
        return z.messen(rolle, self._text) + 2 * z.px(6) + extra, z.zeilenhoehe(rolle) + 4


class ChipGruppe(tk.Frame):
    """Eine Reihe von Chips, von denen genau einer gewaehlt ist (Filter, Quelle, Ansicht).

    Haengt an einer ``tk.StringVar``: Wer sie von aussen setzt, bewegt die
    Auswahl mit - und umgekehrt ruft ein Klick ``befehl`` auf, nachdem die
    Variable gesetzt ist.

    Args:
        optionen: ``[(wert, text), ...]`` von links nach rechts; ``text`` darf
            ein Rueckruf ``() -> str`` sein (Sprachwechsel).
    """

    def __init__(self, master: tk.Misc, zeichner: Zeichner, optionen: list, variable: tk.StringVar,
                 befehl: Callable | None = None, *, grund: str = "bg_card", abstand: int = 6,
                 hoehe: float = 30) -> None:
        super().__init__(master, bg=zeichner.palette.get(grund, "#000000"), bd=0, highlightthickness=0)
        self._z = zeichner
        self._variable = variable
        self._befehl = befehl
        self._grund = grund
        self._chips: list[tuple[str, Any, KartenKnopf]] = []
        for nummer, (wert, text) in enumerate(optionen):
            chip = KartenKnopf(self, zeichner, text() if callable(text) else text,
                               command=lambda w=wert: self._gewaehlt(w), stil="chip", grund=grund, hoehe=hoehe)
            chip.pack(side="left", padx=(0 if nummer == 0 else zeichner.px(abstand), 0))
            self._chips.append((wert, text, chip))
        variable.trace_add("write", self._nachziehen)
        self._nachziehen()

    def _gewaehlt(self, wert: str) -> None:
        if self._variable.get() != wert:
            self._variable.set(wert)
        if self._befehl is not None:
            self._befehl()

    def _nachziehen(self, *_a: Any) -> None:
        try:
            aktuell = self._variable.get()
            for wert, _text, chip in self._chips:
                chip.configure(an=(wert == aktuell))
        except tk.TclError:
            pass

    def beschriften(self) -> None:
        """Nach einem Sprachwechsel: die Texte neu holen."""
        for _wert, text, chip in self._chips:
            if callable(text):
                chip.configure(text=text())

    def neu_faerben(self) -> None:
        try:
            tk.Frame.configure(self, bg=self._z.palette.get(self._grund, "#000000"))
        except tk.TclError:
            return
        for _wert, _text, chip in self._chips:
            chip.neu_faerben()

    @property
    def chips(self) -> list:
        return [chip for _w, _t, chip in self._chips]


# ---------------------------------------------------------------------------
# Runde Flaeche mit echten Widgets darin, umbrechende Zeile, Suchfeld
# ---------------------------------------------------------------------------

class RundeKarte(tk.Frame):
    """Eine abgerundete Flaeche, in die echte Widgets gelegt werden (``innen``).

    Tk kennt keine runden Ecken. Hinter dem Inhalt liegt ein Label mit dem Bild
    der Karte (Fuellung, Rand, durchsichtige Ecken); ``innen`` liegt davor. Die
    Karte ist ein gewoehnlicher Rahmen: Ihre Hoehe folgt dem Inhalt von selbst
    (eine Zeile bricht um, die Karte waechst mit), ihre Breite der Umgebung.

    Das Bild ist ein RGBA-Bild, dessen Ecken durchsichtig sind - das Label
    zeigt dort seine eigene Farbe, und die ist der Grund, auf dem die Karte
    steht. Die Ecken muessen so nicht wissen, was hinter der Karte liegt.

    Eine Karte, deren Inhalt ein Fenster auf einer Zeichenflaeche waere, haette
    das nicht: Ein Fenster ausserhalb des sichtbaren Bereichs bekommt kein
    Groessenereignis, die Karte bliebe eine Zeile hoch (am 03.10.2026 so
    gesehen, die Kopfkarte fehlte).

    Args:
        fuellung, rand, grund: Rollen der Palette - Kartenflaeche, Rand und
            der Grund, auf dem die Karte steht.
        radius: Eckenradius bei 100 %.
        polster: ``(waagerecht, senkrecht)`` bei 100 % zwischen Rand und Inhalt.
        fuellend: Der Inhalt fuellt die Karte aus (Liste) und gibt ihr keine
            eigene Hoehe vor.
    """

    def __init__(self, master: tk.Misc, zeichner: Zeichner, *, fuellung: str = "bg_card", rand: str = "border",
                 grund: str = "bg_main", radius: float = 16, polster: tuple[float, float] = (20, 16),
                 randbreite: float = 1.0, fuellend: bool = False, **kwargs: Any) -> None:
        self._z = zeichner
        self._rollen = (fuellung, rand, grund)
        self._radius, self._polster, self._randbreite = radius, polster, randbreite
        self._fuellend = bool(fuellend)
        palette = zeichner.palette
        super().__init__(master, bg=palette.get(grund, "#000000"), bd=0, highlightthickness=0, **kwargs)
        self._hintergrund = tk.Label(self, bd=0, highlightthickness=0, padx=0, pady=0,
                                     bg=palette.get(grund, "#000000"))
        self._hintergrund.place(x=0, y=0, relwidth=1.0, relheight=1.0)
        self.innen = tk.Frame(self, bg=palette.get(fuellung, "#000000"), bd=0, highlightthickness=0)
        self.innen.pack(fill="both", expand=True, padx=zeichner.px(polster[0]), pady=zeichner.px(polster[1]))
        self._foto: Any = None
        self._groesse_gemalt = (0, 0)
        self._nach: str | None = None
        self.bind("<Configure>", self._groesse, add="+")

    def _groesse(self, e: Any) -> None:
        if (int(e.width), int(e.height)) != self._groesse_gemalt and self._nach is None:
            self._nach = self.after_idle(self._bild_neu)

    def _bild_neu(self) -> None:
        self._nach = None
        try:
            breite, hoehe = int(self.winfo_width()), int(self.winfo_height())
        except tk.TclError:
            return
        if breite < 4 or hoehe < 4:
            return
        p = self._z.palette
        fuellung, rand, _grund = self._rollen
        bild = zeichnen.rund_rechteck(breite, hoehe, self._z.px(self._radius), p.get(fuellung, "#000000"),
                                      p.get(rand, "#000000"), max(1.0, self._randbreite * self._z.faktor))
        self._foto = ImageTk.PhotoImage(bild, master=self._z.wurzel)
        self._groesse_gemalt = (breite, hoehe)
        try:
            self._hintergrund.configure(image=self._foto)
        except tk.TclError:
            pass

    def neu_faerben(self) -> None:
        """Nach einem Designwechsel: Grund, Fuellung und Bild in den neuen Farben."""
        p = self._z.palette
        fuellung, _rand, grund = self._rollen
        try:
            tk.Frame.configure(self, bg=p.get(grund, "#000000"))
            self._hintergrund.configure(bg=p.get(grund, "#000000"))
            self.innen.configure(bg=p.get(fuellung, "#000000"))
        except tk.TclError:
            return
        self._bild_neu()


class FlussZeile(tk.Frame):
    """Ordnet Kinder nebeneinander an und bricht um, wenn die Breite nicht reicht.

    ``pack`` quetscht bei zu wenig Platz die zuletzt gepackten Widgets, bis ihr
    Text abgeschnitten ist - genau das darf auf der Kopfleiste nicht
    geschehen, deren Breite an Fenstergroesse, Skalierung und Sprache haengt.
    Die Kinder gehoeren dieser Zeile (``master=zeile``) und werden mit ``place``
    gesetzt; die Zeile meldet ihre Hoehe selbst.

    * ``flex``: das Kind waechst, bis die Zeile voll ist (Suchfeld); als
      Mindestbreite gilt ``min_breite``.
    * ``rechts``: das Kind sitzt am rechten Rand seiner Zeile.
    """

    def __init__(self, master: tk.Misc, zeichner: Zeichner, *, grund: str = "bg_card",
                 abstand: tuple[float, float] = (12, 8)) -> None:
        super().__init__(master, bg=zeichner.palette.get(grund, "#000000"), bd=0, highlightthickness=0, height=1)
        self._z = zeichner
        self._grund = grund
        self._abstand = abstand
        self._kinder: list[dict] = []
        self._letzte = (0, ())
        self.bind("<Configure>", self._verteilen, add="+")

    def hinzufuegen(self, widget: tk.Misc, *, flex: bool = False, rechts: bool = False,
                    min_breite: float = 0) -> None:
        self._kinder.append({"w": widget, "flex": flex, "rechts": rechts, "min": min_breite})
        widget.bind("<Configure>", self._kind_geaendert, add="+")

    def _kind_geaendert(self, _e: Any = None) -> None:
        self.after_idle(self._verteilen)

    def neu_verteilen(self) -> None:
        self._letzte = (0, ())
        self._verteilen()

    def neu_faerben(self) -> None:
        try:
            tk.Frame.configure(self, bg=self._z.palette.get(self._grund, "#000000"))
        except tk.TclError:
            pass

    def _verteilen(self, _e: Any = None) -> None:
        try:
            breite = int(self.winfo_width())
        except tk.TclError:
            return
        if breite <= 1:
            return
        sichtbar = [k for k in self._kinder if k["w"].winfo_exists()]
        masse = tuple((k["w"].winfo_reqwidth(), k["w"].winfo_reqheight()) for k in sichtbar)
        if self._letzte == (breite, masse):
            return
        self._letzte = (breite, masse)
        hluft, vluft = self._z.px(self._abstand[0]), self._z.px(self._abstand[1])
        zeilen: list[list[dict]] = [[]]
        benutzt = 0
        for k in sichtbar:
            b = max(int(self._z.px(k["min"])), 1) if k["flex"] else int(k["w"].winfo_reqwidth())
            noetig = b if not zeilen[-1] else hluft + b
            if zeilen[-1] and benutzt + noetig > breite:
                zeilen.append([])
                benutzt, noetig = 0, b
            zeilen[-1].append(k)
            benutzt += noetig
        y = 0
        for zeile in zeilen:
            hoehe = max((int(k["w"].winfo_reqheight()) for k in zeile), default=0)
            breiten = {id(k): (max(int(self._z.px(k["min"])), 1) if k["flex"] else int(k["w"].winfo_reqwidth()))
                       for k in zeile}
            rest = breite - sum(breiten.values()) - hluft * (len(zeile) - 1)
            flex = [k for k in zeile if k["flex"]]
            if flex and rest > 0:
                zusatz = rest // len(flex)
                for k in flex:
                    breiten[id(k)] += zusatz
            links = [k for k in zeile if not k["rechts"]]
            rechts = [k for k in zeile if k["rechts"]]
            x = 0
            for k in links:
                self._setzen(k, x, y, breiten[id(k)], hoehe)
                x += breiten[id(k)] + hluft
            x = breite
            for k in reversed(rechts):
                x -= breiten[id(k)]
                self._setzen(k, x, y, breiten[id(k)], hoehe)
                x -= hluft
            y += hoehe + vluft
        gesamt = max(1, y - vluft)
        try:
            if int(float(self.cget("height"))) != gesamt:
                tk.Frame.configure(self, height=gesamt)
        except tk.TclError:
            pass

    @staticmethod
    def _setzen(kind: dict, x: int, y: int, breite: int, zeilenhoehe: int) -> None:
        widget = kind["w"]
        hoehe = int(widget.winfo_reqheight())
        try:
            if kind["flex"]:
                widget.place(x=x, y=y + max(0, (zeilenhoehe - hoehe) // 2), width=breite)
            else:
                widget.place(x=x, y=y + max(0, (zeilenhoehe - hoehe) // 2))
        except tk.TclError:
            pass


class SuchFeld(RundeKarte):
    """Das Suchfeld: eine runde, vertiefte Flaeche mit einem Eingabefeld und einem Platzhalter.

    Der Platzhalter ist ein Label ueber dem Feld, kein Text im Feld: So steht in
    der ``StringVar`` immer nur, was der Anwender getippt hat, und die Suche
    muss nichts ausfiltern.
    """

    def __init__(self, master: tk.Misc, zeichner: Zeichner, variable: tk.StringVar, platzhalter: str,
                 *, grund: str = "bg_card") -> None:
        super().__init__(master, zeichner, fuellung="console_bg", rand="border", grund=grund, radius=10,
                         polster=(14, 6))
        p = zeichner.palette
        self.variable = variable
        self._platzhalter_text = platzhalter
        self.eingabe = tk.Entry(self.innen, textvariable=variable, relief="flat", bd=0, highlightthickness=0,
                                bg=p.get("console_bg", "#000000"), fg=p.get("fg_primary", "#ffffff"),
                                insertbackground=p.get("fg_primary", "#ffffff"),
                                selectbackground=p.get("accent_btn", "#2e6be6"), selectforeground="#ffffff",
                                font=zeichner.schrift_angabe("eingabe"))
        self.eingabe.pack(fill="x", expand=True, ipady=zeichner.px(6))
        self._platz = tk.Label(self.innen, text=platzhalter, bg=p.get("console_bg", "#000000"),
                               fg=p.get("fg_secondary", "#9a9ca6"), font=zeichner.schrift_angabe("eingabe"),
                               bd=0, padx=0, anchor="w", cursor="xterm")
        self._platz.bind("<Button-1>", self._platzhalter_klick)
        variable.trace_add("write", self._platzhalter_nachziehen)
        self.eingabe.bind("<FocusIn>", self._platzhalter_nachziehen, add="+")
        self.eingabe.bind("<FocusOut>", self._platzhalter_nachziehen, add="+")
        self._platzhalter_nachziehen()

    def _platzhalter_klick(self, _e: Any = None) -> None:
        """Ein Klick auf den Platzhalter gilt dem Feld darunter."""
        self.eingabe.focus_set()

    def _platzhalter_nachziehen(self, *_a: Any) -> None:
        try:
            leer = not self.variable.get()
            if leer:
                self._platz.place(in_=self.eingabe, x=0, y=0, relheight=1.0)
                self._platz.lift()
            else:
                self._platz.place_forget()
        except tk.TclError:
            pass

    def beschriften(self, platzhalter: str) -> None:
        self._platzhalter_text = platzhalter
        try:
            self._platz.configure(text=platzhalter)
        except tk.TclError:
            pass

    def neu_faerben(self) -> None:
        super().neu_faerben()
        p = self._z.palette
        try:
            self.eingabe.configure(bg=p.get("console_bg", "#000000"), fg=p.get("fg_primary", "#ffffff"),
                                   insertbackground=p.get("fg_primary", "#ffffff"),
                                   selectbackground=p.get("accent_btn", "#2e6be6"))
            self._platz.configure(bg=p.get("console_bg", "#000000"), fg=p.get("fg_secondary", "#9a9ca6"))
        except tk.TclError:
            pass


# ---------------------------------------------------------------------------
# Das Kartenraster
# ---------------------------------------------------------------------------

@dataclass
class Karte:
    """Eine Karte des Rasters: ihr Eintrag, ihr Platz und ihre Tk-Elemente."""

    eintrag: dict
    nummer: int
    x: int = 0
    y: int = 0
    b: int = 0
    h: int = 0
    inhalt: dict = field(default_factory=dict)
    knoepfe: list = field(default_factory=list)          # GezeichneterKnopf
    ids: dict = field(default_factory=dict)
    fotos: dict = field(default_factory=dict)
    bilddatei: str = ""                                 # "" = noch kein Bild
    bildzustand: str = "laedt"                          # laedt | da | leer
    poster_da: bool = False                             # das Titelbild ist gebaut (nicht nur sein Platzhalter)
    chip_ids: list = field(default_factory=list)


class PosterFeld:
    """Das Titelbild einer Karte, wie es die Bildlader der Bibliothek ansprechen.

    Die Lader (``_bibliothek_bild_setzen``) kennen nur ``winfo_exists``,
    ``bild_setzen`` und ``ohne_bild`` und die Eigenschaft ``_mini_rueckruf`` -
    nicht die Zeichenflaeche dahinter.
    """

    def __init__(self, raster: "KartenRaster", eintrag: dict) -> None:
        self._raster = raster
        self._eintrag = eintrag
        self._mini_rueckruf = None

    def winfo_exists(self) -> bool:
        return self._raster.lebt() and self._raster.karte_von(self._eintrag) is not None

    def bild_setzen(self, datei: str) -> None:
        self._raster.bild_setzen(self._eintrag, datei)

    def ohne_bild(self) -> None:
        self._raster.bild_setzen(self._eintrag, "")

    def __str__(self) -> str:                           # Schluessel fuer die Foto-Verweise der Lader
        return "poster:%x" % id(self._eintrag)


class KartenRaster:
    """Das Raster der Karten auf einer rollbaren Zeichenflaeche.

    Args:
        eltern: Wohin der Rahmen (Flaeche + Rollbalken) kommt.
        inhalt: ``(eintrag) -> dict`` mit ``titel``, ``plattform`` (``"PS4"``,
            ``"PS5"`` oder ``""``), ``chips`` (``[(text, art), ...]``) und
            ``knoepfe`` (``[KnopfSpec, ...]`` in der Reihenfolge Infos,
            Starten, Kopieren, Konvertieren).
        aktion: ``(name, eintrag)`` - ein Knopf wurde gedrueckt.
        bei_auswahl: ``(eintrag)`` - Klick auf die Karte selbst.
        bei_start: ``(eintrag)`` - Doppelklick auf die Karte.
        bei_gesperrt: ``(name, eintrag)`` - ein gesperrter Knopf wurde gedrueckt
            (die Seite sagt, warum er gesperrt ist).
        symbol: ``(groesse, farbe) -> PIL.Image`` - das Zeichen "kein Titelbild".
        texte: ``(schluessel) -> str`` fuer "laedt ..." und "kein Titelbild"
            (``laedt``, ``ohne_bild``).
        rad: ``(ereignis) -> int`` - Rolleinheiten fuer ein Mausrad-Ereignis.
    """

    #: Abstand zwischen der letzten Kartenspalte und dem Rollbalken (Pixel bei 100 %). So gross wie
    #: der Abstand der Karten untereinander (``KartenMasse.abstand``): Ohne ihn klebte die Spalte am
    #: Balken (Nutzer, 03.10.2026: "etwas mehr Abstand ... vor allem rechts beim Scrollbalken").
    BALKEN_LUECKE = 16

    def __init__(self, zeichner: Zeichner, eltern: tk.Misc, *, inhalt: Callable[[dict], dict],
                 aktion: Callable[[str, dict], None], bei_auswahl: Callable[[dict], None],
                 bei_start: Callable[[dict], None], bei_gesperrt: Callable[[str, dict], None] | None = None,
                 symbol: Callable[[int, str], "Image.Image"] | None = None,
                 texte: Callable[[str], str] | None = None,
                 rad: Callable[[Any], int] | None = None) -> None:
        self._z = zeichner
        self._inhalt = inhalt
        self._aktion = aktion
        self._bei_auswahl = bei_auswahl
        self._bei_start = bei_start
        self._bei_gesperrt = bei_gesperrt
        self._symbol = symbol
        self._texte = texte or (lambda k: {"laedt": "…", "ohne_bild": "–"}.get(k, k))
        self._rad = rad or _rad_einheiten_vorgabe
        palette = zeichner.palette
        self.rahmen = tk.Frame(eltern, bg=palette.get("bg_main", "#000000"))
        self.rahmen.grid_rowconfigure(0, weight=1)
        self.rahmen.grid_columnconfigure(0, weight=1)
        self.flaeche = tk.Canvas(self.rahmen, bg=palette.get("bg_main", "#000000"), highlightthickness=0, bd=0,
                                 takefocus=0)
        self.balken = ttk.Scrollbar(self.rahmen, orient="vertical", command=self.flaeche.yview)
        self.flaeche.configure(yscrollcommand=self._rollt)
        self.flaeche.grid(row=0, column=0, sticky="nsew")
        self.balken.grid(row=0, column=1, sticky="ns", padx=(zeichner.px(self.BALKEN_LUECKE), 0))
        self.karten: list[Karte] = []
        self.spalten = 0
        self.kartenbreite = 0
        self.kartenhoehe = 0
        self.gewaehlt = ""
        self._masse: zeichnen.KartenMasse | None = None
        self._auf: zeichnen.KartenAufteilung | None = None
        self._hover: tuple[Karte, GezeichneterKnopf] | None = None
        self._druck: tuple[Karte, GezeichneterKnopf] | None = None
        self._druck_gesperrt: tuple[Karte, GezeichneterKnopf] | None = None   # Druck auf einen gesperrten Knopf
        self._zeiger = ""                               # der zuletzt gesetzte Mauszeiger der Flaeche
        self._nach: str | None = None
        self._nach_seit = 0.0
        self.flaeche.bind("<Configure>", self._groesse_geaendert, add="+")
        self.flaeche.bind("<Map>", lambda _e: self._posters_nachziehen(), add="+")
        self.flaeche.bind("<ButtonPress-1>", self._gedrueckt, add="+")
        self.flaeche.bind("<ButtonRelease-1>", self._losgelassen, add="+")
        self.flaeche.bind("<Double-Button-1>", self._doppelt, add="+")
        self.flaeche.bind("<Motion>", self._bewegt, add="+")
        self.flaeche.bind("<Leave>", self._verlassen, add="+")
        self.flaeche.bind("<MouseWheel>", self._mausrad, add="+")
        self.flaeche.bind("<Button-4>", lambda _e: self.flaeche.yview_scroll(-3, "units"), add="+")
        self.flaeche.bind("<Button-5>", lambda _e: self.flaeche.yview_scroll(3, "units"), add="+")
        self.rahmen.bind("<Destroy>", self._weg, add="+")

    # --- Lebenszeit ------------------------------------------------------------------------------------
    def lebt(self) -> bool:
        try:
            return bool(self.flaeche.winfo_exists())
        except tk.TclError:
            return False

    def _weg(self, e: Any = None) -> None:
        if e is not None and str(getattr(e, "widget", "")) != str(self.rahmen):
            return
        if self._nach is not None:
            try:
                self.rahmen.after_cancel(self._nach)
            except tk.TclError:
                pass
            self._nach = None

    # --- Masse -----------------------------------------------------------------------------------------
    def rechts_frei(self) -> int:
        """Breite rechts neben den Karten: Luecke plus Rollbalken.

        Kopfkarte, Liste und Streifen der Seite lassen rechts genau so viel frei und
        enden damit an derselben Kante wie die letzte Kartenspalte.
        """
        return int(self.balken.winfo_reqwidth()) + self._z.px(self.BALKEN_LUECKE)

    def _masse_neu(self) -> zeichnen.KartenMasse:
        z = self._z
        chip_h = max(z.px(24), z.zeilenhoehe("chip") + z.px(10))
        return zeichnen.KartenMasse(faktor=z.faktor, titel_zeile=z.zeilenhoehe("titel") + z.px(2),
                                    chip_zeile=chip_h)

    def _layout(self, breite: int) -> tuple[int, int]:
        """Spaltenzahl und Kartenbreite fuer die Flaechenbreite; setzt die Aufteilung."""
        self._masse = self._masse_neu()
        spalten, kb = zeichnen.spalten_berechnen(breite, self._masse.karte_min, self._masse.abstand,
                                                 self._masse.rand)
        self._auf = self._masse.aufteilen(kb)
        return spalten, kb

    # --- Daten -----------------------------------------------------------------------------------------
    def setzen(self, eintraege: list[dict], gewaehlt: str = "") -> int:
        """Zeigt ``eintraege`` als Karten. Gibt die Spaltenzahl zurueck.

        Stellt die Bildverweise der Eintraege her: Jeder Eintrag bekommt
        ``_bildfeld`` (``PosterFeld``) und ``_kachel`` (die Karte). Schon
        geladene Bilder bleiben nicht erhalten - die Bildlader laufen nach
        jedem Setzen noch einmal (aus dem Bildspeicher, ohne Netz).
        """
        if not self.lebt():                             # ein spaeter Suchlauf nach dem Schliessen der Seite
            return 0
        self.gewaehlt = gewaehlt
        alt = {karte.eintrag.get("path"): karte for karte in self.karten}
        self.karten = []
        for nummer, eintrag in enumerate(eintraege):
            karte = Karte(eintrag=eintrag, nummer=nummer)
            vorher = alt.get(eintrag.get("path"))
            if vorher is not None and vorher.bilddatei:
                karte.bilddatei, karte.bildzustand = vorher.bilddatei, vorher.bildzustand
            elif vorher is not None and vorher.bildzustand == "leer":
                karte.bildzustand = "leer"
            self.karten.append(karte)
            eintrag["_bildfeld"] = PosterFeld(self, eintrag)
            eintrag["_kachel"] = karte
        breite = max(1, int(self.flaeche.winfo_width()) if self.flaeche.winfo_width() > 1 else 900)
        self._zeichnen_alles(breite)
        return self.spalten

    def karte_von(self, eintrag: dict) -> Karte | None:
        for karte in self.karten:
            if karte.eintrag is eintrag:
                return karte
        return None

    # --- Zeichnen --------------------------------------------------------------------------------------
    def _gesamtbreite(self) -> int:
        b = int(self.flaeche.winfo_width())
        return b if b > 1 else 900

    #: Wie lange die Flaeche ruhen muss, bevor eine neue Groesse gezeichnet wird (ms), und wie lange
    #: ein Ziehen hoechstens warten darf (s). Beim Ziehen der Fensterkante meldet Tk die Groesse
    #: jeden Pixel; jedes Mal alle Karten neu zu zeichnen, ruckelt - also erst bei einer Pause.
    RUHE_MS = 40
    LAENGSTE_WARTEZEIT = 0.25

    def _groesse_geaendert(self, e: Any) -> None:
        jetzt = time.monotonic()
        if self._nach is not None:
            if jetzt - self._nach_seit >= self.LAENGSTE_WARTEZEIT:
                return                                   # langes Ziehen: das Anstehende laeuft gleich
            try:
                self.rahmen.after_cancel(self._nach)
            except tk.TclError:
                pass
        else:
            self._nach_seit = jetzt
        self._nach = self.rahmen.after(self.RUHE_MS, self._nachziehen)

    def _nachziehen(self) -> None:
        self._nach = None
        if not self.lebt():
            return
        breite = self._gesamtbreite()
        spalten, kb = self._layout(breite)
        if spalten != self.spalten or kb != self.kartenbreite:
            self._zeichnen_alles(breite)
        else:
            self._bereich_setzen(breite)
            self._posters_nachziehen()                   # ein hoeheres Fenster zeigt mehr Karten

    def _bereich_setzen(self, breite: int) -> None:
        """Rollbereich - mindestens so hoch wie die Flaeche, damit kurze Listen nicht rollen."""
        m, a = self._masse, self._auf
        if m is None or a is None:
            return
        zeilen = (len(self.karten) + max(1, self.spalten) - 1) // max(1, self.spalten)
        gesamt = m.rand + zeilen * (a.hoehe + m.abstand)
        try:
            self.flaeche.configure(scrollregion=(0, 0, breite, max(gesamt, int(self.flaeche.winfo_height()))))
        except tk.TclError:
            pass

    def _zeichnen_alles(self, breite: int) -> None:
        self.flaeche.delete("all")
        self._hover = None
        self._druck = None
        self._druck_gesperrt = None
        spalten, kb = self._layout(breite)
        self.spalten, self.kartenbreite = spalten, kb
        m, a = self._masse, self._auf
        self.kartenhoehe = a.hoehe
        # Die Karten stehen mittig, wenn die Spalten die Breite nicht ganz fuellen (Rundung).
        links = max(m.rand, (breite - (spalten * kb + (spalten - 1) * m.abstand)) // 2)
        fenster = self._sichtfenster()                  # einmal fragen, nicht je Karte
        for karte in self.karten:
            zeile, spalte = divmod(karte.nummer, spalten)
            karte.x = links + spalte * (kb + m.abstand)
            karte.y = m.rand + zeile * (a.hoehe + m.abstand)
            karte.b, karte.h = kb, a.hoehe
            self._karte_zeichnen(karte, fenster)
        self._bereich_setzen(breite)

    def _karte_foto(self, gewaehlt: bool) -> "ImageTk.PhotoImage":
        z, m, a = self._z, self._masse, self._auf
        p = z.palette
        rb = m.randbreite
        rand = p.get("fg_accent", "#7fb2ff") if gewaehlt else p.get("border", "#34353d")
        breite_rand = rb if gewaehlt else 1.0
        return z.foto(("karte", a.breite, a.hoehe, gewaehlt, rb),
                      lambda: zeichnen.rund_rechteck(a.breite, a.hoehe, m.ecke, p.get("bg_card", "#1d1d23"),
                                                     rand, breite_rand))

    def _karte_zeichnen(self, karte: Karte, fenster: Any = _ERFRAGEN) -> None:
        z, m, a = self._z, self._masse, self._auf
        c, p = self.flaeche, z.palette
        tag = "k%d" % karte.nummer
        gewaehlt = karte.eintrag.get("path") == self.gewaehlt
        karte.ids = {}
        karte.fotos = {}
        karte.poster_da = False
        karte.inhalt = self._inhalt(karte.eintrag) or {}
        foto = self._karte_foto(gewaehlt)
        karte.fotos["karte"] = foto
        karte.ids["karte"] = c.create_image(karte.x, karte.y, image=foto, anchor="nw", tags=(tag, "karte"))
        self._poster_zeichnen(karte, tag, fenster)
        # Plakette PS4/PS5 oben links auf dem Titelbild
        plattform = str(karte.inhalt.get("plattform") or "")
        if plattform:
            rb = m.randbreite
            pb = z.messen("plakette", plattform) + 2 * z.px(10)
            ph = z.zeilenhoehe("plakette") + z.px(8)
            px_, py_ = karte.x + rb + z.px(12), karte.y + rb + z.px(12)
            pf = z.foto(("plakette", pb, ph), lambda: zeichnen.plakette(pb, ph))
            karte.fotos["plakette"] = pf
            karte.ids["plakette"] = c.create_image(px_, py_, image=pf, anchor="nw", tags=(tag,))
            karte.ids["plakette_text"] = c.create_text(px_ + pb / 2.0, py_ + ph / 2.0, text=plattform,
                                                       fill="#ffffff", font=z.schrift_angabe("plakette"),
                                                       tags=(tag,))
        # Titel (hoechstens zwei Zeilen)
        titel = str(karte.inhalt.get("titel") or "?")
        zeilen = zeichnen.text_umbrechen(titel, lambda t: z.messen("titel", t), a.innen_breite, m.titel_zeilen)
        karte.ids["titel"] = c.create_text(
            karte.x + a.innen_x, karte.y + a.titel_y, text="\n".join(zeilen) or "?", anchor="nw",
            fill=p.get("fg_accent" if gewaehlt else "fg_primary", "#ffffff"), font=z.schrift_angabe("titel"),
            tags=(tag,))
        self._chips_zeichnen(karte, tag)
        self._knoepfe_zeichnen(karte, tag)

    def _poster_zeichnen(self, karte: Karte, tag: str, fenster: Any = _ERFRAGEN) -> None:
        z, m, a = self._z, self._masse, self._auf
        c, p = self.flaeche, z.palette
        rb = m.randbreite
        pb = a.breite - 2 * rb
        x, y = karte.x + rb, karte.y + rb
        radius = max(1, m.ecke - rb)
        foto = None
        if karte.bildzustand == "da" and karte.bilddatei and self._poster_gewuenscht(karte, fenster):
            foto = z.poster_foto(karte.bilddatei, pb, pb, radius)
            if foto is None:                            # kaputte oder verschwundene Datei: wie "kein Bild"
                karte.bildzustand = "leer"
        karte.poster_da = foto is not None
        if foto is not None:
            karte.fotos["poster"] = foto
            karte.ids["poster"] = c.create_image(x, y, image=foto, anchor="nw", tags=(tag,))
            return
        # Platzhalter: vertiefte Flaeche, "laedt ..." oder das Zeichen "kein Titelbild"
        flaeche = z.foto(("poster_leer", pb, radius),
                         lambda: zeichnen.poster_bild(Image.new("RGB", (4, 4), p.get("console_bg", "#121216")),
                                                      pb, pb, radius))
        karte.fotos["poster"] = flaeche
        karte.ids["poster"] = c.create_image(x, y, image=flaeche, anchor="nw", tags=(tag,))
        if karte.bildzustand == "da":                   # fern vom sichtbaren Bereich: kommt beim Heranrollen
            return
        mitte_x, mitte_y = x + pb / 2.0, y + pb / 2.0
        if karte.bildzustand == "leer" and self._symbol is not None:
            groesse = max(16, int(pb * 0.3))
            farbe = p.get("fg_secondary", "#9a9ca6")
            sym = z.foto(("symbol", groesse, farbe), lambda: self._symbol(groesse, farbe))
            karte.fotos["symbol"] = sym
            karte.ids["symbol"] = c.create_image(mitte_x, mitte_y - z.px(10), image=sym, anchor="center",
                                                 tags=(tag,))
            text = self._texte("ohne_bild")
            versatz = z.px(10) + groesse / 2.0 + z.px(8)
        else:
            text = self._texte("laedt") if karte.bildzustand != "leer" else self._texte("ohne_bild")
            versatz = 0
        karte.ids["poster_text"] = c.create_text(mitte_x, mitte_y + versatz, text=text,
                                                 fill=p.get("fg_secondary", "#9a9ca6"),
                                                 font=z.schrift_angabe("klein"), tags=(tag,))

    def _chips_zeichnen(self, karte: Karte, tag: str) -> None:
        z, m, a = self._z, self._masse, self._auf
        c, p = self.flaeche, z.palette
        for alt in karte.chip_ids:
            c.delete(alt)
        karte.chip_ids = []
        chips = list(karte.inhalt.get("chips") or [])
        if not chips:
            return
        luft = z.px(10)
        breiten = [z.messen("chip", text) + 2 * luft for text, _art in chips]
        h = m.chip_zeile
        # Was nicht mehr in die zwei Zeilen passt, steht als "+N" da - nicht still weg.
        zeilen, versteckt = zeichnen.chips_mit_rest(
            breiten, lambda n: z.messen("chip", "+%d" % n) + 2 * luft, a.innen_breite, z.px(6), m.chip_zeilen)
        if versteckt:
            chips.append(("+%d" % versteckt, "neutral"))
            breiten.append(z.messen("chip", "+%d" % versteckt) + 2 * luft)
        y = karte.y + a.chips_y
        for zeile in zeilen:
            x = karte.x + a.innen_x
            for nummer in zeile:
                text, art = chips[nummer]
                b = min(breiten[nummer], a.innen_breite)
                if b < breiten[nummer]:                 # allein breiter als die Karte: Text kuerzen statt herausragen
                    text = _passend(z, "chip", text, b - 2 * luft)
                farben = zeichnen.chip_farben(p, art)
                bild = z.foto(("chip", art, b, h),
                              lambda f=farben, b=b: zeichnen.rund_rechteck(
                                  b, h, h / 2.0, f["fuellung"], f["rand"], max(1.0, z.faktor),
                                  gestrichelt=f["gestrichelt"]))
                karte.fotos["chip%d" % nummer] = bild
                karte.chip_ids.append(c.create_image(x, y, image=bild, anchor="nw", tags=(tag,)))
                karte.chip_ids.append(c.create_text(x + b / 2.0, y + h / 2.0, text=text, fill=farben["text"],
                                                    font=z.schrift_angabe("chip"), tags=(tag,)))
                x += b + z.px(6)
            y += h + z.px(6)

    def _knoepfe_zeichnen(self, karte: Karte, tag: str) -> None:
        z, a = self._z, self._auf
        c = self.flaeche
        for alt in karte.knoepfe:
            for teil in (alt.bild, alt.text, alt.chevron):
                if teil:
                    c.delete(teil)
        karte.knoepfe = []
        specs = {spec.name: spec for spec in karte.inhalt.get("knoepfe") or []}
        x0, b = karte.x + a.innen_x, a.innen_breite
        gap = z.px(8)

        def _knopf(name: str, x: int, y: int, breite: int, hoehe: int) -> None:
            spec = specs.get(name)
            if spec is None:
                return
            karte.knoepfe.append(knopf_zeichnen(c, z, spec, x, y, breite, hoehe, tags=(tag,)))

        _knopf("info", x0, karte.y + a.info_y, b, a.knopf_hoehe)
        _knopf("start", x0, karte.y + a.start_y, b, a.start_hoehe)
        halb = (b - gap) // 2
        _knopf("kopieren", x0, karte.y + a.aktion_y, halb, a.aktion_hoehe)
        _knopf("konvertieren", x0 + halb + gap, karte.y + a.aktion_y, b - halb - gap, a.aktion_hoehe)

    # --- Bilder und Marken -------------------------------------------------------------------------------
    def bild_setzen(self, eintrag: dict, datei: str) -> None:
        """Setzt das Titelbild einer Karte; ``""`` heisst "kein Titelbild"."""
        karte = self.karte_von(eintrag)
        if karte is None or not self.lebt():
            return
        karte.bilddatei = str(datei or "")
        karte.bildzustand = "da" if datei else "leer"
        if self._auf is not None:
            self._poster_neu(karte)

    def _poster_neu(self, karte: Karte, fenster: Any = _ERFRAGEN) -> None:
        """Zeichnet das Titelbild einer Karte (oder seinen Platzhalter) neu, an derselben Stelle im Stapel."""
        for name in ("poster", "symbol", "poster_text"):
            teil = karte.ids.pop(name, None)
            if teil:
                self.flaeche.delete(teil)
        karte.fotos.pop("symbol", None)
        self._poster_zeichnen(karte, "k%d" % karte.nummer, fenster)
        # Das Titelbild liegt ueber dem Kartengrund, aber unter Plakette, Titel und Knoepfen.
        self.flaeche.tag_lower(karte.ids["poster"], karte.ids.get("plakette") or karte.ids.get("titel"))
        for name in ("symbol", "poster_text"):
            if karte.ids.get(name):
                self.flaeche.tag_raise(karte.ids[name], karte.ids["poster"])

    def _sichtfenster(self) -> tuple[float, float] | None:
        """Der sichtbare Bereich der Zeichenflaeche als ``(oben, unten)`` in Flaechenkoordinaten.

        ``None``, solange die Flaeche nicht gemessen ist (die Seite ist nicht
        sichtbar): Dann gilt alles als sichtbar. Zwei Tk-Aufrufe - deshalb einmal
        je Rollung fragen, nicht je Karte.
        """
        try:
            hoehe = int(self.flaeche.winfo_height())
            if hoehe <= 1:
                return None
            oben = float(self.flaeche.canvasy(0))
        except tk.TclError:
            return None
        return oben, oben + hoehe

    def _poster_gewuenscht(self, karte: Karte, fenster: Any = _ERFRAGEN) -> bool:
        """Soll das Titelbild dieser Karte jetzt gebaut sein?

        Gebaut wird nur, was nahe am sichtbaren Bereich liegt: eine Kartenhoehe
        darueber und darunter. Was schon gebaut ist, bleibt, bis es drei
        Kartenhoehen entfernt ist - ein Hin- und Herrollen baut so nicht
        staendig neu. Das haelt den Speicher bei Hunderten von Titeln klein und
        den Aufbau der Seite schnell.

        ``fenster`` ist das Ergebnis von ``_sichtfenster``; wer viele Karten
        prueft, fragt es einmal und gibt es mit.
        """
        if fenster is _ERFRAGEN:
            fenster = self._sichtfenster()
        if fenster is None:
            return True
        oben, unten = fenster
        luft = karte.h * (3 if karte.poster_da else 1)
        return karte.y + karte.h >= oben - luft and karte.y <= unten + luft

    def _posters_nachziehen(self) -> None:
        """Baut die Titelbilder, die in die Naehe des sichtbaren Bereichs gerollt sind, und gibt ferne frei."""
        if self._auf is None or not self.lebt():
            return
        fenster = self._sichtfenster()
        for karte in self.karten:
            if karte.bildzustand == "da" and self._poster_gewuenscht(karte, fenster) != karte.poster_da:
                self._poster_neu(karte, fenster)

    def _rollt(self, erste: str, letzte: str) -> None:
        """Rueckruf der Zeichenflaeche bei jeder Rollung: Balken nachziehen, Titelbilder nachladen."""
        self.balken.set(erste, letzte)
        self._posters_nachziehen()

    def aktualisieren(self, eintrag: dict) -> None:
        """Zeichnet Chips und Knoepfe einer Karte neu (Einbauten sind da, Zustand hat sich geaendert)."""
        karte = self.karte_von(eintrag)
        if karte is None or not self.lebt() or self._auf is None:
            return
        karte.inhalt = self._inhalt(karte.eintrag) or {}
        tag = "k%d" % karte.nummer
        self._chips_zeichnen(karte, tag)
        self._knoepfe_zeichnen(karte, tag)
        self._knoepfe_nachfuehren(karte)
        titel = karte.ids.get("titel")
        if titel:
            self.flaeche.itemconfigure(titel, text=self._titel_text(karte))

    def _knoepfe_nachfuehren(self, karte: Karte) -> None:
        """Haelt Hover und Druck bei, wenn die Knoepfe einer Karte neu gezeichnet wurden.

        ``_knoepfe_zeichnen`` baut neue ``GezeichneterKnopf``-Objekte; ``_hover`` und
        ``_druck`` zeigten danach auf die alten. Folge: Ein Druck zwischen Druecken und
        Loslassen (eine Einbaupruefung im Hintergrund meldet sich) ging verloren, und der
        Hover-Ton verschwand, solange der Zeiger sich nicht bewegte.
        """
        for name in ("_hover", "_druck", "_druck_gesperrt"):
            halt = getattr(self, name)
            if halt is None or halt[0] is not karte:
                continue
            neu = next((k for k in karte.knoepfe if k.spec.name == halt[1].spec.name), None)
            if neu is None:
                setattr(self, name, None)
                continue
            if name == "_druck_gesperrt" and neu.spec.aktiv:        # inzwischen frei: kein "gesperrt" mehr melden
                setattr(self, name, None)
                continue
            if name != "_druck_gesperrt" and not neu.spec.aktiv:    # inzwischen gesperrt: nichts mehr zu druecken
                setattr(self, name, None)
                continue
            setattr(self, name, (karte, neu))
            if name == "_druck":
                knopf_umfaerben(self.flaeche, self._z, neu, "gedrueckt")
            elif name == "_hover":
                knopf_umfaerben(self.flaeche, self._z, neu, "hover")

    def _titel_text(self, karte: Karte) -> str:
        z, m, a = self._z, self._masse, self._auf
        zeilen = zeichnen.text_umbrechen(str(karte.inhalt.get("titel") or "?"),
                                         lambda t: z.messen("titel", t), a.innen_breite, m.titel_zeilen)
        return "\n".join(zeilen) or "?"

    def markieren(self, gewaehlt: str) -> None:
        """Hebt die gewaehlte Karte hervor - ohne etwas neu zu bauen."""
        self.gewaehlt = gewaehlt
        if self._auf is None or not self.lebt():
            return
        p = self._z.palette
        for karte in self.karten:
            ist = karte.eintrag.get("path") == gewaehlt
            foto = self._karte_foto(ist)
            karte.fotos["karte"] = foto
            try:
                self.flaeche.itemconfigure(karte.ids["karte"], image=foto)
                self.flaeche.itemconfigure(karte.ids["titel"],
                                           fill=p.get("fg_accent" if ist else "fg_primary", "#ffffff"))
            except (tk.TclError, KeyError):
                continue

    def farben_neu(self, neu_zeichnen: bool = True) -> None:
        """Nach einem Designwechsel: Grund und Bilder in den neuen Farben.

        ``neu_zeichnen=False``, wenn der Aufrufer die Karten gleich selbst neu
        setzt (die Seite filtert nach einem Designwechsel ohnehin neu).
        """
        p = self._z.palette
        try:
            self.rahmen.configure(bg=p.get("bg_main", "#000000"))
            self.flaeche.configure(bg=p.get("bg_main", "#000000"))
        except tk.TclError:
            return
        self._z.leeren()
        if neu_zeichnen and self.karten:
            self._zeichnen_alles(self._gesamtbreite())

    # --- Treffer ---------------------------------------------------------------------------------------
    def _canvas_xy(self, e: Any) -> tuple[float, float]:
        return float(self.flaeche.canvasx(e.x)), float(self.flaeche.canvasy(e.y))

    def treffer(self, x: float, y: float) -> tuple[Karte | None, GezeichneterKnopf | None]:
        """Welche Karte und welcher Knopf liegen bei ``(x, y)`` (Flaechenkoordinaten)?"""
        if self._masse is None or self._auf is None or not self.karten:
            return None, None
        a, m = self._auf, self._masse
        zeile = int((y - m.rand) // (a.hoehe + m.abstand)) if y >= m.rand else -1
        if zeile < 0:
            return None, None
        for karte in self.karten[zeile * self.spalten:(zeile + 1) * self.spalten]:
            if karte.x <= x < karte.x + karte.b and karte.y <= y < karte.y + karte.h:
                for knopf in karte.knoepfe:
                    if knopf.enthaelt(x, y):
                        return karte, knopf
                return karte, None
        return None, None

    def klick(self, x: float, y: float) -> None:
        """Ein vollstaendiger Klick (Druecken und Loslassen) bei ``(x, y)`` - fuer Tests und Tastatur."""
        self._druecken_bei(x, y)
        self._loslassen_bei(x, y)

    def _druecken_bei(self, x: float, y: float) -> None:
        karte, knopf = self.treffer(x, y)
        self._druck = None
        self._druck_gesperrt = None
        if karte is None:
            return
        if knopf is None:
            self._bei_auswahl(karte.eintrag)
            return
        if knopf.spec.aktiv:
            self._druck = (karte, knopf)
            knopf_umfaerben(self.flaeche, self._z, knopf, "gedrueckt")
        else:
            self._druck_gesperrt = (karte, knopf)

    def _loslassen_bei(self, x: float, y: float) -> None:
        druck, self._druck = self._druck, None
        gesperrt, self._druck_gesperrt = self._druck_gesperrt, None
        karte, knopf = self.treffer(x, y)
        if druck is not None:
            d_karte, d_knopf = druck
            knopf_umfaerben(self.flaeche, self._z, d_knopf, "hover" if (karte is d_karte and knopf is d_knopf)
                            else "normal")
            if karte is d_karte and knopf is d_knopf:
                self._aktion(d_knopf.spec.name, d_karte.eintrag)
            return
        # "Gesperrt" meldet nur ein Klick, der auf dem gesperrten Knopf beginnt UND dort endet - nicht
        # ein Ziehen von woanders her (der KartenKnopf der Kopfkarte haelt es ebenso).
        if (gesperrt is not None and karte is gesperrt[0] and knopf is gesperrt[1]
                and self._bei_gesperrt is not None):
            self._bei_gesperrt(knopf.spec.name, karte.eintrag)

    def _gedrueckt(self, e: Any) -> None:
        try:
            self.flaeche.focus_set()
        except tk.TclError:
            pass
        self._druecken_bei(*self._canvas_xy(e))

    def _losgelassen(self, e: Any) -> None:
        self._loslassen_bei(*self._canvas_xy(e))

    def _doppelt(self, e: Any) -> None:
        karte, knopf = self.treffer(*self._canvas_xy(e))
        if karte is not None and knopf is None:
            self._bei_start(karte.eintrag)

    def _bewegt(self, e: Any) -> None:
        karte, knopf = self.treffer(*self._canvas_xy(e))
        neu = (karte, knopf) if (karte is not None and knopf is not None) else None
        if (neu is None) != (self._hover is None) or (neu and self._hover and neu[1] is not self._hover[1]):
            if self._hover is not None and (self._druck is None or self._druck[1] is not self._hover[1]):
                knopf_umfaerben(self.flaeche, self._z, self._hover[1],
                                "normal" if self._hover[1].spec.aktiv else "gesperrt")
            self._hover = neu
            if neu is not None and neu[1].spec.aktiv and (self._druck is None or self._druck[1] is not neu[1]):
                knopf_umfaerben(self.flaeche, self._z, neu[1], "hover")
        # Nur bei einer Aenderung: Jedes ``configure`` der Zeichenflaeche laesst Tk die ganze sichtbare
        # Flaeche neu malen und die Rollbalken neu melden - bei jeder Mausbewegung waere das ein
        # Dauerfeuer ueber alle Karten.
        wunsch = "arrow" if (karte is None or (knopf is not None and not knopf.spec.aktiv)) else "hand2"
        if wunsch != self._zeiger:
            try:
                self.flaeche.configure(cursor=wunsch)
                self._zeiger = wunsch
            except tk.TclError:
                pass

    def _verlassen(self, _e: Any = None) -> None:
        if self._hover is not None:
            knopf_umfaerben(self.flaeche, self._z, self._hover[1],
                            "normal" if self._hover[1].spec.aktiv else "gesperrt")
            self._hover = None

    def _mausrad(self, e: Any) -> None:
        try:
            self.flaeche.yview_scroll(int(self._rad(e)), "units")
        except tk.TclError:
            pass

    # --- Lage fuer Aufrufer --------------------------------------------------------------------------------
    def knopf_lage(self, eintrag: dict, name: str) -> tuple[int, int, int, int] | None:
        """Bildschirmlage (x, y, breite, hoehe) eines Knopfs - dort verankert sich das Infofenster."""
        karte = self.karte_von(eintrag)
        if karte is None:
            return None
        for knopf in karte.knoepfe:
            if knopf.spec.name == name:
                wx = self.flaeche.winfo_rootx() + knopf.x - int(self.flaeche.canvasx(0))
                wy = self.flaeche.winfo_rooty() + knopf.y - int(self.flaeche.canvasy(0))
                return wx, wy, knopf.b, knopf.h
        return None

    def sichtbar_machen(self, eintrag: dict) -> None:
        """Rollt die Karte in den sichtbaren Bereich."""
        karte = self.karte_von(eintrag)
        if karte is None or not self.lebt():
            return
        hoehe = max(1, int(self.flaeche.winfo_height()))
        oben = int(self.flaeche.canvasy(0))
        gesamt = max(1, int(float(self.flaeche.cget("height")) or 1))
        try:
            region = [float(v) for v in str(self.flaeche.cget("scrollregion")).split()]
            gesamt = region[3] if len(region) == 4 else gesamt
        except (ValueError, tk.TclError):
            pass
        if karte.y < oben:
            self.flaeche.yview_moveto(max(0.0, (karte.y - self._masse.rand) / gesamt))
        elif karte.y + karte.h > oben + hoehe:
            self.flaeche.yview_moveto(max(0.0, (karte.y + karte.h + self._masse.rand - hoehe) / gesamt))


# ---------------------------------------------------------------------------
# Das Fortschrittsfenster des Suchlaufs
# ---------------------------------------------------------------------------

class SuchlaufAnzeige:
    """Das Fenster "Bibliothek wird durchsucht": Stufe, aktueller Titel, Balken mit Prozent, Abbrechen.

    Die Seite legt je Suchlauf eine Anzeige an. Die Arbeitsfaeden melden ueber :meth:`melden` und
    beenden mit :meth:`beenden` - beides aus jedem Faden. **Kein Faden fasst dabei Tk an:** Eine Meldung
    landet nur in einem Merker (die jeweils letzte gilt), ``beenden`` setzt nur ein Merkmal. Ein Takt im
    Fensterfaden (:attr:`TAKT_MS`) holt beides ab, baut das Fenster, zeichnet und schliesst es - das
    Takt-Muster des Projekts. Bis zum 03.10.2026 ging jede Meldung ueber ``after`` aus dem Faden: Ohne
    laufende Hauptschleife (Tests, Programmende) wartete jeder dieser Aufrufe eine Sekunde und kam doch
    nicht an, und im ersten Volllauf blieb ein sichtbares Fenster fuer den Rest des Laufs stehen.

    **Es erscheint erst nach** ``verzoegerung_ms``: Ein Suchlauf, der in einem Augenblick fertig ist
    (zwei, drei Ordner voller Dumps), soll kein Fenster aufblitzen lassen. Wer lange wartet - ein Abbild
    auf einer kalten Platte, die Konsole im Netz -, sieht es und weiss, dass es weitergeht. Und nur,
    solange die Seite selbst zu sehen ist (``nur_sichtbar``): Das Fenster gehoert zu ihr.

    Args:
        seite: Das Widget, an dem der Takt laeuft (``after``). Geht es zu, ist auch der Takt weg - die
            Seite schliesst das Fenster dann ueber :meth:`schliessen`.
        zeichner: Palette und Schriften.
        phasen: ``bibliothek_fortschritt.Phasen`` dieses Suchlaufs.
        bauen: ``() -> tk.Toplevel`` - das Fenster samt Kopfzeile. Kommt vom Programm, damit es aussieht
            wie seine anderen Fenster (Titel, Symbol, Lage).
        text: ``(schluessel, **werte) -> str`` - die Uebersetzung. Gebraucht werden ``action.cancel``,
            ``library.scan_zaehlung`` (``{getan}``, ``{gesamt}``), ``library.scan_hinweis`` und je Stufe der
            Schluessel aus ``stufen``.
        abbrechen: ``()`` - der Anwender hat "Abbrechen" (oder das X) gedrueckt. Die Seite beendet damit
            die Faeden; das Fenster schliesst sich danach selbst.
        stufen: ``{Stufe: Textschluessel}`` - die Zeile je Stufe, etwa "Angaben werden gelesen ...".
        verzoegerung_ms: Wie lange der Suchlauf laufen muss, bevor das Fenster aufgeht.
        drossel: Die Drossel der Meldungen; Tests setzen eine eigene.
        hinweis: Textschluessel der ruhigen Zeile unter dem Balken (Rechner und Konsole sagen Verschiedenes).
        nur_sichtbar: Das Fenster nur bauen, solange ``seite`` zu sehen ist (``winfo_viewable``). Tests des
            Fensters selbst schalten das ab - ihre Wurzel ist verborgen.
    """

    #: Takt, in dem der Fensterfaden Meldungen abholt, das Fenster baut und es schliesst (Millisekunden).
    TAKT_MS = 100

    def __init__(self, seite: tk.Misc, zeichner: Zeichner, phasen: Phasen, *,
                 bauen: Callable[[], tk.Misc], text: Callable[..., str], abbrechen: Callable[[], None],
                 stufen: dict[str, str], verzoegerung_ms: int = 400, drossel: Drossel | None = None,
                 hinweis: str = "library.scan_hinweis", nur_sichtbar: bool = True) -> None:
        self._hinweis = hinweis
        self._nur_sichtbar = nur_sichtbar
        self._seite = seite
        self._z = zeichner
        self._phasen = phasen
        self._bauen = bauen
        self._text = text
        self._abbrechen_rueckruf = abbrechen
        self._stufen = dict(stufen)
        self._drossel = drossel or Drossel(0.08)
        self._stand: Stand | None = None
        self._detail = ""
        self._fenster: tk.Misc | None = None
        self._balken: ttk.Progressbar | None = None
        self._modus = ""
        self._labels: dict[str, tk.Label] = {}
        self._beendet = False
        self._gezeigt = False             # das Fenster wurde schon einmal gebaut (oder versucht)
        self._neu: tuple[str, int | None, int | None, str] | None = None
        self._sperre = threading.Lock()
        self._start = time.monotonic()
        self._verzoegerung = max(0, int(verzoegerung_ms)) / 1000.0
        self._nach_takt: str | None = None
        try:
            self._nach_takt = seite.after(min(max(0, int(verzoegerung_ms)), self.TAKT_MS), self._takt)
        except tk.TclError:
            self._beendet = True

    # --- aus jedem Faden -------------------------------------------------------------------------------
    @property
    def beendet(self) -> bool:
        return self._beendet

    @property
    def offen(self) -> bool:
        """Steht das Fenster gerade auf dem Schirm?"""
        return self._fenster is not None and not self._beendet

    @staticmethod
    def _im_fensterfaden() -> bool:
        return threading.current_thread() is threading.main_thread()

    def melden(self, stufe: str, getan: int | None = None, gesamt: int | None = None, text: str = "",
               letzte: bool = False) -> None:
        """Meldet den Stand einer Stufe - aus jedem Faden. ``letzte`` kommt an der Drossel vorbei.

        Aus einem Arbeitsfaden landet die Meldung nur im Merker, der Takt zeigt sie an. Aus dem Fensterfaden
        gilt sie sofort.
        """
        if self._beendet or not self._drossel.darf(letzte):
            return
        if self._im_fensterfaden():
            self._im_fenster(stufe, getan, gesamt, str(text or ""))
            return
        with self._sperre:
            self._neu = (stufe, getan, gesamt, str(text or ""))

    def beenden(self) -> None:
        """Beendet die Anzeige: Das Fenster geht zu, spaetere Meldungen verpuffen. Aus jedem Faden, mehrfach.

        Aus einem Arbeitsfaden wird nur das Merkmal gesetzt - der Takt schliesst das Fenster beim naechsten
        Schlag, ein noch nicht gezeigtes geht gar nicht erst auf. Aus dem Fensterfaden schliesst es sofort.
        """
        self._beendet = True
        if self._im_fensterfaden():
            self._schliessen()

    def schliessen(self) -> None:
        """Schliesst das Fenster sofort - nur im Fensterfaden.

        Fuer die Seite, die zugeht oder einen neuen Suchlauf beginnt: Der Takt laeuft an der Seite und
        endet mit ihr - das Fenster, ein eigenes Toplevel, bliebe sonst stehen.
        """
        self._schliessen()

    def _takt(self) -> None:
        """Ein Schlag im Fensterfaden: Ende abfragen, letzte Meldung uebernehmen, Fenster bauen, weiter."""
        self._nach_takt = None
        if self._beendet:
            self._schliessen()
            return
        with self._sperre:
            neu, self._neu = self._neu, None
        if neu is not None:
            self._im_fenster(*neu)
        if (not self._gezeigt and time.monotonic() - self._start >= self._verzoegerung
                and self._seite_zu_sehen()):
            self._gezeigt = True
            self._zeigen()
        try:
            self._nach_takt = self._seite.after(self.TAKT_MS, self._takt)
        except tk.TclError:
            self._schliessen()

    def _seite_zu_sehen(self) -> bool:
        if not self._nur_sichtbar:
            return True
        try:
            return bool(self._seite.winfo_viewable())
        except tk.TclError:
            return False

    # --- im Fensterfaden -------------------------------------------------------------------------------
    def _im_fenster(self, stufe: str, getan: int | None, gesamt: int | None, text: str) -> None:
        if self._beendet:
            return
        try:
            self._stand = self._phasen.setzen(stufe, getan, gesamt)
        except ValueError:
            return                    # eine Stufe, die es nicht gibt, soll den Suchlauf nicht stoeren
        self._detail = str(text or "")
        if self._fenster is not None:
            self._anzeigen()

    def _zeigen(self) -> None:
        if self._beendet or self._fenster is not None:
            return
        try:
            fenster = self._bauen()
            palette = self._z.palette
            hintergrund = palette.get("bg_main", "#000000")
            koerper = tk.Frame(fenster, bg=hintergrund, padx=20, pady=6)
            for name, rolle, farbe in (("stufe", "knopf_fett", "fg_primary"), ("detail", "klein", "fg_secondary")):
                zeile_label = tk.Label(koerper, text="", font=self._z.schrift_angabe(rolle), bg=hintergrund,
                                       fg=palette.get(farbe, "#ffffff"), anchor="w", justify="left",
                                       wraplength=self._z.px(520))
                zeile_label.pack(fill="x", pady=(0, 2))
                self._labels[name] = zeile_label
            zeile = tk.Frame(koerper, bg=hintergrund)
            zeile.pack(fill="x", pady=(8, 4))
            self._balken = ttk.Progressbar(zeile, mode="determinate", maximum=100.0)
            self._balken.pack(side="left", fill="x", expand=True)
            prozent = tk.Label(zeile, text="", width=6, anchor="e", font=self._z.schrift_angabe("klein_fett"),
                               bg=hintergrund, fg=palette.get("fg_primary", "#ffffff"))
            prozent.pack(side="left", padx=(10, 0))
            self._labels["prozent"] = prozent
            hinweis = tk.Label(koerper, text=self._text(self._hinweis), font=self._z.schrift_angabe("klein"),
                               bg=hintergrund, fg=palette.get("fg_secondary", "#aaaaaa"), anchor="w",
                               justify="left", wraplength=self._z.px(520))
            hinweis.pack(fill="x", pady=(8, 0))
            self._labels["hinweis"] = hinweis
            fuss = tk.Frame(fenster, bg=hintergrund, padx=20, pady=12)
            fuss.pack(side="bottom", fill="x")
            ttk.Button(fuss, text=self._text("action.cancel"), command=self._abbrechen).pack(side="right")
            koerper.pack(fill="both", expand=True)
            fenster.protocol("WM_DELETE_WINDOW", self._abbrechen)
            self._fenster = fenster
        except tk.TclError:
            self._fenster = None
            return
        self._anzeigen()

    def _anzeigen(self) -> None:
        if self._fenster is None or self._balken is None:
            return
        stand = self._stand
        stufe = stand.stufe if stand is not None else next(iter(self._stufen), "")
        try:
            self._labels["stufe"].configure(text=self._text(self._stufen[stufe]) if stufe in self._stufen else "")
            teile: list[str] = []
            if stand is not None and not stand.unbestimmt and stand.gesamt:
                teile.append(self._text("library.scan_zaehlung", getan=stand.getan, gesamt=stand.gesamt))
            if self._detail:
                teile.append(self._detail)
            self._labels["detail"].configure(text="   ·   ".join(teile))
            if stand is None or stand.unbestimmt:
                if self._modus != "indeterminate":
                    self._balken.configure(mode="indeterminate")
                    self._balken.start(14)
                    self._modus = "indeterminate"
                self._labels["prozent"].configure(text="…")
            else:
                if self._modus != "determinate":
                    self._balken.stop()
                    self._balken.configure(mode="determinate")
                    self._modus = "determinate"
                self._balken.configure(value=stand.prozent)
                self._labels["prozent"].configure(text="%d %%" % stand.prozent)
        except tk.TclError:
            pass                      # das Fenster ging gerade zu

    def _abbrechen(self) -> None:
        """Abbrechen oder das X: erst die Seite verstaendigen, dann zumachen - nur einmal."""
        if self._beendet:
            return
        self._beendet = True
        try:
            self._abbrechen_rueckruf()
        finally:
            self._schliessen()

    def _schliessen(self) -> None:
        self._beendet = True
        if self._nach_takt is not None:
            try:
                self._seite.after_cancel(self._nach_takt)
            except tk.TclError:
                pass
            self._nach_takt = None
        fenster, self._fenster = self._fenster, None
        if self._balken is not None:
            try:
                self._balken.stop()
            except tk.TclError:
                pass
            self._balken = None
        if fenster is not None:
            try:
                fenster.destroy()
            except tk.TclError:
                pass
