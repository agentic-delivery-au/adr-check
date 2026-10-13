import pytest

from hello_world import greet


def test_greet_uses_the_default_greeting():
    assert greet("Ada") == "Hello, Ada!"


def test_greet_uses_a_custom_greeting():
    assert greet("Ada", greeting="Hi") == "Hi, Ada!"


def test_greet_ignores_surrounding_whitespace():
    assert greet("  Ada  ") == "Hello, Ada!"


@pytest.mark.parametrize("name", ["", "   "])
def test_greet_rejects_a_blank_name(name):
    with pytest.raises(ValueError, match="must not be blank"):
        greet(name)
