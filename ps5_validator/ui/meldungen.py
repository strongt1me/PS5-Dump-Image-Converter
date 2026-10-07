# -*- coding: utf-8 -*-
"""Meldungen und Rueckfragen in der Pillenoptik des Programms statt der Systemdialoge.

Wunsch des Nutzers vom 06.10.2026: "alle Fenster, die sich oeffnen, an die neue Optik anpassen". Die
Werkzeugfenster sind es laengst (``fenster_pillen``); alt sahen nur noch die rund 290 Meldungen und Rueckfragen
aus - ``tkinter.messagebox`` zeigt die Dialoge von Windows (weiss, eckig, Systemknoepfe).

:func:`einrichten` ersetzt beim Programmstart die acht Funktionen von ``tkinter.messagebox`` durch
:func:`zeigen`. Jeder Aufruf im Programm (``messagebox.askyesno(...)``) bekommt so dieselbe Antwort wie vorher
- ``"ok"``, ``True``/``False``, ``None`` bei "Abbrechen", ``"yes"``/``"no"`` bei ``askquestion`` -, nur in
eigenem Fenster. Geht dabei etwas schief (kein Hauptfenster, Aufruf aus einem Faden), gilt der Systemdialog.

Nicht ersetzt: die Datei- und Ordnerdialoge (der Explorer von Windows - dort gehoeren sie hin).
Die Testreihe ruft :func:`einrichten` nie auf; ihre Dialogsperre (``conftest.py``) bleibt unberuehrt.
"""
from __future__ import annotations

import logging
import threading
import tkinter as tk
from tkinter import messagebox

logger = logging.getLogger(__name__)

#: Art -> (Knoepfe, Zeichen, Farbrolle). Knoepfe als (Antwort, Textschluessel); der erste ist die Vorgabe.
ARTEN: dict[str, tuple[tuple[tuple[str, str], ...], str, str]] = {
    "showinfo": ((("ok", "ok"),), "i", "fg_accent"),
    "showwarning": ((("ok", "ok"),), "!", "fg_warning"),
    "showerror": ((("ok", "ok"),), "✕", "error_btn"),
    "askquestion": ((("yes", "ja"), ("no", "nein")), "?", "fg_accent"),
    "askyesno": ((("yes", "ja"), ("no", "nein")), "?", "fg_accent"),
    "askokcancel": ((("ok", "ok"), ("cancel", "abbrechen")), "?", "fg_accent"),
    "askyesnocancel": ((("yes", "ja"), ("no", "nein"), ("cancel", "abbrechen")), "?", "fg_accent"),
    "askretrycancel": ((("retry", "wiederholen"), ("cancel", "abbrechen")), "!", "fg_warning"),
}

#: Knopftexte - hier statt in i18n, weil sie zu diesem Baustein gehoeren.
TEXTE = {
    "ok": {"de": "OK", "en": "OK"},
    "ja": {"de": "Ja", "en": "Yes"},
    "nein": {"de": "Nein", "en": "No"},
    "abbrechen": {"de": "Abbrechen", "en": "Cancel"},
    "ja_alle": {"de": "Ja, für alle", "en": "Yes, for all"},
    "nein_alle": {"de": "Nein, für alle", "en": "No, for all"},
    "wiederholen": {"de": "Wiederholen", "en": "Retry"},
}

#: Die Originale aus ``tkinter.messagebox`` - fuer den Rueckfall und :func:`aufheben`.
_ORIGINALE: dict[str, object] = {}

#: Die vier Antworten der Frage "fuer alle Titel dieses Laufs" (:func:`frage_fuer_alle`).
FUER_ALLE = (("yes", "ja"), ("no", "nein"), ("yes_all", "ja_alle"), ("no_all", "nein_alle"))

#: Wie viele Meldungen gerade auf eine Antwort warten. Eine offene Rueckfrage ist kein Stillstand der Anzeige:
#: Die Ueberwachung des Programms (``_stillstand_uhr``) fragt das ab.
_OFFEN = 0


def offene_meldungen() -> int:
    """Zahl der Meldungen und Rueckfragen, die gerade auf eine Antwort warten."""
    return _OFFEN


def ergebnis(art: str, antwort: "str | None"):
    """Was ``tkinter.messagebox.<art>`` fuer diese Antwort zurueckgaebe."""
    if art in ("showinfo", "showwarning", "showerror"):
        return "ok"
    if art == "askquestion":
        return "yes" if antwort == "yes" else "no"
    if art == "askyesnocancel":
        if antwort in (None, "cancel"):
            return None
        return antwort == "yes"
    return antwort in ("yes", "ok", "retry")


def _ohne_antwort(art: str) -> str:
    """Schliessen ueber das Fenster-X bzw. Esc - wie bei den Systemdialogen."""
    knoepfe = ARTEN[art][0]
    for antwort, _text in reversed(knoepfe):
        if antwort in ("cancel", "no", "ok"):
            return antwort
    return knoepfe[-1][0]


class Meldung:
    """Ein modales Meldungsfenster in der Optik des Programms."""

    def __init__(self, gui, art: str, titel: str, text: str, eltern=None, vorgabe: str = "",
                 knoepfe_eigen: "tuple | None" = None) -> None:
        self.gui = gui
        self.art = art
        self.antwort: "str | None" = None
        self._roh = knoepfe_eigen is not None      # eigene Knopfreihe: die Antwort kommt unuebersetzt zurueck
        knoepfe, zeichen, rolle = ARTEN[art]
        if knoepfe_eigen is not None:
            knoepfe = knoepfe_eigen
        c = gui._COLORS
        sprache = "de" if getattr(gui, "_current_language", "de") == "de" else "en"
        eltern = eltern if eltern is not None else gui.root
        # Schrift und Mass des Programms aus seinem Pillen-Kit - ein Import des Hauptmoduls fuehrte es,
        # als __main__ gestartet, ein zweites Mal aus.
        teile = gui._pw
        UI_SCHRIFT, pt = teile.F, teile.pt  # noqa: N806

        win = tk.Toplevel(eltern, bg=c["bg_main"])
        self.win = win
        win.withdraw()
        win.title(str(titel or ""))
        win.resizable(False, False)
        try:
            win.transient(eltern.winfo_toplevel())
        except tk.TclError:
            pass
        try:
            gui._apply_icon_to_toplevel(win)
        except Exception as exc:  # noqa: BLE001 - ohne Symbol geht es auch
            logger.debug("Meldung ohne Fenstersymbol: %s", exc)

        koerper = tk.Frame(win, bg=c["bg_main"], padx=22, pady=18)
        koerper.pack(fill="both", expand=True)
        oben = tk.Frame(koerper, bg=c["bg_main"])
        oben.pack(fill="x")
        kreis = tk.Canvas(oben, width=pt(30), height=pt(30), bg=c["bg_main"], highlightthickness=0, bd=0)
        rand = 2
        farbe = c.get(rolle, c["fg_accent"])
        kreis.create_oval(rand, rand, pt(30) - rand, pt(30) - rand, outline=farbe, width=2)
        kreis.create_text(pt(30) // 2, pt(30) // 2, text=zeichen, fill=farbe, font=(UI_SCHRIFT, pt(13), "bold"))
        kreis.pack(side="left", anchor="n", padx=(0, 14))
        rechts = tk.Frame(oben, bg=c["bg_main"])
        rechts.pack(side="left", fill="both", expand=True)
        if titel:
            tk.Label(rechts, text=str(titel), font=(UI_SCHRIFT, pt(12), "bold"), bg=c["bg_main"],
                     fg=c["fg_accent"], anchor="w", justify="left").pack(fill="x")
        tk.Label(rechts, text=str(text or ""), font=(UI_SCHRIFT, pt(10)), bg=c["bg_main"],
                 fg=c["fg_primary"], anchor="w", justify="left",
                 wraplength=pt(440)).pack(fill="x", pady=(6 if titel else 0, 0))

        reihe = tk.Frame(koerper, bg=c["bg_main"])
        reihe.pack(fill="x", pady=(18, 0))
        vorgabe = vorgabe if vorgabe in [a for a, _t in knoepfe] else knoepfe[0][0]
        self._vorgabe = vorgabe
        self.knoepfe: dict[str, object] = {}
        for antwort, schluessel in reversed(knoepfe):
            knopf = gui._pw.Button(reihe, text=TEXTE[schluessel][sprache],
                                   command=lambda a=antwort: self._fertig(a),
                                   style="Accent.TButton" if antwort == vorgabe else "")
            knopf.pack(side="right", padx=(8, 0))
            self.knoepfe[antwort] = knopf

        win.protocol("WM_DELETE_WINDOW", lambda: self._fertig(_ohne_antwort(art)))
        win.bind("<Escape>", lambda _e: self._fertig(_ohne_antwort(art)))
        win.bind("<Return>", lambda _e: self._fertig(self._vorgabe))
        win.bind("<KP_Enter>", lambda _e: self._fertig(self._vorgabe))
        self._mittig(eltern)

    def _mittig(self, eltern) -> None:
        win = self.win
        win.update_idletasks()
        breite, hoehe = win.winfo_reqwidth(), win.winfo_reqheight()
        try:
            oben = eltern.winfo_toplevel()
            if oben.winfo_viewable():
                x = oben.winfo_rootx() + (oben.winfo_width() - breite) // 2
                y = oben.winfo_rooty() + (oben.winfo_height() - hoehe) // 3
            else:
                raise tk.TclError("Eltern nicht sichtbar")
        except tk.TclError:
            x = (win.winfo_screenwidth() - breite) // 2
            y = (win.winfo_screenheight() - hoehe) // 3
        win.geometry("+%d+%d" % (max(0, x), max(0, y)))

    def _fertig(self, antwort: str) -> None:
        self.antwort = antwort
        try:
            self.win.grab_release()
        except tk.TclError:
            pass
        self.win.destroy()

    def _nach_vorn(self) -> None:
        """Holt die Meldung vor alle Fenster und lässt die Taskleiste blinken.

        Meldung des Anwenders (07.10.2026): Bei der Ordner-zu-exFAT-Konvertierung von zwölf Titeln fragte das Programm
        nach dem neunten, ob eine fehlerhafte param.json repariert werden soll - und der Anwender sah nichts davon:
        Das Fenster stand hinter anderen Programmen, das Hauptfenster war gesperrt (die Meldung ist modal), und es
        sah aus, als sei das Programm abgestuerzt. Windows laesst ein Programm im Hintergrund keinen Fokus nehmen -
        ``focus_force`` allein reicht dort nicht. Deshalb: oberstes Fenster, ein minimiertes Hauptfenster wird
        zurueckgeholt, und die Taskleistenschaltflaeche blinkt, bis das Programm vorn ist.
        """
        win = self.win
        try:
            win.attributes("-topmost", True)
        except tk.TclError:
            pass
        try:
            oben = self.gui.root
            if oben.state() == "iconic":
                oben.deiconify()
        except tk.TclError:
            pass
        _blinken(self.gui.root)

    def zeigen(self):
        """Zeigt das Fenster, wartet auf die Antwort und gibt sie wie ``tkinter.messagebox`` zurueck."""
        global _OFFEN
        win = self.win
        win.deiconify()
        win.lift()
        self._nach_vorn()
        try:
            win.grab_set()
        except tk.TclError:
            pass
        knopf = self.knoepfe.get(self._vorgabe)
        try:
            (knopf or win).focus_force()
        except tk.TclError:
            pass
        _OFFEN += 1
        try:
            win.wait_window()
        finally:
            _OFFEN -= 1
        if self._roh:
            return self.antwort or "no"
        return ergebnis(self.art, self.antwort)


def frage_fuer_alle(gui, titel: str, text: str, vorgabe: str = "yes") -> str:
    """Eine Ja/Nein-Frage mit "fuer alle" - nur im Hauptfaden.

    Returns:
        ``"yes"``, ``"no"``, ``"yes_all"`` oder ``"no_all"``; das Fenster-X und Esc gelten als ``"no"``.
    """
    meldung = Meldung(gui, "askyesno", titel, text, vorgabe=vorgabe, knoepfe_eigen=FUER_ALLE)
    return meldung.zeigen()


def _blinken(fenster) -> None:
    """Die Taskleistenschaltflaeche des Hauptfensters blinken lassen (nur Windows); ohne Wirkung sonst."""
    import sys
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        class _FLASHWINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND), ("dwFlags", wintypes.DWORD),
                        ("uCount", wintypes.UINT), ("dwTimeout", wintypes.DWORD)]

        hwnd = ctypes.windll.user32.GetParent(fenster.winfo_id()) or fenster.winfo_id()
        info = _FLASHWINFO(ctypes.sizeof(_FLASHWINFO), hwnd, 0x00000003 | 0x0000000C, 0, 0)  # ALL | TIMERNOFG
        ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
    except Exception as exc:  # noqa: BLE001 - Blinken ist Beiwerk
        logger.debug("Taskleiste nicht zum Blinken gebracht: %s", exc)


def zeigen(gui, art: str, title=None, message=None, **optionen):
    """Ersatz fuer ``tkinter.messagebox.<art>(title, message, **optionen)``."""
    original = _ORIGINALE.get(art) or getattr(messagebox, art)
    if threading.current_thread() is not threading.main_thread():
        return original(title, message, **optionen)
    try:
        if gui is None or not gui.root.winfo_exists():
            return original(title, message, **optionen)
        vorgabe = str(optionen.get("default") or "")
        meldung = Meldung(gui, art, title or "", message or "", eltern=optionen.get("parent"),
                          vorgabe=vorgabe)
    except Exception as exc:  # noqa: BLE001 - lieber der Systemdialog als gar keine Meldung
        logger.debug("Meldung in Pillenoptik nicht moeglich (%s) - Systemdialog", exc)
        return original(title, message, **optionen)
    return meldung.zeigen()


def einrichten(gui) -> None:
    """Leitet alle ``tkinter.messagebox``-Aufrufe auf :func:`zeigen` um - einmal beim Programmstart."""
    for art in ARTEN:
        if art not in _ORIGINALE:
            _ORIGINALE[art] = getattr(messagebox, art)

        def _ersatz(title=None, message=None, _art=art, **optionen):
            return zeigen(gui, _art, title, message, **optionen)

        _ersatz.__name__ = art
        setattr(messagebox, art, _ersatz)


def aufheben() -> None:
    """Stellt die Systemdialoge wieder her."""
    for art, original in _ORIGINALE.items():
        setattr(messagebox, art, original)
