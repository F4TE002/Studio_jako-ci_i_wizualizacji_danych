# Raport jakości danych — przed i po czyszczeniu

## 1. Źródło i parametry
- Plik wejściowy: `data/raw/california_housing_sample.csv` (SHA-256: `cb77bfbf652b5029…`)
- Separator: przecinek, kodowanie: `utf-8-sig`, separator dziesiętny: `.`, pominięte wadliwe wiersze: 0
- Konfiguracja reguł: `config/cleaning_config.json`
- Plik wynikowy: `output/cleaned.csv` (SHA-256: `79b1b128039088e4…`) — identyczny skrót przy każdym uruchomieniu potwierdza powtarzalność.

## 2. Podsumowanie
| miara | przed | po |
|---|---|---|
| Liczba rekordów | 2025 | 1995 |
| Liczba kolumn | 10 | 16 |
| Braki (komórki) | 110 | 0 |
| Pełne duplikaty | 25 | 0 |
| Błędne tokeny w kolumnach liczbowych | 15 | 0 |
| Naruszenia reguł jakości | 34 | 0 |

## 3. Wykryte problemy (dane surowe)
### 3.1 Profil kolumn
| column | dtype | missing | missing_pct | unique | constant |
|---|---|---|---|---|---|
| longitude | float64 | 0 | 0 | 864 | nie |
| latitude | float64 | 0 | 0 | 825 | nie |
| housing_median_age | str | 0 | 0 | 55 | nie |
| total_rooms | float64 | 0 | 0 | 1581 | nie |
| total_bedrooms | float64 | 60 | 2.96 | 867 | nie |
| population | float64 | 0 | 0 | 1335 | nie |
| households | float64 | 0 | 0 | 794 | nie |
| median_income | float64 | 20 | 0.99 | 1936 | nie |
| median_house_value | float64 | 0 | 0 | 1400 | nie |
| ocean_proximity | str | 30 | 1.48 | 7 | nie |

### 3.2 Nieliczbowe tokeny w kolumnach liczbowych
| column | token | count |
|---|---|---|
| housing_median_age | brak | 8 |
| housing_median_age | ? | 7 |

### 3.3 Reguły jakości (tylko wykrycie — bez zmiany danych)
| rule | column | violations | violations_pct | examples |
|---|---|---|---|---|
| longitude ∈ [-124.5, -114] | longitude | 0 | 0 |  |
| latitude ∈ [32.5, 42] | latitude | 6 | 0.3 | 0.0 |
| housing_median_age ∈ [1, 52] | housing_median_age | 5 | 0.25 | 999.0 |
| total_rooms ∈ [1, +∞] | total_rooms | 0 | 0 |  |
| total_bedrooms ∈ [0, +∞] | total_bedrooms | 0 | 0 |  |
| population ∈ [1, +∞] | population | 8 | 0.4 | -5.0 |
| households ∈ [1, +∞] | households | 0 | 0 |  |
| median_income ∈ [0.4999, 15.0001] | median_income | 0 | 0 |  |
| median_house_value ∈ [14999, 500001] | median_house_value | 5 | 0.25 | 9999999.0 |
| ocean_proximity ∈ {<1H OCEAN, INLAND, ISLAND, NEAR BAY, NEAR OCEAN} | ocean_proximity | 10 | 0.49 | near bay, UNKNOWN_ZONE |

### 3.4 Pełne duplikaty: **25**

## 4. Dziennik operacji (ślad zmian)
Kolumna `unrelated_columns_unchanged` potwierdza, że operacja nie zmieniła kolumn spoza swojego zakresu (sprawdzane automatycznie po każdym kroku).

| step | operation | columns | params | rows_before | rows_after | rows_affected | cells_changed | unrelated_columns_unchanged |
|---|---|---|---|---|---|---|---|---|
| 1 | usunięcie duplikatów |  | subset=wszystkie kolumny; keep=first; removed_rows=25 | 2025 | 2000 | 25 | 0 | tak |
| 2 | konwersja na liczby | housing_median_age | invalid_tokens={'brak': 8, '?': 7} | 2000 | 2000 | 15 | 15 | tak |
| 3 | normalizacja tekstu | ocean_proximity | case=upper | 2000 | 2000 | 6 | 6 | tak |
| 4 | reguła zakresu | longitude | rule=longitude ∈ [-124.5, -114]; action=set_nan | 2000 | 2000 | 0 | 0 | tak |
| 5 | reguła zakresu | latitude | rule=latitude ∈ [32.5, 42]; action=set_nan | 2000 | 2000 | 6 | 6 | tak |
| 6 | reguła zakresu | housing_median_age | rule=housing_median_age ∈ [1, 52]; action=set_nan | 2000 | 2000 | 5 | 5 | tak |
| 7 | reguła zakresu | total_rooms | rule=total_rooms ∈ [1, +∞]; action=set_nan | 2000 | 2000 | 0 | 0 | tak |
| 8 | reguła zakresu | total_bedrooms | rule=total_bedrooms ∈ [0, +∞]; action=set_nan | 2000 | 2000 | 0 | 0 | tak |
| 9 | reguła zakresu | population | rule=population ∈ [1, +∞]; action=set_nan | 2000 | 2000 | 8 | 8 | tak |
| 10 | reguła zakresu | households | rule=households ∈ [1, +∞]; action=set_nan | 2000 | 2000 | 0 | 0 | tak |
| 11 | reguła zakresu | median_income | rule=median_income ∈ [0.4999, 15.0001]; action=set_nan | 2000 | 2000 | 0 | 0 | tak |
| 12 | reguła zakresu | median_house_value | rule=median_house_value ∈ [14999, 500001]; action=set_nan | 2000 | 2000 | 5 | 5 | tak |
| 13 | reguła kategorii | ocean_proximity | rule=ocean_proximity ∈ {<1H OCEAN, INLAND, ISLAND, NEAR BAY, NEAR OCEAN}; action=set_nan | 2000 | 2000 | 4 | 4 | tak |
| 14 | obsługa braków | median_house_value | strategy=drop; removed_rows=5 | 2000 | 1995 | 5 | 0 | tak |
| 15 | obsługa braków | latitude | strategy=median; fill_value=37.41 | 1995 | 1995 | 6 | 6 | tak |
| 16 | obsługa braków | housing_median_age | strategy=median; fill_value=27.0 | 1995 | 1995 | 20 | 20 | tak |
| 17 | obsługa braków | total_bedrooms | strategy=median; fill_value=474.0 | 1995 | 1995 | 60 | 60 | tak |
| 18 | obsługa braków | population | strategy=median; fill_value=1226.0 | 1995 | 1995 | 8 | 8 | tak |
| 19 | obsługa braków | median_income | strategy=median; fill_value=3.5761 | 1995 | 1995 | 20 | 20 | tak |
| 20 | obsługa braków | ocean_proximity | strategy=mode; fill_value=<1H OCEAN | 1995 | 1995 | 34 | 34 | tak |
| 21 | outliery (IQR) | total_rooms, total_rooms_outlier_iqr | method=IQR; factor=1.5; action=flag; lower=-831.5; upper=5664.5 | 1995 | 1995 | 105 | 0 | tak |
| 22 | outliery (IQR) | total_bedrooms, total_bedrooms_outlier_iqr | method=IQR; factor=1.5; action=flag; lower=-181.75; upper=1192.25 | 1995 | 1995 | 92 | 0 | tak |
| 23 | outliery (IQR) | population, population_outlier_iqr | method=IQR; factor=1.5; action=flag; lower=-554.0; upper=3170.0 | 1995 | 1995 | 74 | 0 | tak |
| 24 | outliery (IQR) | households, households_outlier_iqr | method=IQR; factor=1.5; action=flag; lower=-125.5; upper=1038.5 | 1995 | 1995 | 84 | 0 | tak |
| 25 | outliery (IQR) | median_income, median_income_outlier_iqr | method=IQR; factor=1.5; action=flag; lower=-0.596; upper=8.0808 | 1995 | 1995 | 71 | 0 | tak |
| 26 | outliery (IQR) | median_house_value, median_house_value_outlier_iqr | method=IQR; factor=1.5; action=flag; lower=-27100.0; upper=380500.0 | 1995 | 1995 | 51 | 0 | tak |

## 5. Stan po czyszczeniu
### 5.1 Profil kolumn
| column | dtype | missing | missing_pct | unique | constant |
|---|---|---|---|---|---|
| longitude | float64 | 0 | 0 | 863 | nie |
| latitude | float64 | 0 | 0 | 824 | nie |
| housing_median_age | float64 | 0 | 0 | 52 | nie |
| total_rooms | float64 | 0 | 0 | 1579 | nie |
| total_bedrooms | float64 | 0 | 0 | 866 | nie |
| population | float64 | 0 | 0 | 1331 | nie |
| households | float64 | 0 | 0 | 794 | nie |
| median_income | float64 | 0 | 0 | 1931 | nie |
| median_house_value | float64 | 0 | 0 | 1399 | nie |
| ocean_proximity | str | 0 | 0 | 5 | nie |
| total_rooms_outlier_iqr | bool | 0 | 0 | 2 | nie |
| total_bedrooms_outlier_iqr | bool | 0 | 0 | 2 | nie |
| population_outlier_iqr | bool | 0 | 0 | 2 | nie |
| households_outlier_iqr | bool | 0 | 0 | 2 | nie |
| median_income_outlier_iqr | bool | 0 | 0 | 2 | nie |
| median_house_value_outlier_iqr | bool | 0 | 0 | 2 | nie |

### 5.2 Reguły jakości po czyszczeniu
| rule | column | violations | violations_pct | examples |
|---|---|---|---|---|
| longitude ∈ [-124.5, -114] | longitude | 0 | 0 |  |
| latitude ∈ [32.5, 42] | latitude | 0 | 0 |  |
| housing_median_age ∈ [1, 52] | housing_median_age | 0 | 0 |  |
| total_rooms ∈ [1, +∞] | total_rooms | 0 | 0 |  |
| total_bedrooms ∈ [0, +∞] | total_bedrooms | 0 | 0 |  |
| population ∈ [1, +∞] | population | 0 | 0 |  |
| households ∈ [1, +∞] | households | 0 | 0 |  |
| median_income ∈ [0.4999, 15.0001] | median_income | 0 | 0 |  |
| median_house_value ∈ [14999, 500001] | median_house_value | 0 | 0 |  |
| ocean_proximity ∈ {<1H OCEAN, INLAND, ISLAND, NEAR BAY, NEAR OCEAN} | ocean_proximity | 0 | 0 |  |

### 5.3 Obserwacje odstające (IQR, k = 1.5)
Outliery są **oznaczane** kolumnami `*_outlier_iqr`, a nie usuwane: w danych spisowych duże wartości (np. liczba pokoi w dużym obszarze) są zwykle prawdziwe. Błędy (wartości niemożliwe) obsługują reguły zakresu w kroku 4.

| column | granica dolna (po) | granica górna (po) | outliery przed | outliery po | % po |
|---|---|---|---|---|---|
| total_rooms | -831.5 | 5 664.5 | 107 | 105 | 5.26 |
| total_bedrooms | -181.8 | 1 192.2 | 83 | 92 | 4.61 |
| population | -554 | 3 170 | 75 | 74 | 3.71 |
| households | -125.5 | 1 038.5 | 88 | 84 | 4.21 |
| median_income | -0.596 | 8.081 | 69 | 71 | 3.56 |
| median_house_value | -27 100 | 380 500 | 56 | 51 | 2.56 |

## 6. Statystyki opisowe kolumn liczbowych
| index | mean (przed) | mean (po) | std (przed) | std (po) | min (przed) | min (po) | 50% (przed) | 50% (po) | max (przed) | max (po) |
|---|---|---|---|---|---|---|---|---|---|---|
| longitude | -119.3 | -119.3 | 2.807 | 2.81 | -124.3 | -124.3 | -119.3 | -119.3 | -114.4 | -114.4 |
| latitude | 37.17 | 37.29 | 3.401 | 2.729 | 0 | 32.6 | 37.37 | 37.41 | 41.9 | 41.9 |
| housing_median_age | — | 26.69 | — | 15.03 | — | 1 | — | 27 | — | 52 |
| total_rooms | 2 852.1 | 2 856.1 | 3 933.7 | 3 959.7 | 428 | 428 | 2 304 | 2 304 | 76 575 | 76 575 |
| total_bedrooms | 552.9 | 550.6 | 327.3 | 323.3 | 88 | 88 | 474 | 474 | 2 699 | 2 699 |
| population | 1 418.5 | 1 422.6 | 839.1 | 835.5 | -5 | 196 | 1 224 | 1 226 | 7 602 | 7 602 |
| households | 491.2 | 491.3 | 258.7 | 259.2 | 72 | 72 | 441 | 442 | 2 185 | 2 185 |
| median_income | 3.965 | 3.965 | 1.902 | 1.899 | 0.7348 | 0.7348 | 3.577 | 3.576 | 15 | 15 |
| median_house_value | 206 902.4 | 182 895.8 | 494 221.4 | 82 519.1 | 15 000 | 15 000 | 171 800 | 171 700 | 9 999 999 | 500 000 |

## 7. Ostrzeżenia
- reguły jakości: pominięto — kolumny nieobecne w danych: Longitude, Latitude, HouseAge, MedInc, AveRooms, AveBedrms, Population, AveOccup, MedHouseVal
- strategia braków: pominięto — kolumny nieobecne w danych: MedHouseVal
- outliery: pominięto — kolumny nieobecne w danych: MedInc, AveRooms, AveBedrms, Population, AveOccup, MedHouseVal
