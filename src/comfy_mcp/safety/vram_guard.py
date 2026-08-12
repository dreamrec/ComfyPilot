"""VRAMGuard - VRAM monitoring and safety enforcement.

Monitors GPU VRAM usage and provides safety checks before operations.
"""
from __future__ import annotations

import asyncio
import csv
import json
import shutil
import subprocess
import time
from typing import Any
from urllib.parse import urlparse


class VRAMGuard:
    """Monitors and enforces VRAM safety thresholds."""

    def __init__(self, client: Any, warn_pct: float = 80.0, block_pct: float = 95.0):
        self._client = client
        self.warn_pct = warn_pct
        self.block_pct = block_pct
        self._limits = {"max_queue": 10, "timeout": 300}
        self._queue_first_seen: dict[str, float] = {}
        self._nvml_cache: dict | None = None
        self._nvml_cache_at = 0.0

    async def check_vram(self) -> dict:
        """Check current VRAM usage and return status (ok/warn/critical)."""
        stats = await self._client.get_system_stats()
        devices = stats.get("devices", []) if isinstance(stats, dict) else []
        nvml = (
            await self._get_nvml_snapshot()
            if devices and self._is_local_client()
            else {"available": False, "devices": [], "processes": []}
        )
        if not devices:
            return {
                "status": "unknown",
                "message": "No GPU devices found",
                "vram_used_pct": 0.0,
                "devices": [],
                "nvml_available": bool(nvml.get("available")),
                "gpu_processes": nvml.get("processes", []),
            }

        device_infos = []
        overall_status = "ok"
        nvml_devices: dict[int, dict] = {}
        for index, device in enumerate(nvml.get("devices", [])):
            if not isinstance(device, dict):
                continue
            try:
                nvml_devices[int(device.get("index", index))] = device
            except (TypeError, ValueError):
                continue
        for position, dev in enumerate(devices):
            total = dev.get("vram_total", 0)
            free = dev.get("vram_free", 0)
            used = total - free
            used_pct = round(used / total * 100, 1) if total > 0 else 0
            try:
                device_index = int(dev.get("index", position))
            except (TypeError, ValueError):
                device_index = position
            nvml_device = nvml_devices.get(device_index, {})

            status = "ok"
            if used_pct >= self.block_pct:
                status = "critical"
                overall_status = "critical"
            elif used_pct >= self.warn_pct:
                status = "warn"
                if overall_status != "critical":
                    overall_status = "warn"

            device_infos.append({
                "name": dev.get("name", "unknown"),
                "vram_total": total,
                "vram_free": free,
                "vram_used": used,
                "vram_used_pct": used_pct,
                "status": status,
                "index": device_index,
                "nvml_vram_total": nvml_device.get("vram_total"),
                "nvml_vram_free": nvml_device.get("vram_free"),
                "nvml_vram_used": nvml_device.get("vram_used"),
                "process_vram_used": nvml_device.get("process_vram_used", 0),
            })

        # Report the max used_pct so the top-level number matches the worst
        # device, which is the one that drives `overall_status`. The old code
        # copied device 0 unconditionally, which could yield contradictory
        # results like status=critical + vram_used_pct=10 on multi-GPU rigs.
        max_used_pct = max(
            (d["vram_used_pct"] for d in device_infos), default=0,
        )
        return {
            "status": overall_status,
            "vram_used_pct": max_used_pct,
            "devices": device_infos,
            "nvml_available": bool(nvml.get("available")),
            "gpu_processes": nvml.get("processes", []),
        }

    async def estimated_headroom_mb(self) -> float | None:
        """Return conservative free VRAM across visible devices in MiB."""
        snapshot = await self.check_vram()
        free_values: list[int] = []
        for device in snapshot.get("devices", []):
            free = device.get("vram_free")
            nvml_free = device.get("nvml_vram_free")
            candidates = [
                int(value) for value in (free, nvml_free)
                if isinstance(value, (int, float)) and value >= 0
            ]
            if candidates:
                free_values.append(min(candidates))
        if not free_values:
            return None
        return min(free_values) / (1024 * 1024)

    async def _get_nvml_snapshot(self) -> dict:
        """Return a short-lived, dependency-optional NVML process snapshot."""
        now = time.monotonic()
        if self._nvml_cache is not None and now - self._nvml_cache_at < 1.0:
            return self._nvml_cache
        try:
            snapshot = await asyncio.to_thread(self._read_nvml_snapshot)
        except Exception as exc:
            snapshot = {"available": False, "devices": [], "processes": [], "error": str(exc)}
        self._nvml_cache = snapshot
        self._nvml_cache_at = now
        return snapshot

    def _is_local_client(self) -> bool:
        """Avoid reporting the MCP host's GPU for a remote ComfyUI server."""
        base_url = getattr(self._client, "base_url", "")
        if not isinstance(base_url, str):
            return False
        host = (urlparse(base_url).hostname or "").lower()
        return host in {"127.0.0.1", "localhost", "::1"}

    @staticmethod
    def _read_nvml_snapshot() -> dict:
        """Best-effort NVML aggregation with no hard pynvml dependency."""
        try:
            import pynvml  # type: ignore[import-not-found]
        except ImportError:
            return VRAMGuard._read_nvidia_smi_snapshot()

        try:
            pynvml.nvmlInit()
            count = int(pynvml.nvmlDeviceGetCount())
        except Exception as exc:
            fallback = VRAMGuard._read_nvidia_smi_snapshot()
            fallback.setdefault("error", str(exc))
            return fallback

        devices: list[dict] = []
        process_totals: dict[tuple[int, int], dict] = {}
        process_functions = [
            name
            for name in (
                "nvmlDeviceGetComputeRunningProcesses_v3",
                "nvmlDeviceGetComputeRunningProcesses_v2",
                "nvmlDeviceGetComputeRunningProcesses",
                "nvmlDeviceGetGraphicsRunningProcesses_v3",
                "nvmlDeviceGetGraphicsRunningProcesses_v2",
                "nvmlDeviceGetGraphicsRunningProcesses",
            )
            if hasattr(pynvml, name)
        ]
        for index in range(count):
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(index)
                memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
                raw_name = pynvml.nvmlDeviceGetName(handle)
                name = raw_name.decode(errors="replace") if isinstance(raw_name, bytes) else str(raw_name)
                device_process_bytes = 0
                seen_pids: set[int] = set()
                for function_name in process_functions:
                    try:
                        processes = getattr(pynvml, function_name)(handle) or []
                    except Exception:
                        continue
                    for process in processes:
                        pid = int(getattr(process, "pid", 0) or 0)
                        used = int(getattr(process, "usedGpuMemory", 0) or 0)
                        if pid <= 0 or used < 0 or used > int(memory.total):
                            continue
                        key = (index, pid)
                        if key not in process_totals or used > process_totals[key]["used_gpu_memory"]:
                            process_totals[key] = {
                                "pid": pid,
                                "device_index": index,
                                "used_gpu_memory": used,
                            }
                        seen_pids.add(pid)
                for pid in seen_pids:
                    device_process_bytes += process_totals[(index, pid)]["used_gpu_memory"]
                devices.append({
                    "index": index,
                    "name": name,
                    "vram_total": int(memory.total),
                    "vram_free": int(memory.free),
                    "vram_used": int(memory.used),
                    "process_vram_used": device_process_bytes,
                })
            except Exception:
                continue

        for process in process_totals.values():
            try:
                raw_name = pynvml.nvmlSystemGetProcessName(process["pid"])
                process["name"] = (
                    raw_name.decode(errors="replace") if isinstance(raw_name, bytes) else str(raw_name)
                )
            except Exception:
                process["name"] = "unknown"
        return {
            "available": bool(devices),
            "source": "pynvml",
            "devices": devices,
            "processes": sorted(
                process_totals.values(),
                key=lambda process: process["used_gpu_memory"],
                reverse=True,
            ),
        }

    @staticmethod
    def _read_nvidia_smi_snapshot() -> dict:
        """Fallback to nvidia-smi when the optional pynvml package is absent."""
        executable = shutil.which("nvidia-smi")
        if not executable:
            return {"available": False, "devices": [], "processes": []}
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        def _run(query: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [
                    executable,
                    f"--query-{query}",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
                creationflags=creation_flags,
            )

        gpu_result = _run("gpu=index,uuid,name,memory.total,memory.used,memory.free")
        if gpu_result.returncode != 0:
            return {
                "available": False,
                "devices": [],
                "processes": [],
                "error": gpu_result.stderr.strip(),
            }

        devices: list[dict] = []
        uuid_to_index: dict[str, int] = {}
        mib = 1024 * 1024
        for row in csv.reader(gpu_result.stdout.splitlines()):
            if len(row) < 6:
                continue
            try:
                index = int(row[0].strip())
                total = int(float(row[3].strip())) * mib
                used = int(float(row[4].strip())) * mib
                free = int(float(row[5].strip())) * mib
            except ValueError:
                continue
            gpu_uuid = row[1].strip()
            uuid_to_index[gpu_uuid] = index
            devices.append({
                "index": index,
                "name": row[2].strip(),
                "vram_total": total,
                "vram_free": free,
                "vram_used": used,
                "process_vram_used": 0,
            })

        processes: list[dict] = []
        process_result = _run("compute-apps=pid,gpu_uuid,used_memory,process_name")
        if process_result.returncode == 0:
            seen: set[tuple[int, int]] = set()
            for row in csv.reader(process_result.stdout.splitlines()):
                if len(row) < 4:
                    continue
                try:
                    pid = int(row[0].strip())
                except ValueError:
                    continue
                device_index = uuid_to_index.get(row[1].strip(), 0)
                key = (device_index, pid)
                if key in seen:
                    continue
                seen.add(key)
                try:
                    used = int(float(row[2].strip())) * mib
                except ValueError:
                    # WDDM commonly withholds per-process memory while still
                    # exposing the PID/name, which remains useful worker data.
                    used = 0
                processes.append({
                    "pid": pid,
                    "device_index": device_index,
                    "used_gpu_memory": used,
                    "name": row[3].strip() or "unknown",
                })
                for device in devices:
                    if device["index"] == device_index:
                        device["process_vram_used"] += used
                        break
        return {
            "available": bool(devices),
            "source": "nvidia-smi",
            "devices": devices,
            "processes": sorted(
                processes,
                key=lambda process: process["used_gpu_memory"],
                reverse=True,
            ),
        }

    async def validate_before_queue(self) -> dict:
        """Pre-flight check before queueing a prompt. Checks VRAM headroom and queue size."""
        vram = await self.check_vram()
        queue = await self._client.get_queue()
        running = len(queue.get("queue_running", []))
        pending = len(queue.get("queue_pending", []))
        total_queued = running + pending

        issues = []
        if vram["status"] == "critical":
            issues.append(f"VRAM critically high at {vram['vram_used_pct']}%")
        if total_queued >= self._limits["max_queue"]:
            issues.append(f"Queue full: {total_queued} items (max {self._limits['max_queue']})")

        return {
            "safe_to_queue": len(issues) == 0,
            "vram_status": vram["status"],
            "vram_used_pct": vram["vram_used_pct"],
            "queue_running": running,
            "queue_pending": pending,
            "issues": issues,
        }

    def set_limits(self, **kwargs) -> dict:
        """Update safety thresholds."""
        if "warn_pct" in kwargs:
            self.warn_pct = float(kwargs["warn_pct"])
        if "block_pct" in kwargs:
            self.block_pct = float(kwargs["block_pct"])
        if "max_queue" in kwargs:
            self._limits["max_queue"] = int(kwargs["max_queue"])
        if "timeout" in kwargs:
            self._limits["timeout"] = int(kwargs["timeout"])
        return {
            "warn_pct": self.warn_pct,
            "block_pct": self.block_pct,
            "max_queue": self._limits["max_queue"],
            "timeout": self._limits["timeout"],
        }

    async def emergency_stop(self) -> dict:
        """Emergency stop: interrupt current job, clear queue, free VRAM."""
        actions: list[str] = []
        errors: list[dict] = []
        operations = (
            ("interrupted", self._client.interrupt, {}),
            ("queue_cleared", self._client.clear_queue, {}),
            (
                "vram_freed",
                self._client.free_vram,
                {"unload_models": True, "free_memory": True},
            ),
        )
        for action, operation, kwargs in operations:
            try:
                await operation(**kwargs)
                actions.append(action)
            except Exception as exc:
                errors.append({"action": action, "error": str(exc)})
        return {
            "status": "stopped" if not errors else "partial",
            "actions": actions,
            "errors": errors,
        }

    async def detect_instability(self) -> dict:
        """Check for stuck jobs, error spikes, OOM patterns."""
        issues: list[str] = []
        checks: dict[str, dict] = {}
        memory_issue = False

        try:
            vram = await self.check_vram()
            devices = vram.get("devices", [])
            checks["vram"] = {"available": bool(devices), "device_count": len(devices)}
        except Exception as exc:
            devices = []
            checks["vram"] = {"available": False, "error": str(exc)}
        for dev in devices:
            total = dev.get("vram_total", 0)
            free = dev.get("vram_free", 0)
            if total > 0 and free / total < 0.05:
                issues.append(f"Near-OOM: {dev.get('name', 'GPU')} has <5% VRAM free")
                memory_issue = True

        try:
            queue = await self._client.get_queue()
            queue_available = isinstance(queue, dict)
        except Exception as exc:
            queue = {}
            queue_available = False
            checks["queue"] = {"available": False, "error": str(exc)}
        running = queue.get("queue_running", []) if isinstance(queue, dict) else []
        pending = queue.get("queue_pending", []) if isinstance(queue, dict) else []
        now = time.time()
        running_ids: set[str] = set()
        for item in running:
            prompt_id, observed_at = self._queue_item_identity(item, now)
            if not prompt_id:
                continue
            running_ids.add(prompt_id)
            first_seen = self._queue_first_seen.setdefault(prompt_id, observed_at)
            elapsed = max(0.0, now - first_seen)
            if elapsed >= self._limits["timeout"]:
                issues.append(
                    f"Stuck job: {prompt_id} has run for {elapsed:.0f}s "
                    f"(timeout {self._limits['timeout']}s)"
                )
        for prompt_id in list(self._queue_first_seen):
            if prompt_id not in running_ids:
                self._queue_first_seen.pop(prompt_id, None)
        if len(running) + len(pending) >= self._limits["max_queue"]:
            issues.append(
                f"Queue pressure: {len(running) + len(pending)} items "
                f"(max {self._limits['max_queue']})"
            )
        if queue_available:
            checks["queue"] = {
                "available": True,
                "running": len(running),
                "pending": len(pending),
                "tracked_running": len(running_ids),
            }

        history_checked = False
        recent_entries = 0
        recent_errors = 0
        recent_oom_errors = 0
        get_history = getattr(self._client, "get_history", None)
        if callable(get_history):
            try:
                history = await get_history(max_items=50)
                if isinstance(history, dict):
                    history_checked = True
                    window = max(600.0, float(self._limits["timeout"]) * 2)
                    for entry in history.values():
                        if not isinstance(entry, dict):
                            continue
                        created_at = self._history_create_time(entry)
                        if created_at is None or created_at > now + 60 or now - created_at > window:
                            continue
                        recent_entries += 1
                        status = entry.get("status", {})
                        status_text = json.dumps(status, default=str).lower()
                        status_str = str(status.get("status_str", "")).lower() if isinstance(status, dict) else ""
                        is_error = status_str in {"error", "failed", "failure"} or "execution_error" in status_text
                        if is_error:
                            recent_errors += 1
                            if any(term in status_text for term in (
                                "out of memory",
                                "cuda oom",
                                "oomerror",
                                "memoryerror",
                                '"oom"',
                            )):
                                recent_oom_errors += 1
            except Exception as exc:
                checks["history"] = {"available": False, "error": str(exc)}
        checks.setdefault("history", {
            "available": history_checked,
            "window_entries": recent_entries,
            "errors": recent_errors,
            "oom_errors": recent_oom_errors,
        })
        if recent_oom_errors:
            issues.append(f"OOM pattern: {recent_oom_errors} recent execution error(s)")
            memory_issue = True
        if recent_errors >= 3 and recent_errors * 2 >= max(recent_entries, 1):
            issues.append(
                f"Error spike: {recent_errors} of {recent_entries} recent executions failed"
            )

        result = {
            "stable": len(issues) == 0,
            "assessment": "unstable" if issues else (
                "stable" if all(check.get("available") for check in checks.values()) else "partial"
            ),
            "issues": issues,
            "queue_running": len(running),
            "queue_pending": len(pending),
            "checks": checks,
        }
        if memory_issue:
            result["recommendations"] = self.recommended_flags()
        return result

    @staticmethod
    def _queue_item_identity(item: Any, now: float) -> tuple[str, float]:
        prompt_id = ""
        metadata: dict = {}
        if isinstance(item, (list, tuple)):
            if len(item) > 1:
                prompt_id = str(item[1])
            if len(item) > 3 and isinstance(item[3], dict):
                metadata = item[3]
        elif isinstance(item, dict):
            prompt_id = str(item.get("prompt_id") or item.get("id") or "")
            metadata = item
        created_at = metadata.get("create_time")
        try:
            created_at = float(created_at)
            while abs(created_at) >= 10_000_000_000:
                created_at /= 1000.0
            if created_at <= 0 or created_at > now + 60:
                created_at = now
        except (TypeError, ValueError):
            created_at = now
        return prompt_id, created_at

    @staticmethod
    def _history_create_time(entry: dict) -> float | None:
        value = entry.get("create_time")
        prompt = entry.get("prompt")
        if (
            value is None
            and isinstance(prompt, (list, tuple))
            and len(prompt) > 3
            and isinstance(prompt[3], dict)
        ):
            value = prompt[3].get("create_time")
        try:
            timestamp = float(value)
        except (TypeError, ValueError):
            return None
        while abs(timestamp) >= 10_000_000_000:
            timestamp /= 1000.0
        return timestamp

    @staticmethod
    def recommended_flags() -> dict:
        """ComfyUI memory-management flags worth knowing about.

        Dynamic VRAM mode (v0.16.0+) is now the *default* - older guides that
        tell users to opt in are out of date. The other two flags are
        opt-in escape hatches for near-OOM situations on large video models.
        """
        return {
            "dynamic_vram_default": True,
            "notes": (
                "ComfyUI v0.16+ enables dynamic VRAM by default. The flags "
                "below are explicit overrides - useful when the heuristic "
                "guesses wrong on large Flux/Wan/LTX video graphs."
            ),
            "flags": {
                "--enable-dynamic-vram": (
                    "Force dynamic VRAM management even when ComfyUI has "
                    "decided not to enable it on this hardware. Helpful on "
                    "borderline GPUs with the older detection heuristic."
                ),
                "--fp16-intermediates": (
                    "Run intermediate tensors at fp16 precision (v0.18.0+). "
                    "Significant VRAM savings on Flux 2 / Wan 2.2 / LTX-2 / "
                    "HunyuanVideo with minimal quality cost."
                ),
                "--cpu-vae": (
                    "Move VAE decode to CPU when GPU is near full. Slows "
                    "decode but unblocks generation."
                ),
                "--lowvram": (
                    "Last-resort mode that aggressively offloads models. "
                    "Use --enable-dynamic-vram first - lowvram is a "
                    "fallback for systems where dynamic VRAM fails."
                ),
            },
            "precision_formats": {
                "mxfp8": "Supported since v0.18.0 - 8-bit microscaled FP for transformers.",
                "nvfp4": "Supported since v0.8.0 - NVIDIA FP4 matrix multiplication.",
                "fp8": "Long-supported; combine with --fp16-intermediates for best memory.",
            },
        }
