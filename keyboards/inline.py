def keyboard(rows):
    return {'inline_keyboard': [[{'text': text, 'callback_data': data} for text, data in row] for row in rows]}


def inline_keyboard_start():
    return keyboard([
        [('➖ Расход', 'new:expense'), ('➕ Доход', 'new:income')],
        [('💰 Баланс', 'balance'), ('📋 История', 'history:0')],
        [('📊 Статистика', 'stats:month'), ('❔ Помощь', 'help')],
    ])
