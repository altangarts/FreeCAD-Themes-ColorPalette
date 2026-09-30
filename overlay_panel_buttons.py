# -*- coding: utf-8 -*-

_SIDES = ("left", "right", "top", "bottom")
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
            super().hideEvent(event)

        # -------------------------------------------------------------------
        def sizeHint(self):
            hint = super().sizeHint()
            # QSS width/height/min-*/max-* hiçbir şey vermediyse varsayılan boyut
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
                self.move(x0 + margin, y0 + margin)
            elif side == "right":
                self.move(x0 + max(0, w - bw - margin), y0 + margin)
            elif side == "top":
                # sol butonun (varsa) yanına yerleşir
                left_w = buttons["left"].width() if "left" in buttons else bw
                self.move(x0 + margin + left_w + gap, y0 + margin)
            elif side == "bottom":
                self.move(x0 + margin, y0 + max(0, h - bh - margin))

            self.raise_()

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
        def __init__(self):
            super().__init__(mw)
            self._last_qss = None
            self._timer = QtCore.QTimer(self)
            self._timer.setInterval(250)
            self._timer.timeout.connect(self.update_all)
            self._timer.start()
            mw.installEventFilter(self)

        def eventFilter(self, obj, event):
            if obj is mw and event.type() in (
                QtCore.QEvent.Resize,
                QtCore.QEvent.Show,
                QtCore.QEvent.LayoutRequest,
            ):
                self._place_all()
            return False

        @staticmethod
        def _is_hidden(overlay, side):
            if not overlay.isVisible():
                return True
            if side in ("left", "right"):
                return overlay.width() <= _HIDDEN_THICKNESS
            return overlay.height() <= _HIDDEN_THICKNESS

        def _sync_qss(self):

            found = None
            for side in _SIDES:
                overlay = _find_overlay(mw, QtWidgets, side)
                if overlay is None:
                    continue
                ss = overlay.styleSheet()
                if ss and ("cpOverlaySide" in ss or "ColorPaletteOverlay" in ss):
                    found = ss
                    break
            if found is None or found == self._last_qss:
                return
            self._last_qss = found
            for b in buttons.values():
                b.setStyleSheet(found)
                b.style().unpolish(b)
                b.style().polish(b)

        def update_all(self):
            try:
                self._sync_qss()
                for side in _SIDES:
                    button = buttons[side]
                    overlay = _find_overlay(mw, QtWidgets, side)  # her seferinde yeniden bul

                    visible = bool(
                        overlay is not None
                        and overlay.findChildren(QtWidgets.QDockWidget)
                        and self._is_hidden(overlay, side)
                    )

                    if button.isVisible() != visible:
                        button.setVisible(visible)
                    if visible:
                        button.place()
            except Exception:
                pass

        def _place_all(self):
            for b in buttons.values():
                if b.isVisible():
                    b.place()

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
