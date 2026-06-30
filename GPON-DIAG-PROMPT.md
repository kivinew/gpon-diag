# GPON Diagnostic Framework — Промпт для ИИ-агентов

Ты работаешь с проектом **gpon-diag** — фреймворком автоматизированной диагностики GPON-сети на базе Huawei MA5608T.

**Расположение:** `/mnt/e/DOWNLOADS/CREATIVE/PYTHON/GitHub/gpon-diag/`
**Python:** 3.12+, менеджер `uv`
**Виртуальное окружение:** `/home/kivinew/gpon-diag-venv/` (WSL-native, опционально)
**Транспорт:** синхронный socket TCP (telnet) с IAC stripping

---

## 1. Задача фреймворка

Автоматизация диагностики инцидентов на GPON-сети: подключение к OLT по telnet, сбор параметров ONT, сбор данных о состоянии всех ont на GPON-порту, анализ через rule-based движок, генерация отчётов.

Типовые инциденты: ONT offline, низкий Rx/Tx, высокий BER (BIP errors), flapping, потеря регистрации, перегрев.

---

## 2. Архитектура (модули)

```
diagnose.py          ← CLI entry (argparse), оркестрация вызовов
config.yaml          ← 22 OLT + пороги + настройки
core/olt.py          ← Менеджер telnet-подключений (socket, circuit breaker)
core/parser.py       ← Парсинг вывода Huawei CLI → OntMetrics (20+ regex)
core/models.py       ← OntMetrics, LanPort, MacDevice (dataclass)
core/engine.py       ← Rule-based движок (21 правило: 13 default + 8 extended)
core/thresholds.py   ← Пороговые значения (dataclass)
core/report.py       ← DiagnosisProblem, DiagnosisReport → to_text()/to_dict()
core/reporter.py     ← Сохранение отчётов (text/JSON) с файловой блокировкой
core/collector.py    ← Re-export OltConnection (legacy, не трогать)
core/adapter.py      ← Адаптер SecureCRT ↔ core (legacy, не трогать)
core/crt_stub.py     ← Эмуляция SecureCRT API (legacy, не трогать — используется GPON_class.py)
core/loop_runner.py  ← Циклический запуск диагностики
web/app.py           ← Flask + SSE (real-time логи, SQLite)
orchestrator/        ← Модуль оркестрации AI-агентов
tests/test_smoke.py  ← Smoke-тесты (без OLT)
hermes-lockutils/    ← Файловая блокировка (atomic mkdir)
AGENTS.md            ← Контракт для мультиагентной разработки
```

### Зоны ответственности (один агент — одна зона)

| Зона | Файлы | Что можно |
|------|-------|-----------|
| Парсер | `core/parser.py` | Добавлять regex в `PATTERNS`, `parse_*` функции |
| Движок | `core/engine.py` | Добавлять правила в **конец** `EXTENDED_RULES` |
| Модель | `core/models.py` | Добавлять поля в **конец** `OntMetrics` с `field(default=…)` |
| Соединение | `core/olt.py` | Добавлять методы. Не менять `_read_to_prompt`, `send_command`, `_gpon_ctx` |
| Отчёт | `core/report.py`, `core/reporter.py` | Расширять `to_text()` / `to_dict()`. Не удалять секции. |
| Веб | `web/app.py`, `web/templates/*` | Свободная зона, не ломать импорты из `core.*` |
| CLI | `diagnose.py` | Добавлять аргументы. Не менять `run_diagnosis()` |

---

## 3. Поток диагностики

```
1. CLI → parse_input(input_str) → F/S/P/ONT, SN или description
2. Поиск ONT на OLT:
   - по F/S/P/ONT: прямой адрес
   - по SN: display ont info by-sn <sn> (max_more=-1)
   - по description: display ont info by-desc <desc> (max_more=-1)
   - --auto-search: параллельно по всем OLT (ThreadPoolExecutor, 8 workers)
3. OltConnection.connect() → enable → config → interface gpon
4. Сбор данных:
   - display ont info F S P ID
   - display ont version F S P ID
   - display ont optical-info P ID (в контексте interface gpon F/S)
   - display statistics ont-line-quality F S P ID
   - display ont port state F S P ID eth-port all
   - display statistics ont-eth F S P ID ont-port 1..4
   - display mac-address ont F/S/P ID
   - display ont wan-info F S P ID
   - ping 1.1.1.1 (с ONT, не для модели 310)
5. Парсинг → OntMetrics
6. engine.diagnose() → список DiagnosisProblem
7. DiagnosisReport → to_text() / to_dict()
8. save_text_report() / save_report() → data/reports/
```

---

## 4. OLT Connection (core/olt.py)

### Важные детали:

- **Синхронный socket**, не telnetlib3 (хотя telnetlib3 указан в pyproject.toml)
- **IAC stripping**: функция `_strip_iac()` — удаляет telnet escape-последовательности
- **Circuit breaker**: `_skip_disconnect=True` после 2 неудачных попыток. При включении — соединение не переподключается
- **Idle timeout**: 120 сек → auto-disconnect
- **Пул**: макс 2 соединения на OLT (`_MAX_CONNECTIONS_PER_OLT = 2`)
- **Scroll**: `max_more=-1` читает все страницы, `max_more=0` прерывает

### Telnet-рукопожатие:
```python
sock → read banner → send username → read → send password → read → send "enable" → send "config" → готово
```
При подключении OLT может слать `IAC DO ECHO` / `IAC DO SUPPRESS GO AHEAD`. Если не обработать — разрыв соединения при длинных командах.

### Critical методы (НЕ МЕНЯТЬ без понимания):
- `_read_to_prompt()` — читает до появления промпта `MA5608T>` / `MA5608T#` / `MA5608T (Config)#`
- `send_command(command, max_more=0)` — отправляет команду, читает ответ, обрабатывает `---- More ----`
- `_gpon_ctx(frame, slot)` — входит в `interface gpon F/S`

---

## 5. Парсер (core/parser.py)

20+ паттернов в словаре `PATTERNS`. Ключевые:

| Паттерн | Что парсит |
|---------|------------|
| `status` | `Run state: online/offline` |
| `serial` | `SN: 48575443XXXXXXXX` |
| `description` | `Description: fl_XXXXX` |
| `distance` / `distance_last` | `ONT distance(m): 1234` |
| `downcause` | `Last down cause: dying-gasp` |
| `ont_rx_power` | `Rx optical power(dBm): -19.5` |
| `olt_rx_power` | `OLT Rx ONT optical power(dBm): -22.3` |
| `ont_tx_power` | `Tx optical power(dBm): 2.1` |
| `laser_bias` | `Laser bias current(mA): 12` |
| `ont_temperature` | `Temperature(C): 45` |
| `supply_voltage` | `Voltage(V): 3.3` |
| `module_subtype` | `Module sub-type: SFP` |
| `upstream_errors` | `Upstream frame BIP error count: 0` |
| `downstream_errors` | `Downstream frame BIP error count: 0` |
| `lan_ports` | `1 1 GE 100 full up` |
| `mac_entry` | `1 1234-ABCD-5678` |
| `register_downtime` | `DownTime: 2026-06-01 12:00:00+07` |

**Правила парсинга:**
- `strip_ansi()` — удалить ANSI escape-последовательности перед парсингом
- `_search(text, pattern)` — возвращает `group(1)` или `None`
- `_search_int()` / `_search_float()` — с дефолтами `0` / `999.0`
- **Расстояние:** сначала `ONT distance(m)`, если `-` → fallback на `ONT last distance(m)`
- **catv_rx_power НЕ ИСПОЛЬЗОВАТЬ** — поля нет в OntMetrics

### `_parse_fsp()` (многострочный):
Аккумулирует F/S/P и ONT-ID построчно, т.к. Huawei выводит их в key-value формате на разных строках. Не переписывать на однострочный подход.

---

## 6. Модели (core/models.py)

### OntMetrics (ключевые поля)
Все поля с sentinel-дефолтами. Новые поля — только в конец с `field(default=…)`:

| Поле | Sentinel | Тип |
|------|----------|-----|
| `ont_rx_power`, `olt_rx_power`, `ont_tx_power` | `999.0` | float |
| `distance_m` | `-1` | int |
| `cpu_temp`, `ont_temperature` | `-999` | int |
| `cpu_usage`, `memory_usage` | `-1` | int |
| `supply_voltage` | `-1.0` | float |
| `laser_bias_current` | `-1` | int |
| `last_down_cause`, `online_duration` | `""` | str |

**ВАЖНО:** Проверять sentinel-ы через `>= 900`, `< 0`, `<= -900`, `not val or val == "-"`. НЕ через `if not metrics.xxx` (0 — валидное значение для distance_m=0).

---

## 7. Движок диагностики (core/engine.py)

### 21 правило (13 default + 8 extended):

```
DEFAULT_RULES:
  offline        → offline, dying-gasp, LOS, wire-down, LOKI
  low_ont_rx     → Rx < warn/crit
  low_olt_rx     → OLT Rx < warn/crit
  low_tx_power   → Tx < 0 dBm (crit) / < 1 dBm (warn)
  bip_errors     → BIP > 10K (warn) / > 100K (crit)
  bad_firmware   → version в bad_versions[]
  no_lan         → нет active LAN ports
  overheating    → cpu_temp > 75°C (warn) / > 90°C (crit)
  ont_temperature → ont_temperature > 65°C (warn) / > 75°C (crit)
  long_distance  → distance > 19km (warn) / > 20km (crit)
  config_state   → config_state != normal
  wan_disconnected → WAN status = disconnected/failed
  lan_no_link    → все LAN down
  high_cpu       → cpu > 90%
  high_memory    → mem > 85%
  no_description → description = ONT_NO_DESCRIPTION
  frequent_falls → 2+ falls за 1 час
  eth_port_errors → FCS/RX bad/TX bad > 0
  long_uptime    → online > 5 days
```

### Правила для правил:
- **Offline правила:** только `rule_offline` и `rule_config_state`
- **Online правила:** все остальные — с guard `if not metrics.is_online: return None`
- Пороги — из `Thresholds`, не хардкодить
- Новые правила — только в **конец** `EXTENDED_RULES`
- Порядок правил влияет на результат сортировки проблем

### Формат правила:
```python
def rule_new(metrics: OntMetrics, t: Thresholds) -> Optional[DiagnosisProblem]:
    if not metrics.is_online:
        return None
    if condition:
        return DiagnosisProblem(
            severity="critical|warning|info",
            category="optic|hardware|ethernet|wan|firmware|config|accounting|stability|maintenance",
            description="Описание (русский)",
            recommendation="Рекомендация (русский)"
        )
    return None
```

---

## 8. CLI (diagnose.py)

### Аргументы:
```
positional:  input (F/S/P/ONT, SN, или description)
--olt       имя или IP (из config.yaml)
--auto-search  поиск по всем OLT параллельно
--json      вывод в JSON
--no-save   не сохранять файл отчёта
--no-actions  без сброса ошибок и перезагрузки портов (безопасный режим)
--only-optics  только оптика (Rx/Tx, BIP), без LAN/WAN
--clipboard   копировать в буфер обмена
```

### Команды:
```bash
uv run diagnose.py 0/1/3/9 --olt "пос.Пионер"
uv run diagnose.py 4857544312E0E379 --auto-search
uv run diagnose.py fl_105222 --olt "пос.Звёздный"
uv run diagnose.py 0/1/3/9 --json --no-save --no-actions
uv run diagnose.py 0/1/3/9 --only-optics
```

---

## 9. Smoke-тесты

Без подключения к OLT:
```bash
uv run python -m tests.test_smoke
```

Используют семплы CLI-вывода Huawei (зашиты в тестах). Покрытие: offline (dying-gasp), online healthy, low Rx + BIP errors.

При изменении `core/` — **обязательно** запустить smoke-тесты.

---

## 10. Конфигурация

### config.yaml
```yaml
olts:
  - name: "пос.Пионер"
    host: "172.16.37.252"
    port: 23
    credential_key: "RADIUS"

thresholds:
  ont_rx_power_warn: -26.5
  ont_rx_power_crit: -30.0
  bip_error_warn: 10000
  bip_error_crit: 100000
  # ... полный список в core/thresholds.py

bad_versions:
  - "V1R003C00S108"
  - "V1R006C00S130"

no_ping_models:
  - "310"
```

### .env (креды — НЕ КОММИТИТЬ)
```
GPON_OLT_RADIUS_USERNAME=admin
GPON_OLT_RADIUS_PASSWORD=password
```

Загрузка: python-dotenv → `os.environ`. Формат ключа: `GPON_OLT_<CREDENTIAL_KEY>_USERNAME` / `_PASSWORD`.

---

## 11. Жёсткие правила (НЕ НАРУШАТЬ)

1. **Не удалять код из `crt_stub.py`** — используется `GPON_class.py` через `inject_crt()`
2. **Не менять порядок `DEFAULT_RULES` / `EXTENDED_RULES`** — влияет на результат диагностики
3. **Не удалять/переименовывать поля `OntMetrics`** — все потребители сломаются
4. **Не хардкодить пороги** — через параметр `t: Thresholds`
5. **Не добавлять `catv_rx_power` в optical-info** — поля нет в модели
6. **Online/offline ONTs разделять** — правила для online проверяют `metrics.is_online`
7. **Sentinel-значения не заменять на `None`/`0`** — 0 валидное значение
8. **Не коммитить и не пушить** без явного запроса пользователя
9. **Не добавлять новые зависимости** в pyproject.toml без согласования
10. **Не делать косметический рефакторинг** — не переименовывать, не менять отступы, не удалять "мёртвый" код

---

## 12. Типичные ошибки и pitfalls

| Ошибка | Как избежать |
|--------|-------------|
| `if not metrics.ont_rx_power:` вместо `>= 900` | См. таблицу sentinel-ов (§6) |
| Парсинг distance из `-` как 0 | Проверить: если `-`, брать `last_distance`, если тоже `-` → sentinel -1 |
| Забыл `interface gpon` перед optical-info | Использовать `_gpon_ctx()` / `_quit_gpon()` |
| Broken pipe / reconnect loop | В `_write` при ошибке — `logger.warning`, не `logger.error`, проверять `_connected` |
| Поиск ONT находит только 1-ю страницу | `max_more=-1` во всех `find_ont_by_*` |
| .venv на /mnt/e ломается под WSL | Создавать venv в `/home/` (WSL-native FS) |

---

## 13. Полезные ссылки

- **AGENTS.md** — мультиагентный контракт (зоны, процедуры, координация)
- **core/engine.py** — правила диагностики
- **core/models.py** — OntMetrics полный список полей
- **tests/test_smoke.py** — smoke-тесты (примеры вывода Huawei)
- **data/reports/** — 200+ реальных отчётов для анализа
- **config.yaml** — все OLT и пороги
