# -*- coding: utf-8 -*-
"""Das Fenster "Abbild bearbeiten" unter WEITERE TOOLS (Nutzerwunsch 05.11.2026).

Dateien eines fertigen Abbilds umbenennen, loeschen, ersetzen oder hinzufuegen - und das Ergebnis wieder als Abbild
speichern. In ein fertiges Abbild laesst sich nichts hineinschreiben (siehe :mod:`ps5_validator.utils.abbild_bearbeiten`);
der Weg ist deshalb immer derselbe, den das Programm auch sonst geht:

1. **Entpacken** - das Abbild wird mit der vorhandenen Umwandlung (Aufgabe 6, Ziel Dump-Ordner) in einen Arbeitsordner
   entpackt, mit allen Rueckfragen und Pruefungen dieser Aufgabe.
2. **Bearbeiten** - im Baum Dateien waehlen und aendern; jede Aenderung geschieht sofort im Arbeitsordner.
3. **Speichern** - der Ordner wird mit derselben Umwandlung (Aufgabe 6) wieder zu einem Abbild gepackt. Das Ergebnis
   heisst ``<Name>_bearbeitet.<Endung>`` und liegt neben dem Original (oder wo man es hinlegt); das Original bleibt
   unveraendert.

Die Umwandlung selbst laeuft in der Hauptoberflaeche (Fortschritt, Protokoll, Abbrechen wie gewohnt). Dieses Fenster
stellt ihr Quelle, Ziel und Format ein, startet sie und wartet im Takt auf ihr Ende; danach gehoert die Oberflaeche
wieder dem Anwender (:func:`aufgabe_starten`).
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from typing import Any, Callable

from ps5_validator.utils import abbild_bearbeiten as ab
from ps5_validator.utils import exfat_bearbeiten as exfat_direkt

logger = logging.getLogger("PS5Converter.abbild_bearbeiten_fenster")

#: Endung -> Formatschluessel der Umwandlung. ``.ffpfs`` ist die unkomprimierte Fassung von ``.ffpfsc``.
FORMATE: dict[str, str] = {".ffpfsc": "ffpfsc", ".ffpfs": "ffpfs", ".exfat": "exfat", ".ffpkg": "ffpkg"}
ENDUNG_VON: dict[str, str] = {schluessel: endung for endung, schluessel in FORMATE.items()}
#: Wie oft (ms) das Fenster nachsieht, ob die Umwandlung fertig ist.
TAKT_MS = 400
#: Namenszusatz des gespeicherten Ergebnisses - das Original bleibt dadurch unberuehrt.
ZUSATZ = "_bearbeitet"


def format_der_datei(pfad: str) -> str:
    """Der Formatschluessel zu einer Abbilddatei (``""`` wenn die Endung keins ist)."""
    return FORMATE.get(os.path.splitext(str(pfad or ""))[1].lower(), "")


def ordner_entfernen(pfad: str) -> None:
    """Entfernt einen Arbeitsordner samt schreibgeschuetzter Dateien (entpackte Dumps haben solche)."""
    import stat

    def _nachbessern(funktion, p, _fehler) -> None:
        try:
            os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
            funktion(p)
        except OSError:
            pass

    if sys_hat_onexc():
        shutil.rmtree(pfad, onexc=_nachbessern)
    else:
        shutil.rmtree(pfad, onerror=_nachbessern)


def sys_hat_onexc() -> bool:
    """``shutil.rmtree`` kennt ``onexc`` ab Python 3.12 (``onerror`` ist seitdem veraltet)."""
    import sys
    return sys.version_info >= (3, 12)


def aufgabe_starten(gui, quelle: str, ziel: str, zielformat: str,
                    fertig: Callable[[bool, str], None]) -> bool:
    """Startet die Umwandlung ``quelle`` -> ``zielformat`` in der Hauptoberflaeche und meldet das Ende.

    Setzt Aufgabe 6, Quelle, Ziel und Zielformat der Hauptoberflaeche, ruft ``_launch_task`` (mit allen ihren Pruefungen
    und Rueckfragen) und ruft ``fertig(ok, ausgabepfad)`` im Hauptfaden, sobald der Aufgabenfaden zu Ende ist. Danach
    stellt es die vorherigen Werte der Oberflaeche wieder her.

    Returns:
        ``False``, wenn die Aufgabe nicht anlief (eine andere laeuft noch, oder eine Pruefung bzw. Rueckfrage hat sie
        abgelehnt) - ``fertig`` wird dann **nicht** gerufen.
    """
    if gui._vorgang_laeuft_noch():
        return False
    vorher = {
        "modus": str(gui.current_mode.get()),
        "quelle": gui.source_path.get(),
        "ziel": gui.dest_path.get(),
        "format": gui.target_format.get(),
        "sammel": list(getattr(gui, "_batch_sources", []) or []),
    }

    def _zuruecksetzen() -> None:
        try:
            gui._set_mode_from_sidebar(vorher["modus"])
            gui.source_path.set(vorher["quelle"])
            gui.dest_path.set(vorher["ziel"])
            gui._batch_sources = vorher["sammel"]
        except Exception as exc:  # noqa: BLE001 - die Oberflaeche darf an einer Wiederherstellung nicht scheitern
            logger.debug("Oberflaeche nicht wiederhergestellt: %s", exc)

    gui._batch_sources = []
    gui._set_mode_from_sidebar("universal_convert")
    gui.source_path.set(quelle)
    gui.dest_path.set(ziel)
    gui.target_format.set(gui._zielformat_label(zielformat, "universal_convert", quelle))
    faden_vorher = getattr(gui, "_task_thread", None)
    gui._last_task_ok = False
    gui.task_final_output_path = ""
    try:
        gui._launch_task()
    except Exception:  # noqa: BLE001
        logger.exception("Abbild bearbeiten: Aufgabe liess sich nicht starten")
        _zuruecksetzen()
        return False
    faden = getattr(gui, "_task_thread", None)
    if faden is None or faden is faden_vorher:
        _zuruecksetzen()
        return False

    def _pruefen() -> None:
        if faden.is_alive() or gui._vorgang_laeuft_noch():
            gui.root.after(TAKT_MS, _pruefen)
            return
        ok = bool(getattr(gui, "_last_task_ok", False))
        ausgabe = str(getattr(gui, "task_final_output_path", "") or "")
        _zuruecksetzen()
        try:
            fertig(ok, ausgabe)
        except Exception:  # noqa: BLE001
            logger.exception("Abbild bearbeiten: Rueckmeldung fehlgeschlagen")

    gui.root.after(TAKT_MS, _pruefen)
    return True


class BearbeitenFenster:
    """Der Inhalt des Fensters: Abbild waehlen und entpacken, Baum bearbeiten, wieder speichern."""

    def __init__(self, gui, win: "tk.Toplevel", schrift: str, mono: str, pt: Callable[[int], int]) -> None:
        self.g = gui
        self.t = gui._t
        self.c = gui._COLORS
        self.F = schrift
        self.M = mono
        self.pt = pt
        self.win = win
        self.bild = ""
        self.arbeit = ""            # Arbeitsordner (enthaelt den Spielordner)
        self.ordner = ""            # der entpackte Spielordner darin
        self.protokoll = ab.Protokoll()
        self.gespeichert_bei = 0    # Anzahl der Aenderungen, die schon in einem gespeicherten Abbild stecken
        self.beschaeftigt = False
        self.direkt: "exfat_direkt.ExfatAbbild | None" = None   # ein .exfat, das direkt geaendert wird (ohne Entpacken)
        self.direkt_offen = 0                                   # Aenderungen daran, die noch nicht geschrieben sind
        self.direkt_ordner: "set[str]" = set()
        self.baum_status = ""
        self._bauen()
        win.protocol("WM_DELETE_WINDOW", self._schliessen)
        win.bind("<Destroy>", self._beim_zerstoeren, add="+")

    # ---- Aufbau ----------------------------------------------------------------------------------------------
    def _bauen(self) -> None:
        c, pw = self.c, self.g._pw
        koerper = tk.Frame(self.win, bg=c["bg_main"], padx=16, pady=8)
        koerper.pack(fill="both", expand=True)
        koerper.grid_columnconfigure(0, weight=1)
        koerper.grid_rowconfigure(2, weight=1)

        tk.Label(koerper, text=self.t("bearbeiten.hinweis_ablauf"), font=(self.F, self.pt(9)), bg=c["bg_main"],
                 fg=c["fg_secondary"], wraplength=780, justify="left", anchor="w").grid(
                     row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        zeile = tk.Frame(koerper, bg=c["bg_main"])
        zeile.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        zeile.grid_columnconfigure(1, weight=1)
        tk.Label(zeile, text=self.t("bearbeiten.abbild_label"), font=(self.F, self.pt(9), "bold"),
                 bg=c["bg_main"], fg=c["fg_primary"]).grid(row=0, column=0, padx=(0, 8))
        self.bild_var = tk.StringVar()
        pw.Entry(zeile, textvariable=self.bild_var, font=(self.F, self.pt(9))).grid(row=0, column=1, sticky="ew")
        self.waehlen_knopf = pw.Button(zeile, text=self.t("bearbeiten.waehlen"), command=self._abbild_waehlen)
        self.waehlen_knopf.grid(row=0, column=2, padx=(8, 0))
        self.entpacken_knopf = pw.Button(zeile, text=self.t("bearbeiten.entpacken"), style="Accent.TButton",
                                         command=self._entpacken)
        self.entpacken_knopf.grid(row=0, column=3, padx=(8, 0))
        self.direkt_knopf = pw.Button(zeile, text=self.t("bearbeiten.direkt"), command=self._direkt_oeffnen)
        self.direkt_knopf.grid(row=0, column=4, padx=(8, 0))

        self.baum = pw.Treeview(koerper, columns=("groesse",), show="tree headings", selectmode="browse", height=14)
        self.baum.heading("#0", text=self.t("bearbeiten.spalte_name"), anchor="w")
        self.baum.heading("groesse", text=self.t("bearbeiten.spalte_groesse"), anchor="e")
        self.baum.column("#0", width=520, anchor="w")
        self.baum.column("groesse", width=120, anchor="e")
        self.baum.grid(row=2, column=0, sticky="nsew")

        knoepfe = tk.Frame(koerper, bg=c["bg_main"])
        knoepfe.grid(row=2, column=1, sticky="n", padx=(10, 0))
        self.aenderungs_knoepfe = []
        for schluessel, befehl in (("bearbeiten.umbenennen", self._umbenennen),
                                   ("bearbeiten.loeschen", self._loeschen),
                                   ("bearbeiten.ersetzen", self._ersetzen),
                                   ("bearbeiten.hinzufuegen", self._hinzufuegen),
                                   ("bearbeiten.ordner_neu", self._neuer_ordner)):
            knopf = pw.Button(knoepfe, text=self.t(schluessel), command=befehl)
            knopf.pack(fill="x", pady=(0, 6))
            self.aenderungs_knoepfe.append(knopf)

        fuss = tk.Frame(koerper, bg=c["bg_main"])
        fuss.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        fuss.grid_columnconfigure(0, weight=1)
        self.zaehler_var = tk.StringVar()
        tk.Label(fuss, textvariable=self.zaehler_var, font=(self.F, self.pt(9)), bg=c["bg_main"],
                 fg=c["fg_secondary"], anchor="w").grid(row=0, column=0, sticky="w")
        tk.Label(fuss, text=self.t("bearbeiten.format_label"), font=(self.F, self.pt(9)), bg=c["bg_main"],
                 fg=c["fg_primary"]).grid(row=0, column=1, padx=(8, 6))
        self.format_var = tk.StringVar()
        self.format_namen = {ENDUNG_VON[k]: k for k in ENDUNG_VON}       # ".ffpfsc" -> "ffpfsc"
        self.format_box = pw.Combobox(fuss, textvariable=self.format_var, state="readonly", width=10,
                                      values=list(self.format_namen), font=(self.F, self.pt(9)))
        self.format_box.grid(row=0, column=2)
        self.speichern_knopf = pw.Button(fuss, text=self.t("bearbeiten.speichern"), style="Accent.TButton",
                                         command=self._speichern)
        self.speichern_knopf.grid(row=0, column=3, padx=(8, 0))

        self.status_var = tk.StringVar(value=self.t("bearbeiten.status_bereit"))
        tk.Label(koerper, textvariable=self.status_var, font=(self.F, self.pt(9)), bg=c["bg_main"],
                 fg=c["fg_secondary"], anchor="w", wraplength=780, justify="left").grid(
                     row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self._zustand_setzen()

    # ---- Zustand ---------------------------------------------------------------------------------------------
    def _zustand_setzen(self) -> None:
        """Knoepfe freigeben oder sperren, je nachdem, ob ein Spielordner da ist und ob etwas laeuft."""
        direkt = self.direkt is not None
        da = direkt or (bool(self.ordner) and os.path.isdir(self.ordner))
        frei = not self.beschaeftigt
        for knopf in self.aenderungs_knoepfe:
            knopf.config(state="normal" if (da and frei) else "disabled")
        # Direkt im Abbild gibt es nichts zu speichern, solange nichts vorgemerkt ist; das Format bleibt .exfat.
        anwenden = direkt and self.direkt_offen > 0
        self.speichern_knopf.config(text=self.t("bearbeiten.anwenden" if direkt else "bearbeiten.speichern"),
                                    state="normal" if (frei and (anwenden if direkt else da)) else "disabled")
        self.format_box.config(state="readonly" if (da and frei and not direkt) else "disabled")
        self.entpacken_knopf.config(state="normal" if frei else "disabled")
        self.direkt_knopf.config(state="normal" if frei else "disabled")
        self.waehlen_knopf.config(state="normal" if frei else "disabled")
        if direkt:
            n, offen = self.direkt_offen, self.direkt_offen
        else:
            n, offen = self.protokoll.anzahl(), self.protokoll.anzahl() - self.gespeichert_bei
        self.zaehler_var.set(self.t("bearbeiten.zaehler", n=n, offen=max(0, offen)))

    def _hat_ungespeichertes(self) -> bool:
        if self.direkt is not None and self.direkt_offen > 0:
            return True
        return bool(self.ordner) and self.protokoll.anzahl() > self.gespeichert_bei

    def _ist_ordner(self, rel: str) -> bool:
        """Ist ``rel`` im Baum ein Ordner (im Arbeitsordner oder direkt im Abbild)?"""
        if self.direkt is not None:
            return rel in self.direkt_ordner
        return os.path.isdir(os.path.join(self.ordner, *rel.split("/")))

    def _status(self, text: str) -> None:
        self.status_var.set(text)

    def _fehler(self, exc: "ab.BearbeitenFehler") -> None:
        text = self.t(exc.schluessel)
        detail = str(exc) if str(exc) != exc.schluessel else ""
        messagebox.showerror(self.t("titlebar.abbild_bearbeiten"),
                             "%s\n\n%s" % (text, detail) if detail else text, parent=self.win)

    # ---- Baum ------------------------------------------------------------------------------------------------
    def _baum_fuellen(self, auswahl: str = "") -> None:
        for kind in self.baum.get_children(""):
            self.baum.delete(kind)
        if self.direkt is not None:
            self._direkt_baum_fuellen(auswahl)
            return
        if not self.ordner:
            return
        eintraege = ab.auflisten(self.ordner)
        for e in eintraege:
            eltern = e.rel.rsplit("/", 1)[0] if "/" in e.rel else ""
            name = e.rel.rsplit("/", 1)[-1]
            groesse = "" if e.ist_ordner else self.g._fmt_bytes(e.groesse)
            self.baum.insert(eltern, "end", iid=e.rel, text=name, values=(groesse,), open=(eltern == ""))
        if auswahl and self.baum.exists(auswahl):
            self.baum.selection_set(auswahl)
            self.baum.see(auswahl)
        self._status(self.t("bearbeiten.status_entpackt", n=len(eintraege)))

    def _gewaehlt(self) -> str:
        auswahl = self.baum.selection()
        return str(auswahl[0]) if auswahl else ""

    def _gewaehlt_pruefen(self, ordner_erlaubt: bool = True) -> str:
        rel = self._gewaehlt()
        if not rel:
            messagebox.showinfo(self.t("titlebar.abbild_bearbeiten"), self.t("bearbeiten.nichts_gewaehlt"),
                                parent=self.win)
            return ""
        if not ordner_erlaubt and self._ist_ordner(rel):
            messagebox.showinfo(self.t("titlebar.abbild_bearbeiten"), self.t("bearbeiten.keine_datei"),
                                parent=self.win)
            return ""
        return rel

    def _ziel_ordner(self) -> str:
        """Der Ordner, in den hinzugefuegt wird: der gewaehlte Ordner, bei einer Datei ihr Ordner, sonst die Wurzel."""
        rel = self._gewaehlt()
        if not rel:
            return ""
        if self._ist_ordner(rel):
            return rel
        return rel.rsplit("/", 1)[0] if "/" in rel else ""

    # ---- Aenderungen -----------------------------------------------------------------------------------------
    def _aendern(self, aktion: Callable[[], str], auswahl_danach: str = "") -> None:
        try:
            ergebnis = aktion()
        except ab.BearbeitenFehler as exc:
            self._fehler(exc)
            return
        self._baum_fuellen(ergebnis or auswahl_danach)
        self._zustand_setzen()

    def _loeschen(self) -> None:
        if self.direkt is not None:
            return self._direkt_loeschen()
        rel = self._gewaehlt_pruefen()
        if not rel:
            return
        if not messagebox.askyesno(self.t("titlebar.abbild_bearbeiten"),
                                   self.t("bearbeiten.frage_loeschen", name=rel), icon="warning", parent=self.win):
            return
        self._aendern(lambda: (ab.loeschen(self.ordner, rel, protokoll=self.protokoll, melden=self._loescht), "")[1])

    def _loescht(self, rel: str) -> None:
        """Zeigt vor dem Loeschen, was geschieht - ein grosser Ordner braucht Sekunden im Oberflaechenfaden."""
        self._status(self.t("bearbeiten.loescht", name=rel))
        try:
            self.win.update_idletasks()
        except tk.TclError:
            pass

    def _umbenennen(self) -> None:
        if self.direkt is not None:
            return self._direkt_umbenennen()
        rel = self._gewaehlt_pruefen()
        if not rel:
            return
        alt = rel.rsplit("/", 1)[-1]
        neu = simpledialog.askstring(self.t("titlebar.abbild_bearbeiten"),
                                     self.t("bearbeiten.frage_umbenennen", name=alt),
                                     initialvalue=alt, parent=self.win)
        if neu is None or neu == alt:
            return
        self._aendern(lambda: ab.umbenennen(self.ordner, rel, neu, protokoll=self.protokoll))

    def _ersetzen(self) -> None:
        if self.direkt is not None:
            return self._direkt_ersetzen()
        rel = self._gewaehlt_pruefen(ordner_erlaubt=False)
        if not rel:
            return
        quelle = filedialog.askopenfilename(parent=self.win, title=self.t("bearbeiten.dateidialog_ersetzen",
                                                                          name=rel.rsplit("/", 1)[-1]))
        if not quelle:
            return
        self._aendern(lambda: (ab.ersetzen(self.ordner, rel, quelle, protokoll=self.protokoll), rel)[1])

    def _hinzufuegen(self) -> None:
        if self.direkt is not None:
            return self._direkt_hinzufuegen()
        if not self._gewaehlt():
            messagebox.showinfo(self.t("titlebar.abbild_bearbeiten"), self.t("bearbeiten.nichts_gewaehlt"),
                                parent=self.win)
            return
        ziel = self._ziel_ordner()
        quellen = filedialog.askopenfilenames(parent=self.win, title=self.t("bearbeiten.dateidialog_hinzufuegen",
                                                                            ordner=ziel or "/"))
        if not quellen:
            return
        neu = ""
        for quelle in quellen:
            try:
                neu = ab.hinzufuegen(self.ordner, ziel, quelle, protokoll=self.protokoll)
            except ab.BearbeitenFehler as exc:
                self._fehler(exc)
                break
        self._baum_fuellen(neu)
        self._zustand_setzen()

    def _neuer_ordner(self) -> None:
        if self.direkt is not None:
            return self._direkt_neuer_ordner()
        if not self._gewaehlt():
            messagebox.showinfo(self.t("titlebar.abbild_bearbeiten"), self.t("bearbeiten.nichts_gewaehlt"),
                                parent=self.win)
            return
        ziel = self._ziel_ordner()
        name = simpledialog.askstring(self.t("titlebar.abbild_bearbeiten"),
                                      self.t("bearbeiten.frage_neu_name"), parent=self.win)
        if not name:
            return
        self._aendern(lambda: ab.ordner_anlegen(self.ordner, ziel, name, protokoll=self.protokoll))

    # ---- Abbild entpacken und speichern ----------------------------------------------------------------------
    def _abbild_waehlen(self) -> None:
        pfad = filedialog.askopenfilename(
            parent=self.win, title=self.t("bearbeiten.dateidialog_abbild"),
            initialdir=os.path.dirname(self.bild_var.get()) if self.bild_var.get() else None,
            filetypes=[(self.t("bearbeiten.filetype_abbild"), "*.ffpfsc *.ffpfs *.exfat *.ffpkg"),
                       (self.t("filetype.all_files"), "*.*")])
        if pfad:
            self.bild_var.set(os.path.normpath(pfad))

    def _arbeitsordner_leeren(self) -> None:
        if self.arbeit and os.path.isdir(self.arbeit):
            ordner_entfernen(self.arbeit)
        self.arbeit = self.ordner = ""

    def _entpacken(self) -> None:
        bild = self.bild_var.get().strip()
        if not bild or not os.path.isfile(bild) or not format_der_datei(bild):
            messagebox.showwarning(self.t("titlebar.abbild_bearbeiten"), self.t("bearbeiten.kein_abbild"),
                                   parent=self.win)
            return
        if self._hat_ungespeichertes() and not messagebox.askyesno(
                self.t("titlebar.abbild_bearbeiten"), self.t("bearbeiten.frage_verwerfen"),
                icon="warning", parent=self.win):
            return
        self._direkt_schliessen()
        self._arbeitsordner_leeren()
        self.protokoll = ab.Protokoll()
        self.gespeichert_bei = 0
        self._baum_fuellen()
        try:
            self.arbeit = tempfile.mkdtemp(prefix="ps5conv_bearbeiten_", dir=self.g._get_runtime_temp_dir())
        except OSError as exc:
            messagebox.showerror(self.t("titlebar.abbild_bearbeiten"), str(exc), parent=self.win)
            return
        self.bild = os.path.normpath(bild)
        self.format_var.set(os.path.splitext(bild)[1].lower())
        self.beschaeftigt = True
        self._zustand_setzen()
        self._status(self.t("bearbeiten.status_entpackt_laeuft"))
        if not aufgabe_starten(self.g, self.bild, self.arbeit, "folder", self._entpackt):
            self._abgelehnt()

    def _abgelehnt(self) -> None:
        """Die Aufgabe lief nicht an (andere Aufgabe aktiv, Pruefung oder Rueckfrage abgelehnt)."""
        self.beschaeftigt = False
        self._arbeitsordner_leeren()
        self._zustand_setzen()
        self._status(self.t("bearbeiten.nicht_gestartet"))

    def _entpackt(self, ok: bool, ausgabe: str) -> None:
        if not self.g._fenster_lebt(self.win):
            return
        self.beschaeftigt = False
        spiel = ausgabe if ausgabe and os.path.isdir(ausgabe) else ""
        if not spiel and self.arbeit:
            unter = [e.path for e in os.scandir(self.arbeit) if e.is_dir()]
            spiel = unter[0] if len(unter) == 1 else ""
        if not ok or not spiel:
            self._arbeitsordner_leeren()
            self._zustand_setzen()
            self._status(self.t("bearbeiten.entpacken_fehlgeschlagen"))
            messagebox.showerror(self.t("titlebar.abbild_bearbeiten"), self.t("bearbeiten.entpacken_fehlgeschlagen"),
                                 parent=self.win)
            return
        stem = os.path.splitext(os.path.basename(self.bild))[0]
        ziel = os.path.join(self.arbeit, stem + ZUSATZ)
        try:
            if os.path.normcase(spiel) != os.path.normcase(ziel):
                os.rename(spiel, ziel)
            spiel = ziel
        except OSError as exc:
            logger.debug("Spielordner nicht umbenannt: %s", exc)
        self.ordner = spiel
        self._baum_fuellen()
        self._zustand_setzen()

    def _speichern(self) -> None:
        if self.direkt is not None:
            return self._direkt_anwenden()
        if not self.ordner or not os.path.isdir(self.ordner):
            return
        endung = self.format_var.get() or os.path.splitext(self.bild)[1].lower()
        zielformat = FORMATE.get(endung, "")
        if not zielformat:
            return
        fehlt = ab.spiel_pruefen(self.ordner)
        if fehlt and not messagebox.askyesno(
                self.t("titlebar.abbild_bearbeiten"),
                self.t("bearbeiten.frage_unvollstaendig", fehlt=", ".join(fehlt)), icon="warning", parent=self.win):
            return
        zielordner = filedialog.askdirectory(
            parent=self.win, title=self.t("bearbeiten.dateidialog_ziel"),
            initialdir=os.path.dirname(self.bild) if self.bild else None, mustexist=True)
        if not zielordner:
            return
        zielordner = os.path.normpath(zielordner)
        self.beschaeftigt = True
        self._zustand_setzen()
        self._status(self.t("bearbeiten.status_speichert"))
        stand = self.protokoll.anzahl()

        def _fertig(ok: bool, ausgabe: str) -> None:
            if not self.g._fenster_lebt(self.win):
                return
            self.beschaeftigt = False
            if ok:
                self.gespeichert_bei = stand
            self._zustand_setzen()
            if ok:
                text = self.t("bearbeiten.gespeichert", pfad=ausgabe or zielordner)
                self._status(text)
                messagebox.showinfo(self.t("titlebar.abbild_bearbeiten"), text, parent=self.win)
            else:
                self._status(self.t("bearbeiten.speichern_fehlgeschlagen"))
                messagebox.showerror(self.t("titlebar.abbild_bearbeiten"),
                                     self.t("bearbeiten.speichern_fehlgeschlagen"), parent=self.win)

        if not aufgabe_starten(self.g, self.ordner, zielordner, zielformat, _fertig):
            self.beschaeftigt = False
            self._zustand_setzen()
            self._status(self.t("bearbeiten.nicht_gestartet"))

    # ---- Direkt im Abbild (.exfat) ---------------------------------------------------------------------------
    def _direkt_schliessen(self) -> None:
        """Gibt die Abbilddatei frei (nicht geschriebene Aenderungen verfallen)."""
        if self.direkt is not None:
            try:
                self.direkt.schliessen()
            except Exception as exc:  # noqa: BLE001 - ein Griff, der sich nicht schliessen laesst, haelt das Fenster nicht auf
                logger.debug("Abbild nicht geschlossen: %s", exc)
        self.direkt = None
        self.direkt_offen = 0
        self.direkt_ordner = set()

    def _direkt_oeffnen(self) -> None:
        bild = self.bild_var.get().strip()
        if not bild or not os.path.isfile(bild) or not bild.lower().endswith(".exfat"):
            messagebox.showwarning(self.t("titlebar.abbild_bearbeiten"), self.t("bearbeiten.direkt_nur_exfat"), parent=self.win)
            return
        if self._hat_ungespeichertes() and not messagebox.askyesno(
                self.t("titlebar.abbild_bearbeiten"), self.t("bearbeiten.frage_verwerfen"), icon="warning", parent=self.win):
            return
        if not messagebox.askyesno(self.t("titlebar.abbild_bearbeiten"), self.t("bearbeiten.direkt_frage", pfad=bild),
                                   icon="warning", parent=self.win):
            return
        self._direkt_schliessen()
        self._arbeitsordner_leeren()
        rueckgaengig = os.path.exists(exfat_direkt.journal_pfad(bild))
        try:
            self.direkt = exfat_direkt.ExfatAbbild(bild)
        except (exfat_direkt.ExfatBearbeitenFehler, OSError) as exc:
            messagebox.showerror(self.t("titlebar.abbild_bearbeiten"), self.t("bearbeiten.direkt_fehler", fehler=exc), parent=self.win)
            return
        self.bild = os.path.normpath(bild)
        self.protokoll = ab.Protokoll()
        self.gespeichert_bei = 0
        self.direkt_offen = 0
        self.format_var.set(".exfat")
        self._baum_fuellen()
        if rueckgaengig:
            self._status(self.t("bearbeiten.direkt_rueckgaengig") + " " + self.baum_status)
        self._zustand_setzen()

    def _direkt_baum_fuellen(self, auswahl: str = "") -> None:
        eintraege: "list[tuple[str, bool, int]]" = []

        def gehen(rel: str) -> None:
            for name, ist_ordner, groesse in self.direkt.auflisten(rel):
                pfad = (rel + "/" + name) if rel else name
                eintraege.append((pfad, ist_ordner, groesse))
                if ist_ordner:
                    gehen(pfad)

        gehen("")
        self.direkt_ordner = {p for p, ist_ordner, _g in eintraege if ist_ordner}
        for pfad, ist_ordner, groesse in eintraege:
            eltern = pfad.rsplit("/", 1)[0] if "/" in pfad else ""
            self.baum.insert(eltern, "end", iid=pfad, text=pfad.rsplit("/", 1)[-1],
                             values=("" if ist_ordner else self.g._fmt_bytes(groesse),), open=(eltern == ""))
        if auswahl and self.baum.exists(auswahl):
            self.baum.selection_set(auswahl)
            self.baum.see(auswahl)
        frei = self.direkt.freie_cluster() * self.direkt.cluster_groesse
        self.baum_status = self.t("bearbeiten.direkt_status", n=len(eintraege), frei=self.g._fmt_bytes(frei))
        self._status(self.baum_status)

    def _direkt_aendern(self, aktion: Callable[[], object], auswahl_danach: str = "") -> bool:
        """Fuehrt eine Aenderung im Abbild aus (im Speicher geplant, geschrieben wird mit "Anwenden"). ``False``, wenn sie abgelehnt wurde."""
        try:
            aktion()
            ok = True
        except exfat_direkt.PlatzFehlt as exc:
            ok = False
            messagebox.showerror(self.t("titlebar.abbild_bearbeiten"), self.t("bearbeiten.direkt_platz", detail=exc), parent=self.win)
        except (exfat_direkt.ExfatBearbeitenFehler, OSError) as exc:
            ok = False
            messagebox.showerror(self.t("titlebar.abbild_bearbeiten"), self.t("bearbeiten.direkt_fehler", fehler=exc), parent=self.win)
        if ok:
            self.direkt_offen += 1
        self._baum_fuellen(auswahl_danach)
        self._zustand_setzen()
        return ok

    def _direkt_loeschen(self) -> None:
        rel = self._gewaehlt_pruefen()
        if not rel:
            return
        if not messagebox.askyesno(self.t("titlebar.abbild_bearbeiten"), self.t("bearbeiten.frage_loeschen", name=rel),
                                   icon="warning", parent=self.win):
            return
        self._direkt_aendern(lambda: self.direkt.loeschen(rel))

    def _direkt_umbenennen(self) -> None:
        rel = self._gewaehlt_pruefen()
        if not rel:
            return
        alt = rel.rsplit("/", 1)[-1]
        neu = simpledialog.askstring(self.t("titlebar.abbild_bearbeiten"), self.t("bearbeiten.frage_umbenennen", name=alt),
                                     initialvalue=alt, parent=self.win)
        if neu is None or neu == alt:
            return
        eltern = rel.rsplit("/", 1)[0] if "/" in rel else ""
        self._direkt_aendern(lambda: self.direkt.umbenennen(rel, neu), (eltern + "/" if eltern else "") + neu)

    def _direkt_ersetzen(self) -> None:
        rel = self._gewaehlt_pruefen(ordner_erlaubt=False)
        if not rel:
            return
        quelle = filedialog.askopenfilename(parent=self.win, title=self.t("bearbeiten.dateidialog_ersetzen",
                                                                          name=rel.rsplit("/", 1)[-1]))
        if quelle:
            self._direkt_aendern(lambda: self.direkt.ersetzen(rel, quelle), rel)

    def _direkt_hinzufuegen(self) -> None:
        if not self._gewaehlt():
            messagebox.showinfo(self.t("titlebar.abbild_bearbeiten"), self.t("bearbeiten.nichts_gewaehlt"), parent=self.win)
            return
        ziel = self._ziel_ordner()
        quellen = filedialog.askopenfilenames(parent=self.win, title=self.t("bearbeiten.dateidialog_hinzufuegen", ordner=ziel or "/"))
        for quelle in quellen or ():
            pfad = (ziel + "/" if ziel else "") + os.path.basename(quelle)
            if not self._direkt_aendern(lambda q=quelle, p=pfad: self.direkt.hinzufuegen(p, q), pfad):
                break

    def _direkt_neuer_ordner(self) -> None:
        if not self._gewaehlt():
            messagebox.showinfo(self.t("titlebar.abbild_bearbeiten"), self.t("bearbeiten.nichts_gewaehlt"), parent=self.win)
            return
        ziel = self._ziel_ordner()
        name = simpledialog.askstring(self.t("titlebar.abbild_bearbeiten"), self.t("bearbeiten.frage_neu_name"), parent=self.win)
        if name:
            pfad = (ziel + "/" if ziel else "") + name
            self._direkt_aendern(lambda: self.direkt.ordner_anlegen(pfad), pfad)

    def _direkt_anwenden(self) -> None:
        """Schreibt die vorgemerkten Aenderungen ins Abbild (im Hintergrund: Journal, Daten, Eintraege)."""
        if self.direkt is None or not self.direkt_offen:
            return
        self.beschaeftigt = True
        self._zustand_setzen()
        self._status(self.t("bearbeiten.direkt_schreibt"))
        abbild = self.direkt
        ergebnis: "dict[str, BaseException | None]" = {"fehler": None}

        def arbeit() -> None:
            try:
                abbild.speichern()
            except BaseException as exc:  # noqa: BLE001 - jeder Fehler kommt als Meldung in die Oberflaeche
                ergebnis["fehler"] = exc
            self.g._hauptfaden_planen(self._direkt_angewendet_melden(ergebnis))

        threading.Thread(target=arbeit, name="abbild-direkt", daemon=True).start()

    def _direkt_angewendet_melden(self, ergebnis: "dict[str, BaseException | None]") -> Callable[[], None]:
        def melden() -> None:
            if not self.g._fenster_lebt(self.win):
                return
            self.beschaeftigt = False
            fehler = ergebnis["fehler"]
            if fehler is not None:
                self._zustand_setzen()
                messagebox.showerror(self.t("titlebar.abbild_bearbeiten"),
                                     self.t("bearbeiten.direkt_fehler", fehler=fehler), parent=self.win)
                return
            self.direkt_offen = 0
            self._baum_fuellen()
            self._zustand_setzen()
            text = self.t("bearbeiten.direkt_angewendet", pfad=self.bild)
            self._status(text)
            messagebox.showinfo(self.t("titlebar.abbild_bearbeiten"), text, parent=self.win)
        return melden

    # ---- Schliessen ------------------------------------------------------------------------------------------
    def _schliessen(self) -> None:
        if self.beschaeftigt:
            messagebox.showinfo(self.t("titlebar.abbild_bearbeiten"), self.t("bearbeiten.beschaeftigt"),
                                parent=self.win)
            return
        if self._hat_ungespeichertes() and not messagebox.askyesno(
                self.t("titlebar.abbild_bearbeiten"), self.t("bearbeiten.frage_verwerfen"),
                icon="warning", parent=self.win):
            return
        self.win.destroy()

    def _beim_zerstoeren(self, ereignis: Any) -> None:
        if getattr(ereignis, "widget", None) is not self.win:
            return
        self._direkt_schliessen()
        try:
            self._arbeitsordner_leeren()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Arbeitsordner nicht entfernt: %s", exc)


def oeffnen(gui, schrift: str, mono: str, pt: Callable[[int], int]) -> "tk.Toplevel":
    """Baut das Fenster und gibt es zurueck (das Menue oeffnet und schliesst es ueber ``_werkzeugknopf``)."""
    titel = gui._t("titlebar.abbild_bearbeiten")
    win = gui._build_modern_toplevel(titel, 860, 700, min_width=700, min_height=520)
    gui._build_modern_header(win, titel, gui._t("bearbeiten.untertitel"))
    win._bearbeiten = BearbeitenFenster(gui, win, schrift, mono, pt)     # haelt das Objekt am Leben
    return win
