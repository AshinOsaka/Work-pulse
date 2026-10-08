; Inno Setup script for the WorkPulse agent (https://jrsoftware.org/isinfo.php)
;   iscc packaging\installer.iss
; Per-user install: no administrator rights, installs to %LOCALAPPDATA%\Programs\WorkPulse.
;
; Silent / managed deployment (Intune, SCCM, GPO):
;   WorkPulseAgentSetup-0.5.0.exe /VERYSILENT /SUPPRESSMSGBOXES /API=https://workpulse.example.com/api /CODE=WP-XXXX-XXXX-XXXX

#define AppName "WorkPulse Agent"
#define AppVersion "0.5.0"
#define AppExe "WorkPulseAgent.exe"

[Setup]
AppId={{6F2C7D8E-4B1A-4E5F-9C3D-2A7B8E9F0C11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=WorkPulse
DefaultDirName={localappdata}\Programs\WorkPulse
DefaultGroupName=WorkPulse
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=WorkPulseAgentSetup-{#AppVersion}
SetupIconFile=workpulse.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Files]
Source: "..\dist\WorkPulseAgent\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\WorkPulse"; Filename: "{app}\{#AppExe}"

[Registry]
; Start with Windows for the installing user (the agent can toggle this from its tray menu).
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "WorkPulseAgent"; \
  ValueData: """{app}\{#AppExe}"" --minimized"; Flags: uninsdeletevalue

[INI]
; Pre-configure the server for managed installs (/API=...); otherwise the default is used.
Filename: "{localappdata}\WorkPulse\Agent\agent.ini"; Section: "agent"; Key: "api_url"; String: "{param:API|}"; Check: HasParam('API')

[Run]
; Managed install: enrol silently with an admin-issued code (/CODE=...).
Filename: "{app}\{#AppExe}"; Parameters: "--headless --enroll-code {param:CODE|} --run-for 1"; Flags: runhidden waituntilterminated; Check: HasParam('CODE')
Filename: "{app}\{#AppExe}"; Description: "Start WorkPulse"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\{#AppExe}"; Parameters: "--sign-out"; Flags: runhidden waituntilterminated; RunOnceId: "SignOut"

[UninstallDelete]
; Remove local encrypted state (credentials, queue, logs) on uninstall.
Type: filesandordirs; Name: "{localappdata}\WorkPulse\Agent"

[Code]
function HasParam(Name: String): Boolean;
begin
  Result := ExpandConstant('{param:' + Name + '|}') <> '';
end;
