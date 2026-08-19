# PS5 Dump & Image Converter v1.8.58 – Release Notes

## Zweck dieses Releases

Das Programm hat Fehler gemacht, die niemand sehen konnte — auch der Diagnosebericht nicht. Diese Version fängt sie ab und sagt dazu, in welchem Zustand die Anzeige war.

Anlass war eine Frage: ob die Diagnose eigentlich alle Fehler aufnimmt, auch Darstellungsfehler der Oberfläche. Die Antwort war nein — und beim Nachsehen kam etwas Schwerwiegenderes heraus.

---

## Der Befund: Fehler landeten im Nichts

```text
report_callback_exception / sys.excepthook / threading.excepthook:  0 Treffer
```

Das Programm fing unbehandelte Ausnahmen **nirgends** ab. Zusammen mit dem Bau als Fensteranwendung (`console=False` in der Spec) heißt das: `sys.stderr` ist leer, und genau dorthin schreibt Tkinter jeden Fehler aus einem Knopf-Handler oder einer Bindung.

**Ein Fehler in der Oberfläche verschwand spurlos.** Kein Protokolleintrag, keine Meldung, nichts im Diagnosebericht — der Knopf tat einfach nichts.

Der macOS-Absturz aus v1.8.55 war nur deshalb greifbar, weil er *unterhalb* von Python passierte und Apple einen Bericht schrieb. Ein Python-Fehler an derselben Stelle hätte nichts hinterlassen.

### Drei Haken

| Weg | Haken |
| --- | --- |
| Knöpfe, Bindungen, `after`-Aufrufe | `root.report_callback_exception` |
| Hauptfaden | `sys.excepthook` |
| die Arbeitsfäden | `threading.excepthook` |

Jeder Fehler geht mit vollständiger Rückverfolgung ins Protokoll, in einen Ringspeicher der letzten 20 für den Bericht, und als kurze Zeile ins Konsolenfenster — sichtbar, ohne dass ein Fenster den Ablauf zerreißt.

Die Haken stehen unmittelbar hinter `freeze_support()`, also **vor** dem Aufbau der Oberfläche; Fehler beim Programmstart sind mit erfasst.

Der Melder fängt selbst alles ab. Ein Test sprengt absichtlich die Protokollfunktion und prüft, dass der Fehler trotzdem aufgezeichnet wird: **Ein Fehler beim Melden eines Fehlers darf das Programm nicht mitreißen** — im Fensterbetrieb gäbe es keinen Ort, an dem das noch sichtbar würde.

---

## Der Diagnosebericht

Bisher: System, aktuelle Aufgabe, Einstellungen, 60 Zeilen Konsole. Neu dazu:

| Abschnitt | Inhalt |
| --- | --- |
| **Anzeige** | Bildschirmgröße, Fenstergeometrie, Vollbild, `tk scaling`, Tcl/Tk-Fassung, Fenster-DPI, Schriftfamilien und gemessene Zeilenhöhe, Design, Sprache, Maße der Hintergrundbilder |
| **Laufzeitumgebung** | als EXE gebaut oder nicht, `_MEIPASS`, Rechte, Pillow/tkinterdnd2/psutil, Drag & Drop aktiv |
| **Fremdwerkzeuge** | gemerkte Pfade zu FileZilla, OSFMount, UFS2Tool mit Existenzprüfung |
| **Speicherplatz** | freier Platz auf Quelle, Ziel und Temp |
| **Fehler dieser Sitzung** | die aufgezeichneten Ausnahmen mit Rückverfolgung |
| **Protokolldatei** | 80 Zeilen aus `ps5converter.log` statt nur der 60 Konsolenzeilen |

### Zwei bewusste Entscheidungen

**Die Fremdwerkzeuge werden nicht neu gesucht** — nur die gemerkten Pfade gelesen und geprüft, ob die Datei da ist. Ein frischer FileZilla-Suchlauf durchkämmt im schlimmsten Fall alle Laufwerke; ein Diagnosebericht darf nicht minutenlang hängen. Ein Test hält fest, dass keine Suche ausgelöst wird.

**Jeder Abschnitt ist einzeln abgesichert.** Scheitert einer, steht dort „Abschnitt fehlgeschlagen: …" und der Rest wird trotzdem geschrieben — der Bericht ist genau dann gefragt, wenn etwas nicht stimmt.

---

## Was sich damit *nicht* erfassen lässt

Dass ein Fenster falsch **aussieht**, kann kein Programm an sich selbst erkennen. Dafür braucht es ein Auge und ein Bildschirmfoto.

Was der Bericht liefert, ist der Zustand dazu. Bei den vier Mac-Befunden aus v1.8.55 hätten `tk scaling`, die Fenster-DPI und die gemessene Zeilenhöhe sofort erklärt, warum die Schrift zu klein war — statt es aus Vermutungen herzuleiten.

---

## Ein Hinweis zur Erwartung

Fehler, die es womöglich schon länger gibt, werden ab jetzt **sichtbar**. Tauchen nach dem Aktualisieren Meldungen im Konsolenfenster auf, ist das kein neuer Schaden, sondern der alte, der bisher unsichtbar war.

---

## Tests

**821 Prüfungen, 0 Fehlschläge.** Neu: zehn zu den Fehlerfängern und dem Bericht — alle drei Wege, die Rückverfolgung, der Ringspeicher, das Scheitern des Melders, und dass keine Werkzeugsuche ausgelöst wird.

---

## Dateien

Ab dieser Version hängen **alle vier Plattform-Dateien** am Release:

| Datei | Bedeutung |
| --- | --- |
| `PS5_Dump_Image_Converter_v1.8.58.exe` | Windows |
| `PS5_Dump_Image_Converter_v1.8.58_linux_x86_64` | Linux x86-64 |
| `PS5_Dump_Image_Converter_v1.8.58_macos_arm64.dmg` | macOS, Apple Silicon |
| `PS5_Dump_Image_Converter_v1.8.58_macos_x86_64.dmg` | macOS, Intel |
| `SOURCE_FILE_MANIFEST_v1.8.58.sha256` | Prüfsummen aller Quelldateien |
