# -*- coding: utf-8 -*-

import re
import time

import FreeCAD

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

try:
    import FreeCADGui as Gui
except ImportError:
    Gui = None

# Kurallar (#cpShadow...) ana qss'te tanimlidir. Iki kapi vardir:
#  - Genel stylesheet adi "ColorPalette Shadow ..." ile basliyorsa: overlay disindaki widget'lar.
#  - UYGULANMIS overlay qss "ColorPalette Shadow Overlay" ise (icinde "cpShadow" kurallari
#    vardir): overlay panel widget'lari (Gui::Overlay* ata/sinif). Parametre degil, overlay
#    konteynerinde fiilen uygulanan stylesheet metni okunur; parametre FreeCAD tarafindan
#    qss uygulandiktan SONRA yazildigi icin bir degisiklik geriden gelir.
_GENERAL_PREFIX = "colorpalette shadow"
_OVERLAY_THEME = "colorpalette shadow overlay"
_GEN_BASE = "cpShadow"
_OVL_MARKER = "cpShadow"      # Shadow Overlay qss'inin icinde gecen ayirt edici metin
_P_OVL_HOOK = "_cpShadowOvlHooked"
_P_EFFECT_OFF = "_cpShadowEffectOff"

_PARAM_PATH = "User parameter:BaseApp/Preferences/MainWindow"
_MARK = "cpShadowEffect"      
_P_HOOKED = "_cpShadowHooked"
_P_NO_SHADOW = "cpNoShadow"
_CONTEXTS = ("ToolBar", "StatusBar", "MenuBar", "Dialog", "Panel", "PropertyPopup", "MDI",
             "StartPage", "TabWidget", "Other")
_CONTEXT_BY_OBJECTNAME = {"cpPropertyPopup": "PropertyPopup", "StartView": "StartPage"}
_STACK_NAME = "qt_tabwidget_stackedwidget"
_CTX_KINDS = ("PushButton", "ToolButton", "TabBar") 
_CONTAINER_KINDS = ("Dock", "ToolBar", "Named")
_EPHEMERAL_WINDOW_TYPES = (QtCore.Qt.Popup, QtCore.Qt.ToolTip)
_GL_HINTS = ("OpenGL", "GLWidget", "View3D", "QuarterWidget")

_SHOW = QtCore.QEvent.Show
_STYLE_CHANGE = QtCore.QEvent.StyleChange
_DYN_SUFFIX = ("Widget_", "Class_", "Prop_", "Pane_")
_SHOW_DELAY_MS = 150    
_DEFER_TICK_MS = 50     
_FLUSH_BUDGET_S = 0.008 
_retry_count = [0]


# --------------------------------------------------------------------------
# Tema kontrolu
# --------------------------------------------------------------------------
def _norm(name):
    n = (name or "").strip().replace("\\", "/").split("/")[-1].lower()
    if n.endswith(".qss"):
        n = n[:-4]
    return " ".join(n.replace("_", " ").replace("-", " ").split())


def _is_overlay_shadow_active():
    """FreeCAD'in Overlay Style Sheet ayari (OverlayActiveStyleSheet) 'ColorPalette Shadow Overlay' mi?"""
    grp = FreeCAD.ParamGet(_PARAM_PATH)
    try:
        keys = list(grp.GetStrings())
    except Exception:
        keys = ["OverlayActiveStyleSheet"]
    for k in keys:
        kl = k.lower()
        if "stylesheet" in kl and "overlay" in kl:
            if _norm(grp.GetString(k, "")) == _OVERLAY_THEME:
                return True
    return False


def _is_general_shadow_active():
    """MainWindow altindaki genel *StyleSheet* anahtari 'ColorPalette Shadow ...' ile basliyor mu?
    (adinda 'overlay' gecen anahtar FreeCAD'in Overlay Style Sheet ayaridir; yok sayilir)"""
    grp = FreeCAD.ParamGet(_PARAM_PATH)
    try:
        keys = list(grp.GetStrings())
    except Exception:
        keys = ["StyleSheet"]
    for k in keys:
        kl = k.lower()
        if "stylesheet" in kl and "overlay" not in kl:
            if _norm(grp.GetString(k, "")).startswith(_GENERAL_PREFIX):
                return True
    return False


# --------------------------------------------------------------------------
# QSS kural widget'i (qproperty hedefi)
# --------------------------------------------------------------------------
class _ShadowRule(QtWidgets.QWidget):

    def __init__(self, parent, name):
        super().__init__(parent)
        self.setObjectName(name)
        self.reset()
        self.hide()

    def reset(self):
        self._enabled = -1    
        self._blur = 12
        self._dx = 0
        self._dy = 3
        self._color = QtGui.QColor(0, 0, 0, 60)

    def _get_enabled(self):
        return self._enabled

    def _set_enabled(self, v):
        self._enabled = int(v)

    def _get_blur(self):
        return self._blur

    def _set_blur(self, v):
        self._blur = int(v)

    def _get_dx(self):
        return self._dx

    def _set_dx(self, v):
        self._dx = int(v)

    def _get_dy(self):
        return self._dy

    def _set_dy(self, v):
        self._dy = int(v)

    def _get_color(self):
        return self._color

    def _set_color(self, v):
        self._color = QtGui.QColor(v)

    shadowEnabled = QtCore.Property(int, _get_enabled, _set_enabled)
    shadowBlur = QtCore.Property(int, _get_blur, _set_blur)
    shadowOffsetX = QtCore.Property(int, _get_dx, _set_dx)
    shadowOffsetY = QtCore.Property(int, _get_dy, _set_dy)
    shadowColor = QtCore.Property(QtGui.QColor, _get_color, _set_color)


def _rule_names(base):
    names = [base + "Dock", base + "ToolBar"]
    for kind in _CTX_KINDS:
        names.append(base + kind)
        for ctx in _CONTEXTS:
            names.append(base + kind + ctx)
    return names


# --------------------------------------------------------------------------
# Widget siniflandirma
# --------------------------------------------------------------------------
_TARGETS = (QtWidgets.QDockWidget, QtWidgets.QToolBar, QtWidgets.QTabBar,
            QtWidgets.QPushButton, QtWidgets.QToolButton)


def _kind(w):
    if isinstance(w, QtWidgets.QDockWidget):
        return "Dock"
    if isinstance(w, QtWidgets.QToolBar):
        return "ToolBar"
    if isinstance(w, QtWidgets.QTabBar):
        return "TabBar"
    if isinstance(w, QtWidgets.QPushButton):
        return "PushButton"
    if isinstance(w, QtWidgets.QToolButton):
        return "ToolButton"
    return None


def _context(w):
    p = w.parentWidget()
    while p is not None:
        ctx = _CONTEXT_BY_OBJECTNAME.get(p.objectName())
        if ctx is not None:
            return ctx
        if isinstance(p, QtWidgets.QMdiArea):
            return "MDI"
        if isinstance(p, QtWidgets.QStatusBar):
            return "StatusBar"
        if isinstance(p, QtWidgets.QMenuBar):
            return "MenuBar"
        if isinstance(p, QtWidgets.QToolBar):
            return "ToolBar"
        if isinstance(p, QtWidgets.QDialog):
            return "Dialog"
        if isinstance(p, QtWidgets.QDockWidget):
            return "Panel"
        p = p.parentWidget()
    return "Other"


def _in_overlay(w):
    """Widget (veya atalarindan biri) FreeCAD overlay paneline (Gui::Overlay*) ait mi?"""
    p = w
    while p is not None:
        try:
            if "Overlay" in p.metaObject().className():
                return True
        except Exception:
            pass
        p = p.parentWidget()
    return False


def _in_tabwidget(w):
    p = w.parentWidget()
    while p is not None:
        if isinstance(p, QtWidgets.QTabWidget):
            return True
        if p.isWindow():
            break
        p = p.parentWidget()
    return False


def _effect_active(e, owner=None):
    if e is None:
        return False
    try:
        return bool(e.isEnabled())
    except Exception:
        return True


def _ancestor_has_effect(w):
    p = w.parentWidget()
    while p is not None:
        if _effect_active(p.graphicsEffect(), p):
            return True
        p = p.parentWidget()
    return False


def _is_gl_widget(c):
    try:
        cn = c.metaObject().className()
    except Exception:
        return False
    for h in _GL_HINTS:
        if h in cn:
            return True
    return False


def _has_gl_child(w, gl_list=None):
    if gl_list is not None:
        for g in gl_list:
            try:
                if w.isAncestorOf(g):
                    return True
            except RuntimeError:
                pass
        return False
    for c in w.findChildren(QtWidgets.QWidget):
        if _is_gl_widget(c):
            return True
    return False


def _class_chain(w):
    out = []
    try:
        mo = w.metaObject()
        while mo is not None:
            out.append(mo.className())
            mo = mo.superClass()
    except Exception:
        pass
    return out


def _remove_effect(w):
    e = w.graphicsEffect()
    if e is not None and e.objectName() == _MARK:
        w.setGraphicsEffect(None)


# --------------------------------------------------------------------------
# Denetleyici
# --------------------------------------------------------------------------
class _ParamObserver(object):
    """Olay temelli: MainWindow parametre grubunda degisiklik olunca tetiklenir (debounce'lu)."""

    def __init__(self, callback):
        self._callback = callback

    def onChange(self, grp, reason):
        try:
            self._callback()
        except Exception:
            pass


class _RuleSet(object):
    """Bir QSS kaynaginin (genel / overlay) kural widget'lari ve cozumleme mantigi."""

    def __init__(self, base):
        self.base = base
        self.anchor = None
        self.rules = {}
        self.named = {}
        self.classes = {}
        self.props = {}
        self.panes = {}
        self.dyn = False
        self._class_cache = {}
        self._props_active = []
        p = "#" + base
        self._re = (
            re.compile(p + r"Widget_([A-Za-z0-9_\-]+)"),
            re.compile(p + r"Class_([A-Za-z0-9_\-]+)"),
            re.compile(p + r"Prop_([A-Za-z0-9\-]+)_([A-Za-z0-9_\-]+)"),
            re.compile(p + r"Pane_([A-Za-z0-9_\-]+)"),
        )

    def _alive(self):
        if self.anchor is None:
            return False
        try:
            self.anchor.objectName()
            return True
        except RuntimeError:
            return False

    def bind(self, anchor):
        """Kural widget'larini 'anchor' altina kur (qss o widget uzerinden polish edilir)."""
        if anchor is self.anchor and self._alive():
            return
        for r in self.all_rules():
            try:
                r.deleteLater()
            except RuntimeError:
                pass
        self.rules, self.named, self.classes, self.props, self.panes = {}, {}, {}, {}, {}
        self.dyn = False
        self._class_cache = {}
        self._props_active = []
        self.anchor = anchor
        if anchor is not None:
            for name in _rule_names(self.base):
                self.rules[name] = _ShadowRule(anchor, name)

    def all_rules(self):
        return (list(self.rules.values()) + list(self.named.values())
                + list(self.classes.values()) + list(self.props.values())
                + list(self.panes.values()))

    def _sync_dynamic(self, text):
        if self.anchor is None:
            return
        b = self.base
        re_n, re_c, re_p, re_t = self._re
        for obj_name in set(re_n.findall(text)):
            if obj_name not in self.named:
                self.named[obj_name] = _ShadowRule(self.anchor, b + "Widget_" + obj_name)
        for key in set(re_c.findall(text)):
            cls = key.replace("__", "::")
            if cls not in self.classes:
                self.classes[cls] = _ShadowRule(self.anchor, b + "Class_" + key)
        for prop, val in set(re_p.findall(text)):
            if (prop, val) not in self.props:
                self.props[(prop, val)] = _ShadowRule(self.anchor, b + "Prop_" + prop + "_" + val)
        for tab_name in set(re_t.findall(text)):
            if tab_name not in self.panes:
                self.panes[tab_name] = _ShadowRule(self.anchor, b + "Pane_" + tab_name)

    def read(self, text):
        """Kurallari qss'ten oku. Etkin (shadowEnabled != -1) kural sayisini dondurur."""
        count = 0
        self._sync_dynamic(text)
        for rule in self.all_rules():
            rule.reset()
            try:
                st = rule.style()
                st.unpolish(rule)
                st.polish(rule)
            except Exception:
                pass
            rule.ensurePolished()
            if rule._enabled != -1:
                count += 1
        self._class_cache = {}
        self._props_active = [(pn, pv, r) for (pn, pv), r in self.props.items()
                              if r._enabled != -1]
        self.dyn = bool(self.named or self.classes or self.props or self.panes)
        return count

    def has_enabled(self):
        return any(r._enabled > 0 for r in self.all_rules())

    def cfg(self, kind, ctx, in_tab=False):
        b = self.base
        if in_tab:
            r = self.rules.get(b + kind + "TabWidget")
            if r is not None and r._enabled != -1:
                return r if r._enabled > 0 else None
        if ctx is not None:
            r = self.rules.get(b + kind + ctx)
            if r is not None and r._enabled != -1:
                return r if r._enabled > 0 else None
        r = self.rules.get(b + kind)
        if r is not None and r._enabled > 0:
            return r
        return None

    def class_rule(self, w):
        try:
            cn0 = w.metaObject().className()
        except Exception:
            return None
        cache = self._class_cache
        if cn0 in cache:
            return cache[cn0]
        found = None
        for cn in _class_chain(w):
            r = self.classes.get(cn)
            if r is not None and r._enabled != -1:
                found = r
                break
        cache[cn0] = found
        return found

    def named_rule(self, w):
        name = w.objectName()
        if name:
            r = self.named.get(name)
            if r is not None and r._enabled != -1:
                return r
            if self.panes and name == _STACK_NAME:
                par = w.parentWidget()
                if isinstance(par, QtWidgets.QTabWidget):
                    r = self.panes.get(par.objectName())
                    if r is not None and r._enabled != -1:
                        return r
        for pn, pv, r in self._props_active:
            v = w.property(pn)
            if v is not None and str(v) == pv:
                return r
        if self.classes:
            return self.class_rule(w)
        return None


class _Controller(QtCore.QObject):
    def __init__(self, app, mw):
        super().__init__(app)
        self.app = app
        self.mw = mw
        self.active = False
        self.general_on = False
        self.overlay_on = False
        self._ovl_known = False
        self._sig = None
        self.gen = _RuleSet(_GEN_BASE)
        self.gen.bind(mw)

        # Olaylar (parametre degisimi / overlay stil degisimi) tek bir debounce'a baglanir.
        # Yoklama (polling) yok: olay gelmedikce hicbir sey calismaz.
        self._debounce = QtCore.QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(100)
        self._debounce.timeout.connect(self.refresh)
        self._observer = _ParamObserver(self._debounce.start)

        # Gecikmeli golge: id(widget) -> (widget, gosterilme zamani). Tek zamanlayici isler.
        self._pending = {}
        self._defer_timer = QtCore.QTimer(self)
        self._defer_timer.setSingleShot(True)
        self._defer_timer.setInterval(_DEFER_TICK_MS)
        self._defer_timer.timeout.connect(self._flush_pending)

    def start(self):
        try:
            FreeCAD.ParamGet(_PARAM_PATH).Attach(self._observer)
        except Exception:
            pass
        self.refresh()

    # ---- overlay qss tespiti -------------------------------------------------
    def _overlay_containers(self):
        out = []
        try:
            for w in self.mw.findChildren(QtWidgets.QTabWidget):
                if "OverlayTabWidget" in w.metaObject().className():
                    out.append(w)
                    if not w.property(_P_OVL_HOOK):
                        w.setProperty(_P_OVL_HOOK, True)
                        w.installEventFilter(self)   # yalniz StyleChange'e tepki verir
        except RuntimeError:
            pass
        return out

    def _detect_overlay(self, containers):
        """Uygulanmis overlay stylesheet 'Shadow Overlay' mi? Bilgi yoksa None."""
        seen = False
        for w in containers:
            try:
                text = w.styleSheet()
            except RuntimeError:
                continue
            if text:
                seen = True
                if _OVL_MARKER in text:
                    return True
        return False if seen else None

    # ---- FreeCAD'in kendi overlay golgesi ----------------------------------
    def _enforce_overlay_effect(self, overlay_on, containers):
        """FreeCAD'in kendi overlay golgesi (overlay qss'teki 'qproperty-enableEffect: 1').
        Qt'de qproperty degerleri qss degisince geri alinmaz; ustelik ozelligi False yapmak
        gorunen efekti hemen kaldirmaz (FreeCAD efekti ancak bir sonraki qss uygulamasinda
        yeniler). Bu yuzden hem ozellik kapatilir hem de overlay widget'larindaki FreeCAD
        efekti dogrudan devre disi birakilir; 'Shadow Overlay' donunce geri acilir."""
        for c in containers:
            try:
                if not overlay_on and c.property("enableEffect"):
                    c.setProperty("enableEffect", False)
                for w in [c] + c.findChildren(QtWidgets.QSplitter):
                    e = w.graphicsEffect()
                    if e is None or e.objectName() == _MARK:
                        continue                      # bizim efektimize dokunma
                    if overlay_on:
                        if e.property(_P_EFFECT_OFF):
                            e.setEnabled(True)
                            e.setProperty(_P_EFFECT_OFF, False)
                    elif e.isEnabled():
                        e.setEnabled(False)
                        e.setProperty(_P_EFFECT_OFF, True)
            except RuntimeError:
                pass

    # ---- etkinlestirme / kapatma -----------------------------------------
    def refresh(self):
        try:
            general_on = _is_general_shadow_active()
            containers = self._overlay_containers()
            detected = self._detect_overlay(containers)
            if detected is None:
                # Konteynerde stylesheet yok/okunamadi: ilk seferde parametreye, sonra son bilinene dayan.
                overlay_on = self.overlay_on if self._ovl_known else _is_overlay_shadow_active()
            else:
                overlay_on = detected
                self._ovl_known = True
            self._enforce_overlay_effect(overlay_on, containers)

            if not (general_on or overlay_on):
                self._sig = None
                if self.active:
                    self.active = False
                    self.general_on = False
                    self.overlay_on = False
                    self.app.removeEventFilter(self)
                    self._pending.clear()
                    self._defer_timer.stop()
                    self._clear_all()
                return

            app_ss = self.app.styleSheet()
            sig = (general_on, overlay_on, len(app_ss), hash(app_ss))
            if self.active and sig == self._sig:
                return
            self._sig = sig
            self.general_on = general_on
            self.overlay_on = overlay_on
            self.gen.read(app_ss)
            if not self.active:
                self.active = True
                self.app.installEventFilter(self)
            # Eski efekt kalmasin: agac tek gecisle temizlenip yeni kapilara gore uygulanir.
            self.resync_all(clear=True)
        except Exception as e:
            FreeCAD.Console.PrintError(f"ColorPalette Shadow: refresh hatasi - {str(e)}\n")

    def _exclusion_reason(self, w, kind, rs, gl_list=None):
        if w.property(_P_NO_SHADOW):
            return "cpNoShadow ozelligi"
        if _in_overlay(w):
            if not self.overlay_on:
                return "overlay stylesheet 'ColorPalette Shadow Overlay' degil"
        elif not self.general_on:
            return "genel stylesheet 'ColorPalette Shadow ...' degil"
        if kind in ("PushButton", "ToolButton") and w.objectName().startswith("qt_"):
            return "Qt dahili widget'i (qt_ ile baslayan objectName)"
        try:
            win = w.window()
            if win is not None and win.windowType() in _EPHEMERAL_WINDOW_TYPES:
                return "popup/tooltip penceresi"
        except Exception:
            pass
        if kind == "ToolButton" and isinstance(w.parentWidget(), QtWidgets.QTabBar):
            return "tabbar kaydirma butonu"
        if isinstance(w, (QtWidgets.QDockWidget, QtWidgets.QToolBar)) and w.isFloating():
            return "kayan (floating) dock/toolbar"
        if kind in ("Dock", "Named") and _has_gl_child(w, gl_list):
            return "icinde OpenGL/3B gorunum var"
        return None

    # ---- uygulama -----------------------------------------------------------
    def _classify(self, w):
        """(tur, named_kural, konteyner_mi, kural_kumesi). Tur None ise hedef degil."""
        kind = _kind(w)
        if kind is None and not self.gen.dyn:
            return (None, None, False, None)
        named = self.gen.named_rule(w)
        if named is not None:
            return ("Named", named, True, self.gen)
        return (kind, None, kind in ("Dock", "ToolBar"), self.gen)

    def _cfg_for(self, w, kind, named, rs):
        if kind is None:
            return None
        if kind == "Named":
            return named if named._enabled > 0 else None
        ctx = _context(w) if kind in _CTX_KINDS else None
        in_tab = (kind in _CTX_KINDS) and _in_tabwidget(w)
        return rs.cfg(kind, ctx, in_tab)

    def apply(self, w, cls=None, gl_list=None, cleanup=True):
        kind, named, _cont, rs = cls if cls is not None else self._classify(w)
        if kind is None:
            _remove_effect(w)
            return

        if self._exclusion_reason(w, kind, rs, gl_list) is not None:
            _remove_effect(w)
            return

        cfg = self._cfg_for(w, kind, named, rs)
        if cfg is None:
            _remove_effect(w)
            return

        cur = w.graphicsEffect()
        if cur is not None and cur.objectName() != _MARK:
            return                                  
        if _ancestor_has_effect(w):
            _remove_effect(w)                       
            return

        if cur is not None and not hasattr(cur, "setBlurRadius"):
            w.setGraphicsEffect(None)
            cur = None
        if cur is None:
            cur = QtWidgets.QGraphicsDropShadowEffect(w)
            cur.setObjectName(_MARK)
            w.setGraphicsEffect(cur)

        cur.setBlurRadius(cfg._blur)
        cur.setOffset(cfg._dx, cfg._dy)
        cur.setColor(cfg._color)

        if cleanup and kind in _CONTAINER_KINDS:
            for c in w.findChildren(QtWidgets.QWidget):
                _remove_effect(c)

    def _apply_items(self, items, cleanup=True, visible_only=False):
        containers = []
        leaves = []
        for w in items:
            try:
                if visible_only and not w.isVisible():
                    continue
                cls = self._classify(w)
            except RuntimeError:
                continue
            if cls[0] is None:
                continue
            (containers if cls[2] else leaves).append((w, cls))
        if not containers and not leaves:
            return

        gl_list = None
        if containers:
            gl_list = []
            for w in items:
                try:
                    if _is_gl_widget(w):
                        gl_list.append(w)
                except RuntimeError:
                    pass

        for w, cls in containers + leaves:    
            try:
                self.apply(w, cls, gl_list, cleanup)
            except RuntimeError:
                pass                         

    def _roots(self):
        roots = [self.mw]
        for t in QtWidgets.QApplication.topLevelWidgets():
            if t is self.mw or self.mw.isAncestorOf(t):
                continue
            try:
                if t.windowType() in _EPHEMERAL_WINDOW_TYPES:
                    continue
            except Exception:
                pass
            roots.append(t)
        return roots

    def resync_all(self, clear=False):
        for root in self._roots():
            items = [root] + root.findChildren(QtWidgets.QWidget)
            if clear:
                for w in items:
                    try:
                        _remove_effect(w)
                    except RuntimeError:
                        pass
            self._apply_items(items, cleanup=not clear, visible_only=True)

    def resync_subtree(self, root):
        if not self.active:
            return
        try:
            self._apply_items([root] + root.findChildren(QtWidgets.QWidget),
                              visible_only=True)
        except RuntimeError:
            pass

    def _clear_all(self):
        for root in self._roots():
            for w in [root] + root.findChildren(QtWidgets.QWidget):
                try:
                    _remove_effect(w)
                except RuntimeError:
                    pass

    # ---- yeni acilan widget'lar ------------------------------------------------
    def _hook_float_signal(self, w):
        if w.property(_P_HOOKED):
            return
        w.setProperty(_P_HOOKED, True)
        sig = getattr(w, "topLevelChanged", None)
        if sig is None:
            return

        def _on_float(*_args, _w=w):
            QtCore.QTimer.singleShot(0, lambda: self.resync_subtree(_w))

        sig.connect(_on_float)

    # ---- gecikmeli golge kuyrugu ----------------------------------------------
    def _schedule(self, w):
        self._pending[id(w)] = (w, time.monotonic())
        if not self._defer_timer.isActive():
            self._defer_timer.start()

    def _flush_pending(self):
        if not self.active:
            self._pending.clear()
            return
        now = time.monotonic()
        delay = _SHOW_DELAY_MS / 1000.0
        ready = []
        for key, (w, t) in list(self._pending.items()):
            if now - t >= delay:
                del self._pending[key]
                ready.append(w)

        containers = []
        leaves = []
        for w in ready:
            try:
                if not w.isVisible():
                    continue                     
                cls = self._classify(w)
            except RuntimeError:
                continue                         
            if cls[0] is None:
                continue
            (containers if cls[2] else leaves).append((w, cls))

        work = containers + leaves               
        deadline = time.monotonic() + _FLUSH_BUDGET_S
        for i, (w, cls) in enumerate(work):
            if i and time.monotonic() > deadline:
                for w2, _c in work[i:]:          
                    self._pending[id(w2)] = (w2, 0.0)
                break
            try:
                self.apply(w, cls)
            except RuntimeError:
                pass                            

        if self._pending:
            self._defer_timer.start()

    def eventFilter(self, obj, event):
        t = event.type()
        if t == _STYLE_CHANGE:
            # Overlay widget'inin stili degisti (overlay qss uygulandi): tek debounce'li yenileme.
            try:
                if "Overlay" in obj.metaObject().className():
                    self._debounce.start()
            except Exception:
                pass
            return False
        if t != _SHOW:
            return False
        try:
            if not isinstance(obj, QtWidgets.QWidget):
                return False
            e = obj.graphicsEffect()
            if e is not None and e.objectName() == _MARK:
                return False                    
            cls = self._classify(obj)
            if cls[0] is None:
                return False
            win = obj.window()
            if win is not None and win.windowType() in _EPHEMERAL_WINDOW_TYPES:
                return False                  
            if isinstance(obj, (QtWidgets.QDockWidget, QtWidgets.QToolBar)):
                self._hook_float_signal(obj)
            self._schedule(obj)
        except Exception:
            pass
        return False


# --------------------------------------------------------------------------
# Disa acik API
# --------------------------------------------------------------------------
def install():
    app = QtWidgets.QApplication.instance()
    mw = Gui.getMainWindow() if (Gui and app) else None
    if app is None or mw is None:
        _retry_count[0] += 1
        if _retry_count[0] < 40:
            QtCore.QTimer.singleShot(500, install)
        return
    if hasattr(app, "_cp_shadow_ctrl"):
        return
    ctrl = _Controller(app, mw)
    app._cp_shadow_ctrl = ctrl
    ctrl.start()
