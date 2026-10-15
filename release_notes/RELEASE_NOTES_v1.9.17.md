Ein neuer Knopf unter „Weitere Tools" schickt den unjail-Daemon (SvenGDK) an
die Konsole. Einmal gesendet, hebt er anfragende Homebrew-Anwendungen aus ihrer
Sandbox.

## Neu: „unjail senden"

unjail ist ein Konsolen-Daemon. Einmal gesendet, gibt er Homebrew-Anwendungen,
die danach fragen, Schreibzugriff außerhalb ihres eigenen Ordners – er läuft
dann bis zum Neustart der Konsole.

Im Fenster trägst du die **PS5-Adresse** ein und drückst **An PS5 senden**. Der
Payload geht über denselben erprobten Weg wie jeder andere (elfldr, sonst der
Payload Manager). Ein Protokoll und eine Statuszeile zeigen die ganze Zeit, was
läuft, und geben die Antwort der Konsole wieder.

Schicke unjail **einmal, bevor** du eine Homebrew startest, die Schreibzugriff
außerhalb ihres Ordners braucht.

### Firmware

unjail ist für die Firmwares **1.00 bis 10.60** verifiziert: Der Start läuft
durch, der Listener öffnet, Rechteanfragen gelingen. Ab **11.00** ist er noch
nicht verifiziert – der Start bricht ab, bevor der Daemon bereit ist. Auf einer
**12.00-Konsole** funktioniert er derzeit nicht. Das Fenster nennt diese
Abdeckung ausführlich.

### Lizenz

unjail steht unter der **GPL-3.0**. Lizenztext und Quellcode liegen dem
Programm im Ordner `helloworld/unjail-ps5app-payload-1.0/` bei.

## Dateien

| Datei | Plattform |
| --- | --- |
| `PS5_Dump_Image_Converter_v1.9.17.exe` | Windows 64-bit |
| `SOURCE_FILE_MANIFEST_v1.9.17.sha256` | Prüfsummen der Quelldateien |

Die Programmdatei läuft eigenständig; es muss nichts nachinstalliert werden.
