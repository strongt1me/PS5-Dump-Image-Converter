# -*- coding: utf-8 -*-
"""Macht eine Seite durchsichtig: Rahmen, Beschriftungen und Pillen stehen direkt auf dem Hauptbild.

Aufgabe 7 (PKG / FPKG, seit 30.10.2026) soll wie die Aufgaben 1 bis 6 ohne feste Flaeche auf dem Hintergrundbild stehen
(Nutzerwunsch: "durchsichtig ueber dem Hintergrundbild"). Die beiden Bereiche (``ps4_dump_image``, ``ps5_pkg_fenster``)
bauen aber aus gewoehnlichen ``tk.Frame``/``tk.Label`` - und Tk kennt keine durchsichtigen Container. Statt sie neu zu
schreiben, legt dieses Modul den Ausschnitt des Hauptbilds **hinter jedes Teil**, wie es die Aufgaben 1 bis 6 mit ihren
Beschriftungen tun (``_redraw_content_captions``):

* ``tk.Frame``: ein Label ueber die ganze Flaeche (``place``), ganz unten - sein Bild ist der Ausschnitt dahinter,
* ``tk.Label``: der Ausschnitt in der Groesse des Textes unter dem Text (``compound="center"``); ein Label, das sich ueber
  die Zeile streckte, wird dafuer auf die Groesse seines Textes zurueckgenommen (dieselbe Anordnung, Text links wie vorher),
* gezeichnete Knoepfe und Balken (Canvas): der Ausschnitt als unterstes Element, sodass die Ecken das Bild zeigen,
* runde Karten (``RundeKarte``): ihre Ecken malen den Ausschnitt (``_seitenbild`` am Seitenrahmen),
* Haken und Drehknoepfe des Hauptprogramms: ueber ``_rund_hintergrund`` (``_seitenbild`` am Seitenrahmen).

Karten mit eigener Flaeche (Eingabefelder, Protokoll, Kacheln) bleiben, was sie sind: runde Karten in Kartenfarbe.
Gerechnet wird entprellt (``planen``) und nur, was sich geaendert hat (Schluessel aus Text, Groesse, Lage, Bild).
"""
from __future__ import annotations

import logging
import tkinter as tk
from typing import Any, Callable

from PIL import ImageTk

from ps5_validator.utils import bibliothek_raster as raster

logger = logging.getLogger("PS5Converter.ui.seitenbild")

#: Rahmen, die nur ein Strich sind (Trennlinien, Reiterunterstrich): kein Bild darunter.
_STRICH = 4


class Seitenbild:
    """Haelt eine Seite durchsichtig. ``hinter(widget, breite, hoehe)`` liefert den Bildausschnitt hinter ``widget``."""

    def __init__(self, gui, rahmen: tk.Misc, hinter: Callable[..., Any]) -> None:
        self.g = gui
        self.rahmen = rahmen
        self.hinter = hinter
        self._nach: "str | None" = None
        self._ruhe = 0
        self._nachholen = False
        self._zwilling: "tk.Label | None" = None
        self._bindungen: "list[tuple[str, str]]" = []
        self._dnd: "dict[Any, tuple[Any, Any]]" = {}
        #: Zaehlt hoch, wenn das Bild dahinter ein anderes geworden ist (Fenstergroesse, Design, Bildwechsel).
        self._bildstand: tuple = ()
        try:
            oben = rahmen.winfo_toplevel()
            for folge in ("<Map>", "<Configure>"):
                self._bindungen.append((folge, oben.bind(folge, self._ereignis, add="+")))
            rahmen.bind("<Destroy>", self._abbauen, add="+")
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Ereignisse
    # ------------------------------------------------------------------
    def _abbauen(self, e: Any) -> None:
        if e.widget is not self.rahmen:
            return
        try:
            oben = self.rahmen.winfo_toplevel()
            for folge, kennung in self._bindungen:
                oben.unbind(folge, kennung)
        except tk.TclError:
            pass
        self._bindungen = []

    def _ereignis(self, e: Any) -> None:
        widget = getattr(e, "widget", None)
        try:
            pfad = str(widget)
        except Exception:                                  # noqa: BLE001
            return
        wurzel = str(self.rahmen)
        if pfad == wurzel or pfad.startswith(wurzel + "."):
            self.planen()

    def ruhen(self):
        """``with``-Block: solange er laeuft, wird nicht unterlegt (jedes ``update()`` darin wuerde sonst einen ganzen
        Durchlauf ausloesen). Danach folgt, falls etwas anstand, genau ein entprellter Durchlauf."""
        bild = self

        class _Ruhe:
            def __enter__(self_):
                bild._ruhe += 1

            def __exit__(self_, *a):
                bild._ruhe -= 1
                if bild._ruhe == 0 and bild._nachholen:
                    bild._nachholen = False
                    bild.planen()

        return _Ruhe()

    def planen(self) -> None:
        if self._ruhe:
            self._nachholen = True
            return
        if self._nach is not None:
            return
        try:
            self._nach = self.rahmen.after_idle(self.jetzt)
        except tk.TclError:
            self._nach = None

    def dnd_weitergeben(self, rahmen: tk.Misc, art: Any, befehl: Any) -> None:
        """Ein Rahmen, auf dem abgelegt werden darf: sein Unterlegbild nimmt Ablagen genauso an."""
        self._dnd[rahmen] = (art, befehl)

    # ------------------------------------------------------------------
    # Durchlauf
    # ------------------------------------------------------------------
    def jetzt(self) -> None:
        self._nach = None
        if self._ruhe:
            self._nachholen = True
            return
        try:
            if not self.rahmen.winfo_exists() or not self.rahmen.winfo_ismapped():
                return
            b, h = int(self.rahmen.winfo_width()), int(self.rahmen.winfo_height())
            if b <= 1 or h <= 1:
                return
        except tk.TclError:
            return
        quelle = getattr(self.g, "_bg_image_cache", None)
        self._bildstand = (id(quelle), b, h, self.rahmen.winfo_rootx(), self.rahmen.winfo_rooty())
        stapel = [self.rahmen]
        while stapel:
            knoten = stapel.pop()
            try:
                kinder = list(knoten.winfo_children())
            except tk.TclError:
                continue
            for kind in kinder:
                try:
                    if self._behandeln(kind):
                        stapel.append(kind)
                except tk.TclError:
                    continue
                except Exception as exc:                   # noqa: BLE001
                    logger.debug("Unterlegen von %s fehlgeschlagen: %s", kind, exc)
        try:
            self.g._runde_flaechen_planen()
        except Exception as exc:                           # noqa: BLE001
            logger.debug("Pillen nicht nachziehbar: %s", exc)

    def _behandeln(self, kind) -> bool:
        """Legt dem Teil sein Bild unter. Liefert ``True``, wenn seine Kinder auch drankommen."""
        if getattr(kind, "_sb_eigen", False):
            return False
        if isinstance(kind, raster.RundeKarte):
            self._karte(kind)
            return False
        if type(kind).__name__ in ("RunderHaken", "Drehknopf"):
            self._haken(kind)
            return False
        if isinstance(kind, (raster.KartenKnopf,)) or hasattr(kind, "_zeichnen") and isinstance(kind, tk.Canvas):
            self._leinwand(kind)
            return False
        if isinstance(kind, tk.Label):
            self._beschriftung(kind)
            return False
        if isinstance(kind, tk.Frame):
            self._rahmen(kind)
            return True
        if type(kind) is tk.Canvas:
            self._rollflaeche(kind)
            return True
        return bool(kind.winfo_children()) if isinstance(kind, tk.Misc) else False

    # ------------------------------------------------------------------
    # Ausschnitte
    # ------------------------------------------------------------------
    def _lage(self, widget) -> tuple:
        return (widget.winfo_rootx() - self.rahmen.winfo_rootx(), widget.winfo_rooty() - self.rahmen.winfo_rooty())

    def _foto(self, widget, breite: int, hoehe: int, versatz: tuple = (0, 0), funktion: Any = None):
        ausschnitt = (funktion or self.hinter)(widget, int(breite), int(hoehe), versatz)
        if ausschnitt is None:
            return None
        return ImageTk.PhotoImage(ausschnitt.convert("RGB"), master=self.g.root)

    # ------------------------------------------------------------------
    # Rahmen
    # ------------------------------------------------------------------
    def _rahmen(self, rahmen: tk.Frame) -> None:
        if not rahmen.winfo_ismapped():
            return
        b, h = int(rahmen.winfo_width()), int(rahmen.winfo_height())
        if b <= 1 or h <= 1 or min(b, h) <= _STRICH:
            return
        unter = getattr(rahmen, "_sb_unter", None)
        if unter is None or not unter.winfo_exists():
            unter = tk.Label(rahmen, bd=0, highlightthickness=0, padx=0, pady=0, bg=str(rahmen.cget("bg")))
            unter._sb_eigen = True                          # type: ignore[attr-defined]
            # ``padx``/``pady`` eines Rahmens sind sein innerer Rand: ``place`` rechnet erst dahinter - das Unterlegbild
            # reicht deshalb um diesen Rand hinaus, sonst bliebe ein dunkler Rahmen um den Inhalt stehen.
            try:
                rand_x, rand_y = int(rahmen.winfo_pixels(rahmen.cget("padx"))), int(rahmen.winfo_pixels(rahmen.cget("pady")))
            except (tk.TclError, ValueError):
                rand_x = rand_y = 0
            unter.place(x=-rand_x, y=-rand_y, width=2 * rand_x, height=2 * rand_y, relwidth=1.0, relheight=1.0)
            unter._sb_rand = (rand_x, rand_y)               # type: ignore[attr-defined]
            unter.lower()
            # Klicks und Ablagen auf dem Unterlegbild gelten dem Rahmen darunter.
            unter.bindtags((str(rahmen),) + tuple(unter.bindtags()))
            rahmen._sb_unter = unter                        # type: ignore[attr-defined]
            unter._sb_schluessel = None                     # type: ignore[attr-defined]
            if rahmen in self._dnd:
                art, befehl = self._dnd[rahmen]
                try:
                    unter.drop_target_register(art)         # type: ignore[attr-defined]
                    unter.dnd_bind("<<Drop>>", befehl)      # type: ignore[attr-defined]
                except Exception as exc:                    # noqa: BLE001
                    logger.debug("Ablegen auf dem Unterlegbild nicht verfuegbar: %s", exc)
        # Ganz unten: Ein ``lower()`` am Kind (verdecktes Vorbauen) schiebt es sonst unter das Unterlegbild.
        try:
            stapel = rahmen.tk.splitlist(rahmen.tk.call("winfo", "children", str(rahmen)))
            if stapel and str(stapel[0]) != str(unter):
                unter.lower()
        except tk.TclError:
            pass
        rand = getattr(unter, "_sb_rand", (0, 0))
        schluessel = (b, h) + self._lage(rahmen) + self._bildstand
        if unter._sb_schluessel == schluessel:
            return
        # Eine Karte (``_sb_karte``) bringt ihr eigenes Bild mit: der getoente Ausschnitt mit runden Ecken.
        foto = self._foto(rahmen, b + 2 * rand[0], h + 2 * rand[1], (-rand[0], -rand[1]),
                          funktion=getattr(rahmen, "_sb_bild", None))
        if foto is None:
            unter.configure(image="")
        else:
            unter._sb_foto = foto                           # type: ignore[attr-defined]
            unter.configure(image=foto)
        unter._sb_schluessel = schluessel                   # type: ignore[attr-defined]

    def _rollflaeche(self, leinwand: tk.Canvas) -> None:
        """Eine rollbare Flaeche (Leinwand mit einem Fenster): der Inhalt fuellt sie mindestens aus - unten kein Grund."""
        if not leinwand.winfo_ismapped():
            return
        eintraege = [i for i in leinwand.find_all() if leinwand.type(i) == "window"]
        if len(eintraege) != 1:
            return
        kennung = eintraege[0]
        try:
            inhalt = leinwand.nametowidget(leinwand.itemcget(kennung, "window"))
        except (KeyError, tk.TclError):
            return
        hoch = int(leinwand.winfo_height())
        if hoch <= 1:
            return
        soll = max(int(inhalt.winfo_reqheight()), hoch)
        try:
            ist = int(float(leinwand.itemcget(kennung, "height") or 0))
        except ValueError:
            ist = 0
        if ist != soll:
            leinwand.itemconfigure(kennung, height=soll)
        if not getattr(leinwand, "_sb_rollt", False):
            leinwand._sb_rollt = True                       # type: ignore[attr-defined]
            alt = str(leinwand.cget("yscrollcommand"))
            if alt:
                def _gerollt(*a: Any, _alt: str = alt, _lw: tk.Canvas = leinwand) -> None:
                    try:
                        _lw.tk.call(_alt, *a)
                    finally:
                        self.planen()
                leinwand.configure(yscrollcommand=_gerollt)

    # ------------------------------------------------------------------
    # Gezeichnete Teile
    # ------------------------------------------------------------------
    def _karte(self, karte: "raster.RundeKarte") -> None:
        if not karte.winfo_ismapped():
            return
        b, h = int(karte.winfo_width()), int(karte.winfo_height())
        if b < 4 or h < 4:
            return
        schluessel = (b, h) + self._lage(karte) + self._bildstand
        if getattr(karte, "_sb_schluessel", None) == schluessel:
            return
        karte._sb_schluessel = schluessel                   # type: ignore[attr-defined]
        karte.neu_malen()

    def _haken(self, haken: tk.Canvas) -> None:
        """Haken und Drehknoepfe des Hauptprogramms holen sich den Bildausschnitt selbst (``_rund_hintergrund``)."""
        if not haken.winfo_ismapped():
            return
        b, h = int(haken.winfo_width()), int(haken.winfo_height())
        if b <= 1 or h <= 1:
            return
        if getattr(haken, "_hintergrund", None) is None:
            haken._hintergrund = self.g._rund_hintergrund   # type: ignore[attr-defined]
            haken._sb_schluessel = None                     # type: ignore[attr-defined]
        schluessel = (b, h) + self._lage(haken) + self._bildstand
        if getattr(haken, "_sb_schluessel", None) == schluessel:
            return
        haken._sb_schluessel = schluessel                   # type: ignore[attr-defined]
        haken.nachziehen()                                  # type: ignore[attr-defined]

    def _leinwand(self, leinwand: tk.Canvas) -> None:
        if not leinwand.winfo_ismapped():
            return
        b, h = int(leinwand.winfo_width()), int(leinwand.winfo_height())
        if b <= 1 or h <= 1:
            return
        if not getattr(leinwand, "_sb_haengt", False):
            original = leinwand._zeichnen                   # type: ignore[attr-defined]

            def _gezeichnet(_o=original, _l=leinwand) -> None:
                _o()
                self._leinwand_unterlegen(_l)

            leinwand._zeichnen = _gezeichnet                # type: ignore[attr-defined]
            leinwand._sb_haengt = True                      # type: ignore[attr-defined]
        schluessel = (b, h) + self._lage(leinwand) + self._bildstand
        if getattr(leinwand, "_sb_schluessel", None) == schluessel:
            return
        leinwand._sb_schluessel = schluessel                # type: ignore[attr-defined]
        foto = self._foto(leinwand, b, h)
        leinwand._sb_foto = foto                            # type: ignore[attr-defined]
        self._leinwand_unterlegen(leinwand)

    @staticmethod
    def _leinwand_unterlegen(leinwand: tk.Canvas) -> None:
        foto = getattr(leinwand, "_sb_foto", None)
        try:
            leinwand.delete("sb_unter")
            if foto is not None:
                leinwand.create_image(0, 0, image=foto, anchor="nw", tags="sb_unter")
                leinwand.tag_lower("sb_unter")
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Beschriftungen
    # ------------------------------------------------------------------
    def _text(self, label: tk.Label) -> str:
        name = str(label.cget("textvariable") or "")
        if name:
            try:
                return str(label.getvar(name))
            except tk.TclError:
                return ""
        return str(label.cget("text"))

    def _natuerlich(self, label: tk.Label, text: str) -> tuple:
        """Wie gross das Label fuer seinen Text ist - gemessen an einem Zwilling, der nie angezeigt wird."""
        zwilling = self._zwilling
        if zwilling is None or not zwilling.winfo_exists():
            zwilling = tk.Label(self.rahmen)
            zwilling._sb_eigen = True                       # type: ignore[attr-defined]
            self._zwilling = zwilling
        optionen = {name: label.cget(name) for name in ("font", "wraplength", "justify", "anchor")}
        # Mit den Massen, die das Label vor dem Unterlegen hatte: Ein Bild im Label bekommt Rand und Polsterung
        # zusaetzlich (sonst saehe man einen Kasten ringsum) - sie stecken deshalb im Bild.
        optionen.update(label._sb_mass)                    # type: ignore[attr-defined]
        zwilling.configure(text=text, image="", compound="none", textvariable="", **optionen)
        return int(zwilling.winfo_reqwidth()), int(zwilling.winfo_reqheight())

    def _zurueckgenommen(self, label: tk.Label, breite_natuerlich: int) -> None:
        """Ein Label, das seine Zeile ausfuellte, behaelt die Groesse seines Textes - und seinen Platz (Anker)."""
        if getattr(label, "_sb_schmal", False):
            return
        verwalter = label.winfo_manager()
        anker = str(label.cget("anchor"))
        try:
            if verwalter == "pack":
                info = label.pack_info()
                fuellen = str(info.get("fill", "none"))
                if fuellen in ("x", "both"):
                    label.pack_configure(fill="y" if fuellen == "both" else "none", anchor=anker)
            elif verwalter == "grid":
                info = label.grid_info()
                kante = str(info.get("sticky", ""))
                if "e" in kante and "w" in kante:
                    rest = kante.replace("e", "").replace("w", "")
                    seite = "".join(z for z in anker if z in "ew")
                    label.grid_configure(sticky=rest + seite)
        except tk.TclError:
            return
        label._sb_schmal = True                             # type: ignore[attr-defined]

    def _beschriftung(self, label: tk.Label) -> None:
        if not label.winfo_ismapped():
            return
        if str(label.cget("image")) and getattr(label, "_sb_foto", None) is None:
            return                                          # ein eigenes Bild (Cover): nicht anfassen
        if not getattr(label, "_sb_haengt", False):
            label._sb_haengt = True                         # type: ignore[attr-defined]
            label._sb_foto = None                           # type: ignore[attr-defined]
            label._sb_schluessel = None                     # type: ignore[attr-defined]
            label._sb_mass = {n: label.cget(n) for n in ("padx", "pady", "bd", "highlightthickness", "width", "height")}  # type: ignore[attr-defined]
            label.tk.call(str(label), "configure", "-padx", 0, "-pady", 0, "-bd", 0, "-highlightthickness", 0)
            original = label.configure

            def _configure(cnf: Any = None, _o=original, _l=label, **kw: Any) -> Any:
                ergebnis = _o(cnf, **kw) if cnf else _o(**kw)
                if any(k in kw for k in ("text", "font", "wraplength", "image", "width", "padx", "pady")) or cnf:
                    self.planen()
                return ergebnis

            label.configure = _configure                    # type: ignore[assignment]
            label.config = _configure                       # type: ignore[assignment]
            name = str(label.cget("textvariable") or "")
            if name:
                befehl = label.register(lambda *_a: self.planen())
                try:
                    label.tk.call("trace", "add", "variable", name, "write", befehl)
                    label.bind("<Destroy>", lambda _e, n=name, b=befehl, l=label: self._spur_loesen(l, n, b), add="+")
                except tk.TclError:
                    pass
        text = self._text(label)
        b, h = self._natuerlich(label, text)
        if label.winfo_width() > b + 2:
            self._zurueckgenommen(label, b)
        if b <= 2 or h <= 2:
            if label._sb_foto is not None:                  # type: ignore[attr-defined]
                label._sb_foto = None                       # type: ignore[attr-defined]
                label._sb_schluessel = None                 # type: ignore[attr-defined]
                label.tk.call(str(label), "configure", "-image", "", "-width", label._sb_mass["width"],   # type: ignore[attr-defined]
                              "-height", label._sb_mass["height"])                                      # type: ignore[attr-defined]
            return
        schluessel = (text, b, h) + self._lage(label) + self._bildstand
        if label._sb_schluessel == schluessel:             # type: ignore[attr-defined]
            # Hat jemand das Bild zwischendurch weggenommen (``image=""``), kommt es neu.
            if label._sb_foto is None or str(label.cget("image")) == str(label._sb_foto):   # type: ignore[attr-defined]
                return
        foto = self._foto(label, b, h)
        if foto is None:
            label._sb_foto = None                           # type: ignore[attr-defined]
            label.configure(image="")
            label._sb_schluessel = schluessel               # type: ignore[attr-defined]
            return
        label._sb_foto = foto                               # type: ignore[attr-defined]
        label._sb_schluessel = schluessel                   # type: ignore[attr-defined]
        mass = label._sb_mass                               # type: ignore[attr-defined]
        # Mit einem Bild zaehlen ``width``/``height`` in Pixeln, nicht in Zeichen: Eine feste Zeichenbreite (Prozentzahl,
        # ``width=6``) wuerde sonst zu sechs Punkten - das Bild hat schon genau die Groesse des Labels.
        feste = ("-width", b) if str(mass["width"]) not in ("0", "") else ()
        feste += ("-height", h) if str(mass["height"]) not in ("0", "") else ()
        label.tk.call(str(label), "configure", "-image", str(foto), "-compound", "center", *feste)

    @staticmethod
    def _spur_loesen(label: tk.Label, name: str, befehl: str) -> None:
        try:
            label.tk.call("trace", "remove", "variable", name, "write", befehl)
        except tk.TclError:
            pass
