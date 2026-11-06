import os

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QMessageBox, QCheckBox, QFileDialog, QDialog,
    QTextEdit, QProgressBar, QGraphicsDropShadowEffect
)
from PyQt5.QtGui import QPixmap, QColor
from PyQt5.QtCore import Qt, pyqtSignal

from utils import (
    is_supported_file, is_png_file, format_file_size,
    format_compression_ratio, get_resource_path
)
from config_manager import ConfigManager
from ui_theme import (
    current, current_mode, theme_label,
    checkbox_style, pill_toggle_style, primary_btn, ghost_btn, icon_btn,
    card_style, title_bar_style, drop_zone_style, drop_zone_hover_style,
    result_style, status_bar_style, text_box_style, chip_style, meter_style,
)
from version import VERSION, RELEASE_DATE, UPDATE_LOG


class HelpDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("关于 TinyPNG Pro")
        self.setMinimumSize(480, 560)
        self.resize(520, 600)
        self.setStyleSheet(f"""
            QDialog {{
                background: {current.bg};
                font-family: {current.font};
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("TinyPNG Pro")
        title.setStyleSheet(f"""
            font-family: {current.font};
            font-size: {current.size_2xl};
            font-weight: 700;
            color: {current.fg};
            padding: 2px 0;
        """)
        layout.addWidget(title)

        ver_pill = QLabel(f"v{VERSION} · {RELEASE_DATE}")
        ver_pill.setStyleSheet(chip_style('info'))
        layout.addWidget(ver_pill)

        t = QTextEdit()
        t.setReadOnly(True)
        t.setFrameShape(QTextEdit.NoFrame)
        t.setStyleSheet(text_box_style())
        t.setHtml(f"""
<div style="font-family: {current.font}; color: {current.muted}; line-height: 1.8;">
<p><b style="color: {current.fg};">关于</b></p>
<p style="margin-left: 8px;">使用 TinyPNG 在线服务智能压缩图片，支持 PNG、JPEG 和 WebP 格式。通过智能算法在保持视觉质量的同时减小文件大小。</p>
<br>
<p><b style="color: {current.primary};">主要功能</b></p>
<ul style="margin-left: 14px;">
<li>拖放压缩 — 直接拖入图片文件快速压缩</li>
<li>批量处理 — 支持同时选择多个图片文件</li>
<li>文件夹监控 — 自动监控指定文件夹的新图片</li>
<li>多 API 密钥 — 支持配置多个 TinyPNG API 密钥</li>
<li>系统托盘 — 支持最小化到系统托盘</li>
<li>开机自启 — 可选开机自动启动</li>
<li>日志记录 — 可查看操作和压缩日志</li>
</ul>
<br>
<p><b style="color: {current.primary};">使用方法</b></p>
<ol style="margin-left: 14px;">
<li>在设置中配置 TinyPNG API 密钥</li>
<li>拖入图片或点击「选择图像」按钮</li>
<li>勾选「自动压缩」监控文件夹中的新图片</li>
<li>勾选「替换原文件」直接覆盖原图</li>
</ol>
<br>
<p><b style="color: {current.primary};">更新日志</b></p>
<pre style="margin-left: 8px; font-family: {current.mono_font}; font-size: 11px; white-space: pre-wrap; color: {current.dim};">{UPDATE_LOG}</pre>
<br>
<p style="color: {current.secondary};">提示：免费 API 每月 500 张压缩额度。更多额度请访问 tinypng.com 购买。</p>
</div>
""")
        layout.addWidget(t, 1)

        close_btn = QPushButton("关闭")
        close_btn.setFixedSize(90, 34)
        close_btn.setStyleSheet(ghost_btn())
        close_btn.clicked.connect(self.accept)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)


class MainWindow(QMainWindow):
    show_settings = pyqtSignal()
    auto_compress_toggled = pyqtSignal(bool)
    replace_original_toggled = pyqtSignal(bool)
    always_on_top_toggled = pyqtSignal(bool)
    exit_application = pyqtSignal()
    theme_changed = pyqtSignal(str)   # 主题切换后通知外层统一重建
    closed = pyqtSignal()             # 窗口已关闭（供外层清空引用）

    def __init__(self, compression_manager, parent=None):
        super().__init__(parent)
        self.config = ConfigManager()
        self.manager = compression_manager
        self.help_dialog = None
        self._batch_id = None
        self._batch_total = 0
        self._batch_done = 0
        self._dragging = False
        self._drag_offset = None
        self._connect_manager()
        self.init_ui()

    # ---------------- 与压缩管线的对接 ----------------
    def _connect_manager(self):
        self.manager.compressionStarted.connect(self.on_compression_started)
        self.manager.compressionFinished.connect(self.on_compression_finished)
        self.manager.batchFinished.connect(self.on_batch_finished)
        self.manager.queueChanged.connect(self.on_queue_changed)

    def _disconnect_manager(self):
        for signal, slot in (
            (self.manager.compressionStarted, self.on_compression_started),
            (self.manager.compressionFinished, self.on_compression_finished),
            (self.manager.batchFinished, self.on_batch_finished),
            (self.manager.queueChanged, self.on_queue_changed),
        ):
            try:
                signal.disconnect(slot)
            except Exception:
                pass

    def closeEvent(self, event):
        self._disconnect_manager()
        if self.help_dialog is not None:
            self.help_dialog.close()
            self.help_dialog = None
        self.closed.emit()
        super().closeEvent(event)

    # ---------------- 窗口拖拽（按住任意空白区域即可移动窗口，而非仅标题栏） ----------------
    def mousePressEvent(self, event):
        # 子控件（按钮/输入框等）会自行消费按下事件，只有落在空白区域的按下才会冒泡到这里，
        # 因此这里接受的拖拽不会干扰按钮点击或拖放区操作。
        if (event.button() == Qt.LeftButton
                and not self.isMaximized() and not self.isFullScreen()):
            self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
            self._dragging = True
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and (event.buttons() & Qt.LeftButton):
            self.move(event.globalPos() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging and event.button() == Qt.LeftButton:
            self._dragging = False
            self._drag_offset = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ---------------- 构建界面 ----------------
    def init_ui(self):
        self.setWindowTitle("TinyPNG Pro")
        self.setMinimumSize(480, 560)
        self.resize(520, 600)
        self.setAcceptDrops(True)
        self.setStyleSheet(f"""
            QMainWindow {{
                background: {current.bg};
                font-family: {current.font};
            }}
            QMainWindow::separator {{
                background: transparent;
                width: 0px;
                height: 0px;
            }}
        """)

        central = QWidget()
        central.setObjectName("central")
        central.setStyleSheet(f"QWidget#central {{ background: {current.bg}; }}")
        self.setCentralWidget(central)
        ml = QVBoxLayout(central)
        ml.setContentsMargins(16, 14, 16, 14)
        ml.setSpacing(10)

        ml.addWidget(self._build_header())
        ml.addWidget(self._build_drop_zone(), 1)
        ml.addWidget(self._build_result_card())
        ml.addWidget(self._build_status_bar())

        self._apply_window_flags()

    def _add_shadow(self, widget, blur=24, dy=8):
        effect = QGraphicsDropShadowEffect(widget)
        r, g, b, a = current.shadow
        effect.setColor(QColor(r, g, b, a))
        effect.setBlurRadius(blur)
        effect.setOffset(0, dy)
        widget.setGraphicsEffect(effect)

    def _build_header(self):
        hdr = QFrame()
        hdr.setObjectName("headerBar")
        hdr.setFixedHeight(48)
        hdr.setStyleSheet(title_bar_style())
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(14, 0, 10, 0)
        hl.setSpacing(4)

        title_lbl = QLabel("TinyPNG")
        title_lbl.setStyleSheet(f"""
            font-family: {current.font};
            font-size: {current.size_xl};
            font-weight: 700;
            letter-spacing: 0.3px;
            color: {current.fg};
        """)
        title_pro = QLabel("Pro")
        title_pro.setStyleSheet(f"""
            font-family: {current.font};
            font-size: {current.size_xl};
            font-weight: 800;
            color: {current.primary2};
        """)
        ver_hdr = QLabel(f"v{VERSION}")
        ver_hdr.setStyleSheet(f"""
            font-family: {current.font};
            font-size: {current.size_xs};
            color: {current.dim};
            padding-left: 6px;
        """)
        hl.addWidget(title_lbl)
        hl.addWidget(title_pro)
        hl.addWidget(ver_hdr)
        hl.addStretch()

        self.always_on_top_check = QCheckBox("置顶")
        self.always_on_top_check.setChecked(self.config.get_always_on_top())
        self.always_on_top_check.setStyleSheet(checkbox_style())
        self.always_on_top_check.stateChanged.connect(self.on_always_on_top_toggle)
        hl.addWidget(self.always_on_top_check)

        self.theme_btn = QPushButton("☾" if current_mode() == 'dark' else "☀")
        self.theme_btn.setFixedSize(32, 32)
        self.theme_btn.setStyleSheet(icon_btn())
        self.theme_btn.setToolTip(f"当前 {theme_label()}模式，点击切换")
        self.theme_btn.clicked.connect(self.toggle_theme)
        hl.addWidget(self.theme_btn)

        self.help_btn = QPushButton("?")
        self.help_btn.setFixedSize(32, 32)
        self.help_btn.setStyleSheet(icon_btn())
        self.help_btn.setToolTip("帮助 / 关于")
        self.help_btn.clicked.connect(self.show_help)
        hl.addWidget(self.help_btn)

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setFixedSize(32, 32)
        self.settings_btn.setStyleSheet(icon_btn())
        self.settings_btn.setToolTip("设置")
        self.settings_btn.clicked.connect(self.show_settings.emit)
        hl.addWidget(self.settings_btn)
        return hdr

    def _build_drop_zone(self):
        drop = QFrame()
        drop.setAcceptDrops(True)
        drop.setMinimumHeight(230)
        drop.setStyleSheet(drop_zone_style())
        self.drop_zone = drop
        dl = QVBoxLayout(drop)
        dl.setContentsMargins(20, 18, 20, 18)
        dl.setSpacing(8)

        icon = QLabel()
        pp = get_resource_path('icon.png')
        if os.path.exists(pp):
            icon.setPixmap(QPixmap(pp).scaled(56, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("background: transparent; border: none;")
        dl.addWidget(icon)

        dt = QLabel("拖放图片到此处压缩")
        dt.setAlignment(Qt.AlignCenter)
        dt.setStyleSheet(f"""
            font-family: {current.font};
            font-size: {current.size_lg};
            font-weight: 600;
            color: {current.fg};
        """)
        dl.addWidget(dt)

        sub_hint = QLabel("支持 PNG / JPEG / WebP")
        sub_hint.setAlignment(Qt.AlignCenter)
        sub_hint.setStyleSheet(f"""
            font-family: {current.font};
            font-size: {current.size_xs};
            color: {current.dim};
        """)
        dl.addWidget(sub_hint)

        bw = QWidget()
        bl = QHBoxLayout(bw)
        bl.setContentsMargins(0, 8, 0, 0)
        self.select_btn = QPushButton("选择图像")
        self.select_btn.setFixedSize(300, 40)
        self.select_btn.setCursor(Qt.PointingHandCursor)
        self.select_btn.setStyleSheet(primary_btn())
        self.select_btn.clicked.connect(self.select_files)
        bl.addStretch()
        bl.addWidget(self.select_btn)
        bl.addStretch()
        dl.addWidget(bw)

        self._add_shadow(drop, blur=22, dy=8)
        return drop

    def _build_result_card(self):
        rc = QFrame()
        rc.setStyleSheet(card_style())
        rc.setMinimumHeight(112)
        rl = QVBoxLayout(rc)
        rl.setContentsMargins(16, 14, 16, 14)
        rl.setSpacing(8)

        chip_row = QHBoxLayout()
        chip_row.addStretch()
        self.status_chip = QLabel("就绪")
        self.status_chip.setStyleSheet(chip_style('idle'))
        chip_row.addWidget(self.status_chip)
        chip_row.addStretch()
        rl.addLayout(chip_row)

        self.result_label = QLabel("等待图片压缩…")
        self.result_label.setAlignment(Qt.AlignCenter)
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet(result_style())
        rl.addWidget(self.result_label)

        self.detail_label = QLabel("可拖放图片，或在设置中开启文件夹自动压缩")
        self.detail_label.setAlignment(Qt.AlignCenter)
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet(f"""
            font-family: {current.font};
            font-size: {current.size_xs};
            color: {current.dim};
        """)
        rl.addWidget(self.detail_label)

        self._add_shadow(rc, blur=18, dy=6)
        return rc

    def _build_status_bar(self):
        bc = QFrame()
        bc.setStyleSheet(status_bar_style())
        v = QVBoxLayout(bc)
        v.setContentsMargins(14, 10, 12, 10)
        v.setSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(14)

        self.auto_compress_check = QCheckBox("自动压缩")
        self.auto_compress_check.setChecked(self.config.get_auto_compression_enabled())
        self.auto_compress_check.setStyleSheet(pill_toggle_style())
        self.auto_compress_check.stateChanged.connect(self.on_auto_compress_toggle)
        row.addWidget(self.auto_compress_check)

        self.replace_original_check = QCheckBox("替换原文件")
        self.replace_original_check.setChecked(self.config.get_replace_original())
        self.replace_original_check.setStyleSheet(pill_toggle_style())
        self.replace_original_check.stateChanged.connect(self.on_replace_original_toggle)
        row.addWidget(self.replace_original_check)

        row.addStretch()

        self.queue_label = QLabel("")
        self.queue_label.setStyleSheet(f"""
            font-family: {current.font};
            font-size: {current.size_xs};
            color: {current.dim};
        """)
        self.queue_label.setVisible(False)
        row.addWidget(self.queue_label)

        self.compression_count_label = QLabel()
        self.compression_count_label.setToolTip("本月免费压缩额度")
        self.compression_count_label.setStyleSheet(f"""
            font-family: {current.font};
            font-size: {current.size_xs};
            color: {current.primary2};
            font-weight: 700;
        """)
        row.addWidget(self.compression_count_label)

        self.exit_btn = QPushButton("退出")
        self.exit_btn.setFixedSize(58, 28)
        self.exit_btn.setStyleSheet(ghost_btn())
        self.exit_btn.clicked.connect(self.exit_application.emit)
        row.addWidget(self.exit_btn)
        v.addLayout(row)

        self.quota_meter = QProgressBar()
        self.quota_meter.setFixedHeight(6)
        self.quota_meter.setTextVisible(False)
        self.quota_meter.setRange(0, 500)
        self.quota_meter.setStyleSheet(meter_style())
        v.addWidget(self.quota_meter)

        self._refresh_count()
        return bc

    def _apply_window_flags(self):
        flags = self.windowFlags()
        if self.config.get_always_on_top():
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    def _set_chip(self, kind, text):
        self.status_chip.setText(text)
        self.status_chip.setStyleSheet(chip_style(kind))

    def _refresh_count(self):
        count = self.config.get_compression_count()
        self.compression_count_label.setText(f"{count}/500")
        self.quota_meter.setValue(min(count, 500))

    # ---------------- 主题 ----------------
    def toggle_theme(self):
        """切换 明/暗 主题并通知外层统一重建。"""
        new_mode = 'light' if current_mode() == 'dark' else 'dark'
        self.config.set_theme(new_mode)
        self.theme_changed.emit(new_mode)

    def rebuild(self):
        """以当前激活主题重建整个窗口 UI（用于主题切换后刷新）。"""
        central = self.centralWidget()
        if central is not None:
            self.takeCentralWidget()
            central.deleteLater()
        if self.help_dialog is not None:
            self.help_dialog.close()
            self.help_dialog = None
        self._batch_id = None
        self._batch_total = 0
        self._batch_done = 0
        self.init_ui()

    # ---------------- 交互 ----------------
    def on_always_on_top_toggle(self, state):
        enabled = state == Qt.Checked
        self.config.set_always_on_top(enabled)
        self.always_on_top_toggled.emit(enabled)
        self._apply_window_flags()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.drop_zone.setStyleSheet(drop_zone_hover_style())

    def dragLeaveEvent(self, event):
        self.drop_zone.setStyleSheet(drop_zone_style())

    def dropEvent(self, event):
        self.drop_zone.setStyleSheet(drop_zone_style())
        files = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        self.process_files(files)

    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择图片", "", "图片 (*.webp *.png *.jpg *.jpeg)")
        if files:
            self.process_files(files)

    def process_files(self, files):
        """把文件交给后台压缩管线（界面线程只做校验与入队，不再阻塞）。"""
        key = self.config.get_current_api_key()
        if not key or not key.strip():
            QMessageBox.warning(self, "API 密钥未配置", "请先在设置中配置 TinyPNG API 密钥")
            return

        invalid = [f for f in files if not is_supported_file(f)]
        only_png = self.config.get_only_png()
        skipped = ([f for f in files if is_supported_file(f) and not is_png_file(f)]
                   if only_png else [])
        if invalid:
            QMessageBox.warning(self, "格式不支持", "请拖入 WebP / PNG / JPEG 图片")
            return
        if skipped:
            names = ", ".join(os.path.basename(f) for f in skipped[:5])
            more = f" 等 {len(skipped)} 个文件" if len(skipped) > 5 else ""
            QMessageBox.information(self, "已跳过非PNG",
                                    f"已开启「只压缩 PNG」，跳过非 PNG 文件：{names}{more}")

        candidates = [f for f in files if f not in invalid and f not in skipped]
        if not candidates:
            return

        batch_id = self.manager.add_batch(candidates)
        if batch_id is None:
            QMessageBox.information(self, "无可压缩文件", "所选文件中没有可压缩的图片")
            return

        self._batch_id = batch_id
        self._batch_total = len(candidates)
        self._batch_done = 0
        self._set_chip('info', f"压缩中 0/{self._batch_total}")
        self.result_label.setText("正在压缩…")
        self.detail_label.setText(f"共 {self._batch_total} 个文件排队处理")

    # ---------------- 压缩管线信号 ----------------
    def on_compression_started(self, basename, is_auto):
        if is_auto:
            self._set_chip('info', "自动压缩中…")
            self.result_label.setText(f"<b>{basename}</b>")
            self.detail_label.setText("后台自动压缩处理中")

    def on_compression_finished(self, basename, ok, message, is_auto):
        if not is_auto and self._batch_id is not None:
            self._batch_done += 1
            self._set_chip('info', f"压缩中 {self._batch_done}/{self._batch_total}")
            self.result_label.setText(f"<b>{basename}</b>")
        elif is_auto:
            self._set_chip('ok' if ok else 'err', "自动压缩完成" if ok else "自动压缩失败")
            self.result_label.setText(f"<b>{basename}</b>")
            self.detail_label.setText(message)
        self._refresh_count()

    def on_batch_finished(self, batch_id, summary, is_auto):
        total = summary.get('total', 0)
        ok = summary.get('ok', 0)
        failed = summary.get('failed', 0)
        orig = summary.get('original_size', 0)
        comp = summary.get('compressed_size', 0)
        elapsed = summary.get('elapsed', 0.0)

        if not is_auto:
            self._batch_id = None
            self._batch_total = 0
            self._batch_done = 0

        if ok > 0:
            ratio = format_compression_ratio(orig, comp)
            detail = (f"{format_file_size(orig)} → {format_file_size(comp)}"
                      f" · 节省 {ratio} · 耗时 {elapsed:.1f}s")
            if failed:
                detail += f" · 失败 {failed}"
            self._set_chip('ok', f"批量完成 {ok}/{total}")
            self.result_label.setText("✓ 压缩完成")
            self.detail_label.setText(detail)
        else:
            self._set_chip('err', "批量失败")
            self.result_label.setText("✗ 压缩失败")
            self.detail_label.setText(
                "；".join(summary.get('errors', [])[:3]) or "请检查 API 密钥与网络连接")
        self._refresh_count()

    def on_queue_changed(self, size):
        if size > 0:
            self.queue_label.setText(f"排队 {size}")
            self.queue_label.setVisible(True)
        else:
            self.queue_label.setVisible(False)

    def on_auto_compress_toggle(self, state):
        self.config.set_auto_compression_enabled(state == Qt.Checked)
        self.auto_compress_toggled.emit(state == Qt.Checked)

    def on_replace_original_toggle(self, state):
        self.config.set_replace_original(state == Qt.Checked)
        self.replace_original_toggled.emit(state == Qt.Checked)

    def show_help(self):
        if not self.help_dialog:
            self.help_dialog = HelpDialog()
        self.help_dialog.show()
        self.help_dialog.raise_()
        self.help_dialog.activateWindow()

    def update_settings(self):
        """设置变更后刷新界面状态（阻断信号，避免回写配置造成循环）。"""
        for chk, value in (
            (self.auto_compress_check, self.config.get_auto_compression_enabled()),
            (self.replace_original_check, self.config.get_replace_original()),
            (self.always_on_top_check, self.config.get_always_on_top()),
        ):
            chk.blockSignals(True)
            chk.setChecked(value)
            chk.blockSignals(False)
        self._refresh_count()
