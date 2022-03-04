import logging
import os
import shutil
import time
from functools import wraps
from pathlib import Path
from typing import Tuple, Optional

from django.conf import settings
from django.core.cache import cache
from django.db import connection

logger = logging.getLogger()

CHUNK = 1024 * 1024 * 2  # 2MB chunks
DEFAULT_CACHE_EXPIRATION = 86400  # expire in a day


def retry(base=2, count=1):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwds):
            exc: Optional[Exception] = None
            attempts = count
            while attempts:
                try:
                    return f(*args, **kwds)
                except Exception as e:
                    exc = e
                    if getattr(settings, "TESTING", False):
                        # Don't wait/retry when running tests.
                        break
                    if attempts:
                        delay = base ** (count - attempts + 1)
                        logger.info(
                            "Retrying %s for %s more times, sleeping for %s...",
                            getattr(f, "__name__"),
                            str(attempts),
                            delay,
                        )
                        time.sleep(delay)
                        attempts -= 1
            if exc:
                raise exc

        return wrapper

    return decorator

def get_cache_key(obj=None, attribute=None, uid=None):
    """
    A way to store values in the cache ideally models would use their own implementation of this, but this could
    be called directly to prevent the need to call the model to update the state.

    Example
    :param obj: A string representing a model name (i.e. ExportTaskRecord)
    :param attribute: The models attribute.
    :param uid: An optional uid if a specific object isn't passed.
    :return:
    """
    obj_uid = uid
    if obj:
        obj_uid = obj.uid
    if not obj_uid:
        raise Exception("Cannot cache a state without a uid.")
    cache_key = f"{str(obj_uid)}.{attribute}"
    return cache_key


def set_cache_value(
    obj=None,
    uid=None,
    attribute=None,
    value=None,
    expiration=DEFAULT_CACHE_EXPIRATION,
):
    return cache.set(
        get_cache_key(obj=obj, attribute=attribute, uid=str(uid)),
        value,
        timeout=expiration,
    )


def get_cache_value(obj=None, uid=None, attribute=None, default=None):
    return cache.get(
        get_cache_key(obj=obj, attribute=attribute, uid=str(uid)),
        default,
    )


def update_progress(
    task_uid,
    progress=None,
    subtask_percentage=100.0,
    subtask_start=0,
    estimated_finish=None,
    eta=None,
    msg=None,
):
    """
    Updates the progress of the ExportTaskRecord from the given task_uid.
    :param task_uid: A uid to reference the ExportTaskRecord.
    :param progress: The percent of completion for the task or subtask [0-100]
    :param subtask_percentage: is the percentage of the task referenced by task_uid the caller takes up. [0-100]
    :param subtask_start: is the beginning of where this subtask's percentage block beings [0-100]
                          (e.g. when subtask_percentage=0.0 the absolute_progress=subtask_start)
    :param estimated_finish: The datetime of when the entire task is expected to finish, overrides eta estimator
    :param eta: The ETA estimator for this task will be used to automatically determine estimated_finish
    :param msg: Message describing the current activity of the task
    """
    if task_uid is None:
        return

    if not progress and not estimated_finish:
        return

    subtask_percentage = subtask_percentage or 100.0
    subtask_start = subtask_start or 0

    if progress is not None:
        subtask_progress = min(progress, 100.0)
        absolute_progress = min(
            subtask_start + subtask_progress * (subtask_percentage / 100.0), 100.0
        )

    # We need to close the existing connection because the logger could be using a forked process which
    # will be invalid and throw an error.
    connection.close()

    if absolute_progress:
        set_cache_value(
            uid=task_uid,
            attribute="progress",
            value=absolute_progress,
        )
        if eta is not None:
            eta.update(absolute_progress / 100.0, dbg_msg=msg)  # convert to [0-1.0]

    if estimated_finish:
        set_cache_value(
            uid=task_uid,
            attribute="estimated_finish",
            value=estimated_finish,
        )
    elif eta is not None:
        # Use the updated ETA estimator to determine an estimated_finish
        set_cache_value(
            uid=task_uid,
            attribute="estimated_finish",
            value=eta.eta_datetime(),
        )


def get_run_staging_dir(run_uid):
    """
    The run staging dir is where all files are stored while they are being processed.
    It is a unique space to ensure that files aren't being improperly modified.
    :param run_uid: The unique value to store the directory for the run data.
    :return: The path to the run directory.
    """
    return os.path.join(settings.EXPORT_STAGING_ROOT.removesuffix("/"), str(run_uid))


def get_download_path(folder_name):
    """
    The download dir is where all files are stored after they are processed.
    It is a unique space to ensure that files aren't being improperly modified.
    :param file_path: The unique value to store the directory for the data.
    :return: The path to the directory.
    """
    return os.path.join(
        settings.EXPORT_DOWNLOAD_ROOT.removesuffix("/"), str(folder_name)
    )


def get_download_url(file_name):
    """
    A URL path to the run data
    :param run_uid: The unique identifier for the run data.
    :return: The url context. (e.g. /downloads/123e4567-e89b-12d3-a456-426655440000)
    """
    return f"{settings.EXPORT_MEDIA_ROOT.rstrip('/')}/{str(file_name)}"


def make_file_downloadable(file_path: Path) -> Tuple[Path, str]:
    """Construct the filesystem location and url needed to download the file at filepath.
    Copy filepath to the filesystem location required for download.
    @return A url to reach filepath.
    """

    # File name is the relative path, e.g. run/provider_slug/file.ext.
    # File path is an absolute path e.g. /var/lib/eventkit/export_stage/run/provider_slug/file.ext.
    file_name = Path(file_path)
    if Path(settings.EXPORT_STAGING_ROOT) in file_name.parents:
        file_name = file_name.relative_to(settings.EXPORT_STAGING_ROOT)

    download_url = get_download_url(file_name)

    download_path = get_download_path(file_name)
    make_dirs(os.path.dirname(download_path))

    if not os.path.isfile(file_path):
        logger.error(
            "Cannot make file %s downloadable because it does not exist.", file_path
        )
    else:
        shutil.copy(file_path, download_path)

    return file_name, download_url


def make_dirs(path):
    try:
        os.makedirs(path, 0o751, exist_ok=True)
    except OSError:
        if not os.path.isdir(path):
            raise
