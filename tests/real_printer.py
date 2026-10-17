"""Import tools.printer.tools without leaving its tools in the global registry.

The real tools and the fakes share names (FAKE_TOOLS picks one set), so a test
that imports the real module must not leave it registered.
"""

from tools import registry

_saved = dict(registry._tools)
registry._tools.clear()
try:
    from tools.printer import tools as pt
finally:
    registry._tools.clear()
    registry._tools.update(_saved)
