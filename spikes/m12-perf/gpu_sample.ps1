param([int]$Seconds=60,[string]$Out)
$rows=@()
$end=(Get-Date).AddSeconds($Seconds)
while((Get-Date) -lt $end){
  $c=Get-Counter -Counter '\GPU Engine(*engtype_3D)\Utilization Percentage','\GPU Engine(*engtype_Compute*)\Utilization Percentage','\GPU Adapter Memory(*)\Dedicated Usage','\GPU Process Memory(*)\Dedicated Usage' -ErrorAction SilentlyContinue
  $s=$c.CounterSamples
  $ids=(Get-Process vv-studio,msedgewebview2,vv-domain-* -EA SilentlyContinue).Id
  $mine={ param($p) foreach($i in $ids){ if($p -match "pid_${i}_"){ return $true } }; $false }
  $rows+= [pscustomobject]@{
    t=(Get-Date).ToString('HH:mm:ss.f')
    gpu3d_total=[math]::Round(($s|?{$_.Path -match 'engtype_3d'}|Measure CookedValue -Sum).Sum,2)
    gpu_compute_total=[math]::Round(($s|?{$_.Path -match 'engtype_compute'}|Measure CookedValue -Sum).Sum,2)
    gpu3d_studio=[math]::Round(($s|?{$_.Path -match 'engtype_3d' -and (& $mine $_.Path)}|Measure CookedValue -Sum).Sum,2)
    vram_adapter_mb=[int](($s|?{$_.Path -match 'gpu adapter memory'}|Measure CookedValue -Max).Maximum/1MB)
    vram_studio_mb=[int](($s|?{$_.Path -match 'gpu process memory' -and (& $mine $_.Path)}|Measure CookedValue -Sum).Sum/1MB)
  }
}
$rows | Export-Csv -NoTypeInformation $Out
