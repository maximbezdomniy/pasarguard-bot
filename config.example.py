# config.example.py
# Скопируй этот файл как config.py и заполни своими данными:
#   cp config.example.py config.py

# --- Telegram ---
BOT_TOKEN = "YOUR_BOT_TOKEN"        # Получить у @BotFather
ADMIN_ID = 123456789                 # Твой числовой Telegram ID (узнать у @userinfobot)

# --- PasarGuard API ---
PANEL_URL = "https://your-panel-url:8000"
API_USERNAME = "your_username"
API_PASSWORD = "your_password"

# --- Настройки тарифа ---
MONTHLY_PRICE = 80                  # Стандартная цена за месяц в рублях
DEFAULT_DATA_LIMIT_GB = 1000        # Лимит трафика по умолчанию (ГБ)
USER_GROUP_IDS = [1]                # ID группы пользователей в панели

# --- Авторизация ---
AUTH_INVITE_CODE = "YOUR_INVITE_CODE"  # Код для первого входа через /start

# --- Оплата и контакты ---
SBP_PHONE = "+79001234567"          # Номер телефона для переводов по СБП
ADMIN_USERNAME = "@your_username"   # Telegram username администратора для связи

# --- Промокоды ---
# Типы промокодов:
#   "lifetime_free"    — вечный бесплатный доступ
#   "permanent_discount" — постоянная скидка (value: 0.0–1.0, например 0.30 = 30%)
#   "fixed_tariff"     — фиксированный тариф на 6 месяцев
#   "limited_free"     — бесплатный доступ на N дней, ограничен по количеству активаций
SPECIAL_CODES = {
    "EXAMPLE_CODE_1": {"type": "lifetime_free"},
    "EXAMPLE_CODE_2": {"type": "permanent_discount", "value": 0.30},
    "EXAMPLE_CODE_3": {"type": "fixed_tariff", "tariff": "fixed_6m"},
    "EXAMPLE_CODE_4": {"type": "limited_free", "days": 14, "max_uses": 5},
}

