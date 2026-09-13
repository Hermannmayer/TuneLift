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
    """源码模式下资源锚定在 main.py 所在目录，而不是当前工作目录。

    锚在工作目录的话，从别的路径调用就会找不到 ffmpeg 与钩子脚本。
    """
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.chdir(tmp_path)  # 故意换到别的地方，结果不该受影响
    expected = os.path.join(os.path.dirname(os.path.abspath(main.__file__)), "hook.js")
    assert main.resource_path("hook.js") == expected


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


# --------------------------------------------------------------------------
# 输入既可以是目录，也可以是单个歌曲文件
# --------------------------------------------------------------------------
def test_resolve_input_accepts_a_directory(tmp_path):
    src = tmp_path / "in"
    src.mkdir()
    assert main.resolve_input(str(src)) == src


def test_resolve_input_accepts_a_single_song(tmp_path):
    song = tmp_path / "a.mflac"
    song.write_bytes(b"x")
    assert main.resolve_input(str(song)) == song


def test_resolve_input_rejects_other_file_types(tmp_path):
    other = tmp_path / "a.mp3"
    other.write_bytes(b"x")
    with pytest.raises(main.TuneLiftError):
        main.resolve_input(str(other))


def test_resolve_input_rejects_missing_path(tmp_path):
    with pytest.raises(main.TuneLiftError):
        main.resolve_input(str(tmp_path / "nope"))


def test_collect_sources_walks_a_directory(tmp_path):
    src = tmp_path / "in"
    (src / "sub").mkdir(parents=True)
    (src / "a.mflac").write_bytes(b"x")
    (src / "sub" / "b.mgg").write_bytes(b"x")
    (src / "c.mp3").write_bytes(b"x")  # 不是加密格式，不该被收进来

    assert sorted(p.name for p in main.collect_sources(src)) == ["a.mflac", "b.mgg"]


def test_collect_sources_accepts_a_single_file(tmp_path):
    song = tmp_path / "a.mflac"
    song.write_bytes(b"x")
    assert main.collect_sources(song) == [song]


def test_main_accepts_a_single_song(monkeypatch, tmp_path):
    """-i 直接给一个 .mflac 文件也要能跑，不必先给它建目录。"""
    song = tmp_path / "a.mflac"
    song.write_bytes(b"x")
    _stub_ffmpeg(monkeypatch, tmp_path)

    seen = {}

    def _spy(path, _out):
        seen["path"] = path
        return 1, 0, 0

    monkeypatch.setattr(main, "run_decrypt", _spy)
    monkeypatch.setattr(main, "process_audio_to_mp3", lambda *a, **k: (0, 0))

    assert main.main(["-i", str(song), "-o", str(tmp_path / "out")]) == main.EXIT_OK
    assert seen["path"] == str(song)


def test_main_rejects_a_non_encrypted_file(monkeypatch, tmp_path):
    other = tmp_path / "a.mp3"
    other.write_bytes(b"x")
    _stub_ffmpeg(monkeypatch, tmp_path)
    assert main.main(["-i", str(other)]) == main.EXIT_BAD_USAGE


def test_run_decrypt_leaves_everything_alone_when_nothing_encrypted(tmp_path):
    """目录里没有加密文件时，连输出目录都不该建，输入目录也一个字不动。"""
    src = tmp_path / "in"
    src.mkdir()
    (src / "song.mp3").write_bytes(b"x")
    (src / "notes.txt").write_text("x", encoding="utf-8")
    out = tmp_path / "out"

    assert main.run_decrypt(str(src), str(out)) == (0, 0, 0)
    assert not out.exists(), "没有加密文件时不该创建输出目录"
    assert sorted(p.name for p in src.iterdir()) == ["notes.txt", "song.mp3"]
