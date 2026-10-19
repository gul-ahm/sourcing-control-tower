import altair as alt

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_MUTED = "#52514e"
GRID = "#e6e5e1"

SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
SEQ_BLUE = ["#cde2fb", "#9ec5f4", "#5598e7", "#2a78d6", "#1c5cab", "#104281"]

GOOD = "#0ca30c"
WARNING = "#fab219"
SERIOUS = "#ec835a"
CRITICAL = "#d03b3b"

TREND_COLORS = {"improving": GOOD, "stable": INK_MUTED, "deteriorating": CRITICAL}


def chart_theme():
    return {
        "config": {
            "background": SURFACE,
            "font": "Inter, Segoe UI, system-ui, sans-serif",
            "title": {"color": INK, "fontSize": 14, "fontWeight": 600, "anchor": "start"},
            "axis": {
                "labelColor": INK_MUTED, "titleColor": INK_MUTED,
                "gridColor": GRID, "domainColor": GRID, "tickColor": GRID,
                "labelFontSize": 11, "titleFontSize": 11, "titlePadding": 8,
            },
            "legend": {"labelColor": INK_MUTED, "titleColor": INK_MUTED,
                       "labelFontSize": 11, "titleFontSize": 11, "symbolType": "square"},
            "view": {"stroke": "transparent"},
            "range": {"category": SERIES, "heatmap": SEQ_BLUE, "ramp": SEQ_BLUE},
        }
    }


alt.themes.register("sourcing", chart_theme)
alt.themes.enable("sourcing")
