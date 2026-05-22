from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from random import choice
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
    CHALLENGE_DIFFICULTY_POINTS,
    BUFF1_POINTS,
    BUFF_INFO_TEMPLATE,
    FINAL_BOSS_TEMPLATE,
    GIVE_UP_TEMPLATE,
    LEVEL_SELECT_TEMPLATE,
    MID_BOSS_TEMPLATE,
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


NORMAL_STAGE_NAME = "小怪关卡"
MID_BOSS_STAGE_NAME = "道中 BOSS 关卡"
FINAL_BOSS_STAGE_NAME = "BOSS 关卡"


def match_resolution() -> ScaledTemplateMatch | None:
    """匹配深渊主界面，并返回游戏窗口位置和缩放比例。"""

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
    challenge_difficulty: int = 0
    current_stage_number: int = 1
    entered_boss_battle_count: int = 0
    entered_final_boss_stage: bool = False

    @property
    def scale(self) -> float:
        return self.window_match.scale

    def reset_cycle_state(self) -> None:
        """重置一轮深渊的关卡进度和 BOSS 记录。"""

        self.current_stage_number = 1
        self.entered_boss_battle_count = 0
        self.entered_final_boss_stage = False

    def expected_stage_name(self) -> str:
        """根据当前关卡号判断当前是小怪关卡、mid boss 关卡还是 final boss 关卡。

        游戏规则很固定：非 5 的倍数是普通关；5、15、25 这种是 mid boss；
        10、20、30 这种 10 的倍数是 final boss。
        """

        if self.current_stage_number % 10 == 0:
            return FINAL_BOSS_STAGE_NAME
        if self.current_stage_number % 5 == 0:
            return MID_BOSS_STAGE_NAME
        return NORMAL_STAGE_NAME

    def expected_stage_template(self) -> tuple[str, Path]:
        """返回当前关卡类型和应该使用的模板，避免不同模板互相抢匹配分数。"""

        stage_name = self.expected_stage_name()
        if stage_name == NORMAL_STAGE_NAME:
            return stage_name, NORMAL_TEMPLATE
        if stage_name == MID_BOSS_STAGE_NAME:
            return stage_name, MID_BOSS_TEMPLATE
        return stage_name, FINAL_BOSS_TEMPLATE

    def prepare_one_reset_cycle(self) -> bool:
        """从深渊主界面进入本轮第一次强化/编成情报页。"""

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
        """持续战斗，直到本轮循环达到目标 BOSS 次数。"""

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
        """点击重置并确认放弃，开始下一轮深渊。"""

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
        """执行一场战斗，并回到下一个稳定的关卡入口。"""

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

        battle = self.wait_battle_button_after_sortie(
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

        if not self.confirm_final_boss_ok_if_needed():
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
        """从关卡选择页进入强化/编成情报页，并在成功后推进关卡状态。"""

        if stage_entry is None:
            stage_entry = self.wait_stable_stage_entry(timeout_seconds=30, threshold=0.8)
        if stage_entry is None:
            return False

        stage_name, match = stage_entry
        stage_number = self.current_stage_number

        logger.info(
            f"已确认第 {stage_number} 关 {stage_name} 入口，匹配中心：({match.center.x}, {match.center.y})，"
            f"匹配分数：{match.score:.4f}"
        )
        self.click_challenge_difficulty()

        buff_info = wait_template(
            BUFF_INFO_TEMPLATE,
            template_name="获得强化效果+简单编成情报",
            scale=self.scale,
            timeout_seconds=30,
            threshold=0.8,
        )
        if buff_info is None:
            return False

        # 只有确认进入下一页后才更新状态，避免点击失败时关卡号提前变化。
        if stage_name in (MID_BOSS_STAGE_NAME, FINAL_BOSS_STAGE_NAME):
            self.entered_boss_battle_count += 1
            logger.info(f"已进入 BOSS 战斗次数：{self.entered_boss_battle_count}")
        if stage_name == FINAL_BOSS_STAGE_NAME:
            self.entered_final_boss_stage = True
            logger.info("本场为 final boss 关卡，战斗结束后需要额外确认 OK")

        self.current_stage_number += 1
        logger.info(f"下一次将识别第 {self.current_stage_number} 关 {self.expected_stage_name()}")
        return True

    def click_challenge_difficulty(self) -> None:
        """按脚本参数点击 R、SR、SSR 三个固定挑战难度位置。"""

        difficulty, difficulty_name, offset_x, offset_y = self.resolve_challenge_difficulty()
        point = click_window_offset(self.window_match, offset_x, offset_y)
        logger.info(
            f"已点击挑战难度 {difficulty_name}，难度参数：{difficulty}，"
            f"点击坐标：({point.x}, {point.y})"
        )

    def resolve_challenge_difficulty(self) -> tuple[int, str, int, int]:
        """解析本次应该点击的挑战难度；参数为 0 时每关随机一次。"""

        difficulty = self.challenge_difficulty
        if difficulty == 0:
            difficulty = choice(tuple(CHALLENGE_DIFFICULTY_POINTS))

        difficulty_point = CHALLENGE_DIFFICULTY_POINTS.get(difficulty)
        if difficulty_point is None:
            logger.warning(f"未知挑战难度参数：{self.challenge_difficulty}，本次改为随机")
            difficulty = choice(tuple(CHALLENGE_DIFFICULTY_POINTS))
            difficulty_point = CHALLENGE_DIFFICULTY_POINTS[difficulty]

        difficulty_name, offset_x, offset_y = difficulty_point
        return difficulty, difficulty_name, offset_x, offset_y

    def click_buff_option(self) -> None:
        """点击默认的第一个 BUFF 固定位置。"""

        buff_name, offset_x, offset_y = BUFF1_POINTS
        point = click_window_offset(self.window_match, offset_x, offset_y)
        logger.info(f"已点击{buff_name}固定位置：({point.x}, {point.y})")

    def wait_battle_button_after_sortie(
        self,
        *,
        timeout_seconds: float,
        threshold: float,
    ) -> TemplateMatch | None:
        """出击后等待战斗按钮，兼容回复类 BUFF 额外弹出的 OK 窗口。"""

        logger.info("正在等待战斗按钮或回复类 BUFF 的 OK")
        deadline = monotonic() + timeout_seconds
        while True:
            # 出击后可能直接出现战斗按钮，也可能先弹出回复类 BUFF 的 OK 确认。
            screen = capture_screen()
            ok = find_template_center(
                OK_TEMPLATE,
                threshold=threshold,
                template_scale=self.scale,
                screen_image=screen,
            )
            if ok is not None:
                logger.info(
                    f"匹配到回复类 BUFF 的 OK，点击坐标：({ok.center.x}, {ok.center.y})，"
                    f"匹配分数：{ok.score:.4f}"
                )
                click_match(ok)
                logger.info("已点击回复类 BUFF 的 OK，继续等待战斗按钮")
                return self.wait_battle_button(
                    timeout_seconds=max(1, deadline - monotonic()),
                    threshold=threshold,
                )

            battle = find_template_center(
                BATTLE_TEMPLATE,
                threshold=threshold,
                template_scale=self.scale,
                screen_image=screen,
            )
            if battle is not None:
                logger.info(
                    f"匹配到战斗按钮，中心坐标：({battle.center.x}, {battle.center.y})，"
                    f"匹配分数：{battle.score:.4f}"
                )
                return battle

            remaining_seconds = deadline - monotonic()
            if remaining_seconds <= 0:
                logger.error("等待战斗按钮或回复类 BUFF 的 OK 失败")
                return None
            sleep(min(0.5, remaining_seconds))

    def wait_battle_button(self, *, timeout_seconds: float, threshold: float) -> TemplateMatch | None:
        """等待战斗按钮出现，不执行点击。"""

        return wait_template(
            BATTLE_TEMPLATE,
            template_name="战斗按钮",
            scale=self.scale,
            timeout_seconds=timeout_seconds,
            threshold=threshold,
        )

    def ensure_auto_battle_enabled(self) -> bool:
        """点击战斗按钮前，确保自动战斗已经开启。"""

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

    def confirm_final_boss_ok_if_needed(self) -> bool:
        """如果刚打完 final boss 关卡，就点击装备奖励后的 OK 确认。"""

        if not self.entered_final_boss_stage:
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

        self.entered_final_boss_stage = False
        return True

    def wait_stable_stage_entry(
        self,
        *,
        timeout_seconds: float = 30,
        threshold: float = 0.8,
        confirm_delay_seconds: float = 2,
    ) -> tuple[str, TemplateMatch] | None:
        """等待当前关卡入口出现两次，避免界面过渡时误点。"""

        first_stage_entry = self.wait_stage_entry(timeout_seconds=timeout_seconds, threshold=threshold)
        if first_stage_entry is None:
            return None

        first_stage_name, _ = first_stage_entry
        logger.info(f"首次匹配到第 {self.current_stage_number} 关 {first_stage_name}，等待 {confirm_delay_seconds:.1f}s 后二次确认")
        sleep(confirm_delay_seconds)

        stage_entry = self.wait_stage_entry(timeout_seconds=timeout_seconds, threshold=threshold)
        if stage_entry is None:
            return None

        stage_name, _ = stage_entry
        logger.info(f"二次确认匹配到第 {self.current_stage_number} 关 {stage_name}")
        return stage_entry

    def wait_stage_entry(
        self,
        *,
        timeout_seconds: float = 30,
        threshold: float = 0.8,
    ) -> tuple[str, TemplateMatch] | None:
        """等待当前关卡应该出现的入口，不再同时匹配全部关卡类型。"""

        expected_stage_name = self.expected_stage_name()
        logger.info(f"正在等待第 {self.current_stage_number} 关 {expected_stage_name}")
        deadline = monotonic() + timeout_seconds
        while True:
            stage_entry = self.find_stage_entry_once(threshold=threshold)
            if stage_entry is not None:
                stage_name, match = stage_entry
                logger.info(
                    f"匹配到第 {self.current_stage_number} 关 {stage_name}，中心坐标：({match.center.x}, {match.center.y})，"
                    f"匹配分数：{match.score:.4f}"
                )
                return stage_name, match

            remaining_seconds = deadline - monotonic()
            if remaining_seconds <= 0:
                logger.error(f"等待第 {self.current_stage_number} 关 {expected_stage_name} 失败")
                return None
            sleep(min(0.5, remaining_seconds))

    def find_stage_entry_once(self, *, threshold: float = 0.8) -> tuple[str, TemplateMatch] | None:
        """按当前关卡号只匹配一种入口模板。"""

        stage_name, stage_template = self.expected_stage_template()
        screen = capture_screen()
        match = find_template_center(
            stage_template,
            threshold=threshold,
            template_scale=self.scale,
            screen_image=screen,
        )
        if match is None:
            return None
        return stage_name, match
