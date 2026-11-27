"""libs.TelegramSession — concatenates tg_part1 + tg_part2 at import."""
from pathlib import Path
import importlib.util, sys
here = Path(__file__).resolve().parent
src = (here / "tg_part1.py").read_text() + (here / "tg_part2.py").read_text()
full = here / "_telegram_session_full.py"
full.write_text(src)
name = "backend.sandbox.libs._telegram_session_full"
sys.modules.pop(name, None)
spec = importlib.util.spec_from_file_location(name, full)
mod = importlib.util.module_from_spec(spec)
sys.modules[name] = mod
spec.loader.exec_module(mod)
TelegramSession = mod.TelegramSession
TelegramSessionLib = getattr(mod, "TelegramSessionLib", TelegramSession)
__all__ = ["TelegramSession", "TelegramSessionLib"]
