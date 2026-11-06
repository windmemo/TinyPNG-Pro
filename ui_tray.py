import os
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import pyqtSignal
from config_manager import ConfigManager
from logging_system import logger
from ui_theme import menu_style
from utils import get_resource_path

class TrayIcon(QSystemTrayIcon):
    show_main_window = pyqtSignal()
    show_settings = pyqtSignal()
    show_logs = pyqtSignal()
    exit_app = pyqtSignal()
    # 跨线程通知信号:压缩工作线程中不可直接操作 GUI,须经信号投递到主线程
    _notify = pyqtSignal(str, str, int, int)  # (title, message, icon, duration_ms)
    
    def __init__(self):
        super().__init__()
        self.config = ConfigManager()
        self._notify.connect(self._show_notification)
        self.init_tray()

    def _show_notification(self, title, message, icon, duration):
        """在主线程中真正弹出托盘通知"""
        try:
            self.showMessage(title, message, QSystemTrayIcon.MessageIcon(icon), duration)
        except Exception as e:
            logger.warning(f"Failed to show tray notification: {e}")
    
    def init_tray(self):
        icon_path = get_resource_path('icon.png')
        if os.path.exists(icon_path):
            self.setIcon(QIcon(icon_path))
        else:
            self.setIcon(QIcon.fromTheme('image'))
        
        self.setToolTip("TinyPNG Pro")
        self.setContextMenu(self.create_menu())
        self.activated.connect(self.on_tray_activated)
        
        self.show()
        logger.info("System tray icon initialized")
    
    def create_menu(self):
        menu = QMenu()
        menu.setStyleSheet(menu_style())
        
        self.show_action = QAction("打开主窗口", self)
        self.settings_action = QAction("设置", self)
        self.logs_action = QAction("查看日志", self)
        self.exit_action = QAction("退出", self)
        
        menu.addAction(self.show_action)
        menu.addAction(self.settings_action)
        menu.addAction(self.logs_action)
        menu.addSeparator()
        menu.addAction(self.exit_action)
        
        self.show_action.triggered.connect(self.show_main_window.emit)
        self.settings_action.triggered.connect(self.show_settings.emit)
        self.logs_action.triggered.connect(self.show_logs.emit)
        self.exit_action.triggered.connect(self.exit_app.emit)
        
        return menu
    
    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick or reason == QSystemTrayIcon.Trigger:
            self.show_main_window.emit()
    
    def show_notification(self, title, message, duration=5000):
        # 通过信号投递,保证在主线程调用 showMessage(线程安全)
        self._notify.emit(title, message, int(QSystemTrayIcon.Information), duration)