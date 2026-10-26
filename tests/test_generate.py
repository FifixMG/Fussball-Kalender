import os
import sys
import unittest
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import generate as g  # noqa: E402

CAL = {"id": "cl", "name": "Champions League", "tag": "CL", "european": True}

TXT = """= UEFA Champions League 2025/26

▪ League, Matchday 1
  Tue Sep 16 2025
    18:45  Athletic Club (ESP)     v Arsenal FC (ENG)         0-2 (0-0)
    21:00  Real Madrid CF (ESP)    v Olympique de Marseille (FRA)  2-1 (1-1)
           Paris Saint-Germain FC (FRA) v Atalanta BC (ITA)        4-0 (2-0)
  Wed Sep 17
    21:00  FC Bayern München (GER) v Chelsea FC (ENG)

▪ Finals, Final
  Sat May 30
    18:00  Paris Saint-Germain FC (FRA) v Arsenal FC (ENG)         4-3 pen. 1-1 a.e.t. (1-1, 0-1)
"""

CFG = {
    "core": [["Paris Saint-Germain", "PSG"], ["FC Barcelona", "Barca"], ["Real Madrid"], ["Bayern"]],
    "strong": [["Arsenal"], ["Internazionale", "Inter Milan"], ["Atletico de Madrid"]],
    "national_strong": ["Spain", "France", "Argentina"],
}


def mk(home, away, rnd="", knockout=False, european=True, kind="club"):
    return g.Match("X", "x", kind, european, "X", rnd, date(2026, 1, 1), None,
                   home, away, home, away, knockout=knockout)


class Parser(unittest.TestCase):
    def test_txt_times_and_year(self):
        ms = g.parse_openfootball_txt(TXT.encode(), CAL, {"tz": "Europe/Berlin"})
        self.assertEqual(len(ms), 5)
        self.assertEqual(ms[0].home, "Athletic Club")
        self.assertEqual(ms[0].start, datetime(2025, 9, 16, 16, 45, tzinfo=timezone.utc))  # CEST
        self.assertEqual(ms[2].start, datetime(2025, 9, 16, 19, 0, tzinfo=timezone.utc))   # Zeit uebernommen
        self.assertEqual(ms[3].day, date(2025, 9, 17))
        self.assertIsNone(ms[3].result)
        self.assertEqual(ms[4].day, date(2026, 5, 30))
        self.assertTrue(ms[4].knockout)
        self.assertFalse(ms[0].knockout)

    def test_json_time_formats(self):
        tz = g.ZoneInfo("Europe/Berlin")
        d = date(2026, 6, 11)
        self.assertEqual(g.to_utc(d, "13:00 UTC-6", tz), datetime(2026, 6, 11, 19, 0, tzinfo=timezone.utc))
        self.assertEqual(g.to_utc(d, "20:30", tz), datetime(2026, 6, 11, 18, 30, tzinfo=timezone.utc))
        self.assertIsNone(g.to_utc(d, None, tz))

    def test_score_shapes(self):
        self.assertEqual(g.result_from_score([2, 1]), "2-1")
        self.assertEqual(g.result_from_score({"ft": [0, 0], "et": [1, 0]}), "0-0 n.V. 1-0")
        self.assertIsNone(g.result_from_score(None))
        self.assertIsNone(g.result_from_score({"ht": [0, 0]}))

    def test_football_data(self):
        raw = (b'{"matches":[{"utcDate":"2026-11-04T20:00:00Z","stage":"LEAGUE_STAGE",'
               b'"homeTeam":{"name":"FC Bayern M\xc3\xbcnchen","shortName":"Bayern"},'
               b'"awayTeam":{"name":null,"shortName":null},'
               b'"score":{"fullTime":{"home":null,"away":null}}}]}')
        ms = g.parse_football_data(raw, CAL, {})
        self.assertEqual((ms[0].home, ms[0].away, ms[0].result), ("Bayern", "TBD", None))


OLDB = b"""[
 {"matchID": 1, "matchDateTime": "2026-11-04T21:00:00", "matchDateTimeUTC": "2026-11-04T20:00:00Z",
  "group": {"groupName": "4. Spieltag"},
  "team1": {"teamName": "FC Bayern M\xc3\xbcnchen", "shortName": "Bayern"},
  "team2": {"teamName": "Paris Saint-Germain", "shortName": "PSG"},
  "matchIsFinished": false, "matchResults": [], "location": null},
 {"matchID": 2, "matchDateTime": "2026-12-08T00:00:00", "matchDateTimeUTC": "2026-12-07T23:00:00Z",
  "group": {"groupName": "6. Spieltag"},
  "team1": {"teamName": "FC Barcelona", "shortName": "Bar\xc3\xa7a"},
  "team2": {"teamName": "Club Brugge", "shortName": "Brugge"},
  "matchIsFinished": false, "matchResults": [], "location": {"locationCity": "Barcelona", "locationStadium": null}},
 {"matchID": 3, "matchDateTime": "2026-09-08T21:00:00", "matchDateTimeUTC": "2026-09-08T19:00:00Z",
  "group": {"groupName": "Halbfinale"},
  "team1": {"teamName": "Real Madrid", "shortName": "Real"},
  "team2": {"teamName": "Inter Mailand", "shortName": "Inter"},
  "matchIsFinished": true,
  "matchResults": [{"resultTypeID": 1, "pointsTeam1": 1, "pointsTeam2": 0},
                   {"resultTypeID": 2, "pointsTeam1": 2, "pointsTeam2": 1}]}
]"""

UEFA = b"""[
 {"id": "1", "status": "UPCOMING", "competition": {"metaData": {"name": "UEFA Champions League"}},
  "kickOffTime": {"dateTime": "2026-11-04T20:00:00Z"},
  "homeTeam": {"internationalName": "Bayern M\xc3\xbcnchen"}, "awayTeam": {"internationalName": "Paris"},
  "matchday": {"longName": "Matchday 4"}, "round": {"phase": "LEAGUE"}},
 {"id": "2", "status": "FINISHED", "competition": {"metaData": {"name": "UEFA Champions League"}},
  "kickOffTime": {"dateTime": "2026-09-08T19:00:00Z"},
  "homeTeam": {"internationalName": "Real Madrid"}, "awayTeam": {"internationalName": "Barcelona"},
  "score": {"total": {"home": 2, "away": 2}}, "matchday": {"longName": "Final"}, "round": {"phase": "KNOCKOUT"}}
]"""


class NewSources(unittest.TestCase):
    def test_openligadb(self):
        ms = g.parse_openligadb(OLDB, CAL, {})
        self.assertEqual(len(ms), 3)
        self.assertEqual(ms[0].start, datetime(2026, 11, 4, 20, 0, tzinfo=timezone.utc))
        self.assertIsNone(ms[1].start)                       # 00:00 Ortszeit = offen
        self.assertEqual(ms[1].day, date(2026, 12, 8))       # Ortsdatum, nicht UTC-Vortag
        self.assertEqual(ms[1].venue, "Barcelona")
        self.assertEqual(ms[2].result, "2-1")                # Endergebnis, nicht Halbzeit
        self.assertTrue(ms[2].knockout)
        self.assertFalse(ms[0].knockout)
        r = g.TopRules(CFG)
        self.assertEqual(r.score(ms[0]), 3)
        self.assertEqual(r.score(ms[1]), 1)                  # Barca via shortName "Barca"

    def test_uefa(self):
        ms = g.parse_uefa(UEFA, CAL, {"expect": "champions league"})
        self.assertEqual((ms[0].home, ms[0].away, ms[0].result), ("Bayern München", "Paris", None))
        self.assertEqual(ms[1].result, "2-2")
        self.assertTrue(ms[1].knockout)
        with self.assertRaises(g.SourceUnavailable):
            g.parse_uefa(UEFA, CAL, {"expect": "europa league"})


class Collect(unittest.TestCase):
    def setUp(self):
        self.orig = g.load_source

    def tearDown(self):
        g.load_source = self.orig

    def _fake(self, table):
        def fake(src, cal):
            v = table[src["n"]]
            if isinstance(v, Exception):
                raise v
            return v
        g.load_source = fake

    def test_min_matches_and_fallback(self):
        a = [mk("A", "B")] * 2
        b = [mk("C", "D")] * 5
        self._fake({1: g.SourceUnavailable("404"), 2: a, 3: b, 4: [mk("X", "Y")] * 9})
        cal = {"id": "c", "sources": [{"kind": "fake", "n": 1}, {"kind": "fake", "n": 2, "min_matches": 3}, {"kind": "fake", "n": 3, "min_matches": 3}, {"kind": "fake", "n": 4}]}
        self.assertEqual(len(g.collect(cal, date(2000, 1, 1))), 5)   # Quelle 3 reicht, 4 wird nicht gefragt

    def test_best_when_none_complete(self):
        self._fake({1: [mk("A", "B")] * 2, 2: ConnectionError("down"), 3: [mk("A", "B")] * 3})
        cal = {"id": "c", "sources": [{"kind": "fake", "n": 1, "min_matches": 9}, {"kind": "fake", "n": 2}, {"kind": "fake", "n": 3, "min_matches": 9}]}
        self.assertEqual(len(g.collect(cal, date(2000, 1, 1))), 3)

    def test_merge_dedup(self):
        x = mk("Deutschland", "Spanien")
        y = mk("Spanien", "Deutschland")          # gleiche Paarung, anderer Heim-Eintrag
        y.start = datetime(2026, 1, 1, 20, tzinfo=timezone.utc)
        self._fake({1: [x, mk("Frankreich", "Italien")], 2: [y]})
        out = g.collect({"id": "c", "merge": True, "sources": [{"kind": "fake", "n": 1}, {"kind": "fake", "n": 2}]}, date(2000, 1, 1))
        self.assertEqual(len(out), 2)
        self.assertTrue(any(m.start for m in out))  # Eintrag mit Uhrzeit gewinnt


class RealConfig(unittest.TestCase):
    """Regeln aus der echten config.toml mit Namen, wie die Probe sie geliefert hat."""

    def setUp(self):
        import tomllib
        path = os.path.join(os.path.dirname(__file__), "..", "config.toml")
        with open(path, "rb") as f:
            self.cfg = tomllib.load(f)
        self.r = g.TopRules(self.cfg["top"])

    def s(self, home, away, kind="club", rnd="", ko=False):
        m = mk(home, away, rnd, ko, kind == "club", kind)
        return self.r.score(m)

    def test_uefa_short_names(self):
        self.assertEqual(self.s("Paris|PSG", "Barcelona|BAR"), 3)
        self.assertEqual(self.s("Bayern München|BAY", "Atleti|ATM"), 2)
        self.assertEqual(self.s("Real Madrid|RMA", "Milan|MIL"), 2)
        self.assertEqual(self.s("Barcelona|BAR", "Man Utd|MUN"), 2)

    def test_exact_alias_no_false_hits(self):
        self.assertEqual(self.s("Espanyol Barcelona", "Mainz"), 0)       # OpenLigaDB-Name
        self.assertEqual(self.s("Paris FC", "Lens"), 0)                   # nicht PSG
        self.assertEqual(self.s("Real Madrid", "Inter Miami"), 1)        # "=Inter" exakt

    def test_openligadb_german_names(self):
        self.assertEqual(self.s("Italien", "Frankreich", "national"), 2)
        self.assertEqual(self.s("Serbien", "Deutschland", "national"), 0)
        self.assertEqual(self.s("Türki̇ye", "Belgium", "national"), 0)

    def test_config_is_consistent(self):
        ids = [c["id"] for c in self.cfg["calendars"]]
        self.assertEqual(len(ids), len(set(ids)))
        for c in self.cfg["calendars"]:
            if c.get("merge"):
                flags = [bool(s.get("fallback")) for s in c["sources"]]
                self.assertEqual(flags, sorted(flags), f"{c['id']}: fallback-Quellen ans Ende")


class Phases(unittest.TestCase):
    def test_filter(self):
        a, b, c = mk("A", "B", "Matchday 4"), mk("C", "D", "Third qualifying round"), mk("E", "F", "Final")
        a.phase, b.phase, c.phase = "LEAGUE", "QUALIFYING", "TOURNAMENT | KNOCKOUT"
        self.assertEqual(g.phase_filter([a, b, c], {"exclude_phases": ["qualif"]}), [a, c])
        self.assertEqual(g.phase_filter([a, b, c], {"only_phases": ["qualif"]}), [b])
        self.assertEqual(g.phase_filter([a, b, c], {}), [a, b, c])

    def test_uefa_phase_and_knockout(self):
        raw = (b'[{"kickOffTime":{"dateTime":"2027-03-09T20:00:00Z"},'
               b'"homeTeam":{"internationalName":"Paris","teamCode":"PSG"},'
               b'"awayTeam":{"internationalName":"Arsenal"},'
               b'"round":{"phase":"KNOCKOUT","metaData":{"name":"Round of 16"}},'
               b'"matchday":{"longName":"Round of 16"}}]')
        m = g.parse_uefa(raw, CAL, {})[0]
        self.assertTrue(m.knockout)
        self.assertIn("KNOCKOUT", m.phase)
        self.assertEqual(m.home_key, "Paris|PSG")

    def test_uefa_real_phase_strings(self):
        # Phasen exakt wie im Quellen-Test vom 2026-10-26 gesehen
        def one(phase, name, rnd):
            raw = ('[{"kickOffTime":{"dateTime":"2027-02-17T20:00:00Z"},'
                   '"homeTeam":{"internationalName":"Barcelona"},"awayTeam":{"internationalName":"Brugge"},'
                   '"round":{"phase":"%s","mode":"%s","metaData":{"name":"%s"}},'
                   '"matchday":{"phase":"%s","longName":"%s"}}]' % (phase, name, rnd, phase, rnd)).encode()
            return g.parse_uefa(raw, CAL, {})[0]
        league = one("TOURNAMENT", "GROUP", "League Phase")
        quali = one("QUALIFYING", "KNOCK_OUT", "Play-Offs")
        ko = one("TOURNAMENT", "KNOCK_OUT", "Knockout Phase Play-offs")
        self.assertFalse(league.knockout)
        self.assertTrue(ko.knockout)
        self.assertEqual(g.phase_filter([league, quali, ko], {"exclude_phases": ["qualif", "prelim"]}), [league, ko])
        rules = g.TopRules({**CFG, "core": CFG["core"] + [["=Barcelona"]]})
        self.assertEqual(rules.score(ko), 2)      # CL-K.o. mit Kern-Verein = Stufe 2
        self.assertEqual(rules.score(league), 1)  # Ligaphase gegen schwachen Gegner = Stufe 1


class MergeFallback(unittest.TestCase):
    def setUp(self):
        self.orig = g.load_source

    def tearDown(self):
        g.load_source = self.orig

    def test_fallback_only_if_empty(self):
        calls = []

        def fake(src, cal):
            calls.append(src["n"])
            return {1: [mk("Spain", "France")], 2: [], 3: [mk("Spanien", "Frankreich")]}[src["n"]]
        g.load_source = fake
        cal = {"id": "c", "merge": True, "sources": [{"kind": "f", "n": 1}, {"kind": "f", "n": 3, "fallback": True}]}
        self.assertEqual(len(g.collect(cal, date(2000, 1, 1))), 1)
        self.assertEqual(calls, [1])                       # Fallback nicht abgefragt
        calls.clear()
        cal["sources"][0]["n"] = 2                         # Primaerquelle leer
        self.assertEqual(len(g.collect(cal, date(2000, 1, 1))), 1)
        self.assertEqual(calls, [2, 3])


class Rules(unittest.TestCase):
    def setUp(self):
        self.r = g.TopRules(CFG)

    def test_core_vs_core(self):
        self.assertEqual(self.r.score(mk("Real Madrid CF", "FC Barcelona")), 3)
        self.assertEqual(self.r.score(mk("Paris Saint-Germain FC", "FC Bayern München")), 3)

    def test_core_vs_strong(self):
        self.assertEqual(self.r.score(mk("Arsenal FC", "Real Madrid CF")), 2)
        self.assertEqual(self.r.score(mk("Club Atlético de Madrid", "FC Bayern München")), 2)

    def test_core_vs_weak(self):
        self.assertEqual(self.r.score(mk("FC Bayern München", "Heidenheim")), 1)
        self.assertEqual(self.r.score(mk("Mainz", "Heidenheim")), 0)

    def test_knockout_european(self):
        self.assertEqual(self.r.score(mk("Real Madrid", "Benfica", "Quarter-final", True)), 2)
        self.assertEqual(self.r.score(mk("Inter Milan", "Arsenal", "Round of 16", True)), 2)
        self.assertEqual(self.r.score(mk("Inter Milan", "Arsenal", "League, Matchday 3", False)), 0)

    def test_no_false_positive_bayer(self):
        self.assertEqual(self.r.score(mk("Bayer 04 Leverkusen", "Mainz")), 0)

    def test_no_false_positive_espanyol(self):
        self.assertEqual(self.r.score(mk("RCD Espanyol de Barcelona", "Real Madrid CF")), 1)
        self.assertEqual(self.r.score(mk("Barça", "Real Madrid")), 3)

    def test_national(self):
        self.assertEqual(self.r.score(mk("Spain", "France", "Matchday 3", False, False, "national")), 2)
        self.assertEqual(self.r.score(mk("Spain", "Peru", "Final", True, False, "national")), 3)
        self.assertEqual(self.r.score(mk("Peru", "Chile", "Matchday 1", False, False, "national")), 0)
        # Viertelfinale enthaelt "final", ist aber keine Stufe 3
        self.assertEqual(self.r.score(mk("W1", "W2", "Quarter-finals", True, False, "national")), 0)
        self.assertEqual(self.r.score(mk("W1", "W2", "Semi-finals", True, False, "national")), 3)


class Ics(unittest.TestCase):
    def test_fold_and_escape(self):
        line = "SUMMARY:" + "ä" * 60
        folded = g.fold(line)
        for part in folded.split("\r\n"):
            self.assertLessEqual(len(part.encode()), 75)
        self.assertEqual(folded.replace("\r\n ", ""), line)
        self.assertEqual(g.esc("a,b;c\nd"), "a\\,b\\;c\\nd")

    def test_build(self):
        m = g.parse_openfootball_txt(TXT.encode(), CAL, {})[0]
        ics = g.build_ics("Test", [m], datetime(2026, 1, 1, tzinfo=timezone.utc), True)
        self.assertTrue(ics.startswith("BEGIN:VCALENDAR\r\n"))
        self.assertIn("DTSTART:20250916T164500Z", ics)
        self.assertIn("SUMMARY:[CL] Athletic Club - Arsenal FC", ics)
        self.assertTrue(ics.endswith("END:VCALENDAR\r\n"))


if __name__ == "__main__":
    unittest.main()
