<#
.SYNOPSIS
    Устанавливает browser-act и запускает браузер для входа на mail.ru
.REQUIREMENTS
    - Windows 10/11
    - PowerShell 5.1+ или PowerShell 7+
    - Интернет для скачивания Node.js и npm пакетов
#>

# Настройки
$ProfileDir = "$env:USERPROFILE\.config\browser-act\mailru"

Write-Host "=== Настройка browser-act для mail.ru ===" -ForegroundColor Cyan

# 1. Проверка Node.js
Write-Host "`n[1/5] Проверка Node.js..." -ForegroundColor Yellow
if (Get-Command node -ErrorAction SilentlyContinue) {
    $nodeVer = node --version
    Write-Host "  ✓ Node.js найден: $nodeVer" -ForegroundColor Green
}
else {
    Write-Host "  ✗ Node.js не найден" -ForegroundColor Red
    Write-Host "  Устанавливаю Node.js LTS через winget..." -ForegroundColor Yellow

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  ✗ Ошибка установки через winget. Скачайте вручную: https://nodejs.org/" -ForegroundColor Red
            Read-Host "Нажмите Enter для выхода"
            exit 1
        }
        $env:PATH = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    }
    else {
        Write-Host "  ✗ winget недоступен. Установите Node.js вручную: https://nodejs.org/" -ForegroundColor Red
        Read-Host "Нажмите Enter для выхода"
        exit 1
    }

    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        Write-Host "  ✗ Node.js всё ещё не найден. Перезапустите терминал и запустите скрипт снова." -ForegroundColor Red
        Read-Host "Нажмите Enter для выхода"
        exit 1
    }
    Write-Host "  ✓ Node.js установлен: $(node --version)" -ForegroundColor Green
}

# 2. Проверка/установка browser-act
Write-Host "`n[2/5] Установка browser-act..." -ForegroundColor Yellow
if (Get-Command browser-act -ErrorAction SilentlyContinue) {
    Write-Host "  ✓ browser-act уже установлен: $(browser-act --version)" -ForegroundColor Green
}
else {
    Write-Host "  Устанавливаю @browser-act/cli глобально..." -ForegroundColor Yellow
    npm install -g @browser-act/cli
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ✗ Ошибка установки. Попробуйте запустить от имени администратора." -ForegroundColor Red
        Read-Host "Нажмите Enter для выхода"
        exit 1
    }
    Write-Host "  ✓ browser-act установлен: $(browser-act --version)" -ForegroundColor Green
}

# 3. Создание браузера
Write-Host "`n[3/5] Создание браузера..." -ForegroundColor Yellow
$browserResult = browser-act browser create --type chrome --name "mailru-profile" --desc "Mail.ru persistent profile" --format json 2>&1
if ($LASTEXITCODE -ne 0) {
    # Возможно браузер уже существует
    $browsers = browser-act browser list --format json 2>$null | ConvertFrom-Json
    if ($browsers) {
        foreach ($b in $browsers) {
            if ($b.name -eq "mailru-profile") {
                $browserId = $b.id
                Write-Host "  ✓ Использую существующий браузер: $browserId" -ForegroundColor Green
                break
            }
        }
    }
    if (-not $browserId) {
        Write-Host "  ✗ Ошибка создания: $browserResult" -ForegroundColor Red
        Read-Host "Нажмите Enter для выхода"
        exit 1
    }
}
else {
    $created = $browserResult | ConvertFrom-Json
    $browserId = $created.id
    Write-Host "  ✓ Браузер создан: $browserId" -ForegroundColor Green
}

# 4. Запуск браузера для входа
Write-Host "`n[4/5] Запуск браузера для входа на mail.ru..." -ForegroundColor Yellow
Write-Host "  ОТКРОЕТСЯ ОКНО БРАУЗЕРА (Chrome)" -ForegroundColor Cyan
Write-Host "  1. Дождитесь загрузки https://e.mail.ru" -ForegroundColor Cyan
Write-Host "  2. Войдите в аккаунт (логин, пароль, 2FA)" -ForegroundColor Cyan
Write-Host "  3. Убедитесь, что входящие открылись" -ForegroundColor Cyan
Write-Host "  4. НЕ ЗАКРЫВАЙТЕ браузер сразу — дайте сохраниться куки (5-10 сек)" -ForegroundColor Yellow
Write-Host "  5. Потом можно закрыть окно" -ForegroundColor Cyan
Write-Host "`nНажмите Enter, чтобы запустить браузер..." -ForegroundColor Yellow
Read-Host | Out-Null

try {
    browser-act --session mailru browser open $browserId "https://e.mail.ru" --headed --allow-restart-chrome
}
catch {
    Write-Host "  Ошибка запуска: $_" -ForegroundColor Red
    Write-Host "  Попробуйте вручную:" -ForegroundColor Yellow
    Write-Host "  browser-act --session mailru browser open $browserId https://e.mail.ru --headed --allow-restart-chrome" -ForegroundColor Gray
    Read-Host "Нажмите Enter для выхода"
    exit 1
}

# 5. Проверка сессии
Write-Host "`n[5/5] Проверка сессии..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

# Попробуем получить куки через сессию
$cookies = browser-act --session mailru cookies get --url https://e.mail.ru 2>&1
if ($cookies -match "mail\.ru|session|auth") {
    Write-Host "  ✓ Сессия активна, куки найдены" -ForegroundColor Green
}
else {
    Write-Host "  ⚠ Куки не обнаружены (возможно, вход не завершён)" -ForegroundColor Yellow
}

Write-Host "`n=== Готово! ===" -ForegroundColor Green
Write-Host "`nТеперь читать входящие:" -ForegroundColor Cyan
Write-Host "  browser-act --session mailru navigate https://e.mail.ru/messages/inbox/" -ForegroundColor Gray
Write-Host "  browser-act --session mailru wait stable" -ForegroundColor Gray
Write-Host "  browser-act --session mailru get html" -ForegroundColor Gray
Write-Host "`nСкриншот:" -ForegroundColor Cyan
Write-Host "  browser-act --session mailru navigate https://e.mail.ru/messages/inbox/" -ForegroundColor Gray
Write-Host "  browser-act --session mailru wait stable" -ForegroundColor Gray
Write-Host "  browser-act --session mailru screenshot inbox.png" -ForegroundColor Gray
Write-Host "`nБраузер ID: $browserId" -ForegroundColor Gray
Write-Host "Сессия: mailru" -ForegroundColor Gray

Read-Host "`nНажмите Enter для выхода"