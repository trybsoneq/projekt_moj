# Etap 5 – wielopoziomowe podpowiedzi i poprawka nawigacji

## System podpowiedzi

Każde zadanie może mieć maksymalnie trzy poziomy podpowiedzi:
1. pierwsza wskazówka – delikatny trop,
2. druga wskazówka – bardziej konkretna pomoc,
3. trzecia wskazówka – najbardziej konkretna pomoc.

Administrator ustawia treść i koszt punktowy każdego poziomu w formularzu tworzenia lub edycji zadania. Koszt może wynosić 0, czyli wskazówka jest bezpłatna.

### Zasady dla gracza
- Podpowiedzi odblokowuje się po kolei.
- Treść zablokowanej podpowiedzi nie jest wysyłana do przeglądarki.
- Koszt jest odejmowany od punktów w chwili odblokowania.
- Saldo użytkownika nie może spaść poniżej zera.
- Każdy poziom można opłacić tylko raz na użytkownika.
- Ponowne kliknięcie odblokowanej wskazówki nie odejmuje punktów ponownie.
- Jeśli administrator zmieni lub wyłączy wskazówkę, wcześniej odblokowany gracz zachowuje zakupioną treść w historii odblokowania.

### Kompatybilność ze starymi zadaniami
Dotychczasowe pole `Challenge.hint` nie jest usuwane. Migracja przenosi jego treść do poziomu 1 z kosztem 0 punktów, o ile taki poziom nie został już utworzony. Migracja jest idempotentna.

## Poprawka paska nawigacji
- Na desktopie logo jest w osobnym wierszu nad menu.
- Pozycje menu są układane przez Flexbox i zawijają się do kolejnego wiersza zamiast nachodzić na siebie.
- Na ekranach do 980 px pozostaje dotychczasowe mobilne menu ZeroFour.
- Style znajdują się w `templates/zerofour/assets/css/custom.css` i są ładowane po oryginalnym `main.css`.

## Baza danych
Dodano tabele:
- `challenge_hints`: poziom, treść, koszt punktowy i aktywność wskazówki.
- `hint_unlocks`: użytkownik, odblokowana wskazówka, data, naliczony koszt i kopia treści, którą użytkownik odblokował.

Unikalne ograniczenia zabezpieczają przed utworzeniem kilku takich samych poziomów dla zadania i przed wielokrotnym odblokowaniem tej samej wskazówki przez jednego użytkownika.

## Aktualizacja istniejącej instalacji

W katalogu `CB_projekt`:

```powershell
python -m pip install -r requirements.txt
python migrate_hints.py
python -m uvicorn main:app --reload
```

Migracja uruchamia się również automatycznie przy imporcie `main.py`. Zatrzymaj Uvicorn przed podmianą plików i zachowaj istniejący `ctf_platform.db`.

## Testy

```powershell
python -m unittest -v test_auth.py test_docker_manager.py test_activity.py test_hints.py test_templates.py
```

Testy obejmują kolejność wskazówek, naliczanie kosztu tylko raz, ochronę przed ujemnym saldem, zachowanie kupionej treści po edycji przez administratora oraz kompilację strony zadania i nowej nawigacji.
