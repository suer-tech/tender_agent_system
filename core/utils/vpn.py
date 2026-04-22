"""Управление VPN (WireSock / AmneziaVPN) для переключения
между режимом сбора тендеров (VPN OFF) и режимом Claude (VPN ON).

Площадки тендеров (zakupki.gov.ru и др.) требуют российский IP → VPN OFF.
Claude API / Anthropic → требует не-российский IP → VPN ON.

Использование:
    from core.utils.vpn import vpn_off, vpn_on, vpn_status

    vpn_off()           # отключить VPN для доступа к тендерным площадкам
    vpn_on()            # включить VPN для доступа к Claude
    vpn_status()        # текущий статус
"""
from __future__ import annotations

import subprocess
import time

CLI = r"C:\Program Files\WireSock Secure Connect\command-line\wiresock-connect-cli.exe"

# Профиль VPN по умолчанию (определяется автоматически)
_default_profile: str | None = None


def _run(args: list[str], timeout: int = 15) -> str:
    """Выполнить команду WireSock CLI."""
    try:
        res = subprocess.run(
            [CLI] + args,
            capture_output=True, timeout=timeout,
        )
        out = (res.stdout or b"")
        # WireSock на Windows выдаёт cp866 / cp1251 / utf-8
        for enc in ("utf-8", "cp866", "cp1251"):
            try:
                return out.decode(enc).strip()
            except UnicodeDecodeError:
                continue
        return out.decode("utf-8", errors="replace").strip()
    except FileNotFoundError:
        return "[WireSock CLI not found]"
    except Exception as e:
        return f"[error: {e}]"


def vpn_status() -> dict:
    """Текущий статус VPN.

    Returns:
        {"connected": bool, "profile": str|None, "ip": str|None}
    """
    out = _run(["status"])
    if "Подключен" in out or "Connected" in out:
        # Извлекаем профиль и IP
        profile = None
        ip = None
        for line in out.splitlines():
            if "профил" in line.lower() or "profile" in line.lower():
                parts = line.split()
                profile = parts[-1] if parts else None
            if "внешний" in line.lower() or "external" in line.lower():
                # "Внешний адрес: 104.243.45.144, United States"
                for part in line.split():
                    if "." in part and part[0].isdigit():
                        ip = part.rstrip(",")
                        break
        return {"connected": True, "profile": profile, "ip": ip, "raw": out}
    return {"connected": False, "profile": None, "ip": None, "raw": out}


def vpn_profiles() -> list[str]:
    """Список доступных VPN-профилей."""
    out = _run(["list"])
    profiles = []
    for line in out.splitlines():
        line = line.strip().lstrip("- ").strip()
        if line and not line.lower().startswith(("доступ", "avail")):
            profiles.append(line)
    return profiles


def vpn_on(profile: str | None = None) -> bool:
    """Включить VPN. Возвращает True если подключён."""
    status = vpn_status()
    if status["connected"]:
        print(f"[vpn] уже подключён: {status['profile']}")
        return True

    if not profile:
        profile = _get_default_profile()
    if not profile:
        print("[vpn] нет доступных профилей")
        return False

    print(f"[vpn] подключаюсь к {profile}...")
    out = _run(["connect", profile, "-exit"], timeout=30)
    # Ждём подключения
    for _ in range(10):
        time.sleep(1)
        if vpn_status()["connected"]:
            print(f"[vpn] подключён: {profile}")
            return True
    print(f"[vpn] не удалось подключиться: {out}")
    return False


def vpn_off() -> bool:
    """Отключить VPN. Возвращает True если отключён."""
    status = vpn_status()
    if not status["connected"]:
        print("[vpn] уже отключён")
        return True

    # Запоминаем профиль для повторного подключения
    global _default_profile
    if status["profile"]:
        _default_profile = status["profile"]

    print("[vpn] отключаю...")
    _run(["disconnect"])
    for _ in range(5):
        time.sleep(1)
        if not vpn_status()["connected"]:
            print("[vpn] отключён")
            return True
    print("[vpn] не удалось отключить")
    return False


def _get_default_profile() -> str | None:
    """Определить профиль по умолчанию."""
    global _default_profile
    if _default_profile:
        return _default_profile
    profiles = vpn_profiles()
    if profiles:
        _default_profile = profiles[0]
    return _default_profile
