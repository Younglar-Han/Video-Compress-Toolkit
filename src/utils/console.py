"""控制台输出工具。

目标：统一日志风格，让压缩、分析、绘图阶段的输出更易读。
"""

from __future__ import annotations

from typing import Iterable, Sequence


def _emit(message: str, tag: str | None = None, leading_blank: bool = False) -> None:
    """统一输出底层函数。"""

    if leading_blank:
        print("")
    if tag:
        print(f"[{tag}] {message}")
        return
    print(message)


def info(message: str, leading_blank: bool = False) -> None:
    """输出普通信息。"""

    _emit(message, tag="信息", leading_blank=leading_blank)


def success(message: str, leading_blank: bool = False) -> None:
    """输出成功信息。"""

    _emit(message, tag="成功", leading_blank=leading_blank)


def warn(message: str, leading_blank: bool = False) -> None:
    """输出警告信息。"""

    _emit(message, tag="警告", leading_blank=leading_blank)


def error(message: str, leading_blank: bool = False) -> None:
    """输出错误信息。"""

    _emit(message, tag="错误", leading_blank=leading_blank)


def phase_start(scope: str, message: str) -> None:
    """输出阶段开始信息（自动空行，符合项目关键阶段规则）。"""

    _emit(f"{scope} | {message}", tag="开始", leading_blank=True)


def phase_end(scope: str, message: str) -> None:
    """输出阶段结束信息（自动空行，符合项目关键阶段规则）。"""

    _emit(f"{scope} | {message}", tag="完成", leading_blank=True)


def progress(current: int, total: int, message: str) -> None:
    """输出进度信息。"""

    _emit(f"[{current}/{total}] {message}", tag="进度")


def section(title: str) -> None:
    """输出分节标题。"""

    line = "=" * 16
    print("")
    print(f"{line} {title} {line}")


def print_table(headers: Sequence[str], rows: Iterable[Sequence[str]]) -> None:
    """按列宽输出简洁表格。"""

    matrix = [list(headers)] + [list(r) for r in rows]
    if not matrix:
        return

    col_count = len(matrix[0])
    widths = [0] * col_count
    for row in matrix:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    def _fmt(row: Sequence[str]) -> str:
        return " | ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row))

    print(_fmt(headers))
    print("-+-".join("-" * widths[i] for i in range(col_count)))
    for row in rows:
        print(_fmt(row))
