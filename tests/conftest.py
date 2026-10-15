# -*- coding: utf-8 -*-
"""Gemeinsame pytest-Einstellungen der Testreihe: nach jeder Testklasse aufraeumen.

Im Volllauf vom 19.09.2026 wuchs der pytest-Prozess auf 6,5 GB privaten
Speicher, frei blieben zuletzt 25 MB; im Lauf davor scheiterte der Aufbau von
``test_werkzeugfeinheiten`` mit ``MemoryError`` - zweimal sogar als
scheinbares ``SyntaxError: invalid syntax`` in einer gueltigen Zeile. Zwei
Dinge blieben bis zum Laufende liegen, weil Klassen so lange leben wie der
Lauf:

**Syntaxbaeume.** Rund zwanzig Klassen parsen das Hauptmodul in
``setUpClass`` (``cls.baum = ast.parse(...)``). Ein Baum belegt rund 80 MB
(2,8 MB Quelltext, 266.898 Knoten). Freigegeben werden Klassenattribute, die
ein ``ast.AST`` sind. Danach: Spitze 4,0 statt 6,5 GB.

**Programmfenster.** Klassen legen ein ganzes ``PS5ConverterGUI`` an
(``cls.app``) - ``test_platzpruefung`` fuenf, ``test_fensterlayout`` sieben;
je Datei zuletzt +544 bzw. +562 MB. Die Referenz loszulassen genuegt nicht:
Gemessen blieb das Fenster am Leben, gehalten von der Tk-Wurzel
(``report_callback_exception`` zeigt auf eine seiner Methoden) und von den
Tcl-Befehlen seiner Variablen (``trace_add``). Abgebaut wird deshalb, was
seit Beginn der Klasse an der Wurzel dazukam - Zeitgeber, Kindfenster,
Bindungen, Tcl-Befehle, Bilder, Fehlermelder, Schliessen-Handler - und die
Befehle der Variablen des Fensters. Gemessen: danach lebt kein Fenster mehr,
der Speicher faellt auf den Ausgangswert (drei Runden: +5 statt +73 MB).

Die Tk-Wurzel selbst bleibt stehen - eine Wurzel je Prozess, nie zerstoeren
(sonst kippt Tcl, siehe ``pruefumgebung``). Abgebaut wird nur bei Klassen,
die selbst ein Programmfenster als Attribut halten; ein modulweit geteiltes
Fenster (``test_debuglauf_befunde._app``) bleibt unberuehrt.

**Dialogfenster.** Kein Test darf ein echtes, modales Fenster oeffnen - es
haelt den ganzen Lauf an (``_keine_echten_dialoge``, seit 24.09.2026).
"""
from __future__ import annotations

import ast
import gc
import importlib
import logging
import os

import pytest

import pruefumgebung

# Kein Testlauf schreibt in den Einstellungsordner des Anwenders. Viele
# Testdateien lenken selbst um (pruefumgebung.umlenken), etliche aber nicht -
# wer eine davon einzeln startete, ohne PS5CONV_KONFIGORDNER zu setzen,
# veraenderte %APPDATA%\PS5ImageConverterPro\paths.json (Durchsicht vom
# 23.09.2026, B-1). Hier, vor dem Laden jeder Testdatei, gilt deshalb ein
# eigener Ordner - es sei denn, der Aufrufer hat schon einen gesetzt.
if not os.environ.get(pruefumgebung.UMGEBUNGSNAME):
    pruefumgebung.umlenken("conftest")

# Dieselbe DPI-Einstellung wie das Programm (Kopf des Hauptmoduls) - und zwar
# bevor irgendeine Testdatei ihre Tk-Wurzel anlegt. Tk uebernimmt die
# Aufloesung beim Anlegen der Wurzel: Kam eine Testdatei ohne Import des
# Hauptmoduls zuerst dran, hatte die gemeinsame Wurzel 96 statt 120 dpi
# ("tk scaling" 1.3346 statt 1.6683). Messungen, die auf 125 % umrechnen,
# lagen dann je nach Reihenfolge daneben - am 25.09.2026 der Hoehentest der
# ActRemoteLink-Seite: 719 px, allein gelaufen unter 700.
if os.name == "nt":
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:  # noqa: BLE001 - aeltere Windows-Fassungen
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:  # noqa: BLE001
            pass

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - ohne Tk gibt es keine Fenster
    tk = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

#: Bindungsziele, die ein Programmfenster setzt - nach dem Abbau wie vorher.
_TK_ZIELE = ("all", "Text", "Entry", "TEntry", "Canvas", "Listbox", "TCombobox",
             "Treeview", "Button", "Label", "Frame", "Toplevel", "Scrollbar")
#: So heisst die Klasse des Programmfensters - in jeder Ladeweise gleich.
_FENSTERKLASSE = "PS5ConverterGUI"


@pytest.fixture(autouse=True, scope="class")
def _syntaxbaeume_freigeben(request: pytest.FixtureRequest):
    """Nach der letzten Pruefung einer Klasse: ihre Syntaxbaeume loslassen."""
    yield
    klasse = request.cls
    if klasse is None:
        return
    for name, wert in list(vars(klasse).items()):
        if isinstance(wert, ast.AST):
            delattr(klasse, name)


def _tk_stand(wurzel) -> dict:
    """Was an der Wurzel haengt - zum Zuruecksetzen nach der Klasse."""
    ziele = _TK_ZIELE + (str(wurzel),)
    return {
        "after": set(wurzel.tk.splitlist(wurzel.tk.call("after", "info"))),
        "kinder": set(wurzel.winfo_children()),
        "bind": {z: {s: wurzel.tk.call("bind", z, s)
                     for s in wurzel.tk.splitlist(wurzel.tk.call("bind", z))}
                 for z in ziele},
        "befehle": set(getattr(wurzel, "_tclCommands", None) or []),
        "bilder": set(wurzel.image_names()),
        "melder": wurzel.__dict__.get("report_callback_exception"),
        "schliessen": wurzel.protocol("WM_DELETE_WINDOW"),
    }


def _wurzel_zuruecksetzen(wurzel, vorher: dict) -> None:
    """Nimmt zurueck, was seit ``vorher`` an der Wurzel dazukam."""
    for job in set(wurzel.tk.splitlist(wurzel.tk.call("after", "info"))) - vorher["after"]:
        try:
            wurzel.after_cancel(job)
        except tk.TclError:
            pass
    for kind in list(wurzel.winfo_children()):
        if kind not in vorher["kinder"]:
            try:
                kind.destroy()
            except tk.TclError:
                pass
    for ziel, alt in vorher["bind"].items():
        for seq in wurzel.tk.splitlist(wurzel.tk.call("bind", ziel)):
            if alt.get(seq) != wurzel.tk.call("bind", ziel, seq):
                wurzel.tk.call("bind", ziel, seq, alt.get(seq, ""))
    try:
        wurzel.tk.call("wm", "protocol", wurzel._w, "WM_DELETE_WINDOW",
                       vorher["schliessen"] or "")
    except tk.TclError:
        pass
    for name in list(getattr(wurzel, "_tclCommands", None) or []):
        if name not in vorher["befehle"]:
            try:
                wurzel.deletecommand(name)
            except tk.TclError:
                pass
    for bild in set(wurzel.image_names()) - vorher["bilder"]:
        try:
            wurzel.tk.call("image", "delete", bild)
        except tk.TclError:
            pass
    if vorher["melder"] is None:
        wurzel.__dict__.pop("report_callback_exception", None)
    else:
        wurzel.report_callback_exception = vorher["melder"]


def _variablen(obj, tiefe: int = 2, gesehen: "set | None" = None):
    """Die Tk-Variablen eines Fensters: Attribute, Listen und Woerterbuecher darin."""
    gesehen = gesehen if gesehen is not None else set()
    if id(obj) in gesehen or tiefe < 0:
        return
    gesehen.add(id(obj))
    if isinstance(obj, tk.Variable):
        yield obj
        return
    if isinstance(obj, dict):
        werte = list(obj.values())
    elif isinstance(obj, (list, tuple, set)):
        werte = list(obj)
    elif hasattr(obj, "__dict__") and not isinstance(obj, (type, tk.Misc)):
        werte = list(vars(obj).values())
    else:
        return
    for wert in werte:
        yield from _variablen(wert, tiefe - 1, gesehen)


def _variablen_loesen(fenster) -> None:
    """Loescht die Tcl-Befehle (trace_add) der Variablen - sie halten Methoden fest."""
    for var in _variablen(vars(fenster)):
        for name in list(var._tclCommands or []):
            try:
                var._tk.deletecommand(name)
            except tk.TclError:
                pass
        var._tclCommands = None


@pytest.fixture(autouse=True, scope="class")
def _programmfenster_abbauen(request: pytest.FixtureRequest):
    """Nach der letzten Pruefung einer Klasse: ihr Programmfenster abbauen."""
    wurzel = getattr(tk, "_default_root", None) if tk is not None else None
    vorher = None
    if wurzel is not None:
        try:
            vorher = _tk_stand(wurzel)
        except tk.TclError as exc:
            logger.debug("Tk-Stand nicht lesbar: %s", exc)
    yield
    klasse = request.cls
    if klasse is None or vorher is None or tk._default_root is not wurzel:
        return
    fenster = [(name, wert) for name, wert in list(vars(klasse).items())
               if type(wert).__name__ == _FENSTERKLASSE]
    if not fenster:
        return
    try:
        _wurzel_zuruecksetzen(wurzel, vorher)
        for _name, app in fenster:
            _variablen_loesen(app)
    except Exception as exc:  # noqa: BLE001 - Aufraeumen darf keinen Test kippen
        logger.warning("Programmfenster von %s nicht vollstaendig abgebaut: %s",
                       klasse.__name__, exc)
    for name, _app in fenster:
        delattr(klasse, name)
    gc.collect()


#: Die modalen Tk-Dialoge. Oeffnet ein Test einen davon wirklich, wartet das
#: Fenster auf einen Klick, den niemand gibt - und mit ihm der ganze Lauf.
_DIALOGE = {
    "tkinter.messagebox": ("showinfo", "showwarning", "showerror", "askquestion",
                           "askokcancel", "askyesno", "askyesnocancel",
                           "askretrycancel"),
    "tkinter.filedialog": ("askopenfilename", "askopenfilenames",
                           "asksaveasfilename", "askdirectory", "askopenfile",
                           "askopenfiles", "asksaveasfile"),
    "tkinter.simpledialog": ("askstring", "askinteger", "askfloat"),
}


#: Die Dialoge, wie tkinter sie mitbringt - festgehalten beim Laden dieser
#: Datei, bevor ein Test etwas ersetzt.
_ORIGINALE: dict = {}
for _modulname, _namen in _DIALOGE.items():
    try:
        _modul = importlib.import_module(_modulname)
    except ImportError:  # pragma: no cover - ohne Tk gibt es keine Dialoge
        continue
    for _name in _namen:
        if hasattr(_modul, _name):
            _ORIGINALE[(_modulname, _name)] = getattr(_modul, _name)


class EchterDialogImTest(AssertionError):
    """Ein Test hat ein echtes, modales Fenster geoeffnet."""


def _dialogsperre(name: str, geoeffnet: list):
    def _dialog(*args, **kwargs):
        titel = kwargs.get("title", args[0] if args else "")
        eintrag = "%s(%r)" % (name, titel)
        geoeffnet.append(eintrag)
        raise EchterDialogImTest("Echter Dialog im Test: " + eintrag)
    return _dialog


@pytest.fixture(autouse=True)
def _keine_echten_dialoge(monkeypatch: pytest.MonkeyPatch):
    """Ein echter Dialog laesst den Test sofort scheitern, statt den Lauf anzuhalten.

    Zweimal ist die Testreihe schon an einem Fenster stehen geblieben, das
    niemand beantworten konnte: am 17.09.2026 der Adminlauf eine halbe Stunde
    lang an "param.json beanstandet", am 23.09.2026 der Volllauf an
    "Content-ID fehlt" (``test_debuglauf_befunde``, der .ffpkg-Bau fragte
    neuerdings nach). Beide Male war nichts zu sehen als ein stehender
    Fortschritt - welcher Test es war, liess sich erst mit Zeitgrenzen
    einkreisen.

    Jetzt ersetzt jeder Test die Dialoge durch eine Sperre. Wird sie
    ausgeloest, wirft sie ``EchterDialogImTest``, und der Test scheitert beim
    Abbau mit Titel und Art des Fensters - auch wenn das Programm die Ausnahme
    selbst verschluckt. Tests, die eine Rueckfrage beantworten wollen, ersetzen
    den Dialog wie bisher mit ``mock.patch``; das geht der Sperre vor.

    Ersetzt wird nur, was noch der echte Dialog ist. Manche Klassen setzen
    ihre Antworten schon in ``setUpClass`` (``test_fensterlayout`` oeffnet so
    jedes Werkzeugfenster samt Ordnerwahl) - die Sperre ueberschrieb sie im
    ersten Volllauf und liess genau diese Klasse scheitern.
    """
    geoeffnet: list[str] = []
    for (modulname, name), original in _ORIGINALE.items():
        modul = importlib.import_module(modulname)
        if getattr(modul, name, None) is not original:
            continue  # schon durch eine Antwort des Tests ersetzt
        monkeypatch.setattr(modul, name,
                            _dialogsperre("%s.%s" % (modulname, name), geoeffnet))
    yield
    if geoeffnet:
        pytest.fail("Der Test hat ein echtes Dialogfenster geoeffnet: "
                    + "; ".join(geoeffnet), pytrace=False)
