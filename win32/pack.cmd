@echo off

cls

if x%1 == x (
    echo %0 [hdns, dnsprobe]
    exit /b
)

pushd ..

rmdir build /s /q 2>nul
rmdir dist /s /q 2>nul

if x%1 == xhdns (
    pyinstaller --icon App-browser.ico --clean --noupx --noconfirm --console --paths homedns --onefile hdns.py
)

if x%1 == xdnsprobe (
    pyinstaller --icon App-browser.ico --clean --noupx --noconfirm --console --paths homedns --onefile dnsprobe.py
)

del *.spec /q
popd
