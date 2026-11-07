; Installer HarmoniSATB Studio (Inno Setup 6).
; Dibuat oleh tools\build_installer.py setelah PyInstaller selesai:
;   ISCC.exe /DMyAppVersion=1.2.0 installer\HarmoniSATB.iss
;
; - Instal per pengguna (tanpa hak administrator) ke %LOCALAPPDATA%\Programs\HarmoniSATB Studio,
;   atau ke Program Files bila pengguna memilih "untuk semua pengguna".
; - Shortcut Start Menu dan Desktop.
; - Uninstall hanya menghapus file aplikasi. Data pengguna TIDAK dihapus:
;   %APPDATA%\HarmoniSATB (pengaturan, kalibrasi, log) dan folder proyek (Documents\HarmoniSATB).

#ifndef MyAppVersion
  #define MyAppVersion "1.2.0"
#endif
#define MyAppName "HarmoniSATB Studio"
#define MyAppExe "HarmoniSATB Studio.exe"
#define SourceDir "..\dist\HarmoniSATB Studio"

[Setup]
AppId={{8C2F6B9E-4A1D-4E7B-9C3F-2D5E8A1B7C40}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=HarmoniSATB
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=Output
OutputBaseFilename=HarmoniSATB-Studio-{#MyAppVersion}-Setup
SetupIconFile=..\src\chorale\ui\assets\harmonisatb.ico
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes

[Languages]
; Bahasa Indonesia bukan terjemahan resmi Inno Setup; wizard memakai bahasa Inggris,
; teks khusus aplikasi di bawah memakai Bahasa Indonesia.
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
english.DesktopIcon=Buat shortcut di Desktop
english.ExtraIcons=Shortcut tambahan:
english.LaunchApp=Jalankan HarmoniSATB Studio sekarang

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"; GroupDescription: "{cm:ExtraIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent
