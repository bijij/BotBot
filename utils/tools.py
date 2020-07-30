from numbers import Number

__all__ = (
    'plural'
)


class plural:

    def __init__(self, value: Number):
        self.value = value

    def __format__(self, format_spec: str):
        singular, _, plural = format_spec.partition('|')
        plural = plural or f'{singular}s'
        return f'{self.value} {plural if abs(self.value) != 1 else singular}'
