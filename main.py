"""TuneLift 后端：解密 QQ音乐加密音频，并按需转成 MP3。

整体流程：
    1. 用 frida 注入正在运行的 QQMusic.exe，加载同目录的 hook_qq_music.js；
    2. 该脚本调用 QQMusicCommon.dll 里 EncAndDesMediaFile 的导出函数，
       把 .mflac / .mgg 解密成普通的 FLAC / OGG；
    3. 调用同目录的 ffmpeg.exe 把音频转成 MP3。

运行前必须先启动 QQ音乐客户端并登录——解密依赖它的进程。
命令行参数见 `python main.py --help`。
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path

import frida
from frida.core import Script, Session

# 进程退出码：0 成功；2 是环境/参数不满足（沿用 argparse 的习惯）；
# 3 和 4 表示程序跑起来了但有文件没处理成功，便于脚本编排时区分。
EXIT_OK = 0
EXIT_BAD_USAGE = 2
EXIT_DECRYPT_FAILED = 3
EXIT_CONVERT_FAILED = 4

SOURCE_EXTS = (".mflac", ".mgg")
DEFAULT_BITRATE = "192k"
QQMUSIC_PROCESS = "QQMusic.exe"


def _force_utf8_console() -> None:
    """把 stdout/stderr 重新包成 UTF-8 输出，避免中文日志乱码或直接抛异常。

    只在 PyInstaller 冻结后执行：那时流是按系统代码页装配的，打印中文会抛
    UnicodeEncodeError。直接跑源码时 Python 自己就处理得很好，而且模块 import
    时替换全局 sys.stdout 会破坏调用方的输出捕获（pytest 就因此报
    "Bad file descriptor"），所以不做无条件替换。
    """
    if not getattr(sys, "frozen", False):
        return
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        try:
            fd = stream.fileno()
        except (AttributeError, OSError, ValueError):
            continue
        setattr(sys, name, open(fd, mode="w", encoding="utf-8", errors="replace"))


_force_utf8_console()


class TuneLiftError(RuntimeError):
    """前置条件不满足：输入目录、输出目录、QQ音乐进程或 hook 脚本有问题。

    这类问题意味着「现在根本没法开工」，和「某个文件解密失败」要分开对待，
    调用方据此返回不同的退出码。
    """


def resource_path(relative_path: str) -> str:
    """返回随程序分发的资源（hook 脚本、ffmpeg）的绝对路径。

    PyInstaller 冻结后会设置 sys._MEIPASS 指向资源目录；直接跑源码时
    则以当前工作目录为准。
    """
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


def force_remove(file_path: str | Path, max_retries: int = 5, delay: float = 0.2) -> bool:
    """尽最大努力删除文件，删不掉也不抛异常。

    Windows 上刚被 QQ音乐读完的文件句柄可能还没释放，unlink 会报
    PermissionError，所以这里重试若干次。返回是否删干净了
    （文件本来就不存在也算成功）。
    """
    for _ in range(max_retries):
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
            return True
        except PermissionError:
            time.sleep(delay)
    return False


def _log_script_error(message: dict, data: bytes | None) -> None:
    """hook 脚本内部报错时的回调。

    frida 不会把脚本错误抛给 load()，只在 message 里异步送出，不打出来的话
    真正的原因（比如某个导出函数找不到）就完全看不见了。
    """
    if message.get("type") == "error":
        logging.error("hook 脚本报错: %s", message.get("description"))


def _activate_hook(session: Session) -> Script:
    """在当前会话里加载 hook 脚本并确认它真的可用。

    QQMusicCommon.dll 要等 QQ音乐真正用到时才加载，所以「客户端开着但还没
    播放过任何歌」的情况下脚本会初始化失败。这种失败必须当场认出来，
    否则后面每个文件都会报一句莫名其妙的 "unable to find method 'decrypt'"。
    """
    hook_path = resource_path("hook_qq_music.js")
    with open(hook_path, encoding="utf-8") as f:
        jscode = f.read()

    script = session.create_script(jscode)
    script.on("message", _log_script_error)
    script.load()

    try:
        exports = script.list_exports_sync()
    except Exception:
        return script  # 老版本 frida 没有这个接口，只能放行

    if "decrypt" not in exports:
        logging.error(
            "hook 脚本没有生效：QQMusicCommon.dll 可能还没被 QQ音乐加载。"
            "先在 QQ音乐里播放任意一首歌，再重新运行本程序。"
        )
        raise TuneLiftError("hook 脚本未生效")
    return script


def run_decrypt(input_dir: str, flac_output_dir: str) -> tuple[int, int, int]:
    """把 input_dir（含子目录）里所有 .mflac / .mgg 解密到 flac_output_dir。

    返回 (本次解密数, 失败数, 已存在跳过数)。单个文件失败只跳过该文件，
    不影响其余文件；前置条件不满足则抛 TuneLiftError。
    """
    if not os.path.isdir(input_dir):
        raise TuneLiftError(f"输入目录不存在: {input_dir}")

    input_dir = os.path.abspath(input_dir)
    flac_output_dir = os.path.abspath(flac_output_dir)

    # 只有 attach 这一步要单独接住：QQ音乐没开是最常见的失败，提示要够直白。
    try:
        session = frida.attach(QQMUSIC_PROCESS)
    except frida.ProcessNotFoundError:
        logging.error("请确保QQ音乐客户端正在运行后重试")
        raise TuneLiftError(f"未找到进程 {QQMUSIC_PROCESS}") from None

    # 从这里开始无论怎么退出都要 detach，否则会把 attach 状态留在 QQ音乐进程里。
    try:
        script = _activate_hook(session)

        try:
            os.makedirs(flac_output_dir, exist_ok=True)
        except OSError as e:
            logging.error("无法创建输出目录 %s: %s", flac_output_dir, e)
            raise TuneLiftError(f"输出目录不可用: {flac_output_dir}") from e

        # 先把待处理文件收集成 (所在目录, 文件名) 列表，后续按序号报进度。
        pending: list[tuple[str, str]] = []
        for src_dir, _sub_dirs, filenames in os.walk(input_dir):
            for src_name in filenames:
                if os.path.splitext(src_name)[1] in SOURCE_EXTS:
                    pending.append((src_dir, src_name))

        total = len(pending)
        if total == 0:
            logging.info("没有找到 .mflac 或 .mgg 文件")
            return 0, 0, 0

        logging.info("找到 %d 个文件，开始解密...", total)
        decrypted = 0
        failed = 0
        reused = 0

        for index, (src_dir, src_name) in enumerate(pending, 1):
            base_name, ext = os.path.splitext(src_name)
            # mflac 是无损（FLAC），mgg 是 OGG
            out_ext = ".flac" if ext == ".mflac" else ".ogg"
            out_name = base_name + out_ext
            out_path = os.path.join(flac_output_dir, out_name)
            if os.path.exists(out_path):
                # 上一轮已经解过了，直接复用（方便换输出格式后重跑）
                reused += 1
                continue

            # QQMusicCommon.dll 只认本地文件路径，所以先把源文件复制一份到临时目录，
            # 再把解密结果写到另一个临时文件，成功后 move 到输出目录。
            # 两个临时文件都交给 finally 清理（用 force_remove，删不掉也不会中断流程）。
            with tempfile.NamedTemporaryFile(suffix=".mflac", delete=False) as tmp_handle:
                tmp_in_path = tmp_handle.name
            tmp_out_path = tempfile.NamedTemporaryFile(suffix=out_ext, delete=False).name

            try:
                shutil.copy2(os.path.join(src_dir, src_name), tmp_in_path)
                script.exports_sync.decrypt(tmp_in_path, tmp_out_path)
                shutil.move(tmp_out_path, out_path)
                decrypted += 1
            except Exception as e:
                failed += 1
                print()
                logging.error("解密失败: %s - %s", src_name, e)
            finally:
                if os.path.exists(tmp_in_path):
                    force_remove(tmp_in_path)
                if os.path.exists(tmp_out_path):
                    force_remove(tmp_out_path)

            print(f"解密进度: {index}/{total} (成功: {decrypted}, 失败: {failed})", end="\r", flush=True)

        print()
        logging.info("解密阶段完成: 新解密 %d 个，失败 %d 个，已存在跳过 %d 个", decrypted, failed, reused)
        return decrypted, failed, reused
    finally:
        session.detach()


def convert_to_mp3(audio_path: str, mp3_path: str, ffmpeg_path: str, bitrate: str) -> bool:
    """用 ffmpeg 把单个音频转成 MP3，成功返回 True。"""
    cmd = [ffmpeg_path, "-i", audio_path, "-b:a", bitrate, mp3_path, "-y"]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        return True
    except subprocess.CalledProcessError as e:
        logging.error("转码失败 %s，返回码: %s", Path(audio_path).name, e.returncode)
        return False
    except FileNotFoundError:
        logging.error("未找到 ffmpeg.exe")
        return False


def process_audio_to_mp3(
    audio_dir: str,
    mp3_dir: str,
    ffmpeg_path: str,
    bitrate: str = DEFAULT_BITRATE,
    keep_flac: bool = False,
    no_mp3: bool = False,
) -> tuple[int, int]:
    """把 audio_dir 里的 FLAC / OGG 按模式转成 MP3。

    no_mp3=True（对应 --no-mp3，「仅 FLAC」）：
        - FLAC 不转码，原样保留；
        - OGG 本来就不是无损，强制转 MP3 且不保留源文件。
    no_mp3=False：
        - 全部转码，转完是否删源文件由 keep_flac 决定。

    返回 (转码成功数, 转码失败数)。
    """
    all_files = sorted(Path(audio_dir).glob("*.flac")) + sorted(Path(audio_dir).glob("*.ogg"))
    if not all_files:
        logging.info("在 %s 中没有找到 .flac 或 .ogg 文件", audio_dir)
        return 0, 0

    try:
        os.makedirs(mp3_dir, exist_ok=True)
    except OSError as e:
        logging.error("无法创建输出目录 %s: %s", mp3_dir, e)
        return 0, 0

    total = len(all_files)
    converted = 0
    failed = 0
    kept = 0

    logging.info("找到 %d 个音频文件，开始转码 MP3...", total)

    for index, audio_file in enumerate(all_files, 1):
        ext = audio_file.suffix.lower()
        mp3_file = Path(mp3_dir) / (audio_file.stem + ".mp3")
        print(f"转码进度: {index}/{total} - {audio_file.stem}", end="\r", flush=True)

        # 仅 FLAC 模式下 FLAC 原样留；OGG 没有无损可言，强制转 MP3 且不保留源文件。
        if no_mp3 and ext == ".flac":
            kept += 1
            continue

        keep_source = keep_flac and not no_mp3
        if convert_to_mp3(str(audio_file), str(mp3_file), ffmpeg_path, bitrate):
            converted += 1
            if not keep_source:
                force_remove(audio_file)
                logging.info("已删除 %s 源文件: %s", ext, audio_file)
        else:
            failed += 1

    print()
    logging.info("转码阶段完成: 成功 %d 个，失败 %d 个，未转码保留 %d 个", converted, failed, kept)
    return converted, failed


def build_output_dirs(args: argparse.Namespace) -> tuple[str, str]:
    """根据命令行参数算出 (FLAC 输出目录, MP3 输出目录)。

    显式给了 --flac-dir 和 --mp3-dir 就完全按用户说的来，否则在 -o
    （或默认的 ./output）下面自动分 mp3 / flac 两个子目录。
    """
    if args.flac_dir and args.mp3_dir:
        return os.path.abspath(args.flac_dir), os.path.abspath(args.mp3_dir)

    root_output = os.path.abspath(args.output) if args.output else os.path.join(os.getcwd(), "output")
    return os.path.join(root_output, "flac"), os.path.join(root_output, "mp3")


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="解密 QQ音乐 mflac 文件并转换为 MP3")
    parser.add_argument("-i", "--input", help="输入目录（包含 .mflac 文件），默认为当前目录")
    parser.add_argument(
        "-o",
        "--output",
        help="输出根目录（默认为当前目录下的 output），其下自动创建 mp3 子目录；"
        "若同时使用 --keep-flac，还会创建 flac 子文件夹",
    )
    parser.add_argument("--flac-dir", help="FLAC 输出目录（仅在 --keep-flac 时有效）")
    parser.add_argument("--mp3-dir", help="MP3 输出目录（覆盖默认）")
    parser.add_argument(
        "-b", "--bitrate", default=DEFAULT_BITRATE, help=f"MP3 比特率，例如 128k, 192k, 320k (默认: {DEFAULT_BITRATE})"
    )
    parser.add_argument("--keep-flac", action="store_true", help="保留解密后的 FLAC 文件（默认不保留）")
    parser.add_argument("--no-mp3", action="store_true", help="不生成 MP3，仅保留 FLAC（忽略 --keep-flac）")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口，返回进程退出码。"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    args = _parse_args(argv)

    input_dir = args.input if args.input else os.getcwd()
    if not os.path.isdir(input_dir):
        logging.error("输入目录不存在: %s", input_dir)
        return EXIT_BAD_USAGE
    input_dir = os.path.abspath(input_dir)

    flac_output_dir, mp3_output_dir = build_output_dirs(args)
    logging.info("输入目录: %s", input_dir)
    logging.info("FLAC 输出: %s", flac_output_dir)
    logging.info("MP3 输出: %s", mp3_output_dir)

    ffmpeg_path = resource_path("ffmpeg.exe")
    if not os.path.isfile(ffmpeg_path):
        logging.error("未找到 ffmpeg.exe，请将其放在 %s 路径", ffmpeg_path)
        return EXIT_BAD_USAGE

    try:
        decrypted, dec_failed, reused = run_decrypt(input_dir, flac_output_dir)
    except TuneLiftError:
        return EXIT_BAD_USAGE

    # 只要输出目录里有音频就转码——包括这一轮跳过的旧文件，
    # 否则「先 --no-mp3 再改要 MP3」会因为新解密数为 0 而什么都不做。
    if decrypted + reused > 0:
        _converted, conv_failed = process_audio_to_mp3(
            flac_output_dir, mp3_output_dir, ffmpeg_path, args.bitrate, args.keep_flac, args.no_mp3
        )
    else:
        conv_failed = 0
        logging.info("没有可转码的 FLAC/OGG 文件，跳过转码步骤")

    logging.info("全部处理完成")

    if dec_failed:
        return EXIT_DECRYPT_FAILED
    if conv_failed:
        return EXIT_CONVERT_FAILED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
