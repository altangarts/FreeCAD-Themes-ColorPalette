import FreeCADGui
import FreeCAD

def apply3DViewportColor():
    try:
        from PySide6 import QtWidgets, QtCore, QtGui
    except ImportError:
        from PySide2 import QtWidgets, QtCore, QtGui
    import re

    mw = FreeCADGui.getMainWindow()
    if not mw:
        return

    mdi = mw.findChild(QtWidgets.QMdiArea)
    app = QtWidgets.QApplication.instance()
    if not mdi or not app:
        return

    _style_cache = {"stylesheet": None, "stops": None}

    def parseMainWindowStops():
        ss = app.styleSheet()
        if _style_cache["stylesheet"] == ss:
            return _style_cache["stops"]
        
        _style_cache["stylesheet"] = ss
        if not ss:
            return None
            
        mw_match = re.search(r'QMainWindow\s*\{[^}]*background-color\s*:\s*([^;]+);', ss)
        if not mw_match:
            return None
            
        stops = re.findall(r'stop\s*:\s*([\d.]+)\s+(#[0-9a-fA-F]{3,8})', mw_match.group(1))
        unique = []
        seen = set()
        for pos, color in stops:
            p_val = float(pos)
            if p_val not in seen:
                seen.add(p_val)
                unique.append((p_val, QtGui.QColor(color)))
        
        unique.sort(key=lambda x: x[0])
        _style_cache["stops"] = unique
        return unique

    def interpolateColor(stops, pos):
        pos = max(0.0, min(1.0, pos))
        if pos <= stops[0][0]: return stops[0][1]
        if pos >= stops[-1][0]: return stops[-1][1]
        for i in range(len(stops) - 1):
            p0, c0 = stops[i]
            p1, c1 = stops[i + 1]
            if p0 <= pos <= p1:
                t = (pos - p0) / (p1 - p0) if p1 > p0 else 0
                return QtGui.QColor(
                    int(c0.red() + t * (c1.red() - c0.red())),
                    int(c0.green() + t * (c1.green() - c0.green())),
                    int(c0.blue() + t * (c1.blue() - c0.blue()))
                )
        return stops[-1][1]

    def syncViewportColor():
        for top_level in app.topLevelWidgets():
            if isinstance(top_level, QtWidgets.QDialog) and top_level.isVisible():
                return

        if mw.isMinimized() or not mw.isVisible():
            return

        try:
            p = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/View")
            if p.GetBool("Simple", False) or p.GetBool("RadialGradient", False) or not p.GetBool("Gradient", True):
                return
        except Exception:
            return

        h = mw.height()
        if h <= 0:
            return

        active_sub = mdi.activeSubWindow()
        if active_sub and active_sub.widget():
            vp = active_sub.widget()
            top_y = mdi.mapTo(mw, QtCore.QPoint(0, 0)).y() + vp.y()
            vp_h = vp.height()
        else:
            sv = mw.findChild(QtWidgets.QWidget, "StartView")
            if sv and sv.isVisible():
                top_y = sv.mapTo(mw, QtCore.QPoint(0, 0)).y()
                vp_h = sv.height()
            else:
                top_y = mdi.mapTo(mw, QtCore.QPoint(0, 0)).y()
                vp_h = mdi.height()

        bot_y = top_y + vp_h
        if vp_h <= 10 or top_y < 0 or bot_y > h:
            return

        current_dims = (h, top_y, vp_h)
        if current_dims == mw.__dict__.get("_last_dims_track"):
            return

        base_stops = parseMainWindowStops()
        if not base_stops or len(base_stops) < 2:
            return

        mw.__dict__["_last_dims_track"] = current_dims

        mid_y = top_y + vp_h * 0.5
        c_top = interpolateColor(base_stops, top_pos := max(0.0, min(1.0, top_y / h)))
        c_mid = interpolateColor(base_stops, mid_pos := max(0.0, min(1.0, mid_y / h)))
        c_bot = interpolateColor(base_stops, bot_pos := max(0.0, min(1.0, bot_y / h)))

        if abs(top_pos - bot_pos) < 0.01:
            return

        def to_fc(c):
            return (c.red() << 24) | (c.green() << 16) | (c.blue() << 8) | 0xFF

        p.SetBool("Simple", False)
        p.SetBool("Gradient", True)
        p.SetBool("RadialGradient", False)
        p.SetUnsigned("BackgroundColor2", to_fc(c_top))
        p.SetUnsigned("BackgroundColor4", to_fc(c_mid))
        p.SetUnsigned("BackgroundColor3", to_fc(c_bot))
        FreeCADGui.updateGui()

    mw.__dict__["_sync_viewport_color_fn"] = syncViewportColor

    class ViewportResizeFilter(QtCore.QObject):
        def eventFilter(self, obj, event):
            if event.type() == QtCore.QEvent.Resize:
                syncViewportColor()
            return False

    for k in ("_viewport_color_timer", "_viewport_color_filter"):
        if old := mw.__dict__.get(k):
            try:
                if k == "_viewport_color_timer": old.stop()
                else:
                    mw.removeEventFilter(old)
                    mdi.removeEventFilter(old)
            except Exception: pass
            mw.__dict__[k] = None

    ef = ViewportResizeFilter(mw)
    mw.installEventFilter(ef)
    mdi.installEventFilter(ef)
    mdi.subWindowActivated.connect(lambda _: syncViewportColor())
    
    sv = mw.findChild(QtWidgets.QWidget, "StartView")
    if sv:
        sv.installEventFilter(ef)
        
    mw.__dict__["_viewport_color_filter"] = ef
    syncViewportColor()

def lockColorPreferences():
    try:
        from PySide6 import QtWidgets, QtCore
    except ImportError:
        from PySide2 import QtWidgets, QtCore

    mw = FreeCADGui.getMainWindow()
    app = QtWidgets.QApplication.instance()
    if not mw or not app:
        return

    widgets_to_lock = ("backgroundColorFrom", "backgroundColorTo", "backgroundColorMid", "checkMidColor", "SwitchGradientColors")

    def applyLock():
        dialog = next((w for w in app.topLevelWidgets() if isinstance(w, QtWidgets.QDialog) and w.isVisible()), None)
        if not dialog:
            return

        linear_btn = dialog.findChild(QtWidgets.QRadioButton, "radioButtonGradient")
        gradient_active = linear_btn is not None and linear_btn.isChecked()

        for name in widgets_to_lock:
            w = dialog.findChild(QtWidgets.QWidget, name)
            if w:
                w.setEnabled(not gradient_active)

        if linear_btn and not linear_btn.property("locked_connected"):
            sync_fn = mw.__dict__.get("_sync_viewport_color_fn")
            
            def make_toggle_handler(s, g, r):
                def handler(checked):
                    if not checked: return
                    try:
                        p = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/View")
                        p.SetBool("Simple", s)
                        p.SetBool("Gradient", g)
                        p.SetBool("RadialGradient", r)
                    except Exception: pass
                    for n in widgets_to_lock:
                        w = dialog.findChild(QtWidgets.QWidget, n)
                        if w: w.setEnabled(not g)
                    if g and sync_fn: sync_fn()
                return handler

            rb_radial = dialog.findChild(QtWidgets.QRadioButton, "rbRadialGradient")
            rb_simple = dialog.findChild(QtWidgets.QRadioButton, "radioButtonSimple")

            linear_btn.toggled.connect(make_toggle_handler(False, True, False))
            if rb_radial: rb_radial.toggled.connect(make_toggle_handler(False, False, True))
            if rb_simple: rb_simple.toggled.connect(make_toggle_handler(True, False, False))
            linear_btn.setProperty("locked_connected", True)

    class PreferencesDialogWatcher(QtCore.QObject):
        def eventFilter(self, obj, event):
            if isinstance(obj, QtWidgets.QDialog) and event.type() in (QtCore.QEvent.Show, QtCore.QEvent.Hide):
                QtCore.QTimer.singleShot(30, applyLock)
                QtCore.QTimer.singleShot(150, applyLock)
                if event.type() == QtCore.QEvent.Hide:
                    sync_fn = mw.__dict__.get("_sync_viewport_color_fn")
                    if sync_fn: QtCore.QTimer.singleShot(50, sync_fn)
            return False

    if old_watcher := mw.__dict__.get("_pref_dialog_watcher"):
        try: app.removeEventFilter(old_watcher)
        except Exception: pass

    watcher = PreferencesDialogWatcher(app)
    app.installEventFilter(watcher)
    mw.__dict__["_pref_dialog_watcher"] = watcher

mw = FreeCADGui.getMainWindow()
if mw:
    try:
        from PySide6 import QtCore
    except ImportError:
        from PySide2 import QtCore
    mw.__dict__["_apply_viewport_color"] = apply3DViewportColor
    mw.__dict__["_lock_color_preferences"] = lockColorPreferences
    QtCore.QTimer.singleShot(1500, apply3DViewportColor)
    QtCore.QTimer.singleShot(1500, lockColorPreferences)