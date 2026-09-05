# -*- coding: utf-8 -*-
"""Der Log-Server des JS-Loaders: wer schreiben darf, und was er hinterlaesst.

Drei Befunde vom 04.09.2026, alle im Fenster ``_show_js_loader``:

* **M084** - Der Server band auf ``0.0.0.0`` und nahm jedes ``POST /log``
  an, ohne den Absender anzusehen. Der Inhalt ging ungefiltert ins
  Konsolenfeld und in die Protokolldatei; Umbrueche darin erzeugten dort
  eigene Zeilen mit gefaelschtem Zeitstempel.
* **M085** - ``win.bind("<Destroy>", ...)`` traf auch jedes Kindelement, weil
  der Pfad des Toplevels in dessen Bindetags steht.
* Beim Nachlesen dazugekommen: ``shutdown()`` beendet nur ``serve_forever``,
  der lauschende Socket blieb offen. Ohne ``server_close()`` war der Port
  nach dem Schliessen des Fensters weiter belegt.

Geprueft wird die Wirkung, nicht der Wortlaut: der Helfer mit echten
Adressen, der Handler ueber einen nachgebauten Aufruf.
"""
from __future__ import annotations

import io
import os
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("jsloader_logserver")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402


class HerkunftTests(unittest.TestCase):
    """``_logserver_absender_erlaubt`` - die Wache selbst."""

    def test_das_eigene_netz_darf(self):
        for adresse in ("192.168.1.94", "192.168.0.5", "10.0.0.7",
                        "172.16.3.1", "127.0.0.1", "169.254.1.1"):
            with self.subTest(adresse=adresse):
                self.assertTrue(APP._logserver_absender_erlaubt(adresse))

    def test_das_offene_netz_darf_nicht(self):
        # Keine Adresse aus 203.0.113.0/24 (TEST-NET-3): Python zaehlt die
        # Dokumentationsbereiche zu is_private, weil sie nicht global routbar
        # sind. Das ist richtig so - nur als Beispiel fuer "offenes Netz"
        # taugen sie nicht.
        for adresse in ("8.8.8.8", "1.1.1.1", "93.184.216.34", "100.100.5.5"):
            with self.subTest(adresse=adresse):
                self.assertFalse(APP._logserver_absender_erlaubt(adresse))

    def test_die_eingestellte_konsole_darf_immer(self):
        """Auch dann, wenn ihre Adresse nicht als privat gilt.

        Der CGNAT-Bereich 100.64.0.0/10 - den etwa Tailscale benutzt - ist
        fuer ``ipaddress`` NICHT privat. Wer seine Konsole ueber ein
        Mesh-Netz anspricht, faellt sonst durchs Raster und sucht den Grund
        woanders.
        """
        self.assertFalse(APP._logserver_absender_erlaubt("100.100.5.5"))
        self.assertTrue(APP._logserver_absender_erlaubt("100.100.5.5",
                                                        ps5_ip="100.100.5.5"))

    def test_muell_und_leeres_werden_abgewiesen(self):
        for adresse in ("", "   ", "kein-name", "999.1.1.1", None):
            with self.subTest(adresse=adresse):
                self.assertFalse(APP._logserver_absender_erlaubt(adresse))

    def test_eine_fremde_eingestellte_adresse_oeffnet_nicht_alles(self):
        """Der Vergleich gilt genau der einen Adresse, nicht ihrem Netz."""
        self.assertTrue(APP._logserver_absender_erlaubt("93.184.216.34",
                                                        ps5_ip="93.184.216.34"))
        self.assertFalse(APP._logserver_absender_erlaubt("93.184.216.35",
                                                         ps5_ip="93.184.216.34"))


class QuelltextTests(unittest.TestCase):
    """Was sich ohne laufendes Fenster am Syntaxbaum festhalten laesst."""

    @classmethod
    def setUpClass(cls):
        import ast
        with io.open(PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py",
                     encoding="utf-8") as fh:
            cls.quelle = fh.read()
        cls.baum = ast.parse(cls.quelle)

    def _methode(self, name):
        import ast
        for k in ast.walk(self.baum):
            if isinstance(k, ast.FunctionDef) and k.name == name:
                return k
        self.fail("Methode %s gibt es nicht mehr" % name)

    def test_beide_handler_fragen_die_wache(self):
        """do_POST und do_GET - eines von beiden zu vergessen ist die Falle."""
        import ast
        fenster = self._methode("_show_js_loader")
        handler = [k for k in ast.walk(fenster)
                   if isinstance(k, ast.ClassDef) and k.name == "_LogHandler"]
        self.assertTrue(handler, "Die Handler-Klasse gibt es nicht mehr.")
        methoden = {k.name: k for k in handler[0].body
                    if isinstance(k, ast.FunctionDef)}
        for name in ("do_POST", "do_GET"):
            with self.subTest(methode=name):
                self.assertIn(name, methoden)
                aufrufe = [k for k in ast.walk(methoden[name])
                           if isinstance(k, ast.Call)
                           and getattr(k.func, "attr", "") == "_absender_ok"]
                self.assertTrue(
                    aufrufe,
                    "%s nimmt wieder von jedem an." % name)

    def test_der_port_wird_beim_anhalten_freigegeben(self):
        """shutdown() allein laesst den Socket offen."""
        import ast
        fenster = self._methode("_show_js_loader")
        stopper = [k for k in ast.walk(fenster)
                   if isinstance(k, ast.FunctionDef)
                   and k.name == "_logserver_anhalten"]
        self.assertTrue(stopper, "Der gemeinsame Stopper fehlt.")
        aufrufe = {getattr(k.func, "attr", "") for k in ast.walk(stopper[0])
                   if isinstance(k, ast.Call)}
        self.assertIn("shutdown", aufrufe)
        self.assertIn("server_close", aufrufe,
                      "Ohne server_close bleibt der Port belegt, und ein "
                      "zweiter Start im selben Programmlauf scheitert.")

    def test_kein_weg_haelt_den_server_noch_von_hand_an(self):
        """Alle drei Wege - Schliessen, Zerstoeren, Stopp-Knopf - gehen ueber
        denselben Stopper. Sonst gibt einer den Port wieder nicht frei."""
        import ast
        fenster = self._methode("_show_js_loader")
        stopper = next(k for k in ast.walk(fenster)
                       if isinstance(k, ast.FunctionDef)
                       and k.name == "_logserver_anhalten")
        eigene = [k for k in ast.walk(fenster)
                  if isinstance(k, ast.Call)
                  and getattr(k.func, "attr", "") == "shutdown"
                  and not any(k is j for j in ast.walk(stopper))]
        self.assertEqual([], [k.lineno for k in eigene],
                         "Ein Weg haelt den Server an _logserver_anhalten "
                         "vorbei an - der gibt den Port dann nicht frei.")


if __name__ == "__main__":
    unittest.main()
