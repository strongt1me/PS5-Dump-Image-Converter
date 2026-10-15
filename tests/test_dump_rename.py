"""Tests fuer ps5_validator.utils.dump_rename (reine Namens-/Konfidenzlogik)."""
import unittest

from ps5_validator.utils.dump_rename import (
    CONFIDENCE_FAILED,
    CONFIDENCE_NEEDS_REVIEW,
    CONFIDENCE_READY,
    build_presets,
    compute_confidence,
    is_generic_folder_name,
    sanitize_name,
)


class DumpRenameTests(unittest.TestCase):
    def test_sanitize_name_strips_invalid_chars_and_whitespace(self) -> None:
        self.assertEqual(sanitize_name('My:Game<Title>?  Extra   Spaces'), "MyGameTitle Extra Spaces")

    def test_generic_folder_names_detected_case_insensitively(self) -> None:
        self.assertTrue(is_generic_folder_name("Downloads"))
        self.assertTrue(is_generic_folder_name("BACKUP"))
        self.assertFalse(is_generic_folder_name("Spider-Man 2"))

    def test_confidence_levels(self) -> None:
        self.assertEqual(compute_confidence(False, False, False), CONFIDENCE_FAILED)
        self.assertEqual(compute_confidence(True, False, False), CONFIDENCE_NEEDS_REVIEW)
        self.assertEqual(compute_confidence(True, True, False), CONFIDENCE_NEEDS_REVIEW)
        self.assertEqual(compute_confidence(True, True, True), CONFIDENCE_READY)

    def test_build_presets_without_ppsa_are_empty(self) -> None:
        presets = build_presets("", "Some Title", "01.00", has_ppsa=False, has_version=True)
        self.assertEqual(presets["PPSA only"], "")
        self.assertEqual(presets["PPSA + Title"], "")
        self.assertEqual(presets["PPSA + Title + Version"], "")

    def test_build_presets_with_full_metadata(self) -> None:
        presets = build_presets("PPSA01234", "Spider-Man", "01.005.000", has_ppsa=True, has_version=True)
        self.assertEqual(presets["PPSA only"], "PPSA01234")
        self.assertEqual(presets["PPSA + Title"], "PPSA01234 Spider-Man")
        self.assertEqual(presets["PPSA + Title + Version"], "PPSA01234 Spider-Man (01.005.000)")

    def test_build_presets_without_version_falls_back(self) -> None:
        presets = build_presets("PPSA01234", "Spider-Man", "–", has_ppsa=True, has_version=False)
        self.assertEqual(presets["PPSA + Title + Version"], "PPSA01234 Spider-Man")


class Ps4KennungTests(unittest.TestCase):
    """Eine PS4-Kennung darf nicht als PPSA durchgehen.

    Das Fenster prueft die Title-ID mit ``re.fullmatch(r"[A-Z]{4}d{5}")``.
    Diese Form trifft auch ``CUSA00000`` und ``PUSA00000`` - PS4-Kennungen.
    Der Wert heisst aber ``hat_ppsa``, und ``build_presets`` baut daraus
    PS5-Namen ("Ohne gueltige PPSA-Title-ID bleiben alle Presets leer").
    Bei einem PS4-Dump sprang die Einschaetzung deshalb auf gruen und das
    Fenster bot drei Namen an, die es gar nicht anbieten wollte.

    Geprueft wird hier die Liste, an der das Fenster jetzt haengt - der
    Quelltextabgleich steht in test_werkzeugfeinheiten.
    """

    def test_die_liste_kennt_die_ps5_kennungen(self):
        from ps5_validator.utils.ps4_werkzeug import PS5_KENNUNGEN
        for kennung in ("PPSA", "PPSS", "PPUS", "PPJP"):
            self.assertIn(kennung, PS5_KENNUNGEN)

    def test_die_liste_kennt_keine_ps4_kennungen(self):
        from ps5_validator.utils.ps4_werkzeug import PS5_KENNUNGEN
        for kennung in ("CUSA", "PUSA"):
            self.assertNotIn(kennung, PS5_KENNUNGEN)

    def test_ohne_ppsa_bleiben_die_vorschlaege_leer(self):
        """Anker: Genau darauf stuetzt sich die Behebung."""
        leer = build_presets("CUSA12345", "Spiel", "01.00", False, True)
        self.assertEqual({""}, set(leer.values()))
        self.assertEqual(CONFIDENCE_FAILED, compute_confidence(False, True, True))


class DoppelteVorschlaegeTests(unittest.TestCase):
    """Zwei Vorschlaege koennen denselben Namen ergeben.

    ``build_presets`` liefert drei **benannte** Vorschlaege, nicht drei
    verschiedene Namen. Ohne Versionsangabe sind "PPSA + Titel" und
    "PPSA + Titel + Version" identisch, ohne Titel sogar alle drei.

    Im Fenster bekommen die Radiobuttons ``value=name``. Zwei mit
    demselben Wert teilen sich eine Auswahl - Tk zeigt beide als
    markiert, und derselbe Vorschlag stand zweimal da. Das Fenster fasst
    gleiche Namen deshalb zusammen; hier steht der Beleg, dass es sie
    ueberhaupt geben kann.
    """

    def test_ohne_version_fallen_zwei_zusammen(self):
        p = build_presets("PPSA12345", "Mein Spiel", "", True, False)
        werte = [w for w in p.values() if w]
        self.assertNotEqual(len(werte), len(set(werte)),
                            "Wenn hier keine Dubletten mehr entstehen, ist "
                            "die Zusammenfassung im Fenster unnoetig "
                            "geworden - dann darf sie raus, aber bewusst.")

    def test_ohne_titel_fallen_alle_drei_zusammen(self):
        p = build_presets("PPSA12345", "", "", True, False)
        werte = [w for w in p.values() if w]
        self.assertEqual(1, len(set(werte)))

    def test_mit_titel_und_version_bleiben_es_drei(self):
        """Anker: Sonst wuerde die Zusammenfassung echte Vorschlaege schlucken."""
        p = build_presets("PPSA12345", "Mein Spiel", "01.000.000", True, True)
        werte = [w for w in p.values() if w]
        self.assertEqual(3, len(set(werte)))


if __name__ == "__main__":
    unittest.main()
