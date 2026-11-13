# Etap 6 – osiągnięcia, odznaki, XP i serie aktywności

## Co dodaje ten etap?

### Doświadczenie i poziomy
- Każde nowe, poprawne rozwiązanie daje 10 XP.
- XP jest osobne od punktów rankingowych. Punkty za zadania i kary za podpowiedzi pozostają bez zmian.
- Każde 100 XP oznacza kolejny poziom (poziom 1 zaczyna się od 0 XP).
- Odznaki przyznają dodatkowe XP zgodnie z katalogiem osiągnięć.

### Odznaki
- **Pierwszy krok** – pierwsze rozwiązane zadanie.
- **First Blood** – pierwsze rozwiązanie konkretnego zadania; może zostać przyznane różnym graczom dla różnych zadań, ale tylko jednej osobie dla danego zadania.
- **Początkujący łowca** – 5 rozwiązanych zadań.
- **Ekspert CTF** – 10 rozwiązanych zadań.
- **Trzy dni z rzędu** – rozwiązanie co najmniej jednego zadania w 3 kolejnych dniach.
- **Tydzień cybertreningu** – rozwiązanie co najmniej jednego zadania w 7 kolejnych dniach.
- **Wszechstronny badacz** – rozwiązania z 3 różnych kategorii.
- **Komplet zadań** – rozwiązanie wszystkich zadań dostępnych w chwili zdobycia odznaki.

Odznaki są definiowane w `achievement_service.py` i inicjalizowane idempotentnie przez migrację.

### Serie aktywności
- Seria jest liczona na podstawie dni z co najmniej jednym poprawnym rozwiązaniem.
- Błędne próby, logowanie i odblokowywanie wskazówek nie wydłużają serii.
- W danym dniu seria rośnie najwyżej raz.
- Profil pokazuje aktualną i najdłuższą serię.

### Profil i ranking
- Profil `/profile` pokazuje XP, poziom, pasek postępu, serie oraz odblokowane i zablokowane odznaki.
- Scoreboard pokazuje punkty rankingowe, poziom i XP.
- Po poprawnym rozwiązaniu zadania użytkownik widzi przyznane XP i nowe osiągnięcia.

## Dane i migracja

Dodano do tabeli `users` kolumny:
- `xp`
- `current_streak`
- `longest_streak`
- `last_solve_date`

Dodano tabele:
- `achievements` – katalog odznak i nagrody XP.
- `user_achievements` – zdobyte odznaki, data, kontekst oraz przyznane XP.

Migracja `migrate_achievements.py`:
- najpierw uruchamia wcześniejsze migracje etapów 1–5,
- dodaje brakujące kolumny użytkowników bez usuwania danych,
- inicjalizuje katalog odznak,
- odtwarza możliwe do wyliczenia odznaki z dotychczasowych rozwiązań,
- odtwarza XP z liczby rozwiązań i nagród zapisanych przy odznakach,
- wylicza najdłuższe serie z historycznych dat rozwiązań.
  
Migracja jest idempotentna. Dotychczasowe punkty rankingowe, zadania, rozwiązania i historia prób są zachowywane. Historyczne rozwiązania są uwzględniane w XP i odznakach.

## Aktualizacja lokalnej instalacji

W katalogu `CB_projekt`:

```powershell
python -m pip install -r requirements.txt
python migrate_achievements.py
python -m uvicorn main:app --reload
```

Migracja uruchamia się też automatycznie przy starcie aplikacji, po inicjalizacji zadań. Zachowaj istniejący plik `ctf_platform.db`.

## Testy

```powershell
python -m unittest -v test_auth.py test_docker_manager.py test_activity.py test_hints.py test_migrate_hints.py test_achievements.py test_templates.py
```

Testy obejmują naliczanie XP, progi poziomów, First Blood, odznaki za postęp, serie dni, brak wielokrotnego nagradzania oraz szablony profilu i rankingu.
