from loguru import logger

from game_script.main import main, pause_before_exit_if_frozen


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
