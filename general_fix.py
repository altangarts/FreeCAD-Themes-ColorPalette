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

        class NoUnderlineStyle(QtWidgets.QProxyStyle):
            def styleHint(self, hint, option=None, widget=None, returnData=None):
                if hint == QtWidgets.QStyle.SH_UnderlineShortcut:
                    return 0
                return super().styleHint(hint, option, widget, returnData)

        current_style = app.style()
        if not isinstance(current_style, NoUnderlineStyle):
            proxy_style = NoUnderlineStyle(current_style)
            app.setStyle(proxy_style)

        if hasattr(app, "_globalFreeCADFixer"):
            try:
                app.removeEventFilter(app._globalFreeCADFixer)
            except Exception:
                pass

        class GlobalFreeCADFixer(QtCore.QObject):
            def __init__(self):
                super().__init__()
                self._debounce_timer = QtCore.QTimer()
                self._debounce_timer.setSingleShot(True)
                self._debounce_timer.setInterval(60)
                self._debounce_timer.timeout.connect(self.refresh_task_panels)

                self._toolbar_pixmap_cache = {}   # id(obj) -> ((W,H), QPixmap)
                self._toolbar_combo_cache = {}    # id(obj) -> combo | False
                self._toolbar_combo_miss_count = {}  # id(obj) -> denenme sayaci
                self._view_pixmap_cache = {}      # id(obj) -> ((W,H), QPixmap)

            def _forget_on_destroy(self, obj, *caches):
                key = id(obj)

                def _cleanup(_=None):
                    for c in caches:
                        c.pop(key, None)

                try:
                    obj.destroyed.connect(_cleanup)
                except Exception:
                    pass

            _COMBO_RETRY_EVERY = 30

            def _should_retry_combo(self, key):
                n = self._toolbar_combo_miss_count.get(key, 0) + 1
                self._toolbar_combo_miss_count[key] = n
                return (n % self._COMBO_RETRY_EVERY) == 1

            def eventFilter(self, obj, event):
                etype = event.type()

                if etype == QtCore.QEvent.Paint:
                    if isinstance(obj, QtWidgets.QToolBar):
                        if self.paint_toolbar_blueprint(obj):
                            return True
                        return False

                    if isinstance(obj, QtWidgets.QWidget) and obj.property("is_workbench_view"):
                        self.draw_blueprint_view(obj)
                        return False

                elif etype == QtCore.QEvent.Show or etype == QtCore.QEvent.DynamicPropertyChange:
                    if isinstance(obj, QtWidgets.QFrame) and obj.property("class") == "panel":
                        self._debounce_timer.start()

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
                    combo = obj.findChild(QtWidgets.QWidget, "Gui--WorkbenchComboBox")
                    if not combo:
                        combos = obj.findChildren(QtWidgets.QComboBox)
                        combo = combos[0] if combos else False
                    self._toolbar_combo_cache[key] = combo
                    self._forget_on_destroy(obj, self._toolbar_combo_cache,
                                             self._toolbar_pixmap_cache,
                                             self._toolbar_combo_miss_count)

                    if combo:
                        combo.setIconSize(QtCore.QSize(21, 21))
                        combo.setMinimumWidth(170)
                        view = combo.view()
                        if view:
                            view.viewport().setProperty("is_workbench_view", True)
                            view.setStyleSheet("background-color: transparent;")

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

                grad = QtGui.QLinearGradient(0, offset_y, 0, H)
                grad.setColorAt(0.0, QtGui.QColor("#1d5eb4"))
                grad.setColorAt(1.0, QtGui.QColor("#133d73"))
                painter.fillRect(rect, grad)

                thin_lines = []
                thick_lines = []
                for i, x in enumerate(range(15, W, 15)):
                    target = thick_lines if (rounded and (i + 1) % 4 == 0) else thin_lines
                    target.append(QtCore.QLineF(x, offset_y, x, H))

                start_y = 15 + offset_y if rounded else 15
                for i, y in enumerate(range(start_y, H, 15)):
                    target = thick_lines if (rounded and (i + 1) % 2 == 0) else thin_lines
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
                    painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 100), 0.8))
                    painter.drawRoundedRect(rect, 4, 4)
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


            def refresh_task_panels(self):
                import FreeCADGui

                mw = FreeCADGui.getMainWindow()
                if not mw:
                    return
                tasks_dock = mw.findChild(QtWidgets.QDockWidget, "Tasks")
                if not tasks_dock or not tasks_dock.isVisible():
                    return

                panels = [w for w in tasks_dock.findChildren(QtWidgets.QFrame)
                          if w.property("class") == "panel"]
                first = True
                for w in panels:
                    target_name = "taskPanelOuter" if first else "taskPanelInner"
                    first = False
                    if w.objectName() != target_name:
                        w.setObjectName(target_name)
                        w.style().unpolish(w)
                        w.style().polish(w)
                        w.update()

        fixer = GlobalFreeCADFixer()
        app.installEventFilter(fixer)
        app._globalFreeCADFixer = fixer
        fixer.refresh_task_panels()

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

        _fix()

    QtCore.QTimer.singleShot(1000, _setup)


if __name__ == "__main__" or __name__ == "color_palette_general_fix":
    _bootstrap_global_fixer()