[Setup]
AppId={{93743588-BDCB-48B4-B57A-FEDBEBB0ADDC}
AppName=capcut_helper
AppVersion={#VERSION}
AppPublisher=cookaihq
DefaultDirName={localappdata}\Programs\capcut_helper
DefaultGroupName=capcut_helper
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=capcut_helper-x64-v{#VERSION}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\capcut_helper.exe
SetupIconFile=..\backend\assets\icon.ico

[Files]
Source: "..\dist\capcut_helper\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\capcut_helper"; Filename: "{app}\capcut_helper.exe"
Name: "{group}\卸载 capcut_helper"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\capcut_helper.exe"; Description: "立即启动 capcut_helper"; Flags: nowait postinstall skipifsilent

[Code]
// Restart Manager 关不掉 pystray 托盘 / pywebview 进程（无标准顶级窗口），
// 装包前直接 taskkill 旧实例 + 全部子进程，避免 DeleteFile failed; code 5。
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{cmd}'), '/C taskkill /F /IM capcut_helper.exe /T', '',
       SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(500);
  Result := '';
end;
