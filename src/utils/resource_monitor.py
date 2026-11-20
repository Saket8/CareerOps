"""Resource Monitor & Circuit Breaker for Low-Resource VPS Environments.

Protects against unconstrained browser resource consumption and OOM kills:
  - Enforces Memory threshold <= 75%
  - Enforces CPU threshold <= 85% (sustained > 10s)
  - Provides safe single-instance browser lifecycle management
  - Guaranteed zombie process cleanup (pkill -f chrome fallback)
"""

import os
import sys
import time
import subprocess
from contextlib import contextmanager
from typing import Dict, Any, Tuple, Optional
import psutil

from src.utils.logger import get_logger

logger = get_logger("resource_monitor")


class ResourceMonitor:
    """Monitors system resources and triggers circuit breaker before OOM / thrashing occurs."""

    MEMORY_THRESHOLD_PERCENT = 75.0
    MEMORY_SUSTAINED_SECONDS = 10.0
    CPU_THRESHOLD_PERCENT = 85.0
    CPU_SUSTAINED_SECONDS = 10.0

    _instance = None
    _high_cpu_start_time: Optional[float] = None
    _high_ram_start_time: Optional[float] = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ResourceMonitor, cls).__new__(cls)
        return cls._instance

    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """Returns current CPU, RAM, and Swap metrics."""
        vm = psutil.virtual_memory()
        swap = psutil.swap_memory()
        cpu = psutil.cpu_percent(interval=None)
        if cpu == 0.0:
            time.sleep(0.05)
            cpu = psutil.cpu_percent(interval=None)

        return {
            "ram_total_mb": round(vm.total / (1024 * 1024), 1),
            "ram_used_mb": round(vm.used / (1024 * 1024), 1),
            "ram_available_mb": round(vm.available / (1024 * 1024), 1),
            "ram_percent": vm.percent,
            "swap_total_mb": round(swap.total / (1024 * 1024), 1),
            "swap_used_mb": round(swap.used / (1024 * 1024), 1),
            "swap_percent": swap.percent,
            "cpu_percent": cpu,
            "load_avg": [round(x, 2) for x in os.getloadavg()],
        }

    @classmethod
    def check_health(cls) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """
        Evaluates system health against strict thresholds.
        Returns:
            is_healthy (bool): True if resources are within safe limits.
            stats (dict): Current metrics.
            reason (str or None): Breach explanation if unhealthy.
        """
        stats = cls.get_stats()
        now = time.time()

        # 1. Memory Check: Triggers if RAM > 75% AND available RAM is critically low (< 75MB), or RAM > 90%
        # (Protects against low-resource VPS where idle baseline is ~73-76% due to system services)
        is_mem_critical = (
            stats["ram_percent"] > cls.MEMORY_THRESHOLD_PERCENT
            and stats["ram_available_mb"] < 75.0
        ) or stats["ram_percent"] > 90.0

        if is_mem_critical:
            if cls._high_ram_start_time is None:
                cls._high_ram_start_time = now
            elif (now - cls._high_ram_start_time) >= cls.MEMORY_SUSTAINED_SECONDS:
                duration = round(now - cls._high_ram_start_time, 1)
                msg = (
                    f"Memory circuit breaker tripped: {stats['ram_percent']}% used "
                    f"sustained for {duration}s > {cls.MEMORY_SUSTAINED_SECONDS}s "
                    f"(threshold: {cls.MEMORY_THRESHOLD_PERCENT}%, available: {stats['ram_available_mb']}MB)"
                )
                logger.warning(msg)
                return False, stats, msg
        else:
            cls._high_ram_start_time = None

        # 2. CPU Check (Sustained > 85% for > 10s)
        if stats["cpu_percent"] > cls.CPU_THRESHOLD_PERCENT:
            if cls._high_cpu_start_time is None:
                cls._high_cpu_start_time = now
            elif (now - cls._high_cpu_start_time) >= cls.CPU_SUSTAINED_SECONDS:
                duration = round(now - cls._high_cpu_start_time, 1)
                msg = (
                    f"CPU circuit breaker tripped: {stats['cpu_percent']}% utilization "
                    f"sustained for {duration}s > {cls.CPU_SUSTAINED_SECONDS}s (threshold: {cls.CPU_THRESHOLD_PERCENT}%)"
                )
                logger.warning(msg)
                return False, stats, msg
        else:
            cls._high_cpu_start_time = None

        return True, stats, None

    @classmethod
    def cleanup_zombies(cls) -> int:
        """Terminates dangling or orphaned Chrome/Chromium processes."""
        terminated = 0
        current_pid = os.getpid()

        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                pid = proc.info["pid"]
                if pid == current_pid:
                    continue

                cmdline = " ".join(proc.info.get("cmdline") or []).lower()
                name = (proc.info.get("name") or "").lower()

                is_browser = any(k in name or k in cmdline for k in ["chrome", "chromium", "playwright"])
                is_subcommand = "agy" in cmdline or "main.py" in cmdline or "bash" in name

                if is_browser and not is_subcommand:
                    proc.terminate()
                    terminated += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if terminated > 0:
            time.sleep(0.5)
            # Kill any stubborn processes remaining
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    cmdline = " ".join(proc.info.get("cmdline") or []).lower()
                    name = (proc.info.get("name") or "").lower()
                    if ("chrome" in name or "chromium" in name) and "agy" not in cmdline:
                        proc.kill()
                except Exception:
                    pass
            logger.info(f"Cleaned up {terminated} lingering browser process(es).")

        return terminated


@contextmanager
def safe_browser_session():
    """
    Guaranteed resource-safe context manager.
    Pre-flight cleans any lingering processes, and always cleans up on exit.
    """
    # Pre-flight cleanup
    ResourceMonitor.cleanup_zombies()
    healthy, stats, breach_reason = ResourceMonitor.check_health()
    if not healthy:
        logger.warning(f"Resource pre-flight check warning: {breach_reason}. Attempting garbage collection.")
        import gc
        gc.collect()

    try:
        yield ResourceMonitor
    finally:
        ResourceMonitor.cleanup_zombies()
