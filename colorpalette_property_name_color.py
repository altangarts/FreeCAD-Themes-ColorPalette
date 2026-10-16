# -*- coding: utf-8 -*-
"""
ColorPalette: Property Editor "Name" sutunu metin rengi (QSS ile yonetilir).

QSS, sutun bazli secim yapamadigi icin renk degerleri gizli bir yardimci
widget uzerinden QSS'ten okunur (qproperty-...), Name sutununa ozel bir
delegate sarmalayici ile uygulanir. FreeCAD'in kendi delegate'i korunur
(sadece paint sirasinda palette degistirilir).

Tema .qss dosyasina ekle:

    #cpPropertyNameColor {
        qproperty-nameColor: #ff8800;           /* normal satir */
        qproperty-nameSelectedColor: #ffffff;   /* secili satir (istege bagli) */
        qproperty-nameBold: true;               /* Name yazisi kalin (istege bagli) */
    }

Renk tanimlanmazsa hicbir sey degismez (varsayilan gorunum).
Grup basliklari (Base, Data...) etkilenmez.
"""

import FreeCAD

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

try:
    import shiboken6 as _shiboken
except ImportError:
    import shiboken2 as _shiboken


def _is_valid(obj):
    try:
        return _shiboken.isValid(obj)
    except Exception:
        return False


HELPER_OBJECT_NAME = "cpPropertyNameColor"
_MAX_TRIES = 15
_RETRY_MS = 1000

_state = {"holder": None, "tries": 0}


def _find_property_editors():
    try:
        import FreeCADGui as Gui
        mw = Gui.getMainWindow()
    except Exception:
        return []
    if not mw:
        return []
    result = []
    for tv in mw.findChildren(QtWidgets.QTreeView):
        try:
            if "PropertyEditor" in tv.metaObject().className():
                result.append(tv)
        except Exception:
            pass
    return result


def refresh():
    """Tum property editor gorunumlerini yeniden ciz."""
    for pe in _find_property_editors():
        try:
            pe.viewport().update()
        except Exception:
            pass


class _ColorHolder(QtWidgets.QWidget):
    """QSS'ten qproperty ile renk okuyan gizli widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName(HELPER_OBJECT_NAME)
        self._name_color = QtGui.QColor()
        self._name_selected_color = QtGui.QColor()
        self._name_bold = False
        self.hide()

    def _get_name_color(self):
        return self._name_color

    def _set_name_color(self, c):
        self._name_color = QtGui.QColor(c)
        QtCore.QTimer.singleShot(0, refresh)

    def _get_name_selected_color(self):
        return self._name_selected_color

    def _set_name_selected_color(self, c):
        self._name_selected_color = QtGui.QColor(c)
        QtCore.QTimer.singleShot(0, refresh)

    def _get_name_bold(self):
        return self._name_bold

    def _set_name_bold(self, v):
        self._name_bold = bool(v)
        QtCore.QTimer.singleShot(0, refresh)

    nameColor = QtCore.Property(QtGui.QColor, _get_name_color, _set_name_color)
    nameBold = QtCore.Property(bool, _get_name_bold, _set_name_bold)
    nameSelectedColor = QtCore.Property(
        QtGui.QColor, _get_name_selected_color, _set_name_selected_color
    )


class _NameColumnDelegate(QtWidgets.QStyledItemDelegate):
    """Orijinal delegate'i sarar; sadece Name sutunu (0) metin rengini degistirir.

    FreeCAD / diger moduller view'in delegate'ini degistirip eskisini silebilir;
    bu yuzden sarilan delegate her cagrida gecerlilik kontrolunden gecirilir,
    silinmisse view'in guncel delegate'i yeniden bulunur.
    """

    def __init__(self, inner, holder, parent=None):
        super().__init__(parent)
        self._inner = inner
        self._holder = holder

    def _resolve_inner(self):
        inner = self._inner
        if inner is not None and _is_valid(inner):
            return inner
        view = self.parent()
        new = None
        if view is not None and _is_valid(view):
            try:
                cand = view.itemDelegate()
                if cand is not None and cand is not self and _is_valid(cand):
                    new = cand
            except Exception:
                new = None
        self._inner = new
        return new

    def paint(self, painter, option, index):
        inner = self._resolve_inner()
        if inner is None:
            super().paint(painter, option, index)
            return
        # Grup basliklari (ust seviye satirlar) dokunulmadan birakilir
        if index.column() == 0 and index.parent().isValid():
            nc = self._holder.nameColor
            sc = self._holder.nameSelectedColor
            bold = self._holder.nameBold
            if nc.isValid() or sc.isValid() or bold:
                opt = QtWidgets.QStyleOptionViewItem(option)
                if nc.isValid() or sc.isValid():
                    pal = QtGui.QPalette(opt.palette)
                    if nc.isValid():
                        pal.setColor(QtGui.QPalette.Text, nc)
                        pal.setColor(QtGui.QPalette.WindowText, nc)
                    if sc.isValid():
                        pal.setColor(QtGui.QPalette.HighlightedText, sc)
                    elif nc.isValid():
                        pal.setColor(QtGui.QPalette.HighlightedText, nc)
                    opt.palette = pal
                if bold:
                    font = QtGui.QFont(opt.font)
                    font.setBold(True)
                    opt.font = font
                inner.paint(painter, opt, index)
                return
        inner.paint(painter, option, index)

    # --- Orijinal delegate'e yonlendirmeler ---
    def sizeHint(self, option, index):
        inner = self._resolve_inner()
        if inner is None:
            return super().sizeHint(option, index)
        return inner.sizeHint(option, index)

    def createEditor(self, parent, option, index):
        inner = self._resolve_inner()
        if inner is None:
            return super().createEditor(parent, option, index)
        return inner.createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        inner = self._resolve_inner()
        if inner is None:
            return super().setEditorData(editor, index)
        inner.setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        inner = self._resolve_inner()
        if inner is None:
            return super().setModelData(editor, model, index)
        inner.setModelData(editor, model, index)

    def updateEditorGeometry(self, editor, option, index):
        inner = self._resolve_inner()
        if inner is None:
            return super().updateEditorGeometry(editor, option, index)
        inner.updateEditorGeometry(editor, option, index)

    def editorEvent(self, event, model, option, index):
        inner = self._resolve_inner()
        if inner is None:
            return super().editorEvent(event, model, option, index)
        return inner.editorEvent(event, model, option, index)


def _get_holder():
    holder = _state["holder"]
    if holder is not None:
        return holder
    import FreeCADGui as Gui
    mw = Gui.getMainWindow()
    holder = _ColorHolder(mw)
    holder.ensurePolished()   # QSS'teki qproperty degerlerini hemen uygula
    _state["holder"] = holder
    return holder


def _wrap_editor(pe, holder):
    if getattr(pe, "_cp_name_delegate", None) is not None:
        return
    inner = pe.itemDelegateForColumn(0) or pe.itemDelegate()
    if inner is None or not _is_valid(inner):
        return
    wrapper = _NameColumnDelegate(inner, holder, pe)
    pe._cp_name_delegate = wrapper   # GC'ye karsi referans
    pe.setItemDelegateForColumn(0, wrapper)
    pe.viewport().update()


def install():
    """InitGui'den cagrilir. Property editor henuz yoksa birkac kez tekrar dener."""
    try:
        holder = _get_holder()
        editors = _find_property_editors()
        for pe in editors:
            _wrap_editor(pe, holder)
        if not editors and _state["tries"] < _MAX_TRIES:
            _state["tries"] += 1
            QtCore.QTimer.singleShot(_RETRY_MS, install)
        else:
            holder.ensurePolished()
            refresh()
    except Exception as e:
        FreeCAD.Console.PrintError(
            f"ColorPalette: property name color kurulamadi - {str(e)}\n"
        )
