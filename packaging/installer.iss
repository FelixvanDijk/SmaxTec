#ifndef MyAppVersion
  #error MyAppVersion must be supplied by scripts/build_installer.ps1
#endif
#ifndef SourceDir
  #error SourceDir must be supplied by scripts/build_installer.ps1
#endif
#ifndef OutputDir
  #error OutputDir must be supplied by scripts/build_installer.ps1
#endif

#define MyAppName "SmaxTec Workbench"
#define MyAppExeName "SmaxTec Workbench.exe"

[Setup]
AppId={{7D62376C-0D57-46A9-A799-FD7E7EAB7E85}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=SmaxTec Workbench Project
AppComments=Independent data collection and analysis application; not an official smaXtec product.
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=SmaxTec-Workbench-Setup-{#MyAppVersion}-windows-x64
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes
UsePreviousGroup=yes
UsePreviousTasks=yes
UninstallDisplayName={#MyAppName} {#MyAppVersion}
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoDescription={#MyAppName} Windows installer
VersionInfoCompany=SmaxTec Workbench Project
SetupLogging=yes
#ifdef SignInstaller
SignTool=signtool
SignedUninstaller=yes
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\{#MyAppExeName}"
Type: files; Name: "{app}\START_HERE.txt"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Getting started"; Filename: "{app}\QUICK_START.html"
Name: "{group}\Third-party notices"; Filename: "{app}\THIRD_PARTY_NOTICES.txt"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Open {#MyAppName}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent
