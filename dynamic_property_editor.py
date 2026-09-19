import os
import time
import FreeCAD

try:
    from PySide6 import QtCore, QtWidgets, QtGui
except ImportError:
    from PySide2 import QtCore, QtWidgets, QtGui


_STATE_GRP_PATH = "User parameter:BaseApp/Preferences/Mod/ColorPaletteState"
_state_grp_cache = None


def _state_grp():
    global _state_grp_cache
    if _state_grp_cache is None:
        _state_grp_cache = FreeCAD.ParamGet(_STATE_GRP_PATH)
    return _state_grp_cache


def _register_with_global_filter(list_name, callback, retries_left=20):
    app = QtWidgets.QApplication.instance()
    gfilter = getattr(app, "_cp_global_filter", None) if app else None
    if gfilter is not None:
        getattr(gfilter, list_name).append(callback)
        return
    if retries_left <= 0:
        return
    QtCore.QTimer.singleShot(
        300, lambda: _register_with_global_filter(list_name, callback, retries_left - 1)
    )


_GRID_PREF_GROUP = "ColorPalette"   # colorpalette_grid.py -> _GRID_PREFS_GROUP_NAME ile aynı olmalı
_GRID_PAGE_TITLE_HINTS = ("grid", "ızgara", "izgara")


def _select_grid_page_in_prefs(dialog):
    tree = dialog.findChild(QtWidgets.QTreeView, "groupsTreeView")
    model = tree.model() if tree is not None else None
    if model is None or model.rowCount() == 0:
        return False

    found_titles = []
    for row in range(model.rowCount()):
        group_idx = model.index(row, 0)
        group_text = str(group_idx.data() or "").replace(" ", "").lower()
        if _GRID_PREF_GROUP.lower() not in group_text:
            continue

        for child_row in range(model.rowCount(group_idx)):
            child_idx = model.index(child_row, 0, group_idx)
            title = str(child_idx.data() or "")
            found_titles.append(title)
            if not any(hint in title.lower() for hint in _GRID_PAGE_TITLE_HINTS):
                continue

            tree.expand(group_idx)
            tree.setCurrentIndex(child_idx)
            tree.scrollTo(child_idx)
            try:
                # DlgPreferencesImp::onPageSelected sağdaki sayfayı da değiştirir
                tree.clicked.emit(child_idx)
            except Exception:
                try:
                    from PySide6 import QtTest
                except ImportError:
                    from PySide2 import QtTest
                QtTest.QTest.mouseClick(
                    tree.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier,
                    tree.visualRect(child_idx).center(),
                )
            return True

    FreeCAD.Console.PrintWarning(
        "ColorPalette: '%s' grubunda Grid sayfası bulunamadı. Mevcut sayfalar: %s\n"
        % (_GRID_PREF_GROUP, found_titles)
    )
    return True


def _schedule_grid_page_selection(tries=40, interval_ms=50):
    """Gui.showPreferences() modal (exec) çalıştığı için çağrı geri dönmez;
    sayfa seçimi, pencere açılırken zamanlayıcı ile yapılır."""

    def _poll(left):
        app = QtWidgets.QApplication.instance()
        dialog = app.activeModalWidget() if app else None
        try:
            if dialog is not None and _select_grid_page_in_prefs(dialog):
                return
        except Exception as e:
            FreeCAD.Console.PrintError(f"ColorPalette: Grid sayfasi secilemedi - {str(e)}\n")
            return
        if left > 1:
            QtCore.QTimer.singleShot(interval_ms, lambda: _poll(left - 1))

    QtCore.QTimer.singleShot(0, lambda: _poll(tries))


_cp_menu = None            # oluşturulan ColorPalette QMenu'su (yeniden kullanılır)
_cp_menubar_guard = None   # menubar olay gözlemcisi (referans tutulur)
_CP_MENU_ACTION_NAME = "ColorPaletteMenuAction"
_CP_MENU_TITLE = "ColorPalette"
_CP_THEME_PARAM_PATH = "User parameter:BaseApp/Preferences/MainWindow"
_CP_MENU_DEBUG = False   # True: menü her eklendiğinde/taşındığında Report View'a yazar


_cp_theme_grp_cache = None


def _cp_is_theme_active():
    global _cp_theme_grp_cache
    try:
        if _cp_theme_grp_cache is None:
            _cp_theme_grp_cache = FreeCAD.ParamGet(_CP_THEME_PARAM_PATH)
        theme = _cp_theme_grp_cache.GetString("StyleSheet", "").lower()
    except Exception:
        return True 
    return "colorpalette" in theme or "color-palette" in theme


def _cp_sync_menu(menubar, cp_menu):
    actions = menubar.actions()
    ours = next((a for a in actions if a.objectName() == _CP_MENU_ACTION_NAME), None)

    if not _cp_is_theme_active():
        if ours is not None:
            menubar.removeAction(ours)
            return "removed"
        return None

    help_action = None
    for action in actions:
        if action is ours:
            continue
        txt = action.text().lower()
        if "help" in txt or "yardım" in txt:
            help_action = action
            break

    change = "added"
    if ours is not None:
        repaired = False
        if ours.menu() is not cp_menu:
            ours.setMenu(cp_menu)
            repaired = True
        if ours.text() != _CP_MENU_TITLE:
            ours.setText(_CP_MENU_TITLE)
            repaired = True
        if not ours.isVisible():
            ours.setVisible(True)
            repaired = True
        if repaired:
            change = "repaired"
        if help_action is None:
            return change if repaired else None
        pos = actions.index(ours)
        if pos + 1 < len(actions) and actions[pos + 1] is help_action:
            return change if repaired else None  # zaten doğru yerde
        menubar.removeAction(ours)
        change = "moved"

    if help_action is not None:
        menubar.insertMenu(help_action, cp_menu)
    else:
        menubar.addMenu(cp_menu)
    return change


class _CpThemeParamObserver:

    def __init__(self, callback):
        self._callback = callback

    def slotParamChanged(self, param, param_type, name, value):
        self._callback()

    def onChange(self, param, reason):  # eski Attach() API'si
        self._callback()


class _CpDocumentObserver:

    def __init__(self, callback):
        self._callback = callback

    def slotCreatedDocument(self, doc):
        self._callback()

    def slotActivateDocument(self, doc):
        self._callback()


class _CpMenuBarGuard(QtCore.QObject):

    _WATCHED = (
        QtCore.QEvent.ActionAdded,
        QtCore.QEvent.ActionRemoved,
        QtCore.QEvent.ActionChanged,
    )
    _WATCHDOG_MS = 2000
    _DELAYED_CHECKS_MS = (300, 1200)

    def __init__(self, menubar):
        super().__init__(menubar)
        self._menubar = menubar
        self._fallback_reported = False
        self._delayed_scheduled = False

        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(lambda: self._sync("event"))

        self._watchdog = QtCore.QTimer(self)
        self._watchdog.setInterval(self._WATCHDOG_MS)
        self._watchdog.timeout.connect(lambda: self._sync("watchdog"))
        self._watchdog.start()

        self._param_grp = None
        self._param_observer = _CpThemeParamObserver(self.schedule)
        try:
            self._param_grp = FreeCAD.ParamGet(_CP_THEME_PARAM_PATH)
            try:
                self._param_grp.AttachManager(self._param_observer)
            except Exception:
                self._param_grp.Attach(self._param_observer)
        except Exception as e:
            FreeCAD.Console.PrintWarning(f"ColorPalette: tema gozlemcisi kurulamadi - {str(e)}\n")

        try:
            import FreeCADGui as Gui
            mw = Gui.getMainWindow()
            if mw:
                try:
                    mw.workbenchActivated.connect(lambda *_: self.kick())
                except Exception:
                    pass
                mdi = mw.findChild(QtWidgets.QMdiArea)
                if mdi:
                    mdi.subWindowActivated.connect(lambda *_: self.kick())
        except Exception:
            pass

        try:
            self._doc_observer = _CpDocumentObserver(self.kick)
            FreeCAD.addDocumentObserver(self._doc_observer)
        except Exception:
            self._doc_observer = None

    def schedule(self):
        self._timer.start()

    def kick(self):
        """Workbench/belge/sekme değişimi: hemen ve gecikmeli kontrol."""
        self._timer.start()
        if self._delayed_scheduled:
            return
        self._delayed_scheduled = True
        for ms in self._DELAYED_CHECKS_MS:
            QtCore.QTimer.singleShot(ms, lambda: self._sync("delayed"))
        QtCore.QTimer.singleShot(max(self._DELAYED_CHECKS_MS), self._clear_delayed_flag)

    def _clear_delayed_flag(self):
        self._delayed_scheduled = False

    def eventFilter(self, obj, event):
        if obj is self._menubar and event.type() in self._WATCHED:
            self._timer.start()
        return False

    def _sync(self, source):
        global _cp_menu
        if _cp_menu is None:
            _setup_colorpalette_menu()
            return
        try:
            try:
                _cp_menu.menuAction()
            except RuntimeError:
                _cp_menu = None
                _setup_colorpalette_menu()
                return

            change = _cp_sync_menu(self._menubar, _cp_menu)
            if not change:
                return

            if _CP_MENU_DEBUG:
                FreeCAD.Console.PrintMessage(f"ColorPalette: menu {change} (kaynak: {source})\n")
            elif source == "watchdog" and not self._fallback_reported:
                self._fallback_reported = True
                FreeCAD.Console.PrintMessage(
                    f"ColorPalette: menu beklenmeyen durumda watchdog ile duzeltildi ({change})\n"
                )
        except RuntimeError:
            pass
        except Exception as e:
            FreeCAD.Console.PrintError(f"ColorPalette: menu esitlenemedi - {str(e)}\n")


def _cp_install_menubar_guard(menubar):
    global _cp_menubar_guard
    if _cp_menubar_guard is not None:
        return
    _cp_menubar_guard = _CpMenuBarGuard(menubar)
    menubar.installEventFilter(_cp_menubar_guard)
    app = QtWidgets.QApplication.instance()
    if app is not None:
        app._cpMenuBarGuard = _cp_menubar_guard


def _setup_colorpalette_menu(_tries=0):
    global _cp_menu
    try:
        import FreeCADGui as Gui
    except ImportError:
        return

    mw = Gui.getMainWindow()
    menubar = mw.menuBar() if mw else None
    if not menubar:
        if _tries < 120:
            QtCore.QTimer.singleShot(500, lambda: _setup_colorpalette_menu(_tries + 1))
        return

    if _cp_menu is not None:
        try:
            _cp_menu.menuAction()
        except RuntimeError:
            _cp_menu = None
        else:
            _cp_sync_menu(menubar, _cp_menu)
            _cp_install_menubar_guard(menubar)
            return

    existing_action = next(
        (a for a in menubar.actions() if a.objectName() == _CP_MENU_ACTION_NAME), None
    )
    if existing_action is not None:
        existing_menu = existing_action.menu()
        if existing_menu is not None:
            _cp_menu = existing_menu
            _cp_sync_menu(menubar, _cp_menu)
            _cp_install_menubar_guard(menubar)
            return

    cp_menu = QtWidgets.QMenu(_CP_MENU_TITLE, mw)
    cp_menu.setObjectName("ColorPaletteMenu")
    
    cp_action = cp_menu.menuAction()
    cp_action.setObjectName(_CP_MENU_ACTION_NAME)

    normal_font = cp_menu.font()
    normal_font.setBold(False)

    bold_font = cp_menu.font()
    bold_font.setBold(True)

    state_grp = _state_grp()
    
    saved_mode = state_grp.GetString("PropertyEditorMode", "DoubleClick")
    grid_collapsed = state_grp.GetBool("GridCollapsed", False)
    prop_enabled = state_grp.GetBool("PropertyEditorEnabled", True)

    # 1. Satır: Property Editor Başlığı (Bold)
    prop_header = cp_menu.addAction("Property Editor")
    prop_header.setEnabled(False)
    prop_header.setFont(bold_font)

    # 2. Satır: Use Duble Click (Normal)
    act_double_click = cp_menu.addAction("Use Duble Click")
    act_double_click.setCheckable(True)
    act_double_click.setChecked(saved_mode == "DoubleClick")
    act_double_click.setFont(normal_font)

    # 3. Satır: Use Standard (Normal)
    act_standard = cp_menu.addAction("Use Standard")
    act_standard.setCheckable(True)
    act_standard.setChecked(saved_mode == "Standard")
    act_standard.setFont(normal_font)

    mode_group = QtGui.QActionGroup(cp_menu)
    mode_group.addAction(act_double_click)
    mode_group.addAction(act_standard)
    mode_group.setExclusive(True)

    # 4. Satır: Property Editor On/Off (Normal, checkable)
    act_prop_toggle = cp_menu.addAction("Property Editor On/Off")
    act_prop_toggle.setCheckable(True)
    act_prop_toggle.setChecked(prop_enabled)
    act_prop_toggle.setFont(normal_font)

    cp_menu.addSeparator()

    # 5. Satır: Grid Başlığı (Bold)
    grid_header = cp_menu.addAction("Grid")
    grid_header.setEnabled(False)
    grid_header.setFont(bold_font)

    # 6. Satır: Grid On/Off (Normal)
    act_grid_toggle = cp_menu.addAction("Grid On/Off")
    act_grid_toggle.setCheckable(True)
    act_grid_toggle.setChecked(not grid_collapsed)
    act_grid_toggle.setFont(normal_font)

    # 7. Satır: Grid Settings (Normal)
    act_grid_settings = cp_menu.addAction("Grid Settings")
    act_grid_settings.setFont(normal_font)

    def on_mode_changed(action):
        if action == act_double_click and act_double_click.isChecked():
            state_grp.SetString("PropertyEditorMode", "DoubleClick")
        elif action == act_standard and act_standard.isChecked():
            state_grp.SetString("PropertyEditorMode", "Standard")
        _cp_sync_view_callbacks()

    mode_group.triggered.connect(on_mode_changed)

    def on_prop_toggle(checked):
        state_grp.SetBool("PropertyEditorEnabled", checked)
        _cp_sync_view_callbacks()
        _cp_request_layout()

    act_prop_toggle.triggered.connect(on_prop_toggle)

    def on_grid_toggle(checked):
        new_collapsed = not checked
        state_grp.SetBool("GridCollapsed", new_collapsed)
        try:
            import colorpalette_grid
            colorpalette_grid.toggle_3d_grid()
        except ImportError:
            pass

    act_grid_toggle.triggered.connect(on_grid_toggle)

    def on_grid_settings():
        _schedule_grid_page_selection()
        try:
            Gui.showPreferences(_GRID_PREF_GROUP)
        except Exception:
            try:
                Gui.runCommand("Std_DlgPreferences", 0)
            except Exception:
                pass

    act_grid_settings.triggered.connect(on_grid_settings)

    _cp_menu = cp_menu
    _cp_sync_menu(menubar, cp_menu)
    _cp_install_menubar_guard(menubar)


class _CosmeticHandleFilter(QtCore.QObject):
    _BLOCKED = (QtCore.QEvent.MouseButtonPress,
                QtCore.QEvent.MouseButtonRelease,
                QtCore.QEvent.MouseButtonDblClick,
                QtCore.QEvent.MouseMove)

    def eventFilter(self, obj, event):
        return event.type() in self._BLOCKED


def _bootstrap_property_editor_anchoring():
    _tries = [0]

    def _setup():
        global _cp_schedule_layout_fn
        import FreeCADGui
        _tries[0] += 1
        mw = FreeCADGui.getMainWindow()
        if not mw:
            if _tries[0] < 240:
                QtCore.QTimer.singleShot(500, _setup)
            return

        tab = mw.findChild(QtWidgets.QTabWidget, "propertyTab")
        container = tab.parent() if tab else None
        if not tab or not container:
            if _tries[0] < 240:
                QtCore.QTimer.singleShot(1000, _setup)
            return

        if container.property("_bottomAnchorInstalled"):
            return

        container.setProperty("_bottomAnchorInstalled", True)
        trees = [t for t in [mw.findChild(QtWidgets.QTreeView, "propertyEditorView"),
                             mw.findChild(QtWidgets.QTreeView, "propertyEditorData")] if t]
        original_layout = container.layout()

        original_vscroll_policies = {t: t.verticalScrollBarPolicy() for t in trees}

        proxy_scrollbar = QtWidgets.QScrollBar(QtCore.Qt.Vertical, container)
        proxy_scrollbar.setObjectName("propertyEditorProxyScrollBar")
        proxy_scrollbar.hide()
        container._proxyScrollBar = proxy_scrollbar
        
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

        def _tree_height(tree, model, parent, current_h=0, max_height=1200):
            h = current_h
            row_count = model.rowCount(parent)
            for i in range(row_count):
                if h > max_height:
                    break
                idx = model.index(i, 0, parent)
                try:
                    h += tree.rowHeight(idx)
                except Exception:
                    h += 20
                if tree.isExpanded(idx):
                    h = _tree_height(tree, model, idx, h, max_height)
            return h

        _height_cache = {"height": 0, "dirty": True}

        def _mark_height_dirty(*a):
            _height_cache["dirty"] = True
            _schedule_layout()

        def _content_height():
            state_grp = _state_grp()
            if not state_grp.GetBool("PropertyEditorEnabled", True):
                return 0

            if not _height_cache["dirty"]:
                return _height_cache["height"]

            total = 0
            for tree in trees:
                if not tree or not tree.isVisible():
                    continue
                model = tree.model()
                if model:
                    total = max(total, _tree_height(tree, model, QtCore.QModelIndex()))
            
            _height_cache["height"] = total
            _height_cache["dirty"] = False
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
        state = {"anchoring": False, "in_active_mode": False, "layout_scheduled": False,
                 "proxy_bound_tree": None, "proxy_bound_conn": None, "proxy_sync_lock": False,
                 "needs_proxy_scroll": False, "proxy_w": 0}
        splitter = container.parent() if isinstance(container.parent(), QtWidgets.QSplitter) else None
        splitter_idx = splitter.indexOf(container) if splitter else -1
        above_idx = splitter_idx - 1 if (splitter and splitter_idx > 0) else None
        original_handle_width = splitter.handleWidth() if splitter else None

        def _bind_proxy_scrollbar(tree):
            if state.get("proxy_bound_tree") is tree:
                return

            prev = state.get("proxy_bound_conn")
            if prev:
                prev_vbar, sync_from_real, sync_to_real = prev
                try:
                    prev_vbar.rangeChanged.disconnect(sync_from_real)
                    prev_vbar.valueChanged.disconnect(sync_from_real)
                except Exception:
                    pass
                try:
                    proxy_scrollbar.valueChanged.disconnect(sync_to_real)
                except Exception:
                    pass
            state["proxy_bound_tree"] = None
            state["proxy_bound_conn"] = None

            if not tree:
                return
            vbar = tree.verticalScrollBar()
            if not vbar:
                return

            def _sync_from_real(_=None):
                if state.get("proxy_sync_lock"):
                    return
                state["proxy_sync_lock"] = True
                try:
                    proxy_scrollbar.setRange(vbar.minimum(), vbar.maximum())
                    proxy_scrollbar.setPageStep(vbar.pageStep())
                    proxy_scrollbar.setSingleStep(vbar.singleStep())
                    proxy_scrollbar.setValue(vbar.value())
                finally:
                    state["proxy_sync_lock"] = False

            def _sync_to_real(v):
                if state.get("proxy_sync_lock"):
                    return
                state["proxy_sync_lock"] = True
                try:
                    vbar.setValue(v)
                finally:
                    state["proxy_sync_lock"] = False

            vbar.rangeChanged.connect(_sync_from_real)
            vbar.valueChanged.connect(_sync_from_real)
            proxy_scrollbar.valueChanged.connect(_sync_to_real)
            state["proxy_bound_tree"] = tree
            state["proxy_bound_conn"] = (vbar, _sync_from_real, _sync_to_real)
            _sync_from_real()

        def layout_tab_widget():
            if state["anchoring"]:
                return
                
            panel_state = _get_panel_state(dock_widget)
            state["in_active_mode"] = True
            
            if original_layout and original_layout.indexOf(tab) != -1:
                original_layout.removeWidget(tab)

            if splitter:
                splitter.setCollapsible(splitter_idx, False)
                for i in range(1, splitter.count()):
                    h = splitter.handle(i)
                    if h:
                        if h.isEnabled():
                            h.setEnabled(False)
                        if h.cursor().shape() != QtCore.Qt.ArrowCursor:
                            h.setCursor(QtCore.Qt.ArrowCursor)
                        if not h.testAttribute(QtCore.Qt.WA_TransparentForMouseEvents):
                            h.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
                        if not hasattr(h, "_cosmeticFilter"):
                            filt_handle = _CosmeticHandleFilter(h)
                            h.installEventFilter(filt_handle)
                            h._cosmeticFilter = filt_handle

                want_handle_w = 0 if panel_state == "overlay" else original_handle_width
                if want_handle_w is not None and splitter.handleWidth() != want_handle_w:
                    splitter.setHandleWidth(want_handle_w)

            proxy_w = (proxy_scrollbar.sizeHint().width()
                       or QtWidgets.QApplication.style().pixelMetric(QtWidgets.QStyle.PM_ScrollBarExtent)
                       or 16)
            active_tree = next((t for t in trees if t and t.isVisible()), None)

            if panel_state == "overlay":
                for t in trees:
                    if t and t.verticalScrollBarPolicy() != QtCore.Qt.ScrollBarAlwaysOff:
                        t.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            else:
                for t in trees:
                    if t and t in original_vscroll_policies:
                        orig_policy = original_vscroll_policies[t]
                        if t.verticalScrollBarPolicy() != orig_policy:
                            t.setVerticalScrollBarPolicy(orig_policy)
                _bind_proxy_scrollbar(None)
                if not proxy_scrollbar.isHidden():
                    proxy_scrollbar.setVisible(False)
                state["needs_proxy_scroll"] = False
                state["proxy_w"] = 0

            state_grp = _state_grp()
            prop_enabled = state_grp.GetBool("PropertyEditorEnabled", True)

            global _cp_editor_active
            is_active = prop_enabled and globals().get("_cp_editor_active", False)

            if tab.isHidden() == is_active:
                tab.setVisible(is_active)

            if not is_active:
                desired_tab_h = 0
            else:
                content_h = _content_height()
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
                
            desired_total_h = desired_tab_h if is_active else 0
            
            state["anchoring"] = True
            try:
                if splitter and splitter_idx != -1:
                    total = sum(splitter.sizes())
                    min_above_h = _min_panel_height(splitter.widget(above_idx)) if above_idx is not None else 0
                    max_prop_h = max(total - min_above_h, 0 if not is_active else 50)
                    target_total_h = max(min(desired_total_h, max_prop_h), 0 if not is_active else 50)
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
                            new_sizes[splitter_idx] = max(new_sizes[splitter_idx] - deficit, 0 if not is_active else 50)
                        splitter.setSizes(new_sizes)
                else:
                    target_total_h = max(min(desired_total_h, container.rect().height()), 0 if not is_active else 50)
            finally:
                state["anchoring"] = False

            if panel_state == "overlay":
                needs_proxy_scroll = False
                if is_active:
                    available_tab_h = max(target_total_h, 0)
                    needs_proxy_scroll = desired_tab_h > available_tab_h + 1 

                if needs_proxy_scroll:
                    _bind_proxy_scrollbar(active_tree)
                else:
                    _bind_proxy_scrollbar(None)

                proxy_scrollbar.setVisible(needs_proxy_scroll)
                state["needs_proxy_scroll"] = needs_proxy_scroll
                state["proxy_w"] = proxy_w if needs_proxy_scroll else 0

            def _apply_geometry():
                if state["anchoring"]:
                    return
                state["anchoring"] = True
                try:
                    full_rect = container.rect()
                    tab_x = tab.x()
                    proxy_w = state.get("proxy_w", 0)
                    tab_w = max(full_rect.width() - proxy_w, 0)

                    target_tab_h = max(full_rect.height(), 0) if is_active else 0
                    if tab.minimumHeight() != target_tab_h or tab.maximumHeight() != target_tab_h:
                        tab.setFixedHeight(target_tab_h)
                    new_geo = QtCore.QRect(tab_x, 0, tab_w, target_tab_h)
                    if tab.geometry() != new_geo:
                        tab.setGeometry(new_geo)

                    if state.get("needs_proxy_scroll"):
                        sb_geo = QtCore.QRect(tab_x + tab_w, 0, proxy_w, target_tab_h)
                        if proxy_scrollbar.geometry() != sb_geo:
                            proxy_scrollbar.setGeometry(sb_geo)
                        proxy_scrollbar.raise_()
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
                
            QtCore.QTimer.singleShot(100, _do_layout)

        container._cp_schedule_layout = _schedule_layout
        _cp_schedule_layout_fn = _schedule_layout

        class AnchorFilter(QtCore.QObject):
            def eventFilter(self, obj, event):
                if obj is container and not state["anchoring"]:
                    if event.type() in (QtCore.QEvent.Resize, QtCore.QEvent.Show, QtCore.QEvent.ParentChange):
                        _schedule_layout()
                return False

        filt = AnchorFilter(container)
        container.installEventFilter(filt)
        container._bottomAnchorFilter = filt

        for tree in trees:
            model = tree.model()
            if model:
                model.rowsInserted.connect(_mark_height_dirty)
                model.rowsRemoved.connect(_mark_height_dirty)
                model.modelReset.connect(_mark_height_dirty)
            tree.expanded.connect(_mark_height_dirty)
            tree.collapsed.connect(_mark_height_dirty)

        tab.currentChanged.connect(_mark_height_dirty)

        _schedule_layout()
        container.update()
        _cp_sync_view_callbacks()
        
        state_grp = _state_grp()
        if not state_grp.GetBool("GridCollapsed", False):
            try:
                import colorpalette_grid
                QtCore.QTimer.singleShot(1000, colorpalette_grid.toggle_3d_grid)
            except ImportError:
                pass

    QtCore.QTimer.singleShot(2000, _setup)


# --- Seçim ve Çift Tıklama Gözlemcisi ---
_cp_editor_active = False
_cp_schedule_layout_fn = None
_cp_clear_check_pending = False


def _cp_request_layout():
    fn = _cp_schedule_layout_fn
    if fn:
        try:
            fn()
        except Exception:
            pass


def _cp_has_selection():
    try:
        import FreeCADGui as Gui
        try:
            return bool(Gui.Selection.hasSelection())
        except AttributeError:
            return bool(Gui.Selection.getSelection())
    except Exception:
        False


class _ColorPaletteSelectionObserver:
    def addSelection(self, doc, obj, sub, pnt):
        self._handle_selection(sub, is_double_click=False)

    def setSelection(self, doc):
        pass

    def clearSelection(self, doc):
        global _cp_editor_active, _cp_clear_check_pending
        if not _cp_editor_active:
            return

        mode = _state_grp().GetString("PropertyEditorMode", "DoubleClick")

        if mode == "DoubleClick":
            if not _cp_editor_active:
                return

            if not _cp_clear_check_pending:
                _cp_clear_check_pending = True
                QtCore.QTimer.singleShot(50, self._deferred_clear_check)
            return

        _cp_editor_active = False
        _cp_request_layout()

    def _deferred_clear_check(self):
        global _cp_editor_active, _cp_clear_check_pending
        _cp_clear_check_pending = False
        if _cp_has_selection():
            return
        if _cp_editor_active:
            _cp_editor_active = False
            _cp_request_layout()

    def _handle_selection(self, sub, is_double_click):
        global _cp_editor_active
        grp = _state_grp()
        if not grp.GetBool("PropertyEditorEnabled", True):
            return

        mode = grp.GetString("PropertyEditorMode", "DoubleClick")
        if mode == "Standard":
            if _cp_editor_active:
                return
            _cp_editor_active = True
        elif mode == "DoubleClick":
            if not is_double_click or _cp_editor_active:
                return
            _cp_editor_active = True
        else:
            return
        _cp_request_layout()


class _ColorPaletteViewEventFilter(QtCore.QObject):
    def _activate_editor(self):
        global _cp_editor_active
        if _cp_editor_active or not _cp_has_selection():
            return
        _cp_editor_active = True
        _cp_request_layout()

    def eventFilter(self, obj, event):
        if event.type() != QtCore.QEvent.MouseButtonDblClick:
            return False

        try:
            if event.button() == QtCore.Qt.LeftButton:
                QtCore.QTimer.singleShot(0, self._activate_editor)
        except Exception:
            pass

        return False


_cp_sel_observer = None
_cp_view_callback_ids = {}
_cp_mdi_connected = False
_cp_last_click_time = 0.0
_cp_last_click_pos = None


def _cp_view_double_click_callback(info):
    global _cp_last_click_time, _cp_last_click_pos

    try:
        grp = _state_grp()
        if not grp.GetBool("PropertyEditorEnabled", True):
            return
        if grp.GetString("PropertyEditorMode", "DoubleClick") != "DoubleClick":
            return

        if info.get("State") != "DOWN":
            return
        if info.get("Button") not in ("BUTTON1", "BUTTON1DOWN", 1):
            return

        now = time.monotonic()
        pos = info.get("Position")

        interval_ms = 500
        try:
            app = QtWidgets.QApplication.instance()
            if app is not None:
                interval_ms = max(100, int(app.doubleClickInterval()))
        except Exception:
            pass

        interval = interval_ms / 1000.0

        same_pos = True
        if _cp_last_click_pos is not None and pos is not None:
            try:
                dx = float(pos[0]) - float(_cp_last_click_pos[0])
                dy = float(pos[1]) - float(_cp_last_click_pos[1])
                same_pos = (dx * dx + dy * dy) <= 64.0
            except Exception:
                same_pos = True

        if (now - _cp_last_click_time) <= interval and same_pos:
            _cp_last_click_time = 0.0
            _cp_last_click_pos = None

            QtCore.QTimer.singleShot(0, _cp_activate_editor)
            return

        _cp_last_click_time = now
        try:
            _cp_last_click_pos = (float(pos[0]), float(pos[1])) if pos is not None else None
        except Exception:
            _cp_last_click_pos = None

    except Exception:
        pass


def _cp_activate_editor():
    global _cp_editor_active
    if _cp_editor_active or not _cp_has_selection():
        return
    _cp_editor_active = True
    _cp_request_layout()


def _cp_view_callback_for_view(view):
    if view is None:
        return

    key = id(view)
    if key in _cp_view_callback_ids:
        return

    try:
        callback_id = view.addEventCallback(
            "SoMouseButtonEvent",
            _cp_view_double_click_callback,
        )
        _cp_view_callback_ids[key] = (view, callback_id)
    except Exception:
        pass


def _cp_remove_view_callback(view):
    if view is None:
        return

    key = id(view)
    entry = _cp_view_callback_ids.pop(key, None)
    if entry is None:
        return

    old_view, callback_id = entry
    try:
        old_view.removeEventCallback("SoMouseButtonEvent", callback_id)
    except Exception:
        pass


def _cp_sync_view_callbacks():
    try:
        grp = _state_grp()
        enabled = (
            grp.GetBool("PropertyEditorEnabled", True)
            and grp.GetString("PropertyEditorMode", "DoubleClick") == "DoubleClick"
        )

        import FreeCADGui as Gui

        active_view = None
        doc = Gui.activeDocument()
        if doc:
            try:
                active_view = doc.activeView()
            except Exception:
                active_view = None

        if not enabled or active_view is None:
            for view, _callback_id in tuple(_cp_view_callback_ids.values()):
                _cp_remove_view_callback(view)
            return

        _cp_view_callback_for_view(active_view)

        for key, (view, _callback_id) in tuple(_cp_view_callback_ids.items()):
            if view is not active_view:
                _cp_remove_view_callback(view)

    except Exception:
        pass


def _bootstrap_double_click_handler(_tries=0):
    global _cp_sel_observer, _cp_mdi_connected

    try:
        import FreeCADGui as Gui
        mw = Gui.getMainWindow()
        if not mw:
            if _tries < 240:
                QtCore.QTimer.singleShot(
                    500,
                    lambda: _bootstrap_double_click_handler(_tries + 1),
                )
            return

        if _cp_sel_observer is None:
            _cp_sel_observer = _ColorPaletteSelectionObserver()
            Gui.Selection.addObserver(_cp_sel_observer)

        mdi = mw.findChild(QtWidgets.QMdiArea)
        if mdi and not _cp_mdi_connected:
            mdi.subWindowActivated.connect(
                lambda *_: _cp_sync_view_callbacks()
            )
            _cp_mdi_connected = True

        _cp_sync_view_callbacks()

    except Exception:
        pass


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
        _register_with_global_filter(
            "pref_dialog_show_callbacks",
            lambda dialog: QtCore.QTimer.singleShot(100, lambda: _lock_combo_in_dialog(dialog)),
        )

    def _setup():
        _enforce_combined_tree_property_mode()
        _install_preferences_watcher()

    QtCore.QTimer.singleShot(2500, _setup)

def _bootstrap_colorpalette_menu():
    QtCore.QTimer.singleShot(1500, _setup_colorpalette_menu)


if __name__ == "__main__" or __name__ == "color_palette_dynamic_editor":
    _bootstrap_colorpalette_menu()
    _bootstrap_property_editor_anchoring()
    _bootstrap_lock_tree_property_view_mode()
    _bootstrap_double_click_handler()