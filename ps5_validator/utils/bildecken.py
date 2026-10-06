# -*- coding: utf-8 -*-
"""Runde Ecken fuer Spielbilder - wie die Kacheln im Homescreen der PS5 (Wunsch des Nutzers vom 06.10.2026).

Tk kennt keine Durchsichtigkeit gegenueber dem, was hinter einem Label liegt: Ein Bild mit Alphakanal zeigt in
den durchsichtigen Ecken die Hintergrundfarbe des Labels. Deshalb wird das Bild hier gleich auf seinen Grund
gesetzt - eine Farbe oder der passende Ausschnitt des Hintergrundbilds (Seitenleiste). Die Ecken werden vierfach
ueberabgetastet gezeichnet, damit die Rundung glatt wird und nicht treppt.
"""
from __future__ import annotations

from PIL import Image, ImageDraw

#: Radius im Verhaeltnis zur kuerzeren Kante. Die Kacheln im Homescreen der PS5 liegen bei rund 7-8 %.
RADIUS_ANTEIL = 0.075

_UEBERABTASTUNG = 4


def maske(groesse: tuple[int, int], radius: int) -> Image.Image:
    """Graustufenmaske (255 innen, 0 in den Ecken) mit geglaetteter Rundung."""
    breite, hoehe = groesse
    gross = Image.new("L", (breite * _UEBERABTASTUNG, hoehe * _UEBERABTASTUNG), 0)
    ImageDraw.Draw(gross).rounded_rectangle(
        (0, 0, gross.width - 1, gross.height - 1), radius=radius * _UEBERABTASTUNG, fill=255)
    return gross.resize((breite, hoehe), Image.LANCZOS)


def radius_fuer(groesse: tuple[int, int], anteil: float = RADIUS_ANTEIL) -> int:
    return max(2, round(min(groesse) * anteil))


def runde_ecken(bild: Image.Image, grund=None, anteil: float = RADIUS_ANTEIL) -> Image.Image:
    """Das Bild mit runden Ecken.

    Args:
        bild: Das fertig skalierte Bild.
        grund: ``None`` - Ergebnis mit Alphakanal (RGBA); eine Farbe (``"#RRGGBB"`` oder Tupel) oder ein
            gleich grosses Bild - Ergebnis als RGB, die Ecken zeigen diesen Grund.
        anteil: Radius im Verhaeltnis zur kuerzeren Kante.
    """
    rgba = bild.convert("RGBA")
    rund = maske(rgba.size, radius_fuer(rgba.size, anteil))
    alpha = Image.new("L", rgba.size, 0)
    alpha.paste(rgba.getchannel("A"), mask=rund)
    rgba.putalpha(alpha)
    if grund is None:
        return rgba
    if isinstance(grund, Image.Image):
        unten = grund.convert("RGBA").resize(rgba.size) if grund.size != rgba.size else grund.convert("RGBA")
    else:
        unten = Image.new("RGBA", rgba.size, grund)
    return Image.alpha_composite(unten, rgba).convert("RGB")
