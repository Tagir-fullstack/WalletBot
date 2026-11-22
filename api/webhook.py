import hmac
import json
import logging
from http.server import BaseHTTPRequestHandler

from config import Settings
from utils.service import process_update
from utils.telegram import Telegram

MAX_BODY = 1024 * 1024


class handler(BaseHTTPRequestHandler):
    def respond(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.respond(200, {'service': 'WalletBot', 'status': 'ok'})

    def do_POST(self):
        try:
            settings = Settings.from_env(webhook=True)
        except ValueError:
            self.respond(503, {'error': 'Service is not configured'})
            return
        supplied = self.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
        if not hmac.compare_digest(supplied.encode(), settings.webhook_secret.encode()):
            self.respond(403, {'error': 'Forbidden'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > MAX_BODY:
                self.respond(413, {'error': 'Invalid payload size'})
                return
            update = json.loads(self.rfile.read(length))
            if not isinstance(update, dict) or type(update.get('update_id')) is not int:
                raise ValueError()
            if any(key in update and not isinstance(update[key], dict) for key in ('message', 'callback_query')):
                raise ValueError()
        except (ValueError, UnicodeDecodeError):
            self.respond(400, {'error': 'Invalid update'})
            return
        try:
            responses = process_update(update, settings)
            Telegram(settings.bot_token).deliver(update, responses)
        except Exception as exc:
            logging.error('Update processing failed (%s)', type(exc).__name__)
            # Non-2xx causes Telegram to retry. The stored update prevents double spending.
            self.respond(500, {'error': 'Processing failed; retry later'})
            return
        self.respond(200, {'ok': True})
