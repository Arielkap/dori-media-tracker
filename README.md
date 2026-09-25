# 🐟 Dori Media Tracker — Zewnętrzny RAM dla Złotej Rybki

> **Zasada działania:**  
> Dori ma 3-sekundową pamięć i tendencję do bujania w obłokach (a raczej marzenia o zamkach z piasku na dnie oceanu).  
> Mando założył jej cyfrową obrożę z linuksowego crontaba, która co poniedziałek pyta Ariela o obejrzane filmy, a co piątek przed weekendem przypomina o rozgrzebanych serialach.

---

## 📅 Harmonogram Dori (Crontab na VPS)

1. **Poniedziałek 09:00 UTC:**  
   Dori wysyła raport/pytanie na Telegram: *Jakie filmy obejrzałeś w minionym tygodniu / przez weekend?*
2. **Piątek 17:00 UTC:**  
   Dori wysyła przypomnienie na Telegram z aktualną listą nieskończonych seriali czekających na dokończenie w weekend.

---

## 🚀 Komendy CLI (`tracker.py`)

Skrypt używa wyłącznie biblioteki standardowej Pythona (**Zero LLM Tokens**, $0.00 kosztu operacyjnego).

```bash
# 1. Wyświetlenie aktualnego stanu
python3 tracker.py list
python3 tracker.py list --json

# 2. Dodawanie / aktualizacja seriali
python3 tracker.py add-series --title "Severance" --season 2 --episode 1 --platform "Apple TV+" --notes "Czeka na weekend"
python3 tracker.py update-series --title "Severance" --season 2 --episode 2

# 3. Zakończenie / usunięcie serialu
python3 tracker.py finish-series --title "Severance" --rating "9.5/10"
python3 tracker.py drop-series --title "Słaby Serial"

# 4. Dodawanie obejrzanych filmów
python3 tracker.py add-movie --title "Gladiator 2" --rating "8.5/10" --comment "Świetne kino akcji"

# 5. Szybkie parsowanie języka naturalnego (wykorzystywane przez Dori na czacie)
python3 tracker.py quick "film: Diuna 2 9/10"
python3 tracker.py quick "serial: Silo s02e05"
python3 tracker.py quick "skończyłem serial Severance 10/10"

# 6. Ręczne wywołanie powiadomień na Telegram
python3 tracker.py monday-check --send
python3 tracker.py friday-reminder --send
```

---

## 🗄️ Plik stanu (`media_data.json`)

Trwała baza danych w formacie JSON przechowująca:
- `unfinished_series` — aktywnie oglądane seriale z numerem sezonu, odcinka i platformą.
- `watched_movies` — historia obejrzanych filmów z datami i ocenami.
- `finished_series` — archiwum ukończonych produkcji.

---

## 🛡️ Architektura Mando & Dori (Zero-Hostinger Rule)

- Kod żyje lokalnie w `/Users/ariello/Agents/dori-media-tracker`.
- Zreplikowany na serwerze VPS w `/docker/hermes-agent-umxh/data/projects/dori-media-tracker`.
- Zabezpieczony w repozytorium GitHub: `Arielkap/dori-media-tracker`.
- Wszystkie sekrety (`TELEGRAM_BOT_TOKEN`) są czytane bezpośrednio z `/docker/hermes-agent-umxh/data/.env` na serwerze VPS.
