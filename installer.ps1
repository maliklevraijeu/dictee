# Installe Dictee pour l'utilisateur courant, sans droits administrateur.
#   irm https://raw.githubusercontent.com/maliklevraijeu/dictee/v0.4.0/installer.ps1 | iex
# Ou, depuis un dossier telecharge :  powershell -ExecutionPolicy Bypass -File installer.ps1 [-Dossier D:\Dictee] [-SansDemarrage]
# (Fichier volontairement en ASCII : PowerShell 5.1 lit mal l'UTF-8 sans BOM. Les accents sont construits avec [char].)
param(
    [string]$Dossier = (Join-Path $env:LOCALAPPDATA 'Dictee'),
    [switch]$SansDemarrage,
    [string]$Source = 'https://github.com/maliklevraijeu/dictee/archive/refs/tags/v0.4.0.zip'
)
$ErrorActionPreference = 'Stop'
$e = [char]0xE9; $o = [char]0xF4; $a = [char]0xE2; $g = [char]0xE8
$Nom = "Dict${e}e"
# Messages en francais si Windows est en francais, en anglais sinon.
$EnFrancais = (Get-UICulture).TwoLetterISOLanguageName -eq 'fr'
function M([string]$texteFr, [string]$texteEn) { if ($EnFrancais) { $texteFr } else { $texteEn } }
$TestVersion = 'import sys; print(sys.version_info >= (3, 10)); print(sys.executable)'

function Tester-Python([string]$exe, [string[]]$avant) {
    # Le faux python.exe du Microsoft Store ouvre le Store au lieu de repondre : on teste la version.
    try {
        $v = & $exe @avant -c $TestVersion 2>$null
        if ($LASTEXITCODE -eq 0 -and $v -and $v[0] -eq 'True') { return $v[1] }
    } catch { }
    return $null
}

function Trouver-Python {
    $p = Tester-Python 'py' @('-3')
    if (-not $p) { $p = Tester-Python 'python' @() }
    if (-not $p) {
        $dossiers = Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python3*\python.exe') -ErrorAction SilentlyContinue |
            Sort-Object { [int]($_.Directory.Name -replace '\D', '') } -Descending
        foreach ($exe in $dossiers) {
            $p = Tester-Python $exe.FullName @()
            if ($p) { break }
        }
    }
    return $p
}

$py = Trouver-Python
if (-not $py) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw (M "Python 3.10 ou plus est introuvable, et winget n'existe pas sur ce Windows. Installe Python depuis python.org (coche 'Add python.exe to PATH'), puis relance cette ligne." "Python 3.10+ was not found and winget is missing on this Windows. Install Python from python.org (tick 'Add python.exe to PATH'), then run this line again.")
    }
    Write-Host (M "Python 3.10+ introuvable : installation de Python 3.12 pour ton compte (winget, sans droits admin)..." "Python 3.10+ not found: installing Python 3.12 for your account (winget, no admin rights)...")
    winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
    $py = Trouver-Python
    if (-not $py) { throw (M "Python n'a pas pu ${e}tre install${e}. Installe-le depuis python.org puis relance cette ligne." "Python could not be installed. Install it from python.org, then run this line again.") }
}

$venv = Join-Path $Dossier 'venv'
Write-Host (M "Installation de $Nom dans $Dossier ..." "Installing $Nom in $Dossier ...")
New-Item -ItemType Directory -Force $Dossier | Out-Null
# Une version deja lancee depuis ce dossier est arretee le temps de la mise a jour.
Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$venv*" } | Stop-Process -Force
if (-not (Test-Path (Join-Path $venv 'Scripts\python.exe'))) { & $py -m venv $venv }
$vpy = Join-Path $venv 'Scripts\python.exe'
$vpyw = Join-Path $venv 'Scripts\pythonw.exe'
# --no-cache-dir : rien ne reste dans le cache de pip apres l'installation.
& $vpy -m pip install --quiet --disable-pip-version-check --no-cache-dir --upgrade $Source
if ($LASTEXITCODE -ne 0) { throw (M "L'installation des paquets a ${e}chou${e}." "Package installation failed.") }

$menu = Join-Path ([Environment]::GetFolderPath('Programs')) "$Nom.lnk"
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($menu)
$s.TargetPath = $vpyw
$s.Arguments = '-m dictee'
$s.WorkingDirectory = $Dossier
$s.Description = "$Nom : dict${e}e vocale"
$s.Save()

if (Test-Path (Join-Path $env:APPDATA 'Wispr Flow\flow.sqlite')) {
    Write-Host (M "Wispr Flow trouv${e} : reprise de ton dictionnaire (lu sur ce PC, rien n'est envoy${e})." "Wispr Flow found: importing your dictionary (read on this PC, nothing is sent).")
    & $vpy -m dictee importer-wispr
}
# Lancee avec Windows, comme une dictee doit l'etre ; se coupe dans le menu de l'icone.
if (-not $SansDemarrage) { & $vpy -m dictee demarrage on | Out-Null }

Start-Process $vpyw -ArgumentList '-m', 'dictee' -WorkingDirectory $Dossier
Write-Host ""
Write-Host (M "$Nom est lanc${e}e. Maintiens Ctrl+Win, parle, rel${a}che." "$Nom is running. Hold Ctrl+Win, speak, release.")
Write-Host (M "Son ic${o}ne est pr${e}s de l'horloge (parfois cach${e}e derri${g}re la fl${g}che ^)." "Its icon is next to the clock (sometimes hidden behind the ^ arrow).")
