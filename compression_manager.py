import json
import os
import queue
import threading
import time
import uuid

from PyQt5.QtCore import QObject, pyqtSignal

from tinypng_api import TinyPNGAPI
from config_manager import ConfigManager
from logging_system import logger
from utils import (
    format_file_size, COMPRESSED_SUFFIX, is_allowed_file, normkey, get_state_path
)


class ProcessedRegistry:
    """自动压缩去重账本（持久化）。

    记录每个文件最近一次被处理时的 (mtime, size)：
    - 重启后依然记得“这个文件已经压过了”（旧实现只在内存里记，重启即清空）；
    - 外部因素（同步盘 / 杀软 / 资源管理器移动）把 mtime 推新时，只要 (mtime, size)
      与账本完全一致，仍判为“未变化”，不会重复压缩。

    仅服务于自动(监控)路径；手动压缩是用户显式意图，不查询账本。
    """

    SAVE_INTERVAL = 2.0          # 变更落盘的最小间隔（秒）
    MAX_AGE = 30 * 24 * 3600     # 记录最长保留 30 天
    MAX_ENTRIES = 5000           # 记录条数上限

    def __init__(self, path=None):
        self.path = path or get_state_path()
        self._lock = threading.RLock()
        self._entries = {}
        self._dirty = False
        self._last_save = 0.0
        self._load()

    # ---------------- 持久化 ----------------
    def _load(self):
        try:
            if not os.path.exists(self.path):
                return
            with open(self.path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            entries = data.get('entries', {}) if isinstance(data, dict) else {}
            if isinstance(entries, dict):
                self._entries = {
                    k: (float(v[0]), int(v[1]))
                    for k, v in entries.items()
                    if isinstance(v, (list, tuple)) and len(v) == 2
                }
        except Exception as e:
            logger.warning(f"Failed to load processed state: {e}")
            self._entries = {}

    def flush(self, force=False):
        with self._lock:
            if not force:
                if not self._dirty or (time.time() - self._last_save) < self.SAVE_INTERVAL:
                    return
            self._prune_locked()
            try:
                tmp_path = f"{self.path}.tmp"
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump({'version': 1, 'entries': self._entries}, f)
                os.replace(tmp_path, self.path)
                self._dirty = False
                self._last_save = time.time()
            except Exception as e:
                logger.warning(f"Failed to save processed state: {e}")

    def _prune_locked(self):
        now = time.time()
        stale = [k for k, sig in self._entries.items() if now - sig[0] > self.MAX_AGE]
        for k in stale:
            self._entries.pop(k, None)
        if len(self._entries) > self.MAX_ENTRIES:
            ordered = sorted(self._entries.items(), key=lambda kv: kv[1][0], reverse=True)
            self._entries = dict(ordered[:self.MAX_ENTRIES])

    def prune(self):
        with self._lock:
            self._prune_locked()
            self._dirty = True
        self.flush(force=True)

    # ---------------- 查询/登记 ----------------
    @staticmethod
    def _stat(file_path):
        try:
            st = os.stat(file_path)
            return (st.st_mtime, st.st_size)
        except OSError:
            return None

    def is_recorded_same(self, file_path):
        """当前文件的 (mtime, size) 与账本完全一致 → 已处理且未变化。"""
        sig = self._stat(file_path)
        if sig is None:
            return False
        with self._lock:
            return self._entries.get(normkey(file_path)) == sig

    def mark(self, file_path):
        sig = self._stat(file_path)
        if sig is None:
            return
        with self._lock:
            self._entries[normkey(file_path)] = sig
            self._dirty = True
        self.flush()


class CompressionTask:
    def __init__(self, input_path, output_path=None, is_auto=True, batch_id=None):
        self.input_path = input_path
        self.output_path = output_path
        self.is_auto = is_auto
        self.batch_id = batch_id
        self.status = 'pending'
        self.error = None
        self.result = None
        self.finished = False


class _Batch:
    """手动批量压缩的记账对象：由 manager 汇总，界面只负责渲染。"""

    def __init__(self, batch_id, is_auto=False):
        self.id = batch_id
        self.is_auto = is_auto
        self.total = 0
        self.remaining = 0
        self.ok = 0
        self.failed = 0
        self.total_orig = 0
        self.total_comp = 0
        self.errors = []
        self.started = time.time()
        self.finalized = False

    def summary(self):
        return {
            'batch_id': self.id,
            'total': self.total,
            'ok': self.ok,
            'failed': self.failed,
            'original_size': self.total_orig,
            'compressed_size': self.total_comp,
            'ratio': (1 - self.total_comp / self.total_orig) if self.total_orig > 0 else 0.0,
            'elapsed': max(time.time() - self.started, 0.0),
            'errors': list(self.errors),
        }


class CompressionManager(QObject):
    """唯一的压缩管线：手动（用户拖放/选择）与自动（目录监控）任务的共同入口。

    - 所有网络请求都在后台 worker 线程执行，界面线程只收信号，不会卡死；
    - 手动任务优先级高于自动任务，用户拖入的文件不会被后台自动任务排到后面；
    - 输出路径、去重账本、压缩计数统一在这一层处理，避免多处重复实现。
    """

    compressionStarted = pyqtSignal(str, bool)              # (basename, is_auto)
    compressionFinished = pyqtSignal(str, bool, str, bool)  # (basename, ok, message, is_auto)
    batchFinished = pyqtSignal(str, object, bool)           # (batch_id, summary(dict), is_auto)
    queueChanged = pyqtSignal(int)                          # 队列剩余长度

    PRIORITY_MANUAL = 0
    PRIORITY_AUTO = 1
    RECENT_WRITE_TTL = 30.0    # 写盘后抑制监控再次派发的时长（覆盖事件到达与账本登记之间的竞态）
    IN_FLIGHT_TTL = 120.0      # 处理期间抑制同一路径被重复派发

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = ConfigManager()
        self.registry = ProcessedRegistry()
        self._queue = queue.PriorityQueue()
        self._seq = 0
        self._seq_lock = threading.Lock()
        self._batch_lock = threading.Lock()
        self._batches = {}
        self._active_lock = threading.Lock()
        self._active = {}          # {normkey: 抑制截止时间}
        self.running = False
        self.worker_thread = None
        self.monitor_thread = None

    # ---------------- 生命周期 ----------------
    def start(self):
        if not self.running:
            self.running = True
            self.worker_thread = threading.Thread(target=self._worker, daemon=True)
            self.worker_thread.start()

            if self.monitor_thread is None or not self.monitor_thread.is_alive():
                self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
                self.monitor_thread.start()

            logger.info("Compression manager started")

    def stop(self):
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
        try:
            self.registry.flush(force=True)
        except Exception as e:
            logger.warning(f"Failed to flush processed state on exit: {e}")
        logger.info("Compression manager stopped")

    # ---------------- 入队 ----------------
    def _default_output_path(self, input_path):
        """未显式指定输出路径时计算默认输出（手动与自动共用同一套规则）。
        勾选替换原文件 -> 直接写回原文件；
        否则生成与原文件同名、加 _compressed 后缀的新文件，原文件保持不变。
        """
        if self.config.get_replace_original():
            return input_path
        base, ext = os.path.splitext(input_path)
        out_dir = self.config.get_output_path()
        if not (out_dir and os.path.isdir(out_dir)):
            out_dir = os.path.dirname(input_path) or '.'
        stem = os.path.basename(base)
        return os.path.join(out_dir, f"{stem}{COMPRESSED_SUFFIX}{ext}")

    def is_allowed(self, file_path):
        """按『只压缩PNG』开关判断文件是否可处理（供监控器与任务入队统一使用）。"""
        return is_allowed_file(file_path, self.config.get_only_png())

    def is_recorded_same(self, file_path):
        """供监控器判断：该文件是否已被自动处理过且此后没有变化。"""
        return self.registry.is_recorded_same(file_path)

    def is_recently_written(self, file_path):
        """该路径是否正处于「本软件刚写过 / 正在处理」的抑制窗口内。"""
        key = normkey(file_path)
        if not key:
            return False
        with self._active_lock:
            expiry = self._active.get(key)
            return bool(expiry and expiry > time.time())

    def _mark_active(self, file_path, ttl):
        key = normkey(file_path)
        if not key:
            return
        now = time.time()
        with self._active_lock:
            expired = [k for k, exp in self._active.items() if exp < now]
            for k in expired:
                self._active.pop(k, None)
            self._active[key] = now + ttl

    def add_task(self, input_path, output_path=None, is_auto=True, batch_id=None):
        if not self.is_allowed(input_path):
            logger.warning(f"Invalid file type: {input_path}")
            return False

        if output_path is None:
            output_path = self._default_output_path(input_path)

        task = CompressionTask(input_path, output_path, is_auto, batch_id)

        # 自动任务在入队瞬间即登记账本：事件风暴下同一路径只会入队一次
        if is_auto:
            try:
                self.registry.mark(input_path)
            except Exception as e:
                logger.warning(f"Failed to mark registry for {input_path}: {e}")

        with self._seq_lock:
            self._seq += 1
            seq = self._seq
        priority = self.PRIORITY_MANUAL if not is_auto else self.PRIORITY_AUTO
        self._queue.put((priority, seq, task))

        if batch_id:
            with self._batch_lock:
                batch = self._batches.get(batch_id)
                if batch:
                    batch.remaining += 1

        logger.info(f"Added compression task: {input_path} -> {output_path}")
        self.queueChanged.emit(self._queue.qsize())
        return True

    def add_batch(self, paths):
        """把一批文件按「手动」语义入队，返回 batch_id；无有效文件时返回 None。"""
        candidates = [p for p in paths if self.is_allowed(p)]
        if not candidates:
            return None

        batch_id = uuid.uuid4().hex
        batch = _Batch(batch_id, is_auto=False)
        with self._batch_lock:
            self._batches[batch_id] = batch

        added = 0
        for path in candidates:
            if self.add_task(path, is_auto=False, batch_id=batch_id):
                added += 1

        emit_now = False
        with self._batch_lock:
            if added == 0:
                self._batches.pop(batch_id, None)
                return None
            batch.total = added
            batch.finalized = True
            if batch.remaining <= 0:
                self._batches.pop(batch_id, None)
                emit_now = True

        if emit_now:
            self.batchFinished.emit(batch_id, batch.summary(), False)
        logger.info(f"Batch {batch_id} queued with {added} file(s)")
        return batch_id

    # ---------------- worker ----------------
    def _worker(self):
        while self.running:
            try:
                _priority, _seq, task = self._queue.get(timeout=1)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Worker error: {e}")
                continue

            try:
                self._process_task(task)
            except Exception as e:
                # 任何未捕获异常都不能让线程退出或丢失队列记账
                logger.error(f"Unhandled worker error for {task.input_path}: {e}")
                try:
                    self._finish_task(task, False, str(e), None)
                except Exception as inner:
                    logger.error(f"Failed to finalize task {task.input_path}: {inner}")
            finally:
                try:
                    self._queue.task_done()
                except Exception:
                    pass

    def _process_task(self, task):
        task.status = 'processing'
        # 处理期间抑制监控对同一路径的重复派发（防「手动压缩 + 监控」双压）
        self._mark_active(task.input_path, self.IN_FLIGHT_TTL)
        self.compressionStarted.emit(os.path.basename(task.input_path), task.is_auto)

        api_key = self.config.get_current_api_key()
        if not api_key or not str(api_key).strip():
            self._finish_task(task, False, "未配置 API 密钥", None)
            return

        try:
            api = TinyPNGAPI(api_key)
            result = api.compress_file(task.input_path, task.output_path, self.config.get_timeout())
        except Exception as e:
            logger.error(f"Compression failed for {task.input_path}: {e}")
            self._finish_task(task, False, str(e), None)
            return

        task.result = result
        original_size = format_file_size(result['original_size'])
        compressed_size = format_file_size(result['compressed_size'])
        ratio = f"{result['ratio'] * 100:.2f}%"
        logger.info(f"Compression completed: {task.input_path} -> {task.output_path}")
        logger.info(f"Original: {original_size}, Compressed: {compressed_size}, Ratio: {ratio}")
        self._finish_task(
            task, True,
            f"{original_size} -> {compressed_size} ({ratio})",
            result
        )

    def _finish_task(self, task, ok, message, result):
        if task.finished:
            return
        task.finished = True
        task.status = 'completed' if ok else 'failed'
        task.error = None if ok else message

        # 写回抑制 + 账本登记：这是「被本软件改过的文件不会被监控再压一遍」的关键
        input_path = task.input_path
        output_path = task.output_path
        same_target = (not output_path) or normkey(output_path) == normkey(input_path)
        try:
            self._mark_active(input_path, self.RECENT_WRITE_TTL)
            if not same_target:
                self._mark_active(output_path, self.RECENT_WRITE_TTL)
            self.registry.mark(input_path)
            if not same_target:
                self.registry.mark(output_path)
        except Exception as e:
            logger.warning(f"Failed to record processed state for {input_path}: {e}")

        if ok and result and 'compression_count' in result:
            try:
                self.config.set_compression_count(result['compression_count'])
            except Exception as e:
                logger.warning(f"Failed to update compression count: {e}")

        try:
            self.compressionFinished.emit(os.path.basename(input_path), bool(ok), message, task.is_auto)
        except Exception as e:
            logger.warning(f"Failed to emit compression result: {e}")

        self._record_batch(task, ok, message, result)
        self.queueChanged.emit(self._queue.qsize())

    def _record_batch(self, task, ok, message, result):
        if not task.batch_id:
            return
        emit_now = False
        with self._batch_lock:
            batch = self._batches.get(task.batch_id)
            if batch is None:
                return
            batch.remaining -= 1
            if ok and result:
                batch.ok += 1
                batch.total_orig += result['original_size']
                batch.total_comp += result['compressed_size']
            else:
                batch.failed += 1
                batch.errors.append(f"{os.path.basename(task.input_path)}: {message}")
            if batch.finalized and batch.remaining <= 0:
                self._batches.pop(task.batch_id, None)
                emit_now = True
        if emit_now:
            self.batchFinished.emit(batch.id, batch.summary(), batch.is_auto)

    def get_queue_size(self):
        return self._queue.qsize()

    # ---------------- 后台自恢复/清理 ----------------
    def _monitor_loop(self):
        """监控循环：恢复工作线程，定期裁剪去重账本。"""
        last_prune = time.time()
        while self.running:
            try:
                time.sleep(10)

                if not self.running:
                    break

                if self.worker_thread is None or not self.worker_thread.is_alive():
                    logger.warning("Worker thread is not alive, restarting...")
                    self.worker_thread = threading.Thread(target=self._worker, daemon=True)
                    self.worker_thread.start()
                    logger.info("Worker thread restarted")

                if time.time() - last_prune > 600:
                    self.registry.prune()
                    last_prune = time.time()

            except Exception as e:
                logger.error(f"Error in compression manager monitor loop: {e}")
