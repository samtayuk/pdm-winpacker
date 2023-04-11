import os
import winreg
import operator
import subprocess
import jinja2
import ntpath
import itertools
import shutil
from operator import itemgetter
from pdm import termui
from pdm.exceptions import NoPythonVersion, PdmUsageError, ProjectError

_PKGDIR = os.path.abspath(os.path.dirname(__file__))


class NSISPacker():
    def __init__(self, packed_app) -> None:
        self.packed_app = packed_app
        self.project = packed_app.project
        self._config = self.packed_app.config

        # Sort by destination directory, so we can group them effectively
        self.packed_app.install_files.sort(key=operator.itemgetter(1))

        if self.include_msvcrt:
            self.nsi_template = 'pyapp_msvcrt.nsi'
        else:
            self.nsi_template = 'pyapp.nsi'

        self.nsi_file = os.path.join(self.packed_app.build_dir, 'installer.nsi')

    @property
    def _makensis_win(self):
        """Locate makensis.exe on Windows by querying the registry"""
        try:
            nsis_install_dir = winreg.QueryValue(winreg.HKEY_LOCAL_MACHINE, 'SOFTWARE\\NSIS')
        except OSError:
            nsis_install_dir = winreg.QueryValue(winreg.HKEY_LOCAL_MACHINE, 'SOFTWARE\\Wow6432Node\\NSIS')

        if nsis_install_dir is None:
            raise PdmUsageError("makensis.exe not found in registry")

        return os.path.join(nsis_install_dir, 'makensis.exe')

    @property
    def include_msvcrt(self):
        """Whether to include the MSVCRT redistributable in the installer"""
        return len(self.packed_app.msvcrt_files) > 0

    @property
    def installer_name(self):
        """Generate the filename of the installer exe

        e.g. My_App_1.0.exe
        """
        s = f"{self.packed_app.app_name}_{self.packed_app.app_version}.exe"
        return s.replace(' ', '_')

    def _write_nsi(self):
        """Write the NSI file to define the NSIS installer.

        Most of the details of this are in the template and the
        :class:`nsist.nsiswriter.NSISFileWriter` class.
        """
        env = jinja2.Environment(loader=jinja2.FileSystemLoader([
            _PKGDIR,
            os.getcwd()
        ]),
            # Change template markers from {}, which NSIS uses, to [], which it
            # doesn't much, so it's easier to distinguishing our templating from
            # NSIS preprocessor variables.
            block_start_string="[%",
            block_end_string="%]",
            variable_start_string="[[",
            variable_end_string="]]",
            comment_start_string="[#",
            comment_end_string="#]",

            # Trim whitespace around block tags, so formatting works as I expect
            trim_blocks=True,
            lstrip_blocks=True,
        )

        template = env.get_template(self.nsi_template)

        # Group files by their destination directory
        grouped_files = [(dest, [x[0] for x in group]) for (dest, group) in
            itertools.groupby(self.packed_app.install_files, itemgetter(1))
                ]
        license_file = None
        if self.packed_app.license:
            license_file = os.path.basename(self.packed_app.license)

        # Copy icons to build directory
        config_shortcuts = self._config.get("shortcuts", {})
        shortcuts = {}
        for key in config_shortcuts.keys():
            sc = config_shortcuts.get(key, {})
            if "target" not in sc:
                #TODO: Should be a warning skip this shortcut?
                raise ProjectError(f"Shortcut '{key}' must have a target")

            shortcuts[key] = sc

            if "icon" in shortcuts[key]:
                if not os.path.exists(os.path.join(self.packed_app.build_dir, os.path.basename(shortcuts[key]["icon"]))):
                    shutil.copy2(shortcuts[key]["icon"], self.packed_app.build_dir)

                shortcuts[key]["icon"] = os.path.basename(shortcuts[key]["icon"])
            else:
                shortcuts[key]["icon"] = os.path.basename(self.packed_app.icon)

        namespace = {
            'app_name': self.packed_app.app_name,
            'app_version': self.packed_app.app_version,
            'publisher': self._config.get("publisher",""),
            'installer_name': self.installer_name,
            'grouped_files': grouped_files,
            'icon': os.path.basename(self.packed_app.icon),
            'arch_tag': '.amd64' if (int(self.packed_app.py_bit)==64) else '',
            'py_version': self.packed_app.py_version,
            'py_bit': self.packed_app.py_bit,
            'py_major_version': self.packed_app.py_version.split('.')[0],
            'pjoin': ntpath.join,
            'single_shortcut': len(shortcuts) == 1,
            'shortcuts': shortcuts,
            'pynsist_pkg_dir': _PKGDIR,
            'has_commands': len(self._config.get("commands", {})) > 0,
            'python': '"$INSTDIR\\Python\\python"',
            'license_file': license_file,
            'install_dirs': self.packed_app.install_dirs,
            'extra_files': self.packed_app.extra_files,
            'install_files': self.packed_app.install_files,
            'msvcrt_files': self.packed_app.msvcrt_files,
        }

        with open(self.nsi_file, 'w') as f:
            f.write(template.render(namespace))

    def pack(self):
        """Build the installer using NSIS"""
        with self.project.core.ui.open_spinner("Compiling NSIS installer..."):
            self._write_nsi()

            output = os.path.abspath(os.path.join(self.packed_app.dist_dir, self.installer_name))
            subprocess.call([self._makensis_win, f"/XOutFile {output}", self.nsi_file], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)

        self.project.core.ui.echo(f"[success]{termui.Emoji.SUCC}[/] NSIS Installer built: {output}", style="success")
        self.packed_app.artifacts.append(output)
        return output
