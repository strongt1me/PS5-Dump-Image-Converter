"""Beobachtbare Werte, die beide Oberflaechen bedienen koennen.

Das Programm haelt seinen Bedienzustand in 99 Tk-Variablen (``StringVar``,
``BooleanVar``, ``IntVar``, ``DoubleVar``). Die haengen an einem Tk-Fenster:
Ohne ``tk.Tk()`` lassen sie sich nicht einmal anlegen, und eine WPF-Ansicht
kann sie weder lesen noch beschreiben.

Dieses Modul setzt einen neutralen Wert an ihre Stelle. Er kennt kein Tk und
kein .NET, meldet aber jede Aenderung an angemeldete Beobachter - und genau
darauf laesst sich beides aufsetzen: Die Tk-Seite haengt einen Beobachter an,
der das Widget nachzieht, die WPF-Seite ebenso.

Die Schnittstelle ist absichtlich die von ``tk.Variable`` (``get`` und ``set``):
So bleiben die Aufrufstellen im bestehenden Quelltext unveraendert, und der
Umbau kann Stueck fuer Stueck erfolgen, statt in einem Zug.

Beispiel::

    stufe = Ganzzahl(4, kleinster=1, groesster=8)
    abmelden = stufe.beobachten(lambda alt, neu: print(alt, "->", neu))
    stufe.set(6)          # gibt "4 -> 6" aus
    abmelden()

Gedanken zur Nebenlaeufigkeit: Das Setzen ist durch eine Sperre geschuetzt, das
Benachrichtigen aber ausdruecklich nicht - ein Beobachter, der seinerseits
setzt, liefe sonst in eine Selbstblockade. Beobachter muessen deshalb damit
rechnen, aus einem fremden Thread gerufen zu werden, und die Oberflaeche
selbst ueber ihren Verteiler (``Dispatcher`` bei WPF, ``after`` bei Tk)
nachziehen.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Generic, TypeVar

logger = logging.getLogger("PS5Converter.ui.zustand")

T = TypeVar("T")

#: Ein Beobachter bekommt den alten und den neuen Wert.
Beobachter = Callable[[Any, Any], None]


class Wert(Generic[T]):
    """Ein Wert, der Aenderungen meldet.

    Args:
        anfang: Startwert.
        name: Bezeichnung fuer Protokollmeldungen. Ohne Angabe bleibt sie leer.
    """

    def __init__(self, anfang: T, name: str = "") -> None:
        self._wert: T = anfang
        self._name = name
        self._beobachter: list[Beobachter] = []
        self._sperre = threading.Lock()

    # ── Lesen und Schreiben ─────────────────────────────────────────────
    def get(self) -> T:
        """Liefert den aktuellen Wert. Name wie bei ``tk.Variable``."""
        return self._wert

    def set(self, neu: T) -> None:  # noqa: A003 - bewusst tk-kompatibler Name
        """Setzt den Wert und meldet die Aenderung.

        Ein Setzen auf denselben Wert meldet nichts. Das ist kein Sparzwang,
        sondern verhindert Schleifen: Zwei Werte, die sich gegenseitig
        nachziehen, kaemen sonst nicht zur Ruhe.
        """
        neu = self._pruefen(neu)
        with self._sperre:
            alt = self._wert
            if alt == neu and type(alt) is type(neu):
                return
            self._wert = neu
            # Kopie ziehen: Ein Beobachter darf sich waehrend der Meldung
            # abmelden, ohne dass die Schleife darueber stolpert.
            zuhoerer = list(self._beobachter)

        for melden in zuhoerer:
            try:
                melden(alt, neu)
            except Exception as exc:  # noqa: BLE001
                # Ein fehlerhafter Beobachter darf die anderen nicht mitnehmen
                # und schon gar nicht das Setzen selbst scheitern lassen.
                logger.warning("Beobachter von %r fehlgeschlagen: %s",
                               self._name or "Wert", exc)

    def _pruefen(self, neu: T) -> T:
        """Haken fuer Unterklassen, die Werte begrenzen oder umwandeln."""
        return neu

    # ── Beobachter ──────────────────────────────────────────────────────
    def beobachten(self, melden: Beobachter) -> Callable[[], None]:
        """Meldet einen Beobachter an.

        Returns:
            Eine Funktion, die den Beobachter wieder abmeldet. Das ist
            bequemer als ein Kennzeichen, das der Aufrufer verwahren muss -
            und es vergisst niemand.
        """
        with self._sperre:
            self._beobachter.append(melden)

        def abmelden() -> None:
            with self._sperre:
                if melden in self._beobachter:
                    self._beobachter.remove(melden)

        return abmelden

    def beobachter_anzahl(self) -> int:
        """Wie viele Beobachter angemeldet sind - fuer Tests und Diagnose."""
        with self._sperre:
            return len(self._beobachter)

    # ── Bequemlichkeit ──────────────────────────────────────────────────
    def __repr__(self) -> str:
        kennung = " %r" % self._name if self._name else ""
        return "<%s%s = %r>" % (type(self).__name__, kennung, self._wert)


class Text(Wert[str]):
    """Zeichenkette. Tritt an die Stelle von ``tk.StringVar``."""

    def __init__(self, anfang: str = "", name: str = "") -> None:
        super().__init__(anfang, name)

    def _pruefen(self, neu: Any) -> str:
        # Tk wandelt beim Setzen still in Text um; wer sich darauf verlaesst,
        # soll hier nicht ueber einen Typfehler stolpern.
        return neu if isinstance(neu, str) else str(neu)


class Schalter(Wert[bool]):
    """Ja/Nein. Tritt an die Stelle von ``tk.BooleanVar``."""

    def __init__(self, anfang: bool = False, name: str = "") -> None:
        super().__init__(bool(anfang), name)

    def _pruefen(self, neu: Any) -> bool:
        return bool(neu)

    def umlegen(self) -> bool:
        """Kippt den Schalter und liefert den neuen Stand.

        Fuer die Umschalter der Oberflaeche - dort stand bisher ueberall
        ``var.set(not var.get())``, was bei nebenlaeufigem Zugriff zwei
        Umschaltungen verschlucken kann.
        """
        with self._sperre:
            neu = not self._wert
        self.set(neu)
        return self.get()


class Ganzzahl(Wert[int]):
    """Ganze Zahl, wahlweise mit Bereichsgrenzen.

    Tritt an die Stelle von ``tk.IntVar``. Die Grenzen sind der Grund, warum
    diese Klasse mehr ist als ein Feld: Der Drehknopf braucht sie, und bisher
    lag diese Prueflogik im Widget selbst - also an einer Stelle, die eine
    zweite Oberflaeche nicht mitbenutzen kann.
    """

    def __init__(self, anfang: int = 0, kleinster: int | None = None,
                 groesster: int | None = None, name: str = "") -> None:
        self._kleinster = kleinster
        self._groesster = groesster
        super().__init__(self._begrenzen(int(anfang)), name)

    def _begrenzen(self, wert: int) -> int:
        if self._kleinster is not None:
            wert = max(self._kleinster, wert)
        if self._groesster is not None:
            wert = min(self._groesster, wert)
        return wert

    def _pruefen(self, neu: Any) -> int:
        try:
            zahl = int(neu)
        except (TypeError, ValueError):
            # Wie Tk: Unsinn aendert nichts, statt das Programm anzuhalten.
            logger.debug("Ganzzahl %r: %r ist keine Zahl, Wert bleibt.",
                         self._name or "?", neu)
            return self._wert
        return self._begrenzen(zahl)

    def grenzen_setzen(self, kleinster: int | None, groesster: int | None) -> None:
        """Aendert den erlaubten Bereich und zieht den Wert hinein.

        Gebraucht, sobald eine Grenze erst zur Laufzeit feststeht - etwa die
        Zahl der Kerne fuer die Zahl der Arbeitsvorgaenge.
        """
        if (kleinster is not None and groesster is not None
                and kleinster > groesster):
            raise ValueError(
                "Untergrenze %r liegt ueber der Obergrenze %r" % (kleinster, groesster))
        self._kleinster, self._groesster = kleinster, groesster
        self.set(self._begrenzen(self._wert))

    @property
    def kleinster(self) -> int | None:
        """Untergrenze, oder ``None`` wenn keine gesetzt ist."""
        return self._kleinster

    @property
    def groesster(self) -> int | None:
        """Obergrenze, oder ``None`` wenn keine gesetzt ist."""
        return self._groesster

    def anteil(self) -> float:
        """Wo der Wert im Bereich liegt - 0.0 bis 1.0.

        Der Drehknopf zeichnet daraus seinen Bogen. Ohne beide Grenzen gibt es
        keinen Anteil; dann ist die Antwort 0.0.
        """
        if self._kleinster is None or self._groesster is None:
            return 0.0
        spanne = self._groesster - self._kleinster
        if spanne <= 0:
            return 0.0
        return max(0.0, min(1.0, (self._wert - self._kleinster) / spanne))


class Kommazahl(Wert[float]):
    """Kommazahl. Tritt an die Stelle von ``tk.DoubleVar``."""

    def __init__(self, anfang: float = 0.0, name: str = "") -> None:
        super().__init__(float(anfang), name)

    def _pruefen(self, neu: Any) -> float:
        try:
            return float(neu)
        except (TypeError, ValueError):
            logger.debug("Kommazahl %r: %r ist keine Zahl, Wert bleibt.",
                         self._name or "?", neu)
            return self._wert


class Strom:
    """Ein Fluss von Meldungen - kein Wert mit einem Stand.

    ``Wert`` beschreibt etwas, das einen Stand hat: eine Quelle, eine
    Stufe, einen Schalter. Ein Protokoll hat keinen Stand, sondern eine
    Folge. Der Unterschied ist nicht theoretisch: :meth:`Wert.set`
    unterdrueckt das Melden, wenn sich nichts aendert, und zwei gleiche
    Zeilen hintereinander kaemen deshalb nur einmal an. Bei
    Fortschrittsbalken ist das der Normalfall.

    Ein Strom merkt sich nichts. Wer sich anmeldet, bekommt ab dann jede
    Meldung; was vorher lief, ist vorbei. Fuer eine Anzeige, die
    mitlaeuft, ist das richtig - sie soll nicht beim Anmelden die ganze
    Vergangenheit nachgereicht bekommen.

    Args:
        name: Nur fuer Meldungen im Fehlerfall.
    """

    __slots__ = ("_name", "_beobachter", "_sperre")

    def __init__(self, name: str = "") -> None:
        self._name = name
        self._beobachter: list[Any] = []
        self._sperre = threading.RLock()

    def senden(self, meldung: str) -> None:
        """Gibt eine Meldung an alle Anmelder weiter.

        Anders als :meth:`Wert.set` immer - auch wenn dieselbe Meldung
        schon einmal kam.
        """
        with self._sperre:
            # Kopie ziehen: Ein Anmelder darf sich waehrend der Meldung
            # abmelden, ohne dass die Schleife darueber stolpert.
            zuhoerer = list(self._beobachter)

        for melden in zuhoerer:
            try:
                melden(meldung)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Anmelder von %r fehlgeschlagen: %s",
                               self._name or "Strom", exc)

    def beobachten(self, melden: Any) -> Any:
        """Meldet einen Zuhoerer an.

        Returns:
            Ein Aufrufbares, das ihn wieder abmeldet.
        """
        with self._sperre:
            self._beobachter.append(melden)

        def abmelden() -> None:
            with self._sperre:
                if melden in self._beobachter:
                    self._beobachter.remove(melden)

        return abmelden

    def beobachter_anzahl(self) -> int:
        """Wie viele gerade zuhoeren."""
        with self._sperre:
            return len(self._beobachter)

    def __repr__(self) -> str:
        return "Strom(%r, %d Zuhoerer)" % (self._name,
                                           self.beobachter_anzahl())
