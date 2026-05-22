from __future__ import annotations

from loguru import logger

from game_script.abyss_runner import AbyssRunner, match_resolution
from game_script.runtime import (
    configure_logging,
    pause_before_exit_if_frozen,
    read_int_in_range,
    read_positive_int,
)
from game_script.settings import (
    DEFAULT_BOSS_BATTLE_TARGET_COUNT,
    DEFAULT_CHALLENGE_DIFFICULTY,
    DEFAULT_RESET_CYCLE_COUNT,
    INTRO_TEXT,
    BotOptions,
)


def read_bot_options() -> BotOptions:
    return BotOptions(
        reset_cycle_count=read_positive_int("请输入循环次数", DEFAULT_RESET_CYCLE_COUNT),
        boss_battle_target_count=read_positive_int(
            "请输入每次循环遭遇 BOSS 次数（5 关 1 BOSS）",
            DEFAULT_BOSS_BATTLE_TARGET_COUNT,
        ),
        challenge_difficulty=read_int_in_range(
            "请选择 BUFF 等级（即打第几个门）：0：随机 1：R 2：SR 3：SSR",
            DEFAULT_CHALLENGE_DIFFICULTY,
            min_value=0,
            max_value=3,
        ),
    )


def main() -> int:
    """主入口：读取运行参数、匹配游戏窗口，并执行深渊重置循环。"""

    print(INTRO_TEXT)
    configure_logging()
    options = read_bot_options()

    window_match = match_resolution()
    if window_match is None:
        return 1

    runner = AbyssRunner(window_match, challenge_difficulty=options.challenge_difficulty)
    for reset_cycle_index in range(1, options.reset_cycle_count + 1):
        runner.reset_cycle_state()
        logger.info(
            f"开始第 {reset_cycle_index}/{options.reset_cycle_count} 次循环，"
            f"目标 BOSS 次数：{options.boss_battle_target_count}，"
            f"挑战难度参数：{options.challenge_difficulty}"
        )

        if not runner.prepare_one_reset_cycle():
            return 1

        if not runner.run_until_boss_target(options.boss_battle_target_count):
            return 1

        if not runner.reset_abyss():
            return 1

        logger.info(f"第 {reset_cycle_index}/{options.reset_cycle_count} 次循环完成")

    logger.info("达到循环次数，脚本结束")
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
