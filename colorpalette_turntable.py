import bisect
import math
import os
import re
import shutil
import subprocess
import sys

import FreeCAD

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets


_PARAM_PATH = "User parameter:BaseApp/Preferences/Mod/ColorPaletteTurntable"
_FRAMES_DIR_NAME = "CP Turntable Video"   # PNG karelerinin yazildigi klasor (videonun yaninda)


_RESOLUTIONS = (
    ("Current view size", None),
    ("1280 x 720", (1280, 720)),
    ("1920 x 1080", (1920, 1080)),
    ("2560 x 1440", (2560, 1440)),
    ("3840 x 2160", (3840, 2160)),
)
_PATHS = ("Circle", "Sketch path")           
_BACKGROUNDS = ("Current", "White", "Black")  

# (etiket, zemin normali)
_GROUND_PLANES = (
    ("XY plane  (Z is up)", (0.0, 0.0, 1.0)),
    ("XZ plane  (Y is up)", (0.0, 1.0, 0.0)),
    ("YZ plane  (X is up)", (1.0, 0.0, 0.0)),
)


# --- Saf vektor  --
def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _normalize(v):
    length = math.sqrt(_dot(v, v))
    if length < 1e-12:
        return None
    return (v[0] / length, v[1] / length, v[2] / length)


def _rotate(v, axis, angle):
    c, s = math.cos(angle), math.sin(angle)
    return _add(
        _add(_scale(v, c), _scale(_cross(axis, v), s)),
        _scale(axis, _dot(axis, v) * (1.0 - c)),
    )


def _orthonormal_basis(up_hint, back):
    back = _normalize(back)
    right = _normalize(_cross(up_hint, back))
    if right is None:  # up_hint, back ile paralel
        alt = (1.0, 0.0, 0.0) if abs(back[0]) < 0.9 else (0.0, 1.0, 0.0)
        right = _normalize(_cross(alt, back))
    up = _cross(back, right)
    return right, up, back


def _basis_to_quat(right, up, back):
    m00, m10, m20 = right
    m01, m11, m21 = up
    m02, m12, m22 = back
    tr = m00 + m11 + m22
    if tr > 0.0:
        s = math.sqrt(tr + 1.0) * 2.0
        w = 0.25 * s
        x = (m21 - m12) / s
        y = (m02 - m20) / s
        z = (m10 - m01) / s
    elif m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2.0
        w = (m21 - m12) / s
        x = 0.25 * s
        y = (m01 + m10) / s
        z = (m02 + m20) / s
    elif m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2.0
        w = (m02 - m20) / s
        x = (m01 + m10) / s
        y = 0.25 * s
        z = (m12 + m21) / s
    else:
        s = math.sqrt(1.0 + m22 - m00 - m11) * 2.0
        w = (m10 - m01) / s
        x = (m02 + m20) / s
        y = (m12 + m21) / s
        z = 0.25 * s
    return (x, y, z, w)


def orbit_step(pos, right, up, back, pivot, axis, angle):
    new_pos = _add(pivot, _rotate(_sub(pos, pivot), axis, angle))
    new_up = _rotate(up, axis, angle)
    new_back = _rotate(back, axis, angle)
    r, u, b = _orthonormal_basis(new_up, new_back)
    return new_pos, r, u, b


# --- Skec yolu (saf matematik) ---
def _dist(a, b):
    d = _sub(a, b)
    return math.sqrt(_dot(d, d))


def _plane_basis(axis):
    alt = (1.0, 0.0, 0.0) if abs(axis[0]) < 0.9 else (0.0, 1.0, 0.0)
    e1 = _normalize(_cross(alt, axis))
    return e1, _cross(axis, e1)


def chain_edges(edges, close_frac=0.02):
    edges = [list(e) for e in edges if len(e) >= 2]
    if not edges:
        return None, False
    total = sum(sum(_dist(p, q) for p, q in zip(e, e[1:])) for e in edges)
    if total < 1e-9:
        return None, False
    tol = max(1e-6, 1e-4 * total)

    def free_end(i, w):                      # bu uc baska bir kenarla eslesmiyor mu?
        pt = edges[i][0 if w == 0 else -1]
        for j, e in enumerate(edges):
            if j != i and (_dist(pt, e[0]) <= tol or _dist(pt, e[-1]) <= tol):
                return False
        return True

    start_i, start_w = 0, 0
    found = False
    for i in range(len(edges)):              # acik zincirse serbest uctan basla
        for w in (0, 1):
            if free_end(i, w):
                start_i, start_w, found = i, w, True
                break
        if found:
            break
    first = edges.pop(start_i)
    chain = first if start_w == 0 else first[::-1]

    while edges:
        end = chain[-1]
        best = None
        for j, e in enumerate(edges):
            for flip in (False, True):
                d = _dist(end, e[-1] if flip else e[0])
                if best is None or d < best[0]:
                    best = (d, j, flip)
        _d, j, flip = best
        e = edges.pop(j)
        if flip:
            e = e[::-1]
        chain.extend(e[1:] if _dist(end, e[0]) <= tol else e)

    gap = _dist(chain[0], chain[-1])
    path_len = sum(_dist(p, q) for p, q in zip(chain, chain[1:]))
    return chain, gap <= close_frac * max(path_len, 1e-9)


def build_path(points, closed):
    pts = [(float(p[0]), float(p[1]), float(p[2])) for p in points]
    if closed and len(pts) > 1 and _dist(pts[0], pts[-1]) < 1e-7:
        pts.pop()
    if closed and pts:
        pts.append(pts[0])
    if len(pts) < 2:
        return None
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + _dist(a, b))
    if cum[-1] < 1e-9:
        return None
    return {"pts": pts, "cum": cum, "total": cum[-1], "closed": bool(closed)}


def path_point(path, u):
    cum = path["cum"]
    target = min(max(u, 0.0), 1.0) * path["total"]
    i = max(0, min(bisect.bisect_right(cum, target) - 1, len(cum) - 2))
    seg = cum[i + 1] - cum[i]
    f = 0.0 if seg < 1e-12 else (target - cum[i]) / seg
    a, b = path["pts"][i], path["pts"][i + 1]
    return _add(a, _scale(_sub(b, a), f))


def path_nearest_u(path, p):
    pts, cum, total = path["pts"], path["cum"], path["total"]
    best_d, best_u = None, 0.0
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        ab = _sub(b, a)
        l2 = _dot(ab, ab)
        f = 0.0 if l2 < 1e-18 else max(0.0, min(1.0, _dot(_sub(p, a), ab) / l2))
        d = _dist(p, _add(a, _scale(ab, f)))
        if best_d is None or d < best_d:
            best_d, best_u = d, (cum[i] + f * (cum[i + 1] - cum[i])) / total
    return best_u


def path_u(phase, closed, u0):
    if closed:
        return (u0 + phase) % 1.0
    w = (u0 + 2.0 * phase) % 2.0
    return w if w <= 1.0 else 2.0 - w


def azimuth_table(path, pivot, axis):
    if not path["closed"]:
        return None
    e1, e2 = _plane_basis(axis)
    a, b = [], []
    for p in path["pts"]:
        d = _sub(p, pivot)
        a.append(_dot(d, e1))
        b.append(_dot(d, e2))
    th = [math.atan2(y, x) for x, y in zip(a, b)]
    un = [th[0]]
    for i in range(1, len(th)):
        d = (th[i] - th[i - 1] + math.pi) % (2.0 * math.pi) - math.pi
        un.append(un[-1] + d)
    total = un[-1] - un[0]
    if abs(abs(total) - 2.0 * math.pi) > 1e-3:        # pivot dongunun icinde degil
        return None
    sgn = 1.0 if total > 0 else -1.0
    arr = [sgn * v for v in un]
    for i in range(len(arr) - 1):
        if arr[i + 1] < arr[i] - 1e-9:                # yol pivot etrafinda geri donuyor
            return None
    return {"sgn": sgn, "arr": arr, "a": a, "b": b, "e1": e1, "e2": e2, "T0": arr[0]}


def azimuth_point(az, path, T):
    arr = az["arr"]
    T = arr[0] + ((T - arr[0]) % (2.0 * math.pi))
    i = max(0, min(bisect.bisect_right(arr, T) - 1, len(arr) - 2))
    ang = az["sgn"] * T
    dx, dy = math.cos(ang), math.sin(ang)
    ax_, ay_ = az["a"][i], az["b"][i]
    ex, ey = az["a"][i + 1] - ax_, az["b"][i + 1] - ay_
    den = dx * ey - dy * ex
    t = 0.5 if abs(den) < 1e-12 else -(dx * ay_ - dy * ax_) / den
    t = max(0.0, min(1.0, t))
    p, q = path["pts"][i], path["pts"][i + 1]
    return _add(p, _scale(_sub(q, p), t))


def sketch_setup(path, axis, pos, up, back, pivot, angular=True):
    n = _normalize(axis)
    off = _sub(pos, pivot)
    rise = _dot(off, n)                                    # kameranin pivota gore yuksekligi
    horiz_now = math.sqrt(max(_dot(off, off) - rise * rise, 0.0))
    e_now = max(-math.radians(85.0), min(math.radians(85.0), math.atan2(rise, horiz_now)))
    plane_pos = _sub(pos, _scale(n, _dot(pos, n)))
    az = azimuth_table(path, pivot, n) if angular else None
    note = ""
    if az is not None:
        d = _sub(plane_pos, pivot)
        x, y = _dot(d, az["e1"]), _dot(d, az["e2"])
        t0 = az["arr"][0] if math.hypot(x, y) < 1e-9 else az["sgn"] * math.atan2(y, x)
        az["T0"] = az["arr"][0] + ((t0 - az["arr"][0]) % (2.0 * math.pi))   # baslangic: kameranin acisi
        start_pt = azimuth_point(az, path, az["T0"])
    else:
        if angular:
            note = ("view-angle speed needs a closed loop around the pivot - "
                    "using constant speed along the path")
        start_pt = path_point(path, path_nearest_u(path, plane_pos))
    ds = _sub(start_pt, pivot)
    d_start = math.sqrt(max(_dot(ds, ds) - _dot(ds, n) ** 2, 0.0))   # baslangicin pivota yatay mesafesi
    if d_start > 1e-6:
        h_rel = d_start * math.tan(e_now)
    else:
        h_rel = rise
    fwd0 = _scale(back, -1.0)
    h0 = _normalize(_sub(fwd0, _scale(n, _dot(fwd0, n)))) or _plane_basis(n)[0]
    return {
        "path": path,
        "axis": n,
        "height": _dot(pivot, n) + h_rel,                  # mutlak dikey konum (yol boyunca sabit)
        "h_rel": h_rel,                                    # pivota gore yukseklik
        "u0": path_nearest_u(path, plane_pos),
        "az": az,
        "note": note,
        "up_hint": n if _dot(up, n) >= 0.0 else _scale(n, -1.0),   # kamera ters donmesin
        "back0": back,
        "h0": h0,
    }


def sketch_pose(sp, pivot, phase):
    path = sp["path"]
    if sp["az"] is not None:
        pt = azimuth_point(sp["az"], path, sp["az"]["T0"] + 2.0 * math.pi * phase)
    else:
        pt = path_point(path, path_u(phase, path["closed"], sp["u0"]))
    n = sp["axis"]
    pos = _add(pt, _scale(n, sp["height"]))
    d = _sub(pivot, pos)
    fwd = _normalize(d)
    if fwd is None:
        fwd = _scale(sp["back0"], -1.0)
    up_hint = sp["up_hint"]
    if abs(_dot(fwd, n)) > 0.99:                       # (neredeyse) tam ustten / alttan bakis
        q = _sub(d, _scale(n, _dot(d, n)))
        ql = math.sqrt(_dot(q, q))
        h = _scale(q, 1.0 / ql) if ql > 1e-6 else sp["h0"]
        up_hint = h if _dot(fwd, n) < 0 else _scale(h, -1.0)
    right, up, back = _orthonormal_basis(up_hint, _scale(fwd, -1.0))
    return pos, right, up, back


# --- FreeCAD / Coin tarafi ---------------------------------------------------
def _find_view():
    try:
        import FreeCADGui as Gui
    except ImportError:
        return None
    doc = Gui.ActiveDocument
    view = doc.ActiveView if doc else None
    if view is None or not hasattr(view, "getCameraNode"):
        return None
    return view


def _v3(sb):
    t = sb.getValue()
    return (float(t[0]), float(t[1]), float(t[2]))


def _read_camera(cam):
    from pivy import coin
    orient = cam.orientation.getValue()
    pos = _v3(cam.position.getValue())
    right = _v3(orient.multVec(coin.SbVec3f(1, 0, 0)))
    up = _v3(orient.multVec(coin.SbVec3f(0, 1, 0)))
    back = _v3(orient.multVec(coin.SbVec3f(0, 0, 1)))
    return pos, right, up, back


def _write_camera(cam, pos, right, up, back):
    from pivy import coin
    x, y, z, w = _basis_to_quat(right, up, back)
    cam.position.setValue(pos[0], pos[1], pos[2])
    cam.orientation.setValue(coin.SbRotation(x, y, z, w))


def _shape_boxes_of(obj, boxes, seen):
    if obj is None or obj.Name in seen:
        return
    seen.add(obj.Name)
    shape = getattr(obj, "Shape", None)
    try:
        if shape is not None and not shape.isNull() and shape.BoundBox.isValid():
            boxes.append(shape.BoundBox)
            return
    except Exception:
        pass
    for child in getattr(obj, "Group", None) or []:
        _shape_boxes_of(child, boxes, seen)


def _collect_boxes(selected_only, exclude=()):
    import FreeCADGui as Gui
    boxes = []
    if selected_only:
        for sel in Gui.Selection.getSelectionEx():
            if sel.Object.Name in exclude:      # kamera yolu skeci pivota katilmaz
                continue
            added = False
            try:
                for sub in sel.SubObjects:
                    if hasattr(sub, "BoundBox") and sub.BoundBox.isValid():
                        boxes.append(sub.BoundBox)
                        added = True
            except Exception:
                pass
            if not added:
                _shape_boxes_of(sel.Object, boxes, set())
        return boxes

    doc = FreeCAD.ActiveDocument
    if doc is None:
        return boxes
    for obj in doc.Objects:
        if obj.Name in exclude:
            continue
        vo = getattr(obj, "ViewObject", None)
        if vo is not None and hasattr(vo, "Visibility") and not vo.Visibility:
            continue
        shape = getattr(obj, "Shape", None)
        try:
            if shape is not None and not shape.isNull() and shape.BoundBox.isValid():
                boxes.append(shape.BoundBox)
        except Exception:
            pass
    return boxes


def compute_pivot(selected_only, exclude=()):
    boxes = _collect_boxes(selected_only, exclude)
    note = "selection" if selected_only else "all objects"
    if not boxes and selected_only:
        boxes = _collect_boxes(False, exclude)
        note = "all objects (nothing selected)"
    if not boxes:
        return None, "no visible geometry"
    bb = FreeCAD.BoundBox()
    for b in boxes:
        bb.add(b)
    c = bb.Center
    return (c.x, c.y, c.z), note


def sketch_path_data(obj, axis, samples=1000):
    try:
        shape = obj.Shape.copy()
        gp = None
        try:
            gp = obj.getGlobalPlacement()          # Body / Part icindeki skecler icin
        except Exception:
            pass
        if gp is None:
            gp = obj.Placement
        shape.Placement = gp
        nrm = gp.Rotation.multVec(FreeCAD.Vector(0, 0, 1))
        if abs(nrm.x * axis[0] + nrm.y * axis[1] + nrm.z * axis[2]) < 0.999:
            return None, "the sketch is not parallel to the selected ground plane"
        edges = list(shape.Edges)
        total = sum(e.Length for e in edges)
        if not edges or total < 1e-9:
            return None, "the sketch has no geometry"
        chains = []
        for e in edges:
            k = max(2, int(math.ceil(samples * e.Length / total)) + 1)
            chains.append([(v.x, v.y, v.z) for v in e.discretize(Number=k)])
        pts, closed = chain_edges(chains)
        if pts is None:
            return None, "the sketch path is empty"
        proj = []
        for p in pts:                              # zemine izdusum: dikey koordinati sifirla
            h = p[0] * axis[0] + p[1] * axis[1] + p[2] * axis[2]
            proj.append((p[0] - axis[0] * h, p[1] - axis[1] * h, p[2] - axis[2] * h))
        path = build_path(proj, closed)
        if path is None:
            return None, "the sketch path is empty"
        return path, ""
    except Exception as e:
        return None, "cannot read the sketch (%s)" % e


# --- Ayarlar -----------------------------------------------------------------
class _Settings:
    def __init__(self):
        self.pivot_selected = False   # False: tum nesneler, True: secili nesneler
        self.use_ground = True        # True: zemin duzlemi, False: eksen kombinasyonu
        self.ground_index = 0
        self.axes = [False, False, True]   # X, Y, Z (eksen kombinasyonu modu)
        self.speed = 20.0             # derece / saniye
        self.reverse = False
        self.path_type = 0            # 0: daire, 1: skec yolu
        self.sketch_name = ""         # kamera yolu skecinin ic adi (Name)
        self.sketch_angular = True    # skec yolunda hiz: pivotun gordugu aciya gore sabit
        self.aim = False              # kamerayi pivota cevir
        # video kaydi
        self.rec_path = os.path.join(os.path.expanduser("~"), "turntable.mp4")
        self.rec_res = 0
        self.rec_fps = 30
        self.rec_secs = 10.0          # bir tam tur suresi (sn)
        self.rec_turns = 1
        self.rec_bg = 0
        self.rec_keep = False
        self.rec_ffmpeg = ""          # bos: PATH'te ara

    def load(self):
        g = FreeCAD.ParamGet(_PARAM_PATH)
        self.pivot_selected = g.GetBool("PivotSelected", False)
        self.use_ground = g.GetBool("UseGround", True)
        self.ground_index = max(0, min(len(_GROUND_PLANES) - 1, g.GetInt("GroundIndex", 0)))
        self.axes = [g.GetBool("AxisX", False), g.GetBool("AxisY", False), g.GetBool("AxisZ", True)]
        self.speed = g.GetFloat("Speed", 20.0)
        self.reverse = g.GetBool("Reverse", False)
        self.path_type = max(0, min(len(_PATHS) - 1, g.GetInt("CameraPath", 0)))
        self.sketch_name = g.GetString("SketchName", "")
        self.sketch_angular = g.GetBool("SketchAngular", True)
        self.aim = g.GetBool("Aim", False)
        self.rec_path = g.GetString("RecPath", self.rec_path)
        self.rec_res = max(0, min(len(_RESOLUTIONS) - 1, g.GetInt("RecRes", 0)))
        self.rec_fps = max(5, min(60, g.GetInt("RecFps", 30)))
        self.rec_secs = max(1.0, g.GetFloat("RecSecs", 10.0))
        self.rec_turns = max(1, g.GetInt("RecTurns", 1))
        self.rec_bg = max(0, min(len(_BACKGROUNDS) - 1, g.GetInt("RecBg", 0)))
        self.rec_keep = g.GetBool("RecKeep", False)
        self.rec_ffmpeg = g.GetString("RecFfmpeg", "")

    def save(self):
        g = FreeCAD.ParamGet(_PARAM_PATH)
        g.SetBool("PivotSelected", self.pivot_selected)
        g.SetBool("UseGround", self.use_ground)
        g.SetInt("GroundIndex", self.ground_index)
        g.SetBool("AxisX", self.axes[0])
        g.SetBool("AxisY", self.axes[1])
        g.SetBool("AxisZ", self.axes[2])
        g.SetFloat("Speed", self.speed)
        g.SetBool("Reverse", self.reverse)
        g.SetInt("CameraPath", self.path_type)
        g.SetString("SketchName", self.sketch_name)
        g.SetBool("SketchAngular", self.sketch_angular)
        g.SetBool("Aim", self.aim)
        g.SetString("RecPath", self.rec_path)
        g.SetInt("RecRes", self.rec_res)
        g.SetInt("RecFps", self.rec_fps)
        g.SetFloat("RecSecs", self.rec_secs)
        g.SetInt("RecTurns", self.rec_turns)
        g.SetInt("RecBg", self.rec_bg)
        g.SetBool("RecKeep", self.rec_keep)
        g.SetString("RecFfmpeg", self.rec_ffmpeg)

    def axis_vector(self):
        if self.use_ground or self.path_type == 1:     # skec yolunda yalnizca zemin duzlemi
            return _GROUND_PLANES[self.ground_index][1]
        v = (
            1.0 if self.axes[0] else 0.0,
            1.0 if self.axes[1] else 0.0,
            1.0 if self.axes[2] else 0.0,
        )
        return _normalize(v)


# --- Denetleyici -------------------------------------------------------------
class _Controller:
    INTERVAL_MS = 16

    def __init__(self):
        self.settings = _Settings()
        self.settings.load()
        self.pivot = None
        self.spath = None              # skec yolu tabani (sketch_setup); None: skec yolu yok
        self._spath_key = None
        self._phase = 0.0              # skec yolunda tur fazi (0..1)
        self.on_state_changed = None   # fn(running: bool, message: str)
        self.recorder = None           # _Recorder (panel olusturur)
        self._clock = QtCore.QElapsedTimer()
        self._last_ms = 0
        self._timer = QtCore.QTimer()
        self._timer.setInterval(self.INTERVAL_MS)
        self._timer.timeout.connect(self._step)

    def is_running(self):
        return self._timer.isActive()

    def _notify(self, message=""):
        if self.on_state_changed:
            try:
                self.on_state_changed(self.is_running(), message)
            except Exception:
                pass

    def prepare(self):
        s = self.settings
        view = _find_view()
        if view is None:
            self._notify("No active 3D view.")
            return False
        sketch_mode = (s.path_type == 1)
        if s.axis_vector() is None:
            self._notify("Select at least one axis.")
            return False

        exclude = {s.sketch_name} if (sketch_mode and s.sketch_name) else set()
        pivot, note = compute_pivot(s.pivot_selected, exclude)
        if pivot is None:
            self._notify("Nothing to rotate around: %s." % note)
            return False
        self.pivot = pivot

        cam = view.getCameraNode()
        if sketch_mode:
            return self._prepare_sketch(cam, pivot, note)
        self.spath = None
        self._spath_key = None
        if s.aim:
            pos, right, up, back = _read_camera(cam)
            dist = _dot(_sub(pos, pivot), back)   # gorus ekseni boyunca mesafe
            if dist < 1e-3:                       # pivot kameranin arkasinda / cok yakin
                to_pivot = _sub(pos, pivot)
                dist = math.sqrt(_dot(to_pivot, to_pivot))
                if dist < 1e-3:
                    dist = 1000.0
            new_pos = _add(pivot, _scale(back, dist))
            _write_camera(cam, new_pos, right, up, back)
            try:
                cam.focalDistance.setValue(dist)
            except Exception:
                pass

        self._notify("Pivot: %.1f, %.1f, %.1f  (%s)" % (pivot[0], pivot[1], pivot[2], note))
        return True

    def _prepare_sketch(self, cam, pivot, note):
        s = self.settings
        doc = FreeCAD.ActiveDocument
        obj = doc.getObject(s.sketch_name) if (doc is not None and s.sketch_name) else None
        if obj is None:
            self._notify("Choose a sketch for the camera path.")
            return False
        axis = s.axis_vector()
        key = (s.sketch_name, pivot, axis, s.sketch_angular)
        if self.spath is not None and self.is_running() and key == self._spath_key:
            return True
        path, err = sketch_path_data(obj, axis)
        if path is None:
            self._notify("Sketch path: %s." % err)
            return False
        pos, _right, up, back = _read_camera(cam)
        self.spath = sketch_setup(path, axis, pos, up, back, pivot, s.sketch_angular)
        self._spath_key = key
        self._phase = 0.0
        self.apply_sketch_pose(cam, 0.0)
        msg = ("Sketch path: %s  |  camera height %.1f (%.1f above the pivot)  |  "
               "Pivot: %.1f, %.1f, %.1f (%s)"
               % (obj.Label, self.spath["height"], self.spath["h_rel"],
                  pivot[0], pivot[1], pivot[2], note))
        if self.spath["note"]:
            msg += "\n" + self.spath["note"]
        self._notify(msg)
        return True

    def apply_sketch_pose(self, cam, phase):
        pos, right, up, back = sketch_pose(self.spath, self.pivot, phase)
        _write_camera(cam, pos, right, up, back)
        try:
            along = _dot(_sub(self.pivot, pos), _scale(back, -1.0))
            cam.focalDistance.setValue(along if along > 1e-3 else _dist(pos, self.pivot))
        except Exception:
            pass

    def start(self):
        if self.is_running():
            return
        if not self.prepare():
            return
        self._clock.start()
        self._last_ms = 0
        self._timer.start()
        self._notify("Running. " + self._last_message_suffix())

    def _last_message_suffix(self):
        p = self.pivot
        return "Pivot: %.1f, %.1f, %.1f" % p if p else ""

    def stop(self):
        was_running = self.is_running()
        self._timer.stop()
        if was_running:
            self._notify("Stopped.")

    def toggle(self):
        self.stop() if self.is_running() else self.start()

    def refresh(self):
        if self.is_running() and not self.prepare():
            self.stop()

    def _step(self):
        view = _find_view()
        axis = self.settings.axis_vector()
        if view is None or axis is None or self.pivot is None:
            self.stop()
            return

        now = self._clock.elapsed()
        dt = min((now - self._last_ms) / 1000.0, 0.1)
        self._last_ms = now
        if dt <= 0.0:
            return

        cam = view.getCameraNode()
        if self.spath is not None:                       # skec yolu: hiz = derece/sn ~ tur/sn
            step = self.settings.speed / 360.0 * dt
            self._phase = (self._phase + (-step if self.settings.reverse else step)) % 1.0
            self.apply_sketch_pose(cam, self._phase)
            return

        angle = math.radians(self.settings.speed) * dt
        if self.settings.reverse:
            angle = -angle

        pos, right, up, back = _read_camera(cam)
        pos, right, up, back = orbit_step(pos, right, up, back, self.pivot, axis, angle)
        _write_camera(cam, pos, right, up, back)


# --- Video kaydi -------------------------------------------------------------
def _even(n):
    n = int(n)
    return n if n % 2 == 0 else n + 1   # H.264 / yuv420p cift boyut ister


def _view_size(view):
    try:
        w, h = view.getSize()
        return int(w), int(h)
    except Exception:
        return 1280, 720


def _normalize_video_path(path):
    path = (path or "").strip().strip('"')
    if not path:
        return ""
    base, ext = os.path.splitext(path)
    if ext.lower() not in (".mp4", ".mov", ".mkv"):
        path = base + ".mp4"
    return path


def _numbered_path(path):
    folder = os.path.dirname(os.path.abspath(path))
    base, ext = os.path.splitext(os.path.basename(path))
    pattern = re.compile(r"^%s_(\d+)%s$" % (re.escape(base), re.escape(ext)), re.IGNORECASE)
    highest = 0
    try:
        for name in os.listdir(folder):
            m = pattern.match(name)
            if m:
                highest = max(highest, int(m.group(1)))
    except OSError:
        pass
    return os.path.join(folder, "%s_%d%s" % (base, highest + 1, ext))


def _ffmpeg_exe_name():
    return "ffmpeg.exe" if os.name == "nt" else "ffmpeg"


def _ffmpeg_candidates():
    exe = _ffmpeg_exe_name()
    cands = []
    if os.name == "nt":
        for env in ("ProgramFiles", "ProgramFiles(x86)"):
            base = os.environ.get(env, "")
            if base:
                cands.append(os.path.join(base, "ffmpeg", "bin", exe))
        cands.append(os.path.join("C:\\", "ffmpeg", "bin", exe))
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            cands.append(os.path.join(local, "Microsoft", "WinGet", "Links", exe))
    else:
        cands += ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg",
                  "/usr/bin/ffmpeg", "/snap/bin/ffmpeg"]
    return cands


def resolve_ffmpeg(configured=""):
    p = (configured or "").strip().strip('"')
    if p:
        if os.path.isdir(p):                       # ornegin ffmpeg/bin klasoru secilmisse
            p = os.path.join(p, _ffmpeg_exe_name())
        if os.path.isfile(p):
            return p
    found = shutil.which("ffmpeg")
    if found:
        return found
    for cand in _ffmpeg_candidates():
        if os.path.isfile(cand):
            return cand
    return None


def _reveal_in_folder(path):
    path = os.path.abspath(path)
    folder = os.path.dirname(path)
    try:
        if os.name == "nt" and os.path.isfile(path):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            return True
        if sys.platform == "darwin" and os.path.isfile(path):
            subprocess.Popen(["open", "-R", path])
            return True
    except Exception:
        pass
    return QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(folder))


def _remove_frames(frames_dir):
    try:
        for name in os.listdir(frames_dir):
            if name.startswith("frame_") and name.endswith(".png"):
                os.remove(os.path.join(frames_dir, name))
        os.rmdir(frames_dir)
    except OSError:
        pass


class _Recorder:
    def __init__(self, controller):
        self.ctl = controller
        self.on_state = None   # fn(active: bool, message: str, progress: float | None)
        self._timer = QtCore.QTimer()
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._tick)
        self._proc = None
        self._active = False
        self._cancelled = False
        self._cam_state = None
        self._frames_dir = ""
        self._out = ""
        self._keep = False
        self._fps = 30
        self._i = 0
        self._n = 0
        self._angle = 0.0
        self._axis = (0.0, 0.0, 1.0)
        self._size = (0, 0)
        self._bg = "Current"
        self.last_saved = ""   # son basarili kaydin yolu (bos: yok)

    def is_active(self):
        return self._active

    def _notify(self, message="", progress=None):
        if self.on_state:
            try:
                self.on_state(self._active, message, progress)
            except Exception:
                pass

    # --- baslat / iptal ---
    def start(self):
        if self._active:
            return
        s = self.ctl.settings
        self.last_saved = ""
        if not self._find_ffmpeg():          # ffmpeg yoksa video cikmaz -> kare uretme
            self._notify("ffmpeg not found - select it with the \"...\" button next to ffmpeg. "
                         "Nothing was recorded.")
            return
        v0 = _find_view()
        orig_cam = _read_camera(v0.getCameraNode()) if v0 is not None else None
        self.ctl.stop()                      # canli turntable'i durdur
        if not self.ctl.prepare():           # gorunum, eksen, pivot kontrolu (+ merkeze alma)
            return
        view = _find_view()
        if view is None:
            self._notify("No active 3D view.")
            return

        out = _normalize_video_path(s.rec_path)
        if not out:
            self._notify("Choose an output file.")
            return
        out = _numbered_path(out)            # her kayit yeni numara alir, eskinin uzerine yazmaz
        out_dir = os.path.dirname(os.path.abspath(out))
        frames_dir = os.path.join(out_dir, _FRAMES_DIR_NAME)
        try:
            os.makedirs(frames_dir, exist_ok=True)   # out_dir de birlikte olusur
            for name in os.listdir(frames_dir):   # eski kareleri temizle
                if name.startswith("frame_") and name.endswith(".png"):
                    os.remove(os.path.join(frames_dir, name))
        except OSError as e:
            self._notify("Cannot write to the output folder: %s" % e)
            return

        size = _RESOLUTIONS[s.rec_res][1] or _view_size(view)
        self._size = (_even(size[0]), _even(size[1]))
        self._bg = _BACKGROUNDS[s.rec_bg]
        self._fps = max(1, int(s.rec_fps))
        self._n = max(2, int(round(s.rec_turns * s.rec_secs * self._fps)))
        angle = 2.0 * math.pi * s.rec_turns / self._n   # tam turlarda son kare = ilk kare -> kusursuz dongu
        self._angle = -angle if s.reverse else angle
        self._axis = s.axis_vector()
        self._out = out
        self._frames_dir = frames_dir
        self._keep = s.rec_keep
        self._phase_step = (s.rec_turns / float(self._n)) * (-1.0 if s.reverse else 1.0)
        # skec yolunda kullanicinin kendi gorunumune don; digerlerinde hazirlanmis gorunume
        self._cam_state = (orig_cam if (self.ctl.spath is not None and orig_cam is not None)
                           else _read_camera(view.getCameraNode()))
        self._i = 0
        self._cancelled = False
        self._active = True
        self._timer.start()
        self._notify("Recording %d frames (%d x %d)..." % (self._n, self._size[0], self._size[1]), 0.0)

    def cancel(self):
        if not self._active:
            return
        self._cancelled = True
        if self._proc is not None and self._proc.state() != QtCore.QProcess.NotRunning:
            self._proc.kill()
        if self._timer.isActive():
            self._abort("Cancelled.")
        else:
            self._active = False

    # --- kare dongusu ---
    def _tick(self):
        view = _find_view()
        if view is None:
            self._abort("3D view was closed.")
            return
        path = os.path.join(self._frames_dir, "frame_%05d.png" % self._i)
        try:
            view.saveImage(path, self._size[0], self._size[1], self._bg)
        except Exception as e:
            self._abort("saveImage failed: %s" % e)
            return
        if not os.path.isfile(path):
            self._abort("Frame was not written: %s" % path)
            return

        cam = view.getCameraNode()
        if self.ctl.spath is not None:
            self.ctl.apply_sketch_pose(cam, (self._i + 1) * self._phase_step)
        else:
            pos, right, up, back = _read_camera(cam)
            pos, right, up, back = orbit_step(pos, right, up, back, self.ctl.pivot, self._axis, self._angle)
            _write_camera(cam, pos, right, up, back)

        self._i += 1
        if self._i >= self._n:
            self._timer.stop()
            self._restore_camera()
            self._encode()
        else:
            self._notify("Frame %d / %d" % (self._i, self._n), self._i / float(self._n))

    def _restore_camera(self):
        view = _find_view()
        if view is not None and self._cam_state is not None:
            try:
                _write_camera(view.getCameraNode(), *self._cam_state)
            except Exception:
                pass

    def _abort(self, message):
        self._timer.stop()
        self._restore_camera()
        if not self._keep:
            _remove_frames(self._frames_dir)
        self._active = False
        self._notify(message)

    # --- ffmpeg ---
    def _find_ffmpeg(self):
        return resolve_ffmpeg(self.ctl.settings.rec_ffmpeg)

    def _encode(self):
        pattern = os.path.join(self._frames_dir, "frame_%05d.png")
        ffmpeg = self._find_ffmpeg()
        if not ffmpeg:
            self._active = False
            self._notify(
                "ffmpeg not found - select it with the \"...\" button next to ffmpeg.\n"
                "%d frames kept in: %s\nOr encode manually with:\n"
                "ffmpeg -framerate %d -i \"%s\" -c:v libx264 -pix_fmt yuv420p \"%s\""
                % (self._n, self._frames_dir, self._fps, pattern, self._out)
            )
            return

        args = ["-y", "-loglevel", "error", "-framerate", str(self._fps), "-i", pattern,
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18"]
        if self._out.lower().endswith((".mp4", ".mov")):
            args += ["-movflags", "+faststart"]
        args.append(self._out)

        self._proc = QtCore.QProcess()
        self._proc.finished.connect(self._on_encoded)
        self._proc.errorOccurred.connect(self._on_proc_error)
        self._proc.start(ffmpeg, args)
        self._notify("Encoding video...", None)

    def _on_proc_error(self, error):
        if error == QtCore.QProcess.FailedToStart:
            self._active = False
            self._notify("ffmpeg could not be started. Frames kept in: %s" % self._frames_dir)

    def _on_encoded(self, exit_code, _status):
        if self._cancelled:
            self._active = False
            if not self._keep:
                _remove_frames(self._frames_dir)
            self._notify("Cancelled.")
            return
        err = bytes(self._proc.readAllStandardError()).decode("utf-8", "replace").strip()
        self._active = False
        if exit_code == 0 and os.path.isfile(self._out):
            if not self._keep:
                _remove_frames(self._frames_dir)
            self.last_saved = self._out
            self._notify("Saved: %s" % self._out, 1.0)
        else:
            tail = "\n".join(err.splitlines()[-3:])
            self._notify("ffmpeg failed (code %s). Frames kept in: %s\n%s"
                         % (exit_code, self._frames_dir, tail))


# --- Task paneli -------------------------------------------------------------
def _close_button_flag():
    try:
        flag = QtWidgets.QDialogButtonBox.StandardButton.Close
    except AttributeError:
        flag = QtWidgets.QDialogButtonBox.Close
    return int(getattr(flag, "value", flag))


def _make_box(title):
    w = QtWidgets.QWidget()
    w.setWindowTitle(title)
    return w


def _tight(layout):
    layout.setContentsMargins(0, 0, 0, 0)
    return layout


class _TurntableTaskPanel:

    def __init__(self, controller):
        self.ctl = controller
        self.is_open = False
        self._building = True
        s = controller.settings

        # Kutu 1: Kontrol (Play/Stop + durum)
        self.box_ctl = _make_box("ColorPalette Turntable")
        lay = _tight(QtWidgets.QVBoxLayout(self.box_ctl))
        self.btn_play = QtWidgets.QPushButton("Play")
        self.btn_play.setObjectName("cpTurntablePlay")   # QSS: QPushButton#cpTurntablePlay { ... }
        play_font = self.btn_play.font()
        play_font.setBold(True)
        self.btn_play.setFont(play_font)
        self.lbl_status = QtWidgets.QLabel("")
        self.lbl_status.setWordWrap(True)
        lay.addWidget(self.btn_play)
        lay.addWidget(self.lbl_status)

        # Kutu 2: Pivot
        self.box_pivot = _make_box("Camera focus (pivot)")
        lay = _tight(QtWidgets.QVBoxLayout(self.box_pivot))
        self.rb_all = QtWidgets.QRadioButton("Center of all objects")
        self.rb_sel = QtWidgets.QRadioButton("Center of selected object(s)")
        self.chk_aim = QtWidgets.QCheckBox("Re-center view on the pivot")
        lay.addWidget(self.rb_all)
        lay.addWidget(self.rb_sel)
        lay.addWidget(self.chk_aim)

        # Kutu 3: Eksen
        self.box_axis = _make_box("Rotation axis")
        lay = _tight(QtWidgets.QVBoxLayout(self.box_axis))
        self.rb_ground = QtWidgets.QRadioButton("Ground plane")
        self.cmb_ground = QtWidgets.QComboBox()
        for label, _n in _GROUND_PLANES:
            self.cmb_ground.addItem(label)
        self.rb_combo = QtWidgets.QRadioButton("Axis combination")
        combo_row = QtWidgets.QHBoxLayout()
        self.chk_axes = []
        for name in ("X", "Y", "Z"):
            cb = QtWidgets.QCheckBox(name)
            self.chk_axes.append(cb)
            combo_row.addWidget(cb)
        combo_row.addStretch(1)
        hint = QtWidgets.QLabel(
            "Ground plane: the camera turns parallel to the floor. "
            "Combination: checked axes are summed into one axis (e.g. X+Z)."
        )
        hint.setWordWrap(True)
        lay.addWidget(self.rb_ground)
        lay.addWidget(self.cmb_ground)
        lay.addWidget(self.rb_combo)
        lay.addLayout(combo_row)
        lay.addWidget(hint)

        # Kutu 4: Hareket
        self.box_motion = _make_box("Motion")
        form = _tight(QtWidgets.QFormLayout(self.box_motion))
        self.spn_speed = QtWidgets.QDoubleSpinBox()
        self.spn_speed.setRange(1.0, 360.0)
        self.spn_speed.setDecimals(1)
        self.spn_speed.setSuffix(" \u00b0/s")
        self.chk_reverse = QtWidgets.QCheckBox("Reverse direction")
        self.cmb_path = QtWidgets.QComboBox()
        for label in _PATHS:
            self.cmb_path.addItem(label)
        self.cmb_sketch = QtWidgets.QComboBox()
        self.cmb_sketch.setToolTip("Sketch whose curve the camera follows")
        self.btn_sketch_refresh = QtWidgets.QPushButton("Refresh")
        self.btn_sketch_refresh.setToolTip("Refresh the sketch list (picks the sketch selected in the tree)")
        sketch_row = QtWidgets.QHBoxLayout()
        sketch_row.addWidget(self.cmb_sketch, 1)
        sketch_row.addWidget(self.btn_sketch_refresh)
        self.chk_angular = QtWidgets.QCheckBox("Constant view rotation speed")
        self.chk_angular.setToolTip(
            "On: the view turns around the pivot at the set \u00b0/s (like the circle). "
            "Off: the camera moves at constant speed along the sketch line."
        )
        self.lbl_sketch_hint = QtWidgets.QLabel(
            "Sketch path works with the ground plane only (choose XY / XZ / YZ under Rotation "
            "axis); the sketch must lie on that plane. The camera moves right above the sketch "
            "line at a constant height and always looks at the pivot. The height is chosen so the "
            "first frame keeps your current view angle - use \"Center of selected object(s)\" "
            "to focus on specific objects."
        )
        self.lbl_sketch_hint.setWordWrap(True)
        form.addRow("Camera path", self.cmb_path)
        form.addRow("Sketch", sketch_row)
        form.addRow("", self.chk_angular)
        form.addRow(self.lbl_sketch_hint)
        form.addRow("Speed", self.spn_speed)
        form.addRow("", self.chk_reverse)

        # Kutu 5: Video kaydi
        self.box_rec = _make_box("Record video")
        rform = _tight(QtWidgets.QFormLayout(self.box_rec))
        self.edt_path = QtWidgets.QLineEdit()
        self.btn_browse = QtWidgets.QPushButton("...")
        self.btn_browse.setMaximumWidth(32)
        path_row = QtWidgets.QHBoxLayout()
        path_row.addWidget(self.edt_path, 1)
        path_row.addWidget(self.btn_browse)
        self.cmb_res = QtWidgets.QComboBox()
        for label, _sz in _RESOLUTIONS:
            self.cmb_res.addItem(label)
        self.spn_fps = QtWidgets.QSpinBox()
        self.spn_fps.setRange(5, 60)
        self.spn_fps.setSuffix(" fps")
        self.spn_secs = QtWidgets.QDoubleSpinBox()
        self.spn_secs.setRange(1.0, 300.0)
        self.spn_secs.setDecimals(1)
        self.spn_secs.setSuffix(" s")
        self.spn_turns = QtWidgets.QSpinBox()
        self.spn_turns.setRange(1, 20)
        self.cmb_bg = QtWidgets.QComboBox()
        for label in _BACKGROUNDS:
            self.cmb_bg.addItem(label)
        self.chk_keep = QtWidgets.QCheckBox("Keep PNG frames")
        self.edt_ffmpeg = QtWidgets.QLineEdit()
        self.edt_ffmpeg.setReadOnly(True)            # elle yazilmaz / yapistirilmaz: "..." ile secilir
        self.edt_ffmpeg.setPlaceholderText("auto (PATH) - use ... to select")
        self.btn_ffmpeg = QtWidgets.QPushButton("...")
        self.btn_ffmpeg.setMaximumWidth(32)
        self.btn_ffmpeg.setToolTip("Select the ffmpeg executable")
        self.btn_ffmpeg_clear = QtWidgets.QPushButton("\u00d7")
        self.btn_ffmpeg_clear.setMaximumWidth(28)
        self.btn_ffmpeg_clear.setToolTip("Clear (auto-detect ffmpeg)")
        ffmpeg_row = QtWidgets.QHBoxLayout()
        ffmpeg_row.addWidget(self.edt_ffmpeg, 1)
        ffmpeg_row.addWidget(self.btn_ffmpeg)
        ffmpeg_row.addWidget(self.btn_ffmpeg_clear)
        self.btn_rec = QtWidgets.QPushButton("Record video")
        self.btn_rec.setObjectName("cpTurntableRecord")
        rec_font = self.btn_rec.font()
        rec_font.setBold(True)
        self.btn_rec.setFont(rec_font)
        self.prg = QtWidgets.QProgressBar()
        self.prg.setRange(0, 1000)
        self.prg.setValue(0)
        self.lbl_rec = QtWidgets.QLabel("")
        self.lbl_rec.setWordWrap(True)
        self.btn_open = QtWidgets.QPushButton("Open folder")
        self.btn_open.setVisible(False)          # yalnizca basarili kayittan sonra gorunur
        rec_msg_row = QtWidgets.QHBoxLayout()
        rec_msg_row.addWidget(self.lbl_rec, 1)
        rec_msg_row.addWidget(self.btn_open, 0, QtCore.Qt.AlignTop)
        rform.addRow("Save Location", path_row)
        rform.addRow("Resolution", self.cmb_res)
        rform.addRow("Frame rate", self.spn_fps)
        rform.addRow("Seconds / turn", self.spn_secs)
        rform.addRow("Turns", self.spn_turns)
        rform.addRow("Background", self.cmb_bg)
        rform.addRow("ffmpeg", ffmpeg_row)
        rform.addRow("", self.chk_keep)
        rform.addRow(self.btn_rec)
        rform.addRow(self.prg)
        rform.addRow(rec_msg_row)

        self.form = [self.box_ctl, self.box_pivot, self.box_axis, self.box_motion, self.box_rec]

        if controller.recorder is None:
            controller.recorder = _Recorder(controller)
        self.rec = controller.recorder
        self.rec.on_state = self._on_rec_state

        # Ayarlardan arayuze
        (self.rb_sel if s.pivot_selected else self.rb_all).setChecked(True)
        self.chk_aim.setChecked(s.aim)
        (self.rb_ground if (s.use_ground or s.path_type == 1) else self.rb_combo).setChecked(True)
        self.cmb_ground.setCurrentIndex(s.ground_index)
        for cb, val in zip(self.chk_axes, s.axes):
            cb.setChecked(val)
        self.spn_speed.setValue(s.speed)
        self.chk_reverse.setChecked(s.reverse)
        self.cmb_path.setCurrentIndex(s.path_type)
        self.chk_angular.setChecked(s.sketch_angular)
        self._refresh_sketches(False)
        self.edt_path.setText(s.rec_path)
        self.cmb_res.setCurrentIndex(s.rec_res)
        self.spn_fps.setValue(s.rec_fps)
        self.spn_secs.setValue(s.rec_secs)
        self.spn_turns.setValue(s.rec_turns)
        self.cmb_bg.setCurrentIndex(s.rec_bg)
        self.chk_keep.setChecked(s.rec_keep)
        self.edt_ffmpeg.setText(s.rec_ffmpeg)
        self._update_enabled()
        self._building = False

        # Sinyaller
        for w in (self.rb_all, self.rb_sel, self.chk_aim, self.rb_ground, self.rb_combo,
                  self.chk_reverse, *self.chk_axes):
            w.toggled.connect(self._on_changed)
        self.cmb_ground.currentIndexChanged.connect(self._on_changed)
        self.spn_speed.valueChanged.connect(self._on_changed)
        self.cmb_path.currentIndexChanged.connect(self._on_path_changed)
        self.cmb_sketch.currentIndexChanged.connect(self._on_changed)
        self.btn_sketch_refresh.clicked.connect(self._on_sketch_refresh)
        self.chk_angular.toggled.connect(self._on_changed)
        self.btn_play.clicked.connect(self.ctl.toggle)
        self.edt_path.textChanged.connect(self._on_changed)
        self.edt_ffmpeg.textChanged.connect(self._on_changed)
        self.cmb_res.currentIndexChanged.connect(self._on_changed)
        self.cmb_bg.currentIndexChanged.connect(self._on_changed)
        self.spn_fps.valueChanged.connect(self._on_changed)
        self.spn_secs.valueChanged.connect(self._on_changed)
        self.spn_turns.valueChanged.connect(self._on_changed)
        self.chk_keep.toggled.connect(self._on_changed)
        self.btn_browse.clicked.connect(self._browse)
        self.btn_ffmpeg.clicked.connect(self._browse_ffmpeg)
        self.btn_ffmpeg_clear.clicked.connect(self.edt_ffmpeg.clear)
        self.btn_rec.clicked.connect(self._toggle_rec)
        self.btn_open.clicked.connect(self._open_folder)

        self.ctl.on_state_changed = self._on_state
        self._on_state(self.ctl.is_running(), "")

    # --- FreeCAD TaskDialog arayuzu ---
    def getStandardButtons(self):
        return _close_button_flag()

    def clicked(self, button):
        pass

    def open(self):
        self.is_open = True

    def accept(self):
        self._cleanup()
        return True

    def reject(self):
        self._cleanup()
        return True

    def isAllowedAlterDocument(self):
        return True

    # --- Ic mantik ---
    def _cleanup(self):
        self.ctl.stop()
        self.rec.cancel()
        self.rec.on_state = None
        self.ctl.settings.save()
        self.ctl.on_state_changed = None
        self.is_open = False

    def _update_enabled(self):
        ground = self.rb_ground.isChecked() or self.cmb_path.currentIndex() == 1
        self.cmb_ground.setEnabled(ground)
        for cb in self.chk_axes:
            cb.setEnabled(not ground)
        sketch = (self.cmb_path.currentIndex() == 1)
        self.cmb_sketch.setEnabled(sketch)
        self.btn_sketch_refresh.setEnabled(sketch)
        self.chk_angular.setEnabled(sketch)
        self.lbl_sketch_hint.setVisible(sketch)
        self.rb_combo.setEnabled(not sketch)    # skec yolunda yalnizca zemin duzlemi
        self.chk_aim.setEnabled(not sketch)     # skec yolunda kamera zaten pivota bakar

    def _on_changed(self, *_):
        if self._building:
            return
        s = self.ctl.settings
        s.pivot_selected = self.rb_sel.isChecked()
        s.aim = self.chk_aim.isChecked()
        s.use_ground = self.rb_ground.isChecked()
        s.ground_index = self.cmb_ground.currentIndex()
        s.axes = [cb.isChecked() for cb in self.chk_axes]
        s.speed = self.spn_speed.value()
        s.reverse = self.chk_reverse.isChecked()
        s.path_type = self.cmb_path.currentIndex()
        s.sketch_angular = self.chk_angular.isChecked()
        s.sketch_name = self.cmb_sketch.currentData() or ""
        s.rec_path = self.edt_path.text()
        s.rec_res = self.cmb_res.currentIndex()
        s.rec_fps = self.spn_fps.value()
        s.rec_secs = self.spn_secs.value()
        s.rec_turns = self.spn_turns.value()
        s.rec_bg = self.cmb_bg.currentIndex()
        s.rec_keep = self.chk_keep.isChecked()
        s.rec_ffmpeg = self.edt_ffmpeg.text()
        self._update_enabled()
        s.save()
        # Hiz / yon aninda etkili; pivot ve eksen degisimi icin yeniden hazirla
        self.ctl.refresh()

    def _on_state(self, running, message):
        self.btn_play.setText("Stop" if running else "Play")
        if message:
            self.lbl_status.setText(message)

    def _sketch_items(self):
        items = []
        doc = FreeCAD.ActiveDocument
        if doc is not None:
            for o in doc.Objects:
                try:
                    if o.isDerivedFrom("Sketcher::SketchObject"):
                        items.append((o.Label, o.Name))
                except Exception:
                    pass
        return items

    def _refresh_sketches(self, prefer_selection):
        want = self.ctl.settings.sketch_name
        if prefer_selection:
            try:
                import FreeCADGui as Gui
                for o in Gui.Selection.getSelection():
                    if o.isDerivedFrom("Sketcher::SketchObject"):
                        want = o.Name
                        break
            except Exception:
                pass
        self.cmb_sketch.blockSignals(True)
        self.cmb_sketch.clear()
        self.cmb_sketch.addItem("(choose a sketch)", "")
        for label, name in self._sketch_items():
            self.cmb_sketch.addItem(label, name)
        idx = self.cmb_sketch.findData(want) if want else 0
        self.cmb_sketch.setCurrentIndex(idx if idx > 0 else 0)
        self.cmb_sketch.blockSignals(False)
        self.ctl.settings.sketch_name = self.cmb_sketch.currentData() or ""

    def _on_sketch_refresh(self):
        self._refresh_sketches(True)
        self._on_changed()

    def _on_path_changed(self, *_):
        if not self._building and self.cmb_path.currentIndex() == 1:
            self.rb_ground.setChecked(True)      # skec yolu: yalnizca zemin duzlemi
            self._refresh_sketches(False)        # listeyi guncelle; skeci kullanici secer
        self._on_changed()

    def _browse(self):
        start = self.edt_path.text() or os.path.expanduser("~")
        path, _flt = QtWidgets.QFileDialog.getSaveFileName(
            self.box_rec, "Save video", start, "MP4 video (*.mp4);;QuickTime (*.mov);;Matroska (*.mkv)"
        )
        if path:
            self.edt_path.setText(path)

    def _browse_ffmpeg(self):
        cur = (self.edt_ffmpeg.text() or "").strip()
        start = os.path.dirname(cur) if cur else os.path.dirname(resolve_ffmpeg("") or "")
        start = start or os.path.expanduser("~")
        if os.name == "nt":
            flt = "ffmpeg (ffmpeg.exe);;Programs (*.exe);;All files (*)"
        else:
            flt = "ffmpeg (ffmpeg);;All files (*)"
        path, _flt = QtWidgets.QFileDialog.getOpenFileName(
            self.box_rec, "Select ffmpeg executable", start, flt
        )
        if not path:
            return
        path = os.path.normpath(path)
        if os.path.basename(path).lower().startswith("ffmpeg"):
            self.lbl_rec.setText("ffmpeg: %s" % path)
        else:
            self.lbl_rec.setText("Warning: the selected file does not look like ffmpeg: %s"
                                 % os.path.basename(path))
        self.edt_ffmpeg.setText(path)      # textChanged -> _on_changed -> ayar kaydedilir

    def _open_folder(self):
        path = self.rec.last_saved
        if path:
            _reveal_in_folder(path)

    def _toggle_rec(self):
        if self.rec.is_active():
            self.rec.cancel()
        else:
            self.rec.start()

    def _on_rec_state(self, active, message, progress):
        self.btn_rec.setText("Cancel" if active else "Record video")
        self.btn_play.setEnabled(not active)
        if progress is not None:
            self.prg.setRange(0, 1000)
            self.prg.setValue(int(progress * 1000))
        elif active:
            self.prg.setRange(0, 0)     # belirsiz ilerleme (ffmpeg kodlaniyor)
        else:
            self.prg.setRange(0, 1000)
            self.prg.setValue(0)
        if message:
            self.lbl_rec.setText(message)
        self.btn_open.setVisible(bool(self.rec.last_saved) and not active)


# --- Disariya acik API -------------------------------------------------------
_controller = None
_panel = None


def _get_controller():
    global _controller
    if _controller is None:
        _controller = _Controller()
    return _controller


def show_panel():
    global _panel
    import FreeCADGui as Gui

    if _panel is not None and _panel.is_open:
        try:
            Gui.Control.showTaskView()
        except Exception:
            pass
        return

    try:
        other_active = bool(Gui.Control.activeDialog())
    except Exception:
        other_active = False
    if other_active:
        FreeCAD.Console.PrintWarning(
            "ColorPalette: baska bir gorev paneli acik; once onu kapatin, sonra Turntable'i acin.\n"
        )
        return

    panel = _TurntableTaskPanel(_get_controller())
    try:
        Gui.Control.showDialog(panel)
    except Exception as e:
        panel._cleanup()
        FreeCAD.Console.PrintError("ColorPalette: Turntable paneli acilamadi - %s\n" % e)
        return
    _panel = panel


# Menu dosyasi (colorpalette_menu.py) bu adi cagirir; geriye uyumluluk icin korundu.
show_dialog = show_panel


def stop():
    if _controller is not None:
        _controller.stop()
