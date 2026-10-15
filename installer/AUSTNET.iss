; 安徽理工大学校园网助手 安装脚本
; 用 Inno Setup 6 编译：ISCC.exe installer\AUSTNET.iss

#define MyAppName "安徽理工大学校园网助手"
#define MyAppVersion "0.1.0"
#define MyAppExeName "AUSTNET.exe"

[Setup]
AppId={{A7F3C2E1-5B4D-4E7A-9C18-3D6E5F2B8A41}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=huaiyu
AppCopyright=Copyright (C) 2026 huaiyu
DefaultDirName={localappdata}\Programs\AUSTNET
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=AUSTNET-Setup-{#MyAppVersion}
SetupIconFile=..\assets\austnet-ok.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："
Name: "autostart"; Description: "开机自动启动"; GroupDescription: "附加任务："; Flags: checkedonce

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
    ValueName: "AUSTNET"; ValueData: """{app}\{#MyAppExeName}"" --tray"; \
    Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行 {#MyAppName}"; \
    Flags: nowait postinstall skipifsilent
