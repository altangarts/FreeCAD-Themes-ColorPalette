import os
import FreeCAD

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets


def _bootstrap_global_fixer():

    def _setup():
        app = QtWidgets.QApplication.instance()
        if not app:
            QtCore.QTimer.singleShot(200, _setup)
            return

        class MenuNoUnderlineStyle(QtWidgets.QProxyStyle):
            def styleHint(self, hint, option=None, widget=None, returnData=None):
                if hint == QtWidgets.QStyle.SH_UnderlineShortcut:
                    return 0
                return super().styleHint(hint, option, widget, returnData)

        class StatusBarNoFrameStyle(QtWidgets.QProxyStyle):
            def drawPrimitive(self, element, option, painter, widget=None):
                if element == QtWidgets.QStyle.PE_FrameStatusBarItem:
                    return
                super().drawPrimitive(element, option, painter, widget)

        def _style_menu_recursive(menu, proxy):
            menu.setStyle(proxy)
            for act in menu.actions():
                sub = act.menu()
                if sub:
                    _style_menu_recursive(sub, proxy)

        _STYLE_REFRESH_MS = 5000

        def _apply_scoped_styles():
            import FreeCADGui

            mw = FreeCADGui.getMainWindow()
            if not mw:
                QtCore.QTimer.singleShot(500, _apply_scoped_styles)
                return

            menu_proxy = getattr(app, "_menuNoUnderlineProxy", None)
            if menu_proxy is None:
                menu_proxy = MenuNoUnderlineStyle(mw.style())
                app._menuNoUnderlineProxy = menu_proxy

            menubar = mw.menuBar()
            if menubar and not isinstance(menubar.style(), MenuNoUnderlineStyle):
                menubar.setStyle(menu_proxy)

            if menubar:
                for action in menubar.actions():
                    menu = action.menu()
                    if menu and not isinstance(menu.style(), MenuNoUnderlineStyle):
                        _style_menu_recursive(menu, menu_proxy)

            status_proxy = getattr(app, "_statusBarNoFrameProxy", None)
            if status_proxy is None:
                status_proxy = StatusBarNoFrameStyle(mw.style())
                app._statusBarNoFrameProxy = status_proxy

            status_bar = mw.statusBar() if hasattr(mw, "statusBar") else None
            if status_bar and not isinstance(status_bar.style(), StatusBarNoFrameStyle):
                status_bar.setStyle(status_proxy)

            QtCore.QTimer.singleShot(_STYLE_REFRESH_MS, _apply_scoped_styles)

        _apply_scoped_styles()

        if hasattr(app, "_globalFreeCADFixer"):
            old_fixer = app._globalFreeCADFixer
            try:
                app.removeEventFilter(old_fixer)
            except Exception:
                pass

            for w in (getattr(old_fixer, "_filtered_toolbar", None),
                      getattr(old_fixer, "_filtered_viewport", None)):
                if w is not None:
                    try:
                        w.removeEventFilter(old_fixer)
                    except Exception:
                        pass

        class GlobalFreeCADFixer(QtCore.QObject):

            TOOLBAR_OBJECT_NAME = "Workbench"
            COMBO_OBJECT_NAME = "Gui--WorkbenchComboBox"
            COMBO_CLASS_NAMES = ("Gui::WorkbenchComboBox", "WorkbenchComboBox")
            VIEW_PROPERTY = "is_workbench_combo_view"

            def __init__(self):
                super().__init__()
                self._toolbar_pixmap_cache = {}   # id(obj) -> ((W,H), QPixmap)
                self._toolbar_combo_cache = {}    # id(obj) -> combo | False
                self._toolbar_combo_miss_count = {}  # id(obj) -> denenme sayaci
                self._view_pixmap_cache = {}      # id(obj) -> ((W,H), QPixmap)

                self._filtered_toolbar = None
                self._filtered_viewport = None
                self._cached_main_window = None

            def _forget_on_destroy(self, obj, *caches):
                key = id(obj)

                def _cleanup(_=None):
                    for c in caches:
                        c.pop(key, None)

                try:
                    obj.destroyed.connect(_cleanup)
                except Exception:
                    pass

            _COMBO_RETRY_EVERY = 5

            def _should_retry_combo(self, key):
                n = self._toolbar_combo_miss_count.get(key, 0) + 1
                self._toolbar_combo_miss_count[key] = n
                return (n % self._COMBO_RETRY_EVERY) == 1

            def _main_window(self):
                mw = self._cached_main_window
                if mw is not None:
                    try:
                        if mw.objectName() or True:  # C++ nesnesi hala yasiyor mu
                            return mw
                    except RuntimeError:
                        self._cached_main_window = None

                try:
                    import FreeCADGui
                    mw = FreeCADGui.getMainWindow()
                except Exception:
                    mw = None
                self._cached_main_window = mw
                return mw

            def _is_workbench_toolbar(self, obj):

                if obj.objectName() != self.TOOLBAR_OBJECT_NAME:
                    return False
                mw = self._main_window()
                if mw is None:
                    return False
                try:
                    return obj.window() is mw
                except Exception:
                    return False

            def _find_workbench_combo(self, toolbar):

                combo = toolbar.findChild(QtWidgets.QComboBox, self.COMBO_OBJECT_NAME)
                if combo is not None:
                    return combo

                for c in toolbar.findChildren(QtWidgets.QComboBox):
                    try:
                        cls = c.metaObject().className()
                    except Exception:
                        continue
                    if cls in self.COMBO_CLASS_NAMES:
                        return c
                return None

            def attach_to_toolbar(self, toolbar):

                if self._filtered_toolbar is toolbar:
                    return
                if self._filtered_toolbar is not None:
                    try:
                        self._filtered_toolbar.removeEventFilter(self)
                    except Exception:
                        pass
                toolbar.installEventFilter(self)
                self._filtered_toolbar = toolbar

            def attach_to_viewport(self, viewport):

                if self._filtered_viewport is viewport:
                    return
                if self._filtered_viewport is not None:
                    try:
                        self._filtered_viewport.removeEventFilter(self)
                    except Exception:
                        pass
                viewport.installEventFilter(self)
                self._filtered_viewport = viewport

            def eventFilter(self, obj, event):
                if event.type() != QtCore.QEvent.Paint:
                    return False

                if isinstance(obj, QtWidgets.QToolBar):
                    if not self._is_workbench_toolbar(obj):
                        return False
                    if self.paint_toolbar_blueprint(obj):
                        return True
                    return False

                if isinstance(obj, QtWidgets.QWidget) and \
                        obj.property(self.VIEW_PROPERTY) is True:
                    self.draw_blueprint_view(obj)
                    return False

                return False

            def draw_blueprint_view(self, obj):
                W, H = obj.width(), obj.height()
                if W <= 0 or H <= 0:
                    return

                dpr = obj.devicePixelRatioF()
                key = id(obj)
                cache_key = (W, H, dpr)
                cached = self._view_pixmap_cache.get(key)
                if cached is None or cached[0] != cache_key:
                    pix = QtGui.QPixmap(max(1, round(W * dpr)), max(1, round(H * dpr)))
                    pix.setDevicePixelRatio(dpr)
                    pix.fill(QtCore.Qt.transparent)
                    p = QtGui.QPainter(pix)
                    p.setRenderHint(QtGui.QPainter.Antialiasing)
                    self._render_blueprint(p, W, H, offset_x=0, offset_y=0,
                                            draw_gears=False, rounded=False)
                    p.end()
                    self._view_pixmap_cache[key] = (cache_key, pix)
                    self._forget_on_destroy(obj, self._view_pixmap_cache)
                else:
                    pix = cached[1]

                painter = QtGui.QPainter(obj)
                painter.drawPixmap(0, 0, pix)
                painter.end()

            def paint_toolbar_blueprint(self, obj):
                key = id(obj)

                combo = self._toolbar_combo_cache.get(key)
                need_lookup = combo is None or (combo is False and self._should_retry_combo(key))
                if need_lookup:
                    found = self._find_workbench_combo(obj)
                    combo = found if found is not None else False
                    self._toolbar_combo_cache[key] = combo
                    self._forget_on_destroy(obj, self._toolbar_combo_cache,
                                             self._toolbar_pixmap_cache,
                                             self._toolbar_combo_miss_count)

                    if combo:
                        combo.setIconSize(QtCore.QSize(21, 21))
                        combo.setMinimumWidth(170)
                        view = combo.view()
                        if view:
                            palette = view.palette()
                            palette.setColor(QtGui.QPalette.Base, QtCore.Qt.transparent)
                            palette.setColor(QtGui.QPalette.Window, QtCore.Qt.transparent)
                            view.setPalette(palette)
                            view.setAutoFillBackground(False)
                            viewport = view.viewport()
                            if viewport:
                                viewport.setProperty(self.VIEW_PROPERTY, True)
                                vp_palette = viewport.palette()
                                vp_palette.setColor(QtGui.QPalette.Base, QtCore.Qt.transparent)
                                vp_palette.setColor(QtGui.QPalette.Window, QtCore.Qt.transparent)
                                viewport.setPalette(vp_palette)
                                viewport.setAutoFillBackground(False)
                                # app-wide filtre yerine sadece bu viewport'a kur
                                self.attach_to_viewport(viewport)

                if not combo:
                    return False

                handle_extent = 0
                if obj.isMovable():
                    handle_opt = QtWidgets.QStyleOptionToolBar()
                    handle_opt.initFrom(obj)
                    handle_extent = obj.style().pixelMetric(
                        QtWidgets.QStyle.PM_ToolBarHandleExtent, handle_opt, obj)

                W = combo.geometry().right()
                H = obj.height() if obj.height() > 0 else 30
                dpr = obj.devicePixelRatioF()

                cache_key = (W, H, dpr, handle_extent)
                cached = self._toolbar_pixmap_cache.get(key)
                if cached is None or cached[0] != cache_key:
                    pix = QtGui.QPixmap(max(1, round(W * dpr)), max(1, round(H * dpr)))
                    pix.setDevicePixelRatio(dpr)
                    pix.fill(QtCore.Qt.transparent)
                    p = QtGui.QPainter(pix)
                    p.setRenderHint(QtGui.QPainter.Antialiasing)
                    self._render_blueprint(p, W, H, offset_x=1, offset_y=3,
                                            draw_gears=True, rounded=True,
                                            left_offset=handle_extent)
                    p.end()
                    self._toolbar_pixmap_cache[key] = (cache_key, pix)
                else:
                    pix = cached[1]

                painter = QtGui.QPainter(obj)
                opt = QtWidgets.QStyleOption()
                opt.initFrom(obj)
                obj.style().drawPrimitive(QtWidgets.QStyle.PE_Widget, opt, painter, obj)

                if handle_extent > 0:
                    handle_draw_opt = QtWidgets.QStyleOptionToolBar()
                    handle_draw_opt.initFrom(obj)
                    handle_draw_opt.rect = QtCore.QRect(0, 0, handle_extent, obj.height())
                    handle_draw_opt.state |= QtWidgets.QStyle.State_Enabled
                    if obj.orientation() == QtCore.Qt.Horizontal:
                        handle_draw_opt.state |= QtWidgets.QStyle.State_Horizontal
                    obj.style().drawPrimitive(QtWidgets.QStyle.PE_IndicatorToolBarHandle,
                                               handle_draw_opt, painter, obj)

                painter.drawPixmap(0, 0, pix)
                painter.end()
                return True

            def _render_blueprint(self, painter, W, H, offset_x, offset_y, draw_gears, rounded,
                                   left_offset=0):
                if rounded:
                    left_x = offset_x + left_offset
                    rect = QtCore.QRectF(left_x, offset_y,
                                          W - left_x - offset_x, H - (offset_y * 1.5))
                    clip_path = QtGui.QPainterPath()
                    clip_path.addRoundedRect(rect, 4, 4)
                    painter.setClipPath(clip_path)
                else:
                    rect = QtCore.QRectF(0, 0, W, H)

                if rounded:
                    grad = QtGui.QLinearGradient(0, offset_y, 0, H)
                    grad.setColorAt(0.0, QtGui.QColor("#1d5eb4"))
                    grad.setColorAt(1.0, QtGui.QColor("#133d73"))
                    painter.fillRect(rect, grad)
                else:
                    painter.fillRect(rect, QtGui.QColor("#133d73"))

                thin_lines = []
                thick_lines = []
                for i, x in enumerate(range(15, W, 15)):
                    target = thick_lines if (i + 1) % 4 == 0 else thin_lines
                    target.append(QtCore.QLineF(x, offset_y, x, H))

                start_y = 15 + offset_y if rounded else 15
                for i, y in enumerate(range(start_y, H, 15)):
                    target = thick_lines if (i + 1) % 2 == 0 else thin_lines
                    target.append(QtCore.QLineF(0, y, W, y))

                if thin_lines:
                    painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 45), 0.6))
                    painter.drawLines(thin_lines)
                if thick_lines:
                    painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 60), 1.0))
                    painter.drawLines(thick_lines)

                if draw_gears:
                    self._draw_gear(painter, W - 35, (H * 0.45) + offset_y, 7.5, 2.8, 12, 2.0, 15)
                    self._draw_gear(painter, W - 18, (H * 0.38) + offset_y, 6.5, 2.4, 12, 1.8, 0)
                    self._draw_gear(painter, W - 26, (H * 0.72) + offset_y, 4.5, 1.5, 8, 1.4, 22)
                    self._draw_gear(painter, W - 48, (H * 0.28) + offset_y, 4.5, 1.5, 8, 1.4, 5)

                painter.setClipping(False)
                painter.setBrush(QtCore.Qt.NoBrush)
                if rounded:
                    painter.setPen(QtGui.QPen(QtGui.QColor(250, 250, 250, 200), 1.0))
                    painter.drawRoundedRect(rect, 4, 4)

                    inner_rect = rect.adjusted(1, 1, -1, -1)
                    painter.setPen(QtGui.QPen(QtGui.QColor(24, 24, 24, 255), 2.0))
                    painter.drawRoundedRect(inner_rect, 3, 3)
                else:
                    painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 50), 1.0))
                    painter.drawLine(QtCore.QLineF(0, 0, W - 1, 0))
                    painter.drawLine(QtCore.QLineF(0, 0, 0, H - 2))
                    painter.drawLine(QtCore.QLineF(W - 1, 0, W - 1, H - 2))
                    painter.drawLine(QtCore.QLineF(0, H - 1, W - 1, H - 2))

            @staticmethod
            def _draw_gear(p, cx, cy, r_out, r_in, teeth, tooth_h, angle_start=0):
                p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 200), 0.8))
                p.drawEllipse(QtCore.QPointF(cx, cy), r_out, r_out)
                p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 130), 0.6))
                p.drawEllipse(QtCore.QPointF(cx, cy), r_in, r_in)

                p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 180), 0.8,
                                     QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
                p.save()
                p.translate(cx, cy)
                for i in range(teeth):
                    p.save()
                    p.rotate(angle_start + i * 360.0 / teeth)
                    p.drawLine(QtCore.QLineF(0, -r_out, 0, -(r_out + tooth_h)))
                    p.restore()
                p.restore()


        fixer = GlobalFreeCADFixer()
        app._globalFreeCADFixer = fixer

        def _fix():
            import FreeCADGui

            mw = FreeCADGui.getMainWindow()
            if not mw:
                QtCore.QTimer.singleShot(500, _fix)
                return

            tb = mw.findChild(QtWidgets.QToolBar, "Workbench")
            if not tb:
                QtCore.QTimer.singleShot(500, _fix)
                return

            tb.setContentsMargins(0, 0, 0, 0)
            if tb.layout():
                tb.layout().setSpacing(0)
                tb.layout().setContentsMargins(0, 0, 0, 0)

            fixer.attach_to_toolbar(tb)

            def _kick_repaint(remaining=30):
                try:
                    tb.update()
                except RuntimeError:
                    return
                if remaining > 0:
                    QtCore.QTimer.singleShot(200, lambda: _kick_repaint(remaining - 1))

            _kick_repaint()

        _fix()

    QtCore.QTimer.singleShot(1000, _setup)


if __name__ == "__main__" or __name__ == "color_palette_workbench_combobox":
    _bootstrap_global_fixer()
