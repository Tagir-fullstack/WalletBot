"""Register the webhook only after verifying the deployed health endpoint."""
import argparse
import json
import re
from urllib.parse import urlparse
from urllib.request import urlopen

from config import Settings
from scripts.env import load_local_env
from utils.telegram import Telegram


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['set', 'info', 'delete'])
    parser.add_argument('--url', help='Stable production URL, e.g. https://walletbot.vercel.app')
    args = parser.parse_args()
    load_local_env()
    settings = Settings.from_env(webhook=args.action == 'set')
    telegram = Telegram(settings.bot_token)
    if args.action == 'set':
        parsed = urlparse(args.url or '')
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
            parser.error('--url must be an HTTPS origin without a path')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', settings.webhook_secret):
            parser.error('WEBHOOK_SECRET must contain 1–256 letters, digits, underscores or hyphens')
        endpoint = args.url.rstrip('/') + '/api/webhook'
        with urlopen(endpoint, timeout=20) as response:
            health = json.load(response)
        if health.get('service') != 'WalletBot':
            parser.error('Unexpected health response')
        telegram.call('setWebhook', url=endpoint, secret_token=settings.webhook_secret,
                      allowed_updates=['message', 'callback_query'], max_connections=10,
                      drop_pending_updates=False)
        print('Webhook registered.')
    elif args.action == 'delete':
        telegram.call('deleteWebhook', drop_pending_updates=False)
        print('Webhook removed; local polling is available.')
    else:
        info = telegram.call('getWebhookInfo')
        print(json.dumps({key: info.get(key) for key in ('url', 'pending_update_count', 'last_error_message')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
