# Демо на VPS: отдаём серверу локальную Ollama обратным SSH-туннелем.
#   powershell -ExecutionPolicy Bypass -File scripts/vps-tunnel.ps1
# Пока окно открыто, https://data-to-product.ozzy1986.com генерирует карточки моделью этого ноутбука.
# Тот же туннель обслуживает и ai-client-responder: оба сервиса ходят на 127.0.0.1:11434 сервера.
$vpsHost = if ($env:D2P_DEPLOY_HOST) { $env:D2P_DEPLOY_HOST } else { "root@162.35.161.95" }
Write-Host "Туннель к Ollama поднят (Ctrl+C — закрыть)"
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -R 11434:127.0.0.1:11434 $vpsHost
