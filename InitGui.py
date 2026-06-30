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

try:
    try:
        from PySide6 import QtWidgets, QtCore
    except ImportError:
        from PySide2 import QtWidgets, QtCore

    def _fix_task_panels(QtWidgets=QtWidgets, QtCore=QtCore):
        import FreeCADGui
        mw = FreeCADGui.getMainWindow()
        if not mw:
            return
        tasks_dock = mw.findChild(QtWidgets.QDockWidget, "Tasks")
        if not tasks_dock:
            return

        def refresh_panels():
            panels = tasks_dock.findChildren(QtWidgets.QFrame)
            first = True
            for w in panels:
                if w.property("class") == "panel":
                    if first:
                        w.setObjectName("taskPanelOuter")
                        first = False
                    else:
                        w.setObjectName("taskPanelInner")
                    w.style().unpolish(w)
                    w.style().polish(w)
                    w.update()

        class _PanelWatcher(QtCore.QObject):
            def eventFilter(self, obj, event):
                if event.type() == QtCore.QEvent.ChildAdded:
                    QtCore.QTimer.singleShot(50, refresh_panels)
                return False

        watcher = _PanelWatcher(tasks_dock)
        tasks_dock.installEventFilter(watcher)
        refresh_panels()

    QtCore.QTimer.singleShot(3000, _fix_task_panels)
except Exception:
    pass

try:
    try:
        from PySide6 import QtWidgets, QtCore
    except ImportError:
        from PySide2 import QtWidgets, QtCore

    def _make_property_editor_anchor_setup(QtWidgets=QtWidgets, QtCore=QtCore):
        # Kendine referansı global isim yerine closure üzerinden tutuyoruz;
        # InitGui.py bir metod içinde exec() edilebildiğinden global isim
        # aramasıyla kendi adını bulamayabilir (NameError riski).
        _self_ref = []

        MIN_HEIGHT = 10
        TOP_PADDING = 0
        BOTTOM_PADDING = 0

        def _find_dock_widget(widget):
            p = widget.parent()
            while p:
                if isinstance(p, QtWidgets.QDockWidget) or p.inherits("QDockWidget") or p.inherits("Gui::DockWnd::DockWindow"):
                    return p
                p = p.parent()
            return None

        def _is_strictly_overlay(dock_widget):
            if not dock_widget:
                return False
            if dock_widget.isWindow() or dock_widget.window() == dock_widget:
                return False
            mw = dock_widget.window()
            if mw and hasattr(mw, "dockWidgetArea"):
                area = mw.dockWidgetArea(dock_widget)
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

        def _content_height(trees):
            total = 0
            for tree in trees:
                if not tree or not tree.isVisible():
                    continue
                model = tree.model()
                if not model:
                    continue
                total = max(total, _tree_height(tree, model, QtCore.QModelIndex()))
            return total

        def _setup_property_editor_anchoring():
            """Overlay modunda property editörünü (propertyTab) ebeveyninin
            QGridLayout'undan çıkarıp manuel setGeometry ile alta sabitler;
            ağaç görünümünü ayıran QSplitter'ı da içerik yüksekliğine göre
            taşıyarak ayracın editör doluyken içeriğin hemen üstünde, editör
            boşken en altta (tab bar'ın üstünde) durmasını sağlar."""
            import FreeCADGui
            mw = FreeCADGui.getMainWindow()
            if not mw:
                QtCore.QTimer.singleShot(500, _self_ref[0])
                return

            tab = mw.findChild(QtWidgets.QTabWidget, "propertyTab")
            container = tab.parent() if tab else None
            if not tab or not container:
                QtCore.QTimer.singleShot(1000, _self_ref[0])
                return

            if not container.property("_bottomAnchorInstalled"):
                container.setProperty("_bottomAnchorInstalled", True)

                trees = [
                    t for t in [
                        mw.findChild(QtWidgets.QTreeView, "propertyEditorView"),
                        mw.findChild(QtWidgets.QTreeView, "propertyEditorData"),
                    ] if t
                ]
                original_layout = container.layout()
                dock_widget = _find_dock_widget(container)
                state = {"anchoring": False, "in_overlay": False}

                # Ağaç görünümü + property görünümünü ayıran QSplitter'ı bul
                splitter = container.parent()
                if not isinstance(splitter, QtWidgets.QSplitter):
                    splitter = None
                splitter_idx = splitter.indexOf(container) if splitter else -1
                original_splitter_sizes = list(splitter.sizes()) if splitter else None
                original_handle_width = splitter.handleWidth() if splitter else None
                splitter_handle = splitter.handle(splitter_idx) if (splitter and splitter_idx > 0) else None

                def _resize_splitter_pane(target_h):
                    sizes = splitter.sizes()
                    if sizes[splitter_idx] == target_h:
                        return
                    total = sum(sizes)
                    other_indices = [i for i in range(len(sizes)) if i != splitter_idx]
                    other_total_cur = sum(sizes[i] for i in other_indices) or 1
                    remainder = total - target_h
                    new_sizes = list(sizes)
                    new_sizes[splitter_idx] = target_h
                    consumed = 0
                    for n, i in enumerate(other_indices):
                        if n == len(other_indices) - 1:
                            new_sizes[i] = max(remainder - consumed, 0)
                        else:
                            share = max(int(round(remainder * (sizes[i] / other_total_cur))), 0)
                            new_sizes[i] = share
                            consumed += share
                    splitter.setSizes(new_sizes)

                def layout_tab_widget():
                    if state["anchoring"]:
                        return

                    if not _is_strictly_overlay(dock_widget):
                        if original_layout and original_layout.indexOf(tab) == -1:
                            original_layout.addWidget(tab)
                        if state["in_overlay"]:
                            # Sadece overlay'den dock'a GEÇİŞ anında, bir kez eski
                            # haline döndür. Aksi halde kullanıcı docked modda
                            # ayracı her sürüklediğinde de bu tetiklenip onu sürekli
                            # eski konumuna geri iter, ayraç hiç hareket etmiyormuş
                            # gibi görünür.
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

                    # Boyutlandırmayı tamamen biz yönettiğimiz için kullanıcının
                    # elle sürükleyebileceği ayraca artık gerek yok; gizle.
                    if splitter is not None:
                        splitter.setHandleWidth(0)
                    if splitter_handle is not None:
                        splitter_handle.setEnabled(False)

                    tab_bar_h = tab.tabBar().sizeHint().height() if tab.tabBar().isVisible() else 0
                    desired_h = tab_bar_h + _content_height(trees) + TOP_PADDING + BOTTOM_PADDING

                    state["anchoring"] = True
                    try:
                        if splitter and splitter_idx != -1:
                            total = sum(splitter.sizes())
                            target_h = max(min(desired_h, total), MIN_HEIGHT)
                            _resize_splitter_pane(target_h)
                        else:
                            target_h = max(min(desired_h, container.rect().height()), MIN_HEIGHT)

                        full_rect = container.rect()
                        target_y = max(full_rect.height() - target_h, 0)
                        target_w = full_rect.width()
                        target_y = int(round(target_y))
                        target_h = int(round(target_h))

                        cur = tab.geometry()
                        if not (cur.x() == 0 and cur.y() == target_y and cur.width() == target_w and cur.height() == target_h):
                            tab.setGeometry(0, target_y, target_w, target_h)
                    finally:
                        state["anchoring"] = False

                class _AnchorFilter(QtCore.QObject):
                    def eventFilter(self, obj, event):
                        if obj is container and event.type() in (QtCore.QEvent.Resize, QtCore.QEvent.Paint, QtCore.QEvent.LayoutRequest):
                            layout_tab_widget()
                        return False

                filt = _AnchorFilter(container)
                container.installEventFilter(filt)
                container._bottomAnchorFilter = filt  # referansı canlı tut

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

            # Overlay paneli kapatılıp açılınca yeniden oluşturulabiliyor;
            # bu yüzden periyodik olarak kontrol edip gerekirse yeniden bağlan
            QtCore.QTimer.singleShot(2000, _self_ref[0])

        _self_ref.append(_setup_property_editor_anchoring)
        return _setup_property_editor_anchoring

    _setup_property_editor_anchoring = _make_property_editor_anchor_setup()
    QtCore.QTimer.singleShot(2000, _setup_property_editor_anchoring)
except Exception:
    pass
