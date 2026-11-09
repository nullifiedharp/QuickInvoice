; QuickInvoice installer - built by build.bat with Inno Setup 6
#define AppName "QuickInvoice"
#define AppVersion "1.0.0"
#define AppPublisher "NullHarp"
#define AppURL "https://github.com/nullifiedharp/QuickInvoice"

[Setup]
AppId={{1BD76848-C540-4139-B818-B5B9BAA35E94}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
; Per-user install: no admin prompt
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=LICENSE
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\QuickInvoice.exe
OutputDir=installer
OutputBaseFilename=QuickInvoice-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
; Checked by default - easiest for people who aren't comfortable finding apps
Name: "desktopicon"; Description: "Put a shortcut on the Desktop"; GroupDescription: "Shortcuts:"

[Files]
Source: "dist\QuickInvoice.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\QuickInvoice.exe"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\QuickInvoice.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\QuickInvoice.exe"; Description: "Open {#AppName} now"; Flags: nowait postinstall skipifsilent
