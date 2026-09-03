# -*- coding: utf-8 -*-
"""Zahlen lesbar machen.

Achtzehnter Schnitt der Trennung.

Kleine Umrechnungen, die keine Oberflaeche brauchen und ueberall im
Programm gebraucht werden. Der Anfang ist die Byte-Groesse: Sie steht an
78 Stellen im Monolithen, in der WPF-Oberflaeche und in den Berichten.

Warum ein eigenes Modul und nicht einfach ein Import: Solange die
Funktion eine Methode der Tk-Klasse ist, braucht jeder, der sie
benutzen will, eine Instanz dieser Klasse. Fuer eine Zahlenumrechnung
ist das eine unangemessen grosse Voraussetzung.
"""
from __future__ import annotations


def bytes_lesbar(n: int) -> str:
    """Formatiert eine Byte-Zahl lesbar (KB / MB / GB).

    Args:
        n: Anzahl Bytes. Negative Werte werden als 0 behandelt.

    Returns:
        Formatierter String, z.B. ``"3.72 GB"``.
    """
    n = max(0, n)  # Schutz vor negativen Werten
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{n / 1024 ** 3:.2f} GB"
