# PS5 Dump & Image Converter v1.9.39

Neues Werkzeug **PKG entpacken** unter WEITERE TOOLS: Eine PS4-Paketdatei
wird zum gewöhnlichen Spielordner.

## PKG entpacken

Eine `.pkg` (Fake-PKG: Spiel, Patch oder DLC) und einen Zielordner wählen,
**Entpacken** drücken. Im Zielordner entsteht ein Unterordner mit der
Title-ID – `CUSA00775` für ein Spiel, `CUSA16627_patch_01.02` für einen
Patch, `CUSA16627_dlc_<Label>` für ein DLC – mit `eboot.bin`, `sce_sys` und
allem Weiteren. Entpackt wird mit demselben Entpacker, den
*PS4 PKG → ffpfsc* schon mitbringt.

- Balken, Größenzeile („x von y“) und Statuszeile zeigen den Fortschritt;
  **Abbrechen** geht jederzeit, **Zielordner öffnen** zeigt das Ergebnis.
- **Nichts wird überschrieben.** Gibt es den Unterordner schon, bricht das
  Fenster mit einem Hinweis ab.
- **Kein halber Stand unter dem richtigen Namen.** Geschrieben wird zuerst
  in einen `.partial`-Ordner, umbenannt erst nach der Fertigmeldung des
  Entpackers. Nach Fehler oder Abbruch wird er sichtbar entfernt.
- **Platz.** Steht die entpackte Größe fest, wird der freie Platz geprüft;
  reicht er nicht, hört das Fenster sofort auf. Gemessen: 124 MB Paket →
  404 MB Spielordner.
- **Windows-Pfadgrenze.** Der Zielpfad darf höchstens 140 Zeichen lang sein.
- Den Entpacker gibt es nur für Windows (x64) und Macs mit Apple-Prozessor.

## PS5-Pakete: nicht entpackbar

Ein PS5-Paket erkennt das Fenster an seiner Kennung und weist es ab, mit
Verweis auf **PKG lesen**. Der Entpacker der eingebetteten PKG-Bibliothek
scheiterte in beiden vorliegenden Fassungen an allen vier geprüften
PS5-Paketen – auch an einem, das dieselbe Bibliothek selbst gebaut hatte.
Retail-Pakete sind ohnehin an die Konsole gebunden.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.39.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.39_linux_x86_64` – nach dem Download ausführbar machen:

  ```
  chmod +x PS5_Dump_Image_Converter_v1.9.39_linux_x86_64
  ```

- **Prüfsummen:** `SOURCE_FILE_MANIFEST_v1.9.39.sha256` listet die SHA-256 aller Quelldateien dieser Fassung.
