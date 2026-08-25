## Was ist neu

**Die Oberfläche schreibt endlich richtig Deutsch.**

An vielen Stellen stand bisher die Behelfsschreibweise: „fuer" statt „für",
„ueber" statt „über", „geprueft" statt „geprüft". Das betraf das Protokoll im
Hauptfenster, die Meldungen der Prüfung, die Anzeigediagnose, die
Umgebungsprüfung und die Hinweise in den Dialogen.

Umgestellt sind **410 Textstellen** im Programm. Ein Beispiel aus der
Diagnose:

| | |
| --- | --- |
| vorher | `Sichtbare Raender: keine (Fokusrahmen zaehlen nicht mit)` |
| jetzt | `Sichtbare Ränder: keine (Fokusrahmen zählen nicht mit)` |

**Die Dokumente ebenfalls.** Im Benutzerhandbuch waren es neun Stellen; das
PDF ist neu erzeugt. Die mitgelieferte ShadowMount+-Anleitung war bereits
korrekt und bleibt unverändert — sie stammt von einem anderen Autor.

Im Changelog bleibt die alte Schreibweise an einer Stelle absichtlich stehen:
im Eintrag zu dieser Version, wo das Vorher zitiert wird.

## Warum das nicht „suchen und ersetzen" war

Die Buchstabenfolge „ue" steht auch dort, wo kein Umlaut hingehört — in
„neue", „Quelle", „Steuerung", „Vertrauenswürdig". Eine schlichte Ersetzung
hätte daraus „nü" und „Vertraünswürdig" gemacht.

Umgestellt wurde deshalb über eine **geprüfte Wortliste**: 278 Kandidaten aus
dem eigenen Quelltext gesammelt, jeder einzeln entschieden. Was nicht in der
Liste steht, wird nicht angefasst — und ein unbekanntes Wort bricht den Lauf
ab, statt zu raten.

Drei Durchgänge waren nötig, weil jeder eine andere Textform erreicht:
einzeilige Literale, dann mehrzeilige und zusammengesetzte, zuletzt
f-Strings — die zerlegt Python seit Version 3.12 anders.

**Was bewusst gleich bleibt:** Platzhalter wie `{hoehe}` sind Kennungen, keine
Sprache. Übersetzt man sie, findet das Programm sie nicht mehr und in der
Anzeige stünde die geschweifte Klammer statt der Zahl. Genau das ist beim
zweiten Durchgang passiert und wurde zurückgedreht; ein neuer Test steht jetzt
davor. Die Kommentare im Quelltext sind Entwicklertext und wurden nicht
angefasst — nachgemessen: davor wie danach dieselbe Zahl.

## Downloads

| Plattform | Datei |
| --- | --- |
| Windows | `PS5_Dump_Image_Converter_v1.8.99.exe` |
| Linux | `PS5_Dump_Image_Converter_v1.8.99_linux_x86_64` |
| macOS (Apple Silicon) | `PS5_Dump_Image_Converter_v1.8.99_macos_arm64.dmg` |
| macOS (Intel) | `PS5_Dump_Image_Converter_v1.8.99_macos_x86_64.dmg` |

Prüfsummen aller Quelldateien: `SOURCE_FILE_MANIFEST_v1.8.99.sha256`

## Hinweis

Nur für **eigene, rechtmäßig erworbene** Inhalte. Das Umgehen technischer
Schutzmaßnahmen und die Verbreitung urheberrechtlich geschützter Inhalte sind
nicht Zweck dieses Projekts. Nutzung auf eigene Verantwortung; keine Verbindung
zu Sony Interactive Entertainment. Einzelheiten im
[Haftungsausschluss](https://github.com/strongt1me/PS5-Dump-Image-Converter#haftungsausschluss).

## Geprüft

1554 Tests grün, Anzeigediagnose ohne Auffälligkeit, Umgebungsprüfung 14/0.

Vierzehn Tests prüften noch auf die alte Schreibweise und sind nachgezogen.
Gefunden wurden sie nicht durch Durchsehen, sondern über eine Regel: Kommt eine
Zeichenkette in alter Form nicht mehr im Programm vor, in neuer aber schon, ist
es eine Erwartung an die Ausgabe. Das trennte die vierzehn von rund 130
Stellen, die nur Fehlermeldungen der Tests selbst sind und bleiben dürfen.

Nachgemessen wurde außerdem, dass die Ausgabe auch auf einer Konsole mit
Codepage 850 lesbar bleibt — das Programm stellt seine Ausgabe selbst auf
UTF-8 um.

**Nicht angefasst:** `ss` → `ß`. Wo ein Wort beides braucht, steht es richtig
(„Größe", „äußere", „vergrößert"); ein eigener Durchgang für „heisst" oder
„Grossbuchstaben" wäre eine getrennte Entscheidung, weil „dass", „muss" und
„Prozess" dabei nicht umfallen dürfen.

**Vollständiges Changelog:** https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v1.8.98...v1.8.99
