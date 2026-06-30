# SQL Pro — Возможности использования базы данных в gpon-diag

## 1. Текущее состояние

### 1.1. Что есть сейчас

| Хранилище | Расположение | Содержимое | Проблемы |
|-----------|--------------|------------|----------|
| SQLite `diagnoses.db` | `data/diagnoses.db` | `Diagnosis` (JSON-блоб), `PortSnapshot` | JSON-бLOB = невозможно запросить конкретные поля |
| Flat-файлы | `data/reports/*.txt|json` | Текстовые/JSON-отчёты | Дублируют БД, нет единого интерфейса запросов |
| Flat-файл | `data/oui.txt` | База MAC-вендоров | Read-only, пока норм |
| YAML | `config.yaml` | Список OLT, пороги | Не транзакционна, нет истории изменений |

### 1.2. Боли
- **Отчёты как JSON-блобы**: Нельзя выполнить запрос "показать все ONT с Rx < -30 dBm за прошлую неделю"
- **Нет временных рядов**: Нельзя отследить деградацию оптической мощности
- **Нет инвентаря**: Метаданные OLT/ONT в YAML, не в реляционной модели
- **Нет аудита**: Кто запускал диагностику, когда, какие действия выполнял?
- **Дублирование хранения**: БД + flat-файлы = риск рассогласования

---

## 2. Предлагаемая схема БД

### 2.1. Нормализованная схема (вместо JSON-блоба)

```sql
-- Структурированные отчёты вместо JSON-блоба
CREATE TABLE diagnosis_reports (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,  -- ISO8601
    olt_name        TEXT NOT NULL,
    olt_host        TEXT NOT NULL,
    ont_address     TEXT NOT NULL,  -- F/S/P/ONT
    ont_serial      TEXT,
    description     TEXT,           -- лицевой счёт
    model           TEXT,
    version         TEXT,
    distance_m      INTEGER,
    is_online       BOOLEAN,
    status          TEXT,
    
    -- Оптика (nullable, sentinel-safe)
    ont_rx_power    REAL,           -- 999.0 = unknown
    olt_rx_power    REAL,
    ont_tx_power    REAL,
    laser_bias      INTEGER,
    ont_temperature INTEGER,        -- -999 = unknown
    supply_voltage  REAL,
    
    -- Ошибки
    upstream_errors    INTEGER DEFAULT 0,
    downstream_errors  INTEGER DEFAULT 0,
    
    -- Система
    cpu_usage       INTEGER,        -- -1 = unknown
    memory_usage    INTEGER,
    cpu_temp        INTEGER,
    online_duration TEXT,
    last_down_cause TEXT,
    last_up_time    TEXT,
    last_down_time  TEXT,
    last_dying_gasp TEXT,
    
    -- Мета
    ping_status     TEXT,
    ping_target     TEXT DEFAULT '1.1.1.1',
    match_state     TEXT,
    config_state    TEXT,
    
    created_at      TEXT DEFAULT (datetime('now'))
);

-- Снапшоты оптики для трендинга (сохраняются при каждой диагностике)
CREATE TABLE optics_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id       INTEGER NOT NULL REFERENCES diagnosis_reports(id) ON DELETE CASCADE,
    ont_rx_power    REAL,
    olt_rx_power    REAL,
    ont_tx_power    REAL,
    ont_temperature INTEGER,
    supply_voltage  REAL,
    upstream_errors   INTEGER DEFAULT 0,
    downstream_errors INTEGER DEFAULT 0,
    sampled_at      TEXT DEFAULT (datetime('now'))
);

-- Лог срабатываний правил (вместо вложенного JSON)
CREATE TABLE rule_firings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id       INTEGER NOT NULL REFERENCES diagnosis_reports(id) ON DELETE CASCADE,
    rule_name       TEXT NOT NULL,
    severity        TEXT NOT NULL CHECK(severity IN ('critical', 'warning', 'info')),
    category        TEXT NOT NULL,
    description     TEXT NOT NULL,
    recommendation  TEXT NOT NULL
);

-- MAC-устройства (сейчас теряются после отчёта)
CREATE TABLE mac_devices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id       INTEGER NOT NULL REFERENCES diagnosis_reports(id) ON DELETE CASCADE,
    port_type       TEXT,  -- ETH/WLAN
    port_number     TEXT,
    mac_address     TEXT NOT NULL,
    vendor          TEXT
);

-- История состояний LAN-портов (для детекции флапов)
CREATE TABLE lan_port_states (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id       INTEGER NOT NULL REFERENCES diagnosis_reports(id) ON DELETE CASCADE,
    lan_id          TEXT NOT NULL,
    port_type       TEXT,
    speed           TEXT,
    duplex          TEXT,
    link_state      TEXT NOT NULL,
    fcs_errors      INTEGER DEFAULT 0,
    rx_bad_bytes    INTEGER DEFAULT 0,
    tx_bad_bytes    INTEGER DEFAULT 0
);

-- Инвентарь OLT (вместо YAML)
CREATE TABLE olts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    host            TEXT NOT NULL UNIQUE,
    port            INTEGER DEFAULT 23,
    credential_key  TEXT DEFAULT 'RADIUS',
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- Реестр ONT (master data, discovered during diagnosis)
CREATE TABLE onts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    olt_id          INTEGER NOT NULL REFERENCES olts(id),
    ont_address     TEXT NOT NULL,  -- F/S/P/ONT
    serial          TEXT,
    description     TEXT,
    model           TEXT,
    version         TEXT,
    frame           TEXT,
    slot            TEXT,
    port            TEXT,
    ont_id          TEXT,
    first_seen      TEXT DEFAULT (datetime('now')),
    last_seen       TEXT DEFAULT (datetime('now')),
    UNIQUE(olt_id, ont_address)
);

-- История конфигурации (thresholds, rules)
CREATE TABLE config_versions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    config_type     TEXT NOT NULL CHECK(config_type IN ('thresholds', 'rules', 'bad_versions')),
    config_yaml     TEXT NOT NULL,
    applied_at      TEXT DEFAULT (datetime('now')),
    applied_by      TEXT  -- operator name / agent id
);

-- Аудит действий (compliance)
CREATE TABLE audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT DEFAULT (datetime('now')),
    agent_id        TEXT,  -- cline/qwen/claude or operator
    action          TEXT NOT NULL,  -- diagnose, clear_errors, reset_port
    ont_address     TEXT,
    olt_host        TEXT,
    parameters      TEXT,  -- JSON
    result          TEXT,  -- success/error
    duration_ms     INTEGER
);
```

### 2.2. Покрывающие индексы для частых запросов

```sql
-- Последние диагностики по ONT
CREATE INDEX idx_reports_ont_timestamp 
    ON diagnosis_reports (ont_address, timestamp DESC);

-- Дашборд онлайн/оффлайн
CREATE INDEX idx_reports_online 
    ON diagnosis_reports (is_online, timestamp DESC) 
    WHERE is_online = 0;

-- Трендинг оптики
CREATE INDEX idx_optics_report 
    ON optics_snapshots (report_id, sampled_at DESC);

-- Статистика правил
CREATE INDEX idx_rules_severity 
    ON rule_firings (severity, category, report_id);

-- MAC-инвентарь
CREATE INDEX idx_mac_report 
    ON mac_devices (report_id);

-- История LAN
CREATE INDEX idx_lan_report 
    ON lan_port_states (report_id);

-- Активные OLT
CREATE INDEX idx_olts_active 
    ON olts (is_active) WHERE is_active = TRUE;

-- Поиск ONT в реестре
CREATE INDEX idx_onts_address 
    ON onts (olt_id, ont_address);
```

---

## 3. Ключевые запросы, которые станут возможны

### 3.1. Анализ трендов (раньше невозможно)

```sql
-- Деградация оптической мощности за последние 30 дней
WITH recent_reports AS (
    SELECT dr.id, dr.timestamp, dr.ont_rx_power, dr.olt_rx_power
    FROM diagnosis_reports dr
    WHERE dr.ont_address = '0/1/3/9'
      AND dr.timestamp >= datetime('now', '-30 days')
      AND dr.ont_rx_power < 900  -- исключаем sentinel
)
SELECT 
    date(timestamp) as day,
    AVG(ont_rx_power) as avg_rx,
    MIN(ont_rx_power) as min_rx,
    MAX(ont_rx_power) as max_rx,
    COUNT(*) as samples
FROM recent_reports
GROUP BY date(timestamp)
ORDER BY day DESC;
```

**Используемый индекс:** `idx_reports_ont_timestamp`

### 3.2. Дашборд здоровья сети (вместо сканирования flat-файлов)

```sql
-- Последний статус каждого ONT по всем OLT
WITH latest AS (
    SELECT 
        ont_address,
        MAX(timestamp) as max_ts
    FROM diagnosis_reports
    GROUP BY ont_address
)
SELECT 
    dr.olt_name,
    dr.ont_address,
    dr.is_online,
    dr.ont_rx_power,
    dr.last_down_cause,
    rf.category,
    rf.description
FROM diagnosis_reports dr
JOIN latest l ON dr.ont_address = l.ont_address AND dr.timestamp = l.max_ts
LEFT JOIN rule_firings rf ON rf.report_id = dr.id AND rf.severity = 'critical'
WHERE dr.timestamp >= datetime('now', '-1 day')
ORDER BY dr.is_online, dr.olt_name;
```

**Используемые индексы:** `idx_reports_online`, `idx_rules_severity`

### 3.3. Частые проблемы (стабильность)

```sql
-- Топ-20 ONT с критичными проблемами за 7 дней
WITH report_issues AS (
    SELECT 
        dr.ont_address,
        dr.olt_name,
        COUNT(rf.id) as critical_count,
        GROUP_CONCAT(DISTINCT rf.category) as categories
    FROM diagnosis_reports dr
    JOIN rule_firings rf ON rf.report_id = dr.id
    WHERE dr.timestamp >= datetime('now', '-7 days')
      AND rf.severity = 'critical'
    GROUP BY dr.ont_address, dr.olt_name
)
SELECT ont_address, olt_name, critical_count, categories
FROM report_issues
ORDER BY critical_count DESC
LIMIT 20;
```

### 3.4. Аудит действий (compliance)

```sql
-- Полный журнал действий над конкретным ONT
SELECT 
    timestamp,
    agent_id,
    action,
    result,
    duration_ms
FROM audit_log
WHERE ont_address = '0/1/3/9'
  AND timestamp >= datetime('now', '-30 days')
ORDER BY timestamp DESC;
```

---

## 4. Стратегия миграции

### Фаза 1: Двойная запись (низкий риск)
```python
# В core/reporter.py
def save_report(report: DiagnosisReport, reports_dir: str = "data/reports") -> str:
    # Существующие flat-файлы (оставляем для отката)
    txt_path = _save_text_report(report, reports_dir)
    
    # Новая структурированная запись в БД
    _save_structured_report(report)
    
    return txt_path
```

### Фаза 2: Обратное заполнение исторических данных
```sql
-- Разовый перенос из JSON-отчётов
INSERT INTO diagnosis_reports (timestamp, olt_name, ont_address, ...)
SELECT 
    json_extract(data, '$.timestamp'),
    json_extract(data, '$.head_station'),
    json_extract(data, '$.ont'),
    ...
FROM legacy_reports_json;
```

### Фаза 3: Миграция чтения
- Обновить Web UI для запросов к SQL вместо сканирования `data/reports/`
- Обновить `diagnose.py` для чтения истории из БД при автопоиске

### Фаза 4: Удаление flat-файлов
- Оставить на 30 дней, потом удалить

---

## 5. Производительность

### 5.1. Оценка объёмов

| Таблица | Примерно строк/год (21 OLT, 10k ONT, диагноз раз в неделю) |
|---------|--------------------------------------------------------------|
| `diagnosis_reports` | ~10M |
| `optics_snapshots` | ~10M (1:1 с reports) |
| `rule_firings` | ~20-30M (в среднем 3-5 правил на отчёт) |
| `mac_devices` | ~5M (в среднем 5 MAC на отчёт) |
| `lan_port_states` | ~20M (4 порта × 1 отчёт) |

### 5.2. Особенности SQLite и mitigation

| Проблема | Решение |
|-----------|---------|
| Размер БД ~500MB/год | Приемлемо для SQLite; ротация раз в год |
| Write contention | WAL mode (`PRAGMA journal_mode=WAL`) |
| Медленные bulk inserts | Пакетная вставка через `executemany()` |
| Нужен vacuum | `PRAGMA auto_vacuum = INCREMENTAL` |

```sql
-- Рекомендуемые pragmas
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA cache_size = -64000;  -- 64MB
PRAGMA mmap_size = 268435456; -- 256MB
```

### 5.3. Партиционирование (если >10M строк)

SQLite не поддерживает нативное партиционирование, но можно эмулировать:
- Создавать таблицы по месяцам: `diagnosis_reports_2026_06`
- Маршрутизировать на уровне приложения по timestamp

---

## 6. Платформенные особенности

### 6.1. SQLite
- Нет `FULL OUTER JOIN` — использовать `UNION`
- Нет `GENERATED ALWAYS AS` для computed columns в старых версиях
- Использовать `datetime('now')` вместо `NOW()`
- `TEXT` для timestamp (ISO8601), не `DATETIME`

### 6.2. Будущая миграция на PostgreSQL

```sql
-- Переход на SERIAL / BIGSERIAL
-- Добавить JSONB для гибкого хранения
ALTER TABLE diagnosis_reports ADD COLUMN raw_metrics JSONB;
-- Использовать tsvector для full-text search
ALTER TABLE diagnosis_reports ADD COLUMN description_tsv TSVECTOR;
```

---

## 7. Приоритет реализации

| Приоритет | Фича | Трудоёмкость | Ценность |
|-----------|------|--------------|----------|
| **P0** | Структурированная `diagnosis_reports` (вместо JSON) | 2 дня | Высокая — открывает все запросы |
| **P0** | Таблица `rule_firings` | 1 день | Высокая — аудит |
| **P1** | `optics_snapshots` для трендов | 1 день | Средняя — проактивный ремонт |
| **P1** | Инвентарь `onts` | 1 день | Средняя — вместо YAML |
| **P2** | `mac_devices` персистентность | 0.5 дня | Низкая — forensics |
| **P2** | `audit_log` для compliance | 1 день | Средняя — закон |
| **P3** | История `lan_port_states` | 1 день | Низкая — детекция флапов |

---

## 8. Итог

**Лучший быстрый win:** Заменить `Diagnosis.report_json` TEXT на структурированную таблицу `diagnosis_reports`. Это одно изменение открывает:
- Дашборды (последний статус ONT)
- Трендовый анализ (Rx по времени)
- Статистику правил (самые частые проблемы)
- Аудиторские отчёты (compliance)

**Оценка ROI:** 2 дня разработки → устранение ручного разбора логов для 80% запросов NOC.

**Риск:** Низкий — двойная запись позволяет моментально откатиться на flat-файлы.

---

## 9. Где именно можно использовать БД в текущем коде

### 9.1. Сразу (P0)
- **`core/reporter.py`**: вместо сохранения JSON-отчета в `report_json` — запись строки в `diagnosis_reports`
- **`core/report.py`**: добавить метод `to_structured_dict()` для маппинга OntMetrics → row
- **Web UI** (`web/app.py`): дашборд "последний статус" из SQL, не из файлов

### 9.2. Краткосрочно (P1)
- **`core/engine.py`**: логировать каждое срабатывание правила в `rule_firings` (сейчас теряется после отчёта)
- **Оптический трендинг**: добавить в `diagnose.py` сохранение снапшота оптики в `optics_snapshots`
- **Инвентарь ONT**: `web/app.py:api_summary` → запись в `onts` вместо/вместе с `PortSnapshot`

### 9.3. Среднесрочно (P2)
- **Аудит**: `diagnose.py:run_diagnosis` — запись в `audit_log` (кто, что, результат)
- **MAC-устройства**: `core/parser.py:parse_mac_addresses` → `mac_devices`
- **Flapping detection**: `core/parser.py:parse_lan_ports` → `lan_port_states`

### 9.4. Долгосрочно (P3)
- **Конфигурация**: `config.yaml` → `olts`, `config_versions` таблицы
- **Автопоиск OLT**: `diagnose.py:find_olt_parallel` — читать `olts.is_active` из БД, не из YAML
- **MCP-инструменты**: `mcp_server.py` — возвращать aggregated данные из SQL, не из текстовых отчётов

---

## 10. Примеры готовых SQL-запросов для NOC

### 10.1. Критические ONT за сегодня
```sql
SELECT dr.olt_name, dr.ont_address, dr.last_down_cause, rf.description
FROM diagnosis_reports dr
JOIN rule_firings rf ON rf.report_id = dr.id
WHERE dr.timestamp >= date('now')
  AND rf.severity = 'critical'
ORDER BY dr.timestamp DESC;
```

### 10.2. Деградация Rx за неделю
```sql
SELECT dr.ont_address, dr.olt_name,
       MIN(dr.ont_rx_power) as min_rx,
       AVG(dr.ont_rx_power) as avg_rx
FROM diagnosis_reports dr
WHERE dr.timestamp >= datetime('now', '-7 days')
  AND dr.ont_rx_power < 900
GROUP BY dr.ont_address, dr.olt_name
HAVING min_rx < -30.0
ORDER BY min_rx ASC;
```

### 10.3. TOP проблемных категорий
```sql
SELECT rf.category, rf.severity, COUNT(*) as cnt
FROM rule_firings rf
JOIN diagnosis_reports dr ON dr.id = rf.report_id
WHERE dr.timestamp >= datetime('now', '-7 days')
GROUP BY rf.category, rf.severity
ORDER BY cnt DESC;
```

### 10.4. История конкретного ONT
```sql
SELECT dr.timestamp, dr.is_online, dr.ont_rx_power, dr.distance_m
FROM diagnosis_reports dr
WHERE dr.ont_address = '0/1/3/9'
ORDER BY dr.timestamp DESC
LIMIT 50;
```

---

## 11. Резюме

**Лучший быстрый результат:** Нормализованная таблица `diagnosis_reports` вместо JSON-блоба. Это одно изменение открывает:
- Дашборды (последний статус ONT)
- Трендовый анализ (Rx по времени)
- Статистику правил (самые частые проблемы)
- Аудиторские отчёты (compliance)

**Ожидаемый ROI:** 2 дня разработки → устранение ручного разбора логов для 80% запросов NOC.

**Риск:** Низкий — двойная запись позволяет мгновенный откат.
