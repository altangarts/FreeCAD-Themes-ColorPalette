import os
import FreeCAD
_mod_dir = os.path.join(FreeCAD.getUserAppDataDir(), "Mod", "Color-Palette-Theme")
try:
    import importlib.util
    _spec = importlib.util.spec_from_file_location(
        "color_palette_theme_sync",
        os.path.join(_mod_dir, "viewport_color_sync.py")
    )
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
except Exception:
    pass
try:
    try:
        from PySide6 import QtWidgets, QtCore
    except ImportError:
        from PySide2 import QtWidgets, QtCore
    _retry_count = [0]
    def _fix_workbench_toolbar(QtWidgets=QtWidgets, QtCore=QtCore):
        import FreeCADGui
        mw = FreeCADGui.getMainWindow()
        if not mw:
            return
        tb = mw.findChild(QtWidgets.QToolBar, "Workbench")
        if not tb:
            _retry_count[0] += 1
            if _retry_count[0] < 10:
                QtCore.QTimer.singleShot(500, _fix_workbench_toolbar)
            return
        if tb.layout():
            tb.layout().setSpacing(0)
            tb.layout().setContentsMargins(0, 0, 0, 0)
    QtCore.QTimer.singleShot(2000, _fix_workbench_toolbar)
except Exception:
    pass