"""
Telegram Bot - النظام المتكامل مع لوحة مفاتيح عربية
Complete Arabic Telegram Bot with Reply Keyboard Menu
"""

import logging
import asyncio
import sqlite3
import datetime
import random
import string
import hashlib
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from contextlib import contextmanager

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, 
    ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton,
    Bot, WebAppInfo
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, ConversationHandler, ContextTypes, filters
)
from telegram.constants import ParseMode

# Configuration
BOT_TOKEN = "توكن البوت"
ADMIN_IDS = [ايدي المستخدم ]  # Replace with actual admin Telegram IDs
DATABASE_NAME = "bot_database.db"

# States
class States(Enum):
    MAIN_MENU = 0
    ADMIN_PANEL = 1
    BROADCAST = 2
    ADD_ADMIN = 3
    REMOVE_ADMIN = 4
    USER_INFO = 5
    SETTINGS = 6
    SUPPORT = 7
    SHOP = 8
    GAMES = 9
    PROFILE = 10
    REFERRAL = 11
    WALLET = 12
    NEWS = 13
    SEARCH = 14
    WAITING_INPUT = 15

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== DATABASE MANAGER ====================

class DatabaseManager:
    def __init__(self, db_name: str):
        self.db_name = db_name
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def init_database(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    language_code TEXT,
                    join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_banned BOOLEAN DEFAULT 0,
                    is_premium BOOLEAN DEFAULT 0,
                    balance REAL DEFAULT 0.0,
                    points INTEGER DEFAULT 0,
                    referral_code TEXT UNIQUE,
                    referred_by INTEGER,
                    message_count INTEGER DEFAULT 0,
                    phone_number TEXT
                )
            ''')
            
            # Admins table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS admins (
                    admin_id INTEGER PRIMARY KEY,
                    added_by INTEGER,
                    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    level INTEGER DEFAULT 1
                )
            ''')
            
            # Settings table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Products table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS products (
                    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    price REAL NOT NULL,
                    stock INTEGER DEFAULT 0,
                    category TEXT,
                    image_url TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Orders table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    product_id INTEGER,
                    quantity INTEGER,
                    total_price REAL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (product_id) REFERENCES products(product_id)
                )
            ''')
            
            # Support tickets
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tickets (
                    ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    subject TEXT,
                    message TEXT,
                    status TEXT DEFAULT 'open',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    resolved_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            # Transactions log
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
                    trans_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    type TEXT,
                    amount REAL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            # Initialize default settings
            default_settings = [
                ('bot_name', '🤖 البوت الذكي'),
                ('welcome_message', 'أهلاً وسهلاً بك في بوتنا! 🌟'),
                ('maintenance_mode', '0'),
                ('referral_bonus', '50'),
                ('min_withdrawal', '100'),
                ('support_channel', '@support'),
                ('bot_version', '2.0')
            ]
            cursor.executemany(
                'INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
                default_settings
            )
            
            # Add default admins
            for admin_id in ADMIN_IDS:
                cursor.execute(
                    'INSERT OR IGNORE INTO admins (admin_id, added_by, level) VALUES (?, ?, ?)',
                    (admin_id, admin_id, 3)
                )
    
    def add_user(self, user_id: int, username: str, first_name: str, 
                 last_name: str, language_code: str, phone: str = None) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            referral_code = self.generate_referral_code(user_id)
            try:
                cursor.execute('''
                    INSERT INTO users (user_id, username, first_name, last_name, 
                                     language_code, referral_code, phone_number)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, username, first_name, last_name, language_code, referral_code, phone))
                return True
            except sqlite3.IntegrityError:
                cursor.execute('''
                    UPDATE users SET last_activity = CURRENT_TIMESTAMP,
                    username = ?, first_name = ?, last_name = ?
                    WHERE user_id = ?
                ''', (username, first_name, last_name, user_id))
                return False
    
    def generate_referral_code(self, user_id: int) -> str:
        code = f"REF{user_id}{''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}"
        return code
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def update_user_activity(self, user_id: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET last_activity = CURRENT_TIMESTAMP,
                message_count = message_count + 1
                WHERE user_id = ?
            ''', (user_id,))
    
    def get_all_users(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM users ORDER BY join_date DESC LIMIT ? OFFSET ?
            ''', (limit, offset))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_users_count(self) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM users')
            return cursor.fetchone()[0]
    
    def ban_user(self, user_id: int, ban: bool = True):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET is_banned = ? WHERE user_id = ?', 
                         (1 if ban else 0, user_id))
    
    def is_admin(self, user_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM admins WHERE admin_id = ?', (user_id,))
            return cursor.fetchone() is not None
    
    def add_admin(self, admin_id: int, added_by: int, level: int = 1):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO admins (admin_id, added_by, level)
                VALUES (?, ?, ?)
            ''', (admin_id, added_by, level))
    
    def remove_admin(self, admin_id: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM admins WHERE admin_id = ?', (admin_id,))
    
    def get_admins(self) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM admins ORDER BY added_date DESC')
            return [dict(row) for row in cursor.fetchall()]
    
    def get_setting(self, key: str) -> str:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
            row = cursor.fetchone()
            return row[0] if row else ''
    
    def set_setting(self, key: str, value: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (key, value))
    
    def add_product(self, name: str, description: str, price: float, 
                    stock: int, category: str, image_url: str = None) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO products (name, description, price, stock, category, image_url)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (name, description, price, stock, category, image_url))
            return cursor.lastrowid
    
    def get_products(self, category: str = None, active_only: bool = True) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM products WHERE 1=1'
            params = []
            if active_only:
                query += ' AND is_active = 1'
            if category:
                query += ' AND category = ?'
                params.append(category)
            query += ' ORDER BY created_at DESC'
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_product(self, product_id: int) -> Optional[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM products WHERE product_id = ?', (product_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def create_order(self, user_id: int, product_id: int, quantity: int) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            product = self.get_product(product_id)
            if not product or product['stock'] < quantity:
                return -1
            
            total_price = product['price'] * quantity
            cursor.execute('''
                INSERT INTO orders (user_id, product_id, quantity, total_price)
                VALUES (?, ?, ?, ?)
            ''', (user_id, product_id, quantity, total_price))
            
            cursor.execute('''
                UPDATE products SET stock = stock - ? WHERE product_id = ?
            ''', (quantity, product_id))
            
            return cursor.lastrowid
    
    def get_user_orders(self, user_id: int) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT o.*, p.name as product_name 
                FROM orders o 
                JOIN products p ON o.product_id = p.product_id 
                WHERE o.user_id = ? 
                ORDER BY o.created_at DESC
            ''', (user_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def update_balance(self, user_id: int, amount: float) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
            current = cursor.fetchone()
            if not current:
                return False
            
            new_balance = current[0] + amount
            if new_balance < 0:
                return False
            
            cursor.execute('UPDATE users SET balance = ? WHERE user_id = ?',
                         (new_balance, user_id))
            
            # Log transaction
            cursor.execute('''
                INSERT INTO transactions (user_id, type, amount, description)
                VALUES (?, ?, ?, ?)
            ''', (user_id, 'credit' if amount > 0 else 'debit', abs(amount), 'Balance update'))
            return True
    
    def add_points(self, user_id: int, points: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET points = points + ? WHERE user_id = ?',
                         (points, user_id))
    
    def create_ticket(self, user_id: int, subject: str, message: str) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO tickets (user_id, subject, message)
                VALUES (?, ?, ?)
            ''', (user_id, subject, message))
            return cursor.lastrowid
    
    def get_user_tickets(self, user_id: int) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM tickets WHERE user_id = ? ORDER BY created_at DESC
            ''', (user_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_transactions(self, user_id: int, limit: int = 10) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM transactions 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            ''', (user_id, limit))
            return [dict(row) for row in cursor.fetchall()]

# Initialize database
db = DatabaseManager(DATABASE_NAME)

# ==================== KEYBOARD LAYOUTS ====================

def get_main_menu_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """Main menu keyboard with control buttons"""
    if db.is_admin(user_id):
        keyboard = [
            ["👤 حسابي", "🛒 المتجر", "💰 المحفظة"],
            ["🎮 الألعاب والترفيه", "📢 الأخبار", "🔗 الإحالات"],
            ["⚙️ الإعدادات", "📞 الدعم الفني", "❓ المساعدة"],
            ["🔐 لوحة تحكم الأدمن"]
        ]
    else:
        keyboard = [
            ["👤 حسابي", "🛒 المتجر", "💰 المحفظة"],
            ["🎮 الألعاب والترفيه", "📢 الأخبار", "🔗 الإحالات"],
            ["⚙️ الإعدادات", "📞 الدعم الفني", "❓ المساعدة"]
        ]
    
    return ReplyKeyboardMarkup(
        keyboard, 
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="اختر من القائمة..."
    )

def get_admin_keyboard() -> ReplyKeyboardMarkup:
    """Admin panel keyboard"""
    keyboard = [
        ["📊 الإحصائيات", "👥 إدارة المستخدمين"],
        ["📢 إذاعة", "⚙️ إعدادات البوت"],
        ["🛍️ إدارة المنتجات", "🎫 التذاكر"],
        ["➕ إضافة أدمن", "➖ إزالة أدمن"],
        ["🔙 العودة للقائمة الرئيسية"]
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )

def get_shop_keyboard() -> ReplyKeyboardMarkup:
    """Shop categories keyboard"""
    keyboard = [
        ["🎮 منتجات رقمية", "👕 ملابس وأزياء"],
        ["📚 كتب ومراجع", "🎁 هدايا واكسسوارات"],
        ["🔍 البحث في المتجر", "🛒 عربة التسوق"],
        ["🔙 العودة للقائمة الرئيسية"]
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )

def get_games_keyboard() -> ReplyKeyboardMarkup:
    """Games menu keyboard"""
    keyboard = [
        ["🎲 لعبة النرد", "🎯 لعبة السهم"],
        ["🎰 آلة الحظ", "❓ تحدي المعرفة"],
        ["🏆 المتصدرين", "🎁 مكافآت يومية"],
        ["🔙 العودة للقائمة الرئيسية"]
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )

def get_wallet_keyboard() -> ReplyKeyboardMarkup:
    """Wallet keyboard"""
    keyboard = [
        ["💳 شحن الرصيد", "💸 سحب الأموال"],
        ["📜 سجل العمليات", "🎁 تحويل نقاط"],
        ["🔙 العودة للقائمة الرئيسية"]
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )

def get_settings_keyboard() -> ReplyKeyboardMarkup:
    """Settings keyboard"""
    keyboard = [
        ["🌐 تغيير اللغة", "🔔 إعدادات الإشعارات"],
        ["👤 تعديل الملف الشخصي", "🔒 الخصوصية والأمان"],
        ["📱 ربط رقم الهاتف", "🌙 الوضع الليلي"],
        ["❌ حذف الحساب", "🔙 العودة للقائمة الرئيسية"]
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )

def get_support_keyboard() -> ReplyKeyboardMarkup:
    """Support keyboard"""
    keyboard = [
        ["📝 إنشاء تذكرة جديدة"],
        ["📋 عرض تذاكري السابقة"],
        ["📞 التواصل المباشر", "❓ الأسئلة الشائعة"],
        ["🔙 العودة للقائمة الرئيسية"]
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Cancel/Back keyboard"""
    keyboard = [["❌ إلغاء"]]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_yes_no_keyboard() -> ReplyKeyboardMarkup:
    """Yes/No confirmation"""
    keyboard = [["✅ نعم", "❌ لا"]]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=True
    )

def remove_keyboard() -> ReplyKeyboardRemove:
    """Remove keyboard"""
    return ReplyKeyboardRemove()

# ==================== MESSAGE TEXTS ====================

TEXTS = {
    'welcome': """
🌟 *أهلاً وسهلاً بك في {bot_name}* 🌟

📌 *المميزات الرئيسية:*
• 🛒 متجر إلكتروني متكامل
• 💰 نظام محفظة إلكترونية
• 🎮 ألعاب ومكافآت يومية
• 🔗 نظام إحالات مع عمولات
• 📞 دعم فني 24/7

🎯 *اختر من القائمة أدناه للبدء:*
""",
    
    'profile': """
👤 *الملف الشخصي*

🆔 *المعرف:* `{user_id}`
👤 *الاسم:* {first_name} {last_name}
📧 *المستخدم:* @{username}
📱 *الهاتف:* {phone}

⭐ *النقاط:* {points} نقطة
💰 *الرصيد:* {balance} ريال
🏆 *الرتبة:* {rank}

📅 *تاريخ الانضمام:* {join_date}
📨 *عدد الرسائل:* {message_count}

🔗 *كود الإحالة:*
`{referral_code}`
""",
    
    'admin_welcome': """
🔐 *لوحة تحكم الأدمن*

⚠️ *تنبيه:* هذه المنطقة للمشرفين فقط!

اختر الإجراء المطلوب من القائمة:
""",
    
    'wallet': """
💰 *المحفظة الإلكترونية*

💵 *الرصيد المتاح:* `{balance}` ريال
⭐ *النقاط:* `{points}` نقطة
📊 *إجمالي الإنفاق:* `{total_spent}` ريال

💳 *آخر العمليات:*
{transactions}
""",
    
    'shop': """
🛒 *المتجر الإلكتروني*

🎁 *الأقسام المتاحة:*

اختر القسم المطلوب من الأسفل 👇
""",
    
    'support': """
📞 *مركز الدعم الفني*

🕐 *أوقات العمل:* على مدار الساعة
📧 *البريد:* support@bot.com
📱 *الهاتف:* +966500000000

💡 *نصائح:*
• صف مشكلتك بوضوح
• أرفق لقطات شاشة إن أمكن
• تجنب إرسال رسائل متكررة
""",
    
    'games': """
🎮 *مركز الألعاب*

🏆 *جوائز يومية:* {daily_prize}
📊 *ألعابك:* {games_played}
⭐ *نقاطك في الألعاب:* {game_points}

🎯 اختر لعبة للبدء:
"""
}

# ==================== BOT HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    # Add/update user
    is_new = db.add_user(
        user_id=user.id,
        username=user.username or '',
        first_name=user.first_name or '',
        last_name=user.last_name or '',
        language_code=user.language_code or 'ar'
    )
    
    # Check ban
    user_data = db.get_user(user.id)
    if user_data and user_data['is_banned']:
        await update.message.reply_text("⛔ تم حظرك من استخدام هذا البوت.")
        return
    
    # Send welcome
    bot_name = db.get_setting('bot_name')
    welcome_text = TEXTS['welcome'].format(bot_name=bot_name)
    
    if is_new:
        welcome_text += "\n🎁 *مكافأة ترحيبية:* 10 نقاط!"
        db.add_points(user.id, 10)
        await update.message.reply_text(
            "🎉 أهلاً بك لأول مرة! لقد حصلت على 10 نقاط ترحيبية!"
        )
    
    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_menu_keyboard(user.id)
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages"""
    user = update.effective_user
    text = update.message.text
    user_id = user.id
    
    # Update activity
    db.update_user_activity(user_id)
    
    # Check ban
    user_data = db.get_user(user_id)
    if user_data and user_data['is_banned']:
        await update.message.reply_text("⛔ تم حظرك من استخدام هذا البوت.")
        return
    
    # Route messages
    if text == "👤 حسابي":
        await show_profile(update, context)
    elif text == "🛒 المتجر":
        await show_shop(update, context)
    elif text == "💰 المحفظة":
        await show_wallet(update, context)
    elif text == "🎮 الألعاب والترفيه":
        await show_games(update, context)
    elif text == "📢 الأخبار":
        await show_news(update, context)
    elif text == "🔗 الإحالات":
        await show_referral(update, context)
    elif text == "⚙️ الإعدادات":
        await show_settings(update, context)
    elif text == "📞 الدعم الفني":
        await show_support(update, context)
    elif text == "❓ المساعدة":
        await show_help(update, context)
    elif text == "🔐 لوحة تحكم الأدمن":
        await show_admin_panel(update, context)
    elif text == "🔙 العودة للقائمة الرئيسية":
        await back_to_main(update, context)
    
    # Admin commands
    elif text == "📊 الإحصائيات":
        await admin_stats(update, context)
    elif text == "👥 إدارة المستخدمين":
        await admin_users(update, context)
    elif text == "📢 إذاعة":
        await admin_broadcast_start(update, context)
    elif text == "⚙️ إعدادات البوت":
        await admin_settings(update, context)
    elif text == "🛍️ إدارة المنتجات":
        await admin_products(update, context)
    elif text == "🎫 التذاكر":
        await admin_tickets(update, context)
    elif text == "➕ إضافة أدمن":
        await admin_add_start(update, context)
    elif text == "➖ إزالة أدمن":
        await admin_remove_start(update, context)
    
    # Shop categories
    elif text == "🎮 منتجات رقمية":
        await show_category(update, context, "digital")
    elif text == "👕 ملابس وأزياء":
        await show_category(update, context, "clothing")
    elif text == "📚 كتب ومراجع":
        await show_category(update, context, "books")
    elif text == "🎁 هدايا واكسسوارات":
        await show_category(update, context, "gifts")
    
    # Games
    elif text == "🎲 لعبة النرد":
        await play_dice(update, context)
    elif text == "🎯 لعبة السهم":
        await play_dart(update, context)
    elif text == "🎰 آلة الحظ":
        await play_slots(update, context)
    elif text == "❓ تحدي المعرفة":
        await play_trivia(update, context)
    elif text == "🏆 المتصدرين":
        await show_leaderboard(update, context)
    elif text == "🎁 مكافآت يومية":
        await claim_daily(update, context)
    
    # Wallet
    elif text == "💳 شحن الرصيد":
        await deposit_start(update, context)
    elif text == "💸 سحب الأموال":
        await withdraw_start(update, context)
    elif text == "📜 سجل العمليات":
        await show_transactions(update, context)
    
    # Settings
    elif text == "🌐 تغيير اللغة":
        await change_language(update, context)
    elif text == "🔔 إعدادات الإشعارات":
        await notification_settings(update, context)
    elif text == "👤 تعديل الملف الشخصي":
        await edit_profile(update, context)
    
    # Support
    elif text == "📝 إنشاء تذكرة جديدة":
        await create_ticket_start(update, context)
    elif text == "📋 عرض تذاكري السابقة":
        await show_my_tickets(update, context)
    elif text == "❌ إلغاء":
        await cancel_operation(update, context)
    
    # Handle input states
    elif context.user_data.get('awaiting_input'):
        await handle_user_input(update, context, text)
    else:
        await update.message.reply_text(
            "❓ لم أفهم طلبك. يرجى استخدام الأزرار في القائمة.",
            reply_markup=get_main_menu_keyboard(user_id)
        )

# ==================== MENU HANDLERS ====================

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user profile"""
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    
    if not user:
        await update.message.reply_text("⚠️ خطأ في تحميل البيانات")
        return
    
    # Determine rank
    if user['points'] >= 1000:
        rank = "💎 ماسي"
    elif user['points'] >= 500:
        rank = "🥇 ذهبي"
    elif user['points'] >= 100:
        rank = "🥈 فضي"
    else:
        rank = "🥉 برونزي"
    
    text = TEXTS['profile'].format(
        user_id=user['user_id'],
        first_name=user['first_name'],
        last_name=user['last_name'] or '',
        username=user['username'] or 'غير متوفر',
        phone=user['phone_number'] or 'غير مربوط',
        points=user['points'],
        balance=user['balance'],
        rank=rank,
        join_date=user['join_date'],
        message_count=user['message_count'],
        referral_code=user['referral_code']
    )
    
    buttons = [
        [InlineKeyboardButton("🔄 تحديث", callback_data='refresh_profile')],
        [InlineKeyboardButton("📤 مشاركة البطاقة", callback_data='share_card')]
    ]
    
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def show_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show shop menu"""
    await update.message.reply_text(
        TEXTS['shop'],
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_shop_keyboard()
    )

async def show_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show wallet"""
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    
    # Get transactions
    transactions_list = db.get_transactions(user_id, 5)
    trans_text = ""
    if transactions_list:
        for t in transactions_list:
            emoji = "➕" if t['type'] == 'credit' else "➖"
            trans_text += f"{emoji} {t['amount']} ريال - {t['description'][:20]}\n"
    else:
        trans_text = "لا توجد عمليات حديثة"
    
    # Calculate total spent
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COALESCE(SUM(total_price), 0) FROM orders 
            WHERE user_id = ? AND status = 'completed'
        ''', (user_id,))
        total_spent = cursor.fetchone()[0]
    
    text = TEXTS['wallet'].format(
        balance=user['balance'],
        points=user['points'],
        total_spent=total_spent,
        transactions=trans_text
    )
    
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_wallet_keyboard()
    )

async def show_games(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show games menu"""
    user_id = update.effective_user.id
    
    # Get user's game stats
    text = TEXTS['games'].format(
        daily_prize="100 نقطة",
        games_played="0",
        game_points="0"
    )
    
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_games_keyboard()
    )

async def show_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show news"""
    news_items = [
        "📢 تم إطلاق النسخة الجديدة من البوت!",
        "🎉 عرض خاص: ضاعف نقاطك اليوم",
        "📱 تم إضافة دعم الدفع الإلكتروني"
    ]
    
    text = "📰 *آخر الأخبار:*\n\n"
    for item in news_items:
        text += f"• {item}\n\n"
    
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_menu_keyboard(update.effective_user.id)
    )

async def show_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show referral system"""
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    
    # Count referrals
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users WHERE referred_by = ?', (user_id,))
        referral_count = cursor.fetchone()[0]
    
    bonus = db.get_setting('referral_bonus')
    bot_username = context.bot.username
    
    text = f"""
🔗 *نظام الإحالات*

💡 شارك رابطك واكسب *{bonus}* نقطة لكل صديق!

🔗 رابط الإحالة:
`t.me/{bot_username}?start={user['referral_code']}`

📊 إحصائياتك:
• عدد الإحالات: {referral_count}
• النقاط المكتسبة: {referral_count * int(bonus)}
"""
    
    buttons = [[InlineKeyboardButton(
        "📤 مشاركة الرابط",
        url=f"https://t.me/share/url?url=t.me/{bot_username}?start={user['referral_code']}"
    )]]
    
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show settings"""
    await update.message.reply_text(
        "⚙️ *الإعدادات*\n\nاختر الإعداد المراد تعديله:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_settings_keyboard()
    )

async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show support"""
    await update.message.reply_text(
        TEXTS['support'],
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_support_keyboard()
    )

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help"""
    text = """
❓ *مركز المساعدة*

📌 *الأوامر المتاحة:*
/start - بدء البوت
/help - عرض المساعدة
/profile - حسابي
/support - الدعم الفني

💡 *نصائح:*
• استخدم الأزرار للتنقل السريع
• اجمع النقاط من الإحالات والألعاب
• تابع الأخبار للعروض الخاصة
    """
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_menu_keyboard(update.effective_user.id)
    )

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return to main menu"""
    await update.message.reply_text(
        "🏠 *القائمة الرئيسية*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_menu_keyboard(update.effective_user.id)
    )

# ==================== GAME HANDLERS ====================

async def play_dice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Play dice game"""
    msg = await update.message.reply_text("🎲 جاري رمي النرد...")
    await asyncio.sleep(1)
    
    dice_msg = await context.bot.send_dice(
        chat_id=update.effective_chat.id,
        emoji='🎲'
    )
    
    value = dice_msg.dice.value
    points = value * 5
    
    await msg.delete()
    await update.message.reply_text(
        f"🎲 النتيجة: {value}\n⭐ ربحت {points} نقطة!",
        reply_markup=get_games_keyboard()
    )
    db.add_points(update.effective_user.id, points)

async def play_dart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Play dart game"""
    msg = await update.message.reply_text("🎯 جاري رمي السهم...")
    
    dice_msg = await context.bot.send_dice(
        chat_id=update.effective_chat.id,
        emoji='🎯'
    )
    
    value = dice_msg.dice.value
    if value == 6:
        points = 100
        text = "🎯 بُل! ربحت 100 نقطة!"
    else:
        points = value * 10
        text = f"🎯 النتيجة: {value}\n⭐ ربحت {points} نقطة!"
    
    await msg.delete()
    await update.message.reply_text(text, reply_markup=get_games_keyboard())
    db.add_points(update.effective_user.id, points)

async def play_slots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Play slots"""
    msg = await update.message.reply_text("🎰 جاري الدوران...")
    
    dice_msg = await context.bot.send_dice(
        chat_id=update.effective_chat.id,
        emoji='🎰'
    )
    
    value = dice_msg.dice.value
    if value == 64:  # Jackpot
        points = 500
        text = "🎰 جاكبوت! ربحت 500 نقطة! 🎉"
    elif value in [1, 22, 43]:
        points = 100
        text = "🎰 فوز كبير! 100 نقطة!"
    else:
        points = 10
        text = f"🎰 حظ أوفر المرة القادمة! 10 نقاط"
    
    await msg.delete()
    await update.message.reply_text(text, reply_markup=get_games_keyboard())
    db.add_points(update.effective_user.id, points)

async def play_trivia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Play trivia"""
    questions = [
        {
            'q': 'ما هي عاصمة المملكة العربية السعودية؟',
            'options': ['جدة', 'الرياض', 'مكة', 'الدمام'],
            'correct': 1,
            'points': 50
        },
        {
            'q': 'كم عدد أيام السنة الكبيسة؟',
            'options': ['365', '366', '364', '367'],
            'correct': 1,
            'points': 30
        }
    ]
    
    q = random.choice(questions)
    
    buttons = [[InlineKeyboardButton(opt, callback_data=f'trivia_{i}_{q["correct"]}_{q["points"]}')] 
               for i, opt in enumerate(q['options'])]
    
    await update.message.reply_text(
        f"❓ *سؤال:*\n\n{q['q']}\n\n💰 الجائزة: {q['points']} نقطة",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show leaderboard"""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT first_name, points FROM users 
            ORDER BY points DESC LIMIT 10
        ''')
        top_users = cursor.fetchall()
    
    text = "🏆 *أفضل اللاعبين:*\n\n"
    for i, (name, points) in enumerate(top_users, 1):
        medal = {1: '🥇', 2: '🥈', 3: '🥉'}.get(i, f'{i}.')
        text += f"{medal} {name} - {points} نقطة\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def claim_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Claim daily reward"""
    # In real implementation, check last claim date
    points = random.randint(10, 100)
    db.add_points(update.effective_user.id, points)
    await update.message.reply_text(
        f"🎁 مكافأتك اليومية: {points} نقطة!",
        reply_markup=get_games_keyboard()
    )

# ==================== SHOP HANDLERS ====================

async def show_category(update: Update, context: ContextTypes.DEFAULT_TYPE, category: str):
    """Show products in category"""
    products = db.get_products(category=category)
    
    if not products:
        await update.message.reply_text(
            "⚠️ لا توجد منتجات في هذا القسم حالياً",
            reply_markup=get_shop_keyboard()
        )
        return
    
    for product in products:
        text = f"📦 *{product['name']}*\n"
        text += f"💰 السعر: {product['price']} ريال\n"
        text += f"📋 {product['description']}\n"
        text += f"📊 المتاح: {product['stock']} قطعة"
        
        buttons = [[InlineKeyboardButton(
            "🛒 أضف للسلة", 
            callback_data=f"add_cart_{product['product_id']}"
        )]]
        
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

# ==================== ADMIN HANDLERS ====================

async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin panel"""
    user_id = update.effective_user.id
    
    if not db.is_admin(user_id):
        await update.message.reply_text("⛔ ليس لديك صلاحية!")
        return
    
    await update.message.reply_text(
        TEXTS['admin_welcome'],
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_admin_keyboard()
    )

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show statistics"""
    total_users = db.get_users_count()
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users WHERE date(join_date) = date("now")')
        today_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM orders')
        total_orders = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM tickets WHERE status = 'open'")
        open_tickets = cursor.fetchone()[0]
    
    text = f"""
📊 *إحصائيات البوت*

👥 المستخدمين: {total_users}
📈 جدد اليوم: {today_users}
🛒 الطلبات: {total_orders}
🎫 التذاكر المفتوحة: {open_tickets}
"""
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start broadcast"""
    await update.message.reply_text(
        "📢 أرسل رسالتك للإذاعة (نص، صورة، فيديو، ملف):\n\nللإلغاء اضغط ❌ إلغاء",
        reply_markup=get_cancel_keyboard()
    )
    context.user_data['awaiting_broadcast'] = True

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User management"""
    await update.message.reply_text(
        "👥 إدارة المستخدمين\n\n"
        "• للبحث: أرسل /user [ID]\n"
        "• للحظر: /ban [ID]\n"
        "• للفك: /unban [ID]",
        reply_markup=get_admin_keyboard()
    )

async def admin_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot settings"""
    maintenance = db.get_setting('maintenance_mode')
    status = "🔴 مفعل" if maintenance == '1' else "🟢 معطل"
    
    await update.message.reply_text(
        f"⚙️ الإعدادات\n\n"
        f"وضع الصيانة: {status}\n\n"
        "للتبديل: /maintenance",
        reply_markup=get_admin_keyboard()
    )

async def admin_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Product management"""
    await update.message.reply_text(
        "🛍️ إدارة المنتجات\n\n"
        "• إضافة: /addproduct\n"
        "• تعديل: /editproduct [ID]\n"
        "• حذف: /delproduct [ID]",
        reply_markup=get_admin_keyboard()
    )

async def admin_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ticket management"""
    await update.message.reply_text(
        "🎫 إدارة التذاكر\n\n"
        "لعرض التذاكر المفتوحة: /tickets",
        reply_markup=get_admin_keyboard()
    )

async def admin_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start add admin"""
    await update.message.reply_text(
        "➕ أرسل معرف المستخدم (ID) للترقية:",
        reply_markup=get_cancel_keyboard()
    )
    context.user_data['awaiting_admin_id'] = True

async def admin_remove_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start remove admin"""
    await update.message.reply_text(
        "➖ أرسل معرف الأدمن للإزالة:",
        reply_markup=get_cancel_keyboard()
    )
    context.user_data['removing_admin'] = True

# ==================== INPUT HANDLERS ====================

async def handle_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Handle special inputs"""
    user_id = update.effective_user.id
    
    if context.user_data.get('awaiting_broadcast'):
        await process_broadcast(update, context, text)
        context.user_data['awaiting_broadcast'] = False
    
    elif context.user_data.get('awaiting_admin_id'):
        try:
            new_admin = int(text)
            db.add_admin(new_admin, user_id)
            await update.message.reply_text(
                f"✅ تمت ترقية المستخدم {new_admin}",
                reply_markup=get_admin_keyboard()
            )
        except:
            await update.message.reply_text("⚠️ معرف غير صحيح")
        context.user_data['awaiting_admin_id'] = False
    
    elif context.user_data.get('creating_ticket'):
        ticket_id = db.create_ticket(user_id, "دعم فني", text)
        await update.message.reply_text(
            f"✅ تم إنشاء تذكرة #{ticket_id}",
            reply_markup=get_support_keyboard()
        )
        context.user_data['creating_ticket'] = False

async def process_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Process broadcast"""
    users = db.get_all_users(limit=5000)
    sent = 0
    
    status_msg = await update.message.reply_text("⏳ جاري الإرسال...")
    
    for user in users:
        try:
            await context.bot.send_message(
                chat_id=user['user_id'],
                text=f"📢 إذاعة:\n\n{text}"
            )
            sent += 1
            await asyncio.sleep(0.05)
        except:
            pass
    
    await status_msg.edit_text(f"✅ تم الإرسال لـ {sent} مستخدم")

async def cancel_operation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current operation"""
    context.user_data.clear()
    await update.message.reply_text(
        "❌ تم الإلغاء",
        reply_markup=get_main_menu_keyboard(update.effective_user.id)
    )

async def create_ticket_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start ticket creation"""
    await update.message.reply_text(
        "📝 اكتب رسالتك للدعم الفني:",
        reply_markup=get_cancel_keyboard()
    )
    context.user_data['creating_ticket'] = True

async def show_my_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's tickets"""
    user_id = update.effective_user.id
    tickets = db.get_user_tickets(user_id)
    
    if not tickets:
        await update.message.reply_text("📭 ليس لديك تذاكر")
        return
    
    text = "📋 تذاكرك:\n\n"
    for t in tickets:
        status = "🔴 مفتوحة" if t['status'] == 'open' else "✅ مغلقة"
        text += f"#{t['ticket_id']}: {t['subject']} - {status}\n"
    
    await update.message.reply_text(text)

# ==================== MAIN ====================

def main():
    """Start bot"""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    print("🤖 Bot is running with Arabic Reply Keyboard...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button callbacks"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith('trivia_'):
        parts = data.split('_')
        selected = int(parts[1])
        correct = int(parts[2])
        points = int(parts[3])
        
        if selected == correct:
            db.add_points(update.effective_user.id, points)
            text = f"✅ إجابة صحيحة! ربحت {points} نقطة"
        else:
            text = "❌ إجابة خاطئة! حاول مرة أخرى"
        
        await query.edit_message_text(text)

if __name__ == "__main__":
    main()
