function Get-RecentLogons {
    $system = Get-WmiObject -Class Win32_ComputerSystem
    if ($system.PartOfDomain) {
        $computer = $system.Name + '.' + $system.Domain
    } else {
        $computer = $system.Name
    }
    # fetch logon events from last 30 days
    Get-WinEvent -LogName security -MaxEvents 16384 -FilterXPath 'Event[System[EventID=4624 and TimeCreated[timediff(@SystemTime) < 2592000000]]]' | %{
        @{
            'timestamp'=$_.TimeCreated.ToUniversalTime().ToString('yyyy-MM-ddThh:mm:ss.000000Z');
            'computerfqdn'=$computer;
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
    } | ConvertTo-Json
}
