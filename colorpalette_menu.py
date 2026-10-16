
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


_suppress_observer = False 
_cp_actions = {}           
_cp_last_state = {}        
_cp_state_observer = None


def _state_set(kind, key, value):
    global _suppress_observer
    _suppress_observer = True
    try:
        getattr(_state_grp(), kind)(key, value)
    finally:
        _suppress_observer = False
    _cp_last_state[key] = value


# --- Tema (QSS) degisimi korumasi ---------------------------------------------
# Tercihlerden QSS/tema degisince ColorPaletteState anahtarlari disaridan yeniden
# yazilabiliyor (ornegin PropertyEditorDoubleClick=True). Bunu kullanici secimi
# sanmamak icin: tema degisiminden hemen onceki dis degisiklikler geri alinir,
# sonraki kisa sure icindeki dis yazimlar yok sayilir ve sure bitince mod/motor
# kullanicinin secimine geri yazilir.
_THEME_WINDOW = 3.0            # saniye
_THEME_PARAM_NAMES = ("StyleSheet", "Theme")
_recent_changes = {}           # anahtar -> (eski_deger, zaman)
_theme_guard_until = 0.0


def _remember_change(key, old):
    prev = _recent_changes.get(key)
    now = time.monotonic()
    if prev is not None and now - prev[1] <= _THEME_WINDOW:
        return
    _recent_changes[key] = (old, now)


def _current_mode():
    return _normalize_mode(_state_grp().GetString("PropertyEditorMode", _MODE_DEFAULT))


def _apply_mode(mode):
    _state_set("SetString", "PropertyEditorMode", mode)
    _state_set("SetBool", "PropertyEditorDoubleClick", mode == "DoubleClick")
    act = _cp_actions.get
    if act("double_click") is not None:
        act("double_click").setChecked(mode == "DoubleClick")
        act("standard").setChecked(mode == "Standard")
    _emit("property_mode_changed")


def _mirror_engine_bools(engine):
    """Keep the bool keys used by the settings page radio buttons in sync with the engine string."""
    is_cp = engine == "ColorPalette"
    _state_set("SetBool", "PropertyEngineColorPalette", is_cp)
    _state_set("SetBool", "PropertyEngineFreeCAD", not is_cp)


def _mirror_menubar_bools(as_button):
    """Keep MenuBarAsBar (settings page "Menu Bar" radio) the inverse of MenuBarAsButton."""
    _state_set("SetBool", "MenuBarAsBar", not as_button)


def _apply_engine(engine):
    _state_set("SetString", "PropertyEngine", engine)
    _mirror_engine_bools(engine)
    _sync_engine_actions(engine)


def _restore_state(mode, engine, reason):
    changed = False
    try:
        if mode is not None and _current_mode() != mode:
            _apply_mode(mode)
            changed = True
        if engine is not None and _state_grp().GetString("PropertyEngine", _ENGINE_DEFAULT) != engine:
            _apply_engine(engine)
            changed = True
    except Exception as e:
        FreeCAD.Console.PrintError(f"ColorPalette: could not restore preferences - {str(e)}\n")
        return
    if changed:
        FreeCAD.Console.PrintMessage(
            f"ColorPalette: property editor settings restored after {reason} (mode={mode}, engine={engine})\n")


def _on_theme_param_changed():
    global _theme_guard_until
    now = time.monotonic()
    _theme_guard_until = now + _THEME_WINDOW

    mode = engine = None
    for key, (old, t) in list(_recent_changes.items()):
        if now - t > _THEME_WINDOW or old is None:
            continue
        if key == "PropertyEditorMode":
            mode = old
        elif key == "PropertyEngine":
            engine = old
    _recent_changes.clear()
    _restore_state(mode, engine, "theme change")

    keep_mode = _current_mode()
    keep_engine = _state_grp().GetString("PropertyEngine", _ENGINE_DEFAULT)
    QtCore.QTimer.singleShot(
        int(_THEME_WINDOW * 1000) + 200,
        lambda: _restore_state(keep_mode, keep_engine, "theme change (delayed)"),
    )


# --- Hook sistemi ------------------------------------------------------------
_callbacks = {}


def register_callback(name, fn):
    lst = _callbacks.setdefault(name, [])
    if fn not in lst:
        lst.append(fn)


def _emit(name):
    for fn in list(_callbacks.get(name, [])):
        try:
            fn()
        except Exception as e:
            FreeCAD.Console.PrintError(f"ColorPalette: menu hook '{name}' failed - {str(e)}\n")


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
        "ColorPalette: Grid page not found in group '%s'. Available pages: %s\n"
        % (_GRID_PREF_GROUP, found_titles)
    )
    return True


def _schedule_grid_page_selection(tries=40, interval_ms=50):

    def _poll(left):
        app = QtWidgets.QApplication.instance()
        dialog = app.activeModalWidget() if app else None
        try:
            if dialog is not None and _select_grid_page_in_prefs(dialog):
                return
        except Exception as e:
            FreeCAD.Console.PrintError(f"ColorPalette: could not select the Grid page - {str(e)}\n")
            return
        if left > 1:
            QtCore.QTimer.singleShot(interval_ms, lambda: _poll(left - 1))

    QtCore.QTimer.singleShot(0, lambda: _poll(tries))



# --- Tercihler (Other Settings sayfasi) -> uygulama -------------------------
_STATE_KEYS = (
    "PropertyEngine",              
    "PropertyEngineColorPalette",  
    "PropertyEngineFreeCAD",       
    "PropertyEditorDoubleClick",   
    "PropertyEditorEnabled",
    "GridVisible",                 
    "StatusBarAutoHide",
    "MenuBarAsButton",
    "MenuBarAsBar",                # Settings radio "Menu Bar" (MenuBarAsButton'in tersi)
)


_ENGINE_DEFAULT = "ColorPalette"    
_MODE_DEFAULT = "DoubleClick"      


def _normalize_mode(value):
    """Yalnizca acikca "Standard" ise Standard; digerleri (yok/gecersiz) DoubleClick."""
    return "Standard" if value == "Standard" else _MODE_DEFAULT


def _sync_engine_actions(engine):
    act = _cp_actions.get
    is_fc = engine != "ColorPalette"
    if act("engine_freecad") is not None:
        act("engine_freecad").setChecked(is_fc)
        act("engine_colorpalette").setChecked(not is_fc)
    for key in ("double_click", "standard", "prop_toggle"):
        if act(key) is not None:
            act(key).setEnabled(is_fc)


def _apply_state_key(name):
    grp = _state_grp()
    act = _cp_actions.get

    if name == "PropertyEngine":
        value = grp.GetString(name, _ENGINE_DEFAULT)
        prev = _cp_last_state.get(name)
        if prev == value:
            return
        _remember_change("PropertyEngine", prev)
        _cp_last_state[name] = value
        # Mod (DoubleClick/Standard) motor degisince korunur: ColorPalette'e gecip
        # geri donunce kullanicinin son secimi aynen devam eder.
        _mirror_engine_bools(value)
        _sync_engine_actions(value)
        _emit("property_engine_changed")

    elif name in ("PropertyEngineColorPalette", "PropertyEngineFreeCAD"):
        # Settings page radio buttons -> engine string
        value = grp.GetBool(name, name == "PropertyEngineColorPalette")
        is_cp = value if name == "PropertyEngineColorPalette" else not value
        engine = "ColorPalette" if is_cp else "FreeCAD"
        prev = _cp_last_state.get("PropertyEngine")
        if prev == engine:
            return
        _remember_change("PropertyEngine", prev)
        _state_set("SetString", "PropertyEngine", engine)
        _mirror_engine_bools(engine)
        _sync_engine_actions(engine)
        _emit("property_engine_changed")

    elif name == "PropertyEditorDoubleClick":
        value = grp.GetBool(name, True)
        if _cp_last_state.get(name) == value:
            return
        _remember_change("PropertyEditorMode", _current_mode())
        _cp_last_state[name] = value
        mode = "DoubleClick" if value else "Standard"
        _state_set("SetString", "PropertyEditorMode", mode)
        if act("double_click") is not None:
            act("double_click").setChecked(value)
            act("standard").setChecked(not value)
        _emit("property_mode_changed")

    elif name == "PropertyEditorEnabled":
        value = grp.GetBool(name, True)
        if _cp_last_state.get(name) == value:
            return
        _cp_last_state[name] = value
        if act("prop_toggle") is not None:
            act("prop_toggle").setChecked(value)
        _emit("property_enabled_changed")

    elif name == "GridVisible":
        value = grp.GetBool(name, True)
        if _cp_last_state.get(name) == value:
            return
        _cp_last_state[name] = value
        _state_set("SetBool", "GridCollapsed", not value)
        if act("grid_toggle") is not None:
            act("grid_toggle").setChecked(value)
        try:
            import colorpalette_grid
            colorpalette_grid.toggle_3d_grid()
        except ImportError:
            pass

    elif name == "StatusBarAutoHide":
        value = grp.GetBool(name, True)
        if _cp_last_state.get(name) == value:
            return
        _cp_last_state[name] = value
        if act("sb_autohide") is not None:
            act("sb_autohide").setChecked(value)
        try:
            import colorpalette_chrome
            colorpalette_chrome.set_statusbar_autohide(value)
        except Exception as e:
            FreeCAD.Console.PrintError(f"ColorPalette: could not apply the status bar feature - {str(e)}\n")

    elif name == "MenuBarAsButton":
        value = grp.GetBool(name, True)
        if _cp_last_state.get(name) == value:
            return
        _cp_last_state[name] = value
        _mirror_menubar_bools(value)
        if act("menu_button") is not None:
            act("menu_button").setChecked(value)
        try:
            import colorpalette_chrome
            colorpalette_chrome.set_menubar_button(value)
        except Exception as e:
            FreeCAD.Console.PrintError(f"ColorPalette: could not apply the menu button feature - {str(e)}\n")

    elif name == "MenuBarAsBar":
        # Settings page "Menu Bar" radio -> MenuBarAsButton
        as_button = not grp.GetBool(name, False)
        if _cp_last_state.get("MenuBarAsButton") == as_button:
            return
        _cp_last_state["MenuBarAsButton"] = as_button
        _state_set("SetBool", "MenuBarAsButton", as_button)
        if act("menu_button") is not None:
            act("menu_button").setChecked(as_button)
        try:
            import colorpalette_chrome
            colorpalette_chrome.set_menubar_button(as_button)
        except Exception as e:
            FreeCAD.Console.PrintError(f"ColorPalette: could not apply the menu button feature - {str(e)}\n")


class _CpStateObserver:

    def _handle(self, name):
        if _suppress_observer or name not in _STATE_KEYS:
            return
        if time.monotonic() < _theme_guard_until:
            return      # tema degisimi sirasinda gelen dis yazimlar yok sayilir
        try:
            _apply_state_key(name)
        except Exception as e:
            FreeCAD.Console.PrintError(f"ColorPalette: could not apply preference change ({name}) - {str(e)}\n")

    def slotParamChanged(self, param, param_type, name, value):
        self._handle(name)

    def onChange(self, param, reason):  # eski Attach() API'si: reason = anahtar adi
        self._handle(reason)


def _install_state_observer():
    global _cp_state_observer
    if _cp_state_observer is not None:
        return
    _cp_state_observer = _CpStateObserver()
    grp = _state_grp()
    try:
        grp.AttachManager(_cp_state_observer)
    except Exception:
        try:
            grp.Attach(_cp_state_observer)
        except Exception as e:
            FreeCAD.Console.PrintWarning(f"ColorPalette: could not install preference observer - {str(e)}\n")


_cp_menu = None           
_cp_menubar_guard = None  
_CP_MENU_ACTION_NAME = "ColorPaletteMenuAction"
_CP_MENU_TITLE = "ColorPalette"
_CP_THEME_PARAM_PATH = "User parameter:BaseApp/Preferences/MainWindow"
_CP_MENU_DEBUG = False  

_cp_theme_grp_cache = None
_cp_theme_active_cache = None


def _cp_is_theme_active():
    global _cp_theme_grp_cache, _cp_theme_active_cache

    if _cp_theme_active_cache is not None:
        return _cp_theme_active_cache

    try:
        if _cp_theme_grp_cache is None:
            _cp_theme_grp_cache = FreeCAD.ParamGet(_CP_THEME_PARAM_PATH)
        theme = _cp_theme_grp_cache.GetString("StyleSheet", "").lower()
        _cp_theme_active_cache = (
            "colorpalette" in theme or "color-palette" in theme
        )
    except Exception:
        _cp_theme_active_cache = True

    return _cp_theme_active_cache


def _cp_invalidate_theme_cache():
    global _cp_theme_active_cache
    _cp_theme_active_cache = None


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
        if name in _THEME_PARAM_NAMES:
            _on_theme_param_changed()
        self._callback()

    def onChange(self, param, reason):  # eski Attach() API'si
        if reason in _THEME_PARAM_NAMES:
            _on_theme_param_changed()
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

        self._param_grp = None
        self._param_observer = _CpThemeParamObserver(self.schedule)
        try:
            self._param_grp = FreeCAD.ParamGet(_CP_THEME_PARAM_PATH)
            try:
                self._param_grp.AttachManager(self._param_observer)
            except Exception:
                self._param_grp.Attach(self._param_observer)
        except Exception as e:
            FreeCAD.Console.PrintWarning(f"ColorPalette: could not install theme observer - {str(e)}\n")

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
        _cp_invalidate_theme_cache()
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
                FreeCAD.Console.PrintMessage(f"ColorPalette: menu {change} (source: {source})\n")
        except RuntimeError:
            pass
        except Exception as e:
            FreeCAD.Console.PrintError(f"ColorPalette: could not sync menu - {str(e)}\n")


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
    
    saved_mode = _normalize_mode(state_grp.GetString("PropertyEditorMode", _MODE_DEFAULT))
    saved_engine = state_grp.GetString("PropertyEngine", _ENGINE_DEFAULT)
    engine_is_fc = saved_engine != "ColorPalette"
    grid_collapsed = state_grp.GetBool("GridCollapsed", False)
    prop_enabled = state_grp.GetBool("PropertyEditorEnabled", True)

    _state_set("SetBool", "PropertyEditorDoubleClick", saved_mode == "DoubleClick")
    _mirror_engine_bools(saved_engine)
    _state_set("SetBool", "GridVisible", not grid_collapsed)
    _mirror_menubar_bools(state_grp.GetBool("MenuBarAsButton", True))
    _cp_last_state.update({
        "PropertyEngine": saved_engine,
        "PropertyEditorEnabled": prop_enabled,
        "GridVisible": not grid_collapsed,
        "StatusBarAutoHide": state_grp.GetBool("StatusBarAutoHide", True),
        "MenuBarAsButton": state_grp.GetBool("MenuBarAsButton", True),
    })

    # 1. Satır: Property Editor Başlığı (Bold)
    prop_header = cp_menu.addAction("Property Editor")
    prop_header.setEnabled(False)
    prop_header.setFont(bold_font)

    # Motor secimi: FreeCAD Property (dinamik editor) / ColorPalette Property (agac butonlari + popup)
    act_engine_cp = cp_menu.addAction("Property Editor / PopUp")
    act_engine_cp.setCheckable(True)
    act_engine_cp.setChecked(not engine_is_fc)
    act_engine_cp.setFont(normal_font)

    act_engine_fc = cp_menu.addAction("Property Editor / ComboView")
    act_engine_fc.setCheckable(True)
    act_engine_fc.setChecked(engine_is_fc)
    act_engine_fc.setFont(normal_font)

    engine_group = QtGui.QActionGroup(cp_menu)
    engine_group.addAction(act_engine_cp)
    engine_group.addAction(act_engine_fc)
    engine_group.setExclusive(True)

    cp_menu.addSeparator()

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

    act_double_click.setEnabled(engine_is_fc)
    act_standard.setEnabled(engine_is_fc)

    mode_group = QtGui.QActionGroup(cp_menu)
    mode_group.addAction(act_double_click)
    mode_group.addAction(act_standard)
    mode_group.setExclusive(True)

    # 4. Satır: Property Editor On/Off (Normal, checkable)
    act_prop_toggle = cp_menu.addAction("Property Editor On/Off")
    act_prop_toggle.setCheckable(True)
    act_prop_toggle.setChecked(prop_enabled)
    act_prop_toggle.setFont(normal_font)
    act_prop_toggle.setEnabled(engine_is_fc)

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

    cp_menu.addSeparator()

    # 8. Satır: Interface Başlığı (Bold)
    ui_header = cp_menu.addAction("Interface")
    ui_header.setEnabled(False)
    ui_header.setFont(bold_font)

    # 9. Satır: Status Bar Auto-Hide On/Off
    act_sb_autohide = cp_menu.addAction("Status Bar Auto-Hide On/Off")
    act_sb_autohide.setCheckable(True)
    act_sb_autohide.setChecked(state_grp.GetBool("StatusBarAutoHide", True))
    act_sb_autohide.setFont(normal_font)

    # 10. Satır: Menu Button/Menu Bar On/Off (menubar yerine tek toolbutton)
    act_menu_button = cp_menu.addAction("Menu Button/Menu Bar On/Off")
    act_menu_button.setCheckable(True)
    act_menu_button.setChecked(state_grp.GetBool("MenuBarAsButton", True))
    act_menu_button.setFont(normal_font)

    cp_menu.addSeparator()

    # 11. Satır: Animation Başlığı (Bold)
    anim_header = cp_menu.addAction("Animation")
    anim_header.setEnabled(False)
    anim_header.setFont(bold_font)

    # 12. Satır: Turntable... (Görev açar)
    act_turntable = cp_menu.addAction("Turntable Motion and Record")
    act_turntable.setFont(normal_font)

    def on_mode_changed(action):
        if action == act_double_click and act_double_click.isChecked():
            _state_set("SetString", "PropertyEditorMode", "DoubleClick")
            _state_set("SetBool", "PropertyEditorDoubleClick", True)
        elif action == act_standard and act_standard.isChecked():
            _state_set("SetString", "PropertyEditorMode", "Standard")
            _state_set("SetBool", "PropertyEditorDoubleClick", False)
        _emit("property_mode_changed")

    mode_group.triggered.connect(on_mode_changed)

    def on_engine_changed(action):
        engine = "ColorPalette" if action == act_engine_cp else "FreeCAD"
        if _cp_last_state.get("PropertyEngine") == engine:
            return
        _state_set("SetString", "PropertyEngine", engine)
        _mirror_engine_bools(engine)
        _sync_engine_actions(engine)
        try:
            QtWidgets.QMessageBox.information(
                mw, "ColorPalette",
                "The property engine change is applied the next time FreeCAD is restarted.",
            )
        except Exception:
            FreeCAD.Console.PrintMessage(
                "ColorPalette: the property engine change is applied on the next restart.\n")

    engine_group.triggered.connect(on_engine_changed)

    def on_prop_toggle(checked):
        _state_set("SetBool", "PropertyEditorEnabled", checked)
        _emit("property_enabled_changed")

    act_prop_toggle.triggered.connect(on_prop_toggle)

    def on_grid_toggle(checked):
        new_collapsed = not checked
        _state_set("SetBool", "GridCollapsed", new_collapsed)
        _state_set("SetBool", "GridVisible", checked)
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

    def on_sb_autohide_toggle(checked):
        _state_set("SetBool", "StatusBarAutoHide", checked)
        try:
            import colorpalette_chrome
            colorpalette_chrome.set_statusbar_autohide(checked)
        except Exception as e:
            FreeCAD.Console.PrintError(f"ColorPalette: could not apply the status bar feature - {str(e)}\n")

    act_sb_autohide.triggered.connect(on_sb_autohide_toggle)

    def on_menu_button_toggle(checked):
        _state_set("SetBool", "MenuBarAsButton", checked)
        _mirror_menubar_bools(checked)
        try:
            import colorpalette_chrome
            colorpalette_chrome.set_menubar_button(checked)
        except Exception as e:
            FreeCAD.Console.PrintError(f"ColorPalette: could not apply the menu button feature - {str(e)}\n")

    act_menu_button.triggered.connect(on_menu_button_toggle)

    def on_turntable():
        try:
            import colorpalette_turntable
            colorpalette_turntable.show_dialog()
        except Exception as e:
            FreeCAD.Console.PrintError(f"ColorPalette: could not open the turntable dialog - {str(e)}\n")

    act_turntable.triggered.connect(on_turntable)

    _cp_actions.update({
        "engine_freecad": act_engine_fc,
        "engine_colorpalette": act_engine_cp,
        "double_click": act_double_click,
        "standard": act_standard,
        "prop_toggle": act_prop_toggle,
        "grid_toggle": act_grid_toggle,
        "sb_autohide": act_sb_autohide,
        "menu_button": act_menu_button,
    })
    _install_state_observer()

    _cp_menu = cp_menu
    _cp_sync_menu(menubar, cp_menu)
    _cp_install_menubar_guard(menubar)


def install():
    _setup_colorpalette_menu()
