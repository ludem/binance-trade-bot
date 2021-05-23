import collections
import random
import statistics
import sys
from datetime import datetime

from sqlalchemy.sql.functions import current_user

from binance_trade_bot.auto_trader import AutoTrader


class Strategy(AutoTrader):
    def initialize(self):
        super().initialize()
        self.initialize_current_coin()
        self.low_point_tick = 15
        self.high_point_tick = 60
        self.low_point_sell_signal_check = -1
        self.high_point_sell_signal_check = -1.5
        self.low_point_buy_signal_check = 0.2
        self.high_point_buy_signal_check = 0.4
        self.price_history = None
        self.is_in_save_mode = False
        self.hits = 0
        self.save_balance = None
        self.sell_threshold = 30
        self.buy_threshold = 15

    def scout(self):

        """
        Scout for potential jumps from the current coin to another coin
        """
        current_coin = self.db.get_current_coin()

        current_coin_price = self.manager.get_ticker_price(current_coin + self.config.BRIDGE)

        if self.price_history == None:
            self.logger.info("Initalizing price history")
            self.price_history = {}        
            for coin in self.config.SUPPORTED_COIN_LIST:
                coin_price = self.manager.get_ticker_price(coin + self.config.BRIDGE.symbol)     
                self.price_history[coin] = collections.deque(1000*[coin_price], 1000)

        for coin in self.config.SUPPORTED_COIN_LIST:
            price_history = self.price_history[coin]
            coin_price = self.manager.get_ticker_price(coin + self.config.BRIDGE.symbol)
            price_history.appendleft(coin_price)          

        low_point_price = self.price_history[current_coin.symbol][self.low_point_tick]
        high_point_price = self.price_history[current_coin.symbol][self.high_point_tick]
        low_point_velocity = (current_coin_price - low_point_price) / low_point_price * 100
        high_point_velocity = (current_coin_price - high_point_price) / high_point_price * 100

        low_point_sell_signal = low_point_velocity <= self.low_point_sell_signal_check
        high_point_sell_signal = high_point_velocity <= self.high_point_sell_signal_check
        low_point_buy_signal = low_point_velocity >= self.low_point_buy_signal_check
        high_point_buy_signal = high_point_velocity >= self.high_point_buy_signal_check

        if self.is_in_save_mode != True:            
            if low_point_sell_signal:
                self.hits += 5
            else:
                self.hits -= 5
            if high_point_sell_signal:
                self.hits += 10
            else:
                self.hits -= 10
        else:      
            if low_point_buy_signal:
                self.hits += 5
            else:
                self.hits -= 5
            if high_point_buy_signal:
                self.hits += 10
            else:
                self.hits -= 10

        if self.hits < 0:
            self.hits = 0


        if self.is_in_save_mode != True and self.hits >= self.sell_threshold:
            self.logger.info(f"{self.manager.datetime} Sell signal! Current Price {current_coin_price}. Low Point: Price {low_point_price} Velocity {low_point_velocity}%. High Point: Price {high_point_price}  Velocity {high_point_velocity}%")
            can_sell = False
            balance = self.manager.get_currency_balance(current_coin.symbol)

            if balance and balance * current_coin_price > self.manager.get_min_notional(
                current_coin.symbol, self.config.BRIDGE.symbol
            ):
                can_sell = True
            else:
                self.logger.info("Skipping sell")

            if can_sell and self.manager.sell_alt(current_coin, self.config.BRIDGE, current_coin_price) is None:
                self.logger.info("Couldn't sell, going back to scouting mode...")
            else:
                self.is_in_save_mode = True
                self.save_balance = balance
                self.hits = 0
        
        if self.is_in_save_mode == True:
            print(
                f"{datetime.now()} - CONSOLE - INFO - I am in safe mode looking for buy signal."
                f"Current coin: {current_coin + self.config.BRIDGE} ",
                end="\r",
            )           
            if self.hits >= self.buy_threshold:
                self.logger.info(f"{self.manager.datetime} Buy signal! Current Price {current_coin_price}. Low Point: Price {low_point_price} Velocity {low_point_velocity}%. High Point: Price {high_point_price}  Velocity {high_point_velocity}%")
                if self.manager.buy_alt(current_coin, self.config.BRIDGE, current_coin_price) != None:
                    self.is_in_save_mode = False
                    balance = self.manager.get_currency_balance(current_coin.symbol)
                    save_reward_percent = (balance - self.save_balance) / self.save_balance * 100
                    save_reward = balance - self.save_balance
                    self.logger.info(f"Save reward: {save_reward} ({save_reward_percent} %)")
                    self.hits = 0
                else:
                    self.logger.info("Could not buy. Waiting for next buy signal.")
                
        if self.is_in_save_mode != True:
            # Display on the console, the current coin+Bridge, so users can see *some* activity and not think the bot has
            # stopped. Not logging though to reduce log size.
            print(
                f"{datetime.now()} - CONSOLE - INFO - I am scouting the best trades. "
                f"Current coin: {current_coin + self.config.BRIDGE} ",
                end="\r",
            )

            if current_coin_price is None:
                self.logger.info("Skipping scouting... current coin {} not found".format(current_coin + self.config.BRIDGE))
                return

            self._jump_to_best_coin(current_coin, current_coin_price)

    def bridge_scout(self):
        current_coin = self.db.get_current_coin()
        if self.manager.get_currency_balance(current_coin.symbol) > self.manager.get_min_notional(
            current_coin.symbol, self.config.BRIDGE.symbol
        ):
            # Only scout if we don't have enough of the current coin
            return
        new_coin = super().bridge_scout()
        if new_coin is not None:
            self.db.set_current_coin(new_coin)

    def initialize_current_coin(self):
        """
        Decide what is the current coin, and set it up in the DB.
        """
        if self.db.get_current_coin() is None:
            current_coin_symbol = self.config.CURRENT_COIN_SYMBOL
            if not current_coin_symbol:
                current_coin_symbol = random.choice(self.config.SUPPORTED_COIN_LIST)

            self.logger.info(f"Setting initial coin to {current_coin_symbol}")

            if current_coin_symbol not in self.config.SUPPORTED_COIN_LIST:
                sys.exit("***\nERROR!\nSince there is no backup file, a proper coin name must be provided at init\n***")
            self.db.set_current_coin(current_coin_symbol)

            # if we don't have a configuration, we selected a coin at random... Buy it so we can start trading.
            if self.config.CURRENT_COIN_SYMBOL == "":
                current_coin = self.db.get_current_coin()
                self.logger.info(f"Purchasing {current_coin} to begin trading")
                self.manager.buy_alt(
                    current_coin, self.config.BRIDGE, self.manager.get_ticker_price(current_coin + self.config.BRIDGE)
                )
                self.logger.info("Ready to start trading")
