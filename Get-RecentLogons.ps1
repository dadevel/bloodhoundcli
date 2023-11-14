function Get-RecentLogons {
    $system = Get-WmiObject -Class Win32_ComputerSystem
    if ($system.PartOfDomain) {
        $computer = $system.Name + '.' + $system.Domain
    } else {
        $computer = $system.Name
    }
    Get-WinEvent -LogName security -MaxEvents 256 -FilterXPath 'Event[System[EventID=4624]]' | %{
        @{
            'timestamp'=$_.TimeCreated.ToUniversalTime().ToString('yyyy-MM-ddThh:mm:ss.000000Z');
            'computerfqdn'=$computer;
            'userdomain'=$_.Properties[6].Value;
            'username'=$_.Properties[5].Value;
            'usersid'=$_.Properties[4].Value.Value;
            'logontype'=$_.Properties[8].Value;
            'authenticationpackage'=$_.Properties[10].Value;
        }
    } | ConvertTo-Json
}
