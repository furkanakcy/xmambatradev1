import ccxt
import pandas as pd
import requests

def get_unauthenticated_binance_client():
    """Kimlik doğrulaması gerektirmeyen, sadece halka açık veriler için bir CCXT istemcisi döndürür."""
    try:
        exchange = ccxt.binance({
            'options': {
                'defaultType': 'future',
            },
        })
        return exchange
    except Exception as e:
        print(f"Kimlik doğrulaması olmayan istemci oluşturulurken hata: {e}")
        return None

def get_binance_client(api_key, secret_key):
    """Verilen anahtarlar ile yapılandırılmış bir CCXT Binance Futures istemcisi döndürür."""
    if not api_key or not secret_key:
        return None
    try:
        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': secret_key,
            'options': {
                'defaultType': 'future',
            },
        })
        return exchange
    except Exception as e:
        print(f"CCXT istemcisi oluşturulurken hata: {e}")
        return None

def test_api_connection(api_key, secret_key):
    """Verilen API anahtarlarının geçerliliğini test eder."""
    client = get_binance_client(api_key, secret_key)
    if client is None:
        return False, "API anahtarları ile istemci oluşturulamadı."
    try:
        client.fetch_balance()
        return True, "API bağlantısı başarılı."
    except ccxt.AuthenticationError as e:
        return False, f"Kimlik doğrulama hatası: {e}"
    except Exception as e:
        return False, f"Bir hata oluştu: {e}"

def get_futures_balance(client):
    """USDT cinsinden Futures cüzdan bakiyesini döndürür."""
    if not client:
        return None
    try:
        balance = client.fetch_balance()
        usdt_balance = balance['total'].get('USDT', 0)
        return usdt_balance
    except Exception as e:
        print(f"Bakiye alınırken hata: {e}")
        return None

def set_leverage_and_margin_mode(client, symbol, leverage, margin_mode='ISOLATED'):
    """Bir sembol için kaldıraç ve marjin modunu ayarlar."""
    if not client:
        return False, "Geçersiz istemci."
    try:
        # Marjin modunu ayarla (örn: ISOLATED veya CROSSED)
        # Not: CCXT, `set_margin_mode` için standart bir `params` yapısı bekler.
        client.set_margin_mode(margin_mode, symbol=symbol)
        print(f"'{symbol}' için marjin modu '{margin_mode}' olarak ayarlandı.")

        # Kaldıracı ayarla
        client.set_leverage(leverage, symbol=symbol)
        print(f"'{symbol}' için kaldıraç {leverage}x olarak ayarlandı.")
        
        return True, "Kaldıraç ve marjin modu başarıyla ayarlandı."
    except ccxt.NetworkError as e:
        print(f"Ağ hatası: {e}")
        return False, f"Ağ hatası: {e}"
    except ccxt.ExchangeError as e:
        # Bazen kaldıraç zaten ayarlıysa hata verebilir, bu durumu görmezden gelebiliriz.
        if 'Leverage not modified' in str(e) or 'Margin type not modified' in str(e):
            print(f"Kaldıraç veya marjin modu zaten ayarlı: {e}")
            return True, "Kaldıraç veya marjin modu zaten ayarlı."
        print(f"Borsa hatası: {e}")
        return False, f"Borsa hatası: {e}"
    except Exception as e:
        print(f"Kaldıraç/marjin ayarlanırken bilinmeyen bir hata oluştu: {e}")
        return False, f"Bilinmeyen bir hata oluştu: {e}"

def get_historical_data(client, symbol, timeframe='1h', limit=100):
    """Belirtilen sembol için geçmiş mum verilerini çeker."""
    if not client:
        return None
    try:
        ohlcv = client.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df
    except Exception as e:
        print(f"Geçmiş veri alınırken hata: {e}")
        return None

def create_market_order(client, symbol, side, amount, take_profit_price=None, stop_loss_price=None):
    """Verilen sembol için bir market emri ve isteğe bağlı olarak TP/SL emirleri oluşturur."""
    if not client:
        return None, "Geçersiz istemci."
    try:
        # Ana market emrini oluştur
        order = client.create_market_order(symbol, side, amount)
        print(f"Market order created: {order}")

        # TP/SL emirlerini oluştur
        opposite_side = 'sell' if side == 'buy' else 'buy'
        
        if take_profit_price:
            try:
                tp_params = {'stopPrice': take_profit_price, 'reduceOnly': True}
                tp_order = client.create_order(symbol, 'TAKE_PROFIT_MARKET', opposite_side, amount, None, tp_params)
                print(f"Take profit order created: {tp_order}")
            except Exception as e:
                print(f"Take profit emri oluşturulurken hata: {e}")

        if stop_loss_price:
            try:
                sl_params = {'stopPrice': stop_loss_price, 'reduceOnly': True}
                sl_order = client.create_order(symbol, 'STOP_MARKET', opposite_side, amount, None, sl_params)
                print(f"Stop loss order created: {sl_order}")
            except Exception as e:
                print(f"Stop loss emri oluşturulurken hata: {e}")

        return order, "Emir başarıyla oluşturuldu."
    except Exception as e:
        return None, f"Emir oluşturulurken hata: {e}"

def get_24h_ticker():
    """Tüm USDT vadeli işlem çiftleri için 24 saatlik ticker verilerini döndürür (Halka Açık API)."""
    try:
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Hatalı yanıtlar için exception fırlat
        data = response.json()
        
        # Sadece USDT ile biten sembolleri filtrele
        usdt_tickers = [t for t in data if t['symbol'].endswith('USDT')]
        
        if not usdt_tickers:
            return pd.DataFrame()

        df = pd.DataFrame(usdt_tickers)
        
        # Gerekli sütunları seç ve yeniden adlandır
        df = df[['symbol', 'priceChangePercent', 'lastPrice', 'quoteVolume']]
        df.rename(columns={
            'symbol': 'Sembol',
            'priceChangePercent': 'Değişim (%)',
            'lastPrice': 'Son Fiyat',
            'quoteVolume': 'Hacim (USDT)'
        }, inplace=True)
        
        # Veri tiplerini dönüştür
        df['Değişim (%)'] = pd.to_numeric(df['Değişim (%)'], errors='coerce')
        df['Son Fiyat'] = pd.to_numeric(df['Son Fiyat'], errors='coerce')
        df['Hacim (USDT)'] = pd.to_numeric(df['Hacim (USDT)'], errors='coerce')
        
        # Sembol formatını düzelt (örn: BTCUSDT -> BTC/USDT)
        # Sadece sonda bulunan USDT'yi değiştirmek için
        df['Sembol'] = df['Sembol'].apply(lambda s: f"{s[:-4]}/{s[-4:]}" if s.endswith('USDT') else s)
        
        return df.dropna()
    except requests.exceptions.RequestException as e:
        print(f"Binance API'sine bağlanırken hata (ticker): {e}")
        return None
    except Exception as e:
        print(f"24 saatlik ticker verisi işlenirken hata: {e}")
        return None

def get_position(client, symbol):
    """Belirtilen sembol için mevcut pozisyonu ve PNL'i döndürür."""
    if not client:
        return None, None
    try:
        # `fetch_positions` yerine `fetch_position` kullanarak tek bir pozisyon çek
        # Not: CCXT kütüphanesinin bazı sürümlerinde `fetch_position` olmayabilir.
        # Bu durumda `fetch_positions` kullanmaya devam etmek gerekir.
        # Şimdilik, daha verimli olabilecek `fetch_positions([symbol])` ile devam edelim.
        positions = client.fetch_positions([symbol])
        
        if not positions:
            return None, None

        # Sembole uyan ilk pozisyonu bul
        for p in positions:
            if p['info']['symbol'] == symbol.replace('/', ''):
                # Pozisyonun boyutu sıfırdan farklıysa, yani açık bir pozisyon varsa
                if p.get('contracts') is not None and float(p['contracts']) != 0:
                    unrealized_pnl = p.get('unrealizedPnl', 0.0)
                    return p, float(unrealized_pnl)
        
        return None, None
    except Exception as e:
        print(f"Pozisyon bilgisi alınırken hata: {e}")
        return None, None

if __name__ == '__main__':
    print("Bu betik artık doğrudan çalıştırılamaz.")
    print("API anahtarları artık veritabanından, kullanıcıya özel olarak yüklenmektedir.")
