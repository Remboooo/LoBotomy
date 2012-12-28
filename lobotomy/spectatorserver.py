from lobotomy.event import Listener
from lobotomy import config
import json
from queue import Queue, Empty
from threading import Thread
import socket
import logging


class SpectatorServer():
	"""
	Provides a simple read-only TCP interface with newline-separated JSON events relayed from the SpectatorEmitter
	"""
	def __init__(self, lobotomyserver, port = config.host.spectator_port, host = config.host.spectator_host):
		self.lobotomy = lobotomyserver
		self.port = port
		self.host = host
		self._ssock = socket.socket()
		self._ssock.bind((host, port))
		self._ssock.listen(5)
		logging.info('successfully bound to %s:%d, listening for spectators', host, port)
		self._shutdown = False
		t = Thread(name='spectator_server', target=self.serve_forever)
		t.daemon = True
		t.start()
		
	def serve_forever(self):
		while not self._shutdown:
			try:
				client, address = self._ssock.accept()
				logging.info('spectator from %s connected', address[0])
				Spectator(self, client)
			except Exception as e:
				if not self._shutdown:
					logging.critical('unexpected network error, shutting down server: %s', str(e))


	def stop(self):
		self._shutdown = True
		logging.info('shutting down spectator server')
		try:
			self._ssock.shutdown(socket.SHUT_RDWR)
			self._ssock.close()
		except:
			pass


class Spectator(Listener):
	def __init__(self, server, socket):
		super().__init__()
		self.lobotomy = server.lobotomy
		self.socket = socket
		self.lobotomy.spectator_emitter.start_spectating(self, self.set_state)

	def set_state(self, state):
		state['type'] = 'server_state'
		self.send(state)

	def submit(self, **event):
		del event['server_state']
		self.send(event)

	def send(self, message):
		try:
			self.socket.sendall(bytes(json.dumps(message)+'\n', 'utf-8'))
		except Exception as e:
			logging.info('Error sending spectator message, spectator disconnected: %s' % str(e))
			self.closed()

	def closed(self):
		self.lobotomy.spectator_emitter.remove_listener(self)
		try:
			self.socket.shutdown(socket.SHUT_RDWR)
			self.socket.close()
		except:
			pass

