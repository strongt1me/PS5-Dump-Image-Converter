"""Der Bedienzustand des Hauptfensters, unabhaengig von der Oberflaeche.

Hier liegen die Werte, die das Programm waehrend der Arbeit traegt: welche
Aufgabe gewaehlt ist, wo Quelle und Ziel liegen, wie stark gepackt wird, wie
weit der Fortschritt ist. Bis August 2026 waren das 22 Tk-Variablen, die an
einem Tk-Fenster hingen und fuer eine WPF-Ansicht unerreichbar waren.

Der Behaelter aendert daran nur eines: Die **Wahrheit** liegt jetzt in
neutralen Werten. Die Tk-Oberflaeche bekommt ueber
:func:`ps5_validator.ui.tk_bruecke.koppeln` weiterhin echte Tk-Variablen fuer
ihre ``textvariable=``-Bindungen, und der bestehende Quelltext merkt vom
Umbau nichts.

Die Namen sind absichtlich dieselben wie die der bisherigen Attribute
(``source_path``, ``dest_path``, ...). Beim Umstellen der Aufrufstellen ist
damit ohne Nachschlagen klar, was wohin gehoert - und beim Suchen im
Quelltext findet man beide Seiten mit demselben Wort.

Nicht enthalten sind die rund 70 Variablen, die nur innerhalb eines Dialogs
leben. Sie gehoeren zu ihrem Fenster und werden mit ihm umgestellt.
"""
from __future__ import annotations

from ps5_validator.ui.zustand import (Ganzzahl, Kommazahl, Schalter,
                                      Strom, Text, Wert)

#: Platzhalter fuer eine noch unbekannte Angabe. Ein Gedankenstrich, kein
#: Bindestrich - so steht er auch in der Tk-Fassung.
UNBEKANNT = "–"

#: Die dreizehn Angaben zum erkannten Spiel, in der Reihenfolge der
#: Tk-Fassung.
#:
#: Sie sind der einzige Teil der rund 70 Dialogvariablen, der wirklich
#: geteilt werden muss: Die Ablauflogik liest sie aus dem Abbild oder holt
#: sie aus dem Netz, und beide Oberflaechen zeigen sie an. Alle uebrigen
#: leben nur innerhalb ihres Dialogs und bleiben dort, wo sie sind.
#:
#: ``content_id`` und ``ampr_emu`` kamen am 03.09.2026 dazu - angeregt von
#: ``mkpfs.game_metadata`` aus MkPFS 1.0.0, das beides liest. Die
#: ``content_id`` steht in der ``param.json`` und sagt Region und Ausgabe
#: genauer als die Title-ID; ``ampr_emu`` sagt, ob die Quelle die
#: AMPR-Emulation mitbringt (``fakelib/libSceAmpr.sprx``).
METADATENFELDER: tuple[str, ...] = (
    "title", "title_id", "content_id", "version", "required_firmware",
    "sdk_stand", "region", "publisher", "category", "ampr_emu",
    "release_date", "genre", "platform",
)


class Bedienzustand:
    """Alle Werte des Hauptfensters an einer Stelle.

    Args:
        zielpfad: Zuletzt benutzter Zielordner.
        temp_pfad: Ordner fuer Zwischenstaende.
        format_beschriftung: Vorausgewaehltes Ausgabeformat.
        pruefstufe: Vorausgewaehlte Pruefstufe.
        packstufe: Vorausgewaehlte Packstufe.
        bereit_text: Anfangstext der Fortschrittsmeldung.
        kerne: Zahl der nutzbaren Kerne; sie begrenzt die Arbeitsvorgaenge.
    """

    def __init__(
        self,
        zielpfad: str = "",
        temp_pfad: str = "",
        format_beschriftung: str = "",
        pruefstufe: str = "",
        packstufe: str = "",
        bereit_text: str = "",
        kerne: int = 8,
    ) -> None:
        # ── Was gemacht wird ────────────────────────────────────────────
        self.current_mode = Text("pack_folder", "Aufgabe")
        # ── Was das Programm zurueckmeldet ──────────────────────
        # Bis zum 28.08.2026 gab es geteilte Werte nur fuer das, was
        # der Anwender EINSTELLT. Was das Programm ihm SAGT, hatte
        # keinen - und konnte deshalb in der WPF-Fassung nirgends
        # ankommen: Die Statuszeile blieb leer, das Protokollfeld
        # blieb leer, und ABBRECHEN blieb gesperrt, weil niemand
        # wusste, dass etwas laeuft.
        # Sprache und Farbstand sagen der Oberflaeche, dass sie ihre
        # Beschriftungen und Farben neu holen muss. In Tk erledigen das
        # _apply_language und _apply_theme unmittelbar an den Widgets;
        # die WPF-Seite erfaehrt es nur ueber einen geteilten Wert.
        #
        # Der Farbstand traegt beides zusammen - Design und
        # Farbschwaeche -, weil ein Wechsel der Farbschwaeche denselben
        # Designnamen behaelt. Zwei getrennte Werte haetten den
        # zweiten Fall verschluckt.
        self.sprache = Text("de", "Sprache")
        self.farbstand = Text("dunkel|keine", "Farbstand")
        # Zaehler statt Inhalt: Das Hintergrundbild ist ein Bild, kein
        # Text - geteilt wird nur die Nachricht "es ist neu gerechnet
        # worden". Die WPF-Seite holt sich danach den fertigen
        # Zwischenspeicher aus der Ablauflogik.
        #
        # Ein Zaehler und kein Schalter: Zweimal dasselbe Bild neu zu
        # rechnen muss zweimal melden, und ein Schalter, der schon auf
        # True steht, meldet beim zweiten Mal nichts.
        self.bildstand = Text("0", "Hintergrundbilder")

        self.statustext = Text("", "Statuszeile")
        # Was waehrend eines Laufs rechts neben dem Balken und unter
        # der Statuszeile steht. Alle drei sind in Tk eigene
        # Beschriftungen, die im Leerlauf ganz aus dem Raster genommen
        # werden - leer heisst hier deshalb "nicht anzeigen".
        self.prozenttext = Text("", "Prozentanzeige")
        self.groessentext = Text("", "Groesse und Restzeit")
        self.telemetrietext = Text("", "Telemetrie")

        # Was die Seitenleiste vom erkannten Spiel zeigt. Der
        # Vorschaubereich war gebaut, aber nichts beschrieb ihn - er
        # blieb den ganzen Lauf leer.
        #
        # Das Bild traegt die PNG-Daten und keinen Pfad: Die
        # Ablauflogik haelt das Cover im Speicher, icon0.png steckt je
        # nach Quelle in einem Abbild. Ein Pfad muesste erst
        # geschrieben werden - und ein gleichbleibender Dateiname
        # meldete gar keine Aenderung, waehrend beim Quellwechsel bis
        # zu fuenf Bilder hintereinander kommen.
        self.spielname = Text("", "Spielname")
        self.titelbild = Wert(None, "Titelbild")
        self.protokoll = Strom("Protokoll")
        # Zweiter Strom fuer die Befehle daran. Das Protokoll wird
        # nicht nur beschrieben, sondern auch geleert (beim Start
        # eines Laufs) und um seine letzte Zeile gekuerzt (wenn ein
        # Fortschrittsbalken sich fortschreibt, statt eine neue Zeile
        # zu bekommen). Ohne diesen Weg liefe das WPF-Protokoll
        # waehrend eines Laufs mit hunderten fast gleicher
        # Balkenzeilen voll - genau das, was die Zusammenfassung in
        # der Tk-Fassung verhindert.
        self.protokoll_befehl = Strom("Protokollbefehl")
        self.laeuft = Schalter(False, "Auftrag laeuft")

        self.source_path = Text("", "Quelle")
        self.dest_path = Text(zielpfad, "Ziel")
        self.temp_path = Text(temp_pfad, "Zwischenablage")
        self.target_format = Text(format_beschriftung, "Ausgabeformat")

        # ── Wie es gemacht wird ─────────────────────────────────────────
        self.compression_level_var = Text(packstufe, "Packstufe")
        #: Welche Bauform neue Container bekommen: was zwischen Huelle
        #: und Spieldateien liegt. Siehe BAUFORM_KEYS in i18n.
        self.bauform_var = Text("", "Bauform")
        self.verify_var = Text(pruefstufe, "Pruefstufe")
        # Die Obergrenze ist die Kernzahl. Sie steht erst zur Laufzeit fest,
        # deshalb laesst sie sich mit grenzen_setzen nachziehen.
        self.worker_count_var = Ganzzahl(
            min(4, max(1, kerne)), kleinster=1, groesster=max(1, kerne),
            name="Arbeitsvorgaenge")

        # ── Zusatzschritte ──────────────────────────────────────────────
        self.ampr_integrate_var = Schalter(False, "AMPR einbauen")
        self.ampr_playgo_var = Schalter(False, "PlayGo einbauen")
        self.ampr_version_var = Text("", "AMPR-Fassung")
        self.backport_integrate_var = Schalter(False, "Backport einbauen")
        self.backport_fw_var = Text("", "Backport-Firmware")

        # ── Anzeige ─────────────────────────────────────────────────────
        self.dock_info = Schalter(False, "Spielinfo angedockt")
        self.dock_credits = Schalter(False, "Mitwirkende angedockt")

        #: Ob der Fussknopf "Spiel Info" bedienbar ist.
        #:
        #: Er bleibt gesperrt, solange keine gueltige Quelle eingestellt ist -
        #: sonst oeffnete sich ein Fenster, das nichts anzuzeigen haette. In
        #: Tk steckt das im Widget selbst (``config(state=...)``), was die
        #: WPF-Fassung nicht sehen kann. Deshalb hier als eigener Wert.
        self.spielinfo_bereit = Schalter(False, "Spielinfo bedienbar")
        self._info_src_size_var = Text(UNBEKANNT, "Quellgroesse")
        self._info_est_size_var = Text(UNBEKANNT, "Groesse geschaetzt")
        self._info_format_var = Text(UNBEKANNT, "Format")
        self._info_method_var = Text(UNBEKANNT, "Verfahren")
        self._patch_status_var = Text(bereit_text, "Stand")

        # ── Angaben zum erkannten Spiel ─────────────────────────────────
        # Sie stehen als Zuordnung und nicht als elf einzelne Felder: Die
        # Logik geht sie in einer Schleife durch, und die Oberflaechen
        # ebenfalls.
        self.metadaten: dict[str, Text] = {
            schluessel: Text(UNBEKANNT, "Angabe " + schluessel)
            for schluessel in METADATENFELDER
        }

        # ── Ablauf ──────────────────────────────────────────────────────
        self.progress_var = Kommazahl(0.0, "Fortschritt")
        self.shutdown_after_success = Schalter(False, "Danach herunterfahren")

    # ── Bequemlichkeit ──────────────────────────────────────────────────
    def alle(self) -> dict[str, object]:
        """Alle Werte als Zuordnung Name -> Wert.

        Gedacht fuer das Koppeln in einem Rutsch und fuer die Diagnose. Die
        Angaben zum Spiel kommen mit dem Vorsatz ``meta.`` dazu, damit die
        Namen eindeutig bleiben.
        """
        werte: dict[str, object] = {
            name: wert for name, wert in vars(self).items()
            if isinstance(wert, (Text, Schalter, Ganzzahl, Kommazahl))}
        werte.update({"meta." + k: v for k, v in self.metadaten.items()})
        return werte

    def metadaten_zuruecksetzen(self) -> None:
        """Setzt alle Angaben zum Spiel auf den Platzhalter.

        Gebraucht beim Wechsel der Quelle: Die Angaben des vorigen Spiels
        stehenzulassen waere schlimmer als gar keine - sie saehen aus, als
        gehoerten sie zum neuen.
        """
        for wert in self.metadaten.values():
            wert.set(UNBEKANNT)

    def metadaten_lesen(self) -> dict[str, str]:
        """Alle Angaben als gewoehnliche Zuordnung - fuer die Oberflaechen."""
        return {schluessel: wert.get() for schluessel, wert in self.metadaten.items()}

    def kerngrenze_setzen(self, kerne: int) -> None:
        """Zieht die Obergrenze der Arbeitsvorgaenge nach.

        Die Kernzahl steht erst fest, wenn das Programm laeuft; bis dahin
        gilt die Vorgabe aus dem Erzeuger.
        """
        self.worker_count_var.grenzen_setzen(1, max(1, int(kerne)))

    def zuruecksetzen_fuer_neuen_lauf(self) -> None:
        """Setzt zurueck, was zu einem einzelnen Durchlauf gehoert.

        Quelle, Ziel und die Einstellungen bleiben stehen - wer zweimal
        hintereinander umwandelt, will sie nicht neu setzen.
        """
        self.progress_var.set(0.0)
        for wert in (self._info_src_size_var, self._info_est_size_var,
                     self._info_format_var, self._info_method_var):
            wert.set(UNBEKANNT)
