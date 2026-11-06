import os
import queue
import threading
import time

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from config_manager import ConfigManager
from logging_system import logger
from utils import is_compressed_output, normkey


class FileHandler(FileSystemEventHandler):
    """把文件系统事件转换成「候选压缩文件」，并做最基础的本地去重。

    - COOLDOWN：同一路径在派发压缩后的一段时间内忽略后续事件，既防止「替换原文件」
      写回触发死循环，也允许该路径稍后被写入新内容时再次压缩。
    - 抑制表 / 处理中集合统一以 normkey(path) 为键，消除大小写与分隔符差异。
      （真正的「已处理/正在处理」判定交给 CompressionManager，本类只做兜底节流。）
    """

    COOLDOWN = 30.0
    # 等待文件写入完成的最长时间（秒）：超时后只要文件存在且有内容仍继续处理
    READY_TIMEOUT = 3.0

    def __init__(self, callback, suppressed, lock, is_allowed):
        self.callback = callback
        self.processing_files = set()
        self.suppressed = suppressed  # {normkey: 抑制截止时间},与 FolderWatcher 共享
        self.lock = lock
        self.is_allowed = is_allowed  # 按『只压缩PNG』等开关动态判定文件是否可处理

    def _file_unlocked(self, file_path):
        """Windows 下尝试『只写 + 独占打开』文件：
        成功说明写入方已释放句柄（文件写完）；失败说明仍被其它进程占用。"""
        try:
            fd = os.open(file_path, os.O_RDWR | os.O_EXCL)
        except OSError:
            return False
        else:
            os.close(fd)
            return True

    def _wait_until_ready(self, file_path):
        """等待文件写入完成后返回其大小；文件不存在或仍为空时返回 0。

        - 首选『能否独占打开』(Windows)：写入方一释放句柄即可判定写完，重命名事件几乎立即通过；
        - 兜底『大小连续两次稳定』：兼容非 Windows 或文件被以共享方式持有时。
        """
        deadline = time.time() + self.READY_TIMEOUT
        last_size = -1
        stable_checks = 0
        while time.time() < deadline:
            try:
                if not os.path.exists(file_path):
                    return 0
                size = os.path.getsize(file_path)
            except OSError:
                time.sleep(0.1)
                continue
            if size == 0:
                time.sleep(0.1)
                continue
            if os.name == 'nt' and self._file_unlocked(file_path):
                return size
            if size == last_size:
                stable_checks += 1
                if stable_checks >= 2:
                    return size
            else:
                stable_checks = 0
                last_size = size
            time.sleep(0.1)
        # 超时兜底：文件存在且有内容就继续处理
        try:
            return os.path.getsize(file_path) if os.path.exists(file_path) else 0
        except OSError:
            return 0

    def _process_file(self, file_path):
        key = normkey(file_path)
        now = time.time()
        with self.lock:
            if key in self.processing_files:
                logger.debug(f"Already processing: {file_path}")
                return
            if self.suppressed.get(key, 0) > now:
                logger.debug(f"Within cooldown, skip: {file_path}")
                return
            self.processing_files.add(key)

        try:
            file_size = self._wait_until_ready(file_path)
            if file_size <= 0 or not os.path.exists(file_path):
                logger.warning(f"File not ready or no longer exists: {file_path}")
                return

            logger.info(f"Detected new file, ready to compress: {file_path} ({file_size} bytes)")
            # 派发前设置冷却，避免压缩写回 / 后续事件再次触发
            with self.lock:
                self.suppressed[key] = time.time() + self.COOLDOWN
            self.callback(file_path)
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
        finally:
            with self.lock:
                self.processing_files.discard(key)

    def _dispatch(self, file_path, tag):
        """三类事件（created / modified / moved）共用的一条派发通道。"""
        if not self.is_allowed(file_path):
            logger.debug(f"Not an allowed file: {file_path}")
            return
        # 忽略本软件自动压缩生成的 _compressed 结果文件，避免对该副本再次压缩形成嵌套
        if is_compressed_output(file_path):
            logger.debug(f"Skipping compressed output: {file_path}")
            return
        logger.debug(f"{tag}: {file_path}")
        threading.Thread(target=self._process_file, args=(file_path,), daemon=True).start()

    def on_created(self, event):
        if event.is_directory:
            return
        logger.debug(f"File created event: {event.src_path}")
        self._dispatch(event.src_path, "created")

    def on_modified(self, event):
        if event.is_directory:
            return
        logger.debug(f"File modified event: {event.src_path}")
        self._dispatch(event.src_path, "modified")

    def on_moved(self, event):
        """捕获「临时文件重命名成最终文件」的场景（如 PixPin 先写 xx.png.<随机> 再 rename）。

        只处理重命名后的目标路径：直接以受支持后缀落盘的文件才会被 on_created 漏掉。
        """
        if event.is_directory:
            return
        dest_path = getattr(event, 'dest_path', None)
        if not dest_path or not isinstance(dest_path, str):
            return
        logger.debug(f"File moved event -> {dest_path}")
        self._dispatch(dest_path, "moved")


class FolderWatcher:
    """目录监控器：GUI 侧只投递命令，Observer 的创建/停止/刷新全部由控制线程独占执行。

    这样启动、关闭、切换监控目录时不会在界面线程里持锁 join 观察者，彻底避免界面卡顿。
    """

    RECOVER_INTERVAL = 30.0     # 观察者存活检查周期（秒）
    CLEANUP_INTERVAL = 600.0    # 抑制表清理周期（秒）
    SUPPRESS_TTL = 3600.0       # 抑制记录最长保留时长（秒）

    def __init__(self, compression_manager):
        self.config = ConfigManager()
        self.compression_manager = compression_manager
        self.observers = []
        self.watch_folders = []
        self.lock = threading.Lock()             # 保护 suppressed / observers / watch_folders
        self.suppressed = {}                     # {normkey: 抑制截止时间}
        self.watch_start_time = time.time()      # 监控启动水位：早于此刻写入的文件一律不压缩
        self._cmd_queue = queue.Queue()
        self._controller_thread = None
        self._running = threading.Event()
        self._last_cleanup_time = time.time()

    # ---------------- GUI 侧：只投递命令，立即返回 ----------------
    def start(self):
        self._ensure_controller()
        self._cmd_queue.put('start')

    def stop(self, wait=False):
        self._cmd_queue.put('stop')
        if wait:
            self._join_controller()

    def shutdown(self):
        """退出时使用：停止监控并等待控制线程结束，保证观察者被置停。"""
        self._cmd_queue.put('shutdown')
        self._join_controller()

    def refresh_watchers(self):
        if self._running.is_set():
            self._cmd_queue.put('refresh')

    def get_watched_folders(self):
        with self.lock:
            return self.watch_folders.copy()

    # ---------------- 控制线程 ----------------
    def _ensure_controller(self):
        if self._controller_thread is None or not self._controller_thread.is_alive():
            self._controller_thread = threading.Thread(
                target=self._controller_loop, name="FolderWatcherController", daemon=True
            )
            self._controller_thread.start()

    def _join_controller(self):
        thread = self._controller_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)

    def _controller_loop(self):
        last_recover = time.time()
        while True:
            try:
                cmd = self._cmd_queue.get(timeout=1.0)
            except queue.Empty:
                cmd = None
            except Exception:
                cmd = None

            try:
                if cmd == 'start':
                    self._do_start()
                elif cmd == 'stop':
                    self._do_stop()
                elif cmd == 'refresh':
                    if self._running.is_set():
                        self._update_watchers()
                elif cmd == 'shutdown':
                    self._do_stop()
                    logger.debug("Folder watcher controller exiting")
                    break
            except Exception as e:
                logger.error(f"Error handling watcher command {cmd!r}: {e}")

            now = time.time()
            if self._running.is_set() and now - last_recover >= self.RECOVER_INTERVAL:
                last_recover = now
                try:
                    self._check_and_recover_observers()
                except Exception as e:
                    logger.error(f"Error in watcher recovery: {e}")
                if now - self._last_cleanup_time >= self.CLEANUP_INTERVAL:
                    self._cleanup_suppressed()
                    self._last_cleanup_time = now

    def _do_start(self):
        if self._running.is_set():
            logger.debug("Folder watcher already running")
            return
        self._running.set()
        self._update_watchers()
        logger.info("Folder watcher started")

    def _do_stop(self):
        if not self._running.is_set() and not self.observers:
            return
        self._running.clear()
        logger.info("Stopping folder watcher...")
        with self.lock:
            observers, self.observers = self.observers, []
            self.watch_folders = []
        for observer in observers:
            try:
                observer.stop()
            except Exception as e:
                logger.warning(f"Error stopping observer: {e}")
        for observer in observers:
            try:
                observer.join(timeout=5)
            except Exception as e:
                logger.warning(f"Error joining observer: {e}")
        logger.info("Folder watcher stopped")

    def _update_watchers(self):
        """按最新配置重建监控。水位在本次重建的起点取一次（不再每个目录各取一次，
        避免多目录时互相顶掉水位导致旧文件被误判为新文件）。"""
        new_folders = self.config.get_watch_folders()
        logger.debug(f"Updating watchers with folders: {new_folders}")
        self.watch_start_time = time.time()

        with self.lock:
            old_observers, self.observers = self.observers, []
            self.watch_folders = []
        for observer in old_observers:
            try:
                observer.stop()
                observer.join(timeout=2)
            except Exception as e:
                logger.warning(f"Error recycling observer: {e}")

        for folder in new_folders:
            if os.path.isdir(folder):
                self._add_watcher(folder)

    def _add_watcher(self, folder):
        event_handler = FileHandler(
            self._on_file_created, self.suppressed, self.lock,
            self.compression_manager.is_allowed
        )
        observer = Observer()
        observer.schedule(event_handler, folder, recursive=False)
        observer.start()
        with self.lock:
            self.observers.append(observer)
            self.watch_folders.append(folder)
        logger.info(f"Started watching folder: {folder} (watch_start_time={self.watch_start_time:.3f})")

    def _is_old_file(self, file_path):
        """以「监控启动水位」判定文件是否为旧文件：
        last-write 时间早于/等于监控启动时刻 → 启动前已存在，跳过压缩。

        取不到文件状态时返回 True（fail-safe）：宁可漏压一个新文件，也不重复压一个已存在文件。
        """
        try:
            st = os.stat(file_path)
        except OSError:
            return True
        return st.st_mtime <= self.watch_start_time

    def _on_file_created(self, file_path):
        if not self.config.get_auto_compression_enabled():
            logger.debug("Auto compression is disabled")
            return
        # 双保险：即使事件处理器漏判，也绝不把压缩副本再次送去做压缩
        if is_compressed_output(file_path):
            logger.debug(f"Skipping compressed output at dispatch: {file_path}")
            return
        # 跳过监控启动前已存在的旧文件（以时间戳水位判定，杜绝误压缩已有文件）
        if self._is_old_file(file_path):
            logger.debug(f"Skipping pre-existing file (write time predates watch start): {file_path}")
            return
        # 本软件刚写过 / 正在处理该路径 → 跳过，防止「手动压缩后监控又压一遍」
        if self.compression_manager.is_recently_written(file_path):
            logger.debug(f"Skipping recently written file: {file_path}")
            return
        # 该文件已被自动处理过且此后没有变化 → 跳过（重启后依然生效）
        if self.compression_manager.is_recorded_same(file_path):
            logger.debug(f"Skipping already processed file: {file_path}")
            return

        logger.info(f"Adding compression task for: {file_path}")
        # add_task(is_auto=True) 会在入队瞬间登记去重账本，事件风暴下同一路径只会入队一次
        if self.compression_manager.add_task(file_path):
            logger.info(f"Successfully added task for: {file_path}")
        else:
            logger.warning(f"Failed to add task for: {file_path}")

    def _check_and_recover_observers(self):
        """检查并恢复失效的观察者（仅在控制线程内调用）。"""
        if not self._running.is_set():
            return
        with self.lock:
            alive = [o.is_alive() for o in self.observers]
        if alive and not all(alive):
            logger.warning(f"Recovering {alive.count(False)} failed observer(s)")
            self._update_watchers()

    def _cleanup_suppressed(self):
        """清理过期的抑制记录，避免字典无限增长。"""
        now = time.time()
        with self.lock:
            before = len(self.suppressed)
            expired = [k for k, until in self.suppressed.items() if until + self.SUPPRESS_TTL < now]
            for k in expired:
                self.suppressed.pop(k, None)
            after = len(self.suppressed)
        if expired:
            logger.info(f"Cleaned up {len(expired)} stale suppression entries ({before} -> {after})")
