; LED Raster Designer - Windows installer (Inno Setup 6)
;
; Built by .github/workflows/release.yml on the Windows runner, which passes:
;   /DAppVersion=1.7.0            the release label (a beta passes 1.7.0-beta.1)
;   /DAppNumericVersion=1.7.0     the top entry of src/VERSION.txt
;   /DBundleDir=<path>            the PyInstaller output folder
;   /O<dir>                       where the setup file is written
; and, for the upgrade smoke test only, /DSmokeFastBuild (no compression).
;
; Per-user install: {autopf} is %LOCALAPPDATA%\Programs because setup runs
; with lowest privileges, so a crew laptop never needs an admin password.
; The app keeps its own data OUTSIDE this folder (logs and presets under
; %LOCALAPPDATA%\LED Raster Designer, settings under %APPDATA%\LED Raster
; Designer), so neither an upgrade nor the uninstaller ever touches it.

#ifndef AppVersion
  #error Pass the version: ISCC /DAppVersion=1.7.0 /DAppNumericVersion=1.7.0
#endif
#ifndef AppNumericVersion
  #define AppNumericVersion AppVersion
#endif
#ifndef BundleDir
  #define BundleDir "..\LED Raster Designer App"
#endif

#define AppName "LED Raster Designer"
#define AppExeName "LED Raster Designer.exe"

[Setup]
; NEVER change AppId. It is how a new version finds and replaces the old one,
; and how Settings > Apps knows they are the same program.
; (tests/test_windows_installer.py pins it.)
AppId={{7D7BC445-209D-4629-A5D7-1C0B7EDC0C94}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=kman1898
AppPublisherURL=https://github.com/kman1898/LED-Raster-Designer
AppSupportURL=https://github.com/kman1898/LED-Raster-Designer/issues
AppUpdatesURL=https://github.com/kman1898/LED-Raster-Designer/releases
VersionInfoVersion={#AppNumericVersion}
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName} Setup
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#AppName}
DisableDirPage=auto
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
UsePreviousTasks=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
SetupIconFile=..\src\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
WizardStyle=modern
OutputBaseFilename=led_raster_designer_v{#AppVersion}_windows_setup
; A running copy holds its own files open. [Code] asks to close it first;
; the Restart Manager is the fallback if that check cannot run.
CloseApplications=force
RestartApplications=no
#ifdef SmokeFastBuild
Compression=none
#else
Compression=lzma2/max
SolidCompression=yes
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; The bundled runtime is replaced whole, so a file a newer build no longer
; ships cannot linger and be loaded beside the new ones.
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\.lrd-unblocked"

[Files]
; .lrd-unblocked and launcher_crash.log are written by the app at run time;
; the CI smoke tests create them in the build folder before this runs.
Source: "{#BundleDir}\*"; DestDir: "{app}"; Excludes: ".lrd-unblocked,launcher_crash.log"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
; The app's own Update runs setup with /RELAUNCH (src/updater.py
; INSTALLER_ARGS) and quits; this reopens it when the install is done. An
; ordinary silent install has no /RELAUNCH, so the app stays closed.
Filename: "{app}\{#AppExeName}"; Flags: nowait; Check: RelaunchRequested

[UninstallDelete]
; Only files the app writes beside itself. User data lives elsewhere and stays.
Type: files; Name: "{app}\.lrd-unblocked"
Type: files; Name: "{app}\launcher_crash.log"
Type: dirifempty; Name: "{app}"

[Code]
const
  RunKey = 'Software\Microsoft\Windows\CurrentVersion\Run';

{ True when setup was started with /RELAUNCH, which only the app's own
  Update passes. Setup ignores a switch it does not know, so this reads the
  command line itself. }
function RelaunchRequested(): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), '/RELAUNCH') = 0 then
    begin
      Result := True;
      Exit;
    end;
end;

{ How many copies of the app are running from THIS install folder. A copy
  run from anywhere else (an old unzipped folder) is left alone. With
  Terminate, each one found is closed. }
function RunningCopies(const ExePath: String; Terminate: Boolean): Integer;
var
  Locator, Service, Procs, Proc: Variant;
  I: Integer;
begin
  Result := 0;
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Service := Locator.ConnectServer('', 'root\CIMV2', '', '');
    Procs := Service.ExecQuery('SELECT ProcessId, ExecutablePath FROM Win32_Process WHERE Name = "{#AppExeName}"');
    for I := 0 to Procs.Count - 1 do
    begin
      Proc := Procs.ItemIndex(I);
      if not VarIsNull(Proc.ExecutablePath) then
        if CompareText(Proc.ExecutablePath, ExePath) = 0 then
        begin
          Result := Result + 1;
          if Terminate then
            Proc.Terminate(0);
        end;
    end;
  except
    Log('Could not check for a running copy: ' + GetExceptionMessage);
    Result := 0;
  end;
end;

function CloseRunningCopy(const ExePath, Question: String): Boolean;
var
  I: Integer;
begin
  Result := True;
  if RunningCopies(ExePath, False) = 0 then
    Exit;
  if SuppressibleMsgBox(Question, mbConfirmation, MB_OKCANCEL, IDOK) <> IDOK then
  begin
    Result := False;
    Exit;
  end;
  RunningCopies(ExePath, True);
  for I := 1 to 50 do
  begin
    if RunningCopies(ExePath, False) = 0 then
      Exit;
    Sleep(200);
  end;
  Result := RunningCopies(ExePath, False) = 0;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not CloseRunningCopy(ExpandConstant('{app}\{#AppExeName}'),
      '{#AppName} is open. Save your show, then click OK to close it and continue, or click Cancel to stop.') then
    Result := '{#AppName} is still open. Quit it from its icon in the system tray, then run setup again.';
end;

function InitializeUninstall(): Boolean;
begin
  Result := CloseRunningCopy(ExpandConstant('{app}\{#AppExeName}'),
      '{#AppName} is open. Save your show, then click OK to close it and uninstall, or click Cancel to stop.');
  if not Result then
    SuppressibleMsgBox('{#AppName} is still open. Quit it from its icon in the system tray, then uninstall again.',
      mbError, MB_OK, IDOK);
end;

{ Run at Login (Windows) writes a Run value pointing at the exe. Once the exe
  is gone that value only points at nothing, so drop it, but only when it
  points into this install folder. }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Value: String;
begin
  if CurUninstallStep = usPostUninstall then
    if RegQueryStringValue(HKCU, RunKey, '{#AppName}', Value) then
      if Pos(Lowercase(ExpandConstant('{app}\')), Lowercase(Value)) > 0 then
        RegDeleteValue(HKCU, RunKey, '{#AppName}');
end;
