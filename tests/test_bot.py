import io
import json
import os
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from api.webhook import handler
from config import Settings
from handlers.form import Conversation
from utils.money import parse_amount
from utils.service import process_update

SETTINGS = Settings('123:test', 'postgresql://test', 'test_secret')


class MemoryRequest:
    user_id = 42

    def __init__(self):
        self.data = {}
        self.rows = []

    def session(self):
        return dict(self.data)

    def save_session(self, state):
        self.data = dict(state)

    def add(self, data):
        self.rows.append({**data, 'amount': Decimal(data['amount']), 'id': len(self.rows) + 1,
                          'created_at': datetime.now(timezone.utc)})
        return self.rows[-1]['id']

    def balances(self):
        result = {}
        for r in self.rows:
            result[r['account']] = result.get(r['account'], Decimal(0)) + r['amount'] * (1 if r['kind'] == 'income' else -1)
        return [{'account': k, 'balance': v} for k, v in result.items()]

    def get_transaction(self, transaction_id):
        return next((r for r in self.rows if r['id'] == transaction_id), None)

    def delete(self, transaction_id):
        row = self.get_transaction(transaction_id)
        if row:
            self.rows.remove(row)
        return bool(row)

    def history(self, offset):
        return list(reversed(self.rows))[offset:offset+11]

    def stats(self, since):
        return self.rows


class MoneyTests(unittest.TestCase):
    def test_exact_decimal_and_localized_input(self):
        self.assertEqual(parse_amount('1 234,56'), Decimal('1234.56'))
        self.assertEqual(parse_amount('0.10') + parse_amount('0.20'), Decimal('0.30'))
        self.assertEqual(parse_amount('999999999999.99'), Decimal('999999999999.99'))

    def test_reject_invalid_amounts(self):
        for value in ['0', '-1', 'NaN', 'Infinity', '1.001', '1e3', '1000000000000', '', '12a', '1,000.50']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_amount(value)


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.db = MemoryRequest()

    def run_message(self, text):
        return Conversation(self.db, SETTINGS).run(text=text)

    def click(self, action):
        return Conversation(self.db, SETTINGS).run(callback=f"flow:{self.db.data['nonce']}:{action}")

    def prepare_expense(self):
        self.run_message('-1500 Обед')
        self.click('account:card')
        self.click('category:2')

    def test_persistent_steps_and_confirmation_only(self):
        self.prepare_expense()
        self.assertEqual(self.db.data['step'], 'confirm')
        self.assertFalse(self.db.rows)
        nonce = self.db.data['nonce']
        self.click('confirm')
        self.assertEqual(len(self.db.rows), 1)
        self.assertEqual(self.db.rows[0]['amount'], Decimal('1500.00'))
        self.assertEqual(self.db.rows[0]['description'], 'Обед')
        Conversation(self.db, SETTINGS).run(callback=f'flow:{nonce}:confirm')
        self.assertEqual(len(self.db.rows), 1)

    def test_invalid_amount_keeps_step_and_cancel_clears(self):
        self.run_message('/income')
        self.run_message('NaN')
        self.assertEqual(self.db.data['step'], 'amount')
        self.run_message('/cancel')
        self.assertEqual(self.db.data, {})
        self.assertEqual(self.db.rows, [])

    def test_old_button_cannot_change_new_draft(self):
        self.run_message('/income')
        old = self.db.data['nonce']
        self.run_message('/expense')
        Conversation(self.db, SETTINGS).run(callback=f'flow:{old}:account:cash')
        self.assertEqual(self.db.data['kind'], 'expense')
        self.assertEqual(self.db.data['step'], 'amount')

    def test_comment_is_escaped(self):
        self.run_message('/income')
        self.run_message('100,25')
        self.click('account:cash')
        self.click('category:0')
        response = self.run_message('<b>name</b>')
        self.assertIn('&lt;b&gt;name&lt;/b&gt;', response[0]['text'])
        self.click('confirm')
        self.assertEqual(self.db.rows[0]['description'], '<b>name</b>')

    def test_delete_requires_confirmation_and_changes_balance(self):
        self.prepare_expense()
        self.click('confirm')
        self.run_message('/delete 1')
        self.assertEqual(len(self.db.rows), 1)
        self.click('delete')
        self.assertEqual(self.db.rows, [])

    def test_initial_balance_excluded_from_income_stats(self):
        self.run_message('+10000')
        self.click('account:cash')
        self.click('category:3')
        self.click('skip')
        self.click('confirm')
        balance = self.run_message('/balance')[0]['text']
        stats = self.run_message('/stats')[0]['text']
        self.assertIn('10 000,00', balance)
        self.assertIn('Доходы: 0,00', stats)

    def test_text_in_button_step_does_not_save(self):
        self.prepare_expense()
        self.run_message('да')
        self.assertFalse(self.db.rows)
        self.assertEqual(self.db.data['step'], 'confirm')


class ServiceTests(unittest.TestCase):
    @patch('utils.service.psycopg.connect')
    def test_groups_and_unauthorized_users_never_touch_database(self, connect):
        update = {'update_id': 1, 'message': {'from': {'id': 1}, 'chat': {'type': 'group'}}}
        self.assertEqual(process_update(update, SETTINGS), [])
        update['message']['chat']['type'] = 'private'
        restricted = Settings('123:test', 'postgresql://test', 'secret', allowed_users=frozenset({42}))
        self.assertIn('ограничен', process_update(update, restricted)[0]['text'])
        connect.assert_not_called()


class WebhookTests(unittest.TestCase):
    def request(self, payload, secret='test_secret'):
        request = handler.__new__(handler)
        request.headers = {'X-Telegram-Bot-Api-Secret-Token': secret, 'Content-Length': str(len(payload))}
        request.rfile = io.BytesIO(payload)
        request.respond = lambda status, data: setattr(request, 'result', (status, data))
        with patch('api.webhook.Settings.from_env', return_value=SETTINGS):
            request.do_POST()
        return request.result

    @patch('api.webhook.process_update')
    def test_wrong_secret_cannot_touch_database(self, process):
        self.assertEqual(self.request(b'{"update_id":1}', 'wrong')[0], 403)
        process.assert_not_called()

    def test_malformed_payload(self):
        for body in [b'[]', b'broken', b'{"update_id":true}', b'{"update_id":1,"message":[]}']:
            self.assertEqual(self.request(body)[0], 400)

    @patch('api.webhook.Telegram')
    @patch('api.webhook.process_update')
    def test_database_failure_is_retryable(self, process, telegram):
        process.side_effect = RuntimeError('secret')
        status, body = self.request(b'{"update_id":1}')
        self.assertEqual(status, 500)
        self.assertNotIn('secret', json.dumps(body))
        telegram.assert_not_called()

    @patch('api.webhook.Telegram')
    @patch('api.webhook.process_update', return_value=[])
    def test_valid_update(self, process, telegram):
        self.assertEqual(self.request(b'{"update_id":1}')[0], 200)
        telegram.return_value.deliver.assert_called_once()


if __name__ == '__main__':
    unittest.main()
