import os
import FreeCAD

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:
    try:
        from PySide2 import QtCore, QtWidgets
    except ImportError:
        from PySide import QtCore, QtGui as QtWidgets

_PARAM_PATH = "User parameter:BaseApp/Preferences/Mod/ColorPalette"
_THEME_PARAM_PATH = "User parameter:BaseApp/Preferences/Themes"

_THEME_PRESETS = [
    ("Light-Gray",         "#005500", "#727270", "#727270"),
    ("Middle-Gray",        "#AA5500", "#414140", "#414140"),
    ("Dark-Gray",          "#55007F", "#212120", "#212120"),
    ("Dark Pale-Green",    "#AA5500", "#2d3234", "#2d3234"),
    ("Darker Pale-Blue",   "#AA5500", "#172028", "#172028"),
    ("FreeCAD Gradyan",    "#00557F", "#2C2C57", "#777788"),
    ("Sand Gradyan",       "#500000", "#3C3328", "#7D6F4F"),
    ("Soft-Green Gradyan", "#AA5500", "#253a3c", "#777775"),
    ("Purple Gradyan",     "#00557F", "#2B1B3F", "#777775"),
    ("Cyberpunk Gradyan",  "#00557F", "#23056C", "#875086"),
]

_FONT_PARAM_GROUP_NAME = "UserParameters"

_FONT_COLOR_PARAMS = [
    ("ColorPaletteTextGeneralTop",     "General Top",       "#eeeeee"),
    ("ColorPaletteTextGeneralBottom",  "General Bottom",    "#000000"),
    ("ColorPaletteTextDisabled",       "Disabled",          "#bbbbbb"),
    ("ColorPaletteTextPropertyEditor", "Property Editor",   "#ffff69"),
    ("ColorPaletteTextHeader",         "Header",            "#f5c5f5"),
    ("ColorPaletteTextHeader2",        "Header 2",          "#ffaa7f"),
    ("ColorPaletteTextGroupBoxHeader", "Group Box Header",  "#c3c3ff"),
    ("ColorPaletteTextHeaderOverlay",  "Header Overlay",    "#f5c5f5"),
    ("ColorPaletteTextList",           "List",              "#ffff69"),
    ("ColorPaletteTextTreeEnd",        "Tree End",          "#ffff69"),
    ("ColorPaletteTextTreeOpen",       "Tree Open",         "#abff7d"),
    ("ColorPaletteTextTreeClosed",     "Tree Closed",       "#beffff"),
    ("ColorPaletteTextCombobox",       "Combobox",          "#beffff"),
    ("ColorPaletteTextSpinBox",        "Spin Box",          "#ffff69"),
    ("ColorPaletteTextRadioButton",    "Radio Button",      "#91ffc8"),
    ("ColorPaletteTextCheckBox",       "Check Box",         "#c6f0ae"),
    ("ColorPaletteTextDarkenList",     "Darken List",       "#eeeeee"),
]


def _normalize_hex(hex_str):
    hex_str = str(hex_str).strip().lstrip('#').upper()
    if len(hex_str) >= 6:
        return f"#{hex_str[:6]}"
    return "#050505"

def _hex_to_rgb(hex_str):
    clean = _normalize_hex(hex_str).lstrip('#')
    return (int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16))

def _int_to_rgb(val):
    if val is None or val == 0:
        return (0, 0, 0)
    r = (val >> 24) & 0xFF
    g = (val >> 16) & 0xFF
    b = (val >> 8) & 0xFF
    return (r, g, b)

def _hex_to_int(hex_str):
    r, g, b = _hex_to_rgb(hex_str)
    return (r << 24) | (g << 16) | (b << 8) | 0xFF

def _find_ui_file():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    full_path = os.path.join(base_dir, "preferences-colorpalettetheme.ui")
    if os.path.isfile(full_path):
        return full_path
    return None

def _get_font_params_group():
    return FreeCAD.ParamGet(_THEME_PARAM_PATH).GetGroup(_FONT_PARAM_GROUP_NAME)

def _get_accent3_hex():
    p = FreeCAD.ParamGet(_PARAM_PATH)
    hex_val = p.GetString("AccentColor3_Hex", "")
    if hex_val:
        return _normalize_hex(hex_val)
    
    p_theme = FreeCAD.ParamGet(_THEME_PARAM_PATH)
    val = p_theme.GetUnsigned("ThemeAccentColor3", 0)
    if val != 0:
        r, g, b = _int_to_rgb(val)
        return f"#{r:02X}{g:02X}{b:02X}"
    return "#727270"

def _update_swatch_appearance(swatch, swatch_hex):
    accent3_hex = _get_accent3_hex()
    obj_name = swatch.objectName() or "swatch"
    swatch.setStyleSheet(
        f"QLabel#{obj_name} {{\n"
        f"    background-color: {swatch_hex};\n"
        f"    border: 1px solid #555;\n"
        f"    border-radius: 3px;\n"
        f"}}\n"
        f"QToolTip {{\n"
        f"    background-color: {accent3_hex};\n"
        f"    color: {swatch_hex};\n"
        f"    border: 1px solid #555;\n"
        f"    padding: 4px;\n"
        f"    font-weight: bold;\n"
        f"}}"
    )
    swatch.setToolTip("Click to select color")

def _apply_font_color(key, hex_value):
    normalized = _normalize_hex(hex_value)
    _get_font_params_group().SetString(key, normalized)
    return normalized

def _force_reload_stylesheet():
    try:
        import FreeCADGui as Gui
        p_theme = FreeCAD.ParamGet(_THEME_PARAM_PATH)
        
        curr_val = p_theme.GetUnsigned("ThemeAccentColor1", 0)
        p_theme.SetUnsigned("ThemeAccentColor1", curr_val ^ 1)
        p_theme.SetUnsigned("ThemeAccentColor1", curr_val)

        mw = Gui.getMainWindow()
        if mw:
            style_name = p_theme.GetString("StyleSheet", "")
            if style_name:
                mw.setProperty("styleSheetName", "")
                mw.setProperty("styleSheetName", style_name)
        
        if hasattr(Gui, "reloadStyleSheet"):
            Gui.reloadStyleSheet()
            
        Gui.updateGui()
    except Exception:
        pass

def _refresh_open_theme_editor():
    app = QtWidgets.QApplication.instance()
    if not app:
        return

    for w in app.topLevelWidgets():
        if not isinstance(w, QtWidgets.QDialog):
            continue

        is_theme_editor = w.objectName() == "DlgThemeEditor"
        if not is_theme_editor:
            is_theme_editor = w.findChild(QtWidgets.QTreeView, "tokensTreeView") is not None

        if not is_theme_editor:
            continue

        button_box = w.findChild(QtWidgets.QDialogButtonBox)
        if not button_box:
            continue

        reset_btn = None
        apply_btn = None
        for btn in button_box.buttons():
            role = button_box.buttonRole(btn)
            if role == QtWidgets.QDialogButtonBox.ResetRole:
                reset_btn = btn
            elif role == QtWidgets.QDialogButtonBox.ApplyRole:
                apply_btn = btn

        if reset_btn:
            reset_btn.click()
        if apply_btn:
            apply_btn.click()

def _apply_selected_theme_preset(selected_idx):
    if 0 <= selected_idx < len(_THEME_PRESETS):
        name, c1_hex, c2_hex, c3_hex = _THEME_PRESETS[selected_idx]
        
        c1_val = _hex_to_int(c1_hex)
        c2_val = _hex_to_int(c2_hex)
        c3_val = _hex_to_int(c3_hex)
        
        p = FreeCAD.ParamGet(_PARAM_PATH)
        p.SetInt("SelectedPreset", selected_idx)
        p.SetUnsigned("AccentColor1", c1_val)
        p.SetUnsigned("AccentColor2", c2_val)
        p.SetUnsigned("AccentColor3", c3_val)
        p.SetString("AccentColor1_Hex", _normalize_hex(c1_hex))
        p.SetString("AccentColor2_Hex", _normalize_hex(c2_hex))
        p.SetString("AccentColor3_Hex", _normalize_hex(c3_hex))

        p_theme = FreeCAD.ParamGet(_THEME_PARAM_PATH)
        p_theme.SetUnsigned("ThemeAccentColor1", c1_val)
        p_theme.SetUnsigned("ThemeAccentColor2", c2_val)
        p_theme.SetUnsigned("ThemeAccentColor3", c3_val)

        _force_reload_stylesheet()

def _build_font_colors_group(widget):
    if widget.findChild(QtWidgets.QGroupBox, "groupBox_fontColors") is not None:
        return

    preset_box = widget.findChild(QtWidgets.QGroupBox, "groupBox_themePresets")
    if preset_box is None:
        return

    group_box = QtWidgets.QGroupBox("Fonts Colors")
    group_box.setObjectName("groupBox_fontColors")
    
    main_layout = QtWidgets.QVBoxLayout(group_box)
    form = QtWidgets.QFormLayout()
    main_layout.addLayout(form)

    grp = _get_font_params_group()
    swatch_refs = []

    for key, label, default_hex in _FONT_COLOR_PARAMS:
        current_hex = _normalize_hex(grp.GetString(key, default_hex))

        row = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)

        swatch = QtWidgets.QLabel()
        swatch.setObjectName(f"swatch_{key}")
        swatch.setFixedSize(20, 20)
        swatch.setCursor(QtCore.Qt.PointingHandCursor)
        swatch.setProperty("hex_value", current_hex)
        _update_swatch_appearance(swatch, current_hex)
        
        swatch_refs.append((key, swatch, default_hex))

        def _make_color_dialog_handler(k=key, sw=swatch):
            def _open_dialog(event):
                if event.button() == QtCore.Qt.LeftButton:
                    try:
                        from PySide6.QtGui import QColor
                    except ImportError:
                        try:
                            from PySide2.QtGui import QColor
                        except ImportError:
                            from PySide.QtGui import QColor
                    
                    current_color = QColor(sw.property("hex_value"))
                    chosen = QtWidgets.QColorDialog.getColor(current_color, widget, "Select Color")
                    
                    if chosen.isValid():
                        hex_val = chosen.name().upper()
                        sw.setProperty("hex_value", hex_val)
                        normalized = _apply_font_color(k, hex_val)
                        _update_swatch_appearance(sw, normalized)
                        if hasattr(widget, "_cpUncheckPresets"):
                            widget._cpUncheckPresets()
            return _open_dialog

        swatch.mousePressEvent = _make_color_dialog_handler()

        row_layout.addWidget(swatch)
        row_layout.addStretch(1)

        form.addRow(label, row)

    btn_layout = QtWidgets.QHBoxLayout()
    btn_white = QtWidgets.QPushButton("All fonts White")
    btn_black = QtWidgets.QPushButton("All fonts Black")
    btn_default = QtWidgets.QPushButton("Default Colors")

    btn_layout.addWidget(btn_white)
    btn_layout.addWidget(btn_black)
    btn_layout.addWidget(btn_default)
    
    main_layout.addLayout(btn_layout)

    def make_batch_handler(mode):
        def handler():
            for k, sw, def_hex in swatch_refs:
                if mode == "white":
                    target_hex = "#FFFFFF"
                elif mode == "black":
                    target_hex = "#000000"
                else:
                    target_hex = def_hex
                    
                sw.setProperty("hex_value", target_hex)
                normalized = _apply_font_color(k, target_hex)
                _update_swatch_appearance(sw, normalized)
            
            if hasattr(widget, "_cpUncheckPresets"):
                widget._cpUncheckPresets()
        return handler

    btn_white.clicked.connect(make_batch_handler("white"))
    btn_black.clicked.connect(make_batch_handler("black"))
    btn_default.clicked.connect(make_batch_handler("default"))

    added = False
    try:
        parent_w = preset_box.parentWidget()
        if parent_w:
            parent_layout = parent_w.layout()
            if parent_layout:
                idx = parent_layout.indexOf(preset_box)
                if idx != -1:
                    parent_layout.insertWidget(idx + 1, group_box)
                    added = True
    except Exception:
        pass

    if not added:
        try:
            w_layout = widget.layout()
            if w_layout:
                w_layout.addWidget(group_box)
        except Exception:
            pass

def _bootstrap_dialog_hook():
    def _init_dialog(widget):
        widget._cpPendingChange = False

        p_theme = FreeCAD.ParamGet(_THEME_PARAM_PATH)
        c1_curr = _int_to_rgb(p_theme.GetUnsigned("ThemeAccentColor1", 0))
        c2_curr = _int_to_rgb(p_theme.GetUnsigned("ThemeAccentColor2", 0))
        c3_curr = _int_to_rgb(p_theme.GetUnsigned("ThemeAccentColor3", 0))

        matched_idx = -1
        for i, (name, c1_hex, c2_hex, c3_hex) in enumerate(_THEME_PRESETS):
            if (_hex_to_rgb(c1_hex) == c1_curr and 
                _hex_to_rgb(c2_hex) == c2_curr and 
                _hex_to_rgb(c3_hex) == c3_curr):
                matched_idx = i
                break

        def swatch_css(hex_val):
            return f"background-color: {hex_val}; border: 1px solid #555; border-radius: 3px;"

        btn_group = widget.findChild(QtWidgets.QButtonGroup, "cpPresetButtonGroup")
        if not btn_group:
            btn_group = QtWidgets.QButtonGroup(widget)
            btn_group.setObjectName("cpPresetButtonGroup")

        btn_group.setExclusive(False)

        for i, (name, c1, c2, c3) in enumerate(_THEME_PRESETS):
            idx_str = f"{i:02d}"
            rb = widget.findChild(QtWidgets.QRadioButton, f"radioButton_{idx_str}")
            if rb:
                if btn_group.id(rb) == -1:
                    btn_group.addButton(rb, i)
                rb.setText(name)
                rb.setFixedWidth(240)
                rb.setChecked(i == matched_idx)
                if not getattr(rb, "_cpDirtyHooked", False):
                    rb._cpDirtyHooked = True
                    rb.clicked.connect(lambda checked=False, w=widget: setattr(w, "_cpPendingChange", True))

            colors = [c1, c2, c3]
            for c_idx, hex_code in enumerate(colors, start=1):
                lbl_box = widget.findChild(QtWidgets.QLabel, f"label_r{idx_str}_c{c_idx}")
                if lbl_box:
                    lbl_box.setStyleSheet(swatch_css(hex_code))
                    lbl_box.setFixedSize(24, 16)
                    lbl_box.setText("")
                
                lbl_txt = widget.findChild(QtWidgets.QLabel, f"label_r{idx_str}_t{c_idx}")
                if lbl_txt:
                    lbl_txt.setText(hex_code)
                    lbl_txt.setStyleSheet("color: #ccc; font-family: monospace; font-size: 11px;")

        btn_group.setExclusive(True)

        def _uncheck_presets_on_custom_change():
            if getattr(widget, "_internal_updating", False):
                return
            widget._cpPendingChange = True
            btn_group.setExclusive(False)
            for i in range(len(_THEME_PRESETS)):
                rb = widget.findChild(QtWidgets.QRadioButton, f"radioButton_{i:02d}")
                if rb:
                    rb.setChecked(False)
            btn_group.setExclusive(True)
            p = FreeCAD.ParamGet(_PARAM_PATH)
            p.SetInt("SelectedPreset", -1)

        widget._cpUncheckPresets = _uncheck_presets_on_custom_change

        for child in widget.findChildren(QtWidgets.QWidget):
            if getattr(child, "_cpSignalHooked", False):
                continue
            
            child_name = child.objectName()
            if child_name.startswith("radioButton_") or child_name.startswith("swatch_"):
                continue

            child._cpSignalHooked = True
            for sig_name in ("colorChanged", "changed", "colorPicked", "textEdited", "valueChanged"):
                if hasattr(child, sig_name):
                    try:
                        getattr(child, sig_name).connect(lambda *a: _uncheck_presets_on_custom_change())
                    except Exception:
                        pass
            
            if isinstance(child, (QtWidgets.QPushButton, QtWidgets.QToolButton)) and not isinstance(child, QtWidgets.QRadioButton):
                try:
                    child.clicked.connect(lambda *a: _uncheck_presets_on_custom_change())
                except Exception:
                    pass

    def _save_dialog(widget):
        for key, label, default_hex in _FONT_COLOR_PARAMS:
            swatch = widget.findChild(QtWidgets.QLabel, f"swatch_{key}")
            if swatch:
                text_val = swatch.property("hex_value")
                if text_val:
                    _apply_font_color(key, text_val)

        any_checked = False
        for i in range(len(_THEME_PRESETS)):
            idx_str = f"{i:02d}"
            rb = widget.findChild(QtWidgets.QRadioButton, f"radioButton_{idx_str}")
            if rb and rb.isChecked():
                widget._internal_updating = True
                _apply_selected_theme_preset(i)
                widget._internal_updating = False
                any_checked = True
                break
        
        if not any_checked:
            p = FreeCAD.ParamGet(_PARAM_PATH)
            p.SetInt("SelectedPreset", -1)
            _force_reload_stylesheet()

        _refresh_open_theme_editor()
        widget._cpPendingChange = False

    def _hook_widget(widget):
        try:
            if getattr(widget, "_cpHooked", False):
                return
            if widget.findChild(QtWidgets.QGroupBox, "groupBox_themePresets") is None:
                return

            widget._cpHooked = True
            _init_dialog(widget)
            _build_font_colors_group(widget)

            parent_dlg = widget.window()
            if parent_dlg:
                def _iter_view_texts(view):
                    model = view.model()
                    if model is None:
                        return
                    try:
                        for row in range(model.rowCount()):
                            idx = model.index(row, 0)
                            text = model.data(idx, QtCore.Qt.DisplayRole)
                            if text is not None:
                                yield str(text).strip()
                    except Exception:
                        return

                category_view = None
                for view in parent_dlg.findChildren(QtWidgets.QAbstractItemView):
                    texts = list(_iter_view_texts(view))
                    if category_view is None and "ColorPalette" in texts:
                        category_view = view

                def _current_category_text():
                    try:
                        idx = category_view.currentIndex()
                        if not idx.isValid():
                            return None
                        model = category_view.model()
                        text = model.data(idx, QtCore.Qt.DisplayRole)
                        return str(text).strip() if text is not None else None
                    except RuntimeError:
                        return None

                button_box = parent_dlg.findChild(QtWidgets.QDialogButtonBox)
                if button_box and not getattr(button_box, "_cpApplyHooked", False):
                    button_box._cpApplyHooked = True
                    def _on_button_clicked(button):
                        role = button_box.buttonRole(button)
                        if role in (QtWidgets.QDialogButtonBox.ApplyRole, QtWidgets.QDialogButtonBox.AcceptRole):
                            try:
                                current_text = _current_category_text() if category_view is not None else None
                                if current_text is not None:
                                    on_colorpalette = (current_text == "ColorPalette")
                                else:
                                    on_colorpalette = getattr(widget, "_cpPendingChange", False)
                                if on_colorpalette:
                                    _save_dialog(widget)
                            except RuntimeError:
                                pass
                    button_box.clicked.connect(_on_button_clicked)
        except RuntimeError:
            pass

    def _install_watcher():
        app = QtWidgets.QApplication.instance()
        if not app:
            QtCore.QTimer.singleShot(500, _install_watcher)
            return

        class ColorPaletteWatcher(QtCore.QObject):
            def eventFilter(self, obj, event):
                if event.type() == QtCore.QEvent.Show and isinstance(obj, QtWidgets.QWidget):
                    if not getattr(obj, "_cpHooked", False):
                        class_name = obj.metaObject().className()
                        obj_name = obj.objectName()
                        if "Preference" in class_name or "Dlg" in class_name or "Page" in class_name or "ColorPalette" in obj_name:
                            if obj.findChild(QtWidgets.QGroupBox, "groupBox_themePresets") is not None:
                                QtCore.QTimer.singleShot(50, lambda o=obj: _hook_widget(o))
                return False

        if not hasattr(app, "_colorPaletteWatcher"):
            watcher = ColorPaletteWatcher(app)
            app.installEventFilter(watcher)
            app._colorPaletteWatcher = watcher

    QtCore.QTimer.singleShot(1000, _install_watcher)

def _register_colorpalette_page():
    try:
        import FreeCADGui as Gui
    except ImportError:
        return

    ui_path = _find_ui_file()
    if not ui_path:
        return

    try:
        from PySide.QtCore import QT_TRANSLATE_NOOP
    except ImportError:
        def QT_TRANSLATE_NOOP(context, text):
            return text

    try:
        Gui.addPreferencePage(ui_path, QT_TRANSLATE_NOOP("QObject", "ColorPalette"))
    except Exception:
        pass

if __name__ == "__main__" or __name__ == "colorpalette_theme_presets":
    _register_colorpalette_page()
    _bootstrap_dialog_hook()