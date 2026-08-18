# PS5 Dump & Image Converter v1.8.40 – Release Notes

## Zweck dieses Releases

Der Knopf **FILEZILLA** öffnete zwei ganz verschiedene Dinge: entweder Ihre eigene FileZilla-Installation – oder, wenn keine gefunden wurde, ein eingebautes FTP-Fenster. Dieses zweite Gesicht entfällt. Der Knopf startet jetzt ausschließlich FileZilla, und er findet es zuverlässiger als vorher.

---

## Der eingebaute FTP-Client ist entfernt

Das eingebaute Fenster war ein vollständiger Zwei-Fenster-Client mit Verbindungsleiste, Übertragungsleiste und Warteschlange – aber es erschien praktisch nie. Es kam erst zum Zug, wenn FileZilla **fehlt**, die angebotene Installation **abgelehnt** und der Dateiauswahl-Dialog **abgebrochen** wird.

| Entfernt | Umfang |
| --- | --- |
| Die Funktion samt Kommentarblöcken | 1853 Zeilen |
| Übersetzungen der Gruppe `ftp_client.*` (deutsch und englisch) | 104 Einträge |

Das Hauptprogramm schrumpft von 28 975 auf 27 243 Zeilen. Der Knopf **FILEZILLA** und das Tastenkürzel **Strg+Umschalt+T** starten nun beide direkt die externe Anwendung.

Unangetastet bleiben Schlüssel wie `mode.*` und `format.*`, obwohl sie in einer Textsuche ebenfalls unbenutzt wirken – sie werden zur Laufzeit zusammengesetzt.

---

## FileZilla wird zuverlässiger gefunden

Bisher half im Wesentlichen eine feste Liste bekannter Pfade. Wer FileZilla anders benannt oder direkt auf ein Laufwerk gelegt hat, fiel durch.

Neu ist ein Schritt, der **nach dem Ordnernamen** sucht: in den Programmordnern, unter `AppData` und in der Wurzel **jedes festen Laufwerks** wird jeder Ordner betrachtet, dessen Name „filezilla“ enthält – und darin bis zu zwei Ebenen tief nach der ausführbaren Datei gesucht.

Damit werden unter anderem gefunden:

| Fall | Beispiel |
| --- | --- |
| Standardinstallation | `C:\Program Files\FileZilla FTP Client\filezilla.exe` |
| Ordnername ohne Zusatz | `C:\Program Files\FileZilla\filezilla.exe` |
| Direkt auf einem Laufwerk | `C:\FileZilla\filezilla.exe` |
| Eigener Ordnername | `D:\Tools\FileZilla3_x64\filezilla.exe` |
| Portable Ablage | `…\FileZillaPortable\App\FileZilla\filezilla.exe` |

Die Laufwerke werden über die Windows-Schnittstelle ermittelt und auf **fest eingebaute** Datenträger eingeschränkt. Ein verbundenes, gerade nicht erreichbares Netzlaufwerk würde die Suche sonst sekundenlang aufhalten. Gemessen auf dem Testrechner: **1 ms**.

---

## Gesucht wird nur einmal

Hier lag ein stiller Fehler. Der einmal gefundene Pfad wurde zwar gespeichert – gelesen wurde er aber aus einem Attribut, das im ganzen Programm **nirgends gesetzt wird**:

```python
custom = getattr(self, '_settings', {}).get('filezilla_path', '').strip()
```

`getattr` lieferte damit immer ein leeres Wörterbuch. Der erste Schritt der Suche lief ins Leere, und FileZilla wurde bei **jedem** Programmstart neu gesucht.

Jetzt liest dieser Schritt aus der Einstellungsdatei, und gemerkt wird nach dem erfolgreichen Start – vorher geschah das nur auf einzelnen Suchwegen. Nachgemessen:

    Erster Knopfdruck : gemerkt war ein toter Pfad
                        gestartet   C:\Program Files\FileZilla\filezilla.exe
                        gemerkt nun C:\Program Files\FileZilla\filezilla.exe
    Zweiter Knopfdruck: aus den Einstellungen in 0,51 ms – ohne jede Suche

Passt der gemerkte Pfad eines Tages nicht mehr, weil FileZilla verschoben oder neu installiert wurde, wird er übergangen und der neue Ort gemerkt.

### Dasselbe bei OSFMount

Dort war es doppelt wirkungslos: gelesen wurde ebenfalls aus dem nicht existierenden Attribut – und `osfmount_path` wurde überdies **nirgends geschrieben**. OSFMount wurde deshalb bei jedem Einhängen eines Abbilds neu gesucht, an neun Aufrufstellen im Programm. Suche und gemerkter Pfad sind jetzt getrennt, ein Treffer wird genau einmal gemerkt.

---

## Getrennte Klapplisten für Hintergrundbilder

Die Seitenleiste hatte bisher nur den Knopf **Bild wählen …** – die
mitgelieferten Seitenleisten-Bilder waren nur über den Dateidialog erreichbar.
Sie hat jetzt dieselbe Klappliste wie der Hauptbereich.

Beide Listen zeigen nur, was in ihren Bereich passt:

| Liste | Bilder | Format |
| --- | --- | --- |
| Hintergrundbild | die breiten | quer, 1920 x 1020 |
| Sidebar-Hintergrundbild | die hohen | hoch, 320 x 1000 |

Unterschieden wird am **Seitenverhältnis**, nicht am Dateinamen. Die
mitgelieferten Seitenleisten-Bilder heißen zwar alle `s..`, ein selbst
hinzugelegtes Bild aber nicht zwingend – das Format sagt dagegen eindeutig,
wohin es gehört. Ein hohes Bild im breiten Hauptbereich würde stark verzerrt.

### Das Sidebar-Bild tritt weiter zurück

Beide Bilder liefen bisher durch dieselbe Blende (85 % Deckkraft) – und wirkten
trotzdem unterschiedlich stark. Der Grund liegt nicht in der Blende, sondern in
dem, was darüber liegt: Im Hauptbereich decken die Karten QUELLE, ZIELFORMAT und
das Protokollfenster den größten Teil des Bildes ab. In der Seitenleiste gibt es
solche Flächen nicht, dort steht das Bild über die volle Höhe frei.

Die Seitenleiste hat deshalb einen eigenen Wert bekommen: `SIDEBAR_BG_IMAGE_OPACITY`
mit **50 %**. Damit treten beide Bereiche gleich weit zurück.

### Die Statuszeile flackerte

Waehrend einer laufenden Aufgabe zuckte die Statuszeile unten rechts
(*„Aufgabe 8/8: Validierung [1.9 GB/2.5 GB]"*) sichtbar. Ursache war das
Vermessen selbst: Jede Beschriftung bekommt einen passenden Ausschnitt des
Hintergrundbilds untergelegt, und um dessen Groesse zu kennen, wurde am
**sichtbaren** Label der Ausschnitt entfernt und ein Neuzeichnen erzwungen:

```python
label.config(image="")
label.update_idletasks()      # zeichnet einmal OHNE Hintergrund
natural_size = (label.winfo_reqwidth(), label.winfo_reqheight())
```

Bei laufender Aufgabe aendert sich der Text mehrmals je Sekunde – jedes Mal
wurde neu vermessen. Gemessen wird jetzt an einem unsichtbaren Zwillingslabel,
das nie gezeigt wird. Zwei Feinheiten waren dabei noetig: Der Zwilling muss
derselben Widget-Klasse angehoeren (Inhalt und Karten sind ttk-Labels, die
Seitenleiste tk-Labels) und ebenso randlos gemacht werden – sonst mass er
durchgehend 4 Pixel zu viel.

Nachgemessen: **52 Vergleiche, 0 Abweichungen** zur bisherigen Messung, und
bei 160 Textwechseln **kein einziges Mal** ohne Hintergrundausschnitt.

### Ein Knopf „Speichern"

Der Einstellungen-Dialog hatte nur „Schließen". Jede Einstellung wird zwar
weiterhin sofort übernommen und geschrieben – sichtbar war das aber nur am
Ergebnis. Der neue Knopf sichert den angezeigten Stand geschlossen weg,
bestätigt ihn in der Statuszeile und schließt das Fenster. Ein Hinweis daneben
sagt, dass Änderungen ohnehin sofort wirken.

---

## Danksagung vervollständigt

Auf die Frage, ob wirklich alle Beteiligten genannt sind, ergab die Prüfung
sieben Lücken. Die Namen der Payload-Autoren wurden dabei **aus den Dateien
selbst** gelesen – Copyright-Zeilen, Credit-Banner und Projektadressen im ELF –
statt geraten:

| Beleg in der Datei | Ergibt |
| --- | --- |
| `Copyright (C) 2025 John T…` | John Törnblom (ftpsrv, klogsrv) |
| `NP Fake Signin (by earthonion)` | earthonion |
| `Coded by OpenSourcereR` | OpenSourcereR (ps5debug-NG) |
| `CheatRunner v0.17 by maj0r` | maj0r |
| `Built by Juma Sayeh` | PS5 Game Compressor |
| `(c) Drakmor` | nanodns |
| `Thx to VoidWhisper/Gezine/Earthonion/EchoStretch/Drakmor` | ShadowMount+ |
| Projektadressen im ELF | ps5-payload-dev, itsPLK, seregonwar |

Ergänzt wurden außerdem die Grundlagen der BACKPORT-Funktion (BestPig,
idlesauce, John Törnblom, CyB1K, PS5 BackPork Kitchen), der PlayGo-Stub und
der AMPR-EMU-Resolver, die Onlinequelle prosperopatches.com, die Bibliotheken
**psutil** und **tkinterdnd2** – sowie **psxtools.de** als Forum und Community.

`THIRD_PARTY_LICENSES.md` führt jetzt **alle 24 mitgelieferten Payloads**
einzeln auf, mit Projekt, Autor und dem jeweiligen Beleg. Wo sich kein Beleg
fand, steht das Projekt ohne Zuordnung – lieber eine Lücke als eine falsche
Zuschreibung.

### paramiko entfernt

Mit dem eingebauten FTP-Client fällt auch seine SFTP-Bibliothek weg. Sie stand
noch mit 34 Einträgen in der Bauspezifikation und wanderte damit in die EXE,
obwohl kein Code sie mehr importierte. Entfernt aus Spec, `requirements.txt`,
den Übersetzungen und der Danksagung.

---

## Tests

`test_filezilla_suche.py` ist neu und deckt 29 Fälle ab; dazu kommen sieben Fälle
für die getrennten Bilderlisten in `test_background_image.py`:

- Ordnernamen mit Zusatz, ohne Zusatz, mit Versionsnummer, in Kleinschreibung
- portable Ablage zwei Ebenen tief, Tiefengrenze, fremder Ordner, Ordner ohne ausführbare Datei
- Merken nach dem Start, Wiederverwenden beim nächsten Aufruf, toter Pfad, unveränderter Pfad wird nicht neu geschrieben
- dieselben Fälle für OSFMount
- Quelltextprüfungen: keine Reste des alten Fensters, keine Zugriffe mehr auf das leere `_settings`

**488 Tests, alle grün.**

---

## Dateien

| Datei | Bedeutung |
| --- | --- |
| `dist\PS5_Dump_Image_Converter_v1.8.40.exe` | Ausführbares Programm |
| `SOURCE_FILE_MANIFEST_v1.8.40.sha256` | Prüfsummen aller Quelldateien |
| `BENUTZERHANDBUCH.html` / `.pdf` | Handbuch, neuer Abschnitt 13.6 zur FileZilla-Suche |
