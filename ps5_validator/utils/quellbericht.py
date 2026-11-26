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


#: Dieselben Namen kurz, wie sie vor einer Fassung stehen (``ampr-emu-ng 0.5.0``, ``AMPR EMU 0.3.6.6``).
_LAUFZEITEN_KURZ = {"zstd": "ampr-emu-ng", "other": "AMPR EMU", "forge_release": "ampr_emu", "forge_trace": "ampr_emu (Trace)"}


def laufzeit_name(fakten) -> str:
    """Die Laufzeit im Spiel mit ihrer Fassung, wie sie ein Anwender liest: ``ampr-emu-ng 0.5.0``, ``AMPR EMU 0.3.6.6`` (ohne Fassung: nur der Name)."""
    name = _LAUFZEITEN_KURZ.get(str(fakten.laufzeit or "").strip().lower(), "AMPR EMU")
    version = str(fakten.laufzeit_version or "").strip()
    return "%s %s" % (name, version) if version else name


def _ersetzt_beim_umwandeln(fakten) -> bool:
    """Ersetzt Dump Forge die Laufzeit des Spiels, wenn es die Quelle selbst umwandelt (``.pkg`` direkt in ein Abbild)?

    Anders als :attr:`forge_cli.QuellFakten.laufzeit_ersetzt` (Paketbau: ein gepacktes Spiel entpackt das Programm dort ohnehin) zaehlt
    hier auch ein gepacktes Spiel - der direkte Weg reicht kein Entpacken mit.
    """
    return (str(fakten.laufzeit_aktion or "") == "replace"
            and str(fakten.laufzeit or "").strip().lower() not in ("", "none"))


def laufzeit_neu_name(fakten) -> str:
    """Forges eigene Laufzeit, die es an die Stelle der des Spiels setzt.

    Bis Forge 0.5.7 ``ampr_emu 0.4.2.1`` (``shipped_runtime_version``; ohne Fassung: ``ampr_emu``). Seit 0.6.0 liefert Forge nur noch
    ampr-emu-ng mit und setzt es bei jeder Umwandlung ein (gemessen 26.11.2026: "replacing the game's runtime ... with the bundled
    ampr-emu-ng 0.5.1"); ``shipped_runtime_version`` nennt dort weiter die alte Nummer und gilt nicht mehr. Erkannt wird 0.6.0 an
    ``pkg_runtime_action``, das es vorher nicht gab - die Fassung von NG nennt ``inspect`` nicht.
    """
    if str(getattr(fakten, "laufzeit_aktion_paket", "") or ""):
        return "ampr-emu-ng"
    version = str(fakten.laufzeit_neu or "").strip()
    return "ampr_emu %s" % version if version else "ampr_emu"


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


def zeilen(fakten, t: Callable[..., str], konsole: str = "", forge_ergaenzt_ampr: bool = False,
           forge_wandelt: bool = False) -> "list[Zeile]":
    """Die Zeilen des Berichts zu ``fakten`` (:class:`forge_cli.QuellFakten`), eine je Schluessel.

    Args:
        fakten: was Forges ``inspect`` ueber die Quelle sagt.
        t: Uebersetzung (``Schluessel, **Werte`` -> Text).
        konsole: die Firmware der Konsole als Text (``"12.00"``; ``"7.99"`` = nur die Hauptversion bekannt), ``""`` =
            unbekannt. Ohne sie steht bei BACKPORT nur, was das Spiel verlangt.
        forge_ergaenzt_ampr: Das Paket baut Dump Forge, und es legt AMPR EMU fuer ein Spiel, das ``libSceAmpr`` laedt,
            selbst dazu - ein fehlender AMPR EMU ist dann nur ein Hinweis, nichts, was der Anwender einbauen muss.
        forge_wandelt: Dump Forge schreibt das Abbild selbst aus der Quelle (``convert x.pkg --to ffpkg|exfat``). Auch dort setzt
            es seine Laufzeit an die des Spiels: "ampr-emu-ng goes into a game only by packing: any other job puts the release
            runtime in its place" (Forge ``lz4.rs``, ``Runtime::action`` - dieselbe Regel, die ``inspect`` als ``runtime_action``
            nennt). Ohne diese Zeile stand dort "[OK] vorhanden (ampr-emu-ng)", und im Abbild steckte danach ampr_emu.
    """
    liste: list[Zeile] = []

    # AMPR EMU: braucht das Spiel libSceAmpr, und bringt es einen Ersatz mit?
    paket_ohne = bool(forge_ergaenzt_ampr and getattr(fakten, "paket_ohne_laufzeit", False))
    if fakten.ampr_fehlt is True and paket_ohne:
        # Forge ab 0.6.0: Ein .pkg traegt keine AMPR-Laufzeit - ein fehlender AMPR EMU ist beim Paketbau kein Mangel, und Forge legt
        # auch keinen dazu (vorher: ``bericht.ampr_forge``).
        liste.append(Zeile("ampr", STUFE_HINWEIS, t("bericht.ampr_paket_ohne")))
    elif fakten.ampr_fehlt is True and forge_ergaenzt_ampr:
        liste.append(Zeile("ampr", STUFE_HINWEIS, t("bericht.ampr_forge")))
    elif fakten.ampr_fehlt is True:
        liste.append(Zeile("ampr", STUFE_FEHLT, t("bericht.ampr_fehlt")))
    elif fakten.ampr_importiert and paket_ohne and fakten.laufzeit_entfaellt:
        # Forge ab 0.6.0: Die Laufzeit des Spiels bleibt beim Paketbau draussen - nur ein Hinweis, die Rueckfrage dazu stellt das
        # Fenster (``Ps5PkgFenster._laufzeit_fragen``).
        liste.append(Zeile("ampr", STUFE_HINWEIS, t("bericht.ampr_entfaellt", alt=laufzeit_name(fakten))))
    elif fakten.ampr_importiert and forge_ergaenzt_ampr and fakten.laufzeit_ersetzt:
        # Ein Paket: Dump Forge setzt seine eigene Laufzeit an die des Spiels (auch ampr-emu-ng) - nur ein Hinweis, die Rueckfrage
        # dazu stellt das Fenster (``Ps5PkgFenster._laufzeit_fragen``).
        liste.append(Zeile("ampr", STUFE_HINWEIS,
                           t("bericht.ampr_ersetzt", alt=laufzeit_name(fakten), neu=laufzeit_neu_name(fakten))))
    elif fakten.ampr_importiert and forge_wandelt and _ersetzt_beim_umwandeln(fakten):
        # Auch ein gepacktes Spiel: Forges ``runtime_action`` ist das, was eine einfache Umwandlung tut (``inspect.rs``: bei LZ4-Packs
        # ``action(.., packs)``, bei zstd-Packs ``zstd_action`` - dort kommt Forges mitgeliefertes ampr-emu-ng hinein, nicht ampr_emu).
        neu = "ampr-emu-ng" if fakten.gepackt == "zstd" else laufzeit_neu_name(fakten)
        liste.append(Zeile("ampr", STUFE_HINWEIS,
                           t("bericht.ampr_ersetzt_umwandeln", alt=laufzeit_name(fakten), neu=neu)))
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
    if fakten.backport_schon_da(konsole):
        liste.append(Zeile("backport", STUFE_OK, t("bericht.backport_da")))
    elif not verlangt:
        liste.append(Zeile("backport", STUFE_HINWEIS, t("bericht.backport_unbekannt")))
    elif not konsole:
        liste.append(Zeile("backport", STUFE_HINWEIS, t("bericht.backport_konsole_unbekannt", spiel=verlangt)))
    elif fakten.backport_noetig(konsole):
        # Ohne gelesenes SDK der Programme (verschluesseltes Paket, fremdes Verfahren, unlesbares Abbild) urteilt nur die param.json -
        # das sagt die Zeile, statt wie ein gemessenes Urteil auszusehen (bei einem schon herabgesetzten Spiel waere es ein Fehlalarm).
        # Gemessen heisst: die eboot.bin gelesen oder Forges backport_firmware (alle Programme) - die Module allein (sce_module) nicht.
        gemessen = getattr(fakten, "eboot_sdk", "?") or getattr(fakten, "backport_firmware", "")
        schluessel = "bericht.backport_fehlt" if gemessen else "bericht.backport_fehlt_param"
        liste.append(Zeile("backport", STUFE_FEHLT,
                           t(schluessel, spiel=verlangt, konsole=konsole_anzeige(konsole))))
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
