import ctypes
import sys
import os

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtGui import QIcon

from ui_main_window import MainWindow
from ui_settings import SettingsDialog
from ui_tray import TrayIcon
from ui_log_viewer import LogViewer
from compression_manager import CompressionManager
from folder_watcher import FolderWatcher
from logging_system import logger
from config_manager import ConfigManager
from ui_theme import current, set_theme, menu_style
from utils import get_resource_path, format_file_size


def build_global_qss():
    """根据当前激活主题生成应用级全局样式（弹窗/文件对话框/气泡提示/菜单等）。"""
    return f"""
    /* 顶层对话框与弹窗背景随主题联动 */
    QMessageBox {{
        background: {current.bg};
    }}
    QMessageBox QLabel {{
        color: {current.fg};
        font-family: {current.font};
        font-size: 13px;
    }}
    QMessageBox QPushButton {{
        font-family: {current.font};
        background: {current.elev};
        color: {current.muted};
        border: 1px solid {current.border};
        border-radius: {current.pill};
        font-size: 12px;
        font-weight: 600;
        padding: 7px 20px;
        min-width: 70px;
    }}
    QMessageBox QPushButton:hover {{
        background: {current.card};
        color: {current.fg};
        border-color: {current.primary2};
    }}
    QMessageBox QPushButton:pressed {{
        background: {current.video};
    }}
    QFileDialog {{
        background: {current.bg};
    }}
    QDialog {{
        background: {current.bg};
        font-family: {current.font};
    }}
    QToolTip {{
        background: {current.elev};
        color: {current.fg};
        border: 1px solid {current.border};
        border-radius: {current.radius_sm};
        padding: 4px 8px;
        font-family: {current.font};
        font-size: 11px;
    }}
    QScrollBar {{
        background: {current.video};
        width: 6px;
        height: 6px;
        border-radius: 3px;
    }}
    QScrollBar::handle {{
        background: {current.border_strong};
        border-radius: 3px;
        min-height: 30px;
    }}
    QScrollBar::handle:hover {{ background: {current.dim}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0px; height: 0px; }}
    {menu_style()}
"""


class Application(QApplication):
    def __init__(self, argv):
        super().__init__(argv)
        self.config = ConfigManager()
        # 启动即按配置加载主题，再应用全局样式
        set_theme(self.config.get_theme())
        self.setStyleSheet(build_global_qss())
        self.setQuitOnLastWindowClosed(False)

        self.compression_manager = CompressionManager()
        self.folder_watcher = FolderWatcher(self.compression_manager)

        self.main_window = None
        self.tray_icon = None
        self.settings_dialog = None
        self.log_viewer = None

        self.init_components()
        self.setup_connections()

        self.check_api_key_on_startup()

        logger.info("Application started")

    def init_components(self):
        self.tray_icon = TrayIcon()
        self.compression_manager.start()
        # 压缩结果统一经信号回到主线程：手动走批量汇总通知，自动逐条通知
        self.compression_manager.compressionFinished.connect(self.on_compression_finished)
        self.compression_manager.batchFinished.connect(self.on_batch_finished)

        if self.config.get_auto_compression_enabled():
            self.folder_watcher.start()

    def setup_connections(self):
        self.tray_icon.show_main_window.connect(self.show_main_window)
        self.tray_icon.show_settings.connect(self.show_settings)
        self.tray_icon.show_logs.connect(self.show_logs)
        self.tray_icon.exit_app.connect(self.exit_application)

    def on_theme_changed(self, mode):
        """主题切换后的统一刷新：同步应用级样式、重建主页与设置窗。"""
        if mode in ('light', 'dark'):
            set_theme(mode)
        self.setStyleSheet(build_global_qss())
        if self.main_window:
            self.main_window.rebuild()
        # 设置窗采用「关闭并重建」而非原地 rebuild，避免切换主题时残留旧主题组件导致黑屏
        if self.settings_dialog:
            self.settings_dialog.close()
            self.settings_dialog = None
        # 日志查看器按主题即时重建（下次打开时重新取色）
        if self.log_viewer:
            self.log_viewer.close()
            self.log_viewer = None

    def check_api_key_on_startup(self):
        api_key = self.config.get_current_api_key()
        self.show_main_window()  # 启动后显示主页
        if not api_key or api_key.strip() == "":
            reply = QMessageBox.question(
                self.main_window, "API密钥未配置",
                "未检测到API密钥，请先配置TinyPNG API密钥。是否现在打开设置界面？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply == QMessageBox.Yes:
                self.show_settings()

    def show_main_window(self):
        if not self.main_window:
            self.main_window = MainWindow(self.compression_manager)
            self.main_window.closed.connect(self.on_main_window_closed)
            self.main_window.show_settings.connect(self.show_settings)
            self.main_window.auto_compress_toggled.connect(self.on_auto_compress_toggled)
            self.main_window.replace_original_toggled.connect(self.on_replace_original_toggled)
            self.main_window.always_on_top_toggled.connect(self.on_always_on_top_toggled)
            self.main_window.exit_application.connect(self.exit_application)
            self.main_window.theme_changed.connect(self.on_theme_changed)
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def on_main_window_closed(self):
        self.main_window = None

    def on_auto_compress_toggled(self, enabled):
        # 启动/停止均由监控控制器线程异步完成，界面线程不会被 join 阻塞
        if enabled:
            self.folder_watcher.start()
        else:
            self.folder_watcher.stop()

    def on_replace_original_toggled(self, enabled):
        # 与设置页「压缩后替换原文件」共用同一配置项：若设置窗正打开，实时同步其勾选状态
        logger.info(f"Replace original file toggled to: {enabled}")
        if self.settings_dialog:
            self.settings_dialog.refresh_replace_original()

    def on_always_on_top_toggled(self, enabled):
        logger.info(f"Always on top toggled to: {enabled}")

    def show_settings(self):
        if not self.settings_dialog:
            self.settings_dialog = SettingsDialog()
            self.settings_dialog.settings_applied.connect(self.on_settings_applied)
            self.settings_dialog.theme_changed.connect(self.on_theme_changed)
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def on_settings_applied(self):
        self.update_folder_watcher()
        if self.main_window:
            self.main_window.update_settings()

    def update_folder_watcher(self):
        if self.config.get_auto_compression_enabled():
            self.folder_watcher.start()
        else:
            self.folder_watcher.stop()

    def show_logs(self):
        if not self.log_viewer:
            self.log_viewer = LogViewer()
        self.log_viewer.show()
        self.log_viewer.raise_()
        self.log_viewer.activateWindow()

    def exit_application(self):
        logger.info("Application exiting...")

        self.compression_manager.stop()
        self.folder_watcher.shutdown()

        if self.main_window:
            self.main_window.close()
            self.main_window = None

        if self.tray_icon:
            self.tray_icon.hide()
        self.quit()

    def on_compression_finished(self, filename, success, message, is_auto):
        """自动压缩逐条通知；手动压缩不在此逐条弹窗（由批量汇总统一通知，避免噪声）。"""
        if not is_auto:
            return
        title = "压缩完成" if success else "压缩失败"
        duration = self.config.get_notification_duration() * 1000
        self.tray_icon.show_notification(title, f"{filename}: {message}", duration)

    def on_batch_finished(self, batch_id, summary, is_auto):
        """手动批量压缩统一弹一条汇总通知。"""
        if is_auto:
            return
        total = summary.get('total', 0)
        ok = summary.get('ok', 0)
        failed = summary.get('failed', 0)
        duration = self.config.get_notification_duration() * 1000

        if ok > 0:
            ratio = summary.get('ratio', 0.0) * 100
            message = (f"成功 {ok}/{total} · 节省 {ratio:.1f}%"
                       f" · {format_file_size(summary.get('original_size', 0))} →"
                       f" {format_file_size(summary.get('compressed_size', 0))}")
            if failed:
                message += f" · 失败 {failed}"
            self.tray_icon.show_notification("压缩完成", message, duration)
        else:
            message = "；".join(summary.get('errors', [])[:2]) or "请检查 API 密钥与网络"
            self.tray_icon.show_notification("压缩失败", message, duration)


# ---------------- 单实例保护 ----------------
# 同一时间只允许一个进程运行：多个实例会各自监控同一目录、重复压缩同一个文件，
# 并各弹一条托盘通知（表现为「压缩完成后弹出多次提示」）。
_MUTEX_NAME = "TinyPNGPro_SingleInstance_v1"   # 本地命名空间：同会话内互斥
_ERROR_ALREADY_EXISTS = 183
_instance_mutex = None                         # 句柄随进程存活，退出时由系统释放


def _acquire_single_instance():
    """尝试获取命名互斥量。

    返回 True 表示本进程是唯一实例；False 表示已有实例在运行。
    非 Windows 或获取失败时一律放行，避免误伤正常启动。
    """
    global _instance_mutex
    if os.name != 'nt':
        return True
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel32.GetLastError.restype = ctypes.c_uint32
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

        handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
        if not handle:
            logger.warning("CreateMutex failed, skip single-instance check")
            return True
        if kernel32.GetLastError() == _ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False
        _instance_mutex = handle
        return True
    except Exception as e:
        logger.warning(f"Single-instance check failed: {e}")
        return True


def _activate_existing_window():
    """把已有实例的主窗口唤到前台；找不到窗口时返回 False。"""
    try:
        user32 = ctypes.windll.user32
        user32.FindWindowW.restype = ctypes.c_void_p
        user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]

        hwnd = user32.FindWindowW(None, "TinyPNG Pro")
        if not hwnd:
            return False
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception as e:
        logger.warning(f"Failed to activate existing window: {e}")
        return False


def main():
    if not _acquire_single_instance():
        logger.info("Another instance is already running; exiting")
        if not _activate_existing_window():
            ctypes.windll.user32.MessageBoxW(
                None,
                "TinyPNG Pro 已在运行中，请在系统托盘中查看。",
                "TinyPNG Pro",
                0x40,   # MB_ICONINFORMATION
            )
        return

    app = Application(sys.argv)

    myappid = 'tinypng.pro.app.1.0'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    icon_path = get_resource_path('icon.png')
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
