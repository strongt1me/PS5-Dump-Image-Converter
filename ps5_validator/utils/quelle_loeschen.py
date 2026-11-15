# -*- coding: utf-8 -*-
"""Die Quelle nach einem erfolgreichen Lauf loeschen (Wunsch vom 14.11.2026; Vorbild Dump Forge ``--delete-source``).

Das Loeschen ist endgueltig (kein Papierkorb: ein Spiel von 100 GB passt dort nie hinein). Deshalb gilt es nur, wenn alles
stimmt, und im Zweifel bleibt die Quelle liegen - der Lauf bleibt trotzdem erfolgreich:

* Der Anwender hat es fuer diesen Lauf gewollt (Haken, Rueckfrage beim Start) - das entscheidet der Aufrufer.
* Das Ergebnis liegt da, ist nicht leer und stammt aus einem Lauf, der es geprueft hat (Aufrufer).
* Die Quelle ist seit dem Start unveraendert (:func:`stempel_nehmen` beim Start, :func:`pruefen` am Ende): Wer waehrend des Laufs
  etwas hineinlegt oder aendert, behaelt sie.
* Quelle und Ergebnis sind nicht dasselbe und liegen nicht ineinander (ein Selbst-Ziel ersetzt die Quelle schon; ein Ergebnis im
  Quellordner wuerde mit ihr geloescht).
* Die Quelle ist kein Laufwerk, kein Benutzerordner und keine Verknuepfung.
"""
from __future__ import annotations

import os
import shutil
from typing import Callable

from ps5_validator.utils import pfadvergleich

#: Ordner, die nie als Quelle geloescht werden (zusaetzlich zu Laufwerkswurzeln und dem Benutzerordner selbst). Verglichen wird
#: klein geschrieben - ``normcase`` faltet nur unter Windows, ``~/Documents`` auf Linux/macOS waere sonst ungeschuetzt.
_GESCHUETZTE_NAMEN = ("documents", "dokumente", "desktop", "downloads", "pictures", "bilder", "music", "videos", "appdata",
                      "windows", "program files", "program files (x86)", "users", "benutzer")


def _norm(pfad: str) -> str:
    return os.path.normcase(os.path.abspath(pfad))


def _ist_verknuepfung(pfad: str) -> bool:
    """Symbolische Verknuepfung oder Junction (unter Windows ``is_junction``)."""
    try:
        if os.path.islink(pfad):
            return True
        pruefen = getattr(os.path, "isjunction", None)
        return bool(pruefen and pruefen(pfad))
    except OSError:
        return False


def stempel_nehmen(pfad: str) -> "tuple | None":
    """Merkt, wie die Quelle aussieht: Datei ``("datei", Groesse, Aenderungszeit)``, Ordner ``("ordner", Dateien, Bytes, juengste Zeit)``.

    ``None``, wenn sie sich nicht lesen laesst - dann wird nichts geloescht. Verknuepfungen im Ordner zaehlen als Eintrag, ihr Ziel
    wird nicht verfolgt.
    """
    try:
        if os.path.isfile(pfad):
            st = os.stat(pfad)
            return ("datei", st.st_size, st.st_mtime_ns)
        if not os.path.isdir(pfad):
            return None
        dateien = 0
        gesamt = 0
        juengste = 0
        offen = [pfad]
        while offen:
            ordner = offen.pop()
            with os.scandir(ordner) as eintraege:
                for e in eintraege:
                    st = e.stat(follow_symlinks=False)
                    juengste = max(juengste, st.st_mtime_ns)
                    if e.is_dir(follow_symlinks=False):
                        offen.append(e.path)
                    else:
                        dateien += 1
                        gesamt += st.st_size
        return ("ordner", dateien, gesamt, juengste)
    except OSError:
        return None


#: Ordner, deren unmittelbare Unterordner Benutzer- oder Datentraegerwurzeln sind (Linux/macOS): ``/home/bob``, ``/Users/Shared``,
#: ``/Volumes/STICK``, ``/media/anna`` ... (Gesamtpruefung 14.11.2026, R2-A3).
_SAMMELORDNER_POSIX = ("/home", "/Users", "/Volumes", "/media", "/mnt", "/run/media")


def unter_sammelordner(voll: str) -> bool:
    """Ist ``voll`` (POSIX-Pfad) ein unmittelbarer Unterordner von ``/home``, ``/Users``, ``/Volumes``, ``/media``, ``/mnt``?"""
    return voll.rstrip("/").rpartition("/")[0] in _SAMMELORDNER_POSIX


def _gefaehrlich(pfad: str) -> bool:
    """Wurzel eines Laufwerks oder Einhaengepunkt, ein Benutzer- oder Systemordner: solche Pfade gelten nie als Quelle.

    Unter Linux und macOS ist ein USB-Stick kein Laufwerksbuchstabe, sondern ein Ordner (``/Volumes/STICK``, ``/media/anna/STICK``).
    Lag ein Dump direkt in dessen Wurzel, haette "Quelle nach Erfolg loeschen" den ganzen Stick geleert (R2-A3).
    """
    voll = _norm(pfad)
    if os.path.dirname(voll) == voll:                       # Laufwerks- oder Dateisystemwurzel
        return True
    try:
        if os.path.isdir(voll) and os.path.ismount(voll):   # Einhaengepunkt (auch ein in einen Ordner eingehaengtes Laufwerk)
            return True
    except OSError:
        return True
    if os.name != "nt" and os.path.isdir(voll) and unter_sammelordner(voll):
        return True
    heim = os.path.expanduser("~")
    if pfadvergleich.gleicher_ort(voll, heim):
        return True
    teile = [t for t in voll.replace("\\", "/").split("/") if t and not t.endswith(":")]
    # Ein Ordner direkt unter der Wurzel (/home, D:\Spiele) ist nie die Quelle eines Laufs; eine Datei dort (D:\Spiel.ffpkg) schon.
    if len(teile) < 2 and not os.path.isfile(voll):
        return True
    eltern = os.path.dirname(voll)
    return (os.path.basename(voll).lower() in _GESCHUETZTE_NAMEN
            and (pfadvergleich.gleicher_ort(eltern, heim) or pfadvergleich.gleicher_ort(eltern, os.path.dirname(heim))))


def _ineinander(aussen: str, innen: str) -> bool:
    """Liegt ``innen`` im Ordner ``aussen`` (oder ist es derselbe Pfad)? Auch in anderer Schreibung (:mod:`pfadvergleich`)."""
    return pfadvergleich.gleicher_ort(aussen, innen) or pfadvergleich.liegt_in(innen, aussen)


def _nicht_leer(pfad: str) -> bool:
    try:
        if os.path.isfile(pfad):
            return os.path.getsize(pfad) > 0
        if os.path.isdir(pfad):
            with os.scandir(pfad) as eintraege:
                return any(True for _ in eintraege)
    except OSError:
        return False
    return False


def pruefen(quelle: str, ergebnis: str, stempel: "tuple | None") -> str:
    """Darf die Quelle geloescht werden? ``""`` = ja, sonst der Grund als Schluessel (``quelle_loeschen.grund.<Schluessel>``)."""
    if not quelle or not os.path.lexists(quelle):
        return "quelle_fehlt"
    if _ist_verknuepfung(quelle):
        return "verknuepfung"
    if _gefaehrlich(quelle):
        return "geschuetzt"
    if not ergebnis or not os.path.exists(ergebnis) or not _nicht_leer(ergebnis):
        return "ergebnis_fehlt"
    if pfadvergleich.gleicher_ort(quelle, ergebnis):
        return "gleicher_pfad"
    if _ineinander(quelle, ergebnis):
        return "ergebnis_in_quelle"
    if os.path.isdir(ergebnis) and _ineinander(ergebnis, quelle):
        return "quelle_in_ergebnis"
    if stempel is None:
        return "ohne_stempel"
    if stempel_nehmen(quelle) != stempel:
        return "geaendert"
    return ""


def loeschen(quelle: str, *, ordner_loeschen: "Callable[[str], object] | None" = None,
             datei_loeschen: "Callable[[str], object] | None" = None) -> str:
    """Loescht die Quelle endgueltig. Rueckgabe: ``""`` oder der Fehlertext (die Quelle ist dann teilweise oder ganz noch da).

    ``ordner_loeschen``/``datei_loeschen`` kommen vom Programm (schreibgeschuetzte Dateien unter Windows); ohne sie ``shutil``/``os``.
    """
    try:
        if os.path.isdir(quelle):
            (ordner_loeschen or (lambda p: shutil.rmtree(p)))(quelle)
        else:
            (datei_loeschen or os.remove)(quelle)
    except OSError as exc:
        return str(exc)
    if os.path.lexists(quelle):
        return "bleibt"
    return ""
