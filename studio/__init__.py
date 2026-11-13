"""Studio jakości i wizualizacji danych — logika niezależna od GUI.

Moduły:
    loading     – odporne wczytywanie CSV (separator, kodowanie, wadliwe wiersze)
    profiling   – profil danych (rozmiar, typy, statystyki, braki, duplikaty, unikalność)
    quality     – reguły jakości (zakresy, dozwolone wartości) i wykrywanie outlierów (IQR)
    cleaning    – czyste funkcje czyszczące (nie modyfikują danych wejściowych)
    session     – DataSession: dane surowe + aktualne + dziennik operacji (audit log)
    pipeline    – konfigurowalny pipeline czyszczenia sterowany plikiem JSON
    report      – raport before/after w Markdown
    cli         – skrypt kamienia milowego Lab. 6
"""

__version__ = "0.1.0"
