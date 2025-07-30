import json
import threading
import time
from datetime import datetime, timedelta
import importlib

from binance_api import get_historical_data, create_market_order, get_position, set_leverage_and_margin_mode
from database import log_trade, update_trade
from utils.helpers import get_available_strategies

BOT_STATE_FILE = "bot_state.json"
_running_bot_threads = {}

def _parse_timeframe_to_seconds(timeframe: str) -> int:
    """Zaman aralığı dizesini (ör. '1m', '5m', '1h') saniyeye çevirir."""
    if not isinstance(timeframe, str) or len(timeframe) < 2:
        return 60  # Varsayılan 1 dakika

    unit = timeframe[-1]
    try:
        value = int(timeframe[:-1])
    except (ValueError, TypeError):
        return 60  # Varsayılan 1 dakika

    if unit == 'm':
        return value * 60
    elif unit == 'h':
        return value * 3600
    elif unit == 'd':
        return value * 86400
    else:
        # Tanınmayan birim varsa dakika olduğunu varsay
        try:
            return int(timeframe) * 60
        except ValueError:
            return 60 # Varsayılan

class Bot(threading.Thread):
    def __init__(self, bot_id, user_id, symbol, strategy_instance, settings, client):
        super().__init__()
        self.bot_id = bot_id
        self.user_id = user_id
        self.symbol = symbol
        self.strategy = strategy_instance
        self.settings = settings
        self.client = client
        self.is_running = True
        self.active_trade_id = None
        self.daemon = True

    def run(self):
        """Bot'un ana çalışma döngüsü."""
        timeframe = self.settings.get('timeframe', '1m')
        print(f"Bot {self.bot_id}, {timeframe} periyotları ile başlatıldı.")

        while self.is_running:
            try:
                # --- Ana İşlem Mantığı ---
                df = get_historical_data(self.client, self.symbol, timeframe=timeframe, limit=100)
                if df is None:
                    print(f"[{self.bot_id}] Veri çekilemedi, döngü atlanıyor.")
                    time.sleep(60)  # Veri alınamazsa tekrar denemeden önce 1 dakika bekle
                    continue

                df_with_signals = self.strategy.generate_signals(df)
                last_signal = df_with_signals['signal'].iloc[-1]
                position, unrealized_pnl = get_position(self.client, self.symbol)
                
                print(f"[{self.bot_id}] Son sinyal: {last_signal}, Pozisyon: {'Var' if position else 'Yok'}")

                # --- Pozisyon Açma Mantığı (İşlem Yönü Kontrolü ile) ---
                trade_direction = self.settings.get('direction', 'Her İkisi de')
                
                can_long = trade_direction in ["Long", "Her İkisi de"]
                can_short = trade_direction in ["Short", "Her İkisi de"]

                should_open_long = position is None and last_signal == 1 and can_long
                should_open_short = position is None and last_signal == -1 and can_short

                if should_open_long or should_open_short:
                    # Kaldıraç ve Marjin Modunu Ayarla
                    leverage = self.settings.get('leverage', 10) # Varsayılan 10x
                    set_leverage_and_margin_mode(self.client, self.symbol, leverage, 'ISOLATED')

                    side = 'buy' if should_open_long else 'sell'
                    entry_price = df['close'].iloc[-1]
                    amount = self.settings['balance'] / entry_price
                    tp = self.settings.get('take_profit')
                    sl = self.settings.get('stop_loss')

                    if side == 'buy':
                        tp_price = entry_price * (1 + tp / 100) if tp else None
                        sl_price = entry_price * (1 - sl / 100) if sl else None
                    else: # short
                        tp_price = entry_price * (1 - tp / 100) if tp else None
                        sl_price = entry_price * (1 + sl / 100) if sl else None
                    
                    order, msg = create_market_order(self.client, self.symbol, side, round(amount, 3), tp_price, sl_price)
                    if order:
                        log_side = 'long' if side == 'buy' else 'short'
                        self.active_trade_id = log_trade(self.user_id, self.bot_id, self.symbol, log_side, amount, entry_price)
                
                elif position is not None and self.active_trade_id is not None:
                    pos_side = 'long' if float(position['contracts']) > 0 else 'short'
                    if (pos_side == 'long' and last_signal == -1) or (pos_side == 'short' and last_signal == 1):
                        # Pozisyonu kapatmadan hemen önce PNL'i al
                        _, realized_pnl_on_close = get_position(self.client, self.symbol)
                        
                        close_side = 'sell' if pos_side == 'long' else 'buy'
                        amount = abs(float(position['contracts']))
                        order, msg = create_market_order(self.client, self.symbol, close_side, amount)
                        
                        if order:
                            exit_price = df['close'].iloc[-1]
                            entry_price = float(position['entryPrice'])
                            
                            # Yüzdesel PNL hesaplaması
                            pnl_percentage = ((exit_price - entry_price) / entry_price) * 100 * self.settings.get('leverage', 1)
                            if pos_side == 'short':
                                pnl_percentage = -pnl_percentage
                            
                            # Gerçekleşen PNL'i (USD cinsinden) veritabanına kaydet
                            update_trade(self.active_trade_id, exit_price, pnl_percentage, realized_pnl_on_close or 0)
                            self.active_trade_id = None
            except Exception as e:
                print(f"[{self.bot_id}] Bot döngüsünde hata: {e}")

            # --- Bekleme Mantığı ---
            if not self.is_running: break
            
            try:
                sleep_duration = _parse_timeframe_to_seconds(timeframe)
                print(f"[{self.bot_id}] Kontrol tamamlandı. Sonraki kontrol {sleep_duration} saniye içinde.")
                
                # Durdurma sinyalini her saniye kontrol ederek bekle
                for _ in range(sleep_duration):
                    if not self.is_running:
                        break
                    time.sleep(1)
            except Exception as e:
                print(f"[{self.bot_id}] Bekleme mantığında hata: {e}. 1 dakika bekleniyor.")
                time.sleep(60)

    def stop(self):
        self.is_running = False
        print(f"Bot {self.bot_id} stopping...")

def _load_bot_state():
    try:
        with open(BOT_STATE_FILE, "r") as f: return json.load(f)
    except FileNotFoundError: return {}

def _save_bot_state(state):
    with open(BOT_STATE_FILE, "w") as f: json.dump(state, f, indent=4)

def start_new_bot(bot_id, user_id, symbol, strategy_name, settings, client):
    configs = _load_bot_state()
    # Bot ID'leri artık kullanıcıya özel olmalı
    user_specific_bot_id = f"{user_id}_{bot_id}"

    if user_specific_bot_id in configs:
        print(f"Bot '{user_specific_bot_id}' already configured for this user.")
        return False
    
    available_strategies = get_available_strategies()
    strategy_class = available_strategies.get(strategy_name)
    if not strategy_class:
        print(f"Strategy '{strategy_name}' not found.")
        return False

    bot_thread = Bot(user_specific_bot_id, user_id, symbol, strategy_class(), settings, client)
    bot_thread.start()
    _running_bot_threads[user_specific_bot_id] = bot_thread
    
    configs[user_specific_bot_id] = {
        "user_id": user_id, 
        "symbol": symbol, 
        "strategy": strategy_name, 
        "settings": settings
    }
    _save_bot_state(configs)
    print(f"Bot '{user_specific_bot_id}' started and configured for user {user_id}.")
    return True

def stop_bot(bot_id):
    configs = _load_bot_state()
    if bot_id in _running_bot_threads:
        _running_bot_threads[bot_id].stop()
        _running_bot_threads[bot_id].join()
        del _running_bot_threads[bot_id]
    
    if bot_id in configs:
        del configs[bot_id]
        _save_bot_state(configs)
        print(f"Bot '{bot_id}' stopped and configuration removed.")
        return True
    return False

def get_active_bot_configs(user_id):
    """Belirli bir kullanıcı için aktif bot yapılandırmalarını döndürür."""
    all_configs = _load_bot_state()
    user_configs = {
        bot_id: config for bot_id, config in all_configs.items()
        if config.get('user_id') == user_id
    }
    return user_configs

def start_all_bots_from_config(user_id, client):
    """Load all bot configs for a specific user and start them."""
    print(f"Starting all configured bots for user {user_id}...")
    configs = get_active_bot_configs(user_id)
    for bot_id, config in configs.items():
        if bot_id not in _running_bot_threads:
            available_strategies = get_available_strategies()
            strategy_class = available_strategies.get(config['strategy'])
            if strategy_class:
                # user_id'yi Bot yapıcısına iletiyoruz
                bot_thread = Bot(bot_id, user_id, config['symbol'], strategy_class(), config['settings'], client)
                bot_thread.start()
                _running_bot_threads[bot_id] = bot_thread
                print(f"Bot '{bot_id}' for user {user_id} started from config.")
            else:
                print(f"Strategy '{config['strategy']}' for bot '{bot_id}' not found.")
