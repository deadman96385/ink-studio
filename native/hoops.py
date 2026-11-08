"""Hoop sizes a project can be designed for. Shared by the server and its workers.

A project chooses one with project["hoop"] (an id below); projects without one are
PP1 projects, as every project was before larger hoops existed."""

HOOPS = {
    'pp1': {'id': 'pp1', 'w': 100.0, 'h': 100.0, 'label': 'Brother PP1 · 100 × 100 mm', 'short': '100 × 100'},
    '8x12': {'id': '8x12', 'w': 200.0, 'h': 300.0, 'label': '8 × 12 in · 200 × 300 mm', 'short': '200 × 300'},
}
DEFAULT = 'pp1'


def hoop(project) -> dict:
    key = project.get('hoop', DEFAULT) if isinstance(project, dict) else DEFAULT
    if key not in HOOPS:
        raise ValueError('Unknown hoop size.')
    return HOOPS[key]


def size(project) -> tuple[float, float]:
    h = hoop(project)
    return h['w'], h['h']


def largest(project) -> float:
    return max(size(project))


def inside(project, x, y, w, h, slack=.1) -> bool:
    hw, hh = size(project)
    return x >= -slack and y >= -slack and x + w <= hw + slack and y + h <= hh + slack


def outside_message(project) -> str:
    return f"Part of the design is outside the {hoop(project)['short']} mm hoop. Move or resize it before exporting."
