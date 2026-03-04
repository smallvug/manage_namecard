Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")

dir     = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = dir & "\.venv\Scripts\pythonw.exe"
script  = dir & "\manage_gui.py"

sh.Run """" & pythonw & """ """ & script & """", 0, False
