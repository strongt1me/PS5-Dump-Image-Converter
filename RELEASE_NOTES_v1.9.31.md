# PS5 Dump & Image Converter v1.9.31

Asset-Packs: Spiele stürzten kurz nach dem Start ab. Die Ursache ist gefunden
und doppelt abgesichert.

## Warum kein Spiel mit Asset-Pack lief

Beim Packen wanderten auch Dateien in die Bänder, die **das System selbst
liest** – nicht der AMPR EMU: `cache_ps5/playgo.pgm`,
`cache_ps5/game.sprig.packman` und die `pgc_*_dummy_file`. Solange die
Originale liegen blieben, fiel das nicht auf. Wer aber beim Bau „Originale
weglassen" wählte, bei dem wurden genau diese Dateien aus dem Spielordner
**gelöscht** – und PlayGo liest sie an der Emulation vorbei. Das Spiel fragte,
bekam nichts und stürzte rund eine Sekunde nach dem Start ab.

Nachgemessen an einem echten Abbild (Ghost of Yotei, 96,7 GB): Das Manifest
führte 84.182 von 84.219 Dateien als gepackt, darunter alle genannten
Systemdateien; im Abbild lagen danach noch 57 Dateien. Im Systemprotokoll der
Konsole steht der Absturz als `SIGSEGV`, Fehleradresse `0x20`, und die
Rücksprungkette liegt vollständig im Spielcode – der Emulator taucht darin
nicht auf. Der Absturz sieht gleich aus, egal welche Fassung des AMPR EMU
eingebaut ist; geprüft wurde mit 0.3.6.6 und 0.4.2.1.

Jetzt gilt: Diese Dateien landen **nie** in einem Band. Ebenso bleiben Filme
(`movies/`) außen vor – so halten es auch die veröffentlichten Packprofile für
Ghost of Yotei, Final Fantasy VII Rebirth und Spider-Man 2.

## Der zweite Riegel

Die Ausschlussliste allein genügt nicht, denn ein eigenes Packprofil kann sie
umgehen. Deshalb sieht das Programm jetzt zusätzlich ins **fertige Manifest**:
Steht dort eine solche Systemdatei als gepackt, bricht der Bau ab, **bevor**
irgendetwas in den Spielordner übernommen oder gelöscht wird – mit einer
Meldung, die die betroffene Datei nennt.

## Was die Konsole braucht, steht jetzt beim Bauen im Protokoll

Ein Asset-Pack hängt nicht nur am Abbild, sondern auch an zwei Einstellungen
von ShadowMount+ – und je nach Spiel am PlayGo-Stub. Das Programm schreibt
diese Punkte jetzt ans Ende des Baus, für genau das Abbild, das gerade
entstanden ist:

- **`backport_fakelib=1`** in der `config.ini` von ShadowMount+ hängt den
  Ordner `fakelib` aus dem Abbild nach `common/lib` – nur so wird der
  eingebaute AMPR EMU überhaupt geladen. Das ist die Voreinstellung.
- **`global_fakelib_priority`** steht voreingestellt auf `game`, die Fassung
  aus dem Abbild gewinnt also. Steht dort `global` und liegt in
  `/data/shadowmount/fakelib` ein eigenes `libSceAmpr.sprx`, gewinnt jenes –
  und muss dann ebenfalls pack-fähig sein. (Am 20.09.2026 an der Konsole
  nachgemessen: Der Emulator meldete danach die globale Fassung.)
- **PlayGo:** Erklärt der Titel Sprach- oder Szenariopakete
  (`sce_sys/playgo-scenario.json`), gehört der Stub mit ins Abbild, sonst
  wartet das Spiel auf Pakete, die nie kommen.

Dieselben Punkte stehen jetzt auch im Benutzerhandbuch im Abschnitt zur neuen
Methode.

## Was das für vorhandene Abbilder heißt

Ein Abbild, das mit „Originale weglassen" gebaut wurde, lässt sich nicht
reparieren: Die Dateien fehlen darin physisch. Es muss neu gebaut werden. Die
Anleitung des Entwicklers empfiehlt ohnehin, jedes Spiel **zuerst mit
behaltenen Originalen** zu testen – so ist es auch voreingestellt.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.31.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.31_linux_x86_64` – nach dem Download ausführbar machen:

  ```
  chmod +x PS5_Dump_Image_Converter_v1.9.31_linux_x86_64
  ```

- **Prüfsummen:** `SOURCE_FILE_MANIFEST_v1.9.31.sha256` listet die SHA-256 aller Quelldateien dieser Fassung.
