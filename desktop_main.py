"""Windows exe 入口：启动 uvicorn 并自动打开浏览器。

PyInstaller 打包时以此为入口 (见 build/windows.spec)。
"""
import os
import sys
import threading
import webbrowser

import uvicorn

HOST = "127.0.0.1"
PORT = 8000


def _open_browser():
    webbrowser.open(f"http://{HOST}:{PORT}")


def main():
    # PyInstaller onefile 会把资源解包到 sys._MEIPASS，
    # web.server 已通过该变量定位 static 目录。
    if getattr(sys, "frozen", False):
        os.chdir(getattr(sys, "_MEIPASS", os.getcwd()))

    threading.Timer(1.5, _open_browser).start()

    from web.server import app

    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
