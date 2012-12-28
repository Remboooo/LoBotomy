#!/usr/bin/env python3
# make sure flake8 ignores this file: flake8: noqa

import signal
import logging
import lobotomy.server
import lobotomy.config


# create a server object
server = lobotomy.server.LoBotomyServer()

# define a shutdown handler
def shutdown(signal, frame):
	logging.info("caught SIGINT, requesting shutdown")
	server.shutdown()

# add a signal before serving
signal.signal(signal.SIGINT, shutdown)

# setup simple logging to print messages from server
logging.basicConfig(format = '[ %(levelname)8s ] %(message)s', level = logging.DEBUG)

# start spectator interface
from lobotomy.spectatorserver import SpectatorServer
spectatorserver = SpectatorServer(server)
# handle config parameter
lobotomy.config.parse_args()

# start the server
server.serve_forever()

# kill the spectatorserver
spectatorserver.stop()
