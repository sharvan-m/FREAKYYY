# Builds Freakyyy Desktop into dist\Freakyyy (Freakyyy.exe + models) and dist\Freakyyy-Desktop.zip.
# Usage:  powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = ".\.venv\Scripts\python.exe"

# freakyyy.ico and the SVG assets come from the brand kit (..\brand\make_brand.py).
& $py -m PyInstaller --noconfirm --clean --windowed --name Freakyyy --icon freakyyy.ico `
    --collect-all mediapipe --collect-all kokoro_onnx --collect-all espeakng_loader --collect-all phonemizer `
    --collect-all vosk --collect-all faster_whisper --collect-all ctranslate2 --collect-all onnxruntime `
    --collect-all uiautomation --collect-all screen_brightness_control `
    --add-data "freakyyy\ui\assets;ui\assets" `
    --hidden-import win32timezone --hidden-import keyring.backends.Windows `
    --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets `
    --exclude-module PySide6.Qt3DCore --exclude-module PySide6.QtQuick3D --exclude-module PySide6.QtMultimedia `
    --exclude-module tkinter --exclude-module matplotlib `
    launcher.py

# Models live next to the exe (not inside the bundle) so they load fast and can be updated.
$models = "dist\Freakyyy\models"
New-Item -ItemType Directory -Force $models | Out-Null
Copy-Item -Recurse -Force "models\vosk-model-small-en-us-0.15" $models
Copy-Item -Recurse -Force "models\whisper-base.en" $models
Copy-Item -Force "models\model_quantized.onnx", "models\voices-am_onyx.bin" $models
if ($env:FREAKYYY_INCLUDE_LITERT -eq "1") { Copy-Item -Force "models\kokoro_int8_fp16.litertlm" $models }

Copy-Item -Force "install.ps1", "uninstall.ps1" "dist\Freakyyy\"
Compress-Archive -Force -Path "dist\Freakyyy" -DestinationPath "dist\Freakyyy-Desktop.zip"
Write-Host "Built dist\Freakyyy\Freakyyy.exe and dist\Freakyyy-Desktop.zip"
