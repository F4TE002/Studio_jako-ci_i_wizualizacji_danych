# Studio jakości i wizualizacji danych

Projekt 2 z przedmiotu **Programowanie V** — aplikacja prowadząca użytkownika od wczytania
pliku CSV przez diagnozę i czyszczenie danych do wizualizacji i eksportu wyników.
Każda operacja zmieniająca zbiór jest zapisywana w dzienniku (ślad zmian), więc wynik
da się uzasadnić i odtworzyć.

## Stan realizacji

| Etap | Zakres | Status |
|---|---|---|
| Lab. 6 | Pandas: profil danych, reguły jakości, pipeline czyszczenia, raport przed/po, `cleaned.csv` | ✅ gotowe |
| Lab. 7 | Matplotlib/Seaborn: histogram, punktowy, pudełkowy, słupkowy, korelacja | ⏳ |
| Lab. 8 | GUI Tkinter/ttk: wczytywanie, profil, wybór parametrów | ⏳ |
| Lab. 9 | Osadzenie wykresu, eksport PNG/PDF/SVG, testy GUI, oddanie | ⏳ |

## Wymagania i instalacja

- Python ≥ 3.10 (testowane na 3.14, pandas 3.0)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
```

## Uruchomienie (Lab. 6)

```bash
# 1. (opcjonalnie) wygeneruj zbiór demonstracyjny z kontrolowanymi problemami
python -m studio.sample_data

# 2. profil + czyszczenie + raport
python -m studio.cli data/raw/california_housing_sample.csv

# zbiór referencyjny od prowadzącej: wrzuć plik do data/raw/ i podaj jego nazwę
python -m studio.cli data/raw/<plik>.csv --config config/cleaning_config.json --out output
```

Opcje: `--sep ";"` (wymuszony separator), `--encoding cp1250`, `--skip-bad-lines`
(pomija wadliwe wiersze zamiast przerywać).

Wyniki w katalogu `output/`:

- `cleaned.csv` — oczyszczone dane (UTF-8, przecinek),
- `report.md` — raport przed/po: profil, wykryte problemy, dziennik operacji, statystyki,
- `audit_log.csv` — ślad zmian w formie tabeli.

## Struktura

```
studio/
  loading.py      wczytywanie CSV: separator , ; \t |, przecinek dziesiętny, UTF-8/CP1250, kontrolowane błędy
  profiling.py    profil: rozmiar, typy, statystyki, braki (liczba i %), duplikaty, unikalność, kolumny stałe
  quality.py      reguły zakresu i dozwolonych kategorii, IQR — wyłącznie WYKRYWANIE
  cleaning.py     czyste funkcje czyszczące (kopie danych, zwracają liczbę zmian)
  session.py      DataSession: raw / current / audit_log, reset, eksport
  pipeline.py     pipeline sterowany plikiem JSON + walidacja konfiguracji
  report.py       raport Markdown przed/po
  cli.py          skrypt Lab. 6
  sample_data.py  generator zbioru demonstracyjnego + manifest problemów
config/cleaning_config.json   reguły jakości i strategie
data/test/                    małe pliki testowe (opis: data/test/README.md)
tests/                        testy pytest
```

## Reguły i uzasadnienie strategii

Pipeline wykonuje kroki w stałej kolejności:

1. **Pełne duplikaty** — usuwane jako pierwsze, zanim jakakolwiek zmiana mogłaby sprawić,
   że różne rekordy staną się identyczne. Domyślnie porównywane są wszystkie kolumny;
   klucz można wskazać jawnie (`duplicates.subset`).
2. **Konwersja typów** — kolumna tekstowa, w której ≥ 80% wartości to liczby, jest uznawana
   za liczbową z błędnymi tokenami (np. `?`, `brak`); tokeny zamieniane są na braki, a ich
   lista trafia do raportu.
3. **Normalizacja tekstu** — `" near bay"` → `"NEAR BAY"` (usunięcie spacji, wielkie litery).
4. **Reguły zakresu i kategorii** — granice fizycznie/definicyjnie możliwych wartości
   (np. szerokość geograficzna Kalifornii 32.5–42°, `housing_median_age` 1–52 — w źródle
   wartości są obcięte na 52, `median_house_value` ≤ 500 001 — obcięcie w spisie 1990).
   Moduł `quality` tylko **wykrywa** naruszenia; zmiana danych następuje wyłącznie
   według akcji jawnie wybranej w konfiguracji (`set_nan` / `drop` / `clip` / `flag`).
   Domyślnie `set_nan`: wartość niemożliwa to błąd pomiaru, więc traktujemy ją jak brak.
5. **Braki** — po krokach 2–4, bo one mogą tworzyć nowe braki.
   - kolumny liczbowe: **mediana** — odporna na skośność i outliery (typowe dla danych spisowych),
   - kolumny tekstowe: **dominanta** (wynik deterministyczny — przy remisie pierwsza alfabetycznie),
   - zmienna celu `median_house_value`: **usunięcie rekordu** — imputacja wartości, którą
     chcemy później analizować/przewidywać, fałszowałaby wnioski.
   - dostępne także: `mean`, `constant`, `drop` dla dowolnej kolumny.
6. **Outliery (IQR, k = 1.5)** — granice [Q1 − 1.5·IQR, Q3 + 1.5·IQR]. Domyślnie są tylko
   **oznaczane** kolumną `<kolumna>_outlier_iqr`, a nie usuwane: duże wartości liczby pokoi
   czy populacji odpowiadają po prostu dużym obszarom spisowym i są prawdziwe. Wartości
   błędne usuwa krok 4. Dla kolumny o IQR = 0 nie wykrywa się outlierów. Akcje
   `clip` (winsoryzacja) i `drop` są dostępne, ale wymagają świadomej decyzji w konfiguracji.

Konfiguracja zawiera reguły dla obu wariantów nazw kolumn California Housing
(Kaggle: `median_income`…, scikit-learn: `MedInc`…). Reguły dla nieobecnych kolumn są
pomijane i wypisywane w sekcji „Ostrzeżenia” raportu.

### Gwarancje

- `DataSession.raw` nigdy nie jest modyfikowane; `reset()` przywraca dane surowe bez
  ponownego wczytywania pliku.
- Po każdej operacji sesja automatycznie sprawdza, że **kolumny niezwiązane z operacją
  nie zmieniły się** (kolumna `unrelated_columns_unchanged` w dzienniku).
- Wynik jest **powtarzalny**: brak losowości w pipeline; raport podaje SHA-256 pliku `cleaned.csv`.

## Testy

```bash
python -m pytest -v
```

| Przypadek z macierzy testów | Test |
|---|---|
| CSV z przecinkiem i średnikiem | `test_loading.py::test_comma_and_semicolon_give_same_frame` |
| Braki liczbowe i tekstowe | `test_cleaning.py::test_numeric_imputation`, `test_text_missing_mode_and_constant` |
| Duplikaty (kontrolowana para) | `test_cleaning.py::test_only_full_duplicates_are_removed`, `test_duplicates_by_explicit_key` |
| Wartość poza zakresem — wykrycie bez zmiany | `test_quality.py::test_range_rule_detects_without_modifying` |
| Błędny plik / kodowanie / pusty plik | `test_loading.py` |
| Niepoprawne parametry reguły i konfiguracji | `test_quality.py::test_invalid_rule_parameters_raise`, `test_session_pipeline.py::test_invalid_config_is_rejected` |
| Raport wykrywa przygotowane problemy | `test_session_pipeline.py::test_profile_detects_all_injected_problems` |
| Powtarzalność i ponowny odczyt eksportu | `test_session_pipeline.py::test_cli_writes_reloadable_outputs` |
| Stała / nienumeryczna kolumna, wykresy, GUI | Lab. 7–8 |

Raport z ostatniego uruchomienia: **60 testów, 60 zaliczonych** (Python 3.14.3, pandas 3.0.3).

## Znane ograniczenia

- Wykrywanie separatora analizuje pierwsze 50 wierszy; nietypowe pliki można wczytać z `--sep`.
- Przecinek dziesiętny jest rozpoznawany tylko w plikach, w których separatorem pól nie jest przecinek.
- Zbiór `data/raw/california_housing_sample.csv` jest **syntetyczny** (schemat jak California
  Housing z Kaggle) — służy do rozwoju do czasu otrzymania zbioru referencyjnego.

## Źródła i biblioteki

- pandas — https://pandas.pydata.org/docs/ (read_csv, braki danych, duplikaty)
- Reguła IQR (Tukey, 1977) — granice Q1 − 1.5·IQR, Q3 + 1.5·IQR
- Opis zbioru California Housing — Pace & Barry (1997); dokumentacja scikit-learn `fetch_california_housing`
- Kod inspiracyjny z instrukcji projektu (`DataSession`, `iqr_mask`)
- Biblioteki: pandas, numpy, matplotlib, seaborn, pytest

## Wykorzystanie narzędzi AI

Projekt był realizowany z pomocą asystenta AI **Claude (Anthropic)** w narzędziu Claude Code.
AI pomagało w:

- zaprojektowaniu struktury pakietu i modelu sesji (na bazie kodu inspiracyjnego z instrukcji),
- pisaniu kodu wczytywania, profilowania, reguł jakości, czyszczenia i raportu,
- przygotowaniu testów automatycznych, danych testowych i generatora zbioru demonstracyjnego,
- redagowaniu dokumentacji.

Autor przejrzał wygenerowany kod, uruchomił testy, rozumie zastosowane rozwiązania
i odpowiada za decyzje dotyczące strategii czyszczenia danych.

## Autorzy

- _(imię i nazwisko, nr albumu)_
