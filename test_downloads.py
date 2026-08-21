# -*- coding: utf-8 -*-
"""Tests fuer die Download-Verwaltung (Updates & Patches).

Prueft die reine Logik in ``ps5_validator.utils.ps5_downloads`` an einer echten,
am 16.08.2026 nachgemessenen Adresse sowie die Verdrahtung im Hauptprogramm
(Menueeintrag, i18n-Schluessel, Weiterleitung des Download-Klicks).
"""
import io
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ps5_validator.utils import ps5_downloads as dl
from ps5_validator.utils import i18n

# Echte Adresse aus dem Praxistest - Grundlage aller Zerlegungspruefungen.
ECHTE_URL = (
    "http://gst.prod.dl.playstation.net/gst/prod/00/PPSA19015_00/app/pkg/5/"
    "f_2f6a8429bc090a765d66f5d3d46b0db710967ef4b40c57005ba8e5ce4b6abff4/"
    "UP8016-PPSA19015_00-0489895718491618.pkg"
)

HAUPTDATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "PS5ImageConverter_Pro_FINAL_revised.py")


class AdresseZerlegenTests(unittest.TestCase):
    """parse_pkg_url an echter und an fehlerhafter Eingabe."""

    def test_echte_adresse_vollstaendig_zerlegt(self):
        d = dl.parse_pkg_url(ECHTE_URL)
        self.assertEqual(d["title_id"], "PPSA19015")
        self.assertEqual(d["content_id"], "UP8016-PPSA19015_00-0489895718491618")
        self.assertEqual(d["region_code"], "UP8016")
        self.assertEqual(d["dateiname"], "UP8016-PPSA19015_00-0489895718491618.pkg")
        self.assertEqual(d["host"], "gst.prod.dl.playstation.net")
        self.assertEqual(d["url"], ECHTE_URL)

    def test_anfuehrungszeichen_werden_abgestreift(self):
        d = dl.parse_pkg_url(f'  "{ECHTE_URL}"  ')
        self.assertEqual(d["url"], ECHTE_URL)

    def test_https_wird_ebenfalls_angenommen(self):
        self.assertTrue(dl.ist_pkg_url(ECHTE_URL.replace("http://", "https://", 1)))

    def test_cusa_und_plas_kennungen(self):
        for kennung in ("CUSA12345", "PLAS10000"):
            url = ECHTE_URL.replace("PPSA19015", kennung)
            self.assertEqual(dl.parse_pkg_url(url)["title_id"], kennung)

    def test_fremder_host_nennt_den_host(self):
        url = ECHTE_URL.replace("gst.prod.dl.playstation.net", "beispiel.invalid")
        with self.assertRaises(dl.DownloadAdresseUngueltig) as ctx:
            dl.parse_pkg_url(url)
        self.assertIn("beispiel.invalid", str(ctx.exception))

    def test_keine_pkg_datei(self):
        with self.assertRaises(dl.DownloadAdresseUngueltig) as ctx:
            dl.parse_pkg_url(ECHTE_URL[:-4] + ".zip")
        self.assertIn(".pkg", str(ctx.exception))

    def test_ohne_content_id_im_namen(self):
        url = ECHTE_URL.rsplit("/", 1)[0] + "/beliebig.pkg"
        with self.assertRaises(dl.DownloadAdresseUngueltig) as ctx:
            dl.parse_pkg_url(url)
        self.assertIn("Content-ID", str(ctx.exception))

    def test_kein_http_schema(self):
        with self.assertRaises(dl.DownloadAdresseUngueltig):
            dl.parse_pkg_url("ftp://gst.prod.dl.playstation.net/x.pkg")
        with self.assertRaises(dl.DownloadAdresseUngueltig):
            dl.parse_pkg_url("")

    def test_jede_ablehnung_hat_eigene_meldung(self):
        meldungen = set()
        for kaputt in ("nichts",
                       ECHTE_URL.replace("gst.prod.dl.playstation.net", "beispiel.invalid"),
                       ECHTE_URL[:-4] + ".zip",
                       ECHTE_URL.rsplit("/", 1)[0] + "/beliebig.pkg"):
            with self.assertRaises(dl.DownloadAdresseUngueltig) as ctx:
                dl.parse_pkg_url(kaputt)
            meldungen.add(str(ctx.exception))
        self.assertEqual(len(meldungen), 4)

    def test_ist_pkg_url_wirft_nicht(self):
        self.assertFalse(dl.ist_pkg_url("https://prosperopatches.com/PPSA19015"))
        self.assertTrue(dl.ist_pkg_url(ECHTE_URL))


class EinordnungTests(unittest.TestCase):
    """Neueste Version = Update, aeltere = Patch."""

    def test_neueste_ist_update(self):
        self.assertEqual(dl.art_bestimmen(True), dl.ART_UPDATE)

    def test_aeltere_ist_patch(self):
        self.assertEqual(dl.art_bestimmen(False), dl.ART_PATCH)

    def test_unbekannt_landet_als_update(self):
        # Lieber im Hauptordner als in einer falschen Ablage.
        self.assertEqual(dl.art_bestimmen(None), dl.ART_UPDATE)

    def test_ordnernamen_wie_gefordert(self):
        self.assertEqual(dl.ORDNER_UPDATE, "PS5 Spiele Updates")
        self.assertEqual(dl.ORDNER_PATCH, "Patches")


class ZielpfadTests(unittest.TestCase):
    """Zielordner, Zielpfad, Teildatei und Bestandsaufnahme."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dl_test_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_getrennte_ordner(self):
        self.assertTrue(dl.zielordner(self.tmp, dl.ART_UPDATE).endswith(dl.ORDNER_UPDATE))
        self.assertTrue(dl.zielordner(self.tmp, dl.ART_PATCH).endswith(dl.ORDNER_PATCH))
        self.assertNotEqual(dl.zielordner(self.tmp, dl.ART_UPDATE),
                            dl.zielordner(self.tmp, dl.ART_PATCH))

    def test_teildatei_endung(self):
        ziel = dl.zielpfad(self.tmp, dl.ART_UPDATE, "a.pkg")
        self.assertEqual(dl.teildatei(ziel), ziel + ".teil")

    def test_bereits_vorhanden_findet_in_beiden_ordnern(self):
        name = "UP8016-PPSA19015_00-0489895718491618.pkg"
        for art in (dl.ART_UPDATE, dl.ART_PATCH):
            pfad = dl.zielpfad(self.tmp, art, name)
            os.makedirs(os.path.dirname(pfad), exist_ok=True)
            with io.open(pfad, "wb") as fh:
                fh.write(b"x")
            self.assertEqual(dl.bereits_vorhanden(self.tmp, name), pfad)
            os.remove(pfad)
        self.assertEqual(dl.bereits_vorhanden(self.tmp, name), "")

    def test_vorhandene_dateien_liest_beide_ordner(self):
        namen = {
            dl.ART_UPDATE: "UP8016-PPSA19015_00-0489895718491618.pkg",
            dl.ART_PATCH: "EP9000-CUSA12345_00-ABCDEF0123456789.pkg",
        }
        for art, name in namen.items():
            pfad = dl.zielpfad(self.tmp, art, name)
            os.makedirs(os.path.dirname(pfad), exist_ok=True)
            with io.open(pfad, "wb") as fh:
                fh.write(b"0123456789")
        gefunden = {e["art"]: e for e in dl.vorhandene_dateien(self.tmp)}
        self.assertEqual(set(gefunden), {dl.ART_UPDATE, dl.ART_PATCH})
        self.assertEqual(gefunden[dl.ART_UPDATE]["title_id"], "PPSA19015")
        self.assertEqual(gefunden[dl.ART_PATCH]["title_id"], "CUSA12345")
        self.assertEqual(gefunden[dl.ART_UPDATE]["bytes"], "10")

    def test_teildateien_und_fremdes_werden_uebergangen(self):
        ordner = dl.zielordner(self.tmp, dl.ART_UPDATE)
        os.makedirs(ordner, exist_ok=True)
        for name in ("UP8016-PPSA19015_00-0489895718491618.pkg.teil",
                     "liesmich.txt", "ohne_id.pkg"):
            with io.open(os.path.join(ordner, name), "wb") as fh:
                fh.write(b"x")
        self.assertEqual(dl.vorhandene_dateien(self.tmp), [])

    def test_fehlender_ordner_ist_kein_fehler(self):
        self.assertEqual(dl.vorhandene_dateien(os.path.join(self.tmp, "gibtsnicht")), [])


class MehrereAdressenTests(unittest.TestCase):
    """eingehende_urls trennt, filtert und entdoppelt."""

    def test_mehrere_zeilen(self):
        zweite = ECHTE_URL.replace("PPSA19015", "CUSA12345")
        text = f"{ECHTE_URL}\n{zweite}\n"
        self.assertEqual(dl.eingehende_urls(text), [ECHTE_URL, zweite])

    def test_doppelte_fallen_weg_reihenfolge_bleibt(self):
        zweite = ECHTE_URL.replace("PPSA19015", "CUSA12345")
        self.assertEqual(dl.eingehende_urls(f"{ECHTE_URL} {zweite} {ECHTE_URL}"),
                         [ECHTE_URL, zweite])

    def test_beiwerk_wird_uebergangen(self):
        self.assertEqual(
            dl.eingehende_urls(f"Hier bitte: {ECHTE_URL} danke!"), [ECHTE_URL])

    def test_leer_und_unbrauchbar(self):
        self.assertEqual(dl.eingehende_urls(""), [])
        self.assertEqual(dl.eingehende_urls("nur Text, keine Adresse"), [])


class VerdrahtungTests(unittest.TestCase):
    """Der Weg vom Knopf im Spieleinfo-Fenster bis in den Verwalter."""

    @classmethod
    def setUpClass(cls):
        with io.open(HAUPTDATEI, encoding="utf-8") as fh:
            cls.quelle = fh.read()

    def test_menueeintrag_vorhanden(self):
        self.assertIn('("titlebar.downloads", "_show_downloads_manager")', self.quelle)

    def test_modul_eingebunden(self):
        self.assertIn("from ps5_validator.utils import ps5_downloads", self.quelle)

    def test_download_klick_geht_nicht_mehr_direkt_in_den_browser(self):
        # Frueher: self._open_url(url) - jetzt ueber die Weiche _download_starten.
        self.assertIn("self._download_starten(url, self._patch_latest.get(iid))",
                      self.quelle)

    def test_alle_wesentlichen_methoden_da(self):
        for name in ("_download_starten", "_download_basis", "_download_basis_waehlen",
                     "_show_downloads_manager", "_download_aufnehmen", "_download_worker"):
            self.assertIn(f"def {name}(", self.quelle, name)

    def test_speicherort_auch_in_den_einstellungen(self):
        self.assertIn("settings_dialog.downloads_choose_button", self.quelle)
        self.assertIn('self._save_setting("download_dir", "")', self.quelle)

    def test_ist_neueste_wird_je_zeile_gemerkt(self):
        self.assertIn("self._patch_latest[iid] = bool(is_latest)", self.quelle)

    def test_teildatei_wird_erst_am_ende_umbenannt(self):
        # Schuetzt davor, dass ein Abbruch eine halbe Datei als fertig hinterlaesst.
        self.assertIn("os.replace(teil, ziel)", self.quelle)

    def test_fortsetzen_per_range(self):
        self.assertIn('kopfzeilen["Range"] = f"bytes={schon}-"', self.quelle)


def _gui():
    """Ein Programmobjekt ohne Tk, gerade genug fuer die Aufnahme-Logik.

    Der Konstruktor baut ein ganzes Fenster auf; hier interessiert nur, was
    _download_aufnehmen mit einer Adresse macht. Also __new__ und die paar
    Felder, die der Weg tatsaechlich anfasst.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("_ps5_haupt", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("_ps5_haupt", modul)
    spec.loader.exec_module(modul)
    gui = modul.PS5ConverterGUI.__new__(modul.PS5ConverterGUI)

    gui._downloads = {}
    gui._eingefuegt = []          # Was in die Liste gewandert waere
    gui._protokoll = []           # Was ins Log geschrieben wurde
    gui._fenster = []             # Hinweisfenster, die aufgegangen waeren
    gui._threads = []             # Gestartete Downloads

    class _Baum:
        def winfo_exists(self):
            return True

        def insert(self, _parent, _pos, values=()):
            iid = "I%03d" % len(gui._eingefuegt)
            gui._eingefuegt.append(values)
            return iid

    gui._downloads_tree = _Baum()
    gui._t = lambda key, **kw: key
    gui._append_to_log = lambda zeile: gui._protokoll.append(zeile)
    gui._load_setting = lambda key, default: {"download_dir": tempfile.gettempdir()}.get(
        key, default)
    gui._save_setting = lambda key, value: None
    gui._fmt_bytes = lambda n: str(n)
    gui._letzte_patch_ist_neueste = None
    return gui, modul


class StapelaufnahmeTests(unittest.TestCase):
    """Mehrere Adressen auf einmal.

    Gemeldet am 19.08.2026: "Auch wird mir nur ein Downloadlink angenommen und
    heruntergeladen. Moechte man mehrere in das Fenster einfuegen, passiert
    nichts."
    """

    def setUp(self):
        self.gui, self.modul = _gui()
        # Die Downloads selbst duerfen hier nicht loslaufen.
        self.gui._download_worker = lambda iid: None
        self.echt = ECHTE_URL
        self.zweite = ECHTE_URL.replace("0489895718491618", "0489895718491619")

    def _threads_abfangen(self):
        import threading
        class _Falsch:
            def __init__(self, *a, **kw):
                pass
            def start(self):
                pass
        self._alt = threading.Thread
        threading.Thread = _Falsch
        self.addCleanup(lambda: setattr(threading, "Thread", self._alt))

    def test_zwei_adressen_werden_beide_aufgenommen(self):
        self._threads_abfangen()
        anzahl = self.gui._downloads_uebernehmen(
            self.echt + "\n" + self.zweite, still=True)
        self.assertEqual(anzahl, 2)
        self.assertEqual(len(self.gui._eingefuegt), 2)

    def test_dieselbe_adresse_zweimal_zaehlt_einmal(self):
        # Beim Ueberwachen der Zwischenablage sonst ein Dauerlauf: Wer
        # dieselbe Adresse noch einmal kopiert, bekaeme sie noch einmal.
        self._threads_abfangen()
        self.gui._downloads_uebernehmen(self.echt, still=True)
        anzahl = self.gui._downloads_uebernehmen(self.echt, still=True)
        self.assertEqual(anzahl, 0)
        self.assertEqual(len(self.gui._eingefuegt), 1)

    def test_fehlgeschlagene_lassen_sich_erneut_aufnehmen(self):
        self._threads_abfangen()
        self.gui._downloads_uebernehmen(self.echt, still=True)
        for eintrag in self.gui._downloads.values():
            eintrag["status"] = "failed"
        self.assertEqual(self.gui._downloads_uebernehmen(self.echt, still=True), 1)

    def test_unbrauchbare_zeilen_oeffnen_kein_fenster(self):
        # Wer einen Textblock aus einer Seite einfuegt, hat Zeilen dabei, die
        # keine Adresse sind. Frueher kam pro Zeile ein Hinweisfenster.
        self._threads_abfangen()
        block = "Beschreibung der Seite\nhttps://example.com/kein.pkg\n" + self.echt
        anzahl = self.gui._downloads_uebernehmen(block, still=True)
        self.assertEqual(anzahl, 1)

    def test_einzelaufnahme_meldet_weiterhin_per_fenster(self):
        # Ausserhalb des Stapels bleibt das Hinweisfenster: Wer genau eine
        # Adresse einfuegt, will wissen, warum sie nicht angenommen wurde.
        gemeldet = []
        vorher = self.modul.messagebox.showwarning
        self.modul.messagebox.showwarning = lambda *a, **kw: gemeldet.append(a)
        self.addCleanup(lambda: setattr(self.modul.messagebox, "showwarning", vorher))
        self.gui.root = object()  # nur als parent-Ersatz, wird nicht benutzt
        ergebnis = self.gui._download_aufnehmen("kein-link")
        self.assertEqual(ergebnis, "ungueltig")
        self.assertEqual(len(gemeldet), 1)


class ZwischenablageTests(unittest.TestCase):
    """Kopierte Adressen landen von selbst in der Liste.

    Seit v1.8.61 laeuft die Ueberwachung unabhaengig vom Download-Fenster:
    Man sammelt Links im Browser, waehrend das Programm im Hintergrund steht.
    Die erste Fassung endete mit dem Schliessen des Fensters - ausdruecklich
    zurueckgenommen.
    """

    def setUp(self):
        self.gui, self.modul = _gui()
        self.gui._download_worker = lambda iid: None
        self.gui._zwischenablage_after_id = None
        self.gui._zwischenablage_letzter = ""
        self.geplant = []
        self.gespeichert = {}
        self.gui._save_setting = lambda k, v: self.gespeichert.__setitem__(k, v)

        pruefstand = self

        class _Var:
            def __init__(self, wert=True):
                self.wert = wert

            def get(self):
                return self.wert

            def set(self, wert):
                self.wert = wert

        class _Root:
            def __init__(self, inhalt):
                self.inhalt = inhalt
                self.abbestellt = []

            def clipboard_get(self):
                if not self.inhalt:
                    raise RuntimeError("leer")
                return self.inhalt

            def after(self, ms, fn):
                pruefstand.geplant.append(ms)
                return "nach%d" % len(pruefstand.geplant)

            def after_cancel(self, kennung):
                self.abbestellt.append(kennung)

        self._Var = _Var
        self._Root = _Root

    def _ohne_threads(self):
        import threading
        alt = threading.Thread
        threading.Thread = type("X", (), {"__init__": lambda s, *a, **k: None,
                                          "start": lambda s: None})
        self.addCleanup(lambda: setattr(threading, "Thread", alt))

    def test_kopierte_adresse_wird_aufgenommen(self):
        self._ohne_threads()
        self.gui._zwischenablage_var = self._Var(True)
        self.gui.root = self._Root(ECHTE_URL)
        self.gui._zwischenablage_tick()
        self.assertEqual(len(self.gui._eingefuegt), 1)

    def test_unveraenderter_inhalt_wird_nicht_erneut_genommen(self):
        self._ohne_threads()
        self.gui._zwischenablage_var = self._Var(True)
        self.gui.root = self._Root(ECHTE_URL)
        self.gui._zwischenablage_tick()
        self.gui._zwischenablage_tick()
        self.assertEqual(len(self.gui._eingefuegt), 1)

    def test_abgeschaltet_passiert_nichts(self):
        self.gui._zwischenablage_var = self._Var(False)
        self.gui.root = self._Root(ECHTE_URL)
        self.gui._zwischenablage_tick()
        self.assertEqual(len(self.gui._eingefuegt), 0)
        self.assertEqual(self.geplant, [], "Abgeschaltet darf sich nichts neu planen.")

    def test_naechster_lauf_wird_geplant(self):
        # Ohne diese Zeile liefe die Ueberwachung genau einmal.
        self.gui._zwischenablage_var = self._Var(True)
        self.gui.root = self._Root("")
        self.gui._zwischenablage_tick()
        self.assertEqual(self.geplant, [700])

    def test_geschlossenes_fenster_beendet_sie_nicht(self):
        # Der Kern der Aenderung: Frueher endete die Ueberwachung hier.
        class _Weg:
            def winfo_exists(self):
                return False

        self._ohne_threads()
        self.gui._downloads_tree = _Weg()
        self.gui._show_downloads_manager = lambda: None
        self.gui._zwischenablage_var = self._Var(True)
        self.gui.root = self._Root(ECHTE_URL)
        self.gui._zwischenablage_tick()
        self.assertEqual(self.geplant, [700],
                         "Ohne Fenster plant sich die Ueberwachung nicht mehr.")

    def test_ohne_haken_entscheidet_die_einstellung(self):
        # Das Fenster ist zu, den Haken gibt es nicht mehr - der Zustand steht
        # dann allein in den Einstellungen.
        self.gui._zwischenablage_var = None
        self.gui._load_setting = lambda k, d: True if k == "downloads_watch_clipboard" else d
        self.assertTrue(self.gui._zwischenablage_an())
        self.gui._load_setting = lambda k, d: False if k == "downloads_watch_clipboard" else d
        self.assertFalse(self.gui._zwischenablage_an())

    def test_start_nimmt_nicht_auf_was_schon_kopiert_war(self):
        # Sonst landet beim Einschalten sofort das in der Liste, was zufaellig
        # gerade in der Zwischenablage lag.
        self._ohne_threads()
        self.gui._zwischenablage_var = self._Var(True)
        self.gui.root = self._Root(ECHTE_URL)
        self.gui._zwischenablage_starten()
        self.assertEqual(len(self.gui._eingefuegt), 0)
        self.assertEqual(self.geplant, [700])

    def test_zweiter_start_plant_nicht_doppelt(self):
        # Zwei Laeufe wuerden jeden Fund doppelt melden.
        self.gui._zwischenablage_var = self._Var(True)
        self.gui.root = self._Root("")
        self.gui._zwischenablage_starten()
        self.gui._zwischenablage_starten()
        self.assertEqual(len(self.geplant), 1)

    def test_stoppen_bestellt_den_lauf_ab(self):
        self.gui._zwischenablage_var = self._Var(True)
        self.gui.root = self._Root("")
        self.gui._zwischenablage_starten()
        kennung = self.gui._zwischenablage_after_id
        self.gui._zwischenablage_stoppen()
        self.assertIsNone(self.gui._zwischenablage_after_id)
        self.assertEqual(self.gui.root.abbestellt, [kennung])

    def test_umschalten_merkt_die_wahl(self):
        self.gui._zwischenablage_var = self._Var(True)
        self.gui.root = self._Root("")
        self.gui._zwischenablage_umschalten()
        self.assertIs(self.gespeichert["downloads_watch_clipboard"], True)
        self.gui._zwischenablage_var.set(False)
        self.gui._zwischenablage_umschalten()
        self.assertIs(self.gespeichert["downloads_watch_clipboard"], False)


class TextmenueTests(unittest.TestCase):
    """Rechtsklick in einem Eingabefeld oeffnet Ausschneiden/Kopieren/Einfuegen.

    Der Rechtsklick war nur am Hauptfenster belegt. Nebenfenster sind eigene
    Toplevels und erben das nicht - im Feld fuer Download-Adressen passierte
    deshalb gar nichts (gemeldet 19.08.2026).
    """

    @classmethod
    def setUpClass(cls):
        with io.open(HAUPTDATEI, encoding="utf-8") as fh:
            cls.quelle = fh.read()

    def test_an_der_klasse_gebunden_nicht_am_einzelnen_feld(self):
        # Nur so bekommen auch Felder das Menue, die es beim Aufbau noch
        # nicht gab - und das sind fast alle.
        self.assertIn('self.root.bind_class(klasse, taste, self._textmenue_zeigen',
                      self.quelle)

    def test_alle_textklassen_abgedeckt(self):
        for klasse in ("Entry", "TEntry", "Text", "Spinbox", "TSpinbox", "TCombobox"):
            self.assertIn('"%s"' % klasse, self.quelle, klasse)

    def test_mac_bekommt_seine_eigene_taste(self):
        # Auf dem Mac liefert die rechte Taste Button-2, nicht Button-3.
        self.assertIn('tasten += ["<Button-2>", "<Control-Button-1>"]', self.quelle)

    def test_menue_wird_beim_sprachwechsel_neu_beschriftet(self):
        self.assertIn("_TEXTMENUE_EINTRAEGE", self.quelle)
        self.assertIn("textmenue.entryconfigure(position, label=self._t(label_key))",
                      self.quelle)


class I18nTests(unittest.TestCase):
    """Jeder benutzte Schluessel existiert in beiden Sprachen."""

    @classmethod
    def setUpClass(cls):
        with io.open(HAUPTDATEI, encoding="utf-8") as fh:
            cls.quelle = fh.read()

    def test_benutzte_schluessel_vollstaendig(self):
        benutzt = set(re.findall(
            r'_t\(\s*["\']((?:downloads|settings_dialog)\.[a-z_0-9]+)', self.quelle))
        benutzt |= {"downloads.kind_update", "downloads.kind_patch", "titlebar.downloads"}
        fehlend = sorted(k for k in benutzt if k not in i18n.STRINGS)
        self.assertEqual(fehlend, [], f"Nicht uebersetzt: {fehlend}")
        for sprache in ("de", "en"):
            luecken = sorted(k for k in benutzt if sprache not in i18n.STRINGS[k])
            self.assertEqual(luecken, [], f"{sprache} fehlt: {luecken}")

    def test_protokollzeilen_enden_mit_umbruch(self):
        # Ohne \n kleben die Zeilen im Konsolenfenster aneinander.
        for k in ("downloads.added", "downloads.finished",
                  "downloads.already_queued", "downloads.details_opened"):
            for sprache in ("de", "en"):
                self.assertTrue(i18n.STRINGS[k][sprache].endswith("\n"), f"{k}/{sprache}")

    def test_platzhalter_stimmen_zwischen_den_sprachen(self):
        muster = re.compile(r"\{([a-z_]+)")
        for k, werte in i18n.STRINGS.items():
            if not k.startswith("downloads."):
                continue
            self.assertEqual(set(muster.findall(werte["de"])),
                             set(muster.findall(werte["en"])), k)


if __name__ == "__main__":
    unittest.main(verbosity=2)
