from __future__ import annotations

import sys
from pathlib import Path
from time import monotonic, sleep

import pyautogui
from loguru import logger

from game_script.vision import (
    ScaledTemplateMatch,
    TemplateMatch,
    capture_screen,
    click_window_offset,
    find_scaled_template,
    find_template_center,
    wait_template_center,
)


def app_base_dir() -> Path:
    """返回程序运行目录。

    源码运行时是项目根目录；PyInstaller 打包后是 exe 所在目录。
    """

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def resource_path(relative_path: str) -> Path:
    """返回资源文件路径，兼容源码运行和 PyInstaller onefile。

    源码运行时，资源从项目根目录读取；PyInstaller onefile 运行时，资源会被
    解压到 sys._MEIPASS，必须从那里读取。
    """

    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / relative_path
    return app_base_dir() / relative_path


ABYSS_MAIN_TEMPLATE = resource_path("templates/深渊主界面.png")
START_BATTLE_TEMPLATE = resource_path("templates/编队&出击.png")
SORTIE_TEMPLATE = resource_path("templates/出击.png")
NORMAL_TEMPLATE = resource_path("templates/NORMAL.png")
BOSS_TEMPLATES = {
    "BOSS1": resource_path("templates/BOSS1.png"),
    "BOSS2": resource_path("templates/BOSS2.png"),
}
BUFF_INFO_TEMPLATE = resource_path("templates/获得强化效果+简单编成情报.png")
BATTLE_TEMPLATE = resource_path("templates/战斗.png")
AUTO_ON_TEMPLATE = resource_path("templates/自动开.png")
AUTO_OFF_TEMPLATE = resource_path("templates/自动关.png")
NEXT_TEMPLATE = resource_path("templates/NEXT.png")
LEVEL_SELECT_TEMPLATE = resource_path("templates/关卡选择.png")
OK_TEMPLATE = resource_path("templates/OK.png")
RESET_TEMPLATE = resource_path("templates/重置.png")
GIVE_UP_TEMPLATE = resource_path("templates/放弃.png")

DEFAULT_RESET_CYCLE_COUNT = 99
DEFAULT_BOSS_BATTLE_TARGET_COUNT = 2
BUFF_OPTION_OFFSET_X = 650
BUFF_OPTION_OFFSET_Y = 322
AUTO_BUTTON_THRESHOLD = 0.95
BATTLE_BUTTON_TIMEOUT_SECONDS = 60
BATTLE_TIMEOUT_SECONDS = 300

# 全局状态：当前重置循环内已经进入 BOSS 战斗的次数。点击 BOSS 入口后增加。
entered_boss_battle_count = 0

# 全局状态：当前这场战斗是否由 BOSS2 触发。BOSS2 战斗结束后需要额外点 OK。
entered_boss2_battle = False


def configure_logging() -> None:
    """配置 loguru 日志格式，同时写控制台和本地日志文件。"""

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
    """exe 模式下退出前等待回车，避免双击启动的终端窗口自动关闭。"""

    if not getattr(sys, "frozen", False):
        return

    try:
        input("\n脚本已结束，按 Enter 关闭窗口...")
    except EOFError:
        pass


def read_positive_int(prompt: str, default: int) -> int:
    """读取正整数输入；直接回车或输入非法值时使用默认值。"""

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


def click_match(match: TemplateMatch, *, click_delay_seconds: float = 0.5) -> None:
    """移动到匹配结果中心点并点击。

    click_delay_seconds 是点击前延时，默认等 0.5 秒，给游戏 UI 留一点稳定时间。
    """

    if click_delay_seconds < 0:
        raise ValueError("click_delay_seconds 不能小于 0")

    pyautogui.moveTo(match.center.x, match.center.y, duration=0.15)
    sleep(click_delay_seconds)
    pyautogui.click(match.center.x, match.center.y)


def wait_and_click_template(
    template_path: Path,
    *,
    template_name: str,
    scale: float,
    timeout_seconds: float = 20,
    threshold: float = 0.8,
    click_delay_seconds: float = 0.5,
) -> TemplateMatch | None:
    """等待一个模板出现，匹配成功后点击它。"""

    logger.info(f"正在等待{template_name}")
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
    """等待一个模板出现，只等待不点击。"""

    logger.info(f"正在等待{template_name}")
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

    logger.info(
        f"匹配到{template_name}，中心坐标：({match.center.x}, {match.center.y})，"
        f"匹配分数：{match.score:.4f}"
    )
    return match


def wait_stage_entry(
    scale: float,
    *,
    timeout_seconds: float = 30,
    threshold: float = 0.8,
) -> tuple[str, TemplateMatch] | None:
    """等待选关入口出现，入口可能是 NORMAL，也可能是 BOSS。"""

    logger.info("正在等待 NORMAL 或 BOSS")
    deadline = monotonic() + timeout_seconds
    while True:
        stage_entry = find_stage_entry_once(scale, threshold=threshold)
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


def find_stage_entry_once(scale: float, *, threshold: float = 0.8) -> tuple[str, TemplateMatch] | None:
    """对当前画面匹配一次 NORMAL/BOSS1/BOSS2，返回分数最高的入口。"""

    # 同一轮截图同时匹配所有入口，避免先等 NORMAL 时错过 BOSS。
    screen = capture_screen()
    normal = find_template_center(
        NORMAL_TEMPLATE,
        threshold=threshold,
        template_scale=scale,
        screen_image=screen,
    )
    matches = [("NORMAL", normal)] if normal is not None else []
    for boss_name, boss_template in BOSS_TEMPLATES.items():
        boss = find_template_center(
            boss_template,
            threshold=threshold,
            template_scale=scale,
            screen_image=screen,
        )
        if boss is not None:
            matches.append((boss_name, boss))

    if not matches:
        return None
    return max(matches, key=lambda item: item[1].score)


def wait_stable_stage_entry(
    scale: float,
    *,
    timeout_seconds: float = 30,
    threshold: float = 0.8,
    confirm_delay_seconds: float = 2,
) -> tuple[str, TemplateMatch] | None:
    """等待 NORMAL/BOSS 入口稳定出现，二次确认成功后返回第二次匹配结果。"""

    first_stage_entry = wait_stage_entry(scale, timeout_seconds=timeout_seconds, threshold=threshold)
    if first_stage_entry is None:
        return None

    first_stage_name, _ = first_stage_entry
    logger.info(f"首次匹配到{first_stage_name}，等待 {confirm_delay_seconds:.1f}s 后二次确认")
    sleep(confirm_delay_seconds)

    stage_entry = wait_stage_entry(scale, timeout_seconds=timeout_seconds, threshold=threshold)
    if stage_entry is None:
        return None

    stage_name, _ = stage_entry
    logger.info(f"二次确认匹配到{stage_name}")
    return stage_entry


def enter_buff_info_from_stage_selection(
    scale: float,
    stage_entry: tuple[str, TemplateMatch] | None = None,
) -> bool:
    """从 NORMAL/BOSS 选关入口进入强化效果和编成情报界面。"""

    global entered_boss2_battle, entered_boss_battle_count

    if stage_entry is None:
        stage_entry = wait_stable_stage_entry(scale, timeout_seconds=30, threshold=0.8)
    if stage_entry is None:
        return False

    stage_name, match = stage_entry
    if stage_name.startswith("BOSS"):
        entered_boss_battle_count += 1
        logger.info(f"已进入 BOSS 战斗次数：{entered_boss_battle_count}")
    if stage_name == "BOSS2":
        entered_boss2_battle = True
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
        scale=scale,
        timeout_seconds=30,
        threshold=0.8,
    )
    return buff_info is not None


def click_buff_option(window_match: ScaledTemplateMatch) -> None:
    """点击强化效果和编成情报界面里的固定位置。"""

    point = click_window_offset(window_match, BUFF_OPTION_OFFSET_X, BUFF_OPTION_OFFSET_Y)
    logger.info(f"已点击固定位置：({point.x}, {point.y})")


def ensure_auto_battle_enabled(scale: float) -> bool:
    """确保自动战斗处于开启状态。"""

    logger.info("正在检测自动开")
    auto_on = wait_template_center(
        AUTO_ON_TEMPLATE,
        timeout_seconds=2,
        interval_seconds=0.3,
        threshold=AUTO_BUTTON_THRESHOLD,
        template_scale=scale,
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
        template_scale=scale,
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
        template_scale=scale,
    )
    if auto_on is None:
        logger.error("开启自动战斗失败")
        return False

    logger.info(f"已开启自动战斗，匹配分数：{auto_on.score:.4f}")
    return True


def run_battle_cycle(window_match: ScaledTemplateMatch, index: int) -> tuple[str, TemplateMatch] | None:
    """执行一次从强化效果界面出击，到回到 NORMAL/BOSS 选关界面的流程。"""

    scale = window_match.scale
    logger.info(f"开始第 {index} 次战斗流程")

    click_buff_option(window_match)

    sortie = wait_and_click_template(
        SORTIE_TEMPLATE,
        template_name="出击按钮",
        scale=scale,
        timeout_seconds=20,
        threshold=0.8,
    )
    if sortie is None:
        return None

    battle = wait_template(
        BATTLE_TEMPLATE,
        template_name="战斗按钮",
        scale=scale,
        timeout_seconds=BATTLE_BUTTON_TIMEOUT_SECONDS,
        threshold=0.8,
    )
    if battle is None:
        return None

    if not ensure_auto_battle_enabled(scale):
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
        scale=scale,
        timeout_seconds=BATTLE_TIMEOUT_SECONDS,
        threshold=0.8,
        click_delay_seconds=2.0,
    )
    if next_button is None:
        return None

    level_select = wait_and_click_template(
        LEVEL_SELECT_TEMPLATE,
        template_name="关卡选择",
        scale=scale,
        timeout_seconds=30,
        threshold=0.8,
        click_delay_seconds=2.0,
    )
    if level_select is None:
        return None

    # BOSS2 结束后会先弹 OK，必须先处理掉，才能继续检测 NORMAL/BOSS 入口。
    if not confirm_boss2_ok_if_needed(scale):
        return None

    # 战斗结束后会回到选关界面。这里二次确认入口已经稳定，但不在这里点击。
    stage_entry = wait_stable_stage_entry(scale, timeout_seconds=30, threshold=0.8)
    if stage_entry is None:
        return None

    logger.info(f"第 {index} 次战斗流程完成")
    return stage_entry


def prepare_one_reset_cycle(scale: float) -> bool:
    """从主界面进入一次重置循环的首次强化效果和编成情报界面。"""

    start_battle = wait_and_click_template(
        START_BATTLE_TEMPLATE,
        template_name="编队出击按钮",
        scale=scale,
        timeout_seconds=30,
        threshold=0.8,
    )
    if start_battle is None:
        return False

    sortie = wait_and_click_template(
        SORTIE_TEMPLATE,
        template_name="出击按钮",
        scale=scale,
        timeout_seconds=20,
        threshold=0.8,
    )
    if sortie is None:
        return False

    return enter_buff_info_from_stage_selection(scale)


def run_until_boss_target(window_match: ScaledTemplateMatch, boss_battle_target_count: int) -> bool:
    """持续战斗，直到当前循环完成指定次数的 BOSS 战斗。"""

    cycle_index = 1
    while True:
        stage_entry = run_battle_cycle(window_match, cycle_index)
        if stage_entry is None:
            return False

        if entered_boss_battle_count >= boss_battle_target_count:
            logger.info(f"已完成当前循环第 {entered_boss_battle_count} 次 BOSS 战斗")
            return True

        if not enter_buff_info_from_stage_selection(window_match.scale, stage_entry=stage_entry):
            return False

        cycle_index += 1


def confirm_boss2_ok_if_needed(scale: float) -> bool:
    """如果刚完成的是 BOSS2 战斗，则等待并点击 OK。"""

    global entered_boss2_battle

    if not entered_boss2_battle:
        return True

    ok = wait_and_click_template(
        OK_TEMPLATE,
        template_name="OK",
        scale=scale,
        timeout_seconds=30,
        threshold=0.8,
    )
    if ok is None:
        return False

    entered_boss2_battle = False
    return True


def reset_abyss(scale: float) -> bool:
    """执行一次深渊重置：点击重置，再点击放弃确认。"""

    reset = wait_and_click_template(
        RESET_TEMPLATE,
        template_name="重置",
        scale=scale,
        timeout_seconds=30,
        threshold=0.8,
    )
    if reset is None:
        return False

    give_up = wait_and_click_template(
        GIVE_UP_TEMPLATE,
        template_name="放弃",
        scale=scale,
        timeout_seconds=5,
        threshold=0.8,
    )
    return give_up is not None


def match_resolution() -> ScaledTemplateMatch | None:
    """匹配深渊主界面，返回窗口位置和缩放比例。"""

    logger.info("正在匹配分辨率，请将界面停留在深渊迷宫主界面（能看到 編隊&出擊 的界面）")
    try:
        match = find_scaled_template(
            ABYSS_MAIN_TEMPLATE,
            threshold=0.7,
            min_scale=0.5,
            max_scale=4.0,
            scale_step=0.01,
        )
    except Exception as exc:
        logger.error(f"匹配分辨率失败：{exc}")
        return None

    if match is None:
        logger.error("匹配分辨率失败")
        return None

    logger.info(f"匹配到分辨率，当前缩放比例：{match.scale * 100:.2f}%")
    return match


def main() -> int:
    """游戏脚本主入口：打指定 BOSS 次数后重置，并重复指定循环次数。"""

    global entered_boss2_battle, entered_boss_battle_count

    print("""
传奇四叶草自动刷深渊脚本 v1.0
启动时请停留在深渊迷宫主界面（能看到 編隊&出擊 的界面），请先自行配置好分队
兼容不同分辨率，只要是电脑上运行能看到完整的游戏界面即可，手机、浏览器应该都可以
有问题请联系：532990165@qq.com
""")
    configure_logging()
    reset_cycle_count = read_positive_int("请输入重置循环次数", DEFAULT_RESET_CYCLE_COUNT)
    boss_battle_target_count = read_positive_int("请输入每个循环遭遇 BOSS 次数", DEFAULT_BOSS_BATTLE_TARGET_COUNT)
    logger.info(f"脚本参数：重置循环次数={reset_cycle_count}，每循环 BOSS 次数={boss_battle_target_count}")

    window_match = match_resolution()
    if window_match is None:
        return 1

    for reset_cycle_index in range(1, reset_cycle_count + 1):
        entered_boss_battle_count = 0
        entered_boss2_battle = False
        logger.info(
            f"开始第 {reset_cycle_index}/{reset_cycle_count} 个重置循环，"
            f"目标 BOSS 次数：{boss_battle_target_count}"
        )

        if not prepare_one_reset_cycle(window_match.scale):
            return 1

        if not run_until_boss_target(window_match, boss_battle_target_count):
            return 1

        if not reset_abyss(window_match.scale):
            return 1

        logger.info(f"第 {reset_cycle_index}/{reset_cycle_count} 个重置循环完成")

    logger.info("全部循环完成，脚本结束")
    return 0


if __name__ == "__main__":
    exit_code = 1
    try:
        exit_code = main()
    except KeyboardInterrupt:
        logger.warning("用户中断脚本")
    except Exception:
        logger.exception("脚本发生未处理异常")
    finally:
        pause_before_exit_if_frozen()

    raise SystemExit(exit_code)
