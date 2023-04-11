import os
import re
import zipfile
import shutil
import logging
from urllib.parse import urlparse
from typing import Iterable
from pdm import termui
from pdm.project import Project
from pdm.cli.actions import resolve_candidates_from_lockfile
from pdm.exceptions import PdmUsageError
from pdm.models.candidates import Candidate
from pdm.models.requirements import Requirement
from pdm.exceptions import NoPythonVersion, PdmUsageError, ProjectError
from pdm.cli.hooks import HookManager
from unearth import PackageFinder, TargetPython
from pathlib import Path

from .wheelinstaller import extract_wheel
from .command import CommandBuilder
from ..utils import download, get_cache_dir
from ..packers import NSISPacker, ZipPacker
from ..packedapp import PackedApp



DEFAULT_PY_BIT = 64
DEFAULT_PY_VERSION = '3.10.11'
_PKGDIR = os.path.abspath(os.path.dirname(__file__))


logger = logging.getLogger(__name__)


class Bundler():
    def __init__(self, packed_app: PackedApp):

        self.project = packed_app.project
        self.packed_app = packed_app
        self._config = self.project.pyproject.settings.setdefault("win-packer", {})
        self._package_dir = os.path.join(self.project.root, self.project.pyproject.settings.get("build", {}).get("package-dir", "."))

    @property
    def _py_version_tuple(self):
        parts = self.packed_app.py_version.split('.')
        return int(parts[0]), int(parts[1])

    @property
    def _dependencies(self):
        """Return a list of dependencies for the project.
        """
        dependencies = []
        just_names = []

        requirements: dict[str, Requirement] = {}
        packages: Iterable[Requirement] | Iterable[Candidate]

        requirements.update(self.project.get_dependencies())
        if not self.project.lockfile.exists:
            raise PdmUsageError("No lockfile found, please run `pdm lock` first.")

        candidates = resolve_candidates_from_lockfile(self.project, requirements.values())
        packages = (candidate for candidate in candidates.values() if not candidate.req.extras)

        for package in packages:
            dependencies.append(f"{package.name}=={package.version}")
            just_names.append(package.name)

        return dependencies, just_names

    def _check_entry_point(self, ep: str):
        """Like ep.split(':'), but with extra checks and helpful errors"""
        module, _, func = ep.partition(':')
        if all([s.isidentifier() for s in module.split('.')]) and func.isidentifier():
            return True

        return False

    def _python_download_url_filename(self):
        version = self.packed_app.py_version
        bitness = self.packed_app.py_bit
        filename = 'python-{}-embed-{}.zip'.format(version, 'amd64' if bitness==64 else 'win32')

        version_minus_prerelease = re.sub(r'(a|b|rc)\d+$', '', self.packed_app.py_version)
        return 'https://www.python.org/ftp/python/{0}/{1}'.format(version_minus_prerelease, filename), filename

    def prepare_icon(self):
        """Copy the icon file to the build directory"""
        with self.project.core.ui.open_spinner("Copying icon..."):
            shutil.copy2(self.packed_app.icon, self.packed_app.build_dir)

    def prepare_python_embeddable(self):
        """Fetch the embeddable Windows build for the specified Python version

        It will be unpacked into the build directory.

        In addition, any ``*._pth`` files found therein will have the pkgs path
        appended to them.
        """
        url, filename = self._python_download_url_filename()
        cache_file = get_cache_dir(ensure_existence=True) / filename
        if not cache_file.is_file():
            with self.project.core.ui.open_spinner('Downloading embeddable Python build...'):
                logger.info('Downloading embeddable Python build...')
                logger.info('Getting %s', url)
                download(url, cache_file)

        with self.project.core.ui.open_spinner('Unpacking Python...'):
            logger.info('Unpacking Python...')
            python_dir = os.path.join(self.packed_app.build_dir, 'Python')

            with zipfile.ZipFile(str(cache_file)) as z:
                z.extractall(python_dir)

            # Manipulate any *._pth files so the default paths AND pkgs directory
            # ends up in sys.path. Please see:
            # https://docs.python.org/3/using/windows.html#finding-modules
            # for more information.
            pth_files = [f for f in os.listdir(python_dir)
                        if os.path.isfile(os.path.join(python_dir, f))
                        and f.endswith('._pth')]
            for pth in pth_files:
                with open(os.path.join(python_dir, pth), 'a+b') as f:
                    f.write(b'\r\n..\\pkgs\r\nimport site\r\n')

            self.packed_app.install_dirs.append(('Python', '$INSTDIR'))
            self.packed_app.extra_files.append((os.path.join(_PKGDIR, '_system_path.py'), '$INSTDIR'))

    def prepare_msvcrt(self):
        #TODO: Move to NSIS packer
        arch = 'x64' if self.packed_app.py_bit == 64 else 'x86'
        src = os.path.join(_PKGDIR, 'msvcrt', arch)
        dst = os.path.join(self.packed_app.build_dir, 'msvcrt')
        self.msvcrt_files = sorted(os.listdir(src))

        with self.project.core.ui.open_spinner('Copying msvcrt files...'):
            shutil.copytree(src, dst)

    def prepare_license(self):
        """
        If a license file has been specified, ensure it's copied into the
        install directory and added to the install_files list.
        """
        if self.packed_app.license:
            with self.project.core.ui.open_spinner('Copying license file...'):
                shutil.copy2(self.packed_app.license, self.packed_app.build_dir)
                license_file_name = os.path.basename(self.packed_app.license)
                self.packed_app.install_files.append((license_file_name, '$INSTDIR'))

    def prepare_dependencies(self):
        """Copy any dependencies into the build directory."""

        #TODO: a better way? Maybe install them into a virtualenv and copy from there? or install pip in to embeddable python and use that?
        target_platform = 'win_amd64' if int(self.packed_app.py_bit) == 64 else 'win32'
        dependencies, just_names = self._dependencies

        with self.project.core.ui.open_spinner(title="Preparing dependencies...") as spin:
            target_python = TargetPython(self._py_version_tuple, [f"cp{self._py_version_tuple[0]}{self._py_version_tuple[1]}", "none"], "cp", [target_platform, "any"])
            finder = PackageFinder(index_urls=["https://pypi.org/simple/"], target_python=target_python, prefer_binary=just_names)

            build_pkg_dir = os.path.join(self.packed_app.build_dir, 'pkgs')
            try:
                os.makedirs(build_pkg_dir)
            except FileExistsError:
                pass

            for dependency in dependencies:
                spin.update(f"Preparing dependencies: {dependency}...")
                result = finder.find_best_match(dependency)

                if result.best is not None:
                    if result.best.link.is_wheel:

                        url = result.best.link.url
                        filename = os.path.basename(urlparse(url).path)

                        cache_file = get_cache_dir(ensure_existence=True) / filename
                        if not cache_file.is_file():
                            download(url, cache_file)

                        extract_wheel(cache_file, build_pkg_dir)
                    else:
                        #TODO: handle non-wheel dependencies
                        #TODO:Set as warning
                        self.project.core.ui.echo(f"Skipping {dependency} as it's not a wheel", style="warning")
                else:
                    self.project.core.ui.echo(f"Skipping {dependency} as it's not found", style="warning")

                #install local dependencies(wheels)
                for dep in self.packed_app.config.get("local_wheels", []):
                    dep_filepath = os.path.join(self._package_dir, dep)
                    if os.path.isfile(dep_filepath):
                        #TODO: get name and version from wheel
                        extract_wheel(dep_filepath, build_pkg_dir)

    def prepare_commands(self):
        with self.project.core.ui.open_spinner("Preparing creating excutables"):
            command_dir = Path(self.packed_app.build_dir) / 'bin'
            command_dir.mkdir()

            commands = self._config.setdefault("commands", {})
            for name, cmd_options in commands.items():
                if not "entry_point" in cmd_options:
                    raise ProjectError(f"Command {name} has no entry_point")
                #TODO: fix check entry point is valid
                #elif self._check_entry_point(cmd_options["entry_point"]):
                #    raise ValueError(f"Command {name} has an invalid entry_point", cmd_options["entry_point"])

                if not "console" in cmd_options:
                    cmd_options["console"] = False

                if "extra_preamble" in cmd_options:
                    extra_preamble = cmd_options["extra_preamble"]
                else:
                    extra_preamble = None

                if "env" in cmd_options:
                    env = cmd_options["env"]
                else:
                    env = {}

                CommandBuilder(
                    name,
                    cmd_options["entry_point"],
                    cmd_options["console"],
                    command_dir,
                    self.packed_app.py_bit,
                    extra_preamble,
                    env
                ).build()

            self.packed_app.install_dirs.append((command_dir.name, '$INSTDIR'))

    def prepare_packages(self):
        """Copy any packages into the build directory."""
        with self.project.core.ui.open_spinner("Copying packages..."):

            for file in os.listdir(self._package_dir):
                package_dir = os.path.join(self._package_dir, file)
                if os.path.isdir(os.path.join(self._package_dir, file)):
                    if os.path.isfile(os.path.join(self._package_dir, file, '__init__.py')):
                        shutil.copytree(package_dir, os.path.join(self.packed_app.build_dir, 'pkgs', file))

            #include_packages = self.packed_app.config.get("include_packages", [])
            #TODO: check if package is valid
            #TODO: Include packages

    def prepare_extra_files(self):
        """Copy a list of files into the build directory, and add them to
        install_files or install_dirs as appropriate.
        """
        # Create installer.nsi, so that a data file with the same name will
        # automatically be renamed installer.1.nsi. All the other files needed
        # in the build directory should already be in place.
        #Path(self.nsi_file).touch()

        with self.project.core.ui.open_spinner(title='Copying extra files...') as spin:
            for file, destination in self.packed_app.extra_files:
                file = file.rstrip('/\\')
                in_build_dir = Path(self.packed_app.build_dir, os.path.basename(file))
                spin.update(f"Copying {file}...")

                # Find an unused name in the build directory,
                # similar to the source filename, e.g. foo.1.txt, foo.2.txt, ...
                stem, suffix = in_build_dir.stem, in_build_dir.suffix
                n = 1
                while in_build_dir.exists():
                    name = '{}.{}{}'.format(stem, n, suffix)
                    in_build_dir = in_build_dir.with_name(name)
                    n += 1

                if destination:
                    # Normalize destination paths to Windows-style
                    destination = destination.replace('/', '\\')
                else:
                    destination = '$INSTDIR'

                if os.path.isdir(file):
                    if self.exclude:
                        shutil.copytree(file, str(in_build_dir),
                            ignore=self.copytree_ignore_callback)
                    else:
                        # Don't use our exclude callback if we don't need to,
                        # as it slows things down.
                        shutil.copytree(file, str(in_build_dir))
                    self.packed_app.install_dirs.append((in_build_dir.name, destination))
                else:
                    shutil.copy2(file, str(in_build_dir))
                    self.packed_app.install_files.append((in_build_dir.name, destination))

    def build(self):
        """Build the bundle."""
        self.prepare_icon()
        self.prepare_python_embeddable()
        self.prepare_msvcrt()
        self.prepare_dependencies()
        self.prepare_packages()
        self.prepare_commands()
        self.prepare_extra_files()

        self.project.core.ui.echo(f"[success]{termui.Emoji.SUCC}[/] Bundle built", style="success")
