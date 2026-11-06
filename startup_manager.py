import winreg
import os
import sys
from logging_system import logger

class StartupManager:
    RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
    
    @staticmethod
    def get_app_path():
        if getattr(sys, 'frozen', False):
            return sys.executable
        return os.path.abspath(sys.argv[0])
    
    @staticmethod
    def is_auto_start_enabled():
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, StartupManager.RUN_KEY, 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, "TinyPNG Pro")
            winreg.CloseKey(key)
            return value == StartupManager.get_app_path()
        except FileNotFoundError:
            return False
        except Exception as e:
            logger.error(f"Error checking auto-start: {e}")
            return False
    
    @staticmethod
    def set_auto_start(enable):
        app_path = StartupManager.get_app_path()
        
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, StartupManager.RUN_KEY, 0, winreg.KEY_ALL_ACCESS)
            
            if enable:
                winreg.SetValueEx(key, "TinyPNG Pro", 0, winreg.REG_SZ, app_path)
                logger.info("Auto-start enabled")
            else:
                try:
                    winreg.DeleteValue(key, "TinyPNG Pro")
                    logger.info("Auto-start disabled")
                except FileNotFoundError:
                    pass
            
            winreg.CloseKey(key)
            return True
        except Exception as e:
            logger.error(f"Error setting auto-start: {e}")
            return False