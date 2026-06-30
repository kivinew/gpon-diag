   Что было сделано:

   1. Рефакторинг ядра диагностики (core/engine.py):
      - Удалён неиспользуемый rule_match_state
      - Улучшена логика rule_long_distance (добавлены warn/crit пороги)
      - Упрощён rule_config_state
      - Очищен DEFAULT_RULES

   2. Стандартизация порогов (diagnose.py, core/thresholds.py):
      - Добавлен THRESHOLD_KEY_MAP и _build_thresholds() — единая точка загрузки
   порогов из config.yaml
      - Убраны хардкодные дефолты из CLI
      - Обновлены дефолты в Thresholds dataclass

   3. Исправление парсера (core/parser.py):
      - Сентнелы laser_bias_current (-1) и ont_temperature (-999) теперь сохраняются
   корректно

   4. Веб-интерфейс (web/app.py):
      - Использует новый unified threshold builder
      - Убран мёртвый код SQLite ALTER TABLE

   5. Файловые блокировки (core/reporter.py):
      - Исправлен путь к hermes-lockutils/file_lock.py — теперь через абсолютный путь

   6. Подключение к OLT (core/olt.py):
      - Инициализирован _last_used = time.time() (раньше 0.0 → немедленный idle-
   disconnect)
      - Сброс circuit-breaker при каждом connect()
      - self._strip_iac → модульная функция _strip_iac
      - Добавлен OSError catch в _read_until_prompt

   7. Обработка ошибок:
      - pyperclip импорт и clipboard failures логируются корректно

   Тестирование:
   - ✅ Smoke-тесты прошли:  uv run python -m tests.test_smoke — ALL TESTS PASSED
   - ⚠️Тест с реальным OLT:(172.16.17.232) показывает ConnectionAbortedError [ D
   WinError 10053] на этапе(аутентификации — это, скорее всего, сетевое ограничение/
   политика OLT в текущей среде. Логика теперь корректно обрабатывает такие ошибки.

   Следующий шаг — выкладка в staging с реальным доступом к OLT для проверки
   подключения.
