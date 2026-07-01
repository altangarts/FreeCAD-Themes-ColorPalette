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
                    from PySide2 import QtWidgets, QtCore
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

def _bootstrap_property_editor_anchoring():
    try:
        from PySide6 import QtCore
    except ImportError:
        from PySide2 import QtCore

    def _setup():
        try:
            from PySide6 import QtWidgets, QtCore
        except ImportError:
            from PySide2 import QtWidgets, QtCore
            
        import FreeCADGui
        mw = FreeCADGui.getMainWindow()
        if not mw:
            QtCore.QTimer.singleShot(500, _setup)
            return

        tab = mw.findChild(QtWidgets.QTabWidget, "propertyTab")
        container = tab.parent() if tab else None
        if not tab or not container:
            QtCore.QTimer.singleShot(1000, _setup)
            return

        if container.property("_bottomAnchorInstalled"):
            return

        container.setProperty("_bottomAnchorInstalled", True)
        trees = [t for t in [mw.findChild(QtWidgets.QTreeView, "propertyEditorView"),
                             mw.findChild(QtWidgets.QTreeView, "propertyEditorData")] if t]
        original_layout = container.layout()
        
        def _find_dock_widget(widget):
            try:
                from PySide6 import QtWidgets
            except ImportError:
                from PySide2 import QtWidgets
            p = widget.parent()
            while p:
                if isinstance(p, QtWidgets.QDockWidget) or p.inherits("QDockWidget") or p.inherits("Gui::DockWnd::DockWindow"):
                    return p
                p = p.parent()
            return None

        def _is_strictly_overlay(dock_widget):
            try:
                from PySide6 import QtCore
            except ImportError:
                from PySide2 import QtCore
            if not dock_widget or dock_widget.isWindow() or dock_widget.window() == dock_widget:
                return False
            mw_win = dock_widget.window()
            if mw_win and hasattr(mw_win, "dockWidgetArea"):
                area = mw_win.dockWidgetArea(dock_widget)
                no_area = getattr(QtCore.Qt.DockWidgetArea, "NoDockWidgetArea", None) if hasattr(QtCore.Qt, "DockWidgetArea") else QtCore.Qt.NoDockWidgetArea
                if area != no_area:
                    return False
            return True

        def _tree_height(tree, model, parent):
            h = 0
            for i in range(model.rowCount(parent)):
                idx = model.index(i, 0, parent)
                h += tree.rowHeight(idx)
                if tree.isExpanded(idx):
                    h += _tree_height(tree, model, idx)
            return h

        def _content_height():
            total = 0
            for tree in trees:
                if not tree or not tree.isVisible():
                    continue
                model = tree.model()
                if model:
                    total = max(total, _tree_height(tree, model, QtCore.QModelIndex()))
            return total

        dock_widget = _find_dock_widget(container)
        state = {"anchoring": False, "in_overlay": False}
        splitter = container.parent() if isinstance(container.parent(), QtWidgets.QSplitter) else None
        splitter_idx = splitter.indexOf(container) if splitter else -1
        original_splitter_sizes = list(splitter.sizes()) if splitter else None
        original_handle_width = splitter.handleWidth() if splitter else None
        splitter_handle = splitter.handle(splitter_idx) if (splitter and splitter_idx > 0) else None

        def layout_tab_widget():
            try:
                from PySide6 import QtWidgets, QtCore
            except ImportError:
                from PySide2 import QtWidgets, QtCore
            if state["anchoring"]:
                return
            if not _is_strictly_overlay(dock_widget):
                if original_layout and original_layout.indexOf(tab) == -1:
                    original_layout.addWidget(tab)
                if state["in_overlay"]:
                    if splitter and splitter_idx != -1 and original_splitter_sizes:
                        state["anchoring"] = True
                        try:
                            splitter.setSizes(original_splitter_sizes)
                            if original_handle_width is not None:
                                splitter.setHandleWidth(original_handle_width)
                            if splitter_handle is not None:
                                splitter_handle.setEnabled(True)
                        finally:
                            state["anchoring"] = False
                    state["in_overlay"] = False
                return

            state["in_overlay"] = True
            if original_layout and original_layout.indexOf(tab) != -1:
                original_layout.removeWidget(tab)
            if splitter:
                splitter.setHandleWidth(0)
            if splitter_handle:
                splitter_handle.setEnabled(False)

            tab_bar_h = tab.tabBar().sizeHint().height() if tab.tabBar().isVisible() else 0
            desired_h = tab_bar_h + _content_height()
            
            state["anchoring"] = True
            try:
                if splitter and splitter_idx != -1:
                    total = sum(splitter.sizes())
                    target_h = max(min(desired_h, total), 10)
                    sizes = splitter.sizes()
                    if sizes[splitter_idx] != target_h:
                        new_sizes = list(sizes)
                        new_sizes[splitter_idx] = target_h
                        remainder = total - target_h
                        other_indices = [i for i in range(len(sizes)) if i != splitter_idx]
                        other_total_cur = sum(sizes[i] for i in other_indices) or 1
                        consumed = 0
                        for n, idx in enumerate(other_indices):
                            if n == len(other_indices) - 1:
                                new_sizes[idx] = max(remainder - consumed, 0)
                            else:
                                share = max(int(round(remainder * (sizes[idx] / other_total_cur))), 0)
                                new_sizes[idx] = share
                                consumed += share
                        splitter.setSizes(new_sizes)
                else:
                    target_h = max(min(desired_h, container.rect().height()), 10)

                full_rect = container.rect()
                target_y = int(round(max(full_rect.height() - target_h, 0)))
                target_w = full_rect.width()
                cur = tab.geometry()
                if not (cur.x() == 0 and cur.y() == target_y and cur.width() == target_w and cur.height() == int(round(target_h))):
                    tab.setGeometry(0, target_y, target_w, int(round(target_h)))
            finally:
                state["anchoring"] = False

        class AnchorFilter(QtCore.QObject):
            def eventFilter(self, obj, event):
                try:
                    from PySide6 import QtCore
                except ImportError:
                    from PySide2 import QtCore
                if obj is container and event.type() == QtCore.QEvent.Resize:
                    layout_tab_widget()
                return False

        filt = AnchorFilter(container)
        container.installEventFilter(filt)
        container._bottomAnchorFilter = filt

        for tree in trees:
            model = tree.model()
            if model:
                model.rowsInserted.connect(lambda *a: layout_tab_widget())
                model.rowsRemoved.connect(lambda *a: layout_tab_widget())
                model.modelReset.connect(lambda *a: layout_tab_widget())
            tree.expanded.connect(lambda *a: layout_tab_widget())
            tree.collapsed.connect(lambda *a: layout_tab_widget())

        tab.currentChanged.connect(lambda *a: layout_tab_widget())
        layout_tab_widget()
        container.update()

    QtCore.QTimer.singleShot(2000, _setup)

if __name__ == "__main__" or __name__ == "InitGui":
    _bootstrap_toolbar_fix()
    _bootstrap_global_task_watcher()
    _bootstrap_property_editor_anchoring()