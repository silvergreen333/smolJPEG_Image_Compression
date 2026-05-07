[app]
title = smolJPEG Image Compression
project_dir = .
project_file = main.py
exec_directory = .
icon = smolJPEG_icon.ico
python_path = .venv\Scripts\python.exe

[python]
packages = PySide6,PIL

# local python source folders to include
packages_dir = app
python_path = .\.venv\Scripts\python.exe

[qt]
qml_files = 
excluded_qml_plugins = 
modules = Core,Gui,Widgets
plugins = accessiblebridge,egldeviceintegrations,generic,iconengines,imageformats,platforminputcontexts,platforms,platforms/darwin,platformthemes,styles,wayland-decoration-client,wayland-graphics-integration-client,wayland-shell-integration,xcbglintegrations

[deploy]
output_dir = .
verbose = False
dry_run = False
keep_deployment_files = False
force = True

[nuitka]
mode = onefile

# include the app icon plus all external helper tools inside the onefile bundle.
# --include-data-files is the documented option for specific files in onefile mode.
extra_args = --quiet --noinclude-qt-translations --windows-console-mode=disable --include-data-files=smolJPEG_icon.ico=smolJPEG_icon.ico --include-data-files=tools/jpegli/cjpegli.exe=tools/jpegli/cjpegli.exe --include-data-files=tools/mozjpeg/cjpeg.exe=tools/mozjpeg/cjpeg.exe --include-data-files=tools/butteraugli/butteraugli.exe=tools/butteraugli/butteraugli.exe

[buildozer]
mode = release
recipe_dir = 
jars_dir = 

