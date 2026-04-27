from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from time import monotonic, sleep
from typing import Iterable


def _enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except OSError:
        return
    except Exception:
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


_enable_dpi_awareness()

import cv2
import mss
import numpy as np
import pyautogui
from loguru import logger


SUPPORTED_TEMPLATE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


@dataclass(frozen=True)
class Point:
    """屏幕坐标点，后续可以直接交给点击逻辑使用。"""

    x: int
    y: int


@dataclass(frozen=True)
class TemplateMatch:
    """模板匹配结果，保留调试需要的模板名、坐标和相似度。"""

    template_path: Path
    center: Point
    top_left: Point
    bottom_right: Point
    score: float


@dataclass(frozen=True)
class ScaledTemplateMatch:
    """带缩放比例的模板匹配结果，用于跨分辨率定位游戏界面。"""

    center: Point
    top_left: Point
    bottom_right: Point
    score: float
    scale: float
    template_size: tuple[int, int]
    matched_size: tuple[int, int]
    template_path: Path | None = None


def capture_screen(region: dict[str, int] | None = None) -> np.ndarray:
    """截取屏幕并返回 OpenCV 使用的 BGR 图像。

    region 为空时截取整个虚拟桌面；不为空时只截取指定区域。
    region 格式示例：{"left": 0, "top": 0, "width": 800, "height": 600}
    """

    with mss.MSS() as screenshot_tool:
        monitor = region or screenshot_tool.monitors[0]
        screenshot = screenshot_tool.grab(monitor)

    # mss 返回 BGRA，OpenCV 模板匹配通常使用 BGR 或灰度图，这里先去掉 alpha 通道。
    return cv2.cvtColor(np.array(screenshot), cv2.COLOR_BGRA2BGR)


def scale_image(image: np.ndarray, scale: float) -> np.ndarray:
    """按比例缩放图片，返回新的 OpenCV 图像。

    scale 是“目标尺寸 / 原始尺寸”。比如模板是 100x50，scale=1.8 后就是
    180x90。这个函数只负责缩放，不负责读取文件和缓存。
    """

    if scale <= 0:
        raise ValueError("scale 必须大于 0")

    image_height, image_width = image.shape[:2]
    resized_width = round(image_width * scale)
    resized_height = round(image_height * scale)
    if resized_width <= 0 or resized_height <= 0:
        raise ValueError("缩放后的图片尺寸无效")

    # scale=1 时也返回 copy，避免调用方误改原图或缓存里的图。
    if resized_width == image_width and resized_height == image_height:
        return image.copy()

    # 缩小时 INTER_AREA 更稳，放大时 INTER_CUBIC 的边缘质量更好。
    interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    return cv2.resize(image, (resized_width, resized_height), interpolation=interpolation)


def load_scaled_template(template_path: str | Path, scale: float, *, use_cache: bool = True) -> np.ndarray:
    """读取模板并按比例缩放，默认缓存缩放结果。

    点击阶段会反复匹配同一批小模板，缓存可以避免每次都重新读取和缩放图片。
    缓存 key 带上文件修改时间和文件大小，所以模板文件被替换后会自动重新生成。
    """

    path = Path(template_path)
    normalized_scale = round(scale, 4)
    if not use_cache:
        return scale_image(_read_image(path), normalized_scale)

    file_stat = path.stat()
    cached_image = _load_scaled_template_cached(
        str(path.resolve()),
        normalized_scale,
        file_stat.st_mtime_ns,
        file_stat.st_size,
    )
    # lru_cache 返回的是同一个 ndarray 对象，给调用方 copy，避免缓存被意外污染。
    return cached_image.copy()


def find_scaled_template(
    template: str | Path | np.ndarray,
    *,
    threshold: float = 0.85,
    screen_image: np.ndarray | None = None,
    region: dict[str, int] | None = None,
    min_scale: float = 0.5,
    max_scale: float = 2.0,
    scale_step: float = 0.02,
) -> ScaledTemplateMatch | None:
    """在当前画面中查找可能被缩放过的模板，并返回实际缩放比例。

    template 可以是模板图片路径，也可以是已经读取好的 OpenCV BGR 图像。
    scale 表示“实际画面里的尺寸 / 模板图片原始尺寸”，后续可以用它把模板坐标
    映射到真实屏幕坐标。
    """

    if not 0 <= threshold <= 1:
        raise ValueError("threshold 必须在 0 到 1 之间")
    if min_scale <= 0 or max_scale <= 0:
        raise ValueError("min_scale 和 max_scale 必须大于 0")
    if min_scale > max_scale:
        raise ValueError("min_scale 不能大于 max_scale")
    if scale_step <= 0:
        raise ValueError("scale_step 必须大于 0")

    template_bgr, template_path = _load_template_image(template)
    screen_bgr = screen_image if screen_image is not None else capture_screen(region)
    offset_x = int(region["left"]) if screen_image is None and region else 0
    offset_y = int(region["top"]) if screen_image is None and region else 0

    screen_gray = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
    template_gray = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)
    original_height, original_width = template_gray.shape[:2]

    best_match: ScaledTemplateMatch | None = None
    for scale in _iter_scales(min_scale=min_scale, max_scale=max_scale, scale_step=scale_step):
        resized_width = round(original_width * scale)
        resized_height = round(original_height * scale)
        if resized_width <= 0 or resized_height <= 0:
            continue
        if resized_width > screen_gray.shape[1] or resized_height > screen_gray.shape[0]:
            continue

        # 缩小时用 INTER_AREA 更干净，放大时用 INTER_CUBIC 保留边缘细节。
        interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
        resized_template_gray = cv2.resize(
            template_gray,
            (resized_width, resized_height),
            interpolation=interpolation,
        )

        match_score, match_location = _match_gray_images(
            screen_gray=screen_gray,
            template_gray=resized_template_gray,
        )
        if best_match is not None and match_score <= best_match.score:
            continue

        left = int(match_location[0]) + offset_x
        top = int(match_location[1]) + offset_y
        right = left + resized_width
        bottom = top + resized_height
        best_match = ScaledTemplateMatch(
            center=Point(x=left + resized_width // 2, y=top + resized_height // 2),
            top_left=Point(x=left, y=top),
            bottom_right=Point(x=right, y=bottom),
            score=match_score,
            scale=scale,
            template_size=(original_width, original_height),
            matched_size=(resized_width, resized_height),
            template_path=template_path,
        )

    if best_match is None or best_match.score < threshold:
        return None
    return best_match


def find_scaled_template_coarse_to_fine(
    template: str | Path | np.ndarray,
    *,
    threshold: float = 0.85,
    screen_image: np.ndarray | None = None,
    region: dict[str, int] | None = None,
    min_scale: float = 0.5,
    max_scale: float = 2.0,
    coarse_scale_step: float = 0.1,
    fine_scale_step: float = 0.01,
    fine_scale_window: float | None = None,
    coarse_downsample: float = 1.0,
) -> ScaledTemplateMatch | None:
    """Find a scaled template by coarse search, then progressively approach it.

    Example with the defaults: scan 0.5..4.0 by 0.1, then search around the
    best scale by 0.02, then by 0.01. That keeps final click offsets accurate
    without doing hundreds of full-screen matches up front.
    """

    if coarse_scale_step <= 0:
        raise ValueError("coarse_scale_step 必须大于 0")
    if fine_scale_step <= 0:
        raise ValueError("fine_scale_step 必须大于 0")
    if coarse_scale_step < fine_scale_step:
        raise ValueError("coarse_scale_step 不能小于 fine_scale_step")
    if fine_scale_window is not None and fine_scale_window < 0:
        raise ValueError("fine_scale_window 不能小于 0")
    if not 0 < coarse_downsample <= 1:
        raise ValueError("coarse_downsample 必须在 0 到 1 之间")

    captured_screen = screen_image if screen_image is not None else capture_screen(region)
    coarse_template = template
    coarse_screen = captured_screen
    logger.info(
        "分辨率匹配：开始粗扫，"
        f"范围={min_scale:.2f}-{max_scale:.2f}，步长={coarse_scale_step:.3f}，"
        f"截图尺寸={captured_screen.shape[1]}x{captured_screen.shape[0]}，"
        f"粗扫降采样={coarse_downsample:.2f}"
    )
    if coarse_downsample < 1:
        template_bgr, _ = _load_template_image(template)
        coarse_template = scale_image(template_bgr, coarse_downsample)
        coarse_screen = scale_image(captured_screen, coarse_downsample)
        logger.info(
            "分辨率匹配：粗扫使用降采样截图，"
            f"尺寸={coarse_screen.shape[1]}x{coarse_screen.shape[0]}"
        )

    best_match = find_scaled_template(
        coarse_template,
        threshold=0,
        screen_image=coarse_screen,
        region=region,
        min_scale=min_scale,
        max_scale=max_scale,
        scale_step=coarse_scale_step,
    )
    if best_match is None:
        logger.info("分辨率匹配：粗扫没有找到候选")
        return None
    logger.info(f"分辨率匹配：粗扫候选，{_format_scaled_match(best_match)}")

    search_radius = max(fine_scale_window or 0, coarse_scale_step)
    scale_step = max(fine_scale_step, coarse_scale_step / 5)
    round_index = 1
    while True:
        round_min_scale = max(min_scale, best_match.scale - search_radius)
        round_max_scale = min(max_scale, best_match.scale + search_radius)
        logger.info(
            f"分辨率匹配：第 {round_index} 轮逼近，"
            f"范围={round_min_scale:.3f}-{round_max_scale:.3f}，步长={scale_step:.3f}"
        )
        candidate = find_scaled_template(
            template,
            threshold=0,
            screen_image=captured_screen,
            region=region,
            min_scale=round_min_scale,
            max_scale=round_max_scale,
            scale_step=scale_step,
        )
        if candidate is None:
            logger.info(f"分辨率匹配：第 {round_index} 轮逼近没有找到候选")
        else:
            logger.info(f"分辨率匹配：第 {round_index} 轮候选，{_format_scaled_match(candidate)}")
        if candidate is not None and candidate.score >= best_match.score:
            best_match = candidate
            logger.info(f"分辨率匹配：第 {round_index} 轮更新最佳候选")

        if scale_step <= fine_scale_step:
            break

        search_radius = scale_step
        scale_step = max(fine_scale_step, scale_step / 5)
        round_index += 1

    if best_match.score < threshold:
        logger.info(
            "分辨率匹配：最佳候选低于阈值，"
            f"阈值={threshold:.4f}，{_format_scaled_match(best_match)}"
        )
        return None
    logger.info(f"分辨率匹配：最终结果，{_format_scaled_match(best_match)}")
    return best_match


def _format_scaled_match(match: ScaledTemplateMatch) -> str:
    return (
        f"scale={match.scale:.4f}，score={match.score:.4f}，"
        f"top_left=({match.top_left.x}, {match.top_left.y})，"
        f"bottom_right=({match.bottom_right.x}, {match.bottom_right.y})，"
        f"matched_size={match.matched_size[0]}x{match.matched_size[1]}"
    )


def find_first_template_center(
    templates_dir: str | Path = "templates",
    *,
    threshold: float = 0.85,
    template_scale: float | None = None,
    use_scaled_template_cache: bool = True,
    screen_image: np.ndarray | None = None,
    region: dict[str, int] | None = None,
) -> TemplateMatch | None:
    """在屏幕图像中查找 templates 目录下第一个匹配成功的模板。

    匹配顺序按文件名排序。template_scale 不为空时，会先把模板缩放到当前
    游戏分辨率再匹配。某个模板最高相似度达到 threshold 后，就返回该模板
    最佳匹配位置的中心点；所有模板都不达标时返回 None。
    """

    templates_path = Path(templates_dir)
    if not templates_path.exists():
        raise FileNotFoundError(f"模板目录不存在：{templates_path}")

    if not 0 <= threshold <= 1:
        raise ValueError("threshold 必须在 0 到 1 之间")
    if template_scale is not None and template_scale <= 0:
        raise ValueError("template_scale 必须大于 0")

    # 没有传入截图时，函数自己截屏；传入 screen_image 时方便写测试和复用已有截图。
    screen_bgr = screen_image if screen_image is not None else capture_screen(region)
    offset_x = int(region["left"]) if screen_image is None and region else 0
    offset_y = int(region["top"]) if screen_image is None and region else 0

    for template_path in _iter_template_paths(templates_path):
        if template_scale is None:
            template_bgr = _read_image(template_path)
        else:
            template_bgr = load_scaled_template(
                template_path,
                template_scale,
                use_cache=use_scaled_template_cache,
            )
        match = _match_single_template(
            screen_bgr=screen_bgr,
            template_bgr=template_bgr,
            template_path=template_path,
            threshold=threshold,
            offset_x=offset_x,
            offset_y=offset_y,
        )
        if match is not None:
            return match

    return None


def find_template_center(
    template_path: str | Path,
    *,
    threshold: float = 0.85,
    template_scale: float | None = None,
    use_scaled_template_cache: bool = True,
    screen_image: np.ndarray | None = None,
    region: dict[str, int] | None = None,
) -> TemplateMatch | None:
    """在屏幕图像中查找一张指定模板，并返回最佳匹配中心点。

    后续点击按钮时优先用这个函数。它只匹配传入的那张模板，不会被 templates
    目录里的其他图片干扰。
    """

    path = Path(template_path)
    if not 0 <= threshold <= 1:
        raise ValueError("threshold 必须在 0 到 1 之间")
    if template_scale is not None and template_scale <= 0:
        raise ValueError("template_scale 必须大于 0")

    # 没有传入截图时，函数自己截屏；传入 screen_image 时方便一帧内匹配多个按钮。
    screen_bgr = screen_image if screen_image is not None else capture_screen(region)
    offset_x = int(region["left"]) if screen_image is None and region else 0
    offset_y = int(region["top"]) if screen_image is None and region else 0

    if template_scale is None:
        template_bgr = _read_image(path)
    else:
        template_bgr = load_scaled_template(
            path,
            template_scale,
            use_cache=use_scaled_template_cache,
        )

    return _match_single_template(
        screen_bgr=screen_bgr,
        template_bgr=template_bgr,
        template_path=path,
        threshold=threshold,
        offset_x=offset_x,
        offset_y=offset_y,
    )


def wait_template_center(
    template_path: str | Path,
    *,
    timeout_seconds: float = 10,
    interval_seconds: float = 0.5,
    threshold: float = 0.85,
    template_scale: float | None = None,
    use_scaled_template_cache: bool = True,
    region: dict[str, int] | None = None,
) -> TemplateMatch | None:
    """等待指定模板出现在屏幕上，超时后返回 None。

    每次轮询都会重新截图，因此适合等待游戏加载、弹窗出现、按钮刷新等场景。
    template_scale 不为空时，会先按当前分辨率缩放模板再匹配。
    """

    if timeout_seconds < 0:
        raise ValueError("timeout_seconds 不能小于 0")
    if interval_seconds <= 0:
        raise ValueError("interval_seconds 必须大于 0")
    if not 0 <= threshold <= 1:
        raise ValueError("threshold 必须在 0 到 1 之间")
    if template_scale is not None and template_scale <= 0:
        raise ValueError("template_scale 必须大于 0")

    path = Path(template_path)
    if template_scale is None:
        template_bgr = _read_image(path)
    else:
        template_bgr = load_scaled_template(
            path,
            template_scale,
            use_cache=use_scaled_template_cache,
        )

    deadline = monotonic() + timeout_seconds
    while True:
        # 等待期间画面会变化，所以每一轮都必须重新截图。
        screen_bgr = capture_screen(region)
        offset_x = int(region["left"]) if region else 0
        offset_y = int(region["top"]) if region else 0
        match = _match_single_template(
            screen_bgr=screen_bgr,
            template_bgr=template_bgr,
            template_path=path,
            threshold=threshold,
            offset_x=offset_x,
            offset_y=offset_y,
        )
        if match is not None:
            return match

        remaining_seconds = deadline - monotonic()
        if remaining_seconds <= 0:
            return None

        # 最后一轮只睡剩余时间，避免明显超过调用方设置的超时时间。
        sleep(min(interval_seconds, remaining_seconds))


def resolve_window_offset_point(window_match: ScaledTemplateMatch, offset_x: int | float, offset_y: int | float) -> Point:
    """把模板窗口内的偏移坐标转换成真实屏幕坐标。

    offset_x、offset_y 是基于“深渊主界面模板原始尺寸”的坐标，也就是从模板
    左上角开始量出来的位置。函数会按 window_match.scale 放大偏移量，再加上
    当前真实游戏窗口的左上角坐标。
    """

    return Point(
        x=round(window_match.top_left.x + offset_x * window_match.scale),
        y=round(window_match.top_left.y + offset_y * window_match.scale),
    )


def click_window_offset(
    window_match: ScaledTemplateMatch,
    offset_x: int | float,
    offset_y: int | float,
    *,
    duration: float = 0.15,
) -> Point:
    """点击游戏窗口内的固定偏移坐标，并返回真实点击点。

    这个函数适合点击没有稳定图片模板、但相对窗口位置固定的 UI。传入坐标仍然
    使用模板原始分辨率下的坐标，函数内部会自动乘以缩放比例。
    """

    point = resolve_window_offset_point(window_match, offset_x, offset_y)
    click_screen_point(point.x, point.y, duration=duration)
    return point


def click_screen_point(x: int | float, y: int | float, *, duration: float = 0.15) -> Point:
    """Click a screen coordinate, including coordinates on secondary monitors."""

    point = move_screen_point(x, y, duration=duration)
    if sys.platform == "win32":
        _send_current_position_click()
        return point

    pyautogui.click()
    return point


def move_screen_point(x: int | float, y: int | float, *, duration: float = 0.15) -> Point:
    """Move to a screen coordinate, including coordinates on secondary monitors."""

    point = Point(x=round(x), y=round(y))
    if sys.platform == "win32":
        ctypes.windll.user32.SetCursorPos(point.x, point.y)
        if duration > 0:
            sleep(duration)
        return point

    pyautogui.moveTo(point.x, point.y, duration=duration)
    return point


class _MouseInput(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    )


class _InputUnion(ctypes.Union):
    _fields_ = (("mi", _MouseInput),)


class _Input(ctypes.Structure):
    _fields_ = (("type", wintypes.DWORD), ("union", _InputUnion))


def _send_current_position_click() -> None:
    inputs = (_Input * 2)(
        _Input(type=0, union=_InputUnion(mi=_MouseInput(0, 0, 0, 0x0002, 0, None))),
        _Input(type=0, union=_InputUnion(mi=_MouseInput(0, 0, 0, 0x0004, 0, None))),
    )
    ctypes.windll.user32.SendInput(len(inputs), ctypes.byref(inputs), ctypes.sizeof(_Input))


def _iter_template_paths(templates_dir: Path) -> Iterable[Path]:
    """按稳定顺序返回支持的模板图片文件。"""

    return (
        path
        for path in sorted(templates_dir.iterdir())
        if path.is_file() and path.suffix.lower() in SUPPORTED_TEMPLATE_EXTENSIONS
    )


def _read_image(path: Path) -> np.ndarray:
    """读取图片为 OpenCV BGR 图像，兼容中文路径。"""

    image_bytes = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(image_bytes, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"无法读取模板图片：{path}")
    return image


def _load_template_image(template: str | Path | np.ndarray) -> tuple[np.ndarray, Path | None]:
    """把路径或已读取图片统一转换成 OpenCV BGR 图像。"""

    if isinstance(template, np.ndarray):
        return template, None

    template_path = Path(template)
    return _read_image(template_path), template_path


@lru_cache(maxsize=128)
def _load_scaled_template_cached(
    template_path: str,
    scale: float,
    mtime_ns: int,
    file_size: int,
) -> np.ndarray:
    """缓存按比例缩放后的模板图。

    mtime_ns 和 file_size 只用于组成缓存 key；函数体不直接使用它们。
    """

    _ = mtime_ns, file_size
    return scale_image(_read_image(Path(template_path)), scale)


def _iter_scales(*, min_scale: float, max_scale: float, scale_step: float) -> Iterable[float]:
    """生成稳定的缩放比例序列，包含 max_scale 附近的最后一个值。"""

    scale = min_scale
    while scale <= max_scale + scale_step / 2:
        yield round(scale, 4)
        scale += scale_step


def _match_gray_images(
    *,
    screen_gray: np.ndarray,
    template_gray: np.ndarray,
) -> tuple[float, tuple[int, int]]:
    """匹配两张灰度图，返回统一语义的分数和左上角坐标。

    返回分数越接近 1 表示越匹配。纯色模板会自动改用平方差算法。
    """

    if float(template_gray.std()) < 1:
        result = cv2.matchTemplate(screen_gray, template_gray, cv2.TM_SQDIFF_NORMED)
        min_score, _, min_location, _ = cv2.minMaxLoc(result)
        return 1 - float(min_score), min_location

    result = cv2.matchTemplate(screen_gray, template_gray, cv2.TM_CCOEFF_NORMED)
    _, max_score, _, max_location = cv2.minMaxLoc(result)
    return float(max_score), max_location


def _match_single_template(
    *,
    screen_bgr: np.ndarray,
    template_bgr: np.ndarray,
    template_path: Path,
    threshold: float,
    offset_x: int,
    offset_y: int,
) -> TemplateMatch | None:
    """对单张模板做匹配，达到阈值时返回最佳匹配中心点。"""

    screen_height, screen_width = screen_bgr.shape[:2]
    template_height, template_width = template_bgr.shape[:2]
    if template_width > screen_width or template_height > screen_height:
        return None

    # 转灰度可以减少颜色差异造成的误判，也比彩色匹配更快。
    screen_gray = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
    template_gray = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)

    match_score, match_location = _match_gray_images(
        screen_gray=screen_gray,
        template_gray=template_gray,
    )
    if match_score < threshold:
        return None

    left = int(match_location[0]) + offset_x
    top = int(match_location[1]) + offset_y
    right = left + template_width
    bottom = top + template_height
    center_x = left + template_width // 2
    center_y = top + template_height // 2

    return TemplateMatch(
        template_path=template_path,
        center=Point(x=center_x, y=center_y),
        top_left=Point(x=left, y=top),
        bottom_right=Point(x=right, y=bottom),
        score=match_score,
    )
