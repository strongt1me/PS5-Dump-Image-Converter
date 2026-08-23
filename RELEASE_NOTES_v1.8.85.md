# PS5 Dump & Image Converter v1.8.85

**23.08.2026**

Die Funktion **PS4 PKG → ffpfsc** ist wieder da — vollständig.

## Was zurückkommt

In v1.8.82 war sie entfernt worden. Sie ist jetzt in dem Zustand
wiederhergestellt, den sie unmittelbar davor hatte:

| Ort | Umfang |
| --- | --- |
| Eingebettetes Werkzeug | `PS4FFPFSC-0.2.8/` — 52 Dateien, 11 MB |
| Hauptprogramm | das Fenster (996 Zeilen), der Modulteil (138), der Einstieg `--ps4ffpsc` / `--ps4-mkpfs`, der Menüeintrag, zwei Einträge im Werkzeug-Inventar |
| Sprachdatei | 65 Schlüssel |
| Bauspezifikationen | die Bündelung in allen drei `.spec`-Dateien |
| Tests | `test_ps4_pkg_converter.py`, `test_ps4_einblendung.py`, der Layouttest, die Inventarprüfung |
| Handbuch | der Abschnitt — jetzt als **13.9** |

Der Handbuchabschnitt musste umnummeriert werden: **13.8 ist inzwischen
AMPR EMU**, das kam in v1.8.83 dazu. Die Werkzeugleisten-Tabelle nennt beide.

## Was bewusst draußen bleibt

**Der Knopf NP-BINDUNG.** Er war nicht Teil des Ausbaus in v1.8.82, sondern
schon eine Ausgabe früher entfernt worden — in v1.8.81, nachdem an der Konsole
gemessen war, dass er nichts bewirkt.

Zur Erinnerung, was damals herauskam: Ein PS4-Titel aus einem Abbild
registriert seine Trophäen nicht, weil Sonys Prüfkette ein regulär
installiertes Paket verlangt. Weder `npbind.dat` noch `param.sfo` in `appmeta`
ändern daran etwas, und selbst ein von Hand nachgebauter
Registrierungseintrag unter `/user/trophy/conf/` wurde vom System nicht
einmal angesehen. Sechs PS5-Titel aus Abbildern registrieren dagegen
einwandfrei — es liegt also nicht am Abbildbetrieb, sondern an der alten
PS4-Kette.

Wiederhergestellt wurde deshalb der Stand von **v1.8.81**, nicht der von
v1.8.80. Aus demselben Grund trägt der Handbuchabschnitt den **korrigierten**
Text: die belegte Ursache, den Gegenbeweis und alle vier widerlegten
Versuche — nicht das überholte Versprechen von v1.8.80.

## Was ebenfalls draußen bleibt

`BEFUNDE_PS4_ABBILDBETRIEB.md`, das Messprotokoll zu Trophäen,
Ladebildschirm, Ablageorten und PKG-Formaten. Es war kein Teil der Funktion,
sondern ein eigenes Dokument, dessen Löschung getrennt entschieden wurde.

## Woher die Teile kamen

Das eingebettete Werkzeug und die beiden Testdateien aus dem Commit
`f007553` (v1.8.80). Die Testdatei `test_ps4_pkg_converter.py` enthielt dort
noch die NP-Bindungs-Tests; auf sie wurde dieselbe Umstellung angewandt wie
seinerzeit in v1.8.81, sodass sie wieder exakt 35 576 Bytes misst — den Stand
vor dem Ausbau.

Der Programmcode und die Texte stammen aus Sicherungen, die unmittelbar vor
dem Ausbau angelegt worden waren und den v1.8.81-Stand tragen: Fenster
vollständig, NP-BINDUNG bereits entfernt, Trophäentext bereits korrigiert.

## Tests

**1266 laufen durch** — 71 mehr als in v1.8.84. Der Layouttest öffnet das
Fenster wieder und misst es aus (980 × 769).
