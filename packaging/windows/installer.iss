; Inno Setup script for MorningRoutine-Setup.exe. Installs for the current user (no admin needed).
; Build: iscc /DAppVersion=1.6.0 packaging\windows\installer.iss
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8C2B6C1E-6F3A-4C0E-9D7B-4D0A1E2F3B10}
AppName=Morning Routine
AppVersion={#AppVersion}
AppPublisher=John Thein
AppPublisherURL=https://github.com/tegn-co/Good-Meuwning-Routines
DefaultDirName={localappdata}\Programs\Morning Routine
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=MorningRoutine-Setup
SetupIconFile=morning-routine.ico
UninstallDisplayIcon={app}\MorningRoutine.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Close a running copy so an update can replace its files
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "dist\MorningRoutine\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{userprograms}\Morning Routine"; Filename: "{app}\MorningRoutine.exe"
Name: "{userdesktop}\Morning Routine"; Filename: "{app}\MorningRoutine.exe"; Tasks: desktopicon

[Registry]
; The app adds itself to "start at login"; remove that again when uninstalled
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "Morning Routine"; Flags: uninsdeletevalue

[Run]
; Also runs after a silent update from inside the app, so the app comes back
Filename: "{app}\MorningRoutine.exe"; Description: "{cm:LaunchProgram,Morning Routine}"; Flags: nowait postinstall
