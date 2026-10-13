

import FreeCAD

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtWidgets

QWIDGETSIZE_MAX = 16777215
EXCLUDE_OBJECT_NAMES = set()      # ornek: {"Workbench"}
_FILTER_ATTR = "_cp_toolbar_fit_filter"

_TB_EVENTS = frozenset((
    QtCore.QEvent.ActionAdded,
    QtCore.QEvent.ActionRemoved,
    QtCore.QEvent.ActionChanged,
    QtCore.QEvent.Show,
    QtCore.QEvent.StyleChange,
    QtCore.QEvent.LayoutRequest,
))

_enabled = True


def _content_hint(tb):
    lay = tb.layout()
    hint = lay.sizeHint() if lay is not None else tb.sizeHint()
    return hint


def _reset(tb):
    if tb.maximumWidth() != QWIDGETSIZE_MAX:
        tb.setMaximumWidth(QWIDGETSIZE_MAX)
    if tb.maximumHeight() != QWIDGETSIZE_MAX:
        tb.setMaximumHeight(QWIDGETSIZE_MAX)


def _fit_toolbar(tb, mw):
    excluded = (
        not _enabled
        or tb.property("cpNoFit")
        or tb.objectName() in EXCLUDE_OBJECT_NAMES
        or tb.parentWidget() is not mw      # sadece ana pencereye docked olanlar
        or tb.isFloating()
    )
    if excluded:
        _reset(tb)
        return

    if not tb.isVisible():
        return

    hint = _content_hint(tb)
    if hint.width() <= 0 or hint.height() <= 0:
        return

    if tb.orientation() == QtCore.Qt.Horizontal:
        if tb.maximumHeight() != QWIDGETSIZE_MAX:
            tb.setMaximumHeight(QWIDGETSIZE_MAX)
        if tb.maximumWidth() != hint.width():
            tb.setMaximumWidth(hint.width())
    else:
        if tb.maximumWidth() != QWIDGETSIZE_MAX:
            tb.setMaximumWidth(QWIDGETSIZE_MAX)
        if tb.maximumHeight() != hint.height():
            tb.setMaximumHeight(hint.height())


class _ToolbarFitFilter(QtCore.QObject):
    def __init__(self, mw):
        super().__init__(mw)
        self._mw = mw
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self.refresh_all)

    def schedule(self):
        if not self._timer.isActive():
            self._timer.start()

    def _hook(self, tb):
        if tb.property("_cpFitHooked"):
            return
        tb.setProperty("_cpFitHooked", True)
        tb.installEventFilter(self)
        try:
            tb.topLevelChanged.connect(lambda *_: self.schedule())
            tb.orientationChanged.connect(lambda *_: self._on_orientation(tb))
        except Exception:
            pass

    def _on_orientation(self, tb):
        _reset(tb)
        self.schedule()

    def refresh_all(self):
        try:
            for tb in self._mw.findChildren(QtWidgets.QToolBar):
                self._hook(tb)
                _fit_toolbar(tb, self._mw)
        except Exception as e:
            FreeCAD.Console.PrintError(
                f"ColorPalette: toolbar_fit guncellenemedi - {str(e)}\n"
            )

    def eventFilter(self, obj, event):
        t = event.type()
        if obj is self._mw:
            if t == QtCore.QEvent.ChildAdded:
                self.schedule()
        elif t in _TB_EVENTS:
            self.schedule()
        return False


def _get_filter():
    try:
        import FreeCADGui as Gui
        mw = Gui.getMainWindow()
    except Exception:
        return None, None
    if not mw:
        return None, None
    return mw, getattr(mw, _FILTER_ATTR, None)


def set_enabled(value):
    global _enabled
    _enabled = bool(value)
    _, flt = _get_filter()
    if flt:
        flt.refresh_all()


def install():
    mw, flt = _get_filter()
    if not mw:
        QtCore.QTimer.singleShot(500, install)
        return
    if flt is not None:
        return

    flt = _ToolbarFitFilter(mw)
    mw.installEventFilter(flt)
    setattr(mw, _FILTER_ATTR, flt)

    flt.refresh_all()
    for delay in (500, 1500, 4000):
        QtCore.QTimer.singleShot(delay, flt.refresh_all)
