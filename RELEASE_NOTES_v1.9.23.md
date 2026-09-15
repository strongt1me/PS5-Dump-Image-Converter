# PS5 Dump & Image Converter v1.9.23

## Behoben: Es liess sich nichts mehr packen

Unter Umständen brach jeder Packlauf sofort ab – mit einer Meldung über ein
nicht verfügbares Rechenwerk („Unable to select compression backend“) – und
es entstand keine Ausgabedatei. Ursache war ein älterer Ordner mit
nachinstallierten Zusatzpaketen im Benutzerprofil: Er stammte aus einer
früheren Python-Fassung, wurde aber bevorzugt geladen und verdeckte die
mitgelieferten Bestandteile.

Der Ordner trägt jetzt die Python-Fassung im Namen, wird nur noch **nach**
den mitgelieferten Bestandteilen durchsucht, und lässt sich das schnelle
Rechenwerk nicht laden, wird still auf das eingebaute Standardverfahren
ausgewichen statt abzubrechen.

## Sichtbarer Fortschritt statt scheinbarem Stillstand

Mehrere Schritte rechneten lange, ohne etwas anzuzeigen – von einem Hänger
nicht zu unterscheiden. Sie melden sich jetzt: das Vermessen vor der
Arbeitskopie (abbrechbar, meist ganz entfallend), die BACKPORT-Sicherung
(40–100 GB, mit Dateizahl und Datenmenge), die BACKPORT-Platzprüfung, die
Container-Kopie und die Abschlussprüfung bei 98 %.

## Diagnose prüft mehr

Sie stellt fest, ob das Rechenwerk zum Packen sich wirklich laden lässt,
prüft alle acht Aufgaben auf ihre Quell- und Zielformate und erkennt Knöpfe,
die für ihre Beschriftung zu klein sind – samt fehlender Pixelzahl. Das
betrifft vor allem hohe Bildschirmauflösungen, wo die Schrift mitwächst.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.23.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.23_linux_x86_64` – nach dem Download ausführbar machen:

  ```
  chmod +x PS5_Dump_Image_Converter_v1.9.23_linux_x86_64
  ```

- **Prüfsummen:** `SOURCE_FILE_MANIFEST_v1.9.23.sha256` listet die SHA-256 aller Quelldateien dieser Fassung.
