import os
import FreeCAD

def _bootstrap_toolbar_fix():
    try:
        from PySide6 import QtCore
    except ImportError:
        from PySide2 import QtCore

    def _fix():
        try:
            from PySide6 import QtWidgets, QtCore
        except ImportError:
            from PySide2 import QtWidgets, QtCore
        import FreeCADGui
        mw = FreeCADGui.getMainWindow()
        if not mw:
            return
        tb = mw.findChild(QtWidgets.QToolBar, "Workbench")
        if not tb:
            QtCore.QTimer.singleShot(500, _fix)
            return
        if tb.layout():
            tb.layout().setSpacing(0)
            tb.layout().setContentsMargins(0, 0, 0, 0)

    QtCore.QTimer.singleShot(2000, _fix)

def _bootstrap_global_task_watcher():
    try:
        from PySide6 import QtCore
    except ImportError:
        from PySide2 import QtCore

    def _setup():
        try:
            from PySide6 import QtWidgets, QtCore
        except ImportError:
            from PySide2 import QtWidgets, QtCore
        
        app = QtWidgets.QApplication.instance()
        if not app:
            QtCore.QTimer.singleShot(200, _setup)
            return

        if hasattr(app, "_colorPaletteTaskWatcher"):
            try:
                app.removeEventFilter(app._colorPaletteTaskWatcher)
            except Exception:
                pass

        class OptimizedTaskWatcher(QtCore.QObject):
            def __init__(self):
                try:
                    from PySide6 import QtCore
                except ImportError:
                    from PySide2 import QtCore
                super().__init__()
                self._debounce_timer = QtCore.QTimer()
                self._debounce_timer.setSingleShot(True)
                self._debounce_timer.setInterval(0)
                self._debounce_timer.timeout.connect(self.refresh_task_panels)

            def eventFilter(self, obj, event):
                try:
                    from PySide6 import QtWidgets, QtCore
                except ImportError:
                    from PySide2 import QtCore
                if event.type() in (QtCore.QEvent.Show, QtCore.QEvent.DynamicPropertyChange):
                    if isinstance(obj, QtWidgets.QFrame) and obj.property("class") == "panel":
                        self._debounce_timer.start()
                return False

            def refresh_task_panels(self):
                try:
                    from PySide6 import QtWidgets
                except ImportError:
                    from PySide2 import QtWidgets
                import FreeCADGui
                mw = FreeCADGui.getMainWindow()
                if not mw:
                    return
                tasks_dock = mw.findChild(QtWidgets.QDockWidget, "Tasks")
                if not tasks_dock or not tasks_dock.isVisible():
                    return
                
                panels = [w for w in tasks_dock.findChildren(QtWidgets.QFrame) if w.property("class") == "panel"]
                first = True
                for w in panels:
                    target_name = "taskPanelOuter" if first else "taskPanelInner"
                    first = False
                    if w.objectName() != target_name:
                        w.setObjectName(target_name)
                        w.style().unpolish(w)
                        w.style().polish(w)
                        w.update()

        watcher = OptimizedTaskWatcher()
        app.installEventFilter(watcher)
        app._colorPaletteTaskWatcher = watcher
        watcher.refresh_task_panels()

    QtCore.QTimer.singleShot(500, _setup)

# Importlib modülüyle dinamik olarak yüklendiğinde tetiklenecek blok
if __name__ == "__main__" or __name__ == "color_palette_general_fix":
    _bootstrap_toolbar_fix()
    _bootstrap_global_task_watcher()