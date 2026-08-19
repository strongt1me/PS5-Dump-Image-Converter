# PS5 Dump & Image Converter v1.8.61 – Release Notes

## Zweck dieses Releases

Drei Meldungen zum Download-Fenster, die zusammen einen Satz ergeben: *„Rechtsklick einfügen funktioniert nicht. Es wird nur ein Link angenommen. Mehrere einzufügen bewirkt nichts."*

---

## Der Rechtsklick

Belegt war er nur auf dem **Hauptfenster** – mit Vollbild, Verkleinern und Beenden. Nebenfenster sind eigene Toplevels und erben eine Bindung des Hauptfensters nicht. Im Feld für Download-Adressen passierte deshalb buchstäblich nichts.

Jetzt hat **jedes Textfeld im ganzen Programm** ein Bearbeiten-Menü: Ausschneiden, Kopieren, Einfügen, Alles markieren. Dazu Strg+A, das Tk in einem Eingabefeld sonst mit „an den Zeilenanfang" belegt.

**An der Widget-Klasse gebunden, nicht am einzelnen Feld.** Ein Feld nach dem anderen zu verdrahten hätte genau die Felder erreicht, an die man beim Schreiben denkt – und die vergessen, die später dazukommen. `bind_class` erreicht auch die, die es zum Zeitpunkt des Aufrufs noch gar nicht gibt.

Auf dem Mac zusätzlich Button-2 und Strg+Klick: Dort liefert die rechte Taste Button-2, und am Trackpad ist Strg+Klick der gewohnte Weg.

---

## „Nur ein Link wird angenommen"

Die Erkennung war nie das Problem – `eingehende_urls` liest beliebig viele Adressen aus einem Textblock, nachgemessen an echten Sony-Adressen.

Was fehlte, war der Weg hinein und die Rückmeldung heraus:

1. **Hinein** kam nur, was sich einfügen ließ. Siehe oben.
2. **Heraus** kam pro unbrauchbarer Zeile ein eigenes Hinweisfenster. Wer einen Textblock aus einer Seite einfügt, hat Beschreibungen und fremde Links dabei – und klickt sich durch mehrere Fenster, hinter denen die Liste nicht mehr zu sehen ist.

Jetzt eine Zeile im Protokoll: *„3 von 5 Adressen übernommen. 1 stand bereits in der Liste."* Verworfene gehen ins Debug-Protokoll, nicht ins Gesicht.

**Beim Einzelfall bleibt das Hinweisfenster.** Wer genau eine Adresse einfügt und sie wird nicht angenommen, will den Grund wissen. Das ist kein Widerspruch, sondern der Unterschied zwischen einer Eingabe und einem Stapel.

---

## Die Zwischenablage überwachen

Der eigentliche Wunsch: im Browser Rechtsklick auf den Link, „Linkadresse kopieren" – und mehr nicht.

Ein Haken – im Download-Fenster und in den Einstellungen, beide auf derselben Variablen. Solange er gesetzt ist, landet jede kopierte `.pkg`-Adresse von selbst in der Liste und wird geladen.

**Sie läuft unabhängig vom Download-Fenster** und schon ab dem Programmstart. Die erste Fassung endete mit dem Schließen des Fensters; das war die vorsichtige Variante und wurde ausdrücklich zurückgenommen – man sammelt Links im Browser, während das Programm im Hintergrund steht. Ist beim Fund kein Fenster offen, öffnet es sich von selbst, damit der Fund sichtbar bleibt.

**Abgefragt statt benachrichtigt:** Tk kennt kein Ereignis für eine geänderte Zwischenablage, und die Windows-API dafür hängt an einem Fensterhandle, das ein PyInstaller-Bündel nicht verlässlich hat. Alle 700 ms nachsehen ist der Kompromiss – schnell genug, dass es unmittelbar wirkt, selten genug, dass es nicht auffällt.

**Zwei Dinge, die dabei schiefgehen konnten:**

- **Beim Einschalten** hätte sofort das aufgenommen werden können, was zufällig gerade in der Zwischenablage lag. Der Inhalt beim Einschalten gilt deshalb als schon gesehen.
- **Dieselbe Adresse ein zweites Mal** ergab bisher einen zweiten Eintrag: Die Doppelt-Prüfung sah nur nach wartenden und laufenden Downloads, nicht nach fertigen. Bei einer Überwachung wäre das ein Dauerlauf gewesen. Jetzt zählt alles als doppelt außer Fehlgeschlagenem und Abgebrochenem – die soll man erneut anstoßen können.

Die Überwachung hängt am Hauptfenster, weil ein `after`-Lauf ein Fenster braucht, das ihn überlebt – das Download-Fenster tut das nicht. `_zwischenablage_starten` ist mehrfach aufrufbar, ohne einen zweiten Lauf zu erzeugen: Zwei Läufe würden die Zwischenablage doppelt so oft lesen und jeden Fund doppelt melden. Ein Test prüft genau das.

---

## Backport: „Deckung prüfen"

Bis jetzt hieß **backportiert** nur: Die Ersatzbibliotheken liegen im Ordner. Ob eine davon überhaupt exportiert, was das Spiel von ihr verlangt, hat nie jemand nachgesehen. Auf der Konsole fällt das erst beim Start auf — und dann ohne brauchbare Meldung.

Möglich wurde die Prüfung durch den **backport-helper**, der im Repo unter `PS5 SDK usw/` liegt. Nicht durch das, was er baut — das braucht Sonys Toolchain — sondern durch den NID-Algorithmus in seinen Python-Werkzeugen: SHA-1 über den Funktionsnamen plus ein fester 16-Byte-Anhang, die ersten acht Bytes als Base64 mit `+-`.

**Nachgerechnet, nicht geglaubt:** `sceKernelLoadStartModule` → `wzvqT4UqKX8`, `sceKernelDlsym` → `LwG8g3niqwA`, `sceKernelAllocateDirectMemory` → `rTXw65xmLIA`. Und an unserer **eigenen** Bibliothek gegengeprüft: `sceNpAuthCreateAsyncRequest` ergibt `N+mr7GjTvr8`, und genau dieses Symbol steht in der Exporttabelle von `libSceNpAuth.sprx`.

Damit liest das Programm jetzt die Importe des Spiels und die Exporte der Ersatzbibliotheken und schreibt ins Protokoll, welche Funktionen fehlen.

**Zwei Fallen, die dabei zugeschnappt wären:**

- **Bibliotheken nicht zusammenwerfen.** `libSceNpAuth.sprx` führt drei Bibliotheken: `libSceNpAuth` (14 Symbole), `libSceNpAuthAuthorizedApp` (1) und `libSceNpAuthCompat` (2). Die erste Fassung warf alle Exporte einer Datei in einen Topf — dann gilt ein Symbol als geliefert, das in Wahrheit unter einem anderen Namen steht, und die Prüfung schweigt genau dort, wo sie etwas sagen müsste.
- **Fremde Bibliotheken sind kein Befund.** Ein Spiel importiert aus `libkernel`, `libSceLibcInternal` und einem Dutzend weiterer — die kommen von der Konsole. Sie als „fehlend" zu melden wäre ein Fehlalarm bei jedem einzelnen Spiel. Sie stehen getrennt als „Von der Konsole kommen: …".

**Grenze, klar benannt:** Statisch gebundene Dateien haben keine Importtabelle. Sie werden gezählt und ausgewiesen („n ohne Importtabelle"), nicht stillschweigend übergangen — sonst hieße es „alles in Ordnung" über Dateien, die nie gelesen wurden.

---

## Neu: ps5_autoloader

Ein Fenster für die Startreihenfolge der Konsole, unter **WEITERE TOOLS**. Es arbeitet über FTP auf `/data/ps5_autoloader`:

- `autoload.txt` holen, bearbeiten, zurückschreiben
- Payloads hochladen und löschen
- den ganzen Ordner als **Schnappschuss** sichern und zurückspielen

**Die Suchreihenfolge steht im Fenster**, weil sie sonst überrascht: Die Konsole nimmt `ps5_autoloader/autoload.txt` von **USB**, dann aus `/data`, dann aus dem Spielstandordner — und nur die erste gefundene Datei. Wer einen Stick stecken hat, ändert mit diesem Fenster nichts, was beim nächsten Start wirkt.

**Zwei stille Fehler, gegen die das Fenster etwas sagt:**

- Nennt die `autoload.txt` eine Datei, die nicht im Ordner liegt, überspringt die Konsole die Zeile wortlos. Vor dem Schreiben wird gefragt.
- Wird eine Datei ohne Ausführungsrecht abgelegt, startet die Konsole sie nicht — auch das ohne Meldung. Deshalb geht der Upload über `ftpsrv` (Port 2121), und danach wird der Dateimodus nachgesehen.

Löschen und Zurückspielen fragen nach, beide mit „Nein" als Vorgabe.

---

## Tests

**893 Prüfungen, 0 Fehlschläge.** 53 neue: Stapelaufnahme, Doppelt-Erkennung, erneutes Aufnehmen nach Fehlschlag, die Überwachung in fünf Lagen (an, aus, unverändert, nächster Lauf geplant, Fenster geschlossen) und die Bindung des Textmenüs.

---

## Dateien

| Datei | Bedeutung |
| --- | --- |
| `PS5_Dump_Image_Converter_v1.8.61.exe` | Windows |
| `PS5_Dump_Image_Converter_v1.8.61_linux_x86_64` | Linux x86-64 |
| `PS5_Dump_Image_Converter_v1.8.61_macos_arm64.dmg` | macOS, Apple Silicon |
| `PS5_Dump_Image_Converter_v1.8.61_macos_x86_64.dmg` | macOS, Intel |
| `SOURCE_FILE_MANIFEST_v1.8.61.sha256` | Prüfsummen aller Quelldateien |
