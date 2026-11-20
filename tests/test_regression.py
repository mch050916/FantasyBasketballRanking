import pandas as pd
from model import _regress_to_pool_mean


def test_regress_to_pool_mean():
    df = pd.DataFrame({
        "PLAYER_NAME": ["a", "b"], "MIN": [30.0, 20.0],
        "PTS_RATE": [30.0, 10.0], "PTS": [0.0, 0.0], "_F_PTS": [1.0, 1.0],
        "DD_RATE": [0.5, 0.0], "TD_RATE": [0.0, 0.0], "TECH_RATE": [0.1, 0.1],
        "_F_DD": [1.0, 1.0], "_F_TD": [1.0, 1.0], "_F_TECH": [1.0, 1.0],
        "_GPF": [1.0, 0.5], "_WMIN": [3000.0, 1000.0],
    })
    out = _regress_to_pool_mean(df, ["PTS"], minutes_k=1000, gp_shrink=0.5, pool_size=2)
    # pool mean PTS 20, GPF 0.75; reliabilities 0.75 and 0.5
    assert out["PTS_RATE"].tolist() == [27.5, 15.0]
    assert out["GP_FACTOR"].tolist() == [0.875, 0.625]
    assert out["PTS"].tolist() == [27.5 * 0.875, 15.0 * 0.625]
    assert out["DD"].tolist() == [0.5 * 0.875, 0.0]


def test_minutes_k_zero_leaves_rates_alone():
    df = pd.DataFrame({
        "PLAYER_NAME": ["a", "b"], "MIN": [30.0, 20.0],
        "PTS_RATE": [30.0, 10.0], "PTS": [0.0, 0.0], "_F_PTS": [1.0, 1.0],
        "DD_RATE": [0.0, 0.0], "TD_RATE": [0.0, 0.0], "TECH_RATE": [0.1, 0.1],
        "_F_DD": [1.0, 1.0], "_F_TD": [1.0, 1.0], "_F_TECH": [1.0, 1.0],
        "_GPF": [1.0, 0.5], "_WMIN": [3000.0, 0.0],
    })
    out = _regress_to_pool_mean(df, ["PTS"], minutes_k=0, gp_shrink=0.5, pool_size=2)
    assert out["PTS_RATE"].tolist() == [30.0, 10.0]
    assert out["GP_FACTOR"].tolist() == [0.875, 0.625]


def test_market_blend(tmp_path):
    from main import add_market_blend
    f = tmp_path / "m.csv"
    f.write_text("Player,Preseason ADP\nB Two,1.0\nA One,5.0\n")
    r = pd.DataFrame({"PLAYER_NAME": ["A One", "B Two", "C Three"], "RANK": [1, 2, 3]})
    out = add_market_blend(r, str(f))
    assert out["MARKET_RANK"].tolist() == [2.0, 1.0, 3.0]
    assert out["BLEND_RANK"].tolist() == [1, 1, 3]
    assert out["MARKET_GAP"].tolist() == [-1.0, 1.0, 0.0]
    assert add_market_blend(r, str(tmp_path / "missing.csv")) is r


def test_market_first_rows_skip_the_blend(tmp_path):
    from main import add_market_blend
    f = tmp_path / "m.csv"
    f.write_text("Player,Preseason ADP\nR One,1.0\nV One,2.0\n")
    board = pd.DataFrame({"PLAYER_NAME": ["V One", "V Two", "R One", "R Two"],
                          "BOARD_RANK": [1, 2, 3, 4]})
    out = add_market_blend(board, str(f), rank_col="BOARD_RANK",
                           market_first=pd.Series([False, False, True, True]))
    # market ranks: R One 1, V One 2, V Two and R Two tied last at 3.5.
    # scores: V One 1.5, V Two 2.75, R One 1 (market alone), R Two 4 (board alone)
    assert out["BLEND_RANK"].tolist() == [2, 3, 1, 4]


def test_rookie_scored_like_a_veteran_with_the_same_line():
    from config import LEAGUE_CONFIG
    from main import place_rookies
    from model import compute_g_scores
    cats = ["FGM", "FGA", "3PTM", "FTM", "PTS", "REB", "AST", "ST", "BLK", "TO", "PF", "DD", "TD", "TECH"]
    n = 140
    vets = pd.DataFrame({c: [1.0 + (i % 7) * 0.3 for i in range(n)] for c in cats})
    vets["FG%"] = 0.47
    vets["MIN"] = [30.0 - i * 0.1 for i in range(n)]
    vets["GP_FACTOR"] = 0.8
    vets["PLAYER_NAME"] = [f"v{i}" for i in range(n)]
    rookie = vets.iloc[[3]][cats + ["FG%", "MIN"]].copy()
    rookie["PLAYER_NAME"] = "rook"
    rookie["GP"] = 82 * 0.8          # own GP_FACTOR 0.8 = pool mean, so shrink is a no-op
    rookie["OVERALL_PICK"] = 1
    for c in cats:                   # rookie rows carry per-game rates
        rookie[c] = rookie[c] / 0.8
    placed = place_rookies(rookie, vets, {}, {}, LEAGUE_CONFIG)
    vet = compute_g_scores(vets, {}, {}, LEAGUE_CONFIG).set_index("PLAYER_NAME").loc["v3"]
    assert abs(placed.loc[0, "TOTAL_VALUE"] - vet["TOTAL_VALUE"]) < 1e-9
    assert placed.loc[0, "GP_FACTOR"] == 0.8
