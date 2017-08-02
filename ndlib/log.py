'Logging Initialization'
import logging
from logging.handlers import DatagramHandler

logger = logging.getLogger(__name__)

def init_logging(log_level, log_file, quiet):
    'Initialize Logging Globally'

    # Specify our log format for handlers
    log_format = logging.Formatter('%(asctime)s %(name)s:%(levelname)s: %(message)s')

    # Get the root_logger to attach log handlers to
    root_logger = logging.getLogger()

    # Set root logger to debug level always
    # Control log levels at log handler level
    root_logger.setLevel(logging.DEBUG)

    if not quiet:
        # Console Handler (always use log_level)
        ch = logging.StreamHandler()
        ch.setLevel(log_level)
        ch.setFormatter(log_format)
        root_logger.addHandler(ch)

    # Logfile Handler
    fh = logging.FileHandler(log_file)

    # Always log at INFO or below
    if log_level < logging.INFO:
        fh.setLevel(log_level)
    else:
        fh.setLevel(logging.INFO)
    
    # Attach logfile handler
    fh.setFormatter(log_format)
    root_logger.addHandler(fh)

    # # Attach Datagram Handler
    # dh = DatagramHandler('232.8.8.8', port=1900)
    # dh.setFormatter(log_format)
    # dh.setLevel(log_level)
    # root_logger.addHandler(dh)
