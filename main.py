# main.py
import asyncio
import logging
import time
import html
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

import config
import database
from pasarguard_api import PasarGuardAPI

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()
api = PasarGuardAPI()

class BotStates(StatesGroup):
    waiting_for_invite = State()
    waiting_for_promo = State()

def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Нижняя клавиатура над панелью ввода текста"""
    keyboard = [
        [KeyboardButton(text="📥 Получить доступ")],
        [KeyboardButton(text="❤️ Поддержать сервер")],
        [KeyboardButton(text="❓ Инструкция"), KeyboardButton(text="🎟 Ввести спецкод")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

# --- ВХОД И АВТОРИЗАЦИЯ ---

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = database.get_user(message.from_user.id)

    if user:
        current_name = f"@{message.from_user.username}" if message.from_user.username else (message.from_user.full_name or f"user_{message.from_user.id}")
        if user.get('username') != current_name:
            database.update_username(message.from_user.id, current_name)
        await message.answer("С возвращением! Рады, что вы снова с нами.", reply_markup=get_main_keyboard())
    else:
        await message.answer(
            "«Если ты хочешь пройти дальше, тебе придётся победить...» Ладно, шучу.\n"
            "Введите код для входа:", 
            reply_markup=None
        )
        await state.set_state(BotStates.waiting_for_invite)

@dp.message(BotStates.waiting_for_invite)
async def process_invite(message: Message, state: FSMContext):
    code = message.text.strip()
    
    if code != config.AUTH_INVITE_CODE:
        admin_contact = getattr(config, "ADMIN_USERNAME", "администратору")
        await message.answer(
            "Код неверный или вы просто ошиблись в символах\n"
            f"Попробуй ещё раз или обратись к {admin_contact}, чтобы разобраться."
        )
        return

    tg_id = message.from_user.id
    user_name = f"@{message.from_user.username}" if message.from_user.username else (message.from_user.full_name or f"user_{tg_id}")
    database.register_user(telegram_id=tg_id, username=user_name)
    await state.clear()
    await message.answer("Welcome to the club buddy.", reply_markup=get_main_keyboard())

# --- УПРАВЛЕНИЕ МУЛЬТИ-КЛЮЧАМИ ---

@dp.message(F.text == "📥 Получить доступ")
async def handle_get_key(message: Message):
    tg_id = message.from_user.id
    user = database.get_user(tg_id)
    if not user:
        await message.answer("Пожалуйста, перезапустите бота командой /start")
        return

    keys = database.get_user_keys(tg_id)
    current_time = int(time.time())

    if not keys:
        await message.answer(
            "GAME OVER. Срок действия доступа истёк или профиль ещё не активирован.\n"
            "Нажми кнопку «❤️ Поддержать сервер», чтобы закинуть монетку и продолжить.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Оформить первый ключ", callback_data="key_route:new")]
            ])
        )
        return

    text = "⚡️ <b>NEW ITEM UNLOCKED! Твои персональные ссылки-подписки:</b>\n\n"
    inline_keyboard = []

    for idx, key in enumerate(keys, 1):
        sub_path = key['subscription_url'].lstrip('/')
        full_sub_url = f"{config.PANEL_URL.rstrip('/')}/{sub_path}"
        
        days_left = max(0, (key['expiry_timestamp'] - current_time) // 86400)
        status_str = f"{days_left} дн." if days_left > 0 else "Истёк 💀"

        text += f"🔑 <b>Ключ #{idx}</b> (<code>{html.escape(key['panel_username'])}</code>)\n"
        text += f"<code>{html.escape(full_sub_url)}</code>\n"
        text += f"▫️ Статус: {status_str}\n\n"

        inline_keyboard.append([
            InlineKeyboardButton(text=f"🔄 Продлить Ключ #{idx}", callback_data=f"key_route:extend:{key['panel_username']}")
        ])

    inline_keyboard.append([InlineKeyboardButton(text="➕ Создать ещё один ключ", callback_data="key_route:new")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
    await message.answer(
        text + "Скопируй нужную ссылку (просто тапни по тексту выше) и импортируй в своё приложение.",
        parse_mode="HTML",
        reply_markup=markup
    )

# --- ИНТЕРФЕЙС ОПЛАТЫ / ПОДДЕРЖКИ ---

@dp.message(F.text == "❤️ Поддержать сервер")
async def handle_support(message: Message):
    tg_id = message.from_user.id
    keys = database.get_user_keys(tg_id)
    
    if not keys:
        await generate_invoice(message, tg_id, "new")
    else:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Купить новый ключ", callback_data="key_route:new")],
            [InlineKeyboardButton(text="🔄 Продлить существующий", callback_data="key_route:choose_extend")]
        ])
        await message.answer("Что именно ты хочешь сделать?", reply_markup=markup)

@dp.callback_query(F.data.startswith("key_route:"))
async def process_key_routing(callback: CallbackQuery):
    data_parts = callback.data.split(":")
    action = data_parts[1]
    tg_id = callback.from_user.id

    if action == "new":
        await generate_invoice(callback.message, tg_id, "new")
    elif action == "choose_extend":
        keys = database.get_user_keys(tg_id)
        inline_keyboard = []
        for idx, key in enumerate(keys, 1):
            inline_keyboard.append([
                InlineKeyboardButton(text=f"Ключ #{idx} ({key['panel_username']})", callback_data=f"key_route:extend:{key['panel_username']}")
            ])
        await callback.message.edit_text("Выбери ключ для продления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_keyboard))
    elif action == "extend":
        panel_username = data_parts[2]
        
        # --- ПРОВЕРКА ОГРАНИЧЕНИЯ В 3 ДНЯ (Пункт 1) ---
        key = database.get_key_by_panel_username(panel_username)
        if key:
            current_time = int(time.time())
            time_left = key['expiry_timestamp'] - current_time
            # 259200 секунд = ровно 3 дня
            if time_left > 259200:
                days_left = time_left // 86400
                await callback.message.answer(
                    f"⚠️ <b>Рано для продления!</b>\n\n"
                    f"Продлить ключ можно не ранее, чем за 3 дня до его истечения (после получения первого предупреждения).\n"
                    f"Сейчас у ключа <code>{html.escape(panel_username)}</code> осталось дней: <b>{days_left}</b>.",
                    parse_mode="HTML"
                )
                await callback.answer()
                return
                
        await generate_invoice(callback.message, tg_id, "extend", panel_username)
    
    await callback.answer()

async def generate_invoice(message: Message, tg_id: int, action_type: str, panel_username: str = ""):
    user = database.get_user(tg_id)
    if user['tariff_group'] == 'free':
        await message.answer("У тебя активирован вечный бесплатный доступ! Оплата не требуется. Создавай ключи прямо через меню «📥 Получить доступ».")
        return

    if user['tariff_group'] == 'fixed_6m':
        months = 6
        base_price = 600
    else:
        months = 1
        base_price = config.MONTHLY_PRICE

    discount = user['permanent_discount']
    final_price = int(base_price * (1 - discount))
    sbp_requisites = getattr(config, "SBP_PHONE", "+79001234567")

    text = (
        f"🎸 **Скидываемся на аренду точки**\n\n"
        f"Чтобы наше шоу продолжалось стабильно и без лагов, нужно обновить взнос.\n"
        f"▫️ Срок: {months} мес.\n"
        f"▫️ Сумма взноса: **{final_price} руб.**\n\n"
        f"💳 **Реквизиты СБП:**\n`{sbp_requisites}`\n\n"
        f"Как только отправишь перевод, жми кнопку снизу."
    )
    
    confirm_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Перевод выполнен", callback_data=f"user_confirm_pay:{final_price}:{action_type}:{panel_username}")]
    ])
    
    await message.answer(text, parse_mode="Markdown", reply_markup=confirm_markup)

# --- ПОДТВЕРЖДЕНИЕ ПЕРЕВОДА ---

@dp.callback_query(F.data.startswith("user_confirm_pay:"))
async def process_user_confirm(callback: CallbackQuery):
    _, price, action_type, panel_username = callback.data.split(":")
    user_id = callback.from_user.id
    username = callback.from_user.username or "без_ника"

    admin_markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"admin_approve:{user_id}:{action_type}:{panel_username}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_decline:{user_id}")
        ]
    ])

    await bot.send_message(
        chat_id=config.ADMIN_ID,
        text=f"💻 <b>[SYSTEM LOG]: Инициализирована проверка транзакции</b>\n\n"
             f"▫️ Аккаунт: @{html.escape(username)}\n"
             f"▫️ ID пользователя: <code>{user_id}</code>\n"
             f"▫️ Тип: <code>{html.escape(action_type)}</code> | <code>{html.escape(panel_username)}</code>\n"
             f"▫️ Ожидаемый взнос: <b>{price} руб.</b>\n\n"
             f"Запусти проверку банковского счёта на указанную сумму.",
        reply_markup=admin_markup,
        parse_mode="HTML"
    )

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("⏳ Сигнал улетел к админу! Ожидай подтверждения . Скоро всё будет.")
    await callback.answer()

# --- ОДОБРЕНИЕ И ОТКЛОНЕНИЕ (ДЛЯ АДМИНА) ---

@dp.callback_query(F.data.startswith("admin_approve:"))
async def admin_approve(callback: CallbackQuery):
    _, user_id, action_type, panel_username = callback.data.split(":")
    user_id = int(user_id)
    user = database.get_user(user_id)
    
    if not user:
        await callback.answer("Пользователь не найден.")
        return

    days = 180 if user['tariff_group'] == 'fixed_6m' else 30
    success = False

    if action_type == "new":
        generated_username = f"user_{user_id}_{int(time.time())}"
        res = await api.create_user(username=generated_username, days=days, data_limit_gb=config.DEFAULT_DATA_LIMIT_GB)
        if res and "subscription_url" in res:
            database.add_vpn_key(user_id, generated_username, res["subscription_url"], days)
            success = True
    elif action_type == "extend":
        success = await api.extend_user(username=panel_username, days=days)
        if success:
            database.update_key_expiry(panel_username, days)

    if success:
        await bot.send_message(
            user_id, 
            "🎮 Твоя монетка успешно долетела. Твой ключ уже ждёт тебя по кнопке «📥 Получить доступ» в главном меню."
        )
        await callback.message.edit_text(text=f"{html.escape(callback.message.text)}\n\n🟢 <b>ОДОБРЕНО</b>", parse_mode="HTML")
    else:
        await callback.answer("Ошибка PasarGuard API")
    await callback.answer()

@dp.callback_query(F.data.startswith("admin_decline:"))
async def admin_decline(callback: CallbackQuery):
    user_id = int(callback.data.split(":")[1])
    admin_contact = getattr(config, "ADMIN_USERNAME", "администратору")
    await bot.send_message(
        user_id, 
        f"❌ ОШИБКА ПРОВЕРКИ\nВзнос за поддержание инфраструктуры не найден. Если произошла ошибка при переводе, напиши {admin_contact} напрямую."
    )
    await callback.message.edit_text(text=f"{html.escape(callback.message.text)}\n\n🔴 <b>ОТКЛОНЕНО</b>", parse_mode="HTML")
    await callback.answer()

# --- АДМИНСКИЕ КОМАНДЫ МОНИТОРИНГА ---

@dp.message(Command("admin_users"))
async def cmd_admin_users(message: Message):
    """Выводит список всех пользователей бота и состояние их ключей"""
    if message.from_user.id != config.ADMIN_ID:
        return
    
    users = database.get_all_users()
    if not users:
        await message.answer("База данных пользователей пуста.")
        return
        
    current_time = int(time.time())
    
    for u in users:
        user_name = u['username']
        # Если в базе всё ещё заглушка вида user_123456789, пробуем подтянуть реальный ник через Telegram API
        if str(user_name).startswith("user_"):
            try:
                chat = await bot.get_chat(u['telegram_id'])
                if chat.username:
                    user_name = f"@{chat.username}"
                elif chat.full_name:
                    user_name = chat.full_name
                database.update_username(u['telegram_id'], user_name)
            except Exception:
                pass

        keys = database.get_user_keys(u['telegram_id'])
        keys_str = ""
        
        for k in keys:
            days_left = max(0, (k['expiry_timestamp'] - current_time) // 86400)
            status_str = f"{days_left} дн." if days_left > 0 else "Истёк 💀"
            keys_str += f"\n  └ 🔑 <code>{html.escape(k['panel_username'])}</code> (Осталось: {status_str})"
            
        if not keys_str:
            keys_str = "\n  └ Ключей нет"

        discount_pct = int(u['permanent_discount'] * 100)
        text = (
            f"👤 <b>Пользователь:</b> {html.escape(user_name)} (ID: <code>{u['telegram_id']}</code>)\n"
            f"▫️ Группа: <code>{html.escape(u['tariff_group'])}</code> | Перм. скидка: {discount_pct}%\n"
            f"▫️ <b>Управление ключами:</b>{keys_str}"
        )
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Аннулировать преимущества", callback_data=f"admin_revoke:{u['telegram_id']}")]
        ])
        await message.answer(text, parse_mode="HTML", reply_markup=markup)

@dp.message(Command("admin_promo_users"))
async def cmd_admin_promo_users(message: Message):
    """Выводит только тех пользователей, у кого активен статус от промокодов"""
    if message.from_user.id != config.ADMIN_ID:
        return
        
    users = database.get_users_with_benefits()
    if not users:
        await message.answer("На данный момент нет пользователей с активированными спецкодами.")
        return
        
    for u in users:
        user_name = u['username']
        if str(user_name).startswith("user_"):
            try:
                chat = await bot.get_chat(u['telegram_id'])
                if chat.username:
                    user_name = f"@{chat.username}"
                elif chat.full_name:
                    user_name = chat.full_name
                database.update_username(u['telegram_id'], user_name)
            except Exception:
                pass

        discount_pct = int(u['permanent_discount'] * 100)
        text = (
            f"🎟 <b>Обнаружен активный спецкод</b>\n\n"
            f"▫️ Пользователь: {html.escape(user_name)}\n"
            f"▫️ ID: <code>{u['telegram_id']}</code>\n"
            f"▫️ Тарифная группа: <code>{html.escape(u['tariff_group'])}</code>\n"
            f"▫️ Постоянная скидка: {discount_pct}%"
        )
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Деактивировать преимущества", callback_data=f"admin_revoke:{u['telegram_id']}")]
        ])
        await message.answer(text, parse_mode="HTML", reply_markup=markup)

# --- СПЕЦКОДЫ И ИНСТРУКЦИЯ ---

@dp.message(F.text == "🎟 Ввести спецкод")
async def handle_spec_code_btn(message: Message, state: FSMContext):
    await message.answer("🕹️ Обнаружил секретную комбинацию?\nВведи специальный код:")
    await state.set_state(BotStates.waiting_for_promo)

@dp.message(BotStates.waiting_for_promo)
async def process_promo(message: Message, state: FSMContext):
    code = message.text.strip()
    tg_id = message.from_user.id
    username = message.from_user.username or "без_ника"

    if code not in config.SPECIAL_CODES:
        await message.answer("❌ Чит-код не сработал. Такой комбинации не существует, проверь символы и попробуй ещё раз.")
        await state.clear()
        return

    if database.is_code_used(tg_id, code):
        await message.answer("Вы уже активировали этот код.")
        await state.clear()
        return

    code_data = config.SPECIAL_CODES[code]
    t_type = code_data["type"]

    if t_type == "limited_free":
        total_uses = database.get_code_total_uses(code)
        if total_uses >= code_data["max_uses"]:
            await message.answer("❌ Лимит активаций этого чит-кода исчерпан.")
            await state.clear()
            return

    admin_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Аннулировать преимущества", callback_data=f"admin_revoke:{tg_id}")]
    ])

    if t_type == "permanent_discount":
        database.update_user_status(tg_id, "standard", code_data["value"])
        database.apply_promo_code(tg_id, code)
        await message.answer(f"🎉 Код сработал идеально. Получена скидка на следующий взнос: {int(code_data['value']*100)}%. Отличный мув!")

    elif t_type == "fixed_tariff":
        database.update_user_status(tg_id, "fixed_6m", 0.0)
        database.apply_promo_code(tg_id, code)
        await message.answer("Привет Адам.")

    elif t_type == "lifetime_free":
        database.update_user_status(tg_id, "free", 1.0)
        database.apply_promo_code(tg_id, code)
        
        gen_user = f"user_{tg_id}_lifetime"
        res = await api.create_user(username=gen_user, days=3650, data_limit_gb=config.DEFAULT_DATA_LIMIT_GB)
        if res and "subscription_url" in res:
            database.add_vpn_key(tg_id, gen_user, res["subscription_url"], 3650)
        await message.answer("Because I’m in lesbians with you. I really, really mean it.")

    elif t_type == "limited_free":
        database.apply_promo_code(tg_id, code)
        days = code_data["days"]
        
        gen_user = f"user_{tg_id}_{int(time.time())}"
        res = await api.create_user(username=gen_user, days=days, data_limit_gb=config.DEFAULT_DATA_LIMIT_GB)
        if res and "subscription_url" in res:
            database.add_vpn_key(tg_id, gen_user, res["subscription_url"], days)
        await message.answer(f"🎉 Чит-код активирован! Тебе мгновенно выделен бесплатный доступ на {days} дней. Ключ уже ждет в меню «📥 Получить доступ».")

    await bot.send_message(
        chat_id=config.ADMIN_ID,
        text=f"🔔 <b>[PROMO ALERT]</b>\n\n"
             f"▫️ Пользователь: @{html.escape(username)}\n"
             f"▫️ ID: <code>{tg_id}</code>\n"
             f"▫️ Активировал код: <code>{html.escape(code)}</code>\n\n"
             f"Преимущества применились автоматически без подтверждения.",
        reply_markup=admin_markup,
        parse_mode="HTML"
    )

    await state.clear()

@dp.callback_query(F.data.startswith("admin_revoke:"))
async def admin_revoke_benefits(callback: CallbackQuery):
    target_id = int(callback.data.split(":")[1])
    database.update_user_status(target_id, "standard", 0.0)
    
    await callback.message.edit_text(text=f"{html.escape(callback.message.text)}\n\n🔴 <b>ПРЕИМУЩЕСТВА АННУЛИРОВАНЫ</b>", parse_mode="HTML")
    try:
        await bot.send_message(target_id, "⚠️ Ваш читкод были аннулирован администратором.")
    except Exception:
        pass
    await callback.answer()

# --- ИНСТРУКЦИЯ И ПЛАНИРОВЩИК ---

@dp.message(F.text == "❓ Инструкция")
async def send_instructions(message: Message):
    admin_contact = getattr(config, "ADMIN_USERNAME", "администратора")
    text = (
        "Перед стартом нажмите кнопку `📥 Получить доступ` в меню бота и скопируйте свою персональную ссылку-подписку (достаточно просто тапнуть по тексту с ссылкой).\n\n"
        "### 📱 Настройка через v2rayTun \n\n"
        "**Для iOS (iPhone / iPad), Android, Windows и macOS:**\n"
        "1. Установите приложение **v2rayTun** из App Store или Google Play.\n"
        "2. Скопируйте ссылку-подписку в этом боте.\n"
        "3. Откройте приложение **v2rayTun** и нажмите на иконку **Плюс (+)** в правом верхнем углу экрана.\n"
        "4. Выберите пункт **«Import from clipboard»** (Импорт из буфера обмена). Приложение само подхватит ссылку и мгновенно загрузит актуальный список серверов.\n"
        "5. Выберите сервер Lemna в списке внизу и нажмите кнопку **«Connect»** вверху экрана для запуска.\n\n"
        "**Ссылки на установку v2rayTun:**\n"
        "• **iOS / iPadOS / macOS (M1+):** [Скачать в App Store](https://apps.apple.com/us/app/v2raytun/id6476628951)\n"
        "• **Android:** [Скачать в Google Play](https://play.google.com/store/apps/details?id=com.v2raytun.android)\n"
        "• **Windows:** [Скачать c офф. сайта](https://v2raytun.com/)\n\n"
        "--- \n\n"
        "### 🔥 Настоятельная рекомендация: Попробуйте Hiddify\n\n"
        "Если вам нужен максимально красивый, современный интерфейс и поддержка абсолютно всех платформ (включая Windows), мы искренне рекомендуем поставить клиент **Hiddify**.\n"
        "Процесс настройки там точно такой же одноклеточный: открываете приложение → жмете одну кнопку **«Добавить из буфера обмена»** (Add from Clipboard) на главном экране. Программа сама всё импортирует и настроит подключение в один клик.\n\n"
        "**Ссылки на установку Hiddify:**\n"
        "• **iOS / iPadOS / macOS:** [Скачать в App Store](https://apps.apple.com/us/app/hiddify-proxy-vpn/id6596777532)\n"
        "• **Android:** [Скачать в Google Play](https://play.google.com/store/apps/details?id=app.hiddify.com)\n"
        "• **Windows:** [Скачать на GitHub](https://github.com/hiddify/hiddify-app/releases) (ищите `.exe` файл)\n\n"
        "--- \n\n"
        "### 🛠️ Список проверенных аналогов\n\n"
        "Если основные приложения вам по какой-то причине не подошли, вы можете использовать любой альтернативный софт. Все эти клиенты без проблем работают с нашими подписками:\n\n"
        "🍏 **iOS / iPadOS:**\n"
        "• FoXray, V2Box, Streisand (доступны в App Store)\n\n"
        "🤖 **Android:**\n"
        "• v2rayNG, NekoBox (доступны в Google Play или на GitHub)\n\n"
        "💻 **Windows:**\n"
        "• NekoRay (доступен на GitHub, ищите архив `windows64.zip`)\n\n"
        "🖥️ **macOS:**\n"
        "• FoXray, V2rayU (доступны в Mac App Store или на GitHub)\n\n"
        "--- \n\n"
        "### ⚠️ Информация для пользователей Amnezia#%!\n\n"
        f"Если вы до безумия любите интерфейс **Amnezia#%!** и не хотите заморачиваться с установкой другого приложения — вам придётся стучаться в личные сообщения ({admin_contact}) за ручным файлом конфигурации.\n\n"
        "Но сразу предупреждаем: **делать это крайне не рекомендуется**. Амнезия не позволяет что-то менять на сервере. Если появятся какие-то проблемы, изменения не применятся автоматически и вам придется ручками менять конфиг в приложении. Не усложняйте себе жизнь — переходите на v2rayTun или Hiddify, это стабильнее и надежнее."
    )
    await message.answer(text, parse_mode="Markdown", disable_web_page_preview=True)

async def expiration_scheduler():
    while True:
        try:
            current_time = int(time.time())
            with database.sqlite3.connect(database.DB_NAME) as conn:
                conn.row_factory = database.sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM vpn_keys")
                keys = cursor.fetchall()

            for key in keys:
                tg_id = key['telegram_id']
                expiry = key['expiry_timestamp']
                seconds_left = expiry - current_time

                if 259200 >= seconds_left > 255600:
                    await bot.send_message(
                        chat_id=tg_id,
                        text=f"⚠️ **Предупреждение!** Срок действия твоего ключа `{key['panel_username']}` истекает через 3 дня. Рекомендуем обновить взнос, чтобы не остался без сети."
                    )
                
                elif 43200 >= seconds_left > 39600:
                    await bot.send_message(
                        chat_id=tg_id,
                        text=f"🔥 **Внимание!** Доступ для ключа `{key['panel_username']}` отключится уже сегодня. Скорее жми кнопку «❤️ Поддержать сервер», шоу должно продолжаться!"
                    )
        except Exception as e:
            logging.error(f"Ошибка в планировщике: {e}")
        
        await asyncio.sleep(3600)

async def main():
    asyncio.create_task(expiration_scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
