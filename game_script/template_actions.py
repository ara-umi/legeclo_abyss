from __future__ import annotations

from pathlib import Path
from time import sleep

from loguru import logger

from game_script.vision import (
    TemplateMatch,
    click_screen_point,
    move_screen_point,
    wait_template_center,
)


def click_match(match: TemplateMatch, *, click_delay_seconds: float = 0.5) -> None:
    """Move to a template match center and click it after a short delay."""

    if click_delay_seconds < 0:
        raise ValueError("click_delay_seconds 不能小于 0")

    move_screen_point(match.center.x, match.center.y, duration=0.15)
    sleep(click_delay_seconds)
    click_screen_point(match.center.x, match.center.y, duration=0)


def wait_and_click_template(
    template_path: Path,
    *,
    template_name: str,
    scale: float,
    timeout_seconds: float = 20,
    threshold: float = 0.8,
    click_delay_seconds: float = 0.5,
) -> TemplateMatch | None:
    """Wait for a template to appear, then click its center."""

    logger.info(f"正在等待{template_name}")
    match = _wait_template_center_safely(
        template_path,
        template_name=template_name,
        scale=scale,
        timeout_seconds=timeout_seconds,
        threshold=threshold,
    )
    if match is None:
        return None

    logger.info(
        f"匹配到{template_name}，点击坐标：({match.center.x}, {match.center.y})，"
        f"匹配分数：{match.score:.4f}"
    )
    click_match(match, click_delay_seconds=click_delay_seconds)
    logger.info(f"已点击{template_name}")
    return match


def wait_template(
    template_path: Path,
    *,
    template_name: str,
    scale: float,
    timeout_seconds: float = 20,
    threshold: float = 0.8,
) -> TemplateMatch | None:
    """Wait for a template to appear without clicking it."""

    logger.info(f"正在等待{template_name}")
    match = _wait_template_center_safely(
        template_path,
        template_name=template_name,
        scale=scale,
        timeout_seconds=timeout_seconds,
        threshold=threshold,
    )
    if match is None:
        return None

    logger.info(
        f"匹配到{template_name}，中心坐标：({match.center.x}, {match.center.y})，"
        f"匹配分数：{match.score:.4f}"
    )
    return match


def _wait_template_center_safely(
    template_path: Path,
    *,
    template_name: str,
    scale: float,
    timeout_seconds: float,
    threshold: float,
) -> TemplateMatch | None:
    try:
        match = wait_template_center(
            template_path,
            timeout_seconds=timeout_seconds,
            interval_seconds=0.5,
            threshold=threshold,
            template_scale=scale,
        )
    except Exception as exc:
        logger.error(f"等待{template_name}失败：{exc}")
        return None

    if match is None:
        logger.error(f"等待{template_name}失败")
        return None

    return match
