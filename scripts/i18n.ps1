$ErrorActionPreference = "Stop"

Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location ..

Write-Host "== i18n: extract -> update/init -> compile ==" -ForegroundColor Cyan

# 1) Extract to messages.pot
pybabel extract -F babel.cfg -o messages.pot .

# 2) Update existing catalogs or init English if missing
if (Test-Path "translations/en/LC_MESSAGES/messages.po") {
  pybabel update -i messages.pot -d translations
} else {
  pybabel init -i messages.pot -d translations -l en
}

# 3) Compile (.mo)
pybabel compile -d translations

# Astuce dev: Flask reloader ne surveille pas les fichiers .mo, donc on "touche" app.py
# pour déclencher un reload automatique après compilation des traductions.
try {
  if (Test-Path "app.py") {
    (Get-Item "app.py").LastWriteTime = Get-Date
    Write-Host "Touched app.py to trigger Flask auto-reload." -ForegroundColor DarkGray
  }
} catch {
  # non bloquant
}

Write-Host "Done. Edit translations/en/LC_MESSAGES/messages.po then re-run this script." -ForegroundColor Green


