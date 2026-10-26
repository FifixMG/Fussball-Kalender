# Fussball-Kalender

Erzeugt ICS-Feeds (Bundesliga, La Liga, Ligue 1, Champions League, Europa League,
Laenderspiele, EM, WM und "Top-Spiele") und veroeffentlicht sie per GitHub Pages.
Nur Python-Standardbibliothek, kein Tracking, keine externen Ressourcen auf der Index-Seite.

## Einrichten

1. Repo auf GitHub anlegen (muss oeffentlich sein, Pages aus privaten Repos braucht einen Bezahlplan), Dateien pushen auf `main`.
2. Settings > Pages > Source: **GitHub Actions**.
3. Optional fuer Champions League / Europa League: kostenlosen API-Key bei football-data.org holen
   und als Secret `FOOTBALL_DATA_TOKEN` hinterlegen (Settings > Secrets and variables > Actions).
4. Actions > "Kalender bauen und veroeffentlichen" > Run workflow.
5. Auf dem Handy in ICSx5 jede gewuenschte URL aus `https://<user>.github.io/<repo>/` abonnieren,
   z.B. `top-spiele.ics`, `champions-league.ics`. Je Feed ein eigener Kalender, in Fossify ein- und ausblendbar.

## Filter

- Wettbewerbs-Filter = eigene Kalender (je eine `.ics`).
- Top-Spiele = `top-spiele.ics`, Regeln in `config.toml` unter `[top]`:
  - Stufe 3: Kern-Verein gegen Kern-Verein (z.B. Clasico, PSG gegen Bayern); WM/EM Halbfinale und Finale
  - Stufe 2: Kern-Verein gegen starken Gegner; K.o.-Spiele in CL/EL mit Kern-Verein; starker gegen starken Gegner in CL/EL-K.o.
  - Stufe 1: jedes andere Spiel eines Kern-Vereins (mit `min_score = 1` aktivierbar)

## Quellen (Stand 2026-10-26)

Reihenfolge pro Kalender in `config.toml`. Die erste Quelle mit genug Spielen (`min_matches`) gewinnt.

Ergebnisse des Quellen-Tests vom 2026-10-26 (`probe_sources.py`, Saison 2026/27):

| Kalender | Quellen (Reihenfolge) | Test 2026/27 |
|---|---|---|
| Bundesliga | OpenLigaDB `bl1`, openfootball | `bl1`: 306 Spiele, 100 % mit Uhrzeit |
| La Liga | OpenLigaDB `la1`, openfootball | `la1`: 380 Spiele, 99 % mit Uhrzeit |
| Ligue 1 | football-data.org `FL1` (Token), openfootball | nur openfootball getestet, meist ohne Uhrzeit |
| Champions League | UEFA-API ID 1, OpenLigaDB `ucl`, `ucl2026`, football-data.org | UEFA: 234 inkl. Quali; `ucl`: 144; `ucl2026`: nur 32 |
| Europa League | UEFA-API ID 14, OpenLigaDB `uel2026` | UEFA: 224 inkl. Quali; `uel2026`: 144 |
| Laenderspiele | UEFA Nations League (2014), EM-Quali (3), WM-Quali (17); Fallback OpenLigaDB `nla` + `DFBN` | UEFA NL: 156; `nla`: 48; `DFBN`: 6; `unl`: 0 |
| EM / WM | UEFA-API (3 / 17), openfootball | Turniere 2028/2030 noch ohne echte Paarungen |

Historisch (3 Jahre zurueck) lieferten UEFA-API, OpenLigaDB und openfootball fuer CL/EL/EM/WM vollstaendige Saisons.
UEFA-competitionIds laut API: 1 CL, 3 EM, 14 EL, 17 WM, 2014 Nations League, 2019 Conference League.

- **OpenLigaDB**: ODbL, ohne Key. Ligen ausser `bl1` pflegt die Community, Vollstaendigkeit schwankt.
- **UEFA-API**: inoffiziell (Frontend-API von uefa.com), ohne Key. Kann sich jederzeit aendern.
- **football-data.org**: Key noetig. Free-Tier laut Drittquelle: CL, BL, La Liga, Ligue 1, WM, EM, aber **keine EL**.
- **openfootball**: Public Domain, Liga-Spiele meist ohne Uhrzeit, CL/EL 2026-27 fehlt.

Ausfaelle einzelner Quellen (404, Netzfehler) werden uebersprungen. Liefert ein Kalender mit
`required = true` gar keine Daten, bricht der Job ab, damit der zuletzt veroeffentlichte Stand online bleibt.

## Quellen pruefen

    python probe_sources.py           # aktuelle Saison + 3 Jahre zurueck
    python probe_sources.py --quick   # nur aktuelle Saison

Oder in GitHub: Actions > "Quellen pruefen" > Run workflow. Das Ergebnis steht in der Job-Zusammenfassung.
Die Ausgabe listet auch die UEFA-competitionIds mit Namen. Damit laesst sich die EL-ID klaeren.

Hinweise: Spiele ohne Uhrzeit in den Daten werden als ganztaegige Termine eingetragen.
Zeiten aus openfootball gelten als Ortszeit der Liga (Config `tz`), sie werden nach UTC umgerechnet.

## Lokal testen

    python -I -m unittest discover -s tests
    python generate.py --config config.toml --out site
