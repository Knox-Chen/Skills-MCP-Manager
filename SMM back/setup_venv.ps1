# 使用 Python 3.12 创建虚拟环境并安装依赖（避免 3.14 下 PyTorch DLL 错误）
$py312 = "C:\Users\陈昊成\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\python.exe"
if (-not (Test-Path $py312)) {
    Write-Host "未找到 Python 3.12，请先安装或修改本脚本中的路径。"
    exit 1
}
& $py312 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Write-Host "`n完成。以后请先激活环境再运行 ingest："
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "  python ingest.py"
