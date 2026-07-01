# sync_diario.ps1 — Atualiza dados do HubSpot automaticamente (D-1)
# Agendado para rodar todo dia as 06:00

$logFile = "C:\Users\kelly\OneDrive\Documentos\Claude\Gestão de incidentes\sync_diario.log"
$syncDir  = "C:\Users\kelly\OneDrive\Documentos\Claude\Gestão de incidentes"
$node     = (Get-Command node -ErrorAction SilentlyContinue).Source

function Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts  $msg" | Tee-Object -FilePath $logFile -Append
}

Log "=== Iniciando sync diario HubSpot ==="

if (-not $node) {
    Log "ERRO: Node.js nao encontrado no PATH."
    exit 1
}

# Executa o sync
$proc = Start-Process -FilePath $node `
    -ArgumentList "hubspot-only-sync.js" `
    -WorkingDirectory $syncDir `
    -Wait -PassThru -NoNewWindow `
    -RedirectStandardOutput "$syncDir\sync_output.txt" `
    -RedirectStandardError  "$syncDir\sync_error.txt"

$saida = Get-Content "$syncDir\sync_output.txt" -Raw -ErrorAction SilentlyContinue
$erro  = Get-Content "$syncDir\sync_error.txt"  -Raw -ErrorAction SilentlyContinue

if ($saida) { Log $saida.Trim() }
if ($erro -and $erro.Trim()) { Log "STDERR: $($erro.Trim())" }

if ($proc.ExitCode -eq 0) {
    Log "Sync concluido com sucesso. Exit code: 0"
} else {
    Log "ERRO no sync. Exit code: $($proc.ExitCode)"
}

Log "=== Fim do sync ==="
