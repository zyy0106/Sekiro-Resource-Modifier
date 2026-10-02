"""Check the standalone EXE with synthetic data and no Python search paths."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    exe = Path(sys.argv[1]).resolve()
    if not exe.is_file():
        raise SystemExit(f"Missing executable: {exe}")
    with tempfile.TemporaryDirectory(prefix="srm_portable_check_") as directory:
        env = {key: value for key, value in os.environ.items()
               if key.upper() not in {"PATH", "PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "APPDATA", "LOCALAPPDATA"}}
        windows = next((v for k, v in env.items() if k.upper() == "SYSTEMROOT"), r"C:\Windows")
        env["PATH"] = str(Path(windows) / "System32") + os.pathsep + windows
        env["APPDATA"] = directory
        env["LOCALAPPDATA"] = directory
        report = Path(directory) / "report.json"
        result = subprocess.run([str(exe), "--self-test-report", str(report)],
                                env=env, cwd=directory, timeout=90)
        data = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {}
        if result.returncode != 0 or not data.get("passed"):
            raise SystemExit(f"Portable check failed ({result.returncode}): {data}")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        print("Standalone EXE passed with Windows-only PATH and synthetic saves.")


if __name__ == "__main__":
    main()
