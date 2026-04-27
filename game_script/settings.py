from __future__ import annotations

from dataclasses import dataclass

from game_script.runtime import resource_path


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

AUTO_BUTTON_THRESHOLD = 0.9
BATTLE_BUTTON_TIMEOUT_SECONDS = 60
BATTLE_TIMEOUT_SECONDS = 300

INTRO_TEXT = """
========================================
  传奇四叶草 深渊自动脚本 v1.0
========================================

启动前请确认：
- 游戏停留在「深渊迷宫主界面」（即可以看到「编队&出击」的界面），画面完整可见（不要有任何遮挡，包括启动时的小黑窗）
- 战斗已重置，阵容已配置完成（脚本会自动开启自动战斗）

支持环境：
- 不同分辨率的模拟器/浏览器，推荐分辨率是 720P 或 1080P（720P 即游戏画面截图是 1280x720），太大或太小无法保证能正常运行
- 主屏副屏皆可正常运行

问题反馈：532990165@qq.com
"""


@dataclass(frozen=True)
class BotOptions:
    reset_cycle_count: int
    boss_battle_target_count: int
