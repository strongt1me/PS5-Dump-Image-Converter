# -*- coding: utf-8 -*-
"""Die Konsole fragen, statt zu raten - ShadowMount+ HTTP/JSON-API v1.

Angelegt am 03.09.2026.

**Wozu.** Das Programm ermittelt heute per FTP-Verzeichnisdurchlauf,
welche Spiele und Abbilder auf der Konsole liegen. Das ist Raten: Es
sieht Dateien, nicht den Zustand. Ob ShadowMount+ ein Abbild wirklich
kennt, ob es eingehaengt ist, ob die Quelle noch erreichbar ist - das
steht nicht im Verzeichnis. Ab 1.7alpha13 beantwortet die Konsole diese
Fragen selbst.

**Nur lesen.** Die Schnittstelle bietet 21 Endpunkte, darunter
``games/mount``, ``games/delete`` und ``games/uninstall``. Hier stehen
nur die vier lesenden. Ein Konvertierprogramm hat nichts auf der
Konsole zu loeschen, und ein Einhaengen waere ein Eingriff, den der
Anwender an anderer Stelle bewusst ausloest. Wer die uebrigen braucht,
nimmt die mitgelieferte Weboberflaeche der Konsole.

**Erreichbarkeit ist die Ausnahme, nicht die Regel.** Ab Werk lauscht
die Schnittstelle auf ``127.0.0.1:10101`` - also nur fuer Programme auf
der PS5 selbst. Vom PC aus geht es erst, wenn in der ``config.ini``
zusaetzlich ``api_bind_address=0.0.0.0`` steht. Deshalb meldet dieses
Modul einen unerreichbaren Dienst als gewoehnlichen Fall mit Grund,
nicht als Fehler.

**Ohne Anmeldung.** Die Schnittstelle hat keine. Wer sie ans Netz
haengt, oeffnet sie jedem im selben Netz - darauf muss das Programm
hinweisen, bevor es dazu raet.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, NamedTuple

#: Vorgaben aus ``config.ini.example`` von 1.7alpha13.
STANDARD_HOST = "127.0.0.1"
STANDARD_PORT = 10101

#: Wie lange auf die Konsole gewartet wird.
#:
#: Kurz gehalten: Der Dienst ist meist gar nicht erreichbar (siehe oben),
#: und dann soll das Programm weiterlaufen statt zu haengen. Die Konsole
#: schliesst untaetige Verbindungen ohnehin nach 15 s.
ZEITGRENZE = 4.0

#: Groesste Antwort, die eingelesen wird.
#:
#: Ohne Grenze koennte eine Gegenstelle - oder ein Missverstaendnis
#: darueber, was auf Port 10101 lauscht - beliebig viel in den Speicher
#: schieben. Eine Spielliste mit hundert Eintraegen bleibt weit darunter.
GROESSTE_ANTWORT = 4 * 1024 * 1024


class Antwort(NamedTuple):
    """Ergebnis einer Abfrage.

    Attributes:
        ok:     Ob die Konsole geantwortet hat **und** ``status`` null war.
        daten:  Die Antwort als Woerterbuch; bei Misserfolg leer.
        grund:  Klartext, warum es nicht ging. Leer bei Erfolg.
    """

    ok: bool
    daten: dict
    grund: str


def _fragen(pfad: str, nutzlast: dict | None = None, *,
            host: str = STANDARD_HOST, port: int = STANDARD_PORT,
            zeitgrenze: float = ZEITGRENZE) -> Antwort:
    """Stellt eine Frage und liefert die Antwort - oder den Grund.

    Wirft nicht. Eine nicht erreichbare Konsole ist der Normalfall, kein
    Programmfehler; der Aufrufer soll das anzeigen koennen, ohne jeden
    Aufruf einzupacken.

    Args:
        pfad:       Etwa ``"/api/v1/version"``.
        nutzlast:   Der JSON-Koerper. ``None`` wird zu ``{}`` - jede
            Abfrage der Schnittstelle ist ein ``POST`` mit einem Objekt,
            auch wenn nichts mitzugeben ist.
        host:       Adresse der Konsole.
        port:       Port der Schnittstelle.
        zeitgrenze: Sekunden.

    Returns:
        :class:`Antwort`.
    """
    koerper = json.dumps(nutzlast if nutzlast is not None else {}).encode("utf-8")
    if len(koerper) > 4096:
        # Die Konsole weist groessere Koerper ab (HTTP 413). Lieber hier
        # sagen, warum, als dort einen Fehlercode einsammeln.
        return Antwort(False, {}, "Anfrage zu gross (%d Bytes, erlaubt 4096)"
                       % len(koerper))

    anfrage = urllib.request.Request(
        "http://%s:%d%s" % (host, port, pfad),
        data=koerper, method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(anfrage, timeout=zeitgrenze) as verbindung:
            roh = verbindung.read(GROESSTE_ANTWORT + 1)
    except urllib.error.HTTPError as fehler:
        # Auch ein Fehlerschlag traegt einen JSON-Koerper mit "error".
        try:
            text = json.loads(fehler.read(GROESSTE_ANTWORT).decode("utf-8"))
            grund = str(text.get("error") or "").strip()
        except Exception:                                   # noqa: BLE001
            grund = ""
        return Antwort(False, {}, "HTTP %s%s" % (
            fehler.code, ": " + grund if grund else ""))
    except urllib.error.URLError as fehler:
        return Antwort(False, {}, "nicht erreichbar (%s)" % (fehler.reason,))
    except OSError as fehler:
        return Antwort(False, {}, "nicht erreichbar (%s)" % (fehler,))

    if len(roh) > GROESSTE_ANTWORT:
        return Antwort(False, {}, "Antwort groesser als %d Bytes" % GROESSTE_ANTWORT)
    try:
        daten = json.loads(roh.decode("utf-8"))
    except Exception as fehler:                             # noqa: BLE001
        return Antwort(False, {}, "keine gueltige JSON-Antwort (%s)" % fehler)
    if not isinstance(daten, dict):
        return Antwort(False, {}, "Antwort ist kein Objekt")

    # "status" ist null bei Erfolg, sonst ein errno-Wert. Ein fehlendes
    # Feld ist verdaechtig: Dann antwortet dort etwas anderes als
    # ShadowMount+.
    if "status" not in daten:
        return Antwort(False, {}, "Antwort ohne 'status' - lauscht dort "
                                  "wirklich ShadowMount+?")
    if daten.get("status") != 0:
        return Antwort(False, daten, "Konsole meldet Fehler %s%s" % (
            daten.get("status"),
            ": " + str(daten["error"]) if daten.get("error") else ""))
    return Antwort(True, daten, "")


def fassung(**wohin: Any) -> Antwort:
    """Fassung der Schnittstelle und was sie kann.

    Die guenstigste Frage von allen und deshalb die richtige, um zu
    pruefen, ob ueberhaupt jemand antwortet. Die Antwort traegt
    ``api_version``, ``shadowmount_version`` und ``capabilities``.
    """
    return _fragen("/api/v1/version", **wohin)


def abbilder(**wohin: Any) -> Antwort:
    """Was die Konsole an Abbildern kennt.

    Je Eintrag unter anderem ``path``, ``mount_point``, ``size``,
    ``complete``, ``source_available`` und ``mounted`` - also gerade
    das, was ein Verzeichnisdurchlauf nicht sieht.
    """
    return _fragen("/api/v1/images", **wohin)


def spiele(mit_groesse: bool = False, **wohin: Any) -> Antwort:
    """Was die Konsole an Spielen kennt.

    Args:
        mit_groesse: Laesst die Konsole zusaetzlich die Quellgroesse
            ausrechnen. Ab Werk nicht: Dafuer laeuft sie jeden
            Spielordner durch, und das kostet dort Zeit.
    """
    return _fragen("/api/v1/games", {"include_size": bool(mit_groesse)}, **wohin)


def speicher(**wohin: Any) -> Antwort:
    """Die eingehaengten Dateisysteme mit Gesamt-, Frei- und Restplatz.

    Nuetzlich vor dem Uebertragen: Das Programm kann heute nicht sagen,
    ob auf dem Ziellaufwerk der Konsole ueberhaupt Platz ist.
    """
    return _fragen("/api/v1/storage", **wohin)


def erreichbar(**wohin: Any) -> tuple[bool, str]:
    """Kurzform fuer "antwortet dort ShadowMount+?".

    Returns:
        ``(True, "1.7")`` bei Erfolg - die zweite Stelle traegt dann die
        gemeldete Fassung -, sonst ``(False, Grund)``.
    """
    antwort = fassung(**wohin)
    if not antwort.ok:
        return False, antwort.grund
    return True, str(antwort.daten.get("shadowmount_version") or "").strip()
