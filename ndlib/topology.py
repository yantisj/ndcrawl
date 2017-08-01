'Topology Routines'
import logging
import re
import csv
import threading
from time import sleep
from queue import Queue
from . import execute

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

    # Queue up seed devices
    for s in seeds:
        q.put(s)
        devices[s] = dict()
        devices[s]['remote_device_id'] = s
        devices[s]['ipv4'] = s
        devices[s]['os'] = 'cisco_nxos'
        devices[s]['platform'] = 'Unknown'
        distances[s] = 0

    # Outer Queue, starts inner queue and then adds all unvisited neighbors to queue when
    # inner queue is empty
    while not q.empty():

        # Launch threads on everything in queue to scrape
        while not q.empty():
            current = q.get()

            # Only scrape unvisited devices
            if current not in visited:
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
                    logger.warning('Thread running long time, ignoring: %s: %s', tid, str(some_thread))

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
                        q.put(rname)
                    elif n['os'] == 'cisco_ios':
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
        fieldnames = ['local_device_id', 'distance', 'remote_device_id', 'platform', 'local_int', \
                      'remote_int', 'ipv4', 'os']
        f = open(outf, 'w')
        dw = csv.DictWriter(f, fieldnames=fieldnames)
        dw.writeheader()
        for n in neighbors:
            dw.writerow(n)
        f.close()

    if dout:
        fieldnames = ['device_id', 'ipv4', 'platform', 'os']
        f = open(dout, 'w')
        dw = csv.DictWriter(f, fieldnames=fieldnames)
        dw.writeheader()
        for d in devices:
            dd = {'device_id': devices[d]['remote_device_id'], 'ipv4': devices[d]['ipv4'], \
                  'platform': devices[d]['platform'], 'os': devices[d]['os']}
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

    if device['os'] == 'cisco_nxos':
        nd = parse_cdp(cdp, device)
    elif device['os'] == 'cisco_ios':
        nd = parse_cdp(cdp, device)
    else:
        logger.warning('Unknown OS Type to Parse on %s: %s', dname, device['os'])

    for n in nd:
        logger.debug('Found Neighbor %s on %s', n, dname)
    ses.disconnect()

    return nd

def parse_cdp(cdp, device):
    'Return nd neighbors for NXOS CDP output'

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
                    logger.warning('Regex Ignore on %s neighbor from %s', \
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
