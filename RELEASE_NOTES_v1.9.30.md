# PS5 Dump & Image Converter v1.9.30

Der Treiber von OSFMount lässt sich jetzt im Programm einrichten – und „App
direkt installieren“ erkennt einen Erfolg auch dann, wenn die Konsole nichts
zurückmeldet.

## OSFMount: Punkt 19 richtet den fehlenden Treiber ein

OSFMount braucht zum Einhängen seinen Treiber `osfdisk`, und der gehört zu
einem virtuellen Gerät, das es von selbst nicht gibt. Fehlte nur dieser
Treiber, bot der Diagnosebericht bisher einen `pnputil`-Befehl an. Der legt das
Treiberpaket aber nur ab und installiert es auf vorhandene Geräte – das
virtuelle Gerät legt er nicht an, und so blieb der Treiber aus.

Jetzt erledigt das **Punkt 19 (OSFMount installieren)** unter „Was man sonst
ev. noch braucht“. Ist OSFMount schon da und fehlt nur der Treiber, wird nichts
heruntergeladen: Das Programm legt das Gerät an und installiert den Treiber aus
dem Programmordner von OSFMount. Lässt eine frische stille Installation den
Treiber aus, holt es ihn gleich danach nach. Dafür braucht es
Administratorrechte, die EXE hat sie. Windows fragt dabei eventuell, ob die
Gerätesoftware von PassMark installiert werden soll. Verlangt Windows danach
einen Neustart, sagt es die Erfolgsmeldung. Scheitert das Einrichten, nennt das
Fehlerfenster den Schritt und den Grund.

Auch der Diagnosebericht rät im Abschnitt *Fremdwerkzeuge* jetzt zu Punkt 19.
Das Programm selbst braucht OSFMount nicht – der eingebaute exFAT-Leser kommt
ohne aus, OSFMount springt nur bei ungewöhnlichen Abbildern ein.

## „App direkt installieren“ meldete einen Fehlschlag, der keiner war

Bei **App direkt installieren** legt das Programm die Dateien auf der Konsole ab
und lässt sie dann von einem kleinen Payload anmelden. Lauscht `elfldr` auf Port
9021, kommt dessen Ausgabe zurück, und daran liest das Programm ab, ob es
geklappt hat. Ist der Port zu, weckt das Programm `elfldr` über den Payload
Manager – und der gibt nichts zurück. Ohne Antwort meldete das Programm
zwangsläufig „Die Konsole hat das Registrieren nicht bestätigt“, obwohl die
Anwendung angemeldet sein konnte; die letzte Datei für `/system_ex` blieb dann
liegen.

Das Payload schreibt seine Meldungen auf der Konsole zusätzlich nach
`/data/appinst.log`. Genau die holt das Programm jetzt über FTP nach, wenn keine
Ausgabe zurückkam: Es wartet bis zu 20 Sekunden, bis das Protokoll sein Urteil
enthält („… registriert“ oder „Lauf endet ohne Erfolg“), und beurteilt dieses.
Damit ein Protokoll vom letzten Mal keinen Erfolg vortäuscht, überschreibt das
Programm die Datei vor dem Start mit einer einmaligen Marke – steht die noch
drin, lief das Payload nicht, und es bleibt beim Fehlschlag. Im Protokollfeld
steht eine Zeile, wenn das Protokoll von der Konsole geholt wird.

## Jedes mitgelieferte Fremdwerkzeug ist genannt

Zwei Bestandteile lagen in jeder Fassung, ohne in `THIRD_PARTY_LICENSES.md` zu
stehen: die **AMPR PackTools**, mit denen die Asset-Packs für den AMPR EMU
entstehen, und **PS5-AppInstall** – das `appinst.elf` hinter „App direkt
installieren“, abgeleitet von einem Beispiel aus John Törnbloms PS5 Payload SDK
(GPL-3.0). Beide stehen jetzt in der Lizenzdatei, im Fenster **CREDITS** und in
den Credits der README. Künftig hält ein Wächter jeden mitgelieferten Ordner
gegen die Lizenzdatei.

## Kleinigkeiten

- Alle drei Fassungen schleppten 23 Module der Bibliotheken `bcrypt` und
  `PyNaCl` mit. Sie gehörten zu `paramiko`, das das Programm längst nicht mehr
  benutzt; die Bauskripte installierten es eigens dafür. Beides ist raus, die
  Programmdateien werden dadurch etwas kleiner.
- Im Fenster **EINSTELLUNGEN** standen zwei Trennlinien unmittelbar
  übereinander. Der Abschnitt dazwischen war beim Ausbau der Bildeffekte
  entfallen, seine Linie blieb stehen.

## Aufgeräumt (für alle, die aus dem Quelltext bauen)

Eine Durchsicht des ganzen Programms hat neun Funktionen gefunden, die niemand
mehr ruft – Reste ausgebauter Teile, darunter die verworfene Vorgängerfassung
einer Bildprüfung und zwei Win32-Helfer aus der Zeit des rahmenlosen Fensters.
Sie sind entfernt, ebenso sieben Konstanten und sechs Importe, die zu ihnen
gehörten; eine Suchbedingung stand dreifach im Quelltext und steht jetzt einmal.
Vier neue Wächter halten das offen: Sie melden eine Funktion, die niemand ruft,
ungleiche Platzhalter in den deutschen und englischen Texten, Werte, die keine
Aufrufstelle liefert, und jede Oberfläche, die aus einem Arbeitsfaden
angesprochen wird.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.30.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.30_linux_x86_64` – nach dem Download ausführbar machen:

  ```
  chmod +x PS5_Dump_Image_Converter_v1.9.30_linux_x86_64
  ```

- **Prüfsummen:** `SOURCE_FILE_MANIFEST_v1.9.30.sha256` listet die SHA-256 aller Quelldateien dieser Fassung.
