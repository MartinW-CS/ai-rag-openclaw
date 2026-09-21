"""One background builder, coalesced updates, and leased immutable indexes."""
from contextlib import contextmanager
from dataclasses import dataclass
import logging
from pathlib import Path
import shutil
import tempfile
from threading import Condition, RLock, Thread

logger = logging.getLogger(__name__)


@dataclass(eq=False)
class Version:
    index: object
    signature: tuple
    readers: int = 0
    retired: bool = False


class IndexUnavailable(Exception):
    pass


class IndexService:
    def __init__(self, directory: Path, builder, poll_seconds=2):
        self.directory = directory
        self.builder = builder
        self.poll_seconds = poll_seconds
        self.condition = Condition(RLock())
        self.current = None
        self.building = None
        self.failed = None
        self.retry_requested = False
        self.stopping = False
        self.thread = None

    def paths(self):
        return sorted(p for p in self.directory.glob('*.pdf') if p.is_file() and not p.is_symlink())

    def signature(self):
        records = []
        for path in self.paths():
            try:
                stat = path.stat()
            except FileNotFoundError:
                # Streamlit may remove a file independently of the API lock.
                continue
            records.append((path.name, stat.st_size, stat.st_mtime_ns))
        return tuple(records)

    def start(self):
        self.thread = Thread(target=self._worker, name='rag-index-builder', daemon=True)
        self.thread.start()

    def stop(self):
        with self.condition:
            self.stopping = True
            self.condition.notify_all()
        if self.thread:
            self.thread.join()  # Never release process ownership while a build is still running.
        with self.condition:
            old, self.current = self.current, None
            self._retire(old)

    def changed(self):
        # One pending state, not an unbounded queue of full rebuild jobs.
        with self.condition:
            self.condition.notify_all()

    def retry(self):
        with self.condition:
            if self.failed is not None:
                self.failed = None
                self.retry_requested = True
            self.condition.notify_all()

    def documents(self):
        with self.condition:
            signature = self.signature()
            ready = dict((item[0], item) for item in self.current.signature) if self.current else {}
            building = set(self.building or ())
            failed = set(self.failed or ())
            return [dict(name=item[0], size=item[1], status=(
                'indexed' if ready.get(item[0]) == item else
                'failed' if item in failed else
                'indexing' if item in building else 'queued'
            )) for item in signature]

    @contextmanager
    def lease(self):
        with self.condition:
            version = self.current
            if version is None:
                raise IndexUnavailable('索引尚未就绪，请等待文档处理完成。')
            active = set(self.signature())
            allowed = [item[0] for item in version.signature if item in active]
            if not allowed:
                raise IndexUnavailable('没有已就绪的文档，请上传 PDF 或等待索引完成。')
            version.readers += 1
        try:
            yield version, allowed
        finally:
            with self.condition:
                version.readers -= 1
                if version.retired and version.readers == 0:
                    self._close(version.index)

    def filter_current(self, retrieved, signature):
        # Remove deleted/replaced sources again after retrieval and before returning an answer.
        with self.condition:
            active = set(self.signature())
            allowed = {item[0] for item in signature if item in active}
            return [(text, meta) for text, meta in retrieved if meta['source'] in allowed]

    def _close(self, index):
        try:
            index.close()
        except Exception:
            logger.exception('Failed to retire index')

    def _retire(self, version):
        if version is not None:
            version.retired = True
            if version.readers == 0:
                self._close(version.index)

    def _worker(self):
        while True:
            with self.condition:
                if self.stopping:
                    return
                try:
                    target = self.signature()
                except OSError:
                    self.condition.wait(self.poll_seconds)
                    continue
                current = self.current.signature if self.current else None
                if target == current or (target == self.failed and not self.retry_requested):
                    self.condition.wait(self.poll_seconds)
                    continue
                self.retry_requested = False
                if not target:
                    old, self.current = self.current, None
                    self._retire(old)
                    self.failed = None
                    self.condition.wait(self.poll_seconds)
                    continue
                self.building = target
            candidate = None
            try:
                # Copies protect reads from API rename/removal and external in-place edits.
                with tempfile.TemporaryDirectory(prefix='rag-index-') as temp:
                    for name, _, _ in target:
                        shutil.copy2(self.directory / name, Path(temp) / name)
                    candidate = self.builder(Path(temp))
                with self.condition:
                    if not self.stopping and self.signature() == target:
                        old = self.current
                        self.current = Version(candidate, target)
                        candidate = None
                        self.failed = None
                        self._retire(old)
            except Exception:
                logger.exception('Background indexing failed')
                with self.condition:
                    self.failed = target
            finally:
                if candidate is not None:
                    self._close(candidate)
                with self.condition:
                    self.building = None
                    self.condition.notify_all()
