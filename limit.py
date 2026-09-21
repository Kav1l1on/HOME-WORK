"""Обчислення границі функції в точці числовим методом.

Функція обчислюється в точках, що наближаються до x0 зліва та справа
(крок h зменшується в 10 разів). Якщо послідовність значень збігається,
то це і є однобічна границя; границя в точці існує, коли обидві
однобічні границі рівні.
"""

import math

# Менший крок брати не можна: через похибку округлення різниці
# на зразок 1 - cos(x) втрачають точність.
START_STEP = 1e-2
MIN_STEP = 1e-5
RATIO = 10.0


def _values(f, x0, side):
    """Значення f у точках x0 + side*h для спадних h."""
    result = []
    h = START_STEP
    while h >= MIN_STEP:
        try:
            y = f(x0 + side * h)
        except (ZeroDivisionError, ValueError, OverflowError):
            y = None
        if y is not None and math.isfinite(y):
            result.append(y)
        h /= RATIO
    return result


def _aitken(v0, v1, v2):
    """Прискорення збіжності (Δ²-процес Ейткена)."""
    denom = v2 - 2 * v1 + v0
    if abs(denom) < 1e-15 * max(1.0, abs(v2)):
        return v2
    return v2 - (v2 - v1) ** 2 / denom


def one_sided_limit(f, x0, side, tol=1e-6):
    """Однобічна границя f(x) при x -> x0.

    side: -1 - зліва, +1 - справа.
    Повертає число, math.inf, -math.inf або None, якщо границі немає.
    """
    values = _values(f, x0, side)
    if len(values) < 4:
        return None

    v0, v1, v2, v3 = values[-4:]

    # Значення необмежено зростають -> нескінченна границя.
    if abs(v3) > 1e3 and abs(v3) > 2 * abs(v2) > 2 * abs(v1):
        return math.inf if v3 > 0 else -math.inf

    step2, step3 = abs(v2 - v1), abs(v3 - v2)
    scale = max(1.0, abs(v3))
    # Коливання не згасають -> границі немає.
    if step3 > tol * scale and step3 > step2 / 5:
        return None

    result = _aitken(v1, v2, v3)
    if abs(result - v3) > 10 * step3 + tol * scale:
        result = v3

    # Контрольна перевірка в проміжній точці: випадковий збіг
    # двох сусідніх значень не сприймається за збіжність.
    h = START_STEP / RATIO ** (len(values) - 1)
    try:
        control = f(x0 + side * 3 * h)
    except (ZeroDivisionError, ValueError, OverflowError):
        return result
    if not math.isfinite(control):
        return result
    if abs(control - result) > 20 * step3 + 10 * tol * scale:
        return None
    return result


def limit(f, x0, tol=1e-6):
    """Границя f(x) при x -> x0 (None, якщо не існує)."""
    left = one_sided_limit(f, x0, -1, tol)
    right = one_sided_limit(f, x0, +1, tol)
    if left is None or right is None:
        return None
    if left == right:
        return left
    if math.isinf(left) or math.isinf(right):
        return None
    if abs(left - right) <= tol * max(1.0, abs(left), abs(right)):
        return (left + right) / 2
    return None


def format_limit(value):
    if value is None:
        return 'не існує'
    if value == math.inf:
        return '+нескінченність'
    if value == -math.inf:
        return '-нескінченність'
    return f'{value:.6g}'


def show(name, f, x0):
    print(f'lim {name} при x -> {x0}')
    print(f'  зліва:   {format_limit(one_sided_limit(f, x0, -1))}')
    print(f'  справа:  {format_limit(one_sided_limit(f, x0, +1))}')
    print(f'  границя: {format_limit(limit(f, x0))}\n')


if __name__ == '__main__':
    show('(x^2 - 1) / (x - 1)', lambda x: (x ** 2 - 1) / (x - 1), 1)
    show('sin(x) / x', lambda x: math.sin(x) / x, 0)
    show('(1 - cos(x)) / x^2', lambda x: (1 - math.cos(x)) / x ** 2, 0)
    show('(sqrt(x + 4) - 2) / x', lambda x: (math.sqrt(x + 4) - 2) / x, 0)
    show('1 / x^2', lambda x: 1 / x ** 2, 0)
    show('1 / x', lambda x: 1 / x, 0)
    show('|x| / x', lambda x: abs(x) / x, 0)
    show('sin(1 / x)', lambda x: math.sin(1 / x), 0)
    show('x^2 + 3x - 2', lambda x: x ** 2 + 3 * x - 2, 2)
