import os
import shutil
from pdm.project import Project


DEFAULT_PY_BIT = 64
DEFAULT_PY_VERSION = '3.10.11'
_PKGDIR = os.path.abspath(os.path.dirname(__file__))


class PackedApp():
    def __init__(self, project: Project):
        self._config = project.pyproject.settings.setdefault("win-packer", {})
        self.config = self._config
        self._package_dir = os.path.join(project.root, project.pyproject.settings.get("build", {}).get("package-dir", "."))
        self.app_name = self._config.get("app_name", project.pyproject.metadata.get("name"))
        self.app_version = project.pyproject.metadata.get("version", "0.0.0")
        self.py_version = self._config.get("py_version", DEFAULT_PY_VERSION)
        self.py_bit = int(self._config.get("py_bit", DEFAULT_PY_BIT))
        self.include_msvcrt = self._config.get("include_msvcrt", True)
        self.license = self._config.get("license", None)
        self.icon = self._config.get("icon", os.path.join(_PKGDIR, 'glossyorb.ico'))
        self.project = project
        self.build_dir = self._config.get("build_directory", os.path.join('build', 'winpacker'))
        self.dist_dir = self._config.get("dist_directory", os.path.join('dist',))

        self.install_files = []
        self.install_dirs = []
        self.msvcrt_files = []
        self.extra_files = []
        self.artifacts = []

    def clean_build_directry(self) -> None:
        if os.path.exists(self.build_dir):
            shutil.rmtree(self.build_dir)
        os.makedirs(self.build_dir)

        if not os.path.exists(self.dist_dir):
            os.makedirs(self.dist_dir)
