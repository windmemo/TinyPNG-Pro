import os
import sys

def get_app_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_resource_path(relative_path):
    """获取资源文件路径，支持PyInstaller打包后的环境"""
    if getattr(sys, 'frozen', False):
        # 如果是打包后的环境，优先检查exe同目录
        base_path = os.path.dirname(sys.executable)
        full_path = os.path.join(base_path, relative_path)
        if os.path.exists(full_path):
            return full_path
        # 如果不存在，检查PyInstaller临时提取目录
        if hasattr(sys, '_MEIPASS'):
            return os.path.join(sys._MEIPASS, relative_path)
        return full_path
    else:
        # 开发环境直接返回当前目录
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

def get_config_path():
    return os.path.join(get_app_path(), 'config.ini')

def get_log_path():
    return os.path.join(get_app_path(), 'logs')

def get_state_path():
    """自动压缩去重账本文件路径（与 config.ini 同目录，便于随程序一起迁移）。"""
    return os.path.join(get_app_path(), 'processed_state.json')

def normkey(file_path):
    """把路径归一化成去重/抑制表的统一键：
    统一为绝对路径并消除大小写与分隔符差异（Windows 上 C:\\A\\b.PNG 与 c:/a/B.png 视为同一文件）。"""
    if not file_path:
        return ''
    try:
        return os.path.normcase(os.path.abspath(file_path))
    except Exception:
        return str(file_path)

def format_file_size(bytes_size):
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.2f} KB"
    else:
        return f"{bytes_size / (1024 * 1024):.2f} MB"

def format_compression_ratio(original, compressed):
    if original == 0:
        return "0%"
    ratio = (1 - compressed / original) * 100
    return f"{ratio:.2f}%"

def is_png_file(file_path):
    return file_path.lower().endswith('.png')

def is_supported_file(file_path):
    supported_extensions = ('.png', '.jpg', '.jpeg', '.webp')
    return file_path.lower().endswith(supported_extensions)

# 自动压缩、不替换原文件时，生成的压缩副本统一加该后缀（原文件保持不变）
COMPRESSED_SUFFIX = "_compressed"

def is_compressed_output(file_path):
    """判断是否为本软件自动压缩生成的 _compressed 结果文件，
    供监控器忽略，避免对压缩副本再次压缩形成无限嵌套。"""
    if not file_path:
        return False
    name, ext = os.path.splitext(os.path.basename(file_path))
    return (ext.lower() in ('.png', '.jpg', '.jpeg', '.webp')
            and name.endswith(COMPRESSED_SUFFIX))

def is_allowed_file(file_path, only_png):
    """按『只压缩PNG』开关过滤可处理的文件。
    only_png=True 时仅 PNG 可处理；否则放行全部受支持格式。"""
    return is_png_file(file_path) if only_png else is_supported_file(file_path)