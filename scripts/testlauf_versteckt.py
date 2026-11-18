# -*- coding: utf-8 -*-
"""Startet einen Befehl - meist pytest - auf einem eigenen, unsichtbaren Windows-Desktop.

Die Tests oeffnen echte Tk-Fenster (Programmfenster, Dialoge, Toplevels). Auf dem Desktop des Anwenders blitzen sie auf, stehlen den
Fokus und lassen ihn waehrend des ganzen Laufs nicht arbeiten (Ruege vom 17.11.2026). Ein Prozess, der auf einem **anderen Desktop**
derselben Fensterstation gestartet wird, zeigt nichts davon: Seine Fenster gibt es dort, sie erscheinen aber nie auf dem
sichtbaren Bildschirm und nehmen keinen Fokus. Tk laeuft dort unveraendert (gleiche Fensterklassen, gleiche Masse, Zwischenablage und
Bildschirmgroesse gelten fuer die ganze Fensterstation) - kein Test aendert sich.

Aufruf (alles hinter ``--`` ist der Befehl; Kindprozesse erben den Desktop, also auch ``subprocess.run([... pytest ...])`` in einem
Pruefskript)::

    .venv\\Scripts\\python.exe scripts\\testlauf_versteckt.py --ausgabe lauf.txt -- .venv\\Scripts\\python.exe -m pytest tests\\test_x.py -q

Ohne ``--ausgabe`` erbt der Befehl die Standardausgabe dieses Aufrufers. Rueckgabe = Rueckgabe des Befehls. Unter Linux und macOS
(kein Desktop-Begriff) startet der Befehl einfach normal.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import uuid


def _unter_windows_starten(befehl: list[str], ausgabe: str, arbeitsordner: str) -> int:
    import ctypes
    import msvcrt
    from ctypes import wintypes as wt

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    GENERIC_ALL = 0x10000000
    STARTF_USESHOWWINDOW, STARTF_USESTDHANDLES = 0x1, 0x100
    CREATE_UNICODE_ENVIRONMENT = 0x400
    INFINITE = 0xFFFFFFFF

    class STARTUPINFOW(ctypes.Structure):
        _fields_ = [("cb", wt.DWORD), ("lpReserved", wt.LPWSTR), ("lpDesktop", wt.LPWSTR), ("lpTitle", wt.LPWSTR),
                    ("dwX", wt.DWORD), ("dwY", wt.DWORD), ("dwXSize", wt.DWORD), ("dwYSize", wt.DWORD),
                    ("dwXCountChars", wt.DWORD), ("dwYCountChars", wt.DWORD), ("dwFillAttribute", wt.DWORD),
                    ("dwFlags", wt.DWORD), ("wShowWindow", wt.WORD), ("cbReserved2", wt.WORD),
                    ("lpReserved2", ctypes.POINTER(ctypes.c_byte)), ("hStdInput", wt.HANDLE), ("hStdOutput", wt.HANDLE),
                    ("hStdError", wt.HANDLE)]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [("hProcess", wt.HANDLE), ("hThread", wt.HANDLE), ("dwProcessId", wt.DWORD), ("dwThreadId", wt.DWORD)]

    user32.CreateDesktopW.argtypes = [wt.LPCWSTR, wt.LPCWSTR, ctypes.c_void_p, wt.DWORD, wt.DWORD, ctypes.c_void_p]
    user32.CreateDesktopW.restype = wt.HANDLE
    user32.CloseDesktop.argtypes = [wt.HANDLE]
    kernel32.CreateProcessW.argtypes = [wt.LPCWSTR, wt.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, wt.BOOL, wt.DWORD, ctypes.c_void_p,
                                        wt.LPCWSTR, ctypes.POINTER(STARTUPINFOW), ctypes.POINTER(PROCESS_INFORMATION)]
    kernel32.CreateProcessW.restype = wt.BOOL
    kernel32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
    kernel32.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
    kernel32.CloseHandle.argtypes = [wt.HANDLE]
    kernel32.GetStdHandle.argtypes = [wt.DWORD]
    kernel32.GetStdHandle.restype = wt.HANDLE

    name = "ps5conv_test_%s" % uuid.uuid4().hex[:10]
    desktop = user32.CreateDesktopW(name, None, None, 0, GENERIC_ALL, None)
    if not desktop:
        raise OSError(ctypes.get_last_error(), "CreateDesktopW fehlgeschlagen")
    offene: list = []
    try:
        if ausgabe:
            datei = open(ausgabe, "wb")
            offene.append(datei)
            aus = msvcrt.get_osfhandle(datei.fileno())
            os.set_handle_inheritable(aus, True)
            fehl = aus
        else:
            aus, fehl = kernel32.GetStdHandle(wt.DWORD(-11)), kernel32.GetStdHandle(wt.DWORD(-12))
        nul = open(os.devnull, "rb")
        offene.append(nul)
        ein = msvcrt.get_osfhandle(nul.fileno())
        for h in (ein, aus, fehl):
            if h not in (None, 0, -1):
                try:
                    os.set_handle_inheritable(int(h), True)
                except OSError:
                    pass
        si = STARTUPINFOW()
        si.cb = ctypes.sizeof(si)
        si.lpDesktop = "winsta0\\" + name
        si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW
        si.wShowWindow = 0                     # SW_HIDE
        si.hStdInput, si.hStdOutput, si.hStdError = ein, aus, fehl
        pi = PROCESS_INFORMATION()
        zeile = ctypes.create_unicode_buffer(subprocess.list2cmdline(befehl))
        ok = kernel32.CreateProcessW(None, zeile, None, None, True, CREATE_UNICODE_ENVIRONMENT, None, arbeitsordner,
                                     ctypes.byref(si), ctypes.byref(pi))
        if not ok:
            raise OSError(ctypes.get_last_error(), "CreateProcessW fehlgeschlagen: %s" % subprocess.list2cmdline(befehl))
        kernel32.CloseHandle(pi.hThread)
        try:
            kernel32.WaitForSingleObject(pi.hProcess, INFINITE)
            code = wt.DWORD()
            kernel32.GetExitCodeProcess(pi.hProcess, ctypes.byref(code))
            return int(code.value)
        finally:
            kernel32.CloseHandle(pi.hProcess)
    finally:
        for datei in offene:
            datei.close()
        user32.CloseDesktop(desktop)


def befehl_aufloesen(befehl: list[str], ordner: str) -> list[str]:
    """Ein relativer Programmpfad (``.venv\\Scripts\\python.exe``) gilt ab ``ordner`` - wie unter Linux und macOS (``cwd=``).

    ``CreateProcessW`` loest ihn sonst gegen den Ordner des Aufrufers auf, nicht gegen ``lpCurrentDirectory``: Mit ``--ordner X``
    scheiterte ein relativer Befehl mit ``OSError 2``. Ein Name ohne Ordnerteil (``python``) bleibt, wie er ist (Suche im PATH); ein
    Pfad, den es ab ``ordner`` nicht gibt, ebenso.
    """
    programm = befehl[0]
    if os.path.isabs(programm) or not (os.sep in programm or (os.altsep and os.altsep in programm)):
        return list(befehl)
    kandidat = os.path.join(ordner, programm)
    return [os.path.abspath(kandidat) if os.path.exists(kandidat) else programm, *befehl[1:]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Befehl auf einem unsichtbaren Windows-Desktop ausfuehren (Tests ohne Fenster).")
    parser.add_argument("--ausgabe", default="", help="Standard- und Fehlerausgabe des Befehls in diese Datei schreiben")
    parser.add_argument("--ordner", default=os.getcwd(), help="Arbeitsordner des Befehls (Vorgabe: der jetzige)")
    parser.add_argument("befehl", nargs=argparse.REMAINDER, help="-- <Befehl> <Argumente>")
    a = parser.parse_args(argv)
    befehl = a.befehl[1:] if a.befehl and a.befehl[0] == "--" else a.befehl
    if not befehl:
        parser.error("kein Befehl angegeben (nach -- )")
    if sys.platform != "win32":
        if a.ausgabe:
            with open(a.ausgabe, "wb") as datei:
                return subprocess.call(befehl, cwd=a.ordner, stdout=datei, stderr=subprocess.STDOUT)
        return subprocess.call(befehl, cwd=a.ordner)
    return _unter_windows_starten(befehl_aufloesen(befehl, a.ordner), a.ausgabe, a.ordner)


if __name__ == "__main__":
    sys.exit(main())
