

import FreeCAD
import FreeCADGui as Gui

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

try:
    from shiboken6 import isValid as _is_valid
except ImportError:
    try:
        from shiboken2 import isValid as _is_valid
    except ImportError:
        def _is_valid(obj):
            try:
                obj.objectName()
                return True
            except RuntimeError:
                return False

# ---------------------------------------------------------------- ayarlar
POPUP_WIDTH = 380
POPUP_HEIGHT = 560
POPUP_MIN_W = 260          
POPUP_MIN_H = 60
GRIP = 6                  
_SIZE_GRP = "User parameter:BaseApp/Preferences/Mod/ColorPaletteState"
ROW_GAP = 6                
TAB_VIEW, TAB_DATA = 0, 1 
TEXT_VIEW = "View"
TEXT_DATA = "Data"
MENU_TEXT_DATA = "Property Editor - Data"   
MENU_TEXT_VIEW = "Property Editor - View"
REFRESH_MS = 50           
MENU_ARM_MS = 1500       
MENU_ARM_HOLD_MS = 8000 
MENU_ARM_TREE_MS = 3000 
MENU_ACTION_NAME = "cpPropertyAction" 


ENGINE_PARAM = "PropertyEngine"
ENGINE_COLORPALETTE = "ColorPalette"
ENGINE_DEFAULT = ENGINE_COLORPALETTE


def _engine_is_colorpalette():
    try:
        grp = FreeCAD.ParamGet(_SIZE_GRP)
        return grp.GetString(ENGINE_PARAM, ENGINE_DEFAULT) == ENGINE_COLORPALETTE
    except Exception:
        return False


def _log(msg):
    FreeCAD.Console.PrintError(f"ColorPalette: colorpalette_property - {msg}\n")


def _dbg(msg):

    try:
        if FreeCAD.ParamGet(_SIZE_GRP).GetBool("DebugMenu", False):
            FreeCAD.Console.PrintMessage(f"ColorPalette: menu - {msg}\n")
    except Exception:
        pass


def _menu_has_ours(menu):
    try:
        names = {a.text() for a in menu.actions() if a.objectName() == MENU_ACTION_NAME}
        return MENU_TEXT_DATA in names and MENU_TEXT_VIEW in names
    except Exception:
        return False


def _menu_qualifies(menu):

    try:
        if not isinstance(menu, QtWidgets.QMenu):
            return False
        parent = menu.parentWidget()
        if isinstance(parent, QtWidgets.QMenuBar):
            return False
        return True
    except (RuntimeError, Exception):
        return False


def _event_pos(ev):
    try:
        return ev.position().toPoint()
    except AttributeError:
        return ev.pos()


def _global_pos(ev):
    try:
        return ev.globalPosition().toPoint()
    except AttributeError:
        return ev.globalPos()


def _same_index(a, b):
    if a is None or b is None:
        return a is None and b is None
    return a == b


# ---------------------------------------------------------------- bulucular
def _find_tree(mw):
    for t in mw.findChildren(QtWidgets.QTreeWidget):
        try:
            if t.metaObject().className() == "Gui::TreeWidget":
                return t
        except Exception:
            pass
    for d in mw.findChildren(QtWidgets.QDockWidget):
        if d.objectName() in ("Tree view", "Combo View"):
            t = d.findChild(QtWidgets.QTreeWidget)
            if t:
                return t
    return None


def _find_property_view(mw):
    tab = mw.findChild(QtWidgets.QTabWidget, "propertyTab")
    if tab is not None and tab.parentWidget() is not None:
        return tab.parentWidget()
    for d in mw.findChildren(QtWidgets.QDockWidget):
        if d.objectName() == "Property view":
            w = d.widget()
            if w:
                return w
    for w in mw.findChildren(QtWidgets.QWidget):
        try:
            if w.metaObject().className() == "Gui::PropertyView":
                return w
        except Exception:
            pass
    return None


def _has_preselection():
    try:
        p = Gui.Selection.getPreselection()
        return bool(p is not None and getattr(p, "ObjectName", ""))
    except Exception:
        return False


# ---------------------------------------------------------------- ikonlar
def _make_icon(kind, color):
    pm = QtGui.QPixmap(32, 32)
    pm.fill(QtCore.Qt.transparent)
    pm.setDevicePixelRatio(2.0)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    pen = QtGui.QPen(color)
    pen.setWidthF(1.4)
    p.setPen(pen)
    if kind == "view":      # goz
        p.setBrush(QtCore.Qt.NoBrush)
        path = QtGui.QPainterPath()
        path.moveTo(1.5, 8)
        path.quadTo(8, 1, 14.5, 8)
        path.quadTo(8, 15, 1.5, 8)
        p.drawPath(path)
        p.setBrush(color)
        p.drawEllipse(QtCore.QPointF(8, 8), 2.2, 2.2)
    else:                   # data: nokta + cizgi satirlari
        p.setBrush(color)
        for y in (4, 8, 12):
            p.drawEllipse(QtCore.QPointF(2.6, y), 1.0, 1.0)
            p.drawLine(QtCore.QPointF(6, y), QtCore.QPointF(14.5, y))
    p.end()
    return QtGui.QIcon(pm)


# ---------------------------------------------------------------- satir butonlari
class _StateButton(QtWidgets.QToolButton):
    """Checkable ama tiklayinca kendiliginden toggle olmaz: durumu (checked) yalnizca
    denetleyici yonetir. Boylece popup acikken View/Data butonu QSS'ten :checked ile
    boyanabilir.  QSS:  QToolButton#cpRowDataButton:checked { ... }"""

    def nextCheckState(self):
        pass


class _ButtonBox:

    def __init__(self, owner, selected):
        self.owner = owner
        self.index = None           # en son yerlestirildigi satir (0. sutun)
        frame = QtWidgets.QFrame(owner.vp)
        frame.setObjectName("cpRowButtons")
        frame.setProperty("cpSelected", bool(selected))     
        frame.setAttribute(QtCore.Qt.WA_StyledBackground, True)  
        lay = QtWidgets.QHBoxLayout(frame)
        lay.setContentsMargins(2, 0, 2, 0)
        lay.setSpacing(2)
        self.frame = frame

        col = owner.tree.palette().color(QtGui.QPalette.Text)
        self.btn_view = self._make_button(lay, "view", "cpRowViewButton", col, TAB_VIEW,
                                          "View properties")
        self.btn_data = self._make_button(lay, "data", "cpRowDataButton", col, TAB_DATA,
                                          "Data properties")
        frame.adjustSize()
        frame.hide()

    def _make_button(self, layout, kind, name, color, tab, tip):
        b = _StateButton(self.frame)
        b.setObjectName(name)
        b.setCheckable(True)         # QSS: :checked  (popup acikken aktif buton)
        b.setAutoRaise(True)
        b.setIconSize(QtCore.QSize(16, 16))
        b.setToolTip(tip)
        # Ikon QSS'ten (qproperty-icon) gelebilir; gelmediyse yerlesik ikon kullanilir.
        b.ensurePolished()
        if b.icon().isNull():
            b.setIcon(_make_icon(kind, color))
        b.setCursor(QtCore.Qt.PointingHandCursor)
        b.clicked.connect(lambda _=False, t=tab: self.owner.clicked(self, t))
        layout.addWidget(b)
        return b

    def owns(self, w):
        return w is self.frame or self.frame.isAncestorOf(w)

    def set_active(self, tab):
        """Popup'ta acik olan sekmenin butonunu checked yapar (tab=None: hicbiri)."""
        try:
            self.btn_view.setChecked(tab == TAB_VIEW)
            self.btn_data.setChecked(tab == TAB_DATA)
        except RuntimeError:
            pass

    def invalidate(self):
        self.index = None         

    def hide(self):
        if self.frame.isVisible():
            self.frame.hide()
        self.index = None

    def place(self, idx):
        fr = self.frame
        if self.index is not None and idx == self.index and fr.isVisible():
            return                
        owner = self.owner
        rect = owner.tree.visualRect(idx)
        # kapali ust dugum altinda (rect bos) veya gorunum disinda ise gosterme
        if rect.isNull() or rect.bottom() < 0 or rect.top() > owner.vp.height():
            self.hide()
            return
        fr.adjustSize()                                 
        x = rect.left() + owner.content_width(idx) + ROW_GAP
        x = max(0, min(x, owner.vp.width() - fr.width() - 2))
        y = rect.top() + (rect.height() - fr.height()) // 2
        fr.move(x, y)
        self.index = idx
        if not fr.isVisible():
            fr.show()
            fr.raise_()


class _RowButtons(QtCore.QObject):

    def __init__(self, tree, on_click, on_context, on_dead=None, parent=None):
        super().__init__(parent if parent is not None else tree)
        self.tree = tree
        self.vp = tree.viewport()
        self.on_click = on_click
        self.on_context = on_context
        self.on_dead = on_dead     # agac silinince (dock <-> overlay) cagrilir
        self._dead_notified = False
        self._enabled = False
        self._hover = None         
        self._hover_y = None        
        self._sel = None 
        self._suppress_hover_until_move = False

        self.sel_box = _ButtonBox(self, True)
        self.hover_box = _ButtonBox(self, False)

        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(REFRESH_MS)
        self._timer.timeout.connect(self._do_refresh)

    # -- agac omru
    def alive(self):
        return _is_valid(self.tree) and _is_valid(self.vp)

    def _handle_dead(self):
        self._enabled = False
        try:
            self._timer.stop()
        except RuntimeError:
            pass
        if self.on_dead is not None and not self._dead_notified:
            self._dead_notified = True
            QtCore.QTimer.singleShot(0, self.on_dead)

    # -- ac / kapat
    def enable(self):
        if self._enabled:
            return
        if not self.alive():
            self._handle_dead()
            return
        self._enabled = True
        self.vp.setMouseTracking(True)
        self.vp.installEventFilter(self)
        self._connect(True)
        self._timer.start()       

    def disable(self):
        if not self._enabled:
            return
        self._enabled = False
        try:
            self._timer.stop()
        except RuntimeError:
            pass
        if self.alive():
            self._connect(False)
            self.vp.removeEventFilter(self)
            try:
                self.sel_box.hide()
                self.hover_box.hide()
            except RuntimeError:
                pass
        self._hover = self._hover_y = self._sel = None

    def _connect(self, on):
        tree = self.tree
        model = tree.model()
        pairs = [
            (tree.itemSelectionChanged, self._on_selection),
            (tree.verticalScrollBar().valueChanged, self._on_moved),
            (tree.expanded, self._on_moved),
            (tree.collapsed, self._on_moved),
        ]
        if model is not None:
            pairs += [
                (model.rowsInserted, self._on_struct),
                (model.rowsRemoved, self._on_struct),
                (model.rowsMoved, self._on_struct),
                (model.layoutChanged, self._on_struct),
                (model.modelReset, self._on_struct),
            ]
        sm = tree.selectionModel()
        if sm is not None:
            pairs.append((sm.selectionChanged, self._on_selection))
        for sig, slot in pairs:
            try:
                if on:
                    sig.connect(slot)
                else:
                    sig.disconnect(slot)
            except Exception:
                pass

    def owns(self, w):
        return self.sel_box.owns(w) or self.hover_box.owns(w)

    def set_active_tab(self, tab):
        self.sel_box.set_active(tab)
        self.hover_box.set_active(None)

    # -- sinyal yakalayicilari (hepsi hafif: sadece zamanlayiciyi baslatir)
    def _on_selection(self, *_):
        if not self._enabled:
            return
        try:
            if self._selected_anchor() is None:
                self._suppress_hover_until_move = True
                self._hover = self._hover_y = None
                self.sel_box.hide()
                self.hover_box.hide()
        except RuntimeError:
            pass
        self._timer.start()                   

    def _on_moved(self, *_):
        if not self._enabled:
            return
        try:
            self._hover = self._hover_y = None
            self.sel_box.hide()
            self.hover_box.hide()
            self._timer.start()
        except RuntimeError:
            pass                            

    def _on_struct(self, *_):
        if not self._enabled or self._timer.isActive():
            return
        try:
            if self.sel_box.frame.isVisible() or self.hover_box.frame.isVisible():
                self.sel_box.invalidate()
                self.hover_box.invalidate()
                self._timer.start()
        except RuntimeError:
            pass                             

    # -- hesaplama
    def _object_index(self, idx):
        if idx is None or not idx.isValid() or not idx.parent().isValid():
            return None
        return self.tree.model().index(idx.row(), 0, idx.parent())

    def _selected_anchor(self):
        tree = self.tree
        sm = tree.selectionModel()
        if sm is None or not sm.hasSelection():
            return None
        cur = tree.currentIndex()
        if cur.isValid() and sm.isSelected(cur):
            obj = self._object_index(cur)
            if obj is not None:
                return obj
        sel = sm.selection()
        for i in range(min(len(sel), 8)):       # ilk birkac aralik yeterli
            obj = self._object_index(sel[i].topLeft())
            if obj is not None:
                return obj
        return None

    def content_width(self, idx):
        try:
            opt = QtWidgets.QStyleOptionViewItem()
            opt.initFrom(self.tree)
            opt.widget = self.tree
            isz = self.tree.iconSize()
            if not isz.isValid():
                m = self.tree.style().pixelMetric(QtWidgets.QStyle.PM_SmallIconSize)
                isz = QtCore.QSize(m, m)
            opt.decorationSize = isz
            w = self.tree.itemDelegate().sizeHint(opt, idx).width()
            if w > 0:
                return w
        except Exception:
            pass
        # yedek: yaklasik hesap
        fm = QtGui.QFontMetrics(self.tree.font())
        text = idx.data(QtCore.Qt.DisplayRole) or ""
        w = fm.horizontalAdvance(str(text)) + 8
        if idx.data(QtCore.Qt.DecorationRole) is not None:
            w += self.tree.iconSize().width() + 4 if self.tree.iconSize().isValid() else 20
        return w

    # -- yerlestirme
    def _do_refresh(self):
        if not self._enabled:
            return
        if not self.alive():
            self._handle_dead()
            return
        self.sel_box.invalidate()
        self.hover_box.invalidate()
        self._sel = self._selected_anchor()
        if self._suppress_hover_until_move:
            self._hover = self._hover_y = None
        elif self.vp.underMouse():
            pos = self.vp.mapFromGlobal(QtGui.QCursor.pos())
            self._hover = self._object_index(self.tree.indexAt(pos))
            self._hover_y = None
        else:
            self._hover = None
        self._apply_sel()
        self._apply_hover()

    def _apply_sel(self):
        if self._sel is not None:
            self.sel_box.place(self._sel)
        else:
            self.sel_box.hide()

    def _apply_hover(self):
        if self._hover is not None and not _same_index(self._hover, self._sel):
            self.hover_box.place(self._hover)
        else:
            self.hover_box.hide()

    # -- fare
    def _on_move(self, pos):
        if self._suppress_hover_until_move:
            self._suppress_hover_until_move = False
            self._hover = self._hover_y = None
        y = pos.y()
        hy = self._hover_y
        if hy is not None and hy[0] <= y < hy[1]:
            return                              # ayni satir: ucuz cikis
        idx = self.tree.indexAt(pos)
        if idx.isValid():
            r = self.tree.visualRect(idx)
            self._hover_y = (r.top(), r.bottom() + 1)
        else:
            self._hover_y = None
        hov = self._object_index(idx)
        if _same_index(hov, self._hover):
            return
        self._hover = hov
        self._apply_hover()

    def _on_leave(self):
        # fare butonlarin uzerindeyken de vp "underMouse" sayilir
        if self.vp.underMouse():
            return
        self._hover = self._hover_y = None
        self.hover_box.hide()

    def _context_pos(self, ev):
        try:
            return _event_pos(ev)
        except Exception:
            return self.vp.mapFromGlobal(QtGui.QCursor.pos())

    def eventFilter(self, obj, ev):
        if obj is not self.vp:
            return False
        t = ev.type()
        if t == QtCore.QEvent.MouseMove:
            self._on_move(_event_pos(ev))
        elif t == QtCore.QEvent.Leave:
            QtCore.QTimer.singleShot(0, self._on_leave)
        elif t == QtCore.QEvent.Resize:
            self._on_moved()
        elif t == QtCore.QEvent.ContextMenu:
            self.on_context(self._context_pos(ev))
        elif t == QtCore.QEvent.MouseButtonPress and ev.button() == QtCore.Qt.RightButton:
            # ContextMenu olayi her durumda (or. butonlarin ustunde) gelmeyebilir: sag tus
            # basilirken de menuyu bekleyen kanca kurulur
            self.on_context(_event_pos(ev), True)
        return False

    def clicked(self, box, tab):
        idx = box.index
        if idx is None or not idx.isValid():
            return
        rect = self.tree.visualRect(idx)
        gy = self.vp.mapToGlobal(QtCore.QPoint(0, rect.top())).y()
        self.on_click(self.tree, idx, tab, gy)


# ---------------------------------------------------------------- 3B gorunumde sag tik
class _ViewRightClick:

    def __init__(self, mw, on_right_click):
        self.mw = mw
        self.on_right_click = on_right_click
        self._view = None
        self._cb_id = None
        self._mdi = None
        self._cb = self._callback     

    def enable(self):
        if self._mdi is None:
            self._mdi = self.mw.findChild(QtWidgets.QMdiArea)
            if self._mdi is not None:
                self._mdi.subWindowActivated.connect(self._sync)
        self._sync()

    def disable(self):
        if self._mdi is not None:
            try:
                self._mdi.subWindowActivated.disconnect(self._sync)
            except Exception:
                pass
            self._mdi = None
        self._detach()

    def _detach(self):
        if self._view is not None and self._cb_id is not None:
            try:
                self._view.removeEventCallback("SoMouseButtonEvent", self._cb_id)
            except Exception:
                pass
        self._view = None
        self._cb_id = None

    def _sync(self, *_):
        view = None
        try:
            doc = Gui.activeDocument()
            view = doc.activeView() if doc else None
        except Exception:
            view = None
        if view is not None and not hasattr(view, "addEventCallback"):
            view = None               
        if view is self._view:
            return
        self._detach()
        if view is None:
            return
        try:
            self._cb_id = view.addEventCallback("SoMouseButtonEvent", self._cb)
            self._view = view
        except Exception:
            self._cb_id = None
            self._view = None

    def _callback(self, info):
        try:
            state = info.get("State")
            if state not in ("DOWN", "UP"):
                return
            button = info.get("Button")
            _dbg(f"3D mouse callback: state={state}, button={button!r}")
            if button not in ("BUTTON2", "BUTTON3", 2, 3):
                return
            self.on_right_click(state)
        except Exception:
            pass


# ---------------------------------------------------------------- sag tik menusu kancasi
class _MenuInjector(QtCore.QObject):

    def __init__(self, on_menu):
        super().__init__()
        self._on_menu = on_menu
        self._armed = False
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.disarm)

    def arm(self, ms):
        if not self._armed:
            self._armed = True
            QtWidgets.QApplication.instance().installEventFilter(self)
        self._timer.start(ms)
        _dbg(f"armed ({ms} ms)")
        QtCore.QTimer.singleShot(0, self._check_open)

    def _check_open(self):
        if not self._armed:
            return
        m = QtWidgets.QApplication.activePopupWidget()
        if m is not None and _menu_qualifies(m):
            _dbg("menu was already open when armed")
            self._armed_menu(m)

    def disarm(self):
        self._timer.stop()
        if self._armed:
            self._armed = False
            try:
                QtWidgets.QApplication.instance().removeEventFilter(self)
            except Exception:
                pass

    def eventFilter(self, obj, ev):
        if ev.type() == QtCore.QEvent.Show and isinstance(obj, QtWidgets.QMenu):
            if _menu_qualifies(obj):
                _dbg(f"root menu shown: parent={type(obj.parentWidget()).__name__ if obj.parentWidget() else 'None'}, actions={len(obj.actions())}")
                self._armed_menu(obj)
            else:
                _dbg("menu shown but skipped (menubar/submenu)")
        return False

    def _armed_menu(self, menu):
        try:
            for delay in (0, 40, 120, 250):
                QtCore.QTimer.singleShot(delay, lambda m=menu: self._inject_if_alive(m))
        except Exception as e:
            _log(f"menu injection scheduling failed - {e}")

    def _inject_if_alive(self, menu):
        try:
            if menu is None or not menu.isVisible():
                return
            self._on_menu(menu)
        except RuntimeError:
            return
        except Exception as e:
            _log(f"menu injection failed - {e}")


# ---------------------------------------------------------------- yardimcilar
def _find_property_editors(pv):
    views = pv.findChildren(QtWidgets.QTreeView)
    found = []
    for v in views:
        try:
            if "PropertyEditor" in v.metaObject().className():
                found.append(v)
        except Exception:
            pass
    return found or list(views)


# ---------------------------------------------------------------- acilir panel
class _Grip(QtWidgets.QWidget):

    _CURSORS = {
        "l": QtCore.Qt.SizeHorCursor, "r": QtCore.Qt.SizeHorCursor,
        "b": QtCore.Qt.SizeVerCursor,
        "lb": QtCore.Qt.SizeBDiagCursor, "rb": QtCore.Qt.SizeFDiagCursor,
    }

    def __init__(self, popup, edges):
        super().__init__(popup)
        self.popup = popup
        self.edges = edges
        self._start = None
        self.setObjectName("cpPropertyPopupGrip")
        self.setCursor(self._CURSORS[edges])

    def mousePressEvent(self, ev):
        if ev.button() == QtCore.Qt.LeftButton:
            self._start = (_global_pos(ev), self.popup.geometry())
            ev.accept()

    def mouseMoveEvent(self, ev):
        if self._start is None:
            return
        gp, g0 = self._start
        now = _global_pos(ev)
        self.popup.apply_resize(g0, self.edges, now.x() - gp.x(), now.y() - gp.y())

    def mouseReleaseEvent(self, ev):
        if self._start is not None:
            self._start = None
            self.popup.save_size()


class _PropertyPopup(QtWidgets.QFrame):

    closed = QtCore.Signal()

    def __init__(self, mw):
        super().__init__(mw)
        self.mw = mw
        self.pv = None
        self._origin = None
        self._tab_name = ""
        self._pv_saved = None
        self._fit_tabs = None    
        self._vscroll_policies = [] 
        self._proxy_bound = None   
        self._proxy_lock = False
        self._fit_views = []
        self._fit_timer = QtCore.QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.setInterval(20)
        self._fit_timer.timeout.connect(self.fit_height)

        grp = FreeCAD.ParamGet(_SIZE_GRP)
        self._size = QtCore.QSize(grp.GetInt("PopupWidth", POPUP_WIDTH),
                                  grp.GetInt("PopupHeight", POPUP_HEIGHT))

        self.setObjectName("cpPropertyPopup")
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet(
            "#cpPropertyPopup, #cpPropertyPopupHeader, #cpPropertyPopupTitle"
            "{background: transparent; border: none;}")

        self.setMinimumSize(POPUP_MIN_W, POPUP_MIN_H)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)

        head = QtWidgets.QWidget(self)
        head.setObjectName("cpPropertyPopupHeader")
        head.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        head.setAutoFillBackground(False)
        hl = QtWidgets.QHBoxLayout(head)
        hl.setContentsMargins(8, 4, 8, 4)
        self.title = QtWidgets.QLabel("", head)
        self.title.setObjectName("cpPropertyPopupTitle")
        f = self.title.font()
        f.setBold(True)
        self.title.setFont(f)
        self.title.setMinimumWidth(0)
        self.title.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        close = QtWidgets.QToolButton(head)
        close.setObjectName("cpPropertyPopupClose")
        close.setAutoRaise(True)
        close.setToolTip("Close")
        close.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        close.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_TitleBarCloseButton))
        close.clicked.connect(self.detach)
        hl.addWidget(self.title, 1)
        hl.addWidget(close)
        root.addWidget(head)

        self.body_frame = QtWidgets.QFrame(self)
        self.body_frame.setObjectName("cpPropertyPopupBody")
        self.body_frame.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.body_frame.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.body_frame.setMinimumSize(0, 0)
        self.body = QtWidgets.QVBoxLayout(self.body_frame)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(0)
        self.body.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)

        row = QtWidgets.QWidget(self)
        row.setObjectName("cpPropertyPopupRow")
        row.setAttribute(QtCore.Qt.WA_StyledBackground, False)
        row.setMinimumSize(0, 0)
        rl = QtWidgets.QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
        rl.addWidget(self.body_frame, 1)
        root.addWidget(row, 1)

        self.proxy_bar = QtWidgets.QScrollBar(QtCore.Qt.Vertical, row)
        self.proxy_bar.setObjectName("propertyEditorProxyScrollBar")
        self.proxy_bar.hide()
        rl.addWidget(self.proxy_bar)

        self._grips = [_Grip(self, e) for e in ("l", "r")]
        self.hide()

    # -- boyutlandirma
    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        w, h, g = self.width(), self.height(), GRIP
        geo = {
            "l": (0, 0, g, h - g), "r": (w - g, 0, g, h - g),
            "b": (g, h - g, w - 2 * g, g),
            "lb": (0, h - g, g, g), "rb": (w - g, h - g, g, g),
        }
        for gr in self._grips:
            gr.setGeometry(*geo[gr.edges])
            gr.raise_()

    def apply_resize(self, g0, edges, dx, dy):
        mw = self.mw
        w, h = g0.width(), g0.height()
        if "r" in edges:
            w = g0.width() + dx
        if "l" in edges:
            w = g0.width() - dx
        if "b" in edges:
            h = g0.height() + dy
        graph_h = self._graph_rect().height()
        w = max(min(POPUP_MIN_W, mw.width() - 8), min(w, mw.width() - 8))
        h = max(min(POPUP_MIN_H, graph_h), min(h, graph_h))
        x = g0.x()
        if "l" in edges:
            x = g0.right() + 1 - w      
        x = max(4, min(x, mw.width() - w - 4))
        self.setGeometry(x, g0.y(), w, h)

    def save_size(self):
        self._size = QtCore.QSize(self.width(), self.height())
        try:
            grp = FreeCAD.ParamGet(_SIZE_GRP)
            grp.SetInt("PopupWidth", self.width())
            grp.SetInt("PopupHeight", self.height())
        except Exception:
            pass

    # -- PropertyView tasima
    def _tabs(self):
        return self.pv.findChild(QtWidgets.QTabWidget) if self.pv is not None else None

    def attach(self, pv):
        if self.pv is not None and pv.parentWidget() is self:
            return True
        parent = pv.parentWidget()
        if isinstance(parent, QtWidgets.QDockWidget):
            self._origin = ("dock", parent, 0)
        elif isinstance(parent, QtWidgets.QSplitter):
            self._origin = ("splitter", parent, parent.indexOf(pv))
        elif parent is not None and parent.layout() is not None:
            self._origin = ("layout", parent, parent.layout().indexOf(pv))
        else:
            _log("Property view is inside an unexpected container and could not be moved.")
            return False
        self.pv = pv
        self._pv_saved = (pv.minimumSize(), pv.maximumSize(), pv.sizePolicy())
        pv.setMinimumSize(1, 1)
        pv.setMaximumSize(16777215, 16777215)
        pv.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
        self.body.insertWidget(0, pv, 1)
        pv.show()
        self._repolish(pv)          # popup'a ozel QSS (#cpPropertyPopupBody ...) uygulansin
        self._hide_native_vscroll()
        self._connect_fit()
        return True

    # -- yuksekligi satirlara gore ayarla
    def _connect_fit(self):
        self._disconnect_fit()
        if self.pv is None:
            return
        for view in _find_property_editors(self.pv):
            self._fit_views.append(view)
            for sig in (view.expanded, view.collapsed):
                sig.connect(self._schedule_fit)
            m = view.model()
            if m is not None:
                for sig in (m.rowsInserted, m.rowsRemoved, m.modelReset, m.layoutChanged):
                    sig.connect(self._schedule_fit)
        tabs = self._tabs()
        if tabs is not None:
            tabs.currentChanged.connect(self._schedule_fit)
            self._fit_tabs = tabs

    @staticmethod
    def _safe_disconnect(sig, slot):
        try:
            sig.disconnect(slot)
        except (RuntimeError, TypeError):
            pass

    def _disconnect_fit(self):
        views, self._fit_views = self._fit_views, []
        tabs, self._fit_tabs = self._fit_tabs, None
        for view in views:
            try:
                self._safe_disconnect(view.expanded, self._schedule_fit)
                self._safe_disconnect(view.collapsed, self._schedule_fit)
                m = view.model()
                if m is not None:
                    for sig in (m.rowsInserted, m.rowsRemoved, m.modelReset, m.layoutChanged):
                        self._safe_disconnect(sig, self._schedule_fit)
            except RuntimeError:
                pass       
        if tabs is not None:
            try:
                self._safe_disconnect(tabs.currentChanged, self._schedule_fit)
            except RuntimeError:
                pass

    @staticmethod
    def _repolish(pv):
        try:
            widgets = [pv] + pv.findChildren(QtWidgets.QWidget)
            for w in widgets:
                st = w.style()
                st.unpolish(w)
                st.polish(w)
            for view in _find_property_editors(pv):
                view.viewport().update()
        except RuntimeError:
            pass

    # -- proxy scrollbar
    def _hide_native_vscroll(self):
        if self.pv is None or self._vscroll_policies:
            return
        for view in _find_property_editors(self.pv):
            try:
                self._vscroll_policies.append((view, view.verticalScrollBarPolicy()))
                view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            except RuntimeError:
                pass

    def _restore_native_vscroll(self):
        items, self._vscroll_policies = self._vscroll_policies, []
        for view, policy in items:
            try:
                view.setVerticalScrollBarPolicy(policy)
            except RuntimeError:
                pass

    def _bind_proxy(self, view):
        bound = self._proxy_bound
        if bound is not None and bound[0] is view:
            return
        if bound is not None:
            _, vbar, from_real, to_real = bound
            try:
                self._safe_disconnect(vbar.rangeChanged, from_real)
                self._safe_disconnect(vbar.valueChanged, from_real)
            except RuntimeError:
                pass
            self._safe_disconnect(self.proxy_bar.valueChanged, to_real)
        self._proxy_bound = None
        if view is None:
            return
        vbar = view.verticalScrollBar()
        if vbar is None:
            return
        bar = self.proxy_bar

        def from_real(*_):
            if self._proxy_lock:
                return
            self._proxy_lock = True
            try:
                bar.setRange(vbar.minimum(), vbar.maximum())
                bar.setPageStep(vbar.pageStep())
                bar.setSingleStep(vbar.singleStep())
                bar.setValue(vbar.value())
            except RuntimeError:
                pass
            finally:
                self._proxy_lock = False

        def to_real(v):
            if self._proxy_lock:
                return
            self._proxy_lock = True
            try:
                vbar.setValue(v)
            except RuntimeError:
                pass
            finally:
                self._proxy_lock = False

        vbar.rangeChanged.connect(from_real)
        vbar.valueChanged.connect(from_real)
        bar.valueChanged.connect(to_real)
        self._proxy_bound = (view, vbar, from_real, to_real)
        from_real()

    def _update_proxy(self, view, needs_scroll):
        if needs_scroll and view is not None:
            self._bind_proxy(view)
        else:
            self._bind_proxy(None)
        if self.proxy_bar.isVisible() != needs_scroll:
            self.proxy_bar.setVisible(needs_scroll)

    def _schedule_fit(self, *_):
        self._fit_timer.start()

    def _current_editor(self):
        if self.pv is None:
            return None
        for v in _find_property_editors(self.pv):
            if v.isVisibleTo(self):
                return v
        return None

    @staticmethod
    def _rows_height(view):
        model = view.model()
        if model is None:
            return 0
        total = 0
        idx = model.index(0, 0)
        guard = 0
        while idx.isValid() and guard < 5000:
            total += view.rowHeight(idx)
            idx = view.indexBelow(idx)
            guard += 1
        return total

    def fit_height(self):
        if not self.isVisible() or self.pv is None:
            return
        view = self._current_editor()
        if view is None:
            return
        rows = self._rows_height(view)
        for _ in range(2):          # cerceve payi olculerek bulunur; 2. tur dogrular
            chrome = self.height() - view.viewport().height()
            max_h = max(POPUP_MIN_H, min(self._graph_rect().height(),
                                         self.mw.height() - self.y() - 4))
            h = max(POPUP_MIN_H, min(rows + chrome, max_h))
            # Icerik kullanilabilir yukseklige sigmiyorsa proxy scrollbar gerekir
            self._update_proxy(view, rows + chrome > max_h + 1)
            if h == self.height():
                break
            self.resize(self.width(), h)

    def detach(self, *_):
        self._fit_timer.stop()
        self._disconnect_fit()
        self._update_proxy(None, False)
        self._restore_native_vscroll()
        tabs = self._tabs()
        if tabs is not None:
            tabs.tabBar().show()
        self.hide()
        if self.pv is not None and self._origin:
            pv = self.pv
            kind, parent, idx = self._origin
            self.body.removeWidget(pv)
            if self._pv_saved:
                pv.setMinimumSize(self._pv_saved[0])
                pv.setMaximumSize(self._pv_saved[1])
                pv.setSizePolicy(self._pv_saved[2])
                self._pv_saved = None
            pv.hide()      # yerine donerken gorunmesin (ColorPalette motorunda panel hep gizli)
            try:
                if kind == "dock":
                    parent.setWidget(pv)
                elif kind == "splitter":
                    parent.insertWidget(idx, pv)
                else:
                    lay = parent.layout()
                    if hasattr(lay, "insertWidget"):
                        lay.insertWidget(idx, pv)
                    else:
                        lay.addWidget(pv)
            except Exception as e:
                _log(f"Property view could not be restored - {e}")
            self._repolish(pv)      # dock'taki (TabWidget) boyamasina geri don
            self.pv = None
            self._origin = None
        self.setMinimumSize(POPUP_MIN_W, POPUP_MIN_H)
        self.hide()
        self.closed.emit()

    # -- gosterme
    def _graph_rect(self):
        try:
            mdi = self.mw.findChild(QtWidgets.QMdiArea)
            sub = mdi.activeSubWindow() if mdi is not None else None
            if sub is not None and sub.isVisible():
                content = sub.widget()
                target = content if content is not None else sub
                top_left = self.mw.mapFromGlobal(target.mapToGlobal(QtCore.QPoint(0, 0)))
                rect = QtCore.QRect(top_left, target.size())
                bounds = self.mw.rect().adjusted(4, 4, -4, -4)
                rect = rect.intersected(bounds)
                if not rect.isEmpty():
                    return rect
        except Exception:
            pass
        return self.mw.rect().adjusted(4, 4, -4, -4)

    def show_at(self, tree, global_y, tab, center=False):
        tabs = self._tabs()
        if tabs is not None:
            if tabs.count() > tab:
                tabs.setCurrentIndex(tab)
            tabs.tabBar().hide()       # panelde sekme cubugu yerine baslik var
        self._tab_name = TEXT_VIEW if tab == TAB_VIEW else TEXT_DATA
        self.title.setText(self._tab_name)
        self.setProperty("cpTab", "view" if tab == TAB_VIEW else "data")   # QSS: [cpTab="data"]
        self.style().unpolish(self)
        self.style().polish(self)

        mw = self.mw
        graph = self._graph_rect()
        max_h = max(1, graph.height())
        max_w = max(1, mw.width() - 8)
        w = min(max_w, max(1, self._size.width()))
        h = max_h                      # once azami; fit_height icerige kisar
        self.setMinimumSize(min(POPUP_MIN_W, w), min(POPUP_MIN_H, h))
        self.resize(w, h)

        tl = mw.mapFromGlobal(tree.mapToGlobal(QtCore.QPoint(0, 0)))
        x = tl.x() + tree.width() + 6               
        if x + w > mw.width() - 4:                  
            x = tl.x() - w - 6
        if x < 4:
            x = max(4, mw.width() - w - 4)

        y = max(4, min(graph.top(), mw.height() - h - 4))
        self.move(x, y)
        self.show()
        self.raise_()
        self.fit_height()
        self._schedule_fit()           # layout oturduktan sonra tekrar
        QtCore.QTimer.singleShot(150, self.fit_height)

    def set_object_title(self, label):
        self.title.setText(f"{label} — {self._tab_name}")
        self._schedule_fit()


# ---------------------------------------------------------------- denetleyici
class _Controller(QtCore.QObject):
    def __init__(self, mw, tree):
        super().__init__(mw)
        self.mw = mw
        self.tree = tree
        self.popup = _PropertyPopup(mw)
        self.popup.closed.connect(self._on_closed)
        self.buttons = _RowButtons(tree, self.open_for, self._tree_context,
                                   self._on_tree_dead, mw)
        self._rebind_tries = 0
        self.view_hook = _ViewRightClick(mw, self._view_context)

        self._poll = QtCore.QTimer(self)
        self._poll.setInterval(50)
        self._poll.timeout.connect(self._poll_selection)
        self._tries = 0
        self.enabled = False
        self._active_tab = None      # popup'ta acik sekme (TAB_VIEW / TAB_DATA / None)

        # sag tik menusu takibi
        self.menu_hook = _MenuInjector(self._inject)
        self._probe_idx = None
        self._probe_gy = 0
        self._probe_source = ""

    # -- agac yeniden olusturulunca (dock <-> overlay) yeni agaca baglan
    def _on_tree_dead(self):
        self._rebind_tries = 0
        self._try_rebind()

    def _try_rebind(self):
        tree = _find_tree(self.mw)
        if tree is None or not _is_valid(tree) or tree is self.tree:
            self._rebind_tries += 1
            if self._rebind_tries < 40:                 # yeni agac hazir olana kadar bekle
                QtCore.QTimer.singleShot(250, self._try_rebind)
            else:
                _log("Tree view was re-created but the new tree could not be found.")
            return
        old = self.buttons
        try:
            old.disable()
            old.deleteLater()
        except RuntimeError:
            pass
        self.tree = tree
        self.buttons = _RowButtons(tree, self.open_for, self._tree_context,
                                   self._on_tree_dead, self.mw)
        self.buttons.set_active_tab(self._active_tab)     # yeni butonlara mevcut durumu uygula
        if self.enabled:
            self.buttons.enable()

    def _set_pv_visible(self, visible):
        pv = self.popup.pv or _find_property_view(self.mw)
        if pv is None:
            return
        parent = pv.parentWidget()
        if isinstance(parent, QtWidgets.QDockWidget):
            parent.setVisible(visible)
        else:
            pv.setVisible(visible)

    def set_enabled(self, on):
        on = bool(on)
        if on == self.enabled:
            return
        self.enabled = on
        if on:
            self.buttons.enable()
            self.view_hook.enable()
            self.mw.installEventFilter(self)   
            self._set_pv_visible(False)
        else:
            self.menu_hook.disarm()             
            self.popup.detach()
            self.buttons.disable()
            self.view_hook.disable()
            try:
                self.mw.removeEventFilter(self)
            except Exception:
                pass
            self._set_pv_visible(True)

    # -- popup acma
    def _open_popup(self, tab, global_y, center=False):
        pv = self.popup.pv or _find_property_view(self.mw)
        if pv is None:
            _log("Property view not found.")
            return False
        if not self.popup.attach(pv):
            return False
        self.popup.show_at(self.tree, global_y, tab, center)
        QtWidgets.QApplication.instance().installEventFilter(self)  
        self._active_tab = tab
        self.buttons.set_active_tab(tab)        # QSS: QToolButton#cpRowDataButton:checked
        return True

    def _start_poll(self):
        self._tries = 0
        self._poll.start()

    def _select_row(self, tree, idx):
        sm = tree.selectionModel()
        if sm.isSelected(idx):
            targets = [i for i in sm.selectedIndexes() if i.column() == 0] or [idx]
        else:
            targets = [idx]
        tree.clearSelection()
        for i in targets:
            sm.select(i, QtCore.QItemSelectionModel.Select)
        sm.setCurrentIndex(idx, QtCore.QItemSelectionModel.NoUpdate)

    def open_for(self, tree, idx, tab, global_y, center=False):
        if not self._open_popup(tab, global_y, center):
            return
        self._select_row(tree, idx)
        self._start_poll()

    def _poll_selection(self):
        self._tries += 1
        try:
            sel = Gui.Selection.getSelection()
        except Exception:
            sel = []
        if sel:
            self._poll.stop()
            label = sel[0].Label if len(sel) == 1 else f"{len(sel)} objects"
            self.popup.set_object_title(label)
        elif self._tries > 10:
            self._poll.stop()

    def _on_closed(self):
        self._active_tab = None
        try:
            self.buttons.set_active_tab(None)
        except RuntimeError:
            pass
        self._poll.stop()
        try:
            QtWidgets.QApplication.instance().removeEventFilter(self)
        except Exception:
            pass

    # -- FreeCAD sag tik menusune "Property - Data / View" ekleme
    def _tree_context(self, vp_pos, press=False):
        idx = self.tree.indexAt(vp_pos)
        if not idx.isValid() or not idx.parent().isValid():
            _dbg("tree right-click on document row / empty area: not armed")
            return 
        self._arm_probe(self.tree.model().index(idx.row(), 0, idx.parent()),
                        MENU_ARM_TREE_MS if press else MENU_ARM_MS,
                        source="tree")

    def _view_context(self, state="UP"):
        if state == "DOWN":
            self._arm_probe(None, MENU_ARM_HOLD_MS, source="view")
        else:
            self._arm_probe(None, MENU_ARM_MS, source="view")

    def _arm_probe(self, idx, ms=None, source="tree"):
        self._probe_idx = idx
        self._probe_gy = QtGui.QCursor.pos().y()
        self._probe_source = source
        self.menu_hook.arm(ms or MENU_ARM_MS)

    def _inject(self, menu):
        if not self.enabled:
            _dbg("inject skipped: controller disabled")
            return
        if self._probe_source == "view":
            try:
                selection = Gui.Selection.getSelection()
            except Exception:
                selection = []
            if not selection:
                _dbg("inject skipped: 3D View menu has no selected objects (hover only)")
                return
        if _menu_has_ours(menu):
            _dbg("inject skipped: both actions already present")
            return
        try:
            for old_action in list(menu.actions()):
                if old_action.objectName() == MENU_ACTION_NAME:
                    menu.removeAction(old_action)
        except Exception:
            pass
        idx, gy = self._probe_idx, self._probe_gy
        existing = menu.actions()
        first = existing[0] if existing else None
        box = self.buttons.sel_box
        icons = {TAB_DATA: box.btn_data.icon(), TAB_VIEW: box.btn_view.icon()}
        new = []
        for text, tab in ((MENU_TEXT_DATA, TAB_DATA), (MENU_TEXT_VIEW, TAB_VIEW)):
            act = menu.addAction(text)
            act.setObjectName(MENU_ACTION_NAME)
            act.setIcon(icons[tab])
            act.setIconVisibleInMenu(True)      # uygulama genelinde ikonlar gizlenmis olsa da goster
            act.triggered.connect(lambda _=False, t=tab: self._menu_open(t, idx, gy))
            new.append(act)
        if first is not None:
            sep = menu.addSeparator()
            sep.setObjectName(MENU_ACTION_NAME)
            new.append(sep)
        for act in new:                         # sona eklenenleri menunun en basina tasi
            menu.removeAction(act)
            menu.insertAction(first, act)
        _dbg(f"injected Property actions; menu now has {len(menu.actions())} actions")
        self._fit_menu(menu)
        _dbg(f"injected {len(new)} actions; menu now has {len(menu.actions())} actions")

    @staticmethod
    def _fit_menu(menu):
        try:
            menu.ensurePolished()
            menu.adjustSize()
            scr = QtGui.QGuiApplication.screenAt(menu.pos()) or QtGui.QGuiApplication.primaryScreen()
            ag = scr.availableGeometry()
            g = menu.frameGeometry()
            x = max(ag.left(), min(g.x(), ag.right() - g.width() + 1))
            y = max(ag.top(), min(g.y(), ag.bottom() - g.height() + 1))
            if x != g.x() or y != g.y():
                menu.move(x, y)
        except Exception:
            pass

    def _menu_open(self, tab, idx, gy):
        def _go():
            if not self.enabled:
                return
            if idx is not None and idx.isValid():
                self.open_for(self.tree, idx, tab, gy, True)   
            elif self._open_popup(tab, gy, True):
                self._start_poll()
        QtCore.QTimer.singleShot(0, _go)       

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == QtCore.QEvent.Close and obj is self.mw:
            self.popup.detach()
        elif t == QtCore.QEvent.MouseButtonPress and self.popup.isVisible():
            if not isinstance(obj, QtWidgets.QWidget):
                return False
            if obj.window() is not self.mw:
                return False
            if obj is self.popup or self.popup.isAncestorOf(obj):
                return False
            if self.buttons.owns(obj):
                return False
            self.popup.detach()
        return False


# ---------------------------------------------------------------- giris noktasi
def install(_tries=0):
    try:
        mw = Gui.getMainWindow()
    except Exception:
        mw = None

    def _retry():
        if _tries < 20:
            QtCore.QTimer.singleShot(500, lambda: install(_tries + 1))
        else:
            _log("Tree view / Property view not found, installation cancelled.")

    if mw is None:
        _retry()
        return
    if getattr(mw, "_cp_tree_prop_ctrl", None):
        return
    if not _engine_is_colorpalette():
        return    

    tree = _find_tree(mw)
    pv = _find_property_view(mw)
    if tree is None or pv is None:
        _retry()
        return

    try:
        ctrl = _Controller(mw, tree)
        mw._cp_tree_prop_ctrl = ctrl
        ctrl.set_enabled(True)
    except Exception as e:
        _log(f"installation failed - {e}")
