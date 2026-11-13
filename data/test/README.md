# Dane testowe i oczekiwane wyniki

Małe, ręcznie kontrolowane pliki używane przez testy automatyczne (`tests/`).

| Plik | Co sprawdza | Oczekiwany wynik |
|---|---|---|
| `comma.csv` | separator `,` | 4 rekordy × 5 kolumn; `price` liczbowa |
| `semicolon_decimal_comma.csv` | separator `;` + przecinek dziesiętny | identyczny DataFrame jak `comma.csv` (`price[0] = 450000.5`) |
| `bad_line.csv` | wiersz z nadmiarowym polem | tryb domyślny: `CsvLoadError` „Wadliwy wiersz…”; tryb `skip`: 2 rekordy, 1 pominięty wiersz |
| `cp1250.csv` | plik zapisany w Windows-1250 | wczytany awaryjnie jako `cp1250`, polskie znaki poprawne |
| `broken_encoding.csv` | bajty niepoprawne w UTF-8 i CP1250 | `CsvLoadError` z sugestią zapisu jako UTF-8 |
| `empty.csv` | pusty plik | `CsvLoadError` „plik jest pusty” |
| `header_only.csv` | sam nagłówek | `CsvLoadError` „tylko nagłówek” |
| `quality_problems.csv` | braki liczbowe i tekstowe, pełny duplikat (wiersze `id=1`), „prawie duplikat” (`id=5`, inna kategoria), token `?`, wartości ujemne i skrajne | profil: 1 pełny duplikat; `price` wykryta jako liczbowa z tokenem `?` (1×) |

Duży zbiór demonstracyjny `data/raw/california_housing_sample.csv` jest generowany
deterministycznie (`python -m studio.sample_data`, ziarno 42). Plik
`california_housing_sample_manifest.json` zawiera liczbę każdego wstrzykniętego problemu
oraz oczekiwany stan po czyszczeniu (1995 rekordów, 0 braków, 0 duplikatów, 0 naruszeń reguł).
Test `test_profile_detects_all_injected_problems` sprawdza zgodność raportu z manifestem.
