# -*- coding: utf-8 -*-
"""Die neue AMPR-EMU-Methode: gepackte Asset-Baender statt loser Dateien.

Ab AMPR EMU 0.4.2.1 gibt es neben dem bisherigen Weg - Bibliothek in
``fakelib`` legen, ``ampr_emu.index`` bauen, fertig - einen zweiten: Die
Spieldateien wandern in gepackte Baender (``ampr_assets-*.pak``), und ein
Manifest (``ampr_assets.index``) sagt der Laufzeit, wo welcher Block liegt.
Das spart Platz und Dateideskriptoren; gelesen wird blockweise mit LZ4.

**Was dieses Modul bewusst nicht tut.** Der Herstellerweg beginnt mit
Mitschnitten von der Konsole (``ampr_commands.bin``): Man spielt das Spiel
mit einem Debug-Bau durch, und aus den beobachteten Zugriffen entsteht ein
Profil mit passender Blockgroesse je Datei. Diese Mitschnitte gibt es hier
nicht - wer ein Abbild baut, hat das Spiel noch nicht gespielt. Deshalb
schreibt :func:`standardprofil_text` ein **vorsichtiges** Profil ohne
Mitschnitte: einheitlich 64 KiB, ``mixed``, keine erzwungene Aufnahme.

Das ist keine Notloesung, sondern die Empfehlung des Herstellers fuer
unbekannte Daten - 64 KiB entspricht der Abrechnungsgroesse von APR, und
``mixed`` haelt wahlfreien Zugriff in Grenzen. Was ein Mitschnitt brachte,
waere eine feinere Blockwahl je Datei, nicht ein anderes Ergebnis.

**Der Fallstrick, der hier abgefangen wird.** ``ampr_pack.py`` schuetzt
``eboot.bin``, ``sce_sys`` und die Module nur beim *Entfernen* der Quellen
(``_REMOVAL_PROTECTED_*``), **nicht beim Packen**. Ein ``include = ["**"]``
packt sie mit - und das Spiel startet nicht mehr, denn das System liest sie
am AMPR EMU vorbei direkt vom Dateisystem. Die Ausschlussliste in
:data:`NIE_PACKEN` ist deshalb Bedingung, nicht Beiwerk.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import threading
import sys
from typing import Any, Callable

from ps5_validator.utils.nahtstellen import (Melder, Textquelle,
                                             schluessel_zeigen, stumm)
from ps5_validator.utils.werkzeuge_bereitstellen import suchwurzeln

logger = logging.getLogger("PS5Converter.utils.ampr_assetpakete")

#: Der mitgelieferte Werkzeugordner. Enthaelt ``ampr_pack.py`` samt
#: Formatmodul - beide muessen nebeneinander liegen, sonst findet der
#: Import des Werkzeugs sein ``ampr_pack_format`` nicht.
PACKWERKZEUG_ORDNER = "AMPR_PackTools-4.0"

#: Das Werkzeug selbst.
PACKWERKZEUG = "ampr_pack.py"

#: Die Fassung des Packformats, die dieser Ordner bedient.
PACKFORMAT = "AMPRPAK4"

#: Wie das Manifest heisst. Ohne diese Datei laedt die Laufzeit nichts.
MANIFEST_NAME = "ampr_assets.index"

#: Die Laufzeiteinstellungen neben dem Manifest. Fehlt sie, gelten die
#: einkompilierten Vorgaben - das ist zulaessig, aber nicht gewollt.
LAUFZEIT_NAME = "ampr_assets.index.runtime"

#: Die Pruefsummenbeilage. Die Konsole liest sie **nie**; ``verify`` und
#: ``unpack`` brauchen sie aber, und zwar zu genau diesem Bestand. Sie wandert
#: deshalb mit in den Spielordner (siehe :func:`bestand_uebernehmen`).
PRUEFSUMMEN_NAME = "ampr_assets.index.crc"

#: Erste Zeile jedes Profils, das dieses Programm schreibt. Daran erkennt
#: :func:`profil_ist_eigenes` ein eigenes Profil und unterscheidet es von
#: einem des Anwenders.
PROFIL_KENNZEILE = "# Vom PS5 Dump & Image Converter erzeugt"

#: Nur diese Varianten des AMPR EMU koennen gepackte Baender lesen. Eine
#: ``test-nopack``-Bibliothek findet das Manifest zwar, kann damit aber
#: nichts anfangen - das Spiel liefe dann ohne seine Daten.
PACKFAEHIGE_VARIANTEN: frozenset[str] = frozenset({
    "test-pack", "test-debug-pack",
})

#: Was niemals in ein Band wandert.
#:
#: Die ersten Zeilen sind Systemwege: Das Ladeprogramm der Konsole liest
#: sie, bevor der AMPR EMU ueberhaupt geladen ist. Danach die ausfuehrbaren
#: Dateien - dasselbe Argument. Zuletzt die AMPR-eigenen Dateien: Ein
#: Manifest, das sich selbst enthaelt, ist nicht ladbar.
#:
#: **Jeder Name steht doppelt da - einmal mit ``**/`` und einmal ohne.**
#: Das ist kein Versehen. ``**/eboot.bin`` verlangt mindestens ein
#: Verzeichnis davor und trifft die Datei im Wurzelverzeichnis von
#: ``/app0`` nicht - und genau dort liegt sie. Gemessen am 07.09.2026 mit
#: einem Testbaum aus acht Dateien: ``eboot.bin`` landete im Band, obwohl
#: ``**/eboot.bin`` ausgeschlossen war. Auf der Konsole waere das nicht
#: aufgefallen, sondern als startunfaehiges Spiel.
NIE_PACKEN: tuple[str, ...] = (
    "sce_sys/**",
    "sce_module/**",
    "system/**",
    "mods/**",
    "save/**",
    # Die Bibliotheksordner haengt ShadowMount+ direkt aus dem Dateisystem in
    # die Sandbox - am AMPR EMU vorbei. Die .sprx darin fing schon die Endung
    # ab, nicht aber die Markierungsdatei des Backports (FW7) und die
    # Sicherung libSceAmpr.sprx.orig; beide landeten bis zum 17.09.2026 im Band.
    "fakelib/**",
    "fakelib2/**",
    # Laufzeitprotokolle und Einstellungen der Stubs. ASSET_PACKS.md des
    # Entwicklers: "runtime logs excluded from recursive packing". Die
    # PlayGo-Einstellung liest der Stub selbst, nicht ueber den AMPR EMU.
    "ampr_emu.log", "**/ampr_emu.log",
    "apr_emu.log", "**/apr_emu.log",
    "ampr_commands.bin", "**/ampr_commands.bin",
    "playgo_stub.dat", "**/playgo_stub.dat",
    "playlgo.log", "**/playlgo.log",
    "*.prx", "**/*.prx",
    "*.sprx", "**/*.sprx",
    "*.self", "**/*.self",
    "*.elf", "**/*.elf",
    "*.bin.sig", "**/*.bin.sig",
    "eboot.bin", "**/eboot.bin",
    "param.sfo", "**/param.sfo",
    "nptitle.dat", "**/nptitle.dat",
    "ampr_emu.index", "**/ampr_emu.index",
    "ampr_assets.index", "**/ampr_assets.index",
    "ampr_assets.index.crc", "**/ampr_assets.index.crc",
    "ampr_assets.index.runtime", "**/ampr_assets.index.runtime",
    "ampr_assets-*.pak", "**/ampr_assets-*.pak",
    # --- Was das System selbst liest, nicht der AMPR EMU -----------------
    # Nachgetragen am 20.09.2026, nachdem drei Spiele mit Asset-Pack nicht
    # liefen. Die veroeffentlichten Profile der Gemeinschaft fuehren diese
    # Dateien unter "MUST REMAIN LOOSE" - Ghost of Yotei nennt
    # ``cache_ps5/playgo.pgm``, ``cache_ps5/game.sprig.packman`` und
    # ``cache_ps5/pgc_*_dummy_file`` einzeln, FF7 Rebirth und Spider-Man 2
    # fuehren dieselbe Liste. Der Grund steht in der Fehlertabelle der
    # Anleitung: "A packed file exists but in-game reading fails - mmap,
    # direct I/O, or another unintercepted path may be involved". PlayGo
    # liest seine Dateien ueber die Systemschicht, am Emulator vorbei.
    # Im echten Dump von Ghost of Yotei sind das playgo.pgm (4,3 MB),
    # game.sprig.packman und 23 pgc_*_dummy_file - unser Profil packte
    # bisher alle drei Sorten mit.
    "playgo.pgm", "**/playgo.pgm",
    "*.packman", "**/*.packman",
    "pgc_*_dummy_file", "**/pgc_*_dummy_file",
    # Die IL2CPP-Metadaten von Unity. Am 20.09.2026 an der Konsole
    # gemessen ("Wer wird Millionaer", ohne Originale gebaut): Der
    # Debug-Bau des Emulators meldete
    #   io.hook.error function=open errno=2 text=No such file or directory
    #   path=/app0/Media/Metadata/global-metadata.dat
    # und das Spiel beendete sich selbst
    # (SYSTEM_ABNORMAL_TERMINATION_REQUEST). Die Unity-Laufzeit laedt diese
    # Datei ganz frueh an der Emulation vorbei - genau der Fall aus der
    # Fehlertabelle der Anleitung ("mmap, direct I/O, or another
    # unintercepted path"). Jedes IL2CPP-Spiel traegt sie unter diesem
    # Namen.
    "global-metadata.dat", "**/global-metadata.dat",
    # Filme sind vorverdichtet; LZ4 bringt nichts und die Anleitung nennt
    # sie als Beispiel fuer Daten, die lose bleiben duerfen. Jedes
    # veroeffentlichte Profil haelt sie lose (Ghost: "movies/**",
    # FF7 Rebirth: "end/content/movie/**"). Gemessen: 205 Dateien,
    # 4,46 GB allein bei Ghost of Yotei.
    "movies/**", "**/movies/**",
    "movie/**", "**/movie/**",
)


class PackFehler(RuntimeError):
    """Der Packlauf ist gescheitert - mit einer Zeile, die das erklaert."""


def werkzeug_finden() -> str:
    """Sucht ``ampr_pack.py`` in den mitgelieferten Ordnern.

    Returns:
        Der volle Pfad - oder eine leere Zeichenkette, wenn der
        Werkzeugordner fehlt. Ein fehlendes Werkzeug ist kein Fehler
        dieses Moduls, sondern eine Aussage ueber den Bestand; der
        Aufrufer entscheidet, ob er die neue Methode dann anbietet.
    """
    for wurzel in suchwurzeln():
        kandidat = os.path.join(wurzel, PACKWERKZEUG_ORDNER, PACKWERKZEUG)
        if os.path.isfile(kandidat):
            return kandidat
    return ""


def werkzeugordner_finden() -> str:
    """Der Ordner mit ``ampr_pack.py`` und seinem Formatmodul.

    Beide muessen nebeneinander liegen - ``ampr_pack`` importiert
    ``ampr_pack_format`` als Geschwister. Wer das Werkzeug im eigenen Prozess
    laufen laesst, legt deshalb diesen Ordner auf ``sys.path``, nicht die
    einzelne Datei.
    """
    werkzeug = werkzeug_finden()
    return os.path.dirname(werkzeug) if werkzeug else ""


def lz4_vorhanden() -> bool:
    """Ist das LZ4-Modul da, ohne das ``ampr_pack.py`` nicht packt?

    Gefragt wird der **laufende** Prozess - und das ist seit dem 07.09.2026
    wieder richtig, weil :func:`_python_ruf` nicht mehr nach einem fremden
    Python sucht: Die fertige Programmdatei ruft sich selbst mit
    ``--ampr-pack`` auf, das Werkzeug laeuft also in genau diesem Prozess.

    Vorher stimmte die Frage nicht zur Antwort. ``_python_ruf`` nahm im
    gebuendelten Programm ein Python aus dem System, ``find_spec`` sah aber im
    eigenen Prozess nach. Gemessen auf dem Entwicklungsrechner, dessen .venv
    lz4 hat und dessen System-Python nicht: Die Pruefung meldete "vorhanden",
    und das Werkzeug scheiterte danach mit ``ModuleNotFoundError``.

    Bedingung dafuer, dass das hier stimmt: ``lz4`` steht in den
    ``hiddenimports`` aller drei ``.spec``-Dateien. Der Quelltext importiert
    es nirgends unmittelbar - PyInstaller findet es sonst nicht.
    """
    try:
        import importlib.util
        return importlib.util.find_spec("lz4.block") is not None
    except Exception as exc:  # noqa: BLE001
        logger.debug("LZ4-Pruefung nicht moeglich: %s", exc)
        return False


def einsatzbereit() -> tuple[bool, str]:
    """Kann die neue Methode ueberhaupt laufen?

    Returns:
        (bereit, grund). ``grund`` ist ein Uebersetzungsschluessel, kein
        fertiger Text - die Meldung entsteht dort, wo eine Sprache bekannt
        ist.
    """
    if not werkzeug_finden():
        return False, "ampr_pack.werkzeug_fehlt"
    if not lz4_vorhanden():
        return False, "ampr_pack.lz4_fehlt"
    return True, ""


def variante_kann_packen(variante: str) -> bool:
    """Liest die gewaehlte AMPR-Variante gepackte Baender?"""
    return str(variante or "").strip().lower() in PACKFAEHIGE_VARIANTEN


def standardprofil_text(arbeiter: int = 0,
                        zusatz_ausschluss: "tuple[str, ...]" = ()) -> str:
    """Ein Packprofil ohne Mitschnitte - vorsichtig, aber vollstaendig.

    Die Werte stammen aus der mitgelieferten ``ampr_pack.example.toml``
    des Herstellers. Abweichend davon:

    * ``include = ["**"]`` statt einer Aufzaehlung von ``assets/``,
      ``data/`` und dergleichen. Diese Namen sind Beispiele aus einem
      bestimmten Spiel; welche Ordner ein beliebiger Titel hat, weiss hier
      niemand. Was uebrig bleibt, faengt :data:`NIE_PACKEN` ab.
    * ``force_pack`` bleibt **ungesetzt**. Es unterdrueckt die
      Rueckgabe schlecht komprimierbarer Dateien in den losen Bestand -
      sinnvoll, wenn ein Mitschnitt den Zugriff belegt, hier aber geraten.
    * ``auto_loose_large_files = true`` bleibt an: Grosse Dateien ohne
      messbaren Gewinn bleiben lose, statt Rechenzeit zu kosten.

    Args:
        arbeiter: Anzahl der Packvorgaenge auf dem PC. 0 laesst das
            Werkzeug selbst waehlen.
    """
    # Die festen Muster plus die Filmordner dieses Spiels. Letztere kommen
    # aus dem Ordnerbaum, weil das Werkzeug die Schreibung genau nimmt.
    ausschluss = "\n".join('  "%s",' % muster
                           for muster in (*NIE_PACKEN, *zusatz_ausschluss))
    zeilen = [
        PROFIL_KENNZEILE + " - Packprofil ohne Mitschnitte.",
        "# Einheitlich 64 KiB/mixed: die Herstellerempfehlung fuer unbekannte",
        "# Zugriffsmuster. Wer Mitschnitte von der Konsole hat, erzeugt mit",
        "# ampr_pack_profile.py ein feineres Profil und ersetzt diese Datei.",
        "",
        "[pack]",
        'index_name = "%s"' % MANIFEST_NAME,
        'pack_pattern = "ampr_assets-{group}-lane{lane:02d}-vol{volume:02d}-{id:03d}.pak"',
        "",
        "# Was keine Regel trifft, bleibt eine gewoehnliche Datei.",
        'default_action = "loose"',
        'default_block_size = "64KiB"',
        "",
        'io_page_size = "64KiB"',
        'payload_alignment = "64KiB"',
        'chunk_alignment = "64B"',
        "",
        'compression_mode = "hc"',
        "compression_level = 12",
        "deduplicate = true",
        'deduplicate_scope = "lane"',
        "deduplicate_streaming = false",
        "min_savings_bytes = 64",
        "min_savings_ratio = 0.01",
        'io_neutral_min_savings_bytes = "8KiB"',
        "io_neutral_min_savings_ratio = 0.125",
        "",
        "# Grosse, bereits verdichtete Dateien ohne Gewinn bleiben lose.",
        "auto_loose_large_files = true",
        "auto_loose_hot_files = false",
        'auto_loose_min_file_size = "64MiB"',
        "auto_loose_sample_blocks = 32",
        'auto_loose_sample_bytes = "16MiB"',
        "auto_loose_min_savings_ratio = 0.05",
        "auto_loose_max_raw_ratio = 0.90",
        "",
        "preserve_mtime = true",
        "validate_index_metadata = true",
    ]
    if arbeiter > 0:
        zeilen.append("workers = %d" % int(arbeiter))
    zeilen += [
        "",
        "[groups.assets]",
        "pack_count = 4",
        'assignment = "balanced"',
        'max_pack_size = "8GiB"',
        "stripe_large_files = false",
        "",
        "[[rule]]",
        'action = "compress"',
        'include = ["**"]',
        "exclude = [",
        ausschluss,
        "]",
        'block_size = "64KiB"',
        'group = "assets"',
        'layout = "mixed"',
        "",
        "# Vorgaben der Laufzeit. Sie vergroessern den fest einkompilierten",
        "# Speicherblock (384 MiB) nicht, sondern fordern daraus an.",
        "[runtime]",
        'decoded_cache_bytes = "96MiB"',
        'physical_cache_bytes = "32MiB"',
        "workers = 4",
        "latency_reserve_workers = 1",
        "",
    ]
    return "\n".join(zeilen)


def profil_ist_eigenes(pfad: str) -> bool:
    """Stammt das Profil von diesem Programm (und nicht vom Anwender)?

    Erkannt an der ersten Zeile, die :func:`standardprofil_text` schreibt.
    """
    try:
        with open(pfad, "r", encoding="utf-8", errors="replace") as datei:
            return datei.readline().startswith(PROFIL_KENNZEILE)
    except OSError:
        return False


#: Ordnernamen, hinter denen Filme und Videos liegen - in irgendeiner
#: Schreibung. Jedes veroeffentlichte Profil haelt diesen Bestand lose:
#: Ghost of Yotei "movies/**", FF7 Rebirth "end/content/movie/**",
#: Spider-Man 2 "d/movie", Astro Bot "data/prein/video/*"; Cyberpunk
#: erreicht dasselbe ueber auto_loose (die Dateien sind gross und schon
#: verdichtet). Videos liest die Konsole ueber ihren eigenen Dekoder, also
#: nicht zwingend ueber den AMPR EMU.
FILMORDNER: tuple[str, ...] = ("movie", "movies", "video", "videos")


def filmordner_muster(app0: str) -> tuple[str, ...]:
    """Ausschlussmuster fuer die Filmordner **dieses** Spiels.

    Warum aus dem Ordnerbaum und nicht aus einer festen Liste: Das Werkzeug
    vergleicht mit ``fnmatch.fnmatchcase``, also **genau** nach Schreibung
    (``glob_matches`` in ampr_pack_format.py). Ein festes ``movies/**``
    trifft deshalb ``Media/StreamingAssets/Movies/`` nicht - am 20.09.2026
    an "Wer wird Millionaer" gemessen: 17 von 17 Filmen landeten im Band,
    obwohl die Ausschlussliste "movies" kannte. Aus dem echten Baum
    gelesen, stimmt die Schreibung immer.

    Args:
        app0: Der Spielordner (die spaetere ``/app0``-Wurzel).

    Returns:
        Muster wie ``"Media/StreamingAssets/Movies/**"`` - je gefundenem
        Ordner eines, in der Schreibung des Dateisystems.
    """
    gefunden: list[str] = []
    try:
        for wurzel, ordner, _dateien in os.walk(str(app0)):
            for name in ordner:
                if name.lower() not in FILMORDNER:
                    continue
                rel = os.path.relpath(os.path.join(wurzel, name), str(app0))
                gefunden.append(rel.replace("\\", "/") + "/**")
    except OSError as exc:
        logger.debug("Filmordner nicht suchbar (%s): %s", app0, exc)
    return tuple(sorted(set(gefunden)))


def systemdateien_muster(app0: str) -> tuple[str, ...]:
    """Ausschlussmuster fuer die Systemdateien **dieses** Spiels.

    Dieselbe Begruendung wie bei :func:`filmordner_muster`: Die festen
    Muster in :data:`NIE_PACKEN` sind kleingeschrieben, und das Werkzeug
    vergleicht mit ``fnmatch.fnmatchcase``. Ein Titel mit ``PlayGo.pgm``
    wuerde sonst am Riegel (:func:`systemdateien_im_pack`) haengen bleiben -
    der bricht den Bau ab, statt die Datei einfach lose zu lassen. Aus dem
    Baum gelesen stimmt die Schreibung.

    Returns:
        Genau die Pfade, die im Spielordner wirklich liegen.
    """
    import fnmatch

    gefunden: list[str] = []
    try:
        for wurzel, _ordner, dateien in os.walk(str(app0)):
            for name in dateien:
                klein = name.lower()
                if not any(fnmatch.fnmatch(klein, m) for m in SYSTEMDATEIEN):
                    continue
                rel = os.path.relpath(os.path.join(wurzel, name), str(app0))
                gefunden.append(rel.replace("\\", "/"))
    except OSError as exc:
        logger.debug("Systemdateien nicht suchbar (%s): %s", app0, exc)
    return tuple(sorted(set(gefunden)))


#: Dateien, an denen eine Spielengine erkennbar ist, die ihre Daten **am
#: Emulator vorbei** liest.
#:
#: Am 20.09.2026 an der Konsole gemessen ("Wer wird Millionaer", ohne
#: Originale gebaut, Debug-Bau des AMPR EMU 0.4.2.1): Der Emulator meldete
#: fuer genau diese fuenf Dateien der Unity-Laufzeit
#: ``io.hook.error function=stat|open errno=2 No such file or directory``
#: (12 x stat, 7 x open, 6 x sceKernelClose) - er hat sie also **nicht** aus
#: den Baendern bedient. Im ganzen Mitschnitt stand keine einzige
#: ``apr.pack``-Zeile; das Spiel beendete sich danach selbst. Mit denselben
#: Baendern **und** den Originalen daneben lief dasselbe Spiel durch.
#:
#: Die Baender bedienen nur Lesevorgaenge, die ueber APR laufen. Was eine
#: Engine mit gewoehnlichem Datei-I/O liest, muss als Datei dort liegen -
#: genau der Fall, den die Fehlertabelle der Anleitung als "mmap, direct
#: I/O, or another unintercepted path" fuehrt. Deshalb baut der Entwickler
#: seine Profile aus Mitschnitten: Ins Band darf nur, was ein Titel
#: nachweislich ueber APR liest.
#:
#: Warum die Folge **keine** laengere Ausschlussliste ist, sondern ein
#: Riegel: Im Abbild, das abstuerzte, waren 197 von 259 Dateien gepackt und
#: entfernt (nachgemessen am fertigen Abbild) - darunter vier der fuenf
#: Namen hier. Im Mitschnitt steht aber **keine einzige** ``apr.pack``-Zeile.
#: Es gibt also keinen Beleg, dass fuer diesen Titel ueberhaupt **eine**
#: gepackte Datei bedient wurde; die vier sind nur die, an denen es sofort
#: auffiel. Vier Namen mehr auszuschliessen hiesse raten, dass die
#: uebrigen 193 tragen. ``data.unity3d`` ist ausserdem der Hauptbestand des
#: Spiels - lose gelassen bliebe vom Pack ohnehin nichts.
DIREKTLESER: dict[str, tuple[str, ...]] = {
    "Unity": (
        "global-metadata.dat",
        "data.unity3d",
        "globalgamemanagers",
        "ScriptingAssemblies.json",
        "RuntimeInitializeOnLoads.json",
    ),
}


def direktleser_merkmale(app0: str) -> tuple[str, tuple[str, ...]]:
    """Traegt dieser Titel eine Engine, die am Emulator vorbei liest?

    Gesucht wird nach den Dateinamen aus :data:`DIREKTLESER`, ohne
    Ruecksicht auf die Schreibung und an jeder Stelle im Baum: Unity legt
    seinen Datenordner je nach Projekt anders an (gemessen unter
    ``Media/``, ueblich sind auch ``<Spiel>_Data/`` und ``Data/``).

    Args:
        app0: Der Spielordner (die spaetere ``/app0``-Wurzel).

    Returns:
        ``(Name der Engine, gefundene Pfade)`` - relativ zu ``app0`` und in
        der Schreibung des Dateisystems - oder ``("", ())``, wenn nichts
        darauf hindeutet.
    """
    gesucht = {name.lower(): engine
               for engine, namen in DIREKTLESER.items()
               for name in namen}
    gefunden: dict[str, list[str]] = {}
    try:
        for wurzel, _ordner, dateien in os.walk(str(app0)):
            for name in dateien:
                engine = gesucht.get(name.lower())
                if not engine:
                    continue
                rel = os.path.relpath(os.path.join(wurzel, name), str(app0))
                gefunden.setdefault(engine, []).append(rel.replace("\\", "/"))
    except OSError as exc:
        logger.debug("Direktleser nicht suchbar (%s): %s", app0, exc)
    if not gefunden:
        return "", ()
    # Bei mehreren Treffern gewinnt die Engine mit den meisten Merkmalen -
    # eine einzelne gleichnamige Datei soll keinen Titel umdeuten.
    engine = max(gefunden, key=lambda k: (len(gefunden[k]), k))
    return engine, tuple(sorted(set(gefunden[engine])))


def videos_im_pack(zeilen: list[dict[str, Any]]) -> list[str]:
    """Welche gepackten Dateien liegen in einem Film-/Videoordner?

    Anders als :func:`systemdateien_im_pack` ist das **kein** Abbruchgrund:
    Dass ein gepacktes Video ein Spiel wirklich anhaelt, ist hier nicht
    gemessen - belegt ist nur, dass jedes veroeffentlichte Profil solche
    Dateien lose laesst. Deshalb eine Warnung, kein Riegel.
    """
    getroffen: list[str] = []
    for zeile in zeilen:
        if not isinstance(zeile, dict) or not zeile.get("packed"):
            continue
        pfad = str(zeile.get("path") or "").replace("\\", "/")
        teile = [t.lower() for t in pfad.split("/")[:-1]]
        if any(t in FILMORDNER for t in teile):
            getroffen.append(pfad)
    return getroffen


def profil_schreiben(ziel: str, arbeiter: int = 0, app0: str = "") -> str:
    """Legt das Standardprofil ab - ein eigenes des Anwenders bleibt.

    Ein Profil des Anwenders bleibt unangetastet: Wer eines aus Mitschnitten
    erzeugt und dorthin gelegt hat, will es benutzt sehen - es beim
    naechsten Lauf zu ueberschreiben waere der teuerste Datenverlust, den
    dieses Modul anrichten koennte.

    Ein Profil, das dieses Programm selbst geschrieben hat, wird dagegen
    **jedes Mal neu** geschrieben. Bis zum 17.09.2026 blieb es liegen: Ein
    abgebrochener Lauf liess den Ausgabeordner samt Profil neben dem
    Spielordner zurueck (gemessen bei Ghost of Yotei, 12.09.2026), und jeder
    spaetere Lauf packte mit dem alten Profil weiter - auch nachdem sich die
    Ausschlussliste im Programm geaendert hatte.

    Returns:
        Der Pfad des Profils.
    """
    if os.path.isfile(ziel) and not profil_ist_eigenes(ziel):
        return ziel
    ordner = os.path.dirname(os.path.abspath(ziel))
    if ordner:
        os.makedirs(ordner, exist_ok=True)
    with open(ziel, "w", encoding="utf-8", newline="\n") as datei:
        zusatz = ((*filmordner_muster(app0), *systemdateien_muster(app0))
                  if app0 else ())
        datei.write(standardprofil_text(arbeiter, zusatz))
    return ziel


#: Interner Schalter, mit dem sich die fertige Programmdatei selbst als
#: Packwerkzeug aufruft. Behandelt wird er ganz vorn in ``main`` (siehe dort
#: ``_run_ampr_pack_subcommand``), noch vor der Rechtepruefung.
SELBSTAUFRUF = "--ampr-pack"


def _python_ruf() -> list[str]:
    """Womit ``ampr_pack.py`` gestartet wird - samt Weg zum Werkzeug.

    **Die fertige Programmdatei ruft sich selbst auf.** ``sys.executable`` ist
    dort das Programm und kein Python; mit dem Schalter :data:`SELBSTAUFRUF`
    verhaelt es sich aber wie eines. Genau so macht es das eingebettete
    PS4-Werkzeug seit jeher (``ps4_werkzeug.py``, ``--ps4ffpsc``).

    Bis zum 07.09.2026 wurde stattdessen ``python3``/``python``/``py`` im
    System gesucht. Das brach das Versprechen der einen Datei: Wer kein Python
    installiert hatte, bekam "Kein Python gefunden", und wer eines hatte,
    brauchte darin zusaetzlich ``lz4``. Die neue Methode war damit fuer jeden
    unerreichbar, der nur die Programmdatei heruntergeladen hat.

    Raises:
        PackFehler: Wenn das Werkzeug gar nicht mitgeliefert ist.
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, SELBSTAUFRUF]
    werkzeug = werkzeug_finden()
    if not werkzeug:
        raise PackFehler("ampr_pack.werkzeug_fehlt")
    return [sys.executable, werkzeug]


#: Muster der Fortschrittszeilen von ``ampr_pack.py``.
#:
#: Das Werkzeug schreibt sie auf ``stderr``, zum Beispiel::
#:
#:     [pack  42%] packing: files 120/300, 1.2 GiB/3.4 GiB, ..., elapsed 00:00:30
#:
#: Die Prozentzahl steht rechtsbuendig in drei Stellen ("  0%" bis "100%").
#: Bis zum 08.09.2026 landeten diese Zeilen nur im Protokoll - der Balken
#: stand waehrend des ganzen Packens still, und bei einem grossen Spiel sind
#: das viele Minuten, in denen nichts darauf hindeutet, dass etwas geschieht.
#:
#: ``verify`` meldet nichts dergleichen: Es rechnet und gibt am Ende JSON aus.
#: Dafuer gibt es keinen Prozentwert, nur die Aussage "laeuft noch".
FORTSCHRITT_MUSTER = re.compile(r"^\[pack\s+(\d{1,3})\s*%\]\s*([A-Za-z_]+)?")


def fortschritt_lesen(zeile: str) -> tuple[float, str] | None:
    """Liest Prozentwert und Phase aus einer Fortschrittszeile.

    Returns:
        ``(prozent, phase)`` - oder ``None``, wenn die Zeile keine ist.
    """
    treffer = FORTSCHRITT_MUSTER.match(str(zeile or "").strip())
    if not treffer:
        return None
    try:
        prozent = float(treffer.group(1))
    except (TypeError, ValueError):
        return None
    return min(100.0, max(0.0, prozent)), (treffer.group(2) or "")


def _lauf(argumente: list[str], melden: Melder,
          abbruch: Callable[[], bool] | None = None,
          fortschritt: Callable[[float, str], None] | None = None) -> str:
    """Startet das Werkzeug und reicht seine Ausgabe durch.

    ``ampr_pack.py`` schreibt den Fortschritt auf ``stderr`` und haelt
    ``stdout`` fuer das abschliessende JSON frei. Beides wird getrennt
    gelesen, damit die JSON-Zeile nicht zwischen Fortschrittszeilen
    verlorengeht.
    """
    werkzeug = werkzeug_finden()
    if not werkzeug:
        raise PackFehler("ampr_pack.werkzeug_fehlt")

    # _python_ruf bringt den Weg zum Werkzeug schon mit: In der fertigen
    # Programmdatei ist das der Selbstaufruf, sonst der Pfad der .py-Datei.
    befehl = _python_ruf() + argumente
    logger.debug("AMPR-Packlauf: %s", " ".join(befehl))

    startinfo = None
    if os.name == "nt":
        startinfo = subprocess.STARTUPINFO()
        startinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    # Das Kind (ampr_pack.py bzw. der EXE-Selbstaufruf) schreibt seinen
    # Fortschritt mit dem aktuellen Dateipfad auf stderr. Ohne erzwungenes
    # UTF-8 stuenden seine Stroeme unter Windows auf der ANSI-Codepage
    # (cp1252), und ein Pfad mit Sonderzeichen (z. B. "Yotei" mit o-Makron,
    # U+014D) braechte den Lauf mit UnicodeEncodeError ab. PYTHONUTF8 stellt
    # zusaetzlich open() im Kind auf UTF-8. Deckt auch den Nicht-EXE-Fall ab,
    # in dem _stroeme_absichern gar nicht laeuft.
    umgebung = dict(os.environ)
    umgebung["PYTHONUTF8"] = "1"
    umgebung["PYTHONIOENCODING"] = "utf-8"
    prozess = subprocess.Popen(
        befehl, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
        cwd=os.path.dirname(werkzeug), startupinfo=startinfo,
        env=umgebung,
    )

    # stdout wird nebenher geleert - als Vorsorge, nicht als Fehlerbehebung.
    #
    # Bis zum 12.09.2026 wurde es erst nach der stderr-Schleife gelesen
    # ("ausgabe = prozess.stdout.read()"). Solange die Schleife laeuft,
    # bleibt der stdout-Puffer ungeleert; unter Windows fasst er rund
    # 64 KB. Schreibt das Werkzeug mehr, blockiert es und der Elternprozess
    # wartet auf ein stderr-EOF, das nie kommt - ein Deadlock.
    #
    # **Gemessen ist dieser Fall hier nicht.** Ein Lauf ueber 4000 Dateien
    # am 12.09.2026 brachte nur 664 Byte auf stdout: Das Abschluss-JSON
    # nennt allein die **nicht** gepackten Dateien, und das waren zwei. Der
    # Weg dorthin ist also weit; erreichbar bleibt er trotzdem - ein Titel
    # mit vielen unkomprimierbaren Dateien fuellt die Liste.
    #
    # Der Absturz, den der Anwender am selben Tag gemeldet hat, hatte eine
    # andere Ursache: Die Programmdatei ist mit ``console=False`` gebaut,
    # und beim Selbstaufruf ``--ampr-pack`` war ``sys.stderr`` unbrauchbar.
    # Siehe ``_stroeme_absichern`` im Hauptmodul.
    sammler: list[str] = []

    def _stdout_leeren() -> None:
        if prozess.stdout is None:
            return
        try:
            for stueck in prozess.stdout:
                sammler.append(stueck)
        except Exception as exc:  # noqa: BLE001
            logger.debug("stdout des Packwerkzeugs nicht lesbar: %s", exc)

    leser = threading.Thread(target=_stdout_leeren, daemon=True,
                             name="ampr-pack-stdout")
    leser.start()

    # Der Abbruch wird zusaetzlich unabhaengig von der Ausgabe abgefragt. Die
    # Schleife unten fragt ihn nur, wenn eine stderr-Zeile ankommt - "verify"
    # schreibt waehrend der ganzen Pruefung nichts. Bis v1.9.24 wirkte
    # Abbrechen dort erst, wenn die Pruefung (bei einem grossen Spiel die
    # laengste Phase) von selbst zu Ende war.
    abgebrochen = threading.Event()

    def _abbruch_waechter() -> None:
        while prozess.poll() is None:
            if abbruch is not None and abbruch():
                abgebrochen.set()
                try:
                    prozess.terminate()
                except OSError as exc:
                    logger.debug("Packwerkzeug nicht beendbar: %s", exc)
                return
            abgebrochen.wait(0.5)

    if abbruch is not None:
        threading.Thread(target=_abbruch_waechter, daemon=True,
                         name="ampr-pack-abbruch").start()

    fehlerzeilen: list[str] = []
    try:
        assert prozess.stderr is not None
        for zeile in prozess.stderr:
            zeile = zeile.rstrip()
            if not zeile:
                continue
            fehlerzeilen.append(zeile)
            gelesen = fortschritt_lesen(zeile)
            if gelesen is not None:
                # Fortschrittszeilen gehen an den Balken, nicht ins Protokoll:
                # Das Werkzeug schreibt viele davon, und im Protokoll waeren
                # sie nur Rauschen zwischen den Meldungen, auf die es ankommt.
                if fortschritt is not None:
                    try:
                        fortschritt(*gelesen)
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("Packfortschritt nicht anzeigbar: %s", exc)
            else:
                melden("[AMPR-PACK] %s" % zeile)
            if abbruch is not None and abbruch():
                prozess.terminate()
                raise PackFehler("ampr_pack.abgebrochen")
    finally:
        prozess.wait()
        # Erst jetzt ist sicher, dass der Leser alles hat.
        leser.join(timeout=30.0)
        for strom in (prozess.stdout, prozess.stderr):
            if strom is not None:
                strom.close()

    if abgebrochen.is_set():
        raise PackFehler("ampr_pack.abgebrochen")
    if prozess.returncode != 0:
        letzte = fehlerzeilen[-1] if fehlerzeilen else ""
        raise PackFehler(letzte or "Rueckgabewert %d" % prozess.returncode)
    return "".join(sammler)


def packen(app0: str, ampr_index: str, ausgabe_ordner: str, profil: str,
           melden: Melder = stumm,
           abbruch: Callable[[], bool] | None = None,
           fortschritt: Callable[[float, str], None] | None = None
           ) -> dict[str, Any]:
    """Baut die Baender und das Manifest.

    Returns:
        Die JSON-Zusammenfassung des Werkzeugs. Darin steht unter
        ``loose_paths``, was **nicht** gepackt wurde und deshalb weiterhin
        als Datei vorhanden sein muss.
    """
    os.makedirs(ausgabe_ordner, exist_ok=True)
    roh = _lauf([
        "pack",
        "--root", app0,
        "--ampr-index", ampr_index,
        "--output", ausgabe_ordner,
        "--config", profil,
    ], melden, abbruch, fortschritt)
    try:
        return json.loads(roh or "{}")
    except ValueError as exc:
        raise PackFehler("Zusammenfassung nicht lesbar: %s" % exc) from exc


def pruefen(manifest: str, app0: str = "", melden: Melder = stumm,
            abbruch: Callable[[], bool] | None = None) -> None:
    """Prueft jeden Block gegen die Pruefsummenbeilage.

    Args:
        app0: Ist er gesetzt, wird jede gepackte Datei zusaetzlich
            zurueckgerechnet und Byte fuer Byte mit dem Original
            verglichen. Ohne diesen Vergleich sagt ein bestandener Lauf
            nur, dass die Baender in sich stimmig sind - nicht, dass sie
            den Spielinhalt tragen.
    """
    argumente = ["verify", "--index", manifest]
    if app0:
        argumente += ["--root", app0]
    _lauf(argumente, melden, abbruch)


def zusammenfassung(manifest: str, melden: Melder = stumm) -> str:
    """Die Manifestuebersicht des Werkzeugs als Text."""
    return _lauf(["inspect", "--index", manifest], melden)


#: Harte Grenzen der Laufzeit (Anleitung des Autors, Abschnitt "Hard format
#: and runtime limits"). Sie sind keine Empfehlung: "Even if the TOML parser
#: accepts a larger pack_count, the runtime will not load that set." Ein
#: Bestand darueber ist also nicht langsam, sondern unbrauchbar - und das
#: faellt erst an der Konsole auf.
GRENZEN: dict[str, int] = {
    "files": 2_000_000,
    "chunks": 16_000_000,
    "packs": 1_024,
}


def uebersicht(manifest: str, melden: Melder = stumm) -> dict[str, Any]:
    """Die Manifestuebersicht als ausgewertete Angaben.

    Das ist die vierte Stufe aus der Anleitung ("Print the manifest
    summary"). Sie ist nicht nur Zierde: Erst hier stehen die **tatsaechlichen**
    Zahlen, gegen die die Bereitschaftsliste des Autors ihre Grenzen prueft -
    die Schaetzung aus der Profilerzeugung gilt danach nicht mehr.
    """
    roh = _lauf(["inspect", "--index", manifest], melden)
    try:
        daten = json.loads(roh or "{}")
    except ValueError as exc:
        raise PackFehler("Uebersicht nicht lesbar: %s" % exc) from exc
    return daten if isinstance(daten, dict) else {}


def grenzen_ueberschritten(uebersicht_daten: dict[str, Any]) -> list[tuple[str, int, int]]:
    """Welche harten Grenzen der Bestand reisst.

    Returns:
        Je Verstoss ``(Name, gemessen, erlaubt)``. Eine leere Liste heisst,
        dass alle drei Zahlen darunter liegen.
    """
    gemessen = {
        "files": int(uebersicht_daten.get("files") or 0),
        "chunks": int(uebersicht_daten.get("chunks") or 0),
        "packs": len(uebersicht_daten.get("packs") or []),
    }
    return [(name, gemessen[name], GRENZEN[name])
            for name in GRENZEN if gemessen[name] > GRENZEN[name]]


def liste(manifest: str, melden: Melder = stumm) -> list[dict[str, Any]]:
    """``list --json``: je Datei des Manifests eine Zeile, gepackt oder lose.

    Ein Punkt der Bereitschaftsliste des Entwicklers (Abschnitt 5): "pack,
    verify --root, inspect, and list --json all finish without errors". Er
    fehlte bis zum 17.09.2026.
    """
    roh = _lauf(["list", "--index", manifest, "--json"], melden)
    try:
        daten = json.loads(roh or "[]")
    except ValueError as exc:
        raise PackFehler("Dateiliste nicht lesbar: %s" % exc) from exc
    return daten if isinstance(daten, list) else []


def lose_fehlend(zeilen: list[dict[str, Any]], app0: str) -> list[str]:
    """Welche als lose gefuehrten Dateien liegen nicht im Spielordner?

    Abschnitt 5 der Anleitung: "loose_paths has been reviewed and every listed
    file remains in /app0". Eine lose Datei, die fehlt, liest die Konsole
    ueber das Dateisystem - und findet dort nichts.

    Returns:
        Die ``/app0``-Pfade der fehlenden Dateien; leer, wenn alle da sind.
    """
    fehlend: list[str] = []
    for zeile in zeilen:
        if not isinstance(zeile, dict) or zeile.get("packed"):
            continue
        pfad = str(zeile.get("path") or "")
        rel = pfad[len("/app0/"):] if pfad.lower().startswith("/app0/") else pfad.lstrip("/")
        if not rel or not os.path.isfile(os.path.join(str(app0), *rel.split("/"))):
            fehlend.append(pfad)
    return fehlend


#: Dateien, die die Systemschicht selbst liest - sie duerfen unter keinen
#: Umstaenden in einem Band landen. Geprueft wird am fertigen Manifest, nicht
#: nur ueber das Profil: Ein eigenes Profil des Anwenders kann die
#: Ausschlussliste :data:`NIE_PACKEN` umgehen, und dann faellt es erst an der
#: Konsole auf - dort aber als Absturz ohne jede Meldung.
#:
#: Gemessen am 20.09.2026 an einem echten Abbild (Ghost of Yotei, gebaut am
#: 18.09.): Das Manifest fuehrte 84.182 von 84.219 Dateien als PACK, darunter
#: cache_ps5/playgo.pgm, cache_ps5/game.sprig.packman und 23
#: pgc_*_dummy_file. Mit "Originale weglassen" wurden sie aus /app0 entfernt.
#: Das Spiel stuerzte danach 0,2 s nach dem Start ab - SIGSEGV auf
#: Adresse 0x20, also ein Nullzeiger, und zwar im Spielcode selbst und mit
#: jeder EMU-Fassung (0.3.6.6 wie 0.4.2.1 nachgemessen). PlayGo liest seine
#: Dateien an der Emulation vorbei; fehlt playgo.pgm, gibt es nichts zu
#: lesen. Alle veroeffentlichten Profile fuehren genau diese Dateien unter
#: "MUST REMAIN LOOSE".
SYSTEMDATEIEN: tuple[str, ...] = (
    "playgo.pgm",
    "playgo-chunk.dat",
    "pgc_*_dummy_file",
    "*.packman",
    # Unity/IL2CPP: an der Konsole gemessen, siehe NIE_PACKEN.
    "global-metadata.dat",
)


def systemdateien_im_pack(zeilen: list[dict[str, Any]]) -> list[str]:
    """Welche Systemdateien stehen im Manifest als PACK?

    Args:
        zeilen: Die Ausgabe von :func:`liste` (``list --json``).

    Returns:
        Die ``/app0``-Pfade der betroffenen Dateien; leer, wenn alles in
        Ordnung ist. Ein nicht leeres Ergebnis heisst: nicht ausliefern.
    """
    import fnmatch

    getroffen: list[str] = []
    for zeile in zeilen:
        if not isinstance(zeile, dict) or not zeile.get("packed"):
            continue
        pfad = str(zeile.get("path") or "")
        name = pfad.replace("\\", "/").rsplit("/", 1)[-1].lower()
        if any(fnmatch.fnmatch(name, muster) for muster in SYSTEMDATEIEN):
            getroffen.append(pfad)
    return getroffen


#: Der interne Speicherblock der Pack-Bauten des AMPR EMU: fest 384 MiB
#: (ASSET_PACKS.md, "Runtime memory defaults"). ``[runtime]`` fordert nur
#: daraus an, es vergroessert ihn nicht.
POOL_BYTES = 384 * 1024 * 1024

#: Was die Laufzeit vor den Caches fest zuruecklegt: 32 Pipeline-Fenster zu
#: je 2 MiB und 32 MiB Sicherheitsreserve - zusammen mit einem MiB je
#: Arbeiter die "100 MiB" aus Abschnitt 8 der Anleitung.
POOL_FEST_BYTES = 32 * 2 * 1024 * 1024 + 32 * 1024 * 1024
POOL_JE_ARBEITER = 1024 * 1024

#: Luft, die frei bleiben muss ("at least another 8-16 MiB of headroom").
#: Genommen wird die obere Grenze: Nachmessen laesst sich das erst an der
#: Konsole, und dort faellt es niemandem auf.
POOL_LUFT = 16 * 1024 * 1024

#: Raster der Cachegroessen ("must be a multiple of 16 KiB").
CACHE_RASTER = 16 * 1024

#: Untergrenze des entpackten Caches, bevor der physische angetastet wird
#: (die einkompilierte Mindestgroesse der Laufzeit).
MIN_ENTPACKT = 16 * 1024 * 1024

#: Laufzeitwerte, wenn keine ``.runtime`` daneben liegt - die einkompilierten
#: Vorgaben aus ASSET_PACKS.md.
LAUFZEIT_VORGABE: dict[str, int] = {
    "decoded_cache_bytes": 128 * 1024 * 1024,
    "physical_cache_bytes": 32 * 1024 * 1024,
    "workers": 4,
    "latency_reserve_workers": 1,
}


def speicherbedarf(manifest_bytes: int, index_bytes: int,
                   laufzeit: dict[str, Any]) -> int:
    """Der Vorab-Haushalt aus Abschnitt 8 der Anleitung, in Bytes.

    ``ampr_assets.index`` + ``ampr_emu.index`` + beide Caches + 32
    Pipeline-Fenster zu 2 MiB + ein MiB je Arbeiter + 32 MiB Reserve. Die
    ``.crc`` zaehlt nicht mit - die Laufzeit laedt sie nie.
    """
    return (int(manifest_bytes) + int(index_bytes)
            + int(laufzeit.get("decoded_cache_bytes") or 0)
            + int(laufzeit.get("physical_cache_bytes") or 0)
            + POOL_FEST_BYTES
            + max(1, int(laufzeit.get("workers") or 1)) * POOL_JE_ARBEITER)


def laufzeit_einpassen(manifest_bytes: int, index_bytes: int,
                       laufzeit: dict[str, Any]) -> dict[str, int] | None:
    """Verkleinert die Caches, bis der Bestand mit Luft in den Block passt.

    Reihenfolge wie in der Anleitung empfohlen ("reduce caches"): erst der
    entpackte Cache bis auf 16 MiB, dann der physische, zuletzt der
    entpackte ganz. Kleine Bloecke zu vergroessern hiesse neu packen - das
    bleibt dem Anwender.

    Returns:
        Die Laufzeitwerte, die passen - unveraendert, wenn nichts zu tun war.
        ``None``, wenn schon Manifest, Index und die festen Anteile den Block
        sprengen; dann hilft kein Cache mehr.
    """
    werte = dict(LAUFZEIT_VORGABE)
    for schluessel in LAUFZEIT_VORGABE:
        if (laufzeit or {}).get(schluessel) is not None:
            werte[schluessel] = int(laufzeit[schluessel])
    frei =(POOL_BYTES - POOL_LUFT - int(manifest_bytes) - int(index_bytes)
            - POOL_FEST_BYTES - max(1, werte["workers"]) * POOL_JE_ARBEITER)
    if frei < 0:
        return None
    zuviel = werte["decoded_cache_bytes"] + werte["physical_cache_bytes"] - frei
    if zuviel <= 0:
        return werte
    for schluessel, untergrenze in (("decoded_cache_bytes", MIN_ENTPACKT),
                                    ("physical_cache_bytes", 0),
                                    ("decoded_cache_bytes", 0)):
        abzug = min(zuviel, max(0, werte[schluessel] - untergrenze))
        werte[schluessel] -= abzug
        zuviel -= abzug
    for schluessel in ("decoded_cache_bytes", "physical_cache_bytes"):
        werte[schluessel] -= werte[schluessel] % CACHE_RASTER
    return werte


def laufzeit_schreiben(manifest: str, laufzeit: dict[str, int],
                       melden: Melder = stumm) -> None:
    """Schreibt ``ampr_assets.index.runtime`` neu - ohne neu zu packen.

    Der Weg aus Abschnitt 8 der Anleitung: ``runtime-config`` bindet die
    Werte an die Build-ID des vorhandenen Manifests. Das Profil dafuer
    enthaelt nur ``[runtime]`` und wird danach wieder entfernt.
    """
    ordner = os.path.dirname(os.path.abspath(manifest))
    profil = os.path.join(ordner, "ampr_pack.runtime-angepasst.toml")
    with open(profil, "w", encoding="utf-8", newline="\n") as datei:
        datei.write("[runtime]\n")
        datei.writelines("%s = %d\n" % (schluessel, int(laufzeit[schluessel]))
                         for schluessel in LAUFZEIT_VORGABE)
    try:
        _lauf(["runtime-config", "--index", manifest, "--config", profil], melden)
    finally:
        try:
            os.remove(profil)
        except OSError as exc:
            logger.debug("Laufzeitprofil nicht entfernbar: %s", exc)


def bandnamen(uebersicht_daten: dict[str, Any]) -> list[str]:
    """Die Namen aller Baender, die das Manifest nennt (aus ``inspect``)."""
    namen: list[str] = []
    for band in uebersicht_daten.get("packs") or []:
        name = str((band or {}).get("name") or "") if isinstance(band, dict) else ""
        if name:
            namen.append(name)
    return namen


def _bestandsdateien(ausgabe_ordner: str, baender: list[str] | None) -> list[str]:
    """Was zum Laufzeitbestand gehoert - relativ zum Ausgabeordner."""
    namen = [MANIFEST_NAME, LAUFZEIT_NAME, PRUEFSUMMEN_NAME]
    if baender is not None:
        return namen + list(baender)
    try:
        return namen + sorted(n for n in os.listdir(ausgabe_ordner)
                              if n.lower().endswith(".pak"))
    except OSError as exc:
        raise PackFehler("Ausgabeordner nicht lesbar: %s" % exc) from exc


def bestand_uebernehmen(ausgabe_ordner: str, app0: str,
                        melden: Melder = stumm,
                        text: Textquelle = schluessel_zeigen,
                        baender: list[str] | None = None) -> int:
    """Legt den Laufzeitbestand vollstaendig in den Spielordner.

    Abschnitt 7 der Anleitung: ``ampr_assets.index``, dessen ``.runtime`` und
    **jedes vom Manifest genannte** Band - als ein Satz mit einer Build-ID.
    Danach wird nachgesehen, ob jede Datei mit ihrer Groesse angekommen ist
    ("verify that every named volume is present").

    Die Pruefsummenbeilage ``.crc`` geht seit dem 17.09.2026 mit. Die
    Laufzeit oeffnet sie nie, laut Anleitung ist sie im ``/app0`` aber
    "harmless and may be convenient for maintenance" - und sie muss beim
    Bestand bleiben, sonst lassen sich die Baender nie wieder pruefen oder
    auspacken. Bis dahin blieb sie im Ausgabeordner zurueck, und der lag
    beim Bau eines Abbilds im Temp-Verzeichnis: Sie war danach verloren.

    Args:
        baender: Die Bandnamen aus dem Manifest (:func:`bandnamen`). Nur sie
            werden uebernommen - ein liegen gebliebenes Band eines frueheren
            Laufs im selben Ordner nicht. Ohne Angabe alle ``.pak``.

    Returns:
        Anzahl der uebernommenen Dateien.

    Raises:
        PackFehler: Wenn ein Teil des Bestands fehlt oder nicht vollstaendig
            ankommt. Ein halber Satz waere schlimmer als keiner.
    """
    # Erst vollstaendig nachsehen, dann kopieren: Fehlt ein Teil, soll im
    # Spielordner gar nichts von diesem Satz landen.
    vorhanden: list[str] = []
    for name in _bestandsdateien(ausgabe_ordner, baender):
        if os.path.isfile(os.path.join(ausgabe_ordner, *name.split("/"))):
            vorhanden.append(name)
        elif name != LAUFZEIT_NAME:
            # Nur die Laufzeitdatei darf fehlen - dann gelten die
            # einkompilierten Vorgaben (Profil ohne [runtime]).
            raise PackFehler("%s fehlt im Ausgabeordner" % name)

    uebernommen = 0
    for name in vorhanden:
        quelle = os.path.join(ausgabe_ordner, *name.split("/"))
        ziel = os.path.join(str(app0), *name.split("/"))
        try:
            os.makedirs(os.path.dirname(ziel), exist_ok=True)
            shutil.copy2(quelle, ziel)
        except OSError as exc:
            raise PackFehler("%s nicht uebernehmbar: %s" % (name, exc)) from exc
        try:
            angekommen = os.path.getsize(ziel) == os.path.getsize(quelle)
        except OSError:
            angekommen = False
        if not angekommen:
            raise PackFehler("%s nicht vollstaendig uebernommen" % name)
        uebernommen += 1

    if uebernommen:
        melden(text("ampr_pack.uebernommen", count=uebernommen))
    return uebernommen


def bestand_aufraeumen(ausgabe_ordner: str, baender: list[str] | None,
                       ganz: bool) -> None:
    """Entfernt den Bestand aus dem Ausgabeordner, nachdem er uebernommen ist.

    Er liegt danach vollstaendig im Spielordner. Blieb er stehen, lag neben
    einem Spielordner, in dem ohne Arbeitskopie gebaut wurde, eine zweite
    Kopie aller Baender - bei einem grossen Spiel viele Gigabyte.

    Args:
        ganz: True entfernt den ganzen Ordner (er enthaelt nur, was dieses
            Programm hineingelegt hat). False entfernt nur den Bestand und
            laesst das eigene Profil des Anwenders stehen.
    """
    if ganz:
        shutil.rmtree(ausgabe_ordner, ignore_errors=True)
        return
    for name in _bestandsdateien(ausgabe_ordner, baender):
        try:
            os.remove(os.path.join(ausgabe_ordner, *name.split("/")))
        except OSError:
            continue


# Frueher stand hier ``pack_entfernen``, der Rueckweg aus Aufgabe 7: Er
# loeschte Manifest, .runtime und Baender in der Annahme, die Originale
# laegen daneben. Seit gepackte Originale beim Erstellen weggelassen werden
# koennen, haette er dabei die Spieldaten geloescht. Aufgabe 7 fasst Asset-
# Packs seit dem 17.09.2026 gar nicht mehr an (Entscheidung des Anwenders).


def quellen_entfernen(manifest: str, app0: str, melden: Melder = stumm,
                      abbruch: Callable[[], bool] | None = None) -> dict[str, Any]:
    """Entfernt die Originale, die jetzt in den Baendern liegen.

    **Unwiderruflich.** Das Werkzeug prueft vorher noch einmal vollstaendig
    und vergleicht jedes Byte; es weigert sich bei Systemdateien und bei
    allem ausserhalb von ``app0``. Trotzdem gilt: Ohne getesteten Lauf auf
    der Konsole gehoert dieser Schritt nicht in einen Automatiklauf - das
    Hauptprogramm fragt deshalb bei jedem Start danach und fuehrt ihn nur in
    einer Arbeitskopie aus, nie im Ordner des Anwenders.

    Returns:
        Die Zusammenfassung des Werkzeugs: ``files``, ``bytes``,
        ``directories``, ``verified``.
    """
    roh = _lauf([
        "remove-packed-sources",
        "--index", manifest,
        "--root", app0,
        "--confirm",
        "--remove-empty-dirs",
    ], melden, abbruch)
    try:
        daten = json.loads(roh or "{}")
    except ValueError as exc:
        raise PackFehler("Zusammenfassung nicht lesbar: %s" % exc) from exc
    return daten if isinstance(daten, dict) else {}
