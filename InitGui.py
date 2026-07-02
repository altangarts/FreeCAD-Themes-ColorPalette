import os
import FreeCAD

_mod_dir = os.path.join(FreeCAD.getUserAppDataDir(), "Mod", "Color-Palette-Theme")

# 1. Viewport Renk Senkronizasyonu
try:
    import importlib.util
    _spec = importlib.util.spec_from_file_location(
        "color_palette_theme_sync",
        os.path.join(_mod_dir, "viewport_color_sync.py")
    )
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
except Exception as e:
    FreeCAD.Console.PrintError(f"ColorPalette: viewport_color_sync yuklenemedi - {str(e)}\n")

# 2. Overlay Property Editor
try:
    import importlib.util
    _spec_overlay = importlib.util.spec_from_file_location(
        "color_palette_overlay_editor",
        os.path.join(_mod_dir, "overlay_property_editor.py")
    )
    _mod_overlay = importlib.util.module_from_spec(_spec_overlay)
    _spec_overlay.loader.exec_module(_mod_overlay)
except Exception as e:
    FreeCAD.Console.PrintError(f"ColorPalette: overlay_property_editor yuklenemedi - {str(e)}\n")

# 3. Genel Düzeltmeler (Toolbar & Task Panel)
try:
    import importlib.util
    _spec_general = importlib.util.spec_from_file_location(
        "color_palette_general_fix",
        os.path.join(_mod_dir, "general_fix.py")
    )
    _mod_general = importlib.util.module_from_spec(_spec_general)
    _spec_general.loader.exec_module(_mod_general)
except Exception as e:
    FreeCAD.Console.PrintError(f"ColorPalette: general_fix yuklenemedi - {str(e)}\n")