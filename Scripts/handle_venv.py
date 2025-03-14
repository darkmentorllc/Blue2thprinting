import os
import sys
from pathlib import Path
def activate_venv():
    """Activate virtual environment if it exists"""
    script_dir = Path(__file__).parent
    venv_path = script_dir / '../venv'

    if not venv_path.exists():
        # Because I do testing with it in a different location, try this
        venv_path = script_dir / './venv'
        if not venv_path.exists():
            return False

    # Get Python version from venv binary
    venv_python = venv_path / 'bin' / 'python'
    if not venv_python.exists():
        return False

    # Set environment variables
    os.environ['VIRTUAL_ENV'] = str(venv_path)
    os.environ['PATH'] = f"{venv_path}/bin:{os.environ['PATH']}"

    # Remove PYTHONHOME if set
    if 'PYTHONHOME' in os.environ:
        del os.environ['PYTHONHOME']

    # Add site-packages to path
    for lib_dir in venv_path.glob('lib/python*/site-packages'):
        sys.path.insert(0, str(lib_dir))
        break

    # Set base prefix
    sys.prefix = str(venv_path)
    sys.exec_prefix = str(venv_path)

    return True