'Topology Routines'
import logging
import csv
import threading
from time import sleep
from queue import Queue
from . import execute
from . import parse
from . import output
#from progressbar import ProgressBar
from tqdm import tqdm

logger = logging.getLogger(__name__)

config = dict()

def crawl(seeds, username, password, outf=None, dout=None, ngout=None):
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
        devices[s]['logged_in'] = True
        distances[s] = 0

    # Outer Queue, starts inner queue and then adds all unvisited neighbors to queue when
    # inner queue is empty. Each iteration of outer queue visits all next level neighbors
    # at once inside inner queue via threads.
    while not q.empty():
        iteration_count += 1
        cqsize = q.qsize()
        if not config['main']['quiet']:
            if int(config['main']['log_level']) >= logging.WARNING and iteration_count > 1:
                pbar = tqdm(total=cqsize, unit='dev')
                pbar.set_description('Iteration %s' % str(iteration_count))

        # Launch threads on everything in queue to scrape
        while not q.empty():
            current = q.get()
            qsize = q.qsize()

            # Progress bar on warning level or above
            if not config['main']['quiet']:
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

                # Save device to devices
                if rname not in devices:
                    devices[rname] = n
                # Update unknown devices, restore logged_in variable
                elif devices[rname]['platform'] == 'Unknown':
                    logged_in = False
                    if 'logged_in' in devices[rname]:
                        logged_in = devices[rname]['logged_in']
                    devices[rname] = n
                    devices[rname]['logged_in'] = logged_in

                # Save logged_in as False initially, update on another pass
                if 'logged_in' not in devices[n['local_device_id']]:
                    devices[n['local_device_id']]['logged_in'] = False

                # Local device always was logged in to
                devices[n['local_device_id']]['logged_in'] = True
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


    output.output_files(outf, ngout, dout, neighbors, devices, distances)


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
        nd_cdp = parse.parse_cdp(cdp, device)
        nd_lldp = parse.parse_lldp(lldp, lldp_sum, device)
    elif device['os'] == 'cisco_ios':
        nd_cdp = parse.parse_cdp(cdp, device)
        nd_lldp = parse.parse_lldp(lldp, lldp_sum, device)
    else:
        logger.warning('Unknown OS Type to Parse on %s: %s', dname, device['os'])

    for n in nd_cdp:
        logger.debug('Found Neighbor %s on %s', n, dname)
    ses.disconnect()

    nd = parse.merge_nd(nd_cdp, nd_lldp)

    return nd

