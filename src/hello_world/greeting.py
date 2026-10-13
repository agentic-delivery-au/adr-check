"""Build greeting text."""


def greet(name: str, *, greeting: str = "Hello") -> str:
    """Return `greeting` addressed to `name`, ignoring surrounding whitespace."""
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("name must not be blank")
    return f"{greeting}, {cleaned}!"
