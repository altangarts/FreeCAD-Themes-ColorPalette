

import FreeCAD

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtWidgets

PROP_NAME = "cpOrient"
_FILTER_ATTR = "_cp_toolbar_orient_filter"
_P_HOOKED = "_cpOrientHooked"


def _orient_name(tb):
    return "horizontal" if tb.orientation() == QtCore.Qt.Horizontal else "vertical"


def _repolish(tb):
    style = tb.style()
    for w in [tb] + tb.findChildren(QtWidgets.QWidget):
        try:
            style.unpolish(w)
            style.polish(w)
            # QListView/QAbstractItemView update()'i override eder (QModelIndex ister);
            # QWidget.update'i dogrudan cagirarak override'dan kacin
            QtWidgets.QWidget.update(w)
        except RuntimeError:
            pass    # widget silinmis


class _OrientationFilter(QtCore.QObject):
    def __init__(self, mw):
        super().__init__(mw)
        self._mw = mw
        self._pending = set()
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)   # yerlesim bittikten sonra, bir olay turu gecikmeli
        self._timer.timeout.connect(self._process)

    def _queue(self, tb):
        self._pending.add(tb)
        if not self._timer.isActive():
            self._timer.start()

    def _process(self):
        pending, self._pending = self._pending, set()
        for tb in pending:
            try:
                cur = _orient_name(tb)
                if tb.property(PROP_NAME) == cur:
                    continue
                tb.setProperty(PROP_NAME, cur)
                _repolish(tb)
            except RuntimeError:
                pass    # toolbar silinmis
            except Exception as e:
                FreeCAD.Console.PrintError(
                    f"ColorPalette: toolbar_orientation hata - {str(e)}\n"
                )

    def hook_all(self):
        for tb in self._mw.findChildren(QtWidgets.QToolBar):
            if tb.property(_P_HOOKED):
                continue
            tb.setProperty(_P_HOOKED, True)
            tb.installEventFilter(self)
            try:
                tb.orientationChanged.connect(lambda *_, t=tb: self._queue(t))
            except Exception:
                pass
            self._queue(tb)     # ilk property atamasi + ilk polish

    def eventFilter(self, obj, event):
        t = event.type()
        if obj is self._mw:
            if t == QtCore.QEvent.ChildAdded:
                QtCore.QTimer.singleShot(200, self.hook_all)
        elif t == QtCore.QEvent.Resize:
            if obj.property(PROP_NAME) != _orient_name(obj):
                self._queue(obj)
        return False


def install():
    try:
        import FreeCADGui as Gui
        mw = Gui.getMainWindow()
    except Exception:
        mw = None

    if not mw:
        QtCore.QTimer.singleShot(500, install)
        return
    if getattr(mw, _FILTER_ATTR, None) is not None:
        return

    flt = _OrientationFilter(mw)
    mw.installEventFilter(flt)
    setattr(mw, _FILTER_ATTR, flt)

    flt.hook_all()
    for delay in (500, 1500, 4000):
        QtCore.QTimer.singleShot(delay, flt.hook_all)
