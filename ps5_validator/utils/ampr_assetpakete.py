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
from ps5_validator.utils.prozess_beenden import baum_beenden
from ps5_validator.utils.werkzeuge_bereitstellen import suchwurzeln

logger = logging.getLogger("PS5Converter.utils.ampr_assetpakete")

#: Der mitgelieferte Werkzeugordner. Enthaelt ``ampr_pack.py`` samt
#: Formatmodul - beide muessen nebeneinander liegen, sonst findet der
#: Import des Werkzeugs sein ``ampr_pack_format`` nicht.
PACKWERKZEUG_ORDNER = "AMPR_PackTools-4.0"

#: Mitgelieferte Spielprofile (aus danthespal/MkPFS.CSharp, GPL-3.0).
#: Vier erprobte Titel: ASTRO BOT, UFC 6, Insomniac-Engine, Unity-Engine.
#: Liegt neben dem Werkzeugordner, relativ zu dieser Datei berechnet.
PROFIL_ORDNER: str = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", PACKWERKZEUG_ORDNER, "profiles")
)

#: Das Werkzeug selbst.
PACKWERKZEUG = "ampr_pack.py"

#: Liegt im selben Ordner: erzeugt aus Mitschnitten (``ampr_commands.bin`` +
#: ``ampr_emu.index``) ein maszgeschneidertes TOML-Profil statt des
#: vorsichtigen Standardprofils - siehe :func:`profil_generieren`.
PACKPROFIL_WERKZEUG = "ampr_pack_profile.py"

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

#: LZ4-Stufe der Baender: 1 bis 12 wie bei LZ4 Compression und Lazy_AMPR.
#: 1 bis 4 laufen im schnellen Modus, 5 bis 12 mit LZ4 HC; 9 ist die Vorgabe.
#:
#: Gemessen am 15.10.2026 (python-lz4 4.4.5, 64-KiB-Bloecke, Stichproben von
#: Dumps): Stufe 12 spart gegenueber 9 nur 0,0 bis 0,6 Prozentpunkte, ist aber
#: 1,2- bis 3,6-mal langsamer (Mafia, pakchunk0: 52,6 -> 52,3 % bei 31 -> 9
#: MB/s je Kern). Bis v1.9.80 stand die Stufe fest auf 12. Die Stufe aendert
#: nur Groesse und Packzeit, nicht das Format - jede Stufe liest die
#: Laufzeit gleich.
LZ4_STUFE_VORGABE = 9
LZ4_STUFE_MIN = 1
LZ4_STUFE_MAX = 12
LZ4_STUFE_SCHNELL_BIS = 4


def lz4_stufe_lesen(wert: Any) -> int:
    """Eine gespeicherte oder uebergebene LZ4-Stufe als Zahl von 1 bis 12.

    Alles Unbrauchbare (Text, Wahrheitswert, Zahl ausserhalb) wird zur
    Vorgabe - eine kaputte Einstellung darf den Bau nicht anhalten.
    """
    if isinstance(wert, bool):
        return LZ4_STUFE_VORGABE
    try:
        stufe = int(wert)
    except (TypeError, ValueError):
        return LZ4_STUFE_VORGABE
    if not LZ4_STUFE_MIN <= stufe <= LZ4_STUFE_MAX:
        return LZ4_STUFE_VORGABE
    return stufe


def kompression_zeilen(stufe: Any) -> tuple[str, ...]:
    """Die drei TOML-Zeilen, die ``ampr_pack.py`` fuer die Stufe liest.

    Im schnellen Modus bleibt ``acceleration = 1`` (so rechnet auch LZ4
    Compression); die Stufe 1 bis 4 ist dort also dasselbe.
    """
    stufe = lz4_stufe_lesen(stufe)
    modus = "fast" if stufe <= LZ4_STUFE_SCHNELL_BIS else "hc"
    return ('compression_mode = "%s"' % modus,
            "compression_level = %d" % stufe,
            "acceleration = 1")


_KOMPRESSIONSSCHLUESSEL = re.compile(
    r"^\s*(compression_mode|compression_level|acceleration)\s*=")


def profil_stufe_einsetzen(text: str, stufe: Any) -> str:
    """Setzt die gewaehlte Stufe in ein Profil dieses Programms ein.

    Gedacht fuer die mitgelieferten Spielprofile: Zwei tragen
    ``compression_level = 12`` selbst, zwei gar keine Angabe (dann gilt 12
    im Werkzeug). LZ4 Compression wendet die gewaehlte Stufe ebenfalls auf
    jedes Profil an. Ein Profil des Anwenders fasst das Programm nie an
    (:func:`profil_schreiben`).

    Nur Zeilen in der Tabelle ``[pack]`` werden ersetzt; ein Profil ohne diese
    Tabelle bekommt sie am Ende angehaengt.
    """
    ergebnis: list[str] = []
    in_pack = False
    eingesetzt = False
    for zeile in text.splitlines():
        kopf = zeile.split("#", 1)[0].strip()
        if kopf.startswith("["):
            in_pack = kopf == "[pack]"
            ergebnis.append(zeile)
            if in_pack and not eingesetzt:
                ergebnis.extend(kompression_zeilen(stufe))
                eingesetzt = True
            continue
        if in_pack and _KOMPRESSIONSSCHLUESSEL.match(zeile):
            continue
        ergebnis.append(zeile)
    if not eingesetzt:
        ergebnis.append("")
        ergebnis.append("[pack]")
        ergebnis.extend(kompression_zeilen(stufe))
    return "\n".join(ergebnis) + "\n"

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
    # --- Aus LZ4 Compression 1.5.0 nachgetragen (15.10.2026) ---------------
    # LZ4 Compression (Husam Osman, GPL-3.0) haelt diese Dateien per
    # k_keep_on_disk[] lose: das Programm laedt sie ausserhalb des
    # Spielprozesses, wo der AMPR EMU den Zugriff nicht abfangen kann.
    # Fehlende Muster wurden am 15.10.2026 mit einem Testbaum gemessen:
    # Alle unten stehenden Eintraege landeten im Band, obwohl sie lose sein
    # muessen. Quelle: ampr_pack.c, Kommentar "Ghost of Yotei needs to get
    # past a black screen (found by a Reddit user, confirmed on PPSA26344
    # 02.002.000)".
    # .texmeshman: Shader-Metadaten (all_shaders, game.sprig, pulse.sprig).
    # Die Endung ist stabil - jedes Spiel, das diese Dateien erzeugt, legt
    # sie unter cache_ps5/ mit dieser Endung ab.
    "*.texmeshman", "**/*.texmeshman",
    # Der Lademenue-Katalog wird beim Hochfahren des Spiels gelesen, bevor
    # der Emulator hochgefahren ist. Die Datei liegt unter cache_ps5/ -
    # ``**/load_menu_catalog.log`` deckt sie dort ab; ``load_menu_catalog.log``
    # deckt die Wurzelebene von app0 ab (tritt in der Praxis nicht auf, ist
    # aber gemaess der Doppelform-Konvention noetig, s. NIE_PACKEN-Kopfkommentar).
    "load_menu_catalog.log", "**/load_menu_catalog.log",
    # Scream-Audio-Laufzeitdaten: drei feste Dateien unter sounds/scream/
    # _generated/. Die Endungen decken .bus (Bus-Konfiguration), .dml
    # (Distanzmodell) und .gmx (Gruppenmischung) pauschal ab, damit ein
    # kuenftiges Spiel mit einer vierten Scream-Datei nicht bricht.
    "sounds/scream/_generated/*.bus", "**/sounds/scream/_generated/*.bus",
    "sounds/scream/_generated/*.dml", "**/sounds/scream/_generated/*.dml",
    "sounds/scream/_generated/*.gmx", "**/sounds/scream/_generated/*.gmx",
    # Leere Dateien (Groesse 0) laedt LZ4 Compression ebenfalls immer lose
    # (if(size == 0) return 1) - die Sprachplatzhalter von Ghost of Yotei
    # prueft die PS5 ausserhalb des Spiels (Schwarzbild, Version 1.4.3 des
    # Werkzeugs). Das Python-Werkzeug packt sie; ohne "Originale weglassen"
    # bleiben sie ohnehin als Datei liegen, mit dem Weglassen schreibt
    # :func:`leere_dateien_zurueckschreiben` sie danach wieder hin.
    # Spielplatzhalter (pgc_*_dummy_file) sind oben per Muster abgedeckt.
)

#: Dateiendungen, die das **Standardprofil** lose laesst: schon verdichtete
#: Medien, Bilder, Texturen und Archive (LZ4 bringt dort fast nichts), dazu
#: Konfigdateien, die das Spiel oder das System auch ausserhalb des AMPR EMU
#: liest. Die Liste folgt ``k_safety_exclusions`` aus LZ4 Compression 1.5.0
#: (``ampr_pack_profile.c``), das sie fuer jedes Profil erzwingt.
#:
#: Hier gilt sie **nur** fuer das Standardprofil dieses Programms. Die
#: mitgelieferten Spielprofile sind an der Konsole erprobt und bleiben, wie sie
#: sind; ein Profil des Anwenders fasst das Programm nie an.
#:
#: Gemessen am 15.10.2026 (Metadaten echter Dumps): Ghost of Yotei 4,8 GB
#: (3,2 %, alles ``.at9``), Teardown 0,74 GB (18,8 %), Dirt 5 6,1 GB (6,5 %),
#: Mafia, Street Fighter 6 und Matchbox rund 0 %. Ueber alle 37 Dumps des
#: Entwicklungsrechners (1620 GB) tragen diese Endungen 384 GB (24 %), vor allem
#: ``zip`` (Forza Horizon 5, 131 GB), ``gnfp``/``jxm``/``7z`` (ASTRO BOT, hat ein
#: eigenes Profil und ist davon nicht betroffen), ``bk2``, ``mp4``, ``webm``,
#: ``wem`` und ``at9`` - durchweg verdichtete Daten.
#:
#: Die Muster stehen **ohne** ``**/``-Doppel: ``fnmatch.fnmatchcase`` laesst
#: ``*`` auch ``/`` treffen, ``*.png`` trifft also ``a/b/c.png`` ebenso wie
#: ``c.png`` (``test_ampr_assetpakete.LoseListeTests``). Schreibweisen mit
#: Grossbuchstaben liefert :func:`lose_endungen_muster` aus dem Ordnerbaum.
#: **``dat`` fehlt hier absichtlich**, obwohl LZ4 Compression ``*.dat`` lose laesst:
#: Ueber alle Dumps des Entwicklungsrechners sind es 283 Dateien und 0,19 GB von
#: 1620 GB - der Gewinn ist null, die Aenderung gegenueber dem erprobten
#: Verhalten (Asterix & Obelix, Arcade Game Zone) nicht. Die ``.dat`` der
#: Systemschicht (``nptitle.dat``, ``playgo-chunk.dat``, ``global-metadata.dat``)
#: stehen einzeln in :data:`NIE_PACKEN` bzw. :data:`SYSTEMDATEIEN`.
LOSE_ENDUNGEN: tuple[str, ...] = (
    # Konfiguration und Sicherungen
    "json", "ini", "cfg", "xml", "txt", "bak", "utoc",
    # Bilder und Texturen
    "png", "jpg", "jpeg", "webp", "gif", "bmp", "ico", "tga", "tif", "tiff",
    "exr", "hdr", "psd", "dds", "ktx", "ktx2", "astc", "basis", "gnf",
    "gnfp", "jxm", "vtf",
    # Archive und Abbilder
    "zip", "7z", "rar", "gz", "xz", "bz2", "zst", "lz4", "pfs", "img",
    # Audio und Video (die Konsole spielt sie ueber eigene Dekoder)
    "mp3", "ogg", "flac", "aac", "opus", "m4a", "at9", "wem", "bnk",
    "bk2", "mp4", "ivf", "usm", "avi", "mkv", "mov", "wmv", "flv", "webm",
    "m4v",
)

#: Ordner, die das Standardprofil ebenfalls lose laesst (Entschluesseltes,
#: Duplex-Dateien, Trophaeen, Nutzungsdaten) - wie ``k_safety_exclusions``.
LOSE_ORDNER: tuple[str, ...] = ("decrypted", "_DUPLEX_", "trophy2", "uds")

#: Die fertigen Ausschlussmuster fuer das Standardprofil.
LOSE_MUSTER: tuple[str, ...] = (
    tuple("*.%s" % endung for endung in LOSE_ENDUNGEN)
    + tuple(muster for ordner in LOSE_ORDNER
            for muster in ("%s/**" % ordner, "**/%s/**" % ordner))
)


class PackFehler(RuntimeError):
    """Der Packlauf ist gescheitert - mit einer Zeile, die das erklaert."""


def werkzeug_finden(name: str = PACKWERKZEUG) -> str:
    """Sucht ein Werkzeug aus :data:`PACKWERKZEUG_ORDNER` (Vorgabe ``ampr_pack.py``).

    Args:
        name: Dateiname im Werkzeugordner, z. B. :data:`PACKPROFIL_WERKZEUG`.

    Returns:
        Der volle Pfad - oder eine leere Zeichenkette, wenn der
        Werkzeugordner fehlt. Ein fehlendes Werkzeug ist kein Fehler
        dieses Moduls, sondern eine Aussage ueber den Bestand; der
        Aufrufer entscheidet, ob er die neue Methode dann anbietet.
    """
    for wurzel in suchwurzeln():
        kandidat = os.path.join(wurzel, PACKWERKZEUG_ORDNER, name)
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
                        zusatz_ausschluss: "tuple[str, ...]" = (),
                        stufe: Any = LZ4_STUFE_VORGABE) -> str:
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
    * Medien, Bilder, Archive und Konfigdateien (:data:`LOSE_MUSTER`) bleiben
      lose - schon verdichtet oder von der Systemschicht gelesen.

    Args:
        arbeiter: Anzahl der Packvorgaenge auf dem PC. 0 laesst das
            Werkzeug selbst waehlen.
        stufe: LZ4-Stufe 1 bis 12 (:data:`LZ4_STUFE_VORGABE` = 9).
    """
    # Die festen Muster plus die Filmordner dieses Spiels. Letztere kommen
    # aus dem Ordnerbaum, weil das Werkzeug die Schreibung genau nimmt.
    ausschluss = "\n".join('  "%s",' % muster
                           for muster in (*NIE_PACKEN, *LOSE_MUSTER,
                                          *zusatz_ausschluss))
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
        *kompression_zeilen(stufe),
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


def lose_endungen_muster(app0: str) -> tuple[str, ...]:
    """Ausschlussmuster fuer Schreibweisen von :data:`LOSE_ENDUNGEN` in **diesem** Spiel.

    Das Werkzeug vergleicht mit ``fnmatch.fnmatchcase``, also nach Schreibung:
    ``*.png`` trifft ``Logo.PNG`` nicht. :data:`LOSE_MUSTER` kennt nur die
    kleine Schreibung; hier kommen die Schreibweisen dazu, die im Ordnerbaum
    wirklich vorkommen (``*.PNG``, ``*.Dds``).

    Gelesen wird mit ``os.scandir`` - die Dateinamen genuegen, kein ``stat``
    ausser dem, das der Eintrag ohnehin mitbringt.

    Returns:
        Muster wie ``"*.PNG"`` - nur fuer Schreibweisen ungleich der kleinen.
    """
    bekannt = set(LOSE_ENDUNGEN)
    gefunden: set[str] = set()
    stapel = [str(app0)]
    while stapel:
        ordner = stapel.pop()
        try:
            with os.scandir(ordner) as eintraege:
                for eintrag in eintraege:
                    try:
                        if eintrag.is_dir(follow_symlinks=False):
                            stapel.append(eintrag.path)
                            continue
                    except OSError:
                        continue
                    endung = os.path.splitext(eintrag.name)[1][1:]
                    if endung and endung != endung.lower() \
                            and endung.lower() in bekannt:
                        gefunden.add("*.%s" % endung)
        except OSError as exc:
            logger.debug("Endungen nicht suchbar (%s): %s", ordner, exc)
    return tuple(sorted(gefunden))


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

#: Mitgelieferte Profile (aus danthespal/MkPFS.CSharp, GPL-3.0).
#: Schluessel: Title-ID (PPSA-Format) oder Engine-Name aus DIREKTLESER.
#: Die Insomniac-Engine wird nicht ueber DIREKTLESER erkannt (die Markerdateien
#: ``dag``/``toc`` sind zu generisch), sondern direkt in
#: :func:`profil_integriert_fuer` geprueft.
MITGELIEFERTE_PROFILE: dict[str, str] = {
    "PPSA21567": "astrobot.toml",        # ASTRO BOT (01.019.000, getestet)
    "PPSA23566": "ufc6-PPSA23566.toml",  # EA Sports UFC 6 (01.004.000, getestet)
    "Unity":     "unity.toml",           # Unity-Engine (getestet an PPSA28997)
    "Insomniac": "insomniac.toml",       # Insomniac-Engine (getestet an PPSA03671)
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


def profil_ordner() -> str:
    """Der Ordner mit den mitgelieferten Profilen.

    Gesucht wird wie beim Packwerkzeug ueber :func:`werkzeugordner_finden`
    (gebaute Fassungen legen die Datenordner nicht dort ab, wo der Quelltext
    liegt - unter macOS etwa nach ``Contents/Resources``). Erst wenn das
    Werkzeug nicht gefunden wird, gilt der Pfad relativ zu dieser Datei.
    """
    werkzeug = werkzeugordner_finden()
    if werkzeug:
        kandidat = os.path.join(werkzeug, "profiles")
        if os.path.isdir(kandidat):
            return kandidat
    return PROFIL_ORDNER


def title_id_aus_sfo(app0: str) -> str:
    """Liest die TITLE_ID aus ``sce_sys/param.sfo`` - oder gibt '' zurueck.

    Nur lesend, nie werfend. Format: Big-Endian-Magic + Tabelleneintraege -
    gleicher Aufbau wie in ``ps4pkg_bibliothek.sfo_lesen``.
    """
    import struct as _struct
    pfad = os.path.join(str(app0 or ""), "sce_sys", "param.sfo")
    try:
        with open(pfad, "rb") as dat:
            roh = dat.read()
    except OSError:
        return ""
    if len(roh) < 0x14 or roh[:4] != b"\x00PSF":
        return ""
    try:
        schl_start, dat_start, anzahl = _struct.unpack_from("<III", roh, 0x08)
        for i in range(min(anzahl, 512)):
            schl_off, _fmt, laenge, _max, dat_off = _struct.unpack_from(
                "<HHIII", roh, 0x14 + i * 16)
            ende = roh.find(b"\x00", schl_start + schl_off)
            if ende < 0:
                continue
            name = roh[schl_start + schl_off:ende].decode("ascii", "replace")
            if name == "TITLE_ID":
                return (roh[dat_start + dat_off:dat_start + dat_off + laenge]
                        .split(b"\x00", 1)[0].decode("utf-8", "replace"))
    except (_struct.error, IndexError):
        pass
    return ""


def _erkennt_insomniac(app0: str) -> bool:
    """Typische Insomniac-Titelstruktur: ``dag``, ``toc`` und ``d/`` in app0.

    ``dag`` und ``toc`` als Dateinamen in Unterordnern sind zu generisch fuer
    :data:`DIREKTLESER` (Frostbite hat ebenfalls viele ``.toc``-Dateien).
    Erst alle drei zusammen an der Wurzel von app0 sind Insomniac-typisch.
    """
    try:
        return (os.path.isfile(os.path.join(str(app0), "dag")) and
                os.path.isfile(os.path.join(str(app0), "toc")) and
                os.path.isdir(os.path.join(str(app0), "d")))
    except OSError:
        return False


def profil_integriert_fuer(app0: str) -> tuple[str, str]:
    """Welches mitgelieferte Profil passt zu diesem Spielordner?

    Prueft der Reihe nach:
    1. Genaues Title-ID-Profil aus ``sce_sys/param.sfo``.
    2. Engine-Profil aus :func:`direktleser_merkmale` (derzeit: Unity).
    3. Insomniac-Engine anhand der typischen Ordnerstruktur.

    Returns:
        ``(Bezeichnung, vollstaendiger Pfad)`` oder ``("", "")``.
    """
    if not app0:
        return "", ""
    # 1. Title-ID (genaues Profil hat Vorrang vor allgemeinem Engine-Profil)
    title_id = title_id_aus_sfo(app0)
    if title_id:
        dateiname = MITGELIEFERTE_PROFILE.get(title_id, "")
        if dateiname:
            pfad = os.path.join(profil_ordner(), dateiname)
            if os.path.isfile(pfad):
                return title_id, pfad
    # 2. Engine-Erkennung (Unity)
    engine, _ = direktleser_merkmale(app0)
    if engine:
        dateiname = MITGELIEFERTE_PROFILE.get(engine, "")
        if dateiname:
            pfad = os.path.join(profil_ordner(), dateiname)
            if os.path.isfile(pfad):
                return engine, pfad
    # 3. Insomniac anhand Ordnerstruktur (nicht ueber DIREKTLESER)
    if _erkennt_insomniac(app0):
        dateiname = MITGELIEFERTE_PROFILE.get("Insomniac", "")
        if dateiname:
            pfad = os.path.join(profil_ordner(), dateiname)
            if os.path.isfile(pfad):
                return "Insomniac", pfad
    return "", ""


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


def profil_schreiben(ziel: str, arbeiter: int = 0, app0: str = "",
                     stufe: Any = LZ4_STUFE_VORGABE) -> str:
    """Legt das Packprofil ab - ein eigenes des Anwenders bleibt.

    Reihenfolge:
    1. Existiert eine Datei, die NICHT von diesem Programm stammt?
       → Benutzerdefiniertes Profil, unveraendert zurueckgeben.
    2. Ergibt :func:`profil_integriert_fuer` ein Ergebnis?
       → Mitgeliefertes Spielprofil schreiben (PROFIL_KENNZEILE vorangestellt),
       mit der gewaehlten LZ4-Stufe (:func:`profil_stufe_einsetzen`).
    3. Fallback: Standardprofil erzeugen und schreiben.

    Ein Profil dieses Programms (Schritt 2 und 3) wird **jedes Mal neu**
    geschrieben, damit Aenderungen an den Profilen oder der Ausschlussliste
    beim naechsten Lauf wirksam werden.

    Args:
        stufe: LZ4-Stufe 1 bis 12 (:data:`LZ4_STUFE_VORGABE` = 9).

    Returns:
        Der Pfad des Profils.
    """
    if os.path.isfile(ziel) and not profil_ist_eigenes(ziel):
        return ziel
    ordner = os.path.dirname(os.path.abspath(ziel))
    if ordner:
        os.makedirs(ordner, exist_ok=True)
    # Mitgeliefertes Profil (Title-ID oder Engine-Erkennung)?
    bezeichnung, quell_pfad = profil_integriert_fuer(app0)
    if quell_pfad:
        try:
            with open(quell_pfad, "r", encoding="utf-8") as quelle:
                inhalt = quelle.read()
            with open(ziel, "w", encoding="utf-8", newline="\n") as datei:
                datei.write(
                    PROFIL_KENNZEILE + " - integriertes Profil fuer "
                    + bezeichnung + ".\n")
                datei.write(profil_stufe_einsetzen(inhalt, stufe))
            logger.debug("integriertes Profil fuer %s: %s", bezeichnung, ziel)
            return ziel
        except OSError as exc:
            logger.warning("integriertes Profil nicht lesbar (%s): %s",
                           quell_pfad, exc)
    # Fallback: Standardprofil (vorsichtig, unbekannte Daten)
    with open(ziel, "w", encoding="utf-8", newline="\n") as datei:
        zusatz = ((*filmordner_muster(app0), *systemdateien_muster(app0),
                   *lose_endungen_muster(app0))
                  if app0 else ())
        datei.write(standardprofil_text(arbeiter, zusatz, stufe))
    return ziel


#: Interner Schalter, mit dem sich die fertige Programmdatei selbst als
#: Packwerkzeug aufruft. Behandelt wird er ganz vorn in ``main`` (siehe dort
#: ``_run_ampr_pack_subcommand``), noch vor der Rechtepruefung.
SELBSTAUFRUF = "--ampr-pack"

#: Derselbe Selbstaufruf-Trick fuer :data:`PACKPROFIL_WERKZEUG` (siehe dort
#: ``_run_ampr_pack_profil_subcommand``).
PACKPROFIL_SELBSTAUFRUF = "--ampr-pack-profil"


def _python_ruf(skript: str = PACKWERKZEUG,
                selbstaufruf: str = SELBSTAUFRUF) -> list[str]:
    """Womit ``skript`` gestartet wird - samt Weg zum Werkzeug.

    **Die fertige Programmdatei ruft sich selbst auf.** ``sys.executable`` ist
    dort das Programm und kein Python; mit dem Schalter ``selbstaufruf``
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
        return [sys.executable, selbstaufruf]
    werkzeug = werkzeug_finden(skript)
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
          fortschritt: Callable[[float, str], None] | None = None, *,
          skript: str = PACKWERKZEUG,
          selbstaufruf: str = SELBSTAUFRUF) -> str:
    """Startet das Werkzeug und reicht seine Ausgabe durch.

    Standardmaessig ``ampr_pack.py``; :func:`profil_generieren` ruft
    dieselbe Maschine mit ``skript=PACKPROFIL_WERKZEUG`` fuer
    ``ampr_pack_profile.py`` auf - beide liegen im selben Werkzeugordner.

    ``ampr_pack.py`` schreibt den Fortschritt auf ``stderr`` und haelt
    ``stdout`` fuer das abschliessende JSON frei. Beides wird getrennt
    gelesen, damit die JSON-Zeile nicht zwischen Fortschrittszeilen
    verlorengeht. ``ampr_pack_profile.py`` schreibt keine ``[pack NN%]``-
    Zeilen - jede stderr-Zeile geht dort einfach ins Protokoll
    (:func:`fortschritt_lesen` findet dann nie ein Muster).
    """
    werkzeug = werkzeug_finden(skript)
    if not werkzeug:
        raise PackFehler("ampr_pack.werkzeug_fehlt")

    # _python_ruf bringt den Weg zum Werkzeug schon mit: In der fertigen
    # Programmdatei ist das der Selbstaufruf, sonst der Pfad der .py-Datei.
    befehl = _python_ruf(skript, selbstaufruf) + argumente
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
                    baum_beenden(prozess)      # samt Nachkommen: Die EXE ruft sich selbst auf (Starter + Programm)
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
                baum_beenden(prozess)
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


def profil_generieren(traces: "list[tuple[str, str]]", ausgabe: str, *,
                      bericht: str = "", metriken: str = "", name: str = "",
                      overwrite: bool = True, melden: Melder = stumm,
                      abbruch: Callable[[], bool] | None = None) -> str:
    """Erzeugt aus Mitschnitten ein massgeschneidertes TOML-Profil.

    Ruft :data:`PACKPROFIL_WERKZEUG` (``ampr_pack_profile.py generate``) mit
    einem ``--trace``-Paar je aufgenommenem Lauf auf - derselbe Aufruf, den
    das Handbuch des Herstellers fuer die eigene GUI beschreibt
    (``AMPR_PackTools-4.0/USER_GUIDE_EN.md``, Abschnitt 3), hier ohne dessen
    Tk-Oberflaeche.

    Args:
        traces: ``(ampr_commands.bin, ampr_emu.index)`` je Lauf, in der
            Reihenfolge, in der sie aufgenommen wurden.
        ausgabe: Zielpfad der ``.toml``. Ohne ``overwrite`` bricht das
            Werkzeug ab, wenn die Datei schon existiert (``ProfileError:
            refusing to overwrite existing file``) - der Aufrufer soll das
            vorher selbst entscheiden, nicht diese Funktion.
        bericht: optionaler Pfad fuer den lesbaren Bericht (``--report``).
        metriken: optionaler Pfad fuer die Eingabedaten als JSON (``--metrics``).

    Raises:
        PackFehler: Werkzeug fehlt, kein Mitschnitt uebergeben, oder das
            Werkzeug selbst meldet einen Fehler (z. B. ein beschaedigter
            Mitschnitt).
    """
    if not traces:
        raise PackFehler("amprmitschnitt.keine_laeufe")
    argumente = ["generate", "--output", ausgabe]
    for commands, index in traces:
        argumente += ["--trace", commands, index]
    if name:
        argumente += ["--name", name]
    if bericht:
        argumente += ["--report", bericht]
    if metriken:
        argumente += ["--metrics", metriken]
    if overwrite:
        argumente.append("--overwrite")
    return _lauf(argumente, melden, abbruch,
                skript=PACKPROFIL_WERKZEUG, selbstaufruf=PACKPROFIL_SELBSTAUFRUF)


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


#: Blockgroesse beim Uebernehmen der Baender - zwischen zwei Bloecken wird
#: nach dem Abbruch gefragt (siehe :func:`bestand_uebernehmen`).
_UEBERNAHME_BLOCK = 8 * 1024 * 1024


def _kopieren_mit_abbruch(quelle: str, ziel: str,
                          abbruch: Callable[[], bool] | None) -> None:
    """Wie ``shutil.copy2`` - aber zwischen zwei Bloecken abbrechbar.

    Ein Band ist bis zu 8 GiB gross; ``copy2`` liesse sich dazwischen nicht
    anhalten. Die Zeitstempel kommen wie bei ``copy2`` ueber ``copystat``.
    """
    with open(quelle, "rb") as q, open(ziel, "wb") as z:
        while True:
            if abbruch is not None and abbruch():
                raise PackFehler("ampr_pack.abgebrochen")
            block = q.read(_UEBERNAHME_BLOCK)
            if not block:
                break
            z.write(block)
    shutil.copystat(quelle, ziel)


def bestand_uebernehmen(ausgabe_ordner: str, app0: str,
                        melden: Melder = stumm,
                        text: Textquelle = schluessel_zeigen,
                        baender: list[str] | None = None,
                        abbruch: Callable[[], bool] | None = None) -> int:
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
        abbruch: Wird waehrend des Kopierens alle 8 MiB gefragt. Bis zur
            Durchsicht (Runde 19, U2-5) gab es ihn nicht, anders als bei
            :func:`packen` und :func:`pruefen`: "Abbrechen" wirkte erst nach
            dem letzten Band, bei einem grossen Spiel nach Dutzenden GB.
            Abgebrochen wird nur beim Kopieren unter Zwischennamen - das
            Umbenennen danach laeuft durch, sonst laege ein halber Satz da.

    Returns:
        Anzahl der uebernommenen Dateien.

    Raises:
        PackFehler: Wenn ein Teil des Bestands fehlt oder nicht vollstaendig
            ankommt. Ein halber Satz waere schlimmer als keiner. Beim
            Abbruch mit dem Schluessel ``ampr_pack.abgebrochen``; die
            Zwischenstaende sind dann entfernt, ein frueherer Satz steht
            unberuehrt da.
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

    # Erst alles unter Zwischennamen kopieren und nachmessen, dann umbenennen.
    # Bis zum 24.09.2026 ging jede Datei sofort an ihren Platz: Scheiterte
    # das dritte von zehn Baendern (voller Datentraeger), lagen Manifest und
    # zwei Baender im Spielordner - ein halber Satz, den die Laufzeit liest
    # und an den fehlenden Baendern zerbricht (Durchsicht, U2-1). Ein
    # vorhandener frueherer Satz bleibt so bis zum Schluss unberuehrt.
    kopiert: list[tuple[str, str]] = []
    try:
        for name in vorhanden:
            quelle = os.path.join(ausgabe_ordner, *name.split("/"))
            ziel = os.path.join(str(app0), *name.split("/"))
            zwischen = ziel + ".uebernahme"
            # Vor dem Kopieren vormerken: Bricht copy2 mittendrin ab, liegt
            # schon ein halber Zwischenstand, und den raeumt das finally weg.
            kopiert.append((zwischen, ziel))
            try:
                os.makedirs(os.path.dirname(ziel), exist_ok=True)
                _kopieren_mit_abbruch(quelle, zwischen, abbruch)
            except OSError as exc:
                raise PackFehler("%s nicht uebernehmbar: %s" % (name, exc)) from exc
            try:
                angekommen = os.path.getsize(zwischen) == os.path.getsize(quelle)
            except OSError:
                angekommen = False
            if not angekommen:
                raise PackFehler("%s nicht vollstaendig uebernommen" % name)
        for zwischen, ziel in kopiert:
            try:
                os.replace(zwischen, ziel)
            except OSError as exc:
                raise PackFehler("%s nicht uebernehmbar: %s"
                                 % (os.path.basename(ziel), exc)) from exc
    finally:
        for zwischen, _ziel in kopiert:
            try:
                if os.path.exists(zwischen):
                    os.remove(zwischen)
            except OSError:
                pass
    uebernommen = len(kopiert)

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


def _rel_aus_zeile(zeile: dict[str, Any]) -> str:
    """Der Pfad einer ``list --json``-Zeile relativ zum Spielordner (mit ``/``)."""
    pfad = str(zeile.get("path") or "").replace("\\", "/")
    if pfad.lower().startswith("/app0/"):
        return pfad[len("/app0/"):]
    return pfad.lstrip("/")


def _innerhalb(wurzel: str, rel: str) -> str:
    """Der volle Pfad zu ``rel`` unter ``wurzel`` - oder "" bei Ausbruch.

    Ein Pfad aus einem fremden Manifest mit ``..`` oder einem Laufwerk darf nie
    ausserhalb des Spielordners schreiben.
    """
    teile = [t for t in rel.split("/") if t]
    if not teile or any(t in (".", "..") or ":" in t for t in teile):
        return ""
    voll = os.path.normpath(os.path.join(str(wurzel), *teile))
    basis = os.path.normpath(str(wurzel))
    try:
        if os.path.commonpath([voll, basis]) != basis:
            return ""
    except ValueError:
        # Verschiedene Laufwerke (Windows) - sicher draussen.
        return ""
    return voll


def leere_dateien_zurueckschreiben(zeilen: list[dict[str, Any]], app0: str,
                                   melden: Melder = stumm,
                                   text: Textquelle = schluessel_zeigen) -> int:
    """Legt gepackte Dateien der Groesse 0 nach dem Entfernen der Originale wieder hin.

    LZ4 Compression haelt leere Dateien immer lose: Die Sprachplatzhalter von
    Ghost of Yotei prueft die PS5 ausserhalb des Spiels, und fehlen sie, steht
    das Spiel auf einem schwarzen Bild (Werkzeug 1.4.3, 14.10.2026). Das
    Python-Werkzeug packt sie, und ``remove-packed-sources`` loescht sie dann
    mit den uebrigen Originalen. Eine leere Datei hat keine Nutzdaten, die man
    sichern muesste - sie wird einfach wieder angelegt.

    Args:
        zeilen: Die Ausgabe von :func:`liste`, **vor** dem Entfernen gelesen.

    Returns:
        Anzahl der neu angelegten Dateien.
    """
    angelegt = 0
    for zeile in zeilen:
        if not isinstance(zeile, dict) or not zeile.get("packed"):
            continue
        try:
            if int(zeile.get("logical_size") or 0) != 0:
                continue
        except (TypeError, ValueError):
            continue
        ziel = _innerhalb(app0, _rel_aus_zeile(zeile))
        if not ziel or os.path.exists(ziel):
            continue
        try:
            os.makedirs(os.path.dirname(ziel), exist_ok=True)
            with open(ziel, "wb"):
                pass
        except OSError as exc:
            logger.debug("Leere Datei nicht anlegbar (%s): %s", ziel, exc)
            continue
        angelegt += 1
    if angelegt:
        melden(text("ampr_pack.leere_zurueck", count=angelegt))
    return angelegt


# ---------------------------------------------------------------------------
# Fertige Asset-Pack-Ordner: ansehen, pruefen, entpacken
# ---------------------------------------------------------------------------
# Bis v1.9.79 konnte das Programm Baender nur bauen. ``ampr_pack.py`` bringt
# ``verify`` und ``unpack`` mit; LZ4 Compression (Konsole) bietet beides als
# "Verify LZ4 Packs" und "Uncompress LZ4" an. Hier die PC-Seite dazu.


def manifest_im_ordner(ordner: str) -> str:
    """Pfad des Manifests im Spielordner - oder "" ohne Asset-Pack."""
    pfad = os.path.join(str(ordner or ""), MANIFEST_NAME)
    return pfad if os.path.isfile(pfad) else ""


def ordner_befund(ordner: str, melden: Melder = stumm) -> dict[str, Any]:
    """Was ein fertiger Asset-Pack-Ordner enthaelt - ohne einen Block zu lesen.

    Liest nur das Manifest (``inspect`` und ``list --json``) und sieht im Ordner
    nach. Das dauert Sekunden, auch bei 80.000 Dateien.

    Returns:
        Ein Woerterbuch mit ``dateien``, ``gepackt``, ``lose``,
        ``gepackt_bytes`` (logische Groesse), ``gesamt_bytes``, ``band_bytes``
        (auf der Platte), ``baender``, ``baender_fehlen``, ``crc_da``,
        ``fehlende_gepackte`` und ``fehlende_gepackte_bytes`` (gepackte Dateien,
        die nicht mehr lose im Ordner liegen), ``lose_fehlend`` und
        ``systemdateien`` (siehe :func:`lose_fehlend`,
        :func:`systemdateien_im_pack`), ``uebersicht`` (die Ausgabe von
        ``inspect``).

    Raises:
        PackFehler: ``ampr_pack.kein_manifest``, wenn kein Manifest da ist.
    """
    manifest = manifest_im_ordner(ordner)
    if not manifest:
        raise PackFehler("ampr_pack.kein_manifest")
    daten = uebersicht(manifest, melden)
    zeilen = liste(manifest, melden)
    baender = bandnamen(daten)
    gepackt = [z for z in zeilen if isinstance(z, dict) and z.get("packed")]
    fehlende = 0
    fehlende_bytes = 0
    for zeile in gepackt:
        ziel = _innerhalb(ordner, _rel_aus_zeile(zeile))
        if ziel and not os.path.isfile(ziel):
            fehlende += 1
            fehlende_bytes += int(zeile.get("logical_size") or 0)
    band_bytes = 0
    baender_fehlen: list[str] = []
    for name in baender:
        try:
            band_bytes += os.path.getsize(os.path.join(str(ordner), name))
        except OSError:
            baender_fehlen.append(name)
    return {
        "uebersicht": daten,
        "dateien": len(zeilen),
        "gepackt": len(gepackt),
        "lose": len(zeilen) - len(gepackt),
        "gepackt_bytes": sum(int(z.get("logical_size") or 0) for z in gepackt),
        "gesamt_bytes": sum(int(z.get("logical_size") or 0)
                            for z in zeilen if isinstance(z, dict)),
        "band_bytes": band_bytes,
        "baender": baender,
        "baender_fehlen": baender_fehlen,
        "crc_da": os.path.isfile(manifest + ".crc"),
        "fehlende_gepackte": fehlende,
        "fehlende_gepackte_bytes": fehlende_bytes,
        "lose_fehlend": lose_fehlend(zeilen, str(ordner)),
        "systemdateien": systemdateien_im_pack(zeilen),
    }


def ordner_pruefen(ordner: str, melden: Melder = stumm,
                   abbruch: Callable[[], bool] | None = None) -> dict[str, Any]:
    """Liest jeden Block eines fertigen Ordners und haelt ihn gegen die ``.crc``.

    Wie ``verify`` der Anleitung, aber ohne ``--root``: In einem fertigen Spiel
    sind die Originale oft weg, dann gibt es nichts zu vergleichen - die
    Pruefsummenbeilage ist der Massstab.

    Returns:
        ``files``, ``physical_chunks``, ``stored_bytes``, ``raw_bytes``.

    Raises:
        PackFehler: ``ampr_pack.kein_manifest``, ``ampr_pack.crc_fehlt`` oder
            die Meldung des Werkzeugs (beschaedigtes Band, falsche Groesse).
    """
    manifest = manifest_im_ordner(ordner)
    if not manifest:
        raise PackFehler("ampr_pack.kein_manifest")
    if not os.path.isfile(manifest + ".crc"):
        raise PackFehler("ampr_pack.crc_fehlt")
    roh = _lauf(["verify", "--index", manifest], melden, abbruch)
    try:
        daten = json.loads(roh or "{}")
    except ValueError as exc:
        raise PackFehler("Pruefergebnis nicht lesbar: %s" % exc) from exc
    return daten if isinstance(daten, dict) else {}


def entpack_platzbedarf(befund: dict[str, Any], in_ordner: bool) -> int:
    """Wie viel freier Platz das Entpacken mindestens braucht (Bytes).

    * In den eigenen Ordner: nur, was dort noch fehlt - liegen die Originale
      noch daneben, ist das wenig.
    * In einen neuen Ordner: das ganze Spiel.

    Ein Viertel GiB Luft kommt dazu (Zwischendateien, Zeitstempel).
    """
    luft = 256 * 1024 * 1024
    if in_ordner:
        return int(befund.get("fehlende_gepackte_bytes") or 0) + luft
    return int(befund.get("gesamt_bytes") or 0) + luft


def _dateien_scannen(wurzel: str):
    """Alle Dateien und Ordner unter ``wurzel`` als ``(rel, absolut, ist_ordner)``.

    Mit ``os.scandir`` und ohne Rekursion, ohne Verknuepfungen zu folgen.
    """
    stapel = [""]
    while stapel:
        rel_ordner = stapel.pop()
        voll = os.path.join(wurzel, rel_ordner) if rel_ordner else wurzel
        try:
            with os.scandir(voll) as eintraege:
                for eintrag in eintraege:
                    rel = (rel_ordner + "/" + eintrag.name) if rel_ordner else eintrag.name
                    try:
                        ist_ordner = eintrag.is_dir(follow_symlinks=False)
                    except OSError:
                        continue
                    if ist_ordner:
                        stapel.append(rel)
                    yield rel, eintrag.path, ist_ordner
        except OSError as exc:
            logger.debug("Ordner nicht lesbar (%s): %s", voll, exc)


def entpacken_in_ordner(ordner: str, melden: Melder = stumm,
                        text: Textquelle = schluessel_zeigen,
                        abbruch: Callable[[], bool] | None = None) -> dict[str, Any]:
    """Legt alle gepackten Dateien in den Spielordner und entfernt dann die Baender.

    Wie ``Uncompress LZ4`` in place. Reihenfolge ist Absicht: erst auspacken
    (``unpack --overwrite``, je Datei atomar ueber einen Zwischennamen), dann
    ein zweiter Blick auf den Befund, **erst danach** Manifest, ``.runtime``,
    ``.crc`` und Baender loeschen. Bricht etwas ab, liegt noch der ganze Satz da
    und der Lauf laesst sich wiederholen.

    ``ampr_emu.index`` und die Bibliotheken in ``fakelib`` bleiben unberuehrt.

    Returns:
        ``files``, ``bytes`` (ausgepackt), ``entfernt`` (geloeschte Dateien des
        Bestands).

    Raises:
        PackFehler: kein Manifest, fehlende Baender, Abbruch oder ein Fehler des
            Werkzeugs.
    """
    manifest = manifest_im_ordner(ordner)
    if not manifest:
        raise PackFehler("ampr_pack.kein_manifest")
    daten = uebersicht(manifest, melden)
    baender = bandnamen(daten)
    fehlend = [n for n in baender
               if not os.path.isfile(os.path.join(str(ordner), n))]
    if fehlend:
        raise PackFehler("ampr_pack.baender_fehlen")
    roh = _lauf(["unpack", "--index", manifest, "--output", str(ordner),
                 "--overwrite"], melden, abbruch)
    try:
        ergebnis = json.loads(roh or "{}")
    except ValueError as exc:
        raise PackFehler("Entpackergebnis nicht lesbar: %s" % exc) from exc
    if not isinstance(ergebnis, dict):
        ergebnis = {}
    erwartet = int(daten.get("packed_files") or 0)
    # Nur ein Vergleich, der etwas aussagt: Ohne gepackte Dateien gibt es
    # nichts auszupacken, und ein anderes Ergebnis waere ein Rueckstand.
    if erwartet and int(ergebnis.get("files") or 0) != erwartet:
        raise PackFehler("ampr_pack.entpacken_unvollstaendig")
    entfernt = 0
    for name in _bestandsdateien(str(ordner), baender):
        pfad = os.path.join(str(ordner), *name.split("/"))
        try:
            os.remove(pfad)
            entfernt += 1
        except FileNotFoundError:
            continue
        except OSError as exc:
            logger.warning("Bestandsdatei nicht entfernbar (%s): %s", pfad, exc)
            melden(text("ampr_pack.bestand_bleibt", name=name))
    ergebnis["entfernt"] = entfernt
    return ergebnis


def entpacken_in_neuen_ordner(ordner: str, ziel: str, melden: Melder = stumm,
                              text: Textquelle = schluessel_zeigen,
                              abbruch: Callable[[], bool] | None = None
                              ) -> dict[str, Any]:
    """Baut aus einem gepackten Spielordner einen losen in einem **neuen** Ordner.

    Wie ``Uncompress LZ4`` in einen neuen Ordner: Alles, was nicht zum
    Packbestand gehoert und nicht im Band steht (Systemordner, Bibliotheken,
    lose gefuehrte Dateien), wird kopiert; die gepackten Dateien kommen aus den
    Baendern. Der Quellordner bleibt unveraendert. Liegen die Originale dort noch
    daneben, werden sie **nicht** kopiert - die Baender sind die Quelle, so
    entsteht das, was die Konsole gesehen haette.

    Args:
        ziel: Ein Ordner, den es nicht gibt oder der leer ist.

    Returns:
        ``files`` und ``bytes`` (aus den Baendern), ``kopiert`` (Dateien).

    Raises:
        PackFehler: ``ampr_pack.ziel_nicht_leer``, ``ampr_pack.ziel_im_quellordner``,
            kein Manifest, Abbruch oder ein Fehler des Werkzeugs. Ein von diesem
            Aufruf angelegter Zielordner wird bei jedem Fehler wieder entfernt.
    """
    manifest = manifest_im_ordner(ordner)
    if not manifest:
        raise PackFehler("ampr_pack.kein_manifest")
    quelle = os.path.normcase(os.path.abspath(str(ordner)))
    ziel_abs = os.path.normcase(os.path.abspath(str(ziel)))
    if ziel_abs == quelle or ziel_abs.startswith(quelle + os.sep):
        raise PackFehler("ampr_pack.ziel_im_quellordner")
    ziel_war_da = os.path.isdir(ziel)
    if ziel_war_da and os.listdir(ziel):
        raise PackFehler("ampr_pack.ziel_nicht_leer")

    daten = uebersicht(manifest, melden)
    baender = bandnamen(daten)
    zeilen = liste(manifest, melden)
    gepackt = {_rel_aus_zeile(z).lower() for z in zeilen
               if isinstance(z, dict) and z.get("packed")}
    bestand = {n.lower() for n in _bestandsdateien(str(ordner), baender)}

    kopiert = 0
    try:
        os.makedirs(ziel, exist_ok=True)
        for rel, voll, ist_ordner in _dateien_scannen(str(ordner)):
            if abbruch is not None and abbruch():
                raise PackFehler("ampr_pack.abgebrochen")
            if ist_ordner:
                ziel_ordner = _innerhalb(ziel, rel)
                if ziel_ordner:
                    os.makedirs(ziel_ordner, exist_ok=True)
                continue
            kleinrel = rel.lower()
            if kleinrel in gepackt or kleinrel in bestand:
                continue
            ziel_datei = _innerhalb(ziel, rel)
            if not ziel_datei:
                continue
            os.makedirs(os.path.dirname(ziel_datei), exist_ok=True)
            try:
                _kopieren_mit_abbruch(voll, ziel_datei, abbruch)
            except OSError as exc:
                raise PackFehler("%s nicht kopierbar: %s" % (rel, exc)) from exc
            kopiert += 1
            if kopiert % 500 == 0:
                melden(text("ampr_pack.entpacken_kopiert", count=kopiert))
        melden(text("ampr_pack.entpacken_kopiert", count=kopiert))
        roh = _lauf(["unpack", "--index", manifest, "--output", str(ziel),
                     "--overwrite"], melden, abbruch)
        try:
            ergebnis = json.loads(roh or "{}")
        except ValueError as exc:
            raise PackFehler("Entpackergebnis nicht lesbar: %s" % exc) from exc
        if not isinstance(ergebnis, dict):
            ergebnis = {}
        erwartet = int(daten.get("packed_files") or 0)
        if erwartet and int(ergebnis.get("files") or 0) != erwartet:
            raise PackFehler("ampr_pack.entpacken_unvollstaendig")
    except BaseException:
        # Auch bei Abbruch (KeyboardInterrupt) nichts Halbes zuruecklassen.
        # Ein Ordner, den es vorher nicht gab, geht ganz; ein leerer, den der
        # Anwender angegeben hat, wird wieder geleert (er war leer, sonst waere
        # es oben schon abgelehnt worden).
        if not ziel_war_da:
            shutil.rmtree(ziel, ignore_errors=True)
        else:
            try:
                for name in os.listdir(ziel):
                    pfad = os.path.join(ziel, name)
                    if os.path.isdir(pfad) and not os.path.islink(pfad):
                        shutil.rmtree(pfad, ignore_errors=True)
                    else:
                        os.remove(pfad)
            except OSError as exc:
                logger.debug("Zielordner nicht leerbar (%s): %s", ziel, exc)
        raise
    ergebnis["kopiert"] = kopiert
    return ergebnis
