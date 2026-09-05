# PS5-AppInstall — Payload zum Registrieren einer Anwendung

`appinst.elf` wird vom Werkzeug **App direkt installieren** an einen
ELF-Loader auf der Konsole geschickt. Es liest die Title-ID aus
`/data/appinst.txt` und registriert die Anwendung, sodass sie als Kachel
im Menü erscheint.

## Herkunft und Lizenz

Abgeleitet von `samples/install_app` aus dem **PS5 Payload SDK** von
John Törnblom, veröffentlicht unter der **GNU General Public License,
Version 3 oder später**. Damit steht auch `appinst.c` unter der GPL-3.

Der vollständige Lizenztext liegt unter
<https://www.gnu.org/licenses/gpl-3.0.html>.

Der Quelltext `appinst.c` liegt dieser Ablage bei — das verlangt die
GPL, und es erspart die Frage, was in der Binärdatei steckt.

## Was gegenüber dem Vorbild geändert wurde

**1. Die Title-ID kommt zur Laufzeit.** Das SDK-Beispiel schreibt sie
beim Übersetzen fest hinein (`-DTITLE_ID=\"$(TITLE_ID)\"`). Für ein
Werkzeug taugt das nicht — jede Anwendung bräuchte ein eigenes Payload
und damit jeder Anwender die Werkzeugkette. Diese Fassung liest sie aus
`/data/appinst.txt`, die das Programm vorher per FTP ablegt.

**2. Eine andere Registrierfunktion.** Das Beispiel ruft
`sceAppInstUtilAppInstallTitleDir`. Die ist nicht auf jeder Firmware
vorhanden — am 29.08.2026 auf einer echten Konsole war sie es nicht, und
zwar auch unter elfldr nicht. Ein unauflösbares Symbol verhindert den
Start des ganzen Payloads. Deshalb `sceAppInstUtilAppInstallAll`.

Der Unterschied ist nicht kosmetisch: Diese Funktion registriert alles
Anstehende, nicht gezielt eine Kennung.

**3. Ein Protokoll auf der Konsole.** `printf` erreicht den Aufrufer nur
über elfldr; andere Loader verwerfen die Ausgabe. Das Payload schreibt
seinen Verlauf zusätzlich nach `/data/appinst.log`, lesbar per FTP.

Bewusst *keine* Reihensuche über `/user/app`: Dort stehen auch die
echten Anwendungen der Konsole.

## Voraussetzung auf der Konsole

Ein ELF-Loader auf **Port 9021**. Ist keiner da, lädt das Programm
`elfldr` selbständig über den Payload Manager nach — siehe
`ps5_validator/utils/payload_versand.py`. OnionHEN und etaHEN helfen
dabei nicht; OnionHEN verlangt seinerseits einen elfldr auf 9021.

## Neu übersetzen

Braucht das PS5 Payload SDK und dessen Werkzeugkette (unter Windows am
einfachsten in WSL):

```sh
export PS5_PAYLOAD_SDK=/pfad/zum/PS5_PAYLOAD_SDK
"$PS5_PAYLOAD_SDK/bin/prospero-clang" -Wall -Werror -g \
    -lSceIpmi -lSceAppInstUtil -lSceUserService -lSceSystemService \
    -o appinst.elf appinst.c
```

Liegt das SDK in einem Pfad mit Leerzeichen oder `&`, brechen `make` und
`ld.lld` ab. Dann hilft nur eine Kopie an einen Ort ohne solche Zeichen;
das SDK ist rund 35 MB groß.

## Randnotiz zum eboot.bin

Nicht Sache dieses Payloads, aber die häufigste Stolperstelle: Das zu
registrierende Modul muss mit der Autorität `0x31…` signiert sein.

```sh
make_fself.py --ptype fake --paid 0x3100000000000002 \
    --app-version 0x0 --fw-version 0x0 eboot.elf FAKE02932/eboot.bin
```

Mit der Vorgabe des Payload-SDK (`0x38…`) erscheint die Kachel, stürzt
beim Start aber sofort ab (`CE-108262-9`, im Kernel-Log `Decrypt error in
SELF block`). Der Wert `0x3100000000000002` ist an `libSceAmpr.sprx`
abgelesen — einem fake-signierten Modul, das jede Konsole mit
ShadowMount+ lädt.
