$base = "http://localhost:8000/api/v1/session"
$email = "qa.user.$(Get-Random)@example.com"
$pass = "S3curePass!42"

Write-Output "== 1. Signup =="
try {
  $r = Invoke-RestMethod -Uri "$base/signup" -Method Post -ContentType "application/json" -Body (@{email=$email;password=$pass} | ConvertTo-Json)
  Write-Output "OK role=$($r.role) email=$($r.email) tokenLen=$($r.token.Length)"
} catch { Write-Output "FAILED: $($_.Exception.Message)"; exit 1 }

Write-Output "== 2. Duplicate signup rejected =="
try {
  Invoke-RestMethod -Uri "$base/signup" -Method Post -ContentType "application/json" -Body (@{email=$email;password=$pass} | ConvertTo-Json) | Out-Null
  Write-Output "FAILED: duplicate accepted"
} catch { Write-Output "OK rejected: $($_.ErrorDetails.Message)" }

Write-Output "== 3. Weak password rejected =="
try {
  Invoke-RestMethod -Uri "$base/signup" -Method Post -ContentType "application/json" -Body (@{email="x1@example.com";password="short"} | ConvertTo-Json) | Out-Null
  Write-Output "FAILED: weak password accepted"
} catch { Write-Output "OK rejected: $($_.ErrorDetails.Message)" }

Write-Output "== 4. Login with correct password =="
try {
  $r = Invoke-RestMethod -Uri "$base/login" -Method Post -ContentType "application/json" -Body (@{email=$email;password=$pass} | ConvertTo-Json)
  Write-Output "OK role=$($r.role) email=$($r.email)"
} catch { Write-Output "FAILED: $($_.Exception.Message)" }

Write-Output "== 5. Login with wrong password rejected =="
try {
  Invoke-RestMethod -Uri "$base/login" -Method Post -ContentType "application/json" -Body (@{email=$email;password="WrongPass999"} | ConvertTo-Json) | Out-Null
  Write-Output "FAILED: wrong password accepted"
} catch { Write-Output "OK rejected: $($_.ErrorDetails.Message)" }

Write-Output "== 6. Case-insensitive email login =="
$upper = $email.ToUpper()
try {
  $r = Invoke-RestMethod -Uri "$base/login" -Method Post -ContentType "application/json" -Body (@{email=$upper;password=$pass} | ConvertTo-Json)
  Write-Output "OK role=$($r.role)"
} catch { Write-Output "FAILED: $($_.Exception.Message)" }
