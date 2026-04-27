"""Verify per-result counters increment correctly on settle."""
from app import create_app
from app.config import Config
from app.models import GameSession
from app.services.games import StartRoundRequest, start_round, take_action
from app.services.sessions import create_from_template


class _TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test"


def _drive_to_completion(sess: GameSession) -> str:
    """Start a round and stand all the way to completion. Returns final state."""
    view = start_round(sess, StartRoundRequest(main_bet=10))
    guard = 0
    while view.state == "playing":
        action = "stand" if "stand" in view.legal_actions else view.legal_actions[0]
        view = take_action(sess, action)
        guard += 1
        assert guard < 12
    return view.state


def test_counters_sum_to_hands_played_across_seeds():
    """Across many seeds, wins + losses + pushes should equal hands_played
    (split hands count individually)."""
    app = create_app(_TestConfig())
    with app.app_context():
        for seed in range(1, 25):
            sess = create_from_template(
                template_id=None,
                starting_bankroll=500,
                player_seat=1,
                rules_overrides={
                    "seats": 1,
                    "min_bet": 5, "max_bet": 100, "bet_increment": 5,
                    "insurance_offered": False, "dealer_peeks": False,
                },
                seed=seed,
            )
            _drive_to_completion(sess)
            total = sess.wins + sess.losses + sess.pushes
            assert total == sess.hands_played, (
                f"seed {seed}: counters {total} != hands_played {sess.hands_played}"
            )
            # All counters non-negative.
            for n in (sess.wins, sess.losses, sess.pushes,
                      sess.player_blackjacks, sess.busts, sess.surrenders):
                assert n >= 0


def test_blackjack_counted_as_win_and_blackjack():
    """When the player gets a natural, both wins and player_blackjacks
    should bump."""
    app = create_app(_TestConfig())
    with app.app_context():
        # Sweep until we find a seed that hands the player a blackjack.
        found_bj = False
        for seed in range(1, 200):
            sess = create_from_template(
                template_id=None,
                starting_bankroll=500,
                player_seat=1,
                rules_overrides={
                    "seats": 1,
                    "min_bet": 5, "max_bet": 100, "bet_increment": 5,
                    "insurance_offered": False, "dealer_peeks": False,
                },
                seed=seed,
            )
            view = start_round(sess, StartRoundRequest(main_bet=10))
            if view.state != "complete":
                continue
            outcomes = view.result["outcomes"] if view.result else []
            if any(o["result"] == "blackjack" for o in outcomes):
                assert sess.player_blackjacks >= 1
                assert sess.wins >= 1
                found_bj = True
                break
        assert found_bj, "no blackjack found across 200 seeds"
