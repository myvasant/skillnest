"""Task manager: a to-do list with priorities, due dates and pluggable storage.

Package layout. Each module may import only the modules listed above it:

* ``models``  - Task, Priority, Status and the rules (validation, due dates, sorting)
* ``storage`` - the TaskRepository interface with JSON and SQLite implementations
* ``cli``     - the argparse front end, run with ``python -m task_manager``
"""

from .models import Priority, Status, Task, TaskError
from .storage import (
    JsonTaskRepository,
    SqliteTaskRepository,
    StorageError,
    TaskNotFoundError,
    TaskRepository,
    open_repository,
)

__all__ = [
    "JsonTaskRepository",
    "Priority",
    "SqliteTaskRepository",
    "Status",
    "StorageError",
    "Task",
    "TaskError",
    "TaskNotFoundError",
    "TaskRepository",
    "open_repository",
]
