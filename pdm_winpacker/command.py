from pdm.cli.commands.base import BaseCommand
from pdm.cli.hooks import HookManager


from . winpacker import Bundler, PackedApp
from . winpacker.packers import NSISPacker, ZipPacker

class WinpackerCommand(BaseCommand):
    """Build NSIS installer for your project.
    If none is given, will read from "hello.name" config.
    """

    name = "winpacker"

    def add_arguments(self, parser):
        #parser.add_argument("-n", "--name", help="the person's name to whom you greet")
        pass

    def handle(self, project, options):
        hooks = HookManager(project)

        packed_app = PackedApp(project)
        packed_app.clean_build_directry()

        hooks.try_emit("pre_build", dest=packed_app.build_dir, config_settings={})

        Bundler(packed_app).build()
        NSISPacker(packed_app).pack()
        ZipPacker(packed_app).pack()

        hooks.try_emit("post_build", artifacts=packed_app.artifacts, config_settings={})