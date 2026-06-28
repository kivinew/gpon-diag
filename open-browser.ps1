<#
.SYNOPSIS
    Запускает/переиспользует ЕДИНСТВЕННЫЙ браузер, удаляет лишние.
#>

param(
    [string]$Url = "https://www.notion.so",
    [string]$SessionName = "main",
    [string]$BrowserName = "main-browser"
)

Write-Host "=== Единый браузер: $BrowserName ===" -ForegroundColor Cyan

# 1. Список браузеров
$browsersJson = browser-act browser list --format json 2>$null
if ($browsersJson) {
    $browsers = $browsersJson | ConvertFrom-Json
} else {
    $browsers = @()
}

# 2. Ищем наш браузер
$mainBrowser = $null
foreach ($b in $browsers) {
    if ($b.name -eq $BrowserName) {
        $mainBrowser = $b
        break
    }
}

# 3. Удаляем все остальные
foreach ($b in $browsers) {
    if ($b.name -ne $BrowserName) {
        Write-Host "  Удаляю лишний: $($b.name) ($($b.id))" -ForegroundColor Yellow
        browser-act browser delete $b.id 2>$null
    }
}

# 4. Создаём если нет
if (-not $mainBrowser) {
    Write-Host "  Создаю основной браузер..." -ForegroundColor Yellow
    $result = browser-act browser create --type chrome --name $BrowserName --desc "Main persistent browser" --format json 2>&1
    if ($LASTEXITCODE -eq 0) {
        $mainBrowser = $result | ConvertFrom-Json
        Write-Host "  OK: $($mainBrowser.id)" -ForegroundColor Green
    } else {
        Write-Host "  ERROR: $result" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "  Использую существующий: $($mainBrowser.id)" -ForegroundColor Green
}

# 5. Открываем URL
Write-Host "`nОткрываю $Url ..." -ForegroundColor Yellow
browser-act --session $SessionName browser open $mainBrowser.id $Url --headed --allow-restart-chrome

Write-Host "`n=== Готово ===" -ForegroundColor Green
Write-Host "Browser ID: $($mainBrowser.id)" -ForegroundColor Gray
Write-Host "Session: $SessionName" -ForegroundColor Gray