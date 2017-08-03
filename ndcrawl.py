#!/usr/bin/env python
import os.path
import sys
import argparse
import configparser
import logging
import getpass
from ndlib.log import init_logging
from ndlib import topology

CONFIG_FILE = 'ndcrawl.ini'

parser = argparse.ArgumentParser(description='Discover Network Topology via CDP/LLDP')
parser.add_argument('-seed', metavar="switch1[,switch2]", help="Seed devices to start crawl")
parser.add_argument('-nei_file', metavar="file", help="Output Neighbors to File", type=str)
parser.add_argument('-dev_file', metavar="file", help="Output Neighbors to File", type=str)
parser.add_argument('-ng_file', metavar="file", help="Output NetGrph Topology File", type=str)
parser.add_argument('--quiet', help='Quiet output, log to file only', action="store_true")
parser.add_argument("--seed_os", metavar='cisco_nxos', help="Netmiko OS type for seed devices",
                    type=str)
parser.add_argument("--seed_file", metavar='file', help="Seed devices from a file, one per line",
                    type=str)
parser.add_argument("--user", metavar='username', help="Username to execute as",
                    type=str)
parser.add_argument("--max_crawl", metavar='int', help="Max devices to crawl (default 10000)",
                    type=int)
parser.add_argument("--conf", metavar='file', help="Alternate Config File",
                    type=str)
parser.add_argument("--debug", help="Set debugging level", type=int)
parser.add_argument("-v", help="Verbose Output", action="store_true")

args = parser.parse_args()

log_level = logging.WARNING
logging.getLogger('paramiko').setLevel(logging.WARNING)

if args.v and not args.debug:
    args.debug = 1

if args.debug:
    if args.debug:
        log_level = logging.INFO
    if args.debug > 1:
        log_level = logging.DEBUG
    if args.debug > 1 and args.debug < 3:
        logging.getLogger('netmiko').setLevel(logging.INFO)
        logging.getLogger('paramiko').setLevel(logging.INFO)

logger = logging.getLogger('ndcrawl.py')

# Local config files to import
config = configparser.ConfigParser()

if os.path.exists(CONFIG_FILE):
    config.read(CONFIG_FILE)
else:
    logger.warning('Warning: Loading Sample Config File: Please create ndcrawl.ini from ndcrawl-sample.ini')
    config.read('ndcrawl-sample.ini')

config['main']['log_level'] = str(log_level)
topology.config = config

if args.quiet:
    config['main']['quiet'] = '1'
else:
    config['main']['quiet'] = ''

init_logging(log_level, config['main']['log_file'], args.quiet)

if args.max_crawl:
    config['main']['max_crawl'] = str(args.max_crawl)

if args.seed_os:
    config['main']['seed_os'] = args.seed_os

if not args.seed:
    if 'seeds' in config['main'] and config['main']['seeds']:
        args.seed = config['main']['seeds']

if args.seed or args.seed_file:

    if not args.user:
        if 'username' in config['main'] and config['main']['username']:
            args.user = config['main']['username']
        else:
            print('\nError: Must provide --user if not using config file\n')
            sys.exit(1)
    if 'password' in config['main'] and config['main']['password']:
        password = config['main']['password']
    else:
        password = getpass.getpass('Password for ' + args.user + ': ')

    # Check for output files from config
    if not args.nei_file:
        if 'nei_file' in config['main'] and config['main']['nei_file']:
            args.nei_file = config['main']['nei_file']
    if not args.dev_file:
        if 'dev_file' in config['main'] and config['main']['dev_file']:
            args.dev_file = config['main']['dev_file']

    if args.seed_file:
        seeds = list()
        f = open(args.seed_file, 'r')
        for l in f:
            l = l.strip()
            if l:
                seeds.append(l)
    else:
        seeds = args.seed.split(',')

    if not args.quiet:
        print('Beginning crawl on:', ', '.join(seeds))

    topology.crawl(seeds, args.user, password, outf=args.nei_file, dout=args.dev_file, ngout=args.ng_file)
else:
    print('\nError: Must provide -seed devices if not using config file\n')
    parser.print_help()
