# -*- coding: utf-8 -*-
"""Das Undo-Journal fuer "Direkt aendern" (exFAT, UFS2, PFS) und die gemeinsamen Ausnahmen der drei Editoren.

Ein Editor aendert ein fertiges Abbild an Ort und Stelle. Damit ein Abbruch (Absturz, Strom weg, Fehler mitten im Schreiben) nie ein
halbes Abbild hinterlaesst, schreibt er vorher die **alten** Bytes jeder Stelle, die er aendern wird, in ``<Abbild>.undo``:

* Das Journal entsteht als ``<Abbild>.undo.neu``, wird auf die Platte gezwungen und erst dann umbenannt. Gueltig ist es nur mit der
  Ende-Marke; jede Stelle traegt eine CRC32.
* Waechst das Abbild beim Schreiben (PFS haengt neue Daten hinten an), steht die alte Laenge als eigener Satz darin: Beim Zurueckspielen
  wird das Abbild wieder auf sie gekuerzt.
* Findet das Programm beim naechsten Oeffnen ein vollstaendiges Journal, spielt es die alten Bytes zurueck - das Abbild ist wieder wie
  vorher. Ein unvollstaendiges ``.undo.neu`` heisst: Es wurde noch nichts geaendert; es wird nur entfernt. Ein ``.undo`` dagegen
  entsteht nur vollstaendig (Umbenennen nach dem Erzwingen auf die Platte) - laesst es sich spaeter nicht lesen (defekter Sektor,
  Datentraeger ohne verlaessliches fsync, Lesefehler), wird es **nicht** geloescht, sondern als ``<Abbild>.undo.defekt`` beiseitegelegt
  und gemeldet: Das Abbild kann halb geschrieben sein (Gesamtpruefung 23.11.2026).
* Liegt beim Speichern noch ein ``.undo`` (ein frueherer Lauf scheiterte, und auch das Zurueckspielen gelang nicht), wird nichts
  geschrieben: Ein neues Journal haette die halb neuen Bytes als "alt" festgehalten und das einzige gueltige ueberschrieben.

**Format 2 (Gesamtpruefung 14.11.2026, E3):** Zu jeder Verwaltungsstelle stehen auch die Pruefsummen der **neuen** Bytes, je Sektor
(512 Bytes). Zurueckgespielt wird nur, wenn an jeder dieser Stellen jeder Sektor entweder noch alt oder schon neu ist - so ein Abbild
ist der unterbrochene Lauf (auch ein halb geschriebener Block besteht aus alten und neuen Sektoren). Lag das Journal neben einem
**anderen** Abbild gleichen Namens (neu gebaut, kopiert), spielte Format 1 dessen alte Bytes hinein und kuerzte ein PFS - jetzt
bleibt das Abbild unberuehrt, und das Journal wird als ``<Abbild>.undo.fremd`` beiseitegelegt. Stellen mit Dateidaten tragen keine
neuen Pruefsummen (der Inhalt wird erst beim Schreiben gelesen); sie werden nicht verglichen.

Format 1 (``PS5CONV-EXFAT-UNDO1``, ohne neue Pruefsummen) wird weiter gelesen und wie bisher zurueckgespielt.
"""
from __future__ import annotations

import logging
import os
import struct
import zlib
from typing import Any

logger = logging.getLogger(__name__)

JOURNAL_ENDUNG = ".undo"
#: Endung eines Journals, das nicht zum Abbild daneben passt (es wird nicht zurueckgespielt, aber auch nicht still geloescht).
FREMD_ENDUNG = ".fremd"
#: Endung eines ``.undo``, das sich nicht lesen laesst (Pruefsumme, abgeschnitten, Lesefehler) - beiseitegelegt, nie geloescht.
DEFEKT_ENDUNG = ".defekt"
_MAGIC = b"PS5CONV-EXFAT-UNDO1\n"
_MAGIC2 = b"PS5CONV-DIREKT-UNDO2\n"
_ENDE = b"ENDE-DES-JOURNALS!"
#: Offset des Satzes "Laenge des Abbilds vorher" (8 Bytes Nutzlast); kein echtes Abbild ist so gross.
_LAENGE_SATZ = 0xFFFFFFFFFFFFFFFF
#: Die neuen Bytes einer Stelle sind nicht bekannt (Dateidaten).
_UNBEKANNT = 0xFFFFFFFF
SEKTOR = 512


class DirektFehler(RuntimeError):
    """Das Abbild laesst sich so nicht direkt aendern (Format, Name unzulaessig, Pfad fehlt, beschaedigt)."""


class DirektPlatzFehlt(DirektFehler):
    """Im Abbild ist nicht genug Platz (oder die Verwaltung des Formats ist voll) - dann bleibt nur, es neu zu bauen."""


def journal_pfad(abbild: str) -> str:
    """Wo das Undo-Journal zu ``abbild`` liegt."""
    return abbild + JOURNAL_ENDUNG


def _stuecke(offset: int, laenge: int) -> "list[tuple[int, int]]":
    """Die Teile ``[von, bis)`` einer Stelle (relativ zu ihr), geschnitten an den Sektorgrenzen der DATEI - so faellt ein halb
    geschriebener Block (die Platte schreibt ganze Sektoren) immer in ganze Teile, die alt oder neu sind."""
    teile: "list[tuple[int, int]]" = []
    von = 0
    while von < laenge:
        bis = min(laenge, (offset + von) // SEKTOR * SEKTOR + SEKTOR - offset)
        teile.append((von, bis))
        von = bis
    return teile


def _sektor_summen(offset: int, daten: bytes) -> "list[int]":
    return [zlib.crc32(daten[von:bis]) & 0xFFFFFFFF for von, bis in _stuecke(offset, len(daten))]


def stellen_zusammenfassen(stellen: "list[tuple[int, bytes]]") -> "list[tuple[int, bytes]]":
    """Fasst Schreibstellen zu nicht ueberlappenden Bereichen zusammen; eine spaetere Stelle gewinnt (wie beim Schreiben der Reihe nach).

    Das Journal prueft beim Zurueckspielen jede Stelle auf "alt oder neu" - zwei Stellen ueber denselben Bytes (ein Ordnereintrag,
    der in einer Sitzung zweimal geaendert wird) haetten sich dabei gegenseitig widersprochen.

    Erst die Vereinigung der Bereiche (sortiert), dann jede Stelle in ihrer Reihenfolge in ihren Bereich: O(n log n). Die erste
    Fassung verglich jede Stelle mit allen Bereichen - 6000 aneinanderliegende FAT-Bloecke brauchten 25 s (Gesamtpruefung, R2-J4).
    """
    import bisect

    if not stellen:
        return []
    grenzen: "list[list[int]]" = []
    for anfang, ende in sorted((o, o + len(d)) for o, d in stellen):
        if grenzen and anfang <= grenzen[-1][1]:             # ueberlappend oder angrenzend: derselbe Bereich
            grenzen[-1][1] = max(grenzen[-1][1], ende)
        else:
            grenzen.append([anfang, ende])
    anfaenge = [g[0] for g in grenzen]
    puffer = [bytearray(g[1] - g[0]) for g in grenzen]
    for offset, daten in stellen:                            # in der Reihenfolge des Schreibens: die spaetere gewinnt
        i = bisect.bisect_right(anfaenge, offset) - 1
        start = offset - anfaenge[i]
        puffer[i][start:start + len(daten)] = daten
    return [(anfaenge[i], bytes(p)) for i, p in enumerate(puffer)]


def _ordner_sichern(pfad: str) -> None:
    """Zwingt den Eintrag einer umbenannten Datei auf die Platte (POSIX; unter Windows erledigt das ``os.replace`` selbst)."""
    if os.name == "nt":
        return
    try:
        fd = os.open(os.path.dirname(os.path.abspath(pfad)) or ".", os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def journal_schreiben(pfad: str, stellen: "list[tuple]", *, laenge_vorher: "int | None" = None) -> None:
    """Schreibt die Stellen ins Journal und zwingt es auf die Platte; die Ende-Marke kommt zuletzt und macht es gueltig.

    ``stellen``: ``(Offset, alte Bytes)`` oder ``(Offset, alte Bytes, neue Bytes)``. Mit den neuen Bytes kann das Zurueckspielen
    pruefen, ob das Journal zu diesem Abbild gehoert (Format 2) - Verwaltungsstellen sollten sie immer mitgeben. Die neuen Bytes duerfen
    auch ein Rueckruf sein, der sie erst hier liefert (Dateidaten: nie alle zugleich im Speicher); ``None`` aus ihm heisst unbekannt.
    ``laenge_vorher``: die Laenge des Abbilds vor dem Schreiben, wenn es wachsen wird (beim Zurueckspielen wird es darauf gekuerzt).
    """
    if os.path.lexists(pfad):
        # Ein frueherer Lauf scheiterte, und sein Journal liess sich nicht zurueckspielen: Es ist die einzige Rettung des Abbilds. Ein
        # neues haette die halb geschriebenen Bytes als "alt" festgehalten (Gesamtpruefung 23.11.2026). Erst neu oeffnen - das spielt
        # es zurueck oder legt es beiseite. Ausnahme: Das Abbild traegt an jeder geprueften Stelle schon die NEUEN Bytes - der Lauf ist
        # vollstaendig geschrieben, nur das Entfernen des Journals scheiterte (Virenscanner, Sync). Dann ist es erledigt und darf weg;
        # sonst kaeme beim Neuoeffnen ein Zurueckspielen, das die gespeicherten Aenderungen verwirft.
        if not _erledigt(pfad):
            raise DirektFehler("Ein unerledigtes Rueckgaengig-Journal liegt noch neben dem Abbild (%s) - bitte das Abbild neu "
                               "oeffnen, bevor erneut gespeichert wird." % os.path.basename(pfad))
        journal_entfernen(pfad)
    saetze: "list[tuple[int, bytes, Any]]" = [
        (int(s[0]), bytes(s[1]), s[2] if len(s) > 2 else None) for s in stellen]
    if laenge_vorher is not None:
        saetze.append((_LAENGE_SATZ, struct.pack("<Q", int(laenge_vorher)), None))
    teil = pfad + ".neu"
    try:
        with open(teil, "wb") as fh:
            fh.write(_MAGIC2)
            fh.write(struct.pack("<Q", len(saetze)))
            for offset, alt, neu in saetze:
                if callable(neu):
                    neu = neu()
                if neu is not None:
                    neu = bytes(neu)
                # Die neuen Pruefsummen decken den Bereich ab, den es vorher gab (``alt``): Waechst eine Stelle (PFS), ist der Rest neu;
                # ist die neue Stelle kuerzer, bleibt dahinter das Alte stehen.
                summen = (_sektor_summen(offset, neu[:len(alt)] + alt[len(neu):]) if neu is not None else None)
                fh.write(struct.pack("<QIII", offset, len(alt), zlib.crc32(alt) & 0xFFFFFFFF,
                                     len(summen) if summen is not None else _UNBEKANNT))
                fh.write(alt)
                if summen:
                    fh.write(struct.pack("<%dI" % len(summen), *summen))
            fh.write(_ENDE)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(teil, pfad)
    except BaseException:
        # Ein halbes ``.undo.neu`` (Platte voll, Abbruch) bleibt nicht liegen (Gesamtpruefung 14.11.2026, U6).
        try:
            os.remove(teil)
        except OSError:
            pass
        raise
    _ordner_sichern(pfad)


def _saetze_lesen(pfad: str) -> "list[tuple[int, bytes, list[int] | None]] | None":
    """Die Saetze eines vollstaendigen Journals (Format 1 oder 2), sonst ``None`` (fehlt, abgeschnitten, Pruefsumme falsch)."""
    try:
        with open(pfad, "rb") as fh:
            kennung = fh.read(len(_MAGIC2))
            if kennung == _MAGIC2:
                format2 = True
            elif kennung[:len(_MAGIC)] == _MAGIC:
                format2 = False
                fh.seek(len(_MAGIC))
            else:
                return None
            kopf = fh.read(8)
            if len(kopf) < 8:
                return None
            anzahl = struct.unpack("<Q", kopf)[0]
            saetze: "list[tuple[int, bytes, list[int] | None]]" = []
            for _ in range(anzahl):
                groesse = 20 if format2 else 16
                satz = fh.read(groesse)
                if len(satz) < groesse:
                    return None
                if format2:
                    offset, laenge, crc, summen_zahl = struct.unpack("<QIII", satz)
                else:
                    offset, laenge, crc = struct.unpack("<QII", satz)
                    summen_zahl = _UNBEKANNT
                alt = fh.read(laenge)
                if len(alt) < laenge or (zlib.crc32(alt) & 0xFFFFFFFF) != crc:
                    return None
                summen: "list[int] | None" = None
                if summen_zahl != _UNBEKANNT:
                    if summen_zahl != len(_stuecke(offset, laenge)):
                        return None
                    roh = fh.read(4 * summen_zahl)
                    if len(roh) < 4 * summen_zahl:
                        return None
                    summen = list(struct.unpack("<%dI" % summen_zahl, roh)) if summen_zahl else []
                saetze.append((offset, alt, summen))
            if fh.read(len(_ENDE)) != _ENDE:
                return None
            return saetze
    except OSError:
        return None


def _erledigt(pfad: str) -> bool:
    """Gehoert das Journal ``pfad`` zu einem vollstaendig geschriebenen Lauf? Jede Stelle mit bekannten neuen Bytes ist im Abbild
    Sektor fuer Sektor NEU (nicht "alt oder neu" wie beim Zurueckspielen). Ohne solche Stellen oder unlesbar: ``False``."""
    saetze = _saetze_lesen(pfad)
    abbild = pfad[:-len(JOURNAL_ENDUNG)] if pfad.endswith(JOURNAL_ENDUNG) else ""
    if not saetze or not abbild:
        return False
    geprueft = 0
    try:
        with open(abbild, "rb") as fh:
            for offset, alt, summen in saetze:
                if summen is None or offset == _LAENGE_SATZ:
                    continue
                fh.seek(offset)
                jetzt = fh.read(len(alt))
                if len(jetzt) < len(alt):
                    return False
                for n, (von, bis) in enumerate(_stuecke(offset, len(alt))):
                    if (zlib.crc32(jetzt[von:bis]) & 0xFFFFFFFF) != summen[n]:
                        return False
                geprueft += 1
    except OSError:
        return False
    return geprueft > 0


def journal_entfernen(pfad: str, versuche: int = 3) -> None:
    """Entfernt das Journal nach einem vollstaendigen Lauf - mit ein paar Versuchen: Ein Virenscanner oder ein Sync-Dienst haelt eine
    frisch geschriebene Datei kurz offen (Gesamtpruefung 23.11.2026). Scheitert es auch dann, kommt der Fehler (``OSError``)."""
    import time
    for versuch in range(max(1, versuche)):
        try:
            os.remove(pfad)
            return
        except FileNotFoundError:
            return
        except OSError:
            if versuch + 1 >= max(1, versuche):
                raise
            time.sleep(0.2 * (versuch + 1))


def journal_lesen(pfad: str) -> "list[tuple[int, bytes]] | None":
    """Die Saetze eines vollstaendigen Journals als ``(Offset, alte Bytes)`` (samt Laengensatz), sonst ``None``."""
    saetze = _saetze_lesen(pfad)
    return None if saetze is None else [(offset, alt) for offset, alt, _s in saetze]


def _gehoert_zum_abbild(fh, saetze: "list[tuple[int, bytes, list[int] | None]]") -> bool:
    """Ist jede Verwaltungsstelle mit bekannten neuen Bytes Sektor fuer Sektor alt oder neu? Dann ist es der unterbrochene Lauf."""
    for offset, alt, summen in saetze:
        if summen is None or offset == _LAENGE_SATZ:
            continue
        fh.seek(offset)
        jetzt = fh.read(len(alt))
        if len(jetzt) < len(alt):
            return False
        for n, (von, bis) in enumerate(_stuecke(offset, len(alt))):
            stueck = jetzt[von:bis]
            if stueck != alt[von:bis] and (zlib.crc32(stueck) & 0xFFFFFFFF) != summen[n]:
                return False
    return True


#: Ergebnisse von :func:`zurueckspielen`.
NICHTS, ZURUECKGESPIELT, UNVOLLSTAENDIG, FREMD, DEFEKT = "", "zurueckgespielt", "unvollstaendig", "fremd", "defekt"


def _fremd_pfad(pfad: str, endung: str = FREMD_ENDUNG) -> str:
    """Ein freier Name fuer ein beiseitegelegtes Journal: ``.undo.fremd``, sonst ``.undo.fremd2``, ... - nie ein frueheres ueberschreiben
    (Gesamtpruefung, R2-J3: es koennte die einzige Rettung eines anderen Laufs sein). Ebenso ``.undo.defekt``."""
    kandidat = pfad + endung
    nummer = 2
    while os.path.lexists(kandidat):
        kandidat = "%s%s%d" % (pfad, endung, nummer)
        nummer += 1
    return kandidat


def journal_zurueckspielen(abbild: str, *, eigen: bool = False) -> bool:
    """Wie :func:`zurueckspielen`; ``True``, wenn etwas zurueckgespielt wurde.

    Raises:
        DirektFehler: nur mit ``eigen=True`` (die Rueckabwicklung eines gescheiterten ``speichern``), wenn das eben geschriebene
            Journal sich nicht lesen liess - das Abbild kann halb geschrieben sein. Bis zum 23.11.2026 kam dann nur der urspruengliche
            Fehler, und das naechste Oeffnen fand ein ``.undo.defekt`` ohne Warnung (Gesamtpruefung, Gegenlese).
    """
    ergebnis, ort = zurueckspielen(abbild, eigen=eigen)
    if eigen and ergebnis == DEFEKT:
        raise DirektFehler("Speichern gescheitert, und das Rueckgaengig-Journal liess sich nicht lesen (beiseitegelegt als %s) - das "
                           "Abbild kann halb geschrieben sein; bitte mit Aufgabe 8 pruefen oder neu bauen."
                           % os.path.basename(ort))
    return ergebnis == ZURUECKGESPIELT


def zurueckspielen(abbild: str, *, eigen: bool = False) -> "tuple[str, str]":
    """Spielt ein vollstaendiges Journal zurueck (die alten Bytes, dann die alte Laenge) und entfernt es.

    Rueckgabe ``(Ergebnis, beiseitegelegt)``: :data:`NICHTS` (kein Journal), :data:`ZURUECKGESPIELT`, :data:`UNVOLLSTAENDIG` (ein halbes
    ``.undo.neu``: der Lauf brach vor dem ersten Schreiben ins Abbild ab, es wird nur entfernt), :data:`FREMD` oder :data:`DEFEKT` (ein
    ``.undo``, das sich nicht lesen laesst - das Abbild kann halb geschrieben sein) jeweils mit dem Pfad, unter dem das Journal jetzt
    liegt. Ein vollstaendiges ``.undo.neu`` ohne ``.undo`` (Strom weg, bevor das Umbenennen auf der Platte stand) gilt wie das
    Journal selbst (Gesamtpruefung 14.11.2026, U5). Gehoert das Journal nicht zu diesem Abbild (Format 2, E3), bleibt das Abbild
    unberuehrt.

    ``eigen=True``: Die Rueckabwicklung eines Editors im selben Lauf (ein Fehler mitten in ``speichern``) - das Journal hat er eben
    selbst geschrieben, es wird ohne Pruefung zurueckgespielt (R2-J1: sonst blieb ein halb geschriebenes Abbild ohne Journal zurueck).
    """
    pfad = journal_pfad(abbild)
    teil = pfad + ".neu"
    quelle = pfad if os.path.exists(pfad) else teil
    if not os.path.exists(quelle):
        return NICHTS, ""
    saetze = _saetze_lesen(quelle)
    if saetze is not None:
        laenge: "int | None" = None
        with open(abbild, "r+b") as fh:
            if not eigen and not _gehoert_zum_abbild(fh, saetze):
                fremd = True
            else:
                fremd = False
                for offset, alt, _s in reversed(saetze):
                    if offset == _LAENGE_SATZ:
                        if len(alt) == 8:
                            laenge = struct.unpack("<Q", alt)[0]
                        continue
                    fh.seek(offset)
                    fh.write(alt)
                if laenge is not None:
                    fh.truncate(laenge)
                fh.flush()
                os.fsync(fh.fileno())
        if fremd:
            ziel = _fremd_pfad(pfad)
            logger.warning("Undo-Journal passt nicht zu %s - nicht zurueckgespielt, beiseitegelegt als %s", abbild, ziel)
            try:
                os.replace(quelle, ziel)
            except OSError:
                ziel = quelle
            for datei in (pfad, teil):
                if datei != quelle:
                    try:
                        os.remove(datei)
                    except OSError:
                        pass
            return FREMD, ziel
    elif quelle == pfad:
        # Ein ``.undo`` entsteht nur vollstaendig (journal_schreiben benennt erst nach fsync um). Laesst es sich nicht lesen, ist es
        # beschaedigt - nicht "noch nichts geaendert": beiseitelegen und melden, nie loeschen (Gesamtpruefung 23.11.2026).
        ziel = _fremd_pfad(pfad, DEFEKT_ENDUNG)
        logger.warning("Undo-Journal zu %s laesst sich nicht lesen - nicht zurueckgespielt, beiseitegelegt als %s; "
                       "das Abbild kann halb geschrieben sein", abbild, ziel)
        try:
            os.replace(pfad, ziel)
        except OSError:
            ziel = pfad
        if ziel != pfad:
            try:
                os.remove(teil)
            except OSError:
                pass
        return DEFEKT, ziel
    for datei in (pfad, teil):
        try:
            os.remove(datei)
        except OSError:
            pass
    return (ZURUECKGESPIELT if saetze is not None else UNVOLLSTAENDIG), ""
