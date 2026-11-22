"""Integration checks use an isolated test database; CI provides PostgreSQL."""
import os
import unittest
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor

import psycopg
from psycopg.rows import dict_row

from config import Settings
from utils.create_db import create_db
from utils.service import process_update


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'TEST_DATABASE_URL is not set')
class PostgresTests(unittest.TestCase):
    def setUp(self):
        self.url = os.environ['TEST_DATABASE_URL']
        self.settings = Settings('123:test', self.url, 'test_secret')
        with psycopg.connect(self.url) as conn:
            create_db(conn)
            conn.execute('TRUNCATE wallet_updates, wallet_transactions, wallet_users RESTART IDENTITY CASCADE')
        self.counter = 1

    def send(self, text='', callback='', user=42):
        update = {'update_id': self.counter}
        self.counter += 1
        message = {'from': {'id': user}, 'chat': {'id': user, 'type': 'private'}, 'text': text}
        if callback:
            update['callback_query'] = {'id': 'test', 'from': {'id': user}, 'message': message, 'data': callback}
        else:
            update['message'] = message
        return process_update(update, self.settings)

    def state(self):
        with psycopg.connect(self.url, row_factory=dict_row) as conn:
            return conn.execute('SELECT session FROM wallet_users WHERE user_id=42').fetchone()['session']

    def prepare(self):
        self.send('+100,25 Зарплата')
        nonce = self.state()['nonce']
        self.send(callback=f'flow:{nonce}:account:card')
        self.send(callback=f'flow:{nonce}:category:0')
        return nonce

    def test_retries_concurrent_instances_and_user_isolation(self):
        nonce = self.prepare()
        update = {'update_id': 500, 'callback_query': {'id': 'test', 'from': {'id': 42},
                  'message': {'chat': {'id': 42, 'type': 'private'}}, 'data': f'flow:{nonce}:confirm'}}
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: process_update(update, self.settings), range(4)))
        self.assertTrue(all(r == results[0] for r in results))
        with psycopg.connect(self.url) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*), SUM(amount) FROM wallet_transactions').fetchone(), (1, Decimal('100.25')))
        self.assertIn('0,00', self.send('/balance', user=99)[0]['text'])
        self.assertIn('не найдена', self.send('/delete 1', user=99)[0]['text'])
        self.send('/delete 1')
        delete_nonce = self.state()['nonce']
        self.send(callback=f'flow:{delete_nonce}:delete')
        self.assertIn('Баланс: 0,00', self.send('/balance')[0]['text'])

    def test_failed_operation_rolls_back_session_and_dedup(self):
        from unittest.mock import patch
        nonce = self.prepare()
        with patch('handlers.form.Conversation.balance', side_effect=RuntimeError('response generation failed')):
            with self.assertRaises(RuntimeError):
                self.send(callback=f'flow:{nonce}:confirm')
        with psycopg.connect(self.url) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM wallet_transactions').fetchone()[0], 0)
        self.assertEqual(self.state()['step'], 'confirm')
        self.send(callback=f'flow:{nonce}:confirm')
        self.assertIn('100,25', self.send('/balance')[0]['text'])
