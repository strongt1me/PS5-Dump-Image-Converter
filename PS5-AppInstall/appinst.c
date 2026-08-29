/* Registriert einen bereits abgelegten App-Ordner auf der PS5.
 *
 * Das Beispiel des PS5-Payload-SDK (samples/install_app) schreibt die
 * Title-ID beim Uebersetzen fest hinein. Fuer ein Werkzeug taugt das
 * nicht: Man muesste fuer jede Anwendung neu uebersetzen, und dafuer
 * braeuchte jeder Anwender die Werkzeugkette.
 *
 * Diese Fassung liest die Kennung stattdessen zur Laufzeit aus
 * /data/appinst.txt. Das aufrufende Programm legt die Datei vorher per
 * FTP ab; das Payload bleibt eines fuer alle Faelle.
 *
 * Bewusst *keine* Reihensuche ueber /user/app: Dort stehen auch die
 * echten Anwendungen der Konsole. Ein Payload, das alles registriert,
 * was es findet, ist ein Payload, das irgendwann etwas anfasst, das
 * niemand gemeint hat.
 *
 *
 * Welche Funktion registriert
 * ---------------------------
 * Das SDK-Beispiel ruft sceAppInstUtilAppInstallTitleDir. Diese Funktion
 * gibt es nicht auf jeder Firmware. Am 29.08.2026 auf einer echten
 * Konsole gemessen - sie war dort nicht aufloesbar, und zwar auch unter
 * elfldr nicht:
 *
 *     [payload.elf] Unable to resolve 'sceAppInstUtilAppInstallTitleDir'
 *     # process pid=114, payload.elf calls exit() exit_value=ffffffff.
 *
 * Ein unaufloesbares Symbol laesst der Loader das ganze Payload gar nicht
 * erst starten. Deshalb sceAppInstUtilAppInstallAll, die dort vorhanden
 * ist. Denselben Weg geht apr-emu-updater, das beide Funktionen kennt und
 * fuer die erste eigens die Meldung "is unavailable" bereithaelt.
 *
 * Der Unterschied ist nicht kosmetisch: AppInstallAll registriert alles
 * Anstehende, nicht gezielt eine Kennung. Gemessen hat das genuegt; wer
 * es genauer braucht, muss die andere Funktion suchen.
 *
 *
 * Was der Loader koennen muss
 * ---------------------------
 * Die Sony-Funktionen werden beim Uebersetzen dazugebunden und erst vom
 * Loader aufgeloest. Das setzt **elfldr auf Port 9021** voraus - die
 * Umgebung, fuer die das SDK-Beispiel gebaut ist. Unter dem Loader des
 * Payload Managers (v0.5.1) geht es auf keinem Weg:
 *
 *   - gebunden:            "Unable to resolve ..."
 *   - dlsym(RTLD_DEFAULT): liefert 0 / 0
 *   - dlopen(MODUL):       bringt den Prozess um, ohne jede Meldung
 *   - sceKernelLoadStartModule: dito - das Symbol gibt es im SDK doppelt
 *     (Import *und* BSS-Zeiger in crt1.o), eine eigene Deklaration bindet
 *     an den unaufgeloesten Import und faehrt gegen die Wand.
 *
 * Fehlt elfldr, laedt das aufrufende Programm ihn ueber den Payload
 * Manager nach (siehe payload_versand.py). OnionHEN und etaHEN helfen
 * dabei *nicht* - OnionHEN sagt selbst "The elfldr on port 9021 is
 * REQUIRED".
 *
 *
 * Warum ein Protokoll in eine Datei
 * ---------------------------------
 * printf kommt beim Aufrufer nur an, wenn der Loader die Ausgabe
 * zurueckreicht; elfldr tut das ueber den Socket, der Payload Manager
 * verwirft sie. Deshalb schreibt das Payload seinen Verlauf zusaetzlich
 * nach /data/appinst.log, das sich per FTP lesen laesst. Ohne das ist ein
 * Fehlschlag nicht von einem Erfolg zu unterscheiden - genau darin ist
 * die Fehlersuche mehrfach stecken geblieben.
 *
 *
 * Zum eboot.bin, das registriert wird
 * -----------------------------------
 * Nicht Sache dieses Payloads, aber die haeufigste Stolperstelle: Das
 * Modul muss mit der Autoritaet 0x31... signiert sein. Mit der Vorgabe
 * des Payload-SDK (0x38...) startet die Kachel und stuerzt sofort ab
 * (CE-108262-9, "Decrypt error in SELF block").
 *
 * Abgeleitet vom Beispiel install_app (GPL-3, John Toernblom 2025).
 */
#include <stdarg.h>
#include <stdio.h>
#include <string.h>


#define KENNUNGSDATEI "/data/appinst.txt"
#define PROTOKOLL     "/data/appinst.log"
#define ZIELORDNER    "/user/app/"


int sceAppInstUtilInitialize(void);
/* Ein Argument deklariert, auch falls die Funktion keines nimmt: Ein
 * ueberzaehliges Argument ist auf x86-64 folgenlos, ein fehlendes nicht.
 */
int sceAppInstUtilAppInstallAll(const char*);


static FILE *protokoll;


/* Schreibt in beide Richtungen: zum Aufrufer, falls der zuhoert, und in
 * die Datei, die es hinterher auch noch gibt.
 */
static void
melde(const char *format, ...) {
  va_list args;

  va_start(args, format);
  vprintf(format, args);
  va_end(args);

  if(protokoll) {
    va_start(args, format);
    vfprintf(protokoll, format, args);
    va_end(args);
    fflush(protokoll);
  }
}


/* Liest die Title-ID und schneidet Leerraum ab.
 *
 * Rueckgabe: 0 wenn etwas Brauchbares gelesen wurde.
 */
static int
kennung_lesen(char *puffer, size_t groesse) {
  FILE *datei;
  size_t i;

  if(!(datei = fopen(KENNUNGSDATEI, "r"))) {
    melde("appinst: %s nicht lesbar\n", KENNUNGSDATEI);
    return -1;
  }

  if(!fgets(puffer, (int)groesse, datei)) {
    melde("appinst: %s ist leer\n", KENNUNGSDATEI);
    fclose(datei);
    return -1;
  }
  fclose(datei);

  for(i = strlen(puffer); i > 0; i--) {
    char z = puffer[i - 1];
    if(z == '\n' || z == '\r' || z == ' ' || z == '\t') {
      puffer[i - 1] = '\0';
    } else {
      break;
    }
  }

  if(!puffer[0]) {
    melde("appinst: keine Kennung in %s\n", KENNUNGSDATEI);
    return -1;
  }
  return 0;
}


int
main(int argc, char *argv[]) {
  char kennung[64];
  int err;

  (void)argc;
  (void)argv;

  protokoll = fopen(PROTOKOLL, "w");
  melde("appinst: Lauf beginnt\n");

  if(kennung_lesen(kennung, sizeof(kennung))) {
    goto ende;
  }
  melde("appinst: registriere '%s' aus %s\n", kennung, ZIELORDNER);

  if((err = sceAppInstUtilInitialize())) {
    melde("appinst: sceAppInstUtilInitialize: %x\n", err);
    goto ende;
  }
  melde("appinst: initialisiert\n");

  if((err = sceAppInstUtilAppInstallAll(ZIELORDNER))) {
    melde("appinst: sceAppInstUtilAppInstallAll: %x\n", err);
    goto ende;
  }

  melde("appinst: '%s' registriert\n", kennung);
  if(protokoll) {
    fclose(protokoll);
  }
  return 0;

ende:
  melde("appinst: Lauf endet ohne Erfolg\n");
  if(protokoll) {
    fclose(protokoll);
  }
  return -1;
}
