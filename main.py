"""TuneLift 后端：把 QQ音乐的加密音频解密出来，并按需转成 MP3。

三段式流程：

    扫描  →  解密  →  转码
    ────     ────     ────
    递归找出输入目录里的 .mflac / .mgg；
    注入 QQ音乐客户端，借它的解密能力把文件还原成 FLAC / OGG；
    再调用 ffmpeg 把音频转成 MP3。

解密这一步依赖 QQMusic.exe 正在运行——程序会把一段钩子脚本注入进去，调用它自己
读取加密媒体的那套逻辑。所以运行前必须先把 QQ音乐客户端打开并登录。

命令行用法见 `python main.py --help`；退出码含义见 `EXIT_*` 常量。
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import frida
from frida.core import Script, Session

# 进程退出码。分成四档是为了让批处理能区分「环境没准备好」和「跑起来了但有文件失败」。
EXIT_OK = 0
EXIT_BAD_USAGE = 2  # 沿用 argparse 对「用法/参数不对」的约定
EXIT_DECRYPT_FAILED = 3
EXIT_CONVERT_FAILED = 4

SOURCE_SUFFIXES = (".mflac", ".mgg")
DEFAULT_BITRATE = "192k"
QQMUSIC_PROCESS = "QQMusic.exe"
HOOK_SCRIPT = "hook_qq_music.js"
FFMPEG_BINARY = "ffmpeg.exe"

# 加密格式与还原后格式的对应关系：mflac 是无损，mgg 是 OGG。
RESTORED_SUFFIX = {".mflac": ".flac", ".mgg": ".ogg"}


class TuneLiftError(RuntimeError):
    """前置条件不满足，当前根本没法开工。

    输入目录、输出目录、QQ音乐进程、钩子脚本这四类问题都归到这里。它们和
    「某个文件解密失败」性质不同：前者重试也没用，应当直接退出；后者逐文件跳过即可。
    """


def _force_utf8_console() -> None:
    """把 stdout/stderr 换成 UTF-8 输出，避免中文日志乱码或直接抛异常。

    只在 PyInstaller 冻结后执行：那时流的编码跟着系统代码页走，打印中文会抛
    UnicodeEncodeError。直接跑源码时 Python 自己处理得很好，而且模块 import 阶段
    替换全局 sys.stdout 会破坏调用方的输出捕获（pytest 会因此报
    "Bad file descriptor"），所以不做无条件替换。
    """
    if not getattr(sys, "frozen", False):
        return
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        try:
            handle = stream.fileno()
        except (AttributeError, OSError, ValueError):
            continue
        setattr(sys, name, open(handle, mode="w", encoding="utf-8", errors="replace"))


_force_utf8_console()


def resource_path(name: str) -> str:
    """返回随程序分发的资源（钩子脚本、ffmpeg）的绝对路径。

    PyInstaller 冻结后资源在 sys._MEIPASS 下；直接跑源码时以当前工作目录为准。
    """
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, name)
    return os.path.join(os.path.abspath("."), name)


def force_remove(path: str | Path, max_retries: int = 5, delay: float = 0.2) -> bool:
    """尽力删除文件，删不掉也不抛异常。

    Windows 上刚被读取过的文件句柄可能还没释放，unlink 会报 PermissionError，
    所以重试若干次。返回最终是否删干净（文件本来就不存在也算成功）。
    """
    for _ in range(max_retries):
        try:
            if os.path.exists(path):
                os.unlink(path)
            return True
        except PermissionError:
            time.sleep(delay)
    return False


def _log_script_error(message: dict, data: bytes | None) -> None:
    """钩子脚本内部报错时的回调。

    frida 不会把脚本错误抛给 load()，只在 message 里异步送出。不打出来的话，
    真正的原因（比如某个导出函数找不到）就完全看不见了。
    """
    if message.get("type") == "error":
        logging.error("解密脚本报错: %s", message.get("description"))


def _activate_hook(session: Session) -> Script:
    """在会话里加载钩子脚本，并确认它真的可用。

    脚本要调用的 DLL（QQMusicCommon.dll）是 QQ音乐按需加载的，所以「客户端开着
    但还没播放过任何歌」时脚本会初始化失败。这种失败必须当场认出来，否则后面
    每个文件都会报一句莫名其妙的 "unable to find method 'decrypt'"。
    """
    hook_file = resource_path(HOOK_SCRIPT)
    with open(hook_file, encoding="utf-8") as handle:
        source = handle.read()

    script = session.create_script(source)
    script.on("message", _log_script_error)
    script.load()

    try:
        exported = script.list_exports_sync()
    except Exception:
        return script  # 老版本 frida 没有这个接口，只能跳过检查

    if "decrypt" not in exported:
        logging.error(
            "解密脚本没有生效：QQMusicCommon.dll 可能还没被 QQ音乐加载。先在 QQ音乐里播放任意一首歌，再重新运行本程序。"
        )
        raise TuneLiftError("解密脚本未生效")
    return script


@contextmanager
def _decryptor() -> Iterator[Script]:
    """连上 QQ音乐并装好钩子；无论怎么退出都会断开连接。

    attach 之后如果中途抛异常而不 detach，会把附着状态留在 QQ音乐进程里。
    用上下文管理器把这件事集中在一处，调用方就不用逐个出口去写了。
    """
    try:
        session = frida.attach(QQMUSIC_PROCESS)
    except frida.ProcessNotFoundError:
        logging.error("请确保QQ音乐客户端正在运行后重试")
        raise TuneLiftError(f"未找到进程 {QQMUSIC_PROCESS}") from None

    try:
        yield _activate_hook(session)
    finally:
        session.detach()


def collect_sources(root: str) -> list[Path]:
    """递归收集 root 下所有待解密的文件，按路径排序。"""
    found: list[Path] = []
    for directory, _sub_dirs, filenames in os.walk(root):
        for filename in filenames:
            if os.path.splitext(filename)[1] in SOURCE_SUFFIXES:
                found.append(Path(directory) / filename)
    return sorted(found)


def _decrypt_one(script: Script, source: Path, target: Path) -> None:
    """解密单个文件到 target。失败时抛异常，由调用方负责计数。

    解密库只认本地路径，所以先把源文件复制到临时目录，让它把结果写到另一个
    临时文件，成功后再挪到最终位置。两个临时文件都要清理掉。
    """
    restored_suffix = RESTORED_SUFFIX[source.suffix]
    source_copy = tempfile.NamedTemporaryFile(suffix=source.suffix, delete=False).name
    result_copy = tempfile.NamedTemporaryFile(suffix=restored_suffix, delete=False).name

    try:
        shutil.copy2(source, source_copy)
        script.exports_sync.decrypt(source_copy, result_copy)
        shutil.move(result_copy, target)
    finally:
        force_remove(source_copy)
        force_remove(result_copy)


def run_decrypt(input_dir: str, flac_output_dir: str) -> tuple[int, int, int]:
    """把 input_dir（含子目录）里的加密音频全部解密到 flac_output_dir。

    返回 (本次解密数, 失败数, 已存在跳过数)。单个文件失败只跳过它，不影响其余；
    前置条件不满足则抛 TuneLiftError。
    """
    if not os.path.isdir(input_dir):
        raise TuneLiftError(f"输入目录不存在: {input_dir}")

    input_dir = os.path.abspath(input_dir)
    flac_output_dir = os.path.abspath(flac_output_dir)

    try:
        os.makedirs(flac_output_dir, exist_ok=True)
    except OSError as exc:
        logging.error("无法创建输出目录 %s: %s", flac_output_dir, exc)
        raise TuneLiftError(f"输出目录不可用: {flac_output_dir}") from exc

    sources = collect_sources(input_dir)
    if not sources:
        logging.info("没有找到 %s 文件", " 或 ".join(SOURCE_SUFFIXES))
        return 0, 0, 0

    logging.info("找到 %d 个文件，开始解密...", len(sources))
    decrypted = failed = reused = 0

    with _decryptor() as script:
        for index, source in enumerate(sources, 1):
            target = Path(flac_output_dir) / (source.stem + RESTORED_SUFFIX[source.suffix])
            if target.exists():
                # 上一次已经解出来了，直接复用——这样换了输出格式重跑不必从头再来
                reused += 1
                continue

            try:
                _decrypt_one(script, source, target)
                decrypted += 1
            except Exception as exc:
                failed += 1
                print()
                logging.error("解密失败: %s - %s", source.name, exc)

            print(f"解密进度: {index}/{len(sources)} (成功: {decrypted}, 失败: {failed})", end="\r", flush=True)

    print()
    logging.info("解密阶段完成: 新解密 %d 个，失败 %d 个，已存在跳过 %d 个", decrypted, failed, reused)
    return decrypted, failed, reused


def convert_to_mp3(audio_path: str, mp3_path: str, ffmpeg_path: str, bitrate: str) -> bool:
    """用 ffmpeg 把一个音频转成 MP3，成功返回 True。"""
    command = [ffmpeg_path, "-i", audio_path, "-b:a", bitrate, mp3_path, "-y"]

    try:
        subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        return True
    except subprocess.CalledProcessError as exc:
        logging.error("转码失败 %s，返回码: %s", Path(audio_path).name, exc.returncode)
        return False
    except FileNotFoundError:
        logging.error("未找到 %s", FFMPEG_BINARY)
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

    两种模式的区别只在一处：FLAC 是无损的，值得留；OGG 不是，留着没意义。

    no_mp3=True（--no-mp3，「仅 FLAC」）：FLAC 原样保留不转码；OGG 强制转 MP3
    且删掉源文件。
    no_mp3=False：全部转码，转完是否删源文件由 keep_flac 决定。

    返回 (转码成功数, 转码失败数)。
    """
    audio_files = sorted(Path(audio_dir).glob("*.flac")) + sorted(Path(audio_dir).glob("*.ogg"))
    if not audio_files:
        logging.info("在 %s 中没有找到 .flac 或 .ogg 文件", audio_dir)
        return 0, 0

    try:
        os.makedirs(mp3_dir, exist_ok=True)
    except OSError as exc:
        logging.error("无法创建输出目录 %s: %s", mp3_dir, exc)
        return 0, 0

    logging.info("找到 %d 个音频文件，开始转码 MP3...", len(audio_files))
    converted = failed = kept = 0

    for index, audio_file in enumerate(audio_files, 1):
        suffix = audio_file.suffix.lower()
        print(f"转码进度: {index}/{len(audio_files)} - {audio_file.stem}", end="\r", flush=True)

        if no_mp3 and suffix == ".flac":
            kept += 1
            continue

        target = Path(mp3_dir) / (audio_file.stem + ".mp3")
        if convert_to_mp3(str(audio_file), str(target), ffmpeg_path, bitrate):
            converted += 1
            if not (keep_flac and not no_mp3):
                force_remove(audio_file)
                logging.info("已删除 %s 源文件: %s", suffix, audio_file)
        else:
            failed += 1

    print()
    logging.info("转码阶段完成: 成功 %d 个，失败 %d 个，未转码保留 %d 个", converted, failed, kept)
    return converted, failed


def build_output_dirs(args: argparse.Namespace) -> tuple[str, str]:
    """按命令行参数算出 (FLAC 输出目录, MP3 输出目录)。

    同时给了 --flac-dir 和 --mp3-dir 就完全按用户说的来；
    否则在 -o（默认 ./output）下面自动分 flac / mp3 两个子目录。
    """
    if args.flac_dir and args.mp3_dir:
        return os.path.abspath(args.flac_dir), os.path.abspath(args.mp3_dir)

    root = os.path.abspath(args.output) if args.output else os.path.join(os.getcwd(), "output")
    return os.path.join(root, "flac"), os.path.join(root, "mp3")


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

    input_dir = os.path.abspath(args.input) if args.input else os.getcwd()
    if not os.path.isdir(input_dir):
        logging.error("输入目录不存在: %s", input_dir)
        return EXIT_BAD_USAGE

    flac_output_dir, mp3_output_dir = build_output_dirs(args)
    logging.info("输入目录: %s", input_dir)
    logging.info("FLAC 输出: %s", flac_output_dir)
    logging.info("MP3 输出: %s", mp3_output_dir)

    ffmpeg_path = resource_path(FFMPEG_BINARY)
    if not os.path.isfile(ffmpeg_path):
        logging.error("未找到 %s，请将其放在 %s 路径", FFMPEG_BINARY, ffmpeg_path)
        return EXIT_BAD_USAGE

    try:
        decrypted, decrypt_failed, reused = run_decrypt(input_dir, flac_output_dir)
    except TuneLiftError:
        return EXIT_BAD_USAGE

    # 只要输出目录里有音频就进转码阶段——包括这一轮跳过的旧文件。
    # 否则「先 --no-mp3 只要 FLAC，再改成默认要 MP3」会因为新解密数为 0 而什么都不做。
    convert_failed = 0
    if decrypted + reused > 0:
        _converted, convert_failed = process_audio_to_mp3(
            flac_output_dir, mp3_output_dir, ffmpeg_path, args.bitrate, args.keep_flac, args.no_mp3
        )
    else:
        logging.info("没有可转码的 FLAC/OGG 文件，跳过转码步骤")

    logging.info("全部处理完成")

    if decrypt_failed:
        return EXIT_DECRYPT_FAILED
    if convert_failed:
        return EXIT_CONVERT_FAILED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
