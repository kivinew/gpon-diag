# GPON Diagnostic Framework

Автоматизированная система диагностики GPON-сети на базе Huawei OLT.

## Возможности

- Подключение к Huawei OLT через Telnet
- Сбор оптических параметров ONT (Rx/Tx power, laser bias, temperature, voltage)
- Парсинг диагностической информации (FEC, BIP errors, distance, last-down-cause)
- Rule-based движок диагностики с настраиваемыми порогами
- Генерация текстовых и JSON-отчётов
- Интеграция с SecureCRT (адаптер + stub)
- Пинг-тестирование ONT

## Структура проекта

```
gpon-diag/
├── config.yaml           # Конфигурация OLT, порогов, настроек отчётов
├── main.py               # Точка входа
├── diagnose.py           # CLI для запуска диагностики
├── securecrt_adapter.py  # Адаптер для работы через SecureCRT
├── core/
│   ├── engine.py         # Rule-based движок диагностики
│   ├── models.py         # Модели данных (OntMetrics, OltInfo)
│   ├── collector.py      # Сбор данных с OLT
│   ├── parser.py         # Парсинг вывода команд OLT
│   ├── report.py         # Генерация отчётов
│   ├── reporter.py       # Вывод отчётов в консоль/файл
│   ├── thresholds.py     # Пороговые значения для правил
│   ├── olt.py            # Работа с OLT (telnet, команды)
│   ├── adapter.py        # Абстракция адаптера (telnet/SecureCRT)
│   └── crt_stub.py       # Stub для SecureCRT (тестирование без реального OLT)
├── data/
│   ├── incidents/        # Инциденты
│   └── reports/          # Сгенерированные отчёты
├── interfaces/            # Описания интерфейсов (резерв)
└── tests/
    └── test_smoke.py     # Smoke-тесты
```

## Установка

```bash
uv sync
```

## Использование

Диагностика ONT по индексу на конкретном OLT:

```bash
uv run diagnose.py --olt 172.16.17.232 --ont-index 0/1/3
```

Тестовый запуск без реального OLT:

```bash
uv run debug_test.py
```

## Конфигурация

Основной файл: `config.yaml`

- **olts** — список OLT с адресами и учётными данными
- **thresholds** — пороговые значения для предупреждений и критических состояний
- **bad_versions** — список проблемных версий прошивки ONT
- **report** — настройки формата и сохранения отчётов

## Зависимости

- Python 3.12+
- pyyaml — конфигурация
- telnetlib3 — асинхронный Telnet

## Лицензия

Private
