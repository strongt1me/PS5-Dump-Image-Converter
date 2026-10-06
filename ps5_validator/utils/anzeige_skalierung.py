"""Skalierung und Aufloesung der Oberflaeche - die Rechenregeln, ohne Tk.

Das Programm passt sich dem Bildschirm von selbst an: ``tk scaling`` kommt vom
System, und alle Fenstergroessen richten sich nach dem, was Tk als Bildschirm
meldet. Dieses Modul haelt fest, was geschieht, wenn der Anwender davon
abweicht - von Hand, ueber die Einstellungen:

* **Skalierung** in Prozent, wie in der Windows-Anzeigeeinstellung
  (100 % = 96 dpi). Sie ersetzt ``tk scaling`` beim Start; Schrift und alle
  ueber ``knopfmass`` gerechneten Masse folgen ihr.
* **Aufloesung** in Pixeln. Sie ist die Bildschirmgroesse, die das Programm
  annimmt: Hintergrundbilder werden fuer sie bemessen, Fenster werden nie
  groesser als dieser Bildschirm, und ist er kleiner als der echte, oeffnet
  sich das Hauptfenster in seiner Groesse statt maximiert.

Beides gilt **nur, wenn der Anwender es gesetzt hat**. Fehlt der Wert in der
Einstellungsdatei oder ist er unbrauchbar, bleibt es bei der automatischen
Anpassung - ein verstuemmelter Wert darf nie dazu fuehren, dass die
Oberflaeche unbenutzbar wird.

Gerechnet wird hier, gemessen und gesetzt im Hauptprogramm. Die Trennung ist
Absicht: Jede Regel laesst sich so mit erfundenen Zahlen pruefen, ohne dass ein
Test ein Fenster oeffnen muss.
"""
from __future__ import annotations

import math
import re

#: Schluessel in der Einstellungsdatei. Fehlt der Wert (oder steht ``null``
#: darin), gilt die automatische Anpassung.
SCHLUESSEL_SKALIERUNG = "ui_skalierung"
SCHLUESSEL_AUFLOESUNG = "ui_aufloesung"

#: Bereich des Schiebereglers. Nach unten Schluss bei 100 %: Das ist der
#: unskalierte Windows-Schirm, auf dem die Oberflaeche seit jeher laeuft - die
#: Pixelmasse sind auf 125 % geschrieben und schrumpfen nicht (siehe
#: ``knopfmass``), nur die Schrift wird kleiner. Nach oben begrenzt
#: ``KNOPF_FAKTOR_MAX`` (2,5 x 125 % = rund 312 %) die Knopfmasse; darueber
#: waechst nur noch die Schrift.
SKALIERUNG_MIN = 100
SKALIERUNG_MAX = 300
SKALIERUNG_SCHRITT = 5

#: Tk rechnet 72 Punkt auf den Zoll, Windows 96 dpi auf 100 %: ein Prozent
#: sind 96 / 72 / 100 = 1/75 ``tk scaling``. Am 02.10.2026 an Minimalfenstern
#: gemessen (Standardschrift, Tupelschrift und ttk-Felder folgen); Tk rundet
#: die Bildschirmmillimeter auf ganze Zahlen, daher landet 2,0 bei 1,998.
TK_PROZENT_TEILER = 75.0

#: Auf macOS wirkt die Schriftanhebung (``MACOS_SCHRIFT_SKALIERUNG``), nicht
#: ``tk scaling`` allein. Sie ist so geeicht, dass dieselben Pixelhoehen wie
#: unter Windows bei 125 % herauskommen - das ist dort der Ausgangspunkt, an dem
#: der Regler "automatisch" steht.
MAC_BASIS_PROZENT = 125

#: Die Skalierung, auf die die Mindestbreite des Hauptfensters geschrieben ist
#: (``WINDOW_MIN_WIDTH`` = 1245 px). Darauf rechnet ``skalierung_obergrenze``.
BREITE_BASIS_PROZENT = 125

#: Was als gespeicherte Aufloesung noch vernuenftig ist.
AUFLOESUNG_UNTEN = (640, 480)
AUFLOESUNG_OBEN = (16384, 16384)

#: Gaengige Aufloesungen fuer die Klappliste. Unter 1280x720 bietet das
#: Programm nichts an: Die Mindestgroesse des Hauptfensters (1245x700) passt
#: dort nicht mehr hinein. Die erkannte Aufloesung kommt immer dazu.
AUFLOESUNGEN: tuple[tuple[int, int], ...] = (
    (1280, 720), (1366, 768), (1440, 900), (1536, 864), (1600, 900),
    (1680, 1050), (1920, 1080), (1920, 1200), (2048, 1152), (2560, 1080),
    (2560, 1440), (2560, 1600), (3440, 1440), (3840, 1600), (3840, 2160),
    (5120, 1440), (5120, 2880),
)

#: Was ein maximiertes Fenster an Rand verbraucht: links und rechts die
#: Rahmen, oben die Titelleiste, unten die Taskleiste. Gemessen unter Windows
#: bei 125 % (Titelleiste rund 39 px, Taskleiste rund 60 px); anderswo
#: ungefaehr dasselbe. Es geht nur um die Groesse eines Fensters, das ein
#: *angenommenes* Maximum nachstellt - das echte Maximieren bleibt dem System.
FENSTER_RAND_BREITE = 16
FENSTER_RAND_HOEHE = 110

_AUFLOESUNG_MUSTER = re.compile(r"^\s*(\d{3,5})\s*[xX×]\s*(\d{3,5})\s*$")


def skalierung_lesen(wert: object) -> int | None:
    """Der gespeicherte Skalierungswert, sofern er brauchbar ist.

    Args:
        wert: Was in der Einstellungsdatei steht (Zahl, Text, ``None`` ...).

    Returns:
        Ganze Prozent zwischen ``SKALIERUNG_MIN`` und ``SKALIERUNG_MAX``;
        ``None`` fuer alles andere - dann gilt die automatische Anpassung.
    """
    if wert is None or isinstance(wert, bool):
        return None
    try:
        zahl = float(wert)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(zahl):
        return None
    prozent = int(round(zahl))
    if not SKALIERUNG_MIN <= prozent <= SKALIERUNG_MAX:
        return None
    return prozent


def aufloesung_lesen(wert: object) -> tuple[int, int] | None:
    """Die gespeicherte Aufloesung, sofern sie brauchbar ist.

    Args:
        wert: Was in der Einstellungsdatei steht, erwartet ``"1920x1080"``
            (auch mit Mal-Zeichen und Leerzeichen).

    Returns:
        ``(Breite, Hoehe)``; ``None`` fuer alles andere - dann gilt die
        automatisch erkannte Aufloesung.
    """
    if not isinstance(wert, str):
        return None
    treffer = _AUFLOESUNG_MUSTER.match(wert)
    if not treffer:
        return None
    breite, hoehe = int(treffer.group(1)), int(treffer.group(2))
    if not (AUFLOESUNG_UNTEN[0] <= breite <= AUFLOESUNG_OBEN[0]
            and AUFLOESUNG_UNTEN[1] <= hoehe <= AUFLOESUNG_OBEN[1]):
        return None
    return breite, hoehe


def aufloesung_text(breite: int, hoehe: int) -> str:
    """Die Schreibweise in der Einstellungsdatei: ``1920x1080``."""
    return "%dx%d" % (breite, hoehe)


def aufloesung_anzeige(breite: int, hoehe: int) -> str:
    """Die Schreibweise fuer den Anwender: ``1920 × 1080``."""
    return "%d × %d" % (breite, hoehe)


def aufloesungen_anbieten(erkannt: tuple[int, int] | None,
                          gewaehlt: tuple[int, int] | None = None
                          ) -> list[tuple[int, int]]:
    """Die Eintraege der Klappliste: gaengige Werte plus erkannte und gewaehlte.

    Args:
        erkannt: Was Tk als Bildschirm meldet.
        gewaehlt: Die gespeicherte, von Hand gewaehlte Aufloesung - auch wenn
            sie nicht zu den gaengigen gehoert (von Hand in die Datei
            geschrieben), damit die Liste sie zeigen kann.

    Returns:
        Die Aufloesungen, nach Flaeche sortiert, ohne Doppelte.
    """
    menge = set(AUFLOESUNGEN)
    for zusatz in (erkannt, gewaehlt):
        if zusatz and len(zusatz) == 2 and all(int(v) > 0 for v in zusatz):
            menge.add((int(zusatz[0]), int(zusatz[1])))
    return sorted(menge, key=lambda a: (a[0] * a[1], a[0]))


def tk_skalierung(prozent: int) -> float:
    """``tk scaling`` fuer eine Skalierung in Prozent (100 % = 96 dpi)."""
    return prozent / TK_PROZENT_TEILER


#: Wie weit ein umgerechneter Wert von einem Vielfachen von 5 entfernt sein darf,
#: um als dieses zu gelten. Tk rundet die Bildschirmmillimeter auf ganze Zahlen;
#: gemessen am 02.10.2026 wurde aus 300 % ein ``tk scaling`` von 4,0079 (= 300,6 %).
#: Windows bietet 100, 125, 150, 175 ... an - ein krummer Wert wie 126 bleibt aber
#: 126 (Abstand 1,0 zum naechsten Vielfachen).
_RUNDUNGSTOLERANZ = 0.7


def prozent_aus_tk(skalierung: float) -> int:
    """Skalierung in ganzen Prozent aus einem ``tk scaling``-Wert."""
    prozent = skalierung * TK_PROZENT_TEILER
    naechster = int(round(prozent / SKALIERUNG_SCHRITT)) * SKALIERUNG_SCHRITT
    if abs(prozent - naechster) <= _RUNDUNGSTOLERANZ:
        return naechster
    return int(round(prozent))


def system_prozent(ist_macos: bool, tk_skalierung_system: float) -> int:
    """Die Skalierung, die das System von sich aus liefert - in Prozent.

    Args:
        ist_macos: Auf macOS ist der Ausgangspunkt die Eichung der
            Schriftanhebung (``MAC_BASIS_PROZENT``), nicht ``tk scaling``.
        tk_skalierung_system: ``tk scaling`` vor jedem eigenen Eingriff.

    Returns:
        Ganze Prozent; 100, wenn sich nichts Brauchbares messen liess.
    """
    if ist_macos:
        return MAC_BASIS_PROZENT
    if not tk_skalierung_system or tk_skalierung_system <= 0:
        return 100
    return prozent_aus_tk(tk_skalierung_system)


def mac_faktor(basis: float, prozent: int | None) -> float:
    """Faktor der macOS-Schriftanhebung unter Beruecksichtigung der Skalierung.

    Args:
        basis: Die automatische Anhebung (``MACOS_SCHRIFT_SKALIERUNG`` oder der
            Wert aus ``macos_font_scaling``).
        prozent: Die manuelle Skalierung, oder ``None`` fuer automatisch.

    Returns:
        ``basis`` unveraendert bei automatisch, sonst im Verhaeltnis der
        gewaehlten Skalierung zu ``MAC_BASIS_PROZENT``, hoechstens 4,0 (die
        Grenze, die die Anhebung auch sonst hat).
    """
    if prozent is None:
        return basis
    return min(basis * prozent / MAC_BASIS_PROZENT, 4.0)


def auf_schritt(prozent: float) -> int:
    """Rundet auf den Reglerschritt und haelt den Bereich ein."""
    if not math.isfinite(prozent):
        return SKALIERUNG_MIN
    gerundet = int(round(prozent / SKALIERUNG_SCHRITT)) * SKALIERUNG_SCHRITT
    return max(SKALIERUNG_MIN, min(SKALIERUNG_MAX, gerundet))


def skalierung_obergrenze(fensterbreite: int, mindestbreite: int,
                          system: int | None = None) -> int:
    """Die hoechste Skalierung, die der Regler anbietet.

    Die Oberflaeche braucht mindestens ``mindestbreite`` Pixel - auf
    ``BREITE_BASIS_PROZENT`` geschrieben - und wird mit der Skalierung
    breiter. Am 02.10.2026 gemessen, die gewuenschte Breite des Hauptfensters
    je Skalierung: 100 % 776 px, 125 % 966, 150 % 1152, 200 % 1532, 250 % 1912,
    300 % 2292 - Breite und Skalierung wachsen im gleichen Verhaeltnis. Darueber
    hinaus ragt sie seitlich aus dem Bildschirm, und eine Rollleiste nach
    rechts gibt es nicht: Man kaeme nicht einmal mehr an den Knopf, der die
    Wahl zuruecknimmt.

    Der Wert, den das System selbst liefert, bleibt immer erreichbar: Wer unter
    Windows 150 % eingestellt hat, soll das auch auf einem schmalen Schirm
    sehen und waehlen koennen.

    Args:
        fensterbreite: Breite des Bildschirms (oder der angenommenen
            Aufloesung) in Pixeln, siehe ``fenster_obergrenze``.
        mindestbreite: ``WINDOW_MIN_WIDTH``.
        system: Was das System von sich aus liefert, in Prozent.

    Returns:
        Prozent, auf volle Reglerschritte abgerundet, zwischen
        ``SKALIERUNG_MIN`` und ``SKALIERUNG_MAX``.
    """
    passend = int(fensterbreite * BREITE_BASIS_PROZENT / max(1, mindestbreite))
    grenze = passend // SKALIERUNG_SCHRITT * SKALIERUNG_SCHRITT
    if system:
        grenze = max(grenze, system)
    return max(SKALIERUNG_MIN, min(SKALIERUNG_MAX, grenze))


def bildschirm_wirksam(erkannt: tuple[int, int],
                       gewaehlt: tuple[int, int] | None) -> tuple[int, int]:
    """Die Bildschirmgroesse, nach der sich das Programm richtet."""
    return gewaehlt if gewaehlt else erkannt


def ist_verkleinert(erkannt: tuple[int, int],
                    gewaehlt: tuple[int, int] | None) -> bool:
    """Ist die gewaehlte Aufloesung in einer Richtung kleiner als die echte?

    Nur dann ist etwas nachzustellen: Eine gleich grosse oder groessere
    Aufloesung aendert an der Groesse der Fenster nichts - mehr als der echte
    Bildschirm passt ohnehin nicht hinein.
    """
    if not gewaehlt:
        return False
    return gewaehlt[0] < erkannt[0] or gewaehlt[1] < erkannt[1]


def fenster_obergrenze(erkannt: tuple[int, int],
                       gewaehlt: tuple[int, int] | None) -> tuple[int, int]:
    """Wie gross ein Fenster hoechstens werden darf: je Richtung der kleinere Wert."""
    if not gewaehlt:
        return erkannt
    return min(erkannt[0], gewaehlt[0]), min(erkannt[1], gewaehlt[1])


def maximiert_groesse(bildschirm: tuple[int, int]) -> tuple[int, int]:
    """Die Groesse, die ein maximiertes Fenster auf diesem Bildschirm haette."""
    return (max(1, bildschirm[0] - FENSTER_RAND_BREITE),
            max(1, bildschirm[1] - FENSTER_RAND_HOEHE))


def hintergrund_masse(fenster: tuple[int, int], seitenleiste: int) -> tuple[int, int, int]:
    """Wie gross die beiden Hintergrundbilder sein sollen: ``(Hauptbild-Breite, Hoehe, Seitenleisten-Breite)``.

    Das Hauptbild liegt nur **rechts neben der Seitenleiste**, die Seitenleiste hat ihr eigenes Bild - beide
    nebeneinander, keines unter dem anderen (Nutzerhinweis 05.10.2026). Beide sind so hoch wie das Fenster; das
    Hauptbild ist so breit wie das, was neben der Leiste uebrig bleibt. Gemessen an einem maximierten Fenster von
    1920 x 1111 bei einer Leiste von 493: Hauptbild 1427 x 1111, Seitenleiste 493 x 1111.

    Args:
        fenster: ``(breite, hoehe)`` des Fensters, auf das sich die Bilder beziehen (maximiert).
        seitenleiste: Die Breite der Seitenleiste in Pixeln.

    Returns:
        ``(breite, hoehe, leiste)`` - jede Zahl mindestens 1.
    """
    leiste = max(1, int(seitenleiste))
    return max(1, int(fenster[0]) - leiste), max(1, int(fenster[1])), leiste
