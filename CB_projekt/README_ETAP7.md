# Etap 7 – turnieje CTF i rywalizacja drużynowa

## Zakres funkcji

### Turnieje
- Administrator tworzy turniej z tytułem, opisem, trybem indywidualnym lub drużynowym, terminem rozpoczęcia i zakończenia, opcjonalnym limitem oraz listą zadań.
- Nowy turniej powstaje jako szkic. Administrator otwiera zapisy, a później może je zamknąć lub oznaczyć turniej jako zakończony.
- Uczestnicy zapisują się przed planowanym startem. W turnieju drużynowym zapis wykonuje lider drużyny.
- Strona /tournaments pokazuje dostępne zawody. Strona szczegółowa turnieju zawiera terminy, zadania, zapisy i rankingi.

### Drużyny
- Użytkownik może należeć do jednej drużyny.
- Każdy może utworzyć drużynę i zostaje jej liderem.
- Lider zaprasza użytkowników po nazwie konta.
- Zaproszony użytkownik może przyjąć lub odrzucić zaproszenie na stronie /teams.
- Lider może przekazać przywództwo innemu członkowi. Skład drużyny nie może być zmieniany podczas trwającego turnieju.
- Właściciel nie może usunąć drużyny mającej historię udziału w turniejach.

### Punktacja i rankingi
- Zadania i wartości punktowe turnieju są zapisywane jako snapshot w chwili utworzenia turnieju.
- Poprawne rozwiązanie zadania w aktywnym przedziale czasu jest zaliczane do turnieju, jeżeli gracz lub jego drużyna jest zarejestrowana.
- W trybie drużynowym pierwszy członek zespołu, który rozwiąże dane zadanie, zdobywa punkty w rankingu indywidualnym, a drużyna otrzymuje te same punkty w rankingu drużynowym. Kolejne rozwiązania tego zadania nie naliczają punktów drużynie ponownie.
- Ranking sortuje po punktach, liczbie rozwiązań i czasie ostatniego rozwiązania.
- Punkty turniejowe są przechowywane oddzielnie. Nie zmieniają globalnego wyniku użytkownika, XP, odznak ani serii aktywności.

## Nowe moduły i tabele

- tournament_models.py – modele drużyn, zaproszeń, turniejów, uczestników i rozwiązań.
- tournament_service.py – rejestracja, naliczanie punktów i generowanie rankingów.
- tournament_routes.py – widoki i akcje użytkowników oraz administratora.
- migrate_tournaments.py – idempotentne utworzenie tabel etapu 7.
- Nowe szablony: teams.html, tournaments.html, tournament_detail.html, admin_tournaments.html, admin_tournament_detail.html.
- Nowy test: test_tournaments.py.

Tabele: teams, team_members, team_invitations, tournaments, tournament_challenges, tournament_participants, tournament_team_participants, tournament_solves.

## Aktualizacja lokalnej instalacji

Zachowaj istniejący plik ctf_platform.db. W katalogu CB_projekt wykonaj:

```powershell
python -m pip install -r requirements.txt
python migrate_tournaments.py
python -m uvicorn main:app --reload
```

Migracja jest wykonywana również automatycznie podczas uruchomienia aplikacji. Daty turniejów w formularzach są interpretowane jako UTC.

## Testy

```powershell
python -m unittest -v test_tournaments.py test_templates.py test_auth.py test_activity.py test_achievements.py
```

Testy sprawdzają osobną punktację, unikalność rozwiązania, rankingi indywidualne i drużynowe, zakres czasowy zawodów, limit rejestracji i wymóg zgłoszenia drużyny przez lidera.
