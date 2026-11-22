"""Persistent conversation. Every change is committed with the incoming update."""
import re
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from html import escape
from zoneinfo import ZoneInfo

from keyboards.inline import inline_keyboard_start, keyboard
from utils.money import money, parse_amount

ACCOUNTS = {'card': 'Карта', 'cash': 'Наличные'}
CATEGORIES = {
    'expense': ['Продукты', 'Транспорт', 'Кафе', 'Дом', 'Здоровье', 'Покупки', 'Развлечения', 'Другое'],
    'income': ['Зарплата', 'Подработка', 'Подарок', 'Начальный остаток', 'Другое'],
}
HELP = ('<b>Кошелёк — доходы и расходы</b>\n\n'
        'Начните с кнопки «Доход» или «Расход». Выберите сумму, счёт и категорию, '
        'добавьте комментарий и подтвердите запись.\n\n'
        'Быстрый ввод: <code>-1500 Обед</code> или <code>+250000 Зарплата</code>. '
        'Счёт и категорию можно выбрать перед сохранением.\n\n'
        '/balance — баланс\n/history — последние операции\n/stats — статистика\n'
        '/income — добавить доход\n/expense — добавить расход\n'
        '/delete 123 — удалить свою операцию с подтверждением\n/cancel — отмена\n\n'
        'Для начального баланса добавьте доход с категорией «Начальный остаток». '
        'Он учитывается в балансе, но не в доходах статистики. '
        'Бот ведёт учёт и не подключается к банковским счетам.')


class Conversation:
    def __init__(self, request, settings):
        self.db = request
        self.settings = settings
        self.state = request.session()
        self.responses = []

    def reply(self, text, markup=None):
        self.responses.append({'text': text, 'reply_markup': markup or inline_keyboard_start()})

    def buttons(self, rows):
        rows = [[(text, f"flow:{self.state['nonce']}:{value}") for text, value in row] for row in rows]
        return keyboard(rows + [[('Отмена', 'cancel')]])

    def start(self, kind, amount=None, description=''):
        self.state = {'step': 'amount', 'kind': kind, 'nonce': secrets.token_hex(4)}
        if amount:
            self.state.update(amount=str(amount), description=description, step='account')
            self.ask_account()
        else:
            self.reply('Введите сумму дохода:' if kind == 'income' else 'Введите сумму расхода:', keyboard([[('Отмена', 'cancel')]]))

    def ask_account(self):
        self.reply('Выберите счёт:', self.buttons([[(v, 'account:' + k) for k, v in ACCOUNTS.items()]]))

    def ask_category(self):
        categories = CATEGORIES[self.state['kind']]
        self.reply('Выберите категорию:', self.buttons([[(v, f'category:{i}')] for i, v in enumerate(categories)]))

    def confirm(self):
        self.state['step'] = 'confirm'
        d = self.state
        sign = '+' if d['kind'] == 'income' else '−'
        self.reply(f"<b>Проверьте операцию</b>\n{sign}{money(d['amount'])} {escape(self.settings.currency)}\n"
                   f"Счёт: {ACCOUNTS[d['account']]}\nКатегория: {d['category']}\n"
                   f"Комментарий: {escape(d.get('description') or '—')}", self.buttons([[('✅ Сохранить', 'confirm')]]))

    def balance(self):
        balances = {r['account']: r['balance'] for r in self.db.balances()}
        total = sum(balances.values(), Decimal(0))
        self.reply(f'<b>Баланс: {money(total)} {escape(self.settings.currency)}</b>\n\n' + '\n'.join(
            f'{label}: {money(balances.get(account, 0))}' for account, label in ACCOUNTS.items()))

    def history(self, offset):
        rows = self.db.history(offset)
        if not rows:
            self.reply('Операций пока нет.' if not offset else 'Больше операций нет.')
            return
        lines = ['<b>История операций</b>']
        for row in rows[:10]:
            date = row['created_at'].astimezone(ZoneInfo(self.settings.timezone)).strftime('%d.%m.%Y %H:%M')
            sign = '+' if row['kind'] == 'income' else '−'
            lines.append(f"\n#{row['id']} · {date}\n{sign}{money(row['amount'])} {escape(self.settings.currency)} · "
                         f"{escape(row['category'])} · {ACCOUNTS[row['account']]}\n{escape(row['description'])}")
        nav = []
        if offset:
            nav.append(('← Новее', f'history:{max(0, offset - 10)}'))
        if len(rows) > 10:
            nav.append(('Старее →', f'history:{offset + 10}'))
        lines.append('\nУдалить запись: /delete номер')
        self.reply('\n'.join(lines), keyboard(([nav] if nav else []) + [[('Меню', 'menu')]]))

    def stats(self, period):
        now = datetime.now(ZoneInfo(self.settings.timezone))
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if period == 'month':
            since = since.replace(day=1)
        elif period == 'all':
            since = datetime(1970, 1, 1, tzinfo=timezone.utc)
        rows = [r for r in self.db.stats(since) if r['category'] != 'Начальный остаток']
        income = sum((r['amount'] for r in rows if r['kind'] == 'income'), Decimal(0))
        expense = sum((r['amount'] for r in rows if r['kind'] == 'expense'), Decimal(0))
        label = {'today': 'сегодня', 'month': 'текущий месяц', 'all': 'всё время'}[period]
        lines = [f'<b>Статистика: {label}</b> · {escape(self.settings.currency)}',
                 f'Доходы: {money(income)}', f'Расходы: {money(expense)}', f'Разница: {money(income - expense)}']
        for kind, title in [('expense', 'Расходы по категориям'), ('income', 'Доходы по категориям')]:
            lines.append('\n<b>' + title + '</b>')
            lines.extend(f"{escape(r['category'])}: {money(r['amount'])}" for r in rows if r['kind'] == kind)
        self.reply('\n'.join(lines), keyboard([[('Сегодня', 'stats:today'), ('Месяц', 'stats:month'), ('Всё время', 'stats:all')], [('Меню', 'menu')]]))

    def run(self, *, text='', callback=''):
        if callback:
            self.callback(callback)
        else:
            self.message(text)
        self.db.save_session(self.state)
        return self.responses

    def message(self, text):
        text = text.strip()
        command = text.split(maxsplit=1)[0].split('@')[0] if text else ''
        if command in ('/start', '/cancel'):
            self.state = {}
            self.reply('Привет! Здесь можно учитывать доходы и расходы. Выберите действие.' if command == '/start' else 'Добавление отменено.')
        elif command == '/help':
            self.reply(HELP)
        elif command == '/balance':
            self.balance()
        elif command == '/history':
            self.history(0)
        elif command == '/stats':
            self.stats('month')
        elif command == '/id':
            self.reply(f'Ваш Telegram ID: <code>{self.db.user_id}</code>')
        elif command in ('/income', '/expense'):
            self.start(command[1:])
        elif command == '/delete':
            parts = text.split()
            if len(parts) != 2 or not parts[1].isdigit() or len(parts[1]) > 18:
                self.reply('Укажите номер: /delete 123. Номер можно найти в /history.')
            else:
                row = self.db.get_transaction(int(parts[1]))
                if not row:
                    self.reply('Операция не найдена.')
                else:
                    self.state = {'step': 'delete', 'id': row['id'], 'nonce': secrets.token_hex(4)}
                    self.reply(f"Удалить операцию #{row['id']} на {money(row['amount'])} {escape(self.settings.currency)}?",
                               self.buttons([[('Удалить', 'delete')]]))
        elif text.startswith('/'):
            self.reply('Неизвестная команда. /help — помощь, /cancel — отмена.')
        elif self.state.get('step') == 'amount':
            try:
                self.state.update(amount=str(parse_amount(text)), step='account')
                self.ask_account()
            except ValueError as exc:
                self.reply(str(exc), keyboard([[('Отмена', 'cancel')]]))
        elif self.state.get('step') == 'description':
            if not text or len(text) > 200:
                self.reply('Введите комментарий от 1 до 200 символов или нажмите «Пропустить».', self.buttons([[('Пропустить', 'skip')]]))
            else:
                self.state['description'] = text
                self.confirm()
        elif text.startswith(('+', '-')) and not self.state:
            match = re.fullmatch(r'([+-])(\d+(?:[.,]\d+)?)(?:\s+(.+))?', text)
            if not match:
                self.reply('Пример быстрого ввода: <code>-1500 Обед</code>. Для сумм с пробелами используйте кнопки.')
                return
            try:
                amount = parse_amount(match[2])
                description = match[3] or ''
                if len(description) > 200:
                    raise ValueError('Комментарий — максимум 200 символов.')
                self.start('income' if match[1] == '+' else 'expense', amount, description)
            except ValueError as exc:
                self.reply(str(exc))
        elif self.state:
            self.reply('Продолжите с помощью кнопок в предыдущем сообщении или введите /cancel.')
        else:
            self.reply('Выберите действие или введите <code>-1500 Обед</code>. /help — помощь.')

    def callback(self, data):
        if data in ('cancel', 'menu'):
            self.state = {}
            self.reply('Выберите действие.')
        elif data.startswith('new:') and data[4:] in CATEGORIES:
            self.start(data[4:])
        elif data == 'balance':
            self.balance()
        elif data == 'help':
            self.reply(HELP)
        elif re.fullmatch(r'history:\d{1,8}', data):
            self.history(int(data.split(':')[1]))
        elif data in ('stats:today', 'stats:month', 'stats:all'):
            self.stats(data.split(':')[1])
        elif data.startswith('flow:'):
            parts = data.split(':', 2)
            if len(parts) != 3 or parts[1] != self.state.get('nonce'):
                self.reply('Эта кнопка устарела. Продолжите текущую операцию или начните новую.')
                return
            action = parts[2]
            step = self.state.get('step')
            if step == 'account' and action.startswith('account:') and action[8:] in ACCOUNTS:
                self.state.update(account=action[8:], step='category')
                self.ask_category()
            elif step == 'category' and re.fullmatch(r'category:\d', action):
                categories = CATEGORIES[self.state['kind']]
                index = int(action.split(':')[1])
                if index >= len(categories):
                    return
                self.state['category'] = categories[index]
                if self.state.get('description'):
                    self.confirm()
                else:
                    self.state['step'] = 'description'
                    self.reply('Добавьте комментарий (до 200 символов):', self.buttons([[('Пропустить', 'skip')]]))
            elif step == 'description' and action == 'skip':
                self.state['description'] = ''
                self.confirm()
            elif step == 'confirm' and action == 'confirm':
                transaction_id = self.db.add(self.state)
                self.state = {}
                self.reply(f'✅ Операция #{transaction_id} сохранена.')
                self.balance()
            elif step == 'delete' and action == 'delete':
                deleted = self.db.delete(self.state['id'])
                self.state = {}
                self.reply('Операция удалена, баланс пересчитан.' if deleted else 'Операция уже удалена.')
            else:
                self.reply('Этот шаг уже завершён. Продолжите с помощью последнего сообщения.')
        else:
            self.reply('Откройте актуальное меню: /start.')
