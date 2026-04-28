"""Demo fixture generator. Produces plausible-looking events with
moneyline + spread + total markets so the simulator works without a
live odds-feed integration. Deterministic via seed so a regression
test can reproduce a slate.

The generator picks teams at random from a small pool per sport and
draws odds + lines from sport-appropriate ranges. Final scores are
rolled with the spread/total in mind so the markets resolve in
believable ways (favorites cover ~52%, totals split roughly 50/50).
"""
from __future__ import annotations

import random
from dataclasses import dataclass


# Tiny team pools — enough variety for a few days of fixtures without
# needing a real data source. Future work: pull from a roster API.
_TEAM_POOL: dict[str, list[str]] = {
    "NBA": [
        "Lakers", "Celtics", "Warriors", "Bucks", "Nuggets", "Suns",
        "Heat", "76ers", "Knicks", "Mavericks", "Grizzlies", "Pelicans",
    ],
    "NFL": [
        "Chiefs", "49ers", "Eagles", "Cowboys", "Bills", "Ravens",
        "Bengals", "Lions", "Dolphins", "Packers", "Vikings", "Jets",
    ],
    "MLB": [
        "Dodgers", "Yankees", "Astros", "Braves", "Phillies", "Mets",
        "Cubs", "Red Sox", "Padres", "Mariners",
    ],
    "NHL": [
        "Rangers", "Bruins", "Avalanche", "Lightning", "Oilers",
        "Maple Leafs", "Stars", "Hurricanes",
    ],
}

_SPORT_LEAGUES: dict[str, str] = {
    "basketball": "NBA",
    "football": "NFL",
    "baseball": "MLB",
    "hockey": "NHL",
}

# Typical totals per sport — generator wobbles around these.
_TOTAL_BASELINE: dict[str, float] = {
    "basketball": 220.0,   # ~110 per team
    "football": 47.5,
    "baseball": 8.5,
    "hockey": 6.0,
}


@dataclass
class FixtureMarket:
    market_type: str
    selections: list[dict]


@dataclass
class FixtureEvent:
    sport: str
    league: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    markets: list[FixtureMarket]


def _draw_moneyline(home_advantage: float, rng: random.Random) -> tuple[int, int]:
    """Pick American moneyline odds for a game where `home_advantage`
    is the favorite skew (positive = home favored). Returns
    (home_odds, away_odds) totaling roughly -110/-110-ish vig."""
    # Translate advantage [-1, 1] into American odds. ±0.4 is a small
    # favorite (~-150), ±0.7 a heavy one (~-280).
    if home_advantage > 0:
        home = -int(110 + home_advantage * 350)
        away = int(95 + home_advantage * 320)
    else:
        away = int(110 + abs(home_advantage) * 350)
        home = -int(-95 - home_advantage * 320)  # double negation
    # Round to nearest 5 for realism.
    home = int(round(home / 5) * 5)
    away = int(round(away / 5) * 5)
    return home, away


def _draw_spread(home_advantage: float, sport: str, rng: random.Random) -> float:
    """Pick a spread line consistent with the moneyline. Negative =
    home favored by that many points."""
    if sport == "basketball":
        magnitude = abs(home_advantage) * 12
    elif sport == "football":
        magnitude = abs(home_advantage) * 9
    elif sport == "baseball":
        magnitude = 1.5 if abs(home_advantage) > 0.2 else 0  # MLB usually -1.5
    elif sport == "hockey":
        magnitude = 1.5 if abs(home_advantage) > 0.2 else 0
    else:
        magnitude = abs(home_advantage) * 5
    # Round to nearest 0.5, except baseball/hockey which use the
    # standard puck/run line of 1.5.
    if sport in ("baseball", "hockey"):
        line = 1.5
    else:
        line = max(0.5, round(magnitude * 2) / 2)
    return -line if home_advantage > 0 else line


def _generate_one_event(
    sport: str,
    teams: tuple[str, str],
    rng: random.Random,
    day: int,
) -> FixtureEvent:
    league = _SPORT_LEAGUES[sport]
    home, away = teams
    home_advantage = rng.uniform(-0.6, 0.6)

    home_ml, away_ml = _draw_moneyline(home_advantage, rng)
    spread = _draw_spread(home_advantage, sport, rng)
    total_baseline = _TOTAL_BASELINE[sport]
    total_line = round((total_baseline + rng.uniform(-12, 12)) * 2) / 2

    # Roll a final score. Each team scores around half the total, with
    # the favorite getting a bias proportional to home_advantage.
    half = total_baseline / 2
    bias = home_advantage * (half * 0.15)
    home_score = max(0, int(rng.gauss(half + bias, half * 0.20)))
    away_score = max(0, int(rng.gauss(half - bias, half * 0.20)))
    if sport in ("baseball", "hockey"):
        # Low-scoring sports — clamp closer to baseline.
        home_score = max(0, int(rng.gauss(total_baseline / 2 + bias, 1.5)))
        away_score = max(0, int(rng.gauss(total_baseline / 2 - bias, 1.5)))

    markets: list[FixtureMarket] = [
        FixtureMarket(
            market_type="moneyline",
            selections=[
                {"key": "home", "label": home, "odds": home_ml, "line": None},
                {"key": "away", "label": away, "odds": away_ml, "line": None},
            ],
        ),
        FixtureMarket(
            market_type="spread",
            selections=[
                # Convention: spread is from the home team's perspective.
                # Both sides priced ~ -110.
                {"key": "home", "label": home, "odds": -110, "line": spread},
                {"key": "away", "label": away, "odds": -110, "line": -spread},
            ],
        ),
        FixtureMarket(
            market_type="total",
            selections=[
                {"key": "over", "label": "Over", "odds": -110, "line": total_line},
                {"key": "under", "label": "Under", "odds": -110, "line": total_line},
            ],
        ),
    ]

    return FixtureEvent(
        sport=sport,
        league=league,
        home_team=home,
        away_team=away,
        home_score=home_score,
        away_score=away_score,
        markets=markets,
    )


def generate_day_slate(
    *,
    day: int,
    seed: int,
    games_per_sport: int = 2,
) -> list[FixtureEvent]:
    """Build a list of FixtureEvent objects for one day. Deterministic
    on `(seed, day)` — a regression test can reproduce the exact slate."""
    rng = random.Random((seed * 1000003) ^ day)
    events: list[FixtureEvent] = []
    for sport, league in _SPORT_LEAGUES.items():
        teams = list(_TEAM_POOL[league])
        rng.shuffle(teams)
        # Pair adjacent teams; cap to games_per_sport pairings.
        for i in range(games_per_sport):
            if len(teams) < 2:
                break
            home = teams.pop()
            away = teams.pop()
            events.append(_generate_one_event(sport, (home, away), rng, day))
    return events


def winner_keys_for_event(event: FixtureEvent) -> dict[str, str]:
    """Compute the `winner_key` for each market on an event from the
    final score. Returns a dict keyed by market_type."""
    home_score = event.home_score
    away_score = event.away_score
    out: dict[str, str] = {}

    # Moneyline: who won outright. NBA/NFL ties are vanishingly rare
    # but still possible in football — handle via PUSH.
    if home_score > away_score:
        out["moneyline"] = "home"
    elif away_score > home_score:
        out["moneyline"] = "away"
    else:
        out["moneyline"] = "PUSH"

    # Spread: did home cover. The home market's `line` is the spread
    # (negative = favored). Home covers when (home_score - away_score)
    # is greater than -line. Push when equal.
    spread_market = next(m for m in event.markets if m.market_type == "spread")
    home_line = spread_market.selections[0]["line"]
    diff = home_score - away_score
    if diff + home_line > 0:
        out["spread"] = "home"
    elif diff + home_line < 0:
        out["spread"] = "away"
    else:
        out["spread"] = "PUSH"

    # Total: over/under the line.
    total_market = next(m for m in event.markets if m.market_type == "total")
    total_line = total_market.selections[0]["line"]
    total_score = home_score + away_score
    if total_score > total_line:
        out["total"] = "over"
    elif total_score < total_line:
        out["total"] = "under"
    else:
        out["total"] = "PUSH"

    return out
