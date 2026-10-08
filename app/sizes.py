"""Размеры файлов по-русски: «850 КБ», «45,6 МБ», «1,3 ГБ»."""


def human(size: int | float | None) -> str:
    if size is None:
        return "?"
    size = float(size)
    for unit, step in (("ГБ", 1024 ** 3), ("МБ", 1024 ** 2), ("КБ", 1024)):
        if size >= step:
            value = size / step
            text = f"{value:.1f}" if value < 100 else f"{value:.0f}"
            return text.replace(".", ",") + " " + unit
    return f"{int(size)} Б"


def estimate_text(size: int | None, exact: bool) -> str:
    """«45,6 МБ» для точного, «≈ 45,6 МБ» для примерного, «размер неизвестен» — если нет данных."""
    if size is None:
        return "размер неизвестен"
    return ("" if exact else "≈ ") + human(size)
