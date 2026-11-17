# -*- coding: utf-8 -*-
"""Die Pruefung der Quelle in Worten: was Dump Forge ueber ein Spiel sagt und was davon fehlt.

Nutzerwunsch 17.11.2026 (Seite 7, PKG / FPKG): Der Anwender soll sehen, ob das Programm selbst erkannt hat, was im Spiel
liegt - AMPR EMU, Asset-Packs (LZ4, zstd), PlayGo, DLC, BACKPORT - und ob etwas eingebaut werden muss. Dieselben Zeilen
stehen im Protokoll bei jedem Lauf (Aufgaben 1 bis 6 und Seite 7) und in der Rueckfrage vor dem Paketbau; sie kommen aus einer
Stelle, damit beide nie voneinander abweichen. Was schon eingebaut ist, steht - wie in den Aufgaben 1 bis 6 - schon nach der
Wahl der Quelle als ``[Pruefung]``-Zeilen im Protokoll (``PS5ConverterGUI._quelle_einbauten_zeilen``).

Rein: nichts startet, nichts wird gelesen. Die Fakten liefert :func:`ps5_validator.utils.forge_cli.quellfakten_lesen`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

#: Die Quelle hat, was sie braucht - oder braucht nichts davon.
STUFE_OK = "ok"
#: Das Spiel braucht es, und es liegt nicht darin.
STUFE_FEHLT = "fehlt"
#: Nicht zu sagen oder nur eine Auskunft.
STUFE_HINWEIS = "hinweis"

#: Die Reihenfolge der Zeilen - dieselbe wie bei den Kaestchen der Karte.
SCHLUESSEL = ("ampr", "packs", "playgo", "dlc", "backport")

#: Forges Namen der Laufzeit in ``fakelib/libSceAmpr.sprx`` (``lz4.runtime``), wie sie der Anwender liest.
_LAUFZEITEN = {"zstd": "ampr-emu-ng (zstd)", "other": "AMPR EMU", "forge_release": "Dump Forge",
               "forge_trace": "Dump Forge (Trace)"}


@dataclass(frozen=True)
class Zeile:
    """Eine Zeile des Berichts: ``schluessel`` aus :data:`SCHLUESSEL`, ``stufe`` eine der ``STUFE_*``, ``text`` fertig."""

    schluessel: str
    stufe: str
    text: str


def konsole_anzeige(firmware: str) -> str:
    """``"7.99"`` (nur die Hauptversion ist bekannt) wird ``"7.xx"``, alles andere bleibt (wie ``_konsole_fw_anzeige``)."""
    text = str(firmware or "")
    return text[:-2] + "xx" if text.endswith(".99") else text


def zeilen(fakten, t: Callable[..., str], konsole: str = "", forge_ergaenzt_ampr: bool = False) -> "list[Zeile]":
    """Die Zeilen des Berichts zu ``fakten`` (:class:`forge_cli.QuellFakten`), eine je Schluessel.

    Args:
        fakten: was Forges ``inspect`` ueber die Quelle sagt.
        t: Uebersetzung (``Schluessel, **Werte`` -> Text).
        konsole: die Firmware der Konsole als Text (``"12.00"``; ``"7.99"`` = nur die Hauptversion bekannt), ``""`` =
            unbekannt. Ohne sie steht bei BACKPORT nur, was das Spiel verlangt.
        forge_ergaenzt_ampr: Das Paket baut Dump Forge, und es legt AMPR EMU fuer ein Spiel, das ``libSceAmpr`` laedt,
            selbst dazu - ein fehlender AMPR EMU ist dann nur ein Hinweis, nichts, was der Anwender einbauen muss.
    """
    liste: list[Zeile] = []

    # AMPR EMU: braucht das Spiel libSceAmpr, und bringt es einen Ersatz mit?
    if fakten.ampr_fehlt is True and forge_ergaenzt_ampr:
        liste.append(Zeile("ampr", STUFE_HINWEIS, t("bericht.ampr_forge")))
    elif fakten.ampr_fehlt is True:
        liste.append(Zeile("ampr", STUFE_FEHLT, t("bericht.ampr_fehlt")))
    elif fakten.ampr_importiert:
        laufzeit = _LAUFZEITEN.get(str(fakten.laufzeit or "").lower(), "AMPR EMU")
        liste.append(Zeile("ampr", STUFE_OK, t("bericht.ampr_da", laufzeit=laufzeit)))
    elif fakten.ampr_fehlt is False:
        liste.append(Zeile("ampr", STUFE_OK, t("bericht.ampr_nicht_noetig")))
    else:
        liste.append(Zeile("ampr", STUFE_HINWEIS, t("bericht.ampr_unbekannt")))

    # Asset-Packs: schon gepackt (LZ4 oder zstd) oder die Dateien liegen einzeln.
    packs = {"lz4": "bericht.packs_lz4", "zstd": "bericht.packs_zstd"}.get(fakten.gepackt, "bericht.packs_keine")
    liste.append(Zeile("packs", STUFE_OK, t(packs)))

    # PlayGo: Inhalt in der Quelle und der Stub dazu.
    if fakten.playgo_fehlt:
        liste.append(Zeile("playgo", STUFE_FEHLT, t("bericht.playgo_fehlt", merkmal=fakten.playgo_merkmal)))
    elif "playgo" in fakten.emulatoren:
        liste.append(Zeile("playgo", STUFE_OK, t("bericht.playgo_da")))
    else:
        liste.append(Zeile("playgo", STUFE_OK, t("bericht.playgo_nicht_noetig")))

    # DLC: Zusatzinhalte im Spiel und ob DLC EMU sie an der Konsole meldet.
    if fakten.dlc_fehlt:
        liste.append(Zeile("dlc", STUFE_FEHLT, t("bericht.dlc_fehlt", merkmal=fakten.dlc_merkmal or "-")))
    elif fakten.dlc_vorhanden:
        liste.append(Zeile("dlc", STUFE_OK, t("bericht.dlc_da")))
    else:
        liste.append(Zeile("dlc", STUFE_OK, t("bericht.dlc_nicht_noetig")))

    # BACKPORT: verlangt das Spiel mehr, als die Konsole hat?
    verlangt = fakten.verlangt_text
    if fakten.backport_vorhanden:
        liste.append(Zeile("backport", STUFE_OK, t("bericht.backport_da")))
    elif not verlangt:
        liste.append(Zeile("backport", STUFE_HINWEIS, t("bericht.backport_unbekannt")))
    elif not konsole:
        liste.append(Zeile("backport", STUFE_HINWEIS, t("bericht.backport_konsole_unbekannt", spiel=verlangt)))
    elif fakten.backport_noetig(konsole):
        liste.append(Zeile("backport", STUFE_FEHLT,
                           t("bericht.backport_fehlt", spiel=verlangt, konsole=konsole_anzeige(konsole))))
    else:
        liste.append(Zeile("backport", STUFE_OK,
                           t("bericht.backport_nicht_noetig", spiel=verlangt, konsole=konsole_anzeige(konsole))))
    return liste


def fehlendes(liste: "list[Zeile]") -> "list[str]":
    """Die Schluessel der Zeilen, bei denen etwas fehlt (Reihenfolge wie :data:`SCHLUESSEL`)."""
    return [z.schluessel for z in liste if z.stufe == STUFE_FEHLT]


def protokoll(liste: "list[Zeile]", t: Callable[..., str]) -> "list[str]":
    """Die Zeilen fuers Protokoll: Titel, je Zeile ``[OK]``, ``[FEHLT]`` oder ``[HINWEIS]`` davor."""
    marke = {STUFE_OK: "[OK]", STUFE_FEHLT: "[FEHLT]", STUFE_HINWEIS: "[HINWEIS]"}
    return [t("bericht.titel")] + ["%s %s" % (marke.get(z.stufe, "[HINWEIS]"), z.text) for z in liste]
