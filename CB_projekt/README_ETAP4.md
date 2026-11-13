# Etap 4 – historia aktywności i system prób flag

## Funkcje dla użytkownika

- Prywatny profil pod adresem `/profile`.
- Liczba rozwiązanych zadań i postęp względem wszystkich zadań.
- Łączna liczba prób flag, liczba poprawnych i błędnych prób oraz skuteczność.
- Zestawienie rozwiązanych zadań według kategorii.
- Historia do 50 ostatnich prób wraz z nazwą zadania, datą i wynikiem.
- Na stronie zadania widoczna jest liczba zapisanych prób tego użytkownika.

## Funkcje dla administratora

- Panel `/admin/activity` dostępny wyłącznie dla roli administratora.
- Łączna liczba prób poprawnych i błędnych.
- Liczba użytkowników, którzy przesłali co najmniej jedną flagę.
- Skuteczność każdego zadania: poprawne zgłoszenia / wszystkie zapisane zgłoszenia.
- Liczba rozwiązujących dane zadanie.
- Zestawienie aktywności do 25 użytkowników.

## Ochrona przesyłania flag

- Każda zalogowana próba jest zapisywana jako wynik `is_correct` oraz czas `submitted_at`.
- Treść wpisanej flagi nigdy nie jest zapisywana w bazie ani w logach aplikacji.
- Domyślny limit to 10 prób na użytkownika w ruchomym oknie 60 sekund (wspólny dla zadań).
- Limit można zmienić przez zmienną środowiskową `CTF_FLAG_ATTEMPTS_PER_MINUTE`.
- Porównanie flag wykorzystuje porównanie stałoczasowe na bajtach UTF-8.
- Punkty i rekord rozwiązania są zapisywane razem z poprawną próbą w jednej transakcji.
- Dodano unikalność pary użytkownik–zadanie w tabeli `solves`, aby równoległe zgłoszenia nie przyznały punktów dwa razy. Migracja nie usuwa danych i pomija indeks unikalny, jeśli wykryje wcześniejsze duplikaty.

## Baza danych

Dodano tabelę `submissions`:
- `id`
- `user_id`
- `challenge_id`
- `is_correct`
- `submitted_at`

Nie zapisujemy wartości pola formularza z flagą.

## Aktualizacja istniejącej instalacji

W katalogu `CB_projekt`:

```powershell
python -m pip install -r requirements.txt
python migrate_activity.py
python -m uvicorn main:app --reload
```

Migracja jest idempotentna i nie usuwa użytkowników, zadań ani wyników. Aplikacja uruchamia ją również automatycznie przy imporcie `main.py`. Jeżeli konto/serwer jest już uruchomione, zatrzymaj Uvicorn przed aktualizacją kodu i uruchom go ponownie.

Opcjonalna konfiguracja limitu w bieżącym oknie PowerShell:

```powershell
$env:CTF_FLAG_ATTEMPTS_PER_MINUTE = "10"
```

## Adresy

- Profil użytkownika: `http://127.0.0.1:8000/profile`
- Analityka administratora: `http://127.0.0.1:8000/admin/activity`

Linki są widoczne w nawigacji po zalogowaniu. Analityka administratora wymaga roli `admin`.

## Testy

```powershell
python -m unittest -v test_auth.py test_docker_manager.py test_activity.py test_templates.py
```

Testy sprawdzają zapisywanie wyników, przyznawanie punktów, brak podwójnego punktowania, limit prób oraz kompilację nowych szablonów. GitHub Actions uruchamia te testy i kompilację modułów Python dla pushy oraz pull requestów.
