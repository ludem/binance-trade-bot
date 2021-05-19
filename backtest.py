import json
from datetime import datetime

from binance_trade_bot import backtest

shib_and_shit_added = False
rlc_added = False
coins = None

if __name__ == "__main__":
    history = []
    for manager in backtest(datetime(2021, 4, 1), datetime(2021, 5, 18), yield_interval=60):
        btc_value = manager.collate_coins("BTC")
        if coins is None:
            coins = manager.config.SUPPORTED_COIN_LIST[:]
        bridge_value = manager.collate_coins(manager.config.BRIDGE.symbol)
        history.append(
            (btc_value, bridge_value, manager.datetime.strftime("%d %b %Y %H:%M:%S"), manager.balances.copy())
        )
        btc_diff = round((btc_value - history[0][0]) / history[0][0] * 100, 3)
        bridge_diff = round((bridge_value - history[0][1]) / history[0][1] * 100, 3)
        # if not shib_and_shit_added and manager.datetime >= datetime(2021, 5, 13):
        #     coins += ["SHIB", "NANO", "ICP"]
        #     manager.set_coins(coins)
        #     shib_and_shit_added = True
        # if not rlc_added and manager.datetime >= datetime(2021, 5, 17):
        #     coins += ["RLC"]
        #     manager.set_coins(coins)
        #     rlc_added = True
        print("------")
        print("TIME:", manager.datetime)
        print("BALANCES:", manager.balances)
        print("BTC VALUE:", btc_value, f"({btc_diff}%)")
        print(f"{manager.config.BRIDGE.symbol} VALUE:", bridge_value, f"({bridge_diff}%)")
        print("------")
    with open("backtest_history.txt", "w") as outfile:
        json.dump(history, outfile)
