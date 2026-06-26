import FreeCADGui


def apply3DViewportColor():
    import PySide6.QtWidgets as QtWidgets
    import PySide6.QtGui as QtGui
    import PySide6.QtCore as QtCore
    import re
    import FreeCAD

    mw = FreeCADGui.getMainWindow()
    if not mw:
        return

    mdi = mw.findChild(QtWidgets.QMdiArea)
    if not mdi:
        return

    app = QtWidgets.QApplication.instance()

    def parseMainWindowStops(stylesheet):
        mw_match = re.search(
            r'QMainWindow\s*\{[^}]*background-color\s*:\s*([^;]+);', stylesheet
        )
        if not mw_match:
            return None
        val = mw_match.group(1).strip()
        stops = re.findall(r'stop\s*:\s*([\d.]+)\s+(#[0-9a-fA-F]{3,8})', val)
        result = [(float(pos), QtGui.QColor(color)) for pos, color in stops]
        seen = set()
        unique = []
        for pos, color in result:
            if pos not in seen:
                seen.add(pos)
                unique.append((pos, color))
        return unique

    def interpolateColor(stops, pos):
        if pos <= stops[0][0]:
            return stops[0][1]
        if pos >= stops[-1][0]:
            return stops[-1][1]
        for i in range(len(stops) - 1):
            p0, c0 = stops[i]
            p1, c1 = stops[i + 1]
            if p0 <= pos <= p1:
                t = (pos - p0) / (p1 - p0) if p1 > p0 else 0
                r = int(c0.red()   + t * (c1.red()   - c0.red()))
                g = int(c0.green() + t * (c1.green() - c0.green()))
                b = int(c0.blue()  + t * (c1.blue()  - c0.blue()))
                return QtGui.QColor(r, g, b)
        return stops[-1][1]

    def colorToFreeCAD(color):
        return (color.red() << 24) | (color.green() << 16) | (color.blue() << 8) | 0xFF

    base_stops = parseMainWindowStops(app.styleSheet())
    if not base_stops or len(base_stops) < 2:
        return

    def isGradientModeActive():
        try:
            p = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/View")
            is_simple   = p.GetBool("Simple", False)
            is_radial   = p.GetBool("RadialGradient", False)
            is_gradient = p.GetBool("Gradient", True)
            if is_simple or is_radial:
                return False
            return is_gradient
        except Exception:
            return False

    def syncViewportColor():
        if not isGradientModeActive():
            return

        h = mw.height()
        if h == 0:
            return

        active_sub = mdi.activeSubWindow()
        if active_sub:
            vp = active_sub.widget() if active_sub.widget() else active_sub
            gp_top = vp.mapToGlobal(QtCore.QPoint(0, 0))
            gp_bot = vp.mapToGlobal(QtCore.QPoint(0, vp.height()))
            top_y = mw.mapFromGlobal(gp_top).y()
            bot_y = mw.mapFromGlobal(gp_bot).y()
        else:
            mdi_pos = mdi.mapTo(mw, QtCore.QPoint(0, 0))
            top_y = mdi_pos.y()
            bot_y = top_y + mdi.height()

        mid_y = top_y + (bot_y - top_y) * 0.5

        top_pos = max(0.0, min(1.0, top_y / h))
        bot_pos = max(0.0, min(1.0, bot_y / h))
        mid_pos = max(0.0, min(1.0, mid_y / h))

        c_top = interpolateColor(base_stops, top_pos)
        c_mid = interpolateColor(base_stops, mid_pos)
        c_bot = interpolateColor(base_stops, bot_pos)

        p = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/View")
        p.SetBool("Simple", False)
        p.SetBool("Gradient", True)
        p.SetBool("RadialGradient", False)
        p.SetUnsigned("BackgroundColor2", colorToFreeCAD(c_top))
        p.SetUnsigned("BackgroundColor4", colorToFreeCAD(c_mid))
        p.SetUnsigned("BackgroundColor3", colorToFreeCAD(c_bot))
        FreeCADGui.updateGui()

    mw.__dict__["_sync_viewport_color_fn"] = syncViewportColor

    class ViewportEventFilter(QtCore.QObject):
        def __init__(self, mw):
            super().__init__(mw)
            self._timer = QtCore.QTimer(self)
            self._timer.setSingleShot(True)
            self._timer.setInterval(0)
            self._timer.timeout.connect(syncViewportColor)

        def eventFilter(self, obj, event):
            if event.type() in (
                QtCore.QEvent.Resize,
                QtCore.QEvent.Move,
            ):
                self._timer.start()
            return False

    old_filter = mw.__dict__.get("_viewport_color_filter")
    if old_filter:
        mw.removeEventFilter(old_filter)
        mdi.removeEventFilter(old_filter)

    ef = ViewportEventFilter(mw)
    mw.installEventFilter(ef)
    mdi.installEventFilter(ef)
    mdi.subWindowActivated.connect(lambda _: syncViewportColor())
    mw.__dict__["_viewport_color_filter"] = ef

    syncViewportColor()


def lockColorPreferences():
    import PySide6.QtWidgets as QtWidgets
    import PySide6.QtCore as QtCore
    import FreeCAD

    mw = FreeCADGui.getMainWindow()
    if not mw:
        return

    app = QtWidgets.QApplication.instance()
    if not app:
        return

    COLOR_WIDGET_NAMES = (
        "backgroundColorFrom",
        "backgroundColorTo",
        "backgroundColorMid",
        "checkMidColor",
    )

    _connected_buttons = mw.__dict__.setdefault("_radio_btn_connected", set())

    def findSwapButton():
        for w in app.allWidgets():
            if w.objectName() == "SwitchGradientColors":
                return w
        return None

    def setColorWidgets(enabled):
        for w in app.allWidgets():
            if w.objectName() in COLOR_WIDGET_NAMES:
                w.setEnabled(enabled)

    def setSwapButton(enabled):
        btn = findSwapButton()
        if btn is not None:
            btn.setEnabled(enabled)

    def applyLock():
        radial_btn = None
        simple_btn = None
        linear_btn = None

        for w in app.allWidgets():
            name = w.objectName()
            if name == "rbRadialGradient":
                radial_btn = w
            elif name == "radioButtonSimple":
                simple_btn = w
            elif name == "radioButtonGradient":
                linear_btn = w

        gradient_active = linear_btn is not None and linear_btn.isChecked()
        setColorWidgets(not gradient_active)
        setSwapButton(not gradient_active)

        _connectRadioSignals(radial_btn, simple_btn, linear_btn)

    def _connectRadioSignals(radial_btn, simple_btn, linear_btn):
        sync_fn = mw.__dict__.get("_sync_viewport_color_fn")
        if sync_fn is None:
            return

        def onGradientToggled(checked):
            if checked:
                try:
                    p = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/View")
                    p.SetBool("Simple", False)
                    p.SetBool("Gradient", True)
                    p.SetBool("RadialGradient", False)
                except Exception:
                    pass
                setColorWidgets(False)
                setSwapButton(False)
                sync_fn()

        def onRadialToggled(checked):
            if checked:
                try:
                    p = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/View")
                    p.SetBool("Simple", False)
                    p.SetBool("Gradient", False)
                    p.SetBool("RadialGradient", True)
                except Exception:
                    pass
                setColorWidgets(True)
                setSwapButton(True)

        def onSimpleToggled(checked):
            if checked:
                try:
                    p = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/View")
                    p.SetBool("Simple", True)
                    p.SetBool("Gradient", False)
                    p.SetBool("RadialGradient", False)
                except Exception:
                    pass
                setColorWidgets(True)
                setSwapButton(True)

        if linear_btn is not None:
            btn_id = id(linear_btn)
            if btn_id not in _connected_buttons:
                linear_btn.toggled.connect(onGradientToggled)
                _connected_buttons.add(btn_id)

        if radial_btn is not None:
            btn_id = id(radial_btn)
            if btn_id not in _connected_buttons:
                radial_btn.toggled.connect(onRadialToggled)
                _connected_buttons.add(btn_id)

        if simple_btn is not None:
            btn_id = id(simple_btn)
            if btn_id not in _connected_buttons:
                simple_btn.toggled.connect(onSimpleToggled)
                _connected_buttons.add(btn_id)

    class PreferencesDialogWatcher(QtCore.QObject):
        def eventFilter(self, obj, event):
            if event.type() == QtCore.QEvent.Show and isinstance(obj, QtWidgets.QDialog):
                QtCore.QTimer.singleShot(0, applyLock)
                QtCore.QTimer.singleShot(200, applyLock)
            return False

    old_watcher = mw.__dict__.get("_pref_dialog_watcher")
    if old_watcher:
        app.removeEventFilter(old_watcher)

    watcher = PreferencesDialogWatcher(app)
    app.installEventFilter(watcher)
    mw.__dict__["_pref_dialog_watcher"] = watcher


mw = FreeCADGui.getMainWindow()
if mw:
    mw.__dict__["_apply_viewport_color"] = apply3DViewportColor
    mw.__dict__["_lock_color_preferences"] = lockColorPreferences
    import PySide6.QtCore as QtCore
    QtCore.QTimer.singleShot(1500, apply3DViewportColor)
    QtCore.QTimer.singleShot(1500, lockColorPreferences)
