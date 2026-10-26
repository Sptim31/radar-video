"""Radar Vidéo France — serveur.

Lance :  python app.py   puis ouvre http://localhost:5000
Clé API YouTube Data v3 dans la variable d'environnement YT_API_KEY (ou fichier .env).
"""
import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from flask import Flask, jsonify, request, send_from_directory

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

API_KEY = os.environ.get("YT_API_KEY", "").strip()
PARIS = ZoneInfo("Europe/Paris")
YT = "https://www.googleapis.com/youtube/v3"

app = Flask(__name__, static_folder="static")

# ---------- cache mémoire (économise le quota : 1 recherche = 100 unités / 10 000 par jour) ----------
_cache: dict = {}


def cache_get(key):
    hit = _cache.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    return None


def cache_set(key, value, ttl):
    if len(_cache) > 2000:
        _cache.clear()
    _cache[key] = (time.time() + ttl, value)


# ---------- helpers ----------
def day_bounds(date_str):
    """Début et fin de la journée (heure de Paris) au format RFC3339 UTC."""
    d = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=PARIS)
    start = d.astimezone(ZoneInfo("UTC"))
    end = (d + timedelta(days=1)).astimezone(ZoneInfo("UTC"))
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return start.strftime(fmt), end.strftime(fmt)


def iso_duration(s):
    """PT1H2M3S -> 1:02:03"""
    if not s or not s.startswith("PT"):
        return ""
    h = m = sec = 0
    num = ""
    for ch in s[2:]:
        if ch.isdigit():
            num += ch
        else:
            v = int(num or 0)
            if ch == "H":
                h = v
            elif ch == "M":
                m = v
            elif ch == "S":
                sec = v
            num = ""
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


class YTError(Exception):
    pass


def yt_get(endpoint, params):
    params = {**params, "key": API_KEY}
    r = requests.get(f"{YT}/{endpoint}", params=params, timeout=15)
    if r.status_code != 200:
        try:
            err = r.json()["error"]
            reason = err.get("errors", [{}])[0].get("reason", "")
            msg = err.get("message", "")
        except Exception:
            reason, msg = "", r.text[:200]
        if reason in ("quotaExceeded", "dailyLimitExceeded"):
            raise YTError("Quota YouTube du jour épuisé (remis à zéro vers 9h, heure de Paris).")
        if reason in ("keyInvalid", "badRequest") and "key" in msg.lower():
            raise YTError("Clé API YouTube invalide. Vérifie YT_API_KEY.")
        raise YTError(f"Erreur YouTube : {msg}")
    return r.json()


def search_videos(mode, lat, lng, radius_km, date_str, q):
    start, end = day_bounds(date_str)
    params = {
        "part": "snippet",
        "type": "video",
        "maxResults": 50,
        "order": "date",
        "publishedAfter": start,
        "publishedBefore": end,
        "relevanceLanguage": "fr",
        "safeSearch": "moderate",
    }
    if mode == "geo":
        params["location"] = f"{lat:.4f},{lng:.4f}"
        params["locationRadius"] = f"{max(1, min(1000, round(radius_km)))}km"
        if q:
            params["q"] = q
    else:
        params["q"] = q or "actualité"
        params["regionCode"] = "FR"

    items = yt_get("search", params).get("items", [])
    ids = [it["id"]["videoId"] for it in items if it.get("id", {}).get("videoId")]
    if not ids:
        return []

    details = yt_get("videos", {
        "part": "snippet,recordingDetails,contentDetails,statistics",
        "id": ",".join(ids),
        "maxResults": 50,
    }).get("items", [])

    out = []
    for v in details:
        sn = v.get("snippet", {})
        loc = (v.get("recordingDetails") or {}).get("location") or {}
        thumbs = sn.get("thumbnails", {})
        thumb = (thumbs.get("medium") or thumbs.get("high") or thumbs.get("default") or {}).get("url", "")
        live = sn.get("liveBroadcastContent", "none")
        out.append({
            "id": v["id"],
            "title": sn.get("title", ""),
            "channel": sn.get("channelTitle", ""),
            "publishedAt": sn.get("publishedAt", ""),
            "thumb": thumb,
            "duration": iso_duration((v.get("contentDetails") or {}).get("duration", "")),
            "views": int((v.get("statistics") or {}).get("viewCount", 0) or 0),
            "live": live == "live",
            "lat": loc.get("latitude"),
            "lng": loc.get("longitude"),
        })
    out.sort(key=lambda x: x["publishedAt"], reverse=True)
    return out


# ---------- routes ----------
@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/api/videos")
def api_videos():
    if not API_KEY:
        return jsonify(error="Aucune clé API. Ajoute YT_API_KEY dans le fichier .env puis relance."), 500
    try:
        mode = request.args.get("mode", "geo")
        lat = float(request.args.get("lat", 46.6))
        lng = float(request.args.get("lng", 2.4))
        radius = float(request.args.get("radius", 50))
        date_str = request.args.get("date") or datetime.now(PARIS).strftime("%Y-%m-%d")
        datetime.strptime(date_str, "%Y-%m-%d")
        q = (request.args.get("q") or "").strip()[:100]
    except ValueError:
        return jsonify(error="Paramètres invalides."), 400

    # arrondi des coordonnées selon le rayon -> plus de hits de cache quand on bouge un peu la carte
    step = 0.01 if radius < 10 else 0.05 if radius < 50 else 0.2 if radius < 200 else 1.0
    lat_r, lng_r = round(lat / step) * step, round(lng / step) * step
    key = (mode, round(lat_r, 3), round(lng_r, 3), round(radius), date_str, q.lower())

    cached = cache_get(key)
    if cached is not None:
        return jsonify(videos=cached, cached=True)

    try:
        videos = search_videos(mode, lat_r, lng_r, radius, date_str, q)
    except YTError as e:
        return jsonify(error=str(e)), 502
    except requests.RequestException:
        return jsonify(error="YouTube ne répond pas. Réessaie dans un instant."), 502

    today = datetime.now(PARIS).strftime("%Y-%m-%d")
    cache_set(key, videos, 20 * 60 if date_str == today else 24 * 3600)
    return jsonify(videos=videos, cached=False)


@app.get("/api/status")
def status():
    return jsonify(key=bool(API_KEY))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  Radar Vidéo France  ->  http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
