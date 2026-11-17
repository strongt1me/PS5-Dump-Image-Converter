# -*- coding: utf-8 -*-
"""Die Aufklappliste einer ``ttk.Combobox`` so breit wie ihr laengster Eintrag (Nutzerwunsch 17.11.2026).

Gemeldet wurde: In der Liste des Zielformats stand "Dump-Ordner (mit Ei...", in der Liste der AMPR-EMU-Fassung "NG 0.4.0-beta de..." -
**Texte wurden abgeschnitten**. Tk macht die Liste genauso breit wie das Feld (``ttk::combobox::PlacePopdown`` nimmt ``winfo width``
des Feldes); ein Eintrag, der laenger ist als das Feld, wird am Rand abgeschnitten, und das Feld selbst ist oft schmal, damit die
Zeile der Aufgabe nicht ausufert.

Die Liste ist ein eigenes Fenster und waechst nach rechts, ohne das Feld zu veraendern. Eingebaut wird das **einmal fuer alle** Comboboxen
des Programms, indem ``ttk::combobox::PlacePopdown`` umhuellt wird. Die Huelle misst den laengsten Eintrag mit der Schrift der Liste
(samt Rand und - wenn die Liste rollt - Rollleiste) und gibt Tk die fehlende Breite ueber die eigene Stiloption ``-postoffset`` (Breite
und Verschiebung der Liste) mit; die urspruengliche Prozedur platziert dann wie gewohnt. Nach dem Aufruf steht die Stiloption wieder, wie sie
war. Ginge die Liste so ueber den rechten Rand des Bildschirms, rueckt sie nach links. Kuerzere Eintraege lassen sie so breit wie das Feld.

Warum nicht die Geometrie der Liste nachlesen und aendern: ``wm geometry`` liefert bei einem verborgenen Fenster die zuletzt **angewandte**
Groesse, nicht die eben gesetzte (gemessen: Die Huelle las 200 statt 1 und liess die Breite stehen).

Reine Tcl-Huelle, kein Zustand; ``installieren`` ist wiederholbar.
"""
from __future__ import annotations

import tkinter as tk

#: Der Name, unter dem die urspruengliche Prozedur von Tk erhalten bleibt (und der zeigt, dass schon installiert ist).
URSPRUNG = "::ps5conv::PlacePopdownTk"

_SKRIPT = r"""
if {[llength [info commands ::ps5conv::PlacePopdownTk]] == 0 && [llength [info commands ::ttk::combobox::PlacePopdown]] == 1} {
    namespace eval ::ps5conv {}
    # Die Breite in Pixeln, die die Liste fuer ihre Eintraege braucht (0: unbekannt).
    proc ::ps5conv::ListenBreite {cb popdown} {
        set lb $popdown.f.l
        if {![winfo exists $lb]} { return 0 }
        set values [$cb cget -values]
        if {[llength $values] == 0} { return 0 }
        set font [$lb cget -font]
        set need 0
        foreach v $values {
            set m [font measure $font $v]
            if {$m > $need} { set need $m }
        }
        # Rand der Liste und ein Streifen links und rechts vom Text; dazu die Rollleiste, wenn die Liste eine zeigt.
        set extra [expr {[font measure $font "00"] + 6}]
        if {[winfo exists $popdown.f.sb] && [llength [grid info $popdown.f.sb]] > 0} {
            incr extra [winfo reqwidth $popdown.f.sb]
        }
        set need [expr {$need + $extra}]
        # Nie breiter als der Bildschirm (die Liste soll erreichbar bleiben).
        set screen [winfo vrootwidth $popdown]
        if {$need > $screen} { set need $screen }
        return $need
    }
    rename ::ttk::combobox::PlacePopdown ::ps5conv::PlacePopdownTk
    proc ::ttk::combobox::PlacePopdown {cb popdown} {
        set style [$cb cget -style]
        if {$style eq {}} { set style TCombobox }
        set alt [ttk::style lookup $style -postoffset {} {0 0 0 0}]
        set need [::ps5conv::ListenBreite $cb $popdown]
        set feld [winfo width $cb]
        if {$need <= $feld + [lindex $alt 2]} {
            ::ps5conv::PlacePopdownTk $cb $popdown
            return
        }
        # Die Liste waechst nach rechts; ginge sie ueber den Bildschirmrand, rueckt sie nach links (nie ueber den linken Rand hinaus).
        set dx [lindex $alt 0]
        set x [expr {[winfo rootx $cb] + $dx}]
        set links [winfo vrootx $popdown]
        set rechts [expr {$links + [winfo vrootwidth $popdown]}]
        if {$x + $need > $rechts} { incr dx [expr {$rechts - $need - $x}] }
        set x [expr {[winfo rootx $cb] + $dx}]
        if {$x < $links} { incr dx [expr {$links - $x}] }
        ttk::style configure $style -postoffset [list $dx [lindex $alt 1] [expr {$need - $feld}] [lindex $alt 3]]
        try {
            ::ps5conv::PlacePopdownTk $cb $popdown
        } finally {
            ttk::style configure $style -postoffset $alt
        }
    }
}
"""


def installieren(root: tk.Misc) -> bool:
    """Umhuellt ``ttk::combobox::PlacePopdown`` (einmal je Tcl-Interpreter; jeder weitere Aufruf aendert nichts).

    Returns:
        ``True``, wenn die Huelle jetzt aktiv ist; ``False``, wenn dieses Tk die Prozedur nicht kennt (dann bleibt die Liste, wie sie war).
    """
    root.tk.eval(_SKRIPT)
    return bool(root.tk.call("info", "commands", URSPRUNG))
