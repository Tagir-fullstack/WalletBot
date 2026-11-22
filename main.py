"""Local polling runner. Production uses api/webhook.py."""
import logging
import time

from config import Settings
from scripts.env import load_local_env
from scripts.migrate import main as migrate
from utils.service import process_update
from utils.telegram import Telegram


def main():
    load_local_env()
    settings = Settings.from_env()
    migrate()
    telegram = Telegram(settings.bot_token)
    if telegram.call('getWebhookInfo').get('url'):
        raise SystemExit('Webhook is active. Run python -m scripts.webhook delete before local polling.')
    offset = 0
    logging.info('WalletBot polling started')
    while True:
        try:
            for update in telegram.call('getUpdates', offset=offset, timeout=25, allowed_updates=['message', 'callback_query']):
                telegram.deliver(update, process_update(update, settings))
                offset = update['update_id'] + 1
        except KeyboardInterrupt:
            break
        except Exception as exc:
            logging.error('Update failed (%s); retrying', type(exc).__name__)
            time.sleep(3)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
