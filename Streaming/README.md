# Streaming – das ProsperoLight-Abbild

Hier liegt **`PPSA99002.ffpfsc`**, das Abbild von ProsperoLight: ein
Moonlight-Client, der *auf* der PS5 läuft und sich das Bild von einem
Sunshine-Host auf dem PC holt. Das Fenster **KONSOLE → ProsperoLight** findet
es hier von selbst und reicht es auf Knopfdruck an die normale Umwandlung
weiter.

Fehlt die Datei, können Sie sie im Fenster über „…“ von Hand auswählen – der
Ordner ist nur die bequeme Vorgabe.

## Was hier *nicht* liegt

Die beiden Payloads der Remote-Play-Kopplung –
`actremotelink_agent*.elf` und `actremotelink_pin_notify*.elf` – gehören in
den Ordner **`helloworld`**, zusammen mit allen anderen Payloads. Nur dort
erscheinen sie in der Schnellauswahl, und nur dort prüft die Werkzeugpflege,
ob zu jeder mitgelieferten Datei eine Zeile in `THIRD_PARTY_LICENSES.md`
steht.

## Hinweis zur Weitergabe

Das Abbild ist **nicht** Teil dieses Projekts und wird nicht mit ins Git
aufgenommen (siehe `.gitignore`). Wer das Programm weitergibt, gibt
ProsperoLight nicht automatisch mit.
