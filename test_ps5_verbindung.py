"""Tests fuer die zentralen PS5-Verbindungsdaten in den Einstellungen.

Vorher hielt jedes Fenster seine eigene Adresse (``klog_ip``,
``<prefix>_ftp_ip``, ``ps5_ip``), und der JS Loader hatte sie fest im Code.
Wer die Konsole umzieht, musste sie an vier Stellen nachtragen.

Jetzt gibt es einen zentralen Satz - ``ps5_ip``, ``ps5_ftp_port``,
``ps5_klog_port`` -, den die Fenster als Vorschlag nehmen. Ein Fenster mit
eigenem Eintrag behaelt seinen; nur wo nichts steht, greift der zentrale Wert.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import PS5ImageConverter_Pro_FINAL_revised as APP
from ps5_validator.utils.i18n import STRINGS, translate

QUELLE = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"


class _Attrappe:
    """Instanz ohne __init__ mit hinterlegten Einstellungen."""

    def __init__(self, werte: dict):
        self.werte = dict(werte)

    def _load_setting(self, schluessel, standard=None):
        return self.werte.get(schluessel, standard)


def _app(werte: dict):
    obj = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    obj._load_setting = _Attrappe(werte)._load_setting  # type: ignore[method-assign]
    return obj


class LesehilfenTests(unittest.TestCase):
    def test_ip_kommt_aus_der_einstellung(self):
        self.assertEqual(APP.PS5ConverterGUI._ps5_ip(_app({"ps5_ip": " 10.0.0.5 "})), "10.0.0.5")

    def test_ip_leer_wenn_nichts_gesetzt(self):
        self.assertEqual(APP.PS5ConverterGUI._ps5_ip(_app({})), "")

    def test_ftp_port_standard(self):
        self.assertEqual(APP.PS5ConverterGUI._ps5_ftp_port(_app({})), APP.PS5_FTP_DEFAULT_PORT)

    def test_ftp_port_aus_einstellung(self):
        self.assertEqual(APP.PS5ConverterGUI._ps5_ftp_port(_app({"ps5_ftp_port": "1337"})), 1337)

    def test_klog_port_standard_3232(self):
        self.assertEqual(APP.PS5ConverterGUI._ps5_klog_port(_app({})), 3232)

    def test_unsinnige_ports_fallen_auf_den_standard(self):
        for wert in ("0", "70000", "abc", "", None, -5):
            with self.subTest(wert=wert):
                self.assertEqual(
                    APP.PS5ConverterGUI._ps5_ftp_port(_app({"ps5_ftp_port": wert})),
                    APP.PS5_FTP_DEFAULT_PORT)
                self.assertEqual(
                    APP.PS5ConverterGUI._ps5_klog_port(_app({"ps5_klog_port": wert})), 3232)


class VorrangTests(unittest.TestCase):
    """Der eigene Wert eines Fensters schlaegt den zentralen."""

    def test_eigener_wert_gewinnt(self):
        obj = _app({"klog_ip": "10.1.1.1", "ps5_ip": "192.168.1.94"})
        self.assertEqual(
            APP.PS5ConverterGUI._ps5_wert_oder_zentral(obj, "klog_ip", "192.168.1.94"),
            "10.1.1.1")

    def test_zentraler_wert_wenn_eigener_leer(self):
        for leer in ("", "   ", None):
            with self.subTest(leer=leer):
                obj = _app({"klog_ip": leer})
                self.assertEqual(
                    APP.PS5ConverterGUI._ps5_wert_oder_zentral(obj, "klog_ip", "192.168.1.94"),
                    "192.168.1.94")

    def test_zentraler_port_wird_als_text_geliefert(self):
        obj = _app({})
        self.assertEqual(
            APP.PS5ConverterGUI._ps5_wert_oder_zentral(obj, "klog_port", 3232), "3232")


class MerkenTests(unittest.TestCase):
    """Ein Fenster darf den zentralen Wert nicht bei sich festschreiben.

    Die Fenster fuellen ihr Feld beim Oeffnen aus der zentralen Einstellung
    vor. Beim Verbinden wurde der Feldinhalt bis zum 06.09.2026
    bedingungslos als eigener Wert gespeichert - auch wenn der Anwender
    nichts geaendert hatte. Ab dem ersten Verbinden stand damit ein eigener
    Wert da, und der schlaegt den zentralen: Wer danach in den
    Einstellungen eine andere Adresse eintrug, sah sie in KLOG, den
    FTP-Fenstern und im AMPR-Picker nie wieder.
    """

    def _app_mit_speicher(self):
        """Eine Instanz, die ihre Einstellungen im Speicher haelt."""
        werte: dict = {}
        obj = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        obj._load_setting = lambda k, s=None: werte.get(k, s)
        obj._save_setting = lambda k, v: werte.__setitem__(k, v)
        return obj, werte

    def test_der_unveraenderte_wert_wird_nicht_festgeschrieben(self):
        obj, werte = self._app_mit_speicher()
        obj._ps5_wert_merken("klog_ip", "192.168.1.94", "192.168.1.94")
        self.assertEqual("", werte.get("klog_ip"),
                         "Der zentrale Wert wurde als eigener festgehalten - "
                         "dann folgt das Fenster der Einstellung nie wieder.")

    def test_danach_wirkt_eine_geaenderte_einstellung_wieder(self):
        """Der eigentliche Fall, gemessen ueber beide Methoden."""
        obj, werte = self._app_mit_speicher()
        werte["ps5_ip"] = "192.168.1.94"
        # Verbinden, ohne etwas zu aendern
        obj._ps5_wert_merken("klog_ip", "192.168.1.94", werte["ps5_ip"])
        # Jetzt zentral umstellen
        werte["ps5_ip"] = "192.168.1.50"
        self.assertEqual(
            "192.168.1.50",
            obj._ps5_wert_oder_zentral("klog_ip", werte["ps5_ip"]))

    def test_ein_bewusst_anderer_wert_bleibt(self):
        obj, werte = self._app_mit_speicher()
        werte["ps5_ip"] = "192.168.1.94"
        obj._ps5_wert_merken("klog_ip", "10.0.0.5", werte["ps5_ip"])
        self.assertEqual("10.0.0.5", werte["klog_ip"])
        self.assertEqual(
            "10.0.0.5",
            obj._ps5_wert_oder_zentral("klog_ip", werte["ps5_ip"]))

    def test_zahlen_und_text_werden_gleich_behandelt(self):
        """Der Port kommt mal als int, mal als str - beides derselbe Wert."""
        obj, werte = self._app_mit_speicher()
        obj._ps5_wert_merken("klog_port", 3232, "3232")
        self.assertEqual("", werte.get("klog_port"))
        obj._ps5_wert_merken("klog_port", "3232", 3232)
        self.assertEqual("", werte.get("klog_port"))
        obj._ps5_wert_merken("klog_port", 3333, 3232)
        self.assertEqual("3333", werte.get("klog_port"))

    def test_ein_leerer_wert_loescht_den_eigenen(self):
        obj, werte = self._app_mit_speicher()
        werte["klog_ip"] = "10.0.0.5"
        obj._ps5_wert_merken("klog_ip", "   ", "192.168.1.94")
        self.assertEqual("", werte["klog_ip"])

    def test_kein_fenster_speichert_mehr_direkt(self):
        """Ueber den Syntaxbaum: _save_setting darf hier nicht mehr stehen."""
        import ast
        baum = ast.parse(QUELLE.read_text(encoding="utf-8"))
        schlecht = []
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.Call):
                continue
            if getattr(knoten.func, "attr", "") != "_save_setting":
                continue
            if not knoten.args:
                continue
            erstes = ast.unparse(knoten.args[0])
            if any(teil in erstes for teil in
                   ("klog_ip", "klog_port", "_ftp_ip", "_ftp_port",
                    "ampr_ftp_port")):
                schlecht.append((knoten.lineno, erstes))
        self.assertEqual([], schlecht,
                         "Diese Stellen schreiben den eigenen Wert wieder "
                         "bedingungslos: %s" % schlecht)


class QuelltextTests(unittest.TestCase):
    """Was sich nur am Aufbau zeigt."""

    @classmethod
    def setUpClass(cls):
        cls.text = QUELLE.read_text(encoding="utf-8")

    def test_js_loader_hat_keine_fest_verdrahtete_adresse_mehr(self):
        self.assertNotIn('ip_var = tk.StringVar(value="192.168.1.94")', self.text)

    def test_die_vier_fenster_fragen_die_zentrale_stelle(self):
        for stelle in ('_ps5_wert_oder_zentral("klog_ip"',
                       '_ps5_wert_oder_zentral("klog_port"',
                       '_ps5_wert_oder_zentral(f"{settings_prefix}_ftp_ip"',
                       '_ps5_wert_oder_zentral(f"{settings_prefix}_ftp_port"',
                       '_ps5_wert_oder_zentral("ampr_ftp_port"'):
            with self.subTest(stelle=stelle):
                self.assertIn(stelle, self.text)

    def test_speichern_schreibt_die_drei_schluessel(self):
        stelle = self.text.index("def _speichern_und_schliessen")
        block = self.text[stelle:stelle + 4000]
        for schluessel in ('"ps5_ip"', '"ps5_ftp_port"', '"ps5_klog_port"'):
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, block)

    def test_hinweis_hat_eine_umbruchbreite(self):
        """Ohne sie lief der Text auf eine Zeile und wurde abgeschnitten."""
        stelle = self.text.index('settings_dialog.ps5_hint')
        self.assertIn("wraplength", self.text[stelle:stelle + 400])

    def _adressschreiber(self):
        """Funktionen, die die zentrale Adresse ``ps5_ip`` speichern."""
        import ast
        namen = set()
        for knoten in ast.walk(ast.parse(self.text)):
            if not isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for k in ast.walk(knoten):
                if (isinstance(k, ast.Call)
                        and isinstance(k.func, ast.Attribute)
                        and k.func.attr == "_save_setting"
                        and k.args
                        and isinstance(k.args[0], ast.Constant)
                        and k.args[0].value == "ps5_ip"):
                    namen.add(knoten.name)
        return namen

    def test_die_zentrale_adresse_wird_nicht_bei_jedem_zeichen_geschrieben(self):
        """Kein Speicherer der zentralen Adresse haengt an ``trace_add``.

        Zweimal dieselbe Falle: Ein ``ip_var.trace_add("write", _ip_merken)``
        feuert bei **jedem Tastendruck**. Waehrend "192.168.1.94" entsteht,
        wandern elf Zwischenstaende ("1", "19", "192", "192.", ...) in die
        zentrale Einstellung, die alle anderen Fenster lesen; wer mittendrin
        abbricht, laesst dort einen Torso zurueck. Im Autoloader-Fenster am
        05.09.2026 behoben, im AppInstall-Fenster stehen geblieben und erst am
        07.09.2026 gefunden.

        Richtig ist ``<FocusOut>``/``<Return>`` plus eine Plausibilitaets-
        pruefung.
        """
        import ast
        schreiber = self._adressschreiber()
        self.assertTrue(
            schreiber,
            "Keine Funktion speichert mehr ps5_ip - dann misst dieser Test "
            "nichts. Wurde der Schluessel umbenannt?")
        verdaechtig = []
        for knoten in ast.walk(ast.parse(self.text)):
            if not (isinstance(knoten, ast.Call)
                    and isinstance(knoten.func, ast.Attribute)
                    and knoten.func.attr == "trace_add"):
                continue
            for arg in knoten.args:
                if isinstance(arg, ast.Name) and arg.id in schreiber:
                    verdaechtig.append("%s (Zeile %d)" % (arg.id, knoten.lineno))
        self.assertEqual(
            verdaechtig, [],
            "Diese Funktionen schreiben die zentrale PS5-Adresse und haengen "
            "an trace_add - also an jedem Tastendruck.")

    def test_beide_adressfelder_pruefen_die_eingabe(self):
        """Gegenprobe: Wer speichert, hat vorher etwas belegt.

        Ohne diese Pruefung koennte ein Feld auf ``<FocusOut>`` umgestellt
        werden und trotzdem jede Zeichenfolge durchlassen.

        **Zwei Belege gelten, nicht einer.** Die erste Fassung dieses Tests
        verlangte ueberall ``_ist_plausible_ps5_adresse`` und meldete deshalb
        drei Stellen, an denen nichts falsch war: Sie speichern die Adresse
        erst, **nachdem** eine FTP-Verbindung dorthin zustande kam - ein
        staerkerer Beleg als jede Musterpruefung. Die Regel lautet also
        "geprueft **oder** verbunden".

        Ausserdem wird jetzt am Knoten gemessen, nicht am Namen. Die erste
        Fassung sammelte Funktions*namen* und beanstandete dadurch jedes
        ``_connect`` im Programm, auch die, die keine Adresse anfassen.
        """
        import ast
        ohne_beleg = []
        for knoten in ast.walk(ast.parse(self.text)):
            if not isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            aufrufe = self._aufrufe_im_eigenen_rumpf(knoten)
            speichert = any(
                isinstance(a.func, ast.Attribute)
                and a.func.attr == "_save_setting"
                and a.args and isinstance(a.args[0], ast.Constant)
                and a.args[0].value == "ps5_ip"
                for a in aufrufe)
            if not speichert:
                continue
            belegt = any(
                isinstance(a.func, ast.Attribute)
                and (a.func.attr == "_ist_plausible_ps5_adresse"
                     or "connect" in a.func.attr.lower())
                for a in aufrufe)
            if not belegt:
                ohne_beleg.append("%s (Zeile %d)"
                                  % (knoten.name, knoten.lineno))
        self.assertEqual(
            ohne_beleg, [],
            "Diese Funktionen speichern die zentrale PS5-Adresse, ohne sie "
            "vorher zu pruefen oder eine Verbindung dorthin aufgebaut zu "
            "haben.")

    @staticmethod
    def _aufrufe_im_eigenen_rumpf(funktion):
        """Aufrufe im Rumpf der Funktion - ohne die verschachtelter Funktionen.

        So wird ein Speichervorgang der **innersten** Funktion zugerechnet,
        die ihn enthaelt, und nicht zusaetzlich jeder darueberliegenden. Sonst
        haette das umgebende Fenster den Beleg seiner inneren Funktion
        geerbt - und ein fehlender waere unbemerkt geblieben.
        """
        import ast
        treffer = []
        rest = list(funktion.body)
        while rest:
            k = rest.pop()
            if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef,
                              ast.Lambda)):
                continue
            if isinstance(k, ast.Call):
                treffer.append(k)
            rest.extend(ast.iter_child_nodes(k))
        return treffer


class UebersetzungTests(unittest.TestCase):
    def test_alle_neuen_schluessel_in_beiden_sprachen(self):
        for schluessel in ("settings_dialog.ps5_section", "settings_dialog.ps5_hint",
                           "settings_dialog.ps5_ip_label",
                           "settings_dialog.ps5_ftp_port_label",
                           "settings_dialog.ps5_klog_port_label",
                           "settings_dialog.ps5_test_button",
                           "settings_dialog.ps5_invalid_ip",
                           "settings_dialog.ps5_invalid_port"):
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, STRINGS)
                for sprache in ("de", "en"):
                    text = translate(sprache, schluessel)
                    self.assertTrue(text.strip())
                    self.assertNotEqual(text, schluessel)

    def test_testmeldungen_tragen_ihre_platzhalter(self):
        for schluessel in ("settings_dialog.ps5_test_running",
                           "settings_dialog.ps5_test_ok",
                           "settings_dialog.ps5_test_failed"):
            with self.subTest(schluessel=schluessel):
                text = translate("de", schluessel, ip="1.2.3.4", port=2121)
                self.assertIn("1.2.3.4", text)
                self.assertIn("2121", text)


class PortAnpassungTests(unittest.TestCase):
    """Stimmt der eingestellte Port nicht, werden die bekannten mitprobiert."""

    def _obj(self):
        return _app({})

    def test_eingestellter_port_hat_vorrang(self):
        obj = self._obj()
        with mock.patch.object(APP.socket, "create_connection") as verbinden:
            verbinden.return_value.__enter__ = lambda s: s
            verbinden.return_value.__exit__ = lambda s, *a: False
            port = APP.PS5ConverterGUI._ps5_port_finden(obj, "1.2.3.4", 1337, "ftp")
        self.assertEqual(port, 1337)
        self.assertEqual(verbinden.call_args_list[0][0][0], ("1.2.3.4", 1337))

    def test_faellt_auf_den_naechsten_bekannten_port(self):
        obj = self._obj()

        def nur_2121(adresse, timeout=None):
            if adresse[1] != 2121:
                raise OSError("zu")
            return mock.MagicMock(__enter__=lambda s: s, __exit__=lambda s, *a: False)

        with mock.patch.object(APP.socket, "create_connection", side_effect=nur_2121):
            port = APP.PS5ConverterGUI._ps5_port_finden(obj, "1.2.3.4", 21, "ftp")
        self.assertEqual(port, 2121)

    def test_ohne_antwort_bleibt_der_eingestellte(self):
        obj = self._obj()
        with mock.patch.object(APP.socket, "create_connection", side_effect=OSError("zu")):
            port = APP.PS5ConverterGUI._ps5_port_finden(obj, "1.2.3.4", 4711, "ftp")
        self.assertEqual(port, 4711)

    def test_ohne_host_wird_nichts_probiert(self):
        obj = self._obj()
        with mock.patch.object(APP.socket, "create_connection") as verbinden:
            port = APP.PS5ConverterGUI._ps5_port_finden(obj, "  ", 2121, "ftp")
        verbinden.assert_not_called()
        self.assertEqual(port, 2121)

    def test_kandidaten_je_werkzeug(self):
        self.assertEqual(APP.PS5ConverterGUI._PS5_PORTKANDIDATEN["ftp"], APP.PS5_FTP_PORTS)
        self.assertIn(3232, APP.PS5ConverterGUI._PS5_PORTKANDIDATEN["klog"])

    def test_werkzeuge_nutzen_die_portsuche(self):
        text = QUELLE.read_text(encoding="utf-8")
        self.assertIn('self._ps5_port_finden(ip, port, "ftp")', text)
        self.assertIn('self._ps5_port_finden(ip, port, "klog")', text)


class KurzeTexteTests(unittest.TestCase):
    """Die Hinweise zu den Hintergrundbildern waren zu lang zum Lesen."""

    def test_bildhinweise_bleiben_kurz(self):
        for schluessel in ("settings_dialog.background_hint",
                           "settings_dialog.sidebar_background_hint"):
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    text = translate(sprache, schluessel, breite=1920, hoehe=1080)
                    self.assertLessEqual(len(text), 240)

    def test_masse_kommen_aus_der_messung(self):
        """Feste Zahlen waren falsch: die Leiste waechst mit der Skalierung."""
        for schluessel in ("settings_dialog.background_hint",
                           "settings_dialog.sidebar_background_hint"):
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    roh = translate(sprache, schluessel)
                    self.assertIn("{breite}", roh)
                    self.assertIn("{hoehe}", roh)
                    gefuellt = translate(sprache, schluessel, breite=2560, hoehe=1440)
                    self.assertIn("2560", gefuellt)
                    self.assertIn("1440", gefuellt)
                    self.assertNotIn("{", gefuellt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
