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
            "color_palette_workbench_combobox",
            os.path.join(_mod_dir, "workbench_combobox.py")
        )
        _mod_fix = importlib.util.module_from_spec(_spec_fix)
        _spec_fix.loader.exec_module(_mod_fix)
    except Exception as e:
        FreeCAD.Console.PrintError(f"ColorPalette: workbench_combobox yuklenemedi - {str(e)}\n")


    try:
        def _apply_task_panel_style_fix():
            try:
                import FreeCADGui as Gui
                from PySide6 import QtCore

                mw = Gui.getMainWindow()
                targets = mw.findChildren(object, "Tasks")

                for w in targets:
                    w.setAttribute(QtCore.Qt.WA_StyledBackground, True)
                    w.style().unpolish(w)
                    w.style().polish(w)
                    w.update()

                if not targets:
                    FreeCAD.Console.PrintError("ColorPalette: Task paneli (Tasks) bulunamadi, WA_StyledBackground uygulanamadi.\n")
            except Exception as e:
                FreeCAD.Console.PrintError(f"ColorPalette: task_panel_style_fix calisirken hata - {str(e)}\n")

        from PySide6 import QtCore
        QtCore.QTimer.singleShot(0, _apply_task_panel_style_fix)
    except Exception as e:
        FreeCAD.Console.PrintError(f"ColorPalette: task_panel_style_fix kurulamadi - {str(e)}\n")

else:
    FreeCAD.Console.PrintMessage("ColorPalette temasi aktif degil, eklenti modulleri baslatilmadi.\n")