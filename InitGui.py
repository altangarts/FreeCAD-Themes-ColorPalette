import os
import FreeCAD

def _is_colorpalette_theme_active():

    param = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/MainWindow")
    current_theme = param.GetString("StyleSheet", "").lower()
    
    return "colorpalette" in current_theme or "color-palette" in current_theme

if _is_colorpalette_theme_active():
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
        _spec_grid = importlib.util.spec_from_file_location(
            "colorpalette_grid",
            os.path.join(_mod_dir, "colorpalette_grid.py")
        )
        _mod_grid = importlib.util.module_from_spec(_spec_grid)
        _spec_grid.loader.exec_module(_mod_grid)
    except Exception as e:
        FreeCAD.Console.PrintError(f"ColorPalette: colorpalette_grid yuklenemedi - {str(e)}\n")


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

else:
    # İsteğe bağlı olarak, geliştirme aşamasında temanın aktif olmadığını görmek için log bırakabilirsiniz.
    FreeCAD.Console.PrintMessage("ColorPalette temasi aktif degil, eklenti modulleri baslatilmadi.\n")