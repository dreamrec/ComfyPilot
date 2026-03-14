"""JobTracker — tracks prompt execution jobs and their progress.

Monitors active jobs via EventManager, caches completed results,
and supports async wait-for-completion.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any


class JobTracker:
    """Tracks prompt jobs from submission to completion."""

    def __init__(self, client, event_mgr):
        self._client = client
        self._event_mgr = event_mgr
        self._active_jobs: dict[str, dict] = {}  # prompt_id → job status dict
        self._completed: deque[dict] = deque(maxlen=100)

    async def track(self, prompt_id: str) -> None:
        """Start tracking a submitted prompt."""
        self._active_jobs[prompt_id] = {
            "prompt_id": prompt_id,
            "status": "queued",
            "submitted_at": time.time(),
            "progress": 0,
            "max_progress": 0,
        }

    def get_status(self, prompt_id: str) -> dict | None:
        """Get current status of a tracked job."""
        # Check active first
        if prompt_id in self._active_jobs:
            # Update from EventManager progress cache
            progress = self._event_mgr.get_latest_progress(prompt_id)
            if progress:
                job = self._active_jobs[prompt_id]
                job["progress"] = progress.get("data", {}).get("value", 0)
                job["max_progress"] = progress.get("data", {}).get("max", 0)
                job["status"] = "running"
            return self._active_jobs[prompt_id]
        # Check completed
        for job in self._completed:
            if job["prompt_id"] == prompt_id:
                return job
        return None

    async def mark_complete(self, prompt_id: str, result: dict | None = None) -> None:
        """Mark a job as completed and move to completed deque."""
        if prompt_id in self._active_jobs:
            job = self._active_jobs.pop(prompt_id)
            job["status"] = "completed"
            job["completed_at"] = time.time()
            if result:
                job["result"] = result
            self._completed.appendleft(job)

    async def mark_failed(self, prompt_id: str, error: str = "") -> None:
        """Mark a job as failed."""
        if prompt_id in self._active_jobs:
            job = self._active_jobs.pop(prompt_id)
            job["status"] = "failed"
            job["completed_at"] = time.time()
            job["error"] = error
            self._completed.appendleft(job)

    async def mark_cancelled(self, prompt_id: str) -> None:
        """Mark a job as cancelled."""
        if prompt_id in self._active_jobs:
            job = self._active_jobs.pop(prompt_id)
            job["status"] = "cancelled"
            job["completed_at"] = time.time()
            self._completed.appendleft(job)

    async def mark_interrupted(self, prompt_id: str) -> None:
        """Mark a job as interrupted."""
        if prompt_id in self._active_jobs:
            job = self._active_jobs.pop(prompt_id)
            job["status"] = "interrupted"
            job["completed_at"] = time.time()
            self._completed.appendleft(job)

    async def wait_for_completion(self, prompt_id: str, timeout: float = 300, poll_interval: float = 1.0) -> dict:
        """Poll history until prompt is done or timeout."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                history = await self._client.get_history(prompt_id=prompt_id)
                if prompt_id in history:
                    entry = history[prompt_id]
                    status = entry.get("status", {})
                    if status.get("completed", False) or status.get("status_str") == "success":
                        await self.mark_complete(prompt_id, entry)
                        return {"status": "completed", "prompt_id": prompt_id, "result": entry}
                    if status.get("status_str") == "error":
                        error_msg = str(status.get("messages", ["Unknown error"]))
                        await self.mark_failed(prompt_id, error_msg)
                        return {"status": "failed", "prompt_id": prompt_id, "error": error_msg}
            except Exception:
                pass  # History not ready yet, keep polling
            await asyncio.sleep(poll_interval)

        # Timeout
        return {"status": "timeout", "prompt_id": prompt_id, "elapsed": time.time() - start}

    def list_active(self) -> list[dict]:
        """List all currently active jobs."""
        return list(self._active_jobs.values())

    def list_recent(self, limit: int = 20) -> list[dict]:
        """List recently completed jobs."""
        return list(self._completed)[:limit]
