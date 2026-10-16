; Inno Setup 6 のインストーラー定義。packaging/build.ps1 から呼ばれる。
; 管理者権限なしで、ユーザーごと（%LOCALAPPDATA%\Programs\kotoba-desktop）に入れる。
; 設定（%APPDATA%\kotoba-desktop）と音声認識のモデル（Hugging Face のキャッシュ）はアンインストールしても残す。

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "kotoba-desktop"
#define AppExe "kotoba-desktop.exe"

[Setup]
; AppId はアップデートとアンインストールの識別に使うので変えない
AppId={{6C1F4E2B-8D3A-4F7E-9B21-5A0C7D9E3F14}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=AkiraMatsumoto-github
AppPublisherURL=https://github.com/AkiraMatsumoto-github/kotoba-desktop
AppSupportURL=https://github.com/AkiraMatsumoto-github/kotoba-desktop/issues
DefaultDirName={localappdata}\Programs\{#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.22000
OutputDir=..\dist
OutputBaseFilename={#AppName}-{#AppVersion}-setup
SetupIconFile=kotoba-desktop.ico
UninstallDisplayIcon={app}\{#AppExe}
LicenseFile=..\LICENSE
Compression=lzma2/ultra64
SolidCompression=yes
LZMANumBlockThreads=4
; コンパイラは 32 ビットで、cuBLAS（約 670 MB）を圧縮するとメモリが足りなくなるので 64 ビットの別プロセスで圧縮する
LZMAUseSeparateProcess=yes
WizardStyle=modern
; 起動中なら閉じてから上書きする
CloseApplications=force
RestartApplications=no

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "startup"; Description: "Windows にサインインしたときに起動する"; GroupDescription: "追加の設定:"
Name: "desktopicon"; Description: "デスクトップにショートカットを作る"; GroupDescription: "追加の設定:"; Flags: unchecked

[Files]
Source: "..\dist\kotoba-desktop\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; 前のバージョンの部品が残らないよう、上書きの前に消す
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: startup

[Run]
Filename: "{app}\{#AppExe}"; Description: "kotoba-desktop を起動する"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; 常駐していると DLL を消せないので先に終了させる
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im {#AppExe}"; Flags: runhidden; RunOnceId: "StopApp"
