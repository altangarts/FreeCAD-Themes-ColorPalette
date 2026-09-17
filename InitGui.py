import os
import FreeCAD

def _load_module(mod_dir, module_name, file_name, error_label):
    import importlib.util
    try:
        spec = importlib.util.spec_from_file_location(
            module_name, os.path.join(mod_dir, file_name)
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception as e:
        FreeCAD.Console.PrintError(f"ColorPalette: {error_label} yuklenemedi - {str(e)}\n")
        return None

_mod_dir = os.path.join(FreeCAD.getUserAppDataDir(), "Mod", "Color-Palette-Theme")

# Tercihler sayfasının her koşulda (tema aktif olmasa bile) menüde görünmesi için önce yüklenir:
_load_module(_mod_dir, "colorpalette_theme_presets", "colorpalette_theme_presets.py", "colorpalette_theme_presets")

# Tema aktifse diğer görsel düzeltme modüllerini yükle
def _is_colorpalette_theme_active():
    param = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/MainWindow")
    current_theme = param.GetString("StyleSheet", "").lower()
    return "colorpalette" in current_theme or "color-palette" in current_theme

if _is_colorpalette_theme_active():
    _load_module(_mod_dir, "color_palette_theme_sync", "viewport_color_sync.py", "viewport_color_sync")
    _load_module(_mod_dir, "color_palette_dynamic_editor", "dynamic_property_editor.py", "dynamic_property_editor")
    _load_module(_mod_dir, "colorpalette_grid", "colorpalette_grid.py", "colorpalette_grid")
    _load_module(_mod_dir, "color_palette_workbench_combobox", "workbench_combobox.py", "workbench_combobox")

    try:
        def _apply_task_panel_style_fix():
            try:
                import FreeCADGui as Gui
                from PySide6 import QtCore, QtWidgets

                mw = Gui.getMainWindow()
                targets = mw.findChildren(QtWidgets.QWidget, "Tasks")

                for w in targets:
                    w.setAttribute(QtCore.Qt.WA_StyledBackground, True)
                    w.style().unpolish(w)
                    w.style().polish(w)
                    w.update()

                if not targets:
                    FreeCAD.Console.PrintError("ColorPalette: Task paneli (Tasks) bulunamadi, WA_StyledBackground uygulanamadi.\n")
            except Exception as e:
                FreeCAD.Console.PrintError(f"ColorPalette: task_panel_style_fix calisirken hata - {str(e)}\n")

        from PySide6 import QtCore
        QtCore.QTimer.singleShot(0, _apply_task_panel_style_fix)
    except Exception as e:
        FreeCAD.Console.PrintError(f"ColorPalette: task_panel_style_fix kurulamadi - {str(e)}\n")

    try:
        def _apply_workbench_floating_fix():
            try:
                import FreeCADGui as Gui
                from PySide6 import QtCore

                mw = Gui.getMainWindow()
                tb = mw.findChild(QtCore.QObject, "Workbench")

                if tb:
                    def on_top_level_changed(is_floating):
                        tb.setProperty("floating", is_floating)
                        tb.style().unpolish(tb)
                        tb.style().polish(tb)
                        tb.update()

                    tb.topLevelChanged.connect(on_top_level_changed)
                else:
                    FreeCAD.Console.PrintError("ColorPalette: Workbench arac cubugu bulunamadi.\n")
            except Exception as e:
                FreeCAD.Console.PrintError(f"ColorPalette: workbench_floating_fix calisirken hata - {str(e)}\n")

        from PySide6 import QtCore
        QtCore.QTimer.singleShot(1000, _apply_workbench_floating_fix)
    except Exception as e:
        FreeCAD.Console.PrintError(f"ColorPalette: workbench_floating_fix kurulamadi - {str(e)}\n")

    try:
        def _setup_dialog_and_task_fixer():
            from PySide6 import QtCore, QtWidgets
            import FreeCADGui as Gui

            mw = Gui.getMainWindow()
            if not mw:
                return

            _scan_timer = QtCore.QTimer()
            _scan_timer.setSingleShot(True)
            _scan_timer.setInterval(150)

            def _refresh_tree_lightweight(tree):
                try:
                    if tree and tree.isVisible() and hasattr(tree, 'doItemsLayout'):
                        tree.doItemsLayout()
                        tree.viewport().update()
                except Exception:
                    pass

            def _fix_tree(tree):
                if not tree or not hasattr(tree, 'model'):
                    return

                try:
                    tree.style().unpolish(tree)
                    tree.style().polish(tree)
                except Exception:
                    pass

                _refresh_tree_lightweight(tree)

                try:
                    model = tree.model()
                    if model and not getattr(tree, "_cp_hooked", False):
                        tree._cp_hooked = True

                        refresh_timer = QtCore.QTimer(tree)
                        refresh_timer.setSingleShot(True)
                        refresh_timer.setInterval(30)
                        refresh_timer.timeout.connect(lambda: _refresh_tree_lightweight(tree))
                        tree._cp_refresh_timer = refresh_timer

                        def _on_model_change(*a):
                            tree._cp_refresh_timer.start()

                        model.rowsInserted.connect(_on_model_change)
                        model.modelReset.connect(_on_model_change)
                        model.layoutChanged.connect(_on_model_change)

                        if isinstance(tree, QtWidgets.QTreeView):
                            tree.expanded.connect(_on_model_change)
                            tree.collapsed.connect(_on_model_change)
                except Exception:
                    pass

            def _scan_and_fix_all():
                try:
                    for tree in mw.findChildren((QtWidgets.QTreeView, QtWidgets.QListView)):
                        _fix_tree(tree)

                    for top in QtWidgets.QApplication.topLevelWidgets():
                        if top.isVisible():
                            for tree in top.findChildren((QtWidgets.QTreeView, QtWidgets.QListView)):
                                _fix_tree(tree)
                except Exception:
                    pass

            _scan_timer.timeout.connect(_scan_and_fix_all)

            def _trigger_debounced_scan():
                _scan_timer.start()

            _WATCHED_EVENTS = frozenset((QtCore.QEvent.Show, QtCore.QEvent.ChildAdded))

            class GlobalTreeFixerFilter(QtCore.QObject):
                def eventFilter(self, obj, event):
                    ev_type = event.type()
                    if ev_type not in _WATCHED_EVENTS:
                        return False

                    if ev_type == QtCore.QEvent.Show:
                        if isinstance(obj, (QtWidgets.QTreeView, QtWidgets.QListView)):
                            _fix_tree(obj)
                        elif isinstance(obj, (QtWidgets.QWidget, QtWidgets.QDialog)):
                            _trigger_debounced_scan()
                    else:  # ChildAdded
                        child = event.child()
                        if isinstance(child, (QtWidgets.QTreeView, QtWidgets.QListView)):
                            _fix_tree(child)
                        elif isinstance(child, QtWidgets.QWidget):
                            _trigger_debounced_scan()

                    return False

            app = QtWidgets.QApplication.instance()
            if app and not hasattr(app, "_cp_global_tree_filter"):
                filter_obj = GlobalTreeFixerFilter(app)
                app.installEventFilter(filter_obj)
                app._cp_global_tree_filter = filter_obj

            if app and not hasattr(app, "_cp_tree_fixer_connected"):
                app._cp_tree_fixer_connected = True
                app.focusChanged.connect(lambda old, new: _trigger_debounced_scan())

            QtCore.QTimer.singleShot(1000, _scan_and_fix_all)

        from PySide6 import QtCore
        QtCore.QTimer.singleShot(1000, _setup_dialog_and_task_fixer)

    except Exception as e:
        FreeCAD.Console.PrintError(f"ColorPalette: DialogAndTaskTreeFixer kurulamadi - {str(e)}\n")
else:
    FreeCAD.Console.PrintMessage("ColorPalette temasi aktif degil, sadece preset tercihler sayfasi yüklendi.\n")