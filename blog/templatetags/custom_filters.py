from django import template

register = template.Library()

@register.filter
def get(dictionary, key):
    """
    Gets a value from a dictionary using a key.
    Usage: {{ dictionary|get:key }}
    """
    if dictionary is None:
        return None
    return dictionary.get(key, None) 