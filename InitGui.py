
def _cp_bootstrap():
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

    _load_module(_mod_dir, "colorpalette_theme_presets", "colorpalette_theme_presets.py", "colorpalette_theme_presets")

    def _is_colorpalette_theme_active():
        param = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/MainWindow")
        current_theme = param.GetString("StyleSheet", "").lower()
        return "colorpalette" in current_theme or "color-palette" in current_theme

    _PREF_DIALOG_NAMES = ("Gui::Dialog::DlgPreferencesImp", "DlgPreferencesImp")
    _PREF_DIALOG_TITLE_HINTS = ("preferences", "tercihler", "ayarlar")


    def _looks_like_pref_dialog(widget, QtWidgets):
        obj_name = widget.objectName() if hasattr(widget, "objectName") else ""
        if obj_name in _PREF_DIALOG_NAMES:
            return True
        if hasattr(widget, "inherits") and widget.inherits("QDialog"):
            title = (widget.windowTitle() or "").lower() if hasattr(widget, "windowTitle") else ""
            return any(hint in title for hint in _PREF_DIALOG_TITLE_HINTS)
        return False


    def _install_global_colorpalette_filter():
        try:
            from PySide6 import QtCore, QtWidgets
        except ImportError:
            from PySide2 import QtCore, QtWidgets

        app = QtWidgets.QApplication.instance()
        if not app:
            QtCore.QTimer.singleShot(500, _install_global_colorpalette_filter)
            return

        if hasattr(app, "_cp_global_filter"):
            return

        try:
            import FreeCADGui as Gui
        except ImportError:
            Gui = None

        _TREE_TYPES = (QtWidgets.QTreeView, QtWidgets.QListView)
        _EPHEMERAL_WINDOW_TYPES = (QtCore.Qt.Popup, QtCore.Qt.ToolTip)
        _P_POLISHED = "_cpTreePolished"   # Qt dinamik property: wrapper GC olsa da kaybolmaz
        _P_HOOKED = "_cpTreeHooked"

        def _is_ephemeral(widget):
            """Menü / tooltip gibi kısa ömürlü pencereler ağaç barındırmaz; taramayı tetiklemesin."""
            try:
                return widget.isWindow() and widget.windowType() in _EPHEMERAL_WINDOW_TYPES
            except Exception:
                return False

        def _refresh_tree_lightweight(tree):
            try:
                if tree and tree.isVisible() and hasattr(tree, 'doItemsLayout'):
                    tree.doItemsLayout()
                    tree.viewport().update()
            except Exception:
                pass

        def _fix_tree(tree, on_show=False):
            if not tree or not hasattr(tree, 'model'):
                return

            # unpolish/polish pahalıdır (stylesheet yeniden değerlendirilir):
            # ağaç başına yalnızca ilk karşılaşmada yapılır.
            if not tree.property(_P_POLISHED):
                tree.setProperty(_P_POLISHED, True)
                try:
                    tree.style().unpolish(tree)
                    tree.style().polish(tree)
                except Exception:
                    pass
                _refresh_tree_lightweight(tree)
            elif on_show:
                # Zaten hazır ağaç yeniden gösterildi: sadece hafif, debounce'lu yenileme
                timer = getattr(tree, "_cp_refresh_timer", None)
                if timer is not None:
                    timer.start()
                else:
                    _refresh_tree_lightweight(tree)

            if tree.property(_P_HOOKED):
                return

            try:
                model = tree.model()
                if model:
                    tree.setProperty(_P_HOOKED, True)

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
            if not Gui:
                return
            mw = Gui.getMainWindow()
            if not mw:
                return
            try:
                # Sadece henüz hazırlanmamış ağaçlar işlenir (diğerleri için ucuz property kontrolü)
                for tree in mw.findChildren(_TREE_TYPES):
                    if not tree.property(_P_HOOKED):
                        _fix_tree(tree)

                # mw zaten yukarıda tarandı; tekrar taranmasın
                for top in QtWidgets.QApplication.topLevelWidgets():
                    if top is mw or not top.isVisible() or _is_ephemeral(top):
                        continue
                    for tree in top.findChildren(_TREE_TYPES):
                        if not tree.property(_P_HOOKED):
                            _fix_tree(tree)
            except Exception:
                pass

        _scan_timer = QtCore.QTimer()
        _scan_timer.setSingleShot(True)
        _scan_timer.setInterval(150)
        _scan_timer.timeout.connect(_scan_and_fix_all)

        def _trigger_debounced_scan():
            # start() her çağrıda zamanlayıcıyı sıfırlar; olay sağanağında (bir dialog
            # açılırken yüzlerce Show olayı) gereksiz iş olmasın diye çalışıyorsa dokunma.
            if not _scan_timer.isActive():
                _scan_timer.start()

        _WATCHED_EVENTS = frozenset((QtCore.QEvent.Show, QtCore.QEvent.Hide, QtCore.QEvent.ChildAdded))

        class _ColorPaletteGlobalFilter(QtCore.QObject):
            def __init__(self, parent):
                super().__init__(parent)
                self.pref_dialog_show_callbacks = []
                self.any_dialog_show_callbacks = []
                self.any_dialog_hide_callbacks = []

            def eventFilter(self, obj, event):
                ev_type = event.type()
                if ev_type not in _WATCHED_EVENTS:
                    return False

                if ev_type == QtCore.QEvent.Show:
                    if isinstance(obj, _TREE_TYPES):
                        _fix_tree(obj, on_show=True)
                    elif isinstance(obj, QtWidgets.QWidget):  # QDialog da QWidget'tır
                        if not _is_ephemeral(obj):
                            _trigger_debounced_scan()

                    if isinstance(obj, QtWidgets.QDialog):
                        for cb in list(self.any_dialog_show_callbacks):
                            try:
                                cb(obj)
                            except Exception:
                                pass
                        if _looks_like_pref_dialog(obj, QtWidgets):
                            for cb in list(self.pref_dialog_show_callbacks):
                                try:
                                    cb(obj)
                                except Exception:
                                    pass

                elif ev_type == QtCore.QEvent.Hide:
                    if isinstance(obj, QtWidgets.QDialog):
                        for cb in list(self.any_dialog_hide_callbacks):
                            try:
                                cb(obj)
                            except Exception:
                                pass

                else:  # ChildAdded
                    child = event.child()
                    if isinstance(child, _TREE_TYPES):
                        _fix_tree(child)
                    elif isinstance(child, QtWidgets.QWidget) and not _is_ephemeral(child):
                        _trigger_debounced_scan()

                return False

        gfilter = _ColorPaletteGlobalFilter(app)
        app.installEventFilter(gfilter)
        app._cp_global_filter = gfilter
        app._cp_scan_timer_ref = _scan_timer  # garbage collector'a karsi referans

        if Gui and not hasattr(app, "_cp_focus_scan_connected"):
            app._cp_focus_scan_connected = True
            app.focusChanged.connect(lambda old, new: _trigger_debounced_scan())


    if _is_colorpalette_theme_active():
        _install_global_colorpalette_filter()
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
            from PySide6 import QtCore, QtWidgets

            def _initial_tree_scan():
                app = QtWidgets.QApplication.instance()
                timer = getattr(app, "_cp_scan_timer_ref", None) if app else None
                if timer:
                    timer.start()

            QtCore.QTimer.singleShot(1000, _initial_tree_scan)
        except Exception as e:
            FreeCAD.Console.PrintError(f"ColorPalette: baslangic tree taramasi kurulamadi - {str(e)}\n")
    else:
        FreeCAD.Console.PrintMessage("ColorPalette temasi aktif degil, sadece preset tercihler sayfasi yüklendi.\n")

_cp_bootstrap()
