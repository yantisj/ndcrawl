# Work in progress CDP crawler for Cisco networks

This is experimental at the moment. Uses netmiko and some seed devices to scrape
your network and output a CSV file of all neighbors from each device.

Uses a BFS algorithm with netmiko, and calculates distances from seed devices.
Only visits each device once. Currently only works with CDP but could easily be
modified to do LLDP as well.

Only supports NXOS and IOS at the moment. Could be modified easily for other
devices.

## Usage Example: Scrape network starting with the core devices

* Note: The initial devices should have the same device ID in the cdp neighbors

```./ndcrawl.py -seed core1.domain.com,core2.domain.com --user yantisj -out nd.csv --debug 1```


## Output Example

