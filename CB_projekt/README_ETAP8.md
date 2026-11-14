# Etap 8 – centrum powiadomień i komunikaty administratora

## Funkcje użytkownika

- Strona `/notifications` pokazuje do 100 najnowszych powiadomień.
- Menu główne wyświetla licznik nieprzeczytanych wiadomości.
- Użytkownik może oznaczyć pojedyncze powiadomienie lub wszystkie wiadomości jako przeczytane.
- Przycisk „Otwórz” prowadzi do odpowiedniego miejsca w aplikacji.
- Ustawienia pozwalają osobno włączyć lub wyłączyć cztery kategorie: drużyny, turnieje, osiągnięcia i komunikaty.
- Domyślnie wszystkie kategorie są włączone.

## Automatyczne powiadomienia

- Zaproszenie do drużyny i zaakceptowanie zaproszenia przez nowego członka.
- Opublikowanie turnieju po otwarciu zapisów.
- Zdobycie nowej odznaki.
- Przypomnienie turniejowe 24 godziny i godzinę przed rozpoczęciem.
- Informacja o rozpoczęciu i zakończeniu turnieju.

Aplikacja sprawdza harmonogram co 60 sekund. Po przekroczeniu terminu końca aktywny turniej automatycznie otrzymuje status „finished”. Unikalne klucze zdarzeń zapobiegają wielokrotnemu wysyłaniu tych samych powiadomień.

## Komunikaty administratora

- Strona `/admin/announcements` jest dostępna dla administratora.
- Można opublikować komunikat z tytułem i treścią.
- Publikacja wysyła powiadomienie do użytkowników z włączoną kategorią „Komunikaty”.
- Historia pokazuje liczbę utworzonych powiadomień dla komunikatu.
- Wcześniejsze komunikaty można archiwizować. Archiwizacja nie usuwa już dostarczonych powiadomień.

## Nowe pliki

- `notification_models.py` – modele powiadomień, ustawień, komunikatów i rejestru zdarzeń.
- `notification_service.py` – dostarczanie, deduplikacja i harmonogram turniejowy.
- `notification_routes.py` – centrum użytkownika i panel komunikatów.
- `migrate_notifications.py` – idempotentna migracja tabel.
- `templates/zerofour/notifications.html` – skrzynka i ustawienia powiadomień.
- `templates/zerofour/admin_announcements.html` – panel publikacji komunikatów.
- `test_notifications.py` – testy usług powiadomień i harmonogramu.

Tabele: `notifications`, `notification_preferences`, `announcements`, `notification_dispatches`.

## Aktualizacja lokalnej instalacji

Zachowaj istniejący plik `ctf_platform.db`. W katalogu `CB_projekt` wykonaj:

```powershell
python -m pip install -r requirements.txt
python migrate_notifications.py
python -m uvicorn main:app --reload
```

Migracja uruchamia się również automatycznie podczas importu aplikacji, po migracji turniejów. Nie jest potrzebny zewnętrzny dostawca poczty elektronicznej.

## Testy

```powershell
python -m unittest -v test_notifications.py test_tournaments.py test_templates.py test_auth.py test_activity.py test_achievements.py
```

Testy obejmują domyślne ustawienia, wyłączanie kategorii, deduplikację, wysyłkę komunikatów oraz przypomnienia, rozpoczęcie i automatyczne zakończenie turnieju.
