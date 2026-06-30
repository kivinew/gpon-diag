# TODO — GPON Diagnostic Framework

## 🎯 Ключевые рекомендации (что даст максимум пользы)

| № | Что | Почему |
|---|-----|--------|
| 1 | **Пакетная диагностика** (`--batch file.csv`) | Самый частый запрос при массовых проверках абонентов |
| 2 | **Telegram-алерты** на critical-проблемы | Инженеры не сидят в вебе постоянно — уведомления в чат |
| 3 | **Исправить утечку connection pool и race condition** | Реальные баги, проявятся при параллельных запросах |
| 4 | **Вынести дублирующуюся логику подключения** из `web/app.py` в `core/collector.py` | 4+ маршрута копипастят один и тот же код |

## Оптимизации (code quality / reliability)

- [ ] **Утечка connection pool** — `_olt_registry` в `core/olt.py` никогда не очищает старые соединения. Добавить TTL или явную очистку при `close_all()`.
- [ ] **Race condition в `_skip_disconnect`** — флаг мутируется из нескольких потоков (port-monitor, diagnosis, search). Использовать `threading.Lock` в `OltConnection`.
- [ ] **Дублирование MAC DB** — `load_mac_database()` в `diagnose.py:108` и `_load_mac_database()` в `core/report.py:17` — идентичный код. Вынести в `core/parser.py` или отдельный модуль.
- [ ] **SSE thread leak в web/app.py** — при таймауте `queue.get(timeout=120)` генератор завершается, но `worker`-thread остаётся висеть, если OLT не отвечает. Добавить `threading.Event` для корректной остановки.
- [ ] **Дублирующийся тест** — `test_load_report_from_data` в `tests/test_smoke.py` — копия `test_offline_dying_gasp` с неработающим прологом (падает, если `data/reports` пуст). Удалить или починить.
- [ ] **Отсутствует валидация config.yaml** — опечатки в ключах порогов бесшумно игнорируются. Добавить `pydantic`-схему (опционально) или проверку при загрузке.
- [ ] **Путаница с MAC DB загрузкой** — `report.py` грузит `oui.txt` при каждом `to_text()` для online ONT. Кешировать или грузить один раз.
- [ ] **`test_smoke.py` использует `sys.path.insert` в теле модуля** — лучше перенести в `conftest.py` или `__init__.py`.

## Новые возможности (features)

### Высокий приоритет

- [ ] **CLI: пакетная диагностика** — `diagnose.py --batch file.csv` с колонками `address,olt_host`. Параллельный запуск через `ThreadPoolExecutor`.
- [ ] **CLI: инвентаризация порта** — `diagnose.py --port-summary 0/1/3 --olt OLT-NAME` — выгрузить все ONT на порту в JSON/CSV.
- [ ] **Веб: графики оптики в реальном времени** — на dashboard добавить `Chart.js` для истории `ont_rx_power` при auto-refresh.
- [ ] **Веб: экспорт отчёта в PDF** — кнопка «Скачать PDF» на странице результата (через `weasyprint` или `pdfkit`).
- [ ] **API: healthcheck с метриками** — `GET /api/health` — вернуть кол-во активных соединений, размер БД, аптайм.

### Средний приоритет

- [ ] **Alerting (Telegram)** — при обнаружении critical-проблем отправлять уведомление в Telegram-бота. Конфигурация в `config.yaml: alerts.telegram`.
- [ ] **Scheduled port snapshots** — фоновый сбор `display ont info summary` для всех GPON-портов раз в N минут. Хранить тренды в отдельной таблице SQLite.
- [ ] **ONT firmware scanner** — `diagnose.py --scan-firmware` — пройти по всем OLT, собрать версии всех ONT, вывести список с устаревшим ПО.
- [ ] **Сравнение снимков порта** — веб-страница diff: «что изменилось на порту за последние 24ч».
- [ ] **History trends API** — `GET /api/trends?address=0/1/3/9&field=ont_rx_power&days=7` — агрегация по историческим отчётам.

### Низкий приоритет

- [ ] **Multi-tenant auth для веба** — базовая HTTP Basic Auth или сессионная аутентификация (Flask-Login).
- [ ] **Excel-отчёт** — экспорт полной диагностики в `.xlsx` с цветовой кодировкой severity.
- [ ] **Read-only mode (CLI)** — `--read-only` запрещает `reset_lan_port`, `clear_errors`, `remote_ping`.
- [ ] **ONU Alias management** — удобный веб-интерфейс для массового переименования description ONT.
- [ ] **Поддержка SSH** — `--ssh` в CLI есть, но не реализован в `core/olt.py`. Добавить `SshConnection` subclass.

## Архитектурные

- [ ] **Убрать дублирование логики в `web/app.py`** — 4+ маршрута (`/api/diagnose`, `/api/search`, `/api/optics`, `/api/port-monitor`) содержат одинаковый код подключения к OLT. Вынести в `core/collector.py`.
- [ ] **Migrate to Alembic** — SQLite-схема (Diagnosis, PortSnapshot) расширяется вручную через `db.create_all()`. Пора на Alembic.
- [ ] **Async OLT connection** — заменить `time.sleep(N)` на `asyncio` для конкурентного опроса нескольких OLT без блокировки потоков.
- [ ] **Unified error handling** — разные маршруты возвращают error в разном формате (`{error: str}` vs HTML vs SSE). Унифицировать.

## Known Issues

- `find_ont_by_description()` делает двойной запрос при неудаче (`core/olt.py:500-503`) — баг или фича? Нужно разобраться.
- `test_load_report_from_data` в `tests/test_smoke.py` падает, если в `data/reports/` нет JSON-файлов.
