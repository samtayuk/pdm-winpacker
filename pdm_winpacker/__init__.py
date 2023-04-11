from pdm.core import Core

from . command import WinpackerCommand

def plugin(core: Core) -> None:
    core.register_command(WinpackerCommand)