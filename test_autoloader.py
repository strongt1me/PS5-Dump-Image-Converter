# -*- coding: utf-8 -*-
"""Tests fuer den ps5_autoloader-Editor.

Der Autoloader entscheidet, was die Konsole nach dem Exploit startet. Eine
falsch geschriebene autoload.txt faellt erst beim naechsten Neustart auf, und
dann ohne Meldung - deshalb wird hier gegen einen nachgebauten FTP-Dienst
geprueft statt gegen die echte Konsole.
"""
import ast
import io
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import PS5ImageConverter_Pro_FINAL_revised as APP
from ps5_validator.utils import i18n

HAUPTDATEI = str(PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py")


def _gui():
    """Programmobjekt ohne Tk - nur die Autoloader-Wege werden gebraucht."""
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui._t = lambda key, **kw: key
    return gui


class _FtpNachbau:
    """Ein FTP-Dienst, so weit nachgebaut, wie dieses Fenster ihn benutzt."""

    def __init__(self, dateien=None, ordner_da=True):
        self.dateien = dict(dateien or {})
        self.ordner_da = ordner_da
        self.angelegt = []
        self.geloescht = []
        self.geschrieben = {}

    def cwd(self, pfad):
        if not self.ordner_da:
            raise OSError("550 kein solcher Ordner")
        return "250 ok"

    def mkd(self, pfad):
        self.angelegt.append(pfad)
        self.ordner_da = True

    def nlst(self, pfad):
        return [pfad + "/" + n for n in sorted(self.dateien)]

    def retrbinary(self, befehl, schreiber):
        name = befehl.split("/")[-1]
        if name not in self.dateien:
            raise OSError("550 nicht da")
        schreiber(self.dateien[name])

    def storbinary(self, befehl, strom):
        name = befehl.split("/")[-1]
        daten = strom.read()
        self.geschrieben[name] = daten
        self.dateien[name] = daten

    def delete(self, pfad):
        name = pfad.split("/")[-1]
        self.geloescht.append(name)
        self.dateien.pop(name, None)


class ReihenfolgeTests(unittest.TestCase):
    """Welche Zeilen der autoload.txt eine Datei nennen - und welche nicht."""

    def test_kommentare_und_wartezeilen_zaehlen_nicht(self):
        gui = _gui()
        inhalt = (
            "#\n"
            "# ps5_autoloader\n"
            "\n"
            "zftpd-ps5-v1.2.1.elf\n"
            "!5000\n"
            "ps5-backpork.elf\n"
            "  !3000  \n"
            "customPSNotify.js\n"
        )
        self.assertEqual(
            gui._autoloader_genannte_dateien(inhalt),
            ["zftpd-ps5-v1.2.1.elf", "ps5-backpork.elf", "customPSNotify.js"])

    def test_leerer_inhalt_ergibt_leere_liste(self):
        self.assertEqual(_gui()._autoloader_genannte_dateien(""), [])
        self.assertEqual(_gui()._autoloader_genannte_dateien(None), [])

    def test_leerraum_wird_abgeschnitten(self):
        # Eine Zeile mit Leerzeichen am Rand nennt dieselbe Datei - sonst
        # meldete die Pruefung sie als fehlend, obwohl sie im Ordner liegt.
        self.assertEqual(_gui()._autoloader_genannte_dateien("  kstuff.elf  \n"),
                         ["kstuff.elf"])


class LesenTests(unittest.TestCase):
    """Dateiliste und autoload.txt von der Konsole holen."""

    def test_liste_und_inhalt_kommen_an(self):
        gui = _gui()
        ftp = _FtpNachbau({
            "autoload.txt": b"kstuff.elf\n!1000\n",
            "kstuff.elf": b"\x7fELF...",
            "notiz.txt": b"kein Payload",
        })
        stand = gui._autoloader_lesen(ftp)
        self.assertEqual(stand["dateien"], ["kstuff.elf"])
        self.assertEqual(stand["inhalt"], "kstuff.elf\n!1000\n")
        # "alle" traegt auch die Dateien, die der Autoloader nicht startet -
        # der Schnappschuss muss sie trotzdem mitnehmen.
        self.assertIn("notiz.txt", stand["alle"])

    def test_fehlende_autoload_ist_kein_fehler(self):
        gui = _gui()
        stand = gui._autoloader_lesen(_FtpNachbau({"kstuff.elf": b"x"}))
        self.assertEqual(stand["inhalt"], "")
        self.assertEqual(stand["dateien"], ["kstuff.elf"])

    def test_ordner_wird_angelegt_wenn_er_fehlt(self):
        gui = _gui()
        ftp = _FtpNachbau({}, ordner_da=False)
        gui._autoloader_lesen(ftp)
        self.assertEqual(ftp.angelegt, ["/data/ps5_autoloader"])

    def test_nur_startbare_endungen_in_der_liste(self):
        gui = _gui()
        ftp = _FtpNachbau({"a.elf": b"", "b.bin": b"", "c.js": b"",
                           "d.png": b"", "e.txt": b""})
        self.assertEqual(gui._autoloader_lesen(ftp)["dateien"],
                         ["a.elf", "b.bin", "c.js"])

    def test_unlesbare_liste_wirft_nicht(self):
        class _Kaputt(_FtpNachbau):
            def nlst(self, pfad):
                raise OSError("550 keine Liste")

        stand = _gui()._autoloader_lesen(_Kaputt())
        self.assertEqual(stand["dateien"], [])
        self.assertEqual(stand["inhalt"], "")


class QuelltextTests(unittest.TestCase):
    """Was sich am Quelltext festhalten laesst, ohne ein Fenster zu bauen."""

    @classmethod
    def setUpClass(cls):
        with io.open(HAUPTDATEI, encoding="utf-8") as fh:
            cls.quelle = fh.read()

    def test_im_werkzeugmenue(self):
        self.assertIn('("titlebar.autoloader", "_show_autoloader")', self.quelle)

    def test_richtiger_ordner(self):
        # /data ist der einzige Ort, an den man ohne USB-Stick herankommt.
        self.assertIn('_AUTOLOADER_ORDNER = "/data/ps5_autoloader"', self.quelle)
        self.assertIn('_AUTOLOADER_DATEI = "autoload.txt"', self.quelle)

    def test_geht_ueber_die_vorhandene_ftp_wahl(self):
        # _ampr_ftp_connect bevorzugt ftpsrv auf 2121. Nur dessen Uploads
        # tragen das Ausfuehrungsrecht - mit einem anderen Dienst startet die
        # Konsole die Payloads nicht und sagt nichts dazu.
        self.assertIn("ftp = self._ampr_ftp_connect(host, self._ps5_ftp_port())",
                      self.quelle)

    def test_ausfuehrungsrecht_wird_nachgesehen(self):
        # Frueher stand hier die Bitmaske direkt: "_ps5_datei_modus(...) & 0o111".
        # Der Helfer liefert 0, wenn weder MLST noch LIST die Rechte hergeben -
        # dann warnte das Fenster nach JEDEM Upload. Seither geht es ueber
        # _warnen_wenn_nicht_ausfuehrbar, das "nicht gesetzt" von "nicht
        # feststellbar" unterscheidet. Dass der Helfer das wirklich tut, misst
        # test_werkzeugfeinheiten.py; hier steht nur, dass er benutzt wird.
        baum = ast.parse(self.quelle)
        fenster = next(k for k in ast.walk(baum)
                       if isinstance(k, ast.FunctionDef)
                       and k.name == "_show_autoloader")
        aufrufe = [getattr(k.func, "attr", "") for k in ast.walk(fenster)
                   if isinstance(k, ast.Call)]
        self.assertIn("_warnen_wenn_nicht_ausfuehrbar", aufrufe,
                      "Nach dem Upload wird gar nicht mehr nachgesehen.")
        self.assertNotIn("_ps5_datei_modus", aufrufe,
                         "Die Bitmaske wird wieder direkt abgefragt - dann gilt "
                         "'Rechte nicht auslesbar' faelschlich als 'nicht "
                         "ausfuehrbar'.")

    def test_nur_startbare_dateien_werden_geprueft(self):
        # autoload.txt ist eine Textdatei. Bei ihr fehlt das Ausfuehrungsrecht
        # zu Recht - eine Warnung waere hier immer falsch.
        self.assertIn('name.lower().endswith((".elf", ".bin"))', self.quelle)

    def test_arbeit_laeuft_nicht_im_oberflaechen_thread(self):
        # Eine FTP-Verbindung zu einer abwesenden Konsole braucht Sekunden.
        # Im Tk-Thread waere das Fenster so lange eingefroren.
        self.assertIn("threading.Thread(target=_lauf, daemon=True).start()", self.quelle)

    def test_verbindung_wird_immer_geschlossen(self):
        stelle = self.quelle.find("def _autoloader_auftrag")
        ende = self.quelle.find("def _autoloader_ordner_sichern")
        self.assertGreater(ende, stelle)
        self.assertIn("finally:", self.quelle[stelle:ende])

    def test_loeschen_und_zurueckspielen_fragen_nach(self):
        # Beides ueberschreibt oder entfernt auf der Konsole - ohne Rueckfrage
        # waere ein Fehlklick nicht zu widerrufen.
        stelle = self.quelle.find("def _show_autoloader")
        block = self.quelle[stelle:stelle + 20000]
        for schluessel in ("autoloader.delete_message", "autoloader.restore_message"):
            self.assertIn(schluessel, block, schluessel)
        self.assertGreaterEqual(block.count('default="no"'), 2)


class I18nTests(unittest.TestCase):
    """Jeder benutzte Schluessel steht in beiden Sprachen."""

    @classmethod
    def setUpClass(cls):
        with io.open(HAUPTDATEI, encoding="utf-8") as fh:
            cls.quelle = fh.read()

    def test_benutzte_schluessel_vollstaendig(self):
        import re
        benutzt = set(re.findall(r'_t\(\s*["\'](autoloader\.[a-z_0-9]+)', self.quelle))
        benutzt.add("titlebar.autoloader")
        self.assertGreaterEqual(len(benutzt), 15, "zu wenige Schluessel gefunden")
        fehlend = sorted(k for k in benutzt if k not in i18n.STRINGS)
        self.assertEqual(fehlend, [], "fehlen in STRINGS: %s" % fehlend)
        for schluessel in sorted(benutzt):
            for sprache in ("de", "en"):
                self.assertTrue(i18n.STRINGS[schluessel].get(sprache),
                                "%s/%s fehlt" % (schluessel, sprache))

    def test_hinweis_nennt_die_suchreihenfolge(self):
        # Ohne sie glaubt man, /data sei der einzige Ort - ein USB-Stick
        # sticht ihn aber aus, und dann wirkt dieses Fenster folgenlos.
        text = i18n.STRINGS["autoloader.hint"]["de"]
        for stueck in ("USB", "/data"):
            self.assertIn(stueck, text)


class FehlschlaegeWerdenGemeldetTests(unittest.TestCase):
    """Eine Datei, die nicht mitkommt, darf nicht stillschweigend fehlen.

    Beim Loeschen und beim Zurueckspielen faengt die Schleife je Datei die
    Ausnahme ab und schrieb bis zum 06.09.2026 nur ein ``logger.debug``.
    Der ``PS5Converter``-Logger steht im Auslieferungsstand auf INFO - der
    Anwender erfuhr also nie, dass etwas stehenblieb; die Zahl im Ergebnis
    war der einzige Hinweis, und die liest niemand nach.

    Der Schnappschuss daneben macht es seit jeher richtig: Er sammelt seine
    Fehlschlaege in ``misslungen`` und meldet sie ueber ``_append_to_log``.
    Genau diese Behandlung fehlte den beiden Geschwistern.
    """

    @classmethod
    def setUpClass(cls) -> None:
        import ast
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8")
        baum = ast.parse(quelle)
        knoten = next(k for k in ast.walk(baum)
                      if isinstance(k, ast.FunctionDef)
                      and k.name == "_show_autoloader")
        cls.block = ast.unparse(knoten)

    def test_alle_drei_wege_melden_ihre_fehlschlaege(self) -> None:
        for schluessel in ("autoloader.snapshot_incomplete",
                           "autoloader.delete_incomplete",
                           "autoloader.restore_incomplete"):
            with self.subTest(meldung=schluessel):
                self.assertIn(schluessel, self.block,
                              "Dieser Weg verschweigt seine Fehlschlaege "
                              "wieder.")

    def test_die_meldungen_gibt_es_in_beiden_sprachen(self) -> None:
        from ps5_validator.utils import i18n
        for schluessel in ("autoloader.delete_incomplete",
                           "autoloader.restore_incomplete"):
            with self.subTest(meldung=schluessel):
                eintrag = i18n.STRINGS[schluessel]
                self.assertTrue(eintrag.get("de"))
                self.assertTrue(eintrag.get("en"))
                self.assertNotEqual(eintrag["de"], eintrag["en"])

    def test_die_namen_stehen_in_der_meldung(self) -> None:
        """Eine blosse Zahl hilft nicht - man will wissen, welche Datei."""
        from ps5_validator.utils import i18n
        for schluessel in ("autoloader.delete_incomplete",
                           "autoloader.restore_incomplete"):
            with self.subTest(meldung=schluessel):
                for sprache in ("de", "en"):
                    text = i18n.STRINGS[schluessel][sprache]
                    self.assertIn("{names}", text)
                    self.assertIn("{count}", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
