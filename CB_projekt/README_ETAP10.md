# Etap 10 – bezpieczeństwo, stabilność i finalizacja

## Zabezpieczenia aplikacji

- Wszystkie żądania zmieniające stan (POST/PUT/PATCH/DELETE) wymagają podpisanego tokenu CSRF w cookie i w formularzu lub nagłówku `X-CSRF-Token`.
- Token CSRF jest dostarczany przez bazowy szablon do formularzy samej aplikacji. Zewnętrzny formularz kontaktowy nie otrzymuje tokenu.
- Sesja pozostaje podpisana przez `itsdangerous`, ma maksymalny czas życia 8 godzin i korzysta z ciasteczka HttpOnly, SameSite=Lax.
- W produkcji wymagany jest własny `CTF_SECRET_KEY` oraz `CTF_COOKIE_SECURE=1` (HTTPS).
- Dodano nagłówki: CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy i Permissions-Policy.
- Logowanie i rejestracja mają limit prób według adresu IP. Limit jest przechowywany w pamięci procesu; przy wielu workerach należy skonfigurować wspólny limiter na reverse proxy lub współdzielony magazyn.
- Rejestracja sprawdza po stronie serwera nazwę użytkownika, długość hasła, limit 72 bajtów UTF-8 dla bcrypt i zgodność potwierdzenia hasła.
- Tworzenie/edycja zadania waliduje tytuł, opis, kategorię, punkty, flagę i link zewnętrzny.
- Wylogowanie zmieniono z GET na POST i objęto ochroną CSRF.
- Nie można usuwać zadań, które mają historię prób, rozwiązań lub udziału w turniejach.

## Docker i laboratoria

- Port proxy jest domyślnie publikowany wyłącznie na loopback (`127.0.0.1`).
- Zdalne wystawienie portów wymaga jawnego `CTF_ALLOW_REMOTE_DOCKER_BIND=1` i odpowiedniego firewalla.
- `CTF_DOCKER_BIND_HOST` musi być adresem IP, a `CTF_PUBLIC_HOST` jest walidowany przed użyciem w linku.
- Walidowane są granice TTL, liczby aktywnych kontenerów i interwału sprzątania.
- Kontenery mają jawny limit pamięci i swap, CPU, PID, zrzucenie capabilities, no-new-privileges, read-only filesystem i wydzielony tmpfs.
- Laboratorium pozostaje w sieci internal; do hosta wystawiany jest tylko zaufany proxy.
- Panel infrastruktury pobiera użytkownika i zadanie eager-loadingiem, ograniczając dodatkowe zapytania N+1.

## Baza danych i wydajność

- SQLite wymusza klucze obce i ustawia timeout oczekiwania na blokadę.
- `migrate_stage10.py` tworzy siedem indeksów dla rankingu, rozwiązań, prób, turniejów, członków drużyn i historii instancji.
- Ostatnie próby użytkownika są pobierane razem z zadaniami, a panel administratora ładuje podpowiedzi w jednym zapytaniu.
- Scoreboard ma limit 1000 rekordów.
- Dane platformy i pliki `__pycache__` zostały usunięte z repozytorium. Lokalny plik bazy pozostaje u użytkownika; pliki `*.db` są ignorowane przez Git.

## Obsługa błędów i interfejs

- Nieobsłużone wyjątki są logowane po stronie serwera, a klient otrzymuje bezpieczny komunikat bez szczegółów wewnętrznych.
- Formularze są walidowane po stronie serwera; ograniczenia HTML służą wyłącznie jako dodatkowa pomoc.
- Dodano poprawki responsywności tabel, formularzy, obrazów i kart na małych ekranach.
- GitHub Actions kompiluje moduły, uruchamia cały zestaw testów oraz audyt zależności `pip-audit`.

## Nowe i zmienione pliki

- `csrf_middleware.py` – ochrona CSRF i nagłówki bezpieczeństwa.
- `migrate_stage10.py` – indeksy SQLite etapu 10.
- `test_security_hardening.py` – testy CSRF, rate limitera, reguł rejestracji i konfiguracji SQLite.
- Zmodyfikowane: `security.py`, `main.py`, `database.py`, `docker_manager.py`, `activity_routes.py`, `create_admin.py`, szablony bazowe, CSS i workflow CI.

## Aktualizacja lokalnej instalacji

**Zachowaj dotychczasowy plik `ctf_platform.db`.** Nowa gałąź nie zawiera już bazy danych w Git. Skopiuj ją ze swojego lokalnego folderu etapu 9 do `CB_projekt` etapu 10.

W katalogu `CB_projekt` wykonaj:

```powershell
python -m pip install -r requirements.txt
python migrate_stage10.py
python -m uvicorn main:app --reload
```

Migracja jest też wykonywana automatycznie przy uruchomieniu aplikacji. Można ją bezpiecznie uruchamiać ponownie.

## Konfiguracja produkcyjna

Wygeneruj sekret i ustaw go w środowisku:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

W produkcji ustaw co najmniej:

```ini
CTF_ENV=production
CTF_SECRET_KEY=<wygenerowany-losowy-sekret>
CTF_COOKIE_SECURE=1
CTF_DOCKER_BIND_HOST=127.0.0.1
CTF_ALLOW_REMOTE_DOCKER_BIND=0
```

Aplikację udostępniaj przez HTTPS. Wbudowany limiter logowania i worker zadań cyklicznych są lokalne dla procesu — do uruchomienia wielu workerów potrzebny będzie współdzielony limiter i jeden scheduler/koordynator.

## Testy

```powershell
python -m unittest -v test_auth.py test_docker_manager.py test_activity.py test_hints.py test_migrate_hints.py test_achievements.py test_tournaments.py test_notifications.py test_analytics.py test_security_hardening.py test_templates.py
```
