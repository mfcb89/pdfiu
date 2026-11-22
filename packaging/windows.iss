#define BuildRoot GetEnv("PDFIU_BUILD_DIR")
#if BuildRoot == ""
  #error Define PDFIU_BUILD_DIR first.
#endif
#include AddBackslash(BuildRoot) + "release.iss"
#define ShellClsid "10230B99-2AD4-4607-939D-7085BAFB4A96"

[Setup]
AppId={{AA1A6AE8-ED3A-4E53-8F00-B27DFB63F8FD}
AppName={#ProductName}
AppVersion={#ReleaseVersion}
AppPublisher=mfcb89
AppPublisherURL=https://github.com/mfcb89/pdfiu
AppSupportURL=https://github.com/mfcb89/pdfiu/issues
AppUpdatesURL=https://github.com/mfcb89/pdfiu/releases
LicenseFile=..\LICENSE
DefaultDirName={localappdata}\Programs\{#ProductName}
DefaultGroupName={#ProductName}
UsePreviousGroup=no
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
MinVersion=10.0.17763
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
UsePreviousAppDir=yes
CloseApplications=yes
RestartApplications=no
OutputBaseFilename={#ProductName}-{#ReleaseVersion}-Windows-x64
OutputDir={#BuildRoot}\installer
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\assets\brand\pdfiu-app.ico
UninstallDisplayIcon={app}\{#ProductName}.exe
ChangesAssociations=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
spanish.StartApp=Abrir PDFiu
english.StartApp=Open PDFiu
spanish.CombinePDFs=Combinar archivos con PDFiu
english.CombinePDFs=Merge files with PDFiu
spanish.AppDescription=Lector y editor de documentos PDF.
english.AppDescription=PDF reader and editor.
spanish.PDFDocument=Documento PDF
english.PDFDocument=PDF document
spanish.CheckFailed=No se pudo comprobar si PDFiu está abierto.
english.CheckFailed=Could not check whether PDFiu is running.
spanish.CloseFirst=Cierra PDFiu antes de continuar.
english.CloseFirst=Close PDFiu before continuing.
spanish.AskClose=PDFiu está abierto. ¿Quieres cerrar sus ventanas para continuar?
english.AskClose=PDFiu is running. Close its windows to continue?
spanish.SaveFirst=PDFiu te permitirá guardar los documentos con cambios.
english.SaveFirst=PDFiu will let you save documents with changes.
spanish.StillOpen=La instalación o desinstalación se detuvo porque PDFiu sigue abierto.
english.StillOpen=Setup stopped because PDFiu is still running.
spanish.RetryClose=PDFiu sigue abierto. Termina de guardar o cierra las ventanas pendientes y pulsa Reintentar.
english.RetryClose=PDFiu is still running. Finish saving or close the remaining windows, then click Retry.
spanish.CannotClose=No se pudo cerrar PDFiu. Cierra sus ventanas y vuelve a intentarlo.
english.CannotClose=Could not close PDFiu. Close its windows and try again.

[Files]
Source: "{#BuildRoot}\dist\{#ProductName}\PDFiuClose.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#BuildRoot}\dist\{#ProductName}\*"; Excludes: "PDFiuClose.exe"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#ProductName}"; Filename: "{app}\{#ProductName}.exe"

[Run]
Filename: "{app}\{#ProductName}.exe"; Description: "{cm:StartApp}"; Flags: nowait postinstall skipifsilent

[Registry]
Root: HKCU; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "PDFiu"; ValueData: "Software\PDFiu\Capabilities"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\PDFiu"; Flags: uninsdeletekeyifempty
Root: HKCU; Subkey: "Software\PDFiu\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "PDFiu"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\PDFiu\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "{cm:AppDescription}"
Root: HKCU; Subkey: "Software\PDFiu\Capabilities\FileAssociations"; ValueType: string; ValueName: ".pdf"; ValueData: "PDFiu.Document"
Root: HKCU; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "PDFiu.Document"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty
Root: HKCU; Subkey: "Software\Classes\PDFiu.Document"; ValueType: string; ValueData: "{cm:PDFDocument}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\PDFiu.Document\DefaultIcon"; ValueType: string; ValueData: """{app}\_internal\assets\brand\pdfiu-document.ico"",0"
Root: HKCU; Subkey: "Software\Classes\PDFiu.Document\shell\open\command"; ValueType: string; ValueData: """{app}\PDFiu.exe"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\Applications\PDFiu.exe"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "PDFiu"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Applications\PDFiu.exe\SupportedTypes"; ValueType: string; ValueName: ".pdf"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\Applications\PDFiu.exe\shell\open\command"; ValueType: string; ValueData: """{app}\PDFiu.exe"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\PDFiu.Combine"; ValueType: string; ValueData: "{cm:CombinePDFs}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\PDFiu.Combine"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\PDFiu.Combine"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\PDFiu.exe"",0"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\PDFiu.Combine\DropTarget"; ValueType: string; ValueName: "CLSID"; ValueData: "{{{#ShellClsid}}"
Root: HKCU; Subkey: "Software\Classes\CLSID\{{{#ShellClsid}}"; ValueType: string; ValueData: "PDFiu: combinar documentos"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\CLSID\{{{#ShellClsid}}\LocalServer32"; ValueType: string; ValueData: """{app}\PDFiuExplorer.exe"""

[InstallDelete]
Type: files; Name: "{app}\_internal\PySide6\translations\*.qm"
Type: files; Name: "{app}\_internal\pyphen\dictionaries\*"
Type: dirifempty; Name: "{app}\_internal\pyphen\dictionaries"
Type: dirifempty; Name: "{app}\_internal\pyphen"
Type: files; Name: "{app}\_internal\PIL\_avif*.pyd"

[UninstallDelete]
Type: files; Name: "{localappdata}\{#ProductName}\preferencias.ini"
Type: files; Name: "{localappdata}\{#ProductName}\preferencias.ini.lock"
Type: filesandordirs; Name: "{localappdata}\{#ProductName}\sesiones"
Type: filesandordirs; Name: "{localappdata}\{#ProductName}\logs"
Type: files; Name: "{localappdata}\{#ProductName}\shell\*.txt"
Type: dirifempty; Name: "{localappdata}\{#ProductName}\shell"
Type: dirifempty; Name: "{localappdata}\{#ProductName}"
Type: files; Name: "{localappdata}\Folio PDF\preferencias.ini"
Type: files; Name: "{localappdata}\Folio PDF\preferencias.ini.lock"
Type: filesandordirs; Name: "{localappdata}\Folio PDF\sesiones"
Type: dirifempty; Name: "{localappdata}\Folio PDF"

[Code]
const
  PreviousAppKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{AA1A6AE8-ED3A-4E53-8F00-B27DFB63F8FD}_is1';
  PDFiuStillOpen = 10;

var
  ReplacingLegacyVersion: Boolean;

function ClosePDFiu(const Helper, Arguments: String; Silent: Boolean): String;
var
  ExitCode: Integer;
begin
  Result := '';
  if not Exec(Helper, '--check ' + Arguments, '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
  begin
    Result := CustomMessage('CheckFailed');
    Exit;
  end;
  if ExitCode = 0 then
    Exit;
  if ExitCode <> PDFiuStillOpen then
  begin
    Result := CustomMessage('CheckFailed');
    Exit;
  end;
  if Silent then
  begin
    Result := CustomMessage('CloseFirst');
    Exit;
  end;
  if MsgBox(CustomMessage('AskClose') + #13#10#13#10 +
    CustomMessage('SaveFirst'), mbConfirmation, MB_YESNO) <> IDYES then
  begin
    Result := CustomMessage('StillOpen');
    Exit;
  end;
  repeat
    if Exec(Helper, '--close ' + Arguments, '', SW_HIDE, ewWaitUntilTerminated, ExitCode) and (ExitCode = 0) then
      Exit;
  until MsgBox(CustomMessage('RetryClose'),
    mbError, MB_RETRYCANCEL) <> IDRETRY;
  Result := CustomMessage('CannotClose');
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  PreviousDir, Arguments: String;
begin
  Arguments := AddQuotes(ExpandConstant('{app}'));
  if RegQueryStringValue(HKCU, PreviousAppKey, 'Inno Setup: App Path', PreviousDir) and (PreviousDir <> '') then
    Arguments := Arguments + ' ' + AddQuotes(PreviousDir);
  ExtractTemporaryFile('PDFiuClose.exe');
  Result := ClosePDFiu(ExpandConstant('{tmp}\PDFiuClose.exe'), Arguments, WizardSilent);
end;

function InitializeUninstall: Boolean;
var
  Error: String;
begin
  Error := ClosePDFiu(ExpandConstant('{app}\PDFiuClose.exe'), AddQuotes(ExpandConstant('{app}')), UninstallSilent);
  Result := Error = '';
  if not Result then
    SuppressibleMsgBox(Error, mbError, MB_OK, IDOK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  PreviousName, PreviousDir: String;
begin
  if CurStep = ssInstall then
    ReplacingLegacyVersion :=
      RegQueryStringValue(HKCU, PreviousAppKey,
        'DisplayName', PreviousName) and (PreviousName = 'Folio PDF') and
      RegQueryStringValue(HKCU, PreviousAppKey,
        'Inno Setup: App Path', PreviousDir) and (CompareText(PreviousDir, ExpandConstant('{app}')) = 0);
  if (CurStep = ssPostInstall) and ReplacingLegacyVersion then
  begin
    DeleteFile(ExpandConstant('{app}\Folio PDF.exe'));
    DeleteFile(ExpandConstant('{userprograms}\Folio PDF\Folio PDF.lnk'));
    RemoveDir(ExpandConstant('{userprograms}\Folio PDF'));
  end;
end;
