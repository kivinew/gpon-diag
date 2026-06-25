# $language = "Python"
# $interface = "1.0"

import re
import time
import pyperclip
from typing import Dict, List, Optional, Any

# crt = None

# Глобальная ссылка на объект crt (инициализируется из основного скрипта)
def inject_crt(obj):
    """Инъекция SecureCRT-объекта crt. Вызывать обязательно из основного скрипта после импорта этого модуля."""
    global crt
    crt = obj

# Команды OLT
COMMANDS = {
    "iface_gpon": "interface gpon {frame}/{slot}",
    "ont_info": "display ont info {frame} {slot} {port} {ont}",
    "info_by_serial": "display ont info by-sn {serial}",
    "info_by_description": "display ont info by-desc {description}",
    "ont_version": "display ont version {frame} {slot} {port} {ont}",
    "optical_info": "display ont optical-info {port} {ont}",
    "ont_line_quality": "{command} statistics ont-line-quality {port} {ont}",
    "eth_ports": "display ont port state {port} {ont} eth-port all",
    "eth_errors": "{command} statistics ont-eth {port} {ont} ont-port {lan_id}",
    "port_switch": "ont port attribute {port} {ont} eth {lan_id} operational-state {state}",
    "remote_ping": "ont remote-ping {port} {ont} ip-address {ip}",
    "mac_table": "display mac-address ont {frame}/{slot}/{port} {ont}",
    "quit": "quit",
}

PATTERNS = {
    "ont_by_sn": r"F\/S\/P\s*:\s(\d+)\/(\d+)\/(\d+).*ONT-ID\s*:\s(\d+)",
    "ont_by_desc": r"(\d+)\/\s*(\d+)\/\s*(\d+)\s+(\d+)",
    "status": r"Run state\s+:\s+(\S+)",
    "serial": r"(?i)SN\s+:\s+([\da-f]{16})",
    "description": r"Description\s+:\s(\S+)",
    "uptime": r"Last up time\s*:\s*([\d-]+\s[\d:+-]+)",
    "downtime": r"Last down time\s*:\s*([\d-]+\s[\d:+-]+)",
    "downcause": r"Last down cause\s+:\s+(\S+)",
    "distance": r"distance\(m\)\s*:\s*(\d+)",
    "soft_version": r"Main Software Version\s*:\s*(\S*)",
    "ont_model": r"OntProductDescription\s+: EchoLife (\S+) GPON",
    "ont_model2": r"Equipment-ID\s*:\s*(\w+)",
    "ont_rx_power": r"Rx optical power\(dBm\)\s*:\s*([\d.-]+)",
    "olt_rx_power": r"OLT Rx ONT optical power\(dBm\)\s*:\s*([\d.-]+)",
    "lan_ports": r"(\d+)\s+(\d+)\s+(GE|FE)\s+(\d+|-)+\s+(full|half|-)\s+(up|down)",
    "upstream_errors": r"Upstream frame BIP error count\s*:\s*(\d+)",
    "downstream_errors": r"Downstream frame BIP error count\s*:\s*(\d+)",
    "eth_errors": {
        "fcs": r"Received FCS error frames\s+:\s+(\d+)",
        "received_bad_bytes": r"Received bad bytes\s+:\s+(\d+)",
        "sent_bad_bytes": r"Sent bad bytes\s+:\s+(\d+)",
    },
    "mac_addresses": r"(ETH|WLAN)\s+(\d)+\s+([0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4})",
}

class GPONError(Exception):
    pass

class GPON:
    def __init__(self, frame: str, slot: str, port: str, ont: str,
                 sn: Optional[str] = None, desc: Optional[str] = None):
        if crt is None:
            raise RuntimeError("CRT не инициализирован. Вызовите inject_crt(crt).")
        self.frame = frame
        self.slot = slot
        self.port = port
        self.ont = ont
        self.sn = sn
        self.desc = desc

    # ---------------------- Фабрики ----------------------
    @classmethod
    def from_serial(cls, serial: str):
        output = cls._send_command_and_read(COMMANDS["info_by_serial"].format(serial=serial.upper()))
        match = re.search(PATTERNS["ont_by_sn"], output)
        if not match:
            raise GPONError(f"ONT с SN {serial} не найден")
        f, s, p, o = match.groups()
        return cls(f, s, p, o, sn=serial)

    @classmethod
    def from_description(cls, description: str):
        # Добавляем префикс fl_ если description - это цифры
        value = description
        if description.isdigit() and 5 <= len(description) <= 16:
            value = f"fl_{description}"
        output = cls._send_command_and_read(COMMANDS["info_by_description"].format(description=value))
        match = re.search(PATTERNS["ont_by_desc"], output)
        if not match:
            raise GPONError(f"ONT с описанием {description} не найден")
        f, s, p, o = match.groups()
        return cls(f, s, p, o, desc=description)

    @classmethod
    def from_fspo(cls, frame: str, slot: str, port: str, ont: str):
        return cls(frame, slot, port, ont)

    @classmethod
    def from_buffer(cls, buffer_text: str):
        buffer_text = buffer_text.strip()
        if re.fullmatch(r"(?i)(48575443|hwtc)[\da-f]{8}", buffer_text):
            return cls.from_serial(buffer_text)
        parts = buffer_text.replace("/", " ").split()
        if len(parts) == 4 and all(p.isdigit() for p in parts):
            return cls.from_fspo(parts[0], parts[1], parts[2], parts[3])
        if 4 < len(buffer_text) <= 16 and not re.match(r"[\d/ ]+$", buffer_text):
            return cls.from_description(buffer_text)
        raise GPONError("Не удалось определить тип идентификатора")

    # ---------------------- Низкоуровневые методы ----------------------
    @staticmethod
    def _send_command(cmd: str, delay: float = 0.2):
        crt.Screen.Send(cmd + "\r")
        time.sleep(delay)

    @staticmethod
    def _read_output() -> str:
        out = ""
        while True:
            line = crt.Screen.ReadString("\n", 1)
            if not line:
                break
            out += line
        return out

    @staticmethod
    def _send_command_and_read(cmd: str, delay: float = 0.2, special: str = None) -> str:
        crt.Screen.Send(cmd + "\r")
        time.sleep(delay)
        if special == "q":
            crt.Screen.Send("q")
            time.sleep(0.1)
        elif special == "space":
            crt.Screen.Send(" ")
            time.sleep(0.1)
        return GPON._read_output()

    # ---------------------- Методы диагностики ----------------------
    def get_status_info(self) -> Dict[str, str]:
        """Базовая информация (статус, SN, desc, uptime, downtime, distance)."""
        cmd = COMMANDS["ont_info"].format(frame=self.frame, slot=self.slot, port=self.port, ont=self.ont)
        output = self._send_command_and_read(cmd, special="q")
        data = {}
        for key in ("status", "serial", "description", "uptime", "downtime", "downcause", "distance"):
            match = re.search(PATTERNS[key], output)
            data[key] = match.group(1) if match else "нет данных"
        return data

    def get_version_info(self) -> Dict[str, str]:
        """Модель и версия ПО."""
        cmd = COMMANDS["ont_version"].format(frame=self.frame, slot=self.slot, port=self.port, ont=self.ont)
        output = self._send_command_and_read(cmd)
        model = re.search(PATTERNS["ont_model"], output)
        if not model:
            model = re.search(PATTERNS["ont_model2"], output)
        version = re.search(PATTERNS["soft_version"], output)
        return {
            "model": model.group(1) if model else "нет данных",
            "version": version.group(1) if version else "нет данных",
        }

    def get_optical_powers(self) -> Dict[str, str]:
        """Уровни ONT Rx и OLT Rx."""
        self._send_command(COMMANDS["iface_gpon"].format(frame=self.frame, slot=self.slot))
        output = self._send_command_and_read(
            COMMANDS["optical_info"].format(port=self.port, ont=self.ont),
            special="space"
        )
        self._send_command("quit")
        ont_rx = re.search(PATTERNS["ont_rx_power"], output)
        olt_rx = re.search(PATTERNS["olt_rx_power"], output)
        return {
            "ont_rx": ont_rx.group(1) if ont_rx else "нет данных",
            "olt_rx": olt_rx.group(1) if olt_rx else "нет данных",
        }

    def get_line_quality(self, clear: bool = False) -> Dict[str, int]:
        """BIP ошибки (с опцией сброса)."""
        cmd = COMMANDS["ont_line_quality"].format(
            command="clear" if clear else "display",
            port=self.port,
            ont=self.ont
        )
        output = self._send_command_and_read(cmd)
        upstream = re.search(PATTERNS["upstream_errors"], output)
        downstream = re.search(PATTERNS["downstream_errors"], output)
        return {
            "upstream": int(upstream.group(1)) if upstream else 0,
            "downstream": int(downstream.group(1)) if downstream else 0,
        }

    def get_lan_ports_status(self) -> List[Dict[str, str]]:
        """Состояние всех LAN-портов."""
        cmd = COMMANDS["eth_ports"].format(port=self.port, ont=self.ont)
        output = self._send_command_and_read(cmd)
        ports = []
        for m in re.finditer(PATTERNS["lan_ports"], output):
            ports.append({
                "lan_id": m.group(2),
                "port_type": m.group(3),
                "speed": m.group(4),
                "duplex": m.group(5),
                "link_state": m.group(6),
            })
        return ports

    def get_eth_errors(self, lan_id: int, clear: bool = False) -> Dict[str, int]:
        """Ethernet-ошибки на порту (с опцией сброса)."""
        cmd = COMMANDS["eth_errors"].format(
            command="clear" if clear else "display",
            port=self.port,
            ont=self.ont,
            lan_id=lan_id
        )
        output = self._send_command_and_read(cmd)
        errors = {}
        for key, pattern in PATTERNS["eth_errors"].items():
            m = re.search(pattern, output)
            errors[key] = int(m.group(1)) if m else 0
        return errors

    def reset_lan_port(self, lan_id: int) -> None:
        """Перезапуск LAN-порта (выкл/вкл)."""
        cmd_off = COMMANDS["port_switch"].format(port=self.port, ont=self.ont, lan_id=lan_id, state="off")
        cmd_on = COMMANDS["port_switch"].format(port=self.port, ont=self.ont, lan_id=lan_id, state="on")
        self._send_command(cmd_off)
        time.sleep(0.5)
        self._send_command(cmd_on)

    def get_register_info(self) -> str:
        """Возвращает вывод display ont register-info."""
        cmd = f"display ont register-info {self.port} {self.ont}"
        return self._send_command_and_read(cmd)

    def get_mac_table(self) -> List[Dict[str, str]]:
        """MAC-адреса за ONT."""
        cmd = COMMANDS["mac_table"].format(frame=self.frame, slot=self.slot, port=self.port, ont=self.ont)
        output = self._send_command_and_read(cmd)
        devices = []
        for m in re.finditer(PATTERNS["mac_addresses"], output):
            devices.append({
                "port_type": m.group(1),
                "port_number": m.group(2),
                "mac": m.group(3),
            })
        return devices

    def remote_ping(self, ip: str = "1.1.1.1") -> str:
        """Ping с ONT (возвращает вывод)."""
        cmd = COMMANDS["remote_ping"].format(port=self.port, ont=self.ont, ip=ip)
        return self._send_command_and_read(cmd, delay=3)

    def delete(self) -> None:
        """Удаление ONT (сервисные порты + сама ONT)."""
        scr = crt.Screen
        scr.Send(f"undo service-port port {self.frame}/{self.slot}/{self.port} ont {self.ont}\r")
        scr.WaitForString("gemport", 5)
        scr.Send("\r")
        scr.WaitForString("(y/n)", 5)
        scr.Send("y\r")
        scr.Send(COMMANDS["iface_gpon"].format(frame=self.frame, slot=self.slot) + "\r")
        scr.Send(COMMANDS["ont_delete"].format(port=self.port, ont=self.ont) + "\r")
        scr.Send("q\r")
        
if __name__ == "builtins":
    try:
        memBuffer = pyperclip.paste()
        ontSelect = memBuffer.replace('/', ' ').split()
        ont = GPON(ontSelect)
        ont.get_info()
    except pyperclip.PyperclipException as e:
        crt.Dialog.MessageBox(f"Ошибка чтения буфера обмена:\r{e}")
    except ValueError as e:
        crt.Dialog.MessageBox(f"Ошибка при получении данных об ONT: {e}")
    except Exception as e:
        crt.Dialog.MessageBox(f"Ошибка при выполнении:\r{e}")