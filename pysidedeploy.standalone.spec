[app]
title = smolJPEG Image Compression
project_dir = .
input_file = main.py
project_file = 
exec_directory = .
icon = smolJPEG_icon.ico
python_path = .venv\Scripts\python.exe

[python]
packages = PySide6,PIL
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
mode = standalone
extra_args = --quiet --noinclude-qt-translations --windows-console-mode=disable --assume-yes-for-downloads --include-data-files=smolJPEG_icon.ico=smolJPEG_icon.ico --include-data-files=LICENSE=LICENSE --include-data-files=THIRD_PARTY_NOTICES.txt=THIRD_PARTY_NOTICES.txt --include-data-dir=third_party_licenses=third_party_licenses

[buildozer]
mode = release
recipe_dir = 
jars_dir = 

