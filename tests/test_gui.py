"""GUI.py 的行为测试。

离屏构造真实窗口，不需要显示器、QQ音乐或 ffmpeg。
用的是窗口自身的公开接口，因此重构内部结构不会让这些测试失效。
"""

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
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


def test_build_command_uses_bundled_backend_when_present(window, tmp_path):
    """发行版里后端是同目录的 main.exe。"""
    fake_exe = tmp_path / "main.exe"
    fake_exe.write_bytes(b"")
    window.exe_path = fake_exe

    cmd = window.build_command()
    assert cmd[0] == str(fake_exe)
    assert "-i" in cmd and "-b" in cmd


def test_build_command_falls_back_to_main_py(window):
    """从源码跑时没有 main.exe，应当退回用当前解释器执行 main.py。"""
    window.exe_path = GUI.app_dir() / "这个后端不存在.exe"

    cmd = window.build_command()
    assert cmd[0] == sys.executable
    assert cmd[1].endswith("main.py")


def test_input_field_accepts_a_single_song(window, tmp_path):
    """输入框里直接填一个歌曲文件路径，也要能拼出正确的命令行。"""
    song = tmp_path / "a.mflac"
    song.write_bytes(b"x")
    window.input_edit.setText(str(song))

    cmd = window.build_command()
    assert cmd[cmd.index("-i") + 1] == str(song)


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


def test_follow_source_option_maps_to_the_backend_token(window):
    """下拉框里显示的是中文，传给后端的是 main.py 认识的 source。"""
    window.bitrate_combo.setCurrentText(GUI.FOLLOW_SOURCE_LABEL)

    cmd = window.build_command()
    assert cmd[cmd.index("-b") + 1] == GUI.BITRATE_SOURCE
    assert GUI.BITRATE_SOURCE == "source"


def test_preview_mirrors_command(window):
    window.update_preview()
    assert window.preview.toPlainText() == " ".join(window.build_command())


# --------------------------------------------------------------------------
# 交互
# --------------------------------------------------------------------------
def test_toggle_preview_visibility(window):
    window.show()
    assert not window.preview.isVisible()

    window.toggle_preview_visibility()
    assert window.preview.isVisible()
    assert window.toggle_preview_btn.text() == "▼ 隐藏命令预览"

    window.toggle_preview_visibility()
    assert not window.preview.isVisible()
    assert window.toggle_preview_btn.text() == "▶ 显示命令预览"


def test_backend_is_spawned_with_utf8_output(window, monkeypatch):
    """后端按 UTF-8 写日志，界面按 UTF-8 读；两边必须一致，否则中文会变乱码。

    冻结版后端会自己把 stdout 换成 UTF-8，源码版不会，所以必须由界面显式指定。
    """
    monkeypatch.setattr(GUI.QProcess, "start", lambda self, *a, **k: None)
    window.start_conversion()

    assert window.process is not None
    assert window.process.processEnvironment().value("PYTHONIOENCODING") == "utf-8"


def test_backend_runs_from_the_app_directory(window, monkeypatch):
    """源码模式下后端靠工作目录找 hook_qq_music.js 与 ffmpeg.exe。"""
    monkeypatch.setattr(GUI.QProcess, "start", lambda self, *a, **k: None)
    window.start_conversion()

    assert window.process.workingDirectory() == str(GUI.app_dir())


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


def test_window_icon_loads(window):
    """图标文件缺失或格式坏了不该悄悄过去，得多尺寸可用才算数。"""
    icon = window.windowIcon()
    assert not icon.isNull(), "窗口图标没加载上"
    assert len(icon.availableSizes()) > 1, "ico 里应当包含多个尺寸，供不同 DPI 取用"


# --------------------------------------------------------------------------
# Memphis 视觉机制：只测行为，不测像素
# --------------------------------------------------------------------------
def test_buttons_carry_a_hard_shadow(window):
    """孟菲斯要的是硬边偏移阴影。模糊半径非 0 就说明风格跑偏了。"""
    for button in (window.start_btn, window.stop_btn, window.clear_btn, window.toggle_preview_btn):
        effect = button.graphicsEffect()
        assert effect is not None, "按钮必须有阴影效果"
        assert effect.blurRadius() == 0, "阴影必须是硬边（blurRadius=0），不能是模糊阴影"
        assert effect.offset().x() == GUI.SHADOW_REST


def test_hover_grows_the_shadow(window):
    """规范里 hover 的读法是「阴影变大 + 换色」，不是位移。"""
    button = window.start_btn
    assert button.shadow_target() == GUI.SHADOW_REST

    button.set_shadow(GUI.SHADOW_HOVER)
    assert button.shadow_target() == GUI.SHADOW_HOVER

    button.set_shadow(0.0)
    assert button.shadow_target() == 0.0, "按下时阴影应缩回 0，读作「陷进阴影里」"


def test_cards_expose_decorations(window):
    """孟菲斯不允许空白卡片：每张卡片都要有几何装饰，且各自朝不同方向动。"""
    cards = [w for w in window.findChildren(GUI.MemphisCard)]
    assert cards, "界面上应当有卡片"

    decorated = [c for c in cards if c.decorations()]
    assert len(decorated) >= 2, "至少标题卡与预览卡要有几何装饰"

    for card in decorated:
        vectors = {(d.delta.x(), d.delta.y()) for d in card.decorations()}
        assert len(vectors) > 1 or len(card.decorations()) == 1, (
            "同一张卡片里的装饰必须朝不同方向动（Playful Chaos），不能整齐划一"
        )


def test_decorations_do_not_swallow_hover(window):
    """装饰若吃掉鼠标事件，卡片的 hover 就会时灵时不灵。"""
    for shape in window.findChildren(GUI.Decoration):
        assert shape.testAttribute(Qt.WA_TransparentForMouseEvents), "装饰不能拦截鼠标事件"
