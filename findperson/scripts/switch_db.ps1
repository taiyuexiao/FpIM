# 数据库双轨切换 / 回滚脚本(feature/real-data)
# 用法: powershell -File scripts\switch_db.ps1 [-Target newdb|old]
#   newdb = 真实数据库 shouwenzeren_newdb(208人/32部门/310文)
#   old   = 合成数据库 shouwenzeren_agent(回滚用)
param([ValidateSet("newdb", "old")][string]$Target = "newdb")

$root = "C:\python\pycharm\shouwenzeren"
$dbMap = @{ newdb = "shouwenzeren_newdb"; old = "shouwenzeren_agent" }
$db = $dbMap[$Target]
Write-Output "== 切换目标: $db =="

# 1. 改两个 .env(幂等替换当前库名)
$agentEnv = "$root\agent-service\.env"
(Get-Content $agentEnv) -replace 'PGDATABASE=\w+', "PGDATABASE=$db" | Set-Content $agentEnv -Encoding utf8
$backendEnv = "$root\_repo_push\backend\.env"
(Get-Content $backendEnv) -replace '5432/\w+', "5432/$db" | Set-Content $backendEnv -Encoding utf8
Write-Output ".env 已切换"

# 2. 重启服务(start_all.ps1 自带 FASTEMBED_CACHE_PATH)
$conns = Get-NetTCPConnection -LocalPort 8001, 8100 -State Listen -ErrorAction SilentlyContinue
$conns | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep 2
powershell -File "$root\start_all.ps1" | Select-Object -Last 3
Write-Output "== 切换完成,请验证登录与问答 =="
