# $language = "Python"
# $interface = "1.0"

import importlib
import os
import argparse
import re
import sys
import time
import pyperclip
#______________________________________________________________
# Обязательная часть для работы подключаемого модуля GPON_class
# Добавляем текущую папку, где находится скрипт
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
# Импортируем модуль GPON
import GPON_class
importlib.reload(GPON_class)
from GPON_class import GPON, inject_crt, COMMANDS
# Передаём объект crt в импортированный модуль
inject_crt(crt)
#______________________________________________________________

MAC_DB_PATH = os.path.join(SCRIPT_DIR, "oui.txt")

BAD_VERSIONS = {
    "V1R003C00S108",
    "V1R006C00S130",
    "V1R006C00S205",
    "V1R006C00S201",
    "V1R006C01S201",
}

def load_mac_database():
    mac_db = {}
    if not os.path.exists(MAC_DB_PATH):
        return mac_db
    pattern = re.compile(
        r"^([0-9A-Fa-f]{2}[-]?[0-9A-Fa-f]{2}[-]?[0-9A-Fa-f]{2})\s+\(hex\)\s+(.+)|"
        r"^([0-9A-Fa-f]{6})\s+\(base 16\)\s+(.+)"
    )
    with open(MAC_DB_PATH, "r", encoding="utf-8") as f:
        for line in f:
            m = pattern.match(line.strip())
            if not m:
                continue
            oui = (m.group(1) or m.group(3)).replace("-", "").upper()
            vendor = (m.group(2) or m.group(4)).strip()
            mac_db[oui] = vendor.split()[0]
    return mac_db

def get_vendor(mac, mac_db):
    clean = re.sub(r"[^A-Fa-f0-9]", "", mac).upper()
    return mac_db.get(clean[:6], "n/a")

def output_to_clipboard_and_exit(text, title="Результат"):
    pyperclip.copy(text)
    crt.Dialog.MessageBox(title + "\n\nРезультат скопирован в буфер обмена.")

def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-n", "--no-actions", action="store_true",
                        help="Полная диагностика без перезапуска LAN-портов и сброса ошибок")
    parser.add_argument("-o", "--only-optics", action="store_true",
                        help="Только проверка оптики (уровни + BIP-ошибки)")
    parser.add_argument("-r", "--only-register", action="store_true",
                        help="Только проверка register-info")
    parser.add_argument("-d", "--delete", action="store_true",
                        help="Удаление терминала (ONT)")
    args = parser.parse_known_args()[0]

    # Проверка взаимоисключения (кроме -n)
    exclusive = [args.only_optics, args.only_register, args.delete]
    if sum(exclusive) > 1:
        crt.Dialog.MessageBox("Ошибка: аргументы -o, -r, -d не могут использоваться вместе.")
        return

    buffer_text = pyperclip.paste().strip()
    if not buffer_text:
        crt.Dialog.MessageBox("Буфер обмена пуст. Выделите SN, лицевой счёт или F/S/P/ONT.")
        return

    try:
        ont = GPON_class.GPON.from_buffer(buffer_text)
    except GPON_class.GPONError as e:
        crt.Dialog.MessageBox(str(e))
        return

    # ----- Удаление ONT -----
    if args.delete:
        try:
            ont.delete()
            output_to_clipboard_and_exit(
                f"ONT {ont.frame}/{ont.slot}/{ont.port}/{ont.ont} успешно удалён.",
                "Удаление ONT"
            )
        except Exception as e:
            output_to_clipboard_and_exit(f"Ошибка при удалении ONT:\n{e}", "Ошибка")
        return

    # ----- Только register-info -----
    if args.only_register:
        status_info = ont.get_status_info()
        if status_info['status'] != 'online':
            output_to_clipboard_and_exit(
                f"ONT {ont.frame}/{ont.slot}/{ont.port}/{ont.ont} не в сети.\n"
                "Невозможно получить register-info.",
                "Register-info"
            )
            return
        # Вход в interface gpon
        crt.Screen.Send(GPON_class.COMMANDS["iface_gpon"].format(frame=ont.frame, slot=ont.slot) + "\r")
        time.sleep(0.2)
        reg_output = ont.get_register_info()
        crt.Screen.Send("quit\r")
        output_to_clipboard_and_exit(reg_output, "Register-info")
        return

    # ----- Только оптика -----
    if args.only_optics:
        status_info = ont.get_status_info()
        if status_info['status'] != 'online':
            output_to_clipboard_and_exit(
                f"ONT {ont.frame}/{ont.slot}/{ont.port}/{ont.ont} не в сети.\n"
                "Оптическая диагностика невозможна.",
                "Проверка оптики"
            )
            return
        crt.Screen.Send(GPON_class.COMMANDS["iface_gpon"].format(frame=ont.frame, slot=ont.slot) + "\r")
        time.sleep(0.2)

        opt = ont.get_optical_powers()
        quality = ont.get_line_quality(clear=False)

        report = [
            f"ONT = {ont.frame}/{ont.slot}/{ont.port}/{ont.ont}",
            f"ONT Rx (dBm): {opt['ont_rx']}",
            f"OLT Rx (dBm): {opt['olt_rx']}",
            f"Upstream BIP ошибки: {quality['upstream']}",
            f"Downstream BIP ошибки: {quality['downstream']}",
        ]
        crt.Screen.Send("quit\r")
        output_to_clipboard_and_exit("\n".join(report), "Проверка оптики")
        return

    # ----- Полная диагностика (с возможным -n) -----
    info = ont.get_status_info()
    report = [
        f"ONT = {ont.frame}/{ont.slot}/{ont.port}/{ont.ont}",
        f"Дескрипшн (лицевой счёт) = {info['description']}",
        f"PON SN = {info['serial']}",
        f"Терминал {'доступен' if info['status'] == 'online' else 'недоступен'}.",
    ]

    if info['status'] != "online":
        report.append(f"Отключён: {info['downtime']}")
        report.append(f"Время последнего включения: {info['uptime']}")
        report.append(f"Расстояние от OLT (м): {info['distance']}")
        cause = info['downcause']
        if cause == "нет данных":
            report.append("Причина недоступности не зафиксирована.")
        elif "LOFi" in cause or "LOS" in cause:
            report.append(f"Причина: {cause} — низкий/отсутствует оптический сигнал. Необходима проверка оптической линии.")
        elif "dying-gasp" in cause:
            report.append(f"Причина: {cause} — отключение питания. Необходима проверка состояния роутера, БП.")
        else:
            report.append(f"Причина: {cause}")
        output_to_clipboard_and_exit("\n".join(report), "Диагностика (offline)")
        return

    # ONLINE
    allow_actions = not args.no_actions

    ver = ont.get_version_info()
    report.append(f"Включён: {info['uptime']}")
    report.append(f"Модель терминала: {ver['model']}")
    bad = " !!!" if ver['version'] in BAD_VERSIONS else ""
    report.append(f"Версия ПО: {ver['version']}{bad}")
    report.append(f"Расстояние от OLT (м): {info['distance']}\n")

    crt.Screen.Send(GPON_class.COMMANDS["iface_gpon"].format(frame=ont.frame, slot=ont.slot) + "\r")
    time.sleep(0.2)
    # Оптика
    opt = ont.get_optical_powers()
    report.append(f"ONT Rx (dBm): {opt['ont_rx']}")
    report.append(f"OLT Rx (dBm): {opt['olt_rx']}")

    trouble = []
    try:
        ont_rx = float(opt['ont_rx']) if opt['ont_rx'] != "нет данных" else None
        olt_rx = float(opt['olt_rx']) if opt['olt_rx'] != "нет данных" else None
        if ont_rx is not None and ont_rx < -26:
            trouble.append("Низкий уровень входящего сигнала (ONT RX), необходима проверка линии.")
        if olt_rx is not None and olt_rx < -32:
            trouble.append("Низкий уровень обратного сигнала (OLT RX), необходима проверка линии и терминала.")
    except ValueError:
        trouble.append("Не удалось определить уровень сигнала.")

    quality = ont.get_line_quality(clear=allow_actions)
    total = quality['upstream'] + quality['downstream']
    if total:
        prefix = "Значительное количество" if total > 10000 else "Незначительное количество"
        report.append(f"{prefix} ошибок оптики: Up={quality['upstream']}, Down={quality['downstream']}.")
        if allow_actions:
            report.append("Счётчики ошибок сброшены.")
    else:
        report.append("Ошибок оптики не обнаружено.")
    report.append("")

    # LAN-порты
    ports = ont.get_lan_ports_status()
    for port in ports:
        if port['link_state'] != 'up':
            continue
        report.append(f"LAN{port['lan_id']}: {port['port_type']}, {port['speed']} Mbps, {port['duplex']}, Link=up")
        if allow_actions:
            ont.reset_lan_port(int(port['lan_id']))
        err = ont.get_eth_errors(int(port['lan_id']), clear=allow_actions)
        if any(err.values()):
            report.append(f"  Ошибки Ethernet: FCS={err['fcs']}, Input bad={err['received_bad_bytes']}, Output bad={err['sent_bad_bytes']}.")
            if allow_actions:
                report.append("  Счётчики сброшены.")
            trouble.append(f"Проверьте патчкорды на LAN{port['lan_id']}.")
        else:
            report.append("  Ошибок Ethernet нет.")
    if not any(p['link_state'] == 'up' for p in ports):
        report.append("Ни один LAN-порт не в состоянии UP.")

    # MAC
    macs = ont.get_mac_table()
    if macs:
        report.append("\nMAC-адреса устройств за ONT:")
        mac_db = load_mac_database()
        seen = set()
        for dev in macs:
            mac = dev['mac']
            if mac in seen:
                continue
            seen.add(mac)
            vendor = get_vendor(mac, mac_db)
            port_label = "LAN" if dev['port_type'] == "ETH" else dev['port_type']
            report.append(f"{port_label}{dev['port_number']} {mac} — {vendor}")
    else:
        report.append("\nMAC-адреса не найдены (нет активных клиентов).")

    # Ping
    if "310" not in ver['model']:
        ont.remote_ping("1.1.1.1")  # выполняется, но не парсится

    crt.Screen.Send("quit\r")

    if trouble:
        report.append("\nРекомендации:\n" + "\n".join(trouble))
    else:
        report.append("\nНарушений не выявлено.")

    output_to_clipboard_and_exit("\n".join(report), "Полная диагностика")

if __name__ == "builtins" or __name__ == "__main__":
    main()