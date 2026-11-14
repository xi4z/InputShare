import socket
import threading
import pystray

from PIL import Image

from input.controller import schedule_toggle as main_schedule_toggle,\
                             schedule_exit as main_schedule_exit
from scrcpy_client.clipboard_event import SetClipboardEvent
from ui import ICON_ICO_PATH
from ui.settings import open_settings_window
from utils import VoidCallable
from utils.config_manager import get_config
from utils.i18n import get_i18n
from utils.clipboard import Clipboard
from utils.logger import LOGGER, LogType

Menu = pystray.Menu
MenuItem = pystray.MenuItem

# pystray 创建通知区窗口后会调用 ChangeWindowMessageFilterEx。该调用在部分
# 环境下返回 ERROR_ACCESS_DENIED（WinError 5），pystray 会把它当成致命错误，
# 整个托盘线程随即退出，托盘图标不会出现。这个调用只是为了允许提权进程接收
# WM_TASKBARCREATED，失败时忽略即可，因此这里包一层屏蔽该异常。
try:
    from pystray._util import win32 as _pystray_win32
    _original_change_filter = _pystray_win32.ChangeWindowMessageFilterEx

    def _tolerant_change_filter(*args, **kwargs):
        try:
            return _original_change_filter(*args, **kwargs)
        except OSError:
            return True

    _pystray_win32.ChangeWindowMessageFilterEx = _tolerant_change_filter
except Exception:
    pass

tray = None

def create_tray(client_socket: socket.socket):
    global tray

    def send_clipboard_text():
        nonlocal client_socket
        current_clipboard_content = Clipboard.safe_paste()
        if current_clipboard_content is None:
            return
        event = SetClipboardEvent(current_clipboard_content)
        try:
            client_socket.sendall(event.serialize())
        except Exception as e:
            LOGGER.write(LogType.Error, "Send data error: " + str(e))
            exit_tray()

    def toggle_share_keyboard_only(_, item: MenuItem):
        get_config().share_keyboard_only = not item.checked
    def toggle_sync_clipboard(_, item: MenuItem):
        get_config().sync_clipboard = not item.checked

    def exit_tray():
        global tray
        main_schedule_exit()
        assert tray is not None
        tray.stop()

    i18n = get_i18n()
    tray_img = Image.open(ICON_ICO_PATH)
    tray_menu = Menu(
        MenuItem(
            i18n(["Enable sharing", "开启键鼠共享"]),
            action=main_schedule_toggle),
        MenuItem(
            i18n(["Send clipboard text", "发送当前剪贴板文本"]),
            action=send_clipboard_text),
        Menu.SEPARATOR,
        MenuItem(
            i18n(["Share keyboard only", "仅共享键盘"]),
            action=toggle_share_keyboard_only,
            checked=lambda _: get_config().share_keyboard_only),
        MenuItem(
            i18n(["Sync clipboard", "同步剪贴板"]),
            action=toggle_sync_clipboard,
            checked=lambda _: get_config().sync_clipboard),
        Menu.SEPARATOR,
        MenuItem(
            i18n(["Settings", "设置"]),
            action=open_settings_window),
        MenuItem(
            i18n(["Exit", "退出"]),
            action=exit_tray),
    )
    tray = pystray.Icon(
        "InputShare",
        title=i18n(["InputShare", "输入流转"]),
        icon=tray_img,
        menu=tray_menu,
    )
    LOGGER.write(LogType.Info, "Tray started.")
    try:
        tray.run()
    except Exception as e:
        LOGGER.write(LogType.Error, "Tray failed: " + repr(e))

def tray_thread_factory(client_socket: socket.socket) -> VoidCallable:
    def close_tray():
        global tray
        if tray is not None: tray.stop()
        LOGGER.write(LogType.Info, "Tray stopped.")

    thread = threading.Thread(
        target=create_tray,
        args=[client_socket],
        daemon=True,
    )
    thread.start()
    return close_tray
