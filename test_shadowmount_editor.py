# -*- coding: utf-8 -*-
"""Der config.ini-Editor darf die Datei der Konsole nie blind ersetzen.

Am 04.09.2026 gefunden: „Auf PS5 schreiben" liess sich druecken, ohne dass je
geladen worden war. Der Rohtext ist bis dahin leer, und der leere Text fuehrte
in den Zweig ``render_flat_ini`` - der baut die Datei aus dem Woerterbuch neu
auf. Wer das Fenster oeffnete, einen Wert aenderte und schrieb, ersetzte damit
die gepflegte ``config.ini`` der Konsole durch die eingebauten Vorgaben: alle
fremden Schluessel weg (``api_port``, ``language``, ``persistent_image_mounts``
…), alle erklaerenden Kommentarzeilen weg.

**Warum kein Test das gemerkt hat:** ``test_ini_config.py`` prueft die reinen
Funktionen ``merge_flat_ini`` und ``render_flat_ini`` - beide taten immer, was
sie sollten. Falsch war die *Zweigwahl* in der Oberflaeche, und die lief in
keiner Pruefung. Hier wird deshalb das echte Fenster geoeffnet und der echte
Knopf gedrueckt; nur die FTP-Gegenstelle ist gestellt.

Drei Wege, alle am 04.09.2026 vorher/nachher gemessen:

===========================  =========================  ======================
Ablauf                       vorher                     nachher
===========================  =========================  ======================
schreiben ohne zu laden      geschrieben, Datei weg     nichts, Warnung
laden, dann schreiben        Kommentare erhalten        unveraendert gut
Ziel gewechselt (550)        geschrieben                nichts, Warnung
===========================  =========================  ======================

Der mittlere Weg stand nie in Frage - er wird mitgeprueft, damit die Behebung
ihn nicht nebenbei zunagelt.
"""
from __future__ import annotations

import os
import sys
import time
import unittest

PROJEKT = os.path.dirname(os.path.abspath(__file__))
if PROJEKT not in sys.path:
    sys.path.insert(0, PROJEKT)

import pruefumgebung

pruefumgebung.umlenken("shadowmount_editor")

import ftplib

try:
    import tkinter as tk
    from tkinter import messagebox

    # Vorhandene Wurzel weiterbenutzen und niemals zerstoeren - siehe die
    # Regeln in test_fensterlayout.py und test_handbuch_knopf.py.
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover
    TK_DA = False
    _WURZEL = None

import PS5ImageConverter_Pro_FINAL_revised as hauptprogramm

#: Eine gepflegte Datei, wie sie auf der Konsole liegt: viel Erklaerung,
#: dazu Schluessel, die der Editor gar nicht fuehrt.
GEPFLEGT = "\r\n".join(
    ["# ShadowMount+ Konfiguration"]
    + ["# erklaerende Zeile %d" % i for i in range(40)]
    + ["api_port=9021", "scanpath=/mnt/usb0", "recursive_scan=1",
       "language=de", "lvd_ufs_sector_size=4096"]
).encode("utf-8")

#: Was der Editor selbst fuehrt - deutlich weniger als oben.
VORGABEN = {"api_port": "9021", "scanpath": "/mnt/usb0",
            "lvd_ufs_sector_size": "4096"}


def _sammle(widget, art):
    """Alle Nachfahren, deren Tk-Klasse auf ``art`` endet."""
    raus = []
    for kind in widget.winfo_children():
        if kind.winfo_class().endswith(art):
            raus.append(kind)
        raus += _sammle(kind, art)
    return raus


@unittest.skipUnless(TK_DA, "Ohne Anzeige laesst sich kein Fenster oeffnen")
class EditorSchreibwegTests(unittest.TestCase):
    """Oeffnet das echte Fenster; nur die Gegenstelle ist gestellt."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = hauptprogramm.PS5ConverterGUI(_WURZEL)
        # Die Portsuche wuerde wirklich ins Netz greifen.
        cls.app._ps5_port_finden = lambda ip, port, art: port
        # Sonst schreibt der Lauf Verbindungsdaten in die Einstellungen.
        cls.app._save_setting = lambda *a, **k: None

    def setUp(self) -> None:
        self.lage = {"datei": GEPFLEGT, "stor": [], "fehlt": False}
        lage = self.lage

        class _FTP:
            def connect(self, *a, **k): pass
            def login(self, *a, **k): pass
            def quit(self): pass
            def mkd(self, pfad): pass

            def retrbinary(self, befehl, schreiber):
                if lage["fehlt"]:
                    raise ftplib.error_perm(
                        "550 %s: No such file or directory" % befehl)
                schreiber(lage["datei"])

            def storbinary(self, befehl, strom):
                daten = strom.read()
                lage["stor"].append(daten)
                lage["datei"] = daten

        self._echtes_ftp = ftplib.FTP
        ftplib.FTP = _FTP

        # Rueckfragen werden bejaht: Die Pruefung soll zeigen, dass selbst ein
        # zustimmender Anwender nichts zerstoeren kann.
        self.warnungen: list[str] = []
        self._echte = (messagebox.askyesno, messagebox.showwarning,
                       messagebox.showinfo)
        messagebox.askyesno = lambda *a, **k: True
        messagebox.showwarning = lambda *a, **k: self.warnungen.append(
            k.get("message") or (a[1] if len(a) > 1 else ""))
        messagebox.showinfo = lambda *a, **k: None

        self.fenster = self._fenster_oeffnen()

    def tearDown(self) -> None:
        ftplib.FTP = self._echtes_ftp
        (messagebox.askyesno, messagebox.showwarning,
         messagebox.showinfo) = self._echte
        if self.fenster is not None and self.fenster.winfo_exists():
            self.fenster.destroy()

    def _fenster_oeffnen(self):
        vorher = {str(w) for w in _WURZEL.winfo_children()}
        self.app._show_remote_ini_editor(
            "Pruefung", "/data/shadowmount/config.ini",
            "/data/shadowmount/debug.log", dict(VORGABEN), "pruefung")
        self._ruhen(0.4)
        neu = [w for w in _WURZEL.winfo_children()
               if str(w) not in vorher and isinstance(w, tk.Toplevel)
               and w.winfo_exists()]
        self.assertTrue(neu, "Es wurde kein Editorfenster geoeffnet")
        fenster = neu[-1]
        _sammle(fenster, "Entry")[0].insert(0, "127.0.0.1")
        self.knoepfe = {str(b.cget("text")).upper(): b
                        for b in _sammle(fenster, "Button")}
        return fenster

    @staticmethod
    def _ruhen(sekunden: float) -> None:
        """Kurz Ereignisse abarbeiten - reicht nur fuer den Fensteraufbau."""
        ende = time.perf_counter() + sekunden
        while time.perf_counter() < ende:
            _WURZEL.update()
            time.sleep(0.01)

    def _druecken(self, teil: str) -> None:
        """Drueckt den Knopf, dessen Beschriftung ``teil`` enthaelt."""
        for name, knopf in self.knoepfe.items():
            if teil in name:
                knopf.invoke()
                return
        self.fail("Kein Knopf enthaelt %r - vorhanden: %s"
                  % (teil, sorted(self.knoepfe)))

    def _ablauf(self, *schritte, schrittzeit: float = 1.6) -> None:
        """Faehrt die Schritte in einer **echten** Ereignisschleife ab.

        ``update()`` in einer Warteschleife genuegt hier nicht: Der Editor
        liest Adresse und Port erst im Arbeitsfaden
        (``_ftp_connect_blocking``), und ein Tk-Variablenzugriff aus einem
        Faden wirft ohne laufende ``mainloop`` sofort
        ``RuntimeError: main thread is not in main loop``. Der Ladevorgang
        kaeme dann nie zustande, und die Pruefung saehe einen Fehler, den es
        im Betrieb nicht gibt (beim Schreiben dieser Datei genau so
        passiert).
        """
        rest = list(schritte)
        # Notbremse: Bleibt ein Schritt haengen, endet der Lauf trotzdem -
        # eine mainloop ohne quit() haelt sonst die ganze Pruefreihe an.
        notaus = _WURZEL.after(int((len(rest) + 2) * schrittzeit * 1000) + 5000,
                               _WURZEL.quit)

        def _weiter() -> None:
            if rest:
                rest.pop(0)()
                _WURZEL.after(int(schrittzeit * 1000), _weiter)
            else:
                _WURZEL.quit()

        _WURZEL.after(200, _weiter)
        _WURZEL.mainloop()
        try:
            _WURZEL.after_cancel(notaus)
        except Exception:
            pass

    def test_ohne_laden_wird_nichts_geschrieben(self) -> None:
        """Der gemeldete Mangel: der Knopf war ab der ersten Sekunde scharf."""
        self._ablauf(lambda: self._druecken("SCHREIBEN"))
        self.assertEqual([], self.lage["stor"],
                         "Ohne geladenen Stand wurde auf die Konsole geschrieben.")
        self.assertEqual(GEPFLEGT, self.lage["datei"],
                         "Die gepflegte config.ini wurde veraendert.")
        self.assertTrue(self.warnungen,
                        "Der Anwender bekam keinen Hinweis, warum nichts geschah.")

    def test_nach_dem_laden_bleibt_alles_erhalten(self) -> None:
        """Der gute Weg darf durch die Behebung nicht zunageln."""
        self._ablauf(lambda: self._druecken("LADEN"),
                     lambda: self._druecken("SCHREIBEN"))
        self.assertEqual(1, len(self.lage["stor"]),
                         "Nach dem Laden muss sich schreiben lassen.")
        geschrieben = self.lage["stor"][-1].decode("utf-8")
        kommentare = [z for z in geschrieben.splitlines() if z.startswith("#")]
        self.assertGreaterEqual(
            len(kommentare), 40,
            "Die erklaerenden Zeilen der Vorlage geben verloren (nur %d)."
            % len(kommentare))
        self.assertIn("language=de", geschrieben,
                      "Ein Schluessel, den der Editor nicht fuehrt, ging verloren.")

    def test_liegt_am_ziel_nichts_wird_nicht_geschrieben(self) -> None:
        """Geladen von Konsole A, geschrieben nach B - der Stand passt nicht.

        Vor dem Ruecklesen in derselben Sitzung wurde hier geschrieben, obwohl
        der geladene Stand zu einer ganz anderen Datei gehoerte.
        """
        def _ziel_wechseln() -> None:
            self.lage["fehlt"] = True      # am neuen Ziel liegt nichts
            self.warnungen.clear()

        self._ablauf(lambda: self._druecken("LADEN"),
                     _ziel_wechseln,
                     lambda: self._druecken("SCHREIBEN"))
        self.assertEqual([], self.lage["stor"],
                         "Es wurde geschrieben, obwohl der Stand nicht passt.")
        self.assertTrue(self.warnungen,
                        "Der Anwender erfuhr nicht, dass nichts geschrieben wurde.")


@unittest.skipUnless(TK_DA, "Ohne Anzeige laesst sich kein Fenster oeffnen")
class FehlercodeTests(EditorSchreibwegTests):
    """Nur ``550`` heisst „da liegt nichts" - jede andere 5xx-Antwort nicht.

    Der zweite Entwurf fragte den Anwender bei **jedem** ``error_perm``, ob er
    die Datei als leer behandeln wolle. ``ftplib`` wirft das aber auch auf
    ``TYPE I``, ``PASV`` und die Quittung nach dem Datenstrom. Ein bejahtes
    „502 PASV command not implemented" setzte den Rohtext auf ``""`` - und weil
    das Ruecklesen vor dem Schreiben an derselben Ursache scheiterte, fiel auch
    die zweite Schranke aus. Gemessen: 1141 Bytes wurden zu 116.
    """

    def setUp(self) -> None:
        super().setUp()
        # Dieselbe Gegenstelle, aber mit einer Antwort, die ueber die Datei
        # nichts aussagt.
        lage = self.lage
        echtes = ftplib.FTP

        class _FTP502(echtes):
            def retrbinary(self, befehl, schreiber):
                raise ftplib.error_perm("502 PASV command not implemented")

        ftplib.FTP = _FTP502

    def test_ohne_laden_wird_nichts_geschrieben(self) -> None:
        """Erbt nichts Neues - der Fall steckt in den beiden Wegen unten."""
        self.skipTest("in test_502_beim_laden_zerstoert_nichts enthalten")

    def test_nach_dem_laden_bleibt_alles_erhalten(self) -> None:
        self.skipTest("mit 502 kommt kein Ladevorgang zustande")

    def test_liegt_am_ziel_nichts_wird_nicht_geschrieben(self) -> None:
        self.skipTest("mit 502 kommt kein Ladevorgang zustande")

    def test_502_beim_laden_zerstoert_nichts(self) -> None:
        self._ablauf(lambda: self._druecken("LADEN"),
                     lambda: self._druecken("SCHREIBEN"))
        self.assertEqual(
            [], self.lage["stor"],
            "Nach einem 502 wurde geschrieben - die Datei der Konsole ist weg.")
        self.assertEqual(
            GEPFLEGT, self.lage["datei"],
            "Die gepflegte config.ini wurde durch die Vorgaben ersetzt.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
