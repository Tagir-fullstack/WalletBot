# WalletBot

Telegram-бот для учёта доходов и расходов. Python 3.13, PostgreSQL (Neon), webhook на Vercel, проверки и деплой через GitHub Actions.

## Возможности

- Доходы и расходы: сумма → карта/наличные → категория → комментарий → подтверждение.
- Быстрый ввод: `-1500 Обед`, `+250000 Зарплата`.
- Баланс по счетам, история с листанием, статистика за сегодня, месяц и всё время.
- Удаление своей операции с подтверждением; баланс пересчитывается.
- Начальный остаток: доход с соответствующей категорией; не входит в доходы статистики.
- Суммы через Decimal / NUMERIC, отдельные данные для каждого Telegram-пользователя.
- Диалог хранится в PostgreSQL. Перезапуск Vercel не теряет незавершённую запись.
- Повтор webhook не создаёт вторую операцию: операция, диалог и результат update фиксируются в одной транзакции. Согласованность между функциями обеспечивает блокировка пользователя в PostgreSQL.
- Личные чаты, опциональное ограничение доступа через `ALLOWED_USER_IDS`.

По умолчанию валюта `KZT`, часовой пояс `Asia/Almaty`. Валюта является частью записей: после её изменения старые записи остаются в базе и доступны при возврате прежней валюты. Конвертации валют и подключения к банкам нет. На одного Telegram-бота используйте отдельную базу или схему PostgreSQL.

## Что было в исходнике

Заготовка на aiogram с polling, незавершённой регистрацией, меню «Доход / Расход / Настройки» и локальной PostgreSQL. Рабочих финансовых операций не было: обработчики и SQL содержали части бота ремонта, ссылки на `AddData`, `next_id`, таблицы заказов. Токен находился прямо в `config.py`.

Теперь HTTP-обработчик и локальный polling используют общий синхронный обработчик без aiogram. Для Vercel не нужен постоянно работающий процесс или хранилище FSM в памяти. Старые таблицы базы не меняются и не удаляются; новые имеют префикс `wallet_`. Миграции данных из старых таблиц нет.

## Локальный запуск

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env.local
```

Если `.env.local` уже существует, сохраните его: при подготовке проекта туда был перенесён существующий токен. Заполните `DATABASE_URL`, проверьте `BOT_TOKEN`, сгенерируйте `WEBHOOK_SECRET`:

```bash
.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Скрипты автоматически читают `.env.local`, не перезаписывая уже заданные переменные окружения.

```bash
.venv/bin/python -m scripts.migrate
.venv/bin/python main.py
```

При активном webhook polling намеренно не запускается. Чтобы переключить работающий бот на локальную машину, явно удалите webhook:

```bash
.venv/bin/python -m scripts.webhook delete
```

## Neon

В [Neon Console](https://console.neon.tech/) создайте проект `walletbot` и базу `walletbot`. Выберите регион рядом с регионом Vercel. В диалоге **Connect** возьмите PostgreSQL connection string с `sslmode=require`. Для коротких serverless-соединений подходит pooled endpoint (`-pooler` в имени хоста). Сохраните строку в `DATABASE_URL`, не в код.

Схема применяется командой `python -m scripts.migrate`. Скрипт идемпотентный, создаёт только таблицы и индекс. Новая база не должна содержать чужие приложения или данные.

## GitHub → Vercel

### Однократная настройка

1. Создайте приватный GitHub-репозиторий `WalletBot` и отправьте туда эту папку. `.venv`, `.env.local`, кеши, IDE и настройки Vercel исключены из Git.
2. Создайте проект Vercel, Framework Preset: **Other**, Root Directory: корень репозитория. Дополнительные Build Command / Output Directory не нужны. `api/webhook.py` определяется как Python Function.
3. Добавьте в Vercel **Production Environment Variables**:

   | Имя | Значение |
   | --- | --- |
   | `BOT_TOKEN` | Токен Telegram-бота |
   | `DATABASE_URL` | Строка подключения Neon |
   | `WEBHOOK_SECRET` | Случайная строка, одинаковая в Vercel и GitHub |
   | `BOT_CURRENCY` | `KZT` |
   | `BOT_TIMEZONE` | `Asia/Almaty` |
   | `ALLOWED_USER_IDS` | Необязательно: Telegram ID через запятую; пусто — доступ всем с раздельными данными |

4. Разрешите публичный доступ к production endpoint: Deployment Protection не должна закрывать его экраном авторизации Vercel. Проверку запросов выполняет секрет Telegram webhook. Используйте постоянный production-домен, например `https://walletbot.vercel.app`.
5. В GitHub Settings → Secrets and variables → Actions добавьте secrets: `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`, `BOT_TOKEN`, `DATABASE_URL`, `WEBHOOK_SECRET`. Идентификаторы проекта и команды можно получить после `vercel link` из `.vercel/project.json`.
6. Добавьте GitHub variables: `VERCEL_DEPLOY_ENABLED=true`, `BOT_PUBLIC_URL=https://ваш-постоянный-домен.vercel.app`.
7. Если проект импортирован через Vercel Git Integration, отключите её автоматические деплои через настройку **Git → Ignored Build Step → Don't build anything**. Production будет публиковать GitHub Actions после тестов. Иначе один push вызовет два независимых деплоя.
8. Сделайте push в `main`. Workflow проверит код на PostgreSQL 17, применит схему Neon, опубликует Vercel и зарегистрирует Telegram webhook на постоянном домене. Прямые push в другие ветки и pull requests запускают только тесты.

Production secrets должны совпадать в GitHub и Vercel; workflow не загружает токены бота и базы в Vercel автоматически. Preview-деплоям не передавайте production `BOT_TOKEN`, `DATABASE_URL`, `WEBHOOK_SECRET`. Для них используйте отдельного бота и ветку/базу Neon.

Если нужна встроенная интеграция Vercel с GitHub, оставьте `VERCEL_DEPLOY_ENABLED` выключенным, сохраните автодеплой Vercel, один раз примените схему и зарегистрируйте webhook вручную. Последующие push обновят функцию без смены webhook.

### Проверка запуска

```bash
.venv/bin/python -m scripts.webhook set --url https://ваш-постоянный-домен.vercel.app
.venv/bin/python -m scripts.webhook info
```

`GET /api/webhook` проверяет доступность функции и возвращает `service: WalletBot`; это не проверка соединения с БД. `POST` без правильного `X-Telegram-Bot-Api-Secret-Token` получает 403. Ошибки БД и доставки возвращают 500, чтобы Telegram повторил запрос.

В Telegram откройте бота, отправьте `/start`, добавьте доход `1000` на карту и расход `125,50`. Баланс карты должен стать `874,50`. Удаление расхода через `/delete номер` после подтверждения вернёт баланс `1000`.

При сетевой ошибке Telegram может повторно получить уже отправленный ответ, но финансовая операция остаётся единственной. Сохранённые результаты webhook (`wallet_updates`) нужны для повторной доставки; не удаляйте их при обычном деплое.

## Проверки

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Без `TEST_DATABASE_URL` выполняются 14 тестов, две интеграционные проверки пропускаются. Для полного запуска задайте `TEST_DATABASE_URL` на отдельную тестовую PostgreSQL. Интеграционные тесты очищают только эту базу (`wallet_*`); никогда не направляйте их на production. GitHub Actions автоматически создаёт тестовую PostgreSQL.

## Состояние подготовки в этой среде

Код и конфигурация подготовлены локально. Git-репозиторий, Neon-проект, Vercel-проект и webhook ещё не созданы: запись в `.git` запрещена политикой файловой системы, терминал не разрешает DNS для сервисов, GitHub не подтвердил подключение, интеграции Neon и Vercel отключены администратором. Локально прошли 14 тестов. Проверка с настоящей PostgreSQL здесь не выполнена из-за ограничения запуска shared memory.

Документация: [Python Functions на Vercel](https://vercel.com/docs/functions/runtimes/python), [Telegram webhook](https://core.telegram.org/bots/api#setwebhook).
