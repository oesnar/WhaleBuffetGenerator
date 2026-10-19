import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "app.py"
ASSETS = ROOT / "assets"
ICON_ICO = ASSETS / "botc_icon.ico"
ICON_ICNS = ASSETS / "botc_icon.icns"


def add_data_args():
    if not ASSETS.exists():
        return []
    separator = ";" if os.name == "nt" else ":"
    return ["--add-data", f"{ASSETS}{separator}assets"]


def build():
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        "WhaleBuffetGenerator",
        "--onefile",
        "--hidden-import=PIL",
        "--collect-all=PIL",
    ]

    if os.name == "nt":
        cmd.append("--windowed")
        if ICON_ICO.exists():
            cmd.extend(["--icon", str(ICON_ICO)])
    elif sys.platform == "darwin":
        cmd.append("--windowed")
        if ICON_ICNS.exists():
            cmd.extend(["--icon", str(ICON_ICNS)])

    cmd.extend(add_data_args())
    cmd.append(str(APP))

    print("Running:")
    print(" ".join(cmd))
    subprocess.run(cmd, cwd=str(ROOT), check=True)


if __name__ == "__main__":
    build()
