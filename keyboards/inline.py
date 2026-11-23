def keyboard(rows):
    return {'inline_keyboard': [[{'text': text, 'callback_data': data} for text, data in row] for row in rows]}


def inline_keyboard_start():
    return keyboard([
        [('➖ Расход', 'new:expense'), ('➕ Доход', 'new:income')],
        [('💰 Баланс', 'balance'), ('📋 История', 'history:0')],
        [('📊 Статистика', 'stats:month'), ('❔ Помощь', 'help')],
        [('🛒 Магазины', 'shops')],
    ])


def shops_keyboard():
    return {'inline_keyboard': [
        [{'text': '🛒 Magnum', 'url': 'https://magnum.kz/'},
         {'text': '🛒 SMALL', 'url': 'https://small.kz/'}],
        [{'text': '← Меню', 'callback_data': 'menu'}],
    ]}
