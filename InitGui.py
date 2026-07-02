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
except Exception as e:
    FreeCAD.Console.PrintError(f"ColorPalette: viewport_color_sync yuklenemedi - {str(e)}\n")


try:
    import importlib.util
    _spec_editor = importlib.util.spec_from_file_location(
        "color_palette_dynamic_editor",
        os.path.join(_mod_dir, "dynamic_property_editor.py")
    )
    _mod_editor = importlib.util.module_from_spec(_spec_editor)
    _spec_editor.loader.exec_module(_mod_editor)
except Exception as e:
    FreeCAD.Console.PrintError(f"ColorPalette: dynamic_property_editor yuklenemedi - {str(e)}\n")


try:
    import importlib.util
    _spec_fix = importlib.util.spec_from_file_location(
        "color_palette_general_fix",
        os.path.join(_mod_dir, "general_fix.py")
    )
    _mod_fix = importlib.util.module_from_spec(_spec_fix)
    _spec_fix.loader.exec_module(_mod_fix)
except Exception as e:
    FreeCAD.Console.PrintError(f"ColorPalette: general_fix yuklenemedi - {str(e)}\n")