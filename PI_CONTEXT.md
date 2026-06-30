# GPON Diagnostic Framework — AI Context

## 📋 Описание проекта

**GPON Diagnostic Framework** — это система диагностики GPON сетей Huawei OLT через Telnet. Подключается к OLT, собирает метрики ONT и применяет 21 правило диагностики.

**Включает MCP сервер** для интеграции с AI-ассистентами.

## 🏗️ Архитектура

```
diagnose.py              → CLI entry point + orchestration
├── core/
│   ├── models.py        → OntMetrics, LanPort, MacDevice
│   ├── parser.py        → Huawei CLI → OntMetrics (регулярки)
│   ├── engine.py        → Diagnostic rules (DEFAULT_RULES + EXTENDED_RULES)
│   ├── thresholds.py    → Пороги (dataclass)
│   ├── report.py        → DiagnosisProblem, DiagnosisReport
│   ├── reporter.py      → Сохранение отчётов + file locking
│   ├── olt.py           → Singleton telnet connection pool
│   └── crt_stub.py      → Эмуляция SecureCRT
├── web/app.py           → Flask + SSE
├── config.yaml          → OLT, thresholds, settings
└── tests/test_smoke.py  → Smoke тесты
```

## 🔧 Компоненты

| Компонент | Назначение | Важные детали |
|-----------|------------|---------------|
| **OntMetrics** | Контейнер данных ONT | 50+ полей, sentinel значения (`-1`, `999.0`) |
| **DiagnosticEngine** | Движок правил | 21 правило, сортировка по severity |
| **OltConnection** | Telnet к Huawei | Singleton pool (максимум 2 на хост), `_gpon_ctx()` |
| **PATTERNS** | Регулярки | Парсят реальный вывод `display ont` |

## 📊 Диагностические правила (21 штука)

**DEFAULT_RULES (13):** `offline`, `low_ont_rx`, `low_olt_rx`, `low_tx_power`, `bip_errors`, `bad_firmware`, `no_lan`, `overheating`, `ont_temperature`, `long_distance`, `config_state`

**EXTENDED_RULES (8):** `wan_disconnected`, `lan_no_link`, `high_cpu`, `high_memory`, `no_description`, `frequent_falls`, `eth_port_errors`, `long_uptime`

## ⚠️ Строгие ограничения (AGENTS.md)

| Файл | Ограничение |
|------|-------------|
| `core/models.py` | Только ДОБАВЛЯТЬ поля в КОНЕЦ с `field(default=...)` |
| `core/engine.py` | Только ДОБАВЛЯТЬ правила в КОНЕЦ `EXTENDED_RULES` |
| `core/olt.py` | Не менять `_read_to_prompt`, `_gpon_ctx()` без полного тестирования |
| `core/parser.py` | Regex требуют тестирования на реальном выводе |
| `diagnose.py` | Не менять порядок вызовов в `run_diagnosis()` |

## 🎯 Sentinel значения (НЕ заменять на `None`/`0`)

| Поле | Sentinel | Проверка |
|------|----------|----------|
| `ont_rx_power` | `999.0` / `>= 900` | `if metrics.ont_rx_power >= 900: skip` |
| `distance_m` | `-1` | `if metrics.distance_m < 0: skip` |
| `cpu_temp` | `-999` / `<= -900` | `if metrics.cpu_temp < -900: skip` |
| `cpu_usage` | `-1` | `if metrics.cpu_usage < 0: skip` |
| `supply_voltage` | `-1.0` | `if metrics.supply_voltage < 0: skip` |
| Строки | `""` или `"-"` | `if not val or val == "-": skip` |

## 🚀 Использование

```bash
# Установка
uv sync

# Диагностика
uv run diagnose.py 0/1/3/9 --olt "OLT-40.111"
uv run diagnose.py 4857544312E0E379 --json --clipboard
uv run diagnose.py 0/1/3/9 --no-actions  # без сброса

# Тесты
uv run python -m tests.test_smoke

# Веб-интерфейс
uv run python -m web.app
```

## 🔐 Безопасность

- Учётные данные: `GPON_OLT_<NAME>_USERNAME` / `GPON_OLT_<NAME>_PASSWORD`
- `.env` и `config.yaml` не коммиться
- Telnet не шифруется — использовать management VLAN

## 📝 Конвенции кода

- Python ≥3.12, dataclasses, type hints
- Максимальная длина строки: 120 символов
- Отступы: 4 пробела
- Импорты: stdlib → third-party → local
- Логирование через `logging.getLogger(__name__)`
- Диагностические сообщения на русском

## 🗂️ Структура файлов

```
gpon-diag/
├── diagnose.py            # CLI entry
├── config.yaml            # OLT + thresholds
├── core/
│   ├── models.py          # OntMetrics
│   ├── parser.py          # PATTERNS + parse_*
│   ├── engine.py          # Rule engine
│   ├── thresholds.py      # Thresholds dataclass
│   ├── report.py          # DiagnosisProblem, DiagnosisReport
│   ├── reporter.py        # save_text_report()
│   ├── olt.py             # OltConnection
│   └── crt_stub.py        # SecureCRT stub
├── web/
│   ├── app.py             # Flask
│   ├── templates/
│   └── static/
├── data/
│   └── reports/           # Сохранённые отчёты
├── tests/
│   └── test_smoke.py
├── mcp_server.py          # MCP сервер для AI
└── hermes-lockutils/      # File locking
```

## MCP Сервер

**Файл:** `mcp_server.py`

**Инструменты:**
- `diagnose` — полная диагностика ONT
- `search_ont` — поиск по SN/описанию
- `get_optical` — оптические параметры
- `get_line_quality` — BIP ошибки
- `get_lan_ports` — LAN порты
- `ont_ping` — удалённый ping
- `reset_lan_port` — сброс порта
- `clear_ont_errors` — очистка ошибок
- `get_port_summary` — свод по порту
- `list_olts` — список OLT
- `reset_connections` — сброс соединений

**Запуск:** `uv run python mcp_server.py`