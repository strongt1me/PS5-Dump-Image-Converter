"""Oberflaechenschichten des Programms.

Das Programm hatte bis August 2026 genau eine Oberflaeche: Tkinter. Sie laeuft
auf Windows, Linux und macOS, hat aber zwei Schwaechen, die sich nicht
wegkonfigurieren lassen:

* Hintergrundbilder muessen als ``PhotoImage`` von Hand nachgezogen werden.
  Jede Groessenaenderung erzwingt ein neues Bild, sonst bleibt der alte
  Ausschnitt stehen - im Programm haengt dafuer eigens
  ``_hintergrund_beim_start_nachziehen`` mit fuenf Wiederholversuchen.
* Echte Teiltransparenz kennt Tk nur fuer ein ganzes Fenster (``-alpha``)
  oder ueber einen Farbschluessel (``-transparentcolor``), der ausserdem nur
  unter Windows wirkt. Einzelne Flaechen halbdurchsichtig uebereinanderzu-
  legen geht damit nicht.

WPF loest beides von sich aus: Ein ``ImageBrush`` skaliert mit, und jede
Flaeche hat eine eigene Deckkraft. WPF ist aber an Windows gebunden.

Damit Linux und macOS erhalten bleiben, stehen beide Oberflaechen
nebeneinander und greifen auf dieselbe Ablauflogik zu. Welche startet,
entscheidet :func:`ps5_validator.ui.plattformwahl.oberflaeche_waehlen`.
"""
from __future__ import annotations
