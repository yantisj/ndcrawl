'Netmiko Routines'
import logging
import re
from time import sleep
from netmiko import ConnectHandler

logger = logging.getLogger(__name__)

def get_session(host, platform, username, password):
    """ Get an SSH session on device """

    net_connect = ConnectHandler(device_type=platform,
                                 ip=host,
                                 global_delay_factor=0.2,
                                 username=username,
                                 password=password,
                                 timeout=20)

    net_connect.enable()

    return net_connect

def send_command_timing(session, cmd, delay_factor=1, host=''):
    """ Send command and return results as list """

    logger.debug('Executing Command on %s: %s', host, cmd)
    results = session.send_command_timing(cmd, delay_factor=delay_factor)
    return results.split('\n')

def send_command(session, cmd, host=''):
    """ Send command and return results as list """

    logger.debug('Executing Command on %s: %s', host, cmd)
    results = session.send_command(cmd)
    return results.split('\n')
