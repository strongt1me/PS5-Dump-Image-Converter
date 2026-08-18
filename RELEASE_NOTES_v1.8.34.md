# PS5 Dump & Image Converter v1.8.34 – Release Notes

## Zweck dieses Releases

Der Knopf **Download** im Fenster *Spiel-Info – Updates & Patches* führte bisher nur auf eine Internetseite. Das eigentliche Herunterladen, Einsortieren und Nachhalten blieb Handarbeit. Dieses Release macht daraus einen vollständigen Vorgang im Programm.

---

## Was neu ist

### Download-Verwaltung

Ein neuer Eintrag **DOWNLOADS** im Menü **WEITERE TOOLS** öffnet eine Übersicht mit sechs Spalten: Datei, Title-ID, Art, Größe, Fortschritt, Status. Darin stehen laufende Downloads und alles, was bereits auf der Platte liegt.

| Knopf | Wirkung |
| --- | --- |
| **Aus Zwischenablage** | nimmt die kopierte Adresse auf und startet sofort |
| **Adresse(n) einfügen** | Textfeld für mehrere Adressen auf einmal |
| **Vorhandene einlesen** | durchsucht beide Zielordner und listet, was da ist |
| **Abbrechen** | hält den markierten Download an |
| **Erneut versuchen** | setzt einen abgebrochenen oder fehlgeschlagenen Download fort |
| **Als Update/Patch umsortieren** | verschiebt eine fertige Datei in den jeweils anderen Ordner |
| **Ordner öffnen** | öffnet den Explorer am Ablageort |

### Getrennte Ordner nach Art

Die Einordnung folgt der Markierung im Spiel-Info-Fenster: Die dort als neueste gekennzeichnete Version gilt als **Update**, jede ältere als **Patch**.

```
<gewählter Speicherort>\
├── PS5 Spiele Updates\    ← neueste Version
└── Patches\               ← ältere Fassungen
```

Ist die Lage nicht feststellbar, wird als Update behandelt – lieber im Hauptordner als in einer falschen Ablage. Korrigieren lässt sich das mit einem Klick.

### Speicherort

Beim ersten Download wird nach dem Datenträger gefragt. Danach steht der Ort in den **Einstellungen** unter *Speicherort für Downloads* und lässt sich dort oder direkt im Download-Fenster ändern. Beide Unterordner entstehen automatisch.

### Fortsetzen statt neu anfangen

Geladen wird blockweise in eine Datei mit der Endung `.teil`. Erst wenn ihre Größe der vom Server gemeldeten entspricht, bekommt sie ihren endgültigen Namen – eine abgebrochene Datei kann also nie fälschlich als fertig gelten. Beim erneuten Versuch fragt das Programm per `Range`-Anfrage nur den fehlenden Rest an.

Am echten Endpunkt nachgemessen (16.08.2026):

```
HTTP/1.1 206 Partial Content
Content-Range: bytes 0-1023/457310208
Accept-Ranges: bytes
```

Die ersten vier Bytes der ausgelieferten Datei sind `7F 46 49 48` – das PS5-PKG-Magic. Der Abruf läuft über einfaches HTTP ohne Anmeldung.

---

## Ein Schritt bleibt bewusst von Hand

Die Download-Adresse entsteht erst beim Klick auf **DETAILS** auf der Patch-Seite, und dieser Klick ist dort durch eine Sicherheitsabfrage geschützt. **Dieser Schutz wird nicht umgangen.** Der Ablauf ist deshalb:

1. Im Fenster **Spiel-Info** auf **Download** klicken. Die Seite öffnet sich im Browser, das Download-Fenster kommt nach vorn.
2. Auf der Seite die Sicherheitsabfrage bestätigen.
3. Rechtsklick auf **Download Piece PKG** → *Link kopieren*.
4. Zurück im Download-Fenster: **Aus Zwischenablage**.

Alles danach – Prüfen der Adresse, Einordnen, Zielordner, Laden, Fortsetzen, Abschluss – läuft ohne weiteres Zutun. Mehrere Adressen dürfen auf einmal eingefügt werden.

Zeigt eine Zeile bereits direkt auf eine `.pkg`-Datei, entfallen die Schritte 2 bis 4 und der Download startet sofort.

---

## Prüfung

| Prüfung | Umfang | Ergebnis |
| --- | --- | --- |
| Neue Tests `test_downloads.py` | 35 | grün |
| Gesamte Testsuite | 327 | grün (2 übersprungen) |
| Oberfläche mit echtem `mainloop` | 14 Punkte | 14/14 |
| Download-Vorgang gegen lokalen Server | 13 Punkte | 13/13 |
| Echter Endpunkt, Bereichsanfrage | 1 KiB gelesen | HTTP 206 |

Der Download-Vorgang wurde gegen einen lokalen Server mit Bereichsunterstützung Byte-genau geprüft: vollständiger Lauf, Fortsetzen aus der Mitte, Abbruch, bereits vorhandene Datei, Netzfehler. Der Inhalt stimmte in allen Fällen per SHA-256 mit der Vorlage überein.

**Bekannte Grenze:** Geprüft wird die Größe, nicht der Inhalt. Eine `.teil`-Datei, die von einem *anderen* Download stammt und zufällig zur selben Zielgröße führt, würde nicht auffallen. In der Praxis kann das nur eintreten, wenn eine Teildatei von Hand verändert wurde.

---

## Geänderte Dateien

| Datei | Änderung |
| --- | --- |
| `ps5_validator/utils/ps5_downloads.py` | **neu** – Adressen, Einordnung, Zielpfade (ohne GUI- und Netzbezug) |
| `PS5ImageConverter_Pro_FINAL_revised.py` | Download-Fenster, Vorgang, Weiche am Download-Knopf, Einstellungseintrag |
| `ps5_validator/utils/i18n.py` | 45 neue Schlüssel, deutsch und englisch |
| `test_downloads.py` | **neu** – 35 Tests |
