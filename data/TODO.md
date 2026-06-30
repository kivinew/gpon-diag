# TODO.md — Анализ оптимизаций GPON Diagnostic Framework

## Потенциальные проблемы

### 1. Производительность
- **Параллельные запросы к OLT**: `collect_ont()` в `core/olt.py` — синхронные запросы (5-8 секунд на ONT). Нужно: async/parallel для массовой диагностики портов.
- **Пул соединений**: `_MAX_CONNECTIONS_PER_OLT = 2` — мало для нагруженных OLT. Увеличить до 5-10.
- **Блокировки файлов**: `hermes-lockutils/file_lock.py` использует `mkdir` — может блокировать NFS-среды.

### 2. Надёжность
- **Telnet без шифрования**: Уязвимость в трафике. Перейти на SSH (Huawei MA5600 поддерживает).
- **Hardcoded timeout'ы**: `time.sleep(1)`, `time.sleep(2)` — костыли. Нужно: настраиваемые таймауты в config.yaml.
- **Повторное подключение**: При падении соединения нет автоматического реконнекта в `run_diagnosis()`.

### 3. Масштабируемость
- **SQLite на диске**: `web/app.py` — `diagnoses.db` в `data/`. При 100+ одновременных запросов будет contention.
- **Отчёты в памяти**: Каждый `DiagnosisReport` держит всё в памяти. Для большого числа ONT — OOM.
- **Однопоточность**: `ThreadPoolExecutor` в `diagnose.py` — ограничение 8 OLT одновременно.

## Варианты оптимизации

### Краткосрочные (1-2 недели)
- [ ] **async/await в core/olt.py**: Заменить `socket` на `asyncio` + `telnetlib3` async mode.
- [ ] **Настраиваемые таймауты**: Вынести все `time.sleep()` в `config.yaml` (connect_delay, command_delay).
- [ ] **Retry-логика**: Добавить экспоненциальный backoff в `connect()` при неудачах.

### Среднесрочные (1-2 месяца)
- [ ] **SSH-режим**: Альтернативная реализация `OltConnection` через paramiko/asyncssh.
- [ ] **Batch API**: endpoint `/api/diagnose/batch` для 10-50 ONT за один запрос.
- [ ] **Redis cache**: Кеширование результатов диагностики на 30 секунд.
- [ ] **Connection health check**: ping перед каждым `send_command()`.

### Долгосрочные (3-6 месяцев)
- [ ] **PostgreSQL**: Замена SQLite на PostgreSQL (async SQLAlchemy).
- [ ] **Message queue**: Redis/RabbitMQ для фоновых задач (очередь диагностики).
- [ ] **Prometheus metrics**: Экспорт метрик (latency, error_rate, olt_uptime).
- [ ] **Multi-region OLT**: Репликация конфигурации между дата-центрами.

## Оптимизации CPU/памяти

| Задача | Текущее | Цель | Приоритет |
|--------|---------|------|-----------|
| Парсинг regex | 66 паттернов в `PATTERNS` | компилировать один раз | 🔥 Высокий |
| MAC-БД | загружается каждый раз в `parse_mac_addresses()` | singleton cache | 🔥 Высокий |
| ANSI-очистка | `strip_ansi()` вызывается 10+ раз | один вызов на output | 🔥 Высокий |
| JSON-сериализация | `ensure_ascii=False` каждый раз | pre-encoded | Средний |

## Риски изменений

### core/olt.py — Критично
- Любое изменение `_read_to_prompt()` → возможен блокинг соединений
- Изменение протокола telnet → падение на всех OLT

### core/parser.py — Средне
- Изменение regex PATTERNS → потеря парсинга реального вывода
- Нужно тестировать с актуальным выводом Huawei CLI

### web/app.py — Низко
- Добавление endpoints не ломает бизнес-логику
- Можно безопасно расширять API

## Метрики для мониторинга

1. **Diag time**: среднее время на ONT (сейчас 5-8 сек)
2. **Error rate**: % неудачных подключений
3. **OLT availability**: uptime через ping
4. **Memory usage**: RSS процесса (сейчас ~50MB)