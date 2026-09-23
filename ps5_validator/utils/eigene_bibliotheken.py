# -*- coding: utf-8 -*-
"""Eigene Bibliotheken aus dem Ordner ``libs`` vorziehen.

Gedacht fuer den Fall, dass eine selbst geschriebene Fassung von
``LibProsperoPkg.dll`` oder ``libScePubTools.dll`` das mitgelieferte
Werkzeug ersetzen soll: Datei in den Ordner ``libs`` legen - fertig. Das
Programm findet sie beim naechsten Bau von selbst.

**Warum nicht einfach die Datei im Werkzeugordner ueberschreiben?** Weil
die mitgelieferte ``LibProsperoPkg.dll`` git-verfolgt ist. Ein
Ueberschreiben wuerde das Projekt verschmutzen, die Werkzeugpruefung
brechen und waere nur von Hand rueckgaengig zu machen. Stattdessen
entsteht eine **Arbeitskopie** des Werkzeugordners, in der die eigene
Bibliothek liegt; gestartet wird aus der Kopie. Das Original bleibt
unberuehrt, und wer die Datei aus ``libs`` wieder herausnimmt, bekommt
beim naechsten Lauf ohne weiteres Zutun wieder das mitgelieferte Werkzeug.

**Dateinamen.** Eine .NET-Assembly heisst auf jeder Plattform ``.dll`` -
auch unter Linux und macOS. Eine native Bibliothek dagegen traegt dort
``.so`` bzw. ``.dylib``. Deshalb kennt dieses Modul beide Faelle; die
Windows-Schreibweise wird ueberall zusaetzlich akzeptiert, weil sie die
ist, die einem zuerst einfaellt.

Nur Standardbibliothek.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys

logger = logging.getLogger("PS5Converter.eigene_bibliotheken")

#: Der Ordner neben dem Programm, in den die eigenen Dateien gehoeren.
ORDNER = "libs"

#: Name der Arbeitskopie im Arbeitsordner.
KOPIE_NAME = "prosperopkg_eigen"

#: Merkzettel in der Kopie: was daraus stammt und mit welcher Pruefsumme.
MERKZETTEL = ".eigene_bibliotheken.json"

#: Fassung des Merkzettels. **Wird sie erhoeht, gilt jede aeltere Kopie als
#: veraltet und wird neu gespiegelt und geprueft.**
#:
#: Am 23.09.2026 gemessen, warum das noetig ist: Eine Arbeitskopie aus einem
#: frueheren Lauf - angelegt, bevor es den Selbsttest gab - trug einen
#: Merkzettel, der zu den Pruefsummen passte. Also wurde weder neu gespiegelt
#: noch geprueft, und die unpassende Bibliothek war weiter in Benutzung. Zwei
#: echte Tests scheiterten daran, in einem Einstellungsordner, den niemand
#: mehr auf dem Schirm hatte.
MERKZETTEL_FASSUNG = 2

#: Managed .NET-Assemblys - ueberall ``.dll``.
VERWALTETE = ("LibProsperoPkg.dll",)

#: Native Bibliotheken je Plattform. Die ``.dll``-Schreibweise wird
#: ueberall mitgenommen, damit niemand ratlos vor dem Ordner steht.
NATIVE = {
    "win32": ("libScePubTools.dll",),
    "linux": ("libScePubTools.so", "libScePubTools.dll"),
    "darwin": ("libScePubTools.dylib", "libScePubTools.dll"),
}

#: Dateien, die zu einer Assembly gehoeren, aber allein nichts bewirken:
#: die Symboldatei und die XML-Doku. Sie werden **mitgenommen, wenn die
#: zugehoerige Assembly da ist** - allein ausgelegt bleiben sie liegen.
#: Ohne die ``.pdb`` nennt .NET in einem Absturzbericht keine Zeilennummern;
#: wer eine eigene Bibliothek baut, will genau die sehen.
BEGLEITER = {
    "LibProsperoPkg.dll": ("LibProsperoPkg.pdb", "LibProsperoPkg.xml"),
}

#: Unterordner in ``libs``, die das Programm **nicht** benutzt, aber im
#: Bericht nennt - sonst wundert sich jemand, warum sein dort abgelegter
#: SDK-Baukasten nichts bewirkt. Ein eigener Bauweg ueber
#: ``prospero-pub-cmd.exe`` waere ein anderes Programm, kein Tausch einer
#: Bibliothek (Stand 23.09.2026: nicht gebaut).
NICHT_BENUTZTE_ORDNER = ("sdk",)


def bekannte_namen() -> "tuple[str, ...]":
    """Welche Dateinamen dieser Ordner fuer diese Plattform beachtet."""
    return tuple(VERWALTETE) + tuple(NATIVE.get(sys.platform,
                                                ("libScePubTools.dll",)))


def _suchwurzeln() -> "list[str]":
    """Wo der Ordner ``libs`` liegen kann.

    Wie in ``prosperopkg``, mit **einer** Erweiterung fuer macOS: Dort
    steckt die Programmdatei in ``<Programm>.app/Contents/MacOS``. Ein
    ``libs`` daneben laege im Buendel - und ``Contents/Resources``, wohin
    mitgelieferte Datenordner sonst gehoeren, ist beim Signieren
    **versiegelt**: Wer dort eine Datei ablegt, macht das Buendel ungueltig
    ("a sealed resource is missing or invalid"), und auf Apple Silicon
    startet es dann gar nicht mehr (am 25.08.2026 im CI erlebt). Der Ordner
    fuer **eigene** Bibliotheken gehoert deshalb **neben die .app**.
    """
    wurzeln = [getattr(sys, "_MEIPASS", "")]
    neben = ""
    try:
        neben = os.path.dirname(os.path.abspath(sys.argv[0]))
        wurzeln.append(neben)
    except Exception:  # noqa: BLE001
        pass
    if (sys.platform == "darwin" and neben
            and os.path.basename(neben) == "MacOS"):
        # .../Programm.app/Contents/MacOS -> der Ordner, in dem die .app liegt
        wurzeln.append(os.path.dirname(os.path.dirname(
            os.path.dirname(neben))))
    wurzeln.append(os.getcwd())
    wurzeln.append(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    return [w for w in wurzeln if w]


def ordner_finden() -> str:
    """Der Pfad des ``libs``-Ordners - leer, wenn es ihn nicht gibt."""
    for wurzel in _suchwurzeln():
        pfad = os.path.join(wurzel, ORDNER)
        if os.path.isdir(pfad):
            return pfad
    return ""


def gefundene(ordner: str = "") -> "dict[str, str]":
    """Welche eigenen Bibliotheken liegen bereit?

    Gesucht wird nur in der **obersten Ebene** von ``libs``. Unterordner
    wie ``sdk`` bleiben unberuehrt - sie tragen ganze Werkzeugketten, die
    dieses Programm nicht startet (:data:`NICHT_BENUTZTE_ORDNER`).

    Returns:
        ``{Dateiname: Pfad}``. Leere Dateien zaehlen nicht - eine
        0-Byte-Datei ist ein Versehen, kein Ersatz. Begleitdateien
        (``.pdb``, ``.xml``) kommen nur mit, wenn ihre Assembly da ist.
    """
    wurzel = ordner or ordner_finden()
    if not wurzel or not os.path.isdir(wurzel):
        return {}

    def _brauchbar(name: str) -> str:
        pfad = os.path.join(wurzel, name)
        try:
            if os.path.isfile(pfad) and os.path.getsize(pfad) > 0:
                return pfad
        except OSError:
            pass
        return ""

    treffer: "dict[str, str]" = {}
    for name in bekannte_namen():
        pfad = _brauchbar(name)
        if not pfad:
            continue
        treffer[name] = pfad
        for begleiter in BEGLEITER.get(name, ()):
            neben = _brauchbar(begleiter)
            if neben:
                treffer[begleiter] = neben
    return treffer


def unbenutzte_ordner(ordner: str = "") -> "list[str]":
    """Welche Unterordner liegen da, ohne dass sie etwas bewirken?

    Damit ein dort abgelegter SDK-Baukasten im Diagnosebericht auftaucht
    und niemand auf seine Wirkung wartet.
    """
    wurzel = ordner or ordner_finden()
    if not wurzel or not os.path.isdir(wurzel):
        return []
    return [name for name in NICHT_BENUTZTE_ORDNER
            if os.path.isdir(os.path.join(wurzel, name))]


def pruefsumme(pfad: str) -> str:
    """SHA-256 einer Datei - kurz gehalten fuer Anzeige und Vergleich."""
    haschisch = hashlib.sha256()
    try:
        with open(pfad, "rb") as datei:
            for brocken in iter(lambda: datei.read(1024 * 1024), b""):
                haschisch.update(brocken)
    except OSError:
        return ""
    return haschisch.hexdigest()


def einsatzordner(werkzeugordner: str, arbeitsordner: str,
                  ordner: str = "") -> str:
    """Aus welchem Ordner soll ``prosperopkg`` gestartet werden?

    Liegt in ``libs`` nichts, bleibt es beim mitgelieferten Werkzeug - der
    Normalfall kostet dann keine einzige Kopie.

    Args:
        werkzeugordner: Der Ordner mit dem mitgelieferten ``prosperopkg``.
        arbeitsordner: Wohin die Arbeitskopie darf (Einstellungsordner).
        ordner: Nur fuer Tests - der ``libs``-Ordner.

    Returns:
        Den Ordner, aus dem gestartet werden soll.
    """
    eigene = gefundene(ordner)
    if not eigene or not werkzeugordner or not os.path.isdir(werkzeugordner):
        return werkzeugordner

    kopie = os.path.join(arbeitsordner, KOPIE_NAME)
    soll = {name: pruefsumme(pfad) for name, pfad in sorted(eigene.items())}
    soll["_fassung"] = MERKZETTEL_FASSUNG
    merkzettel = os.path.join(kopie, MERKZETTEL)
    try:
        with open(merkzettel, "r", encoding="utf-8") as datei:
            ist = json.load(datei)
    except (OSError, ValueError):
        ist = None

    # Verglichen werden nur die Pruefsummen; ``_untauglich`` ist ein Merker
    # und darf kein erneutes Spiegeln ausloesen (sonst liefe der Selbsttest
    # vor jedem Bau).
    gemerkt = ({name: wert for name, wert in ist.items()
                if not name.startswith("_") or name == "_fassung"}
               if isinstance(ist, dict) else None)
    if gemerkt != soll or not os.path.isdir(kopie):
        logger.info("Eigene Bibliotheken werden eingesetzt: %s",
                    ", ".join(sorted(eigene)))
        # Frisch spiegeln: Eine alte Kopie koennte eine Bibliothek tragen,
        # die inzwischen aus libs verschwunden ist.
        shutil.rmtree(kopie, ignore_errors=True)
        os.makedirs(kopie, exist_ok=True)
        shutil.copytree(werkzeugordner, kopie, dirs_exist_ok=True)
        for name, pfad in eigene.items():
            shutil.copy2(pfad, os.path.join(kopie, name))
        taugt, grund = kopie_taugt(kopie)
        if not taugt:
            # Lieber das mitgelieferte Werkzeug als ein totes: Eine
            # unpassende Bibliothek legt sonst jeden Bau lahm, und der
            # Anwender saehe nur einen .NET-Ladefehler.
            logger.warning("Eigene Bibliothek passt nicht zur Huelle "
                           "(%s) - es bleibt beim mitgelieferten Werkzeug.",
                           grund)
            soll["_untauglich"] = grund
        try:
            with open(merkzettel, "w", encoding="utf-8") as datei:
                json.dump(soll, datei, indent=2, sort_keys=True)
        except OSError as fehler:
            logger.warning("Merkzettel nicht schreibbar: %s", fehler)
        if not taugt:
            return werkzeugordner

    # Auch beim zweiten Lauf: Was einmal als untauglich erkannt wurde,
    # wird nicht stillschweigend doch benutzt.
    if isinstance(ist, dict) and ist.get("_untauglich"):
        return werkzeugordner

    if sys.platform != "win32":
        # Das Ausfuehrungsrecht ueberlebt das Kopieren nicht immer.
        for name in os.listdir(kopie):
            pfad = os.path.join(kopie, name)
            if os.path.isfile(pfad) and not name.endswith(
                    (".json", ".xml", ".dll")):
                try:
                    os.chmod(pfad, os.stat(pfad).st_mode | 0o111)
                except OSError:
                    pass
    return kopie


#: Woran im Ausgabetext zu erkennen ist, dass .NET die Bibliothek nicht
#: laedt. Am 23.09.2026 gemessen: Eine LibProsperoPkg **1.2.0.0** (fuer
#: .NET 9) im Ordner liess ``prosperopkg`` mit genau dieser Meldung
#: abbrechen - unsere Huelle ist gegen 2.6.0.0 gebunden. Ohne diese
#: Pruefung wuerde eine unpassende Datei den ganzen PKG-Weg lahmlegen,
#: und der Anwender saehe nur einen .NET-Fehler.
LADEFEHLER = ("Could not load file or assembly",
              "FileNotFoundException",
              "FileLoadException")


#: Der Prüfgriff: ``read`` auf eine Datei, die es nicht gibt.
#:
#: **Warum nicht einfach das Programm ohne Argumente starten?** Weil .NET
#: eine Assembly erst laedt, wenn sie gebraucht wird. Ohne Argumente
#: druckt ``prosperopkg`` seine Hilfe und fasst LibProsperoPkg nie an -
#: am 23.09.2026 gemessen: Der Selbsttest meldete "taugt", und der naechste
#: echte Aufruf scheiterte trotzdem am Ladefehler. ``read`` zwingt das
#: Laden; dass die Datei fehlt, faellt erst danach auf.
SELBSTTEST = ("read", "--source", "__kein_paket_selbsttest__.pkg")


def kopie_taugt(ordner: str, programm: str = "prosperopkg.exe",
                zeit: float = 60.0) -> "tuple[bool, str]":
    """Ruft das Werkzeug einmal so auf, dass es die Bibliothek laden muss.

    Der Aufruf kostet unter einer Sekunde und faellt nur an, wenn frisch
    gespiegelt wurde. Er beantwortet die einzige Frage, die sich sonst
    erst beim naechsten Bau stellt - und dann als roher .NET-Fehler:
    Passt die eigene Bibliothek zu dieser Huelle?

    Returns:
        ``(taugt, grund)``. ``grund`` ist die Zeile, die es verraten hat.
    """
    pfad = os.path.join(ordner, programm)
    if not os.path.isfile(pfad):
        return False, "%s fehlt in der Arbeitskopie" % programm
    anlauf: dict = {"capture_output": True, "text": True,
                    "encoding": "utf-8", "errors": "replace",
                    "cwd": ordner, "timeout": float(zeit)}
    if sys.platform == "win32":
        anlauf["creationflags"] = 0x08000000   # CREATE_NO_WINDOW
    try:
        lauf = subprocess.run([pfad, *SELBSTTEST], **anlauf)
    except (OSError, subprocess.SubprocessError) as fehler:
        # Laesst sich das Programm gar nicht starten, ist das **nicht** der
        # Befund, um den es hier geht. Die Huelle stammt aus dem eigenen
        # Ordner; startet sie nicht, liegt es an etwas anderem
        # (Virenwaechter, fremde Architektur) - und das mitgelieferte
        # Werkzeug haette dasselbe Problem. Hier wird nur geurteilt, was
        # sich wirklich messen laesst: die Ladbarkeit der Bibliothek.
        logger.warning("Selbsttest nicht durchfuehrbar (%s) - die Kopie "
                       "wird trotzdem benutzt.", fehler)
        return True, ""
    text = "%s\n%s" % (lauf.stdout or "", lauf.stderr or "")
    for merkmal in LADEFEHLER:
        if merkmal in text:
            zeile = next((z.strip() for z in text.splitlines()
                          if merkmal in z), merkmal)
            return False, zeile
    return True, ""


def letzter_befund(arbeitsordner: str = "") -> str:
    """Wurde die eigene Bibliothek zuletzt als untauglich erkannt?

    Liest den Merkzettel der Arbeitskopie. Leer heisst: kein Befund - die
    Bibliothek wird benutzt, oder es gibt gar keine.
    """
    if not arbeitsordner:
        try:
            from ps5_validator.utils.einstellungen import konfigurationsordner
            arbeitsordner = konfigurationsordner()
        except Exception:  # noqa: BLE001
            return ""
    try:
        with open(os.path.join(arbeitsordner, KOPIE_NAME, MERKZETTEL),
                  "r", encoding="utf-8") as datei:
            return str(json.load(datei).get("_untauglich", "") or "")
    except (OSError, ValueError):
        return ""


def stand(ordner: str = "") -> "list[dict]":
    """Was liegt in ``libs`` - fuer den Diagnosebericht.

    Returns:
        Je Datei ein Eintrag mit ``name``, ``pfad``, ``bytes`` und
        ``sha256``. Leere Liste heisst: Es wird das mitgelieferte
        Werkzeug benutzt.
    """
    eintraege: "list[dict]" = []
    for name, pfad in sorted(gefundene(ordner).items()):
        try:
            groesse = os.path.getsize(pfad)
        except OSError:
            groesse = 0
        eintraege.append({"name": name, "pfad": pfad, "bytes": groesse,
                          "sha256": pruefsumme(pfad)})
    return eintraege
