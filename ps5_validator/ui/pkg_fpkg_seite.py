# -*- coding: utf-8 -*-
"""Aufgabe 7 "PKG / FPKG" als Seite im rechten Bereich der Ansicht UMWANDELN (seit 12.10.2026).

Bis zum 12.10.2026 abends war das nur ein Platzhalter. Danach zeigte die Seite oben zwei Knoepfe, **PKG** und **FPKG**,
darunter eine von zwei eingebetteten Seiten. Seit dem 30.10.2026 (Nutzerwunsch: "so, dass alle Aufgaben 1-8 im rechten
Fenster etwa aehnlich aussehen") gleicht die Seite den Aufgaben 1 bis 6: Ueberschrift, Untertitel, **ein** Quellfeld
(QUELLE: Datei waehlen, Ordner waehlen, Ablegen) - und der Bereich darunter richtet sich nach der Quelle:

* ein **PS4-Paket** oeffnet :mod:`ps5_validator.ui.ps4_dump_image` ("PS4 PKG"),
* ein **PS5-Paket** :mod:`ps5_validator.ui.ps5_pkg_fenster` ("PS5 PKG").

Die Entscheidung trifft :func:`ps5_validator.utils.pkg_plattform.erkennen` am Format der Datei (nicht am Namen); einen
Umschalter gibt es nicht mehr. Vor der ersten Wahl steht der zuletzt benutzte Bereich da (Vorgabe: PS5), damit die Seite
nie leer wirkt.

Beide Module bauen ihr ``self.win`` als ``tk.Frame`` - diese Seite reicht ihnen beim ersten Zeigen ihren Bereichsrahmen
(``self.bereich``) als ``master`` herein und baut sie dadurch direkt an ihren Platz; danach wird nur noch ein- und
ausgeblendet (``pack``/``pack_forget``), kein Neuaufbau. Beide bleiben Singletons (``ps4_dump_image.FENSTER_ATTRIBUT`` /
``ps5_pkg_fenster.FENSTER_ATTRIBUT`` auf ``gui``) - die Bibliothek reicht ein umzuwandelndes Paket weiterhin ueber
``PS5ConverterGUI._show_ps4_pkg_converter`` herein.

Gleicher Grundmechanismus wie :mod:`ampr_seite`: eine eigene Flaeche in der Zelle (1, 1), die die Rollflaeche mit
den Aufgabenkarten ersetzt (``PS5ConverterGUI._pkg_fpkg_seite_einblenden``).
"""
from __future__ import annotations

import logging
import os
import sys
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog

from PIL import Image, ImageTk

from ps5_validator.ui import ps4_dump_image
from ps5_validator.ui import ps5_pkg_fenster
from ps5_validator.ui import seitenbild
from ps5_validator.utils import pkg_plattform

logger = logging.getLogger("PS5Converter.ui.pkg_fpkg_seite")

SEITE_ATTRIBUT = "_pkg_fpkg_seite"

UNTERSEITE_PKG = "pkg"
UNTERSEITE_FPKG = "fpkg"

#: Der zuletzt benutzte Bereich (``_load_setting``/``_save_setting``).
EINST_BEREICH = "pkg_fpkg_bereich"


def _haupt(gui):
    """Das Modul des Hauptprogramms (``pt``, Schriften, ``RoundedButton``)."""
    return sys.modules[type(gui).__module__]


class _Bezug:
    """Eine Attrappe mit Breite und Hoehe fuer ``_flaechen_ausschnitt`` (die Flaeche der Seite samt Titelleiste)."""

    def __init__(self, breite: int, hoehe: int) -> None:
        self._b, self._h = int(breite), int(hoehe)

    def winfo_width(self) -> int:
        return self._b

    def winfo_height(self) -> int:
        return self._h


class PkgFpkgSeite:
    """Die Seite: Kopf wie bei den Aufgaben 1 bis 6, ein Quellfeld, darunter der Bereich, den die Quelle verlangt."""

    def __init__(self, gui) -> None:
        self.g = gui
        self.h = _haupt(gui)
        self.t = gui._t
        self.c = gui._COLORS
        self.unterseite = ""
        self._sichtbar: "tk.Frame | None" = None
        self._vorbau_geplant = False
        #: Das Objekt des sichtbaren Bereichs.
        self._aktiv = None
        #: Das Ergebnis der letzten Erkennung (``pkg_plattform.Erkennung``) - ``None`` vor der ersten Wahl.
        self.erkennung: "pkg_plattform.Erkennung | None" = None
        #: Beschriftungen direkt auf dem Hauptbild (Ueberschrift, Untertitel): ihr Grund ist der Bildausschnitt.
        self._auf_bild: "list[tk.Label]" = []
        self._grund_foto = None
        self._nachziehen_nach: "str | None" = None
        #: Ob schon ein Paket gewaehlt und erkannt wurde - erst dann nennt der Untertitel den Bereich (31.10.2026).
        self._gewaehlt = False
        self._bauen()

    # ------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------
    #: Seitenrand links und rechts - wie der Inhalt der Aufgaben 1 bis 6 (``content_area``: 40 px).
    _RAND = 40

    def _bauen(self) -> None:
        g, h, c = self.g, self.h, self.c
        F, pt = h.UI_SCHRIFT, h.pt
        self.rahmen = tk.Frame(g.root, bg=c["bg_main"])
        # Wer auf dieser Seite steht (Pillen, Haken, runde Karten), holt sich den Bildausschnitt hinter sich hier.
        self.rahmen._seitenbild = self.bild_hinter
        self.bild = seitenbild.Seitenbild(g, self.rahmen, self.bild_hinter)
        # Das Hauptbild liegt unter allem: dasselbe Bild in derselben Lage wie hinter den Aufgaben 1 bis 6.
        self._grund = tk.Label(self.rahmen, bg=c["bg_main"], bd=0, highlightthickness=0, padx=0, pady=0)
        self._grund._sb_eigen = True
        self._grund.place(x=0, y=0, relwidth=1.0, relheight=1.0)

        # Kopf und Flaeche liegen als einzelne Teile im Raster der Seite, nicht in Zwischenrahmen: Ein Rahmen waere
        # eine einfarbige Flaeche und deckte das Hauptbild zu.
        self.rahmen.columnconfigure(0, weight=1)
        self.rahmen.rowconfigure(2, weight=1)
        self._titel = self._beschriftung(self.rahmen, self.t("mode.pkg_fpkg"), (F, pt(22), "bold"), c["fg_accent"])
        # Abstaende und Schrift wie ``header_label``/``subtitle_label`` der Aufgabe 1 (gemessen: Titel y 38, Untertitel
        # y 93, Karte y 146 bei 1920 px Fensterbreite; die Seite beginnt 32 px unter der Titelleiste).
        self._titel.grid(row=0, column=0, sticky="w", padx=self._RAND, pady=(6, 5))
        self._untertitel = self._beschriftung(self.rahmen, "", (F, pt(10)), c["fg_secondary"])
        self._untertitel.grid(row=1, column=0, sticky="w", padx=self._RAND, pady=(0, 30))

        # Der Inhalt ist ein Rahmen ohne eigene Farbe (``Seitenbild`` legt ihm den Bildausschnitt unter). Die Karte wie bei
        # den Aufgaben 1 bis 6 (getoent, runde Ecken, mit Quelle und Einstellungen darin) baut jeder Bereich in seiner
        # Rollflaeche selbst (``karte_bauen``) - sie rollt mit dem Inhalt.
        self.inhalt = tk.Frame(self.rahmen, bg=c["bg_main"])
        self.inhalt.grid(row=2, column=0, sticky="nsew", padx=(self._RAND - self._BEREICH_RAND,
                                                              self._RAND - self._BEREICH_RAND - self._ROLLLEISTE),
                         pady=(0, 10))
        #: Die Quellfelder der Bereiche (je eines in der Karte jedes Bereichs), nach Kennung.
        self._quellsaetze: "dict[str, dict]" = {}
        self.quelle_var = tk.StringVar(value="")
        self._hinweis_text = self.t("pkg_fpkg_seite.source_hint")
        self._hinweis_farbe = c["fg_secondary"]
        # Hier stehen die beiden Bereiche (PS4 PKG / PS5 PKG), einer sichtbar.
        self.bereich = tk.Frame(self.inhalt, bg=c["bg_main"])
        self.bereich.pack(fill="both", expand=True)
        self.rahmen.bind("<Configure>", lambda _e: self._nachziehen_planen(), add="+")
        self._untertitel_aktualisieren()

    #: Linker Rand der Bereiche in ``bereich`` (die Karte steht dort x Pixel weiter rechts als der Seitenrand).
    _BEREICH_RAND = 14
    #: Was rechts von der Karte fehlt: die Rollleiste des Bereichs steht in seiner Flaeche, bei Aufgabe 1 daneben.
    _ROLLLEISTE = 8

    def quelle_zeile_bauen(self, eltern, kennung: str = "") -> tk.Frame:
        """QUELLE in der Karte eines Bereichs: Beschriftung, rundes Feld mit den Waehl-Knoepfen rechts, Hinweis darunter.

        Jeder Bereich baut seine Karte in seiner eigenen Rollflaeche und ruft dies fuer seine Quelle auf (``kennung`` =
        ``UNTERSEITE_PKG``/``UNTERSEITE_FPKG``); alle Felder teilen sich ``quelle_var`` und den Hinweistext.
        Zurueck kommt der Rahmen - platzieren muss ihn der Aufrufer.
        """
        g, h, c = self.g, self.h, self.c
        t = self.t
        F, pt = h.UI_SCHRIFT, h.pt
        pw = g._pw
        zeile = tk.Frame(eltern, bg=c["bg_main"])
        tk.Label(zeile, text=t("ps4pkg.source_label").upper(), font=(F, pt(9), "bold"), bg=c["bg_main"],
                 fg=c["fg_primary"], anchor="w").pack(fill="x", pady=(0, 5))
        feld_zeile = tk.Frame(zeile, bg=c["bg_main"])
        feld_zeile.pack(fill="x")
        feld = pw.Entry(feld_zeile, textvariable=self.quelle_var, font=(F, pt(12)))
        feld.pack(side="left", fill="x", expand=True, ipady=3)
        datei = pw.Button(feld_zeile, text=t("ps5pkg.choose_file"), command=self._datei_waehlen, hoehe=36, fett=True)
        datei.pack(side="left", padx=(8, 0))
        ordner = pw.Button(feld_zeile, text=t("ps5pkg.choose_folder"), command=self._ordner_waehlen, hoehe=36, fett=True)
        ordner.pack(side="left", padx=(8, 0))
        feld.bind("<Return>", lambda _e: self._quelle_eingegeben(), add="+")
        hinweis = tk.Label(zeile, text=self._hinweis_text, font=(F, pt(9)), bg=c["bg_main"],
                           fg=self._hinweis_farbe, anchor="w", justify="left", wraplength=560)
        hinweis.pack(fill="x", pady=(5, 0))
        # Der Umbruch folgt der Breite der Zeile, nicht des Labels selbst (das hat die Groesse seines Textes).
        zeile.bind("<Configure>", lambda e: hinweis.configure(wraplength=max(160, e.width - 4)), add="+")
        dnd = getattr(self.h, "DND_FILES", None)
        if dnd:
            self.bild.dnd_weitergeben(zeile, dnd, self._abgelegt)
            for ziel in (feld, zeile):
                try:
                    ziel.drop_target_register(dnd)
                    ziel.dnd_bind("<<Drop>>", self._abgelegt)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Ablegen nicht verfuegbar: %s", exc)
        self._quellsaetze[kennung] = {"zeile": zeile, "feld": feld, "hinweis": hinweis, "datei": datei, "ordner": ordner}
        return zeile

    def _satz(self) -> "dict | None":
        """Das Quellfeld des sichtbaren Bereichs (sonst eines der vorhandenen)."""
        kennung = self.unterseite or self._letzter_bereich()
        satz = self._quellsaetze.get(kennung)
        if satz is None and self._quellsaetze:
            satz = next(iter(self._quellsaetze.values()))
        return satz

    @property
    def quelle_feld(self):
        satz = self._satz()
        return satz["feld"] if satz else None

    @property
    def _quelle_zeile(self):
        satz = self._satz()
        return satz["zeile"] if satz else None

    @property
    def _hinweis(self):
        satz = self._satz()
        return satz["hinweis"] if satz else None

    def karte_bauen(self, eltern, **optionen) -> "tuple[tk.Frame, tk.Frame]":
        """Die Karte eines Bereichs wie ``path_card`` der Aufgabe 1: getoentes Bild, runde Ecken, 30 px Polster.

        Liefert ``(karte, innen)``; die Felder gehoeren in ``innen``. ``Seitenbild`` legt der Karte ihr Bild unter
        (``bild_karte``), und alles darin steht auf diesem getoenten Ausschnitt statt auf dem reinen Hauptbild.
        """
        c = self.c
        karte = tk.Frame(eltern, bg=c["bg_card"], **optionen)
        karte._sb_karte = True
        karte._sb_bild = self.bild_karte
        innen = tk.Frame(karte, bg=c["bg_card"])
        innen.pack(fill="both", expand=True, padx=30, pady=30)
        return karte, innen

    # ------------------------------------------------------------------
    # Hauptbild
    # ------------------------------------------------------------------
    def _ausschnitt(self, widget, breite: int, hoehe: int, versatz: tuple, roh: bool):
        """Der Ausschnitt des Hauptbilds (``roh``: des ungetoenten, aus dem die Karten ihr Bild mischen) hinter ``widget``."""
        g = self.g
        quelle = getattr(g, "_bg_image_raw" if roh else "_bg_image_cache", None)
        if quelle is None or breite <= 1 or hoehe <= 1:
            return None
        try:
            b, hoch = int(self.rahmen.winfo_width()), int(self.rahmen.winfo_height())
            if b <= 1 or hoch <= 1:
                return None
            leiste = int(g._titelleiste_hoehe())
            x0 = widget.winfo_rootx() - self.rahmen.winfo_rootx() + int(versatz[0])
            y0 = widget.winfo_rooty() - self.rahmen.winfo_rooty() + leiste + int(versatz[1])
            voll = g._flaechenbild(quelle, b, hoch + leiste)
            if voll is None:
                return None
            # Ein Teil darf ueber die Seite hinausragen (ein Rollinhalt, der weiter rollt als sichtbar): Es bekommt
            # sein Stueck des Bildes an der richtigen Stelle - ohne es zu dehnen.
            breite, hoehe = int(breite), int(hoehe)
            ziel = Image.new("RGB", (breite, hoehe), (0, 0, 0))
            box = (max(0, x0), max(0, y0), min(b, x0 + breite), min(hoch + leiste, y0 + hoehe))
            if box[2] > box[0] and box[3] > box[1]:
                ziel.paste(voll.crop(box).convert("RGB"), (box[0] - x0, box[1] - y0))
            return ziel
        except (tk.TclError, AttributeError, ValueError):
            return None

    def _in_karte(self, widget) -> bool:
        """Liegt ``widget`` (oder es selbst) in einer Karte (``karte_bauen``)?"""
        knoten = widget
        for _ in range(40):
            if knoten is None or knoten is self.rahmen:
                return False
            if getattr(knoten, "_sb_karte", False):
                return True
            knoten = getattr(knoten, "master", None)
        return False

    def bild_hinter(self, widget, breite: int, hoehe: int, versatz: tuple = (0, 0)):
        """Der Ausschnitt des Hauptbilds, der an der Stelle von ``widget`` liegt - oder ``None`` ohne Hauptbild.

        Gerechnet wie bei der Inhaltsflaeche der Aufgaben (``_compute_content_bg_crop``), nur gegen diese Seite: Das Bild
        reicht ueber die Zelle samt der Titelleiste, die Seite beginnt darunter. Steht ``widget`` in einer Karte, ist es
        der Ausschnitt der Karte (``_blend_bg_image_for_card`` - wie ``_compute_card_bg_image`` der Aufgabe 1).
        """
        if self._in_karte(widget):
            roh = self._ausschnitt(widget, breite, hoehe, versatz, True)
            if roh is not None:
                try:
                    return self.g._blend_bg_image_for_card(roh)
                except Exception:  # noqa: BLE001
                    logger.debug("Kartenausschnitt nicht berechenbar", exc_info=True)
        return self._ausschnitt(widget, breite, hoehe, versatz, False)

    def bild_karte(self, karte, breite: int, hoehe: int, versatz: tuple = (0, 0)):
        """Das Bild der Karte selbst: der getoente Ausschnitt, in den Ecken (``_KARTEN_ECKE``) das Hauptbild dahinter."""
        g = self.g
        roh = self._ausschnitt(karte, breite, hoehe, versatz, True)
        hinten = self._ausschnitt(karte, breite, hoehe, versatz, False)
        if roh is None or hinten is None:
            return None
        try:
            vorn = g._blend_bg_image_for_card(roh).convert("RGB")
            r = int(g._KARTEN_ECKE)
            breite, hoehe = int(breite), int(hoehe)
            if breite <= 2 * r or hoehe <= 2 * r:
                return vorn
            maske = Image.new("L", (breite, hoehe), 255)
            for ecke, (x, y) in {"ol": (0, 0), "or": (breite - r, 0), "ul": (0, hoehe - r),
                                 "ur": (breite - r, hoehe - r)}.items():
                maske.paste(g._eckmaske(ecke, r), (x, y))
            return Image.composite(vorn, hinten, maske)
        except Exception:  # noqa: BLE001
            logger.debug("Kartenbild nicht berechenbar", exc_info=True)
            return None

    def _beschriftung(self, eltern, text: str, schrift, farbe: str) -> tk.Label:
        """Ein Text direkt auf dem Hauptbild: ein Label ohne Kasten, dessen Bild der Ausschnitt dahinter ist."""
        c = self.c
        label = tk.Label(eltern, text=text, font=schrift, fg=farbe, bg=c["bg_main"], bd=0, highlightthickness=0,
                         padx=0, pady=0, anchor="w", compound="center")
        label._sb_eigen = True
        self._auf_bild.append(label)
        # Erst wenn das Label abgebildet ist, steht seine Lage fest: Dann bekommt es seinen Bildausschnitt.
        label.bind("<Map>", lambda _e: self._nachziehen_planen(), add="+")
        return label

    def _beschriftung_setzen(self, label: tk.Label, text: str) -> None:
        if str(label.cget("text")) != text:
            label.configure(text=text, image="")
            label._natuerlich = None

    def _natuerliche_groesse(self, label: tk.Label) -> "tuple[int, int]":
        gemerkt = getattr(label, "_natuerlich", None)
        if gemerkt is None:
            schrift = tkfont.Font(root=label, font=label.cget("font"))
            gemerkt = (max(2, int(schrift.measure(str(label.cget("text"))))),
                       max(2, int(schrift.metrics("linespace"))))
            label._natuerlich = gemerkt
        return gemerkt

    def _nachziehen_planen(self) -> None:
        if self._nachziehen_nach is not None:
            return
        try:
            self._nachziehen_nach = self.rahmen.after_idle(self._nachziehen)
        except tk.TclError:
            self._nachziehen_nach = None

    def _nachziehen(self) -> None:
        """Malt das Hauptbild und die Beschriftungen darauf neu - nach Groessen- oder Lageaenderung."""
        self._nachziehen_nach = None
        self.bild.planen()
        try:
            if not self.rahmen.winfo_exists():
                return
            b, hoch = int(self.rahmen.winfo_width()), int(self.rahmen.winfo_height())
            if b <= 1 or hoch <= 1:
                return
            quelle = getattr(self.g, "_bg_image_cache", None)
            if quelle is None:
                self._grund_foto = None
                self._grund.configure(image="")
            else:
                leiste = int(self.g._titelleiste_hoehe())
                voll = self.g._flaechenbild(quelle, b, hoch + leiste)
                if voll is not None:
                    self._grund_foto = ImageTk.PhotoImage(voll.crop((0, leiste, b, leiste + hoch)), master=self.g.root)
                    self._grund.configure(image=self._grund_foto)
            for label in self._auf_bild:
                if not label.winfo_exists() or not label.winfo_ismapped():
                    continue
                w, hh = self._natuerliche_groesse(label)
                ausschnitt = self.bild_hinter(label, w, hh)
                if ausschnitt is None:
                    label.configure(image="")
                    continue
                foto = ImageTk.PhotoImage(ausschnitt, master=self.g.root)
                label._bild_foto = foto
                label.configure(image=foto)
        except tk.TclError:
            pass

    def _untertitel_aktualisieren(self) -> None:
        """Der Untertitel nennt den Bereich erst, wenn ein Paket gewaehlt und erkannt wurde (Nutzerwunsch 31.10.2026).

        Vorher steht ein geschuetztes Leerzeichen da, damit die Zeile ihre Hoehe behaelt und nichts springt. Der Bereich
        selbst (zuletzt benutzt, Vorgabe PS5) bleibt die Grundlage der Seite.
        """
        if self._gewaehlt:
            kennung = self.unterseite or self._letzter_bereich()
            text = self.t("main.config_for", task=self._bereich_text(kennung))
        else:
            text = "\u00a0"
        self._beschriftung_setzen(self._untertitel, text)
        self._nachziehen_planen()

    def _bereich_text(self, kennung: str) -> str:
        return self.t("pkg_fpkg_seite.tab_pkg" if kennung == UNTERSEITE_PKG else "pkg_fpkg_seite.tab_fpkg")

    def _letzter_bereich(self) -> str:
        """Der zuletzt benutzte Bereich - Vorgabe PS5."""
        try:
            wert = str(self.g._load_setting(EINST_BEREICH, UNTERSEITE_FPKG) or UNTERSEITE_FPKG)
        except Exception:  # noqa: BLE001
            wert = UNTERSEITE_FPKG
        return wert if wert in (UNTERSEITE_PKG, UNTERSEITE_FPKG) else UNTERSEITE_FPKG

    def _bereich_merken(self, kennung: str) -> None:
        try:
            self.g._save_setting(EINST_BEREICH, kennung)
        except Exception:  # noqa: BLE001
            logger.debug("Bereich nicht gespeichert", exc_info=True)

    # ------------------------------------------------------------------
    # Quelle waehlen und erkennen
    # ------------------------------------------------------------------
    def _datei_waehlen(self) -> None:
        pfade = filedialog.askopenfilenames(
            parent=self.rahmen, title=self.t("pkg_fpkg_seite.choose_files"),
            filetypes=[("PKG", "*.pkg"), (self.t("filetype.all_files"), "*.*")])
        if pfade:
            self.quelle_waehlen([os.path.normpath(p) for p in pfade])

    def _ordner_waehlen(self) -> None:
        ordner = filedialog.askdirectory(parent=self.rahmen, title=self.t("pkg_fpkg_seite.choose_folder"),
                                         initialdir=self._startordner() or None)
        if ordner:
            self.quelle_waehlen([os.path.normpath(ordner)])

    def _startordner(self) -> str:
        try:
            return str(self.g._get_source_dialog_initial_dir() or "")
        except Exception:  # noqa: BLE001
            return ""

    def _abgelegt(self, ereignis) -> None:
        try:
            pfade = [os.path.normpath(p) for p in self.rahmen.tk.splitlist(ereignis.data)]
        except tk.TclError:
            return
        if pfade:
            self.quelle_waehlen(pfade)

    def _quelle_eingegeben(self) -> None:
        """Ein von Hand getippter oder eingefuegter Pfad (mehrere mit ``os.pathsep`` getrennt)."""
        pfade = [os.path.normpath(p.strip().strip('"')) for p in self.quelle_var.get().split(os.pathsep) if p.strip()]
        if pfade:
            self.quelle_waehlen(pfade)

    def _hinweis_setzen(self, text: str, fehler: bool = False) -> None:
        c = self.c
        self._hinweis_text = text
        self._hinweis_farbe = c.get("fg_error", "#ff6b6b") if fehler else c["fg_secondary"]
        for satz in self._quellsaetze.values():
            try:
                satz["hinweis"].configure(text=self._hinweis_text, fg=self._hinweis_farbe)
            except tk.TclError:
                pass

    def _meldung_in_bereich(self, text: str) -> None:
        """Dieselbe Meldung auch ins Protokoll des gerade sichtbaren Bereichs - eine Fehlwahl bleibt nicht stumm."""
        aktiv = self._aktiv
        if aktiv is None:
            return
        try:
            aktiv._protokoll(text)
        except Exception:  # noqa: BLE001
            logger.debug("Meldung nicht ins Protokoll geschrieben", exc_info=True)

    def quelle_waehlen(self, pfade: "list[str]") -> "pkg_plattform.Erkennung":
        """Die gewaehlte Quelle gilt: erkennen, den passenden Bereich zeigen und ihm die Quelle geben.

        Nichts Erkennbares (keine bekannte Paketkennung, ein Ordner ohne Spiel und ohne ``.pkg``): eine klare Meldung,
        Bereich und Feld bleiben unveraendert.
        """
        t = self.t
        erg = pkg_plattform.erkennen(pfade)
        self.erkennung = erg
        if erg.plattform is None:
            ordner = any(os.path.isdir(p) for p in pfade)
            grund = t("pkg_fpkg_seite.reason_nothing" if ordner else "pkg_fpkg_seite.reason_magic")
            meldung = t("pkg_fpkg_seite.invalid", grund=grund)
            self._hinweis_setzen(meldung, fehler=True)
            self._meldung_in_bereich(meldung)
            return erg
        self.quelle_var.set(os.pathsep.join(pfade))
        self._gewaehlt = True
        if erg.gemischt:
            text = t("pkg_fpkg_seite.mixed", ps4=erg.anzahl_ps4, ps5=erg.anzahl_ps5)
        else:
            kennung = UNTERSEITE_PKG if erg.plattform == pkg_plattform.PS4 else UNTERSEITE_FPKG
            text = t("pkg_fpkg_seite.detected", art=self._bereich_text(kennung), grund=erg.grund)
        self._hinweis_setzen(text)
        if erg.plattform == pkg_plattform.PS4:
            fenster = self.pkg_zeigen()
            fenster.quelle_von_seite(erg.art, pfade)
        else:
            fenster = self.fpkg_zeigen()
            fenster._pakete_hinzufuegen(pfade, waehlen=True)
        if erg.gemischt:
            self._meldung_in_bereich(text)
        return erg

    # ------------------------------------------------------------------
    # Bereiche
    # ------------------------------------------------------------------
    #: Wie oft das Layout eines neu gebauten Bereichs vor dem Zeigen nachgezogen wird. Karten, Rollbereich und
    #: Spalten stellen ihre Breite erst auf ein Groessenereignis ein; meist reichen zwei Durchgaenge.
    _VORLEGEN_DURCHGAENGE = 4

    def _bauer(self, kennung: str) -> dict:
        """Was ein Bereich beim Bauen braucht: seine Karte und das Quellfeld darin (siehe ``karte_bauen``)."""
        return {"karte_bauer": self.karte_bauen,
                "quelle_bauer": lambda eltern, _k=kennung: self.quelle_zeile_bauen(eltern, _k)}

    def _vorlegen(self, win: "tk.Frame") -> "tk.Frame | None":
        """Legt einen neu gebauten Bereich an seinem endgueltigen Platz fertig aus, ohne dass man es sieht.

        Gemeldet am 30.10.2026: Beim ersten Klick auf PS5 PKG baute sich die Ansicht sichtbar auf - leere Flaeche,
        ein Geruest mit schmaler Karte, dann die endgueltige Breite und Stueck fuer Stueck der Inhalt. Beim zweiten
        Mal war sie schon geordnet, nichts sprang. Die runden Karten rechnen sich bei jeder Lage neu (sie nehmen den
        Hintergrund an ihrer Stelle auf); der Bereich darf also nicht an anderer Stelle vorbereitet und dann
        verschoben werden. Er steht deshalb gleich an seinem Platz, verdeckt: hinter dem bisherigen Bereich - oder,
        wenn es keinen gibt, unter einer Abdeckung. Zurueck kommt die Abdeckung (oder ``None``); der Aufrufer
        entfernt sie, nachdem der Bereich gepackt ist.
        """
        if getattr(win, "_vorgelegt", False):
            return None
        win._vorgelegt = True
        abdeckung = None
        try:
            # Beim ersten Klick steht die Seite eben erst im Raster: ohne diesen Durchgang waere der Bereich noch 1x1
            # gross, das Vorlegen unterbliebe und alles ordnete sich sichtbar danach (gemessen 31.10.2026: ~1 s).
            self.rahmen.update_idletasks()
            if int(self.bereich.winfo_width()) <= 1 or int(self.bereich.winfo_height()) <= 1:
                return None
            if self._sichtbar is None:
                abdeckung = tk.Frame(self.bereich, bg=self.c["bg_main"])
                abdeckung._sb_eigen = True
                abdeckung.place(x=0, y=0, relwidth=1, relheight=1)
            win.place(in_=self.bereich, x=0, y=0, relwidth=1, relheight=1)
            if abdeckung is not None:
                abdeckung.lift()
            else:
                win.lower()
            with self.bild.ruhen():
                for _ in range(self._VORLEGEN_DURCHGAENGE):
                    win.update_idletasks()
                    self.rahmen.update()
            win.place_forget()
        except tk.TclError:
            try:
                win.place_forget()
            except tk.TclError:
                pass
        return abdeckung

    #: Hoechstzahl der Durchgaenge, mit denen ein frisch gepackter Bereich unter der Abdeckung zur Ruhe kommt.
    _SETZEN_DURCHGAENGE = 8

    def _setzen_lassen(self) -> None:
        """Laesst Layout und Unterlegbilder eines frisch gepackten Bereichs unter der Abdeckung zur Ruhe kommen.

        Gemeldet am 31.10.2026: Der erste Klick auf PKG / FPKG zeigte sekundenlang eine sich neu ordnende Seite -
        jedes Unterlegen verschob Karten, das loeste das naechste aus (gemessen: 27 Durchgaenge in 0,9 s, sichtbar).
        Jetzt laufen sie, bevor die Abdeckung fällt; ein Durchgang ohne Wirkung (unter 3 ms) beendet es.
        """
        try:
            for _ in range(self._SETZEN_DURCHGAENGE):
                self.rahmen.update_idletasks()
                self.rahmen.update()
                t0 = time.perf_counter()
                self.bild.jetzt()
                if time.perf_counter() - t0 < 0.003:
                    break
        except tk.TclError:
            pass

    def _umschalten(self, kennung: str, win: "tk.Frame") -> None:
        abdeckung = self._vorlegen(win) if win.winfo_manager() != "pack" else None
        if self._sichtbar is not None and self._sichtbar is not win:
            self._sichtbar.pack_forget()
        if win.winfo_manager() != "pack":
            win.pack(fill="both", expand=True)
        if abdeckung is not None:
            self._setzen_lassen()
            try:
                abdeckung.destroy()
            except tk.TclError:
                pass
        self._sichtbar = win
        self.unterseite = kennung
        self._bereich_merken(kennung)
        self._untertitel_aktualisieren()

    def _rest_fertig(self, fenster, geaendert: bool) -> None:
        """Wurde der Rest eines Bereichs eben eingeblendet (erste gueltige Wahl), steht er gleich fertig da.

        Ausgelegt und unterlegt wird noch vor dem naechsten Zeichnen, damit nichts aufblitzt oder springt: erst das
        Layout, dann das Hauptbild hinter jedem Teil (``Seitenbild.jetzt`` sonst erst im Leerlauf danach).
        """
        if not geaendert or not self._gewaehlt:
            return
        try:
            with self.bild.ruhen():
                for _ in range(2):
                    fenster.win.update_idletasks()
                    self.rahmen.update()
            self.bild.jetzt()
        except tk.TclError:
            pass

    def pkg_zeigen(self, vorgabe: str = "") -> "ps4_dump_image.Ps4DumpImageFenster":
        """Zeigt "PS4 PKG" (``ps4_dump_image``) - eine Vorgabe (aus der Bibliothek) wird gleich eingelesen."""
        h = self.h
        fenster = ps4_dump_image.oeffnen(self.g, h.UI_SCHRIFT, h.MONO_SCHRIFT, h.pt, vorgabe, master=self.bereich,
                                       **self._bauer(UNTERSEITE_PKG))
        kam_von_fpkg = self.unterseite == UNTERSEITE_FPKG
        self._aktiv = fenster
        if vorgabe:
            self._gewaehlt = True
            self.quelle_var.set(vorgabe)
        geaendert = fenster.rest_zeigen(self._gewaehlt)
        self._umschalten(UNTERSEITE_PKG, fenster.win)
        self._rest_fertig(fenster, geaendert)
        self._nachziehen_planen()
        if kam_von_fpkg:
            # Die Angaben des PS5-Pakets in Seitenleiste und Info-Box gehoeren nicht zu "PS4 PKG".
            ps5_pkg_fenster.spielinfo_zuruecksetzen(self.g)
        fenster.spielinfo_nachziehen()
        self._vorbau_planen()
        return fenster

    #: Wartezeit, bis der andere Bereich im Leerlauf vorgebaut wird (nach dem Zeigen des ersten).
    _VORBAU_NACH_MS = 900

    def _vorbau_planen(self) -> None:
        if not self._vorbau_geplant:
            self._vorbau_geplant = True
            try:
                self.rahmen.after(self._VORBAU_NACH_MS, self._anderen_vorbauen)
            except tk.TclError:
                pass

    def _anderen_vorbauen(self) -> None:
        """Baut den Bereich, der gerade nicht sichtbar ist, im Leerlauf vor."""
        if self.unterseite == UNTERSEITE_PKG:
            self._fpkg_vorbauen()
        else:
            self._pkg_vorbauen()

    def _fpkg_vorbauen(self) -> None:
        """Baut und legt die PS5-Ansicht vor, solange der Anwender den PS4-Bereich liest.

        Gemessen am 30.10.2026: Der erste Wechsel auf PS5 PKG brauchte 0,66 s (Aufbau 0,1 s, erstes Auslegen 0,5 s),
        der zweite 0,08 s. Die Ansicht entsteht jetzt kurz nach dem Zeigen des anderen Bereichs, hinter ihm und
        ungepackt; das Zeigen packt sie nur noch. Ist die Seite dann nicht sichtbar (andere Ansicht) oder die
        PS5-Ansicht schon da, geschieht nichts - das Zeigen baut sie wie bisher.
        """
        try:
            if (not self.rahmen.winfo_exists() or not self.bereich.winfo_ismapped()
                    or getattr(self.g, ps5_pkg_fenster.FENSTER_ATTRIBUT, None) is not None):
                return
            h = self.h
            fenster = ps5_pkg_fenster.oeffnen(self.g, h.UI_SCHRIFT, h.MONO_SCHRIFT, h.pt, "", master=self.bereich,
                                            **self._bauer(UNTERSEITE_FPKG))
            fenster.rest_zeigen(self._gewaehlt)
            self._vorlegen(fenster.win)
        except tk.TclError:
            pass

    def _pkg_vorbauen(self) -> None:
        """Wie :meth:`_fpkg_vorbauen`, fuer den PS4-Bereich."""
        try:
            if (not self.rahmen.winfo_exists() or not self.bereich.winfo_ismapped()
                    or getattr(self.g, ps4_dump_image.FENSTER_ATTRIBUT, None) is not None):
                return
            h = self.h
            fenster = ps4_dump_image.oeffnen(self.g, h.UI_SCHRIFT, h.MONO_SCHRIFT, h.pt, "", master=self.bereich,
                                           **self._bauer(UNTERSEITE_PKG))
            fenster.rest_zeigen(self._gewaehlt)
            self._vorlegen(fenster.win)
        except tk.TclError:
            pass

    def fpkg_zeigen(self, vorgabe: str = "") -> "ps5_pkg_fenster.Ps5PkgFenster":
        """Zeigt "PS5 PKG" (``ps5_pkg_fenster``)."""
        h = self.h
        fenster = ps5_pkg_fenster.oeffnen(self.g, h.UI_SCHRIFT, h.MONO_SCHRIFT, h.pt, vorgabe, master=self.bereich,
                                        **self._bauer(UNTERSEITE_FPKG))
        self._aktiv = fenster
        if vorgabe:
            self._gewaehlt = True
        geaendert = fenster.rest_zeigen(self._gewaehlt)
        self._umschalten(UNTERSEITE_FPKG, fenster.win)
        self._rest_fertig(fenster, geaendert)
        fenster.spielinfo_nachziehen()
        self._nachziehen_planen()
        self._vorbau_planen()
        return fenster


def seite(gui) -> PkgFpkgSeite:
    """Die Seite des Programms - beim ersten Zeigen gebaut."""
    vorhanden = getattr(gui, SEITE_ATTRIBUT, None)
    if vorhanden is None:
        vorhanden = PkgFpkgSeite(gui)
        setattr(gui, SEITE_ATTRIBUT, vorhanden)
    return vorhanden


def zeigen(gui) -> PkgFpkgSeite:
    """Blendet die Seite im rechten Bereich ein. Nur beim allerersten Mal waehlt sie den zuletzt benutzten Bereich
    (Vorgabe PS5) von selbst - ein spaeterer Aufruf (ein erneuter Druck auf "7.") laesst den gewaehlten stehen."""
    s = seite(gui)
    gui._pkg_fpkg_seite_einblenden(s.rahmen)
    if not s.unterseite:
        if s._letzter_bereich() == UNTERSEITE_PKG:
            s.pkg_zeigen()
        else:
            s.fpkg_zeigen()
    return s
