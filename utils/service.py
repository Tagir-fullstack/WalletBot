import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from handlers.form import Conversation
from utils.db_request import Request


def process_update(update, settings):
    callback = update.get('callback_query') or {}
    message = update.get('message') or callback.get('message') or {}
    actor = callback.get('from') or message.get('from') or {}
    user_id = actor.get('id')
    if not isinstance(user_id, int) or actor.get('is_bot') or message.get('chat', {}).get('type') != 'private':
        return []
    if settings.allowed_users and user_id not in settings.allowed_users:
        return [{'text': 'Доступ к этому боту ограничен.'}]
    update_id = update['update_id']
    with psycopg.connect(settings.database_url, connect_timeout=10, row_factory=dict_row) as connection:
        # Both locks are transactional and work across independent serverless instances.
        connection.execute('SELECT pg_advisory_xact_lock(%s, %s)', (8191, update_id % 2147483647))
        cached = connection.execute('SELECT responses FROM wallet_updates WHERE update_id=%s', (update_id,)).fetchone()
        if cached:
            return cached['responses']
        connection.execute('SELECT pg_advisory_xact_lock(%s)', (user_id,))
        request = Request(connection, user_id, settings.currency)
        responses = Conversation(request, settings).run(text=message.get('text') or '', callback=callback.get('data') or '')
        connection.execute('INSERT INTO wallet_updates(update_id, responses) VALUES (%s,%s)', (update_id, Jsonb(responses)))
        return responses
