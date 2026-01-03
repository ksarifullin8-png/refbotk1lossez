import asyncio
import sqlite3
import logging
import json
import os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode, ContentType
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
import random
import string

# ===================== НАСТРОЙКА ЛОГГИРОВАНИЯ =====================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===================== КОНФИГУРАЦИЯ =====================
BOT_TOKEN = "8305510237:AAGXj0GEfEyxYmTayBimDTUDYZesoWdTqxA"
GROUP_ID = -5086100260
REQUIRED_CHANNEL_ID = -1003525909692

# Динамические данные (загружаются из БД)
REQUIRED_CHANNELS = []
ADMIN_IDS = []
IMAGES_DIR = "images"

# Создаем папку для изображений
if not os.path.exists(IMAGES_DIR):
    os.makedirs(IMAGES_DIR)

# ===================== ИНИЦИАЛИЗАЦИЯ БОТА =====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ===================== СОСТОЯНИЯ FSM =====================
class WithdrawalStates(StatesGroup):
    waiting_for_skin_name = State()
    waiting_for_pattern = State()
    waiting_for_skin_photo = State()

class AddChannelStates(StatesGroup):
    waiting_for_channel_id = State()
    waiting_for_channel_username = State()
    waiting_for_channel_name = State()
    waiting_for_invite_link = State()

class AddAdminStates(StatesGroup):
    waiting_for_admin_id = State()

class AddPromoCodeStates(StatesGroup):
    waiting_for_promo_code = State()
    waiting_for_promo_amount = State()
    waiting_for_promo_uses = State()
    waiting_for_promo_expires = State()

class AddPhotoStates(StatesGroup):
    waiting_for_photo_type = State()
    waiting_for_photo = State()

class BonusSettingsStates(StatesGroup):
    waiting_for_referral_bonus = State()
    waiting_for_welcome_bonus = State()
    waiting_for_min_withdrawal = State()

class CreateLinkStates(StatesGroup):
    waiting_for_link_amount = State()
    waiting_for_link_uses = State()
    waiting_for_link_name = State()

# ===================== ФУНКЦИИ БАЗЫ ДАННЫХ =====================

def load_channels_from_db():
    """Загрузка каналов из БД"""
    global REQUIRED_CHANNELS
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT value FROM settings WHERE key = 'required_channels'")
    result = cursor.fetchone()
    
    REQUIRED_CHANNELS = []
    
    if result and result[0]:
        try:
            loaded_channels = json.loads(result[0])
            if isinstance(loaded_channels, list):
                for item in loaded_channels:
                    if isinstance(item, dict):
                        REQUIRED_CHANNELS.append(item)
                    elif isinstance(item, (int, str)):
                        channel_id = int(item)
                        REQUIRED_CHANNELS.append({
                            "id": channel_id,
                            "username": f"channel_{channel_id}",
                            "name": "Канал " + str(channel_id),
                            "invite_link": f"https://t.me/c/{str(abs(channel_id))[4:]}"
                        })
            elif isinstance(loaded_channels, (int, str)):
                channel_id = int(loaded_channels)
                REQUIRED_CHANNELS.append({
                    "id": channel_id,
                    "username": f"channel_{channel_id}",
                    "name": "Канал " + str(channel_id),
                    "invite_link": f"https://t.me/c/{str(abs(channel_id))[4:]}"
                })
        except Exception as e:
            logger.error(f"Ошибка загрузки каналов: {e}")
            REQUIRED_CHANNELS = []
    
    if not REQUIRED_CHANNELS:
        default_channel = {
            "id": REQUIRED_CHANNEL_ID,
            "username": "k1lossez",
            "name": "K1LOSS EZ",
            "invite_link": "https://t.me/k1lossez"
        }
        REQUIRED_CHANNELS = [default_channel]
        
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                      ('required_channels', json.dumps(REQUIRED_CHANNELS)))
        conn.commit()
    
    conn.close()
    logger.info(f"Загружено каналов: {len(REQUIRED_CHANNELS)}")

def load_admins_from_db():
    """Загрузка админов из БД"""
    global ADMIN_IDS
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT user_id FROM admins")
    admins = cursor.fetchall()
    ADMIN_IDS = [admin[0] for admin in admins]
    
    conn.close()

def init_database():
    """Инициализация базы данных"""
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        balance REAL DEFAULT 0,
        referrals_count INTEGER DEFAULT 0,
        referral_from INTEGER DEFAULT 0,
        join_date TEXT,
        last_activity TEXT,
        subscribed_channels TEXT DEFAULT '[]'
    )
    ''')
    
    # Таблица реферальных кодов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS referral_codes (
        user_id INTEGER PRIMARY KEY,
        referral_code TEXT UNIQUE,
        created_date TEXT
    )
    ''')
    
    # Таблица транзакций
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        type TEXT,
        description TEXT,
        date TEXT,
        status TEXT DEFAULT 'completed'
    )
    ''')
    
    # Таблица выводов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS withdrawals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        skin_name TEXT,
        pattern TEXT,
        photo_id TEXT,
        amount REAL,
        status TEXT DEFAULT 'pending',
        admin_id INTEGER,
        admin_username TEXT,
        created_date TEXT,
        processed_date TEXT,
        message_id INTEGER
    )
    ''')
    
    # Таблица админов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY,
        is_super_admin BOOLEAN DEFAULT 0,
        added_date TEXT,
        added_by INTEGER
    )
    ''')
    
    # Таблица настроек
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    ''')
    
    # Таблица промокодов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS promo_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        amount REAL,
        max_uses INTEGER,
        used_count INTEGER DEFAULT 0,
        created_by INTEGER,
        created_date TEXT,
        expires_date TEXT,
        is_active BOOLEAN DEFAULT 1
    )
    ''')
    
    # Таблица использованных промокодов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS used_promo_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        promo_code TEXT,
        used_date TEXT,
        amount REAL
    )
    ''')
    
    # Таблица раздаточных ссылок
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS giveaway_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        link_code TEXT UNIQUE,
        amount REAL,
        max_uses INTEGER,
        used_count INTEGER DEFAULT 0,
        created_by INTEGER,
        created_date TEXT,
        expires_date TEXT,
        is_active BOOLEAN DEFAULT 1,
        name TEXT DEFAULT 'Бонусная ссылка'
    )
    ''')
    
    # Таблица использованных раздаточных ссылок
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS used_giveaway_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        link_code TEXT,
        used_date TEXT,
        amount REAL
    )
    ''')
    
    # Настройки по умолчанию
    default_settings = [
        ('referral_bonus', '300'),
        ('welcome_bonus', '0'),
        ('group_id', str(GROUP_ID)),
        ('bot_name', 'K1LOSS EZ Referral Bot'),
        ('min_withdrawal', '100'),
        ('photo_welcome', ''),
        ('photo_profile', '')
    ]
    
    for key, value in default_settings:
        cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, value))
    
    # Добавляем начальных админов
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    initial_admins = [
        (7546928092, 1, current_time, 0),
        (6472276968, 1, current_time, 0)
    ]
    
    for admin_id, is_super, added_date, added_by in initial_admins:
        cursor.execute('SELECT * FROM admins WHERE user_id = ?', (admin_id,))
        if not cursor.fetchone():
            cursor.execute('INSERT INTO admins (user_id, is_super_admin, added_date, added_by) VALUES (?, ?, ?, ?)', 
                          (admin_id, is_super, added_date, added_by))
    
    conn.commit()
    conn.close()

# Инициализация БД при запуске
init_database()

# Загружаем данные из БД после инициализации
load_channels_from_db()
load_admins_from_db()

# ===================== ОСНОВНЫЕ ФУНКЦИИ БД =====================

def get_user(user_id):
    """Получить информацию о пользователе"""
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def update_user(user_id, **kwargs):
    """Обновить данные пользователя"""
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    
    for key, value in kwargs.items():
        cursor.execute(f'UPDATE users SET {key} = ? WHERE user_id = ?', (value, user_id))
    
    conn.commit()
    conn.close()

def get_setting(key, default=None):
    """Получить настройку"""
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else default

def update_setting(key, value):
    """Обновить настройку"""
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def get_referral_bonus():
    """Получить бонус за реферала"""
    return float(get_setting('referral_bonus', '300'))

def get_welcome_bonus():
    """Получить стартовый бонус"""
    return float(get_setting('welcome_bonus', '0'))

def get_photo_url(photo_type):
    """Получить URL фото из настроек"""
    return get_setting(f'photo_{photo_type}', '')

def register_user(user_id, username, full_name, referral_code=None):
    """Регистрация пользователя"""
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    existing_user = cursor.fetchone()
    
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    if existing_user is None:
        # Новый пользователь
        referrer_id = None
        
        if referral_code:
            cursor.execute('SELECT user_id FROM referral_codes WHERE referral_code = ?', (referral_code,))
            result = cursor.fetchone()
            if result:
                referrer_id = result[0]
                
                # Увеличиваем счетчик рефералов
                cursor.execute('UPDATE users SET referrals_count = referrals_count + 1 WHERE user_id = ?', (referrer_id,))
                
                # Начисляем бонус рефереру
                referral_bonus = get_referral_bonus()
                cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (referral_bonus, referrer_id))
                
                # Транзакция для реферера
                cursor.execute('''
                INSERT INTO transactions (user_id, amount, type, description, date, status)
                VALUES (?, ?, ?, ?, ?, ?)
                ''', (referrer_id, referral_bonus, 'referral_bonus', 
                      f'Бонус за приглашение #{user_id}', current_time, 'completed'))
        
        welcome_bonus = get_welcome_bonus()
        
        cursor.execute('''
        INSERT INTO users (user_id, username, full_name, referral_from, balance, join_date, 
                          last_activity, subscribed_channels)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, username, full_name, referrer_id if referrer_id else 0, 
              welcome_bonus, current_time, current_time, '[]'))
        
        # Транзакция для нового пользователя
        cursor.execute('''
        INSERT INTO transactions (user_id, amount, type, description, date, status)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, welcome_bonus, 'welcome_bonus', 'Бонус за регистрацию', current_time, 'completed'))
        
        # Уведомление админам
        try:
            asyncio.create_task(notify_admins_new_user(user_id, username, full_name, referrer_id))
        except Exception as e:
            logger.error(f"Ошибка уведомления админов: {e}")
    else:
        # Обновляем данные существующего пользователя
        cursor.execute('UPDATE users SET username = ?, full_name = ?, last_activity = ? WHERE user_id = ?', 
                      (username, full_name, current_time, user_id))
    
    conn.commit()
    conn.close()

async def notify_admins_new_user(user_id, username, full_name, referrer_id):
    """Уведомить админов о новом пользователе"""
    try:
        for admin_id in ADMIN_IDS:
            try:
                referrer_details = ""
                if referrer_id:
                    referrer = get_user(referrer_id)
                    if referrer:
                        referrer_name = referrer[2]  # full_name
                        referrer_username = f"@{referrer[1]}" if referrer[1] else "без юзернейма"
                        referrer_details = f"\n👤 Пригласил: {referrer_name} ({referrer_username})"
                
                admin_message = (
                    f"📈 <b>НОВЫЙ ПОЛЬЗОВАТЕЛЬ</b>\n\n"
                    f"👤 Имя: {full_name}\n"
                    f"📧 Юзернейм: @{username if username else 'Не указан'}\n"
                    f"🆔 ID: {user_id}{referrer_details}\n"
                    f"📅 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                
                await bot.send_message(admin_id, admin_message, parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.error(f"Ошибка отправки админу {admin_id}: {e}")
    except Exception as e:
        logger.error(f"Ошибка уведомления админов: {e}")

async def notify_admins_promo_activation(user_id, promo_code, amount, is_link=False):
    """Уведомить админов об активации промокода/ссылки"""
    try:
        user = get_user(user_id)
        if not user:
            return
            
        user_name = user[2]  # full_name
        user_username = f"@{user[1]}" if user[1] else "без юзернейма"
        
        for admin_id in ADMIN_IDS:
            try:
                message_type = "🔗 ссылки" if is_link else "🎁 промокода"
                admin_message = (
                    f"✅ <b>АКТИВАЦИЯ {message_type.upper()}</b>\n\n"
                    f"👤 Пользователь: {user_name}\n"
                    f"📧 Юзернейм: {user_username}\n"
                    f"🆔 ID: {user_id}\n"
                    f"💰 Получено: {amount}г\n"
                    f"{'🔗' if is_link else '🎁'} Код: {promo_code}\n"
                    f"📅 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                
                await bot.send_message(admin_id, admin_message, parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления админу {admin_id}: {e}")
    except Exception as e:
        logger.error(f"Ошибка уведомления админов об активации: {e}")

def create_referral_code(user_id):
    """Создать реферальный код"""
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    
    # Генерируем уникальный код
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute('INSERT OR REPLACE INTO referral_codes (user_id, referral_code, created_date) VALUES (?, ?, ?)', 
                  (user_id, code, current_time))
    
    conn.commit()
    conn.close()
    return code

def get_referral_code(user_id):
    """Получить реферальный код пользователя"""
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT referral_code FROM referral_codes WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def get_referral_stats(user_id):
    """Получить статистику рефералов"""
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*), SUM(balance) FROM users WHERE referral_from = ?', (user_id,))
    direct_stats = cursor.fetchone()
    direct_count = direct_stats[0] or 0
    
    conn.close()
    
    return {
        'direct_count': direct_count,
        'referral_bonus': get_referral_bonus()
    }

def update_balance(user_id, amount, description, transaction_type='manual_adjustment'):
    """Обновить баланс пользователя"""
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Обновляем баланс
    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
    
    # Записываем транзакцию
    cursor.execute('''
    INSERT INTO transactions (user_id, amount, type, description, date, status)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, amount, transaction_type, description, current_time, 'completed'))
    
    conn.commit()
    conn.close()

def create_withdrawal(user_id, skin_name, pattern, photo_id, amount):
    """Создать заявку на вывод"""
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        # Снимаем баланс
        cursor.execute('UPDATE users SET balance = balance - ? WHERE user_id = ?', (amount, user_id))
        
        # Создаем запись о выводе
        cursor.execute('''
        INSERT INTO withdrawals (user_id, skin_name, pattern, photo_id, amount, status, created_date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, skin_name, pattern, photo_id, amount, 'pending', current_time))
        
        withdrawal_id = cursor.lastrowid
        
        # Записываем транзакцию
        cursor.execute('''
        INSERT INTO transactions (user_id, amount, type, description, date, status)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, -amount, 'withdrawal', f'Заявка на вывод #{withdrawal_id}', current_time, 'pending'))
        
        conn.commit()
        conn.close()
        return withdrawal_id, None
        
    except Exception as e:
        conn.rollback()
        conn.close()
        logger.error(f"Ошибка создания вывода: {e}")
        return None, f"Ошибка при создании заявки: {str(e)}"

def get_withdrawals(user_id=None, status=None, limit=50):
    """Получить заявки на вывод"""
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    
    query = 'SELECT * FROM withdrawals'
    params = []
    
    if user_id or status:
        query += ' WHERE'
        conditions = []
        if user_id:
            conditions.append(' user_id = ?')
            params.append(user_id)
        if status:
            conditions.append(' status = ?')
            params.append(status)
        query += ' AND'.join(conditions)
    
    query += ' ORDER BY id DESC LIMIT ?'
    params.append(limit)
    
    cursor.execute(query, params)
    withdrawals = cursor.fetchall()
    conn.close()
    return withdrawals

def update_withdrawal_status(withdrawal_id, status, admin_id=None, admin_username=None):
    """Обновить статус вывода"""
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute('SELECT user_id, amount, status FROM withdrawals WHERE id = ?', (withdrawal_id,))
    result = cursor.fetchone()
    
    if not result:
        conn.close()
        return False
    
    user_id, amount, old_status = result
    
    if status == 'completed':
        cursor.execute('''
        UPDATE withdrawals SET status = ?, admin_id = ?, admin_username = ?, processed_date = ?
        WHERE id = ?
        ''', (status, admin_id, admin_username, current_time, withdrawal_id))
        
        cursor.execute("UPDATE transactions SET status = 'completed' WHERE description = ? AND type = 'withdrawal'", 
                      (f'Заявка на вывод #{withdrawal_id}',))
        
    elif status == 'rejected':
        cursor.execute('''
        UPDATE withdrawals SET status = ?, admin_id = ?, admin_username = ?, processed_date = ?
        WHERE id = ?
        ''', (status, admin_id, admin_username, current_time, withdrawal_id))
        
        # Возвращаем баланс
        cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
        cursor.execute("UPDATE transactions SET status = 'rejected' WHERE description = ? AND type = 'withdrawal'", 
                      (f'Заявка на вывод #{withdrawal_id}',))
    
    conn.commit()
    conn.close()
    return True

def get_transactions(user_id=None, limit=20):
    """Получить транзакции"""
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    
    if user_id:
        cursor.execute('SELECT * FROM transactions WHERE user_id = ? ORDER BY date DESC LIMIT ?', (user_id, limit))
    else:
        cursor.execute('SELECT * FROM transactions ORDER BY date DESC LIMIT ?', (limit,))
    
    transactions = cursor.fetchall()
    conn.close()
    return transactions

# ===================== ФУНКЦИИ ПРОМОКОДОВ =====================

def create_promo_code(code, amount, max_uses, created_by, expires_days=30):
    """Создать промокод"""
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    expires_date = (datetime.now() + timedelta(days=expires_days)).strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute('''
    INSERT INTO promo_codes (code, amount, max_uses, used_count, created_by, created_date, expires_date, is_active)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (code, amount, max_uses, 0, created_by, current_time, expires_date, 1))
    
    conn.commit()
    conn.close()
    return True

def use_promo_code(user_id, code):
    """Использовать промокод"""
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM promo_codes WHERE code = ? AND is_active = 1', (code,))
    promo = cursor.fetchone()
    
    if not promo:
        conn.close()
        return None, "Промокод не найден или неактивен"
    
    # Используем индексы
    promo_id = promo[0]
    amount = promo[2]
    max_uses = promo[3]
    used_count = promo[4]
    expires_date = promo[7]
    
    # Проверяем срок действия
    if expires_date and datetime.now() > datetime.strptime(expires_date, '%Y-%m-%d %H:%M:%S'):
        cursor.execute('UPDATE promo_codes SET is_active = 0 WHERE id = ?', (promo_id,))
        conn.commit()
        conn.close()
        return None, "Промокод истек"
    
    # Проверяем количество использований
    if used_count >= max_uses:
        cursor.execute('UPDATE promo_codes SET is_active = 0 WHERE id = ?', (promo_id,))
        conn.commit()
        conn.close()
        return None, "Промокод уже использован максимальное количество раз"
    
    # Проверяем, использовал ли пользователь уже этот промокод
    cursor.execute('SELECT * FROM used_promo_codes WHERE user_id = ? AND promo_code = ?', (user_id, code))
    if cursor.fetchone():
        conn.close()
        return None, "Вы уже использовали этот промокод"
    
    # Начисляем баллы
    update_balance(user_id, amount, f'Активация промокода: {code}', 'promo_code')
    
    # Обновляем счетчик использований
    cursor.execute('UPDATE promo_codes SET used_count = used_count + 1 WHERE id = ?', (promo_id,))
    
    # Записываем использование
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('''
    INSERT INTO used_promo_codes (user_id, promo_code, used_date, amount)
    VALUES (?, ?, ?, ?)
    ''', (user_id, code, current_time, amount))
    
    conn.commit()
    conn.close()
    
    # Уведомляем админов
    try:
        asyncio.create_task(notify_admins_promo_activation(user_id, code, amount, is_link=False))
    except Exception as e:
        logger.error(f"Ошибка уведомления админов: {e}")
    
    return amount, "Промокод успешно активирован"

def get_promo_codes(active_only=False):
    """Получить промокоды"""
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    
    if active_only:
        cursor.execute('SELECT * FROM promo_codes WHERE is_active = 1 ORDER BY created_date DESC')
    else:
        cursor.execute('SELECT * FROM promo_codes ORDER BY created_date DESC')
    
    promos = cursor.fetchall()
    conn.close()
    return promos

def delete_promo_code(code):
    """Удалить промокод"""
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM promo_codes WHERE code = ?', (code,))
    conn.commit()
    conn.close()
    return True

# ===================== ФУНКЦИИ РАЗДАТОЧНЫХ ССЫЛОК =====================

def create_giveaway_link(amount, max_uses, created_by, name="Бонусная ссылка", expires_days=30):
    """Создать раздаточную ссылку"""
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    
    # Генерируем уникальный код
    link_code = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    expires_date = (datetime.now() + timedelta(days=expires_days)).strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute('''
    INSERT INTO giveaway_links (link_code, amount, max_uses, used_count, created_by, created_date, expires_date, is_active, name)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (link_code, amount, max_uses, 0, created_by, current_time, expires_date, 1, name))
    
    conn.commit()
    conn.close()
    return link_code

def use_giveaway_link(user_id, link_code):
    """Использовать раздаточную ссылку"""
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM giveaway_links WHERE link_code = ? AND is_active = 1', (link_code,))
    link = cursor.fetchone()
    
    if not link:
        conn.close()
        return None, "Ссылка не найдена или неактивна"
    
    # Используем индексы
    link_id = link[0]
    amount = link[2]
    max_uses = link[3]
    used_count = link[4]
    expires_date = link[7]
    name = link[9]
    
    # Проверяем срок действия
    if expires_date and datetime.now() > datetime.strptime(expires_date, '%Y-%m-%d %H:%M:%S'):
        cursor.execute('UPDATE giveaway_links SET is_active = 0 WHERE id = ?', (link_id,))
        conn.commit()
        conn.close()
        return None, "Ссылка истекла"
    
    # Проверяем количество использований
    if used_count >= max_uses:
        cursor.execute('UPDATE giveaway_links SET is_active = 0 WHERE id = ?', (link_id,))
        conn.commit()
        conn.close()
        return None, "Ссылка уже использована максимальное количество раз"
    
    # Проверяем, использовал ли пользователь уже эту ссылку
    cursor.execute('SELECT * FROM used_giveaway_links WHERE user_id = ? AND link_code = ?', (user_id, link_code))
    if cursor.fetchone():
        conn.close()
        return None, "Вы уже использовали эту ссылку"
    
    # Начисляем баллы
    update_balance(user_id, amount, f'Активация ссылки: {name}', 'giveaway_link')
    
    # Обновляем счетчик использований
    cursor.execute('UPDATE giveaway_links SET used_count = used_count + 1 WHERE id = ?', (link_id,))
    
    # Записываем использование
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('''
    INSERT INTO used_giveaway_links (user_id, link_code, used_date, amount)
    VALUES (?, ?, ?, ?)
    ''', (user_id, link_code, current_time, amount))
    
    conn.commit()
    conn.close()
    
    # Уведомляем админов
    try:
        asyncio.create_task(notify_admins_promo_activation(user_id, link_code, amount, is_link=True))
    except Exception as e:
        logger.error(f"Ошибка уведомления админов: {e}")
    
    return amount, "Ссылка успешно активирована"

def get_giveaway_links(active_only=False):
    """Получить раздаточные ссылки"""
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    
    if active_only:
        cursor.execute('SELECT * FROM giveaway_links WHERE is_active = 1 ORDER BY created_date DESC')
    else:
        cursor.execute('SELECT * FROM giveaway_links ORDER BY created_date DESC')
    
    links = cursor.fetchall()
    conn.close()
    return links

def delete_giveaway_link(link_code):
    """Удалить раздаточную ссылку"""
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM giveaway_links WHERE link_code = ?', (link_code,))
    conn.commit()
    conn.close()
    return True

# ===================== ФУНКЦИИ АДМИНИСТРИРОВАНИЯ =====================

def is_admin(user_id):
    """Проверить, является ли пользователь админом"""
    return user_id in ADMIN_IDS

def is_super_admin(user_id):
    """Проверить, является ли пользователь суперадмином"""
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT is_super_admin FROM admins WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result and result[0] == 1

def add_admin_to_db(user_id, is_super=False, added_by=0):
    """Добавить администратора"""
    global ADMIN_IDS
    if user_id not in ADMIN_IDS:
        ADMIN_IDS.append(user_id)
        conn = sqlite3.connect('referral_bot.db')
        cursor = conn.cursor()
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute('''
        INSERT OR REPLACE INTO admins (user_id, is_super_admin, added_date, added_by)
        VALUES (?, ?, ?, ?)
        ''', (user_id, 1 if is_super else 0, current_time, added_by))
        
        conn.commit()
        conn.close()
        return True
    return False

def remove_admin_from_db(user_id):
    """Удалить администратора"""
    global ADMIN_IDS
    if user_id in ADMIN_IDS:
        ADMIN_IDS.remove(user_id)
        conn = sqlite3.connect('referral_bot.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM admins WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return True
    return False

def get_all_admins():
    """Получить всех администраторов"""
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM admins ORDER BY is_super_admin DESC, added_date DESC')
    admins = cursor.fetchall()
    conn.close()
    return admins

def add_channel_to_db(channel_data):
    """Добавить канал в список обязательных"""
    global REQUIRED_CHANNELS
    REQUIRED_CHANNELS.append(channel_data)
    update_setting('required_channels', json.dumps(REQUIRED_CHANNELS))
    return True

def remove_channel_from_db(channel_id):
    """Удалить канал из списка обязательных"""
    global REQUIRED_CHANNELS
    REQUIRED_CHANNELS = [ch for ch in REQUIRED_CHANNELS if isinstance(ch, dict) and ch.get('id') != channel_id]
    update_setting('required_channels', json.dumps(REQUIRED_CHANNELS))
    return True

# ===================== ФУНКЦИИ ПРОВЕРКИ ПОДПИСОК =====================

async def check_all_subscriptions(user_id):
    """Проверить подписки на все каналы"""
    not_subscribed_channels = []
    
    for channel in REQUIRED_CHANNELS:
        try:
            if isinstance(channel, dict):
                channel_id = channel.get("id")
                if not channel_id:
                    continue
            elif isinstance(channel, (int, str)):
                channel_id = int(channel)
                temp_channel = {
                    "id": channel_id,
                    "name": "Канал " + str(channel_id),
                    "username": "",
                    "invite_link": f"https://t.me/c/{str(abs(channel_id))[4:]}"
                }
            else:
                continue
            
            member = await bot.get_chat_member(channel_id, user_id)
            if member.status in ['left', 'kicked']:
                if isinstance(channel, dict):
                    not_subscribed_channels.append(channel)
                else:
                    not_subscribed_channels.append(temp_channel)
                    
        except Exception as e:
            logger.error(f"Ошибка проверки подписки на канал {channel_id if 'channel_id' in locals() else 'неизвестный'}: {e}")
            if isinstance(channel, dict):
                not_subscribed_channels.append(channel)
            elif isinstance(channel, (int, str)):
                channel_id = int(channel)
                not_subscribed_channels.append({
                    "id": channel_id,
                    "name": "Канал " + str(channel_id),
                    "username": "",
                    "invite_link": f"https://t.me/c/{str(abs(channel_id))[4:]}"
                })
    
    return not_subscribed_channels

# ===================== ФУНКЦИИ ОТПРАВКИ СООБЩЕНИЙ =====================

async def send_with_photo(chat_id, photo_type, caption, reply_markup=None):
    """Отправить сообщение с фото"""
    # Сначала проверяем локальный файл
    photo_path = os.path.join(IMAGES_DIR, f'{photo_type}.jpg')
    
    if os.path.exists(photo_path):
        try:
            photo = FSInputFile(photo_path)
            message = await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
            return message
        except Exception as e:
            logger.error(f"Ошибка отправки локального фото {photo_type}: {e}")
    
    # Проверяем file_id
    photo_file_id = get_setting(f'photo_{photo_type}_file_id', '')
    
    if photo_file_id:
        try:
            message = await bot.send_photo(
                chat_id=chat_id,
                photo=photo_file_id,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
            return message
        except Exception as e:
            logger.error(f"Ошибка отправки фото по file_id ({photo_type}): {e}")
            update_setting(f'photo_{photo_type}_file_id', '')
    
    # Проверяем URL
    photo_url = get_photo_url(photo_type)
    
    if photo_url and photo_url.startswith(('http://', 'https://')):
        try:
            message = await bot.send_photo(
                chat_id=chat_id,
                photo=photo_url,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
            return message
        except Exception as e:
            logger.error(f"Ошибка отправки фото по URL ({photo_type}): {e}")
    
    # Если фото нет или ошибка - отправляем текст
    message = await bot.send_message(
        chat_id=chat_id,
        text=caption,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )
    return message

async def edit_with_photo(callback, photo_type, caption, reply_markup=None):
    """Редактировать сообщение с фото"""
    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        else:
            await callback.message.edit_text(
                text=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"Ошибка редактирования сообщения: {e}")
        await send_with_photo(callback.from_user.id, photo_type, caption, reply_markup)

# ===================== КЛАВИАТУРЫ =====================

def main_keyboard():
    """Основная клавиатура"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="👤 Профиль", callback_data="profile"))
    keyboard.add(InlineKeyboardButton(text="👥 Мои рефералы", callback_data="my_referrals"))
    keyboard.add(InlineKeyboardButton(text="🔗 Реферальная ссылка", callback_data="referral_link"))
    keyboard.add(InlineKeyboardButton(text="💰 Вывод средств", callback_data="withdrawal"))
    keyboard.add(InlineKeyboardButton(text="🎁 Промокод", callback_data="use_promo_code"))
    keyboard.add(InlineKeyboardButton(text="📦 История выводов", callback_data="withdrawal_history"))
    keyboard.adjust(2)
    return keyboard.as_markup()

def profile_keyboard():
    """Клавиатура профиля"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="✅ Проверить подписки", callback_data="check_subscriptions"))
    keyboard.add(InlineKeyboardButton(text="🔄 Обновить баланс", callback_data="refresh_balance"))
    keyboard.add(InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu"))
    keyboard.adjust(2)
    return keyboard.as_markup()

def admin_keyboard():
    """Клавиатура админа"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="📊 Статистика бота", callback_data="bot_stats"))
    keyboard.add(InlineKeyboardButton(text="💰 Изменить баланс", callback_data="change_balance"))
    keyboard.add(InlineKeyboardButton(text="📢 Управление каналами", callback_data="manage_channels"))
    keyboard.add(InlineKeyboardButton(text="🎁 Управление промокодами", callback_data="manage_promo_codes"))
    keyboard.add(InlineKeyboardButton(text="🔗 Управление ссылками", callback_data="manage_giveaway_links"))
    keyboard.add(InlineKeyboardButton(text="📦 Заявки на вывод", callback_data="withdrawal_requests"))
    keyboard.add(InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users"))
    keyboard.add(InlineKeyboardButton(text="⚙️ Настройки бонусов", callback_data="bonus_settings"))
    keyboard.add(InlineKeyboardButton(text="👑 Управление админами", callback_data="manage_admins"))
    keyboard.add(InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu"))
    keyboard.adjust(2)
    return keyboard.as_markup()

def withdrawal_confirmation_keyboard(withdrawal_id):
    """Клавиатура подтверждения вывода"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="✅ Подтвердить вывод", callback_data=f"confirm_withdrawal_{withdrawal_id}"))
    keyboard.add(InlineKeyboardButton(text="❌ Отклонить вывод", callback_data=f"reject_withdrawal_{withdrawal_id}"))
    return keyboard.as_markup()

def channels_subscription_keyboard(not_subscribed_channels):
    """Клавиатура для подписки на каналы"""
    keyboard = InlineKeyboardBuilder()
    for channel in not_subscribed_channels:
        if isinstance(channel, dict):
            channel_name = channel.get('name', 'Канал ' + str(channel.get('id', '')))
            keyboard.add(InlineKeyboardButton(
                text=f"📢 Подписаться на {channel_name}", 
                url=channel.get('invite_link', f"https://t.me/c/{str(abs(channel.get('id', '')))[4:]}")
            ))
    keyboard.add(InlineKeyboardButton(text="✅ Я подписался", callback_data="check_subscriptions_after"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def bonus_settings_keyboard():
    """Клавиатура настроек бонусов"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="💰 Бонус за реферала", callback_data="set_referral_bonus"))
    keyboard.add(InlineKeyboardButton(text="🎁 Стартовый бонус", callback_data="set_welcome_bonus"))
    keyboard.add(InlineKeyboardButton(text="💸 Минимальный вывод", callback_data="set_min_withdrawal"))
    keyboard.add(InlineKeyboardButton(text="👑 Назад в админ-меню", callback_data="admin_menu_back"))
    keyboard.adjust(2)
    return keyboard.as_markup()

def withdrawal_requests_keyboard():
    """Клавиатура заявок на вывод"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="⏳ Ожидающие", callback_data="withdrawal_pending"))
    keyboard.add(InlineKeyboardButton(text="✅ Выполненные", callback_data="withdrawal_completed"))
    keyboard.add(InlineKeyboardButton(text="❌ Отклоненные", callback_data="withdrawal_rejected"))
    keyboard.add(InlineKeyboardButton(text="👑 Назад в админ-меню", callback_data="admin_menu_back"))
    keyboard.adjust(2)
    return keyboard.as_markup()

def giveaway_links_keyboard():
    """Клавиатура управления ссылками"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="➕ Создать ссылку", callback_data="create_giveaway_link"))
    keyboard.add(InlineKeyboardButton(text="📋 Список ссылок", callback_data="giveaway_links_list"))
    keyboard.add(InlineKeyboardButton(text="👑 Назад в админ-меню", callback_data="admin_menu_back"))
    keyboard.adjust(2)
    return keyboard.as_markup()

# ===================== ОБРАБОТЧИКИ КОМАНД =====================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    args = message.text.split()
    referral_code = args[1] if len(args) > 1 else None
    
    user_id = message.from_user.id
    username = message.from_user.username or ""
    full_name = message.from_user.full_name
    
    # Проверяем, если это ссылка на раздачу
    if referral_code and len(referral_code) == 12 and all(c in string.ascii_lowercase + string.digits for c in referral_code):
        # Это ссылка раздачи
        amount, result_message = use_giveaway_link(user_id, referral_code)
        if amount:
            register_user(user_id, username, full_name, None)
            user = get_user(user_id)
            balance = user[3] if user else 0
            
            success_text = (
                f"🎉 <b>Вы активировали бонусную ссылку!</b>\n\n"
                f"💰 <b>Получено:</b> {amount}г\n"
                f"💰 <b>Текущий баланс:</b> {balance}г\n\n"
                f"Спасибо за участие в раздаче!"
            )
            
            # Проверяем подписки
            not_subscribed_channels = await check_all_subscriptions(user_id)
            
            if not_subscribed_channels:
                channels_text = "📢 <b>Для дальнейшего использования бота необходимо подписаться на каналы:</b>\n\n"
                for channel in not_subscribed_channels:
                    if isinstance(channel, dict):
                        channel_name = channel.get('name', 'Канал ' + str(channel.get('id', '')))
                        channels_text += f"• {channel_name}\n"
                    else:
                        channels_text += f"• Канал {channel}\n"
                channels_text += "\nПосле подписки нажмите кнопку ниже:"
                
                await message.answer(
                    channels_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=channels_subscription_keyboard(not_subscribed_channels)
                )
                return
            
            await send_with_photo(message.chat.id, 'welcome', success_text, main_keyboard())
            return
        else:
            # Если ссылка не сработала, регистрируем как обычного пользователя
            pass
    
    register_user(user_id, username, full_name, referral_code)
    
    # Проверяем подписки
    not_subscribed_channels = await check_all_subscriptions(user_id)
    
    if not_subscribed_channels:
        channels_text = "📢 <b>Для использования бота необходимо подписаться на каналы:</b>\n\n"
        for channel in not_subscribed_channels:
            if isinstance(channel, dict):
                channel_name = channel.get('name', 'Канал ' + str(channel.get('id', '')))
                channels_text += f"• {channel_name}\n"
            else:
                channels_text += f"• Канал {channel}\n"
        channels_text += "\nПосле подписки нажмите кнопку ниже:"
        
        await message.answer(
            channels_text,
            parse_mode=ParseMode.HTML,
            reply_markup=channels_subscription_keyboard(not_subscribed_channels)
        )
        return
    
    user = get_user(user_id)
    balance = user[3] if user else 0
    referral_bonus = get_referral_bonus()
    
    caption = (
        f"👋 <b>Добро пожаловать в {get_setting('bot_name', 'K1LOSS EZ Referral Bot')}!</b>\n\n"
        f"👤 <b>Имя:</b> {full_name}\n"
        f"💰 <b>Баланс:</b> {balance}г\n\n"
        f"💎 <b>За каждого реферала:</b> {referral_bonus}г\n\n"
        f"<b>Используйте кнопки ниже:</b>"
    )
    
    await send_with_photo(message.chat.id, 'welcome', caption, main_keyboard())

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    """Панель администратора"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("⛔ У вас нет прав администратора!")
        return
    
    admin_count = len(ADMIN_IDS)
    
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    user_count = cursor.fetchone()[0] or 0
    conn.close()
    
    pending_withdrawals = len(get_withdrawals(status='pending'))
    
    caption = (
        f"👑 <b>Панель администратора</b>\n\n"
        f"📊 <b>Общая статистика:</b>\n"
        f"• Администраторов: <b>{admin_count}</b>\n"
        f"• Пользователей: <b>{user_count}</b>\n"
        f"• Заявок на вывод: <b>{pending_withdrawals}</b>\n\n"
        f"<b>Выберите действие:</b>"
    )
    
    await send_with_photo(message.chat.id, 'admin', caption, admin_keyboard())
    await message.delete()

@dp.callback_query(F.data == "main_menu")
async def main_menu(callback: CallbackQuery):
    """Главное меню"""
    user_id = callback.from_user.id
    user = get_user(user_id)
    balance = user[3] if user else 0
    
    caption = (
        f"🏠 <b>Главное меню {get_setting('bot_name', 'K1LOSS EZ Referral Bot')}</b>\n\n"
        f"💰 <b>Баланс:</b> {balance}г\n\n"
        f"👤 <b>Профиль</b> - информация о вашем аккаунте\n"
        f"👥 <b>Мои рефералы</b> - список приглашенных друзей\n"
        f"🔗 <b>Реферальная ссылка</b> - ваша персональная ссылка\n"
        f"💰 <b>Вывод средств</b> - заказать вывод голды\n"
        f"🎁 <b>Промокод</b> - активировать промокод\n"
        f"📦 <b>История выводов</b> - история ваших заявок\n"
    )
    
    await edit_with_photo(callback, 'welcome', caption, main_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery):
    """Показать профиль"""
    user_id = callback.from_user.id
    user = get_user(user_id)
    
    if not user:
        await callback.answer("❌ Пользователь не найден!", show_alert=True)
        return
    
    referral_code = get_referral_code(user_id) or create_referral_code(user_id)
    
    referrer_info = ""
    if user[5] and user[5] != 0:  # referral_from
        referrer = get_user(user[5])
        if referrer:
            referrer_name = referrer[2]  # full_name
            referrer_username = f"@{referrer[1]}" if referrer[1] else "без юзернейма"
            referrer_info = f"\n👤 <b>Пригласил:</b> {referrer_name} ({referrer_username})"
    
    join_date = user[6][:10] if user[6] else "Неизвестно"  # join_date
    
    not_subscribed = await check_all_subscriptions(user_id)
    subscription_status = "✅ Подписан" if not not_subscribed else "❌ Не подписан"
    
    ref_stats = get_referral_stats(user_id)
    
    profile_text = (
        f"👤 <b>Ваш профиль</b>\n\n"
        f"🆔 <b>ID:</b> <code>{user[0]}</code>\n"
        f"👤 <b>Имя:</b> {user[2]}\n"
        f"📧 <b>Юзернейм:</b> @{user[1] if user[1] else 'Не указан'}\n"
        f"💰 <b>Баланс:</b> <code>{user[3]}г</code>\n"
        f"👥 <b>Рефералов:</b> <code>{user[4]} человек</code>"
        f"{referrer_info}\n"
        f"🔗 <b>Реферальный код:</b> <code>{referral_code}</code>\n"
        f"📅 <b>Дата регистрации:</b> {join_date}\n"
        f"✅ <b>Статус подписок:</b> {subscription_status}\n\n"
        f"💎 <b>Реферальная программа:</b>\n"
        f"• За каждого реферала: <b>{ref_stats['referral_bonus']}г</b>\n"
        f"• Всего приглашено: <b>{ref_stats['direct_count']} человек</b>"
    )
    
    await edit_with_photo(callback, 'profile', profile_text, profile_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "referral_link")
async def show_referral_link(callback: CallbackQuery):
    """Показать реферальную ссылку"""
    user_id = callback.from_user.id
    referral_code = get_referral_code(user_id) or create_referral_code(user_id)
    
    bot_username = (await bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={referral_code}"
    
    referral_bonus = get_referral_bonus()
    
    referral_text = (
        f"🔗 <b>Ваша реферальная ссылка</b>\n\n"
        f"📝 <b>Ссылка:</b>\n"
        f"<code>{referral_link}</code>\n\n"
        f"📝 <b>Код:</b>\n"
        f"<code>{referral_code}</code>\n\n"
        f"💎 <b>За каждого реферала:</b> <b>{referral_bonus}г</b>\n\n"
        f"📢 <b>Просто отправьте эту ссылку друзьям!</b>"
    )
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="📢 Поделиться", url=f"https://t.me/share/url?url={referral_link}&text=Присоединяйся%20к%20нам!"))
    keyboard.add(InlineKeyboardButton(text="📋 Мои рефералы", callback_data="my_referrals"))
    keyboard.add(InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu"))
    keyboard.adjust(1)
    
    await edit_with_photo(callback, 'profile', referral_text, keyboard.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "my_referrals")
async def show_my_referrals(callback: CallbackQuery):
    """Показать моих рефералов"""
    user_id = callback.from_user.id
    
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, full_name, join_date, balance FROM users WHERE referral_from = ? ORDER BY join_date DESC LIMIT 20', (user_id,))
    referrals = cursor.fetchall()
    conn.close()
    
    if referrals:
        ref_stats = get_referral_stats(user_id)
        
        referrals_text = f"👥 <b>Ваши рефералы</b>\n\n"
        referrals_text += f"📊 <b>Статистика:</b>\n"
        referrals_text += f"• Всего рефералов: <b>{ref_stats['direct_count']}</b>\n"
        referrals_text += f"• Заработано: <b>{ref_stats['direct_count'] * ref_stats['referral_bonus']}г</b>\n\n"
        
        for ref in referrals:
            username = f"@{ref[1]}" if ref[1] else ref[2]
            
            referrals_text += (
                f"👤 <b>{ref[2]}</b> ({username})\n"
                f"   🆔 ID: <code>{ref[0]}</code>\n"
                f"   📅 Дата: {ref[3][:10]}\n"
                f"   💰 Баланс: {ref[4]}г\n\n"
            )
    else:
        referrals_text = "😔 <b>У вас пока нет рефералов.</b>\n\n🔗 Приглашайте друзей по своей реферальной ссылке!"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="🔗 Получить ссылку", callback_data="referral_link"))
    keyboard.add(InlineKeyboardButton(text="🔄 Обновить", callback_data="my_referrals"))
    keyboard.add(InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu"))
    keyboard.adjust(2)
    
    await edit_with_photo(callback, 'profile', referrals_text, keyboard.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "use_promo_code")
async def use_promo_code_handler(callback: CallbackQuery, state: FSMContext):
    """Активация промокода"""
    user_id = callback.from_user.id
    user = get_user(user_id)
    
    if not user:
        await callback.answer("❌ Пользователь не найден!", show_alert=True)
        return
    
    await callback.message.answer(
        "🎁 <b>Активация промокода</b>\n\n"
        "Введите промокод:",
        parse_mode=ParseMode.HTML
    )
    await state.set_state("waiting_for_promo_code")
    await callback.answer()

@dp.message(F.text, StateFilter("waiting_for_promo_code"))
async def process_promo_code(message: Message, state: FSMContext):
    """Обработка ввода промокода"""
    promo_code = message.text.strip().upper()
    user_id = message.from_user.id
    
    amount, result_message = use_promo_code(user_id, promo_code)
    
    if amount:
        user = get_user(user_id)
        new_balance = user[3] if user else amount
        
        success_text = (
            f"✅ <b>Промокод активирован!</b>\n\n"
            f"🎁 Промокод: <code>{promo_code}</code>\n"
            f"💰 Получено: <b>{amount}г</b>\n"
            f"💰 Новый баланс: <b>{new_balance}г</b>\n\n"
            f"Спасибо за использование нашего бота!"
        )
        
        await message.answer(success_text, parse_mode=ParseMode.HTML)
    else:
        error_text = (
            f"❌ <b>Ошибка активации промокода</b>\n\n"
            f"Промокод: <code>{promo_code}</code>\n"
            f"Ошибка: {result_message}"
        )
        
        await message.answer(error_text, parse_mode=ParseMode.HTML)
    
    await state.clear()

@dp.callback_query(F.data == "check_subscriptions")
async def check_subscriptions_handler(callback: CallbackQuery):
    """Проверка подписок"""
    user_id = callback.from_user.id
    not_subscribed_channels = await check_all_subscriptions(user_id)
    
    if not_subscribed_channels:
        channels_text = "📢 <b>Вы не подписаны на все обязательные каналы:</b>\n\n"
        for channel in not_subscribed_channels:
            if isinstance(channel, dict):
                channel_name = channel.get('name', 'Канал ' + str(channel.get('id', '')))
                channels_text += f"• {channel_name}\n"
            else:
                channels_text += f"• Канал {channel}\n"
        channels_text += "\nПосле подписки нажмите кнопку ниже:"
        
        await edit_with_photo(callback, 'profile', channels_text, 
                            channels_subscription_keyboard(not_subscribed_channels))
    else:
        success_text = "✅ <b>Отлично! Вы подписаны на все обязательные каналы.</b>"
        await edit_with_photo(callback, 'profile', success_text, profile_keyboard())
    
    await callback.answer()

@dp.callback_query(F.data == "refresh_balance")
async def refresh_balance(callback: CallbackQuery):
    """Обновить баланс"""
    user_id = callback.from_user.id
    user = get_user(user_id)
    
    if not user:
        await callback.answer("❌ Пользователь не найден!", show_alert=True)
        return
    
    balance = user[3] or 0
    
    await callback.answer(f"💰 Ваш баланс: {balance}г")

@dp.callback_query(F.data == "withdrawal")
async def start_withdrawal(callback: CallbackQuery, state: FSMContext):
    """Начать процесс вывода"""
    user_id = callback.from_user.id
    user = get_user(user_id)
    
    if not user:
        await callback.answer("❌ Пользователь не найден!", show_alert=True)
        return
    
    balance = user[3] if user else 0
    min_withdrawal = float(get_setting('min_withdrawal', '100'))
    
    if balance < min_withdrawal:
        await callback.answer(f"❌ Минимальная сумма вывода: {min_withdrawal}г!", show_alert=True)
        return
    
    await state.set_state(WithdrawalStates.waiting_for_skin_name)
    await state.update_data(user_id=user_id, balance=balance)
    
    await callback.message.answer(
        f"💰 <b>Заявка на вывод средств</b>\n\n"
        f"💰 Ваш баланс: <b>{balance}г</b>\n"
        f"💰 Минимум для вывода: <b>{min_withdrawal}г</b>\n\n"
        f"📝 <b>Шаг 1 из 3</b>\n"
        f"✏️ Напишите название скина с паттерном:\n\n"
        f"<i>Пример: USP | GHOSTS </i>",
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

@dp.message(WithdrawalStates.waiting_for_skin_name)
async def process_skin_name(message: Message, state: FSMContext):
    """Обработка названия скина"""
    skin_name = message.text.strip()
    
    if len(skin_name) < 3:
        await message.answer("❌ Название скина слишком короткое. Попробуйте еще раз:")
        return
    
    await state.update_data(skin_name=skin_name)
    await state.set_state(WithdrawalStates.waiting_for_pattern)
    
    await message.answer(
        "✅ Название скина сохранено!\n\n"
        "📝 <b>Шаг 2 из 3</b>\n"
        "🔢 Напишите паттерн скина:\n\n"
        "<i>Пример: 0.123(где цифры после нуля сам паттерн скина)</i>",
        parse_mode=ParseMode.HTML
    )

@dp.message(WithdrawalStates.waiting_for_pattern)
async def process_pattern(message: Message, state: FSMContext):
    """Обработка паттерна"""
    pattern = message.text.strip()
    
    try:
        float(pattern)
        if not (0 <= float(pattern) <= 1):
            await message.answer("❌ Паттерн должен быть между 0 и 1. Попробуйте еще раз:")
            return
    except ValueError:
        await message.answer("❌ Паттерн должен быть числом (например: 0.123). Попробуйте еще раз:")
        return
    
    await state.update_data(pattern=pattern)
    await state.set_state(WithdrawalStates.waiting_for_skin_photo)
    
    await message.answer(
        "✅ Паттерн сохранен!\n\n"
        "📝 <b>Шаг 3 из 3</b>\n"
        "📸 Отправьте фотографию скина:\n\n"
        "<i>Прикрепите фото в следующем сообщении</i>",
        parse_mode=ParseMode.HTML
    )

@dp.message(WithdrawalStates.waiting_for_skin_photo, F.photo)
async def process_skin_photo(message: Message, state: FSMContext):
    """Обработка фото скина"""
    photo_id = message.photo[-1].file_id
    data = await state.get_data()
    
    user_id = data['user_id']
    skin_name = data['skin_name']
    pattern = data['pattern']
    balance = data['balance']
    
    # Создаем заявку на вывод
    withdrawal_id, error = create_withdrawal(user_id, skin_name, pattern, photo_id, balance)
    
    if error:
        await message.answer(f"❌ <b>Ошибка создания заявки:</b>\n\n{error}", parse_mode=ParseMode.HTML)
        await state.clear()
        return
    
    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
    
    # Формируем сообщение для группы
    withdrawal_text = (
        f"📦 <b>НОВАЯ ЗАЯВКА НА ВЫВОД #{withdrawal_id}</b>\n\n"
        f"👤 <b>Пользователь:</b> {message.from_user.full_name}\n"
        f"📧 <b>Юзернейм:</b> {username}\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
        f"💰 <b>Сумма:</b> {balance}г\n\n"
        f"🎮 <b>Скин:</b> {skin_name}\n"
        f"🔢 <b>Паттерн:</b> {pattern}\n\n"
        f"📅 <b>Дата:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    # Отправляем в группу с фото и кнопками
    try:
        sent_message = await bot.send_photo(
            chat_id=GROUP_ID,
            photo=photo_id,
            caption=withdrawal_text,
            parse_mode=ParseMode.HTML,
            reply_markup=withdrawal_confirmation_keyboard(withdrawal_id)
        )
        
        # Сохраняем ID сообщения
        conn = sqlite3.connect('referral_bot.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE withdrawals SET message_id = ? WHERE id = ?', (sent_message.message_id, withdrawal_id))
        conn.commit()
        conn.close()
        
        # Уведомляем всех админов
        for admin_id in ADMIN_IDS:
            if admin_id != message.from_user.id:
                try:
                    await bot.send_message(
                        admin_id,
                        f"📦 <b>Новая заявка на вывод #{withdrawal_id}</b>\n\n"
                        f"👤 Пользователь: {message.from_user.full_name}\n"
                        f"💰 Сумма: {balance}г\n\n"
                        f"Перейдите в группу для обработки.",
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e:
                    logger.error(f"Ошибка уведомления админа {admin_id}: {e}")
    except Exception as e:
        logger.error(f"Ошибка отправки заявки в группу: {e}")
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"📦 <b>НОВАЯ ЗАЯВКА НА ВЫВОД #{withdrawal_id}</b>\n\n"
                    f"👤 Пользователь: {message.from_user.full_name}\n"
                    f"📧 Юзернейм: {username}\n"
                    f"🆔 ID: {user_id}\n"
                    f"💰 Сумма: {balance}г\n"
                    f"🎮 Скин: {skin_name}\n"
                    f"🔢 Паттерн: {pattern}\n"
                    f"📅 Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"⚠️ <b>Внимание:</b> Не удалось отправить заявку в группу!",
                    parse_mode=ParseMode.HTML
                )
            except Exception as admin_error:
                logger.error(f"Ошибка уведомления админа {admin_id}: {admin_error}")
    
    await state.clear()
    
    success_text = (
        f"✅ <b>Заявка на вывод успешно создана!</b>\n\n"
        f"📝 <b>Номер заявки:</b> #{withdrawal_id}\n"
        f"💰 <b>Сумма:</b> {balance}г\n"
        f"🎮 <b>Скин:</b> {skin_name}\n"
        f"🔢 <b>Паттерн:</b> {pattern}\n\n"
        f"⏳ <b>Статус:</b> Ожидание обработки администратором\n\n"
        f"Администратор свяжется с вами в ближайшее время!"
    )
    
    await message.answer(success_text, parse_mode=ParseMode.HTML)

@dp.callback_query(F.data == "withdrawal_history")
async def show_withdrawal_history(callback: CallbackQuery):
    """Показать историю выводов"""
    user_id = callback.from_user.id
    withdrawals = get_withdrawals(user_id=user_id, limit=10)
    
    if withdrawals:
        history_text = f"📦 <b>История ваших выводов</b>\n\n"
        
        for wd in withdrawals:
            # Индексы для таблицы withdrawals
            wd_id = wd[0]
            skin_name = wd[2]
            pattern = wd[3]
            amount = wd[5]
            status = wd[6]
            created_date = wd[9]
            
            status_emoji = {
                'pending': '⏳',
                'completed': '✅',
                'rejected': '❌'
            }.get(status, '❓')
            
            status_text = {
                'pending': 'В обработке',
                'completed': 'Выполнено',
                'rejected': 'Отклонено'
            }.get(status, status)
            
            history_text += (
                f"{status_emoji} <b>Заявка #{wd_id}</b>\n"
                f"💰 Сумма: {amount}г\n"
                f"🎮 Скин: {skin_name}\n"
                f"🔢 Паттерн: {pattern}\n"
                f"📅 Дата: {created_date[:10] if created_date else 'Неизвестно'}\n"
                f"📊 Статус: {status_text}\n\n"
            )
    else:
        history_text = "📭 <b>У вас еще не было заявок на вывод.</b>"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="💰 Новый вывод", callback_data="withdrawal"))
    keyboard.add(InlineKeyboardButton(text="🔄 Обновить", callback_data="withdrawal_history"))
    keyboard.add(InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu"))
    keyboard.adjust(2)
    
    await edit_with_photo(callback, 'profile', history_text, keyboard.as_markup())
    await callback.answer()

# ===================== ОБРАБОТЧИКИ ДЛЯ АДМИНИСТРАТОРОВ =====================

@dp.callback_query(F.data.startswith("confirm_withdrawal_"))
async def confirm_withdrawal_handler(callback: CallbackQuery):
    """Подтвердить вывод"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    withdrawal_id = int(callback.data.split("_")[-1])
    admin_username = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.full_name
    
    success = update_withdrawal_status(withdrawal_id, 'completed', user_id, admin_username)
    
    if success:
        conn = sqlite3.connect('referral_bot.db')
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, amount FROM withdrawals WHERE id = ?', (withdrawal_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            wd_user_id, amount = result
            
            # Уведомляем пользователя
            try:
                await bot.send_message(
                    wd_user_id,
                    f"✅ <b>Ваша заявка на вывод #{withdrawal_id} одобрена!</b>\n\n"
                    f"💰 Сумма: {amount}г\n"
                    f"👤 Администратор: {admin_username}\n"
                    f"📅 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"Совсем скоро ваш скин купят!",
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Ошибка уведомления пользователя: {e}")
            
            # Обновляем сообщение в группе
            try:
                conn = sqlite3.connect('referral_bot.db')
                cursor = conn.cursor()
                cursor.execute('SELECT message_id FROM withdrawals WHERE id = ?', (withdrawal_id,))
                msg_result = cursor.fetchone()
                conn.close()
                
                if msg_result and msg_result[0]:
                    try:
                        await bot.edit_message_caption(
                            chat_id=GROUP_ID,
                            message_id=msg_result[0],
                            caption=f"✅ <b>ВЫВОД #{withdrawal_id} ВЫПОЛНЕН</b>\n\n"
                                   f"👤 Администратор: {admin_username}\n"
                                   f"📅 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                            parse_mode=ParseMode.HTML
                        )
                    except Exception as e:
                        logger.error(f"Ошибка редактирования сообщения в группе: {e}")
            except Exception as e:
                logger.error(f"Ошибка получения message_id: {e}")
        
        await callback.answer(f"✅ Вывод #{withdrawal_id} подтвержден!")
        
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception as e:
            logger.error(f"Ошибка обновления клавиатуры: {e}")
    else:
        await callback.answer("❌ Ошибка подтверждения вывода!", show_alert=True)

@dp.callback_query(F.data.startswith("reject_withdrawal_"))
async def reject_withdrawal_handler(callback: CallbackQuery):
    """Отклонить вывод"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    withdrawal_id = int(callback.data.split("_")[-1])
    admin_username = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.full_name
    
    success = update_withdrawal_status(withdrawal_id, 'rejected', user_id, admin_username)
    
    if success:
        conn = sqlite3.connect('referral_bot.db')
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, amount FROM withdrawals WHERE id = ?', (withdrawal_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            wd_user_id, amount = result
            user = get_user(wd_user_id)
            new_balance = user[3] if user else amount
            
            # Уведомляем пользователя
            try:
                await bot.send_message(
                    wd_user_id,
                    f"❌ <b>Ваша заявка на вывод #{withdrawal_id} отклонена!</b>\n\n"
                    f"💰 Сумма: {amount}г возвращена на баланс\n"
                    f"👤 Администратор: {admin_username}\n"
                    f"📅 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"💰 Текущий баланс: {new_balance}г",
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Ошибка уведомления пользователя: {e}")
        
        await callback.answer(f"✅ Вывод #{withdrawal_id} отклонен!")
        
        # Обновляем сообщение в группе
        try:
            conn = sqlite3.connect('referral_bot.db')
            cursor = conn.cursor()
            cursor.execute('SELECT message_id FROM withdrawals WHERE id = ?', (withdrawal_id,))
            msg_result = cursor.fetchone()
            conn.close()
            
            if msg_result and msg_result[0]:
                try:
                    await bot.edit_message_caption(
                        chat_id=GROUP_ID,
                        message_id=msg_result[0],
                        caption=f"❌ <b>ВЫВОД #{withdrawal_id} ОТКЛОНЕН</b>\n\n"
                               f"👤 Администратор: {admin_username}\n"
                               f"📅 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e:
                    logger.error(f"Ошибка редактирования сообщения в группе: {e}")
        except Exception as e:
            logger.error(f"Ошибка получения message_id: {e}")
    else:
        await callback.answer("❌ Ошибка отклонения вывода!", show_alert=True)

# ===================== АДМИН КОМАНДЫ =====================

@dp.message(Command("add_balance"))
async def add_balance_command(message: Message):
    """Добавить баланс пользователю"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 4:
            await message.answer(
                "❌ Неверный формат. Используйте:\n"
                "<code>/add_balance user_id сумма описание</code>\n\n"
                "Пример:\n"
                "<code>/add_balance 123456789 100 Бонус за активность</code>",
                parse_mode=ParseMode.HTML
            )
            return
        
        target_user_id = int(parts[1])
        amount = float(parts[2])
        description = ' '.join(parts[3:])
        
        user = get_user(target_user_id)
        if not user:
            await message.answer("❌ Пользователь не найден!")
            return
        
        old_balance = user[3] or 0
        update_balance(target_user_id, amount, description, 'manual_adjustment')
        new_user = get_user(target_user_id)
        new_balance = new_user[3] if new_user and new_user[3] is not None else old_balance + amount
        
        result_text = (
            f"✅ <b>Баланс обновлен!</b>\n\n"
            f"👤 Пользователь: {user[2]}\n"
            f"🆔 ID: {target_user_id}\n"
            f"📊 Изменение: {amount:+}г\n"
            f"📝 Причина: {description}\n"
            f"💰 Старый баланс: {old_balance}г\n"
            f"💰 Новый баланс: {new_balance}г"
        )
        
        await message.answer(result_text, parse_mode=ParseMode.HTML)
        
        # Уведомляем пользователя
        try:
            await bot.send_message(
                target_user_id,
                f"💰 <b>Ваш баланс изменен!</b>\n\n"
                f"📊 Изменение: {amount:+}г\n"
                f"📝 Причина: {description}\n"
                f"💰 Новый баланс: {new_balance}г",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Ошибка уведомления пользователя: {e}")
            
    except ValueError as e:
        await message.answer(f"❌ Ошибка в формате данных: {e}")
    except Exception as e:
        logger.error(f"Ошибка в команде add_balance: {e}")
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("set_referral_bonus"))
async def set_referral_bonus_command(message: Message):
    """Установить бонус за реферала"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        return
    
    try:
        amount = float(message.text.split()[1])
        if amount < 0:
            await message.answer("❌ Сумма должна быть положительной!")
            return
        
        update_setting('referral_bonus', str(amount))
        
        await message.answer(f"✅ Бонус за реферала изменен на {amount}г!")
        
        for admin_id in ADMIN_IDS:
            if admin_id != user_id:
                try:
                    await bot.send_message(
                        admin_id,
                        f"⚙️ <b>Изменение настройки</b>\n\n"
                        f"👤 Админ: @{message.from_user.username if message.from_user.username else message.from_user.full_name}\n"
                        f"🎯 Настройка: Бонус за реферала\n"
                        f"💰 Новое значение: {amount}г",
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e:
                    logger.error(f"Ошибка уведомления админа {admin_id}: {e}")
    except IndexError:
        await message.answer("❌ Ошибка формата. Используйте: /set_referral_bonus 500")
    except ValueError:
        await message.answer("❌ Ошибка формата. Сумма должна быть числом!")
    except Exception as e:
        logger.error(f"Ошибка в команде set_referral_bonus: {e}")
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("set_welcome_bonus"))
async def set_welcome_bonus_command(message: Message):
    """Установить стартовый бонус"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        return
    
    try:
        amount = float(message.text.split()[1])
        if amount < 0:
            await message.answer("❌ Сумма должна быть положительной!")
            return
        
        update_setting('welcome_bonus', str(amount))
        
        await message.answer(f"✅ Стартовый бонус изменен на {amount}г!")
        
        for admin_id in ADMIN_IDS:
            if admin_id != user_id:
                try:
                    await bot.send_message(
                        admin_id,
                        f"⚙️ <b>Изменение настройки</b>\n\n"
                        f"👤 Админ: @{message.from_user.username if message.from_user.username else message.from_user.full_name}\n"
                        f"🎯 Настройка: Стартовый бонус\n"
                        f"💰 Новое значение: {amount}г",
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e:
                    logger.error(f"Ошибка уведомления админа {admin_id}: {e}")
    except IndexError:
        await message.answer("❌ Ошибка формата. Используйте: /set_welcome_bonus 100")
    except ValueError:
        await message.answer("❌ Ошибка формата. Сумма должна быть числом!")
    except Exception as e:
        logger.error(f"Ошибка в команде set_welcome_bonus: {e}")
        await message.answer(f"❌ Ошибка: {e}")

# ===================== КОМАНДЫ ДЛЯ РАБОТЫ С ФОТО =====================

@dp.message(Command("set_photo"))
async def set_photo_command(message: Message, state: FSMContext):
    """Установить фото для раздела бота"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        return
    
    photo_types = [
        "welcome - фото для приветствия",
        "profile - фото для профиля"
    ]
    
    await message.answer(
        "📸 <b>Установка фото для раздела бота</b>\n\n"
        "<b>Доступные типы фото:</b>\n" + "\n".join([f"• {pt}" for pt in photo_types]) + "\n\n"
        "Введите тип фото (например: <code>welcome</code>):",
        parse_mode=ParseMode.HTML
    )
    
    await state.set_state(AddPhotoStates.waiting_for_photo_type)

@dp.message(AddPhotoStates.waiting_for_photo_type)
async def process_photo_type(message: Message, state: FSMContext):
    """Обработка типа фото"""
    photo_type = message.text.strip().lower()
    
    valid_types = ['welcome', 'profile']
    
    if photo_type not in valid_types:
        await message.answer(
            f"❌ Неверный тип фото. Доступные типы:\n"
            f"{', '.join(valid_types)}\n\n"
            f"Попробуйте еще раз:"
        )
        return
    
    await state.update_data(photo_type=photo_type)
    await state.set_state(AddPhotoStates.waiting_for_photo)
    
    await message.answer(
        f"📸 <b>Установка фото для {photo_type}</b>\n\n"
        f"Отправьте URL фото (ссылку) или прикрепите фото.\n\n"
        f"<i>Поддерживаются ссылки на изображения.</i>",
        parse_mode=ParseMode.HTML
    )

@dp.message(AddPhotoStates.waiting_for_photo)
async def process_photo_url(message: Message, state: FSMContext):
    """Обработка URL фото"""
    data = await state.get_data()
    photo_type = data['photo_type']
    
    # Проверяем, отправлена ли ссылка или фото
    if message.text:
        # Это URL
        photo_url = message.text.strip()
        
        if not (photo_url.startswith('http://') or photo_url.startswith('https://')):
            await message.answer("❌ Неверный формат ссылки. Ссылка должна начинаться с http:// или https://")
            return
        
        update_setting(f'photo_{photo_type}', photo_url)
        
        await message.answer(
            f"✅ <b>Фото для {photo_type} успешно установлено!</b>\n\n"
            f"📎 Ссылка: {photo_url}\n\n"
            f"Фото будет использоваться в соответствующем разделе бота.",
            parse_mode=ParseMode.HTML
        )
        
    elif message.photo:
        # Это загруженное фото
        photo_id = message.photo[-1].file_id
        
        update_setting(f'photo_{photo_type}_file_id', photo_id)
        update_setting(f'photo_{photo_type}', f'file_id:{photo_id}')
        
        await message.answer(
            f"✅ <b>Фото для {photo_type} успешно установлено!</b>\n\n"
            f"📸 Фото сохранено как file_id.\n\n"
            f"<i>Фото будет использоваться в соответствующем разделе бота.</i>",
            parse_mode=ParseMode.HTML
        )
        
        try:
            file = await bot.get_file(photo_id)
            file_path = file.file_path
            downloaded_file = await bot.download_file(file_path)
            
            local_path = os.path.join(IMAGES_DIR, f'{photo_type}.jpg')
            with open(local_path, 'wb') as f:
                f.write(downloaded_file.read())
            
            await message.answer(
                f"📁 Фото также сохранено локально: {local_path}",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Ошибка сохранения фото локально: {e}")
            await message.answer(
                f"⚠️ Не удалось сохранить фото локально. Ошибка: {e}",
                parse_mode=ParseMode.HTML
            )
    
    else:
        await message.answer("❌ Пожалуйста, отправьте URL ссылку или прикрепите фото.")
        return
    
    await state.clear()

@dp.callback_query(F.data == "check_subscriptions_after")
async def check_subscriptions_after(callback: CallbackQuery):
    """Проверка подписок после нажатия кнопки"""
    user_id = callback.from_user.id
    not_subscribed_channels = await check_all_subscriptions(user_id)
    
    if not_subscribed_channels:
        await callback.answer("❌ Вы все еще не подписаны на все каналы!", show_alert=True)
        return
    
    user = get_user(user_id)
    balance = user[3] if user else 0
    
    caption = (
        f"✅ <b>Отлично! Вы подписаны на все каналы!</b>\n\n"
        f"👤 <b>Имя:</b> {callback.from_user.full_name}\n"
        f"💰 <b>Баланс:</b> {balance}г\n\n"
        f"Теперь вы можете использовать все функции бота!"
    )
    
    await edit_with_photo(callback, 'welcome', caption, main_keyboard())
    await callback.answer()

# ===================== ОБРАБОТЧИКИ АДМИН-МЕНЮ =====================

@dp.callback_query(F.data == "bot_stats")
async def bot_stats_handler(callback: CallbackQuery):
    """Статистика бота для админа"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*), SUM(balance) FROM users')
    total_stats = cursor.fetchone()
    user_count = total_stats[0] or 0
    total_balance = total_stats[1] or 0
    
    cursor.execute('SELECT COUNT(*) FROM users WHERE date(join_date) = date("now")')
    today_new = cursor.fetchone()[0] or 0
    
    pending_withdrawals = len(get_withdrawals(status='pending'))
    total_promos = len(get_promo_codes(active_only=False))
    total_links = len(get_giveaway_links(active_only=False))
    
    conn.close()
    
    stats_text = (
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 <b>Пользователи:</b>\n"
        f"• Всего: <b>{user_count}</b>\n"
        f"• Новых сегодня: <b>{today_new}</b>\n\n"
        f"💰 <b>Финансы:</b>\n"
        f"• Общий баланс: <b>{total_balance}г</b>\n\n"
        f"📦 <b>Заявки:</b>\n"
        f"• Ожидают обработки: <b>{pending_withdrawals}</b>\n\n"
        f"🎁 <b>Промокоды:</b>\n"
        f"• Всего: <b>{total_promos}</b>\n\n"
        f"🔗 <b>Ссылки:</b>\n"
        f"• Всего: <b>{total_links}</b>\n\n"
        f"👑 <b>Администраторы:</b> <b>{len(ADMIN_IDS)}</b>"
    )
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users"))
    keyboard.add(InlineKeyboardButton(text="📦 Заявки на вывод", callback_data="withdrawal_requests"))
    keyboard.add(InlineKeyboardButton(text="🔄 Обновить", callback_data="bot_stats"))
    keyboard.add(InlineKeyboardButton(text="👑 В админ-меню", callback_data="admin_menu_back"))
    keyboard.adjust(2)
    
    await edit_with_photo(callback, 'admin', stats_text, keyboard.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "admin_menu_back")
async def admin_menu_back(callback: CallbackQuery):
    """Возврат в админ-меню"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    admin_count = len(ADMIN_IDS)
    
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    user_count = cursor.fetchone()[0] or 0
    conn.close()
    
    pending_withdrawals = len(get_withdrawals(status='pending'))
    
    caption = (
        f"👑 <b>Панель администратора</b>\n\n"
        f"📊 <b>Общая статистика:</b>\n"
        f"• Администраторов: <b>{admin_count}</b>\n"
        f"• Пользователей: <b>{user_count}</b>\n"
        f"• Заявок на вывод: <b>{pending_withdrawals}</b>\n\n"
        f"<b>Выберите действие:</b>"
    )
    
    await edit_with_photo(callback, 'admin', caption, admin_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "admin_users")
async def admin_users_handler(callback: CallbackQuery):
    """Управление пользователями"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*), SUM(balance) FROM users')
    total_stats = cursor.fetchone()
    user_count = total_stats[0] or 0
    total_balance = total_stats[1] or 0
    
    cursor.execute('SELECT COUNT(*) FROM users WHERE date(join_date) = date("now")')
    today_new = cursor.fetchone()[0] or 0
    
    cursor.execute('SELECT full_name, referrals_count FROM users WHERE referrals_count > 0 ORDER BY referrals_count DESC LIMIT 5')
    top_referrers = cursor.fetchall()
    
    cursor.execute('SELECT full_name, balance FROM users WHERE balance > 0 ORDER BY balance DESC LIMIT 5')
    top_balance = cursor.fetchall()
    
    conn.close()
    
    stats_text = (
        f"👥 <b>Управление пользователей</b>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• Всего пользователей: <b>{user_count}</b>\n"
        f"• Новых сегодня: <b>{today_new}</b>\n"
        f"• Общий баланс: <b>{total_balance}г</b>\n\n"
        f"🏆 <b>Топ 5 рефереров:</b>\n"
    )
    
    for i, (name, ref_count) in enumerate(top_referrers, 1):
        stats_text += f"{i}. {name}: <b>{ref_count}</b> рефералов\n"
    
    stats_text += f"\n💰 <b>Топ 5 по балансу:</b>\n"
    for i, (name, balance) in enumerate(top_balance, 1):
        stats_text += f"{i}. {name}: <b>{balance}г</b>\n"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="📋 Список пользователей", callback_data="user_list"))
    keyboard.add(InlineKeyboardButton(text="🔍 Поиск пользователя", callback_data="search_user"))
    keyboard.add(InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_users"))
    keyboard.add(InlineKeyboardButton(text="👑 В админ-меню", callback_data="admin_menu_back"))
    keyboard.adjust(2)
    
    await edit_with_photo(callback, 'admin', stats_text, keyboard.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "change_balance")
async def change_balance_handler(callback: CallbackQuery):
    """Изменение баланса"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    stats_text = (
        f"💰 <b>Изменение баланса пользователя</b>\n\n"
        f"Для изменения баланса используйте команду:\n"
        f"<code>/add_balance ID_пользователя сумма описание</code>\n\n"
        f"Примеры:\n"
        f"• Добавить баланс:\n"
        f"<code>/add_balance 123456789 100 Бонус за активность</code>\n\n"
        f"• Снять баланс:\n"
        f"<code>/add_balance 123456789 -50 Штраф за нарушение</code>"
    )
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="🔍 Найти пользователя", callback_data="search_user"))
    keyboard.add(InlineKeyboardButton(text="📋 Список пользователей", callback_data="user_list"))
    keyboard.add(InlineKeyboardButton(text="👑 В админ-меню", callback_data="admin_menu_back"))
    keyboard.adjust(2)
    
    await edit_with_photo(callback, 'admin', stats_text, keyboard.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "bonus_settings")
async def bonus_settings_handler(callback: CallbackQuery):
    """Настройки бонусов"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    referral_bonus = get_referral_bonus()
    welcome_bonus = get_welcome_bonus()
    min_withdrawal = float(get_setting('min_withdrawal', '100'))
    
    stats_text = (
        f"⚙️ <b>Настройки бонусов</b>\n\n"
        f"📊 <b>Текущие настройки:</b>\n"
        f"• Бонус за реферала: <b>{referral_bonus}г</b>\n"
        f"• Стартовый бонус: <b>{welcome_bonus}г</b>\n"
        f"• Минимальный вывод: <b>{min_withdrawal}г</b>\n\n"
        f"Выберите параметр для изменения:"
    )
    
    await edit_with_photo(callback, 'admin', stats_text, bonus_settings_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "manage_channels")
async def manage_channels_handler(callback: CallbackQuery):
    """Управление каналами"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    channels_text = "📢 <b>Управление обязательными каналами</b>\n\n"
    
    if not REQUIRED_CHANNELS:
        channels_text += "❌ Нет обязательных каналов\n"
    else:
        channels_text += f"📊 Всего каналов: <b>{len(REQUIRED_CHANNELS)}</b>\n\n"
        
        for i, channel in enumerate(REQUIRED_CHANNELS, 1):
            if isinstance(channel, dict):
                channel_name = channel.get('name', 'Канал ' + str(channel.get('id', '')))
                channels_text += (
                    f"{i}. <b>{channel_name}</b>\n"
                    f"   🆔 ID: <code>{channel.get('id', 'Не указан')}</code>\n"
                    f"   📧 Юзернейм: @{channel.get('username', 'Не указан')}\n"
                    f"   🔗 Ссылка: {channel.get('invite_link', 'Не указана')}\n\n"
                )
            else:
                channels_text += f"{i}. Канал {channel}\n"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="➕ Добавить канал", callback_data="add_channel"))
    keyboard.add(InlineKeyboardButton(text="➖ Удалить канал", callback_data="remove_channel"))
    keyboard.add(InlineKeyboardButton(text="🔄 Обновить список", callback_data="manage_channels"))
    keyboard.add(InlineKeyboardButton(text="👑 В админ-меню", callback_data="admin_menu_back"))
    keyboard.adjust(2)
    
    await edit_with_photo(callback, 'admin', channels_text, keyboard.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "manage_admins")
async def manage_admins_handler(callback: CallbackQuery):
    """Управление админами"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    if not is_super_admin(user_id):
        await callback.answer("⛔ Только суперадмин может управлять админами!", show_alert=True)
        return
    
    admins = get_all_admins()
    
    admins_text = "👑 <b>Управление администраторами</b>\n\n"
    
    if not admins:
        admins_text += "❌ Нет администраторов\n"
    else:
        admins_text += f"📊 Всего администраторов: <b>{len(admins)}</b>\n\n"
        
        for admin in admins:
            # Используем индексы
            admin_id = admin[0]
            is_super = admin[1]
            added_date = admin[2]
            added_by = admin[3]
            
            user_info = get_user(admin_id)
            if user_info:
                name = user_info[2]  # full_name
                username = f"@{user_info[1]}" if user_info[1] else "без юзернейма"
            else:
                name = "Неизвестно"
                username = "без юзернейма"
            
            status = "🟢 Суперадмин" if is_super == 1 else "🔵 Админ"
            
            admins_text += (
                f"• <b>{name}</b> {status}\n"
                f"  📧 {username}\n"
                f"  🆔 ID: <code>{admin_id}</code>\n"
                f"  📅 Добавлен: {added_date[:10] if added_date else 'Неизвестно'}\n\n"
            )
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="➕ Добавить админа", callback_data="add_admin"))
    keyboard.add(InlineKeyboardButton(text="➖ Удалить админа", callback_data="remove_admin"))
    keyboard.add(InlineKeyboardButton(text="🔄 Обновить список", callback_data="manage_admins"))
    keyboard.add(InlineKeyboardButton(text="👑 В админ-меню", callback_data="admin_menu_back"))
    keyboard.adjust(2)
    
    await edit_with_photo(callback, 'admin', admins_text, keyboard.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "manage_promo_codes")
async def manage_promo_codes_handler(callback: CallbackQuery):
    """Управление промокодами"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    promos = get_promo_codes(active_only=False)
    
    promos_text = "🎁 <b>Управление промокодами</b>\n\n"
    
    if not promos:
        promos_text += "❌ Нет промокодов\n"
    else:
        active_count = len([p for p in promos if p[8] == 1])
        used_count = sum([p[4] for p in promos])
        
        promos_text += f"📊 Всего промокодов: <b>{len(promos)}</b>\n"
        promos_text += f"✅ Активных: <b>{active_count}</b>\n"
        promos_text += f"🔄 Использовано раз: <b>{used_count}</b>\n\n"
        
        for promo in promos[:5]:
            promo_id = promo[0]
            code = promo[1]
            amount = promo[2]
            max_uses = promo[3]
            used_count = promo[4]
            created_date = promo[6]
            expires_date = promo[7]
            is_active = promo[8]
            
            status = "🟢 Активен" if is_active == 1 else "🔴 Неактивен"
            expires_info = f"до {expires_date[:10]}" if expires_date else "без срока"
            
            promos_text += (
                f"• <b>{code}</b> {status}\n"
                f"  💰 Сумма: {amount}г\n"
                f"  🎯 Использовано: {used_count}/{max_uses}\n"
                f"  📅 {expires_info}\n\n"
            )
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="➕ Создать промокод", callback_data="create_promo_code"))
    keyboard.add(InlineKeyboardButton(text="📋 Список промокодов", callback_data="promo_codes_list"))
    keyboard.add(InlineKeyboardButton(text="🔄 Обновить", callback_data="manage_promo_codes"))
    keyboard.add(InlineKeyboardButton(text="👑 В админ-меню", callback_data="admin_menu_back"))
    keyboard.adjust(2)
    
    await edit_with_photo(callback, 'admin', promos_text, keyboard.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "manage_giveaway_links")
async def manage_giveaway_links_handler(callback: CallbackQuery):
    """Управление раздаточными ссылками"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    links = get_giveaway_links(active_only=False)
    
    links_text = "🔗 <b>Управление раздаточными ссылками</b>\n\n"
    
    if not links:
        links_text += "❌ Нет созданных ссылок\n"
    else:
        active_count = len([l for l in links if l[8] == 1])
        used_count = sum([l[4] for l in links])
        total_amount = sum([l[2] * l[4] for l in links])  # сумма * использований
        
        links_text += f"📊 Всего ссылок: <b>{len(links)}</b>\n"
        links_text += f"✅ Активных: <b>{active_count}</b>\n"
        links_text += f"🔄 Использовано раз: <b>{used_count}</b>\n"
        links_text += f"💰 Выдано голды: <b>{total_amount}г</b>\n\n"
        
        bot_username = (await bot.get_me()).username
        
        for link in links[:3]:
            link_code = link[1]
            amount = link[2]
            max_uses = link[3]
            used_count = link[4]
            expires_date = link[7]
            is_active = link[8]
            name = link[9]
            
            status = "🟢" if is_active == 1 else "🔴"
            expires_info = f"до {expires_date[:10]}" if expires_date else "без срока"
            giveaway_link = f"https://t.me/{bot_username}?start={link_code}"
            
            links_text += (
                f"{status} <b>{name}</b>\n"
                f"  🔗 Ссылка: {giveaway_link[:30]}...\n"
                f"  💰 Сумма: {amount}г\n"
                f"  🎯 Использовано: {used_count}/{max_uses}\n"
                f"  📅 {expires_info}\n\n"
            )
    
    await edit_with_photo(callback, 'admin', links_text, giveaway_links_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "withdrawal_requests")
async def withdrawal_requests_handler(callback: CallbackQuery):
    """Заявки на вывод"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    pending_withdrawals = get_withdrawals(status='pending', limit=10)
    
    stats_text = "📦 <b>Заявки на вывод</b>\n\n"
    
    if not pending_withdrawals:
        stats_text += "✅ <b>Нет ожидающих заявок</b>\n\n"
    else:
        stats_text += f"⏳ <b>Ожидают обработки:</b> <b>{len(pending_withdrawals)}</b>\n\n"
        
        total_amount = sum([wd[5] for wd in pending_withdrawals])
        stats_text += f"💰 <b>Общая сумма:</b> <b>{total_amount}г</b>\n\n"
        
        for wd in pending_withdrawals[:3]:
            wd_id = wd[0]
            wd_user_id = wd[1]
            skin_name = wd[2]
            pattern = wd[3]
            amount = wd[5]
            created_date = wd[9]
            
            user = get_user(wd_user_id)
            if user:
                user_name = user[2]
                user_username = f"@{user[1]}" if user[1] else "без юзернейма"
            else:
                user_name = "Неизвестно"
                user_username = "без юзернейма"
            
            stats_text += (
                f"• <b>Заявка #{wd_id}</b>\n"
                f"  👤 {user_name} ({user_username})\n"
                f"  🆔 ID: <code>{wd_user_id}</code>\n"
                f"  💰 {amount}г | 🎮 {skin_name[:20]}...\n"
                f"  📅 {created_date[:16]}\n\n"
            )
    
    stats_text += "Выберите действие:"
    
    await edit_with_photo(callback, 'admin', stats_text, withdrawal_requests_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "search_user")
async def search_user_handler(callback: CallbackQuery):
    """Поиск пользователя через кнопку"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    search_text = (
        "🔍 <b>Поиск пользователя</b>\n\n"
        "Вы можете искать пользователей по:\n"
        "• <b>ID</b> - например: 123456789\n"
        "• <b>Юзернейму</b> - например: @username или username\n"
        "• <b>Имени</b> - например: Иван Иванов\n"
        "• <b>*</b> - показать последних 20 пользователей\n\n"
        "Просто отправьте мне поисковый запрос."
    )
    
    await callback.message.answer(search_text, parse_mode=ParseMode.HTML)
    await callback.answer()

@dp.message(Command("find_user"))
async def find_user_command(message: Message):
    """Команда поиска пользователя - РАБОЧАЯ ВЕРСИЯ"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("⛔ У вас нет прав администратора!")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer(
                "❌ Неверный формат. Используйте:\n"
                "<code>/find_user поисковый_запрос</code>\n\n"
                "Примеры:\n"
                "<code>/find_user 1234567890</code> - поиск по ID\n"
                "<code>/find_user @username</code> - поиск по юзернейму\n"
                "<code>/find_user Имя Фамилия</code> - поиск по имени\n"
                "<code>/find_user *</code> - последние 20 пользователей",
                parse_mode=ParseMode.HTML
            )
            return
        
        search_term = ' '.join(parts[1:])
        
        conn = sqlite3.connect('referral_bot.db')
        cursor = conn.cursor()
        
        # Если звездочка - показываем последних пользователей
        if search_term == '*':
            cursor.execute('SELECT * FROM users ORDER BY user_id DESC LIMIT 20')
            results = cursor.fetchall()
            conn.close()
            
            if not results:
                await message.answer("❌ В базе данных нет пользователей!")
                return
            
            results_text = f"👥 <b>Последние 20 пользователей</b>\n\n"
            
            for user in results:
                user_id_val = user[0]
                username = user[1] or ""
                full_name = user[2] or "Без имени"
                balance = user[3] or 0
                referrals_count = user[4] or 0
                join_date = user[6] or "Неизвестно"
                
                username_display = f"@{username}" if username else "без юзернейма"
                join_date_formatted = join_date[:10] if len(join_date) >= 10 else join_date
                
                results_text += (
                    f"👤 <b>{full_name}</b> ({username_display})\n"
                    f"🆔 ID: <code>{user_id_val}</code>\n"
                    f"💰 Баланс: {balance}г\n"
                    f"👥 Рефералов: {referrals_count}\n"
                    f"📅 Регистрация: {join_date_formatted}\n\n"
                )
            
            await message.answer(results_text, parse_mode=ParseMode.HTML)
            return
        
        # Поиск по ID
        if search_term.isdigit():
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (int(search_term),))
            results = cursor.fetchall()
            
        # Поиск по юзернейму (с @ или без)
        elif search_term.startswith('@'):
            username = search_term[1:].strip()
            cursor.execute('SELECT * FROM users WHERE username LIKE ? ORDER BY join_date DESC LIMIT 10', 
                          (f'%{username}%',))
            results = cursor.fetchall()
            
        # Поиск по имени
        else:
            cursor.execute('''
                SELECT * FROM users 
                WHERE full_name LIKE ? OR username LIKE ? 
                ORDER BY join_date DESC LIMIT 10
            ''', (f'%{search_term}%', f'%{search_term}%'))
            results = cursor.fetchall()
        
        conn.close()
        
        if not results:
            await message.answer(f"❌ Пользователи по запросу '{search_term}' не найдены!")
            return
        
        results_text = f"🔍 <b>Результаты поиска '{search_term}'</b>\n\n"
        
        for user in results:
            user_id_val = user[0]
            username = user[1] or ""
            full_name = user[2] or "Без имени"
            balance = user[3] or 0
            referrals_count = user[4] or 0
            join_date = user[6] or "Неизвестно"
            
            username_display = f"@{username}" if username else "без юзернейма"
            join_date_formatted = join_date[:10] if len(join_date) >= 10 else join_date
            
            results_text += (
                f"👤 <b>{full_name}</b> ({username_display})\n"
                f"🆔 ID: <code>{user_id_val}</code>\n"
                f"💰 Баланс: {balance}г\n"
                f"👥 Рефералов: {referrals_count}\n"
                f"📅 Регистрация: {join_date_formatted}\n\n"
            )
        
        await message.answer(results_text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Ошибка поиска пользователя: {e}")
        await message.answer(f"❌ Ошибка при поиске: {str(e)}")

@dp.message(Command("user"))
async def user_info_command(message: Message):
    """Быстрый просмотр информации о пользователе"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("⛔ У вас нет прав администратора!")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer(
                "❌ Неверный формат. Используйте:\n"
                "<code>/user ID_пользователя</code>\n\n"
                "Пример:\n"
                "<code>/user 1234567890</code>",
                parse_mode=ParseMode.HTML
            )
            return
        
        target_user_id = int(parts[1])
        user = get_user(target_user_id)
        
        if not user:
            await message.answer(f"❌ Пользователь с ID <code>{target_user_id}</code> не найден!", parse_mode=ParseMode.HTML)
            return
        
        # Получаем данные пользователя
        user_id_val = user[0]
        username = user[1] or ""
        full_name = user[2] or "Без имени"
        balance = user[3] or 0
        referrals_count = user[4] or 0
        referral_from = user[5]
        join_date = user[6] or "Неизвестно"
        last_activity = user[7] or "Неизвестно"
        
        # Информация о пригласившем
        referrer_info = ""
        if referral_from and referral_from != 0:
            referrer = get_user(referral_from)
            if referrer:
                referrer_name = referrer[2] or "Неизвестно"
                referrer_username = f"@{referrer[1]}" if referrer[1] else "без юзернейма"
                referrer_info = f"\n👤 <b>Пригласил:</b> {referrer_name} ({referrer_username})"
        
        # Получаем статистику рефералов
        conn = sqlite3.connect('referral_bot.db')
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users WHERE referral_from = ?', (target_user_id,))
        invited_count = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT COUNT(*) FROM transactions WHERE user_id = ?', (target_user_id,))
        transactions_count = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT COUNT(*) FROM withdrawals WHERE user_id = ?', (target_user_id,))
        withdrawals_count = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type = "referral_bonus"', (target_user_id,))
        earned_from_refs = cursor.fetchone()[0] or 0
        
        conn.close()
        
        user_info = (
            f"👤 <b>Информация о пользователе</b>\n\n"
            f"🆔 <b>ID:</b> <code>{user_id_val}</code>\n"
            f"👤 <b>Имя:</b> {full_name}\n"
            f"📧 <b>Юзернейм:</b> @{username if username else 'Не указан'}\n"
            f"💰 <b>Баланс:</b> <b>{balance}г</b>\n\n"
            f"📊 <b>Статистика:</b>\n"
            f"• Рефералов приглашено: <b>{referrals_count}</b>\n"
            f"• Заработано с рефералов: <b>{earned_from_refs}г</b>\n"
            f"• Транзакций: <b>{transactions_count}</b>\n"
            f"• Заявок на вывод: <b>{withdrawals_count}</b>\n"
            f"{referrer_info}\n\n"
            f"📅 <b>Дата регистрации:</b> {join_date[:10] if len(join_date) >= 10 else join_date}\n"
            f"🕒 <b>Последняя активность:</b> {last_activity[:16] if last_activity else 'Неизвестно'}"
        )
        
        # Клавиатура с действиями
        keyboard = InlineKeyboardBuilder()
        keyboard.add(InlineKeyboardButton(text="💰 Изменить баланс", callback_data=f"edit_balance_{target_user_id}"))
        keyboard.add(InlineKeyboardButton(text="📋 Транзакции", callback_data=f"user_transactions_{target_user_id}"))
        keyboard.add(InlineKeyboardButton(text="📦 Выводы", callback_data=f"user_withdrawals_{target_user_id}"))
        keyboard.adjust(2)
        
        await message.answer(user_info, parse_mode=ParseMode.HTML, reply_markup=keyboard.as_markup())
        
    except ValueError:
        await message.answer("❌ Неверный формат ID. ID должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка получения информации о пользователе: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")

@dp.callback_query(F.data == "user_list")
async def user_list_handler(callback: CallbackQuery):
    """Список пользователей"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users ORDER BY join_date DESC LIMIT 20')
    users = cursor.fetchall()
    conn.close()
    
    if not users:
        stats_text = "📭 <b>Нет пользователей в базе данных</b>"
    else:
        stats_text = f"👥 <b>Последние 20 пользователей</b>\n\n"
        
        for i, user in enumerate(users, 1):
            user_id_val = user[0]
            username = user[1] or ""
            full_name = user[2] or "Без имени"
            balance = user[3] or 0
            referrals_count = user[4] or 0
            join_date = user[6] or "Неизвестно"
            
            username_display = f"@{username}" if username else "без юзернейма"
            join_date_formatted = join_date[:10] if len(join_date) >= 10 else join_date
            
            stats_text += (
                f"{i}. <b>{full_name}</b> ({username_display})\n"
                f"   🆔 <code>{user_id_val}</code> | 💰 {balance}г\n"
                f"   👥 {referrals_count} реф. | 📅 {join_date_formatted}\n\n"
            )
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="🔍 Поиск пользователя", callback_data="search_user"))
    keyboard.add(InlineKeyboardButton(text="🔄 Обновить", callback_data="user_list"))
    keyboard.add(InlineKeyboardButton(text="👑 В админ-меню", callback_data="admin_menu_back"))
    keyboard.adjust(2)
    
    await edit_with_photo(callback, 'admin', stats_text, keyboard.as_markup())
    await callback.answer()

# ===================== ОБРАБОТЧИКИ ДЛЯ УПРАВЛЕНИЯ ПРОМОКОДАМИ =====================

@dp.callback_query(F.data == "create_promo_code")
async def create_promo_code_handler(callback: CallbackQuery, state: FSMContext):
    """Создание промокода"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    await callback.message.answer(
        "🎁 <b>Создание промокода</b>\n\n"
        "Введите код промокода (только латинские буквы и цифры):",
        parse_mode=ParseMode.HTML
    )
    
    await state.set_state(AddPromoCodeStates.waiting_for_promo_code)
    await callback.answer()

@dp.message(AddPromoCodeStates.waiting_for_promo_code)
async def process_promo_code_name(message: Message, state: FSMContext):
    """Обработка названия промокода"""
    promo_code = message.text.strip().upper()
    
    if not promo_code.isalnum():
        await message.answer(
            "❌ Промокод должен содержать только латинские буквы и цифры.\n"
            "Попробуйте еще раз:"
        )
        return
    
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM promo_codes WHERE code = ?', (promo_code,))
    if cursor.fetchone():
        conn.close()
        await message.answer(
            "❌ Промокод уже существует. Введите другой код:"
        )
        return
    conn.close()
    
    await state.update_data(promo_code=promo_code)
    await state.set_state(AddPromoCodeStates.waiting_for_promo_amount)
    
    await message.answer(
        f"✅ Код промокода: <b>{promo_code}</b>\n\n"
        f"Введите сумму бонуса (например: 100):",
        parse_mode=ParseMode.HTML
    )

@dp.message(AddPromoCodeStates.waiting_for_promo_amount)
async def process_promo_amount(message: Message, state: FSMContext):
    """Обработка суммы промокода"""
    try:
        amount = float(message.text.strip())
        if amount <= 0:
            await message.answer("❌ Сумма должна быть положительной. Попробуйте еще раз:")
            return
    except ValueError:
        await message.answer("❌ Неверный формат суммы. Введите число (например: 100):")
        return
    
    await state.update_data(amount=amount)
    await state.set_state(AddPromoCodeStates.waiting_for_promo_uses)
    
    await message.answer(
        f"✅ Сумма бонуса: <b>{amount}г</b>\n\n"
        f"Введите максимальное количество использований (например: 10):",
        parse_mode=ParseMode.HTML
    )

@dp.message(AddPromoCodeStates.waiting_for_promo_uses)
async def process_promo_uses(message: Message, state: FSMContext):
    """Обработка количества использований"""
    try:
        max_uses = int(message.text.strip())
        if max_uses <= 0:
            await message.answer("❌ Количество должно быть больше 0. Попробуйте еще раз:")
            return
    except ValueError:
        await message.answer("❌ Неверный формат. Введите целое число (например: 10):")
        return
    
    await state.update_data(max_uses=max_uses)
    await state.set_state(AddPromoCodeStates.waiting_for_promo_expires)
    
    await message.answer(
        f"✅ Максимальное использование: <b>{max_uses} раз</b>\n\n"
        f"Введите срок действия в днях (например: 30):",
        parse_mode=ParseMode.HTML
    )

@dp.message(AddPromoCodeStates.waiting_for_promo_expires)
async def process_promo_expires(message: Message, state: FSMContext):
    """Обработка срока действия"""
    try:
        expires_days = int(message.text.strip())
        if expires_days <= 0:
            await message.answer("❌ Срок должен быть больше 0 дней. Попробуйте еще раз:")
            return
    except ValueError:
        await message.answer("❌ Неверный формат. Введите число дней (например: 30):")
        return
    
    data = await state.get_data()
    promo_code = data.get('promo_code')
    amount = data.get('amount')
    max_uses = data.get('max_uses')
    
    success = create_promo_code(
        code=promo_code,
        amount=amount,
        max_uses=max_uses,
        created_by=message.from_user.id,
        expires_days=expires_days
    )
    
    if success:
        result_text = (
            f"✅ <b>Промокод успешно создан!</b>\n\n"
            f"🎁 <b>Код:</b> <code>{promo_code}</code>\n"
            f"💰 <b>Сумма:</b> {amount}г\n"
            f"🔄 <b>Использований:</b> {max_uses} раз\n"
            f"📅 <b>Срок действия:</b> {expires_days} дней\n\n"
            f"Промокод активен и готов к использованию!"
        )
    else:
        result_text = "❌ Ошибка создания промокода!"
    
    await message.answer(result_text, parse_mode=ParseMode.HTML)
    await state.clear()

@dp.callback_query(F.data == "promo_codes_list")
async def promo_codes_list_handler(callback: CallbackQuery):
    """Список промокодов"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    promos = get_promo_codes(active_only=False)
    
    if not promos:
        promos_text = "📭 <b>Нет созданных промокодов</b>"
    else:
        promos_text = "🎁 <b>Список всех промокодов</b>\n\n"
        
        for promo in promos:
            code = promo[1]
            amount = promo[2]
            max_uses = promo[3]
            used_count = promo[4]
            expires_date = promo[7]
            is_active = promo[8]
            
            status = "🟢" if is_active == 1 else "🔴"
            expires_info = f"до {expires_date[:10]}" if expires_date else "без срока"
            
            promos_text += (
                f"{status} <b>{code}</b>\n"
                f"   💰 Сумма: {amount}г\n"
                f"   🎯 Использовано: {used_count}/{max_uses}\n"
                f"   📅 {expires_info}\n\n"
            )
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="➕ Создать промокод", callback_data="create_promo_code"))
    keyboard.add(InlineKeyboardButton(text="🔄 Обновить список", callback_data="promo_codes_list"))
    keyboard.add(InlineKeyboardButton(text="👑 В админ-меню", callback_data="admin_menu_back"))
    keyboard.adjust(2)
    
    await edit_with_photo(callback, 'admin', promos_text, keyboard.as_markup())
    await callback.answer()

@dp.message(Command("delete_promo"))
async def delete_promo_command(message: Message):
    """Команда удаления промокода"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("⛔ У вас нет прав администратора!")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer(
                "❌ Неверный формат. Используйте:\n"
                "<code>/delete_promo КОД_ПРОМОКОДА</code>\n\n"
                "Пример:\n"
                "<code>/delete_promo SUMMER2024</code>",
                parse_mode=ParseMode.HTML
            )
            return
        
        promo_code = parts[1].upper()
        success = delete_promo_code(promo_code)
        
        if success:
            await message.answer(f"✅ Промокод <code>{promo_code}</code> удален!", parse_mode=ParseMode.HTML)
        else:
            await message.answer(f"❌ Промокод <code>{promo_code}</code> не найден!", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Ошибка удаления промокода: {e}")
        await message.answer(f"❌ Ошибка: {e}")

# ===================== ОБРАБОТЧИКИ ДЛЯ СОЗДАНИЯ ССЫЛОК =====================

@dp.callback_query(F.data == "create_giveaway_link")
async def create_giveaway_link_handler(callback: CallbackQuery, state: FSMContext):
    """Создание раздаточной ссылки"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    await callback.message.answer(
        "🔗 <b>Создание раздаточной ссылки</b>\n\n"
        "Введите количество голды, которое получит пользователь (например: 50):",
        parse_mode=ParseMode.HTML
    )
    
    await state.set_state(CreateLinkStates.waiting_for_link_amount)
    await callback.answer()

@dp.message(CreateLinkStates.waiting_for_link_amount)
async def process_link_amount(message: Message, state: FSMContext):
    """Обработка суммы ссылки"""
    try:
        amount = float(message.text.strip())
        if amount <= 0:
            await message.answer("❌ Сумма должна быть положительной. Попробуйте еще раз:")
            return
    except ValueError:
        await message.answer("❌ Неверный формат суммы. Введите число (например: 50):")
        return
    
    await state.update_data(amount=amount)
    await state.set_state(CreateLinkStates.waiting_for_link_uses)
    
    await message.answer(
        f"✅ Сумма бонуса: <b>{amount}г</b>\n\n"
        f"Введите максимальное количество активаций (например: 100):",
        parse_mode=ParseMode.HTML
    )

@dp.message(CreateLinkStates.waiting_for_link_uses)
async def process_link_uses(message: Message, state: FSMContext):
    """Обработка количества активаций"""
    try:
        max_uses = int(message.text.strip())
        if max_uses <= 0:
            await message.answer("❌ Количество должно быть больше 0. Попробуйте еще раз:")
            return
    except ValueError:
        await message.answer("❌ Неверный формат. Введите целое число (например: 100):")
        return
    
    await state.update_data(max_uses=max_uses)
    await state.set_state(CreateLinkStates.waiting_for_link_name)
    
    await message.answer(
        f"✅ Максимальное использование: <b>{max_uses} раз</b>\n\n"
        f"Введите название для ссылки (например: Бонусная раздача):",
        parse_mode=ParseMode.HTML
    )

@dp.message(CreateLinkStates.waiting_for_link_name)
async def process_link_name(message: Message, state: FSMContext):
    """Обработка названия ссылки"""
    link_name = message.text.strip()
    
    if not link_name:
        link_name = "Бонусная ссылка"
    
    data = await state.get_data()
    amount = data.get('amount')
    max_uses = data.get('max_uses')
    
    # Создаем ссылку
    link_code = create_giveaway_link(
        amount=amount,
        max_uses=max_uses,
        created_by=message.from_user.id,
        name=link_name,
        expires_days=365  # Год по умолчанию
    )
    
    bot_username = (await bot.get_me()).username
    giveaway_link = f"https://t.me/{bot_username}?start={link_code}"
    
    result_text = (
        f"✅ <b>Раздаточная ссылка успешно создана!</b>\n\n"
        f"🔗 <b>Название:</b> {link_name}\n"
        f"💰 <b>Сумма:</b> {amount}г\n"
        f"🔄 <b>Активаций:</b> {max_uses} раз\n"
        f"📅 <b>Срок действия:</b> 365 дней\n\n"
        f"🔗 <b>Ссылка:</b>\n"
        f"<code>{giveaway_link}</code>\n\n"
        f"📝 <b>Код:</b> <code>{link_code}</code>\n\n"
        f"Просто отправьте эту ссылку пользователям!"
    )
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="🔗 Поделиться ссылкой", url=f"https://t.me/share/url?url={giveaway_link}&text=Получи%20{amount}г%20голды%20бесплатно!"))
    keyboard.add(InlineKeyboardButton(text="📋 Список ссылок", callback_data="giveaway_links_list"))
    keyboard.adjust(1)
    
    await message.answer(result_text, parse_mode=ParseMode.HTML, reply_markup=keyboard.as_markup())
    await state.clear()

@dp.callback_query(F.data == "giveaway_links_list")
async def giveaway_links_list_handler(callback: CallbackQuery):
    """Список раздаточных ссылок"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    links = get_giveaway_links(active_only=False)
    bot_username = (await bot.get_me()).username
    
    if not links:
        links_text = "📭 <b>Нет созданных ссылок</b>"
    else:
        links_text = "🔗 <b>Список всех раздаточных ссылок</b>\n\n"
        
        for link in links[:10]:
            link_code = link[1]
            amount = link[2]
            max_uses = link[3]
            used_count = link[4]
            expires_date = link[7]
            is_active = link[8]
            name = link[9]
            
            status = "🟢" if is_active == 1 else "🔴"
            expires_info = f"до {expires_date[:10]}" if expires_date else "без срока"
            giveaway_link = f"https://t.me/{bot_username}?start={link_code}"
            
            links_text += (
                f"{status} <b>{name}</b>\n"
                f"   🔗 Ссылка: {giveaway_link}\n"
                f"   💰 Сумма: {amount}г\n"
                f"   🎯 Использовано: {used_count}/{max_uses}\n"
                f"   📅 {expires_info}\n\n"
            )
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="➕ Создать ссылку", callback_data="create_giveaway_link"))
    keyboard.add(InlineKeyboardButton(text="🔄 Обновить список", callback_data="giveaway_links_list"))
    keyboard.add(InlineKeyboardButton(text="👑 В админ-меню", callback_data="admin_menu_back"))
    keyboard.adjust(2)
    
    await edit_with_photo(callback, 'admin', links_text, keyboard.as_markup())
    await callback.answer()

@dp.message(Command("delete_link"))
async def delete_link_command(message: Message):
    """Команда удаления ссылки"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("⛔ У вас нет прав администратора!")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer(
                "❌ Неверный формат. Используйте:\n"
                "<code>/delete_link КОД_ССЫЛКИ</code>\n\n"
                "Пример:\n"
                "<code>/delete_link abc123def456</code>",
                parse_mode=ParseMode.HTML
            )
            return
        
        link_code = parts[1].lower()
        success = delete_giveaway_link(link_code)
        
        if success:
            await message.answer(f"✅ Ссылка <code>{link_code}</code> удалена!", parse_mode=ParseMode.HTML)
        else:
            await message.answer(f"❌ Ссылка <code>{link_code}</code> не найдена!", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Ошибка удаления ссылки: {e}")
        await message.answer(f"❌ Ошибка: {e}")

# ===================== ОСТАЛЬНЫЕ ФИКСЫ =====================

@dp.callback_query(F.data == "add_channel")
async def add_channel_handler(callback: CallbackQuery, state: FSMContext):
    """Добавление канала"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    await callback.message.answer(
        "📢 <b>Добавление обязательного канала</b>\n\n"
        "Введите ID канала (например: -1001234567890):",
        parse_mode=ParseMode.HTML
    )
    
    await state.set_state(AddChannelStates.waiting_for_channel_id)
    await callback.answer()

@dp.message(AddChannelStates.waiting_for_channel_id)
async def process_channel_id(message: Message, state: FSMContext):
    """Обработка ID канала"""
    try:
        channel_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Неверный формат ID. Введите число (например: -1001234567890):")
        return
    
    await state.update_data(channel_id=channel_id)
    await state.set_state(AddChannelStates.waiting_for_channel_username)
    
    await message.answer(
        f"✅ ID канала: <code>{channel_id}</code>\n\n"
        f"Введите юзернейм канала (без @, например: k1lossez):",
        parse_mode=ParseMode.HTML
    )

@dp.message(AddChannelStates.waiting_for_channel_username)
async def process_channel_username(message: Message, state: FSMContext):
    """Обработка юзернейма канала"""
    username = message.text.strip().replace('@', '')
    
    if not username:
        await message.answer("❌ Юзернейм не может быть пустым. Попробуйте еще раз:")
        return
    
    await state.update_data(channel_username=username)
    await state.set_state(AddChannelStates.waiting_for_channel_name)
    
    await message.answer(
        f"✅ Юзернейм: @{username}\n\n"
        f"Введите название канала (например: K1LOSS EZ):",
        parse_mode=ParseMode.HTML
    )

@dp.message(AddChannelStates.waiting_for_channel_name)
async def process_channel_name(message: Message, state: FSMContext):
    """Обработка названия канала"""
    channel_name = message.text.strip()
    
    if not channel_name:
        await message.answer("❌ Название не может быть пустым. Попробуйте еще раз:")
        return
    
    await state.update_data(channel_name=channel_name)
    await state.set_state(AddChannelStates.waiting_for_invite_link)
    
    await message.answer(
        f"✅ Название: {channel_name}\n\n"
        f"Введите ссылку-приглашение (например: https://t.me/k1lossez):",
        parse_mode=ParseMode.HTML
    )

@dp.message(AddChannelStates.waiting_for_invite_link)
async def process_channel_invite_link(message: Message, state: FSMContext):
    """Обработка ссылки-приглашения"""
    invite_link = message.text.strip()
    
    if not (invite_link.startswith('https://t.me/') or invite_link.startswith('t.me/')):
        await message.answer("❌ Неверный формат ссылки. Должна начинаться с https://t.me/ или t.me/\nПопробуйте еще раз:")
        return
    
    data = await state.get_data()
    channel_id = data.get('channel_id')
    channel_username = data.get('channel_username')
    channel_name = data.get('channel_name')
    
    channel_data = {
        "id": channel_id,
        "username": channel_username,
        "name": channel_name,
        "invite_link": invite_link if invite_link.startswith('https://') else f"https://{invite_link}"
    }
    
    success = add_channel_to_db(channel_data)
    
    if success:
        result_text = (
            f"✅ <b>Канал успешно добавлен!</b>\n\n"
            f"📢 <b>Название:</b> {channel_name}\n"
            f"🆔 <b>ID:</b> <code>{channel_id}</code>\n"
            f"📧 <b>Юзернейм:</b> @{channel_username}\n"
            f"🔗 <b>Ссылка:</b> {invite_link}\n\n"
            f"Теперь пользователи должны подписаться на этот канал."
        )
    else:
        result_text = "❌ Ошибка добавления канала!"
    
    await message.answer(result_text, parse_mode=ParseMode.HTML)
    await state.clear()

@dp.callback_query(F.data == "remove_channel")
async def remove_channel_handler(callback: CallbackQuery):
    """Удаление канала"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    if not REQUIRED_CHANNELS:
        await callback.answer("❌ Нет каналов для удаления!", show_alert=True)
        return
    
    channels_text = "🗑 <b>Удаление канала</b>\n\n"
    channels_text += "Введите ID канала для удаления:\n\n"
    channels_text += "<b>Текущие каналы:</b>\n"
    
    for channel in REQUIRED_CHANNELS:
        if isinstance(channel, dict):
            channels_text += f"• <code>{channel.get('id')}</code> - {channel.get('name', 'Канал ' + str(channel.get('id', '')))}\n"
        else:
            channels_text += f"• <code>{channel}</code>\n"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="↩️ Назад к списку", callback_data="manage_channels"))
    keyboard.add(InlineKeyboardButton(text="👑 В админ-меню", callback_data="admin_menu_back"))
    keyboard.adjust(2)
    
    await callback.message.answer(channels_text, parse_mode=ParseMode.HTML, reply_markup=keyboard.as_markup())
    await callback.answer()

@dp.message(Command("remove_channel"))
async def remove_channel_command(message: Message):
    """Команда удаления канала"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("⛔ У вас нет прав администратора!")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer(
                "❌ Неверный формат. Используйте:\n"
                "<code>/remove_channel ID_КАНАЛА</code>\n\n"
                "Пример:\n"
                "<code>/remove_channel -1003525909692</code>",
                parse_mode=ParseMode.HTML
            )
            return
        
        channel_id = int(parts[1])
        success = remove_channel_from_db(channel_id)
        
        if success:
            await message.answer(f"✅ Канал <code>{channel_id}</code> удален!", parse_mode=ParseMode.HTML)
        else:
            await message.answer(f"❌ Канал <code>{channel_id}</code> не найден!", parse_mode=ParseMode.HTML)
    except ValueError:
        await message.answer("❌ Неверный формат ID. ID должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка удаления канала: {e}")
        await message.answer(f"❌ Ошибка: {e}")

@dp.callback_query(F.data == "add_admin")
async def add_admin_handler(callback: CallbackQuery, state: FSMContext):
    """Добавление администратора"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    if not is_super_admin(user_id):
        await callback.answer("⛔ Только суперадмин может добавлять админов!", show_alert=True)
        return
    
    await callback.message.answer(
        "👑 <b>Добавление администратора</b>\n\n"
        "Введите ID пользователя (например: 1234567890):",
        parse_mode=ParseMode.HTML
    )
    
    await state.set_state(AddAdminStates.waiting_for_admin_id)
    await callback.answer()

@dp.message(AddAdminStates.waiting_for_admin_id)
async def process_admin_id(message: Message, state: FSMContext):
    """Обработка ID администратора"""
    try:
        admin_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Неверный формат ID. Введите число (например: 1234567890):")
        return
    
    user = get_user(admin_id)
    if not user:
        await message.answer(f"❌ Пользователь с ID <code>{admin_id}</code> не найден в базе данных!", parse_mode=ParseMode.HTML)
        await state.clear()
        return
    
    success = add_admin_to_db(admin_id, is_super=False, added_by=message.from_user.id)
    
    if success:
        user_name = user[2]  # full_name
        result_text = (
            f"✅ <b>Администратор успешно добавлен!</b>\n\n"
            f"👤 <b>Пользователь:</b> {user_name}\n"
            f"🆔 <b>ID:</b> <code>{admin_id}</code>\n"
            f"👑 <b>Статус:</b> Администратор\n\n"
            f"Теперь пользователь имеет доступ к панели администратора."
        )
        
        try:
            await bot.send_message(
                admin_id,
                f"👑 <b>Вас назначили администратором!</b>\n\n"
                f"Теперь у вас есть доступ к панели администратора.\n"
                f"Для входа используйте команду /admin",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Ошибка уведомления нового админа: {e}")
            result_text += "\n\n⚠️ Не удалось отправить уведомление новому администратору."
    else:
        result_text = f"❌ Пользователь <code>{admin_id}</code> уже является администратором!"
    
    await message.answer(result_text, parse_mode=ParseMode.HTML)
    await state.clear()

@dp.callback_query(F.data == "remove_admin")
async def remove_admin_handler(callback: CallbackQuery):
    """Удаление администратора"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    if not is_super_admin(user_id):
        await callback.answer("⛔ Только суперадмин может удалять админов!", show_alert=True)
        return
    
    admins = get_all_admins()
    
    if len(admins) <= 1:
        await callback.answer("❌ Нельзя удалить последнего администратора!", show_alert=True)
        return
    
    admins_text = "🗑 <b>Удаление администратора</b>\n\n"
    admins_text += "Введите ID администратора для удаления:\n\n"
    admins_text += "<b>Текущие администраторы:</b>\n"
    
    for admin in admins:
        admin_id = admin[0]
        is_super = admin[1]
        
        user_info = get_user(admin_id)
        if user_info:
            name = user_info[2]  # full_name
        else:
            name = "Неизвестно"
        
        status = "🟢 Суперадмин" if is_super == 1 else "🔵 Админ"
        admins_text += f"• <code>{admin_id}</code> - {name} {status}\n"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="↩️ Назад к списку", callback_data="manage_admins"))
    keyboard.add(InlineKeyboardButton(text="👑 В админ-меню", callback_data="admin_menu_back"))
    keyboard.adjust(2)
    
    await callback.message.answer(admins_text, parse_mode=ParseMode.HTML, reply_markup=keyboard.as_markup())
    await callback.answer()

@dp.message(Command("remove_admin"))
async def remove_admin_command(message: Message):
    """Команда удаления администратора"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("⛔ У вас нет прав администратора!")
        return
    
    if not is_super_admin(user_id):
        await message.answer("⛔ Только суперадмин может удалять админов!")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer(
                "❌ Неверный формат. Используйте:\n"
                "<code>/remove_admin ID_АДМИНИСТРАТОРА</code>\n\n"
                "Пример:\n"
                "<code>/remove_admin 1234567890</code>",
                parse_mode=ParseMode.HTML
            )
            return
        
        admin_id = int(parts[1])
        
        if admin_id == user_id:
            await message.answer("❌ Нельзя удалить самого себя!")
            return
        
        if is_super_admin(admin_id) and not is_super_admin(user_id):
            await message.answer("❌ Нельзя удалить суперадмина!")
            return
        
        success = remove_admin_from_db(admin_id)
        
        if success:
            await message.answer(f"✅ Администратор <code>{admin_id}</code> удален!", parse_mode=ParseMode.HTML)
            
            try:
                await bot.send_message(
                    admin_id,
                    f"👑 <b>Ваши права администратора были отозваны!</b>\n\n"
                    f"Теперь у вас нет доступа к панели администратора.",
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Ошибка уведомления удаленного админа: {e}")
        else:
            await message.answer(f"❌ Администратор <code>{admin_id}</code> не найден!", parse_mode=ParseMode.HTML)
    except ValueError:
        await message.answer("❌ Неверный формат ID. ID должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка удаления администратора: {e}")
        await message.answer(f"❌ Ошибка: {e}")

@dp.callback_query(F.data == "withdrawal_pending")
async def withdrawal_pending_handler(callback: CallbackQuery):
    """Ожидающие заявки на вывод"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    withdrawals = get_withdrawals(status='pending', limit=10)
    
    if not withdrawals:
        stats_text = "✅ <b>Нет ожидающих заявок на вывод</b>"
    else:
        stats_text = f"⏳ <b>Ожидающие заявки на вывод ({len(withdrawals)})</b>\n\n"
        
        total_amount = 0
        for wd in withdrawals:
            wd_id = wd[0]
            wd_user_id = wd[1]
            skin_name = wd[2]
            pattern = wd[3]
            amount = wd[5]
            created_date = wd[9]
            
            user = get_user(wd_user_id)
            if user:
                user_name = user[2]
                user_username = f"@{user[1]}" if user[1] else "без юзернейма"
            else:
                user_name = "Неизвестно"
                user_username = "без юзернейма"
            
            total_amount += amount
            
            stats_text += (
                f"📦 <b>Заявка #{wd_id}</b>\n"
                f"👤 {user_name} ({user_username})\n"
                f"🆔 ID: <code>{wd_user_id}</code>\n"
                f"💰 Сумма: {amount}г\n"
                f"🎮 Скин: {skin_name[:20]}...\n"
                f"🔢 Паттерн: {pattern}\n"
                f"📅 Дата: {created_date[:16]}\n\n"
            )
        
        stats_text += f"💰 <b>Общая сумма:</b> <b>{total_amount}г</b>\n"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="🔄 Обновить", callback_data="withdrawal_pending"))
    keyboard.add(InlineKeyboardButton(text="📦 Все заявки", callback_data="withdrawal_requests"))
    keyboard.add(InlineKeyboardButton(text="👑 В админ-меню", callback_data="admin_menu_back"))
    keyboard.adjust(2)
    
    await edit_with_photo(callback, 'admin', stats_text, keyboard.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "withdrawal_completed")
async def withdrawal_completed_handler(callback: CallbackQuery):
    """Выполненные заявки на вывод"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    withdrawals = get_withdrawals(status='completed', limit=10)
    
    if not withdrawals:
        stats_text = "📭 <b>Нет выполненных заявок на вывод</b>"
    else:
        stats_text = f"✅ <b>Выполненные заявки на вывод ({len(withdrawals)})</b>\n\n"
        
        total_amount = 0
        for wd in withdrawals:
            wd_id = wd[0]
            wd_user_id = wd[1]
            amount = wd[5]
            admin_username = wd[8]
            processed_date = wd[10]
            
            user = get_user(wd_user_id)
            if user:
                user_name = user[2]
            else:
                user_name = "Неизвестно"
            
            total_amount += amount
            
            stats_text += (
                f"✅ <b>#{wd_id}</b> - {amount}г\n"
                f"👤 {user_name} | 👷 {admin_username or 'Неизвестно'}\n"
                f"📅 {processed_date[:10] if processed_date else 'Неизвестно'}\n\n"
            )
        
        stats_text += f"💰 <b>Всего выплачено:</b> <b>{total_amount}г</b>\n"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="🔄 Обновить", callback_data="withdrawal_completed"))
    keyboard.add(InlineKeyboardButton(text="📦 Все заявки", callback_data="withdrawal_requests"))
    keyboard.add(InlineKeyboardButton(text="👑 В админ-меню", callback_data="admin_menu_back"))
    keyboard.adjust(2)
    
    await edit_with_photo(callback, 'admin', stats_text, keyboard.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "withdrawal_rejected")
async def withdrawal_rejected_handler(callback: CallbackQuery):
    """Отклоненные заявки на вывод"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    withdrawals = get_withdrawals(status='rejected', limit=10)
    
    if not withdrawals:
        stats_text = "📭 <b>Нет отклоненных заявок на вывод</b>"
    else:
        stats_text = f"❌ <b>Отклоненные заявки на вывод ({len(withdrawals)})</b>\n\n"
        
        for wd in withdrawals:
            wd_id = wd[0]
            wd_user_id = wd[1]
            amount = wd[5]
            admin_username = wd[8]
            processed_date = wd[10]
            
            user = get_user(wd_user_id)
            if user:
                user_name = user[2]
            else:
                user_name = "Неизвестно"
            
            stats_text += (
                f"❌ <b>#{wd_id}</b> - {amount}г\n"
                f"👤 {user_name} | 👷 {admin_username or 'Неизвестно'}\n"
                f"📅 {processed_date[:10] if processed_date else 'Неизвестно'}\n\n"
            )
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="🔄 Обновить", callback_data="withdrawal_rejected"))
    keyboard.add(InlineKeyboardButton(text="📦 Все заявки", callback_data="withdrawal_requests"))
    keyboard.add(InlineKeyboardButton(text="👑 В админ-меню", callback_data="admin_menu_back"))
    keyboard.adjust(2)
    
    await edit_with_photo(callback, 'admin', stats_text, keyboard.as_markup())
    await callback.answer()

# ===================== ОБРАБОТЧИКИ ДЛЯ НАСТРОЕК БОНУСОВ =====================

@dp.callback_query(F.data == "set_referral_bonus")
async def set_referral_bonus_handler(callback: CallbackQuery, state: FSMContext):
    """Установка бонуса за реферала"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    current_bonus = get_referral_bonus()
    
    await callback.message.answer(
        f"💰 <b>Изменение бонуса за реферала</b>\n\n"
        f"Текущее значение: <b>{current_bonus}г</b>\n\n"
        f"Введите новое значение (например: 500):",
        parse_mode=ParseMode.HTML
    )
    
    await state.set_state(BonusSettingsStates.waiting_for_referral_bonus)
    await callback.answer()

@dp.message(BonusSettingsStates.waiting_for_referral_bonus)
async def process_referral_bonus(message: Message, state: FSMContext):
    """Обработка нового бонуса за реферала"""
    try:
        new_bonus = float(message.text.strip())
        if new_bonus < 0:
            await message.answer("❌ Сумма должна быть положительной. Попробуйте еще раз:")
            return
    except ValueError:
        await message.answer("❌ Неверный формат. Введите число (например: 500):")
        return
    
    old_bonus = get_referral_bonus()
    update_setting('referral_bonus', str(new_bonus))
    
    result_text = (
        f"✅ <b>Бонус за реферала изменен!</b>\n\n"
        f"💰 <b>Старое значение:</b> {old_bonus}г\n"
        f"💰 <b>Новое значение:</b> {new_bonus}г\n\n"
        f"Изменение вступит в силу для новых рефералов."
    )
    
    await message.answer(result_text, parse_mode=ParseMode.HTML)
    await state.clear()

@dp.callback_query(F.data == "set_welcome_bonus")
async def set_welcome_bonus_handler(callback: CallbackQuery, state: FSMContext):
    """Установка стартового бонуса"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    current_bonus = get_welcome_bonus()
    
    await callback.message.answer(
        f"🎁 <b>Изменение стартового бонуса</b>\n\n"
        f"Текущее значение: <b>{current_bonus}г</b>\n\n"
        f"Введите новое значение (например: 100):",
        parse_mode=ParseMode.HTML
    )
    
    await state.set_state(BonusSettingsStates.waiting_for_welcome_bonus)
    await callback.answer()

@dp.message(BonusSettingsStates.waiting_for_welcome_bonus)
async def process_welcome_bonus(message: Message, state: FSMContext):
    """Обработка нового стартового бонуса"""
    try:
        new_bonus = float(message.text.strip())
        if new_bonus < 0:
            await message.answer("❌ Сумма должна быть положительной. Попробуйте еще раз:")
            return
    except ValueError:
        await message.answer("❌ Неверный формат. Введите число (например: 100):")
        return
    
    old_bonus = get_welcome_bonus()
    update_setting('welcome_bonus', str(new_bonus))
    
    result_text = (
        f"✅ <b>Стартовый бонус изменен!</b>\n\n"
        f"🎁 <b>Старое значение:</b> {old_bonus}г\n"
        f"🎁 <b>Новое значение:</b> {new_bonus}г\n\n"
        f"Изменение вступит в силу для новых пользователей."
    )
    
    await message.answer(result_text, parse_mode=ParseMode.HTML)
    await state.clear()

@dp.callback_query(F.data == "set_min_withdrawal")
async def set_min_withdrawal_handler(callback: CallbackQuery, state: FSMContext):
    """Установка минимального вывода"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    current_min = float(get_setting('min_withdrawal', '100'))
    
    await callback.message.answer(
        f"💸 <b>Изменение минимального вывода</b>\n\n"
        f"Текущее значение: <b>{current_min}г</b>\n\n"
        f"Введите новое значение (например: 50):",
        parse_mode=ParseMode.HTML
    )
    
    await state.set_state(BonusSettingsStates.waiting_for_min_withdrawal)
    await callback.answer()

@dp.message(BonusSettingsStates.waiting_for_min_withdrawal)
async def process_min_withdrawal(message: Message, state: FSMContext):
    """Обработка нового минимального вывода"""
    try:
        new_min = float(message.text.strip())
        if new_min < 0:
            await message.answer("❌ Сумма должна быть положительной. Попробуйте еще раз:")
            return
    except ValueError:
        await message.answer("❌ Неверный формат. Введите число (например: 50):")
        return
    
    old_min = float(get_setting('min_withdrawal', '100'))
    update_setting('min_withdrawal', str(new_min))
    
    result_text = (
        f"✅ <b>Минимальный вывод изменен!</b>\n\n"
        f"💸 <b>Старое значение:</b> {old_min}г\n"
        f"💸 <b>Новое значение:</b> {new_min}г\n\n"
        f"Пользователи смогут выводить средства от {new_min}г."
    )
    
    await message.answer(result_text, parse_mode=ParseMode.HTML)
    await state.clear()

# ===================== ГЛАВНАЯ ФУНКЦИЯ =====================

async def main():
    """Главная функция запуска бота"""
    print("=" * 70)
    print(f"🤖 {get_setting('bot_name', 'K1LOSS EZ Referral Bot')} запущен!")
    print(f"🔑 Администраторов: {len(ADMIN_IDS)}")
    print(f"📢 Каналов для подписки: {len(REQUIRED_CHANNELS)}")
    print(f"👥 Группа ID: {GROUP_ID}")
    print("=" * 70)
    
    try:
        bot_info = await bot.get_me()
        print(f"🤖 Бот: @{bot_info.username}")
        print(f"🆔 ID бота: {bot_info.id}")
        print(f"👤 Имя бота: {bot_info.first_name}")
    except Exception as e:
        print(f"❌ Ошибка получения информации о боте: {e}")
    
    print("=" * 70)
    
    print("📸 Проверка фото:")
    
    photo_types = ['welcome', 'profile']
    for photo_type in photo_types:
        photo_url = get_photo_url(photo_type)
        photo_file_id = get_setting(f'photo_{photo_type}_file_id', '')
        photo_path = os.path.join(IMAGES_DIR, f'{photo_type}.jpg')
        
        if photo_file_id:
            print(f"  ✅ {photo_type} - file_id установлен")
        elif photo_url:
            print(f"  ✅ {photo_type} - URL установлен")
        elif os.path.exists(photo_path):
            print(f"  ✅ {photo_type}.jpg - локальный файл")
        else:
            print(f"  ⚠️ {photo_type} - не установлено")
    
    print("=" * 70)
    print("🚀 Бот готов к работе!")
    print("=" * 70)
    print("👑 Команда админ-меню: /admin")
    print("📸 Команда для установки фото: /set_photo")
    print("💰 Команда для изменения баланса: /add_balance")
    print("⚙️ Команда для изменения бонуса: /set_referral_bonus /set_welcome_bonus")
    print("🎁 Команда для управления промокодами: /delete_promo")
    print("🔗 Команда для управления ссылками: /delete_link")
    print("📢 Команда для управления каналами: /remove_channel")
    print("👑 Команда для управления админами: /remove_admin")
    print("🔍 Команда для поиска пользователя: /find_user")
    print("👤 Команда для информации о пользователе: /user ID")
    print("=" * 70)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    if not os.path.exists('referral_bot.db'):
        print("📁 Создаю новую базу данных...")
        init_database()
    else:
        print("📁 Загружаю существующую базу данных...")
    
    load_channels_from_db()
    load_admins_from_db()
    
    asyncio.run(main())
