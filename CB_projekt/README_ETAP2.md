# Etap 2 – indywidualne środowiska Docker

## Funkcje

- Każdy użytkownik może uruchomić własną instancję zadania „Podatna wyszukiwarka” (SQL Injection).
- Każda instancja ma osobny kontener, wewnętrzną sieć Docker i losowo przydzielony port hosta.
- Jedna instancja danego zadania na użytkownika; maksymalnie dwa aktywne środowiska na użytkownika.
- Instancja wygasa po 30 minutach. Worker FastAPI sprawdza wygasające instancje co 30 sekund.
- Użytkownik może zatrzymać własny kontener wcześniej; administrator może zatrzymać dowolną instancję.
- Limity kontenera: 256 MB RAM, 0,5 CPU, 64 procesy, brak dodatkowych capabilities, `no-new-privileges`, read-only filesystem oraz tmpfs dla pliku bazy zadania.
- Dozwolone są wyłącznie szablony z allowlisty `SUPPORTED_TEMPLATES`. Dane z formularza nie mogą wybrać obrazu, polecenia ani montowania woluminu.

## Instalacja / aktualizacja

W katalogu `CB_projekt`:

```powershell
pip install -r requirements.txt
python migrate_roles.py
python migrate_docker.py
```

Migracje są idempotentne i zachowują dotychczasowych użytkowników, zadania, wyniki oraz punktację. Zadanie „Podatna wyszukiwarka” zostanie powiązane z szablonem `web_sqli`, a stary adres localhost zostanie wyczyszczony.

Jeśli konto administratora nie zostało jeszcze skonfigurowane po etapie 1, wykonaj `python create_admin.py`.

## Lokalnie (Docker Desktop)

Uruchom Docker Desktop i poczekaj na gotowość silnika. Ustaw sekret sesji i adresy:

```powershell
$env:CTF_SECRET_KEY = (python -c "import secrets; print(secrets.token_urlsafe(48))")
$env:CTF_DOCKER_BIND_HOST = "127.0.0.1"
$env:CTF_PUBLIC_HOST = "127.0.0.1"
uvicorn main:app --reload
```

Otwórz zadanie „Podatna wyszukiwarka” i kliknij „Uruchom środowisko (30 min)”. Pierwsze uruchomienie zbuduje obraz z lokalnego Dockerfile.

## Serwer zdalny

Ustaw `CTF_PUBLIC_HOST` na nazwę DNS lub publiczny adres hosta i `CTF_DOCKER_BIND_HOST=0.0.0.0`. Ogranicz dostęp do publikowanych portów na firewallu. Nie wystawiaj Docker API ani socketu Dockera do przeglądarki ani kontenerów zadań.

Na tym etapie adresy instancji działają przez HTTP na losowych portach. Do publicznego wdrożenia zalecany jest reverse proxy z HTTPS i odpowiednimi regułami sieciowymi.

## Testy

```powershell
python -m unittest -v test_auth.py test_docker_manager.py
```

Testy jednostkowe nie wymagają demona Docker. Rzeczywiste uruchomienie kontenera wymaga działającego Docker Desktop lub usługi Docker.

## Uwaga bezpieczeństwa

Zadanie SQL Injection jest celowo podatne i powinno być udostępniane wyłącznie w odizolowanym laboratorium. Kontenery nie montują katalogów hosta ani socketu Dockera, a ich sieć wewnętrzna nie ma routingu wychodzącego do Internetu.
