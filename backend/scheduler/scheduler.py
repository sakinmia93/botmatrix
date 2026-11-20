"""APScheduler-backed task runner for bot scheduled commands."""
from __future__ import annotations

import logging
import threading
from typing import Optional

logger = logging.getLogger("scheduler")

try:
    from apscheduler.schedulers.background import BackgroundScheduler
except Exception:  # pragma: no cover
    BackgroundScheduler = None  # type: ignore

_scheduler = None
_lock = threading.Lock()


def _plan_maintenance():
    try:
        from backend import plans
        a = plans.expire_plans_tick()
        b = plans.monthly_free_reset_tick()
        if a or b:
            logger.info("plan maintenance: expired=%s free_reset=%s", a, b)
    except Exception:
        logger.exception("plan maintenance")


def start_scheduler():
    global _scheduler
    with _lock:
        if _scheduler is not None and getattr(_scheduler, "running", False):
            return
        if BackgroundScheduler is None:
            logger.warning("APScheduler not installed; scheduler disabled")
            return
        _scheduler = BackgroundScheduler(timezone="UTC")
        try:
            _scheduler.add_job(
                _plan_maintenance, "interval", hours=6, id="plan_maintenance",
                replace_existing=True, max_instances=1, coalesce=True,
            )
        except Exception:
            logger.exception("plan job")
        try:
            _scheduler.start()
            logger.info("Scheduler started")
        except Exception:
            logger.exception("scheduler start")


def stop_scheduler():
    global _scheduler
    with _lock:
        if _scheduler is not None:
            try:
                _scheduler.shutdown(wait=False)
            except Exception:
                pass
            _scheduler = None


def schedule_task(*args, **kwargs):
    return None


def cancel_task(*args, **kwargs):
    return None
