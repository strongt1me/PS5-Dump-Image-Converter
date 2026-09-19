# -*- coding: utf-8 -*-
"""Ist der OSFMount-Treiber wirklich einsatzbereit - oder liegt nur das Programm da?

OSFMount ist seit v1.9.25 nur noch Rueckfall fuer ungewoehnliche Abbilder;
der eingebettete exFAT-Leser kommt ohne aus. Wenn der Rueckfall aber einmal
gebraucht wird, genuegt es nicht, dass ``OSFMount.com`` existiert: Einhaengen
kann es nur mit seinem Kerneltreiber ``osfdisk``.

Gemessen am 19.09.2026 auf dem Entwicklungsrechner - OSFMount 3.3.1000 war
installiert, ``win10\\osfdisk.inf`` lag im Programmordner, und trotzdem:

* kein Dienst ``osfdisk`` (``sc query``: Fehler 1060, kein Registry-Schluessel),
* kein Paket im Treiberspeicher (``pnputil /enum-drivers`` listete 52 Pakete,
  keines davon osfdisk),
* keine ``osfdisk.sys`` in ``System32\\drivers``, kein Geraet unter
  ``Enum\\Root``.

Der bisherige Bericht meldete dazu "vorhanden, Fassung 3.3.1000" - und der
Rueckfall haette nichts einhaengen koennen. Dieselbe Fehlerklasse beschreibt
eine Anleitung, die einem fremden FPKG-Builder beiliegt ("driver not
installed", "driver disabled", fehlender Legacy-Adapter ``root\\osfdisk``).
Uebernommen ist nur dieses Wissen, kein Code.

Alles hier **liest nur**: Registry, Dateisystem und ``pnputil
/enum-drivers`` (laeuft ohne Adminrechte). Installiert oder geaendert wird
nichts - das bleibt dem Anwender, und der Bericht sagt ihm wie.
"""
from __future__ import annotations

import glob
import logging
import os
import subprocess
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)

#: Der Dienstname aus ``osfdisk.inf`` (``AddService = osfdisk, ...``).
DIENST = "osfdisk"
#: Die Hardware-Kennung des Legacy-Adapters aus derselben INF.
HARDWARE_ID = "root\\osfdisk"
#: ``Start`` = 4 heisst: Dienst deaktiviert.
START_DEAKTIVIERT = 4

# Die Urteile, vom guenstigsten zum schlechtesten gelesen.
BEREIT = "bereit"
NICHT_WINDOWS = "nicht_windows"
NICHT_INSTALLIERT = "nicht_installiert"
TREIBER_FEHLT = "treiber_fehlt"
DEAKTIVIERT = "deaktiviert"
DATEI_FEHLT = "datei_fehlt"
ADAPTER_FEHLT = "adapter_fehlt"
UNBEKANNT = "unbekannt"


@dataclass
class Treiberzustand:
    """Was ueber OSFMount und seinen Treiber feststeht.

    ``None`` in einem Feld heisst "nicht feststellbar" - nie "nein".
    """

    urteil: str
    programm: str = ""
    inf: str = ""
    dienst_start: int | None = None
    im_treiberspeicher: bool | None = None
    treiberdatei: bool = False
    geraet: bool | None = None
    hinweise: list[str] = field(default_factory=list)


@dataclass
class Messfuehler:
    """Die vier Stellen, an denen gelesen wird - fuer Pruefungen ersetzbar."""

    dienst_start: Callable[[], "int | None"]
    im_treiberspeicher: Callable[[], "bool | None"]
    treiberdatei: Callable[[], bool]
    geraet: Callable[[], "bool | None"]


def inf_finden(programmordner: str) -> str:
    """Die ``osfdisk.inf`` im Programmordner - bevorzugt die fuer Windows 10+."""
    if not programmordner or not os.path.isdir(programmordner):
        return ""
    bevorzugt = os.path.join(programmordner, "win10", "osfdisk.inf")
    if os.path.isfile(bevorzugt):
        return bevorzugt
    treffer = sorted(glob.glob(os.path.join(programmordner, "*", "osfdisk.inf"))
                     + glob.glob(os.path.join(programmordner, "osfdisk.inf")))
    return treffer[0] if treffer else ""


def _dienst_start_lesen() -> "int | None":
    """``Start`` des Dienstes osfdisk; None, wenn es den Dienst nicht gibt."""
    import winreg  # noqa: PLC0415 - nur unter Windows vorhanden

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SYSTEM\CurrentControlSet\Services\%s" % DIENST) as schluessel:
            wert, _typ = winreg.QueryValueEx(schluessel, "Start")
            return int(wert)
    except FileNotFoundError:
        return None


def _im_treiberspeicher_lesen() -> "bool | None":
    """Steht ein osfdisk-Paket im Treiberspeicher? None, wenn nicht abfragbar.

    Die Ausgabe von ``pnputil`` ist uebersetzt ("Originalname", "Original
    Name"); gesucht wird deshalb nur der Dateiname. Eine leere Ausgabe ist
    kein Nein - dann hat die Abfrage nichts geliefert.
    """
    try:
        from ps5_validator.utils.plattform import prozess_flags  # noqa: PLC0415
        flaggen = prozess_flags()
    except Exception:  # noqa: BLE001
        flaggen = {}
    try:
        lauf = subprocess.run(["pnputil", "/enum-drivers"], capture_output=True,
                              timeout=20, **flaggen)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("pnputil nicht abfragbar: %s", exc)
        return None
    text = (lauf.stdout or b"").decode("utf-8", errors="replace").lower()
    if ".inf" not in text:
        return None
    return DIENST + ".inf" in text


def _treiberdatei_lesen() -> bool:
    wurzel = os.environ.get("SystemRoot") or r"C:\Windows"
    return os.path.isfile(os.path.join(wurzel, "System32", "drivers", DIENST + ".sys"))


def _geraet_lesen() -> "bool | None":
    """Gibt es ein Geraet mit Dienst osfdisk bzw. Kennung root\\osfdisk?

    Windows legt solche Geraete unter ``Enum\\Root\\<Name>\\<Nummer>`` ab, mit
    den Werten ``Service`` und ``HardwareID`` (gemessen an den vorhandenen
    Eintraegen, Schreibweise gemischt). Verglichen werden die Werte, nicht
    der Schluesselname - der haengt davon ab, wie das Geraet angelegt wurde.
    """
    import winreg  # noqa: PLC0415

    try:
        wurzel = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SYSTEM\CurrentControlSet\Enum\Root")
    except OSError as exc:
        logger.debug("Enum\\Root nicht lesbar: %s", exc)
        return None
    with wurzel:
        i = 0
        while True:
            try:
                name = winreg.EnumKey(wurzel, i)
            except OSError:
                return False
            i += 1
            try:
                geraet = winreg.OpenKey(wurzel, name)
            except OSError:
                continue
            with geraet:
                j = 0
                while True:
                    try:
                        nummer = winreg.EnumKey(geraet, j)
                    except OSError:
                        break
                    j += 1
                    if _traegt_osfdisk(geraet, nummer):
                        return True


def _traegt_osfdisk(geraet, nummer: str) -> bool:
    import winreg  # noqa: PLC0415

    try:
        with winreg.OpenKey(geraet, nummer) as eintrag:
            try:
                dienst = str(winreg.QueryValueEx(eintrag, "Service")[0])
            except OSError:
                dienst = ""
            try:
                kennungen = winreg.QueryValueEx(eintrag, "HardwareID")[0]
            except OSError:
                kennungen = []
    except OSError:
        return False
    if isinstance(kennungen, str):
        kennungen = [kennungen]
    return (dienst.lower() == DIENST
            or any(str(k).lower() == HARDWARE_ID for k in kennungen or []))


def echte_messfuehler() -> Messfuehler:
    return Messfuehler(dienst_start=_dienst_start_lesen,
                       im_treiberspeicher=_im_treiberspeicher_lesen,
                       treiberdatei=_treiberdatei_lesen,
                       geraet=_geraet_lesen)


def zustand(programm: str, *, fuehler: "Messfuehler | None" = None,
            windows: "bool | None" = None) -> Treiberzustand:
    """Beurteilt OSFMount samt Treiber.

    Args:
        programm: Pfad auf ``OSFMount.com`` (oder ``.exe``); leer oder nicht
            vorhanden heisst "nicht installiert".
        fuehler: Die Lesestellen; ohne Angabe die echten.
        windows: Nur fuer Pruefungen; sonst entscheidet ``os.name``.
    """
    if not (os.name == "nt" if windows is None else windows):
        return Treiberzustand(NICHT_WINDOWS, programm=programm)
    if not programm or not os.path.isfile(programm):
        return Treiberzustand(NICHT_INSTALLIERT, programm=programm)
    fuehler = fuehler or echte_messfuehler()
    ergebnis = Treiberzustand(UNBEKANNT, programm=programm,
                              inf=inf_finden(os.path.dirname(programm)))
    try:
        ergebnis.dienst_start = fuehler.dienst_start()
        ergebnis.im_treiberspeicher = fuehler.im_treiberspeicher()
        ergebnis.treiberdatei = bool(fuehler.treiberdatei())
        ergebnis.geraet = fuehler.geraet()
    except Exception as exc:  # noqa: BLE001 - ein Bericht darf daran nicht scheitern
        logger.debug("OSFMount-Treiber nicht pruefbar: %s", exc)
        ergebnis.hinweise.append(str(exc))
        return ergebnis

    if ergebnis.dienst_start is None:
        ergebnis.urteil = TREIBER_FEHLT
    elif ergebnis.dienst_start == START_DEAKTIVIERT:
        ergebnis.urteil = DEAKTIVIERT
    elif not ergebnis.treiberdatei:
        ergebnis.urteil = DATEI_FEHLT
    elif ergebnis.geraet is False:
        ergebnis.urteil = ADAPTER_FEHLT
    elif ergebnis.geraet is True:
        ergebnis.urteil = BEREIT
    # Sonst bleibt es bei UNBEKANNT: Ohne lesbares Geraet ist "bereit"
    # eine Behauptung ueber etwas, das niemand angesehen hat.
    return ergebnis


def berichtszeile(z: Treiberzustand) -> str:
    """Der Text fuer den Diagnosebericht - leer, wo es nichts zu sagen gibt."""
    inf = z.inf or r"C:\Program Files\OSFMount\win10\osfdisk.inf"
    if z.urteil in (NICHT_WINDOWS, NICHT_INSTALLIERT):
        return ""
    if z.urteil == BEREIT:
        return "bereit (Dienst osfdisk, Treiberdatei und Gerät vorhanden)"
    if z.urteil == TREIBER_FEHLT:
        stand = ("das Paket steht im Treiberspeicher, der Dienst fehlt"
                 if z.im_treiberspeicher else "weder Dienst noch Treiberpaket")
        return ("NICHT INSTALLIERT – OSFMount liegt da, sein Treiber osfdisk aber "
                "nicht (%s). Das Programm braucht OSFMount nicht; als Rückfall "
                "wäre es so nicht nutzbar. Abhilfe: OSFMount neu installieren, "
                "den Treiber dabei zulassen, danach neu starten – oder als "
                "Administrator: pnputil /add-driver \"%s\" /install" % (stand, inf))
    if z.urteil == DEAKTIVIERT:
        return ("DEAKTIVIERT – der Dienst osfdisk steht auf Start=4. Abhilfe: "
                "OSFMount neu installieren und danach neu starten.")
    if z.urteil == DATEI_FEHLT:
        return ("Dienst osfdisk eingetragen, aber osfdisk.sys fehlt in "
                "System32\\drivers. Abhilfe: OSFMount neu installieren.")
    if z.urteil == ADAPTER_FEHLT:
        return ("Treiber installiert, aber kein Gerät root\\osfdisk. Abhilfe: "
                "Geräte-Manager › Aktion › Legacyhardware hinzufügen › "
                "Datenträger › \"%s\", danach neu starten." % inf)
    grund = "; ".join(z.hinweise) if z.hinweise else "Geräteliste nicht lesbar"
    return "nicht feststellbar (%s)" % grund
