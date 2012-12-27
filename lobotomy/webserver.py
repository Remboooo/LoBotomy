from lobotomy.event import Listener
from lobotomy import config
import json
from queue import Queue, Empty
from threading import Thread
import cherrypy
from ws4py.server.cherrypyserver import WebSocketPlugin, WebSocketTool
from ws4py.websocket import WebSocket
from ws4py.messaging import TextMessage
import socket
import os
import random

class WebServer():
	def __init__(self, lobotomyserver, port = config.host.http_port, host = config.host.http_host):
		self.lobotomy = lobotomyserver
		self.port = port
		self.host = host
		WebServer.instance = self
		t = Thread(name='webserver', target=self.start)
		t.daemon = True
		t.start()
		
	def start(self):
		staticroot = os.path.abspath(os.path.join(os.path.dirname(__file__), 'static'))
		cherrypy.config.update({'server.socket_host': self.host,
								'server.socket_port': self.port,
								'tools.staticdir.root': staticroot,
								'tools.staticfile.root': staticroot,
								'log.screen': False})
		WebSocketPlugin(cherrypy.engine).subscribe()
		cherrypy.tools.websocket = WebSocketTool()
		cherrypy.quickstart(WebRoot(self.host, self.port), '', config={
			'/ws': {
					'tools.websocket.on': True,
					'tools.websocket.handler_cls': SpectatorWebSocketHandler
				},
			'/js': {
					'tools.staticdir.on': True,
					'tools.staticdir.dir': 'js'
				},
			'/index': {
					'tools.staticfile.on': True,
					'tools.staticfile.filename': 'index.html'
				},
			}
		)

	def stop(self):
		cherrypy.server.stop()
		cherrypy.engine.exit()


class SpectatorWebSocketHandler(WebSocket, Listener):
	def opened(self):
		self.lobotomy = WebServer.instance.lobotomy
		self.lobotomy.spectator_emitter.start_spectating(self, self.set_state)

	def set_state(self, state):
		state['type'] = 'server_state'
		self.send(json.dumps(state))

	def submit(self, **event):
		del event['server_state']
		self.send(json.dumps(event))

	def closed(self, event, reason):
		self.lobotomy.spectator_emitter.remove_listener(self)

class WebRoot(object):
	def __init__(self, host, port, ssl=False):
		self.host = host
		self.port = port
		self.scheme = 'wss' if ssl else 'ws'

	@cherrypy.expose
	def ws(self):
		cherrypy.log("Handler created: %s" % repr(cherrypy.request.ws_handler))


