# MCP Server for GPON Huawei

MCP сервер для управления Huawei GPON ONT через telnet.

## Installation

```bash
# MCP сервер уже включен в pyproject.toml (mcp>=1.0.0)
uv sync
```

## Usage

### 1. Add to MCP configuration

Файл `.mcp.json` уже создан. Добавьте его в ваш MCP клиент:

```json
{
  "mcpServers": {
    "gpon-huawei": {
      "command": "uv",
      "args": ["run", "python", "mcp_server.py"],
      "env": {
        "PYTHONPATH": "E:/DOWNLOADS/CREATIVE/PYTHON/GitHub/gpon-diag"
      }
    }
  }
}
```

### 2. Available Tools

#### `gpon_connect`
Подключение к OLT и получение информации о головной станции.

Parameters:
- `host` (string, required) — IP адрес OLT
- `port` (integer, default: 23) — Telnet порт
- `username` (string, required) — Имя пользователя
- `password` (string, required) — Пароль
- `timeout` (integer, default: 30) — Таймаут подключения
- `session_name` (string, default: "default") — Идентификатор сессии

#### `gpon_diagnose`
Полная диагностика ONT.

Parameters:
- `ont` (string, required) — Адрес ONT (F/S/P/ONT), серийный номер или описание
- `session_name` (string, default: "default") — Идентификатор сессии
- `allow_actions` (boolean, default: true) — Выполнять действия (сброс ошибок, порты)
- `ping_target` (string, default: "1.1.1.1") — Цель для удалённого ping

#### `gpon_clear_errors`
Сброс счётчиков ошибок BIP и Ethernet.

Parameters:
- `address` (string, required) — Адрес ONT (F/S/P/ONT)
- `session_name` (string, default: "default") — Идентификатор сессии

#### `gpon_reset_lan_port`
Перезапуск LAN порта (выключить/включить).

Parameters:
- `address` (string, required) — Адрес ONT (F/S/P/ONT)
- `lan_id` (integer, required) — Номер порта (1-4)
- `session_name` (string, default: "default") — Идентификатор сессии

#### `gpon_get_optics`
Получение оптических параметров в реальном времени.

Parameters:
- `address` (string, required) — Адрес ONT (F/S/P/ONT)
- `session_name` (string, default: "default") — Идентификатор сессии

## Workflow

1. Сначала подключитесь: `gpon_connect` с host/username/password
2. Затем используйте: `gpon_diagnose`, `gpon_clear_errors`, `gpon_reset_lan_port`, `gpon_get_optics`
3. Сессии множественные — используйте разные `session_name` для параллельных подключений

## Security

- Не храните учётные данные в файлах!
- Используйте переменные окружения или передавайте credentials в запросе
- MCP сервер создаёт telnet соединения на лету

## Example

```json
// 1. Connect
{"method": "tools/call", "params": {"name": "gpon_connect", "arguments": {"host": "172.16.17.232", "username": "...", "password": "..."}}}

// 2. Diagnose ONT
{"method": "tools/call", "params": {"name": "gpon_diagnose", "arguments": {"ont": "0/1/3/9", "session_name": "default"}}}

// 3. Clear errors
{"method": "tools/call", "params": {"name": "gpon_clear_errors", "arguments": {"address": "0/1/3/9", "session_name": "default"}}}
```