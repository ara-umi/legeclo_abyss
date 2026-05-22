from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


def app_base_dir() -> Path:
    """返回源码运行和 PyInstaller 打包后都可用的程序目录。"""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def resource_path(relative_path: str) -> Path:
    """返回源码运行和 PyInstaller 打包后都可用的资源路径。"""

    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / relative_path
    return app_base_dir() / relative_path


def configure_logging() -> None:
    """配置控制台日志和滚动文件日志。"""

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
    """打包后的 exe 双击运行时，结束前暂停一下，避免窗口直接关闭。"""

    if not getattr(sys, "frozen", False):
        return

    try:
        input("\n脚本已结束，按 Enter 关闭窗口...")
    except EOFError:
        pass


def read_positive_int(prompt: str, default: int) -> int:
    """读取正整数，空输入或非法输入时使用默认值。"""

    user_input = input(f"{prompt}（默认 {default}，按 ENTER 直接使用默认）：").strip()
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


def read_int_in_range(prompt: str, default: int, *, min_value: int, max_value: int) -> int:
    """读取指定范围内的整数，空输入或非法输入时使用默认值。"""

    user_input = input(f"{prompt}（默认 {default}，按 ENTER 直接使用默认）：").strip()
    if not user_input:
        return default

    try:
        value = int(user_input)
    except ValueError:
        logger.warning(f"输入不是整数，使用默认值：{default}")
        return default

    if value < min_value or value > max_value:
        logger.warning(f"输入必须在 {min_value} 到 {max_value} 之间，使用默认值：{default}")
        return default

    return value
