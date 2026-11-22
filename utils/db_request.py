from psycopg.types.json import Jsonb


class Request:
    def __init__(self, connection, user_id, currency):
        self.connection = connection
        self.user_id = user_id
        self.currency = currency

    def session(self):
        self.connection.execute('INSERT INTO wallet_users(user_id) VALUES (%s) ON CONFLICT DO NOTHING', (self.user_id,))
        return self.connection.execute('SELECT session FROM wallet_users WHERE user_id=%s FOR UPDATE', (self.user_id,)).fetchone()['session']

    def save_session(self, data):
        self.connection.execute('UPDATE wallet_users SET session=%s WHERE user_id=%s', (Jsonb(data), self.user_id))

    def add(self, data):
        return self.connection.execute('''INSERT INTO wallet_transactions
            (user_id, kind, amount, account, category, description, currency)
            VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
            (self.user_id, data['kind'], data['amount'], data['account'], data['category'], data.get('description', ''), self.currency)).fetchone()['id']

    def balances(self):
        return self.connection.execute('''SELECT account,
            SUM(CASE WHEN kind='income' THEN amount ELSE -amount END) AS balance
            FROM wallet_transactions WHERE user_id=%s AND currency=%s AND deleted_at IS NULL GROUP BY account''',
            (self.user_id, self.currency)).fetchall()

    def history(self, offset=0):
        return self.connection.execute('''SELECT * FROM wallet_transactions
            WHERE user_id=%s AND currency=%s AND deleted_at IS NULL
            ORDER BY created_at DESC, id DESC LIMIT 11 OFFSET %s''', (self.user_id, self.currency, offset)).fetchall()

    def stats(self, since):
        return self.connection.execute('''SELECT kind, category, SUM(amount) AS amount
            FROM wallet_transactions WHERE user_id=%s AND currency=%s AND deleted_at IS NULL
            AND created_at >= %s GROUP BY kind, category ORDER BY SUM(amount) DESC''',
            (self.user_id, self.currency, since)).fetchall()

    def get_transaction(self, transaction_id):
        return self.connection.execute('''SELECT * FROM wallet_transactions
            WHERE id=%s AND user_id=%s AND currency=%s AND deleted_at IS NULL''',
            (transaction_id, self.user_id, self.currency)).fetchone()

    def delete(self, transaction_id):
        return self.connection.execute('''UPDATE wallet_transactions SET deleted_at=now()
            WHERE id=%s AND user_id=%s AND currency=%s AND deleted_at IS NULL RETURNING id''',
            (transaction_id, self.user_id, self.currency)).fetchone() is not None
