Set shell = CreateObject("WScript.Shell")
scriptPath = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
shell.Run Chr(34) & scriptPath & "\start_windows.bat" & Chr(34), 0, False
