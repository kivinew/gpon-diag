# План рефакторинга GPON Diagnostic Framework

**Дата:** 2026-07-04  
**Статус:** ✅ Завершено  
**Автор:** AI Agent

---

## 1. Обзор текущего состояния

### 1.1 Структура проекта
```
gpon-diag/
├── diagnose.py          # CLI entry (делегирует core.cli_diagnosis)
├── config.yaml          # Конфигурация OLT и порогов
├── core/                # Основная логика
│   ├── models.py        # OntMetrics, OntSummary
│   ├── parser.py        # Парсер CLI-вывода Huawei
│   ├── engine.py        # Диагностический движок (правила)
│   ├── thresholds.py    # Пороги из config
│   ├── report.py        # Модели отчётов
│   ├── reporter.py      # Сохранение отчётов
│   ├── olt.py           # Telnet-соединение (singleton)
│   ├── adapter.py       # SecureCRT adapter
│   ├── collector.py     # Сбор данных
│   └── ...
├── web/app.py           # Flask-интерфейс (legacy)
├── web/api/             # FastAPI приложение
├── tests/               # Тесты
└── data/reports/        # Сохранённые отчёты
```

---

## 2. Выполненные изменения

### P0 — Критические баги ✅

| Изменение | Файл | Описание |
|-----------|------|----------|
| Исправлен маппинг поргов | `core/config_parser.py` | Пороги из config.yaml теперь корректно применяются |
| Устранены дубликаты | `core/constants.py` | Удалено дублирующееся `BAD_VERSIONS` |
| Исправлены паттерны | `core/parser.py` | Исправлены регулярки для memory_usage, cpu_usage, temperature |
| Устранён deprecation | `web/api/exceptions.py` | HTTP_422_UNPROCESSABLE_CONTENT вместо устаревшего |

### P1 — Архитектура ✅

| Изменение | Файл | Описание |
|-----------|------|----------|
| FastAPI сервер | `web/api/main.py` | Уже существует и работает |
| Типизация | `core/engine.py` | Добавлены аннотации к функциям-правилам |

---

## 3. Результаты тестирования

```
=== TEST 1: Offline (dying-gasp) ===
PASSED

=== TEST 2: Online healthy ===
PASSED

=== TEST 3: Low Rx + BIP errors ===
PASSED (3 problems)

PASSED: parse_input types
PASSED: web routes
PASSED: parse_ont_info_summary
PASSED: PortSnapshot model

========================================
ALL TESTS PASSED
```

---

## 4. Приоритеты изменений (итог)

| Приоритет | Изменение | Файл | Статус |
|-----------|-----------|------|--------|
| **P0** | Исправить маппинг поргов | `core/config_parser.py` | ✅ Выполнено |
| **P0** | Проверка sentinel-значений | `core/engine.py` | ✅ Уже работало |
| **P1** | Миграция Flask → FastAPI | `web/app.py` | ✅ Уже существует |
| **P1** | Добавить типизацию | `core/engine.py` | ✅ Выполнено |
| **P2** | Исправить паттерны парсера | `core/parser.py` | ✅ Выполнено |
| **P2** | Обработка исключений | `core/engine.py` | ✅ Уже работала |
| **P3** | Расширить тесты | `tests/test_smoke.py` | ⬜ Опционально |

---

## 5. Запуск веб-сервера

```bash
# FastAPI (рекомендуется)
PYTHONPATH=. python -m web.api.main

# Или через uvicorn
uvicorn web.api.main:app --host 0.0.0.0 --port 8000

# Доступно:
# - API docs: http://localhost:8000/docs
# - ReDoc: http://localhost:8000/redoc
```

---

## 6. Критерии готовности ✅

- [x] Все smoke-тесты проходят
- [x] Пороги применяются корректно
- [x] Веб-интерфейс работает
- [x] Исправлены критические баги

---

## 7. Файлы, изменённые в ходе рефакторинга

1. `core/config_parser.py` — исправлен маппинг поргов
2. `core/constants.py` — удалены дубликаты
3. `core/parser.py` — исправлены паттерны
4. `web/api/exceptions.py` — устранён deprecation warning
5. `core/engine.py` — добавлены типизации