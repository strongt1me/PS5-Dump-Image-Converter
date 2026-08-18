# PS5 Dump & Image Converter v1.8.39 – Release Notes

## Zweck dieses Releases

Der Programmstart war unruhig: Das Fenster blitzte weiß auf, die Bedienelemente schoben sich danach sichtbar an ihren Platz, und die Cover-Vorschau in der Seitenleiste wanderte mehrfach hin und her. Dieses Release macht den Start ruhig.

Grundlage war eine Bildschirmaufzeichnung. Jeder Befund wurde am laufenden Programm nachgemessen — Einzelbilder im Abstand von 30 ms, dazu eine Auswertung der Zeilenvarianz im Seitenleisten-Ausschnitt, die Ober- und Unterkante des Covers auf das Pixel genau verfolgt.

---

## Was zu sehen war

| Befund | Messung |
| --- | --- |
| Hauptfenster erscheint weiß | zwei Einzelbilder vollflächig weiß (96 % / 99 %) |
| Bedienelemente schieben sich an ihren Platz | über rund eine Sekunde |
| Download-Fenster erst weiß, Inhalt später | dasselbe Muster |
| Spielname steht **über** dem Cover | Textzeile bei y=561, Cover erst ab y=571 |
| Cover wandert | 584 → 548 → 569 px, dazwischen 0,8 s ganz leer |

---

## Die fünf Ursachen

**1. Weißes Fenster.** Tk zeichnet ein frisches Fenster zuerst in seiner weißen Standardfarbe. Die dunkle Farbe wurde erst danach gesetzt — zu spät. Betroffen waren das Hauptfenster und zehn Werkzeugfenster. Die Farbe steht jetzt schon bei der Erzeugung fest.

**2. Sichtbarer Aufbau.** Das Hauptfenster bleibt bis zum fertigen Aufbau durchsichtig und erscheint dann in einem Zug. Der naheliegende Weg, es so lange zurückzuziehen, funktioniert hier nicht: Das Maximieren beim Einrichten bildet ein zurückgezogenes Fenster wieder ab — gemessen springt seine Sichtbarkeit dabei von 0 auf 1.

**3. Spielname über dem Cover.** Der Packmanager hängt jedes Bedienelement ans Ende seiner Liste. War die Titelzeile schon eingetragen, landete ein danach eingetragenes Cover dahinter. Die Reihenfolge ist jetzt festgelegt, unabhängig davon, welcher der vier Aufrufer zuerst kommt.

**4. Cover blinkt weg.** Die Metadaten melden dreimal „kein Bild", während die Schnellvorschau längst eines derselben Quelle zeigt. Metadaten ohne eigenes Cover nehmen das vorhandene Bild jetzt nicht mehr weg. Nur ein echter Quellwechsel leert die Vorschau.

**5. Wanderndes Cover.** Die Zentrierung leitete ihren Vorlauf aus der gemessenen Position ab — also aus dem Wert, den sie selbst gerade setzt. Diese Rückkopplung schaukelte sich beim Start über 33, 21, 18, 15, 21, 24 auf 21 px ein. Der Vorlauf wird jetzt einmal gemessen, solange das Bildfeld noch leer und damit unsichtbar ist. Die Polsterung steht dadurch fest, **bevor** das Cover zum ersten Mal gezeichnet wird.

Dazu zwei Feinheiten, ohne die es weiter gezuckt hätte: Die Titelzeile wird schon zusammen mit dem Bild eingeblendet — eine leere Zeile zählt wie eine beschriftete. Und ihre Höhe wird aus der Schrift gerechnet statt am Bedienelement gemessen; der untergelegte Hintergrundausschnitt ließ die gemessene Höhe zwischen 20 und 26 px schwanken.

---

## Ergebnis, wieder gemessen

    weiße Vollbilder : keine
    Cover            : erscheint einmal bei y=576 und bleibt
    Titelzeile       : 0,17 s später, 528 geänderte Pixel – reiner Text
    danach           : unverändert bis Aufnahmeende (31 s)

Vorher waren es drei Sprünge.

---

## Weitere Änderungen

- **Der Spielname ist etwas größer** (9 statt 8 pt), und der Block aus Cover und Name sitzt 8 px tiefer als die rechnerische Mitte. Der Zusatzabstand wird aus dem Platz genommen, der sonst darunter bliebe — bei engem Raum bleibt es bei der Mitte.
- **Runde Ecken am Startbildschirm.** Gelöst über den Fensterbereich, nicht über einen Farbschlüssel: Ein Farbschlüssel würde jeden Bildpunkt derselben Farbe im Startbild mit ausstanzen. Die Fenstergröße wird in echten Bildschirmpunkten geholt, weil sie bei skalierter Anzeige von der Programmangabe abweicht. Schlägt der Eckenschnitt fehl, erscheint der Startbildschirm trotzdem — nur eckig.
- **Der Dokan-2-Installationsdialog** stand in hellen Systemfarben, benutzte für seine Hinweiszeile aber schon die Schriftfarbe des dunklen Designs: hellgrauer Text auf weißem Grund. Jetzt durchgängig dunkel.

---

## Tests

`test_sidebar_vorschau.py` ist neu und deckt zwölf Fälle ab, darunter **alle 24 Reihenfolgen** der vier Aufrufarten der Seitenleisten-Vorschau — die vertauschte Reihenfolge war genau ein solcher Sonderfall. Ein weiterer Test beschießt den Eckenschnitt mit unsinnigen Werten; er darf den Startbildschirm unter keinen Umständen verhindern.

Die Sollwerte in `test_kleine_fixes.py` sind an den neuen Abstand angepasst.

**449 Tests, alle grün.**

---

## Dateien

| Datei | Bedeutung |
| --- | --- |
| `dist\PS5_Dump_Image_Converter_v1.8.39.exe` | Ausführbares Programm |
| `SOURCE_FILE_MANIFEST_v1.8.39.sha256` | Prüfsummen aller Quelldateien |
| `CHANGELOG.md` | Kurzfassung in einfacher Sprache |
