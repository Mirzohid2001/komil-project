from django import template
from django.template.defaultfilters import stringfilter

register = template.Library()

@register.filter(name='get')
def get_dict_value(dictionary, key):
    """Get a value from a dictionary by key."""
    if not dictionary:
        return None
    return dictionary.get(key, None) 

@register.filter(name='multiply')
def multiply(value, arg):
    """Multiply the value by the argument."""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter(name='divide')
def divide(value, arg):
    """Divide the value by the argument."""
    try:
        arg = float(arg)
        if arg == 0:
            return 0
        return float(value) / arg
    except (ValueError, TypeError):
        return 0

@register.filter(name='get_range')
def get_range(value):
    """Creates a range from 1 to the value."""
    try:
        value = int(value)
        return range(1, value + 1)
    except (ValueError, TypeError):
        return range(0) 