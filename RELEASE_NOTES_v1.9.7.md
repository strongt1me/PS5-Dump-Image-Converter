## Behoben: Vier Wege löschten, bevor der Ersatz fertig war

Vier Stellen räumten das vorhandene Ergebnis weg, **bevor** das neue gebaut
war. Ging beim Bauen etwas schief — volle Platte, Abbruch durch den Anwender,
ein Fehler im Werkzeug —, war beides fort.

**Der schwerste Fall traf die Quelldatei.** Steht im Feld ZIEL derselbe
Ordner, in dem die Quelle liegt — der Normalfall, wenn alles in einem
Spieleordner liegt —, dann zeigt der „erwartete Ausgabepfad" bei Zielformat
`.ffpkg` auf die Quelldatei selbst. Nachgemessen:

    _get_expected_output_path("ffpkg_to_ffpfsc",
                              "D:\PS5 Spiele\Spiel.ffpkg",
                              "D:\PS5 Spiele")   ->  dieselbe Datei

Ein „Ja, überschreiben" führte zu einem `os.remove` auf genau diese Datei,
bevor ein einziger Arbeitsschritt begonnen hatte.

**Die Sammelkonvertierung fragte gar nicht.** Der Überschreib-Block wurde
dort übersprungen, und der erste Packschritt entfernte eine vorhandene
Zieldatei kommentarlos — ausgerechnet in der Aufgabe, in der zehn Dateien in
einen Ordner gehen und Namensgleichheit beim Wiederholungslauf der Normalfall
ist. Gefragt wird jetzt vor dem Bauen, und zwar **einmal für den ganzen
Lauf**: Wer zehn Dateien einfügt, soll nicht zehn Fenster wegklicken.

Der AMPR EMU Manager entfernte den Container ebenfalls vor dem Bau. Alle
Wege bauen jetzt nach `<name>.neu` und übernehmen erst bei Erfolg. Auf
demselben Datenträger ist das unteilbar: Entweder steht dort das neue
Ergebnis oder weiterhin das alte, nie ein Rumpf.

---

## Behoben: Die Einstellungsdatei konnte komplett verschwinden

Beim Speichern der zuletzt benutzten Pfade wurde `paths.json` zuerst geleert
und dann neu geschrieben — ohne Schloss und ohne Zwischendatei, anders als
alle übrigen Einstellungen. Gemessen wurde beides:

| | beim Speichern der Pfade | bei allen anderen Einstellungen |
| --- | --- | --- |
| Abbruch beim Schreiben (volle Platte) | **0 Bytes — alles weg** | unversehrt |
| 400 gleichzeitige Speicherversuche | 4 verloren (1,0 %) | 0 verloren |
| Leser fand die Datei leer vor | 136 von 1600 (8,5 %) | — |

Das war kein Sonderfall: Der Pfad-Speicher läuft zu Beginn **jeder**
Konvertierung im Hintergrund. Es gibt jetzt genau einen Schreibweg für die
Datei; danach gemessen: 0 verlorene Speicherversuche, 0 leere Lesungen.

Der Debug-`.pkg`-Bauer überschrieb außerdem den Zielpfad ohne Rückfrage —
und er **schlägt diesen Pfad selbst vor**: Wer einen Quellordner wählt,
bekommt den Pfad eingetragen, unter dem das Paket des letzten Laufs liegt.
Bricht das Kopieren des PFS-Abbilds ab, stand dort ein Rumpf von 65.600
Bytes, groß genug, um wie ein Ergebnis auszusehen.

---

## Behoben: Die englische Oberfläche sprach Deutsch

Über 200 Texte standen fest im Programm und erschienen auch dann auf
Deutsch, wenn die Oberfläche auf Englisch stand:

* die **gesamte Statuszeile** während einer Umwandlung, einschließlich aller
  vier Phasen des `.ffpfsc`-Wegs — der exFAT-Weg direkt daneben war seit
  jeher übersetzt;
* die **Warnungen vor dem Start** (acht von neun Meldungen);
* die Meldungen zu einer **untauglichen Quelle** — zweiundzwanzig Sätze;
* das Fenster von **Aufgabe 7**, der Bericht über einen **unvollständigen
  Dump**, die **Kurzhinweise der Aufgabenknöpfe** und die Stufen des
  Fensters „Fortsetzen?".

Sechzehn Helfermodule geben ihre Sätze jetzt über Vorlagen aus, statt sie
fest zu führen. Die Übersetzungstabelle wuchs von 1791 auf 2092 Einträge.

---

## Behoben: Fenster ließen sich nicht schließen

* Im **PS4-PKG-Wandler**, im **Debug-`.pkg`-Bauer** und im
  **Umbenennen-Fenster** warf der Knopf SCHLIESSEN einen Fehler ins
  Protokoll, statt zuzumachen. Es half nur das X der Fensterleiste.
* Dem **Y2JB-Fenster** fehlte der Knopf ganz.
* Im **WebKit-Fenster** lag er über dem Knopf darüber — nachgerechnet 29
  Pixel Überlappung, und der Dank darunter wurde mitten im Wort
  abgeschnitten. Die Fensterhöhe stand fest, statt aus dem Inhalt gerechnet
  zu werden.
* **Aufgabe 7** blieb offen stehen, wenn danach eine andere Aufgabe gewählt
  wurde.

---

## Behoben: Auf dem Mac waren Knöpfe kaum zu lesen

macOS zeichnet einen einfachen Knopf als Systemknopf und ignoriert dabei die
gewählte Hintergrundfarbe. Die helle Schrift des Programms stand dadurch auf
heller Systemfläche — je nach Farbe schwer bis gar nicht lesbar; „Konsole
leeren" im Y2JB-Fenster war vollständig unsichtbar. Alle 34 betroffenen
Knöpfe sind umgestellt. Unter Windows und Linux ändert sich nichts.

---

## Weitere Behebungen

* **Fehlende Laufzeitpakete ließen sich nicht nachinstallieren.** Der Versuch
  brach mit einem internen Fehler ab, ein zweiter Anlauf stolperte über
  denselben, und die Engine startete nicht — zu lesen war nur „MkPFS kann
  nicht gestartet werden".
* **Was ein Payload zurückmeldet, steht jetzt im Protokoll.** Die Antwort der
  Konsole wurde bisher verworfen.
* **Eine geänderte PS5-Adresse wirkte nach dem ersten Verbinden nie wieder.**
  Die Fenster schrieben den vorbefüllten Wert als eigenen fest; gemessen
  zeigte KLOG weiter `192.168.1.94:3232`, obwohl in den Einstellungen
  `192.168.1.50:3333` stand.
* **Der Autoloader meldet einzelne Fehlschläge** beim Zurückspielen und
  Löschen, statt nur die Zahl der gelungenen zu nennen.
* **Die Infobox beantwortet „AMPR EMU eingebaut?"** für einen Ordner und für
  ein Abbild jetzt gleich. Der Weg über den Container zählte auch `fakelib2`
  mit — und die ignoriert ShadowMount+ ab 1.7 alpha8 ohne Meldung.

---

## Zum Prüfbestand

63 Prüfungen liefen bisher nie mit: In sieben Dateien stand der Startblock
mitten in der Datei, wodurch beim Einzelaufruf alle Klassen darunter
übersprungen wurden — der Bericht meldete trotzdem „OK". Zwei weitere
Prüfungen waren tot: Eine suchte nach einem Knopftyp, den es seit einem Umbau
nicht mehr gibt, eine andere zerbrach an jedem Zeilenumbruch im Quelltext.

Stand jetzt: **2428 Prüfungen in 121 Dateien**, alle grün.

Prüfsummen der Auslieferung: `SOURCE_FILE_MANIFEST_v1.9.7.sha256`
