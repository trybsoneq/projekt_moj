# Etap 2 – indywidualne środowiska Docker

## Funkcje

- Każdy użytkownik może uruchomić własną instancję zadania „Podatna wyszukiwarka” (SQL Injection).
- Każde laboratorium ma własny kontener i dedykowaną sieć Docker typu `internal`.
- Dostęp z przeglądarki zapewnia osobny, zaufany kontener Nginx (ingress proxy). Port hosta jest publikowany przez proxy w osobnej sieci bridge.
- Kontener z celowo podatną aplikacją pozostaje wyłącznie w sieci wewnętrznej i nie ma domyślnej trasy do Internetu.
- Proxy ma stały upstream `http://challenge:7000`; użytkownik nie może zmienić adresu docelowego.
- Jedna instancja danego zadania na użytkownika; maksymalnie dwa aktywne środowiska na użytkownika.
- Instancja wygasa po 30 minutach. Worker FastAPI sprawdza wygasające instancje co 30 sekund.
- Użytkownik może zatrzymać własny kontener wcześniej; administrator może zatrzymać dowolną instancję.
- Limity laboratorium: 256 MB RAM, 0,5 CPU i 64 procesy. Limity proxy: 64 MB RAM, 0,25 CPU i 32 procesy.
- Oba kontenery działają bez dodatkowych capabilities, z `no-new-privileges` i read-only root filesystem.
- Dozwolone są wyłącznie szablony z allowlisty `SUPPORTED_TEMPLATES`. Dane z formularza nie mogą wybrać obrazu, polecenia, montowania woluminu ani celu proxy.

## Dlaczego proxy jest osobnym kontenerem?

Docker Engine nie publikuje portów kontenera, który jest podłączony wyłącznie do sieci `internal` bez bramy domyślnej. Samo laboratorium nie może więc jednocześnie pozostać wyłącznie w sieci wewnętrznej i otrzymać mapowania portu hosta.

Rozwiązanie rozdziela role:
- podatne laboratorium jest podłączone tylko do prywatnej sieci `internal`;
- zaufany Nginx jest podłączony do sieci ingress (bridge) oraz prywatnej sieci laboratorium;
- host publikuje port Nginx, który przekazuje żądania wyłącznie do stałej nazwy `challenge` w prywatnej sieci.

W konsekwencji kontener z zadaniem nie otrzymuje zewnętrznej karty sieciowej. Kontener proxy ma połączenie z siecią bridge, dlatego musi pozostać zaufanym, niezmiennym elementem infrastruktury — nie uruchamiamy w nim kodu ani konfiguracji pochodzącej od użytkowników.

## Instalacja / aktualizacja

W katalogu `CB_projekt`:

```powershell
python -m pip install -r requirements.txt
python migrate_roles.py
python migrate_docker.py
```

Migracje są idempotentne i zachowują dotychczasowych użytkowników, zadania, wyniki oraz punktację. Migracja Docker dodaje również pola identyfikujące kontener proxy i sieć ingress. Zadanie „Podatna wyszukiwarka” zostanie powiązane z szablonem `web_sqli`.

Jeśli konto administratora nie zostało jeszcze skonfigurowane po etapie 1, wykonaj `python create_admin.py`.

## Lokalnie (Docker Desktop)

Uruchom Docker Desktop i poczekaj na gotowość silnika. Ustaw sekret sesji i adresy:

```powershell
$env:CTF_SECRET_KEY = (python -c "import secrets; print(secrets.token_urlsafe(48))")
$env:CTF_DOCKER_BIND_HOST = "127.0.0.1"
$env:CTF_PUBLIC_HOST = "127.0.0.1"
python -m uvicorn main:app --reload
```

Otwórz zadanie „Podatna wyszukiwarka” i kliknij „Uruchom środowisko (30 min)”. Przy pierwszym uruchomieniu Docker zbuduje obraz laboratorium i obraz proxy Nginx.

## Serwer zdalny

Ustaw `CTF_PUBLIC_HOST` na nazwę DNS lub publiczny adres hosta i `CTF_DOCKER_BIND_HOST=0.0.0.0`. Ogranicz dostęp do publikowanych portów na firewallu. Nie wystawiaj Docker API ani socketu Dockera do przeglądarki ani kontenerów zadań.

Na tym etapie adresy instancji działają przez HTTP na losowych portach. Do publicznego wdrożenia zalecany jest centralny reverse proxy z HTTPS i odpowiednimi regułami sieciowymi.

## Testy

```powershell
python -m unittest -v test_auth.py test_docker_manager.py
```

Testy jednostkowe nie wymagają demona Docker. Rzeczywiste budowanie obrazów i uruchomienie kontenerów wymaga działającego Docker Desktop lub usługi Docker.

## Uwaga bezpieczeństwa

Zadanie SQL Injection jest celowo podatne i powinno być udostępniane wyłącznie w odizolowanym laboratorium. Kontener laboratorium nie ma montowań hosta, socketu Dockera ani zewnętrznej sieci. Zaufany proxy ma dostęp do ingress i do sieci prywatnej laboratorium, ale obsługuje wyłącznie statyczny upstream.


## Wspólna baza i automatyczne migracje

Aplikacja oraz skrypty migracyjne korzystają z tej samej, bezwzględnej ścieżki `CTF_DATABASE_PATH` (domyślnie: plik `ctf_platform.db` obok `database.py`). Przy imporcie aplikacji automatycznie i idempotentnie uruchamiane są migracje ról oraz instancji Docker. Możesz nadal uruchamiać `python migrate_roles.py` i `python migrate_docker.py` ręcznie.

Po uruchomieniu serwera sprawdź w terminalu komunikat `Używana baza SQLite: ...` i `Kolumna users.role: OK`. Jeżeli masz istniejącą bazę poza katalogiem projektu, przed uruchomieniem ustaw `CTF_DATABASE_PATH` na jej pełną ścieżkę. Nie kasuj starego pliku bazy.


## Diagnostyka uruchamiania środowiska

Pierwsze uruchomienie może potrwać dłużej, ponieważ Docker pobiera obrazy bazowe i buduje dwa obrazy. Klient Docker ma timeout 180 sekund. W terminalu Uvicorn pojawiają się logi kolejnych etapów:
- `checking/building challenge image`
- `checking/building ingress proxy image`
- `private challenge container is running`
- `starting ingress proxy`
- `proxy published at ...`

Jeżeli przeglądarka nadal czeka, sprawdź terminal Uvicorn. Nie klikaj przycisku wielokrotnie. W drugim terminalu sprawdź:
```powershell
docker ps -a --filter "name=ctf-"
docker network ls --filter "name=ctf-"
```
Logi kontenera proxy:
```powershell
$proxy = docker ps -aq --filter "name=ctf-proxy-" | Select-Object -First 1
if ($proxy) { docker logs $proxy }
```


### Nginx na read-only filesystem

Konfiguracja ingress proxy kieruje wszystkie katalogi tymczasowe Nginx (`client_body`, `proxy`, `fastcgi`, `uwsgi`, `scgi`) do katalogów pod `/tmp`. Kontener proxy ma zapisywalny `tmpfs` pod `/tmp`, natomiast jego główny system plików pozostaje tylko do odczytu. Dzięki temu Nginx nie próbuje tworzyć katalogów w `/var/cache/nginx`.
