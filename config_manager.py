import os
import time
import configparser
import threading
from utils import get_config_path

class ConfigManager:
    """全局唯一配置管理器（单例）。

    历史问题：`ConfigManager()` 在 7 处被各自 new 出来，每个实例有自己的 parser 与锁，
    锁无法约束跨实例并发，而 `save_config()` 是整文件覆写 —— 后写者会用陈旧内存状态
    覆盖前写者（设置莫名回退/丢项）。改为单例后所有调用点共享同一 parser 与同一把锁。
    """

    _instance = None
    _instance_lock = threading.Lock()
    # 热重载节流：距上次读盘不足该秒数时不做任何文件状态检查
    RELOAD_THROTTLE = 2.0

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        self.config_path = get_config_path()
        self.config = configparser.ConfigParser()
        # UI 线程与压缩工作线程会并发读写同一份配置，用同一把可重入锁串行化
        self._lock = threading.RLock()
        self._last_stat = None      # 上次读盘时的 (mtime, size)
        self._last_read = 0.0
        self._initialized = True
        self.load_config(force=True)

    def _record_stat(self):
        try:
            st = os.stat(self.config_path)
            self._last_stat = (st.st_mtime, st.st_size)
        except OSError:
            self._last_stat = None
        self._last_read = time.time()

    def _needs_reload(self):
        """只有『距上次读盘超过节流窗口』且『文件 mtime/size 确实变了』才需要真正读盘。"""
        now = time.time()
        if now - self._last_read < self.RELOAD_THROTTLE:
            return False
        try:
            st = os.stat(self.config_path)
            sig = (st.st_mtime, st.st_size)
        except OSError:
            return False
        return sig != self._last_stat

    def load_config(self, force=False):
        with self._lock:
            if not force and not self._needs_reload():
                return
            if os.path.exists(self.config_path):
                self.config.read(self.config_path, encoding='utf-8')
                self._record_stat()
            else:
                self.create_default_config()

    def refresh_config(self):
        """重新加载配置（带节流）：无变化时直接复用内存态，避免每个 getter 都读盘。"""
        self.load_config()

    def create_default_config(self):
        self.config['API'] = {
            'api_key_1': '',
            'api_key_2': '',
            'api_key_3': '',
            'active_key': '1',
            'compression_count': '0'
        }
        self.config['Compression'] = {
            'replace_original': 'True',
            'only_png': 'True',
            'output_path': ''
        }
        self.config['AutoCompression'] = {
            'enabled': 'False',
            'watch_folders': ''
        }
        self.config['Settings'] = {
            'timeout': '30',
            'close_to_tray': 'True',
            'always_on_top': 'False',
            'notification_duration': '5',
            'logging_enabled': 'True',
            'theme': 'dark'
        }
        self.config['Startup'] = {
            'auto_start': 'False'
        }
        self.save_config()

    def save_config(self):
        """原子落盘：先写临时文件再 os.replace，避免写到一半崩溃留下半截配置。"""
        with self._lock:
            tmp_path = f"{self.config_path}.tmp"
            with open(tmp_path, 'w', encoding='utf-8') as f:
                self.config.write(f)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(tmp_path, self.config_path)
            self._record_stat()

    def set_many(self, section, values):
        """一次性写入同一分组的多个键，只触发一次整文件覆写（供设置页集中应用）。"""
        with self._lock:
            for key, value in values.items():
                self.config.set(section, key, str(value))
            self.save_config()

    def get_api_keys(self):
        self.refresh_config()
        keys = []
        for i in range(1, 4):
            key = self.config.get('API', f'api_key_{i}', fallback='')
            keys.append(key)
        return keys
    
    def set_api_key(self, index, key):
        if 1 <= index <= 3:
            with self._lock:
                self.config.set('API', f'api_key_{index}', key)
                self.save_config()
    
    def get_active_key(self):
        self.refresh_config()
        return self.config.getint('API', 'active_key', fallback=1)
    
    def set_active_key(self, index):
        if 1 <= index <= 3:
            with self._lock:
                self.config.set('API', 'active_key', str(index))
                self.save_config()
    
    def get_current_api_key(self):
        self.refresh_config()
        keys = self.get_api_keys()
        active_index = self.get_active_key() - 1
        if 0 <= active_index < len(keys):
            return keys[active_index]
        return ''
    
    def get_replace_original(self):
        self.refresh_config()
        return self.config.getboolean('Compression', 'replace_original', fallback=True)
    
    def set_replace_original(self, value):
        with self._lock:
            self.config.set('Compression', 'replace_original', str(value))
            self.save_config()

    def get_only_png(self):
        """是否只压缩 PNG（默认开启）：开启时非 PNG 图片既不监控也不压缩。"""
        self.refresh_config()
        return self.config.getboolean('Compression', 'only_png', fallback=True)

    def set_only_png(self, value):
        with self._lock:
            self.config.set('Compression', 'only_png', str(value))
            self.save_config()
    
    def get_output_path(self):
        self.refresh_config()
        return self.config.get('Compression', 'output_path', fallback='')
    
    def set_output_path(self, path):
        with self._lock:
            self.config.set('Compression', 'output_path', path)
            self.save_config()
    
    def get_auto_compression_enabled(self):
        self.refresh_config()
        return self.config.getboolean('AutoCompression', 'enabled', fallback=False)
    
    def set_auto_compression_enabled(self, value):
        with self._lock:
            self.config.set('AutoCompression', 'enabled', str(value))
            self.save_config()
    
    def get_watch_folders(self):
        self.refresh_config()
        folders_str = self.config.get('AutoCompression', 'watch_folders', fallback='')
        if folders_str:
            return folders_str.split('|')
        return []
    
    def set_watch_folders(self, folders):
        with self._lock:
            folders_str = '|'.join(folders)
            self.config.set('AutoCompression', 'watch_folders', folders_str)
            self.save_config()
    
    def add_watch_folder(self, folder):
        folders = self.get_watch_folders()
        if folder not in folders:
            folders.append(folder)
            self.set_watch_folders(folders)
    
    def remove_watch_folder(self, folder):
        folders = self.get_watch_folders()
        if folder in folders:
            folders.remove(folder)
            self.set_watch_folders(folders)
    
    def get_setting(self, key, default=None):
        self.refresh_config()
        try:
            return self.config.get('Settings', key)
        except Exception:
            return default
    
    def get_setting_int(self, key, default=0):
        self.refresh_config()
        try:
            return self.config.getint('Settings', key)
        except Exception:
            return default
    
    def get_setting_bool(self, key, default=False):
        self.refresh_config()
        try:
            return self.config.getboolean('Settings', key)
        except Exception:
            return default
    
    def set_setting(self, key, value):
        with self._lock:
            self.config.set('Settings', key, str(value))
            self.save_config()
    
    def get_timeout(self):
        self.refresh_config()
        return self.config.getint('Settings', 'timeout', fallback=30)
    
    def set_timeout(self, value):
        if 10 <= value <= 300:
            with self._lock:
                self.config.set('Settings', 'timeout', str(value))
                self.save_config()
    
    def get_close_to_tray(self):
        self.refresh_config()
        return self.config.getboolean('Settings', 'close_to_tray', fallback=True)
    
    def set_close_to_tray(self, value):
        with self._lock:
            self.config.set('Settings', 'close_to_tray', str(value))
            self.save_config()
    
    def get_always_on_top(self):
        self.refresh_config()
        return self.config.getboolean('Settings', 'always_on_top', fallback=False)
    
    def set_always_on_top(self, value):
        with self._lock:
            self.config.set('Settings', 'always_on_top', str(value))
            self.save_config()
    
    def get_notification_duration(self):
        self.refresh_config()
        return self.config.getint('Settings', 'notification_duration', fallback=5)
    
    def set_notification_duration(self, value):
        if 1 <= value <= 30:
            with self._lock:
                self.config.set('Settings', 'notification_duration', str(value))
                self.save_config()
    
    def get_theme(self):
        """获取界面主题模式，默认夜间(dark)。"""
        self.refresh_config()
        v = self.config.get('Settings', 'theme', fallback='dark')
        return v if v in ('dark', 'light') else 'dark'

    def set_theme(self, value):
        if value in ('dark', 'light'):
            with self._lock:
                self.config.set('Settings', 'theme', value)
                self.save_config()

    def get_logging_enabled(self):
        self.refresh_config()
        return self.config.getboolean('Settings', 'logging_enabled', fallback=True)
    
    def set_logging_enabled(self, value):
        with self._lock:
            self.config.set('Settings', 'logging_enabled', str(value))
            self.save_config()
    
    def get_auto_start(self):
        self.refresh_config()
        return self.config.getboolean('Startup', 'auto_start', fallback=False)
    
    def set_auto_start(self, value):
        with self._lock:
            self.config.set('Startup', 'auto_start', str(value))
            self.save_config()
    
    def get_compression_count(self):
        """获取本月压缩次数"""
        self.refresh_config()
        try:
            if 'API' not in self.config:
                return 0
            if 'compression_count' not in self.config['API']:
                return 0
            val = self.config.get('API', 'compression_count', fallback='0')
            # 确保我们得到的是有效的数字
            if val is None:
                return 0
            # 处理可能的列表情况
            if isinstance(val, list):
                val = str(val[0]) if val else '0'
            val_str = str(val).strip()
            if val_str.isdigit():
                return int(val_str)
            return 0
        except Exception:
            return 0
    
    def set_compression_count(self, count):
        """设置本月压缩次数"""
        try:
            # 确保 count 是整数
            if isinstance(count, list):
                count = count[0] if count else 0
            count_val = int(count)
            with self._lock:
                self.config.set('API', 'compression_count', str(count_val))
                self.save_config()
        except Exception as e:
            # 记录错误但不抛出
            try:
                from logging_system import logger
                logger.error(f"Failed to set compression count: {e}")
            except:
                pass