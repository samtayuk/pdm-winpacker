import os
from zipfile import ZipFile
from pdm import termui

class ZipPacker:
    def __init__(self, packed_app) -> None:
        self.packed_app = packed_app
        self.project = packed_app.project
        self.file_paths = []

    @property
    def zip_name(self):
        """Generate the filename of the installer exe

        e.g. My_App_1.0.exe
        """
        s = f"{self.packed_app.app_name}_{self.packed_app.app_version}.zip"
        return s.replace(' ', '_')

    def _get_all_file_paths(self):
        cwd = os.getcwd()
        os.chdir(self.packed_app.build_dir)

        for root, directories, files in os.walk("."):
            for filename in files:
                if not filename in ["_system_path.py", "installer.nsi"]:
                    filepath = os.path.join(root, filename)
                    self.file_paths.append(filepath)

        os.chdir(cwd)

    def pack(self):
        with self.project.core.ui.open_spinner("Creating zip package..."):
            self._get_all_file_paths()
            output = os.path.abspath(os.path.join(self.packed_app.dist_dir, self.zip_name))
            if os.path.exists(output):
                os.remove(output)

            cwd = os.getcwd()
            os.chdir(self.packed_app.build_dir)
            with ZipFile(output,"w") as zip:
                for file in self.file_paths:
                    zip.write(file)
            os.chdir(cwd)

        self.project.core.ui.echo(f"[success]{termui.Emoji.SUCC}[/] Zip package built: {output}", style="success")
        self.packed_app.artifacts.append(output)
        return output

