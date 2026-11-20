"""Bot runtime — re-exports the full engine runtime."""
from backend.runtime_core import *  # noqa: F401,F403
from backend.runtime_core import (
    init_engine,
    sync_bot,
    set_running,
    is_running,
    stop_worker,
    resume_all,
    engine_pk,
    drop_engine_bot,
    uptime_text,
    restart_if_running,
    maintenance_get,
    process_update,
    run_external,
    Worker,
)

# Ensure /api/new-webhook uses stable-secret verification (webhook_handler)
try:
    from backend.webhook_handler import install_webhook_route
    install_webhook_route()
except Exception:
    pass
