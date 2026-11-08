#ifndef StageDir
  #error StageDir must point to the staged application
#endif
#ifndef InstallerAppId
  #define InstallerAppId "{{D995F88D-982B-4AD1-8346-43FA20FE0F66}"
#endif
#ifndef InstallerName
  #define InstallerName "Ink Studio"
#endif
#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef ReleaseDir
  #error ReleaseDir is required
#endif

[Setup]
AppId={#InstallerAppId}
AppName={#InstallerName}
AppVersion={#AppVersion}
AppVerName={#InstallerName} {#AppVersion} Preview
AppPublisher=Ink Studio contributors
DefaultDirName={localappdata}\Programs\Ink Studio
DefaultGroupName=Ink Studio
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
WizardStyle=modern
DisableProgramGroupPage=yes
DisableWelcomePage=no
LicenseFile={#StageDir}\LICENSE
InfoBeforeFile={#StageDir}\docs\INSTALL.txt
SetupIconFile={#StageDir}\resources\ink-studio.ico
UninstallDisplayIcon={app}\Ink Studio.exe
OutputDir={#ReleaseDir}
OutputBaseFilename=InkStudio-{#AppVersion}-windows-x64-setup
Compression=lzma2/fast
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
UninstallLogMode=append
AppMutex=InkStudioSetup
VersionInfoDescription=Ink Studio Setup
VersionInfoVersion={#AppVersion}.0
VersionInfoProductName=Ink Studio
VersionInfoProductVersion={#AppVersion}.0

[Tasks]
Name: desktopicon; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "portable.txt"

[Icons]
Name: "{group}\Ink Studio"; Filename: "{app}\Ink Studio.exe"
Name: "{group}\Ink Studio Settings"; Filename: "{app}\Ink Studio.exe"; Parameters: "--settings"
Name: "{group}\Ink Studio Setup and Diagnostics"; Filename: "{app}\Ink Studio.exe"; Parameters: "--setup"
Name: "{group}\Stop Ink Studio"; Filename: "{app}\Ink Studio.exe"; Parameters: "--stop"
Name: "{group}\Ink Studio User Guide"; Filename: "{app}\docs\INSTALL.txt"
Name: "{autodesktop}\Ink Studio"; Filename: "{app}\Ink Studio.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Ink Studio.exe"; Description: "Open Ink Studio"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\Ink Studio.exe"; Parameters: "--stop --quiet"; Flags: runhidden waituntilterminated; RunOnceId: "StopStudio"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var Code: Integer;
begin
  Result := '';
  if FileExists(ExpandConstant('{app}\Ink Studio.exe')) then begin
    if not Exec(ExpandConstant('{app}\Ink Studio.exe'), '--stop --quiet', '', SW_HIDE, ewWaitUntilTerminated, Code) or (Code <> 0) then
      Result := 'Close Ink Studio before upgrading. Your projects will be retained.';
  end;
end;

