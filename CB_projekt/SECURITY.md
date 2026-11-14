# Security policy – CyberSim

## Bezpieczna konfiguracja

- Nie commituj plików `.env`, baz danych SQLite, haseł, tokenów ani kluczy.
- Ustaw unikatowy `CTF_SECRET_KEY` i przechowuj go poza repozytorium.
- W środowisku produkcyjnym ustaw `CTF_ENV=production` i `CTF_COOKIE_SECURE=1`; aplikacja wymaga HTTPS.
- Utrzymuj `CTF_DOCKER_BIND_HOST=127.0.0.1`. Nie wystawiaj portów laboratoriów do Internetu bez świadomej konfiguracji, reverse proxy i reguł firewalla.
- Nie udostępniaj niezaufanym użytkownikom dostępu do Docker Engine/socket.
- Używaj jednego procesu aplikacji, dopóki limiter logowania i scheduler nie zostaną przeniesione do współdzielonej infrastruktury.

## Zabezpieczenia aplikacji

- Sesje są podpisywane, mają maksymalnie 8 godzin i używają HttpOnly oraz SameSite=Lax.
- Żądania modyfikujące stan wymagają podpisanego tokenu CSRF w cookie oraz formularzu lub nagłówku.
- Odpowiedzi otrzymują CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy i Permissions-Policy.
- Logowanie i rejestracja mają limiter prób per adres IP; przesyłanie flag ma niezależny limit per konto.
- Role są pobierane z bazy przy każdym żądaniu, a operacje administracyjne wymagają roli administratora.
- Laboratoria Docker korzystają z allowlisty obrazów, prywatnej sieci, limitów zasobów, read-only filesystem, ograniczonych capabilities i no-new-privileges.

## Zgłaszanie problemów

Nie umieszczaj w zgłoszeniu publicznym aktywnych flag, haseł, kluczy sesji ani danych użytkowników. Opisz ścieżkę odtworzenia, wpływ i logi po usunięciu sekretów. Przed wdrożeniem na publiczny serwer wykonaj audyt konfiguracji hosta, Docker Engine, firewalla i reverse proxy — aplikacja nie zastępuje zabezpieczenia systemu operacyjnego.
