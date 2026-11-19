"""Create a Start Menu shortcut named 'Raze' so Windows lists it without .exe."""
import os
import sys

import win32com.client  # pywin32

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(HERE, "dist", "Raze.exe")
ICON = os.path.join(HERE, "assets", "raze.ico")
START_MENU = os.path.join(os.environ["APPDATA"],
                          r"Microsoft\Windows\Start Menu\Programs")
DESKTOP = os.path.join(os.environ["USERPROFILE"], "Desktop")

shell = win32com.client.Dispatch("WScript.Shell")

for folder in (START_MENU, DESKTOP):
    os.makedirs(folder, exist_ok=True)
    link_path = os.path.join(folder, "Raze.lnk")
    if os.path.exists(link_path):
        os.remove(link_path)
    link = shell.CreateShortCut(link_path)
    link.Targetpath = EXE
    link.WorkingDirectory = os.path.dirname(EXE)
    link.IconLocation = ICON
    link.Description = "Raze - type anything automatically"
    link.save()
    print("created", link_path)
