"""Generate a sample dataset in the same format as the Sparkify project.

song_data/  -> one JSON object per file, partitioned by the first three
               letters of the track ID (e.g. song_data/A/B/C/TRABC....json)
log_data/   -> newline-delimited JSON event logs, one file per day
               (e.g. log_data/2018/11/2018-11-01-events.json)
"""
import json
import random
import string
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)
DATA = Path(__file__).parent / "data"

WORDS = ("love night city fire dream heart summer rain gold blue river road "
         "electric echo shadow light wild young midnight ocean stars velvet "
         "neon broken silver home ghost thunder sugar paper mirror").split()
CITIES = ["New York, NY", "Los Angeles, CA", "Chicago, IL", "Austin, TX",
          "Seattle, WA", "Atlanta, GA", "Denver, CO", "Boston, MA",
          "San Francisco-Oakland-Hayward, CA", "Portland-South Portland, ME"]
FIRST = ["Ava", "Liam", "Mia", "Noah", "Zoe", "Ethan", "Lily", "Mason", "Chloe",
         "Lucas", "Ella", "Logan", "Aria", "Jacob", "Nora", "Owen", "Ivy",
         "Caleb", "Ruby", "Henry", "Jade", "Leo", "Maya", "Eli", "Kai"]
LAST = ["Smith", "Garcia", "Kim", "Nguyen", "Patel", "Brown", "Lopez", "Chen",
        "Davis", "Wilson", "Moore", "Clark", "Lewis", "Young", "Hall"]
AGENTS = [
    '"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1985.143 Safari/537.36"',
    '"Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1985.143 Safari/537.36"',
    "Mozilla/5.0 (Windows NT 6.1; WOW64; rv:31.0) Gecko/20100101 Firefox/31.0",
    '"Mozilla/5.0 (iPhone; CPU iPhone OS 7_1_2 like Mac OS X) AppleWebKit/537.51.2 (KHTML, like Gecko) Version/7.0 Mobile/11D257 Safari/9537.53"',
]


def rand_id(prefix, n=16):
    return prefix + "".join(random.choices(string.ascii_uppercase + string.digits, k=n))


def title(k):
    return " ".join(random.sample(WORDS, k)).title()


def make_songs(n_artists=40, n_songs=120):
    artists = []
    for _ in range(n_artists):
        has_geo = random.random() < 0.6
        artists.append({
            "artist_id": rand_id("AR"),
            "artist_name": f"The {title(1)} {random.choice(['Band', 'Collective', 'Project', 'Kids', 'Society'])}"
                           if random.random() < 0.5 else f"{random.choice(FIRST)} {random.choice(LAST)}",
            "artist_location": random.choice(CITIES + [""]),
            "artist_latitude": round(random.uniform(25, 48), 5) if has_geo else None,
            "artist_longitude": round(random.uniform(-122, -71), 5) if has_geo else None,
        })
    songs = []
    for _ in range(n_songs):
        a = random.choice(artists)
        track_id = "TRA" + "".join(random.choices(string.ascii_uppercase, k=2)) + rand_id("", 13)
        song = {"num_songs": 1, **a,
                "song_id": rand_id("SO"),
                "title": title(random.randint(1, 3)),
                "duration": round(random.uniform(120, 420), 5),
                "year": random.choice([0] + list(range(1970, 2011)))}
        path = DATA / "song_data" / track_id[2] / track_id[3] / track_id[4] / f"{track_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(song))
        songs.append(song)
    return songs


def make_logs(songs, n_users=60, days=30):
    users = [{"userId": str(i), "firstName": random.choice(FIRST), "lastName": random.choice(LAST),
              "gender": random.choice("MF"), "level": random.choice(["free", "free", "paid"]),
              "location": random.choice(CITIES), "userAgent": random.choice(AGENTS),
              "registration": float(random.randint(1_530_000_000_000, 1_541_000_000_000))}
             for i in range(1, n_users + 1)]
    other_pages = ["Home", "Logout", "Settings", "Help", "About", "Upgrade", "Downgrade"]
    session_id = 1
    for d in range(days):
        day = datetime(2018, 11, 1) + timedelta(days=d)
        events = []
        for u in random.sample(users, random.randint(15, 35)):
            # Users upgrade from free to paid over the month
            if u["level"] == "free" and random.random() < 0.03:
                u["level"] = "paid"
            t = day + timedelta(seconds=random.randint(0, 80_000))
            for item in range(random.randint(3, 25)):
                is_song = random.random() < 0.8
                if is_song:
                    # ~35% of plays are songs present in our song catalogue;
                    # the rest come from the much larger full catalogue
                    s = random.choice(songs) if random.random() < 0.35 else {
                        "artist_name": f"{random.choice(FIRST)} {random.choice(LAST)}",
                        "title": title(2), "duration": round(random.uniform(120, 420), 5)}
                events.append({
                    "artist": s["artist_name"] if is_song else None,
                    "auth": "Logged In",
                    "firstName": u["firstName"], "gender": u["gender"],
                    "itemInSession": item, "lastName": u["lastName"],
                    "length": s["duration"] if is_song else None,
                    "level": u["level"], "location": u["location"],
                    "method": "PUT" if is_song else "GET",
                    "page": "NextSong" if is_song else random.choice(other_pages),
                    "registration": u["registration"], "sessionId": session_id,
                    "song": s["title"] if is_song else None,
                    "status": 200,
                    "ts": int(t.timestamp() * 1000),
                    "userAgent": u["userAgent"], "userId": u["userId"],
                })
                t += timedelta(seconds=random.randint(60, 400))
            session_id += 1
        # A few logged-out events with empty userId, as in the real logs
        for _ in range(random.randint(2, 6)):
            events.append({"artist": None, "auth": "Logged Out", "firstName": None, "gender": None,
                           "itemInSession": 0, "lastName": None, "length": None, "level": "free",
                           "location": None, "method": "GET", "page": "Home", "registration": None,
                           "sessionId": session_id, "song": None, "status": 200,
                           "ts": int((day + timedelta(seconds=random.randint(0, 86_000))).timestamp() * 1000),
                           "userAgent": None, "userId": ""})
            session_id += 1
        events.sort(key=lambda e: e["ts"])
        path = DATA / "log_data" / "2018" / "11" / f"{day:%Y-%m-%d}-events.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(e) for e in events) + "\n")


if __name__ == "__main__":
    songs = make_songs()
    make_logs(songs)
    print(f"Generated data in {DATA}")
