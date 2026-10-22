from xml.etree.ElementTree import Element, SubElement, ElementTree

ASCII = r"""
       ___
    \ /   \ /
     <[] []>
    /_|___|_\
 ___/  | |  \___
       | |
       | |
       | |
    ___| |___
   /___| |___\
"""

CELL_W = 24
CELL_H = 24

MARGIN_X = 50
MARGIN_Y = 50

STROKE = "#a855ff"
STROKE_WIDTH = 4


def add_line(parent, x1, y1, x2, y2):
    SubElement(
        parent,
        "line",
        {
            "x1": str(x1),
            "y1": str(y1),
            "x2": str(x2),
            "y2": str(y2),
        },
    )


lines = ASCII.splitlines()

max_cols = max(len(line) for line in lines)

svg_w = max_cols * CELL_W + MARGIN_X * 2
svg_h = len(lines) * CELL_H + 250

svg = Element(
    "svg",
    {
        "xmlns": "http://www.w3.org/2000/svg",
        "viewBox": f"0 0 {svg_w} {svg_h}",
    },
)

SubElement(
    svg,
    "rect",
    {
        "width": "100%",
        "height": "100%",
        "fill": "#09000f",
    },
)

defs = SubElement(svg, "defs")

filt = SubElement(
    defs,
    "filter",
    {
        "id": "glow",
        "x": "-50%",
        "y": "-50%",
        "width": "200%",
        "height": "200%",
    },
)

SubElement(
    filt,
    "feGaussianBlur",
    {
        "stdDeviation": "4",
        "result": "blur",
    },
)

merge = SubElement(filt, "feMerge")

SubElement(merge, "feMergeNode", {"in": "blur"})
SubElement(merge, "feMergeNode", {"in": "SourceGraphic"})

g = SubElement(
    svg,
    "g",
    {
        "stroke": STROKE,
        "stroke-width": str(STROKE_WIDTH),
        "stroke-linecap": "square",
        "fill": "none",
        "filter": "url(#glow)",
    },
)

for row, line in enumerate(lines):

    for col, ch in enumerate(line):

        x = MARGIN_X + col * CELL_W
        y = MARGIN_Y + row * CELL_H

        if ch == "_":
            add_line(
                g,
                x,
                y + CELL_H * 0.75,
                x + CELL_W,
                y + CELL_H * 0.75,
            )

        elif ch == "|":
            add_line(
                g,
                x + CELL_W / 2,
                y,
                x + CELL_W / 2,
                y + CELL_H,
            )

        elif ch == "/":
            add_line(
                g,
                x,
                y + CELL_H,
                x + CELL_W,
                y,
            )

        elif ch == "\\":
            add_line(
                g,
                x,
                y,
                x + CELL_W,
                y + CELL_H,
            )

        elif ch == "<":
            add_line(
                g,
                x + CELL_W,
                y,
                x,
                y + CELL_H / 2,
            )
            add_line(
                g,
                x,
                y + CELL_H / 2,
                x + CELL_W,
                y + CELL_H,
            )

        elif ch == ">":
            add_line(
                g,
                x,
                y,
                x + CELL_W,
                y + CELL_H / 2,
            )
            add_line(
                g,
                x + CELL_W,
                y + CELL_H / 2,
                x,
                y + CELL_H,
            )

        elif ch == "[":
            add_line(g, x + CELL_W * 0.8, y, x + CELL_W * 0.2, y)
            add_line(g, x + CELL_W * 0.2, y, x + CELL_W * 0.2, y + CELL_H)
            add_line(
                g,
                x + CELL_W * 0.2,
                y + CELL_H,
                x + CELL_W * 0.8,
                y + CELL_H,
            )

        elif ch == "]":
            add_line(g, x + CELL_W * 0.2, y, x + CELL_W * 0.8, y)
            add_line(g, x + CELL_W * 0.8, y, x + CELL_W * 0.8, y + CELL_H)
            add_line(
                g,
                x + CELL_W * 0.2,
                y + CELL_H,
                x + CELL_W * 0.8,
                y + CELL_H,
            )

text_y = len(lines) * CELL_H + 140

SubElement(
    svg,
    "text",
    {
        "x": str(svg_w / 2),
        "y": str(text_y),
        "text-anchor": "middle",
        "font-family": "Cascadia Mono",
        "font-size": "56",
        "fill": "#d8b4ff",
        "filter": "url(#glow)",
    },
).text = "stretch___beatz"

ElementTree(svg).write(
    "stretch_beatz_grid.svg",
    encoding="utf-8",
    xml_declaration=True,
)