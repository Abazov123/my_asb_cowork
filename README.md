# Agent Second Brain

**Персональный AI-ассистент с долговременной памятью**

Записывайте голосовые в Telegram — агент сам разберётся что с ними делать: создаст задачи, сохранит мысли, обновит прогресс по целям.

---

## Главное перед началом

| Параметр | Значение |
|----------|----------|
| **Время на настройку** | **2-3 часа тишины.** Не торопитесь — лучше один раз сделать правильно. |
| **Стоимость** | ~$25/мес (Claude Pro $20 + VPS $5) |
| **Приватность** | **Это ваш личный сервер. Никто, кроме вас, не имеет доступа к вашим мыслям и задачам.** |

---

## Оглавление

- [Зачем это нужно](#зачем-это-нужно)
- [Что умеет бот](#что-умеет-бот)
- [Архитектура](#архитектура)
- [Что понадобится](#что-понадобится)
- **Часть 1: Подготовка на компьютере** — 30-50 мин
  - [1.1 Установите Git и VS Code](#11-установите-git-и-vs-code)
  - [1.2 Создайте аккаунт на GitHub](#12-создайте-аккаунт-на-github)
  - [1.3 Сделайте Fork проекта](#13-сделайте-fork-проекта)
  - [1.4 Клонируйте Fork на компьютер](#14-клонируйте-fork-на-компьютер)
  - [1.5 Заполните ваши цели](#15-заполните-ваши-цели)
  - [1.6 Настройте профиль](#16-настройте-профиль)
  - [1.7 Сохраните изменения в GitHub](#17-сохраните-изменения-в-github)
- **Часть 2: Получите ключи** — 15 мин
  - [2.1 Telegram Bot Token](#21-telegram-bot-token)
  - [2.2 Ваш Telegram ID](#22-ваш-telegram-id)
  - [2.3 Deepgram API Key](#23-deepgram-api-key)
  - [2.4 Todoist API Token (опционально)](#24-todoist-api-token-опционально)
- **Часть 3: Настройка сервера** — 40-70 мин
  - [3.1 Купите VPS и подключитесь](#31-купите-vps-и-подключитесь)
  - [3.2 Создайте пользователя](#32-создайте-пользователя)
  - [3.3 Установите всё необходимое](#33-установите-всё-необходимое)
  - [3.4 Запуск бота](#34-запуск-бота)
- [Часть 4: Использование](#часть-4-использование)
- [Часть 5: Синхронизация](#часть-5-синхронизация)
- [Помощь](#помощь)
- [Продвинутые настройки](#продвинутые-настройки)

---

## Зачем это нужно

Это система управления задачами и мыслями «на стероидах». Один раз настроите — и у вас всегда под рукой понимание, что происходит в жизни.

**Кидайте туда вообще всё:**
- Голосовые сообщения — надиктуйте мысли, итоги встречи, идеи
- Пересланные посты из Telegram — бот извлечёт суть
- Фото и скриншоты — сохранит с описанием
- Документы (PDF, Word, Excel) — извлечёт текст и сохранит
- Ссылки на YouTube — скачает и транскрибирует видео
- Текстовые сообщения — любые заметки и ссылки

---

## Что умеет бот

### Команды Telegram

| Команда | Что делает |
|---------|------------|
| `/start` | Запуск и меню |
| `/status` | Сколько записей сегодня, статус целей |
| `/process` | Запустить обработку дневных записей (классификация, задачи, отчёт) |
| `/weekly` | Недельный дайджест с прогрессом по целям |
| `/do` | Произвольный запрос к AI-агенту (самая мощная команда) |
| `/done` | Завершить рефлексию |
| `/fix` | Добавить правило коррекции транскрипции |
| `/edit` | Режим пакетных правок с предпросмотром через Claude |
| `/location` | Обновить геолокацию (для погоды и таймзоны) |
| `/news` | Утренний новостной дайджест |
| `/improve` | Предложения по улучшению бота |
| `/help` | Справка |

### Кнопки быстрого доступа

```
[Статус] [Обработать] [Неделя]
[Запрос]              [Помощь]
```

### Обработка контента

| Тип контента | Что делает бот |
|-------------|----------------|
| **Голосовые** | Транскрипция через Deepgram, коррекция, сохранение в daily |
| **Текст** | Сохранение в daily-заметку |
| **Фото** | Сохранение в attachments с датой |
| **Документы** | Извлечение текста из PDF/DOCX/XLSX, транскрипция аудио |
| **Пересылки** | Извлечение сути из пересланных сообщений через Claude |
| **YouTube-ссылки** | Скачивание аудио, транскрипция, саммари |
| **Веб-ссылки** | Извлечение контента страницы |

### Автоматизация

| Процесс | Когда | Что делает |
|---------|-------|------------|
| **Обработка записей** | По команде `/process` или автоматически вечером | 3-фазный пайплайн: Capture (классификация) -> Execute (задачи + заметки) -> Reflect (отчёт + память) |
| **Утренний брифинг** | Утром | Погода, новости, задачи на день |
| **Недельный дайджест** | Воскресенье | Итоги недели, прогресс по целям |
| **Ночная имплементация** | Ночью (если включено) | Авто-реализация предложений по улучшению бота |

### Интеграции

| Сервис | Назначение |
|--------|------------|
| **Todoist** | Управление задачами (создание, перенос, завершение) |
| **Deepgram** | Транскрипция голоса (русский + английский) |
| **Claude Code** | AI-обработка, анализ, рефлексия |
| **YouTube** | Скачивание и транскрипция видео |
| **Obsidian** | Визуализация vault через Git-синхронизацию |

---

## Архитектура

```
Telegram  ──>  Бот (aiogram)  ──>  Vault (Obsidian-совместимый)
    ^               |                        |
    |               v                        v
    |          Claude Code             GitHub (sync)
    |               |
    |               v
    └──────  Todoist (задачи)
```

**Структура vault:**
```
vault/
  daily/           # Ежедневные записи (YYYY-MM-DD.md)
  goals/           # Каскад целей (3 года -> год -> месяц -> неделя)
  thoughts/        # Обработанные заметки по категориям
    reflections/   # Рефлексии и размышления
    learnings/     # Уроки и знания
    ideas/         # Идеи
    projects/      # Проектные заметки
    business/      # Бизнес-заметки
  MOC/             # Maps of Content (индексы)
  attachments/     # Фото по датам
  summaries/       # Недельные сводки
  agent/           # Заметки агента
  templates/       # Шаблоны
  .claude/         # Инструкции для Claude (skills, rules, agents)
  .obsidian/       # Настройки Obsidian
```

---

## Что понадобится

| Компонент | Зачем | Стоимость |
|-----------|-------|-----------|
| **Claude Pro/Max** | AI-агент для обработки записей | $20/мес |
| **VPS-сервер** | Чтобы бот работал 24/7 | ~$5/мес |
| **GitHub** | Хранение и синхронизация записей | бесплатно |
| **Deepgram** | Транскрипция голосовых | бесплатно ($200 на старт) |
| **Todoist** | Управление задачами (опционально) | бесплатно / $4/мес |

**Итого: ~$25/мес**

### Где взять VPS

Нужен сервер НЕ в России/Беларуси — из-за блокировки Claude по территории.

- [Contabo](https://contabo.com) — $4.96/мес
- [OVH](https://ovhcloud.com) — $5/мес
- [Hetzner](https://hetzner.com) — $4.15/мес

---

# Часть 1: Подготовка на компьютере

### 1.1 Установите Git и VS Code

**Windows:**
1. Скачайте Git: [git-scm.com/download/win](https://git-scm.com/download/win)
2. Установите: Next -> Next -> Install -> Finish
3. Скачайте VS Code: [code.visualstudio.com](https://code.visualstudio.com/)
4. Установите: Next -> Next -> Install -> Finish

**Mac:**
1. Откройте Terminal (`Cmd + Пробел`, наберите `Terminal`)
2. Выполните `git --version` — если предложит установить, согласитесь
3. Скачайте VS Code: [code.visualstudio.com](https://code.visualstudio.com/)
4. Перетащите в Applications

---

### 1.2 Создайте аккаунт на GitHub

1. Зайдите на [github.com](https://github.com)
2. **Sign up** -> введите email, пароль, логин
3. Подтвердите email

> Запомните логин — он понадобится далее.

---

### 1.3 Сделайте Fork проекта

1. Откройте ссылку на репозиторий (попросите её у того, кто дал вам эту инструкцию)
2. Нажмите кнопку **Fork** в правом верхнем углу
3. Нажмите **Create fork**

> **ВАЖНО:** Сделайте репозиторий приватным!
> Settings -> Danger Zone -> Change visibility -> **Private**

---

### 1.4 Клонируйте Fork на компьютер

1. Откройте VS Code
2. `Ctrl+Shift+P` (Mac: `Cmd+Shift+P`) -> `Git: Clone`
3. Введите `https://github.com/ВАШ_ЛОГИН/agent-second-brain.git`
4. Выберите папку «Документы» -> **Open**

---

### 1.5 Заполните ваши цели

> **ЭТО САМЫЙ ВАЖНЫЙ ШАГ.** Бот использует цели для приоритизации.

В VS Code откройте `vault/goals/` — там 4 файла:

| Файл | Что заполнить |
|------|---------------|
| `0-vision-3y.md` | Видение на 3 года по сферам жизни |
| `1-yearly-2025.md` | Цели на год с разбивкой по кварталам |
| `2-monthly.md` | Топ-3 приоритета на месяц |
| `3-weekly.md` | ONE Big Thing — главная задача недели |

**Как заполнить быстро:** Скопируйте содержимое файла в ChatGPT/Claude и попросите:
```
Это шаблон моего 3-летнего видения. Помоги заполнить.
Задавай вопросы ПО ОДНОМУ, жди мой ответ.
В конце верни заполненный документ в том же формате.
```

---

### 1.6 Настройте профиль

Откройте `vault/.claude/skills/dbrain-processor/references/about.md` и заполните информацию о себе.

Также настройте под себя файлы в `vault/.claude/skills/dbrain-processor/references/`:

| Файл | Что настроить |
|------|---------------|
| `about.md` | Ваш профиль, роль, стиль работы |
| `classification.md` | Категории задач, имена проектов |
| `todoist.md` | Проекты в Todoist, приоритеты |

> Можно заархивировать папку `references/` и отправить в ChatGPT/Claude:
> «Помоги заполнить эти файлы под меня. Задавай вопросы по одному.»

---

### 1.7 Сохраните изменения в GitHub

1. В VS Code нажмите иконку Source Control (третья слева)
2. В поле Message напишите: `Initial setup with my goals`
3. Нажмите **Commit** -> **Yes** (stage all) -> **Sync Changes**

---

# Часть 2: Получите ключи

### 2.1 Telegram Bot Token

1. В Telegram найдите `@BotFather`
2. Отправьте `/newbot`
3. Придумайте имя и username (должен заканчиваться на `bot`)
4. Скопируйте токен: `7123456789:AAHxxxxxxxxx...`

### 2.2 Ваш Telegram ID

1. В Telegram найдите `@userinfobot`
2. Отправьте любое сообщение
3. Скопируйте число из строки **Id:** (например `123456789`)

### 2.3 Deepgram API Key

1. Зарегистрируйтесь на [console.deepgram.com](https://console.deepgram.com/)
2. Settings -> API Keys -> Create API Key
3. Скопируйте ключ (показывается только один раз!)

### 2.4 Todoist API Token (опционально)

1. Войдите на [todoist.com](https://todoist.com)
2. Аватар -> Settings -> Integrations -> Developer
3. Скопируйте API token

---

# Часть 3: Настройка сервера

### 3.1 Купите VPS и подключитесь

1. Купите VPS на [Contabo](https://contabo.com), [OVH](https://ovhcloud.com) или [Hetzner](https://hetzner.com)
2. Выберите **Ubuntu 22.04**
3. Получите IP-адрес и пароль на email

Подключитесь:
```bash
ssh root@ВАШ_IP_АДРЕС
```

> При вводе пароля символы не отображаются — это нормально.

### 3.2 Создайте пользователя

```bash
adduser myuser
usermod -aG sudo myuser
su - myuser
```

### 3.3 Установите всё необходимое

Выполняйте команды по одной:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl wget build-essential software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa && sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev
curl -LsSf https://astral.sh/uv/install.sh | sh && source ~/.bashrc
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
sudo npm install -g @anthropic-ai/claude-code
claude auth login
```

> Подробная инструкция по настройке VPS (SSH ключи, firewall, безопасность): `docs/vps-setup.md`
>
> Скилл для автоматизации через Claude Code: `docs/server-management/SKILL.md`

### 3.4 Запуск бота

```bash
curl -fsSL https://raw.githubusercontent.com/ВАШ_ЛОГИН/agent-second-brain/main/bootstrap.sh | bash
```

> **Замените `ВАШ_ЛОГИН`** на ваш логин GitHub!

Скрипт автоматически:
- Скачает ваш проект
- Спросит токены (Telegram, Deepgram, Todoist)
- Создаст `.env` конфигурацию
- Установит зависимости
- Настроит автозапуск через systemd
- Запустит бота

**Если curl не сработал:**
```bash
cd ~ && git clone https://github.com/ВАШ_ЛОГИН/agent-second-brain.git
cd agent-second-brain && bash setup.sh
```

### Проверка работоспособности

| Что проверить | Как |
|---------------|-----|
| Бот запущен | `sudo systemctl status d-brain-bot` — должен быть `active (running)` |
| Бот отвечает | Отправьте `/start` в Telegram |
| Голос работает | Отправьте голосовое сообщение |
| Логи | `sudo journalctl -u d-brain-bot -f` |

---

# Часть 4: Использование

### Основной рабочий процесс

1. **В течение дня** — записывайте голосовые, пересылайте посты, отправляйте фото
2. **Вечером** — нажмите `Обработать` или дождитесь автоматической обработки
3. **Бот создаст** — задачи в Todoist, заметки в vault, отчёт в Telegram
4. **В воскресенье** — получите недельный дайджест с прогрессом по целям

### Кнопка «Запрос» — самая мощная

Нажмите **Запрос** и скажите что угодно:

| Запрос | Что сделает |
|--------|-------------|
| «Покажи задачи на сегодня» | Достанет из Todoist |
| «Перенеси просроченные на понедельник» | Найдёт и перенесёт |
| «Что я записывал про маркетинг?» | Найдёт в заметках |
| «Обнови недельные цели» | Откроет и обновит файл |
| «Создай задачу: позвонить в банк» | Создаст в Todoist |
| «На чём сфокусироваться сегодня?» | Проанализирует цели и задачи |

### Словарь коррекций

Бот учится правильно транскрибировать ваши имена и термины:
- `/fix` — добавить правило (например: «Петя -> Пётр Иванов»)
- `/edit` — режим пакетных правок с предпросмотром

Правила сохраняются в `vault/corrections.md`.

### Веб-портал для больших файлов

Для загрузки записей встреч (файлы > 20 МБ) есть веб-портал. Настраивается через nginx на порту 8090.

---

# Часть 5: Синхронизация

### Obsidian (рекомендуется)

1. Скачайте [Obsidian](https://obsidian.md)
2. Open folder as vault -> выберите папку `vault`
3. Все заметки, связи и графы будут доступны

### GitHub

Заметки автоматически синхронизируются в ваш приватный репозиторий. Можно просматривать прямо на github.com.

### Через бота

Просто спросите: «Что я записал вчера?», «Покажи цели на неделю», «Найди заметку про [тема]»

---

# Помощь

### Если что-то не работает

1. Подключитесь к серверу
2. Перейдите в папку проекта: `cd ~/agent-second-brain`
3. Запустите `claude` и опишите проблему

### Частые проблемы

| Проблема | Решение |
|----------|---------|
| Бот не отвечает | `sudo systemctl status d-brain-bot` — проверьте статус |
| Голос не распознаётся | Проверьте `DEEPGRAM_API_KEY` в `.env` |
| Claude не работает | `claude auth status` -> если не авторизован: `claude auth login` |
| Задачи не создаются | Проверьте `TODOIST_API_KEY` в `.env` |
| Бот не запускается после перезагрузки | `sudo systemctl enable d-brain-bot` |

### Полезные команды

```bash
# Логи бота
sudo journalctl -u d-brain-bot -f

# Перезапуск
sudo systemctl restart d-brain-bot

# Остановка
sudo systemctl stop d-brain-bot

# Ручной запуск (для отладки)
cd ~/agent-second-brain && uv run python -m d_brain
```

---

# Продвинутые настройки

<details>
<summary><strong>Дополнительные API-ключи</strong></summary>

В `.env` можно добавить опциональные ключи:

```bash
# YouTube Data API v3 — для транскрипции видео
YOUTUBE_API_KEY=

# Firecrawl — для скрапинга веб-страниц
FIRECRAWL_API_KEY=

# Oura Ring — данные о сне и здоровье
OURA_ACCESS_TOKEN=

# Anthropic API — если Claude Code не авторизован
ANTHROPIC_API_KEY=
```

</details>

<details>
<summary><strong>Ночная авто-имплементация</strong></summary>

Бот может сам улучшать свой код по ночам. Включается в `.env`:

```bash
NIGHT_IMPLEMENT_ENABLED=true
```

Как работает:
1. `/improve` собирает предложения по улучшению
2. Ночью `scripts/night_implement.sh` запускает Claude для реализации
3. Утром вы получаете уведомление о внесённых изменениях

</details>

<details>
<summary><strong>MCP-серверы (дополнительные интеграции)</strong></summary>

Система использует **MCP (Model Context Protocol)** для подключения к внешним сервисам.

По умолчанию настроен Todoist. Можно подключить:

| Сервис | MCP-сервер |
|--------|------------|
| **Google Workspace** | [google_workspace_mcp](https://github.com/taylorwilsdon/google_workspace_mcp) |
| **Notion** | [notion-mcp-server](https://github.com/makenotion/notion-mcp-server) |
| **Things 3** | [things-mcp](https://github.com/hald/things-mcp) |
| **GitHub** | [github-mcp-server](https://github.com/github/github-mcp-server) |

Настройка MCP: `docs/mcp-cli-setup.md`

</details>

<details>
<summary><strong>Веб-портал для загрузки аудио</strong></summary>

Для больших файлов (записи встреч) есть веб-портал на FastAPI.

Настройка systemd:
```ini
[Unit]
Description=d-brain Web Upload
After=network.target

[Service]
Type=simple
User=myuser
WorkingDirectory=/home/myuser/agent-second-brain
ExecStart=/home/myuser/.local/bin/uv run uvicorn d_brain.web.app:app --host 127.0.0.1 --port 8090
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Для внешнего доступа настройте nginx reverse proxy с SSL.

</details>

<details>
<summary><strong>Настройка systemd вручную</strong></summary>

```bash
sudo nano /etc/systemd/system/d-brain-bot.service
```

```ini
[Unit]
Description=d-brain Telegram Bot
After=network.target

[Service]
Type=simple
User=myuser
WorkingDirectory=/home/myuser/agent-second-brain
ExecStart=/home/myuser/.local/bin/uv run python -m d_brain
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable d-brain-bot
sudo systemctl start d-brain-bot
```

</details>

<details>
<summary><strong>Управление VPS через Claude Code</strong></summary>

В `docs/server-management/` находится skill для настройки и управления VPS через Claude Code.

Покрывает: SSH настройку, firewall, fail2ban, Docker, деплой, мониторинг.

Используйте его при первичной настройке сервера или для автоматизации серверных задач.

</details>

<details>
<summary><strong>Skills и агенты Claude</strong></summary>

Внутри `vault/.claude/` находятся инструкции для Claude Code:

**Skills (навыки):**
| Skill | Назначение |
|-------|------------|
| `dbrain-processor` | Вечерняя обработка записей (3-фазный пайплайн) |
| `morning-briefer` | Утренний брифинг (погода, новости, задачи) |
| `todoist-ai` | Управление задачами через MCP |
| `graph-builder` | Анализ и построение связей в vault |
| `agent-memory` | Управление памятью с Ebbinghaus decay |
| `vault-health` | Мониторинг здоровья графа знаний |
| `agent-improver` | Самоулучшение бота |

**Agents (агенты):**
| Agent | Назначение |
|-------|------------|
| `weekly-digest` | Недельный обзор с прогрессом |
| `goal-aligner` | Проверка соответствия задач целям |
| `note-organizer` | Организация vault, починка связей |
| `inbox-processor` | GTD-обработка входящих |

</details>

---

## Структура проекта

```
agent-second-brain/
  src/d_brain/          # Python-код бота
    bot/                # Telegram-хендлеры (aiogram)
    services/           # Бизнес-логика (транскрипция, Claude, хранилище)
    web/                # Веб-портал для загрузки аудио
    config.py           # Конфигурация из .env
  scripts/              # Bash/Python скрипты автоматизации
  vault/                # Obsidian-совместимое хранилище
  docs/                 # Документация и руководства
  setup.sh              # Скрипт установки на VPS
  install.sh            # Скрипт установки на Mac/WSL
  pyproject.toml        # Python зависимости (uv)
```

---

## Словарь терминов

| Термин | Что это |
|--------|---------|
| **VPS** | Удалённый мини-компьютер, работает 24/7 |
| **SSH** | Подключение к VPS через терминал |
| **Token** | Секретный код для доступа к сервису |
| **.env** | Файл с секретами (не публикуется) |
| **Fork** | Ваша личная копия проекта на GitHub |
| **Vault** | Хранилище заметок (совместимо с Obsidian) |
| **MCP** | Протокол подключения AI к внешним сервисам |

---

> **Если запутались на каком-то шаге** — откройте [claude.ai](https://claude.ai) и напишите:
> «Помоги разобраться с настройкой agent-second-brain, я застрял на шаге [номер]»
