"""main.py 的单元测试。

全部离线运行：不需要 QQ音乐进程，也不需要真的调用 ffmpeg。
真实解密链路由 tools/ 下的端到端脚本覆盖，这里只锁行为契约。
"""

import argparse
import os
import sys
from pathlib import Path

import pytest

import main


# --------------------------------------------------------------------------
# resource_path
# --------------------------------------------------------------------------
def test_resource_path_without_meipass(monkeypatch, tmp_path):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.chdir(tmp_path)
    assert main.resource_path("hook.js") == os.path.join(os.path.abspath("."), "hook.js")


def test_resource_path_with_meipass(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert main.resource_path("hook.js") == os.path.join(str(tmp_path), "hook.js")


# --------------------------------------------------------------------------
# force_remove
# --------------------------------------------------------------------------
def test_force_remove_deletes_file(tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("x", encoding="utf-8")
    assert main.force_remove(target) is True
    assert not target.exists()


def test_force_remove_missing_file_counts_as_success(tmp_path):
    assert main.force_remove(tmp_path / "nope.txt") is True


def test_force_remove_retries_then_gives_up(tmp_path, monkeypatch):
    target = tmp_path / "locked.txt"
    target.write_text("x", encoding="utf-8")
    monkeypatch.setattr(main.time, "sleep", lambda _delay: None)

    attempts = []

    def always_locked(path):
        attempts.append(path)
        raise PermissionError("file is in use")

    monkeypatch.setattr(main.os, "unlink", always_locked)
    assert main.force_remove(target, max_retries=3, delay=0) is False
    assert len(attempts) == 3


# --------------------------------------------------------------------------
# _activate_hook —— 锁住「hook 没生效要当场发现」这个修复
# --------------------------------------------------------------------------
class _FakeScript:
    def __init__(self, exports):
        self._exports = exports

    def on(self, *_args):
        pass

    def load(self):
        pass

    def list_exports_sync(self):
        return self._exports


class _FakeSession:
    def __init__(self, script):
        self._script = script

    def create_script(self, _code):
        return self._script


def _fake_hook_file(monkeypatch, tmp_path):
    hook = tmp_path / "hook_qq_music.js"
    hook.write_text("// stub", encoding="utf-8")
    monkeypatch.setattr(main, "resource_path", lambda _name: str(hook))


def test_activate_hook_ok(monkeypatch, tmp_path):
    _fake_hook_file(monkeypatch, tmp_path)
    script = _FakeScript(["decrypt"])
    assert main._activate_hook(_FakeSession(script)) is script


def test_activate_hook_raises_when_decrypt_export_missing(monkeypatch, tmp_path):
    """脚本加载成功但没有 decrypt 导出（QQMusicCommon.dll 还没加载）。"""
    _fake_hook_file(monkeypatch, tmp_path)
    with pytest.raises(main.TuneLiftError):
        main._activate_hook(_FakeSession(_FakeScript([])))


def test_activate_hook_tolerates_old_frida_without_list_exports(monkeypatch, tmp_path):
    _fake_hook_file(monkeypatch, tmp_path)

    class OldScript(_FakeScript):
        def list_exports_sync(self):
            raise AttributeError("not available")

    script = OldScript([])
    assert main._activate_hook(_FakeSession(script)) is script


# --------------------------------------------------------------------------
# build_output_dirs
# --------------------------------------------------------------------------
def _args(**overrides):
    base = {"flac_dir": None, "mp3_dir": None, "output": None}
    base.update(overrides)
    return argparse.Namespace(**base)


def test_build_output_dirs_default_is_cwd_output(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    flac, mp3 = main.build_output_dirs(_args())
    assert flac == os.path.join(os.getcwd(), "output", "flac")
    assert mp3 == os.path.join(os.getcwd(), "output", "mp3")


def test_build_output_dirs_uses_output_root(tmp_path):
    flac, mp3 = main.build_output_dirs(_args(output=str(tmp_path / "o")))
    assert flac == str(tmp_path / "o" / "flac")
    assert mp3 == str(tmp_path / "o" / "mp3")


def test_build_output_dirs_explicit_dirs_win(tmp_path):
    flac, mp3 = main.build_output_dirs(
        _args(output=str(tmp_path / "ignored"), flac_dir=str(tmp_path / "F"), mp3_dir=str(tmp_path / "M"))
    )
    assert Path(flac) == tmp_path / "F"
    assert Path(mp3) == tmp_path / "M"


# --------------------------------------------------------------------------
# process_audio_to_mp3
# --------------------------------------------------------------------------
@pytest.fixture
def fake_convert(monkeypatch):
    """替换 convert_to_mp3，记录调用并生成一个假的 mp3 文件。"""
    calls = []

    def _fake(audio_path, mp3_path, _ffmpeg_path, bitrate):
        calls.append((Path(audio_path).name, Path(mp3_path).name, bitrate))
        Path(mp3_path).write_bytes(b"MP3")
        return True

    monkeypatch.setattr(main, "convert_to_mp3", _fake)
    return calls


def _make_audio(directory, *names):
    for name in names:
        (directory / name).write_bytes(b"audio")


def test_no_mp3_leaves_flac_alone(tmp_path, fake_convert):
    src, out = tmp_path / "in", tmp_path / "out"
    src.mkdir()
    _make_audio(src, "a.flac")

    assert main.process_audio_to_mp3(str(src), str(out), "ffmpeg", no_mp3=True) == (0, 0)
    assert fake_convert == []
    assert (src / "a.flac").exists()
    assert not (out / "a.mp3").exists()


def test_no_mp3_forces_ogg_conversion_and_removes_source(tmp_path, fake_convert):
    src, out = tmp_path / "in", tmp_path / "out"
    src.mkdir()
    _make_audio(src, "b.ogg")

    converted, failed = main.process_audio_to_mp3(str(src), str(out), "ffmpeg", no_mp3=True)
    assert (converted, failed) == (1, 0)
    assert [c[0] for c in fake_convert] == ["b.ogg"]
    assert not (src / "b.ogg").exists()
    assert (out / "b.mp3").exists()


def test_default_converts_and_deletes_source(tmp_path, fake_convert):
    src, out = tmp_path / "in", tmp_path / "out"
    src.mkdir()
    _make_audio(src, "c.flac")

    converted, _failed = main.process_audio_to_mp3(str(src), str(out), "ffmpeg")
    assert converted == 1
    assert not (src / "c.flac").exists()
    assert (out / "c.mp3").exists()


def test_keep_flac_keeps_source(tmp_path, fake_convert):
    src, out = tmp_path / "in", tmp_path / "out"
    src.mkdir()
    _make_audio(src, "d.flac")

    converted, _failed = main.process_audio_to_mp3(str(src), str(out), "ffmpeg", keep_flac=True)
    assert converted == 1
    assert (src / "d.flac").exists()


def test_conversion_failure_is_counted_not_raised(tmp_path, monkeypatch):
    src, out = tmp_path / "in", tmp_path / "out"
    src.mkdir()
    _make_audio(src, "e.flac")
    monkeypatch.setattr(main, "convert_to_mp3", lambda *a, **k: False)

    assert main.process_audio_to_mp3(str(src), str(out), "ffmpeg") == (0, 1)


def test_empty_audio_dir(tmp_path):
    src = tmp_path / "in"
    src.mkdir()
    assert main.process_audio_to_mp3(str(src), str(tmp_path / "out"), "ffmpeg") == (0, 0)


def test_bitrate_is_passed_through(tmp_path, fake_convert):
    src, out = tmp_path / "in", tmp_path / "out"
    src.mkdir()
    _make_audio(src, "f.flac")
    main.process_audio_to_mp3(str(src), str(out), "ffmpeg", bitrate="320k")
    assert fake_convert[0][2] == "320k"


# --------------------------------------------------------------------------
# main() —— 退出码契约
# --------------------------------------------------------------------------
def test_main_missing_input_dir_returns_bad_usage(tmp_path):
    assert main.main(["-i", str(tmp_path / "nope")]) == main.EXIT_BAD_USAGE


def _stub_ffmpeg(monkeypatch, tmp_path):
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"")
    monkeypatch.setattr(main, "resource_path", lambda name: str(tmp_path / name))


def test_main_missing_ffmpeg_returns_bad_usage(monkeypatch, tmp_path):
    src = tmp_path / "in"
    src.mkdir()
    monkeypatch.setattr(main, "resource_path", lambda name: str(tmp_path / "missing.exe"))
    assert main.main(["-i", str(src), "-o", str(tmp_path / "out")]) == main.EXIT_BAD_USAGE


def test_main_reports_decrypt_failures(monkeypatch, tmp_path):
    src = tmp_path / "in"
    src.mkdir()
    _stub_ffmpeg(monkeypatch, tmp_path)
    monkeypatch.setattr(main, "run_decrypt", lambda *a, **k: (2, 1, 0))

    assert main.main(["-i", str(src), "-o", str(tmp_path / "out")]) == main.EXIT_DECRYPT_FAILED


def test_main_reports_convert_failures(monkeypatch, tmp_path):
    src = tmp_path / "in"
    src.mkdir()
    _stub_ffmpeg(monkeypatch, tmp_path)
    monkeypatch.setattr(main, "run_decrypt", lambda *a, **k: (1, 0, 0))
    monkeypatch.setattr(main, "process_audio_to_mp3", lambda *a, **k: (0, 1))

    assert main.main(["-i", str(src), "-o", str(tmp_path / "out")]) == main.EXIT_CONVERT_FAILED


def test_main_maps_precondition_failure_to_bad_usage(monkeypatch, tmp_path):
    src = tmp_path / "in"
    src.mkdir()
    _stub_ffmpeg(monkeypatch, tmp_path)

    def _boom(*_a, **_k):
        raise main.TuneLiftError("QQ音乐没开")

    monkeypatch.setattr(main, "run_decrypt", _boom)
    assert main.main(["-i", str(src), "-o", str(tmp_path / "out")]) == main.EXIT_BAD_USAGE


def test_main_success_returns_zero(monkeypatch, tmp_path):
    src = tmp_path / "in"
    src.mkdir()
    _stub_ffmpeg(monkeypatch, tmp_path)
    monkeypatch.setattr(main, "run_decrypt", lambda *a, **k: (1, 0, 0))
    monkeypatch.setattr(main, "process_audio_to_mp3", lambda *a, **k: (1, 0))

    assert main.main(["-i", str(src), "-o", str(tmp_path / "out")]) == main.EXIT_OK


def test_reused_files_still_trigger_transcode(monkeypatch, tmp_path):
    """回归测试：输出已存在、本轮全部跳过时，也必须进入转码阶段。

    以前这里会因为「新解密数 == 0」而整段跳过，导致
    「先用 --no-mp3 只要 FLAC，再改成默认要 MP3」一个 MP3 都生成不出来。
    """
    src = tmp_path / "in"
    src.mkdir()
    _stub_ffmpeg(monkeypatch, tmp_path)
    monkeypatch.setattr(main, "run_decrypt", lambda *a, **k: (0, 0, 3))

    called = []

    def _spy(*args, **kwargs):
        called.append(args)
        return 3, 0

    monkeypatch.setattr(main, "process_audio_to_mp3", _spy)
    assert main.main(["-i", str(src), "-o", str(tmp_path / "out")]) == main.EXIT_OK
    assert called, "已存在跳过的文件也必须触发转码"
