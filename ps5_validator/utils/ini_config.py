"""Generischer Parser/Writer für flache `key=value`-Konfigurationsdateien.

Deckt das Format ab, das PS5-Payloads wie ShadowMountPlus und MicroMount für ihre
`config.ini` verwenden: eine Zeile pro Eintrag, `#`/`;` leiten Kommentarzeilen ein,
keine `[Abschnitte]`. Kommentare/Formatierung sind beim Schreiben bewusst auf das
Nötigste reduziert - für den PS5-seitigen Parser zählen nur die reinen
`key=value`-Paare, nicht die kosmetische Gruppierung des Referenz-Tools.
"""
from __future__ import annotations


def parse_flat_ini(text: str) -> dict[str, str]:
    """Parst eine flache INI-artige Textdatei in ein Dict. Wiederholte Schlüssel
    überschreiben den vorherigen Wert (letzter gewinnt), da die PS5-seitigen
    Parser der Referenz-Tools ebenso funktionieren."""
    result: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        result[key] = value.strip()
    return result


def mehrfach_schluessel(text: str) -> set[str]:
    """Schlüssel, die in ``text`` auf mehr als einer Zeile stehen.

    Das flache Format kennt wiederholbare Schlüssel; die Anleitung von
    ShadowMount+ führt sieben davon (``scanpath``, ``image_ro``, ``image_rw``,
    ``image_sector``, ``global_fakelib_exclude``, ``kstuff_no_pause``,
    ``kstuff_delay``). Ein Wörterbuch kann sie nicht abbilden - für
    :func:`parse_flat_ini` gewinnt der letzte, die übrigen fallen weg.

    Aufgezählt wird hier nicht nach Namen, sondern nach dem, was wirklich
    dasteht: Eine feste Liste ginge an der nächsten Payload-Fassung vorbei,
    und MicroMount benutzt denselben Editor mit eigenen Schlüsseln.
    """
    gesehen: set[str] = set()
    mehrfach: set[str] = set()
    for rohzeile in text.splitlines():
        zeile = rohzeile.strip()
        if not zeile or zeile.startswith(("#", ";")) or "=" not in zeile:
            continue
        schluessel = zeile.split("=", 1)[0].strip()
        if not schluessel:
            continue
        if schluessel in gesehen:
            mehrfach.add(schluessel)
        gesehen.add(schluessel)
    return mehrfach


def merge_flat_ini(original: str, data: dict[str, str], header_comment: str = "") -> str:
    """Schreibt Werte in einen bestehenden INI-Text, ohne dessen Aufbau zu verlieren.

    `render_flat_ini` baut die Datei aus dem Wörterbuch neu auf – Kommentare,
    Leerzeilen und auskommentierte Vorlagen gehen dabei verloren. Genau das ist
    bei den Konfigurationen auf der Konsole heikel: `/data/shadowmount/config.ini`
    ist eine 146-zeilige Vorlage, in der alle Parameter als Kommentar erklärt
    sind und (noch) keiner aktiv ist. Ein Rückschreiben hätte daraus eine
    dreizeilige Datei gemacht und die gesamte Dokumentation gelöscht.

    Diese Funktion bearbeitet stattdessen den vorhandenen Text:
      * Kommentare, Leerzeilen und unbekannte Zeilen bleiben unverändert.
      * Ein bestehender Eintrag `key=alt` bekommt den neuen Wert.
      * Ein im Editor geleerter oder entfernter Eintrag wird auskommentiert,
        nicht gelöscht – auf der Konsole ist das umkehrbar.
      * Neue Einträge werden am Ende angehängt.

    Args:
        original: Der unveränderte Text der geladenen Datei.
        data: Schlüssel/Wert-Paare aus dem Editor.
        header_comment: Überschrift für den Block neu angehängter Einträge.

    Returns:
        Der zusammengeführte Text mit abschließendem Zeilenumbruch.
    """
    behandelt: set[str] = set()
    ausgabe: list[str] = []
    # Wiederholbare Schlüssel bleiben unangetastet - siehe unten.
    wiederholt = mehrfach_schluessel(original)

    for zeile in original.splitlines():
        inhalt = zeile.strip()
        if not inhalt or inhalt.startswith(("#", ";")) or "=" not in inhalt:
            ausgabe.append(zeile)
            continue
        schluessel = inhalt.split("=", 1)[0].strip()
        alter_wert = inhalt.split("=", 1)[1].strip()
        if schluessel in wiederholt:
            # Steht der Schlüssel mehrfach da, kann das Wörterbuch ihn nicht
            # abbilden: parse_flat_ini behält nur den letzten Wert. Würde er
            # hier gesetzt, bekäme JEDE seiner Zeilen denselben - aus drei
            # Suchpfaden würde dreimal derselbe. Bei "scanpath" heißt das,
            # dass an den übrigen Orten nie wieder gesucht wird; die Anleitung
            # sagt: "If at least one scanpath=... is present, only those custom
            # paths are used." Solche Zeilen bleiben deshalb wörtlich stehen -
            # was der Editor nicht darstellen kann, darf er nicht anfassen.
            behandelt.add(schluessel)
            ausgabe.append(zeile)
            continue
        if schluessel in data:
            behandelt.add(schluessel)
            neuer_wert = data[schluessel]
            if neuer_wert is None or str(neuer_wert) == "":
                ausgabe.append(f"# {schluessel}={alter_wert}")
            else:
                ausgabe.append(f"{schluessel}={neuer_wert}")
        else:
            ausgabe.append(f"# {inhalt}")

    neue = [(k, v) for k, v in data.items()
            if k not in behandelt and v is not None and str(v) != ""]
    if neue:
        if ausgabe and ausgabe[-1].strip():
            ausgabe.append("")
        for kommentarzeile in header_comment.splitlines():
            ausgabe.append(f"# {kommentarzeile}" if kommentarzeile else "#")
        for schluessel, wert in neue:
            ausgabe.append(f"{schluessel}={wert}")

    return "\n".join(ausgabe) + "\n"


def render_flat_ini(data: dict[str, str], header_comment: str = "") -> str:
    """Rendert ein Dict als `key=value`-Textdatei. Leere Werte werden übersprungen."""
    lines: list[str] = []
    if header_comment:
        for comment_line in header_comment.splitlines():
            lines.append(f"# {comment_line}" if comment_line else "#")
        lines.append("")
    for key, value in data.items():
        if value is None or value == "":
            continue
        lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"
