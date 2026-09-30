# -*- coding: utf-8 -*-

import time

_SIDES = ("left", "right", "top", "bottom")
_RETRY_SECONDS = 2.0   # overlay bulunamazsa yeniden arama aralığı
_POLL_MS = 1000        # yedek yoklama; asıl tetikleme olay tabanlı
_DOCK_TTL = 2.0        # dock var mı sonucunun geçerlilik süresi
_HIDDEN_THICKNESS = 30

_DEFAULT_SIZE = 24
_DEFAULT_MARGIN = 3
_DEFAULT_GAP = 3


def _qt():
    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtWidgets
    return QtCore, QtWidgets


def _find_overlay(mw, QtWidgets, side):
    exact = {
        "left": "OverlayLeft",
        "right": "OverlayRight",
        "top": "OverlayTop",
        "bottom": "OverlayBottom",
    }[side]

    w = mw.findChild(QtWidgets.QWidget, exact)
    if w:
        return w

    for cand in mw.findChildren(QtWidgets.QWidget):
        try:
            cls = cand.metaObject().className()
            name = (cand.objectName() or "").lower()
        except Exception:
            continue
        if "overlaytabwidget" in cls.lower() and side in name:
            return cand
    return None


def debug():
    import FreeCADGui as Gui
    QtCore, QtWidgets = _qt()
    mw = Gui.getMainWindow()

    print("--- Overlay widgets ---")
    for w in mw.findChildren(QtWidgets.QWidget):
        n = w.objectName()
        c = w.metaObject().className()
        if "overlay" in (n + c).lower():
            print(repr(n), c, "visible=", w.isVisible(), "geom=", w.geometry())

    print("--- Butons ---")
    buttons = getattr(mw, "_cp_overlay_panel_buttons", None)
    if not buttons:
        print("Butonlar kurulmamis.")
        return
    for side, b in buttons.items():
        ov = _find_overlay(mw, QtWidgets, side)
        print(
            side,
            "button_visible=", b.isVisible(),
            "pos=", b.pos(),
            "size=", (b.width(), b.height()),
            "margin=", b.cpMargin,
            "gap=", b.cpGap,
            "overlay_found=", ov is not None,
            "overlay_visible=", (ov.isVisible() if ov else None),
            "overlay_size=", ((ov.width(), ov.height()) if ov else None),
        )


def install():
    QtCore, QtWidgets = _qt()
    try:
        from PySide6 import QtGui
    except ImportError:
        from PySide2 import QtGui

    import FreeCAD
    import FreeCADGui as Gui

    app = QtWidgets.QApplication.instance()
    mw = Gui.getMainWindow()

    if not app or not mw:
        return

    if hasattr(mw, "_cp_overlay_panel_buttons"):
        return

    class _OverlayButton(QtWidgets.QToolButton):

        def __init__(self, parent, object_name, text, tooltip, command, side):
            super().__init__(parent)
            self._margin = _DEFAULT_MARGIN
            self._gap = _DEFAULT_GAP
            self._hover_icon = QtGui.QIcon()
            self._normal_icon = None  # hover sırasında saklanan normal ikon
            self._placed = False

            self.setObjectName(object_name)
            self.setText(text)
            self.setToolTip(tooltip)
            self.setAutoRaise(True)
            self.setCursor(QtCore.Qt.PointingHandCursor)
            self.setFocusPolicy(QtCore.Qt.NoFocus)
            self.setProperty("cpOverlaySide", side)
            self._command = command
            self.clicked.connect(self._run_command)
            self.hide()

        def _get_margin(self):
            return self._margin

        def _set_margin(self, value):
            self._margin = max(0, int(value))

        def _get_gap(self):
            return self._gap

        def _set_gap(self, value):
            self._gap = max(0, int(value))

        cpMargin = QtCore.Property(int, _get_margin, _set_margin)
        cpGap = QtCore.Property(int, _get_gap, _set_gap)

        def _get_icon_hover(self):
            return self._hover_icon

        def _set_icon_hover(self, icon):
            self._hover_icon = icon

        cpIconHover = QtCore.Property(QtGui.QIcon, _get_icon_hover, _set_icon_hover)

        def _swap_to_hover(self):
            if self._normal_icon is None and not self._hover_icon.isNull():
                self._normal_icon = self.icon()
                self.setIcon(self._hover_icon)

        def _restore_normal(self):
            if self._normal_icon is not None:
                self.setIcon(self._normal_icon)
                self._normal_icon = None

        def enterEvent(self, event):
            self._swap_to_hover()
            super().enterEvent(event)

        def leaveEvent(self, event):
            self._restore_normal()
            super().leaveEvent(event)

        def hideEvent(self, event):
            # Tıklayınca panel açılıp buton gizlenirse leaveEvent gelmeyebilir
            self._restore_normal()
            self._placed = False
            super().hideEvent(event)

        # -------------------------------------------------------------------
        def sizeHint(self):
            hint = super().sizeHint()
            if hint.width() <= 0 or hint.height() <= 0:
                return QtCore.QSize(_DEFAULT_SIZE, _DEFAULT_SIZE)
            return hint

        def _run_command(self):
            try:
                Gui.runCommand(self._command)
            except Exception as e:
                FreeCAD.Console.PrintError(
                    "ColorPalette: overlay butonu komutu calistirilamadi - "
                    f"{self._command}: {e}\n"
                )

        def place(self):
            p = self.parentWidget()
            cw = p.centralWidget() if p is not None else None
            if cw is None:
                return

            self.ensurePolished()
            hint = self.sizeHint()
            if self.size() != hint:
                self.resize(hint)

            origin = cw.mapTo(p, QtCore.QPoint(0, 0))
            x0, y0 = origin.x(), origin.y()
            w, h = cw.width(), cw.height()
            bw, bh = self.width(), self.height()
            margin = self._margin
            gap = self._gap
            side = self.property("cpOverlaySide")

            if side == "left":
                tx, ty = x0 + margin, y0 + margin
            elif side == "right":
                tx, ty = x0 + max(0, w - bw - margin), y0 + margin
            elif side == "top":
                left_w = buttons["left"].width() if "left" in buttons else bw
                tx, ty = x0 + margin + left_w + gap, y0 + margin
            elif side == "bottom":
                tx, ty = x0 + margin, y0 + max(0, h - bh - margin)
            else:
                return

            target = QtCore.QPoint(tx, ty)
            moved = self.pos() != target
            if moved:
                self.move(target)
            if moved or not self._placed:
                self.raise_()
                self._placed = True

    buttons = {
        "left": _OverlayButton(
            mw, "cpOverlayLeftButton", "‹",
            "show / hide", "Std_DockOverlayToggleLeft", "left",
        ),
        "right": _OverlayButton(
            mw, "cpOverlayRightButton", "›",
            "show / hide", "Std_DockOverlayToggleRight", "right",
        ),
        "top": _OverlayButton(
            mw, "cpOverlayTopButton", "⌃",
            "show / hide", "Std_DockOverlayToggleTop", "top",
        ),
        "bottom": _OverlayButton(
            mw, "cpOverlayBottomButton", "⌄",
            "show / hide", "Std_DockOverlayToggleBottom", "bottom",
        ),
    }

    class _OverlayMonitor(QtCore.QObject):
        _MW_EVENTS = (
            QtCore.QEvent.Resize,
            QtCore.QEvent.Show,
            QtCore.QEvent.LayoutRequest,
        )
        _OVERLAY_EVENTS = (
            QtCore.QEvent.Resize,
            QtCore.QEvent.Show,
            QtCore.QEvent.Hide,
            QtCore.QEvent.ChildAdded,
            QtCore.QEvent.ChildRemoved,
        )
        _DOCK_EVENTS = (
            QtCore.QEvent.Show,
            QtCore.QEvent.Hide,
            QtCore.QEvent.ChildAdded,
            QtCore.QEvent.ChildRemoved,
        )

        def __init__(self):
            super().__init__(mw)
            self._cache = {}       # side -> overlay widget
            self._retry_at = {}    # side -> monotonic zaman (bulunamadıysa)
            self._docks_at = {}    # side -> (zaman, dock var mı)
            self._scheduled = False
            mw.installEventFilter(self)
            # Yedek yoklama: olay kaçarsa (ör. overlay geç oluşursa) yakalar
            self._timer = QtCore.QTimer(self)
            self._timer.setInterval(_POLL_MS)
            self._timer.timeout.connect(self.update_all)
            self._timer.start()
            app.applicationStateChanged.connect(self._on_app_state)

        def _on_app_state(self, _state):
            self._schedule()

        def _schedule(self):
            if not self._scheduled:
                self._scheduled = True
                QtCore.QTimer.singleShot(0, self._flush)

        def _flush(self):
            self._scheduled = False
            self.update_all()

        def eventFilter(self, obj, event):
            t = event.type()
            if obj is mw:
                if t in self._MW_EVENTS:
                    self._schedule()
            elif t in self._OVERLAY_EVENTS:
                if t in self._DOCK_EVENTS:
                    self._docks_at.clear()
                self._schedule()
            return False

        @staticmethod
        def _is_hidden(overlay, side):
            if not overlay.isVisible():
                return True
            if side in ("left", "right"):
                return overlay.width() <= _HIDDEN_THICKNESS
            return overlay.height() <= _HIDDEN_THICKNESS

        def _overlay(self, side):
            w = self._cache.get(side)
            if w is not None:
                try:
                    w.objectName()  # silinmişse RuntimeError fırlatır
                    return w
                except Exception:
                    self._cache.pop(side, None)

            now = time.monotonic()
            if now < self._retry_at.get(side, 0.0):
                return None

            w = _find_overlay(mw, QtWidgets, side)
            if w is None:
                self._retry_at[side] = now + _RETRY_SECONDS
                return None
            self._cache[side] = w
            self._retry_at.pop(side, None)
            w.installEventFilter(self)
            return w

        def _has_docks(self, side, overlay):
            now = time.monotonic()
            cached = self._docks_at.get(side)
            if cached is not None and now - cached[0] < _DOCK_TTL:
                return cached[1]
            result = overlay.findChild(QtWidgets.QDockWidget) is not None
            self._docks_at[side] = (now, result)
            return result

        def update_all(self):
            try:
                if not mw.isVisible() or mw.isMinimized():
                    return
                if app.applicationState() != QtCore.Qt.ApplicationActive:
                    return

                for side in _SIDES:
                    button = buttons[side]
                    overlay = self._overlay(side)

                    visible = False
                    if overlay is not None:
                        if self._is_hidden(overlay, side):
                            visible = self._has_docks(side, overlay)
                        else:
                            self._docks_at.pop(side, None)

                    if button.isVisible() != visible:
                        button.setVisible(visible)
                    if visible:
                        button.place()
            except Exception:
                pass

    monitor = _OverlayMonitor()

    mw._cp_overlay_panel_buttons = buttons
    mw._cp_overlay_panel_buttons_monitor = monitor

    monitor.update_all()


def uninstall():
    try:
        import FreeCADGui as Gui
        mw = Gui.getMainWindow()
        if not mw:
            return

        monitor = getattr(mw, "_cp_overlay_panel_buttons_monitor", None)
        if monitor:
            monitor._timer.stop()
            monitor.deleteLater()

        for button in getattr(mw, "_cp_overlay_panel_buttons", {}).values():
            button.deleteLater()

        for attr in ("_cp_overlay_panel_buttons", "_cp_overlay_panel_buttons_monitor"):
            if hasattr(mw, attr):
                delattr(mw, attr)
    except Exception:
        pass
