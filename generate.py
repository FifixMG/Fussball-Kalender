#!/usr/bin/env python3
"""Erzeugt Fussball-ICS-Kalender aus offenen Daten (nur Standardbibliothek).

Quellen (siehe config.toml):
  openfootball_json  - https://github.com/openfootball/football.json (Public Domain)
  openfootball_txt   - Football.TXT aus openfootball/champions-league
  football_data      - https://api.football-data.org (API-Key, optional)

Aufruf:  python generate.py --config config.toml --out site
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import tomllib
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

UA = "fussball-kalender/1.0 (+https://github.com)"
MATCH_LENGTH = timedelta(hours=2)
KNOCKOUT_WORDS = (
    "round of", "quarter", "semi", "final", "play-off", "playoff",
    "last_16", "last 16", "last_32", "knockout", "third place", "3rd place",
)
MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


class SourceUnavailable(Exception):
    """Quelle existiert (noch) nicht oder ist nicht freigeschaltet. Kein Abbruch."""


@dataclass
class Match:
    competition: str
    cal: str
    kind: str                 # "club" | "national"
    european: bool
    tag: str
    round: str
    day: date
    start: datetime | None    # UTC; None = Uhrzeit unbekannt (ganztaegig)
    home: str
    away: str
    home_key: str = ""        # Text fuer das Regel-Matching (Name + Kurzname)
    away_key: str = ""
    result: str | None = None
    venue: str = ""
    knockout: bool = False
    top: int = 0
    phase: str = ""           # Rohdaten zur Phase (UEFA), fuer only_phases/exclude_phases


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
def http_get(url: str, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            raise SourceUnavailable(f"HTTP {e.code} fuer {url}") from e
        raise  # 429/5xx: Job soll scheitern, damit der alte Stand online bleibt


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------
def is_knockout(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in KNOCKOUT_WORDS)


def result_from_score(score: dict | list | None) -> str | None:
    if isinstance(score, list):  # manche Dateien liefern nur [heim, gast]
        score = {"ft": score} if len(score) == 2 else None
    if not score or not score.get("ft"):
        return None
    a, b = score["ft"]
    out = f"{a}-{b}"
    if score.get("et"):
        out += f" n.V. {score['et'][0]}-{score['et'][1]}"
    if score.get("p"):
        out += f" i.E. {score['p'][0]}-{score['p'][1]}"
    return out


TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})(?:\s+UTC([+-]\d{1,2})(?::?(\d{2}))?)?$")


def to_utc(day: date, time_str: str | None, tz: ZoneInfo) -> datetime | None:
    if not time_str:
        return None
    m = TIME_RE.match(time_str.strip())
    if not m:
        return None
    hh, mm, off_h, off_m = m.groups()
    local = datetime(day.year, day.month, day.day, int(hh), int(mm))
    if off_h is not None:
        sign = -1 if off_h.startswith("-") else 1
        zone = timezone(sign * timedelta(hours=abs(int(off_h)), minutes=int(off_m or 0)))
    else:
        zone = tz
    return local.replace(tzinfo=zone).astimezone(timezone.utc)


def parse_openfootball_json(raw: bytes, cal: dict, src: dict) -> list[Match]:
    data = json.loads(raw)
    tz = ZoneInfo(src.get("tz", "Europe/Berlin"))
    out = []
    for m in data.get("matches", []):
        if not m.get("team1") or not m.get("team2") or not m.get("date"):
            continue
        day = date.fromisoformat(m["date"])
        rnd = m.get("round", "")
        stage = f"{rnd} {m.get('group', '')}".strip()
        out.append(Match(
            competition=cal["name"], cal=cal["id"], kind=cal.get("kind", "club"),
            european=cal.get("european", False), tag=cal.get("tag", ""),
            round=stage, day=day, start=to_utc(day, m.get("time"), tz),
            home=m["team1"], away=m["team2"], home_key=m["team1"], away_key=m["team2"],
            result=result_from_score(m.get("score")), venue=m.get("ground", ""),
            knockout=is_knockout(rnd),
        ))
    return out


STAGE_RE = re.compile(r"^[▪»]\s*(.+)$")
DATE_RE = re.compile(
    r"^\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Z][a-z]{2})\s+(\d{1,2})(?:\s+(\d{4}))?\s*$")
MATCH_RE = re.compile(r"^\s+(?:(\d{1,2}:\d{2})\s+)?(.+?)\s+v\s+(.+?)\s*$")
CC_RE = re.compile(r"\s*\([A-Z]{3}\)\s*$")


def parse_openfootball_txt(raw: bytes, cal: dict, src: dict) -> list[Match]:
    tz = ZoneInfo(src.get("tz", "Europe/Berlin"))
    text = raw.decode("utf-8")
    season = re.search(r"(\d{4})/(\d{2})", text)
    start_year = int(season.group(1)) if season else date.today().year
    stage, day, time_str = "", None, None
    out = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#") or line.startswith("="):
            continue
        sm = STAGE_RE.match(line)
        if sm:
            stage, day, time_str = sm.group(1).strip(), None, None
            continue
        dm = DATE_RE.match(line)
        if dm:
            mon, dd, yy = MONTHS[dm.group(1)], int(dm.group(2)), dm.group(3)
            year = int(yy) if yy else (start_year if mon >= 7 else start_year + 1)
            day, time_str = date(year, mon, dd), None
            continue
        mm = MATCH_RE.match(line)
        if mm and day:
            if mm.group(1):
                time_str = mm.group(1)
            home = CC_RE.sub("", mm.group(2).strip())
            rest = re.split(r"\s{2,}", mm.group(3).strip(), maxsplit=1)
            away = CC_RE.sub("", rest[0].strip())
            sc = re.match(r"(\d+)-(\d+)", rest[1]) if len(rest) > 1 else None
            out.append(Match(
                competition=cal["name"], cal=cal["id"], kind=cal.get("kind", "club"),
                european=cal.get("european", False), tag=cal.get("tag", ""),
                round=stage, day=day, start=to_utc(day, time_str, tz),
                home=home, away=away, home_key=home, away_key=away,
                result=rest[1].strip() if sc else None, knockout=is_knockout(stage),
            ))
    return out


def parse_football_data(raw: bytes, cal: dict, src: dict) -> list[Match]:
    data = json.loads(raw)
    out = []
    for m in data.get("matches", []):
        utc = datetime.strptime(m["utcDate"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        h, a = m.get("homeTeam") or {}, m.get("awayTeam") or {}
        full = (m.get("score") or {}).get("fullTime") or {}
        res = f"{full['home']}-{full['away']}" if full.get("home") is not None else None
        stage = (m.get("stage") or "").replace("_", " ").title()
        out.append(Match(
            competition=cal["name"], cal=cal["id"], kind=cal.get("kind", "club"),
            european=cal.get("european", False), tag=cal.get("tag", ""),
            round=stage, day=utc.date(), start=utc,
            home=h.get("shortName") or h.get("name") or "TBD",
            away=a.get("shortName") or a.get("name") or "TBD",
            home_key=f"{h.get('name') or ''}|{h.get('shortName') or ''}",
            away_key=f"{a.get('name') or ''}|{a.get('shortName') or ''}",
            result=res, knockout=is_knockout(m.get("stage") or ""),
        ))
    return out


def parse_utc_iso(s: str) -> datetime:
    s = s.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_openligadb(raw: bytes, cal: dict, src: dict) -> list[Match]:
    """https://api.openligadb.de/getmatchdata/{shortcut}/{season} (ODbL, ohne Key)."""
    data = json.loads(raw)
    out = []
    for m in data or []:
        t1, t2 = m.get("team1") or {}, m.get("team2") or {}
        home, away = t1.get("teamName") or "", t2.get("teamName") or ""
        if not home or not away or not m.get("matchDateTimeUTC"):
            continue
        utc = parse_utc_iso(m["matchDateTimeUTC"])
        local = datetime.fromisoformat(m["matchDateTime"]) if m.get("matchDateTime") else utc
        # Ortszeit 00:00 heisst bei Community-Ligen praktisch immer "Uhrzeit noch offen"
        start = None if (local.hour, local.minute) == (0, 0) else utc
        day = local.date() if start is None else utc.date()
        res = None
        if m.get("matchIsFinished"):
            finals = [r for r in m.get("matchResults") or [] if r.get("resultTypeID") == 2]
            if finals:
                res = f"{finals[0].get('pointsTeam1')}-{finals[0].get('pointsTeam2')}"
        group = (m.get("group") or {}).get("groupName") or ""
        loc = m.get("location") or {}
        venue = ", ".join(x for x in (loc.get("locationStadium"), loc.get("locationCity")) if x)
        out.append(Match(
            competition=cal["name"], cal=cal["id"], kind=cal.get("kind", "club"),
            european=cal.get("european", False), tag=cal.get("tag", ""),
            round=group, day=day, start=start,
            home=home, away=away,
            home_key=f"{home}|{t1.get('shortName') or ''}", away_key=f"{away}|{t2.get('shortName') or ''}",
            result=res, venue=venue,
            knockout=is_knockout(group) or any(w in group.lower() for w in
                                               ("achtelfinale", "viertelfinale", "halbfinale", "finale", "k.o.")),
        ))
    return out


def parse_uefa(raw: bytes, cal: dict, src: dict) -> list[Match]:
    """Inoffizielle UEFA-Frontend-API match.uefa.com/v5/matches (ohne Key)."""
    data = json.loads(raw)
    items = data if isinstance(data, list) else data.get("matches") or data.get("items") or []
    expect = norm(src.get("expect", ""))
    out = []
    for m in items:
        comp = norm(((m.get("competition") or {}).get("metaData") or {}).get("name") or "")
        if expect and comp and expect not in comp:
            raise SourceUnavailable(f"competitionId liefert '{comp}', erwartet '{expect}'")
        h, a = m.get("homeTeam") or {}, m.get("awayTeam") or {}
        ko =(m.get("kickOffTime") or {}).get("dateTime")
        if not ko:
            continue
        utc = parse_utc_iso(ko)
        total = (m.get("score") or {}).get("total") or {}
        res = (f"{total['home']}-{total['away']}"
               if m.get("status") == "FINISHED" and total.get("home") is not None else None)
        md = m.get("matchday") or {}
        rd = m.get("round") or {}
        round_name = (rd.get("metaData") or {}).get("name") or ""
        rnd = md.get("longName") or md.get("name") or round_name
        phase = " | ".join(str(x) for x in (rd.get("phase"), md.get("phase"), rd.get("mode"), round_name) if x)
        out.append(Match(
            competition=cal["name"], cal=cal["id"], kind=cal.get("kind", "club"),
            european=cal.get("european", False), tag=cal.get("tag", ""),
            round=rnd, day=utc.date(), start=utc,
            home=h.get("internationalName") or "TBD", away=a.get("internationalName") or "TBD",
            home_key=f"{h.get('internationalName') or ''}|{h.get('teamCode') or ''}",
            away_key=f"{a.get('internationalName') or ''}|{a.get('teamCode') or ''}",
            result=res, phase=phase,
            # UEFA schreibt "KNOCK_OUT" (gesehen im Quellen-Test 2026-10-26)
            knockout="KNOCKOUT" in phase.upper().replace("_", "") or is_knockout(rnd) or is_knockout(round_name),
        ))
    return out


def phase_filter(ms: list[Match], src: dict) -> list[Match]:
    """only_phases / exclude_phases: Teilstrings, verglichen mit Phase + Runde (ohne Gross/Klein)."""
    only = [p.lower() for p in src.get("only_phases", [])]
    excl = [p.lower() for p in src.get("exclude_phases", [])]
    out = []
    for m in ms:
        text = f"{m.phase} | {m.round}".lower()
        if only and not any(p in text for p in only):
            continue
        if any(p in text for p in excl):
            continue
        out.append(m)
    return out


def load_uefa(src: dict, cal: dict) -> list[Match]:
    out, offset, limit = [], 0, 100
    while True:
        url = (f"https://match.uefa.com/v5/matches?competitionId={src['competition_id']}"
               f"&seasonYear={src['season_year']}&limit={limit}&offset={offset}&order=ASC")
        page = parse_uefa(http_get(url), cal, src)
        out += page
        if len(page) < limit or offset > 2000:
            return phase_filter(out, src)
        offset += limit


def load_source(src: dict, cal: dict) -> list[Match]:
    kind = src["kind"]
    if kind == "openligadb":
        url = (f"https://api.openligadb.de/getmatchdata/"
               f"{urllib.parse.quote(str(src['shortcut']))}/{src['season']}")
        return parse_openligadb(http_get(url), cal, src)
    if kind == "uefa":
        return load_uefa(src, cal)
    if kind == "football_data":
        token = os.environ.get("FOOTBALL_DATA_TOKEN", "")
        if not token:
            raise SourceUnavailable("FOOTBALL_DATA_TOKEN nicht gesetzt")
        url = (f"https://api.football-data.org/v4/competitions/{src['code']}/matches"
               f"?season={src['season']}")
        return parse_football_data(http_get(url, {"X-Auth-Token": token}), cal, src)
    raw = http_get(src["url"])
    if kind == "openfootball_json":
        return parse_openfootball_json(raw, cal, src)
    if kind == "openfootball_txt":
        return parse_openfootball_txt(raw, cal, src)
    raise ValueError(f"Unbekannte Quelle: {kind}")


# --------------------------------------------------------------------------
# Top-Spiele-Regeln
# --------------------------------------------------------------------------
def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


class Teams:
    """Alias-Gruppen. Normaler Alias = ganzes Wort irgendwo im Namen.
    Alias mit "=" davor = der Name muss exakt so lauten (fuer UEFA-Kurznamen wie
    "=Barcelona", die sonst auch "Espanyol Barcelona" treffen wuerden)."""

    def __init__(self, groups: list[list[str]]):
        self.patterns, self.exact = [], set()
        for g in groups:
            words = [norm(a) for a in g if not a.startswith("=")]
            self.exact |= {norm(a[1:]) for a in g if a.startswith("=")}
            if words:
                self.patterns.append(re.compile(
                    r"(?<![a-z0-9])(?:%s)(?![a-z0-9])" % "|".join(re.escape(w) for w in words)))

    def hit(self, text: str) -> bool:
        """text: ein Name oder mehrere Namen getrennt mit "|" (z.B. Name|Kurzname)."""
        names = [norm(p) for p in text.split("|")]
        if any(n in self.exact for n in names):
            return True
        return any(p.search(n) for p in self.patterns for n in names)


class TopRules:
    def __init__(self, cfg: dict):
        self.core = Teams(cfg.get("core", []))
        self.strong = Teams(cfg.get("strong", []))
        self.nations = Teams([[n] for n in cfg.get("national_strong", [])])

    def score(self, m: Match) -> int:
        if m.kind == "national":
            both = self.nations.hit(m.home_key) and self.nations.hit(m.away_key)
            r = m.round.lower()
            late = m.knockout and ("semi" in r or (
                "final" in r and not any(w in r for w in ("quarter", "third", "round of"))))
            if late:
                return 3
            return 2 if both else 0
        hc, ac = self.core.hit(m.home_key), self.core.hit(m.away_key)
        hs, as_ = self.strong.hit(m.home_key), self.strong.hit(m.away_key)
        if hc and ac:
            return 3
        if (hc and as_) or (ac and hs):
            return 2
        if m.european and m.knockout and (hc or ac or (hs and as_)):
            return 2
        if hc or ac:
            return 1
        return 0


# --------------------------------------------------------------------------
# ICS
# --------------------------------------------------------------------------
def esc(s: str) -> str:
    return (s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r", "").replace("\n", "\\n"))


def fold(line: str) -> str:
    if len(line.encode()) <= 75:
        return line
    parts, cur = [], b""
    for ch in line:
        cb = ch.encode()
        limit = 75 if not parts else 74
        if len(cur) + len(cb) > limit:
            parts.append(cur.decode())
            cur = cb
        else:
            cur += cb
    parts.append(cur.decode())
    return "\r\n ".join(parts)


def stamp(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%SZ")


def build_ics(name: str, matches: list[Match], now: datetime, with_tag: bool) -> str:
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//fussball-kalender//DE",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        f"X-WR-CALNAME:{esc(name)}", f"NAME:{esc(name)}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H",
    ]
    seen: dict[str, int] = {}
    for m in matches:
        base = hashlib.sha1(
            f"{m.cal}|{m.round}|{norm(m.home)}|{norm(m.away)}".encode()).hexdigest()[:20]
        seen[base] = seen.get(base, 0) + 1
        uid = f"{base}-{seen[base]}@fussball-kalender" if seen[base] > 1 else f"{base}@fussball-kalender"
        prefix = f"[{m.tag}] " if with_tag and m.tag else ""
        desc = [f"{m.competition}" + (f" - {m.round}" if m.round else "")]
        if m.result:
            desc.append(f"Ergebnis: {m.result}")
        if with_tag and m.top:
            desc.append(f"Top-Stufe: {m.top}/3")
        lines += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp(now)}"]
        if m.start:
            lines += [f"DTSTART:{stamp(m.start)}", f"DTEND:{stamp(m.start + MATCH_LENGTH)}"]
        else:
            lines += [f"DTSTART;VALUE=DATE:{m.day:%Y%m%d}",
                      f"DTEND;VALUE=DATE:{m.day + timedelta(days=1):%Y%m%d}"]
        lines += [f"SUMMARY:{esc(prefix + m.home + ' - ' + m.away)}",
                  f"DESCRIPTION:{esc(chr(10).join(desc))}"]
        if m.venue:
            lines.append(f"LOCATION:{esc(m.venue)}")
        lines += ["STATUS:CONFIRMED", "TRANSP:TRANSPARENT", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(l) for l in lines) + "\r\n"


def build_index(entries: list[tuple[str, str, int]], base_url: str, now: datetime) -> str:
    rows = []
    for fname, name, n in entries:
        url = f"{base_url.rstrip('/')}/{fname}" if base_url else fname
        rows.append(f"<li><a href=\"{html.escape(url)}\">{html.escape(name)}</a> "
                    f"<small>({n} Spiele)</small><br><code>{html.escape(url)}</code></li>")
    return ("<!doctype html><html lang=\"de\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>Fussball-Kalender</title>"
            "<style>body{font:16px system-ui;max-width:40rem;margin:1rem auto;padding:0 1rem}"
            "li{margin:.8rem 0}code{word-break:break-all;font-size:.8em}</style></head><body>"
            "<h1>Fussball-Kalender</h1><p>ICS-URLs in ICSx5 abonnieren.</p><ul>"
            + "".join(rows) + f"</ul><p><small>Stand: {now:%Y-%m-%d %H:%M} UTC</small></p>"
            "</body></html>\n")


# --------------------------------------------------------------------------
# Quellenauswahl
# --------------------------------------------------------------------------
def describe(src: dict) -> str:
    return src.get("label") or src.get("shortcut") or src.get("url") or src.get("code") or \
        f"{src['kind']}:{src.get('competition_id', '')}"


def collect(cal: dict, cutoff: date) -> list[Match]:
    """Standard: Quellen der Reihe nach, die erste mit >= min_matches Spielen gewinnt,
    sonst die ergiebigste. merge = true: alle Quellen zusammenfuehren (dedupliziert);
    Quellen mit fallback = true werden dann nur genutzt, wenn bis dahin nichts geladen wurde."""
    merge = cal.get("merge", False)
    best: list[Match] = []
    merged: dict[tuple, Match] = {}
    for src in cal.get("sources", []):
        if merge and src.get("fallback") and merged:
            continue
        try:
            ms = load_source(src, cal)
        except SourceUnavailable as e:
            print(f"[{cal['id']}] {describe(src)}: nicht verfuegbar ({e})", file=sys.stderr)
            continue
        except Exception as e:  # Netzfehler, kaputtes JSON: naechste Quelle probieren
            print(f"[{cal['id']}] {describe(src)}: Fehler {type(e).__name__}: {e}", file=sys.stderr)
            continue
        print(f"[{cal['id']}] {describe(src)}: {len(ms)} Spiele geladen", file=sys.stderr)
        if merge:
            for m in ms:
                key = (m.day, tuple(sorted((norm(m.home), norm(m.away)))))
                old = merged.get(key)
                if old is None or (old.start is None and m.start is not None):
                    merged[key] = m
            continue
        if len(ms) > len(best):
            best = ms
        if len(ms) >= src.get("min_matches", 1):
            break
    result = list(merged.values()) if merge else best
    return [m for m in result if m.day >= cutoff]


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.toml")
    ap.add_argument("--out", default="site")
    ap.add_argument("--today", help="YYYY-MM-DD (nur fuer Tests)")
    args = ap.parse_args(argv)

    with open(args.config, "rb") as f:
        cfg = tomllib.load(f)
    now = datetime.now(timezone.utc)
    today = date.fromisoformat(args.today) if args.today else now.date()
    cutoff = today - timedelta(days=cfg["output"].get("past_days", 7))
    rules = TopRules(cfg["top"])
    min_score = cfg["top"].get("min_score", 2)

    by_cal: dict[str, list[Match]] = {}
    failed_required = []
    for cal in cfg["calendars"]:
        matches = collect(cal, cutoff)
        if cal.get("required") and not matches:
            failed_required.append(cal["id"])
        for m in matches:
            m.top = rules.score(m)
        matches.sort(key=lambda m: (m.start or datetime.combine(m.day, datetime.min.time(), timezone.utc), m.home))
        by_cal[cal["id"]] = matches
        print(f"[{cal['id']}] {len(matches)} Spiele")

    os.makedirs(args.out, exist_ok=True)
    entries = []
    top_matches = sorted((m for ms in by_cal.values() for m in ms if m.top >= min_score),
                         key=lambda m: (m.start or datetime.combine(m.day, datetime.min.time(), timezone.utc), m.home))
    outputs = [(c["id"], c["title"], by_cal[c["id"]], False) for c in cfg["calendars"]]
    outputs.append(("top-spiele", cfg["top"].get("title", "Top-Spiele"), top_matches, True))
    for cid, title, ms, tagged in outputs:
        with open(os.path.join(args.out, f"{cid}.ics"), "w", encoding="utf-8", newline="") as f:
            f.write(build_ics(title, ms, now, tagged))
        entries.append((f"{cid}.ics", title, len(ms)))
    with open(os.path.join(args.out, "index.html"), "w", encoding="utf-8") as f:
        f.write(build_index(entries, os.environ.get("BASE_URL", cfg["output"].get("base_url", "")), now))
    if failed_required or not any(by_cal.values()):
        print(f"Pflicht-Kalender ohne Daten: {failed_required or 'alle'}. Abbruch, "
              "damit der zuletzt veroeffentlichte Stand online bleibt.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
