"""XDG paths; application releases never contain personal configuration."""
import os
from pathlib import Path


def data_dir():
    return Path(os.environ.get('XDG_DATA_HOME', Path.home()/'.local/share'))/'rglauncher-linux'


def config_dir():
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/'rglauncher-linux'


def state_dir():
    return Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'rglauncher-linux'


def release_root():
    return Path(__file__).resolve().parents[1]
