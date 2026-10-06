# database.py
import sqlite3
import time
from typing import Optional, List, Dict

DB_NAME = "users.db"

def init_db():
    """Создает таблицы в базе данных с новой архитектурой мульти-ключей"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        
        # Таблица пользователей: хранит профиль и перманентные модификаторы
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                tariff_group TEXT DEFAULT 'standard',
                permanent_discount REAL DEFAULT 0.0
            )
        """)
        
        # Новая таблица VPN-ключей (Один ко многим: у юзера может быть N ключей)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vpn_keys (
                key_id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                panel_username TEXT UNIQUE,
                subscription_url TEXT DEFAULT '',
                expiry_timestamp INTEGER DEFAULT 0,
                FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
            )
        """)
        
        # Таблица истории использованных промокодов (защита от повторного ввода)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS used_promocodes (
                telegram_id INTEGER,
                code TEXT,
                PRIMARY KEY (telegram_id, code)
            )
        """)
        conn.commit()

# --- РАБОТА С ПОЛЬЗОВАТЕЛЯМИ ---

def get_user(telegram_id: int) -> Optional[dict]:
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def register_user(telegram_id: int, username: str) -> None:
    """Регистрирует пользователя в системе после ввода инвайта"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO users (telegram_id, username) 
            VALUES (?, ?)
        """, (telegram_id, username))
        conn.commit()

def update_user_status(telegram_id: int, tariff_group: str, permanent_discount: float) -> None:
    """Перманентно привязывает преимущества к аккаунту"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users 
            SET tariff_group = ?, permanent_discount = ? 
            WHERE telegram_id = ?
        """, (tariff_group, permanent_discount, telegram_id))
        conn.commit()

def update_username(telegram_id: int, username: str) -> None:
    """Обновляет никнейм пользователя в базе данных"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET username = ? WHERE telegram_id = ?", (username, telegram_id))
        conn.commit()


# --- РАБОТА С VPN-КЛЮЧАМИ ---

def get_user_keys(telegram_id: int) -> List[dict]:
    """Получает все ключи, привязанные к конкретному пользователю"""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM vpn_keys WHERE telegram_id = ?", (telegram_id,))
        return [dict(row) for row in cursor.fetchall()]

def get_key_by_panel_username(panel_username: str) -> Optional[dict]:
    """Получает информацию о конкретном ключе по его имени в панели"""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM vpn_keys WHERE panel_username = ?", (panel_username,))
        row = cursor.fetchone()
        return dict(row) if row else None

def add_vpn_key(telegram_id: int, panel_username: str, subscription_url: str, days: int) -> None:
    """Добавляет новый созданный ключ в базу данных"""
    expiry = int(time.time()) + (days * 86400)
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO vpn_keys (telegram_id, panel_username, subscription_url, expiry_timestamp)
            VALUES (?, ?, ?, ?)
        """, (telegram_id, panel_username, subscription_url, expiry))
        conn.commit()

def update_key_expiry(panel_username: str, days: int) -> None:
    """Продлевает срок действия конкретного ключа по его имени в панели"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT expiry_timestamp FROM vpn_keys WHERE panel_username = ?", (panel_username,))
        row = cursor.fetchone()
        if not row:
            return
        
        current_expiry = row[0]
        base_time = max(current_expiry, int(time.time()))
        new_expiry = base_time + (days * 86400)
        
        cursor.execute("UPDATE vpn_keys SET expiry_timestamp = ? WHERE panel_username = ?", (new_expiry, panel_username))
        conn.commit()

# --- СИСТЕМА ПРОМОКОДОВ ---

def apply_promo_code(telegram_id: int, code: str) -> None:
    """Фиксирует, что конкретный юзер использовал этот код"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO used_promocodes (telegram_id, code) VALUES (?, ?)", (telegram_id, code))
        conn.commit()

def is_code_used(telegram_id: int, code: str) -> bool:
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM used_promocodes WHERE telegram_id = ? AND code = ?", (telegram_id, code))
        return cursor.fetchone() is not None

def get_code_total_uses(code: str) -> int:
    """Считает суммарное количество активаций кода среди всех юзеров"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM used_promocodes WHERE code = ?", (code,))
        return cursor.fetchone()[0]

# --- АДМИНСКИЕ ВЫБОРКИ ---

def get_all_users() -> List[dict]:
    """Возвращает список абсолютно всех зарегистрированных пользователей"""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users")
        return [dict(row) for row in cursor.fetchall()]

def get_users_with_benefits() -> List[dict]:
    """Возвращает только тех пользователей, у которых активированы спецкоды"""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE tariff_group != 'standard' OR permanent_discount > 0.0")
        return [dict(row) for row in cursor.fetchall()]

init_db()