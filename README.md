# Work in progress CDP crawler for Cisco networks

This is experimental at the moment, and mostly written as an exercise for fun.
Uses netmiko and some seed devices to scrape your network and output a CSV file
of all neighbors from each device.

Uses a BFS algorithm with netmiko, and calculates distances from seed devices.
Only visits each device once. Currently only works with CDP but could easily be
modified to do LLDP as well.

Only supports NXOS and IOS at the moment. Could be modified easily for other
devices.

## Usage Example: Scrape network starting with the core devices

* Note: The initial devices should have the same device ID in the cdp neighbors

```./ndcrawl.py -seed core1.domain.com,core2.domain.com --user yantisj -nei_file nd.csv -dev_file devices.csv --debug 1```


## Output Example
```
local_device_id,distance,remote_device_id,platform,local_int,remote_int,ipv4,os
core1.domain.com,0,mdcoobsw1.domain.com,WS-C4948,mgmt0,GigabitEthernet1/1,10.25.9.1,cisco_ios
core1.domain.com,0,servchas1.domain.com,WS-C6504-E,Ethernet7/25,TenGigabitEthernet3/1,10.24.70.51,cisco_ios
core1.domain.com,0,core2.domain.com,N7K-C7010,Ethernet7/26,Ethernet8/26,10.25.156.103,cisco_nxos
core1.domain.com,0,artmdf1.domain.com,N7K-C7010,Ethernet7/27,Ethernet2/26,10.25.80.103,cisco_nxos
```
