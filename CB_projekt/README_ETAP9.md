# Etap 9 – analityka i raportowanie

## Panel administratora

Strona `/admin/analytics` prezentuje:
- bieżącą liczbę kont, zadań, drużyn i turniejów;
- aktywnych użytkowników w wybranym okresie;
- próby, poprawne i niepoprawne zgłoszenia flag, rozwiązania oraz skuteczność;
- dzienną aktywność w UTC;
- popularność kategorii;
- statystyki i skuteczność poszczególnych zadań;
- zestawienie użytkowników, drużyn i turniejów.

Filtry „Od” i „Do” są opcjonalne. Obie daty są interpretowane jako daty UTC, a data końcowa jest włączona do raportu. Liczba kont, zadań i drużyn jest stanem bieżącym; próby, rozwiązania, aktywni użytkownicy i punkty turniejowe są liczone w wybranym okresie.

## Statystyki gracza

Strona `/profile/analytics` pokazuje punkty globalne, XP, poziom, serie, próby, poprawne odpowiedzi, skuteczność, postęp w kategoriach, aktywność z ostatnich 30 dni i historię udziału w turniejach. Dane osobiste są dostępne wyłącznie po zalogowaniu.

## Statystyki drużyny

Strona `/teams/analytics` jest dostępna dla zalogowanego członka drużyny. Pokazuje aktywność członków, punkty globalne i XP poszczególnych graczy, rozwiązania oraz wkład w wyniki turniejowe zespołu.

## Eksport raportów

- Administrator: `/admin/analytics/export.csv?kind=summary` lub `kind=challenges|users|categories|daily|teams|tournaments`; pełny raport PDF: `/admin/analytics/export.pdf`.
- Gracz: `/profile/analytics/export.csv` i `/profile/analytics/export.pdf`.
- Drużyna: `/teams/analytics/export.csv` i `/teams/analytics/export.pdf`.

CSV jest kodowany jako UTF-8 z BOM, aby Excel poprawnie odczytywał polskie znaki. Wartości mogące zostać zinterpretowane jako formuły arkusza są poprzedzane apostrofem. PDF jest generowany lokalnie przez ReportLab; polskie znaki są transliterowane w celu zachowania kompatybilności z wbudowanymi fontami PDF.

## Nowe pliki

- `analytics_service.py` – odczytowe agregacje i statystyki.
- `analytics_routes.py` – strony i endpointy eksportu.
- `analytics_export.py` – generowanie CSV i PDF.
- `test_analytics.py` – testy agregacji, filtrów i eksportu.
- `templates/zerofour/admin_analytics.html` – panel administratora.
- `templates/zerofour/player_analytics.html` – statystyki gracza.
- `templates/zerofour/team_analytics.html` – statystyki drużyny.

Etap 9 nie dodaje tabel ani nie zmienia istniejących punktów, XP, rozwiązań i wyników turniejowych. Wymaga jedynie doinstalowania biblioteki ReportLab z pliku `requirements.txt`.

## Aktualizacja lokalnej instalacji

Zachowaj istniejący plik `ctf_platform.db`. W katalogu `CB_projekt` wykonaj:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

Nie jest wymagana dodatkowa migracja bazy danych.

## Testy

```powershell
python -m unittest -v test_analytics.py test_notifications.py test_tournaments.py test_templates.py test_auth.py test_activity.py test_achievements.py
```

Testy sprawdzają zakres dat, liczenie prób i rozwiązań, skuteczność, statystyki gracza i drużyny, ochronę CSV przed formułami arkusza oraz prawidłową strukturę pliku PDF.
