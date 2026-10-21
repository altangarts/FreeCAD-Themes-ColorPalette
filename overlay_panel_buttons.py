# -*- coding: utf-8 -*-

import time

_SIDES = ("left", "right", "top", "bottom")
_RETRY_SECONDS = 2.0   # overlay bulunamazsa yeniden arama aralığı
_HIDDEN_THICKNESS = 30

_DEFAULT_SIZE = 24
_DEFAULT_MARGIN = 3
_DEFAULT_GAP = 3

# --- Panel kilitleme ---------------------------------------------------------
# Task / Model panelleri: başlangıçta overlay + transparent moda alınır,
# transparent butonu devre dışı; overlay (toggle) butonu AÇIK ve çalışır.
# Bunlar dışındaki tüm paneller: docked, yalnızca kendi overlay butonu
# devre dışı. Eşleşme dock'un objectName / windowTitle değerine göre yapılır.
# Panel adları sürüme/dile göre farklıysa debug_docks() çıktısına bakıp
# aşağıdaki listeleri düzenleyin.
_LOCK_PANELS = True
_MAX_ATTEMPTS = 3      # bir panel için en fazla mod değiştirme denemesi (döngü koruması)
_TRANSPARENT_PANELS = ("combo view", "task", "model", "tree view")
# Başlık çubuğu düğmelerini tooltip / metin / objectName içinden tanırız
_TRANSPARENT_BTN_KEYS = ("transparent", "saydam")
_OVERLAY_BTN_KEYS = ("overlay", "kaplama")


def _qt():
    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtWidgets
    return QtCore, QtWidgets


def _find_overlay(mw, QtWidgets, side):
    exact = {
        "left": "OverlayLeft",
        "right": "OverlayRight",
        "top": "OverlayTop",
        "bottom": "OverlayBottom",
    }[side]

    w = mw.findChild(QtWidgets.QWidget, exact)
    if w:
        return w

    for cand in mw.findChildren(QtWidgets.QWidget):
        try:
            cls = cand.metaObject().className()
            name = (cand.objectName() or "").lower()
        except Exception:
            continue
        if "overlaytabwidget" in cls.lower() and side in name:
            return cand
    return None


def _dock_key(dock):
    try:
        return ((dock.objectName() or "") + " " + (dock.windowTitle() or "")).lower()
    except Exception:
        return ""


def _is_transparent_panel(dock):
    key = _dock_key(dock)
    return any(k in key for k in _TRANSPARENT_PANELS)


def _dock_in_overlay(dock):
    p = dock.parentWidget()
    while p is not None:
        try:
            if "overlaytabwidget" in p.metaObject().className().lower():
                return True
        except Exception:
            pass
        p = p.parentWidget()
    return False


def _title_buttons(dock, QtWidgets):
    tb = dock.titleBarWidget()
    if tb is None:
        return []
    return tb.findChildren(QtWidgets.QAbstractButton)


def _overlay_ancestor(dock):
    p = dock.parentWidget()
    while p is not None:
        try:
            if "overlaytabwidget" in p.metaObject().className().lower():
                return p
        except Exception:
            pass
        p = p.parentWidget()
    return None


def _text_of(obj_parts):
    return " ".join(p for p in obj_parts if p).lower()


def _transparent_targets(dock, QtWidgets):
    """Transparent düğmeleri ve action'ları: dock başlığı + bağlı olduğu overlay."""
    scopes = [dock, dock.titleBarWidget(), _overlay_ancestor(dock)]
    scopes = [w for w in scopes if w is not None]
    buttons, actions = [], []
    for w in scopes:
        for b in w.findChildren(QtWidgets.QAbstractButton):
            if b not in buttons and _is_transparent_btn(b):
                buttons.append(b)
        for a in w.actions():
            txt = _text_of([a.text(), a.toolTip(), a.objectName()])
            if a not in actions and any(k in txt for k in _TRANSPARENT_BTN_KEYS):
                actions.append(a)
    for b in buttons:
        a = b.defaultAction() if hasattr(b, "defaultAction") else None
        if a is not None and a not in actions:
            actions.append(a)
    return buttons, actions


def _button_text(btn):
    parts = [btn.toolTip(), btn.text(), btn.objectName()]
    act = btn.defaultAction() if hasattr(btn, "defaultAction") else None
    if act is not None:
        parts += [act.text(), act.toolTip(), act.objectName()]
    return " ".join(p for p in parts if p).lower()


def _is_transparent_btn(btn):
    txt = _button_text(btn)
    return any(k in txt for k in _TRANSPARENT_BTN_KEYS)


def _is_overlay_btn(btn):
    txt = _button_text(btn)
    if any(k in txt for k in _TRANSPARENT_BTN_KEYS):
        return False
    return any(k in txt for k in _OVERLAY_BTN_KEYS)


def debug_docks():
    """Panel adlarını ve başlık çubuğu düğmelerini yazdırır (eşleşme ayarı için)."""
    import FreeCADGui as Gui
    QtCore, QtWidgets = _qt()
    mw = Gui.getMainWindow()
    for dock in mw.findChildren(QtWidgets.QDockWidget):
        print(
            repr(dock.objectName()), repr(dock.windowTitle()),
            "overlay=", _dock_in_overlay(dock),
            "transparent_panel=", _is_transparent_panel(dock),
        )
        ov = _overlay_ancestor(dock)
        extra = ov.findChildren(QtWidgets.QAbstractButton) if ov is not None else []
        for b in list(_title_buttons(dock, QtWidgets)) + [x for x in extra]:
            print(
                "    btn", b.metaObject().className(), repr(_button_text(b)),
                "enabled=", b.isEnabled(),
                "checkable=", b.isCheckable(),
                "checked=", b.isChecked(),
                "transparent=", _is_transparent_btn(b),
                "overlay=", _is_overlay_btn(b),
            )


def debug():
    import FreeCADGui as Gui
    QtCore, QtWidgets = _qt()
    mw = Gui.getMainWindow()

    print("--- Overlay widgets ---")
    for w in mw.findChildren(QtWidgets.QWidget):
        n = w.objectName()
        c = w.metaObject().className()
        if "overlay" in (n + c).lower():
            print(repr(n), c, "visible=", w.isVisible(), "geom=", w.geometry())

    print("--- Butons ---")
    buttons = getattr(mw, "_cp_overlay_panel_buttons", None)
    if not buttons:
        print("Butonlar kurulmamis.")
        return
    for side, b in buttons.items():
        ov = _find_overlay(mw, QtWidgets, side)
        print(
            side,
            "button_visible=", b.isVisible(),
            "pos=", b.pos(),
            "size=", (b.width(), b.height()),
            "margin=", b.cpMargin,
            "gap=", b.cpGap,
            "overlay_found=", ov is not None,
            "overlay_visible=", (ov.isVisible() if ov else None),
            "overlay_size=", ((ov.width(), ov.height()) if ov else None),
        )


def install():
    QtCore, QtWidgets = _qt()
    try:
        from PySide6 import QtGui
    except ImportError:
        from PySide2 import QtGui

    import FreeCAD
    import FreeCADGui as Gui

    app = QtWidgets.QApplication.instance()
    mw = Gui.getMainWindow()

    if not app or not mw:
        return

    if hasattr(mw, "_cp_overlay_panel_buttons"):
        return

    class _OverlayButton(QtWidgets.QToolButton):

        def __init__(self, parent, object_name, text, tooltip, command, side):
            super().__init__(parent)
            self._margin = _DEFAULT_MARGIN
            self._gap = _DEFAULT_GAP
            self._hover_icon = QtGui.QIcon()
            self._normal_icon = None  # hover sırasında saklanan normal ikon
            self._placed = False

            self.setObjectName(object_name)
            self.setText(text)
            self.setToolTip(tooltip)
            self.setAutoRaise(True)
            self.setCursor(QtCore.Qt.PointingHandCursor)
            self.setFocusPolicy(QtCore.Qt.NoFocus)
            self.setProperty("cpOverlaySide", side)
            self._command = command
            self.clicked.connect(self._run_command)
            self.hide()

        def _get_margin(self):
            return self._margin

        def _set_margin(self, value):
            self._margin = max(0, int(value))

        def _get_gap(self):
            return self._gap

        def _set_gap(self, value):
            self._gap = max(0, int(value))

        cpMargin = QtCore.Property(int, _get_margin, _set_margin)
        cpGap = QtCore.Property(int, _get_gap, _set_gap)

        def _get_icon_hover(self):
            return self._hover_icon

        def _set_icon_hover(self, icon):
            self._hover_icon = icon

        cpIconHover = QtCore.Property(QtGui.QIcon, _get_icon_hover, _set_icon_hover)

        def _swap_to_hover(self):
            if self._normal_icon is None and not self._hover_icon.isNull():
                self._normal_icon = self.icon()
                self.setIcon(self._hover_icon)

        def _restore_normal(self):
            if self._normal_icon is not None:
                self.setIcon(self._normal_icon)
                self._normal_icon = None

        def enterEvent(self, event):
            self._swap_to_hover()
            super().enterEvent(event)

        def leaveEvent(self, event):
            self._restore_normal()
            super().leaveEvent(event)

        def hideEvent(self, event):
            # Tıklayınca panel açılıp buton gizlenirse leaveEvent gelmeyebilir
            self._restore_normal()
            self._placed = False
            super().hideEvent(event)

        # -------------------------------------------------------------------
        def sizeHint(self):
            hint = super().sizeHint()
            if hint.width() <= 0 or hint.height() <= 0:
                return QtCore.QSize(_DEFAULT_SIZE, _DEFAULT_SIZE)
            return hint

        def _run_command(self):
            try:
                Gui.runCommand(self._command)
            except Exception as e:
                FreeCAD.Console.PrintError(
                    "ColorPalette: overlay butonu komutu calistirilamadi - "
                    f"{self._command}: {e}\n"
                )

        def place(self):
            p = self.parentWidget()
            cw = p.centralWidget() if p is not None else None
            if cw is None:
                return

            self.ensurePolished()
            hint = self.sizeHint()
            if self.size() != hint:
                self.resize(hint)

            origin = cw.mapTo(p, QtCore.QPoint(0, 0))
            x0, y0 = origin.x(), origin.y()
            w, h = cw.width(), cw.height()
            bw, bh = self.width(), self.height()
            margin = self._margin
            gap = self._gap
            side = self.property("cpOverlaySide")

            if side == "left":
                tx, ty = x0 + margin, y0 + margin
            elif side == "right":
                tx, ty = x0 + max(0, w - bw - margin), y0 + margin
            elif side == "top":
                left_w = buttons["left"].width() if "left" in buttons else bw
                tx, ty = x0 + margin + left_w + gap, y0 + margin
            elif side == "bottom":
                tx, ty = x0 + margin, y0 + max(0, h - bh - margin)
            else:
                return

            target = QtCore.QPoint(tx, ty)
            moved = self.pos() != target
            if moved:
                self.move(target)
            if moved or not self._placed:
                self.raise_()
                self._placed = True

    buttons = {
        "left": _OverlayButton(
            mw, "cpOverlayLeftButton", "‹",
            "show / hide", "Std_DockOverlayToggleLeft", "left",
        ),
        "right": _OverlayButton(
            mw, "cpOverlayRightButton", "›",
            "show / hide", "Std_DockOverlayToggleRight", "right",
        ),
        "top": _OverlayButton(
            mw, "cpOverlayTopButton", "⌃",
            "show / hide", "Std_DockOverlayToggleTop", "top",
        ),
        "bottom": _OverlayButton(
            mw, "cpOverlayBottomButton", "⌄",
            "show / hide", "Std_DockOverlayToggleBottom", "bottom",
        ),
    }

    class _OverlayMonitor(QtCore.QObject):
        _MW_EVENTS = (
            QtCore.QEvent.Resize,
            QtCore.QEvent.Show,
            QtCore.QEvent.LayoutRequest,
        )
        _OVERLAY_EVENTS = (
            QtCore.QEvent.Resize,
            QtCore.QEvent.Show,
            QtCore.QEvent.Hide,
            QtCore.QEvent.ChildAdded,
            QtCore.QEvent.ChildRemoved,
        )
        _DOCK_EVENTS = (
            QtCore.QEvent.Show,
            QtCore.QEvent.Hide,
            QtCore.QEvent.ChildAdded,
            QtCore.QEvent.ChildRemoved,
        )

        def __init__(self):
            super().__init__(mw)
            self._cache = {}       # side -> overlay widget
            self._retry_at = {}    # side -> monotonic zaman (bulunamadıysa)
            self._docks_at = {}    # side -> dock var mı (dock olaylarında temizlenir)
            self._scheduled = False
            self._normalized = {}  # dock -> bir kez mod düzeltmesi yapıldı mı
            self._disabled = []    # (buton, action, önceki buton/action durumu)
            self._watched = {}     # dock -> mod değiştirme deneme sayısı
            self._btn_watch = {}   # kilitli düğmeler (EnabledChange izlenir)
            self._act_watch = []   # kilitli action'lar (changed sinyali izlenir)
            self._tb_watch = {}    # dock başlık çubukları (düğmeler sonradan oluşabilir)
            self._lock_pending = False
            self._unlocking = False
            mw.installEventFilter(self)
            app.applicationStateChanged.connect(self._on_app_state)

        def _on_app_state(self, _state):
            self._schedule()

        def _schedule(self):
            if not self._scheduled:
                self._scheduled = True
                QtCore.QTimer.singleShot(0, self._flush)

        def _flush(self):
            self._scheduled = False
            self.update_all()

        def eventFilter(self, obj, event):
            t = event.type()
            if obj is mw:
                if t in self._MW_EVENTS:
                    if t == QtCore.QEvent.Show:
                        self._retry_at.clear()
                    self._schedule()
                elif t == QtCore.QEvent.ChildAdded:
                    child = event.child()
                    if child.isWidgetType():
                        if "overlay" in (child.objectName() or "").lower():
                            self._retry_at.clear()  # geç oluşan overlay'i hemen ara
                            self._schedule()
                        if _LOCK_PANELS and isinstance(child, QtWidgets.QDockWidget):
                            self._schedule_lock()
            elif obj in self._btn_watch:
                # FreeCAD düğmeyi tekrar açarsa kapat (yoklama yok, olay tabanlı)
                if (t == QtCore.QEvent.EnabledChange and not self._unlocking
                        and obj.isEnabled()):
                    obj.setEnabled(False)
            elif obj in self._watched:
                if t in (QtCore.QEvent.ParentChange, QtCore.QEvent.ChildAdded,
                         QtCore.QEvent.Show):
                    self._schedule_lock()
            elif obj in self._tb_watch:
                if t in (QtCore.QEvent.ChildAdded, QtCore.QEvent.ChildPolished,
                         QtCore.QEvent.Show, QtCore.QEvent.ShowToParent):
                    self._schedule_lock()
            elif t in self._OVERLAY_EVENTS:
                if t in self._DOCK_EVENTS:
                    self._docks_at.clear()
                    if _LOCK_PANELS:
                        self._schedule_lock()
                self._schedule()
            return False

        @staticmethod
        def _is_hidden(overlay, side):
            if not overlay.isVisible():
                return True
            if side in ("left", "right"):
                return overlay.width() <= _HIDDEN_THICKNESS
            return overlay.height() <= _HIDDEN_THICKNESS

        def _overlay(self, side):
            w = self._cache.get(side)
            if w is not None:
                try:
                    w.objectName()  # silinmişse RuntimeError fırlatır
                    return w
                except Exception:
                    self._cache.pop(side, None)

            now = time.monotonic()
            if now < self._retry_at.get(side, 0.0):
                return None

            w = _find_overlay(mw, QtWidgets, side)
            if w is None:
                self._retry_at[side] = now + _RETRY_SECONDS
                return None
            self._cache[side] = w
            self._retry_at.pop(side, None)
            w.installEventFilter(self)
            return w

        def _has_docks(self, side, overlay):
            cached = self._docks_at.get(side)
            if cached is not None:
                return cached
            result = overlay.findChild(QtWidgets.QDockWidget) is not None
            self._docks_at[side] = result
            return result

        # --- Panel kilitleme (olay tabanlı) -----------------------------------
        def _schedule_lock(self):
            if not self._lock_pending:
                self._lock_pending = True
                QtCore.QTimer.singleShot(50, self._flush_lock)

        def _flush_lock(self):
            self._lock_pending = False
            self.lock_panels()

        def _disable_action(self, act):
            if act not in self._act_watch:
                self._act_watch.append(act)
                act.changed.connect(self._on_action_changed)
            if act.isEnabled():
                act.setEnabled(False)
                self._disabled.append((None, act, False, True))

        def _on_action_changed(self):
            if self._unlocking:
                return
            for act in self._act_watch:
                try:
                    if act.isEnabled():
                        act.setEnabled(False)
                except Exception:
                    pass

        def _disable_button(self, btn, with_action=True):
            # with_action=False: yalnızca düğme widget'ı kapatılır. Overlay
            # düğmelerinin defaultAction'ı paneller arasında paylaşılabildiği
            # için action kapatılırsa Model/Task'ın düğmesi de kapanır.
            if btn not in self._btn_watch:
                self._btn_watch[btn] = True
                btn.installEventFilter(self)
            act = None
            if with_action and hasattr(btn, "defaultAction"):
                act = btn.defaultAction()
            was_btn = btn.isEnabled()
            was_act = act.isEnabled() if act is not None else False
            if was_btn:
                btn.setEnabled(False)
            if act is not None and was_act:
                act.setEnabled(False)
            if was_btn or was_act:
                self._disabled.append((btn, act, was_btn, was_act))

        def _click(self, btn):
            # Devre dışı düğme tıklanmaz; önce etkinleştirip tıklıyoruz.
            self._unlocking = True
            try:
                act = btn.defaultAction() if hasattr(btn, "defaultAction") else None
                if act is not None and not act.isEnabled():
                    act.setEnabled(True)
                if not btn.isEnabled():
                    btn.setEnabled(True)
                btn.click()
            finally:
                self._unlocking = False

        def _switch(self, dock, btn):
            n = self._watched.get(dock, 0)
            if n >= _MAX_ATTEMPTS:
                return False
            self._watched[dock] = n + 1
            self._click(btn)
            return True

        def _lock_dock(self, dock):
            if dock not in self._watched:
                self._watched[dock] = 0
                dock.installEventFilter(self)

            tb = dock.titleBarWidget()
            if tb is not None and tb not in self._tb_watch:
                self._tb_watch[tb] = True
                tb.installEventFilter(self)

            in_overlay = _dock_in_overlay(dock)
            buttons = _title_buttons(dock, QtWidgets)
            tbtns, tacts = _transparent_targets(dock, QtWidgets)
            obtns = [b for b in buttons if _is_overlay_btn(b)]

            if _is_transparent_panel(dock):
                # Task / Model: başlangıçta bir kez overlay + transparent moda
                # alınır. Sonrasında overlay butonu serbest: kullanıcı
                # istediği gibi açıp kapatabilir (geri zorlanmaz).
                if dock not in self._normalized:
                    if not in_overlay:
                        if obtns:
                            if self._switch(dock, obtns[0]):
                                return  # yeniden parent olunca olay gelir
                            self._normalized[dock] = True
                    elif tbtns:
                        t = tbtns[0]
                        if t.isCheckable() and not t.isChecked():
                            self._switch(dock, t)
                        self._normalized[dock] = True
                # Transparent butonu kilitli; overlay butonuna dokunulmaz
                for b in tbtns:
                    self._disable_button(b)
                for a in tacts:
                    self._disable_action(a)
            else:
                # Diğer paneller: docked, yalnızca kendi overlay butonu kilitli
                if in_overlay and obtns and self._switch(dock, obtns[0]):
                    return
                for b in obtns:
                    self._disable_button(b, with_action=False)

        def lock_panels(self):
            if not _LOCK_PANELS:
                return
            for dock in mw.findChildren(QtWidgets.QDockWidget):
                try:
                    self._lock_dock(dock)
                except Exception:
                    pass

        def release(self):
            """Kilitleri geri alır (uninstall)."""
            for obj in list(self._btn_watch) + list(self._watched) + list(self._tb_watch):
                try:
                    obj.removeEventFilter(self)
                except Exception:
                    pass
            for act in self._act_watch:
                try:
                    act.changed.disconnect(self._on_action_changed)
                except Exception:
                    pass
            self._act_watch.clear()
            for btn, act, was_btn, was_act in self._disabled:
                try:
                    if was_btn and btn is not None:
                        btn.setEnabled(True)
                    if act is not None and was_act:
                        act.setEnabled(True)
                except Exception:
                    pass
            self._disabled.clear()
            self._btn_watch.clear()
            self._tb_watch.clear()
            self._watched.clear()
            self._normalized.clear()

        def update_all(self):
            try:
                if not mw.isVisible() or mw.isMinimized():
                    return
                if app.applicationState() != QtCore.Qt.ApplicationActive:
                    return

                for side in _SIDES:
                    button = buttons[side]
                    overlay = self._overlay(side)

                    visible = False
                    if overlay is not None:
                        if self._is_hidden(overlay, side):
                            visible = self._has_docks(side, overlay)
                        else:
                            self._docks_at.pop(side, None)

                    if button.isVisible() != visible:
                        button.setVisible(visible)
                    if visible:
                        button.place()
            except Exception:
                pass

    monitor = _OverlayMonitor()

    mw._cp_overlay_panel_buttons = buttons
    mw._cp_overlay_panel_buttons_monitor = monitor

    monitor.update_all()
    monitor.lock_panels()


def uninstall():
    try:
        import FreeCADGui as Gui
        mw = Gui.getMainWindow()
        if not mw:
            return

        monitor = getattr(mw, "_cp_overlay_panel_buttons_monitor", None)
        if monitor:
            monitor.release()
            monitor.deleteLater()

        for button in getattr(mw, "_cp_overlay_panel_buttons", {}).values():
            button.deleteLater()

        for attr in ("_cp_overlay_panel_buttons", "_cp_overlay_panel_buttons_monitor"):
            if hasattr(mw, attr):
                delattr(mw, attr)
    except Exception:
        pass
