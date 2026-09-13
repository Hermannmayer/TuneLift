"""TuneLift 图形界面 —— Memphis 风格。

界面只做三件事：收集参数、拼出命令行、用 QProcess 把同目录的 main.exe 拉起来，
再把它打到 stdout/stderr 的内容接进日志窗口。真正的解密与转码逻辑都在 main.py。

视觉上遵循孟菲斯（Memphis）设计语言：高饱和撞色、4px 纯黑粗边框、
无模糊的硬边偏移阴影、几何装饰，以及 hover 时"零件各自乱跑"的游乐场感。
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QEvent,
    QParallelAnimationGroup,
    QPoint,
    QPointF,
    QProcess,
    QPropertyAnimation,
    Qt,
)
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
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

# ---------------------------------------------------------------------------
# 孟菲斯调色板与度量
# ---------------------------------------------------------------------------
RED = "#ff6b6b"
YELLOW = "#feca57"
CYAN = "#48dbfb"
PINK = "#ff9ff3"
GREEN = "#1dd1a1"
PAGE = "#fef9ef"
WHITE = "#ffffff"
INK = "#000000"

BORDER_WIDTH = 4  # 规范要求 border-4，禁止细边框
SHADOW_REST = 5.0  # shadow-[5px_5px_0px_0px_#000]
SHADOW_HOVER = 8.0  # hover 时阴影变大
MOTION_MS = 150  # 规范要求 duration-150，干脆的波普玩具手感

# ---------------------------------------------------------------------------
# 单一样式表。注意每个块都必须带选择器——Qt 遇到第一条没有选择器的声明会
# 把整张表丢掉，而且是静默丢掉。
# ---------------------------------------------------------------------------
MEMPHIS_QSS = f"""
QWidget {{
    background: transparent;
    color: {INK};
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 10pt;
}}

QMainWindow, #page {{
    background: {PAGE};
}}

/* ---- 卡片：4px 黑边、直角、无圆角 ---- */
#card {{
    border: {BORDER_WIDTH}px solid {INK};
    border-radius: 0;
}}
#card[fill="yellow"] {{ background: {YELLOW}; }}
#card[fill="white"]  {{ background: {WHITE}; }}
#card[fill="cyan"]   {{ background: {CYAN}; }}
#card[fill="pink"]   {{ background: {PINK}; }}
#card[fill="green"]  {{ background: {GREEN}; }}

/* ---- 文字 ---- */
#titleLabel {{
    font-size: 22pt;
    font-weight: 900;
    color: {INK};
}}
#subtitle {{
    font-size: 10pt;
    font-weight: 700;
    color: {INK};
}}
#label {{
    font-weight: 900;
    color: {INK};
}}
#status {{
    background: {YELLOW};
    border: {BORDER_WIDTH}px solid {INK};
    font-weight: 900;
    padding: 6px 14px;
}}
#tipLabel {{
    font-size: 9pt;
    font-weight: 600;
    color: {INK};
}}

/* ---- 输入框：粗边、直角 ---- */
#inputField {{
    background: {WHITE};
    border: {BORDER_WIDTH}px solid {INK};
    border-radius: 0;
    padding: 6px 10px;
    selection-background-color: {PINK};
}}
#inputField:hover {{ background: {YELLOW}; }}
#inputField:focus {{ background: {WHITE}; border-color: {INK}; }}

/* ---- 下拉框：必须显式干掉原生的灰色箭头，否则就违反"禁止单调配色" ---- */
#combo {{
    background: {WHITE};
    border: {BORDER_WIDTH}px solid {INK};
    border-radius: 0;
    padding: 4px 8px;
    min-width: 84px;
}}
#combo::drop-down {{
    background: {YELLOW};
    border-left: {BORDER_WIDTH}px solid {INK};
    width: 26px;
}}
#combo::down-arrow {{
    image: none;
}}
#combo QAbstractItemView {{
    background: {WHITE};
    border: {BORDER_WIDTH}px solid {INK};
    selection-background-color: {PINK};
    selection-color: {INK};
}}

/* ---- 复选框 / 单选框：指示器也要上色，不能用系统默认的灰 ---- */
#toggleCheck {{
    font-weight: 900;
    spacing: 8px;
}}
#toggleCheck::indicator {{
    width: 16px;
    height: 16px;
    border: {BORDER_WIDTH}px solid {INK};
    background: {WHITE};
}}
#toggleCheck::indicator:checked {{ background: {GREEN}; }}

#formatRadio {{
    font-weight: 900;
    spacing: 6px;
    margin-right: 14px;
}}
#formatRadio::indicator {{
    width: 14px;
    height: 14px;
    border: {BORDER_WIDTH}px solid {INK};
    border-radius: 7px;
    background: {WHITE};
}}
#formatRadio::indicator:checked {{ background: {RED}; }}

/* ---- 按钮：底色 + 粗边；hover 换撞色，按下再换一种 ---- */
#startBtn    {{ background: {GREEN};  }}
#stopBtn     {{ background: {RED};    }}
#clearBtn    {{ background: {CYAN};   }}
#togglePreviewBtn {{ background: {PINK}; }}
#browseBtn   {{ background: {YELLOW}; }}

#startBtn, #stopBtn, #clearBtn, #togglePreviewBtn, #browseBtn {{
    color: {INK};
    border: {BORDER_WIDTH}px solid {INK};
    border-radius: 0;
    padding: 7px 16px;
    font-weight: 900;
}}

#startBtn:hover, #stopBtn:hover, #clearBtn:hover,
#togglePreviewBtn:hover, #browseBtn:hover {{
    background: {PINK};
}}
#startBtn:pressed, #stopBtn:pressed, #clearBtn:pressed,
#togglePreviewBtn:pressed, #browseBtn:pressed {{
    background: {YELLOW};
}}
#startBtn:disabled, #stopBtn:disabled {{
    background: {PAGE};
    color: {INK};
    border: {BORDER_WIDTH}px dotted {INK};
}}

/* ---- 预览与日志：等宽字体必须在样式表里声明，否则会被 QSS 的 font-family 盖掉 ---- */
#preview, #log {{
    background: {WHITE};
    border: {BORDER_WIDTH}px solid {INK};
    border-radius: 0;
    padding: 8px;
    font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 9pt;
}}
#preview {{ background: {PAGE}; }}

/* ---- 滚动条：黑边、无灰色凹槽 ---- */
QScrollBar:vertical {{
    background: {PAGE};
    border-left: {BORDER_WIDTH}px solid {INK};
    width: 14px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {CYAN};
    border: {BORDER_WIDTH}px solid {INK};
    min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
    height: 0;
}}

/* ---- 对话框 ---- */
QMessageBox {{
    background: {PAGE};
}}
QMessageBox QPushButton {{
    background: {YELLOW};
    border: {BORDER_WIDTH}px solid {INK};
    border-radius: 0;
    padding: 6px 16px;
    font-weight: 900;
}}
QMessageBox QPushButton:hover {{ background: {PINK}; }}
"""


def app_dir() -> Path:
    """返回程序所在目录。

    打包成 exe 后是 exe 自己的目录，直接跑源码时是本文件所在目录。
    后端的 main.exe、图标、赞赏码.png 都按这个位置去找。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


# ---------------------------------------------------------------------------
# 硬阴影：孟菲斯的阴影是「纯黑、无模糊、整体偏移」，不是柔和投影。
# QSS 没有 box-shadow，用 blurRadius=0 的 QGraphicsDropShadowEffect 等价实现。
# ---------------------------------------------------------------------------
class _HardShadow:
    """给控件挂一个可动画的硬边阴影。"""

    def _install_shadow(self) -> None:
        effect = QGraphicsDropShadowEffect(self)
        effect.setBlurRadius(0)  # 0 才是硬边
        effect.setOffset(QPointF(SHADOW_REST, SHADOW_REST))
        effect.setColor(QColor(INK))
        self.setGraphicsEffect(effect)

        # 必须留一个 Python 引用。内联创建后直接 setGraphicsEffect 的话，
        # 渲染时阴影会完全不出现——而 graphicsEffect() 依旧返回非 None、
        # 参数看着也对，非常难查。
        self._shadow = effect
        self._shadow_target = SHADOW_REST
        self._shadow_anim = QPropertyAnimation(effect, b"offset", self)
        self._shadow_anim.setDuration(MOTION_MS)
        self._shadow_anim.setEasingCurve(QEasingCurve.OutCubic)

    def shadow_target(self) -> float:
        """当前阴影偏移的目标值。"""
        return self._shadow_target

    def set_shadow(self, offset: float) -> None:
        """把阴影偏移动画到 offset（0 表示阴影收回，视觉上"陷进去"）。"""
        self._shadow_target = offset
        self._shadow_anim.stop()
        self._shadow_anim.setStartValue(self._shadow.offset())
        self._shadow_anim.setEndValue(QPointF(offset, offset))
        self._shadow_anim.start()


class MemphisButton(_HardShadow, QPushButton):
    """孟菲斯按钮：hover 阴影变大，按下时缩回阴影里。"""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self._install_shadow()
        # 用信号而不是重写 mousePressEvent：键盘激活也会走到这里，
        # 而且 setEnabled() 之类的程序化状态变化不会让视觉错位。
        self.pressed.connect(lambda: self.set_shadow(0.0))
        self.released.connect(self._settle_shadow)

    def _settle_shadow(self) -> None:
        self.set_shadow(SHADOW_HOVER if self.underMouse() else SHADOW_REST)

    def enterEvent(self, event: QEvent) -> None:
        self.set_shadow(SHADOW_HOVER)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self.set_shadow(0.0 if self.isDown() else SHADOW_REST)
        super().leaveEvent(event)


# ---------------------------------------------------------------------------
# 几何装饰
# ---------------------------------------------------------------------------
class Decoration(QWidget):
    """卡片上的一个几何图形。

    位置由卡片在 hover 时驱动，所以它必须是绝对定位的子控件（不进布局），
    而且必须对鼠标透明——否则它会吃掉卡片的 hover，装饰就会时灵时不灵。
    """

    def __init__(self, shape: str, color: str, size: int = 20, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._shape = shape
        self._color = QColor(color)
        self._angle = 0.0
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)

    # 属性名不能和读写方法重名，否则 PySide 会直接抛错
    def _get_angle(self) -> float:
        return self._angle

    def _set_angle(self, value: float) -> None:
        if value != self._angle:
            self._angle = value
            self.update()

    angle = Property(float, _get_angle, _set_angle)

    def paintEvent(self, _event: QEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        width, height = self.width(), self.height()
        painter.translate(width / 2, height / 2)
        painter.rotate(self._angle)
        painter.translate(-width / 2, -height / 2)

        painter.setPen(QPen(QColor(INK), BORDER_WIDTH))
        painter.setBrush(self._color)
        inset = BORDER_WIDTH / 2

        if self._shape == "circle":
            painter.drawEllipse(inset, inset, width - BORDER_WIDTH, height - BORDER_WIDTH)
        elif self._shape == "triangle":
            painter.drawPolygon(
                QPolygonF(
                    [
                        QPointF(width / 2, inset),
                        QPointF(width - inset, height - inset),
                        QPointF(inset, height - inset),
                    ]
                )
            )
        elif self._shape == "diamond":
            painter.drawPolygon(
                QPolygonF(
                    [
                        QPointF(width / 2, inset),
                        QPointF(width - inset, height / 2),
                        QPointF(width / 2, height - inset),
                        QPointF(inset, height / 2),
                    ]
                )
            )
        elif self._shape == "wave":
            path = QPainterPath()
            path.moveTo(inset, height * 0.65)
            path.quadTo(width * 0.25, inset, width * 0.5, height * 0.5)
            path.quadTo(width * 0.75, height - inset, width - inset, height * 0.35)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
        elif self._shape == "bars":
            step = width / 3.0
            painter.setBrush(Qt.NoBrush)
            for index in range(3):
                x = inset + index * step
                painter.drawLine(QPointF(x, inset), QPointF(x, height - inset))


class _CardDecoration:
    """一张卡片上某个装饰的完整描述：停在哪、hover 时往哪跑、转多少度。"""

    def __init__(self, shape: Decoration, origin: tuple[float, float], delta: QPoint, spin: float) -> None:
        self.shape = shape
        self.origin = origin  # 用比例表示，这样缩放窗口后位置依然正确
        self.delta = delta
        self.spin = spin


class MemphisCard(_HardShadow, QFrame):
    """粗边框 + 硬阴影的卡片，内部可以放几何装饰。"""

    def __init__(self, fill: str = "white", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # 卡片必须继承 QFrame：普通 QWidget 子类不会画 QSS 背景
        self.setObjectName("card")
        self.setProperty("fill", fill)
        self._install_shadow()
        self._decorations: list[_CardDecoration] = []
        self._chaos: QParallelAnimationGroup | None = None

    def decorations(self) -> list[_CardDecoration]:
        """本卡片上的装饰清单（供测试与布局使用）。"""
        return list(self._decorations)

    def add_decoration(
        self, shape: str, color: str, origin: tuple[float, float], delta: QPoint, spin: float, size: int = 20
    ) -> Decoration:
        """放一个装饰。delta 与 spin 必须逐个别扭，这正是 Playful Chaos 的来源。"""
        item = Decoration(shape, color, size, self)
        record = _CardDecoration(item, origin, delta, spin)
        self._decorations.append(record)
        item.show()
        self._place_decorations()
        return item

    def _place_decorations(self) -> None:
        for record in self._decorations:
            record.shape.move(
                round(record.origin[0] * self.width()),
                round(record.origin[1] * self.height()),
            )
            record.shape.angle = 0.0

    def resizeEvent(self, event: QEvent) -> None:
        super().resizeEvent(event)
        if self._chaos is not None:
            self._chaos.stop()  # 别让跑到一半的动画把装饰留在卡片外
        self._place_decorations()

    def enterEvent(self, event: QEvent) -> None:
        self._scatter(True)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._scatter(False)
        super().leaveEvent(event)

    def _ensure_chaos(self) -> None:
        """一次性建好装饰的动画对象并反复复用。

        每次 hover 都新建的话，动画对象会不断堆积——它们挂在卡片上，
        只有卡片销毁时才回收。
        """
        if self._chaos is not None:
            return
        self._chaos = QParallelAnimationGroup(self)
        for record in self._decorations:
            for prop in (b"pos", b"angle"):
                animation = QPropertyAnimation(record.shape, prop, self._chaos)
                animation.setDuration(MOTION_MS)
                animation.setEasingCurve(QEasingCurve.OutCubic)
                self._chaos.addAnimation(animation)

    def _scatter(self, entered: bool) -> None:
        """Playful Chaos：每个装饰朝各自的方向跑、转各自的角度，不统一。"""
        if not self._decorations:
            return
        self._ensure_chaos()

        for index, record in enumerate(self._decorations):
            home = QPoint(round(record.origin[0] * self.width()), round(record.origin[1] * self.height()))
            move = self._chaos.animationAt(index * 2)
            turn = self._chaos.animationAt(index * 2 + 1)
            move.setStartValue(record.shape.pos())
            move.setEndValue(home + record.delta if entered else home)
            turn.setStartValue(record.shape.angle)
            turn.setEndValue(record.spin if entered else 0.0)

        self._chaos.stop()
        self._chaos.start()


class MemphisBackground(QWidget):
    """页面底色 + 背景几何图案。

    图案直接画在 paintEvent 里，不做成子控件——子控件会挡鼠标事件，
    而且数量一多就没必要。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("page")
        self._pulse = 0.0
        # 固定的非对称布点，不用随机数，保证每次渲染都一样
        self._shapes = [
            ("circle", 0.04, 0.10, 26, CYAN, QPointF(-8, -6)),
            ("diamond", 0.92, 0.06, 22, RED, QPointF(7, 5)),
            ("triangle", 0.88, 0.88, 24, YELLOW, QPointF(-6, 8)),
            ("wave", 0.06, 0.82, 34, GREEN, QPointF(9, -5)),
            ("bars", 0.50, 0.04, 26, PINK, QPointF(-5, 7)),
        ]

    def _get_pulse(self) -> float:
        return self._pulse

    def _set_pulse(self, value: float) -> None:
        self._pulse = value
        self.update()

    pulse = Property(float, _get_pulse, _set_pulse)

    def _animate_pulse(self, target: float) -> None:
        animation = QPropertyAnimation(self, b"pulse", self)
        animation.setDuration(MOTION_MS)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.setStartValue(self._pulse)
        animation.setEndValue(target)
        animation.start()

    def enterEvent(self, event: QEvent) -> None:
        self._animate_pulse(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._animate_pulse(0.0)
        super().leaveEvent(event)

    def paintEvent(self, _event: QEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(PAGE))

        for shape, fx, fy, size, color, drift in self._shapes:
            drift_now = drift * self._pulse
            painter.save()
            painter.translate(fx * self.width() + drift_now.x(), fy * self.height() + drift_now.y())
            painter.setPen(QPen(QColor(INK), BORDER_WIDTH))
            painter.setBrush(QColor(color))
            half = size / 2

            if shape == "circle":
                painter.drawEllipse(QPointF(0, 0), half, half)
            elif shape == "diamond":
                painter.drawPolygon(
                    QPolygonF(
                        [
                            QPointF(0, -half),
                            QPointF(half, 0),
                            QPointF(0, half),
                            QPointF(-half, 0),
                        ]
                    )
                )
            elif shape == "triangle":
                painter.drawPolygon(
                    QPolygonF(
                        [
                            QPointF(0, -half),
                            QPointF(half, half),
                            QPointF(-half, half),
                        ]
                    )
                )
            elif shape == "wave":
                path = QPainterPath()
                path.moveTo(-half, 0)
                path.quadTo(-half / 2, -half, 0, 0)
                path.quadTo(half / 2, half, half, 0)
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(path)
            else:  # bars
                painter.setBrush(Qt.NoBrush)
                for index in (-1, 0, 1):
                    x = index * half * 0.7
                    painter.drawLine(QPointF(x, -half), QPointF(x, half))
            painter.restore()


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------
class TuneLiftWindow(QMainWindow):
    """主窗口：左栏参数，右栏命令预览与运行日志。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("TuneLift")
        self.setMinimumSize(1100, 780)

        # 后端可执行文件，按约定和本程序放在同一个目录
        self.exe_path = app_dir() / "main.exe"
        self.process: QProcess | None = None
        self.running = False

        self.setup_ui()
        # 样式表必须在所有控件（含它们的 objectName 与动态属性）都就位之后再应用，
        # 否则 Qt 不会重新 polish，选择器匹配不上。
        self.setStyleSheet(MEMPHIS_QSS)

        # 输入输出默认都指向程序自己所在目录，打开就能直接开始
        self.input_edit.setText(str(app_dir()))
        self.root_edit.setText(str(app_dir() / "output"))
        self.mp3_edit.setText(str(app_dir() / "output" / "mp3"))
        self.flac_edit.setText(str(app_dir() / "output" / "flac"))
        self.update_preview()

        self.setWindowIcon(QIcon(str(app_dir() / "tunelift.ico")))

        if not self.exe_path.exists():
            QMessageBox.warning(
                self,
                "提示",
                f"未找到 main.exe（后端程序），请确保它与本程序在同一目录。\n当前目录：{app_dir()}",
            )

    # -- 界面搭建 ----------------------------------------------------------
    def setup_ui(self) -> None:
        """一次性建好全部控件，最后再统一接线。

        构造期间不连任何信号，是为了从根上杜绝「信号打进半成品窗口」——
        update_preview() 会读取多个控件，任何一个还没建好都会抛 AttributeError。
        """
        page = MemphisBackground()
        self.setCentralWidget(page)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(26, 22, 26, 24)  # 留够阴影所需的 ≥8px 空隙
        outer.setSpacing(16)

        outer.addWidget(self._build_header())

        columns = QHBoxLayout()
        columns.setSpacing(18)
        columns.addLayout(self._build_left_column(), 1)
        columns.addLayout(self._build_right_column(), 1)
        outer.addLayout(columns, 1)

        outer.addLayout(self._build_bottom_bar())

        # 最后一句必须是这个：它会触发 toggled → update_preview → build_command，
        # 而 build_command 需要读 root_edit / mp3_edit / flac_edit，此时它们都已就绪。
        self.format_mp3.setChecked(True)

    def _build_header(self) -> MemphisCard:
        card = MemphisCard("yellow")
        card.setFixedHeight(88)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 12, 150, 12)
        layout.setSpacing(2)

        title = QLabel("TuneLift")
        title.setObjectName("titleLabel")
        font = title.font()
        font.setLetterSpacing(QFont.AbsoluteSpacing, -1.0)  # QSS 不支持 letter-spacing
        title.setFont(font)

        subtitle = QLabel("把 QQ音乐的加密音频解出来，转成通用的 FLAC / MP3")
        subtitle.setObjectName("subtitle")

        layout.addWidget(title)
        layout.addWidget(subtitle)

        card.add_decoration("circle", RED, (0.80, 0.18), QPoint(16, -10), -35.0, 26)
        card.add_decoration("triangle", CYAN, (0.90, 0.55), QPoint(-18, 9), 28.0, 24)
        card.add_decoration("wave", GREEN, (0.72, 0.62), QPoint(11, -18), -22.0, 30)
        return card

    def _build_left_column(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(16)
        column.addWidget(self._build_params_card())
        column.addWidget(self._build_tips_card())
        column.addStretch()
        return column

    def _build_params_card(self) -> MemphisCard:
        card = MemphisCard("white")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 16, 16)
        layout.setSpacing(12)

        # 输入目录
        row_input = QHBoxLayout()
        row_input.setSpacing(10)
        label_input = QLabel("输入目录")
        label_input.setObjectName("label")
        self.input_edit = QLineEdit()
        self.input_edit.setObjectName("inputField")
        self.input_edit.setToolTip(
            "包含 .mflac 或 .mgg 文件的文件夹。建议使用英文路径，避免中文、日文等特殊字符，以防解密失败。"
        )
        browse_input = MemphisButton("浏览")
        browse_input.setObjectName("browseBtn")
        self._browse_input = browse_input
        row_input.addWidget(label_input)
        row_input.addWidget(self.input_edit, 1)
        row_input.addWidget(browse_input)
        layout.addLayout(row_input)

        # 输出模式 + 比特率
        row_mode = QHBoxLayout()
        row_mode.setSpacing(10)
        self.independent_check = QCheckBox("使用独立输出目录")
        self.independent_check.setObjectName("toggleCheck")
        self.independent_check.setToolTip("勾选后，MP3 和 FLAC 可分别输出到两个不同的文件夹。")
        label_bitrate = QLabel("比特率")
        label_bitrate.setObjectName("label")
        self.bitrate_combo = QComboBox()
        self.bitrate_combo.setObjectName("combo")
        self.bitrate_combo.addItems(["128k", "160k", "192k", "224k", "256k", "320k"])
        self.bitrate_combo.setCurrentText("192k")
        self.bitrate_combo.setToolTip("数值越高，MP3 音质越好，文件越大。\n推荐 192k（平衡）或 320k（高品质）。")
        row_mode.addWidget(self.independent_check)
        row_mode.addStretch()
        row_mode.addWidget(label_bitrate)
        row_mode.addWidget(self.bitrate_combo)
        layout.addLayout(row_mode)

        # 输出格式
        row_format = QHBoxLayout()
        row_format.setSpacing(6)
        label_format = QLabel("输出格式")
        label_format.setObjectName("label")
        self.format_group = QButtonGroup(self)
        self.format_mp3 = QRadioButton("仅 MP3")
        self.format_flac = QRadioButton("仅 FLAC")
        self.format_both = QRadioButton("两者均保留")
        for button in (self.format_mp3, self.format_flac, self.format_both):
            button.setObjectName("formatRadio")
            self.format_group.addButton(button)
        self.format_mp3.setToolTip("只生成 MP3 文件，解密后的 FLAC 会自动删除。")
        self.format_flac.setToolTip(
            "只保留 FLAC 无损文件，不生成 MP3。<br>注意：部分歌曲解密后是 OGG 格式，会强制转 MP3 并删除 OGG。"
        )
        self.format_both.setToolTip("同时保留 FLAC 和 MP3 两种格式，适合收藏爱好者。")
        row_format.addWidget(label_format)
        row_format.addWidget(self.format_mp3)
        row_format.addWidget(self.format_flac)
        row_format.addWidget(self.format_both)
        row_format.addStretch()
        layout.addLayout(row_format)

        # 输出位置：两页切换，第 0 页是根目录模式，第 1 页是独立目录模式
        self.output_stack = QStackedWidget()
        self.output_stack.setObjectName("outputStack")
        self.output_stack.addWidget(self._build_root_page())
        self.output_stack.addWidget(self._build_independent_page())
        self.output_stack.setCurrentIndex(0)
        layout.addWidget(self.output_stack)

        card.add_decoration("diamond", YELLOW, (0.965, 0.06), QPoint(-9, 12), 40.0, 18)
        return card

    def _build_root_page(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        label = QLabel("根目录")
        label.setObjectName("label")
        self.root_edit = QLineEdit()
        self.root_edit.setObjectName("inputField")
        self.root_edit.setToolTip("输出 MP3 和 FLAC 的总文件夹，程序会自动在其下创建 mp3 和 flac 子文件夹。")
        browse = MemphisButton("浏览")
        browse.setObjectName("browseBtn")
        self._browse_root = browse
        layout.addWidget(label)
        layout.addWidget(self.root_edit, 1)
        layout.addWidget(browse)
        return page

    def _build_independent_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        row_mp3 = QHBoxLayout()
        row_mp3.setSpacing(10)
        label_mp3 = QLabel("MP3 目录")
        label_mp3.setObjectName("label")
        self.mp3_edit = QLineEdit()
        self.mp3_edit.setObjectName("inputField")
        self.mp3_edit.setToolTip("存放最终 MP3 文件的文件夹。")
        browse_mp3 = MemphisButton("浏览")
        browse_mp3.setObjectName("browseBtn")
        row_mp3.addWidget(label_mp3)
        row_mp3.addWidget(self.mp3_edit, 1)
        row_mp3.addWidget(browse_mp3)
        layout.addLayout(row_mp3)

        row_flac = QHBoxLayout()
        row_flac.setSpacing(10)
        label_flac = QLabel("FLAC 目录")
        label_flac.setObjectName("label")
        self.flac_edit = QLineEdit()
        self.flac_edit.setObjectName("inputField")
        self.flac_edit.setToolTip("存放解密后 FLAC 文件的文件夹（仅当选择「两者均保留」或「仅 FLAC」时有效）。")
        browse_flac = MemphisButton("浏览")
        browse_flac.setObjectName("browseBtn")
        row_flac.addWidget(label_flac)
        row_flac.addWidget(self.flac_edit, 1)
        row_flac.addWidget(browse_flac)
        layout.addLayout(row_flac)

        page.mp3_browse = browse_mp3
        page.flac_browse = browse_flac
        self._browse_mp3 = browse_mp3
        self._browse_flac = browse_flac
        return page

    def _build_tips_card(self) -> MemphisCard:
        card = MemphisCard("cyan")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 16, 16)
        label = QLabel(
            "使用提示：\n"
            "• 转换前请确保 QQ音乐客户端已在后台运行（否则会提示无法连接）。\n"
            "• 建议输入/输出路径使用纯英文，避免中文字符，以免解密失败。\n"
            "• 若遇到「No such file or directory」错误，请检查路径中是否包含空格或特殊字符。\n"
            "• 选择「仅 FLAC」时，部分 OGG 文件会强制转 MP3 并删除 OGG 源文件。"
        )
        label.setObjectName("tipLabel")
        label.setWordWrap(True)
        layout.addWidget(label)
        card.add_decoration("triangle", WHITE, (0.94, 0.82), QPoint(-12, -9), -30.0, 20)
        return card

    def _build_right_column(self) -> QVBoxLayout:
        column = QVBoxLayout()
        # 右栏整体下沉一截，让两栏错开——孟菲斯不喜欢对称规整
        column.setContentsMargins(0, 30, 0, 0)
        column.setSpacing(16)
        column.addWidget(self._build_preview_card())
        column.addWidget(self._build_log_card(), 1)
        return column

    def _build_preview_card(self) -> MemphisCard:
        card = MemphisCard("pink")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 16, 16)
        layout.setSpacing(8)

        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.toggle_preview_btn = MemphisButton("▶ 显示命令预览")
        self.toggle_preview_btn.setObjectName("togglePreviewBtn")
        bar.addWidget(self.toggle_preview_btn)
        bar.addStretch()
        layout.addLayout(bar)

        self.preview = QTextEdit()
        self.preview.setObjectName("preview")
        self.preview.setReadOnly(True)
        self.preview.setFixedHeight(80)
        self.preview.setToolTip("这里是即将执行的命令行预览，你可以核对参数是否正确。")
        self.preview.setVisible(False)
        layout.addWidget(self.preview)

        card.add_decoration("circle", WHITE, (0.90, 0.10), QPoint(-14, 11), 33.0, 22)
        return card

    def _build_log_card(self) -> MemphisCard:
        card = MemphisCard("white")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 16, 16)
        layout.setSpacing(8)

        self.log = QTextEdit()
        self.log.setObjectName("log")
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(140)
        self.log.setToolTip("程序运行过程中的详细日志，包括解密进度、转码状态和错误信息。")
        layout.addWidget(self.log)

        card.add_decoration("bars", CYAN, (0.955, 0.05), QPoint(-13, -8), -26.0, 22)
        return card

    def _build_bottom_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(12)

        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("status")

        self.start_btn = MemphisButton("开始执行")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.setToolTip("点击开始转换，处理过程会显示在日志中。")
        self.stop_btn = MemphisButton("停止")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setToolTip("终止当前正在进行的转换任务。")
        self.clear_btn = MemphisButton("清空日志")
        self.clear_btn.setObjectName("clearBtn")

        bar.addWidget(self.status_label)
        bar.addStretch()
        bar.addWidget(self.start_btn)
        bar.addWidget(self.stop_btn)
        bar.addWidget(self.clear_btn)

        self._wire_signals()
        return bar

    def _wire_signals(self) -> None:
        """集中接线。

        放在最后统一做：构造期间不连信号，就不会有信号打进还没建好的窗口。
        """
        self.input_edit.textChanged.connect(self.update_preview)
        self.root_edit.textChanged.connect(self.update_preview)
        self.mp3_edit.textChanged.connect(self.update_preview)
        self.flac_edit.textChanged.connect(self.update_preview)
        self.bitrate_combo.currentTextChanged.connect(self.update_preview)
        self.format_mp3.toggled.connect(self.update_preview)
        self.format_flac.toggled.connect(self.update_preview)
        self.format_both.toggled.connect(self.update_preview)
        self.independent_check.stateChanged.connect(self.toggle_output_mode)

        self.toggle_preview_btn.clicked.connect(self.toggle_preview_visibility)
        self.start_btn.clicked.connect(self.start_conversion)
        self.stop_btn.clicked.connect(self.stop_conversion)
        self.clear_btn.clicked.connect(self.clear_log)

        # 四个「浏览」按钮各自绑到对应的输入框上。
        # 这里传的是控件对象本身，因为 browse_folder 用 `is` 做身份比较，
        # 判断改的是不是输入目录。
        self._browse_input.clicked.connect(lambda: self.browse_folder(self.input_edit))
        self._browse_root.clicked.connect(lambda: self.browse_folder(self.root_edit))
        self._browse_mp3.clicked.connect(lambda: self.browse_folder(self.mp3_edit))
        self._browse_flac.clicked.connect(lambda: self.browse_folder(self.flac_edit))

    # -- 行为 --------------------------------------------------------------
    def toggle_output_mode(self) -> None:
        """「使用独立输出目录」勾选状态变化时，切换到对应的设置页。"""
        self.output_stack.setCurrentIndex(1 if self.independent_check.isChecked() else 0)

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
        elif output_format == "both":
            cmd.append("--keep-flac")
        return cmd

    def update_preview(self) -> None:
        """把 build_command() 的结果显示到预览框里。

        故意不收参数：它同时连着 textChanged(str)、currentTextChanged(str)、
        toggled(bool)，由 PySide6 负责截断多余的实参。
        """
        self.preview.setText(" ".join(self.build_command()))

    def start_conversion(self) -> None:
        """启动后端进程，并把它 stdout/stderr 接到日志窗口。"""
        if not self.exe_path.exists():
            QMessageBox.warning(self, "错误", "未找到 main.exe，请确保它位于程序目录。")
            return
        if self.running:
            return

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
        if self.process and self.running:
            self.process.kill()
            self.process.waitForFinished(2000)
            self.log.append("⚠️ 用户终止任务")
            self.status_label.setText("已停止")
            self.running = False
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

    def read_output(self) -> None:
        """QProcess 有新输出时触发，按行追加到日志窗口。"""
        raw = self.process.readAllStandardOutput()
        text = raw.data().decode("utf-8", errors="replace")
        for line in text.splitlines():
            if line.strip():
                self.log.append(line.strip())

    def process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        """后端进程结束时触发：恢复按钮状态并记录结果。

        exit_status 用不上，保留参数只是为了对上 QProcess.finished 的信号签名。
        """
        self.running = False
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if exit_code == 0:
            self.status_label.setText("完成")
            self.log.append("✅ 执行完成")
        else:
            self.status_label.setText(f"异常退出 (代码 {exit_code})")
            self.log.append(f"❌ 执行失败，返回码：{exit_code}")

    def clear_log(self) -> None:
        """清空日志窗口。"""
        self.log.clear()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TuneLiftWindow()
    window.show()
    sys.exit(app.exec())
