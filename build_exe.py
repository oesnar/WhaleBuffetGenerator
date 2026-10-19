import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "app.py"
ASSETS = ROOT / "assets"
TEMPLATES = ROOT / "templates"
ICON_ICO = ASSETS / "botc_icon.ico"
ICON_ICNS = ASSETS / "botc_icon.icns"


def add_data_args():
    separator = ";" if os.name == "nt" else ":"
    data_args = []
    for source, destination in ((ASSETS, "assets"), (TEMPLATES, "templates")):
        if source.exists():
            data_args.extend(["--add-data", f"{source}{separator}{destination}"])
    return data_args


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
