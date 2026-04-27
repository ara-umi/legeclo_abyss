from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


def app_base_dir() -> Path:
    """Return the program directory for both source and PyInstaller builds."""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def resource_path(relative_path: str) -> Path:
    """Return a bundled resource path for both source and PyInstaller builds."""

    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / relative_path
    return app_base_dir() / relative_path


def configure_logging() -> None:
    """Configure console and rolling file logging."""

    log_dir = app_base_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "abyss_bot.log"

    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<7} | {message}",
    )
    logger.add(
        log_file,
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<7} | {message}",
        encoding="utf-8",
        rotation="5 MB",
        retention=10,
    )
    logger.info(f"日志文件：{log_file}")


def pause_before_exit_if_frozen() -> None:
    """Keep the console open when the packaged exe is launched by double click."""

    if not getattr(sys, "frozen", False):
        return

    try:
        input("\n脚本已结束，按 Enter 关闭窗口...")
    except EOFError:
        pass


def read_positive_int(prompt: str, default: int) -> int:
    """Read a positive integer, falling back to default on blank or invalid input."""

    user_input = input(f"{prompt}（默认 {default}）：").strip()
    if not user_input:
        return default

    try:
        value = int(user_input)
    except ValueError:
        logger.warning(f"输入不是整数，使用默认值：{default}")
        return default

    if value <= 0:
        logger.warning(f"输入必须大于 0，使用默认值：{default}")
        return default

    return value
