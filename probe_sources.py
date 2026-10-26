#!/usr/bin/env python3
"""Prueft alle Datenquellen mit echten Abfragen: aktuelle Saison + 3 Jahre zurueck.

    python probe_sources.py            # alles
    python probe_sources.py --quick    # nur aktuelle Saison

Gibt pro Quelle aus: Spiele, Zeitraum, Anteil mit Uhrzeit, kommende Spiele,
und ob PSG/Barca/Real/Bayern bzw. DE/ES/FR vorkommen. Nur Standardbibliothek.
FOOTBALL_DATA_TOKEN in der Umgebung aktiviert die football-data.org-Tests.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate as g  # noqa: E402

CORE = g.Teams([["Paris Saint-Germain", "PSG", "Paris SG", "=Paris"], ["FC Barcelona", "Barca", "=Barcelona"],
                ["Real Madrid"], ["Bayern"]])
NATIONS = g.Teams([["Germany", "Deutschland"], ["Spain", "Spanien"], ["France", "Frankreich"]])
SEASONS = [2026, 2025, 2024, 2023]          # Startjahr der Saison
TODAY = datetime.now(timezone.utc).date()


def summarize(label: str, fn) -> None:
    t0 = time.time()
    try:
        ms = fn()
    except g.SourceUnavailable as e:
        print(f"  {label:44} --  nicht verfuegbar: {e}")
        return
    except Exception as e:
        print(f"  {label:44} !!  {type(e).__name__}: {e}")
        return
    if not ms:
        print(f"  {label:44} 0 Spiele ({time.time() - t0:.1f}s)")
        return
    days = sorted(m.day for m in ms)
    timed = sum(1 for m in ms if m.start)
    upcoming = sum(1 for m in ms if m.day >= TODAY)
    teams = CORE if ms[0].kind == "club" else NATIONS
    hits = sum(1 for m in ms if teams.hit(m.home_key) or teams.hit(m.away_key))
    print(f"  {label:44} {len(ms):4} Spiele | {days[0]} bis {days[-1]} | "
          f"Uhrzeit {100 * timed // len(ms):3}% | kommend {upcoming:3} | Top-Teams {hits:3}")
    up = [m for m in ms if m.day >= TODAY][:2]
    for m in up:
        when = m.start.strftime("%Y-%m-%d %H:%MZ") if m.start else f"{m.day} (ganztaegig)"
        print(f"  {'':44}   z.B. {when} {m.home} - {m.away} [{m.round}]")


def club(cid: str, name: str, european=False) -> dict:
    return {"id": cid, "name": name, "tag": cid, "european": european, "kind": "club"}


def nat(cid: str, name: str) -> dict:
    return {"id": cid, "name": name, "tag": cid, "kind": "national"}


def probe_openligadb(quick: bool) -> None:
    print("\n== OpenLigaDB (api.openligadb.de, ODbL, ohne Key)")
    try:
        leagues = json.loads(g.http_get("https://api.openligadb.de/getavailableleagues"))
    except Exception as e:
        print(f"  getavailableleagues fehlgeschlagen: {type(e).__name__}: {e}")
        return
    words = ("champions", "europa league", "nations", "national", "laender", "länder",
             "wm", "world cup", "em ", "euro", "freundschaft", "bundesliga", "laliga", "la liga", "ligue")
    seasons = SEASONS[:1] if quick else SEASONS
    picked = [l for l in leagues
              if int(l.get("leagueSeason") or 0) in seasons
              and (l.get("sport") or {}).get("sportId") in (1, None)
              and any(w in (l.get("leagueName") or "").lower() + " " for w in words)]
    print(f"  {len(picked)} passende Ligen in {seasons}")
    for l in sorted(picked, key=lambda x: (-int(x["leagueSeason"]), x["leagueName"])):
        name = l["leagueName"]
        kind = "national" if any(w in name.lower() for w in
                                 ("nation", "länder", "laender", "wm", "world", "em ", "euro", "dfb")) else "club"
        cal = (nat if kind == "national" else club)("x", name)
        src = {"shortcut": l["leagueShortcut"], "season": l["leagueSeason"]}
        label = f"{l['leagueShortcut']}/{l['leagueSeason']} {name}"[:44]
        summarize(label, lambda s=src, c=cal: g.load_source({"kind": "openligadb", **s}, c))
        time.sleep(0.3)


def probe_uefa(quick: bool) -> None:
    print("\n== UEFA-Frontend-API (match.uefa.com, inoffiziell, ohne Key)")
    ids = "1,3,5,14,17,18,24,25,27,28,2014,2019"
    try:
        comps = json.loads(g.http_get(f"https://comp.uefa.com/v2/competitions?competitionIds={ids}"))
        items = comps if isinstance(comps, list) else comps.get("data") or comps.get("items") or []
        for c in items:
            print(f"  competitionId {c.get('id'):>5} = {(c.get('metaData') or {}).get('name')}")
    except Exception as e:
        print(f"  competitions-Abfrage fehlgeschlagen: {type(e).__name__}: {e}")
    years = [s + 1 for s in (SEASONS[:1] if quick else SEASONS)]
    for cid, name in ((1, "Champions League"), (14, "Europa League"), (3, "EM"), (2014, "Nations League"),
                      (17, "WM")):
        for y in ([2028] if cid == 3 else [2030] if cid == 17 else years):
            src = {"kind": "uefa", "competition_id": cid, "season_year": y}
            cal = (club("x", name, True) if cid in (1, 14) else nat("x", name))
            store: list = []

            def run(s=src, c=cal, st=store):
                ms = g.load_source(s, c)
                st.extend(ms)
                return ms
            summarize(f"competitionId={cid} seasonYear={y} ({name})", run)
            if store:  # Phasen-Werte zeigen, damit only_/exclude_phases stimmen
                phases = collections.Counter(m.phase or "(leer)" for m in store)
                for p, n in phases.most_common(8):
                    print(f"  {'':44}   Phase {n:3}x  {p}")


def probe_config(quick: bool) -> None:
    """End-to-End: genau die Quellenauswahl aus config.toml, wie im Workflow."""
    import tomllib
    print("\n== config.toml (End-to-End, wie generate.py)")
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.toml"), "rb") as f:
        cfg = tomllib.load(f)
    rules = g.TopRules(cfg["top"])
    from datetime import timedelta
    cutoff = TODAY - timedelta(days=cfg["output"].get("past_days", 7))
    for cal in cfg["calendars"]:
        ms = g.collect(cal, cutoff)
        for m in ms:
            m.top = rules.score(m)
        timed = sum(1 for m in ms if m.start)
        tops = [m for m in ms if m.top >= cfg["top"].get("min_score", 2)]
        print(f"  {cal['id']:18} {len(ms):4} Spiele | Uhrzeit {100 * timed // max(len(ms), 1):3}% | "
              f"Top-Spiele {len(tops):3}")
        for m in sorted(tops, key=lambda m: m.day)[:4]:
            when = m.start.strftime("%Y-%m-%d %H:%MZ") if m.start else f"{m.day} (ganztaegig)"
            print(f"  {'':18}   Stufe {m.top} {when} {m.home} - {m.away}")


def probe_football_data(quick: bool) -> None:
    print("\n== football-data.org (Key noetig, Free-Tier 10 Abfragen/Minute)")
    if not g.os.environ.get("FOOTBALL_DATA_TOKEN"):
        print("  FOOTBALL_DATA_TOKEN nicht gesetzt, uebersprungen")
        return
    tests = [("CL", s) for s in (SEASONS[:1] if quick else SEASONS)] + \
            [("FL1", 2026), ("EL", 2026), ("EC", 2024), ("WC", 2026)]
    for code, season in tests:
        src = {"kind": "football_data", "code": code, "season": season}
        summarize(f"{code} season={season}", lambda s=src: g.load_source(s, club("x", code, True)))
        time.sleep(6.5)


def probe_github(quick: bool) -> None:
    print("\n== openfootball (GitHub, Public Domain)")
    raw = "https://raw.githubusercontent.com/openfootball"
    for s in (SEASONS[:1] if quick else SEASONS):
        tag = f"{s}-{(s + 1) % 100:02d}"
        for comp in ("cl", "el"):
            src = {"kind": "openfootball_txt", "url": f"{raw}/champions-league/master/{tag}/{comp}.txt"}
            summarize(f"champions-league/{tag}/{comp}.txt",
                      lambda s=src: g.load_source(s, club("x", comp, True)))
    for path in ("euro.json/master/2024/euro.json", "euro.json/master/2028/euro.json",
                 "worldcup.json/master/2022/worldcup.json", "worldcup.json/master/2026/worldcup.json",
                 "worldcup.json/master/2030/worldcup.json"):
        summarize(path, lambda p=path: g.load_source({"kind": "openfootball_json", "url": f"{raw}/{p}"},
                                                      nat("x", p)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--only", choices=["openligadb", "uefa", "football_data", "github", "config"])
    a = ap.parse_args()
    print(f"Quellen-Test, Stand {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")
    for name, fn in (("openligadb", probe_openligadb), ("uefa", probe_uefa),
                     ("football_data", probe_football_data), ("github", probe_github),
                     ("config", probe_config)):
        if a.only in (None, name):
            fn(a.quick)
    return 0


if __name__ == "__main__":
    sys.exit(main())
