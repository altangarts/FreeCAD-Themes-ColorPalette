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

def _apply_font_color_param(key, hex_value):
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

def _apply_selected_theme_preset_params(selected_idx):
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
                        _update_swatch_appearance(sw, hex_val)
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
                _update_swatch_appearance(sw, target_hex)
            
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

def _has_user_made_changes(widget):
    current_preset = -1
    for i in range(len(_THEME_PRESETS)):
        idx_str = f"{i:02d}"
        rb = widget.findChild(QtWidgets.QRadioButton, f"radioButton_{idx_str}")
        if rb and rb.isChecked():
            current_preset = i
            break
    
    if current_preset != getattr(widget, "_initial_preset", -1):
        return True

    initial_fonts = getattr(widget, "_initial_fonts", {})
    for key, label, default_hex in _FONT_COLOR_PARAMS:
        swatch = widget.findChild(QtWidgets.QLabel, f"swatch_{key}")
        if swatch:
            current_hex = _normalize_hex(swatch.property("hex_value"))
            if current_hex != initial_fonts.get(key, ""):
                return True

    return False

def _init_dialog(widget):
    if getattr(widget, "_cpInitialized", False):
        return
    widget._cpInitialized = True
    widget._internal_updating = True

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

    for i, (name, c1, c2, c3) in enumerate(_THEME_PRESETS):
        idx_str = f"{i:02d}"
        rb = widget.findChild(QtWidgets.QRadioButton, f"radioButton_{idx_str}")
        if rb:
            rb.setText(name)
            rb.setFixedWidth(240)
            
            rb.blockSignals(True)
            rb.setChecked(i == matched_idx)
            rb.blockSignals(False)

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

    def _uncheck_presets_on_custom_change():
        if getattr(widget, "_internal_updating", False):
            return
        for i in range(len(_THEME_PRESETS)):
            rb = widget.findChild(QtWidgets.QRadioButton, f"radioButton_{i:02d}")
            if rb:
                rb.blockSignals(True)
                rb.setChecked(False)
                rb.blockSignals(False)
        p = FreeCAD.ParamGet(_PARAM_PATH)
        p.SetInt("SelectedPreset", -1)

    widget._cpUncheckPresets = _uncheck_presets_on_custom_change

    widget._initial_preset = matched_idx
    grp = _get_font_params_group()
    widget._initial_fonts = {}
    for key, label, default_hex in _FONT_COLOR_PARAMS:
        widget._initial_fonts[key] = _normalize_hex(grp.GetString(key, default_hex))

    widget._internal_updating = False

def _save_dialog(widget):
    if not _has_user_made_changes(widget):
        return

    for key, label, default_hex in _FONT_COLOR_PARAMS:
        swatch = widget.findChild(QtWidgets.QLabel, f"swatch_{key}")
        if swatch:
            text_val = swatch.property("hex_value")
            if text_val:
                _apply_font_color_param(key, text_val)

    current_preset = -1
    for i in range(len(_THEME_PRESETS)):
        idx_str = f"{i:02d}"
        rb = widget.findChild(QtWidgets.QRadioButton, f"radioButton_{idx_str}")
        if rb and rb.isChecked():
            current_preset = i
            break
    
    if current_preset != -1:
        _apply_selected_theme_preset_params(current_preset)
    else:
        p = FreeCAD.ParamGet(_PARAM_PATH)
        p.SetInt("SelectedPreset", -1)

    _force_reload_stylesheet()
    _refresh_open_theme_editor()

    widget._initial_preset = current_preset
    widget._initial_fonts = {}
    for key, label, default_hex in _FONT_COLOR_PARAMS:
        swatch = widget.findChild(QtWidgets.QLabel, f"swatch_{key}")
        if swatch:
            widget._initial_fonts[key] = _normalize_hex(swatch.property("hex_value"))

def _hook_widget(widget):
    try:
        if widget.findChild(QtWidgets.QGroupBox, "groupBox_themePresets") is None:
            return

        _init_dialog(widget)
        _build_font_colors_group(widget)

        button_box = None
        p = widget.parentWidget()
        while p:
            if isinstance(p, QtWidgets.QDialog):
                button_box = p.findChild(QtWidgets.QDialogButtonBox)
                if button_box:
                    break
            p = p.parentWidget()
        
        if not button_box:
            app = QtWidgets.QApplication.instance()
            if app:
                for top in app.topLevelWidgets():
                    if isinstance(top, QtWidgets.QDialog):
                        box = top.findChild(QtWidgets.QDialogButtonBox)
                        if box and top.isAncestorOf(widget):
                            button_box = box
                            break

        if button_box and not getattr(button_box, "_cpApplyHooked", False):
            button_box._cpApplyHooked = True
            def _on_button_clicked(button):
                try:
                    role = button_box.buttonRole(button)
                    if role in (QtWidgets.QDialogButtonBox.ApplyRole, QtWidgets.QDialogButtonBox.AcceptRole):
                        _save_dialog(widget)
                except RuntimeError:
                    pass
            button_box.clicked.connect(_on_button_clicked)
    except RuntimeError:
        pass

def _bootstrap_dialog_hook():
    def _install_watcher():
        app = QtWidgets.QApplication.instance()
        if not app:
            QtCore.QTimer.singleShot(500, _install_watcher)
            return

        for w in app.topLevelWidgets():
            for qbox in w.findChildren(QtWidgets.QGroupBox, "groupBox_themePresets"):
                page = qbox.parentWidget()
                while page and page.parentWidget() and not isinstance(page.parentWidget(), QtWidgets.QStackedWidget) and not isinstance(page.parentWidget(), QtWidgets.QDialog):
                    page = page.parentWidget()
                if page:
                    _hook_widget(page)

        class ColorPaletteWatcher(QtCore.QObject):
            def eventFilter(self, obj, event):
                if event.type() in (QtCore.QEvent.Show, QtCore.QEvent.WindowActivate, QtCore.QEvent.Paint) and isinstance(obj, QtWidgets.QWidget):
                    if obj.findChild(QtWidgets.QGroupBox, "groupBox_themePresets") is not None:
                        _hook_widget(obj)
                return False

        if not hasattr(app, "_colorPaletteWatcher"):
            watcher = ColorPaletteWatcher(app)
            app.installEventFilter(watcher)
            app._colorPaletteWatcher = watcher

    QtCore.QTimer.singleShot(200, _install_watcher)

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