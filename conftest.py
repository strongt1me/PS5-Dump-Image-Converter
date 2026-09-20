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
"""
from __future__ import annotations

import ast
import gc
import logging

import pytest

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
