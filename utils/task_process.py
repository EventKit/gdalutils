import logging
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Union

from django.db import connection

logger = logging.getLogger(__name__)


class TaskProcess:
    """Wraps a Task subprocess up and handles logic specifically for the application.
    If the child process calls other subprocesses use billiard.
    Note, unlike multi-use process classes start and join/wait happen during instantiation."""

    def __init__(self, task_uid=None):
        self.task_uid = task_uid
        self.exitcode = None
        self.stdout = None
        self.stderr = None

    def start_process(
        self, *args, command: Optional[Union[str, Callable]] = None, **kwargs
    ):
        # We need to close the existing connection because the logger could be using a forked process which,
        # will be invalid and throw an error.
        connection.close()

        if callable(command):
            with ThreadPoolExecutor() as executor:
                future = executor.submit(command)
                future.result()
        elif isinstance(command, str):
            with subprocess.Popen(command, *args, **kwargs) as proc:
                (self.stdout, self.stderr) = proc.communicate()
                self.exitcode = proc.wait()
        else:
            raise Exception("Start Process command must be either string or callable.")
