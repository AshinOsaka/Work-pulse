; Inno Setup script for the WorkPulse agent (https://jrsoftware.org/isinfo.php)
;   iscc packaging\installer.iss
; Per-user install: no administrator rights, installs to %LOCALAPPDATA%\Programs\WorkPulse.
;
; Silent / managed deployment (Intune, SCCM, GPO):
;   WorkPulseAgentSetup-0.5.0.exe /VERYSILENT /SUPPRESSMSGBOXES /API=https://workpulse.example.com/api /CODE=WP-XXXX-XXXX-XXXX

#define AppName "WorkPulse Agent"
#define AppVersion "0.8.6"
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
; The running agent is closed by the [Code] below (it ignores Windows' polite "please close" request),
; so Windows' own close-applications prompt is not needed.
CloseApplications=no
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
; Automatic update (the agent ran this installer with /AUTOUPDATE=1): start the new version straight away.
Filename: "{app}\{#AppExe}"; Parameters: "--minimized"; Flags: nowait; Check: HasParam('AUTOUPDATE')

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

{ Is this user's WorkPulse agent running? (A per-user install: other people's agents are never touched.) }
function AgentRunning(): Boolean;
var
  Code: Integer;
begin
  Exec(ExpandConstant('{cmd}'),
    '/C tasklist /NH /FI "IMAGENAME eq {#AppExe}" /FI "USERNAME eq ' + GetUserNameString + '" | find /I "{#AppExe}" >NUL',
    '', SW_HIDE, ewWaitUntilTerminated, Code);
  Result := Code = 0;
end;

{ Close the running agent so its files can be replaced. Its work session and unsent data are saved on disk
  and the new version continues them. Returns False if it is still running after about 10 seconds. }
function CloseAgent(): Boolean;
var
  Code, Tries: Integer;
begin
  Tries := 0;
  while AgentRunning() and (Tries < 20) do
  begin
    Exec(ExpandConstant('{sys}\taskkill.exe'),
      '/F /IM {#AppExe} /FI "USERNAME eq ' + GetUserNameString + '"', '', SW_HIDE, ewWaitUntilTerminated, Code);
    Sleep(500);
    Tries := Tries + 1;
  end;
  Result := not AgentRunning();
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not CloseAgent() then
    Result := 'WorkPulse Agent is still running and could not be closed. Close it from the tray (or Task Manager) and run Setup again.';
end;

function InitializeUninstall(): Boolean;
begin
  { Close it first, so the sign-out step and the file removal both work. }
  CloseAgent();
  Result := True;
end;
