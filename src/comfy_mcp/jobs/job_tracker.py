"""JobTracker - tracks prompt execution jobs and their progress.

Monitors active jobs via EventManager, caches completed results,
and supports async wait-for-completion.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
from collections import deque
from typing import Any


logger = logging.getLogger("comfypilot.jobs")


class JobTracker:
    """Tracks prompt jobs from submission to completion."""

    def __init__(self, client, event_mgr):
        self._client = client
        self._event_mgr = event_mgr
        self._active_jobs: dict[str, dict] = {}  # prompt_id -> job status dict
        self._completed: deque[dict] = deque(maxlen=100)
        subscribe = getattr(event_mgr, "subscribe", None)
        if callable(subscribe):
            for event_type, callback in (
                ("execution_start", self._on_execution_start),
                ("executing", self._on_execution_start),
                ("execution_success", self._on_execution_success),
                ("execution_error", self._on_execution_error),
                ("execution_interrupted", self._on_execution_interrupted),
                ("connection_restored", self._on_connection_restored),
            ):
                registration = subscribe(event_type, callback)
                # Some lifecycle tests use an AsyncMock EventManager. The real
                # API is synchronous; close the synthetic coroutine so it does
                # not leak a RuntimeWarning during teardown.
                if inspect.iscoroutine(registration):
                    registration.close()

    async def track(self, prompt_id: str) -> None:
        """Start tracking a submitted prompt."""
        if self._find_completed(prompt_id) is not None:
            return
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
        self._finish(prompt_id, "completed", result=result)

    async def mark_failed(self, prompt_id: str, error: str = "") -> None:
        """Mark a job as failed."""
        self._finish(prompt_id, "failed", error=error)

    async def mark_cancelled(self, prompt_id: str) -> None:
        """Mark a job as cancelled."""
        self._finish(prompt_id, "cancelled")

    async def mark_interrupted(self, prompt_id: str) -> None:
        """Mark a job as interrupted."""
        self._finish(prompt_id, "interrupted")

    def _find_completed(self, prompt_id: str) -> dict | None:
        for job in self._completed:
            if job.get("prompt_id") == prompt_id:
                return job
        return None

    def _finish(
        self,
        prompt_id: str,
        status: str,
        *,
        result: dict | None = None,
        error: str = "",
    ) -> dict:
        """Synchronously finalize or refresh a job without creating duplicates."""
        existing = self._find_completed(prompt_id)
        if prompt_id in self._active_jobs:
            job = self._active_jobs.pop(prompt_id)
        elif existing is not None:
            job = existing
            self._completed.remove(existing)
        else:
            # Very short workflows can finish over WS before queue_prompt's HTTP
            # response reaches the caller and track() is invoked.
            job = {"prompt_id": prompt_id, "submitted_at": None, "progress": 0, "max_progress": 0}
        job["status"] = status
        job["completed_at"] = time.time()
        if result is not None:
            job["result"] = result
        if error:
            job["error"] = error
        self._completed.appendleft(job)
        return job

    @staticmethod
    def _event_prompt_id(event: dict) -> str:
        data = event.get("data", {}) if isinstance(event, dict) else {}
        return str(data.get("prompt_id", "")) if isinstance(data, dict) else ""

    def _on_execution_start(self, event: dict) -> None:
        prompt_id = self._event_prompt_id(event)
        job = self._active_jobs.get(prompt_id)
        if job is not None:
            job["status"] = "running"
            job.setdefault("started_at", time.time())

    async def _on_execution_success(self, event: dict) -> None:
        prompt_id = self._event_prompt_id(event)
        if not prompt_id:
            return
        await self.mark_complete(prompt_id, event.get("data", {}))
        # History normally lands with the success event. Enrich the tracker
        # when available, but keep the event-derived completion if it lags.
        try:
            await self.reconcile(prompt_id=prompt_id)
        except Exception:
            logger.debug("History not ready for completed prompt %s", prompt_id, exc_info=True)

    def _on_execution_error(self, event: dict) -> None:
        prompt_id = self._event_prompt_id(event)
        if not prompt_id:
            return
        data = event.get("data", {})
        error = (
            data.get("exception_message")
            or data.get("exception_type")
            or data.get("error")
            or json.dumps(data, default=str)
        )
        self._finish(prompt_id, "failed", error=str(error))

    def _on_execution_interrupted(self, event: dict) -> None:
        prompt_id = self._event_prompt_id(event)
        if prompt_id:
            self._finish(prompt_id, "interrupted", result=event.get("data", {}))

    async def _on_connection_restored(self, event: dict) -> None:
        """Reconcile tracked jobs after a ComfyUI process restart/reconnect."""
        await self.reconcile()
        try:
            queue = await self._client.get_queue()
        except Exception:
            return
        queued_ids = self._prompt_ids_from_queue(queue)
        for prompt_id in list(self._active_jobs):
            if prompt_id not in queued_ids:
                self._finish(
                    prompt_id,
                    "failed",
                    error="Job disappeared from queue and history after ComfyUI reconnect",
                )

    @staticmethod
    def _prompt_ids_from_queue(queue: dict) -> set[str]:
        prompt_ids: set[str] = set()
        if not isinstance(queue, dict):
            return prompt_ids
        for key in ("queue_running", "queue_pending"):
            for entry in queue.get(key, []) or []:
                if isinstance(entry, (list, tuple)) and len(entry) > 1:
                    prompt_ids.add(str(entry[1]))
                elif isinstance(entry, dict):
                    prompt_id = entry.get("prompt_id") or entry.get("id")
                    if prompt_id:
                        prompt_ids.add(str(prompt_id))
        return prompt_ids

    @staticmethod
    def _history_status(entry: dict) -> tuple[str | None, str]:
        status = entry.get("status", {}) if isinstance(entry, dict) else {}
        if not isinstance(status, dict):
            return None, ""
        status_str = str(status.get("status_str") or status.get("status") or "").lower()
        if status.get("completed") is True or status_str in {"success", "completed"}:
            return "completed", ""
        if status_str in {"error", "failed", "failure"}:
            messages = status.get("messages") or status.get("error") or "Unknown execution error"
            return "failed", str(messages)
        if status_str in {"interrupted", "cancelled", "canceled"}:
            return "interrupted", str(status.get("messages") or "")
        return None, ""

    async def reconcile(
        self,
        *,
        prompt_id: str | None = None,
        history: dict | None = None,
    ) -> list[str]:
        """Reconcile active/specific jobs against ComfyUI history."""
        if history is None:
            if prompt_id:
                history = await self._client.get_history(prompt_id=prompt_id)
            else:
                history = await self._client.get_history(max_items=max(200, len(self._active_jobs)))
        if not isinstance(history, dict):
            return []

        targets = set(self._active_jobs)
        targets.update(job.get("prompt_id") for job in self._completed)
        if prompt_id:
            targets.add(prompt_id)
        reconciled: list[str] = []
        for candidate in targets:
            if not candidate or candidate not in history:
                continue
            entry = history[candidate]
            state, error = self._history_status(entry)
            if state == "completed":
                self._finish(candidate, "completed", result=entry)
                reconciled.append(candidate)
            elif state == "failed":
                self._finish(candidate, "failed", result=entry, error=error)
                reconciled.append(candidate)
            elif state == "interrupted":
                self._finish(candidate, "interrupted", result=entry, error=error)
                reconciled.append(candidate)
        return reconciled

    async def wait_for_completion(self, prompt_id: str, timeout: float = 300, poll_interval: float = 1.0) -> dict:
        """Poll history until prompt is done or timeout."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                history = await self._client.get_history(prompt_id=prompt_id)
                await self.reconcile(prompt_id=prompt_id, history=history)
                status = self.get_status(prompt_id)
                if status and status.get("status") == "completed":
                    return {
                        "status": "completed",
                        "prompt_id": prompt_id,
                        "result": status.get("result", history.get(prompt_id, {})),
                    }
                if status and status.get("status") in {"failed", "interrupted"}:
                    return {
                        "status": status["status"],
                        "prompt_id": prompt_id,
                        "error": status.get("error", "Unknown error"),
                    }
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
