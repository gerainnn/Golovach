#!/usr/bin/env python3
"""Единый скрипт установки и настройки Golovach.

Запуск:
    python setup.py

Что делает:
1. Проверяет Python >= 3.10
2. Создаёт venv (если нет)
3. Устанавливает зависимости из requirements.txt
4. Запускает интерактивную настройку (провайдеры, модели, токен)
5. Предлагает сразу запустить бота
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
IS_WIN = platform.system() == "Windows"
PYTHON_MIN = (3, 10)


def cprint(msg: str, color: str = "") -> None:
    colors = {"r": "31", "g": "32", "y": "33", "c": "36", "b": "1"}
    code = colors.get(color, "0")
    if sys.stdout.isatty():
        print(f"\033[{code}m{msg}\033[0m")
    else:
        print(msg)


def get_venv_python() -> Path:
    if IS_WIN:
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def get_venv_pip() -> Path:
    if IS_WIN:
        return VENV_DIR / "Scripts" / "pip.exe"
    return VENV_DIR / "bin" / "pip"


def check_python() -> None:
    cprint("\n[1/5] Проверяю Python...", "c")
    v = sys.version_info
    cprint(f"       Python {v.major}.{v.minor}.{v.micro}", "g")
    if (v.major, v.minor) < PYTHON_MIN:
        cprint(f"  Нужен Python >= {PYTHON_MIN[0]}.{PYTHON_MIN[1]}!", "r")
        sys.exit(1)


def create_venv() -> None:
    cprint("\n[2/5] Виртуальное окружение...", "c")
    if VENV_DIR.exists() and get_venv_python().exists():
        cprint("       .venv уже существует, пропускаю.", "g")
        return
    cprint("       Создаю .venv...", "y")
    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
    cprint("       Готово.", "g")


def install_deps() -> None:
    cprint("\n[3/5] Устанавливаю зависимости...", "c")
    pip = str(get_venv_pip())
    subprocess.run([pip, "install", "--upgrade", "pip"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([pip, "install", "-r", str(REQUIREMENTS)], check=True)
    cprint("       Все пакеты установлены.", "g")


def run_configure() -> None:
    cprint("\n[4/5] Настройка (провайдеры, модели, Telegram)...", "c")
    cprint("       Откроется интерактивное меню.\n", "y")
    python = str(get_venv_python())
    try:
        subprocess.run([python, str(ROOT / "configure.py")], check=True)
    except (subprocess.CalledProcessError, KeyboardInterrupt):
        cprint("       Настройка прервана. Позже: python configure.py", "y")


def offer_launch() -> None:
    cprint("\n[5/5] Всё готово!", "g")
    cprint("\n  Запустить бота сейчас? (Ctrl+C чтобы потом остановить)", "b")
    try:
        answer = input("  [Y/n]: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        answer = "n"

    if answer in ("", "y", "yes", "д", "да"):
        python = str(get_venv_python())
        cprint("\n  Запускаю...\n", "g")
        os.execv(python, [python, str(ROOT / "main.py")])
    else:
        cprint("\n  Когда будешь готов:", "c")
        if IS_WIN:
            cprint("    .venv\\Scripts\\python main.py", "")
        else:
            cprint("    .venv/bin/python main.py", "")


def main() -> None:
    cprint("╔══════════════════════════════════════════════╗", "c")
    cprint("║     Golovach — установка и настройка         ║", "c")
    cprint("║     AI-команда агентов в Telegram            ║", "c")
    cprint("╚══════════════════════════════════════════════╝", "c")

    check_python()
    create_venv()
    install_deps()
    run_configure()
    offer_launch()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        cprint("\n\nПрервано.", "y")
        sys.exit(130)
    except subprocess.CalledProcessError as e:
        cprint(f"\nОшибка: {e}", "r")
        sys.exit(1)
