# -*- coding: utf-8 -*-
"""Die zwei Ablage-Mechaniken von ShadowMountPlus.

Zwischen 1.7 alpha6 und 1.7 alpha8 wurde umgebaut, und zwar so, dass eine
Ablage, die vorher richtig war, danach stillschweigend nicht mehr wirkt.
Das ist die teuerste Sorte Aenderung: Es gibt keine Fehlermeldung, das Spiel
startet einfach ohne die Ersatzbibliotheken.

**bis 1.7 alpha6** - die Ordner werden aus der laufenden Sandbox gelesen.
Alles, was in ``app0`` landet, zaehlt; ``fakelib2`` hat Vorrang vor
``fakelib``, und es wird immer nur *einer* von beiden eingehaengt. Globale
und spiel-eigene Bibliotheken werden als zwei unionfs-Schichten gestapelt.
Cache, Emulator-Dateien und AMPR-Download gibt es nicht.

**ab 1.7 alpha8** - feste Suchreihenfolge, erster Treffer gewinnt:

1. ``<scanpath>/backports/<TITLE_ID>/fakelib2/``
2. ``<scanpath>/backports/<TITLE_ID>/fakelib/``
3. ``<Spielquelle>/fakelib/``

Ein ``fakelib2`` im **Spielordner** wird hier ignoriert - der haeufigste
Fehler beim Umstieg. Statt zweier Schichten wird vorab ein Cache unter
``/data/shadowmount/cache/<TITLE_ID>/fakelib/`` zusammenkopiert.

Alle Angaben stammen aus den beiden Anleitungen vom 22.08.2026, die am
Quellcode von alpha6 bzw. alpha8 geprueft wurden (``src/sm_fakelib.c``,
``src/sm_config_mount.c``, ``src/sm_scan.c``, ``include/sm_paths.h``,
``config.ini.example``).
"""
from __future__ import annotations

import posixpath
from typing import Any

#: Die beiden Generationen.
ALT = "alt"
NEU = "neu"

#: Ordnernamen. Bewusst hier gespiegelt statt aus ps5_backport importiert:
#: Dieses Modul beschreibt fremdes Verhalten und soll sich nicht mit
#: aendern, wenn unser eigener Backport-Teil seine Namen anpasst.
FAKELIB = "fakelib"
FAKELIB2 = "fakelib2"

#: Wo die Ablage stattfinden kann.
#:
#: ``ORT_SPIEL`` und ``ORT_BACKPORT`` betreffen ein einzelnes Spiel und
#: arbeiten mit einem ``fakelib``-Unterordner. ``ORT_GLOBAL`` und
#: ``ORT_EMUS`` sind feste Ordner auf der Konsole, in denen die Dateien
#: **direkt** liegen - dort gibt es keinen Unterordner.
ORT_SPIEL = "spiel"
ORT_BACKPORT = "backport"
ORT_GLOBAL = "global"
ORT_EMUS = "emus"

#: Feste Pfade auf der Konsole.
GLOBAL_STANDARD = "/data/shadowmount/fakelib"
EMUS_STANDARD = "/data/shadowmount/emus"
CACHE_ORDNER = "/data/shadowmount/cache"
CONFIG_PFAD = "/data/shadowmount/config.ini"
DEBUG_LOG = "/data/shadowmount/debug.log"

#: Schluessel, die es **nur** ab alpha8 gibt. Steht einer davon in der
#: config.ini.example der Konsole, laeuft dort die neue Fassung.
NUR_NEU_SCHLUESSEL = ("update_emulators", "emulators_path",
                      "auto_update_ampr", "ampr_update_url")

#: Log-Zeile, die es nur in der neuen Fassung gibt.
NUR_NEU_LOGZEILE = "using cache for"


GENERATIONEN: dict[str, dict[str, Any]] = {
    ALT: {
        "kennung": ALT,
        "gilt_fuer": "ShadowMountPlus bis einschließlich 1.7 alpha6",
        "nicht_fuer": "1.7 alpha8 und neuer",
        # Im Spielordner wirken beide, fakelib2 hat Vorrang.
        "spiel_ordner": (FAKELIB2, FAKELIB),
        "spiel_fakelib2_wirkt": True,
        "backport_ordner": (FAKELIB2,),
        "backport_erlaubt": True,
        "orte": (ORT_BACKPORT, ORT_SPIEL, ORT_GLOBAL),
        "hat_cache": False,
        "hat_emus": False,
        "stapelt_schichten": True,
        "config_schluessel": (
            ("backport_fakelib", "1"),
            ("global_fakelib", "1"),
            ("global_fakelib_path", GLOBAL_STANDARD),
            ("global_fakelib_priority", "game"),
            ("global_fakelib_exclude", ""),
        ),
        "log_marken": (
            ("game libraries mounted for", "Spiel-fakelib aktiv"),
            ("global libraries mounted for", "Globale fakelib aktiv"),
            ("mount failed for", "Einhängen fehlgeschlagen, Stapel zurückgerollt"),
            ("global path unavailable for", "Globaler Pfad fehlt oder nicht lesbar"),
            ("global path is not a directory for", "Pfad zeigt auf eine Datei"),
            ("handoff active mount", "Spielwechsel, alter Mount wird abgeräumt"),
            ("unmount deferred for", "Ziel noch belegt (EBUSY)"),
        ),
    },
    NEU: {
        "kennung": NEU,
        "gilt_fuer": "ShadowMountPlus ab 1.7 alpha8",
        "nicht_fuer": "1.7 alpha6 und älter",
        # Im Spielordner zaehlt NUR fakelib.
        "spiel_ordner": (FAKELIB,),
        "spiel_fakelib2_wirkt": False,
        "backport_ordner": (FAKELIB2, FAKELIB),
        "backport_erlaubt": True,
        "orte": (ORT_BACKPORT, ORT_SPIEL, ORT_GLOBAL, ORT_EMUS),
        "hat_cache": True,
        "hat_emus": True,
        "stapelt_schichten": False,
        "config_schluessel": (
            ("backport_fakelib", "1"),
            ("update_emulators", "1"),
            ("emulators_path", EMUS_STANDARD),
            ("auto_update_ampr", "0"),
            ("ampr_update_url", ""),
            ("global_fakelib", "1"),
            ("global_fakelib_path", GLOBAL_STANDARD),
            ("global_fakelib_priority", "game"),
            ("global_fakelib_exclude", ""),
        ),
        "log_marken": (
            ("using cache for", "Zusammengeführter Cache wird eingehängt"),
            ("cache updated for", "Cache neu gebaut"),
            ("cache current for", "Cache ist aktuell, kein Neubau"),
            ("combined cache unavailable", "Globale fakelib für diesen Start ausgelassen"),
            ("libraries mounted for", "Mount aktiv"),
            ("cache build failed", "Speicherplatz und Rechte prüfen"),
            ("cache publish failed", "Speicherplatz und Rechte prüfen"),
            ("global path unavailable", "Globaler Pfad fehlt"),
            ("global path is not a directory", "Globaler Pfad ist eine Datei"),
            ("handoff active mount", "Spielwechsel, alter Mount wird abgeräumt"),
            ("unmount deferred for", "Ziel noch belegt (EBUSY)"),
        ),
    },
}


def profil(generation: str) -> dict[str, Any]:
    """Gibt das Profil einer Generation.

    Raises:
        KeyError: Bei einer unbekannten Kennung - lieber laut scheitern als
            still die falsche Mechanik anwenden.
    """
    return GENERATIONEN[generation]


def suchreihenfolge(generation: str) -> tuple[str, ...]:
    """Wonach ShadowMountPlus sucht - in der Reihenfolge, die entscheidet.

    Die beiden Generationen suchen grundverschieden, und das laesst sich
    nicht in dieselbe Form pressen:

    * **alt** kennt gar keine Pfadreihenfolge. Gelesen wird die laufende
      Sandbox, also ``app0`` - und dort liegen Spieldateien und
      Backport-Dateien laengst uebereinander, weil der Backport ueber das
      Spiel gelegt wird. Entschieden wird allein am Ordnernamen:
      ``fakelib2`` vor ``fakelib``.
    * **neu** geht eine feste Liste von Pfaden durch; der erste Treffer
      gewinnt, und der Spielordner steht darin ganz hinten.
    """
    p = profil(generation)
    if generation == ALT:
        return tuple("app0/%s/  (aus dem Spiel oder aus dem Backport)" % name
                     for name in p["spiel_ordner"])
    wege = ["<scanpath>/backports/<TITLE_ID>/%s/" % name
            for name in p["backport_ordner"]]
    wege += ["<Spielquelle>/%s/" % name for name in p["spiel_ordner"]]
    return tuple(wege)


def ablageordner(generation: str, ort: str) -> str:
    """Der Ordnername, der an diesem Ort tatsaechlich wirkt.

    Args:
        generation: ``ALT`` oder ``NEU``.
        ort: ``ORT_SPIEL`` oder ``ORT_BACKPORT``.

    Returns:
        Der Ordnername, den man nehmen muss - nicht der, den man nehmen
        koennte. Bei mehreren moeglichen gewinnt der bevorzugte.
    """
    p = profil(generation)
    if ort == ORT_BACKPORT:
        return p["backport_ordner"][0]
    if ort == ORT_SPIEL:
        return p["spiel_ordner"][0]
    if ort in (ORT_GLOBAL, ORT_EMUS):
        # Bewusst ein Fehler statt einer leeren Zeichenkette: Dort liegen
        # die Dateien direkt im konfigurierten Ordner. Wer hier einen Namen
        # bekaeme und ihn anhaengte, legte sie eine Ebene zu tief ab - und
        # ShadowMountPlus sieht nur die oberste.
        raise ValueError(
            "%r hat keinen Unterordner - die Dateien liegen direkt im "
            "konfigurierten Pfad (siehe ablageziel)." % (ort,))
    raise ValueError("unbekannter Ort: %r" % (ort,))


def _ablageziel_fest(generation: str, ort: str, *,
                     pfad: str = "") -> dict[str, Any]:
    """Die beiden festen Ordner auf der Konsole - global und Emulatoren.

    Beide sind in der ``config.ini`` verstellbar; steht dort ein anderer
    Pfad, gilt der. Deshalb nimmt diese Funktion ihn entgegen, statt den
    Standard zu erzwingen.
    """
    p = profil(generation)
    if ort == ORT_EMUS and not p["hat_emus"]:
        return {"pfad": "", "ordner": "", "wirkt": False, "empfohlen": False,
                "hinweis": ("Emulator-Dateien gibt es erst ab 1.7 alpha8. "
                            "Die ältere Fassung liest %s gar nicht."
                            % EMUS_STANDARD)}
    standard = GLOBAL_STANDARD if ort == ORT_GLOBAL else EMUS_STANDARD
    ziel = (str(pfad).strip() or standard).rstrip("/")

    if ort == ORT_GLOBAL:
        if generation == ALT:
            hinweis = ("Wird als zweite Schicht über das Spiel gelegt und "
                       "gilt für jedes erfasste Spiel. Bei gleichem "
                       "Dateinamen entscheidet global_fakelib_priority - "
                       "voreingestellt gewinnt die Datei des Spiels.")
        else:
            hinweis = ("Wird vollständig in den Cache kopiert und gilt für "
                       "jedes erfasste Spiel. Bei gleichem Dateinamen "
                       "entscheidet global_fakelib_priority - voreingestellt "
                       "gewinnt die Datei des Spiels.")
        return {"pfad": ziel, "ordner": "", "wirkt": True, "empfohlen": True,
                "hinweis": hinweis}

    # Emulator-Dateien. Die entscheidende Einschraenkung steht in
    # sm_fakelib.c (copy_emulator_files_to_cache): Bevor eine Datei aus
    # emulators_path in den Cache kommt, wird geprueft, ob es sie im
    # Spiel-fakelib ueberhaupt gibt - sonst wird sie uebersprungen.
    return {"pfad": ziel, "ordner": "", "wirkt": True, "empfohlen": True,
            "hinweis": ("Ersetzt nur Dateien, die im fakelib des Spiels "
                        "schon liegen - neue Namen werden übersprungen. "
                        "Für ein Spiel ohne libSceAmpr.sprx bringt dieser "
                        "Weg allein nichts.")}


def ablageziel(generation: str, ort: str, *, wurzel: str = "",
               title_id: str = "", scanpath: str = "",
               pfad: str = "") -> dict[str, Any]:
    """Rechnet aus, wohin die Bibliotheken gehoeren.

    Args:
        generation: ``ALT`` oder ``NEU``.
        ort: ``ORT_SPIEL``, ``ORT_BACKPORT``, ``ORT_GLOBAL`` oder
            ``ORT_EMUS``.
        wurzel: Spielordner - lokaler Pfad oder Pfad auf der Konsole.
        title_id: Nur fuer ``ORT_BACKPORT`` noetig.
        scanpath: Nur fuer ``ORT_BACKPORT`` noetig, z. B. ``/data/homebrew``.
        pfad: Nur fuer ``ORT_GLOBAL`` und ``ORT_EMUS`` - der in der
            ``config.ini`` eingetragene Ordner. Leer heisst: der Standard.

    Returns:
        ``{"pfad": str, "ordner": str, "wirkt": bool, "empfohlen": bool,
        "hinweis": str}`` - ``hinweis`` ist leer, wenn nichts zu sagen ist.
        ``ordner`` ist bei den festen Orten leer, weil es dort keinen
        Unterordner gibt.
    """
    if ort in (ORT_GLOBAL, ORT_EMUS):
        return _ablageziel_fest(generation, ort, pfad=pfad)

    ordner = ablageordner(generation, ort)

    if ort == ORT_BACKPORT:
        if not (title_id and scanpath):
            raise ValueError("Backport-Ablage braucht title_id und scanpath")
        pfad = posixpath.join(scanpath.rstrip("/"), "backports", title_id, ordner)
        hinweis = ""
        if generation == NEU:
            hinweis = ("Erster Treffer der Suchreihenfolge - das Spiel bleibt "
                       "unberührt.")
        else:
            hinweis = ("Der Backport wird über das Spiel gelegt und erscheint "
                       "dadurch ebenfalls in app0.")
        return {"pfad": pfad, "ordner": ordner, "wirkt": True,
                "empfohlen": True, "hinweis": hinweis}

    # Ablage im Spielordner.
    trenner = "/" if "/" in str(wurzel) or not wurzel else "\\"
    pfad = "%s%s%s" % (str(wurzel).rstrip("/\\"), trenner, ordner)
    hinweis = ""
    empfohlen = True
    if generation == NEU:
        empfohlen = False
        hinweis = ("Hier zählt nur %r. Ein %r im Spielordner wird ab alpha8 "
                   "ignoriert - ohne Meldung. Empfohlen ist die Ablage als "
                   "Backport." % (FAKELIB, FAKELIB2))
    else:
        hinweis = ("%r hat Vorrang vor %r; es wird immer nur einer von beiden "
                   "eingehängt." % (FAKELIB2, FAKELIB))
    return {"pfad": pfad, "ordner": ordner, "wirkt": True,
            "empfohlen": empfohlen, "hinweis": hinweis}


def beanstandungen(generation: str, ort: str,
                   vorhandene_ordner: "list[str] | tuple[str, ...]") -> list[str]:
    """Prueft eine bestehende Ablage und meldet, was nicht wirkt.

    Args:
        generation: ``ALT`` oder ``NEU``.
        ort: Wo die Ordner liegen.
        vorhandene_ordner: Die dort gefundenen Ordnernamen.

    Returns:
        Klartext-Beanstandungen; leere Liste, wenn alles wirkt.
    """
    da = {str(n).strip().lower() for n in vorhandene_ordner if str(n).strip()}
    p = profil(generation)
    meldungen: list[str] = []

    if ort == ORT_SPIEL:
        wirksam = set(p["spiel_ordner"])
        if FAKELIB2 in da and not p["spiel_fakelib2_wirkt"]:
            meldungen.append(
                "Im Spielordner liegt %r. Ab 1.7 alpha8 wird der dort "
                "ignoriert - umbenennen nach %r oder als Backport ablegen."
                % (FAKELIB2, FAKELIB))
        if generation == ALT and FAKELIB2 in da and FAKELIB in da:
            meldungen.append(
                "Beide Ordner vorhanden: %r gewinnt, der Inhalt von %r bleibt "
                "ungenutzt - auch wenn %r leer ist."
                % (FAKELIB2, FAKELIB, FAKELIB2))
        if da and not (da & wirksam):
            meldungen.append(
                "Keiner der gefundenen Ordner wirkt an dieser Stelle. "
                "Wirksam wäre: %s." % ", ".join(sorted(wirksam)))
    elif ort == ORT_BACKPORT:
        wirksam = set(p["backport_ordner"])
        if da and not (da & wirksam):
            meldungen.append(
                "Im Backport-Ordner wirkt nur: %s." % ", ".join(sorted(wirksam)))
        if generation == NEU and FAKELIB in da and FAKELIB2 in da:
            meldungen.append(
                "Beide Ordner vorhanden: %r steht in der Suchreihenfolge vor "
                "%r und gewinnt." % (FAKELIB2, FAKELIB))
    elif ort == ORT_GLOBAL:
        if FAKELIB in da or FAKELIB2 in da:
            meldungen.append(
                "Im globalen Ordner liegt ein Unterordner %r. Dort gehören "
                "die Bibliotheken direkt hinein - ein Unterordner wird "
                "mitkopiert, aber nicht eingehängt."
                % (FAKELIB if FAKELIB in da else FAKELIB2,))
    elif ort == ORT_EMUS:
        if not p["hat_emus"]:
            meldungen.append(
                "Diese Fassung liest %s nicht - der Ordner bleibt wirkungslos."
                % EMUS_STANDARD)
        if FAKELIB in da or FAKELIB2 in da:
            meldungen.append(
                "Im Emulator-Ordner liegt ein Unterordner %r. Verglichen "
                "werden nur Dateien direkt darin."
                % (FAKELIB if FAKELIB in da else FAKELIB2,))
    else:
        raise ValueError("unbekannter Ort: %r" % (ort,))
    return meldungen


def orte(generation: str) -> tuple[dict[str, Any], ...]:
    """Die Ablagewege dieser Fassung - in der Reihenfolge der Anleitung.

    Args:
        generation: ``ALT`` oder ``NEU``.

    Returns:
        Je Weg ``{"kennung", "standardpfad", "nur_konsole", "pro_spiel",
        "ersetzt_nur"}``:

        * ``nur_konsole`` - der Pfad liegt auf der Konsole und laesst sich
          nicht durch einen Ordner am Rechner ersetzen.
        * ``pro_spiel`` - der Weg betrifft ein einzelnes Spiel.
        * ``ersetzt_nur`` - es werden nur Dateien ersetzt, die im fakelib
          des Spiels schon liegen (gilt allein fuer die Emulator-Dateien).
    """
    p = profil(generation)
    beschreibung = {
        ORT_BACKPORT: dict(standardpfad="<scanpath>/backports/<TITLE_ID>/",
                           nur_konsole=False, pro_spiel=True,
                           ersetzt_nur=False),
        ORT_SPIEL: dict(standardpfad="<Spielordner>/",
                        nur_konsole=False, pro_spiel=True, ersetzt_nur=False),
        ORT_GLOBAL: dict(standardpfad=GLOBAL_STANDARD,
                         nur_konsole=True, pro_spiel=False, ersetzt_nur=False),
        ORT_EMUS: dict(standardpfad=EMUS_STANDARD,
                       nur_konsole=True, pro_spiel=False, ersetzt_nur=True),
    }
    ergebnis = []
    for kennung in p["orte"]:
        eintrag = dict(beschreibung[kennung])
        eintrag["kennung"] = kennung
        ergebnis.append(eintrag)
    return tuple(ergebnis)


def config_schluessel_fuer(generation: str, ort: str) -> tuple[str, ...]:
    """Welche config.ini-Schluessel dieser Weg braucht, um ueberhaupt zu wirken.

    Ohne sie legt man Dateien richtig ab und es passiert trotzdem nichts -
    genau die Sorte Fehler, die keine Meldung erzeugt.
    """
    if ort == ORT_GLOBAL:
        return ("global_fakelib", "global_fakelib_path")
    if ort == ORT_EMUS:
        if not profil(generation)["hat_emus"]:
            return ()
        return ("update_emulators", "emulators_path")
    return ("backport_fakelib",)


def generation_erkennen(*, config_text: str = "", cache_ordner_da: bool | None = None,
                        log_text: str = "") -> dict[str, Any]:
    """Bestimmt aus drei Anzeichen, welche Fassung auf der Konsole laeuft.

    Jedes Anzeichen allein genuegt laut beiden Anleitungen. Widersprechen
    sie sich, wird das gemeldet statt stillschweigend eines zu waehlen.

    Args:
        config_text: Inhalt der config.ini oder config.ini.example.
        cache_ordner_da: Ob ``/data/shadowmount/cache/`` existiert. ``None``
            heisst "nicht nachgesehen" - fehlender Cache beweist nichts,
            er entsteht erst bei Bedarf.
        log_text: Inhalt von debug.log.

    Returns:
        ``{"generation": ALT|NEU|"", "belege": [...], "widerspruch": bool}``
    """
    belege: list[tuple[str, str]] = []

    gefunden = [s for s in NUR_NEU_SCHLUESSEL if s in (config_text or "")]
    if gefunden:
        belege.append((NEU, "config.ini nennt %s" % ", ".join(gefunden)))
    elif config_text:
        belege.append((ALT, "config.ini nennt keinen der neuen Schlüssel"))

    if cache_ordner_da is True:
        belege.append((NEU, "%s/ existiert" % CACHE_ORDNER))
    # cache_ordner_da is False beweist nichts - der Cache entsteht erst,
    # wenn er gebraucht wird. Deshalb kein Beleg fuer ALT.

    if log_text and NUR_NEU_LOGZEILE in log_text:
        belege.append((NEU, "debug.log enthält %r" % NUR_NEU_LOGZEILE))

    kennungen = {k for k, _ in belege}
    if not kennungen:
        return {"generation": "", "belege": [], "widerspruch": False}
    if len(kennungen) > 1:
        return {"generation": "", "belege": belege, "widerspruch": True}
    return {"generation": kennungen.pop(), "belege": belege,
            "widerspruch": False}


def rangfolge(generation: str, prioritaet: str = "game") -> tuple[str, ...]:
    """In welcher Reihenfolge gleiche Dateinamen gewinnen.

    Args:
        generation: ``ALT`` oder ``NEU``.
        prioritaet: Wert von ``global_fakelib_priority`` - ``game`` oder
            ``global``.

    Returns:
        Von "verliert" nach "gewinnt" gelesen ist es die Einhaengereihenfolge;
        die Liste hier steht in der Reihenfolge, in der die Anleitungen sie
        nennen: was zuerst steht, setzt sich durch.
    """
    global_gewinnt = str(prioritaet).strip().lower() == "global"
    if generation == ALT:
        # Zwei Schichten: zuletzt eingehaengt liegt oben.
        return (("globale fakelib", "Spiel-fakelib") if global_gewinnt
                else ("Spiel-fakelib", "globale fakelib"))
    # Neue Fassung: alles wird in einen Cache kopiert.
    if global_gewinnt:
        return ("globale fakelib", "Emulator-Dateien", "Spiel-fakelib")
    return ("Emulator-Dateien", "Spiel-fakelib", "globale fakelib")


def cache_pfad(title_id: str) -> str:
    """Wohin die neue Fassung den zusammengefuehrten Cache legt."""
    return posixpath.join(CACHE_ORDNER, title_id, FAKELIB)


def stolperfallen(generation: str) -> tuple[str, ...]:
    """Die Punkte, an denen es in der Praxis haengt."""
    gemeinsam = (
        "Nur ein Spiel gleichzeitig - beim Wechsel wird der alte Mount zuerst "
        "abgeräumt; scheitert das, bekommt das neue Spiel keine fakelib.",
        "Die config.ini nicht während des Spiels ändern - jede Änderung an "
        "einem fakelib-Schlüssel entfernt sofort alle Overlays.",
        "Ohne common/lib in der Sandbox passiert nichts - stiller Abbruch "
        "ohne Meldung.",
        "Das BackPork-Payload muss aus sein; Parallelbetrieb kollidiert.",
    )
    if generation == ALT:
        return gemeinsam + (
            "Bei mehreren Sandboxen <TITLE_ID>_NNN gewinnt die höchste "
            "Nummer; alte Reste stören nicht.",
        )
    return gemeinsam + (
        "Der Cache-Ordner darf nicht als global_fakelib_path gesetzt werden - "
        "das wird abgelehnt.",
        "Der Kommentar über backport_fakelib in der mitgelieferten "
        "config.ini.example beschreibt noch das alte app0-Verhalten und ist "
        "stehengeblieben.",
    )
