# 第三方组件与许可

TuneLift 自身以 **Apache License 2.0** 发布，全文见 [`LICENSE`](LICENSE)。

发行包里还包含下列第三方组件。它们各自适用自己的许可条款，**不适用**本项目的
Apache-2.0。各许可的完整文本随包放在 [`LICENSES/`](LICENSES/) 目录下。

---

## 一、打包进发行版的组件

### FFmpeg — GNU Lesser General Public License v3.0

- 用途：把解密出来的 FLAC / OGG 转码成 MP3。
- 来源：[BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds) 的 **LGPL** 变体
  （`ffmpeg-master-latest-win64-lgpl.zip`）。
- 对应许可文本：[`LICENSES/FFmpeg-LGPL-3.0.txt`](LICENSES/FFmpeg-LGPL-3.0.txt)
- 可自行核验：`ffmpeg.exe -L` 会自述 "GNU Lesser General Public License ... version 3"；
  `ffmpeg.exe -version` 的 configuration 行里没有 `--enable-gpl`，且
  `--disable-libx264 --disable-libx265 --disable-libxvid --disable-libvidstab` 都是关的。

**本项目只用到它的音频解码与 MP3 编码（libmp3lame）**，用不到 GPL-only 的那些组件，
所以选了 LGPL 构建而不是 GPL 构建——LGPL 免去了「随包提供对应源码」的义务。

义务履行情况：许可证全文已随包分发；`ffmpeg.exe` 作为**独立可执行程序**由本程序
以子进程方式调用，用户可自行替换成别的 ffmpeg 构建。

### Qt 6 / PySide6 — GNU Lesser General Public License v3.0

- 用途：图形界面。
- 来源：[qtproject/pyside-pyside-setup](https://github.com/qtproject/pyside-pyside-setup)（PyPI 上的 `PySide6` / `shiboken6` 包）。
- 对应许可文本：[`LICENSES/Qt-LGPL-3.0-only.txt`](LICENSES/Qt-LGPL-3.0-only.txt)、
  [`LICENSES/Qt-GPL-3.0-only.txt`](LICENSES/Qt-GPL-3.0-only.txt)
  （LGPLv3 以 GPLv3 为基础，两份文本都需要一并提供）。

PySide6 采用三选一授权：`LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`，
**本项目按 LGPL-3.0-only 使用**。

> 注意：PySide6 的 wheel 里**只带了商业许可文本**，LGPLv3 / GPLv3 全文并不包含在内，
> 所以上面两份文本是由本项目自行补入 `LICENSES/` 的。

义务履行情况：

- 许可证全文已随包分发，本文件即为「使用了 LGPL 组件」的显著声明；
- Qt 以 **动态链接**方式使用（`Qt6*.dll` 是独立文件，由 `.pyd` 在运行时加载）；
- 发行包使用 PyInstaller 的 **onedir** 模式，`Qt6*.dll` 是**散落、可被用户替换**的文件，
  用户可以为调试目的替换或重新链接它们。**不得改用 onefile 模式**——那会把 DLL
  封进单个 exe 的内嵌归档，破坏这一要求。

### Frida — wxWindows Library Licence, Version 3.1

- 用途：注入 QQ音乐客户端进程，调用其解密能力。
- 来源：[frida/frida](https://github.com/frida/frida)（PyPI 上的 `frida` 包）。
- 对应许可文本：[`LICENSES/Frida-WXWindows-3.1.txt`](LICENSES/Frida-WXWindows-3.1.txt)

该许可正文基于 GNU Library GPL v2 或更高版本，但附带的 **Exception Notice 第 2 条**
明确允许「以你自己的条款使用、复制、链接、修改和分发基于该库的**二进制目标码**」。
因此 `_frida.pyd` 的打包**不会**对 TuneLift 自身的许可产生传染。

义务履行情况：`COPYING`（许可全文）已随包分发。

### Python — PSF License Agreement

- 用途：运行时（`python312.dll` 等）。
- 来源：[python.org](https://www.python.org/)
- 对应许可文本：[`LICENSES/Python-PSF.txt`](LICENSES/Python-PSF.txt)

PSF 许可证允许自由再分发，要求保留许可与版权声明——已随包分发。

### Microsoft Visual C++ 运行库

- 内容：`VCRUNTIME140.dll`、`VCRUNTIME140_1.dll`、`ucrtbase.dll` 等。
- 依据 Visual Studio 可再发行组件条款，**允许随应用程序一同分发**。

---

## 二、不构成本项目义务的组件

### PyInstaller

本项目用 PyInstaller 把 Python 代码打包成 exe，其引导程序被嵌入产出的可执行文件。
PyInstaller 以 GPL-2.0-or-later 发布，但附有 **Bootloader Exception**：允许把引导程序
嵌入其他程序并**不受 GPL 限制地分发**。官方文档进一步明确，产出的发行包可以采用
任意许可，**无需附带 PyInstaller 的许可文件、也无需任何署名**。

因此本项目的 Apache-2.0 不受其影响。（仅当修改并再分发 PyInstaller 自身时才回到 GPL。）

---

## 三、需要说明的遗留风险

以下是我们在核查中发现、但**无法通过修改本项目解决**的问题，如实记录：

1. **`_frida.pyd` 内部疑似静态链接了 GLib（LGPL-2.1）等第三方库，却没有附带任何声明。**
   静态扫描该文件可见大量 GLib 相关字符串（`G_CREDENTIALS_TYPE_*` 等）却没有任何
   glib 动态库依赖，同时还能看到 OpenSSL、QuickJS、usrsctp、zlib 的痕迹，
   而它只带了一份 wxWindows `COPYING`。这是 Frida 自身打包时就存在的问题，
   本项目作为下游继承之。无法从字符串证据断定确切的链接关系（上游也没有 SBOM）。
2. **PySide6 的 wheel 里还带有 MSVC 运行库和 Mesa 的 `opengl32sw.dll`**（约 20MB），
   各有自己的条款，wheel 内同样没有附带声明。
3. **Qt 的一部分模块仅以 GPLv3 提供**（Qt Lottie Animation、Qt Qml Compiler、
   Qt Quick Timeline 等）。若发行包中混入这些模块的 DLL，按 Qt 自己的说法整个应用
   都需要以 GPL 授权。**本项目只 import `QtCore` / `QtGui` / `QtWidgets`**，
   PyInstaller 理论上不会收集这些模块；打包流程中有一道检查专门确认
   `Qt6Lottie.dll` / `Qt6QmlCompiler.dll` / `Qt6QuickTimeline.dll` **不存在**于产物中。

---

## 四、源码获取

LGPLv3 要求提供对应源码。上述以 LGPL 分发的组件（FFmpeg、Qt/PySide6）均**未经修改**，
其完整对应源码可从各自上游获取：

| 组件 | 源码位置 |
|---|---|
| FFmpeg | <https://github.com/FFmpeg/FFmpeg>（构建方式见 [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds)） |
| Qt / PySide6 | <https://code.qt.io/> 、 <https://github.com/qtproject/pyside-pyside-setup> |

如无法自行获取，可向本项目提出请求，我们会提供对应版本的源码副本。
