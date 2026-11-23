"""BOT MATRIX API server — load boot parts then run."""
from pathlib import Path
_p = Path(__file__).with_name
_code = "".join(_p(f"sboot{i}.txt").read_text() for i in range(3))
exec(compile(_code, str(_p("server_boot.py")), "exec"), globals())
