## Was ist neu

**Knopf 7 führt jetzt zu allen Wegen des AMPR EMU.**

Bisher war er verstreut: Knopf 7 in der Seitenleiste bot den einen Weg, zwei
Knöpfe oben in der Titelleiste die beiden anderen. Wer nicht wusste, dass es
die oberen gibt, hat sie nie gefunden.

Jetzt öffnet **Knopf 7** ein kleines Fenster ohne Rahmen, mit runden Ecken:

* **AMPR EMU – neue Methode** (ab ShadowMount+ 1.7 alpha8)
* **AMPR EMU – alte Methode** (bis alpha6)
* **AMPR EMU ins Backup einbauen** (der bisherige Weg im Hauptbereich)

Neben den beiden Methoden steht je ein Knopf **Anleitung** — er öffnet die
Beschreibung zu genau dieser Fassung.

Ein zweiter Druck auf Knopf 7 schließt das Fenster wieder. Die beiden Knöpfe
oben in der Titelleiste sind dafür weggefallen — die Leiste hat wieder Platz.
Das Fenster nimmt die Farben des gewählten Designs an und stört
Hintergrundbilder mit Transparenz nicht.

**Die Ablage ist wählbar — pro Spiel, global oder Emulatoren.**

ShadowMount+ liest Bibliotheken aus drei Quellen. Bisher benutzte das Programm
nur die erste. Im Auswahlfenster stehen jetzt alle drei:

| Weg | Ordner | Wirkung |
| --- | --- | --- |
| Pro Spiel | Backport des Titels, sonst Spielordner | nur dieses Spiel |
| Global | `/data/shadowmount/fakelib` | jedes erfasste Spiel |
| Emulatoren | `/data/shadowmount/emus` | ab alpha8; **ersetzt nur, was schon da ist** |

Der Emulator-Ordner hat eine Einschränkung, die leicht zu übersehen ist: Er
ersetzt nur Dateien, die im fakelib des Spiels **schon liegen**. Bei einem
Spiel ohne `libSceAmpr.sprx` bringt er allein nichts. Das steht so in
`sm_fakelib.c` und jetzt auch im Fenster.

Steht in Ihrer `config.ini` ein anderer Ordner, wird der benutzt — nicht der
Standard. Ist der zugehörige Schalter aus (`global_fakelib=0`,
`update_emulators=0`), sagt das Protokoll es: Die Dateien ließen sich sonst
richtig ablegen und würden trotzdem nie benutzt. Die gewählte Ablage bleibt
gemerkt und ist am Haken zu erkennen, nicht nur an der Farbe.

## Behoben

**Der Einbau ins Backup landete im falschen Ordner.**

Wer den AMPR EMU fest in ein Backup einbaut, legt zwei Bibliotheken in einen
Ordner im Spielverzeichnis. **Welcher Ordner das sein muss, war einstellbar** —
und die falsche Wahl führte dazu, dass die Konsole die Dateien schlicht übersah.
Ohne Meldung: Das Spiel startete, nur ohne den Emulator.

Der Grund steht in ShadowMount+ selbst. Bis Fassung 1.7 alpha6 wurde `fakelib2`
bevorzugt und `fakelib` war der Rückfall; **ab alpha8 zählt im Spielordner nur
noch `fakelib`**. Eingehängt wird immer nur *ein* Ordner. Nur `fakelib` wirkt
also in beiden Fassungen — und genau dorthin legt das Programm die Bibliotheken
jetzt, ohne Nachfrage.

* **Backport und AMPR EMU benutzen denselben Ordner.** Vorher konnten sie
  auseinanderlaufen — dann wirkte einer von beiden nicht.
* **Alte Sicherungen bleiben erreichbar.** Wer früher mit `fakelib2` gearbeitet
  hat, dessen Originaldateien liegen dort. Das Zurücksetzen durchsucht deshalb
  weiterhin beide Ordner und legt **jedes** gefundene Original wieder an seinen
  Platz.

**Ohne Konsole wurde nie etwas abgelegt.**

Wer die beiden Methoden ohne Verbindung zur PS5 benutzte, wählte einen
Spielordner am Rechner aus, sah alle Schritte durchlaufen — und bekam am Ende
nur „fehlgeschlagen". Der Grund: Der letzte Schritt rief eine Funktion auf, die
es im Programm gar nicht gab. Jetzt legt er die Bibliotheken wirklich ab und
sichert ein vorhandenes Original einmalig als `.orig`.

Dazu zwei Kleinigkeiten: Der Ordner mit den Diagnoseberichten läuft nicht mehr
voll — die zehn neuesten bleiben. Und drei Stellen, an denen ein
fehlgeschlagenes Speichern stillschweigend verschluckt wurde, melden sich jetzt
im Protokoll.

## Downloads

| Plattform | Datei |
| --- | --- |
| Windows | `PS5_Dump_Image_Converter_v1.8.98.exe` |
| Linux | `PS5_Dump_Image_Converter_v1.8.98_linux_x86_64` |
| macOS (Apple Silicon) | `PS5_Dump_Image_Converter_v1.8.98_macos_arm64.dmg` |
| macOS (Intel) | `PS5_Dump_Image_Converter_v1.8.98_macos_x86_64.dmg` |

Prüfsummen aller Quelldateien: `SOURCE_FILE_MANIFEST_v1.8.98.sha256`

## Hinweis

Nur für **eigene, rechtmäßig erworbene** Inhalte. Das Umgehen technischer
Schutzmaßnahmen und die Verbreitung urheberrechtlich geschützter Inhalte sind
nicht Zweck dieses Projekts. Nutzung auf eigene Verantwortung; keine Verbindung
zu Sony Interactive Entertainment. Einzelheiten im
[Haftungsausschluss](https://github.com/strongt1me/PS5-Dump-Image-Converter#haftungsausschluss).

## Geprüft

Die volle Testreihe ist grün, dazu eine Messung am laufenden Programm:
Titelleiste ohne die beiden Knöpfe, Auswahlfenster rahmenlos mit allen
Optionen, nichts überlappt, jede Option öffnet genau ein Fenster — auch beim
zweiten Druck. Das Umschalten der Ablage wird gemerkt, und der Haken wandert
mit.

Die Regeln sind nicht geraten. Sie stammen aus einem Referenzmodul, das die
beiden ShadowMount+-Fassungen nachbildet; die Belege dafür sind
`config.ini.example`, `sm_fakelib.c`, `sm_scan.c` und `sm_paths.h` aus 1.7
alpha6 und alpha8.

**Noch nicht an echter Hardware bestätigt:** Die Änderungen verschieben, wohin
Dateien geschrieben werden. Belegt sind sie an Dateisystem und Quelltext der
Referenz, nicht an einer laufenden PS5. Bei einem Titel mit
`fakelib2`-Altbestand lohnt eine Kontrolle, ebenso der erste Lauf über den
globalen Ordner.

**Nur eine Anleitung liegt bei.** Die Beschreibung zur *alten* Methode ist
eingebettet; für die *neue* fehlt sie noch, und der Knopf sagt das mit dem
erwarteten Dateinamen, statt stumm nichts zu tun.

**Vollständiges Changelog:** https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v1.8.97...v1.8.98
