"""Prueft, ob die Oberflaeche richtig dargestellt wird.

Ein Programm sieht sein eigenes Fenster nicht. Es kann aber jede Zahl
auslesen, aus der sich ein Darstellungsfehler ergibt - und genau das macht
dieses Modul: Es bekommt den gemessenen Zustand als schlichte Datensaetze und
gibt zurueck, was daran nicht stimmt.

Die Trennung ist Absicht. Das Messen braucht ein laufendes Tk-Fenster, das
Urteilen nicht. So laesst sich jede Regel hier mit erfundenen Zahlen pruefen,
ohne dass ein Test ein Fenster oeffnen muss - was auf einem Bauserver ohnehin
nicht geht.

Die Befunde sind bewusst deutsch und nicht uebersetzt: Sie stehen im
Diagnosebericht neben den uebrigen Messwerten, und der ist zum Weitergeben
gedacht, nicht zum Vorlesen.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# --- Schwellen ------------------------------------------------------------
# Alle Grenzwerte an einer Stelle, damit Tests sie nennen koennen statt sie
# abzuschreiben.

#: Ab wie vielen Pixeln Ueberstand ein Element als abgeschnitten gilt. Zwei
#: Pixel Toleranz, weil Rahmenbreiten je nach Design um einen Pixel wandern.
RAND_TOLERANZ = 2

#: Ab welchem Verhaeltnis ein Bild als hochgerechnet gilt. Zwei Prozent sind
#: unter jeder Wahrnehmungsschwelle; darueber wird es weich.
BILD_FAKTOR_GRENZE = 1.02

#: Unter dieser Zeilenhoehe ist die Schrift auf keiner Plattform mehr
#: lesbar. Bewusst tief angesetzt: Der Mac-Befund vom 19.08.2026 lag bei
#: 12,1 px - dieselben 12 px sind unter Windows bei 100 % Anzeigeskalierung
#: aber der Normalfall (9 pt x 1,3333). Eine Regel, die den Mac-Fall faengt,
#: meckerte jeden unskalierten Windows-Rechner an. Was die Schrift dort zu
#: klein machte, loest ``pt()`` im Hauptprogramm.
SCHRIFT_MINDESTHOEHE_PX = 11
SCHRIFT_HOECHSTHOEHE_PX = 30

#: Wie weit ``tk scaling`` vom DPI-Wert des Fensters abweichen darf.
SKALIERUNG_TOLERANZ = 0.15

#: Speicher: ab hier lohnt ein Blick, ab dem zweiten Wert ist etwas kaputt.
SPEICHER_WARNUNG_MB = 1500
SPEICHER_FEHLER_MB = 3000
#: Zuwachs gegenueber dem Start, ohne dass ein Auftrag laeuft.
SPEICHER_ZUWACHS_MB = 800

#: Tk gibt Bilder nur frei, wenn niemand mehr auf sie zeigt. Haeufen sie
#: sich, wurde bei jedem Neuzeichnen eines angelegt und keines verworfen -
#: die haeufigste Ursache fuer stetig wachsenden Speicher in Tk.
TK_BILDER_GRENZE = 200

#: Dasselbe fuer ``after``-Auftraege: ein Zeitgeber, der sich selbst neu
#: bestellt und nie abbestellt wird, macht die Oberflaeche zaeh.
ZEITGEBER_GRENZE = 60

#: Wie lange ein Durchlauf der Ereignisschleife hoechstens dauern darf.
#: 150 ms sind die Grenze, ab der eine Bewegung nicht mehr fluessig wirkt.
SCHLEIFE_WARNUNG_MS = 150
SCHLEIFE_FEHLER_MS = 500

FEHLER = "FEHLER"
WARNUNG = "WARNUNG"
HINWEIS = "HINWEIS"

_RANG = {FEHLER: 0, WARNUNG: 1, HINWEIS: 2}

#: Nur bei diesen Klassen sagt eine zu kleine Breite wirklich, dass Text
#: abgeschnitten ist. Eingabefelder und Listen duerfen kleiner sein als ihr
#: Inhalt - sie rollen.
_TEXTKLASSEN = frozenset({
    "Label", "TLabel", "Button", "TButton",
    "Checkbutton", "TCheckbutton", "Radiobutton", "TRadiobutton",
    "Menubutton", "TMenubutton",
})


@dataclass(frozen=True)
class Befund:
    """Ein einzelner Mangel an der Darstellung."""

    schwere: str
    kennung: str
    text: str

    def __str__(self) -> str:
        return "%s [%s] %s" % (self.schwere, self.kennung, self.text)


@dataclass(frozen=True)
class Flaeche:
    """Ein Bedienelement, so wie es tatsaechlich auf dem Schirm liegt.

    ``x``/``y`` sind Bildschirmkoordinaten, nicht die des Elternelements -
    nur so laesst sich der Ueberstand ueber den Fensterrand ausrechnen, ohne
    die ganze Verschachtelung nachzubauen.
    """

    name: str
    klasse: str
    x: int
    y: int
    breite: int
    hoehe: int
    wunschbreite: int = 0
    wunschhoehe: int = 0
    sichtbar: bool = True
    #: Ob wirklich Text darauf steht. Ein Label mit blossem Bild darf enger
    #: sein als sein Wunschmass - die Hintergrundbilder liegen absichtlich
    #: ueber ihren Rand hinaus. Ohne diese Unterscheidung meldete die
    #: Pruefung am 20.08.2026 vier Fehlalarme.
    hat_text: bool = False
    #: Ob das Element in einer Flaeche liegt, die gerade gerollt werden kann.
    #: Dann ist ein Ueberstand ueber den Fensterrand kein Mangel - es ist
    #: erreichbar, man muss nur rollen.
    rollbar: bool = False


@dataclass(frozen=True)
class Bildlage:
    """Ein Hintergrundbild in seinen drei Groessen.

    ``quelle`` ist die Bilddatei, ``gezeichnet`` das daraus erzeugte
    ``PhotoImage`` und ``flaeche`` das Element, auf dem es liegt. Erst alle
    drei zusammen sagen etwas aus: Die Datei allein verraet nicht, ob sie
    hochgerechnet wurde, und das gezeichnete Bild nicht, ob es noch passt.
    """

    name: str
    quelle: tuple[int, int] | None = None
    gezeichnet: tuple[int, int] | None = None
    flaeche: tuple[int, int] | None = None


@dataclass(frozen=True)
class Fensterlage:
    """Das Fenster selbst - der Rahmen, gegen den alles geprueft wird."""

    breite: int
    hoehe: int
    x: int = 0
    y: int = 0
    schirm_breite: int = 0
    schirm_hoehe: int = 0


@dataclass(frozen=True)
class Skalierungslage:
    """Was das System und was Tk ueber die Anzeigegroesse denken."""

    plattform: str = ""
    dpi_bewusstsein: int | None = None
    fenster_dpi: int | None = None
    tk_skalierung: float = 0.0
    schrifthoehe_px: int = 0
    schriftgroesse_pt: int = 0


@dataclass(frozen=True)
class Laufruhelage:
    """Speicher, Zeitgeber und Reaktionszeit."""

    speicher_mb: float = 0.0
    speicher_start_mb: float = 0.0
    auftrag_laeuft: bool = False
    tk_bilder: int = 0
    offene_zeitgeber: int = 0
    schleife_ms: float = 0.0
    threads: int = 0


@dataclass
class Pruefergebnis:
    """Alle Befunde eines Durchgangs, nach Schwere sortiert."""

    befunde: list[Befund] = field(default_factory=list)

    @property
    def fehler(self) -> list[Befund]:
        return [b for b in self.befunde if b.schwere == FEHLER]

    @property
    def warnungen(self) -> list[Befund]:
        return [b for b in self.befunde if b.schwere == WARNUNG]

    @property
    def sauber(self) -> bool:
        """Wahr, wenn nichts Ernstes gefunden wurde (Hinweise zaehlen nicht)."""
        return not self.fehler and not self.warnungen


def _prozent(faktor: float) -> str:
    return "%.0f %%" % ((faktor - 1.0) * 100.0)


def pruefe_flaechen(fenster: Fensterlage,
                    flaechen: list[Flaeche]) -> list[Befund]:
    """Sucht Elemente, die abgeschnitten, eingeklappt oder zu eng sind.

    Args:
        fenster: Groesse des Programmfensters.
        flaechen: Alle gemessenen Bedienelemente.

    Returns:
        Die gefundenen Maengel; leere Liste, wenn alles passt.
    """
    befunde: list[Befund] = []
    for f in flaechen:
        if not f.sichtbar:
            continue

        # Eingeklappt: sichtbar, aber ohne Ausdehnung. Kommt von der
        # Packreihenfolge - ein Element, das vor der Knopfleiste mit
        # expand=True gepackt wird, quetscht sie auf null.
        if (f.breite <= 1 or f.hoehe <= 1) and f.wunschbreite > 1 and f.wunschhoehe > 1:
            befunde.append(Befund(
                FEHLER, "eingeklappt",
                "%s (%s) ist auf %dx%d zusammengedrückt, braucht aber %dx%d"
                % (f.name, f.klasse, f.breite, f.hoehe,
                   f.wunschbreite, f.wunschhoehe)))
            continue

        if f.breite <= 1 or f.hoehe <= 1:
            continue

        # Ueber den Fensterrand hinaus - der Teil ist schlicht nicht da.
        # Ausser er laesst sich heranrollen; dann ist er erreichbar.
        if f.rollbar:
            continue

        rechts = f.x + f.breite - (fenster.x + fenster.breite)
        unten = f.y + f.hoehe - (fenster.y + fenster.hoehe)
        if rechts > RAND_TOLERANZ:
            befunde.append(Befund(
                WARNUNG, "abgeschnitten",
                "%s (%s) steht %d px über den rechten Fensterrand hinaus"
                % (f.name, f.klasse, rechts)))
        if unten > RAND_TOLERANZ:
            befunde.append(Befund(
                WARNUNG, "abgeschnitten",
                "%s (%s) steht %d px über den unteren Fensterrand hinaus"
                % (f.name, f.klasse, unten)))
        if f.x - fenster.x < -RAND_TOLERANZ:
            befunde.append(Befund(
                WARNUNG, "abgeschnitten",
                "%s (%s) beginnt %d px links ausserhalb des Fensters"
                % (f.name, f.klasse, fenster.x - f.x)))

        # Zu eng fuer den eigenen Text. Nur dort, wo Text nicht rollen kann -
        # und nur, wenn ueberhaupt Text darauf steht.
        if f.klasse in _TEXTKLASSEN and f.hat_text:
            fehlt_breit = f.wunschbreite - f.breite
            fehlt_hoch = f.wunschhoehe - f.hoehe
            if fehlt_breit > RAND_TOLERANZ:
                befunde.append(Befund(
                    WARNUNG, "text_beschnitten",
                    "%s (%s) ist %d px zu schmal für seine Beschriftung"
                    % (f.name, f.klasse, fehlt_breit)))
            if fehlt_hoch > RAND_TOLERANZ:
                befunde.append(Befund(
                    WARNUNG, "text_beschnitten",
                    "%s (%s) ist %d px zu niedrig für seine Beschriftung"
                    % (f.name, f.klasse, fehlt_hoch)))
    return befunde


def pruefe_bilder(bilder: list[Bildlage]) -> list[Befund]:
    """Prueft Hintergrundbilder auf Hochrechnung und stehengebliebene Groesse.

    Verzerrung laesst sich aus Zahlen allein nicht ablesen: Die Bilder werden
    formatfuellend gerechnet und mittig beschnitten, das gezeichnete Bild hat
    also immer genau die Groesse der Flaeche und nie das Seitenverhaeltnis der
    Datei. Was der Betrachter als "gestretcht" wahrnimmt, ist deshalb fast
    immer eine Hochrechnung - und die steht hier.

    Args:
        bilder: Die drei Groessen je Hintergrundbild.

    Returns:
        Die gefundenen Maengel.
    """
    befunde: list[Befund] = []
    for b in bilder:
        if b.quelle and b.flaeche and all(b.quelle) and all(b.flaeche):
            faktor = max(b.flaeche[0] / b.quelle[0], b.flaeche[1] / b.quelle[1])
            if faktor > BILD_FAKTOR_GRENZE:
                befunde.append(Befund(
                    WARNUNG, "bild_hochgerechnet",
                    "%s: Datei %dx%d auf %dx%d hochgerechnet (+%s) - wirkt weich; "
                    "mindestens %dx%d wären nötig"
                    % (b.name, b.quelle[0], b.quelle[1],
                       b.flaeche[0], b.flaeche[1], _prozent(faktor),
                       b.flaeche[0], b.flaeche[1])))

        # Das gezeichnete Bild muss die Flaeche genau treffen. Tut es das
        # nicht, ist die Anpassung stehengeblieben - dann zeigt Tk das alte
        # Bild in der neuen Flaeche, und das sieht wirklich gestretcht aus.
        if b.gezeichnet and b.flaeche and all(b.flaeche):
            ab = abs(b.gezeichnet[0] - b.flaeche[0])
            ah = abs(b.gezeichnet[1] - b.flaeche[1])
            if ab > RAND_TOLERANZ or ah > RAND_TOLERANZ:
                befunde.append(Befund(
                    FEHLER, "bild_nicht_nachgezogen",
                    "%s: gezeichnet %dx%d, Fläche ist aber %dx%d - "
                    "die Anpassung ist stehengeblieben"
                    % (b.name, b.gezeichnet[0], b.gezeichnet[1],
                       b.flaeche[0], b.flaeche[1])))
    return befunde


def pruefe_skalierung(lage: Skalierungslage) -> list[Befund]:
    """Prueft DPI-Bewusstsein, ``tk scaling`` und die Schriftgroesse.

    Args:
        lage: Was System und Tk ueber die Anzeige melden.

    Returns:
        Die gefundenen Maengel.
    """
    befunde: list[Befund] = []

    # Ohne DPI-Bewusstsein zeichnet das Programm in 96 dpi, und Windows
    # zieht das fertige Fenster als Bitmap auf die echte Groesse. Dann ist
    # nicht ein Bild unscharf, sondern alles.
    if lage.plattform == "win32" and lage.dpi_bewusstsein == 0:
        befunde.append(Befund(
            FEHLER, "dpi_unbewusst",
            "Der Prozess ist nicht DPI-bewusst - Windows zieht das ganze "
            "Fenster als Bitmap hoch, alles wirkt unscharf"))

    if lage.fenster_dpi and lage.tk_skalierung:
        erwartet = lage.fenster_dpi / 72.0
        if abs(lage.tk_skalierung - erwartet) > SKALIERUNG_TOLERANZ:
            befunde.append(Befund(
                WARNUNG, "skalierung_weicht_ab",
                "tk scaling steht auf %.4f, das Fenster meldet aber %d dpi "
                "(erwartet %.4f) - Schrift und Abstände passen nicht zusammen"
                % (lage.tk_skalierung, lage.fenster_dpi, erwartet)))

    if 0 < lage.schrifthoehe_px < SCHRIFT_MINDESTHOEHE_PX:
        befunde.append(Befund(
            WARNUNG, "schrift_zu_klein",
            "Die Standardschrift ist nur %d px hoch (%d pt) - unter %d px "
            "wird die Oberfläche schwer lesbar"
            % (lage.schrifthoehe_px, lage.schriftgroesse_pt,
               SCHRIFT_MINDESTHOEHE_PX)))
    elif lage.schrifthoehe_px > SCHRIFT_HOECHSTHOEHE_PX:
        befunde.append(Befund(
            HINWEIS, "schrift_sehr_gross",
            "Die Standardschrift ist %d px hoch - Beschriftungen können "
            "ihre Knöpfe sprengen" % lage.schrifthoehe_px))
    return befunde


def pruefe_laufruhe(lage: Laufruhelage) -> list[Befund]:
    """Prueft Speicher, angesammelte Tk-Bilder, Zeitgeber und Reaktionszeit.

    Args:
        lage: Die gemessenen Laufwerte.

    Returns:
        Die gefundenen Maengel.
    """
    befunde: list[Befund] = []

    if lage.speicher_mb >= SPEICHER_FEHLER_MB:
        befunde.append(Befund(
            FEHLER, "speicher_hoch",
            "Das Programm belegt %.0f MB - ab %d MB ist mit Abbrüchen zu "
            "rechnen" % (lage.speicher_mb, SPEICHER_FEHLER_MB)))
    elif lage.speicher_mb >= SPEICHER_WARNUNG_MB:
        befunde.append(Befund(
            WARNUNG, "speicher_hoch",
            "Das Programm belegt %.0f MB" % lage.speicher_mb))

    # Zuwachs zaehlt nur im Leerlauf: Waehrend ein Auftrag laeuft, sind
    # grosse Puffer gewollt und sagen nichts ueber ein Leck aus.
    zuwachs = lage.speicher_mb - lage.speicher_start_mb
    if (not lage.auftrag_laeuft and lage.speicher_start_mb > 0
            and zuwachs >= SPEICHER_ZUWACHS_MB):
        befunde.append(Befund(
            WARNUNG, "speicher_waechst",
            "Seit dem Start sind %.0f MB dazugekommen, ohne dass ein Auftrag "
            "läuft - das deutet auf ein Leck" % zuwachs))

    if lage.tk_bilder > TK_BILDER_GRENZE:
        befunde.append(Befund(
            WARNUNG, "bilder_haeufen_sich",
            "Tk hält %d Bilder im Speicher (Grenze %d) - vermutlich wird bei "
            "jedem Neuzeichnen eines angelegt und keines verworfen"
            % (lage.tk_bilder, TK_BILDER_GRENZE)))

    if lage.offene_zeitgeber > ZEITGEBER_GRENZE:
        befunde.append(Befund(
            WARNUNG, "zeitgeber_haeufen_sich",
            "%d offene after-Aufträge (Grenze %d) - ein Zeitgeber bestellt "
            "sich neu, ohne abbestellt zu werden"
            % (lage.offene_zeitgeber, ZEITGEBER_GRENZE)))

    if lage.schleife_ms >= SCHLEIFE_FEHLER_MS:
        befunde.append(Befund(
            FEHLER, "schleife_traege",
            "Ein Durchlauf der Ereignisschleife dauert %.0f ms - das Fenster "
            "reagiert sichtbar verzögert" % lage.schleife_ms))
    elif lage.schleife_ms >= SCHLEIFE_WARNUNG_MS:
        befunde.append(Befund(
            WARNUNG, "schleife_traege",
            "Ein Durchlauf der Ereignisschleife dauert %.0f ms - Bewegungen "
            "wirken nicht mehr flüssig" % lage.schleife_ms))
    return befunde


def pruefe_alles(fenster: Fensterlage | None = None,
                 flaechen: list[Flaeche] | None = None,
                 bilder: list[Bildlage] | None = None,
                 skalierung: Skalierungslage | None = None,
                 laufruhe: Laufruhelage | None = None) -> Pruefergebnis:
    """Fuehrt alle Pruefungen aus und sortiert die Befunde nach Schwere.

    Jeder Teil ist einzeln abschaltbar: Fehlt eine Messung, entfaellt nur der
    dazugehoerige Abschnitt. Ein Diagnosebericht soll auch dann entstehen,
    wenn sich etwas nicht auslesen liess.

    Returns:
        Das gesammelte Ergebnis.
    """
    befunde: list[Befund] = []
    if fenster is not None and flaechen:
        befunde.extend(pruefe_flaechen(fenster, flaechen))
    if bilder:
        befunde.extend(pruefe_bilder(bilder))
    if skalierung is not None:
        befunde.extend(pruefe_skalierung(skalierung))
    if laufruhe is not None:
        befunde.extend(pruefe_laufruhe(laufruhe))
    befunde.sort(key=lambda b: (_RANG.get(b.schwere, 9), b.kennung, b.text))
    return Pruefergebnis(befunde)


def zusammenfassung(ergebnis: Pruefergebnis) -> str:
    """Eine Zeile fuer den Kopf des Berichts.

    Returns:
        Klartext, kein Schluessel - die Zeile steht so im Bericht.
    """
    if not ergebnis.befunde:
        return "Darstellung: keine Auffälligkeit"
    teile = []
    for schwere in (FEHLER, WARNUNG, HINWEIS):
        anzahl = sum(1 for b in ergebnis.befunde if b.schwere == schwere)
        if anzahl:
            teile.append("%d x %s" % (anzahl, schwere))
    return "Darstellung: " + ", ".join(teile)
