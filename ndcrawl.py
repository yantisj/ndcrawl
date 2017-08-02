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
parser.add_argument("--seed_os", metavar='cisco_nxos', help="Netmiko OS type for seed devices",
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
    logger.warning('Loading Sample Config File: Please create ndcrawl.ini from ndcrawl-sample.ini')
    config.read('ndcrawl-sample.ini')

config['main']['log_level'] = str(log_level)
topology.config = config

init_logging(log_level, config['main']['log_file'])

if args.max_crawl:
    config['main']['max_crawl'] = str(args.max_crawl)

if args.seed_os:
    config['main']['seed_os'] = args.seed_os

if args.seed:

    if not args.user:
        logger.warning('Must provide a username')
        sys.exit(1)
    password = getpass.getpass('Password for ' + args.user + ': ')

    seeds = args.seed.split(',')

    topology.crawl(seeds, args.user, password, outf=args.nei_file, dout=args.dev_file)
else:
    parser.print_help()