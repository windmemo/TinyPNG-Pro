import os
import time
import logging
import threading
from datetime import datetime
from utils import get_log_path
from config_manager import ConfigManager

class Logger:
    _instance = None
    _instance_lock = threading.Lock()
    _init_lock = threading.Lock()
    # 日志开关的读取节流：监控侧每个文件事件都会打多条日志，
    # 若每条都去读配置会放大磁盘 I/O，因此最多每 2 秒回读一次开关状态。
    FLAG_TTL = 2.0

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        with Logger._init_lock:
            if getattr(self, '_initialized', False):
                return
            self._setup()

    def _setup(self):
        self._config = ConfigManager()
        self._log_enabled = self._config.get_logging_enabled()
        self._flag_ts = time.time()
        self._log_dir = get_log_path()
        os.makedirs(self._log_dir, exist_ok=True)

        # 初始化 logger
        self._logger = logging.getLogger('TinyPNG_Pro')
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False

        # 清除旧的 handlers
        for handler in self._logger.handlers[:]:
            try:
                handler.close()
            except Exception:
                pass
        self._logger.handlers.clear()

        # 设置 formatter
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        # 添加文件 handler
        current_date = datetime.now().strftime('%Y-%m-%d')
        log_file = os.path.join(self._log_dir, f'{current_date}.log')

        try:
            self._file_handler = logging.FileHandler(log_file, encoding='utf-8', delay=True)
            self._file_handler.setLevel(logging.DEBUG)
            self._file_handler.setFormatter(formatter)
            self._logger.addHandler(self._file_handler)
        except Exception as e:
            print(f"Failed to create file handler: {e}")

        # 添加控制台 handler
        self._console_handler = logging.StreamHandler()
        self._console_handler.setLevel(logging.INFO)
        self._console_handler.setFormatter(formatter)
        self._logger.addHandler(self._console_handler)

        self._initialized = True
    
    def set_enabled(self, enabled):
        self._log_enabled = enabled
        self._flag_ts = time.time()
        self._config.set_logging_enabled(enabled)
    
    def close_handlers(self):
        # 关闭所有 handlers
        if hasattr(self, '_logger'):
            for handler in self._logger.handlers[:]:
                try:
                    handler.close()
                    self._logger.removeHandler(handler)
                except Exception:
                    pass
    
    def reopen_handlers(self):
        # 重新初始化 logger 以重新打开 handlers
        with Logger._init_lock:
            if hasattr(self, '_initialized'):
                del self._initialized
            self._setup()
    
    def _log(self, level, message):
        if not getattr(self, '_initialized', False):
            self.__init__()

        # 开关状态回读带节流，避免每条日志都读配置
        now = time.time()
        if now - self._flag_ts >= self.FLAG_TTL:
            self._flag_ts = now
            try:
                self._log_enabled = self._config.get_logging_enabled()
            except Exception:
                pass

        if self._log_enabled:
            try:
                if level == 'debug':
                    self._logger.debug(message)
                elif level == 'info':
                    self._logger.info(message)
                elif level == 'warning':
                    self._logger.warning(message)
                elif level == 'error':
                    self._logger.error(message)
                elif level == 'critical':
                    self._logger.critical(message)
            except Exception as e:
                print(f"Logging error: {e}")
    
    def debug(self, message):
        self._log('debug', message)
    
    def info(self, message):
        self._log('info', message)
    
    def warning(self, message):
        self._log('warning', message)
    
    def error(self, message):
        self._log('error', message)
    
    def critical(self, message):
        self._log('critical', message)
    
    def clean_old_logs(self, days_to_keep=30):
        try:
            for filename in os.listdir(self._log_dir):
                if filename.endswith('.log'):
                    try:
                        file_date = datetime.strptime(filename, '%Y-%m-%d.log')
                        days_old = (datetime.now() - file_date).days
                        if days_old > days_to_keep:
                            os.remove(os.path.join(self._log_dir, filename))
                            self.info(f"Removed old log file: {filename}")
                    except ValueError:
                        pass
        except Exception as e:
            self.error(f"Error cleaning old logs: {e}")

logger = Logger()