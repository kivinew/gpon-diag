# MCP Server for GPON Huawei Diagnostics

MCP (Model Context Protocol) сервер для диагностики GPON сетей Huawei OLT через Telnet.

## Возможности

| Инструмент | Описание |
|------------|----------|
| `diagnose` | Полная диагностика ONT (оптика, качество линии, LAN, WAN, MAC, ping) |
| `search_ont` | Поиск ONT по серийному номеру, описанию или адресу |
| `get_optical` | Оптические параметры: Rx/Tx power, лазер, температура, BIP ошибки |
| `get_line_quality` | Статистика BIP ошибок (upstream/downstream) |
| `get_lan_ports` | Состояние LAN портов (скорость, дуплекс, link) |
| `ont_ping` | Удалёный ping от ONT к целевому хосту |
| `reset_lan_port` | Сброс LAN порта |
| `clear_ont_errors` | Очистка счётчиков ошибок |
| `get_port_summary` | Сводная информация обо всех ONT на порту |
| `list_olts` | Список настроенных OLT |
| `reset_connections` | Сбросить все соединения |

## Установка

```bash
uv sync
```

## Запуск

```bash
# STDIO режим (для MCP клиентов)
uv run python mcp_server.py

# SSE транспорт (экспериментально)
uv run python mcp_server.py --transport sse --port 8090
```

## Использование с MCP клиентом

### Конфигурация для Claude Desktop

Добавьте в `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "gpon-diag": {
      "command": "uv",
      "args": ["run", "python", "/путь/до/gpon-diag/mcp_server.py"],
      "env": {
        "GPON_OLT_DEFAULT_USERNAME": "admin",
        "GPON_OLT_DEFAULT_PASSWORD": "password"
      }
    }
  }
}
```

### Примеры вызовов

```json
// Диагностика ONT
{"tool": "diagnose", "arguments": {"query": "0/1/3/9"}}

// Поиск по серийному номеру
{"tool": "search_ont", "arguments": {"query": "4857544312E0E379"}}

// Получение оптики
{"tool": "get_optical", "arguments": {"address": "0/1/3/9"}}

// Свод по порту
{"tool": "get_port_summary", "arguments": {"port_address": "0/1/3"}}
```

## Ресурсы

| URI | Описание |
|-----|----------|
| `gpon://config/olts` | Список настроенных OLT |
| `gpon://ont/{address}/diagnosis` | Диагноз ONT по адресу |

## Архитектура

```
MCP Client ←→ MCP Server ←→ core/
                    │           ├── models.py (OntMetrics)
                    │           ├── parser.py (PATTERNS)
                    │           ├── engine.py (21 правило)
                    │           └── olt.py (OltConnection)
                    │
                    └─ Telnet → Huawei OLT
```

## Безопасность

- Учётные данные через переменные окружения
- Автоматическое закрытие соединений
- Используйте management VLAN для Telnet