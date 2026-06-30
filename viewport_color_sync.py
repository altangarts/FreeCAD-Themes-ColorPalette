import FreeCADGui

try:
    from PySide6 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui

def apply3DViewportColor():
    import re
    import FreeCAD

    mw = FreeCADGui.getMainWindow()
    if not mw:
        return

    mdi = mw.findChild(QtWidgets.QMdiArea)
    if not mdi:
        return

    app = QtWidgets.QApplication.instance()
    if not app:
        return

    def parseMainWindowStops(stylesheet):
        if not stylesheet:
            return None
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
        pos = max(0.0, min(1.0, pos))
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

    mw.__dict__["_last_dims_track"] = (0, 0, 0)

    def syncViewportColor():
        # --- GÜVENLİ DIALOG KONTROLÜ ---
        # Eğer şu an ekranda aktif/görünür bir QDialog (Tercihler vb.) varsa,
        # dış tıklamalardan kaynaklanan tüm sahte sinyalleri engellemek için hesaplamayı tamamen durdur.
        for top_level in app.topLevelWidgets():
            if isinstance(top_level, QtWidgets.QDialog) and top_level.isVisible():
                return

        if mw.isMinimized() or not mw.isVisible():
            return
            
        if not isGradientModeActive():
            return

        h = mw.height()
        if h <= 0:
            return

        active_sub = mdi.activeSubWindow()
        vp_h = 0
        if active_sub:
            vp = active_sub.widget() if active_sub.widget() else active_sub
            mdi_offset = mdi.mapTo(mw, QtCore.QPoint(0, 0)).y()
            top_y = mdi_offset + vp.y()
            bot_y = top_y + vp.height()
            vp_h = vp.height()
        else:
            start_view = mw.findChild(QtWidgets.QWidget, "StartView")
            if start_view and start_view.isVisible():
                top_y = start_view.mapTo(mw, QtCore.QPoint(0, 0)).y()
                bot_y = top_y + start_view.height()
                vp_h = start_view.height()
            else:
                mdi_pos = mdi.mapTo(mw, QtCore.QPoint(0, 0))
                top_y = mdi_pos.y()
                bot_y = top_y + mdi.height()
                vp_h = mdi.height()

        if (bot_y - top_y) <= 10 or top_y < 0 or bot_y > h:
            return

        current_dims = (h, top_y, vp_h)
        if current_dims == mw.__dict__.get("_last_dims_track"):
            return

        mid_y = top_y + (bot_y - top_y) * 0.5

        top_pos = max(0.0, min(1.0, top_y / h))
        bot_pos = max(0.0, min(1.0, bot_y / h))
        mid_pos = max(0.0, min(1.0, mid_y / h))

        if abs(top_pos - bot_pos) < 0.01:
            return

        mw.__dict__["_last_dims_track"] = current_dims

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

    class ViewportResizeFilter(QtCore.QObject):
        def eventFilter(self, obj, event):
            # Sadece gerçek boyut değişimlerinde tetiklenir
            if event.type() == QtCore.QEvent.Resize:
                syncViewportColor()
            return False

    old_timer = mw.__dict__.get("_viewport_color_timer")
    if old_timer:
        try: old_timer.stop()
        except Exception: pass
        mw.__dict__["_viewport_color_timer"] = None

    old_filter = mw.__dict__.get("_viewport_color_filter")
    if old_filter:
        try:
            mw.removeEventFilter(old_filter)
            mdi.removeEventFilter(old_filter)
            app.removeEventFilter(old_filter)
            sv = mw.findChild(QtWidgets.QWidget, "StartView")
            if sv: sv.removeEventFilter(old_filter)
        except Exception: pass

    ef = ViewportResizeFilter(mw)
    mw.installEventFilter(ef)
    mdi.installEventFilter(ef)
    
    mdi.subWindowActivated.connect(lambda _: syncViewportColor())
    
    # Dialog kapandığında veya odağa dönüldüğünde arayüzü tazelemek için evrensel tetikleyici
    app.installEventFilter(ef) 
    
    start_view = mw.findChild(QtWidgets.QWidget, "StartView")
    if start_view:
        start_view.installEventFilter(ef)
        
    mw.__dict__["_viewport_color_filter"] = ef
    syncViewportColor()


def lockColorPreferences():
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

    def setColorWidgets(dialog, enabled):
        if not dialog:
            return
        for name in COLOR_WIDGET_NAMES:
            w = dialog.findChild(QtWidgets.QWidget, name)
            if w:
                w.setEnabled(enabled)

    def setSwapButton(dialog, enabled):
        if not dialog:
            return
        btn = dialog.findChild(QtWidgets.QWidget, "SwitchGradientColors")
        if btn:
            btn.setEnabled(enabled)

    def applyLock():
        dialog = None
        for top_level in QtWidgets.QApplication.topLevelWidgets():
            if isinstance(top_level, QtWidgets.QDialog) and top_level.isVisible():
                dialog = top_level
                break
        
        if not dialog:
            return

        radial_btn = dialog.findChild(QtWidgets.QRadioButton, "rbRadialGradient")
        simple_btn = dialog.findChild(QtWidgets.QRadioButton, "radioButtonSimple")
        linear_btn = dialog.findChild(QtWidgets.QRadioButton, "radioButtonGradient")

        gradient_active = linear_btn is not None and linear_btn.isChecked()
        setColorWidgets(dialog, not gradient_active)
        setSwapButton(dialog, not gradient_active)

        _connectRadioSignals(dialog, radial_btn, simple_btn, linear_btn)

    def _connectRadioSignals(dialog, radial_btn, simple_btn, linear_btn):
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
                setColorWidgets(dialog, False)
                setSwapButton(dialog, False)
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
                setColorWidgets(dialog, True)
                setSwapButton(dialog, True)

        def onSimpleToggled(checked):
            if checked:
                try:
                    p = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/View")
                    p.SetBool("Simple", True)
                    p.SetBool("Gradient", False)
                    p.SetBool("RadialGradient", False)
                except Exception:
                    pass
                setColorWidgets(dialog, True)
                setSwapButton(dialog, True)

        if linear_btn is not None and not linear_btn.property("locked_connected"):
            linear_btn.toggled.connect(onGradientToggled)
            linear_btn.setProperty("locked_connected", True)

        if radial_btn is not None and not radial_btn.property("locked_connected"):
            radial_btn.toggled.connect(onRadialToggled)
            radial_btn.setProperty("locked_connected", True)

        if simple_btn is not None and not simple_btn.property("locked_connected"):
            simple_btn.toggled.connect(onSimpleToggled)
            simple_btn.setProperty("locked_connected", True)

    class PreferencesDialogWatcher(QtCore.QObject):
        def eventFilter(self, obj, event):
            # Dialog kapandığında (Hide / Destroy) arka planı otomatik olarak bir kez tetikle
            if event.type() in (QtCore.QEvent.Show, QtCore.QEvent.Hide) and isinstance(obj, QtWidgets.QDialog):
                QtCore.QTimer.singleShot(30, applyLock)
                QtCore.QTimer.singleShot(150, applyLock)
                if event.type() == QtCore.QEvent.Hide:
                    sync_fn = mw.__dict__.get("_sync_viewport_color_fn")
                    if sync_fn: QtCore.QTimer.singleShot(50, sync_fn)
            return False

    old_watcher = mw.__dict__.get("_pref_dialog_watcher")
    if old_watcher:
        try:
            app.removeEventFilter(old_watcher)
        except Exception:
            pass

    watcher = PreferencesDialogWatcher(app)
    app.installEventFilter(watcher)
    mw.__dict__["_pref_dialog_watcher"] = watcher


mw = FreeCADGui.getMainWindow()
if mw:
    mw.__dict__["_apply_viewport_color"] = apply3DViewportColor
    mw.__dict__["_lock_color_preferences"] = lockColorPreferences
    QtCore.QTimer.singleShot(1500, apply3DViewportColor)
    QtCore.QTimer.singleShot(1500, lockColorPreferences)