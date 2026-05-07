#define MyAppName "smolJPEG Image Compression"
#define MyAppExeName "smolJPEG Image Compression.exe"

#ifndef MyAppVersion
  #define MyAppVersion "0.1.8"
#endif

#ifndef MyAppPublisher
  #define MyAppPublisher "Silvergreen333"
#endif

#ifndef MyAppPublisherURL
  #define MyAppPublisherURL "https://github.com/silvergreen333/smolJPEG_Image_Compression"
#endif

#ifndef SourceDir
  #define SourceDir "..\artifacts\standalone"
#endif

#ifndef OutputDir
  #define OutputDir "output"
#endif

[Setup]
AppId={{4B7FB3E2-A63C-4D44-9A71-8C867F78A195}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppPublisherURL}
AppSupportURL={#MyAppPublisherURL}
AppUpdatesURL={#MyAppPublisherURL}
DefaultDirName={autopf}\smolJPEG Image Compression
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
OutputDir={#OutputDir}
OutputBaseFilename=smolJPEG_Setup_{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\smolJPEG_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
#ifdef EnableSigning
SignTool=signtool
SignedUninstaller=yes
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\smolJPEG Image Compression"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\smolJPEG Image Compression"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch smolJPEG Image Compression"; Flags: nowait postinstall skipifsilent
