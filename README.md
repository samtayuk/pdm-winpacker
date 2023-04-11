# pdm-winpacker

A PDM plugin to bundle python application with python and create a installer using NSIS.

## Configuration

| Config item                                       | Description                                                               | Default value       | Required |
|---------------------------------------------------|---------------------------------------------------------------------------|---------------------|----------|
| `win-packer.app_name`                             | Application name                                                          |                     | Yes      |
| `win-packer.publisher`                            | Application publisher                                                     |                     | No       |
| `win-packer.icon`                                 | Application icon                                                          |                     | No       |
| `win-packer.py_version`                           | Python version for bundle                                                 |                     | Yes      |
| `win-packer.py_bit`                               | Python bit for bundle                                                     | 64                  | No       |
| `win-packer.local_wheels`                         | local list of wheel to add to bundle                                      | []                  | No       |
| `win-packer.commands.{command_name}.entry_point`  | Entry point for command                                                   |                     | Yes      |
| `win-packer.commands.{command_name}.console`      | If command is run in console                                              | `False`             | No       |
| `win-packer.commands.{command_name}.env`          | Dictionary of environment variables                                       | {}                  | No       |
| `win-packer.shortcuts.{shortcut_name}.target`     | Shortcut target                                                           |                     | Yes      |
| `win-packer.shortcuts.{shortcut_name}.parameters` | Parameters for shortcut                                                   |                     | No       |
| `win-packer.shortcuts.{shortcut_name}.icon`       | Icon for shortcut                                                         |                     | No       |

All configuration items use prefix `pdm.tool`, this is a viable configuration:

### Example configuration
```toml
[tool.pdm.win-packer]
app_name = "Project"
publisher = "Project Lead"
py_version = "3.10.10"
py_bit = "64"
local_wheels = ["wheels/Flask_APScheduler-1.12.4-py3-none-any.whl"]

[tool.pdm.win-packer.commands.project]
entry_point = "project:cli"
console = true
env = {PROJECT_ENV = "packaged"}

[tool.pdm.win-packer.shortcuts."Project Kiosk"]
target = "http://localhost:9797/kiosk"
parameters = "kiosk"
icon = "project.ico"

[tool.pdm.win-packer.shortcuts."Project Manage"]
target = "http://localhost:9797/manage"
```

## Usage

Note - nsismake is required to be installed.

* `pdm winpacker` - Command bundles the application with python and compiles the NSIS installer.
