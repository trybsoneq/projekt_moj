# Etap 3 – panel infrastruktury administratora

## Funkcje

- Nowa strona administratora pod adresem `/admin/infrastructure`.
- Zestawienie ostatnich 100 instancji: użytkownik, zadanie, status w bazie, termin wygaśnięcia i opublikowany port proxy.
- Rzeczywisty stan kontenera laboratorium i kontenera Nginx pobierany z Docker Engine.
- Odczyt bieżącego zużycia CPU i RAM kontenera laboratorium.
- Podsumowanie liczby instancji, aktywnych rekordów, działających laboratoriów i błędów.
- Automatyczne odświeżanie dashboardu co 20 sekund.
- Administrator może zrestartować istniejące kontenery instancji lub zatrzymać i usunąć środowisko.
- Operacje administracyjne są chronione przez zależność `require_admin`.
- Historia instancji pozostaje w bazie po zatrzymaniu kontenerów.

## Uruchomienie

Po pobraniu aktualnej gałęzi, z katalogu `CB_projekt`:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

Nie jest potrzebna nowa migracja bazy danych. Po zalogowaniu na konto administratora otwórz panel administratora i kliknij „Otwórz monitoring infrastruktury”, albo przejdź bezpośrednio na `/admin/infrastructure`.

## Interpretacja danych

- **Status w bazie** opisuje ostatni zapisany stan lifecycle instancji.
- **Status laboratorium / proxy** jest odczytywany bezpośrednio z Docker Engine i może ujawnić rozjazd z rekordem bazy.
- **CPU** jest szacowane z delty dwóch próbek Docker stats i może być puste, gdy Docker nie udostępnia jeszcze poprawnej próbki.
- **RAM** pokazuje użycie pamięci kontenera z uwzględnieniem cache plików nieaktywnych, jeśli takie pole zwróci Docker.
- Wartości dotyczą kontenera laboratorium; stan proxy jest pokazany oddzielnie.

## Restart i zatrzymanie

- **Restart** zatrzymuje i ponownie uruchamia istniejący kontener laboratorium oraz proxy. Zachowuje ID instancji i istniejący port hosta, o ile Docker odtworzy mapowanie.
- **Zatrzymaj** usuwa kontenery i sieci danej instancji; rekord historyczny pozostaje w bazie.
- Instancje już zatrzymane lub wygasłe nie mogą być restartowane z dashboardu. Nowe środowisko należy uruchomić ze strony zadania.

## Testy

```powershell
python -m unittest -v test_auth.py test_docker_manager.py
```

Testy jednostkowe obliczeń CPU i RAM nie wymagają uruchomionego Docker Engine. Odczyt rzeczywistych statystyk, restart i zatrzymanie należy sprawdzić przy działającym Docker Desktop.
