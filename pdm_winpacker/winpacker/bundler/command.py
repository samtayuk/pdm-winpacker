import os
import io
import distlib.scripts
from zipfile import ZipFile

class CommandBuilder():

    SCRIPT_TEMPLATE = u"""# -*- coding: utf-8 -*-
import sys, os
import site
installdir = os.path.dirname(os.path.dirname(sys.executable))
pkgdir = os.path.join(installdir, 'pkgs')
sys.path.insert(0, pkgdir)
# Ensure .pth files in pkgdir are handled properly
site.addsitedir(pkgdir)
os.environ['PYTHONPATH'] = pkgdir + os.pathsep + os.environ.get('PYTHONPATH', '')

# Allowing .dll files in Python directory to be found
os.environ['PATH'] += ';' + os.path.dirname(sys.executable)

{script_env}

{extra_preamble}

if __name__ == '__main__':
    from {module} import {func}
    sys.exit({func}())
"""

    def __init__(self, name, entry_point, console, target, bit=64, extra_preamble=None, env={}):
        self.name = name
        self.entry_point = entry_point
        self.console = console
        self.target = target
        self.bit = bit
        self.extra_preamble = extra_preamble
        self.env = env

    def _find_exe(self):
        distlib_dir = os.path.dirname(distlib.scripts.__file__)
        name = 't' if self.console else 'w'
        return os.path.join(distlib_dir, f"{name}{self.bit}.exe")

    def _prepare_bin_directory(self):
        exe_path = self.target / (self.name + '.exe')
        console = self.console

        # 1. Get the base launcher exe from distlib
        with open(self._find_exe(), 'rb') as f:
            launcher_b = f.read()

        # 2. Shebang: Python executable to run with
        # shebangs relative to launcher location, according to
        # https://bitbucket.org/vinay.sajip/simple_launcher/wiki/Launching%20an%20interpreter%20in%20a%20location%20relative%20to%20the%20launcher%20executable
        if console:
            shebang = b"#!<launcher_dir>\\..\\Python\\python.exe\r\n"
        else:
            shebang = b"#!<launcher_dir>\\..\\Python\\pythonw.exe\r\n"

        # 3. The script to run, inside a zip file
        if isinstance(self.extra_preamble, str):
            # Filename
            extra_preamble = io.open(self.extra_preamble, encoding='utf-8')
        elif self.extra_preamble is None:
            extra_preamble = io.StringIO()  # Empty
        else:
            # Passed a StringIO or similar object
            extra_preamble = self.extra_preamble
        module, func = self.entry_point.split(':')
        script_env = "\r\n".join(f"os.environ['{k}'] = '{v}'" for k, v in self.env.items())
        script = self.SCRIPT_TEMPLATE.format(
            module=module, func=func,
            extra_preamble=extra_preamble.read().rstrip(),
            script_env=script_env,
        )

        zip_bio = io.BytesIO()
        with ZipFile(zip_bio, 'w') as zf:
            zf.writestr('__main__.py', script.encode('utf-8'))

        # Put the pieces together
        with exe_path.open('wb') as f:
            f.write(launcher_b)
            f.write(shebang)
            f.write(zip_bio.getvalue())

    def build(self):
        self._prepare_bin_directory()