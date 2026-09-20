"""Tests fuer ps5_validator.utils.i18n (De/En-Uebersetzung ueber stabile Schluessel)."""
import ast
import re
import unittest
from pathlib import Path

from ps5_validator.utils.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, ZSTD_LEVEL_KEYS, translate

PROJEKT = Path(__file__).resolve().parent


class I18nTests(unittest.TestCase):
    def test_default_language_is_german(self) -> None:
        self.assertEqual(DEFAULT_LANGUAGE, "de")
        self.assertIn("de", SUPPORTED_LANGUAGES)
        self.assertIn("en", SUPPORTED_LANGUAGES)

    def test_german_translation_for_known_key(self) -> None:
        self.assertEqual(translate("de", "action.start"), "STARTEN")
        self.assertEqual(translate("de", "action.cancel"), "ABBRECHEN")

    def test_known_english_translations(self) -> None:
        self.assertEqual(translate("en", "action.start"), "START")
        self.assertEqual(translate("en", "action.cancel"), "CANCEL")
        self.assertEqual(translate("en", "titlebar.library"), "LIBRARY")
        self.assertEqual(translate("en", "mode.pack_folder"), "1. Convert dump folder")

    def test_unknown_key_falls_back_to_key_itself(self) -> None:
        self.assertEqual(translate("en", "Ein noch nicht übersetzter Text"), "Ein noch nicht übersetzter Text")
        self.assertEqual(translate("de", "kein.registrierter.schluessel"), "kein.registrierter.schluessel")

    def test_unknown_language_falls_back_to_german(self) -> None:
        self.assertEqual(translate("fr", "action.start"), "STARTEN")

    def test_kwargs_are_formatted_into_the_translated_template(self) -> None:
        self.assertEqual(
            translate("de", "main.config_for", task="1. Dump-Ordner konvertieren"),
            "Konfiguration für: 1. Dump-Ordner konvertieren",
        )
        self.assertEqual(
            translate("en", "main.config_for", task="1. Convert dump folder"),
            "Configuration for: 1. Convert dump folder",
        )

    def test_kwargs_mismatch_returns_unformatted_template_without_raising(self) -> None:
        # Fehlender Platzhalterwert darf keine Ausnahme auslösen, sondern liefert
        # die unformatierte Vorlage zurück.
        result = translate("de", "main.config_for", wrong_kwarg="x")
        self.assertIn("{task}", result)

    def test_zstd_level_keys_cover_all_four_compression_levels(self) -> None:
        levels = {level for _key, level in ZSTD_LEVEL_KEYS}
        self.assertEqual(levels, {1, 3, 6, 9})

    def test_zstd_level_keys_all_resolve_to_known_translations(self) -> None:
        # Direkt im Woerterbuch, nicht ueber translate(): Das faellt bei
        # fehlendem "en" auf den deutschen Text zurueck, und die englische
        # Haelfte dieses Tests war damit nie rot zu bekommen.
        from ps5_validator.utils.i18n import STRINGS

        for key, _level in ZSTD_LEVEL_KEYS:
            de_text = translate("de", key)
            self.assertNotEqual(de_text, key, f"Kein deutscher Text für {key} hinterlegt")
            self.assertTrue(STRINGS.get(key, {}).get("en"),
                            f"Kein englischer Text für {key} hinterlegt")


class AnfuehrungszeichenTests(unittest.TestCase):
    """Anfuehrungszeichen muessen paarweise und sprachrichtig sein.

    Deutsch oeffnet mit U+201E und schliesst mit U+201C, Englisch oeffnet
    mit U+201C und schliesst mit U+201D. Ein gerades Zeichen dazwischen
    ist fast immer ein Versehen beim Schreiben.

    Gefunden am 19.08.2026 in dump_rename.exists_message: typografisch
    geoeffnet, gerade geschlossen - sichtbar in einem Dialogfenster.
    Dieselbe Verwechslung hatte kurz zuvor ein Einfuegeskript zerlegt,
    weil sie dort ein Python-Literal beendete.
    """

    UNTEN = chr(0x201E)
    OBEN = chr(0x201C)
    RECHTS = chr(0x201D)
    GERADE = chr(34)

    def test_alle_texte_haben_paarige_anfuehrungszeichen(self):
        from ps5_validator.utils.i18n import STRINGS

        beanstandet = []
        for schluessel, sprachen in STRINGS.items():
            for sprache, text in sprachen.items():
                if not isinstance(text, str):
                    continue
                unten = text.count(self.UNTEN)
                oben = text.count(self.OBEN)
                rechts = text.count(self.RECHTS)
                if sprache == "de":
                    if unten != oben or rechts:
                        beanstandet.append("%s [de]: %s" % (schluessel, text[:80]))
                elif oben != rechts or unten:
                    beanstandet.append("%s [en]: %s" % (schluessel, text[:80]))
                if self.GERADE in text and (unten or oben or rechts):
                    beanstandet.append("%s [%s] gerades Zeichen: %s"
                                       % (schluessel, sprache, text[:80]))
        self.assertEqual(beanstandet, [],
                         "Unpaarige oder falsche Anfuehrungszeichen: "
                         + " | ".join(beanstandet))

    def test_die_pruefung_greift_ueberhaupt(self):
        # Ohne diese Kontrolle koennte die Pruefung oben stillschweigend
        # ins Leere laufen, falls STRINGS je anders aufgebaut waere.
        from ps5_validator.utils.i18n import STRINGS

        mit_zeichen = [s for s, sp in STRINGS.items()
                       if any(self.UNTEN in t for t in sp.values()
                              if isinstance(t, str))]
        self.assertGreater(len(mit_zeichen), 5,
                           "Kaum Texte mit Anfuehrungszeichen gefunden.")


class PlatzhalterTests(unittest.TestCase):
    """Platzhalter in den Texten gegen die Werte an der Aufrufstelle.

    Warum das eine eigene Pruefung braucht: ``translate`` loest bei einem
    fehlenden Wert keine Ausnahme aus, sondern gibt die Vorlage
    unformatiert zurueck (siehe der Test weiter oben). Der Anwender liest
    dann "Ordner {ordner} angelegt" - mit Klammern. Und hat ein Text in
    einer Sprache einen Platzhalter mehr, fehlt dieser Wert genau dort,
    wo die Sprache umgestellt ist: beim englischen Anwender, nie hier.

    Gemessen wird ueber den Syntaxbaum, ueber alle vier Wege zum Text.
    """

    #: Name des Aufrufs -> Stelle des Schluessels in den Argumenten.
    WEGE = {"_t": 0, "t": 0, "uebersetzen": 0, "translate": 1,
            "i18n_translate": 1, "_register_translatable": 1}

    #: Eigene Angaben dieser Wege, die nie Platzhalter sind.
    KEINE_PLATZHALTER = {"config_attr"}

    PLATZ = re.compile(r"\{([A-Za-z_][A-Za-z_0-9]*)[^{}]*\}")

    @classmethod
    def setUpClass(cls):
        from ps5_validator.utils.i18n import STRINGS

        cls.STRINGS = STRINGS
        cls.stellen: list[tuple[str, int, str, set[str], set[str]]] = []
        dateien = [PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"]
        dateien += sorted((PROJEKT / "ps5_validator").rglob("*.py"))
        for pfad in dateien:
            baum = ast.parse(pfad.read_text(encoding="utf-8", errors="replace"))
            for knoten in ast.walk(baum):
                if not isinstance(knoten, ast.Call):
                    continue
                name = getattr(knoten.func, "attr", "") or getattr(knoten.func, "id", "")
                stelle = cls.WEGE.get(name)
                if stelle is None or len(knoten.args) <= stelle:
                    continue
                arg = knoten.args[stelle]
                if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
                    continue  # zusammengesetzter Schluessel - nicht beurteilbar
                if any(kw.arg is None for kw in knoten.keywords):
                    continue  # **werte - von aussen nicht beurteilbar
                gegeben = {kw.arg for kw in knoten.keywords
                           if kw.arg and kw.arg not in cls.KEINE_PLATZHALTER}
                cls.stellen.append((pfad.name, knoten.lineno, arg.value,
                                    cls._platzhalter_von(arg.value), gegeben))
            del baum

    @classmethod
    def _platzhalter_von(cls, schluessel: str) -> set[str]:
        """Alle Platzhalter beider Sprachen - die Aufrufstelle bedient beide."""
        eintrag = cls.STRINGS.get(schluessel)
        if not isinstance(eintrag, dict):
            return set()
        gebraucht: set[str] = set()
        for sprache in ("de", "en"):
            text = eintrag.get(sprache, "")
            if isinstance(text, str):
                gebraucht |= set(cls.PLATZ.findall(text))
        return gebraucht

    def test_de_und_en_tragen_dieselben_platzhalter(self):
        schief = []
        for schluessel, eintrag in self.STRINGS.items():
            if not isinstance(eintrag, dict):
                continue
            de, en = eintrag.get("de", ""), eintrag.get("en", "")
            if not isinstance(de, str) or not isinstance(en, str) or not en:
                continue
            links, rechts = set(self.PLATZ.findall(de)), set(self.PLATZ.findall(en))
            if links != rechts:
                schief.append("%s de=%s en=%s" % (schluessel, sorted(links),
                                                  sorted(rechts)))
        self.assertEqual([], schief, "Ungleiche Platzhalter: " + " | ".join(schief))

    def test_jede_aufrufstelle_liefert_ihre_platzhalter(self):
        fehlt = ["%s:%d %s ohne %s" % (datei, zeile, schluessel,
                                       sorted(gebraucht - gegeben))
                 for datei, zeile, schluessel, gebraucht, gegeben in self.stellen
                 if gebraucht - gegeben]
        self.assertEqual([], fehlt,
                         "Der Text zeigt die Klammern statt des Werts: "
                         + " | ".join(fehlt))

    def test_keine_aufrufstelle_gibt_werte_ins_leere(self):
        # Harmlos in der Anzeige, aber ein Zeichen fuer eine halb
        # angekommene Umbenennung - und der naechste Platzhalter fehlt dann.
        ueberzaehlig = ["%s:%d %s ohne Platzhalter fuer %s"
                        % (datei, zeile, schluessel, sorted(gegeben - gebraucht))
                        for datei, zeile, schluessel, gebraucht, gegeben in self.stellen
                        if gegeben - gebraucht]
        self.assertEqual([], ueberzaehlig, " | ".join(ueberzaehlig))

    def test_jeder_schluessel_an_der_aufrufstelle_ist_hinterlegt(self):
        unbekannt = ["%s:%d %s" % (datei, zeile, schluessel)
                     for datei, zeile, schluessel, _g, _v in self.stellen
                     if schluessel not in self.STRINGS]
        self.assertEqual([], unbekannt,
                         "Unbekannter Schluessel - der Anwender liest ihn im "
                         "Klartext: " + " | ".join(unbekannt))

    def test_die_pruefung_greift_ueberhaupt(self):
        self.assertGreater(len(self.stellen), 2000,
                           "kaum Aufrufstellen gefunden - die Pruefung misst nichts")
        mit_platzhaltern = [s for s in self.stellen if s[3]]
        self.assertGreater(len(mit_platzhaltern), 200,
                           "kaum Texte mit Platzhaltern gefunden")
        self.assertGreater(len(self.STRINGS), 2000)


if __name__ == "__main__":
    unittest.main()
