#!/usr/bin/env python3
"""
Dori Media Tracker - CLI Engine & State Manager
Zero LLM tokens used for scheduled checks.

Runs via Linux Crontab on VPS for Dori, keeping track of:
- Unfinished TV series (reminded on Fridays)
- Watched movies (queried on Mondays)
"""

import os
import sys
import json
import re
import argparse
import urllib.request
import urllib.error
from datetime import datetime, date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "media_data.json")

ENV_PATHS = [
    os.path.join(BASE_DIR, ".env"),
    "/docker/hermes-agent-umxh/data/.env",
    "/opt/data/.env",
    os.path.expanduser("~/.env")
]

def get_env_var(key: str, default: str = "") -> str:
    val = os.environ.get(key)
    if val:
        return val.strip("\"' ")
    for path in ENV_PATHS:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith(f"{key}="):
                            v = line.split("=", 1)[1].strip("\"' ")
                            if v:
                                return v
            except Exception:
                pass
    return default

# Import telegram alert sender
try:
    from telegram_alert import send_alert
except ImportError:
    # If run in subpath or different cwd
    sys.path.insert(0, BASE_DIR)
    from telegram_alert import send_alert


def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {
            "unfinished_series": [],
            "watched_movies": [],
            "finished_series": [],
            "metadata": {"version": "1.0"}
        }
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] Błąd odczytu {DATA_FILE}: {e}, tworzę nową strukturę.", file=sys.stderr)
        return {
            "unfinished_series": [],
            "watched_movies": [],
            "finished_series": [],
            "metadata": {"version": "1.0"}
        }


def save_data(data: dict):
    # Atomic write to avoid corruptions
    temp_file = f"{DATA_FILE}.tmp.{os.getpid()}"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(temp_file, DATA_FILE)


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[-\s]+", "-", cleaned)


def normalize_title(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.lower())


# --- Media Operations ---

def add_movie(title: str, rating: str = None, watched_date: str = None, comment: str = None) -> dict:
    data = load_data()
    now_iso = datetime.now().isoformat()
    if not watched_date:
        watched_date = date.today().isoformat()

    item_id = f"mov-{slugify(title)}-{date.today().strftime('%Y%m%d')}"
    entry = {
        "id": item_id,
        "title": title.strip(),
        "watched_date": watched_date,
        "rating": rating or "",
        "comment": comment or "",
        "added_at": now_iso
    }
    data.setdefault("watched_movies", []).insert(0, entry)
    save_data(data)
    print(f"🎬 [DORI] Dodano film do trwałej pamięci: '{title}' (Ocena: {rating or 'brak'})")
    return entry


def add_series(title: str, season: int = 1, episode: int = 1, platform: str = "", notes: str = "") -> dict:
    data = load_data()
    now_iso = datetime.now().isoformat()
    series_list = data.setdefault("unfinished_series", [])

    # Check if already exists
    for s in series_list:
        if s.get("title", "").lower() == title.strip().lower():
            s["current_season"] = season
            s["current_episode"] = episode
            if platform:
                s["platform"] = platform
            if notes:
                s["notes"] = notes
            s["status"] = "watching"
            s["updated_at"] = now_iso
            save_data(data)
            print(f"📺 [DORI] Zaktualizowano istniejący serial: '{s['title']}' -> S{season:02d}E{episode:02d}")
            return s

    item_id = f"ser-{slugify(title)}"
    entry = {
        "id": item_id,
        "title": title.strip(),
        "current_season": season,
        "current_episode": episode,
        "platform": platform.strip(),
        "status": "watching",
        "notes": notes.strip(),
        "updated_at": now_iso
    }
    series_list.append(entry)
    save_data(data)
    print(f"📺 [DORI] Dodano nowy serial do listy: '{title}' (S{season:02d}E{episode:02d}, {platform or 'brak platformy'})")
    return entry


def update_series(title: str, season: int = None, episode: int = None, platform: str = None, notes: str = None, status: str = None) -> bool:
    data = load_data()
    now_iso = datetime.now().isoformat()
    series_list = data.get("unfinished_series", [])
    found = False

    for s in series_list:
        if title.strip().lower() in s.get("title", "").lower():
            if season is not None:
                s["current_season"] = season
            if episode is not None:
                s["current_episode"] = episode
            if platform is not None:
                s["platform"] = platform
            if notes is not None:
                s["notes"] = notes
            if status is not None:
                s["status"] = status
            s["updated_at"] = now_iso
            found = True
            print(f"📺 [DORI] Pomyślnie zaktualizowano: '{s['title']}' -> S{s.get('current_season', 1):02d}E{s.get('current_episode', 1):02d}")
            break

    if found:
        save_data(data)
        return True
    else:
        print(f"[ERROR] Nie znaleziono serialu o tytule pasującym do '{title}'.", file=sys.stderr)
        return False


def finish_series(title: str, rating: str = None) -> bool:
    data = load_data()
    series_list = data.get("unfinished_series", [])
    matched = None

    for i, s in enumerate(series_list):
        if title.strip().lower() in s.get("title", "").lower():
            matched = series_list.pop(i)
            break

    if not matched:
        print(f"[ERROR] Nie znaleziono serialu '{title}' na liście nieskończonych.", file=sys.stderr)
        return False

    finished_entry = {
        "id": matched.get("id"),
        "title": matched.get("title"),
        "finished_date": date.today().isoformat(),
        "rating": rating or "",
        "platform": matched.get("platform", "")
    }
    data.setdefault("finished_series", []).insert(0, finished_entry)
    save_data(data)
    print(f"🎉 [DORI] Gratulacje! Serial '{matched['title']}' przeniesiony do ukończonych! (Ocena: {rating or 'brak'})")
    return True


def drop_series(title: str) -> bool:
    data = load_data()
    series_list = data.get("unfinished_series", [])
    before_len = len(series_list)
    data["unfinished_series"] = [s for s in series_list if title.strip().lower() not in s.get("title", "").lower()]

    if len(data["unfinished_series"]) < before_len:
        save_data(data)
        print(f"🗑️ [DORI] Usunięto serial '{title}' z listy.")
        return True
    else:
        print(f"[ERROR] Nie znaleziono serialu '{title}'.", file=sys.stderr)
        return False


# --- Trakt.tv Synchronization (Zero LLM Tokens) ---

def sync_trakt(username: str = None, client_id: str = None, limit: int = 50, sync_episodes: bool = True) -> dict:
    user = username or get_env_var("TRAKT_USERNAME", "Ariello")
    cid = client_id or get_env_var("TRAKT_CLIENT_ID")

    if not cid:
        print("[ERROR] Brak TRAKT_CLIENT_ID w zmiennych środowiskowych ani w plikach .env.", file=sys.stderr)
        return {"error": "Missing TRAKT_CLIENT_ID"}

    headers = {
        "Content-Type": "application/json",
        "trakt-api-version": "2",
        "trakt-api-key": cid,
        "User-Agent": "DoriMediaTracker/1.0"
    }

    print(f"🐟 [DORI] Łączę się z Trakt.tv dla profilu: '{user}'...")

    # 1. Pobieramy oceny filmów użytkownika (enrichment)
    ratings_map = {}
    try:
        req_ratings = urllib.request.Request(
            f"https://api.trakt.tv/users/{user}/ratings/movies",
            headers=headers
        )
        with urllib.request.urlopen(req_ratings, timeout=15) as resp:
            ratings_data = json.loads(resp.read().decode("utf-8"))
            for r in ratings_data:
                m = r.get("movie", {})
                trakt_id = m.get("ids", {}).get("trakt")
                if trakt_id:
                    ratings_map[str(trakt_id)] = r.get("rating")
                if m.get("title"):
                    ratings_map[m.get("title").strip().lower()] = r.get("rating")
    except Exception as e:
        print(f"[WARN] Nie udało się pobrać ocen z Trakt: {e}", file=sys.stderr)

    data = load_data()
    watched_movies = data.setdefault("watched_movies", [])
    unfinished_series = data.setdefault("unfinished_series", [])
    finished_series = data.setdefault("finished_series", [])

    existing_history_ids = {str(m.get("trakt_history_id")) for m in watched_movies if m.get("trakt_history_id")}
    existing_movie_keys = {(m.get("title", "").strip().lower(), m.get("watched_date", "")) for m in watched_movies}

    # 2. Pobieramy historię obejrzanych filmów
    movies_added = 0
    try:
        req_movies = urllib.request.Request(
            f"https://api.trakt.tv/users/{user}/history/movies?limit={limit}",
            headers=headers
        )
        with urllib.request.urlopen(req_movies, timeout=20) as resp:
            movies_data = json.loads(resp.read().decode("utf-8"))
            for item in movies_data:
                hist_id = str(item.get("id"))
                m_info = item.get("movie", {})
                title = m_info.get("title", "").strip()
                year = m_info.get("year")
                watched_at_raw = item.get("watched_at", "")
                watched_date = watched_at_raw[:10] if watched_at_raw else date.today().isoformat()
                trakt_movie_id = str(m_info.get("ids", {}).get("trakt", ""))

                if hist_id in existing_history_ids:
                    continue
                if (title.lower(), watched_date) in existing_movie_keys:
                    continue

                rating_val = ratings_map.get(trakt_movie_id) or ratings_map.get(title.lower())
                rating_str = f"{rating_val}/10" if rating_val else ""

                entry = {
                    "id": f"mov-{slugify(title)}-{hist_id}",
                    "title": title,
                    "year": year,
                    "watched_date": watched_date,
                    "rating": rating_str,
                    "comment": "Trakt.tv",
                    "trakt_history_id": item.get("id"),
                    "trakt_id": m_info.get("ids", {}).get("trakt"),
                    "added_at": datetime.now().isoformat()
                }
                watched_movies.append(entry)
                existing_history_ids.add(hist_id)
                existing_movie_keys.add((title.lower(), watched_date))
                movies_added += 1
                print(f"🎬 [DORI] Zaimportowano z Trakt: '{title}' ({year or 'brak roku'}) - {watched_date}{f' (Ocena: {rating_str})' if rating_str else ''}")

    except Exception as e:
        print(f"[ERROR] Błąd synchronizacji filmów z Trakt: {e}", file=sys.stderr)

    # Sortujemy filmy malejąco po dacie obejrzenia
    watched_movies.sort(key=lambda x: x.get("watched_date", ""), reverse=True)

    # 3. Pobieramy historię odcinków seriali
    episodes_updated = 0
    episodes_added = 0
    if sync_episodes:
        try:
            req_episodes = urllib.request.Request(
                f"https://api.trakt.tv/users/{user}/history/episodes?limit=50",
                headers=headers
            )
            with urllib.request.urlopen(req_episodes, timeout=20) as resp:
                episodes_data = json.loads(resp.read().decode("utf-8"))
                show_latest = {}
                for ep_item in episodes_data:
                    show_title = ep_item.get("show", {}).get("title", "").strip()
                    ep_info = ep_item.get("episode", {})
                    s_num = ep_info.get("season", 1)
                    e_num = ep_info.get("number", 1)
                    watched_at = ep_item.get("watched_at", "")[:10]

                    if not show_title:
                        continue

                    key = show_title.lower()
                    if key not in show_latest:
                        show_latest[key] = {
                            "title": show_title,
                            "season": s_num,
                            "episode": e_num,
                            "watched_date": watched_at
                        }
                    else:
                        prev = show_latest[key]
                        if (s_num, e_num) > (prev["season"], prev["episode"]):
                            prev["season"] = s_num
                            prev["episode"] = e_num
                            prev["watched_date"] = watched_at

                for s_key, s_data in show_latest.items():
                    matched = False
                    norm_s_key = normalize_title(s_data["title"])
                    for existing in unfinished_series:
                        if norm_s_key == normalize_title(existing.get("title", "")):
                            matched = True
                            cur_s = existing.get("current_season", 1)
                            cur_e = existing.get("current_episode", 1)
                            if (s_data["season"], s_data["episode"]) > (cur_s, cur_e):
                                existing["current_season"] = s_data["season"]
                                existing["current_episode"] = s_data["episode"]
                                existing["updated_at"] = datetime.now().isoformat()
                                episodes_updated += 1
                                print(f"📺 [DORI] Zaktualizowano postęp '{existing['title']}': S{cur_s:02d}E{cur_e:02d} ➔ S{s_data['season']:02d}E{s_data['episode']:02d}")
                            break

                    is_finished = any(norm_s_key == normalize_title(fs.get("title", "")) for fs in finished_series)
                    if not matched and not is_finished:
                        new_s_entry = {
                            "id": f"ser-{slugify(s_data['title'])}",
                            "title": s_data["title"],
                            "current_season": s_data["season"],
                            "current_episode": s_data["episode"],
                            "platform": "",
                            "status": "watching",
                            "notes": "Trakt.tv",
                            "updated_at": datetime.now().isoformat()
                        }
                        unfinished_series.append(new_s_entry)
                        episodes_added += 1
                        print(f"📺 [DORI] Dodano nowy serial z Trakt: '{s_data['title']}' (S{s_data['season']:02d}E{s_data['episode']:02d})")

        except Exception as e:
            print(f"[WARN] Błąd synchronizacji seriali z Trakt: {e}", file=sys.stderr)

    save_data(data)
    summary = {
        "movies_added": movies_added,
        "episodes_updated": episodes_updated,
        "episodes_added": episodes_added
    }
    print(f"✅ [DORI] Synchronizacja z Trakt zakończona! Dodano filmów: {movies_added}, zaktualizowano seriali: {episodes_updated}, dodano seriali: {episodes_added}.")
    return summary


# --- Automated Prompts (Monday / Friday) ---

def build_monday_prompt() -> str:
    """Builds Monday question about watched movies, syncing with Trakt first if configured."""
    try:
        sync_trakt(limit=20, sync_episodes=False)
    except Exception:
        pass

    data = load_data()
    movies = data.get("watched_movies", [])

    # Ostatnie filmy z ostatnich 7 dni
    recent = []
    today = date.today()
    for m in movies:
        w_date_str = m.get("watched_date")
        if w_date_str:
            try:
                w_d = datetime.strptime(w_date_str, "%Y-%m-%d").date()
                if (today - w_d).days <= 7:
                    recent.append(m)
            except Exception:
                pass

    if recent:
        lines = [
            "🐟 <b>Dori: Poniedziałkowy meldunek filmowy</b> 🎬\n\n",
            "Zsynchronizowałam Twoje ostatnie seanse z Trakt.tv:\n\n"
        ]
        for rm in recent[:5]:
            rate = f" ({rm.get('rating')})" if rm.get("rating") else ""
            lines.append(f"• <b>{rm['title']}</b> [{rm.get('watched_date')}]{rate}\n")
        lines.append("\nOglądałeś w minionym tygodniu coś jeszcze, czego nie ma na Trakcie?")
        return "".join(lines)
    else:
        return (
            "🐟 <b>Dori: Poniedziałkowy meldunek filmowy</b> 🎬\n\n"
            "Ariel, co tam wpadło na ekran przez weekend lub w minionym tygodniu?\n"
            "Rzuć tytuł i ocenę, a od razu ląduje w notesie."
        )


def build_friday_reminder() -> str:
    """Builds Friday reminder with current unfinished TV series."""
    try:
        sync_trakt(limit=10, sync_episodes=True)
    except Exception:
        pass

    data = load_data()
    series = [s for s in data.get("unfinished_series", []) if s.get("status") != "dropped"]

    if not series:
        msg = (
            "🐟 <b>Dori: Piątkowy rozkład serialowy</b> 📺\n\n"
            "Czyste konto — nie masz obecnie rozgrzebanych seriali w notesie.\n"
            "Zaczynasz coś w ten weekend?"
        )
        return msg

    msg_lines = [
        "🐟 <b>Dori: Piątkowy rozkład serialowy</b> 📺\n\n",
        "Rozgrzebane seriale na ten weekend:\n\n"
    ]

    for s in series:
        platform_txt = f" ({s.get('platform')})" if s.get("platform") else ""
        notes_txt = f" — <i>{s.get('notes')}</i>" if s.get("notes") else ""
        season = s.get("current_season", 1)
        episode = s.get("current_episode", 1)
        msg_lines.append(f"• <b>{s['title']}</b>: Sezon {season}, Odcinek {episode}{platform_txt}{notes_txt}\n")

    msg_lines.append("\nMiłego seansu! Jak coś obejrzysz lub zmienisz, po prostu mi napisz.")
    return "".join(msg_lines)


def run_quick_add(text: str) -> bool:
    """
    Parses natural language from Ariel / Dori to automatically update state.
    Handles both compact notation (S01E05) and natural Polish phrasing.
    """
    text_clean = text.strip()

    # Check Trakt sync request
    if any(k in text_clean.lower() for k in ["sync trakt", "synchronizuj trakt", "pobierz z trakt", "zsynchronizuj", "zaciągnij z trakt", "pobierz filmy"]):
        sync_trakt()
        return True

    # Check finished / dropped
    if any(k in text_clean.lower() for k in ["skończyłem", "zaliczony", "obejrzany cały", "koniec serialu", "zakończyłem", "porzuciłem", "nie dla mnie"]):
        clean_title = re.sub(r"(?i)(skończyłem serial|zaliczony serial|obejrzany cały|koniec serialu|cały sezon|zakończyłem na \d+ sezonie|zakończyłem|porzuciłem|nie dla mnie)\s*", "", text_clean).strip("!.,: ")
        rate_match = re.search(r"(?:ocena:?\s*|rating:?\s*)?(\d+(?:\.\d+)?\s*/\s*10|\b(?:10|[1-9])\b\s*$)", clean_title)
        rating = ""
        if rate_match:
            rating = rate_match.group(1).strip()
            clean_title = clean_title[:rate_match.start()].strip(" ,-")
        return finish_series(clean_title, rating=rating)

    # Check series pattern: s01e02 or Polish "sezon X odcinek Y"
    se_match = re.search(r"(?i)\bs(\d{1,2})\s*e(\d{1,2})\b", text_clean)
    polish_se_match = re.search(r"(?i)(?:w\s*|na\s*)?(\d{1,2})\s*sezon(?:ie)?\s*(\d{1,2})\s*odcin(?:ku|ek)", text_clean)
    
    if se_match or polish_se_match:
        if se_match:
            s_num = int(se_match.group(1))
            e_num = int(se_match.group(2))
            raw_title = text_clean[:se_match.start()].strip()
            tail = text_clean[se_match.end():].strip(" ,-")
        else:
            s_num = int(polish_se_match.group(1))
            e_num = int(polish_se_match.group(2))
            raw_title = text_clean[:polish_se_match.start()].strip()
            tail = text_clean[polish_se_match.end():].strip(" ,-")

        raw_title = re.sub(r"(?i)^(dodaj serial|serial|zacząłem|oglądam|jestem na)\s*[:\-]?\s*", "", raw_title).strip()
        raw_title = re.sub(r"(?i)\s+oglądam\s*$", "", raw_title).strip()
        
        platform = ""
        notes = ""
        plat_match = re.search(r"\(([^)]+)\)|\[([^\]]+)\]", tail)
        if plat_match:
            platform = plat_match.group(1) or plat_match.group(2)
            tail = re.sub(r"\(([^)]+)\)|\[([^\]]+)\]", "", tail).strip()
        if tail:
            notes = tail
        if raw_title:
            add_series(raw_title, season=s_num, episode=e_num, platform=platform, notes=notes)
            return True

    # Check movie
    if any(k in text_clean.lower() for k in ["film:", "obejrzałem film", "obejrzałem", "widziałem", "film "]):
        raw = re.sub(r"(?i)^(dodaj film|film|obejrzałem film|obejrzałem|widziałem)\s*[:\-]?\s*", "", text_clean).strip()
        rating = ""
        rate_match = re.search(r"(?:(?:ocena|rating)\s*[:=]?\s*|\b)(\d+(?:\.\d+)?\s*/\s*10)\b", raw, re.IGNORECASE)
        if rate_match:
            rating = rate_match.group(1).strip()
            raw = raw[:rate_match.start()].strip(" ,-")
        else:
            trailing_rate = re.search(r"(?:[,\-–—]\s*|\s+(?:ocena\s*[:=]?\s*))(\d+(?:\.\d+)?)\s*$", raw, re.IGNORECASE)
            if trailing_rate:
                rating = trailing_rate.group(1).strip()
                raw = raw[:trailing_rate.start()].strip(" ,-")
        if raw:
            add_movie(title=raw, rating=rating)
            return True

    print(f"[WARN] Nie rozpoznano schematu tekstu: '{text_clean}'. Użyj standardowych flag --help.", file=sys.stderr)
    return False


# --- CLI Commands ---

def main():
    parser = argparse.ArgumentParser(description="Dori Media Tracker CLI")
    subparsers = parser.add_subparsers(dest="command")

    # list
    p_list = subparsers.add_parser("list", help="Wyświetl listę seriali i filmów")
    p_list.add_argument("--json", action="store_true", help="Format JSON")

    # add-movie
    p_am = subparsers.add_parser("add-movie", help="Dodaj obejrzany film")
    p_am.add_argument("--title", "-t", required=True, help="Tytuł filmu")
    p_am.add_argument("--rating", "-r", default="", help="Ocena (np. 8/10)")
    p_am.add_argument("--date", "-d", default="", help="Data (YYYY-MM-DD)")
    p_am.add_argument("--comment", "-c", default="", help="Krótki komentarz")

    # add-series
    p_as = subparsers.add_parser("add-series", help="Dodaj nowy serial lub zaktualizuj istniejący")
    p_as.add_argument("--title", "-t", required=True, help="Tytuł serialu")
    p_as.add_argument("--season", "-s", type=int, default=1, help="Numer sezonu")
    p_as.add_argument("--episode", "-e", type=int, default=1, help="Numer odcinka")
    p_as.add_argument("--platform", "-p", default="", help="Platforma (np. Apple TV+, Netflix)")
    p_as.add_argument("--notes", "-n", default="", help="Notatki")

    # update-series
    p_us = subparsers.add_parser("update-series", help="Zaktualizuj stan serialu")
    p_us.add_argument("--title", "-t", required=True, help="Tytuł serialu")
    p_us.add_argument("--season", "-s", type=int, default=None, help="Numer sezonu")
    p_us.add_argument("--episode", "-e", type=int, default=None, help="Numer odcinka")
    p_us.add_argument("--platform", "-p", default=None, help="Platforma")
    p_us.add_argument("--notes", "-n", default=None, help="Notatki")

    # finish-series
    p_fs = subparsers.add_parser("finish-series", help="Oznacz serial jako ukończony")
    p_fs.add_argument("--title", "-t", required=True, help="Tytuł serialu")
    p_fs.add_argument("--rating", "-r", default="", help="Ocena końcowa")

    # drop-series
    p_ds = subparsers.add_parser("drop-series", help="Usuń serial z listy")
    p_ds.add_argument("--title", "-t", required=True, help="Tytuł serialu")

    # monday-check
    p_mc = subparsers.add_parser("monday-check", help="Wygeneruj lub wyślij poniedziałkowe pytanie o filmy")
    p_mc.add_argument("--send", action="store_true", help="Wyślij na Telegram")

    # friday-reminder
    p_fr = subparsers.add_parser("friday-reminder", help="Wygeneruj lub wyślij piątkowe przypomnienie o serialach")
    p_fr.add_argument("--send", action="store_true", help="Wyślij na Telegram")

    # sync-trakt
    p_st = subparsers.add_parser("sync-trakt", help="Zsynchronizuj filmy i seriale z Trakt.tv")
    p_st.add_argument("--user", "-u", default=None, help="Nazwa użytkownika Trakt (domyślnie z .env)")
    p_st.add_argument("--limit", "-l", type=int, default=50, help="Liczba ostatnich filmów do pobrania")
    p_st.add_argument("--no-episodes", action="store_true", help="Nie synchronizuj seriali")

    # quick
    p_qk = subparsers.add_parser("quick", help="Szybkie dodawanie z tekstu naturalnego")
    p_qk.add_argument("text", help="Tekst w stylu 'film: Diuna 2 9/10' lub 'Silo s02e05'")

    args = parser.parse_args()

    if not args.command or args.command == "list":
        data = load_data()
        if getattr(args, "json", False):
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return

        print("\n========================================")
        print("🐟 DORI MEDIA TRACKER — STAN NOTESU")
        print("========================================")
        unfinished = data.get("unfinished_series", [])
        print(f"\n📺 ROZGRZEBANE SERIALE ({len(unfinished)}):")
        if not unfinished:
            print("  (Brak rozgrzebanych seriali)")
        for s in unfinished:
            plat = f" [{s.get('platform')}]" if s.get('platform') else ""
            notes = f" — {s.get('notes')}" if s.get('notes') else ""
            print(f"  • {s['title']} — S{s.get('current_season', 1):02d}E{s.get('current_episode', 1):02d}{plat}{notes}")

        movies = data.get("watched_movies", [])
        print(f"\n🎬 OSTATNIO OBEJRZANE FILMY ({len(movies)}):")
        if not movies:
            print("  (Brak zapisanych filmów)")
        for m in movies[:5]:
            rate = f" ({m.get('rating')})" if m.get('rating') else ""
            comm = f" — {m.get('comment')}" if m.get('comment') else ""
            print(f"  • [{m.get('watched_date', '')}] {m['title']}{rate}{comm}")

        finished = data.get("finished_series", [])
        if finished:
            print(f"\n🎉 UKOŃCZONE SERIALE ({len(finished)}):")
            for fs in finished[:3]:
                rate = f" ({fs.get('rating')})" if fs.get('rating') else ""
                print(f"  • {fs['title']}{rate} — ukończono {fs.get('finished_date')}")
        print("========================================\n")

    elif args.command == "add-movie":
        add_movie(title=args.title, rating=args.rating, watched_date=args.date, comment=args.comment)

    elif args.command == "add-series":
        add_series(title=args.title, season=args.season, episode=args.episode, platform=args.platform, notes=args.notes)

    elif args.command == "update-series":
        update_series(title=args.title, season=args.season, episode=args.episode, platform=args.platform, notes=args.notes)

    elif args.command == "finish-series":
        finish_series(title=args.title, rating=args.rating)

    elif args.command == "drop-series":
        drop_series(title=args.title)

    elif args.command == "sync-trakt":
        sync_trakt(username=args.user, limit=args.limit, sync_episodes=not args.no_episodes)

    elif args.command == "monday-check":
        msg = build_monday_prompt()
        if args.send:
            ok = send_alert(msg)
            if ok:
                print("✅ Poniedziałkowe pytanie wysłane na Telegram!")
            else:
                print("❌ Błąd wysyłki poniedziałkowego pytania.")
                sys.exit(1)
        else:
            print("--- PODGLĄD WIADOMOŚCI (Poniedziałek) ---")
            print(msg)

    elif args.command == "friday-reminder":
        msg = build_friday_reminder()
        if args.send:
            ok = send_alert(msg)
            if ok:
                print("✅ Piątkowe przypomnienie wysłane na Telegram!")
            else:
                print("❌ Błąd wysyłki piątkowego przypomnienia.")
                sys.exit(1)
        else:
            print("--- PODGLĄD WIADOMOŚCI (Piątek) ---")
            print(msg)

    elif args.command == "quick":
        run_quick_add(args.text)


if __name__ == "__main__":
    main()
