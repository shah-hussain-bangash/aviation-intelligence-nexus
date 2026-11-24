"""Presence-based startup interlock for an unfinished private restore."""
from pathlib import Path

RESTORE_MARKER = 'restore-in-progress.json'


class RestoreIncompleteError(RuntimeError):
    pass


def restore_incomplete(state):
    try:
        (Path(state) / RESTORE_MARKER).lstat()
    except FileNotFoundError:
        return False
    except OSError:
        raise RestoreIncompleteError('restore_state_unavailable') from None
    return True


def require_complete_restore(database):
    if restore_incomplete(Path(database).parent):
        raise RestoreIncompleteError('restore_incomplete')
