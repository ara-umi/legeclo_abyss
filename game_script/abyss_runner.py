from __future__ import annotations

from dataclasses import dataclass
from time import monotonic, sleep

from loguru import logger

from game_script.settings import (
    ABYSS_MAIN_TEMPLATE,
    AUTO_BUTTON_THRESHOLD,
    AUTO_OFF_TEMPLATE,
    AUTO_ON_TEMPLATE,
    BATTLE_BUTTON_TIMEOUT_SECONDS,
    BATTLE_TEMPLATE,
    BATTLE_TIMEOUT_SECONDS,
    BOSS_TEMPLATES,
    BUFF_INFO_TEMPLATE,
    BUFF_OPTION_OFFSET_X,
    BUFF_OPTION_OFFSET_Y,
    GIVE_UP_TEMPLATE,
    LEVEL_SELECT_TEMPLATE,
    NEXT_TEMPLATE,
    NORMAL_TEMPLATE,
    OK_TEMPLATE,
    RESET_TEMPLATE,
    SORTIE_TEMPLATE,
    START_BATTLE_TEMPLATE,
)
from game_script.template_actions import click_match, wait_and_click_template, wait_template
from game_script.vision import (
    ScaledTemplateMatch,
    TemplateMatch,
    capture_screen,
    click_window_offset,
    find_scaled_template_coarse_to_fine,
    find_template_center,
    wait_template_center,
)


def match_resolution() -> ScaledTemplateMatch | None:
    """Match the abyss main screen and return its location and scale."""

    logger.info("正在匹配分辨率，请将界面停留在深渊迷宫主界面（能看到 编队&出击 的界面）")
    try:
        match = find_scaled_template_coarse_to_fine(
            ABYSS_MAIN_TEMPLATE,
            threshold=0.7,
            min_scale=0.5,
            max_scale=4.0,
            coarse_scale_step=0.1,
            fine_scale_step=0.01,
            fine_scale_window=0.1,
            coarse_downsample=1.0,
        )
    except Exception as exc:
        logger.error(f"匹配分辨率失败：{exc}")
        return None

    if match is None:
        logger.error("匹配分辨率失败")
        return None

    logger.info(f"匹配到分辨率，当前缩放比例：{match.scale * 100:.2f}%")
    logger.info(
        "分辨率匹配尺寸："
        f"素材原始大小={match.template_size[0]}x{match.template_size[1]}，"
        f"换算实际大小={match.matched_size[0]}x{match.matched_size[1]}"
    )
    return match


@dataclass
class AbyssRunner:
    window_match: ScaledTemplateMatch
    entered_boss_battle_count: int = 0
    entered_boss2_battle: bool = False

    @property
    def scale(self) -> float:
        return self.window_match.scale

    def reset_cycle_state(self) -> None:
        self.entered_boss_battle_count = 0
        self.entered_boss2_battle = False

    def prepare_one_reset_cycle(self) -> bool:
        """Enter the first buff info screen from the abyss main screen."""

        start_battle = wait_and_click_template(
            START_BATTLE_TEMPLATE,
            template_name="编队&出击按钮",
            scale=self.scale,
            timeout_seconds=30,
            threshold=0.8,
        )
        if start_battle is None:
            return False

        sortie = wait_and_click_template(
            SORTIE_TEMPLATE,
            template_name="出击按钮",
            scale=self.scale,
            timeout_seconds=20,
            threshold=0.8,
        )
        if sortie is None:
            return False

        return self.enter_buff_info_from_stage_selection()

    def run_until_boss_target(self, boss_battle_target_count: int) -> bool:
        """Keep battling until this reset cycle reaches the target BOSS count."""

        cycle_index = 1
        while True:
            stage_entry = self.run_battle_cycle(cycle_index)
            if stage_entry is None:
                return False

            if self.entered_boss_battle_count >= boss_battle_target_count:
                logger.info(f"已完成当前循环第 {self.entered_boss_battle_count} 次 BOSS 战斗")
                return True

            if not self.enter_buff_info_from_stage_selection(stage_entry=stage_entry):
                return False

            cycle_index += 1

    def reset_abyss(self) -> bool:
        """Reset the abyss by clicking reset, then abandon confirmation."""

        reset = wait_and_click_template(
            RESET_TEMPLATE,
            template_name="重置",
            scale=self.scale,
            timeout_seconds=30,
            threshold=0.8,
        )
        if reset is None:
            return False

        give_up = wait_and_click_template(
            GIVE_UP_TEMPLATE,
            template_name="放弃",
            scale=self.scale,
            timeout_seconds=5,
            threshold=0.8,
        )
        return give_up is not None

    def run_battle_cycle(self, index: int) -> tuple[str, TemplateMatch] | None:
        """Run one battle and return to a stable NORMAL/BOSS stage entry."""

        logger.info(f"开始第 {index} 次战斗流程")
        self.click_buff_option()

        sortie = wait_and_click_template(
            SORTIE_TEMPLATE,
            template_name="出击按钮",
            scale=self.scale,
            timeout_seconds=20,
            threshold=0.8,
        )
        if sortie is None:
            return None

        battle = wait_template(
            BATTLE_TEMPLATE,
            template_name="战斗按钮",
            scale=self.scale,
            timeout_seconds=BATTLE_BUTTON_TIMEOUT_SECONDS,
            threshold=0.8,
        )
        if battle is None:
            return None

        if not self.ensure_auto_battle_enabled():
            return None

        logger.info(
            f"正在点击战斗按钮，点击坐标：({battle.center.x}, {battle.center.y})，"
            f"匹配分数：{battle.score:.4f}"
        )
        click_match(battle)
        logger.info("已点击战斗按钮")

        next_button = wait_and_click_template(
            NEXT_TEMPLATE,
            template_name="NEXT",
            scale=self.scale,
            timeout_seconds=BATTLE_TIMEOUT_SECONDS,
            threshold=0.8,
            click_delay_seconds=2.0,
        )
        if next_button is None:
            return None

        level_select = wait_and_click_template(
            LEVEL_SELECT_TEMPLATE,
            template_name="关卡选择",
            scale=self.scale,
            timeout_seconds=30,
            threshold=0.8,
            click_delay_seconds=2.0,
        )
        if level_select is None:
            return None

        if not self.confirm_boss2_ok_if_needed():
            return None

        stage_entry = self.wait_stable_stage_entry(timeout_seconds=30, threshold=0.8)
        if stage_entry is None:
            return None

        logger.info(f"第 {index} 次战斗流程完成")
        return stage_entry

    def enter_buff_info_from_stage_selection(
        self,
        stage_entry: tuple[str, TemplateMatch] | None = None,
    ) -> bool:
        """Enter buff and formation info from a NORMAL/BOSS stage entry."""

        if stage_entry is None:
            stage_entry = self.wait_stable_stage_entry(timeout_seconds=30, threshold=0.8)
        if stage_entry is None:
            return False

        stage_name, match = stage_entry
        if stage_name.startswith("BOSS"):
            self.entered_boss_battle_count += 1
            logger.info(f"已进入 BOSS 战斗次数：{self.entered_boss_battle_count}")
        if stage_name == "BOSS2":
            self.entered_boss2_battle = True
            logger.info("本场为 BOSS2 战斗，战斗结束后需要额外确认 OK")

        logger.info(
            f"正在点击{stage_name}，点击坐标：({match.center.x}, {match.center.y})，"
            f"匹配分数：{match.score:.4f}"
        )
        click_match(match)
        logger.info(f"已点击{stage_name}")

        buff_info = wait_template(
            BUFF_INFO_TEMPLATE,
            template_name="获得强化效果+简单编成情报",
            scale=self.scale,
            timeout_seconds=30,
            threshold=0.8,
        )
        return buff_info is not None

    def click_buff_option(self) -> None:
        """Click the fixed buff choice position on the buff info screen."""

        point = click_window_offset(self.window_match, BUFF_OPTION_OFFSET_X, BUFF_OPTION_OFFSET_Y)
        logger.info(f"已点击固定位置：({point.x}, {point.y})")

    def ensure_auto_battle_enabled(self) -> bool:
        """Ensure auto battle is enabled before clicking the battle button."""

        logger.info("正在检测自动开")
        auto_on = wait_template_center(
            AUTO_ON_TEMPLATE,
            timeout_seconds=2,
            interval_seconds=0.3,
            threshold=AUTO_BUTTON_THRESHOLD,
            template_scale=self.scale,
        )
        if auto_on is not None:
            logger.info(f"已检测到自动开，匹配分数：{auto_on.score:.4f}")
            return True

        logger.info("未检测到自动开，正在检测自动关")
        auto_off = wait_template_center(
            AUTO_OFF_TEMPLATE,
            timeout_seconds=5,
            interval_seconds=0.3,
            threshold=AUTO_BUTTON_THRESHOLD,
            template_scale=self.scale,
        )
        if auto_off is None:
            logger.error("检测自动关失败")
            return False

        logger.info(
            f"匹配到自动关，点击坐标：({auto_off.center.x}, {auto_off.center.y})，"
            f"匹配分数：{auto_off.score:.4f}"
        )
        click_match(auto_off)
        logger.info("已点击自动关，等待自动开")

        auto_on = wait_template_center(
            AUTO_ON_TEMPLATE,
            timeout_seconds=5,
            interval_seconds=0.3,
            threshold=AUTO_BUTTON_THRESHOLD,
            template_scale=self.scale,
        )
        if auto_on is None:
            logger.error("开启自动战斗失败")
            return False

        logger.info(f"已开启自动战斗，匹配分数：{auto_on.score:.4f}")
        return True

    def confirm_boss2_ok_if_needed(self) -> bool:
        """Click OK after BOSS2 if that battle was entered in this cycle."""

        if not self.entered_boss2_battle:
            return True

        ok = wait_and_click_template(
            OK_TEMPLATE,
            template_name="OK",
            scale=self.scale,
            timeout_seconds=30,
            threshold=0.8,
        )
        if ok is None:
            return False

        self.entered_boss2_battle = False
        return True

    def wait_stable_stage_entry(
        self,
        *,
        timeout_seconds: float = 30,
        threshold: float = 0.8,
        confirm_delay_seconds: float = 2,
    ) -> tuple[str, TemplateMatch] | None:
        """Wait for NORMAL/BOSS entry to appear twice, avoiding transient UI."""

        first_stage_entry = self.wait_stage_entry(timeout_seconds=timeout_seconds, threshold=threshold)
        if first_stage_entry is None:
            return None

        first_stage_name, _ = first_stage_entry
        logger.info(f"首次匹配到{first_stage_name}，等待 {confirm_delay_seconds:.1f}s 后二次确认")
        sleep(confirm_delay_seconds)

        stage_entry = self.wait_stage_entry(timeout_seconds=timeout_seconds, threshold=threshold)
        if stage_entry is None:
            return None

        stage_name, _ = stage_entry
        logger.info(f"二次确认匹配到{stage_name}")
        return stage_entry

    def wait_stage_entry(
        self,
        *,
        timeout_seconds: float = 30,
        threshold: float = 0.8,
    ) -> tuple[str, TemplateMatch] | None:
        """Wait for a NORMAL/BOSS stage entry to appear."""

        logger.info("正在等待 NORMAL 或 BOSS")
        deadline = monotonic() + timeout_seconds
        while True:
            stage_entry = self.find_stage_entry_once(threshold=threshold)
            if stage_entry is not None:
                stage_name, match = stage_entry
                logger.info(
                    f"匹配到{stage_name}，中心坐标：({match.center.x}, {match.center.y})，"
                    f"匹配分数：{match.score:.4f}"
                )
                return stage_name, match

            remaining_seconds = deadline - monotonic()
            if remaining_seconds <= 0:
                logger.error("等待 NORMAL 或 BOSS 失败")
                return None
            sleep(min(0.5, remaining_seconds))

    def find_stage_entry_once(self, *, threshold: float = 0.8) -> tuple[str, TemplateMatch] | None:
        """Find the best NORMAL/BOSS1/BOSS2 match in one screenshot."""

        screen = capture_screen()
        normal = find_template_center(
            NORMAL_TEMPLATE,
            threshold=threshold,
            template_scale=self.scale,
            screen_image=screen,
        )
        matches = [("NORMAL", normal)] if normal is not None else []
        for boss_name, boss_template in BOSS_TEMPLATES.items():
            boss = find_template_center(
                boss_template,
                threshold=threshold,
                template_scale=self.scale,
                screen_image=screen,
            )
            if boss is not None:
                matches.append((boss_name, boss))

        if not matches:
            return None
        return max(matches, key=lambda item: item[1].score)
