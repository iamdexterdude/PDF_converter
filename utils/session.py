"""
Per-user session: in-memory store of pending images and conversion options.

Sessions auto-expire after settings.SESSION_TTL_SECONDS to free disk.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Literal, Optional

from config import settings

log = logging.getLogger(__name__)

PageSize = Literal["A4", "Letter", "Legal", "A3", "A5", "Auto"]
Orientation = Literal["Portrait", "Landscape", "Auto"]
FitMode = Literal["Fit", "Fill", "Stretch", "Original"]
Quality = Literal["High", "Medium", "Low"]


@dataclass
class PdfOptions:
    page_size: PageSize = "A4"
    orientation: Orientation = "Auto"
    fit_mode: FitMode = "Fit"
    quality: Quality = "High"
    margin_mm: int = 10
    grayscale: bool = False
    one_per_page: bool = True
    add_page_numbers: bool = False
    password: Optional[str] = None
    title: Optional[str] = None
    author: Optional[str] = None


@dataclass
class Session:
    user_id: int
    work_dir: Path
    images: List[Path] = field(default_factory=list)
    options: PdfOptions = field(default_factory=PdfOptions)
    last_active: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.last_active = time.time()

    @property
    def image_count(self) -> int:
        return len(self.images)

    def add_image(self, path: Path) -> None:
        self.images.append(path)
        self.touch()

    def clear_images(self) -> None:
        for p in self.images:
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
        self.images.clear()
        self.touch()

    def reorder(self, new_order: List[int]) -> None:
        """Reorder images by a list of current indices."""
        self.images = [self.images[i] for i in new_order]
        self.touch()

    def remove_at(self, idx: int) -> Optional[Path]:
        if 0 <= idx < len(self.images):
            p = self.images.pop(idx)
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
            self.touch()
            return p
        return None

    def cleanup(self) -> None:
        try:
            shutil.rmtree(self.work_dir, ignore_errors=True)
        except OSError as e:
            log.warning("Cleanup failed for %s: %s", self.work_dir, e)


class SessionManager:
    """Async-safe session registry with TTL-based cleanup."""

    def __init__(self) -> None:
        self._sessions: Dict[int, Session] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    async def get(self, user_id: int) -> Session:
        async with self._lock:
            sess = self._sessions.get(user_id)
            if sess is None:
                work_dir = settings.WORK_DIR / f"user_{user_id}"
                work_dir.mkdir(parents=True, exist_ok=True)
                sess = Session(user_id=user_id, work_dir=work_dir)
                self._sessions[user_id] = sess
            sess.touch()
            return sess

    async def drop(self, user_id: int) -> None:
        async with self._lock:
            sess = self._sessions.pop(user_id, None)
        if sess is not None:
            sess.cleanup()

    async def _sweep(self) -> None:
        """Periodically drop expired sessions."""
        while True:
            await asyncio.sleep(300)  # every 5 min
            now = time.time()
            expired: List[int] = []
            async with self._lock:
                for uid, s in self._sessions.items():
                    if now - s.last_active > settings.SESSION_TTL_SECONDS:
                        expired.append(uid)
            for uid in expired:
                log.info("Expiring session for user %d", uid)
                await self.drop(uid)

    def start_sweeper(self) -> None:
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._sweep())


session_manager = SessionManager()
