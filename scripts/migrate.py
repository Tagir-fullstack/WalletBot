import psycopg
from config import Settings
from scripts.env import load_local_env
from utils.create_db import create_db


def main():
    load_local_env()
    settings = Settings.from_env()
    with psycopg.connect(settings.database_url, connect_timeout=10) as connection:
        create_db(connection)
    print('Wallet schema is ready.')


if __name__ == '__main__':
    main()
