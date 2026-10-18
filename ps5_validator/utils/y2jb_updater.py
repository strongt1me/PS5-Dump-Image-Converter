# -*- coding: utf-8 -*-
"""Y2JB Updater: ``download0.dat`` von itsPLK/ps5-y2jb-autoloader waehlen und auf die PS5 legen.

Reine Logik - kein Netz- oder FTP-Code. Das Holen der Freigaben-Liste und das
Laden einer Datei macht das Hauptprogramm ueber :mod:`werkzeug_updates`
(``Netz``, ``freigaben_lesen``), den eigentlichen FTP-Transfer ``konsole_ftp``
- wie bei den uebrigen Werkzeug-Aktualisierungen des Programms.

Das Werkzeug selbst (itsPLK, Fork von Gezine/Y2JB, GPL-3.0) nutzt eine
Luecke im Aktualisierungsweg der YouTube-App, um ein eigenes ``download0.dat``
anstelle einer echten App-Aktualisierung einzuspielen - fuer die eigene,
bereits gejailbreakte PS5 des Nutzers. Quelle und Anleitung:
https://github.com/itsPLK/ps5-y2jb-autoloader
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ps5_validator.utils.werkzeug_updates import Anhang, Freigabe

#: Die Quelle in der Form, die werkzeug_updates.adresse_der_quelle()/Netz.abfragen() erwarten.
QUELLE = "itsPLK/ps5-y2jb-autoloader"
#: Der Anhang, der auf die Konsole gehoert - die zweite Datei jeder Freigabe
#: (``y2jb_update.zip``) ist nur fuer den PC-seitigen Host, nicht fuer die PS5.
DATEINAME = "download0.dat"
#: Die drei Titel-IDs der YouTube-App, auf die die offizielle Anleitung des Werkzeugs
#: verweist (``/user/download/PPSA0165*`` - das Sternchen steht fuer alle drei, je nach
#: Region der installierten App). PPSA01650 ist der in der Anleitung zuerst genannte
#: Regelfall (18.10.2026 gegen das README gelesen, nicht geraten).
ZIEL_IDS: tuple[str, ...] = ("PPSA01650", "PPSA01651", "PPSA01652")
ZIEL_STANDARD = ZIEL_IDS[0]
#: download0.dat ueberschreitet das allgemeine Netz-Limit (200 MiB, werkzeug_updates.GRENZE_BYTES)
#: deutlich - gemessen rund 321 MiB je Fassung (18.10.2026, v0.9.1 bis v1.0.2 alle gleich
#: gross). Grosszuegig bemessen, damit eine etwas groessere kuenftige Fassung nicht gleich
#: daran scheitert; ``Netz.laden(..., grenze=GRENZE_BYTES)`` nimmt diesen Wert statt des
#: allgemeinen.
GRENZE_BYTES = 400 * 1024 * 1024

_TITEL_ID_MUSTER = re.compile(r"[A-Z0-9]{9}")


def ziel_id_gueltig(ziel_id: str) -> bool:
    """Sieht ``ziel_id`` wie eine Titel-ID aus (neun Grossbuchstaben/Ziffern)?

    Kein Abgleich gegen eine Liste bekannter IDs - nur eine Formpruefung, damit ein
    Tippfehler im freien Eingabefeld nicht in einen beliebigen Konsolenpfad muendet.
    """
    return bool(_TITEL_ID_MUSTER.fullmatch(str(ziel_id or "").strip().upper()))


def ziel_pfad(ziel_id: str) -> str:
    """Der Ordner auf der Konsole fuer eine Titel-ID, z. B. ``/user/download/PPSA01650``.

    Leer, wenn ``ziel_id`` nicht nach :func:`ziel_id_gueltig` aussieht.
    """
    ziel_id = str(ziel_id or "").strip().upper()
    if not ziel_id_gueltig(ziel_id):
        return ""
    return "/user/download/%s" % ziel_id


def angebote(freigaben: "list[Freigabe]") -> "list[tuple[Freigabe, Anhang]]":
    """Die Freigaben, die ein ``download0.dat`` anbieten - Entwuerfe nie.

    Reihenfolge wie in ``freigaben``: Die GitHub-Schnittstelle liefert Freigaben
    bereits neueste zuerst, hier wird nicht neu sortiert.

    Returns:
        Paare ``(Freigabe, Anhang)`` - aus der Freigabe braucht die Anzeige nur Tag,
        Datum und Vorabkennzeichen, aus dem Anhang Groesse, Pruefsumme und Ladeadresse.
    """
    erg: "list[tuple[Freigabe, Anhang]]" = []
    for freigabe in freigaben:
        if freigabe.entwurf:
            continue
        for anhang in freigabe.anhaenge:
            if anhang.name == DATEINAME and anhang.adresse:
                erg.append((freigabe, anhang))
                break
    return erg
