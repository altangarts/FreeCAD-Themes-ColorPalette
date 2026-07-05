import os
import FreeCAD

def _bootstrap_property_editor_anchoring():
    try:
        from PySide6 import QtCore, QtWidgets, QtGui
    except ImportError:
        from PySide2 import QtCore, QtWidgets, QtGui

    def _setup():
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
            p = widget.parent()
            while p:
                if isinstance(p, QtWidgets.QDockWidget) or p.inherits("QDockWidget") or p.inherits("Gui::DockWnd::DockWindow"):
                    return p
                p = p.parent()
            return None

        def _get_panel_state(dock_widget):
            if not dock_widget:
                return "floating"
            if dock_widget.isWindow() or dock_widget.window() == dock_widget:
                return "floating"
                
            mw_win = dock_widget.window()
            if mw_win and hasattr(mw_win, "dockWidgetArea"):
                area = mw_win.dockWidgetArea(dock_widget)
                no_area = getattr(QtCore.Qt.DockWidgetArea, "NoDockWidgetArea", None) if hasattr(QtCore.Qt, "DockWidgetArea") else QtCore.Qt.NoDockWidgetArea
                
                if area == no_area:
                    return "overlay"
                else:
                    return "docked"
            return "floating"

        def _tree_height(tree, model, parent, current_h=0, max_height=1500):
            h = current_h
            for i in range(model.rowCount(parent)):
                if h > max_height:
                    break
                idx = model.index(i, 0, parent)
                h += tree.rowHeight(idx)
                if tree.isExpanded(idx):
                    h = _tree_height(tree, model, idx, h, max_height)
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

        MIN_ABOVE_PANEL_ROWS = 8

        def _min_panel_height(widget, min_rows=MIN_ABOVE_PANEL_ROWS):
            if not widget:
                return 0
            tree = widget.findChild(QtWidgets.QTreeView)
            if not tree:
                return 0
            row_h = 0
            model = tree.model()
            if model and model.rowCount() > 0:
                row_h = tree.rowHeight(model.index(0, 0))
            if not row_h:
                row_h = QtGui.QFontMetrics(tree.font()).height() + 6
            extra = tree.frameWidth() * 2
            if hasattr(tree, "isHeaderHidden") and not tree.isHeaderHidden() and tree.header():
                extra += tree.header().sizeHint().height() or tree.header().height() or 0
            return row_h * min_rows + extra

        dock_widget = _find_dock_widget(container)
        state = {"anchoring": False, "in_active_mode": False, "collapsed": False, "layout_scheduled": False}
        splitter = container.parent() if isinstance(container.parent(), QtWidgets.QSplitter) else None
        splitter_idx = splitter.indexOf(container) if splitter else -1
        above_idx = splitter_idx - 1 if (splitter and splitter_idx > 0) else None
        original_handle_width = splitter.handleWidth() if splitter else None

        def update_button_text(target_button):
            source_text = "Property View"
            translated_text = source_text
            for ctx in ("PropertyDockView", "Gui::DockWnd::PropertyDockView"):
                try:
                    translated = QtCore.QCoreApplication.translate(ctx, source_text)
                except Exception:
                    translated = None
                if translated and translated != source_text:
                    translated_text = translated
                    break
            target_button.setText(translated_text)

        # --- BUTON SATIRI KONTEYNERİ ---
        btn_container = container.findChild(QtWidgets.QWidget, "propertyEditorBtnContainer")
        if not btn_container:
            btn_container = QtWidgets.QWidget(container)
            btn_container.setObjectName("propertyEditorBtnContainer")
            
            h_layout = QtWidgets.QHBoxLayout(btn_container)
            h_layout.setContentsMargins(2, 0, 0, 0)
            h_layout.setSpacing(4)
            
            state_grp = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/ColorPaletteState")
            prop_is_collapsed = state_grp.GetBool("PropertyCollapsed", False)
            grid_is_collapsed = state_grp.GetBool("GridCollapsed", True)
            
            btn = QtWidgets.QPushButton("Property", btn_container)
            btn.setObjectName("propertyEditorToggleButton")
            btn.setLayoutDirection(QtCore.Qt.RightToLeft)
            btn.setMinimumWidth(120)
            btn.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
            btn.setProperty("is_collapsed", prop_is_collapsed)
            btn.setProperty("collapsed", "true" if prop_is_collapsed else "false")
            
            grid_btn = QtWidgets.QPushButton("Grid", btn_container)
            grid_btn.setObjectName("gridToggleButton")
            grid_btn.setLayoutDirection(QtCore.Qt.RightToLeft)
            grid_btn.setMinimumWidth(70)
            grid_btn.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
            grid_btn.setProperty("is_collapsed", grid_is_collapsed)
            grid_btn.setProperty("collapsed", "true" if grid_is_collapsed else "false")
            
            h_layout.addWidget(btn)
            h_layout.addWidget(grid_btn)
            h_layout.addStretch()
            
            container._btnContainer = btn_container
            container._toggleButton = btn
            container._gridButton = grid_btn
            
            def toggle_grid():
                new_state = not grid_btn.property("is_collapsed")
                grid_btn.setProperty("is_collapsed", new_state)
                grid_btn.setProperty("collapsed", "true" if new_state else "false")
                
                state_grp.SetBool("GridCollapsed", new_state)
                
                grid_btn.style().unpolish(grid_btn)
                grid_btn.style().polish(grid_btn)
                grid_btn.update()
                
                try:
                    import colorpalette_grid
                    colorpalette_grid.toggle_3d_grid()
                except ImportError:
                    pass

            grid_btn.clicked.connect(toggle_grid)
        else:
            btn = btn_container.findChild(QtWidgets.QPushButton, "propertyEditorToggleButton")
            grid_btn = btn_container.findChild(QtWidgets.QPushButton, "gridToggleButton")

        if btn:
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()
            
        if grid_btn:
            grid_btn.style().unpolish(grid_btn)
            grid_btn.style().polish(grid_btn)
            grid_btn.update()

        update_button_text(btn)

        def layout_tab_widget():
            if state["anchoring"]:
                return
                
            panel_state = _get_panel_state(dock_widget)
            state["in_active_mode"] = True
            btn_container.setVisible(True)
            
            if original_layout and original_layout.indexOf(tab) != -1:
                original_layout.removeWidget(tab)

            if splitter:
                splitter.setCollapsible(splitter_idx, False)
                for i in range(1, splitter.count()):
                    h = splitter.handle(i)
                    if h:
                        h.setEnabled(False)
                        h.setCursor(QtCore.Qt.ArrowCursor)
                        h.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
                        if not hasattr(h, "_cosmeticFilter"):
                            class CosmeticHandleFilter(QtCore.QObject):
                                def eventFilter(self, obj, event):
                                    if event.type() in (QtCore.QEvent.MouseButtonPress, 
                                                        QtCore.QEvent.MouseButtonRelease, 
                                                        QtCore.QEvent.MouseButtonDblClick, 
                                                        QtCore.QEvent.MouseMove):
                                        return True
                                    return False
                            filt_handle = CosmeticHandleFilter(h)
                            h.installEventFilter(filt_handle)
                            h._cosmeticFilter = filt_handle
                
                if panel_state == "overlay":
                    splitter.setHandleWidth(0)
                else:
                    if original_handle_width is not None:
                        splitter.setHandleWidth(original_handle_width)

            has_visible_trees = any(tree and tree.isVisible() for tree in trees)
            content_h = _content_height()
            is_empty = (content_h == 0 or not has_visible_trees)
            btn_h = btn_container.sizeHint().height() or 26

            tab.setVisible(True)

            if btn.property("is_collapsed"):
                desired_total_h = btn_h
            else:
                if is_empty:
                    desired_tab_h = 0
                else:
                    tab_bar_h = tab.tabBar().sizeHint().height() if tab.tabBar() else 0
                    dynamic_extra = 4
                    
                    try:
                        frame_w = tab.style().pixelMetric(QtWidgets.QStyle.PM_DefaultFrameWidth, None, tab)
                        dynamic_extra += frame_w * 2
                    except:
                        dynamic_extra += 4
                    
                    for tree in trees:
                        if tree and tree.isVisible():
                            dynamic_extra += tree.frameWidth() * 2
                            if hasattr(tree, "isHeaderHidden") and not tree.isHeaderHidden():
                                if tree.header():
                                    dynamic_extra += tree.header().sizeHint().height() or tree.header().height() or 24
                            break
                    
                    desired_tab_h = tab_bar_h + content_h + dynamic_extra
                    
                desired_total_h = desired_tab_h + btn_h
            
            state["anchoring"] = True
            try:
                if splitter and splitter_idx != -1:
                    total = sum(splitter.sizes())
                    min_above_h = _min_panel_height(splitter.widget(above_idx)) if above_idx is not None else 0
                    max_prop_h = max(total - min_above_h, btn_h)
                    target_total_h = max(min(desired_total_h, max_prop_h), btn_h)
                    sizes = splitter.sizes()
                    if sizes[splitter_idx] != target_total_h:
                        new_sizes = list(sizes)
                        new_sizes[splitter_idx] = target_total_h
                        remainder = total - target_total_h
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
                        if above_idx is not None and above_idx in other_indices and new_sizes[above_idx] < min_above_h:
                            deficit = min_above_h - new_sizes[above_idx]
                            new_sizes[above_idx] = min_above_h
                            new_sizes[splitter_idx] = max(new_sizes[splitter_idx] - deficit, btn_h)
                        splitter.setSizes(new_sizes)
                else:
                    target_total_h = max(min(desired_total_h, container.rect().height()), btn_h)
            finally:
                state["anchoring"] = False

            def _apply_geometry():
                if state["anchoring"]:
                    return
                state["anchoring"] = True
                try:
                    full_rect = container.rect()
                    tab_x = tab.x()
                    target_btn_w = full_rect.width()
                    btn_container.setGeometry(tab_x, full_rect.height() - btn_h, target_btn_w, btn_h)

                    if not btn.property("is_collapsed"):
                        target_tab_h = max(full_rect.height() - btn_h, 0)
                        tab.setFixedHeight(target_tab_h)
                        tab.setGeometry(tab_x, 0, full_rect.width(), target_tab_h)
                    else:
                        tab.setFixedHeight(0)
                        tab.setGeometry(tab_x, 0, full_rect.width(), 0)
                finally:
                    state["anchoring"] = False

            QtCore.QTimer.singleShot(0, _apply_geometry)

        def _schedule_layout():
            if state.get("layout_scheduled"):
                return
            state["layout_scheduled"] = True
            
            def _do_layout():
                state["layout_scheduled"] = False
                layout_tab_widget()
                
            QtCore.QTimer.singleShot(50, _do_layout)

        def toggle_collapsed():
            new_state = not btn.property("is_collapsed")
            btn.setProperty("is_collapsed", new_state)
            btn.setProperty("collapsed", "true" if new_state else "false")
            
            state_grp = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/ColorPaletteState")
            state_grp.SetBool("PropertyCollapsed", new_state)
            
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            _schedule_layout()

        btn.clicked.connect(toggle_collapsed)

        class AnchorFilter(QtCore.QObject):
            def eventFilter(self, obj, event):
                if obj is container:
                    if event.type() in (QtCore.QEvent.Resize, QtCore.QEvent.Show, QtCore.QEvent.ParentChange):
                        _schedule_layout()
                    elif event.type() == QtCore.QEvent.LanguageChange:
                        update_button_text(btn)
                return False

        filt = AnchorFilter(container)
        container.installEventFilter(filt)
        container._bottomAnchorFilter = filt

        for tree in trees:
            model = tree.model()
            if model:
                model.rowsInserted.connect(lambda *a: _schedule_layout())
                model.rowsRemoved.connect(lambda *a: _schedule_layout())
                model.modelReset.connect(lambda *a: _schedule_layout())
            tree.expanded.connect(lambda *a: _schedule_layout())
            tree.collapsed.connect(lambda *a: _schedule_layout())

        tab.currentChanged.connect(lambda *a: _schedule_layout())

        class GlobalSelectionWatcher(QtCore.QObject):
            _WATCHED_EVENTS = (
                QtCore.QEvent.Hide,
                QtCore.QEvent.Show,
                QtCore.QEvent.ChildAdded,
                QtCore.QEvent.ChildRemoved,
            )

            def eventFilter(self, obj, event):
                if event.type() in self._WATCHED_EVENTS:
                    _schedule_layout()
                return False

        watcher = GlobalSelectionWatcher(container)
        for watched in list(trees) + [tab]:
            if watched:
                watched.installEventFilter(watcher)
        container._tabBarVisibilityWatcher = watcher

        _schedule_layout()
        container.update()
        
        state_grp = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/ColorPaletteState")
        if not state_grp.GetBool("GridCollapsed", True):
            try:
                import colorpalette_grid
                QtCore.QTimer.singleShot(1000, colorpalette_grid.toggle_3d_grid)
            except ImportError:
                pass

    QtCore.QTimer.singleShot(2000, _setup)

_TREEVIEW_LOCK_PARAM_PATH = "User parameter:BaseApp/Preferences/DockWindows"

def _enforce_combined_tree_property_mode():
    try:
        hGrp = FreeCAD.ParamGet(_TREEVIEW_LOCK_PARAM_PATH)
        hGrp.GetGroup("ComboView").SetBool("Enabled", True)
        hGrp.GetGroup("TreeView").SetBool("Enabled", False)
        hGrp.GetGroup("PropertyView").SetBool("Enabled", False)
    except Exception:
        pass

def _bootstrap_lock_tree_property_view_mode():
    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtWidgets

    _SHOW_EVENT = QtCore.QEvent.Show

    def _lock_combo_in_dialog(dialog):
        combo = dialog.findChild(QtWidgets.QComboBox, "treeMode")
        if combo:
            if combo.count() > 0 and combo.currentIndex() != 0:
                combo.blockSignals(True)
                combo.setCurrentIndex(0)
                combo.blockSignals(False)
            combo.setEnabled(False)
            combo.setToolTip(
                "Bu ayar yönetici tarafından kilitlenmiştir ve 'Combined' "
                "(Birleşik) modda sabittir, değiştirilemez."
            )
        label = dialog.findChild(QtWidgets.QLabel, "treeModeLabel")
        if label:
            label.setEnabled(False)

    def _install_preferences_watcher():
        app = QtWidgets.QApplication.instance()
        if not app:
            QtCore.QTimer.singleShot(500, _install_preferences_watcher)
            return

        if hasattr(app, "_treeModeLockWatcher"):
            return

        class PreferencesLockWatcher(QtCore.QObject):
            def eventFilter(self, obj, event):
                if event.type() != _SHOW_EVENT:
                    return False

                obj_name = obj.objectName() if hasattr(obj, "objectName") else ""
                if obj_name in ("Gui::Dialog::DlgPreferencesImp", "DlgPreferencesImp"):
                    is_pref_dialog = True
                elif hasattr(obj, "inherits") and obj.inherits("QDialog"):
                    title = (obj.windowTitle() or "").lower() if hasattr(obj, "windowTitle") else ""
                    is_pref_dialog = (
                        "preferences" in title or "tercihler" in title or "ayarlar" in title
                    )
                else:
                    is_pref_dialog = False

                if is_pref_dialog:
                    QtCore.QTimer.singleShot(100, lambda: _lock_combo_in_dialog(obj))
                return False

        watcher = PreferencesLockWatcher(app)
        app.installEventFilter(watcher)
        app._treeModeLockWatcher = watcher

    def _setup():
        _enforce_combined_tree_property_mode()
        _install_preferences_watcher()

    QtCore.QTimer.singleShot(2500, _setup)

if __name__ == "__main__" or __name__ == "color_palette_dynamic_editor":
    _bootstrap_property_editor_anchoring()
    _bootstrap_lock_tree_property_view_mode()