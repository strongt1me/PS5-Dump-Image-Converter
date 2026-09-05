"""Generischer Parser/Writer für flache `key=value`-Konfigurationsdateien.

Deckt das Format ab, das PS5-Payloads wie ShadowMountPlus und MicroMount für ihre
`config.ini` verwenden: eine Zeile pro Eintrag, `#`/`;` leiten Kommentarzeilen ein,
keine `[Abschnitte]`. Kommentare/Formatierung sind beim Schreiben bewusst auf das
Nötigste reduziert - für den PS5-seitigen Parser zählen nur die reinen
`key=value`-Paare, nicht die kosmetische Gruppierung des Referenz-Tools.
"""
from __future__ import annotations


#: Die Schlüssel, die in einer ``config.ini`` **mehrfach aktiv** stehen dürfen –
#: eine Zeile je Suchpfad, je Abbild, je Titel.
#:
#: Die Liste dient der **Anzeige** im Editor: Nur benannte Schlüssel werden zu
#: einer bearbeitbaren Zeile zusammengezogen. Ob ein Schlüssel tatsächlich
#: mehrfach dasteht, entscheidet daneben weiterhin :func:`mehrfach_schluessel`
#: an dem, was in der Datei steht – MicroMount benutzt denselben Editor mit
#: eigenen Schlüsseln, und die nächste Payload-Fassung kann weitere bringen.
WIEDERHOLBARE_SCHLUESSEL: tuple[str, ...] = (
    "scanpath",
    "image_ro",
    "image_rw",
    "image_sector",
    "kstuff_delay",
    "kstuff_no_pause",
    "global_fakelib_exclude",
)

#: Womit mehrere Werte in **einer** Editorzeile getrennt werden.
#:
#: Weder der Doppelpunkt noch das bloße Leerzeichen kämen infrage: Der Wert von
#: ``image_sector`` trägt selbst einen Doppelpunkt (``<datei>:<größe>``), und
#: Dateinamen dürfen Leerzeichen enthalten. Der senkrechte Strich ist in
#: Dateinamen unter Windows verboten und auf den Datenträgern der Konsole nicht
#: gebräuchlich.
MEHRFACH_TRENNER = " | "


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


def parse_flat_ini_multi(text: str) -> dict[str, list[str]]:
    """Wie :func:`parse_flat_ini`, aber ohne Werte zu verlieren.

    Sieben Schlüssel der ShadowMount+-Konfiguration sind ausdrücklich
    wiederholbar (siehe :data:`WIEDERHOLBARE_SCHLUESSEL`). Wer sie in ein
    gewöhnliches Wörterbuch liest, behält genau den letzten Wert; drei
    Suchpfade werden so zu einem, und der Anwender merkt nichts davon, weil
    die Zeilenzahl gleich bleibt.

    Returns:
        Je Schlüssel die Werte in der Reihenfolge ihres Auftretens.
    """
    ergebnis: dict[str, list[str]] = {}
    for rohzeile in text.splitlines():
        zeile = rohzeile.strip()
        if not zeile or zeile.startswith(("#", ";")) or "=" not in zeile:
            continue
        schluessel, _, wert = zeile.partition("=")
        schluessel = schluessel.strip()
        if not schluessel:
            continue
        ergebnis.setdefault(schluessel, []).append(wert.strip())
    return ergebnis


def fuer_anzeige(mehrfach: dict[str, list[str]]) -> dict[str, str]:
    """Macht aus :func:`parse_flat_ini_multi` eine Zeile je Schlüssel.

    Wiederholbare Schlüssel werden mit :data:`MEHRFACH_TRENNER` verbunden,
    alle übrigen behalten ihren letzten Wert – so, wie
    :func:`parse_flat_ini` es auch getan hätte.

    Der Editor hält seine Werte als Zeichenketten, und das ist keine
    Kleinigkeit: Eine Liste in seiner Tabelle reicht Tk an Tcl weiter, und
    aus ``["a b.img:4096", "c.img:512"]`` wird dort ``{a b.img:4096}
    c.img:512`` – geschweifte Klammern, sobald ein Dateiname ein Leerzeichen
    trägt.
    """
    ergebnis: dict[str, str] = {}
    for schluessel, werte in mehrfach.items():
        if schluessel in WIEDERHOLBARE_SCHLUESSEL:
            ergebnis[schluessel] = MEHRFACH_TRENNER.join(werte)
        elif werte:
            ergebnis[schluessel] = werte[-1]
    return ergebnis


def fuer_datei(anzeige: dict[str, str]) -> dict[str, "str | list[str]"]:
    """Zerlegt die Anzeigezeilen wiederholbarer Schlüssel wieder in Listen.

    Gegenstück zu :func:`fuer_anzeige`, gedacht als letzter Schritt vor
    :func:`merge_flat_ini`. Leere Teilstücke fallen weg: Ein ``"a | "`` soll
    eine Zeile ergeben und nicht zwei, von denen die zweite eine bestehende
    auskommentiert.

    Ein Schlüssel, dessen Zeile ganz leer ist, bleibt eine leere
    Zeichenkette – das heißt für :func:`merge_flat_ini` weiterhin
    "auskommentieren" und nicht "eine leere Liste schreiben".
    """
    ergebnis: dict[str, "str | list[str]"] = {}
    for schluessel, wert in anzeige.items():
        if schluessel not in WIEDERHOLBARE_SCHLUESSEL:
            ergebnis[schluessel] = wert
            continue
        teile = [t.strip() for t in str(wert).split(MEHRFACH_TRENNER.strip())]
        teile = [t for t in teile if t]
        ergebnis[schluessel] = teile if teile else ""
    return ergebnis


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


def merge_flat_ini(original: str, data: dict[str, "str | list[str]"],
                   header_comment: str = "") -> str:
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
      * Bei einem wiederholbaren Schlüssel darf die **Liste** länger sein als
        die Vorlage Zeilen hat; was darüber hinausgeht, kommt in den
        Anhängeblock.

    Args:
        original: Der unveränderte Text der geladenen Datei.
        data: Schlüssel/Wert-Paare aus dem Editor. Eine Liste setzt mehrere
            Zeilen desselben Schlüssels der Reihe nach.
        header_comment: Überschrift für den Block neu angehängter Einträge.

    Returns:
        Der zusammengeführte Text mit abschließendem Zeilenumbruch.
    """
    behandelt: set[str] = set()
    verbraucht: dict[str, int] = {}
    ausgabe: list[str] = []
    # Welche Schlüssel stehen mehrfach aktiv in der Vorlage? Für sie darf ein
    # einzelner Wert nicht in jede Zeile geschrieben werden - siehe unten.
    wiederholt = mehrfach_schluessel(original)

    for zeile in original.splitlines():
        inhalt = zeile.strip()
        if not inhalt or inhalt.startswith(("#", ";")) or "=" not in inhalt:
            ausgabe.append(zeile)
            continue
        schluessel = inhalt.split("=", 1)[0].strip()
        alter_wert = inhalt.split("=", 1)[1].strip()
        if schluessel in data:
            behandelt.add(schluessel)
            roh = data[schluessel]
            if isinstance(roh, (list, tuple)):
                # Eine Liste ordnet der Reihe nach zu: erste Fundstelle
                # bekommt den ersten Wert, zweite den zweiten. Erst damit ist
                # ein wiederholbarer Schlüssel überhaupt bearbeitbar.
                nummer = verbraucht.get(schluessel, 0)
                verbraucht[schluessel] = nummer + 1
                neuer_wert = roh[nummer] if nummer < len(roh) else None
            elif schluessel in wiederholt and str(roh) != "":
                # Mehrfach in der Vorlage, aber nur EIN nicht-leerer Wert
                # übergeben: Der Aufrufer kann diese Zeilen nicht
                # auseinanderhalten. Würde er hier gesetzt, bekäme jede Zeile
                # denselben - aus drei Suchpfaden würde dreimal derselbe. Bei
                # "scanpath" hieße das, dass an den übrigen Orten nie wieder
                # gesucht wird; die Anleitung sagt: "If at least one
                # scanpath=... is present, only those custom paths are used."
                # Also unangetastet lassen.
                #
                # Ein LEERER Wert ist davon ausgenommen: Er lässt sich nicht
                # missverstehen. Wer die Zeile im Editor leert, will alle
                # Vorkommen abschalten - und bekam bis dahin gar nichts, weil
                # dieser Zweig auch ihn abfing.
                ausgabe.append(zeile)
                continue
            else:
                neuer_wert = roh
            if neuer_wert is None or str(neuer_wert) == "":
                ausgabe.append(f"# {schluessel}={alter_wert}")
            else:
                ausgabe.append(f"{schluessel}={neuer_wert}")
        else:
            ausgabe.append(f"# {inhalt}")

    neue = [(k, v) for k, v in data.items()
            if k not in behandelt and v is not None and str(v) != ""]

    # ÜBERZÄHLIGE LISTENWERTE. Trägt die Vorlage zwei aktive
    # ``image_sector``-Zeilen und der Editor drei Werte, ginge der dritte
    # stillschweigend verloren: Die Schleife oben ordnet nur den vorhandenen
    # Zeilen zu und trägt den Schlüssel dabei in ``behandelt`` ein - damit
    # überspränge ihn der Anhängeblock. Die Zeilenzahl bliebe gleich, also
    # fiele es niemandem auf; dieselbe Sorte Verlust wie bei
    # :func:`parse_flat_ini`.
    #
    # Nur für Schlüssel, die wirklich schon dastanden: Ein Schlüssel ohne
    # aktive Zeile geht durch ``neue`` und wird dort vollständig
    # ausgeschrieben - er darf hier nicht ein zweites Mal erscheinen.
    ueberzaehlig: list[tuple[str, str]] = []
    for schluessel, wert in data.items():
        if schluessel not in behandelt or not isinstance(wert, (list, tuple)):
            continue
        for einzeln in list(wert)[verbraucht.get(schluessel, 0):]:
            if einzeln is not None and str(einzeln) != "":
                ueberzaehlig.append((schluessel, str(einzeln)))

    if neue or ueberzaehlig:
        if ausgabe and ausgabe[-1].strip():
            ausgabe.append("")
        for kommentarzeile in header_comment.splitlines():
            ausgabe.append(f"# {kommentarzeile}" if kommentarzeile else "#")
        for schluessel, wert in neue:
            if isinstance(wert, (list, tuple)):
                for einzeln in wert:
                    if einzeln is not None and str(einzeln) != "":
                        ausgabe.append(f"{schluessel}={einzeln}")
            else:
                ausgabe.append(f"{schluessel}={wert}")
        for schluessel, einzeln in ueberzaehlig:
            ausgabe.append(f"{schluessel}={einzeln}")

    return "\n".join(ausgabe) + "\n"


def render_flat_ini(data: dict[str, "str | list[str]"],
                    header_comment: str = "") -> str:
    """Rendert ein Dict als `key=value`-Textdatei. Leere Werte werden übersprungen.

    Eine Liste ergibt **eine Zeile je Wert** – sonst stünde dort die
    Python-Schreibweise ``scanpath=['/mnt/usb0', '/data/games']``, und die
    Konsole läse einen einzigen, unsinnigen Pfad.
    """
    lines: list[str] = []
    if header_comment:
        for comment_line in header_comment.splitlines():
            lines.append(f"# {comment_line}" if comment_line else "#")
        lines.append("")
    for key, value in data.items():
        if isinstance(value, (list, tuple)):
            for einzeln in value:
                if einzeln is not None and str(einzeln) != "":
                    lines.append(f"{key}={einzeln}")
            continue
        if value is None or value == "":
            continue
        lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"
