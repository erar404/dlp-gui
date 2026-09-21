"""Entry point for DLP-UI.

The implementation lives in the `dlp_gui` package next to this file —
see dlp_gui/app.py for the main window and dlp_gui/ui/ for its tabs.
"""
from dlp_gui.app import App


def main():
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()


if __name__ == "__main__":
    main()
