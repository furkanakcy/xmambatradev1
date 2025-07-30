import sqlite3
import os

# Veritabanı yolu
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(SCRIPT_DIR, "data")
DB_PATH = os.path.join(DB_DIR, "logs.db")

def add_trade():
    """Veritabanına manuel olarak işlem ekler."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Eklenecek işlem verileri
        bot_id = "Strategy 1"
        symbol = "NEWTUSDT"
        side = "Long"
        amount = 50.0
        entry_price = 0.3813
        exit_price = 0.7540
        pnl = 95.0
        profit_usd = 3562.0
        status = "closed"
        open_timestamp = "2025-07-24 03:00:00"
        close_timestamp = "2025-07-24 12:45:00"

        # Önce bu işlemin zaten var olup olmadığını kontrol et
        cursor.execute("""
            SELECT COUNT(*) FROM trade_history 
            WHERE symbol = ? AND entry_price = ? AND open_timestamp = ?
        """, (symbol, entry_price, open_timestamp))
        
        if cursor.fetchone()[0] == 0:
            # İşlemi ekle
            cursor.execute("""
                INSERT INTO trade_history (bot_id, symbol, side, amount, entry_price, exit_price, pnl, profit_usd, status, open_timestamp, close_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (bot_id, symbol, side, amount, entry_price, exit_price, pnl, profit_usd, status, open_timestamp, close_timestamp))
            
            conn.commit()
            print("İşlem başarıyla veritabanına eklendi.")
        else:
            print("Bu işlem zaten veritabanında mevcut.")

    except sqlite3.Error as e:
        print(f"Veritabanı hatası: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    add_trade()
