#ifndef AppVersion
  #define AppVersion "4.0.0"
#endif

#ifndef SourceMode
  #define SourceMode "onedir"
#endif

#ifndef OutputTag
  #define OutputTag SourceMode
#endif

#ifndef ProjectRoot
  #define ProjectRoot ".."
#endif

#ifndef DistDir
  #define DistDir AddBackslash(ProjectRoot) + "dist"
#endif

#ifndef OutputDir
  #define OutputDir AddBackslash(DistDir) + "installer"
#endif

#ifndef IconPath
  #define IconPath AddBackslash(ProjectRoot) + "assets\annual_report_spider.ico"
#endif

#define MyAppId "{{72F07C9E-2BF3-4D84-90C0-80D07747488B}"
#define MyAppName "Annual Report Spider"
#define MyAppNameZh "年报抓取桌面版"
#define MyAppPublisher "Little-pig-create"
#define MyAppExeName "AnnualReportSpiderGUI.exe"
#define MyAppGroupName "Annual Report Spider"
#define MyAppURL "https://github.com/Little-pig-create/AnnualReportSpider"

[Setup]
AppId={#MyAppId}
AppName={#MyAppNameZh}
AppVersion={#AppVersion}
AppVerName={#MyAppNameZh} {#AppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\AnnualReportSpider
DefaultGroupName={#MyAppGroupName}
AllowNoIcons=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
OutputDir={#OutputDir}
OutputBaseFilename=AnnualReportSpiderGUI-Setup-{#AppVersion}-{#OutputTag}
SetupIconFile={#IconPath}
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=110
DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=no
DisableReadyMemo=no
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
english.BeveledLabel=年报抓取桌面版安装向导
english.SetupWindowTitle=安装 - 年报抓取桌面版
english.WelcomeLabel1=欢迎使用年报抓取桌面版安装向导
english.WelcomeLabel2=本向导将帮助你在当前电脑上安装年报抓取桌面版。建议关闭其他正在运行的程序后继续。
english.SelectDirLabel3=请选择安装位置。建议保留默认目录。
english.SelectStartMenuFolderLabel3=请选择开始菜单文件夹，用于创建程序快捷方式。
english.ReadyLabel1=准备开始安装
english.ReadyLabel2a=安装程序已准备好将年报抓取桌面版安装到你的电脑。
english.ReadyMemoDir=安装目录:
english.ReadyMemoGroup=开始菜单:
english.ReadyMemoTasks=附加任务:
english.ReadyMemoTask= - %1
english.FinishedHeadingLabel=安装完成
english.FinishedLabelNoIcons=年报抓取桌面版已经成功安装完成。
english.FinishedLabel=年报抓取桌面版已经成功安装完成。你现在可以立即启动程序。
english.LaunchProgram=立即启动年报抓取桌面版
english.AdditionalIcons=附加任务:
english.CreateDesktopIcon=创建桌面快捷方式
english.ProgramOnTheWeb=项目主页
english.UninstallProgram=卸载年报抓取桌面版

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
#if SourceMode == "onedir"
Source: "{#DistDir}\AnnualReportSpiderGUI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#else
Source: "{#DistDir}\AnnualReportSpiderGUI.exe"; DestDir: "{app}"; Flags: ignoreversion
#endif
Source: "{#ProjectRoot}\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ProjectRoot}\RELEASE_NOTES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\年报抓取桌面版"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\项目说明"; Filename: "{app}\README.md"
Name: "{group}\发布说明"; Filename: "{app}\RELEASE_NOTES.md"
Name: "{group}\项目主页"; Filename: "{#MyAppURL}"
Name: "{group}\卸载年报抓取桌面版"; Filename: "{uninstallexe}"
Name: "{autodesktop}\年报抓取桌面版"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram}"; Flags: nowait postinstall skipifsilent
