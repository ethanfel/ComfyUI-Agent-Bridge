"""A wildcard socket type that accepts any connection.

Used for optional 'signal' inputs whose only purpose is to create a dependency
edge so ComfyUI runs the upstream node first (execution ordering).
"""


class AnyType(str):
    # Comparing the type against any other type reports "equal", so ComfyUI's
    # connection type-check accepts a link from any output.
    def __ne__(self, other):
        return False


ANY = AnyType("*")
