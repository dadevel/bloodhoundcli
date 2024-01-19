function Get-RecentLogons {
    # usage: Get-RecentLogons | ConvertTo-Json | Out-File -FilePath \\tsclient\share\logons-$env:computername.json -Encoding utf8
     param (
        [Int] $Days = 30
    )
    $system = Get-WmiObject -Class Win32_ComputerSystem
    if ($system.PartOfDomain) {
        $computer = $system.Name + '.' + $system.Domain
    } else {
        $computer = $system.Name
    }
    $delta = 1000 * 60 * 60 * 24 * $Days
    Get-WinEvent -LogName security -FilterXPath "Event[System[EventID=4624 and TimeCreated[timediff(@SystemTime) < ${delta}]]]" | %{
        @{
            'timestamp'=$_.TimeCreated.ToUniversalTime().ToString('yyyy-MM-ddThh:mm:ss.000000Z');
            'computerfqdn'=$computer;
            'sourceip'=$_.Properties[18].Value;
            'userdomain'=$_.Properties[6].Value;
            'username'=$_.Properties[5].Value;
            'usersid'=$_.Properties[4].Value.Value;
            'logontype'=$_.Properties[8].Value;
            'authenticationpackage'=$_.Properties[10].Value;
            'elevated'=$_.Properties[26].Value -eq '%%1842';
        }
    } | ?{
        # keep only real users
        $_['usersid'] -match '^S-1-5-21-'
    }
}
