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

    def syncViewportColor():
        h = mw.height()
        if h == 0:
            return

        mdi_pos = mdi.mapTo(mw, QtCore.QPoint(0, 0))
        top_y = mdi_pos.y()
        bot_y = top_y + mdi.height()

        top_pos = max(0.0, min(1.0, top_y / h))
        bot_pos = max(0.0, min(1.0, bot_y / h))

        raw_mid = top_pos + (bot_pos - top_pos) * 0.5
        mid_pos = max(top_pos, min(bot_pos, raw_mid + 0.0532))

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
    mw.__dict__["_viewport_color_filter"] = ef

    syncViewportColor()


def lockColorPreferences():
    import PySide6.QtWidgets as QtWidgets
    import PySide6.QtCore as QtCore

    mw = FreeCADGui.getMainWindow()
    if not mw:
        return

    app = QtWidgets.QApplication.instance()
    if not app:
        return

    LOCKED_WIDGET_NAMES = (
        "backgroundColorFrom",
        "backgroundColorTo",
        "backgroundColorMid",
        "checkMidColor",
    )

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
            elif name in LOCKED_WIDGET_NAMES:
                if w.isEnabled():
                    w.setEnabled(False)

        if (radial_btn is not None or simple_btn is not None) and linear_btn is not None:
            was_radial_or_simple = (radial_btn is not None and radial_btn.isChecked()) or \
                                    (simple_btn is not None and simple_btn.isChecked())
            if was_radial_or_simple:
                linear_btn.setChecked(True)

        if radial_btn is not None:
            radial_btn.setChecked(False)
            radial_btn.setEnabled(False)

        if simple_btn is not None:
            simple_btn.setChecked(False)
            simple_btn.setEnabled(False)

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