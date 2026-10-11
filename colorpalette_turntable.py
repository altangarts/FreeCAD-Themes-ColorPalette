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
_FRAMES_DIR_NAME = "CP Turntable Video"  

_RESOLUTIONS = (
    ("Current view size", None),
    ("1280 x 720", (1280, 720)),
    ("1920 x 1080", (1920, 1080)),
    ("2560 x 1440", (2560, 1440)),
    ("3840 x 2160", (3840, 2160)),
)
_BACKGROUNDS = ("Current", "White", "Black")  

_GROUND_PLANES = (
    ("XY plane  (Z is up)", (0.0, 0.0, 1.0)),
    ("XZ plane  (Y is up)", (0.0, 1.0, 0.0)),
    ("YZ plane  (X is up)", (1.0, 0.0, 0.0)),
)


# --- Saf vektor / kuaterniyon matematigi (Coin'den bagimsiz, test edilebilir) --
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


def _collect_boxes(selected_only):
    import FreeCADGui as Gui
    boxes = []
    if selected_only:
        for sel in Gui.Selection.getSelectionEx():
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


def compute_pivot(selected_only):
    boxes = _collect_boxes(selected_only)
    note = "selection" if selected_only else "all objects"
    if not boxes and selected_only:
        boxes = _collect_boxes(False)
        note = "all objects (nothing selected)"
    if not boxes:
        return None, "no visible geometry"
    bb = FreeCAD.BoundBox()
    for b in boxes:
        bb.add(b)
    c = bb.Center
    return (c.x, c.y, c.z), note


# --- Ayarlar -----------------------------------------------------------------
class _Settings:
    def __init__(self):
        self.pivot_selected = False   # False: tum nesneler, True: secili nesneler
        self.use_ground = True        # True: zemin duzlemi, False: eksen kombinasyonu
        self.ground_index = 0
        self.axes = [False, False, True]   # X, Y, Z (eksen kombinasyonu modu)
        self.speed = 20.0             # derece / saniye
        self.reverse = False
        self.aim = False              # kamerayi pivota cevir (varsayilan: kapali)
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
        if self.use_ground:
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
        if s.axis_vector() is None:
            self._notify("Select at least one axis.")
            return False

        pivot, note = compute_pivot(s.pivot_selected)
        if pivot is None:
            self._notify("Nothing to rotate around: %s." % note)
            return False
        self.pivot = pivot

        cam = view.getCameraNode()
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
        """Calisirken ayar degisti: pivotu / ekseni yeniden hazirla."""
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

        angle = math.radians(self.settings.speed) * dt
        if self.settings.reverse:
            angle = -angle

        cam = view.getCameraNode()
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
    """Dosya adinin yanina siradaki numarayi ekler: video.mp4 -> video_1.mp4, video_2.mp4 ...
    Klasordeki mevcut video_N.ext dosyalarina bakar, en buyuk N'in bir fazlasini kullanir;
    boylece onceki kayitlarin uzerine asla yazilmaz."""
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
        if os.path.isdir(p): 
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


def _attach_grid_for_capture(view):
    """Grid'i saveImage'in render ettigi koke (pcViewProviderRoot) da baglar.

    saveImage yalnizca nesne kokunu render eder; grid ise bir ust seviyedeki sahne
    kokune eklendigi icin resme girmez. Kayit suresince ayni grid dugumu nesne
    kokunun altina da baglanir (ayni malzeme/renk/seffaflik ayarlariyla).
    """
    from pivy import coin
    sg = view.getSceneGraph()

    sa = coin.SoSearchAction()
    sa.setName("ColorPaletteGridSwitch")
    sa.apply(sg)
    gp = sa.getPath()
    if gp is None:
        return None
    grid = gp.getTail()

    sb = coin.SoSearchAction()
    sb.setName("ObjectGroup")      # pcViewProviderRoot'un cocugu
    sb.apply(sg)
    op = sb.getPath()
    if op is None or op.getLength() < 2:
        return None
    parent = op.getNode(op.getLength() - 2)
    if parent.findChild(grid) >= 0:
        return None
    parent.insertChild(grid, 0)
    return parent, grid


def _detach_grid_after_capture(handle):
    if not handle:
        return
    parent, grid = handle
    try:
        idx = parent.findChild(grid)
        if idx >= 0:
            parent.removeChild(idx)
    except Exception:
        pass


class _Recorder:

    def __init__(self, controller):
        self.ctl = controller
        self._grid_handle = None
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
        if not self._find_ffmpeg():        
            self._notify("ffmpeg not found - select it with the \"...\" button next to ffmpeg. "
                         "Nothing was recorded.")
            return
        self.ctl.stop()                    
        if not self.ctl.prepare():         
            return
        view = _find_view()
        if view is None:
            self._notify("No active 3D view.")
            return

        out = _normalize_video_path(s.rec_path)
        if not out:
            self._notify("Choose an output file.")
            return
        out = _numbered_path(out)          # her kayit yeni numara alir, eskinin uzerine yazmaz
        out_dir = os.path.dirname(os.path.abspath(out))
        frames_dir = os.path.join(out_dir, _FRAMES_DIR_NAME)
        try:
            os.makedirs(frames_dir, exist_ok=True) 
            for name in os.listdir(frames_dir):  
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
        self._cam_state = _read_camera(view.getCameraNode())
        self._i = 0
        self._cancelled = False
        try:
            self._grid_handle = _attach_grid_for_capture(view)
        except Exception:
            self._grid_handle = None
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
        _detach_grid_after_capture(self._grid_handle)
        self._grid_handle = None
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
        rform.addRow("File", path_row)
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
        (self.rb_ground if s.use_ground else self.rb_combo).setChecked(True)
        self.cmb_ground.setCurrentIndex(s.ground_index)
        for cb, val in zip(self.chk_axes, s.axes):
            cb.setChecked(val)
        self.spn_speed.setValue(s.speed)
        self.chk_reverse.setChecked(s.reverse)
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
        ground = self.rb_ground.isChecked()
        self.cmb_ground.setEnabled(ground)
        for cb in self.chk_axes:
            cb.setEnabled(not ground)

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
        self.ctl.refresh()

    def _on_state(self, running, message):
        self.btn_play.setText("Stop" if running else "Play")
        if message:
            self.lbl_status.setText(message)

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
