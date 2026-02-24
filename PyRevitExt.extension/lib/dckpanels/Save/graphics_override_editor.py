# -*- coding: utf-8 -*-
"""Graphics override editor for filter view settings."""

import clr

clr.AddReference("System")
clr.AddReference("System.Windows.Forms")
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")
clr.AddReference("RevitAPI")

import System.Windows.Media as WinMedia
from Autodesk.Revit.DB import (
    Color,
    ElementId,
    FillPatternElement,
    FillPatternTarget,
    FilteredElementCollector,
    LinePatternElement,
    OverrideGraphicSettings,
)
from System.Drawing import Color as DrawColor
from System.Windows.Forms import ColorDialog, DialogResult


# =================== Data model ===================
class GraphicsOverrideModel(object):
    """Data model for OverrideGraphicSettings editing."""

    def __init__(self, view, filter_id, doc):
        ovr = view.GetFilterOverrides(filter_id)
        self.proj_line_weight = ovr.ProjectionLineWeight
        self.proj_line_color = _revit_to_rgb(ovr.ProjectionLineColor)
        self.proj_line_pattern_id = ovr.ProjectionLinePatternId

        self.surf_fg_visible = ovr.IsSurfaceForegroundPatternVisible
        self.surf_fg_pattern_id = ovr.SurfaceForegroundPatternId
        self.surf_fg_color = _revit_to_rgb(ovr.SurfaceForegroundPatternColor)

        self.surf_bg_visible = ovr.IsSurfaceBackgroundPatternVisible
        self.surf_bg_pattern_id = ovr.SurfaceBackgroundPatternId
        self.surf_bg_color = _revit_to_rgb(ovr.SurfaceBackgroundPatternColor)

        self.transparency = ovr.Transparency
        self.halftone = ovr.Halftone

        self.cut_line_weight = ovr.CutLineWeight
        self.cut_line_color = _revit_to_rgb(ovr.CutLineColor)
        self.cut_line_pattern_id = ovr.CutLinePatternId

        self.cut_fg_visible = ovr.IsCutForegroundPatternVisible
        self.cut_fg_pattern_id = ovr.CutForegroundPatternId
        self.cut_fg_color = _revit_to_rgb(ovr.CutForegroundPatternColor)

        self.cut_bg_visible = ovr.IsCutBackgroundPatternVisible
        self.cut_bg_pattern_id = ovr.CutBackgroundPatternId
        self.cut_bg_color = _revit_to_rgb(ovr.CutBackgroundPatternColor)


def _revit_to_rgb(color):
    """Convert Revit Color to (R, G, B) tuple."""
    if not color or not color.IsValid:
        return None
    return (color.Red, color.Green, color.Blue)


def _rgb_to_revit(rgb):
    """Convert (R, G, B) tuple to Revit Color."""
    if not rgb:
        return Color(255, 255, 255)
    return Color(rgb[0], rgb[1], rgb[2])


def _is_no_override_color(rgb):
    """Check if color is default (no override)."""
    return rgb is None or rgb == (255, 255, 255)


# =================== Pattern collectors ===================
_line_patterns_cache = None
_fill_patterns_cache = None


def collect_line_patterns(doc):
    """Return list of (name, ElementId)."""
    global _line_patterns_cache
    if _line_patterns_cache is not None:
        return _line_patterns_cache
    patterns = FilteredElementCollector(doc).OfClass(LinePatternElement).ToElements()
    result = [("Нет переопределения", ElementId.InvalidElementId)]
    for p in sorted(patterns, key=lambda x: x.Name):
        result.append((p.Name, p.Id))
    _line_patterns_cache = result
    return result


def collect_fill_patterns(doc):
    """Return list of (name, ElementId) — drafting only."""
    global _fill_patterns_cache
    if _fill_patterns_cache is not None:
        return _fill_patterns_cache
    patterns = FilteredElementCollector(doc).OfClass(FillPatternElement).ToElements()
    result = [("Нет переопределения", ElementId.InvalidElementId)]
    for p in sorted(patterns, key=lambda x: x.Name):
        fp = p.GetFillPattern()
        if not fp:
            continue
        if fp.Target != FillPatternTarget.Drafting:
            continue
        result.append((p.Name, p.Id))
    _fill_patterns_cache = result
    return result


def clear_pattern_caches():
    """Clear pattern caches between editor sessions."""
    global _line_patterns_cache, _fill_patterns_cache
    _line_patterns_cache = None
    _fill_patterns_cache = None


# =================== Color picker ===================
def pick_color(current_rgb):
    """Open Windows color picker dialog."""
    dlg = ColorDialog()
    dlg.AllowFullOpen = True
    dlg.FullOpen = True
    if current_rgb:
        dlg.Color = DrawColor.FromArgb(current_rgb[0], current_rgb[1], current_rgb[2])
    if dlg.ShowDialog() == DialogResult.OK:
        c = dlg.Color
        return (c.R, c.G, c.B)
    return None


def _rgb_to_brush(rgb):
    """Convert (R,G,B) to WPF SolidColorBrush."""
    if not rgb:
        return WinMedia.SolidColorBrush(WinMedia.Color.FromRgb(255, 255, 255))
    return WinMedia.SolidColorBrush(WinMedia.Color.FromRgb(rgb[0], rgb[1], rgb[2]))


# =================== Override detection ===================
def has_non_default_override(view, filter_id):
    """Check if filter has any non-default graphic overrides."""
    ovr = view.GetFilterOverrides(filter_id)
    if ovr.ProjectionLineWeight != -1:
        return True
    if not _is_no_override_color(_revit_to_rgb(ovr.ProjectionLineColor)):
        return True
    if ovr.ProjectionLinePatternId != ElementId.InvalidElementId:
        return True
    if not _is_no_override_color(_revit_to_rgb(ovr.SurfaceForegroundPatternColor)):
        return True
    if ovr.SurfaceForegroundPatternId != ElementId.InvalidElementId:
        return True
    if not _is_no_override_color(_revit_to_rgb(ovr.SurfaceBackgroundPatternColor)):
        return True
    if ovr.SurfaceBackgroundPatternId != ElementId.InvalidElementId:
        return True
    if ovr.Transparency != 0:
        return True
    if ovr.Halftone:
        return True
    if ovr.CutLineWeight != -1:
        return True
    if not _is_no_override_color(_revit_to_rgb(ovr.CutLineColor)):
        return True
    if ovr.CutLinePatternId != ElementId.InvalidElementId:
        return True
    if not _is_no_override_color(_revit_to_rgb(ovr.CutForegroundPatternColor)):
        return True
    if ovr.CutForegroundPatternId != ElementId.InvalidElementId:
        return True
    if not _is_no_override_color(_revit_to_rgb(ovr.CutBackgroundPatternColor)):
        return True
    if ovr.CutBackgroundPatternId != ElementId.InvalidElementId:
        return True
    return False


def get_indicator_brush(view, filter_id):
    """Get SolidColorBrush for override indicator."""
    ovr = view.GetFilterOverrides(filter_id)
    rgb = _revit_to_rgb(ovr.ProjectionLineColor)
    if not _is_no_override_color(rgb):
        return _rgb_to_brush(rgb)
    rgb = _revit_to_rgb(ovr.SurfaceForegroundPatternColor)
    if not _is_no_override_color(rgb):
        return _rgb_to_brush(rgb)
    # Accent fallback
    return WinMedia.SolidColorBrush(WinMedia.Color.FromRgb(0x5F, 0x9E, 0xA0))


# =================== Build override settings ===================
def build_override_settings(model):
    """Build OverrideGraphicSettings from GraphicsOverrideModel."""
    ovr = OverrideGraphicSettings()

    if model.proj_line_weight != -1:
        ovr.SetProjectionLineWeight(model.proj_line_weight)
    if not _is_no_override_color(model.proj_line_color):
        ovr.SetProjectionLineColor(_rgb_to_revit(model.proj_line_color))
    if model.proj_line_pattern_id != ElementId.InvalidElementId:
        ovr.SetProjectionLinePatternId(model.proj_line_pattern_id)

    ovr.SetSurfaceForegroundPatternVisible(model.surf_fg_visible)
    if model.surf_fg_pattern_id != ElementId.InvalidElementId:
        ovr.SetSurfaceForegroundPatternId(model.surf_fg_pattern_id)
    if not _is_no_override_color(model.surf_fg_color):
        ovr.SetSurfaceForegroundPatternColor(_rgb_to_revit(model.surf_fg_color))

    ovr.SetSurfaceBackgroundPatternVisible(model.surf_bg_visible)
    if model.surf_bg_pattern_id != ElementId.InvalidElementId:
        ovr.SetSurfaceBackgroundPatternId(model.surf_bg_pattern_id)
    if not _is_no_override_color(model.surf_bg_color):
        ovr.SetSurfaceBackgroundPatternColor(_rgb_to_revit(model.surf_bg_color))

    if model.transparency > 0:
        ovr.SetSurfaceTransparency(model.transparency)
    ovr.SetHalftone(model.halftone)

    if model.cut_line_weight != -1:
        ovr.SetCutLineWeight(model.cut_line_weight)
    if not _is_no_override_color(model.cut_line_color):
        ovr.SetCutLineColor(_rgb_to_revit(model.cut_line_color))
    if model.cut_line_pattern_id != ElementId.InvalidElementId:
        ovr.SetCutLinePatternId(model.cut_line_pattern_id)

    ovr.SetCutForegroundPatternVisible(model.cut_fg_visible)
    if model.cut_fg_pattern_id != ElementId.InvalidElementId:
        ovr.SetCutForegroundPatternId(model.cut_fg_pattern_id)
    if not _is_no_override_color(model.cut_fg_color):
        ovr.SetCutForegroundPatternColor(_rgb_to_revit(model.cut_fg_color))

    ovr.SetCutBackgroundPatternVisible(model.cut_bg_visible)
    if model.cut_bg_pattern_id != ElementId.InvalidElementId:
        ovr.SetCutBackgroundPatternId(model.cut_bg_pattern_id)
    if not _is_no_override_color(model.cut_bg_color):
        ovr.SetCutBackgroundPatternColor(_rgb_to_revit(model.cut_bg_color))

    return ovr


# =================== Graphics tab XAML ===================
GRAPHICS_TAB_XAML = """
<ScrollViewer
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    VerticalScrollBarVisibility="Auto"
    HorizontalScrollBarVisibility="Disabled"
    Padding="4">
<StackPanel Margin="8">

    <!-- Projection / Surface -->
    <TextBlock Text="Проекция / Поверхность"
        FontWeight="SemiBold" FontSize="13" Foreground="#5F9EA0"
        Margin="0,0,0,10"/>

    <!-- Projection lines -->
    <TextBlock Text="Линии" FontSize="11" FontWeight="SemiBold"
        Foreground="#666" Margin="0,0,0,4"/>
    <Grid Margin="8,0,0,8">
        <Grid.ColumnDefinitions>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
        </Grid.ColumnDefinitions>
        <TextBlock Grid.Column="0" Text="Толщина" FontSize="10"
            Foreground="#888" VerticalAlignment="Center" Margin="0,0,4,0"/>
        <ComboBox x:Name="ProjLineWeight" Grid.Column="1"
            Width="55" Height="24" FontSize="11" Margin="0,0,16,0"/>
        <TextBlock Grid.Column="2" Text="Цвет" FontSize="10"
            Foreground="#888" VerticalAlignment="Center" Margin="0,0,4,0"/>
        <Button x:Name="BtnProjLineColor" Grid.Column="3"
            Width="24" Height="24" BorderBrush="#CCC" BorderThickness="1"
            Cursor="Hand" Margin="0,0,16,0" ToolTip="Выбрать цвет"/>
        <TextBlock Grid.Column="4" Text="Образец" FontSize="10"
            Foreground="#888" VerticalAlignment="Center" Margin="0,0,4,0"/>
        <ComboBox x:Name="ProjLinePattern" Grid.Column="5"
            Width="200" Height="24" FontSize="11"/>
    </Grid>

    <!-- Surface foreground -->
    <TextBlock Text="Штриховка - Передний план" FontSize="11" FontWeight="SemiBold"
        Foreground="#666" Margin="0,0,0,4"/>
    <Grid Margin="8,0,0,8">
        <Grid.ColumnDefinitions>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
        </Grid.ColumnDefinitions>
        <CheckBox x:Name="SurfFgVisible" Grid.Column="0"
            Content="Видимость" FontSize="10" VerticalAlignment="Center"
            Margin="0,0,16,0" IsChecked="True"/>
        <TextBlock Grid.Column="1" Text="Образец" FontSize="10"
            Foreground="#888" VerticalAlignment="Center" Margin="0,0,4,0"/>
        <ComboBox x:Name="SurfFgPattern" Grid.Column="2"
            Width="200" Height="24" FontSize="11" Margin="0,0,16,0"/>
        <TextBlock Grid.Column="3" Text="Цвет" FontSize="10"
            Foreground="#888" VerticalAlignment="Center" Margin="0,0,4,0"/>
        <Button x:Name="BtnSurfFgColor" Grid.Column="4"
            Width="24" Height="24" BorderBrush="#CCC" BorderThickness="1"
            Cursor="Hand"/>
    </Grid>

    <!-- Surface background -->
    <TextBlock Text="Штриховка - Фон" FontSize="11" FontWeight="SemiBold"
        Foreground="#666" Margin="0,0,0,4"/>
    <Grid Margin="8,0,0,8">
        <Grid.ColumnDefinitions>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
        </Grid.ColumnDefinitions>
        <CheckBox x:Name="SurfBgVisible" Grid.Column="0"
            Content="Видимость" FontSize="10" VerticalAlignment="Center"
            Margin="0,0,16,0" IsChecked="True"/>
        <TextBlock Grid.Column="1" Text="Образец" FontSize="10"
            Foreground="#888" VerticalAlignment="Center" Margin="0,0,4,0"/>
        <ComboBox x:Name="SurfBgPattern" Grid.Column="2"
            Width="200" Height="24" FontSize="11" Margin="0,0,16,0"/>
        <TextBlock Grid.Column="3" Text="Цвет" FontSize="10"
            Foreground="#888" VerticalAlignment="Center" Margin="0,0,4,0"/>
        <Button x:Name="BtnSurfBgColor" Grid.Column="4"
            Width="24" Height="24" BorderBrush="#CCC" BorderThickness="1"
            Cursor="Hand"/>
    </Grid>

    <!-- Transparency -->
    <TextBlock Text="Прозрачность" FontSize="11" FontWeight="SemiBold"
        Foreground="#666" Margin="0,0,0,4"/>
    <Grid Margin="8,0,0,12">
        <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="40"/>
        </Grid.ColumnDefinitions>
        <Slider x:Name="TransparencySlider" Grid.Column="0"
            Minimum="0" Maximum="100" Value="0"
            TickFrequency="5" IsSnapToTickEnabled="True"
            VerticalAlignment="Center"/>
        <TextBlock x:Name="TransparencyValue" Grid.Column="1"
            FontSize="11" Foreground="#333"
            VerticalAlignment="Center" Margin="8,0,0,0" Text="0%"/>
    </Grid>

    <Separator Margin="0,4,0,8"/>

    <!-- Cut -->
    <TextBlock Text="Разрез"
        FontWeight="SemiBold" FontSize="13" Foreground="#5F9EA0"
        Margin="0,0,0,10"/>

    <!-- Cut lines -->
    <TextBlock Text="Линии" FontSize="11" FontWeight="SemiBold"
        Foreground="#666" Margin="0,0,0,4"/>
    <Grid Margin="8,0,0,8">
        <Grid.ColumnDefinitions>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
        </Grid.ColumnDefinitions>
        <TextBlock Grid.Column="0" Text="Толщина" FontSize="10"
            Foreground="#888" VerticalAlignment="Center" Margin="0,0,4,0"/>
        <ComboBox x:Name="CutLineWeight" Grid.Column="1"
            Width="55" Height="24" FontSize="11" Margin="0,0,16,0"/>
        <TextBlock Grid.Column="2" Text="Цвет" FontSize="10"
            Foreground="#888" VerticalAlignment="Center" Margin="0,0,4,0"/>
        <Button x:Name="BtnCutLineColor" Grid.Column="3"
            Width="24" Height="24" BorderBrush="#CCC" BorderThickness="1"
            Cursor="Hand" Margin="0,0,16,0" ToolTip="Выбрать цвет"/>
        <TextBlock Grid.Column="4" Text="Образец" FontSize="10"
            Foreground="#888" VerticalAlignment="Center" Margin="0,0,4,0"/>
        <ComboBox x:Name="CutLinePattern" Grid.Column="5"
            Width="200" Height="24" FontSize="11"/>
    </Grid>

    <!-- Cut foreground -->
    <TextBlock Text="Штриховка - Передний план" FontSize="11" FontWeight="SemiBold"
        Foreground="#666" Margin="0,0,0,4"/>
    <Grid Margin="8,0,0,8">
        <Grid.ColumnDefinitions>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
        </Grid.ColumnDefinitions>
        <CheckBox x:Name="CutFgVisible" Grid.Column="0"
            Content="Видимость" FontSize="10" VerticalAlignment="Center"
            Margin="0,0,16,0" IsChecked="True"/>
        <TextBlock Grid.Column="1" Text="Образец" FontSize="10"
            Foreground="#888" VerticalAlignment="Center" Margin="0,0,4,0"/>
        <ComboBox x:Name="CutFgPattern" Grid.Column="2"
            Width="200" Height="24" FontSize="11" Margin="0,0,16,0"/>
        <TextBlock Grid.Column="3" Text="Цвет" FontSize="10"
            Foreground="#888" VerticalAlignment="Center" Margin="0,0,4,0"/>
        <Button x:Name="BtnCutFgColor" Grid.Column="4"
            Width="24" Height="24" BorderBrush="#CCC" BorderThickness="1"
            Cursor="Hand"/>
    </Grid>

    <!-- Cut background -->
    <TextBlock Text="Штриховка - Фон" FontSize="11" FontWeight="SemiBold"
        Foreground="#666" Margin="0,0,0,4"/>
    <Grid Margin="8,0,0,8">
        <Grid.ColumnDefinitions>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
        </Grid.ColumnDefinitions>
        <CheckBox x:Name="CutBgVisible" Grid.Column="0"
            Content="Видимость" FontSize="10" VerticalAlignment="Center"
            Margin="0,0,16,0" IsChecked="True"/>
        <TextBlock Grid.Column="1" Text="Образец" FontSize="10"
            Foreground="#888" VerticalAlignment="Center" Margin="0,0,4,0"/>
        <ComboBox x:Name="CutBgPattern" Grid.Column="2"
            Width="200" Height="24" FontSize="11" Margin="0,0,16,0"/>
        <TextBlock Grid.Column="3" Text="Цвет" FontSize="10"
            Foreground="#888" VerticalAlignment="Center" Margin="0,0,4,0"/>
        <Button x:Name="BtnCutBgColor" Grid.Column="4"
            Width="24" Height="24" BorderBrush="#CCC" BorderThickness="1"
            Cursor="Hand"/>
    </Grid>

    <Separator Margin="0,4,0,8"/>

    <!-- Halftone -->
    <CheckBox x:Name="HalftoneCheck"
        Content="Полутона" FontSize="11" Margin="0,4,0,0"/>

</StackPanel>
</ScrollViewer>
"""


# =================== UI setup ===================
def _populate_line_weight_combo(combo, current_value):
    """Fill line weight ComboBox."""
    combo.Items.Clear()
    combo.Items.Add("Нет")
    for i in range(1, 17):
        combo.Items.Add(str(i))
    if current_value == -1:
        combo.SelectedIndex = 0
    elif 1 <= current_value <= 16:
        combo.SelectedIndex = current_value
    else:
        combo.SelectedIndex = 0


def _get_line_weight_value(combo):
    """Read line weight from ComboBox."""
    idx = combo.SelectedIndex
    if idx <= 0:
        return -1
    return idx


def _populate_pattern_combo(combo, patterns, current_id):
    """Fill pattern ComboBox with text names only."""
    combo.Items.Clear()
    combo.Tag = []
    ids_list = []
    selected_idx = 0
    for i, entry in enumerate(patterns):
        combo.Items.Add(entry[0])
        ids_list.append(entry[1])
        if entry[1] == current_id:
            selected_idx = i
    combo.Tag = ids_list
    combo.SelectedIndex = selected_idx


def _get_pattern_id(combo):
    """Read selected pattern ElementId from ComboBox."""
    ids_list = combo.Tag
    idx = combo.SelectedIndex
    if not ids_list or idx < 0 or idx >= len(ids_list):
        return ElementId.InvalidElementId
    return ids_list[idx]


def _set_color_button(btn, rgb):
    """Set button background from RGB tuple."""
    btn.Background = _rgb_to_brush(rgb)
    btn.Tag = rgb


def _make_color_handler(btn, model, attr_name):
    """Create click handler for color button."""

    def handler(s, e):
        current = getattr(model, attr_name)
        result = pick_color(current)
        if result is not None:
            setattr(model, attr_name, result)
            _set_color_button(btn, result)

    return handler


def setup_graphics_tab(content, model, doc):
    """Initialize graphics tab controls with model data."""
    line_patterns = collect_line_patterns(doc)
    fill_patterns = collect_fill_patterns(doc)

    # Projection lines
    proj_weight = content.FindName("ProjLineWeight")
    btn_proj_color = content.FindName("BtnProjLineColor")
    proj_pattern = content.FindName("ProjLinePattern")

    _populate_line_weight_combo(proj_weight, model.proj_line_weight)
    _set_color_button(btn_proj_color, model.proj_line_color)
    btn_proj_color.Click += _make_color_handler(
        btn_proj_color, model, "proj_line_color"
    )
    _populate_pattern_combo(proj_pattern, line_patterns, model.proj_line_pattern_id)

    # Surface foreground
    surf_fg_vis = content.FindName("SurfFgVisible")
    surf_fg_pat = content.FindName("SurfFgPattern")
    btn_surf_fg = content.FindName("BtnSurfFgColor")

    surf_fg_vis.IsChecked = model.surf_fg_visible
    _populate_pattern_combo(surf_fg_pat, fill_patterns, model.surf_fg_pattern_id)
    _set_color_button(btn_surf_fg, model.surf_fg_color)
    btn_surf_fg.Click += _make_color_handler(btn_surf_fg, model, "surf_fg_color")

    # Surface background
    surf_bg_vis = content.FindName("SurfBgVisible")
    surf_bg_pat = content.FindName("SurfBgPattern")
    btn_surf_bg = content.FindName("BtnSurfBgColor")

    surf_bg_vis.IsChecked = model.surf_bg_visible
    _populate_pattern_combo(surf_bg_pat, fill_patterns, model.surf_bg_pattern_id)
    _set_color_button(btn_surf_bg, model.surf_bg_color)
    btn_surf_bg.Click += _make_color_handler(btn_surf_bg, model, "surf_bg_color")

    # Transparency
    slider = content.FindName("TransparencySlider")
    label = content.FindName("TransparencyValue")
    slider.Value = model.transparency
    label.Text = "{}%".format(model.transparency)

    def on_slider(s, e):
        val = int(slider.Value)
        label.Text = "{}%".format(val)

    slider.ValueChanged += on_slider

    # Cut lines
    cut_weight = content.FindName("CutLineWeight")
    btn_cut_color = content.FindName("BtnCutLineColor")
    cut_pattern = content.FindName("CutLinePattern")

    _populate_line_weight_combo(cut_weight, model.cut_line_weight)
    _set_color_button(btn_cut_color, model.cut_line_color)
    btn_cut_color.Click += _make_color_handler(btn_cut_color, model, "cut_line_color")
    _populate_pattern_combo(cut_pattern, line_patterns, model.cut_line_pattern_id)

    # Cut foreground
    cut_fg_vis = content.FindName("CutFgVisible")
    cut_fg_pat = content.FindName("CutFgPattern")
    btn_cut_fg = content.FindName("BtnCutFgColor")

    cut_fg_vis.IsChecked = model.cut_fg_visible
    _populate_pattern_combo(cut_fg_pat, fill_patterns, model.cut_fg_pattern_id)
    _set_color_button(btn_cut_fg, model.cut_fg_color)
    btn_cut_fg.Click += _make_color_handler(btn_cut_fg, model, "cut_fg_color")

    # Cut background
    cut_bg_vis = content.FindName("CutBgVisible")
    cut_bg_pat = content.FindName("CutBgPattern")
    btn_cut_bg = content.FindName("BtnCutBgColor")

    cut_bg_vis.IsChecked = model.cut_bg_visible
    _populate_pattern_combo(cut_bg_pat, fill_patterns, model.cut_bg_pattern_id)
    _set_color_button(btn_cut_bg, model.cut_bg_color)
    btn_cut_bg.Click += _make_color_handler(btn_cut_bg, model, "cut_bg_color")

    # Halftone
    halftone = content.FindName("HalftoneCheck")
    halftone.IsChecked = model.halftone


def read_graphics_from_ui(content, model):
    """Read current UI state back into model."""
    model.proj_line_weight = _get_line_weight_value(content.FindName("ProjLineWeight"))
    model.proj_line_pattern_id = _get_pattern_id(content.FindName("ProjLinePattern"))

    model.surf_fg_visible = content.FindName("SurfFgVisible").IsChecked
    model.surf_fg_pattern_id = _get_pattern_id(content.FindName("SurfFgPattern"))
    model.surf_bg_visible = content.FindName("SurfBgVisible").IsChecked
    model.surf_bg_pattern_id = _get_pattern_id(content.FindName("SurfBgPattern"))

    model.transparency = int(content.FindName("TransparencySlider").Value)
    model.halftone = content.FindName("HalftoneCheck").IsChecked

    model.cut_line_weight = _get_line_weight_value(content.FindName("CutLineWeight"))
    model.cut_line_pattern_id = _get_pattern_id(content.FindName("CutLinePattern"))

    model.cut_fg_visible = content.FindName("CutFgVisible").IsChecked
    model.cut_fg_pattern_id = _get_pattern_id(content.FindName("CutFgPattern"))
    model.cut_bg_visible = content.FindName("CutBgVisible").IsChecked
    model.cut_bg_pattern_id = _get_pattern_id(content.FindName("CutBgPattern"))
