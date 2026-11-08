// Ink Studio Windows launcher, GPL-3.0-or-later. Uses the Windows .NET Framework.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

internal static class Launcher {
    internal static readonly string Root = Path.GetFullPath(AppDomain.CurrentDomain.BaseDirectory).TrimEnd('\\');
    internal static readonly string State = Path.GetFullPath(Environment.GetEnvironmentVariable("STUDIO_STATE_HOME") ??
        (File.Exists(Path.Combine(Root,"portable.txt")) ? Root : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Ink Studio")));
    internal static readonly string SettingsFile = Path.Combine(State,"config","settings.json");
    internal static readonly string SessionFile = Path.Combine(State,"runtime","session.json");
    internal static readonly string Logs = Path.Combine(State,"logs");
    internal static readonly string Python = Path.Combine(Root,"runtime","python","python.exe");
    internal static readonly JavaScriptSerializer Json = new JavaScriptSerializer();
    internal static readonly string Key = Hash(State.ToUpperInvariant());
    internal static bool Quiet;
    internal static bool Offline;
    static readonly object LogLock=new object();

    static string Hash(string value) {
        using(var hash=SHA256.Create()) return BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(value))).Replace("-","").Substring(0,24);
    }
    internal static Dictionary<string,object> Read(string path) {
        return File.Exists(path) ? Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(path,Encoding.UTF8)) : new Dictionary<string,object>();
    }
    internal static string Text(Dictionary<string,object> map,string key,string fallback="") {
        object value;return map.TryGetValue(key,out value) && value!=null ? Convert.ToString(value) : fallback;
    }
    internal static void Write(string path,object value) {
        Directory.CreateDirectory(Path.GetDirectoryName(path));
        string temp=path+"."+Guid.NewGuid().ToString("N")+".tmp";
        File.WriteAllText(temp,Json.Serialize(value),new UTF8Encoding(false));
        if(File.Exists(path))File.Replace(temp,path,null);else File.Move(temp,path);
    }
    internal static void Log(string message) {
        try {
            Directory.CreateDirectory(Logs);
            lock(LogLock)File.AppendAllText(Path.Combine(Logs,"launcher.log"),DateTime.UtcNow.ToString("o")+" "+message+Environment.NewLine,Encoding.UTF8);
        } catch(IOException) {} catch(UnauthorizedAccessException) {}
    }
    internal static string Quote(string arg) {
        var value=new StringBuilder("\"");int slashes=0;
        foreach(char ch in arg) {
            if(ch=='\\'){slashes++;continue;}
            if(ch=='\"')value.Append('\\',slashes*2+1).Append(ch);else value.Append('\\',slashes).Append(ch);
            slashes=0;
        }
        return value.Append('\\',slashes*2).Append('"').ToString();
    }
    internal static void Open(string value) {Process.Start(new ProcessStartInfo(value){UseShellExecute=true});}
    internal static Dictionary<string,object> Health(int port) {
        var request=(HttpWebRequest)WebRequest.Create("http://127.0.0.1:"+port+"/api/health");
        request.Proxy=null;request.Timeout=1500;request.ReadWriteTimeout=1500;
        using(var response=request.GetResponse())using(var stream=new StreamReader(response.GetResponseStream(),Encoding.UTF8))
            return Json.Deserialize<Dictionary<string,object>>(stream.ReadToEnd());
    }
    internal static bool OwnedProcess(Dictionary<string,object> session) {
        try {
            if(!String.Equals(Text(session,"root"),Root,StringComparison.OrdinalIgnoreCase))return false;
            using(var process=Process.GetProcessById(Convert.ToInt32(session["pid"]))) {
                if(process.HasExited || !String.Equals(process.MainModule.FileName,Python,StringComparison.OrdinalIgnoreCase) ||
                    process.StartTime.ToUniversalTime().Ticks!=Int64.Parse(Text(session,"startedTicks")))return false;
            }
            return true;
        } catch {return false;}
    }
    internal static bool SessionAlive(Dictionary<string,object> session) {
        if(!OwnedProcess(session))return false;
        try{return Text(Health(Convert.ToInt32(session["port"])),"instance")==Text(session,"instance");}catch{return false;}
    }
    static int Stop() {
        var session=Read(SessionFile);
        if(!OwnedProcess(session))return 0;
        try {
            using(var signal=EventWaitHandle.OpenExisting("Local\\InkStudioStop-"+Key))signal.Set();
        } catch(WaitHandleCannotBeOpenedException) {
            // Only a verified session can be stopped; never kill by port/name.
            using(var process=Process.GetProcessById(Convert.ToInt32(session["pid"])))process.Kill();
        }
        for(int i=0;i<100;i++){if(!OwnedProcess(session))return 0;Thread.Sleep(100);}
        return 2;
    }
    internal static ProcessStartInfo Backend(int port,string instance,string action="") {
        string script=Path.Combine(Root,"app","desktop.py");
        var info=new ProcessStartInfo(Python,"-X utf8 -B "+Quote(script)+" --port "+port+" --instance-id "+instance+" "+action+(Offline ? " --offline" : ""));
        info.WorkingDirectory=Root;info.UseShellExecute=false;info.CreateNoWindow=true;
        info.RedirectStandardOutput=true;info.RedirectStandardError=true;
        info.StandardOutputEncoding=Encoding.UTF8;info.StandardErrorEncoding=Encoding.UTF8;
        info.EnvironmentVariables["STUDIO_STATE_HOME"]=State;
        return info;
    }
    [STAThread] static int Main(string[] args) {
        bool headless=Array.IndexOf(args,"--headless")>=0;
        Offline=Array.IndexOf(args,"--offline")>=0;
        bool checkOnly=Array.IndexOf(args,"--check")>=0||Array.IndexOf(args,"--diagnostics")>=0||Array.IndexOf(args,"--setup-tools")>=0;
        Quiet=headless || checkOnly || Array.IndexOf(args,"--quiet")>=0;
        Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
        try {
#if LAYOUT_TEST
            if(args.Length>0) {
                using(var form=new SettingsForm()) {
                    form.Show();form.PerformLayout();Application.DoEvents();
                    using(var bitmap=new Bitmap(form.Width,form.Height)) {
                        form.DrawToBitmap(bitmap,new Rectangle(0,0,form.Width,form.Height));
                        bitmap.Save(args[0],System.Drawing.Imaging.ImageFormat.Png);
                    }
                }
                return 0;
            }
#endif
#if SETUP_FORM_TEST
            if(!(Environment.GetEnvironmentVariable("STUDIO_WINDOWS_DESKTOP")??"").StartsWith("InkStudio-engine-"))throw new Exception("Run the form test through the private-desktop engine launcher.");
            bool testCheck=args.Length>1;
            using(var form=new SetupForm(testCheck)) {
                form.Show();form.PerformLayout();Application.DoEvents();
                if(testCheck) {
                    DateTime deadline=DateTime.UtcNow.AddMinutes(2);
                    while(!form.CheckCompleted&&DateTime.UtcNow<deadline){Application.DoEvents();Thread.Sleep(25);}
                    if(!form.CheckCompleted)throw new Exception("Setup form check did not complete.");
                    bool expectedReady=args[1]=="--ready";
                    if(form.ContinueEnabled!=expectedReady||!form.ExportEnabled)throw new Exception("Setup form readiness or diagnostic export state is wrong.");
                } else if(form.ContinueEnabled)throw new Exception("Continue must require a successful check.");
                using(var bitmap=new Bitmap(form.Width,form.Height)) {
                    form.DrawToBitmap(bitmap,new Rectangle(0,0,form.Width,form.Height));
                    bitmap.Save(args[0],System.Drawing.Imaging.ImageFormat.Png);
                }
            }
            return 0;
#endif
            if(Array.IndexOf(args,"--stop")>=0)return Stop();
            if(Array.IndexOf(args,"--status")>=0)return SessionAlive(Read(SessionFile)) ? 0 : 1;
            if(Array.IndexOf(args,"--settings")>=0){if(headless)throw new Exception("Use the settings file or run --check for unattended setup.");using(var form=new SettingsForm())form.ShowDialog();return 0;}
            if(!File.Exists(Python)||!File.Exists(Path.Combine(Root,"package.json")))throw new Exception("The application package is incomplete. Extract or reinstall the complete Ink Studio package.");
            if(checkOnly || (headless&&Array.IndexOf(args,"--setup")>=0)) {
                string report=Path.Combine(Logs,"setup-check.json");
                int diagnosticIndex=Array.IndexOf(args,"--diagnostics");
                if(diagnosticIndex>=0) {
                    if(diagnosticIndex+1>=args.Length||args[diagnosticIndex+1].StartsWith("--"))throw new Exception("Use --diagnostics followed by a new JSON report filename.");
                    report=Path.GetFullPath(args[diagnosticIndex+1]);
                }
                return RunCheck(report,Array.IndexOf(args,"--setup-tools")>=0);
            }
            Directory.CreateDirectory(Logs);
            if(!headless&&(Array.IndexOf(args,"--setup")>=0||(!SessionAlive(Read(SessionFile))&&!File.Exists(Path.Combine(State,"config","setup.json"))))) {
                using(var setup=new SetupForm(true,true))if(setup.ShowDialog()!=DialogResult.OK)return 0;
            }
            bool first;
            using(var mutex=new Mutex(true,"Local\\InkStudio-"+Key,out first)) {
                if(!first) {
                    var session=Read(SessionFile);
                    for(int i=0;i<100&&!SessionAlive(session);i++){Thread.Sleep(100);session=Read(SessionFile);}
                    if(!SessionAlive(session)) {
                        if(OwnedProcess(session))return 0;
                        throw new Exception("Ink Studio is already starting. Check its logs if it does not become ready.");
                    }
                    if(!headless&&Array.IndexOf(args,"--no-browser")<0)Open("http://127.0.0.1:"+session["port"]+"/");
                    return 0;
                }
                try {
                    do {
                        StudioContext.Failed=false;StudioContext.Retry=false;
                        using(var context=new StudioContext(headless,headless||Array.IndexOf(args,"--no-browser")>=0))Application.Run(context);
                    } while(!headless&&StudioContext.Retry);
                }
                finally {mutex.ReleaseMutex();}
            }
            return StudioContext.Failed ? 2 : 0;
        } catch(Exception error) {
            Log(error.ToString());
            if(!Quiet)MessageBox.Show(error.Message+"\n\nLogs: "+Logs,"Ink Studio",MessageBoxButtons.OK,MessageBoxIcon.Error);
            return 2;
        }
    }

    internal static int RunCheck(string report,bool prepare) {
        string action=(prepare ? "--setup-tools" : "--check")+" --report "+Quote(report);
        using(var check=new Process{StartInfo=Backend(8801,Guid.NewGuid().ToString("N"),action)}) {
            check.OutputDataReceived+=(s,e)=>{if(e.Data!=null)Log(e.Data);};
            check.ErrorDataReceived+=(s,e)=>{if(e.Data!=null)Log(e.Data);};
            check.Start();
            using(var job=new Job(check)) {
                check.BeginOutputReadLine();check.BeginErrorReadLine();
                if(!check.WaitForExit(300000)){Log("Setup check timed out.");return 2;}
                check.WaitForExit();return check.ExitCode;
            }
        }
    }

    internal sealed class StudioContext : ApplicationContext {
        internal static bool Failed;
        internal static bool Retry;
        readonly System.Windows.Forms.Timer timer=new System.Windows.Forms.Timer();
        readonly EventWaitHandle stop=new EventWaitHandle(false,EventResetMode.ManualReset,"Local\\InkStudioStop-"+Key);
        readonly Process backend;
        readonly Job job;
        readonly Mutex projects;
        readonly string instance=Guid.NewGuid().ToString("N");
        readonly int port;
        readonly bool noBrowser;
        readonly NotifyIcon icon;
        readonly DateTime started=DateTime.UtcNow;
        bool ready,exiting;
        volatile bool serverAnnounced;
        internal StudioContext(bool headless,bool noBrowser) {
            this.noBrowser=noBrowser;
            var settings=Read(SettingsFile);int requested=Convert.ToInt32(Text(settings,"port","8801"));
            if(requested<1024||requested>65535)throw new Exception("Choose a port from 1024 to 65535 in Ink Studio Settings.");
            string projectFolder=Text(settings,"dataDirectory");
            if(String.IsNullOrWhiteSpace(projectFolder))projectFolder=Path.Combine(State,"data");
            bool available;
            projects=new Mutex(true,"Local\\InkStudioProjects-"+Hash(Path.GetFullPath(projectFolder).TrimEnd('\\').ToUpperInvariant()),out available);
            if(!available){projects.Dispose();throw new Exception("This project folder is already open in another Ink Studio session. Stop that session before starting this copy.");}
            port=FindPort(requested);
            if(port!=requested) {
                bool shared=false;
                try {
                    var active=Health(requested);
                    var activeRuntime=active["runtime"] as Dictionary<string,object>;
                    string desired=Text(settings,"dataDirectory");
                    if(String.IsNullOrWhiteSpace(desired))desired=Path.Combine(State,"data");
                    shared=activeRuntime!=null && String.Equals(Path.GetFullPath(Text(activeRuntime,"dataDirectory")).TrimEnd('\\'),Path.GetFullPath(desired).TrimEnd('\\'),StringComparison.OrdinalIgnoreCase);
                } catch {}
                if(shared)throw new Exception("This project folder is already open in another Ink Studio session. Stop that session before starting this copy.");
            }
            Log("Starting "+Root+" on port "+port);
            if(!headless) {
                var menu=new ContextMenuStrip();
                menu.Items.Add("Open Ink Studio",null,(s,e)=>{if(ready)Open(Url);});
                menu.Items.Add("Settings…",null,(s,e)=>{using(var form=new SettingsForm())form.ShowDialog();});
                menu.Items.Add("Setup and diagnostics…",null,(s,e)=>{using(var form=new SetupForm())form.ShowDialog();});
                menu.Items.Add("Open projects folder",null,(s,e)=>{
                    string path=Text(Read(SettingsFile),"dataDirectory",Path.Combine(State,"data"));
                    if(String.IsNullOrWhiteSpace(path))path=Path.Combine(State,"data");
                    Directory.CreateDirectory(path);Open(path);
                });
                menu.Items.Add("Open logs",null,(s,e)=>Open(Logs));
                menu.Items.Add("User guide",null,(s,e)=>Open(Path.Combine(Root,"docs","INSTALL.txt")));
                menu.Items.Add(new ToolStripSeparator());
                menu.Items.Add("About Ink Studio",null,(s,e)=>MessageBox.Show("Ink Studio "+Text(Read(Path.Combine(Root,"package.json")),"version")+" Preview\n\nA free companion to Inkscape and Ink/Stitch.\nGPL-3.0-or-later\n\n"+Root,"About Ink Studio"));
                menu.Items.Add("Exit Ink Studio",null,(s,e)=>ExitThread());
                icon=new NotifyIcon{Icon=new Icon(Path.Combine(Root,"resources","ink-studio.ico")),Text="Ink Studio · starting",ContextMenuStrip=menu,Visible=true};
                icon.DoubleClick+=(s,e)=>{if(ready)Open(Url);};
            }
            backend=new Process{StartInfo=Backend(port,instance),EnableRaisingEvents=true};
            backend.OutputDataReceived+=(s,e)=>{
                if(e.Data!=null){Log(e.Data);if(e.Data.StartsWith("Ink Studio editor: "))serverAnnounced=true;}
            };
            backend.ErrorDataReceived+=(s,e)=>{if(e.Data!=null)Log(e.Data);};
            try {
                backend.Start();job=new Job(backend);
                backend.BeginOutputReadLine();backend.BeginErrorReadLine();
                Write(SessionFile,new Dictionary<string,object>{{"root",Root},{"pid",backend.Id},{"port",port},{"instance",instance},{"startedTicks",backend.StartTime.ToUniversalTime().Ticks.ToString()},{"launcherPid",Process.GetCurrentProcess().Id}});
                timer.Interval=500;timer.Tick+=Tick;timer.Start();
            } catch {
                if(job!=null)job.Dispose();
                if(icon!=null)icon.Dispose();
                try{if(!backend.HasExited)backend.Kill();}catch{}
                stop.Dispose();timer.Dispose();backend.Dispose();throw;
            }
        }
        string Url {get{return "http://127.0.0.1:"+port+"/";}}
        static int FindPort(int preferred) {
            for(int i=0;i<20&&preferred+i<=65535;i++) {
                var listener=new TcpListener(IPAddress.Loopback,preferred+i);
                try{listener.Start();return preferred+i;}catch(SocketException){}finally{listener.Stop();}
            }
            throw new Exception("The preferred local ports are busy. Choose another port in Ink Studio Settings.");
        }
        void Tick(object sender,EventArgs args) {
            if(exiting)return;
            if(stop.WaitOne(0)){ExitThread();return;}
            if(backend.HasExited) {
                if(!ready) {
                    Failed=true;Log("Backend stopped before becoming ready (exit "+backend.ExitCode+").");
                    if(!Quiet) {
                        using(var form=new SetupForm(true,true))Retry=form.ShowDialog()==DialogResult.OK;
                    }
                }
                ExitThread();return;
            }
            if(!ready && serverAnnounced) {
                try {
                    var health=Health(port);
                    if(Text(health,"instance")==instance) {
                        ready=true;Log("Ready: "+Url);
                        if(icon!=null)icon.Text="Ink Studio";
                        if(!noBrowser)Open(Url);
                    }
                } catch(WebException) {}
            }
            if(!ready&&(DateTime.UtcNow-started).TotalMinutes>5) {
                    Failed=true;Log("Startup timed out.");
                    if(!Quiet)MessageBox.Show("Startup took too long. Check the Internet connection if Inkscape is being downloaded, then open the logs.\n\n"+Logs,"Ink Studio");
                    ExitThread();
            }
        }
        protected override void ExitThreadCore() {
            if(exiting)return;exiting=true;timer.Stop();
            if(icon!=null){icon.Visible=false;icon.Dispose();}
            if(job!=null)job.Dispose();
            try{if(!backend.HasExited)backend.Kill();backend.WaitForExit(5000);}catch{}
            try{if(Text(Read(SessionFile),"instance")==instance)File.Delete(SessionFile);}catch{}
            backend.Dispose();timer.Dispose();stop.Dispose();Log("Stopped.");base.ExitThreadCore();
            projects.ReleaseMutex();projects.Dispose();
        }
    }

    sealed class SetupForm : Form {
        readonly TextBox results=new TextBox{Multiline=true,ReadOnly=true,ScrollBars=ScrollBars.Vertical,Dock=DockStyle.Fill,BackColor=SystemColors.Window};
        readonly Button proceed=new Button{Text="Open editor",AutoSize=true,Enabled=false};
        readonly Button recheck=new Button{Text="Check again",AutoSize=true};
        readonly Button tools=new Button{Text="Prepare private Inkscape",AutoSize=true};
        readonly Button settings=new Button{Text="Choose tools / folders…",AutoSize=true};
        readonly Button export=new Button{Text="Save diagnostics…",AutoSize=true,Enabled=false};
        readonly string reportPath=Path.Combine(Logs,"setup-check.json");
        bool busy,hasChecked;
        internal bool ContinueEnabled {get{return proceed.Enabled;}}
        internal bool CheckCompleted {get{return hasChecked&&!busy;}}
        internal bool ExportEnabled {get{return export.Enabled;}}
        internal SetupForm(bool autoCheck=true,bool startsEditor=false) {
            Text="Ink Studio Setup and Diagnostics";StartPosition=FormStartPosition.CenterScreen;
            ClientSize=new Size(790,550);MinimumSize=new Size(730,540);Font=new Font("Segoe UI",10);AutoScaleMode=AutoScaleMode.Dpi;
            var layout=new TableLayoutPanel{Dock=DockStyle.Fill,Padding=new Padding(20),ColumnCount=1,RowCount=5};
            layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));layout.RowStyles.Add(new RowStyle(SizeType.Percent,100));
            layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            layout.Controls.Add(new Label{Text="Get Ink Studio ready\nCheck Inkscape, Ink/Stitch and folder access before opening the editor. Checks work offline and do not open engine windows.",AutoSize=true,MaximumSize=new Size(730,0),Margin=new Padding(0,0,0,16)},0,0);
            results.Text="Choose Check again to inspect this installation.\r\n\r\nInk/Stitch 3.3.0 is required. Inkscape must provide image tracing.\r\n\r\nPrepare private Inkscape uses a verified cached archive, or downloads it from inkscape.org (about 110 MB). Your installed tools stay in place.\r\n\r\nFor an offline computer, follow the user guide to copy the verified archive into the cache.";
            layout.Controls.Add(results,0,1);
            var actions=new FlowLayoutPanel{Dock=DockStyle.Fill,AutoSize=true,WrapContents=true,Margin=new Padding(0,12,0,0)};
            actions.Controls.AddRange(new Control[]{settings,recheck,tools});layout.Controls.Add(actions,0,2);
            var support=new FlowLayoutPanel{Dock=DockStyle.Fill,AutoSize=true,WrapContents=true,Margin=new Padding(0,8,0,8)};
            var guide=new Button{Text="User guide",AutoSize=true};guide.Click+=(s,e)=>Open(Path.Combine(Root,"docs","INSTALL.txt"));
            support.Controls.Add(export);support.Controls.Add(guide);support.Controls.Add(new Label{Text="Report excludes designs, personal paths and raw logs.",AutoSize=true,Margin=new Padding(8,7,0,0)});layout.Controls.Add(support,0,3);
            var buttons=new FlowLayoutPanel{Dock=DockStyle.Fill,FlowDirection=FlowDirection.RightToLeft,AutoSize=true};
            var cancel=new Button{Text="Close",AutoSize=true,DialogResult=DialogResult.Cancel};buttons.Controls.Add(cancel);buttons.Controls.Add(proceed);layout.Controls.Add(buttons,0,4);
            Controls.Add(layout);AcceptButton=proceed;CancelButton=cancel;
            proceed.Text=startsEditor ? "Open editor" : "Done";
            settings.Click+=(s,e)=>{using(var form=new SettingsForm())if(form.ShowDialog()==DialogResult.OK)Check(false);};
            recheck.Click+=(s,e)=>Check(false);tools.Click+=(s,e)=>Check(true);
            proceed.Click+=(s,e)=>{try{Write(Path.Combine(State,"config","setup.json"),new Dictionary<string,object>{{"schema",1}});DialogResult=DialogResult.OK;Close();}catch{results.Text="Setup is ready, but its confirmation could not be saved. Check access to the settings folder.";}};
            export.Click+=(s,e)=>{
                using(var picker=new SaveFileDialog{Filter="Diagnostics JSON|*.json",FileName="InkStudio-diagnostics.json",OverwritePrompt=false}) {
                    if(picker.ShowDialog()!=DialogResult.OK)return;
                    try{File.Copy(reportPath,picker.FileName,false);MessageBox.Show("Diagnostics saved. Review the report before sharing it.","Ink Studio");}
                    catch{MessageBox.Show("Choose a new, writable diagnostics filename. Existing files are retained.","Ink Studio");}
                }
            };
            FormClosing+=(s,e)=>{if(busy)e.Cancel=true;};
            if(autoCheck)Shown+=(s,e)=>Check(false);
        }
        void Check(bool prepare) {
            if(busy)return;busy=true;proceed.Enabled=false;export.Enabled=false;
            recheck.Enabled=settings.Enabled=tools.Enabled=false;
            results.Text=prepare ? "Preparing private Inkscape, then checking dependencies…\r\nThis may take a few minutes. Your installed tools are not replaced." : "Checking dependencies and folder access…";
            ThreadPool.QueueUserWorkItem(_=>{
                int code=2;string text="Setup checks could not complete. Check access to the settings and logs folders, then retry.";
                bool fresh=false;
                try {
                    DateTime started=DateTime.UtcNow;
                    code=RunCheck(reportPath,prepare);
                    if(!File.Exists(reportPath)||File.GetLastWriteTimeUtc(reportPath)<started)throw new Exception("No new report");
                    fresh=true;var report=Read(reportPath);var output=new StringBuilder();
                    object entries;
                    if(report.TryGetValue("checks",out entries))foreach(object entry in (System.Collections.IEnumerable)entries) {
                        var item=entry as Dictionary<string,object>;if(item==null)continue;
                        output.Append(Launcher.Text(item,"status").ToUpperInvariant()).Append("  ").AppendLine(Launcher.Text(item,"message"));
                        if(Launcher.Text(item,"action").Length>0)output.AppendLine(Launcher.Text(item,"action"));output.AppendLine();
                    }
                    if(output.Length>0)text=(code==0 ? "Ready to open the editor.\r\n\r\n" : "Complete the items below, then check again.\r\n\r\n")+output;
                } catch {}
                BeginInvoke((Action)(()=>{busy=false;hasChecked=true;results.Text=text;proceed.Enabled=code==0&&fresh;export.Enabled=fresh;recheck.Enabled=settings.Enabled=tools.Enabled=true;}));
            });
        }
    }

    sealed class SettingsForm : Form {
        readonly TextBox inkscape=new TextBox(),inkstitch=new TextBox(),data=new TextBox();
        readonly NumericUpDown port=new NumericUpDown{Minimum=1024,Maximum=65535,Value=8801};
        internal SettingsForm() {
            Text="Ink Studio Settings";StartPosition=FormStartPosition.CenterScreen;ClientSize=new Size(660,310);
            MinimumSize=new Size(600,350);AutoScaleMode=AutoScaleMode.Dpi;Font=new Font("Segoe UI",10);MaximizeBox=false;
            var layout=new TableLayoutPanel{Dock=DockStyle.Fill,Padding=new Padding(18),ColumnCount=3,RowCount=7};
            layout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,145));layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));layout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,85));
            var hint=new Label{Text="Leave paths blank for automatic discovery and the standard project folder. Restart Ink Studio after saving changes.",AutoSize=true,MaximumSize=new Size(610,0),Margin=new Padding(0,0,0,18)};
            layout.Controls.Add(hint,0,0);layout.SetColumnSpan(hint,3);
            AddPath(layout,1,"Inkscape",inkscape,false);AddPath(layout,2,"Ink/Stitch",inkstitch,false);AddPath(layout,3,"Projects folder",data,true);
            layout.Controls.Add(new Label{Text="Preferred port",AutoSize=true,Anchor=AnchorStyles.Left},0,4);layout.Controls.Add(port,1,4);
            var location=new Label{Text="Settings: "+SettingsFile,AutoSize=true,MaximumSize=new Size(610,0),Margin=new Padding(0,12,0,10)};
            layout.Controls.Add(location,0,5);layout.SetColumnSpan(location,3);
            var buttons=new FlowLayoutPanel{FlowDirection=FlowDirection.RightToLeft,Dock=DockStyle.Fill,AutoSize=true};
            var save=new Button{Text="Save",AutoSize=true};var cancel=new Button{Text="Cancel",AutoSize=true,DialogResult=DialogResult.Cancel};
            save.Click+=(s,e)=>{
                try {
                    foreach(var field in new[]{inkscape,inkstitch,data})if(field.Text.Trim().Length>0&&!Path.IsPathRooted(field.Text.Trim()))throw new Exception("Choose full paths for your tools and project folder.");
                    Write(SettingsFile,new Dictionary<string,object>{{"inkscape",inkscape.Text.Trim()},{"inkstitch",inkstitch.Text.Trim()},{"dataDirectory",data.Text.Trim()},{"port",(int)port.Value}});
                    DialogResult=DialogResult.OK;Close();
                } catch(Exception error){MessageBox.Show(error.Message,"Ink Studio Settings");}
            };
            save.TabIndex=0;cancel.TabIndex=1;
            buttons.Controls.Add(cancel);buttons.Controls.Add(save);layout.Controls.Add(buttons,0,6);layout.SetColumnSpan(buttons,3);
            AcceptButton=save;CancelButton=cancel;Controls.Add(layout);
            try {
                var value=Read(SettingsFile);inkscape.Text=Launcher.Text(value,"inkscape");inkstitch.Text=Launcher.Text(value,"inkstitch");data.Text=Launcher.Text(value,"dataDirectory");
                int requested;if(Int32.TryParse(Launcher.Text(value,"port","8801"),out requested)&&requested>=1024&&requested<=65535)port.Value=requested;
            } catch(Exception error){Log("Could not read settings: "+error.Message);}
        }
        void AddPath(TableLayoutPanel layout,int row,string label,TextBox field,bool folder) {
            layout.Controls.Add(new Label{Text=label,AutoSize=true,Anchor=AnchorStyles.Left},0,row);field.Dock=DockStyle.Fill;layout.Controls.Add(field,1,row);
            var browse=new Button{Text="Browse…",AutoSize=true};
            browse.Click+=(s,e)=>{
                if(folder){using(var picker=new FolderBrowserDialog()){picker.Description="Choose the Ink Studio projects folder";if(picker.ShowDialog()==DialogResult.OK)field.Text=picker.SelectedPath;}}
                else {using(var picker=new OpenFileDialog()){picker.Title="Choose "+label;picker.Filter=label=="Inkscape" ? "Inkscape console launcher|inkscape.com|Programs|*.exe;*.com" : "Ink/Stitch engine|inkstitch.exe|Programs|*.exe";if(picker.ShowDialog()==DialogResult.OK)field.Text=picker.FileName;}}
            };
            layout.Controls.Add(browse,2,row);
        }
    }

    // Own the complete backend tree. Windows closes the job even if the
    // launcher crashes, so neither engine workers nor hidden windows linger.
    sealed class Job : IDisposable {
        [StructLayout(LayoutKind.Sequential)] struct Basic {
            public long processTime,jobTime;public uint flags;public UIntPtr min,max;public uint active;public UIntPtr affinity;public uint priority,scheduling;
        }
        [StructLayout(LayoutKind.Sequential)] struct Io {public ulong a,b,c,d,e,f;}
        [StructLayout(LayoutKind.Sequential)] struct Limits {public Basic basic;public Io io;public UIntPtr process,job,peakProcess,peakJob;}
        [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr CreateJobObject(IntPtr security,string name);
        [DllImport("kernel32.dll",SetLastError=true)] static extern bool SetInformationJobObject(IntPtr job,int kind,ref Limits limits,uint size);
        [DllImport("kernel32.dll",SetLastError=true)] static extern bool AssignProcessToJobObject(IntPtr job,IntPtr process);
        [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
        IntPtr handle;
        internal Job(Process process) {
            handle=CreateJobObject(IntPtr.Zero,null);var limits=new Limits();limits.basic.flags=0x2000;
            if(handle==IntPtr.Zero||!SetInformationJobObject(handle,9,ref limits,(uint)Marshal.SizeOf(limits))||!AssignProcessToJobObject(handle,process.Handle)) {
                int error=Marshal.GetLastWin32Error();Dispose();throw new Exception("Could not own the background process tree: "+error);
            }
        }
        public void Dispose(){if(handle!=IntPtr.Zero){CloseHandle(handle);handle=IntPtr.Zero;}}
    }
}
