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
传奇四叶草自动刷深渊脚本 v1.0
启动时请停留在深渊迷宫主界面（能看到 编队&出击 的界面），请先自行配置好阵容
兼容不同分辨率，只要是电脑上运行能看到完整的游戏界面即可（不要让小黑窗遮挡游戏界面），模拟器、浏览器都可以
有问题请联系：32990165@qq.com
"""


@dataclass(frozen=True)
class BotOptions:
    reset_cycle_count: int
    boss_battle_target_count: int
