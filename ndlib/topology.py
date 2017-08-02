'Topology Routines'
import logging
import re
import csv
import sys
import threading
from time import sleep
from queue import Queue
from . import execute
#from progressbar import ProgressBar
from tqdm import tqdm

logger = logging.getLogger(__name__)

config = dict()

def crawl(seeds, username, password, outf=None, dout=None):
    'Crawl CDP/LLDP Neighbors to build a topology'

    # Queue for devices to scrape next
    q = Queue()

    # Queue for neighbor output from threads
    out_q = Queue()

    # Visited list for loop detection
    visited = list()

    # All Neighbor Entries
    neighbors = list()

    # Device entries for connection details (ipv4, os etc)
    devices = dict()

    # Thread tracking
    qtrack = dict()

    # Thread previous join attempts
    joined = list()

    # Distance tracking
    distances = dict()

    # Counter
    crawl_count = 0
    iteration_count = 0

    # Queue up seed devices
    for s in seeds:
        q.put(s)
        devices[s] = dict()
        devices[s]['remote_device_id'] = s
        devices[s]['ipv4'] = s
        devices[s]['os'] = config['main']['seed_os']
        devices[s]['platform'] = 'Unknown'
        distances[s] = 0

    # Outer Queue, starts inner queue and then adds all unvisited neighbors to queue when
    # inner queue is empty. Each iteration of outer queue visits all next level neighbors
    # at once inside inner queue via threads.
    while not q.empty():
        iteration_count += 1
        cqsize = q.qsize()
        if int(config['main']['log_level']) >= logging.WARNING and iteration_count > 1:
            pbar = tqdm(total=cqsize, unit='dev')
            pbar.set_description('Iteration %s' % str(iteration_count))

        # Launch threads on everything in queue to scrape
        while not q.empty():
            current = q.get()
            qsize = q.qsize()

            # Progress bar on warning level or above
            if int(config['main']['log_level']) >= logging.WARNING and iteration_count > 1:
                p_int = (cqsize - qsize)
                pbar.update(1)
                print('\r', end='')

            if crawl_count > int(config['main']['max_crawl']):
                logger.warning('Max Devices allowed already crawled')

            # Only scrape unvisited devices
            elif current not in visited:
                crawl_count += 1

                visited.append(current)
                while threading.activeCount() > int(config['main']['thread_count']):
                    qsize = q.qsize()
                    logger.debug('Waiting for free thread - Q Size: %s', str(qsize))
                    sleep(1)
                # Throttle connections
                sleep(0.1)
                logger.info('Processing %s', current)

                # Start thread to scrape devices
                nd_thread = threading.Thread(target=gather_nd, \
                    kwargs={"device": devices[current], "username": username, \
                            "password": password, "out_q": out_q, \
                            "qtrack": qtrack})
                nd_thread.start()

        # Join all threads from last iteration and warn if problems joining threads
        logger.info('Joining all active threads')
        main_thread = threading.currentThread()
        wait_timer = 15
        for some_thread in threading.enumerate():
            if some_thread != main_thread:
                tid = str(some_thread.ident)
                if tid in qtrack:
                    tid = qtrack[tid]
                if tid not in joined:
                    joined.append(tid)
                    logger.debug('Joining Thread: %s', tid)
                    some_thread.join(timeout=wait_timer)
                    wait_timer = 1
                else:
                    logger.info('Thread running long time, ignoring: %s: %s', tid, str(some_thread))

        # Process output queue of neighbor data and look for new neighbors to visit
        logger.info('Processing output queue')
        while not out_q.empty():
            nd = out_q.get()

            # Gather distance info
            for n in nd:
                if n['local_device_id'] not in distances:
                    distances[n['local_device_id']] = 100
                if n['remote_device_id'] in distances:
                    if distances[n['local_device_id']] > (distances[n['remote_device_id']] + 1):
                        distances[n['local_device_id']] = distances[n['remote_device_id']] + 1
                        logger.info('Found new distances on %s: %s', n['local_device_id'], \
                                    str(distances[n['remote_device_id']] + 1))

            # Save all neighbor data
            for n in nd:
                n['distance'] = distances[n['local_device_id']]
                neighbors.append(n)
                rname = n['remote_device_id']
                devices[rname] = n
                logger.info('Processing Out_q entry %s on %s', rname, n['local_device_id'])

                # New Neighbor that has not been scraped, only scrape IOS/NXOS for now
                if rname not in visited:
                    if n['os'] == 'cisco_nxos':
                        if rname not in q.queue:
                            q.put(rname)
                    elif n['os'] == 'cisco_ios':
                        if rname not in q.queue:
                            q.put(rname)
                    else:
                        visited.append(rname)
                else:
                    logger.debug('Already visited %s', rname)

    # Count Neighbors
    ncount = 0
    for n in neighbors:
        ncount += 1
    logger.info('Total neighbors: %s', str(ncount))

    # Output Neighbor CSV File
    if outf:
        fieldnames = ['local_device_id', 'remote_device_id', 'distance', 'local_int', \
                      'remote_int', 'ipv4', 'os', 'platform', 'description']
        f = open(outf, 'w')
        dw = csv.DictWriter(f, fieldnames=fieldnames)
        dw.writeheader()
        for n in neighbors:
            dw.writerow(n)
        f.close()

    if dout:
        fieldnames = ['device_id', 'ipv4', 'platform', 'os', 'distance']
        f = open(dout, 'w')
        dw = csv.DictWriter(f, fieldnames=fieldnames)
        dw.writeheader()
        for d in sorted(devices):
            dist = 100
            if devices[d]['remote_device_id'] in distances:
                dist = distances[devices[d]['remote_device_id']]
            dd = {'device_id': devices[d]['remote_device_id'], 'ipv4': devices[d]['ipv4'], \
                  'platform': devices[d]['platform'], 'os': devices[d]['os'], \
                  'distance': dist}
            dw.writerow(dd)
            #print(d, devices[d]['remote_device_id'], devices[d]['ipv4'], devices[d]['os'], devices[d]['platform'])


def gather_nd(**kwargs):
    'Gather neighbors from device'

    out_q = kwargs['out_q']
    device = kwargs['device']
    dname = device['remote_device_id']
    tid = str(threading.get_ident())
    kwargs["qtrack"][tid] = dname

    logger.info('Gathering Neighbors on %s: %s', dname, tid)

    nd = dict()

    # Try to connect to device id first
    try:
        nd = scrape_device(device, dname, kwargs['username'], kwargs['password'])

    except Exception as e:
        if device['ipv4'] == 'Unknown':
            logger.warning('Connection to %s failed and IPv4 is Unknown', dname)

        # Try IPv4 Address
        else:
            logger.info('Failed to connect to %s, trying %s', dname, device['ipv4'])
            try:
                nd = scrape_device(device, device['ipv4'], kwargs['username'], kwargs['password'])
            except Exception as e:
                logger.warning('Failed to scrape %s: %s', dname, str(e))
    if nd:
        out_q.put(nd)
        logger.info('Completed Scraping %s: %s', dname, tid)

def scrape_device(device, host, username, password):
    """ Scrape a device and return the results as list of neighbors """

    dname = device['remote_device_id']

    ses = execute.get_session(host, device['os'], username, password)

    cdp = execute.send_command(ses, 'show cdp neighbor detail', dname)

    lldp = execute.send_command(ses, 'show lldp neighbor detail', dname)
    lldp_sum = execute.send_command(ses, 'show lldp neighbor', dname)

    if device['os'] == 'cisco_nxos':
        nd_cdp = parse_cdp(cdp, device)
        nd_lldp = parse_lldp(lldp, lldp_sum, device)
    elif device['os'] == 'cisco_ios':
        nd_cdp = parse_cdp(cdp, device)
        nd_lldp = parse_lldp(lldp, lldp_sum, device)
    else:
        logger.warning('Unknown OS Type to Parse on %s: %s', dname, device['os'])

    for n in nd_cdp:
        logger.debug('Found Neighbor %s on %s', n, dname)
    ses.disconnect()

    nd = merge_nd(nd_cdp, nd_lldp)

    return nd

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
            current['description'] = desc.group(1)
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

