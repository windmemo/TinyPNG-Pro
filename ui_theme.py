# ============================================================
# TinyPNG Pro — UI Theme System
# 统一管理「普通(明亮)」/「夜间(暗色)」两套配色与全部样式模板。
# 通过 current 代理在运行时读取当前激活主题，搭配 f-string 即可实现即时换肤。
# ============================================================


class Theme:
    def __init__(self, **kw):
        self.__dict__.update(kw)


# ---------------- Dark (夜间 · 深空钴墨) ----------------
DARK = Theme(
    mode='dark',
    label='夜间',
    # Surfaces
    bg="#0F1115", soft="#14161C", card="#171A21", elev="#1E222B", video="#11141A",
    # Brand accent
    primary="#7C5CFF", primary2="#5AC8FF", primary_h="#9680FF",
    primary_press="#6A48E6", primary2_press="#4FB4E8",
    btn_edge="rgba(255,255,255,0.20)",
    secondary="#5AC8FF",
    focus_ring="#7C5CFF",
    # Foreground
    fg="#EDEDF2", muted="#9CA3AF", dim="#6B7280",
    # Border
    border="#2A2E3A", border_strong="#3A4150",
    # Semantic
    success="#34D399", success_bg="#0E2A22",
    error="#F87171", error_bg="#2B1616",
    warning="#FBBF24",
    # Chips (状态胶囊)
    chip_ok_bg="rgba(52,211,153,0.14)", chip_ok_fg="#6EE7B7", chip_ok_border="rgba(52,211,153,0.36)",
    chip_err_bg="rgba(248,113,113,0.14)", chip_err_fg="#FCA5A5", chip_err_border="rgba(248,113,113,0.36)",
    chip_warn_bg="rgba(251,191,36,0.14)", chip_warn_fg="#FCD34D", chip_warn_border="rgba(251,191,36,0.36)",
    chip_info_bg="rgba(124,92,255,0.16)", chip_info_fg="#B7A6FF", chip_info_border="rgba(124,92,255,0.40)",
    chip_idle_bg="rgba(148,163,184,0.13)", chip_idle_fg="#CBD5E1", chip_idle_border="rgba(148,163,184,0.30)",
    # Meter
    meter_bg="#232733",
    # 阴影 (r,g,b,a) —— 供 QColor(*current.shadow) 使用
    shadow=(0, 0, 0, 150),
    # Drop-zone tint (rgba alpha)
    dz_1="rgba(124,92,255,", dz_2="rgba(90,200,255,",
    # Radius
    radius_sm="8px", radius_md="10px", radius_lg="16px", pill="20px",
    # Check icon tint
    check_tint="#FFFFFF",
    # Fonts
    font='Inter, "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif',
    mono_font='"JetBrains Mono", "Cascadia Mono", "Consolas", monospace',
    size_xs="11px", size_sm="12px", size_md="13px", size_lg="16px",
    size_xl="17px", size_2xl="22px",
)


# ---------------- Light (普通 · 明亮) ----------------
LIGHT = Theme(
    mode='light',
    label='普通',
    # Surfaces
    bg="#EEF1F5", soft="#FFFFFF", card="#FFFFFF", elev="#E4E8EE", video="#FAFBFD",
    # Brand accent
    primary="#6D4BFF", primary2="#0EA5E9", primary_h="#8B6BFF",
    primary_press="#5A3AD0", primary2_press="#0B87C4",
    btn_edge="rgba(255,255,255,0.55)",
    secondary="#0EA5E9",
    focus_ring="#6D4BFF",
    # Foreground
    fg="#111418", muted="#3F4A59", dim="#6C7480",
    # Border
    border="#D4DAE3", border_strong="#BFC7D2",
    # Semantic
    success="#059669", success_bg="#E8F8F1",
    error="#DC2626", error_bg="#FDEEEE",
    warning="#B45309",
    # Chips (状态胶囊)
    chip_ok_bg="#E8F8F1", chip_ok_fg="#047857", chip_ok_border="#A7E3CB",
    chip_err_bg="#FDEEEE", chip_err_fg="#B91C1C", chip_err_border="#F5C2C2",
    chip_warn_bg="#FEF6E7", chip_warn_fg="#92400E", chip_warn_border="#F2D08A",
    chip_info_bg="#EEEBFF", chip_info_fg="#4C1D95", chip_info_border="#CFC4FF",
    chip_idle_bg="#EFF2F6", chip_idle_fg="#475569", chip_idle_border="#D4DAE3",
    # Meter
    meter_bg="#E4E8EE",
    # 阴影 (r,g,b,a)
    shadow=(15, 23, 42, 55),
    # Drop-zone tint
    dz_1="rgba(124,92,255,", dz_2="rgba(14,165,233,",
    # Radius
    radius_sm="8px", radius_md="10px", radius_lg="16px", pill="20px",
    # Check icon tint
    check_tint="#FFFFFF",
    # Fonts
    font='Inter, "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif',
    mono_font='"JetBrains Mono", "Cascadia Mono", "Consolas", monospace',
    size_xs="11px", size_sm="12px", size_md="13px", size_lg="16px",
    size_xl="17px", size_2xl="22px",
)


_active = DARK


class _AttrProxy:
    """按需转发属性访问到当前激活主题，确保用 f-string 就能得到当次主题值。"""

    def __getattr__(self, name):
        return getattr(_active, name)


current = _AttrProxy()


def set_theme(mode):
    """切换激活主题；mode ∈ {'dark','light'}。"""
    global _active
    _active = DARK if mode == 'dark' else LIGHT


def current_mode():
    return _active.mode


def theme_label():
    """返回当前主题的中文名（普通/夜间）。"""
    return _active.label


# ============================================================
# 样式模板生成函数（每次调用读取当前主题）
# ============================================================

def checkbox_style():
    return f"""
    QCheckBox {{
        font-family: {current.font};
        font-size: {current.size_sm};
        color: {current.muted};
        spacing: 8px;
        padding: 3px 0;
        background: transparent;
    }}
    QCheckBox:hover {{ color: {current.fg}; }}
    QCheckBox::indicator {{
        width: 17px;
        height: 17px;
        border-radius: 5px;
        border: 2px solid {current.border};
        background: {current.video};
    }}
    QCheckBox::indicator:hover {{ border-color: {current.primary2}; }}
    QCheckBox::indicator:checked {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                    stop:0 {current.primary}, stop:1 {current.primary2});
        border-color: transparent;
    }}
"""


def pill_toggle_style():
    """胶囊开关样式：QCheckBox 换皮为 iOS 风格滑块（用于底部自动压缩/替换原文件）。

    完全使用 QSS 原生属性绘制：关闭=灰色胶囊底，开启=品牌渐变胶囊底。
    不使用 image/SVG（Qt 对 QSS 内 SVG data URI 渲染不可靠，会导致指示器不可见）。
    """
    return f"""
    QCheckBox {{
        font-family: {current.font};
        font-size: {current.size_sm};
        font-weight: 600;
        color: {current.muted};
        spacing: 10px;
        padding: 4px 2px;
        background: transparent;
    }}
    QCheckBox:hover {{ color: {current.fg}; }}
    QCheckBox::indicator {{
        width: 38px;
        height: 20px;
        border: 1px solid {current.border_strong};
        border-radius: 10px;
        background: {current.elev};
    }}
    QCheckBox::indicator:hover {{ border-color: {current.primary2}; }}
    QCheckBox::indicator:pressed {{ background: {current.border}; }}
    QCheckBox::indicator:checked {{
        border: 1px solid transparent;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 {current.primary}, stop:1 {current.primary2});
    }}
    QCheckBox::indicator:checked:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 {current.primary_h}, stop:1 {current.primary2});
    }}
"""


def radio_style():
    return f"""
    QRadioButton {{
        font-family: {current.font};
        font-size: {current.size_sm};
        color: {current.muted};
        spacing: 8px;
        padding: 2px 0;
    }}
    QRadioButton:hover {{ color: {current.fg}; }}
    QRadioButton::indicator {{
        width: 17px;
        height: 17px;
        border-radius: 9px;
        border: 2px solid {current.border};
        background: {current.video};
    }}
    QRadioButton::indicator:hover {{ border-color: {current.primary2}; }}
    QRadioButton::indicator:checked {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                    stop:0 {current.primary}, stop:1 {current.primary2});
        border-color: transparent;
    }}
"""


def primary_btn():
    return f"""
    QPushButton {{
        font-family: {current.font};
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 {current.primary}, stop:1 {current.primary2});
        color: #FFFFFF;
        border: 1px solid {current.btn_edge};
        border-radius: {current.pill};
        font-size: {current.size_sm};
        font-weight: 600;
        padding: 9px 24px;
        min-width: 90px;
    }}
    QPushButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 {current.primary_h}, stop:1 {current.primary2});
        border: 1px solid {current.btn_edge};
    }}
    QPushButton:pressed {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 {current.primary_press}, stop:1 {current.primary2_press});
        border: 1px solid rgba(255,255,255,0.10);
    }}
    QPushButton:disabled {{
        background: {current.elev};
        color: {current.dim};
        border-color: {current.border};
    }}
"""


def accent_outline_btn():
    """强调色描边按钮：用于「应用」等次级主操作。"""
    return f"""
    QPushButton {{
        font-family: {current.font};
        background: transparent;
        color: {current.primary2};
        border: 1px solid {current.focus_ring};
        border-radius: {current.pill};
        font-size: {current.size_sm};
        font-weight: 600;
        padding: 7px 18px;
        min-width: 72px;
    }}
    QPushButton:hover {{
        background: {current.dz_1}0.12);
        border-color: {current.primary2};
        color: {current.fg};
    }}
    QPushButton:pressed {{ background: {current.dz_1}0.20); }}
"""


def ghost_btn():
    return f"""
    QPushButton {{
        font-family: {current.font};
        background: {current.elev};
        color: {current.muted};
        border: 1px solid {current.border};
        border-radius: {current.pill};
        font-size: {current.size_sm};
        font-weight: 600;
        padding: 7px 18px;
        min-width: 64px;
    }}
    QPushButton:hover {{
        background: {current.card};
        color: {current.fg};
        border-color: {current.primary2};
    }}
    QPushButton:pressed {{ background: {current.video}; }}
"""


def icon_btn():
    return f"""
    QPushButton {{
        font-family: {current.font};
        background: {current.elev};
        color: {current.muted};
        border: 1px solid {current.border};
        border-radius: {current.radius_md};
        font-size: 15px;
        font-weight: 600;
        padding: 0px;
        min-width: 32px;
        min-height: 32px;
    }}
    QPushButton:hover {{
        background: {current.card};
        color: {current.fg};
        border-color: {current.primary2};
    }}
    QPushButton:pressed {{ background: {current.video}; }}
"""


def card_style():
    return f"""
    QFrame {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                    stop:0 {current.card}, stop:1 {current.video});
        border: 1px solid {current.border};
        border-radius: {current.radius_lg};
    }}
"""


def title_bar_style():
    """顶部应用栏容器（软件名 + 版本 + 快捷按钮）。"""
    return f"""
    QFrame#headerBar {{
        background: {current.soft};
        border: 1px solid {current.border};
        border-radius: {current.radius_lg};
    }}
"""


def chip_style(kind='idle'):
    """状态胶囊：kind ∈ {ok, err, warn, info, idle}。"""
    table = {
        'ok': (current.chip_ok_bg, current.chip_ok_fg, current.chip_ok_border),
        'err': (current.chip_err_bg, current.chip_err_fg, current.chip_err_border),
        'warn': (current.chip_warn_bg, current.chip_warn_fg, current.chip_warn_border),
        'info': (current.chip_info_bg, current.chip_info_fg, current.chip_info_border),
        'idle': (current.chip_idle_bg, current.chip_idle_fg, current.chip_idle_border),
    }
    bg, fg, bd = table.get(kind, table['idle'])
    return f"""
    QLabel {{
        font-family: {current.font};
        font-size: {current.size_xs};
        font-weight: 700;
        color: {fg};
        background: {bg};
        border: 1px solid {bd};
        border-radius: {current.pill};
        padding: 3px 12px;
    }}
"""


def meter_style():
    """细额度条（本月压缩额度 / 批量进度）。"""
    return f"""
    QProgressBar {{
        font-family: {current.font};
        background: {current.meter_bg};
        border: none;
        border-radius: 4px;
        height: 8px;
        text-align: center;
        color: transparent;
        font-size: 0px;
    }}
    QProgressBar::chunk {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 {current.primary}, stop:1 {current.primary2});
        border-radius: 4px;
    }}
"""


def drop_zone_style():
    return f"""
    QFrame {{
        background: qlineargradient(x1:1, y1:0, x2:0, y2:1,
                                    stop:0 {current.dz_1}0.06), stop:1 {current.dz_2}0.05));
        border: 1px solid {current.border};
        border-radius: {current.radius_lg};
    }}
"""


def drop_zone_hover_style():
    return f"""
    QFrame {{
        background: qlineargradient(x1:1, y1:0, x2:0, y2:1,
                                    stop:0 {current.dz_1}0.16), stop:1 {current.dz_2}0.12));
        border: 1.5px dashed {current.primary2};
        border-radius: {current.radius_lg};
    }}
"""


def result_style():
    return f"""
    QLabel {{
        font-family: {current.font};
        font-size: {current.size_sm};
        color: {current.dim};
        padding: 2px;
        selection-background-color: {current.primary};
    }}
"""


def status_bar_style():
    return f"""
    QFrame {{
        background: {current.soft};
        border: 1px solid {current.border};
        border-radius: {current.radius_lg};
    }}
"""


def input_style():
    return f"""
    QLineEdit {{
        font-family: {current.font};
        background: {current.video};
        border: 1px solid {current.border};
        border-radius: {current.radius_sm};
        padding: 7px 10px;
        font-size: {current.size_sm};
        color: {current.fg};
        selection-background-color: {current.primary};
    }}
    QLineEdit:focus {{ border-color: {current.primary2}; }}
    QLineEdit::placeholder {{ color: {current.dim}; }}
"""


def spin_style():
    return f"""
    QSpinBox {{
        font-family: {current.font};
        background: {current.video};
        border: 1px solid {current.border};
        border-radius: {current.radius_sm};
        padding: 6px 8px;
        font-size: {current.size_sm};
        color: {current.fg};
    }}
    QSpinBox:focus {{ border-color: {current.primary2}; }}
    QSpinBox::up-button, QSpinBox::down-button {{
        background: {current.elev};
        border: none;
        width: 20px;
    }}
    QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
        background: {current.border};
    }}
"""


def group_style():
    return f"""
    QGroupBox {{
        font-family: {current.font};
        font-size: {current.size_sm};
        font-weight: 700;
        color: {current.fg};
        border: 1px solid {current.border};
        border-radius: {current.radius_lg};
        margin-top: 10px;
        padding: 16px 12px 10px 12px;
        background: {current.card};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 14px;
        padding: 0 8px 0 0;
        color: {current.primary};
    }}
"""


def list_style():
    return f"""
    QListWidget {{
        font-family: {current.font};
        background: {current.video};
        border: 1px solid {current.border};
        border-radius: {current.radius_sm};
        padding: 4px;
        font-size: {current.size_sm};
        color: {current.muted};
        min-height: 96px;
        outline: none;
    }}
    QListWidget::item {{ padding: 6px 10px; border-radius: 4px; }}
    QListWidget::item:hover {{ background: {current.elev}; color: {current.fg}; }}
    QListWidget::item:selected {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 {current.primary}, stop:1 {current.primary2});
        color: #FFFFFF;
    }}
"""


def tab_style():
    return f"""
    QTabWidget::pane {{
        border: 1px solid {current.border};
        border-radius: 0 0 {current.radius_lg} {current.radius_lg};
        background: {current.bg};
        top: -1px;
    }}
    QTabBar::tab {{
        font-family: {current.font};
        background: {current.card};
        color: {current.dim};
        padding: 9px 36px;
        font-size: {current.size_sm};
        font-weight: 600;
        border: 1px solid {current.border};
        border-bottom: none;
        border-radius: {current.radius_md} {current.radius_md} 0 0;
        margin-right: 2px;
        min-width: 90px;
    }}
    QTabBar::tab:selected {{
        background: {current.bg};
        color: {current.primary};
        border-color: {current.border};
    }}
    QTabBar::tab:hover:!selected {{ background: {current.elev}; color: {current.fg}; }}
"""


def menu_style():
    return f"""
    QMenu {{
        font-family: {current.font};
        background: {current.card};
        color: {current.fg};
        border: 1px solid {current.border};
        border-radius: {current.radius_md};
        padding: 6px;
        font-size: {current.size_sm};
    }}
    QMenu::item {{
        padding: 7px 20px 7px 14px;
        border-radius: 6px;
    }}
    QMenu::item:selected {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 {current.primary}, stop:1 {current.primary2});
        color: #FFFFFF;
    }}
    QMenu::separator {{
        height: 1px;
        background: {current.border};
        margin: 5px 8px;
    }}
"""


def label_style():
    return f"""
    QLabel {{
        font-family: {current.font};
        font-size: {current.size_sm};
        color: {current.muted};
    }}
"""


def scroll_area_style():
    """设置面板的滚动区 + 细滚动条样式。"""
    return f"""
    QScrollArea {{
        border: none;
        background: transparent;
    }}
    QScrollBar:vertical {{
        background: {current.video};
        width: 6px;
        border-radius: 3px;
    }}
    QScrollBar::handle:vertical {{
        background: {current.border_strong};
        border-radius: 3px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {current.dim}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
"""


def text_box_style():
    """帮助/关于弹窗中的只读文本区。"""
    return f"""
    QTextEdit {{
        background: {current.card};
        border: 1px solid {current.border};
        border-radius: {current.radius_md};
        padding: 16px;
        font-family: {current.font};
        font-size: {current.size_sm};
        color: {current.muted};
        line-height: 1.7;
        selection-background-color: {current.primary};
    }}
"""
