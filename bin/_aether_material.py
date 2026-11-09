"""Pure CSS construction shared by GTK surface adapters; imports no toolkit.

Atmosphere belongs around an opaque working surface. Static light, inner
highlights and an asymmetric rim express suspension without fading content.
"""
from _cyber_theme import BG, BG_CARD, FG, LINE, ACCENT2, PURPLE, rgba


def surface_declarations(radius=20):
    return f"""
    background-color: {BG};
    background-image:
        radial-gradient(ellipse at 100% 0%, {rgba(ACCENT2, .085)}, transparent 50%),
        radial-gradient(ellipse at 0% 5%, {rgba(PURPLE, .14)}, transparent 55%),
        linear-gradient(170deg, {BG_CARD}, {BG});
    border: 1px solid {LINE};
    border-top-color: {rgba(ACCENT2, .48)};
    border-right-color: {rgba(PURPLE, .40)};
    border-radius: {int(radius)}px;
    box-shadow: inset 0 1px {rgba(FG, .04)}, inset 0 -1px {rgba(BG, .75)},
                0 18px 48px {rgba(BG, .78)}, 0 0 28px {rgba(PURPLE, .15)};
    animation: none;
"""
