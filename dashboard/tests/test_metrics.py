from dashboard.metrics import compute_performance


def test_empty():
    p = compute_performance([])
    assert p.trades == 0
    assert p.win_rate == 0.0
    assert p.profit_factor == 0.0


def test_basic_win_loss():
    trades = [{"pnl": 100}, {"pnl": -50}, {"pnl": 50}, {"pnl": -25}]
    p = compute_performance(trades, starting_equity=1000)
    assert p.trades == 4
    assert p.wins == 2 and p.losses == 2
    assert p.win_rate == 50.0
    assert p.gross_profit == 150.0
    assert p.gross_loss == 75.0
    assert p.profit_factor == 2.0
    assert p.net_pnl == 75.0


def test_max_drawdown():
    # equity: 1000 -> 1100 -> 900 -> 1000 ; peak 1100, trough 900 => DD 200
    trades = [{"pnl": 100}, {"pnl": -200}, {"pnl": 100}]
    p = compute_performance(trades, starting_equity=1000)
    assert p.max_drawdown == 200.0
    assert p.max_drawdown_pct == 20.0


def test_all_wins_infinite_pf():
    p = compute_performance([{"pnl": 10}, {"pnl": 20}])
    assert p.profit_factor == float("inf")


def test_avg_rr():
    p = compute_performance([{"pnl": 30, "rr": 2.0}, {"pnl": -15, "rr": 1.0}])
    assert p.avg_rr == 1.5
