"""TuneLift 图形界面。

只负责收集参数、拼出命令行，再用 QProcess 把同目录的 main.exe 拉起来，
并把它的输出接到日志窗口里。真正的解密 / 转码逻辑都在 main.py。
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QProcess, Qt
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


def app_dir() -> Path:
    """返回程序所在目录。

    打包成 exe 后是 exe 自己的目录，直接跑源码时是本文件所在目录。
    后端的 main.exe、图标、赞赏码.png 都按这个位置去找。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


LIGHT_STYLESHEET = '\n    QWidget {\n        background-color: #f5f7fa;\n        color: #1e293b;\n        font-family: "Segoe UI", "Microsoft YaHei", sans-serif;\n        font-size: 10pt;\n    }\n    #titleLabel {\n        font-size: 22pt;\n        font-weight: bold;\n        color: #0f172a;\n        margin-bottom: 8px;\n    }\n    #label {\n        color: #334155;\n        padding-right: 8px;\n        min-width: 60px;\n    }\n    #inputField {\n        background-color: #ffffff;\n        border: 1px solid #cbd5e1;\n        border-radius: 8px;\n        padding: 6px 10px;\n        color: #1e293b;\n    }\n    #inputField:focus {\n        border-color: #3b82f6;\n        outline: none;\n    }\n    #browseBtn {\n        background-color: #e2e8f0;\n        border: none;\n        border-radius: 8px;\n        padding: 6px 16px;\n        color: #1e293b;\n    }\n    #browseBtn:hover {\n        background-color: #cbd5e1;\n    }\n    #toggleCheck {\n        color: #1e293b;\n        spacing: 8px;\n    }\n    #toggleCheck::indicator {\n        width: 16px;\n        height: 16px;\n        border-radius: 4px;\n        background-color: #ffffff;\n        border: 1px solid #cbd5e1;\n    }\n    #toggleCheck::indicator:checked {\n        background-color: #3b82f6;\n        border-color: #3b82f6;\n    }\n    #combo {\n        background-color: #ffffff;\n        border: 1px solid #cbd5e1;\n        border-radius: 8px;\n        padding: 4px 8px;\n        color: #1e293b;\n        min-width: 70px;\n    }\n    #combo::drop-down {\n        border: none;\n    }\n    #combo QAbstractItemView {\n        background-color: #ffffff;\n        color: #1e293b;\n        selection-background-color: #3b82f6;\n        selection-color: #ffffff;\n    }\n    #formatRadio {\n        color: #1e293b;\n        spacing: 6px;\n        margin-right: 12px;\n    }\n    #formatRadio::indicator {\n        width: 14px;\n        height: 14px;\n        border-radius: 7px;\n        background-color: #ffffff;\n        border: 1px solid #cbd5e1;\n    }\n    #formatRadio::indicator:checked {\n        background-color: #3b82f6;\n        border-color: #3b82f6;\n    }\n    #preview, #log {\n        background-color: #ffffff;\n        border: 1px solid #e2e8f0;\n        border-radius: 12px;\n        padding: 10px;\n        color: #1e293b;\n    }\n    #preview {\n        background-color: #f8fafc;\n    }\n    #log {\n        background-color: #f1f5f9;\n    }\n    #startBtn {\n        background-color: #22c55e;\n        color: #ffffff;\n        border: none;\n        border-radius: 8px;\n        padding: 8px 24px;\n        font-weight: bold;\n    }\n    #startBtn:hover {\n        background-color: #16a34a;\n    }\n    #startBtn:disabled {\n        background-color: #94a3b8;\n        color: #e2e8f0;\n    }\n    #stopBtn {\n        background-color: #ef4444;\n        color: #ffffff;\n        border: none;\n        border-radius: 8px;\n        padding: 8px 24px;\n        font-weight: bold;\n    }\n    #stopBtn:hover {\n        background-color: #dc2626;\n    }\n    #stopBtn:disabled {\n        background-color: #94a3b8;\n        color: #e2e8f0;\n    }\n    #clearBtn, #themeBtn, #togglePreviewBtn, #supportBtn {\n        background-color: #e2e8f0;\n        border: none;\n        border-radius: 8px;\n        padding: 8px 16px;\n        color: #1e293b;\n    }\n    #clearBtn:hover, #themeBtn:hover, #togglePreviewBtn:hover, #supportBtn:hover {\n        background-color: #cbd5e1;\n    }\n    #status {\n        color: #475569;\n    }\n    #tipLabel {\n        color: #475569;\n        background-color: #f1f5f9;\n        border-radius: 8px;\n        padding: 8px 12px;\n        font-size: 9pt;\n    }\n    QScrollBar:vertical {\n        background: #f1f5f9;\n        width: 10px;\n        border-radius: 5px;\n    }\n    QScrollBar::handle:vertical {\n        background: #cbd5e1;\n        border-radius: 5px;\n        min-height: 20px;\n    }\n    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {\n        height: 0;\n    }\n    QMessageBox {\n        background-color: #ffffff;\n    }\n    QMessageBox QPushButton {\n        background-color: #e2e8f0;\n        border: none;\n        border-radius: 6px;\n        padding: 6px 16px;\n        color: #1e293b;\n    }\n    QMessageBox QPushButton:hover {\n        background-color: #cbd5e1;\n    }\n'
DARK_STYLESHEET = '\n    QWidget {\n        background-color: #1e1e2e;\n        color: #cdd6f4;\n        font-family: "Segoe UI", "Microsoft YaHei", sans-serif;\n        font-size: 10pt;\n    }\n    #titleLabel {\n        font-size: 22pt;\n        font-weight: bold;\n        color: #89b4fa;\n        margin-bottom: 8px;\n    }\n    #label {\n        color: #a6adc8;\n        padding-right: 8px;\n        min-width: 60px;\n    }\n    #inputField {\n        background-color: #313244;\n        border: 1px solid #45475a;\n        border-radius: 8px;\n        padding: 6px 10px;\n        color: #cdd6f4;\n    }\n    #inputField:focus {\n        border-color: #89b4fa;\n    }\n    #browseBtn {\n        background-color: #45475a;\n        border: none;\n        border-radius: 8px;\n        padding: 6px 16px;\n        color: #cdd6f4;\n    }\n    #browseBtn:hover {\n        background-color: #585b70;\n    }\n    #toggleCheck {\n        color: #cdd6f4;\n        spacing: 8px;\n    }\n    #toggleCheck::indicator {\n        width: 16px;\n        height: 16px;\n        border-radius: 4px;\n        background-color: #313244;\n        border: 1px solid #45475a;\n    }\n    #toggleCheck::indicator:checked {\n        background-color: #89b4fa;\n        border-color: #89b4fa;\n    }\n    #combo {\n        background-color: #313244;\n        border: 1px solid #45475a;\n        border-radius: 8px;\n        padding: 4px 8px;\n        color: #cdd6f4;\n        min-width: 70px;\n    }\n    #combo::drop-down {\n        border: none;\n    }\n    #combo QAbstractItemView {\n        background-color: #313244;\n        color: #cdd6f4;\n        selection-background-color: #89b4fa;\n    }\n    #formatRadio {\n        color: #cdd6f4;\n        spacing: 6px;\n        margin-right: 12px;\n    }\n    #formatRadio::indicator {\n        width: 14px;\n        height: 14px;\n        border-radius: 7px;\n        background-color: #313244;\n        border: 1px solid #45475a;\n    }\n    #formatRadio::indicator:checked {\n        background-color: #89b4fa;\n        border-color: #89b4fa;\n    }\n    #preview, #log {\n        background-color: #1e1e2e;\n        border: 1px solid #313244;\n        border-radius: 12px;\n        padding: 10px;\n        color: #cdd6f4;\n    }\n    #preview {\n        background-color: #11111b;\n        border-color: #45475a;\n    }\n    #log {\n        background-color: #0f0f1a;\n    }\n    #startBtn {\n        background-color: #a6e3a1;\n        color: #1e1e2e;\n        border: none;\n        border-radius: 8px;\n        padding: 8px 24px;\n        font-weight: bold;\n    }\n    #startBtn:hover {\n        background-color: #94d78f;\n    }\n    #startBtn:disabled {\n        background-color: #45475a;\n        color: #6c7086;\n    }\n    #stopBtn {\n        background-color: #f28b82;\n        color: #1e1e2e;\n        border: none;\n        border-radius: 8px;\n        padding: 8px 24px;\n        font-weight: bold;\n    }\n    #stopBtn:hover {\n        background-color: #e06c6c;\n    }\n    #stopBtn:disabled {\n        background-color: #45475a;\n        color: #6c7086;\n    }\n    #clearBtn, #themeBtn, #togglePreviewBtn, #supportBtn {\n        background-color: #45475a;\n        border: none;\n        border-radius: 8px;\n        padding: 8px 16px;\n        color: #cdd6f4;\n    }\n    #clearBtn:hover, #themeBtn:hover, #togglePreviewBtn:hover, #supportBtn:hover {\n        background-color: #585b70;\n    }\n    #status {\n        color: #a6adc8;\n    }\n    #tipLabel {\n        color: #a6adc8;\n        background-color: #2a2a3e;\n        border-radius: 8px;\n        padding: 8px 12px;\n        font-size: 9pt;\n    }\n    QScrollBar:vertical {\n        background: #1e1e2e;\n        width: 10px;\n        border-radius: 5px;\n    }\n    QScrollBar::handle:vertical {\n        background: #45475a;\n        border-radius: 5px;\n        min-height: 20px;\n    }\n    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {\n        height: 0;\n    }\n    QMessageBox {\n        background-color: #1e1e2e;\n    }\n    QMessageBox QPushButton {\n        background-color: #45475a;\n        border: none;\n        border-radius: 6px;\n        padding: 6px 16px;\n        color: #cdd6f4;\n    }\n    QMessageBox QPushButton:hover {\n        background-color: #585b70;\n    }\n'


class TuneLiftWindow(QMainWindow):
    """主窗口：上半部分是参数设置，下面是命令预览和运行日志。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("TuneLift")
        self.setMinimumSize(950, 720)

        # 后端可执行文件，按约定和本程序放在同一个目录
        self.exe_path = app_dir() / "main.exe"
        self.process = None
        self.running = False
        self.is_dark = False

        self.setup_ui()
        self.apply_stylesheet()

        # 输入输出默认都指向程序自己所在目录，打开就能直接开始
        self.input_edit.setText(str(app_dir()))
        self.root_edit.setText(str(app_dir() / "output"))
        self.mp3_edit.setText(str(app_dir() / "output" / "mp3"))
        self.flac_edit.setText(str(app_dir() / "output" / "flac"))
        self.update_preview()

        self.setWindowIcon(QIcon(str(app_dir() / "tunelift.ico")))

        if not self.exe_path.exists():
            QMessageBox.warning(
                self, "提示", f"未找到 main.exe（后端程序），请确保它与本程序在同一目录。\n当前目录：{app_dir()}"
            )

    def setup_ui(self) -> None:
        """一次性搭好整个界面，并把各控件的信号接到对应的槽上。

        注意：所有控件的 textChanged / toggled 都连到了 update_preview，
        所以这里每加一个控件都可能触发一次 update_preview()。构造期间
        必须保证 update_preview 用到的控件（root_edit、mp3_edit、flac_edit）
        已经创建好，否则会抛 AttributeError。
        """
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)
        # ---- 顶部：标题 + 主题切换 + 支持作者 ----
        title_layout = QHBoxLayout()
        title = QLabel("TuneLift 让音乐自由")
        title.setObjectName("titleLabel")
        title_layout.addWidget(title)
        title_layout.addStretch()
        self.theme_btn = QPushButton("🌙")
        self.theme_btn.setObjectName("themeBtn")
        self.theme_btn.clicked.connect(self.toggle_theme)
        title_layout.addWidget(self.theme_btn)
        self.support_btn = QPushButton("❤️ 支持作者")
        self.support_btn.setObjectName("supportBtn")
        self.support_btn.clicked.connect(self.open_support)
        title_layout.addWidget(self.support_btn)
        main_layout.addLayout(title_layout)
        # ---- 输入目录 ----
        row1 = QHBoxLayout()
        label_input = QLabel("输入目录")
        label_input.setObjectName("label")
        self.input_edit = QLineEdit()
        self.input_edit.setObjectName("inputField")
        self.input_edit.textChanged.connect(self.update_preview)
        self.input_edit.setToolTip(
            "包含 .mflac 或 .mgg 文件的文件夹。<br>建议使用英文路径，避免中文、日文等特殊字符，以防解密失败。"
        )
        browse_input = QPushButton("浏览")
        browse_input.setObjectName("browseBtn")
        browse_input.clicked.connect(lambda: self.browse_folder(self.input_edit))
        row1.addWidget(label_input)
        row1.addWidget(self.input_edit, 1)
        row1.addWidget(browse_input)
        main_layout.addLayout(row1)
        # ---- 输出模式 / MP3 比特率 / 输出格式 ----
        row2 = QHBoxLayout()
        self.independent_check = QCheckBox("使用独立输出目录")
        self.independent_check.setObjectName("toggleCheck")
        self.independent_check.stateChanged.connect(lambda: self.toggle_output_mode())
        self.independent_check.setToolTip("勾选后，MP3 和 FLAC 可分别输出到两个不同的文件夹。")
        row2.addWidget(self.independent_check)
        row2.addSpacing(20)
        label_bitrate = QLabel("比特率")
        label_bitrate.setObjectName("label")
        self.bitrate_combo = QComboBox()
        self.bitrate_combo.addItems(["128k", "160k", "192k", "224k", "256k", "320k"])
        self.bitrate_combo.setCurrentText("192k")
        self.bitrate_combo.setObjectName("combo")
        self.bitrate_combo.currentTextChanged.connect(self.update_preview)
        self.bitrate_combo.setToolTip("数值越高，MP3 音质越好，文件越大。\n推荐 192k（平衡）或 320k（高品质）。")
        row2.addWidget(label_bitrate)
        row2.addWidget(self.bitrate_combo)
        row2.addSpacing(20)
        label_format = QLabel("输出格式")
        label_format.setObjectName("label")
        row2.addWidget(label_format)
        self.format_group = QButtonGroup(self)
        self.format_mp3 = QRadioButton("仅 MP3")
        self.format_flac = QRadioButton("仅 FLAC")
        self.format_both = QRadioButton("两者均保留")
        for btn in (self.format_mp3, self.format_flac, self.format_both):
            btn.setObjectName("formatRadio")
            btn.toggled.connect(self.update_preview)
            self.format_group.addButton(btn)
        self.format_mp3.setToolTip("只生成 MP3 文件，解密后的 FLAC 会自动删除。")
        self.format_flac.setToolTip(
            "只保留 FLAC 无损文件，不生成 MP3。<br>注意：部分歌曲解密后是 OGG 格式，会强制转 MP3 并删除 OGG。"
        )
        self.format_both.setToolTip("同时保留 FLAC 和 MP3 两种格式，适合收藏爱好者。")
        row2.addWidget(self.format_mp3)
        row2.addWidget(self.format_flac)
        row2.addWidget(self.format_both)
        row2.addStretch()
        main_layout.addLayout(row2)
        # ---- 输出目录：两页切换，见 toggle_output_mode ----
        self.output_stack = QStackedWidget()
        self.output_stack.setObjectName("outputStack")
        # 第 0 页（默认）：所有输出都放在同一个根目录下
        page_root = QWidget()
        root_layout = QHBoxLayout(page_root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        label_root = QLabel("根目录")
        label_root.setObjectName("label")
        self.root_edit = QLineEdit()
        self.root_edit.setObjectName("inputField")
        self.root_edit.textChanged.connect(self.update_preview)
        self.root_edit.setToolTip("输出 MP3 和 FLAC 的总文件夹，程序会自动在其下创建 mp3 和 flac 子文件夹。")
        browse_root = QPushButton("浏览")
        browse_root.setObjectName("browseBtn")
        browse_root.clicked.connect(lambda: self.browse_folder(self.root_edit))
        root_layout.addWidget(label_root)
        root_layout.addWidget(self.root_edit, 1)
        root_layout.addWidget(browse_root)
        self.output_stack.addWidget(page_root)
        # 第 1 页：MP3 和 FLAC 各自指定目录
        page_ind = QWidget()
        ind_layout = QVBoxLayout(page_ind)
        ind_layout.setContentsMargins(0, 0, 0, 0)
        ind_layout.setSpacing(6)
        mp3_row = QHBoxLayout()
        label_mp3 = QLabel("MP3 目录")
        label_mp3.setObjectName("label")
        self.mp3_edit = QLineEdit()
        self.mp3_edit.setObjectName("inputField")
        self.mp3_edit.textChanged.connect(self.update_preview)
        self.mp3_edit.setToolTip("存放最终 MP3 文件的文件夹。")
        browse_mp3 = QPushButton("浏览")
        browse_mp3.setObjectName("browseBtn")
        browse_mp3.clicked.connect(lambda: self.browse_folder(self.mp3_edit))
        mp3_row.addWidget(label_mp3)
        mp3_row.addWidget(self.mp3_edit, 1)
        mp3_row.addWidget(browse_mp3)
        ind_layout.addLayout(mp3_row)
        flac_row = QHBoxLayout()
        label_flac = QLabel("FLAC 目录")
        label_flac.setObjectName("label")
        self.flac_edit = QLineEdit()
        self.flac_edit.setObjectName("inputField")
        self.flac_edit.textChanged.connect(self.update_preview)
        self.flac_edit.setToolTip("存放解密后 FLAC 文件的文件夹（仅当选择“两者均保留”或“仅 FLAC”时有效）。")
        browse_flac = QPushButton("浏览")
        browse_flac.setObjectName("browseBtn")
        browse_flac.clicked.connect(lambda: self.browse_folder(self.flac_edit))
        flac_row.addWidget(label_flac)
        flac_row.addWidget(self.flac_edit, 1)
        flac_row.addWidget(browse_flac)
        ind_layout.addLayout(flac_row)
        self.output_stack.addWidget(page_ind)
        self.output_stack.setCurrentIndex(0)
        main_layout.addWidget(self.output_stack)
        # ---- 命令预览 ----
        preview_toggle_layout = QHBoxLayout()
        self.toggle_preview_btn = QPushButton("▶ 显示命令预览")
        self.toggle_preview_btn.setObjectName("togglePreviewBtn")
        self.toggle_preview_btn.clicked.connect(self.toggle_preview_visibility)
        preview_toggle_layout.addWidget(self.toggle_preview_btn)
        preview_toggle_layout.addStretch()
        main_layout.addLayout(preview_toggle_layout)
        self.preview = QTextEdit()
        self.preview.setObjectName("preview")
        self.preview.setReadOnly(True)
        self.preview.setFixedHeight(80)
        self.preview.setFont(QFont("Consolas", 9))
        self.preview.setToolTip("这里是即将执行的命令行预览，你可以核对参数是否正确。")
        self.preview.setVisible(False)
        main_layout.addWidget(self.preview)
        # ---- 运行日志 ----
        self.log = QTextEdit()
        self.log.setObjectName("log")
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 9))
        self.log.setToolTip("程序运行过程中的详细日志，包括解密进度、转码状态和错误信息。")
        main_layout.addWidget(self.log)
        # ---- 使用提示 ----
        tip_label = QLabel(
            "使用提示：\n• 转换前请确保 QQ音乐客户端已在后台运行（否则会提示无法连接）。\n• 建议输入/输出路径使用纯英文，避免中文字符，以免解密失败。\n• 若遇到“No such file or directory”错误，请检查路径中是否包含空格或特殊字符。\n• 选择“仅 FLAC”时，部分 OGG 文件会强制转 MP3 并删除 OGG 源文件。"
        )
        tip_label.setObjectName("tipLabel")
        tip_label.setWordWrap(True)
        main_layout.addWidget(tip_label)
        # ---- 底部：状态文本 + 操作按钮 ----
        bottom = QHBoxLayout()
        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("status")
        self.start_btn = QPushButton("开始执行")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.clicked.connect(self.start_conversion)
        self.start_btn.setToolTip("点击开始转换，处理过程会显示在日志中。")
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.clicked.connect(self.stop_conversion)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setToolTip("终止当前正在进行的转换任务。")
        self.clear_btn = QPushButton("清空日志")
        self.clear_btn.setObjectName("clearBtn")
        self.clear_btn.clicked.connect(self.clear_log)
        bottom.addWidget(self.status_label)
        bottom.addStretch()
        bottom.addWidget(self.start_btn)
        bottom.addWidget(self.stop_btn)
        bottom.addWidget(self.clear_btn)
        main_layout.addLayout(bottom)
        self.format_mp3.setChecked(True)

    def toggle_output_mode(self) -> None:
        """「使用独立输出目录」勾选状态变化时，切换到对应的设置页。"""
        self.output_stack.setCurrentIndex(1 if self.independent_check.isChecked() else 0)

    def toggle_theme(self) -> None:
        """在明 / 暗主题之间切换。"""
        self.is_dark = not self.is_dark
        self.apply_stylesheet()
        self.theme_btn.setText("☀️" if self.is_dark else "🌙")

    def apply_stylesheet(self) -> None:
        """按当前主题给窗口套上样式表。"""
        self.setStyleSheet(DARK_STYLESHEET if self.is_dark else LIGHT_STYLESHEET)

    def toggle_preview_visibility(self) -> None:
        """显示 / 隐藏命令预览框。"""
        visible = not self.preview.isVisible()
        self.preview.setVisible(visible)
        self.toggle_preview_btn.setText("▼ 隐藏命令预览" if visible else "▶ 显示命令预览")

    def browse_folder(self, line_edit: QLineEdit) -> None:
        """弹出目录选择框，选中后写入 line_edit。

        如果改的是输入目录，顺手把输出根目录也调到它下面的 output/，
        省得用户再选一次。
        """
        dir_path = QFileDialog.getExistingDirectory(self, "选择文件夹", line_edit.text())
        if dir_path:
            line_edit.setText(dir_path)
            if line_edit is self.input_edit:
                self.root_edit.setText(str(Path(dir_path) / "output"))

    def get_output_format(self) -> str:
        """按单选框返回 'mp3' / 'flac' / 'both'。"""
        if self.format_mp3.isChecked():
            return "mp3"
        if self.format_flac.isChecked():
            return "flac"
        return "both"

    def build_command(self) -> list[str]:
        """按当前界面设置拼出后端命令行参数。"""
        exe = str(self.exe_path)
        input_dir = self.input_edit.text().strip()
        if not input_dir:
            input_dir = str(app_dir())
        bitrate = self.bitrate_combo.currentText()
        output_format = self.get_output_format()
        cmd = [exe, "-i", input_dir, "-b", bitrate]
        if self.independent_check.isChecked():
            mp3_dir = self.mp3_edit.text().strip()
            flac_dir = self.flac_edit.text().strip()
            if not mp3_dir:
                mp3_dir = str(app_dir() / "output" / "mp3")
            if not flac_dir:
                flac_dir = str(app_dir() / "output" / "flac")
            cmd += ["--mp3-dir", mp3_dir, "--flac-dir", flac_dir]
        else:
            root_dir = self.root_edit.text().strip()
            if not root_dir:
                root_dir = str(app_dir() / "output")
            cmd += ["-o", root_dir]
        if output_format == "flac":
            cmd.append("--no-mp3")
            return cmd
        if output_format == "both":
            cmd.append("--keep-flac")
        return cmd

    def update_preview(self) -> None:
        """把 build_command() 的结果显示到预览框里。"""
        cmd = self.build_command()
        self.preview.setText(" ".join(cmd))

    def start_conversion(self) -> None:
        """启动后端进程，并把它 stdout/stderr 接到日志窗口。"""
        if not self.exe_path.exists():
            QMessageBox.warning(self, "错误", "未找到 TuneLift.exe，请确保它位于程序目录。")
            return None
        if self.running:
            return None
        cmd = self.build_command()
        self.process = QProcess(self)
        self.process.setProgram(cmd[0])
        self.process.setArguments(cmd[1:])
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.process_finished)
        self.running = True
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_label.setText("运行中...")
        self.log.append(">>> " + " ".join(cmd))
        self.process.start()

    def stop_conversion(self) -> None:
        """中断正在运行的转换。"""
        if self.process:
            if self.running:
                self.process.kill()
                self.process.waitForFinished(2000)
                self.log.append("⚠️ 用户终止任务")
                self.status_label.setText("已停止")
                self.running = False
                self.start_btn.setEnabled(True)
                self.stop_btn.setEnabled(False)
                return None
            return None

    def read_output(self) -> None:
        """QProcess 有新输出时触发，按行追加到日志窗口。"""
        data = self.process.readAllStandardOutput()
        text = data.data().decode("utf-8", errors="replace")
        for line in text.splitlines():
            if not line.strip():
                continue
            self.log.append(line.strip())

    def process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        """后端进程结束时触发：恢复按钮状态并记录结果。

        exit_code / exit_status 由 QProcess.finished 信号传入；
        exit_status 用不上，保留只是为了对上信号签名。
        """
        self.running = False
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if exit_code == 0:
            self.status_label.setText("完成")
            self.log.append("✅ 执行完成")
            return None
        self.status_label.setText(f"""异常退出 (代码 {exit_code})""")
        self.log.append(f"""❌ 执行失败，返回码：{exit_code}""")

    def clear_log(self) -> None:
        """清空日志窗口。"""
        self.log.clear()

    def open_support(self) -> None:
        """弹出赞赏码对话框。"""
        img_path = app_dir() / "赞赏码.png"
        if not img_path.exists():
            QMessageBox.information(self, "提示", "未找到赞赏码图片，请将 '赞赏码.png' 放在程序目录下。")
            return None
        dialog = QDialog(self)
        dialog.setWindowTitle("支持作者")
        dialog.setFixedSize(600, 720)
        layout = QVBoxLayout(dialog)
        label = QLabel("如果你觉得 TuneLift 对你有帮助，欢迎扫码赞赏！")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        pixmap = QPixmap(str(img_path))
        pixmap = pixmap.scaled(550, 550, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        img_label = QLabel()
        img_label.setPixmap(pixmap)
        img_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(img_label)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignCenter)
        dialog.exec()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TuneLiftWindow()
    window.show()
    sys.exit(app.exec())
