# -*- coding: utf-8 -*-
"""Ausgabename per Vorlage (nach Dump Forge, Nutzerwahl 13.11.2026: "Ausgabename per Vorlage").

Der Name des Ergebnisses ist bisher der Name der Quelle. Mit einer Vorlage entsteht er aus den Angaben des Spiels::

    {title} [{title_id}] v{version}   ->   Astro Bot [PPSA01234] v1.0.0

Teile (``{...}``): ``name`` (der eigene Name der Quelle, ohne Endung), ``title`` (Spieltitel), ``title_id``
(``PPSA01234``; ``titleid`` gilt ebenso), ``version`` (``1.8.0``), ``region`` (``EU``/``US``/...), ``fw`` (Mindest-
Firmware, ``9.00``), ``pack`` (``zstd``/``lz4``, bei einem Spiel ohne Asset-Pack leer). Dazwischen darf beliebiger Text
stehen. Jeder Teil hoechstens einmal; mindestens ``name``, ``title`` oder ``title_id`` muss vorkommen.

Aufgeraeumt wird nur der Text der Vorlage, nie ein Wert: Ein leerer Teil faellt weg, ein dadurch leeres ``[]`` oder ``()``
ebenfalls, eine Folge gleicher Trenner (``-``, ``_``, Leerzeichen) wird einer, und am Anfang und Ende gehen ``-``, ``_``,
``.`` und Leerzeichen weg.

Die Vorgabe ``{name}`` aendert nichts: Der Name der Quelle bleibt, wie er ist; ist er zu lang, warnt die Vorabpruefung
(``vorabpruefung.ausgabename_befund``). Ein **erzeugter** Name dagegen wird auf die Hoechstlaenge des Zielformats
gekuerzt (63 Bytes, bei ``.ffpfsc`` 58, nach dem Einhaengepfad von ShadowMount+) - zuerst der Titel. Ist der Name schon vergeben,
fragt der Lauf wie immer "ueberschreiben?" (in der Sammelkonvertierung: "namensgleich" uebersprungen).

Das Modul rechnet nur: keine Einstellungen, keine Dateien, kein Tk. Die Angaben kommen als Woerterbuch wie aus
``abbild_metadaten`` (``title``, ``title_id``, ``version``, ``required_firmware``, ``content_id``, ``region``).
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ps5_validator.utils import bibliothek, vorabpruefung

#: Die Vorgabe: der Name der Quelle bleibt.
STANDARD = "{name}"

#: Beispiele fuer die Auswahl in der Oberflaeche.
BEISPIELE: tuple[str, ...] = (
    "{name}",
    "[{title}]-[{title_id}]",
    "{title_id}",
    "{title} [{title_id}]",
    "{title} [{title_id}] v{version}",
)

#: Die Teile einer Vorlage.
TEILE: tuple[str, ...] = ("name", "title", "title_id", "version", "region", "fw", "pack")

#: Andere Schreibweisen derselben Teile.
_ALIASE = {"titleid": "title_id", "title-id": "title_id"}

#: So lang darf eine Vorlage hoechstens sein (UTF-8-Bytes).
VORLAGE_MAX = 128

#: In einem Dateinamen nicht erlaubte Zeichen (Windows und exFAT).
VERBOTEN = frozenset('/\\:*?"<>|')

#: Namen, die als Trenner behandelt werden.
_TRENNER = frozenset("-_ ")


@dataclass(frozen=True)
class Problem:
    """Warum eine Vorlage keinen Namen ergibt. ``art``: lang, offen, zu, unbekannt, doppelt, zeichen, steuerzeichen,
    braucht_namen, leer; ``wert``: der Teil oder das Zeichen, um das es geht."""
    art: str
    wert: str = ""


@dataclass(frozen=True)
class Ergebnis:
    """Der erzeugte Name (ohne Endung), ob er gekuerzt werden musste, und das Problem, falls die Vorlage nicht taugt."""
    name: str
    gekuerzt: bool = False
    problem: Problem | None = None


def _teil(token: str) -> str | None:
    token = _ALIASE.get(token, token)
    return token if token in TEILE else None


def zerlegen(vorlage: str) -> "list[tuple[bool, str]] | Problem":
    """Zerlegt eine Vorlage in ``(True, Zeichen)`` fuer eigenen Text und ``(False, Teil)`` fuer einen Teil.

    Gibt ein ``Problem`` zurueck, wenn die Vorlage nicht taugt.
    """
    if not vorlage:
        return Problem("leer")
    if len(vorlage.encode("utf-8")) > VORLAGE_MAX:
        return Problem("lang")
    stuecke: list[tuple[bool, str]] = []
    benutzt: set[str] = set()
    lauf = ""                                   # der eigene Text seit dem letzten Teil, als Ganzes in NFC

    def abschliessen() -> None:
        nonlocal lauf
        stuecke.extend((True, z) for z in unicodedata.normalize("NFC", lauf))
        lauf = ""

    i = 0
    while i < len(vorlage):
        zeichen = vorlage[i]
        if zeichen == "{":
            ende = vorlage.find("}", i)
            if ende < 0:
                return Problem("offen")
            token = vorlage[i + 1:ende]
            teil = _teil(token)
            if teil is None:
                return Problem("unbekannt", token)
            if teil in benutzt:
                return Problem("doppelt", teil)
            benutzt.add(teil)
            abschliessen()
            stuecke.append((False, teil))
            i = ende + 1
            continue
        if zeichen == "}":
            return Problem("zu")
        if unicodedata.category(zeichen) in ("Cc", "Cf"):          # auch Format-Zeichen (U+202E, Null-Breite-Leerzeichen)
            return Problem("steuerzeichen")
        if zeichen in VERBOTEN:
            return Problem("zeichen", zeichen)
        lauf += zeichen
        i += 1
    abschliessen()
    if not benutzt & {"name", "title", "title_id"}:
        return Problem("braucht_namen")
    return stuecke


def vorlage_pruefen(vorlage: str) -> Problem | None:
    """``None``, wenn die Vorlage einen Namen ergeben kann, sonst der Grund."""
    ergebnis = zerlegen(vorlage)
    return ergebnis if isinstance(ergebnis, Problem) else None


def bereinigen(wert: str) -> str:
    """Macht aus einem Wert (Titel, ...) einen Namensteil: ohne unzulaessige Zeichen, NFC, einfache Leerzeichen."""
    text = unicodedata.normalize("NFC", str(wert or ""))
    # Auch Format-Zeichen (Cf: Null-Breite-Leerzeichen, Umkehr der Schreibrichtung U+202E) fallen weg: Sie machen einen Namen unlesbar oder taeuschen.
    text = "".join(z for z in text if z not in VERBOTEN and unicodedata.category(z) not in ("Cc", "Cf"))
    return " ".join(text.split())


def werte_aus_angaben(angaben: Mapping[str, Any], *, name: str = "", pack: str = "") -> dict[str, str]:
    """Die Werte der Teile aus den Angaben eines Spiels. Was fehlt, ist leer (der Teil faellt dann weg)."""
    angaben = angaben or {}
    kennung = str(angaben.get("title_id") or "").strip().upper()
    if not bibliothek._KENNUNG_RE.fullmatch(kennung):
        kennung = ""
    fassung = bibliothek.fassung_kurz(str(angaben.get("version") or "").strip())
    if fassung.lower() in bibliothek._LEER:
        fassung = ""
    titel = str(angaben.get("title") or "").strip()
    return {
        "name": bereinigen(name),
        "title": "" if titel.lower() in bibliothek._LEER else bereinigen(titel),
        "title_id": kennung,
        "version": bereinigen(fassung),
        "region": bibliothek.region_kurz({"content_id": angaben.get("content_id"), "region": angaben.get("region")}),
        "fw": bibliothek.firmware_kurz(str(angaben.get("required_firmware") or angaben.get("fw") or "")),
        "pack": bereinigen(pack),
    }


def kuerzen(text: str, grenze: int) -> str:
    """``text`` auf hoechstens ``grenze`` UTF-8-Bytes, an einer Zeichengrenze, ohne ``.`` und Leerzeichen am Ende."""
    ergebnis = ""
    benutzt = 0
    for zeichen in text:
        n = len(zeichen.encode("utf-8"))
        if benutzt + n > grenze:
            break
        ergebnis += zeichen
        benutzt += n
    return ergebnis.rstrip(". ")


def rendern(vorlage: str, werte: Mapping[str, str]) -> str:
    """Setzt die Werte in die Vorlage ein und raeumt deren eigenen Text auf. Eine ungueltige Vorlage ergibt ``""``."""
    zerlegt = zerlegen(vorlage)
    if isinstance(zerlegt, Problem):
        return ""
    # (eigener Text?, Text): Ein Wert bleibt unberuehrt, nur der Text der Vorlage wird aufgeraeumt.
    stuecke: list[tuple[bool, str]] = [
        (eigen, inhalt if eigen else str(werte.get(inhalt, "") or "")) for eigen, inhalt in zerlegt]
    stuecke = [(e, t) for e, t in stuecke if e or t]
    # Ein Trenner im Text der Vorlage unmittelbar hinter einer oeffnenden oder vor einer schliessenden Klammer ("[ 9.00]") faellt weg.
    stuecke = [s for k, s in enumerate(stuecke)
               if not (s[0] and s[1] in _TRENNER
                       and ((k > 0 and stuecke[k - 1][0] and stuecke[k - 1][1] in ("[", "("))
                            or (k + 1 < len(stuecke) and stuecke[k + 1][0] and stuecke[k + 1][1] in ("]", ")"))))]
    i = 0
    while i + 1 < len(stuecke):
        (e1, t1), (e2, t2) = stuecke[i], stuecke[i + 1]
        if e1 and e2 and t1 + t2 in ("[]", "()"):
            del stuecke[i:i + 2]
            i = max(0, i - 1)
        else:
            i += 1
    stuecke = [s for k, s in enumerate(stuecke)
               if not (k > 0 and s[0] and s[1] in _TRENNER and stuecke[k - 1][0] and stuecke[k - 1][1] == s[1])]

    def rand(s: tuple[bool, str]) -> bool:
        return s[0] and (s[1] in _TRENNER or s[1] == ".")

    ende = len(stuecke)
    while ende > 0 and rand(stuecke[ende - 1]):
        ende -= 1
    anfang = 0
    while anfang < ende and rand(stuecke[anfang]):
        anfang += 1
    return "".join(t for _, t in stuecke[anfang:ende])


def grenze_fuer(zielformat: str) -> int | None:
    """Die Hoechstlaenge des Namens ohne Endung fuer dieses Zielformat, oder ``None`` (Ordner, PKG: keine)."""
    return vorabpruefung.name_max(zielformat) if zielformat in vorabpruefung.ABBILD_FORMATE else None


#: Namen, die Windows als Geraet liest (auch mit Endung): ``CON``, ``PRN``, ``AUX``, ``NUL``, ``COM1`` ... ``LPT9``.
_GERAETE = frozenset({"CON", "PRN", "AUX", "NUL"} | {"COM%d" % n for n in range(1, 10)} | {"LPT%d" % n for n in range(1, 10)})


def _windows_tauglich(text: str, grenze: "int | None" = None) -> "tuple[str, bool]":
    """Kein Punkt oder Leerzeichen am Ende, und kein Geraetename: ``Aux`` wird ``Aux_`` (ein Ordner dieses Namens laesst sich unter Windows nicht anlegen).

    ``grenze``: Hoechstlaenge in UTF-8-Bytes. Der Unterstrich macht den Namen ein Zeichen laenger; reicht die Grenze dann nicht mehr, faellt
    am Ende des Namens etwas weg (der Unterstrich steht vorn und bleibt). Rueckgabe: der Name und ob dabei gekuerzt wurde.
    """
    text = text.rstrip(". ")
    gekuerzt = False
    stamm, punkt, rest = text.partition(".")
    if stamm.strip().upper() in _GERAETE:
        # Windows liest ``Aux.Game`` wie ``AUX``: der Unterstrich gehoert direkt hinter den Geraetenamen, vor den ersten Punkt.
        text = stamm.rstrip() + "_" + punkt + rest
        if grenze is not None and len(text.encode("utf-8")) > grenze:
            text = kuerzen(text, grenze)
            gekuerzt = True
    return text, gekuerzt


def ausgabename(vorlage: str, angaben: Mapping[str, Any], *, name: str, pack: str = "", zielformat: str = "") -> Ergebnis:
    """Der Name des Ergebnisses ohne Endung.

    Die Vorgabe ``{name}`` gibt den Namen der Quelle unveraendert zurueck. Fuer jede andere Vorlage gilt: Taugt sie
    nicht, ist ``problem`` gesetzt und ``name`` der der Quelle; ergibt sie nichts (alle benoetigten Angaben fehlen),
    bleibt ebenfalls der Name der Quelle; ist das Ergebnis laenger als das Zielformat zulaesst, wird zuerst der Titel
    gekuerzt, dann der ganze Name.
    """
    vorlage = vorlage or STANDARD
    if vorlage == STANDARD:
        return Ergebnis(name=name)
    problem = vorlage_pruefen(vorlage)
    if problem is not None:
        return Ergebnis(name=name, problem=problem)
    werte = werte_aus_angaben(angaben, name=name, pack=pack)
    # Liefert kein einziger Teil der Vorlage einen Wert (etwa "PS5 {title}" bei einem Spiel ohne lesbare param.json), bleibt der Name der
    # Quelle: Sonst hiessen alle solchen Quellen gleich ("PS5").
    # Nur die Teile, die das Spiel kennzeichnen (wie ``braucht_namen`` in ``zerlegen``): ``{pack}`` kommt aus der Auswahl und ist immer gesetzt,
    # ``{title} [{pack}]`` ergaebe sonst bei jeder Quelle ohne Angaben denselben Namen.
    zerlegt = zerlegen(vorlage)
    benutzt = ({inhalt for eigen, inhalt in zerlegt if not eigen} & {"name", "title", "title_id"}
               if not isinstance(zerlegt, Problem) else set())
    if not any(werte.get(teil) for teil in benutzt):
        return Ergebnis(name=name)
    text = rendern(vorlage, werte)
    if not text:
        return Ergebnis(name=name)
    grenze = grenze_fuer(zielformat)
    if grenze is None or len(text.encode("utf-8")) <= grenze:
        name_ok, gekuerzt = _windows_tauglich(text, grenze)
        return Ergebnis(name=name_ok, gekuerzt=gekuerzt)
    ueber = len(text.encode("utf-8")) - grenze
    if werte["title"]:
        titel = kuerzen(werte["title"], max(0, len(werte["title"].encode("utf-8")) - ueber))
        text = rendern(vorlage, {**werte, "title": titel})
    if len(text.encode("utf-8")) > grenze:
        text = kuerzen(text, grenze)
    return Ergebnis(name=_windows_tauglich(text, grenze)[0] or name, gekuerzt=True)
