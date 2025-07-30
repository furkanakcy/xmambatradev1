from encryption import encrypt_message, decrypt_message
import sqlite3
import hashlib
import os

# Betiğin bulunduğu dizine göre sağlam bir yol oluştur
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(SCRIPT_DIR, "data")
DB_PATH = os.path.join(DB_DIR, "logs.db")

# Bağlanmaya çalışmadan önce data dizininin mevcut olduğundan emin ol
os.makedirs(DB_DIR, exist_ok=True)

def get_db_connection():
    """Veritabanı bağlantısı oluşturur."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def migrate_tables():
    """Veritabanı şemasını en son sürüme günceller."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # users tablosuna 'üyelik_planı' sütununu ekle (eğer yoksa)
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN üyelik_planı TEXT")
    except sqlite3.OperationalError:
        pass # Sütun zaten var

    # users tablosuna 'ödeme_onaylandı' sütununu ekle (eğer yoksa)
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN ödeme_onaylandı BOOLEAN DEFAULT FALSE")
    except sqlite3.OperationalError:
        pass # Sütun zaten var

    # trade_history tablosuna 'profit_usd' sütununu ekle (eğer yoksa)
    try:
        cursor.execute("ALTER TABLE trade_history ADD COLUMN profit_usd REAL")
    except sqlite3.OperationalError:
        pass # Sütun zaten var

    # trade_history tablosuna 'user_id' sütununu ekle (eğer yoksa)
    try:
        cursor.execute("ALTER TABLE trade_history ADD COLUMN user_id INTEGER REFERENCES users(id)")
    except sqlite3.OperationalError:
        pass # Sütun zaten var

    conn.commit()
    conn.close()

def create_tables():
    """Gerekli veritabanı tablolarını oluşturur."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Kullanıcılar tablosu
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        üyelik_planı TEXT,
        ödeme_onaylandı BOOLEAN DEFAULT FALSE
    )
    """)
    
    # API Anahtarları tablosu (ileride kullanılacak)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS api_keys (
        user_id INTEGER PRIMARY KEY,
        api_key_encrypted BLOB NOT NULL,
        secret_key_encrypted BLOB NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """)

    # İşlem geçmişi tablosu
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trade_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        bot_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        amount REAL NOT NULL,
        entry_price REAL NOT NULL,
        exit_price REAL,
        pnl REAL,
        profit_usd REAL,
        status TEXT NOT NULL,
        open_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        close_timestamp DATETIME,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """)
    
    conn.commit()
    conn.close()

def hash_password(password):
    """Parolayı SHA256 ile hash'ler."""
    return hashlib.sha256(password.encode()).hexdigest()

def add_user(username, password):
    """Veritabanına yeni bir kullanıcı ekler."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, hash_password(password))
        )
        conn.commit()
        print(f"Kullanıcı '{username}' başarıyla eklendi.")
    except sqlite3.IntegrityError:
        print(f"Hata: '{username}' adlı kullanıcı zaten mevcut.")
    finally:
        conn.close()

def log_trade(user_id, bot_id, symbol, side, amount, entry_price, status='open', open_timestamp=None):
    """Yeni bir işlemi belirli bir kullanıcı için veritabanına kaydeder."""
    conn = get_db_connection()
    cursor = conn.cursor()
    if open_timestamp:
        cursor.execute("""
            INSERT INTO trade_history (user_id, bot_id, symbol, side, amount, entry_price, status, open_timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, bot_id, symbol, side, amount, entry_price, status, open_timestamp))
    else:
        cursor.execute("""
            INSERT INTO trade_history (user_id, bot_id, symbol, side, amount, entry_price, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, bot_id, symbol, side, amount, entry_price, status))
    trade_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return trade_id

def update_trade(trade_id, exit_price, pnl, profit_usd, close_timestamp=None):
    """Açık bir işlemi kapatır ve PNL'i günceller."""
    conn = get_db_connection()
    cursor = conn.cursor()
    if close_timestamp:
        cursor.execute("""
            UPDATE trade_history
            SET exit_price = ?, pnl = ?, profit_usd = ?, status = 'closed', close_timestamp = ?
            WHERE id = ?
        """, (exit_price, pnl, profit_usd, close_timestamp, trade_id))
    else:
        cursor.execute("""
            UPDATE trade_history
            SET exit_price = ?, pnl = ?, profit_usd = ?, status = 'closed', close_timestamp = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (exit_price, pnl, profit_usd, trade_id))
    conn.commit()
    conn.close()

def get_trade_history(user_id):
    """Belirli bir kullanıcının işlem geçmişini döndürür."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, bot_id, symbol, side, amount, entry_price, exit_price, pnl, profit_usd, status, open_timestamp, close_timestamp 
        FROM trade_history 
        WHERE user_id = ? 
        ORDER BY open_timestamp DESC
    """, (user_id,))
    history = cursor.fetchall()
    conn.close()
    return history

def has_users():
    """Veritabanında en az bir kullanıcı olup olmadığını kontrol eder."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    conn.close()
    return count > 0

def set_user_membership(user_id, plan):
    """Kullanıcının üyelik planını ve ödeme durumunu günceller."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users
        SET üyelik_planı = ?, ödeme_onaylandı = TRUE
        WHERE id = ?
    """, (plan, user_id))
    conn.commit()
    conn.close()

def get_user_membership(user_id):
    """Kullanıcının üyelik durumunu döndürür."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT üyelik_planı, ödeme_onaylandı FROM users WHERE id = ?", (user_id,))
    membership = cursor.fetchone()
    conn.close()
    if membership:
        return {"plan": membership["üyelik_planı"], "onaylandi": membership["ödeme_onaylandı"]}
    return None

def check_user(username, password):
    """Kullanıcı adı ve parolayı doğrular."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM users WHERE username = ? AND password_hash = ?",
        (username, hash_password(password))
    )
    user = cursor.fetchone()
    conn.close()
    return user is not None

# Not: Veritabanı ve tablolar app.py'den create_tables() çağrılarak oluşturulur.
# Varsayılan kullanıcıyı eklemek için bu betiği bir kez manuel olarak çalıştırabilirsiniz:
# python -c 'from database import create_tables, add_user; create_tables(); add_user("admin", "admin123")'

def get_user_id(username):
    """Kullanıcı adına göre ID'yi döndürür."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    user_id = cursor.fetchone()
    conn.close()
    return user_id[0] if user_id else None

def save_api_keys(user_id, api_key, secret_key):
    """API anahtarlarını şifreleyerek veritabanına kaydeder/günceller."""
    encrypted_api_key = encrypt_message(api_key)
    encrypted_secret_key = encrypt_message(secret_key)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("REPLACE INTO api_keys (user_id, api_key_encrypted, secret_key_encrypted) VALUES (?, ?, ?)",
                   (user_id, encrypted_api_key, encrypted_secret_key))
    conn.commit()
    conn.close()

def get_api_keys(user_id):
    """Bir kullanıcının API anahtarlarını şifresini çözerek döndürür."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT api_key_encrypted, secret_key_encrypted FROM api_keys WHERE user_id = ?", (user_id,))
    keys = cursor.fetchone()
    conn.close()
    
    if keys:
        try:
            decrypted_api_key = decrypt_message(keys['api_key_encrypted'])
            decrypted_secret_key = decrypt_message(keys['secret_key_encrypted'])
            return decrypted_api_key, decrypted_secret_key
        except Exception as e:
            print(f"Error decrypting keys for user {user_id}: {e}")
            return None, None
    return None, None

def delete_api_keys(user_id):
    """Bir kullanıcının API anahtarlarını siler."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM api_keys WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
