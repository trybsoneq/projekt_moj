# CB_projekt – etap 1: uwierzytelnianie i role

## Zakres

- Dodano kolumnę `users.role` (`user` / `admin`).
- Sesja jest podpisywana przez `itsdangerous`; identyfikator użytkownika nie może być zmieniony przez edycję ciasteczka.
- Rola jest pobierana z bazy danych przy każdym żądaniu.
- Wszystkie endpointy administracyjne wymagają roli administratora.
- Usunięto automatyczne tworzenie znanego konta `admin/admin`.
- Dodano migrację bazy, interaktywny skrypt tworzenia administratora i testy autoryzacji.

## Aktualizacja istniejącej instalacji

W katalogu `CB_projekt`:

```bash
pip install -r requirements.txt
python migrate_roles.py
python create_admin.py
```

Migracja zachowuje użytkowników, zadania i wyniki. Dotychczasowy użytkownik o nazwie `admin` otrzyma rolę administratora. Uruchomienie `create_admin.py` pozwala ustawić mu nowe, silne hasło albo utworzyć inne konto administratora.

## Sekret sesji

W PowerShell wygeneruj sekret i ustaw go w bieżącym terminalu:

```powershell
$env:CTF_SECRET_KEY = (python -c "import secrets; print(secrets.token_urlsafe(48))")
```

Na serwerze produkcyjnym ustaw także:

```powershell
$env:CTF_ENV = "production"
$env:CTF_COOKIE_SECURE = "1"
```

Przy `CTF_COOKIE_SECURE=1` aplikacja musi być dostępna przez HTTPS. Nie umieszczaj prawdziwego sekretu w repozytorium.

## Uruchomienie i testy

```bash
uvicorn main:app --reload
python -m unittest -v test_auth.py
```

Użytkownicy zalogowani przed aktualizacją będą musieli zalogować się ponownie, ponieważ nazwa i format ciasteczka sesji uległy zmianie.


## Ważne: wspólna ścieżka bazy danych

Aplikacja i migracje używają teraz domyślnie pliku `ctf_platform.db` znajdującego się obok `database.py`. Dzięki temu uruchomienie terminala z innego katalogu nie tworzy przypadkiem drugiej, pustej bazy.

Przy starcie aplikacja automatycznie wykonuje idempotentną migrację ról. W logu powinny pojawić się ścieżka bazy i komunikat `Kolumna users.role: OK`.

Jeżeli bazę celowo przechowujesz w innym miejscu, ustaw zmienną `CTF_DATABASE_PATH` na pełną ścieżkę do istniejącego pliku SQLite przed uruchomieniem aplikacji oraz skryptów migracyjnych. Nie usuwaj ani nie nadpisuj dotychczasowego pliku bazy.
