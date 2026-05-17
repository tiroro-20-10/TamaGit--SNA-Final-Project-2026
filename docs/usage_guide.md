# TamaGit — Полная инструкция по использованию

В этом документе описано как запустить и проверить **все** функции проекта.

---

## Содержание

1. [Установка](#1-установка)
2. [Первый запуск — вылупление питомца](#2-первый-запуск)
3. [tamagit status — полный статус](#3-tamagit-status)
4. [tamagit log — история событий](#4-tamagit-log)
5. [tamagit scan — сканирование репозитория](#5-tamagit-scan)
6. [Питомец в bash prompt](#6-питомец-в-bash-prompt)
7. [tamagit live — живой TUI](#7-tamagit-live)
8. [Webhook на VPS](#8-webhook-на-vps)
9. [Тест всех GitHub событий](#9-тест-всех-github-событий)
10. [Daily quest и streak](#10-daily-quest-и-streak)
11. [Смерть, кладбище и возрождение](#11-смерть-кладбище-и-возрождение)
12. [Достижения](#12-достижения)
13. [Тесты](#13-тесты)
14. [Docker](#14-docker)

---

## 1. Установка

### Вариант A: локально (рекомендую для разработки)

```bash
# Клонируй репозиторий
git clone https://github.com/tiroro-20-10/TamaGit--SNA-Final-Project-2026.git
cd TamaGit--SNA-Final-Project-2026

# Установи зависимости
pip install -e .
# или через Poetry:
poetry install

# Проверь что tamagit доступен
tamagit help
```

Ожидаемый вывод: список всех команд включая `live`, `init`, `status` и т.д.

### Вариант B: только через Docker (без локальной установки Python)

```bash
docker compose build
# Все команды через:
docker compose run --rm tamagit <команда>
# Например:
docker compose run --rm tamagit status
```

---

## 2. Первый запуск

### Запуск инициализации

```bash
tamagit init
```

**Что должно произойти:**

1. Экран очищается
2. Показывается анимация яйца (5 кадров ~4 секунды):
   - Яйцо трясётся
   - Появляются трещины
   - Яйцо раскалывается
   - Питомец выпрыгивает
3. Вопрос: `Give your team pet a name:` → введи имя, например `Pixel`
4. Вопрос: `GitHub repo to watch (owner/name):` → введи `tiroro-20-10/TamaGit--SNA-Final-Project-2026`
5. Показывается первый `tamagit status`

**Файл создаётся:**

```bash
cat ~/.tamagit/state.json
```

Должен содержать `"name": "Pixel"`, `"alive": true`, статы около 80.

---

## 3. tamagit status

```bash
tamagit status
```

**Что видно в шапке:**
- Name, Age (дней с рождения)
- State (ecstatic/happy/okay/sad/miserable/sleeping/on_fire/ghost)
- Streak (если > 0)
- Fed by (кто последний сделал push через webhook)
- Repo

**ASCII-арт:** меняется под настроение (8 разных состояний)

**Прогресс-бары:**
- Hunger / Energy / Mood / Health
- Цвет: 🔴 0–24 / 🟠 25–49 / 🟡 50–74 / 🟢 75–100

**Tracked Repos:** (после первого `tamagit scan`)
```
  myrepo  (main)  ✅ clean    scanned 5m ago
```

**Daily Quest:** (после первого использования в новый день)
```
  🎯 Push your latest changes  [in progress]
```

**Ачивки:** список разблокированных

**Recent events:** последние 5 записей из лога

---

## 4. tamagit log

```bash
tamagit log
```

Показывает все события за жизнь питомца — коммиты, CI, квесты, ачивки. Полезно для проверки что события от webhook доходят.

---

## 5. tamagit scan

```bash
# Сканировать текущую папку
tamagit scan

# Сканировать конкретный репозиторий
tamagit scan /path/to/your/repo
```

**Что проверяет:**
- Находится ли папка внутри git-репозитория
- Текущая ветка
- Есть ли незакоммиченные изменения (⚠ dirty)
- Последний коммит (hash + сообщение)
- Количество непушеных / непулленых коммитов

**Влияние на питомца:**
- Новый коммит → Hunger +20, Mood +10
- Грязный репозиторий → Mood -5
- Непушеные коммиты → Energy -(до 15)
- Чистый репозиторий → Health +3

**Проверить dirty статус:**

```bash
# Создай незакоммиченный файл
echo "test" > test_dirty.txt
tamagit scan
# Должно показать: "Uncommitted changes — pet is uneasy"

# Закоммить или удали
rm test_dirty.txt
tamagit scan
# Должно показать: "Repository is clean — pet is pleased"
```

**После `scan` запусти `tamagit status`** — в разделе "Tracked Repos" появится запись с ✅ или ⚠.

---

## 6. Питомец в bash prompt

### Установка

```bash
tamagit install-prompt
source ~/.bashrc
```

**Результат:** Каждый новый промпт показывает:
```
[Pixel(^.^) H:80 E:74 M:82] user@host:~$
```

Иконка меняется по настроению:
- `^o^` ecstatic
- `^.^` happy
- `-.-` okay
- `T.T` sad
- `;_;` miserable
- `z.z` sleeping
- `>^<` on_fire (streak≥7)
- `x.x` ghost (мёртв)

### Реакции на команды (автоматически после install-prompt)

```bash
git push       # → ( ^.^ )  pushed! team pet is fed ✓
git push       # (если rejected) → ( T.T )  push rejected... fix and retry
git commit -m "test"   # → ( ^.^ )  new commit! pet is pleased
git pull       # → ( ^.^ )  synced! team keeps moving
pytest         # (если тесты зелёные) → ( ^o^ )  tests green! pet loves clean code
```

Реакция появляется случайно (35% на успех, 55% на ошибку) — не на каждую команду.

### Отключение

```bash
tamagit uninstall-prompt
source ~/.bashrc
```

---

## 7. tamagit live

**Открой отдельный терминал** и запусти:

```bash
tamagit live
```

**Что видно:**
- Анимированный ASCII-питомец (мигает, меняет позы каждые 700мс)
- Прогресс-бары статов с цветом
- Daily quest
- Командная информация (кто кормил, streak)
- Последние 7 событий

**Реакции при новых событиях:**

| Событие | Анимация | Toast уведомление |
|---|---|---|
| push/commit | eating (`*o*`) | 🍖 alice pushed! Nom nom! |
| PR merged | excited (`>^.^<`) | ✨ PR merged! Health bonus! |
| CI failed | sad (`T.T`) | 💔 CI failed... pet is stressed |
| Quest done | trophy (`^o^🎯`) | 🎯 Daily quest complete! |

**Горячие клавиши:**
- `Q` — выход
- `R` — принудительное обновление из state.json

**Тест в реальном времени:**
1. Открой два терминала
2. В первом: `tamagit live`
3. Во втором: сделай `git push` (или эмулируй curl-ом webhook)
4. В живом терминале питомец должен отреагировать в течение 5 секунд

---

## 8. Webhook на VPS

### Подключение к серверу

```bash
ssh root@72.56.239.253
cd /opt/TamaGit
```

### Проверка .env

```bash
cat .env
```

Должно содержать:
```
GITHUB_REPO=tiroro-20-10/TamaGit--SNA-Final-Project-2026
GITHUB_WEBHOOK_SECRET=<ваш_секрет>
```

Если `GITHUB_WEBHOOK_SECRET` пустой — сгенерируй:

```bash
openssl rand -hex 32
# Скопируй вывод и впиши в .env
```

### Запуск webhook сервера

```bash
docker compose up -d --build webhook
docker compose ps
# webhook должен быть Up
```

### Проверка доступности

```bash
# На сервере
curl http://localhost:8000/health
# Публично
curl http://72.56.239.253:8000/health
# Ожидаем: {"status":"ok"}
```

Если порт закрыт:
```bash
ufw allow 8000/tcp
```

### Настройка webhook в GitHub

1. Открой `https://github.com/tiroro-20-10/TamaGit--SNA-Final-Project-2026`
2. Settings → Webhooks → Add webhook
3. Заполни:
   - **Payload URL:** `http://72.56.239.253:8000/webhook/github`
   - **Content type:** `application/json`
   - **Secret:** значение `GITHUB_WEBHOOK_SECRET` из `.env`
   - **SSL verification:** Disable (HTTP)
   - **Events:** Pushes, Pull requests, Issues, Workflow runs
   - **Active:** ✅
4. Нажми Save
5. GitHub автоматически отправит ping — в Recent Deliveries должен быть статус 200

### Просмотр логов webhook

```bash
docker compose logs -f webhook
```

---

## 9. Тест всех GitHub событий

### Push (самое важное)

```bash
echo "test $(date)" >> webhook-test.txt
git add . && git commit -m "test: webhook push"
git push
```

**Ожидаемый результат:**
- В `docker compose logs webhook`: `tiroro pushed 1 commit(s) to 'main'`
- В `tamagit log`: запись с именем того, кто пушнул
- Hunger ↑, Mood ↑, streak обновился
- В `tamagit live`: анимация eating + toast уведомление

### CI (GitHub Actions)

Если в репозитории есть workflow — он запустится при push. Проверь:

```bash
docker compose run --rm tamagit log
# Ожидаем: CI 'tests' passed (triggered by <username>)
# Или: CI 'tests' failed — ...
```

### Pull Request

1. Создай ветку: `git checkout -b test-pr`
2. Сделай коммит и запуши: `git push -u origin test-pr`
3. Открой PR в GitHub
4. Смерджи PR
5. Проверь: `docker compose run --rm tamagit log` — должна появиться запись `merged PR`

### Issues

1. Создай issue в GitHub
2. Закрой его
3. Проверь: `tamagit log` — должна появиться запись `closed issue: "..."`

---

## 10. Daily Quest и Streak

### Daily Quest

```bash
tamagit status
# В разделе "Daily Quest" должно быть случайное задание, например:
# 🎯 Push your latest changes  [in progress]
```

Квест генерируется раз в день. При выполнении:
- Mood +20, Hunger +10
- В логе: `🎯 Quest done: ...`
- Ачивка `Quest Accepted` при первом выполнении

Возможные квесты:
- Push your latest changes to remote
- Make at least 1 new commit
- Pull the latest changes from remote
- Close an open GitHub issue
- Get the CI pipeline green
- Merge an open pull request

### Streak

Streak растёт при каждом первом push-е за день. Проверить:

```bash
tamagit status
# В шапке: Streak: 📅 3 days in a row
```

При streak ≥ 7 дней + хорошие статы питомец переходит в состояние `on_fire`:
- ASCII: `(>^.^<) 🔥`
- Иконка в промпте: `>^<`

---

## 11. Смерть, кладбище и возрождение

### Эмуляция смерти (для теста)

Напрямую отредактируй state.json:

```bash
# На сервере:
nano ~/.tamagit/state.json
# Или на локальной машине:
nano ~/.tamagit/state.json
```

Измени значение `"health"` на `0` и сохрани. Затем:

```bash
tamagit status
```

**Что должно произойти:**
- Серый интерфейс с `👻` призраком
- Сообщение `💀 Your team pet has died.`
- Чеклист cooldown задач (commits 0/3, issues 0/1, CI 0/1)
- Иногда случайное сообщение призрака в духе `~(*-*)~ Pixel: you abandoned me...`

### Прохождение cooldown

Сделай через GitHub:
1. 3 push-а (или 3 коммита через `tamagit scan` после каждого commit)
2. Закрой 1 issue
3. Дождись зелёного CI (или сделай успешный push с рабочим workflow)

Прогресс виден в `tamagit status`:
```
    ✅  Make 3 commits   [3/3]
    ✅  Close 1 issue    [1/1]
    ☐   CI success once  [0/1]
```

### Возрождение после cooldown

```bash
tamagit init
```

Питомец старый уходит в кладбище → анимация → вводишь имя нового.

### Кладбище

```bash
tamagit graveyard
```

Показывает всех умерших питомцев с:
- Именем, датами жизни
- Причиной смерти
- Ачивками (в т.ч. посмертными: `💔 First Loss`, `🍽️ Starved`, `🔥 Burned Out`)

---

## 12. Достижения

### Git ачивки (зарабатываются при жизни)

| Ачивка | Условие |
|---|---|
| First Commit | первый коммит замечен |
| CI Hero | CI прошёл успешно |
| Issue Closer | issue закрыт |
| PR Master | PR смерджен |
| Healthy Repo | health ≥ 80 |
| Happy Pet | mood ≥ 80 |
| Full Belly | hunger ≥ 90 |
| Energised | energy ≥ 90 |
| 7-Day Streak | streak 7+ дней |
| 30-Day Streak | streak 30+ дней |

### Ачивки за квесты

| Ачивка | Условие |
|---|---|
| Quest Accepted | первый выполненный квест |
| Quest Master | 10 квестов выполнено |
| Daily Devotion | 30 квестов выполнено |

### Посмертные ачивки (показываются только в кладбище)

| Ачивка | Условие |
|---|---|
| 💔 First Loss | первая смерть в команде |
| 😬 Serial Offender | уже третья смерть |
| 💀 Graveyard Keeper | пятая+ смерть |
| ⚡ Gone in a Day | умер не дожив до суток |
| 🌱 Short Life | умер до 3 дней |
| 🎖️ Veteran | прожил 30+ дней |
| 🏛️ Legend | прожил 60+ дней |
| 🍽️ Starved | умер от отсутствия коммитов |
| 🔥 Burned Out | умер от постоянно красного CI |
| 😔 Left Unresolved | умер от брошенных issues |
| 💫 Spectacular Failure | умер сразу от трёх причин |
| 🏆 Well Decorated | умер имея 5+ ачивок |
| 🎯 Quest Champion | выполнил 10+ квестов до смерти |

---

## 13. Тесты

```bash
# В папке проекта
pytest tests/ -v
```

Покрытие:
- save/load roundtrip
- default state creation
- stats semantics (higher is better)
- push event increases stats
- CI fail decreases stats
- contributor tracking (who fed the pet)
- streak: consecutive days / gap reset
- daily quest generation and completion
- quest achievement unlock
- sleeping state after 12h
- cooldown logic
- graveyard bury
- death achievements (First Loss, Short Life, Starved)

---

## 14. Docker

### Только webhook сервер (основное использование)

```bash
# Запуск
docker compose up -d webhook

# Проверка
docker compose ps
curl http://72.56.239.253:8000/health

# Логи
docker compose logs -f webhook

# Перезапуск после изменений кода
git pull && docker compose up -d --build webhook
```

### CLI команды через Docker

```bash
docker compose run --rm tamagit status
docker compose run --rm tamagit log
docker compose run --rm tamagit graveyard
docker compose run --rm tamagit scan /workspace
```

> **Примечание:** `tamagit live` через Docker не поддерживается (TUI требует интерактивного терминала). Используй локальную установку.

---

## Быстрый чеклист для демо

- [ ] `tamagit init` → анимация яйца + имя питомца
- [ ] `tamagit status` → шапка, ASCII, прогресс-бары, репо, квест
- [ ] `tamagit scan` → грязный/чистый репо, влияние на статы
- [ ] `tamagit install-prompt && source ~/.bashrc` → питомец в строке
- [ ] Сделать `git push` → реакция в промпте (`( ^.^ )  pushed!`)
- [ ] `tamagit live` → анимация, live обновление при push
- [ ] Webhook ping → статус 200 в GitHub
- [ ] Push через GitHub → питомец реагирует в live TUI
- [ ] CI green/red → health меняется
- [ ] `tamagit graveyard` → кладбище (может быть пустым)
- [ ] Эмулировать смерть → серый интерфейс, cooldown
- [ ] `pytest tests/ -v` → 17 тестов зелёных
