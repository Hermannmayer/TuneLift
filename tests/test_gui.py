"""GUI.py 的行为测试。

离屏构造真实窗口，不需要显示器、QQ音乐或 ffmpeg。
用的是窗口自身的公开接口，因此重构内部结构不会让这些测试失效。
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import GUI  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(qapp, monkeypatch):
    """构造窗口。

    源码目录里没有 main.exe（那是 build.bat 的产物），__init__ 会弹出模态
    警告框把测试卡死，所以这里把弹窗打桩掉。
    """
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    win = GUI.TuneLiftWindow()
    yield win
    win.close()


# --------------------------------------------------------------------------
# 输出格式与命令行拼装
# --------------------------------------------------------------------------
def test_default_format_is_mp3(window):
    assert window.get_output_format() == "mp3"
    assert window.format_mp3.isChecked()


def test_radio_buttons_drive_output_format(window):
    window.format_flac.setChecked(True)
    assert window.get_output_format() == "flac"
    window.format_both.setChecked(True)
    assert window.get_output_format() == "both"


def test_build_command_starts_with_backend(window):
    cmd = window.build_command()
    assert cmd[0] == str(window.exe_path)
    assert "-i" in cmd and "-b" in cmd


def test_build_command_root_mode_uses_output_flag(window):
    cmd = window.build_command()
    assert "-o" in cmd
    assert "--mp3-dir" not in cmd


def test_build_command_both_keeps_flac(window):
    window.format_both.setChecked(True)
    assert "--keep-flac" in window.build_command()


def test_build_command_flac_only_uses_no_mp3(window):
    window.format_flac.setChecked(True)
    cmd = window.build_command()
    assert "--no-mp3" in cmd
    assert "--keep-flac" not in cmd


def test_build_command_independent_dirs(window):
    window.independent_check.setChecked(True)
    cmd = window.build_command()
    assert "--mp3-dir" in cmd and "--flac-dir" in cmd
    assert "-o" not in cmd


def test_independent_check_switches_page(window):
    assert window.output_stack.currentIndex() == 0
    window.independent_check.setChecked(True)
    assert window.output_stack.currentIndex() == 1
    window.independent_check.setChecked(False)
    assert window.output_stack.currentIndex() == 0


def test_bitrate_combo_feeds_command(window):
    window.bitrate_combo.setCurrentText("320k")
    cmd = window.build_command()
    assert cmd[cmd.index("-b") + 1] == "320k"


def test_preview_mirrors_command(window):
    window.update_preview()
    assert window.preview.toPlainText() == " ".join(window.build_command())


# --------------------------------------------------------------------------
# 交互
# --------------------------------------------------------------------------
def test_toggle_theme_round_trips(window):
    original = window.is_dark
    window.toggle_theme()
    assert window.is_dark is not original
    window.toggle_theme()
    assert window.is_dark is original


def test_toggle_preview_visibility(window):
    window.show()
    assert not window.preview.isVisible()

    window.toggle_preview_visibility()
    assert window.preview.isVisible()
    assert window.toggle_preview_btn.text() == "▼ 隐藏命令预览"

    window.toggle_preview_visibility()
    assert not window.preview.isVisible()
    assert window.toggle_preview_btn.text() == "▶ 显示命令预览"


def test_clear_log(window):
    window.log.append("一些日志")
    window.clear_log()
    assert window.log.toPlainText() == ""


def test_start_buttons_initial_state(window):
    assert window.start_btn.isEnabled()
    assert not window.stop_btn.isEnabled()
    assert not window.running


# --------------------------------------------------------------------------
# 路径
# --------------------------------------------------------------------------
def test_backend_path_sits_next_to_app_dir(window):
    assert window.exe_path == GUI.app_dir() / "main.exe"


def test_initial_dirs_point_under_app_dir(window):
    assert window.root_edit.text() == str(GUI.app_dir() / "output")
    assert window.mp3_edit.text() == str(GUI.app_dir() / "output" / "mp3")
    assert window.flac_edit.text() == str(GUI.app_dir() / "output" / "flac")
