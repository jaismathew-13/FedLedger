"""Rich progress display shared by training and transport code."""
import sys

from rich.console import Console
from rich.table import Column
from rich.progress import (
    Progress, TextColumn, BarColumn, TaskProgressColumn,
    TimeElapsedColumn, TimeRemainingColumn,
)


class ProgressBar:
    """Iterable/manual counter backed entirely by rich.progress.Progress."""

    def __init__(self, iterable=None, *, total=None, desc='', unit='item',
                 leave=True, disable=False, position=None, **display_options):
        self.iterable = iterable
        self.total = total if total is not None else (
            len(iterable) if iterable is not None and hasattr(iterable, '__len__') else None)
        self.n = 0
        self.started = False
        # A Tee forwards output to logs; detect its underlying terminal explicitly.
        terminal = sys.stderr
        while hasattr(terminal, 'terminal'):
            terminal = terminal.terminal
        console = Console(file=sys.stderr, force_terminal=terminal.isatty(),
                          highlight=False)
        self.progress = Progress(
            TextColumn('[cyan]{task.description}', markup=True), BarColumn(),
            TaskProgressColumn(), TextColumn('{task.completed:g}/{task.total:g} '+unit
                if self.total is not None else '{task.completed:g} '+unit),
            TimeElapsedColumn(), TimeRemainingColumn(),
            TextColumn('{task.fields[detail]}', markup=False, table_column=Column(no_wrap=True, overflow='ellipsis', ratio=2)),
            console=console, transient=not leave, disable=disable,
            refresh_per_second=4,
        )
        self.task = self.progress.add_task(desc, total=self.total, detail='')

    def __enter__(self):
        if not self.started:
            self.progress.start()
            self.started = True
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self.started:
            self.progress.stop()
            self.started = False

    def __iter__(self):
        with self:
            for item in self.iterable:
                yield item
                self.update(1)

    def update(self, amount=1):
        self.n += amount
        self.progress.update(self.task, completed=self.n)

    def set_postfix_str(self, text, refresh=True):
        self.progress.update(self.task, detail=text, refresh=refresh)

    def set_postfix(self, **values):
        self.set_postfix_str(' '.join(f'{key}={value}' for key, value in values.items()))

    def refresh(self):
        self.progress.refresh()
