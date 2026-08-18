# PS5 Dump & Image Converter v1.8.9 – Release Notes

## Zweck dieses Releases

Version **v1.8.9** ergänzt die FFPKG-Erstellung (Aufgabe 1/7) um eine Dateizahl-Prüfung nach dem UFS2-Bau: Jeder Bau-Kandidat wird nach der bestehenden Struktur- und Hashprüfung zusätzlich schreibgeschützt gemountet, seine tatsächliche Dateizahl wird mit dem Quellordner verglichen, und bei Abweichung wird der Kandidat verworfen. Die übrige Konvertierungslogik (Aufgaben 2–6, 8) ist **unverändert**.

## Symptom

Eine aus einem sehr dateireichen Quellordner (viele Kleindateien, z. B. eine Spielesammlung) erzeugte `.ffpkg` konnte auf der PS5 mit einem Startfehler (u. a. CE-108-255-1) fehlschlagen, obwohl dieselbe `.ffpkg` beim Programm selbst als vollständig geprüft und erfolgreich abgeschlossen gemeldet wurde. Andere, dateiärmere Titel sowie dieselbe Quelle als `.ffpfsc`-Ausgabe waren davon nicht betroffen.

## Ursache

Die bisherige `.ffpkg`-Validierung (`info`, schreibgeschütztes `fsck_ufs -fn`, SHA-256-Lesbarkeitsprüfung) bestätigt ausschließlich, dass das erzeugte UFS2-Dateisystem intern konsistent und vollständig lesbar ist. Sie prüft nicht, ob tatsächlich alle Dateien aus dem Quellordner im Image gelandet sind.

Die ersten beiden Bauprofile (`newfs -D`, 64-KiB- bzw. 32-KiB-Block) arbeiten mit einer festen Inode-Dichte. Nur das letzte Fallback-Profil (`makefs`) berechnet die Inode-Dichte dynamisch aus der tatsächlichen Dateizahl der Quelle. Bei einem Quellordner mit ungewöhnlich vielen Dateien kann die feste Inode-Dichte der ersten beiden Profile zu knapp bemessen sein: `newfs -D` bricht dabei nicht mit einem Fehler ab, sondern erzeugt ein strukturell gültiges UFS2-Dateisystem, in dem jedoch nicht alle Quelldateien Platz gefunden haben. Da die bestehende Validierung nur die Struktur prüft, wurde ein solches unvollständiges Image bisher unbemerkt als fertiges, geprüftes FFPKG übernommen.

## Änderung

Neue Methode `_verify_ffpkg_file_count_via_mount()` in `PS5ImageConverter_Pro_FINAL_revised.py`, eingehängt in `_build_ffpkg_from_folder()` direkt nach der bestehenden Struktur-Validierung jedes Staging-Kandidaten:

1. Der Kandidat wird schreibgeschützt über `UFS2Tool mount_udf` gemountet – derselbe Mechanismus, der bereits beim Entpacken eingebetteter `.ffpkg`-Dateien in Aufgabe 4 verwendet wird.
2. Die enthaltenen Dateien werden per `os.walk` gezählt (kein Datenkopiervorgang, nur Auflistung).
3. Die gezählte Dateizahl wird mit der zu Beginn des Baus am Quellordner ermittelten Dateizahl verglichen.
4. Weicht die Zahl nach unten ab, wird der Kandidat verworfen und – wie bei jedem anderen Validierungsfehler auch – automatisch das nächste Bauprofil versucht, bis hin zum `makefs`-Fallback mit korrekt berechneter Inode-Dichte.
5. Sind Dokan2-Treiber oder erhöhte Rechte nicht verfügbar, wird die Prüfung übersprungen und protokolliert, statt den gesamten Bauvorgang zu blockieren – Dokan2 war bisher keine Voraussetzung für die Ordner-zu-FFPKG-Erstellung und bleibt es für den Grundfall weiterhin nicht.

## Bedeutung für Nutzer

FFPKG-Dateien aus sehr dateireichen Quellordnern werden zuverlässiger vollständig erzeugt. Ein Bauprofil, dessen feste Inode-Dichte für den jeweiligen Titel nicht ausreicht, wird jetzt automatisch erkannt und verworfen, statt als scheinbar erfolgreich abgeschlossenes FFPKG ausgeliefert zu werden. Ist Dokan2 (ohnehin für Aufgabe 4 nötig) bereits installiert und läuft das Programm mit Administratorrechten, greift die neue Prüfung automatisch ohne zusätzlichen Schritt.

## Verifikation

- Syntax-Check erfolgreich: `python -m py_compile PS5ImageConverter_Pro_FINAL_revised.py`
- Code-Review bestätigt: Die neue Prüfung ist ausschließlich additiv in den bestehenden `build_attempts`-Ablauf eingehängt, verändert keine bestehenden Bauprofile oder deren Reihenfolge und bricht den Build bei fehlendem Dokan2/fehlenden Adminrechten nicht ab.
- Hardware-Test auf der PS5 durch den Nutzer steht noch aus (ursprünglicher Fehlerfall: CE-108-255-1 beim Start einer aus einem dateireichen Ordner erzeugten `.ffpkg`).

## Vollständigkeit des Release

Versionen wurden konsistent auf **v1.8.9** angehoben in:

- `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`)
- `Build_EXE.ps1` (`$EXE_VERSION`)
- `PS5ImageConverter_Pro.spec` (Kommentar + `name=...`)
- `file_version_info.txt` (`filevers`, `prodvers`, `FileVersion`, `ProductVersion`, `OriginalFilename`)
- `Start_Build.bat` (Header/Anzeige)
- `README.md`
- `BENUTZERHANDBUCH.md`
- `test_build_ready.py` (erwarteter Output-Dateiname)
- `CHANGELOG.md`
