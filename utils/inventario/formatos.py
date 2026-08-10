from __future__ import annotations


def entero(valor: float | int) -> str:
    return (
        f"{int(round(float(valor))):,}"
        .replace(",", ".")
    )


def decimal(
    valor: float | int,
    decimales: int = 1,
) -> str:
    return (
        f"{float(valor):,.{decimales}f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )
