# QWEN.md – Обзор проекта и рекомендации

## Проект : GPON Diagnostic Framework

**Назначение** – автоматизированная диагностика GPON‑сетей (Huawei OLT) через Telnet. Система собирает параметры ONT, парсит вывод, применяет набор правил и генерирует отчёты (текст/JSON). Предусмотрен веб‑интерфейс на Flask с SSE‑логами и SQLite‑хранилищем истории диагностики.

### Технологический стек
- **Python ≥ 3.12** (type‑annotated, dataclasses)
- **uv** – менеджер зависимостей и сред выполнения
- **Flask + Flask‑SQLAlchemy** – веб‑интерфейс и хранение отчётов
- **telnetlib3** – взаимодействие с OLT по Telnet
- **pyyaml**, **python‑dotenv**, **pyperclip**
- **hermes‑lockutils** – файловые блокировки (обязательно использовать при работе с общими файлами)

### Архитектура (директория `core/`)
| Модуль | Назначение |
|--------|------------|
| `models.py` | dataclasses `OntMetrics`, `LanPort`, `MacDevice` (с фиксированными sentinel‑значениями) |
| `parser.py` | словарь `PATTERNS` и функции `parse_*` – извлечение параметров из вывода OLT |
| `collector.py` | обёртка над Telnet‑соединением, собирает сырой вывод |
| `engine.py` | `DiagnosticEngine`, базовые `DEFAULT_RULES` + `EXTENDED_RULES` (добавлять новые только в конец) |
| `thresholds.py` | `Thresholds` – пороги, используемые правилами |
| `report.py` | модели `DiagnosisProblem`, `DiagnosisReport`; методы `to_text()`, `to_dict()` |
| `reporter.py` | запись отчётов в `data/reports/` с использованием `hermes‑lockutils/file_lock` |
| `olt.py` | singleton‑реестр соединений `OltConnection` |
| `adapter.py` / `crt_stub.py` | адаптеры для SecureCRT (используются в тестах) |
| `web/app.py` | Flask‑приложение, SSE‑логирование, просмотр последних отчётов |

## Сборка и запуск
```bash
# Установка зависимостей
uv sync

# CLI‑диагностика (пример)
uv run diagnose.py 0/1/3/9               # авто‑выбор OLT из config.yaml
uv run diagnose.py 0/1/3/9 --olt "OLT-17.232"   # указать конкретный OLT
uv run diagnose.py 0/1/3/9 --json --no-save   # вывод JSON без сохранения
uv run diagnose.py 0/1/3/9 --clipboard        # скопировать отчёт в буфер

# Тесты (smoke‑тесты, не требуют реального OLT)
uv run python -m tests.test_smoke

# Веб‑интерфейс
uv run python -m web.app   # открыть http://localhost:5000
```
> **Важно**: учётные данные OLT передаются **только** через переменные окружения `GPON_OLT_<NAME>_USERNAME` / `GPON_OLT_<NAME>_PASSWORD`. Не хранить их в репозитории.

## Конвенции и ограничения (из `AGENTS.md`)
- **Не изменять** структуру `OntMetrics` без добавления новых полей в конец с `field(default=…)`.
- **Не менять** порядок правил в `engine.py`; новые правила добавляются в конец `EXTENDED_RULES`.
- **Не редактировать** регулярные выражения в `PATTERNS` без наличия тестов на реальном выводе.
- **Логирование** только через `logging.getLogger(__name__)`; `print` допускается лишь в `diagnose.py:main()`.
- **Исключения** – минимум `logger.warning()`, без «bare except». 
- **Sentinel‑значения** (`-1`, `999.0`, `"-"` и др.) обязаны оставаться и проверяться явно.
- **`.env`** игнорируется Git‑ом; не создавать новые файлы `.env`.
- **Добавление зависимостей** в `pyproject.toml` только после согласования.

## Тестирование
- **Smoke‑тест**: `uv run python -m tests.test_smoke` покрывает базовый движок, парсеры и репортер. После любого изменения в `core/` обязательно запускать.
- При добавлении нового правила – добавить соответствующий тест в `tests/` и убедиться, что smoke‑тесты проходят.

## Полезные скрипты
| Скрипт | Описание |
|--------|----------|
| `probe_all.py` | отладочный скрипт, требует учётные данные OLT |
| `run_waitress.py` | запуск Flask‑приложения через Waitress (production) |
| `watchdog.py` | мониторинг процессов (используется в CI) |
| `set_env_and_probe.py` | утилита для установки переменных окружения и проверки соединения |

## Как добавить новое диагностическое правило
1. **Создать** функцию `def rule_<name>(metrics: OntMetrics, t: Thresholds) -> DiagnosisProblem | None:` в `core/engine.py`.
2. **Добавить** проверку `if not metrics.is_online: return None` (кроме `rule_offline` и аналогов).
3. **Внести** правило в конец списка `EXTENDED_RULES`:
   ```python
   EXTENDED_RULES = DEFAULT_RULES + [Rule("<name>", rule_<name>, "category")]
   ```
4. **Запустить** `uv run python -m tests.test_smoke` и убедиться, что всё проходит.
5. При необходимости добавить новое поле в `OntMetrics` (в конец, `field(default=…)`) и обновить `DiagnosisReport.to_dict()`.

## Открытые задачи (TODO)
- Автоматическое обновление списка `bad_versions` из внешнего источника.
- Добавление поддержки TLS‑соединения к OLT (замена чистого Telnet).
- Расширение веб‑интерфейса: графики мониторинга в реальном времени.
- Интеграция с системами наблюдения (Prometheus, Grafana).

---
*Этот файл создаётся автоматически Qwen Code и служит единственным источником инструкций для будущих взаимодействий.*