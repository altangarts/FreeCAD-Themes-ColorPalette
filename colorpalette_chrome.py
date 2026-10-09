import FreeCAD

try:
    from PySide6 import QtCore, QtWidgets, QtGui
    try:
        import shiboken6 as _shiboken
    except ImportError:
        _shiboken = None
except ImportError:
    from PySide2 import QtCore, QtWidgets, QtGui
    try:
        import shiboken2 as _shiboken
    except ImportError:
        _shiboken = None


_STATE_GRP_PATH = "User parameter:BaseApp/Preferences/Mod/ColorPaletteState"
KEY_STATUSBAR_AUTOHIDE = "StatusBarAutoHide"
KEY_MENUBAR_BUTTON = "MenuBarAsButton"

STRIP_HEIGHT = 12
LAYOUT_DEBOUNCE_MS = 150
LAYOUT_BUSY_MS = 300
_QWIDGETSIZE_MAX = 16777215

MENU_LEFT_GAP = 2 
MENU_RIGHT_GAP = 2 
WB_LEFT_GAP = 0  
WB_RIGHT_GAP = 0 

WORKBENCH_TOOLBAR_NAME = "Workbench"
WORKBENCH_COMBOBOX_CLASS = "WorkbenchComboBox"

_MODE_COMBO = "combo"
_MODE_TAB = "tab"


def _grp():
    return FreeCAD.ParamGet(_STATE_GRP_PATH)


def _is_valid(obj):
    if _shiboken is None:
        return True
    try:
        return _shiboken.isValid(obj)
    except Exception:
        return True


def _make_spacer(width):
    w = QtWidgets.QWidget()
    w.setObjectName("CPGapSpacer")
    w.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
    w.setFixedWidth(int(width))
    w.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Ignored)
    return w


def _main_window():
    try:
        import FreeCADGui as Gui
        return Gui.getMainWindow()
    except Exception:
        return None


def _direct_toolbars(mw):
    try:
        return mw.findChildren(
            QtWidgets.QToolBar, options=QtCore.Qt.FindDirectChildrenOnly
        )
    except TypeError:
        return mw.findChildren(QtWidgets.QToolBar)


def _workbench_mode(tb):
    cb = tb.findChild(QtWidgets.QComboBox)
    if cb is not None and cb.isVisibleTo(tb):
        return _MODE_COMBO
    tabs = tb.findChild(QtWidgets.QTabBar)
    if tabs is not None and tabs.isVisibleTo(tb):
        return _MODE_TAB
    return None


# --------------------------------------------------------------------------- #
# Ortak ana pencere izleyicisi
# --------------------------------------------------------------------------- #

class _MainWindowWatcher(QtCore.QObject):

    def __init__(self, mw):
        super().__init__(mw)
        self._mw = mw
        self._handlers = {}
        mw.installEventFilter(self)

    def subscribe(self, etype, callback):
        self._handlers.setdefault(etype, []).append(callback)

    def unsubscribe(self, callback):
        for et in list(self._handlers):
            remaining = [c for c in self._handlers[et] if c != callback]
            if remaining:
                self._handlers[et] = remaining
            else:
                del self._handlers[et]
        if not self._handlers:
            _drop_watcher()

    def eventFilter(self, obj, event):
        callbacks = self._handlers.get(event.type())
        if callbacks:
            for cb in list(callbacks):
                try:
                    cb()
                except RuntimeError:
                    pass
        return False


_watcher = None


def _get_watcher(mw):
    global _watcher
    if _watcher is None:
        _watcher = _MainWindowWatcher(mw)
    return _watcher


def _drop_watcher():
    global _watcher
    w = _watcher
    _watcher = None
    if w is not None:
        try:
            w._mw.removeEventFilter(w)
        except Exception:
            pass
        w.deleteLater()


# --------------------------------------------------------------------------- #
# 1) Dinamik Status Bar (Otomatik Gizleme)
# --------------------------------------------------------------------------- #

class _ClickStrip(QtWidgets.QWidget):
    clicked = QtCore.Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("CPStatusClickStrip")
        self.setFixedHeight(STRIP_HEIGHT)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

    def paintEvent(self, event):
        pass

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()
            event.accept()
        else:
            super().mousePressEvent(event)


class _StatusBarAutoHide(QtCore.QObject):

    def __init__(self, mw):
        super().__init__(mw)
        self._mw = mw
        self._sb = mw.statusBar()
        self._open = False
        self._disposed = False
        self._app_filter_on = False

        self._strip = _ClickStrip(mw)
        self._strip.clicked.connect(self._open_bar)

        watcher = _get_watcher(mw)
        watcher.subscribe(QtCore.QEvent.Resize, self._on_mw_geometry)
        watcher.subscribe(QtCore.QEvent.Show, self._on_mw_geometry)
        self._sb.installEventFilter(self)

        self._close_bar()

    def _on_mw_geometry(self):
        if not self._open:
            self._place_strip()

    def _place_strip(self):
        mw = self._mw
        rect = QtCore.QRect(
            0,
            max(0, mw.height() - STRIP_HEIGHT),
            mw.width(),
            STRIP_HEIGHT,
        )
        if self._strip.geometry() != rect:
            self._strip.setGeometry(rect)

    def _set_app_filter(self, on):
        if on == self._app_filter_on:
            return
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        if on:
            app.installEventFilter(self)
        else:
            app.removeEventFilter(self)
        self._app_filter_on = on

    def _open_bar(self):
        if self._open or self._disposed:
            return
        self._open = True
        self._strip.hide()
        self._sb.show()
        self._set_app_filter(True)

    def _close_bar(self):
        self._set_app_filter(False)
        self._open = False
        if self._sb.isVisible():
            self._sb.hide()
        self._place_strip()
        self._strip.show()
        self._strip.raise_()

    def _enforce_hidden(self):
        if self._disposed:
            return
        if not self._open and self._sb.isVisible():
            self._sb.hide()
            self._place_strip()
            self._strip.show()
            self._strip.raise_()

    def _is_inside_statusbar(self, obj):
        if not isinstance(obj, QtWidgets.QWidget):
            return False
        return obj is self._sb or self._sb.isAncestorOf(obj)

    def eventFilter(self, obj, event):
        et = event.type()

        if et == QtCore.QEvent.MouseButtonPress:
            if self._open and not self._disposed:
                app = QtWidgets.QApplication.instance()
                # Status bar içindeki bir menü/popup açıksa dokunma.
                if (app is not None and app.activePopupWidget() is None
                        and not self._is_inside_statusbar(obj)):
                    # Tıklamanın kendisi normal işlensin; kapatmayı sonraya bırak.
                    QtCore.QTimer.singleShot(0, self._close_bar)
            return False

        if et == QtCore.QEvent.Show and obj is self._sb:
            if not self._open:
                QtCore.QTimer.singleShot(0, self._enforce_hidden)
        return False

    def dispose(self):
        self._disposed = True
        self._set_app_filter(False)

        try:
            w = _watcher
            if w is not None:
                w.unsubscribe(self._on_mw_geometry)
            self._sb.removeEventFilter(self)
        except Exception:
            pass

        self._strip.hide()
        self._strip.deleteLater()
        self._sb.show()
        self.deleteLater()


# --------------------------------------------------------------------------- #
# 2) Menubar Yerine Tek ToolButton
#    Yerleşim: [Menü butonu] [Workbench combobox] [diğer toolbarlar...]
# --------------------------------------------------------------------------- #

class _MenuBarButton(QtCore.QObject):
    _COLLAPSE_QSS = (
        "QMenuBar { min-height: 0px; max-height: 0px; height: 0px;"
        " padding: 0px; margin: 0px; border: none; }"
    )

    def __init__(self, mw):
        super().__init__(mw)
        self._mw = mw
        self._mb = mw.menuBar()
        self._saved_qss = self._mb.styleSheet()
        self._wb_tb = None
        self._wb_was_movable = True
        self._wb_gap_left = None
        self._wb_gap_right = None
        self._busy = False
        self._disposed = False

        self._menu = QtWidgets.QMenu(mw)
        self._menu.setObjectName("CPMainMenu")
        self._menu.aboutToShow.connect(self._populate)

        self._button = QtWidgets.QToolButton()
        self._button.setObjectName("CPMenuButton")
        self._button.setToolTip("Menu")
        self._button.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self._button.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        self._button.setAutoRaise(True)
        self._button.setIconSize(QtCore.QSize(20, 20))
        self._button.setIcon(self._fallback_icon())
        self._button.setMenu(self._menu)

        self._toolbar = QtWidgets.QToolBar("ColorPalette Menu", mw)
        self._toolbar.setObjectName("CPMenuToolBar")
        self._toolbar.setMovable(False)
        self._toolbar.setFloatable(False)

        tl = self._toolbar.layout()
        if tl is not None:
            tl.setSpacing(0)
            tl.setContentsMargins(0, 0, 0, 0)

        if MENU_LEFT_GAP > 0:
            self._toolbar.addWidget(_make_spacer(MENU_LEFT_GAP))
        self._toolbar.addWidget(self._button)
        if MENU_RIGHT_GAP > 0:
            self._toolbar.addWidget(_make_spacer(MENU_RIGHT_GAP))

        try:
            mw.addToolBar(QtCore.Qt.TopToolBarArea, self._toolbar)
        except Exception:
            mw.addToolBar(self._toolbar)

        self._toolbar.show()
        self._collapse_menubar()

        self._check_timer = QtCore.QTimer(self)
        self._check_timer.setSingleShot(True)
        self._check_timer.setInterval(LAYOUT_DEBOUNCE_MS)
        self._check_timer.timeout.connect(self._enforce_layout)

        self._busy_timer = QtCore.QTimer(self)
        self._busy_timer.setSingleShot(True)
        self._busy_timer.setInterval(LAYOUT_BUSY_MS)
        self._busy_timer.timeout.connect(self._release_busy)

        _get_watcher(mw).subscribe(QtCore.QEvent.LayoutRequest, self._on_layout_request)

        for ms in (150, 800, 2500):
            QtCore.QTimer.singleShot(ms, self._enforce_layout)

    # ------------------------------------------------------------------ #

    def _fallback_icon(self):
        color = self._mw.palette().color(QtGui.QPalette.ButtonText)
        pm = QtGui.QPixmap(64, 64)
        pm.fill(QtCore.Qt.transparent)

        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        pen = QtGui.QPen(color, 6)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        p.setPen(pen)

        for y in (16, 32, 48):
            p.drawLine(12, y, 52, y)

        p.end()
        return QtGui.QIcon(pm)

    def _populate(self):
        for act in list(self._menu.actions()):
            try:
                self._menu.removeAction(act)
            except RuntimeError:
                pass

        for action in list(self._mb.actions()):
            try:
                if not _is_valid(action):
                    continue
                if action.isVisible() and (action.menu() is not None or action.text()):
                    self._menu.addAction(action)
            except RuntimeError:
                continue

    def _collapse_menubar(self):
        self._mb.setStyleSheet(self._COLLAPSE_QSS)
        self._mb.setFixedHeight(0)
        self._mb.updateGeometry()

    def _restore_menubar(self):
        self._mb.setStyleSheet(self._saved_qss)
        self._mb.setMinimumHeight(0)
        self._mb.setMaximumHeight(_QWIDGETSIZE_MAX)
        self._mb.updateGeometry()

    # ------------------------------------------------------------------ #
    # Yerleşim
    # ------------------------------------------------------------------ #

    def _on_layout_request(self):
        if not self._busy and not self._disposed:
            self._check_timer.start()

    def _apply_wb_gap(self, wb_tb):
        left = self._wb_gap_left
        if left is not None:
            acts = wb_tb.actions()
            if not _is_valid(left) or not acts or acts[0] is not left or WB_LEFT_GAP <= 0:
                self._drop_gap(wb_tb, "_wb_gap_left")
                left = None
        if left is None and WB_LEFT_GAP > 0:
            acts = wb_tb.actions()
            first = acts[0] if acts else None
            self._wb_gap_left = wb_tb.insertWidget(first, _make_spacer(WB_LEFT_GAP))

        right = self._wb_gap_right
        if right is not None:
            acts = wb_tb.actions()
            if not _is_valid(right) or not acts or acts[-1] is not right or WB_RIGHT_GAP <= 0:
                self._drop_gap(wb_tb, "_wb_gap_right")
                right = None
        if right is None and WB_RIGHT_GAP > 0:
            self._wb_gap_right = wb_tb.addWidget(_make_spacer(WB_RIGHT_GAP))

    def _drop_gap(self, wb_tb, attr):
        act = getattr(self, attr)
        setattr(self, attr, None)
        if act is not None and _is_valid(act):
            try:
                wb_tb.removeAction(act)
                act.deleteLater()
            except RuntimeError:
                pass

    def _remove_wb_gap(self, wb_tb):
        self._drop_gap(wb_tb, "_wb_gap_left")
        self._drop_gap(wb_tb, "_wb_gap_right")

    def _release_wb(self):
        if self._wb_tb is not None:
            try:
                self._remove_wb_gap(self._wb_tb)
            except Exception:
                pass
            try:
                self._wb_tb.setMovable(self._wb_was_movable)
                self._wb_tb.setFloatable(True)
            except Exception:
                pass
        self._wb_tb = None

    @staticmethod
    def _key(tb):
        p = tb.pos()
        return (p.y(), p.x())

    def _is_ordered(self, pinned, others):
        mw = self._mw
        for t in pinned:
            if mw.toolBarArea(t) != QtCore.Qt.TopToolBarArea:
                return False
        keys = [self._key(t) for t in pinned]
        if keys != sorted(keys):
            return False
        last = keys[-1]
        # Kesin küçüktür: eşitlikte döngüye girmemek için
        return not any(self._key(t) < last for t in others)

    def _enforce_layout(self):
        if self._disposed or self._busy:
            return

        if QtWidgets.QApplication.mouseButtons() != QtCore.Qt.NoButton:
            self._check_timer.start()
            return

        mw = self._mw
        all_tbs = _direct_toolbars(mw)

        named = None
        for t in all_tbs:
            if t is not self._toolbar and t.objectName() == WORKBENCH_TOOLBAR_NAME:
                named = t
                break

        mode = _workbench_mode(named) if named is not None else None

        if mode == _MODE_COMBO:
            wb_tb = named
            if self._wb_tb is not wb_tb:
                self._release_wb()
                self._wb_tb = wb_tb
                self._wb_was_movable = wb_tb.isMovable()
            if wb_tb.isMovable():
                wb_tb.setMovable(False)
            if wb_tb.isFloatable():
                wb_tb.setFloatable(False)
            self._apply_wb_gap(wb_tb)
            pinned = [self._toolbar, wb_tb]
            free_tab = None
        else:
            self._release_wb()
            pinned = [self._toolbar]
            free_tab = named if mode == _MODE_TAB else None

        if self._toolbar.isMovable():
            self._toolbar.setMovable(False)
        if self._toolbar.isFloatable():
            self._toolbar.setFloatable(False)

        others = [
            t for t in all_tbs
            if t not in pinned
            and t is not free_tab            # tabbar sıralamaya dahil değil
            and mw.toolBarArea(t) == QtCore.Qt.TopToolBarArea
            and t.isVisibleTo(mw)
        ]

        if self._is_ordered(pinned, others):
            return

        self._busy = True
        self._busy_timer.start()

        for t in pinned:
            mw.removeToolBar(t)

        if others:
            others.sort(key=self._key)
            first_tb = others[0]
            for t in pinned:
                mw.insertToolBar(first_tb, t)
        else:
            for t in pinned:
                mw.addToolBar(QtCore.Qt.TopToolBarArea, t)

        for t in pinned:
            t.show()

    def _release_busy(self):
        self._busy = False

    def dispose(self):
        self._disposed = True
        self._check_timer.stop()
        self._busy_timer.stop()

        try:
            w = _watcher
            if w is not None:
                w.unsubscribe(self._on_layout_request)
        except Exception:
            pass

        self._release_wb()
        self._restore_menubar()

        try:
            self._mw.removeToolBar(self._toolbar)
        except Exception:
            pass

        self._toolbar.deleteLater()
        self._menu.deleteLater()
        self.deleteLater()


# --------------------------------------------------------------------------- #
# Genel API
# --------------------------------------------------------------------------- #

_sb_ctrl = None
_mb_ctrl = None


def is_statusbar_autohide_enabled():
    return _grp().GetBool(KEY_STATUSBAR_AUTOHIDE, True)


def is_menubar_button_enabled():
    return _grp().GetBool(KEY_MENUBAR_BUTTON, True)


def set_statusbar_autohide(enabled, save=True):
    global _sb_ctrl
    enabled = bool(enabled)

    if save:
        _grp().SetBool(KEY_STATUSBAR_AUTOHIDE, enabled)

    mw = _main_window()
    if mw is None:
        return

    if enabled and _sb_ctrl is None:
        _sb_ctrl = _StatusBarAutoHide(mw)
    elif not enabled and _sb_ctrl is not None:
        _sb_ctrl.dispose()
        _sb_ctrl = None


def set_menubar_button(enabled, save=True):
    global _mb_ctrl
    enabled = bool(enabled)

    if save:
        _grp().SetBool(KEY_MENUBAR_BUTTON, enabled)

    mw = _main_window()
    if mw is None:
        return

    if enabled and _mb_ctrl is None:
        _mb_ctrl = _MenuBarButton(mw)
    elif not enabled and _mb_ctrl is not None:
        _mb_ctrl.dispose()
        _mb_ctrl = None


def install(_tries=0):
    mw = _main_window()

    if mw is None or mw.menuBar() is None:
        if _tries < 40:
            QtCore.QTimer.singleShot(
                500,
                lambda: install(_tries + 1),
            )
        else:
            FreeCAD.Console.PrintError(
                "ColorPalette: chrome modulu kurulamadi - ana pencere bulunamadi.\n"
            )
        return

    try:
        set_statusbar_autohide(
            is_statusbar_autohide_enabled(),
            save=False,
        )
        set_menubar_button(
            is_menubar_button_enabled(),
            save=False,
        )
    except Exception as e:
        FreeCAD.Console.PrintError(
            f"ColorPalette: chrome modulu kurulurken hata - {str(e)}\n"
        )
