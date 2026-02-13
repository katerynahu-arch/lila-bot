import sqlite3
import random
import os
from telebot import TeleBot
from telebot.types import Message

# ---------- Токен из переменной окружения ----------
TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    raise Exception("BOT_TOKEN не задан! Добавьте переменную окружения.")

bot = TeleBot(TOKEN)

# ---------- База данных ----------
DB_NAME = 'lila_game.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            position INTEGER DEFAULT 68,
            entered BOOLEAN DEFAULT 0,
            game_active BOOLEAN DEFAULT 0,
            pending_sixes INTEGER DEFAULT 0,
            waiting_for_roll BOOLEAN DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {
            'user_id': row[0],
            'position': row[1],
            'entered': bool(row[2]),
            'game_active': bool(row[3]),
            'pending_sixes': row[4],
            'waiting_for_roll': bool(row[5])
        }
    return None

def save_user(data):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        INSERT OR REPLACE INTO users (user_id, position, entered, game_active, pending_sixes, waiting_for_roll)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        data['user_id'],
        data['position'],
        int(data['entered']),
        int(data['game_active']),
        data['pending_sixes'],
        int(data['waiting_for_roll'])
    ))
    conn.commit()
    conn.close()

def reset_game(user_id):
    data = {
        'user_id': user_id,
        'position': 68,
        'entered': False,
        'game_active': True,
        'pending_sixes': 0,
        'waiting_for_roll': False
    }
    save_user(data)
    return data

# ---------- Игровая логика (полностью та же) ----------
SNAKES = {
    16: 6,
    47: 26,
    49: 11,
    56: 44,
    62: 19,
    64: 60
}

ARROWS = {
    2: 23,
    9: 34,
    18: 50,
    25: 58,
    31: 68,
    42: 66
}

def apply_snake_or_arrow(cell):
    if cell in SNAKES:
        return SNAKES[cell]
    if cell in ARROWS:
        return ARROWS[cell]
    return None

def move_from_start(steps, user_id):
    position = 0
    triggered = False
    for _ in range(steps):
        position += 1
        if position > 68:
            position = 68
            break
        new_pos = apply_snake_or_arrow(position)
        if new_pos is not None:
            position = new_pos
            triggered = True
            break
    return position, triggered

def move_from_position(current_pos, steps, user_id):
    pos = current_pos
    triggered = False
    finished = False
    for _ in range(steps):
        next_cell = pos + 1
        if next_cell > 68:
            pos = 68
            finished = True
            break
        pos = next_cell
        new_pos = apply_snake_or_arrow(pos)
        if new_pos is not None:
            pos = new_pos
            triggered = True
            break
    return pos, triggered, finished

def process_roll(user_id, dice_value):
    user = get_user(user_id)
    if not user or not user['game_active']:
        return "У вас нет активной игры. Начните новую с /newgame.", None

    if dice_value == 6:
        user['pending_sixes'] += 1
        user['waiting_for_roll'] = True
        save_user(user)
        return f"🎲 Выпало 6! Всего шестёрок подряд: {user['pending_sixes']}\nБросайте ещё раз (/roll или /enter <число>).", None

    total_sixes = user['pending_sixes']
    user['pending_sixes'] = 0
    user['waiting_for_roll'] = False

    if total_sixes == 3:
        steps = dice_value
        rule_text = "🔥 Три шестёрки сгорели! Учитывается только последнее число."
    else:
        steps = total_sixes * 6 + dice_value
        rule_text = f"➡️ Всего шагов: {steps} (шестёрок: {total_sixes}, последнее: {dice_value})"

    if not user['entered']:
        if total_sixes == 0:
            return "❌ Для входа в игру необходима шестёрка. Попробуйте снова.", None
        position, triggered = move_from_start(steps, user_id)
        user['entered'] = True
        user['position'] = position
        if position == 68:
            user['game_active'] = False
            save_user(user)
            return f"{rule_text}\n\n✨ Вы вошли в игру и сразу достигли Космического сознания (68)!\nИгра окончена. Поздравляю!", None
        save_user(user)
        desc = get_cell_description(position)
        msg = f"{rule_text}\n\nВы вступили на поле и оказались на клетке {position}.\n{desc}"
        if triggered:
            msg += "\n\n🧭 Сработала змея/стрела!"
        return msg, None

    current_pos = user['position']
    if 57 <= current_pos <= 64:
        if current_pos + steps > 68:
            save_user(user)
            return f"🌌 Вы находитесь на восьмом уровне. Бросок выводит за пределы доски и сгорает.\n{rule_text}", None

    new_pos, triggered, finished = move_from_position(current_pos, steps, user_id)
    user['position'] = new_pos

    if finished:
        user['game_active'] = False
        save_user(user)
        return f"{rule_text}\n\n🎯 Вы достигли клетки 68 – Космическое сознание!\nИгра завершена. Благодарю за путешествие.", None

    save_user(user)
    desc = get_cell_description(new_pos)
    msg = f"{rule_text}\n\nВы переместились на клетку {new_pos}.\n{desc}"
    if triggered:
        msg += "\n\n🧙‍♂️ Сработала змея/стрела!"
    return msg, None

def get_cell_description(cell):
    descriptions = {
        1: "1. Рождение — начало пути, чистое намерение.",
        6: "6. Заблуждение — иллюзия, требующая осознания.",
        68: "68. Космическое сознание — цель игры, просветление."
    }
    return descriptions.get(cell, f"{cell}. Эта клетка ждёт своё описание.")

# ---------- Обработчики команд ----------
@bot.message_handler(commands=['start'])
def cmd_start(message: Message):
    bot.send_message(message.chat.id,
        "🎲 Добро пожаловать в игру ЛИЛА!\n"
        "Я буду вашим Проводником.\n"
        "Начните новую игру: /newgame")

@bot.message_handler(commands=['newgame'])
def cmd_newgame(message: Message):
    user_id = message.from_user.id
    reset_game(user_id)
    bot.send_message(user_id,
        "🕉 Новая игра начата!\n"
        "Вы находитесь на клетке 68 — Космическое сознание.\n"
        "Чтобы войти на поле, бросьте кубик и постарайтесь выбросить 6.\n"
        "Используйте /roll (виртуальный кубик) или /enter <число> (физический кубик).")

@bot.message_handler(commands=['roll'])
def cmd_roll(message: Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user or not user['game_active']:
        bot.send_message(user_id, "У вас нет активной игры. /newgame")
        return
    dice = random.randint(1, 6)
    response, _ = process_roll(user_id, dice)
    bot.send_message(user_id, f"🎲 Выпало: {dice}\n\n{response}")

@bot.message_handler(commands=['enter'])
def cmd_enter(message: Message):
    user_id = message.from_user.id
    args = message.text.split()
    if len(args) != 2 or not args[1].isdigit():
        bot.send_message(user_id, "Использование: /enter <число от 1 до 6>")
        return
    dice = int(args[1])
    if dice < 1 or dice > 6:
        bot.send_message(user_id, "Число должно быть от 1 до 6.")
        return
    response, _ = process_roll(user_id, dice)
    bot.send_message(user_id, f"🎲 Вы ввели: {dice}\n\n{response}")

@bot.message_handler(commands=['status'])
def cmd_status(message: Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user or not user['game_active']:
        bot.send_message(user_id, "Нет активной игры.")
        return
    pos = user['position']
    entered = "да" if user['entered'] else "нет (ожидаем вход)"
    status = f"📍 Позиция: {pos}\nВошел в игру: {entered}\nСерия 6-к: {user['pending_sixes']}"
    bot.send_message(user_id, status)

@bot.message_handler(commands=['cancel'])
def cmd_cancel(message: Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    if user and user['game_active']:
        user['pending_sixes'] = 0
        user['waiting_for_roll'] = False
        save_user(user)
        bot.send_message(user_id, "⏸ Текущая серия бросков сброшена.")
    else:
        bot.send_message(user_id, "Нет активной игры.")

@bot.message_handler(commands=['stop'])
def cmd_stop(message: Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    if user:
        user['game_active'] = False
        save_user(user)
        bot.send_message(user_id, "🛑 Игра принудительно завершена. Помните: однажды начатая игра должна быть закончена, но это исключение.")
    else:
        bot.send_message(user_id, "Нет активной игры.")

# ---------- Запуск ----------
if __name__ == '__main__':
    print("✅ Бот запускается на Bothost...")
    bot.infinity_polling()