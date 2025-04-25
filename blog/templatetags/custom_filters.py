from django import template
from itertools import groupby
from operator import attrgetter

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

@register.filter
def filter_passed_tests(queryset, is_passed):
    """Фильтрует результаты тестов по статусу прохождения"""
    return [test for test in queryset if test.is_passed == is_passed]

@register.filter
def regroup_by(queryset, attr):
    """Группирует результаты по указанному атрибуту"""
    queryset = sorted(queryset, key=attrgetter(attr))
    return {k: list(g) for k, g in groupby(queryset, key=attrgetter(attr))}

@register.filter
def length_or_zero(grouped_dict, key):
    """Возвращает длину списка по ключу или 0, если ключа нет"""
    if key == "True":
        return len(grouped_dict.get(True, []))
    elif key == "False":
        return len(grouped_dict.get(False, []))
    return 0 