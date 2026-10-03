# -*- coding: utf-8 -*-
"""Gezeichnetes fuer die Bibliothek - Bilder und Rechenregeln, ohne Tk.

Die Bibliothek zeigt ihre Titel als Karten: abgerundete Flaechen mit Titelbild,
Plaketten, Chips und Knoepfen. Tk kennt weder runde Ecken noch Verlaeufe noch
Schatten. Was rund und weich aussehen soll, wird hier mit PIL gezeichnet -
vierfach gross und dann verkleinert, sonst stehen die Ecken als Treppe da. Der
**Text bleibt Tk**: Schrift, Zeilenhoehe und Zeichensatz sind die des Programms,
und sie folgen der Anzeigeskalierung von selbst. Eine mit PIL gesetzte Schrift
sah unter Windows, Linux und macOS je anders aus oder fehlte ganz.

Gerechnet und gezeichnet wird hier, platziert im Hauptprogramm. Die Trennung ist
Absicht: Jede Regel laesst sich so mit erfundenen Zahlen und ohne Fenster
pruefen (``test_bibliothek_zeichnen.py``).

Drei Gruppen:

* Farben (``mischen``, ``farbton_verschieben``, ``chip_farben``,
  ``knopf_farben``): leiten alles aus der Palette des gewaehlten Designs ab -
  die Karten sind in jedem der vier Designs lesbar, ohne eigene Farbtabelle.
* Bilder (``rund_rechteck``, ``akzent_knopf``, ``poster_bild``, ``plakette``,
  ``chevron``): fertige RGBA-Bilder, die Tk mit seinem eigenen Alphakanal
  ueber die Flaeche legt.
* Raster (``spalten_berechnen``, ``chips_verteilen``, ``text_umbrechen``,
  ``KartenMasse``): wie viele Spalten, wo ein Chip umbricht, wo der Titel
  endet und wie hoch eine Karte wird.
"""
from __future__ import annotations

import colorsys
import functools
import math
from dataclasses import dataclass

from PIL import Image, ImageChops, ImageDraw, ImageFilter

try:                                                    # Pillow >= 9.1
    _LANCZOS = Image.Resampling.LANCZOS
except AttributeError:                                  # pragma: no cover - alte Pillow
    _LANCZOS = Image.LANCZOS                            # type: ignore[attr-defined]

#: Wie fein gezeichnet wird, bevor verkleinert wird. Dieselbe Zahl wie
#: ``PS5ConverterGUI._ECKE_FEIN`` bei den Kartenecken des Hauptbereichs.
UEBERABTASTUNG = 4


# ---------------------------------------------------------------------------
# Farben
# ---------------------------------------------------------------------------

def hex_zu_rgb(farbe: str) -> tuple[int, int, int]:
    """``#rrggbb`` (oder ``#rgb``) als Zahlentripel; alles andere als Schwarz."""
    text = str(farbe or "").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(zeichen * 2 for zeichen in text)
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except (ValueError, IndexError):
        return (0, 0, 0)


def rgb_zu_hex(rgb) -> str:
    """Zahlentripel als ``#rrggbb`` - jeder Wert auf 0..255 begrenzt."""
    r, g, b = (max(0, min(255, int(round(wert)))) for wert in tuple(rgb)[:3])
    return "#%02x%02x%02x" % (r, g, b)


def mischen(a: str, b: str, anteil: float) -> str:
    """``a`` zu ``anteil`` (0..1) in Richtung ``b`` gemischt: 0 = a, 1 = b."""
    t = max(0.0, min(1.0, float(anteil)))
    ra, rb = hex_zu_rgb(a), hex_zu_rgb(b)
    return rgb_zu_hex(tuple(x * (1.0 - t) + y * t for x, y in zip(ra, rb)))


def farbton_verschieben(farbe: str, grad: float) -> str:
    """Dreht den Farbton um ``grad`` Grad; Helligkeit und Saettigung bleiben.

    Aus dem Blau eines Designs wird so das Violett am Ende des Verlaufs
    ("Starten"), aus dem Tuerkis ein Blau - ohne dass jedes Design einen
    zweiten Farbwert braucht.
    """
    r, g, b = (wert / 255.0 for wert in hex_zu_rgb(farbe))
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    h = (h + grad / 360.0) % 1.0
    return rgb_zu_hex(tuple(wert * 255.0 for wert in colorsys.hsv_to_rgb(h, s, v)))


def helligkeit(farbe: str) -> float:
    """Wahrgenommene Helligkeit 0..1 (Rec. 709) - zum Entscheiden, ob ein Design dunkel ist."""
    r, g, b = hex_zu_rgb(farbe)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def ist_dunkel(palette: dict) -> bool:
    """Ob das Design eine dunkle Kartenflaeche hat (``bg_card``)."""
    return helligkeit(str(palette.get("bg_card", "#000000"))) < 0.5


def kontrastfarbe(grund: str) -> str:
    """Weiss oder Fast-Schwarz - was auf ``grund`` besser lesbar ist."""
    return "#ffffff" if helligkeit(grund) < 0.62 else "#101418"


def _leuchtdichte(farbe: str) -> float:
    def kanal(wert: int) -> float:
        v = wert / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = hex_zu_rgb(farbe)
    return 0.2126 * kanal(r) + 0.7152 * kanal(g) + 0.0722 * kanal(b)


def kontrastverhaeltnis(a: str, b: str) -> float:
    """Kontrastverhaeltnis zweier Farben nach WCAG 2 (1 = gleich, 21 = Schwarz auf Weiss)."""
    hell, dunkel = sorted((_leuchtdichte(a), _leuchtdichte(b)), reverse=True)
    return (hell + 0.05) / (dunkel + 0.05)


def lesbar_auf(text: str, fuellung: str, richtung: str, mindest: float = 4.5) -> str:
    """Zieht ``fuellung`` Schritt fuer Schritt nach ``richtung`` (Farbe), bis ``text`` darauf lesbar ist.

    Die Flaeche eines Chips ist ein Mischton aus Karte und Rollenfarbe. Bei
    einer mittelhellen Karte (das Design Metallisch) kam der Text darauf nur
    auf 3,3 : 1; die Flaeche wird dann dunkler, nicht der Text heller - so bleibt
    die Rollenfarbe erkennbar.
    """
    for _ in range(24):
        if kontrastverhaeltnis(text, fuellung) >= mindest:
            break
        fuellung = mischen(fuellung, richtung, 0.07)
    return fuellung


def chip_farben(palette: dict, art: str) -> dict:
    """Farben eines Chips: ``fuellung``, ``rand``, ``text`` und ``gestrichelt``.

    Arten: ``neutral`` (Format), ``ampr``, ``playgo``, ``backport``,
    ``assetpack``, ``unbekannt`` (gestrichelt, ohne Fuellung). Alles wird aus
    Kartenfarbe und den Rollenfarben des Designs gemischt: Eine Rolle, die in
    einem Design hell ist, bleibt es auch im Chip. (Die Plakette PS4/PS5 auf dem
    Titelbild ist ein eigenes Bild: ``plakette``.)
    """
    karte = str(palette.get("bg_card", "#1d1d23"))
    sekundaer = str(palette.get("fg_secondary", "#9a9ca6"))
    rollen = {"ampr": "fg_accent", "assetpack": "fg_accent",
              "playgo": "fg_success", "backport": "fg_warning"}
    dunkel = ist_dunkel(palette)
    richtung = "#000000" if dunkel else "#ffffff"
    if art in rollen:
        ton = str(palette.get(rollen[art], "#7fb2ff"))
        text = ton if dunkel else mischen(ton, "#000000", 0.25)
        return {"fuellung": lesbar_auf(text, mischen(karte, ton, 0.22 if dunkel else 0.16), richtung),
                "rand": mischen(karte, ton, 0.55 if dunkel else 0.45),
                "text": text, "gestrichelt": False}
    if art == "unbekannt":
        return {"fuellung": "", "rand": mischen(karte, sekundaer, 0.6),
                "text": sekundaer, "gestrichelt": True}
    # neutral - das Format. Etwas heller als die Karte, mit sichtbarem Rand.
    text = mischen(sekundaer, str(palette.get("fg_primary", "#ffffff")), 0.35)
    return {"fuellung": lesbar_auf(text, mischen(karte, sekundaer, 0.20), richtung),
            "rand": mischen(karte, sekundaer, 0.34), "text": text, "gestrichelt": False}


def knopf_farben(palette: dict, stil: str, zustand: str = "normal") -> dict:
    """Farben eines Knopfs in einem Zustand.

    ``stil``: ``akzent`` (Verlauf, "Starten"), ``flaeche`` und ``auswahl``
    (dunkle Flaeche mit Rand), ``chip`` (Filter, ausgeschaltet) und
    ``chip_an`` (Filter, gewaehlt). ``zustand``: ``normal``, ``hover``,
    ``gedrueckt``, ``gesperrt``.

    Returns:
        ``fuellung`` (bei ``akzent`` ``links``/``rechts`` statt dessen),
        ``rand``, ``text`` und ``glow`` (leer = kein Schein).
    """
    karte = str(palette.get("bg_card", "#1d1d23"))
    tief = str(palette.get("console_bg", "#121216"))
    rand = str(palette.get("border", "#34353d"))
    primaer = str(palette.get("fg_primary", "#f1f2f6"))
    sekundaer = str(palette.get("fg_secondary", "#9a9ca6"))
    akzent = str(palette.get("accent_btn", "#2e6be6"))
    akzent_hell = str(palette.get("fg_accent", "#7fb2ff"))
    dunkel = ist_dunkel(palette)

    if stil == "akzent":
        links, rechts = akzent, farbton_verschieben(akzent, 32.0)
        if zustand == "gesperrt":
            return {"links": mischen(karte, sekundaer, 0.16), "rechts": mischen(karte, sekundaer, 0.16),
                    "rand": mischen(rand, karte, 0.4), "text": mischen(sekundaer, karte, 0.30), "glow": ""}
        if zustand == "hover":
            links, rechts = mischen(links, "#ffffff", 0.16), mischen(rechts, "#ffffff", 0.16)
        elif zustand == "gedrueckt":
            links, rechts = mischen(links, "#000000", 0.20), mischen(rechts, "#000000", 0.20)
        return {"links": links, "rechts": rechts, "rand": "",
                "text": kontrastfarbe(mischen(links, rechts, 0.5)),
                "glow": akzent if zustand != "gedrueckt" else ""}

    if stil in ("chip_an",):
        fuellung = mischen(karte, akzent, 0.55 if dunkel else 0.95)
        umrandung = mischen(akzent, akzent_hell, 0.55)
        if zustand == "hover":
            fuellung = mischen(fuellung, "#ffffff", 0.10)
        text = kontrastfarbe(fuellung)
        return {"fuellung": fuellung, "rand": umrandung, "text": text, "glow": ""}

    # flaeche / auswahl / chip: dunkle Flaeche mit Rand
    fuellung = tief if stil != "chip" else mischen(tief, karte, 0.35)
    umrandung = rand
    text = primaer if stil != "chip" else mischen(primaer, sekundaer, 0.30)
    if zustand == "hover":
        fuellung = mischen(fuellung, akzent_hell, 0.10)
        umrandung = mischen(rand, akzent_hell, 0.55)
        text = primaer
    elif zustand == "gedrueckt":
        fuellung = mischen(fuellung, "#000000", 0.18) if dunkel else mischen(fuellung, "#000000", 0.08)
    elif zustand == "gesperrt":
        fuellung = mischen(karte, tief, 0.5)
        umrandung = mischen(rand, karte, 0.5)
        text = mischen(sekundaer, karte, 0.35)
    return {"fuellung": fuellung, "rand": umrandung, "text": text, "glow": ""}


# ---------------------------------------------------------------------------
# Bilder
# ---------------------------------------------------------------------------

def _rgba(farbe: str, alpha: int = 255) -> tuple[int, int, int, int]:
    r, g, b = hex_zu_rgb(farbe)
    return (r, g, b, max(0, min(255, int(alpha))))


def _maske(breite: int, hoehe: int, radius: float, ecken: tuple[bool, bool, bool, bool]
           = (True, True, True, True), ueber: int = UEBERABTASTUNG) -> "Image.Image":
    """Rundrechteck-Maske (``L``) in Zielgroesse, vierfach gezeichnet.

    ``ecken``: oben links, oben rechts, unten rechts, unten links - nicht
    gewaehlte bleiben eckig (das Titelbild ist nur oben rund).
    """
    gross = Image.new("L", (breite * ueber, hoehe * ueber), 0)
    zeichner = ImageDraw.Draw(gross)
    r = max(0.0, min(float(radius), breite / 2.0, hoehe / 2.0)) * ueber
    box = (0, 0, breite * ueber - 1, hoehe * ueber - 1)
    if r <= 0:
        zeichner.rectangle(box, fill=255)
    else:
        zeichner.rounded_rectangle(box, radius=r, fill=255, corners=ecken)
    return gross.resize((breite, hoehe), _LANCZOS)


def _rundpfad(breite: float, hoehe: float, radius: float, schritte: int = 12) -> list[tuple[float, float]]:
    """Stuetzpunkte der Randlinie eines Rundrechtecks, im Uhrzeigersinn ab oben links nach der Ecke."""
    r = max(0.0, min(radius, breite / 2.0, hoehe / 2.0))
    punkte: list[tuple[float, float]] = []
    mitten = ((breite - r, r, -90), (breite - r, hoehe - r, 0), (r, hoehe - r, 90), (r, r, 180))
    for cx, cy, start in mitten:
        for i in range(schritte + 1):
            winkel = math.radians(start + 90.0 * i / schritte)
            punkte.append((cx + r * math.cos(winkel), cy + r * math.sin(winkel)))
    punkte.append(punkte[0])
    return punkte


def _gestrichelt_zeichnen(bild: "Image.Image", breite: int, hoehe: int, radius: float, farbe: tuple,
                          strich: float, luecke: float, staerke: float, ueber: int) -> None:
    """Zeichnet die Randlinie als Strichfolge (auf das vierfach grosse Bild)."""
    zeichner = ImageDraw.Draw(bild)
    pfad = _rundpfad(breite * ueber - 1, hoehe * ueber - 1, radius * ueber, 16)
    laenge_strich, laenge_luecke = strich * ueber, luecke * ueber
    zu_laufen, malen = laenge_strich, True
    aktuell: list[tuple[float, float]] = [pfad[0]]
    for (x0, y0), (x1, y1) in zip(pfad, pfad[1:]):
        rest = math.hypot(x1 - x0, y1 - y0)
        if rest <= 0:
            continue
        dx, dy = (x1 - x0) / rest, (y1 - y0) / rest
        x, y = x0, y0
        while rest > 1e-6:
            schritt = min(rest, zu_laufen)
            x, y = x + dx * schritt, y + dy * schritt
            rest -= schritt
            zu_laufen -= schritt
            if malen:
                aktuell.append((x, y))
            if zu_laufen <= 1e-6:
                if malen and len(aktuell) > 1:
                    zeichner.line(aktuell, fill=farbe, width=max(1, int(round(staerke * ueber))),
                                  joint="curve")
                malen = not malen
                zu_laufen = laenge_strich if malen else laenge_luecke
                aktuell = [(x, y)] if malen else []
    if malen and len(aktuell) > 1:
        zeichner.line(aktuell, fill=farbe, width=max(1, int(round(staerke * ueber))), joint="curve")


def rund_rechteck(breite: int, hoehe: int, radius: float, fuellung: str = "", rand: str = "",
                  randbreite: float = 1.0, *, gestrichelt: bool = False, alpha: int = 255,
                  ueber: int = UEBERABTASTUNG) -> "Image.Image":
    """Ein abgerundetes Rechteck als RGBA-Bild: Fuellung, Rand innen.

    Leere ``fuellung`` heisst durchsichtig (nur der Rand), leerer ``rand`` kein
    Rand. ``gestrichelt`` zeichnet den Rand als Strichfolge (Chip
    "Anpassungen unbekannt"). Die vier Ecken sind weich geglaettet; ausserhalb
    der Rundung ist das Bild durchsichtig - Tk legt es mit dem eigenen
    Alphakanal auf die Flaeche dahinter, ohne dass die Ecken wissen muessen,
    was dort liegt.
    """
    breite, hoehe = max(2, int(breite)), max(2, int(hoehe))
    gross = Image.new("RGBA", (breite * ueber, hoehe * ueber), (0, 0, 0, 0))
    zeichner = ImageDraw.Draw(gross)
    r = max(0.0, min(float(radius), breite / 2.0, hoehe / 2.0)) * ueber
    box = (0, 0, breite * ueber - 1, hoehe * ueber - 1)
    if fuellung:
        zeichner.rounded_rectangle(box, radius=r, fill=_rgba(fuellung, alpha))
    if rand and randbreite > 0:
        if gestrichelt:
            _gestrichelt_zeichnen(gross, breite, hoehe, float(radius), _rgba(rand, alpha),
                                  strich=3.0, luecke=2.5, staerke=randbreite, ueber=ueber)
        else:
            zeichner.rounded_rectangle(box, radius=r, outline=_rgba(rand, alpha),
                                       width=max(1, int(round(randbreite * ueber))))
    return gross.resize((breite, hoehe), _LANCZOS)


def verlauf_rechteck(breite: int, hoehe: int, radius: float, links: str, rechts: str,
                     *, ueber: int = UEBERABTASTUNG) -> "Image.Image":
    """Ein abgerundetes Rechteck mit waagerechtem Farbverlauf (RGBA)."""
    breite, hoehe = max(2, int(breite)), max(2, int(hoehe))
    kurve = Image.new("RGB", (breite, 1))
    a, b = hex_zu_rgb(links), hex_zu_rgb(rechts)
    kurve.putdata([tuple(int(round(a[k] + (b[k] - a[k]) * (x / max(1, breite - 1)))) for k in range(3))
                   for x in range(breite)])
    flaeche = kurve.resize((breite, hoehe), Image.NEAREST).convert("RGBA")
    flaeche.putalpha(_maske(breite, hoehe, radius, ueber=ueber))
    return flaeche


def akzent_knopf(breite: int, hoehe: int, radius: float, links: str, rechts: str, glow: str = "",
                 *, glow_unschaerfe: float = 8.0, glow_versatz: float = 4.0, glow_staerke: float = 0.55,
                 rand_oben: float = 0.0) -> tuple["Image.Image", tuple[int, int]]:
    """Der Knopf "Starten": Verlauf mit weichem Schein darunter.

    Returns:
        ``(bild, (versatz_x, versatz_y))``. Das Bild ist groesser als der
        Knopf - der Schein braucht Platz um ihn herum. Der Knopf selbst sitzt
        im Bild bei ``(versatz_x, versatz_y)``; wer das Bild bei ``(x, y)``
        des Knopfes platzieren will, rueckt es um diesen Versatz nach links
        oben.
    """
    breite, hoehe = max(2, int(breite)), max(2, int(hoehe))
    if not glow:
        return verlauf_rechteck(breite, hoehe, radius, links, rechts), (0, 0)
    pad = int(math.ceil(glow_unschaerfe * 2.0))
    unten = pad + int(math.ceil(glow_versatz))
    oben = max(0, pad - int(math.floor(glow_versatz)))
    gesamt = Image.new("RGBA", (breite + 2 * pad, hoehe + oben + unten), (0, 0, 0, 0))
    schein = Image.new("L", gesamt.size, 0)
    schein.paste(_maske(breite, hoehe, radius), (pad, oben + int(round(glow_versatz))))
    schein = schein.filter(ImageFilter.GaussianBlur(glow_unschaerfe))
    schein = schein.point(lambda p: int(p * max(0.0, min(1.0, glow_staerke))))
    farbe = Image.new("RGBA", gesamt.size, _rgba(glow, 255))
    farbe.putalpha(schein)
    gesamt = Image.alpha_composite(gesamt, farbe)
    knopf = verlauf_rechteck(breite, hoehe, radius, links, rechts)
    gesamt.alpha_composite(knopf, (pad, oben))
    return gesamt, (pad, oben)


@functools.lru_cache(maxsize=16)
def _poster_maske(breite: int, hoehe: int, radius: float, ueber: int) -> "Image.Image":
    """Die Maske des Titelbilds (oben rund, unten eckig) - fuer alle Karten einer Groesse dieselbe.

    Gemerkt, weil jede Karte einer Bibliothek dieselbe braucht und das vierfache
    Zeichnen samt Verkleinern ein Drittel der Zeit eines Titelbilds kostet. Nie
    veraendern: Der Aufrufer legt sie nur ueber ein Bild.
    """
    return _maske(breite, hoehe, radius, (True, True, False, False), ueber)


def poster_bild(quelle: "Image.Image", breite: int, hoehe: int, radius: float,
                *, ueber: int = UEBERABTASTUNG) -> "Image.Image":
    """Das Titelbild einer Karte: formatfuellend zugeschnitten, oben abgerundet (RGBA).

    Ein Titelbild ist meist quadratisch (``icon0.png``, 512 x 512), manchmal
    nicht. Es wird wie ``object-fit: cover`` beschnitten - Mitte bleibt -,
    nie verzerrt. Unten bleibt es eckig: Dort schliesst die Karte an.
    """
    breite, hoehe = max(2, int(breite)), max(2, int(hoehe))
    bild = quelle.convert("RGBA")
    if bild.width <= 0 or bild.height <= 0:
        bild = Image.new("RGBA", (breite, hoehe), (0, 0, 0, 255))
    faktor = max(breite / bild.width, hoehe / bild.height)
    neu = (max(breite, int(round(bild.width * faktor))), max(hoehe, int(round(bild.height * faktor))))
    bild = bild.resize(neu, _LANCZOS)
    links, oben = (neu[0] - breite) // 2, (neu[1] - hoehe) // 2
    bild = bild.crop((links, oben, links + breite, oben + hoehe))
    maske = _poster_maske(breite, hoehe, float(radius), int(ueber))
    alt = bild.getchannel("A")
    bild.putalpha(ImageChops.multiply(alt, maske))
    return bild


def plakette(breite: int, hoehe: int, fuellung: str = "#0a0f1a", alpha: int = 205) -> "Image.Image":
    """Die Plakette PS4/PS5 oben links auf dem Titelbild: dunkel, halb durchsichtig, ganz rund."""
    return rund_rechteck(breite, hoehe, hoehe / 2.0, fuellung, "", alpha=alpha)


def chevron(groesse: int, farbe: str, staerke: float = 1.6, *, ueber: int = UEBERABTASTUNG) -> "Image.Image":
    """Der kleine Pfeil nach unten am Auswahlknopf (RGBA, quadratisch).

    Gezeichnet statt als Zeichen "v" oder Dreieck aus einer Schrift: Ein
    Zeichen aus einer Schrift sieht auf jedem System anders aus oder fehlt.
    """
    g = max(6, int(groesse))
    gross = Image.new("RGBA", (g * ueber, g * ueber), (0, 0, 0, 0))
    zeichner = ImageDraw.Draw(gross)
    s = g * ueber
    zeichner.line([(s * 0.18, s * 0.34), (s * 0.5, s * 0.68), (s * 0.82, s * 0.34)],
                  fill=_rgba(farbe), width=max(1, int(round(staerke * ueber))), joint="curve")
    return gross.resize((g, g), _LANCZOS)


# ---------------------------------------------------------------------------
# Raster
# ---------------------------------------------------------------------------

def spalten_berechnen(breite: int, mindest_karte: int, abstand: int, rand: int) -> tuple[int, int]:
    """Wie viele Spalten passen, und wie breit jede Karte wird.

    Die Karten fuellen die Breite: Bei mehr Platz wachsen sie, bis eine
    weitere Spalte hineinpasst. So steht rechts nie eine leere Flaeche.

    Returns:
        ``(spalten, kartenbreite)`` - mindestens eine Spalte, auch wenn die
        Flaeche schmaler als eine Karte ist (dann so breit wie die Flaeche).
    """
    nutz = int(breite) - 2 * int(rand)
    if nutz <= 0:
        return 1, max(1, int(mindest_karte))
    spalten = max(1, (nutz + abstand) // (mindest_karte + abstand))
    karte = (nutz - (spalten - 1) * abstand) // spalten
    return spalten, max(1, karte)


def text_umbrechen(text: str, messen, breite: int, max_zeilen: int = 2) -> list[str]:
    """Bricht ``text`` auf ``breite`` Pixel um - hoechstens ``max_zeilen`` Zeilen.

    ``messen(text) -> int`` ist die Breite in Pixeln (``tkfont.Font.measure``).
    Was nicht mehr hineinpasst, wird mit ``…`` abgeschlossen; ein Wort, das
    allein breiter ist als eine Zeile, wird mitten im Wort getrennt. Leerer
    Text ergibt keine Zeilen.
    """
    rest = str(text or "").split()
    if not rest or breite <= 0 or max_zeilen <= 0:
        return []
    zeilen: list[str] = []
    aktuell = ""
    while rest and len(zeilen) < max_zeilen:
        wort = rest[0]
        probe = wort if not aktuell else aktuell + " " + wort
        if messen(probe) <= breite:
            aktuell = probe
            rest.pop(0)
            continue
        if aktuell:                                     # die Zeile ist voll - das Wort kommt in die naechste
            zeilen.append(aktuell)
            aktuell = ""
            continue
        # Ein einzelnes, zu langes Wort: Zeichen fuer Zeichen trennen
        stueck = ""
        for zeichen in wort:
            if stueck and messen(stueck + zeichen) > breite:
                break
            stueck += zeichen
        zeilen.append(stueck)
        if len(stueck) < len(wort):
            rest[0] = wort[len(stueck):]
        else:
            rest.pop(0)
    if aktuell and len(zeilen) < max_zeilen:
        zeilen.append(aktuell)
        aktuell = ""
    # Was nach der letzten erlaubten Zeile noch uebrig ist, wird mit "…" angedeutet.
    if (rest or aktuell) and zeilen:
        letzte = zeilen[-1].rstrip(" …")
        while letzte and messen(letzte + "…") > breite:
            letzte = letzte[:-1].rstrip()
        zeilen[-1] = letzte + "…"
    return zeilen


def chips_verteilen(breiten: list[int], verfuegbar: int, abstand: int,
                    max_zeilen: int = 2) -> tuple[list[list[int]], int]:
    """Verteilt Chips der Reihe nach auf Zeilen - hoechstens ``max_zeilen``.

    Returns:
        ``(zeilen, ausgelassen)``: je Zeile die Nummern der Chips; ``ausgelassen``
        zaehlt die Chips, die in keine Zeile mehr passten. Ein Chip, der allein
        breiter ist als die Zeile, steht trotzdem allein in seiner Zeile - er
        wird beschnitten dargestellt, aber nicht weggelassen.
    """
    zeilen: list[list[int]] = [[]]
    benutzt = 0
    ausgelassen = 0
    for nummer, breite in enumerate(breiten):
        noetig = breite if not zeilen[-1] else abstand + breite
        if zeilen[-1] and benutzt + noetig > verfuegbar:
            if len(zeilen) >= max_zeilen:
                ausgelassen += 1
                continue
            zeilen.append([])
            benutzt = 0
            noetig = breite
        zeilen[-1].append(nummer)
        benutzt += noetig
    return ([zeile for zeile in zeilen if zeile], ausgelassen)


def chips_mit_rest(breiten: list[int], rest_breite, verfuegbar: int, abstand: int,
                   max_zeilen: int = 2) -> tuple[list[list[int]], int]:
    """Wie :func:`chips_verteilen`, laesst aber nichts still weg: Der Rest wird als ``+N`` angedeutet.

    Passen nicht alle Chips in ``max_zeilen`` Zeilen, werden so viele **von vorn** gezeigt,
    wie samt einem Rest-Chip hineinpassen - in der Reihenfolge der Vorlage, ohne dass ein
    schmaler spaeterer Chip den Platz eines uebersprungenen breiten nimmt.

    Args:
        breiten: Breite je Chip.
        rest_breite: ``(anzahl) -> int`` - Breite des Rest-Chips "+anzahl".
        verfuegbar: Breite einer Zeile.
        abstand: Abstand zwischen zwei Chips.
        max_zeilen: Hoechstens so viele Zeilen.

    Returns:
        ``(zeilen, versteckt)``. Die Rest-Chip hat die Nummer ``len(breiten)`` und steht als
        letzter in der letzten Zeile; ``versteckt`` ist, wie viele Chips er vertritt (0 = alle
        gezeigt, dann gibt es keinen Rest-Chip).
    """
    zeilen, ausgelassen = chips_verteilen(breiten, verfuegbar, abstand, max_zeilen)
    if not ausgelassen:
        return zeilen, 0
    for gezeigt in range(len(breiten) - 1, -1, -1):
        versteckt = len(breiten) - gezeigt
        probe, uebrig = chips_verteilen(list(breiten[:gezeigt]) + [int(rest_breite(versteckt))],
                                        verfuegbar, abstand, max_zeilen)
        if not uebrig:
            return ([[len(breiten) if nummer == gezeigt else nummer for nummer in zeile]
                     for zeile in probe], versteckt)
    return zeilen, 0                                    # unerreichbar: gezeigt=0 passt immer (ein Chip steht allein)


@dataclass(frozen=True)
class KartenAufteilung:
    """Wo in einer Karte was steht - alle Masse in Pixeln, von der Kartenkante aus."""

    breite: int
    hoehe: int
    innen_x: int           # linker Rand des Inhalts unter dem Titelbild
    innen_breite: int
    poster_hoehe: int
    titel_y: int
    titel_hoehe: int
    chips_y: int
    chips_hoehe: int
    info_y: int
    start_y: int
    aktion_y: int
    knopf_hoehe: int       # der Knopf "Infos & Metadaten"
    start_hoehe: int
    aktion_hoehe: int


@dataclass(frozen=True)
class KartenMasse:
    """Die Masse einer Karte bei einer Anzeigeskalierung.

    Alle Werte sind auf 100 % (96 dpi) geschrieben, wie sie auf dem Entwurf
    stehen, und werden mit ``faktor`` auf den Schirm umgerechnet (``tk
    scaling`` geteilt durch 96/72). Zeilenhoehen kommen gemessen herein - eine
    Schrift ist je System anders hoch.
    """

    faktor: float = 1.0
    titel_zeile: int = 20          # gemessene Zeilenhoehe der Titelschrift (Pixel, schon skaliert)
    chip_zeile: int = 24           # gemessene Hoehe eines Chips (Pixel, schon skaliert)
    titel_zeilen: int = 2
    chip_zeilen: int = 2

    def px(self, wert: float) -> int:
        return int(round(wert * self.faktor))

    @property
    def rand(self) -> int:
        """Abstand der Karten zum Rand der Flaeche: keiner.

        Die Seite hat ihren eigenen Rand, und die Kopfkarte darueber steht
        buendig mit der ersten Karte - ein eigener Rand des Rasters rueckte die
        Karten gegen die Kopfkarte ein (am Entwurf des Nutzers gemessen: beide
        beginnen am selben Pixel).
        """
        return 0

    @property
    def abstand(self) -> int:
        return self.px(16)

    @property
    def karte_min(self) -> int:
        return self.px(250)

    @property
    def ecke(self) -> int:
        return self.px(16)

    @property
    def polster(self) -> int:
        return self.px(16)

    @property
    def randbreite(self) -> int:
        """Platz fuer den Kartenrand: 2 Pixel bei jeder Skalierung.

        Der Rand ist im Normalfall nur 1 Pixel breit, gewaehlt 2 - der Platz
        ist immer da, damit eine Auswahl nichts verschiebt (das Titelbild
        beginnt in beiden Zustaenden an derselben Stelle).
        """
        return max(2, self.px(2))

    def aufteilen(self, breite: int) -> KartenAufteilung:
        """Zerlegt eine Karte der Breite ``breite`` in ihre Bereiche."""
        b = int(breite)
        rb = self.randbreite
        poster = max(1, b - 2 * rb)                                  # quadratisch, ohne den Rand
        innen_x = self.polster
        innen_b = max(1, b - 2 * self.polster)
        titel_y = rb + poster + self.px(14)
        titel_h = self.titel_zeile * self.titel_zeilen
        chips_y = titel_y + titel_h + self.px(10)
        chips_h = self.chip_zeile * self.chip_zeilen + self.px(6) * (self.chip_zeilen - 1)
        knopf_h, start_h, aktion_h = self.px(40), self.px(42), self.px(36)
        info_y = chips_y + chips_h + self.px(12)
        start_y = info_y + knopf_h + self.px(10)
        aktion_y = start_y + start_h + self.px(10)
        hoehe = aktion_y + aktion_h + self.polster
        return KartenAufteilung(
            breite=b, hoehe=hoehe, innen_x=innen_x, innen_breite=innen_b, poster_hoehe=poster,
            titel_y=titel_y, titel_hoehe=titel_h, chips_y=chips_y, chips_hoehe=chips_h,
            info_y=info_y, start_y=start_y, aktion_y=aktion_y, knopf_hoehe=knopf_h,
            start_hoehe=start_h, aktion_hoehe=aktion_h)
