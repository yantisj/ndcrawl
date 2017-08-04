'Parser Routines'
import re
import logging

logger = logging.getLogger(__name__)

config = dict()

def merge_nd(nd_cdp, nd_lldp):
    """ Merge CDP and LLDP data into one structure """

    neis = dict()
    nd = list()

    for n in nd_lldp:
        neis[(n['local_device_id'], n['remote_device_id'], n['local_int'], n['remote_int'])] = n

    for n in nd_cdp:

        # Always prefer CDP, but grab description from LLDP if available
        if (n['local_device_id'], n['remote_device_id'], n['local_int'], n['remote_int']) in n:
            if 'description' in neis[(n['local_device_id'], n['remote_device_id'], n['local_int'], n['remote_int'])]:
                n['description'] = neis[(n['local_device_id'], n['remote_device_id'], n['local_int'], n['remote_int'])]['description']
        neis[(n['local_device_id'], n['remote_device_id'], n['local_int'], n['remote_int'])] = n


    for n in neis:
        nd.append(neis[n])

    return nd

def parse_cdp(cdp, device):
    'Return nd neighbors for IOS/NXOS CDP output'

    current = dict()
    dname = device['remote_device_id']
    nd = list()

    for l in cdp:
        l = l.rstrip()
        devid = re.search(r'^Device\sID\:\s*([A-Za-z0-9\.\-\_]+)', l)
        platform = re.search(r'^Platform\:\s([A-Za-z0-9\.\-\_]+)\s*([A-Za-z0-9\.\-\_]*)', l)
        ints = re.search(r'^Interface\:\s([A-Za-z0-9\.\-\_\/]+).*\:\s([A-Za-z0-9\.\-\_\/]+)$', l)
        ipv4 = re.search(r'^\s+IPv4\sAddress\:\s(\d+\.\d+\.\d+\.\d+)', l)
        ip = re.search(r'^\s+IP\saddress\:\s(\d+\.\d+\.\d+\.\d+)', l)
        nxos = re.search(r'Cisco Nexus', l)
        ios = re.search(r'Cisco IOS', l)
        if devid:
            if current:
                if not re.search(config['main']['ignore_regex'], current['remote_device_id']):
                    nd.append(current.copy())
                else:
                    logger.info('Regex Ignore on %s neighbor from %s', \
                                    current['remote_device_id'], current['local_device_id'])
            current = dict()
            rname = devid.group(1)
            current['local_device_id'] = dname
            current['remote_device_id'] = rname
            current['platform'] = 'Unknown'
            current['local_int'] = 'Unknown'
            current['remote_int'] = 'Unknown'
            current['ipv4'] = 'Unknown'
            current['os'] = 'Unknown'
            current['description'] = ''
        if ints:
            #print(l, ints.group(1), ints.group(2))
            current['local_int'] = ints.group(1)
            current['remote_int'] = ints.group(2)
        if ipv4:
            current['ipv4'] = ipv4.group(1)
        if ip:
            current['ipv4'] = ip.group(1)
        if platform:
            if platform.group(1) == 'cisco':
                current['platform'] = platform.group(2)
            else:
                current['platform'] = platform.group(1)
        if nxos:
            current['os'] = 'cisco_nxos'
        if ios:
            current['os'] = 'cisco_ios'

    if current:
        if not re.search(config['main']['ignore_regex'], current['remote_device_id']):
            nd.append(current.copy())
        else:
            logger.warning('Regex Ignore on %s neighbor from %s', \
                            current['remote_device_id'], current['local_device_id'])
    return nd


def parse_lldp(lldp_det, lldp_sum, device):
    'Return nd neighbors for IOS/NXOS LLDP output'

    current = dict()
    dname = device['remote_device_id']
    nd = list()
    dmap = dict()

    # Get local ports from summary, store in dmap
    for l in lldp_sum:
        l = l[20:]
        ln = l.split()
        if len(ln) > 3 and re.search(r'\w+\d+\/\d+', ln[0]):
            dmap[ln[3]] = ln[0]
        elif len(ln) == 3 and re.search(r'\w+\d+\/\d+', ln[0]):
            dmap[ln[2]] = ln[0]

    for l in lldp_det:
        l = l.rstrip()
        devid = re.search(r'^Chassis\sid\:\s*([A-Za-z0-9\.\-\_]+)', l)
        sysname = re.search(r'^System\sName\:\s*([A-Za-z0-9\.\-\_]+)', l)
        platform = re.search(r'^Platform\:\s([A-Za-z0-9\.\-\_]+)\s*([A-Za-z0-9\.\-\_]*)', l)
        l_int = re.search(r'^Local\sPort\sid\:\s([A-Za-z0-9\.\-\_\/]+)$', l)
        r_int = re.search(r'^Port\sid\:\s([A-Za-z0-9\.\-\_\/]+)$', l)
        ipv4 = re.search(r'^\s+IP\:\s(\d+\.\d+\.\d+\.\d+)', l)
        ip = re.search(r'^Management\sAddress\:\s(\d+\.\d+\.\d+\.\d+)', l)
        desc = re.search(r'Port\sDescription\:\s(.*)', l)
        nxos = re.search(r'Cisco Nexus', l)
        ios = re.search(r'Cisco IOS', l)
        if devid:
            if current:
                if not re.search(config['main']['ignore_regex'], current['remote_device_id']):
                    nd.append(current.copy())
                else:
                    logger.info('Regex Ignore on %s neighbor from %s', \
                                    current['remote_device_id'], current['local_device_id'])
            current = dict()
            rname = devid.group(1)
            current['local_device_id'] = dname
            current['remote_device_id'] = rname
            current['platform'] = 'Unknown'
            current['local_int'] = 'Unknown'
            current['remote_int'] = 'Unknown'
            current['ipv4'] = 'Unknown'
            current['os'] = 'Unknown'
            current['description'] = ''


        if sysname:
            if not re.search('advertised', sysname.group(1)):
                current['remote_device_id'] = sysname.group(1)
        if r_int:
            current['remote_int'] = r_int.group(1)

            # Try to map interface via summary if Unknown (IOS)
            if device['os'] == 'cisco_ios':
                if current['remote_int'] in dmap:
                    logger.debug('Mapping %s local interface %s to chassis id %s', \
                                dname, dmap[current['remote_int']], current['remote_int'])
                    current['local_int'] = dmap[current['remote_int']]
                elif current['remote_device_id'] in dmap:
                    current['local_int'] = dmap[current['remote_device_id']]
                else:
                    logger.info('No LLDP mapping for %s on %s', current['remote_int'], current['local_device_id'])
        if l_int:
            current['local_int'] = l_int.group(1)
        if ipv4:
            current['ipv4'] = ipv4.group(1)
        if ip:
            current['ipv4'] = ip.group(1)
        if platform:
            if platform.group(1) == 'cisco':
                current['platform'] = platform.group(2)
            else:
                current['platform'] = platform.group(1)
        if desc:
            current['description'] = desc.group(1).strip()
        if nxos:
            current['os'] = 'cisco_nxos'
        if ios:
            current['os'] = 'cisco_ios'

    if current:
        if not re.search(config['main']['ignore_regex'], current['remote_device_id']):
            nd.append(current.copy())
        else:
            logger.warning('Regex Ignore on %s neighbor from %s', \
                            current['remote_device_id'], current['local_device_id'])
    return nd
