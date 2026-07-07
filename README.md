# PS5 Dump & Image Converter

![Platform](https://img.shields.io/badge/platform-Windows-0078D6)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)
![Status](https://img.shields.io/badge/status-release--ready-brightgreen)
![Version](https://img.shields.io/badge/version-v1.7.80-blue)

Windows desktop tool for converting, packing, unpacking, validating and editing PS5 dump formats.

The project combines a GUI workflow with native MkPFS-based paths, targeted admin helpers and automated validation for the main task flows.

## Contents

- [Current Status](#current-status)
- [Main Features](#main-features)
- [Supported Tasks](#supported-tasks)
- [Important Notes](#important-notes)
- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [Targeted Admin Runs](#targeted-admin-runs)
- [Validation](#validation)
- [Project Files](#project-files)
- [Documentation](#documentation)
- [Credits](#credits)
- [Thanks](#thanks)
- [License / Notice](#license--notice)

## Current Status

Release-ready on the current `main` branch.

Validated on the current release state with:
- Quality suite: 8/8 PASS
- Build readiness: 7/7 PASS
- Fresh EXE build: `dist/PS5_Dump_Image_Converter_v1.7.80.exe`
- Targeted admin validation for task 7 with `.ffpkg`: PASS

Best current reference artifacts:
- Admin validation report for task 7 `.ffpkg`: `_e2e_output_a7_ffpkg_admin_live_20260707_direct4/e2e_report_a7.json`
- Build script: `Build_EXE.ps1`
- Main application: `PS5ImageConverter_Pro_FINAL_revised.py`

## Main Features

- Pack PS5 game dump folders to `.ffpfsc`
- Convert `.ffpfsc` to `.exfat`
- Convert `.exfat` to `.ffpfsc`
- Unpack `.ffpfsc` to a game dump folder
- Unpack `.exfat` to a game dump folder
- Convert `.ffpkg` to `.ffpfsc`
- Manage `fakelib` and root files in dump sources
- Auto-generate `ampr_emu.index` for task 7 when `fakelib/libSceAmpr.sprx` is present
- Validate dump structures and artifacts
- Build a standalone Windows EXE with PyInstaller

## Who This Is For

- Users who want a Windows GUI for common PS5 dump conversion workflows
- Users who need repeatable admin-assisted validation for selected tasks
- Homebrew-oriented workflows that benefit from MkPFS-based packing and extraction paths

## Supported Tasks

1. Game dump folder -> `.ffpfsc`
2. `.ffpfsc` -> `.exfat`
3. `.exfat` -> `.ffpfsc`
4. `.ffpfsc` -> game dump folder
5. `.exfat` -> game dump folder
6. `.ffpkg` -> `.ffpfsc`
7. `fakelib` manager for folder / `.ffpfsc` / `.exfat` / `.ffpkg`
8. Dump validator

## Important Notes

- Tasks 1, 2, 4 and 5 can require administrator rights.
- Task 7 with `.ffpkg` input usually also requires administrator rights because extraction uses the UFS2Tool/Dokan path.
- For task 7, `.ffpkg` is supported as an input format, but the edited result is written as `.ffpfsc`.
- Task 7 regenerates `ampr_emu.index` automatically when an AMPR emulation marker (`fakelib/libSceAmpr.sprx`) is detected.
- For exFAT-related workflows, OSFMount must be installed and usable.
- The validator is intended to detect incomplete or implausible dump structures early.

## Requirements

- Windows
- Python 3.10 or newer for the `.py` workflow
- Sufficient free disk space for temporary files and output artifacts
- Administrator rights for elevated workflows

Python dependencies are defined in `requirements.txt`.

## Quick Start

### Run the Python version

```powershell
python PS5ImageConverter_Pro_FINAL_revised.py
```

### Build the EXE

```powershell
.\Build_EXE.ps1
```

### Run the built EXE

Start the generated file from:

```text
dist/PS5_Dump_Image_Converter_v1.7.80.exe
```

## Typical Workflows

### Convert a game dump folder to `.ffpfsc`

```powershell
python PS5ImageConverter_Pro_FINAL_revised.py
```

Then select task 1, choose the dump folder, choose an output directory and start the task.

### Edit `fakelib` from a `.ffpkg` source

1. Start the application
2. Select task 7
3. Choose a `.ffpkg` source
4. Confirm UAC / administrator rights if required
5. Apply `fakelib` or root-file changes
6. Save the result as `.ffpfsc`

## Targeted Admin Runs

The repository includes an elevated runner for targeted validation of single tasks:

```powershell
.\Run_Tasks_1_8_Admin.ps1 -Task A7 -Dump .\path\to\DumpFolder -Ffpkg ".\path\to\input.ffpkg" -OutputDir .\_e2e_output_a7_admin
```

## Validation

### Quality suite

```powershell
python test_all_quality_new.py
```

### Build readiness

```powershell
python test_build_ready.py
```

### End-to-end runner

```powershell
python run_tasks_1_8_e2e.py --task A7 --dump .\path\to\DumpFolder --ffpkg ".\path\to\input.ffpkg" --output-dir .\_e2e_output_a7
```

## Documentation

- `Build_EXE.ps1` for the Windows EXE build flow
- `Run_Tasks_1_8_Admin.ps1` for elevated single-task validation

## Project Files

- `PS5ImageConverter_Pro_FINAL_revised.py`: main GUI application and task logic
- `run_tasks_1_8_e2e.py`: automated task runner
- `Run_Tasks_1_8_Admin.ps1`: elevated runner for targeted admin validation
- `Build_EXE.ps1`: PyInstaller build script
- `test_all_quality_new.py`: current quality-suite entrypoint
- `test_build_ready.py`: build-readiness checks

## Credits

Special version by Strongt1me.

Core engine:
- Phoenixx1202 / PSBrew for MkPFS v0.0.9

Additional foundations and community contributions:
- KryoMod
- Renan Barreto
- Y2JB / PS5 Scene Community
- PS5 exFAT Image Builder / ps5-exfat-builder project contributors

Integrated tools and technical foundations:
- PassMark Software for OSFMount
- Dokan project
- UFS2Tool authors
- PyInstaller project
- paramiko
- Pillow
- cryptography
- zstandard
- zlib-ng

## Thanks

This project stands on the work of the PS5 homebrew community and the open-source ecosystem around it.

A special thank you goes to everyone who shares research, code, tooling and practical knowledge so others can build on it, learn from it and push the scene further.

This explicitly includes the creators and contributors behind PS5 exFAT Image Builder / ps5-exfat-builder, whose published groundwork and tooling helped shape important workflow directions in this project.

## License / Notice

Check the repository files and bundled tool licenses before redistribution. Different integrated tools and dependencies can have their own license terms.
