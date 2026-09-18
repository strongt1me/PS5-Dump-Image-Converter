# PS5 Dump & Image Converter v1.9.26

Ein Nachtrag zu v1.9.25: ein neues Payload und zwei Stellen, an denen der
Diagnosebericht mehr sagt als vorher.

## Neu mitgeliefert: PKG Manager

`pkgmgr_v1.0.0.elf` kommt ab sofort mit – ein Paketverwalter für die Konsole
mit Weboberfläche (itsPLK, GPL-3.0). Er installiert `.pkg`-Dateien direkt von
USB oder über das lokale Netzwerk (Samba/SMB), beherrscht mehrteilige Pakete
samt Datenträgerwechsel, erkennt bereits installierte Fassungen und legt auf
Wunsch eine Kachel auf den Startbildschirm. Zu finden in der Schnellauswahl
der Payloads.

## Der Bericht nennt die Fassung hinter der Fassung

Bei `lz4` fallen zwei Nummern auseinander: das Python-Paket (4.4.5) und die
darin eingebettete C-Bibliothek (`liblz4` 1.9.4). Das ist unbedenklich – das
Format ist unverändert, und es gibt keine bekannte Schwachstelle –, aber bisher
sah man es nirgends. Jetzt steht beides im Diagnosebericht. `lz4` fehlte in der
Liste der geprüften Bibliotheken zudem ganz, obwohl ohne dieses Modul kein
Asset-Pack entsteht.

## Klartext-Pakete werden als solche erkannt

Der eingebaute PKG-Leser erkennt jetzt die Kennung, mit der sich ein
unsigniertes Paket als Klartext ausweist, und meldet sie. Gelesen wurden solche
Pakete schon vorher richtig – nur benannt wurden sie nicht.

## Kleinigkeiten

- Die Prüfung „Werkzeugpflege" sieht jetzt auch in den echten Payload-Ordner
  statt nur in Testordner; eine vergessene Zeile in der Lizenzdatei fällt damit
  schon im Testlauf auf.
- `lz4` ist in den Abhängigkeiten fest auf 4.4.5 gesetzt – vorher war es die
  einzige ungenaue Angabe.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.26.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.26_linux_x86_64` – nach dem Download ausführbar machen:

  ```
  chmod +x PS5_Dump_Image_Converter_v1.9.26_linux_x86_64
  ```

- **Prüfsummen:** `SOURCE_FILE_MANIFEST_v1.9.26.sha256` listet die SHA-256 aller Quelldateien dieser Fassung.
