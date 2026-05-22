from __future__ import annotations

from dataclasses import dataclass

from game_script.runtime import resource_path


ABYSS_MAIN_TEMPLATE = resource_path("templates/深渊主界面.png")
START_BATTLE_TEMPLATE = resource_path("templates/编队&出击.png")
SORTIE_TEMPLATE = resource_path("templates/出击.png")
NORMAL_TEMPLATE = resource_path("templates/NORMAL.png")
MID_BOSS_TEMPLATE = resource_path("templates/MID_BOSS.png")
FINAL_BOSS_TEMPLATE = resource_path("templates/FINAL_BOSS.png")
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
DEFAULT_CHALLENGE_DIFFICULTY = 0

# 固定位置坐标都是基于模板分辨率来进行的
BUFF1_POINTS = ("BUFF1", 650, 322)
CHALLENGE_DIFFICULTY_POINTS = {
    1: ("R", 346, 376),
    2: ("SR", 637, 376),
    3: ("SSR", 930, 376),
}

AUTO_BUTTON_THRESHOLD = 0.9
BATTLE_BUTTON_TIMEOUT_SECONDS = 60
BATTLE_TIMEOUT_SECONDS = 300

INTRO_TEXT = """
========================================
  传奇四叶草 深渊自动脚本 v1.1
========================================

启动前请确认：
- 游戏停留在「深渊迷宫主界面」（即可以看到「编队&出击」的界面），画面完整可见（不要有任何遮挡，包括启动时的小黑窗）
- 战斗已重置，编队已配置完成（编队里的顺序就是行动顺序，你也可以手动进一次战斗调一下顺序，这样编队里也会变成你调的顺序），脚本会自动开启自动战斗

支持环境：
- 不同分辨率的模拟器/浏览器，推荐分辨率是 720P 或 1080P（720P 即游戏画面截图像素尺寸是 1280x720），太大或太小无法保证能正常运行
- 理论上主屏副屏皆可正常运行，如果出现问题，请尽可能放在主屏或使用单屏

问题反馈：532990165@qq.com，或者找群聊里那个头像是红中的
"""


@dataclass(frozen=True)
class BotOptions:
    reset_cycle_count: int
    boss_battle_target_count: int
    challenge_difficulty: int
