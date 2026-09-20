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
import tempfile
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
    from tkinter import filedialog, messagebox

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
        # Die Knoepfe werden ueber ihre **Beschriftung** gedrueckt. Steht in
        # der Einstellungsdatei "en", baut das Fenster englische Knoepfe, und
        # "LADEN"/"SCHREIBEN" finden nichts mehr - ``_druecken`` scheitert
        # dann mitten in einer Tk-Rueckmeldung, der Ausnahmehaken des
        # Programms schluckt es ins Protokoll, und der Test faellt erst an
        # der Folgezusicherung um ("Der Anwender erfuhr nicht ...").
        #
        # Genau das geschah im Verbund: ``pruefumgebung.umlenken`` setzt
        # ``PS5CONV_KONFIGORDNER`` prozessweit und laeuft beim *Import*; es
        # gewinnt der Ordner des zuletzt geladenen Pruefmoduls. Einzeln lief
        # das Trio deshalb immer gruen, im Volllauf immer rot. Dieselbe
        # Zeile steht aus demselben Grund in test_fensterlayout.py.
        cls.app._current_language = "de"

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
class DebugLogAbholenTests(EditorSchreibwegTests):
    """Ein misslungener Abruf darf die gewaehlte Datei nicht leeren.

    ShadowMount+ legt die ``debug.log`` nur bei ``debug=1`` an. Fehlt sie auf
    der Konsole, ging der Abruf trotzdem ueber ``open(pfad, "wb")`` - das legt
    die Zieldatei an bzw. leert sie, noch bevor das ``RETR`` laeuft. Der
    Anwender fand danach eine 0-Byte-Datei; hatte er im Dialog eine vorhandene
    aeltere Protokolldatei zum Ueberschreiben ausgewaehlt, war deren Inhalt
    weg, obwohl nichts angekommen war.
    """

    ALT = b"aeltere Protokolldatei, die es zu erhalten gilt\n"

    def setUp(self) -> None:
        super().setUp()
        self.ziel = os.path.join(
            tempfile.mkdtemp(prefix="ps5_debuglog_"), "debug.log")
        with open(self.ziel, "wb") as datei:
            datei.write(self.ALT)
        self._echter_dialog = filedialog.asksaveasfilename
        filedialog.asksaveasfilename = lambda *a, **k: self.ziel

    def tearDown(self) -> None:
        filedialog.asksaveasfilename = self._echter_dialog
        super().tearDown()

    # Die geerbten Wege pruefen den Schreibweg, hier geht es um den Abruf.
    def test_ohne_laden_wird_nichts_geschrieben(self) -> None:
        self.skipTest("in dieser Klasse geht es um das Abholen")

    def test_nach_dem_laden_bleibt_alles_erhalten(self) -> None:
        self.skipTest("in dieser Klasse geht es um das Abholen")

    def test_liegt_am_ziel_nichts_wird_nicht_geschrieben(self) -> None:
        self.skipTest("in dieser Klasse geht es um das Abholen")

    def test_misslungener_abruf_laesst_die_datei_unberuehrt(self) -> None:
        self.lage["fehlt"] = True          # auf der Konsole liegt keine
        self._ablauf(lambda: self._druecken("DEBUG"))
        with open(self.ziel, "rb") as datei:
            self.assertEqual(
                self.ALT, datei.read(),
                "Die vorhandene Protokolldatei wurde geleert, obwohl der "
                "Abruf fehlschlug.")
        self.assertFalse(
            os.path.exists(self.ziel + ".teil"),
            "Die Zwischendatei blieb liegen und sieht wie ein Ergebnis aus.")

    def test_geglueckter_abruf_schreibt_die_datei(self) -> None:
        """Die Gegenrichtung - sonst hiesse 'nichts kaputt' auch 'nichts tut'."""
        self.lage["datei"] = b"frisches Protokoll von der Konsole\n"
        self._ablauf(lambda: self._druecken("DEBUG"))
        with open(self.ziel, "rb") as datei:
            self.assertEqual(b"frisches Protokoll von der Konsole\n",
                             datei.read())


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


class FremdeSchluesselUeberlebenTests(unittest.TestCase):
    """Eine neuere Payload-Fassung bringt Schluessel mit, die wir nicht kennen.

    Am 21.09.2026 an ShadowMountPlus 1.7 gemessen (Release 4102fa7a): Die
    ``config.ini.example`` fuehrt 39 Schluessel, sechs davon kannte das
    Programm nicht - ``api_enabled``, ``nested_pfs_index_cache``,
    ``fan_target_temperature`` und die drei ``auto_remove_*``. Sie sind
    inzwischen in ``_SHADOWMOUNT_DEFAULTS`` nachgetragen.

    Darauf darf man sich aber nicht verlassen: Die naechste Fassung bringt
    wieder neue. Entscheidend ist, dass der Editor sie **durchreicht** -
    ``merge_flat_ini`` laesst Zeilen stehen, die es nicht kennt, und
    kommentiert nur aus, was im Editor-Woerterbuch fehlt.

    Genau das prueft diese Klasse am Verhalten, mit frei erfundenen
    Schluesselnamen. Ein Test gegen die sechs echten haette nach dem
    Nachtragen nichts mehr gemessen.
    """

    #: Namen, die es in keiner Fassung gibt - so misst der Test die
    #: Durchreiche, nicht die Vorgabenliste.
    ERFUNDEN = {
        "zukunft_eine_zahl": "42",
        "zukunft_ein_pfad": "/data/shadowmount/irgendwas",
        "zukunft_ein_wort": "system",
    }

    def _vorlage(self) -> str:
        from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI
        zeilen = ["# Kommentar, der stehen bleiben muss", ""]
        for schluessel, wert in PS5ConverterGUI._SHADOWMOUNT_DEFAULTS.items():
            zeilen.append("%s=%s" % (schluessel, wert))
        zeilen.append("")
        zeilen.append("# Von einer neueren Fassung mitgebracht:")
        for schluessel, wert in self.ERFUNDEN.items():
            zeilen.append("%s=%s" % (schluessel, wert))
        return "\n".join(zeilen) + "\n"

    def test_unbekannte_schluessel_bleiben_aktiv(self):
        """Der Fall, der auf der Konsole Einstellungen kosten wuerde."""
        from ps5_validator.utils.ini_config import (
            fuer_anzeige, fuer_datei, merge_flat_ini, parse_flat_ini_multi)
        from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI

        vorlage = self._vorlage()
        geladen = parse_flat_ini_multi(vorlage)
        for schluessel in self.ERFUNDEN:
            self.assertIn(schluessel, geladen,
                          "Aufbau: %s wurde nicht einmal gelesen" % schluessel)

        # So baut das Fenster seine Tabelle: geladen, Vorgaben fuer Fehlende.
        tabelle = dict(PS5ConverterGUI._SHADOWMOUNT_DEFAULTS)
        tabelle.update(fuer_anzeige(geladen))
        danach = parse_flat_ini_multi(merge_flat_ini(vorlage, fuer_datei(tabelle)))

        verloren = sorted(k for k in geladen if k not in danach)
        self.assertEqual(
            [], verloren,
            "Diese Schluessel sind beim Speichern verschwunden: %s" % verloren)
        for schluessel, wert in self.ERFUNDEN.items():
            self.assertEqual([wert], danach.get(schluessel),
                             "%s hat seinen Wert verloren" % schluessel)

    def test_kommentare_bleiben_stehen(self):
        """Die config.ini der Konsole ist zugleich ihre Dokumentation."""
        from ps5_validator.utils.ini_config import (
            fuer_anzeige, fuer_datei, merge_flat_ini, parse_flat_ini_multi)
        from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI

        vorlage = self._vorlage()
        tabelle = dict(PS5ConverterGUI._SHADOWMOUNT_DEFAULTS)
        tabelle.update(fuer_anzeige(parse_flat_ini_multi(vorlage)))
        neu = merge_flat_ini(vorlage, fuer_datei(tabelle))
        self.assertIn("# Kommentar, der stehen bleiben muss", neu)
        self.assertIn("# Von einer neueren Fassung mitgebracht:", neu)

    def test_die_sechs_aus_1_7_sind_nachgetragen(self):
        """Damit eine fehlende Datei sie auch anbietet.

        Der Editor haette sie ohnehin durchgereicht - aber beim Anlegen einer
        neuen Datei greift allein diese Liste.
        """
        from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI
        vorgaben = PS5ConverterGUI._SHADOWMOUNT_DEFAULTS
        erwartet = {
            "api_enabled": "1",
            "auto_remove_missing_games": "0",
            "auto_remove_games_with_dlc": "0",
            "auto_remove_missing_delay_seconds": "300",
            "nested_pfs_index_cache": "0",
            "fan_target_temperature": "system",
        }
        for schluessel, wert in erwartet.items():
            self.assertEqual(wert, vorgaben.get(schluessel), schluessel)

    def test_das_fenster_baut_seine_tabelle_wirklich_so(self):
        """Der Nachbau oben muss dem Fenster entsprechen.

        Geprueft wird der Syntaxbaum von ``_show_remote_ini_editor``: Die
        Tabelle beginnt bei den Vorgaben (``dict(defaults)``) und bekommt
        danach das Geladene darueber (``data.update(loaded)``). Faellt das
        zweite weg, landen Schluessel einer neueren Fassung nicht mehr in der
        Tabelle - und ``merge_flat_ini`` wuerde sie folgerichtig
        auskommentieren, weil sie im Woerterbuch fehlen.
        """
        import ast
        pfad = os.path.join(PROJEKT, "PS5ImageConverter_Pro_FINAL_revised.py")
        with open(pfad, encoding="utf-8") as fh:
            quelle = fh.read()
        methode = next(
            (k for k in ast.walk(ast.parse(quelle))
             if isinstance(k, ast.FunctionDef)
             and k.name == "_show_remote_ini_editor"), None)
        self.assertIsNotNone(methode, "_show_remote_ini_editor heisst anders")

        aus_vorgaben = []
        mit_geladen = []
        for knoten in ast.walk(methode):
            if not isinstance(knoten, ast.Call):
                continue
            # dict(defaults)
            if (isinstance(knoten.func, ast.Name) and knoten.func.id == "dict"
                    and len(knoten.args) == 1
                    and isinstance(knoten.args[0], ast.Name)
                    and knoten.args[0].id == "defaults"):
                aus_vorgaben.append(knoten.lineno)
            # data.update(loaded)
            if (isinstance(knoten.func, ast.Attribute)
                    and knoten.func.attr == "update"
                    and isinstance(knoten.func.value, ast.Name)
                    and knoten.func.value.id == "data"
                    and knoten.args
                    and isinstance(knoten.args[0], ast.Name)
                    and knoten.args[0].id == "loaded"):
                mit_geladen.append(knoten.lineno)

        self.assertTrue(aus_vorgaben,
                        "Die Tabelle beginnt nicht mehr bei dict(defaults)")
        self.assertTrue(
            mit_geladen,
            "Kein data.update(loaded) - dann stehen Schluessel einer neueren "
            "Payload-Fassung nicht in der Tabelle und werden beim Speichern "
            "auskommentiert.")
        self.assertLess(min(aus_vorgaben), min(mit_geladen),
                        "Die Vorgaben ueberschreiben das Geladene")

    def test_fehlende_spiele_werden_nicht_von_selbst_ausgetragen(self):
        """Ein abgezogener USB-Stick ist kein Loeschauftrag.

        1.7 kann fehlende Spiele aus der Systembibliothek entfernen. Ab Werk
        ist das aus, und dabei bleibt es hier: Das Programm legt keine
        Konfiguration an, die auf der Konsole von selbst etwas austraegt.
        """
        from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI
        vorgaben = PS5ConverterGUI._SHADOWMOUNT_DEFAULTS
        self.assertEqual("0", vorgaben.get("auto_remove_missing_games"))
        self.assertEqual("0", vorgaben.get("auto_remove_games_with_dlc"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
