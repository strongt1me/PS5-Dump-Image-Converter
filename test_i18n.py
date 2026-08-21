"""Tests fuer ps5_validator.utils.i18n (De/En-Uebersetzung ueber stabile Schluessel)."""
import unittest

from ps5_validator.utils.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, ZSTD_LEVEL_KEYS, translate


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
        for key, _level in ZSTD_LEVEL_KEYS:
            de_text = translate("de", key)
            en_text = translate("en", key)
            self.assertNotEqual(de_text, key, f"Kein deutscher Text für {key} hinterlegt")
            self.assertNotEqual(en_text, key, f"Kein englischer Text für {key} hinterlegt")


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


if __name__ == "__main__":
    unittest.main()
