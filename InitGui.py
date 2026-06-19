import os
import FreeCAD

_mod_dir = os.path.join(FreeCAD.getUserAppDataDir(), "Mod", "Color-Palette-Theme")

try:
    import importlib.util
    _spec = importlib.util.spec_from_file_location(
        "color_palette_theme_sync",
        os.path.join(_mod_dir, "viewport_color_sync.py")
    )
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    FreeCAD.Console.PrintMessage("Color-Palette-Theme: viewport_color_sync.py yuklendi\n")
except Exception as e:
    FreeCAD.Console.PrintError(f"Color-Palette-Theme yuklenemedi: {e}\n")