taskkill /F /IM "smolJPEG Image Compression.exe" /T 2>$null
taskkill /F /IM cjpegli.exe /T 2>$null
taskkill /F /IM cjpeg.exe /T 2>$null
taskkill /F /IM butteraugli.exe /T 2>$null
Remove-Item -Recurse -Force .\deployment -ErrorAction SilentlyContinue
pyside6-deploy