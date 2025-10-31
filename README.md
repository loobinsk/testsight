# Testsight — 🎯 умный запуск только нужных тестов

Testsight помогает CI и локальной разработке оставаться быстрыми: инструмент анализирует Python-проект, находит зависимости между модулями и тестами и запускает только те pytest-модули, которых действительно касаются последние изменения.

```
🚀 Git diff → 🧠 Анализ импорта → 🎯 Подсветка релевантных тестов → ✅ Локальный или CI прогон
```

## ✨ Ключевые особенности
- 🧭 **Статический анализ**: строит граф зависимостей вплоть до уровня символов, избегая лавинообразного запуска тестов.
- 🪄 **Интеллектуальный fallback**: если импорт найти сложно, используется токенизация путей и папок, чтобы подобрать самые близкие тесты.
- 🧱 **Гибкая конфигурация**: CLI, TOML и переменные окружения позволяют настраивать корень репозитория, стратегию `git diff`, правила именования тестов, команды запуска.
- 🧪 **20 сценариев с `git add`**: готовый набор pytest-кейсов демонстрирует, как инструмент ведет себя в реальных репозиториях.
- 🧰 **Zero hardcode**: никаких привязок к `poetry` или структурам — по умолчанию всё работает „из коробки“, но при желании легко расширяется.

## 🚀 Быстрый старт
```bash
poetry install        # или python3.10 -m venv .venv && .venv/bin/pip install -e .
poetry run testsight  # анализирует заиндексированные git-изменения и запускает pytest
```

### Пример CLI
```bash
# Посмотреть список затронутых тестов без запуска
poetry run testsight --dry-run

# Получить JSON — удобно для интеграции в CI
poetry run testsight --json

# Кастомный diff (диапазон коммитов)
poetry run testsight --diff-mode range --base main --head HEAD

# Свой командный раннер (например, через tox)
poetry run testsight --test-command "tox -e py310 --"
```

## 🧩 Интеграция в ваш проект
1. **Добавьте зависимость.**
   - PyPI (после релиза): `poetry add testsight` или `pip install testsight`.
   - Прямо из репозитория:  
     ```bash
     poetry add --git https://github.com/loobinsk/testsight.git
     # или pip install git+https://github.com/loobinsk/testsight.git
     ```
2. **Создайте конфиг.** В корне проекта положите `testsight.toml` или добавьте секцию в `pyproject.toml`:
   ```toml
   [tool.testsight]
   test-command = "pytest -q --maxfail=1"
   dry-run = false

   [tool.testsight.diff]
   mode = "staged"
   include-untracked = true
   ```
3. **Запускайте Testsight:** `poetry run testsight` (или `testsight` из вашего виртуального окружения).

### 🔁 Использование в pre-commit
Добавьте хуки, чтобы блокировать коммиты без прогонов релевантных тестов:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: testsight
        name: testsight (impacted tests)
        entry: poetry run testsight
        language: system
        pass_filenames: false
```

> Хук распечатает список затронутых тестов и запустит ваш `test-command`. Можно оставить `dry-run`, если хотите просто подсказку без запуска.

### 🤖 Интеграция в CI
```yaml
# GitHub Actions
- name: Impacted tests
  run: |
    poetry install
    poetry run testsight --json > impacted.json
    jq '.[]' impacted.json
```

## ⚙️ Конфигурация
Testsight ищет настройки в `testsight.toml`, `.testsightrc` или `pyproject.toml` (`[tool.testsight]`). Всё можно переопределить из CLI или переменных окружения (`TESTSIGHT_*`).

```toml
[testsight]
root = "."
test-command = "poetry run pytest -q"
dry-run = false

[testsight.diff]
mode = "staged"          # staged | unstaged | range | custom
include-untracked = true

[testsight.naming]
directory-markers = ["tests", "e2e"]
filename-prefixes = ["test_", "spec_"]
filename-suffixes = ["_test.py", "_spec.py"]

[testsight.tokens]
minimum-length = 3
fallback-score = 8
stopwords = ["common", "shared"]
```

## 🧠 Архитектура
- `testsight.config` — загрузка настроек и работа с CLI/TOML.
- `testsight.indexer` — обход проекта и построение графа модулей.
- `testsight.resolver` — вычисление затронутых тестов (BFS + токены).
- `testsight.runner` — интеграция с git, запуск команд, публичное API.
- `testsight.cli` — человеко-понятный интерфейс.

Асинхронность здесь не используется намеренно: основная работа CPU-bound (парсинг AST) и выполняется единичными проходами. Добавление `asyncio` усложнило бы API, не дав существенного выиграша.

## 🧪 Тесты и примеры
Команда покрыта 20 кожухами с реальными `git add`, `git commit` и вызовами CLI — см. директорию `tests/`.

```bash
# Локально: создаём окружение 3.10 и запускаем
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r <(poetry export --without-hashes)
PYTHONPATH=src pytest -q
```

Каждый тест — это готовый пример для документации: от unit-проверок токенизации до интеграционных сценариев с `ChangeDetector`.

## 📚 Полезные команды
- `poetry run testsight --help` — полный список опций CLI.
- `poetry run testsight --config ./ci/testsight.toml --json` — пример использования в CI.
- `poetry run testsight path/to/file.py` — вручную указать изменённые файлы.

## 🤝 Вклад
1. Форкните репозиторий `Testsight`.
2. Создайте ветку feature/awesome-idea.
3. Добавьте тесты, убедитесь что `pytest` зелёный (`poetry run pytest`).
4. Откройте PR — расскажите, какие сценарии вы ускорили.

Буду рад любым идеям: от дополнительных стратегий диффа до интеграций с GitHub Actions 🚀

— Danil & Testsight community
