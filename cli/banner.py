"""Argus ASCII art banner and branding constants."""

from rich.text import Text

# Teal → Cyan → Blue → Purple gradient
GRADIENT_COLORS = [
    "#00FFD1",
    "#00C8FF",
    "#0090FF",
    "#5B5CFF",
    "#9B30FF",
]

ARGUS_LOGO = [
    " █████  ██████   ██████  ██    ██ ███████",
    "██   ██ ██   ██ ██       ██    ██ ██     ",
    "███████ ██████  ██   ███ ██    ██ ███████",
    "██   ██ ██   ██ ██    ██ ██    ██      ██",
    "██   ██ ██   ██  ██████   ██████  ███████",
]

TAGLINE = "The All-Seeing Code Reviewer"

# Severity colors
SEVERITY_COLORS = {
    "critical": "#FF3366",
    "warning": "#FFAA00",
    "suggestion": "#00D4FF",
}

# Category labels
CATEGORY_LABELS = {
    "bug": "Bug",
    "security": "Security",
    "performance": "Performance",
    "style": "Style",
    "architecture": "Architecture",
}

# UI colors
PRIMARY = "#00D4FF"
SECONDARY = "#5B5CFF"
ACCENT = "#9B30FF"
DIM_TEXT = "#6B7280"
BORDER_COLOR = "#1E3A5F"
BG_HIGHLIGHT = "#0D1B2A"


def render_logo() -> Text:
    """Render the ARGUS logo with gradient colors."""
    text = Text()
    for i, line in enumerate(ARGUS_LOGO):
        color = GRADIENT_COLORS[i % len(GRADIENT_COLORS)]
        text.append(line, style=f"bold {color}")
        if i < len(ARGUS_LOGO) - 1:
            text.append("\n")
    return text


def render_tagline() -> Text:
    """Render the tagline with subtle styling."""
    text = Text()
    text.append(TAGLINE, style=f"italic {DIM_TEXT}")
    return text


def render_mini_logo() -> Text:
    """Render a small inline logo for headers."""
    text = Text()
    text.append("◉ ", style=f"bold {PRIMARY}")
    text.append("ARGUS", style=f"bold {GRADIENT_COLORS[2]}")
    return text
