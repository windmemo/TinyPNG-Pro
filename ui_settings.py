from PyQt5.QtWidgets import (
    QDialog, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QListWidget,
    QSpinBox, QFileDialog, QGroupBox,
    QRadioButton, QTextEdit, QScrollArea, QButtonGroup
)
from PyQt5.QtCore import QThread, pyqtSignal
from config_manager import ConfigManager
from startup_manager import StartupManager
from tinypng_api import TinyPNGAPI
from version import VERSION, RELEASE_DATE, UPDATE_LOG
from logging_system import logger
from ui_theme import (
    current, set_theme, current_mode, theme_label,
    checkbox_style, radio_style, primary_btn, accent_outline_btn, ghost_btn,
    input_style, spin_style, group_style, list_style, tab_style, label_style,
    scroll_area_style,
)

# ============================================================
# 界面样式统一由 ui_theme 管理(支持 明亮/夜间 主题切换)
# ============================================================


class APIValidator(QThread):
    validated = pyqtSignal(bool, int)
    def __init__(self, api_key, index):
        super().__init__(parent=None)
        self.api_key = api_key; self.index = index; self.is_running = True
    def run(self):
        try:
            api = TinyPNGAPI(self.api_key)
            self.validated.emit(api.validate_api_key(), self.index)
        except Exception as e:
            from logging_system import logger
            logger.error(f"API validation error: {e}")
            self.validated.emit(False, self.index)

class SettingsDialog(QDialog):
    settings_applied = pyqtSignal()
    theme_changed = pyqtSignal(str)
    def __init__(self):
        super().__init__()
        self.config = ConfigManager()
        self.startup_manager = StartupManager()
        self.api_validators = []
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("TinyPNG Pro — 设置")
        self.setMinimumSize(560, 620)
        self.resize(600, 640)
        self.setStyleSheet(f"""
            QDialog {{
                background: {current.bg};
                font-family: {current.font};
            }}
        """)
        ml = QVBoxLayout(self)
        ml.setContentsMargins(12, 12, 12, 12)
        ml.setSpacing(10)

        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet(tab_style())
        self.create_api_tab()
        self.create_advanced_tab()
        self.create_about_tab()
        self.tab_widget.addTab(self.api_tab, "API 设置")
        self.tab_widget.addTab(self.advanced_tab, "高级设置")
        self.tab_widget.addTab(self.about_tab, "关于")
        ml.addWidget(self.tab_widget)

        # Button bar
        bl = QHBoxLayout()
        bl.setSpacing(8)
        bl.addStretch()
        self.apply_btn = QPushButton("应用")
        self.apply_btn.setFixedSize(90, 34)
        self.apply_btn.setStyleSheet(accent_outline_btn())
        self.apply_btn.clicked.connect(self.apply_settings)
        self.ok_btn = QPushButton("确定")
        self.ok_btn.setFixedSize(90, 34)
        self.ok_btn.setStyleSheet(primary_btn())
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setFixedSize(90, 34)
        self.cancel_btn.setStyleSheet(ghost_btn())
        self.cancel_btn.clicked.connect(self.reject)
        bl.addWidget(self.apply_btn)
        bl.addWidget(self.ok_btn)
        bl.addWidget(self.cancel_btn)
        ml.addLayout(bl)

    def _wrap(self, content):
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setStyleSheet(scroll_area_style())
        # 暗色主题下强制滚动区视口与内容背景与当前主题背景一致，避免残留浅色/白色底
        content.setStyleSheet(f"background: {current.bg};")
        vp = sa.viewport()
        vp.setAutoFillBackground(True)
        vp.setStyleSheet(f"background: {current.bg};")
        sa.setWidget(content)
        return sa

    def create_api_tab(self):
        self.api_tab = QWidget()
        cw = QWidget()
        cl = QVBoxLayout(cw)
        cl.setSpacing(10)

        g = QGroupBox("API 密钥管理")
        g.setStyleSheet(group_style())
        gl = QVBoxLayout(g)
        gl.setSpacing(8)

        # Description
        desc = QLabel("配置最多 3 个 TinyPNG API 密钥，可选择当前使用的密钥。")
        desc.setStyleSheet(f"""
            font-family: {current.font};
            font-size: {current.size_xs};
            color: {current.dim};
            padding: 0 0 4px 0;
        """)
        gl.addWidget(desc)

        self.api_inputs = []
        self.radio_buttons = []
        self.status_labels = []
        self.validate_buttons = []
        for i in range(3):
            kl = QHBoxLayout()
            kl.setSpacing(8)

            r = QRadioButton(f"密钥 {i+1}")
            r.setStyleSheet(radio_style())
            r.toggled.connect(lambda c, idx=i: self.on_key_selected(idx))
            self.radio_buttons.append(r)
            kl.addWidget(r)

            inp = QLineEdit()
            inp.setStyleSheet(input_style())
            inp.setPlaceholderText(f"输入 API 密钥 {i+1}")
            keys = self.config.get_api_keys()
            inp.setText(keys[i] if i < len(keys) else '')
            inp.setEchoMode(QLineEdit.Password)
            self.api_inputs.append(inp)
            kl.addWidget(inp, 1)

            vb = QPushButton("验证")
            vb.setFixedSize(56, 30)
            vb.setStyleSheet(ghost_btn())
            vb.clicked.connect(lambda c, idx=i: self.validate_api_key(idx))
            self.validate_buttons.append(vb)
            kl.addWidget(vb)

            sl = QLabel("")
            sl.setStyleSheet(f"""
                font-family: {current.font};
                font-size: {current.size_sm};
                color: {current.dim};
                min-width: 24px;
            """)
            self.status_labels.append(sl)
            kl.addWidget(sl)

            gl.addLayout(kl)

        cl.addWidget(g)
        cl.addStretch()

        self.api_tab_layout = QVBoxLayout(self.api_tab)
        self.api_tab_layout.setContentsMargins(0, 0, 0, 0)
        self.api_tab_layout.addWidget(self._wrap(cw))

        active = self.config.get_active_key() - 1
        if 0 <= active < 3:
            self.radio_buttons[active].setChecked(True)

    def create_advanced_tab(self):
        self.advanced_tab = QWidget()
        cw = QWidget()
        cl = QVBoxLayout(cw)
        cl.setSpacing(10)

        # --- Compression ---
        cg = QGroupBox("压缩设置")
        cg.setStyleSheet(group_style())
        cgl = QVBoxLayout(cg)
        cgl.setSpacing(8)

        self.replace_original_check = QCheckBox("压缩后替换原文件")
        self.replace_original_check.setChecked(self.config.get_replace_original())
        self.replace_original_check.setStyleSheet(checkbox_style())
        cgl.addWidget(self.replace_original_check)

        self.only_png_check = QCheckBox("只压缩 PNG（取消勾选后才会监控和压缩其他图片格式）")
        self.only_png_check.setChecked(self.config.get_only_png())
        self.only_png_check.setStyleSheet(checkbox_style())
        cgl.addWidget(self.only_png_check)

        ol = QHBoxLayout()
        ol.setSpacing(8)
        lbl = QLabel("输出路径")
        lbl.setStyleSheet(label_style())
        ol.addWidget(lbl)
        self.output_path_input = QLineEdit()
        self.output_path_input.setStyleSheet(input_style())
        self.output_path_input.setText(self.config.get_output_path())
        self.output_path_input.setPlaceholderText("留空：替换原文件或在与原文件同目录生成 _compressed 副本")
        ol.addWidget(self.output_path_input, 1)
        bb = QPushButton("浏览")
        bb.setFixedSize(56, 30)
        bb.setStyleSheet(ghost_btn())
        bb.clicked.connect(self.browse_output_path)
        ol.addWidget(bb)
        cgl.addLayout(ol)
        cl.addWidget(cg)

        # --- Watch folders ---
        wg = QGroupBox("监控文件夹")
        wg.setStyleSheet(group_style())
        wgl = QVBoxLayout(wg)
        wgl.setSpacing(8)

        self.folder_list = QListWidget()
        self.folder_list.setStyleSheet(list_style())
        self.folder_list.setMinimumHeight(110)
        for f in self.config.get_watch_folders():
            self.folder_list.addItem(f)
        wgl.addWidget(self.folder_list)

        fbl = QHBoxLayout()
        fbl.setSpacing(8)
        afb = QPushButton("添加")
        afb.setFixedSize(56, 30)
        afb.setStyleSheet(ghost_btn())
        afb.clicked.connect(self.add_watch_folder)
        rfb = QPushButton("移除")
        rfb.setFixedSize(56, 30)
        rfb.setStyleSheet(ghost_btn())
        rfb.clicked.connect(self.remove_watch_folder)
        fbl.addWidget(afb)
        fbl.addWidget(rfb)
        fbl.addStretch()
        wgl.addLayout(fbl)
        cl.addWidget(wg)

        # --- System ---
        sg = QGroupBox("系统设置")
        sg.setStyleSheet(group_style())
        sgl = QVBoxLayout(sg)
        sgl.setSpacing(8)

        tl = QHBoxLayout()
        tl.setSpacing(8)
        lbl = QLabel("超时 (秒)")
        lbl.setStyleSheet(label_style())
        tl.addWidget(lbl)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setStyleSheet(spin_style())
        self.timeout_spin.setRange(10, 300)
        self.timeout_spin.setValue(self.config.get_timeout())
        tl.addWidget(self.timeout_spin)
        tl.addStretch()
        sgl.addLayout(tl)

        self.startup_check = QCheckBox("开机自动启动")
        self.startup_check.setChecked(self.startup_manager.is_auto_start_enabled())
        self.startup_check.setStyleSheet(checkbox_style())
        sgl.addWidget(self.startup_check)
        cl.addWidget(sg)

        # --- Watch settings ---
        wsg = QGroupBox("监控设置")
        wsg.setStyleSheet(group_style())
        wsgl = QVBoxLayout(wsg)
        wsgl.setSpacing(8)

        self.logging_check = QCheckBox("启用日志功能")
        self.logging_check.setChecked(self.config.get_logging_enabled())
        self.logging_check.setStyleSheet(checkbox_style())
        wsgl.addWidget(self.logging_check)
        cl.addWidget(wsg)

        # --- Notification ---
        ng = QGroupBox("通知设置")
        ng.setStyleSheet(group_style())
        ngl = QVBoxLayout(ng)
        ngl.setSpacing(8)

        nl = QHBoxLayout()
        nl.setSpacing(8)
        lbl = QLabel("通知持续 (秒)")
        lbl.setStyleSheet(label_style())
        nl.addWidget(lbl)
        self.notify_duration_spin = QSpinBox()
        self.notify_duration_spin.setStyleSheet(spin_style())
        self.notify_duration_spin.setRange(1, 30)
        self.notify_duration_spin.setValue(self.config.get_notification_duration())
        nl.addWidget(self.notify_duration_spin)
        nl.addStretch()
        ngl.addLayout(nl)
        cl.addWidget(ng)

        # --- UI theme ---
        tg = QGroupBox("主题外观")
        tg.setStyleSheet(group_style())
        tgl = QVBoxLayout(tg)
        tgl.setSpacing(8)

        tip = QLabel("选择界面的明暗配色，保存后立即生效。")
        tip.setStyleSheet(f"""
            font-family: {current.font};
            font-size: {current.size_xs};
            color: {current.dim};
            padding: 0 0 2px 0;
        """)
        tgl.addWidget(tip)

        self.theme_group = QButtonGroup(self)
        self.theme_light_radio = QRadioButton("普通 (明亮)")
        self.theme_light_radio.setStyleSheet(radio_style())
        self.theme_dark_radio = QRadioButton("夜间 (暗色)")
        self.theme_dark_radio.setStyleSheet(radio_style())
        self.theme_group.addButton(self.theme_light_radio)
        self.theme_group.addButton(self.theme_dark_radio)
        if current_mode() == 'light':
            self.theme_light_radio.setChecked(True)
        else:
            self.theme_dark_radio.setChecked(True)

        row = QHBoxLayout()
        row.setSpacing(10)
        for r in (self.theme_light_radio, self.theme_dark_radio):
            row.addWidget(r)
        row.addStretch()
        tgl.addLayout(row)

        info = QLabel(f"当前主题：{theme_label()}模式（主页右上角 ☾/☀ 也可快速切换）")
        info.setStyleSheet(f"""
            font-family: {current.font};
            font-size: {current.size_xs};
            color: {current.dim};
        """)
        tgl.addWidget(info)
        cl.addWidget(tg)

        cl.addStretch()
        self.advanced_tab_layout = QVBoxLayout(self.advanced_tab)
        self.advanced_tab_layout.setContentsMargins(0, 0, 0, 0)
        self.advanced_tab_layout.addWidget(self._wrap(cw))

    def create_about_tab(self):
        self.about_tab = QWidget()
        cw = QWidget()
        cl = QVBoxLayout(cw)
        cl.setSpacing(10)

        ag = QGroupBox("TinyPNG Pro")
        ag.setStyleSheet(group_style())
        agl = QVBoxLayout(ag)
        agl.setSpacing(8)

        # App title
        app_title = QLabel("TinyPNG Pro")
        app_title.setStyleSheet(f"""
            font-family: {current.font};
            font-size: 19px;
            font-weight: 700;
            color: {current.fg};
            padding: 4px 0 2px 0;
        """)
        agl.addWidget(app_title)

        vl = QLabel(f"版本  {VERSION}")
        vl.setStyleSheet(f"""
            font-family: {current.font};
            font-size: {current.size_sm};
            font-weight: 600;
            color: {current.fg};
        """)
        agl.addWidget(vl)

        dl = QLabel(f"构建日期  {RELEASE_DATE}")
        dl.setStyleSheet(f"""
            font-family: {current.font};
            font-size: {current.size_xs};
            color: {current.dim};
        """)
        agl.addWidget(dl)

        # Changelog
        at = QTextEdit()
        at.setReadOnly(True)
        at.setStyleSheet(f"""
            QTextEdit {{
                background: {current.video};
                border: 1px solid {current.border};
                border-radius: {current.radius_sm};
                padding: 12px;
                font-family: {current.font};
                font-size: {current.size_xs};
                color: {current.muted};
                line-height: 1.6;
            }}
        """)
        at.setHtml(f"""
<div style="font-family: {current.font}; color: {current.muted}; line-height: 1.7;">
{UPDATE_LOG}
</div>
""")
        agl.addWidget(at)

        # Tip
        tip = QLabel("免费 API 每月 500 张压缩额度")
        tip.setStyleSheet(f"""
            font-family: {current.font};
            font-size: {current.size_xs};
            color: {current.secondary};
            font-weight: 600;
            padding-top: 4px;
        """)
        agl.addWidget(tip)

        cl.addWidget(ag)
        cl.addStretch()

        self.about_tab_layout = QVBoxLayout(self.about_tab)
        self.about_tab_layout.setContentsMargins(0, 0, 0, 0)
        self.about_tab_layout.addWidget(self._wrap(cw))

    def validate_api_key(self, index):
        self.status_labels[index].setText(f"<span style='color:{current.secondary};'>验证中</span>")
        for v in self.api_validators:
            if v.isRunning(): v.is_running = False; v.wait()
        v = APIValidator(self.api_inputs[index].text(), index)
        v.validated.connect(self.on_api_validated)
        self.api_validators.append(v)
        v.start()

    def on_api_validated(self, ok, idx):
        if ok:
            self.status_labels[idx].setText(f"<span style='color:{current.success};font-weight:700;'>✓</span>")
        else:
            self.status_labels[idx].setText(f"<span style='color:{current.error};font-weight:700;'>✗</span>")

    def on_key_selected(self, idx):
        if self.radio_buttons[idx].isChecked():
            self.config.set_active_key(idx + 1)

    def browse_output_path(self):
        p = QFileDialog.getExistingDirectory(self, "选择输出路径")
        if p: self.output_path_input.setText(p)

    def add_watch_folder(self):
        f = QFileDialog.getExistingDirectory(self, "选择监控文件夹")
        if f: self.folder_list.addItem(f)

    def remove_watch_folder(self):
        ci = self.folder_list.currentItem()
        if ci: self.folder_list.takeItem(self.folder_list.row(ci))

    def apply_settings(self):
        # 按分组一次性提交，减少整文件覆写次数（原实现逐项 set 会写盘十余次）
        api_values = {}
        for i, inp in enumerate(self.api_inputs):
            api_values[f'api_key_{i + 1}'] = inp.text()
        active = 1
        for i, r in enumerate(self.radio_buttons):
            if r.isChecked():
                active = i + 1
                break
        api_values['active_key'] = active
        self.config.set_many('API', api_values)

        self.config.set_many('Compression', {
            'replace_original': self.replace_original_check.isChecked(),
            'only_png': self.only_png_check.isChecked(),
            'output_path': self.output_path_input.text(),
        })

        new_theme = 'dark' if self.theme_dark_radio.isChecked() else 'light'
        self.config.set_many('Settings', {
            'timeout': self.timeout_spin.value(),
            'notification_duration': self.notify_duration_spin.value(),
            'logging_enabled': self.logging_check.isChecked(),
            'theme': new_theme,
        })

        folders = [self.folder_list.item(i).text() for i in range(self.folder_list.count())]
        self.config.set_many('AutoCompression', {'watch_folders': '|'.join(folders)})

        # 立即更新logger状态
        logger.set_enabled(self.logging_check.isChecked())
        self.startup_manager.set_auto_start(self.startup_check.isChecked())

        theme_changed = new_theme != current_mode()
        if theme_changed:
            set_theme(new_theme)
            self.theme_changed.emit(new_theme)
        self.settings_applied.emit()

    def showEvent(self, event):
        """每次显示前从配置重新载入。

        主页底部与设置页共用同一配置项（Compression.replace_original）。若上次以
        「取消」关闭而遗留未保存的改动，或主页在设置窗关闭期间切换了开关，重开时必须
        回到配置的真实值，否则两处状态会不一致。
        """
        self.reload_from_config()
        super().showEvent(event)

    def reload_from_config(self):
        keys = self.config.get_api_keys()
        for i, inp in enumerate(self.api_inputs):
            inp.setText(keys[i] if i < len(keys) else '')
        active = self.config.get_active_key() - 1
        for i, r in enumerate(self.radio_buttons):
            was = r.blockSignals(True)
            r.setChecked(i == active)
            r.blockSignals(was)

        self.refresh_replace_original()
        self.only_png_check.setChecked(self.config.get_only_png())
        self.output_path_input.setText(self.config.get_output_path())

        self.folder_list.clear()
        for f in self.config.get_watch_folders():
            self.folder_list.addItem(f)

        self.timeout_spin.setValue(self.config.get_timeout())
        self.notify_duration_spin.setValue(self.config.get_notification_duration())
        self.startup_check.setChecked(self.startup_manager.is_auto_start_enabled())
        self.logging_check.setChecked(self.config.get_logging_enabled())

        if current_mode() == 'light':
            self.theme_light_radio.setChecked(True)
        else:
            self.theme_dark_radio.setChecked(True)

    def refresh_replace_original(self):
        """与主页「替换原文件」开关实时同步（同一配置项，避免两处状态不一致）。"""
        was = self.replace_original_check.blockSignals(True)
        self.replace_original_check.setChecked(self.config.get_replace_original())
        self.replace_original_check.blockSignals(was)

    def accept(self):
        self.apply_settings()
        super().accept()

    def closeEvent(self, e):
        for v in self.api_validators:
            if v.isRunning(): v.is_running = False; v.wait()
        super().closeEvent(e)
