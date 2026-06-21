# GPON Diagnostic Framework

Автоматизированная система диагностики GPON-сети на базе Huawei OLT.

## Возможности

- Подключение к Huawei OLT через Telnet
- Сбор оптических параметров ONT (Rx/Tx power, laser bias, temperature, voltage)
- Парсинг диагностической информации (FEC, BIP errors, distance, last-down-cause)
- Rule-based движок диагностики с настраиваемыми порогами
- Генерация текстовых и JSON-отчётов
- Интеграция с SecureCRT (адаптер + stub)
- Диагностика WAN-соединений и LAN-портов
- Мониторинг CPU, памяти, температуры ONT

## Структура проекта

```
gpon-diag/
├── config.yaml           # Конфигурация OLT, порогов, настроек отчётов
├── diagnose.py           # CLI для запуска диагностики
├── securecrt_adapter.py  # Адаптер для работы через SecureCRT
├── probe_all.py          # Скрипт для отладки (требует credentials)
├── debug_test.py         # Тест Telnet-соединения
├── core/
│   ├── engine.py         # Rule-based движок диагностики
│   ├── models.py         # Модели данных (OntMetrics, LanPort, MacDevice)
│   ├── collector.py      # Сбор данных с OLT через telnetlib3
│   ├── parser.py         # Парсинг вывода команд OLT
│   ├── report.py         # Модели отчётов (DiagnosisProblem, DiagnosisReport)
│   ├── reporter.py       # Сохранение отчётов в файлы
│   ├── thresholds.py     # Пороговые значения для правил
│   ├── olt.py            # Менеджер подключений к OLT (singleton)
│   ├── adapter.py        # Адаптер для GPON_class.py (legacy)
│   └── crt_stub.py       # Эмуляция SecureCRT для тестирования
├── data/
│   ├── incidents/        # Инциденты (резерв)
│   └── reports/          # Сгенерированные отчёты
├── tests/
│   └── test_smoke.py     # Smoke-тесты движка диагностики
└── .env.example          # Шаблон переменных окружения
```

## Установка

```bash
uv sync
```

## Настройка безопасности

### ⚠️ Важное предупреждение

**Никогда не храните пароли в файлах проекта!** Все учётные данные должны передаваться через переменные окружения.

### Настройка учётных данных OLT

Проект автоматически подхватывает переменные окружения с именами:
- `GPON_OLT_<OLT_NAME>_USERNAME`
- `GPON_OLT_<OLT_NAME>_PASSWORD`

Где `<OLT_NAME>` — имя OLT из `config.yaml` с заменой не-алфавитно-цифровых символов на `_`.

**Пример для OLT с именем `OLT-17.232`:**

**PowerShell:**
```powershell
$env:GPON_OLT_17_232_USERNAME="admin"
$env:GPON_OLT_17_232_PASSWORD="your_password"
```

**CMD:**
```cmd
set GPON_OLT_17_232_USERNAME=admin
set GPON_OLT_17_232_PASSWORD=your_password
```

**Пример для OLT с именем `OLT-40.111`:**
```powershell
$env:GPON_OLT_40_111_USERNAME="admin"
$env:GPON_OLT_40_111_PASSWORD="your_password"
```

## Использование

### Быстрая диагностика (авто-OLT)

```bash
uv run diagnose.py 0/1/3/9
uv run diagnose.py 4857544312E0E379
uv run diagnose.py fl_12345
```

### С выбором OLT

```bash
uv run diagnose.py 0/1/3/9 --olt "OLT-17.232"
```

### С копированием в буфер обмена

```bash
uv run diagnose.py 0/1/3/9 --clipboard
```

### Вывод в JSON

```bash
uv run diagnose.py 0/1/3/9 --json
```

### Без сохранения отчёта

```bash
uv run diagnose.py 0/1/3/9 --no-save
```

### Тестовый запуск (smoke-тесты)

```bash
uv run python -m tests.test_smoke
```

## Конфигурация

Основной файл: `config.yaml`

### OLT (список оборудования)

```yaml
olts:
  - name: "OLT-17.232"
    host: "172.16.17.232"
    port: 23
  - name: "OLT-40.111"
    host: "172.16.40.111"
    port: 23
```

### Thresholds (пороги диагностики)

| Параметр | Значение по умолчанию | Описание |
|----------|----------------------|----------|
| `ont_rx_power_warn_dbm` | -26.5 | Предупреждение: низкий сигнал ONT |
| `ont_rx_power_crit_dbm` | -30.0 | Критично: очень низкий сигнал ONT |
| `olt_rx_power_warn_dbm` | -33.0 | Предупреждение: низкий сигнал OLT |
| `olt_rx_power_crit_dbm` | -35.0 | Критично: очень низкий сигнал OLT |
| `bip_error_warn` | 10000 | Предупреждение: ошибки BIP |
| `bip_error_crit` | 100000 | Критично: много ошибок BIP |
| `cpu_temp_warn_c` | 75 | Предупреждение: температура CPU |
| `cpu_temp_crit_c` | 90 | Критично: перегрев CPU |
| `cpu_usage_warn_pct` | 90 | Предупреждение: загрузка CPU |
| `memory_usage_warn_pct` | 85 | Предупреждение: загрузка памяти |
| `distance_warn_m` | 18000 | Предупреждение: большая дистанция |
| `distance_crit_m` | 20000 | Критично: превышение дистанции |

### Bad Versions (проблемные прошивки)

```yaml
bad_versions:
  - "V1R003C00S108"
  - "V1R006C00S130"
  - "V1R006C00S205"
```

### Report (настройки отчётов)

```yaml
report:
  format: "text"           # text | json
  save_to_file: true
  reports_dir: "data/reports"
  include_timestamp: true
```

## Диагностика проблем

Движок автоматически выявляет следующие проблемы:

| Категория | Проблема | Описание |
|-----------|----------|----------|
| **optic** | Low ONT Rx | Низкий уровень оптического сигнала от ONT |
| **optic** | Low OLT Rx | Низкий уровень обратного сигнала от OLT |
| **optic** | BIP errors | Ошибки коррекции данных (FEC) |
| **power** | Dying Gasp | Потеря питания ONT |
| **hardware** | Overheating | Перегрев терминала |
| **hardware** | Low voltage | Низкое напряжение питания |
| **firmware** | Bad version | Устаревшая прошивка |
| **config** | Match state mismatch | ONT не соответствует профилю |
| **ethernet** | No LAN activity | Нет активных LAN-портов |
| **wan** | WAN disconnected | WAN-соединение не активно |

## Зависимости

- Python 3.12+
- pyyaml — конфигурация
- telnetlib3 — асинхронный Telnet

## Безопасность

- ✅ Переменные окружения для учётных данных
- ✅ Валидация входных параметров (только цифры для F/S/P/ONT)
- ✅ Логирование ошибок диагностики
- ✅ `.gitignore` исключает секреты и отчёты
- ⚠️ Telnet не шифрует трафик — используйте management VLAN

## Лицензия

Private
