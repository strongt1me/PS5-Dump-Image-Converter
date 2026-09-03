# -*- coding: utf-8 -*-
"""Stellt die mitgelieferten Werkzeuge bereit: die MkPFS-Engine und UFS2Tool.

Sechster Schnitt der Trennung. Diese Funktionen lagen als
``_extract_embedded_mkpfs`` und ``_extract_ufs2tool`` samt zwei statischen
Helfern im Tk-Monolithen. Sie sind der meistgerufene Block, der bisher
herausgeloest wurde: **18 Aufrufstellen** - elf fuer die Engine, sieben
fuer UFS2Tool.

**Warum gerade dieser Schnitt.** Beide Nachbarbloecke zeigten auf ihn.
Die Ablauflogik (``_execute_mkpfs``) braucht die Engine als Vorbedingung,
und die Metadatenleser brauchen UFS2Tool - solange beides an einer
Tk-Klasse hing, hing es auch dort.

**Die Programmwurzel - der Fallstrick dieses Umzugs.** Im Monolithen bildete
der Quelltext seine Suchwurzel mit ``os.path.dirname(os.path.abspath(
__file__))``. Aus ``ps5_validator/utils/`` heraus zeigt ``__file__`` nicht
mehr auf das Projektverzeichnis. Der Fehler waere fast sicher **nicht**
aufgefallen: ``os.getcwd()`` steht in derselben Kandidatenliste, also
findet ein Start aus dem Projektordner alles weiterhin. Erst ein Start von
woanders liefert einen leeren Pfad zurueck - ohne Ausnahme, ohne
Protokollzeile. Deshalb :func:`suchwurzeln`, das ``__file__`` drei Ebenen
hochklappt; dieselbe Bauart wie in
:func:`ps5_validator.utils.prosperopkg._suchwurzeln` und
:func:`ps5_validator.utils.app_install.payload_finden`.

**Was bewusst draussen bleibt.** ``_mitgeliefert_finden`` wandert **nicht**
mit: Die Methode kennt eine macOS-Regel, die hier niemand nachbaut - ein
signiertes ``.app``-Buendel versiegelt ``Contents/MacOS`` nicht, Datenordner
gehoeren nach ``Contents/Resources``, und genau das hat am 25.08.2026 einen
CI-Lauf zu Fall gebracht. Sie wird als ``wurzel_finden`` hereingereicht.
Ebenso bleibt ``_get_runtime_temp_dir`` im Monolithen - es liest eine
Tk-Variable; hier kommt der fertige Ordner als Parameter herein.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import platform
import re
import sys
from typing import Callable
from zipfile import ZipFile

from ps5_validator.utils.nahtstellen import (Melder, Textquelle,
                                             schluessel_zeigen, stumm)
from ps5_validator.utils.plattform import (IST_LINUX, IST_MACOS, IST_WINDOWS,
                                           systemname)

logger = logging.getLogger("PS5Converter.utils.werkzeuge_bereitstellen")

#: Die MkPFS-Fassung, die dieses Programm voraussetzt.
MKPFS_ERFORDERLICHE_FASSUNG = "1.0.0"

#: Der Ordner der mitgelieferten UFS2Tool-Baeume. Stand bis zum 30.08.2026
#: zweimal wortgleich im Monolithen (Zeilen 39787 und 39795).
UFS2TOOL_ORDNER = "UFS2Tool-4.1"


def suchwurzeln() -> list[str]:
    """Die Stellen, an denen mitgelieferte Dateien liegen koennen.

    Reihenfolge wie in ``PS5ConverterGUI._mitgeliefert_finden``: im
    entpackten Buendel, neben der Programmdatei, im Arbeitsverzeichnis -
    und zuletzt drei Ebenen ueber dieser Datei, also im Projektstamm.

    Der letzte Eintrag ist der, den der Umzug noetig gemacht hat: Ohne ihn
    faende ein Start ausserhalb des Projektordners nichts mehr.
    """
    wurzeln: list[str] = []
    gebuendelt = getattr(sys, "_MEIPASS", "")
    if gebuendelt:
        wurzeln.append(str(gebuendelt))
    if getattr(sys, "frozen", False):
        wurzeln.append(os.path.dirname(os.path.abspath(sys.executable)))
    try:
        wurzeln.append(os.path.dirname(os.path.abspath(sys.argv[0])))
    except Exception:  # noqa: BLE001
        pass
    wurzeln.append(os.getcwd())
    wurzeln.append(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))

    # Doppelte entfernen, Reihenfolge behalten.
    gesehen: set[str] = set()
    eindeutig: list[str] = []
    for wurzel in wurzeln:
        if not wurzel:
            continue
        fest = os.path.abspath(wurzel)
        if fest in gesehen:
            continue
        gesehen.add(fest)
        eindeutig.append(fest)
    return eindeutig


# -- UFS2Tool -----------------------------------------------------------
def ufs2tool_kennung() -> str:
    """Der Ordnername des mitgelieferten Baus fuer diese Plattform.

    Returns:
        ``win-x64``, ``linux-x64``, ``osx-arm64``, ``osx-x64`` - oder leer,
        wenn nichts passt.
    """
    maschine = (platform.machine() or "").lower()
    arm = maschine in ("arm64", "aarch64")
    if IST_WINDOWS:
        return "win-x64"
    if IST_MACOS:
        return "osx-arm64" if arm else "osx-x64"
    if IST_LINUX and not arm:
        return "linux-x64"
    return ""


def ufs2tool_pruefsumme(wurzel: str, kennung: str, pfad: str) -> None:
    """Prueft die mitgelieferte Datei gegen ``pruefsummen.json``.

    Fehlt die Liste, wird nicht geprueft - aber auch nicht abgebrochen: Ein
    fehlender Pruefwert ist kein Grund, ein vorhandenes Werkzeug
    abzulehnen. Ein *falscher* dagegen schon.
    """
    liste = os.path.join(wurzel, "pruefsummen.json")
    if not os.path.isfile(liste):
        return
    try:
        with io.open(liste, encoding="utf-8") as datei:
            daten = json.load(datei)
        erwartet = str(((daten.get("plattformen") or {}).get(kennung) or {})
                       .get("sha256", "")).lower()
    except Exception as fehler:  # noqa: BLE001
        logger.debug("UFS2Tool-Pruefsummen nicht lesbar: %s", fehler)
        return
    if not re.fullmatch(r"[0-9a-f]{64}", erwartet):
        return
    # Mit with: Ohne den blieb die Datei offen, bis der Sammler kam - der
    # Testlauf meldete das als ResourceWarning, und unter Windows blockiert
    # eine offene Datei das Aufraeumen des Temp-Ordners.
    with open(pfad, "rb") as datei:
        gemessen = hashlib.sha256(datei.read()).hexdigest()
    if gemessen != erwartet:
        raise RuntimeError(
            f"UFS2Tool-v4.1-Integritaetspruefung fuer {kennung} fehlgeschlagen "
            f"(erwartet {erwartet}, erhalten {gemessen})."
        )


def ufs2tool_bereitstellen(wurzel_finden: Callable[[str], str],
                           gemerkt: str = "") -> str:
    """Stellt die mitgelieferte UFS2Tool-v4.1-Fassung dieser Plattform bereit.

    v4.1 liest Zylindergruppen zuverlaessig vollstaendig ein. Das ist fuer
    die schreibgeschuetzte FFPKG-Pruefung wichtig, da aeltere v4.0-Buendel
    bei Teilreads faelschlich ``BAD MAGIC NUMBER`` fuer gueltige Cylinder
    Groups melden konnten.

    **Seit v1.8.72 fuer alle vier Ziele, und eigenstaendig.** Bis dahin lag
    nur der Windows-Bau bei, und der war framework-abhaengig: Seine
    ``runtimeconfig.json`` verlangt ``Microsoft.NETCore.App 8.0.0``. Auf
    einem Rechner ohne installiertes .NET 8 scheiterte ``.ffpkg`` deshalb,
    ohne dass irgendetwas den Grund nannte. Die mitgelieferten Bauten
    bringen jetzt alles mit (``--self-contained``, getrimmt, ohne
    Globalisierung - sonst verlangt der Start unter Linux ``libicu``).

    Args:
        wurzel_finden: Findet den mitgelieferten Ordner. Ueblicherweise
            ``PS5ConverterGUI._mitgeliefert_finden`` - die Methode kennt die
            macOS-Regel zu ``Contents/Resources`` und bleibt deshalb dort.
        gemerkt: Ein frueher gefundener Pfad. Ist er noch da, wird er
            zurueckgegeben, ohne erneut zu suchen.

    Returns:
        Pfad zur ausfuehrbaren Datei.

    Raises:
        RuntimeError: Wenn fuer die Plattform nichts mitgeliefert ist oder
            die Pruefsumme nicht stimmt.
    """
    if gemerkt and os.path.isfile(gemerkt):
        return gemerkt

    wurzel = wurzel_finden(UFS2TOOL_ORDNER)
    kennung = ufs2tool_kennung()
    if not kennung:
        raise RuntimeError(
            f"UFS2Tool wird fuer {systemname()} ({platform.machine()}) "
            "nicht mitgeliefert."
        )
    ordner = os.path.join(wurzel, kennung)
    name = "UFS2Tool.exe" if kennung.startswith("win") else "UFS2Tool"
    pfad = os.path.join(ordner, name)
    if not os.path.isfile(pfad):
        raise RuntimeError(f"UFS2Tool-v4.1 fehlt: {pfad}")

    ufs2tool_pruefsumme(wurzel, kennung, pfad)

    if not IST_WINDOWS:
        # Aus dem Buendel kommt die Datei ohne Ausfuehrungsrecht.
        try:
            os.chmod(pfad, os.stat(pfad).st_mode | 0o111)
        except OSError as fehler:
            logger.debug("UFS2Tool nicht ausfuehrbar zu machen: %s", fehler)

    return pfad


# -- Die MkPFS-Engine ---------------------------------------------------
def _mkpfs_eltern_finden(basis: str) -> str:
    """Sucht rekursiv das Verzeichnis, das das ``mkpfs``-Paket enthaelt.

    Args:
        basis: Wurzelverzeichnis der Suche.

    Returns:
        Uebergeordnetes Verzeichnis des Pakets, oder ``basis`` als Rueckfall.
    """
    for ordner, _unter, dateien in os.walk(basis):
        if os.path.basename(ordner) == "mkpfs" and "__init__.py" in dateien:
            return os.path.dirname(ordner)
    return basis


def _entpacken(ziel: str, zip_pfad: str) -> str:
    """Entpackt das ZIP und gibt den ``sys.path``-Eintrag zurueck."""
    os.makedirs(ziel, exist_ok=True)
    with ZipFile(zip_pfad) as archiv:
        archiv.extractall(ziel)
    return _mkpfs_eltern_finden(ziel)


def _quellordner_finden(fassung: str) -> str | None:
    """Findet einen bereits bereitgestellten MkPFS-Quellordner."""
    for wurzel in suchwurzeln():
        # Variante A: entpackter Ordner "MkPFS-1.0.0/mkpfs"
        kandidat = os.path.join(wurzel, f"MkPFS-{fassung}")
        if os.path.isfile(os.path.join(kandidat, "mkpfs", "__init__.py")):
            return kandidat
        # Variante B: direktes Paket "mkpfs" in der Wurzel
        if os.path.isfile(os.path.join(wurzel, "mkpfs", "__init__.py")):
            return wurzel
    return None


def _zip_finden(fassung: str) -> str | None:
    """Findet die verbindliche MkPFS-ZIP."""
    name = f"MkPFS-{fassung}.zip"
    for wurzel in suchwurzeln():
        kandidat = os.path.join(wurzel, name)
        if os.path.isfile(kandidat):
            return kandidat
    return None


def mkpfs_bereitstellen(temp_ordner: str,
                        fassung: str = MKPFS_ERFORDERLICHE_FASSUNG,
                        melden: Melder | None = None,
                        text: Textquelle | None = None) -> str:
    """Stellt die eingebettete mkpfs-Engine bereit.

    Sucht nach dem Entpacken rekursiv nach dem ``mkpfs``-Python-Paket
    (Verzeichnis mit einer ``__init__.py``) und gibt dessen
    **uebergeordnetes** Verzeichnis zurueck, damit ``import mkpfs``
    funktioniert.

    Windows 10/11: Beruecksichtigt Berechtigungsprobleme in ``%TEMP%`` und
    faellt auf ein Verzeichnis neben der Programmdatei zurueck.

    Args:
        temp_ordner: Der fertige Arbeitsordner. Er wird hereingereicht, weil
            seine Herkunft an einer Tk-Variable haengt - siehe Modulkopf.
        fassung: Die verlangte MkPFS-Fassung.
        melden: Nimmt die Protokollzeilen entgegen.
        text: Uebersetzt die Meldungsschluessel.

    Returns:
        Pfad, der als ``sys.path``-Eintrag taugt - oder ``""``, wenn nichts
        gefunden wurde.
    """
    sag = text or schluessel_zeigen
    melde = melden or stumm

    # 1) Bevorzugt: bereitgestellter Quellordner (bereits entpackt)
    quelle = _quellordner_finden(fassung)
    if quelle:
        eltern = _mkpfs_eltern_finden(quelle)
        if os.path.isdir(os.path.join(eltern, "mkpfs")):
            melde(sag("log.auto.0009", v0=fassung, v1=quelle))
            return eltern

    # 2) ZIP-Variante (auch aus dem PyInstaller-Buendel)
    zip_pfad = _zip_finden(fassung)
    marke = fassung.replace(".", "_")
    if not zip_pfad:
        melde(sag("log.auto.0010", v0=fassung))
        return ""

    ziel = os.path.join(temp_ordner, f"ps5converter_engine_v{marke}")

    # Bereits entpackt und Paket vorhanden?
    vorhanden = _mkpfs_eltern_finden(ziel)
    if os.path.isdir(os.path.join(vorhanden, "mkpfs")):
        melde(sag("log.auto.0011", v0=fassung, v1=vorhanden))
        return vorhanden

    try:
        ergebnis = _entpacken(ziel, zip_pfad)
        melde(sag("log.auto.0012", v0=fassung, v1=zip_pfad))
        melde(sag("log.auto.0013", v0=ergebnis))
        return ergebnis
    except PermissionError as fehler:
        melde(sag("log.auto.0014", v0=fehler))
    except Exception as fehler:  # noqa: BLE001
        melde(sag("log.auto.0015", v0=fehler))

    # Rueckfall: Verzeichnis neben der Programmdatei. Die erste Suchwurzel
    # ist dort das Buendel bzw. der Ordner der Programmdatei selbst.
    daneben = os.path.join(suchwurzeln()[0], f"engine_temp_v{marke}")
    try:
        ergebnis = _entpacken(daneben, zip_pfad)
        melde(sag("log.auto.0016", v0=ergebnis))
        return ergebnis
    except Exception as fehler:  # noqa: BLE001
        melde(sag("log.auto.0017", v0=fehler))
        return daneben


# -- Die Laufzeitpakete der Engine --------------------------------------
def laufzeitpakete_sicherstellen(
        konfigordner: str, *,
        pip_kommando: Callable[..., Any],
        prozess_starten: Callable[..., Any],
        melden: Melder = stumm,
        text: Textquelle = schluessel_zeigen,
) -> bool:
    """Prüft kritische MkPFS-Laufzeitmodule und installiert fehlende Pakete.

    Wird vor dem Start der Engine ausgeführt, damit typische Laufzeitabbrüche
    wie ``ModuleNotFoundError: zlib_ng`` gar nicht erst auftreten.

    Returns:

        True wenn alle benötigten Module verfügbar sind, sonst False.
    """

    # Lokaler Fallback-Pfad für Runtime-Module (wichtig für Umgebungen,
    # in denen pip zwar installiert, die Pakete danach aber nicht im
    # aktuellen Import-Pfad landen).
    runtime_site_dir = os.path.join(
        konfigordner,
        "runtime_site_packages",
    )
    try:
        os.makedirs(runtime_site_dir, exist_ok=True)
        if runtime_site_dir not in sys.path:
            sys.path.insert(0, runtime_site_dir)
    except Exception:
        pass

    # Harte Pflichtmodule (zlib_ng ist optional, MkPFS hat Fallback auf stdlib zlib).
    required = {
        "zstandard": "zstandard",
        "cryptography": "cryptography",
    }

    missing: list[tuple[str, str]] = []
    for module_name, package_name in required.items():
        try:
            __import__(module_name)
        except Exception:
            missing.append((module_name, package_name))

    if not missing:
        return True
        return True

    melden(
        text("log.manual.missing_mkpfs_deps", v0=", ".join(m for m, _ in missing))
    )

    for module_name, package_name in missing:
        melden(text('log.auto.0041', v0=module_name, v1=package_name))
        pip_cmd = pip_kommando(
            [
                "install",
                "--upgrade",
                "--disable-pip-version-check",
                package_name,
            ]
        )
        if not pip_cmd:
            melden(text('log.auto.0042', v0=package_name))
            return False
        rc = prozess_starten(
            pip_cmd,
            timeout=15 * 60,
        )
        if rc != 0:
            melden(text('log.auto.0043', v0=package_name))
            return False
        try:
            importlib.invalidate_caches()
            __import__(module_name)
        except Exception as exc:
            melden(text('log.auto.0044', v0=module_name, v1=exc, v2=runtime_site_dir))
            pip_cmd_fallback = pip_kommando(
                [
                    "install",
                    "--upgrade",
                    "--disable-pip-version-check",
                    "--target",
                    runtime_site_dir,
                    package_name,
                ]
            )
            if not pip_cmd_fallback:
                melden(text('log.auto.0045'))
                return False
            rc_fallback = prozess_starten(
                pip_cmd_fallback,
                timeout=15 * 60,
            )
            if rc_fallback != 0:
                melden(text('log.auto.0046', v0=package_name))
                return False
            try:
                importlib.invalidate_caches()
                if runtime_site_dir not in sys.path:
                    sys.path.insert(0, runtime_site_dir)
                __import__(module_name)
            except Exception as exc2:
                melden(text('log.auto.0047', v0=module_name, v1=exc2))
                return False

    return True
    try:
        # Performance-Optimierung: wenn vorhanden, nutze zlib_ng-Binding.
        # Importform muss zu MkPFS passen (from zlib_ng import zlib_ng as zlib).
        from zlib_ng import zlib_ng as _zlib_ng_impl  # pyright: ignore[reportMissingImports]  # noqa: F401
    except Exception as exc:
        melden(text('log.auto.0048', v0=exc))
    melden(text('log.auto.0049'))
    return True
