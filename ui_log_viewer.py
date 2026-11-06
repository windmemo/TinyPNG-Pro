import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QComboBox, QMessageBox, QLabel, QFrame
)
from PyQt5.QtGui import QTextCursor
from datetime import datetime
from utils import get_log_path
from ui_theme import current

# ============================================================
# 日志查看器外观统一由 ui_theme 管理(支持 明亮/夜间 主题切换)
# ============================================================


def combo_style():
    return f"""
    QComboBox {{
        font-family: {current.font};
        background: {current.video};
        border: 1px solid {current.border};
        border-radius: {current.radius_sm};
        padding: 6px 10px;
        font-size: {current.size_sm};
        color: {current.fg};
        min-width: 120px;
    }}
    QComboBox:focus {{ border-color: {current.primary2}; }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox::down-arrow {{
        image: none;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 5px solid {current.muted};
        margin-right: 8px;
    }}
    QComboBox QAbstractItemView {{
        background: {current.elev};
        border: 1px solid {current.border};
        border-radius: {current.radius_sm};
        color: {current.fg};
        selection-background-color: {current.primary};
        padding: 4px;
        outline: none;
    }}
"""


def btn_ghost():
    return f"""
    QPushButton {{
        font-family: {current.font};
        background: transparent;
        color: {current.muted};
        border: 1px solid {current.border};
        border-radius: {current.pill};
        font-size: {current.size_sm};
        font-weight: 600;
        padding: 7px 16px;
        min-width: 60px;
    }}
    QPushButton:hover {{
        background: {current.elev};
        color: {current.fg};
        border-color: {current.primary2};
    }}
    QPushButton:pressed {{ background: {current.card}; }}
"""


def btn_danger():
    return f"""
    QPushButton {{
        font-family: {current.font};
        background: transparent;
        color: {current.error};
        border: 1px solid {current.error};
        border-radius: {current.pill};
        font-size: {current.size_sm};
        font-weight: 600;
        padding: 7px 16px;
        min-width: 60px;
    }}
    QPushButton:hover {{
        background: {current.error_bg};
        color: {current.error};
    }}
    QPushButton:pressed {{
        background: {current.error_bg};
    }}
"""


def log_text_style():
    return f"""
    QTextEdit {{
        font-family: {current.mono_font};
        background: {current.video};
        border: 1px solid {current.border};
        border-radius: {current.radius_md};
        padding: 12px;
        font-size: {current.size_xs};
        color: {current.muted};
        selection-background-color: {current.primary};
        selection-color: #FFFFFF;
    }}
"""


class LogViewer(QDialog):
    def __init__(self):
        super().__init__()
        self.log_dir = get_log_path()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("TinyPNG Pro — 日志查看器")
        self.setFixedSize(820, 620)
        self.setStyleSheet(f"""
            QDialog {{
                background: {current.bg};
                font-family: {current.font};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header toolbar
        toolbar = QFrame()
        toolbar.setStyleSheet(f"""
            QFrame {{
                background: {current.card};
                border: 1px solid {current.border};
                border-radius: {current.radius_md};
            }}
        """)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(12, 8, 12, 8)
        toolbar_layout.setSpacing(10)

        # Title
        title = QLabel("日志查看器")
        title.setStyleSheet(f"""
            font-family: {current.font};
            font-size: {current.size_md};
            font-weight: 700;
            color: {current.fg};
        """)
        toolbar_layout.addWidget(title)

        toolbar_layout.addStretch()

        # Date selector
        self.date_combo = QComboBox()
        self.date_combo.setStyleSheet(combo_style())
        self.load_log_dates()
        toolbar_layout.addWidget(self.date_combo)

        # Refresh button
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setFixedSize(60, 30)
        self.refresh_btn.setStyleSheet(btn_ghost())
        toolbar_layout.addWidget(self.refresh_btn)

        layout.addWidget(toolbar)

        # Log text area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet(log_text_style())
        layout.addWidget(self.log_text, 1)

        # Bottom button bar
        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        bottom.addStretch()

        # Log count info
        self.log_info = QLabel("")
        self.log_info.setStyleSheet(f"""
            font-family: {current.font};
            font-size: {current.size_xs};
            color: {current.dim};
        """)
        bottom.addWidget(self.log_info)
        bottom.addStretch()

        self.clear_btn = QPushButton("清空日志")
        self.clear_btn.setFixedSize(80, 32)
        self.clear_btn.setStyleSheet(btn_danger())
        bottom.addWidget(self.clear_btn)

        self.close_btn = QPushButton("关闭")
        self.close_btn.setFixedSize(80, 32)
        self.close_btn.setStyleSheet(btn_ghost())
        bottom.addWidget(self.close_btn)

        layout.addLayout(bottom)

        self.date_combo.currentTextChanged.connect(self.load_log_file)
        self.refresh_btn.clicked.connect(self.load_log_dates)
        self.clear_btn.clicked.connect(self.clear_logs)
        self.close_btn.clicked.connect(self.reject)

        if self.date_combo.count() > 0:
            self.load_log_file(self.date_combo.currentText())
        else:
            self.log_text.setPlainText("暂无日志记录")

    def load_log_dates(self):
        self.date_combo.clear()

        if not os.path.exists(self.log_dir):
            self.log_text.setPlainText("日志目录不存在")
            return

        dates = []
        for filename in os.listdir(self.log_dir):
            if filename.endswith('.log'):
                try:
                    date_str = filename[:-4]
                    datetime.strptime(date_str, '%Y-%m-%d')
                    dates.append(date_str)
                except ValueError:
                    pass

        dates.sort(reverse=True)
        for date in dates:
            self.date_combo.addItem(date)

    def load_log_file(self, date_str):
        if not date_str:
            return

        log_file = os.path.join(self.log_dir, f'{date_str}.log')
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                content = f.read()
            self.log_text.setPlainText(content)
            # Count lines
            lines = content.strip().split('\n') if content.strip() else []
            self.log_info.setText(f"{date_str}  ·  {len(lines)} 条记录")
            # Scroll to bottom
            cursor = self.log_text.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.log_text.setTextCursor(cursor)
        else:
            self.log_text.setPlainText("日志文件不存在")
            self.log_info.setText("")

    def clear_logs(self):
        reply = QMessageBox.question(
            self, "确认清空", "确定要清空所有日志吗？此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if os.path.exists(self.log_dir):
                for filename in os.listdir(self.log_dir):
                    if filename.endswith('.log'):
                        try:
                            os.remove(os.path.join(self.log_dir, filename))
                        except Exception as e:
                            QMessageBox.warning(self, "警告", f"删除日志失败: {e}")

            self.date_combo.clear()
            self.log_text.setPlainText("日志已清空")
            self.log_info.setText("")