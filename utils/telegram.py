import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


class TelegramError(RuntimeError):
    pass


class Telegram:
    def __init__(self, token):
        self.token = token

    def call(self, method, **payload):
        request = Request(f'https://api.telegram.org/bot{self.token}/{method}',
                          data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=40) as response:
                result = json.load(response)
        except (HTTPError, URLError, TimeoutError) as exc:
            # Never expose the request URL: it contains the token.
            raise TelegramError(f'Telegram request failed: {method}') from None
        if not result.get('ok'):
            raise TelegramError(f'Telegram rejected: {method}')
        return result['result']

    def deliver(self, update, responses):
        callback = update.get('callback_query')
        if callback:
            try:
                self.call('answerCallbackQuery', callback_query_id=callback['id'])
            except TelegramError:
                pass  # Expired callback must not prevent delivery of the saved result.
        message = update.get('message') or (callback or {}).get('message') or {}
        for response in responses:
            self.call('sendMessage', chat_id=message['chat']['id'], parse_mode='HTML', **response)
