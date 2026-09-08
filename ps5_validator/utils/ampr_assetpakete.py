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

#: Die Pruefsummenbeilage. Die Konsole liest sie **nie**; sie bleibt beim
#: PC-Bestand, damit ``verify`` und ``unpack`` spaeter noch arbeiten koennen.
PRUEFSUMMEN_NAME = "ampr_assets.index.crc"

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


def standardprofil_text(arbeiter: int = 0) -> str:
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
    ausschluss = "\n".join('  "%s",' % muster for muster in NIE_PACKEN)
    zeilen = [
        "# Vom PS5 Dump & Image Converter erzeugt - Packprofil ohne Mitschnitte.",
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


def profil_schreiben(ziel: str, arbeiter: int = 0) -> str:
    """Legt das Standardprofil ab, wenn dort noch keines liegt.

    Ein vorhandenes Profil bleibt unangetastet: Wer eines aus Mitschnitten
    erzeugt und dorthin gelegt hat, will es benutzt sehen - es beim
    naechsten Lauf zu ueberschreiben waere der teuerste Datenverlust, den
    dieses Modul anrichten koennte.

    Returns:
        Der Pfad des Profils.
    """
    if os.path.isfile(ziel):
        return ziel
    ordner = os.path.dirname(os.path.abspath(ziel))
    if ordner:
        os.makedirs(ordner, exist_ok=True)
    with open(ziel, "w", encoding="utf-8", newline="\n") as datei:
        datei.write(standardprofil_text(arbeiter))
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

    prozess = subprocess.Popen(
        befehl, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
        cwd=os.path.dirname(werkzeug), startupinfo=startinfo,
    )

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
        ausgabe = prozess.stdout.read() if prozess.stdout else ""
    finally:
        prozess.wait()
        for strom in (prozess.stdout, prozess.stderr):
            if strom is not None:
                strom.close()

    if prozess.returncode != 0:
        letzte = fehlerzeilen[-1] if fehlerzeilen else ""
        raise PackFehler(letzte or "Rueckgabewert %d" % prozess.returncode)
    return ausgabe


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


def bestand_uebernehmen(ausgabe_ordner: str, app0: str,
                        melden: Melder = stumm,
                        text: Textquelle = schluessel_zeigen) -> int:
    """Legt Manifest, Laufzeitdatei und alle Baender in den Spielordner.

    Die Pruefsummenbeilage bleibt bewusst zurueck: Die Konsole oeffnet sie
    nie, und im Abbild kostet sie nur Platz. Sie bleibt im Ausgabeordner,
    wo ``verify`` sie spaeter noch findet.

    Returns:
        Anzahl der uebernommenen Dateien.
    """
    uebernommen = 0
    try:
        namen = sorted(os.listdir(ausgabe_ordner))
    except OSError as exc:
        raise PackFehler("Ausgabeordner nicht lesbar: %s" % exc) from exc

    for name in namen:
        klein = name.lower()
        if klein == PRUEFSUMMEN_NAME:
            continue
        if klein not in (MANIFEST_NAME, LAUFZEIT_NAME) and not klein.endswith(".pak"):
            continue
        quelle = os.path.join(ausgabe_ordner, name)
        if not os.path.isfile(quelle):
            continue
        try:
            shutil.copy2(quelle, os.path.join(app0, name))
            uebernommen += 1
        except OSError as exc:
            raise PackFehler("%s nicht uebernehmbar: %s" % (name, exc)) from exc

    if uebernommen:
        melden(text("ampr_pack.uebernommen", count=uebernommen))
    return uebernommen


def quellen_entfernen(manifest: str, app0: str, melden: Melder = stumm,
                      abbruch: Callable[[], bool] | None = None) -> None:
    """Entfernt die Originale, die jetzt in den Baendern liegen.

    **Unwiderruflich.** Das Werkzeug prueft vorher noch einmal vollstaendig
    und vergleicht jedes Byte; es weigert sich bei Systemdateien und bei
    allem ausserhalb von ``app0``. Trotzdem gilt: Ohne getesteten Lauf auf
    der Konsole gehoert dieser Schritt nicht in einen Automatiklauf.
    """
    _lauf([
        "remove-packed-sources",
        "--index", manifest,
        "--root", app0,
        "--confirm",
        "--remove-empty-dirs",
    ], melden, abbruch)
