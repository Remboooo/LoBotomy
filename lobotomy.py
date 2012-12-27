#!/usr/bin/env python3

import signal

from lobotomy.server import LoBotomyServer

# create a server object
server = LoBotomyServer()

# define a shutdown handler
def shutdown(signal, frame):
	logging.info("caught SIGINT, requesting shutdown")
	server.shutdown()

# add a signal before serving
signal.signal(signal.SIGINT, shutdown)

# setup simple logging to print messages from server
import logging
logging.basicConfig(format = '[ %(levelname)8s ] %(message)s', level = logging.DEBUG)

# start webinterface
from lobotomy.webserver import WebServer
webserver = WebServer(server)

# start the server
server.serve_forever()

# kill the webserver
webserver.stop()
