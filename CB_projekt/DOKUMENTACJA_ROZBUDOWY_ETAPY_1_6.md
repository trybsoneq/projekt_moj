# Dokumentacja rozbudowy platformy CTF – etapy 1–6

Ten dokument opisuje rolę plików dodanych lub zmienionych w ramach rozbudowy platformy. Przy przenoszeniu do oryginalnego repozytorium zawartość katalogu `CB_projekt/` należy skopiować bezpośrednio do katalogu głównego repozytorium — bez tworzenia dodatkowego podfolderu `CB_projekt`.

## Główna aplikacja i baza

| Plik | Co zmienia w projekcie |
|---|---|
| `main.py` | Główna aplikacja FastAPI. Rejestruje nowe routery, uruchamia migracje oraz obsługuje logowanie, zadania, zgłaszanie flag i komunikaty o nagrodach. |
| `models.py` | Rozszerza modele SQLAlchemy o role, instancje Docker, historię prób, podpowiedzi, XP, serie aktywności i osiągnięcia. |
| `database.py` | Ujednolica ścieżkę SQLite. Aplikacja i migracje korzystają z tej samej bazy; można ją wskazać przez `CTF_DATABASE_PATH`. |
| `requirements.txt` | Dodaje biblioteki potrzebne do FastAPI, ORM, sesji, formularzy i obsługi Docker SDK. |
| `seed.py` | Inicjalizuje przykładowe zadania, ale nie tworzy już domyślnego konta `admin/admin`. |
| `.env.example` | Przykładowa konfiguracja sekretu sesji, limitów Docker i limitu prób flag. |

## Etap 1 – logowanie i role

| Plik | Co zmienia |
|---|---|
| `security.py` | Podpisywane sesje, pobieranie zalogowanego użytkownika i kontrola ról `user/admin`. |
| `create_admin.py` | Bezpieczne tworzenie konta administratora z hasłem podanym przez operatora. |
| `migrate_roles.py` | Idempotentnie dodaje role do istniejącej bazy, bez usuwania użytkowników. |

## Etap 2 – indywidualne środowiska Docker

| Plik | Co zmienia |
|---|---|
| `docker_manager.py` | Buduje obrazy, uruchamia i zatrzymuje instancje, stosuje limity zasobów, izoluje sieci i usuwa wygasłe kontenery. Zawiera również odczyt metryk i restart instancji. |
| `instance_routes.py` | Endpointy uruchamiania i zatrzymywania własnego laboratorium przez użytkownika. |
| `migrate_docker.py` | Dodaje pola bazy potrzebne do wyboru szablonu i zapisywania identyfikatorów kontenerów oraz sieci. |
| `docker_challanges/web_sqli/Dockerfile` | Buduje obraz zadania SQL Injection z nieuprzywilejowanym użytkownikiem i bazą w katalogu tymczasowym. |
| `docker_challanges/web_sqli/app.py` | Uruchamia podatny CyberShop w kontenerze; lokalizacja bazy SQLite jest konfigurowalna. Podatność SQL Injection jest celowa i służy ćwiczeniu. |
| `docker_challanges/ingress_proxy/Dockerfile` | Obraz zaufanej bramy Nginx udostępniającej port laboratorium. |
| `docker_challanges/ingress_proxy/nginx.conf` | Przekazuje ruch do stałego upstreamu laboratorium i kieruje pliki tymczasowe Nginx do zapisywalnego `/tmp`. |

## Etap 3 – monitoring infrastruktury

| Plik | Co zmienia |
|---|---|
| `infrastructure_routes.py` | Panel administracyjny monitoringu oraz chronione akcje restartu i zatrzymania instancji. |
| `templates/zerofour/infrastructure.html` | Tabela instancji, statusy Docker, porty, termin wygaśnięcia oraz użycie CPU/RAM. |
| `templates/zerofour/admin.html` | Odnośniki do monitoringu infrastruktury i analityki aktywności. |

## Etap 4 – historia aktywności i próby flag

| Plik | Co zmienia |
|---|---|
| `activity_service.py` | Sprawdza flagę, zapisuje wynik i czas próby, ogranicza liczbę zgłoszeń i przyznaje punkty. Nie zapisuje tekstu przesłanej flagi. |
| `activity_routes.py` | Prywatny profil użytkownika oraz zbiorcza analityka aktywności dla administratora. |
| `migrate_activity.py` | Tworzy tabelę historii prób i zabezpiecza unikalność rozwiązania zadania przez użytkownika. |
| `templates/zerofour/profile.html` | Profil z postępem, skutecznością i historią prób. |
| `templates/zerofour/admin_activity.html` | Statystyki prób, skuteczności zadań i aktywności użytkowników. |

## Etap 5 – wielopoziomowe podpowiedzi i pasek nawigacji

| Plik | Co zmienia |
|---|---|
| `hint_service.py` | Trzy poziomy wskazówek, kolejność odblokowania, koszty punktowe i zapis już odblokowanej treści. |
| `hint_routes.py` | Chroniony endpoint odblokowania podpowiedzi przez zalogowanego gracza. |
| `migrate_hints.py` | Tworzy tabele podpowiedzi i odblokowań; przenosi stare pole `Challenge.hint` do bezpłatnego poziomu 1. Uruchamia wymagane wcześniejsze migracje. |
| `templates/zerofour/challenge.html` | Karty wskazówek, ceny, informacja o odblokowaniu i licznik prób flag. |
| `templates/zerofour/assets/css/custom.css` | Naprawia desktopowy pasek nawigacji: flexbox zawija linki do kolejnych wierszy, zamiast nakładać je na siebie. |
| `templates/zerofour/base.html` | Wspólna nawigacja do profilu, paneli administratora oraz ładowanie dodatkowego CSS. |

## Etap 6 – XP, odznaki i serie

| Plik | Co zmienia |
|---|---|
| `achievement_service.py` | XP za rozwiązania, poziomy doświadczenia, serie dni i automatyczne przyznawanie odznak. |
| `migrate_achievements.py` | Dodaje kolumny XP/serii, katalog odznak i odtwarza osiągnięcia z dotychczasowych rozwiązań. |
| `templates/zerofour/scoreboard.html` | Dodaje poziom i XP do rankingu obok punktów. |
| `templates/zerofour/profile.html` | Pokazuje poziom, pasek XP, aktualną/najdłuższą serię i kolekcję odznak. |

## Testy i CI

| Plik | Co sprawdza |
|---|---|
| `test_auth.py` | Logowanie, sesje i role. |
| `test_docker_manager.py` | Cykl życia instancji, metryki CPU/RAM i restart z atrapą Docker SDK. |
| `test_activity.py` | Historię prób, punktację i limit zgłoszeń flag. |
| `test_hints.py` | Kolejność podpowiedzi i jednokrotne odliczanie punktów. |
| `test_migrate_hints.py` | Kolejność wcześniejszych migracji. |
| `test_achievements.py` | XP, poziomy, serie i odznaki. |
| `test_templates.py` | Kompilację szablonów Jinja2 i sprawdzenie nowego CSS. |
| `.github/workflows/python-tests.yml` | Automatyczną kompilację modułów Python i uruchamianie testów w GitHub Actions. |

## Dokumentacja etapów

- `README_ETAP1.md` – logowanie i role.
- `README_ETAP2.md` – laboratoria Docker.
- `README_ETAP3.md` – monitoring infrastruktury.
- `README_ETAP4.md` – historia aktywności.
- `README_ETAP5.md` – podpowiedzi i nawigacja.
- `README_ETAP6.md` – XP, poziomy i osiągnięcia.

## Ważne przy przenoszeniu

1. Kopiuj zawartość `CB_projekt/` do katalogu głównego oryginalnego repozytorium.
2. Nie kopiuj lokalnych baz `ctf_platform.db`, `products.db`, plików `.env`, `__pycache__` ani środowiska wirtualnego.
3. Zachowaj oryginalne grafiki, fonty i biblioteki JS motywu ZeroFour; nie trzeba ich nadpisywać.
4. Przed pierwszym uruchomieniem wykonaj `python migrate_achievements.py`. Skrypt uruchamia wcześniejsze migracje automatycznie.
5. SQL Injection w CyberShop jest celową podatnością ćwiczeniową i powinien być dostępny wyłącznie przez odizolowane laboratorium Docker.
