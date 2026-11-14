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
