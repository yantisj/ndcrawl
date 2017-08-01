#!/usr/bin/env python
import os
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
parser.add_argument('-out_file', metavar="file", help="Output Neighbors to File", type=str)
parser.add_argument("--user", metavar='username', help="Username to execute as",
                    type=str)
parser.add_argument("--conf", metavar='file', help="Alternate Config File",
                    type=str)
parser.add_argument("--debug", help="Set debugging level", type=int)
parser.add_argument("-v", help="Verbose Output", action="store_true")

args = parser.parse_args()

log_level = logging.WARNING
logging.getLogger('paramiko').setLevel(logging.WARNING)
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
config.read(CONFIG_FILE)
topology.config = config

init_logging(log_level, config['main']['log_file'])

if args.seed:
    outf = None
    if args.out_file:
        outf = args.out_file
    if not args.user:
        logger.warning('Must provide a username')
        sys.exit(1)
    password = getpass.getpass('Password for ' + args.user + ': ')

    seeds = args.seed.split(',')

    topology.crawl(seeds, args.user, password, outf)
