# AGENTS.md

Инструкции для ИИ-агентов, работающих с кодовой базой GPON Diagnostic Framework.
Цель — параллельная работа нескольких агентов без поломки архитектуры и логики.

---

## 1. Жёсткие правила

### 1.1. НЕ ТРОГАТЬ без явного запроса пользователя

| Что | Почему |
|-----|--------|
| `core/models.py` → `OntMetrics` | Единый контракт данных для парсера, движка, отчёта. Добавление поля — только через `field(default=…)` в конец дата-класса. Удаление/переименование — **запрещены**, пока все потребители не обновлены. |
| `core/engine.py` → `DEFAULT_RULES`, `EXTENDED_RULES` | Порядок правил влияет на результат. Новое правило — только добавление в конец списка. Не менять порядок, не удалять существующие. |
| `core/olt.py` → `OltConnection`, `_olt_registry` | Singleton-реестр. Менять логику соединения — **только** при рефакторе с полным тестированием. Не добавлять параллельные соединения к одному OLT. |
| `core/parser.py` → `PATTERNS` | Регулярки парсят живой вывод Huawei CLI. Незначительное изменение regexp → тихая поломка парсинга. Любое изменение — тестировать с реальным выводом. |
| `diagnose.py` → `run_diagnosis()` | Основной конвейер. Порядок вызовов парсеров и действий (сброс ошибок, пинг) — часть протокола диагностики. Не менять без понимания последствий. |
| `.env`, `.gitignore`, `config.yaml` | Секреты и конфигурация деплоя. Не создавать новые `.env`-файлы, не расширять `.gitignore` на файлы, нужные другим агентам. |

### 1.2. Обязательные требования к коду

1. **Сортировка импортов**: stdlib → third-party → local (`core.*`). Пустая строка между группами.
2. **Типизация**: все публичные функции и методы — с аннотациями типов.
3. **Кодировка UTF-8**: все файлы — с заголовком `# -*- coding: utf-8 -*-` при наличии кириллицы (необязательно, если её нет).
4. **Логирование**: через `logging.getLogger(__name__)`, не через `print()` в библиотечном коде. `print` допустим только в CLI-entry (`diagnose.py:main()`).
5. **Исключения**: не глотать `except Exception: pass`. Минимум — `logger.warning()`. В правилах движка — оборачивать в try/except, логировать, возвращать `None` (см. `DiagnosticEngine.diagnose`).
6. **Строки-заглушки**: `"-"`, `""`, `-1`, `-999`, `999.0` — это sentinel-значения в `OntMetrics`. Проверять строго по существующей логике, не заменять на `None`/`0`.

### 1.3. Запрещённые действия

- **Косметический рефакторинг**: не переименовывать переменные, не менять стиль отступов, не добавлять type stubs «для порядка».
- **Удаление «мёртвого» кода** без ответа на вопрос: используется ли он в SecureCRT-ветке (`GPON_class.py`, `crt_stub.py`)?
- **Слияние/разделение файлов** в `core/` — текущая структура стабильно работает.
- **Добавление новых зависимостей** в `pyproject.toml` без согласования.
- **Коммит и пуш** без явного запроса пользователя.

---

## 2. Архитектура и зоны ответственности

```
diagnose.py          → CLI + оркестрация (входная точка)
├── core/olt.py      → Telnet-соединение с OLT (singleton-реестр)
├── core/parser.py   → CLI-вывод Huawei → OntMetrics
├── core/models.py   → Структуры данных (OntMetrics, LanPort, MacDevice)
├── core/engine.py   → Диагностический движок (правила)
├── core/thresholds.py → Пороги (dataclass из config.yaml)
├── core/report.py   → Модели DiagnosisProblem, DiagnosisReport + рендер to_text()/to_dict()
├── core/reporter.py → Сохранение отчётов в файл + file locking
├── core/crt_stub.py → Эмуляция SecureCRT API (для тестов)
├── core/adapter.py  → Адаптер SecureCRT ↔ core
├── core/collector.py → Обёртка для сбора данных
├── web/app.py       → Flask-веб-интерфейс
└── GPON_class.py    → Legacy SecureCRT-интеграция
```

### Правило版权归: один агент — одна зона

| Зона | Файлы | Что можно делать |
|------|-------|-------------------|
| **Парсер** | `core/parser.py` | Добавлять regex в `PATTERNS`, добавлять `parse_*` функции. Не менять существующие regex без теста на реальном выводе. |
| **Движок** | `core/engine.py` | Добавлять правила в конец `EXTENDED_RULES` (захват `DEFAULT_RULES` — только после согласования). Не менять сигнатуру `Rule.check(metrics, thresholds)`. |
| **Модель** | `core/models.py` | Добавлять поля в конец `OntMetrics` с дефолтом. Обновлять `to_dict()` в `report.py`. Не удалять и не переименовывать поля. |
| **Соединение** | `core/olt.py` | Добавлять методы в `OltConnection`. Не менять логику `_read_to_prompt`, `send_command`, `_gpon_ctx` без полного понимания telnet-протокола. |
| **Отчёт** | `core/report.py`, `core/reporter.py` | Расширять `to_text()` / `to_dict()`. Не удалять существующие секции отчёта. |
| **Веб** | `web/app.py`, `web/templates/*`, `web/static/*` | Свободная зона, но не ломать импорты из `core.*`. |
| **CLI** | `diagnose.py` | Добавлять аргументы, расширять `main()`. Не менять `run_diagnosis()` без знания протокола. |

---

## 3. Конвенции проекта

### 3.1. Язык

- **Диагностические сообщения** (rules, report): русский.
- **Код, комментарии, docstring**: английский, если не указано иное.
- **JSON-ключи** в `to_dict()`: английский snake_case.

### 3.2. Стиль

- Python ≥3.12, dataclasses, type hints.
- Максимальная длина строки: 120 символов.
- Отступы: 4 пробела.
- Строки: двойные кавычки для f-strings и текста, одинарные для ключей dict.
- f-strings优先, `%` и `.format()` — только при необходимости.

### 3.3. Телнет-протокол Huawei (ОСОБЕННОСТИ)

- `display ont optical-info` требует контекста `interface gpon F/S` → `_gpon_ctx()` / `_quit_gpon()`.
- Длинный вывод: прокрутка через `---- More ----`, обрабатывается в `send_command(max_more=...)`.
- `_parse_fsp()` аккумулирует F/S/P и ONT-ID построчно (key-value формат) — не менять без понимания.
- Расстояние: первично `ONT distance(m)`, fallback на `ONT last distance(m)` при значении `-`.
- Оптические параметры: `ont_rx_power`, `olt_rx_power`, `ont_tx_power`, `laser_bias_current`, `ont_temperature`, `supply_voltage`, `module_subtype` — брать ТОЛЬКО из `display ont optical-info`. **НЕ** использовать `catv_rx_power`.

### 3.4. Правила правил

- Правила для **offline** ONT — только `rule_offline` + `rule_match_state` / `rule_config_state`.
- Все остальные правила — только для **online** ONT (`if not metrics.is_online: return None`).
- Пороговые значения — из `Thresholds` (dataclass), не хардкодить.

### 3.5. Сентинел-значения OntMetrics

| Поле | Сентинел | Проверка |
|------|----------|----------|
| `ont_rx_power`, `olt_rx_power`, `ont_tx_power` | `999.0` / `>= 900` | `if metrics.ont_rx_power >= 900: skip` |
| `distance_m` | `-1` | `if metrics.distance_m < 0: skip` |
| `cpu_temp`, `ont_temperature` | `-999` / `<= -900` | `if metrics.cpu_temp < -900: skip` |
| `cpu_usage`, `memory_usage` | `-1` | `if metrics.cpu_usage < 0: skip` |
| `supply_voltage` | `-1.0` | `if metrics.supply_voltage < 0: skip` |
| `last_down_cause`, `online_duration` | `""` или `"-"` | `if not val or val == "-": skip` |

Не заменять эти проверки на `if not metrics.xxx` — сломается логика (0 — валидное значение для `distance_m=0`).

---

## 4. Процедура внесения изменений

### 4.1. Добавление нового правила диагностики

1. Написать функцию в `core/engine.py`:
```python
def rule_new_check(metrics: OntMetrics, t: Thresholds) -> DiagnosisProblem | None:
    """Short description."""
    if not metrics.is_online:   # <-- ОБЯЗАТЕЛЬНО для онлайн-правил
        return None
    if condition:
        return DiagnosisProblem("warning", "category", "Описание (рус)", "Рекомендация (рус)")
    return None
```
2. Добавить в **конец** `EXTENDED_RULES`:
```python
EXTENDED_RULES = DEFAULT_RULES + [..., Rule("new_check", rule_new_check, "category")]
```
3. Запустить `uv run python -m tests.test_smoke` — убедиться, что существующие тесты проходят.
4. Если правило требует нового поля — см. §4.3.

### 4.2. Добавление нового парсера

1. Добавить regex в `PATTERNS` в `core/parser.py`.
2. Написать `def parse_new_data(raw: str, m: OntMetrics) -> None:`.
3. Добавить вызов в `diagnose.py:run_diagnosis()` после сбора сырых данных.
4. Обновить `DiagnosisReport.to_dict()` в `core/report.py`, если поле новое.

### 4.3. Добавление нового поля в OntMetrics

1. Добавить поле **в конец** `OntMetrics` с `field(default=…)`:
```python
new_field: str = ""
```
2. Заполнить в соответствующем парсере.
3. Добавить в `DiagnosisReport.to_dict()` в `core/report.py`.
4. Добавить в `DiagnosisReport.to_text()` при необходимости.
5. Проверить:烟雾-test (`uv run python -m tests.test_smoke`) — поля с дефолтом не ломают существующие вызовы.

### 4.4. Изменение порогов

1. Добавить поле в `Thresholds` (core/thresholds.py) с дефолтом.
2. Добавить маппинг в `diagnose.py:main()` → `Thresholds(...)`.
3. Добавить ключ в `config.yaml` с комментарием.

---

## 5. Тестирование

```bash
# Smoke-тест (без подключения к OLT)
uv run python -m tests.test_smoke

# Запуск диагностики (требует доступ к OLT)
uv run diagnose.py 0/1/3/9 --olt "OLT-40.111"

# Без побочных действий (без сброса ошибок и портов)
uv run diagnose.py 0/1/3/9 --no-actions

# JSON-вывод
uv run diagnose.py 0/1/3/9 --json --no-save
```

**Обязательное условие**: после любых изменений в `core/` запустить `uv run python -m tests.test_smoke`. Тесты должны проходить до и после изменений.

---

## 6. Координация между агентами

### 6.1. Файловые блокировки

Проект использует `hermes-lockutils/` для потокобезопасной записи отчётов. Если агент добавляет файловые операции:
1. Импортировать `lock_file` / `unlock_file` через `_get_lock_functions()` (см. `core/reporter.py`).
2. Обязательно `try/finally` для освобождения锁.
3. Не использовать NFS-пути для блокировок.

### 6.2. Конфликты при параллельной работе

| Ситуация | Решение |
|----------|---------|
| Два агента меняют один файл | Каждый работает в своей зоне (§2). Если зоны пересеклись — один агент, затем другой. Не пытаться объединять автоматически. |
| Оба добавляют правило в `engine.py` | Добавлять строго в конец `EXTENDED_RULES`. Если Git-конфликт —右手 (latest addition) побеждает, дубликатов имён правил не допускать. |
| Оба добавляют поле в `models.py` | Добавлять строго в конец дата-класса. Конфликт слияния решать ручным порядком полей. |
| Оба меняют `parser.py PATTERNS` | Ключи в `PATTERNS` уникальны. Новые ключи — в конец словаря. Не переименовывать чужие ключи. |

### 6.3. Коммуникация через Git

- Каждый агент делает изменения в отдельной ветке: `agent/<имя-агента>/<тема>`.
- Перед merge — убедиться, что `uv run python -m tests.test_smoke` проходит.
- Commit-сообщения: префикс имени агента, например `[claude] add rule_high_memory`, `[codex] fix parser regex`.

---

## 7. Структура файлов (что где лежит)

```
gpon-diag/
├── diagnose.py            # CLI-entry, оркестрация
├── config.yaml            # OLT list + thresholds + settings
├── .env                   # Credentials (НЕ коммитить!)
├── pyproject.toml         # Зависимости, metadata
├── core/
│   ├── models.py          # OntMetrics, LanPort, MacDevice
│   ├── parser.py          # PATTERNS + parse_* функции
│   ├── engine.py          # DiagnosticEngine, Rule, DEFAULT/EXTENDED_RULES
│   ├── thresholds.py      # Thresholds dataclass
│   ├── report.py          # DiagnosisProblem, DiagnosisReport, BAD_VERSIONS
│   ├── reporter.py        # save_text_report(), file locking
│   ├── olt.py             # OltConnection, singleton-registry
│   ├── adapter.py         # SecureCRT adapter
│   ├── collector.py       # Data collection wrapper
│   └── crt_stub.py        # SecureCRT API emulation (tests)
├── web/
│   ├── app.py             # Flask web interface
│   ├── templates/         # Jinja2 templates
│   └── static/            # CSS, JS
├── GPON_class.py          # Legacy SecureCRT integration
├── data/
│   ├── oui.txt            # MAC vendor database
│   └── reports/           # Saved reports (gitignored)
├── tests/
│   └── test_smoke.py      # Smoke tests
├── scripts/               # Utility scripts
├── hermes-lockutils/      # File locking utilities
└── securecrt_adapter.py   # SecureCRT bridge
```

---

## 8. Переменные окружения

Credentials загружаются через `python-dotenv` из `.env` или системных env:

**Не создавать новые `.env`-переменные** без явного запроса. Не коммитить `.env`.

---

## 9. Типичные ошибки и их предотвращение

| Ошибка | Как избежать |
|--------|-------------|
| Добавили `if not metrics.ont_rx_power` вместо `>= 900` | Использовать таблицу сентинелов (§3.5). `0.0` — валидное значение мощности. |
| Изменили regex в `PATTERNS` → парсер перестал находить | Тестировать с реальным выводом `display ont ...`. Добавить пример вывода в docstring теста. |
| Добавили правило без `if not metrics.is_online: return None` | Все правила кроме `rule_offline` / `rule_match_state` / `rule_config_state` должны это проверять. |
| Вызвали `display ont optical-info` без `interface gpon` | Оптические данные собираются ТОЛЬКО через `_gpon_ctx()` → `send_command()` → `_quit_gpon()`. |
| Добавили поле без default в OntMetrics | Все поля OntMetrics должны иметь default — дата-класс мутируется парсерами поштучно. |
| Удалили «мёртвый» код из `crt_stub.py` | Используется `GPON_class.py` через `inject_crt()`. Не трогать без знания SecureCRT-ветки. |
| Использовали `catv_rx_power` | Поля `catv_rx_power` нет в OntMetrics. Оптические данные — только из `display ont optical-info`. |
| Хардкод порогов в правилах | Пороги — через параметр `t: Thresholds`. Числа — только дефолты в `Thresholds` dataclass. |
