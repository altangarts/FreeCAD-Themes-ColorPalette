import os
import math
import FreeCAD


def _nice_step(raw_value):
    if raw_value <= 0:
        raw_value = 1e-6
    exp = math.floor(math.log10(raw_value))
    base = raw_value / (10 ** exp)
    if base < 1.5:
        nice = 1.0
    elif base < 3.5:
        nice = 2.0
    elif base < 7.5:
        nice = 5.0
    else:
        nice = 10.0
    return nice * (10 ** exp)


_GRID_PARAM_PATH = "User parameter:BaseApp/Preferences/Mod/ColorPaletteGrid"
_GRID_DEFAULT_COLOR = 0xCCCCCCFF        
_GRID_DEFAULT_AXIS_X_COLOR = 0xCC3333FF  
_GRID_DEFAULT_AXIS_Y_COLOR = 0x66B333FF  
_GRID_DEFAULT_AXIS_Z_COLOR = 0x3366CCFF  
_GRID_DEFAULT_SHOW_AXIS_X = True
_GRID_DEFAULT_SHOW_AXIS_Y = True
_GRID_DEFAULT_SHOW_AXIS_Z = True
_GRID_DEFAULT_LINE_WIDTH = 1.0
_GRID_DEFAULT_AXIS_LINE_WIDTH = 1.5
_GRID_DEFAULT_DIVISIONS = 30            
_GRID_DEFAULT_SIZE_MULTIPLIER = 20.0     
_GRID_MIN_HALF_SIZE = 100.0             
_GRID_DEFAULT_USE_FIXED_SPACING_MM = True  
_GRID_DEFAULT_SPACING_MM = 50.0         
_GRID_MAX_CELL_COUNT = 700               


def _grid_pref_group():
    return FreeCAD.ParamGet(_GRID_PARAM_PATH)


def _packed_color_to_rgb(packed):
    r = ((packed >> 24) & 0xFF) / 255.0
    g = ((packed >> 16) & 0xFF) / 255.0
    b = ((packed >> 8) & 0xFF) / 255.0
    return (r, g, b)


def _read_grid_prefs():
    grp = _grid_pref_group()
    color = _packed_color_to_rgb(grp.GetUnsigned("Color", _GRID_DEFAULT_COLOR))
    axis_x_color = _packed_color_to_rgb(grp.GetUnsigned("AxisXColor", _GRID_DEFAULT_AXIS_X_COLOR))
    axis_y_color = _packed_color_to_rgb(grp.GetUnsigned("AxisYColor", _GRID_DEFAULT_AXIS_Y_COLOR))
    axis_z_color = _packed_color_to_rgb(grp.GetUnsigned("AxisZColor", _GRID_DEFAULT_AXIS_Z_COLOR))
    show_axis_x = grp.GetBool("ShowAxisX", _GRID_DEFAULT_SHOW_AXIS_X)
    show_axis_y = grp.GetBool("ShowAxisY", _GRID_DEFAULT_SHOW_AXIS_Y)
    show_axis_z = grp.GetBool("ShowAxisZ", _GRID_DEFAULT_SHOW_AXIS_Z)
    line_width = max(grp.GetFloat("LineWidth", _GRID_DEFAULT_LINE_WIDTH), 0.1)
    axis_line_width = max(grp.GetFloat("AxisLineWidth", _GRID_DEFAULT_AXIS_LINE_WIDTH), 0.1)
    divisions = max(grp.GetInt("Divisions", _GRID_DEFAULT_DIVISIONS), 1)
    size_multiplier = max(grp.GetFloat("SizeMultiplier", _GRID_DEFAULT_SIZE_MULTIPLIER), 1.0)
    use_fixed_spacing_mm = grp.GetBool("UseFixedSpacingMm", _GRID_DEFAULT_USE_FIXED_SPACING_MM)
    spacing_mm = max(grp.GetFloat("SpacingMm", _GRID_DEFAULT_SPACING_MM), 0.01)
    return {
        "color": color,
        "axis_x_color": axis_x_color,
        "axis_y_color": axis_y_color,
        "axis_z_color": axis_z_color,
        "show_axis_x": show_axis_x,
        "show_axis_y": show_axis_y,
        "show_axis_z": show_axis_z,
        "line_width": line_width,
        "axis_line_width": axis_line_width,
        "divisions": divisions,
        "size_multiplier": size_multiplier,
        "use_fixed_spacing_mm": use_fixed_spacing_mm,
        "spacing_mm": spacing_mm,
    }


def _document_half_size(size_multiplier):
    return max(_GRID_MIN_HALF_SIZE * size_multiplier, _GRID_MIN_HALF_SIZE)


_grid_rebuild_registry = {}


def _active_doc_name(Gui):
    try:
        return Gui.ActiveDocument.Document.Name
    except Exception:
        return None


def _get_grid_rebuild(Gui, switch_node):
    doc_name = _active_doc_name(Gui)
    rebuild = _grid_rebuild_registry.get(doc_name)
    if rebuild:
        return rebuild
    return getattr(switch_node, "_grid_rebuild", None)


def _create_color_palette_grid(view, coin, doc_name=None):
    switch_node = coin.SoSwitch()
    switch_node.setName("ColorPaletteGridSwitch")

    grid_sep = coin.SoSeparator()

    pick_style = coin.SoPickStyle()
    pick_style.style.setValue(coin.SoPickStyle.UNPICKABLE)
    grid_sep.addChild(pick_style)

    draw_style = coin.SoDrawStyle()
    draw_style.lineWidth.setValue(_GRID_DEFAULT_LINE_WIDTH)
    grid_sep.addChild(draw_style)

    NUM_BANDS = 10
    MAX_SEGS_PER_LINE = 24
    MIN_SEGS_PER_LINE = 4
    # Toplam uretilen cizgi parcasi sayisini sabit bir butce icinde tutmak
    # icin, cell_count buyudukce cizgi basina segment sayisini dusuruyoruz.
    # Aksi halde spacing kucultuldugunde (cell_count -> 700 tavanina
    # carptiginda) rebuild() saf Python dongusunde onbinlerce nokta
    # hesaplayip gozle gorulur bir donme/takilma yaratabiliyordu.
    LINE_SEGMENT_BUDGET = 16000

    band_mats, band_coords, band_lines = [], [], []
    for _ in range(NUM_BANDS):
        band_sep = coin.SoSeparator()
        mat = coin.SoMaterial()
        coords = coin.SoCoordinate3()
        lines = coin.SoLineSet()
        band_sep.addChild(mat)
        band_sep.addChild(coords)
        band_sep.addChild(lines)
        grid_sep.addChild(band_sep)
        band_mats.append(mat)
        band_coords.append(coords)
        band_lines.append(lines)

    axis_group_sep = coin.SoSeparator()
    axis_draw_style = coin.SoDrawStyle()
    axis_draw_style.lineWidth.setValue(_GRID_DEFAULT_AXIS_LINE_WIDTH)
    axis_group_sep.addChild(axis_draw_style)

    x_switch = coin.SoSwitch()
    x_sep = coin.SoSeparator()
    x_mat = coin.SoMaterial()
    x_coords = coin.SoCoordinate3()
    x_lines = coin.SoLineSet()
    x_sep.addChild(x_mat)
    x_sep.addChild(x_coords)
    x_sep.addChild(x_lines)
    x_switch.addChild(x_sep)
    axis_group_sep.addChild(x_switch)

    y_switch = coin.SoSwitch()
    y_sep = coin.SoSeparator()
    y_mat = coin.SoMaterial()
    y_coords = coin.SoCoordinate3()
    y_lines = coin.SoLineSet()
    y_sep.addChild(y_mat)
    y_sep.addChild(y_coords)
    y_sep.addChild(y_lines)
    y_switch.addChild(y_sep)
    axis_group_sep.addChild(y_switch)

    z_switch = coin.SoSwitch()
    z_sep = coin.SoSeparator()
    z_mat = coin.SoMaterial()
    z_coords = coin.SoCoordinate3()
    z_lines = coin.SoLineSet()
    z_sep.addChild(z_mat)
    z_sep.addChild(z_coords)
    z_sep.addChild(z_lines)
    z_switch.addChild(z_sep)
    axis_group_sep.addChild(z_switch)

    grid_sep.addChild(axis_group_sep)

    switch_node.addChild(grid_sep)

    max_opacity = 0.4
    fade_start_ratio = 0.55
    fade_end_ratio = 1.0

    state = {
        "half_size": None, "step": None, "color": None, "line_width": None,
        "axis_x_color": None, "axis_y_color": None, "axis_z_color": None,
        "use_fixed_spacing_mm": None, "spacing_mm": None,
    }

    def _rebuild():
        prefs = _read_grid_prefs()
        base_color = prefs["color"]
        line_width = prefs["line_width"]
        axis_line_width = prefs["axis_line_width"]
        axis_x_color = prefs["axis_x_color"]
        axis_y_color = prefs["axis_y_color"]
        axis_z_color = prefs["axis_z_color"]
        show_axis_x = prefs["show_axis_x"]
        show_axis_y = prefs["show_axis_y"]
        show_axis_z = prefs["show_axis_z"]
        divisions = prefs["divisions"]
        size_multiplier = prefs["size_multiplier"]
        use_fixed_spacing_mm = prefs["use_fixed_spacing_mm"]
        spacing_mm = prefs["spacing_mm"]

        x_switch.whichChild.setValue(0 if show_axis_x else coin.SO_SWITCH_NONE)
        y_switch.whichChild.setValue(0 if show_axis_y else coin.SO_SWITCH_NONE)
        z_switch.whichChild.setValue(0 if show_axis_z else coin.SO_SWITCH_NONE)

        draw_style.lineWidth.setValue(line_width)
        axis_draw_style.lineWidth.setValue(axis_line_width)

        half_size = _document_half_size(size_multiplier)

        if use_fixed_spacing_mm:
            step = spacing_mm
        else:
            raw_step = half_size / divisions
            step = _nice_step(raw_step)

        cell_count = int(math.ceil(half_size / step))
        if cell_count > _GRID_MAX_CELL_COUNT:
            cell_count = _GRID_MAX_CELL_COUNT
            step = half_size / cell_count
        half_size = cell_count * step

        approx_line_count = max(2 * cell_count + 1, 1)
        segs_per_line = max(MIN_SEGS_PER_LINE,
                             min(MAX_SEGS_PER_LINE, LINE_SEGMENT_BUDGET // approx_line_count))
        _seg_fractions = tuple(
            (s / segs_per_line, (s + 1) / segs_per_line) for s in range(segs_per_line)
        )

        if (state["half_size"] == half_size and state["step"] == step
                and state["color"] == base_color and state["line_width"] == line_width
                and state["axis_x_color"] == axis_x_color
                and state["axis_y_color"] == axis_y_color
                and state["axis_z_color"] == axis_z_color
                and state["use_fixed_spacing_mm"] == use_fixed_spacing_mm
                and state["spacing_mm"] == spacing_mm):
            return
            
        state["half_size"] = half_size
        state["step"] = step
        state["color"] = base_color
        state["line_width"] = line_width
        state["axis_x_color"] = axis_x_color
        state["axis_y_color"] = axis_y_color
        state["axis_z_color"] = axis_z_color
        state["use_fixed_spacing_mm"] = use_fixed_spacing_mm
        state["spacing_mm"] = spacing_mm

        fade_start_dist2 = (fade_start_ratio * half_size) ** 2
        fade_end_dist2 = (fade_end_ratio * half_size) ** 2
        inv_fade_range = 1.0 / (fade_end_ratio - fade_start_ratio)
        sqrt = math.sqrt

        def _opacity_at(x, y):
            dist2 = x * x + y * y
            if dist2 <= fade_start_dist2:
                return max_opacity
            if dist2 >= fade_end_dist2:
                return 0.0
            r = sqrt(dist2) / half_size
            u = (r - fade_start_ratio) * inv_fade_range
            return max_opacity * (1.0 - (u * u * (3.0 - 2.0 * u)))

        def _add_faded_line(x0, y0, x1, y1, band_points):
            dx = x1 - x0
            dy = y1 - y0
            for t0, t1 in _seg_fractions:
                xa = x0 + dx * t0
                ya = y0 + dy * t0
                xb = x0 + dx * t1
                yb = y0 + dy * t1
                op = _opacity_at((xa + xb) * 0.5, (ya + yb) * 0.5)
                if op <= 1e-4:
                    continue
                band_idx = int((op / max_opacity) * NUM_BANDS)
                if band_idx >= NUM_BANDS:
                    band_idx = NUM_BANDS - 1
                pts = band_points[band_idx]
                pts.append((xa, ya, 0))
                pts.append((xb, yb, 0))

        band_points = [[] for _ in range(NUM_BANDS)]
        i = -cell_count
        while i <= cell_count:
            if i != 0:
                pos = i * step
                _add_faded_line(pos, -half_size, pos, half_size, band_points)
                _add_faded_line(-half_size, pos, half_size, pos, band_points)
            i += 1

        for idx in range(NUM_BANDS):
            ratio_center = (idx + 0.5) / NUM_BANDS
            transparency = 1.0 - (max_opacity * ratio_center)
            pts = band_points[idx]

            band_mats[idx].diffuseColor.setValue(*base_color)
            band_mats[idx].transparency.setValue(transparency)
            if pts:
                band_coords[idx].point.setValues(0, len(pts), pts)
                band_coords[idx].point.deleteValues(len(pts))
                band_lines[idx].numVertices.setValues(0, len(pts) // 2, [2] * (len(pts) // 2))
                band_lines[idx].numVertices.deleteValues(len(pts) // 2)
            else:
                band_coords[idx].point.deleteValues(0)
                band_lines[idx].numVertices.deleteValues(0)

        x_mat.diffuseColor.setValue(*axis_x_color)
        x_mat.transparency.setValue(0.5)
        x_coords.point.setValues(0, 2, [(-half_size, 0, 0), (half_size, 0, 0)])
        x_lines.numVertices.setValues(0, 1, [2])

        y_mat.diffuseColor.setValue(*axis_y_color)
        y_mat.transparency.setValue(0.5)
        y_coords.point.setValues(0, 2, [(0, -half_size, 0), (0, half_size, 0)])
        y_lines.numVertices.setValues(0, 1, [2])

        z_mat.diffuseColor.setValue(*axis_z_color)
        z_mat.transparency.setValue(0.5)
        z_coords.point.setValues(0, 2, [(0, 0, -half_size), (0, 0, half_size)])
        z_lines.numVertices.setValues(0, 1, [2])

    _rebuild()
    switch_node._grid_rebuild = _rebuild
    if doc_name:
        _grid_rebuild_registry[doc_name] = _rebuild
        _dbg("create: registered rebuild for doc_name=%s (registry now has keys=%s)" % (
            doc_name, list(_grid_rebuild_registry.keys())))
    else:
        _dbg("create: doc_name was falsy at creation time, NOT registered!")

    return switch_node


def _grid_preferences_ui_path():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "preferences-colorpalettegrid.ui")


_GRID_PREFS_GROUP_NAME = "ColorPalette"


def _grid_preferences_expected_icon_basename():
    normalized = "".join(
        "_" if ch == " " else ch.lower() for ch in _GRID_PREFS_GROUP_NAME
    )
    return "preferences-" + normalized


def _grid_preferences_icon_dir():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, "Resources", "icons"),
        os.path.join(base_dir, "resources", "icons"),
        base_dir,
    ]
    expected = _grid_preferences_expected_icon_basename()
    icon_names = (
        expected + ".svg",
        "preferences-colorpalette.svg",
    )
    for candidate_dir in candidates:
        for name in icon_names:
            if os.path.isfile(os.path.join(candidate_dir, name)):
                return candidate_dir
    return None


def _register_grid_preferences_page():
    try:
        import FreeCADGui as Gui
    except ImportError:
        return

    if getattr(Gui, "_colorPaletteGridPrefsLoaded", False):
        return

    ui_path = _grid_preferences_ui_path()
    if not os.path.isfile(ui_path):
        FreeCAD.Console.PrintWarning(
            "ColorPaletteGrid: tercih sayfasi dosyasi bulunamadi: %s\n" % ui_path
        )
        return

    icon_dir = _grid_preferences_icon_dir()
    if icon_dir:
        try:
            Gui.addIconPath(icon_dir)
        except Exception:
            pass

    try:
        from PySide.QtCore import QT_TRANSLATE_NOOP
    except ImportError:
        def QT_TRANSLATE_NOOP(context, text):
            return text

    try:
        Gui.addPreferencePage(ui_path, QT_TRANSLATE_NOOP("QObject", _GRID_PREFS_GROUP_NAME))
        Gui._colorPaletteGridPrefsLoaded = True
    except Exception:
        pass


_grid_refresh_debounce = {"scheduled": False}


def _schedule_grid_refresh():
    if _grid_refresh_debounce["scheduled"]:
        return
    _grid_refresh_debounce["scheduled"] = True

    def _do_refresh():
        _grid_refresh_debounce["scheduled"] = False
        _refresh_active_grid()

    try:
        from PySide6 import QtCore
    except ImportError:
        try:
            from PySide2 import QtCore
        except ImportError:
            _do_refresh()
            return
    QtCore.QTimer.singleShot(200, _do_refresh)


_grid_doc_observer = None

class _GridDocumentObserver:
    def slotRecomputedDocument(self, doc):
        pass

    def slotCreatedObject(self, obj):
        pass

    def slotDeletedObject(self, obj):
        pass

    def slotChangedObject(self, obj, prop):
        pass

    def slotDeletedDocument(self, doc):
        # Bellek sizintisini onlemek icin: dokuman kapatildiginda ona ait
        # rebuild closure'unu (ve dolayisiyla tum Coin node referanslarini)
        # kayit defterinden siliyoruz. Aksi halde bu dict, kapatilan her
        # dokuman icin sahne grafigini sonsuza dek bellekte tutardi.
        try:
            doc_name = doc.Name
        except Exception:
            doc_name = None

        if doc_name and doc_name in _grid_rebuild_registry:
            _grid_rebuild_registry.pop(doc_name, None)
            _dbg("observer: doc=%s kapandi, rebuild kaydi temizlendi (kalan keys=%s)" % (
                doc_name, list(_grid_rebuild_registry.keys())))

        _view_switch_node_cache.clear()


def _ensure_grid_document_observer():
    global _grid_doc_observer
    if _grid_doc_observer is not None:
        return
    _grid_doc_observer = _GridDocumentObserver()
    FreeCAD.addDocumentObserver(_grid_doc_observer)


def _active_doc_name_safe():
    try:
        import FreeCADGui as Gui
        return _active_doc_name(Gui)
    except Exception:
        return None


def _dbg(msg):
    if _DEBUG_GRID:
        try:
            FreeCAD.Console.PrintMessage("[GridDebug] %s\n" % msg)
        except Exception:
            pass


_DEBUG_GRID = False


def _refresh_active_grid():
    try:
        import FreeCADGui as Gui
        from pivy import coin
    except ImportError:
        _dbg("refresh: FreeCADGui/pivy import failed")
        return

    doc_name = _active_doc_name(Gui)
    _dbg("refresh: called, ActiveDocument=%s" % doc_name)

    if not Gui.ActiveDocument or not Gui.ActiveDocument.ActiveView:
        _dbg("refresh: no ActiveDocument/ActiveView -> abort")
        return
        
    if not hasattr(Gui.ActiveDocument.ActiveView, "getSceneGraph"):
        _dbg("refresh: ActiveView has no getSceneGraph -> abort")
        return

    switch_node = _find_grid_switch_node(Gui, coin)
    if not switch_node:
        _dbg("refresh: no ColorPaletteGridSwitch node found in this view's scenegraph -> abort")
        return

    _dbg("refresh: found switch_node, whichChild=%s" % switch_node.whichChild.getValue())

    if switch_node.whichChild.getValue() == coin.SO_SWITCH_NONE:
        _dbg("refresh: grid is switched OFF in this view -> abort (not rebuilding)")
        return

    rebuild = _get_grid_rebuild(Gui, switch_node)
    _dbg("refresh: rebuild function found? %s (in-registry[doc_name=%s]=%s, attr-fallback=%s, registry_keys=%s)" % (
        rebuild is not None,
        doc_name,
        doc_name in _grid_rebuild_registry,
        getattr(switch_node, "_grid_rebuild", None) is not None,
        list(_grid_rebuild_registry.keys()),
    ))
    if rebuild:
        try:
            prefs_now = _read_grid_prefs()
            _dbg("refresh: prefs at rebuild time = %s" % prefs_now)
            rebuild()
            _dbg("refresh: rebuild() executed OK")
            try:
                Gui.updateGui()
            except Exception:
                pass
        except Exception as e:
            _dbg("refresh: rebuild() raised exception: %r" % e)
    else:
        _dbg("refresh: NO rebuild function available for this switch_node -> nothing applied")


_grid_sketch_edit_state = {
    "hidden_for_edit": False,
    "was_visible_before_edit": False,
}

_grid_view_state = {
    "last_view_id": None
}

def _is_sketch_object(obj):
    if obj is None:
        return False
    type_id = getattr(obj, "TypeId", "") or ""
    return type_id.startswith("Sketcher::")


_view_switch_node_cache = {}


def _find_grid_switch_node(Gui, coin, use_cache=True):
    if not Gui.ActiveDocument or not Gui.ActiveDocument.ActiveView:
        return None

    if not hasattr(Gui.ActiveDocument.ActiveView, "getSceneGraph"):
        return None

    view = Gui.ActiveDocument.ActiveView
    view_key = id(view)

    # Her tick'te tum sahne grafigini SoSearchAction ile taramak yerine,
    # bulunan node'u view basina cache'liyoruz. View degistiginde/dokuman
    # kapandiginda cache disaridan temizleniyor (bkz. _grid_view_state ve
    # _GridDocumentObserver.slotDeletedDocument).
    if use_cache and view_key in _view_switch_node_cache:
        return _view_switch_node_cache[view_key]

    sg = view.getSceneGraph()
    search = coin.SoSearchAction()
    search.setName("ColorPaletteGridSwitch")
    search.apply(sg)
    path = search.getPath()
    node = path.getTail() if path else None

    if node is not None:
        _view_switch_node_cache[view_key] = node

    return node


def _check_sketch_edit_state():
    try:
        import FreeCADGui as Gui
        from pivy import coin
    except ImportError:
        return

    if not Gui.ActiveDocument:
        return

    try:
        edit_info = Gui.ActiveDocument.InEditInfo
    except Exception:
        edit_info = None

    edited_obj = edit_info[0] if edit_info else None
    is_editing_sketch = _is_sketch_object(edited_obj)

    entering_edit = is_editing_sketch and not _grid_sketch_edit_state["hidden_for_edit"]
    exiting_edit = not is_editing_sketch and _grid_sketch_edit_state["hidden_for_edit"]

    if not entering_edit and not exiting_edit:
        # Durum degismedi: pahali SoSearchAction taramasini atla. Bu fonksiyon
        # 250ms'lik bir zamanlayicidan surekli cagrildigi icin, sadece gercek
        # bir gecis (sketch duzenlemeye girme/cikma) oldugunda arama yapmak
        # gereksiz sahne grafigi taramalarini buyuk olcude azaltir.
        return

    switch_node = _find_grid_switch_node(Gui, coin)

    if entering_edit:
        was_visible = bool(
            switch_node is not None
            and switch_node.whichChild.getValue() != coin.SO_SWITCH_NONE
        )
        _grid_sketch_edit_state["was_visible_before_edit"] = was_visible
        _grid_sketch_edit_state["hidden_for_edit"] = True
        if was_visible:
            switch_node.whichChild.setValue(coin.SO_SWITCH_NONE)

    elif not is_editing_sketch and _grid_sketch_edit_state["hidden_for_edit"]:
        was_visible = _grid_sketch_edit_state["was_visible_before_edit"]
        _grid_sketch_edit_state["hidden_for_edit"] = False
        _grid_sketch_edit_state["was_visible_before_edit"] = False

        if not was_visible:
            return

        state_grp = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/ColorPaletteState")
        if state_grp.GetBool("GridCollapsed", True):
            return

        if switch_node is None:
            toggle_3d_grid()
            return

        if switch_node.whichChild.getValue() != 0:
            switch_node.whichChild.setValue(0)
            rebuild = _get_grid_rebuild(Gui, switch_node)
            if rebuild:
                rebuild()

def _check_active_view_changed():
    try:
        import FreeCADGui as Gui
        import FreeCAD
    except ImportError:
        return

    if not Gui.ActiveDocument or not hasattr(Gui.ActiveDocument, "ActiveView") or not Gui.ActiveDocument.ActiveView:
        if _grid_view_state["last_view_id"] is not None:
            _grid_view_state["last_view_id"] = None
        return

    current_view = Gui.ActiveDocument.ActiveView
    current_view_id = repr(current_view)

    if current_view_id != _grid_view_state["last_view_id"]:
        _grid_view_state["last_view_id"] = current_view_id
        
        if hasattr(current_view, "getSceneGraph"):
            state_grp = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/ColorPaletteState")
            is_grid_closed = state_grp.GetBool("GridCollapsed", True)
            
            if not is_grid_closed:
                try:
                    from PySide6 import QtCore
                except ImportError:
                    try:
                        from PySide2 import QtCore
                    except ImportError:
                        return
                
                QtCore.QTimer.singleShot(100, toggle_3d_grid)


def _grid_watcher_tick():
    _check_active_view_changed()
    _check_sketch_edit_state()


def _ensure_sketch_edit_watcher():
    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtWidgets

    def _install_watcher():
        app = QtWidgets.QApplication.instance()
        if not app:
            QtCore.QTimer.singleShot(500, _install_watcher)
            return

        if hasattr(app, "_gridSketchEditWatcher"):
            return

        timer = QtCore.QTimer(app)
        timer.setInterval(250)
        timer.timeout.connect(_grid_watcher_tick)
        timer.start()
        app._gridSketchEditWatcher = timer

    QtCore.QTimer.singleShot(1500, _install_watcher)


def _bootstrap_grid_prefs_dialog_hook():

    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtWidgets

    _SHOW_EVENT = QtCore.QEvent.Show

    def _is_pref_dialog(widget):
        obj_name = widget.objectName() if hasattr(widget, "objectName") else ""
        if obj_name in ("Gui::Dialog::DlgPreferencesImp", "DlgPreferencesImp"):
            return True
        if hasattr(widget, "inherits") and widget.inherits("QDialog"):
            title = (widget.windowTitle() or "").lower() if hasattr(widget, "windowTitle") else ""
            return "preferences" in title or "tercihler" in title or "ayarlar" in title
        return False

    def _hook_apply_button(dialog):
        button_box = dialog.findChild(QtWidgets.QDialogButtonBox)
        if button_box is None:
            _dbg("hook: dialog has no QDialogButtonBox -> cannot hook Apply")
            return
        if getattr(button_box, "_gridApplyHooked", False):
            _dbg("hook: button_box already hooked (id=%s), skipping re-hook" % id(button_box))
            return
        button_box._gridApplyHooked = True
        _dbg("hook: Apply/Accept button hooked on button_box id=%s" % id(button_box))

        def _on_button_clicked(button):
            role = button_box.buttonRole(button)
            _dbg("hook: dialog button clicked, role=%s" % role)
            if role in (QtWidgets.QDialogButtonBox.ApplyRole,
                        QtWidgets.QDialogButtonBox.AcceptRole):
                _dbg("hook: Apply/OK detected, scheduling _refresh_active_grid in 50ms "
                     "(ActiveDocument right now = %s)" % _active_doc_name_safe())
                QtCore.QTimer.singleShot(50, _refresh_active_grid)

        button_box.clicked.connect(_on_button_clicked)

    def _install_watcher():
        app = QtWidgets.QApplication.instance()
        if not app:
            QtCore.QTimer.singleShot(500, _install_watcher)
            return

        if hasattr(app, "_gridPrefsDialogHookWatcher"):
            return

        class GridPrefsDialogHookWatcher(QtCore.QObject):
            def eventFilter(self, obj, event):
                if event.type() == _SHOW_EVENT and _is_pref_dialog(obj):
                    QtCore.QTimer.singleShot(0, lambda o=obj: _hook_apply_button(o))
                return False

        watcher = GridPrefsDialogHookWatcher(app)
        app.installEventFilter(watcher)
        app._gridPrefsDialogHookWatcher = watcher

    QtCore.QTimer.singleShot(2000, _install_watcher)


def toggle_3d_grid(checked=None):

    _ensure_grid_document_observer()

    try:
        import FreeCADGui as Gui
        from pivy import coin
    except ImportError:
        return

    if not Gui.ActiveDocument or not Gui.ActiveDocument.ActiveView:
        return
        
    if not hasattr(Gui.ActiveDocument.ActiveView, "getSceneGraph"):
        return

    state_grp = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/ColorPaletteState")
    is_grid_closed = state_grp.GetBool("GridCollapsed", True)

    doc_name_now = _active_doc_name(Gui)
    _dbg("toggle: called for doc=%s, is_grid_closed=%s" % (doc_name_now, is_grid_closed))

    view = Gui.ActiveDocument.ActiveView
    switch_node = _find_grid_switch_node(Gui, coin)
    _dbg("toggle: existing switch_node found in this view's scenegraph? %s" % (switch_node is not None))

    if is_grid_closed:
        if switch_node and switch_node.whichChild.getValue() != coin.SO_SWITCH_NONE:
            switch_node.whichChild.setValue(coin.SO_SWITCH_NONE)
        return

    if not switch_node:
        try:
            _dbg("toggle: creating NEW grid switch node for doc=%s" % doc_name_now)
            sg = view.getSceneGraph()
            switch_node = _create_color_palette_grid(view, coin, doc_name_now)
            sg.insertChild(switch_node, 0)
            _view_switch_node_cache[id(view)] = switch_node
        except Exception as e:
            _dbg("toggle: EXCEPTION during grid creation: %r" % e)
            return

    if switch_node.whichChild.getValue() != 0:
        switch_node.whichChild.setValue(0)
        rebuild = _get_grid_rebuild(Gui, switch_node)
        _dbg("toggle: showing grid, rebuild found? %s" % (rebuild is not None))
        if rebuild:
            rebuild()


def _restore_grid_on_startup():

    try:
        from PySide6 import QtCore
    except ImportError:
        try:
            from PySide2 import QtCore
        except ImportError:
            return

    max_retries = [20]

    def _wait_for_view_and_restore():
        try:
            import FreeCADGui as Gui
            import FreeCAD
        except ImportError:
            return

        if not Gui.ActiveDocument or not Gui.ActiveDocument.ActiveView:
            max_retries[0] -= 1
            if max_retries[0] > 0:
                QtCore.QTimer.singleShot(500, _wait_for_view_and_restore)
            return

        state_grp = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/ColorPaletteState")
        is_grid_closed = state_grp.GetBool("GridCollapsed", True)

        if not is_grid_closed:
            toggle_3d_grid()

    QtCore.QTimer.singleShot(1000, _wait_for_view_and_restore)

if __name__ == "__main__" or __name__ == "colorpalette_grid":
    _register_grid_preferences_page()
    _restore_grid_on_startup()
    _ensure_sketch_edit_watcher()
    _bootstrap_grid_prefs_dialog_hook()