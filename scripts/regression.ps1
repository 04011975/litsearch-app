$ErrorActionPreference = "Stop"

function Fail($msg) {
    Write-Host ""
    Write-Host "❌ $msg" -ForegroundColor Red
    docker compose ps | Out-Host
    exit 1
}

Write-Host "`n== Build + start ==" -ForegroundColor Cyan
docker compose up -d --build | Out-Host

Start-Sleep -Seconds 5

Write-Host "`n== Basic health/redis env ==" -ForegroundColor Cyan
curl.exe -s http://localhost:8001/health | Out-Host
docker compose exec redis redis-cli PING | Out-Host
docker compose exec litsearch printenv REDIS_URL | Out-Host

Write-Host "`n== Europe PMC: page jump WITHOUT cursor ==" -ForegroundColor Cyan
curl.exe -s -o NUL -w "STATUS=%{http_code} TIME=%{time_total}`n" `
  "http://localhost:8001/search?source=europe_pmc&q=cancer&n=10&sort=relevance&page=5" `
  | Out-Host

Write-Host "`n== Redis cursor keys ==" -ForegroundColor Cyan
docker compose exec redis redis-cli KEYS "epmc:cursors:*" | Out-Host

Write-Host "`n== Europe PMC: RIS export page=5 WITHOUT cursor ==" -ForegroundColor Cyan

$exportUrl = "http://localhost:8001/export/ris?source=europe_pmc&q=cancer&scope=page&page=5&n=10&sort=relevance"

$raw = curl.exe -s $exportUrl

if (-not $raw) {
    Fail "RIS export returned empty response"
}

# Force string type (prevents array weirdness)
$ris = [string]::Join("`n", $raw)

if ([string]::IsNullOrWhiteSpace($ris)) {
    Fail "RIS export returned whitespace only"
}

$previewLength = [Math]::Min(300, $ris.Length)

Write-Host "`n---- RIS first $previewLength chars ----"
Write-Host $ris.Substring(0, $previewLength)

if ($ris -notmatch "TY  -" -or $ris -notmatch "ER  -") {
    Fail "RIS markers missing"
}

Write-Host "`n✅ RIS markers detected" -ForegroundColor Green

Write-Host "`n== Run sanity-check container ==" -ForegroundColor Cyan
docker compose run --rm sanity-check | Out-Host

Write-Host "`n== All regression checks completed successfully ==" -ForegroundColor Green
