class CancelException(Exception):
    """Used to indicate when a user calls for cancellation."""

    def __init__(self, message=None, task_name=None, user_name="system", filename=None, *args, **kwargs):
        """

        :param message: A non-default message
        :param task_uid: Task_uid to look up user and task name.
        """
        self.message = message  # without this you may get DeprecationWarning
        self.filename = filename
        if not self.message:
            self.message = f"{task_name} was canceled by {user_name}."
        super(CancelException, self).__init__(self.message, *args, **kwargs)
