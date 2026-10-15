# PS5 Dump & Image Converter v1.9.36

Ein AMPR-EMU-Asset-Pack lässt sich jetzt in ein **fertiges** Backup
nachrüsten, ohne es dafür umzuwandeln.

## Neu: Knopf „Asset-Pack bauen“ in Aufgabe 7

Asset-Pack-Bänder entstanden bisher allein beim **Erstellen** eines
Abbilds – Kästchen „AMPR EMU“, Methode „Asset-Pack“. Ein fertiges Backup
nachzurüsten hieß, es noch einmal durch eine der Aufgaben 1 bis 6 zu
schicken.

Der AMPR-EMU-Manager macht es jetzt selbst. Alle vier Quellen, die
Aufgabe 7 ohnehin annimmt, sind dabei:

| Quelle | Ablauf |
| --- | --- |
| Ordner | direkt gepackt |
| `.ffpfsc` / `.ffpfs` | entpackt, gepackt, zurückgepackt |
| `.exFAT` | entpackt, gepackt, zurückgepackt |
| `.ffpkg` | entpackt, gepackt, zurückgepackt |

## Die Fassung entscheidet der Anwender

Gepackt wird mit der AMPR-Fassung, die im Auswahlfeld des Fensters steht –
gesucht wird nichts automatisch. Bänder lesen kann nur eine Fassung der
Bauart **test-pack** oder **test-debug-pack**; steht die Auswahl auf einer
anderen, meldet das Fenster es **sofort** statt nach einer halben Stunde
Packen.

Auch das Packwerkzeug selbst wird vorher geprüft, und der Lauf bricht ab,
wenn `ampr_emu.index` fehlt: Das Werkzeug liest ihn, um die fileIds zu
vergeben. Erst **Nur Index neu bauen**, dann das Asset-Pack.

## Was der Knopf nicht tut

- Er läuft **nur auf ausdrücklichen Knopfdruck**, nie nebenbei nach einer
  anderen Aktion des AMPR-EMU-Managers.
- Er entfernt **keine** Originaldateien. Das Abbild enthält danach
  Originale und Bänder, der **Inhalt** wächst also. Ein verlässlich
  kleineres Abbild entsteht über die Aufgaben 1 bis 6.
- Ein „Asset-Pack entfernen“ gibt es weiterhin nicht: Ohne Originale wären
  die Bänder die einzige Kopie der Spieldaten.

> **Nachträglich berichtigt (21.09.2026).** Hier stand, das Abbild werde
> „größer, nicht kleiner“. An einem echten Abbild nachgemessen stimmt das so
> nicht: Der **Inhalt** wuchs um 4,2 % (260.935.330 → 271.961.880 Byte), die
> **Abbilddatei** wurde aber um 24 % kleiner (364.904.448 → 275.972.096 Byte)
> – die Quelle hatte 28,5 % Verschnitt, und der eingebaute exFAT-Schreiber
> arbeitet ohne freie Zuordnungseinheiten. Verlässlich ist nur die Aussage
> über den Inhalt; die Dateigröße entscheidet die Quelle. Ausführlich in den
> Notes zu v1.9.37.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.36.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.36_linux_x86_64` – nach dem Download ausführbar machen:

  ```
  chmod +x PS5_Dump_Image_Converter_v1.9.36_linux_x86_64
  ```

- **Prüfsummen:** `SOURCE_FILE_MANIFEST_v1.9.36.sha256` listet die SHA-256 aller Quelldateien dieser Fassung.
